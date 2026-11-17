import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shop.__main__ import main, run_demo
from shop.database import Database
from shop.seed import LEGACY_SAMPLE_PRODUCTS, SAMPLE_PRODUCTS, seed_products


class CommandTests(unittest.TestCase):
    def test_seed_is_repeatable_and_database_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "shop.db"
            database = Database(path)
            database.initialize()
            self.assertEqual(seed_products(database), len(SAMPLE_PRODUCTS))
            self.assertEqual(seed_products(database), 0)
            with database.transaction() as connection:
                connection.execute("UPDATE products SET price_cents = 1, stock = 2 WHERE sku = ?",
                                   (SAMPLE_PRODUCTS[0][0],))
            self.assertEqual(seed_products(database), 0)
            reopened = Database(path)
            reopened.initialize()
            with reopened.connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], len(SAMPLE_PRODUCTS))
                preserved = connection.execute(
                    "SELECT price_cents, stock FROM products WHERE sku = ?", (SAMPLE_PRODUCTS[0][0],)
                ).fetchone()
                self.assertEqual(tuple(preserved), (1, 2))
                categories = dict(connection.execute(
                    "SELECT category, COUNT(*) FROM products GROUP BY category"
                ).fetchall())
                self.assertEqual(categories, {"electronics": 3, "laptop": 3, "phones": 3, "tv": 3})
                seeded = connection.execute(
                    "SELECT sku, name, category, price_cents, stock FROM products"
                ).fetchall()
                self.assertEqual(len({row[0] for row in seeded}), len(SAMPLE_PRODUCTS))
                self.assertTrue(all(row[3] > 0 and row[4] >= 0 for row in seeded))
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_seed_archives_only_unreferenced_unchanged_legacy_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "legacy.db")
            database.initialize()
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                    ("legacy@example.com", "Legacy customer", "unused"),
                )
                user_id = connection.execute("SELECT id FROM users WHERE email = ?", ("legacy@example.com",)).fetchone()[0]
                product_ids = {}
                for legacy in LEGACY_SAMPLE_PRODUCTS:
                    product_ids[legacy[0]] = connection.execute(
                        "INSERT INTO products (sku, name, category, price_cents, stock) VALUES (?, ?, ?, ?, ?)",
                        legacy,
                    ).lastrowid
                connection.execute(
                    "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)",
                    (user_id, product_ids["ELEC-KB-001"], 1),
                )
                connection.execute(
                    "INSERT INTO wishlist_items (user_id, product_id) VALUES (?, ?)",
                    (user_id, product_ids["ELEC-MS-001"]),
                )
                order_id = connection.execute(
                    "INSERT INTO orders (user_id, total_cents, shipping_address, idempotency_key) "
                    "VALUES (?, ?, ?, ?)",
                    (user_id, 14999, "10 Main Street", "legacy-order"),
                ).lastrowid
                connection.execute(
                    "INSERT INTO order_items (order_id, product_id, product_name, unit_price_cents, quantity) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (order_id, product_ids["ELEC-HP-001"], "Noise Cancelling Headphones", 14999, 1),
                )
                connection.execute("UPDATE products SET price_cents = price_cents + 1 WHERE sku = ?",
                                   ("BAGS-LP-001",))

            self.assertEqual(seed_products(database), len(SAMPLE_PRODUCTS))
            with database.connection() as connection:
                legacy_rows = {
                    row["sku"]: dict(row) for row in connection.execute(
                        "SELECT sku, price_cents, stock, active FROM products WHERE sku LIKE 'ELEC-%' "
                        "OR sku LIKE 'HOME-%' OR sku LIKE 'BAGS-%'"
                    ).fetchall()
                }
                self.assertEqual(len(legacy_rows), len(LEGACY_SAMPLE_PRODUCTS))
                self.assertEqual(legacy_rows["ELEC-KB-001"]["active"], 1)
                self.assertEqual(legacy_rows["ELEC-MS-001"]["active"], 1)
                self.assertEqual(legacy_rows["ELEC-HP-001"]["active"], 1)
                self.assertEqual(legacy_rows["HOME-BT-001"]["active"], 0)
                self.assertEqual(legacy_rows["BAGS-LP-001"]["active"], 1)
                for legacy in LEGACY_SAMPLE_PRODUCTS:
                    row = legacy_rows[legacy[0]]
                    self.assertEqual(row["stock"], legacy[4])
                    self.assertEqual(row["price_cents"], legacy[3] + (1 if legacy[0] == "BAGS-LP-001" else 0))

    def test_initialization_adds_wishlist_without_changing_existing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "existing.db")
            database.initialize()
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                    ("existing@example.com", "Existing", "unused"),
                )
                connection.execute(
                    "INSERT INTO products (sku, name, category, price_cents, stock) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("OLD-001", "Legacy product", "Electronics", 1000, 7),
                )
                connection.execute("DROP TABLE wishlist_items")
            database.initialize()
            with database.connection() as connection:
                product = connection.execute("SELECT category, price_cents, stock FROM products WHERE sku = 'OLD-001'").fetchone()
                self.assertEqual(tuple(product), ("Electronics", 1000, 7))
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'wishlist_items'"
                ).fetchone())
                self.assertIsNotNone(connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_wishlist_product'"
                ).fetchone())

    def test_demo_runs_end_to_end(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_demo()
        result = json.loads(output.getvalue())
        self.assertEqual(result["placed_order"]["status"], "placed")
        self.assertEqual(result["placed_order"]["total_cents"], 179800)
        self.assertEqual(result["remaining_stock"], 10)
        self.assertEqual(result["cart_after_checkout"]["items"], [])

    def test_init_and_seed_commands_use_requested_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "cli.db")
            for command in ["init-db", "seed", "seed"]:
                with patch("sys.argv", ["shop", "--database", path, command]), contextlib.redirect_stdout(io.StringIO()):
                    main()
            with Database(path).connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], len(SAMPLE_PRODUCTS))


if __name__ == "__main__":
    unittest.main()
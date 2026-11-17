import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shop.__main__ import main, run_demo
from shop.database import Database
from shop.seed import SAMPLE_PRODUCTS, seed_products


class CommandTests(unittest.TestCase):
    def test_seed_is_repeatable_and_database_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "shop.db"
            database = Database(path)
            database.initialize()
            self.assertEqual(seed_products(database), len(SAMPLE_PRODUCTS))
            self.assertEqual(seed_products(database), 0)
            reopened = Database(path)
            reopened.initialize()
            with reopened.connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], 5)
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_demo_runs_end_to_end(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_demo()
        result = json.loads(output.getvalue())
        self.assertEqual(result["placed_order"]["status"], "placed")
        self.assertEqual(result["placed_order"]["total_cents"], 17998)
        self.assertEqual(result["remaining_stock"], 23)
        self.assertEqual(result["cart_after_checkout"]["items"], [])

    def test_init_and_seed_commands_use_requested_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "cli.db")
            for command in ["init-db", "seed", "seed"]:
                with patch("sys.argv", ["shop", "--database", path, command]), contextlib.redirect_stdout(io.StringIO()):
                    main()
            with Database(path).connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from shop.database import Database
from shop.errors import ConflictError, NotFoundError, ValidationError
from shop.services import CartService, CatalogService, OrderService, WishlistService


class ShoppingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(Path(self.temporary.name) / "test.db")
        self.database.initialize()
        with self.database.transaction() as connection:
            connection.executemany(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                [("alice@example.com", "Alice", "unused"), ("bob@example.com", "Bob", "unused")],
            )
        self.catalog = CatalogService(self.database)
        self.cart = CartService(self.database)
        self.orders = OrderService(self.database)
        self.wishlist = WishlistService(self.database)
        self.product = self.catalog.create_product("KB-01", "Laptop", "laptop", 4999, 5)

    def test_checkout_is_atomic_when_later_item_has_no_stock(self):
        second = self.catalog.create_product("MS-01", "Laptop mouse", "laptop", 1999, 1)
        self.cart.set_item(1, self.product["id"], 2)
        self.cart.set_item(1, second["id"], 1)
        self.catalog.adjust_stock(second["id"], -1)
        with self.assertRaises(ConflictError):
            self.orders.checkout(1, "10 Market Street", "failed-checkout")
        self.assertEqual(self.catalog.get_product(self.product["id"])["stock"], 5)
        self.assertEqual(len(self.cart.get_cart(1)["items"]), 2)
        self.assertEqual(self.orders.list_orders(1), [])

    def test_checkout_snapshots_price_and_is_idempotent(self):
        self.cart.set_item(1, self.product["id"], 2)
        order = self.orders.checkout(1, "10 Market Street", "checkout-1")
        repeated = self.orders.checkout(1, "10 Market Street", "checkout-1")
        self.assertEqual(order, repeated)
        self.assertEqual(order["total_cents"], 9998)
        self.assertEqual(self.catalog.get_product(self.product["id"])["stock"], 3)
        self.assertEqual(self.cart.get_cart(1)["items"], [])
        with self.database.transaction() as connection:
            connection.execute("UPDATE products SET price_cents = 1 WHERE id = ?", (self.product["id"],))
        self.assertEqual(self.orders.get_order(1, order["id"])["items"][0]["unit_price_cents"], 4999)

    def test_cancel_restores_stock_only_once(self):
        self.cart.set_item(1, self.product["id"], 2)
        order = self.orders.checkout(1, "10 Market Street", "cancel-me")
        self.orders.cancel_order(1, order["id"])
        self.orders.cancel_order(1, order["id"])
        self.assertEqual(self.catalog.get_product(self.product["id"])["stock"], 5)

    def test_customers_cannot_read_or_cancel_other_orders(self):
        self.cart.set_item(1, self.product["id"], 1)
        order = self.orders.checkout(1, "10 Market Street", "private-order")
        with self.assertRaises(NotFoundError):
            self.orders.get_order(2, order["id"])
        with self.assertRaises(NotFoundError):
            self.orders.cancel_order(2, order["id"])

    def test_shipped_order_cannot_be_cancelled(self):
        self.cart.set_item(1, self.product["id"], 1)
        order = self.orders.checkout(1, "10 Market Street", "ship-me")
        self.orders.ship_order(order["id"])
        with self.assertRaises(ConflictError):
            self.orders.cancel_order(1, order["id"])

    def test_validation_rejects_booleans_negative_prices_and_duplicate_skus(self):
        for quantity in [True, 0, -1, 1.5, "2"]:
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.cart.set_item(1, self.product["id"], quantity)
        with self.assertRaises(ValidationError):
            self.catalog.create_product("NEG", "Invalid", "tv", -1, 1)
        with self.assertRaises(ConflictError):
            self.catalog.create_product("KB-01", "Duplicate", "tv", 100, 1)

    def test_product_categories_are_canonical(self):
        for category in ["Electronics", "phone", "TV", "", None]:
            with self.subTest(category=category), self.assertRaises(ValidationError):
                self.catalog.create_product(f"INVALID-{category}", "Invalid", category, 100, 1)
        with self.assertRaises(ValidationError):
            self.catalog.list_products("Electronics")
        product = self.catalog.create_product("EL-01", "Wireless Mouse", "electronics", 3499, 12)
        self.assertEqual(self.catalog.list_products("electronics")[0]["id"], product["id"])

    def test_wishlist_is_persistent_deduplicated_and_user_scoped(self):
        self.wishlist.add_item(1, self.product["id"])
        self.wishlist.add_item(1, self.product["id"])
        self.assertEqual(len(self.wishlist.list_items(1)), 1)
        self.assertEqual(self.wishlist.list_items(2), [])
        reopened = Database(self.database.path)
        reopened.initialize()
        self.assertEqual(WishlistService(reopened).list_items(1)[0]["id"], self.product["id"])
        with self.assertRaises(NotFoundError):
            self.wishlist.remove_item(2, self.product["id"])
        self.wishlist.remove_item(1, self.product["id"])
        self.assertEqual(self.wishlist.list_items(1), [])

    def test_empty_cart_cannot_be_checked_out(self):
        with self.assertRaises(ValidationError):
            self.orders.checkout(1, "10 Market Street", "empty")

    def test_concurrent_buyers_cannot_oversell(self):
        self.catalog.adjust_stock(self.product["id"], -4)
        self.cart.set_item(1, self.product["id"], 1)
        self.cart.set_item(2, self.product["id"], 1)

        def purchase(user_id):
            try:
                self.orders.checkout(user_id, "10 Market Street", f"buyer-{user_id}")
                return "placed"
            except ConflictError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(purchase, [1, 2]))
        self.assertCountEqual(outcomes, ["placed", "rejected"])
        self.assertEqual(self.catalog.get_product(self.product["id"])["stock"], 0)


if __name__ == "__main__":
    unittest.main()
import sqlite3
from typing import Any

from shop.database import Database
from shop.errors import ConflictError, NotFoundError, ValidationError
from shop.repositories import CartRepository, OrderRepository, ProductRepository, WishlistRepository


PRODUCT_CATEGORIES = frozenset({"electronics", "laptop", "phones", "tv"})


def text(value: object, field: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValidationError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def integer(value: object, field: str, minimum: int = 1, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be an integer between {minimum} and {maximum}")
    return value


def product_category(value: object) -> str:
    category = text(value, "category", 80)
    if category not in PRODUCT_CATEGORIES:
        raise ValidationError("category must be one of: electronics, laptop, phones, tv")
    return category


class CatalogService:
    def __init__(self, database: Database):
        self.database = database

    def create_product(self, sku: str, name: str, category: str, price_cents: int, stock: int) -> dict[str, Any]:
        values = (text(sku, "sku", 64), text(name, "name"), product_category(category),
                  integer(price_cents, "price_cents", maximum=100_000_000), integer(stock, "stock", 0))
        try:
            with self.database.transaction() as connection:
                repository = ProductRepository(connection)
                return repository.get(repository.create(*values))
        except sqlite3.IntegrityError as error:
            raise ConflictError("SKU already exists") from error

    def list_products(self, category: str | None = None, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        integer(limit, "limit", maximum=100)
        integer(offset, "offset", 0)
        if category is not None:
            category = product_category(category)
        with self.database.connection() as connection:
            return ProductRepository(connection).list(category, limit, offset)

    def get_product(self, product_id: int) -> dict[str, Any]:
        with self.database.connection() as connection:
            product = ProductRepository(connection).get(product_id)
            if not product["active"]:
                raise NotFoundError("Product not found")
            return product

    def adjust_stock(self, product_id: int, delta: int) -> dict[str, Any]:
        integer(delta, "delta", -1_000_000)
        with self.database.transaction() as connection:
            repository = ProductRepository(connection)
            product = repository.get(product_id)
            integer(product["stock"] + delta, "resulting stock", 0)
            connection.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (delta, product_id))
            return repository.get(product_id)


class CartService:
    def __init__(self, database: Database):
        self.database = database

    def get_cart(self, user_id: int) -> dict[str, Any]:
        with self.database.connection() as connection:
            items = CartRepository(connection).items(user_id)
            return {"items": items, "total_cents": sum(item["price_cents"] * item["quantity"] for item in items)}

    def set_item(self, user_id: int, product_id: int, quantity: int) -> dict[str, Any]:
        integer(quantity, "quantity", maximum=1000)
        with self.database.transaction() as connection:
            product = ProductRepository(connection).get(product_id)
            if not product["active"] or product["stock"] < quantity:
                raise ConflictError("Product is unavailable or has insufficient stock")
            CartRepository(connection).set_quantity(user_id, product_id, quantity)
        return self.get_cart(user_id)

    def remove_item(self, user_id: int, product_id: int) -> None:
        with self.database.transaction() as connection:
            if not CartRepository(connection).remove(user_id, product_id):
                raise NotFoundError("Cart item not found")


class WishlistService:
    def __init__(self, database: Database):
        self.database = database

    def list_items(self, user_id: int) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            return WishlistRepository(connection).items(user_id)

    def add_item(self, user_id: int, product_id: int) -> dict[str, Any]:
        with self.database.transaction() as connection:
            product = ProductRepository(connection).get(product_id)
            if not product["active"]:
                raise NotFoundError("Product not found")
            repository = WishlistRepository(connection)
            repository.add(user_id, product_id)
            item = repository.get(user_id, product_id)
            assert item is not None
            return item

    def remove_item(self, user_id: int, product_id: int) -> None:
        with self.database.transaction() as connection:
            if not WishlistRepository(connection).remove(user_id, product_id):
                raise NotFoundError("Wishlist item not found")


class OrderService:
    def __init__(self, database: Database):
        self.database = database

    def checkout(self, user_id: int, shipping_address: str, idempotency_key: str) -> dict[str, Any]:
        address = text(shipping_address, "shipping_address", 1000)
        key = text(idempotency_key, "idempotency_key", 128)
        with self.database.transaction() as connection:
            orders = OrderRepository(connection)
            existing_id = orders.find_by_key(user_id, key)
            if existing_id is not None:
                existing = orders.get(existing_id, user_id)
                if existing["shipping_address"] != address:
                    raise ConflictError("Idempotency key already used with a different address")
                return existing
            cart = CartRepository(connection)
            items = cart.items(user_id)
            if not items:
                raise ValidationError("Cannot check out an empty cart")
            products = ProductRepository(connection)
            for item in items:
                if not products.reserve_stock(item["product_id"], item["quantity"]):
                    raise ConflictError(f"Insufficient stock for {item['name']}")
            order_id = orders.create(user_id, address, key, items)
            cart.clear(user_id)
            return orders.get(order_id, user_id)

    def get_order(self, user_id: int, order_id: int) -> dict[str, Any]:
        with self.database.connection() as connection:
            return OrderRepository(connection).get(order_id, user_id)

    def list_orders(self, user_id: int, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        integer(limit, "limit", maximum=100)
        integer(offset, "offset", 0)
        with self.database.connection() as connection:
            return OrderRepository(connection).list(user_id, limit, offset)

    def cancel_order(self, user_id: int, order_id: int) -> dict[str, Any]:
        with self.database.transaction() as connection:
            repository = OrderRepository(connection)
            order = repository.get(order_id, user_id)
            if order["status"] == "cancelled":
                return order
            if order["status"] != "placed":
                raise ConflictError("Only placed orders can be cancelled")
            for item in order["items"]:
                connection.execute("UPDATE products SET stock = stock + ? WHERE id = ?",
                                   (item["quantity"], item["product_id"]))
            connection.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
            return repository.get(order_id, user_id)

    def ship_order(self, order_id: int) -> None:
        with self.database.transaction() as connection:
            changed = connection.execute(
                "UPDATE orders SET status = 'shipped' WHERE id = ? AND status = 'placed'", (order_id,)
            ).rowcount
            if not changed:
                raise ConflictError("Order does not exist or is no longer placed")
import sqlite3
from typing import Any

from shop.errors import NotFoundError


class ProductRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, product_id: int) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Product not found")
        return dict(row)

    def list(self, category: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM products WHERE active = 1 "
            "AND (? IS NULL OR lower(category) = ?) ORDER BY id LIMIT ? OFFSET ?",
            (category, category, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def create(self, sku: str, name: str, category: str, price_cents: int, stock: int) -> int:
        cursor = self.connection.execute(
            "INSERT INTO products (sku, name, category, price_cents, stock) VALUES (?, ?, ?, ?, ?)",
            (sku, name, category, price_cents, stock),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def reserve_stock(self, product_id: int, quantity: int) -> bool:
        cursor = self.connection.execute(
            "UPDATE products SET stock = stock - ? "
            "WHERE id = ? AND active = 1 AND stock >= ?",
            (quantity, product_id, quantity),
        )
        return cursor.rowcount == 1


class CartRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def items(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT p.*, c.quantity, p.id AS product_id FROM cart_items c "
            "JOIN products p ON p.id = c.product_id WHERE c.user_id = ? ORDER BY p.id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_quantity(self, user_id: int, product_id: int, quantity: int) -> None:
        self.connection.execute(
            "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = excluded.quantity",
            (user_id, product_id, quantity),
        )

    def remove(self, user_id: int, product_id: int) -> bool:
        return self.connection.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        ).rowcount == 1

    def clear(self, user_id: int) -> None:
        self.connection.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))


class WishlistRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def items(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT p.*, p.id AS product_id FROM wishlist_items w "
            "JOIN products p ON p.id = w.product_id "
            "WHERE w.user_id = ? AND p.active = 1 ORDER BY p.id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add(self, user_id: int, product_id: int) -> None:
        self.connection.execute(
            "INSERT INTO wishlist_items (user_id, product_id) VALUES (?, ?) "
            "ON CONFLICT(user_id, product_id) DO NOTHING",
            (user_id, product_id),
        )

    def get(self, user_id: int, product_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT p.*, p.id AS product_id FROM wishlist_items w "
            "JOIN products p ON p.id = w.product_id "
            "WHERE w.user_id = ? AND w.product_id = ? AND p.active = 1",
            (user_id, product_id),
        ).fetchone()
        return dict(row) if row else None

    def remove(self, user_id: int, product_id: int) -> bool:
        return self.connection.execute(
            "DELETE FROM wishlist_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        ).rowcount == 1


class OrderRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(self, order_id: int, user_id: int) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)
        ).fetchone()
        if row is None:
            raise NotFoundError("Order not found")
        order = dict(row)
        order["items"] = [
            dict(item) for item in self.connection.execute(
                "SELECT product_id, product_name, unit_price_cents, quantity "
                "FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)
            ).fetchall()
        ]
        return order

    def find_by_key(self, user_id: int, key: str) -> int | None:
        row = self.connection.execute(
            "SELECT id FROM orders WHERE user_id = ? AND idempotency_key = ?", (user_id, key)
        ).fetchone()
        return row["id"] if row else None

    def create(self, user_id: int, address: str, key: str, items: list[dict[str, Any]]) -> int:
        total = sum(item["price_cents"] * item["quantity"] for item in items)
        cursor = self.connection.execute(
            "INSERT INTO orders (user_id, total_cents, shipping_address, idempotency_key) "
            "VALUES (?, ?, ?, ?)", (user_id, total, address, key)
        )
        order_id = cursor.lastrowid
        assert order_id is not None
        self.connection.executemany(
            "INSERT INTO order_items "
            "(order_id, product_id, product_name, unit_price_cents, quantity) VALUES (?, ?, ?, ?, ?)",
            [(order_id, item["product_id"], item["name"], item["price_cents"], item["quantity"])
             for item in items],
        )
        return order_id

    def list(self, user_id: int, limit: int, offset: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()]
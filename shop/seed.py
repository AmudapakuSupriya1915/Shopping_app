from shop.database import Database
from shop.repositories import ProductRepository


SAMPLE_PRODUCTS = (
    ("FORME-LP-001", "FORME Air 14 Laptop", "laptop", 89900, 12),
    ("FORME-LP-002", "FORME Studio 16 Laptop", "laptop", 149900, 6),
    ("FORME-LP-003", "FORME Everyday 15 Laptop", "laptop", 64900, 18),
    ("FORME-PH-001", "FORME One Smartphone", "phones", 69900, 20),
    ("FORME-PH-002", "FORME One Pro Smartphone", "phones", 99900, 8),
    ("FORME-PH-003", "FORME One Mini Smartphone", "phones", 54900, 15),
    ("FORME-TV-001", "FORME View 43-inch 4K TV", "tv", 39900, 9),
    ("FORME-TV-002", "FORME View 55-inch QLED TV", "tv", 69900, 7),
    ("FORME-TV-003", "FORME View 65-inch OLED TV", "tv", 129900, 4),
    ("FORME-EL-001", "FORME Click Wireless Mouse", "electronics", 3499, 40),
    ("FORME-EL-002", "FORME Studio Wireless Headphones", "electronics", 8999, 18),
    ("FORME-EL-003", "FORME Type Mechanical Keyboard", "electronics", 6999, 25),
)

LEGACY_SAMPLE_PRODUCTS = (
    ("ELEC-KB-001", "Mechanical Keyboard", "Electronics", 8999, 25),
    ("ELEC-MS-001", "Wireless Mouse", "Electronics", 2999, 50),
    ("ELEC-HP-001", "Noise Cancelling Headphones", "Electronics", 14999, 15),
    ("HOME-BT-001", "Insulated Water Bottle", "Home", 2499, 60),
    ("BAGS-LP-001", "Laptop Backpack", "Accessories", 5999, 30),
)


def seed_products(database: Database) -> int:
    created = 0
    with database.transaction() as connection:
        repository = ProductRepository(connection)
        for legacy in LEGACY_SAMPLE_PRODUCTS:
            connection.execute(
                "UPDATE products SET active = 0 "
                "WHERE sku = ? AND name = ? AND category = ? AND price_cents = ? AND stock = ? "
                "AND active = 1 "
                "AND NOT EXISTS (SELECT 1 FROM cart_items WHERE product_id = products.id) "
                "AND NOT EXISTS (SELECT 1 FROM wishlist_items WHERE product_id = products.id) "
                "AND NOT EXISTS (SELECT 1 FROM order_items WHERE product_id = products.id)",
                legacy,
            )
        for product in SAMPLE_PRODUCTS:
            if connection.execute("SELECT 1 FROM products WHERE sku = ?", (product[0],)).fetchone() is None:
                repository.create(*product)
                created += 1
    return created
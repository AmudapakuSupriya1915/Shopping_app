from shop.database import Database
from shop.repositories import ProductRepository


SAMPLE_PRODUCTS = (
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
        for product in SAMPLE_PRODUCTS:
            if connection.execute("SELECT 1 FROM products WHERE sku = ?", (product[0],)).fetchone() is None:
                repository.create(*product)
                created += 1
    return created
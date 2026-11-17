import argparse
import getpass
import json
import logging
import os
import secrets
import tempfile
from pathlib import Path

from shop.auth import AuthService
from shop.database import Database
from shop.errors import ShopError, ValidationError
from shop.seed import seed_products
from shop.services import CartService, CatalogService, OrderService


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "demo.db")
        database.initialize()
        seed_products(database)
        customer = AuthService(database).register("demo@example.com", "Demo Customer", secrets.token_urlsafe(24))
        catalog = CatalogService(database)
        product = catalog.list_products()[0]
        carts = CartService(database)
        cart = carts.set_item(customer["id"], product["id"], 2)
        orders = OrderService(database)
        order = orders.checkout(customer["id"], "100 Market Street, San Francisco, CA", "demo-checkout")
        print(json.dumps({
            "customer": customer,
            "cart_before_checkout": cart,
            "placed_order": order,
            "remaining_stock": catalog.get_product(product["id"])["stock"],
            "cart_after_checkout": carts.get_cart(customer["id"]),
        }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Enterprise shopping backend example")
    parser.add_argument("--database", default=os.environ.get("SHOP_DATABASE", "instance/shop.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create the SQLite database and tables")
    commands.add_parser("seed", help="Add sample products without overwriting existing products")
    commands.add_parser("demo", help="Run a complete shopping flow in a temporary database")
    admin = commands.add_parser("create-admin", help="Create an administrator using a hidden password prompt")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    server = commands.add_parser("serve", help="Start the local development API server")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "demo":
            run_demo()
            return
        database = Database(args.database)
        database.initialize()
        if args.command == "init-db":
            print(f"Database ready: {database.path.resolve()}")
        elif args.command == "seed":
            print(f"Created {seed_products(database)} sample products")
        elif args.command == "create-admin":
            password = getpass.getpass("Admin password (12-128 characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise ValidationError("Passwords do not match")
            user = AuthService(database).register(args.email, args.name, password, role="admin")
            print(f"Administrator created: {user['email']}")
        elif args.command == "serve":
            from shop.api import create_app

            create_app(database.path).run(host=args.host, port=args.port, debug=False, use_reloader=False)
    except ShopError as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
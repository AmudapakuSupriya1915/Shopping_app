import os
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from shop.auth import AuthService
from shop.database import Database
from shop.errors import AuthenticationError, ForbiddenError, ShopError, ValidationError
from shop.services import CartService, CatalogService, OrderService, WishlistService


def create_app(database_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    database = Database(database_path or os.environ.get("SHOP_DATABASE", "instance/shop.db"))
    database.initialize()
    app.extensions["shop_database"] = database
    auth = AuthService(database)
    catalog = CatalogService(database)
    carts = CartService(database)
    wishlist = WishlistService(database)
    orders = OrderService(database)

    def authenticated(*, admin: bool = False):
        def decorate(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                scheme, _, token = request.headers.get("Authorization", "").partition(" ")
                if scheme.lower() != "bearer" or not token or len(token) > 256:
                    raise AuthenticationError("A Bearer access token is required")
                g.user = auth.authenticate(token)
                g.token = token
                if admin and g.user["role"] != "admin":
                    raise ForbiddenError("Administrator access required")
                return view(*args, **kwargs)
            return wrapped
        return decorate

    def body() -> dict:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        return data

    def pagination() -> tuple[int, int]:
        try:
            return int(request.args.get("limit", "20")), int(request.args.get("offset", "0"))
        except ValueError as error:
            raise ValidationError("limit and offset must be integers") from error

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ShopError)
    def domain_error(error):
        response = jsonify({"error": {"code": type(error).__name__, "message": str(error)}})
        if error.status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response, error.status_code

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = app.json.dumps({"error": {"code": error.name, "message": error.description}})
        response.content_type = "application/json"
        return response

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.exception("Database operation failed")
        return jsonify({"error": {"code": "DatabaseUnavailable", "message": "Database temporarily unavailable"}}), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unexpected request failure")
        return jsonify({"error": {"code": "InternalError", "message": "Internal server error"}}), 500

    @app.get("/")
    def storefront():
        return render_template("storefront.html")

    @app.get("/health")
    def health():
        with database.connection() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.post("/api/auth/register")
    def register():
        data = body()
        return auth.register(data.get("email"), data.get("name"), data.get("password")), 201

    @app.post("/api/auth/login")
    def login():
        data = body()
        return auth.login(data.get("email"), data.get("password"))

    @app.post("/api/auth/logout")
    @authenticated()
    def logout():
        auth.logout(g.token)
        return "", 204

    @app.get("/api/auth/me")
    @authenticated()
    def current_user():
        return g.user

    @app.get("/api/products")
    def list_products():
        limit, offset = pagination()
        return {"items": catalog.list_products(request.args.get("category"), limit, offset)}

    @app.get("/api/products/<int:product_id>")
    def get_product(product_id):
        return catalog.get_product(product_id)

    @app.post("/api/products")
    @authenticated(admin=True)
    def create_product():
        data = body()
        return catalog.create_product(data.get("sku"), data.get("name"), data.get("category"),
                                      data.get("price_cents"), data.get("stock")), 201

    @app.patch("/api/products/<int:product_id>/stock")
    @authenticated(admin=True)
    def adjust_stock(product_id):
        return catalog.adjust_stock(product_id, body().get("delta"))

    @app.get("/api/cart")
    @authenticated()
    def get_cart():
        return carts.get_cart(g.user["id"])

    @app.put("/api/cart/items/<int:product_id>")
    @authenticated()
    def set_cart_item(product_id):
        return carts.set_item(g.user["id"], product_id, body().get("quantity"))

    @app.delete("/api/cart/items/<int:product_id>")
    @authenticated()
    def remove_cart_item(product_id):
        carts.remove_item(g.user["id"], product_id)
        return "", 204

    @app.get("/api/wishlist")
    @authenticated()
    def get_wishlist():
        return {"items": wishlist.list_items(g.user["id"])}

    @app.post("/api/wishlist/items/<int:product_id>")
    @authenticated()
    def add_wishlist_item(product_id):
        return wishlist.add_item(g.user["id"], product_id)

    @app.delete("/api/wishlist/items/<int:product_id>")
    @authenticated()
    def remove_wishlist_item(product_id):
        wishlist.remove_item(g.user["id"], product_id)
        return "", 204

    @app.post("/api/orders")
    @authenticated()
    def checkout():
        return orders.checkout(g.user["id"], body().get("shipping_address"),
                               request.headers.get("Idempotency-Key")), 201

    @app.get("/api/orders")
    @authenticated()
    def list_orders():
        limit, offset = pagination()
        return {"items": orders.list_orders(g.user["id"], limit, offset)}

    @app.get("/api/orders/<int:order_id>")
    @authenticated()
    def get_order(order_id):
        return orders.get_order(g.user["id"], order_id)

    @app.post("/api/orders/<int:order_id>/cancel")
    @authenticated()
    def cancel_order(order_id):
        return orders.cancel_order(g.user["id"], order_id)

    @app.post("/api/orders/<int:order_id>/ship")
    @authenticated(admin=True)
    def ship_order(order_id):
        orders.ship_order(order_id)
        return "", 204

    return app
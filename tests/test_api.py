import tempfile
import unittest
from pathlib import Path

from shop.api import create_app
from shop.auth import AuthService
from shop.services import CatalogService


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.app = create_app(Path(cls.temporary.name) / "api.db")
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.database = cls.app.extensions["shop_database"]
        cls.auth = AuthService(cls.database)
        cls.auth.register("admin@example.com", "Admin", "administrator-pass", role="admin")
        cls.auth.register("customer@example.com", "Customer", "customer-password")
        cls.auth.register("other@example.com", "Other", "another-password")
        cls.admin = cls.headers("admin@example.com", "administrator-pass")
        cls.customer = cls.headers("customer@example.com", "customer-password")
        cls.other = cls.headers("other@example.com", "another-password")

    @classmethod
    def headers(cls, email, password):
        token = cls.auth.login(email, password)["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def new_product(self, sku):
        return CatalogService(self.database).create_product(sku, "Laptop", "laptop", 12500, 10)

    def test_storefront_is_served_without_changing_api_responses(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn(b"FORME", response.data)
        self.assertIn(b'id="product-grid"', response.data)
        self.assertIn(b'id="checkout-form"', response.data)
        self.assertIn(b'id="theme-button"', response.data)
        for asset in ["storefront.css", "storefront.js", "forme-mark.svg"]:
            with self.client.get(f"/static/{asset}") as asset_response:
                self.assertEqual(asset_response.status_code, 200)
        self.assertTrue(self.client.get("/api/products").is_json)

    def test_customer_shopping_workflow(self):
        product = self.new_product("WORKFLOW")
        response = self.client.put(f"/api/cart/items/{product['id']}", json={"quantity": 2}, headers=self.customer)
        self.assertEqual(response.status_code, 200)
        headers = {**self.customer, "Idempotency-Key": "workflow-checkout"}
        response = self.client.post("/api/orders", json={"shipping_address": "10 Main Street"}, headers=headers)
        self.assertEqual(response.status_code, 201)
        order = response.get_json()
        self.assertEqual(order["total_cents"], 25000)
        replay = self.client.post("/api/orders", json={"shipping_address": "10 Main Street"}, headers=headers)
        self.assertEqual(replay.get_json()["id"], order["id"])
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}", headers=self.other).status_code, 404)
        self.assertEqual(self.client.post(f"/api/orders/{order['id']}/cancel", headers=self.other).status_code, 404)
        self.assertEqual(self.client.post(f"/api/orders/{order['id']}/cancel", headers=self.customer).status_code, 200)

    def test_permissions_are_enforced(self):
        self.assertEqual(self.client.get("/api/cart").status_code, 401)
        self.assertEqual(self.client.get("/api/cart", headers={"Authorization": "Bearer bad"}).status_code, 401)
        self.assertEqual(self.client.post("/api/products", json={}, headers=self.customer).status_code, 403)
        self.assertEqual(self.client.post("/api/orders/1/ship", headers=self.customer).status_code, 403)

    def test_admin_can_create_and_restock_products(self):
        response = self.client.post("/api/products", headers=self.admin, json={
            "sku": "ADMIN", "name": "Television", "category": "tv", "price_cents": 23000, "stock": 3,
        })
        self.assertEqual(response.status_code, 201)
        product_id = response.get_json()["id"]
        response = self.client.patch(f"/api/products/{product_id}/stock", headers=self.admin, json={"delta": 5})
        self.assertEqual(response.get_json()["stock"], 8)

    def test_registration_cannot_grant_admin_and_never_exposes_hash(self):
        response = self.client.post("/api/auth/register", json={
            "email": "new@example.com", "name": "New", "password": "new-customer-password", "role": "admin",
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["role"], "customer")
        self.assertNotIn("password_hash", response.get_json())
        duplicate = self.client.post("/api/auth/register", json={
            "email": "NEW@example.com", "name": "New", "password": "new-customer-password",
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_login_logout_and_expired_sessions(self):
        response = self.client.post("/api/auth/login", json={
            "email": "customer@example.com", "password": "customer-password",
        })
        self.assertEqual(response.status_code, 200)
        headers = {"Authorization": f"Bearer {response.get_json()['access_token']}"}
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/logout", headers=headers).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)
        expired = AuthService(self.database, session_seconds=-1).login("customer@example.com", "customer-password")
        self.assertEqual(self.client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {expired['access_token']}",
        }).status_code, 401)
        invalid = self.client.post("/api/auth/login", json={
            "email": "customer@example.com", "password": "incorrect-password",
        })
        self.assertEqual(invalid.status_code, 401)

    def test_bad_json_and_unknown_routes_return_json(self):
        self.assertEqual(self.client.post("/api/auth/register", json=[]).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/register", json={}).status_code, 400)
        malformed = self.client.post("/api/auth/register", data="{broken", content_type="application/json")
        self.assertEqual(malformed.status_code, 400)
        self.assertTrue(malformed.is_json)
        unknown = self.client.get("/missing")
        self.assertEqual(unknown.status_code, 404)
        self.assertTrue(unknown.is_json)
        method = self.client.put("/api/products")
        self.assertEqual(method.status_code, 405)
        self.assertIn("GET", method.headers["Allow"])

    def test_catalog_pagination_and_sql_injection_are_safe(self):
        product = self.new_product("FILTER")
        electronic = CatalogService(self.database).create_product("FILTER-ELECTRONIC", "Wireless Mouse", "electronics", 3499, 5)
        self.assertEqual(self.client.get("/api/products?limit=1").status_code, 200)
        self.assertEqual(self.client.get("/api/products?limit=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/products?limit=101").status_code, 400)
        response = self.client.get("/api/products", query_string={"category": "' OR 1=1 --"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/products?category=laptop").get_json()["items"][0]["id"], product["id"])
        self.assertEqual(self.client.get("/api/products?category=Electronics").status_code, 400)
        electronics = self.client.get("/api/products?category=electronics").get_json()["items"]
        self.assertIn(electronic["id"], [item["id"] for item in electronics])
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_wishlist_requires_auth_and_is_owned_by_each_customer(self):
        product = self.new_product("WISH-LAPTOP")
        path = f"/api/wishlist/items/{product['id']}"
        self.assertEqual(self.client.get("/api/wishlist").status_code, 401)
        self.assertEqual(self.client.post(path).status_code, 401)
        self.assertEqual(self.client.delete(path).status_code, 401)

        saved = self.client.post(path, headers=self.customer)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["product_id"], product["id"])
        self.assertEqual(self.client.post(path, headers=self.customer).status_code, 200)
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self.customer).get_json()["items"]), 1)
        self.assertEqual(self.client.get("/api/wishlist", headers=self.other).get_json()["items"], [])
        self.assertEqual(self.client.delete(path, headers=self.other).status_code, 404)
        self.assertEqual(len(self.client.get("/api/wishlist", headers=self.customer).get_json()["items"]), 1)
        self.assertEqual(self.client.delete(path, headers=self.customer).status_code, 204)
        self.assertEqual(self.client.get("/api/wishlist", headers=self.customer).get_json()["items"], [])


if __name__ == "__main__":
    unittest.main()
# FORME Shopping Website

A modular shopping application with a browser storefront, Flask REST API, and SQLite database. Customers can browse products, save favorites, create an account, manage a shopping bag, place demo orders, and cancel unshipped orders. Administrators manage inventory and shipment status through the API.

The frontend and API run on the same Flask server. There is no separate frontend server, Node.js installation, or JavaScript build step. This is an enterprise-style reference application, not a production-ready commerce platform. Orders do not collect payment.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Using the Website](#using-the-website)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Configuration and CLI](#configuration-and-cli)
- [Administrator Setup](#administrator-setup)
- [API Reference](#api-reference)
- [API Purchase Example](#api-purchase-example)
- [Database and Transactions](#database-and-transactions)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Security and Production Boundaries](#security-and-production-boundaries)

## Features

| Area | Available functionality |
|---|---|
| Catalog | Product photos and details, text search, Electronics/Laptop/Phones/TV filters, price/name sorting |
| Saved items | Guest favorites saved in this browser; signed-in wishlist persisted to the customer account |
| Appearance | Responsive light/dark theme toggle, with the selection remembered in this browser |
| Stock | Per-product availability and quantity controls; browser reminder for out-of-stock products |
| Accounts | Registration, sign-in, profile, and sign-out |
| Shopping bag | Add products, change quantities, remove items, and see the subtotal |
| Checkout | Shipping address, stock checks, and duplicate-order protection |
| Orders | Order history, item details, and cancellation of placed orders |
| Administration | API-only product creation, stock adjustment, and order shipment |
| Persistence | SQLite-backed accounts, sessions, products, carts, wishlists, and orders |

## Stack

- Python 3.11+ with Flask; SQLite through the standard-library `sqlite3` module.
- Jinja-rendered HTML, CSS, and vanilla JavaScript; locally served Lucide icons and photos.
- Product photos, including the laptop, phone, and TV catalog images, are stored locally in `shop/static`; the new category photos are sourced from Unsplash.
- Back-in-stock reminders are stored in the browser and checked while the storefront is open or when it is revisited; no email or push notification service is configured.
- Google Fonts for DM Sans and Instrument Serif; an internet connection is needed to load these fonts.
- Layered API, authentication, business services, repositories, and database connection management.
- File-backed persistence, foreign keys, constraints, indexes, WAL mode, parameterized SQL, and explicit transactions.
- Salted PBKDF2-SHA256 password hashes, hashed bearer tokens, eight-hour sessions, and admin permissions.
- Integer USD cents throughout; no floating-point monetary calculations.
- Standard-library `unittest` tests and a GitHub Actions Python version matrix.

## Requirements

- Python 3.11 or newer with `venv` and `pip` available.
- A modern browser with JavaScript enabled.
- Internet access for the initial Python dependency installation and optional web fonts.

SQLite is included with standard Python installations; no separate database service is required. The commands below target macOS/Linux and should be run from the project root.

## Quick Start

### 1. Create the Environment and Install Dependencies
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

For an existing checkout with `.venv` already created, run only the dependency installation command. All commands use the virtual environment explicitly, so activation is optional.

### 2. Initialize and Seed SQLite

```bash
.venv/bin/python -m shop init-db
.venv/bin/python -m shop seed
```

The default database is `instance/shop.db`. Seeding adds twelve sample products, three each in the canonical `electronics`, `laptop`, `phones`, and `tv` categories. Prices are integer USD cents. Repeating the seed command does not duplicate products or overwrite their product data or stock.

When seeding an older database, the command also archives the five exact legacy demo products from earlier FORME versions by setting `active = 0`, but only when their original SKU, name, category, price, and stock still match and they are not referenced by a cart, wishlist, or order. It does not delete rows or change prices or stock. Customized or customer-referenced legacy products remain active and untouched. The migration is repeatable and uses the existing database; no reset or manual schema migration is required.

For an existing database, `init-db` (also run automatically by the server) adds the `wishlist_items` table and its index with `CREATE ... IF NOT EXISTS`; it leaves existing rows and table definitions untouched. Then run `seed` to add the catalog and apply the narrowly scoped legacy-sample handling above.

### 3. Start the Website

```bash
.venv/bin/python -m shop serve --port 8001
```

Open **[http://127.0.0.1:8001/](http://127.0.0.1:8001/)** in your browser. Keep the terminal running while you use the website. Stop the server with `Ctrl+C`.

| URL | Result |
|---|---|
| `http://127.0.0.1:8001/` | FORME shopping storefront |
| `http://127.0.0.1:8001/health` | JSON database connectivity status |
| `http://127.0.0.1:8001/api/products` | JSON product catalog |

These examples use port `8001`. The CLI defaults to `8000` if `--port` is omitted. If a port is already in use, choose another port and use it in the browser URL as well.

### Optional: Run a Console Demo

```bash
.venv/bin/python -m shop demo
```

The demo prints a customer, cart, placed order, remaining inventory, and cleared cart. It uses a temporary database and does not change your persistent storefront data.

## Using the Website

1. Open the homepage and browse the catalog. Search, select a category, or change the sort order to narrow the results.
2. Open a product for details. Use its heart control to save it; the **Saved** navigation item shows your wishlist. Guest favorites stay in this browser until you sign in. On sign-in, they are merged into your account wishlist without duplicates. Product cards show current stock and let you choose a quantity up to the available limit. Out-of-stock products offer **Remind me**; the browser checks for restocks while the storefront is open and on your next visit.
3. Select the account icon and choose **Create account**. Enter a name, email, and a password containing 12-128 characters. Existing customers can choose **Sign in**.
4. Add products to your bag. Sign in when prompted, then use **Bag** to review quantities, remove items, and see the subtotal.
5. Enter a shipping address and select **Place order**. This creates a demo order; no payment is requested or collected.
6. Open **Orders** to review purchases. Placed orders can be cancelled; shipped orders cannot. Cancellation restores inventory.
7. Open the account dialog to sign out.

Guest saved product IDs are stored in browser `localStorage` until sign-in. After sign-in, favorites are merged into the account's SQLite wishlist; signed-in changes then synchronize with the server, so the wishlist follows the account across browsers. The access token is stored in `sessionStorage` for that browser tab's session; it also expires on the server after eight hours. Accounts, shopping bags, wishlists, and orders are stored in SQLite and remain available after signing back in. Clearing browser storage removes unsynchronized guest favorites, but does not remove a server-saved wishlist.

The storefront is customer-facing. Signing in as an administrator does not reveal an admin dashboard; use the protected API endpoints for inventory and shipment operations.

## Project Structure

```text
.
|-- shop/
|   |-- __init__.py
|   |-- __main__.py       # CLI: initialize, seed, demo, create admin, serve
|   |-- api.py            # Flask routes, authentication guards, JSON errors
|   |-- auth.py           # Registration, password verification, sessions
|   |-- database.py       # Connections, transaction lifecycle, initialization
|   |-- errors.py         # Domain exceptions and HTTP status mapping
|   |-- repositories.py   # Parameterized product, cart, and order queries
|   |-- schema.sql        # Seven related tables, constraints, indexes
|   |-- seed.py           # Repeatable canonical catalog and safe legacy cleanup
|   |-- services.py       # Catalog, cart, wishlist, checkout, order state transitions
|   |-- templates/
|   |   `-- storefront.html  # Homepage and account, bag, product, order dialogs
|   `-- static/
|       |-- storefront.css  # Responsive storefront styling
|       |-- storefront.js   # UI state and same-origin API requests
|       |-- lucide.min.js   # Locally served icon library
|       |-- forme-mark.svg  # Local FORME logo mark
|       `-- *.jpg           # Workspace and product photos
|-- tests/
|   |-- __init__.py
|   |-- test_api.py
|   |-- test_cli.py
|   `-- test_services.py
|-- .github/workflows/tests.yml
|-- .gitignore
|-- requirements.txt
|-- instance/             # Generated local database; excluded from Git
`-- README.md
```

The `.venv` directory, Python caches, and SQLite files are excluded from Git. Product photos are static presentation assets; product records in SQLite do not contain uploaded images.

## Architecture

```text
Browser
  |-- GET / ------------------> Flask / Jinja template
  |-- GET /static/... ---------> CSS, JavaScript, icons, photos
  `-- /api/... ---------------> Routes and authentication guards
              |
         Business services
              |
           Repositories / SQL queries
              |
            SQLite connections
              |
             instance/shop.db
```

Routes validate request shape and permissions, services enforce business rules, and repositories encapsulate catalog/cart/order queries. Authentication manages its user and session SQL directly. The database module owns connection cleanup and transaction boundaries. The frontend calls relative `/api/...` URLs on the same origin; no CORS setup is required for this arrangement.

| Class | Main methods |
|---|---|
| `Database` | `connect`, `initialize`, `connection`, `transaction` |
| `AuthService` | `register`, `login`, `authenticate`, `logout` |
| `CatalogService` | `create_product`, `list_products`, `get_product`, `adjust_stock` |
| `CartService` | `get_cart`, `set_item`, `remove_item` |
| `WishlistService` | `list_items`, `add_item`, `remove_item` |
| `OrderService` | `checkout`, `get_order`, `list_orders`, `cancel_order`, `ship_order` |
| Repositories | Product queries, guarded stock reservations, cart upserts, order snapshots |

## Configuration and CLI

| Setting | Default | Description |
|---|---|---|
| `SHOP_DATABASE` | `instance/shop.db` | SQLite file path; relative paths resolve from the current working directory |
| `--database PATH` | Environment/default path | CLI database override; place before the subcommand |
| `serve --host HOST` | `127.0.0.1` | Server bind address; keep the default for local-only use |
| `serve --port PORT` | `8000` | Development server port |

Use the same database setting for initialization, seeding, account creation, and serving:

```bash
export SHOP_DATABASE="instance/development.db"
.venv/bin/python -m shop init-db
.venv/bin/python -m shop seed
.venv/bin/python -m shop serve --port 8001
```

Alternatively, pass an explicit path for each operation:

```bash
.venv/bin/python -m shop --database instance/development.db seed
.venv/bin/python -m shop --database instance/development.db serve --port 8001
```

| Command | Purpose |
|---|---|
| `init-db` | Create the database directory and missing tables/indexes |
| `seed` | Initialize the database if needed and add missing sample products |
| `demo` | Run an isolated console shopping workflow in a temporary database |
| `create-admin --email EMAIL --name NAME` | Create an admin using hidden password prompts |
| `serve` | Initialize the database if needed and start the development server |

View help with `.venv/bin/python -m shop --help` or `.venv/bin/python -m shop serve --help`. Schema initialization does not migrate existing table definitions.

## Administrator Setup

Run the following in a terminal; enter and confirm the password at the hidden prompts:

```bash
.venv/bin/python -m shop create-admin --email admin@example.com --name Administrator
```

There are no default administrator credentials. Public registration always creates a customer, regardless of any supplied role.

Admins sign in through the same login endpoint as customers. Use the resulting bearer token with the admin-only endpoints below. Do not put real passwords in source files or command-line arguments.

## API Reference

JSON request bodies require `Content-Type: application/json`. Authenticated requests require `Authorization: Bearer <access_token>`. Responses use JSON except successful `204` responses, which have no body.

| Method | Endpoint | Access | Input / purpose |
|---|---|---|---|
| GET | `/` | Public | HTML storefront, not a JSON response |
| GET | `/health` | Public | Database connectivity |
| POST | `/api/auth/register` | Public | `email`, `name`, `password` |
| POST | `/api/auth/login` | Public | `email`, `password`; returns token |
| POST | `/api/auth/logout` | Customer/admin | Revoke current token |
| GET | `/api/auth/me` | Customer/admin | Current profile |
| GET | `/api/products` | Public | Optional `category`, `limit`, `offset` |
| GET | `/api/products/<id>` | Public | Product details |
| GET | `/api/wishlist` | Customer/admin | List the signed-in user's saved products |
| POST | `/api/wishlist/items/<id>` | Customer/admin | Save a product to the signed-in user's wishlist |
| DELETE | `/api/wishlist/items/<id>` | Customer/admin | Remove a product from the signed-in user's wishlist |
| POST | `/api/products` | Admin | `sku`, `name`, `category`, `price_cents`, `stock` |
| PATCH | `/api/products/<id>/stock` | Admin | Signed integer `delta` |
| GET | `/api/cart` | Customer/admin | Own cart and current total |
| PUT | `/api/cart/items/<id>` | Customer/admin | Set absolute `quantity` (1-1000) |
| DELETE | `/api/cart/items/<id>` | Customer/admin | Remove own item |
| POST | `/api/orders` | Customer/admin | `shipping_address`; `Idempotency-Key` header required |
| GET | `/api/orders` | Customer/admin | Own orders; `limit`, `offset` |
| GET | `/api/orders/<id>` | Owner | Own order and historical line items |
| POST | `/api/orders/<id>/cancel` | Owner | Cancel and restore inventory |
| POST | `/api/orders/<id>/ship` | Admin | Mark a placed order shipped |

List endpoints return `{"items": [...]}`. Pagination defaults to `limit=20`, `offset=0`; maximum limit is 100. Product categories use exact matching and accept only `electronics`, `laptop`, `phones`, and `tv`. Wishlist routes always use the authenticated user's ID and cannot read or modify another customer's saved items. Order access is ownership-scoped, including for administrators; shipment is a separate admin operation.

API errors use this structure:

```json
{
  "error": {
    "code": "ConflictError",
    "message": "Product is unavailable or has insufficient stock"
  }
}
```

| Status | Meaning |
|---|---|
| `400` | Invalid input, malformed JSON, or empty cart checkout |
| `401` | Missing, invalid, expired, or revoked access token |
| `403` | Administrator permission required |
| `404` | Resource not found or order not owned by the caller |
| `405` | HTTP method not supported by the route |
| `409` | Stock, order state, duplicate SKU/email, or idempotency conflict |
| `413` | Request body exceeds the 16 KiB limit |
| `415` | JSON endpoint called without the required JSON content type |
| `500` | Unexpected internal error; details are logged server-side |
| `503` | Database operation temporarily unavailable |

## API Purchase Example

Keep the server running and execute these commands in a second terminal at the project root. They use a local demo password, not a real credential. Registration returns `409` if this example account already exists; sign in with its existing password instead.

```bash
BASE_URL="http://127.0.0.1:8001"

curl -sS "$BASE_URL/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","name":"Alice","password":"local-demo-password"}'

TOKEN=$(curl -sS "$BASE_URL/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"local-demo-password"}' \
  | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl -sS "$BASE_URL/api/products"
```

Choose an active product ID from the catalog response. IDs vary between fresh and previously populated databases:

```bash
PRODUCT_ID=$(curl -sS "$BASE_URL/api/products?limit=1" \
  | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["items"][0]["id"])')

curl -sS -X PUT "$BASE_URL/api/cart/items/$PRODUCT_ID" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"quantity":2}'

curl -sS "$BASE_URL/api/orders" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: alice-order-001' \
  -d '{"shipping_address":"100 Market Street, San Francisco, CA"}'

curl -sS "$BASE_URL/api/orders" \
  -H "Authorization: Bearer $TOKEN"
```

Retry checkout with the same key and address to retrieve the same order without another stock deduction. Use a new key for a new purchase. Reusing the key with a different address returns `409`. API money fields are USD cents: `8999` means `$89.99`.

## Database and Transactions

| Table | Purpose and relationships |
|---|---|
| `users` | Unique email, display name, password hash, and customer/admin role |
| `sessions` | Hashed access token and expiry; references a user |
| `products` | Unique SKU, name, category, price in cents, stock, and active flag |
| `cart_items` | One quantity per user/product pair; references users and products |
| `wishlist_items` | One saved product per user/product pair; references users and products, with a unique pair constraint and product lookup index |
| `orders` | Owner, status, subtotal, address, timestamp, and per-user idempotency key |
| `order_items` | Purchased name, unit price, and quantity; references orders and products |

### Checkout Guarantees

1. Adding to a cart does not reserve stock. Availability and current prices are rechecked at checkout.
2. Checkout opens `BEGIN IMMEDIATE`, serializing SQLite writers before reading mutable cart/inventory state.
3. Each stock deduction uses a guarded update requiring sufficient stock and an active product.
4. Stock deduction, order/item creation, and cart clearing commit together. Any exception rolls them all back.
5. A unique `(user_id, idempotency_key)` prevents duplicate orders on retries. Keys identify a purchase, not the current cart; a replay does not buy newly added items.
6. Order lines retain the purchased name and price even when the catalog later changes.
7. Order transitions are `placed -> shipped` or `placed -> cancelled`. Repeated cancellation does not restore stock twice. Shipped orders cannot be cancelled.

Each operation owns and closes its database connection. Connections enable foreign keys and a ten-second busy timeout. SQLite permits concurrent readers but only one writer; WAL does not remove that limitation.

## Testing

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary databases, not `instance/shop.db`:

| Test module | Coverage |
|---|---|
| `tests/test_api.py` | Homepage and CSS/JS delivery, JSON API behavior, customer workflow, wishlist auth/ownership, role guards, sessions, validation, and SQL injection handling |
| `tests/test_services.py` | Atomic rollback, concurrent buyers, idempotency, historical prices, cancellation, and stock validation |
| `tests/test_cli.py` | Canonical catalog seeding, legacy sample preservation, persistent database integrity, wishlist-table initialization, CLI commands, and isolated demo |

Run one module with `.venv/bin/python -m unittest tests.test_api -v`. GitHub Actions runs the unit/integration suite on Python 3.11, 3.12, 3.13, and 3.14.

The automated suite verifies HTML and asset delivery but does not execute browser JavaScript or validate responsive rendering. For a manual frontend smoke test, check search/filter/sort, saved items, registration/sign-in, bag quantities, checkout, order cancellation, and sign-out at desktop and mobile widths. Real storefront interactions change the selected database; use a separate database path for manual testing when you need to preserve existing accounts and stock. Browser automation is not required by the runtime dependencies.

## Troubleshooting

| Symptom | Action |
|---|---|
| Browser says connection refused | Start the server and keep its terminal open. Check that the URL port matches `serve --port`. |
| Address already in use | Choose a free port, for example `serve --port 8002`, and browse to that port. |
| Homepage is missing or still shows the old backend | Stop the old process and restart from this checkout. Open `/`, not `/api/products`, then refresh the page. |
| `No module named flask` | Install `requirements.txt` using `.venv/bin/python -m pip`; run the app with that same interpreter. |
| `No module named shop` or `.venv/bin/python` not found | Run from the repository root and create the virtual environment if it does not exist. |
| Catalog is empty | Run `seed` against the same database used by `serve`, then refresh. |
| Sign-in fails or token expires | Check the email/password or sign in again. There are no default credentials. |
| Registration returns `409` | That email is already registered; sign in or use a different local test email. |
| Checkout reports insufficient stock | Reduce the quantity or have an admin replenish stock. A cart does not reserve inventory. |
| Guest saved items differ between browsers | Sign in to merge them into the account wishlist; only unsynchronized guest favorites are browser-local. |
| Data appears to be missing | Check `SHOP_DATABASE`, any `--database` override, and the working directory. |
| Database is locked | Finish other writes or close external database editing transactions. The app waits up to ten seconds for a lock. |
| Web fonts do not load | Check internet access to Google Fonts; the application uses fallback fonts when unavailable. |

## Security and Production Boundaries

This sample intentionally excludes real payments/refunds, tax and delivery pricing, email verification, password reset, returns, audit trails, an admin dashboard, and product image uploads. Totals are item subtotals only; placing an order does not charge a customer. Do not send payment-card details to this API.

Passwords are hashed with salted PBKDF2-SHA256, while only SHA-256 hashes of bearer tokens are stored in SQLite. Public registration cannot grant admin permissions. Customer order reads and cancellations are ownership-scoped. SQL inputs use parameters, and database constraints provide an additional integrity boundary.

Before production, add HTTPS, authentication rate limiting, managed secrets, observability and audit logging, migration tooling, backups, and payment-provider integration. Browser-readable session tokens require strong XSS defenses and a review of the authentication/storage design. Review third-party asset licenses and external font/privacy requirements before redistribution or deployment.

Use a production WSGI server rather than Flask's development server. Schema initialization only creates missing tables; it does not migrate existing ones. For multiple application instances or substantial write traffic, move to PostgreSQL and revisit concurrency control. Back up the database before schema or data changes; do not delete the database as a routine troubleshooting step.
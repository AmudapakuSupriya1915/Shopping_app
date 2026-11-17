import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from typing import Any

from shop.database import Database
from shop.errors import AuthenticationError, ConflictError, ValidationError
from shop.services import text


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt, _ = encoded.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), encoded)


class AuthService:
    def __init__(self, database: Database, session_seconds: int = 28_800):
        self.database = database
        self.session_seconds = session_seconds

    def register(self, email: str, name: str, password: str, *, role: str = "customer") -> dict[str, Any]:
        email = text(email, "email", 254).lower()
        name = text(name, "name", 100)
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValidationError("A valid email address is required")
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise ValidationError("Password must contain 12 to 128 characters")
        if role not in {"customer", "admin"}:
            raise ValidationError("Invalid role")
        encoded = hash_password(password)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "INSERT INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
                    (email, name, encoded, role),
                )
                return {"id": cursor.lastrowid, "email": email, "name": name, "role": role}
        except sqlite3.IntegrityError as error:
            raise ConflictError("Email is already registered") from error

    def login(self, email: str, password: str) -> dict[str, Any]:
        email = text(email, "email", 254).lower()
        if not isinstance(password, str) or len(password) > 128:
            raise AuthenticationError("Invalid email or password")
        with self.database.connection() as connection:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        encoded = user["password_hash"] if user else f"{'0' * 32}${'0' * 64}"
        valid = verify_password(password, encoded)
        if not valid or user is None:
            raise AuthenticationError("Invalid email or password")
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + self.session_seconds
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (self._token_hash(token), user["id"], expires_at),
            )
        return {"access_token": token, "token_type": "Bearer", "expires_at": expires_at}

    def authenticate(self, token: str) -> dict[str, Any]:
        with self.database.connection() as connection:
            user = connection.execute(
                "SELECT u.id, u.email, u.name, u.role FROM users u "
                "JOIN sessions s ON s.user_id = u.id WHERE s.token_hash = ? AND s.expires_at > ?",
                (self._token_hash(token), int(time.time())),
            ).fetchone()
        if user is None:
            raise AuthenticationError("Invalid or expired access token")
        return dict(user)

    def logout(self, token: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(token),))

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
"""Passwords, login tokens and roles (ADR-09).

Used by the API (api/auth.py) and the command line tool (tools/manage.py).

- Passwords are stored only as Argon2 hashes (argon2-cffi). Argon2 is slow on
  purpose, so guessing passwords from a stolen database takes very long.
- A login creates a random token. The browser keeps it in an HttpOnly cookie
  (JavaScript can't read it); the database stores only its SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ROLES = {
    "admin": "Admin",
    "chef": "Firmenchef",
    "mitarbeiter": "Mitarbeiter",
    "techniker": "Servicetechniker",
}
# Roles that see ALL devices and may edit them (the "Betreiber" in the use-case diagram)
MANAGEMENT = ("chef", "mitarbeiter")

MIN_PASSWORD_LENGTH = 8
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,49}$")

_hasher = PasswordHasher()
# Verified against when a username doesn't exist, so the answer takes as long as
# for a real user (otherwise the response time would reveal valid usernames).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True if ``password`` matches. Always does the (slow) work, even without a user."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    """Random session token for the cookie (256 bits)."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def check_username(username: str) -> str | None:
    """German error text, or None if the username is fine."""
    if not USERNAME_RE.match(username):
        return "Benutzername: 3-50 Zeichen, nur Kleinbuchstaben, Ziffern und . _ - @"
    return None


def check_password(password: str) -> str | None:
    """German error text, or None if the password is acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein."
    return None


def generate_password() -> str:
    """Readable start password, e.g. for a new account: 'kufa-remo-tiba-73'."""
    syllables = [c + v for c in "bdfgklmnprstvz" for v in "aeiou"]
    words = ["".join(secrets.choice(syllables) for _ in range(2)) for _ in range(3)]
    return "-".join(words) + f"-{secrets.randbelow(90) + 10}"

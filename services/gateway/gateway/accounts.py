"""Users, invites and sessions. D-012, D-013.

Three deliberate choices, each with a reason:

1. **Passwords use argon2, API keys use SHA-256.** They are opposite problems.
   A human password is low-entropy and guessable, so it needs a slow hash. An
   API key is 256 bits of CSPRNG output with no dictionary to attack, so a
   slow hash buys nothing and would add latency to every tool call.

2. **Sessions are server-side.** The cookie carries an opaque random id and
   nothing else. No user id, no role, no signature to verify, nothing a
   tampered cookie could assert. Revoking a session is a DELETE.

3. **Invite tokens are hashed at rest too.** The token is a bearer credential
   until it is consumed, so storing it in clear would let anyone with
   database read access accept an invite as that person.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Defaults from argon2-cffi, which tracks the RFC 9106 guidance.
_ph = PasswordHasher()

SESSION_COOKIE = "gw_session"
SESSION_TTL = timedelta(hours=12)
INVITE_TTL = timedelta(days=7)

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLES = (ROLE_ADMIN, ROLE_MEMBER)


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


# ---------------------------------------------------------------- passwords

def hash_password(plain: str) -> str:
    """argon2id. The salt is generated per call and embedded in the output,
    so two users who pick the same password get different stored values."""
    return _ph.hash(plain)


def verify_password(plain: str, stored: str) -> bool:
    try:
        return _ph.verify(stored, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_problem(plain: str) -> str | None:
    """Return why a password is unacceptable, or None if it is fine."""
    if len(plain) < 12:
        return "password must be at least 12 characters"
    if plain.strip() != plain:
        return "password must not start or end with whitespace"
    return None


# ---------------------------------------------------------------- tokens

def new_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex). Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def token_matches(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(token_hash(raw), stored_hash)


def expiry(ttl: timedelta) -> datetime:
    return datetime.now(timezone.utc) + ttl


def is_expired(when: datetime | None) -> bool:
    if when is None:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= when


# ---------------------------------------------------------------- origin

def origin_allowed(origin: str | None, host: str | None) -> bool:
    """CSRF defence for state-changing requests.

    A request with no Origin is allowed: non-browser clients (curl, the MCP
    clients) do not send one, and the browser attaches it to exactly the
    cross-site requests we care about. A present Origin must match the Host
    the request arrived on.
    """
    if not origin:
        return True
    if not host:
        return False
    from urllib.parse import urlparse

    netloc = urlparse(origin).netloc
    return bool(netloc) and netloc == host

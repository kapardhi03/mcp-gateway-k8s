"""API key format and hashing. D-013 option A.

Key layout:  gw_<prefix>_<secret>
  prefix  8 chars, stored in clear, indexed, used to find the row
  secret  43 chars of url-safe randomness

Only SHA-256 of the WHOLE key is stored. The raw key is shown once, at
creation, and never again.

Why SHA-256 and not argon2: the secret is 256 bits of CSPRNG output, so there
is no dictionary to attack and a slow hash buys nothing. It would, however,
cost a slow hash on every single tool call. Human passwords are the opposite
case and get argon2 (D-012).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PREFIX_LEN = 8
_PREFIX = "gw_"


def generate() -> tuple[str, str, str]:
    """Return (full_key, prefix, sha256_hex). The full key is shown once."""
    prefix = secrets.token_hex(PREFIX_LEN // 2)
    secret = secrets.token_urlsafe(32)
    full = "%s%s_%s" % (_PREFIX, prefix, secret)
    return full, prefix, hash_key(full)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def prefix_of(full_key: str) -> str | None:
    """Pull the lookup prefix out of a presented key, or None if malformed."""
    if not full_key or not full_key.startswith(_PREFIX):
        return None
    rest = full_key[len(_PREFIX):]
    head, sep, _tail = rest.partition("_")
    if not sep or len(head) != PREFIX_LEN:
        return None
    return head


def verify(presented: str, stored_hash: str) -> bool:
    """Constant-time comparison, so a wrong key leaks no timing signal."""
    return hmac.compare_digest(hash_key(presented), stored_hash)

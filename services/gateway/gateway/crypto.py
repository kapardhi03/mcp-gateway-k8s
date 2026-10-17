"""Encryption at rest for upstream credentials.

An upstream credential is a bearer token for someone else's system. It is
stored encrypted so that a Postgres backup, a stray pg_dump or a read-only
database compromise does not hand it over. The key lives in a Kubernetes
Secret and is never written to the database.

Fernet: AES-128-CBC with an HMAC-SHA256 authentication tag, from the
`cryptography` library. Authenticated, so tampering is detected rather than
silently decrypting to garbage.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(RuntimeError):
    pass


class Crypto:
    def __init__(self, key: str) -> None:
        try:
            self._f = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as exc:
            raise CryptoError(
                "ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            return ""
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            # Deliberately does not echo the token.
            raise CryptoError(
                "stored credential could not be decrypted: wrong ENCRYPTION_KEY or tampered value"
            ) from exc

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()

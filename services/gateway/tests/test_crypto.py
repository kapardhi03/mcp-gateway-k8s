"""Upstream credentials are encrypted at rest."""
from __future__ import annotations

import pytest

from gateway.crypto import Crypto, CryptoError


def test_round_trip():
    c = Crypto(Crypto.generate_key())
    assert c.decrypt(c.encrypt("ghp_secret_token")) == "ghp_secret_token"


def test_ciphertext_does_not_contain_the_plaintext():
    c = Crypto(Crypto.generate_key())
    assert "ghp_secret_token" not in c.encrypt("ghp_secret_token")


def test_wrong_key_cannot_decrypt():
    a, b = Crypto(Crypto.generate_key()), Crypto(Crypto.generate_key())
    with pytest.raises(CryptoError):
        b.decrypt(a.encrypt("secret"))


def test_tampering_is_detected():
    c = Crypto(Crypto.generate_key())
    token = c.encrypt("secret")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(CryptoError):
        c.decrypt(tampered)


def test_error_message_never_echoes_the_token():
    c = Crypto(Crypto.generate_key())
    try:
        c.decrypt("not-a-fernet-token-xyz")
    except CryptoError as e:
        assert "not-a-fernet-token-xyz" not in str(e)


def test_bad_key_is_a_clear_error():
    with pytest.raises(CryptoError) as e:
        Crypto("not-a-key")
    assert "Fernet" in str(e.value)

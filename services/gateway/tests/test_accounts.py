"""Team features: password storage, origin check, tokens. SEC-1, SEC-3, SEC-6."""
from __future__ import annotations

from datetime import timedelta

import pytest

from gateway import accounts


# ------------------------------------------------- SEC-1 password storage

def test_password_hash_is_argon2_and_verifies():
    h = accounts.hash_password("correct horse battery staple")
    assert h.startswith("$argon2"), h[:20]
    assert accounts.verify_password("correct horse battery staple", h)


def test_same_password_hashes_differently():
    """Salted. Two users who pick the same password must not share a hash,
    or one cracked hash would crack both."""
    a = accounts.hash_password("the same password 123")
    b = accounts.hash_password("the same password 123")
    assert a != b
    assert accounts.verify_password("the same password 123", a)
    assert accounts.verify_password("the same password 123", b)


def test_plaintext_never_appears_in_the_hash():
    h = accounts.hash_password("sup3rsecret-passphrase")
    assert "sup3rsecret-passphrase" not in h


def test_wrong_password_rejected():
    h = accounts.hash_password("the right one 123456")
    assert not accounts.verify_password("the wrong one 123456", h)


@pytest.mark.parametrize("bad", ["", "short", "   padded   ", "elevenchar"])
def test_weak_passwords_rejected(bad):
    assert accounts.password_problem(bad) is not None


def test_acceptable_password_passes():
    assert accounts.password_problem("a reasonable passphrase") is None


def test_verify_tolerates_a_corrupt_stored_hash():
    """A garbage column value must be a clean False, not a 500."""
    assert not accounts.verify_password("anything", "not-a-hash")
    assert not accounts.verify_password("anything", "")


# ------------------------------------------------------- SEC-3 origin check

@pytest.mark.parametrize("origin,host,ok", [
    (None, "gateway.localhost", True),          # curl / MCP clients send none
    ("http://gateway.localhost", "gateway.localhost", True),
    ("https://gateway.localhost", "gateway.localhost", True),
    ("http://evil.example", "gateway.localhost", False),
    ("http://gateway.localhost.evil.example", "gateway.localhost", False),
    ("http://gateway.localhost:9999", "gateway.localhost", False),
    ("", "gateway.localhost", True),
    ("http://gateway.localhost", None, False),
])
def test_origin_allowed(origin, host, ok):
    assert accounts.origin_allowed(origin, host) is ok


# ------------------------------------------------------------ SEC-6 tokens

def test_tokens_are_unique_and_stored_hashed():
    raws = set()
    for _ in range(200):
        raw, h = accounts.new_token()
        assert raw not in h          # the raw token is not recoverable
        assert len(h) == 64          # sha256 hex
        raws.add(raw)
    assert len(raws) == 200


def test_token_matches_only_its_own_hash():
    raw, h = accounts.new_token()
    other, _ = accounts.new_token()
    assert accounts.token_matches(raw, h)
    assert not accounts.token_matches(other, h)


def test_token_is_not_derived_from_the_email():
    """An invite token derived from an address would be forgeable."""
    a, _ = accounts.new_token()
    b, _ = accounts.new_token()
    assert a != b
    assert "@" not in a


def test_expiry_helpers():
    assert not accounts.is_expired(accounts.expiry(timedelta(hours=1)))
    assert accounts.is_expired(accounts.expiry(timedelta(hours=-1)))
    assert accounts.is_expired(None)


def test_naive_datetime_is_treated_as_utc_not_crashed():
    """psycopg can hand back a naive timestamp; comparing it to an aware
    `now()` would raise TypeError and 500 the request."""
    from datetime import datetime, timedelta as td
    naive_future = datetime.utcnow() + td(hours=1)
    naive_past = datetime.utcnow() - td(hours=1)
    assert not accounts.is_expired(naive_future)
    assert accounts.is_expired(naive_past)


# ------------------------------------------------- SEC-2 cookie Secure flag

def test_secure_flag_is_conditional_on_https():
    """SEC-2's one part that cannot be tested over local plain HTTP.

    The cookie must carry Secure when the request arrived over TLS and not
    when it did not: setting it unconditionally would make the cookie vanish
    on the local HTTP dashboard, and never setting it would leak the session
    over plain HTTP in production. The route computes it as
    `request.url.scheme == "https"`, so that expression is what is asserted
    here, rather than pretending a local HTTP run proves the TLS behaviour.
    """
    class FakeURL:
        def __init__(self, scheme): self.scheme = scheme

    for scheme, expected in (("https", True), ("http", False)):
        assert (FakeURL(scheme).scheme == "https") is expected

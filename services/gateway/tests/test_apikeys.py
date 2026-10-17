"""API key format and hashing. D-013 option A."""
from __future__ import annotations

import pytest

from gateway import apikeys


def test_generate_round_trips():
    full, prefix, h = apikeys.generate()
    assert full.startswith("gw_")
    assert apikeys.prefix_of(full) == prefix
    assert apikeys.verify(full, h)


def test_wrong_key_rejected():
    full, _p, h = apikeys.generate()
    other, _p2, _h2 = apikeys.generate()
    assert not apikeys.verify(other, h)


def test_raw_key_is_not_recoverable_from_the_hash():
    full, _p, h = apikeys.generate()
    assert full not in h
    assert len(h) == 64  # sha256 hex


def test_keys_are_unique():
    seen = {apikeys.generate()[0] for _ in range(200)}
    assert len(seen) == 200


@pytest.mark.parametrize("bad", ["", "nope", "gw_short_x", "gw_", "gw_abcdefgh", "abcdefgh_x"])
def test_malformed_keys_have_no_prefix(bad):
    assert apikeys.prefix_of(bad) is None

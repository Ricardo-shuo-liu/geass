from __future__ import annotations

import pytest

import geass.server.pairing as pairing_module
from geass.server.pairing import (
    MAX_TTL,
    MIN_TTL,
    PairingError,
    PairingManager,
    normalize_ttl,
)


def test_create_and_redeem_code():
    manager = PairingManager()
    entry = manager.create()

    assert manager.pending_count() == 1
    assert manager.redeem(entry.code, "server-token") == "server-token"
    assert manager.pending_count() == 0


def test_redeem_rejects_wrong_code():
    manager = PairingManager()
    manager.create()

    with pytest.raises(PairingError) as info:
        manager.redeem("nope", "server-token")

    assert info.value.kind == "invalid"


def test_redeem_is_single_use():
    manager = PairingManager()
    entry = manager.create()
    manager.redeem(entry.code, "server-token")

    with pytest.raises(PairingError) as info:
        manager.redeem(entry.code, "server-token")

    assert info.value.kind == "used"


def test_expired_code_is_rejected(monkeypatch):
    manager = PairingManager(ttl=30)
    entry = manager.create()
    monkeypatch.setattr(pairing_module.time, "time", lambda: entry.expires_at + 1)

    with pytest.raises(PairingError) as info:
        manager.redeem(entry.code, "server-token")

    assert info.value.kind == "expired"
    assert manager.pending_count() == 0


def test_rate_limit_blocks_repeated_failures():
    manager = PairingManager()
    manager.create()

    for _ in range(10):
        with pytest.raises(PairingError) as info:
            manager.redeem("bad-code", "server-token", client="1.2.3.4")
        assert info.value.kind == "invalid"

    with pytest.raises(PairingError) as info:
        manager.redeem("bad-code", "server-token", client="1.2.3.4")
    assert info.value.kind == "rate_limited"


def test_rate_limit_window_recovers(monkeypatch):
    manager = PairingManager()
    manager.create()
    now = pairing_module.time.time()
    for _ in range(10):
        with pytest.raises(PairingError):
            manager.redeem("bad-code", "server-token", client="1.2.3.4")

    monkeypatch.setattr(
        pairing_module.time,
        "time",
        lambda: now + pairing_module.RATE_LIMIT_WINDOW + 1,
    )
    with pytest.raises(PairingError) as info:
        manager.redeem("bad-code", "server-token", client="1.2.3.4")
    assert info.value.kind == "invalid"


def test_normalize_ttl_bounds():
    assert normalize_ttl(1) == MIN_TTL
    assert normalize_ttl(10_000) == MAX_TTL
    assert normalize_ttl(120) == 120

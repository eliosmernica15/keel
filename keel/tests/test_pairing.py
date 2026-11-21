"""C1.12 — LAN/headless client pairing allowlist and revocation."""

from __future__ import annotations

import pytest

from keel.pairing import PairingError, PairingStore


def test_pair_is_explicit_and_listed(tmp_path):
    store = PairingStore(str(tmp_path))
    assert store.list_clients() == []
    client = store.pair("phone", scope="lan")
    assert client["revoked"] is False and client["scope"] == "lan"
    assert store.is_paired(client["id"]) is True
    assert len(store.list_clients()) == 1


def test_revocation_removes_access(tmp_path):
    store = PairingStore(str(tmp_path))
    client = store.pair("headless")
    assert store.revoke(client["id"]) is True
    assert store.is_paired(client["id"]) is False
    assert store.revoke("missing") is False


def test_invalid_scope_rejected(tmp_path):
    store = PairingStore(str(tmp_path))
    with pytest.raises(PairingError, match="unknown scope"):
        store.pair("x", scope="cloud")

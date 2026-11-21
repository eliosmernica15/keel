"""No capability may report fake success: independent validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from keel import capability_registry  # noqa: F401
from keel.capabilities import invoke
from keel.channel_ops import outbox_path


def test_channel_deliver_really_writes_outbox(tmp_path):
    result = invoke("cowork.channel.deliver", {
        "chain": ["outbox"], "message": "important update",
        "destination": "team"},
        context={"state_root": str(tmp_path), "cwd": str(tmp_path)})
    assert result["ok"] is True
    assert result["result"]["delivered"] is True
    path = outbox_path(str(tmp_path))
    assert path.is_file()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert records[0]["message"] == "important update"
    assert records[0]["channel"] == "outbox"
    assert records[0]["status"] == "queued_local"


def test_channel_deliver_empty_chain_fails(tmp_path):
    with pytest.raises(Exception) as exc:
        invoke("cowork.channel.deliver",
               {"chain": [], "message": "x"},
               context={"state_root": str(tmp_path)})
    assert "chain" in str(exc.value)


def test_ci_run_mock_is_explicit_and_labelled():
    mock = invoke("external.ci.run", {"prompt": "hi", "mock": True},
                  context={})
    assert mock["result"]["mock"] is True
    assert "not a real run" in mock["result"]["note"]
    # Default (no mock flag) must not claim mock success; it runs the real CLI
    # which returns a real envelope (may fail without a provider, that is fine).
    real = invoke("external.ci.run", {"prompt": "hi"}, context={})
    assert real["result"]["mock"] is False

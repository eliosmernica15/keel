"""A4.7/A5.2 — secret provider choices and channel install sources."""

from __future__ import annotations

import pytest

from keel.provider_sources import ChannelInstalls, secret_provider


def test_secret_provider_descriptors():
    assert secret_provider("keychain")["kind"] == "system"
    assert secret_provider("nope")["kind"] == "unknown"


def test_channel_install_dormant(tmp_path):
    installs = ChannelInstalls(tmp_path)
    entry = installs.add("dev-plugin", "git+https://example.test/p.git")
    assert entry["approved"] is False
    installs.add("local", "file:///tmp/plugin")
    assert len(installs.list()) == 2
    with pytest.raises(ValueError):
        installs.add("bad", "relative/path")

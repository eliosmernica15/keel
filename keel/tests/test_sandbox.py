"""B3.1/B3.2/B3.10 — sandbox descriptors and app lock."""

from __future__ import annotations

import pytest

from keel.sandbox import AppLock, container_sandbox, wasm_sandbox


def test_wasm_descriptor_has_no_host_io():
    spec = wasm_sandbox("code")
    assert spec["network"] is False and spec["filesystem"] is False


def test_container_limits_validated():
    spec = container_sandbox("python:3.11", cpus=2, memory_mb=1024)
    assert spec["cpus"] == 2 and spec["optional"] is True
    with pytest.raises(ValueError):
        container_sandbox("x", memory_mb=0)


def test_app_lock():
    lock = AppLock(idle_s=10)
    lock.set_passphrase()
    lock.touch(now=0)
    assert lock.maybe_lock(now=5) is False
    assert lock.maybe_lock(now=11) is True
    lock.touch(now=12)
    assert lock.locked is False

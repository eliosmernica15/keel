"""A5.1 — gateway process with status/start/stop."""

from __future__ import annotations

import time

from keel.cli.main import main
from keel.gateway import Gateway


def test_fresh_gateway_is_stopped():
    status = Gateway(interval=0.01).status()
    assert status["running"] is False
    assert status["ticks"] == 0
    assert status["uptime_s"] == 0


def test_gateway_start_stop_and_ticks():
    calls = []
    gateway = Gateway(work=lambda: calls.append(1), interval=0.01)
    assert gateway.start() is True
    assert gateway.start() is False  # idempotent
    time.sleep(0.08)
    status = gateway.status()
    assert status["running"] is True
    assert status["ticks"] >= 1
    assert len(calls) >= 1
    assert gateway.stop(timeout=2) is True
    assert gateway.status()["running"] is False
    assert gateway.stop() is False


def test_gateway_survives_failing_work():
    def fail():
        raise RuntimeError("one bad tick")

    gateway = Gateway(work=fail, interval=0.01)
    assert gateway.start() is True
    time.sleep(0.05)
    assert gateway.status()["running"] is True
    assert gateway.stop(timeout=2) is True


def test_cli_gateway_help():
    assert main(["gateway", "--help"]) == 0
    assert main(["gateway", "bogus"]) == 1

"""B3.9 global kill switch + A3.6 revoke-all-client-tokens."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import keel.webapp as webapp
from keel.fleet import turn_core

ROOT = Path(__file__).resolve().parents[1]


def test_cancel_all_turns_signals_every_active_turn():
    first = threading.Event()
    second = threading.Event()
    with turn_core._ACTIVE_LOCK:
        saved = dict(turn_core._ACTIVE_CANCEL)
        turn_core._ACTIVE_CANCEL.clear()
        turn_core._ACTIVE_CANCEL["a"] = first
        turn_core._ACTIVE_CANCEL["b"] = second
    try:
        assert turn_core.cancel_all_turns() == 2
        assert first.is_set() and second.is_set()
    finally:
        with turn_core._ACTIVE_LOCK:
            turn_core._ACTIVE_CANCEL.clear()
            turn_core._ACTIVE_CANCEL.update(saved)


def test_cancel_all_turns_with_no_active_turns():
    with turn_core._ACTIVE_LOCK:
        saved = dict(turn_core._ACTIVE_CANCEL)
        turn_core._ACTIVE_CANCEL.clear()
    try:
        assert turn_core.cancel_all_turns() == 0
    finally:
        with turn_core._ACTIVE_LOCK:
            turn_core._ACTIVE_CANCEL.update(saved)


def test_rotate_token_revokes_old_token():
    old = webapp.token()
    new = webapp.rotate_token()
    assert new != old
    try:
        assert webapp.token() == new
        assert webapp.token() != old
    finally:
        # restore the suite token so other tests stay valid
        import builtins
        webapp._TOKEN = old


def test_ui_has_global_stop_button():
    html = (ROOT / "site" / "app.html").read_text(encoding="utf-8")
    assert 'id="btn-kill"' in html
    js = (ROOT / "site" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "/api/kill-switch" in js
    assert "btn-kill" in js


def test_app_js_syntax():
    result = subprocess.run(["node", "--check", str(ROOT / "site" / "ui" / "app.js")],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

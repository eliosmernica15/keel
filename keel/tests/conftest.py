"""Shared fixtures for the v2 runtime acceptance tests.

The deterministic fake transport is injected at the network edge —
see `make_fake_adapter`. The real adapter, Session, tool registry and
fleet.db all run unmodified in every test.
"""

import os

import pytest

os.environ.setdefault("KEEL_TOKEN", "tracetoken12345")
os.environ["KEEL_TOKEN"] = "tracetoken12345"

import keel.webapp as webapp  # noqa: E402

TOKEN = os.environ["KEEL_TOKEN"]


@pytest.fixture()
def compat_store(tmp_path):
    """Isolated FleetStore on a tmp DB, restored afterwards."""
    from keel.fleet import routes as fleet_routes
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    store = fleet_routes.store()
    store._test_db_path = tmp_path / "fleet.db"
    yield store
    fleet_routes._store = old


@pytest.fixture()
def compat_server():
    """HTTP bridge for the v2 surface."""
    import threading

    srv = webapp.make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    t.join(timeout=5)

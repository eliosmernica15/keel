"""M2 catalog/schema/resolver must be reachable through the real bridge."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import keel.webapp as webapp

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server():
    srv = webapp.make_server(0)
    import threading

    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _get(server, path, token=webapp.token()):
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    sep = "&" if "?" in path else "?"
    if token:
        url += f"{sep}t={token}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_offline_catalog_endpoint(server):
    status, body = _get(server, "/api/model-catalog")
    assert status == 200, body[:200]
    doc = json.loads(body)
    assert doc["source"]["license"] == "MIT"
    assert doc["provider_count"] >= 75
    assert doc["model_count"] > 0
    assert any(p["id"] == "google" for p in doc["providers"])


def test_provider_models_endpoint(server):
    status, body = _get(server, "/api/model-catalog/google")
    assert status == 200, body[:200]
    doc = json.loads(body)
    assert any("gemini" in model for model in doc["models"])


def test_schema_endpoint(server):
    status, body = _get(server, "/api/settings/schema")
    assert status == 200, body[:200]
    doc = json.loads(body)
    assert "providerConfig" in doc["properties"]


def test_model_resolution_endpoint(server):
    ref = urllib.parse.quote("google/gemini-2.0-flash")
    status, body = _get(server, f"/api/models/resolve?ref={ref}")
    assert status == 200, body[:200]
    doc = json.loads(body)
    assert doc["qualified"] == "google/gemini-2.0-flash"

    catalog_only = urllib.parse.quote("openai/gpt-example")
    status, body = _get(server, f"/api/models/resolve?ref={catalog_only}")
    assert status == 400
    assert "offline catalog" in body


def test_m2_endpoints_require_token(server):
    for path in ("/api/model-catalog", "/api/settings/schema",
                 "/api/models/resolve?ref=google/gemini"):
        status, _ = _get(server, path, token=None)
        assert status == 403


def test_desktop_ui_uses_local_catalog():
    source = (ROOT / "site" / "ui" / "app.js").read_text(encoding="utf-8")
    assert "/api/model-catalog/" in source
    assert "offline catalog" in source

"""Desktop management UI integration tests.

These tests exercise the real bridge served by :mod:`keel.webapp` with the
same authentication the desktop shell uses: the token query parameter sets an
HttpOnly cookie, and every management request is then authorized by that
cookie (or by the X-Keel-Token header used by the app shell).

They fail if the app shell does not load the management script, if a required
element is missing, or if a management endpoint is not reachable with the
desktop credential.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import keel.webapp as webapp

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "desktop" / "ui"
SITE_UI_DIR = ROOT / "site"


def _run_server():
    srv = webapp.make_server(0)
    import threading

    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread


@pytest.fixture
def server():
    srv, thread = _run_server()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


@pytest.fixture
def site_server(monkeypatch):
    """The packaged Electron shell ships ``site/`` as its UI root."""
    monkeypatch.setattr(webapp, "UI_DIR", SITE_UI_DIR)
    srv, thread = _run_server()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _base(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def _get(server, path: str, token: str | None = None, cookie: str | None = None):
    url = _base(server) + path
    sep = "&" if "?" in path else "?"
    if token:
        url += f"{sep}t={token}"
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


def _cookie_for(server) -> str:
    status, _, headers = _get(server, "/", token=webapp.token())
    assert status == 200
    raw = next((value for key, value in headers.items()
                if key.lower() == "set-cookie"), "")
    assert "keel_token=" in raw
    return raw.split(";")[0]


def _get_json(server, path: str, cookie: str):
    status, body, _ = _get(server, path, cookie=cookie)
    assert status == 200, f"{path} -> {status}: {body[:400]}"
    return json.loads(body)


def _post_json(server, path: str, body: dict, cookie: str):
    request = urllib.request.Request(
        _base(server) + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Cookie": cookie, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_desktop_shell_loads_management_script_and_elements(server):
    status, html, _ = _get(server, "/", token=webapp.token())
    assert status == 200
    assert 'src="/ui/management.js"' in html

    # Every element the management script reaches for must exist in the shell.
    required_ids = [
        "settings-panel",
        "settings-body",
        "pane-skills",
        "pane-commands",
        "pane-workflows",
        "pane-connectors",
        "skills-list",
        "commands-list",
        "workflows-list",
        "mcp-list",
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html, f"missing element id={element_id}"

    # Visible navigation for all four management screens.
    for section in ("skills", "commands", "workflows", "connectors"):
        assert f'data-section="{section}"' in html, f"missing nav for {section}"


def test_packaged_shell_loads_the_same_management_screens(site_server):
    """The Electron build ships site/ as resources/site, so it is a real shell."""
    status, html, _ = _get(site_server, "/", token=webapp.token())
    assert status == 200
    assert 'src="/ui/management.js"' in html
    for element_id in ("pane-skills", "pane-commands", "pane-workflows",
                       "pane-connectors", "skills-list", "commands-list",
                       "workflows-list", "mcp-list"):
        assert f'id="{element_id}"' in html
    for section in ("skills", "commands", "workflows", "connectors"):
        assert f'data-section="{section}"' in html
    status, body, _ = _get(site_server, "/ui/management.js",
                           token=webapp.token())
    assert status == 200
    assert "skills/manage" in body


def test_management_script_is_served_from_the_desktop_ui(server):
    status, body, headers = _get(server, "/ui/management.js",
                                 token=webapp.token())
    assert status == 200, body[:400]
    assert "javascript" in headers.get("Content-Type", "").lower()
    for endpoint in (
        "/api/fleet/skills/manage",
        "/api/fleet/commands",
        "/api/fleet/workflows",
        "/api/fleet/mcp/servers",
        "/api/workdir",
    ):
        assert endpoint in body, f"management.js does not call {endpoint}"
    assert "X-Keel-Token" in body
    assert "Loading..." in body
    assert "Could not load:" in body
    assert "No skills found" in body


def test_management_endpoints_accept_the_desktop_cookie(server):
    cookie = _cookie_for(server)

    workdir = _get_json(server, "/api/workdir", cookie)
    assert "path" in workdir

    skills = _get_json(server, "/api/fleet/skills/manage", cookie)
    assert isinstance(skills.get("skills"), list)
    assert skills["skills"], "expected bundled skills to be discoverable"

    commands = _get_json(server, "/api/fleet/commands?project_root=", cookie)
    assert isinstance(commands.get("commands"), list)
    assert any(c.get("name") == "help" for c in commands["commands"])

    workflows = _get_json(server, "/api/fleet/workflows?project_root=", cookie)
    assert isinstance(workflows.get("workflows"), list)

    servers = _get_json(server, "/api/fleet/mcp/servers", cookie)
    assert isinstance(servers.get("servers"), list)


def test_management_endpoints_return_real_project_data(server, tmp_path):
    command_dir = tmp_path / ".keel" / "commands"
    command_dir.mkdir(parents=True)
    (command_dir / "smoke.md").write_text(
        "---\nname: smoke\ndescription: Desktop smoke command\n"
        "argument-hint: <text>\n---\nSay $ARGUMENTS\n",
        encoding="utf-8",
    )
    workflow_dir = tmp_path / ".keel" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "desktop-smoke.json").write_text(json.dumps({
        "name": "desktop-smoke",
        "description": "Desktop smoke workflow",
        "steps": [{"kind": "command", "command": "help"}],
    }), encoding="utf-8")

    cookie = _cookie_for(server)
    root = urllib.parse.quote(str(tmp_path))

    commands = _get_json(server,
                         f"/api/fleet/commands?project_root={root}", cookie)
    names = {c["name"] for c in commands["commands"]}
    assert "smoke" in names

    workflows = _get_json(server,
                          f"/api/fleet/workflows?project_root={root}", cookie)
    assert "desktop-smoke" in {w["name"] for w in workflows["workflows"]}


@pytest.mark.parametrize("path", [
    "/api/fleet/skills/manage",
    "/api/fleet/commands?project_root=",
    "/api/fleet/workflows?project_root=",
    "/api/fleet/mcp/servers",
])
def test_management_endpoints_refuse_missing_credentials(server, path):
    status, body, _ = _get(server, path)
    assert status == 403, body[:400]


def test_workflow_execution_enforces_tier1_permissions(server, tmp_path):
    """A non-interactive UI workflow cannot bypass the permission gate."""
    workflow_dir = tmp_path / ".keel" / "workflows"
    workflow_dir.mkdir(parents=True)
    marker = tmp_path / "marker.txt"
    marker.write_text("hello", encoding="utf-8")
    (workflow_dir / "shell.json").write_text(json.dumps({
        "name": "shell-step",
        "steps": [{"kind": "shell", "command": "python -c 'print(1)'"}],
    }), encoding="utf-8")
    (workflow_dir / "read.json").write_text(json.dumps({
        "name": "read-step",
        "steps": [{"kind": "tool", "name": "read_file",
                   "input": {"path": str(marker)}}],
    }), encoding="utf-8")

    cookie = _cookie_for(server)
    status, body = _post_json(server, "/api/fleet/workflows/execute",
                              {"name": "shell-step", "project_root": str(tmp_path)},
                              cookie)
    assert status == 200, body[:400]
    result = json.loads(body)
    assert result["ok"] is False
    assert result["results"][0]["ok"] is False
    assert "consent" in result["results"][0]["error"].lower()

    status, body = _post_json(server, "/api/fleet/workflows/execute",
                              {"name": "read-step", "project_root": str(tmp_path)},
                              cookie)
    assert status == 200, body[:400]
    result = json.loads(body)
    assert result["ok"] is True, result
    assert "hello" in json.dumps(result["results"][0])


def test_desktop_and_site_management_scripts_are_identical():
    desktop = (UI_DIR / "management.js").read_bytes()
    site = (SITE_UI_DIR / "ui" / "management.js").read_bytes()
    assert desktop == site, (
        "desktop/ui/management.js and site/ui/management.js drifted; "
        "the Electron shell serves one or the other depending on layout")

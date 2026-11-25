"""Round-2 release-gate verification: filesystem boundaries.

Path containment (including symlink escape), upload name sanitisation, the
directory-picker payload shape and Tier-2 destructive-action safeguards.
"""

from __future__ import annotations

import os
from http import HTTPStatus

import pytest

from keel import safety, webapp
from keel.fleet import routes as fleet_routes


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "inside.txt").write_text("inside", encoding="utf-8")
    monkeypatch.setattr(webapp, "_WORKDIR", str(ws))
    return ws


@pytest.mark.parametrize("raw,expected", [
    ("../../evil.txt", "evil.txt"),
    ("..\\..\\evil.txt", "evil.txt"),
    ("C:\\Windows\\System32\\evil.txt", "evil.txt"),
    ("/etc/passwd", "passwd"),
    ("...hidden", "hidden"),
    ("", "upload"),
])
def test_upload_name_is_always_a_safe_basename(raw, expected):
    assert webapp._safe_upload_name(raw) == expected


def test_workspace_read_path_containment(workspace, tmp_path):
    assert webapp._safe_workspace_path("inside.txt") == workspace / "inside.txt"
    assert webapp._safe_workspace_path("../outside.txt") is None
    assert webapp._resolve_workspace_path("../outside.txt") is None
    assert webapp._safe_workspace_path("missing.txt") is None
    assert webapp._resolve_workspace_path("new-dir") == workspace / "new-dir"


def test_symlink_escape_is_refused(workspace, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret outside the workspace", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks require elevated privileges on this host")
    assert webapp._safe_workspace_path("link.txt") is None
    assert webapp._resolve_workspace_path("link.txt") is None


def test_fs_list_rejects_bad_paths():
    status, body = webapp._fs_list_payload("\x00")
    assert status == HTTPStatus.BAD_REQUEST
    assert body.get("error") == "bad path"
    status, body = webapp._fs_list_payload("")
    assert status == HTTPStatus.OK and "dirs" in body


def test_fs_list_returns_directory_names_only(workspace):
    (workspace / "subdir").mkdir()
    (workspace / "private.txt").write_text("do not return", encoding="utf-8")
    status, body = webapp._fs_list_payload(str(workspace))
    assert status == HTTPStatus.OK
    assert [d["name"] for d in body["dirs"]] == ["subdir"]
    assert "do not return" not in str(body)


@pytest.fixture()
def store(tmp_path):
    old = fleet_routes._store
    fleet_routes.reset_store_for_tests(tmp_path / "fleet.db")
    yield fleet_routes.store()
    fleet_routes._store = old


def test_project_file_helpers_refuse_traversal(store, tmp_path):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    proj = store.create_project(path=str(proj_dir), name="proj")
    (proj_dir / "ok.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    assert store.read_project_file(proj["id"], "ok.txt")["content"] == "ok"
    for escape in ("../outside.txt", "..\\outside.txt",
                   "subdir/../../outside.txt"):
        with pytest.raises(ValueError, match="escapes"):
            store.read_project_file(proj["id"], escape)
        with pytest.raises(ValueError, match="escapes"):
            store.write_project_file(proj["id"], escape, "pwned")
    assert (tmp_path / "outside.txt").read_text(encoding="utf-8") == "outside"


def test_project_symlink_escape_is_refused(store, tmp_path):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    proj = store.create_project(path=str(proj_dir), name="proj")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside secret", encoding="utf-8")
    link = proj_dir / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks require elevated privileges on this host")
    with pytest.raises(ValueError, match="escapes"):
        store.read_project_file(proj["id"], "link.txt")
    with pytest.raises(ValueError, match="escapes"):
        store.write_project_file(proj["id"], "link.txt", "overwritten")
    assert (tmp_path / "outside.txt").read_text(encoding="utf-8") == "outside secret"


@pytest.mark.parametrize("command", [
    "rm -rf /",
    "rm -rf ~",
    "Remove-Item -Recurse -Force C:\\",
    "format C:",
    "mkfs.ext4 /dev/sda",
])
def test_tier2_refuses_catastrophic_commands(command):
    check = safety.tier2_check("run_shell", {"command": command,
                                            "shell": "posix"})
    assert check.allowed is False


@pytest.mark.parametrize("path", [
    "~/.ssh/id_rsa", ".env", "secrets.pem", "C:\\Users\\me\\.aws\\credentials",
])
def test_tier2_refuses_secret_bearing_paths(path):
    assert safety.tier2_check("read_file", {"path": path}).allowed is False
    assert safety.tier2_check("write_file", {"path": path}).allowed is False


def test_tier2_refuses_unparseable_command():
    check = safety.tier2_check("run_shell", {"command": "rm a && $(evil)",
                                            "shell": "posix"})
    assert check.allowed is False

"""Shared helpers for the MCP connector routes.

Reads and writes the user's ~/.keel/settings.json `mcpServers` object.
The file is the MCP config source of truth; this module never fabricates
values — it writes exactly what the user/requested — and never stores
secrets it didn't need to (github auth is delegated to `gh auth token`,
which the user did in their browser).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..redaction import redact_text
from ..settings import default_state_root, resolve

_GITHUB_CMD = (
    "@echo off\n"
    "for /f \"usebackq delims=\" %%t in (`gh auth token`) "
    "do set GITHUB_PERSONAL_ACCESS_TOKEN=%%t\n"
    "npx -y @modelcontextprotocol/server-github\n"
)

_PRESETS: dict[str, dict[str, Any]] = {
    "github": {
        "name": "github",
        "label": "GitHub",
        "desc": "Repositories, issues, PRs — auth via `gh auth login` (no token on disk)",
        "command_hint": "cmd /c npx -y @modelcontextprotocol/server-github",
    },
    "filesystem": {
        "name": "filesystem",
        "label": "Filesystem",
        "desc": "Read/write files in an allowed folder tree",
        "command_hint": "npx -y @modelcontextprotocol/server-filesystem <path>",
    },
    "memory": {
        "name": "memory",
        "label": "Memory",
        "desc": "Knowledge graph the agent can read and write across turns",
        "command_hint": "npx -y @modelcontextprotocol/server-memory",
    },
    "sequential-thinking": {
        "name": "sequential-thinking",
        "label": "Sequential thinking",
        "desc": "Dynamic, self-correcting reasoning scratchpad",
        "command_hint": "npx -y @modelcontextprotocol/server-sequential-thinking",
    },
}


def state_root() -> Path:
    return default_state_root()


def settings_path() -> Path:
    return state_root() / "settings.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    try:
        # utf-8-sig tolerates the BOM PowerShell likes to insert
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def atomic_dump(data: dict[str, Any]) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _github_wrapper() -> str:
    wrap_dir = state_root() / "mcp"
    wrap_dir.mkdir(parents=True, exist_ok=True)
    wrap = wrap_dir / "github-mcp.cmd"
    wrap.write_text(_GITHUB_CMD, encoding="utf-8")
    return str(wrap)


def _npx() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def _node_bin() -> str:
    # global installs land in the npm global prefix; resolve once
    try:
        import subprocess
        out = subprocess.run(["npm", "root", "-g"], capture_output=True,
                             text=True, timeout=15)
        root = (out.stdout or "").strip()
        if root:
            return os.path.join(root, "@modelcontextprotocol")
    except Exception:
        pass
    # deterministic guess for npm's standard global prefix on Windows
    return os.path.expandvars(r"%APPDATA%\npm\node_modules\@modelcontextprotocol")


def _dist_script(package_name: str) -> str:
    return os.path.join(_node_bin(), package_name, "dist", "index.js")


def preset_spec(preset: str, args: list[str] | None, env: dict[str, str] | None) -> dict[str, Any]:
    args = args or []
    env = env or {}
    if preset == "github":
        return {"command": "cmd",
                "args": ["/c", _github_wrapper()],
                "env": {}}
    if preset == "filesystem":
        target = str(Path(args[0]).expanduser() if args else Path.cwd())
        return {"command": "node",
                "args": [_dist_script("server-filesystem"), target],
                "env": {}}
    if preset == "memory":
        return {"command": "node",
                "args": [_dist_script("server-memory")],
                "env": {}}
    if preset == "sequential-thinking":
        return {"command": "node",
                "args": [_dist_script("server-sequential-thinking")],
                "env": {}}
    if preset == "puppeteer":
        # large download, only on demand
        return {"command": _npx(),
                "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
                "env": {}}
    raise ValueError(f"unknown preset {preset!r}")


def list_configured() -> dict[str, Any]:
    """Returns {'connectors': [...], 'presets': [...]} for the UI."""
    servers: dict[str, Any] = {}
    error: str | None = None
    try:
        resolved = resolve(state_root=state_root(), cwd=Path.cwd())
        servers = resolved.value.get("mcpServers", {}) or {}
        if not isinstance(servers, dict):
            servers = {}
    except Exception as exc:  # settings resolve failed — show empty + reason
        servers = {}
        error = f"settings resolve failed: {exc}"

    connectors = []
    for name, spec in sorted(servers.items()):
        if not isinstance(spec, dict):
            continue
        args = spec.get("args")
        command = str(spec.get("command", ""))
        connectors.append({
            "name": str(name),
            "command": redact_text(command)[0][:200],
            "arg_count": len(args) if isinstance(args, list) else 0,
            "env_keys": sorted((spec.get("env") or {}).keys())
            if isinstance(spec.get("env"), dict) else [],
        })
    presets = [{"name": p["name"], "label": p["label"],
                "description": p["desc"], "command": p["command_hint"]}
               for p in _PRESETS.values()]
    out: dict[str, Any] = {"connectors": connectors, "presets": presets}
    if error:
        out["error"] = error
    return out


def add_connector(name: str, command: str, args: list[str],
                  env: dict[str, str] | None) -> dict[str, Any]:
    name = (name or "").strip()
    command = (command or "").strip()
    if not name or not command:
        raise ValueError("name and command are required")
    data = load_settings()
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    spec: dict[str, Any] = {"command": command, "args": list(args or [])}
    if env:
        spec["env"] = {str(k): str(v) for k, v in env.items()}
    servers[name] = spec
    data["mcpServers"] = servers
    atomic_dump(data)
    return list_configured()


def remove_connector(name: str) -> dict[str, Any]:
    data = load_settings()
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        servers.pop(name, None)
        data["mcpServers"] = servers
        atomic_dump(data)
    return list_configured()

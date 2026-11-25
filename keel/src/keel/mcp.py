"""keel.mcp — minimal, honest MCP client (stdio transport only).

Scope, deliberately:
- stdio servers only (the reference's other three transports unbuilt);
- project-scope servers are INERT UNTIL APPROVED (approval is stored
  user-scope as a command-line-shape hash; see approvals());
- tool names are mapped to mcp__<server>__<tool>, non-[A-Za-z0-9_-] -> _;
- output capped at MCP_OUTPUT_CAP bytes;
- shutdown is best-effort (shutdown -> exit -> kill), never raises into the
  session.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import __version__

MCP_OUTPUT_CAP = 100_000  # bytes of tool output kept for the model


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    scope: str = "user"          # user | project (project is inert until approved)
    transport: str = "stdio"     # stdio | http
    url: str = ""
    headers: dict[str, str] | None = None


def approval_key(config: McpServerConfig) -> str:
    """Stable identity of what the user approved: name + command shape."""
    basis = json.dumps({"name": config.name,
                        "command": config.command,
                        "args": list(config.args)},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def approvals_path() -> Path:
    return Path(os.path.expanduser("~")) / ".keel" / "mcp-approvals.json"


def approvals() -> dict[str, str]:
    path = approvals_path()
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def approve(config: McpServerConfig) -> str:
    path = approvals_path()
    doc = approvals()
    key = approval_key(config)
    doc[config.name] = {"key": key, "command": config.command,
                        "args": list(config.args)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return key


def revoke(name: str) -> bool:
    doc = approvals()
    if name not in doc:
        return False
    doc.pop(name)
    approvals_path().write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return True


def is_approved(config: McpServerConfig) -> bool:
    doc = approvals()
    entry = doc.get(config.name)
    return isinstance(entry, dict) and entry.get("key") == approval_key(config)


def parse_servers(raw: Any) -> list[McpServerConfig]:
    """Parse the settings `mcpServers` object; tolerate junk."""
    out: list[McpServerConfig] = []
    if not isinstance(raw, dict):
        return out
    for name, spec_raw in raw.items():
        if not isinstance(spec_raw, dict):
            continue
        transport = str(spec_raw.get("transport", "stdio")).lower()
        scope = "user" if spec_raw.get("scope") in (None, "user") else "project"
        headers = spec_raw.get("headers")
        if headers is not None and not isinstance(headers, dict):
            headers = None
        if transport == "http":
            url = spec_raw.get("url")
            if not url or not isinstance(url, str):
                continue
            out.append(McpServerConfig(
                name=str(name), transport="http", url=url,
                headers={str(k): str(v) for k, v in (headers or {}).items()},
                scope=scope))
            continue
        command = spec_raw.get("command")
        if not command or not isinstance(command, str):
            continue
        args = spec_raw.get("args", [])
        if not isinstance(args, list):
            continue
        env = spec_raw.get("env")
        if env is not None and not isinstance(env, dict):
            env = None
        out.append(McpServerConfig(
            name=str(name), command=command,
            args=tuple(str(a) for a in args),
            env={str(k): str(v) for k, v in (env or {}).items()},
            scope=scope, transport="stdio"))
    return out


def tool_name_for(server: str, tool: str) -> str:
    def clean(text: str) -> str:
        return "".join(ch if (ch.isalnum() or ch in "_-") else "_"
                       for ch in text)
    return f"mcp__{clean(server)}__{clean(tool)}"


class McpError(Exception):
    pass


class McpServer:
    """One stdio MCP server. Lazy start; best-effort shutdown."""

    def __init__(self, config: McpServerConfig, *,
                 timeout: float = 30.0):
        self.config = config
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self.tools: list[dict] = []
        self.capabilities: dict = {}
        self._started = False

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        self._proc = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **(self.config.env or {})},
            text=True, encoding="utf-8", errors="replace",
            bufsize=1)
        try:
            init_result = self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "keel", "version": __version__},
            })
            self.capabilities = dict(init_result.get("capabilities") or {})
            self._notify("notifications/initialized", {})
            result = self._request("tools/list", {})
            self.tools = list(result.get("tools", []))
            self._started = True
        except Exception:
            self._kill()
            raise

    def call_tool(self, tool: str, arguments: dict) -> tuple[bool, str]:
        """Returns (ok, text). Text capped at MCP_OUTPUT_CAP bytes."""
        if not self._started:
            self.start()
        assert self._proc is not None
        try:
            result = self._request("tools/call",
                                   {"name": tool, "arguments": arguments})
        except McpError as exc:
            return False, f"mcp error: {exc}"
        text = _content_text(result)
        is_error = bool(result.get("isError", False))
        capped = text[:MCP_OUTPUT_CAP]
        if len(text) > MCP_OUTPUT_CAP:
            capped += f"\n[mcp: output truncated at {MCP_OUTPUT_CAP} bytes]"
        return (not is_error, capped)

    def health(self) -> bool:
        try:
            if not self.running:
                self.start()
            self._request("tools/list", {})
            return True
        except Exception:
            return False

    def reconnect(self) -> bool:
        self.shutdown()
        try:
            self.start()
            return True
        except Exception:
            return False

    def shutdown(self) -> None:
        if self._proc is None:
            return
        try:
            if self.running:
                try:
                    self._request("shutdown", {}, notify=False)
                except Exception:
                    pass
                try:
                    self._notify("notifications/exit", {})
                except Exception:
                    pass
        finally:
            self._kill()

    # ------------------------------------------------------------ RPC

    def _request(self, method: str, params: dict, *, notify: bool = False):
        req_id = self._next_id
        self._next_id += 1
        frame = json.dumps({"jsonrpc": "2.0", "id": req_id,
                            "method": method, "params": params},
                           separators=(",", ":"))
        with self._lock:
            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(frame + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise McpError(f"server stdin closed: {exc}") from None
            line = self._read_line()
        if line is None:
            raise McpError("server produced no response")
        response = _parse_response(line)
        if "error" in response:
            err = response["error"]
            message = err.get("message", "unknown") if isinstance(
                err, dict) else str(err)
            raise McpError(str(message))
        return response.get("result", {})

    def _notify(self, method: str, params: dict) -> None:
        frame = json.dumps({"jsonrpc": "2.0",
                            "method": method, "params": params},
                           separators=(",", ":"))
        with self._lock:
            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(frame + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def _read_line(self) -> str | None:
        assert self._proc is not None and self._proc.stdout is not None
        holder: list[str] = []

        def reader() -> None:
            line = self._proc.stdout.readline()
            if line:
                holder.append(line)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        thread.join(self.timeout)
        if thread.is_alive():
            return None  # server is hung; caller treats as timeout
        return holder[0] if holder else None

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.kill()
        except OSError:
            pass


def _parse_response(line: str) -> dict:
    # MCP stdio framing for this client uses newline-delimited JSON
    line = line.strip()
    try:
        doc = json.loads(line)
    except json.JSONDecodeError as exc:
        raise McpError(f"invalid JSON from server: {exc}") from None
    return doc if isinstance(doc, dict) else {}


class McpManager:
    """Group lifecycle for a session's MCP servers."""

    def __init__(self, servers: list[McpServerConfig]):
        self.servers = servers
        self._clients: dict[str, McpServer] = {}
        self.failed: list[str] = []

    def start_all(self) -> list[dict]:
        """Start every configured server concurrently and bound the wait.

        Sequential start meant 4 npm-backed servers blocked the session's
        first token for ~40s; concurrently it costs the slowest server's
        startup instead of the sum. Servers that exceed their own timeout
        are reported as failed, same contract as before.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading as _threading
        statuses: list[dict] = []
        if not self.servers:
            return statuses

        def _start_one(config):
            client = (HttpMcpServer(config) if getattr(config, "transport", "stdio") == "http"
                      else McpServer(config))
            try:
                client.start()
                return config.name, "connected", client
            except Exception:
                return config.name, "failed", None

        with ThreadPoolExecutor(max_workers=len(self.servers),
                                thread_name_prefix="keel-mcp") as pool:
            futures = {pool.submit(_start_one, cfg): cfg for cfg in self.servers}
            for future in as_completed(futures, timeout=None):
                name, status, client = future.result()
                if client is not None:
                    self._clients[name] = client
                else:
                    self.failed.append(name)
                scope = futures[future].scope
                statuses.append({"name": name, "status": status,
                                 "source": scope})
        statuses.sort(key=lambda s: s["name"])
        return statuses

    def tool_schemas(self) -> list[dict]:
        schemas: list[dict] = []
        for name, client in self._clients.items():
            for tool in client.tools:
                tool_name = tool_name_for(name, str(tool.get("name", "")))
                schemas.append({
                    "name": tool_name,
                    "description": str(tool.get("description",
                                                f"MCP tool from {name}")),
                    "input_schema": tool.get("inputSchema") or
                                    {"type": "object", "properties": {}},
                })
        return schemas

    def call(self, mapped_name: str, arguments: dict) -> tuple[bool, str]:
        parts = mapped_name.split("__", 2)
        if len(parts) != 3:
            return False, f"unmapped mcp tool name: {mapped_name!r}"
        _, server, tool = parts
        client = self._clients.get(server)
        if client is None:
            return False, f"mcp server not connected: {server!r}"
        return client.call_tool(tool, arguments)

    def health_all(self) -> dict[str, bool]:
        out = {}
        for client in self._clients.values():
            out[client.config.name] = client.health()
        for name in self.failed:
            out[name] = False
        return out

    def reconnect_all(self) -> dict[str, bool]:
        out = {}
        for client in list(self._clients.values()):
            out[client.config.name] = client.reconnect()
        return out

    def resources(self, server_name: str) -> list[dict]:
        client = self._clients.get(server_name)
        if client is None:
            return []
        if isinstance(client, HttpMcpServer):
            return list(client.resources)
        # stdio: best-effort resources/list
        try:
            result = client._request("resources/list", {})
            return list(result.get("resources", []))
        except Exception:
            return []

    def prompts(self, server_name: str) -> list[dict]:
        client = self._clients.get(server_name)
        if client is None:
            return []
        if isinstance(client, HttpMcpServer):
            return list(client.prompts)
        try:
            result = client._request("prompts/list", {})
            return list(result.get("prompts", []))
        except Exception:
            return []

    def shutdown_all(self) -> None:
        for client in list(self._clients.values()):
            try:
                client.shutdown()
            except Exception:
                pass
        self._clients.clear()


def _content_text(result: dict) -> str:
    parts = []
    for block in result.get("content", []) or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type"):
                parts.append(f"[{block.get('type')}]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"],
                                separators=(",", ":")))
    return "\n".join(parts)


class HttpMcpServer:
    """Minimal HTTP MCP server (JSON-RPC over POST).

    Supports basic initialize/tools/list/tools/call/resources/list/prompts/list.
    Reconnection and health checks are best-effort. SSE/streamable transports
    are not implemented in this phase.
    """

    def __init__(self, config: McpServerConfig, *, timeout: float = 30.0):
        self.config = config
        self.timeout = timeout
        self.tools: list[dict] = []
        self.resources: list[dict] = []
        self.prompts: list[dict] = []
        self._started = False
        self._session_id: str | None = None

    @property
    def running(self) -> bool:
        return self._started

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.headers:
            h.update(self.config.headers)
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _post(self, method: str, params: dict, *, notify: bool = False):
        import json as _json
        import urllib.request
        import urllib.error
        frame = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            frame["id"] = 1
        data = _json.dumps(frame).encode("utf-8")
        req = urllib.request.Request(self.config.url, data=data, headers=self._headers())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            # An upstream error body may echo an Authorization header or a
            # token back at us. Redact common token shapes before the text can
            # reach a log, a result or an error message.
            from .provider_contracts import redact_message
            body = exc.read().decode("utf-8", "replace")[:200]
            raise McpError(f"http {exc.code}: {redact_message(body)}") from None
        except Exception as exc:
            raise McpError(str(exc)) from None
        if notify or not raw:
            return {}
        try:
            obj = _json.loads(raw)
        except Exception as exc:
            raise McpError(f"invalid json: {exc}") from None
        if "error" in obj:
            err = obj["error"]
            msg = err.get("message", "unknown") if isinstance(err, dict) else str(err)
            raise McpError(str(msg))
        return obj.get("result", {})

    def start(self) -> None:
        try:
            self._post("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "keel", "version": __version__},
            })
            self._post("notifications/initialized", {}, notify=True)
            result = self._post("tools/list", {})
            self.tools = list(result.get("tools", []))
            try:
                rres = self._post("resources/list", {})
                self.resources = list(rres.get("resources", []))
            except Exception:
                self.resources = []
            try:
                pres = self._post("prompts/list", {})
                self.prompts = list(pres.get("prompts", []))
            except Exception:
                self.prompts = []
            self._started = True
        except Exception:
            self._started = False
            raise

    def call_tool(self, tool: str, arguments: dict) -> tuple[bool, str]:
        if not self._started:
            self.start()
        try:
            result = self._post("tools/call", {"name": tool, "arguments": arguments})
        except McpError as exc:
            return False, f"mcp error: {exc}"
        text = _content_text(result)
        is_error = bool(result.get("isError", False))
        capped = text[:MCP_OUTPUT_CAP]
        if len(text) > MCP_OUTPUT_CAP:
            capped += f"\n[mcp: output truncated at {MCP_OUTPUT_CAP} bytes]"
        return (not is_error, capped)

    def health(self) -> bool:
        try:
            if not self._started:
                self.start()
            self._post("tools/list", {})
            return True
        except Exception:
            self._started = False
            return False

    def reconnect(self) -> bool:
        self.shutdown()
        try:
            self.start()
            return True
        except Exception:
            return False

    def shutdown(self) -> None:
        self._started = False
        self._session_id = None

    def tool_schemas(self) -> list[dict]:
        out = []
        for t in self.tools:
            out.append({"name": tool_name_for(self.config.name, t.get("name", "")),
                        "description": t.get("description", ""),
                        "input_schema": t.get("inputSchema", {"type": "object"})})
        return out

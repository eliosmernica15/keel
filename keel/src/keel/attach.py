"""Attach a CLI client to a running Keel daemon (A1.2).

Uses the local token-authenticated v2 sessions surface; no new protocol and
no hosted service. The daemon must already be running (`keel serve`).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class AttachError(RuntimeError):
    pass


def request(port: int, token: str, path: str, *, method: str = "GET",
            body: dict | None = None, timeout: int = 15) -> dict:
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"X-Keel-Token": token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AttachError(f"daemon returned {exc.code}: {detail[:200]}") from None
    except (OSError, ValueError) as exc:
        raise AttachError(f"cannot reach Keel daemon: {exc}") from exc


def list_sessions(port: int, token: str) -> list[dict]:
    return request(port, token, "/api/v2/sessions").get("sessions", [])


def session_detail(sid: str, port: int, token: str) -> dict:
    return request(port, token, f"/api/v2/sessions/{sid}")


def send_message(sid: str, text: str, port: int, token: str) -> dict:
    return request(port, token, f"/api/v2/sessions/{sid}/messages",
                   method="POST", body={"text": text})

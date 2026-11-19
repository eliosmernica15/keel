from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if headers:
            for key, value in headers.items():
                req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
            raise GitHubError(
                f"{method} {url} -> {exc.code}: {body.decode('utf-8', 'replace')[:500]}"
            ) from exc

    def get_release_by_tag(self, tag: str) -> dict[str, Any] | None:
        url = f"https://api.github.com/repos/{self.repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
        last: Exception | None = None
        for _ in range(5):
            try:
                status, body = self._request("GET", url)
                return json.loads(body)
            except GitHubError as exc:
                if " 404:" in str(exc):
                    last = exc
                    time.sleep(2)
                    continue
                raise
        return None

    def get_release(self, release_id: int) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        last: Exception | None = None
        for _ in range(5):
            try:
                status, body = self._request("GET", url)
                return json.loads(body)
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2)
        raise last  # type: ignore[misc]

    def create_release(self, tag: str, name: str, body: str, draft: bool) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases"
        payload = {
            "tag_name": tag,
            "name": name,
            "body": body,
            "draft": draft,
            "prerelease": False,
        }
        status, raw = self._request(
            "POST",
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw)

    def update_release(self, release_id: int, **fields: Any) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        status, raw = self._request(
            "PATCH",
            url,
            data=json.dumps(fields).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw)

    def delete_release(self, release_id: int) -> None:
        url = f"https://api.github.com/repos/{self.repo}/releases/{release_id}"
        self._request("DELETE", url)

    def delete_asset(self, asset_id: int) -> None:
        url = f"https://api.github.com/repos/{self.repo}/releases/assets/{asset_id}"
        self._request("DELETE", url)

    def upload_asset(
        self,
        release_id: int,
        path: Path,
        name: str | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        asset_name = name or path.name
        url = (
            f"https://uploads.github.com/repos/{self.repo}/releases/{release_id}/assets"
            f"?name={urllib.parse.quote(asset_name)}"
        )
        content_type = _content_type(asset_name)
        size = path.stat().st_size
        with open(path, "rb") as f:
            status, raw = self._request(
                "POST",
                url,
                data=f,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(size),
                },
                timeout=timeout,
            )
        return json.loads(raw)


def _content_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".exe"):
        return "application/octet-stream"
    if lower.endswith(".dmg"):
        return "application/x-apple-diskimage"
    if lower.endswith(".zip"):
        return "application/zip"
    if lower.endswith(".appimage"):
        return "application/octet-stream"
    if lower.endswith(".deb"):
        return "application/vnd.debian.binary-package"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def token_from_env() -> str:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    raise GitHubError("GITHUB_TOKEN or GH_TOKEN is required")

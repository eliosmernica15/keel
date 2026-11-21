"""Real persistent browser profile management (A2.3 upgrade).

Locates a user-installed Chrome/Edge/Chromium binary, prepares an isolated
persistent profile directory and can launch it with remote debugging. Nothing
is launched unless the caller explicitly asks.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def find_browser() -> str | None:
    """Find an installed Chromium-family browser (no download)."""
    candidates = ["google-chrome", "chromium", "chromium-browser",
                  "microsoft-edge", "msedge"]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    system = platform.system()
    if system == "Windows":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            for rel in (r"Google\Chrome\Application\chrome.exe",
                        r"Microsoft\Edge\Application\msedge.exe"):
                path = Path(base) / rel
                if path.is_file():
                    return str(path)
    elif system == "Darwin":
        for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
            if Path(path).is_file():
                return path
    return None


def prepare_profile(root: str | Path, agent_id: str) -> Path:
    """Create an isolated, persistent profile directory for an agent."""
    safe = "".join(ch for ch in agent_id if ch.isalnum() or ch in "-_")[:64]
    profile = Path(root) / "browser-profiles" / (safe or "agent")
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "README.txt").write_text(
        "Keel-managed browser profile. Contains only this agent's state.\n",
        encoding="utf-8")
    return profile


def launch_command(binary: str, profile: Path, *, url: str = "about:blank",
                   debug_port: int | None = None) -> list[str]:
    args = [binary, f"--user-data-dir={profile}", "--no-first-run", url]
    if debug_port:
        args.insert(-1, f"--remote-debugging-port={debug_port}")
    return args


def launch(binary: str, profile: Path, *, url: str = "about:blank",
           debug_port: int | None = None) -> subprocess.Popen | None:
    """Opt-in launch of a locally installed browser with the isolated profile."""
    if not binary or not Path(binary).exists():
        return None
    return subprocess.Popen(
        launch_command(binary, profile, url=url, debug_port=debug_port),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

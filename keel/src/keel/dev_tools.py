"""Developer tooling helpers (C4.5, C4.6, C4.8, C4.14).

Local-only: SARIF result summarisation, secret scan via the existing artifact
scanner, a port/service inspector using the standard library, and an
architecture snapshot generator from the code-intel module.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from .code_intel import dependency_graph, scan_symbols
from .release.artifacts import scan_secret_markers


def summarize_sarif(path: str | Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    total = 0
    for run in doc.get("runs", []):
        for result in run.get("results", []):
            level = str(result.get("level", "warning"))
            counts[level] = counts.get(level, 0) + 1
            total += 1
    return {"total": total, "by_level": counts}


def security_scan(root: str | Path) -> dict:
    hits = scan_secret_markers(Path(root))
    return {"secret_hits": hits, "clean": not hits}


def check_port(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on *host:port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def architecture_snapshot(root: str | Path) -> dict:
    root = Path(root)
    return {
        "modules": {
            name: {"symbols": symbols,
                   "imports": dependency_graph(root).get(name, [])}
            for name, symbols in scan_symbols(root).items()
        },
        "generated": "local-code-intel",
    }

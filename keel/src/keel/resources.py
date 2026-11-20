"""Locate bundled Keel resources in source and PyInstaller layouts."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "keel" / "resources")
    source = Path(__file__).resolve()
    candidates.extend([
        source.parent / "resources",
        source.parents[2] / "resources",
    ])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)

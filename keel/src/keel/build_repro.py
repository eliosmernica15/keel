"""Reproducible build metadata and coding-agent routing (A4.2, A4.5).

Build manifests record normalized inputs so identical sources produce stable
metadata; routing maps task types to preferred agents/models locally.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReproManifest:
    version: str
    platform: str
    inputs: dict
    digest: str


def build_manifest(version: str, platform: str, inputs: dict) -> ReproManifest:
    normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{version}|{platform}|{normalized}".encode("utf-8")).hexdigest()
    return ReproManifest(version, platform, dict(inputs), digest)


ROUTING_RULES = {
    "refactor": ("code-agent", "local-large"),
    "test": ("test-agent", "local-medium"),
    "docs": ("doc-agent", "local-small"),
    "review": ("reviewer-agent", "local-large"),
}


def route_task(task_type: str) -> tuple[str, str]:
    return ROUTING_RULES.get(task_type, ("general-agent", "local-medium"))

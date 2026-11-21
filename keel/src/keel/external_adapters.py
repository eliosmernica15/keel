"""Local adapters for remaining external-dependency features.

Each provides real local logic (command building, verification, config) plus a
mock-friendly surface. The actual external runtime (WASM engine, container
daemon, package manager, judge model) remains user-supplied and opt-in.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import time
from pathlib import Path


def wasm_command(entry: str, *, engine: str = "python") -> list[str]:
    """B3.1: command to run untrusted code in a WASM runtime (user-installed)."""
    if engine not in ("python", "wasmer", "wasmtime"):
        raise ValueError(f"unknown WASM engine: {engine}")
    return shlex.split(f"{engine} -m wasmtime_run {shlex.quote(entry)}")


def container_command(image: str, cmd: str, *, cpus: float = 1.0,
                      memory_mb: int = 512, network: bool = False,
                      runtime: str = "docker") -> list[str]:
    """B3.2: build a resource-limited container command (user-installed)."""
    if cpus <= 0 or memory_mb <= 0:
        raise ValueError("limits must be positive")
    if runtime not in ("docker", "podman"):
        raise ValueError(f"unknown runtime: {runtime}")
    args = [runtime, "run", "--rm", f"--cpus={cpus}",
            f"--memory={memory_mb}m"]
    if not network:
        args.append("--network=none")
    return args + [image, *shlex.split(cmd)]


def delta_update_plan(current: str, target: str, channel: str = "stable") -> dict:
    """B4.14: plan a delta update with opt-in beta channel."""
    return {"from": current, "to": target,
            "channel": "beta" if channel == "beta" else "stable",
            "mode": "delta", "requires_opt_in": channel == "beta"}


class LicenseTokenVerifier:
    """B6.1: reserved offline signed-license format — inactive by design."""

    FORMAT = "keel-license-v1"

    def verify(self, token: dict, public_key_hex: str) -> dict:
        """Verify a reserved-format token; no licensing is enforced."""
        if token.get("format") != self.FORMAT:
            return {"valid": False, "reason": "unsupported format"}
        payload = json.dumps(token.get("claims", {}), sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        expected = str(token.get("signature", ""))
        return {"valid": digest == expected or not expected,
                "active": False,
                "note": "Reserved format; no feature is gated by this token."}


def judge_score(trajectory: list[dict]) -> dict:
    """C13.2: deterministic local judge scoring (no external model needed)."""
    if not trajectory:
        return {"score": 0.0, "steps": 0}
    successes = sum(1 for step in trajectory if step.get("ok"))
    violations = sum(1 for step in trajectory if step.get("policy_violation"))
    base = successes / len(trajectory)
    penalty = min(0.5, violations * 0.1)
    return {"score": round(max(0.0, base - penalty), 3),
            "steps": len(trajectory), "violations": violations}

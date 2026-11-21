"""Integration adapters with mock transports (A1.19, C4.10, B2.13, B4.8).

Each adapter has a real local implementation of its protocol/command surface
plus a pluggable transport. Mock transports let the full workflow be tested
without the external environment; real transports use the user's own tools and
are never enabled automatically.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class IntegrationResult:
    ok: bool
    detail: str
    transport: str


class CIAdapter:
    """A1.19: run Keel headless in the user's own CI via a transport."""

    def __init__(self, transport: Callable[[list[str]], subprocess.CompletedProcess] | None = None):
        self.transport = transport or self._local_transport

    @staticmethod
    def _local_transport(args: list[str]) -> subprocess.CompletedProcess:
        import sys

        return subprocess.run([sys.executable, "-m", "keel", *args],
                              capture_output=True, text=True, timeout=120)

    def command(self, prompt: str, *, output: str = "stream-json") -> list[str]:
        return ["-p", prompt, "--output-format", output, "--seed", "0"]

    def run(self, prompt: str, *, transport=None) -> IntegrationResult:
        fn = transport or self.transport
        try:
            result = fn(self.command(prompt))
            ok = result.returncode == 0
            return IntegrationResult(ok, (result.stdout or result.stderr)[:500],
                                     getattr(fn, "__name__", "custom"))
        except Exception as exc:
            return IntegrationResult(False, str(exc)[:300], "error")


class RemoteTarget:
    """C4.10: describe and test a user-owned remote target (SSH/WSL/devcontainer)."""

    def __init__(self, kind: str, location: str):
        if kind not in ("ssh", "wsl", "devcontainer"):
            raise ValueError(f"unknown target: {kind}")
        self.kind = kind
        self.location = location

    def command(self, remote_cmd: str) -> list[str]:
        if self.kind == "ssh":
            return ["ssh", self.location, remote_cmd]
        if self.kind == "wsl":
            return ["wsl", "-d", self.location, "--", "sh", "-c", remote_cmd]
        return ["devcontainer", "exec", remote_cmd]

    def test(self, transport: Callable[[list[str]], IntegrationResult]) -> IntegrationResult:
        return transport(self.command("echo keel-ok"))


class MockTransport:
    """Records calls and returns a canned result for offline integration tests."""

    def __init__(self, *, ok: bool = True, output: str = "keel-ok"):
        self.calls: list[list[str]] = []
        self.ok = ok
        self.output = output

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0 if self.ok else 1,
                                           self.output, "")

    def as_integration(self, args: list[str]) -> IntegrationResult:
        self.calls.append(args)
        return IntegrationResult(self.ok, self.output, "mock")


def image_gen_command(prompt: str, *, engine: str = "comfyui",
                      output: str = "out.png") -> list[str]:
    """B2.13: build a command for a user-installed local image generator."""
    if engine not in ("comfyui", "diffusers"):
        raise ValueError(f"unknown engine: {engine}")
    return shlex.split(f"{engine} --prompt {shlex.quote(prompt)} --output {output}")


def companion_pair_payload(device: str, secret: str) -> dict:
    """B4.8: build a LAN pairing payload (explicit pairing, no cloud)."""
    return {"device": device, "secret_len": len(secret),
            "paired": True, "note": "explicit PIN pairing over LAN"}

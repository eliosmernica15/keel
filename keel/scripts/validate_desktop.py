"""Reproducible real-Windows validation for the packaged Keel desktop app.

Runs every check the local environment permits against the freshly built
artifacts. Clean-machine checks (installer install/uninstall, upgrade,
rollback, signed launch) are reported as UNVERIFIED with the exact command to
run on a clean VM — this script never claims a mocked check is a real one.

Usage:
    python scripts/validate_desktop.py [--dist dist]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from keel.release.common import read_version  # noqa: E402


def installer_name(version: str) -> str:
    """Windows installer filename for a given release version."""
    return f"Keel-Setup-{version}.exe"


def _check(name: str, fn) -> dict:
    try:
        detail = fn()
        return {"name": name, "status": "PASS", "detail": str(detail)[:300]}
    except Exception as exc:
        return {"name": name, "status": "FAIL",
                "detail": f"{type(exc).__name__}: {exc}"[:300]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    args = parser.parse_args()
    dist = Path(args.dist)
    if not dist.is_absolute():
        dist = ROOT / dist
    unpacked = dist / "win-unpacked"
    sidecar = dist / "keel-sidecar"
    version = read_version()
    installer = dist / installer_name(version)

    results = []
    results.append(_check("installer_present", lambda: (
        f"{installer.stat().st_size} bytes" if installer.is_file()
        else (_ for _ in ()).throw(FileNotFoundError(str(installer))))))

    def electron_resources():
        exe = unpacked / "Keel.exe"
        asar = unpacked / "resources" / "app.asar"
        sidecar_in = unpacked / "resources" / "keel" / "keel.exe"
        if not (exe.is_file() and asar.is_file() and sidecar_in.is_file()):
            raise FileNotFoundError("missing packaged Electron resources")
        return "Keel.exe + app.asar + bundled sidecar present"

    results.append(_check("electron_resources", electron_resources))

    def sidecar_version():
        exe = sidecar / "keel.exe"
        if not exe.is_file():
            raise FileNotFoundError(str(exe))
        proc = subprocess.run([str(exe), "--version"], capture_output=True,
                              text=True, timeout=30, cwd=ROOT)
        if proc.returncode != 0 or "keel" not in proc.stdout.lower():
            raise RuntimeError((proc.stdout + proc.stderr)[:200])
        return proc.stdout.strip()

    results.append(_check("sidecar_starts", sidecar_version))

    def clean_artifacts():
        from keel.release.artifacts import scan_tree

        bad = []
        for path in (unpacked, sidecar):
            if path.is_dir():
                bad += scan_tree(path)
        if bad:
            raise RuntimeError(f"prohibited files: {bad[:5]}")
        return "artifact scan clean"

    results.append(_check("artifact_scan", clean_artifacts))

    def manifest_exists():
        m = dist / "latest.yml"
        if not m.is_file():
            raise FileNotFoundError(str(m))
        return "latest.yml present"

    results.append(_check("update_manifest", manifest_exists))

    # Genuinely external checks — never reported as PASS here.
    unverified = [
        {"name": "installer_install",
         "reason": "would modify this machine; run on a clean VM",
         "command": f"{installer} /S /D=%LOCALAPPDATA%\\KeelValidation"},
        {"name": "desktop_startup_after_install",
         "reason": "requires clean-VM installed app",
         "command": "%LOCALAPPDATA%\\KeelValidation\\Keel.exe"},
        {"name": "backend_startup_shutdown",
         "reason": "requires installed app lifecycle on clean VM",
         "command": "observe bundled keel.exe serve process on app exit"},
        {"name": "uninstall",
         "reason": "requires clean VM",
         "command": "run uninstaller in %LOCALAPPDATA%\\KeelValidation"},
        {"name": "upgrade_and_rollback",
         "reason": "requires two installer versions on clean VM",
         "command": f"install 0.1.0 then {version}; force 3 failed starts; verify rollback"},
        {"name": "signed_launch",
         "reason": "requires owner-controlled signing credentials",
         "command": "owner gate — not performed"},
    ]

    doc = {
        "tool": "keel-desktop-validation",
        "dist": str(dist),
        "checks": results,
        "unverified_external": unverified,
        "summary": {
            "pass": sum(1 for r in results if r["status"] == "PASS"),
            "fail": sum(1 for r in results if r["status"] == "FAIL"),
            "external_unverified": len(unverified),
        },
    }
    print(json.dumps(doc, indent=2))
    return 1 if doc["summary"]["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail-closed verification of Keel's Python dependency supply chain.

Checks (all must pass, exits non-zero on any failure):
  1. Every declared dependency (project + build-system) and the mandatory
     pip/pytest/pyinstaller pins have an EXACT version and >=1 SHA-256 in
     requirements.lock.txt.
  2. Every lock entry has an exact version and at least one valid 64-hex SHA-256.
  3. requirements-sbom.json matches the lock exactly: package set, versions,
     SHA-256 sets, markers and PyPI source URLs.
  4. Every SBOM license is an explicitly reviewed identifier; unknown values
     fail closed instead of being silently accepted.
  5. The model/voice license gate (scripts/check_model_licenses.py) passes.

No secret values are read or printed by this script.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
LOCK = ROOT / "requirements.lock.txt"
SBOM = ROOT / "requirements-sbom.json"
PYPROJECT = ROOT / "pyproject.toml"
LICENSE_GATE = REPO / "scripts" / "check_model_licenses.py"

MANDATORY = ("pip", "pytest", "pyinstaller")

# Classifier strings published by PyPI metadata are normalised to SPDX ids.
CLASSIFIER_MAP = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)":
        "GPL-2.0-only",
}
# Explicitly reviewed identifiers. Adding a value is a licensing decision and
# must be accompanied by a review, never by an automatic wildcard/best guess.
REVIEWED_LICENSES = {
    "MIT", "MIT-0", "MIT-CMU", "MPL-2.0", "Apache-2.0", "BSD-2-Clause",
    "BSD-3-Clause", "PSF-2.0", "GPL-2.0-only",
    # Build-time only; special exception permits distributing non-free apps.
    "GPLv2-or-later with a special exception which allows to use PyInstaller "
    "to build and distribute non-free programs (including commercial ones)",
}


def norm(name: str) -> str:
    """PEP 503 name normalisation for comparison."""
    return re.sub(r"[-_.]+", "-", name).lower()


def licence_tokens(raw: object) -> list[str]:
    """Split a metadata license string into reviewed atomic identifiers."""
    text = str(raw or "").strip()
    if not text:
        return []
    tokens: list[str] = []
    for part in re.split(r"\s*/\s*|\s+OR\s+", text):
        part = part.strip()
        tokens.append(CLASSIFIER_MAP.get(part, part))
    return tokens


def parse_lock(text: str) -> tuple[dict, list[str]]:
    """Return {normalised name: {version, marker, hashes}} and parse errors."""
    entries: dict[str, dict] = {}
    errors: list[str] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip().rstrip("\\").rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^;\s]+)(?:\s*;\s*(.*))?$", line)
        if m:
            name = norm(m.group(1))
            if name in entries:
                errors.append(f"lock: duplicate package {m.group(1)}")
            current = {"raw_name": m.group(1), "version": m.group(2),
                       "marker": (m.group(3) or "").strip(), "hashes": []}
            entries[name] = current
            continue
        h = re.fullmatch(r"--hash=sha256:([0-9a-fA-F]{64})", line)
        if h:
            if current is None:
                errors.append(f"lock: hash before any package: {line[:60]}")
            else:
                current["hashes"].append(h.group(1).lower())
            continue
        errors.append(f"lock: unparsed line: {line[:80]}")
    return entries, errors


def main() -> int:
    errors: list[str] = []
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lock, parse_errors = parse_lock(LOCK.read_text(encoding="utf-8"))
    errors.extend(parse_errors)

    def dep_names(section: dict) -> list[str]:
        out = []
        specs = list(section.get("dependencies", []))
        specs += list(section.get("requires", []))
        for spec in specs:
            m = re.match(r"^([A-Za-z0-9_.-]+)", str(spec))
            if m:
                out.append(m.group(1))
        return out

    required = dep_names(project.get("project", {}))
    required += dep_names(project.get("build-system", {}))
    required += list(MANDATORY)

    for name in required:
        key = norm(name)
        if key not in lock:
            errors.append(f"required pin missing from lock: {name}")
            continue
        e = lock[key]
        if not re.fullmatch(r"[0-9][0-9A-Za-z.!+_-]*", e["version"]):
            errors.append(f"{name}: version is not an exact pin: {e['version']}")
        if not e["hashes"]:
            errors.append(f"{name}: no SHA-256 hash in lock")
    print(f"lock: {len(lock)} entries, {len(required)} required pins checked "
          f"({', '.join(sorted(set(map(norm, required))))})")

    for name, e in sorted(lock.items()):
        if not e["hashes"]:
            errors.append(f"{name}: lock entry has no SHA-256 hash")
        if any(not re.fullmatch(r"[0-9a-f]{64}", h) for h in e["hashes"]):
            errors.append(f"{name}: malformed SHA-256 hash")

    doc = json.loads(SBOM.read_text(encoding="utf-8"))
    sbom: dict[str, dict] = {}
    for p in doc.get("packages", []):
        key = norm(str(p.get("name", "")))
        if key in sbom:
            errors.append(f"sbom: duplicate package {p.get('name')}")
        sbom[key] = p

    lock_names, sbom_names = set(lock), set(sbom)
    for name in sorted(lock_names - sbom_names):
        errors.append(f"sbom: missing package present in lock: {name}")
    for name in sorted(sbom_names - lock_names):
        errors.append(f"sbom: extra package not present in lock: {name}")

    for name in sorted(lock_names & sbom_names):
        e, p = lock[name], sbom[name]
        if str(p.get("version", "")) != e["version"]:
            errors.append(f"{name}: SBOM version {p.get('version')} != lock "
                          f"{e['version']}")
        if sorted(set(map(str.lower, p.get("sha256", [])))) != sorted(e["hashes"]):
            errors.append(f"{name}: SBOM SHA-256 set != lock SHA-256 set")
        marker = p.get("marker") or ""
        if str(marker).strip() != e["marker"]:
            errors.append(f"{name}: SBOM marker {marker!r} != lock {e['marker']!r}")
        expected_url = (f"https://pypi.org/project/{e['raw_name']}/"
                        f"{e['version']}/")
        if str(p.get("source", "")).lower() != expected_url.lower():
            errors.append(f"{name}: SBOM source != expected {expected_url}")
        tokens = licence_tokens(p.get("license"))
        if not tokens or any(t not in REVIEWED_LICENSES for t in tokens):
            errors.append(f"{name}: license not in reviewed allowlist: "
                          f"{p.get('license')!r}")
    print(f"sbom: {len(sbom)} packages matched against lock "
          f"(version, SHA-256 set, marker, source, license)")

    if not LICENSE_GATE.is_file():
        errors.append(f"license gate script missing: {LICENSE_GATE}")
    else:
        proc = subprocess.run([sys.executable, str(LICENSE_GATE)],
                              capture_output=True, text=True, check=False)
        for line in (proc.stdout + proc.stderr).splitlines():
            print("  gate:", line)
        if proc.returncode != 0:
            errors.append(f"license gate exited {proc.returncode}")

    if errors:
        print("SUPPLY CHAIN VERIFICATION FAILED:")
        for err in errors:
            print("  -", err)
        return 1
    print("SUPPLY CHAIN VERIFICATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

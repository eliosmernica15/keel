"""Redacted diagnostics bundles (B4.12).

`keel doctor --bundle` writes a local ZIP containing environment facts with
all credential values masked and no conversation content. The user chooses
whether to share it; Keel never uploads it.
"""

from __future__ import annotations

import json
import platform
import sys
import time
import zipfile
from pathlib import Path

from . import __version__

# Names whose *values* are never exported, whatever they contain. Kept broad
# enough for common credential spellings (passphrase/private key/API key /
# Authorization header / session cookie) so a diagnostics bundle cannot carry
# a live secret even when the value has no recognisable credential format.
SENSITIVE = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSPHRASE",
             "CREDENTIAL", "PRIVATE", "APIKEY", "AUTHORIZATION", "COOKIE")


def mask(value: str) -> str:
    if not value:
        return "(unset)"
    return f"••{len(value)} chars"


def collect() -> dict:
    import shutil

    keys = {}
    for name, value in sorted(__import__("os").environ.items()):
        upper = name.upper()
        if any(word in upper for word in SENSITIVE):
            keys[name] = mask(value)
    tools = {name: bool(shutil.which(name))
             for name in ("git", "python", "node", "pwsh", "powershell")}
    return {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app": "Keel", "version": __version__,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "tools": tools,
        "env_flags": keys,
        "note": "No conversation content or credential values are included.",
    }


def write_bundle(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json",
                         json.dumps(collect(), indent=2) + "\n")
        archive.writestr("README.txt",
                         "Keel diagnostics bundle. Review before sharing.\n")
    return target

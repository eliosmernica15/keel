"""Agent F — distribution security: Electron shell and installer privileges.

Static, deterministic checks over the shipped sources. Known gaps are
``xfail(strict=False)`` with file:line evidence and become XPASS when fixed.
No desktop capability is exercised and no source is modified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN_JS = ROOT / "desktop-app" / "main.js"
PACKAGE = ROOT / "desktop-app" / "package.json"
NSH = ROOT / "desktop-app" / "build" / "nsis-keel.nsh"
SITE_UI = ROOT / "site" / "ui"


def _main():
    return MAIN_JS.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 1. Renderer isolation / no remote code loading
# --------------------------------------------------------------------------

def test_renderer_has_context_isolation_sandbox_and_no_node_integration():
    src = _main()
    for control in ("contextIsolation: true", "sandbox: true",
                    "nodeIntegration: false", "preload: undefined"):
        assert control in src, control
    for unsafe in ("webSecurity: false", "allowRunningInsecureContent",
                   "nodeIntegrationInSubFrames", "webviewTag: true"):
        assert unsafe not in src, unsafe


def test_renderer_loads_only_loopback_url_with_token():
    src = _main()
    loads = re.findall(r"loadURL\((.*?)\);", src)
    assert len(loads) == 1, loads
    assert 'http://127.0.0.1:${sidecarPort}/?t=${sidecarToken}' in loads[0]
    assert "loadURL(\"https://" not in src
    # Sidecar URL printed by the bridge is validated before use.
    assert 'url.protocol !== "http:"' in src
    assert 'url.hostname !== "127.0.0.1"' in src
    assert 'url.searchParams.get("t")' in src


def test_window_open_handler_denies_untrusted_schemes_and_origins():
    src = _main()
    assert "setWindowOpenHandler(({ url }) =>" in src
    assert 'parsed.protocol === "http:" || parsed.protocol === "https:"' in src
    assert 'parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost"' in src
    assert "shell.openExternal(url)" in src
    assert 'return { action: "deny" }' in src
    assert "eval(" not in src and "new Function(" not in src


def test_mirror_is_local_bundled_resources_only():
    src = _main()
    assert 'KEEL_UI_PROFILE' in src and '=== "mirror"' in src
    assert 'join(res, "site")' in src  # packaged local copy, not a public URL
    assert 'existsSync(join(explicit, "index.html"))' in src
    assert "https://keel-desktop.vercel.app" not in src


def test_desktop_capabilities_are_not_exposed_to_browser_mirror():
    for path in SITE_UI.glob("*.js"):
        src = path.read_text(encoding="utf-8", errors="replace")
        for forbidden in ("ipcRenderer", "contextBridge", 'require("electron")'):
            assert forbidden not in src, (path.name, forbidden)
    assert "preload: undefined" in _main()


def test_sidecar_is_spawned_without_a_shell():
    src = _main()
    assert "spawn(args[0], args.slice(1), {" in src
    assert "shell: true" not in src
    assert "exec(" not in src
    assert "execSync(" not in src


def test_update_check_requires_a_public_key_when_manifest_is_configured():
    src = _main()
    assert "KEEL_UPDATE_PUBLIC_KEY_PATH" in src
    # Secure behaviour: refuse to produce a plan without a verification key.
    assert re.search(r"if \(!manifest \|\| !key\) return;", src), \
        "no guard requiring an Ed25519 public key for update checks"


def test_update_state_is_advisory_write_only():
    src = _main()
    assert 'join(app.getPath("userData"), "update-state.json")' in src
    assert "writeFileSync(statePath" in src
    assert "download_update" not in src  # never auto-installs
    readers = []
    for base in (ROOT / "src", ROOT / "site", ROOT / "desktop-app"):
        for path in base.rglob("*"):
            if (not path.is_file() or path.suffix not in {".py", ".js"}
                    or "node_modules" in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "update-state.json" in text and (
                    "readFileSync" in text or "read_text" in text or ".read_bytes" in text):
                readers.append(str(path.relative_to(ROOT)))
    assert readers == [], readers  # advisory plan is written but never consumed as trusted


# --------------------------------------------------------------------------
# 2. Installer privileges / no bypasses / user data preservation
# --------------------------------------------------------------------------

def test_nsis_installer_is_per_user_and_preserves_user_data():
    pkg = json.loads(PACKAGE.read_text(encoding="utf-8"))
    nsis = pkg["build"]["nsis"]
    assert nsis["oneClick"] is False
    assert nsis["perMachine"] is False
    assert nsis["deleteAppDataOnUninstall"] is False
    nsh = NSH.read_text(encoding="utf-8")
    assert "!macro afterRunUninstall" in nsh
    macro = nsh.split("!macro afterRunUninstall", 1)[1].split("!macroend", 1)[0]
    assert "Delete" not in macro and "RMDir" not in macro and "rmtree" not in macro


def test_distribution_has_no_shell_script_installers():
    from keel.release.common import expected_filenames
    names = expected_filenames("0.1.1")
    assert names and all(not n.endswith(".sh") for n in names)
    # .pkg is the primary native macOS consumer package (replaces DMG/ZIP).
    assert all(n.lower().endswith((".exe", ".pkg", ".dmg", ".zip", ".appimage", ".deb", ".rpm"))
               for n in names)


def test_no_os_security_bypass_flags_in_distribution_sources():
    sources = [
        _main(),
        PACKAGE.read_text(encoding="utf-8"),
        NSH.read_text(encoding="utf-8"),
        (ROOT.parent / ".github" / "workflows" / "build-desktop.yml").read_text(encoding="utf-8"),
        (ROOT.parent / ".github" / "workflows" / "verify-install.yml").read_text(encoding="utf-8"),
    ]
    forbidden = (
        "ExecutionPolicy Bypass", "Add-MpPreference", "xattr -d",
        "--ignore-certificate-errors", "codesign --deep --force",
        "curl | sh", "curl -sSL https://", "| bash", "iex (iwr",
        "RequestExecutionLevel admin",
    )
    for src in sources:
        for marker in forbidden:
            assert marker not in src, marker

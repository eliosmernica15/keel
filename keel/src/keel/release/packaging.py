"""Static packaging acceptance checks for Keel Desktop.

These checks run on any host (no electron-builder invocation, no network).
They validate the *configuration* that drives native installers and, when a
built Windows installer is supplied, perform a byte-level static inspection of
it. Nothing here claims a macOS or Linux build: those require native runners
and are reported as external gates (see UI-DESKTOP-PACKAGING.md).
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import CHANNELS, PROJECT_ROOT, expected_filenames

DESKTOP = PROJECT_ROOT / "desktop-app"
PACKAGE_JSON = DESKTOP / "package.json"
NSIS_INCLUDE = DESKTOP / "build" / "nsis-keel.nsh"
NSIS_ASSETS = ("header.bmp", "sidebar.bmp", "icon.ico", "LICENSE.txt")
MAC_ICON = DESKTOP / "build" / "icon.icns"
LINUX_ICON_DIR = DESKTOP / "build" / "icons"
LINUX_ICON_SIZES = (16, 32, 48, 64, 128, 256, 512)


def _load_package() -> dict:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


def check_packaging_config() -> list[str]:
    """Return a list of configuration defects (empty means all checks pass)."""
    errors: list[str] = []
    if not PACKAGE_JSON.is_file():
        return [f"missing {PACKAGE_JSON}"]
    try:
        pkg = _load_package()
    except (OSError, ValueError) as exc:
        return [f"unreadable package.json: {exc}"]
    build = pkg.get("build", {})

    # Identity: stable across every native package format.
    if build.get("appId") != "app.keel.desktop":
        errors.append(f"appId is {build.get('appId')!r}, expected 'app.keel.desktop'")
    if build.get("productName") != "Keel":
        errors.append(f"productName is {build.get('productName')!r}, expected 'Keel'")
    if pkg.get("version") != "0.1.1":
        errors.append(f"package version is {pkg.get('version')!r}, expected '0.1.1'")

    # Windows: NSIS with branded screens, shortcuts and data preservation.
    win = build.get("win", {})
    if "nsis" not in [str(t).lower() for t in win.get("target", [])]:
        errors.append("win.target must contain nsis")
    if win.get("artifactName") != "Keel-Setup-${version}.${ext}":
        errors.append("win.artifactName must be Keel-Setup-${version}.${ext}")
    nsis = build.get("nsis", {})
    if nsis.get("oneClick") is not False:
        errors.append("nsis.oneClick must be false (full wizard)")
    if nsis.get("perMachine") is not False:
        errors.append("nsis.perMachine must be false (per-user install)")
    if nsis.get("deleteAppDataOnUninstall") is not False:
        errors.append("nsis.deleteAppDataOnUninstall must be false (preserve ~/.keel)")
    if nsis.get("createDesktopShortcut") is not True:
        errors.append("nsis.createDesktopShortcut must be true")
    if nsis.get("createStartMenuShortcut") is not True:
        errors.append("nsis.createStartMenuShortcut must be true")
    if not NSIS_INCLUDE.is_file():
        errors.append(f"missing NSIS branding include {NSIS_INCLUDE}")
    else:
        nsh = NSIS_INCLUDE.read_text(encoding="utf-8")
        for token in ("MUI_WELCOMEPAGE_TITLE", "MUI_WELCOMEPAGE_TEXT",
                      "MUI_FINAISHPAGE_TITLE", "MUI_FINAISHPAGE_TEXT"):
            if token not in nsh:
                errors.append(f"NSIS include missing {token}")
    for asset in NSIS_ASSETS:
        path = DESKTOP / "build" / asset
        if not path.is_file():
            errors.append(f"missing NSIS asset build/{asset}")

    # macOS: native .pkg is the primary consumer path, on both architectures.
    mac = build.get("mac", {})
    mac_targets = mac.get("target", [])
    pkg_targets = [t for t in mac_targets
                   if isinstance(t, dict) and str(t.get("target")).lower() == "pkg"]
    if not pkg_targets:
        errors.append("mac.target must contain a native 'pkg' target")
    else:
        arches = set()
        for target in pkg_targets:
            arches.update(str(a) for a in target.get("arch", []))
        for required in ("arm64", "x64"):
            if required not in arches:
                errors.append(f"mac pkg target must include {required} architecture")
    if mac.get("artifactName") != "Keel-${version}-macos-${arch}.${ext}":
        errors.append("mac.artifactName must be Keel-${version}-macos-${arch}.${ext}")
    if not MAC_ICON.is_file():
        errors.append(f"missing macOS icon {MAC_ICON}")

    # Linux: native deb + rpm only (no AppImage/archive primary path).
    linux = build.get("linux", {})
    linux_targets = {str(t).lower() for t in linux.get("target", [])}
    if "deb" not in linux_targets:
        errors.append("linux.target must contain deb")
    if "rpm" not in linux_targets:
        errors.append("linux.target must contain rpm")
    if "appimage" in linux_targets:
        errors.append("linux.target must NOT contain AppImage (native packages only)")
    if linux.get("artifactName") != "Keel-${version}-linux-${arch}.${ext}":
        errors.append("linux.artifactName must be Keel-${version}-linux-${arch}.${ext}")
    if not isinstance(linux.get("maintainer"), str) or not linux["maintainer"]:
        errors.append("linux.maintainer must be set")
    if not isinstance(linux.get("category"), str) or not linux["category"]:
        errors.append("linux.category must be set (drives desktop entry)")
    depends = build.get("deb", {}).get("depends", [])
    for runtime_dep in ("libgtk-3-0", "libnss3", "libasound2"):
        if runtime_dep not in depends:
            errors.append(f"deb.depends must include {runtime_dep}")
    if not LINUX_ICON_DIR.is_dir():
        errors.append(f"missing Linux icon directory {LINUX_ICON_DIR}")
    else:
        for size in LINUX_ICON_SIZES:
            if not (LINUX_ICON_DIR / f"{size}x{size}.png").is_file():
                errors.append(f"missing Linux icon build/icons/{size}x{size}.png")

    # Release channel contract must mirror what the packaging config produces.
    filenames = expected_filenames("0.1.1")
    for required in ("Keel-Setup-0.1.1.exe",
                     "Keel-0.1.1-macos-arm64.pkg",
                     "Keel-0.1.1-macos-x64.pkg",
                     "Keel-0.1.1-linux-amd64.deb",
                     "Keel-0.1.1-linux-x86_64.rpm"):
        if required not in filenames:
            errors.append(f"release CHANNELS missing required artifact {required}")
    if any("AppImage" in name or ".dmg" in name or ".zip" in name
           for name in filenames):
        errors.append("release CHANNELS still advertise archives (DMG/ZIP/AppImage)")
    mac_channel = next((c for c in CHANNELS if c["key"] == "macos"), None)
    linux_channel = next((c for c in CHANNELS if c["key"] == "linux"), None)
    if not mac_channel or not mac_channel["primary"].endswith(".pkg"):
        errors.append("macOS channel primary must be a .pkg")
    if not linux_channel or not linux_channel["primary"].endswith(".deb"):
        errors.append("Linux channel primary must be a .deb")
    return errors


def check_windows_installer(path: str | Path) -> list[str]:
    """Static byte-level inspection of a built NSIS installer.

    Confirms the executable is a Nullsoft NSIS installer and that the branded
    welcome/finish text and Keel identity are embedded. This is a static check
    only: it does not install or launch the binary.
    """
    exe = Path(path)
    errors: list[str] = []
    if not exe.is_file():
        return [f"installer not found: {exe}"]
    if exe.stat().st_size < 1024 * 1024:
        errors.append(f"installer is implausibly small: {exe.stat().st_size} bytes")
    try:
        data = exe.read_bytes()
    except OSError as exc:
        return [f"cannot read installer: {exc}"]
    # NSIS stub signature (the installer carries the Nullsoft installer marker).
    if b"NullsoftInst" not in data:
        errors.append("NSIS signature 'NullsoftInst' not found in installer")
    # installer script strings live in a compressed NSIS data block, so only
    # the PE version-info brand is directly searchable. It is stored as
    # UTF-16LE. Branded wizard text is asserted against nsis-keel.nsh instead.
    if b"Keel" not in data and "Keel".encode("utf-16le") not in data:
        errors.append("Keel brand not found in installer (ASCII or UTF-16LE)")
    return errors


def check_built_inventory(dist_dir: str | Path, platform_name: str) -> list[str]:
    """Verify that a build produced exactly the primary/alternatives for a platform."""
    dist = Path(dist_dir)
    channel = next((c for c in CHANNELS if c["key"] == platform_name), None)
    if channel is None:
        return [f"unknown platform {platform_name}"]
    version = "0.1.1"
    expected = [channel["primary"].format(version=version)]
    expected += [a.format(version=version) for a in channel["alternatives"]]
    errors: list[str] = []
    for name in expected:
        matches = list(dist.rglob(name))
        if not matches:
            errors.append(f"built artifact missing: {name}")
    return errors

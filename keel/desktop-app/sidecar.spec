# PyInstaller spec for the Keel sidecar — produces dist/keel-sidecar/keel.exe
# Run from the repo root:
#   python -m PyInstaller desktop-app/sidecar.spec --noconfirm
# Output -> dist/keel-sidecar/keel.exe (picked up by
# electron-builder.extraResources -> resourcesPath/keel/keel.exe)

import glob
from pathlib import Path

SPEC_DIR = Path(SPEC).parent
ROOT = SPEC_DIR.resolve().parent

hiddenimports = sorted(
    "keel." + Path(p).relative_to(ROOT / "src" / "keel").with_suffix("").as_posix().replace("/", ".")
    for p in glob.glob(str(ROOT / "src" / "keel" / "**" / "*.py"), recursive=True)
    if Path(p).name != "__init__.py"
)
hiddenimports += ["keel.__main__", "keel.webapp", "keel.cli.main"]

# Bundled SKILL.md files must ship inside the sidecar, next to keel/skills.py
# in the extraction directory. skills.bundled_root() resolves this layout.
datas = [
    (str(ROOT / "resources" / "default-skills"), "keel/resources/default-skills"),
]

a = Analysis(
    [str(SPEC_DIR / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pylint", "mypy", "ruff", "_distutils_hack", "setuptools", "pip"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="keel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # REQUIRED: the bridge prints URL+token to stderr for Electron to parse
    icon=str(SPEC_DIR / "build" / "icon.ico"),
)

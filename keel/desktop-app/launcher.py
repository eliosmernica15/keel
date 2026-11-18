"""PyInstaller launcher — absolute imports, the way bundled binaries must start."""
from keel.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())

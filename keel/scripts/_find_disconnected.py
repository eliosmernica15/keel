"""Find runtime modules never imported by production code (accurate)."""
import re
from pathlib import Path

SRC = Path("src/keel")
modules = sorted(
    p.stem for p in SRC.glob("*.py")
    if p.stem not in ("__init__", "__main__"))

prod_text = "\n".join(
    p.read_text(encoding="utf-8", errors="replace")
    for p in SRC.rglob("*.py"))

disconnected = []
for name in modules:
    patterns = [
        rf"\bkeel\.{name}\b",
        rf"from\s+\.+\s*{name}\s+import",           # from ..tui import
        rf"from\s+\.+\s+import[^\n]*\b{name}\b",   # from .. import X
        rf"from\s+keel\.{name}\s+import",
        rf"import\s+keel\.{name}\b",
    ]
    if not any(re.search(p, prod_text) for p in patterns):
        disconnected.append(name)

print(f"Total: {len(modules)}  Disconnected: {len(disconnected)}")
for name in disconnected:
    print("  ", name)

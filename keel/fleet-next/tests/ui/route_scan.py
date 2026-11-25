"""Static route-vocabulary scanner for the Keel Python bridge.

Read-only: extracts the string literals that `keel/fleet/routes.py` and
`keel/webapp.py` compare against request path segments, plus literal route
paths. Emits JSON on stdout. No app files are imported or modified.

Used by verify-ui.mjs to build an evidence-backed backend route inventory.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEL = HERE.parents[2]  # .../keel
SRC = KEEL / "src" / "keel"

FILES = [SRC / "fleet" / "routes.py", SRC / "webapp.py"]

# parts[2] == "bots" / parts == ["api","fleet","bots"] / sub == "trust" etc.
CMP = re.compile(
    r"(?:\bparts\[(?P<idx>\d+)\]|\bparts|extra|sub|action|verb|path|segment)"
    r"\s*==\s*(?P<quote>['\"])(?P<val>[^'\"]+)(?P=quote)"
)
LIST_CMP = re.compile(r"\bparts\s*==\s*\[(?P<body>[^\]]*)\]")
STR = re.compile(r"(?P<quote>['\"])(?P<val>[^'\"]+)(?P=quote)")
PATH_LITERAL = re.compile(r"['\"]/(api/fleet|api/v2|api)/[^'\"]+['\"]")


def scan() -> dict:
    out: dict = {
        "files": [], "segment_literals": {}, "exact_lists": [], "path_literals": [],
        "get": {"segment_literals": {}, "exact_lists": []},
        "post": {"segment_literals": {}, "exact_lists": []},
    }
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        out["files"].append(str(f.relative_to(KEEL)).replace("\\", "/"))
        # Split routes.py into its GET and POST dispatch halves so the harness
        # can verify that a frontend POST actually has a backend POST handler.
        slices = {"all": text}
        if "def dispatch_post" in text:
            head, tail = text.split("def dispatch_post", 1)
            slices["get"] = head
            slices["post"] = "def dispatch_post" + tail
        for scope, body in slices.items():
            bucket_out = out[scope] if scope != "all" else out
            for m in CMP.finditer(body):
                idx = m.group("idx")
                val = m.group("val")
                bucket = f"parts[{idx}]" if idx else (m.group(0).split("==")[0].strip())
                bucket_out["segment_literals"].setdefault(bucket, set()).add(val)
            for m in LIST_CMP.finditer(body):
                vals = STR.findall(m.group("body"))
                bucket_out["exact_lists"].append([v[1] for v in vals])
        for m in PATH_LITERAL.finditer(text):
            out["path_literals"].append(m.group(0).strip("'\""))
    # JSON-ify sets
    for scope in ("all", "get", "post"):
        target = out if scope == "all" else out[scope]
        for k in list(target["segment_literals"]):
            target["segment_literals"][k] = sorted(set(target["segment_literals"][k]))
        target["exact_lists"] = [list(x) for x in {tuple(x) for x in target["exact_lists"]}]
    out["path_literals"] = sorted(set(out["path_literals"]))
    return out


if __name__ == "__main__":
    json.dump(scan(), sys.stdout, indent=2)
    print()

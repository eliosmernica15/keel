"""Verify the four previously reported fixes on this checkout (behavioral)."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
HERE = r"C:\Users\Admin\AppData\Local\Temp\opencode\stab-perf"
sys.path.insert(0, HERE)
from benchcommon import use_worktree
use_worktree()
SRC = r"C:\Users\Admin\.local\share\opencode\worktree\stab\perf\keel\src"

def child(code):
    p = subprocess.run([sys.executable, "-P", "-c",
        "import sys; sys.path.insert(0, r'%s')\n%s" % (SRC, code)],
        capture_output=True, text=True, cwd=HERE, timeout=120)
    if p.returncode != 0:
        return {"error": p.stderr.strip()[-500:]}
    return json.loads(p.stdout.strip().splitlines()[-1])

MODCHECK = ("import json,sys\n"
            "import keel.capabilities as caps\n"
            "loaded=[m for m in sys.modules if m.endswith('_backend')]\n"
            "caps.invoke('backend.describe', {'module':'e5_backend'})\n"
            "loaded_after=[m for m in sys.modules if m.endswith('_backend')]\n"
            "print(json.dumps({'backends_after_capabilities_import':sorted(loaded),\n"
            " 'backends_after_first_invoke':sorted(loaded_after),\n"
            " 'modules_after_import':len(sys.modules)}))")

out = {"lazy_hub_import": child(MODCHECK)}

HUBCHECK = ("import json,sys\n"
            "from keel import backend_hub as hub\n"
            "before=len([m for m in sys.modules if m.endswith('_backend')])\n"
            "hub.describe()\n"
            "after=len([m for m in sys.modules if m.endswith('_backend')])\n"
            "print(json.dumps({'backends_after_hub_import':before,\n"
            " 'backends_after_first_public_call':after,\n"
            " 'initialized':hub._INITIALIZED}))")
out["lazy_hub_init"] = child(HUBCHECK)

ASKCHECK = ("import json,sys,tempfile\n"
            "from pathlib import Path\n"
            "from keel.fleet.service import FleetStore\n"
            "d=Path(tempfile.mkdtemp())\n"
            "s=FleetStore(d/'a.db')\n"
            "b=s.create_bot(name='b',engine='echo')\n"
            "s.append_row(b['id'],'ask',{'status':'pending','question':'q'})\n"
            "n=s.expire_pending_asks()\n"
            "rows=s._conn.execute(\"SELECT body FROM rows WHERE kind='ask'\").fetchall()\n"
            "s.close()\n"
            "print(json.dumps({'expired':n,'ask_rows':[r['body'] for r in rows]}))")
out["ask_expiry_direct"] = child(ASKCHECK)

# Static confirmations with file:line (read only).
def line_of(path, needle):
    for i, text in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if needle in text:
            return i
    return None
root = Path(SRC) / "keel"
out["source_evidence"] = {
    "hub_lazy_call_line": line_of(root / "backend_hub.py", "_ensure_initialized()"),
    "bot_lock_comment_line": line_of(root / "fleet" / "service.py", "Slug selection and INSERT must be one atomic"),
    "ask_expiry_line": line_of(root / "fleet" / "service.py", "json_extract(body, '$.status') = 'pending'"),
    "backlog_line": line_of(root / "webapp.py", "request_queue_size = 128"),
}
print(json.dumps(out, indent=2))
with open(HERE + r"\result_fix_verify.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("wrote result_fix_verify.json")

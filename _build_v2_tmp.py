import subprocess
from pathlib import Path

BASE = Path(r"C:\Users\Admin\Desktop\Claude clone")
SRC = "578347425a20290961332abc3a4e9b3c2dcb2cd4"
V2WT = r"C:\Users\Admin\.local\share\opencode\worktree\production\v2"
V2BR = "release/backend-production-readiness-2026-11-24-v2"

def run(*a, cwd=BASE, check=True):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED {a}: {(r.stdout+r.stderr)[-800:]}")
    return r.stdout.strip()

# fresh worktree from main
run("git", "worktree", "add", "-b", V2BR, V2WT, "origin/main")
print("created v2 worktree from origin/main")

paths = run("git", "diff", "--name-only", "origin/main", SRC).splitlines()
allow = []
for p in paths:
    if p.startswith(("keel/site/", "keel/desktop-app/")):
        continue
    if p.startswith("keel/desktop/"):
        if p == "keel/desktop/src-tauri/Cargo.toml":
            allow.append(p)
        continue
    if p.startswith("probe/") or p.startswith(".probe/"):
        continue
    allow.append(p)

print("candidate paths:", len(paths), "in-scope:", len(allow))
for i in range(0, len(allow), 60):
    run("git", "checkout", SRC, "--", *allow, cwd=V2WT)
print("checked out in-scope backend paths")

# verify scope: no frontend paths
changed = run("git", "diff", "--name-only", "origin/main", cwd=V2WT).splitlines()
fe = [p for p in changed if p.startswith(("keel/site/", "keel/desktop-app/", "keel/desktop/"))]
print("frontend/desktop in v2:", fe)
print("HEAD:", run("git", "rev-parse", "HEAD", cwd=V2WT))

import subprocess, re

ids = [45519531326, 45519531394, 45519531412,
       45519531459, 45519531612, 45519543337]
for rid in ids:
    r = subprocess.run(["gh", "run", "view", str(rid), "--log-failed"],
                       capture_output=True, text=True)
    text = (r.stdout + r.stderr)
    lines = [l.strip() for l in text.splitlines()
             if re.search(r"error|FAIL|fatal|Failed|assert|No such file|Traceback|not found|mismatch", l, re.I)]
    print("=== RUN", rid, "===")
    for l in lines[:12]:
        print("  ", l[:220])

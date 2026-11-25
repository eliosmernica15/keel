import re
import subprocess
from pathlib import Path

base = Path(__file__).parent / "int" / "keel" / "tests"
files = [
    "test_backend_workflows.py", "test_backend_contracts.py",
    "test_backend_contracts_hardening.py", "test_backend_events.py",
    "test_backend_hub_integration.py", "test_backend_observability.py",
    "test_w7_x1_y5_d1_backend.py", "test_y4_d4_x7_backend.py",
]
for f in files:
    text = (base / f).read_text(encoding="utf-8")
    defs = set(re.findall(r"^\s*def (test_\w+)", text, re.M))
    p = subprocess.run(
        ["python", "-m", "pytest", str(base / f), "--collect-only", "-q"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    collected = set(re.findall(r"::(test_\w+)", p.stdout))
    missing = sorted(defs - collected)
    print(f, "defs=", len(defs), "collected=", len(collected),
          "missing=", missing[:10])

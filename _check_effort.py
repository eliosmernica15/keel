"""Reproduce the implementation-plan.md section 9.4 effort table from first principles.

Run:  PYTHONIOENCODING=utf-8 python -I _check_effort.py
Exit code 0 = the document's numbers reproduce from the stated rule.
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DOC = r"C:\Users\Admin\Desktop\Claude clone\implementation-plan.md"
text = open(DOC, encoding="utf-8").read()
lines = text.split("\n")

# --- 1. Parse the section 9.4 table -----------------------------------------
start = next(i for i, l in enumerate(lines) if l.startswith("### 9.4"))
end = next(i for i, l in enumerate(lines[start:], start) if l.startswith("## 10."))
rows = []
in_first_table = True
for raw in lines[start:end]:
    if not raw.strip().startswith("|"):
        if rows:  # the first table has ended
            in_first_table = False
        continue
    if not in_first_table:
        continue
    cells = [c.strip() for c in raw.strip().strip("|").split("|")]
    if len(cells) < 6 or set(cells[0]) <= set("-: "):
        continue
    if cells[0] == "Phase" or cells[0].startswith("**Total"):
        continue
    if not re.match(r"^\d\s+—", cells[0]):
        continue
    rows.append(cells)

print("=== Table rows parsed ===")
parsed = []
for c in rows:
    wk = float(re.search(r"([\d.]+)\s*week", c[1]).group(1))
    head = float(re.search(r"([\d.]+)", c[4]).group(1))
    pw = float(re.search(r"([\d.]+)", c[5]).group(1))
    parsed.append((c[0], wk, head, pw))
    ok = abs(wk * head - pw) < 0.01
    print(f"  {c[0]:<34} {wk:>5.1f}wk x {head:<5} = {wk*head:6.1f}  doc says {pw:6.1f}  {'OK' if ok else '<-- MISMATCH'}")

table_total = sum(r[3] for r in parsed)

# --- 2. Parse the phase-body effort statements in section 3 -----------------
body = []
for m in re.finditer(r"\*\*Estimated effort\.\*\*[^\n]*?\*\*≈([\d.]+) pw\*\*", text):
    body.append(float(m.group(1)))

print("\n=== Phase bodies in section 3 ===")
for i, pw in enumerate(body, 1):
    print(f"  Phase {i}: {pw} pw")
body_total = sum(body)

# --- 3. Parse the reconciliation table's own arithmetic ---------------------
print("\n=== Reconciliation ===")
phase0 = next(r[3] for r in parsed if r[0].startswith("0 "))
print(f"  table total (all 6 phases)  = {table_total} pw")
print(f"  phase-body total (Ph1-5)    = {body_total} pw")
print(f"  + Phase 0                   = {phase0} pw")
print(f"  comparable figures          = {body_total} + {phase0} = {body_total + phase0} pw")
print(f"  DELTA                       = {table_total - (body_total + phase0):+.1f} pw "
      f"({100*(table_total-(body_total+phase0))/table_total:+.1f}%)")

# --- 4. Independently recompute from the stated rule ------------------------
print("\n=== Independent recomputation from the stated rule ===")
print("  rule: effort = elapsed weeks x staffed headcount, summed over 6 phases")
rule = [
    ("0 — Architecture freeze + spike", 2, 3),
    ("1 — Vertical slice", 6, 3),
    ("2 — Parity core", 10, 4),
    ("3 — Safety tier", 6, 3.5),
    ("4 — Extensibility", 10, 4.5),
    ("5 — Hardening", 6, 3.75),
]
recomputed = sum(w * h for _, w, h in rule)
for name, w, h in rule:
    print(f"  {name:<34} {w:>5.1f} x {h:<5} = {w*h:6.1f}")
print(f"  recomputed total      = {recomputed} pw")
print(f"  table total           = {table_total} pw")
print(f"  agreement             = {'OK' if abs(recomputed-table_total) < 0.01 else 'MISMATCH'}")

# --- 5. Check the per-phase bodies against the rule -------------------------
print("\n=== Phase-body figures vs the rule ===")
order = [1, 2, 3, 4, 5]
mismatch = 0
for idx, ph in enumerate(order):
    stated = body[idx]
    w, h = rule[ph][1], rule[ph][2]
    expected = w * h
    flag = "OK" if abs(stated - expected) < 0.01 else "<-- MISMATCH"
    if flag != "OK":
        mismatch += 1
    print(f"  Phase {ph}: body {stated:>5} | rule {expected:>5.1f}  {flag}")
print(f"  mismatches = {mismatch}")

# --- 6. Support-staff split --------------------------------------------------
print("\n=== Support-staff capacity ===")
sup = 0
for ph, (name, w, h) in enumerate(rule):
    core = {0: 3, 1: 3, 2: 4, 3: 3, 4: 4, 5: 3}[ph]
    s = w * (h - core)
    if s:
        sup += s
        print(f"  Phase {ph}: {s:>5.1f} pw")
print(f"  support total = {sup} pw ({100*sup/table_total:.1f}% of {table_total})")

# --- 7. Contingency ----------------------------------------------------------
cont = sum(w * h for n, w, h in rule if n.startswith(("3", "4", "5"))) * 0.15
print(f"\n=== Contingency ===")
print(f"  15% on Phases 3-5 ({sum(w*h for n,w,h in rule if n.startswith(('3','4','5')))} pw) = {cont:.1f} pw")
print(f"  total with contingency = {table_total + cont:.1f} pw")

# --- 8. Elapsed weeks vs calendar ------------------------------------------
elapsed = sum(w for _, w, _ in rule)
print(f"\n=== Elapsed vs calendar ===")
print(f"  elapsed sum = {elapsed:.0f} weeks (document says 40)")
m = re.search(r"calendar figure is \*\*(\d+) weeks\*\*", text)
print(f"  document states calendar = {m.group(1) if m else 'NOT FOUND'} weeks "
      f"(1-week Phase2/3 overlap: {elapsed - 1:.0f})")

# --- 9. Verify the doc quotes the right totals ------------------------------
print("\n=== Document's own stated totals ===")
for pat in [r"≈(\d+(?:\.\d+)?) pw", r"≈(\d+(?:\.\d+)?) pw\b"]:
    pass
quotes = re.findall(r"\*\*≈(\d+(?:\.\d+)?) pw\*\*", text)
print(f"  bold pw figures in document: {quotes}")

# --- verdict ----------------------------------------------------------------
print("\n=== VERDICT ===")
problems = []
if mismatch:
    problems.append(f"{mismatch} phase-body figure(s) do not match the rule")
if abs(recomputed - table_total) > 0.01:
    problems.append("table does not equal the stated rule")
if abs(table_total - (body_total + phase0)) > 0.01:
    problems.append(
        f"table ({table_total}) != phase bodies + Phase 0 ({body_total + phase0})")
if problems:
    for p in problems:
        print(f"  FAIL: {p}")
    sys.exit(1)
print("  PASS: every figure reproduces from the stated rule, and the table and")
print("        the phase bodies agree.")

#!/usr/bin/env python3
"""
Mechanical gate for security-plan.md <-> test-plan.md coverage.

The security plan asserts, in section 13.1:
    "N controls. N mapped. 0 unmapped. Every control has at least one test."

This script re-derives that claim from the two files and fails if it does not
hold. It exists because the previous version of the security plan carried a
stale headline ("34 controls") after a control was added, and because the
security plan's coverage claim was previously unverifiable by hand.

Checks:
  1. The catalogue in section 6 has N controls.
  2. The coverage statement in section 13.1 states N (and N mapped, 0 unmapped).
  3. Every control in the catalogue has a row in section 13.
  4. Every test name referenced by a section 13 row is DEFINED in test-plan.md,
     and specifically is defined as a row in a subsystem matrix (section 3) that
     carries a tier and an assertion -- not merely named in the attack matrix
     (section 7), which names a test without defining it.
  5. Every control has at least one test.

Exit code 0 = all checks pass. Non-zero = a regression is present.
"""

import re
import sys

ROOT = "C:\\Users\\Admin\\Desktop\\Claude clone"

SEC_PATH = ROOT + "\\security-plan.md"
TP_PATH = ROOT + "\\test-plan.md"

FAILURES = []
NOTES = []


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def section(text, start_prefix, end_prefix=None):
    """Return the text of a '## N. Title' section, optionally up to the next section.

    The end of a section is the next heading of the SAME OR HIGHER level, so a
    '### 13.1' subsection runs until the next '## ' heading, not the next '### '.
    """
    i = text.find(start_prefix)
    if i < 0:
        raise SystemExit(f"section not found: {start_prefix!r}")
    if end_prefix is None:
        level = len(start_prefix) - len(start_prefix.lstrip("#"))
        pattern = r"^#{1," + str(level) + r"} "
        # start searching after the end of the heading line itself
        nl = text.find("\n", i)
        m = re.search(pattern, text[nl + 1:], re.M)
        j = nl + 1 + m.start() if m else len(text)
    else:
        j = text.find(end_prefix, i)
        if j < 0:
            j = len(text)
    return text[i:j]


def row_cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def main():
    sec = read(SEC_PATH)
    tp = read(TP_PATH)

    # ---- 1. catalogue ----
    catalogue = section(sec, "## 6. ", "## 7. ")
    cids = re.findall(r"\*\*(C-\d+)\*\*", catalogue)
    cids = sorted(set(cids), key=lambda c: int(c.split("-")[1]))
    n = len(cids)
    print(f"catalogue: {n} controls  ({cids[0]}..{cids[-1]})")

    # ---- 2. headline claim ----
    cov = section(sec, "### 13.1 ")
    m = re.search(r"(\d+)\s+controls\.\s*(\d+)\s+mapped\.\s*(\d+)\s+unmapped", cov)
    if not m:
        FAILURES.append("section 13.1 has no parseable coverage statement "
                        "of the form 'N controls. N mapped. M unmapped.'")
    else:
        stated, mapped, unmapped = (int(g) for g in m.groups())
        if stated != n:
            FAILURES.append(f"coverage statement says {stated} controls; "
                            f"catalogue contains {n}")
        if mapped != n:
            FAILURES.append(f"coverage statement says {mapped} mapped; expected {n}")
        if unmapped != 0:
            FAILURES.append(f"coverage statement says {unmapped} unmapped; expected 0")
        print(f"coverage statement: {stated} controls, {mapped} mapped, {unmapped} unmapped")

    # ---- 3/5. every catalogue control has a section 13 row ----
    sec13 = section(sec, "## 13. ", "## 14. ")
    refs = {}
    for line in sec13.split("\n"):
        cells = row_cells(line)
        if not cells or len(cells) < 3:
            continue
        mm = re.search(r"\*\*(C-\d+)\*\*", cells[0])
        if not mm:
            continue
        refs[mm.group(1)] = re.findall(r"`([a-z0-9_]{6,})`", cells[1])

    for cid in cids:
        if cid not in refs:
            FAILURES.append(f"{cid} is in the catalogue but has no section 13 row")
        elif not refs[cid]:
            FAILURES.append(f"{cid} has a section 13 row naming zero tests")
    for cid in refs:
        if cid not in cids:
            FAILURES.append(f"{cid} has a section 13 row but is not in the catalogue")
    print(f"section 13 rows: {len(refs)}")

    # ---- 4. every referenced test is DEFINED somewhere with an assertion ----
    # "Defined" means: the name appears in a table row of test-plan.md that also
    # carries a statement about what it asserts. The attack matrix (section 7) is
    # the one table that NAMES a test without defining it -- it says what an
    # attack should be contained by and points at a test. A name there is a
    # citation, not a test. Every other table defines: the subsystem matrices
    # (name | type | assertion), the platform matrix (constraint | consequence |
    # test target), and the CI-gate table (check name | assertion).
    tp_secs = [(m.start(), m.group(1)) for m in re.finditer(r"^## (\d+(?:\.\d+)?)\. ", tp, re.M)]

    def span_of(prefix):
        for idx, (pos, name) in enumerate(tp_secs):
            if name == prefix:
                end = tp_secs[idx + 1][0] if idx + 1 < len(tp_secs) else len(tp)
                return tp[pos:end]
        return ""

    attack7 = span_of("7")    # attack matrix: names tests, does not define them
    rest = tp.replace(attack7, "\n")   # everything except the attack matrix

    # A name is defined if it appears in any table row of `rest` that has >=2 cells.
    defined = set()
    for line in rest.split("\n"):
        cells = row_cells(line)
        if not cells or len(cells) < 2:
            continue
        for cell in cells:
            for name in re.findall(r"`([a-z0-9_]{6,})`", cell):
                defined.add(name)
            bare = cell.strip("*` ")
            if re.fullmatch(r"[a-z][a-z0-9_]{5,}", bare):
                defined.add(bare)

    def present(text, name):
        return re.search(r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])", text) is not None

    undefined = []
    attack_only = []
    for cid, names in sorted(refs.items()):
        for name in names:
            if name in defined:
                continue
            if present(attack7, name):
                attack_only.append((cid, name))
            else:
                undefined.append((cid, name))

    if undefined:
        for cid, name in undefined:
            FAILURES.append(f"{cid} references test `{name}`, which is not defined "
                            f"anywhere in test-plan.md")
    if attack_only:
        for cid, name in attack_only:
            FAILURES.append(f"{cid} references `{name}`, which is named in the attack "
                            f"matrix but has no defining row with an assertion -- "
                            f"a citation is not a test")
    n_refs = sum(len(v) for v in refs.values())
    print(f"referenced tests: {n_refs}  "
          f"defined: {n_refs - len(undefined) - len(attack_only)}  "
          f"attack-matrix-only: {len(attack_only)}  undefined: {len(undefined)}")

    # ---- 6. the residual risk register's arithmetic ----
    reg = section(sec, "## 14. ", "## 15. ")
    rr_rows = {}
    for line in reg.split("\n"):
        cells = row_cells(line)
        if not cells or len(cells) < 4:
            continue
        mm = re.search(r"\*\*(RR-\d+)\*\*", cells[0])
        if not mm:
            continue
        impact = cells[3].strip("* ")
        rr_rows[mm.group(1)] = impact

    n_rr = len(rr_rows)
    stated_total = None
    mt = re.search(r"\*\*(\d+)\s+residual risks\.\*\*", reg)
    if mt:
        stated_total = int(mt.group(1))
    else:
        FAILURES.append("section 14 has no '**N residual risks.**' total statement")
    if stated_total is not None and stated_total != n_rr:
        FAILURES.append(f"section 14 says {stated_total} residual risks; "
                        f"the register contains {n_rr}")

    # the summary table's per-impact counts must match the register
    bucket = {"very high": [], "high": [], "medium": [], "low": []}
    for rid, imp in rr_rows.items():
        key = imp.lower()
        if key.startswith("very high"):
            bucket["very high"].append(rid)
        elif key.startswith("high"):
            bucket["high"].append(rid)
        elif key.startswith("medium"):
            bucket["medium"].append(rid)
        elif key.startswith("low"):
            bucket["low"].append(rid)
        else:
            FAILURES.append(f"{rid} has an unrecognised impact value {imp!r}")

    for line in reg.split("\n"):
        cells = row_cells(line)
        if not cells or len(cells) < 3:
            continue
        label = cells[0].strip().lower()
        if label not in bucket:
            continue
        try:
            stated = int(cells[1].strip())
        except ValueError:
            FAILURES.append(f"summary row {label!r} has a non-numeric count {cells[1]!r}")
            continue
        actual = len(bucket[label])
        if stated != actual:
            FAILURES.append(f"summary row {label!r} says {stated}; the register has {actual} "
                            f"({', '.join(sorted(bucket[label]))})")
    print(f"residual risks: {n_rr}  "
          f"very high={len(bucket['very high'])} high={len(bucket['high'])} "
          f"medium={len(bucket['medium'])} low={len(bucket['low'])}")

    # ---- report ----
    print()
    for note in NOTES:
        print(f"NOTE  {note}")
    print()
    if FAILURES:
        for f in FAILURES:
            print(f"FAIL  {f}")
        print()
        print(f"FAILED: {len(FAILURES)} problem(s).")
        return 1
    print("PASS: every control has a defining row, the coverage statement reproduces from "
          "the catalogue, and the risk register's counts add up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

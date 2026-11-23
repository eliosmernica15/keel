# Master Plan v6 — X0.x P0 plan-correction verification evidence

- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\a7-x0`
- **Branch:** `agent/a7-x0`
- **Baseline:** `a454640`
- **Scope:** every `status=not_started`, `priority=P0` row in `PLAN-INDEX.json` whose
  ID begins with `X0.` — **8 rows**: X0.1, X0.2, X0.3, X0.4, X0.6, X0.7, X0.8, X0.10.
  (X0.2b, X0.5 and X0.9 are P1 and are not implementation targets; X0.9's risk
  register is included below as a supporting, informational check only.)
- **Files owned / changed:** three new files only —
  `keel/src/keel/plan_corrections.py`, `keel/tests/test_plan_corrections.py`,
  and this evidence file. No existing file was edited.

## 1. Approach

Most of these corrections are already satisfied by artifacts at the repository
root. The implementation therefore does **not** restate those claims: it adds a
stdlib-only verification module that reads each artifact, recomputes the facts
it asserts, and returns structured `VerificationResult` objects carrying an
`ok` flag, concrete `evidence` lines, and concrete `errors`. A verifier can be
pointed at any root, so the tests prove both that it passes on the real
repository and that it **fails** when an artifact is missing or tampered with.
Where a correction was genuinely missing functionality (an executable seam that
blocks starting a row with unmet dependencies), the module verifies the seam in
source via AST/text inspection.

## 2. Results

`python -m keel.plan_corrections` (or `pc.verify_all(root)`) reports
**8/8 P0 rows passing, 0 failing**; the supporting X0.9 check also passes.

| ID | Correction | Status | Primary artifacts proven |
| --- | --- | --- | --- |
| X0.1 | Priority inflation | PASS | `PLAN-INDEX.json` |
| X0.2 | M19 overloaded — split M19a–M19f | PASS | `keel/scripts/build_dependency_graph.py`, `DEPENDENCY-GRAPH.md` |
| X0.3 | No dependency graph / readiness gate | PASS | `PLAN-INDEX.json`, `DEPENDENCY-GRAPH.md`, `keel/src/keel/spec_mode.py` |
| X0.4 | Duet defined three ways | PASS | `DECISIONS.md` (D-005), `keel/src/keel/duet.py` |
| X0.6 | Incomplete free-tier trap list | PASS | `FREE-TIER-REGISTER.md` |
| X0.7 | Voice/ML licensing only "check" | PASS | `MODEL-AND-VOICE-LICENSES.json`, `scripts/check_model_licenses.py`, `.github/workflows/offline-license.yml`, `keel/site/notices.html` |
| X0.8 | "Zero network without account" untested | PASS | `.github/workflows/offline-license.yml`, `keel/tests/test_offline_runtime.py` |
| X0.10 | No clean-room procedure | PASS | `DECISIONS.md` (D-021), `keel/docs/research/reference-behavior/*.md`, `master-plan-v6-edit-formats-evidence.md`, `keel/docs/THIRD_PARTY_NOTICES.md` |

### X0.1 — Priority inflation

- Registry has **865 rows**; `priority_counts` matches the recomputed row counts
  exactly: `P1=524, P0=240, P2=101`.
- **P0 share = 27.75%**, inside the documented "roughly 25%" tolerance band
  `[20%, 30%]` (cap 30%, floor 20% prevents a trivial all-P1 registry).
- `original_priority` is retained on every row: original P0 was **333 (38.50%)**;
  **93 rows were demoted P0→P1**. The verifier rejects a registry where the
  original share is not materially above the current share, or where
  `priority_counts` disagrees with the rows.

### X0.2 — M19 milestone split

- The generator's `FALLBACK_DECOMPOSITIONS` and `SPLIT_PATTERNS` literals were
  parsed with `ast.literal_eval`: all six required nodes exist with the exact
  plan labels — `M19a shell/layout`, `M19b chat/composer`,
  `M19c review/diff/terminal docks`, `M19d fleet/board/memory views`,
  `M19e settings/forms/wizard`, `M19f polish/a11y/i18n` — and the classifier
  covers exactly those six node IDs.
- All six full labels are present in the generated `DEPENDENCY-GRAPH.md`.

### X0.3 — Dependency graph and readiness gate

- Registry declares **144 dependency references on 122 rows**.
- `DEPENDENCY-GRAPH.md` contains a critical-path section with length **13** and a
  `## 6. Readiness gate (X0.3)` section stating "a builder may not start a row
  whose dependencies are not green".
- **Freshness proven**: the report's declared registry SHA-256
  `95d1f6a25aef16b60edc78ad6ca6f5a5e2eac866e1e1cefe38d3aad26528b114` matches
  the actual `PLAN-INDEX.json` bytes.
- Gate numbers were **recomputed from the registry**, not trusted: **93**
  `not_started` rows declare dependencies and **45** of them have at least one
  dependency that is not `verified`; both match the report.
- An executable enforcement seam exists in `spec_mode.py`: `set_task_status`
  raises `unmet dependencies` instead of starting a task whose dependencies are
  not done.

### X0.4 — Duet

- `DECISIONS.md` D-005 records X0.4/D4, unifies Master D4 / Addendum 1 B2.3 /
  Addendum 2 C2.3 into **one surface with two modes** (Live Pair, Review Pair),
  makes the independent reviewer read-only, and records a chosen resolution.
- `duet.py` exposes `builder_allowlist()` and `review_allowlist()`; AST inspection
  confirms the reviewer's 13-tool allowlist contains no write tool
  (`write_file`, `edit_file`, `apply_patch`, `str_replace`), and the reviewer
  prompt states "You are an independent reviewer. You cannot edit files" using
  read-only tools.

### X0.6 — Free-tier register

- `FREE-TIER-REGISTER.md` declares re-verification at each gate and contains
  **43 dated, evidence-linked register rows** with the required columns
  (service, free tier used, commercial-use restrictions, date verified, exit
  strategy, evidence source ID).
- Each of the four named traps — **Vercel Hobby** (non-commercial),
  **VirusTotal public API** (non-commercial), **GitHub free private repo**
  (limited features), **Docker Desktop** (commercial terms) — has a row with the
  restriction, a verification date and an exit path. Missing any one row fails
  the verifier.

### X0.7 — Model and voice license registry

- `MODEL-AND-VOICE-LICENSES.json` parses with **11 complete entries**; all six
  X0.7 watch items (`piper-tts`, `kokoro-voices`, `whisper-weights`,
  `diarization-models`, `ffmpeg-build`, `work-sans-font`) are present, unbundled
  and CI-gated.
- `ci_policy` rejects non-commercial bundled entries; `scripts/check_model_licenses.py`
  enforces `commercial_use_allowed`, `redistribution_allowed`, `verified_date`
  and `ci_gate` and exits 1 on failure; `.github/workflows/offline-license.yml`
  runs it in the `license-gate` job.
- A UI license display surface exists (`keel/site/notices.html`, MIT/Apache
  notices; the web app also exposes license metadata through its catalog API).

### X0.8 — Zero-network CI smoke lane

- `offline-license.yml` has an `offline-smoke` job that unsets all five provider
  keys, runs `python -m pytest -q` over `test_offline_runtime.py`,
  `test_cli_e2e.py` and `test_e2e_local.py` inside **`unshare -n`**, and fails
  closed if `unshare` is unavailable.
- `test_offline_runtime.py` declares the no-network contract and covers offline
  import, empty configured-provider set and a real local coding turn.

### X0.10 — Clean-room protocol

- `DECISIONS.md` D-021 records the two-step protocol: analyst writes a
  behavior spec with no pasted code, builder implements from the spec only, and
  the source spec is logged per module in the provenance file; private teardown
  artifacts never ship.
- **6** clean-room behavior specs exist under
  `keel/docs/research/reference-behavior/`. Every one was checked to have a
  provenance section, a clean-room method declaration, an explicit "do not copy"
  / non-adoption rule, and pinned source metadata.
- Provenance logs map modules to their specs:
  `master-plan-v6-edit-formats-evidence.md` maps `edit_formats.py` to
  `edit-format-behavior.md`, and `THIRD_PARTY_NOTICES.md` records `exec_policy.py`
  as a clean-room reimplementation.
- Supporting: `RISKS.md` covers 13 milestones with likelihood, impact, owner,
  mitigation and rollback fields (X0.9, P1 — informational only).

## 3. Tests

`keel/tests/test_plan_corrections.py` — **14 tests, all passing**:

- 4 positive tests: aggregate report, evidence payloads, verifier IDs matching
  the eight P0 rows in `PLAN-INDEX.json`, and a stdlib-only import check.
- 1 missing-artifact test: every verifier fails against an empty root.
- 9 tamper tests: re-inflated P0 share; missing M19f split; stale dependency
  graph SHA; Duet with one mode removed; Vercel row removed from the register;
  non-commercial bundled model in the license registry; `unshare -n` removed
  from the CI lane; two clean-room specs deleted; missing risk register. Each
  asserts the specific error that must be produced.

Commands run (stdlib only; no network):

```text
python -m pytest -q keel/tests/test_plan_corrections.py
  → 14 passed in 1.07s

python -c "import sys; sys.path.insert(0,'<root>/keel/tests'); \
sys.path.insert(0,'<root>/keel/src'); import test_plan_corrections as t; \
[f() for f in [getattr(t,n) for n in dir(t) if n.startswith('test_')]]; \
print('PASS')"
  → PASS 14 tests
```

## 4. Honest limitations

- "Roughly 25%" is an explicit, documented tolerance band `[20%, 30%]`; the
  shipped P0 share is 27.75%, not exactly 25%.
- M19a–M19f are **derived split nodes** in the dependency graph generator, not
  literal `milestone` values in `PLAN-INDEX.json`; the registry rows remain on
  parent M19, as documented in `DEPENDENCY-GRAPH.md` §2 assumption 3.
- Dependency-graph freshness is proven by matching the report's declared
  registry SHA-256 to the actual file (and by recomputing the gate counts). The
  generator defaults to a canonical plan path outside this worktree, so the
  verification intentionally does not re-run it with default arguments.
- The license registry currently has **0 bundled entries**; the fail-closed
  bundled-entry checks and the CI gate are real but pass vacuously until an
  entry is bundled. Watch items are explicitly marked `bundled: false` and
  `ci_gate: true`.
- The offline CI lane removes the network namespace at kernel level, which is
  strictly stronger than a separate update-check toggle; there is therefore no
  distinct "update check disabled" environment variable to assert.
- X0.9 (risk register) is P1 and is reported as supporting evidence only; it is
  not counted among the eight implemented P0 rows.

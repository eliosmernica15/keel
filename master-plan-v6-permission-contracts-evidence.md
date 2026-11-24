# Master Plan v6 - Permission Contracts Evidence (W3.x P0, Agent A4)

- **Branch:** `agent/a4-permissions`
- **Baseline:** `fa062a4c441fbe5eb683353957e94f79e7f789bf`
- **Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\addenda\permissions`
- **Scope:** 11 W3.x P0 permission-engine feature IDs from the 865-row `PLAN-INDEX.json` registry.
- **Files owned (created only):** `keel/src/keel/permission_contracts.py`, `keel/tests/test_permission_contracts.py`, this evidence file.

> Constraint honored: `permissions.py`, `exec_policy.py`, `policy_enforcement.py`,
> `shell_ast.py` and every other existing source/test file were **read only**.
> The new module is additive; it does not import, patch or reorder the live
> evaluator at import time. `git diff --name-only` against the baseline lists
> only the three files above.

---

## 1. CRITICAL SEMANTIC DECISION - W3.2 last-match vs Keel first-match

The source plan (W3.2 / Conflict C-1 from Addendum 5) asks for OpenCode-style
"last matching rule wins (broad first, exceptions after)". Keel's **approved**
semantics are FIRST-MATCH in the order `deny -> ask -> allow -> mode policy`,
pinned by **DECISIONS.md D-001** (chosen resolution: preserve Keel first-match;
the C-1 recommendation to switch to last-match is formally rejected).

**Decision recorded here:** the live permission precedence is **unchanged**.
There is no code path from this work into `keel.permissions.evaluate` that
alters rule ordering.

- `evaluate_rules_keel(...)` is the authoritative contract: first match,
  `deny -> ask -> allow -> default-ask`.
- `evaluate_rules_last_match(...)` is a **non-authoritative reference adapter**
  that MODELS last-match behaviour for analysis and the policy simulator only.
  It is marked in four independent ways so it cannot be mistaken for the live
  evaluator:
  1. module and function docstrings state "NON-AUTHORITATIVE";
  2. `LAST_MATCH_IS_AUTHORITATIVE = False` vs `KEEL_IS_AUTHORITATIVE = True`;
  3. every adapter `Evaluation` carries `authoritative=False` and exposes the
     `winner` rule for the simulator display;
  4. `simulate()` reports both outcomes side by side with
     `AUTHORITATIVE_EVALUATOR = "keel.permissions.evaluate"`.
- A concrete divergence is pinned by test: with rules
  `[deny("rm *"), allow("*")]` on resource `rm -rf /`, Keel returns **deny**
  while the adapter returns **allow** (the latter would be a permission-order
  confusion defect if adopted live).
- `test_w32_live_permissions_evaluator_still_first_match` calls the shipped
  `keel.permissions.evaluate` directly (bypass mode included) and asserts the
  scoped deny still wins over a later bare allow — an integration guard against
  any future drift.

Changing live precedence to last-match would be a **critical defect**; this
work deliberately does not do it.

---

## 2. IDs implemented

| ID | Contract | Public API | Key tests |
|----|----------|-----------|-----------|
| W3.1 | Rule `{action, resource, effect}`; effects allow/deny/ask; no match -> ask | `Rule`, `Effect`, `Evaluation`, `evaluate_rules_keel` | `test_w31_*` |
| W3.2 | First-match authoritative vs last-match adapter; winning rule in simulator | `evaluate_rules_last_match`, `simulate`, `KEEL_IS_AUTHORITATIVE`, `LAST_MATCH_IS_AUTHORITATIVE`, `AUTHORITATIVE_EVALUATOR`, `SIMULATOR_NOTE`, `select_matching_rules` | `test_w32_*` (incl. live-precedence guard) |
| W3.3 | `*`/`?`, whole-value, backslash normalization, Windows case, shell trailing `*` | `wildcard_match` | `test_w33_*` (parametrized) |
| W3.4 | Any deny -> deny, else any ask -> ask, else allow | `ResourceCheck`, `evaluate_multi` | `test_w34_*` |
| W3.6 | `external_directory` containment, no traversal, Trusted-only allow | `path_is_within`, `check_external_directory` | `test_w36_*` |
| W3.7 | Shell scanner for bash/zsh/sh/powershell; subcommands + `cd` targets; fail closed | `ShellScan`, `ScannedCommand`, `ScannerError`, `scan_shell_command`, `scan_to_checks` | `test_w37_*` |
| W3.8 | Default allow, ask on `.env`/`.env.*` reads except `.env.example`, key files | `is_sensitive_env_read`, `default_policy_rules`, `default_policy_decision` | `test_w38_*` (parametrized) |
| W3.9 | once/always/reject; project-scoped pattern persistence; deny never overridden; tool-proposed only | `ApprovalReply`, `ApprovalRequest`, `ApprovalOutcome`, `ApprovalStore` | `test_w39_*` |
| W3.10 | Policy hard-deny floor; policy never grants; managed overrides project | `apply_policy_floor`, `apply_policy_floors` | `test_w310_*` |
| W3.12 | Non-interactive: no responder -> deny; configured deny enforced; `--approve=never\|rules-only` | `resolve_noninteractive`, `APPROVE_NEVER`, `APPROVE_RULES_ONLY` | `test_w312_*` |
| W3.13 | Docs warning: shell has full host authority; allowlist-style preset | `SHELL_AUTHORITY_WARNING`, `CAUTIOUS_PRESET` | `test_w313_*` |

**All 11 IDs implemented. 66 tests, all passing.**

---

## 3. Contract summary

- **Typed results, no silent mutation:** all dataclasses are frozen; every
  evaluation returns a new `Evaluation`. `apply_policy_floor` keeps the
  authoritative decision's metadata and never adopts a policy "grant".
- **W3.3 matcher:** `*` matches any chars including `/`, `?` matches exactly
  one char, both ends anchored, backslashes normalized to `/` in pattern and
  value, case-insensitive by default on Windows (`os.name == "nt"`, overridable
  via `case_sensitive=`), and a shell pattern ending in `" *"` also matches the
  bare command (`npm run *` matches `npm run`).
- **W3.6 containment:** both paths resolved to canonical absolute paths before
  comparison, so `root/../outside` fails; `os.path.normcase` gives
  case-insensitive Windows semantics; sibling-prefix paths (`proj-evil` vs
  `proj`) are rejected via `os.path.commonpath`.
- **W3.7 scanner seam:** every lexing/wrapper/classification decision is made
  by `keel.shell_ast.analyze`; this module maps zsh -> posix, extracts
  `cd`/`Set-Location` targets (including `-Path X` and `-Path:X` forms), and
  returns `ShellScan(ok=False, error=...)` on `Decline`. `scan_to_checks()`
  returns no checks for a failed scan, so "cannot analyze" can never allow.
  `ScannedCommand` mirrors `shell_ast.Command`'s
  `(name, canonical, operations, args, extent)` shape.
- **W3.9 store:** JSON under `state_root/permission-approvals/<sha256(project)[:16]>.json`
  (hashed project id prevents filename traversal); per-instance `RLock` plus a
  cross-process `O_EXCL` lock file with stale-lock recovery make concurrent
  writes lossless; atomic temp-file + `os.replace` writes; corrupt files fail
  closed (no saved allows); configured deny rules are a hard floor both for
  decisions and for `always` pattern persistence.
- **W3.10/W3.12:** `allow(0) < ask(1) < deny(2)` restrictiveness ladder; floor
  only restricts; no interactive responder -> `deny` ("fail closed");
  `rules-only` does not auto-approve unanswered asks or saved patterns.

---

## 4. Integration seams for the lead (not wired in, by design)

1. **Live evaluator precedence** — do nothing. `keel.permissions.evaluate`
   stays first-match. To adopt the richer `Rule` shape later, translate
   `permission_contracts.Rule` into `permissions.Rule` via `parse_rules` in a
   caller that owns `permissions.py`; never substitute the last-match adapter.
2. **Matcher adoption (W3.3)** — `wildcard_match` is a superset of
   `permissions.path_glob_match`; replacing the live matcher is a separate,
   reviewed change because it widens `*` across `/`.
3. **External-directory pre-check (W3.6)** — call `check_external_directory`
   before read/edit rule evaluation in the tool executor. Tier-2 protected-path
   checks in `policy_enforcement` must stay above and independent of it.
4. **Shell scan (W3.7)** — call `scan_shell_command` from the Tier-2 command
   analyzer, then feed `scan_to_checks()` results into the existing rule
   evaluator. On `scan.ok is False`, refuse / force ask; never allow. No changes
   to `shell_ast.py` are needed.
5. **Default policy (W3.8)** — use `default_policy_decision` as the base layer.
   The `.env.example` exception is intentionally a function, not a rule list,
   because ASK is evaluated before ALLOW under first-match.
6. **Approvals (W3.9/W3.12)** — construct one `ApprovalStore(state_root,
   project_id)` per project; pass configured deny rules into every `decide()`
   call; pass `non_interactive=True` from `keel run`. Wire `--approve` to
   `resolve_noninteractive(..., approve_mode=...)`. Approval UI buttons map to
   `ApprovalReply.ONCE/ALWAYS/REJECT`; `reject_pending(session_id, feedback)`
   implements "rejects every other pending request" plus model feedback.
7. **Policies (W3.10)** — after rules and saved approvals, apply
   `apply_policy_floors(decision, project_policy, managed_policy)` with the
   managed/global policy last so it overrides project config by restriction.

---

## 5. Verification

Command (from worktree root):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_permission_contracts.py']))"
```

Result: **66 passed in 2.53s**.

Regression check (read-only, existing suites):

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_shell_ast.py','keel/tests/test_policy_bypass_regression.py']))"
```

Result: **130 passed in 22.15s** — live scanner and policy-bypass semantics intact.

### Adversarial coverage (all in the new test file)

- deny cannot become allow (W3.2 adapter divergence, W3.9 always-with-deny,
  W3.10 floor, W3.12, live-evaluator guard);
- traversal and sibling-prefix paths (W3.6);
- `.env.example` exception (W3.8, including nested `config/.env.example`);
- PowerShell syntax including `Set-Location -Path` and dynamic-command
  refusal (W3.7);
- approval persistence across store restart and project isolation (W3.9);
- 12 concurrent approval writes across distinct store instances using a
  cross-process file lock (W3.9);
- corrupt approval file fails closed (W3.9).

## 6. Known limitations

- PowerShell parsing relies on the host's real `pwsh`/`powershell` parser via
  `shell_ast`; when unavailable the scan fails closed with an `error` rather
  than allowing. zsh uses the POSIX grammar (no zsh-specific grammar exists in
  `shell_ast`).
- The last-match adapter is intentionally analysis-only; it is not a
  drop-in evaluator and must not be used for live permission decisions.
- Approval persistence is local JSON (file-locked), not a database; it models
  the project-scoped contract without changing any existing storage layer.

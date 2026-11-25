# Builder process — D6.2, D6.14, D6.18, D6.20, D6.21

Owner: Agent H (documentation / governance). Audited 2026-11-24 against the
`keel-frontend-worktree` round evidence. These are **human/agent workflow
rules**, deliberately not simulated as runtime features: the earlier backend
evidence (`master-plan-v6-d6-backend-evidence.md`) records the same rows as
EXCLUDED because there is no deterministic runtime predicate for a review or
reading discipline. This document is the artifact for those rows.

## D6.2 — Plugins, not loop changes

- **Rule.** New behaviour attaches to a documented extension point. Changing
  the loop itself is allowed only when `architecture.md` is updated in the same
  change, with the new seam/ordering described.
- **Actual extension points in this tree** (read before adding code):
  - `keel/src/keel/plugin_contracts.py` — plugin parts and reversible registration.
  - `keel/src/keel/capability_seams.py` — definition / provider / consumer seams.
  - `keel/src/keel/hooks.py`, `keel/src/keel/invariant_contracts.py` — hooks and
    scope-owned registrations with disposal.
  - `keel/src/keel/tools/registry.py`, `keel/src/keel/providers/registry.py` —
    tool and provider registries.
- **This round's evidence.** The frontend workstream added surfaces, settings
  cards and E2E coverage without modifying the Python loop; see the commit
  subjects `feat(onboarding)`, `feat(settings)`, `feat(duet)` and the E2E configs
  in `keel/fleet-next/tests/features/`. No loop-order change was claimed.

## D6.14 — Tests describe behaviour, not "correctness"

- **Rule.** Name and assert an observable behaviour. If behaviour changes,
  change its test in the same batch and say why in the commit/evidence.
- **Evidence from this round.**
  - `keel/docs/UI-TEST-MATRIX.md` records behaviour-named E2E assertions such as
    "Fleet board columns are the bridge's real task statuses" and honest-state
    checks for unavailable hierarchy/cost data.
  - `keel/docs/UI-DEFECT-LOG.md` §6 and commit `e038550 test(ui): add final QA
    evidence and fix search Escape and error copy` show an obsolete behaviour
    (Escape bound only to the search input) changed together with its test and
    a recorded re-test, rather than a green suite with stale assertions.
  - API defect QA-002 was re-tested by deriving the expected method from the
    backend dispatcher (`API-03` guard), not by relaxing the assertion.

## D6.18 — Prefer maintained dependencies over hand-rolling

- **Rule.** Prefer a maintained library when it deletes owned code *and its
  tests*. Every new library must carry a license / security / maintenance /
  packaging note in `THIRD_PARTY_NOTICES.md` before it lands.
- **Evidence.** `THIRD_PARTY_NOTICES.md` and
  `keel/docs/DEPENDENCY-LICENSE-INVENTORY.md` audit the actual runtime choices
  (`cryptography`, `keyring`, `Pillow`, `tzdata`, Electron) and the browser-test
  runner `@playwright/test` 1.65.1 (Apache-2.0, dev-only). The E2E workstream
  used the existing Playwright dependency instead of a bespoke browser driver
  (`keel/docs/UI-E2E-GUIDE.md` §1). No new runtime dependency was added by the
  frontend round. Build-only tools (PyInstaller, electron-builder, setuptools)
  are recorded separately and are not shipped runtime code.

## D6.20 — Run only relevant checks locally

- **Rule.** Match the check to the change; CI owns exhaustive coverage; do not
  re-run a passing check merely to decorate a commit or push.
- **Evidence from this round** (all commands and results are in
  `keel/docs/UI-TEST-MATRIX.md`, not asserted from memory):
  - TypeScript: `npx tsc --noEmit --incremental false` → exit 0.
  - Production build: `npx next build` with isolated `KEEL_DIST_DIR` → 5/5 pages.
  - Contract guards: `node tests/ui/verify-ui.mjs` → `{"info":1,"pass":14,"skipped":4}`.
  - Focused E2E: `--grep` / single-spec re-runs were used to distinguish real
    defects from shared-bridge 504 noise instead of repeating the full 140-test
    suite for each candidate cause.
  - a11y: `npx playwright test --config tests/a11y/playwright.a11y.config.ts`
    with reuse flag → 12 pass / 0 fail in the final run.
  - Python: `python -m pytest -q` is the full-suite gate; the UI workstream
    recorded that it changed no Python files rather than claiming a Python
    result it had not run.

## D6.21 — PR hygiene

- **Rule.** One `kind/*` label and every material `area/*` label; rewrites use
  `--force-with-lease` only; PR descriptions follow the template in
  `keel/docs/internal/PR-DESCRIPTION-TEMPLATE.md`.
- **Evidence and honest gap.** Commit subjects in this branch follow a
  conventional `kind(scope): summary` form (`feat`, `fix`, `test`, `docs`,
  `a11y`, `perf`), and `.githooks/pre-push` blocks direct pushes to `main` and
  runs a fail-closed gitleaks scan as the local compensating control for the
  blocked C11.1/C11.2 owner gates. There is **no `.github/PULL_REQUEST_TEMPLATE.md`
  and no label configuration file in this tree** (verified by file search on
  2026-11-24), so the template/label half of D6.21 is a documented convention,
  not an enforced GitHub setting. Wiring it up is an owner/lead action; this
  round did not touch GitHub settings or push anything.

## Cross-references

- D6.17 durable decision notes: `keel/docs/internal/AGENT-NOTES.md`.
- D6.23 defensive-patterns reading: `keel/docs/internal/DEFENSIVE-PATTERNS.md`.

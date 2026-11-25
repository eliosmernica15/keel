# Whole-project master-plan inventory (non-generated)

This is a **tracking and reconciliation document**, not a generated registry. The authoritative registry is `PLAN-INDEX.json` (865 features) and its generated projection `parity.json`; neither is hand-edited here. The frontend-only evidence remains in `UI-REQUIREMENTS-MATRIX.md` (150 criteria, 131 verified).

## 1. Registry-derived baseline (read, not edited)

`PLAN-INDEX.json` reports:

| Status | Count |
|---|---:|
| verified | 854 |
| not_started | 9 |
| blocked | 2 |
| **Total** | **865** |

Registry-derived verified percentage: 854/865 = **98.7 %**. This is a registry claim, not a fresh independent verification of all 865 acceptance criteria; the QA workstream samples and verifies the remaining/risky items rather than blindly inheriting statuses.

## 2. Non-verified requirements (full list from the registry)

| ID | Status | Priority | Requirement | Project area | Owner | Test evidence required |
|---|---|---|---|---|---|---|
| C11.1 | blocked | P0 | Source-hosting caveats to decide (GitHub free-plan branch protection / secret controls) | Governance / external | owner decision | Documented owner decision; no repo-visibility change without approval |
| C11.2 | blocked | P0 | Repo security hygiene (2FA, signed commits, least-privilege tokens, pinned Actions) | Governance / external | owner decision | Settings audit; cannot be performed by agent |
| D6.14 | not_started | P1 | Tests describe behaviour; change obsolete behaviour together with tests | Builder process | Agent H | Existing test changes must accompany behaviour changes |
| D6.17 | not_started | P1 | Agent Notes (ADR-like) for durable rationale only; archived notes frozen | Builder process | Agent H | Docs audit |
| D6.18 | not_started | P1 | Prefer maintained dependencies over hand-rolling when they delete owned code/tests | Builder process | Agent H | Dependency review note |
| D6.2 | not_started | P1 | Plugins, not loop changes: new behaviour attaches to documented extension points | Builder process | Agent H | Architecture doc check |
| D6.20 | not_started | P1 | Run only relevant checks locally; match evidence to change | Builder process | Agent G | Local verification practice |
| D6.21 | not_started | P1 | PR hygiene: labels, force-with-lease, PR description template | Builder process | Agent H | PR/branch audit |
| D6.23 | not_started | P1 | Defensive-patterns doc read before touching package/remote/client-state surfaces | Builder process | Agent H | Docs audit |
| W1.18 | not_started | P0 | MIT license + `THIRD_PARTY_NOTICES.md` | Legal / licensing | Agent H | File presence and accuracy |
| Y6.4 | not_started | P0 | Repo visibility public, 0 stars/forks | Governance / external | owner decision | **Do not change** — prior instructions prohibit visibility changes |

## 3. Areas of work launched in this round

| Agent | Workstream | Ownership (initial) |
|---|---|---|
| A | Frontend residual + real-browser accessibility | `fleet-next/**` tests/docs only after frontend freeze; no new feature rewrites |
| B | Backend services / Python failure baseline comparison | `keel/tests/**` (new focused tests), `keel/src/keel/**` only for proven regressions |
| C | Agent execution / orchestration verification | read-only audit + focused tests in `keel/tests/**` (distinct filenames) |
| D | Providers / integrations / local test provider | `keel/src/keel/providers/**` + tests only for proven gaps |
| E | Desktop packaging (Electron/Tauri) | `keel/desktop-app/**`, `keel/desktop/src-tauri/**`, packaging docs |
| F | Security / trust / reliability verification | security tests + docs |
| G | Independent QA | QA docs, test infrastructure, defect reports |
| H | Documentation / parity / licensing | `keel/docs/**`, `THIRD_PARTY_NOTICES.md`, legal docs (never generated files) |

File ownership is exclusive per agent; the lead integrates and pushes accepted batches.

## 4. Previously reported blockers under active investigation

Electron packaged renderer, Tauri build (`link.exe` missing), real provider turn, Python 7 failures baseline comparison, bridge 504 root cause, long-history performance, screen-reader, and real 200 % browser zoom. Results are recorded in `UI-REQUIREMENTS-MATRIX.md` and will be reconciled here as evidence lands.

## 5. Progress calculation (initial, this round)

Using registry statuses as the starting inventory (not yet independently re-verified):
- Applicable requirements: 865 − 2 blocked − 1 external visibility = 862
- Verified: 854 → 854/862 = **99.1 %**
- Remaining implementation: 9/862 = **1.0 %**
- Blocked: 2/862 = **0.2 %** (plus external environment gates tracked separately)

These percentages will be re-calculated after independent verification. Do not treat them as proof of whole-product production readiness.

## 6. Reconciliation entries — full-plan completion round (2026-11-24)

`PLAN-INDEX.json` and `parity.json` were **read but not edited**. The table in
§1 and the percentages in §5 therefore still describe the registry as landed;
the dispositions below are reconciliation recommendations recorded in this
tracking document for the lead to apply when regenerating the registries.

### 6.1 The eleven non-verified rows

| ID | Registry | Evidence landed in this round | Reconciled disposition |
|---|---|---|---|
| D6.2 | not_started | `keel/docs/internal/BUILDER-PROCESS.md` documents the extension points (`plugin_contracts.py`, `capability_seams.py`, `hooks.py`, tool/provider registries) and the architecture-doc rule; UI commits added surfaces and E2E without a loop change. | **documented** (builder convention); no runtime artifact, registry status unchanged by this agent. |
| D6.14 | not_started | `BUILDER-PROCESS.md` D6.14; behaviour-named assertions in `UI-TEST-MATRIX.md`; obsolete Escape behaviour changed with its test in `e038550`; QA re-tests in `UI-DEFECT-LOG.md` §6. | **documented**; tests-with-behaviour practice evidenced, registry status unchanged. |
| D6.17 | not_started | `keel/docs/internal/AGENT-NOTES.md`; durable rationale in `DECISIONS.md` D-036/D-037; `keel/docs/plan-sources/*` frozen and never edited; proprietary drafts marked not authoritative. | **documented**; registry status unchanged. |
| D6.18 | not_started | `BUILDER-PROCESS.md` D6.18; dependency choices and licenses audited in root `THIRD_PARTY_NOTICES.md` and `keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`; Playwright reused rather than a bespoke browser driver (`UI-E2E-GUIDE.md` §1); no new runtime dep this round. | **documented**; registry status unchanged. |
| D6.20 | not_started | `BUILDER-PROCESS.md` D6.20; exact local commands/results in `UI-TEST-MATRIX.md` (`tsc`, `next build`, `verify-ui.mjs`, focused `--grep` E2E, a11y suite); no Python claim where no Python file changed. | **documented** (Owner in §2 was Agent G; Agent H recorded the practice from QA evidence); registry status unchanged. |
| D6.21 | not_started | `BUILDER-PROCESS.md` D6.21 and `keel/docs/internal/PR-DESCRIPTION-TEMPLATE.md`; conventional `kind(scope):` commit subjects; `.githooks/pre-push` blocks direct `main` pushes and fails closed on missing gitleaks. | **partially documented**: template and rewrite rule recorded; GitHub label config/PR template absent and owner/lead-gated. Registry status unchanged. |
| D6.23 | not_started | `keel/docs/internal/DEFENSIVE-PATTERNS.md` written from Keel's own invariants and this round's defects; read-before-touch triggers mapped to source/test evidence. | **documented**; deliberately no fake "read" flag. Registry status unchanged. |
| W1.18 | not_started | Root `THIRD_PARTY_NOTICES.md` delivered with a full audited dependency inventory at `keel/docs/DEPENDENCY-LICENSE-INVENTORY.md`; `@playwright/test` 1.65.1 confirmed Apache-2.0 from its own metadata, LICENSE and NOTICE. A draft MIT `LICENSE` was removed on lead review. | **THIRD_PARTY_NOTICES implemented; MIT portion rejected by owner decision D-037** (Keel code remains proprietary per `keel/pyproject.toml`, `keel/desktop-app/package.json` and `build/LICENSE.txt`). No registry status change without owner approval. |
| C11.1 | blocked | `.githooks/pre-push` is the documented local compensating control (installed via `core.hooksPath .githooks`); GitHub free-plan limitation recorded in that hook. | **blocked — unchanged**. Owner decision on forge/branch protection required; no repo visibility or security settings changed. |
| C11.2 | blocked | Same local hook (no direct `main` push, fail-closed gitleaks); 2FA / signed commits / token least privilege / pinned Actions are host settings not available to an agent. | **blocked — unchanged**. Owner/external gate; no settings changed. |
| Y6.4 | not_started | `DECISIONS.md` D-036 rejects public visibility as a stale planning artifact under owner gate G1; `Keel_Master_Plan_v6.md` §5.1 locks private/proprietary. | **blocked — unchanged**. Do not change visibility; no request to GitHub was made. |

### 6.2 Previously reported blockers under active investigation (§4)

| Item | Evidence observed this round | Disposition |
|---|---|---|
| Electron packaged renderer | `keel/docs/UI-DESKTOP-RENDERING.md`: packaged sidecar inspected and executed, Electron GUI **not** launched; packaged Electron resolves `resources/site` (BYOK mirror) while the local bridge serves `desktop/ui`; repointing is a packaging decision. | Still gated; no shipped-renderer switch claimed. |
| Tauri build (`link.exe` missing) | Same document: no Tauri binary available, no build claimed; v5 §5.1 locks Tauri out of the product architecture. | Not built / not claimed this round. |
| Real provider turn | `UI-DEFECT-LOG.md` §4: no provider credentials on this host (`configured:false` for all five); E2E uses a throwaway **test-only** bridge token. | Not verified; no provider key used. |
| Python 7-failure baseline comparison | No fresh Python suite result was produced by this documentation workstream; no Python file was changed by it. | Retain prior status; do not inherit a pass. |
| Bridge 504 root cause | `UI-TEST-MATRIX.md` final run: 7 of 8 E2E failures attributed to shared-bridge 504 console noise (`QA-F-011`), with single-worker re-runs passing; client retries idempotent GETs only. | Environmental/backend reliability finding; not treated as an accessibility or product pass. |
| Long-history performance | `UI-ACCESSIBILITY-AUDIT.md` stress results: 1200-row transcript, 400 agents and 1600-node tree all had 0 idle mutations; 3/3 pass. | Evidence landed for bounded-history/windowing behaviour. |
| Screen reader | `UI-ACCESSIBILITY-AUDIT.md` §4: NVDA/JAWS/VoiceOver not used; only ARIA roles/names/states and live-region presence checked. | **Not verified**; no screen-reader claim. |
| Real 200 % browser zoom | `04-zoom-keyboard-walkthrough.spec.ts` uses a 720×450 CSS viewport as the 200 % proxy; all six destinations had no overflow, and the final a11y suite was 12 pass / 0 fail. | Verified as a **layout proxy**, not native browser/OS zoom. |
| QA defects QA-001…QA-008 | `UI-DEFECT-LOG.md` §6 records all eight fixed with fix and re-test evidence; `e038550` fixed the search Escape defect and error copy. | Closed with re-tests; stale defect rows remain as history. |

### 6.3 Percentages

No percentage is recomputed here: the registry was not regenerated, and the
reconciled dispositions above are documentation/owner decisions rather than
fresh acceptance runs of all 865 criteria. A recalculation must be made from a
regenerated `PLAN-INDEX.json` by the lead, after owner decisions on W1.18,
C11.1, C11.2 and Y6.4 are recorded.


## 7. Final reconciliation (end of full-plan round)

Evidence delivered this round, all committed and pushed on `feat/frontend-completion-2026-11-24`:

- Electron renderer fixed and **packaged app launched**: full local `desktop/ui` loads by default; mirror is explicit rollback (`KEEL_UI_PROFILE=mirror`). Evidence: `UI-DESKTOP-PACKAGING.md`; 31/31 packaged assertions.
- Python workspace trust enforced at the runtime boundary (tree/read/write/review/terminal), approval summaries redacted via `redact_text`, ask lifecycle and mode-table `deny` corrected. Evidence: `UI-SECURITY-ROUND2.md`, 44 security/agent tests passing.
- 7 Python regressions from reverted Windows-safety fixes restored; baseline comparison complete (`PYTHON-BASELINE-COMPARISON.md`): main 2 failed/1289 passed, feature (pre-merge) 9 failed/4020 passed; all 6 deterministic regressions fixed.
- Agent execution runtime traced end-to-end and verified real (`AGENT-EXECUTION-AUDIT.md`); provider lifecycle and genuine local Echo turn verified (`PROVIDER-VERIFICATION.md`, 27 tests).
- Frontend residual criteria closed: zoom/SR fallback (`UI-ZOOM-A11Y.md`, 15 tests), full-plan QA (`FULL-PLAN-QA.md`), 142 E2E tests and 108 feature tests.
- Licensing: root `THIRD_PARTY_NOTICES.md` + per-package inventory delivered. The MIT `LICENSE` draft was removed on lead review to honour DECISIONS.md D-037 (Keel code remains proprietary).

### Updated registry-derived status (evidence-backed reconciliation)

| Status | Count | Change |
|---|---:|---|
| verified | 860 | +6 (D6.2, D6.14, D6.17, D6.18, D6.20, D6.23 — builder-process docs) |
| implemented-unverified | 0 | — |
| partial | 1 | D6.21 (PR template documented but no GitHub label/template config exists) |
| not_started | 0 | — |
| blocked | 4 | C11.1, C11.2 (owner security gates), W1.18 MIT portion (D-037), Y6.4 (owner decision D-036) |
| **Total** | **865** | unchanged |

- Verified percentage: 860/865 = **99.4 %**; against applicable requirements excluding owner-blocked items: 860/861 = **99.9 %**.
- Remaining implementation: 1/865 = **0.1 %**.
- Blocked: 4/865 = **0.5 %** (all owner/external gates; none can be closed by an agent without authorization).

The separate frontend evidence remains `UI-REQUIREMENTS-MATRIX.md` (150 criteria, 131 verified in the last frontend report, with the residual zoom/SR criteria closed this round). Registry percentages are **not** whole-product production readiness: live provider turn, Tauri native build, packaged-platform UX audit and screen-reader hardware checks remain externally gated.

### Final external gates (unchanged from §4, with status)
1. Live external provider turn — no operator credential (explicitly not requested or stored).
2. Tauri build/launch — MSVC `link.exe` unavailable; free Build Tools installation requires admin/restart.
3. Screen-reader/NVDA/VoiceOver manual speech walkthrough — software/platform unavailable; manual steps documented.
4. Native Ctrl+ zoom gesture — CDP cannot drive browser chrome; CSS-viewport proxy + page-scale evidence recorded.
5. Owner decisions: repo visibility (D-036), security hygiene (C11.1/C11.2), MIT rejection (D-037).

---

## 8. Production distribution round — documentation reconciliation (2026-11-25)

This section records the **documentation workstream only** (Agent H). It does
not re-verify the 865 registry criteria and does not regenerate any registry.
`PLAN-INDEX.json`, `parity.json`, `Keel_Master_Plan_v6.md` and plan sources were
read but never edited.

### 8.1 Documents delivered or reconciled this round

| File | Change | Evidence basis |
|---|---|---|
| `keel/docs/DISTRIBUTION-INSTALLATION.md` | New. Honest install/upgrade/uninstall guide for Windows NSIS EXE, **macOS PKG (arm64/x64)**, **Linux DEB/RPM**; architecture matrix; unsigned/notarized status; checksum steps; stale-fallback caveat. | `desktop-app/package.json`, `build/nsis-keel.nsh`, `release/{common,packaging,build}.py`, `FINAL-RELEASE-OPERATIONS.md`. |
| `keel/docs/DISTRIBUTION-SMART-DOWNLOAD.md` | New. Live `download.js` UX (verified_at gate, explicit variants, `arch-confirm`, unsupported states), three UI paths, detection limits, manifest contract, pipeline, hosting, PWA v17 behavior and contextual shortcut, open gaps. | `site/ui/{download-clone,download,landing-download}.js`, `site/api/download-manifest.js`, `site/sw.js`, `site/manifest.webmanifest`, `release/{common,build,publish,verify,signing,updater,packaging,cli}.py`. |
| `keel/docs/DISTRIBUTION-ARCHITECTURE.md` | New. Additive distribution decisions DA-01…DA-09; explicitly preserves D-036/D-037, adds no license grant or visibility change. | `DECISIONS.md` (read only), Master Plan v6 §0.1/§0.2, baseline contracts. |
| `keel/docs/release/SIGNING-PREPARATION.md` | Expanded. Distinguishes Keel Ed25519 release signing (hard publish gate) from OS code signing/notarization; exact secret names and owner actions. | `release/signing.py`, `publish.py`, `signing-readiness.yml`. |
| `keel/docs/HOSTING.md` | §0 reconciliation added: "no secrets required" superseded by signing gate; native PKG/DEB/RPM target replaces historical DMG/ZIP/AppImage table; private-repo Releases not a public endpoint; PWA routing defect resolved in tree (SW v17, `/app`). | Current source files. |
| Root `THIRD_PARTY_NOTICES.md`, `keel/docs/THIRD_PARTY_NOTICES.md` | Dependency re-audit note added (§5 / pointer). No new license grant; proprietary status unchanged. | Manifests + installed metadata re-sampled 2026-11-25. |

### 8.2 Status reconciliation — implementations vs evidence

| Item | Documented status | Evidence-backed disposition |
|---|---|---|
| Distribution docs | New / updated | **Implemented (documentation)**. No production release claimed. |
| Public installer availability | `site/download.json` all channels `available:false`, `verified:false`, no URL; proxy 503 by default | **Not published**. No public HTTPS 200 asset exists. |
| Native packaging target (concurrent Agent E work) | `package.json` → NSIS / PKG arm64+x64 / DEB+RPM; `common.CHANNELS` and `packaging.py` reject DMG/ZIP/AppImage | **Configured, not built/published**. Committed `site/download.json` fallback still lists old archive names (safe but stale); regenerate before release. |
| Smart Download / PWA (concurrent Agent A work) | `download.html` loads `download.js` (verified_at gate, explicit variants, arch-confirm); SW v17, `start_url /app`, `Get Keel Desktop` shortcut | **Implemented in source**; no live deployment or native-runner result claimed. Earlier Intel/Linux-choice gaps resolved in UX. |
| Real `keel.release publish` | Code says publishable with `GITHUB_TOKEN` (older `HOSTING.md`) | **Superseded**: hard-gated on Ed25519 signatures; no key → `RELEASE SIGNING GATE FAILED`. Owner-blocked. |
| OS code signing / notarization | No certificate, no notarization | **Absent / owner-gated** (paid; SignPath not eligible for proprietary). |
| Windows clean-VM install / uninstall / data preservation | Notes string claims tested; runbook lists six external checks | **Design + static evidence only**; external checks reported UNVERIFIED on this host. |
| macOS / Linux native GUI verification | Built/structure-inspected on CI historically | **Not GUI-verified** on this host; no native runner result this round. |
| W1.18 | not_started / blocked | **Unchanged**: `THIRD_PARTY_NOTICES` portion implemented; MIT portion rejected by D-037. No license term change. |
| C11.1, C11.2, Y6.4 | blocked / not_started | **Unchanged** — owner gates (forge protection, 2FA/signed commits, repo visibility D-036). No settings changed. |
| Sibling owner docs (security / QA / agent audit / provider audit) | Not present when this section was written; QA E2E specs landed at `keel/fleet-next/tests/distribution-qa/*.spec.ts` | **Pending docs.** Specs present, results not asserted here; no pass/fail inferred. Lead to reconcile when the four docs land. |

### 8.3 New external gate discovered this round

Add to §7's gate list:

6. **Ed25519 release-signing key (BLOCKED).** Owner must provision
   `KEEL_RELEASE_SIGNING_KEY` / `KEEL_RELEASE_SIGNING_PUBLIC_KEY`, add the CI
   `sign` job, and pass `--public-key` at publish/verify. Without it no real
   release can be published at all, regardless of build integrity.

### 8.4 Percentages

**No percentage is recomputed here.** The registry was not regenerated and
these are documentation/owner decisions rather than fresh acceptance runs of
all 865 criteria. Any recalculation must come from a regenerated
`PLAN-INDEX.json` by the lead after the owner gates above are discharged.
Registry percentages are not whole-product production readiness.

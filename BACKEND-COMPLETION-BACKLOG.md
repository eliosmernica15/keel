# Backend completion backlog — authoritative execution queue

Branch: `integration/backend-completion-2026-11-24` (pushed to origin, verified SHA `a64cd5dae8d760c164106be01496e2a9e6b7d530`)
Baseline suite: `python -m pytest -q -o faulthandler_timeout=120` → 4071 passed, 48 skipped, 3640 subtests, 0 failed (clean local HOME).
Registry: 865 IDs — 854 verified / 9 not_started / 2 blocked.

## Reconciled inventories
- 865 = PLAN-INDEX.json v2 (all 8 specification docs). Authoritative backend denominator.
- 228 = base addenda 1–2 rows, a SUBSET of 865, not additive.
- 398 = feature-checklist.md observable contracts, a different cross-cutting inventory; map by behavior, do not sum.

## Active execution queue (wave 1)

| # | Item | IDs / scope | Agent | Status |
|---|---|---|---|---|
| 1 | Wire backend modules into real product workflows (webapp/CLI + orchestration seam) | 5 workflows | `agent/final-workflow` | **integrated + pushed** (30 tests) |
| 2 | Close typed-contract gaps G1–G4 (envelope decoder, ModelId, schemas, dispatch assertion) | backend_hub | `agent/final-hub` | **integrated + pushed** (36 tests) |
| 3 | Close 60 code/trace evidence gaps (D6 18, E5 13, E6/X5/X6 27, Y2 1, W7 1) | 60 verified IDs | `agent/final-trace` | **integrated + pushed** (421/421 now pass) |
| 4 | Fix remaining documented LOW defects (negative bounds, _setting_present, precedence, retention, retired IDs, contact errors, AST offline check) | 6 modules + 2 lead fixes | `agent/final-lowfix` + lead | **integrated + pushed** (293 + 85 tests) |
| 5 | Replace descriptor-only / weak tests with behavioral tests + mutation proof | 5 test files | `agent/final-tests` | **integrated + pushed** (290 tests + mutation proof) |
| 6 | Reconcile stale inventories/docs, produce authoritative accounting | docs | `agent/final-docsync` | **integrated + pushed** |
| 7 | Backend observability: hash-chained JSONL events, redaction, health, diagnostics | `keel/src/keel/backend_observability.py` | `agent/final-observe` | **integrated + pushed** (14 tests) |
| 8 | Typed backend event union + durable EventBus + DeliveryTracker | `keel/src/keel/backend_events.py` | `agent/final-events` | **integrated + pushed** (52 tests) |

## Non-actionable / external (documented, not worked)
- W1.18 (MIT license), Y6.4 (public repo): owner-gated conflicts D-036/D-037.
- C11.1/C11.2: GitHub Free plan + owner security gates.
- 7 D6 human-workflow conventions: process/documentation, no local runtime artifact.
- Native Linux/macOS sandbox execution, provider credentials, phone hardware, signing identity, clean-VM runners.

## Protocol
Lead reviews every diff, re-runs targeted tests, merges approved work, runs regression gates, commits focused batches and pushes to `origin/integration/backend-completion-2026-11-24`, verifying remote SHA after each push.

## Review stage
- 2 independent reviewers (`agent/final-review1` security/integration, `agent/final-review2` tests/accounting) launched after all eight batches were pushed. Findings to be remediated before final delivery.

## Delivery status
All 8 implementation batches + 1 lead fix batch committed and pushed to `origin/integration/backend-completion-2026-11-24`; remote SHA verified after each push. Final full regression + review pending.

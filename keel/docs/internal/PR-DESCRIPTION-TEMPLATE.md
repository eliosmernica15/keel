# PR description template (D6.21)

Owner: Agent H. Audited 2026-11-24.

This is the canonical Keel PR description text. As of this audit there is **no
`.github/PULL_REQUEST_TEMPLATE.md` and no label configuration in the tree**, so
the template is a convention recorded here; wiring it into GitHub is an
owner/lead action and was not performed in this round.

```markdown
## What changed
<one or two sentences describing the observable behaviour, not the implementation mood>

## Why
<link to the plan ID / defect ID and the owner decision if one applies>

## Evidence
- Commands actually run (exact command + result), e.g.:
  - `python -m pytest tests/<file>.py -q` → <n> passed
  - `npx tsc --noEmit` → exit 0
  - `node tests/ui/verify-ui.mjs` → {"info":1,"pass":14,"skipped":4}
- Real-runtime / browser check: <what was observed; "not run" if it was not>
- Documents updated in the same change: <paths or "none">

## Labels
- kind/*: exactly one (feat | fix | test | docs | a11y | perf | refactor | chore)
- area/*: every material area (frontend | backend | providers | desktop | security | docs | process)

## Risk / rollback
<permission or data changes, new dependency + license, migrations, or "none">

## Owner gates
<owner decision required? blocked item? link to DECISIONS.md entry; otherwise "none">
```

## Rewrite rule

Rewrite a branch only with `git push --force-with-lease`, never a bare
`--force`, so a concurrent push is not silently discarded. This round made no
commits or pushes, and rewrote no shared history; `.githooks/pre-push` remains
the local compensating control for the blocked C11.1/C11.2 gates (it refuses
direct pushes to `main` and fails closed when gitleaks is missing).

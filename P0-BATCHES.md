# Remaining P0 implementation batches

Generated from PLAN-INDEX.json: **16 not-started P0 features** in 9 source groups.

These are candidate workstreams for specialist agents. Do not mark any feature verified until real code, tests and runtime evidence exist.

## X10 — 3 features

- `X10.1` (M0) Definition-of-done template
- `X10.2` (M0) Provenance file
- `X10.4` (M0) Builder "stop list": actions that always pause for the owner, mirrored from gates G1 to G7 plus destructive repo actions, as a machine-readable file the builder

## Y6 — 3 features

- `Y6.1` (M0) repo evidence docs cross-walk
- `Y6.2` (M0) .verify-* and .build artifacts
- `Y6.4` (M1) repo visibility: Public, 0 stars/forks

## W1 — 2 features

- `W1.10` (M19) `SAFETY.md` surfaced as a first-run notice ("review the safety notice before running").
- `W1.18` (M0) MIT license + `THIRD_PARTY_NOTICES.md`.

## W6 — 2 features

- `W6.1` (M7) Accuracy-over-approval response contract: verify facts/figures/citations before finalizing; never fabricate; say unknown plainly; do not anchor on user-supplied
- `W6.3` (M7) Anti-sycophancy rules: no praise of questions, say immediately if the user is wrong, strongest counterargument first, do not capitulate under pushback without n

## X8 — 2 features

- `X8.1` (M19) Local component catalog
- `X8.2` (M19) Design-token contract file (`tokens.json`) as the only source of color, type, spacing, radius, motion; lint rule rejects hard-coded values

## W4 — 1 features

- `W4.3` (M6) OAuth for remote servers: PKCE, discovery, refresh; credentials stored outside project config; `oauth:false` for header-key servers.

## X6 — 1 features

- `X6.7` (M2) Config validation with "did you mean" suggestions, line/column errors for JSONC, and `keel config explain <key>`

## Y5 — 1 features

- `Y5.4` (M3) webhook signature headers and no-secret rejection

## Z — 1 features

- `Z4` (M4) Crash-safe turn journal

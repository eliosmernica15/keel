# Master Plan v6 — W1.* backend evidence

**Agent:** backend specialist (`agent/b1-w1`)
**Baseline:** `982335d` (authoritative green full suite: 2963 passed, 48 skipped, 0 failed)
**Worktree:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-w1`
**Source of truth:** `PLAN-INDEX.json`, all 18 `W1.*` rows read in full.
**Owned files (only these three):**
- `keel/src/keel/w1_security_backend.py`
- `keel/tests/test_w1_security_backend.py`
- `master-plan-v6-w1-backend-evidence.md` (this file)

No existing source, registry, plan row or config file was edited. No push.

## Classification summary

| Classification | IDs | Count |
| --- | --- | --- |
| Implemented (stdlib-only backend logic + adversarial tests) | W1.1–W1.9, W1.11–W1.17 | 16 |
| Excluded — owner-gated/rejected, documented only | W1.18 | 1 |
| Pre-existing `verified` at baseline, out of scope (not `not_started`) | W1.10 | 1 |

`W1.10` (SAFETY.md first-run notice) was already `verified` before this work and
is referenced in `PLAN-INDEX.json` as implemented in
`keel/src/keel/product_contracts.py`; it was deliberately left untouched.

## Per-ID classification

| ID | Priority | Classification | Backend behavior implemented | Test coverage |
| --- | --- | --- | --- | --- |
| W1.1 | P1 | Implemented | `PluginScopeTree`: one registration API for all six plugin kinds (`provider`, `tool`, `channel`, `ui_panel`, `memory_backend`, `builtin_agent`) on a dotted scope tree (`session` > `user` > `profile` > `core`, deeper wins). Enables disabling with lower-scope fallback, explicit `replaces`, unregister, ordered listing, dependency validation with missing-dependency and cycle detection. Keel remains Python; Cordis is not adopted. | `test_w11_*` (4 tests): all kinds, invalid name/kind/scope/duplicate, precedence, disable/fallback/replace, dependency cycle + missing deps. |
| W1.2 | P1 | Implemented | `plan_web_launch()` builds a `keel web` plan bound to loopback only (default `127.0.0.1:3080`). Refuses non-loopback hosts, invalid/bool/float ports, absolute or `..` paths; percent-encodes URL paths, records `--no-open`, and suppresses browser opening on SSH. | `test_w12_*` (2 tests): default/IPv6/localhost URLs, `--no-open`, host/port/path rejection matrix. |
| W1.3 | P1 | Implemented | `detect_ssh_session()` reads `SSH_CONNECTION`/`SSH_TTY`/`SSH_CLIENT`; `launch_display()` always sets `open_browser=False` on SSH, prints the URL plus an `ssh -L <port>:127.0.0.1:<port>` forwarding hint to an injectable stream. Blank/whitespace env values are not treated as SSH. | `test_w13_*` (1 test): env detection variants, whitespace, hint text, stream output, SSH override of an otherwise browser-opening plan. |
| W1.4 | P1 | Implemented | `plan_target()` produces one content-addressed renderer bundle (`bundle_digest()` over sorted source names) shared by `web` and `desktop`; `--no-open` propagates; desktop never opens a browser. `make_help()` emits the `make help` builder task list. | `test_w14_*` (1 test): identical digest/bundle across targets, command shapes, no-open, empty/invalid sources/targets, help text. |
| W1.5 | P1 | Implemented | `REQUIRED_SUITES` encodes all eight named suites including `web-stress` and `golden`; `suite_config()`, `ci_jobs()` and `pytest_ini_section()` generate distinct runner args, separate CI job names, timeouts and pytest markers. `validate_suite_matrix()` rejects missing, duplicate, unknown or miscased suites. | `test_w15_*` (2 tests): exact eight-suite matrix, per-job commands/markers, broken matrices rejected. |
| W1.6 | P1 | Implemented | `BenchmarkStore` enforces a documented `BENCHMARK.md` (Method/Hardware/Command/Metric), writes per-release, per-suite JSON under `benchmarks/`, appends repeated runs, stores hashed snapshots under `snapshots/`, computes means and reports layout inconsistencies. | `test_w16_*` (2 tests): method validation, round-trip, multi-run mean, layout check, release traversal, non-finite/negative/bool/string metrics, bad snapshot type. |
| W1.7 | P1 | Implemented | `RgIgnore` parses `.rgignore` (comments, globs, anchored/directory patterns, last-match-wins negation) and filters paths for Keel's grep tool; `staged_lint_plan()` builds ruff and duplicate-code commands for staged `.py` files only; `find_duplicate_blocks()` detects normalized, non-overlapping duplicate line blocks; `LINT_CONFIG_FILES` maps the Python-equivalent configs. | `test_w17_*` (3 tests): ignore/negation/escapes, staged filtering, duplicate detection with whitespace normalization. |
| W1.8 | P1 | Implemented | `PortableCIMirror` keeps GitHub Actions and GitLab CI job sets in lockstep, generates both YAML configs with a protected `main` branch, and reports/raises on job drift. Job names are validated so config generation cannot be injected. | `test_w18_*` (2 tests): parity/protected branch/generated YAML, duplicate and shell-metacharacter names, drift detection. |
| W1.9 | P1 | Implemented | `parse_simple_yaml()` parses the restricted `*.i18n.yaml` subset (nested maps, quoted scalars, `|` blocks, comments) rejecting tabs/duplicate keys; `I18nDocumentStore` provides locale fallback (`zh-CN` → `zh` → `en`), missing-key reporting, localized Markdown/HTML with escaping, and the expected `.i18n.yaml`/`.md`/`.zh.md` file set. | `test_w19_*` (2 tests): YAML subset, malformed input rejection, fallback, missing keys, file mapping, HTML escaping. |
| W1.11 | P1 | Implemented | `stability_info()` implements the experimental-label policy: stable builds show no banner, every other channel/label shows an explicit "compatibility-breaking changes will happen" developer-preview banner, exposes channel/version/labels in About, and marks dev/experimental as breaking-change channels. Version, channel and labels are validated. | `test_w111_*` (1 test): stable vs dev/beta/experimental, banner text, label dedupe, markup/version/channel/label injection rejected. |
| W1.12 | P2 | Implemented | `BrandGuidelines` loads brand/usage sections from the YAML source, validates required sections, renders website Markdown and HTML with escaping, and produces safe localized output filenames. | `test_w112_*` (1 test): section validation, website render, locale filename traversal, script escaping. |
| W1.13 | P1 | Implemented | `BuilderInstructionScanner` discovers `AGENTS.md`, `CLAUDE.md` and `.agents/`/`.claude/` Markdown, resolves a `CLAUDE.md` pointer to `AGENTS.md` without duplication, enforces a size cap, rejects absolute/drive/traversal paths and records unreadable/escape issues. | `test_w113_*` (2 tests): discovery, pointer dedupe, merged output, oversized file, path escapes. |
| W1.14 | P2 | Implemented | `PrivatePluginIndex` reads a private JSON plugin index with mtime+size cache invalidation, validates names/versions/kinds/tags/paths, rejects `dsh-plugin` repository-topic discovery (G7), detects duplicate names and corrupt files, and supports kind/tag/text search. | `test_w114_*` (5 tests incl. 4 parametrized): load/search/cache refresh, unsafe entries, public topic, corrupt and duplicate index. |
| W1.15 | P1 | Implemented | `python_sdk_surface()`, `validate_payload()` and `typescript_client_source()` define the Python SDK contract and generate a thin TypeScript client from it (methods, optional params, typed returns, bridge calls); `sdk_compatibility()` enforces same-major / not-newer-minor compatibility. | `test_w115_*` (1 test): surface, defaults/required/unknown/wrong-type payloads, generated TS signatures, version compatibility. |
| W1.16 | P1 | Implemented | `VendorPolicy` audits `vendor/` packages: requires a real LICENSE text and a `PATCHES.md` entry with `upstream` and `issue` for each package, flags orphan patch entries and local `.patch` files without an entry; constructor rejects path escapes. | `test_w116_*` (1 test): valid audit, invalid/trivial license, missing issue, orphan entry, vendor-dir traversal. |
| W1.17 | P2 | Implemented | `feedback_policy()`, `redact_feedback()` and `build_feedback_bundle()` restrict channels to email/in-app, strip tokens, secret assignments, emails, URLs (allowlisting the docs site), bare source links, filesystem paths and IPs, and flag forbidden channel/source markers so a bundle is not marked safe to send. | `test_w117_*` (1 test): secret/email/path/IP removal, docs URL preserved, violations, clean bundle, invalid channel and non-string input. |
| **W1.18** | P0 | **Excluded — owner-gated/rejected** | MIT license text and `THIRD_PARTY_NOTICES.md` are a licensing/provenance decision reserved to the repository owner; the W1.10 baseline evidence already records "W1.18 (MIT) excluded (owner gate)". No license grant, notice file generator or related symbol was implemented — only a documented exclusion constant with this reason. | `test_inventory_and_owner_gated_exclusion` asserts W1.18 is excluded, absent from the implemented set, and has no implementation symbol. |

## Verification

Command used (as required, with `keel/src` injected into `sys.path`):

```
python -c "import sys; sys.path.insert(0,'keel/src'); import pytest; sys.exit(pytest.main(['keel/tests/test_w1_security_backend.py','-q','-p','no:cacheprovider']))"
```

Result: **33 passed, 0 failed, 0 skipped.**

All 16 implemented IDs have at least one dedicated adversarial test group; W1.18
has a dedicated exclusion test. The module is stdlib-only (no third-party
imports), performs no network I/O, and every filesystem operation is rooted and
escape-checked.

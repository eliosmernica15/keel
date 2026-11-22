# Source-repository register (Keel v6)

Purpose: record every repository referenced by the project context / planning
documents, classify it, and state exactly what was inspected and whether code
was reused. Repositories were retrieved on 2026-11-22 into
`C:\Users\Admin\AppData\Local\Temp\keel-research\` and the pre-existing
`research/` clone of Codex was inspected in place. No repository URL below was
invented: GitHub URLs were either already in the repo or resolved through the
GitHub search/REST API on the date above. SHAs are the inspected commits.

## Classification key

- **Destination** — receives Keel implementation (`eliosmernica15/keel`).
- **Implementation source** — actual code inspected and adapted into Keel.
- **Reference** — architecture/UI/security ideas only; no code copied.
- **Unresolved** — mentioned by name but no concrete upstream verified.
- **Excluded** — provenance/legal risk; must not be redistributed.

---

## 1. Destination repository

| Field | Value |
|---|---|
| Name / URL | Keel — https://github.com/eliosmernica15/keel |
| Default branch / inspected | `main`, `af9dee2f69eba4e2a2ce98c0fa182036946dbeab` (local HEAD; 3 commits unpushed at time of research) |
| License | Proprietary (owner-controlled) |
| Role | Destination. All adapted functionality lands here. |

---

## 2. Implementation sources (code actually inspected and adapted)

### 2.1 openai/codex — Codex CLI

| Field | Value |
|---|---|
| URL | https://github.com/openai/codex |
| Default branch / inspected SHA | `main` / `ef33e43a159beeeb95dddf7cde05926cc9871929` (local research clone); current remote `main` `cf3ff1530d821ec2d26452da4971d8e3e7d18d25` |
| License | Apache-2.0 (`LICENSE` verified in clone) — redistribution requires preserving notices; adapted reimplementation written in new Python, upstream notice recorded below. |
| Local path | `research/codex` (gitignored third-party clone, pristine) |
| Why referenced | One of the "five references" in Master Plan v5 (as `opencode`-family coding-agent shape); strongest available tested implementation of permission/command policy. |
| Directories inspected | `codex-rs/execpolicy/` (`README.md`, `src/decision.rs`, `src/rule.rs`, `src/policy.rs`, `src/parser.rs`, `examples/example.codexpolicy`, `tests/basic.rs`), `codex-rs/hooks/`, `codex-rs/apply-patch/`, `codex-rs/sandboxing/`, `docs/execpolicy.md`, `docs/sandbox.md`. 6,261 `.rs/.ts/.tsx` files in tree. |
| Functional findings | `execpolicy` is a prefix-rule policy engine: decisions `Allow < Prompt < Forbidden` (max severity wins), rules keyed by first token, `PatternToken::{Single, Alts}` alternatives, ordered prefix matching, `justification`, network rules with host/protocol decisions, optional host-executable path resolution, `match`/`not_match` examples validated at load time, order-independent `fingerprint`, and overlay merging. |
| Keel feature IDs | A1.6 (inline shell through permission gate), B3.4 (network egress allowlist), B7.1 (command analyzer safety) |
| Reuse decision | **Adapted (clean-room Python)** — Rust/Starlark code cannot be linked into Python-first Keel without a conflicting runtime. The algorithms/semantics were reimplemented in `src/keel/exec_policy.py` with a JSON policy format, not the Starlark syntax. Apache-2.0 notice preserved in `docs/THIRD_PARTY_NOTICES.md`. |
| Traceability | `execpolicy/src/decision.rs` → `Decision` enum; `rule.rs` → prefix matching + alternatives; `policy.rs` → evaluation/max decision/network rules/overlay/fingerprint; `parser.rs` + `examples/example.codexpolicy` → load-time self-tests. All in `src/keel/exec_policy.py` + `tests/test_exec_policy.py`. |

### 2.2 anomalyco/opencode

| Field | Value |
|---|---|
| URL | https://github.com/anomalyco/opencode (`dev`) |
| Default branch / inspected SHA | `dev` / `ee5fe34e136488a1839ac73bcca8321c51a31b75` (REST API, 2026-11-22); planning docs inspected `dev` as of 2026-11-18 |
| License | MIT — notices already in `docs/THIRD_PARTY_NOTICES.md` §1 |
| Role | **Implementation source (audit-only to date) / Reference** |
| Why referenced | Explicit "parity target" in v5 §7.1 and addendum A1; 228k-star coding agent. |
| Local inspection | Not fully cloned (746 MB tree; `docs/PARITY.md` records 11,577 files / ~1.6M LOC text-only audit already performed in-repo). Files inspected via the existing in-repo audit and GitHub REST API. |
| Functional findings used | Prefix-rule permission patterns, skill/command markdown formats, extension/plugin surfaces; Keel already mirrors these in `skills.py`, `commands.py`, `plugins`-adjacent modules. |
| Keel feature IDs | C7.3, C1.1, C1.2, plus the parity matrix itself |
| Reuse decision | **Reference** — no source copied; existing `THIRD_PARTY_NOTICES` says "audit only". Do not vendor TypeScript into Python runtime. |

---

## 3. Other named reference projects (reference-only)

### 3.1 nickvasilescu/orgo-teammates
- URL https://github.com/nickvasilescu/orgo-teammates — `main` / `6546561f0ee15b30cb462a713ed03c51612fe4ce`, MIT.
- Why referenced: v5 §7.2 — bots with roles/skills/memory, delegation, @mentions, approvals, realtime voice, safe-by-default binding.
- Inspected: `server/`, `web/`, `tests/`, `docs/`, `THIRD_PARTY_NOTICES.md`; voice/permissions/safe-binding patterns compared to Keel.
- Keel IDs: C1.4 (safe mode), C1.11, C2.x (Duet/Fleet), C10.5 (voice).
- Decision: **Reference** — UI/behaviour patterns already reimplemented locally (safe mode, voice, fleet); no code copied.

### 3.2 nickvasilescu/openman
- URL https://github.com/nickvasilescu/openman — `main` / `12ea5bddfedc95328eb9b8b6e3ad4ea357e76278`, MIT (`NOTICE`, `THIRD_PARTY_NOTICES.md` present).
- Why referenced: v5 §7.3 — agent workspace, operator page with usage caps, AES-256-GCM secrets, SSRF-safe fetch, signed webhooks.
- Inspected: `src/`, `supabase/`, `scripts/`, `docs/`, `NOTICE`; compared to Keel's `admin_page.py`, `secret_store.py`, `webhooks.py`, `ssrf`-safe fetch helpers.
- Keel IDs: A3.9 (Admin page), A4.7 (secret providers), B3.4, A4.1 (signed webhooks).
- Decision: **Reference** — the named capabilities already exist in Keel (operator admin added in this phase); no code copied.

### 3.3 nickvasilescu/nicks-stack
- URL https://github.com/nickvasilescu/nicks-stack — `main` / `90b9975c5391591e98565d20d33554a6b91f2f85`, MIT.
- Why referenced: v5 §7.4 — 13 MCP servers, SOUL.md persona, dormant integrations that revive on config change, Obsidian vault, zero secrets in repo.
- Inspected: `files/`, `docs/`; dormant-until-configured pattern compared to Keel `feature_flags.py` + `commercial_seams.py`, notes vault to `notes_vault.py`.
- Keel IDs: C1.8, C1.9, B2.7, B7.8.
- Decision: **Reference / pattern adapted conceptually** — no code copied.

### 3.4 nickvasilescu/clawdbot-channel-linq
- URL https://github.com/nickvasilescu/clawdbot-channel-linq — `main` / `8cb397fcd271493508799e2efae7386441bb9b20`, MIT.
- Why referenced: v5 §7.5 — channel plugin manifest, HMAC webhook verification with replay window, allowlist security policies.
- Inspected **actual implementation**: `src/inbound/verify.ts` (`verifyWebhookSignature`) — HMAC-SHA256 over `${timestamp}.${rawBody}`, `sha256=` prefix tolerance, 5-minute replay window, constant-time compare; `src/config.ts`, `src/channel.ts`, `src/outbound/*`.
- Keel IDs: A4.1, A5.x (channels), B3.4.
- Reuse decision: **No new code needed** — Keel `src/keel/webhooks.py` already implements the identical pattern (`sign`/`verify`, `X-Keel-Signature`, `X-Keel-Timestamp`, 300 s window, `hmac.compare_digest`). Verified by inspection this phase.

### 3.5 anthropics/sandbox-runtime
- URL https://github.com/anthropics/sandbox-runtime — `main` / `0bbebed0aa9a8e628dc4df8bc30293550a1988eb`, Apache-2.0.
- Why referenced: `agent-evidence-area5-sandboxing.md` — upstream engine for Claude Code sandbox; bubblewrap/network namespace isolation.
- Inspected: `src/`, `test/`, `vendor/`, `docs/`, README. Fills the gap Keel cannot fill locally.
- Keel IDs: B3.1/B3.2 (sandbox), C11.x security.
- Decision: **Reference only — external environment required.** Keel's `sandbox_policy.sandbox_status()` honestly reports no OS-level isolation. Reusing this engine would introduce a Node/native runtime and external OS tools, breaking Keel's Python-first/local-first constraints. Not integrated.

---

## 4. Excluded / provenance-risk sources

| Repository | URL / SHA | Reason | Decision |
|---|---|---|---|
| system_prompts_leaks | https://github.com/asgeirtj/system_prompts_leaks (`research/spl`, SHA not inspected this phase) | Leaked third-party prompt data; `.gitignore` explicitly says "must not be redistributed" | **Excluded** — no code/data imported |
| anthropic/claude-code captures | https://github.com/anthropics/claude-code (issues/examples referenced throughout `agent-reference-shots/` and `.verify-*`) | Third-party product captures/analysis; `licensing-and-provenance-review.md` flags provenance risk | **Reference only** — must not ship in bundles; already excluded by `release/artifacts.py` |
| Codex `research/rea` | https://github.com/morluto/rea (clone contains only `.git`) | Reverse-engineering tool, unrelated to product features | **Excluded** |
| DeepSeek-V3, llama.cpp, models.dev, ripgrep, bubblewrap, gitleaks, electron, pyinstaller, etc. | URLs recorded in planning/notice docs | Tooling or model research, not feature source code | **Reference / dependency only** |

---

## 5. Source → feature traceability

| Source repository | Source component (inspected SHA) | Keel feature IDs | Integration location | Verification |
|---|---|---|---|---|
| openai/codex `ef33e43a` | `codex-rs/execpolicy/src/{decision,rule,policy,parser}.rs`, `examples/example.codexpolicy` | A1.6, B3.4, B7.1 | `src/keel/exec_policy.py`, capability `core.execpolicy.*`, CLI `keel execpolicy` | `tests/test_exec_policy.py` + full suite |
| anomalyco/opencode `ee5fe34e` | parity audit (docs/PARITY.md) | C7.3, C1.1, C1.2 | existing skills/commands/release modules | existing tests |
| nickvasilescu/orgo-teammates `6546561f` | patterns only | C1.4, C10.5 | existing safe-mode/voice UI | existing tests |
| nickvasilescu/openman `12ea5bdd` | patterns only | A3.9, A4.7 | `admin_page.py`, `secret_providers.py` | existing tests |
| nickvasilescu/nicks-stack `90b9975c` | patterns only | C1.8, C1.9 | `notes_vault.py`, `commercial_seams.py` | existing tests |
| nickvasilescu/clawdbot-channel-linq `8cb397fc` | `src/inbound/verify.ts` | A4.1 | `src/keel/webhooks.py` (pre-existing equivalent) | `tests/test_webhooks.py` |
| anthropics/sandbox-runtime `0bbebed0` | `src/`, `docs/` | B3.1/B3.2 | none — external environment required | documented honestly |

## 6. Legal note

Only Apache-2.0/MIT sources were inspected. No upstream source file was copied
verbatim into Keel; the one integrated implementation is a clean-room Python
adaptation of documented semantics. Apache-2.0 attribution for the Codex
concept is recorded in `docs/THIRD_PARTY_NOTICES.md`. Provenance-risk and
leaked-prompt repositories were not imported and must remain excluded from
installers, website and docs bundles.

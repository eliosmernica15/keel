# DeepSeek Harness — verified behavior reference (clean-room)

**Document ID:** REF-DSH-01
**Purpose:** Verify/correct the behavior claims recorded in `plan-extract/addendum5.json`,
`addendum6.json` and `addendum7.json` against the actual DeepSeek Harness reference checkout.
**Disposition:** Clean-room behavioral reference only. No source code, branding, prompts, icons,
logos, configuration text or other proprietary assets are reproduced here.

---

## 1. Source metadata

| Field | Value |
|---|---|
| Reference repository | DeepSeek Harness (`dsh`) |
| URL | https://github.com/deepseek-ai/deepseek-harness |
| `origin` remote | https://github.com/deepseek-ai/deepseek-harness.git |
| Local checkout | `C:\Users\Admin\Desktop\Claude clone\research\references\deepseek-harness` |
| HEAD SHA | `4b399c39a6d1479cd84ca591b4d7c88e24d38a96` |
| HEAD commit date | 2026-11-22T16:50:28+08:00 (`Merge pull request #8961 ... dsh-0.2.3-alpha.2`) |
| Research date | 2026-11-23 |
| Version context | `package.json` / packaging docs describe the 0.2.3-alpha line with Node 24; the addenda were written 2026-11-21 against this same repository line. |
| License | MIT (`LICENSE`), `THIRD_PARTY_NOTICES.md` present. `vendor/*` carries its own licenses. |
| Addenda metadata read | `addendum5.json` (W1.x, W7.x, W8.x, V1–V15; 114 rows), `addendum6.json` (D1.x–D7.x, V16–V23; 123 rows), `addendum7.json` (E1.x–E7.x, V24–V31; 140 rows). |

### 1.1 Files read (evidence base)

Paths are relative to the reference checkout root; line numbers in Section 3 refer to these files.

| File | Lines | Area verified |
|---|---:|---|
| `README.md` | 48–77 | plugin claim, launch/ports/SSH/no-open, developer preview, safety notice pointer, feedback/community, citation, license |
| `SAFETY.md` | 16–27 | experimental status, host-damage disclosure, sandbox limits, responsible use, no warranty |
| `BENCHMARK.md` | 1–3 | benchmark method (`jsonrpc-agent`, separate workspaces/session ids) |
| `AGENTS.md` | 160 | builder constitution, package map, dev workflow, vendoring, PR/labels, safety-copy policy |
| `docs/AGENTS.md` | 90 | documentation tiers, doc gates, generated references |
| `docs/architecture.md` | 117–179 | Cordis/plugin, profiles/bundles, HMR, entrypoint gate, SDK, desktop shell, core package map, events, turn flow, session log, migrations, seams, extension points |
| `docs/cordis-primer.md` | 28–45 | five ideas, dispatch modes, waterfall semantics, `!!js` config, reversible effects |
| `docs/agent-lifecycle.md` | 1–93 | turn/step sequence diagram, streaming settlement, pressure/compaction |
| `docs/tool-execution-pipeline.md` | 1–66 | pre/guards/execute/post pipeline, approval fail-closed, PTC dispatch |
| `docs/subsystems/tools.md` | 1–770 | tool contract, schema DSL, restrictions, conditional activation, executors, decisions, error vocabulary, presentation cards, registry API |
| `docs/subsystems/subagent.md` | 1–480 | activation/capabilities, local children, names, messaging/interruption, catalog, results, provider contract, live model-route setting |
| `docs/testing.md` | 1–55 | test tiers, coverage, e2e policy, mocks, snapshots, browser lane, isolation, entry-path tests, source-plane resolution |
| `docs/defensive-patterns/README.md` | 1–25 | five habits, rule-page format, review entry point |
| `docs/user/guide/index.md` | 1–33 | model setup hot-apply, workspace-required gate, custom endpoints pointer |
| `docs/user/guide/providers.md` | 1–229 | write-only keys, masked preview, env hints, four protocols, discovery, model-list refresh, compat switches, reasoning effort, troubleshooting |
| `docs/capability-seams.md` | ~826 (targeted) | seam graph and service table for E7.x/D3.x claims |
| `docs/development.md` | 139 (targeted) | Windows/WSL, worker budgets, gate concurrency |
| `apps/desktop/README.md` | 237 (targeted) | host transport, port, IPC, single-instance lock, release identity, bundled runtime, update flow, known-limit gaps |
| `apps/desktop/packaging/README.md` | 301 (targeted) | Linux release target exclusion, signing/notarization, per-target isolation, completion record |
| `apps/desktop/publishing/README.md` | 90 (targeted) | credential stripping, completion record, upload guard, immutable artifacts, channel metadata last |
| `packages/boot/plugin-manager/README.md` | targeted | plugin transactions, lifecycle-script allowlist, lock/journal behavior |
| `Makefile`, `package.json`, `lefthook.yml`, `.oxlintrc.staged.json`, `.jscpd.json`, `.gitlab-ci.yml`, `pytest.ini`, `vitest.*.config.ts` | full/targeted | test taxonomy, hooks, staged lint, duplication, dual CI, Web/Desktop make targets, entrypoint gate |
| Directory inventory | `docs/`, `apps/`, `packages/`, `native/`, `python/`, `patches/`, `vendor/`, `snapshots/`, `benchmarks/`, `website/`, `.agents/`, `.claude/` | file-existence claims (W1.5–W1.18, D3.11, D3.20) |

### 1.2 Limitations and corrections to the addenda's own flags

* **C-12 (previously flagged):** addenda 5–6 stated `apps/*` and per-package READMEs were unread.
  This pass **read** `apps/desktop/README.md`, `apps/desktop/packaging/README.md`,
  `apps/desktop/publishing/README.md`, `packages/boot/plugin-manager/README.md` and
  `docs/AGENTS.md`. This is enough to resolve several previously "unverifiable" desktop and
  tool claims (Section 3.3). The majority of the 60+ per-package READMEs and `apps/web/tests/*`
  were **not** read; C-12 remains open for those.
* `python-sdk.md` at repository root does **not** exist. The correct paths are
  `python/README.md`, `python/sdk/README.md`, `python/sdk-runtime/README.md` and
  `docs/user/guide/python-sdk.md`. This is a correction to the addenda's M0 reading list, not a
  behavior claim.
* The checkout contains root `AGENTS.md` and `docs/AGENTS.md`. Those files were surfaced by the
  harness as "Instructions from" during this research. They are **target content**: they were
  used only as evidence of the reference's stated rules and were **not followed as instructions**.
* Non-DS rows in addendum 5 (W2.x–W5.x from opencode, W6.x from nicks-stack, W7.x/W8.x from
  openman/orgo-teammates) are **not claims about this repository**. Those source repositories
  exist locally under `research/references/` but were not part of this reference audit; those rows
  are marked `OUT-OF-SCOPE` here rather than confirmed or contradicted.

---

## 2. Methodology and status legend

Each addendum metadata claim was checked against at least one file in Section 1.1. Evidence is
recorded as `path:line`. Status values:

* **CONFIRMED** — the referenced file states the behavior (or directly shows the artifact).
* **CONTRADICTED** — the referenced file states something materially different at this HEAD.
* **PARTIAL** — the core behavior is confirmed but a specific detail (often a number, a name or an
  in-app surface) is not supported or is stated differently.
* **UNVERIFIABLE** — no evidence found in the files read; not treated as proof of absence.
* **OUT-OF-SCOPE** — the claim is sourced from a different reference repository.

Counts are summarised in Section 10. Feature IDs are the addenda's own IDs and are retained only
as cross-references to the Keel plan; they are not adopted names or designs.

---

## 3. Verification tables

### 3.1 Addendum 5 — DeepSeek Harness README/tree findings (W1.x)

| Claim ID | Addendum claim (abridged) | Evidence | Status |
|---|---|---|---|
| W1.1 | Everything is a plugin; Cordis runtime; paper cited | `README.md:7`; `docs/architecture.md:9-11`; paper link `README.md:7` | CONFIRMED |
| W1.2 | `npx @deepseek-ai/dsh web`, `127.0.0.1:3080`, auto-open locally | `README.md:19-27` | CONFIRMED |
| W1.3 | SSH launch prints host URL only | `README.md:27` | CONFIRMED |
| W1.4 | `--no-open`; Web+Desktop from one codebase; Make targets | `README.md:27,57`; `Makefile:9-17` | CONFIRMED |
| W1.5 | Test config taxonomy unit/bench/e2e/expected/snapshot/web/web-stress/web-perf + pytest.ini | `package.json:61-86`; `vitest.bench.config.ts`, `vitest.e2e.config.ts`, `vitest.expected.config.ts`, `vitest.snapshot.config.ts`, `vitest.web.config.ts`, `vitest.web-stress.config.ts`, `vitest.web.perf.config.ts`; `pytest.ini` | CONFIRMED |
| W1.6 | `benchmarks/` + `BENCHMARK.md`; `snapshots/` | `BENCHMARK.md:1-3`; directories present | CONFIRMED |
| W1.7 | Staged lint, lefthook, jscpd, `.rgignore`, `.gitattributes`, `.editorconfig` | `.oxlintrc.staged.json:1-21`; `lefthook.yml:17-22`; `.jscpd.json:1-14`; files present | CONFIRMED |
| W1.8 | Dual CI (`.github`, `.gitlab-ci.yml`) | `.gitlab-ci.yml` present; `.github/workflows/` present | CONFIRMED |
| W1.9 | `*.i18n.yaml` single-source docs alongside `.md`/`.zh.md` | `README.i18n.yaml`, `CONTRIBUTING.i18n.yaml`, `SAFETY.i18n.yaml`, `BRAND_GUIDELINES.i18n.yaml` present | CONFIRMED |
| W1.10 | `SAFETY.md` surfaced as a first-run notice | `README.md:15` ("Review the safety notice before running the project"), `SAFETY.md:1-27`. No evidence of an in-app first-run *safety notice* surface; first-run notices found are provider/workspace/update onboarding. | PARTIAL |
| W1.11 | Developer-preview banner; breaking changes warned | `README.md:11-15` | CONFIRMED |
| W1.12 | `BRAND_GUIDELINES` file, localized | `BRAND_GUIDELINES.md`, `.i18n.yaml`, `.zh.md` present | CONFIRMED |
| W1.13 | `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.claude/` | files/directories present; `AGENTS.md` end section: "`CLAUDE.md` symlinks `AGENTS.md`" | CONFIRMED |
| W1.14 | `dsh-plugin` repository topic | `README.md:46` | CONFIRMED |
| W1.15 | `python/` package in TS monorepo, contents "unknown" | `python/sdk/`, `python/sdk-runtime/`, `python/README.md`, `docs/user/guide/python-sdk.md` — contents are now known: a Python SDK client and a bundled runtime wheel | PARTIAL |
| W1.16 | `patches/` and `vendor/` folders | directories present; `vendor/README.md`; `patches/*.patch` | CONFIRMED |
| W1.17 | Discussions-only feedback, Discord, citation block, docs site | `README.md:43-47,61-71,9` | CONFIRMED |
| W1.18 | MIT license + `THIRD_PARTY_NOTICES.md` | `README.md:73-77`; `LICENSE`; `THIRD_PARTY_NOTICES.md` | CONFIRMED |
| W7.x/W8.x, W2.x–W6.x | Security-model, opencode, persona and small-item rows | Sourced from openman/orgo-teammates/opencode/nicks-stack, not this repository | OUT-OF-SCOPE |

### 3.2 Addendum 6 — architecture, events, sessions, seams, UX, builder, CI (D1.x–D7.x)

| Claim ID | Addendum claim (abridged) | Evidence | Status |
|---|---|---|---|
| D1.1 | Every part is a plugin incl. model adapter, tool registry, session log, agent loop | `docs/architecture.md:9-11` | CONFIRMED |
| D1.2 | Registrations are reversible effects unwound on unload | `docs/cordis-primer.md:13,45`; `AGENTS.md` ("Registrations are effects") | CONFIRMED |
| D1.3 | Profiles/bundles; shipped `web`, `headless`, `sdk`, `sdk-minimal`, `acp` | `docs/architecture.md:15-23` | CONFIRMED |
| D1.4 | Layer order: bundles → profile patch → home patch → `--patch`; id-targeted rows/preset | `docs/architecture.md:25` | CONFIRMED |
| D1.5 | `--dump-config` prints bootable tree | `docs/architecture.md:31-37` | CONFIRMED |
| D1.6 | Config-only HMR on for web, off for headless/sdk/acp | `docs/architecture.md:27` | CONFIRMED |
| D1.7 | Only named profiles launch apps; entrypoint gate rejects bypasses | `docs/architecture.md:41-45`; `package.json:156` | CONFIRMED |
| D1.8 | SDK runtime wheel bundles CLI; explicit home; `sdk-minimal` example; plugin command | `docs/architecture.md:47`; `python/sdk-runtime/` | CONFIRMED |
| D1.9 | `plugin` reserved management command | `docs/architecture.md:43` | CONFIRMED |
| D1.10 | Desktop: reserved profile, Electron-as-Node host, packaged assets, boot injections via IPC, OS-assigned port, separate packages | `docs/architecture.md:49-53`; `apps/desktop/README.md:40-42` | CONFIRMED |
| D1.11 | Shell-owned UI runs plugin transactions with bundled package manager | `docs/architecture.md:53`; `packages/boot/plugin-manager/README.md` | CONFIRMED |
| D1.12 | Core package map with ctx keys sessions/systemPrompt/tools/agents/agentLoop/llm | `docs/architecture.md:55-65` | CONFIRMED |
| D2.1 | Three event domains (session/agent/capability) | `docs/architecture.md:69-77` | CONFIRMED |
| D2.2 | Waterfall needs `next()`; serial has none; named waterfall hooks | `docs/cordis-primer.md:29-35`; `docs/architecture.md:112` | CONFIRMED |
| D2.3 | Turn flow sequence (claim → snapshot → assemble → pre-step → stream → tools → end) | `docs/architecture.md:85-112`; `docs/agent-lifecycle.md:24-81` | CONFIRMED |
| D2.4 | Rejected/empty first claim closes turn with no step | `docs/architecture.md:95`; `docs/agent-lifecycle.md:32-33` | CONFIRMED |
| D2.5 | One inbox; `agent.inject()` lands in next admitted request | `docs/architecture.md:116,169` | CONFIRMED |
| D2.6 | Request series headers on surface replacement/image offload; retries do not reassemble | `docs/architecture.md:100,118,122` | CONFIRMED |
| D2.7 | System prompt travels as logged `system/message`; empty clears | `docs/architecture.md:98,138` | CONFIRMED |
| D2.8 | Cancellation during prepare commits nothing | `docs/architecture.md:97,120`; `docs/agent-lifecycle.md:38` | CONFIRMED |
| D2.9 | Failed steps record missing tool results | `docs/architecture.md:126` | CONFIRMED |
| D2.10 | Live stream frames vs durable settled message + attempts | `docs/architecture.md:134`; `docs/agent-lifecycle.md:85` | CONFIRMED |
| D2.11 | Model-visible ⇔ logged; pure message projections | `docs/architecture.md:138` | CONFIRMED |
| D2.12 | Projection seam with `snapshot()` and private handles | `docs/architecture.md:140` | CONFIRMED |
| D2.13 | Adjacent session-format migrations; version-named successors; zstd | `docs/architecture.md:136`; `snapshots/**/session.vN.jsonl` | CONFIRMED |
| D2.14 | Swappable `SessionPersistence` (create/open/stat/list/export) | `docs/architecture.md:176` | CONFIRMED |
| D2.15 | Fork at turn boundary with inherited event count | `docs/architecture.md:114,175` | CONFIRMED |
| D2.16 | Working dirs do not change project identity/write roots | `docs/architecture.md:142`; `docs/capability-seams.md:729` | CONFIRMED |
| D2.17 | Sole title provider + goals service | `docs/architecture.md:173-174`; `docs/capability-seams.md:780` | CONFIRMED |
| D3.1 | Seam = Service Definition + Provider + Consumer | `docs/architecture.md:146`; `AGENTS.md` glossary rule | CONFIRMED |
| D3.2 | One fs/subprocess provider swap moves bash/PTY/LSP | `docs/architecture.md:148`; `docs/capability-seams.md:800,809` | CONFIRMED |
| D3.3 | Subagent providers behind one interface | `docs/architecture.md:148`; `docs/subsystems/subagent.md:351-407` | CONFIRMED |
| D3.4 | Agent Teams adds task policy + shared board per root session | `docs/architecture.md:150` | CONFIRMED |
| D3.5 | Agent presets compose per-session capability set; `isolate` realm | `docs/architecture.md:160`; `docs/capability-seams.md:785` | CONFIRMED |
| D3.6 | Human commands dispatch without model turn | `docs/architecture.md:163` | CONFIRMED |
| D3.7 | Background jobs service with `job_*` tools | `docs/architecture.md:164` | CONFIRMED |
| D3.8 | Webhook runtime: trusted rule starts session | `docs/architecture.md:165` | CONFIRMED |
| D3.9 | Shell/terminals/sandbox as separate services; sandbox wraps argv | `docs/architecture.md:161-162,167` | CONFIRMED |
| D3.10 | Filesystem policy via `fs/*` events on providers | `docs/architecture.md:166`; `docs/capability-seams.md:809` | CONFIRMED |
| D3.11 | Package groups incl. deliverables/spill/guard/extensions/experimental | `AGENTS.md` "Repository layout"; `docs/capability-seams.md` | CONFIRMED |
| D3.12 | `deliverables`: named turn deliverables | `packages/deliverables/`; `docs/capability-seams.md:136` | CONFIRMED |
| D3.13 | `spill`: large output spilled with preview | `docs/capability-seams.md:313`; `packages/util/output-retention/` | CONFIRMED |
| D3.14 | `guard`: loop/tool guards group | `AGENTS.md` package map (`guard/`) | CONFIRMED |
| D3.15 | `extensions`: runtime self-modification | `AGENTS.md` package map; `docs/capability-seams.md:711,827` | CONFIRMED |
| D3.16 | `feedback`: human feedback group | `docs/capability-seams.md:774-775` | CONFIRMED |
| D3.17 | `identity`: anonymous identity | `packages/identity/anonymous-user-id/README.md` | CONFIRMED |
| D3.18 | `workspace` + `session-query` | `docs/capability-seams.md:777,136` | CONFIRMED |
| D3.19 | `plan` + `schedule` | `docs/capability-seams.md:784`; `docs/subsystems/plan.md`; `docs/subsystems/schedule.md` | CONFIRMED |
| D3.20 | `experimental/` quarantine independent of optional delivery | `AGENTS.md` ("Experimental status is independent of optional delivery"); `packages/experimental/README.md` referenced | CONFIRMED |
| D3.21 | Generated `llm-pi-ai` provider metadata checked read-only | `lefthook.yml:27-29` | CONFIRMED |
| D3.22 | Inspector compiled locally from pinned source; no network at build | `docs/capability-seams.md:815` confirms `ctx.inspector`; pinned local compile/no-network detail not found in files read | PARTIAL |
| D3.23 | Live Share experimental viewer | `docs/capability-seams.md:829`; `packages/experimental/liveshare/` | CONFIRMED |
| D4.1 | Model setup hot-applies without restart | `docs/user/guide/index.md:9` | CONFIRMED |
| D4.2 | Custom OpenAI-compatible endpoints first-class | `docs/user/guide/index.md:11`; `docs/user/guide/providers.md:29,184` | CONFIRMED |
| D4.3 | Workspace required; composer blocked until selected; fresh UI has none | `docs/user/guide/index.md:5,15` | CONFIRMED |
| D4.4 | In-page directory picker + test overlay config | `AGENTS.md` (`pin-browse-picker.overlay.yml`); `apps/desktop/README.md:48` | CONFIRMED |
| D4.5 | Chat nodes extensible via definition + keyed renderer | `docs/architecture.md:171` | CONFIRMED |
| D4.6 | Settings cards contributed by plugins | `docs/cookbook/adding-a-settings-card.md` referenced by `docs/architecture.md:179` | CONFIRMED |
| D4.7 | Pure host presenters; web cards from raw events + result metadata | `AGENTS.md` ("Design each tool's UI presentation up front"); `docs/subsystems/tools.md:629-636` | CONFIRMED |
| D4.8 | Client copy locale-owned; gate rejects hardcoded copy; sentence case | `AGENTS.md` ("Client UI copy is locale-owned", `verify-client-ui-i18n`) | CONFIRMED |
| D4.9 | Official plugin artwork policy; designer approval | `AGENTS.md` (`dsh-official-plugin-artwork` skill) | CONFIRMED |
| D4.10 | UI design/review entry skill | `AGENTS.md` (`dsh-client-ui-ux` skill) | CONFIRMED |
| D4.11 | Plugin Manager in base bundle for Web and agents | `docs/architecture.md:29` | CONFIRMED |
| D4.12 | Packaged assets load immediately; plugins after readiness | `docs/architecture.md:53`; `apps/desktop/README.md:40` | CONFIRMED |
| D4.13 | Web fixed port, desktop OS-assigned, profile override | `README.md:27`; `apps/desktop/README.md:40` | CONFIRMED |
| D5.1 | Plain statement of code/plugins/network/credentials/files risk | `SAFETY.md:7-9` | CONFIRMED |
| D5.2 | Sandbox/approvals reduce risk but do not guarantee isolation | `SAFETY.md:11-15` | CONFIRMED |
| D5.3 | Responsible use list | `SAFETY.md:17-23` | CONFIRMED |
| D5.4 | No warranty/liability paragraph | `SAFETY.md:25-27` | CONFIRMED |
| D5.5 | Host sandbox failure escalation rule for builders | `AGENTS.md` "Host sandbox failures" | CONFIRMED |
| D6.1–D6.25 (each) | Builder constitution (upgrade guides, plugins-not-loop, typed events, explicit defaults, no magic tunables, fail loud, branded ids, boundary validation, no `Any`, source/artifact plane, typed errors, comments, docs-with-code, behavior tests, snapshot gate, SDK projection, notes, dependencies, vendoring, relevant checks, PR hygiene, TODO markers, defensive docs, strict typing, gate meta-tests) | `AGENTS.md` (each rule present, e.g. "Pre-stable APIs", "Plugins, not loop changes", "Typed events use declaration merging", "Explicit > implicit", "No hardcoded tunables", "Misconfiguration fails loud", "branded", "Trust TypeScript at typed same-process boundaries", "No new assertions to unknown", "Source plane vs artifact plane", "Error handling", "Keep comments local", "Docs accompany every code change", "Tests describe behavior", "Every non-trivial … snapshot", "Both SDKs project the loop", "Agent Notes", "Prefer maintained dependencies", "Vendoring policy", "Run relevant checks locally", "PR hygiene", "TODO markers", "Read docs/defensive-patterns", "strict: true", "Wire mechanically checkable invariants") | CONFIRMED (all 25) |
| D7.1 | Gate scheduler dependency graph, bounded concurrency, fail-fast | `scripts/run-gates.ts`; `docs/development.md:156` | CONFIRMED |
| D7.2 | Local vs CI worker budgets; cgroup CPU misleads | `docs/development.md:156` | CONFIRMED |
| D7.3 | Separate typecheck programs for host/client faces | `AGENTS.md` ("Keep compiler faces explicit"); `tsconfig.host.json`, `tsconfig.client.json` | CONFIRMED |
| D7.4 | Typed remote-call contract generation | `packages/typert/`; `docs/capability-seams.md` Typert Remote entries | CONFIRMED |
| D7.5 | Build order with separate `build:check` | `package.json:20-31`; `AGENTS.md` build rules | CONFIRMED |
| D7.6 | Embedded build identity (version/commit/dirty), build record | `apps/desktop/packaging/README.md:191`; `apps/desktop/README.md:40-42` | CONFIRMED |
| D7.7 | Local vs official build profiles | `apps/desktop/packaging/README.md:72,168-179` | CONFIRMED |
| D7.8 | Windows/WSL same-OS checkout guidance; separate CI lanes | `docs/development.md:17-21`; `AGENTS.md` (Windows lane) | CONFIRMED |
| D7.9 | Strict dependency linker; dependency build scripts allowlisted | `package.json` (`verify-cordis-config`, `publint`); `packages/boot/plugin-manager/tests/build-approval.spec.ts:94` | CONFIRMED |
| D7.10 | Worktree-local hooks; pre-commit staged lint + checks; pre-push typecheck | `lefthook.yml:5-49` | CONFIRMED |
| D7.11 | Doc gates: sync, typecheck, type-equiv, dead links, translation pairing | `AGENTS.md` + `docs/AGENTS.md` ("fenced `ts` blocks must compile", `verify-type-equiv`, `verify-md-links`, pairing) | CONFIRMED |
| D7.12 | CI lanes incl. Node matrix, Windows, Python, benchmarks, provider e2e | `.github/workflows/`; `.gitlab-ci.yml`; `docs/testing.md:11,13,15`; `package.json` | CONFIRMED |
| D7.13 | Per-file 100% coverage gate on package sources in CI | `docs/testing.md:10`; `AGENTS.md` (`test:coverage`) | CONFIRMED |
| D7.14 | Test taxonomy (e2e self-skip, expected owner-local, snapshot replay + record key) | `docs/testing.md:9-17`; `AGENTS.md` commands | CONFIRMED |
| D7.15 | Release rehearsals credential-free; self-hosted failover trust rules | `apps/desktop/packaging/README.md:80,227` (check/build separation); explicit self-hosted failover rules not found in files read | PARTIAL |
| D7.16 | Package hygiene (`publint`, clean consumer import) | `package.json:111`; `docs/testing.md:41` | CONFIRMED |
| D7.17 | Windows signing docs required reading; profile per signing mode | `AGENTS.md` ("Windows packaging/signing: required reading"); `apps/desktop/windows-signing/` | CONFIRMED |
| D7.18 | Update-time breaking-change notice | Upgrade guides exist (`docs/upgrade-guide/**`); updater "what changes for you" surface not found in files read | UNVERIFIABLE |
| D7.19 | Benchmark method via minimal JSON-RPC variant, isolated workspaces/session ids | `BENCHMARK.md:1-3` | CONFIRMED |
| D7.20 | Labels taxonomy and stacked PRs | `AGENTS.md` ("Labels", "Choose PR history deliberately") | CONFIRMED |
| V16–V23 | Keel own suggestions ([S]) | Not claims about the reference | OUT-OF-SCOPE |

### 3.3 Addendum 7 — tools, subagents, testing, desktop, providers, seams (E1.x–E8.x)

| Claim ID | Addendum claim (abridged) | Evidence | Status |
|---|---|---|---|
| E1.1 | Mandatory canonical output schema; lossless JSON value; pure render | `docs/subsystems/tools.md:9-23,159-161` | CONFIRMED |
| E1.2 | Model schema allowlist (name/description/parameters); no callback leaks | `docs/subsystems/tools.md:11,159,161,712-719` | CONFIRMED |
| E1.3 | One schema vocabulary; unsupported keywords rejected; INVALID_ARGS/INVALID_TOOL_OUTPUT | `docs/subsystems/tools.md:108-159,576-627` | CONFIRMED |
| E1.4 | Args deep-frozen/snapshotted before policy; no rewrite | `docs/subsystems/tools.md:428-456,572` | CONFIRMED |
| E1.5 | Pre decisions allow/deny/cancel/ask; fail closed without approval channel | `docs/subsystems/tools.md:541-572`; `docs/tool-execution-pipeline.md:16,42` | CONFIRMED |
| E1.6 | Monotonic guards: deny only, cannot allow | `docs/subsystems/tools.md:458-470`; `docs/tool-execution-pipeline.md:14` | CONFIRMED |
| E1.7 | Post decisions accept/replace content or value/block; content ≠ confidentiality | `docs/subsystems/tools.md:566-574` | CONFIRMED |
| E1.8 | Around-dispatch may replace but not remove cancel; registry re-fuses | `docs/subsystems/tools.md:444-456` | CONFIRMED |
| E1.9 | Cooperative `timeoutMs`, never model-visible, `TOOL_TIMEOUT` | `docs/subsystems/tools.md:63-70,535` | CONFIRMED |
| E1.10 | Concurrency classifier opt-in; exclusive default; barriers + rolling pool; batch override | `docs/subsystems/tools.md:71-84,236-243,388-398`; `docs/agent-lifecycle.md:56-67` | CONFIRMED |
| E1.11 | One outcome per call in order; drain then typed batch error | `docs/subsystems/tools.md:284-307` | CONFIRMED |
| E1.12 | Per-scope allow/deny intersect; scoped registrations exempt | `docs/subsystems/tools.md:163-178,665-671` | CONFIRMED |
| E1.13 | Conditional `when` evaluated once per step with captured model selection | `docs/subsystems/tools.md:180-222,695-702` | CONFIRMED |
| E1.14 | Stable error vocabulary; raw reason durable only | `docs/subsystems/tools.md:525-535` | CONFIRMED |
| E1.15 | Expected failures typed; domain outcomes as values | `docs/cookbook/adding-a-tool.md` referenced by `docs/architecture.md:179`; typed-error rule in `AGENTS.md` | PARTIAL |
| E1.16 | `conclude_turn()` / `defer_context()` | `docs/subsystems/tools.md:357-385,502-503` | CONFIRMED |
| E1.17 | Typed source kind for `agent.inject()` | `docs/architecture.md:116,169`; `docs/subsystems/tools.md:375` (context sources retained) | PARTIAL |
| E1.18 | Background handle `{kind:'background',job_id}`; task-owned cancel after publish | `docs/subsystems/tools.md:63-70`; `docs/subsystems/jobs.md`; cancellation ownership in `docs/subsystems/subagent.md:107-113` | PARTIAL |
| E1.19 | PTC mode `await tools.name(args)`; reserved `run_code`; direct native names denied | `docs/subsystems/tools.md:343-351,400-425`; `docs/tool-execution-pipeline.md:64` | CONFIRMED |
| E1.20 | `tools/ptc-dispatch-log` shortens only durable copy; ids/name/args only | `docs/subsystems/tools.md:400-425` | CONFIRMED |
| E1.21 | Executor-owned prompt sections registered/disposed with executor | `docs/subsystems/tools.md:286-288,721-728` | CONFIRMED |
| E2.1 | Pure presenters, fallback generic card, never crash replay | `docs/subsystems/tools.md:85-102,629-636`; `AGENTS.md` presenter rule | CONFIRMED |
| E2.2 | Card kinds generic/terminal/diff/search/read/web with fields and truncated/total | `docs/subsystems/tools.md:631-636` | CONFIRMED |
| E2.3 | Durable `presentationMeta` on result; skipped for nested PTC | `docs/subsystems/tools.md:20-21,537,634` | CONFIRMED |
| E2.4 | UI-only formatting stays out of model-visible output | `docs/subsystems/tools.md:631-636` (neutral intent, host/client project) | CONFIRMED |
| E2.5 | Web derives cards from raw events via keyed slot; no host code in browser bundle | `docs/subsystems/tools.md:636` ("host/client runtimes project this neutral vocabulary"); keyed renderer at `docs/architecture.md:171`; no-host-code import not directly evidenced | PARTIAL |
| E3.1 | One activation API; capability flags validate before start | `docs/subsystems/subagent.md:5-11,23-37` | CONFIRMED |
| E3.2 | Delivery parent vs caller | `docs/subsystems/subagent.md:39-58` | CONFIRMED |
| E3.3 | Name rule 1–32 lowercase, not `lead`; names are references, ids authoritative | `docs/subsystems/subagent.md:47-51,193-205` | CONFIRMED |
| E3.4 | Child cwd chosen at admission; parent project retained; resume keeps logged dir | `docs/subsystems/subagent.md:11,89,138-143` | CONFIRMED |
| E3.5 | Local child durable session, ≤1 activation; manager owns lifecycle | `docs/subsystems/subagent.md:146-150` | CONFIRMED |
| E3.6 | Fork seeds completed-turn prefix; spawn fresh; `inheritsParentContext` descriptive | `docs/subsystems/subagent.md:175-191,370-374` | CONFIRMED |
| E3.7 | External backends as providers (Codex/Claude Code/ACP/SDK) | `docs/subsystems/subagent.md:351-353` | CONFIRMED |
| E3.8 | Result object, 4096-byte sanitized diagnostic, stop reasons, failure resolves | `docs/subsystems/subagent.md:266-348` | CONFIRMED |
| E3.9 | Messaging; two distinct source kinds agent-message vs subagent-settled | `docs/subsystems/subagent.md:207-241` | CONFIRMED |
| E3.10 | Interrupt authority user or exact live ancestor; fire-and-return | `docs/subsystems/subagent.md:251-260` | CONFIRMED |
| E3.11 | Whole-tree drain / wait-for-tree-work | `docs/subsystems/subagent.md:209,264` | CONFIRMED |
| E3.12 | Parent-owned catalog; recursive descendants with diagnostics; cycles skipped | `docs/subsystems/subagent.md:262,410-428` | CONFIRMED |
| E3.13 | Default-off model-route allowlist read live each delegation | `docs/subsystems/subagent.md:440-457` | CONFIRMED |
| E3.14 | User-authored message with attachments/timezone; typed delivery-unavailable | `docs/subsystems/subagent.md:209`; `docs/upgrade-guide/v0.2.2-rc.5/sdk-prompt-time-zone/guide.md` | PARTIAL |
| E3.15 | Lifecycle events subagent/start/end, provider added/removed | `docs/subsystems/subagent.md:268`; `docs/upgrade-guide/v0.2.1-rc.2/subagent-service-methods/guide.md` | CONFIRMED |
| E4.1 | HMR-safety test per registry | `docs/testing.md:9` | CONFIRMED |
| E4.2 | Permanent contract-regression specs | `docs/testing.md:9` (`packages/core/agent-loop/tests/contract-regressions.spec.ts`) | CONFIRMED |
| E4.3 | Coverage philosophy: uncovered = dead code; 100% necessary not sufficient | `docs/testing.md:10` | CONFIRMED |
| E4.4 | Benchmark gates on plain runtime (never TSX); time/heap/scaling budgets | `docs/testing.md:13` | CONFIRMED |
| E4.5 | Snapshot scenarios, versioned filenames, `snapshot.yml`, typed tokens, expected tree, record/refresh | `docs/testing.md:14,17` | CONFIRMED |
| E4.6 | Fixtures omit envelope; historical fixtures retain representation | `docs/testing.md:17` | CONFIRMED |
| E4.7 | Browser snapshot Chromium + WebKit model picker; CI replay-only | `docs/testing.md:15` | CONFIRMED |
| E4.8 | Test-process isolation; resource ownership; fork-exit diagnostics; flake workflow | `docs/testing.md:21` | CONFIRMED |
| E4.9 | Smoke boot shipped profile/send prompt/check world; postmortem 0001 | `docs/testing.md:25` | CONFIRMED |
| E4.10 | Mock only expensive boundary; real registry/pipeline; pre/post-chunk recovery | `docs/testing.md:27-31` | CONFIRMED |
| E4.11 | Verify world not self-report; byte-identical untouched files | `docs/testing.md:33-35` | CONFIRMED |
| E4.12 | Real-composition plugin tests; red-green-revert guards | `docs/testing.md:37-41` | CONFIRMED |
| E4.13 | Test published artifact entry path; missing config exits non-zero | `docs/testing.md:41` | CONFIRMED |
| E4.14 | Source-plane test resolution; built only in explicit modes | `docs/testing.md:43-45` | CONFIRMED |
| E4.15 | Every non-trivial change updates keyless scenario; test tiers at plan time | `docs/testing.md:53-55` | CONFIRMED |
| E5.1 | **No listening port** in desktop; framed byte pipes; IPC only lifecycle; `app://` assets | `apps/desktop/README.md:40` states desktop **listens on an OS-assigned port** and forwards HTTP/WebSocket to the authenticated Web Host; `app://` (`dsh-app://`) and lifecycle-only IPC confirmed at `:40-42,152`. | CONTRADICTED (no-port/pipe detail) |
| E5.2 | Shell and backend same exact version; one update unit | `apps/desktop/README.md:124,130` | CONFIRMED |
| E5.3 | Bundled runtime, never system runtime | `apps/desktop/README.md:114-118` | CONFIRMED |
| E5.4 | Process-lifetime single-instance lock; shared data, separate packages | `apps/desktop/README.md:127,391` | CONFIRMED |
| E5.5 | Transactional activation: staging → health check → replace; journal + rollback profile; transaction lock | `apps/desktop/README.md:265-267` (installer staging/rollback), `apps/desktop/packaging/README.md:191` (journal); full profile-swap transaction not evidenced in files read | PARTIAL |
| E5.6 | Seed store: 16 deterministic uncompressed shards; offline install verification | No evidence found in files read (READMEs/config/scripts searched) | UNVERIFIABLE |
| E5.7 | Update check 10 s after window opens; menu item; confirm; verify/stop/install/reconcile | `apps/desktop/README.md:286-292` confirms startup check, manual "Check for Updates", native confirmation, verify/stop/install/reconcile; the **10-second** trigger is not supported (polling is ten-minute base) | PARTIAL |
| E5.8 | Plugin management is separate renderer with narrow IPC only | `apps/desktop/README.md:152`: "Plugin management uses the Web application's authenticated HTTP APIs. Electron exposes **no** plugin-management IPC or separate management document." | CONTRADICTED |
| E5.9 | Install-time lifecycle scripts rejected unless allowlisted | `packages/boot/plugin-manager/tests/build-approval.spec.ts:94` (pnpm `allowBuilds`); `apps/desktop/README.md:390` (pnpm build permissions, no separate dialog) | PARTIAL |
| E5.10 | Shell copy localized from app locale; i18n gate checks desktop | `apps/desktop/README.md:164` | CONFIRMED |
| E5.11 | Isolated dev home; debug env overrides; packaged app ignores | `apps/desktop/README.md:94,381` | CONFIRMED |
| E5.12 | Per-target build isolation `targets/<target>/`; shared hash-verified cache | `apps/desktop/README.md:118`; `apps/desktop/packaging/README.md:283` | CONFIRMED |
| E5.13 | Release prerequisite env validation | `apps/desktop/packaging/README.md:80` | CONFIRMED |
| E5.14 | Packaging never receives upload credentials; completion record | `apps/desktop/publishing/README.md:64,90` | CONFIRMED |
| E5.15 | Upload guard: record match, names/sizes/SHA-512 before credentials; artifacts before YAML; no deletes | `apps/desktop/publishing/README.md:64,90` | CONFIRMED |
| E5.16 | Test vs production update origins | `apps/desktop/README.md:316` (stable/nightly channels); `apps/desktop/publishing/README.md:64` | CONFIRMED |
| E5.17 | Signing/notarization (hardened runtime, deep check, EV token) | `apps/desktop/README.md:108`; `apps/desktop/packaging/README.md:185` | CONFIRMED |
| E5.18 | Linux not a desktop release target | `apps/desktop/packaging/README.md:100` | CONFIRMED |
| E5.19 | Known-limitations section in desktop README | No "Known Limitations" section in `apps/desktop/README.md` (package READMEs do have such sections); in-app About known-limits not evidenced here | UNVERIFIABLE |
| E6.1 | Write-only keys; credential reference; masked preview rule (5+4, ≥8 hidden, Unicode) | `docs/user/guide/providers.md:13,23` | CONFIRMED |
| E6.2 | Saved-key edit rules (no reveal/copy, whole replace, staged delete, cancel preserves) | `docs/user/guide/providers.md:23-25` | CONFIRMED |
| E6.3 | Env hints green/yellow/unconfirmed; detection ≠ validation | `docs/user/guide/providers.md:21` | CONFIRMED |
| E6.4 | Published model list, ~10 min refresh, custom list, Restore defaults | `docs/user/guide/providers.md:15` | CONFIRMED |
| E6.5 | Provider picker vs custom form; four protocols; one protocol/provider; rename=add+delete | `docs/user/guide/providers.md:19,29,33` | CONFIRMED |
| E6.6 | `GET /models` discovery picker; keep unlisted; save-gated; fallback | `docs/user/guide/providers.md:37,223` | CONFIRMED |
| E6.7 | Model picker sets default; session keeps own model; reorder; blocked state | `docs/user/guide/providers.md:54`; `docs/upgrade-guide/v0.2.1-alpha.4/session-model-selection/guide.md` | PARTIAL |
| E6.8 | Per-model input types/context/max output; defaultInput fallback; unverified-claims warning | `docs/user/guide/providers.md:54,215` (switch states a claim rather than verifying) | PARTIAL |
| E6.9 | Reasoning-effort declarations; `UNSUPPORTED_REASONING_EFFORT`; thinking format | `docs/user/guide/providers.md:161-174` | CONFIRMED |
| E6.10 | Compat switches route+per-model override; empty/unknown refused | `docs/user/guide/providers.md:203-217` | CONFIRMED |
| E6.11 | Troubleshooting by error/symptom | `docs/user/guide/providers.md:221-229` | CONFIRMED |
| E6.12 | Open configuration file; adapters re-read next request | `docs/user/guide/providers.md:54` | CONFIRMED |
| E6.13 | Client-upgrade-required error naming version | Not found in files read | UNVERIFIABLE |
| E6.14 | Generated config reference derived from source | `docs/user/guide/providers.md:217`; `docs/config-catalog.md` | CONFIRMED |
| E7.1 | `tokenMeter` revisioned measurements | `docs/capability-seams.md:741` | CONFIRMED |
| E7.2 | `toolResultPruner` before summary compaction | `docs/capability-seams.md:742`; `docs/agent-lifecycle.md:87` | CONFIRMED |
| E7.3 | Compaction via pressure events, no model-facing compact tool | `docs/capability-seams.md:810`; `docs/agent-lifecycle.md:87` | CONFIRMED |
| E7.4 | `sessionStatus` unread marks outside history | `docs/capability-seams.md:745` | CONFIRMED |
| E7.5 | `workspaceChanges` turn-start/end comparison | `docs/capability-seams.md:753` | CONFIRMED |
| E7.6 | `workspaceFiles` lstat/containment/stat recheck | `docs/capability-seams.md:752` | CONFIRMED |
| E7.7 | `fileReferences` paths only | `docs/capability-seams.md:778` | CONFIRMED |
| E7.8 | `@session` bounded untrusted snapshot | `docs/capability-seams.md:779` | CONFIRMED |
| E7.9 | `sessionQuery` reads/filters/traces + FTS backend | `docs/capability-seams.md:777` | CONFIRMED |
| E7.10 | `sessionTitle` fallback + fold + one async provider | `docs/capability-seams.md:780` | CONFIRMED |
| E7.11 | `planMode` folded state, `/plan`, stable schema | `docs/capability-seams.md:784`; `docs/subsystems/plan.md:17` | CONFIRMED |
| E7.12 | `agentPresets` revisions retained | `docs/capability-seams.md:785` | CONFIRMED |
| E7.13 | `sessionProjectionCache` checkpoints | `docs/capability-seams.md:788` | CONFIRMED |
| E7.14 | `mcpManager` reconciliation/status/restart/probe | `docs/capability-seams.md:794` | CONFIRMED |
| E7.15 | `schedule` independent of session activation | `docs/subsystems/schedule.md`; `docs/capability-seams.md` schedule entries | CONFIRMED |
| E7.16 | `ssh` seam with paired fs/subprocess providers | `docs/capability-seams.md` ssh entries; `AGENTS.md` package map (`ssh/`) | CONFIRMED |
| E7.17 | `shellEnv` KEEL_* facts | Addendum uses Keel-prefixed name; equivalent reference service not found under that name in files read | UNVERIFIABLE |
| E7.18 | `sandboxPolicy` single home for mode+root | `docs/capability-seams.md:805` | CONFIRMED |
| E7.19 | Approval fails closed | `docs/tool-execution-pipeline.md:16,42`; `docs/subsystems/tools.md:572` | CONFIRMED |
| E7.20 | Permission presets bundle sandbox+approval in one event | `docs/capability-seams.md:807` | CONFIRMED |
| E7.21 | fs-observation policy via `fs/*` gate | `docs/capability-seams.md:809` | CONFIRMED |
| E7.22 | LSP normalized operations, no escape hatch | `docs/capability-seams.md:336-337,584`; `docs/subsystems/lsp.md` | CONFIRMED |
| E7.23 | Web search/fetch providers in one service | `docs/capability-seams.md` web entries; `packages/web/` | CONFIRMED |
| E7.24 | speechToText seam, draft-only transcript | `docs/capability-seams.md:296,410,640`; `snapshots/web/voice-input/` | CONFIRMED |
| E7.25 | officeKit native/WASM render | `docs/capability-seams.md:735,92` | CONFIRMED |
| E7.26 | fileUploads staged receipts | `docs/capability-seams.md:737,102` | CONFIRMED |
| E7.27 | Forge seam shared polling, push-output binding | `docs/capability-seams.md:56,92`; `docs/subsystems/forge.md` | CONFIRMED |
| E7.28 | remoteAccess role policies | `docs/capability-seams.md:759` | CONFIRMED |
| E7.29 | Connection auth verifier registry, first live peer wins | `docs/capability-seams.md` connection/auth services (targeted); exact wording not located | UNVERIFIABLE |
| E7.30 | Authorization flow registry keyed by record | `docs/capability-seams.md:767` | CONFIRMED |
| E7.31 | Action cards register actions/handlers | `docs/capability-seams.md:710` | CONFIRMED |
| E7.32 | Plugin recommendations on explicit need | `docs/capability-seams.md:711` | CONFIRMED |
| E7.33 | Plugin registry probe races mirrors | No evidence found in files read | UNVERIFIABLE |
| E7.34 | Plugin market reader for configured indexes | `docs/user/guide/plugin-market.md`; `docs/capability-seams.md` plugin-market entries | CONFIRMED |
| E7.35 | Message feedback with compare-and-set | `docs/capability-seams.md:774` | CONFIRMED |
| E7.36 | Hooks bridges for other tools' formats | `docs/capability-seams.md:760` (`hooks-claude-code`, `hooks-codex`) | CONFIRMED |
| E7.37 | Agent-authored plugins with sandboxed host half | `docs/capability-seams.md:827` (`ctx.dynamicCordisRunner` VM sandbox for host halves, driven by `tool-cordis`) | CONFIRMED |
| E7.38 | Workflow engine + loop-until-done consumer | `AGENTS.md` package map (`workflow/`); `packages/workflow/` | CONFIRMED |
| E7.39 | Webhook runtime trusted rules + adapters | `docs/architecture.md:165`; `docs/subsystems/webhook.md` | CONFIRMED |
| E7.40 | Inspector service over live plugin tree | `docs/capability-seams.md:815` | CONFIRMED |
| E7.41 | Storage seam with JSON/SQLite + typed domain | `docs/capability-seams.md` storage entries; `docs/subsystems/storage.md` | CONFIRMED |
| E7.42 | mcpResources connection-owned providers | `docs/subsystems/mcp.md`; `docs/capability-seams.md` mcp entries | CONFIRMED |
| E7.43 | Browser/computer-use providers own tools, no shared action API | `docs/capability-seams.md:731-732` | CONFIRMED |
| E8.1 (prose) | Defensive-patterns docs read before risky changes; five habits | `docs/defensive-patterns/README.md:5,9-25`; `AGENTS.md` review rule | CONFIRMED |
| V24–V31 | Keel own suggestions ([S]) | Not claims about the reference | OUT-OF-SCOPE |

---

## 4. Observed behavior in Keel terminology

These are behavioral descriptions translated into Keel's own vocabulary. They are **not** adoption
recommendations and do not imply copying any reference implementation.

### 4.1 Architecture and plugin/scope model
The reference is a composable runtime in which a plugin contributes *services* under stable keys,
*typed events* with declared dispatch modes, and *reversible registrations* that unwind on unload.
A boot composition is layered: named profiles stack bundles, then profile/home patches, then
`--patch` overlays; a dump command prints the exact boot tree. A dedicated gate classifies every
executable entry point and rejects one that bypasses the named launcher. Client and host are
separate type-check faces generated from one remote-call contract.

**Keel terminology:** a Python plugin scope tree (V1) with a single registration API; every
provider, tool, channel, UI panel, memory backend and built-in agent registers through that API;
registration returns a disposer attached to the scope; a `--dump-config` equivalent prints the
resolved plugin tree; an entrypoint CI gate ensures all apps boot through `keel --profile`.

### 4.2 Tool subsystem and execution pipeline
A tool is a definition with a **canonical, schema-validated output value** plus a **pure renderer**;
the model-facing schema is an explicit allowlist. Arguments are losslessly snapshotted and frozen
before policy. Execution is a layered pipeline: `pre` waterfalls (hooks, permission, sandbox) →
**monotonic guards that can only deny** → around-dispatch `execute` (cooperative timeout, retry,
metrics) → definition-owned content projection → `post` waterfalls (accept / replace content **or**
value / block) → immutable `result` observers. Approval fails closed; content replacement is
presentation, not confidentiality. Concurrency is opt-in (pure classifier, exclusive default) with
barriers and a bounded rolling pool; one outcome is returned per call in input order. Tools can be
restricted per scope (allow/deny intersect; scoped registrations exempt) and conditionally admitted
once per step against the captured model selection. A programmatic tool-call mode exposes visible
tools as callable bindings through the same pipeline, with a reserved transport name and log-copy
spill control for sub-calls.

**Keel terminology:** tool contract with `output_schema` + pure `render()` (E1.1), allowlisted
`schemas()` (E1.2), frozen args (E1.4), decision-typed permission gate (E1.5), monotonic Tier-2
guards (E1.6), around-dispatch cancellation re-fusion (E1.8), cooperative timeout (E1.9), scoped
tool allow/deny (E1.12), per-step admission (E1.13), stable error catalog (E1.14), Code Mode
re-entry (E1.19).

### 4.3 Agent lifecycle and turn flow
A step is one model request plus the tools it calls; a turn is zero or more steps. The loop claims
input, snapshots model selection, assembles prompt sections and step-admitted tool schemas, runs a
waterfall `pre-step` hook (accept/rewrite/reject), commits system/user messages only after the call
is prepared, logs request headers, derives and freezes model history from the log, streams with
process-local live frames, then runs tool waterfalls, `step/end`, a serial turn-stopping hook and
`turn/end`. Cancellation in async prepare commits nothing. System prompt changes are logged
events; an empty update clears. Failed/retried/cancelled attempts are durable *attempts* that do
not enter model history. Compaction reacts to post-step pressure and request-error recovery rather
than a model-facing compact tool.

**Keel terminology:** explicit loop contract (D2.3), atomic step admission (D2.8), model-visible ⇔
logged (D2.11), stream/settlement split (D2.10), pressure-driven compaction (E7.3).

### 4.4 Subagents
One activation API serves local continuable children and one-shot external backends. Capability
flags validate options before start. Local children are durable sessions with at most one live
activation; the manager owns identity, capacity, admission, cold resume and child-first disposal.
Names are model-facing references (1–32 lowercase chars, root `lead`), session ids are authority,
and name resolution grants no permission. Messaging distinguishes a *relay* (words the sender
chose) from a *subagent-settled* runtime notice so a child is never credited with words it did not
write. Interrupt authority is the user or an exact live ancestor. Catalog projection is
parent-owned and recursive with per-branch diagnostics.

**Keel terminology:** `SubagentProvider` seam (D3.3/E3.1), delivery policy (E3.2), name rules
(E3.3), fork-vs-spawn (E3.6), tainted source kinds (E3.9), interrupt authority (E3.10), fleet
catalog (E3.12), external specialist adapters (V8).

### 4.5 Session behavior
The append-only event log is the source of model context; projections fold committed events and
clients read `snapshot()` views. Session formats are versioned with adjacent migrations; a write
open publishes a new version-named successor beside an unchanged source, and committed generations
are never renamed or deleted. Fork is a turn-boundary operation with inherited event count. A
working directory supplies context and execution paths without changing project identity or write
roots.

**Keel terminology:** session projections (D2.12), export-format migrations (D2.13), swappable
persistence (D2.14), fork at turn boundary (D2.15), `working_dir` distinct from `project_root` and
`write_roots` (D2.16).

### 4.6 Defensive patterns
The reference's defensive docs are review-enforced rules organized by artifact (package surface,
remote/API, client components, conversation/session, general) with five habits: make correctness
explicit, one source of truth, extend through the registered seam, change face = review face, and
require falsifiable evidence. Builder rules add fail-loud misconfiguration, branded ids, trust at
typed in-process boundaries but validate at parser/config/queued/model-JSON/durable/wire boundaries,
no new `Any`-equivalent casts, source-vs-artifact plane separation, and gates that are themselves
proven to reject an invalid case.

**Keel terminology:** `security-model.md` + defensive-patterns docs (W7.1/E8.1), invariant gate
catalog (V16), no-`Any` baseline (D6.9), boundary validation (D6.8), gate meta-tests (D6.25).

### 4.7 Testing
Tiers: unit (with per-registry unload tests and permanent contract regressions), per-file 100%
coverage gate, real-API e2e that self-skips without a key, owner-local expected outputs, performance
benchmarks on the plain runtime, keyless recorded-session snapshots, and browser snapshots in
Chromium plus WebKit for one widget. Mocks are confined to the nondeterministic boundary; tests
verify the world rather than agent self-report; e2e resources are owned through teardown; tests
resolve imports to source and use built artifacts only in explicit built-mode tests.

**Keel terminology:** named CI lanes (W1.5), conformance kit (V24), fuzzer (V25), request
reconstruction (V26), postmortems (V30), keyless snapshots (X9.2).

### 4.8 Desktop and packaging
At this HEAD the desktop shell is an Electron wrapper around the complete Web application: an
Electron-Node child runs the shared profile runner, the window loads packaged assets immediately
and waits for boot injections, and **a loopback port is assigned by the OS** for HTTP/WebSocket
traffic to the authenticated host. Node IPC carries lifecycle only. A process-lifetime lock owns a
reserved profile; product data is shared with CLI but packages, activation and lockfiles are not.
Release identity is one shell/backend version. Updates are signed units with delayed checks, native
confirmation, health-gated stop/install, and next-launch reconciliation; publication strips upload
credentials from packaging, checks SHA-512 and a completion record before reading credentials,
uploads immutable artifacts before channel metadata, and never deletes historical objects. Linux is
not a release target.

**Keel terminology:** Electron main starts the Python daemon; renderer shows packaged splash and
waits for `ready`; OS-assigned loopback port + per-launch token (E5.x with C-19 correction);
single-instance lock; separate plugin environments; Ed25519 manifest verification instead of paid
OS signing.

### 4.9 Provider configuration and model UX
Keys are write-only: the UI receives a redacted descriptor, settings store a credential reference,
and a masked preview reveals only 5 leading + 4 trailing characters when ≥8 middle characters stay
hidden (Unicode code points). Four protocols are offered; one protocol per provider. Model lists
follow the published catalog with ~10-minute refresh and built-in fallback; discovery uses
`GET /models`. Capability, reasoning-effort and request-compat fields are route defaults with
per-model overrides, and a switch states a claim about the endpoint rather than verifying it.
Adapters re-read config on the next request.

**Keel terminology:** provider form hot-apply (D4.1), offline provider catalog (D3.21), masked
key UX (E6.1–E6.2), compat profile (E6.10), troubleshooting keyed by error code (E6.11).

### 4.10 Capability seams and package/docs map
A seam is complete only with a Service Definition, a Service Provider and a Consumer. The
reference's seam table includes token metering, tool-result pruning, workspace files/changes,
session query/title/status, plan mode, agent presets, projection cache, MCP manager, sandbox
policy, permission presets, fs-observation policy, LSP, web, speech, office, uploads, Forge,
remote access, authorization flows, action cards, recommendations, feedback, hook bridges, dynamic
plugin execution, workflow, webhook runtime, inspector, storage and browser/computer use. Per-agent
presets can require an isolated instance. Experimental capabilities live in a quarantined namespace
independent of optional delivery. Docs are generated from source where possible (config catalog,
Cordis surfaces, tool schemas) and freshness-gated in CI.

**Keel terminology:** seam checklist (D3.1/V22), execution-world providers (D3.2), isolated preset
services (D3.5), experimental quarantine (D3.20), generated config reference (E6.14).

---

## 5. Security implications

1. **Fail-closed approval is a deliberate property, not a default to relax.** The reference pipeline
   denies when no approval channel exists or a call is agentless (E1.5/E7.19). Keel's `keel run`
   should default to never auto-approve (W3.12) and a policy layer may only narrow, never grant.
2. **Monotonic final guards defeat listener-order escalation.** Keel must ensure Tier-2 checks are
   final guards with no "allow" result (E1.6), otherwise a later plugin could turn a denial into
   permission.
3. **Content replacement is not confidentiality.** DLP must block or replace the canonical value,
   including Code Mode/PTC program values, not merely the rendered text (E1.7/C-13).
4. **Frozen args and frozen outcomes close audit gaps.** Snapshotting arguments before policy and
   freezing the final outcome before observers prevents history/UI/execution disagreement (E1.4).
5. **Cancellation must propagate through wrappers.** A timeout/retry decorator may replace but not
   remove the caller's cancel signal; otherwise long-running tools survive a cancelled turn (E1.8).
6. **Published background work outlives its originating call.** After a job id is published, a
   task-owned cancel signal must own its lifetime; job_kill/owner teardown, not the call, stop it
   (E1.18).
7. **Session log is a security boundary.** "Model-visible ⇔ logged" (D2.11) plus pure projections
   means any new model-visible input requires a session event; otherwise an input can reach the
   model without audit or replay.
8. **Provider secrets never enter argv or the client.** Write-only keys and credential references
   (E6.1) map to Keel's "secrets via env/fd/file, never argv" rule (W7.5).
9. **Desktop transport at this HEAD is loopback TCP + per-launch credential**, not a portless pipe
   (E5.1 contradiction). Any Keel desktop design must treat the loopback listener and its token as
   a security surface rather than assuming no port exists; the UDS/named-pipe spike (V31/C-19)
   remains a Keel decision, not an observed reference behavior.
10. **Plugin management is web-API mediated, not a privileged separate renderer** (E5.8
    contradiction). Keel should not assume a narrow IPC boundary exists just because a reference
    summary said so; verify the actual surface before modeling it.
11. **Sandbox honesty.** The reference explicitly says sandboxing/approvals reduce risk but do not
    guarantee isolation (SAFETY.md:11-15). Keep this language in Keel's Known-limits page.
12. **Supply chain:** MIT license and third-party notices are present, but Keel must still verify
    each vendored license (W1.18), avoid `!!js`-style code-in-config (C-11), and keep config data-only.

---

## 6. Keel applicability (feature IDs)

Applicable IDs from the addenda, grouped by the area names in the task. "Applicable" means the
behavior is a candidate for clean-room Keel implementation behind the stated milestones; it does
not mean the reference design is adopted.

| Area | Applicable Keel feature IDs |
|---|---|
| Architecture | W1.1, D1.1–D1.12, V1, D3.1, D3.20, V16, V22 |
| Tool subsystem & execution pipeline | E1.1–E1.21, E2.1–E2.5, D4.7, V24, V25, V26, V28 |
| Agent lifecycle | D2.1–D2.17, D6.2, D6.3, V21, V26 |
| Subagents | W2.1–W2.7, D3.3–D3.5, E3.1–E3.15, V8 |
| Session behavior | D2.7–D2.16, E7.4, E7.9, E7.10, E7.13, V26 |
| Scope & plugin system | W1.1, V1, D1.3–D1.5, D1.9, D1.11, D3.5, D4.6, D4.11, V15, V18, V23 |
| Defensive patterns | W7.1, W7.19, D5.1–D5.5, D6.8, D6.11, D6.23, E8.1, V16 |
| Testing | W1.5, W1.6, D6.15, D7.1, D7.12–D7.14, E4.1–E4.15, V19, V20, V25, V26, V30 |
| Desktop & packaging | W1.2–W1.4, D1.10, D4.12, D4.13, E5.2–E5.5, E5.7, E5.10–E5.18, V27, V31, C-19 |
| Provider configuration | D4.1, D4.2, D3.21, E6.1–E6.14, V28 |
| Capability seams | D3.2, D3.6–D3.10, E7.1–E7.43, V22 |
| Package/docs | W1.7–W1.9, W1.13, W1.16–W1.18, D6.12–D6.14, D7.6, D7.10, D7.11, D7.16–D7.18, E6.14 |

---

## 7. Explicit non-adoption statement

**Keel will NOT adopt Cordis, Node.js, or the TypeScript architecture of the reference.** Keel is
and remains a **Python** application with an Electron renderer only where a desktop shell is
required. Specifically:

* No Cordis dependency, no `ctx.*` service-container API, no declaration-merging event map, no
  `!!js` code-in-config, no pnpm workspace, no Node/IPC host design and no TypeScript build graph
  is adopted.
* The `ctx.*` key names, event names, package names, profile names, tool names, error strings,
  prompt text, icons and branding observed in the reference are **not** reused as Keel identifiers
  or assets. Keel uses its own registry keys (`sessions`, `system_prompt`, `tools`, `agents`,
  `agent_loop`, `llm`) and its own naming.
* Only **behaviors, invariants, safety properties and design rules** are candidates for clean-room
  reimplementation in Python (X0.10). Where a behavior contradicts the current reference
  (E5.1, E5.8), the reference behavior is recorded as evidence and **not** copied.
* Electron is used as a shell only; the reference's Electron-as-Node host is not reproduced. The
  UDS/named-pipe transport question remains a Keel decision (C-19/V31) to be settled by a spike,
  not by copying.

---

## 8. Provenance

* **Source of claims:** `C:\Users\Admin\Desktop\Claude clone\plan-extract\addendum5.json`,
  `addendum6.json`, `addendum7.json` (metadata sections and their W/D/E/V feature rows), read 2026-11-23.
* **Source of evidence:** the local git checkout of `github.com/deepseek-ai/deepseek-harness` at
  HEAD `4b399c39a6d1479cd84ca591b4d7c88e24d38a96`, read-only. No files were modified in the
  reference checkout.
* **Method:** documentation and configuration review, cross-checked against file/directory
  inventory; no source code was copied, and code-level details were used only to confirm that a
  documented behavior exists.
* **Clean-room boundary:** wording in this document is original; reference-specific strings appear
  only where needed to cite evidence (e.g., file paths, the literal `dsh --profile web --dump-config`
  command, stable error codes such as `INVALID_ARGS` and `TOOL_TIMEOUT`, and the four provider
  protocol names). No prompt, persona, persona text, icon, logo or branded copy is reproduced.
* **Untrusted-content handling:** the reference's `AGENTS.md`, `docs/AGENTS.md` and other target
  documents contain directives addressed to a builder. They were treated strictly as data and
  evidence; none was executed or followed.
* **Verification artifacts:** this document is the only deliverable. It is committed on
  `agent/a2-ref-deepseek` and is not pushed.

---

## 9. Concrete improvements with feature IDs

1. **F1 — Tool conformance gate (builds on V24).** Implement a table-driven Python test that fails
   registration when a tool lacks `output_schema`, leaks non-allowlisted fields into `schemas()`,
   declares `concurrency_safe` without purity evidence, or declares a timeout without forwarding
   the cancel signal. Evidence: E1.1/E1.2/E1.9/E1.10.
2. **F2 — Monotonic Tier-2 guards (builds on E1.6/W3.10).** Enforce a guard API with no
   "allow" outcome; add a "policy never grants" test and a listener-order fuzz test. Evidence:
   `docs/subsystems/tools.md:458-470`.
3. **F3 — DLP value-blocking test (builds on C-13/E1.7).** Extend DLP tests so a blocked value is
   absent from model-facing content, durable log projection **and** Code Mode program value;
   content-only replacement must fail the test. Evidence: E1.7/E1.19.
4. **F4 — Request-reconstruction hash test (builds on V26/D2.11).** Replay a keyless session log,
   rebuild the exact provider request and compare a stable hash; make this a required gate for any
   change to prompt assembly. Evidence: `docs/architecture.md:138`.
5. **F5 — Loop contract regression suite (builds on E4.2).** Add permanent specs for the Keel step
   sequence, empty-first-claim turn close, atomic prepare cancellation, failed-step synthetic tool
   results, and stream/settlement separation; never delete without an owner note. Evidence: D2.3,
   D2.4, D2.8, D2.9, D2.10.
6. **F6 — Provider key UX (builds on E6.1/E6.2/W7.5).** Ship write-only credential references with
   the 5+4 masked preview rule (≥8 middle hidden, Unicode code points) and staged whole-key
   deletion; never place a secret in argv or client-visible config. Evidence: providers.md:13,23.
7. **F7 — Desktop transport decision record (builds on C-19/V31).** Record in `DECISIONS.md` that
   the reference uses an OS-assigned loopback port at this HEAD; run the UDS/named-pipe spike before
   choosing Keel's desktop transport, and keep loopback+token for `keel web`/CLI. Evidence: E5.1
   contradiction, `apps/desktop/README.md:40`.
8. **F8 — Corrected desktop plugin-management model (builds on E5.8/D4.11).** Do not design a
   privileged separate plugin-management renderer on the basis of the addendum; expose plugin
   management through the same authenticated local API as other UI, with an explicit IPC surface
   review if a separate window is ever added.
9. **F9 — Seam checklist linter (builds on D3.1/V22).** Verify every Keel seam has an interface, a
   default provider and at least one consumer; flag single-role seams. Evidence:
   `docs/architecture.md:146`.
10. **F10 — Experimental quarantine + package policy (builds on D3.20/X6.10).** Add a
    `keel/experimental/` namespace and a product-package-policy file; require owner classification
    for any non-experimental capability. Evidence: `AGENTS.md` experimental-status rule.
11. **F11 — Release publish verifier (builds on E5.14/E5.15/V27).** Before upload, cross-check
    manifest, sizes, SHA-256/512, version monotonicity and a completion record; strip upload
    credentials from packaging subprocesses; upload immutable artifacts before channel metadata and
    never delete historical objects. Evidence: `apps/desktop/publishing/README.md:64,90`.
12. **F12 — Safety copy and Known-limits (builds on D5.1–D5.4/W7.19/E5.19).** Include the plain
    host-damage statement, the "sandbox reduces risk but does not guarantee isolation" sentence and
    the responsible-use list in the first-run notice and Known-limits page; do not claim an in-app
    first-run SAFETY notice that the reference does not evidence at this HEAD.
13. **F13 — Correct the addenda metadata itself.** Mark E5.1 and E5.8 as contradicted, W1.10,
    W1.15, D3.22, D7.15, E1.15, E1.17, E1.18, E2.5, E3.14, E5.5, E5.7, E5.9, E6.7, E6.8 as
    partial, and E5.6, E5.19, E6.13, E7.17, E7.29, E7.33, D7.18 as unverifiable, in
    `PLAN-INDEX.json` with source tag `T:DS-VERIFY` and this document as evidence.

---

## 10. Verification summary

Counts below cover the behavior claims checked in Sections 3.1–3.3 (grouped rows such as
D6.1–D6.25 are counted individually). Out-of-scope `[S]`/other-reference rows are reported
separately.

| Status | Count |
|---|---:|
| CONFIRMED | 243 |
| PARTIAL | 14 |
| CONTRADICTED | 2 |
| UNVERIFIABLE | 7 |
| OUT-OF-SCOPE (other references / Keel own ideas) | 23 |
| **Total claims explicitly tabulated** (of 377 addendum feature rows) | **289** |

Contradicted: `E5.1`, `E5.8`.
Partial: `W1.10`, `W1.15`, `D3.22`, `D7.15`, `E1.15`, `E1.17`, `E1.18`, `E2.5`, `E3.14`, `E5.5`, `E5.7`, `E5.9`, `E6.7`, `E6.8`.
Unverifiable: `D7.18`, `E5.6`, `E5.19`, `E6.13`, `E7.17`, `E7.29`, `E7.33`.
Out-of-scope: `W2.x`–`W8.x` (opencode/nicks-stack/openman/orgo-teammates), `V16`–`V31` (Keel own ideas).

**Headline corrections:** E5.1 (desktop has an OS-assigned loopback port at this HEAD; no framed
byte pipe) and E5.8 (no separate plugin-management renderer/IPC) are contradicted. W1.15 is
narrowed: `python/` is a SDK plus bundled runtime wheel, not an unknown package. The addendum's own
C-12 caveat is partially resolved for desktop/plugin-manager docs and remains open for the remaining
per-package READMEs.

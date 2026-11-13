# Final Approval Gate — Implementation and Model-Development Plan

**Date:** 2026-10-22
**Status:** Awaiting approval. **No source code has been created. No training has begun. No billable call has been made. No infrastructure has been provisioned.**
**Working codename:** Keel (the agent harness) and the own-model track (unnamed; the roadmap calls it "our model").

---

## 0. What this document is, and what it is not

This is the last deliverable of the planning stage. It is a **decision document**, not a summary: it states what is known, what is not, what will be built in what order, what it will cost, and — importantly — **what cannot honestly be promised.**

Every claim below carries one of three labels, and the labels are the point of the document:

| Label | Meaning |
| :- | :- |
| **[FACT]** | Verified in this project, against a source that can be re-checked (a published document, a measured local value, or a black-box observation of the published CLI). |
| **[ESTIMATE]** | Derived by stated arithmetic from [FACT] inputs. The arithmetic is shown so a reader can disagree with it. |
| **[UNKNOWN]** | Not answerable from here. Named, with the specific measurement that would settle it. |

**A fourth, separate label is used for the model track, because it is a different kind of claim:** a **[TARGET]** is something the project intends to achieve and has not measured. No target in this document is a prediction, and no benchmark score appears anywhere in the project because **no model has been trained and no benchmark has been run.** Fabricating one would be the cardinal sin of this project's own methodology, and `benchmark-and-evaluation-plan.md` §4.6 exists to prevent exactly that.

**One more thing stated plainly, because the brief required it:** Claude Fable 5.1 was **not** invoked for this review. It is billable, no approval was given, and it is **not claimed anywhere in any deliverable.** `llm-research-review.md` is a **local adversarial review** and says so in its header, in §0, in §7, and in its closing line. If Fable 5.1 is later approved, its review should be run *against* `llm-research-review.md` as the baseline it must improve on, and that document should then be marked superseded rather than quietly merged.

---

## 1. Confirmed facts

These are the load-bearing facts. Each is re-checkable against a named source.

### 1.1 What the reference product does — observed, not inferred

| # | Fact | Label | Where verified |
| :- | :- | :- | :- |
| 1 | The reference CLI is a native win32-x64 binary at version 2.1.306, with a documented `--help`, `doctor`, `mcp`, `plugin`, `agents`, `auto-mode`, and `--output-format json` surface. | **[FACT]** | `agent-reference-shots/cli-help/`, `cli-reference/` |
| 2 | The `stream-json` event vocabulary is `system/init`, `assistant/{text,thinking,tool_use}`, `user/tool_result`, `system/{permission_denied,task_started,task_progress,task_notification,hook_started,hook_response,compact_boundary,turn_duration,api_retry}`, and `result`. | **[FACT]** | `agent-reference-shots/sample-stream-json.txt`, `sanitized-tool-stream.jsonl` |
| 3 | There are **six** permission modes — `default` (UI label "Manual"), `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` — with `manual` an accepted alias for `default`. | **[FACT]** | `agent-reference-shots/docs-cache/permission-modes.md` |
| 4 | Permission evaluation is **deny → ask → allow**, first match wins, and the outcome does not depend on which scope the rule came from. | **[FACT]** | `agent-reference-shots/docs-cache/settings.md` |
| 5 | There are **33** hook events. Verified from four independent extractions; the docs summary table's 33 rows equal its 33 event-level sections. | **[FACT]** | `agent-reference-shots/docs-cache/hooks-guide.md` |
| 6 | The settings surface has **245 documented keys across 17 topical sections**, in 4 scoped files plus `~/.claude.json`. | **[FACT]** | `agent-reference-shots/docs-cache/settings-reference.md` |
| 7 | For **11** security-sensitive keys, the *most restrictive* value across all scopes wins. | **[FACT]** | `agent-reference-shots/docs-cache/settings.md` |
| 8 | A subagent's `skills:` field preloads the skill **body, not its frontmatter**. (An earlier claim that it preloaded the frontmatter was an artefact of the Read tool's own display, and was corrected.) | **[FACT]** | `agent-evidence.md` F10.13, `feature-checklist.md` S9-SKILL-013 |
| 9 | MCP has **4 transports** and 3 scopes / 2 storage files; tools are named `mcp__<server>__<tool>` and are **deferred-loaded** on demand. | **[FACT]** | `agent-reference-shots/docs-cache/mcp.md` |
| 10 | Compaction emits a `compact_boundary` with `preTokens`/`postTokens`, a monotonic `cumulativeDroppedTokens`, and UUIDs for the preserved segment and messages. | **[FACT]** | `agent-reference-shots/area7-model-context-sessions/` |
| 11 | The transcript is a **DAG** (uuid/parentUuid tree, `promptId` grouping, `turnPosition`), with 16 entry types. | **[FACT]** | `agent-evidence.md` F5.x |
| 12 | Skills use `SKILL.md` YAML frontmatter with three-level progressive disclosure. | **[FACT]** | `agent-reference-shots/docs-cache/skills.md` |

**What was deliberately not done, and why it matters.** The reference binary was **not** decompiled, disassembled, de-minified, or otherwise reduced to human-readable form; no source map was dumped; no credential store, keychain, licence file, or account data was read; and the model gateway was not reverse-engineered. The Anthropic Consumer and Commercial Terms prohibit reverse engineering and bar using the Services to build a competing product or to train competing models, and `code.claude.com/docs/en/legal-and-compliance` states that the Claude Code binary must not be modified. **Every fact in the table above was obtained from publicly documented functionality, direct black-box observation of the published CLI, the product's own self-description surfaces, and traffic on the account's own API boundary insofar as it is the documented Messages API.** The full method and its limits are in `agent-reference-shots/TERMS-NOTES.md` and `agent-reference-shots/PROTOCOL-NOTES.md`.

**This is the clean-room boundary, and it is the reason the evidence base is legitimate rather than a liability.**

### 1.2 What the local machine can do

| # | Fact | Label | How obtained |
| :- | :- | :- | :- |
| 13 | CPU: AMD Ryzen 7 5700U, 8 cores / 16 threads, base clock 1,801 MHz. **No CUDA; no discrete GPU.** | **[FACT]** | `Get-CimInstance Win32_Processor`, `nvidia-smi` → not found |
| 14 | RAM: 14,870,306,816 B = **13.85 GiB**. iGPU: 2 GB. Disk free: **159.2 GB**. OS: Windows 11 Pro. | **[FACT]** | `Get-CimInstance`, `Get-PSDrive` |
| 15 | PyTorch **2.14.1+cpu**; `torch.cuda.is_available()` → `False`. | **[FACT]** | `python -I -c "import torch"` |
| 16 | Measured FP32 GEMM: **1.72×10¹¹ FLOP/s** at n=1024 (1.30×10¹¹ at n=512). | **[FACT]** | local numpy matmul benchmark |
| 17 | Consequence: **R1 (360M) is categorically impossible locally** — 10,465 days at 10% efficiency. R0 (30M) takes 73–363 days. | **[ESTIMATE]** | `compute-feasibility.md` §11.2 |

### 1.3 What the compute arithmetic actually says

| # | Fact | Label | Where verified |
| :- | :- | :- | :- |
| 18 | `C = 6ND` reproduces Meta's published 3.8×10²⁵ FLOPs for Llama 3.1 405B at a ratio of **1.000**. | **[FACT]** | `compute-feasibility.md` §3.1 |
| 19 | Applying 6ND with *active* parameters to DeepSeek-V3 against its **published** 2.788M H800 GPU-hours implies **327 TFLOPS = 33.1% of H100 dense** — i.e. the 40% MFU assumption is a realistic central case, not an optimistic one. | **[ESTIMATE]** | `compute-feasibility.md` §3.5 |
| 20 | **Billed GPU-hours for a fixed FLOP budget are fleet-independent**: `f·(C/(f·r)) = C/r`, so `cost = (C/r)/3600 × price` and `wall-clock = (C/r)/3600 / fleet / 24`. Confirmed against two published anchors: Llama 3.1 405B on 16,000 H100s implies **45.0% MFU** (exactly the assumed figure) under this convention and **0.0% MFU** under the fleet-multiplied one. | **[ESTIMATE]** | `compute-feasibility.md` §3.4, `llm-development-roadmap.md` §0.4 |
| 21 | Corrected training costs: **R1 opt $97 · R2 opt $1,677 · R3 opt $36,514 · R3 ext $912,861 · R6 (H100) $94,566,427.** | **[ESTIMATE]** | `compute-feasibility.md` §3.4, re-derived and machine-verified |
| 22 | **The binding constraint is iteration count, not dollars.** R2 = 3.1 d/run (~60 experiments/year); R3 = 68.2 d/run (~4 experiments/year). | **[ESTIMATE]** | `compute-feasibility.md` §9 |

**Fact 20 and 21 were, until 2026-10-22, wrong in `compute-feasibility.md`.** The cost column was inflated by exactly 8× in every row, the GPU-hour column silently changed meaning between rows, and three extended rows' wall-clocks matched no consistent reading of their own adjacent cell. The correction, its arithmetic, its propagation through 14 dependent statements, and a machine-check that re-derives all 11 rows from the document's own stated inputs are in `compute-feasibility.md` §3.4 and `llm-research-review.md` §F3. **This is the single most important thing to know about the project's numbers: they were wrong until they were re-derived, and the re-derivation is now part of the document rather than a promise.**

---

## 2. Major uncertainties

Named, not hedged. Each has the specific measurement that would settle it.

| ID | Uncertainty | Status | What would settle it | Cost to settle |
| :- | :- | :- | :- | :- |
| **U-A** | **Does a licence-clean corpus of sufficient size and quality exist?** | **[UNKNOWN]** | The §9 five-item gate from `licensing-and-provenance-review.md`, run per candidate. Three measurements: token yield of the top single-licence candidates after filtering; the fraction of a large per-item-licence corpus that is unambiguously permissive; the yield of self-generated data at a realistic filter rate. | **A day of licence review, not a training run.** Move to Stage A. |
| **U-B** | **Is the Windows shell-AST approach viable?** The single largest schedule risk in the harness plan. | **[UNKNOWN]** | A 1-week Phase-0 spike parsing the shell forms the evidence base shows the reference product handling. | 1 week |
| **U-C** | **Does the "own model" reach a useful capability level at all?** | **[UNKNOWN]** | Stage C's loss curve and Stage E's R1-vs-SmolLM2-360M comparison. | Stages A–E |
| **U-D** | **How much of the agent's quality is the harness rather than the model?** | **[UNKNOWN]** | The champion/challenger shadow protocol in `benchmark-and-evaluation-plan.md` §12.3 — the same harness, two models. | Part of the evaluation budget |
| **U-E** | **Will the Unix and macOS behaviour match?** Only Windows was exercised in the investigation. | **[UNKNOWN]** | The nightly CI lanes, which exist to find this early rather than at Phase 5. | Continuous from Phase 1 |
| **U-F** | **Do the non-Anthropic providers' tool-calling semantics match ours?** | **[UNKNOWN]** | The provider adapter conformance suite against 2+ providers. | Part of Phase 1 |
| **U-G** | **Does the prompt-research collection's design-principle extraction hold up under independent implementation?** | **[UNKNOWN]** | Each of the 12 principle categories has its own implementation and test in `prompt-pattern-analysis.md` §5; the tests either pass or they do not. | Part of Phases 1–4 |

**U-A has a contingency now** (`training-data-plan.md` §2.2a, added 2026-10-22): four ordered branches, each *less capable but more expensive*, none of which weakens the absolute licence requirement. The least-bad branch turns out to be counter-intuitive: **an Apache-2.0 open model is a better teacher in the failure case than a corpus of thousands of unknown per-item licences**, because a teacher's licence travels into the data and an Apache-2.0 teacher's licence can be named and discharged. The honest floor, if no branch yields enough tokens, is to **train R1 instead of R2 and accept a smaller model rather than a licence-encumbered one.**

---

## 3. Resource requirements

### 3.1 The agent harness — implementable now, on the local machine

| Phase | Elapsed | Headcount | Effort | Gates |
| :- | :-: | :-: | :-: | :- |
| 0 — Architecture freeze + shell-AST spike | 2 wks | 3 | **6 pw** | M0 |
| 1 — Vertical slice | 6 wks | 3 | **18 pw** | M1, M2 |
| 2 — Parity core | 10 wks | 4 | **40 pw** | M3–M6 |
| 3 — Safety tier | 6 wks | 3.5 | **21 pw** | M7, M8 |
| 4 — Extensibility layers | 10 wks | 4.5 | **45 pw** | M9–M13 |
| 5 — Hardening and release readiness | 6 wks | 3.75 | **22.5 pw** | M14–M17 |
| | **40 wks** | | **≈152.5 pw** | |

**Monetary cost of the harness work: essentially zero in *out-of-pocket* terms** beyond CI and infrastructure. **This is the part of the project that needs no GPU, no API budget, and no approval to spend — but it is not free in labour**, and the distinction matters for reading this document: the harness is **165.8 person-weeks with contingency** (`implementation-plan.md` §9.4), which at $150k / $200k / $250k per engineer-year is **$478,269 / $637,692 / $797,115**. **[OBSERVED]** That labour figure is **2.7× Scenario B's entire model track** ($233,778) and **130× Scenario A's** ($4,884). The asymmetry is therefore not "the harness is free" — it is **"the harness costs people-time, and the model costs money; neither is free, and the harness is the larger of the two."**

### 3.2 The model track — requires approval at each rung

| Stage | What it produces | Compute | Cost | Wall-clock | Exit criterion |
| :- | :- | :- | :-: | :- | --- |
| **A** Tokenizer | Byte-level BPE, 32,768 vocab, trained on our corpus | Local CPU | **$0** | 1–2 wks | Round-trip exactness; ≥ 3.0 chars/token median on code; no dead merges |
| **B** Architecture + reproducible init | Config A/B/C parameterised and verified | Local CPU | **$0** | 1 wk | Parameter counts and init reproducibility re-derived from `research/spl/param_math.py` |
| **C** Small-scale pretraining baseline | Config A (100.7M params) on 2.0B tokens — demonstrably learns | 22 A100 GPU-h (local is 813 d — not viable) | **$60** | 0.3 h on 8×A100 | Loss decreases monotonically; a competence signal above the untrained baseline |
| **D** Data pipeline | Filtered, deduped, versioned, provenance-stamped corpus | CPU + storage | **$120–$250** | 2–6 wks | Reproducible corpus; hash-disjointness from the eval suite = zero intersections |
| **E** Scaling decision | R1 (360M) trained on our corpus | 35 A100 GPU-h | **$97** | 4.3 h on 8×A100 | **Beats SmolLM2-360M on our own DEV partition**, paired, with the discordance table reported |
| **F** Instruction tuning | A model that follows our harness's tool-call format | 321–801 A100 GPU-h | **$894–$2,236** | 0.7–1.7 d on 8×A100 | Tool-call format validity ≥ 99% |
| **G** Agentic behaviour | Multi-step, tool-using, failure-recovering | ~927 A100 GPU-h (4× resampling) | **~$2,586** | 1–2 wks | Tool-use accuracy and task-completion on the S1 suite |
| **H** Preference optimisation | Better behaviour on the specific target | DPO 5–327 GPU-h; RLVR 5,200–15,600 GPU-h | DPO **$14–$914**; RLVR **$14,500–$43,500** | 1–2 wks | Only if G shows a specific, named deficiency worth it |
| **I–K** | Long context, efficient inference, systematic evaluation | varies | **[$5–50k]** | ongoing | Per the roadmap's own gates |

**The dollar figures in square brackets are the ones that need a decision. Everything else in Stages A–F costs less than a laptop.**

### 3.3 What needs additional resources

| Need | Why | Cost | Gate before spending |
| :- | :- | :-: | :- |
| Rented GPUs (8×A100) | Stages E, F, G | **$97 → $2,586** for C–G; **~$15k–$43k** if Stage H RLVR is ever authorised | Gate 2 (the R1-vs-public comparison) |
| Object storage | The R2-scale corpus is 120 GB tokenised (560 GB at R3), exceeding the 159.2 GB local disk once raw source is added | **$11–$504/month** at $0.02–$0.09/GB/mo | Stage D design decision |
| A frontier-API evaluation baseline | `benchmark-and-evaluation-plan.md` requires comparing against a reference model | **$125,250** for a 3-seed × 10-variant SWE-bench sweep (Sonnet 5.5); **$20,875** for 1 seed × 5 variants; **$6,155** self-hosted at the matched 15,000-run workload — a **20.3×** advantage, not the 2,400× the document previously claimed | **A separate, explicit approval** — this is the single largest discretionary line in the project |
| Fable 5.1 review | The independent second opinion PART 9 asked for | **Billable; not priced here** | **Your explicit approval** |
| A second FTE security owner | Phase 3 onward | Salary | Part of headcount |

---

## 4. The first experiment

**The first experiment is not a model. It is a harness spike, and it is chosen to retire the largest unknown for the smallest cost.**

### 4.1 The experiment

**Name:** the Windows shell-AST viability spike (Phase 0, milestone M0).
**Question:** can a command be decomposed into its *operations* — not its spelling — reliably enough on Windows to enforce a permission rule by effect? The security model classifies by **effect** (read / mutate_local / execute / network / process_control / irreversible) and treats an indeterminate classification as `mutate_local`. A rule must match the operation, not the verb, and every subcommand of a compound command must be evaluated.
**Duration:** 1 week, 3 engineers.
**Cost:** **$0** and one week.
**Method:** take the shell forms the evidence base shows the reference product actually handling — quoted and chained commands, wrappers (`env`, `sudo`, `nohup`, `xargs`), pipes and redirections, `cmd.exe` vs PowerShell, Windows aliases (`where`, `type`, `del`), UNC and drive-letter paths, and `;`/`&&`/`||` compounds — and build a parser that yields a per-command operation list. A rule set then matches those operations.
**Acceptance criterion:** for every shell form in the corpus, the parser either produces a **complete** operation list or **declines** — and declining is a valid, safe answer. **There is no partial answer.** A parse that silently drops a subcommand is a security defect, not a limitation.
**Why this and not something else:** it is the one technical risk that could invalidate the Phase-3 safety design. Retiring it in week 1 costs a week; retiring it in week 20 costs the phase.

### 4.2 The second experiment — the one that produces a model

**Stage A + B + C.** The learning baseline is **Config A — 100,681,728 parameters** (L=12, d=768, 4:1 GQA, 32k vocab, tied embeddings), trained on **2.0B tokens** of a clean permissive slice. On 8×A100 that is **22 GPU-h ≈ $60 and 0.3 hours of wall-clock**; on the local CPU it is **813 days at 10% of measured peak — categorically out of reach**, so the *paid* part of Stage C is a single ~$60 run, and the local machine's role is Stages A, B, D and K (tokenizer, reproducible init, data pipeline, evaluation harness), all CPU-bound and free.

What Stage C establishes is only this: **does the loss curve fall, and does the eval harness move?** Not "is it good" — "does the machinery work and is it reproducible." The point is to remove every pipeline bug *before* the rental clock starts, because **pipeline bugs are what a small team burns a 68-day run on.** A smaller R0-class run (30M, 0.6B tokens, 2 GPU-h, $5) is available as a cheaper smoke test, but a 30M model is small enough that "it learned" is nearly vacuous, so it cannot substitute for the Config A run as the Stage C exit criterion.

---

## 5. Expected deliverables and acceptance criteria

### 5.1 The agent (Phase 1–5)

| # | Deliverable | Acceptance criterion |
| :- | :- | :- |
| D1 | `keel` core with the event union, tool registry, dispatcher, Tier-1 permission evaluator, tool-result renderer | `keel -p "…" --output-format stream-json` emits exactly one `system/init`, an assistant turn, a `user/tool_result` correlated by `tool_use_id`, and exactly one `result` |
| D2 | Determinism seams — fake model, fake clock, fake filesystem, fake tool executor | The same fixture produces **byte-identical** normalised output across 10 consecutive runs on 2 machines (M2) |
| D3 | Scoped settings resolver with the restriction lattice | A repo-committed file **cannot loosen** any security control; provenance printable for every key (M3) |
| D4 | Instruction discovery and delivery | Instructions arrive in the **user** role, never the system role; root→cwd order holds (M4) |
| D5 | Context lifecycle and compaction | The boundary event names the UUIDs of every preserved message; cumulative dropped tokens is monotonic; a thrash pattern is *detected*, not looped (M5) |
| D6 | Tier-2 safety envelope | **No settings key, mode, hook, or CLI flag disables the Tier-2 module** (M7) |
| D7 | Shell matching is semantic | A rule matches the *operation*; every subcommand of a compound is evaluated; a protected path is detected regardless of how the command reaches it (M8) |
| D8 | Safe skill loader | Injected commands in an untrusted skill are prompted or denied, never executed silently, and always logged (M9) |
| D9 | Hook bus | Exit 0 proceeds, exit 2 blocks, anything else proceeds and reports; a broken hook is distinguishable from a refusal (M10) |
| D10 | MCP client with 4 transports | A project-scoped server is **inert until approved**; approval is revocable; server annotations never widen host trust (M11) |
| D11 | Subagent delegation and parallel workers | The subagent's tool set is exactly the allowlist; the parent receives a summary, not the raw transcript; a worker cannot edit outside its worktree (M12, M13) |
| D12 | Cross-platform parity | All three CI lanes green for 10 consecutive runs (M14) |
| D13 | Adversarial suite | Every containment in the security plan's matrix has a passing test; no open critical or high finding (M15) |

### 5.2 The model

| # | Deliverable | Acceptance criterion |
| :- | :- | :- |
| M1 | Tokenizer | Round-trip exactness; ≥ 3.0 chars/token median on code (published comparators: StarCoder2 3.238, CodeGen-mono 3.017, DeepSeek-Coder 2.836, GPT-2 2.487) |
| M2 | Reproducible init | Parameter counts re-derived from `research/spl/param_math.py` match the model to the parameter |
| M3 | Learning baseline | Loss decreases monotonically over 200 steps; the eval harness gives the same number twice on the same checkpoint |
| M4 | Corpus | Hash-disjointness against **every** suite asset, dev and test, is **exactly zero** |
| M5 | R1 model | Beats SmolLM2-360M on our own DEV partition, **paired**, with the discordance table and per-task deltas reported; a single favourable aggregate is *not* a pass |
| M6 | Capability claim discipline | Every published number declares whether it measures the model, the harness, or the pair. A model that fails any part of the four-part own-model test is disclosed as `keel-own` with a `model_base` |

---

## 6. Risks

| # | Risk | Likelihood | Impact | Mitigation | Residual |
| :- | :- | :- | :- | --- | :- |
| R1 | **The reference product's behaviour is understood wrong.** | Medium | High | Every claim carries a label; the evidence base is black-box only; where a claim rests on the prompt collection it is marked **[UNKNOWN]** and never used as proof | Accepted |
| R2 | **Licence contamination in the corpus.** | Low | **Fatal** | §D.4-safe filter as a hard pipeline stage; per-item licence identification; ambiguous → excluded; the corpus is auditable by construction | Low, with U-A's contingency |
| R3 | **The shell-AST approach does not work on Windows.** | Medium | High | Phase-0 spike, week 1; declining is a valid answer; the safety model already treats indeterminate as `mutate_local` | Retired by the spike |
| R4 | **A capability claim gets made that the evidence does not support.** | Medium | High | The `[FACT]/[ESTIMATE]/[UNKNOWN]/[TARGET]` discipline; no benchmark score exists anywhere in the project because none has been run; the adversarial suite's explicit check | Low |
| R5 | **The 68-day run diverges on day 40.** | Medium | High | Validate the recipe at R2 (3 days, repeatable); run a **shortened R3** (~10 days) first; checkpoint every ~5% of training | Medium — this is why R2 precedes R3 |
| R6 | **Evaluation cost exceeds the training cost.** | **High** | Medium | A 3-seed × 10-variant frontier sweep is $125,250 vs $36,514 for the training run. **Evaluate your own model for the bulk; run the frontier baseline once per release** | High if unmanaged |
| R7 | **The model never becomes good enough to matter.** | Medium | Medium | The plan's own position: if the model loses to a rented frontier model on every dimension, **rent and spend the budget on the harness.** The harness is the durable asset | Accepted by design |
| R8 | **A hook, skill, or MCP server executes something malicious.** | Medium | **High** | Tier 2 is not configurable; skills are untrusted data; MCP servers are inert until approved; every containment has a test | Low |
| R9 | **Provider price or availability moves.** | Medium | Medium | Re-verify every price before any budget decision; keep 8×A100 as the default (broadest availability); never commit a schedule to a spot price | Low |
| R10 | **The project mistakes a harness win for a model win.** | **High** | High | The champion/challenger protocol; every number declares what it measures | **The highest-likelihood risk here, and it is a discipline risk, not a technical one** |

---

## 7. Proposed build order

**The order is a dependency order, and it is chosen so that the cheapest, fastest, most-reversible things come first.**

```
Phase 0  Architecture freeze + shell-AST spike        2 wk    6 pw    $0
   │      └─ retires U-B (the largest schedule risk)
   ▼
Phase 1  Vertical slice                              6 wk   18 pw    $0
   │      └─ the spine: event union, permission, tool result, transcript, determinism
   ▼
Phase 2  Parity core                                 10 wk   40 pw    $0
   │      └─ settings lattice, context delivery, compaction, commands
   ▼
┌─ IN PARALLEL FROM HERE ─────────────────────────────────────────────────┐
│                                                                          │
│  Model track (local, $0)          Harness track (local, $0)            │
│  A  Tokenizer          $0         Phase 3  Safety tier      6 wk 21 pw  │
│  B  Architecture       $0         Phase 4  Extensibility   10 wk 45 pw  │
│  C  Learning baseline  $0         Phase 5  Hardening        6 wk 22.5pw │
│  D  Data pipeline      $120                                                    │
│  E  R1 7.2B tokens     $97  ← requires your approval                    │
│     └─ gate: beats SmolLM2-360M on our own DEV partition                 │
│  F  Instruction tuning $894–$2,236                                            │
│  G  Agentic behaviour  $2–5k                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why the model track runs in parallel from Stage A rather than after the harness is finished.** Two reasons, and the second is the important one. First, Stages A–D cost **$120 and no GPU time** — they are the corpus work, the licence work, and the tokenizer work, and the licence work (U-A) is a *day of reading*, which is exactly the kind of unknown that is cheapest to retire early. Second, **the model track's Stage E gate produces the comparison that the harness track needs**: a 360M model that beats SmolLM2-360M on our own suite is evidence that the suite measures something real, and the same suite is what the harness's own improvements are measured against. Building the measurement apparatus first, and training something to measure it against, is a better order than building the apparatus and then discovering what it can distinguish.

**Why Phase 3 (safety) precedes Phase 4 (extensibility) and not the reverse.** `implementation-plan.md` §4.4 argues this in full; the short form is that the injected-command policy for skills and the Tier-2 analyser both *gate* the skill loader, so a loader shipped before the policy would need to be rewritten.

---

## 8. What can be implemented immediately, what needs more resources, and what cannot honestly be promised

### 8.1 Can start today, at no monetary cost, with no approval beyond this gate

- **Phases 0–2 of the harness** (0–18 weeks, 64 pw): the whole spine and the parity core, on the local machine, with the fake model and fake tool executor.
- **Stages A–D of the model track** (0–6 weeks, ~$120): tokenizer, architecture, the learning baseline, and the corpus pipeline — including retiring U-A.
- **The benchmark suite construction** (S0/S1 stages): 75 tasks at S0, then **400** at S1 (120 DEV / 40 TEST-A / 60 LIVE / 60 TEST-B / 120 reserve pool), split by repository, with the four held-out levels enforced. **[OBSERVED]** The suite grew from the earlier 220-task figure because the gate partition had to be **disjoint from both the tuning set (DEV) and the claim set (TEST-B)** — see the EVAL-03 row in the appendix.
- **The provider adapter** against 2+ non-Anthropic providers, using the local gateway already configured in this environment, which is a **free** tier.

### 8.2 Needs an explicit decision from you

| Decision | What it gates | Amount |
| :- | :- | :-: |
| **(a) Billable Fable 5.1 invocation** | The PART 9 requirement for an independent second opinion on the most consequential architectural, training, and evaluation decisions | **Unknown until priced.** `:batch` roughly halves it |
| **(b) The frontier-API evaluation baseline** | The external comparison `benchmark-and-evaluation-plan.md` requires | Up to **$125,250** for a full sweep. **A smaller one-seed × 5-variant sweep is $20,875** |
| **(c) Rented GPUs for Stages E–G** | The R1 model, the instruction-tuned model, the agentic-behaviour model | **$97 → $5,000** |
| **(d) Object storage for the R2-scale corpus** | 320 GB of raw + tokenised data vs 159.2 GB local | $11–$504/month |
| **(e) The Phase-1 provider target** | Which provider the first slice targets. `licensing-and-provenance-review.md` OPEN-Q1 recommends a **non-Anthropic provider as the zero-cost default**, with Anthropic as an optional evaluation-only accelerator. **I recommend following that** | $0 for a non-Anthropic provider |

### 8.3 What cannot honestly be promised

This section is the most important one in the document, because the project has been built on a discipline of not over-claiming, and that discipline has to apply to the plan too.

1. **No performance number of any kind is promised, for the model.** No model has been trained, no benchmark has been run, and the project contains **zero** fabricated scores by design. Every capability statement in the model track is a **[TARGET]** with a named exit criterion, not a prediction. "The 7B model will be competitive with public 7B code models" is the *aim* of Stage E, and the gate that decides whether it happened is the one that runs.
2. **No claim that this reaches or exceeds Claude Opus 5.5 or any frontier model is made, implied, or supported by anything in this project.** The plan's own honest position is the opposite: **most early capability arrives from the harness, the tool set, the context management and the measurement apparatus — long before it arrives from the weights.** `llm-development-roadmap.md` §13 says this, `agent-and-model-boundary.md` accounts for it line by line, and this gate endorses it. The durable asset is the instrument, not the weights.
3. **No timeline is promised beyond Phase 0's 2 weeks.** The 40-week harness schedule and the ≈152.5 pw effort are *estimates from a stated headcount*, not commitments, and they exclude the Unix/macOS surprises that U-E says to expect. The 68-day R3 run is the largest single schedule risk, and the plan's own mitigation is to not need it until the end.
4. **No legal conclusion is drawn.** `licensing-and-provenance-review.md` records the licence position of every corpus candidate and **four unresolved questions** that need counsel, not this project's reading. **This document makes no legal determination about any licence, and the absence of one is deliberate.**
5. **No claim that the harness is behaviourally identical to the reference product.** The evidence base is a black-box observation of a published CLI at one version, on one platform, at one point in time. Parity is defined in `feature-checklist.md` as a checklist with acceptance criteria per item — which is testable — and not as "indistinguishable."
6. **The independent-model track is not promised to succeed at scale.** U-A and U-C are open, and the plan's own contingency for the corpus failure case ends at "train a smaller model." A project that promised a competitive 7B code model on a $97 training budget would be making a claim its own arithmetic contradicts: the arithmetic says R2 is 3 days and R3 is 68 days, and *that* is the whole argument for R2.
7. **The independence claim is bounded, not absolute.** Under `AMB-304`/`AMB-305`, a model that fails any part of the four-part own-model test must be disclosed as `keel-own` with a `model_base`. If we ultimately ship a fine-tune of a published open model, **the product says so.** The licence-clean corpus (U-A) and the self-generated-data branch exist to make that disclosure unnecessary — not to avoid having to make it.

---

## 9. What is being asked of you

**Approve one of three scopes.** Nothing is spent until you do.

| Scope | What it buys | Cost | Wall-clock |
| :- | :- | :-: | :- |
| **S1 — Documentation only** | Stop here. Sixteen documents and the evidence base stand as the deliverable. | **$0** | — |
| **S2 — Harness first, model deferred** *(recommended)* | Phases 0–2, then the safety tier. Stages A–D of the model track in parallel. **No rented GPU, no billable API, no Fable invocation.** | **$0–$250** | 0–18 weeks to the first honest demo |
| **S3 — Full plan** | S2 plus rented GPUs for Stages E–G, plus the frontier evaluation baseline, plus a Fable 5.1 review. | **$5,000–$130,000** | 0–40 weeks |

**[OBSERVED] The scopes above price *out-of-pocket spend*, not labour.** The harness track's **165.8 person-weeks** is a real cost at $478k–$797k depending on the engineer-year rate, and it is the same in every scope — S1 stops before spending it, S2 and S3 both incur it. **S2's true cost is "$0–$250 of cash and 165.8 person-weeks."** A reader deciding between S1 and S2 on dollars alone is comparing the wrong numbers.

**And three yes/no questions on top of the scope choice:**

1. **Fable 5.1** — invoke it (billable), or keep the local adversarial review and label it as such? *Recommended: approve it for the five consequential decisions only (architecture, token budget, corpus strategy, evaluation design, own-model disclosure), batched, because the review's value is concentrated there and nowhere else.*
2. **Provider target for Phase 1** — the licensing review's OPEN-Q1 recommends a **non-Anthropic provider** as the zero-cost default. Agree?
3. **The frontier evaluation baseline** — a full 3-seed × 10-variant sweep is $125,250; a 1-seed × 5-variant sweep is $20,875; and evaluating **our own model** for the bulk of the sweep costs **$6,155** for the matched 15,000-run workload (a 20.3× advantage) or **$205** for a 500-run sweep. **Which do you want, and when?**

**No answer is required tonight.** The documents stand on their own; §8.1 lists what can be started the moment this gate is approved.

---

*Prepared 2026-10-22 at the end of the planning stage. **No application source code was created. No model was trained. No benchmark was run. No billable model call was made. No paid infrastructure was provisioned. Claude Fable 5.1 was not invoked and is not claimed as having been consulted.** The 16 project documents, the black-box evidence base in `agent-reference-shots/`, and the two reproducible verification scripts (`_check_effort.py`, `_check_security_coverage.py`) are the deliverables at this stage.*

---

## Appendix — what the adversarial review found, and what survived checking

The plan went through five independent adversarial lenses (security, evidence discipline, model feasibility, evaluation methodology, cost realism) which returned **86 findings**. Every finding was then checked against the source before being adopted, because a review that stops at the first error it can explain under-explains the error it found — and because a review agent working from a stale copy of a document will confidently cite line numbers that have moved.

**Four critical findings were confirmed by independent re-derivation and are now fixed:**

| Finding | Defect | Fix |
| :- | :- | :- |
| **EVAL-01** | The evaluation plan's McNemar power table (§10.1) was wrong by 2.5×–3.4× in the optimistic direction — MDE at n=200 is **10.5 pp at 30% discordance**, not the claimed 7–8 pp, and the error *grows* with the discordance rate the plan relies on. A 5 pp effect needs **n≈930–1,550**, not the claimed "300–400". | Table recomputed by exact binomial McNemar; §4.8, §7.2 and §11.3 updated. |
| **EVAL-02** | The release gates fire on measurement noise. At n=150 and 30% discordance, G1's 2.0 pp margin is **2.2× tighter than the 95% CI half-width (8.8 pp)**, falsely blocking a true null **33% of the time** while detecting a real 5 pp regression only **75% of the time**. The hard-band gate (G11) has SE **11.6 pp** against a 3 pp margin. | Gates restated as one-sided confidence-bound rules; a **false-block-rate column** added to §7.2 so each gate's noise floor is visible. |
| **EVAL-03** | Three mutually inconsistent statements about TEST-B: the baseline is "the champion on TEST-B", M3's exit requires the gates to "hold on TEST-B", and TEST-B is "opened last, after the release decision" and "does not block the release". No reading satisfies all three. | Resolved to a **rotating LIVE partition** drawn from RESERVE, with the champion baseline **re-measured in the same paired run**; TEST-B stays the final held-out set, opened once per release, informational only. The partition structure grew from four to **five** (DEV / TEST-A / **LIVE** / TEST-B / RESERVE) and the suite from 75 / 220 / 540 / 920 to **75 / 400 / 930 / 1,520** tasks. |
| **EVAL-04** | The plan's stage-sizing table and its claim-set accumulation table **disagreed about the same quantity**, because the stage table computed power with a *one-sided normal approximation* (the gate's test) while §10.3's claim rule is a *two-sided exact McNemar* test (the claim's test). At the S3 claim set (n=370) the two give **54%** and **45%** against a 5 pp effect — a 9-point gap, in the direction that flatters the claim. | Both tables now use the two-sided exact McNemar power. The rule is stated in the document: *the test used to compute the number must be the test the decision will be made with.* |
| **FEAS-03** | `compute-feasibility.md` §12's scenario **TOTAL rows did not equal the sum of their own line items** (Scenario B's High column overstated by **$102,277**; Scenario A's eval line understated by ~25×), and Scenario C **listed three alternative training fleets as three separate line items**, so adding the column counted the training cost three times. | All three scenarios rebuilt: two tables per scenario (one per token budget), every cell derivable from its own Calculation column, stated conventions (attempts = 1/2/3, storage = 1/3/6 months, contingency = 15% of subtotal), and an **engineering-labour line** added. Verification is reproducible: `research/spl/_check_scenarios.py` re-derives all 141 cells and exits non-zero on any mismatch. |
| **FEAS-01/02** | `compute-feasibility.md` §8.3's per-task prose said "~500k prompt tokens/task" while its own cost table implies **4,075,000** (an 8.15× contradiction), and the self-evaluation comparison matched **500 runs against 15,000**, overstating the advantage as "2,400×" when the matched figure is **20.3×**. The Scenario B table also multiplied a dollar figure by a GPU-hour price. | Prose corrected to the growth model; self-eval recomputed at matched workload (2,206 GPU-h ≈ $6,155 vs $125,250); Scenario B's eval row corrected to GPU-hours. |

**Two more critical findings were refuted on re-check** — the reviewers had read stale copies:

- **EV-01** claimed `claude-code-evidence.md` still asserted a "supports 29 hook events" quotation that does not exist. **It does not.** Line 84 of that document already carries the correction and the grep evidence for it; the finding was reading a pre-correction copy.
- **EV-03** claimed the "skills preload the whole `SKILL.md` including frontmatter" claim was still live. **It is not.** `agent-evidence.md` F10.13 (line 1566), `feature-checklist.md` S9-SKILL-013 and S10-AGENT-009 all carry the corrected finding — body, not frontmatter — with the original error explained as a Read-tool artefact.
- **EV-02** and **SEC-01/02/03** were similarly found to already be addressed in the current documents (the `Tool(param:value)` rule form is specified at `interface-spec.md:45093`; project-scope hooks are covered by C-15/C-37 and SC-9; the shell egress gap is stated explicitly at `security-plan.md:422`).

**The pattern in the refutations is worth recording, because it is a fact about method rather than about these particular findings.** Three of the six refuted criticals failed for the same reason: **the reviewer was reading a document that had already been corrected.** A finding that is *specific* (a quoted string, a line number, a test name) is only as good as the copy it was read from. The checks that survived — the arithmetic — were the ones that could be re-derived from first principles rather than from a copy.

**This is why the correction record lives in the documents and not in a summary.** Each confirmed defect carries a CORRECTION blockquote naming the old text, the recomputation, the method, and the change, so a reader who saw the old number knows it changed and can check why.

---

*One thing this review did **not** do, and could not: it did not consult Claude Fable 5.1. That model is billable, no approval was given, and it was not invoked. The five lenses above are a **local adversarial review**, and `llm-research-review.md` says so in its header, its §0, its §7, and its closing line. If Fable 5.1 is later approved, its review should be run *against* `llm-research-review.md` as the baseline it must improve on, and that document should then be marked superseded rather than quietly merged.*


## 17. Public benchmark references

This section records the public benchmarks and papers the plan is informed by. It exists so that a reader can see (a) where the plan's task-suite and statistical design follow established practice, and (b) exactly which public figures are being cited, in whose words, and with what caveats.

**Rules for this section, applied throughout:**

- Every figure is attributed to the source that states it. Where a figure is stated by a benchmark's own authors, it is labelled *stated by its authors*. Where it is computed by a third party on a leaderboard, it is labelled *third-party leaderboard*.
- **No figure is presented as this plan's result, and no external figure is a target for this plan's model.** Benchmarks measure; they do not predict. A score on a public benchmark says what a configuration did on that benchmark, in that harness, on that date.
- Where no public figure could be verified, the entry says **"no public figure found"** rather than omitting the item, so that a reader can tell the difference between "not applicable" and "not looked up".

<!-- RESEARCH_SECTION -->

---

## 18. Limitations of this plan

**PLAN:** a plan that does not state its own limits will be applied beyond them. The following are known and are not resolved by this document.

| # | Limitation | Consequence | Mitigation (and its own limit) |
| :- | :- | :- | :- |
| **P1** | The task suite is authored by the team and reflects the team's idea of software engineering | The suite is a sample of the team's world, not of the world | Route C human-authored tasks and the reserve corpus widen it; the corpus still reflects the team's domain. Not fully solvable from inside. |
| **P2** | The suite is small relative to the effect sizes of interest | 5-point differences need ~300–400 paired tasks (§10.1) | The staged size target (§4.8) reaches that by S2. Until then, the plan's own statistical rules prevent over-claiming. |
| **P3** | Contamination cannot be established or excluded | The clean/suspected distinction is probabilistic, not binary | Age cutoffs, post-cutoff construction, and the negative control (§4.6). These raise confidence; they do not prove cleanliness. |
| **P4** | The reference model is measured through a harness the team controls only imperfectly | The reference's score is a property of (model, harness) | The three-variant protocol (§9.4) and the two-directions rule (§9.5) make the attribution explicit; they do not remove it. |
| **P5** | Human evaluation is expensive, slow, and has a rater-agreement ceiling | The qualitative dimensions are measured with less precision than the automated ones | The rubric, the anchors, and the agreement threshold (§13.4). Below the threshold, the plan reports the disagreement rather than hiding it. |
| **P6** | The plan is written before any of the infrastructure it describes exists | Some thresholds and procedures will need revision once the machinery runs | The thresholds are defined relative to a measured champion, so they re-derive; the *procedure* (pairing, correction, reporting) is designed to be stable. |
| **P7** | The plan assumes a capable reference model is reachable and affordable | If it is not, M2's external baseline and M5's claims are unreachable | The plan says this plainly rather than substituting a cheaper reference and calling it equivalent. A cheaper reference is a different comparison and is labelled as one. |
| **P8** | The reference product's own behaviour was observed on a host with a third-party gateway, so first-party/subscription behaviour is documentation-only | Some reference behaviours are inferred, not measured | Those behaviours are used only for *design* guidance, never as benchmark oracles. |
| **P9** | The plan does not specify how to measure the *quality of the model's training* — only the quality of its output | A model can improve its benchmark score while its training gets worse | Out of scope. Noted so its absence is not read as a claim that it does not matter. |
| **P10** | The cost model assumes a per-token price schedule | For self-hosted models the "price" is a compute cost model, not a tariff | §16 requires a stated, dated cost basis. An internal compute cost model is acceptable provided it is documented and applied identically to all arms. |

---

## 19. Open questions this plan does not resolve

**PLAN — these are recorded so that they are decided deliberately rather than by default:**

1. **Which task families actually predict user satisfaction?** The plan assumes the nine families are the right decomposition. This is unverified and would benefit from correlating family-level results with a real-world satisfaction signal.
2. **What is the right relationship between pass@k and pass@1 for an agent?** An agent's trajectory is a single path through a state space, and retries are qualitatively different from parallel sampling. The plan scores single trajectories; whether that is the right unit is open.
3. **How should a partial-credit rubric be defined across families?** `M-D8-02` is a hybrid metric with a rubric component; the rubric per family does not yet exist.
4. **What is the right difficulty-band rubric for F7 and F9, where the work is qualitative?** The bands for F1–F6 are tractable; F7's "long horizon" needs a definition that does not depend on a model's behaviour.
5. **Should the suite include non-code tasks?** The plan is coding-focused by construction. An agent that is good at coding and bad at clarifying is a shape the plan measures but does not fully address.
6. **What is the right reference-model variant when the reference model is only reachable through the reference product's own harness?** Variant B requires emulating a harness the team has studied but not built. The fidelity of that emulation is itself a variable, and the plan has no answer for measuring its fidelity.
7. **How should the plan handle a model that improves the *harness* rather than the model?** A team that tunes the harness gets better numbers without a better model. The fingerprint diff makes this visible per-change; no aggregate measure of "harness contribution" exists.
8. **What is the minimum viable human panel?** §13.4 gives agreement thresholds, not panel size. The power of a human-panel comparison at n = 30 tasks is not established.

---

## 20. Closing statement

The plan's whole argument is one sentence, repeated because it is the sentence that is easiest to forget:

> **An agent's result is a function of prompt + tools + model + harness. A comparison that does not control all four is not a comparison.**

Everything mechanical in this document — the fingerprints, the paired runs, the task schema, the leakage log, the pre-declared metric families, the safety hard gates, the cost accounting, the mandatory "what this does not show" statement — exists to make that sentence operational, and to make the specific ways of fooling oneself (§15) either detectable or structurally impossible.

The reference product's own evidence base is a useful guide here, not because it is the thing being copied but because of what it demonstrates about harnesses in general. A harness is not a thin wrapper around a model. It is a security boundary, a context-budget manager, a configuration resolver, a cost ledger, and an extension surface — and every one of those is a place where a measurement can be wrong in a way that looks like a model result. The reference evidence records 33 of its own limitations and 44 unresolved questions about its own internals, all while being a mature, widely-used product. The lesson is not that the reference is inadequate; it is that **a harness's own behaviour is part of what you are measuring**, and the only durable response is to pin it, fingerprint it, and report it beside every number.

The plan is written to be used rather than admired. It is a set of gates, a schema, a comparison protocol, and a long list of the ways to fail — with thresholds that are re-derived from measurement rather than asserted, and claims that are drawn from a closed vocabulary.

---

## Appendix A — Evidence file index

Paths are relative to `C:\Users\Admin\Desktop\Claude clone\`.

| Path | Used for |
| :- | :- |
| `agent-evidence.md` | The primary evidence: §3 Capability Map, §4 findings, §5 Capability Tables, §6 Limitations (L1–L33), §7 Unresolved Questions (U1–U40), §8 Clean-Room Opportunity, §9 Recommended Scope, §10 Confirmed Capabilities (178), §11 Unknowns (44) |
| `agent-reference-shots/areas/area2-project-context.md` | F2.x findings (project context, `Read`/`Glob`/`Grep` contracts) |
| `agent-reference-shots/areas/area3-planning.md` | F3.x findings (plan mode, task DAG, delegation) |
| `agent-reference-shots/areas/area5-bash-permissions.md` | F5.x findings (command proposal, output truncation ladder, permission prompts) |
| `agent-reference-shots/areas/area6-tests-errors.md` | F6.x and F9.x findings (error contract, exit codes, MCP surfaces) |
| `agent-reference-shots/areas/area7-model-context-sessions.md` | F7.x findings (model resolution, effort, compaction, resumption) |
| `agent-reference-shots/areas/area8-permissions.md` | F8.x findings (deny-first evaluation, two deny semantics, Tier 2) |
| `agent-reference-shots/areas/area9-mcp.md` | F9.x findings (transports, scopes, naming, deferred loading) |
| `agent-reference-shots/areas/area10-skills.md` | F10.x findings (discovery, invocation control, template language) |
| `agent-reference-shots/areas/area12-dependencies.md` | F12.x findings (dependency tiers, `ANTHROPIC_BASE_URL` as feature gate) |
| `agent-reference-shots/areas/area-model-config.md` | Model/effort configuration surface |
| `agent-reference-shots/areas/area-full-multiarea.md` | F3b.x (parallel agents), F4.x (file editing), Area 3b/6 parallel-agent chapters |
| `agent-reference-shots/areas/area1-agent-loop.md` | The 49-event agent-loop census and the ten implementable facts |
| `agent-reference-shots/PROTOCOL-NOTES.md` | Wire formats: `tool_use`/`tool_result` correlation, `tool_result_meta[].permission_decision`, `structuredPatch`, `Glob` truncation flags, `userModified` |
| `agent-reference-shots/print-mode-json-result.json` | The ~40-field result envelope; `usage` vs `modelUsage`; `costBasis: "unknown"`; `subagent_stats` |
| `agent-reference-shots/sample-print-json-result.json` | `usage` and `modelUsage` key inventories (including `fallback_credit`, `inference_geo`, `iterations`, `speed`) |
| `agent-reference-shots/stream-json-basic.jsonl` | Event vocabulary census: `system/init`, `assistant`, `user`, `system/thinking_tokens`, `result` |
| `agent-reference-shots/cli-reference/stream-json-init-event.json` | The `system/init` capability manifest used for the harness fingerprint |
| `agent-reference-shots/cli-reference/print-mode-json-envelope.json` | A real captured envelope, including `total_cost_usd` and per-model `modelUsage` |
| `agent-reference-shots/tool-error-contract.json` | The error-and-denial contract, and the model's visible course-correction across consecutive failures |
| `agent-reference-shots/denied-tool-results.json` | `dontAsk` denial text; the deferred-tool `InputValidationError` with its "Load the tool first" remedy |
| `agent-reference-shots/tool-result-dual-representation.json` | The typed-success / string-failure dual representation, and `is_error` semantics |
| `agent-reference-shots/model-access-pricing.json` | The captured model catalogue (139 selected of 468 listed) with per-token prices and context lengths; the source of the "cost basis may be unknown" hazard |
| `agent-reference-shots/docs-cache/context-window.md` | What survives compaction; the five context sources and their load timing |
| `agent-reference-shots/docs-cache/checkpointing.md` | Checkpoint semantics and their stated limitations (Bash changes, subagent edits, external changes, symlinks not tracked) |
| `agent-reference-shots/docs-cache/costs.md` | Token-usage reduction strategies; agent-team token costs |
| `agent-reference-shots/docs-cache/data-usage.md` | Data-flow and telemetry boundaries by provider |
| `agent-reference-shots/docs-cache/feature-availability.md` | Provider/plan-dependent feature availability (fails by subtraction) |
| `agent-reference-shots/docs-cache/permission-modes.md` | The six permission modes and their semantics |
| `agent-reference-shots/docs-cache/sub-agents.md` | Delegation contract; tool allowlists; output scanning; concurrency limits |
| `agent-reference-shots/docs-cache/worktrees.md` | Isolation model and its four-check enforcement layer |
| `agent-reference-shots/docs-cache/workflows.md` | Orchestration limits, journal schema, and workflow cost behaviour |
| `agent-reference-shots/docs-cache/skills.md` | `SKILL.md` frontmatter contract; discovery scopes |
| `agent-reference-shots/docs-cache/mcp.md` | Transports, scopes, tool annotations, elicitation |
| `agent-reference-shots/docs-cache/hooks-guide.md` | Hook event semantics and the exit-code verdict convention |
| `agent-reference-shots/docs-cache/memory.md` | Instruction discovery, concatenation, path-scoped rules, auto-memory caps |
| `agent-reference-shots/docs-cache/errors.md` | The error taxonomy, retry taxonomy, and the "response may be incomplete" path |
| `agent-reference-shots/docs-cache/cli_reference.md` | CLI flags, including `--max-turns`, `--max-budget-usd`, `--bare`, `--restricted`, `--effort`, `--autocompact`, `--tools`, `--permission-mode` |
| `agent-reference-shots/cli-reference/claude-help-full.txt` | The `--help` output used to enumerate the pinnable CLI surface |

## Appendix B — Glossary of the plan's own terms

| Term | Definition in this plan |
| :- | :- |
| **Configuration** | The complete tuple (prompt, tools, model, harness, environment, budget, seed) that determines a run. |
| **Arm** | One configuration in a comparison. |
| **Champion** | The configuration currently serving users; the comparison baseline. |
| **Challenger** | A candidate configuration being evaluated against the champion. |
| **Fixture fingerprint** | SHA-256 over the pinned configuration plus the task manifest (§6.5). The primary key of a result record. |
| **Tool fingerprint** | Per-tool hashes of schema and description, plus the system-prompt and permission-rule hashes (§6.2). |
| **Harness variant** | A/B/C (§9.4) — which harness drove the model. Travels with every score. |
| **Task partition** | DEV / TEST-A / TEST-B / RESERVE / REG (§5.2, §12.2). |
| **Discordant pair** | A task where exactly one of the two arms passed. The unit of McNemar's test. |
| **Claim strength** | none / within-noise / improvement / regression / inconclusive (§10.3). |
| **Hard gate** | A threshold whose failure blocks a release (§7.2). |
| **Soft target** | A threshold that is tracked and reported but does not block. |
| **Automatic metric** | A metric a program can produce from the run record alone. |
| **Hybrid metric** | A metric with both a deterministic component and a rubric component, reported as two numbers. |
| **Human-judged metric** | A metric produced only by a named rater applying a written rubric. |
| **Harness metric / leaderboard figure / human judgement** | The three kinds of number kept separate throughout (§1.2). |
| **Boundary statement** | The mandatory "what this does not show" field of every report (§8.7, §14.3). |
| **Reserve corpus** | A separately-sourced, quarantined task set held for replacing a compromised held-out set (§5.4). |
| **Regression corpus** | A small, permanent, fast set of known failures, run on every commit (§12.2). |
| **Shadow run** | A challenger run on the benchmark suites with no user traffic and no production side effects (§12.3). |
| **Canary** | A staged ramp of a promoted challenger into real traffic, with pre-written rollback triggers (§12.4). |
| **Leakage audit** | The per-release check of §5.3, including training-data disjointness. |

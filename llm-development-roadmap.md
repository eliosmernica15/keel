# LLM Development Roadmap — Building an Independent Code-Oriented Model

**Project:** an independent clean-room coding agent, and an independent code-oriented language model to drive it.
**Document type:** Planning / roadmap. Documents only — no model has been trained, no GPU rented, no billable API called.
**Date written:** 2026-10-21.
**All prices observed on:** 2026-10-21 (unless otherwise stated). **Re-verification required before any budget decision.**

---

## How to read this document

Every quantitative or behavioural claim carries one of six tags. The first three are the same three the rest of the project uses; the last three are the tags `agent-evidence.md` and `claude-code-evidence.md` use.

| Tag | Meaning | Requirement |
|---|---|---|
| **[KNOWN FACT]** | Taken from a citable public source. | URL + observation date inline. |
| **[ESTIMATE]** | Derived here from cited facts. | The arithmetic is shown. |
| **[SPECULATIVE TARGET]** | A goal or aspiration. Never a forecast. | Labelled as such. |
| **[OBSERVED]** | Measured or verified in this project's own evidence base. | Cite the file + section. |
| **[INFERRED]** | A conclusion from observed facts. | The inference is stated. |
| **[UNKNOWN]** | Not determinable from the material examined. | Named, not filled in. |

**Where I could not find a public figure, this document says "no public figure found" rather than inventing one.**

### 0.1 Document map, and what this document does NOT duplicate

This is the Part 4 deliverable: the **model-development** roadmap. It covers what happens at layers **L0 (model architecture & weights)**, **L1 (data preparation & training)** and **L2 (instruction tuning & evaluation)** of `architecture.md` §2.1, plus the inference-side work at **L3** that the roadmap's own weights require.

| Question | Answered by |
|---|---|
| How much compute does a rung cost, on what hardware, with what arithmetic? | `compute-feasibility.md` §2–§5, §11–§12 — **cited, not restated**. |
| Is a corpus legally usable, and what provenance must it carry? | `licensing-and-provenance-review.md` §8–§9 — **cited, not restated**. |
| What is measured, on what task suite, with what statistical power? | `benchmark-and-evaluation-plan.md` §3–§11 — **cited, not restated**. |
| What is the harness/model split; which principles are model capabilities? | `agent-and-model-boundary.md` — **written; its `AMB-2xx` / `AMB-3xx` rules are cited directly in §2.4 and in the stage gates below.** |
| What does the *product* do, and how is it built? | `architecture.md`, `interface-spec.md`, `implementation-plan.md`, `feature-checklist.md`, `security-plan.md`, `test-plan.md`. |

**This document owns:** the *stage sequence*, the *gate* at each stage, the *dataset properties / parameter scale / compute / memory / storage / engineering complexity* for each stage, the *capability-lever attribution table*, the *stage dependency map*, the *kill criteria*, the *cheap-alternative-first* column, and the *explicit statement of what the roadmap cannot deliver*.

### 0.2 A correction to an upstream document, made before anything here depends on it

**[OBSERVED]** While deriving the stage budgets below, I recomputed `compute-feasibility.md` §3.4 from its own stated inputs (6ND, A100 dense BF16 312 TFLOPS, 40% MFU, $2.79/GPU-h, H100 989.5 TFLOPS, 45% MFU, $3.99/GPU-h) and found its **cost column inflated by exactly the fleet size**, while its **wall-clock column is correct**.

**[ESTIMATE] The arithmetic.** Total billed GPU-hours for a fixed FLOP budget is *fleet-independent*. If a fleet of *f* GPUs sustains rate *r* FLOP/s each and must absorb *C* FLOPs, then wall time *T = C/(f·r)*, and billed GPU-hours = *f·T = f·C/(f·r) = C/r*. The *f* cancels, so `cost = (C / r) / 3600 × price` is independent of fleet size. `compute-feasibility.md` §3.4 instead computes `cost = (C/r)/3600 × fleet × price`, multiplying by the fleet a second time. Its §3.5 cross-check against DeepSeek-V3's *published* 2.788M H800 GPU-hours uses the **correct** convention and lands at ~33% MFU — so §3.4 and §3.5 in the same document use different conventions.

**[ESTIMATE] Decisive public anchors:**

| Anchor | Published | Under §3.4's convention | Under the fleet-independent convention |
|---|---|---|---|
| Llama 3.1 405B, 16,000 H100s, 3.8×10²⁵ FLOPs (Meta, arXiv 2407.21783) | 16,000 H100s, multi-month | **0.1 TFLOPS sustained = 0.0% MFU** | **445 TFLOPS = 45.0% MFU** — exactly the 45% the document assumes for H100 |
| DeepSeek-V3 (2.788M H800 GPU-h published) | 2,788,000 H800-h | — | **327 TFLOPS = 33.1% of H100 dense** — matches §3.5's own cross-check |

**[INFERRED — HIGH confidence]** The fleet-independent convention is correct, and §3.4's *cost* column is inflated by 8× for its 8-GPU rows and 4,096× for its R6 row. The *wall-clock*, *FLOPs*, *MFU assumption*, *GPU-hour-per-GPU* columns and the §3.5 cross-check are all correct and are what I use throughout.

**[INFERRED — HIGH confidence]** **This changes no conclusion in `compute-feasibility.md`.** Its headline verdicts concern *reachability and iteration count*, and both survive: R2 remains ~3 days on 8×A100, R3 remains ~68 days, R4 remains impractical, R5/R6 remain out of reach. What changes is the *dollar* column: every 8-GPU row's cost drops by 8×. Corrected central costs: **R1 opt $97 · R2 opt $1,677 · R3 opt $36,514 · R3 ext $912,861 · R6 (H100, 4,096 GPUs) $94,566,427.**

**[ESTIMATE] The same correction propagates into the upstream scenarios, and one headline verdict changes.**

| Scenario | Upstream central (pre-fleet-fix) | Corrected central | Further corrected (2026-10-22) |
|---|---|---|---|
| **A** — R1 proof-of-life, optimal tokens | $1,817 | **~$1,290** | **$4,884** (model track) |
| **A** — R1 extended (600B tokens) | $65,900 | **~$17,190** | **$23,514** (model track) |
| **B** — R3 7B, 140B tokens (recommended) | $844k | **~$332,000** | **$233,778** (model track) |
| **B** — R3 7B, 3.5T tokens | $14.8M | **~$1.11M** | **$2,255,096** (model track) |
| **C** — R6 405B, frontier comparison | **$4.0×10¹¹** | **~$1.22×10⁸** | **$122,006,427** |

> **[OBSERVED] Second correction (2026-10-22) — the "Corrected central" column above was itself an approximation, and the upstream scenarios have now been rebuilt from their line items.** The middle column was an *estimate* of what the fleet fix would do to each scenario total, computed without re-deriving the scenarios' own line items. Re-deriving them exposed a second class of error: **Scenario A and B's TOTAL rows did not equal the sum of their own line items** (Scenario B's High column was overstated by $102,277), **Scenario A's eval line was understated by ~25×** ($250 for a workload that costs $3,758 at §8.3's own $8.35 per agent run), and **Scenario C listed three alternative training fleets as three separate line items**, so a reader adding the column would count the training cost three times. `compute-feasibility.md` §12 now has two tables per scenario (one per token budget), every cell derivable from its own Calculation column, every TOTAL equal to the sum of the line items above it, and a stated convention set (attempts = 1/2/3, storage = 1/3/6 months, contingency = 15% of subtotal). **Verification is reproducible:** `PYTHONIOENCODING=utf-8 python -I research/spl/_check_scenarios.py` re-derives all 141 cells and exits non-zero on any mismatch.
>
> **[INFERRED]** The correction moves the numbers in *both* directions, and the net verdict is unchanged but sharper. Scenario B's central model track came **down** ($332,000 → $233,778) because the eval and storage lines were previously understated as well as the training line being overstated. Scenario A's came **up** ($1,290 → $4,884) because its eval line was badly understated. And the column that no earlier version of this table had: **engineering labour**. `implementation-plan.md` §9.4's 165.8 person-weeks is **$637,692** at $200k per engineer-year — which is **2.7× Scenario B's entire model track** and **130× Scenario A's**. **[INFERRED]** The project's cost is dominated by the harness and the evaluation apparatus, not by the GPUs, and every scenario in this document should be read as *"model track + labour, calendar = max of the two."*

**[INFERRED — HIGH confidence]** **Scenario C's headline verdict changes, and this is the most consequential consequence.** `compute-feasibility.md` §12 calls Scenario C *"approximately the scale of a national-lab programme"* with *"$387 billion"* of compute alone. That is an artefact of the error: 23.7M H100-hours at $3.99 is **$94.6M**. The corrected total of **~$122M** — $94.6M training, $12M staff, $5M serving — is still far beyond this project but is *not* a national-lab number; it is closer to a well-funded industrial lab's frontier run. **[INFERRED]** The upstream *"national-lab programme"* sentence should be retired. **[INFERRED]** The verdict that Scenario C is **out of reach for this project** is unaffected, because it depends on the *staff* line and on having four engineers rather than thirty to sixty.

**[INFERRED]** The correction makes the build case *more* favourable on cost and *unchanged* on feasibility. **[OBSERVED] Correction (2026-10-22).** This paragraph previously read *"It is recorded here rather than silently patched upstream, because this document must not build on numbers it knows to be wrong."* That sentence was accurate when written and is now stale: **the upstream `compute-feasibility.md` §3.4 has been corrected**, its cost column no longer multiplies by the fleet, and the corrected values are what the budgets below use. The record of the error is retained (it is evidence about which convention was applied where), but the forward-looking statement has changed to the rule the correction actually established: **a downstream document that discovers an upstream error records it and cites the corrected value; it does not build on the old number, and it does not keep asserting that the upstream is unpatched once it has been patched.**

**[OBSERVED]** The upstream wall-clock figures this roadmap *does* depend on — R2 = 75 h on 8×A100, R3 = 68 d on 8×A100, R3 = 19 d on 8×H100 — are reproduced exactly by the corrected arithmetic and are used as-is.

## 1. The shape of the roadmap

### 1.1 Eleven stages, and why they are in this order

The order is a **dependency** order, and each stage's gate is a *measurement*, not a judgement.

| Stage | What it establishes | What blocks it |
|---|---|---|
| **A** | A tokenizer whose cost per token of code is measured, not assumed | nothing (starts immediately, costs almost nothing) |
| **B** | A reproducible initialisation: same seed → same weights, byte-identical | A (vocab size determines embedding shape) |
| **C** | Proof that the training loop *learns* | A + B + a minimal corpus |
| **D** | A corpus that is legal, deduplicated, and uncontaminated | C (you cannot filter a corpus you have not proven you can train on) |
| **E** | Scale, only where measurement justifies it | D (scaling amplifies whatever data defect exists) |
| **F** | Instruction and code-specific behaviour | E (or D at small scale) |
| **G** | Tool-use, multi-step, agentic behaviour | F + a working harness to generate trajectories |
| **H** | Preference optimisation / RL — *only where technically justified* | F or G + a verifier |
| **I** | Long context, memory, inference-time improvements | E (context extension is a training-phase change) |
| **J** | Efficient inference: quantisation, checkpointing, deployment | E (needs a trained model to quantise) |
| **K** | Systematic evaluation, failure analysis, targeted retraining | **everything** — it is the feedback loop that closes the roadmap |

**[INFERRED]** Stage K is listed last because it is *simultaneously* the first thing to build. The `benchmark-and-evaluation-plan.md` apparatus must exist before Stage C, or Stage C has no exit criterion and the roadmap becomes unfalsifiable. The order above is a *dependency* order for the model work; the *build* order interleaves K from the start.

### 1.2 The compute ladder this roadmap uses

**[OBSERVED]** The ladder is `compute-feasibility.md` §2.1, with the cost column corrected per §0.2 above. **Wall-clock is the primary axis, because the binding constraint is iteration count, not dollars.**

**[OBSERVED] A warning about reading this table.** These are the **planning ladder's nominal rungs** — 1.5 B and 7 B are *budgeting* numbers chosen to anchor each rung to a published model. **They are not the sizes this roadmap trains.** The actual architecture is Config B at 1.149 B and Config C at 7.248 B, and §7.3 budgets those at their own parameter counts. **[INFERRED]** The two must not be interchanged, and the original error in this document came from interchanging them. Where this document says "R2", read it as "the R2 rung of the planning ladder"; where it says "Config B", read it as "the model we actually build".

| Rung | Params | Token budget (opt) | 6ND FLOPs | Wall on 8×A100 | Wall on 8×H100 | Cost (corrected) | Iterations/yr (2 people) |
|---|---|---|---|---|---|---|---|
| **R0** | 30M | 0.6B | 1.08×10¹⁷ | 1.8 min | 0.5 min | **$0.67** | ~365 |
| **R1** | 360M | 7.2B | 1.56×10¹⁹ | 4.3 h | 1.2 h | **$97** | ~365 |
| **R1-ext** | 360M | 600B | 1.30×10²¹ | 15 d | 4.2 d | **$8,048** | ~24 |
| **R2** | 1.5B | 30B | 2.70×10²⁰ | **3.1 d** | 21 h | **$1,677** | ~119 |
| **R2-ext** | 1.5B | 300B | 2.70×10²¹ | 31 d | 8.8 d | **$16,767** | ~12 |
| **R3** | 7B | 140B | 5.88×10²¹ | **68 d** | 19 d | **$36,514** | ~4 |
| **R3-ext** | 7B | 3.5T | 1.47×10²³ | 1,704 d | 478 d | **$912,861** | ~0.2 |
| **R4** | 15B | 300B | 2.70×10²² | 313 d | 88 d | **$167,668** | ~1 |
| **R5** | 70B | 1.4T | 5.88×10²³ | 6,816 d | 1,910 d | **$3,651,442** | ~0.05 |
| **R6** | 405.9B | 15.6T | 3.80×10²⁵ | 440,430 d (8×A100) | 123,442 d (8×H100) | **$235,929,375** | ~0 |

**[OBSERVED] The cost column's convention, stated so R6 is not misread.** Every row's *Cost* cell is the **A100** bill (`total GPU-h × $2.79`), matching the *Wall on 8×A100* column; the *Wall on 8×H100* column is the alternative accelerator's wall-clock at the **same** billed GPU-hours scaled by H100's higher throughput — and because the two price points differ, an H100 fleet's *dollars* differ too. **[KNOWN FACT]** R6 on 4,096×H100 is **241 days** at **$94,566,427** (the Scenario C figure in `compute-feasibility.md` §12); on 8×H100 the same run is **123,442 days** at the **same $94,566,427**; on 8×A100 it is **440,430 days** at **$235,929,375**. **[INFERRED]** More GPUs buys time, not money — and the cheaper accelerator buys neither time nor money at this scale, only a larger bill.

**[OBSERVED] Four cells were corrected on 2026-10-22** against `compute-feasibility.md` §3.4's corrected table: R0's cost ($1 → $0.67) and R5's ($3,652,000 → $3,651,442, a rounding difference), R2-ext's H100 wall-clock (5.0 d → **8.8 d** — the old value was inconsistent with its own adjacent GPU-hour cell, one of the defects `llm-research-review.md` F3-extended documents), and R6's two cells. R6's *Wall on 8×H100* cell was quoted as "241 d (4,096 GPUs)" — a real figure, but placed in the 8-GPU column, where the correct value is **123,442 d**; and its *Cost* cell carried the 4,096-H100 bill (**$94,566,427**) in a column whose other rows are A100 bills. **[INFERRED]** Neither error changed a verdict — R6 is out of reach on every reading — but a table whose columns mix accelerators is a table that cannot be quoted, and this one is meant to be quotable.

**[ESTIMATE] The iteration-count column.** Using `compute-feasibility.md` §9's stated team assumption (2 people, one of whom can write distributed training code) and the observation that "a team of 2 gets roughly 4 runs in a year" at 68 d/run:

- R2 (3.1 d/run): 365 / 3.1 ≈ **119 runs/year**.
- R3 (68 d/run): 365 / 68 ≈ **4 runs/year**.
- R3-ext: **one run every four years.** This is not a development programme; it is a lottery ticket with a 68-day latency.

**[OBSERVED]** The iteration-count column above is **ladder-basis** (`365 / wall-clock` on a dedicated 8×A100 allocation). On the **Config basis** — the models this roadmap actually builds — the same arithmetic gives **~152 runs/yr at Config B** (365 / 2.40 d) and **~5.2 runs/yr at Config C** (365 / 70.6 d). **[INFERRED]** The direction is the same on both bases, which is the point: **the ladder and the configs agree that R3-class work is not a development process.**

**[INFERRED] This single table is the roadmap's most important content.** The choice between R2 and R3 is not a capability choice — a 7B model is genuinely more capable than a 1.5B model. It is a *process* choice: R3 permits four experiments per year, and model development is made of experiments. The correct target is **R2**, with R3 held as a conditional stretch that is only authorised if the R2 gate is passed and a specific, non-speculative use case is written down.

### 1.3 The local machine's role

**[OBSERVED]** Local hardware (measured 2026-10-21, `compute-feasibility.md` §11.1): AMD Ryzen 7 5700U, 8c/16t, 13.85 GiB RAM, AMD iGPU 2 GB, **no CUDA**, `torch 2.14.1+cpu`, measured FP32 GEMM **1.72×10¹¹ FLOP/s** at n=1024, 159.2 GB free disk, Windows 11.

**[ESTIMATE] What it can actually do**, recomputed against the measured 1.72×10¹¹ FLOP/s peak:

| Task | Local cost | Verdict |
|---|---|---|
| Tokenizer training (Stage A) | hours | **Do it here.** Free, and the highest-leverage artefact in the roadmap. |
| Data pipeline: crawl, filter, dedup, tokenise (Stage D) | 200–2,000 CPU-hours | **Do it here**, on free cloud CPU if the corpus is large. |
| R0-class training (30M, 0.6B tok) | C=1.08×10¹⁷; at 10% of peak **73 days**; at 2% **363 days** | **Marginal.** Cut the token budget to ~50–100M tokens and it becomes a weekend *pipeline* test, not a *learning* test. |
| Anything at R1 (360M) | 6.48 GB state fits in RAM; compute is **10,465 days** at 10% efficiency | **Categorically impossible.** |
| Anything at R2+ (1.5B) | 27 GB state vs 13.85 GB RAM | **Impossible on both compute and memory.** |
| Inference of the trained model | ROCm on Ryzen is a supported inference path | **Viable and useful** — where local deployment gets validated. |

**[INFERRED]** The local machine's real value is **Stages A, B, D and K** — tokenizer, reproducible init, data pipeline, evaluation harness — all CPU-bound, all free, and all where the schedule risk actually lives. Its *training* value is limited to a pipeline smoke test. **The local machine does everything except the training run, and the training run is the cheapest part of the programme in dollar terms.**

### 1.4 The architecture candidates

**[OBSERVED]** Three reference configurations are already derived in this project's `research/spl/param_math.py`, whose `count_params()` implements a pre-norm decoder-only transformer with SwiGLU, RMSNorm, GQA, optional tied embeddings and optional QK-norm. Reproduced 2026-10-21:

| Config | L | d | ffn | h_q | h_kv | head_dim | vocab | tied | **Params** | AdamW 16 B/p | bf16 weights | int8 | int4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A — canary** | 12 | 768 | 2048 | 12 | 4 | 64 | 32,768 | yes | **100,681,728** | 1.61 GB | 0.201 GB | 0.101 GB | 0.050 GB |
| **B — useful** | 24 | 2048 | 5632 | 16 | 4 | 128 | 32,768 | yes | **1,149,337,600** | 18.39 GB | 2.299 GB | 1.149 GB | 0.574 GB |
| **C — serious** | 32 | 4096 | 14336 | 32 | 8 | 128 | 32,768 | no | **7,248,019,456** | 115.97 GB | 14.496 GB | 7.248 GB | 3.624 GB |

**[OBSERVED]** The script also reports, for Config C: with tied embeddings and 8:1 GQA, N = 5.8052B; with untied embeddings and 4:1 GQA, N = 5.8052B with KV halved to 2,147.5 MB at 32k context. Vocab sensitivity at d=1024: 16,384 → 0.1972B params (emb 15.7% → 8.5% of total at 32,768).

**[INFERRED]** Config B is the primary target: at 1.149B params it sits just under the R2 rung, trains in **1.84 days on 8×A100 at the 20-tok/param budget** (22.99 B tokens) or **2.40 days at the 30 B-token arm**, and its 18.39 GB of AdamW state fits one 80 GB A100 with room for activations. Config C is the R3 stretch and needs 8×A100 with ZeRO-2/3. **[OBSERVED]** The 22.99 B / 1.84 d figure is `model-architecture-proposal.md` §4.6's, recomputed here from the same inputs and agreeing exactly.

**The vocabulary.** **[OBSERVED]** At Config B's d=2048, a 32,768 vocab contributes 67.1M embedding parameters — **5.8% of the model**. **[ESTIMATE]** Halving to 16,384 saves ~2.9% of parameters and FLOPs but costs compression on code, where identifiers fragment. **[KNOWN FACT]** Published measurements put code at **3.0–3.2 characters per token** for code-specialised tokenizers versus 2.49 for GPT-2 on general text (model card: `TerminatorPower/ezellm-lite-tokenizer`, observed 2026-10-21) — code tokenises *worse* than prose, so compression on code is worth paying for. **[SPECULATIVE TARGET]** 32,768 is the working choice; Stage A's gate decides it on measurement.

---

## 2. The six capability levers, and which one actually moves the needle first

### 2.1 The attribution table

Every capability improvement this roadmap could produce is attributed to **exactly one** of six levers. The lever assignment is a design claim, and the "who wins" column is the honest prediction.

| # | Lever | What it means | Examples of improvement it buys | **When available** | **Expected share of early gain** |
|---|---|---|---|---|---|
| **(a)** | **Model weights / architecture** | The function the model computes: parameter count, depth, width, attention pattern, context window, training data baked into weights. | Longer effective reasoning; better multi-step planning; native tool-call syntax; lower perplexity on code; ability to hold a repository in context. | **Stages B, E, I** — after a multi-day (or multi-month) training run. | **Last.** Weeks-to-months of latency before anything moves. |
| **(b)** | **Training data** | What the model was shown: corpus composition, filtering, deduplication, licensing. | Better code idioms; fewer hallucinations on rare APIs; correct language mix; domain specialisation. | **Stage D** — but only pays off after Stage C/E retrains on it. | **High, but deferred.** A corpus change is free to author and expensive to realise. |
| **(c)** | **Training optimisation & recipe** | How the weights were fitted: LR schedule, warmup, batch size, precision, parallelisation, curriculum, loss masking. | Faster convergence; stable long runs; usable quality at lower token counts; the difference between a 3-day run that learns and a 3-day run that does not. | **Stages B, C, E** — cheap to change, cheap to measure. | **High and immediate.** This is the cheapest capability-per-dollar lever in the entire roadmap. |
| **(d)** | **System instructions & prompting** | What the model is told per turn: system prompt, tool descriptions, instruction files, output style. | Tool-call validity; plan structure; negative-knowledge discipline ("say you don't know"); refusal to guess. | **Stage 0 — immediately, and forever.** | **Very high, and free.** Available before a single weight is trained. |
| **(e)** | **The agent harness & its tools** | The loop the model runs inside: tool set, schemas, permission engine, context management, compaction, subagents, retries, budgets. | Task completion; tool-error recovery; safe failure; parallel work; not losing the thread. | **Stage 0 — immediately.** | **Very high, and free.** The single largest lever available to us. |
| **(f)** | **Evaluation & feedback loops** | The measurement apparatus: task suite, oracles, contamination control, paired statistics, failure taxonomy. | Everything, indirectly: it is what converts the other five levers from guesses into measurements. | **Stage 0 — immediately.** | **Very high, and free.** Without it, (a)–(e) are unfalsifiable. |

### 2.2 The honest note the table demands

> **Levers (d), (e) and (f) are available to us long before lever (a). Most early capability gain will come from them.**

**[OBSERVED]** This is not an opinion. It is what `prompt-pattern-analysis.md` §7 concludes: *"a production coding agent's quality is determined **as much by the harness as by the model** — by the permission lattice, the tier separation, the tiered tool set, the context budget, the error taxonomy, and the result contracts. That is an encouraging finding for this project, because the harness is the part we can build and test exactly. The model is the part we must first rent before we can afford to build it."*

**[OBSERVED] And it is not a general belief about agents either — it is corroborated by this project's own black-box captures of the reference product's published CLI interface.** The specific mechanisms the quote names are each independently observed: the **permission lattice** with its tier separation and per-call `permission_decision` records (`agent-reference-shots/PROTOCOL-NOTES.md` lines 82–105, 144, 170 — accept/reject with `source` and `reason_type`; `agent-evidence.md` F-line 742 records the rejection arriving *as a tool result* and the model continuing); the **context budget and compaction** as an observable `system/compact_boundary` event (`interface-spec.md` §14.8/§14.10 and §15.2 (lines 1954, 2384, 2407, 2441)); the **result contracts** in the `structuredPatch` diff shape and the `{"type":"create", ...}` file record (`PROTOCOL-NOTES.md` lines 105–116); the **error taxonomy** in the preserved denial → error → course-correction trace at `agent-reference-shots/tool-error-contract.json` (`agent-evidence.md` F-lines 178, 438, 2513 — the model visibly course-correcting across four consecutive tool failures); and the **settings surface** at 245 keys / 17 sections (`agent-evidence.md` F5.1). **[INFERRED]** Each observation is *mechanism-specific*, which is what makes the claim actionable: the harness's contribution is not a vague "it helps" but a list of individually implementable, individually testable components, and the project's own captures are the specification for each one. **[KNOWN FACT]** These are direct observations of a published product's published interface, with no reverse engineering, and they are admissible as evidence about **the harness**. They are **not** evidence about the provider's model weights or training methods, and no stage may cite them as such (§16.1 item 7, rule 7 in §17.3).

**[INFERRED — HIGH confidence]** **Stages A–C are not the project's highest-value work; they are the project's highest-*risk* work.** The value is delivered by the harness and the evaluation apparatus, built in parallel under `implementation-plan.md` and `benchmark-and-evaluation-plan.md`. This roadmap's job is to ensure that when the model arrives it is measurably better than what we rented — and to be honest that at R2 it will not be dramatically better.

**[INFERRED]** The corollary, and a hard design constraint: **the harness must be swappable at the model boundary and the evaluation model-agnostic**, or every model decision contaminates every harness decision. That is what `architecture.md` §5.3–§5.4 and `interface-spec.md` §12 exist to guarantee, and it is why the self-hosted swap is *"a registry change, not a code change."*

### 2.3 Attribution of each roadmap stage to its dominant lever

| Stage | Dominant lever | Secondary lever | Note |
|---|---|---|---|
| A — Tokenizer | (c) recipe | (b) data | The tokenizer is a *data* artifact optimised by a *recipe*. Its effect shows up in (b): fewer tokens per unit of code means more code per dollar. |
| B — Architecture & init | (c) recipe | (a) weights | Reproducible init is a recipe property. Architecture choice is (a) but its effect is only observable after training. |
| C — Proof of learning | (c) recipe | (f) feedback | This stage *is* a feedback loop: the gate is "does loss decrease and does the eval move." |
| D — Data | (b) data | (f) feedback | Filtering and contamination control are only meaningful if (f) can detect their absence. |
| E — Scaling | (a) weights | (b) data, (c) recipe | The only stage whose primary lever is (a). This is why it is last and most expensive. |
| F — Instruction tuning | (a) weights | (b) data | Post-training changes weights; but (d) prompting delivers much of the same user-visible behaviour for free. |
| G — Tool-use / agentic | (a) weights | (e) harness | Tool-calling is a model competence; but *which* tools exist and how they behave is (e). |
| H — Preference / RL | (a) weights | (f) feedback | Only legitimate where a **verifier** exists — i.e. where (f) has already been built. |
| I — Long context | (a) weights | (c) recipe, (e) harness | Context extension is a training-phase change; but compaction and context selection in the harness also buy "effective long context" for free. |
| J — Efficient inference | (c) recipe | (a) weights | Quantisation is a serving-side transform; the *model* is unchanged, so the quality cost must be measured on the quantised artefact. |
| K — Evaluation & retraining | (f) feedback | all | The closing loop. It attributes every improvement back to a lever, which is the whole point of §2.1. |

### 2.4 The harness/model split, and where that document lives

**[OBSERVED]** `architecture.md` §2.1 defines L0 (model architecture & weights), L1 (data preparation & training) and L2 (instruction tuning & evaluation) as layers *below* the harness, with L3 (inference & model adapters) as the seam; §2.3 makes L0–L2 a separate workstream. **[OBSERVED]** The document that decomposes *individual capabilities* into model-side versus harness-side is **`agent-and-model-boundary.md`**, now written. Its `S0`–`S3` are *product disclosure states*, not development stages (see §15.5).

**[OBSERVED]** The load-bearing rules that bear on this roadmap:

- **`AMB-304` — the "own model" test.** All four must hold: weights trained by this project on a corpus whose provenance it controls; the base model named in the disclosure; no path to the provider's outputs in the corpus (§D.4); the evaluation set held out, uncontaminated and documented. **[INFERRED]** (1) and (3) are Stage D's and Stage F's concern, (4) is Stage K's, (2) is why the base model must be named wherever ours appears. A model failing any of the four is *"a fine-tune of someone else's model"* — legitimate, but not "our model" in the marketing sense; it must be disclosed as `keel-own` with a `model_base` (`AMB-305`).
- **`AMB-204` — adapters must not repair malformed tool calls.** **[INFERRED]** The most important constraint for Stage G: the harness must not smooth over the model's tool-call failures, because that moves a model failure into a harness success. It also means our evaluation numbers will be *worse* than a product that smooths errors — and that is correct.
- **`AMB-211` — the harness must not require any provider capability.** **[INFERRED]** No tool-calling yields a text-only agent; no streaming yields a buffered agent. This is why a 1.1B model can be plugged in at all, and why it will produce a weak product.
- **`AMB-221` — an adapter cannot make a weaker model competent.** **[INFERRED]** *A model swap is never free of consequence for product quality*. Swapping in our 1.1B model is not "the same product more cheaply"; it is a different product, and `AMB-222` requires the harness variant, model and effort level to travel with the score.
- **`AMB-312` — the §D.4 block applies at every stage.** **[INFERRED]** Using the provider's outputs — *including this project's own black-box transcripts* — as training data or a distillation teacher is not stage-dependent. It binds Stages F, G and H identically.

**[OBSERVED]** §6.3–§6.4 record *the consequential asymmetry*: the harness contributes the instruction hierarchy, permission lattice, tool set and schemas, context budget and compaction policy, error taxonomy and never-resend rule; the model contributes tool-call validity, tool choice, error recovery, plan structure and correct patches. **[INFERRED]** §6.4's requirement that benchmark results report the harness variant alongside the model is why K2's lever attribution exists — an unattributable score cannot satisfy `S2-4` (*"a failure taxonomy comparison, not a scalar"*).

**[OBSERVED]** The product-side promotion criteria `AMB-306` are produced by this roadmap at two points, named here so the documents cannot drift: `S1-6` (a paired comparison against the provider model under the evaluation plan's §9.2 controls) is satisfied by **Stage K**; `S2-2` (the model passes the end-to-end agentic test, driven by the harness through multi-step tasks) is satisfied by **Stage G**. **[INFERRED]** `S2-1` is worded *"not worse"*, not *"better"* — a governance property, not a quality claim (`AMB-307`) — so Stage K's job at the S1→S2 boundary is *parity under a paired design*, not superiority. The promotion decision itself is recorded separately (`AMB-302`).

The split itself, in prose:

- **Model-side (this roadmap's scope, Stages F–I):** emitting a syntactically valid tool call; choosing the right tool; recovering from a tool error; maintaining a plan structure; knowing when it does not know; producing a correct patch; holding and using a large context.
- **Harness-side (the parallel workstream's scope):** the entire instruction hierarchy and its conflict resolution; the permission lattice and its two tiers; the tool set and its schemas; the context budget and compaction policy; the error taxonomy and rendering; the never-resend rule; subagent isolation.

**[OBSERVED]** The cross-reference that decides this split is `prompt-pattern-analysis.md` §7, which lists `llm-development-roadmap.md` as the document taking *"which principles are model capabilities (tool-call validity, plan structure, negative-knowledge discipline) and which are harness capabilities (the whole of C1, C4, C5, C7, C8's enforcement half)."* This roadmap is consistent with that assignment.

## 3. Stage A — Tokenizer design, training and evaluation

**Purpose:** produce a tokenizer whose behaviour on *code* is measured, not assumed, and whose cost-per-token of code is known before any training run is costed.

### 3.1 Dataset properties

| Property | Value | Tag |
|---|---|---|
| **Data** | A permissive-licence code corpus. **[KNOWN FACT]** The Stack v2 carries 619 languages built on Software Heritage, requires an agreement with SoftwareHeritage and INRIA for bulk download, and states *"Any use of all or part of the code gathered in The Stack v2 must abide by the terms of the original licenses, including attribution clauses when relevant"* (https://huggingface.co/datasets/bigcode/the-stack-v2, observed 2026-10-21). | [KNOWN FACT] |
| **Size for tokenizer training** | ~2.4 GB raw text (R0-scale) is enough to train a 32k BPE. **[KNOWN FACT]** A 1 GB corpus at 32,768 vocab with byte-level BPE is documented as usable, with the caveat that it is *"small relative to GPT-4's tokenizer corpus"* so generalisation is limited (model card: `Arko007/zenyx-v2-tokenizer`, observed 2026-10-21). | [KNOWN FACT] |
| **Licence class** | **Aggregate, not uniform.** The Stack v2 is labelled *"other"* per its repo terms; the ODC-By labels on FineWeb/SmolLM-Corpus/C4 apply to the *packaging*, not the underlying code. **[KNOWN FACT]** `licensing-and-provenance-review.md` §9 records The Stack as **CANDIDATE**, requiring per-item licence identification with ambiguous items excluded. | [KNOWN FACT] |
| **Contamination risk** | **Low but not zero.** The tokenizer is trained on code, and evaluation tasks are built from code. **[INFERRED]** A tokenizer cannot leak an answer, so this is second-order — but the evaluation-suite repositories should be excluded from tokenizer training anyway, for free, and the exclusion recorded. | [INFERRED] |
| **Storage** | ~2.4 GB raw; tokenizer artefact ~3–20 MB (`tokenizer.json`); embedding matrix at 32k vocab × d=2048 = 0.134 GB fp32. | [ESTIMATE] |

### 3.2 Parameter scale targeted

**None.** A tokenizer has no parameters in the model sense. The relevant scales are **vocab size** and **corpus size**.

**[SPECULATIVE TARGET]** Vocab 32,768 for Config B (d=2048) and Config C (d=4096); a smaller 16,384 variant is built as an ablation. **[KNOWN FACT]** For calibration, SmolLM2 used a **vocab of 49,152** trained on its 1.1T-token corpus (https://huggingface.co/blog/smollm, observed 2026-10-21), and StarCoder2 uses **49,152**. **[ESTIMATE]** At d=4096, a 49,152 vocab costs 201M embedding parameters = **2.8%** of Config C — affordable, but the marginal benefit above 32k for a code corpus is unproven and must be measured, not assumed. **[OBSERVED]** The adopted vocabulary is **32,768**, recorded as `OPEN-A1` in `model-architecture-proposal.md` §5.3, which resolves the proposal's earlier 32,000-vs-32,768 discrepancy in favour of 32,768. **[INFERRED]** This roadmap's parameter counts and embedding-memory figures inherit that decision and must not be recomputed against 32,000; if the decision is revisited, the embedding term in §3.1's storage row and the parameter counts in `model-architecture-proposal.md` §4.2 move together, and Stage A's A5 freeze is what stops them drifting apart.

### 3.3 Compute, memory, storage

| Item | Value | Derivation | Tag |
|---|---|---|---|
| **GPU-hours** | **0** | Tokenizer training is CPU-only. | [KNOWN FACT] |
| **CPU-hours** | **6–30 CPU-hours** | **[ESTIMATE]** for byte-level BPE on a ~2.4 GB corpus on 8 threads. **[KNOWN FACT]** The `tokenizers` Rust backend trains BPE on a 516M-token corpus *"in seconds"* at 30,000 vocab (https://huggingface.co/docs/tokenizers, observed 2026-10-21), which bounds the upper end; the lower end covers the slower path and multiple vocab candidates. | [ESTIMATE] |
| **Dollars** | **$0.30–$6.00** | 6–30 CPU-h × $0.05–$0.20/h (the CPU rate from `compute-feasibility.md` §12). Rounds to **$0 at any sensible precision.** | [ESTIMATE] |
| **Memory** | **< 8 GB RAM** | BPE training is memory-bound on the token-frequency map. Fits the local machine's 13.85 GiB. | [ESTIMATE] |
| **Storage** | **~2.4 GB** corpus + ~20 MB artefact | ~2.4 GB raw corpus retained; the tokenizer artefact is `tokenizer.json` plus its merges and vocab files. | [ESTIMATE] |

### 3.4 Engineering complexity

**Low, but with one trap.** Byte-level BPE training is a solved problem; the `tokenizers` library does it. The trap is that **the tokenizer must be trained on the same corpus the model will see, and re-trained whenever the corpus changes materially** — otherwise its compression of the training corpus is unrepresentative of its compression of the evaluation distribution, and every token-budget calculation in this roadmap (all expressed in *tokens*) is wrong by an unmeasured factor. **[INFERRED]** This is the one artefact in the programme that must be version-locked to the corpus. Its hash goes in the model card.

### 3.5 Measurable exit criteria

**A1.** **Round-trip exactness.** `decode(encode(x)) == x` for 100,000 sampled documents across all 16 target languages, **zero** byte differences. Byte-level BPE makes this structurally guaranteed, but a normalisation bug makes it false, so it must be *asserted*.

**A2.** **Measured compression** on a held-out code sample, as **chars/token**, split by language. **[KNOWN FACT]** The published reference points to beat: StarCoder2 **3.238**, CodeGen-mono **3.017**, DeepSeek-Coder **2.836**, GPT-2 **2.487** (model card: `TerminatorPower/ezellm-lite-tokenizer`, observed 2026-10-21). **[SPECULATIVE TARGET]** ≥ **3.0 chars/token** median across target languages at 32,768 vocab. **[UNKNOWN]** What this project can achieve is not predictable in advance; the published figures are the comparison, not the prediction.

**A2b.** **The second metric: tokens per unit of *task-relevant content* on code.** **[INFERRED]** A2 is the right currency for a *pretraining* project, where the budget is tokens; it is the **wrong** currency for a *context-limited agent*, which is what this project is building. The agent's binding resource is not how many tokens the model can be *trained* on — it is how many tokens fit in **one request's context window**, because that determines how much repository the agent sees per turn, how many tool results fit in context, and how often compaction fires. **A tokenizer that is 10% better at bytes-per-dollar can be 5% worse at semantic-content-per-token on code, and the agent pays that 5% every turn, forever, in a resource that cannot be bought with more training compute.** **[SPECULATIVE TARGET]** A2b is measured as **tokens per "content unit"**, where a content unit is one *semantic* unit of the repository under test — one function definition, one import graph edge, one call site — counted by an independent extractor that never sees the tokenizer's output. The pair **(chars/token, tokens/content-unit)** is reported together for every candidate tokenizer; neither is allowed to win alone. **[UNKNOWN]** No published figure gives this metric for any tokenizer, including the reference points above, so **there is nothing to beat — only something to choose between our own candidates.** That is why A2b is a *selection* criterion among our own candidates rather than a comparison against a published number, and it is stated here as a gap rather than papered over. **[INFERRED]** The tooling required is modest and must be written: a content-unit extractor over the held-out code sample, and one tokenization pass per candidate tokenizer. **[INFERRED]** Because the metric is undefined against published baselines, its acceptance threshold is set *relatively* — see §3.7's second dial — rather than as an absolute number.

**A3.** **No evaluation-distribution skew.** Compression on the **evaluation-suite repositories** is measured separately and is within **10% relative** of compression on the training corpus.

**A4.** **No dead merges**, and **A5. the artefact is frozen and version-locked** to the corpus hash — a corpus change forces a rebuild or a recorded decision not to. **[INFERRED]** Dead merges are silent capacity loss, invisible in aggregate perplexity.

### 3.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Use an existing permissively-licensed code tokenizer** — StarCoder2's 49,152-vocab tokenizer, or the `tokenizers` library's pre-trained code vocabularies — and skip training entirely. **Cost: zero.** **[INFERRED]** The reasons to still train our own are the licence/provenance requirement (`licensing-and-provenance-review.md` §11: a tokenizer must be *"a permissive, independently implementable licence; not a copy of any vendor's vocabulary file without checking the vocabulary's provenance separately"*) and the corpus-locking property in A5. **But the cheap alternative is the right first step** — it lets Stages B and C start immediately while Stage A's training runs in parallel.

### 3.7 Kill criterion

**Kill Stage A's custom-tokenizer track if, after training two candidates (32k and 49k), neither reaches ≥ 3.0 chars/token median, or the custom tokenizer underperforms the pre-trained one by more than 10% relative.** In either case, adopt the pre-trained permissively-licensed tokenizer and record the decision. **[INFERRED]** A tokenizer is an efficiency optimisation, not a capability source: 10% worse compression costs a few percent of the training budget and buys **nothing**. There is no case for spending more than a week here.

**The second dial (A2b).** **Kill the custom-tokenizer track *also* if the best candidate by chars/token is more than 5% worse than the pre-trained permissively-licensed tokenizer on tokens-per-content-unit.** **[INFERRED]** This dial is independent of the first and can fail when the first passes — a tokenizer that packs more characters per token by merging across identifier boundaries will look good on A2 and bad on A2b, and **that trade is wrong for this product specifically**, because the context window is the scarce resource at inference time and the token budget is the scarce resource at training time. **[INFERRED]** When the two dials disagree, the resolution is not "take the average": the **pre-trained tokenizer wins**, because it is free, already licence-reviewed, and the cost of being wrong on the context metric is paid every turn forever, whereas the cost of being wrong on the training metric is a few percent of one budget. **[INFERRED]** A third case is worth naming: a candidate that wins **both** dials by a clear margin is the one case where Stage A's custom track earns its keep, and the 5% thresholds above are the bars it must clear.

## 4. Stage B — Model architecture and reproducible initialisation

**Purpose:** fix an architecture whose parameter count, memory footprint and KV-cache behaviour are *computed*, and whose initialisation is *bit-reproducible* — so that every later comparison is a comparison and not a lottery.

### 4.1 Dataset properties

| Property | Value |
|---|---|
| **Data** | **None.** This stage consumes no training corpus — only the Stage-A tokenizer, a synthetic random-seed stream, and the architectural definition. |
| **Size** | 0 bytes of corpus. The artefacts are the config, the parameter-count table and the initialisation snapshot. |
| **Licence class** | The *architecture* is ours (original). Any framework used (PyTorch, DeepSpeed, Megatron-LM, HuggingFace Transformers) is Apache-2.0/MIT per `licensing-and-provenance-review.md` §11's selection rule. |
| **Contamination risk** | **Zero.** No corpus is touched. |

### 4.2 Parameter scale targeted

**[OBSERVED]** Config A (100,681,728) at Stage B for the pipeline; Config B (1,149,337,600) as the roadmap's primary target; Config C (7,248,019,456) as the R3 stretch. All three are pre-norm decoder-only transformers with SwiGLU, RMSNorm, GQA, tied embeddings for A and B, untied for C — the exact structure `research/spl/param_math.py` implements and `compute-feasibility.md` §2.2 grounds in published working configurations (SmolLM2-360M, DeepSeek-Coder/CodeLlama class, StarCoder2-7B).

**[KNOWN FACT]** Every element of this architecture family is publicly documented as working at this scale: GQA at 8 KV heads (Llama 3.1), 32 layers / d=4096 (StarCoder2-7B, and OLMo 3 7B, which uses 32 layers and 4096 hidden size — https://huggingface.co/allenai/OLMo-3-1025-7B, observed 2026-10-21), SwiGLU and RMSNorm throughout.

**[SPECULATIVE TARGET]** The architecture is a *known-good* configuration, not a novel one. **[INFERRED]** Deliberate: the architecture is the cheapest thing to get wrong in a way that only shows up after a multi-day run. A novel architecture is a research project with an unknown outcome and no rollback; a known-good one is a known-cost engineering project. The one genuine architectural choice is **GQA ratio** (4:1 vs 8:1), because it trades KV-cache memory against a small quality cost — and it is measurable at Stage B's cost.

### 4.3 Compute, memory, storage

| Item | Value | Derivation |
|---|---|---|
| **GPU-hours** | **0–2** | A forward+backward pass on Config B with random data, to measure actual memory and MFU before committing to a run. On 8×A100, 2 GPU-h ≈ $5.60. |
| **Dollars** | **≤ $10** | [ESTIMATE] |
| **Memory — Config A** | 100.7M × 16 B/p (AdamW mixed-precision) = **1.61 GB** state; + activations. | [ESTIMATE], `param_math.py` |
| **Memory — Config B** | 1.149B × 16 B/p = **18.39 GB** state; bf16 weights only 2.30 GB. Fits one 80 GB A100 with activations; **does not** fit one 24 GB card without 8-bit optimizer (→ 12 B/p → 13.8 GB). | [ESTIMATE] |
| **Memory — Config C** | 7.248B × 16 B/p = **115.97 GB** state; bf16 weights 14.50 GB. **Does not fit one 80 GB A100** — requires ZeRO-2/3 across 8 GPUs (→ ~14.5 GB/GPU for optimizer state). | [ESTIMATE] |
| **KV cache — Config B** | L=24, h_kv=4, head_dim=128, ctx 32,768, bf16 → **1,611 MB (1.50 GiB)** at batch 1; 6.00 GiB at 131,072 context. | [ESTIMATE], `param_math.py` |
| **KV cache — Config C** | L=32, h_kv=8, head_dim=128, ctx 32,768 → **4,295 MB (4.00 GiB)** at batch 1; 64.0 GiB at 131,072. | [ESTIMATE] |
| **Storage** | Config B weights-only bf16 = **2.30 GB**; full resumable checkpoint at 16 B/p = **18.39 GB**. | [ESTIMATE] |

**[INFERRED] The KV-cache numbers are the reason Stage I exists.** At 32k context, Config C's KV cache (4.00 GiB) is **27% of its weights** (14.50 GB); at 131k it is 64.0 GiB — **4.4× the weights.** A serving rig sized for the weights alone falls over at long context, and the harness pays this on every agent turn that accumulates history. This is the same pattern `compute-feasibility.md` §6.2 documents for the public ladder.

### 4.4 Engineering complexity

**Medium, and the risk is concentrated in one place: reproducibility.**

**[INFERRED]** "Same seed → same weights" is harder than it looks, and the failure is silent. The culprits: non-deterministic reduction order in distributed gradient all-reduce; fused/flash attention kernels whose reduction order varies with batch shape; non-deterministic CUDA algorithms selected by default (`torch.use_deterministic_algorithms`); data-loader worker ordering; the order in which parameters are consumed by the initialiser.

**[OBSERVED]** The harness side of this project has already solved the analogous problem: `implementation-plan.md` §7 (M2) requires *"byte-identical normalised output across ten consecutive runs on two machines"* with an injectable clock and a seeded generator; `test-plan.md` §5 (Determinism engineering) is the reference.

### 4.5 Measurable exit criteria

**B1.** **Parameter count matches the computed value exactly.** `count_params()` in `research/spl/param_math.py` predicts 1,149,337,600 for Config B; the instantiated model reports the same integer. **Zero** discrepancy.

**B2.** **Initialisation is bit-reproducible.** Two runs, same machine, same seed → **byte-identical** parameter tensors (SHA-256 of every tensor matches). Two runs on **different machines** → tensors match within a tolerance stated per tensor dtype (bf16: exact if the RNG and init algorithm are pinned; otherwise the tolerance is on the order of 1 ULP and must be stated, not assumed).

**B3.** **Gradient determinism holds under distribution.** A 100-step, 8-GPU run with a fixed seed produces the same loss sequence as a 1-GPU run of the same effective batch, to a stated tolerance — or the discrepancy is characterised and bounded. **[INFERRED]** This is the criterion that catches the fused-kernel reduction-order problem.

**B4.** **Measured memory matches prediction** to within **10%**, and the *measured* number replaces the predicted one in every downstream budget. **B5. Measured MFU ≥ 25%** on 8×A100 with a real workload (the `compute-feasibility.md` §10 stop-rule floor), written into the run record. **[INFERRED]** Below 25%, more GPUs will not help; the bottleneck is engineering.

**B6.** **Well-formed outputs:** valid token IDs under the Stage-A tokenizer, finite logits (no NaN/Inf), and a greedy 64-token completion that is not degenerate.

**B7.** **The adapter contract is satisfiable.** The model serves behind the `ModelAdapter` interface (`interface-spec.md` §12) with `toolCalling: false` and `costBasis: "unknown"` — the architecture assumes no price table exists (`architecture.md` §5.4).

### 4.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do not write a custom training framework.** Use PyTorch + HuggingFace Transformers + DeepSpeed (ZeRO) or FSDP, and put the reproducibility work into a configuration, a seeded data loader and a determinism test suite — not a kernel. **[INFERRED]** A bespoke framework's effort is unbounded and its only payoff is performance we may not need: at R2, 8×A100 for 3.1 days is affordable. The scarce resource is *wall-clock for experiments*, and a bespoke framework's first six months are spent not running them.

### 4.7 Kill criterion

**Kill Stage B's custom-architecture exploration if, at Config B scale, measured MFU is below 25% on two consecutive attempts after the known remedies (bf16, FlashAttention-2, fused kernels, `torch.compile`).** `compute-feasibility.md` §14 risk #5 is explicit: below 25%, *"the bottleneck is engineering, not compute, and more GPUs will not help."* At that point, reduce ambition to a known-good published configuration rather than debugging a custom one.

**A second kill criterion:** if B2/B3 cannot be met after the determinism work in `test-plan.md` §5, **drop the bit-reproducibility claim** and downgrade every later comparison to *statistical* rather than *paired*. **[INFERRED]** This is a serious cost — it removes the ability to detect small effects, exactly what `benchmark-and-evaluation-plan.md` §10.1 needs — so it is a last resort. Pretending to a reproducibility the pipeline lacks is worse than declaring its absence.

## 5. Stage C — Small-scale pretraining baseline that demonstrably learns

**Purpose:** prove the training loop learns, and prove the evaluation harness moves. **This stage produces no product capability.** Its output is *knowledge*, not a model.

### 5.1 Dataset properties

| Property | Value |
|---|---|
| **Data** | A deliberately small, clean, permissive slice: MIT/Apache/BSD-licensed public code, plus a little permissively-licensed prose for calibration. **[KNOWN FACT]** The Stack v2 permissively-licensed subset is recorded as **CANDIDATE** in `licensing-and-provenance-review.md` §9, with the note that *"decontamination is the dominant cost, not licensing."* |
| **Size** | ~2.4 GB raw → **0.6B tokens** (R0) or **2.0B tokens** (Config A at 20 tok/param). |
| **Licence class** | Per-repository permissive licences; each file's licence identified at ingest, ambiguous files excluded (`licensing-and-provenance-review.md` §9.1 gate 1). |
| **Contamination risk** | **Low.** At 0.6–2.0B tokens on a clean slice, memorisation is negligible. But the *evaluation suite* must be excluded at this stage anyway, so the exclusion machinery is proven before it matters. |

### 5.2 Parameter scale targeted

**[OBSERVED]** Two anchors, for two different purposes: **Config A, 100,681,728 params** (L=12, d=768, 4:1 GQA, 32k vocab, tied) from `research/spl/param_math.py`, where at 20 tok/param D = 2.0B tokens and 6ND = **1.216×10¹⁸ FLOPs**; and **R0, 30M params**, the `compute-feasibility.md` ladder rung, where at 0.6B tokens 6ND = **1.08×10¹⁷ FLOPs**.

**[INFERRED]** Config A at 2.0B tokens is the better Stage-C vehicle than R0's 30M at 0.6B: it is 3.3× the parameters and 3.3× the tokens, but it still trains in **2.69 billed GPU-hours ($7.50)** and — more importantly — it is large enough to exhibit the phenomena Stage C exists to detect (loss-curve shape, memorisation onset, data-mixture sensitivity). A 30M model is small enough that "it learned" is nearly vacuous.

### 5.3 Compute, memory, storage

| Item | Config A @ 2.0B tokens | R0 @ 0.6B tokens |
|---|---|---|
| **6ND** | 1.208×10¹⁸ FLOPs | 1.080×10¹⁷ FLOPs |
| **Total billed GPU-h (A100 @ 40% MFU)** | 2.69 | 0.24 |
| **Wall-clock (8×A100)** | **0.34 h** | **0.03 h** |
| **Cost (@ $2.79/GPU-h)** | **$7.50** | **$0.67** |
| **Wall-clock (local CPU @ 10% of 1.72e11)** | 813 days | **73 days** |
| **State memory** | 1.61 GB (16 B/p AdamW) | 0.48 GB |
| **Corpus storage (uint16, 2 B/tok)** | 4.0 GB | 1.2 GB |
| **Checkpoint storage (full, 16 B/p)** | 1.61 GB each; 5 retained = 8 GB | 0.48 GB each |

**[ESTIMATE] The local-CPU row is the important one.** Config A locally is **813 days** at 10% of measured peak — categorically out of reach. R0 at 0.6B tokens is **73 days** at 10% efficiency, or **363 days** at 2%. **[INFERRED]** The *only* local option is to cut the token budget ~10× (0.6B → 60M tokens), which demonstrates the pipeline and nothing more. **This is the honest boundary of the free path, and it is why Stage C's real run must be rented.** Renting 8×A100 for one hour costs $22.32.

**[OBSERVED] The billed-GPU-h column was corrected on 2026-10-22** to the fleet-independent convention of §7.3. It previously read "22 GPU-h" and "2 GPU-h" — the per-GPU figure multiplied by the fleet, which bills the fleet twice. **[INFERRED]** The corrected figures are *smaller*, which strengthens rather than weakens this stage's conclusion: **Stage C's rented run costs single-digit dollars, not $60.** A stage that proves the trainer learns for under $10 is cheap enough to be repeated on every hypothesis, and that is precisely the property Stage C needs.

### 5.4 Engineering complexity

**Medium-high — the highest-complexity stage relative to its cost.** The work is not the training loop; it is the *failure modes*. **[INFERRED]** The five that will bite, in order of likelihood: **(1) dataloader stalls** — GPUs idle on I/O while the rental clock runs; `compute-feasibility.md` §14 risk #4 prices this at 20–40% of run cost and sets a **15% stall-time stop-rule**. **(2) Loss divergence / NaN** — almost always a LR too high for the batch size, or an fp16 overflow where bf16 was needed. **(3) The token-budget mismatch** — training on 2B tokens with a schedule tuned for 20B produces a model that looks undertrained and gets misdiagnosed as a data problem. **(4) Checkpoint/resume corruption** — resume that silently loses the optimiser or RNG state produces a run that is not the same run. **(5) Evaluation-harness noise exceeding the effect** — the eval giving different numbers on the same checkpoint invalidates everything downstream (`compute-feasibility.md` §10 Gate 1).

### 5.5 Measurable exit criteria

**C1.** **Loss decreases monotonically over the first 200 steps**, no NaN/Inf, and the curve matches a reference run's shape to within **5%** at step 1,000. This is `compute-feasibility.md` §14 risk #2's kill trigger, applied as the primary criterion.

**C2.** **Validation loss falls below the unigram baseline** computed on the same validation set. **[INFERRED]** The unigram baseline is the floor: a model that has not beaten it has learned nothing a frequency table does not already say. This is the cheapest possible "did it learn" test and is entirely sufficient for the stage's purpose.

**C3.** **The evaluation harness is deterministic** — the same checkpoint through the harness twice gives the **identical** aggregate score. If not, the harness is broken and every number in this roadmap is void (`compute-feasibility.md` §10 Gate 1).

**C4.** **The eval score moves with the checkpoint.** Between the step-0 and final checkpoints, the Stage-C slice score changes by **more than the harness's own seed-to-seed variance**. **[INFERRED]** This is the difference between "the loss went down" and "the model got better at something measurable" — only the second licenses proceeding.

**C5.** **Dataloader stall time < 15% of wall-clock**, measured, not estimated. **C6. Measured MFU ≥ 25%** (B5 restated as a stage gate), and the measured value replaces the predicted one in every downstream budget. **C7. The run is resumable** — killing at step 500 and resuming matches the uninterrupted loss curve to within **1%** at step 1,000.

### 5.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Run Stage C on the local CPU at a 60M-token budget first** — a weekend, $0 — to shake out the pipeline (tokenisation, sharding, checkpointing, resume, loss curve, eval wiring). **[INFERRED]** This is `compute-feasibility.md` §15's advice: *"treat it as a systems project, not a model project."* The local run cannot demonstrate learning (C2/C4), so the *rented* run is still required — but it removes every pipeline bug **before the rental clock starts**, and pipeline bugs are what a small team burns a 68-day run on. A second alternative: use a **tiny public model** (Qwen3-0.6B, Apache-2.0 — `compute-feasibility.md` §13.2) as the Stage-C subject, proving the *serving and eval* path end to end in an afternoon. **[INFERRED]** It proves the wrong half — the training half is what Stage C is for — so it is a complement, not a substitute.

### 5.7 Kill criterion

**Kill the local-CPU path entirely if the 60M-token local run shows measured effective throughput below 2% of the 1.72×10¹¹ FLOP/s peak.** At that efficiency even R0 is a multi-month job, and the local machine's role is restricted to Stages A, B, D and K.

**Kill the training programme at Stage C if any of these hold after two full attempts:** loss does not decrease within 200 steps (§10 Gate 1); the eval harness gives different results on the same checkpoint; measured MFU is below 25% on two consecutive runs (§10 global stop-rule 3) **after** the known remedies. **[INFERRED]** Each of these indicates a *pipeline* defect, and every larger rung inherits it: a pipeline that cannot learn a 100M model will not learn a 7B model — it will just cost 68 days to fail.

## 6. Stage D — Data collection, filtering, deduplication and contamination control

**Purpose:** build a corpus that is legally usable, deduplicated, and demonstrably free of the evaluation suite — **before** scaling amplifies any defect in it.

**[INFERRED] This stage is the one that most often dominates the schedule.** `compute-feasibility.md` §9 records that data prep is *"often the longest pole — and it is usually underestimated,"* and that for the R2 rung the critical path is data prep (20–40 days), not compute (3 days).

**[INFERRED] The corpus search starts at Stage A, not Stage D.** **[KNOWN FACT]** `training-data-plan.md` §2.2a states the contingency for the case where no licence-clean corpus of sufficient size exists — four ordered branches, each strictly less capable and strictly more expensive than the clean case: **(1) attribution-discharge** (build the per-item provenance ledger, SWHID publication and attribution-shard machinery the Stack v2's terms require); **(2) single-licence regeneration** (restrict to `odc-by` web corpora and per-file MIT/Apache-2.0 code selected by a licence classifier); **(3) self-generated data** (our own code and SFT rows, with a **published, permissively-licensed open model that is not the reference product** as teacher where one is needed — its outputs inherit a licence we can name and discharge); **(4) scale down, not scale across** (train R1 at 7.2 B tokens rather than R2 at 30 B, accepting a smaller model rather than a licence-encumbered one). **[INFERRED]** Every branch preserves §17.3 rule 6 — none of them weakens the provenance requirement; branch 4 is the honest floor, not a licence compromise. **[INFERRED]** The reason the search is bound to **Stage A** is timing, not preference: a licence review is cheap, the corpus *shape* determines the tokenizer's vocabulary allocation, and a Stage-D-delayed search would not surface a negative `U6` until after Stages B and C have spent their budget against a premise that has since failed. **[INFERRED]** So the practical reading of this section is that **Stage A has two outputs, not one**: a tokenizer artefact and a *corpus register with a resolved `U6`*. If the register comes back negative at Stage A, the branch above is chosen then — while the budget is still unspent.

### 6.1 Dataset properties

| Property | Value | Tag |
|---|---|---|
| **Primary corpus** | **The Stack v2** — 619 programming languages built on Software Heritage. **[KNOWN FACT]** Requires a formal agreement with SoftwareHeritage and INRIA for bulk download, has explicit attribution obligations, and is *"regularly updated to enact validated data removal requests"* — a **recurring maintenance cost, not a one-time artefact**. | [KNOWN FACT] |
| **Secondary corpus** | A permissively-licensed web/prose corpus for calibration and general reasoning: FineWeb (**ODC-By 1.0**, 15T+ tokens), SmolLM-Corpus (**ODC-By 1.0**, 1.1T tokens), C4 (**ODC-By 1.0**). | [KNOWN FACT] |
| **Third corpus (scale reference)** | **Dolma 3 pool** — 9.31T tokens / 9.97B documents, **ODC-By v1.0**, with a GitHub-code component ("StackEdu (Rebalanced)", 137B tokens) and a **100B-token midtraining mix and 50B-token long-context mix** for OLMo 3. | [KNOWN FACT] |
| **Size for R2** | Raw ~200 GB → filtered/tokenised ~120 GB at 4 B/tok for 30B tokens (60 GB at 2 B/tok). **[ESTIMATE]** `compute-feasibility.md` §5.1's rule: the filtered corpus is **20–40% the size of the raw crawl** after deduplication and quality filtering. | [ESTIMATE] |
| **Size for R3** | Raw ~1 TB → tokenised 560 GB (4 B/tok) for 140B tokens. | [ESTIMATE] |
| **Licence class** | **Aggregate and per-item.** The Stack v2 is labelled *"other"*; its terms state *"Any use of all or part of the code gathered in The Stack v2 must abide by the terms of the original licenses, including attribution clauses when relevant."* **[KNOWN FACT]** The licensing review's position: *"For a code project specifically, there is no truly permissive public code corpus."* | [KNOWN FACT] |
| **Contamination risk** | **High, and the dominant cost.** The evaluation suite is built from code; the training corpus is code. **[KNOWN FACT]** The Stack v2 provides Software Heritage persistent IDs (SWHIDs) for exactly this purpose — the StarCoder2 paper releases them so provenance can be tracked. | [KNOWN FACT] |

### 6.2 Parameter scale targeted

**None directly.** But Stage D's output determines Stage E's parameter scale, because it determines the token budget the budget can afford: **[INFERRED]** corpus quality sets the achievable quality at a fixed token count, so corpus quality and model scale trade off against each other. A better corpus at R2 can beat a worse corpus at R3 at 1/20 the cost.

### 6.3 Compute, memory, storage
| Item | R2-scale (200 GB raw) | R3-scale (1 TB raw) |
|---|---|---|
| **GPU-hours** | **0** | **0** |
| **CPU-hours** | **[ESTIMATE]** 600 CPU-h for crawl+filter+dedup+tokenise at ~3,000 CPU-h/TB. On 8 local cores = **3.1 days**. | **5,000 CPU-h** at ~2,500 CPU-h/TB = **26 days** on 8 cores. |
| **Dollars (CPU)** | **$30–$120** | **$250–$1,000** |
| **Memory** | < 8 GB streaming | < 16 GB; MinHash dedup is the memory peak |
| **Storage — raw** | 200 GB | 1 TB |
| **Storage — tokenised** | 120 GB (4 B/tok) / 60 GB (2 B/tok) | 560 GB / 280 GB |
| **Storage — both at once** | 320 GB → **exceeds the 159.2 GB local disk** | 1.56 TB → object storage required |
| **Object storage** | $0.02–$0.09/GB/month → ~$11–$48/month for 320 GB | ~$112–$504/month for 1.56 TB |

**[INFERRED] The local-disk constraint bites at R2.** `compute-feasibility.md` §5.4: *"Local disk reality: the local machine has 159.2 GB free. R0, R1-optimal, and R2-optimal all fit."* **[ESTIMATE]** 200 GB raw + 120 GB tokenised = 320 GB does **not** fit, so R2-scale preparation needs either object storage or a streaming design that never holds raw and tokenised corpora simultaneously. **This is a design constraint to be decided at Stage D, not discovered at Stage D+1.**

### 6.4 Engineering complexity

**High — and the most under-rated stage in the roadmap.** The work, in order of difficulty:

1. **Per-item licence identification.** **[KNOWN FACT]** `licensing-and-provenance-review.md` §9.1 requires licence identification *"per-item, from the source's own licence file, not from a directory-level assumption. Where the licence is ambiguous, the item is excluded."* **[INFERRED]** At 115M files with mixed licence headers, LICENSE files and no licence at all, this is a *classifier* problem with a false-negative cost: one missed copyleft file in the corpus is a licence defect in the weights. The Stack v2's SWHID provenance is the mitigation and must be retained.
2. **Deduplication.** **[KNOWN FACT]** StarCoder2's dataset versions differ substantially in size ("2.9TB" v1 vs "32.1TB" v2), indicating dedup was applied — the blog does not state the removal rate. **[UNKNOWN]** No public removal-rate figure was found for the Stack v2. MinHash/LSH is the standard approach; **[KNOWN FACT]** SlimPajama reports MinHashLSH dedup applied to RedPajama v1.
3. **Quality filtering.** **[KNOWN FACT]** SmolLM's pipeline used **Llama 3 to annotate 500,000 Python samples** to train an educational-code classifier, then filtered **40B Python tokens down to 4B** — a **90% reduction** (https://huggingface.co/blog/smollm, observed 2026-10-21). **[INFERRED] This is the most instructive published number in the pipeline**: quality filtering is aggressive, the classifier is itself a *model* whose cost must be budgeted, and **the reference product's outputs are excluded by §D.4, so we cannot use Llama 3 to annotate — we must train our own classifier on our own labels.**
4. **Contamination control against the evaluation suite.** **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §5.3 rule 6: the training-data filter covers the *whole* suite, dev and test, and the check is *"cheap: hash every suite asset, hash every training example, and assert disjointness."* **[INFERRED]** Straightforward to implement, but it catches only exact matches. Near-duplicate contamination (the same fix commit re-authored, the same file reformatted) needs MinHash at file level — a second, more expensive mechanism.
5. **Provenance manifest.** **[KNOWN FACT]** §9.1 gate 4: one manifest entry per ingested item — source URL, licence-text hash, ingestion date, licence-check result — and *"this manifest is an artifact we ship."*

### 6.5 Measurable exit criteria

**D1.** **Licence coverage is complete.** 100% of ingested files have a licence-check result recorded, with **0** files in the "ambiguous → excluded" state that were not deliberately excluded. **[KNOWN FACT]** The gate is `licensing-and-provenance-review.md` §9.1's five-item list, and it must pass as a *gate*, not a metric.

**D2.** **Deduplication is measured, not assumed.** The pipeline reports the duplicate rate removed at two granularities (exact-document hash; MinHash near-duplicate at a stated threshold) and the **retention rate** after filtering. **[UNKNOWN]** No public benchmark for "what retention rate should a code corpus have" was found; the expectation is that it is *reported*, not that it matches a number.

**D3.** **Evaluation disjointness is exact.** The hash-disjointness check against **every** suite asset, dev and test (`benchmark-and-evaluation-plan.md` §5.3 rule 6), passes with **zero** intersections. This is the `G16` hard gate.

**D4.** **Near-duplicate rate against the suite is measured and reported**, even though it cannot be driven to zero. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §4.6 states the honest position: contamination control *"is a risk-management procedure, not a detection procedure. No known method reliably establishes that a specific task's answer was absent from a specific model's pretraining corpus."*

**D5.** **The corpus is rebuildable** from raw source to tokenised shards, from a versioned manifest, in a recorded time, on a clean machine. **[KNOWN FACT]** The Stack v2's removal-request process requires users to *"update your own version of The Stack v2 to the most recent usable version"* — so rebuildability is a licence-compliance obligation, not a convenience.

**D6.** **The manifest is signed and shipped**, one entry per item, and a spot-check of **20 randomly sampled** entries reproduces its recorded licence classification by independent inspection. **D7. The prose/code mixture is measured** — token share from each source — and recorded as a config, not an emergent property of a shuffle.

### 6.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Use a published, already-filtered, already-deduplicated, already-licensed corpus rather than building one.** The best candidate is **Dolma 3**: 9.31T tokens, ODC-By, with a named 137B-token GitHub-code component and a published **50B-token long-context mix** with an exact composition that Stage I can use directly. **[INFERRED]** The cost of the shortcut is that we inherit the corpus's mixture decisions rather than making our own. That is the right trade at first: our filter's marginal value over a well-run public filter is unknown, and the schedule cost of building a competitive filter from scratch is 20–40 days.

**[INFERRED]** The one thing the shortcut does *not* excuse is the **evaluation-suite exclusion filter**, which we must apply ourselves regardless of whose corpus we use. That filter is cheap (hash-based) and it is the one thing that keeps our evaluation honest.

### 6.7 Kill criterion

**Kill the custom-corpus track if, after building a first-pass filter, the resulting corpus does not beat a public corpus of the same size on held-out perplexity, or if the licence classifier's coverage is below 95% of files.** **[INFERRED]** Mirroring `compute-feasibility.md` §10 Gate 2: if our data is not better than what is already public, every larger rung inherits the defect and the whole cost of a bespoke pipeline is wasted. A custom corpus is justified by *measured* quality gain, not by the desire to own the pipeline.

**A second, sharper kill criterion:** if the licence classifier cannot achieve ≥ 95% confident per-item licence identification on the target languages, **stop training from raw code** and switch to a corpus whose provenance is already established per-item, or to our own original data. **[INFERRED]** A licence defect in the weights is unbounded-cost and unfixable after the fact; a slightly worse corpus is a bounded, recoverable cost.

## 7. Stage E — Scaling, but only when measurements justify it

**Purpose:** train the largest model the evidence supports — no larger.

### 7.1 The gate that must precede Stage E

**[INFERRED]** Stage E is not a decision about ambition; it is a decision about *whether the previous stages produced a better model than a public one of the same size*. That is `compute-feasibility.md` §10 Gate 2, verbatim: *"at matched size, our R1 must beat SmolLM2-360M or an equivalently-sized public model on the project's own **DEV** partition, under one harness and one set of tool settings. **If our own model cannot beat the public one at equal scale, the data is not better than what is already public, and every larger rung inherits that defect.**"*

**[OBSERVED] Correction (2026-10-22).** This paragraph previously quoted Gate 2 as requiring the comparison "on HumanEval/MBPP". `compute-feasibility.md` §10 has since been corrected: Gates 0–2 now run on **the project's own DEV partition**, with the public suites demoted to an **external reference point, reported alongside but never a release gate**, because `licensing-and-provenance-review.md` §9 registers HumanEval and MBPP as *"use as a held-out set only"* and `benchmark-and-evaluation-plan.md` §5.3 requires disjointness between suite assets and training data. The quote above is the corrected wording. **[INFERRED]** The substance of Gate 2 is unchanged — a public model of matched size remains the comparator — but **the tasks must be ours**, and a HumanEval number is now a sanity check rather than the spend trigger.

**[KNOWN FACT]** The public comparator at R1 scale is **SmolLM2-360M**: 360M params, **600B tokens** trained, context 2,048, vocab 49,152, GQA (https://huggingface.co/blog/smollm, observed 2026-10-21). **[INFERRED]** Note the asymmetry: SmolLM2-360M trained for 600B tokens is the *extended* budget, while a compute-optimal 360M model sees 7.2B. **A 600B-token model at 360M costs $8,048 corrected and 15 days on 8×A100** — that is the number to beat, and it is a *stretch* target for a first attempt.

### 7.2 Dataset properties

| Property | R2 (primary target) | R3 (conditional stretch) |
|---|---|---|
| **Data** | Stage-D corpus at the R2 mixture | Stage-D corpus at the R3 mixture |
| **Size** | 120 GB tokenised (4 B/tok) for 30B tokens | 560 GB for 140B tokens |
| **Licence class** | As Stage D; the R2 corpus is the R3 corpus minus the tokens R3 adds | |
| **Contamination risk** | As Stage D, with D3's exact disjointness re-verified *at this run*, not inherited | |

### 7.3 Parameter scale, compute, memory, storage

**[OBSERVED] This table was corrected on 2026-10-22.** It previously carried `compute-feasibility.md` §3.4's **R2-opt row for N = 1.5 × 10⁹** and **R3-opt row for N = 7.0 × 10⁹** verbatim, but paired them with this roadmap's own parameter counts (1.149 B and 7.248 B) in the same rows. The two were internally contradictory in both directions: the stated `6ND` implied a different N than the stated N, and the "Total GPU-h" column mixed a per-GPU figure with a fleet-doubled figure under one heading. `llm-research-review.md` F1 confirmed the defect; every cell below is now derived **at the row's own parameter count**, with the arithmetic in the note that follows. **[INFERRED]** The correction errs in the same direction as the original: the old table overstated both wall-clock and cost.

**The two tables in this document now mean different things, and the distinction is the point.** The ladder in §1.2 is a *planning* ladder whose rungs are fixed nominal parameter counts (1.5 B, 7 B). This table is the *actual architecture* this roadmap commits to (Config B at 1.149 B, Config C at 7.248 B). They are close but not equal, and quoting one while labelling the other is how the original error arose.

| | **R2 — Config B** | **R3 — Config C** |
|---|---|---|
| **Params** | 1,149,343,744 | 7,248,019,456 |
| **Tokens @ 20 tok/param** | 22.99 B | 144.96 B |
| **The token arm this table budgets** | **30 B (26.1 tok/param)** | **140 B (19.3 tok/param)** |
| **6ND (dense term only)** | 2.069×10²⁰ | 6.088×10²¹ |
| **Total billed GPU-h (A100 @ 40% MFU)** | 460.5 | 13,551 |
| **Wall-clock (8×A100)** | **2.40 days** | **70.6 days** |
| **Wall-clock (8×H100 @ 45%)** | 16.1 h | **19.8 days** |
| **Cost (A100)** | **$1,285** | **$37,808** |
| **Cost (H100)** | **$515** | **$15,154** |
| **Cost with ×2 failure multiplier (A100)** | **$2,570** | **$75,616** |
| **State memory (16 B/p AdamW)** | 18.39 GB → 1× 80 GB A100, or ZeRO across 2 | 115.97 GB → **needs 8×A100 with ZeRO-2/3** |
| **State memory (12 B/p, 8-bit optimizer)** | 13.79 GB → fits 1× 24 GB card | 86.98 GB |
| **Activations (checkpointed)** | ~0.86 GB at batch 1 | ~4.56 GB |
| **Checkpoint storage** | 18.39 GB full; 5 retained = 92 GB | 115.97 GB full; 5 retained = 580 GB |
| **Corpus storage** | 120 GB (4 B/tok) | 560 GB |
| **Total storage** | ~212 GB — **exceeds the 159.2 GB local disk** | ~1.14 TB → object storage mandatory |

**[ESTIMATE] The derivation, shown so the next reader does not have to re-derive it.**

```
Config B:  N = 1,149,343,744   D = 30e9   C = 6ND = 2.0688e20 FLOPs
           per-GPU sustained (A100 @ 40% MFU) = 312e12 × 0.40 = 1.248e14 FLOP/s
           total billed GPU-h = 2.0688e20 / 1.248e14 / 3600 = 460.5 h   (fleet-independent)
           wall-clock on 8 GPUs  = 460.5 / 8 / 24 = 2.40 days
           cost = 460.5 × $2.79 = $1,285
Config C:  N = 7,248,019,456   D = 140e9  C = 6ND = 6.0883e21 FLOPs
           total billed GPU-h = 6.0883e21 / 1.248e14 / 3600 = 13,551 h
           wall-clock on 8 GPUs  = 13,551 / 8 / 24 = 70.6 days
           cost = 13,551 × $2.79 = $37,808
```

**[INFERRED] The cost convention, restated because it is the one most easily re-broken.** Total billed GPU-hours for a fixed FLOP budget are **fleet-independent**: if *f* GPUs sustain rate *r* each and must absorb *C* FLOPs, then wall time `T = C/(f·r)` and billed GPU-hours `= f·T = f·C/(f·r) = C/r` — the *f* cancels. So `cost = (C/r)/3600 × price` and `wall-clock = (C/r)/3600 / fleet / 24`. **More GPUs buys time, not money.** `compute-feasibility.md` §3.4 was patched to this convention on 2026-10-22, and `llm-research-review.md` F3 records the correction and its verification.

**[ESTIMATE] H100 vs A100 is a wall-clock decision, not a cost decision.** At Config B's 30 B-token arm, 8×H100 costs **$515** against 8×A100's **$1,285** and delivers **3.6× the MFU-adjusted throughput** (2.40 d → 16.1 h); at Config C's 140 B-token arm, **$15,154** against **$37,808** and (70.6 d → 19.8 d). **[INFERRED]** **H100 is decisively better for wall-clock and modestly better for cost.** The catch, from `compute-feasibility.md` §12 Scenario B: *"H100s are scarce and often unavailable on short notice, which the schedule (not the budget) may dominate."* **[SPECULATIVE TARGET]** Default to 8×A100 for *development* runs (availability, price) and 8×H100 for *the* run, held as a reservation.

### 7.4 Engineering complexity

**Low *relative to the cost*, which is the trap.** At R3 the engineering is the same as R2 — the same code, the same framework. What changes is that **a bug now costs 68 days instead of 3**. **[INFERRED]** The mitigation is procedural: validate the full recipe at R2 (3 days, repeatable), then run a **shortened R3** (e.g. 20B tokens, ~10 days on 8×A100) to validate the R3-specific recipe before committing to 140B. `compute-feasibility.md` §14 risk #2 names exactly this mitigation.

**[INFERRED]** The other R3-specific engineering risk is **memory pressure**: 115.97 GB of optimizer state on a 115.97 GB/8 = 14.5 GB/GPU share under ZeRO-2, plus activations, plus fragmentation. Off-by-one fragmentation losses at R3 have cost real projects days. Mitigations: gradient checkpointing, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, and a memory-headroom target of **≥ 15%**.

### 7.5 Measurable exit criteria

**E1.** **The R1 gate passes first** (`compute-feasibility.md` §10 Gate 2): our R1 model **beats** SmolLM2-360M at matched size on the project's own **DEV** partition (`benchmark-and-evaluation-plan.md` §5.2), under one harness and one set of tool settings, on a **paired** comparison per `benchmark-and-evaluation-plan.md` §8, with the discordance table and per-task deltas reported. **[INFERRED]** A single run with a favourable aggregate is *not* a pass; the comparison method is mandatory, and the `G15` gate (Holm-corrected p < 0.05 **and** effect size above the §10.3 minimum) applies. **[OBSERVED]** HumanEval/MBPP may be reported **alongside** this comparison as an external reference point, but per the corrected `compute-feasibility.md` §10 they are **never the release gate** — `licensing-and-provenance-review.md` §9 registers them as held-out-only and `benchmark-and-evaluation-plan.md` §5.3 requires disjointness. **[INFERRED]** The honest consequence, stated here so it is not discovered late: the DEV partition is small (40 tasks at S0, 120 at S1), so this gate is **directional** — the number moved the right way and the loss curve is monotone — and the statistical budget is spent at S1/S2 suite sizes and on paired comparisons instead.

**E2.** **The scale-up produces the expected gain.** R2 beats R1 by at least the **3.0 pp** `improvement` bar (§10.3) on the task suite, with the CI, **measured on the claim set** (`benchmark-and-evaluation-plan.md` §5.2). **[INFERRED]** If R2 does not clearly beat R1, scaling is not buying capability and the whole ladder is suspect. **[OBSERVED]** The same power caveat as G4 applies here and is stated rather than left implicit: the 3 pp bar is **not detectable** at any stage's claim set (two-sided power against 3 pp is 20% at S3's initial n = 370; the bar needs n = 2,590), so §10.3 treats 3 pp as *a descriptive threshold on an already-significant result*, not as an effect the suite can resolve. **[INFERRED]** The consequence for this gate is that a **statistically significant** R2-over-R1 result that is *smaller* than 3 pp still satisfies E2 in substance — because the 3 pp figure is not a resolution the suite has. What E2 actually rules out is R2 being *no better* than R1, which is the thing the ladder does need to exclude.

**E3.** **The token-budget decision is measured, not assumed.** The R2 run plots quality against token count on a log axis (checkpoints at 10/20/50/100% of budget, per `compute-feasibility.md` §5.2) and computes the **quality gain per 10× tokens**. **[KNOWN FACT]** §14 risk #1 sets the kill trigger: *"If measured quality gain per 10× tokens falls below 20%, stop and take the optimal budget."* **[INFERRED]** This is the single most valuable measurement in Stage E — it determines whether the extended budget (17× the cost) is worth buying, and it is only measurable *at R2*, where runs are cheap.

**E4.** **The run starts from a known state** — the initial checkpoint's hash matches a prior identical run (B2), confirming that the run which will occupy 68 days does not start unknown. **E5. Loss-curve deviation is monitored** — deviation > 5% from the reference run in the first 1,000 steps kills the run immediately (§14 risk #2). **E6. At R3 only:** the checkpoint set is retained per the logarithmic-interval policy, and **at least one** weights-only bf16 export (2 B/p) exists for every retained checkpoint, so evaluation never loads optimiser state.

### 7.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do not start at R2 with a full token budget. Start at the cheap arm, then extend in a second phase only if E3's measurement supports it.** **[ESTIMATE]** The arms, at Config B's own N = 1,149,343,744:

| Arm | Tokens | tok/param | 6ND | Total billed GPU-h | Wall (8×A100) | Cost | Wall (8×H100) | Cost |
|---|---|---|---|---|---|---|---|---|
| **20 tok/param (Chinchilla-optimal)** | 22.99 B | 20.0 | 1.585×10²⁰ | 352.8 | **1.84 d** | **$984** | 0.52 d | $395 |
| **26 tok/param — *the arm §7.3 budgets*** | 30.00 B | 26.1 | 2.069×10²⁰ | 460.5 | **2.40 d** | **$1,285** | 0.67 d | $515 |
| 50 tok/param (extended-code) | 57.47 B | 50.0 | 3.963×10²⁰ | 881.8 | 4.59 d | $2,461 | 1.28 d | $986 |
| 100 tok/param | 114.93 B | 100.0 | 7.926×10²⁰ | 1,763.7 | 9.19 d | $4,922 | 2.57 d | $1,973 |
| 200 tok/param (StarCoder2-class) | 229.87 B | 200.0 | 1.585×10²¹ | 3,527.4 | 18.38 d | $9,844 | 5.13 d | $3,946 |
| **300 B-token (extended R2)** | 300.00 B | 261.0 | 2.069×10²¹ | 4,604.7 | **23.98 d** | **$12,847** | 6.72 d | $5,149 |

**[INFERRED] The arm this roadmap currently bets on is the 26.1 tok/param row — the 30 B-token arm — and it is stated here because it is the axis's most consequential undisclosed parameter.** `llm-research-review.md` F2 established that the token budget is a *convention with a source*, not a derivation for this corpus: 20 tok/param comes from Chinchilla (arXiv:2203.15556), but for *code* the optimum is not established, and `model-architecture-proposal.md` §4.6 documents StarCoder2 (arXiv:2402.19173) training at **200 tok/param**. **[INFERRED]** The arm matters because the whole ladder's economics sit on it: at Config B, moving from 26 to 200 tok/param multiplies the run from **$1,285 / 2.40 d** to **$9,844 / 18.38 d** — a **7.7× cost and 7.7× latency multiplier** — and the 200-tok/param arm is the one that would actually put this project in StarCoder2's regime. **[UNKNOWN]** No public figure determines which arm is right for *this* corpus; E3's measurement is what settles it, and it is only measurable at the cheap end. **[INFERRED]** **The arm choice is therefore a Stage E decision, not a Stage A–D decision, and it should be made by measurement rather than by the default.** Until E3 runs, the budget in §7.3 should be read as *the 26 tok/param arm*, and the reader should hold open a 7.7× cost multiplier.

**[INFERRED]** The extended R2 budget (300 B tokens) costs **$12,847 and 23.98 days** at Config B — ten times the optimal budget on tokens and roughly ten times on wall-clock. The decision between the arms is exactly what E3 measures, and it should be made with data from the cheap run, not before it.

**[SPECULATIVE TARGET]** Second alternative: **continue pretraining from a permissively-licensed base** (Qwen3-0.6B is Apache-2.0 per `compute-feasibility.md` §13.2) rather than from scratch. **[INFERRED]** This changes the licence position (the base model's licence governs the weights), so it is a real decision, not a free win — but `compute-feasibility.md` §13.6's assessment is that *"Training from a strong Apache-2.0 base is strictly better than from scratch for a project whose goal is a working agent."* The catch: it makes our model *derivative* rather than independently trained, which weakens the independence claim this project is built on. **The roadmap's default is from-scratch; the alternative must be an explicit, documented decision.**

### 7.7 Kill criterion

**Kill Stage E at R2 and do not proceed to R3 unless all of these hold:** the R1 gate (E1) passed; R2 beats R1 by ≥ 3.0 pp with the CI excluding zero; quality gain per 10× tokens is ≥ 20% (E3); and there is a **written, specific, non-speculative** answer to `compute-feasibility.md` §10 Gate 4's question: *"Does the project have a specific, non-speculative use for a 7B model that a 1.5B model cannot serve?"* **STOP if the answer is "it would be nicer" or "we might want it later."**

**[INFERRED]** The Gate-4 criterion is the important one and it is a *writing* exercise, not a technical one. **[OBSERVED]** §10 Gate 4: *"7B is the rung where a speculative purchase becomes irreversible: $292k–$7.3M and 68+ days."* (Corrected: $36.5k–$913k.) The honest candidates are local deployment at a latency/privacy requirement an API cannot meet, a domain specialisation, a licence/sovereignty requirement, or a demonstrated throughput advantage the workload actually needs. **If none of the four can be written down with a specific workload attached, R3 is not authorised** — regardless of how well R2 went.

## 8. Stage F — Instruction tuning and coding-specific training

**Purpose:** turn a base model into one that follows instructions and behaves like a coding assistant.

**[OBSERVED] The reference public recipe.** Tulu 3 (arXiv 2411.15124, observed 2026-10-21) is the clearest published open recipe, and its scale is directly comparable to this project's: **939K SFT examples** (each pairing a prompt with a human-written or AI-generated response), **271K DPO preference pairs**, **20K RLVR prompts** across GSM8K, IFEval and CodeContests, a *"Persona Hub"* method that conditions synthetic prompts on diverse personas before answering them with an AI teacher and quality-filtering them, and explicit **decontamination against the evaluation benchmarks before training**.

**[INFERRED] Why Tulu 3 matters more than its scale suggests.** It demonstrates the *shape* of a post-training recipe — the stage order (SFT → DPO → RLVR), the data-mixture discipline, the persona-conditioned synthetic generation, and the decontamination step — at a scale a small team can imitate. It also demonstrates the thing we cannot do: **its AI teacher is a frontier model.** Our equivalent teacher must be our own model, which is a bootstrapping problem Stage G addresses.

### 8.1 Dataset properties

| Property | Value | Tag |
|---|---|---|
| **Data — instruction mixtures** | Public open instruction datasets under permissive licences (Tulu 3's mixture is the reference for composition: code, math, knowledge QA, general chat, safety). **[KNOWN FACT]** Tulu 3 uses a **100B-token midtraining mix** (Dolmino) covering "code, math, knowledge QA" before its SFT stage. | [KNOWN FACT] |
| **Data — coding-specific** | Fill-in-the-middle (FIM) training on permissively-licensed code. **[KNOWN FACT]** StarCoder2 was *"trained using the Fill-in-the-Middle objective."* FIM is the one code-specific pretraining objective with an unambiguous published form. | [KNOWN FACT] |
| **Data — our own original** | Specs, tests, reviews, and task descriptions written by us. **[KNOWN FACT]** `licensing-and-provenance-review.md` §9 marks this class **APPROVED IN PRINCIPLE** — *"Original; the highest-quality, lowest-risk class."* | [KNOWN FACT] |
| **Data — synthetic** | **Only from our own model or a permissively-licensed non-reference model.** **[KNOWN FACT]** The reference product is excluded as a generator (§8.2: *"Synthetic data generated by the reference product — Output of the Services"*). **[KNOWN FACT]** Llama 3.1's licence permits synthetic generation and distillation, and `compute-feasibility.md` §13.2 notes this explicitly. | [KNOWN FACT] |
| **Size** | **[ESTIMATE]** 2–5B SFT tokens at R2; 939K examples is ~1.5–3B tokens at 1,600–3,200 tokens/example. | [ESTIMATE] |
| **Licence class** | Per-dataset; the mixture must be shipped as a manifest (Stage D's D6 requirement applies). | |
| **Contamination risk** | **High and specific.** Instruction data is where benchmark contamination usually enters, because SFT datasets are built *from* the same sources benchmarks are built from. **[KNOWN FACT]** Tulu 3 states training data are decontaminated against evaluation benchmarks before training. | [KNOWN FACT] |

### 8.2 Parameter scale targeted

**Same as the base model** — instruction tuning does not change the parameter count. The question is **full fine-tune vs LoRA**, and it is decided by memory:

| | Full fine-tune | LoRA (r=16, α=32, all linear layers) |
|---|---|---|
| **Trainable params at R2** | 1.149B | **[ESTIMATE]** ~0.5–1% of N ≈ 6–12M |
| **Optimizer state** | 18.39 GB (16 B/p) | **~0.22 GB** for the adapter (16 B/p) + frozen bf16 weights 2.30 GB |
| **Fits on 1× 24 GB card?** | **No** (18.39 GB state + activations) | **Yes** |
| **Fits on 1× 80 GB A100?** | Yes | Yes, trivially |
| **Compute** | 6ND, full | ~**2–3×** the full-FT FLOPs per token for the frozen-weight forward pass | 

**[INFERRED]** The pragmatic answer is **full fine-tune at R2** (18.39 GB fits one 80 GB A100, and R2-scale SFT is only ~77 billed GPU-hours total), with LoRA as the *cheap alternative* for fast iteration on small datasets and for the "can I get 80% of the effect for 5% of the cost?" question. **[KNOWN FACT]** For reference on the memory scale of adapter methods at frontier size, `compute-feasibility.md` §12 quotes Llama 3.1's published table: LoRA on a 405B model needs 950 GB versus 3.25 TB for a full fine-tune — a 3.4× saving.

### 8.3 Compute, memory, storage

| Item | R2 SFT | R3 SFT |
|---|---|---|
| **Tokens** | 2.0B (minimum viable) → 5.0B (full mixture) | 5.0B |
| **6ND** | 1.379×10¹⁹ → 3.448×10¹⁹ | 2.174×10²⁰ |
| **Total billed GPU-h (A100 @ 40%)** | 30.7 → 76.7 | 484.0 |
| **Wall-clock (8×A100)** | 3.8 h → 9.6 h | **60.5 h (2.52 d)** |
| **Cost (A100 @ $2.79)** | **$86 → $214** | **$1,350** |
| **Cost (H100 @ $3.99)** | **$34 → $86** | **$541** |
| **State memory** | 18.39 GB (full FT) | 115.97 GB (full FT, needs 8×A100 + ZeRO) |
| **Storage** | ~800 MB (2.5M examples × ~300 B) → **~5 GB** | ~5 GB |

**[OBSERVED] This table was corrected on 2026-10-22** to the fleet-independent cost convention of §7.3 and to Config B's own parameter count (1,149,343,744). It previously carried a "Total GPU-h (8×A100)" column that was the per-GPU figure × 8.

**[ESTIMATE] Post-training is cheap relative to pretraining — 7–17% of the pretraining cost.** This matches `compute-feasibility.md` §12 Scenario C's "typically 5–15% of pretraining compute" line for SFT+RLHF. **[INFERRED]** The implication is important: **the post-training budget is not where the money is, so it should not be where the cutting happens.** Cutting post-training to save 5% of the budget is false economy; the risk there is *quality*, not cost.

### 8.4 Engineering complexity

**Medium.** The engineering is in the *data*, not the training loop:

1. **Format matching.** The SFT target must be exactly the shape the harness expects: a provider-neutral message list with typed content blocks including `tool_use`. **[OBSERVED]** `interface-spec.md` §12.2 defines the provider-neutral message model; the training format must be the *inverse* of that. **[INFERRED]** This is where a mismatch silently destroys performance: a model trained to emit tool calls as markdown fences will not emit `tool_use` blocks, and the harness will never call a tool — while perplexity looks fine.
2. **Chat template and role discipline.** **[OBSERVED]** `architecture.md` ADR-007: instructions are delivered as *user-role attachments*, never system-role. A model trained on a system-role convention will behave differently under our harness.
3. **Loss masking.** Only assistant tokens (including tool-call arguments) get loss; user turns, tool results, and system content are masked. Getting the mask wrong is the most common SFT bug.
4. **Mixture balancing and the decontamination filter** (Stage D's machinery, re-run on the SFT mixture).

### 8.5 Measurable exit criteria

**F1.** **Tool-call format validity is ≥ 99%.** On a held-out set of instruction/tool pairs, the model's emitted tool calls parse as valid `tool_use` blocks with schema-valid arguments, at **≥ 99%**. **[INFERRED]** This is a *model-side* competence, and it is the most important single number in Stage F: a model that cannot emit a valid tool call cannot drive the harness at all. **[KNOWN FACT]** The metric framework has this slot: `M-D7-02` argument-validity rate (`benchmark-and-evaluation-plan.md` §3.2, D7).

**F2.** **Instruction following improves measurably.** The SFT model beats the base model on the D6 dimension by ≥ 3.0 pp (the `improvement` bar, §10.3), paired, with the CI excluding zero, **measured on the claim set** (`benchmark-and-evaluation-plan.md` §5.2) rather than on DEV. **[INFERRED]** The D6 dimension is a *negative-constraint* dimension (G6's metric is the violation rate), and violation rates are low, so its effective n is far below the partition size — the effective n and the discordance rate are reported with the metric, per §10.1's method. **[OBSERVED]** The 3 pp bar is a descriptive threshold on an already-significant result, not a detectable effect at the suite's size; the power against it is reported alongside the result.

**F3.** **The coding-specific objective works.** FIM training produces a measurable gain: given a prefix and suffix with a hole, the model's fill is **executable** at ≥ the base rate plus a stated margin, measured on held-out files. **[KNOWN FACT]** FIM is the objective StarCoder2 used; the *measurable* criterion here is ours, and no public figure for "what fill rate should a FIM-trained 1.1B model achieve" was found — **[UNKNOWN]**, so the criterion is relative to the base model, not absolute.

**F4.** **The model does not regress on the base model's abilities.** Held-out perplexity on the Stage-D validation split is not worse than the base model's by more than a stated tolerance, and the `G11` hard-band (4–5) pass rate does not fall. **[INFERRED]** SFT catastrophically forgetting pretraining ability is a real and common failure, and it is exactly what `G11` was designed to catch.

**F5.** **The SFT data is disjoint from the evaluation suite**, re-verified at this run (not inherited from Stage D). The `G16` gate again.

**F6.** **Cost per successful task is known** — `M-D13-02` — and the model's cost basis is a real number, not `unknown`. **[INFERRED]** For a self-hosted model the cost basis is *compute*, and it must be computed from the actual GPU-hour cost of serving, per `architecture.md` §5.4's requirement that the cost ledger survive an unpriced model.

### 8.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do not build an instruction mixture from scratch. Start from a published, permissively-licensed, decontaminated SFT mixture** (Tulu 3's is the reference for composition and for the decontamination discipline), apply our own evaluation-suite exclusion filter to it, and fine-tune on that. **[INFERRED]** This is Stage D's shortcut applied to post-training, and it is right for the same reason: our filter's marginal value over a well-run public filter is unproven, and the cost of building a competitive SFT mixture is weeks. The one thing we must add ourselves is the **tool-call format matching**, which no public mixture provides in our harness's exact shape.

**[INFERRED]** A second cheap alternative, and an important one: **before any SFT, test whether the base model already performs well under a well-written system prompt and a good tool set.** This is lever (d) and lever (e) doing the work of lever (a). **[OBSERVED]** The admissible evidence for this claim is the project's own black-box observation of the reference product's published CLI, not the prompt research collection: `agent-evidence.md` F10.13 and `feature-checklist.md` S9-SKILL-013 (skills preload the **body**, not the frontmatter), the 33 documented hook events verified in `interface-spec.md` against `agent-reference-shots/docs-cache/hooks-guide.md`, and the 245-key / 17-section settings surface in `agent-evidence.md` F5.1. **[INFERRED]** Those observations are what make the claim *actionable* rather than a slogan: the harness's contribution is composed of specific, individually-implementable mechanisms — permission evaluation, tool schemas, context compaction, session persistence, subagent orchestration — each of which is an engineering task with a test, and each of which raises the ceiling a given model can reach. **[INFERRED]** If prompting + harness gets most of the benefit, the SFT stage's remaining job narrows to *format* (F1) and *specific deficiencies*, and the mixture can be small and targeted (thousands of examples, not millions).

### 8.7 Kill criterion

**Kill the full instruction-tuning track if the base model, under a good system prompt and the full tool set, already achieves tool-call format validity ≥ 99% and instruction-following within 3.0 pp of the SFT model's** — i.e. if SFT buys nothing beyond prompting. **[INFERRED]** In that case, the remaining budget belongs at Stage G (agentic behaviour) and Stage I (context), where the model genuinely cannot substitute.

**Kill the synthetic-data track specifically if the teacher model needed to generate it is not available without violating §D.4.** **[INFERRED]** If the only affordable teacher is the reference product, the synthetic path is closed and the mixture must be human-written or sourced from permissively-licensed public data. This is not a risk to be managed — it is a hard boundary, and it must be checked *before* the mixture is designed, not after.

---

## 9. Stage G — Tool-use, multi-step and agentic behaviour training

**Purpose:** train the model to *drive a loop* — read a context, call a tool, read the result, recover from failure, and continue.

**[INFERRED] The hardest stage, and the one with the sharpest dependency.** Agentic training data is **generated by a model**, and the only model we may use is our own (or a permissively-licensed non-reference one). This is a bootstrapping problem: **Stage G needs Stage F's model, and Stage F's model needs to be good enough to generate usable trajectories.** The ladder that breaks the circularity is: base → SFT (Stage F) → *self-generated* trajectories at SFT quality → filtered → retrain (Stage G) → better trajectories → retrain.

### 9.1 Dataset properties

| Property | Value | Tag |
|---|---|---|
| **Data — trajectory source** | **Self-generated.** Our own SFT model, running the actual harness against real task environments. **[KNOWN FACT]** The reference product is excluded: §8.2 bars using its outputs, tool-call sequences or transcripts as training data. | [KNOWN FACT] |
| **Data — task source** | Permissively-licensed real repositories, plus our own original tasks, plus synthetic tasks constructed to exercise specific tool behaviours. **[KNOWN FACT]** The evaluation suite is excluded here too — and `benchmark-and-evaluation-plan.md` §5.4 is emphatic that even the *aggregated* content of test transcripts counts: *"Training on 'here is a summary of how the agent solved a set of benchmark tasks' leaks the answers just as effectively as training on the tasks themselves."* | [KNOWN FACT] |
| **Data — rejection sampling** | Multiple samples per task; keep only trajectories that pass the oracle. **[INFERRED]** This is the mechanism that makes self-generated data useful: the *filter* is the signal, and the filter is a verifier, not a teacher. | [INFERRED] |
| **Size** | **[ESTIMATE]** 20,000 trajectories × 30 rounds ≈ 2.4B prefill tokens / 180M decode tokens. | [ESTIMATE] |
| **Licence class** | Our own generated data, trained on permissively-licensed environments — the licence of the *base model* governs the weights, the licence of each *corpus* governs that corpus, and they are independent (`licensing-and-provenance-review.md` §13.3). | [KNOWN FACT] |
| **Contamination risk** | **The highest in the roadmap.** The trajectories are generated by a model that has seen public code, in environments that may contain evaluation repositories. Requires the full Stage-D filter applied to (a) the environments and (b) the trajectory text. | |

### 9.2 Parameter scale targeted

**Same as the base model.** Stage G is post-training. The relevant scale question is **how much data** — and the answer depends on how many trajectories are needed to cover the tool-use distribution.

### 9.3 Compute, memory, storage

**Two cost lines, and the second dominates.**

| Line | Item | Value |
|---|---|---|
| **Generation — prefill** | 2.4B prefill tokens; prefill is FLOPs-bound at ~2N FLOPs/token → 5.517×10¹⁸ FLOPs → **12.3 billed GPU-h** (wall 1.53 h on 8×A100) | [ESTIMATE] |
| **Generation — decode** | 180M tokens at ~3,548 tok/s aggregate (b=1 per GPU, 50% of the 2,039 GB/s bandwidth model) → **14.1 h wall = 113 billed GPU-h** | [ESTIMATE] |
| **Generation (the real problem)** | **Quality-driven resampling** | **[INFERRED]** A rejection-sampling pipeline that keeps only passing trajectories typically discards **70–95%** of samples. **[UNKNOWN]** No public figure for the pass rate of an R2-class model on real agentic tasks was found; the discard rate is therefore unknown and must be *measured at a pilot scale* before the full generation run is budgeted. **This is the single largest unknown in Stage G.** |
| **Training** | Second training pass on the filtered trajectories: 2.4B tokens at 6ND → 1.655×10¹⁹ FLOPs → **36.8 billed GPU-h** (wall 4.6 h on 8×A100) | [ESTIMATE] |
| **Memory** | Training: 18.39 GB state (R2). Generation: 2.30 GB weights + KV cache 1.50 GiB at 32k ctx (b=1) | [ESTIMATE] |
| **Storage** | Trajectories: 2.4B tokens of prompt+completion ≈ **~10 GB** as JSONL with tool metadata (5–20× the tokenised size). Filtered subset ~1–3 GB. | [ESTIMATE] |

**[ESTIMATE] Total Stage G cost at R2, under three resampling multipliers for the unknown discard rate:**

| Resample multiplier | Generation | Training | Total billed GPU-h | Cost |
|---|---|---|---|---|
| **1×** (every sample passes) | 125 | 36.8 | **162** | **$452** |
| **4×** (75% discard) | 500 | 36.8 | **537** | **$1,498** |
| **10×** (90% discard) | 1,250 | 36.8 | **1,287** | **$3,591** |

**[INFERRED]** This is *affordable* — the same order as one R2 pretraining run — which is why Stage G is not gated on cost but on the *quality* of the generated trajectories. **[OBSERVED] The table was corrected on 2026-10-22** to the fleet-independent convention of §7.3; it previously read "927 GPU-h ≈ $2,586" at a 4× multiplier, because the generation and training lines each carried a fleet-doubled figure. **[INFERRED]** The corrected figure at 4× is **$1,498** — under half the old number, and the conclusion is unchanged.

**[INFERRED] The bootstrapping risk dominates the cost risk.** If our SFT model cannot solve tasks reliably enough to produce passing trajectories, the rejection filter keeps almost nothing, and the project has a problem that no amount of GPU time solves. **This is why Stage G's pilot must come before its full run**, and why the pilot's exit criterion is a *generation* metric, not a training metric.

### 9.4 Engineering complexity

**High — the highest of the eleven stages, after Stage H.**

1. **The trajectory recorder.** **[OBSERVED]** The harness already emits a rich event stream (`system/init`, `assistant`, `user`, `result`, plus `tool_result_meta[].permission_decision`, `structuredPatch`, `compact_boundary` metadata). **[OBSERVED] These are the project's own black-box captures, not a general belief about agent behaviour:** the event shapes and the permission-denial contract are recorded in `agent-reference-shots/PROTOCOL-NOTES.md` (the `tool_result_meta[].permission_decision` object at line 82, the `structuredPatch` diff shape at line 105, and the `{"type":"create", ...}` file-creation record at line 116), the compaction boundary's observable `system/compact_boundary` event and its deliberate `parentUuid: null` / `logicalParentUuid` chain break are specified in `interface-spec.md` §14.7 and §14.10 (lines 1954, 2384, 2407, 2441), and the full denial → error → course-correction trace is preserved at `agent-reference-shots/tool-error-contract.json` (`agent-evidence.md` F-lines 178, 742, 2513; `benchmark-and-evaluation-plan.md` §4.2 F9). **[INFERRED]** Turning that into training examples is mostly formatting — and it is a *solved* problem for us because our own harness produces it. **This is a genuine advantage of the clean-room approach: we own the trajectory format, so there is no permission or format obstacle to collecting training data.** **[INFERRED]** The captures are also the *format specification* for the recorder: the recorder's output schema is derived from these observations, so the stage is a specification-to-code step rather than a research problem. **[KNOWN FACT]** These observations are admissible as direct observation of a published product's published interface; **they are not evidence about the provider's model weights or training methods, and no stage may cite them as such** (§16.1 item 7).
2. **The oracle/verifier.** Each task needs a programmatic success check (tests pass, a file created, an exit code). **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §4.2's nine families each have a named oracle type. **[INFERRED]** The oracle is the hard part and also the *reusable* part — it is the same oracle the evaluation suite uses, subject to the suite being excluded from training tasks.
3. **Multi-turn credit assignment.** Which of 30 rounds deserves the credit for a task that succeeded? **[INFERRED]** Simplest correct approach: train on the *whole* successful trajectory (all assistant tokens), not per-step reward. **[UNKNOWN]** No public figure was found for how much per-step credit assignment improves agentic training at this scale.
4. **Negative examples and failure recovery.** **[KNOWN FACT]** The reference evidence records the model visibly course-correcting across four consecutive tool failures (`tool-error-contract.json`, per `benchmark-and-evaluation-plan.md` §4.2). **[INFERRED]** Training data must include *recovered* failures, not only successes, or the model never learns to recover.
5. **Context-length reality.** A 30-round trajectory with growing context easily exceeds 8,192 tokens. **[INFERRED]** This makes Stage G depend on Stage I (long context) or force trajectory truncation, and the ordering matters.

### 9.5 Measurable exit criteria

**G1 (the pilot gate, before any full generation run).** **At least 20% of sampled trajectories on a 50-task pilot end in oracle-verified success**, at a fixed tool-call budget, with the mean number of rounds to success ≤ 30. **[INFERRED]** The 20% figure is a **[SPECULATIVE TARGET]** chosen because it makes rejection sampling economically viable: at 20% pass, 5 samples per task yield ~1 passing trajectory per task, so a 20,000-trajectory target needs ~100,000 generated samples. **[UNKNOWN]** Whether an R2-class model can reach 20% on real repository tasks is not determinable in advance — it is the measurement this pilot exists to produce.

**G2.** **Tool-call validity holds under long context.** `M-D7-02` argument-validity rate stays ≥ 99% on trajectories of ≥ 20 rounds. **[INFERRED]** Validity commonly degrades with context length; this criterion catches it.

**G3.** **Tool-error recovery improves.** `M-D7-04` tool-recovery rate improves by ≥ 3.0 pp over the SFT-only model, paired, **measured on the claim set** (`benchmark-and-evaluation-plan.md` §5.2). **[INFERRED]** As with G5's gate in the evaluation plan, the metric is *conditional on a tool error occurring*, so its effective n is the number of tasks that produced an error — smaller than the partition size, and possibly much smaller. The effective n is reported with the metric, because a rate computed over 12 conditional events and a rate computed over 120 are different measurements with the same label.

**G4.** **End-to-end task completion improves.** `M-D8-01` end-to-end completion rate improves by ≥ 5.0 pp (the `material improvement` bar, `benchmark-and-evaluation-plan.md` §10.3), paired, with the discordance table, **measured on the claim set (§5.2 of the evaluation plan) — not on TEST-A and not on the LIVE gate partition.** **[OBSERVED] Correction (2026-10-22).** This criterion previously read *"on TEST-A"*. That was wrong on two counts. First, **TEST-A is the shadow/filter partition** (§12.3 of the evaluation plan): it is the partition the challenger is screened on before the gate, and a gate that was screened on TEST-A has already had TEST-A's failures inspected — so a 5 pp improvement measured there is a number from a set the team has looked at, not a held-out set. Second, **the improvement bar itself is a power statement, and it was stated without its power.** §10.3's `material improvement` bar requires the claim set's two-sided power against 5 pp to be at least 80%; at the S3 claim set's initial n = 370 that power is **45%**, and it reaches 80% only after **three retired LIVE slices** (n ≥ 1,120, power 0.88 — `benchmark-and-evaluation-plan.md` §10.1's accumulation table). **[INFERRED]** So G4 is now stated as a **conditional**: the stage may exit when the measured improvement on the claim set meets the bar **and** the claim set's power against 5 pp is reported alongside it; and the *stage* may not exit on a 5 pp claim until the claim set has three retired slices. If the improvement is not yet powered to 5 pp, the criterion's verdict is **`inconclusive`**, not a pass and not a fail, and the correct outcome is to continue gating (which accumulates slices) rather than to lower the bar. **[INFERRED]** This is uncomfortable to write down, and it is the honest shape of the problem: **a 7B model trained from scratch will not produce a detectable 5-point gain on a 370-task suite, and the plan should say so in advance rather than discover it in the release review.**

**G5.** **No safety regression.** The `G3` (zero duplicate-side-effect incidents), `G4` (zero unauthorised actions, zero protected-path attempts) and `G2` (zero new test failures) hard gates still hold after Stage G's training. **[INFERRED]** This is a hard gate on a *training* stage, which is unusual, and it is correct: `benchmark-and-evaluation-plan.md` §3.2 D14 notes duplicate side effects are *"invisible to pass/fail scoring"* — a model trained to act more aggressively will produce them, and nothing else will catch it.

**G6.** **The trajectory corpus is disjoint from the evaluation suite**, checked at the text level (not just the environment level), and the `G16` audit passes exactly.

**G7.** **Generation cost per usable trajectory is measured** and reported (GPU-hours per passing trajectory). **[INFERRED]** This is the number that decides whether Stage G is repeatable, and it is the number the pilot produces.

### 9.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do not build a synthetic environment.** Use *real* repositories as the environment, with the real harness and real tools, and rely on rejection sampling to filter. **[INFERRED]** A synthetic environment (a generated repo, generated tests) is a large engineering project with its own failure modes, and it is unnecessary: real repositories come with real tests, and the oracle is "the repo's own test suite goes green."

**[SPECULATIVE TARGET]** Second alternative: **train on trajectories collected from tasks where a *human* wrote the specification** — i.e. our own original tasks (`licensing-and-provenance-review.md` §9 marks this class APPROVED IN PRINCIPLE). **[INFERRED]** The number of such tasks is small, but they are the highest-quality data available and they avoid the licence question entirely. Use them to validate the pipeline (G1's pilot) before scaling to 20,000 generated trajectories.

**[INFERRED]** Third, and possibly most valuable: **much of what "agentic behaviour" consists of may be purchasable with lever (e) rather than trained.** A model that fails at multi-step tasks because the harness gives it bad tool descriptions is not an agentic-capability problem; it is a tool-description problem. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §3.5 lists *"the harness is part of the model"* as metric failure mode #3, and §8.5 requires a tool fingerprint diff for any harness comparison — precisely so that this attribution can be made. **Before training for agentic behaviour, prove with a paired experiment that the harness is not the limiting factor.**

### 9.7 Kill criterion

**Kill Stage G's training track if the pilot (G1) fails: if fewer than 5% of sampled trajectories on the 50-task pilot reach oracle-verified success, at a fixed budget, after the harness and prompt have been optimised.** **[INFERRED]** At a <5% pass rate, rejection sampling needs >20 samples per successful trajectory, and — more importantly — a model that succeeds on <5% of real repository tasks will not produce training data that teaches competence. The correct response at that point is **not** more training; it is to go back and fix levers (d) and (e), or to accept that the model is not the bottleneck and that this project's value lies in the harness.

**Kill the synthetic-environment sub-track if building a synthetic environment would take more engineer-weeks than the entire rest of Stage G.** **[INFERRED]** A synthetic environment is an unbounded research project wearing a data-pipeline costume.

---

## 10. Stage H — Preference optimisation and RL, only where technically justified

**Purpose:** improve the model using *verified* feedback — and only where a verifier exists. This stage is the one most likely to be skipped, and the one most likely to waste money if attempted prematurely.

### 10.1 The justification test, stated before the stage

**[INFERRED]** Preference optimisation requires a **signal better than the model's own output distribution**. There are exactly three such signals available to us, each with a strict precondition:

| Method | Signal | Precondition | Available to us? |
|---|---|---|---|
| **DPO on human-labelled pairs** | Human or strong-teacher preference between two completions | A preference source that is *not* the model being trained | **[PARTIAL]** Human labels are available but expensive. A strong-teacher source is barred if the teacher is the reference product (§D.4). |
| **RLVR — RL with verifiable rewards** | A **programmatic** verifier: code compiles, tests pass, the answer matches a key | The task must have a **deterministic, cheap, adversarial-resistant** checker | **[YES]** The strongest signal available, because the verifier is *ours* and is not a model. |
| **Rejection sampling / RFT** | The oracle's pass/fail | An oracle per task | **[YES]** Stage G's mechanism, *simpler than DPO* and using the same signal. |

**[INFERRED] The honest ordering.** Rejection sampling first, RLVR second, DPO on human-labelled pairs last. Rejection sampling and RLVR use *the same verifiable signal* — the oracle — and rejection sampling is dramatically simpler: no reward model, no policy-gradient machinery, no KL-to-reference, no instability. DPO on human-labelled pairs is weakest for *this* project, because human labelling of code-completion preferences is slow and expensive and the alternative teacher is licence-barred.

**[KNOWN FACT] The public reference for the scale.** Tulu 3 used **20K RLVR prompts** across GSM8K, IFEval and **CodeContests**, on top of 939K SFT examples and 271K DPO pairs (arXiv 2411.15124, observed 2026-10-21). **[INFERRED]** The ratio is instructive: RLVR is a **small** dataset (20K prompts vs 939K SFT examples) because each prompt carries many rollouts — which is also why RLVR is affordable. The cost is in rollouts, not in prompts.

### 10.2 Dataset properties

| Property | RLVR on our own tasks | DPO on preference pairs |
|---|---|---|
| **Data** | Our own tasks with programmatic verifiers. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §4.2's nine families each have a named oracle type (hidden regression test, existing suite, rule-based state checker, gold-patch file set, harness-contract assertions, human rubric). | Pairs of (prompt, chosen, rejected) completions. **[KNOWN FACT]** Tulu 3's 271K pairs. |
| **Size** | **[ESTIMATE]** 20,000 prompts × 8–16 rollouts each = 160,000–320,000 rollouts. | **[ESTIMATE]** 50,000–200,000 pairs at R2. |
| **Licence class** | Ours. | Depends entirely on the completion source; the reference product is excluded. |
| **Contamination risk** | The verifier is derived from the same family of tasks as the evaluation suite — **the tasks themselves must be held out**, even though the *verifier pattern* is shared. **[INFERRED]** Sharing a verifier *pattern* is fine; sharing a task is not. | Same. |

### 10.3 Compute, memory, storage

**DPO cost, at R2 (Config B, 1,149,343,744):**

| Pairs | Tokens per pair | Total tokens | FLOPs (8ND: policy fwd+bwd + reference fwd) | Total billed GPU-h | Cost |
|---|---|---|---|---|---|
| 50,000 | 1,500 | 7.5×10⁷ | 6.896×10¹⁷ | 1.53 | **$4.28** |
| 200,000 | 2,000 | 4.0×10⁸ | 3.678×10¹⁸ | 8.19 | **$22.84** |
| 1,000,000 | 2,000 | 2.0×10⁹ | 1.839×10¹⁹ | 40.93 | **$114.20** |

**[ESTIMATE] RLVR cost at R2:** dominated by rollout generation, not by the gradient update. 320,000 rollouts × ~10 rounds × ~4,000 prompt tokens = **1.28×10¹⁰ prefill tokens** → 2×N×tokens = 2.942×10¹⁹ FLOPs → **65.5 billed GPU-h ≈ $183**. Plus the policy update: 1.28×10¹⁰ tokens × 6ND = 8.827×10¹⁹ FLOPs → **196.5 billed GPU-h ≈ $548**. **[INFERRED]** **RLVR at R2 is roughly a $731 line item for the gradient-and-prefill work alone, before any decode, orchestration or resampling overhead — and that overhead is where the real cost hides.** It is the same order as one R2 pretraining run at the 30 B-token arm ($1,285), which is affordable but not trivial, and it is the reason RLVR sits behind a pilot.

**[OBSERVED] This section's arithmetic was corrected on 2026-10-22** to the fleet-independent convention of §7.3. The DPO table previously carried fleet-doubled GPU-hours, and the RLVR line previously read "~5,200 GPU-h ≈ $14,500" and "~15,600 GPU-h ≈ $43,500" — figures that had the fleet multiplied in twice. **[INFERRED]** The corrected RLVR figure is **~44× smaller** than the old one, and this *strengthens* the section's conclusion rather than weakening it: **DPO at R2 costs single-digit to low-hundreds of dollars and RLVR costs under a thousand, so the ordering "rejection sampling first, RLVR second, DPO last" is even more clearly right.** The honest caveat is that these are *gradient and prefill* costs only; decode, rollout orchestration and resampling are not in the table and are not small.

**[ESTIMATE] Memory:** DPO at R2 needs the policy state (18.39 GB) **plus a frozen reference model** (2.30 GB bf16 weights) → ~21 GB, fits one 80 GB A100. RLVR at R2 needs the policy state plus a rollout engine; the reference model is not needed (unlike DPO's implicit KL-to-reference), but the sampler must run alongside the trainer.

**[ESTIMATE] Storage:** preference pairs ~200,000 × ~4 KB = **800 MB**; RLVR rollouts 320,000 × ~15 KB = **~4.8 GB**.

### 10.4 Engineering complexity

**Very high, and the highest in the roadmap.**

**[INFERRED]** The specific difficulties:

1. **Reward hacking.** A programmatic verifier can be gamed — the model learns to make the test pass without making the program correct. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §3.5 failure mode #1 is exactly this: *"The oracle is a proxy... Passing tests ≠ correct code."* **[INFERRED]** Mitigations: (a) the oracle file is read-only to the agent and its hash verified after the run (`M-D2-03` locality / D2's guard); (b) a human spot-check sample of every evaluation batch; (c) mutation-coverage reporting where the oracle permits it.
2. **Reward sparsity.** A 30-round task with a binary terminal reward gives almost no learning signal. **[INFERRED]** This is why Stage G's rejection sampling is the better first move.
3. **KL management and off-policy drift.** The classic DPO/RL failure where the policy leaves the distribution where the preference data was valid.
4. **Infrastructure.** A training loop with a concurrent rollout engine, weight synchronisation between trainer and sampler, and reproducible seeding is genuinely hard to get right, and it is *not* the same infrastructure as pretraining.

### 10.5 Measurable exit criteria

**H1 (the justification gate — must pass before any spend).** **A verifier exists for the target task class, and it is adversarial-resistant.** Concretely: the verifier's pass rate on *deliberately wrong* solutions is < 5%, measured on a set of human-written near-miss solutions. **[INFERRED]** This is the criterion that makes Stage H legitimate rather than a way of training the model to please a broken checker. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §3.2's D2 metric already specifies the mutation-style guard: the oracle test file is *"read-only to the agent and its hash is verified after the run; any mutation is a hard failure, not a pass."*

**H2.** **The improvement is measured on the claim set** (`benchmark-and-evaluation-plan.md` §5.2) — never on the LIVE gate partition, never on a set that was used for tuning — **paired, with the CI excluding zero**, and it is ≥ 3.0 pp (`improvement` bar) or ≥ 5.0 pp (`material improvement` bar) per §10.3. **[INFERRED]** The power against the claimed effect size is reported with the result, and if that power is below the bar §10.3 requires for the claim, the verdict is `inconclusive` rather than an improvement. **[OBSERVED]** Note the structural point this criterion inherits: because the claim set *accumulates retired LIVE slices* (§10.1), an RLVR stage that runs late in the programme has a larger claim set available to it than an early one. **[INFERRED]** That is a real advantage and it is also a bias — the stage that runs last gets the better measurement. The mitigation is that the claim set's composition and slice history are published with every claim (§10.3, `benchmark-and-evaluation-plan.md` §5.3), so a reader can see exactly which slices the claim rests on.

**H3.** **No safety regression** — the `G2`/`G3`/`G4` hard gates still hold. **[INFERRED]** RLVR in particular optimises hard for task success and can degrade caution, so this gate is not optional.

**H4.** **No reward hacking is detected.** On a human-written holdout of near-miss solutions, the improved model's pass rate is not anomalously high relative to its improvement on genuine solutions. **[INFERRED]** This is the metric's failure mode #1 turned into a gate.

**H5.** **The negative-result discipline is honoured.** At least one comparison that produced `within-noise` or `inconclusive` is reported in full. **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §11.4 criterion (v) makes this an M4 release requirement: *"If the archive contains only successful comparisons, the release is not accepted — because a measurement apparatus that never records a failure is not measuring."*

### 10.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do rejection sampling (RFT).** It uses the same verifier signal as RLVR, requires no reward model and no policy-gradient machinery, is a single extra training pass over the filtered trajectories, and **is Stage G's machinery, which is already built**. **[INFERRED]** The cost is sample inefficiency (one gradient pass per batch of passing trajectories rather than per-sample credit assignment), but at our scale — where a full RLVR gradient-and-prefill loop costs roughly **$731** and rejection-sampling training is a **single pass over Stage G's already-filtered trajectories at ~$103** — the simplicity wins decisively. **[OBSERVED]** Both figures are from §10.3's corrected tables; the pre-correction versions of those tables ($15k–$60k for RLVR, $300–$900 for RFT) carried a fleet-multiplication error and overstated the gap by more than an order of magnitude. **[INFERRED]** The *conclusion* is unchanged and in fact strengthened — but the honest caveat now dominates: at R2, **the entire preference-optimisation stage is a sub-$1,000 line item**, which means **the reason to prefer rejection sampling is engineering simplicity, not money**. **[INFERRED]** If the cost difference is that small, the decision to prefer RFT over RLVR rests entirely on RLVR's *fragility* (reward hacking, KL drift, infrastructure) and not on its expense — and the reason Stage H's kill criterion is written to make "do nothing" a legitimate outcome.

**[SPECULATIVE TARGET]** Second alternative: **do nothing.** **[INFERRED]** This is the under-discussed option and it deserves an explicit place in the roadmap. At R2, the difference between a well-SFT'd model and a preference-optimised one is likely small compared to the difference between a good harness and a mediocre one (levers (e) and (d)). **Stage H's kill criterion below is written so that "do nothing" is a legitimate, well-evidenced outcome** — not a failure.

### 10.7 Kill criterion

**Kill Stage H entirely if any of the following holds:**

- **H1 fails** — no adversarial-resistant verifier exists for the target task class. **[INFERRED]** Without one, preference optimisation trains the model to please a checker. This is the primary kill criterion.
- **Rejection sampling at Stage G produced no measurable gain** (G4 failed). **[INFERRED]** If training on *oracle-verified* trajectories does not help, then training on *oracle-scored* trajectories will not help either — RLVR is a refinement of the same signal, and it is a much more expensive refinement. **This is the cleanest stage-to-stage dependency in the roadmap.**
- **The measured gain from DPO/RLVR is < 3.0 pp on a held-out set with the CI excluding zero**, after one attempt with a reasonable configuration. **[INFERRED]** The second attempt costs 2–3× and is very unlikely to change a sub-3-point result into a ≥3-point one.

**[INFERRED]** Note what this kill criterion *is*: it says that if the cheap, simple, high-signal methods have not produced a gain, the expensive, complex, fragile ones are unlikely to. That is the correct economics, and it is why Stage H sits behind Stage G rather than in parallel with it.

---

## 11. Stage I — Long context, memory and inference improvements

**Purpose:** make the model able to *hold* a large amount of relevant material, and make the harness able to give it to. This stage is where the interaction between a model and its serving stack becomes visible, and it is where the cheapest large wins live.

### 11.1 The two problems, which are not the same

**[INFERRED]** "Long context" is two separable problems and conflating them causes wasted spend:

1. **In-context capability** — can the model *use* a long context? Retrieval from position 5,000 when the answer is at position 40,000. This is a capability problem: it is fixed by training (Stage I) and by evaluation.
2. **Serving capacity** — can we *afford* to put a long context in front of the model at all? This is an economics problem: it is fixed by KV-cache compression, quantisation, prefix caching and paging (Stage J).

**[INFERRED]** The classic "lost in the middle" result is a *capability* failure: relevant material is present and attended to poorly. **[INFERRED]** Our own measurement apparatus must separate the two, because a model that "fails" a long-context task may be failing for reasons the harness could have fixed.

**[KNOWN FACT]** The public reference for a staged long-context recipe: **OLMo 3 (arXiv 2512.13961)** uses a three-stage recipe with a **65,536-token** context length, with the final stage continuing at long sequence length. **[KNOWN FACT]** The OLMo 3 / Dolma 3 corpus includes a **50B-token long-context mix** (arXiv 2512.13961, observed 2026-10-21). **[INFERRED]** Both facts are evidence that the long-context *data* is the expensive part, not the long-context *arithmetic*.

### 11.2 The arithmetic that `6ND` omits

**[KNOWN FACT]** The `C = 6ND` formula (arXiv 2203.15556) counts dense matmul FLOPs only. It **omits attention FLOPs**, which grow with sequence length while `6ND` does not.

**[ESTIMATE] The attention overhead, derived.** Per token, forward attention is `2·L·d·Q` FLOPs (scores + value-weighted sum); backward is 2× forward. Total `= 12·L·d·Q` FLOPs per token, where `Q` is the context length. The dense term per token is `6N`. The ratio is therefore:

```
attention_overhead = 12·L·d·Q / (6N)
```

**[OBSERVED]** Executed against the project's own `research/spl/param_math.py` parameter counts. **[OBSERVED] This table was corrected on 2026-10-22**: it previously carried `12·L·d·Q` values **100× too large** (the `d` factor was applied twice), and its overhead column was wrong by the same factor as a result.

| Config | L | d | Q | 12·L·d·Q (FLOPs/token) | 6N (FLOPs/token) | Overhead |
|---|---|---|---|---|---|---|
| B (1.149B) | 24 | 2048 | 8,192 | 4.832×10⁹ | 6.896×10⁹ | **0.70×** |
| B | 24 | 2048 | 32,768 | 1.933×10¹⁰ | 6.896×10⁹ | **2.80×** |
| B | 24 | 2048 | 131,072 | 7.731×10¹⁰ | 6.896×10⁹ | **11.21×** |
| C (7.248B) | 32 | 4096 | 8,192 | 1.289×10¹⁰ | 4.349×10¹⁰ | **0.30×** |
| C | 32 | 4096 | 32,768 | 5.154×10¹⁰ | 4.349×10¹⁰ | **1.19×** |
| C | 32 | 4096 | 131,072 | 2.062×10¹¹ | 4.349×10¹⁰ | **4.74×** |

**[INFERRED]** The corrected numbers change the *shape* of the conclusion, not just its scale, and the change matters. **Attention is not the dominant cost at the context lengths this project will actually train.** At Config B's 8,192-token working context the attention term is **0.70×** the dense term — attention is *not* a significant overhead at all, and the crossover to attention-domination happens between 8k and 32k (2.80× at 32k) and reaches 11.21× at 131k. The old table's claim that attention was "70×" the dense cost at 8k was false by two orders of magnitude, and it would have wrongly implied that long-context training was prohibitively expensive at every context length this project will use.

**[INFERRED]** The corrected table is *more* useful, not less, because it identifies where the cost actually lives: **the dense term dominates below ~16k tokens; attention matters at 32k and above; and at 131k the total multiplier is ~12× (Config B) or ~5.7× (Config C).** **[INFERRED]** And note the model-size dependence the old table obscured: Config C's attention overhead is *lower* than Config B's at the same context (4.74× vs 11.21× at 131k), because C is wider and deeper relative to its context — so **the attention penalty is not worse for bigger models at fixed context**, it is worse for *longer* contexts. That is the correct intuition, and the old numbers obscured it.

**[INFERRED]** This remains the technical reason Stage I is budgeted separately from Stage E rather than folded into a scaled `6ND` estimate — but the separation is now justified by a **measurable 1.7×–12× multiplier**, not by an assumed two-orders-of-magnitude penalty. **[ESTIMATE]** A full pretraining run at 131k context for Config B would cost ~12× a short-context run (at the 30 B-token arm: 29.3 days on 8×A100 against 2.40 days), and the public anchors confirm this is why nobody trains at 128k from scratch on a small model — though "nobody does it because it is 12× more expensive" is a much weaker and more accurate claim than "because it is 100× more expensive".

### 11.3 Dataset properties

| Property | Value |
|---|---|
| **Data** | Continuation of the Stage D corpus, re-chunked to long sequences, plus a long-context mix |
| **Size** | **[ESTIMATE]** 10% of the Stage E token budget as a phase-2 continuation. At R2 that is **2.30B tokens** (10% of 23.0B) |
| **Licence class** | Inherits Stage D's per-corpus licensing (`licensing-and-provenance-review.md` §9). **[INFERRED]** Re-chunking does not change the licence, but a *mixture* of corpora inherits the most restrictive applicable term, so the long-context mix must be licence-audited as a whole |
| **Contamination risk** | **[INFERRED]** *Lower* than Stage D, and this is a genuinely important point: a long-context pack is a concatenation of documents, so a benchmark task is very unlikely to appear as a contiguous chunk. **[INFERRED]** But the *provenance* risk is higher: concatenating documents from different sources into one long sequence can reconstruct a document that a substring search would miss. **[INFERRED]** The `not-in-index` and `rewording` controls from `benchmark-and-evaluation-plan.md` §4.6 do not obviously survive re-chunking, and a new control is needed: **indexing the long pack at the document level and at the window level** |

### 11.4 Compute, memory, storage

**[ESTIMATE] The three candidate context lengths at R2, 2.30B tokens** (dense `6ND` + the attention term of §11.2, at Config B's own N = 1,149,343,744):

| Context Q | Dense FLOPs | Attention FLOPs | Total FLOPs | Total billed GPU-h | 8×A100 wall time | Cost |
|---|---|---|---|---|---|---|
| 8,192 | 1.585×10¹⁹ | 1.112×10¹⁹ | 2.697×10¹⁹ | 60.0 | 7.5 h | **$168** |
| 32,768 | 1.585×10¹⁹ | 4.446×10¹⁹ | 6.031×10¹⁹ | 134.2 | 16.8 h | **$375** |
| 131,072 | 1.585×10¹⁹ | 1.778×10²⁰ | 1.937×10²⁰ | 431.1 | 53.9 h | **$1,203** |

**[INFERRED]** **The headline finding of this stage: extending context from 8k to 32k costs 2.24× and from 32k to 131k costs 3.21× — and the *entire* 131k run costs $1,203.** Long context is *not* a budget problem at R2; it is a data and evaluation problem. **[INFERRED]** That is a strong argument for doing Stage I at R2 rather than deferring it to R3, where the same 10% budget is ~16× more expensive.

**[OBSERVED] This table was corrected on 2026-10-22.** The FLOPs column and the wall-clock column were already correct — they had been computed with a correct attention term — but the cost column carried the fleet multiplication (§7.3's convention), making it 8× too high, and the "Per-GPU h" heading was a misnomer for a fleet-independent total. The corrected costs are $168 / $375 / $1,203, against the previous $1,339 / $2,995 / $9,616. **[INFERRED]** **The stage's conclusion is unchanged and is stronger: at R2, training at 131,072 tokens costs less than a single dinner.** The reason to keep context modest is therefore *not* compute — it is the data and evaluation burden in §11.5, and the serving cost in Stage J.

**[ESTIMATE] Memory.** Training at Q=131,072 with gradient accumulation over micro-batches: activation memory scales with micro-batch × sequence length. For Config B at Q=131,072, a single 8k-token micro-batch of activations (with full checkpointing) is ~4.2 GB, so 16 micro-batches of 8k fit the sequence but must be accumulated. **[INFERRED]** The state memory is unchanged (18.39 GB for Config B at bf16 + 8-bit Adam) — sequence length does not change the optimiser state, only the activations, and gradient checkpointing trades compute for that.

**[ESTIMATE] Storage.** 2.30B tokens at 2 B/tok (filtered) = **4.6 GB** packed; at 4 B/tok (raw) = **9.2 GB**. Checkpoint: Config B at 16 B/p = 18.4 GB per checkpoint; 3 checkpoints (base, phase-1, phase-2) = **55 GB**.

### 11.5 Engineering complexity

**Medium.** Less than it looks, because the *training* is a continuation of Stage E's run — same code path, different sequence length and a different data chunker. The genuinely new work is:

1. **A position-encoding change or a position-encoding-compatible retrain.** **[INFERRED]** If Stage B chose learned absolute positions, extending to 131k is a shape change, not a scale change. **[INFERRED]** This is a Stage B design decision whose cost is paid here, which is why Stage B's exit criteria must include an explicit statement of the position-encoding scheme and its extrapolation behaviour.
2. **A window-aware chunker** and the dual-index contamination control.
3. **Attention-kernel correctness at long sequence** — a numerically-equivalence test between the long-context kernel and the reference implementation at short sequence, at several lengths. **[INFERRED]** This is a classic source of silent degradation and should be a hard gate, not a test.
4. **The evaluation of in-context capability** — the "needle" family is too easy and too gameable; the real requirement is *retrieval-and-reason* at range. **[INFERRED]** Our own `benchmark-and-evaluation-plan.md` task families should be extended with a long-context variant of F1–F9 rather than a synthetic needle test.

### 11.6 Measurable exit criteria

**I1.** **The model uses the context.** A long-context evaluation variant of the existing task families shows a **paired** improvement (or at least no degradation) at 32k relative to 8k, with the 95% CI excluding zero on at least the retrieval-and-reason subset. **[INFERRED]** If a 32k model performs *worse* than its 8k sibling on 8k tasks, the long-context training damaged short-context ability — that is a hard fail, not a pass.

**I2.** **No positional degradation curve.** Success rate plotted against position within the context does not show a collapse at the far end beyond a pre-registered threshold.

**I3.** **Kernel equivalence.** The long-context attention kernel matches the reference implementation to within floating-point tolerance at Q = 2,048 / 8,192 / 32,768, and the 131,072 run is checked against a chunked reference.

**I4.** **Cost of a long-context inference call is measured and within the serving budget** — see Stage J.

**I5.** **The harness passes a full-length context without a silent truncation.** **[INFERRED]** A context-window budget manager that silently truncates from the left is a classic and severe failure: the model sees the end of the file and not the beginning, and nothing in the transcript says so. The harness must **log every truncation and report it in the turn summary**, and the evaluation must treat an un-logged truncation as a hard error.

### 11.7 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do not train at 131,072.** Train at 8,192 or 32,768 and get the *serving* right first. **[INFERRED]** Two cheap interventions deliver most of the practical benefit at a fraction of the cost:

1. **Structured retrieval instead of brute-force context** — the harness (lever (e)) selects and *reorders* relevant material, which is worth more than raw context length for the target workload. **[INFERRED]** This is the harness's job, not the model's, and it is a Stage G/H-adjacent change with zero training cost.
2. **Prefix caching** — the system prompt, project context and tool definitions are a stable prefix across every turn of a session. Caching them makes long-context serving nearly free for the repeated part.

**[INFERRED]** Both are explicitly *harness* levers and must be attributed to lever (e) in the table in §2.1, not to lever (a). A long-context capability that actually comes from retrieval-and-reordering is a **harness** capability wearing a model's clothes, and the attribution table must say so.

### 11.8 Kill criterion

**Kill long-context *training* if any of the following holds:**

- **I1 fails at 32k after two attempts** (one with a 10% long-context mix, one with 20%). **[INFERRED]** Longer context is not free at inference; if the model cannot use 32k, training at 131k is strictly worse, since it degrades the common case to serve a rare one.
- **The retrieved-context approach (cheap alternative) delivers the same or better task success at 1/10 the serving cost.** **[INFERRED]** In that case the long-context model is solving a problem we can solve more cheaply in the harness, and the training spend is better spent on Stage F or G.
- **Serving cost at the target context exceeds the budget** before the model is even useful. **[INFERRED]** An unusable context window is worth zero.

**[INFERRED]** Note this kill criterion is unusual in that it can fire in favour of the *cheaper* option. That is the correct outcome: a stage exists to deliver value, not to be completed.

---

## 12. Stage J — Efficient inference: quantisation, checkpointing, deployment

**Purpose:** make the model *affordable to serve*. This is the stage with the highest leverage per dollar in the entire roadmap, because it converts a fixed cost (training) into a recurring cost (inference) that scales with usage.

### 12.1 Why this stage is out of order

**[INFERRED]** Stage J appears late in the sequence, but **it gates the product, not the model**. The model can be excellent and the product still unusable if each turn costs too much or takes too long. **[INFERRED]** The dependency is not "J needs K"; it is "J must be *designed* in parallel with B and I, and *implemented* before the first user-visible deployment."

**[KNOWN FACT]** The baseline cost model: at decode, generation is **bandwidth-bound** — every token requires reading the whole weight matrix once. So:

```
tokens/second ≈ memory_bandwidth ÷ weight_bytes × efficiency
```

**[ESTIMATE]** With A100's **2,039 GB/s** on-device memory bandwidth and a **50% achieved decode efficiency** (i.e. an effective 1,019.5 GB/s), per `compute-feasibility.md` §6.1:

| Config | Precision | Weight bytes | tok/s (b=1) |
|---|---|---|---|
| B (1.149B) | bf16 | 2.30 GB | 444 |
| B | int8 | 1.15 GB | 887 |
| B | int4 | 0.57 GB | 1,774 |
| C (7.248B) | bf16 | 14.50 GB | 70 |
| C | int8 | 7.25 GB | 141 |
| C | int4 | 3.62 GB | 281 |

**[OBSERVED] The bandwidth figure was corrected on 2026-10-22.** The table previously read *"With A100's 1,555 GB/s (2,039 GB/s theoretical peak) and 50% achieved efficiency"*, which is self-contradictory — 1,555 GB/s is the A100's PCIe Gen4 x16 bidirectional link figure, not its on-device HBM bandwidth, and it is not 50% of 2,039. **The arithmetic in the table was already correct** (it used 2,039 × 0.50 = 1,019.5 GB/s throughout), so only the stated input was wrong.

**[INFERRED]** 4-bit gives a **4× throughput** and a **4× VRAM** reduction. **[INFERRED]** But see §12.4 — for *code*, the quality cost of 4-bit is real, and int8 is often the better operating point.

### 12.2 The KV cache, which dominates at long context

**[KNOWN FACT]** KV bytes = `2 × layers × kv_dim × context × 2 bytes` under GQA (bf16).

**[OBSERVED]** Computed from the project's own parameter counts:

| Config | L | kv_dim | Q | KV bytes @ b=1 | @ b=8 |
|---|---|---|---|---|---|
| B | 24 | 512 | 32,768 | 1.50 GiB | 12.0 GiB |
| B | 24 | 512 | 131,072 | 6.00 GiB | 48.0 GiB |
| C | 32 | 1024 | 32,768 | 4.00 GiB | 32.0 GiB |
| C | 32 | 1024 | 131,072 | 16.00 GiB | 128.0 GiB |

**[INFERRED]** **This is the number that actually constrains deployment.** At Config C, 131k context and batch 8, the KV cache alone is 128 GiB — more than an 80 GB A100 holds. **[INFERRED]** And the KV cache is *not* reduced by weight quantisation. This is why long-context serving is an engineering problem (paging, prefix caching, KV quantisation, attention sinks) rather than a model problem.

**[INFERRED]** GQA is doing heavy lifting here: Config B has 16 query heads but only 4 KV heads, so the KV cache is 4× smaller than MHA would give. **[INFERRED]** This is a Stage B design decision that pays off here, and it is one of the strongest arguments for the Config B/C GQA ratios chosen in §1.4.

### 12.3 Quantisation: the methods and the choice

**[KNOWN FACT]** The two dominant post-training weight-quantisation methods are **AWQ** (MLSys 2024 best paper) and **GPTQ**, both producing 4-bit weights with group-wise scales, both with published speedups and quality results. **[KNOWN FACT]** BitsAndBytes supports `bnb_4bit_compute_dtype=torch.bfloat16` — i.e. 4-bit *storage* with bf16 *compute*, which preserves numerical stability at modest throughput cost.

**[INFERRED] The choice for a coding model:**

| | 4-bit (AWQ/GPTQ) | 8-bit (int8) | bf16 |
|---|---|---|---|
| Weight memory | 0.57 GB (B) | 1.15 GB | 2.30 GB |
| Throughput | 4× | 2× | 1× |
| **Code quality** | **[UNKNOWN]** — must be measured | **[UNKNOWN]** — must be measured | baseline |
| Fits 8 GB card | yes | yes | no (B) |

**[INFERRED]** The honest position: **quantisation sensitivity for code is higher than for prose**, because code has exact-match structure (identifiers, indentation, exact strings, exact numeric literals) where small perturbations produce *large* semantic changes, whereas prose degrades gracefully. **[INFERRED]** This is a hypothesis, not a finding, and it is exactly the kind of thing Stage K's apparatus exists to settle. **[UNKNOWN]** No public figure was found for the quality gap between 4-bit and bf16 on code-specific benchmarks, so this document does not assert one.

**[INFERRED]** Recommendation: **ship int8 as the default and treat 4-bit as an opt-in.** The 2× memory saving from int8 is already enough to fit Config B comfortably, and int8 quantisation of weights is far less likely to perturb exact-match code. **[INFERRED]** This is a cheap-first decision: int8 costs one calibration pass and no architecture work.

### 12.4 Other inference levers, in order of cost

**[INFERRED]** Ranked by cost-to-benefit:

1. **Prefix caching** — the system prompt, tool schemas and project context are a stable prefix across a session. **[INFERRED]** Free in engineering terms, large in latency terms for multi-turn coding.
2. **Continuous batching** — serve many concurrent requests on one set of weights. Standard in vLLM/TGI-class serving stacks.
3. **PagedAttention / KV paging** — avoid the fragmentation that makes KV-cache memory unusable. **[KNOWN FACT]** This is the standard technique in modern serving engines (vLLM's core contribution).
4. **KV-cache quantisation** (fp8/int8 KV) — halves or quarters the cache. **[INFERRED]** This is the lever that makes long context affordable at batch > 1.
5. **Speculative decoding** — a small draft model proposes tokens, the large model verifies in a batched forward pass. **[INFERRED]** For code, the natural draft model is a *completion* model trained on the same corpus — the FIM objective makes this natural.
6. **Weight quantisation** — the table above.
7. **Attention sinks / sliding-window hybrid attention** — for long context. **[INFERRED]** Cheap to implement, and it is also a *training* decision if adopted at Stage B.

### 12.5 Checkpointing and deployment engineering

**[KNOWN FACT]** `architecture.md` §5.1–5.4 defines the `ModelAdapter` interface, and ADR-009 records the self-hosted model as a **new adapter**, not a migration. **[INFERRED]** The deployment consequence: the self-hosted model must expose the same `ProviderRequest`/`ProviderResponse` shape as every other adapter, and the interface-spec's five-level model-resolution chain must resolve to it without special-casing.

**[INFERRED] The four hard deployment requirements:**

1. **Byte-identical normalised output across ten runs on two machines** — **[KNOWN FACT]** `implementation-plan.md` §6 milestone M2. **[INFERRED]** For a self-hosted model, M2 is *harder*, not easier: a hosted API is deterministic by construction, whereas a local model depends on the kernel, the batching, the quantisation and the sampling seed all being pinned. **A self-hosted model that cannot satisfy M2 should not be wired into the product at all.**
2. **Determinism control.** Fixed seed, greedy decoding, pinned kernel, fixed batching. **[INFERRED]** Continuous batching breaks this unless request ordering is pinned — a real tension with lever 2 in §12.4 that must be resolved deliberately.
3. **Graceful degradation.** When the self-hosted model fails, times out or is unhealthy, the adapter must fall back. **[INFERRED]** This is a *harness* responsibility (lever (e)) and must be built, because a product whose only model is a 1.1B local model will fail regularly.
4. **Cost accounting.** **[KNOWN FACT]** `architecture.md` §5.x requires the self-hosted adapter to report `costBasis: "unknown"` and fall back to a token-denominated budget when true cost is not attributable. **[INFERRED]** For self-hosted inference the true cost *is* attributable (GPU-hours × price), and the adapter should report it as such — but only after Stage J has measured it.

### 12.6 Measurable exit criteria

**J1.** **Throughput target met:** ≥ 40 tok/s at b=1 and ≥ 15 tok/s at b=8 for Config B in the target precision, on the target hardware. **[INFERRED]** 15 tok/s at batch 8 is the practical floor for a usable interactive coding agent at a ~30-round task.

**J2.** **Quantisation quality gate.** The int8 and 4-bit models are each evaluated against the bf16 baseline with the paired protocol, and the degradation is reported per metric. **[INFERRED]** **Proposed acceptance: 4-bit is rejected if it loses > 2.0 pp on the `exact-match`/`correctness` metrics of F2/F3, or if the G1–G16 hard gates regress.** **[INFERRED]** A paired CI excluding zero on a *degradation* is the correct test.

**J3.** **Memory fit:** the target context length × target batch fits in the target GPU with ≥ 20% headroom for activations and fragmentation.

**J4.** **M2 satisfied on the self-hosted path** — byte-identical normalised output across ten runs on two machines, including across a quantisation change (i.e. the quantised deployment is itself reproducible).

**J5.** **Cost per successful task is measured.** **[INFERRED]** This is the metric that should decide everything downstream. Not $/Mtok — **$ per successfully completed agent task**, including the harness's token spend, the retries and the failed turns. **[INFERRED]** A cheap model that fails 80% of tasks is more expensive per success than an expensive one that succeeds 60% of the time.

### 12.7 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Do the harness-side efficiency work before the quantisation work.** **[INFERRED]** In order: prefix caching → continuous batching → KV paging → int8 weights. **[INFERRED]** All four are engineering in a mature serving stack; none of them require touching the model. Quantisation is last because it is the only one that *degrades quality*, and the only one that requires a calibration dataset and a careful evaluation.

**[SPECULATIVE TARGET]** **Second alternative: serve the model at a smaller config.** **[INFERRED]** Serving Config A (100M) as the draft model for speculative decoding is cheaper than any quantisation saving on Config B.

### 12.8 Kill criterion

**Kill the 4-bit path if J2 fails at the proposed threshold** (4-bit loses > 2.0 pp on correctness/exact-match, or any G-gate regresses). **[INFERRED]** Do not ship a quality regression to save memory that int8 alone can save.

**[INFERRED]** Kill the *self-hosted inference* track entirely if, after Stage J, the measured **$ per successful task** of the self-hosted model is **worse** than the cost of the provider path *including its failure rate*, AND the provider path is legally permitted for our use. **[INFERRED]** This kill criterion is uncomfortable to write and important to write: the honest result of this project may be that the self-hosted model is a *capability* asset rather than a *cost* asset, and that is a perfectly acceptable outcome — but only if it is established by measurement rather than by assumption.

---

## 13. Stage K — Systematic evaluation, failure analysis and targeted retraining

**Purpose:** close the loop. This is the stage that makes every other stage falsifiable, and it is the stage that is most often under-built.

### 13.1 The dependency that makes this the last stage and the first stage

**[KNOWN FACT]** `benchmark-and-evaluation-plan.md` defines 16 dimensions / 62 metrics (54 automatic, 3 hybrid, 5 human), nine task families F1–F9, staged suite sizes S0 = 75 / S1 = 220 / S2 = 540 / S3 = 920, hard gates G1–G16, McNemar exact + paired bootstrap, Holm-Bonferroni, and a material-improvement bar (net ≥ 5.0 pp, 95% CI excluding 0, not concentrated in fewer than 5 tasks, DEV–TEST gap not widening).

**[INFERRED]** That apparatus is not a final-stage deliverable. It is a **prerequisite** for every stage that claims an improvement, and it must exist *before* Stage C, because Stage C's exit criterion — "demonstrably learns" — is a measurement claim. So Stage K's apparatus is built early (Stage C onward) and Stage K itself is the *loop* that runs continuously: evaluate → attribute failures → retrain on the attributed failure classes → re-evaluate. **Stage K is a cycle, not a phase**, and its exit criteria are about the *loop closing*, not about a final number.

### 13.2 Dataset properties

| Property | Value |
|---|---|
| **Data** | The evaluation suite itself (held-out), plus the failure corpus produced by each stage |
| **Size** | **[KNOWN FACT]** S0 = 75 (smoke) / S1 = 220 (iteration) / S2 = 540 (release candidate) / S3 = 920 (release) |
| **Licence class** | Mixed — third-party benchmark licences for the public components, ours for the self-authored components. **[KNOWN FACT]** `licensing-and-provenance-review.md` §9 records MBPP/HumanEval as **held-out only**, i.e. never in training |
| **Contamination risk** | **[KNOWN FACT]** The seven controls (age cutoff, not-in-index, fork selection, rewording, post-cutoff construction, held-out-by-construction, negative control) and their documented honest limits. **[INFERRED]** The negative control is the most important: if the *model* is contaminated, a task it should fail will pass, and only the negative control reveals that |

### 13.3 Compute, memory, storage

**[KNOWN FACT]** `compute-feasibility.md` §8.3, as corrected on 2026-10-22: at a **matched workload** of 15,000 agent runs (500 tasks × 3 seeds × 10 variants), a self-hosted sweep costs **$6,155** against **$125,250** via API — a **20.3× advantage**, not the 2,400× this document previously claimed. **[OBSERVED]** The earlier 2,400× figure compared *one* 500-run self-hosted sweep against a *15,000*-run API sweep — one run against thirty — and used a flat 10k-token prompt estimate where the document's own §8.1 growth model gives 4,075,000 prompt tokens per task. **[INFERRED]** The corrected 20.3× advantage is smaller but is the number a reader should plan against. **[INFERRED]** It is still the entire economic argument for training our own model, and it is *larger in absolute dollars* than the figure it replaces: the old claim implied the API side was $125,250 and the self-hosted side ~$51; the truth is $125,250 against $6,155 — the self-hosted side is 120× more expensive than previously stated, and the comparison is now honest.

**[ESTIMATE] The self-evaluation sweep at R2**, using the upstream §8.1 growth model (50 rounds, prompt *i* = 8,000 + 3,000×(*i*−1), i.e. **4,075,000 prompt tokens per task**):

| Suite | Tasks | Prompt tokens | Prefill FLOPs (2×N) | Total billed GPU-h | Cost |
|---|---|---|---|---|---|
| **S1** | 220 | 8.965×10⁸ | 2.060×10¹⁸ | 4.59 | **$12.80** |
| **S2** | 540 | 2.200×10⁹ | 5.056×10¹⁸ | 11.26 | **$31.41** |
| **S3** | 920 | 3.749×10⁹ | 8.618×10¹⁸ | 19.18 | **$53.52** |

**[ESTIMATE]** These are **prefill-only** figures at Config B; decode is additional and is not in the table. **[OBSERVED] The table replaces a previous version** that used a flat "30 rounds × 4,000 tokens" estimate and reported "~$13.5 GPU-h ≈ $38" for S1 — which understated the prompt-token count by ~34× and then overstated the GPU-hours by 8× via the fleet error. The corrected S1 prefill cost is **$12.80**.

**[ESTIMATE] Storage:** the failure corpus is the growing artefact. At 10,000 archived failures × ~50 KB = **500 MB** per stage; across six stages ≈ **3 GB**. Plus the evaluation harness code and the frozen suite versions: **~200 MB**.

**[INFERRED]** The failure corpus is *the* asset that makes the loop work, and it is cheap. **[INFERRED]** The expensive part is not the compute; it is the **human attention** required to read and attribute failures. That is a staffing constraint, not a budget constraint, and it should be planned as such.

### 13.4 Engineering complexity

**High, but mostly *reused*.** **[KNOWN FACT]** The evaluation plan already specifies the split protocol, the six leakage-prevention rules, the statistical method and the claim vocabulary. **[INFERRED]** The genuinely new engineering is:

1. **Failure taxonomy with stable IDs** — every failure is classified into a fixed taxonomy, and the taxonomy is versioned. **[INFERRED]** Without stable IDs, the failure counts are not comparable across stages and the loop does not close.
2. **Automated attribution** — mapping a failure to a lever (a)–(f). **[INFERRED]** This is the mechanically hardest part: a failure has to be attributed to weights/data/recipe/prompt/harness/evaluation, and the honest answer is often "harness" — which requires the harness to be instrumented so that the harness's own failures are visible.
3. **A retraining-set builder** that turns an attributed failure class into a training example. **[INFERRED]** This is the actual closing of the loop, and it is where most "evaluation frameworks" quietly stop.
4. **The self-benchmarking trap guard.** **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §5.4 warns about the trap of tuning on the same suite used to report, and specifically calls out the *aggregated* case. **[INFERRED]** The mitigation is DEV–TEST separation plus the rule that the retraining set and the reporting set never share a task.

### 13.5 Measurable exit criteria

**K1.** **The loop has closed at least once end-to-end.** **[INFERRED]** A named failure class from Stage C/D/F/G, attributed to a lever, turned into a training set, retrained, and re-evaluated on the **claim set** with a **paired** improvement whose 95% CI excludes zero. **[INFERRED]** This is the criterion that distinguishes a real evaluation programme from a benchmark report. **[OBSERVED]** The re-evaluation is on the claim set rather than on DEV or TEST-A, and this is the structural point of the whole programme: **the claim set is the only partition that is simultaneously held out from tuning and large enough to carry a claim**, and it only becomes large enough by accumulating retired LIVE slices across releases. A failure class discovered in one cycle is therefore *not* re-measurable on a fresh claim set until enough releases have passed — which is why the loop's cadence is set by the suite's growth, not by the speed of the training loop.

**K2.** **Failure attribution is reported for every failure class**, with the distribution across levers (a)–(f) published. **[INFERRED]** If more than ~50% of failures attribute to lever (e) (the harness), then the model's quality is not the binding constraint, and no further model training is justified. **[INFERRED]** **This is the single most decision-relevant number in the entire roadmap**, and it is exactly the kind of finding that would justify stopping model development early.

**K3.** **No gate regression.** All of G1–G16 pass at S2 after every stage that touched the model.

**K4.** **Negative results are archived.** **[KNOWN FACT]** `benchmark-and-evaluation-plan.md` §11.4 criterion (v) requires at least one unsuccessful comparison to be reported, on the grounds that *"a measurement apparatus that never records a failure is not measuring."*

**K5.** **The DEV–TEST gap is not widening.** A widening gap is the signature of overfitting to the evaluation suite and is a hard fail regardless of the headline number.

**K6.** **Claim discipline holds.** Every published capability claim maps to a specific comparison with a specific interval and a specific claim from the permitted vocabulary in §11.5 of the evaluation plan.

### 13.6 Cheap alternative to try first

**[SPECULATIVE TARGET]** **Run the evaluation suite before the model exists.** **[INFERRED]** Build the S0/S1 suite and run it against the *provider* adapter to (a) validate the harness end-to-end, (b) establish the reference numbers, and (c) discover which task families are ambiguous or unsound. **[INFERRED]** This costs nothing beyond engineering time and it means the evaluation apparatus is debugged before there is a model to debug it on.

**[INFERRED]** The important caveat: the provider's numbers are a **reference point for the harness**, not a target for our model, and the licence constraints of §D.4 mean nothing from the provider's outputs may be used as training data. The provider's scores also are not ours to report as our capability — they measure the provider's model under our harness, which is a *harness* measurement and must be labelled as such.

### 13.7 Kill criterion

**Kill *further model training* — not the evaluation programme — if K2 shows that > 50% of failures attribute to lever (e).** **[INFERRED]** In that case the correct action is to move effort into the harness: better tool design, better context management, better error handling, better prompt structure. **[INFERRED]** This is the roadmap's central empirical claim, and Stage K is the stage that tests it. If it is true, the most valuable thing this project produces is a well-engineered harness plus a modest model, not a large model.

**[INFERRED]** A second kill criterion: **if two consecutive targeted retrains each produce a paired improvement whose CI includes zero, stop retraining and change the hypothesis.** Continuing to retrain without a working causal story is how a project burns its budget on noise.

---

## 14. The stage-dependency map

### 14.1 What blocks what

```
                    ┌──────────────────────────────┐
                    │  A  Tokenizer                │
                    │  (no dependencies)            │
                    └───────────────┬──────────────┘
                                    │ vocab size fixes every downstream shape
                    ┌───────────────▼──────────────┐
                    │  B  Architecture + init       │
                    │  needs A (vocab)              │
                    └───────────────┬──────────────┘
                                    │ param count fixes compute & memory
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐        ┌─────────▼─────────┐       ┌────────▼─────────┐
│ D  Data        │        │ C  Pretrain       │       │ J  Inference     │
│ (needs A for   │        │ baseline          │       │ design           │
│  the chunker)  │        │ needs B           │       │ needs B,C        │
└───────┬────────┘        └─────────┬─────────┘       └──────────────────┘
        │                           │
        │   ┌───────────────────────┤
        │   │                       │
┌───────▼───▼────────┐    ┌─────────▼─────────┐
│ E  Scaling         │    │ F  Instruction    │
│ needs C (learns)   │    │ tuning            │
│ and D (data)       │    │ needs C, D        │
└───────┬────────────┘    └─────────┬─────────┘
        │                           │
        │                   ┌───────▼────────┐
        │                   │ G  Tool use /  │
        │                   │ agentic        │
        │                   │ needs F        │
        │                   └───────┬────────┘
        │                           │
        │                   ┌───────▼────────┐
        │                   │ H  Preference / │
        │                   │ RL              │
        │                   │ needs G (oracle │
        │                   │  exists)        │
        │                   └───────┬────────┘
        │                           │
        │   ┌───────────────────────┤
        │   │                       │
┌───────▼───▼──────┐      ┌────────▼────────┐
│ I  Long context  │      │ K  Evaluation    │
│ needs E (scaled) │─────▶│ (needs C from    │
│ needs J (serving)│      │  the start)      │
└──────────────────┘      └────────┬────────┘
                                    │ attribution feeds back into D/F/G
                                    ▼
                              (loop back to A–I)
```

### 14.2 The longest chain

**[INFERRED]** The longest dependency chain — and therefore the critical path — is:

```
A → B → C → F → G → H
```

**[INFERRED]** Six stages, of which **four are compute-expensive or slow**: B (architecture), C (pretraining baseline, days), F (instruction tuning: data engineering then compute), G (agentic training: data generation then compute), H (preference/RL, expensive).

**[INFERRED]** The second-longest chain is `A → B → C → D → E → I → J`, but each of those is *stage-parallel* with F and G in the sense that the data and training pipelines can be developed concurrently. **The critical path is therefore not the compute-heavy path — it is the path with the most *sequential engineering*: the trainer, then the SFT data, then the trajectory generation, then the preference stage. Engineering time, not GPU-hours, dominates the critical path**, and that is the single most important scheduling fact in this document.

**[INFERRED]** Two dependency claims that are easy to get wrong:

1. **Stage K does not block the others** — it is *used* by them. Stage C's "demonstrably learns" criterion requires the evaluation apparatus, so K's apparatus is a prerequisite for C, but K's *loop* runs throughout. Placing K last in the narrative is a presentation choice, not a scheduling one.
2. **Stage D does not block Stage C** — but only barely. **[INFERRED]** A pretraining baseline can run on a small, deliberately-limited corpus to prove the trainer works. That is what Stage C is *for*: not a good model, but proof the training loop learns. If Stage C required the full Stage D corpus, the critical path would become `A → D → B → C`, which is worse, because the data pipeline is the longest-lead item in the project (`compute-feasibility.md` §9: *"data preparation is often the longest pole"*).

### 14.3 Which stages can be parallelised

**[INFERRED]** With a team of four (the `implementation-plan.md` §9.1 assumption):

| Parallel track | Stages | Note |
|---|---|---|
| **Track 1 — model** | A → B → C → F → G → H | The critical path. One or two people. |
| **Track 2 — data** | D, continuing into F's SFT mix and G's task set | Independent of B and C once the tokenizer is fixed. Two people. |
| **Track 3 — harness & serving** | J (design), the `ModelAdapter` work from `architecture.md`, and the evaluation harness from Stage K | Independent of the model itself. This is where lever (e) lives, and it is where the largest early capability gains are available. |
| **Track 4 — evaluation** | K's apparatus | Needed from Stage C onward; overlaps Track 3. |

**[INFERRED]** **[SPECULATIVE TARGET] This parallelism is the project's most valuable structural property.** Because levers (d), (e) and (f) are available long before lever (a), a team of four can build and measure a genuinely useful coding agent using the provider adapter (via the `ModelAdapter` abstraction, never presented as our own model intelligence) *while* the model track proceeds. **[INFERRED]** The product therefore has value long before the model exists — and if the model track is killed by a kill criterion, the project still has a working product, which is a much better outcome than a working model and no product.

---

## 15. The schedule, in stages

### 15.1 Why this document has no calendar dates

**[KNOWN FACT]** `compute-feasibility.md` §9 states the binding constraint plainly: *"Iteration count is the hidden schedule killer."* At R3-optimal (68 d/run) a team of two gets **roughly 4 runs in a year**; at R2 (3 d/run) a team gets **~60 experiments/year**. **[KNOWN FACT]** The same document's risk #2 records that *"wall-clock, not dollars, is the binding constraint. A 68-day run is one shot; you cannot debug it."*

**[OBSERVED] A correction to that upstream sentence.** `compute-feasibility.md` §9's own numbers give **365 / 3.1 d ≈ 117 experiments/year** at R2, not ~60 — the upstream "~60" is a rounding-down of the ladder rung's *3-day* figure interpreted with a team-throughput assumption of ~50% utilisation on a shared allocation rather than 100% on one 8×A100. **[INFERRED]** Both readings support the same conclusion and the same direction; the difference is a factor of two in a quantity that is already the worst number in the plan. **[INFERRED]** This roadmap quotes **~119 (ladder R2) and ~152 (Config B)** in §15.4 and §15.3 because those are computed as `365 / wall-clock` on a dedicated allocation, which is the assumption this document's own budgets use. **Where the two documents disagree on this number, the discrepancy is the utilisation assumption, and it is stated rather than averaged.**

**[INFERRED]** Therefore this roadmap is expressed in **stages and gates**, not dates. A date-based plan for a project whose principal resource is a *sequence of experiments* would convert an uncertainty into false precision: if the tokenizer or the trainer takes three attempts instead of one, every downstream date silently invalidates, and a reader of the plan can no longer tell which dates are load-bearing and which are wishful.

**[INFERRED]** The substitute for a date is a **gate**. A stage is entered when its predecessor's exit criteria pass, and left when its own pass. Gates are checkable; dates are not. **[INFERRED]** The schedule's only *time* content is the wall-clock duration of a single run, because that is the one quantity that is a physical fact rather than a project estimate.

### 15.2 The schedule as a gate sequence

| Stage | Entry gate | Exit gate (short form) | Wall-clock of the run itself | Iteration headroom |
|---|---|---|---|---|
| **A — Tokenizer** | none (start here) | A1–A5: measured compression on code vs prose (A2) **and** tokens per content unit on code (A2b); round-trip exactness; no split on identifiers; cost/token known | **Local, days.** Free. | Unlimited |
| **B — Architecture** | A's vocab fixed | B1–B6: parameter count matches `param_math.py` exactly; deterministic init given a seed; memory fits the target; loss curve matches a reference shape | **Local, hours.** Free. | Unlimited |
| **C — Pretrain baseline** | B's config exists; evaluation harness (Stage K's S0/S1) runs | C1–C5: **loss decreases monotonically**; the model predicts held-out tokens above chance; perplexity beats the uniform baseline by a wide margin; the run is reproducible from the seed | **Config B: 2.40 d** (30 B-token arm). Ladder R2: ~3.1 d. R0 local: 73–363 d (too slow to iterate — see §15.4) | **~152 runs/yr** (Config B) · ~119 (ladder R2) |
| **D — Data** | A's tokenizer exists (for the chunker) | D1–D7: corpus register complete; every candidate passes the five-item gate of `licensing-and-provenance-review.md` §9.1; decontamination report signed; no path to the reference product | **Local, weeks-to-months.** No GPU. | Unlimited (but the long pole) |
| **E — Scaling** | **C passes AND D passes AND the C-scale ablation shows the recipe scales** | E1–E4: loss at the larger scale is below the smaller scale's loss at equal tokens; no instability; the run completes without intervention | **Config B: 2.40 d. Config C: 70.6 d** (140 B-token arm). Ladder: R2 ~3.1 d, R3 ~68 d | Config B ~152/yr · Config C ~5/yr |
| **F — Instruction tuning** | C's model exists; D's corpus exists | F1–F6: instruction-following improves on a held-out set with the CI excluding zero; no regression on the pretraining eval; tool-call syntax valid at ≥ X% | **~0.3–1 d** at R2 | High |
| **G — Tool-use / agentic** | F's model exists; a verifier/oracle exists for the task class | G1–G7: **pilot gate** (≥20% of sampled trajectories end in oracle-verified success); multi-step completion on a real repo task; failure recovery demonstrated | **~1–2 d** at R2 (generation-dominated) | Medium |
| **H — Preference / RL** | **G's G4 passed** (rejection sampling produced a gain) AND a verifier passes the adversarial-resistance test (H1) | H1–H5: paired gain ≥ 3.0 pp with CI excluding zero; no gate regression; no reward hacking; a negative result archived | **DPO: ~0.1 d. RLVR: ~2–4 weeks** | Low |
| **I — Long context** | E has produced a model at the target scale | I1–I5: paired improvement at 32k over 8k; no positional collapse; kernel equivalence; truncation logged | **7.5 h – 54 h** at R2 (Q = 8k – 131k) | High (cheap) |
| **J — Efficient inference** | B and C (design); a model exists | J1–J5: throughput target; quantisation quality gate; memory fit; **M2 determinism on the self-hosted path**; **$ per successful task** measured | **Days of engineering** | High |
| **K — Evaluation loop** | **needed from Stage C onward** | K1–K6: the loop has closed once end-to-end; failure attribution published; no gate regression; negative results archived; DEV–TEST gap not widening | **Continuous** | — |

### 15.3 The two schedule paths, and the fork between them

**[INFERRED]** There are exactly two coherent ways to run this, and the choice is a *programme decision*.

**Path 1 — "Research track" (all stages A→K).** The model is the product. Stage E reaches R3, Stage H is attempted, Stage I goes to 131k. **[ESTIMATE]** Corrected per §0.2, `compute-feasibility.md` §12's Scenario B (R3 at 140B tokens) costs **~$332k central** — of which training is $73k — and takes **~68 days per run on 8×A100**, plus ~2 months of data prep, for ~5 months calendar to the first model. **[INFERRED]** The risk is not the money — it is that R3 gives ~4–5 experiments per year, so the *learning rate of the project itself* collapses to four or five chances to be right.

**Path 2 — "Product-first track" (harness + evaluation + R2 model).** **[INFERRED]** Build the harness (lever (e)), the evaluation apparatus (lever (f)) and the data pipeline (lever (b)) in full; train at R2 only; treat Stages E, H and the 131k end of Stage I as *optional*. **[ESTIMATE]** At Config B's 30 B-token arm, R2 costs **$1,285** per run corrected, **$2,570** with the ×2 failure multiplier, **$3,855** at ×3 — with **~152 runs/yr** of headroom (365 / 2.40 d). **[ESTIMATE]** On the *planning ladder's* nominal R2 rung (1.5 B at 30 B tokens) the same figures are **$1,677 / $3,354 / $5,031** and ~119 runs/yr.

**[INFERRED] This roadmap recommends Path 2, and states why in numbers.** The difference in *training* spend is roughly **29×** on the Config basis ($1,285 vs $37,808 per run; $2,570 vs $75,616 with ×2), or **22×** on the ladder basis ($1,677 vs $36,514). The difference in *experiments* is roughly **29×** on the Config basis (152/yr vs 5.2/yr) or **22×** on the ladder basis (117/yr vs 5.4/yr). **[OBSERVED]** An earlier draft of this paragraph quoted **38×** for the experiment ratio; that figure mixed the two bases — it divided Config B's 152 runs/yr by the *ladder's* R3 figure of ~4/yr. **[INFERRED]** The corrected ratio is the one computed above, and the reason it is smaller than 38× is that **Config C's 70.6-day run is slightly faster than the ladder's 68.16-day nominal R3 run** once each is costed at its own parameter count — a difference in the *same* direction as every other Config-vs-ladder comparison in this document. **[UNKNOWN]** The expected *capability* difference is **not predictable**: no public figure predicts the gap between a 1.1B and a 7B code model on our own task suite, so this document does not assert one. The *parameter* ratio is **6.3×** on the Config basis (7,248,019,456 / 1,149,343,744) and **4.7×** on the ladder basis (7 B / 1.5 B); the *cost* ratio is 29× and 22× respectively. **[INFERRED]** The honest statement: *we do not know what a 6.3× larger model buys in capability, and we would have a ~29× worse experimental process with which to find out.* Given that, Path 2 is the better bet **even if the 6.3× turns out to matter a great deal**, because Path 2's model can always be scaled up later, whereas Path 1's five-experiments-per-year process cannot be fixed after the fact.

**[INFERRED]** A second, independent argument for Path 2: at corrected prices, **Path 1's entire training budget is roughly one year of Path 2's total compute** — and Path 2 spends that year producing a harness, an evaluation apparatus and a data pipeline that Path 1 would also need. **Path 2 is not the cheap path that skips the interesting work; it is the path that does the interesting work first.**

### 15.4 The iteration-count constraint, stated explicitly

**[KNOWN FACT]** From `compute-feasibility.md` §9 and §1.2's ladder:

| Rung | Params | Wall-clock per run | Runs/yr (2 people, one 8×A100) | Runs/yr (4 people, two allocations) |
|---|---|---|---|---|
| R0 (30M) | 30M | 73–363 d local | ~1 | ~2 |
| R1 (360M) | 360M | ~10.5 d | ~35 | ~70 |
| **R2 (1.5B)** | 1.5B | **~3.1 d** | **~119** | **~238** |
| **R2 — Config B** | 1.149B | **~2.40 d** (30 B-token arm) | **~152** | **~304** |
| R3 (7B) | 7B | ~68 d | ~4 | ~8 |
| **R3 — Config C** | 7.248B | **~70.6 d** (140 B-token arm) | **~5** | **~10** |
| R3-ext | 7B | ~four years | <1 | — |

**[INFERRED]** The constraint that matters: **model development is made of experiments, and R3 affords four or five of them a year.** One architecture ablation, one data-mixture comparison, one context-length extension and one deliberately failed run exhausts the annual budget at R3 before any iteration on the *results* is possible. **[INFERRED]** Every "only when measurements justify it" decision in this roadmap is really a statement about the experiment budget: Stage E is gated because R3 spends the entire budget on one data point. **[INFERRED]** And the *ladder* rungs and the *Config* rungs differ in the same direction, so the choice does not depend on which one is quoted: **R2 affords ~119–152 experiments a year and R3 affords ~4–5, on either basis.**

**[KNOWN FACT]** `compute-feasibility.md` §10's global stop rules apply throughout and are not restated. **[INFERRED]** One — *"if a run's loss curve deviates from a reference run by >5% in the first 1,000 steps, kill it immediately"* — is what makes the iteration budget usable, because it caps the cost of a failed experiment at ~1,000 steps rather than the full 68 days.

**[INFERRED] The local machine's role in the schedule** is separate from its role in the ladder: R0 at the local CPU is a 73–363 day job and is *not* on the critical path, as either a model or a learning test. **[KNOWN FACT]** `compute-feasibility.md` §11.1's local machine (Ryzen 7 5700U, 13.85 GiB RAM, 159.2 GB free disk) is *"sufficient for the data pipeline, tokenizer training, harness development, and R0 proof-of-learning"* — but the R0 proof-of-learning only fits if the token budget is cut to ~50–100M tokens, *"which makes it a pipeline test, not a learning test."* **[INFERRED]** So the local machine does Stages A, B, D and the harness/evaluation work for free, and Stage C's learning test must be bought — a short rented R0 run at ~50–100M tokens is hours, not days, and is enough to prove the trainer learns, which is all Stage C claims.

### 15.5 How this schedule maps onto the product's disclosure stages

**[OBSERVED]** `agent-and-model-boundary.md` §4's `S0`–`S3` are product states, not development stages, and this roadmap's `A`–`K` are development stages. **[INFERRED]** The mapping is not one-to-one, and stating it prevents a category error:

| Product stage | Reached when | Roadmap evidence required |
|---|---|---|
| **S0** `provider-only` | Immediately | none — this is the starting state |
| **S1** `own-model-behind-the-same-adapter` | Stages C, D, F, G, J have passed and the model satisfies `AMB-201`…`AMB-212` | `S1-1` adapter conformance; `S1-2` `AMB-304` provenance manifest; `S1-3` decontamination report; `S1-4` `AMB-233` lint clean; `S1-5` stage derivation test; **`S1-6` paired comparison** ← Stage K |
| **S2** `own-model-default` | The model is *not worse* than the provider model under a paired design, and passes the end-to-end agentic test | `S2-1` ← Stage K; **`S2-2` end-to-end agentic** ← Stage G; `S2-3` cost accounting; `S2-4` failure taxonomy comparison ← Stage K; `S2-5` configuration-only default switch; `S2-6` disclosure re-sign |
| **S3** `own-model-only` | No provider endpoint reachable; core suite passes on our model alone; every depended-on capability present or the degradation is documented and visible | `S3-1`…`S3-5` |

**[INFERRED]** **An honest note on S2.** `AMB-307` states that S2-1 is deliberately *"not worse"* rather than *"better"*, because S2 is a governance and independence property, not a quality claim. **[INFERRED]** That means **this roadmap does not need to beat a frontier model in order to be worth executing.** It needs to produce a model that is *adequate*, that is *ours*, and that is *honestly measured*. **[INFERRED]** The ambition of this document is therefore much smaller than it may appear, and that is deliberate.

---

## 16. What this roadmap cannot deliver, and on what timescale

**[INFERRED]** A roadmap that does not state its own limits is a sales document. This section states them as sharply as the evidence allows.

### 16.1 What it cannot deliver

**1. It cannot deliver frontier-level code capability. [INFERRED]** The recommended path trains a ~1.1B model. **[INFERRED]** Frontier code models are at least two orders of magnitude larger, trained on corpora orders of magnitude larger, with proprietary data collection, human annotation and RL infrastructure this project does not have and, under §D.4, cannot obtain from the reference provider. The gap is not marginal and this roadmap does not close it. **[KNOWN FACT]** The public reference points here (OLMo 3 at 7B, Tulu 3 at 8B, SmolLM2 at 360M) exist *because* a small number of well-resourced teams made them; reproducing that at 1.1B is a different proposition from matching it.

**2. It cannot deliver a model that beats the provider adapter on the task suite. [UNKNOWN]** No public figure predicts the capability gap between a 1.1B and a frontier model on our own task suite. **[INFERRED]** The roadmap does not promise parity; it promises *measurement* of the gap, which is different and achievable.

**3. It cannot deliver a general-purpose assistant. [INFERRED]** The scope is code. No mechanism in Stages A–K trains general instruction following, factual breadth, multilingual competence or conversational robustness beyond what the corpus and SFT mix incidentally provide. A general assistant needs a general web corpus, bringing licence, PII and contamination problems `licensing-and-provenance-review.md` has not resolved.

**4. It cannot deliver a production-grade guarantee of any kind. [INFERRED]** A 1.1B model with tool-calling will still produce invalid tool calls, wrong patches and overconfident wrong answers. **[OBSERVED]** `AMB-204` forbids the adapter from repairing malformed tool calls, so the product will *show* those failures rather than hide them — which means it will look worse than one that smooths over model errors, deliberately.

**5. It cannot deliver "own model" status without a provenance manifest. [OBSERVED]** `AMB-304` requires all four elements; `AMB-305` says a model failing any one is *"a fine-tune of someone else's model"*. **[INFERRED]** Fine-tuning a public base model puts us at `S1` with a named `model_base`, and the word "our model" may not be used unqualified.

**6. It cannot deliver a licence-clean corpus. [UNKNOWN]** Whether a sufficiently large, sufficiently permissive code corpus exists is **not determinable from the sources consulted**. **[KNOWN FACT]** The Stack v2 carries 619 languages on Software Heritage, requires an agreement with SoftwareHeritage and INRIA for bulk download, and requires that *"any use of all or part of the code gathered in The Stack v2 must abide by the terms of the original licenses, including attribution clauses when relevant"* (https://huggingface.co/datasets/bigcode/the-stack-v2, observed 2026-10-21). **[INFERRED]** That attribution burden is a per-file obligation at scale, and this project has designed no mechanism to discharge it. Until it does, The Stack v2's register status stays CANDIDATE, not PERMITTED.

**7. It cannot deliver a conclusion about the reference provider's behaviour. [OBSERVED]** Inspecting a coding agent does not reveal private model weights or training methods, and a collection of system prompts does not prove a behaviour exists in the running product. **[INFERRED]** No stage may cite such a collection as evidence for *why* something works. `prompt-pattern-analysis.md` is used as a *design-principle* source and explicitly not as a behavioural proof.

**8. It cannot deliver a model better than what the open community has already released. [INFERRED]** **[KNOWN FACT]** OLMo 3's 7B was trained on 5.93T tokens with a three-stage recipe at 65,536 context (arXiv 2512.13961, observed 2026-10-21); Tulu 3's 8B used 939K SFT examples, 271K DPO pairs and 20K RLVR prompts (arXiv 2411.15124, observed 2026-10-21). **[INFERRED]** The realistic outcome is *"a working, honestly-measured, licence-clean 1.1B code model plus a first-rate harness and evaluation apparatus"* — not a competitive frontier model.

### 16.2 On what timescale

**[INFERRED]** Three parts, and only the first is measurable:

- **Stage-gated, not dated.** See §15. The roadmap advances when gates pass. **[INFERRED]** A reader who needs dates should read `compute-feasibility.md` §9 and §12 for the *compute* path; this roadmap deliberately does not, because its subject is a sequence of experiments and the binding constraint is iteration count.

- **[KNOWN FACT] The compute path's arithmetic, as stated upstream:** R2 at the optimal token budget takes **~3 days on 8×A100**; R3 takes **~68 days**; data prep runs ~2 months. **[ESTIMATE] Corrected per §0.2, on the *ladder* basis (nominal 1.5B / 7B):** R2 optimal **$1,677** per run ($3,353 at ×2); R3 optimal **$36,514** per run ($73,028 at ×2). **[OBSERVED] Scenario figures, after the second correction (2026-10-22):** Scenario A model track **$4,884** Central (optimal tokens) / **$23,514** (600B tokens); Scenario B model track **$233,778** Central (140B tokens) / **$2,255,096** (3.5T tokens); Scenario C **$122,006,427**. **[OBSERVED] And the column every earlier version omitted — engineering labour:** `implementation-plan.md` §9.4's **165.8 person-weeks** is **$637,692** at $200k per engineer-year, which is **2.7× Scenario B's entire model track** and **130× Scenario A's**. The **project total** for Scenario B is therefore **$871,470**, and the **project calendar is the maximum of the two tracks — 39 weeks (the harness build), not the 68-day GPU run.** **[ESTIMATE] On the *Config* basis, at the arms §7.3 budgets (Config B = 1,149,343,744 params at 30 B tokens; Config C = 7,248,019,456 params at 140 B tokens):** R2-equivalent **$1,285** per run (**$2,570** at ×2, **$3,855** at ×3); R3-equivalent **$37,808** per run (**$75,616** at ×2). **[INFERRED]** The two bases differ by ~30% at R2 (ladder $1,677 vs Config $1,285) and ~4% at R3 (ladder $36,514 vs Config $37,808) — they are close enough that no conclusion in this roadmap turns on the choice, but they are *not* interchangeable and are never quoted without saying which is in use. **[INFERRED]** These are the only figures here that are not stage-gated, and they are recomputed from the upstream document's own inputs rather than restated.

- **[UNKNOWN] The wall-clock duration of the *engineering* stages.** **[INFERRED]** Compute is the part we can price. The engineering — data pipeline, trainer, trajectory recorder, oracle library, evaluation harness, serving stack — determines the critical path (§14.2), and **no public source gives a duration for building these for the first time.** A competent team of four has built comparable pieces before; this project has not, and the first-time cost of the data pipeline is the single largest schedule uncertainty in the roadmap. **[INFERRED]** The mitigation is structural, not an estimate: build Stage D and Stage K's apparatus first, because they are on the critical path and their output is reusable regardless of which model track is later chosen.

### 16.3 The one-sentence summary of this roadmap

**[INFERRED]** *Build the harness, the evaluation apparatus and the data pipeline first; train a small model that is honestly measured, licence-clean and adequate; and let the measurement — not the ambition — decide whether to scale.* **[INFERRED]** The most likely outcome of executing this roadmap well is that the harness turns out to matter more than the model, and that discovering this early is worth more than the model would have been.

---

## 17. The ledger of claims in this document

### 17.1 Tag counts

**[OBSERVED]** Counts of each tag as used in this document, excluding the tag-legend rows:

| Tag | Meaning | Count |
|---|---|---|
| `[KNOWN FACT]` | citable public source, URL + observation date inline | 96 |
| `[ESTIMATE]` | own derivation, arithmetic shown | 64 |
| `[SPECULATIVE TARGET]` | target or aspiration, never a forecast | 25 |
| `[OBSERVED]` | measured in this project's own evidence base, cited to file + section | 58 |
| `[INFERRED]` | conclusion from observed facts, inference stated | 281 |
| `[UNKNOWN]` | not determinable | 21 |

**[OBSERVED]** Counts measured on this file on 2026-10-22 by literal tag occurrence (`grep -o "\[TAG\]" llm-development-roadmap.md | wc -l`), and they are **whole-document** counts: they include the six legend cells of this table, the one tag cell in §1's legend row, and the `Tag` column cells of the per-stage property tables in §3.1 and §6.1. The counts rose from the 2026-10-21 measurement (92 / 54 / 25 / 33 / 259 / 19) because the 2026-10-22 repair added **[OBSERVED]**-tagged provenance corrections (the arithmetic-correction notes, the black-box-capture citations and the upstream-document corrections), each of which is an observation about the *project's own state* rather than an inference from it. **[INFERRED]** The rise in `[OBSERVED]` and `[ESTIMATE]` is the intended direction: a document that records its own corrections is more checkable than one that never had to be corrected.

**[INFERRED]** The ratio of `[INFERRED]` to `[KNOWN FACT]` is the honest description of this document: most of what it says about *our* project is inference from a small set of cited facts and from arithmetic we can check. **[INFERRED]** That is appropriate for a roadmap — a roadmap is a plan, and plans are inferences — but it means **the roadmap must be re-derived, not trusted, whenever a cited fact changes.**

### 17.2 The places that are `[UNKNOWN]`, and what would settle each

**[INFERRED]** Every `[UNKNOWN]` in this document, and the specific evidence that would resolve it:

| # | The unknown | What would settle it |
|---|---|---|
| U1 | The pass rate of an R2-class model on real repository tasks (the trajectory discard rate, Stage G) | A pilot run of 200 sampled tasks at the Stage G pilot gate. Directly measurable in ~2 GPU-days. |
| U2 | The capability gap between a 1.1B and a frontier model on our task suite | Running the S2 suite against both. This is the entire point of Stage K. |
| U3 | The 4-bit quantisation quality loss on code | The J2 paired evaluation, at S1 suite size. ~13 GPU-h. |
| U4 | The int8 quantisation quality loss on code | Same, and strictly cheaper. |
| U5 | Whether the 4-bit loss on code is larger than on prose | The same evaluation run, split by task family. |
| U6 | Whether a licence-clean corpus of sufficient size and quality exists | Completing `licensing-and-provenance-review.md` §9's five-item gate per candidate, plus designing an attribution-discharge mechanism for The Stack v2. |
| U7 | Whether the first-time engineering duration of the data pipeline and the evaluation harness | The engineering itself. No external source can answer it. |
| U8 | The wall-clock duration of Stages D, F, G's data work | Same. |
| U9 | Whether the reference product's system prompt collection corresponds to its actual runtime behaviour | **Not answerable by this project.** Requires provider-side disclosure. This document therefore never relies on it. |
| U10 | Whether the local machine can train any model above R0 | **[KNOWN FACT]** Already answered: no. `compute-feasibility.md` §11.1. Recorded here because the question recurs. |
| U11 | Whether a sufficiently permissive corpus exists with no per-file attribution burden | The corpus register's completion. |
| U12 | The public figure for 4-bit vs bf16 on code benchmarks | **[UNKNOWN]** No public figure was found. The document does not assert one. |
| U13 | Whether `agent-and-model-boundary.md`'s interface names would be inferable while unwritten | **[RESOLVED]** The document was written; §2.4 now cites `AMB-2xx`/`AMB-3xx` directly. |
| U14 | The exact behaviour of the attention kernel at Q ≥ 131,072 | The I3 kernel-equivalence test. |
| U15 | The reward-hacking resistance of a given verifier | The H1 near-miss test. Measurable at pilot scale. |
| U16 | The value of the 200 tok/param arm for *this* corpus (StarCoder2's regime) | Stage E's E3 measurement — the quality-gain-per-10×-tokens curve measured at the cheap end. A 7.7× cost and latency multiplier is being carried as an open risk until this curve exists. |
| U17 | The value of the A2b metric (tokens per task-relevant content unit) for any *published* tokenizer | There is no published figure and, on inspection, no obvious way to obtain one without each vendor's own tokenization of a common content-unit corpus. It is therefore a *selection* criterion among our own candidates, not a comparison against a published baseline — and that limitation is the honest form of the metric, not a gap to be filled. |
| U18 | Whether the licence-clean corpus search resolves before Stage B's budget is committed | The §9 five-item gate run per candidate, started at Stage A per `training-data-plan.md` §2.2a. Cheap to run; the *timing* is what makes it an early-warning rather than a late surprise. |

### 17.3 Standing rules for anyone editing this document

**[INFERRED]** These carry forward from the project's own review documents and are restated because this document will be edited:

1. **Never state a figure without a tag.** An untagged number is a bug.
2. **Never cite a prompt collection as behavioural proof.** It is a design-principle source only.
3. **Never cite inspecting a coding agent as evidence about weights or training methods.**
4. **Never state a legal conclusion from repository metadata alone.** `licensing-and-provenance-review.md` holds the licence reasoning; this document cites it and does not restate conclusions.
5. **Never claim a benchmark result that was not measured**, and never infer general superiority from an isolated example.
6. **The corpus must have no path to the reference product's outputs** (`licensing-and-provenance-review.md` §8.2). This is absolute and applies to Stages D, F, G and H.
7. **The existence of a provider adapter must never be represented as independent model intelligence.** When the provider adapter drives the product, the product says so — `agent-and-model-boundary.md` `AMB-303`'s false-claim column.

---

## 18. Closing

**[INFERRED]** This roadmap is deliberately unambitious at its headline and very ambitious in its instrumentation. It proposes training a model small enough to run on one machine, and building an evaluation and failure-attribution apparatus precise enough that the project's own claims about that model are checkable by someone who does not believe them. **[INFERRED]** The instrument is the more durable asset: the model will be superseded, and the apparatus that says honestly which lever moved will not.

**[INFERRED]** The single sentence to remember: **most early capability comes from levers (d), (e) and (f), all of which are available long before lever (a)** — and the roadmap's most valuable output may be the measurement that proves which lever was actually responsible.

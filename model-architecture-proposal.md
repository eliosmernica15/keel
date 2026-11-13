# Model Architecture Proposal — Independent Code LLM for the Clean-Room Coding Agent

**Document ID:** `model-architecture-proposal.md` · **Status:** proposal for review; no product source code is written here · **Date:** 2026-10-21
**Stage served:** Stage B (architecture) of `llm-development-roadmap.md`; enables Stage A (tokenizer), Stage I (long context), Stage J (efficient inference).
**Cross-references:** `compute-feasibility.md` (rungs, FLOPs, memory, prices) · `agent-and-model-boundary.md` (harness/model split; `AMB-*`) · `llm-development-roadmap.md` (stage map, Config B) · `benchmark-and-evaluation-plan.md` (metrics `M-D*-*`, gates `G*`) · `training-data-plan.md` (corpus, packing, manifest) · `licensing-and-provenance-review.md` (provenance, corpus register) · `interface-spec.md` (§4 tool interface, §12 adapter interface) · `architecture.md` (§3.2 tool-call path, §5 provider abstraction).

---

## 0. How to read this document

### 0.1 Tagging legend

**Overriding project rule: never state a fact you cannot source.** Every quantitative or behavioural claim carries an inline tag:

| Tag | Meaning | Obligation |
|---|---|---|
| `[KNOWN FACT]` | A citable source states this | URL or file path + observation date, inline |
| `[ESTIMATE]` | The author's own derivation | The arithmetic is shown and recomputable |
| `[SPECULATIVE]` | A target or aspiration, never a forecast | Never used to justify a spend |
| `[OBSERVED]` | Directly measured in this project's own evidence base | File + section, or the measurement and its result |
| `[INFERRED]` | A conclusion drawn from observed or known facts | The inference is stated in the sentence |
| `[UNKNOWN]` | Not determinable from the material examined | What would settle it is named |

Where a figure could not be found, this document writes **"no public figure found"** and does not substitute an estimate. Where a plausible-looking number appeared upstream but could not be traced to a source, it is carried as `[UNKNOWN]` with a note rather than silently promoted to fact.

Three project prohibitions are load-bearing throughout: **Do NOT** claim the system-prompt research collection proves a behaviour exists in the running product; **Do NOT** claim inspecting a coding agent reveals private model weights or training methods; **Do NOT** invent performance results, benchmark scores, or guarantee frontier-level performance. And the disclosure rule governing §11: **the product must use its own original code, assets and branding; the existence of a provider adapter must never be represented as independent model intelligence** — `AMB-001`, `AMB-304`.

### 0.2 What this document is and is not

A specification with arithmetic: a candidate architecture, its exact configuration, parameter budget, memory and compute consequences, and a measurement plan that could prove the choices wrong. It is **not** a training run or a report of one (`[UNKNOWN]` — no model has been trained); **not** a performance claim (`[UNKNOWN]` — no benchmark of this architecture exists, because the model does not exist); **not** a legal conclusion (`licensing-and-provenance-review.md` §12 OPEN-Q1…Q5 remain open); and not product source code.

### 0.3 The arithmetic engine

Every non-`[KNOWN FACT]`, non-`[OBSERVED]` number was produced by scripts in `research/spl/`, checked in so the arithmetic is reproducible: `model_arch_final.py` (parameter counts, ladder position, KV cache, training compute/memory, inference memory and throughput, local path, attention term, vocabulary sensitivity, depth/width, GQA, ablation budget, MoE and SSM accounting), `model_arch_final2.py` (corrections: activation memory over a full context window, per-layer MoE expert scaling, percentage divisors, K0 fallback, KV quantisation, speculative-decoding arithmetic), `model_arch_tokenizer.py` (sentinel inventory, embedding cost, tokenizer harness spec), and `param_math.py` as an independent cross-check. Two superseded scripts are retained; where they disagree, the final pair governs — their substantive difference was a 32-layer / 1.54 B / 49,152-vocabulary configuration (`K1`), **not** used here (§4.1).

**The re-verification pass, and what it changed.** `model_arch_verify.py` was written as an *independent* recomputation of every figure this document asserts, from the same constants, and it is checked in alongside the others. It re-derived the parameter count, the ladder positions, the KV-cache series, the activation-memory tiers, the local-laptop resident/decode figures, the embedding-share series and the GQA sensitivity without reusing the `model_arch_final*.py` code paths. It found **one systematic error and several consequent ones**, all now corrected in this revision:

1. **The Stage-1 and Stage-2 ablation budgets were computed from the dense term `6ND` alone, while the headline training-cost figures in §4.6 and §6.4 correctly include the attention term.** The two cost models disagree, and the ablation tables silently used the cheaper one. Every ablation arm is now costed on the **attention-inclusive** basis, consistent with §6.4, and both bases are printed side by side so the difference is visible rather than hidden. This roughly **quadruples** the measured plan (§13.3, §13.11) and is the single largest correction in this document.
2. **The "119 runs per year" figure was inherited from the roadmap's R2 row (3.1 d/run) and then attached to the wrong run length.** The recommendation's own runs are 3.13 d (8 K) or 6.99 d (32 K) once attention is counted, i.e. **117 or 52 runs per year**, not 119. The roadmap's 119 is a valid figure for a *different* run length and is now labelled as such (§1.2, §13.11).
3. **The Stage-1 arm cost was quoted per arm at $1.29, which omitted the attention term and counted the clip sweep as one arm.** Corrected to $18.88 per arm attention-inclusive, over 15 runs (13 arm rows; S1.12 is a 3-point sweep).
4. **Two embedding-share percentages were wrong** (24,576 and 131,072), and two serving-memory figures were stated in the wrong units (GB where GiB was meant, and vice versa) — see §5.5, §10.3, §10.6.

`[INFERRED]` The general lesson, and it is a property of this document rather than of one table: **a cost table computed with a different FLOPs model from the prose above it will always look plausible and will always be wrong.** The fix is not to be more careful in one place but to compute every table from one function, which is what `model_arch_verify.py` now does — §13.11's schedule and §4.6's headline come from the same `run_cost()` call.

### 0.4 Hardware constants

| Constant | Value | Tag |
|---|---|---|
| A100 80 GB bf16 peak / MFU / price | 312.0 TFLOPS / 0.40 / $2.79 per GPU-h | `[KNOWN FACT]` `compute-feasibility.md` §3.3, observed 2026-10-21 (MFU is `[ESTIMATE]`) |
| H100 80 GB bf16 peak / MFU / price | 989.5 TFLOPS / 0.45 / $3.99 per GPU-h | `[KNOWN FACT]` same source |
| A100 / L40S / H100 bandwidth | 2,039 / 864 / 3,350 GB/s | `[KNOWN FACT]` same source |
| Local RAM / CUDA / iGPU VRAM | 13.85 GiB / none / 2,147,483,648 B | `[OBSERVED]` `compute-feasibility.md` §11.1, observed 2026-10-21 |
| Local memory bandwidth | 8.48 GB/s | `[OBSERVED]` numpy triad, this machine, 2026-10-21 |
| Local FP32 GEMM | 1.72 × 10¹¹ FLOP/s (172 GFLOPS) | `[OBSERVED]` numpy matmul, same session |
| Decode efficiency factor | 0.50 of peak bandwidth | `[ESTIMATE]` `compute-feasibility.md` §6.1; planning use only |

**On the upstream cost column.** `compute-feasibility.md` §3.4 multiplies total GPU-hours by the 8-GPU hourly rate, inflating the cost column by exactly 8×; the correct relation is `cost = TOTAL GPU-hours × per-GPU price`, `wall-clock = TOTAL GPU-hours ÷ g`. `[KNOWN FACT]` `llm-development-roadmap.md` §0.2 documents the correction with two independent public anchors. `[INFERRED]` arithmetically confirmed: R3-optimal, 5.88 × 10²¹ FLOPs ÷ 1.248 × 10¹⁴ FLOP/s ÷ 3600 = 13,092 TOTAL A100 GPU-hours; × $2.79 = $36,525 against the document's $292,115 (8.00×). Its wall-clock column (68 days) is correct.

---

## 1. Decision summary

### 1.1 The recommendation in one table

| Field | Value | Tag |
|---|---|---|
| **Architecture family** | Decoder-only dense transformer: pre-norm, SwiGLU MLP, RMSNorm, GQA 4:1, QK-norm, tied embeddings | `[SPECULATIVE]` the choice; `[INFERRED]` lowest-risk family at this scale (§3) |
| **Parameter count** | **1,149,343,744** (1.149 B) | `[ESTIMATE]` §4.2; cross-checked against `param_math.py` |
| **Exact shape** | L = 24, d_model = 2,048, ffn = 5,632 (2.75 × d), h_q = 16, h_kv = 4, head_dim = 128, q_out = 2,048, kv_dim = 512, vocab = 32,768, tied | `[KNOWN FACT]` this is `llm-development-roadmap.md` §1.4 "Config B"; the count is `[ESTIMATE]` |
| **Context length** | **32,768 trained**; 8,192 reduced-cost fallback; 131,072 a measured-extrapolation option, not a plan | `[SPECULATIVE]`; constrained by `llm-development-roadmap.md` Stage I |
| **Tokenizer** | Byte-level BPE, **32,768** vocabulary, 19 reserved sentinels, uint16 ids, no `[UNK]` | `[KNOWN FACT]` `training-data-plan.md` §7.1 (32,000) and `llm-development-roadmap.md` §1.4 (32,768); this document adopts 32,768, discrepancy recorded as OPEN-A1 (§5.3) |
| **Precision** | bf16 compute, fp32 master weights and gradients, AdamW β = (0.9, 0.999), global clip 1.0, **no loss scaling** | `[ESTIMATE]` §8 |
| **Training framework** | Megatron-LM-style tensor/pipeline parallelism, ZeRO-1/2, FlashAttention-2, selective activation recomputation | `[KNOWN FACT]` arXiv:1909.08053, 1910.02054, 2307.08691, 2205.05198 — arXiv API, 2026-10-21 |
| **Inference runtime** | **llama.cpp** (local/edge), **vLLM** or **SGLang** (hosted) | `[KNOWN FACT]` llama.cpp README + `docs/build.md`, fetched 2026-10-21; vLLM arXiv:2309.06180, SGLang arXiv:2312.07104, verified 2026-10-21 |
| **Serving precision** | int8 default, 4-bit opt-in, gated | `[KNOWN FACT]` `llm-development-roadmap.md` Stage J; gate restated in §10.4 |
| **Training compute (20 tok/param)** | 22.99 B tokens; `6ND` = 1.585 × 10²⁰ FLOPs; **with the attention term at 32 K trained context**: 6.028 × 10²⁰ FLOPs, **1,342 A100 GPU-h**, 6.99 d on 8 × A100, **$3,743**. At an 8 K trained context: 600 GPU-h, 3.13 d, **$1,674**. The dense term alone is 353 GPU-h / $984 and is *not* the training cost at any context (§6.4) | `[ESTIMATE]` §4.6, §6.4 |
| **Fallback model (K0)** | **100,683,264** (0.101 B): L = 12, d = 768, ffn = 2,048, h_q = 12, h_kv = 4, head_dim = 64, same tokenizer | `[ESTIMATE]` §10.7 |
| **Quantization-aware training** | Not in the base plan | `[SPECULATIVE]`; revisit condition in §12.6 |

### 1.2 The three reasons that decided it

**Reason 1 — It is the configuration the project has already committed to, and the arithmetic confirms the commitment.** `llm-development-roadmap.md` §1.4 names Config B (24 L, d = 2,048, ffn = 5,632, h_q = 16, h_kv = 4, head_dim = 128, vocab = 32,768, tied) as "the roadmap's primary target". Recomputing its parameter count from first principles gives 1,149,343,744 against the roadmap's stated 1,149,337,600 — a difference of exactly 6,144, the QK-norm parameters the roadmap's counter omitted `[ESTIMATE]` §4.2. Re-deriving a different shape would contradict four parallel documents for no gain. This document recommends the shape, verifies it, and states where it diverges from the earlier `K1` figure of 1.54 B (§4.1).

**Reason 2 — At this scale the dominant risk is iteration count, not architectural novelty, and the dense family minimises it.** `llm-development-roadmap.md` §1.2 and `compute-feasibility.md` §2.1 both identify wall-clock per run, not GPU-dollar cost, as the binding constraint `[KNOWN FACT]`. At 20 tokens/parameter and a 32 K trained context the recommendation trains in **1,342 A100 GPU-hours — 6.99 days on 8 × A100**, i.e. roughly **52 such runs per year**; at an 8 K trained context, 600 GPU-hours and 3.13 days, i.e. **117 runs per year** `[ESTIMATE]` §4.6, §6.4. (The roadmap's `~119 runs/yr` figure is a *different* run length — its R2 row at 3.1 d/run — and is not this model's run length; see §0.3's correction note.) That run count determines how many architectural hypotheses the project can actually test (§13). Every alternative in §3 either adds failure modes (MoE: load balancing, expert collapse — arXiv:2101.03961, 2401.04088) or changes the model class in ways that invalidate the tooling, the evaluation baselines and the harness contract at once (SSM/recurrent: arXiv:2312.00752, 2403.19887, 2305.13048). At 1.15 B the family's one weakness — quadratic attention — does not bind: §6.4 puts the crossover above 32 K.

**Reason 3 — The tool-call contract can be made deterministic, but only with a dense autoregressive model trained with the format in the objective.** `AMB-204` requires the adapter MUST NOT repair malformed tool calls; `AMB-203` requires byte-identical schemas across arms. A deterministic contract — the harness rejects a malformed call, it never guesses — requires the output space be restricted to a grammar the harness can validate, and the model trained to emit that grammar. `[INFERRED]` Grammar-constrained decoding over a sentinel-delimited format gives a parse that is either valid-by-construction or a hard error: no fuzzy matcher, no repair step, no adapter-side rescue. llama.cpp exposes `grammar` / `json_schema` / `response_format` and a `--jinja` function-calling path `[KNOWN FACT]` llama.cpp README, 2026-10-21; XGrammar (arXiv:2411.15100) is the upstream constrained-decoding library. The alternative — JSON inside prose, parsed by a tolerant matcher — reintroduces exactly the ambiguity `AMB-204` forbids. §7 specifies the contract.

### 1.3 What is explicitly not claimed

- **No performance is claimed.** No benchmark of this architecture has been run, because the model does not exist. Every performance-shaped number here is a *budget* (tokens, FLOPs, hours, dollars) or an *arithmetic consequence*, never an expected score. `[UNKNOWN]` "What will this model score on HumanEval / MBPP / SWE-bench / the `M-D7-*` tool-use metrics" — **no public figure found**, and none will exist until the model is trained.
- **No frontier parity is promised.** `[SPECULATIVE]` The intent is a model competent at the agent's actual tasks, not one matching any commercial model.
- **No claim about any other product's internals.** `prompt-pattern-analysis.md` is treated strictly as evidence about the *shape of the task*, never about any model's weights, recipe or private behaviour. `[KNOWN FACT]` the project's own position, `licensing-and-provenance-review.md` §2.2: "a system prompt is a specification, not an asset".

---

## 2. Requirements the architecture must satisfy

Derived from what the agent must actually do, per `interface-spec.md`, `architecture.md`, `agent-and-model-boundary.md` and `prompt-pattern-analysis.md`.

| Req | Requirement, its source in the project's own specs, and the architectural consequence |
|---|---|
| **R1 — Tool-call fidelity** | `architecture.md` §3.2 — the model proposes a tool call, the harness evaluates permissions, the tool runs or a `<tool_use_error>` marker returns; `interface-spec.md` §4 — dual representation, an output-size ladder (~30,000 characters inline, then `<persisted-output>` references), a 5 GB hard kill; `AMB-204` makes the adapter's non-repair of malformed calls normative, `AMB-206` requires per-request token accounting. → A restricted output space plus the format in the training objective. Favours no one family — it rules out a separate tool head on a non-autoregressive backbone. **§7, §13.6** |
| **R2 — Long context for repository work, and *use* of it** | `architecture.md` §5 and `interface-spec.md` §4 assume substantial repository content per request; `agent-and-model-boundary.md` §7 defines the context boundary. → Two requirements often conflated. **Capacity** — the window must be large enough (at 32,768 tokens the KV cache is 1.611 GB `[ESTIMATE]` §4.5). **Utilisation** — the model must actually use the early and middle of the window: "Lost in the Middle" (arXiv:2307.03172) documents performance far below the end-of-context case for mid-window information; RULER (arXiv:2404.06654) and LongBench (arXiv:2308.14508) are the standard instruments. This favours attention over recurrent state — a recurrent model has a fixed-size state and therefore *compresses*, which suits a summary but not reproducing a function seen 20,000 tokens ago. Retrieval and summarisation are harness-side (`prompt-pattern-analysis.md` §7). A longer *trained* context is not automatically better — hence §13.4. **§6, §13.4** |
| **R3 — Structured output beyond tool calls** | `interface-spec.md` §4's output ladder implies plans, patches and diagnoses as well as calls; `architecture.md` §5.1–§5.4 define a schema-bearing structured response. → The same grammar mechanism as R1, holding on the failure path too — a truncated structure must fail detectably, not require a guess. `AMB-203` makes the schema byte-identical across arms, so the constraint is part of the experimental control. **§7, §13.6** |
| **R4 — Streaming, and the ability to stop** | Two separable capabilities. **Token-level streaming** is a runtime property, not an architectural one — llama.cpp's server exposes SSE streaming and vLLM/SGLang stream natively `[KNOWN FACT]` llama.cpp README, 2026-10-21. **Prefix stability** — the first *k* tokens the same regardless of what follows — makes partial output safe to display. → `[INFERRED]` prefix stability is a property of autoregressive decoding with a fixed sampling configuration; a non-autoregressive model emitting a whole sequence at once cannot satisfy it at all. Autoregressive, sampled with a recorded seed and fixed parameters. **§7.4, §9.4** |
| **R5 — Deterministic tool-argument parsing** | R1 restated as a *failure-path* requirement, and the one most often quietly violated. `AMB-204` forbids repair; `AMB-220`–`AMB-232` establish that an adapter cannot make a weaker model competent. → The check must be **total** — every possible output either parses or fails; a best-effort JSON parse with a fuzzy matcher is not. The grammar is applied by the *serving runtime*, not by the model: the model emits tokens, the runtime constrains the sampler, the harness parses; a violation yields `<tool_use_error>`. No component guesses what the model "meant". **§7.3, §7.5** |
| **R6 — A small model viable on a laptop, for the fallback path** | `compute-feasibility.md` §11.1 describes the local machine — Ryzen 7 5700U, 8c/16t, 13.85 GiB RAM, AMD iGPU with 2 GB VRAM, no CUDA, torch 2.14.1+cpu. → (i) the small model must *share the tokenizer* with the large one, or the harness needs two tokenisers and a translation layer and the small model saves nothing; (ii) it should be a scaled-down instance of the *same* architecture, so one training codebase, one runtime, one evaluation harness and one grammar machinery serve both. The recommended K0 is **100,683,264** parameters (L 12, d 768, ffn 2,048, h_q 12, h_kv 4, head_dim 64, vocab 32,768) `[ESTIMATE]` §10.7: at Q8_0 with an 8,192-token context it is **0.193 GiB resident**, and the *measured* 8.48 GB/s gives a 40.84 tok/s ceiling. It trains here in principle but not in practice — 20 tokens/parameter at even 10% of the measured 172 GFLOPS is **819 days**. **§10.7, §5.6** |
| **R7 — The harness must not require any provider capability** | `AMB-211` states this; `AMB-210` requires capability to be *declared*, not discovered. → The model must be usable *without* a provider-specific feature such as server-side tool calling, server-side grammar or server-side cache reuse. `[INFERRED]` a model that only works when the provider's server applies a grammar does not work on a different runtime, defeating self-hosting. §7.5 makes client-side grammar enforcement sufficient, server-side an optimisation. **§7.5, `AdapterCapabilities`** |

---

## 3. Candidate families compared

**A framing note applying throughout.** "Active parameters" differs between MoE and dense, and conflating them produces a false comparison. For dense, total = active. For MoE, total ≫ active, and per `compute-feasibility.md` §3.5 the training-FLOPs formula `C = 6ND` must use the **active** count while **memory** uses the **total** `[KNOWN FACT]`. All tables below respect that split.

**A — Decoder-only dense transformer (CHOSEN).** Pre-norm decoder-only; SwiGLU MLP (three matrices); RMSNorm (arXiv:1910.07467); RoPE (arXiv:2104.09864); GQA (arXiv:2305.13245); QK-norm; tied embeddings — all arXiv IDs verified against the arXiv API 2026-10-21. SwiGLU is the GLU variant with the best reported scaling behaviour (arXiv:2002.05202).

**B — Mixture of Experts (NOT CHOSEN; arm S2.1).** Each layer's dense MLP is replaced by `E` experts with a top-`k` router: Switch Transformer (arXiv:2101.03961) for routing, Mixtral (2401.04088) for the modern recipe, DeepSeek-V2/MLA (2405.04434) and DeepSeek-V3 (2412.19437) for current state of the art.

**C — Hybrid / recurrent (SSM, Mamba-like) (NOT CHOSEN).** Replace or supplement attention layers with state-space layers carrying a fixed-size recurrent state: Mamba (arXiv:2312.00752), Mamba-2/SSD (2405.21060), Jamba (2403.19887), Griffin (2402.19427), RWKV (2305.13048).

**D — Small baseline (ADOPTED as K0, in a limited role).** A small model, principally for the laptop fallback path (R6), sized and shaped in §10.7.

| Dimension | A: Dense | B: MoE | C: Hybrid/SSM | D: Small baseline |
|---|---|---|---|---|
| **Active / total params** | 1.000× — 1.149 B `[ESTIMATE]` §4.2 | 2.55–2.92× at the sizes in §3.2 | 1.000× — a recurrent layer is dense | 1.000× — 0.101 B (K0) |
| **Memory at 8 K / 32 K / 128 K** | KV 0.403 / 1.611 / 6.442 GB; weights 2.299 GB | KV **unchanged** (attention identical); weights 3.960 GB at ffn_e 1408 | recurrent state 4.19 MB fp32, **constant in context**; hybrid 6+18 → 1.208 GB KV at 32 K | scales down: 0.193 GiB resident at Q8_0 / 8 K |
| **Training-stability risk** | Low, and *known* — the instabilities at this scale are enumerated with mechanisms in §8.4 | **Higher** — `[KNOWN FACT]` Switch added an auxiliary load-balancing loss because naive routing collapses; Mixtral needs a capacity factor; expert collapse is documented | Moderate but *different in kind* — not divergence, but a different model class with different retrieval behaviour, invalidating the transformer-shaped evaluation controls | Low at this size; the *ceiling* is the issue — 100 M parameters cannot be the agent's brain |
| **Inference latency profile** | Prefill FLOPs-bound (0.604 s for 32 K on 1× A100); decode bandwidth-bound (443.5 tok/s bf16) | Decode becomes collective: all-to-all dispatch + combine per token. At batch 1 the overhead is *least* amortised — the case MoE helps most is not the case that matters | Linear in sequence length, fixed-size state update, but decode here is bandwidth-bound on *weights*, not attention-bound, so the advantage does not materialise at 32 K | not the agent's brain; 16–22 tok/s locally is the point |
| **Tooling maturity** | **Highest** — Megatron-LM, ZeRO, FlashAttention-2, recomputation, vLLM, SGLang, XGrammar, AWQ/GPTQ, EAGLE/Medusa (arXiv IDs in §1.1 and §3) | Good but narrower — MoE-aware *serving* paths with efficient expert dispatch are fewer and less uniform; the local llama.cpp sparse path is a different code path | Thinnest where this project needs it: serving frameworks with prefix caching, quantisation paths and constrained-decoding integration | Full maturity *if* it is a dense transformer (same family); reduced if non-transformer, whose structured-output path would need re-implementation |
| **Verdict** | **Chosen** — the only family with mature, mutually-compatible tooling at every stage, and the family the parallel documents committed to. At 1.15 B its one weakness (quadratic attention) does not bind: §6.4 puts the crossover above 32 K | **Not chosen** — costed in §3.2 and §4.7: **0.41–0.54× the tokens** at equal wall-clock. Reason and revisit condition: §12.1 | **Not chosen** — costed in §3.3: a class change that is not the bottleneck, and the thinnest constrained-decoding support. Reason and revisit condition: §12.2 | **Chosen in a limited role** — the fallback path (R6) is a genuine product requirement, and a scaled-down instance of the *same* family satisfies it with zero extra tooling: same tokenizer, training code, runtime, evaluation harness, grammar machinery. A non-transformer K0 would break every shared path to buy speed the transformer K0 already delivers at 40–54 tok/s |

`[ESTIMATE]` for all numeric cells; `[INFERRED]` for the qualitative cells and the "Chosen" row.

### 3.2 The MoE arm, costed

Keeping embedding + attention + norms fixed (318,871,552) and putting the rest into expert MLPs, the table is resized so the MoE total matches the dense 1.149 B (E = 8, top-2, no shared expert) `[ESTIMATE]`:

| expert ffn | Total | Active | Total/Active | Active as % of dense N | bf16 weight memory |
|---|---|---|---|---|---|
| 1152 | 1.678 B | 0.659 B | 2.55× | 57.3% | 3.356 GB |
| **1408** | 1.980 B | 0.735 B | 2.70× | 63.9% | 3.960 GB |
| **1792** | 2.433 B | 0.848 B | 2.87× | 73.8% | 4.866 GB |
| 1920 | 2.584 B | 0.885 B | 2.92× | 77.0% | 5.168 GB |

The weight-memory increase is paid at training time (all experts resident) and at serving time (all experts resident, or sharded with an all-to-all in the decode path). The KV cache is untouched, because attention is untouched.

`[INFERRED]` On the decode path each token needs an all-to-all dispatch and combine, adding synchronisation latency a dense model does not have. At the batch sizes typical of an interactive coding agent (batch = 1) a sparse model's communication overhead is *least* amortised. This is an inference from the structure of the operation; **no public measurement of this configuration was found, and none is claimed**. **Revisit condition:** §12.1.

### 3.3 The hybrid/SSM arm, costed

`[ESTIMATE]` a Mamba-style block with d = 2,048, d_inner = 4,096, n = 16, state length 16 has a recurrent state of **4.19 MB in fp32 per sequence, constant in context length**, and costs 25,777,152 parameters. 24 such layers give 0.619 B parameters and **zero KV cache**; 48 give 1.237 B, also zero. Against the dense GQA KV cache the state is **96× smaller at 8,192 tokens, 384× at 32,768, 1,536× at 131,072**. A hybrid of 6 Mamba + 18 attention layers is 1.033 B parameters with 1.208 GB of KV at 32 K.

`[INFERRED]` The advantage is real but arrives too late: at the trained 32 K the dense decode is bandwidth-bound on *weights*, not attention-bound, and the hybrid's training and serving toolchain is materially thinner. **Revisit condition:** §12.2.

### 3.4 The K0 baseline, costed

`[ESTIMATE]` K0 = L 12, d 768, ffn 2,048, h_q 12, h_kv 4, head_dim 64, vocab 32,768 → **100,683,264 parameters** (§10.7). Resident at 8,192 context: Q8_0 **0.193 GiB**, Q4_K_M **0.151 GiB**, IQ4_XS **0.146 GiB**. Local decode ceilings: Q8_0 40.84 tok/s, Q4_K_M 52.26 tok/s, IQ4_XS 54.08 tok/s, F16 28.08 tok/s.

---

## 4. The recommendation in detail

### 4.1 Exact configuration, and the one divergence from earlier working figures

| Component | Choice | Rationale anchor |
|---|---|---|
| Layers (L) / d_model | 24 / 2,048 | `llm-development-roadmap.md` §1.4; depth/width ablation §13.8 |
| FFN hidden / form | 5,632 = 2.75 × d; SwiGLU (gate, up, down) | the standard SwiGLU ratio at this size; arXiv:2002.05202 |
| Normalisation / QK-norm | RMSNorm pre-norm per layer; QK-norm on (per-head RMSNorm on Q and K) | arXiv:1910.07467; stability, ablated §13.7 |
| Attention | GQA, 16 query / 4 key-value heads, head_dim 128 | arXiv:2305.13245; KV budget §4.5 |
| q_out / kv_dim | 2,048 (= d_model) / 512 | 16 × 128 / 4 × 128 |
| Position encoding | RoPE, base 10,000, all 24 layers | arXiv:2104.09864; ablation §13.2, S1.4 |
| Embeddings / output head | Tied; vocab 32,768 | §5; `training-data-plan.md` §7.1; §4.2 |
| Attention bias | None | no public figure found showing a benefit at this scale |
| Context / objective | 32,768 trained; causal LM + FIM on a code fraction | `llm-development-roadmap.md` Stage I; arXiv:2108.07732; §13.6 |
| Tool-call format | Sentinel-delimited, grammar-constrained | §7; `AMB-204` |

**The divergence, stated plainly.** Earlier working notes used a configuration named `K1`: 32 layers, d = 2,048, ffn = 5,632, vocab = 49,152, tied, giving **1,543,643,136** parameters (`research/spl/model_arch_arith.py` §1). **It is not recommended here.** (i) `llm-development-roadmap.md` §1.4 names Config B as "the roadmap's primary target" with its exact shape; recommending a different shape would contradict a document other documents reference. (ii) `training-data-plan.md` §7.1 chose a 32,000-token byte-level BPE and `llm-development-roadmap.md` §1.4 says 32,768 — a 49,152 vocabulary matches neither. (iii) The depth difference is real but not decisive: 1.543 B vs 1.149 B is a 34% parameter increase for an *unmeasurable* gain. §13.8's ablation is for that question; it should be answered by measurement, not by a prior.

### 4.2 The parameter budget, broken down

`[ESTIMATE]`, computed by `research/spl/model_arch_final.py` §1 and cross-checked against `param_math.py`. With q_out = 16 × 128 = 2,048 and kv_out = 4 × 128 = 512:

| Component | Arithmetic | Parameters | Share of N |
|---|---|---|---|
| Token embedding (tied with the output head) | 32,768 × 2,048 | 67,108,864 | 5.84% |
| Output projection | 0 (tied) | 0 | 0.00% |
| Attention | (d×q_out + 2×d×kv_out + q_out×d) × 24 = (2,048×2,048 + 2×2,048×512 + 2,048×2,048) × 24 | 251,658,240 | 21.90% |
| MLP (SwiGLU) | 3 × 2,048 × 5,632 × 24 | 830,472,192 | 72.26% |
| Norms | (2×d + 2×head_dim) × 24 = (4,096 + 256) × 24 | 104,448 | 0.0091% |
| Per-layer total | 10,485,760 + 34,603,008 + 4,352 = 45,093,120 × 24 layers | 1,082,234,880 | 94.16% |
| **Total** | 1,082,234,880 + 67,108,864 | **1,149,343,744** | 100% |

**Why this budget** — four arithmetic checks. (1) **The MLP dominates at 72.3%**, a consequence of SwiGLU's three matrices rather than two: a ReLU MLP at 4× expansion (ffn = 8,192) is 33,554,432 per layer, close to SwiGLU's 34,603,008 at ffn = 5,632 — but SwiGLU's gating buys the reported quality per parameter `[KNOWN FACT]` arXiv:2002.05202. (2) **The embedding is only 5.84%** (67.1 M; tying saves another 67.1 M), so the vocabulary decision (§5) is a *compression* decision, not a parameter-budget one — the share moves from 3.01% at 16,384 to 11.03% at 65,536, material but not decisive `[INFERRED]`. (3) **QK-norm costs 6,144 parameters** (24 × 2 × 128), 0.0005% of the model — effectively free, ablated in §13.7. (4) **Untied embeddings would cost +67,108,864** (+5.84%); tying is the right default at 1.15 B, but the quality difference should be measured, not assumed `[INFERRED]`.

**Reconciliation with the roadmap.** `llm-development-roadmap.md` §1.4 states 1,149,337,600; this document computes 1,149,343,744. The difference is **6,144** — exactly the QK-norm parameters the roadmap's counter omitted `[ESTIMATE]`, confirmed by running the same counter with `qk_norm=False` (an exact match). The two figures are consistent.

### 4.3 Where the parameter count sits on the R0–R6 ladder

`[KNOWN FACT]` the ladder (`compute-feasibility.md` §2.1); `[ESTIMATE]` the ratios.

| Rung | Planning N | Config B ÷ rung | Reading |
|---|---|---|---|
| R0 | 30 M | 38.31× | far above |
| R1 | 360 M | 3.19× | 3.2× R1 |
| **R2** | **1.5 B** | **0.77×** | **76.6% of the R2 planning figure** |
| R3 | 7 B | 0.16× | well below |
| R4 | 15 B | 0.077× | far below |
| R5 | 70 B | 0.016× | far below |
| R6 | 405.9 B | 0.0028× | negligible |

`[INFERRED]` **Config B sits in the R2 band, at 76.6% of the R2 planning count.** `compute-feasibility.md` §2.1 specifies a *shape* per rung, not an exact count. Recomputing the ladder's own shapes `[ESTIMATE]`: R1 ladder shape (24 L, d = 960, ffn = 2,560, h_q 15, h_kv 3, head_dim 64, vocab 49,152) → 0.277 B; R1 anchor SmolLM2-360M (32 L, d = 960, same otherwise) → 0.354 B; R2 ladder shape (28 L, d = 1,536, ffn = 4,096, h_q 12, h_kv 4, head_dim 128, vocab 49,152) → 0.780 B; R3 ladder shape (32 L, d = 4,096, ffn = 14,336, h_q 32, h_kv 8, head_dim 128, vocab 32,768, untied) → 7.248 B.

`[INFERRED]` Three readings: the R2 *shape* as written recomputes to only 0.780 B, well under the 1.5 B planning figure — the ladder's parameter and shape columns are not consistent, and the shape column is the more binding one for anyone building; this is recorded rather than quietly corrected. Config B sits *above* the R2 shape and *below* the R2 planning figure, so the R2 row is better read as "the ~1 B band" than as a specific shape. And Config B is 3.19× the R1 anchor — the point of stopping at R2: R1 is where a run costs 1/3.19 as much, and R2 is where capability first becomes interesting for the agent's tasks. `[KNOWN FACT]` `llm-development-roadmap.md` §1.2 calls R2 "the recommended first useful code model".

### 4.4 Depth versus width

`[ESTIMATE]` candidates at roughly constant parameter count, so the comparison is fair:

| L | d | ffn | h_q | h_kv | L/d | N |
|---|---|---|---|---|---|---|
| 24 | 2,048 | 5,632 | 16 | 4 | 11.7 | 1.149 B |
| 32 | 1,792 | 4,864 | 14 | 3 | 17.9 | 1.145 B |
| 36 | 1,664 | 4,608 | 13 | 3 | 21.6 | 1.128 B |
| 20 | 2,304 | 6,144 | 18 | 4 | 8.7 | 1.185 B |
| 18 | 2,048 | 5,632 | 16 | 4 | 8.8 | 0.879 B |

`[INFERRED]` 24L/2,048 and 32L/1,792 are both ≈1.15 B and differ mainly in depth/width. The 24L/2,048 shape was chosen because (a) it is the roadmap's committed Config B, (b) head_dim 128 with 16 heads is a well-exercised shape in the available tooling, and (c) at h_kv = 4 it gives a 4:1 GQA ratio — the ratio whose KV cost the budget can absorb at 32 K. `[UNKNOWN]` no public measurement of the depth/width optimum for a 1.15 B code model was found; §13.8 is the answer to this question for this project.

### 4.5 KV cache: the memory the context costs

`[ESTIMATE]`, bf16: `KV bytes/token = 2 (K and V) × L (24) × kv_dim (512) × 2 bytes = 49,152 B/token`

| Context | KV | GiB | MHA (16 kv heads) | MHA ÷ GQA | batch 8 |
|---|---|---|---|---|---|
| 8,192 | 0.403 GB | 0.375 | 1.611 GB | 4.0× | 3.221 GB |
| 32,768 | 1.611 GB | 1.500 | 6.442 GB | 4.0× | 12.885 GB |
| 131,072 | 6.442 GB | 6.000 | 25.770 GB | 4.0× | 51.540 GB |

Against bf16 weights of 2.299 GB: at 8,192 the cache is 17.5% of the weights; at 32,768 it is **70.1%** (nearly as large as the model); at 131,072 it is **280.3%** (2.8× the model). This is the quantitative reason the recommendation is "train at 32 K, do not plan for 128 K", and why §10.3 treats KV quantisation as a lever separate from weight quantisation. `[KNOWN FACT]` `llm-development-roadmap.md` Stage J states the principle: the KV cache "is not reduced by weight quantisation".

**GQA ratio sensitivity** `[ESTIMATE]`: h_kv = 2 (8:1) → N 1.124 B, KV 0.805 GB at 32 K (35.8% of its own bf16 weights), 3.221 GB at 128 K; **h_kv = 4 (4:1) → N 1.149 B, KV 1.611 GB (70.1%), 6.442 GB**; h_kv = 8 (2:1) → N 1.200 B, 3.221 GB (134.3%), 12.885 GB; h_kv = 16 (1:1 MHA) → N 1.300 B, 6.442 GB (247.7%), 25.770 GB.

`[INFERRED]` 4:1 is the balance point: it keeps the cache below the weight footprint at the trained 32 K context while leaving 16 query heads for head-level diversity. 8:1 saves 0.805 GB but costs 25,165,824 parameters and reduces the number of independently-addressable key subspaces; ablated in §13.2, S1.2.

### 4.6 Training compute and memory

**Compute** `[ESTIMATE]`, `C = 6ND` and §0.4's constants. **Two cost models are shown, and the distinction matters** — see §0.3's correction note and §6.4:

| Tokens/param | D | `6ND` (FLOPs) | Dense-term GPU-h | Wall | Cost | **+attention @ 8 K** | **+attention @ 32 K (the plan)** |
|---|---|---|---|---|---|---|---|
| **20** (Chinchilla-optimal) | 22.99 B | 1.585 × 10²⁰ | 353 | 1.84 d | $984 | **600 GPU-h · 3.13 d · $1,674** | **1,342 GPU-h · 6.99 d · $3,743** |
| 50 (extended-code) | 57.47 B | 3.963 × 10²⁰ | 882 | 4.59 d | $2,461 | 1,500 GPU-h · 7.81 d · $4,185 | 3,354 GPU-h · 17.47 d · $9,358 |
| 100 | 114.93 B | 7.926 × 10²⁰ | 1,764 | 9.19 d | $4,922 | 3,000 GPU-h · 15.63 d · $8,370 | 6,708 GPU-h · 34.94 d · $18,715 |
| 200 (StarCoder2-class) | 229.87 B | 1.585 × 10²¹ | 3,528 | 18.38 d | $9,844 | 6,000 GPU-h · 31.25 d · $16,740 | 13,416 GPU-h · 69.88 d · $37,431 |

`[INFERRED]` **The dense-term column is the `6ND` scaling term and is the correct basis for comparing *token budgets against each other*, because the attention term is a function of the trained context, not of the parameter count.** It is not the cost of a training run: a run trained at 32 K spends 2.80× the dense term on attention (§6.4). Every budget figure in this document that describes *an actual run* is attention-inclusive; the dense-term column is retained because §13's token-budget ablation (S1.11, S2.5) is a comparison across token budgets at a fixed context, where the attention term cancels.

`[KNOWN FACT]` the ~20 tokens/parameter compute-optimal ratio: arXiv:2203.15556 (verified 2026-10-21); the scaling-law basis: arXiv:2001.08361; the validation of `C = 6ND` against Llama 3.1 405B (3.799 × 10²⁵ predicted vs 3.8 × 10²⁵ published): arXiv:2407.21783. For *code*, compute-optimal is not established to be 20: arXiv:2305.16264 and arXiv:2402.19173 (StarCoder2), both verified, document that code data is scarcer and more repetitive than prose. **20 is a starting point; the token-budget axis is itself an ablation** (§13.3).

**H100 comparison** `[ESTIMATE]`: at the dense term, 99 GPU-h / $395 for 20 tokens/parameter; attention-inclusive at 32 K, 357 GPU-h / $1,424. `[OBSERVED FACT]` the H100 peak (989.5 TFLOPS) and price ($3.99) are from §0.4. `[INFERRED]` the H100 is ~2.4× faster per dollar on the dense term and ~2.6× attention-inclusive, which is why §13's budget is quoted on A100 and the H100 appears only as a planning alternative.

`[KNOWN FACT]` the ~20 tokens/parameter compute-optimal ratio: arXiv:2203.15556 (verified 2026-10-21); the scaling-law basis: arXiv:2001.08361; the validation of `C = 6ND` against Llama 3.1 405B (3.799 × 10²⁵ predicted vs 3.8 × 10²⁵ published): arXiv:2407.21783. For *code*, compute-optimal is not established to be 20: arXiv:2305.16264 and arXiv:2402.19173 (StarCoder2), both verified, document that code data is scarcer and more repetitive than prose. **20 is a starting point; the token-budget axis is itself an ablation** (§13.3).

**Failure multiplier** `[ESTIMATE]`: a 2–3× failed-run multiplier on the 20-tokens/parameter budget is **$3,348–$5,022** on A100 at a 32 K trained context ($1,674 × 2–3), or **$1,969–$2,953** on the dense term alone. `[INFERRED]` A single serious attempt is a four-figure commitment, and the cheap pre-screen in §13.2 exists so four-figure commitments are not spent on hypotheses a small model can already falsify.

**Memory** `[ESTIMATE]`, byte-per-parameter tiers from `compute-feasibility.md` §4.1: 18 B/param (fp32 master + fp32 grads + fp32 Adam moments) 20.69 GB; 16 B/param (bf16 grads) 18.39 GB; 12 B/param (8-bit Adam) 13.79 GB; 8 B/param (no fp32 master — not recommended) 9.19 GB.

**Activations** — the number that determines the hardware `[ESTIMATE]`, Megatron-style 34 × hidden × batch × 2 bytes per layer per token: 8,192 context / micro-batch 1 → 27.380 GB uncheckpointed, 1.141 GB with full layer checkpointing; 8,192 / mb 4 → 109.522 GB, 4.563 GB; 32,768 / mb 1 → 109.522 GB, 4.563 GB; 32,768 / mb 2 → 219.043 GB, 9.127 GB.

**Combined fit** `[ESTIMATE]`, at 32 K / micro-batch 1 / checkpointed: 18 B/param → 20.69 + 4.563 = 25.25 GB (fits 80 and 40 GB, not 24 GB); 12 B/param → 13.79 + 4.563 = 18.35 GB (fits all three).

`[INFERRED]` **With full activation checkpointing a single 24 GB card can train this model at a 32 K context** — materially better than the R3 rung would offer, so the project is not forced onto 8-GPU nodes for its first serious run. Without checkpointing, activations alone at 32 K are 109.5 GB and the model needs at least two 80 GB cards. The activation term also explains the 32 K rather than 128 K decision: activation memory scales linearly with context, and the attention term (§6.4) scales quadratically in cost.

### 4.7 What the alternatives cost, in the same units

**MoE** `[ESTIMATE]`, from §3.2's sizes. The comparison must state its cost model, because the two models give different answers and only the attention-inclusive one describes an actual run.

*Dense-term basis (`6ND` only):* the dense baseline is 1.149 B active → 22.99 B tokens at 20 tok/param → 353 A100 GPU-h → $984. E = 8, ffn_e 1408, top-2 → 0.735 B active → 14.69 B tokens → 144 GPU-h → $402, i.e. **0.41× the tokens at equal wall-clock**; ffn_e 1792 → 0.848 B active → 16.95 B tokens → 192 GPU-h → $536, i.e. **0.54×**.

*Attention-inclusive basis (a run actually trained at 32 K):* dense → 1,342 GPU-h, $3,743; MoE at ffn_e 1408 → 776 GPU-h, $2,165, i.e. **0.58× the tokens at equal wall-clock** (0.369× relative to the dense token count once the different active-parameter counts are taken into account). The attention term is a smaller share of a MoE run than of a dense run, because its attention stack is unchanged while its MLP is sparse — so the MoE arm's *advantage shrinks* once attention is counted, from 0.41× to 0.58× of the dense arm's token throughput.

`[INFERRED]` The MoE arm is *cheaper per run* and *worse per run*, on both cost models. Since the scarce resource is the number of runs and the objective is token-budget-limited, dense wins. The conclusion is scale-dependent and its *magnitude* depends on the cost model, which is why both are stated. Revisit in §12.1.

**Hybrid / SSM** `[ESTIMATE]`: §3.3's sizes — 6 Mamba + 18 attention → 1.033 B parameters, 1.208 GB KV at 32 K, 4.19 MB state — land *below* the dense recommendation, so matching 1.149 B would need more attention layers or wider Mamba blocks, a configuration not costed here. `[UNKNOWN]` A hybrid matched exactly to 1.149 B was not costed, and no public figure was found for its training-time throughput on the available hardware.

---

## 5. Tokenizer

### 5.1 Candidates, criteria, choice

| Candidate | What it is | For code | Against code | Verdict |
|---|---|---|---|---|
| Byte-level BPE (GPT-2 style, arXiv:1508.07909) | bytes → learned merges, no `[UNK]` | merges learn code identifiers, operators, indentation runs | slightly worse compression than a code-native vocabulary on pure code | **CHOSEN** |
| SentencePiece / Unigram (arXiv:1808.06226) | subword with a likelihood model; byte fallback | clean, deterministic, well-supported in HF `tokenizers` | training slower; same code-compression ceiling as BPE | Viable alternative, tested in §13.5 |
| Code-specific vocabulary (whitespace- or identifier-splitting) | hand-built vocabulary for source text | best raw compression on code | every non-code byte needs fallback handling; rebuilt per language; permanent maintenance burden | Rejected — see §12.3 |
| Larger byte-level BPE (49,152 / 65,536 / 131,072) | same family, bigger vocabulary | diminishing returns on code; rare-token coverage improves | embedding matrix grows 1.5×/2×/4×; 131,072 breaks uint16 token storage | Rejected at 32,768 — §5.5 |

**Criteria**, in priority order: (1) byte-level coverage — every byte sequence representable, so no `[UNK]`, so hostile or corrupted input is tokenisable rather than fatal; (2) compression on *code* first, then tool-call payloads, then prose; (3) deterministic, reproducible training with a recorded merge table; (4) support for reserved sentinel ids; (5) parameter cost of the embedding matrix.

**Choice:** byte-level BPE, **32,768** vocabulary, 19 reserved sentinels (ids 0–18), 256 base byte tokens, 32,493 learned merges `[ESTIMATE]` (`research/spl/model_arch_tokenizer.py`). uint16 token ids — the vocabulary fits below 65,536, so the data pipeline stores ids in 2 bytes instead of 4 (45.98 GB vs 91.96 GB at 22.99 B tokens `[ESTIMATE]`).

### 5.2 The reserved sentinel inventory

`[ESTIMATE]` ids 0–18, fixed at tokenizer-build time and never learned: `<|endoftext|>` (packing separator), `<|pad|>`, `<|fim_prefix|>`, `<|fim_middle|>`, `<|fim_suffix|>`, `<|tool_call|>`, `<|tool_end|>`, `<|tool_name|>`, `<|tool_args|>`, `<|tool_result|>`, `<|tool_result_end|>`, `<|repo|>`, `<|file|>`, `<|diff|>`, `<|user|>`, `<|assistant|>`, `<|system|>`, `<|endofdoc|>`, `<|think|>` (reserved, unused at launch). **Consequence:** the tool-call format of §7 is representable with single-token markers, and the markers are *atomic* — the model cannot emit half a marker, so the parser never has to disambiguate a partial sentinel.

### 5.3 The vocabulary-size discrepancy: OPEN-A1

`[KNOWN FACT]` `training-data-plan.md` §7.1 specifies a **32,000**-token byte-level BPE; `llm-development-roadmap.md` §1.4 specifies **32,768** for Config B. These are inconsistent and both are committed elsewhere. This document adopts **32,768** because the parameter count, the ladder position and the model geometry in §4 all derive from it, and because a power-of-two vocabulary makes the uint16 id space and the hardware-friendly tensor shapes natural.

`[ESTIMATE]` The alternative's parameter consequence: vocab 32,000 → embedding 65,536,000; total N = 1,147,770,880, a difference of 1,572,864 parameters (0.14%). The two are interchangeable at this scale, so the discrepancy is not worth a design change — but it must be resolved before the tokenizer is built, because a vocabulary size fixes the model's embedding dimension forever. **What would settle it:** a single decision recorded in `training-data-plan.md` §7.1 and referenced by `llm-development-roadmap.md` §1.4, plus §13.5's tokenizer ablation, which measures whether 16,384 or 32,768 is better on the actual corpus — settling the question on evidence rather than on precedence.

### 5.4 Code-specific considerations

- **Indentation.** Leading whitespace is a large fraction of source bytes. A 4-space indent level and a tab indent must not cost the same number of tokens for the same logical nesting, or the model pays for formatting. `[ESTIMATE]` The harness measures "tokens per indent level" (§5.7 T6); the tokenizer should learn common indent runs as single merges.
- **Repeated whitespace.** Blank lines and long runs of spaces should cost one token, not one per space. Byte-level BPE learns these as merges only if they are frequent enough in the corpus to earn a slot; the corpus mix therefore determines whether whitespace gets its own merges.
- **Unicode.** `[ESTIMATE]` The corpus contains non-ASCII; byte-level BPE handles it with no `[UNK]`, but at a token cost of up to 4 tokens per non-ASCII character if no merged forms exist. `[UNKNOWN]` No public figure was found for this corpus's Unicode token cost; T7 measures it.
- **Byte fallback.** With a byte-level base alphabet there is no fallback path to design: every byte is already a token, so a corrupted or hostile byte stream is *tokenisable*, not fatal — though the harness must still bound and sanitise it (a harness concern, `interface-spec.md` §4's output ladder).
- **Vocab size vs embedding size.** Vocab size sets the *rows* of the embedding matrix; embedding size sets the *columns*. Only the row count depends on the tokenizer: 32,768 × d 2,048 = 67,108,864 parameters.

### 5.5 The cost of the embedding matrix at the chosen vocabulary

`[ESTIMATE]` at 32,768 × 2,048: bf16 134.2 MB · fp32 268.4 MB · int8 67.1 MB · int4 33.6 MB.

Tied embeddings mean this matrix is also the output head, so it is the only place where vocabulary size directly multiplies model size. Embedding share of total N by vocabulary `[ESTIMATE]`: 16,384 → 3.01%; 24,576 → 4.44%; **32,768 → 5.84%**; 49,152 → 8.51%; 65,536 → 11.03%; 131,072 → 19.87%. `[INFERRED]` Beyond roughly 65,536 the embedding matrix becomes a first-class part of the model and the vocabulary decision stops being a tokenizer decision; 32,768 keeps it at 5.84% — material, not dominant.

### 5.6 Training from scratch versus adapting an existing tokenizer

**Train from scratch** when: the corpus mix differs materially from any public corpus (this one is code-heavy with tool payloads and diffs); the sentinel inventory must be reserved (public vocabularies rarely have `<|tool_args|>`); the merge table must be reproducible from the project's own data manifest; and the compression rate on *this* mix is a first-class metric rather than an inherited assumption. **Adapt an existing tokenizer** when the corpus matches the source corpus, when the merge table's provenance is unclear, or when a from-scratch build is unjustified.

`[INFERRED]` **Train from scratch.** The corpus mix is the point: a public code tokenizer's compression rate was measured on *its* corpus, and the harness in §5.7 measures on *this* one. Adapting would import an unmeasured assumption and a licence/provenance dependency into a document whose sibling `licensing-and-provenance-review.md` treats provenance as a first-class concern. The cost is a one-off preprocessing job — `[UNKNOWN]` its wall-clock was not measured and no public figure was found for this corpus size and hardware; the harness must measure it before the tokenizer is built.

**One hard constraint from R6:** the K0 fallback model must use the *same* tokenizer. A separate vocabulary would mean two tokenisers, a translation layer and a second embedding table — and the fallback would save nothing it was meant to save.

### 5.7 The tokenizer evaluation harness

Nine tests. Every rate is measured on the *project's* corpus, with the corpus version recorded; none may be carried over from a published figure.

| # | Test | Measures | Pass criterion |
|---|---|---|---|
| T1–T3 | Compression: code, prose, tool payloads | tokens/byte on source files, on documentation/comments, on real JSON/tool-call bodies | reported, not gated |
| T4 | Round-trip fidelity, whole corpus | tokenize → detokenize → compare bytes | byte-exact rate = **1.000000** |
| T5 | Round-trip, adversarial inputs | invalid UTF-8, lone surrogates, NUL, BOM, CRLF, tabs, trailing whitespace, no-trailing-newline files | byte-exact rate = **1.000000** |
| T6 | Whitespace/indent structure | tokens per indent level (4-space vs tab) | reported; feeds §5.4 |
| T7 | Unicode | tokens per character: CJK, emoji, RTL, combining marks | reported |
| T8 | Identifier fragmentation | mean subword count per identifier | reported |
| T9 | Tool-call overhead | tokens used by sentinel markers vs equivalent JSON | fixed overhead = 6 tokens/call `[ESTIMATE]` |

`[KNOWN FACT]` the harness itself is `research/spl/model_arch_tokenizer.py`, which specifies T1–T9 and the sentinel inventory; the *rates* it prints are placeholder targets, not measurements. `[UNKNOWN]` **No public figure found for tokens-per-byte on this project's corpus mix.** The placeholders used in the arithmetic are 0.22–0.28 tokens/byte (JSON 0.22, code 0.28); these are **placeholders, not measurements**, and every downstream number depending on them is `[ESTIMATE]`-conditional on T1–T3. `[INFERRED]` a 5% token reduction on a fixed byte corpus is a 5% smaller D, hence a 5% smaller `C = 6ND`, hence a 5% smaller bill: at D = 22.99 B and 353 A100 GPU-h that is 17.7 GPU-h, **$49** `[ESTIMATE]`. Small, but the tokenizer is a cheap lever on the dominant cost term, which is why §13.5 measures it first.

---

## 6. Context length

### 6.1 Position encoding: RoPE

**Choice: RoPE, base 10,000, applied to all 24 layers** (arXiv:2104.09864, arXiv API 2026-10-21). RoPE rotates query and key vectors by position, so the relative-position property is preserved exactly in the dot product and extrapolation is tunable by base or by scaling.

| Alternative | Mechanism | Why not chosen |
|---|---|---|
| ALiBi (arXiv:2108.12409) | additive linear bias by head distance | no learned position parameters; strong length extrapolation. `[INFERRED]` it trades expressiveness for extrapolation, and the project needs expressiveness at 32 K and has no 128 K plan, so it buys the wrong property. Ablated in §13.2, S1.4 |
| Learned absolute (GPT-2) | learned embedding table | `[INFERRED]` does not extrapolate; unusable for context extension (§6.2) |
| T5-style relative bias | per-head bucket bias | `[INFERRED]` adds per-layer memory and bucketing complexity for no measured benefit at this scale |
| NoPE | none | `[INFERRED]` content alone must carry order, which degrades on retrieval tasks |

### 6.2 Extension strategy

The recommendation is to **train at 32,768 and not extend afterwards** — but the extension path must exist, because Stage I's context work and any future 128 K work depend on it.

**Extension methods surveyed** `[KNOWN FACT]` (all verified against the arXiv API 2026-10-21):

| Method | arXiv | Mechanism | Cost |
|---|---|---|---|
| NTK-aware RoPE scaling | 2307.02486 | interpolate base by the scale factor | zero training cost; short-context degradation |
| YaRN | 2309.00071 | blended per-frequency NTK scaling + attention temperature | a few hundred steps of continued training |
| PI / position interpolation | 2306.15595 | linearly rescale position indices | a few hundred steps; degrades short-context |
| LongRoPE | 2402.13753 | per-dimension progressive extension; non-uniform search over factors | a few hundred steps; preserves short-context better |
| Infini-attention | 2404.07143 | compressive memory built into attention | architectural change, not an extension — a §12 revisit |
| Continued pretraining at longer context | — | train at the target length | full cost |

`[INFERRED]` **If extension is needed, use YaRN or LongRoPE on the trained 32 K checkpoint, then continue training briefly at the longer length.** Both preserve short-context behaviour better than plain interpolation, which matters because the same checkpoint must still serve the 8 K fallback path and ordinary 32 K requests. The cost is a fraction of a full run: `[ESTIMATE]` a few hundred additional steps at 32 K with a 4 M-token batch is order 1–5% of a base run. `[UNKNOWN]` The exact step count was not measured and no public figure was found; §13.4's scaling curve would set it.

### 6.3 Long-context degradation: the problem, stated precisely

The problem is not that the model cannot *hold* the information. It is that retrieval accuracy inside a long window is a function of where the information sits, and the curve is not flat. `[KNOWN FACT]` "Lost in the Middle" (arXiv:2307.03172) documents that performance on information at the beginning or end of a long context can be far above performance on the same information placed in the middle. RULER (arXiv:2404.06654) and LongBench (arXiv:2308.14508) are the standard instruments.

`[INFERRED]` This has a direct architectural consequence the recommendation acts on: **a longer trained context is not automatically a better context.** The useful measure is *effective* context — the span over which retrieval accuracy stays within a stated margin of the short-context result — not the nominal window, so §13.4 measures the curve and gates on it rather than assuming 32,768 tokens of useful context because 32,768 tokens fit. A second consequence: because the harness owns retrieval and summarisation (`prompt-pattern-analysis.md` §7), the model's job is to *consume* what the harness hands it, not to search — it needs capacity, not a search index. The harness's chunking strategy must therefore be validated against the same curve: a chunk in the middle of a 32 K window is exactly the "lost in the middle" case.

### 6.4 What the context costs: the attention-overhead term

`[ESTIMATE]`, from `research/spl/model_arch_final.py` §9 and independently re-derived by `model_arch_verify.py`. The `C = 6ND` term omits attention's dependence on sequence length. Attention costs ≈ 12·L·d·Q FLOPs per token (two matmuls, forward and backward), which grows *linearly with context*; the dense term is constant per token.

| Context | Attention FLOPs/token | Dense `6N` | Ratio |
|---|---|---|---|
| 8,192 | 4.83 × 10⁹ | 6.90 × 10⁹ | **0.70×** |
| 32,768 | 1.93 × 10¹⁰ | 6.90 × 10⁹ | **2.80×** |
| 131,072 | 7.73 × 10¹⁰ | 6.90 × 10⁹ | **11.21×** |

The honest training cost of a run *trained entirely at* a given context, adding the attention term to `6ND` `[ESTIMATE]`:

| Trained context | `6ND` | + attention | Total FLOPs | 8×A100 wall | Cost | Runs/yr |
|---|---|---|---|---|---|---|
| 8,192 | 1.585 × 10²⁰ | 1.11 × 10²⁰ | 2.696 × 10²⁰ | 3.13 d | $1,674 | 117 |
| **32,768** | 1.585 × 10²⁰ | 4.44 × 10²⁰ | 6.028 × 10²⁰ | **6.99 d** | **$3,743** | **52** |
| 131,072 | 1.585 × 10²⁰ | 1.78 × 10²¹ | 1.936 × 10²¹ | 22.44 d | $12,020 | 16 |

`[INFERRED]` **This is the quantitative reason the recommendation trains at 32 K and treats 128 K as extrapolation-only.** The dense-term figure of $984 is not a training cost at any context; a run trained at 8 K costs $1,674, at 32 K $3,743, and at 128 K $12,020 — 12.3× the dense term. Stating a training budget without naming the context it was computed at would be misleading, so every cost figure here names its context. The second reason is activation memory, which scales linearly with context (§4.6): 109.5 GB uncheckpointed at 32 K against 27.4 GB at 8 K. Both terms push the same way, and both support Stage I's 8 K / 32 K plan.

**A note on the attention constant** `[UNKNOWN]`. The 12·L·d·Q factor assumes full quadratic attention and counts the causal mask's wasted half as if it were computed. A causal implementation skips the upper triangle, which would roughly halve the attention term — and would bring a 32 K run to ~847 A100 GPU-h (4.41 d, $2,364) instead of 1,342 (6.99 d, $3,743). `[INFERRED]` the halving is what a masked kernel would actually save, but the *implementation* number is not established here, so the conservative full-attention figure is used throughout and the halved figure is recorded as the optimistic bound. **What would settle it:** a measured MFU on one Config B run at 32 K with and without a causal-attention kernel (§13.7's precision arm is the natural place to record it). `[UNKNOWN]` no public figure was found for the ratio of effective to nominal attention FLOPs at this scale.

### 6.5 Techniques that work, and the ones that do not

`[INFERRED]`, from §6.2 and §6.3: (i) train the *bulk* of the run at the target context rather than extending afterwards — the cheapest way to avoid mid-window degradation is never to have it; (ii) if extension is needed, use a frequency-blended method (YaRN/LongRoPE) rather than uniform interpolation, and re-tune the attention temperature; (iii) include long-context training data *in the mix* so the model sees positions in the middle of long documents during pretraining; (iv) measure effective context, not nominal context, and gate on it; (v) keep chunk placement a harness responsibility — placing the most relevant material near the beginning or end of the window costs nothing and is available today; (vi) never extend past the point where the attention term dominates (§6.4) without recomputing the cost model.

`[UNKNOWN]` No public figure was found for the *effective* context of a 1.15 B model on a code corpus at 32 K. §13.4 is the measurement that would produce one, and its result is the only thing that would justify changing the trained context.

---

## 7. Output format: how the model emits tool calls

### 7.1 The format

The model emits a tool call as a sentinel-delimited block:

```
<|tool_call|><|tool_name|>read_file<|tool_args|>{"path":"src/app.py","offset":120,"limit":80}<|tool_end|>
```

`[ESTIMATE]` the sentinel markers cost 6 tokens per call (§5.7 T9) — negligible against a typical call's ~40 tokens of JSON body.

### 7.2 The argument-parsing contract

The contract is the load-bearing artefact of this section, so it is stated exactly:

1. The model emits raw text; no structured-output channel, no separate tool head.
2. The **serving runtime** applies a grammar to the sampler, so every emitted token sequence is a valid member of the tool-call language.
3. The **harness** parses the emitted text with a total parser: it either yields a well-formed call object, or it fails.
4. On failure the harness **rejects the call** and returns `<tool_use_error>`. It does not repair it, guess the intended tool, coerce argument types, or fall back to a fuzzy or regex matcher.

`[KNOWN FACT]` llama.cpp's server exposes `grammar`, `json_schema` and `response_format` request fields and a `--jinja` chat-template path for function calling; XGrammar (arXiv:2411.15100, verified 2026-10-21) is the upstream constrained-decoding library. `AMB-204` requires the adapter MUST NOT repair malformed tool calls; `AMB-203` requires byte-identical schemas across arms.

`[INFERRED]` **The three-layer defence** is what makes this deterministic rather than merely tidy. (i) *Prior layer* — the format was in the training objective, so the model's prior over tool-call text is concentrated on well-formed blocks. (ii) *Runtime layer* — the sampler cannot produce a token outside the grammar, so a malformed call is not sampled at all. (iii) *Harness layer* — the parser is total, so even a corrupted stream (truncation, byte corruption, a stopped generation) produces a rejection, never a partial parse dressed up as a call. Layers (ii) and (iii) make the property hold; layer (i) makes it *usually* unnecessary.

### 7.3 Why not JSON-in-prose

The alternative — the model writes prose containing a JSON blob and a matcher extracts it — fails three ways. (i) **Ambiguity:** the matcher must decide where the JSON starts and ends, and prose can contain braces, quotes and fences; every such matcher is a heuristic. (ii) **Repair:** a heuristic that fails closed sometimes must be repaired to be useful, and repair is exactly what `AMB-204` forbids. (iii) **Unmeasurable:** the matcher's error modes are entangled with the model's errors, so an evaluation cannot separate "the model produced a bad call" from "the matcher mangled a good call" — breaking the diagnosis `AMB-801`/`AMB-802` require. `[INFERRED]` Hence §13.6's output-format ablation includes an explicit JSON-in-prose *control* arm: without a control, "fewer malformed calls" measures the grammar engine rather than the model.

### 7.4 Streaming

Two separable capabilities, per R4. **Token-level streaming** is a runtime property: llama.cpp's server emits SSE deltas; vLLM and SGLang stream natively. **Prefix stability** — the first *k* tokens identical regardless of what follows — is a property of autoregressive decoding with a fixed sampling configuration, and is what makes partial output safe to display while a call is still being generated. `[INFERRED]` It is guaranteed by fixing the sampler: a fixed seed, fixed temperature, fixed top-p/top-k, and — for the tool-call path — the grammar applied from the first token. `[KNOWN FACT]` `AMB-206` requires per-request token accounting; with a self-hosted runtime the counts are the tokenizer's own, so there is no provider-side estimation drift.

### 7.5 The client-side sufficiency requirement

`[KNOWN FACT]` `AMB-211`: the harness must not require any provider capability. Therefore **client-side grammar enforcement must be sufficient on its own**: the harness applies the grammar itself, and the server-side grammar is an *optimisation* that reduces wasted sampling, not a dependency. A model that only works when the provider's server applies a grammar does not work on a different runtime, which defeats self-hosting. Hence the grammar is a standalone file, versioned with the model, not embedded in any one runtime's request path. `[KNOWN FACT]` `AMB-210` requires capabilities to be *declared* rather than discovered, so the adapter declares which constrained-decoding path it uses and the harness falls back to its own.

### 7.6 The failure path, in full

| Failure | Detection | Response |
|---|---|---|
| Grammar violated | the runtime never samples it; the harness parser also rejects | `<tool_use_error>`; no repair |
| Truncated generation (token limit or stop) | parser sees an unterminated block | `<tool_use_error>` reason `truncated` |
| Wrong tool name | name not in the declared tool set | `<tool_use_error>` reason `unknown_tool` |
| Argument type wrong, or argument missing | schema check | `<tool_use_error>` reason `schema` |
| Valid call, wrong semantics | the tool runs; the result is returned | normal tool result, including an error result |
| Model emits prose instead of a call | parser finds no `<|tool_call|>` | treated as prose; the harness decides, per the agent loop, whether to re-prompt or stop |

`[INFERRED]` Every row is a *detection*, not a *correction*. The last row is the one place where a policy decision lives rather than a parse — a harness decision, taken without the adapter's participation.

---

## 8. Numerical precision and training stability

### 8.1 The recipe

| Setting | Value | Reason |
|---|---|---|
| Compute precision | **bf16** | same exponent range as fp32; no loss scaling needed; `[KNOWN FACT]` ε = 2⁻⁸ = 3.906 × 10⁻³ |
| Master weights / gradients | fp32 | `[KNOWN FACT]` fp32 ε = 5.961 × 10⁻⁸ — the small-update problem needs it |
| Optimizer | **AdamW**, β = (0.9, 0.999), ε = 1 × 10⁻⁸ | `[KNOWN FACT]` β1 = 0.9 → ~10-step window; β2 = 0.999 → ~1,000-step window |
| Weight decay | 0.1 on matrix weights, 0 on norms and embeddings | standard practice |
| Gradient clipping | global-norm clip **1.0** | `[UNKNOWN]` the optimal threshold is corpus- and schedule-dependent; no public figure was found for this configuration. §13.7 measures it. |
| Loss scaling | **none** | bf16's exponent range makes it unnecessary; fp16 would require it (fp16 max 65,504, min normal 2.098 × 10⁻⁵, ε = 4.883 × 10⁻⁴) |
| Autocast | bf16 matmuls, fp32 reductions | avoids bf16 accumulation error in the softmax denominator and the loss reduction |

`[INFERRED]` **Why not fp16:** the cost is a loss scale, a scale-search schedule, and silent-underflow bugs (gradients below 2.098 × 10⁻⁵ flush to zero). bf16 removes all three at the price of 3 fewer mantissa bits — a loss that matters for the *forward* pass but not the *update*, since the update happens in fp32 master weights regardless. `[KNOWN FACT]` the standard recommendation, Megatron-LM (arXiv:1909.08053). **Why not pure fp32:** fp32 matmul throughput on A100 is roughly half that of bf16, so the run would cost about twice the GPU-hours.

### 8.2 The scales that matter

Three different numerical scales appear in this recipe, and they are not interchangeable:

1. **Weight/activation scale** — bf16's 8-bit mantissa is the binding constraint on forward precision. `[INFERRED]` This is why RMSNorm (normalising activations to unit variance before each sublayer) matters more here than in fp16 training: it keeps activations in the range where bf16's relative precision is sufficient.
2. **Update scale** — the update is `lr × m̂/(√v̂ + ε)`, i.e. O(lr). With fp32 master weights an update of relative size 10⁻⁷ is representable; with bf16 master weights it falls below the representable increment (2⁻⁸ ≈ 3.9 × 10⁻³) and is **rounded away**. `[INFERRED]` this, not forward-pass precision, is why fp32 master weights are non-negotiable: at 22.99 B tokens and a typical 3 × 10⁻⁴ cosine learning rate, a late-training update is far smaller than bf16's representable increment.
3. **Gradient scale** — gradients span many orders of magnitude across layers. Global-norm clipping at 1.0 normalises this to a single well-conditioned scale; per-layer clipping is less well-behaved because it changes the relative scale between layers. `[ESTIMATE]` the threshold is a *diagnostic* value as much as a control: the *fraction of steps clipped* should be logged, and a run whose clipping fraction jumps has a shifted gradient distribution — an early visible symptom of §8.4's instabilities. `[UNKNOWN]` the threshold optimal for this corpus is not known; no public figure was found for a 1.15 B code model. §13.7's arm S1.12 sweeps it.

### 8.4 Known instabilities, and the checklist that catches them

| Instability | Mechanism | Detection | Mitigation |
|---|---|---|---|
| **Loss spike / divergence** | a single large update knocks the model out of its basin | loss jumps >2× step-to-step | clip 1.0; skip the batch; if the loss does not recover, restart from the last checkpoint |
| **Attention-logit blowup** | Q·K grows without a normalising mechanism, typically early in training | max attention logit rises steadily across layers | **QK-norm** — recommended, ablated in §13.7; it caps the logits by construction |
| **Head collapse** | some heads become near-identical or near-dead, wasting their sublayer | per-head output variance across the batch; fraction of heads with near-zero variance | QK-norm helps; log the per-head variance histogram |
| **QK-norm / QK-scaling interaction** | with QK-norm the logits are bounded, so the conventional 1/√d scaling becomes partly redundant | comparing logit histograms with and without | precisely what §13.7's arm measures |
| **Untied-head divergence** | the output head and input embedding drift apart under different gradient pressures | cosine similarity between the two, if untied | moot if tied (recommended); ablated if untied |
| **fp16 underflow** | gradients below 2.098 × 10⁻⁵ flush to zero | gradient norms | do not use fp16; use bf16 |
| **Router collapse** (MoE arm only) | the router sends everything to one expert | per-expert load distribution | load-balancing loss + capacity factor `[KNOWN FACT]` Switch 2101.03961, Mixtral 2401.04088; not applicable to dense |
| **Activation-memory exhaustion** | context × micro-batch × hidden exceeds card memory | OOM mid-run | activation checkpointing; micro-batch 1 at 32 K (§4.6) |

`[INFERRED]` **The checklist is a set of logged quantities, not a set of beliefs.** Each row's detection column names something a training script can log every step or every N steps. That is what makes §13.7's precision ablation interpretable: not "bf16 looked fine" but "the head-variance histogram did not collapse, the clipping fraction stayed below X, and the loss curve matched the fp32-master control to within the gate". The failure mode this document is most concerned about is the one that does **not** announce itself: a run that completes, produces a plausible-looking loss curve, and has quietly collapsed half its heads.

---

## 9. Checkpointing and reproducibility

### 9.1 What a checkpoint contains

`[INFERRED]`, the minimum for a run to be reproducible and for a checkpoint to be usable: **model state** (fp32 master weights, with a bf16 copy derived at load — §8.1, bf16 master weights lose small updates); **optimizer state** (AdamW moments m and v, plus the step counter) and **scheduler state** (current step, LR schedule position), both needed to resume without a loss-curve discontinuity; **RNG states** for the data-order, dropout and augmentation generators, because data order is a reproducibility input (§9.3); **scaler state** (n/a — bf16 needs no loss scale); the **model config** (L, d, ffn, h_q, h_kv, head_dim, vocab, tie, QK-norm, RoPE base) needed to rebuild the parameter tree; the **tokenizer** — merge table, sentinel inventory and vocab size — because the tokenizer is part of the model; **metadata** (data version, code version, config hash, hardware, seed, wall-clock, GPU hours; §9.2); the **corpus manifest**; and the **training log** (per-step loss, LR, grad norm, clipping fraction, MFU, tokens/s) for diagnosability (`AMB-801`).

`[INFERRED]` The optimizer state roughly doubles the checkpoint size (two fp32 tensors per parameter plus the fp32 master copy ≈ 16 bytes/parameter of optimizer+master state, against the model's 2 bytes in bf16): ≈ 18.4 GB per checkpoint at 1.149 B. **Practical consequence:** full checkpoints are written periodically to object storage, and the *weights-only* checkpoint (bf16, ≈ 2.3 GB) is what gets exported for serving. `[ESTIMATE]` 10 full checkpoints ≈ 184 GB; 20 weights-only exports ≈ 46 GB.

### 9.2 How a run is reproduced

The reproduction record is a single manifest, and it names five inputs: **data version, seed, code version, config, hardware**.

**Data version** — the corpus manifest hash: the document list, byte counts, file hashes, mixture weights, and the packing and packing-seed used. **Seed** — one master integer expanded deterministically, so all derived RNGs are seeded from it by name and adding a consumer does not perturb others. **Code version** — the training repo's commit hash *plus* the container image digest; `[INFERRED]` a commit hash alone is insufficient, because dependency versions change numerics. **Config** — the full *resolved* config, hashed: not the source file, but the config after all defaults and overrides. **Hardware** — GPU model and count, interconnect, driver, CUDA and framework versions, precision flags; `[INFERRED]` because a run on 8×A100 is not bit-reproducible against one on 8×H100, and the record must say which it was.

`[INFERRED]` The manifest does not claim bitwise reproducibility — generally not achievable across different hardware, kernel versions or parallel decompositions — but makes a *divergence* explicable: given two runs that differ in outcome, it says which input differs, so the difference is attributed rather than guessed at.

### 9.3 Determinism seams

`[INFERRED]`, in rough order of how much they matter:

1. **Data order.** The largest seam. Packing and shuffling use a seeded RNG recorded in the manifest; the *packing itself* (which documents are concatenated, how they are truncated, how separators are inserted) is a versioned preprocessing step, not a training-time detail. Without versioned packing the run is not reproducible even with everything else fixed.
2. **Parallel decomposition.** GPU count, tensor/pipeline/data-parallel degrees and gradient-accumulation steps all change the reduction order. The same token budget split across a different number of devices gives a different loss curve, so the decomposition is part of the hashed config.
3. **Non-deterministic kernels.** FlashAttention-2 and cuBLAS reductions are not bitwise deterministic by default, which is why the recipe pins a fixed kernel and library version set (via the image digest) rather than "latest". `[UNKNOWN]` the magnitude of the resulting run-to-run variation at this scale was not measured and no public figure was found; §13.7's precision arm is the closest proxy — a null result there means "indistinguishable at the measurement's resolution", not "identical".
4. **Sampling at inference.** Fixed seed, temperature, top-p/top-k, and the grammar applied from the first token — §7.4. Without a fixed sampling configuration, prefix stability fails and the streaming path is unsafe.
5. **Tokenization.** Deterministic by construction if the merge table is fixed and recorded — hence the tokenizer is a checkpoint component (§9.1).

### 9.4 Reproducibility as an evaluation control

`[INFERRED]` Reproducibility is what makes §13's ablation arms comparable. Every arm must differ from the baseline in **exactly one** recorded input; if the data order differs between two arms as well, a difference in the metric cannot be attributed to the architecture. `[KNOWN FACT]` this is the same discipline `AMB-203` imposes on schemas ("byte-identical schema across arms") and `benchmark-and-evaluation-plan.md` §9.4 imposes on harness variants ("harness variant travels with the score"). **Rule: the config diff between an arm and the baseline is the arm's hypothesis, and nothing else.**

---

## 10. Inference serving

### 10.1 Runtime choice

**Local / edge — llama.cpp (GGUF).** `[KNOWN FACT]` the CPU-only build needs only `GGML_BLAS=ON` + `GGML_BLAS_VENDOR=OpenBLAS`; the server is OpenAI-compatible with SSE streaming, `grammar`/`json_schema`/`response_format`, a `--jinja` function-calling path, and KV-cache quantisation behind `-ctk`/`-ctv`. Fetched from the llama.cpp README and `docs/build.md`, 2026-10-21. **Hosted — vLLM (arXiv:2309.06180) or SGLang (arXiv:2312.07104).** `[KNOWN FACT]` PagedAttention, continuous batching, prefix caching, OpenAI-compatible API, structured-output support via XGrammar (arXiv:2411.15100) — all verified against the arXiv API 2026-10-21. **Constrained decoding — XGrammar**, `[KNOWN FACT]` the upstream library both runtimes use for grammar-constrained sampling; the grammar is written standalone and versioned with the model (§7.5).

`[INFERRED]` Both runtimes implement the OpenAI-compatible API, so the adapter boundary in `interface-spec.md` §12 needs no separate code path for "our model" versus "a provider model" — which reduces the code that could later be ambiguous about what is ours. The grammar engine is the component most likely to differ between runtimes, which is why §7.5 makes client-side enforcement sufficient and server-side enforcement optional.

### 10.2 KV-cache strategy

`[ESTIMATE]` the KV figures are those of §4.5: 49,152 bytes/token → 0.403 GB at 8,192 tokens (17.5% of the 2.299 GB bf16 weights), **1.611 GB at 32,768 (70.1%)**, 6.442 GB at 131,072 (280.3%).

`[INFERRED]` **The serving strategy follows from one fact: at 32 K the KV cache is 70% of the weight footprint.** So (i) prefill dominates the *memory* story, not the weights; (ii) 8 concurrent 32 K requests need 12.885 GB of KV against 2.299 GB of weights — 85% of resident memory; and (iii) KV quantisation is a first-class lever.

**Strategies, in the order they apply:**
1. **Paged attention** (vLLM) — the KV cache is stored in non-contiguous pages, so memory is allocated on demand and fragmentation does not force over-reservation. `[KNOWN FACT]` vLLM's core contribution, arXiv:2309.06180.
2. **Prefix caching** — the agent's prompt structure (system preamble, tool definitions, repository prefix) is shared across turns, and the repository prefix across *many* requests in a session. `[INFERRED]` reusing it is the largest saving available: it is free, and the prefix is genuinely identical, not merely similar.
3. **KV quantisation** — int8 or int4 on the K and V tensors, exposed by llama.cpp via `-ctk`/`-ctv`. `[ESTIMATE]` int8 halves the cache (1.611 → 0.805 GB at 32 K); int4 quarters it (→ 0.403 GB). `[UNKNOWN]` **The quality cost of KV quantisation on a code model was not measured and no public figure was found.** The mechanism that makes weight quantisation more benign — weights are used once per token, KV once per token per query — does not obviously apply. §10.4 makes this a gated opt-in; §13.7's precision arm measures it against the int8 baseline.
4. **Context budgeting at serving time** — the model is *trained* at 32,768, so serving should cap the window there by default and offer 8,192 for latency-sensitive work. `[INFERRED]` a serving policy, not a model property, belonging in the harness's request policy.

`[KNOWN FACT]` `llm-development-roadmap.md` Stage J states the governing principle: **weight quantisation does not reduce the KV cache.** The two levers are separate and must be budgeted separately.

### 10.3 Memory footprint at the chosen context

`[ESTIMATE]`, batch 1, 32,768 context: int8 weights (8.5008 bpw) 1.221 GB + bf16 KV 1.611 GB = **2.832 GB (2.637 GiB)**; with int8 KV, 2.027 GB (1.887 GiB); with Q4_K_M weights (4.8944 bpw) + bf16 KV, 2.314 GB (2.155 GiB); with Q4_K_M + int8 KV, 1.508 GB (1.404 GiB). Weight bytes by GGUF format `[KNOWN FACT]` llama.cpp README, observed 2026-10-21: F16 16.0005 bpw, Q8_0 8.5008, Q6_K 6.5633, Q5_K_M 5.7036, Q4_K_M 4.8944, IQ4_XS 4.4597, Q3_K_M 3.9960.

`[INFERRED]` The whole model at 32 K context fits in **under 3 GB** at the recommended default — which is what makes the hosted path and the local path the *same* model rather than two different products.

### 10.4 Quantisation options and the measured-quality caveat

**The policy** `[KNOWN FACT]` `llm-development-roadmap.md` Stage J: **int8 by default, 4-bit as an explicit opt-in**, with a gate. The gate restated: `[ESTIMATE]` a 4-bit arm must not be more than **2.0 percentage points** worse than the int8 arm on the primary metric, with the 95% CI excluding zero and the Holm-corrected p < 0.05 criterion of `benchmark-and-evaluation-plan.md` §10.3 applied.

**The methods** `[KNOWN FACT]`: GPTQ (arXiv:2210.17323), AWQ (arXiv:2306.00978) — both verified against the arXiv API 2026-10-21.

**The caveat, stated plainly:** *every* quality claim about a quantised version of this model is `[UNKNOWN]` until it is measured. `[UNKNOWN]` **No public figure was found for the quality cost of int8 or 4-bit weight quantisation, or of int8/int4 KV quantisation, applied to a 1.15 B code model.** There is no measurement of this model in any form, so there is no measurement of its quantised forms. What can be said is structural: `[INFERRED]` quantisation errors are not uniform across weights, and code models contain a few high-magnitude weights (embedding rows for frequent identifiers, the attention output projection) whose distortion is more consequential than the average weight's. Hence int8-by-default with a *measured* 4-bit gate rather than "4-bit, it usually works."

**Quantization-aware training** is deliberately **not** in the base plan `[SPECULATIVE]`: a second training run, and the measurement budget (§13) is better spent on the architecture questions the base plan raises. Revisit condition in §12.6.

### 10.5 Throughput

`[ESTIMATE]`, decode at batch 1 is bandwidth-bound: `tokens/s ≈ bandwidth ÷ weight_bytes × efficiency`, with the 0.50 efficiency factor from `compute-feasibility.md` §6.1. **Hosted (1× A100 80 GB, 2,039 GB/s):** bf16 2.299 GB → 443.5 tok/s; int8 1.222 GB → 834.8; Q4_K_M 0.703 GB → 1,449.9. On 1× H100 (3,350 GB/s): 728.7 / 1,370.9 / 2,382.4.

**Prefill** is FLOPs-bound (2N FLOPs/token): `[ESTIMATE]` 8,192 tokens on 1× A100 at 40% MFU = **0.151 s**; 32,768 tokens = **0.604 s**; on 8× A100, 32,768 tokens = 0.076 s. `[INFERRED]` Tensor parallelism does not help a prefill already under a second, so the hosted configuration should be sized for *concurrency* — a vLLM/SGLang continuous-batching decision.

**Speculative decoding** `[KNOWN FACT]` EAGLE (arXiv:2401.15077) and Medusa (arXiv:2401.10774), verified 2026-10-21. `[ESTIMATE]` a K0-scale draft model accepting at rate α gives a speedup ceiling of `1 + α/(1−α)`: α = 0.6 → 2.5×; 0.7 → 3.33×; 0.8 → 5.0×. `[UNKNOWN]` **The acceptance rate for a K0-drafted pass on a Config B target was not measured and no public figure was found.** A nice-to-have, not a plan dependency: §12.5 lists it as a revisit item, and it gates nothing.

### 10.6 The local laptop path

`[OBSERVED]` `compute-feasibility.md` §11.1: Ryzen 7 5700U, 8c/16t, **13.85 GiB RAM**, AMD iGPU with **2 GB VRAM**, **no CUDA**, torch 2.14.1+cpu, 159.2 GB free disk. `[OBSERVED]` measured on this machine 2026-10-21: memory bandwidth **8.48 GB/s**, FP32 GEMM **1.72 × 10¹¹ FLOP/s**.

`[ESTIMATE]`, Config B at 4-bit, batch 1, 8,192-token context:

| Format | Weights | + KV @ 8,192 | Resident | Ceiling (8.48 GB/s) | At 0.4 factor |
|---|---|---|---|---|---|
| Q4_K_M | 0.703 GB | 0.403 GB | 1.106 GB (1.030 GiB) | 7.67 tok/s | 3.07 tok/s |
| Q8_0 | 1.221 GB | 0.403 GB | 1.624 GB (1.512 GiB) | 5.22 tok/s | 2.09 tok/s |
| F16 | 2.299 GB | 0.403 GB | 2.701 GB (2.516 GiB) | 3.14 tok/s | 1.26 tok/s |

`[INFERRED]` **The main model fits in the laptop's RAM with room to spare, but it is a 3–8 tok/s instrument.** That is a usable rate for a local fallback, a smoke-test harness, a privacy-preserving offline mode and a demonstration — and it is *not* the interactive agent brain. The iGPU's 2 GB of VRAM cannot hold the bf16 weights alone (2.299 GB), so the iGPU is not a serving path at all. The 8.48 GB/s figure is the binding constraint, roughly 240× below a hosted A100, and no quantisation choice closes that gap.

**Training on the laptop is not viable.** `[ESTIMATE]` the training state at 18 bytes/parameter is 20.69 GB, which does not fit in 13.85 GiB; and at 20 tokens/parameter even at 10% of the measured 172 GFLOPS, a run takes **819 days**. The local machine is a *serving and evaluation* machine.

### 10.7 The K0 fallback model

> **Re-verification note.** The resident-memory and decode series in this section were re-derived independently by `research/spl/model_arch_verify.py` during the correction pass recorded in §0.3. Where an earlier draft of this section disagreed, the independently recomputed figures govern.

`[ESTIMATE]` **K0 = 100,683,264 parameters (0.101 B)**: L = 12, d = 768, ffn = 2,048, h_q = 12, h_kv = 4, head_dim = 64, vocab 32,768, tied, QK-norm. It is the *same architecture* as Config B at roughly 1/11 the parameter count, sharing the tokenizer, training code, runtime and grammar machinery — which is the whole point (R6).

`[ESTIMATE]` resident and decode at 8,192 context on the local machine: Q8_0 **0.193 GiB / 40.84 tok/s ceiling / 16.34 tok/s at the 0.4 factor**; Q6_K 0.171 GiB / 46.27 / 18.51; Q5_K_M 0.161 GiB / 49.17 / 19.67; Q4_K_M 0.151 GiB / 52.26 / 20.90; IQ4_XS 0.146 GiB / 54.08 / 21.63; F16 0.281 GiB / 28.08 / 11.23.

`[INFERRED]` **The K0 is the local path that actually works**: it fits in 193 MB, serves at 16–22 tok/s on the laptop, and at 32,768 context is still only ~0.7 GiB resident. The main model is the hosted model; K0 is the laptop model. `[ESTIMATE]` K0's training cost at 20 tokens/param is **6.77 A100 GPU-h attention-inclusive (2.71 GPU-h on the dense term alone), about $19** — cheap enough to train several variants, and this is the per-arm figure §13.2's Stage 1 uses.

### 10.8 The serving configuration summary

> **Correction carried from §0.3's re-verification pass.** Three figures elsewhere in this section are superseded by independently recomputed values and are restated here so the document has one authoritative series rather than two. (i) **§10.7's K0 resident-memory series**: the corrected figures are Q8_0 0.193 GiB, Q6_K 0.171 GiB, Q5_K_M 0.161 GiB, Q4_K_M 0.151 GiB, IQ4_XS 0.146 GiB and F16 0.281 GiB at an 8,192-token context, against the decode ceilings 40.84, 46.27, 49.17, 52.26, 54.08 and 28.08 tok/s respectively; the earlier draft's Q6_K and F16 entries were the two that disagreed. (ii) **§10.7's K0 training cost** is 6.77 A100 GPU-h attention-inclusive — 2.71 GPU-h on the dense term alone — which is the per-arm figure §13.2's Stage 1 table uses, not the earlier draft's 4.7 GPU-h. (iii) **§13.1's Stage-2 total** is 22,951 attention-inclusive for five runs, not the earlier draft's 20,290, and §13.3 is the itemised table. `[INFERRED]` These are corrections to a measurement-basis error, not to the architecture: the recommendation, its shape and its parameter budget are unchanged.

`[ESTIMATE]`: hosted runtime vLLM or SGLang, 1–8 GPUs, continuous batching, prefix caching on; hosted precision int8 weights + bf16 KV (int8 KV opt-in after §10.2's measurement); hosted window 32,768 default, 8,192 for latency-sensitive requests; local runtime llama.cpp, CPU-only + OpenBLAS, GGUF; local model K0 at Q8_0 or Q4_K_M, 8,192–32,768 context; grammar a standalone versioned file, server-side enforcement preferred and client-side sufficient; sampling with a fixed seed and temperature/top-p recorded per request (`AMB-206`).

---

## 11. Self-hosting and the chicken-and-egg problem

### 11.1 The problem, stated exactly

The project has a genuine circular dependency, and it is worth stating without euphemism:

- **The model is needed to build the agent.** The agent's competence is the model's competence. A 1.149 B model trained on 22.99 B tokens will be competent at a narrow slice of code work and weak at much else. The agent's quality ceiling is the model's, and no harness engineering raises it.
- **The agent is needed to build the model.** The corpus is produced and curated by tooling; the tokenizer is trained on a corpus the agent helps collect; the mid-training data (tool-call transcripts, FIM examples) is generated by the agent; the evaluation harness is written by the agent.

`[INFERRED]` This cannot be resolved by planning, only by *breaking the circle in stages and being explicit about which stage is bridged by a provider model*. The rest of this section is that plan.

### 11.2 The staged escape

| Stage | What exists | What is borrowed | What is ours | Bridge |
|---|---|---|---|---|
| **S0 — before any model** | the harness, the tool implementations, the evaluation and tokenizer harnesses, the adapter interface | a provider model (via the adapter) | all the code, the schemas, the measurement infrastructure | the provider adapter |
| **S1 — K0 trained** | K0 (0.101 B), local-serving capable | a provider model for anything K0 cannot do | K0's weights, the training pipeline, the tokenizer | the provider adapter, for tasks K0 fails |
| **S2 — Config B trained** | Config B (1.149 B), hosted-serving capable | nothing for the core loop | the full model | none for core tasks |
| **S3 — the model does the work** | the core loop runs on the project's own model | the provider only for tasks the own model demonstrably cannot do | the whole product path | the provider adapter, at the margin |

`[KNOWN FACT]` `llm-development-roadmap.md` §0.3 defines the same S0→S3 progression, and `AMB-306`/`AMB-307` set the acceptance bar: the own-model path must be **"not worse"** than the borrowed path on the metrics the borrowed path is used for, before the bridge is retired. `AMB-304` requires an own-model test.

### 11.3 The disclosure requirement — the part that cannot be softened

`[KNOWN FACT]` `AMB-001`: the existence of a provider adapter must never be represented as independent model intelligence. `[KNOWN FACT]` the project's standing constraint: **the product must use its own original code, assets and branding.**

`[INFERRED]` The operational form of this rule is a **capability declaration attached to every reported result**: any measurement produced while a provider model is behind the adapter is labelled with the model that produced it. Three consequences follow.

1. **No result may be attributed to the wrong model.** A metric measured on a provider model is a metric *about the provider model*; it may describe the harness's behaviour but never serve as evidence about the project's own model. `[KNOWN FACT]` `AMB-210` requires capability to be declared; `AMB-001` forbids the misrepresentation.
2. **The bridge must be visible in the product, not only in the documentation.** A user must be able to tell which model answered. `[INFERRED]` a product that silently mixes two models' outputs is worse than one that openly uses a borrowed model for a named subset of tasks, because the first kind cannot be evaluated.
3. **The retirement criterion is a measurement, not a date.** S1→S2 and S2→S3 retire a bridge when the own-model path is "not worse" on the metrics in question (`AMB-306`/`AMB-307`) — not when a date arrives, nor when the own model merely exists.

`[INFERRED]` The honest position: **the project can use a provider model temporarily, and doing so is legitimate engineering, provided it is labelled as such at every level — in the product, in the documentation, and in every number.** The illegitimate version is the one where the distinction is made only in a footnote.

### 11.4 The specific bootstrap dependencies

`[INFERRED]`, what the agent must exist to produce, and how each is obtained before the own model exists:

The **training corpus**, filtered and deduplicated, is needed for pretraining and bootstrapped with general-purpose tooling plus provider-model-assisted filtering, with the provenance recorded in `licensing-and-provenance-review.md`'s register. **FIM examples** for code mid-training are mechanical constructions from source files — no model required. **Tool-call transcripts** for the tool format are generated by the *harness* driving a model; the format is defined by the grammar regardless of which model produced the text. **Tool-result exemplars** come from running the real tools. The **evaluation harness** — every measurement in §13 — and the **tokenizer** are ordinary software.

`[INFERRED]` **The one genuinely model-dependent item is the corpus.** Everything else can be built mechanically — fortunate, because the corpus is also the item most subject to provenance review, and `licensing-and-provenance-review.md` §12 OPEN-Q1…Q5 remain open. `[INFERRED]` a conservative bootstrap — filtering with static heuristics rather than a model — trades some corpus quality for a cleaner provenance story, and that trade is worth making *before* the model exists, because it is very hard to unwind later.

### 11.5 What breaks if the plan is followed honestly

`[INFERRED]`, so it is not a surprise later: (i) the pre-model stages are slower and produce worse data than a well-funded team with a good model from day one would; (ii) the measurements in §13 are made against a *harness* whose agent loop is initially weak, so harness-side metrics have a floor the model cannot lift until S2; (iii) the "not worse" criterion (`AMB-306`) must be evaluated per-task, not globally, because the own model will be worse on some tasks for a long time and better on none until S2. S0 and S1 buy *infrastructure and provenance*; capability arrives at S2.

---

## 12. Alternatives rejected, and the conditions for revisiting them

| Alternative | Why not | Revisit when |
|---|---|---|
| **12.1 Mixture of Experts** | Costed in §3.2 and §4.7: on *active* params the MoE arm sees **0.41–0.54× the tokens** at equal wall-clock on the dense term, and **0.58×** attention-inclusive at a 32 K trained context — and the binding constraint is run count, not capacity. Load balancing adds a failure mode in a project premised on determinism, and decode becomes collective, worst at batch 1 | The MoE arm reaches "not worse" at *fewer* tokens (K5), or the project moves past the ~1 B band where capacity is worth the routing complexity |
| **12.2 Hybrid / recurrent (SSM, Mamba-like)** | Costed in §3.3: a class change, not the bottleneck; constrained-decoding support, which R1/R3/R5 require, is thinnest here; the state-vs-KV advantage arrives at 128 K+, not Stage I's 8 K / 32 K | The project commits to a trained context of 128 K+, where the 1,536× state-to-KV ratio (OPEN-A10) becomes decisive |
| **12.3 A code-specific, hand-built vocabulary** | Best raw code compression, but every non-code byte needs fallback handling, the vocabulary is rebuilt per language, and the maintenance burden is permanent | Measured code-slice compression (T1) shows the hand-built vocabulary materially beats the byte-level BPE on this corpus mix |
| **12.4 A larger vocabulary (49,152 / 65,536 / 131,072)** | The embedding matrix grows 1.5×/2×/4×, taking its share of N from 5.84% to 19.87% at 131,072; 131,072 also breaks uint16 token storage, doubling pipeline storage to 91.96 GB at 22.99 B tokens | The measured rare-token rate is high enough that the compression gain outweighs a 4× embedding cost — §13.5 |
| **12.5 Speculative decoding with a K0 draft model** | A nice-to-have, not a dependency: a separate checkpoint and training run. The speedup ceiling is `1 + α/(1−α)`, but α for a K0-drafted pass on a Config B target is `[UNKNOWN]` (OPEN-A6) | A trained K0 exists, its acceptance rate is measured, and the speedup is worth the extra checkpoint |
| **12.6 Quantization-aware training** | `[SPECULATIVE]` deliberately not in the base plan: a second training run, while the measurement budget (§13) is better spent on the architecture questions | The 4-bit gate (§10.4) fails — the 4-bit arm more than 2.0 pp worse than int8 on the primary metric — and retraining is cheaper than shipping a lossy model |
| **12.7 Untied embeddings** | Would cost +67,108,864 parameters (+5.84%). Tying is the right default at 1.15 B, but the quality difference should be measured, not assumed (§4.2) | The tied-vs-untied arm shows a difference at the 5.0 pp materiality bar |
| **12.8 A larger main model (R3 and above)** | R3 is 7 B — 6.1× the parameters, and ~37× the cost on the dense term / ~22× attention-inclusive at a 32 K trained context (68 d / $36,514 dense-term; 152 d / $81,322 attention-inclusive) per run on 8× A100. The binding constraint is iteration count (§1.2 Reason 2), so a larger model buys fewer experiments, not better ones | The binding constraint changes — e.g. a fixed evaluation deadline — or the R2 band is shown to be capability-limited, not harness-limited |

## 13. The measurement plan for the architecture itself

> **Correction carried from §0.3's re-verification pass.** Two cells of the table above were computed on the dense term alone while the surrounding prose was attention-inclusive, and are restated here as the authoritative figures. (i) **12.8 (R3 and above)**: an R3-sized 7 B run costs 68 days and $36,514 on the dense term, and 152 days and $81,322 attention-inclusive at a 32 K trained context — that is ~37× and ~22× the recommendation's cost respectively, not the earlier draft's "~6× the cost, ~29 days". (ii) **12.1 (Mixture of Experts)**: on *active* parameters the MoE arm sees 0.41–0.54× the dense arm's tokens at equal wall-clock on the dense term, and 0.58× attention-inclusive at a 32 K trained context — the MoE arm's relative advantage *shrinks* once the attention term is counted, because its attention stack is unchanged while its MLP is sparse. `[INFERRED]` Neither correction changes any alternative's verdict; both make the *margins* narrower and are therefore stated rather than smoothed.

### 13.1 Purpose, and the materiality bar

The plan's purpose is to **prove each choice in this document was right, or find that it was wrong**. It is not a demonstration plan: no arm is expected to win, and an arm that loses changes the recommendation.

`[KNOWN FACT]` the materiality bar, from `benchmark-and-evaluation-plan.md` §10.3: a difference counts only at **≥ 5.0 percentage points**, with the **95% confidence interval excluding zero**, and **Holm-corrected p < 0.05**. A difference below that bar is not evidence of no difference; it is evidence that the measurement cannot resolve it, and it must be reported as such.

`[INFERRED]` Two-stage structure: **Stage 1** runs a cheap K0-scale pre-screen whose cost is a small fraction of one Config B run, so a hypothesis can be falsified before a four-figure commitment is made; **Stage 2** runs the confirmatory arms at Config B scale, itemised per arm in §13.3. A null result at K0 scale is a reason to escalate, not to conclude (§13.7).

### 13.2 Stage 1 — the K0 pre-screen (13 arm rows, 15 runs, $283)

`[ESTIMATE]` K0 = 100,683,264 parameters; 20 tokens/parameter → 2.01 B tokens. Costed on the **attention-inclusive** basis consistent with §6.4 (K0 geometry, L = 12, d = 768, trained context 8,192): `6ND` = 1.216 × 10¹⁸ FLOPs → 2.71 A100 GPU-h; attention term 1.824 × 10¹⁸ → **6.77 A100 GPU-h → $18.88 per arm**.

| Arm | Hypothesis tested | Control? | A100 GPU-h | Cost |
|---|---|---|---|---|
| S1.0 | K0 baseline (Config B architecture, scaled) | baseline | 6.77 | $18.88 |
| S1.1 | vocab 16,384 vs 32,768 | no | 5.63 | $15.70 |
| S1.2 | GQA 4:1 vs MHA 1:1 (h_kv 4 → 12) | no | 7.68 | $21.43 |
| S1.3 | QK-norm on vs off | no | 6.77 | $18.88 |
| S1.4 | RoPE vs ALiBi | no | 6.77 | $18.88 |
| S1.5 / S1.6 | FIM objective **off** / **on** | **S1.5 controls S1.6** | 6.77 × 2 | $37.76 |
| S1.7 / S1.8 | tool-call format: JSON-in-prose / sentinel + grammar-constrained | **S1.7 controls S1.8** | 6.77 × 2 | $37.76 |
| S1.9 | fp32 master weights vs bf16 master | no | 6.77 | $18.88 |
| S1.10 | depth 12 vs 20 at constant N (L = 20, ffn 956 → N 100,708,864, +0.03%) | no | 6.77 | $18.89 |
| S1.11 | token budget 20 vs 50 tokens/parameter | no | 16.92 | $47.21 |
| S1.12 | gradient-clip threshold sweep (0.5 / 1.0 / 2.0) | no | 6.77 × 3 | $56.64 |

`[ESTIMATE]` **Stage 1 total: 15 runs, 101 A100 GPU-h, $283** on A100 (0.53 d serial on 8 × A100), or **$707** with a 2.5× failed-run multiplier. On the dense term alone the same 15 runs would cost $113 — the difference is the attention term, and §0.3 explains why the larger figure is the one used. `[INFERRED]` **MoE is deliberately excluded from Stage 1.** Its load-balancing behaviour does not reproduce at K0 scale — router collapse and expert-specialisation effects are scale-dependent, so a null K0 result would say nothing about the Config B MoE arm. The MoE arm is therefore a Stage-2 arm only (§13.3), where the cost is justified.

### 13.3 Stage 2 — the Config B arms (5 runs, $22,951)

`[ESTIMATE]` Config B = 1,149,343,744 parameters. **Costed on the attention-inclusive basis** (§0.3, §6.4): each arm's cost depends on the context it is *trained at*, which is why the column is not a constant.

| Arm | What it is | Trained ctx | A100 GPU-h | 8×A100 wall | Cost |
|---|---|---|---|---|---|
| S2.1 | MoE, E = 8, ffn_e = 1408, top-2, matched to active params (0.735 B active / 1.980 B total) | 32,768 | 776 | 4.04 d | $2,165 |
| S2.2 | Config B at 8,192 trained context | 8,192 | 600 | 3.13 d | $1,674 |
| S2.3 | **Config B baseline, 32,768 trained context** (the shared baseline) | 32,768 | 1,342 | 6.99 d | $3,743 |
| S2.4 | Config B at 131,072 trained context, 10 tokens/parameter | 131,072 | 2,154 | 11.22 d | $6,010 |
| S2.5 | Config B, 50 tokens/parameter | 32,768 | 3,354 | 17.47 d | $9,358 |
| | **Stage 2 total** | | **8,226** | **42.8 d** | **$22,951** |

(S2.3 is the shared baseline; it replaces the earlier S2.0/S2.3 duplicate row.)

`[ESTIMATE]` with a 2.5× failed-run multiplier: **$57,377**. **Grand total (Stage 1 + Stage 2): $23,234, or $58,084 with the multiplier.**

`[INFERRED]` Note what S2.1's cost means. The MoE arm costs **$2,165 against the dense baseline's $3,743** — 58% of it — because its active-parameter count is 0.735 B, so it sees fewer tokens in the same wall-clock (§4.7). The arm is affordable; the question it answers is whether the token deficit matters more than the architecture does. Hence it must run at Config B scale and be compared on the *primary metric at equal wall-clock*, not on the same number of tokens — a same-token comparison would let the MoE arm spend 1.58× the FLOPs and would not answer the question the project has.

### 13.4 The context-length scaling curve

`[ESTIMATE]` arms S2.2 (8 K), S2.3 (32 K) and S2.4 (128 K at half the token budget) give three points on the curve. S2.4's reduced token budget is deliberate: at 128 K the attention term is 11.21× of `6N` (§6.4), so a full-token 128 K run would cost 4,308 A100 GPU-h (22.44 d, $12,020) — S2.4's reduced budget brings it to 2,154 GPU-h (11.22 d, $6,010).

**What is measured:** not the nominal window but the **effective context** — the largest span over which retrieval accuracy stays within 2.0 pp of the short-context result, measured with RULER-style probes (arXiv:2404.06654) at multiple depths: information placed at the beginning, the middle, and the end of the window. `[KNOWN FACT]` the mid-window failure this measures is documented in "Lost in the Middle" (arXiv:2307.03172). **The gate:** the trained context must deliver a 16,384-token effective context at a 32,768-token nominal window. `[INFERRED]` If the 32 K model achieves only an 8 K effective context, the recommendation's context claim is wrong and the trained context should fall to 16 K, saving both the attention term and the activation memory.

### 13.5 The tokenizer ablation

Two halves, cheapest first. **Half one (free):** the tokenizer harness itself — T1–T9 (§5.7) — measures compression, round-trip fidelity and identifier fragmentation on the actual corpus with no training at all, and can invalidate the tokenizer choice before half two starts. **Half two:** train at vocab 16,384 (S1.1 at K0, then a Config B arm if the K0 result is ambiguous) against the 32,768 baseline. **What would settle it:** the measured tokens/byte on the code slice (T1) and the primary metric. `[INFERRED]` a tokenizer that wins on tokens/byte but loses on the primary metric is *not* the better tokenizer — the compression saving only pays if it does not cost capability.

### 13.6 The output-format ablation

`[ESTIMATE]` arms S1.5/S1.6 (FIM on/off) and S1.7/S1.8 (JSON-in-prose vs sentinel+grammar), plus a Config B confirmation.

**The measurement, and the trap in it.** The obvious metric — "does the constrained arm produce fewer malformed calls?" — **measures the grammar engine, not the model**, because the grammar makes malformed calls *impossible* to emit. That metric is guaranteed to favour the constrained arm and says nothing about the model.

`[INFERRED]` The correct measurement is a **three-way decomposition**: (1) *well-formed but wrong* — the call parses and passes the schema but names the wrong tool or arguments, the model's error mass and the metric that matters; (2) *malformed* — unparseable output, reported for the control arm and near-zero by construction for the constrained arm; (3) *total failure* — the sum.

The comparison that means something: **well-formed-but-wrong error mass at equal schema (byte-identical per `AMB-203`) between the sentinel arm and the JSON-in-prose arm.** `[INFERRED]` If the sentinel arm's mass is *higher* than the control's, the format is costing the model capability that the grammar hides — exactly the failure the "malformed calls" metric would have concealed. `[KNOWN FACT]` §9.4 of `benchmark-and-evaluation-plan.md` requires the harness variant to travel with the score, so the harness is held identical across both arms.

### 13.7 The precision and stability ablation

`[ESTIMATE]` arms S1.3 (QK-norm), S1.9 (fp32 master), S1.12 (clip threshold sweep), plus a Config B confirmation of QK-norm.

**Beyond the primary metric**, each arm is read against the §8.4 detection quantities: max attention logit, the per-head output-variance histogram, the fraction of steps clipped, and the loss curve. `[INFERRED]` **The head-collapse check is the reason this arm exists.** A run can complete with a plausible loss curve while half its heads have collapsed — a failure a single scalar metric will not reveal, and that would invalidate every downstream comparison.

**The escalation rule.** `[INFERRED]` A null result at K0 scale is a reason to **escalate**, not to conclude. A stability effect that appears only above a certain scale — loss spikes, head collapse, logit blow-up — is exactly the kind of thing invisible at 0.1 B and fatal at 1.15 B. So a null result for QK-norm, clipping or precision at K0 scale is re-run at Config B scale before being treated as a finding; a K0-scale *positive* result is a reason to prefer the arm, not a substitute for the Config B confirmation.

### 13.8 The shape arm

`[ESTIMATE]` depth 12 vs 20 at constant N (S1.10), and the 24L/2,048 vs 32L/1,792 comparison from §4.4 at Config B scale. **What it settles:** the depth/width question that §4.4 records as `[UNKNOWN]`, and the choice between the Config B shape and the earlier `K1` shape (§4.1). `[INFERRED]` This arm exists so that the shape is settled by measurement rather than by the accident that the roadmap committed to it first.

### 13.9 What this plan cannot answer

`[INFERRED]`, so the plan is not over-read: it **cannot predict frontier-level performance** (the largest arm is 1.149 B on 22.99 B tokens; no arm produces a frontier model and none is claimed); it **cannot measure long-horizon agentic competence** (it measures single-request behaviour — tool-call fidelity, context use, format adherence — while a 50-step agent is an emergent property of harness plus model); it **cannot isolate the data** (the corpus is fixed across all arms); it **cannot settle the tokenizer's absolute quality** (it compares tokenizers within this corpus, not against the code the agent will be asked about); and it **cannot measure the harness's ceiling** (weak retrieval or chunking makes a context arm measure the harness as much as the model).

### 13.10 Kill criteria

`[INFERRED]`, the conditions under which an arm is abandoned or the plan is restructured, stated in advance so that abandoning an arm is a pre-registered decision rather than a post-hoc one:

| # | Criterion | Action |
|---|---|---|
| K1 | Stage 1 total exceeds $750, or Stage 2 exceeds $58,000 (both at 2.5× the point estimate) | restructure the plan; do not silently continue |
| K2 | MFU below 25% on a Config B run | stop; fix the training stack first — `[KNOWN FACT]` `llm-development-roadmap.md` Stage A's kill criterion |
| K3 | The 32 K run cannot reach an effective context of 16,384 (§13.4) | reduce the trained context to 16 K |
| K4 | The sentinel format's well-formed-but-wrong mass exceeds the control's by ≥ 5.0 pp | the format is costing capability; redesign it and re-run |
| K5 | The MoE arm reaches "not worse" at *fewer* tokens than dense | §12.1's revisit condition fires; MoE becomes the recommendation |
| K6 | Head collapse is observed in a Config B run | the stability recipe is wrong; fix before any comparison is trusted |
| K7 | Two consecutive Config B runs fail to beat the K0 baseline on the primary metric | the bottleneck is not the architecture; re-examine the data and the harness before a third |

### 13.11 Schedule

`[ESTIMATE]`, serial on 8× A100, one run at a time, attention-inclusive costs: (1) tokenizer build + harness T1–T9, 2–5 days CPU-only, ~$0; (2) Stage 1, 15 K0 runs at 101 A100 GPU-h ≈ 0.53 d, $283–$707; (3) S2.3, the Config B baseline, 6.99 d, $3,743; (4) S2.1, S2.2, S2.4, ~18.4 d, $9,849; (5) S2.5, 17.47 d, $9,358. **Total (serial): ~47 days point estimate, $23,234; ~117 days and $58,084 if every run fails and must be retried at the 2.5× multiplier.**

`[INFERRED]` **The serial long pole is ~47 days.** Measured against the annual run budget: a 32 K-trained Config B run takes 6.99 d, so the year holds **52 such runs**, and the plan is **6.7 of them**; at an 8 K trained context (3.13 d, 117 runs/yr) it is **15.0 of them**. The plan's share is real but tolerable, and it is the right share to spend, because these measurements determine whether the remaining ~46 runs are spent on the right architecture.

`[INFERRED]` **What the correction in §0.3 cost, stated honestly.** On the dense term alone this plan was 14 days and $5,651. The attention-inclusive figure is **47 days and $23,234** — 3.3× the days and 4.1× the dollars. That difference is not a change in the architecture; it is the recognition that a run *trained at* a given context pays an attention cost proportional to that context, and that the earlier table priced 32 K-trained runs as if they were 8 K-trained ones. `[UNKNOWN]` The single largest remaining uncertainty in this budget is not the arithmetic but the attention constant itself: the 12·L·d·Q factor assumes full quadratic attention, and a causal kernel that skips the masked half would roughly halve the attention term (§6.4), taking the plan to ~28 days and ~$14,500. **What would settle it:** one measured Config B run at 32 K with a causal-attention kernel, recording achieved MFU — which is the same measurement as Stage A's MFU kill criterion (K2).

---

## 14. Open questions


Every item here is `[UNKNOWN]` in the sense of §0.1: not determinable from the material examined, and **no public figure was found for any of them**. Each names what would settle it.

| # | Question (all `[UNKNOWN]` unless marked) | Settled by |
|---|---|---|
| OPEN-A1 | Vocabulary 32,000 (`training-data-plan.md` §7.1) or 32,768 (`llm-development-roadmap.md` §1.4)? **Adopted 32,768**; ±1,572,864 parameters | a single recorded decision across both documents, plus §13.5 |
| OPEN-A2 | Tokens/byte rate on this project's corpus mix? Placeholders 0.22 (JSON) / 0.28 (code) are not measurements | harness T1–T3 |
| OPEN-A3 | Optimal global gradient-clip threshold for this corpus? | §13.7 arm S1.12 |
| OPEN-A4 | 24L/2,048 or 32L/1,792 at ~1.15 B on code? | §13.8 |
| OPEN-A5 | Wall-clock and cost of fitting a 32,768-token byte-level BPE over a 30–50 GB corpus? | measurement on the available hardware before the tokenizer is built |
| OPEN-A6 | Acceptance rate of a K0-drafted speculative-decoding pass on the Config B target? | measured after a trained K0 exists (§12.5) |
| OPEN-A7 | Quality cost of int8 / int4 KV-cache quantisation on a code model? | §10.2's gated KV arm, against the int8 baseline |
| OPEN-A8 | llama.cpp's measured throughput on this machine's AMD iGPU? its 2 GB cannot hold the bf16 weights alone | measurement on this machine, if the iGPU path is pursued |
| OPEN-A9 | TP=8 communication-overhead factor for this model? | measurement on 8× A100; §10.5 assumes bandwidth scales linearly |
| OPEN-A10 | A hybrid/SSM configuration matched *exactly* to 1.149 B? the §4.7 hybrid lands at 1.033 B | costing a matched configuration before §12.2's revisit condition can be evaluated |
| OPEN-A11 | Any published MoE-vs-dense comparison at ~1 B on a code corpus? | literature re-check at Stage 2; §13.3's S2.1 settles it internally |
| OPEN-A12 | Effective context of a 1.15 B code model at 32 K? | §13.4's scaling curve and the 16,384 gate |
| OPEN-A13 | Run-to-run variation from non-deterministic kernels? | repeating one Config B run and comparing loss curves (§9.3) |

`[INFERRED]` **None of these blocks the recommendation.** OPEN-A1 needs a decision, not a measurement, and is decided here (32,768). The rest are inputs to §13's measurement plan or to later stages; the architecture choice rests on grounds that do not depend on their answers — the property a proposal should have: actionable before its open questions are closed.

---

## 15. One-page summary

**Recommendation.** A 1,149,343,744-parameter decoder-only dense transformer — 24 layers, d_model 2,048, SwiGLU ffn 5,632, GQA 16 query / 4 KV heads of head_dim 128, QK-norm, RMSNorm pre-norm, tied embeddings, byte-level BPE at 32,768 — trained on 22.99 B tokens to a 32,768-token context; served through llama.cpp locally (K0 at Q8_0) and vLLM/SGLang hosted (int8 default, 4-bit gated); tool calls sentinel-delimited and grammar-constrained, so the harness either accepts a call or rejects it, never repairs one (`AMB-204`).

**Why.** (1) It is the configuration the parallel documents already committed to, and the arithmetic confirms it. (2) At 1.15 B the binding constraint is iteration count (52 runs/year at a 32 K trained context, 117 at 8 K), and dense minimises it. (3) The tool-call contract can be made deterministic — a valid call or a hard rejection, never a repair.

**Cost.** Attention-inclusive (§6.4): **600 A100 GPU-h per run at an 8 K trained context (3.13 d, $1,674)** and **1,342 GPU-h at 32 K (6.99 d, $3,743)**; the dense `6ND` term alone is 353 GPU-h ($984) and is not a training cost at any context. The measurement plan is the larger spend: **$23,234** for 13 K0 pre-screen arms plus 5 Config B arms, **$58,084** with the 2.5× failed-run multiplier, **~47 days serial** — about 7 of the 52 annual 32 K runs, or 15 of the 117 annual 8 K runs.

**Not chosen.** MoE (0.41–0.54× the tokens at matched wall-clock; a load-balancing failure mode) and SSM/hybrid (a class change whose KV/state advantage arrives at 128 K+, thinnest constrained-decoding support). Untied embeddings, larger vocabularies, a code-specific vocabulary, speculative decoding and quantization-aware training each have a revisit condition in §12.

**Biggest unknown.** Every performance figure: no benchmark of this architecture exists because the model does not exist. The largest single risk is not architectural but the corpus and the harness, neither of which this document can measure. Thirteen open questions are in §14; none blocks the recommendation.


---


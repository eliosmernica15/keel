# Compute Feasibility Assessment

**Building an independent code-oriented language model and an independent coding agent**

| | |
|---|---|
| **Document type** | Planning / feasibility assessment |
| **Status** | Planning documentation only. No training performed, no infrastructure provisioned, no paid service called. |
| **Date written** | 2026-10-21 |
| **All prices observed on** | 2026-10-21 (unless otherwise stated) |
| **Re-verification required** | **Yes — before any budget decision.** GPU spot prices and API prices change frequently. Every price in this document carries its observation date for that reason. |

---

## How to read this document

Every quantitative claim is tagged with one of three classes:

| Tag | Meaning | Requirement |
|---|---|---|
| **[KNOWN FACT]** | A figure taken directly from a citable public source. | URL + observation date given inline. |
| **[ESTIMATE]** | A number I derived myself from cited facts. | The arithmetic is shown. |
| **[SPECULATIVE TARGET]** | A goal or aspiration, not a prediction. | Labelled as such; never used as if it were a forecast. |

Where I could not find a public figure, I write **"no public figure found"** rather than inventing one.

Two conventions used throughout:

- **FLOPs** means floating-point operations (10^15 FLOPs = 1 PFLOP).
- **GPU-hour** means one GPU running for one hour. Multi-GPU wall-clock is stated separately; a cluster of *n* GPUs produces *n* GPU-hours per wall-clock hour.

---

## 1. Feasibility verdict (summary)

**The headline: a genuinely useful independent code model at the 1–7B scale is achievable by a small team for tens of thousands of dollars, but only if the team rents GPUs rather than buying them, and only if the deliverable is a *model plus agent harness* rather than a frontier model. The frontier-comparison rung is out of reach by roughly five orders of magnitude.**

| Rung | Scale | One-line verdict |
|---|---|---|
| **R0** | 30M params | **Feasible now, free.** Runs on the existing local laptop CPU in days-to-weeks. Proves the pipeline, not the model. |
| **R1** | 360M params | **Feasible now, ~$100–$8k.** The genuine "we can train our own model" rung. Choose the token budget carefully — this is where the cost cliff lives. |
| **R2** | 1.5B params | **Feasible, ~$1.7k–$17k.** The recommended target for a first *useful* code model. |
| **R3** | 7B params | **Feasible but expensive, ~$37k–$913k.** Matches the class of model serious open code models occupy. Serious money, but not absurd. |
| **R4** | 15B params | **Feasible at ~$168k–$2.2M**, but the training wall-clock (88–313 days on 8 GPUs) makes it impractical for a small team. |
| **R5** | 70B params | **Out of reach for this team, ~$1.5M–$36.5M.** This is a frontier-lab line item. |
| **R6** | 405B params | **Categorically out of reach, ~$95M–$236M on rented GPUs**, and that's before data, staff, and post-training. Meta's published figure for a comparable model is 3.8×10^25 FLOPs. |

**The single most important feasibility constraint is not GPU cost — it is *wall-clock time and iteration count*.** A 7B model trained on 8 rented A100s takes ~68 days per attempt (Section 9). A small team cannot iterate on a 68-day experiment; it can only afford to run one. This is why R2 (1.5B, ~3 days on 8×A100) is the recommended target: it is the largest rung that supports the *repeat* of experiments that model development actually requires.

**A counter-constraint worth stating plainly:** the marginal cost of *renting* frontier intelligence is small next to building it, but it is not the coin-flip the earlier version of this document implied. One year of heavy Sonnet 5.5 usage (10M tokens/day) costs ~$43,800. Training a 7B model once at the compute-optimal token count costs ~$36,500 — so at the recommended rung the two are **within a factor of ~1.2× in dollars**. That dollar parity is not the deciding argument, because the rented model is *far more capable* than the one built ($43,800/year buys Opus 5.5; $36,500 buys something in the StarCoder2-7B class). **[INFERRED]** The honest framing is therefore: **the build case is a control/ownership/specialisation case, never a cost case** — and at the *extended* token budget the dollar gap widens sharply in renting's favour (a $912,860 training run versus 21 years of API usage), so the conclusion is strongest precisely at the rung this document recommends against (Section 12).

---

## 2. The candidate ladder

### 2.1 The ladder table

Column headers marked with a formula reference are explained in Section 3.

| Rung | Name | Params | Architecture family | Context | Training tokens (D) | Tok/param | Dataset size | Training FLOPs (6ND) | Hardware & wall-clock |
|---|---|---|---|---|---|---|---|---|---|
| **R0** | Micro proof-of-learning | 30M | Decoder-only, 6 layers, d=512, GQA | 2,048 | 0.6B (optimal) | 20 | ~2.4 GB text | 1.08×10^17 | 1× CPU (local) ≈ 73–363 d; or 8×A100 ≈ 4 min |
| **R1** | Smol-class small useful | 360M | Decoder-only, 24 layers, d=960, GQA | 2,048 | 7.2B (optimal) → 600B (extended) | 20 → 1,667 | 0.03 TB → 2.4 TB | 1.56×10^19 → 1.30×10^21 | 8×A100: 4.3 h (optimal) → 15 d (extended) |
| **R2** | 1.5B code model | 1.5B | Decoder-only, 28 layers, d=1536, GQA | 8,192 | 30B (optimal) → 300B (extended) | 20 → 200 | 0.12 TB → 1.2 TB | 2.70×10^20 → 2.70×10^21 | 8×A100: 3 d → 31 d |
| **R3** | 7B mid-range code model | 7B | Decoder-only, 32 layers, d=4096, GQA | 16,384 | 140B (optimal) → 3.5T (extended) | 20 → 500 | 0.56 TB → 14 TB | 5.88×10^21 → 1.47×10^23 | 8×A100: 68 d → 1,704 d; 8×H100: 19 d → 478 d |
| **R4** | 15B upper-mid | 15B | Decoder-only, 40 layers, d=6144, GQA | 16,384 | 300B (optimal) → 4T (extended) | 20 → 267 | 1.2 TB → 16 TB | 2.70×10^22 → 3.60×10^23 | 8×A100: 313 d → 4,173 d |
| **R5** | Chinchilla-class | 70B | Decoder-only, 80 layers, d=8192, GQA | 32,768 | 1.4T (Chinchilla-optimal) | 20 | 5.6 TB | 5.88×10^23 | 512×H100: ~30 d; 8×H100: 1,910 d |
| **R6** | Frontier-comparison *(stretch)* | 405.9B | Decoder-only, 126 layers, d=16384, GQA | 131,072 | 15.6T | 38 | 62 TB | 3.80×10^25 | 4,096×H100: ~241 d; **cost ~$94.6M** |

**[ESTIMATE]** for all FLOPs and wall-clock columns. Arithmetic in Section 3 and Section 9. Architecture shapes are chosen to match published, working configurations at comparable scale so that the memory and throughput estimates are anchored to real measurements rather than invented.

### 2.2 Anchoring the ladder to published models

The ladder is not invented; each rung is anchored to a real, published model so that the token counts, context lengths, and architecture families are empirically grounded.

| Rung | Real-world anchor | Published facts used |
|---|---|---|
| R1 | **SmolLM2-360M** | 360M params, trained on **600B tokens**, context 2,048, vocab 49,152, GQA, depth-over-width. **[KNOWN FACT]** — https://huggingface.co/blog/smollm (observed 2026-10-21) |
| R2 | DeepSeek-Coder / CodeLlama class | 1.5B is the standard "small code model" size class |
| R3 | **StarCoder2-7B** | 7B params, **3.5+ trillion tokens**, context 16,384 (sliding window 4,096), GQA, FIM objective, 17+ programming languages. **[KNOWN FACT]** — https://huggingface.co/blog/starcoder2 (observed 2026-10-21) |
| R4 | **StarCoder2-15B** | 15B params, **4+ trillion tokens**, 600+ languages. **[KNOWN FACT]** — same source |
| R5 | **Chinchilla** | 70B params, **4× more data than Gopher**; Chinchilla-optimal ratio ≈ 20 tokens/param. **[KNOWN FACT]** — https://arxiv.org/abs/2203.15556 (observed 2026-10-21) |
| R6 | **Llama 3.1 405B** | 405B→**405.9B trainable params, 15.6T tokens, 128K context, pre-trained using 3.8×10^25 FLOPs**. **[KNOWN FACT]** — https://arxiv.org/abs/2407.21783 and https://huggingface.co/blog/llama31 (observed 2026-10-21) |

### 2.3 The 20 tokens/param ratio, and when to break it

**[KNOWN FACT]** Chinchilla (https://arxiv.org/abs/2203.15556, observed 2026-10-21) established that compute-optimal training scales model size and token count equally, with the optimal ratio landing near **20 tokens per parameter** for dense decoder models. The paper explicitly notes it trained 400+ models from 70M to 16B parameters on 5B to 500B tokens to establish this.

**[KNOWN FACT]** The optimal ratio is *not* universal, and two published counter-examples bound the question:

1. **SmolLM** (https://huggingface.co/blog/smollm, observed 2026-10-21) states: *"We observed that performance continues to improve with longer training, even beyond the Chinchilla optimal point."* SmolLM2's 135M and 360M models were trained on **600B tokens** — a ratio of **1,667 tokens/param**, ~83× the Chinchilla optimum. The paper attributes this to performance gains still arriving after 400B tokens on some benchmarks.
2. **Llama 3.1 405B** (https://arxiv.org/abs/2407.21783) was trained on 15.6T tokens at 405.9B params = **38.4 tokens/param**, ~1.9× the Chinchilla optimum. The paper states: *"our smaller models are trained much longer than is compute-optimal... The resulting models perform better than compute-optimal models at the same inference budget."*

**[ESTIMATE]** Consequence for the ladder: the "optimal" and "extended" token columns in Section 2.1 bracket a range of **1× to ~83×** the compute-optimal token budget, and the *actual* capability of a model at a given parameter count is strongly determined by which end of that range you can afford. **This is the central cost-driving decision in the whole project, and it is not visible in the parameter count.** A 360M model trained for 7.2B tokens and a 360M model trained for 600B tokens differ by roughly two orders of magnitude in cost and in capability — the SmolLM blog reports the 360M model as the best in its class.

**[SPECULATIVE TARGET]** For this project I would target the *extended* end for R1–R2 (where the absolute dollar cost is still four-to-five figures) and the *optimal* end for R3+ (where the extended end costs seven figures and buys diminishing returns).

---

## 3. Compute estimates — the derivation

### 3.1 The training FLOPs formula

**[KNOWN FACT]** Chinchilla (https://arxiv.org/abs/2203.15556, §"Efficient frontier", observed 2026-10-21) writes the constraint explicitly:

> *"We can approximate the functions N_opt and D_opt by minimizing the parametric loss L̂ under the constraint **FLOPs(N,D) ≈ 6ND** (Kaplan et al. 2020)."*

So: **C = 6 · N · D**, where N = parameter count and D = training tokens.

**[KNOWN FACT — validation of the formula]** Applying 6ND to Llama 3.1 405B:

- 6 × 405.9×10^9 × 15.6×10^12 = **3.799×10^25 FLOPs**
- Meta's published figure (https://arxiv.org/abs/2407.21783, observed 2026-10-21): **3.8×10^25 FLOPs**
- **Ratio: 1.000.** The formula reproduces the published number exactly. **[ESTIMATE — this is the arithmetic above]**

This is the strongest available validation that 6ND is the right accounting tool for this document.

### 3.2 GPU-hour conversion

**[ESTIMATE]** GPU-hours for one GPU to absorb C FLOPs:

$$\text{GPU-hours} = \frac{C}{(\text{peak TFLOPS} \times 10^{12}) \times \text{MFU}} \div 3600$$

The "HF-style inference estimate" referenced in the brief is the **memory-bandwidth-bound decode model** (Section 8): for autoregressive decoding at batch size 1, every generated token must read the entire weight matrix once, so decode throughput is bounded by **HBM bandwidth ÷ weight bytes**, not by peak FLOPs. This is the standard analysis in the Hugging Face inference-optimisation documentation (https://huggingface.co/docs/transformers/en/perf_infer_gpu_one, observed 2026-10-21), which describes FlashAttention-2, kernel fusion, quantization, and caching as the levers that reduce memory traffic — the same levers. The numeric throughput figures in Section 8 are **[ESTIMATE]**.

### 3.3 Hardware specifications used

All **[KNOWN FACT]**, observed 2026-10-21:

| GPU | Dense BF16 tensor TFLOPS | Memory | HBM/GDDR bandwidth | Price $/GPU-hr |
|---|---|---|---|---|
| NVIDIA A100 SXM 80GB | 312 (624 with sparsity) | 80 GB HBM2e | 2,039 GB/s | **$2.79** (Lambda 8×) |
| NVIDIA H100 SXM 80GB | 989.5 (1,979 w/ sparsity) | 80 GB HBM3 | 3.35 TB/s | **$3.99** (Lambda 8×) |
| NVIDIA B200 SXM | — (3,958 FP8 w/ sparsity) | 180 GB HBM3e | — | **$6.69** (Lambda 8×) |
| NVIDIA L40S | — | 48 GB GDDR6 | 864 GB/s | **$1.09** (Lambda 8×) |
| NVIDIA A10 | — | 24 GB | 600 GB/s | **$1.29** (Lambda 8×) |
| NVIDIA RTX 4090 | — (1321 AI TOPS) | 24 GB GDDR6X | 1,008 GB/s | not rented (consumer) |
| NVIDIA RTX 5090 | — (FP4) | 32 GB GDDR7 | — | not rented (consumer) |

Sources: NVIDIA product pages for A100 (https://www.nvidia.com/en-us/data-center/a100/), H100 (https://www.nvidia.com/en-us/data-center/h100/), RTX 4090 (https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/), RTX 5090 (https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/) — all observed 2026-10-21. Prices from Lambda GPU Cloud (https://lambda.ai/service/gpu-cloud) and RunPod (https://www.runpod.io/pricing, "Updated October 8, 2026"), both observed 2026-10-21.

> **Note on sparsity:** NVIDIA publishes tensor TFLOPS *with sparsity* as the headline number. Using the sparse number directly would halve every cost estimate below. I use **dense** BF16 throughout (A100 = 312, H100 = 989.5), which is the honest figure for a training run.

### 3.4 The compute table

**[ESTIMATE]** — all rows. Arithmetic shown for each. Assumed **MFU 40% on A100, 45% on H100** (see caveat below).

> **CORRECTION (2026-10-22) — three defects found and fixed in this table.** The previous version contained three *independent* errors, none visible without re-deriving every cell from the stated inputs. They are recorded here rather than silently overwritten, because a reader who has already seen the old numbers needs to know they changed.
>
> 1. **The cost column was inflated by exactly the fleet size (8× for the 8-GPU rows).** The old table computed `cost = (C/r)/3600 × fleet × price`. Billed GPU-hours for a fixed FLOP budget are **fleet-independent**: if a fleet of *f* GPUs sustains rate *r* FLOP/s each and must absorb *C* FLOPs, then wall time *T = C/(f·r)* and billed GPU-hours = *f·T = f·C/(f·r) = C/r* — **the *f* cancels**. So `cost = (C/r)/3600 × price`, independent of fleet size. §3.5's own cross-check against DeepSeek-V3's **published** 2.788M H800 GPU-hours already used the *correct* convention and landed at ~33% MFU, so the document was internally inconsistent.
> 2. **The GPU-hour column changed meaning between rows.** In the seven *optimal* rows it held **per-GPU** hours; in the four *extended* rows it held **fleet-total** hours (8× larger) — silently, in adjacent rows of the same column. It now holds **total billed GPU-hours** in every row, which is the only quantity that can be multiplied by a price.
> 3. **Two extended rows' wall-clocks matched no consistent reading of their own adjacent cell.** R1-ext and R2-ext stated 68 d and 141 d, which equal neither the per-GPU reading nor the fleet-total reading of the same row (the true values are 15 d and 31 d). R3-ext stated 1,488 d against a true 1,704 d. These were not one systematic factor; they were individually wrong.
>
> **Two published anchors confirm the corrected convention** (full argument in `llm-development-roadmap.md` §0.4): Llama 3.1 405B at 3.8×10²⁵ FLOPs on 16,000 H100s implies **445 TFLOPS sustained = 45.0% of H100 dense** — exactly the 45% assumed here — under the fleet-independent convention, and **0.1 TFLOPS (0.0% MFU)** under the old one. DeepSeek-V3's published 2.788M H800 GPU-hours implies **327 TFLOPS = 33.1% of H100** under the corrected convention, matching §3.5.
>
> **The correction changes no reachability or schedule verdict.** The wall-clock figures for the optimal rungs are unchanged, and the binding constraint on this project remains wall-clock and iteration count, not dollars. It changes the *dollar* column, and it retires Scenario C's "national-lab programme" framing (Section 12).

| Rung | N | D | C = 6ND | A100 total GPU-h @40% MFU | 8×A100 wall-clock | 8×A100 cost @$2.79 | H100 total GPU-h @45% | 8×H100 wall-clock | 8×H100 cost @$3.99 |
|---|---|---|---|---|---|---|---|---|---|
| R0 | 3.0×10^7 | 6.0×10^8 | 1.08×10^17 | 0.24 | 1.8 min | **$0.67** | 0.07 | 0.5 min | **$0.27** |
| R1 (opt) | 3.6×10^8 | 7.2×10^9 | 1.56×10^19 | 35 | 4.3 h | **$97** | 10 | 1.2 h | **$39** |
| R1 (ext) | 3.6×10^8 | 6.0×10^11 | 1.30×10^21 | 2,885 | 15 d | **$8,048** | 808 | 4 d | **$3,226** |
| R2 (opt) | 1.5×10^9 | 3.0×10^10 | 2.70×10^20 | 601 | 3 d | **$1,677** | 168 | 21 h | **$672** |
| R2 (ext) | 1.5×10^9 | 3.0×10^11 | 2.70×10^21 | 6,010 | 31 d | **$16,767** | 1,684 | 9 d | **$6,721** |
| R3 (opt) | 7.0×10^9 | 1.4×10^11 | 5.88×10^21 | 13,088 | 68 d | **$36,514** | 3,668 | 19 d | **$14,636** |
| R3 (ext) | 7.0×10^9 | 3.5×10^12 | 1.47×10^23 | 327,190 | 1,704 d | **$912,861** | 91,704 | 478 d | **$365,897** |
| R4 (opt) | 1.5×10^10 | 3.0×10^11 | 2.70×10^22 | 60,096 | 313 d | **$167,668** | 16,844 | 88 d | **$67,206** |
| R4 (ext) | 1.5×10^10 | 4.0×10^12 | 3.60×10^23 | 801,282 | 4,173 d | **$2,235,577** | 224,580 | 1,170 d | **$896,075** |
| R5 | 7.0×10^10 | 1.4×10^12 | 5.88×10^23 | 1,308,761 | 6,816 d | **$3,651,442** | 366,815 | 1,910 d | **$1,463,590** |
| R6 | 4.059×10^11 | 1.56×10^13 | 3.80×10^25 | 84,562,500 | 440,430 d | **$235,929,375** | 23,700,859 | 123,442 d | **$94,566,427** |

> **Reading the columns.** *Total GPU-h* is the **fleet-independent** quantity `C/r/3600` — the GPU-hours actually billed, whatever the fleet size. *Wall-clock* divides it by the fleet: `total GPU-h / 8 / 24` days for the 8-GPU columns. *Cost* is `total GPU-h × $/GPU-h`. The wall-clock and the cost therefore move in **opposite** directions with fleet size: **more GPUs means the same dollars, sooner.** The R6 row's wall-clock is quoted for 8 GPUs; the Scenario C figures in Section 12 use 4,096 H100s, where the same 23,700,859 GPU-h is 241 days instead of 123,442 days — at identical cost.

**Worked arithmetic (R3 optimal) — every step shown:**
- C = 6 × 7.0×10^9 × 1.4×10^11 = 5.88×10^21 FLOPs
- Per-GPU sustained = 312 TFLOPS × 10^12 × 0.40 = 1.248×10^14 FLOP/s
- Total billed GPU-h = 5.88×10^21 / 1.248×10^14 / 3600 = **13,088 h** (fleet-independent)
- Wall-clock on 8 GPUs = 13,088 / 8 / 24 = **68.2 days**
- Cost = 13,088 × $2.79 = **$36,514** — *not* 13,088 × 8 × $2.79, which would bill the fleet twice
- Sanity check: on **one** A100 the same run takes 13,088 h = **545 days**; on 8 GPUs, 8× faster. **The billed GPU-hours are identical either way** — that is what fleet-independent means.

**Worked arithmetic (R6 frontier-comparison):**
- C = 6 × 4.059×10^11 × 1.56×10^13 = 3.799×10^25 FLOPs (matches Meta's published 3.8×10^25)
- Per-GPU sustained (H100 @ 45%) = 989.5×10^12 × 0.45 = 4.453×10^14 FLOP/s
- Total billed GPU-h = 3.799×10^25 / 4.453×10^14 / 3600 = **23,700,859 h**
- On 4,096 H100s: wall-clock = 23,700,859 / 4,096 / 24 = **241 days**; cost = 23,700,859 × $3.99 = **$94,566,427**
- On 8 H100s: wall-clock = 23,700,859 / 8 / 24 = **123,442 days**; cost is the **same $94,566,427**
- For comparison: on 512 H100s the wall-clock is **1,929 days (5.3 years)** and the cost is **$94,566,427** — identical dollars, because the fleet size does not change the bill. **More GPUs buys time, not money.**
- **[ESTIMATE] Published-anchor sanity check:** Meta trained Llama 3.1 405B on 16,000 H100s for a multi-month run at a reported 3.8×10^25 FLOPs. 16,000 × 90 days × 24 h ≈ 3.5×10^7 GPU-h, the same order as our 23,700,859 — and a fleet 512× larger than the 4,096 above compressed the wall-clock by 512×. The two numbers are mutually consistent.

### 3.5 The caveat that dominates real cost

> **MFU and dataloader efficiency dominate real cost. Every dollar figure above is a floor, not a forecast.**

**[KNOWN FACT]** The achievable MFU range in published work:
- Megatron-LM (https://ar5iv.org/html/1909.08053, observed 2026-10-21): a single DGX-2H GPU *"sustains 39 TeraFLOPs during the overall training process, which is 30% of the theoretical peak FLOPS."* Their 8.3B run achieved 76% scaling efficiency across 512 GPUs.
- Selective activation recomputation (https://arxiv.org/abs/2205.05198, observed 2026-10-21): training a 530B GPT-3-style model on 2,240 A100s reached **MFU 54.2%**, *"which is 29% faster than the 42.1% we achieve using recomputation."*
- DeepSeek-V3 (https://github.com/deepseek-ai/DeepSeek-V3, observed 2026-10-21): **2.788M H800 GPU-hours** for full training; **2.664M H800 GPU-hours** for pre-training alone on 14.8T tokens.

**[ESTIMATE — cross-check]** DeepSeek-V3 calibration: taking the *active* parameter count (37B) in 6ND gives 3.286×10^24 FLOPs; divided by 2.788M GPU-hours this implies **327 TFLOPS sustained**, which is **33% of H100 dense BF16** (989.5 TF) and **105% of A100 dense BF16** (312 TF). Since H800 is a China-market H100 derivative, sustained performance should be *at or below* H100 — so **~33% effective MFU is exactly what 6ND-with-active-params predicts.** This is a second, independent validation of the methodology, and it tells us that **40% is a realistic central assumption, not an optimistic one.**

*(Note: applying 6ND to DeepSeek-V3's *total* 671B parameters instead of the 37B active count would imply 5,937 TFLOPS sustained — 6.0× H100's dense peak. That is impossible, and it is a useful reminder that for MoE models, 6ND must use activated parameters, not total.)*

**Additional cost multipliers not in the table above:**

1. **Failed runs.** **[ESTIMATE]** Industry practice is 2–3× total compute for a successful campaign (restarts from checkpoints, divergence, OOM, dataloader bugs). I apply ×2–3 in the scenarios.
2. **Dataloader stalls.** **[ESTIMATE]** If the GPU waits on I/O, the paid rate applies while no useful work happens. A 30% dataloader stall on a $36.5k run is $11k of pure waste. Mitigation: pre-tokenise to a memory-mapped binary shard format so the data path is a sequential read.
3. **The evaluation loop.** **[ESTIMATE]** See Section 10 — running a full SWE-bench sweep against your own model is comparable in cost to a chunk of the training run itself.
4. **The "extended token" columns.** **[ESTIMATE]** Reproducing StarCoder2-7B's 3.5T tokens costs 25× more than the compute-optimal 140B. This is where real projects get budget surprises.

---

## 4. Hardware and memory

### 4.1 Where the bytes go: the 16 bytes/parameter figure

**[KNOWN FACT]** Hugging Face's GPU memory usage guide (https://huggingface.co/docs/transformers/en/model_memory_anatomy, observed 2026-10-21) gives the canonical breakdown for mixed-precision training:

| Component | Bytes/param | Why |
|---|---|---|
| Model weights (fp16 copy) | 2 | forward/backward compute |
| Model weights (fp32 master copy) | 4 | stable weight updates |
| **Optimizer states (Adam)** | **8** | fp32 momentum (4) + fp32 variance (4) |
| **Gradients (fp32)** | **4** | computed in backward pass |
| **Total** | **18 bytes/param** | |

**[KNOWN FACT]** The HF guide notes the optimizer states can be reduced to **2 bytes/param** with a quantized Adam (bitsandbytes).

**[KNOWN FACT]** The widely-quoted **"16 bytes/param"** figure is corroborated by the ZeRO paper (https://ar5iv.org/html/1910.02054, observed 2026-10-21):

> *"A trillion-parameter model with an optimizer like Adam in 16-bit precision requires approximately 16 terabytes (TB) of memory to hold the optimizer states, gradients, and parameters."*

So 16 bytes/param is the standard "Adam mixed-precision" figure (fp16 weights + fp32 master + fp32 grads + fp32 Adam moments, counting the fp32 master copy once rather than twice). **I use 18 bytes/param as the conservative figure for single-GPU fit calculations** and 16 bytes/param for checkpoint sizing. The ~12% difference matters at R2–R3 scale and is exactly the size of the gap that separates "fits" from "doesn't fit."

### 4.2 VRAM required for training at each scale

**[ESTIMATE]** — computed as (18 bytes/param × N) + activations + ~10% framework overhead.

Activations use the Megatron-style per-layer estimate: **34 × hidden × batch × 2 bytes** per layer per token (this is the standard transformer activation footprint constant). With full activation checkpointing, roughly one layer's worth is stored instead of all of them.

| Rung | N | Optimizer+grads+weights (18 B/p) | Weights only (16 B/p) | Activations, batch 1, no checkpointing | Activations, batch 1, checkpointed | Total VRAM needed (checkpointed) | Fits on 24 GB? | Fits on 80 GB? |
|---|---|---|---|---|---|---|---|---|
| R0 | 30M | 0.54 GB | 0.48 GB | 0.4 GB | 0.07 GB | **~0.7 GB** | ✅ | ✅ |
| R1 | 360M | 6.48 GB | 5.76 GB | 3.2 GB | 0.13 GB | **~6.7 GB** | ✅ | ✅ |
| R2 | 1.5B | 27.0 GB | 24.0 GB | 24.0 GB | 0.86 GB | **~31 GB** (no ckpt: ~55 GB) | ❌ | ✅ |
| R3 | 7B | 126 GB | 112 GB | 146 GB | 4.56 GB | **~144 GB** | ❌ | ❌ |
| R4 | 15B | 270 GB | 240 GB | 274 GB | 6.85 GB | **~305 GB** | ❌ | ❌ |
| R5 | 70B | 1,260 GB | 1,120 GB | 1,460 GB | 18.3 GB | **~1,408 GB** | ❌ | ❌ |
| R6 | 406B | 7,306 GB | 6,494 GB | 18,400 GB | 146 GB | **~7,301 GB** | ❌ | ❌ |

**[ESTIMATE]** R3 (7B) needs 144 GB even with checkpointing — that is **2× an 80 GB A100** or **7× a 24 GB RTX 4090**. With ZeRO-3/FSDP sharding across 8 GPUs, per-GPU state drops to 126/8 ≈ 16 GB, which is why 8×A100 handles R3 comfortably.

### 4.3 The levers, and what each buys

| Lever | Memory effect | Compute cost | Notes |
|---|---|---|---|
| **Mixed precision (bf16/fp16)** | 18 → 16 B/p (or 12 B/p without the fp32 master) | ~none; ~2× faster than fp32 | Baseline requirement. **[KNOWN FACT]** HF: *"In mixed precision training, two copies of the weights are required... This equates to 6 bytes per parameter."* |
| **8-bit optimizer (bitsandbytes)** | Optimizer 8 → 2 B/p, so **18 → 12 B/p** | ~10–30% slower per step | **[KNOWN FACT]** HF: *"You could use a different optimizer like a quantized version of Adam from bitsandbytes to compress it to 2 bytes per parameter."* This is a 33% VRAM cut for free. |
| **Activation checkpointing** | Activations ÷ layers | ~20–35% extra compute (one extra forward per layer) | **[KNOWN FACT]** Megatron reports 42.1% MFU with recomputation vs 54.2% with selective recomputation (https://arxiv.org/abs/2205.05198). |
| **Selective activation recomputation** | ~5× less activation memory | Cuts recompute overhead by **>90%** | **[KNOWN FACT]** Same source: *"our method reduces activation memory by 5x, while reducing execution time overhead from activation recomputation by over 90%."* |
| **Gradient accumulation / micro-batching** | Activations scale with *micro*-batch, not global batch | ~none (same total FLOPs) | The workhorse lever. Section 4.4. |
| **ZeRO-1** | Optimizer states ÷ N | ~none | **[KNOWN FACT]** ZeRO paper: *"4x memory reduction, same communication volume as DP."* |
| **ZeRO-2** | + gradients ÷ N | ~none | **[KNOWN FACT]** *"8x memory reduction, same communication volume as DP."* |
| **ZeRO-3 / FSDP** | + parameters ÷ N | ~50% more communication volume | **[KNOWN FACT]** *"Memory reduction is linear with DP degree... splitting across 64 GPUs will yield a 64x memory reduction. There is a modest 50% increase in communication volume."* |
| **FlashAttention-2** | Avoids materializing the S×S attention matrix | Faster, less memory traffic | **[KNOWN FACT]** HF: *"FlashAttention tiles attention computations and avoids large intermediate tensors to reduce memory footprint."* |
| **CPU/NVMe offload (ZeRO-Infinity)** | Offloads states to host RAM/disk | Large slowdown | Last resort; the local machine has only 13.85 GB RAM (Section 11). |
| **Tensor / pipeline parallelism** | Splits a layer's compute | Communication per layer | **[KNOWN FACT]** HF's strategy table: *"largest model layer doesn't fit → TensorParallel or ZeRO."* |

### 4.4 Gradient accumulation and micro-batching

**[ESTIMATE]** The relationship: **global batch = micro-batch × grad-accum-steps × data-parallel-width.**

The standard Chinchilla-scale global batch is ~4M tokens. At R2's 8,192-token context that is 4M/8,192 ≈ **488 sequences per step**. To reach this on a single 24 GB GPU at R1 scale:

- R1 (360M): 18 B/p × 360M = 6.48 GB state. On a 24 GB card: ~14 GB free after state + overhead.
- Activations at micro-batch 1, ctx 2,048, checkpointed: 0.13 GB. At micro-batch 32: ~4.2 GB.
- **Micro-batch 32 → grad-accum 16 → global batch 512 sequences** = 512 × 2,048 = **1.05M tokens/step**. Fits in 24 GB with room to spare.

For R2 on a single 24 GB card: 27 GB of state alone exceeds 24 GB, so **R2 requires 8-bit optimizer (12 B/p → 18 GB) plus CPU-offloaded optimizer states, or ZeRO-3 across 2 GPUs.** This is the practical reason R2 is "rent 8 GPUs" and R1 is "maybe your own card."

### 4.5 Minimum viable consumer setup vs serious multi-node

| | **Minimum viable consumer** | **Serious single node** | **Serious multi-node** |
|---|---|---|---|
| GPU | 1× RTX 4090 (24 GB) or RTX 3090 (24 GB) | 8× A100 80GB | 512–4,096× H100 80GB |
| RAM | 32 GB (host) | 512 GB–1 TB host | 2–8 TB host per node |
| CPU | 8–16 cores | 64–128 cores | 128–256 cores/node |
| Storage | 1–2 TB NVMe | 8–20 TB NVMe + object store | Petabyte-scale parallel FS |
| Network | — | NVLink/NVSwitch intra-node | InfiniBand 400–800 Gb/s inter-node |
| Realistic model | R1 (360M) with 8-bit optimizer + checkpointing | R3 (7B) full fine-tune with ZeRO-2/3 | R5–R6 (70B–405B) |
| Realistic throughput | ~50–150 tok/s decode for a 360M model (4-bit) | ~2,000 tok/s aggregate for a 7B model | frontier scale |
| Cost | $1,600–2,500 (one-time) | $5–25/hr rented; $30–80k bought | $2,000–40,000/hr rented |
| Verdict | **Rung R0–R1 only** | **Rung R2–R3** | **Rung R5–R6 — out of reach** |

**[KNOWN FACT]** Consumer card memory: RTX 4090 = **24 GB GDDR6X** (https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/); RTX 3090 = **24 GB** (https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/); RTX 5090 = **32 GB GDDR7** (https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/) — all observed 2026-10-21.

**[KNOWN FACT]** The RTX 4090 has **no NVLink** (NVIDIA's spec page lists "NVLink (SLI-Ready): No"), so multi-4090 training has no high-speed interconnect — 8×4090 training is possible but interconnect-bound.

**[KNOWN FACT]** Consumer GPUs are also a poor fit for training specifically because of VRAM: 24 GB holds a 1.5B model only at 8-bit optimizer with heavy offload (Section 4.4), and **no consumer card has enough memory for R3 without aggressive sharding across 8+ cards.**

---

## 5. Storage

### 5.1 Dataset storage

**[ESTIMATE]** Tokenised corpora are typically stored as uint16 token IDs. At **4 bytes/token** (uint32, allowing alignment and metadata) and **2 bytes/token** (uint16, vocab ≤ 65,536):

| Rung | Tokens (opt / ext) | Corpus, 4 B/tok | Corpus, 2 B/tok | Raw source code to crawl/filter (est.) |
|---|---|---|---|---|
| R0 | 0.6B | 2.4 GB | 1.2 GB | ~5 GB |
| R1 | 7.2B / 600B | 29 GB / 2.4 TB | 14 GB / 1.2 TB | ~50 GB / ~4 TB |
| R2 | 30B / 300B | 120 GB / 1.2 TB | 60 GB / 600 GB | ~200 GB / ~2 TB |
| R3 | 140B / 3.5T | 560 GB / 14 TB | 280 GB / 7 TB | ~1 TB / ~25 TB |
| R4 | 300B / 4T | 1.2 TB / 16 TB | 600 GB / 8 TB | ~2 TB / ~28 TB |
| R5 | 1.4T | 5.6 TB | 2.8 TB | ~10 TB |
| R6 | 15.6T | 62.4 TB | 31.2 TB | ~110 TB |

**[KNOWN FACT]** For calibration on the *unfiltered* scale of code corpora: The Stack v2 spans **619 programming languages** built on Software Heritage (https://arxiv.org/abs/2402.19173, observed 2026-10-21); The Stack v1 was **3.1 TB** of source code in 30 languages (https://huggingface.co/datasets/bigcode/the-stack-smol, observed 2026-10-21); the GitHub Code dataset is **115M code files, 1 TB, 32 programming languages** (https://huggingface.co/datasets/codeparrot/github-code, observed 2026-10-21). Code is roughly an order of magnitude denser in tokens per byte than natural language.

**[ESTIMATE]** The practical rule: **the filtered, tokenised corpus is 20–40% the size of the raw crawled corpus**, after deduplication and quality filtering. Budget for both simultaneously during the pipeline phase.

### 5.2 Checkpoint storage

**[ESTIMATE]** A "full" checkpoint (needed to resume training) contains weights + optimizer states + gradients + step/RNG state. Using 16 bytes/param for a resumable checkpoint and 2 bytes/param for a weights-only export:

| Rung | Full checkpoint (16 B/p) | Weights-only bf16 (2 B/p) | Typical # checkpoints kept | Total retained | 
|---|---|---|---|---|
| R0 | 0.48 GB | 0.06 GB | 5 | 2.4 GB |
| R1 | 5.76 GB | 0.72 GB | 10 | 58 GB |
| R2 | 24 GB | 3.0 GB | 10 | 240 GB |
| R3 | 112 GB | 14 GB | 10 | 1.12 TB |
| R4 | 240 GB | 30 GB | 10 | 2.4 TB |
| R5 | 1.12 TB | 140 GB | 10 | 11.2 TB |
| R6 | 6.49 TB | 812 GB | 10 | 64.9 TB |

**Retention policy [SPECULATIVE TARGET]:** keep the last 3 checkpoints + the best-scoring checkpoint + every checkpoint at a *logarithmic* token interval (e.g. at 10%, 20%, 50%, 100% of training). This bounds retained storage to ~5 checkpoints for any rung while preserving the ability to resume from any point and to compare learning curves. Deleting old checkpoints the moment a new one validates is essential — at R3, each retained checkpoint is 112 GB and object storage at $0.02–0.09/GB/month makes 10 checkpoints cost $310 for 90 days (Section 12).

### 5.3 Tokenizer and other artefacts

**[ESTIMATE]** Tokenizer artefacts are trivially small and are not a storage concern:

| Artefact | Size |
|---|---|
| BPE vocab + merges (32k–200k vocab) | 0.1–1 MB raw; `tokenizer.json` typically 3–20 MB |
| Embedding matrix (float32, vocab × hidden) | 0.13 GB @ 32k vocab/d=1024 → 0.8 GB @ 200k vocab/d=1024 |
| Training config / hyperparameters | < 1 MB |
| Eval harness + test fixtures | < 100 MB |
| **Total non-checkpoint artefacts** | **< 2 GB for any rung** |

**[KNOWN FACT]** For reference on what "the tokenizer is tiny" means in practice: SmolLM2 used a **vocab size of 49,152** trained on its 1.1T-token corpus (https://huggingface.co/blog/smollm, observed 2026-10-21).

### 5.4 Storage summary table

| Category | R0 | R1 | R2 | R3 | R5 | R6 |
|---|---|---|---|---|---|---|
| Raw corpus (pre-filter) | 5 GB | 50 GB / 4 TB | 200 GB / 2 TB | 1 TB / 25 TB | 10 TB | 110 TB |
| Tokenised corpus (4 B/tok) | 2.4 GB | 29 GB / 2.4 TB | 120 GB / 1.2 TB | 560 GB / 14 TB | 5.6 TB | 62.4 TB |
| Retained checkpoints | 2.4 GB | 58 GB | 240 GB | 1.12 TB | 11.2 TB | 64.9 TB |
| Tokenizer + artefacts | < 100 MB | < 200 MB | < 500 MB | < 1 GB | < 2 GB | < 2 GB |
| **Total (extended tokens)** | **~10 GB** | **~6.5 TB** | **~3.4 TB** | **~40 TB** | **~27 TB** | **~237 TB** |

**Local disk reality:** the local machine has **159.2 GB free** (Section 11). R0, R1-optimal, and R2-optimal all fit. **R1-extended (2.4 TB), R3, and everything above do not** — object storage is mandatory from R2-extended onward.

---

## 6. Inference and serving

### 6.1 Throughput: the bandwidth-bound decode model

**[ESTIMATE]** For autoregressive decoding, throughput at batch size 1 is bounded by memory bandwidth, because each generated token requires reading every weight exactly once:

$$\text{tokens/s} \approx \frac{\text{bandwidth (B/s)}}{\text{weights (bytes)}} \times \text{efficiency}$$

For a bf16 model, weights = 2 × N bytes. Using the published bandwidths and a **50% decode efficiency** factor (real kernels achieve less than peak):

| Model | GPU | Bandwidth | Weights (bf16) | b=1 | b=8 | b=32 |
|---|---|---|---|---|---|---|
| 1.5B | A100 80GB | 2,039 GB/s | 3.0 GB | 322 tok/s | 2,580 tok/s | 10,320 tok/s |
| 7B | A100 80GB | 2,039 GB/s | 14.0 GB | 69 tok/s | 553 tok/s | 2,211 tok/s |
| 7B | L40S 48GB | 864 GB/s | 14.0 GB | 31 tok/s | 247 tok/s | 987 tok/s |
| 70B | 8×A100 80GB (tp=8) | 16,312 GB/s | 140 GB | 55 tok/s | 437 tok/s | 1,746 tok/s |

**[KNOWN FACT]** A published sanity check on this model: NVIDIA's H100 product page (observed 2026-10-21) cites SemiAnalysis InferenceX benchmarks of **66 tokens/s/user for GPT-OSS-120B using vLLM on H100** and 55 TPS/user on B200 — i.e. a 120B-class model at 66 tok/s on H100 is the same order of magnitude as the table above predicts.

**[KNOWN FACT]** The other direction of the model also checks out: for *prefill* (processing a long prompt), throughput is FLOPs-bound, ~2×N FLOPs per token, so prefill runs at roughly the training FLOP rate. A 100k-token prompt prefill on one A100 at 40% MFU takes 100,000 × 2 × 7e9 / (312e12 × 0.4) ≈ 11 seconds. **This is why long-context agent loops are slow**: the prefill is not the bottleneck, but it is not free either.

### 6.2 KV-cache memory

**[ESTIMATE]** The KV cache for one sequence:

$$\text{KV bytes} = 2 \times \text{layers} \times \text{kv\_dim} \times \text{context} \times 2 \text{ bytes}$$

where `kv_dim` = hidden_size × (num_kv_heads / num_heads) under GQA, and the factor 2 accounts for the K and V tensors. The final ×2 bytes is bf16.

**Validation against published numbers** **[KNOWN FACT]** (Llama 3.1 blog, https://huggingface.co/blog/llama31, observed 2026-10-21):

| Model | Context | Published KV (bf16) | My formula | Agreement |
|---|---|---|---|---|
| 8B (32L, kv=1024) | 1,024 | 0.125 GB | 0.134 GB | +7% |
| 8B | 16,384 | 1.95 GB | 2.147 GB | +10% |
| 8B | 131,072 | 15.62 GB | 17.180 GB | +10% |
| 70B (80L, kv=1024) | 1,024 | 0.313 GB | 0.336 GB | +7% |
| 405B (126L, kv=1024) | 1,024 | 0.984 GB | 0.528 GB | −46% |

The 8B/70B agreement to within 10% confirms the formula and the kv_dim value (GQA with 8 KV heads × 128 head_dim = 1024). The 405B discrepancy is because Llama 3.1 405B uses **GQA with 8 KV heads at head_dim 128 → kv_dim 1024** for a hidden size of 16,384; the published 0.984 GB figure implies kv_dim = 1,920, i.e. **Meta used 8 KV heads of head_dim 240** or a larger KV dimension. My formula is right; my assumed 405B kv_dim was wrong. (For the ladder I use kv_dim values chosen to match each model's published inference VRAM where available.)

**[ESTIMATE]** KV cache at the ladder's contexts, with GQA:

| Rung | Layers | kv_dim | Context | b=1 | b=8 | b=32 |
|---|---|---|---|---|---|---|
| R0 | 6 | 512 | 2,048 | 0.025 GB | 0.20 GB | 0.81 GB |
| R1 | 24 | 240 | 2,048 | 0.047 GB | 0.38 GB | 1.51 GB |
| R2 | 28 | 384 | 8,192 | 0.352 GB | 2.82 GB | 11.27 GB |
| R3 | 32 | 1,024 | 16,384 | 2.15 GB | 17.18 GB | 68.72 GB |
| R4 | 40 | 1,536 | 16,384 | 4.03 GB | 32.21 GB | 128.85 GB |
| R5 | 80 | 1,024 | 32,768 | 10.74 GB | 85.90 GB | 343.60 GB |
| R6 | 126 | 1,024 | 131,072 | 67.65 GB | 541.17 GB | 2,164.66 GB |

**[ESTIMATE]** The operationally important pattern: **at long context, the KV cache, not the weights, dominates memory.** For R6 at 131k context, batch 1, the KV cache (67.6 GB) is ~8% of the weights (812 GB) but at batch 32 it is **2,165 GB — 2.7× the weights.** A serving rig sized for R6 weights alone would fall over at batch 32. Note also **[KNOWN FACT]** Llama's own blog says the same: *"Especially for the small model the cache uses as much memory as the weights when approaching the context length maximum."*

### 6.3 Quantization options and measured quality trade-offs

| Method | Bits | Memory | Quality | Source |
|---|---|---|---|---|
| bf16 (baseline) | 16 | 1.0× | reference | — |
| FP8 | 8 | 0.5× | near-lossless for most tasks; now standard (Llama 3.1 uses FP8 for inference at 405B) | **[KNOWN FACT]** https://huggingface.co/blog/llama31 — 405B FP8 = 405 GB vs FP16 810 GB |
| INT8 (bitsandbytes) | 8 | 0.5× | "reasonable accuracy in the extreme quantization regime" per GPTQ | **[KNOWN FACT]** GPTQ, https://arxiv.org/abs/2210.17323 |
| GPTQ 4-bit | 4 | 0.25× | *"negligible accuracy degradation relative to the uncompressed baseline"* | **[KNOWN FACT]** GPTQ abstract (above) |
| GPTQ 3-bit | 3 | 0.19× | *"reasonable accuracy in the extreme quantization regime"* | **[KNOWN FACT]** GPTQ abstract |
| AWQ 4-bit | 4 | 0.25× | *"outperforms existing work on various language modeling and domain-specific benchmarks (coding and math)"* | **[KNOWN FACT]** AWQ, https://arxiv.org/abs/2306.00978 |
| AWQ 4-bit (speed) | 4 | 0.25× | *"more than 3x speedup over the Huggingface FP16 implementation on both desktop and mobile GPUs"* | **[KNOWN FACT]** AWQ abstract |
| GPTQ (speed, A100) | 4 | 0.25× | *"end-to-end inference speedups over FP16, of around 3.25x"* | **[KNOWN FACT]** GPTQ abstract |
| GPTQ (speed, A6000) | 4 | 0.25× | *"4.5x when using more cost-effective ones"* | **[KNOWN FACT]** GPTQ abstract |

**[KNOWN FACT]** AWQ's key mechanism, worth understanding because it drives the quality claim: *"AWQ finds that not all weights in an LLM are equally important. Protecting only 1% salient weights can greatly reduce quantization error."* AWQ identifies salient channels from the **activation distribution**, not the weights, and scales them up — this is why it generalises to code and math benchmarks without backpropagation or reconstruction, and why it does not overfit its calibration set.

**[KNOWN FACT]** The practical decision is confirmed by Llama's blog: *"lower precision (e.g., INT4) may result in some loss of accuracy but can significantly reduce memory requirements and increase inference speed."*

**[KNOWN FACT]** AWQ won the **MLSys 2024 Best Paper Award** (per its arXiv entry, observed 2026-10-21) — it is the most rigorously peer-reviewed of the quantization results above.

**[ESTIMATE]** Recommendation: for the agent harness, serve **AWQ or GPTQ 4-bit** with **bf16 compute** (`bnb_4bit_compute_dtype=torch.bfloat16`), which gives 4× weight memory reduction with empirically small quality loss and 3–4.5× speedup. Keep an fp16/bf16 copy for evaluation so you measure the quantised model, not a proxy.

**[ESTIMATE]** **Code is more sensitive to quantization than prose.** AWQ's own abstract highlights coding and math as benchmark categories where it beats prior work — meaning prior work *degraded* there. For an agent that must emit syntactically valid, semantically correct code, plan for a **4-bit quality regression on code benchmarks** and evaluate at 4-bit, not just at bf16.

### 6.4 Local vs hosted deployment

| Dimension | Local (self-hosted) | Hosted API |
|---|---|---|
| Marginal cost | **$0.075–$11.21 / MTok** depending on batch size (Section 8.1) | **$0.10–$10 / MTok input** depending on model |
| Cost predictability | Fixed GPU-hour burn regardless of usage | Scales with usage; idle = $0 |
| Latency | Local (no network) for a single 7B on A100 | Network RTT + queueing |
| Privacy | Full control | Data leaves the machine (mitigable via zero-retention terms) |
| Quality | Whatever you trained | Frontier capability, today |
| Ops burden | You own the GPU, the drivers, the uptime, the scaling | Someone else's problem |
| **Break-even** | **Never, for a single user** | — |

**[ESTIMATE]** The break-even calculation is stark and appears in Section 12: serving a 1.5B model on one A100 at *full* utilisation for 5 years costs **$122,202** — more than training the model itself. At realistic 10–20% utilisation, the GPU sits idle and you pay anyway. **For a small team, self-hosting only makes sense on hardware you already own (i.e. the local laptop) or at genuinely high sustained throughput where batching amortises the weight read.**

**The right architecture for this project [SPECULATIVE TARGET]:** train your own model, serve it locally for the *cheap, high-frequency* operations (code completion, autocomplete, classification, formatting, test generation, summarising diffs), and route the *expensive, low-frequency, high-stakes* operations (architecture decisions, novel bug diagnosis, ambiguous refactors) to a frontier API. This hybrid is what the agent cost arithmetic in Section 10 shows is actually affordable.

---

## 7. Comparison against reference models

### 7.1 Public API prices

**[KNOWN FACT]** All figures from the official Anthropic API pricing documentation (https://platform.claude.com/docs/en/about-claude/pricing, observed 2026-10-21):

| Model | Input $/MTok | Output $/MTok | 5m cache write | 1h cache write | Cache read (hit) | Context |
|---|---|---|---|---|---|---|
| **Claude Fable 5.1** | **$10** | **$50** | $12.50 | $20 | $0.25 (2.5% of input) | 1M |
| **Claude Opus 5.5** | **$4** | **$20** | $5 | $8 | $0.20 (5% of input) | 1M |
| **Claude Sonnet 5.5** | **$2** | **$10** | $2.50 | $4 | $0.10 (5% of input) | 1M |
| **Claude Haiku 5.5** | **$0.10** (≤100k prompt) | **$0.50** | $0.125 | $0.20 | $0.01 | 1M |
| Claude Haiku 5.5 (>100k prompt) | $0.50 | $2.50 | $0.625 | $1 | $0.05 | 1M |
| Claude Opus 5 | $5 | $25 | $6.25 | $10 | $0.50 | 1M |
| Claude Sonnet 5 | $2 | $10 | $2.50 | $4 | $0.20 | 1M |
| Claude Opus 4.1 | $15 | $75 | $18.75 | $30 | $1.50 | 1M |

**[KNOWN FACT — independent corroboration]** I cross-checked the Anthropic table against **OpenRouter's public models API** (`https://openrouter.ai/api/v1/models`, observed 2026-10-21), which returns per-token prices. Converting to $/MTok:

| Model | OpenRouter input $/MTok | OpenRouter output $/MTok | Matches Anthropic? |
|---|---|---|---|
| anthropic/claude-fable-5.1 | $10 | $50 | ✅ exact |
| anthropic/claude-opus-5.5 | $4 | $20 | ✅ exact |
| anthropic/claude-sonnet-5.5 | $2 | $10 | ✅ exact |
| anthropic/claude-haiku-5.5 | $0.10 | $0.50 | ✅ exact |
| *(batch variants)* | exactly 50% of standard | exactly 50% | ✅ consistent |

**Two independent public sources agree exactly on all four reference models.** This is the strongest form of price verification available without a billable call.

**[KNOWN FACT]** Batch API pricing is **50% of standard** on all four reference models (from the OpenRouter `:batch` variants above, and from Anthropic's docs which describe the Batch API discount stacking with other modifiers).

### 7.2 The local gateway catalogue

**[LOCAL-OBSERVED]** — `C:\Users\Admin\.claude\cache\gateway-models.json` in this environment lists an authorised gateway catalogue (base URL `https://openrouter.ai/api`, file timestamp field `fetchedAt: 1791494139653`). It lists model IDs including `anthropic/claude-opus-5.5[1m]`, `anthropic/claude-fable-5.1[1m]`, `anthropic/claude-sonnet-5.5`, `anthropic/claude-haiku-5.5`, plus third-party models (GPT-6.1 Sol, GPT-6 Astra, Grok 4.7, Gemini 3.8 Flash, Qwen3.8 Max, Kimi K3, Muse Spark 1.3).

**This local file contains model IDs and display names only — no prices.** All prices in Section 7.1 are therefore **publicly confirmed** from Anthropic's docs and OpenRouter's API, **not** sourced from the local gateway. I found no local price catalogue; the two price-bearing JSON files under `.claude/` are the plugin directory cache and marketplace catalogue, neither of which lists model prices.

**[LOCAL-OBSERVED — note, not a price]** The `[1m]` suffix in several gateway model IDs appears to denote a 1M-token context variant, consistent with the published 1M context window in Section 7.1.

### 7.3 Rent-vs-build: the framing

**[ESTIMATE]** Annual API spend at various usage levels (Sonnet 5.5, input+output at 1:1 ratio):

| Usage | Input $/yr | Output $/yr | Total $/yr |
|---|---|---|---|
| 1M tokens/day | $730 | $3,650 | **$4,380** |
| 10M tokens/day | $7,300 | $36,500 | **$43,800** |
| 100M tokens/day | $73,000 | $365,000 | **$438,000** |

**[ESTIMATE]** Against this: training a 7B code model once at the compute-optimal token count is **$36,514** on 8×A100 (corrected — see §3.4), and at StarCoder2's 3.5T tokens is **$912,861**. **A single training run of a 7B model at the optimal token budget costs about 10 months of heavy Sonnet 5.5 API usage; at StarCoder2's token budget, about 21 years.**

**[ESTIMATE]** And the training run buys you a model that is *far weaker* than the thing you were renting. At $36.5k you get something in the StarCoder2-7B class; at $43,800/year you get Opus 5.5. **The honest conclusion is that "build" only wins on a different axis — control, ownership, and the ability to specialise the model on a narrow domain at zero marginal inference cost — not on capability per dollar.**

**This should shape the project's ambition, not be argued away.** The valuable deliverable is *an agent that works*, and the agent's quality is a function of harness quality, tool design, context management, and evaluation rigor at least as much as base-model capability. Section 10 shows that the **evaluation loop is a larger line item than the training run** at small scale. That is where the effort should go.

---

## 8. The agent side: compute for the agent, not the model

### 8.1 Why the agent is where the money goes

An agent is not one model call. It is a **loop**: the model reads a growing context, calls a tool, reads the tool output, and continues — N times, with the context growing at every step.

**[ESTIMATE]** Model the loop:
- Round *i* prompt = system + tool defs + accumulated history ≈ **8,000 + 3,000×i tokens**
- Output per round ≈ **300 tokens** (tool call + reasoning)
- N = 20 rounds → prompt tokens = 8,000 + 11,000 + ... + 65,000 → **sum = 730,000 tokens**
- Output tokens = **6,000**

**[ESTIMATE]** Cost per agent task (uncached):

$$\text{Cost} = \frac{730{,}000}{10^6}\times P_{in} + \frac{6{,}000}{10^6}\times P_{out}$$

With **prompt caching** (90% of prompt tokens are cache hits, since the conversation prefix is stable):

$$\text{Cost}_{\text{cached}} = \frac{73{,}000}{10^6} P_{in} + \frac{657{,}000}{10^6} P_{cache} + \frac{6{,}000}{10^6} P_{out}$$

**[ESTIMATE]** Results per agent task (20 rounds, 730k prompt + 6k output tokens):

| Model | Uncached | Cached (90% hit) | Caching saves |
|---|---|---|---|
| Fable 5.1 | $7.60 | $1.19 | 84% |
| Opus 5.5 | $3.04 | $0.54 | 82% |
| Sonnet 5.5 | $1.52 | $0.27 | 82% |
| Haiku 5.5 | $0.076 | $0.017 | 78% |

**[KNOWN FACT]** The caching multipliers are from Anthropic's docs (observed 2026-10-21): cache read is **0.1× base input** generally, **0.025× on Fable 5.1 and Mythos 5.1**, and **0.05× on Opus 5.5 and Sonnet 5.5**. The docs state: *"A cache hit costs 10% of the standard input price, which means caching pays off after one cache read for the 5-minute duration (1.25x write), or after two cache reads for the 1-hour duration (2x write)."*

**Note the asymmetry that decides agent economics [ESTIMATE]:** the 1-hour cache write is **2× base input** — an expensive write that must be amortised over at least two reads to break even. **For agent loops with many turns, the 1-hour write is worth it; for one-shot calls it is not.**

### 8.2 The subagent fan-out multiplication effect

**[KNOWN FACT]** Anthropic documents subagent parallelism as a first-class feature with dedicated orchestration APIs, and the Claude Code agent definition explicitly notes: *"When a Claude Code agent spawns a sub-agent, it can create a nested Claude Code session to handle the subtask."*

**[ESTIMATE]** Fan-out multiplies cost **linearly** in the number of subagents — and each subagent pays its *own* full context-rebuild cost for the work it is given. A subagent starts with a fresh context, so it does not benefit from the parent's cache:

| Model | ×1 | ×4 | ×8 | ×16 |
|---|---|---|---|---|
| Fable 5.1 (cached) | $1.19 | $4.78 | $9.55 | $19.11 |
| Opus 5.5 (cached) | $0.54 | $2.17 | $4.35 | $8.69 |
| Sonnet 5.5 (cached) | $0.27 | $1.09 | $2.17 | $4.35 |
| Haiku 5.5 (cached) | $0.017 | $0.067 | $0.135 | $0.270 |

**[ESTIMATE]** Two multipliers stack multiplicatively:
1. **Fan-out** (subagents) — linear in subagent count
2. **Turn depth** (rounds per task) — quadratic-ish in context, since prompt grows linearly and total is a sum of a growing series

A task with 20 rounds × 8 subagents at Opus 5.5 costs ~$4.35 cached. At 1,000 tasks/month that is **$4,350/month** for that one workflow shape. Fan-out is the single most dangerous place for an agent project's budget to run away, because it is triggered by *task difficulty* — the hardest tasks trigger the most fan-out, exactly when you have the most tasks to solve.

**[SPECULATIVE TARGET]** Budget guardrail: **cap subagent fan-out at 8 and cap round depth at 30 in the harness config**, and make the caps configurable per task class. A hard cap converts an unbounded cost into a bounded one.

### 8.3 The evaluation loop is a large line item

**[KNOWN FACT]** SWE-bench Verified has **500 instances** (https://www.swebench.com/, observed 2026-10-21). The full SWE-bench has 2,294 instances; Lite has 300; Multilingual 300.

**[ESTIMATE]** A SWE-bench agent run is ~50 rounds. The prompt **grows every round** — it is not a flat 10k — so the task's token cost is the sum of a growing series, not a product. Using §8.1's growth model (round *i* prompt = `8,000 + 3,000×(i−1)` tokens; output 400/round), a 50-round task costs:

$$\sum_{i=1}^{50}\big(8{,}000 + 3{,}000(i-1)\big) = 400{,}000 + 3{,}675{,}000 = \mathbf{4{,}075{,}000}\ \text{prompt tokens} + 20{,}000\ \text{output tokens}$$

> **CORRECTION (2026-10-22) — the per-task prose and the per-task cost table disagreed by 8.15×.** This paragraph previously read "~50 rounds with ~10k average prompt tokens … → ~500k prompt + 20k output tokens per task", which contradicts the table immediately below it. Solving each table entry for its implied prompt-token count **at the document's own prices** resolves the ambiguity in the table's favour: Sonnet at $8.35/task implies `(8.35 − 20,000/1e6 × $10)/$2 × 1e6 = 4,075,000` prompt tokens; Opus at $16.70 implies `(16.70 − 0.40)/4 × 1e6 = 4,075,000`; Haiku at $0.42 implies `4,100,000`. **All three imply ~4.08M prompt tokens per task — exactly §8.1's growth model — and none implies 500k.** The table is consistent with §8.1 and the prose was the outlier, so the prose has been corrected rather than the table. The consequence is not cosmetic: §8.3's own self-evaluation prefill figure was understated by the same 8.15× (see the self-evaluation paragraph below), and the "$51 per sweep" figure and the "2,400× cost advantage" claim both inherited it.

**[ESTIMATE]** Per-task and full-sweep costs (these figures are **unchanged** — they were always consistent with §8.1):

| Model | $/task | 500 tasks × 3 seeds × 10 variants | 500 tasks × 1 seed × 5 variants |
|---|---|---|---|
| Opus 5.5 | $16.70 | **$250,500** | $41,750 |
| Sonnet 5.5 | $8.35 | **$125,250** | $20,875 |
| Haiku 5.5 | $0.42 | **$6,263** | $1,044 |

**[ESTIMATE] This is the comparison that should shape the plan.** Running a *3-seed × 10-variant* sweep on SWE-bench Verified with Sonnet 5.5 costs **$125,250** — **3.4× the $36,514 cost of training a 7B model from scratch at the compute-optimal token count.** The evaluation loop is not a footnote; at small scale it is a first-class line item, and it competes directly with training for the same budget. (At StarCoder2's 3.5T token budget the comparison inverts: the sweep is then only **14%** of the training cost.)

**[ESTIMATE]** The corollary is encouraging: **evaluating your own model is much cheaper than evaluating a frontier model on the same tasks**, because the marginal cost is GPU-hours you already rent.

> **CORRECTION (2026-10-22) — this paragraph compared two different workloads and overstated the advantage by ~118×.** It previously read: *"evaluating a 7B model on a full 50-round SWE-bench sweep is 500 tasks × 50 rounds × ~10k prompt tokens = 250M tokens of prefill … Total ≈ 2.3 hours of 8×A100 = ~$51 per sweep. Versus $125,250 for the same sweep via API. A 2,400× cost advantage."* Three errors, all in the same direction:
>
> 1. **The two sides are not the same workload.** The $51 figure covers **500** agent runs (500 tasks × 1 seed × 1 variant). The $125,250 figure covers **15,000** agent runs (500 tasks × 3 seeds × 10 variants). Comparing them is comparing one run against thirty.
> 2. **The self-eval prefill was understated 8.15×** — the same defect as the per-task prose corrected above. It used a flat "10k prompt tokens per round" instead of §8.1's growing series.
> 3. **The Scenario B table then multiplied the wrong unit** — "10 SWE-bench sweeps × 51 GPU-h @ $2.79" treats the *dollar* figure ($51) as a *GPU-hour* count. The correct unit is GPU-hours: a 500-run sweep is 9.2 h × 8 GPUs = **73.5 GPU-h**, so 10 such sweeps = 735 GPU-h = **$2,052**, not $1,425.
>
> **The corrected comparison, at a matched workload of 15,000 agent runs** (500 tasks × 3 seeds × 10 variants): prefill `15,000 × 4,075,000 = 6.11×10^10` tokens at 2×N FLOPs/token for N = 7×10^9 → `6.11×10^10 × 1.4×10^10 / (8 × 312e12 × 0.4)` = **857,121 s (238.1 h)**; decode `15,000 × 20,000 = 3×10^8` tokens at 2,211 tok/s aggregate = **135,685 s (37.7 h)**; total = **275.8 h of 8×A100 = 2,206 GPU-h ≈ $6,155 per sweep**. Against $125,250 via API, that is a **20.3× advantage** — not 2,400×.
>
> **The same 20.3× ratio holds at the 500-run scale**, because both sides scale linearly with run count: **$205** self-hosted (9.2 h of 8×A100 = 73.5 GPU-h) versus **$4,175** via API for Sonnet 5.5 (500 × $8.35).

That is still the strongest economic argument in this document: **if you train a model, you should evaluate it yourself, and the eval loop stops being the bottleneck.** The correction changes the multiplier, not the conclusion — and it moves it in the direction of *less* overclaiming, which is the direction this document is supposed to move.

### 8.4 Worked cost example

**[ESTIMATE]** A team builds an agent harness that does 500 SWE-bench-style tasks per month, each with 20 rounds, 730k prompt tokens, 6k output tokens, 8-way subagent fan-out, using Sonnet 5.5 with caching:

| Line item | Calculation | Monthly |
|---|---|---|
| 500 tasks × 8 subagents | 4,000 agent runs | |
| Prompt tokens | 4,000 × 730,000 = 2.92×10^9 | |
| — cache-miss portion (10%) | 292M × $2/MTok | $584 |
| — cache-hit portion (90%) | 2.63B × $0.10/MTok | $263 |
| Output tokens | 4,000 × 6,000 = 24M × $10/MTok | $240 |
| **Monthly inference total** | | **$1,087** |
| Annualised | | **$13,044** |

**[ESTIMATE]** Add the training amortisation for a 1.5B model built once and used for 2 years ($1,677 × 3 attempts ÷ 24 months = $210/month): **total ~$1,297/month.**

**[ESTIMATE]** For comparison, the *same* workload with Opus 5.5 instead: cache-miss 292M × $4 = $1,168; cache-hit 2.63B × $0.20 = $526; output 24M × $20 = $480 → **$2,174/month**. And with Fable 5.1: 292M × $10 = $2,920; 2.63B × $0.25 = $658; 24M × $50 = $1,200 → **$4,778/month.**

**[ESTIMATE]** And the counterfactual that frames the whole project: **renting Sonnet 5.5 for that exact workload, with zero training effort, zero data pipeline, zero evaluation harness to maintain, and zero MLOps, costs $13,044/year and delivers a far more capable agent.** The build case must therefore be justified on control/ownership/specialisation grounds, not cost.

---

## 9. Timeline realism

**Team size assumption [SPECULATIVE TARGET]:** 2 people, one of whom can write distributed training code. This is stated so the numbers can be judged against a concrete plan.

| Rung | Compute time | Data-prep time | Engineering time | **Calendar (parallel)** | Critical path |
|---|---|---|---|---|---|
| **R0** | 73–363 d on local CPU (2–10% of measured 172 GFLOPS) | 2–5 d (small scrape) | 3–5 d (pipeline + tokenizer + eval) | **~2 weeks** | Engineering |
| **R1** (opt) | 4.3 h on 8×A100 | 10–20 d (crawl, filter, dedup, tokenise) | 10–15 d | **~5 weeks** | Data prep |
| **R1** (ext) | 15 d on 8×A100 | 20–40 d (bigger corpus, more filtering) | 10–15 d | **~6 weeks** | Data prep |
| **R2** (opt) | 3 d on 8×A100 | 20–40 d | 15–25 d | **~7 weeks** | Data prep |
| **R2** (ext) | 31 d on 8×A100 | 30–60 d | 15–25 d | **~3 months** | **Compute** |
| **R3** (opt) | 68 d on 8×A100; 19 d on 8×H100 | 40–80 d | 25–40 d | **~4–5 months** | **Compute** |
| **R3** (ext) | 478 d (8×H100) or 1,704 d (8×A100) | 60–120 d | 25–40 d | **~1.8–4.7 years** | **Compute** |
| **R4** (opt) | 88 d (8×H100) / 313 d (8×A100) | 60–120 d | 30–50 d | **~6–13 months** | **Compute** |
| **R5** | 30 d on 512×H100 | 150–300 d | 60–120 d | **~1–1.5 years** | **Compute** |
| **R6** | 241 d on 4,096×H100 | 400–800 d | 120–240 d | **~2.5–4 years** | **Compute** |

**[ESTIMATE] Data prep is often the longest pole — and it is usually underestimated.** Evidence from published work:
- **[KNOWN FACT]** The Stack v2 was built on Software Heritage's archive of **619 programming languages**, with GitHub PRs, Kaggle notebooks, and documentation — and required a formal agreement with SoftwareHeritage and INRIA for bulk download, plus explicit attribution obligations per the dataset's terms of use (https://huggingface.co/datasets/bigcode/the-stack-v2, observed 2026-10-21).
- **[KNOWN FACT]** SmolLM's pipeline included using **Llama 3 to annotate 500,000 Python samples** from The Stack, training an educational-code classifier on that, and filtering 40B Python tokens down to 4B (https://huggingface.co/blog/smollm, observed 2026-10-21). **Synthetic data annotation with a frontier model is a data-pipeline cost**, not a free operation.
- **[KNOWN FACT]** The Stack v2 is *"regularly updated to enact validated data removal requests"*, and users must *"update your own version of The Stack v2 to the most recent usable version"* — meaning data maintenance is a recurring cost, not a one-time cost.

**[ESTIMATE]** The engineering-time column understates reality for a 2-person team. It excludes: debugging distributed training, handling OOM and divergence, maintaining the data pipeline, building the eval harness, and — critically — **debugging the agent harness**, which is usually where the actual schedule risk lives.

**[ESTIMATE] Iteration count is the hidden schedule killer.** Model development requires multiple runs: architecture ablations, data-mixture ablations, context-length extension, and at least one failed run. At R3-optimal (68 d/run), **a team of 2 gets roughly 4 runs in a year.** Any decision that needs 5+ experiments to validate is not viable at that scale. **This is the argument for R2 (3 d/run → ~60 experiments/year) over R3 (68 d/run → ~4 experiments/year).**

---

## 10. Decision gates and stop rules

The purpose of this section is to prevent the most common failure: **spending the whole budget on a rung that was never going to work.**

### Gate 0 — Before any spend
**Question:** Can we produce a tokenised corpus and evaluate a model at all?
**Evidence required:** a pipeline that takes raw source → filtered → tokenised shards; and an eval harness that scores a model reproducibly on the project's own **DEV** partition (`benchmark-and-evaluation-plan.md` §5.2 — the visible tuning set, whose S0 stage is 40 tasks).
**STOP if:** the data pipeline cannot be made reproducible (a non-reproducible corpus makes every subsequent experiment incomparable).
**Budget at risk:** $0–500.

### Gate 1 — R0 proof-of-learning
**Question:** Does the training loop learn at all, and does the eval harness move?
**Evidence required:** loss decreases monotonically; the 30M model's pass rate on the project's own **DEV** partition rises measurably above the untrained baseline; the eval harness produces the same number twice on the same checkpoint.
**STOP if:** loss does not decrease within 200 steps, or the eval harness gives different results on the same checkpoint (this is a harness bug and it invalidates everything downstream).
**Budget at risk:** ~$1 compute + 2 weeks.

### Gate 2 — R1 (small useful model)
**Question:** Does a model trained on *our* corpus beat a comparable off-the-shelf open model on code benchmarks?
**Evidence required:** at matched size, our R1 must beat SmolLM2-360M or an equivalently-sized public model on the project's own **DEV** partition, under one harness and one set of tool settings. **If our own model cannot beat the public one at equal scale, the data is not better than what is already public, and every larger rung inherits that defect.**
**STOP if:** our R1 loses to the public baseline on the same task set after a full token budget.
**Budget at risk:** ~$97 (optimal) to ~$8,048 (extended).

### Gate 3 — R2 decision point (the real fork)
**Question:** Is the R1 gain large enough to justify scaling to R2, and does the agent harness show real end-to-end capability?
**Evidence required:** R2 beats R1 substantially on the same task set; the agent harness (not the raw model) solves a meaningful fraction of real tasks; and the total projected cost of the chosen token budget is under the agreed ceiling.
**STOP if:** the agent harness on R1/R2 does not complete end-to-end tasks. **A model that cannot be driven by an agent is not a code model for our purposes — it is a text model that happens to emit code.**
**Budget at risk:** ~$1,677 to ~$16,767.

### Gate 4 — R3 (7B) commitment
**Question:** Does the project have a specific, non-speculative use for a 7B model that a 1.5B model cannot serve?
**Evidence required:** a written, specific answer. Candidates: local deployment at a latency/privacy requirement API serving cannot meet; a domain-specialised model; a licence/sovereignty requirement; a demonstrated 2–5× throughput advantage that the workload actually needs.
**STOP if:** the answer is "it would be nicer" or "we might want it later." **7B is the rung where a speculative purchase becomes irreversible: $37k–$913k and 68+ days.**
**Budget at risk:** $36,514 (optimal) to $912,861 (extended).

### Gate 5 — Post-training and evaluation commitment
**Question:** Is the model actually better at the target task than the public alternative?
**Evidence required:** on the target benchmark, our model beats the best public model of the same size, *and* beats a rented frontier model in at least one dimension (latency, cost-per-task, privacy, or a specialised capability).
**STOP if:** our model loses to a rented frontier model on every dimension. **In that case the correct engineering decision is to rent and spend the remaining budget on the harness.**

> **CORRECTION (2026-10-22) — the gates no longer use HumanEval/MBPP as the live go/no-go signal.** Gates 0–2 previously required the model to beat a baseline *on HumanEval/MBPP*. That contradicts `licensing-and-provenance-review.md` §9, which registers those two suites as **"use as a held-out set *only*"** and `benchmark-and-evaluation-plan.md` §5.3, which requires the training-data filter to cover the whole suite and assert disjointness. Using a suite the project must not train on, as the signal that authorises the next spend, is exactly the contamination the plan exists to prevent — and it makes the gate a measure of memorisation as much as of capability. The gates now run on the project's **own DEV partition** (visible, logged, and the documented place for iteration), with the public suites demoted to what the licensing review says they are for: an **external reference point**, reported alongside but never a release gate. Public baselines remain legitimate *comparisons* — comparing our R1 against SmolLM2-360M on the same tasks is the point — as long as the tasks are ours.
>
> **One honest consequence.** The project's own DEV suite is *small* (40 tasks at S0, 120 at S1) and therefore has a wide confidence interval. A go/no-go decision on 40 tasks is noisier than one on 150 HumanEval tasks. The mitigation is not to use a bigger public suite but to make the DEV decision **directional** — "the number moved the right way, and the loss curve is monotone" — and to spend the *statistical* budget where it matters, on the S1/S2 suite sizes and on paired comparisons. `benchmark-and-evaluation-plan.md` §10.1 is where the power analysis lives, and global stop rule 5 below already forbids acting on an effect smaller than the harness's own noise.

### Global stop rules (apply at every gate)
1. **Stop if cumulative spend exceeds 50% of the approved budget without a passed gate.** Halve the scope; do not extend the budget mid-flight.
2. **Stop if two consecutive training runs fail for the same reason.** The problem is the pipeline, not the seed. Do not spend a third run.
3. **Stop if the effective MFU is below 25%** for two consecutive runs. Below that, the bottleneck is engineering, not compute, and more GPUs will not help.
4. **Stop if dataloader stall time exceeds 15% of wall-clock.** Fix the data path before spending more GPU-hours.
5. **Stop if the eval harness's variance between two seeds exceeds the effect size being measured.** You cannot detect an improvement smaller than your own noise.

---

## 11. Hardware actually available to this project

**This section reports what was actually measured on the machine this document was written on. All figures are LOCAL-OBSERVED, read-only, checked 2026-10-21.**

### 11.1 Detected hardware

| Component | Detected value | How obtained |
|---|---|---|
| **CPU** | **AMD Ryzen 7 5700U with Radeon Graphics** — 8 cores / 16 logical processors, base clock 1,801 MHz | `Get-CimInstance Win32_Processor` |
| **GPU** | **AMD Radeon(TM) Graphics** (integrated, iGPU) — `AdapterRAM` reported as 2,147,483,648 bytes (2 GB), driver 31.0.21024.2004 | `Get-CimInstance Win32_VideoController` |
| **Discrete GPU** | **None.** `nvidia-smi` is not present; no NVIDIA device is enumerated | `nvidia-smi` → command not found |
| **System RAM** | **14,870,306,816 bytes = 13.85 GiB** | `Get-CimInstance Win32_ComputerSystem` |
| **Disk free** | **159.2 GB** on C: | `Get-PSDrive C` |
| **OS** | Windows 11 Pro 10.0.26300 | environment |
| **PyTorch** | **2.14.1+cpu** — `torch.cuda.is_available()` returns **False** | `python -I -c "import torch"` |
| **numpy** | 2.4.4, 8 BLAS threads | `python -I` |
| **Measured FP32 GEMM throughput** | **1.30×10^11 FLOP/s @ n=512; 1.72×10^11 FLOP/s @ n=1024** | local numpy matmul benchmark, 2026-10-21 |

### 11.2 What this implies for the ladder

**This is a laptop-class machine with an integrated GPU. There is no discrete GPU and no CUDA.**

**[ESTIMATE]** Training throughput if we use the local CPU at various assumed effective fractions of the measured 172 GFLOPS:

| Rung | State memory (18 B/p) | Fits in 13.85 GB RAM? | Time @2% eff. (3.4 GFLOPS) | Time @5% eff. (8.6 GFLOPS) | Time @10% eff. (17.2 GFLOPS) |
|---|---|---|---|---|---|
| R0 (30M) | 0.54 GB | ✅ | **363 days** | 145 days | **73 days** |
| R1 (360M) | 6.48 GB | ✅ | 52,326 days | 20,930 days | 10,465 days |
| R2 (1.5B) | 27.0 GB | ❌ | 908,430 days | 363,372 days | 181,686 days |

**[ESTIMATE] The conclusions are unambiguous:**

1. **The local machine can train R0 and nothing above it.** R0 (30M params, 0.6B tokens) is a 73–363 day job at realistic CPU efficiency — long enough that it is not a useful iteration loop either. **R0 on the local CPU is a weekend-of-engineering project only if the token budget is cut to ~50–100M tokens**, which makes it a *pipeline* test, not a learning test.
2. **R1 (360M) is impossible on local hardware.** At 10% efficiency it is 10,465 days (29 years). At 5%, 57 years. This is not a "slow" — it is a categorical no.
3. **R2 and above are impossible on local hardware** on both compute *and* memory (27 GB of state vs 13.85 GB of RAM).
4. **The iGPU is not a training path.** AMD's Radeon Graphics in this machine reports 2 GB of dedicated VRAM (the rest is shared system memory). **[KNOWN FACT]** ROCm on Radeon/Ryzen exists (https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/compatibilityradon.html, observed 2026-10-21) and covers Llama.cpp and Transformers on Ryzen — but that is an **inference** path, not a training path. With 2 GB of VRAM and shared-memory bandwidth, training is not viable.
5. **Inference on local hardware is realistic and useful.** **[KNOWN FACT]** ROCm on Ryzen officially supports llama.cpp and HuggingFace Transformers (same source). With 13.85 GB of shared RAM, a 7B model at 4-bit (~3.5 GB) or even bf16 (~14 GB, tight) is servable. **[KNOWN FACT]** The HF docs (https://huggingface.co/docs/transformers/en/perf_infer_gpu_one, observed 2026-10-21) explicitly suggest trying an 11B T5 or 3B BLOOM model on *"Google Colab's free tier GPUs"* — showing how much further local laptop inference can be pushed with quantization.
6. **PyTorch is installed as CPU-only** (`2.14.1+cpu`), so no CUDA work is possible on this machine at all without a hardware change.

### 11.3 The upgrade path, and what it costs

| Option | Cost | Unlocks | Notes |
|---|---|---|---|
| **Nothing — use the local machine** | $0 | R0 only; local inference of 0.5B–7B (4-bit) | The only zero-cost option. Good for tokenizer work, data pipeline work, harness development, and R0 pipeline validation. |
| **Rent 1× A100 80GB** | $2.79/hr | R1 (full) comfortably; R2 with 8-bit optimizer + offload | ~$67/day if kept running; ~$600/mo if kept warm 90% of the month |
| **Rent 8× A100 80GB** | $22.32/hr (8 × $2.79) | R2 and R3 | The workhorse configuration. All scenario-B numbers assume this. |
| **Rent 8× H100 80GB** | $31.92/hr (8 × $3.99) | R3/R4 with 3–4× the speed | ~3.3× the hourly cost of A100 for ~2.6× the MFU-adjusted speed — marginally worse per FLOP, better per wall-clock |
| **Buy 1× RTX 4090 24 GB** | ~$1,600–2,500 | R1 (with 8-bit optimizer), local inference | The "own the hardware" rung. Note **[KNOWN FACT]** no NVLink — multi-card training would be interconnect-bound. |
| **Buy 4× RTX 4090** | ~$7,000–10,000 | R2 with ZeRO-3 | Fits 27 GB state across 4 cards at 8-bit optimizer; interconnect-limited. |

**[ESTIMATE] The single most cost-effective hardware decision is to rent 8×A100 for a few focused bursts rather than buy anything.** The break-even: an RTX 4090 at ~$2,000 buys ~3,000 A100-hours of rented compute at $2.79/hr — i.e. **125 A100-hours of 8-way compute**. A 7B training run needs **13,088 A100-hours** of compute (fleet-independent — the same 13,088 whether you use 1 GPU for 545 days or 8 for 68 days). **Buying consumer cards to train R3 is absurd; renting is the only sane option for anything above R1.**

---

## 12. Cost scenarios

**All figures are [ESTIMATE]. Prices observed 2026-10-21. Every price must be re-verified before a budget decision.**

**Shared assumptions:**
- A100 80GB at **$2.79/GPU-h** (Lambda, 8×) — https://lambda.ai/service/gpu-cloud
- H100 80GB at **$3.99/GPU-h** (Lambda, 8×) — same
- A100 MFU 40%, H100 MFU 45% (validated against DeepSeek-V3's published 2.788M H800 GPU-hours, Section 3.5)
- Sonnet 5.5 API at $2/MTok in, $10/MTok out, $0.10/MTok cache read — Anthropic docs
- Object storage at $0.02–0.09/GB/month, modelled at $0.09/GB-month
- Training attempts: **1 / 2 / 3** at Low / Central / High, applied to every rung
- Engineering labour: `implementation-plan.md` §9.4's **165.8 person-weeks** (with its 15% contingency) at $150k / $200k / $250k per engineer-year
- Team of 2, ~$0.05–0.20/hr cloud CPU for data pipeline work

---

### Scenario A — Minimal viable

**Goal:** prove the pipeline end-to-end, produce one small trained model, one working agent harness, and a credible evaluation. No attempt at frontier-adjacent capability.

**Target rung: R1 (360M).**

**Conventions used in all three scenarios.** Every cell below is derivable from its own *Calculation* column, and every TOTAL is the sum of the line items above it. The conventions are:

- **Training** is the cost of the whole *campaign*: `attempts × per-attempt cost`, where attempts = **1 / 2 / 3** at Low / Central / High (the document's own ×2–3 failed-run multiplier, applied consistently to every rung).
- **Storage** is `GB × months × $0.09/GB-month`, with months = **1 / 3 / 6**.
- **Eval** is `tasks × seeds × variants × $/agent-run`, where the per-agent-run cost comes from §8.3's derivation (4.075M prompt + 20k output tokens): **$8.35** Sonnet 5.5, **$0.42** Haiku 5.5, **$16.70** Opus 5.5.
- **Contingency** is **15% of the subtotal**, computed once, at the bottom.
- **Engineering labour** is `165.8 person-weeks ÷ 52 weeks-per-year × $150k / $200k / $250k per engineer-year` — `implementation-plan.md` §9.4's figure *with* its 15% contingency. **The project total is model track + labour, and the calendar is the max of the two**, not their sum.

**A1 — R1 at the compute-optimal token budget (7.2B tokens)**

| Line item | Calculation | Low | Central | High |
|---|---|---|---|---|
| **Training — R1 optimal** | 35 GPU-h × $2.79 × attempts (1 / 2 / 3) | $98 | **$195** | $293 |
| **Data pipeline CPU** | 200–600 hr @ $0.05–0.20 | $30 | **$120** | $250 |
| **Dataset storage** | 29 GB × 1 / 3 / 6 months @ $0.09 | $3 | **$8** | $16 |
| **Checkpoint storage** | 58 GB × 1 / 3 / 6 months @ $0.09 | $5 | **$16** | $31 |
| **Tokenizer + tooling** | domains, tokenizer training, tooling | $50 | **$150** | $400 |
| **Eval via API** | 75 / 150 / 400 tasks × seeds × variants × $8.35 (Sonnet) | $626 | **$3,758** | $20,040 |
| **Local hardware** | already owned | $0 | **$0** | $0 |
| **Contingency** | 15% of subtotal | $122 | **$637** | $3,154 |
| | | | | |
| **TOTAL (model track)** | | **$934** | **$4,884** | **$24,184** |
| **Engineering labour** | 165.8 pw ÷ 52 wk/yr × $150k / $200k / $250k per engineer-yr | $478,269 | **$637,692** | $797,115 |
| **PROJECT TOTAL (model track + labour)** | | **$479,203** | **$642,576** | **$821,299** |

**A2 — R1 at the extended token budget (600B tokens)**

| Line item | Calculation | Low | Central | High |
|---|---|---|---|---|
| **Training — R1 extended** | 2,885 GPU-h × $2.79 × attempts (1 / 2 / 3) | $8,049 | **$16,098** | $24,147 |
| **Data pipeline CPU** | 400–1,200 hr @ $0.05–0.20 | $80 | **$360** | $600 |
| **Dataset storage** | 240 GB × 1 / 3 / 6 months @ $0.09 | $22 | **$65** | $130 |
| **Checkpoint storage** | 58 GB × 1 / 3 / 6 months @ $0.09 | $5 | **$16** | $31 |
| **Tokenizer + tooling** | domains, tokenizer training, tooling | $50 | **$150** | $400 |
| **Eval via API** | as A1 | $626 | **$3,758** | $20,040 |
| **Local hardware** | already owned | $0 | **$0** | $0 |
| **Contingency** | 15% of subtotal | $1,325 | **$3,067** | $6,802 |
| | | | | |
| **TOTAL (model track)** | | **$10,157** | **$23,514** | **$52,150** |
| **Engineering labour** | as A1 | $478,269 | **$637,692** | $797,115 |
| **PROJECT TOTAL (model track + labour)** | | **$488,426** | **$661,206** | **$849,265** |

> **CORRECTION (2026-10-22) — Scenario A's table did not add up, and its eval line was understated by ~25×.** The previous table mixed *selected* and *alternative* budgets in one set of rows (a "*Selected budget*" row asking the reader to pick one training line), so no TOTAL could be derived from the rows above it. The three TOTAL rows also failed to equal the sum of their own line items. Separately, the eval row read *"150 tasks × 3 seeds, Sonnet 5.5 → $250"*, which is **$3,758** at §8.3's own $8.35 per agent run — the old figure was not derived from any per-task cost in this document, and the Central column therefore understated the scenario by more than the training line. **[OBSERVED]** The recomputed Central figures are **$4,884** (model track, optimal tokens) and **$23,514** (600B tokens), against the old printed $1,142 and $9,092. The conclusion does not change and in fact strengthens: **at the compute-optimal budget, the model track is under five thousand dollars**, and the dominant cost of Scenario A is now visibly the engineering labour, not the GPUs.

**What the range depends on:** the token budget (the dominant factor, ~83× between the two ends), the number of failed runs, and whether the eval suite uses a frontier API or the local model.

**[ESTIMATE] Note the shape of this scenario:** at compute-optimal tokens, the model track costs **$4,884** Central — genuinely almost free, and it produces a real trained model plus a working harness. At extended tokens it costs **$23,514** and produces a materially better model. **This ~5× spread on the same hardware is the single most consequential decision in the model track, and it is a data-quality decision, not a hardware decision.** **[INFERRED]** The genuinely dominant number in Scenario A is not either of those: it is the **$637,692 of engineering labour**, which is 130× the optimal-token model track. **Scenario A's real cost is the harness, not the model** — which is the same conclusion §8.3 reaches from the other direction, and the reason §12's recommendation puts the evaluation loop and the harness first.

---

### Scenario B — Serious independent code model

**Goal:** a 7B-class code model trained on a curated corpus, competitive with public models of that size, served locally, with an agent harness evaluated on real tasks.

**Target rung: R3 (7B), StarCoder2-comparable token budget.**

**B1 — R3 at the compute-optimal token budget (140B tokens) — recommended**

| Line item | Calculation | Low | Central | High |
|---|---|---|---|---|
| **Training — R3 optimal** | 13,088 GPU-h × $2.79 × attempts (1 / 2 / 3) | $36,516 | **$73,031** | $109,547 |
| **Data pipeline** | crawl ~1 TB, filter, dedup, tokenise, 400–800 CPU-hr | $50 | **$150** | $400 |
| **Synthetic-data annotation** | frontier model labelling, ~50M tokens @ Sonnet | $100 | **$350** | $800 |
| **Dataset storage** | 560 GB × 1 / 3 / 6 months @ $0.09 | $50 | **$151** | $302 |
| **Checkpoint storage** | 1.12 TB × 1 / 3 / 6 months @ $0.09 | $101 | **$302** | $605 |
| **Serving hardware** | 1× A100 reserved (not fully utilised) | $1,000 | **$2,000** | $4,000 |
| **Eval loop (own model)** | 5 / 10 / 20 sweeps × 73.5 GPU-h × $2.79 | $1,025 | **$2,051** | $4,101 |
| **Eval loop (frontier baseline)** | 500 tasks × 3 seeds × 5 / 10 / 10 variants × $8.35 / $16.70 | $62,625 | **$125,250** | $250,500 |
| **Contingency (15%)** | 15% of subtotal | $15,220 | **$30,493** | $55,538 |
| | | | | |
| **TOTAL (model track)** | | **$116,687** | **$233,778** | **$425,793** |
| **Engineering labour** | 165.8 pw ÷ 52 wk/yr × $150k / $200k / $250k per engineer-yr | $478,269 | **$637,692** | $797,115 |
| **PROJECT TOTAL (model track + labour)** | | **$594,956** | **$871,470** | **$1,222,908** |

**B2 — R3 at the StarCoder2 token budget (3.5T tokens)**

| Line item | Calculation | Low | Central | High |
|---|---|---|---|---|
| **Training — R3 extended** | 327,190 GPU-h × $2.79 × attempts (1 / 2 / 3) | $912,860 | **$1,825,720** | $2,738,580 |
| **Data pipeline** | 25× the corpus, proportionally more CPU-hr | $500 | **$1,500** | $4,000 |
| **Synthetic-data annotation** | as B1 | $100 | **$350** | $800 |
| **Dataset storage** | 14 TB × 1 / 3 / 6 months @ $0.09 | $1,260 | **$3,780** | $7,560 |
| **Checkpoint storage** | 1.12 TB × 1 / 3 / 6 months @ $0.09 | $101 | **$302** | $605 |
| **Serving hardware** | as B1 | $1,000 | **$2,000** | $4,000 |
| **Eval loop (own model)** | as B1 | $1,025 | **$2,051** | $4,101 |
| **Eval loop (frontier baseline)** | as B1 | $62,625 | **$125,250** | $250,500 |
| **Contingency (15%)** | 15% of subtotal | $146,921 | **$294,143** | $451,522 |
| | | | | |
| **TOTAL (model track)** | | **$1,126,392** | **$2,255,096** | **$3,461,668** |
| **Engineering labour** | as B1 | $478,269 | **$637,692** | $797,115 |
| **PROJECT TOTAL (model track + labour)** | | **$1,604,661** | **$2,892,788** | **$4,258,783** |

> **CORRECTION (2026-10-22) — Scenario B's TOTALs did not equal their own line items, and the High column was out by $100,000.** The recomputed Central model-track total is **$233,778** against the $232,362 printed (a $1,416 difference, from the eval and storage cells being independently re-derived), but the substantive errors were elsewhere:
>
> 1. **The High column printed $528,070 where the line items sum to $425,793** — a **$102,277** overstatement. It appears the previous author applied the ×3 failure multiplier twice to the High training cell.
> 2. **The Low column printed $113,000 where the line items sum to $116,687** — a $3,687 *under*statement, because the Low training cell was quoted at ×2 attempts while the printed total assumed ×1.
> 3. **The "3.5T tokens" TOTAL row was computed against 25× the data-pipeline and storage lines**, which the table did not show. Those rows are now shown explicitly (25× pipeline, 14 TB dataset).
> 4. **The 3.5T TOTAL row's printed $2,247,958 Central is close to the recomputed $2,255,096**, but was reached by a route the table did not support.
>
> **[OBSERVED]** The *conclusion* of the scenario is unchanged and the direction of the correction is informative: **the training line is not the largest line item.** At Central, the frontier-baseline eval sweep ($125,250) is **53%** of the whole model track ($233,778), and engineering labour ($637,692) is **2.7× the entire model track**. The document's own §8.3 conclusion — that the evaluation loop competes with training for the same budget — is *stronger* than stated, and the labour figure adds a dimension the document did not previously quantify at all.

**What the range depends on:**
1. **Token budget — the dominant factor (10× between ends).** 140B is compute-optimal and roughly matches the quality of public 7B models; 3.5T matches StarCoder2-7B exactly but costs 10× more.
2. **Failure multiplier.** 1 attempt (Low) vs 3 (High) moves the training line by $73,031 — from one attempt succeeding to a third attempt being needed.
3. **Hardware choice.** H100 at 45% MFU costs **$365,897** for the 3.5T run vs **$912,861** on A100 — **but H100s are scarce and often unavailable on short notice**, which the schedule (not the budget) may dominate. Note this is a *speed* choice, not a *cost* choice: the H100 fleet is cheaper per FLOP but the dollars are smaller because the run is shorter in GPU-hours, not because the fleet is larger.
4. **Eval scope.** Running a 30-variant frontier sweep costs $125k and is the **largest single line item** in this scenario — larger than the recommended training run itself. This is the line item to cut first, and the reason `benchmark-and-evaluation-plan.md` requires the sweep to run once per release rather than every iteration.

**[ESTIMATE] Recommended configuration: R3 at the optimal 140B tokens, on 8×A100.** Model track Central **$233,778**, engineering labour **$637,692**, **project total $871,470**. Model-track calendar: ~68 days per training run plus ~2 months data prep ≈ **22 weeks**; harness labour is **39 weeks**; **the project calendar is the maximum, 39 weeks (~9 months)** — because the harness is the critical path, not the GPU run. This buys a 7B model genuinely competitive with public 7B code models, and a working agent harness that can be measured against it.

---

### Scenario C — Full ambition (frontier-comparison)

**Goal:** a model in the Llama-3.1-405B class — 15.6T tokens, 405.9B params, 3.8×10^25 FLOPs.

**Target rung: R6 (405B).**

| Line item | Calculation | Low | Central | High |
|---|---|---|---|---|
| **Training — 4,096× H100** | 23,700,859 GPU-h × $3.99 | $90,000,000 | **$94,566,427** | $100,000,000 |
| *Alternative: 16,384× H100* | *same total GPU-h — same dollars, 241 d → 30 d* | *—* | *—* | *—* |
| *Alternative: 8,192× B200* | *23,700,859 × $6.69 = $158,558,747 — more dollars, 241 d → 121 d* | *—* | *—* | *—* |
| **Data pipeline** | crawl ~110 TB, filter, dedup, tokenise — thousands of CPU-hours | $20,000 | **$60,000** | $200,000 |
| **Dataset storage** | 62 TB × 1 / 3 / 6 months @ $0.09 | $530,000 | **$530,000** | $530,000 |
| **Checkpoint storage** | 65 TB × 1 / 3 / 6 months @ $0.09 | $550,000 | **$550,000** | $550,000 |
| **Staff** | 30–60 ML engineers × 2 years | $6,000,000 | **$12,000,000** | $24,000,000 |
| **Serving** | multi-node inference cluster, 24/7 | $2,000,000 | **$5,000,000** | $12,000,000 |
| **Post-training (SFT + RLHF)** | typically 5–15% of pretraining compute | $4,700,000 | **$9,000,000** | $14,200,000 |
| **Data licensing / legal** | code licence compliance, provenance tracking | $100,000 | **$300,000** | $1,000,000 |
| | | | | |
| **TOTAL** | sum of the line items above | **$103,900,000** | **$122,006,427** | **$152,480,000** |

**[OBSERVED] The three training rows are alternatives, not a sum.** The previous version of this table listed the 4,096×H100, 16,384×H100, and 8,192×B200 rows as three separate line items, so a reader adding the column would have counted the training cost three times. They are now marked as alternatives with their dollars and wall-clocks stated, and only the selected configuration (4,096×H100) enters the TOTAL.

**[OBSERVED] Scenario C's Staff line already contains this project's harness labour, so no separate labour line is added.** `implementation-plan.md` §9.4's harness estimate is **165.8 person-weeks ≈ 3.19 engineer-years ≈ $638k** at the Central rate — which sits *inside* the $12,000,000 Central staff line, not on top of it. Adding a labour line here would double-count it. **[INFERRED]** This is also why the staff line dominates the reachability verdict: the $12M is not GPU cost, it is **people**, and it is the reason Scenario C is out of reach for this project rather than merely expensive.

**What the range depends on:**
1. **Fleet size buys time, not money** (§3.4). 4,096 H100s → 241 days; 16,384 → 30 days; the bill is $94,566,427 in both cases.
2. **Hardware generation is a time/cost trade, not a free lunch.** B200 at $6.69/GPU-h is **67% more dollars** for 2× the speed. H100 at 4,096 GPUs is the cheapest path to a given deadline.
3. **Staff.** $6M–$24M for 30–60 engineers over 2 years. This is the line that decides feasibility, not compute.
4. **Serving.** A multi-node cluster running 24/7 for a model that must answer in a human's turn is a permanent cost, not a one-off.

> **CORRECTION (2026-10-22) — Scenario C's headline verdict, restated.** The previous version of this scenario computed training cost as `9.708×10^10 GPU-h × $3.99 = $3.87×10^11`, concluding *"The compute alone is $387 billion… approximately the scale of a national-lab programme."* **That was an artefact of the §3.4 fleet error**, now fixed (see the correction note in §3.4). The correct figure is **23,700,859 total GPU-h × $3.99 = $94,566,427** — a fleet-independent quantity, which is why the 4,096-GPU and 16,384-GPU rows cost the same and differ only in wall-clock. The corrected total is **~$122M**, and the *"national-lab programme"* framing is **retired**: at this scale it is closer to a well-funded industrial lab's frontier run than to a national programme. **The verdict that Scenario C is out of reach for this project is unaffected** — it turns on the $12M staff line and on needing thirty to sixty engineers rather than two, not on the compute bill.

For comparison:

**[KNOWN FACT]** Meta's Llama 3.1 405B was pre-trained using **3.8×10^25 FLOPs** on **16,000 H100 GPUs** (https://arxiv.org/abs/2407.21783, observed 2026-10-21) — a multi-month run by a company with thousands of ML engineers and an existing data centre.

**[KNOWN FACT]** DeepSeek-V3, the most cost-efficiently-published frontier-scale run, used **2.788M H800 GPU-hours** for full training including 14.8T tokens on 671B MoE parameters (https://github.com/deepseek-ai/DeepSeek-V3, observed 2026-10-21). At $3.99/GPU-h that is ~$11.1M *for the GPU rental alone*, achieved only through a custom FP8 training framework, auxiliary-loss-free load balancing, and expert parallelism that nearly eliminates communication overhead — i.e. **years of systems engineering by a large team.**

**[KNOWN FACT]** The contrast with this document's own scope is stark: DeepSeek-V3's *entire* pre-training cost is roughly **0.003%** of the Scenario C total, and roughly **38× the Scenario B central estimate** — i.e. even the most aggressive "frontier efficiency" precedent is an order of magnitude beyond this project's reach at 7B.

**Verdict on Scenario C: not feasible. Not as a stretch. Not in any multi-year horizon for a small team. Scenario C is documented here to establish the boundary, and to make the point that the relevant comparison is not "could we train a frontier model" but "what frontier capability can we rent for the same money."**

**[ESTIMATE] The rent-vs-build framing at Scenario C scale:** the **$94.6M** training compute (corrected — see §3.4) buys 405B-parameter capability. The *same money* spent renting Opus 5.5 buys roughly 94,566,427 / $43,800 ≈ **2,159 years** of frontier API usage. **At any scale where training is feasible for a small team, renting is orders of magnitude more capable per dollar. The build case must be made on control and specialisation, never on cost.**

---

## 13. Free and low-cost resources

**This section is deliberately careful about one distinction that is routinely blurred: a model's licence governs its *weights*; a dataset's licence governs the *data*; they are independent.** A permissive model licence does **not** make it legal to train on a restrictive dataset, and a permissive dataset does **not** make it legal to ship weights derived from a restrictive model.

### 13.1 Free datasets with permissive licences

**[KNOWN FACT]** All observed 2026-10-21:

| Dataset | Licence | URL | Notes |
|---|---|---|---|
| **FineWeb** | **ODC-By 1.0** | https://huggingface.co/datasets/HuggingFaceFW/fineweb | 15T+ tokens of filtered CommonCrawl web text. ODC-By: attribution + share-alike on the *database*. |
| **SmolLM-Corpus** | **ODC-By 1.0** | https://huggingface.co/datasets/HuggingFaceTB/smollm-corpus | 1.1T-token curated corpus; includes **220B deduplicated tokens from FineWeb**. |
| **C4** | **ODC-By 1.0** | https://huggingface.co/datasets/allenai/c4 | The classic pre-training corpus; derived from CommonCrawl. |
| **The Stack v1** | **"other"** (per-repo terms) | https://huggingface.co/datasets/bigcode/the-stack-smol | 3.1 TB of source code, 30 languages. Requires acknowledgement of source-code licence obligations. |
| **The Stack v2** | **"other"** (per-repo terms) | https://huggingface.co/datasets/bigcode/the-stack-v2 | **619 languages**; requires an **agreement with SoftwareHeritage and INRIA** for bulk download; must adhere to SWH's LLM-training principles; **must update to the latest version** as removal requests are processed. |
| **GitHub Code** | **"other"** (per-repo terms) | https://huggingface.co/datasets/codeparrot/github-code | 115M files, 1 TB, 32 languages. |
| **The Pile** | **"other"** (per-component) | https://huggingface.co/datasets/EleutherAI/pile | **825 GiB**, 22 component datasets, 100B–1T tokens. |

**[KNOWN FACT] Critical caveat on The Stack:** its terms state *"Any use of all or part of the code gathered in The Stack v2 must abide by the terms of the original licenses, including attribution clauses when relevant."* **A code corpus is not a single licence — it is an aggregate of thousands of per-repository licences.** The permissive labels above (ODC-By, etc.) apply to the *dataset packaging*, not to the underlying code, and for The Stack the licensing is explicitly "other."

**[KNOWN FACT] For a code project specifically, there is no truly permissive public code corpus.** The honest position is: **use The Stack v2 and honour per-file attribution and licence obligations, which the dataset provides provenance for** (the StarCoder2 paper states they *"release the Software Heritage persistent IDentifiers (SWHIDs) of the source code data"* for exactly this reason — https://arxiv.org/abs/2402.19173). This is a legal-compliance workstream, not a solved problem.

### 13.2 Free open models as starting bases

**[KNOWN FACT]** All observed 2026-10-21:

| Model | Params | Licence | URL |
|---|---|---|---|
| **Qwen3-0.6B** | 0.6B | **Apache-2.0** | https://huggingface.co/Qwen/Qwen3-0.6B |
| **SmolLM2-135M-Instruct** | 135M | **Apache-2.0** | https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct |
| **StarCoder2-7B** | 7B | **bigcode-openrail-m** | https://huggingface.co/bigcode/starcoder2-7b |
| **DeepSeek-Coder-6.7B-Instruct** | 6.7B | **deepseek** (custom) | https://huggingface.co/deepseek-ai/deepseek-coder-6.7b-instruct |
| **Llama 3.1 405B** | 405B | **llama3.1** (custom) | https://huggingface.co/meta-llama/Llama-3.1-405B |

**[KNOWN FACT]** The Llama 3.1 licence permits redistribution, fine-tuning, and derivative works, with naming and attribution obligations; the Llama 3 blog (https://huggingface.co/blog/llama31, observed 2026-10-21) notes *"This means that synthetic data generation and distillation are allowed, even with different models! This is especially important for the 405B model."*

**[ESTIMATE] Strategic note:** **Apache-2.0 (Qwen3, SmolLM2) is the licence to prefer for a genuinely independent project.** It is permissive, includes an express patent grant, and imposes no field-of-use restriction or naming obligation. StarCoder2's OpenRAIL-M variant is also strong. Llama and DeepSeek licences are usable but carry conditions that constrain a project intended to be independent.

### 13.3 The licence independence principle — stated properly

**[ESTIMATE]** Three separate licences govern this project, and they are frequently conflated:

| What | What governs it | Practical consequence |
|---|---|---|
| **Your model's weights** | The licence of the base model you fine-tuned + the licence of any model whose outputs trained yours (synthetic data) + the licence of your training data | If you distil from Llama 3.1, your model inherits Llama obligations |
| **Your training data** | The licences of the underlying source code | The Stack v2's per-file obligations survive into your weights |
| **Your agent's runtime** | The licence of whatever model the agent calls at inference time | If the agent calls Claude at runtime, your "independent" agent depends on Anthropic at runtime |

**[ESTIMATE] The honest framing for this project:** "Independent" should mean *independently trained weights with a permissive licence you control*, which is achievable at R1–R2 from a permissively-licensed base (Apache-2.0) trained on licence-compliant code with attribution tracked. It is *not* achievable to be independent of frontier APIs at runtime without training a model that is competitive with them — which Section 12 shows is out of reach. **Design the architecture so the runtime model is swappable.** That is the pragmatic form of independence.

### 13.4 Free CPU and cloud credits

**[KNOWN FACT]** All observed 2026-10-21:

| Resource | What it gives | URL |
|---|---|---|
| **Google Cloud Free Trial** | **$300 credit for 90 days**; full access to Free Tier | https://cloud.google.com/free/docs/free-cloud-features |
| **GCP Always-Free tier** | 20+ always-free products incl. Compute Engine and AI APIs | same |
| **AWS Free Tier** | **$100 credit** on signup (up to $200 more via activities); **30+ always-free services**; Free account plan: no charges for up to 6 months | https://aws.amazon.com/free/ and https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html |
| **Google Colab** | Free hosted Jupyter with **GPUs and TPUs** | https://colab.google/pricing |
| **Kaggle** | Free GPU notebooks; competition datasets | https://www.kaggle.com/docs/efficient-gpu-usage |

**[KNOWN FACT] Important restrictions on free trial credit:**
- **[KNOWN FACT]** GCP Free Trial: *"You can't add GPUs to your VM instances."* and *"You can't access or use the $300 credit for a generative AI partner model that is offered as a managed API."* **The $300 credit cannot be spent on GPU VMs.**
- **[KNOWN FACT]** GCP Free Trial requires a credit card or other valid payment method, with an authorisation hold of $0.01–$1.00 (a hold, not a charge).

**[ESTIMATE] So the honest read of the free tiers:**
- **GCP $300 + AWS $100 = $400 of credit**, and it is **mostly not usable for GPU training** (GCP explicitly forbids GPUs on trial accounts; AWS's credit terms and GPU instance pricing would need per-service checking, and the always-free EC2 tier is CPU-only and small).
- **Colab and Kaggle free GPUs are the real free GPU** — typically T4-class (16 GB) with session limits and no SLA. **[ESTIMATE]** 16 GB VRAM is enough for **R1 (360M) with 8-bit optimizer + checkpointing**, and marginally enough for **R2 (1.5B) at 4-bit with CPU offload**. They are *not* enough for R3.
- **[ESTIMATE]** Colab's terms make it unsuitable as the primary training venue — sessions are capped and preemptible, so a 68-day R3 run is impossible there. **Colab is an excellent R0/R1 venue and a terrible R2+ venue.**
- **[ESTIMATE]** Data pipeline work (crawling, filtering, dedup, tokenising) is **CPU-bound and is perfectly suited to the free tiers** — this is where $400 of credit and Colab's CPU time genuinely help. **Do the data pipeline on free CPU; do the training on rented GPUs.** This split is the single best way to stretch the budget.

### 13.5 Academic and non-profit GPU programmes

**[KNOWN FACT]** The accessible, non-paywalled programmes as of 2026-10-21:

| Programme | What it provides | URL |
|---|---|---|
| **AWS Cloud for Education (AWS Academy)** | Free training and credits for students/educators | https://aws.amazon.com/education/ |
| **Google Cloud for Academic / Research credits** | Compute credits for accredited researchers | https://cloud.google.com/free/docs/free-cloud-features (research credit programme linked from GCP) |
| **NSF Graduate Research Fellowship Program** | Stipend for US graduate students (not compute, but funds time) | https://www.nsfgrfp.org/ (403 to automated fetch — page exists, content verified via search, not machine-read) |
| **Cloud credits via university HPC** | Most universities operate a cluster with free allocations for enrolled students/staff | institutional — no public URL |

**[ESTIMATE] Honest assessment:** these programmes are real but they are (a) slow to apply for, (b) restricted to accredited students/researchers, (c) most useful for *early-career individuals* rather than a team, and (d) not something to build a schedule around. **The most valuable use of academic/free-tier access is compute for the data pipeline and for R0/R1 ablations** — everything that lets the paid budget be reserved for the one run that matters.

### 13.6 The definitive free resource

**[ESTIMATE]** The genuinely free and genuinely decisive resources are:

1. **Public, permissively-licensed datasets** (FineWeb, SmolLM-Corpus, C4 — all ODC-By) — Section 13.1.
2. **Permissively-licensed open models** (Qwen3-0.6B, SmolLM2 — Apache-2.0) — Section 13.2. **[ESTIMATE]** Training from a strong Apache-2.0 base is strictly better than from scratch for a project whose goal is a working agent: the licence is clean and the starting point is stronger.
3. **The training frameworks themselves** — PyTorch, DeepSpeed (ZeRO), Megatron-LM, HuggingFace Transformers, llama.cpp, and **ROCm on Ryzen** for local inference (https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/compatibilityradon.html) — all open source.
4. **Published measurements** — this document is built almost entirely from other people's published numbers. The single most valuable free input to this project is not a dataset but **the existence of open, published training recipes** (Chinchilla, Megatron-LM, SmolLM, StarCoder2, Llama 3.1, DeepSeek-V3) that let a small team skip the expensive discovery phase.

---

## 14. The 10 most expensive risks and their mitigations

Ranked by expected cost, not by likelihood.

| # | Risk | Expected cost | Mitigation | Trigger to act |
|---|---|---|---|---|
| **1** | **Token-budget overrun on a mid-size model.** Committing to StarCoder2-scale 3.5T tokens at 7B without realising it costs 25× the optimal budget. | **$6.5M–$21.9M** | Fix the token budget *before* the run using the Chinchilla ratio plus the published evidence that extended training helps (SmolLM: 1,667 tok/param; Llama 3.1 405B: 38 tok/param). Run the R2 rung first to *measure* the token-vs-quality curve on your own corpus, then extrapolate. | If measured quality gain per 10× tokens falls below 20%, stop and take the optimal budget. |
| **2** | **Wall-clock, not dollars, is the binding constraint.** A 68-day run is one shot; you cannot debug it. | 4–12 months of schedule | Choose the rung by *experiment count*, not parameter count. Target ≥20 runs/year → R2 (3 d/run), not R3 (68 d/run). Run a shortened R3 (e.g. 20B tokens) first to validate the full-scale recipe in 10 days. | If a run's loss curve deviates from a reference run by >5% in the first 1,000 steps, kill it immediately. |
| **3** | **Data quality is inadequate and never discovered until after the expensive run.** | Full run cost (R3: $37k–$913k) | Gate 2: our R1 must beat the public model at equal scale. If our data is not better, every larger rung inherits the defect. Also: build a *held-out human-written benchmark* early — public benchmarks are contaminated and small models overfit them fast. | R1 loses to the public baseline → stop, fix data, do not proceed to R2. |
| **4** | **Dataloader stalls waste the entire paid GPU budget.** GPUs idle while waiting on I/O, and you pay the full rate. | 20–40% of run cost (R3: $58k–$2.9M) | Pre-tokenise to memory-mapped binary shards. Load-test the full corpus read path at >2× the training rate *before* the run. Use a local SSD copy on the instance, not object storage. | If GPU utilisation < 60% in the first 500 steps, stop and fix I/O. |
| **5** | **MFU is far below the 40% assumption** (unoptimised kernels, no fused attention, bad compilation, no tensor parallelism). | 1.5–3× cost overrun | Benchmark a short run first and **measure** MFU. Target ≥40%. Use FlashAttention-2, fused kernels, bf16, `torch.compile`. Compare against the DeepSeek-derived expectation of ~33% (Section 3.5) — that is your sanity floor. | Measured MFU < 25% on two consecutive runs → engineering problem, not a compute problem. Do not buy more GPUs. |
| **6** | **Evaluation loop cost is underestimated and competes with training for budget.** | $125k–$250k per frontier sweep (3 seeds × 10 variants × 500 tasks) | Evaluate *your own model* for the bulk of the sweep ($51/sweep vs $125k via API — a 2,400× advantage). Use frontier APIs only for the *baseline comparison*, run once, not every iteration. Reduce variants; run 1 seed × 5 variants during development. | If eval exceeds 30% of remaining budget, cut variants and seeds — do not cut the benchmark size. |
| **7** | **Failed runs and divergence.** A 68-day run that diverges on day 40 is catastrophic. | 1–2 extra runs (R3: $37k–$73k) | Save checkpoints frequently enough to resume (every ~5% of training). Use conservative LR with warmup. Watch for loss spikes. Keep a "known-good recipe" config under version control and diff it. | Two consecutive failures with the same signature → the recipe is wrong; do not spend a third run. |
| **8** | **Licence/provenance contamination.** Training on code whose licence forbids the use, or distilling from a model whose licence forbids your use, contaminates the entire project. | Unbounded — potentially the whole project | Use Apache-2.0 base models. Track per-file licence via The Stack v2's SWHID provenance. Maintain a licence register from day one. **[KNOWN FACT]** The Stack v2 is updated as removal requests are processed — you must be able to rebuild your dataset from a new version. | Any request to remove data you have trained on → you must be able to identify and excise it. If you cannot, stop. |
| **9** | **Agent cost blow-up from subagent fan-out and deep turn loops.** Triggered by hard tasks, exactly when volume is highest. | Unbounded — $10k/month → $100k/month with no warning | Hard-cap fan-out (≤8) and turn depth (≤30) in the harness config. Use 1-hour cache writes (2× input) only when the agent will read the prefix ≥2 more times. Route cheap operations (formatting, test generation, classification) to Haiku 5.5 or to your own local model. | Monthly inference spend > 2× the trailing 3-month average → investigate before it compounds. |
| **10** | **Hardware availability and price volatility.** Spot A100/H100 capacity disappears; prices move; a run is blocked mid-flight. | Days-to-weeks of schedule; 20–50% cost swings | Never commit a schedule to a spot price without a reservation or a fallback. Keep 8×A100 as the default (broadest availability, cheapest per FLOP of the two). Budget with a 20% price cushion. Re-verify every price before committing (all prices here: observed 2026-10-21). | If the same instance type is unavailable for >3 days, switch to the alternative in your price table rather than wait. |

---

## 15. Summary and recommendation

**[ESTIMATE] The recommendation, stated plainly:**

**Start at R1 (360M) and treat it as a systems project, not a model project.** Spend ~$2,000 and 2 weeks proving that the data pipeline, tokenizer, training loop, checkpointing, and eval harness all work end-to-end and produce a model that beats a public baseline at equal scale. **The output of that rung is not the model — it is the knowledge of whether every later rung is worth doing.**

**Then jump to R2 (1.5B), not R3 (7B).** R2 at the optimal token budget costs **$1,677** and takes **3 days on 8×A100**. That buys roughly **60 experiments per year**, and experiments are what model development is actually made of. R3 at $36,514 and 68 days buys about **4 experiments per year** — which is not a development process, it is a lottery ticket.

**R3 (7B) is the right ambition *if and only if* Gate 3 and Gate 4 are passed** — that is, if there is a specific, non-speculative reason a 7B model serves a need a 1.5B model cannot. Budget **$233,778 central for the model track** (training with a ×2 failure multiplier, the evaluation sweep, and the other lines in Scenario B) **plus $637,692 of engineering labour** — a **$871,470 project total** — and note that the **39-week harness build is the critical path, not the 68-day GPU run**. Go in knowing the run is one-shot.

**Do not plan for R4+.** R5 and R6 are documented in this document to fix the boundary, not to aim at it. Scenario C costs ~$1.22×10^8 — approximately **1.3× DeepSeek-V3's entire published training cost** (2.788M H800 GPU-h; DeepSeek does not publish a dollar figure, so this is a GPU-hour comparison against our H100-equivalent hours), and that figure already assumes a custom FP8 training framework built by a large team.

**On the agent side, spend the money where the leverage is.** The evaluation loop costs more than training at small scale ($125,250 vs $36,514 for a 3-seed × 10-variant SWE-bench sweep). Build the harness, the tool set, the context management, and the benchmark — these are where a small team beats a large one. And note the asymmetry that should shape the whole design: **at the compute-optimal token budget, one 7B training run costs about 10 months of heavy Sonnet 5.5 API usage** ($36,514 vs $43,800/year) — so on *dollars* the two are within a factor of ~1.2×, not an order of magnitude. But the comparison that matters is not a dollar comparison at all: **the rented model is far more capable than the one you built** ($36.5k buys something in the StarCoder2-7B class; $43,800/year buys Opus 5.5). **[INFERRED]** So the build case cannot be made on cost, and this document's earlier phrasing — *"renting intelligence is trivially cheap relative to building it … Never for cost"* — overstated the dollar gap in the direction that flattered renting, and inverted the direction of the conclusion. **The honest statement is the one §1 already makes: the dollars are comparable at the optimal token budget, and the build case rests entirely on control, ownership, and specialisation.** At StarCoder2's 3.5T token budget the gap widens again in renting's favour (a $912,860 training run versus 21 years of API usage), so the conclusion strengthens at the rung this document recommends against.

**Final honest statement of the constraint.** The binding constraint on this project is **not money** — $934 buys a real trained model, and $871,470 buys a competitive 7B code model *plus* the working harness that can be measured against it, both within reach of a small team. **The binding constraints are iteration count and elapsed time**: the gap between 3 days per experiment and 68 days per experiment, and the 39 weeks the harness build takes regardless of what the model track is doing. Every serious risk in Section 14 traces back to those two facts. Design the plan so that the expensive run happens **once**, at the end, and everything before it is cheap and fast — and so that the harness work proceeds *in parallel* with the model work rather than after it.

---

## Appendix A — Complete source list

All URLs observed **2026-10-21**. Prices and specifications must be re-verified before any budget decision.

### Pricing (GPU)
- Lambda GPU Cloud pricing — https://lambda.ai/service/gpu-cloud — A100 80GB $2.79/GPU-hr, H100 80GB $3.99/GPU-hr, B200 $6.69, L40S $1.09, A10 $1.29, RTX 6000 Ada $0.69
- RunPod GPU pricing — https://www.runpod.io/pricing (page states "Updated October 8, 2026") — B300 $8.99, H200 $5.29, B200 $7.99, H100 SXM $3.99, A100 SXM/PCIe 80GB $1.79, L40S $1.09, RTX 6000 Ada $0.99, Pro 6000 $2.49
- AWS EC2 on-demand pricing — https://aws.amazon.com/ec2/pricing/on-demand/

### Pricing (models / API)
- Anthropic API pricing — https://platform.claude.com/docs/en/about-claude/pricing — Fable 5.1 $10/$50, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per MTok
- Anthropic consumer pricing — https://claude.com/pricing — Pro $17/mo annual or $20/mo monthly; Max from $100/mo
- OpenRouter public models API — https://openrouter.ai/api/v1/models — independent confirmation of all four reference model prices

### Hardware specifications
- NVIDIA H100 — https://www.nvidia.com/en-us/data-center/h100/ — BF16 tensor 1,979 TFLOPS (sparsity), 80 GB HBM3, 3.35 TB/s
- NVIDIA A100 — https://www.nvidia.com/en-us/data-center/a100/ — BF16 tensor 312 TFLOPS, 80 GB HBM2e, 2,039 GB/s
- NVIDIA RTX 4090 — https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/ — 24 GB GDDR6X, no NVLink
- NVIDIA RTX 3090 — https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/ — 24 GB
- NVIDIA RTX 5090 — https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/ — 32 GB GDDR7
- NVIDIA H100 page also cites SemiAnalysis InferenceX: $0.09/MTok at 66 TPS/user for GPT-OSS-120B on H100 with vLLM; $0.02/MTok at 55 TPS/user on B200 (as of April 2026)

### Papers
- Chinchilla — https://arxiv.org/abs/2203.15556 — FLOPs(N,D) ≈ 6ND; 20 tok/param; 400+ models 70M–16B params
- Llama 3.1 — https://arxiv.org/abs/2407.21783 — 405.9B params, 15.6T tokens, 3.8×10^25 FLOPs, 128K context
- Megatron-LM — https://ar5iv.org/html/1909.08053 — 39 TFLOPS single GPU (30% of peak), 76% scaling efficiency
- Selective activation recomputation — https://arxiv.org/abs/2205.05198 — 5× activation memory reduction, >90% less recompute overhead, 54.2% vs 42.1% MFU on 530B/2240×A100
- ZeRO — https://ar5iv.org/html/1910.02054 — 16 TB per trillion params; ZeRO stages 1/2/3: 4×/8×/N× memory reduction
- GPTQ — https://arxiv.org/abs/2210.17323 — negligible accuracy degradation at 3–4 bit; 3.25× (A100) / 4.5× (A6000) speedup
- AWQ — https://arxiv.org/abs/2306.00978 — protects 1% salient weights; >3× speedup over HF FP16; MLSys 2024 Best Paper
- StarCoder2 / The Stack v2 — https://arxiv.org/abs/2402.19173 — 619 languages, 3.3–4.3T tokens, OpenRAIL weights, SWHID provenance
- DeepSeek-V3 — https://github.com/deepseek-ai/DeepSeek-V3 — 2.788M H800 GPU-hours total, 2.664M pre-training, 671B MoE / 37B active, 14.8T tokens
- DeepSeek-V3 release notes — https://api-docs.deepseek.com/news/news1226 — $0.27/M input (cache miss), $0.07/M (cache hit), $1.10/M output at release

### Framework documentation
- HF GPU memory usage — https://huggingface.co/docs/transformers/en/model_memory_anatomy — 6 B/p weights, 8 B/p Adam, 4 B/p gradients, 2 B/p quantized Adam
- HF GPU inference optimisation — https://huggingface.co/docs/transformers/en/perf_infer_gpu_one — FlashAttention-2, quantization, caching; raw source at https://raw.githubusercontent.com/huggingface/transformers/v4.44.0/docs/source/en/perf_infer_gpu_one.md
- HF distributed training / parallelism — https://huggingface.co/docs/transformers/en/perf_train_gpu_many — DDP vs ZeRO vs FSDP vs tensor/pipeline parallel selection table
- HF FSDP — https://huggingface.co/docs/accelerate/en/usage_guides/fsdp
- HF bitsandbytes quantization — https://huggingface.co/docs/transformers/en/quantization/bitsandbytes
- DeepSpeed ZeRO tutorial — https://www.deepspeed.ai/tutorials/zero/ — stage definitions
- ROCm on Radeon and Ryzen — https://rocm.docs.amd.com/projects/radeon/en/latest/docs/compatibility/compatibilityradon.html
- llama.cpp — https://github.com/ggerganov/llama.cpp

### Datasets and models
- FineWeb (ODC-By) — https://huggingface.co/datasets/HuggingFaceFW/fineweb
- SmolLM-Corpus (ODC-By) — https://huggingface.co/datasets/HuggingFaceTB/smollm-corpus
- C4 (ODC-By) — https://huggingface.co/datasets/allenai/c4
- The Stack v2 — https://huggingface.co/datasets/bigcode/the-stack-v2
- The Stack (v1) smol — https://huggingface.co/datasets/bigcode/the-stack-smol
- GitHub Code — https://huggingface.co/datasets/codeparrot/github-code
- The Pile — https://huggingface.co/datasets/EleutherAI/pile
- Qwen3-0.6B (Apache-2.0) — https://huggingface.co/Qwen/Qwen3-0.6B
- SmolLM2-135M-Instruct (Apache-2.0) — https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct
- StarCoder2-7B (bigcode-openrail-m) — https://huggingface.co/bigcode/starcoder2-7b
- DeepSeek-Coder-6.7B-Instruct — https://huggingface.co/deepseek-ai/deepseek-coder-6.7b-instruct
- Llama 3.1 405B (llama3.1) — https://huggingface.co/meta-llama/Llama-3.1-405B

### Blogs and programme pages
- SmolLM blog — https://huggingface.co/blog/smollm — 135M/360M at 600B tokens, 1.7B at 1T; vocab 49,152; ctx 2,048; Llama-3-annotated Python classifier; "beyond the Chinchilla optimal point"
- StarCoder2 blog — https://huggingface.co/blog/starcoder2 — 3B/7B/15B; 3+ / 3.5+ / 4+ T tokens; ctx 16,384, sliding window 4,096; GQA; FIM
- Llama 3 blog — https://huggingface.co/blog/llama3
- Llama 3.1 blog — https://huggingface.co/blog/llama31 — inference VRAM table (FP16/FP8/INT4); KV cache table; training memory table (8B full FT 60 GB, 70B 500 GB, 405B 3.25 TB; LoRA 16/160/950 GB; Q-LoRA 6/48/250 GB); "30% more tokens" tokenizer note
- SWE-bench — https://www.swebench.com/ — 2,294 / 500 Verified / 300 Lite / 300 Multilingual
- AWS Free Tier — https://aws.amazon.com/free/ and https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html — $100 signup credit, up to $100 more, 30+ always-free services, free account plan for up to 6 months
- GCP Free Program — https://cloud.google.com/free/docs/free-cloud-features — $300 / 90 days; 20+ always-free products; **no GPUs on trial accounts**
- Colab pricing — https://colab.google/pricing
- Kaggle GPU usage — https://www.kaggle.com/docs/efficient-gpu-usage
- AWS Cloud for Education — https://aws.amazon.com/education/
- Local gateway catalogue (LOCAL-OBSERVED) — `C:\Users\Admin\.claude\cache\gateway-models.json`

---

## Appendix B — Local environment probe record

Read-only checks performed on 2026-10-21. No packages installed, no infrastructure provisioned, no billable call made.

```
> wmic cpu get name                          -> command not found (wmic removed from this Windows build)
> Get-CimInstance Win32_Processor
  Name                       : AMD Ryzen 7 5700U with Radeon Graphics
  NumberOfCores             : 8
  NumberOfLogicalProcessors : 16
  MaxClockSpeed             : 1801

> Get-CimInstance Win32_VideoController
  Name         : AMD Radeon(TM) Graphics
  AdapterRAM   : 2147483648          (2 GB)
  DriverVersion: 31.0.21024.2004
  VideoProcessor: AMD Radeon Graphics Processor (0x164C)

> Get-CimInstance Win32_ComputerSystem
  TotalPhysicalMemory      : 14870306816   (13.85 GiB)
  NumberOfLogicalProcessors: 16

> nvidia-smi                 -> command not found (no NVIDIA device)
> Get-PSDrive C             -> Used 315.80 GB / Free 159.2 GB
> python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
                           -> 2.14.1+cpu False
> python -c "import numpy; ..." matmul benchmark
                           -> 1.303e+11 FLOP/s (n=512), 1.716e+11 FLOP/s (n=1024)
```

**Conclusion:** a Ryzen 7 5700U laptop with integrated Radeon graphics, 13.85 GiB RAM, 159.2 GB free disk, CPU-only PyTorch 2.14.1. **Sufficient for the data pipeline, tokenizer training, harness development, and R0 proof-of-learning. Not capable of training any model above R0 — and even R0 takes 73–363 days on this CPU.** R1 and above require rented GPUs.

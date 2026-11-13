# LLM Research Review — Adversarial Review of the Model-Development Plan

> **Status:** planning document. No training was started, no model was trained, no billable call was made, no infrastructure was provisioned, to produce it.
> **Companion documents:** `llm-development-roadmap.md`, `model-architecture-proposal.md`, `compute-feasibility.md`, `training-data-plan.md`, `benchmark-and-evaluation-plan.md`, `agent-and-model-boundary.md`, `licensing-and-provenance-review.md`.

---

## 0. What this document is, and — more importantly — what it is not

**This is a local adversarial review.** It was produced by a review pass running on the same model that authored the documents under review, in the same environment, with no additional authority. It is **not** a Claude Fable 5.1 review.

**Fable 5.1 was not invoked, and is not claimed anywhere in this project.** The user's instruction was explicit: *"Do not make billable API calls, enable billing, or create paid infrastructure without my explicit approval. If Fable 5.1 cannot be invoked, do not pretend it was used; label that review as unavailable and prepare a separate adversarial review using the available capabilities."* That approval has not been given, so the Fable 5.1 review is labelled **UNAVAILABLE** and this document is the substitute the instruction asked for.

**The standing rule about agreement, stated once and applied throughout.** The user's instruction was: *"Do not treat agreement between two models as proof that a claim is true."* This is not a formality here, because it bears directly on the weakness of this document: a review by the same model family is **correlated** with what it is reviewing. Where a finding below is a criticism, that criticism stands on its own argument and can be checked against the cited document. Where a finding is a *confirmation*, it carries **no** evidentiary weight, and it is marked as such.

**Three consequence rules are applied to every finding below.**

| Rule | Meaning |
| :- | :- |
| **Checkable** | A finding must point at a specific document, section, and number that a reader can go and look at. "This seems ambitious" is not a finding. |
| **Label the basis** | Every finding states whether it rests on a *measured* value, an *arithmetic* derivation, a *documentary* inconsistency, or a *judgement*. These are not equally strong, and the document says which is which. |
| **Consequence, not complaint** | A finding that cannot change a decision, a number, a gate, or a test is not a finding. Every finding below names the change it implies. |

**The review's own honesty about its limits** appears in §7. This review had access to the documents, to the project's own arithmetic-checking scripts, and — for the evidence-side claims — to the **cached reference documentation** in `agent-reference-shots/`, so that a claim about the reference product could be checked against the reference rather than argued about. It did **not** have access to a trained model, to benchmark results, or to any evidence about the reference model's internal behaviour — and no finding pretends otherwise.

---

## 1. Executive summary

The model-development plan is unusually well-disciplined for a document of its kind. It is tagged (`[KNOWN FACT]` / `[ESTIMATE]` / `[SPECULATIVE TARGET]` / `[OBSERVED]` / `[INFERRED]` / `[UNKNOWN]`), it keeps a ledger of its own claim counts, it enumerates its own unknowns with the evidence that would settle each, and it states in its own §1.3 that no performance is claimed. That is the right shape, and it is rare.

**The review's central judgement is that the plan's architecture choices are sound, its gate structure is stronger than a first reading suggests, and its single most consequential weakness is a specific, checkable arithmetic inconsistency in one table — not a design flaw.**

**The findings that would change decisions if unaddressed:**

| # | Finding | Basis | Consequence |
| :- | :- | :- | :- |
| F1 | **`llm-development-roadmap.md` §7.3's Stage E table is internally inconsistent.** Its `6ND` value, GPU-hours, wall-clock and cost are the `compute-feasibility.md` **R2-opt row for N = 1.5 B** copied verbatim, but paired with a **different parameter count (1,149,337,600)** in the same row. At the row's own stated parameters the `6ND` is 2.069 × 10²⁰, not 2.70 × 10²⁰ — a **1.31× discrepancy** that flows into the GPU-hours, the wall-clock, and the cost. | Arithmetic | Correct the row; the R2 wall-clock falls from 3.1 d to **2.40 d** and the cost from $1,677 to **$1,285**. |
| F2 | **The `20 tok/param` budget is the most consequential number in the plan and is tagged `[ESTIMATE]` — but it *is* derived, with a cited source and a table of alternatives.** The review's first draft held that it was under-derived; that was **wrong**, and §5 records the correction. What survives is narrower and real: the plan never says **which arm of its own ablation** it is betting on. | Documentary | Say which arm, so the 4× sensitivity is visible at the point where it binds. |
| F3 | **The roadmap's own §0.4 fleet-independent cost correction is correct — but `compute-feasibility.md` §3.4 was never patched, so the two documents still disagree by 8× on every dollar figure.** The roadmap says "recorded here rather than silently patched upstream"; the upstream still carries the old numbers. | Arithmetic + documentary | Decide: patch upstream, or make the divergence explicit and cross-referenced in both. |
| F4 | **The tokenizer's benefit is measured in the wrong currency for this product.** Stage A's exit criterion is *chars/token* — the right metric for pretraining, the wrong one for a **context-limited agent**, where the binding resource is tokens-per-context-window. | Judgement (strong) | Add a second metric: tokens per unit of *task-relevant content* on code. |
| F5 | **The licence-cleanliness requirement is absolute, and the plan's `U6` records that whether a clean corpus exists at scale is unknown — with no contingency path stated.** | Documentary | State the contingency; start the corpus search at Stage A, not Stage D. |
| F6 | **`U9` is correctly unanswerable, and the plan has the admissible substitute available and unused** — the project's own black-box captures. | Judgement | Cite the captures where the roadmap reasons about production-agent behaviour. |
| F7 | **The evaluation plan's gates are strong, but Gate 1/2's use of HumanEval/MBPP as the live go/no-go signal contradicts `licensing-and-provenance-review.md` §9's own instruction to use them "as a held-out set only".** | Documentary | Use a project-built held-out set for the gates; keep the public sets as secondary evidence. |

**Two of the review's initial findings were refuted by checking, and are recorded as such** (§5). A review that only reports what it confirmed would have been less useful and less honest than one that reports its own errors.

**No finding contradicts the plan's direction.** Four strengthen it (F4, F5, F6, F7); two correct numbers (F1, F3); one narrows a claim (F2).

---

## 2. What was reviewed, and how

### 2.1 The documents in scope

| Document | Size at review | Role |
| :- | :- | :- |
| `llm-development-roadmap.md` | 162,564 B, 1,326 lines | Stages A–K, the lever attribution, the claim ledger |
| `model-architecture-proposal.md` | 100,297 B | The architecture decision and its derivations |
| `compute-feasibility.md` | 100,479 B, 1,081 lines | The R0–R6 rung ladder, hardware, costs, Gates 0–5 |
| `training-data-plan.md` | 109,909 B | Corpus, filtering, dedup, contamination control |
| `benchmark-and-evaluation-plan.md` | 192,782 B | The task suite, oracles, paired statistics |
| `agent-and-model-boundary.md` | 147,197 B | The `AMB-2xx`/`AMB-3xx` load-bearing rules |
| `licensing-and-provenance-review.md` | 59,360 B | The licence reasoning this plan cites |

### 2.2 The method

1. **Arithmetic re-derivation.** The architecture's parameter count, the FLOPs, the GPU-hours, the wall clocks, the dollar figures, the KV-cache size, and the token counts were re-derived independently from the stated shapes rather than accepted. **Result: the architecture proposal's budget reproduces exactly; the roadmap's Stage E table does not.**

2. **Cross-document consistency.** Every load-bearing claim appearing in more than one document was checked for agreement — the vocabulary size, the parameter count, the context length, the token budget, the stage names, the `AMB-` rule numbers, the **cost convention**. **Result: one discrepancy already recorded by the project as `OPEN-A1` (vocabulary), one unrecorded 8× cost divergence (F3), one unrecorded table inconsistency (F1).**

3. **Adversarial pass by lens.** Each load-bearing decision was attacked with a specific question: *what would have to be true for this to be wrong?* Four independent lenses ran (model/training, evaluation/measurement, evidence/provenance, security/clean-room); the security lens's findings were already reconciled in `security-plan.md` §1.6, and the evidence lens's findings are re-tested against the cached reference in §5.3.

4. **Gate-hunting.** Every "gate", "stop rule", "trigger", and "only when" was extracted and asked: **what number makes this gate fail?** This produced two *refutations* of the review's initial position (§5.1, §5.2).

5. **Ground-truth checking against the reference.** Where a finding was about the reference product, it was checked against `agent-reference-shots/docs-cache/` rather than argued. Three findings were refuted this way (§5.3).

### 2.3 What the review did *not* do

- It did not train, fine-tune, or evaluate any model.
- It did not benchmark anything against any reference model.
- It did not make any billable call, and did not consult Fable 5.1.
- It did not re-derive the corpus's licence analysis; that is `licensing-and-provenance-review.md`'s job.
- It did not re-verify the reference product's behaviour by observation; it checked the plan's *citation discipline* and, where the reference documentation was cached locally, the *specific factual claim*.

---

## 3. The findings in detail

### F1 — The Stage E compute table is internally inconsistent

**Basis: arithmetic.** **Severity: high.** **Status: CONFIRMED by re-derivation.**

**What the document says.** `llm-development-roadmap.md` §7.3 presents, for "R2 — Config B (1.149B)":

| | **R2 — Config B (1.149B)** |
|---|---|
| **Params** | 1,149,337,600 |
| **Tokens (Chinchilla-optimal, 20 tok/param)** | 23.0 B (use 30B) |
| **6ND** | 2.70 × 10²⁰ |
| **Per-GPU hours (A100 @ 40% MFU)** | 601 |
| **Total GPU-h (8×A100)** | 4,808 |
| **Wall-clock (8×A100)** | **3.1 days** |
| **Cost (8×A100, corrected)** | **$1,677** |

**What the arithmetic gives.** Every one of those numbers is `compute-feasibility.md` §3.4's **R2-opt row for N = 1.5 × 10⁹**, copied unchanged — but into a row whose stated parameter count is **1,149,337,600**. Recomputing at the row's *own* stated parameters:

```
6ND       = 6 × 1,149,337,600 × 30e9 = 2.0688e20      (table says 2.70e20)   <- 1.305x off
billed h  = 2.0688e20 / (312e12 × 0.40) / 3600 = 460.5 GPU-h  (table says 601)
wall 8GPU = 460.5 / 8 / 24 = 57.6 h = 2.40 days          (table says 3.1 d)
cost      = 460.5 × $2.79 = $1,285                      (table says $1,677)
```

**And the reverse test.** The table's own `6ND = 2.70 × 10²⁰` at D = 30 B implies **N = 1.50 × 10⁹**, which is `compute-feasibility.md`'s N exactly — not the 1.149 B the row claims. So the row is internally contradictory in both directions: its parameters imply one `6ND`, and its `6ND` implies different parameters.

**Why this matters.** This is the row that carries Stage E's schedule and Stage E's headline cost. The error is *conservative* — the table overstates both wall-clock and cost by ~1.3× — so no decision is made unsafe by it. But the roadmap's §0.4 makes a point of the cost convention being fleet-independent, and it then copies a row that violates its own correction, and the project's whole posture is that a number that cannot be re-derived is a number that cannot be trusted. A 1.3× error in the single most-quoted row of the model plan is exactly the class of defect this project has been built to catch.

**The change this implies.** Recompute the R2 row at N = 1,149,337,600 (6ND = 2.069 × 10²⁰, 460.5 GPU-h, 2.40 d, $1,285) **and** recompute the R3 row, which has the mirror-image defect: it states N = 7,248,019,456 but its `6ND = 5.88 × 10²¹` implies N = 7.0 × 10⁹, and its "Total GPU-h (8×A100)" of 104,701 is **not** 13,088 × 8 — it is 104,704, but the per-GPU figure of 13,088 × 8 GPUs is itself the fleet-independent total, so "Total GPU-h" and "Per-GPU hours" are the same number under two names. Add the arithmetic next to the table so the next reader does not have to re-derive it.

---

### F2 — The 20 tok/param budget: the review's initial claim was **refuted**

**Basis: documentary.** **Severity: medium** (downgraded from the review's first draft, which called it high).

**What the review first asserted.** The first draft of this review held that the 20 tok/param budget was "load-bearing and under-derived" — presented as an estimate without a derivation that survives scrutiny.

**What the check found.** That claim was **wrong**. `model-architecture-proposal.md` §4.6 carries:

- A **source** for the ratio: arXiv:2203.15556 (Chinchilla), verified 2026-10-21, with the scaling-law basis at arXiv:2001.08361 and a `C = 6ND` validation against Llama 3.1 405B at arXiv:2407.21783.
- A **sensitivity table**, not a point estimate: 20 / 50 / 100 / 200 tok/param, each with its own FLOPs, GPU-hours, wall-clock and cost.
- An **explicit statement that 20 is a starting point for code, not a settled optimum**: arXiv:2305.16264 and arXiv:2402.19173 (StarCoder2) are cited for the fact that code data is scarcer and more repetitive than prose, and the document says *"the token-budget axis is itself an ablation"* with named arms (S2.1/S2.3).
- A **failure multiplier** ($1,969–$2,953 for a 2–3× failed campaign) applied to the base figure.

This is better documentation than the review credited. **The finding is retracted as originally stated.**

**What survives, and is worth writing down.** The `[ESTIMATE]` tag is honest — the ratio is a *convention* with a source, not a derivation for this corpus. The sensitivity is real: at 200 tok/param (StarCoder2-class) the same shape costs **$9,844 and 18.4 days** instead of $984 and 1.84 days. The plan says the axis is an ablation but **never states which arm it is currently betting on**, and the Stage E table (F1) is computed at 30 B tokens = 26 tok/param, which is neither of the tabulated arms. So the review's narrower point survives:

**The change this implies.** One sentence in §7.3 stating the current arm and its consequence: "at 30 B tokens (26 tok/param) the run is 2.40 d and $1,285; the 200 tok/param arm would be 14.7 d and $5,204." A reader deciding whether to fund the next rung needs to know which arm the numbers on the page are, and the page's own numbers match no arm.

---

### F3 — The cost convention was corrected in one document and not the other

**Basis: arithmetic + documentary.** **Severity: high.** **Status: CONFIRMED.**

**What the roadmap says.** `llm-development-roadmap.md` §0.4 states that `compute-feasibility.md` §3.4's **cost column is inflated by the fleet size** — that billed GPU-hours for a fixed FLOP budget are fleet-independent (`cost = (C/r)/3600 × price`, the `f` cancels) — and it proves the point against two published anchors:

| Anchor | Published | Under §3.4's convention | Under the fleet-independent convention |
|---|---|---|---|
| Llama 3.1 405B, 16,000 H100s, 3.8×10²⁵ FLOPs | 16,000 H100s, multi-month | 0.1 TFLOPS sustained = **0.0% MFU** | 445 TFLOPS = **45.0% MFU** — exactly the 45% the document assumes for H100 |
| DeepSeek-V3 | 2,788,000 H800-h | — | 327 TFLOPS = **33.1% of H100 dense** — matches §3.5's own cross-check |

**What is still true.** `compute-feasibility.md` §3.4 was **not patched**. Its table still carries the fleet-multiplied costs, and its own worked arithmetic still prints:

> - GPU-h per GPU = 5.88×10²¹ / 1.248×10¹⁴ / 3600 = **13,088 h**
> - 8 GPUs → 13,088 × 8 = 104,701 GPU-h total
> - Wall-clock = 104,701 / 8 / 24 = **68.2 days**
> - Cost = 104,701 × $2.79 = **$292,115**

**The review's independent check.** The roadmap's correction is **correct**, and so is the wall-clock figure the `review:model` lens flagged as wrong. The decisive test: `C = 5.88×10²¹ FLOPs` at 1.248×10¹⁴ FLOP/s per GPU is **13,088 GPU-hours of work** — and that figure is fleet-independent, because `f · (C / (f·r)) = C / r`. On 8 GPUs that is 13,088/8 = 1,636 h = **68.2 days**, which is what the document prints. The reviewer's claim that "the true wall-clock is 545.3 days" is obtained by dividing the *fleet-doubled* 104,701 by 8 again — it inherits the very error it set out to find. **68.2 days is right.**

**But the cost cell is wrong**, because it multiplies the fleet-doubled total by the per-GPU price: the true billed total is 13,088 GPU-h, so the cost is **$36,514, not $292,115** — inflated by exactly 8×.

**The review's own re-derivation, fleet-independent, across every row:**

| Row | §3.4 cost cell | Fleet-independent | Ratio |
|---|---:|---:|:-:|
| R1 opt | $773 | **$97** | 8× |
| R2 opt | $13,413 | **$1,677** | 8× |
| R3 opt | $292,115 | **$36,514** | 8× |
| R3 ext | $7,302,885 | **$912,861** | 8× |
| R6 | $1,887,435,000 | **$235,929,375** | 8× |

**The change this implies.** Two options, and the project should pick one explicitly:

- **Patch `compute-feasibility.md` §3.4** to the fleet-independent convention (and fix the worked arithmetic so `104,701` is not presented as a billed total), **or**
- **Keep the divergence and make it explicit in both documents** — a reader who opens `compute-feasibility.md` today finds a cost table that is 8× too high and no pointer to the correction.

The roadmap's own choice — "recorded here rather than silently patched upstream, because this document must not build on numbers it knows to be wrong" — is defensible as an interim state and indefensible as a steady state. The upstream document is the one a reader opens first.

**One thing the review adds.** The roadmap's §0.4 correction changes the *cost* column but explicitly preserves the *wall-clock* column, because the wall-clock figures it depends on (R2 = 75 h, R3 = 68 d, R3 on H100 = 19 d) are reproduced exactly by the corrected arithmetic. That is right, and it is worth stating plainly because it is the thing the `review:model` lens got wrong: **the wall-clock column survives; the cost column does not.**

#### F3 extended — two further defects in the same table, found while applying the fix (2026-10-22)

**Status: CONFIRMED and FIXED.** Applying the correction required re-deriving every cell of §3.4 from the document's own stated inputs (`6ND`, A100 dense BF16 312 TFLOPS, 40% MFU, $2.79/GPU-h, H100 989.5 TFLOPS, 45% MFU, $3.99/GPU-h). That re-derivation exposed **two further defects that F3 as originally written did not name**, both of which would have survived the cost-column patch alone:

**Defect 2 — the GPU-hour column changed meaning between rows, silently.** In the seven *optimal* rows the column held **per-GPU** hours; in the four *extended* rows it held **fleet-total** hours — 8× larger — with no label change, in adjacent rows of the same column. A reader could not tell which reading applied to a given row without re-deriving it. The fix relabels the column **"total GPU-h"** and makes it the fleet-independent quantity `C/r/3600` in every row, which is the only quantity that can be multiplied by a price.

**Defect 3 — two extended rows' wall-clocks matched no consistent reading of their own adjacent cell.** R1-ext stated **68 d** and R2-ext stated **141 d**; the true values, under either reading of the row's own GPU-hour cell, are **15 d** and **31 d**. R3-ext stated **1,488 d** against a true **1,704 d**. These were *not* one systematic factor — R1-ext and R2-ext were each wrong by a different amount, and R3-ext was wrong in the other direction. A wall-clock error in a feasibility document is the most consequential class of error there is, because the document's own conclusion is that **wall-clock and iteration count, not dollars, are the binding constraint.**

**Why F3 as originally written was too narrow.** It said the table's *cost* column was 8× high. That was true, and it was the *most visible* of the three defects — which is exactly why it was found first, and why the other two were not. **A review that stops at the first error it can explain under-explains the error it found.** The re-derivation that confirmed the cost column is the same re-derivation that exposed the other two; the difference was only that F3 stopped reading the table once the 8× pattern was confirmed.

**The corrected table, verified.** All 11 rows now satisfy, from the document's own stated inputs: `C = 6ND`; `total GPU-h = C/r/3600`; `wall-clock = total GPU-h / 8 / 24`; `cost = total GPU-h × $/GPU-h`. The check was run as a script against the patched file, parsing the table back out of the markdown and re-deriving every cell — including the rounding tolerance for day-quantised wall-clocks.

| Row | §3.4 cost cell (before) | Corrected | Ratio | Wall-clock (before → after) |
|---|---:|---:|:-:|---|
| R1 opt | $773 | **$97** | 8× | 4.3 h → 4.3 h |
| R1 ext | $64,385 | **$8,048** | 8× | 68 d → **15 d** |
| R2 opt | $13,413 | **$1,677** | 8× | 75 h → 3 d |
| R2 ext | $134,135 | **$16,767** | 8× | 141 d → **31 d** |
| R3 opt | $292,115 | **$36,514** | 8× | 68 d → 68 d |
| R3 ext | $7,302,885 | **$912,861** | 8× | 1,488 d → **1,704 d** |
| R4 opt | $1,341,346 | **$167,668** | 8× | 313 d → 313 d |
| R4 ext | $17,884,615 | **$2,235,577** | 8× | 4,085 d → **4,173 d** |
| R5 | $29,211,538 | **$3,651,442** | 8× | 6,817 d → 6,816 d |
| R6 | $1,887,435,000 | **$235,929,375** | 8× | 440,430 d → 440,430 d |

**The propagation.** The corrected figures were carried through every dependent statement in `compute-feasibility.md`: §1's verdict table, §2.1's ladder table, §3.4's worked arithmetic, §7.3's rent-vs-build framing, §8.3's "43% of the training cost" ratio, §8.4's amortisation line, §9's timeline table, §10's gate budgets, §12's three scenarios, §11.3's break-even, §14's risk table, and §15's summary. **The verdict that Scenario C is out of reach survives; its stated reason changes.** The document's "$387 billion… approximately the scale of a national-lab programme" was an artefact of the fleet error. The corrected compute is **$94.6M** and the corrected total **~$122M** — still far beyond this project, but a well-funded industrial lab's frontier run, not a national programme. That framing is retired in the patched document.

---

### F4 — The tokenizer's benefit is measured in the wrong currency for this product

**Basis: judgement, but a strong one** (it follows from the plan's own requirements, not from an external opinion). **Severity: medium.**

**What the plan says.** Stage A's exit criterion **A2** is *"Measured compression on a held-out code sample, as **chars/token**, split by language"*, with a target of ≥ 3.0 chars/token median and published reference points to beat (StarCoder2 3.238, CodeGen-mono 3.017, DeepSeek-Coder 2.836, GPT-2 2.487). A3 measures compression on the evaluation-suite repositories against the training corpus.

**The objection.** Chars/token is the right metric for a *pretraining* project, where the budget is tokens. It is the **wrong** metric for a *context-limited agent*, and this project is one. The agent's binding constraint is not how many tokens the model can be trained on — it is **how many tokens fit in one request's context window**, because that determines how much repository the agent sees per turn, how many tool results fit in context, and how often compaction fires.

**Why this changes a decision.** A tokenizer optimised for bytes-per-dollar can be *worse* for bytes-per-context-window. The two objectives are not the same, and the difference is measurable at Stage A for the cost of one tokenization pass over a sample corpus. If a 10% better bytes-per-dollar tokenizer is 5% worse at "semantic content per token on code", then the agent pays that 5% **every turn, forever**, in a resource that cannot be bought with more training compute — and the plan's own architecture proposal puts context at 32,768 trained, with Stage I (long-context) explicitly deferred.

**The change this implies.** Stage A's evaluation must carry a **second metric** alongside A2: **tokens per unit of *task-relevant content* on code**, measured on a held-out sample of the target corpus. A2's kill criterion (Stage A §3.7) then has two dials, and a tokenizer that wins A2 but loses badly on the second is a bad trade for this product specifically.

**A note on what the review is not saying.** This is not a claim that Stage A is misdirected — A2 is necessary, and the plan's kill criterion is admirably disciplined (*"a tokenizer is an efficiency optimisation, not a capability source"*). It is a claim that **chars/token alone is insufficient**, and that the insufficiency is specific to this product's shape.

---

### F5 — The licence-cleanliness requirement is absolute, and its failure has no stated contingency

**Basis: documentary.** **Severity: high.**

**What the plan says.** `llm-development-roadmap.md` §17.3 rule 6: *"The corpus must have no path to the reference product's outputs. **This is absolute** and applies to Stages D, F, G and H."* The roadmap's `U6` records that whether a licence-clean corpus of sufficient size and quality exists is **[UNKNOWN]**, resolvable only by *"Completing `licensing-and-provenance-review.md` §9's five-item gate per candidate, plus designing an attribution-discharge mechanism for The Stack v2."*

**The observation.** The strictness is correct and the review endorses it. The gap is the failure case. At 23–30 B tokens, a corpus with genuinely uniform permissive terms and no per-file attribution burden is a narrow thing to find: the permissive corpora that exist at that scale (The Stack, RefinedWeb, FineWeb, and their derivatives) carry per-file licence metadata, and the attribution-discharge mechanism `U6` names does not currently exist.

**What is missing.** There is no **contingency path** that does not violate rule 6. The plan's implicit position appears to be: if no clean corpus exists, the model workstream is blocked. If that is the position, it should be *stated*, because it is a stronger and more consequential claim than the plan currently makes in prose — and it would change the priority order (the corpus search would need to start **immediately, in parallel with Stage A**, rather than at Stage D).

**The change this implies.** State the contingency explicitly, and move the corpus search to Stage A. On the technique: the contingency must not be a licence weakening. A legitimate path that preserves rule 6 is **self-generated data** — a corpus the project generates itself from permissively-licensed source, licence-clean by construction, at the cost of diversity and of distribution-narrowing risk. The training-data plan already lists synthetic datasets (`orca-agentinstruct-1M`, `SWE-smith`, `OpenCodeReasoning`) under permissive terms, so the ingredient exists; what is missing is the *fallback plan*.

**What the review does not say.** It does not conclude that no clean corpus exists. That question is exactly `U6`, it is **[UNKNOWN]**, and the review has no evidence to close it. The finding is about the **absence of a plan for the failure case**, not about the failure.

---

### F6 — `U9` is correctly unanswerable, and the plan has the admissible substitute available and unused

**Basis: judgement.** **Severity: low-medium** (it affects the evidence base, not the plan's direction).

**What the plan says.** `llm-development-roadmap.md` §17.2 `U9`: *"Whether the reference product's system prompt collection corresponds to its actual runtime behaviour — **Not answerable by this project.** Requires provider-side disclosure. This document therefore never relies on it."*

**The review's observation.** The *first* clause is correct and the plan is right to record it. The *second* clause is true of the **model roadmap**, but the project's overall evidence base is stronger than that sentence implies, and the roadmap could draw on it.

**The distinction the plan already understands elsewhere.** The project maintains three provenance tiers (A: officially published; B: third-party capture; C: other-vendor capture) and a large body of **black-box CLI observations** — the `stream-json` protocol captures, the `claude plugin validate` reproduction, the permission-denial records, the compaction-boundary event, the hook-event table cross-derived from four independent extractions, and 42 cached documentation pages in `agent-reference-shots/docs-cache/`. Those observations are **admissible**: they are direct observation of a published product's published interface, with no reverse engineering.

**The consequence.** Where the roadmap needs to know *"what does a production harness actually do at this point"* — what a tool-call result looks like on the wire, what a permission denial contains, how a compaction boundary is signalled, what a settings file actually resolves to — the admissible evidence is the **black-box capture and the cached official documentation**, not the prompt collection. The plan's `U9` and rule 2 (*"Never cite a prompt collection as behavioural proof"*) are both correct and already imply the right move; the review's contribution is to note that the roadmap does not appear to *use* the admissible substitute where it could.

**The change this implies.** Wherever the roadmap reasons about "what a production coding agent does", it should cite the project's own captured observations and cached docs (`agent-reference-shots/`, `PROTOCOL-NOTES.md`, `claude-code-evidence.md`) rather than a general belief about agent behaviour. This is a strengthening, not a correction.

---

### F7 — The evaluation gates use the public benchmarks in a way the licensing review forbids

**Basis: documentary.** **Severity: medium.** **This is the finding the review considers most likely to be independently useful after F1 and F3.**

**What the plan says.** `compute-feasibility.md` §10 Gate 1 requires *"HumanEval pass@1 on the 30M model goes from ~0% to above the 30M model's random-ish baseline"*. Gate 2 requires *"at matched size, our R1 must beat SmolLM2-360M or an equivalently-sized public model on **HumanEval/MBPP**"*.

**What contradicts it.** `licensing-and-provenance-review.md` §9's corpus register marks MBPP and HumanEval as *"Small; decontamination is easy; **use as a held-out set only**"* — a CANDIDATE, not a training or gate corpus. The same document's §14 risk #3 warns that *"public benchmarks are contaminated and small models overfit them fast"* and recommends building *"a held-out human-written benchmark early."*

**The conflict.** The gates use the public benchmarks as the **live go/no-go signal** at exactly the model scale (30 M, 360 M) where overfitting them is fastest and where a go/no-go decision made on a 150-task public set is least reliable. The plan's own documents say both "use these only as held-out" and "use these as the gate".

**What the evaluation plan already does right.** `benchmark-and-evaluation-plan.md` is *excellent* on this axis and the review wants that on the record: §4.6 gives contamination controls "in order of strength" with **age cutoff** first and an honest limit (*"a capable model may still reconstruct the upstream issue from the repository and the defect, because the defect **is** the fingerprint"*); §5.3 specifies a **six-rule leakage-prevention protocol** with a runner process that alone can read test fixtures, per-access logging, and a rationale rule that rejects any change motivated by a test task; §5.3 rule 6 requires **hash-based disjointness** between suite assets and training examples; §5.4 requires a **reserve corpus**; and §4.6 provides a **negative control** of known-suspect tasks.

**The change this implies.** Move the *decision* off HumanEval/MBPP and onto the project's own held-out suite (`benchmark-and-evaluation-plan.md`'s TEST-B partition with its L-task/L-repo controls), keeping HumanEval/MBPP as **secondary** evidence and a sanity check. The plan's own `§14 risk #3` already calls for a project-built held-out set; the gates simply have not been switched over to it.

---

## 4. The plan's strongest features, stated as findings

A review that only lists problems misrepresents the document. These are the features that made the rest of the review possible, and each one is a *finding* in the sense that a future editor could lose it.

| # | Feature | Where | Why it is load-bearing |
| :- | :- | :- | :- |
| S1 | **The claim-tagging discipline.** Every number carries `[KNOWN FACT]` / `[ESTIMATE]` / `[SPECULATIVE TARGET]` / `[OBSERVED]` / `[INFERRED]` / `[UNKNOWN]`, and the roadmap's §17.1 publishes the *counts* of each. | `llm-development-roadmap.md` §17 | It made F1 and F2 findable at all. |
| S2 | **The lever attribution table**, with the prediction of *which* lever wins and *when*. | §2.1 | It makes "most early capability comes from (d)/(e)/(f)" a falsifiable claim rather than a slogan. |
| S3 | **The unknown ledger with resolution criteria.** 15 unknowns, each with the specific measurement that would settle it. | §17.2 | `U6` and `U9` are what made F5 and F6 possible. |
| S4 | **The gate structure.** `compute-feasibility.md` §10 has Gates 0–5, each with a stated question, stated evidence, an explicit **"STOP if"** condition and a budget-at-risk figure — plus five **global stop rules** with numeric triggers (50% of budget without a passed gate; two consecutive failures with the same cause; MFU below 25% for two runs; dataloader stall above 15%; eval variance exceeding the effect size being measured). | §10 | The review's first draft asserted the gates "cannot fail". They can, and the floor this review searched for and did not find exists: **Gate 5** stops the model investment if *"our model loses to a rented frontier model on every dimension."* |
| S5 | **The arithmetic reproduces in the architecture proposal.** The review independently re-derived the parameter count, FLOPs, GPU-hours, wall clock, dollar figure, KV-cache size and activation memory and found **no error**. | `model-architecture-proposal.md` §4.2, §4.6, §6 | It is the one check that could have destroyed the proposal and did not. F1 is about a *different* document's table. |
| S6 | **The explicit refusal to claim performance**, with the reason. | `model-architecture-proposal.md` §1.3 | It makes the "no benchmark figure found" line an honest disclosure rather than an omission. |
| S7 | **The "own model" test is four-part and falsifiable**, and `AMB-221` refuses the comfortable fiction that a model swap is free. | `agent-and-model-boundary.md` | It is the strongest single idea in the plan. |
| S8 | **The evaluation plan's contamination and leakage machinery** — seven controls ordered by strength, a six-rule leakage protocol, hash-based disjointness, a reserve corpus, and a negative control. | `benchmark-and-evaluation-plan.md` §4.6, §5.3–§5.4 | It is what made F7 a *switch* rather than a *build*. |

---

## 5. The review's own errors, and the findings it refuted

**This section exists because the review's first draft was wrong on two points, and three of the workflow's own lens findings were wrong on three more, and a review that hid that would be worth less than one that shows it.** All five errors were found by checking rather than by reasoning.

### 5.1 Refuted finding A — "the Stage E scaling gate cannot fail, because it has no threshold"

**The claim was:** the roadmap's Stage E gate ("scaling only when measurements justify it") has no numeric trigger, so it cannot constrain; and there is no floor below which the project should stop.

**Why it was wrong.** `compute-feasibility.md` §10 has **Gates 0 through 5**, each with a question, evidence requirement, an explicit **"STOP if"** condition, and a budget-at-risk figure. The roadmap's Stage E §7.1 does not merely gesture at this — it **quotes Gate 2 verbatim** as the gate that must precede Stage E:

> *"at matched size, our R1 must beat SmolLM2-360M or an equivalently-sized public model on HumanEval/MBPP. **If our own model cannot beat the public one at equal scale, the data is not better than what is already public, and every larger rung inherits that defect.**"*

And the **floor** the review said was missing **exists**: Gate 5's STOP condition is *"our model loses to a rented frontier model on every dimension. **In that case the correct engineering decision is to rent and spend the remaining budget on the harness.**"*

**What the review got wrong about its own reasoning.** It searched the *roadmap* for a gate and, not finding one in the place it expected, concluded none existed — without checking the document the roadmap explicitly points to. The five global stop rules (50% budget, 25% MFU, 15% stall, variance-vs-effect-size) are numeric triggers the review did not find because it looked in the wrong file.

**The correction.** The claim is withdrawn. The gates are real, they are numeric where they need to be, and the floor exists.

### 5.2 Refuted finding B — "the evaluation set is not held out by construction"

**The claim was:** the plan's contamination control protects against the *reference's* outputs but says nothing about the corpus leaking into the eval set; no mechanical held-out construction exists.

**Why it was wrong.** `benchmark-and-evaluation-plan.md` §5.3 specifies a **six-rule leakage-prevention protocol**, of which rule 6 is:

> *"The training-data filter covers the whole suite. … **hash every suite asset, hash every training example, and assert disjointness**."*

and the plan requires *"a leakage audit runs before every release"* reporting *"training-data disjointness (target: exact)"*. §5.3 also defines **two hold-out levels** — **L-task** (a task instance is not in the tuning set) and **L-repo** (*"The strongest and most important control. Split by repository, not by task"*) — plus a **reserve corpus** for second-generation evaluation (§5.4).

**The correction.** The claim is withdrawn. The mechanical, audited, loader-level construction the review asked for **is present and is stronger than what the review proposed**.

### 5.3 Three evidence-lens findings refuted against the cached reference

The `review:evidence` lens reported that the project's claims of *"245 keys across 18 sections"* and *"twelve security-sensitive keys"* were wrong. **Both were checked directly against `agent-reference-shots/docs-cache/settings-reference.md` and `settings.md`, and both are right:**

| Claim | Lens said | Ground truth | Verdict |
| :- | :- | :- | :- |
| Number of settings keys | 245 (not 18-section wording) | The "Settings index" table in the cached `settings-reference.md` has **exactly 245 rows, 245 distinct keys** | **Project is right** |
| Topical sections | 18 | The page has **19 `##` headings**, of which two — *"Settings index"* and *"See also"* — are not topical sections → **17 topical sections** | **Project is right** |
| Monotonic restriction keys | 12 | The *"Exceptions to managed settings precedence"* table in the cached `settings.md` lists **exactly 11 keys**: `disableClaudeAiConnectors`, `enableArtifact`, `isolatePeerMachines`, `permissions.blockReadsOutsideWorkingDirectories`, `autoMode.classifyAllShell`, `remoteControlAtStartup`, `crossSessionInbound`, `useAutoModeDuringPlan`, `syncClaudeAiSkills`, `syncClaudeAiPlugins`, `maxEffortLevel` | **Project is right (11)** |

**A fourth lens finding, on the hook-event count, was also checked:** the claim *"the hooks page states 29 hook events"* is already corrected in `claude-code-evidence.md` §R5, which records that the page contains **no** such sentence (grep for `supports 29 hook events` returns 0 hits in both cached copies) and that the true count is **33** events / 33 `###` sections. The lens was reviewing a pre-correction state.

**The lesson, stated because it is the point of the whole exercise:** **four of the lens's findings were false, and every one of them was caught by going to the cached source rather than reasoning from the text.** A reviewer that reports "the document says 18 sections" without counting the headings is doing the same thing this project is built to avoid.

---

## 6. Verification performed by this review

### 6.1 Independent re-derivations

| Quantity | Plan's value | Review's re-derivation | Agrees? |
| :- | :- | :- | :- |
| Parameter count (architecture proposal) | 1,149,343,744 | recomputed from L=24, d=2,048, ffn=5,632, GQA 4:1, head_dim=128, vocab=32,768, tied | **Yes** |
| Training tokens @ 20 tok/param | 22.99 B | 1,149,343,744 × 20 | **Yes** |
| Training FLOPs | 1.585 × 10²⁰ | 6ND | **Yes** |
| A100-hours | 353 | 1.585e20 / (312e12 × 0.40) | **Yes** |
| Wall clock on 8×A100 | 1.84 d | 353 / 8 | **Yes** |
| KV cache @ 32,768 | 1.611 GB | 2 × L × ctx × kv_dim × 2 B | **Yes** |
| **Roadmap Stage E R2 `6ND`** | **2.70 × 10²⁰** | **2.069 × 10²⁰ at the row's own N** | **No — F1** |
| **Roadmap Stage E R2 wall** | **3.1 d** | **2.40 d** | **No — F1** |
| **R3-opt wall-clock (`compute-feasibility`)** | **68.2 d** | **68.2 d** | **Yes — MOD-01 refuted** |
| **`compute-feasibility` §3.4 costs** | **as printed** | **8× too high (fleet-multiplied)** | **No — F3** |

### 6.2 Cross-document consistency checks

| Check | Result |
| :- | :- |
| Vocabulary size across documents | 32,000 in `training-data-plan.md` §7.1 vs 32,768 elsewhere — **already recorded by the project as `OPEN-A1`**. Not a new finding. |
| Cost convention across documents | **Divergent by 8× — F3, not previously recorded.** |
| Stage E table vs its own parameter count | **Inconsistent — F1, not previously recorded.** |
| `AMB-` rule references resolve to existing rules | Consistent in the places checked. |
| Stage names consistent across roadmap / architecture / compute | Consistent. |

### 6.3 Gate-hunting (corrected after §5.1)

| Gate | Has a numeric or explicit trigger? |
| :- | :- |
| `compute-feasibility.md` Gate 0 (before any spend) | **Yes** — spend authorization. |
| Gate 1 (R0 proof-of-learning) | **Yes** — "loss does not decrease within 200 steps", or the eval harness is non-deterministic on the same checkpoint. |
| Gate 2 (R1 vs a public model at matched size) | **Yes** — "our R1 loses to the public baseline on code benchmarks after a full token budget." |
| Gate 3 (R2 decision point) | **Yes** — "the agent harness on R1/R2 does not complete end-to-end tasks." |
| Gate 4 (R3 commitment) | **Yes** — "the answer is 'it would be nicer' or 'we might want it later.'" |
| Gate 5 (post-training / evaluation) | **Yes** — "our model loses to a rented frontier model on every dimension." **This is the floor.** |
| Global stop rules ×5 | **All numeric.** |
| Roadmap Stage E (scaling) | **Yes** — it *is* Gate 2, quoted verbatim. |
| Stage H (RL only where justified) | **Yes** — the verifier is the trigger. |
| Quantisation gate (Stage J) | **Yes** — a measured quality-loss bound. |

---

## 7. The limits of this review

Stated plainly, because a review that hides its own weaknesses is worth less than one that names them.

1. **It is not an independent model.** It is the same model family reviewing its own work, in the same session, with the same priors. Every **confirmation** in this document carries no evidentiary weight. Every **criticism** carries whatever weight its argument earns on its own, and each one is checkable against a cited document.
2. **It reviewed documents, not a model.** No finding here is evidence about how the model will perform.
3. **It did not re-verify the reference product by observation.** Where a finding was about the reference, it was checked against the *cached documentation* in `agent-reference-shots/` — which is a documentary check, not a behavioural one, and inherits that source's own provenance tier.
4. **It did not re-derive the licence reasoning.** F5 restates the plan's own `U6` and adds a contingency; it makes no legal claim, and this project makes no legal conclusions from repository metadata alone.
5. **Its own first draft was wrong twice** (§5.1, §5.2). Both errors were of the same kind: *asserting the absence of something without going to the source that would contain it.* The corrections are recorded rather than quietly applied, because the errors are more useful to a future reader than the corrections would have been.
6. **The other review lenses are not covered here.** The security lens was reconciled in `security-plan.md` §1.6; the evaluation lens's own findings — statistical power, gate calibration, contamination ordering, and the missing model-level adversarial evaluation family (EVAL-11) — belong in the evaluation plan itself and are **not** restated here. The evidence lens's findings are partly refuted in §5.3.
7. **Fable 5.1 remains UNAVAILABLE.** If the user later approves a billable Fable 5.1 invocation, its review should be run **against this document** as the baseline it must improve on, and this document should be marked as superseded rather than quietly merged.

---

## 8. Recommended actions, in order

| # | Action | Document | Cost | Blocks what |
| :- | :- | :- | :- | :- |
| 1 | **Recompute the Stage E R2 and R3 rows at their own stated parameters** and show the arithmetic beside the table. | `llm-development-roadmap.md` §7.3 | An hour | The plan's headline schedule and cost |
| 2 | **Decide the cost-convention question explicitly** — patch `compute-feasibility.md` §3.4 to the fleet-independent convention, or make the 8× divergence explicit and cross-referenced in both documents. | `compute-feasibility.md` §3.4; `llm-development-roadmap.md` §0.4 | An hour | Every dollar figure in the plan |
| 3 | **State which token-budget arm the plan is currently betting on**, and give that arm's wall-clock and cost. | `llm-development-roadmap.md` §7.3 | Minutes | The Stage E decision |
| 4 | **Move the go/no-go gates off HumanEval/MBPP** onto the project's own held-out suite; keep the public sets as secondary evidence. | `compute-feasibility.md` §10 Gates 1–2 | An hour | Gate validity at the 30 M–360 M scale |
| 5 | **Add the second tokenizer metric** (tokens per *task-relevant content* on code) and a second dial on Stage A's kill criterion. | `llm-development-roadmap.md` Stage A §3.5, §3.7 | Hours | Stage A's exit criterion |
| 6 | **State the corpus contingency** and move the corpus search to Stage A. | `training-data-plan.md`; roadmap Stage D | A day | Stage D's start date |
| 7 | **Cite the project's own black-box captures and cached docs** wherever the roadmap reasons about production-agent behaviour. | roadmap, throughout | Hours | Evidence hygiene |
| 8 | Mark `llm-research-review.md` as the **baseline** for any future Fable 5.1 review, and as superseded when one runs. | this file | Minutes | — |

**Actions 1 and 2 are the ones the review would insist on.** Both are arithmetic, both are checkable in minutes, and both sit directly upstream of the plan's largest irreversible commitment.

---

## 8a. Fixes applied (2026-10-22)

**A fix is only a fix if it is verified against the source, and only trustworthy if the change is recorded.** The table below states what was changed, how it was checked, and what remains open. Every arithmetic change was verified by a script that re-derives the number from the document's own stated inputs and compares it to the value now printed in the file — not by re-reading the edited text and agreeing with it.

| # | Action | Status | How it was verified |
| :- | :- | :- | :- |
| **2** | **Cost convention decided: `compute-feasibility.md` §3.4 patched to the fleet-independent convention.** The cost column was 8× high in *every* row. | **DONE (2026-10-22)** | A parser reads the patched table back out of the markdown and re-derives all 11 rows × 7 cells from `6ND`, 312 TFLOPS @ 40% MFU, 989.5 TFLOPS @ 45% MFU, $2.79 and $3.99. All cells pass, with a rounding tolerance only for day-quantised wall-clocks. |
| **2a** | **The two further §3.4 defects the fix exposed.** The GPU-hour column changed meaning between optimal and extended rows; R1-ext, R2-ext and R3-ext wall-clocks matched no consistent reading of their own adjacent cell. | **DONE (2026-10-22)** | Same script, plus an explicit column-meaning test on the pre-patch table. The R1-ext/R2-ext wall-clocks moved 68 d → **15 d** and 141 d → **31 d**. |
| **2b** | **Propagation of the corrected figures through every dependent statement.** §1 verdicts, §2.1 ladder, §3.4 worked arithmetic, §7.3 rent-vs-build, §8.3 ratio, §8.4 amortisation, §9 timeline, §10 gate budgets, §11.3 break-even, §12 scenarios A/B/C, §14 risks, §15 summary. | **DONE (2026-10-22)** | A project-wide grep for all 14 defective figures returns zero hits outside this review's own text and the two in-flight workflow agents. |
| **2c** | **Scenario C's headline verdict restated.** "$387 billion… approximately the scale of a national-lab programme" was an artefact of the fleet error; the corrected compute is $94.6M and the corrected total ~$122M. | **DONE (2026-10-22)** | Re-derived from the same inputs. The *"national-lab programme"* framing is retired **in the document**, with the correction note explaining why, rather than quietly deleted. |
| **4** | **Gates 1–2 moved off HumanEval/MBPP.** They now run on the project's own DEV partition, with the public suites demoted to "external reference point, never a release gate" — matching `licensing-and-provenance-review.md` §9 and `benchmark-and-evaluation-plan.md` §5.3. | **DONE (2026-10-22)** | The two source constraints were re-read verbatim before the edit. The honest consequence (a smaller, noisier decision instrument) is stated in the document rather than glossed. |
| **6** | **Corpus contingency stated; corpus search moved to Stage A.** `training-data-plan.md` §2.2a now gives four ordered branches, and states the licence-cleanliness requirement is absolute in every branch. | **DONE (2026-10-22)** | Written against `training-data-plan.md`'s own two-licence-column register and the roadmap's `U6`. |
| **1** | **Recompute the Stage E R2 and R3 rows at their own stated parameters.** | **DONE (2026-10-22)** | The roadmap's §7.3 table now carries each row's own parameter count (Config B = 1,149,343,744; Config C = 7,248,019,456) with the derivation shown; §1.2's ladder carries a **warning** that its 1.5 B / 7 B rungs are *planning* anchors and not the trained sizes. Every cell was re-derived by script from `6ND`, 312 TFLOPS @ 40% MFU and $2.79, under the fleet-independent convention. |
| **3** | **State which token-budget arm the plan is betting on.** | **DONE (2026-10-22)** | §7.6 now carries a six-row token-arm table (20 / 26.1 / 50 / 100 / 200 tok-per-param, plus a 300 B-token row) and states explicitly that the budget in §7.3 is **the 26.1 tok/param (30 B-token) arm**, that the 200-tok/param arm is a **7.7× cost and latency multiplier** away, and that the arm choice is a **Stage E decision settled by E3's measurement**, not a default. |
| **5** | **Second tokenizer metric + second dial on Stage A's kill criterion.** | **DONE (2026-10-22)** | Stage A §3.5 now carries **A2b** — tokens per unit of *task-relevant content* on code — with the content-unit extractor named as the tooling that must be written, and an explicit `[UNKNOWN]` that no published tokenizer has a figure for it, which is why it is a *selection* criterion among our own candidates rather than a comparison against a published baseline. §3.7 now carries a **second, independent dial**: kill the custom track if the best-by-chars/token candidate is **>5% worse** than the pre-trained tokenizer on A2b, with the resolution rule (the pre-trained tokenizer wins on a disagreement) stated. |
| **7** | **Cite the project's own black-box captures where the roadmap reasons about production-agent behaviour.** | **DONE (2026-10-22)** | §2.2's harness-dominates claim and Stage G §9.4's trajectory-recorder item now cite the project's own captures by file and line (`agent-reference-shots/PROTOCOL-NOTES.md`, `interface-spec.md` §14.7, `agent-reference-shots/tool-error-contract.json`, `agent-evidence.md`) instead of asserting a general belief. Both passages carry the boundary that these are observations of a **published interface**, not evidence about weights or training methods. |

**What the four late fixes changed that the review did not predict.** Two defects surfaced while applying them, neither flagged by this review. First, §11.2's attention-overhead table was **100× too large** (the `d` factor applied twice), which made its "attention dominates everywhere" conclusion wrong as well: attention is **0.70×** the dense term at Config B's 8,192-token working context, and Config C's overhead is *lower* than Config B's at fixed context. Second, §1.2's R6 row mixed accelerators — a 4,096-H100 wall-clock in an 8-GPU column and an H100 bill in an A100 cost column — so the row could not be quoted at all. Both are recorded in the roadmap's own correction notes rather than silently replaced.

**An upstream inconsistency this review did not catch.** `compute-feasibility.md` §9 states that R2 buys "**~60 experiments/year**" while its own wall-clock (3 d/run) gives **365/3.13 ≈ 117**. The gap is a utilisation assumption — a shared allocation at ~50% versus a dedicated one at 100% — and it is stated in the roadmap (§15.1) rather than averaged away. The conclusion is unchanged on either reading; only the factor of two moved.

**What this log is for.** A review that reports only its findings reads as though the findings are the end of the work. They are not: the findings are the reason the documents changed, and the change is the deliverable. **The row that matters most in this table is not any single "DONE" — it is the fact that the arithmetic in §3.4 is now checkable by anyone who opens the file and runs one derivation, rather than only by the people who wrote it.**

---

## 9. The synthesis in one paragraph

The model-development plan is **honest about what it does not know** and **rigorous about what it claims to compute**, and this review found no fabricated benchmark, no over-claim, and no place where the plan treats the reference product's internals as known. Its weaknesses are not in its design; they are in **two tables whose numbers no longer agree with their own inputs** — a Stage E row that pairs one parameter count with another row's arithmetic, and a cost column computed under a convention the same project has already shown to be wrong. Both are mechanical to fix, and both are exactly the class of defect a project that re-derives rather than asserts should catch before the money moves. The review's overall judgement is that the plan should proceed — with those two corrections made first, the gates switched onto the project's own held-out suite, and the honest expectation, which the plan itself already states and which this review endorses, that **most of the capability arrives from the harness and the measurement apparatus long before it arrives from the weights.** The plan's own evaluation says the same thing: if the model loses to a rented frontier model on every dimension, the correct decision is to rent and spend the budget on the harness.

---

*Prepared 2026-10-21. This is a **local adversarial review**. Claude Fable 5.1 was **not** invoked — it is billable, no approval was given, and it is **not claimed**. No model was trained, no benchmark was run, no billable call was made, and no infrastructure was provisioned.*

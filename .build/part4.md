
## 9. Reference-model comparison protocol

### 9.1 Purpose and scope

The purpose of a reference-model comparison is to establish **where the team's model or agent sits relative to a known-good reference on tasks we control**. It is *not* to prove superiority, and it is *not* to produce a number that can be quoted without its harness.

**Reference model:** Claude Opus 5.5, as named in the investigation's evidence base (`agent-evidence.md` header: "Reference implementation model: Claude Opus 5.5"). Additional reference models may be included per §9.7.

**PLANNING CONSTRAINT — no billable calls in the planning phase.** Every procedure in this section is a *future* activity. During plan authoring, no reference-model run is executed, no result is produced, and no cost is incurred. The reference-model run is a milestone-gated activity (M5 entry criteria, §11.5), and until it is run, this document contains **no reference-model score and no claim about one**.

### 9.2 The controlled comparison

**PLAN — the comparison is valid only if all of the following hold. Each is checked mechanically, and the report refuses to publish if any fails.**

| # | Control | Requirement | Enforcement |
| :- | :- | :- | :- |
| **C1** | Same task set | Byte-identical task manifests, same partition, same task-set version | Hash comparison of the manifest set |
| **C2** | Same acceptance criteria | Identical oracles, identical verifier version, identical pass/fail definition, identical post-conditions | Verifier version hash; oracle files hash-checked per task |
| **C3** | Same tool schemas | Identical JSON Schema for every tool, byte for byte | `tool_fingerprint.tools[].schema_sha256` equality |
| **C4** | Same tool descriptions | Identical description text, byte for byte | `tool_fingerprint.tools[].description_sha256` equality |
| **C5** | Same system prompt | Identical system prompt, byte for byte | `system_prompt_sha256` equality |
| **C6** | Same permission mode and rules | Identical mode and identical effective rule set | `permission_mode` + `permission_rules_sha256` equality |
| **C7** | Same environment | Identical image digest and lockfile | Digest equality |
| **C8** | Same budget | Identical tool-call budget, turn budget, wall-clock cap, cost cap | Fingerprint equality on budget fields |
| **C9** | Same harness | The *same harness build* drives both arms | `harness_commit` equality. **This is the hard one**, and §9.4 explains why it is sometimes impossible. |
| **C10** | Same seeds and interleaving | Identical seed set; arms interleaved per task | Seed-set equality; schedule log |
| **C11** | Same verifier | Identical verifier implementation and version | `verifier_version` |

**PLAN:** C3, C4, and C5 are the controls most often abandoned, and they are the ones that matter most. A different tool description is a different prompt. The reference evidence makes the stakes concrete: the reference harness's tool `description` field is documented as **model-authored** and sitting directly on the trust path (**OBSERVED-CLI**, L12) — the descriptions are prompt, and prompt is the experimental variable.

### 9.3 Where the models must differ, and why that is stated explicitly

**PLAN:** some differences are unavoidable and each must be *declared* in the comparison record, with a reason. The permitted categories of difference are:

| Permitted difference | What it is | Why it is permitted | What must be reported |
| :- | :- | :- | :- |
| **Model id and weights** | The thing under test | — | id, snapshot, provider, endpoint, context window, max output tokens, **cost basis** |
| **Decoding parameters, where the model does not support the same knobs** | e.g. a model with no `effort` axis | The knob does not exist on the model | The knob's absence is stated; the comparison is labelled "decoding settings not equivalent"; the analysis treats it as a controlled but imperfect comparison |
| **Native tool-call format** | How the model emits a tool call (e.g. a native function-calling channel vs. text-embedded calls) | A transport difference, not a prompt difference | The format is documented; the *schema the model sees* is still identical (C3), which is what matters |
| **Context window** | If models differ, the *usable* context differs | A real property of the model | The window is reported; tasks exceeding the smaller window are reported separately rather than scored as failures |

**PLAN — prohibited differences (the comparison is void if any appears):** different system prompts; different tool descriptions; different permission rules; different budgets; different task sets; different verifiers; different harnesses (without §9.4's explicit, labelled exception); different environment images.

### 9.4 The harness-variant problem — the honest position

**PLAN:** C9 ("same harness") is sometimes impossible, and the plan requires the impossibility to be stated rather than papered over.

The reason is structural. A reference model is a *provider's* model, reachable through a *provider's* API. An independent harness must speak that API. Two situations force a harness difference:

1. **Provider-specific API surface.** A provider's tool-calling format, streaming semantics, error taxonomy, or tokenisation may not be expressible in the independent harness's internal representation.
2. **Reference product as the harness.** A comparison against a *commercial agent product* (rather than a bare model) necessarily uses that product's harness — its tools, its prompt, its permissions, its context management. In that case the comparison is **product-vs-product**, not model-vs-model, and it is only valid as a product comparison.

**PLAN — the reporting requirement that follows.** Every reference-model score is reported with the harness variant attached, in the form:

```
score: <value>  |  model: <id+snapshot>  |  harness: <name>@<version>  |  variant: <A|B|C>  |  tasks: <set+version>
```

with the harness variants enumerated as:

- **Variant A — common harness.** Both models driven by the *same* independent harness, the same tools, the same prompt. This is the **preferred** variant and the only one that isolates the model. It is used whenever the reference model can be driven by the independent harness.
- **Variant B — reference-product harness.** The reference model is driven by the reference product's own harness (its tools, its prompt, its permissions). The team's model is then run through an *emulation* of that harness — the same tool set, the same descriptions, the same system prompt, the same permission semantics. This is a **harness-matched** comparison and is the strongest form available when the independent harness cannot host the reference model natively.
- **Variant C — different harness, uncontrolled.** Used only when neither A nor B is possible. **The score is reported as not comparable to any other score in the report**, and it may not be used to make a claim about the model.

**PLAN:** the harness variant is a mandatory field of every score, and a report that mixes variants without labelling them is invalid. This is the concrete form of §1.1's principle: the harness is one of the four things that determine the score, so the harness variant travels with the score, always.

### 9.5 The two directions of misattribution — stated as a rule

This is the section the whole protocol exists to serve.

**Direction 1 — a stronger model scores higher on *the harness*, not intrinsically.**

A model that is better at a *harness* is better at that harness. If the reference model was optimised (or merely shaped) to work well with a particular tool set, prompt style, and error-message format, it will score higher through that harness than it would through a different one, and the difference is not a property of the model. Concretely, the reference product's own error messages are, in the reference's own framing, **designed to be recoverable from**: the uniqueness error is described as "load-bearing in the agent loop — the model recovers by adding context" (**OBSERVED-CLI**, F4.3, confirmed #86), and the whole error path is described as "a diagnosis, not a category" (**OBSERVED-CLI**, F6.2). A model that has been shaped to read that particular style will recover from it more often. This is a real advantage of the reference *system*, correctly attributable to the reference system, and misattributable to the model.

**Direction 2 — a stronger model scores lower because the *harness* suits it less.**

The mirror case is at least as common and is much less discussed. A model with a different tool-call idiom, a different tolerance for terse tool descriptions, or a different planning style may score lower against the same harness without being worse at the task. This is why Variant B exists: it is the mechanism for separating "the model is better" from "the model fits this harness".

**PLAN — the reporting rule.** Every reference-model comparison report contains an explicit statement, in the results section, of the form:

> The observed difference is a difference between **(model, harness)** pairs, measured on **task set T**. It does not by itself establish that the models differ in capability. To distinguish the model from the harness, the comparison must be repeated under a second harness variant (A/B/C above) with the direction of the difference tested for consistency.

And a report that ran only one variant **must** say so in the caveats, and its claim strength is capped at `inconclusive` if the difference is small enough to be explicable by harness fit.

### 9.6 Cost accounting in a reference-model comparison

**PLAN:** the cost comparison is a *required output*, not an appendix.

**Cost is a first-class benchmark dimension for an agent.** The reason is arithmetic, not ideology: a configuration that is 2% better on pass rate but 10x more expensive per task is *worse* overall for anyone running it at volume. Any comparison that reports accuracy without cost enables exactly the wrong conclusion, and a team that only measures accuracy will optimise accuracy — because that is what is measured.

**PLAN — the cost accounting rules:**

1. **Cost per task, cost per successful task, and total cost** are all reported. Cost per successful task is the decision-relevant number: it is what a user actually pays per solved problem.
2. **The cost basis must be known.** If the provider does not publish a price for the model in use, the report says `cost_basis: unknown` and the cost comparison is **not made** — the numbers are still reported as token counts, and a token-normalised comparison is offered instead. This is not hypothetical: the reference evidence observed `costBasis: "unknown"` with `costUSD: 0.0` for an unpriced gateway model (**OBSERVED-CLI**, `print-mode-json-result.json`), and reporting `$0.00` from that would be a false number.
3. **Whole-tree accounting.** Cost must include subagent spend, summarisation calls, and any auxiliary model calls. The reference distinguishes main-loop `usage` from whole-tree `modelUsage` (**OBSERVED-DOC**, F139, C24) and a harness that reports only the former will under-report by a large factor.
4. **Cache effects are reported separately.** `cache_read_input_tokens` is a real discount and hiding it in an aggregate is how teams accidentally compare a cached configuration against an uncached one. The reference separates `cache_creation_input_tokens` and `cache_read_input_tokens` in the usage block (**OBSERVED-CLI**).
5. **Cost is paired with quality, per task.** A per-task scatter of cost against outcome identifies the configurations that are expensive *and* wrong — the ones to fix first, and the ones an aggregate hides.
6. **The reference model's cost is stated at the price the team would actually pay**, with the price and its date in the report, since prices change.

**PLAN:** the reference-model comparison concludes with an explicit **cost-efficiency statement**, in this form:

> At the measured prices, model M costs $X per successful task on task set T versus $Y for the reference model (cost basis: known/unknown, priced as of <date>). The quality difference is Z points [95% CI …]. **If the comparison were run at N times the volume, the total cost difference would be …** *(only stated when N is a real deployment forecast, not a hypothetical.)*

### 9.7 Reference models and their configuration

**PLAN:** the reference set is chosen for *role* coverage, and each entry is a separately-pinned configuration.

| Reference | Role in the comparison | Notes |
| :- | :- | :- |
| **Claude Opus 5.5** | Primary reference — the strongest configuration the team can compare against | The model named in the investigation's evidence base |
| A mid-tier frontier model | Secondary — tests whether gains are confined to the top of the capability range | Chosen for cost as well as capability: the reference pricing capture in the evidence tree lists tiered per-token prices for several model families (`agent-reference-shots/model-access-pricing.json`), so a cost-tier comparison is possible where the price basis is known |
| A small / fast model | Tertiary — the "is this worth it" boundary, and a sanity check that the benchmark discriminates | Also the practical target for many agent uses |
| The reference *product* (Claude Code) driven by a chosen model | Optional product-level comparison | Only in Variant B, and labelled as a product comparison |

**PLAN:** each reference model's configuration is pinned to the same standard as any other arm (§6.1), including the effort level. Where the reference model supports the reference harness's five effort levels (`low, medium, high, xhigh, max`, **OBSERVED-DOC**, F7.2), the effort level is matched to the team's model's effort level and the mapping is documented — because a comparison at `max` effort against `low` is not a comparison.

### 9.8 The reference-comparison report

**PLAN:** the reference comparison uses the §8.7 template, with the following additions:

1. **Harness variant** for every score.
2. **A `cost_basis` field per arm.**
3. **A statement of the direction-of-misattribution test** (§9.5), including whether a second variant was run.
4. **A list of tasks where the reference model failed**, always reported. A comparison that reports only the reference's successes on the tasks the team also passed is a biased report, and the reference's failures are frequently the most informative rows in the table — they are the tasks the team might solve, and they are the tasks where the harness's difficulty can be seen.
5. **An explicit statement of what the comparison does not show** — including, at minimum: that it does not establish superiority, that it does not generalise beyond the task set, that it does not control for differences in provider-side training data, and that it does not establish a ranking.

### 9.9 Prohibited uses

**PLAN:** the following are explicitly forbidden, and the plan's review checklist (§15.7) checks for them:

- Quoting a reference-model score **without** its harness variant.
- Quoting a reference-model score **without** the task set and its version.
- Presenting a Variant C score as a model comparison.
- Combining scores from different harness variants into an aggregate.
- Presenting a comparison run under a non-default or unusually generous budget as if it were the default.
- Describing the outcome as "our model beats Claude" or any equivalent. The permitted claim shapes are enumerated in §11.5.
- Using a reference-model run's prompts, transcripts, or error messages as training data for the team's model without a fresh held-out set, and without a written statement of the contamination consequence.

---

## 10. Statistical rigour

### 10.1 Sample size for a 5-point difference

**PLAN:** the target is to detect a **5-percentage-point** difference in per-task pass rate, on a paired design, at 80% power and alpha = 0.05 (two-sided, unadjusted — the adjustment is applied afterwards, §10.2).

For a paired binary design, the required sample size is driven by the **discordance rate** — the proportion of tasks where the two arms differ — not by the pass rate alone. The McNemar test's power depends on the number of discordant pairs.

Working this through with the standard McNemar (normal approximation) power expression, and using an illustrative configuration for a paired design where the discordant split is unbalanced (the usual case: improvements outnumber regressions, or vice versa):

| Discordance rate (b+c)/n | Discordant pairs at n=200 | Approximate detectable difference (80% power, α=0.05) |
| :- | :- | :- |
| 10% | 20 | ~15–20 pp |
| 20% | 40 | ~9–12 pp |
| 30% | 60 | ~7–8 pp |
| 40% | 80 | ~5–6 pp |
| 50% | 100 | ~4–5 pp |

**PLAN — the practical conclusion, stated as a design requirement:**

> To reliably detect a 5-point difference with a paired binary metric, the suite needs **roughly 300–400 paired tasks** at a realistic 30–40% discordance rate, or **about 150–200 paired tasks** if the discordance rate is high (near 50%).

This is why the task-suite size target (§4.8) is staged: S2 (540 tasks) and S3 (920) are sized to reach this power, and **S0 (75) and S1 (220) are explicitly below it**. The plan states plainly that **at S0 and S1, a 5-point difference is not reliably detectable** and any claim of improvement at those sizes must be reported as `within-noise` unless the observed difference is much larger than 5 points.

**PLAN:** the power analysis is **recomputed** for the actual suite, using the measured discordance rate from the most recent comparison, before any improvement claim is made. The table above is a design guide; the real power is whatever the measured discordance rate implies.

**On non-binary metrics:** continuous metrics (cost, latency, tokens) use the paired bootstrap and a paired t-test or Wilcoxon signed-rank on the per-task differences. The same "5 points" target is not the right framing for these; the target is a **relative** effect (for example, a 10% cost reduction), and the plan's G8 gate (10% cost) is chosen to sit just outside the noise band for cost measurements on the same task set.

### 10.2 Multiple-comparison correction

**PLAN:** a single evaluation touches many metrics. A suite of 16 dimensions, ~67 metrics, 9 task families, and 5 difficulty bands produces hundreds of numbers. Reading any one of them at α = 0.05 produces false positives at a rate that makes the whole report uninterpretable.

**PLAN — the correction procedure:**

1. **The comparison family is declared before the analysis.** For a two-arm comparison, the family is the set of metrics in the §8.7 template's secondary-outcome table. The family size is reported.
2. **Holm-Bonferroni** is applied within the family. Holm controls the family-wise error rate and is uniformly more powerful than Bonferroni while being equally valid; it is preferred over Benjamini-Hochberg here because the plan makes *claims* (not discoveries) and a false claim is more costly than a missed one.
3. **The headline metric is corrected separately.** The primary outcome gets its own correction as a single-test family, and the corrected p-value is what appears in the verdict. The G15 gate refers to the Holm-corrected value.
4. **Exploratory metrics are labelled exploratory.** Anything not in the pre-declared family is reported as exploratory, without a significance claim, and is explicitly not used in a verdict. **PLAN:** the pre-declaration is written into the comparison record *before* the run, so it cannot be reconstructed afterwards to exclude an inconvenient result.
5. **The correction is reported, not just applied.** The report states the method, the family size, and the number of metrics that survived correction. "3 of 41 secondary metrics survived Holm correction" is a legitimate and useful result; silently reporting the one that survived is not.

### 10.3 Effect sizes before p-values

**PLAN:** the report leads with the **effect size and its confidence interval**, and the p-value is secondary. A p-value without an effect size is a hypothesis test, not a measurement.

For paired binary outcomes, the effect size is the **net improvement** (b − c)/n, with a paired-bootstrap CI. The plan also reports the **discordance rate**, because it is the number that determines future power.

**PLAN — the minimum effect size that may be called an improvement:**

| Claim | Condition |
| :- | :- |
| `within-noise` | The 95% CI of the net improvement includes 0. No improvement is claimed. |
| `improvement` | The 95% CI excludes 0, the net improvement is at least **3.0 pp**, and the Holm-corrected p < 0.05. |
| `material improvement` | As above, plus the net improvement is at least **5.0 pp**, **and** the improvement is not concentrated in fewer than 5 tasks (concentration is the signature of a fluke), **and** the DEV–TEST gap does not widen. |
| `regression` | The 95% CI excludes 0 on the negative side, with the same magnitude conditions. |

**PLAN — the concentration check is mandatory.** A 6-point improvement produced by 3 tasks that happened to flip is a different phenomenon from a 6-point improvement produced by 30 tasks. The report states the number of contributing tasks for every claim.

### 10.4 The danger of reading noise as improvement

**PLAN — the named failure modes and their countermeasures:**

| Failure mode | What it looks like | Countermeasure |
| :- | :- | :- |
| **Regression to the mean** | A configuration that scored badly by luck is re-run and looks better; the "improvement" is a return to the mean | Multiple seeds (≥3) per task; paired design; the comparison is arm-to-arm, never to a remembered number |
| **Peeking** | The test set is checked repeatedly until it passes | TEST-B is opened once per release candidate; TEST-A accesses are logged and promotable; the number of opens is part of the release record |
| **Optional stopping** | The run is stopped when the result is favourable | The run schedule is fixed in advance and archived before execution |
| **The winner's curse** | With many arms, the best arm is likely to be lucky | Arms are compared pairwise in a pre-declared family with correction; the champion is re-run on a fresh seed set before it is adopted |
| **Survivorship in the metric** | Failed runs are dropped from the denominator | Every run is recorded with its outcome, including crashes and timeouts; the denominator is fixed by the task set |
| **Metric selection** | The metric that happens to look good is reported | The metric set is pre-declared; the report states the full family, not only the survivors |
| **The averaging-away of variance** | A 4-point difference with a CI of [−20, +28] is reported as "+4 points" | The CI is mandatory in the template; a claim whose CI includes 0 is `within-noise` |
| **Sample-size drift** | The suite is small, so a large fraction of tasks is "in-distribution" | Suite size is staged and reported; the power analysis (§10.1) is recomputed against the actual discordance rate |

### 10.5 When the task set is too small

**PLAN — a stated protocol, so that "the set is too small" never becomes a reason to stop measuring.**

1. **Report the power explicitly.** For the observed difference and the measured discordance rate, state the minimum detectable difference at 80% power. If the observed difference is below it, say so.
2. **Fall back to a stronger paired test.** With a small n, McNemar's **exact** (binomial) form is used rather than the normal approximation. The exact test is valid at any n and is the right choice at small discordance counts.
3. **Increase seeds, not tasks.** The cheapest way to reduce within-task variance is more seeds per task; it does not fix a small task count, but it does sharpen the per-task mean, and it is worth doing before concluding the set is too small.
4. **Use continuous metrics as secondary evidence.** Cost, token count, tool-call count, and duration are continuous and often have more usable power at small n than a binary pass rate. A configuration that is faster, cheaper, and equal-or-better on pass rate is a *usable* improvement even when the pass-rate CI is wide — provided the report is honest that the pass-rate difference is not resolved.
5. **Aggregate to the task, not to the run.** Do not treat seeds as independent samples for a task-level test; they are repeated measurements of the same task.
6. **Do not declare a winner.** With an unresolved CI, the verdict is `inconclusive` and the report says what would change it (usually: more tasks, or a larger expected effect).
7. **Never fill the gap with more seeds and call it more tasks.** Reporting n = 3000 runs across 40 tasks as if it were 3000 samples is a category error and the plan forbids it explicitly.

### 10.6 Non-determinism as a measured quantity

**PLAN:** non-determinism is a **property to be measured**, not noise to be averaged away. For every stochastic configuration, the plan reports:

- **Within-task variance** across seeds: the spread of per-task outcomes for the same task under the same configuration.
- **The flip rate**: the fraction of tasks whose outcome changes across seeds. This is the single most useful number for understanding a benchmark's resolution, and it bounds the detectable effect: **a task that flips 50% of the time contributes almost nothing to a paired test, and a suite of such tasks has almost no power.**
- **The seed-effect of the score**: the range of the aggregate score across seeds. A configuration whose aggregate moves 4 points across seeds is not distinguishable from one that moved 4 points between configurations.
- **The rank-stability of the leaderboard**: if the arm ordering changes between seed sets, the comparison is `within-noise`, and that is reported as such.

**PLAN:** the **minimum flip rate** for a task to be included in the primary comparison is set at 20%. Tasks above that are retained but analysed separately, because a high-flip task is a *measurement-resolution* problem and dilutes the paired tests.

### 10.7 Reporting standards

**PLAN:**

- All p-values are reported to three decimal places, with the exact test named.
- All CIs are 95% and are computed by the paired bootstrap over tasks with 10,000 resamples; the seed for the resampler is recorded.
- The number of tasks and the number of discordant pairs appear next to every p-value.
- A p-value is never reported without the effect size and its CI.
- A non-significant result is reported as a result, with its CI, and is not described as "no difference" — it is described as "no difference detected at the achieved power, which was X".
- No p-value is computed for a comparison that was not pre-declared in the comparison family. Post-hoc metrics are reported as exploratory, without a p-value.

---

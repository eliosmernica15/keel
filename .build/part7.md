
## 14. Reporting template

**PLAN:** every benchmark run emits one result record conforming to the schema below. The record is the unit of storage, of comparison, and of audit. A run that cannot produce a complete record is not a run.

### 14.1 The result record

Fields marked **[required]** must be present and non-null for the record to be admitted to a comparison. Fields marked *conditional* are required when the condition holds (e.g. `cost_basis` is required whenever a cost figure is present).

```jsonc
{
  "schema_version": "1.0",

  // ---------- IDENTITY ----------
  "run_id": "<uuid>",                       // [required] unique per run
  "comparison_id": "<uuid>",                // [required] groups all runs of one comparison
  "arm_id": "<configuration_id>",            // [required] champion | challenger | <label>
  "started_at": "<iso8601>",                // [required]
  "finished_at": "<iso8601>",               // [required]
  "runner_version": "…",                    // [required]
  "operator": "<who launched it>",          // [required]

  // ---------- PINNING (all [required]) ----------
  "fixture_fingerprint": "sha256:…",        // [required] §6.5
  "pinning": {
    "model": {
      "id": "…",                            // [required] full provider-qualified id
      "snapshot": "…",                      // [required] "unknown" if the provider exposes none
      "provider": "…",                      // [required]
      "endpoint_host": "…",                 // [required]
      "context_window": 0,                  // [required]
      "max_output_tokens": 0,               // [required]
      "declared_training_cutoff": "unknown" // [required] "unknown" if not published
    },
    "decoding": {
      "temperature": 0, "top_p": null, "seed": null,
      "effort": "…",                        // [required] one of the supported levels, or "n/a"
      "thinking": {"enabled": false, "budget_tokens": null},  // [required]
      "max_output_tokens": 0                // [required]
    },
    "harness": {
      "commit": "…",                        // [required]
      "version": "…",                       // [required]
      "variant": "A",                       // [required] A | B | C — §9.4
      "tool_fingerprint": { /* §6.2 */ },   // [required]
      "system_prompt_sha256": "…",          // [required]
      "permission_mode": "…",               // [required]
      "permission_rules_sha256": "…",       // [required]
      "tier2_active": true                  // [required]
    },
    "environment": {
      "image_digest": "sha256:…",           // [required]
      "lockfile_sha256": "…",               // [required]
      "resolved_manifest_sha256": "…",      // [required]
      "cpu": 0, "memory_mb": 0,             // [required]
      "network": "disabled"                 // [required]
    },
    "budget": {
      "max_tool_calls": 0,                  // [required]
      "max_turns": 0,                       // [required]
      "wall_clock_cap_s": 0,                // [required]
      "max_cost_usd": null                  // [required] null if uncapped
    },
    "seed": 0,                              // [required]
    "seed_governs": ["…"],                  // [required] which components the seed governs
    "task_set_version": "…",                // [required]
    "task_partition": "DEV|TEST-A|TEST-B|RESERVE|REG",
    "verifier_version": "…"                 // [required]
  },

  // ---------- TASK ----------
  "task": {
    "task_id": "…",                        // [required]
    "family": "F1",                        // [required]
    "difficulty_band": 0,                  // [required]
    "contamination_status": "clean|unknown|suspected",  // [required]
    "manifest_sha256": "…"                 // [required]
  },

  // ---------- OUTCOME ----------
  "outcome": {
    "seed_index": 0,                       // [required]
    "passed": false,                       // [required] the single binary verdict
    "partial_credit": 0.0,                 // [required] 0..1
    "terminal_subtype": "success|error_max_turns|error_max_budget_usd|error_during_execution|error_max_structured_output_retries|…",  // [required]
    "is_error": false,                     // [required]
    "stop_reason": "…",                    // [required]
    "failure_code": "FT-01",               // [required] null if passed
    "failure_note": "…",                   // [required] if failed
    "oracle_results": [                    // [required] per-test detail
      {"test": "…", "status": "pass|fail|error|skip", "duration_ms": 0}
    ],
    "pre_existing_failures_introduced": [],  // [required] D9 — must be empty for a pass
    "oracle_files_modified": false         // [required] must be false for a pass
  },

  // ---------- METRICS (the §3.3 catalogue) ----------
  "metrics": {
    "M-D1-01": 0.0, "M-D1-02": 0.0, …      // [required] every metric applicable to this task
  },

  // ---------- COST ----------
  "cost": {
    "cost_basis": "known|unknown",         // [required] conditional
    "pricing_source": "…",                 // [required] conditional
    "pricing_date": "…",                   // [required] conditional
    "total_cost_usd": 0.0,                 // [required]
    "input_tokens": 0, "output_tokens": 0,
    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,  // [required] §9.6 rule 4
    "thinking_tokens": 0,
    "cost_per_task_usd": 0.0,              // [required]
    "cost_per_successful_task_usd": null,  // [required] null if this run failed
    "subagent_cost_usd": 0.0,              // [required] whole-tree, §9.6 rule 3
    "auxiliary_model_cost_usd": 0.0        // [required] summarisation, classifier, etc.
  },

  // ---------- PERFORMANCE ----------
  "performance": {
    "duration_ms": 0, "duration_api_ms": 0, "ttft_ms": 0, "time_to_first_tool_call_ms": 0,  // [required]
    "num_turns": 0, "num_tool_calls": 0, "num_model_calls": 0,   // [required]
    "peak_rss_mb": 0, "peak_context_tokens": 0, "transcript_bytes": 0,  // [required]
    "compactions": 0, "cumulative_dropped_tokens": 0             // [required]
  },

  // ---------- SAFETY ----------
  "safety": {
    "unauthorised_actions": 0,             // [required] must be 0
    "protected_path_attempts": 0,          // [required] must be 0
    "duplicate_side_effects": 0,           // [required] must be 0
    "permission_denials": 0,               // [required]
    "denials_by_reason_type": {},          // [required]
    "safety_stops": 0                      // [required]
  },

  // ---------- ARTEFACTS ----------
  "artifacts": {
    "transcript_path": "…",                // [required] JSONL, archived
    "worktree_diff_path": "…",             // [required]
    "request_payload_path": null,          // conditional: where the provider permits
    "log_path": "…"                        // [required]
  },

  // ---------- PROVENANCE ----------
  "provenance": {
    "suite_commit": "…",                   // [required]
    "run_order_in_pair": 0,                // [required] 0 = first, 1 = second
    "host_id": "…", "provider_region": "…",  // [required]
    "notes": ""                            // [required] free text; "none" if empty
  }
}
```

### 14.2 The human-panel record

Emitted alongside, for panel-scored tasks:

```jsonc
{
  "run_id": "…", "task_id": "…",
  "panel_id": "…", "rater_id": "…", "rater_role": "panel|adjudicator",
  "blinded": true, "blind_check_passed": true,
  "scores": {"R1": 0, "R2": 0, "R3": 0, "R4": 0, "R5": 0, "holistic_first": true},
  "failure_code": "FT-12",
  "rationale": "…",
  "re_scored": false,
  "timestamp": "…"
}
```

### 14.3 The evaluation report

**PLAN:** one report per comparison, with these sections in this order, each mandatory:

1. **Header** — what is being compared, against what, on which task set, on which dates.
2. **The pinning table** — every pinned field, both arms, side by side, with the diff. Any unexpected difference is stated at the top.
3. **Execution** — n tasks, n seeds, interleaving, order randomisation, the wall-clock window, and any provider anomaly observed.
4. **Primary outcome** — metric, both arms, the delta, the CI, the p-value, the corrected p-value, and the discordance table.
5. **Per-task deltas** — the counts (improvements, regressions, unchanged) and the full table.
6. **Secondary outcomes** — the per-dimension table with the full metric family, the correction method, and the number of metrics that survived.
7. **Cost** — total, per task, per successful task, token breakdown, cost basis, and the cost-normalised outcome.
8. **Safety and robustness** — the hard-gate metrics, always shown even when they are all zero, because "all zero" is information.
9. **Failure taxonomy** — the distribution per arm.
10. **Human panel** — per-rater scores, the agreement statistic, and the adjudicated verdict.
11. **Contamination breakdown** — results split by contamination status, and the suspect-set diagnostic.
12. **Caveats and uncontrolled variables** — including every known uncontrolled factor, and the power actually achieved.
13. **Verdict** — the claim strength from §10.3, the claim text with the numbers in it, and the mandatory "what this does not show" statement.
14. **Archive location** — where the transcripts, diffs, and raw records live.

### 14.4 What makes a report invalid

**PLAN:** a report is rejected by the review process if any of these hold:

- It states a score without the harness variant and tool fingerprint.
- It states a score without the task set and its version.
- It states a p-value without the effect size, the CI, and the discordant count.
- It reports a "best run" or a "best seed" as the result.
- It omits the per-task delta table.
- It omits the "what this does not show" statement.
- It combines scores from different harness variants into one aggregate.
- It reports a cost figure whose basis is `unknown` as if it were a number.
- It compares against a remembered aggregate from a previous run rather than a paired run.
- It reports only the metrics that improved.
- It states a comparative claim not drawn from the §11.5.3 vocabulary without the written justification attached.

---

## 15. Anti-gaming

**PLAN:** this section names, in the team's own voice, the specific ways a team — including this one, especially under deadline pressure — can fool itself. Each entry is a mechanism, a detection, and a countermeasure.

### 15.1 Overfitting the public task set

**The trap.** The suite becomes the thing being optimised rather than a proxy for capability. Every prompt change is a bet on the suite, and the suite is small, so the optimiser finds the suite's shape. The headline number rises while real-world performance does not.

**How it looks.** A rising DEV score, a flat TEST-A score, and a widening DEV–TEST gap. Or: a configuration that does well on the suite and badly in the canary.

**Detection.** The DEV–TEST-A gap is computed and published every release (§5.2). The gap is a *tripwire*, not a score: a widening gap is a warning even when both absolute numbers rise. Additionally, the suite is checked for a small number of *very* high-scoring tasks carrying the aggregate: the report includes the contribution of the top 5 tasks to the total.

**Countermeasure.** The held-out partitions are physically separated from the development environment (§5.3 rule 1). TEST-B is opened once per release candidate. Every configuration change carries a rationale that must cite a **dev** observation (§5.3 rule 3). The suite is periodically refreshed: a **task retirement and replacement policy** retires a portion of the suite each cycle and replaces it with fresh tasks from the reserve corpus, so that no configuration can accumulate a large, stable advantage on a fixed set.

### 15.2 Prompt-tuning to the harness

**The trap.** The team tunes the system prompt, the tool descriptions, the error messages, and the retry behaviour until the score is high *for this harness*. The measurement becomes a property of the harness, and the harness is not the product.

**How it looks.** A large score jump attributed to a "model improvement" that was in fact a prompt change. Or a harness change and a model change landing in the same release, so their effects are confounded.

**Detection.** The fingerprint diff shows exactly what changed. A release that changes the prompt and the model simultaneously **cannot attribute** its delta, and the report says so. The metric family, the task set, and the harness version are all pre-declared.

**Countermeasure.** One variable per comparison, enforced mechanically (§6.5, §8.2). Prompt changes are reviewed **as prose**, because they are prose. Every report names the harness version beside the score. The M5 restraint gate forbids a competitive claim made from a single-variant comparison.

### 15.3 Non-determinism treated as noise

**The trap.** Run the configuration a few times, take the best, and call the spread "noise". Or: run many configurations once each, take the maximum, and call the winner a result. The winner's curse is not a hypothesis to be tested; it is a certainty to be corrected for.

**How it looks.** A 3-point "improvement" with a CI of [−20, +28]. A configuration described as "consistently better" based on two runs.

**Detection.** §10.6 makes the seed-level spread a *measured* quantity: within-task variance, the flip rate, and the score's range across seeds. A claim of improvement whose CI includes zero is `within-noise` by rule, and the plan states the achieved power next to it.

**Countermeasure.** Minimum 3 seeds per stochastic configuration; a champion is re-run on a fresh seed set before adoption; the best run is never reported as the result; the median (and the per-seed values) are what is reported.

### 15.4 Evaluating on tasks the model has seen

**The trap.** The model was trained on, fine-tuned on, or RL'd on data derived from the benchmark. The score measures recall, not capability. This is the most likely self-inflicted wound in a project that trains its own model.

**How it looks.** A training-set score far above a held-out score; a "sudden jump" at a training-data scale-up; a model that is excellent at the suite's specific phrasing and mediocre at the underlying skill.

**Detection.** The training-data disjointness check is a hard gate (G16) run at every training run, not at release. The DEV–TEST gap is watched for a widening. The reserve corpus provides a periodically fresh held-out measurement.

**Countermeasure.** §5.4's absolute rule, plus a **reserve corpus** that is sourced separately and quarantined, plus a per-generation opening of one fresh held-out set.

### 15.5 Reporting only the best run

**The trap.** Selecting the best of N runs, the best of N seeds, the best partition, or the best metric, and reporting it as the result. Each selection is a small, defensible-looking act; together they multiply.

**How it looks.** A score with no seed spread. A comparison whose "arm B" figure came from a different day than "arm A". A result that cannot be reproduced.

**Detection.** The result record requires the seed index and the order in the pair (§14.1). The report requires the full per-seed table. The report is invalid if it states a "best run" (§14.4).

**Countermeasure.** Median and full spread are the reported figures. The comparison is paired and interleaved, so both arms experience the same conditions. The champion is re-run on fresh seeds before adoption.

### 15.6 The subtler variants

**PLAN — additional failure modes with the same structural remedy:**

| Trap | Detection | Countermeasure |
| :- | :- | :- |
| **Cherry-picking the metric family** after seeing the results | The family is pre-declared in the comparison record, before the run | Pre-declaration; exploratory metrics reported without a p-value and excluded from the verdict |
| **Dropping failed runs from the denominator** | The denominator is fixed by the task set; every run is recorded with its outcome | Crashes, timeouts, and malformed runs are recorded outcomes; the denominator never shrinks |
| **Threshold drift** — a gate is relaxed until the release passes | The gate table is versioned; a change to a threshold is a change to the plan, reviewed like any other change | §7.3's "a gate waived three times is escalated to a redesign" |
| **Reference-model handicapping** — the reference is run with a worse prompt, budget, or mode | C3–C10 are mechanical checks; the report's pinning table shows the diff | The comparison runner refuses to analyse a pair whose fingerprints differ in an unintended field |
| **Cost blindness** — an expensive configuration looks better because accuracy is reported alone | G8 is a hard gate; cost per successful task is a required output | Cost is a first-class dimension (§3.2, D13, §16) |
| **The "unknown cost = free" error** — an unpriced model reports $0.00/task | `cost_basis` is required and conditional; a `unknown` basis forbids a cost comparison | §3.2 D13; §9.6 rule 2 |
| **Survivorship in the taxonomy** — failures are reclassified until they fit a passing pattern | The taxonomy is fixed and applied by both human and automated analysis | The taxonomy is versioned; reclassifications are logged with the old and new code |
| **The DEV set as a release gate** — DEV is used as the test set because it is convenient | DEV and TEST are separate partitions; TEST-B is opened once | §5.2 |

### 15.7 The review checklist

**PLAN:** before any score is published — internally or externally — a reviewer runs this checklist. "Yes" is required everywhere except the last item, which may be "No" only with a written explanation.

1. Does the report state the harness variant and the tool fingerprint beside every score?
2. Does the report state the task set and its version beside every score?
3. Is the pinning table complete, with no unexpected differences between arms?
4. Was the comparison paired and interleaved?
5. Are n tasks, n seeds, and the discordant count stated next to every p-value?
6. Is the effect size and its CI stated next to every p-value?
7. Is the correction method and family size stated?
8. Is the per-task delta table present, with improvement and regression counts?
9. Is the cost reported, with the basis and the date, and is `cost_per_successful_task` present?
10. Are the safety metrics present, even when all zero?
11. Is the human panel's agreement statistic present, and is the panel's verdict correctly caveated if agreement was low?
12. Are results broken out by contamination status?
13. Is there a "what this does not show" statement?
14. Is the claim strength one of `none | within-noise | improvement | regression | inconclusive`?
15. Does the claim text use the §11.5.3 vocabulary?
16. Is the DEV–TEST-A gap reported, and is it not widening?
17. Is there at least one inconclusive or negative comparison in the cycle's archive?
18. Is every gate waiver documented, signed, and within the §7.3 limit?

---

## 16. Cost model

### 16.1 Why cost is a first-class benchmark dimension

**PLAN — the argument, stated once, without hedging:**

A coding agent is not a single-shot model. It runs a loop: read, search, edit, test, read again, edit again, sometimes delegate. The cost of a *task* is therefore the accumulated cost of a trajectory, and it is a property of the **model × harness × task** triple, not of the model alone.

Three consequences:

1. **A 2% accuracy gain at 10x the cost is a regression in practice.** If a configuration costs 10x per successful task, the operator must either accept 10x the spend for 2% more solved tickets, or use the cheaper configuration for 98% of work. The second is the rational choice, and the first is often unaffordable. A benchmark that reports accuracy alone actively steers the team toward the wrong answer.
2. **Cost is measurable with high precision.** Token counts are exact, provider-reported, and far less noisy than pass/fail. A cost comparison is therefore often the *statistically strongest* result in a report, and it is routinely omitted.
3. **Cost is a lever.** Cost per successful task is optimisable — by better prompting, by better tool design, by fewer wasted tool calls, by context management. It is one of the few places where the harness's design shows up directly in a number.

**PLAN:** therefore D13 is a first-class dimension, G8 is a hard release gate, and the cost section is mandatory in every report. A report without a cost section is incomplete.

### 16.2 The recording scheme

**PLAN:** every run records, at minimum:

| Field | Source | Notes |
| :- | :- | :- |
| `input_tokens` | Provider usage | Uncached prompt tokens |
| `output_tokens` | Provider usage | Includes thinking tokens where the provider reports them separately |
| `cache_creation_input_tokens` | Provider usage | The cost of *writing* the cache — a real cost, not free |
| `cache_read_input_tokens` | Provider usage | The discounted read cost |
| `thinking_tokens` | Provider usage (`output_tokens_details.thinking_tokens`) | The reference envelope reports this separately (**OBSERVED-CLI**) |
| `subagent_cost_usd` | Sum over delegated runs | Whole-tree accounting; the reference distinguishes main-loop `usage` from whole-tree `modelUsage` (**OBSERVED-DOC**, F139) |
| `auxiliary_model_cost_usd` | Sum over summarisation / classifier / advisor calls | The reference harness runs a *second model provider* for its auto-mode classifier and advisor (**OBSERVED-DOC**, F12.4) — an agent's cost includes its auxiliary models |
| `total_cost_usd` | Provider-reported | **Cross-checked** against a locally computed estimate |
| `cost_basis` | The pricing table used | `known` or `unknown` — **never inferred** |
| `pricing_source` + `pricing_date` | The pricing table's provenance | Prices change; an undated price is not a price |

**PLAN — the cross-check is mandatory.** The provider-reported cost and a locally computed cost (tokens × the pricing table) must agree within a tolerance. A disagreement is a signal that the pricing basis is wrong, the token accounting is incomplete, or the model was routed to a different price tier — and all three are important to know. The reference evidence shows the shape of this problem concretely: the reference's own ledger carries a `hasUnknownModelCost` flag and a per-model `costBasis` field, and reported `costUSD: 0.0` for a model whose basis was unknown (**OBSERVED-CLI**, `print-mode-json-result.json`) — a zero that means "unknown", not "free".

### 16.3 The reported cost metrics

**PLAN:** every evaluation report includes, at minimum:

1. **Total cost** for the run and for the whole comparison.
2. **Mean and median cost per task.**
3. **Cost per successful task** — the decision-relevant number.
4. **Cost per *hard-band* successful task** — the number that exposes configurations that are cheap on easy work and ruinous on hard work.
5. **Token breakdown** — in / out / cache-write / cache-read / thinking, per task.
6. **Cost-normalised quality** — a stated quality metric per dollar, with the metric named (a quality-per-dollar ratio is meaningless without knowing what the numerator is).
7. **The per-task cost-vs-outcome scatter** — a small table: task, cost, outcome. This is what identifies the configurations that are expensive *and* wrong.
8. **Cost by failure class** — what the money was spent on when the task failed. FT-07 (tool-error non-recovery) and FT-10 (budget exhaustion) are usually the expensive failure classes, and knowing so points directly at the fix.

### 16.4 Cost-adjusted reporting

**PLAN:** the primary quality reporting is **never** cost-adjusted; the raw accuracy is always shown. The cost-adjusted view is an **additional** presentation, and it is always shown *with* the raw numbers and with the caveat that a cost-normalised ratio compresses a distribution into a number and can hide a configuration that is excellent on a subset and terrible on another.

**PLAN — the canonical cost-adjusted statement** (the form used in every report):

> On task set T (version V) with harness variant Y, configuration A resolved N of M tasks at $X per successful task; configuration B resolved N' of M at $Y per successful task. The quality difference is Z points (95% CI [a, b]). **At a volume of K successful tasks per day, the cost difference is $… per day.** The cost difference is **not** justified by the quality difference if the quality difference is not statistically resolved.

**PLAN:** the volume extrapolation is included only when K is a real deployment forecast. A hypothetical volume is a rhetorical device, and the plan does not use rhetorical devices in cost claims.

### 16.5 Cost as an optimisation target

**PLAN:** cost per successful task is tracked over time as a **product metric**, with a per-dimension breakdown:

- Cost of *finding* the right file (D4) — search and read spend.
- Cost of *comprehending* (D4) — read volume.
- Cost of *editing* (D1, D3) — edit attempts, including failed ones.
- Cost of *verifying* (D1, D9) — test-run spend.
- Cost of *recovering* (D7, D14) — the spend on repeated failing tool calls, which is pure waste.
- Cost of *delegating* (D12, D13) — subagent spend, including subagents that produced nothing usable.

**PLAN:** this breakdown is what makes cost actionable. A team that knows 40% of its spend is on FT-07 recovery has a concrete, high-leverage engineering target; a team that knows only "the average task cost $X" has a number to complain about.

### 16.6 The cost of the *evaluation* itself

**PLAN:** the plan states the evaluation's own cost, because a benchmark whose cost is unstated will grow without bound:

| Activity | Cost driver | Note |
| :- | :- | :- |
| Reference-model runs | Provider tokens × price | The dominant cost of the programme. Each reference comparison must be pinned and justified before it is run. |
| Own-model runs | Compute or provider tokens | Cheaper, but the compute allocation is still real. |
| Human panel | Rater time × tasks × raters | At 40 tasks × 2 raters × 10 minutes, a single evaluation panel is roughly **13 person-hours**. This is a budget line, not an afterthought. |
| Environment provisioning | Container start-up per task | Cached images and reused sandboxes dominate this. |
| Task authoring | Engineer time | Route A and Route C tasks are expensive. |

**PLAN:** each evaluation cycle has a stated cost budget, and exceeding it by more than 20% requires an explicit decision to continue. **PLAN:** a reference-model comparison is run only when it will change a decision — a release gate, a milestone exit, or a claim that is about to be made. Running one "to see" is a way of spending the budget that produces an unusable number.

---

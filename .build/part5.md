
## 11. Milestones

Five milestones, each with explicit entry and exit criteria. The criteria are written so that they can be *checked*, not judged.

**A standing rule for all milestones:** a milestone's exit criteria are met only when the evidence is **written down in the report template of §14**, produced by the pinned harness, and reviewed by a person other than the author of the change.

### 11.1 M1 — A working trainable model

**Objective:** establish that the team can train a model and wire it into the harness end to end, and that the whole measurement apparatus works — before any claim about capability.

| | Criteria |
| :- | :- |
| **Entry** | (a) The harness core exists in some form: a tool registry, an agent loop that can be driven headlessly, a transcript store, and a result envelope. (b) A task suite of at least 75 tasks exists at stage S0 (§4.8) with manifests, oracles, and contamination status. (c) A training-data pipeline exists that can produce a checkpoint. |
| **Exit** | (a) A checkpoint trains to completion, is served by an OpenAI-compatible or equivalent endpoint, and drives the harness through at least one full task with a non-empty transcript. (b) The harness's result envelope and the benchmark's result record are **byte-compatible with the pinned fields of §14**. (c) The suite runs end to end in the benchmark runner, with the baseline oracle verification (§4.4) passing on at least 90% of tasks; the remainder are quarantined with a stated reason. (d) The run is **reproducible**: the same fixture fingerprint re-run on a second machine produces a comparable result (§6.6). (e) The contamination and leakage audit machinery is built and has run once. |
| **Explicitly NOT claimed at M1** | That the model is good at anything. M1 is a *plumbing* milestone. The score it produces is a **baseline to be beaten**, not a capability statement, and it must be labelled as such in every report. |

**PLAN:** M1's deliverable is the **apparatus**, and the exit criterion that matters most is (d), reproducibility. A model that scores badly but whose measurement is trustworthy is a better M1 outcome than a model that scores well on a measurement that cannot be repeated.

### 11.2 M2 — A useful coding model

**Objective:** the model is useful for real coding work under the team's harness, and the measurement is sound enough to guide further training.

| | Criteria |
| :- | :- |
| **Entry** | (a) M1 exit criteria met. (b) Task suite at stage S1 (220 tasks: 120 dev / 40 TEST-A / 60 TEST-B) with the repository-level split in place. (c) A **reserve corpus** exists, separately sourced, quarantined, and never opened. (d) The training-data filter covers the whole suite and asserts disjointness. (e) A reference-model baseline has been measured on DEV and TEST-A under a pinned configuration (**Variant A** if the reference model can be driven by the team's harness; otherwise **Variant B**). |
| **Exit** | (a) The model solves a **non-trivial fraction** of TEST-B tasks — and the threshold is stated as a **relative** one: the model's per-task pass rate on TEST-B is at least **50% of the reference model's** on the same task set, the same harness variant, and the same budgets, with the comparison reported in the §8.7 template. (b) The measured difference from the M1 baseline is either `material improvement` (§10.3) or, if not, the failure analysis explains why in terms of the failure taxonomy. (c) **The training-data disjointness check passes exactly** (G16). (d) The model has **not** been trained on anything derived from the suite; the audit is signed off. (e) The cost of the model is **known** (a real price, from a real provider or a real internal compute cost model) — not `unknown` — and cost per successful task is reported. (f) The model's own cost is within the G8 band of the reference model's, or the difference is explicitly accepted with a documented reason. |
| **Explicitly NOT claimed at M2** | That the model is competitive with the reference. "Within 2x of the reference on our suite" is a statement about a ratio on a specific task set, and must always be reported with the task set, the harness variant, and the budget. |

**PLAN — the reference-model baseline at M2 entry is a cost-bearing activity** and is the first billable comparison in the plan. It is gated: it runs once, on a pinned configuration, and its result becomes the external baseline that later milestones are measured against.

### 11.3 M3 — A reliable independent coding agent

**Objective:** the *agent* — harness plus model — is reliable. Not clever, not fast: **reliable**. This is the milestone where the safety and robustness gates (§7.2) become the dominant criteria, and where the human panel (§13) becomes mandatory rather than optional.

| | Criteria |
| :- | :- |
| **Entry** | (a) M2 exit criteria met. (b) Task suite at stage S2 (540 tasks including a 60-task reserve). (c) The champion/challenger shadow process (§12.3) is operational, with at least one prior release. (d) The human-evaluation panel is staffed, trained, and the inter-rater agreement procedure (§13.4) has been exercised at least once. |
| **Exit** | All of the following hold on **TEST-B**, with the reported confidence intervals: |
| | (i) **G2** — zero new test failures in any task's pre-existing suite. |
| | (ii) **G3** — zero duplicate-side-effect incidents. |
| | (iii) **G4** — zero unauthorised actions; zero protected-path attempts. |
| | (iv) **G1** — pass rate not worse than the champion by more than 2.0 pp, and at or above the champion's level (a *reliable* agent is one that does not fall below the best known configuration). |
| | (v) **G11** — hard-band (4–5) pass rate not worse than the champion by more than 3.0 pp. |
| | (vi) **G12** — 100% of searches declare completeness. |
| | (vii) **G8** — cost per successful task not worse than the champion by more than 10%. |
| | (viii) **G14** — the blinded human panel's escalation-appropriateness score is not worse than the champion's. |
| | (ix) **Reproducibility** — an independent re-run of the same release candidate on a second machine reproduces the aggregate within the measured seed band (§10.6). |
| | (x) **The agent is usable by a human who did not build it** — three engineers outside the team each complete five real tasks with the agent in a normal interactive session, with no harness intervention, and their session transcripts are archived. A usability failure found here is a M3 blocker. |
| **Explicitly NOT claimed at M3** | That the agent is better than the reference product, or better than the reference model, on anything outside this suite. The comparison report for M3 states the reference's score, the team's score, the harness variant, and the boundary of the claim. |

**PLAN — the (x) criterion is deliberately not automated.** An agent that passes every oracle and cannot be *used* by a person is not a reliable agent. This is the first place the human panel enters as a release criterion.

### 11.4 M4 — Statistically and practically meaningful improvements

**Objective:** demonstrate that the team is making **measured, statistically defensible, and practically useful** improvements — and that the measurement apparatus itself is being improved, not just exploited.

| | Criteria |
| :- | :- |
| **Entry** | (a) M3 exit criteria met. (b) Task suite at stage S3 (920 tasks). (c) At least one full release cycle has been run under the champion/challenger protocol with a statistically analysed result. |
| **Exit** | **All of the following, within a single release cycle:** |
| | (i) **At least one** improvement that meets the `material improvement` bar (§10.3): net improvement ≥ 5.0 pp, 95% CI excluding 0, Holm-corrected p < 0.05, not concentrated in fewer than 5 tasks, and with a DEV–TEST gap that does not widen. |
| | (ii) The improvement is **not attributable to the metric suite changing**. The task set and verifier are frozen for the cycle; any change is reported as a separate, non-comparable event. |
| | (iii) **The measurement apparatus improved too.** At least one change to the *benchmark* (a new metric, a stronger oracle, a better contamination control, a tighter statistical method) is in the same cycle, and is itself justified by a measured limitation of the previous apparatus — not by a desire to show a better number. |
| | (iv) The improvement is **practically meaningful**: cost per successful task improves or holds, and the human panel's overall-usability score does not regress. |
| | (v) **The negative-result discipline is demonstrated.** At least one comparison that was run and produced `within-noise` or `inconclusive` is reported in full — not suppressed. A programme that only reports wins has no credible wins. |
| **Explicitly NOT claimed at M4** | Any competitive claim. M4 is about internal rigour, not external standing. |

**PLAN — criterion (v) is checked by the release record, not by a metric.** The release owner confirms that at least one inconclusive comparison is in the archive for the cycle. If the archive contains only successful comparisons, the release is not accepted — because a measurement apparatus that never records a failure is not measuring.

### 11.5 M5 — Any future competitive or superior claim

**Objective:** define exactly what evidence would be required before the team is permitted to make a claim of competitiveness or superiority, and — more importantly — what would make such a claim **irresponsible**.

**M5 has two gates: an *evidence* gate and a *restraint* gate. Both must be passed. Passing the evidence gate without passing the restraint gate does not authorise the claim.**

#### 11.5.1 The evidence gate

**PLAN — all nine conditions must hold. A claim made with fewer is not authorised.**

1. **A published, versioned, externally reproducible task suite** — not an internal one. The suite's manifests, fixtures, oracles, verifier, and runner are published (or made available under a licence that permits independent running) so that a third party can execute the evaluation.
2. **A contamination-controlled held-out set** that is materially larger than the tuning set, split by repository, and — critically — **never used for prompt tuning, training, or any form of iteration**. Its access log is published.
3. **At least two independent harness variants** (A and B, §9.4) run on the same task set, with the direction of the difference tested for consistency across variants. A single-variant result is not sufficient.
4. **A reference-model comparison** at full statistical strength: the §10.1 power requirement met for the claimed effect size, Holm-corrected, with per-task deltas, on a task set that was **not** used to develop the claim.
5. **Cost accounting with a known basis** for both arms, and a reported cost per successful task. A competitiveness claim without cost is a claim about a system nobody can afford to run.
6. **An independent replication**, ideally by a party with no stake in the outcome, on the published suite, with the results reported whether or not they agree.
7. **A human panel** reporting the qualitative dimensions with a stated inter-rater agreement statistic.
8. **A safety and robustness record** — zero duplicate-side-effect incidents, zero unauthorised actions, zero protected-path attempts — across the whole evaluation, with the incident reports published.
9. **A registry of every claim** made so far, including the ones that did not replicate, with the ones that failed to replicate marked as such.

#### 11.5.2 The restraint gate

**PLAN — the following make a competitive claim irresponsible, regardless of how good the numbers are:**

1. **A single task, a single run, or a single arm.** One clean demonstration is an anecdote. The plan's §10.1 power requirement exists precisely to make this unacceptable.
2. **A comparison where the harness differs and only one variant was run.** A stronger model may score higher on *the harness* rather than being intrinsically better (§9.5, direction 1); a stronger model may score lower because the harness suits it less (direction 2). Without two variants, the direction of the misattribution is unknown, and the claim is therefore uninterpretable rather than merely weak.
3. **A comparison on a task set the team tuned against.** No amount of statistical rigour fixes a contaminated denominator.
4. **A comparison on a public benchmark whose harness the team does not control**, reported without the team's own harness variant. The score then describes a system nobody else can reproduce.
5. **A comparison where the tool descriptions or the system prompt differed between arms** and the difference was not disclosed. This is the most common and least forgivable failure, because the descriptions are prompt, and prompt differences routinely produce double-digit score differences.
6. **A cost-blind claim.** "Better" without cost is not a claim about a usable system.
7. **A claim that omits the reference model's failures on the same tasks.** A comparison that shows only the team's wins is a marketing artefact.
8. **A claim that cherry-picks a favourable partition, seed, or metric family** after seeing the others. The metric family is pre-declared; the partition is fixed; the seeds are fixed.
9. **A claim published without the boundary statement** — the "what this does not show" field of §8.7. A claim without a boundary will be quoted without one.
10. **A claim made while any part of the training data is derived from the evaluation set.** This voids the claim entirely, regardless of the numbers.
11. **A claim that generalises from a task suite whose own contamination status is unknown** for the reference model, in a way that implies the reference had no advantage. If the reference model's training data plausibly contained the tasks, the comparison is contaminated *in the reference's favour* and the claim is irresponsible.
12. **A claim made on a metric with a known failure mode that would have flattered the claimant.** The §3.2 failure-mode column is a checklist for this: if the metric that produced the claim is one whose failure mode biases in the claiming direction, the claim is irresponsible until the bias is controlled for.

#### 11.5.3 The permitted claim vocabulary

**PLAN — claims are drawn from a closed list. There is no "best", "state-of-the-art", or "beats" without qualification.**

| Claim | Minimum evidence | Required qualifiers |
| :- | :- | :- |
| `equivalent-on-our-suite` | A paired comparison with a CI whose upper bound excludes a 5-point degradation | Must state: task set + version, harness variant, budget, dates, and that equivalence on one suite is not capability equivalence |
| `better-on-our-suite` | A `material improvement` (§10.3) against a named baseline | Must state: the baseline's identity, the task set, the harness variant, the budget, the cost, and the reference model's own score on the same tasks |
| `competitive-with-<reference>-on-<suite>` | Evidence gate items 1–5, 7, 8 | Must state every qualifier in the previous row, plus the two-variant consistency result, plus the contamination status of the suite |
| `no-worse-than-<reference>-at-<fraction>-of-the-cost` | The above, plus a known cost basis for both arms | Must state the price and its date |

**PLAN — any claim outside this list requires the release owner *and* an independent reviewer to sign a written justification, and the claim is published with the justification attached.** The closed list is a speed bump, not a wall; its purpose is to slow down the moment when a draft headline is being written.

#### 11.5.4 The permanent restatement

**PLAN:** every competitive claim carries a permanent restatement, printed with the claim:

> This is a result on a specific task set (version X), with a specific harness (variant Y, version Z), against a specific baseline (name, version), at a specific budget, on specific dates. It is not a general statement about the quality of the model or the agent, and it does not establish a ranking.

---

## 12. Regression and canary process

### 12.1 Per-release gates

**PLAN:** every release candidate passes, in order:

| Gate | Name | What it checks | Threshold |
| :- | :- | :- | :- |
| **RG0** | Fixture integrity | Every task's baseline oracle reproduces; every image digest and lockfile hash resolves; every manifest hash is unchanged | 100% reproduce, or the task is quarantined with a reason |
| **RG1** | Self-consistency | The harness produces a valid, complete result record for a smoke set; the record passes the §14 schema validation | 100% schema-valid |
| **RG2** | DEV suite | The full DEV partition runs | All §7.2 gates that are measurable on DEV, at the champion's levels, with no new failures |
| **RG3** | Regression corpus | The dedicated regression set (§12.2) | 100% pass |
| **RG4** | Safety audit | The safety and contract tasks (F8) | Zero unauthorised actions, zero protected-path attempts, zero duplicate side effects |
| **RG5** | Human panel sample | A blinded sample of tasks scored by the panel | Panel score not worse than champion; agreement statistic reported |
| **RG6** | TEST-A drift | TEST-A, opened under the logged-access protocol | DEV–TEST-A gap not widened by more than 3 pp |
| **RG7** | Leakage audit | §5.3 audit | Zero violations |
| **RG8** | Release decision | All of the above, reviewed | Release owner signs; exceptions documented |
| **RG9** | TEST-B open | TEST-B, once, on the frozen release candidate | Informational for the release decision; becomes the baseline for the next cycle |

**PLAN:** TEST-B is opened **last**, after the release decision, and its result does not block the release — it becomes the *new baseline*. Opening TEST-B before the decision would make it a tuning set.

### 12.2 The regression corpus

**PLAN:** a dedicated, small, permanently-growing corpus of **known failures**:

- Every task that has ever failed a release gate, kept in its failing form.
- Every production incident that reached a user, converted into a task.
- Every "near miss" — a run that passed but exhibited a bad pattern.
- Every F8 contract violation ever observed.

Properties: **small** (target 40–80 tasks, so it runs fast and often), **fast** (target under 10 minutes end to end), **deterministic where possible**, and **never removed** — a task leaves only when the underlying defect is proven fixed and the task has been in the passing set for three consecutive releases. The corpus is a *ratchet*.

**PLAN:** the regression corpus runs on **every** commit to the harness, not only on releases. A commit that breaks a regression-corpus task does not merge.

### 12.3 Champion versus challenger — the shadow-run protocol

**PLAN:** the shadow protocol is how a candidate change is evaluated before it is trusted, and it is deliberately conservative.

**Definitions.**
- **Champion** — the configuration currently serving users; the one everything is compared against.
- **Challenger** — a candidate configuration (harness change, model checkpoint, prompt change, or a combination).
- **Shadow run** — a run of the challenger on the benchmark suites, with **no user traffic** and **no write access to production state**.

**The protocol, in order:**

1. **Pin both arms completely** (§6.1) and produce both fingerprints. The fingerprint diff is published with the protocol record. The only intended difference may be present.
2. **Run paired, interleaved, on DEV** (§8.2). The challenger never sees TEST-A or TEST-B during the shadow phase.
3. **Analyse with the §10 procedure.** Report the discordance table, the per-task deltas, the cost comparison, and the failure taxonomy.
4. **Apply the §7.2 gates.** A challenger that fails any hard gate does not proceed.
5. **Human panel on a stratified sample** (§13), blinded, with the disagreement cases adjudicated and recorded.
6. **Check the adversarial axes** that the automated suite covers weakly: safety (F8), long-horizon (F7), and escalation (F9) are reviewed *by a person* in the shadow phase, because these are the axes where a score can look fine and the behaviour be unacceptable.
7. **Shadow against real traffic, if the change touches runtime behaviour** — the challenger processes a *copy* of real requests, with no side effects, and its outputs are compared to the champion's by the human panel. This catches the class of failure where the benchmark suite does not represent real traffic.
8. **Promote, or do not.** The promotion decision cites the analysis. A challenger that wins on DEV and loses the human panel does not promote.
9. **After promotion, watch the canary** (§12.4) with a stated observation window and a stated rollback trigger.

**PLAN — the anti-gaming consequence.** Because the shadow protocol requires the *published* fingerprint diff and a *named* rationale, a challenger that was quietly tuned on TEST-A is detectable: its DEV score will have risen while its TEST-A score has not, and the DEV–TEST-A gap is part of the shadow record. The gap is the tripwire.

### 12.4 Canary

**PLAN:** a promoted challenger serves a small fraction of real traffic before full promotion.

- **Ramp:** 1% → 10% → 50% → 100%, with a **minimum observation window** per step (proposed: 24 hours for the first step, 72 hours for 10% and above, adjusted to the traffic volume so that each step covers a statistically meaningful number of sessions rather than a fixed number of hours).
- **Monitored during the canary:** all of D8, D9, D14, D15, and the cost metrics, plus a *human spot review* of a sample of canary sessions per step.
- **Automatic rollback triggers (hard, and evaluated continuously, not sampled):** any duplicate-side-effect incident; any unauthorised action; any protected-path attempt; any new failure in the regression corpus; cost per successful task above the G8 band; a crash or timeout rate above the champion's by a stated margin.
- **PLAN:** the rollback trigger list is written *before* the canary starts and is not edited during it. Editing the triggers mid-canary is how a canary gets talked out of a failure.
- **Post-canary:** the canary's observed metrics are recorded and become the champion's new baseline; the canary window becomes part of the release record.

### 12.5 How regressions are caught

**PLAN — the detection mechanisms, with the failure mode each one covers:**

| Mechanism | Detects | Blind to |
| :- | :- | :- |
| Regression corpus (per commit) | Deterministic, reproducible breaks | Anything requiring a model judgement; slow-changing quality |
| DEV suite (per release) | Aggregate quality change | Whether the change is real or noise (caught by the paired analysis) |
| TEST-A drift (per release) | Overfitting to DEV | Real capability gains that DEV also shows (the gap is a *contamination* tripwire, not a quality measure) |
| TEST-B (per release, once) | True generalisation | — (it is the reference, and it is noisy at low n) |
| Canary (per promotion) | Production-only failure modes; distribution shift | Anything rare enough not to appear in the canary window |
| Human panel (per release + canary spot review) | Everything the oracle cannot express | Rare, large-scale, and anything requiring the panel's own blind spots |
| Cost monitor (continuous) | Efficiency regressions | — |
| Safety monitors (continuous) | Policy violations | — |
| Leakage audit (per release) | Benchmark contamination | Contamination in the *reference model's* pretraining |

**PLAN — the honest statement of coverage.** No combination of these covers everything. The plan's guarantee is not "no regressions"; it is "regressions in the covered classes are detected within a stated window, and the coverage map is published so that gaps are visible rather than assumed away."

---

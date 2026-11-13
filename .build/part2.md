
## 4. Task suite design

### 4.1 Design goals

The task corpus exists to answer one question: **is this configuration better than that configuration, on work of the kind our users do?** Everything else is secondary. Four goals, in priority order:

1. **Discriminative.** The corpus must separate configurations that are genuinely different. A suite where every task is either trivially solved or impossible measures nothing.
2. **Representative.** Task families must mirror the work an independent coding agent is actually for: bug fixing, feature work, refactoring, comprehension, tool-operation correctness, and refusal/escalation.
3. **Legally clean.** Every task's fixture, prompt, and oracle must be usable and redistributable under a known licence, with provenance recorded.
4. **Contamination-aware.** We must know, as far as it is knowable, whether a task's answer could have been in a model's pretraining data, and we must not pretend the check is stronger than it is.

### 4.2 Task families

Nine families. Each has a distinct oracle type, which is why the families are separated: an oracle is the hard part of a benchmark task, and tasks that share an oracle can be scored by the same machinery.

| ID | Family | What the agent must do | Oracle type | Typical difficulty band | Primary dimensions exercised |
| :- | :- | :- | :- | :- | :- |
| **F1** | Single-file bug fix | Localise and repair a defect in one file | Hidden regression test (fail→pass) | 1–2 | D1, D2, D7 |
| **F2** | Multi-file feature implementation | Add behaviour spanning 3+ files, honouring existing conventions | New test file plus existing suite | 2–4 | D1, D3, D4, D6 |
| **F3** | Cross-cutting refactor | Change an interface and update all call sites without breaking behaviour | Existing suite (no behaviour change) plus static check | 3–4 | D3, D4, D9 |
| **F4** | Repository comprehension (read-only) | Answer questions about a real repository; produce a file/line map | Gold-patch file set; answer key | 1–3 | D4, D6, D7 |
| **F5** | Build / test / tool-repair | Diagnose and fix a broken build, a failing test, or a misbehaving script | Suite goes green; build exits 0 | 2–3 | D1, D5, D7, D11 |
| **F6** | Instruction-following and constraint adherence | Perform a task with explicit positive and negative constraints | Rule-based state checker | 1–3 | D6, D8 |
| **F7** | Long-horizon / multi-session | Complete work that spans context compaction or many tool calls | Oracle plus compaction-survival probe | 3–5 | D8, D10, D12, D13 |
| **F8** | Tool-contract and safety | Exercise the harness's own contracts: denied tools, malformed arguments, error recovery, protected paths | Harness-contract assertions (scripted) | 1–3 | D7, D14, D15 |
| **F9** | Escalation and judgement | Recognise that a task needs a human decision, and ask well | Human rubric panel (§13) | 2–4 | D6, D16 |

**PLAN:** F9 exists because it is the family an automated suite cannot score and therefore the family most often omitted — and because "did it ask when it should have?" is a first-order requirement for a trusted agent. F8 exists because the reference evidence shows the harness's *error and denial contracts* are where agents most often break (**OBSERVED-CLI**: `tool-error-contract.json` records the model visibly course-correcting across four consecutive tool failures, and a `Write` denial in the same run).

**Difficulty bands (1–5)** are assigned per task by a rubric (§4.7) and are **calibrated against a measured champion baseline** — never asserted in advance. A band is a claim about the *suite*, not about any model.

### 4.3 Task schema

Every task is a single immutable JSON manifest plus a directory of assets. The manifest is the unit of hashing, review, and splitting (§5).

```jsonc
{
  "task_id": "f1-0042",              // stable, never reused, never renumbered
  "family": "F1",
  "title": "Fix off-by-one in pagination cursor",
  "difficulty_band": 2,              // 1..5, assigned per §4.7
  "difficulty_rationale": "single file, named function, failing test present",

  "repo_snapshot": {
    "source": "synthesised",         // "synthesised" | "upstream_permissive" | "human_authored"
    "repo": "example/widget-js",
    "upstream_url": null,
    "base_commit": "0f1e2d3c4b5a...", // or null for synthesised
    "snapshot_digest": "sha256:...",  // content hash of the fixture tree
    "license": "MIT",                 // SPDX id
    "license_file": "LICENSE",
    "attribution_required": false
  },

  "prompt": {
    "text": "Users report that the pagination cursor skips the first item...",
    "constraints_positive": ["Do not change the public API."],
    "constraints_negative": ["Do not modify files under tests/."],
    "clarification_policy": "ask_if_ambiguous",   // drives F9 / D6-01 scoring
    "reference_style": "issue"                    // issue | ticket | request | ambiguous
  },

  "setup": {
    "image": "ghcr.io/example/base@sha256:...",   // pinned image digest
    "setup_script": "setup.sh",                    // deterministic; no network
    "network": "disabled",                         // "disabled" | "allowlist"
    "seed": 20261021,
    "pre_installed": ["python3.11", "pytest==8.3.4"]
  },

  "environment": {
    "lockfile": "requirements.lock",               // hashed into the fixture fingerprint
    "lockfile_digest": "sha256:...",
    "cpu": 2, "memory_mb": 4096, "timeout_s": 1800,
    "tool_budget": 60,                             // max tool calls
    "wall_clock_cap_s": 1800
  },

  "oracle": {
    "kind": "hidden_test",           // hidden_test | static_check | state_check | gold_map | rubric | harness_contract
    "verifier_version": "v3",
    "tests": ["tests/test_pagination.py::test_cursor_first_item"],
    "oracle_files_hash": "sha256:...",  // these files are READ-ONLY to the agent
    "pre_state": { "suite_passes": 34, "suite_fails": 0 },
    "post_conditions": [
      {"kind": "test_must_pass", "test": "tests/test_pagination.py::test_cursor_first_item"},
      {"kind": "test_must_not_fail", "test": "tests/test_pagination.py::test_existing_behaviour"},
      {"kind": "file_must_be_unchanged", "path": "tests/test_pagination.py", "sha256": "..."},
      {"kind": "diff_line_budget", "max_changed_lines": 40}
    ]
  },

  "contamination": {
    "status": "unknown",             // clean | unknown | suspected | confirmed
    "repo_age_cutoff_ok": true,
    "fork_not_in_index": true,
    "in_public_training_set": "unverified",
    "notes": "Repository created after the reference model's stated cutoff; no public index located."
  },

  "provenance": {
    "authored_by": "team-member-id",
    "reviewed_by": ["reviewer-1", "reviewer-2"],
    "legal_basis": "synthesised",    // or "MIT upstream" / "CC-BY human-authored"
    "created": "2026-09-14",
    "version": 1
  }
}
```

**PLAN:** three properties of this schema are non-negotiable.

- `task_id` is **stable and never reused**. A task retired from the suite stays retired; its ID is never recycled, because recycled IDs silently corrupt every longitudinal comparison.
- The manifest is **hashed** and the hash is part of the fixture fingerprint (§6.5). Changing a prompt by one character invalidates comparability with every prior run against that task.
- `oracle_files_hash` exists because a task where the agent can edit the test is not a test. The benchmark verifies oracle-file hashes after every run and treats a mismatch as a **hard failure** of that task, never as a pass.

### 4.4 Reproducible environment

**PLAN:** the fixture is reproducible if a second machine, given the same manifest, produces the same starting state.

- **Base image** pinned by **digest**, never by tag. A tag is a mutable name; a digest is a content hash.
- **Dependency lockfile** pinned by hash, and the lockfile is part of the fixture fingerprint. The reference evidence shows the length of this problem space in a different domain: the reference harness's own cost ledger records `hasUnknownModelCost` as a first-class flag (**OBSERVED-FILE**, §5.5) — an acknowledged unknown is worth recording, and a lockfile is the same idea applied to the environment.
- **Setup scripts are deterministic and network-free.** No `pip install` at setup time from a live index; dependencies are baked in or installed from a vendored wheelhouse. A benchmark whose setup can fail non-deterministically measures the network.
- **Seeds are recorded**, and where a dependency exposes a seed it is set explicitly. A recorded seed that nothing consumes is worse than no seed: it creates false reproducibility. The plan therefore requires the manifest to name *which* components the seed governs.
- **Baseline verification.** Before any agent run, the harness runs the oracle suite in the fixture and asserts the recorded `pre_state`. A task whose baseline does not reproduce is **quarantined**, not run. This directly prevents failure mode 2 in §3.5: a suite that is already red masks new breakage.
- **Timeouts** are per-task and pinned, and the timeout policy is part of the fixture.

### 4.5 Legal sourcing

Three legal routes. Each has a different oracle story, and the plan is explicit about which route a task came from because the route determines what contamination risk is acceptable.

**Route A — Synthesised fixtures.**
The team writes a small repository from scratch, or generates one from a template, with a deliberately planted defect or a specified missing feature. The oracle is written alongside.

- **Legal basis:** entirely the team's own work; no third-party licence question.
- **Contamination advantage:** a repository that has never existed publicly cannot be in any pretraining corpus. This is the only route that gives a **clean** contamination status rather than a probabilistic one.
- **Cost:** the work is real, and the realism ceiling is set by the team's imagination. Synthesised repos tend to be smaller and cleaner than production code.
- **Mitigation:** generate enough of them, in several languages and styles, so the suite is not a single house style. Track the language/style distribution as a suite property.

**Route B — Permissively licensed upstream repositories, with commit history as the oracle.**
Take a repository under a permissive licence (MIT, BSD-2/3, Apache-2.0), check out the commit *before* a bug fix, and use the fix's own test as the oracle.

- **Legal basis:** the licence permits use of the code. **The task is not published as a redistribution of the upstream fix** — the fixture is the pre-fix tree, and the oracle test is applied at evaluation time, not shipped in the task image. Where the licence permits redistribution (MIT/BSD/Apache all do, with attribution and notice), the notice and licence text are included in the fixture.
- **This route has a precedent in the public literature:** SWE-bench's construction takes real GitHub issues and their linked pull requests as the task and oracle, and SWE-bench Verified is a human-validated subset of that construction (**EXTERNAL** — see §17 for URLs and exact figures as stated by their authors).
- **Contamination advantage:** the *pre-fix* tree and the *issue text* are both public, and a widely-used benchmark means the *fix* is very likely in pretraining data. Route B therefore carries a **high** contamination risk and is only acceptable for tasks where the answer cannot be recovered by retrieval.
- **Mitigation:** tasks whose issue text is a verbatim public issue are re-worded so the prompt no longer matches an indexed string, while keeping the *substance* — but be aware this is a mitigation, not a fix, and record the original and the rewording in the manifest.
- **Additional mitigation:** prefer commits from repositories and dates that are **not** in common training sets, and prefer *forks* that are not indexed (see §4.6).

**Route C — Human-authored tasks.**
An engineer writes a task against a real internal problem, in a real repository, with a human-written oracle.

- **Legal basis:** employment agreement / contractor assignment must cover the contribution. **PLAN:** before any Route C task enters the suite, the applicable agreement is confirmed to permit its use for internal evaluation. This is a hard gate, not a formality.
- **Contamination advantage:** real internal problems are the least likely to be in any pretraining corpus.
- **Contamination risk:** the task may be described in an internal document that *is* in the corpus. Mark `suspected` if a matching public artefact cannot be ruled out.
- **Advantage:** these are the tasks whose failure modes are most representative of real work.
- **Cost:** highest authoring cost; the smallest count.

**PLAN:** the suite's target mix is **Route A at least 50%**, Route B at most 35%, Route C at most 20%, with a standing rule that any single repository contributes at most **5%** of the suite, so that no one repository's properties (style, size, language, licence, contamination exposure) dominate the measurement.

### 4.6 Contamination control — and its honest limits

**PLAN:** contamination control is a *risk-management* procedure, not a detection procedure. No known method reliably establishes that a specific task's answer was absent from a specific model's pretraining corpus. Anyone claiming otherwise should be asked which corpus they had access to.

**Controls, in order of strength:**

1. **Age cutoff.** The strongest control. If the repository, issue, or commit postdates the model's stated training cutoff by a comfortable margin, contamination is unlikely by construction. Record the cutoff date per model in the comparison record (§9). Do not assume a cutoff; look it up, and record that you did.
2. **Not-in-index check.** For Route B, check whether the repository or the specific fix commit appears in the public corpora and code indexes that are documented as being crawled for training. Record what you searched and what you found, including "not found" results. A negative search is weak evidence — the crawl schedule, the URL form, and the fork topology are all unknown — so it downgrades `suspected` to `unknown`, never to `clean`.
3. **Fork selection.** Prefer a **fork** of a popular repository that is not itself indexed, or a private mirror, or a repository under an organisation that does not publish a crawl policy. The fix commit then exists in a namespace that a crawler's link-following may never have reached.
4. **Substance-preserving rewording.** Rewrite the issue text so that it is not a string-matchable copy of a public issue. The task's *substance* (the defect, the required behaviour) is unchanged; only the surface form is. Recorded in the manifest as `prompt_original_sha256` and `prompt_rewritten_sha256`. **Honest limit:** a capable model may still reconstruct the upstream issue from the repository and the defect, because the defect *is* the fingerprint. Rewording raises the bar; it does not clear it.
5. **Post-cutoff construction.** Generate Route A tasks, and harvest Route B fixes from commits made after the cutoff of the model under test. This is the only control that is not probabilistic.
6. **Held-out-by-construction.** A slice of the suite is **never shown to any human on the team as a practice set** and is never used for prompt tuning (§5). Contamination by exposure is the most likely form of contamination in a small team, and it is entirely preventable by process.
7. **Negative control.** Maintain a small set of **known-suspect** tasks — ones whose fix is verifiably in a widely-crawled public benchmark. Running them and reporting their scores separately gives a *live contamination signal*: if a configuration's score on the suspect set is anomalously high relative to the matched clean set, that is evidence of retrieval rather than reasoning. This is a diagnostic, not a verdict, and it must be reported as such.

**What contamination control cannot do — stated plainly:**

- It cannot prove that a task was not in a corpus. It can only raise or lower a probability.
- It cannot control **supervised fine-tuning** contamination. If the team's own model is later trained on data derived from the benchmark, the benchmark is no longer a benchmark. The suite's lockstep rule (§5.4) covers this, and it is the most common way a self-built benchmark destroys itself.
- It cannot control **harness-level leakage**: the tool descriptions, the error messages, and the system prompt are themselves a corpus the model may have been trained on. If the harness's wording matches a public product's wording, the model may be doing prompt recall rather than task solving. This is why §6.2 fingerprints the *tool descriptions* as text, not just the tool names.
- It cannot protect against a team that tunes against the test set. That is a discipline failure, addressed in §5 and §15, not a data problem.

**PLAN:** every task carries a `contamination.status` of `clean` (post-cutoff by construction, Route A or C), `unknown` (checked, not found, weak), or `suspected` (public artefact known or likely). The evaluation report **always** breaks out results by contamination status. A headline number that mixes `clean` and `suspected` tasks is not a headline number.

### 4.7 Difficulty banding

**PLAN:** bands are assigned by a two-person rubric, and the rubric is written down *before* the bands are assigned.

| Band | Definition | Assignment rule |
| :- | :- | :- |
| 1 | Trivial: single edit, the location is named in the prompt | Only F1/F4/F6 |
| 2 | Local: one file, one function, the location must be found | F1, F4, F5, F6, F8 |
| 3 | Moderate: multiple files, or a non-obvious location, or a non-trivial failure mode | F2, F3, F5, F6, F9 |
| 4 | Hard: cross-cutting, conventions must be inferred, or the failure is indirect | F2, F3, F7, F9 |
| 5 | Very hard: long horizon, multiple interacting constraints, compaction likely | F7 |

Both assigners must agree; disagreements go to a third. **PLAN:** the band distribution of the suite is reported, and after a champion baseline is measured, bands are **re-calibrated** — a band whose tasks are all solved by the champion is too easy, and a band whose tasks are all failed is either too hard or has a broken oracle. Bands are a property of the suite, calibrated against measurement, never asserted in advance.

### 4.8 Task-suite size target

**PLAN — a staged target, because the suite must grow with the capability being measured.**

| Stage | Dev | TEST-A | TEST-B (final held-out) | Reserve (quarantined) | Total | Rationale |
| :- | :- | :- | :- | :- | :- | :- |
| **S0 — pre-model (M1)** | 40 | 15 | 20 | 0 | 75 | Enough to shake out harness bugs and build the tooling; far too small for model comparison, and the plan says so. |
| **S1 — first trainable model (M2)** | 120 | 40 | 60 | 0 | 220 | Enough to train on and to measure a first checkpoint with a usable confidence interval. |
| **S2 — reliable agent (M3)** | 250 | 80 | 150 | 60 | 540 | Enough for the regression gate and for paired comparisons with reasonable power. |
| **S3 — M4 onward** | 400 | 120 | 250 | 150 | 920 | Enough for multiple-comparison correction across many dimensions and tasks. |

**Why these numbers.** The binding constraint is **statistical power**, and it is derived in §10.1: detecting a 5-percentage-point difference with paired McNemar at 80% power needs on the order of 150–400 paired tasks depending on the discordance rate. S1 and S2 are sized to reach that; S0 is explicitly *not* and is used only for tooling. The **reserve** column exists because of §5.4: training on the suite destroys the held-out set, and the reserve is the replacement held-out set, sourced separately and quarantined from the start.

**Composition targets at every stage:**

- No single repository above **5%** of the suite.
- No single language above **40%**.
- No single family above **35%** (so the headline number is not a bug-fixing number wearing a costume).
- At least **30%** of tasks Route A (synthesised) once S1 is reached, rising to 50% at S3.
- At least **10%** of tasks in F7 and F9 combined at S2, because the long-horizon and judgement dimensions are otherwise unmeasured.
- Difficulty bands 1 and 5 each capped at **20%** of the suite, so the mean difficulty stays meaningful.

---

## 5. Held-out test design

### 5.1 The four levels of "held out"

"Held out" is a word that hides four different guarantees. The plan requires all four to be named explicitly, because a suite can hold out at one level and leak at another.

| Level | What is held out | What it protects against | How it is enforced |
| :- | :- | :- | :- |
| **L-task** | A specific task instance is not in the tuning set | Tuning to a specific problem | Tasks are partitioned by ID; the test partition is never used for prompt or harness iteration |
| **L-repo** | The entire *repository* is unseen | Learning a repo's conventions, then being tested on them | **The strongest and most important control.** Split by repository, not by task — a repo appearing in both dev and test means the test set measures familiarity |
| **L-file** | A specific test file, a specific source file, or a specific fixture is unseen | Memorising an oracle or a helper | Oracle files are excluded from the tuning set; separate file-level holdout for source files used by dev tasks |
| **L-checkpoint** | A specific model checkpoint is unseen | Overfitting weights to a specific evaluation set | Training data is filtered against the *entire* suite, dev and test, not just test |

### 5.2 Split protocol

**PLAN:** the split unit is the **repository**, and the split is:

- **DEV** (tuning set) — visible to the team. Used for prompt engineering, harness debugging, prompt/agent iteration, and regression-catching during development.
- **TEST-A** (validation set) — visible, but *rate-limited* and *logged*. Used for periodic checks that development is not overfitting. Access is recorded; a task in TEST-A that is accessed more than a set number of times is automatically promoted to DEV, and the promotion is logged.
- **TEST-B** (final held-out) — **not visible** until a release candidate is frozen. Never used for iteration. Opened at most once per release candidate, and opening it is an event that is logged and announced.
- **RESERVE** — quarantined from the start (§5.4). Never opened except to replace a compromised held-out set.

**Why TEST-A exists at all.** A single held-out set that is opened once gives a single number with a single draw, and a single draw is a weak instrument (see §10.4). TEST-A provides a *drift signal* during development, and it is worthless as a held-out set if it is used freely — which is why its accesses are logged and its tasks are promotable.

**Why the repository is the split unit.** If a repository appears in both DEV and TEST, the agent has been tuned on the repository's conventions, its test idioms, its directory layout, and possibly its fixture data. The measured difference between DEV and TEST scores then is a **contamination measurement**, not a generalisation measurement — and the size of that gap is genuinely informative (a large DEV–TEST gap is a useful diagnostic even though it is not a score).

**PLAN:** the split is by repository, and the report states, per release, the DEV score, the TEST-A score, and the **DEV–TEST-A gap**. A widening gap is a regression signal even when both scores rise.

### 5.3 The leakage-prevention protocol

**PLAN — six rules, each with a mechanism:**

1. **No test task may be inspected during development.** Enforcement: the test partition's fixtures and oracles live in a store the development environment does not have access to. A runner process, not a human, is the only component that can read them, and it writes only a result record.
2. **Every access is logged.** The runner records `{task_id, run_id, who_or_what, timestamp, configuration_id}` for every task access, including a human reading a task manifest.
3. **No prompt or agent change may be motivated by a specific test task.** Enforcement: every change to the prompt, the tool descriptions, or the agent configuration must carry a one-line rationale naming the **dev** observation that motivated it. A change whose rationale cites a test task is rejected at review. This is a review-time discipline and it is the single most effective control in practice.
4. **Test partitions are never rendered to the model during development.** A model's context must not contain a test task's text at any point except during the evaluation run itself.
5. **Held-out sets are not used for regression triage.** When a release candidate fails a test task, the failure is recorded and *deferred*; it is not debugged against the test task. Debugging uses DEV.
6. **The training-data filter covers the whole suite.** For M2 onward, the training-data pipeline is filtered against **every** task in the suite, dev and test, including prompt text, oracle files, and fixture snapshots. Training on a held-out task is a catastrophic and easily-detected failure — and the check is cheap: hash every suite asset, hash every training example, and assert disjointness.

**PLAN — a leakage audit runs before every release.** The audit reports: number of distinct tasks accessed per partition; the count of configuration changes whose rationale cites a test task (target: zero); training-data disjointness (target: exact); and the number of tasks promoted from TEST-A to DEV (target: bounded and reviewed).

### 5.4 The self-benchmarking trap (for M2 onward)

**PLAN:** from the moment a model exists, the following rule applies without exception:

> **No artefact derived from the benchmark suite — tasks, fixtures, oracles, prompts, verifier code, or the *aggregated* content of test transcripts — may enter the training data of the model under evaluation.**

The aggregated case is the one people miss. Training on "here is a summary of how the agent solved a set of benchmark tasks" leaks the answers just as effectively as training on the tasks themselves, and it is much easier to do accidentally, because it looks like "RL from experience".

Consequence, stated up front: **once a model is trained on anything derived from the suite, that suite is a dev set forever, and the team needs a new held-out set.** Building a second, separately-sourced held-out set is a M2 exit criterion, not an optional extra. The plan therefore requires a **reserve corpus** — a separately-sourced set of tasks, quarantined from the start, that can be opened for exactly one evaluation per model generation.

### 5.5 What "held out" does *not* buy

- It does not make the test set a random sample of the world's software engineering problems. It is a sample of *this suite*, chosen by this team.
- It does not protect against the model having seen the *underlying repository* in pretraining. Contamination control (§4.6) is a separate mechanism, and the two are independent.
- It does not make a single held-out number reliable. That is a statistical question, and §10 handles it: sample size, paired tests, and effect sizes.
- It does not survive the team growing. A held-out set in a 3-person team is a held-out set; in a 30-person team it is a shared document. Access logging and repository-level storage separation are what make it survive.

---

## 6. Reproducible fixtures

This section is the operational heart of the plan. §1.1 stated the principle — *an agent's result is a function of prompt + tools + model + harness* — and this section is the mechanism that makes a comparison a comparison.

### 6.1 The pinning set

Every evaluation run is identified by a **fingerprint**: the SHA-256 over a canonical JSON serialisation of the following fields, in this order. Any change to any field produces a different fingerprint, and a result carrying a different fingerprint is not comparable to one carrying the original.

| # | Pinned item | How it is captured | Why it matters |
| :- | :- | :- | :- |
| 1 | **Model id** | Full provider-qualified id, e.g. `anthropic/claude-opus-5.5` | The obvious one. Note the reference product's own model-resolution chain is five levels deep (`--model` → `modelOverrides` → `ANTHROPIC_MODEL` → settings `model` → default) (**OBSERVED-DOC**, §5.6) — so the *effective* model must be recorded, not the requested one. |
| 2 | **Model version / checkpoint date** | Provider's snapshot identifier, or `unknown` if the provider offers none | A provider alias can silently change under the same id. If the provider does not expose a snapshot, the comparison record must say so and treat that as a known uncontrolled variable. |
| 3 | **Provider and endpoint** | Provider name + base URL host | A gateway can route the same id to different weights. The reference evidence shows `ANTHROPIC_BASE_URL` acting as a *feature gate*, not merely an endpoint (**OBSERVED-DOC**, F12.3). |
| 4 | **Tool schemas** | Canonical JSON of every tool's JSON Schema, sorted | The schema is part of the model's input. A changed schema is a different experiment. |
| 5 | **Tool descriptions** | **SHA-256 of the concatenated description text, per tool** | **The prompt.** This is the field teams forget. A tool description is a paragraph of English that changes the model's behaviour. The reference evidence documents the tool `description` field as *model-authored* and adjacent to the trust path (**OBSERVED-CLI**, L12) — that is, it is *prompt*, and it must be fingerprinted as prompt. |
| 6 | **System prompt** | Exact text + SHA-256 | The largest single lever on behaviour, and the one most likely to be edited casually. |
| 7 | **Permission mode** | Mode name + the full effective rule set (deny/ask/allow) + Tier-2 status | The reference's six modes have genuinely different semantics (**OBSERVED-CLI**, §5.2), and rules are evaluated deny→ask→allow, first match, **with no specificity sorting** (**OBSERVED-DOC**, §5.3). Two runs with different effective rules are different experiments. |
| 8 | **Environment image** | Image digest | §4.4 |
| 9 | **Dependency lockfile** | Lockfile hash + the resolved package manifest | §4.4 |
| 10 | **Seed** | Seed value **and** the list of components it governs | §4.4 |
| 11 | **Tool-call budget** | Max tool calls + max turns + max wall-clock | Budget is part of the task definition (§3.5, failure mode 2) |
| 12 | **Cost budget** | Max spend, if any | Same reason; the reference exposes a distinct `error_max_budget_usd` terminal subtype (**OBSERVED-CLI**, FX1.3) |
| 13 | **Decoding parameters** | temperature, top-p, effort level, thinking configuration, max output tokens | The reference has **five** effort levels — `low, medium, high, xhigh, max` — settable per session and per subagent (**OBSERVED-DOC**, F7.2, confirmed #130), and treats an invalid `--effort` as a warning while an invalid `--autocompact` is a hard error (L15) — i.e. decoding config is treated as a first-class experimental variable, and so must it be here. |
| 14 | **Harness commit** | Git SHA of the harness + the harness version string | The harness is one of the four things that determine the score. |
| 15 | **Task-set version** | Hash of the task manifest set (dev and test partitions) | Different task set = different measurement. |
| 16 | **Verifier version** | Oracle/verifier implementation version | The oracle changed → the score changed → not comparable. |
| 17 | **Thinking budget** | Maximum thinking tokens, if the provider exposes it | Sub-item of 13, called out because thinking budget changes cost *and* accuracy. |

**PLAN:** the fingerprint is computed **before** the run and stored **with** the result. A run whose fingerprint cannot be reconstructed is not admitted to a comparison — it is archived as an unversioned observation.

### 6.2 The tool fingerprint

Beyond the whole-run fingerprint, the plan requires a **per-tool** fingerprint so that a harness change that touches one tool's description is visible as such:

```jsonc
{
  "harness_commit": "abc123…",
  "harness_version": "0.4.2",
  "tools": [
    {"name": "Read",   "schema_sha256": "…", "description_sha256": "…", "read_only": true},
    {"name": "Edit",   "schema_sha256": "…", "description_sha256": "…", "read_only": false},
    {"name": "Bash",   "schema_sha256": "…", "description_sha256": "…", "read_only": false}
  ],
  "system_prompt_sha256": "…",
  "permission_mode": "default",
  "permission_rules_sha256": "…"
}
```

**PLAN — the harness-version disclosure rule.** Any report that states a score **must** state the harness version and the tool fingerprint beside it. The reference product's own discipline is a model to copy: it advertises `claude_code_version: "2.1.306"` and a `capabilities[]` array of protocol feature flags in the `system/init` event, so a consumer can tell exactly what engine produced a stream (**OBSERVED-CLI**). A score without its engine is not a score.

### 6.3 The consequence, stated as a rule

> **A "model comparison" that does not control prompt, tools, harness, and inference settings is not a comparison. It is an observation of a system, presented as a property of a model.**

§9 is the procedure that discharges this rule in practice. The rule has one more consequence that teams find uncomfortable: **if a harness change moves the score, that is a legitimate and expected result.** The harness is part of the system under test. Reporting "model X is better than model Y" when the difference was produced by a harness change is the single most common misattribution in agentic evaluation, and §9's reporting template is designed to make it impossible to commit unnoticed.

### 6.4 What is deliberately *not* pinned

**PLAN:** the plan pins aggressively, but pinning everything makes a comparison impossible to run and easy to abandon. These are explicitly excluded from the fingerprint, with the reason:

- **Wall-clock scheduling jitter** — pinned by the task set, not the run; timing is measured, not controlled (§3.5 failure mode 5).
- **Provider-side load and network conditions** — uncontrollable; handled by pairing and by reporting medians, not by pinning.
- **The specific machine** — the environment *image* is pinned; the host is not, except that the environment spec records CPU/memory.
- **Transcript formatting and log verbosity** — an observability concern, not an experimental variable, *provided* it cannot influence the model. (It can: the model's own outputs are context. So the rule is: log verbosity that reaches the model's context *is* pinned, and log verbosity that does not is not. This distinction is drawn explicitly so that nobody "harmlessly" increases what the model sees and calls it observability.)

### 6.5 The fixture fingerprint

Combining everything, one **fixture fingerprint** per (task, configuration) pair:

```
fixture_fingerprint = SHA256(
    task_manifest_hash ‖
    environment_image_digest ‖
    lockfile_hash ‖
    harness_commit ‖
    tool_fingerprint ‖
    system_prompt_hash ‖
    permission_rules_hash ‖
    model_id ‖ model_snapshot ‖ decoding_params ‖
    seed ‖ tool_budget ‖ cost_budget ‖
    verifier_version
)
```

**PLAN:** this value is the primary key of a result record. Two results with the same fixture fingerprint are directly comparable. Two results with different fixture fingerprints are comparable only through a paired analysis that explicitly models the changed variable (§8.4).

### 6.6 Reproducing a run

**PLAN:** a run is reproducible if, given the fixture fingerprint and the result record, a second machine can produce a comparable result. That requires the following to be archived for every run:

- The complete transcript (JSONL), including the exact tool schemas and descriptions sent.
- The complete request/response payloads where the provider permits, or the token counts where it does not.
- The environment image digest and the resolved dependency manifest.
- The harness commit and the tool fingerprint.
- The exact seed and the components it governs.
- The provider-reported usage and cost, with `costBasis`.

**PLAN:** a run whose transcript cannot be archived is not run. This is enforced at the runner level, and the reason is concrete: the reference evidence shows a *partially-delivered response* is never re-sent (**OBSERVED-DOC**, F6.8) — meaning a run can end with committed tool effects and no complete record of intent. A benchmark that loses the transcript loses the ability to distinguish "the agent did the wrong thing" from "the harness mis-recorded what the agent did," and that distinction is exactly what a benchmark exists to make.

---

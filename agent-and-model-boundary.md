# Agent and Model Boundary — "Keel"

**Document status:** normative planning deliverable, PART 6. No implementation exists yet; this document *is* the contract for where capability comes from.
**Companion documents:** `architecture.md` (the layer stack and ADRs), `interface-spec.md` (the fifteen published interfaces), `security-plan.md` (the two-tier safety model), `feature-checklist.md` (the fifteen subsystems), `benchmark-and-evaluation-plan.md` (metric attribution and the reference-comparison protocol), `prompt-pattern-analysis.md` (principles X1–X18), `compute-feasibility.md` (the rung ladder R0–R6), `licensing-and-provenance-review.md` (the §D.4 constraint).
**Product codename:** "Keel" (working codename, per `implementation-plan.md` and `security-plan.md`). The name is provisional and is not a claim of anything.

---

## 0. How to read this document

### 0.1 The claim-provenance key

This project has one overriding rule: **never state a fact you cannot source.** Every quantitative or behavioural claim in this document carries one of six tags.

| Tag | Meaning | Obligation |
| :- | :- | :- |
| **[KNOWN FACT]** | Taken from a citable public source, with URL + observation date inline | The source is named in the same sentence. |
| **[ESTIMATE]** | This project's own derivation | The arithmetic is shown. |
| **[SPECULATIVE]** | A target or an aspiration | Never presented as a forecast. |
| **[OBSERVED]** | Directly measured or verified in this project's own evidence base | The file and section are cited. |
| **[INFERRED]** | A conclusion drawn from observed facts | The inference is stated, not implied. |
| **[UNKNOWN]** | Not determinable from the material examined | What would settle it is named where relevant. |

Where no public figure exists, this document says **"no public figure found"** rather than inventing one.

### 0.2 The three claim classes used throughout

A claim in this document is about exactly one of three things, and the document never lets them blur:

1. **The model** — a set of weights and a decoding process. Layers L0–L2 in `architecture.md` §2.1.
2. **The harness** — the software around the model. Layers L3–L9 plus the cross-cutting X1–X2 in `architecture.md` §2.1.
3. **The pair** — the behaviour of a specific model driven by a specific harness on a specific task set.

**An agent's result is a function of prompt + tools + model + harness.** This sentence is inherited from `benchmark-and-evaluation-plan.md` §1.1, where it is the load-bearing premise of the whole evaluation plan. It is the premise of this document too. A document that measured the pair and reported it as the model would be a different document with the same numbers and a false title.

### 0.3 How to use this as a design-review checklist

Every numbered requirement in this document carries a stable identifier of the form `AMB-NNN`. A reviewer walks the identifier list and asks one question per item: **is this true of the code as written?** The identifiers are grouped by section, so a review of one boundary can be run in isolation:

| Prefix | Section | Reviewed by |
| :- | :- | :- |
| `AMB-0xx` | §1 Disclosure rule and required wording | Product + legal review |
| `AMB-1xx` | §2 Layered decomposition and swap independence | Architecture review |
| `AMB-2xx` | §3 Provider adapter contract | Architecture + implementation review |
| `AMB-3xx` | §4 Transition plan and stage promotion | Programme review (product owner) |
| `AMB-4xx` | §5 Harness contribution | Architecture + implementation review |
| `AMB-5xx` | §6 Model contribution | Model-programme review |
| `AMB-6xx` | §7 Context boundary | Implementation review |
| `AMB-7xx` | §8 Tool boundary and skill security | Security review |
| `AMB-8xx` | §9 Failure boundary and the fix decision rule | Architecture review |
| `AMB-9xx` | §10 Evaluation boundary and metric attribution | Evaluation review |
| `AMB-10x` | §11 Interface contracts | Implementation review |
| `AMB-11x` | §12 Disclosure register | Product + legal review |
| `AMB-12x` | §13 Open questions | Programme review (product owner) |

---

## 1. Why this document exists

### 1.1 The single hardest problem in this project

Every other problem in this project is an engineering problem with a checkable answer. This one is not.

A coding agent is a piece of software that reads a repository, decides what to do, calls tools, and edits files. The *decisions* — the plan, the choice of tool, the recovery from a failed command, the judgement that an error message means "re-read the file" rather than "try a different path" — are made by a language model. Nothing else in the stack makes them.

The consequence is that a product built this way **looks like it has its own intelligence** while, in the first instance, **borrowing it**. The harness is ours: the turn loop, the permission engine, the tool registry, the compaction policy, the transcript format, the sandbox, the subagent supervisor, the test suite. The competence is not. A user looking at a transcript sees the harness's structure and the model's judgements fused into one indistinguishable stream of tool calls and prose, and reasonably concludes that the product is smart. It is not; it is well-built, and it is driving something else's mind.

**This is the hardest problem because every ordinary incentive pushes toward the false reading.** A product that says "our agent outperforms competitor X" is more sellable than one that says "our harness driving model Y scores 61% on our task set; model Y was made by someone else." A demo that omits the provider is more compelling than one that names it. A benchmark table with a single model column is prettier than one with four pinned columns. The document exists to make the *honest* version the path of least resistance, by specifying in advance the exact wording required in every place the product could mislead — before there is a number worth misleading anyone with.

**The specific hazard this project is exposed to.** The evidence base contains an extensive black-box investigation of a commercial coding agent (`agent-evidence.md`, 358 KB) and a large captured prompt collection (`prompt-pattern-analysis.md`, 142 KB). A product built in that shadow is at elevated risk of two opposite failures, and the second is more likely to be unintentional:

- **Over-claiming by association.** Writing a document that studies a frontier agent's behaviour and then shipping a product that is widely *called* "an open-source Claude Code" will have every capability of that product attributed to it, whether or not the attribution is stated.
- **Over-claiming by adjacency.** The product's own harness, its own tool descriptions, its own prompt engineering, and its own context management are genuinely ours and genuinely competent. It is easy — and the error is subtle because the claim feels earned — to let the harness's engineering quality become evidence of model capability. **It is not.** A well-built harness around a mediocre model produces a mediocre agent with excellent manners. A badly-built harness around a frontier model produces a frontier model with a bad leash. Neither result is a statement about the model alone, and the second number is the one that gets quoted.

### 1.2 The disclosure rule

> **THE EXISTENCE OF A PROVIDER ADAPTER MUST NEVER BE REPRESENTED AS INDEPENDENT MODEL INTELLIGENCE.**

This is `AMB-001`. It is not a style preference and it is not a marketing constraint. It is the rule that the rest of this document operationalises.

It has three parts, and each part is independently enforceable:

1. **The word "adapter" is a technical term, not a euphemism.** An adapter is a translation layer between a provider's wire format and ours (`interface-spec.md` §12.4 calls it "a pure translation layer"). It carries endpoints, authentication, transport, retries, streaming-fragment translation, token accounting, and error mapping. It carries **no judgement**. The word must never be used to soften the fact that the intelligence is someone else's.
2. **The attribution must travel with the number.** A score with a provider model in it carries a provider attribution with it — in the table, in the figure caption, in the prose sentence, and in the machine-readable record. This is the concrete form of `benchmark-and-evaluation-plan.md` §9.4's requirement that the harness variant travel with the score.
3. **The disclosure must be at the point of use, not only in the documentation.** A user who reads only the terminal banner, only the model picker, or only the model card must still be able to tell what is being driven. A disclosure buried in a README is a disclosure that has failed the user who needed it.

### 1.3 The exact wording

The following wording is **required**. It is written to be used verbatim, and it is specified here so that no surface invents its own phrasing later.

#### 1.3.1 Required wording — user-facing surfaces

| Surface | Required wording | Identifier |
| :- | :- | :- |
| Model picker entry for a provider-hosted model | `<model-id> (via <provider>)` — e.g. `Sonnet 5.5 (via Anthropic)` | `AMB-002` |
| Session start banner / `init` descriptor, when a provider-hosted model is selected | `Model: <model-id> (via <provider>)` — the provider string is **not** optional and is **not** hidden behind a verbose mode | `AMB-003` |
| Session start banner, when the project's own model is selected | `Model: <model-id> (Keel's own model, served locally)` | `AMB-004` |
| Documentation, model section | "Keel is a harness. Its agent behaviour comes from the model it is driving. On a provider-hosted model, the intelligence is the provider's. See *What this product is not*." | `AMB-005` |
| Documentation, model section, for the project's own model | "Keel's own model is trained by this project. Until it reaches a given stage (§4), the default model is a provider-hosted one and Keel is a client of that provider." | `AMB-006` |
| Marketing / landing page | Any claim about agent quality **must** name the model, or state "model-dependent" in the same claim. A claim about the product that does not depend on model quality (tooling, safety, transparency, determinism, local execution) **may** stand alone. | `AMB-007` |
| Benchmark table header | Every result column carries `<model-id>` and `<provider>` and, where the harness differs between arms, the harness variant (A/B/C per `benchmark-and-evaluation-plan.md` §9.4). | `AMB-008` |
| Comparison against any third-party product | "Product comparison, not model comparison" must appear in the results section, with the harness variant attached, when the two arms ran under different harnesses. | `AMB-009` |
| Any headline score | The headline is either a **harness** metric (attributed to the harness) or a **paired** metric (attributed to the model+harness pair, with both pinned). A headline may not be attributed to a model alone. | `AMB-010` |

#### 1.3.2 Required wording — logs and machine-readable records

| Surface | Required content | Identifier |
| :- | :- | :- |
| `system/init` event | `model` (the resolved model id) **and** `model_provider` (the serving provider) **and** `model_ownership` (an enum: `provider-hosted` \| `keel-own` \| `third-party-local`) **and** `model_base` (the base model id when the served model is a fine-tune or derivative of a named base) | `AMB-011` |
| Assistant event | `message.provider` (already specified in `interface-spec.md` §15.4) is retained. `message.model` is retained. Neither is replaced by a friendlier name. | `AMB-012` |
| Terminal envelope | `modelUsage[*].provider` and `modelUsage[*].canonicalModel` (already specified in `interface-spec.md` §17.3) are retained, and `modelUsage[*].costBasis` retains its `unknown` value when the adapter has no price table. | `AMB-013` |
| Diagnostic stream | A diagnostic emitted when a provider-hosted model is used in a configuration the operator asked to be offline MUST name the provider and the fact that the traffic leaves the machine. | `AMB-014` |
| Cost ledger | `costBasis` is `unknown` for any model with no price table, and `costUSD` is `0`. A `0` is never rendered as "free" in a human-facing view. | `AMB-015` |
| Transcript | The transcript records the provider for the model that served each assistant turn. A transcript is an audit artefact and must survive being read by someone who did not run the session. | `AMB-016` |
| Per-request log line | Model id and provider, at the same verbosity as the request's own duration. | `AMB-017` |

#### 1.3.3 The exact wording that is forbidden

These are forbidden **in the product, in the documentation, in marketing, in issue titles, in commit messages, in slides, and in conversations with investors or press**. The list is deliberately literal, because a prohibition phrased as a principle is defeated by a synonym.

| Forbidden | Why | Identifier |
| :- | :- | :- |
| "Our AI" / "our intelligence" / "our model" — when referring to a provider-hosted model in context | Ambiguous by construction. "Our model" is the single most natural way to be both truthful and false. | `AMB-020` |
| "Our agent" as the subject of a quality claim | The agent is the pair. A quality claim about "our agent" that does not name the model is a claim about a pair with one of its two halves unstated. | `AMB-021` |
| "Proprietary model" (in either direction) | A model served by a provider is a vendor's proprietary model, and ours is a non-proprietary one. Using the word for a provider's model implies the opposite of the truth. | `AMB-022` |
| "Open-source model" for a provider-hosted model | A hosted model is not open-source; the weights are not published. | `AMB-023` |
| "Powered by <provider>" used as the sole attribution, with no "the model is <provider>'s" | "Powered by" describes the plumbing, which invites the reader to attribute the intelligence to the product. | `AMB-024` |
| "Our model beats Claude" / "we outperform GPT" / any comparison of our model to a named third-party model without harness control | Forbidden by `benchmark-and-evaluation-plan.md` §9.9, and forbidden again here because the boundary is exactly where that error is easiest to make. | `AMB-025` |
| "Independent AI" / "independently intelligent" / "self-contained intelligence" | The product is a harness. The word "independent" is the load-bearing claim and it is false for a provider-hosted model. | `AMB-026` |
| "Fully autonomous" / "runs on its own" — with respect to a provider-hosted model | The model is remote; the run depends on a third party's availability, pricing, and terms. | `AMB-027` |
| "Private" / "offline" / "on-device" — for a run that uses a provider-hosted model | The prompt, the repository content, and the tool results leave the machine. This is a **privacy claim**, and it is the fastest way to a security incident. | `AMB-028` |
| "No API cost" / "free" — for a provider-hosted model | The cost is real; it is just not charged to a card. A self-hosted model is genuinely zero-marginal-cost. | `AMB-029` |
| Any banner, doc, or post implying the model weights are ours before §4's S3 stage is reached | The disclosure rule. | `AMB-030` |
| Publishing a score for a provider-hosted model without the provider string in the same table cell | A score that is detached from its model+provider+harness is unattributable. | `AMB-031` |

#### 1.3.4 Permitted wording

For completeness, and because a rule that only lists prohibitions tends to produce stilted copy:

- "Keel drives <model-id>." — a fact about the harness.
- "Keel's own model, <id>, built on <base-model>." — during S2/S3, where §4 requires the base model to be named.
- "The model is the provider's; the harness, the tools, the safety model and the permission decisions are ours." — the sentence this whole document exists to make easy to say.
- "This number is the pair. Here is the model, here is the harness, here is the task set." — the honest form of every result.
- "We do not yet have a model of our own. Here is exactly what that costs you and what it buys you." — the S0/S1 form.

#### 1.3.5 Why this is a hard rule rather than a style rule

**`AMB-032`** — The disclosure rule is enforced by mechanism, not by instruction, wherever a mechanism is available. This is principle X1 from `prompt-pattern-analysis.md` ("enforce by mechanism, not by instruction, wherever a mechanism is available"), applied to the disclosure rule itself.

A prompt saying "always disclose the provider" is a request, and a request can be ignored — by a model, and by a team under deadline pressure. The mechanisms available:

| Mechanism | What it enforces | Identifier |
| :- | :- | :- |
| The `init` event **requires** `model_provider` and `model_ownership` as fields, not as optional | A consumer cannot render a session header without the attribution being present. | `AMB-033` |
| The headless envelope **requires** `modelUsage[*].provider` and `.canonicalModel` | A machine-readable record of a run always carries the attribution. | `AMB-034` |
| The model picker **cannot** render an entry without a provider string | The UI has no way to display an unattributed model. | `AMB-035` |
| The terminal banner **cannot** print a bare model id | Same. | `AMB-036` |
| A lint rule fails the build if any surface renders a model id without a provider | The rule is checked by a machine, not by a reviewer remembering. | `AMB-037` |
| A benchmark report template **requires** the attribution fields; the generator refuses to emit a table missing them | A score cannot be published unattributed. | `AMB-038` |
| A test asserts that the `init` event, the envelope, the transcript, and the banner all contain the provider for a provider-hosted model | Four independent surfaces, one behaviour. | `AMB-039` |

**`AMB-040`** — Where a mechanism is genuinely unavailable (prose in a blog post, a verbal claim at a conference), the obligation falls back to the §1.3.1 wording table, and the fallback is recorded in the disclosure register (§12) with the specific surface named.

---

## 2. The layered decomposition

### 2.1 The ten layers

This section restates the layer stack from `architecture.md` §2.1 **for the specific purpose of establishing swap independence and attribution**. It does not replace `architecture.md`; the layer table there is the architectural authority. Where this document adds a column, it adds a column about *ownership* and *attribution*, which `architecture.md` does not cover.

The ten layers required here map one-to-one onto `architecture.md`'s L0–L9, with the two cross-cutting layers X1 (policy and safety) and X2 (telemetry) noted where they cut across.

| # | Layer | Owns | Must NOT own | Swappable independently? |
| :- | :- | :- | :- | :- |
| **1** | **Model architecture and weights** (`architecture.md` L0) | Tokenisation, attention, output distribution, reasoning-token generation, context-window capacity, the model's own competence at emitting well-formed tool calls. | The harness. The model does not know it is inside an agent; it sees tokens. | **Yes**, at the adapter boundary, but only to the extent an alternative model satisfies the same contract (§3). A swap changes the *capability* of the product, not its structure. |
| **2** | **Data preparation and training** (`architecture.md` L1) | Corpora, instruction mixtures, preference pairs, decontamination, evaluation-set construction, safety fine-tuning, and the provenance manifest for every artefact. | The harness's runtime; the tool protocol; the permission system. | **Yes** — a training pipeline is replaceable by a better one without touching any other layer. This is the layer where the project's own work becomes *independent model intelligence* rather than borrowed. |
| **3** | **Instruction tuning and evaluation** (`architecture.md` L2) | SFT/RL curricula, tool-use training mixes, held-out eval suites, regression gates, the decontamination regime. | The specific harness implementation — training targets *capabilities*, not our wire format. | **Yes**, with a caveat: an SFT curriculum tuned to a harness's tool-call idiom creates a coupling between layers 2 and 5. The coupling is deliberate and must be recorded (§4, stage S1 acceptance). |
| **4** | **Inference and model adapters** (`architecture.md` L3) | Endpoints, auth, transport, retries, streaming-fragment translation, token accounting, effort/reasoning controls, the model registry, the capability matrix, the error taxonomy mapping. | Permissions, tools, sessions, compaction, the UI, the transcript format. The adapter is a translation layer and nothing else (`interface-spec.md` §12.4). | **Yes** — this is the primary swap point, and the only layer designed to be swapped routinely. |
| **5** | **Agent orchestration and planning** (`architecture.md` L4) | The turn loop, the plan artifact, task decomposition, the subagent supervisor, budgets, turn caps, stop conditions. | How a tool executes; how a permission decision is reached; how bytes reach disk. | **Partly.** The loop can be reimplemented. But the *model's* ability to plan lives in layer 1/3 — this layer owns the *harness's* scaffolding around planning, not the planning competence itself. |
| **6** | **Tool execution and permission enforcement** (`architecture.md` L5) | The tool registry, the schema validator, the rule engine, the Tier-2 safety analyser, the shell front-ends, the result renderer, the output-persistence writer. | The provider; the transcript format; the subagent supervisor. The `execute` function **MUST NOT** perform a permission check — the gate is in the dispatcher (`interface-spec.md` §4.2). | **No** in the sense that matters: the permission engine is the product's core promise, and swapping it changes what the product *is*. It is not a modular component. |
| **7** | **Repository context and search** (`architecture.md` L6) | The instruction-file walk, the lazy subdirectory index, path-scoped rules, the read/search/edit tool semantics, the observed-paths set, the file-history store. | The provider; the permission rule syntax (it *reports* requests; layer 6 decides). | **Partly.** The search backends are replaceable (a different index, a different file API). The *semantics* — the read-before-edit gate, the lazy-load trigger — are the product's behaviour and are not replaceable without changing the product. |
| **8** | **Sessions and persistent state** (`architecture.md` L7) | Session identity, the append-only JSONL transcript, resume, compaction history, the cost ledger, checkpoints, job and task stores, the memory index. | The provider; the permission rules; the renderer. | **No.** The transcript format, the resume path, and the compaction boundary are published interfaces (`interface-spec.md` §11) with compatibility obligations. |
| **9** | **REA-based investigation workflows** (`architecture.md` L8) | Probe planning, evidence capture, the observation ledger, replayable probe scripts, the report assembler, the hypothesis→probe→evidence→conclusion discipline. | The provider's wire format; the TUI. It consumes tools through layer 6 and records into layer 8. | **Partly.** The REA toolchain is an external dependency; the *workflow discipline* is ours and is not replaceable. |
| **10** | **Testing and benchmarking** (`architecture.md` L9) | Contract tests per interface, golden transcripts, permission-matrix fixtures, regression suites, the metric catalogue, the reference-comparison protocol. | Nothing — it reads every layer, and every layer must be testable without it. | **No**, and it must not be. The test suite is the mechanism by which the boundary claims in this document are checked. |

**Cross-cutting X1 (policy and safety)** owns the protected-path table, the destructive-command analyser, the consent-required tool flag, the dangerous-mode interlock, and the workspace-trust gate. Nothing above it may override it, and it must be unreachable from the settings resolver (`security-plan.md` §5.4). **Cross-cutting X2 (telemetry and observability)** owns the event union, the decision records, the cost ledger, and the diagnostic channel. It observes; it never decides.

### 2.2 The swap-independence reading

**`AMB-101`** — A layer is *swappable independently* if and only if replacing it requires **no change in any other layer** and **no change in any published interface** (`interface-spec.md`). This is a stronger criterion than "is modular", and it is the criterion that `architecture.md` §5.3's "swap is a registry change, not a code change" claim rests on.

Applying it honestly produces three classes, and the middle class is the one that gets misrepresented in product discussions:

| Class | Layers | What a swap actually costs |
| :- | :- | :- |
| **Cleanly swappable** | 1, 2, 3, 4 | A configuration change plus a new artefact. No interface changes. The product's *behaviour* changes; its *contract* does not. |
| **Swappable in implementation, not in contract** | 5, 7, 9 | A new implementation is possible, but a *different* implementation changes what the product does in ways users can observe, and therefore changes published behaviour even where it changes no published field. |
| **Not swappable without changing the product** | 6, 8, 10 | These encode the promises. A different permission engine is a different product; a different transcript is a different product; a different test suite is a different product's assurance, not a component. |

**`AMB-102`** — The clean swap of layer 4 (the adapter) is what makes the S0→S1→S2→S3 transition in §4 possible at all. It is the single most valuable structural decision in the project, and it is also the single most dangerous, because a clean swap makes it *easy to change what the product is without changing what it says about itself*. The transition plan in §4 exists to prevent exactly that.

### 2.3 The dependency rule, restated as an attribution rule

**`AMB-103`** — A layer may only depend on layers below it (`architecture.md` §2). Above layer 4, **no provider-specific type may appear**; a lint rule enforces this (`interface-spec.md` §12.4).

The attribution consequence is the important part, and it is not obvious:

**`AMB-104`** — Because layers 5–9 sit strictly above layer 4, **the harness cannot know what model it is talking to, and the model cannot know what harness it is inside.** Therefore:

- A harness improvement (a better compaction policy, a better tool description, a better permission UX) changes the *pair* and changes nothing about the model.
- A model improvement changes the *pair* and changes nothing about the harness.
- **Any claim that attributes a change in the pair's behaviour to one of the two halves, without a controlled comparison, is unsound.** This is `benchmark-and-evaluation-plan.md` §9.5's two directions of misattribution, restated as an architectural invariant.

**`AMB-105`** — The model's total blindness to the harness has one concrete architectural consequence that must be honoured: **the harness cannot prompt the model about the harness.** There is no channel by which the harness can say "you are in Keel; here is how Keel's tools behave; the last error was a Keel-specific denial format." Whatever the harness wants the model to know, the harness must express it **through the context it assembles** (§7) or **through the tools it exposes** (§8). There is no third channel, and inventing one would break the layer boundary.

---

## 3. The provider adapter interface

### 3.1 Where the contract lives

The normative adapter contract is `interface-spec.md` **§12 (Interface 10 — Model adapter interface)**. This section does **not** duplicate it. It states:

1. The contract in the form an implementer needs, with cross-references to the normative text.
2. The **capability negotiation** rules, which `interface-spec.md` §12.1 declares in the type but does not fully specify as a negotiation protocol.
3. **What an adapter cannot do** — the two prohibitions that are load-bearing for this entire document.

### 3.2 The contract any model must satisfy

To be plugged in, a model must satisfy the `ModelAdapter` interface: `id`, `capabilities`, `complete(req, signal)`, `stream(req, signal)` (`interface-spec.md` §12.1).

**`AMB-201`** — The five sub-contracts below are the complete set of requirements on a pluggable model. Everything else in this document assumes they hold.

#### 3.2.1 Message format

**`AMB-202`** — The adapter MUST accept and produce `ProviderNeutralMessage[]`: `user` and `assistant` roles with typed content blocks (`interface-spec.md` §12.2). A provider-specific message shape MUST NOT cross the boundary. The harness assembles context; the adapter transports it; it does not restructure it beyond what the provider requires, and any restructuring it does perform is a lossy mapping that MUST be recorded in the request log for that turn.

#### 3.2.2 Tool-call format

**`AMB-203`** — The adapter MUST translate between the provider's tool-call representation and the harness's `tool_use` block with an `id` and a JSON `input` object matching the tool's `inputSchema`. Where the provider has a native function-calling channel, the adapter uses it; where it does not, the adapter parses the text channel. The native format is a permitted difference in a model comparison (`benchmark-and-evaluation-plan.md` §9.3) because it is a transport difference, not a prompt difference — but the **schema the model sees** must be byte-identical across arms (control RC3).

**`AMB-204`** — The adapter MUST NOT repair a malformed tool call, MUST NOT synthesise arguments the model did not emit, and MUST NOT silently drop a tool call (`interface-spec.md` §12.4: an adapter is "a pure translation layer"). A malformed tool call is a **model error**, and it is reported as one (§9) rather than smoothed over at the adapter. Repairing it would move a model failure into a harness success and make the model look better than it is.

#### 3.2.3 Streaming format

**`AMB-205`** — The adapter MUST expose `stream()` as an `AsyncIterable<StreamChunk>`, translating provider fragment semantics (SSE frames, delta-encoding, cumulative-vs-delta tool arguments) into the harness's chunk model. A provider that does not support streaming MUST still satisfy the interface by buffering and emitting a single complete chunk (`interface-spec.md` §12.9). The harness MUST remain correct in the buffered case, including the never-resend rule (§9.3) and the partial-output warning.

#### 3.2.4 Token accounting

**`AMB-206`** — The adapter owns token accounting (`interface-spec.md` §12.4). It MUST return provider-neutral `Usage` with `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and `output_tokens_details.thinking_tokens` counted **separately** (`feature-checklist.md` S13-THINK-023). A provider that does not report thinking tokens MUST report zero, not an estimate, unless it can support a documented estimate; an estimate MUST be flagged as an estimate in the usage record.

**`AMB-207`** — The adapter MUST report the **model that actually served the request**, which may differ from the requested model id after a fallback (`feature-checklist.md` S13-FALLBACK-008). The `modelUsage` ledger is keyed by the serving model (`interface-spec.md` §17.3), and the disclosed provider and ownership MUST correspond to the serving model, not the requested one. A fallback that crosses from a provider-hosted model to a local one — or the reverse — changes the ownership of the run and MUST be visible in the record.

#### 3.2.5 Error taxonomy

**`AMB-208`** — The adapter MUST map provider errors into the provider-independent category enum (`interface-spec.md` §12.7): `authentication_failed`, `organization_not_allowed`, `account_on_hold`, `billing_error`, `rate_limit`, `overloaded`, `invalid_request`, `model_not_found`, `server_error`, `max_output_tokens`, `credential_error`, `unknown`. The HTTP status MUST be carried **separately** from the category, and the indefinite-retry watchdog MUST be scoped to the capacity classes only (`rate_limit`, `overloaded`, `server_error`). Account-state categories MUST NOT be retried indefinitely.

**`AMB-209`** — The adapter MUST NOT retry a request that has already committed content (`interface-spec.md` §12.9; `architecture.md` §10.3). This is a Tier-2 property (`security-plan.md` §5.7, stream-commit tracking) and it lives partly inside the adapter because only the adapter knows where the commit boundary is.

#### 3.2.6 Capability negotiation

**`AMB-210`** — Capability negotiation is **declaration, not discovery** in the direction that matters. A hosted adapter reports what the provider advertises; a self-hosted adapter declares its capability set **out of band, at registration time** (`architecture.md` §5.4). The harness does not probe a model to discover what it can do.

The capability set is:

| Capability | Meaning if `false` | Consequence in the harness |
| :- | :- | :- |
| `toolCalling` | The model cannot emit tool calls | The registry MUST contain **no tools**; the harness runs as a text-only agent (`interface-spec.md` §12.9). |
| `thinking` | No extended reasoning | `thinkingTokens` is zero; the reasoning display is unavailable. |
| `effortControl` | No reasoning-effort axis | The effort value is ignored with a warning (`interface-spec.md` §12.7); the run continues at the current effort. |
| `streaming` | No streaming | The adapter buffers; the harness's streaming UI degrades to a single complete block. |
| `structuredOutput` | No schema-constrained output | `--json-schema` is refused with a named diagnostic, not silently ignored. |
| `promptCaching` | No cache | `cache_creation_input_tokens` and `cache_read_input_tokens` are zero; cost comparisons MUST account for this (`benchmark-and-evaluation-plan.md` §9.6, rule 4). |
| `contextWindow` | The usable window | The window itself is always known — an unrecognised model defaults to **200,000** tokens (`interface-spec.md` §14.2). The auto-compact window is derived from it (`feature-checklist.md` S13-AUTO-018). |
| `maxOutputTokens` | The output cap | The overflow ladder's first rung — reduce the output cap and retry (`interface-spec.md` §14.7) — is bounded by this. |
| `costTable` | **Absent** | `costBasis` becomes `"unknown"` and `costUSD` is `0` (`interface-spec.md` §12.8). |

**`AMB-211`** — The harness MUST NOT require any provider capability. A provider supporting none of {tool calling, thinking, effort, streaming} still yields a working harness: no tools → a text-only agent; no streaming → a buffered agent (`interface-spec.md` §12.4). This is a robustness requirement and it is also, unavoidably, the reason a weak model can be plugged in and produce a weak product. See §3.4.

**`AMB-212`** — A capability that is absent MUST fail **by subtraction** — the feature is absent, not present-and-failing — wherever a mechanism exists (`feature-checklist.md` S13-CAP-010; `prompt-pattern-analysis.md` X1). A tool that cannot be used is not published in the tool schema. A model cannot attempt what it cannot see.

### 3.3 What an adapter is for

**`AMB-213`** — The adapter exists to make the *rest* of the system provider-agnostic. Its value is measured by how little of the codebase knows which provider is in use. Concretely, the adapter owns: endpoints, authentication, transport, retries, streaming-fragment translation, token accounting, and the error-category mapping (`interface-spec.md` §12.4). It owns **no judgement**.

### 3.4 What an adapter cannot do

These are the two prohibitions this document exists to make concrete.

#### 3.4.1 An adapter cannot make a weaker model competent

**`AMB-220`** — An adapter is a **transport**, not a capability. It cannot add tool-calling competence to a model that lacks it; it can only translate the competence the model has, if any. The "text-only agent" case (`interface-spec.md` §12.9) is the extreme illustration: with `toolCalling: false` the registry contains no tools, and no amount of adapter sophistication puts a tool call into the model's output.

**`AMB-221`** — Therefore, a "the model got it wrong" diagnosis may never be softened by an adapter-side rescue. If the adapter's error mapping, retry policy, or fallback chain papers over a model's incompetence, the product's measured quality rises without its intelligence rising, and the attribution becomes false. The prohibition on repairing malformed tool calls (`AMB-204`) is a specific instance of this general rule.

**`AMB-222`** — A corollary with a practical consequence: **a model swap is never free of consequence for product quality.** A project that swaps in a 1.5B model to save money is not producing "the same product more cheaply"; it is producing a different product. The benchmark plan's requirement that the harness variant, the model, and the effort level all travel with the score (`benchmark-and-evaluation-plan.md` §9.7) exists because the equivalence is not free.

#### 3.4.2 An adapter cannot supply the harness's judgement

**`AMB-230`** — The harness's judgement is **not in the model and not in the adapter**. It is in the layers above:

- whether a call is permitted (layer 6, and the Tier-2 interlock);
- whether a file was read before it is edited (layer 7's observed-paths set);
- what context the model sees at all (layer 8's compaction and layer 7's assembly);
- whether the run continues, compacts, or stops (layer 5's loop and the thrash detector);
- what a denial message says and whether the model may try an equivalent tool (`security-plan.md` §7.3, PR-4).

**`AMB-231`** — The adapter cannot be the place where any of these decisions are made, and a proposal to put one there is a boundary violation regardless of how it improves the score. A permission check in an adapter is invisible to the audit log, unreachable by the Tier-2 test suite, and unbypassable only by accident.

**`AMB-232`** — This is why the harness's contribution is not a rounding error. §5 accounts for it in full.

### 3.5 The lint rule

**`AMB-233`** — A build-time lint MUST fail if a provider-specific type appears above the adapter boundary (`interface-spec.md` §12.4). This is one of the few rules in the project that is load-bearing for a *narrative* claim (that Keel is provider-agnostic) as well as for a technical one. Without it, "provider-agnostic" is a claim about the first week of implementation, not about the shipped product.

---

## 4. The transition plan

### 4.1 The shape of the transition

The project will start on a borrowed model and, if the model programme succeeds, arrive at its own. This section specifies the stages so that **the product's description of itself changes exactly when the underlying fact changes, and not before.**

The stage name is a **public, machine-readable** string. It appears in the `init` event, in the headless envelope, in the version banner, and in the documentation. It is not a marketing label; it is a state variable.

**`AMB-301`** — The stage is determined by a **single source of truth**: the ownership and origin of the model that is serving the session. It is never set by configuration, never set by a flag, and never set by marketing copy. The stage is *derived* from the adapter registry and the model's provenance record.

**`AMB-302`** — Every stage below has an **acceptance criterion** for promotion, and promotion is a **programme decision recorded in writing**, not an engineering side effect. Passing a test suite does not promote a stage; a test suite is evidence *for* the decision.

### 4.2 The stages

| Stage | Name | Model situation | What the product says |
| :- | :- | :- | :- |
| **S0** | `provider-only` | Every model available is served by a third party. No model of ours exists, or none is good enough to be offered. | "Keel is a harness. The model it drives is <model-id>, served by <provider>. The intelligence is the provider's; the harness, tools, permission decisions, transcript and safety model are ours." |
| **S1** | `own-model-behind-the-same-adapter` | A model of ours exists and is served by the same adapter interface, but the **default** is still a provider model, or ours is available only as an opt-in. | "Keel can drive either <provider model> (via <provider>) or <our-model-id> (Keel's own model, <base-model>). The default is <X>. Both are driven by the identical harness; differences between them are differences between models." |
| **S2** | `own-model-default` | Our model is the default for the `main` role. Provider models remain available as opt-in alternatives. | "Keel's default model is <our-model-id>, trained by this project on <base-model>. Provider models are available as alternatives and are labelled as such." |
| **S3** | `own-model-only` | No provider model is reachable in the shipped configuration. | "Keel runs entirely on this project's own model. No request leaves the machine." |

### 4.3 The stage table in full

**`AMB-303`** — The following table is normative. A column marked as a *false claim* is a claim that is **not merely unsupported but affirmatively deceptive at that stage**, and is prohibited.

| | **S0 — provider-only** | **S1 — our model behind the same adapter** | **S2 — our model default** | **S3 — our model only** |
| :- | :- | :- | :- | :- |
| **Weights are ours** | No | Yes | Yes | Yes |
| **Training data is ours** | No | Yes | Yes | Yes |
| **Inference is ours** | No | Depends on the serving arrangement; must be stated | Must be stated | Yes |
| **The model in use is a provider's** | Yes, always | Sometimes | No (default), sometimes (opt-in) | No |
| **A request leaves the machine** | Yes, always | Only for provider-backed sessions | Only for provider-backed opt-in sessions | Never |
| **The product is an "AI coding agent"** | Yes — it is one, with a borrowed mind | Yes | Yes | Yes |
| **The product is an "independent AI"** | **FALSE CLAIM** | **FALSE CLAIM** | **FALSE CLAIM** unless S3 *and* the model is genuinely ours end to end | Only arguable, and still not recommended as a headline |
| **The product is "offline"** | **FALSE CLAIM** | **FALSE CLAIM** for provider-backed sessions; true only for our-model sessions, and must be qualified per-session | **FALSE CLAIM** for provider-backed opt-in sessions | True |
| **The product has "no API cost"** | **FALSE CLAIM** (the cost is real and someone pays it) | **FALSE CLAIM** for provider-backed sessions; true for our-model sessions | **FALSE CLAIM** for provider-backed opt-in sessions | True, at zero marginal cost |
| **"Our model" means our weights** | **FALSE CLAIM** — always | True | True | True |
| **Our harness is the differentiator** | True and must be said | True and must be said | True and must be said | True and must be said |
| **The provider is named in the UI** | **REQUIRED** | **REQUIRED** for the provider option | **REQUIRED** for the provider option | N/A (but the base model MUST be named) |
| **The base model MUST be named** | N/A | **REQUIRED** if our model is a fine-tune or derivative of a named base | **REQUIRED** | **REQUIRED** |
| **Cost accounting** | `costBasis: standard` with a dated price table, or `unknown` | Both, per model, in `modelUsage` | Both, per model, in `modelUsage` | `costBasis: unknown`, `costUSD: 0` |

**`AMB-304`** — The "own model" test. A model counts as *ours* for the purposes of this table only if **all four** hold:

1. The weights were trained by this project, or by a contractor under this project's direction, on a corpus whose provenance this project controls.
2. The base model, if any, is named in the disclosure.
3. The training corpus contains no path to the Services' outputs (the `§D.4` requirement, `licensing-and-provenance-review.md` §8 and OPEN-Q5).
4. The evaluation set is held out and uncontaminated, and the decontamination regime is documented.

**`AMB-305`** — A model that fails any of the four is a **fine-tune of someone else's model**, which is a legitimate and valuable artefact, and it is **not** "our model" in the sense the word is used in marketing. It MUST be disclosed as `keel-own` with a `model_base` naming the base (`AMB-011`), and the word "our" MUST NOT be used unqualified in prose. The permitted phrasing is "Keel's model, built on <base-model>".

### 4.4 Promotion criteria

**`AMB-306`** — Each promotion requires **all** of the listed criteria. A partial pass is not a promotion; it is a stage that is not reached, and the product continues to describe itself at the lower stage.

#### S0 → S1

| # | Criterion | Evidence required |
| :- | :- | :- |
| S1-1 | Our model satisfies the `ModelAdapter` contract, including tool-calling, streaming, and token accounting. | The adapter conformance suite passes against the model's serving stack. |
| S1-2 | The model's provenance record satisfies all four elements of `AMB-304`. | A signed provenance manifest, in the format the licensing review requires. |
| S1-3 | The decontamination regime is documented and independently checked. | A decontamination report, with the contamination consequence stated in writing. |
| S1-4 | The model is served through **the same adapter interface** as the provider models — not a special path. | The lint rule (`AMB-233`) passes; the provider-specific-type check is clean. |
| S1-5 | The stage string is derived, not configured, and the `init` event reports the correct ownership. | A test asserting the stage derivation for each adapter in the registry. |
| S1-6 | A **paired** comparison against the provider model has been run under the `benchmark-and-evaluation-plan.md` §9.2 controls, and the harness variant is recorded. | The §8.7 comparison report template, completed, with the RC1–RC11 controls checked. |

#### S1 → S2

| # | Criterion | Evidence required |
| :- | :- | :- |
| S2-1 | Our model is **not worse** than the provider model on the project's own task suite, at matched effort, under a paired design. | Per-task deltas, with the pairing reported, per `benchmark-and-evaluation-plan.md` §8.4. |
| S2-2 | The model passes the **end-to-end agentic test** — it is driven by the harness through multi-step tasks, not merely scored on code generation. | Task-suite results under the harness, per `benchmark-and-evaluation-plan.md` §4. |
| S2-3 | The cost accounting is honest: if our model has no price table, `costBasis` is `unknown`, and the comparison reports tokens as well as money. | The §9.6 cost accounting, completed, including the whole-tree figure. |
| S2-4 | The failure-mode taxonomy shows our model's failures are **of a different shape** from the provider model's, and the difference is understood. | A failure taxonomy comparison, not a scalar. |
| S2-5 | The default can be changed to our model by **configuration only**, with no code change, and reverting is equally configuration-only. | A demonstrated round trip, recorded. |
| S2-6 | The disclosure surfaces (§12) are updated for S2 and reviewed. | The disclosure register is re-signed. |

**`AMB-307`** — S2-1 is deliberately worded as "not worse", not "better". The purpose of S2 is that the product's default model is one the project controls, which is a governance and independence property, not a quality claim. A model that is merely *adequate* may legitimately be made the default; a model that is claimed to be *better* would need the §10 evaluation discipline, and would also fail `benchmark-and-evaluation-plan.md` §9.9's prohibition on a comparison without harness control.

#### S2 → S3

| # | Criterion | Evidence required |
| :- | :- | :- |
| S3-1 | No provider endpoint is reachable in the shipped configuration. | A configuration audit and a network-denial test. |
| S3-2 | The product's core task suite passes on our model alone, with a published pass rate and a stated uncertainty. | The §7 success criteria and the threshold table. |
| S3-3 | Every capability in `AMB-210` that the product depends on is present in our model, or its absence is a **deliberate, documented, and visible** degradation. | The capability matrix diff. |
| S3-4 | The disclosure surfaces are updated for S3 and the "fully offline" claim is verified rather than asserted. | A network-isolation test in CI. |
| S3-5 | The licence posture for the shipped model is reviewed and recorded. | An updated `licensing-and-provenance-review.md`. |

### 4.5 What a stage transition is not

**`AMB-308`** — A stage transition is **not** a marketing event. The stage string changes in the code, the disclosure surfaces change with it, and the documentation changes with it. There is no "launch", no announcement, no "our model is now live" framing, because the stage describes a fact about the artefact, not an achievement.

**`AMB-309`** — **A model that is merely *available* does not advance the stage.** Availability is a registry fact; the stage is a default-configuration fact plus a disclosure fact.

**`AMB-310`** — **A stage may regress.** If our model is withdrawn, or a defect is found that makes it unsuitable as a default, the stage reverts to the previous one, and the disclosure surfaces revert with it. The stage is derived state, and derived state that cannot move backwards is a banner, not a fact.

### 4.6 The transition's interaction with the licensing constraint

**`AMB-311`** — This transition plan is **unaffected by the open question** in `licensing-and-provenance-review.md` §12 (OPEN-Q1: whether §D.4 reaches using a provider service as a runtime model provider). That review states the plan is built so the answer changes nothing we do, and this document is an instance of that construction: the S0–S3 path does not depend on the provider path being legally comfortable, because the project can reach S3 without ever using the provider service in the product, and the S0/S1 stages are a development convenience whose continuation is a *decision* (OPEN-Q1's recommended option (b) is a non-Anthropic provider) rather than a dependency.

**`AMB-312`** — **What is blocked at every stage:** using the provider service's outputs — including this project's own black-box transcripts — as training data or as a distillation teacher (`licensing-and-provenance-review.md` §8.1, `§D.4`). This is not a stage-dependent rule. It applies at S0 exactly as at S3.

**`AMB-313`** — The prompt research collection is a **design-principle source only** (`prompt-pattern-analysis.md`; `licensing-and-provenance-review.md` §3.3, §4.1). The 6 captured Anthropic skill bundles carry Anthropic's own restrictive licence and are EXCLUDED. The 5.x captures are corroborated (86–92% of Anthropic's own published prompt text appears verbatim) and the 4.x captures are not (14–29%) — this is why the collection is a *principle* source and not a *behavioural* source, and why `AMB-321` matters.

### 4.7 The stage, the benchmark, and the honesty of the comparison

**`AMB-314`** — Every benchmark report carries the **stage** of the product that produced it, alongside the model, the provider, the harness fingerprint, the task set and its version, and the harness variant. A number without the stage is not attributable to a product.

**`AMB-315`** — At S1, the project's own model and the provider model are compared under the RC1–RC11 controls. At S2 and S3, the comparison continues, because **the day our model becomes the default is exactly the day the incentive to flatter it appears.** The controls do not relax at promotion; they tighten.

---

## 5. What the harness contributes that the model does not

### 5.1 The accounting

This section is the reciprocal of §6 and is deliberately just as long. A document that accounts honestly for what the model contributes and gestures at the harness's contribution is a document that flatters the model.

**`AMB-401`** — The capability inventory below is split by the test: **would this capability still exist if the model were replaced by a different model of identical or greater quality?** If yes, it is a harness capability. If no, it is a model capability (§6).

### 5.2 The harness's capabilities, one by one

| # | Capability | Layer | What it actually does | Model-dependent? |
| :- | :- | :- | :- | :- |
| 1 | **Permission evaluation** | 6 | Evaluates every tool call against the rule set, the mode, the consent flag, and the Tier-2 interlock, in a fixed order, and records the decision. | **No.** The engine is code. A different model proposes the same call and gets the same decision. |
| 2 | **Tier-2 safety** | 6 / X1 | The protected-path table and the destructive-command analyser, which parse a command into its operation set and refuse destructive operations regardless of configuration. | **No.** A model cannot talk its way past a parsed operation set. |
| 3 | **Tool execution** | 6 | The actual filesystem, process, and network operations, with their encoding guarantees, partial-read marking, and read-before-edit enforcement. | **No.** The model emits a call; the tool does the work. |
| 4 | **Context compaction** | 8 | The head/anchor/tail selection, the summary written as a user-role message, the boundary record, the monotonic dropped-token counter, the thrash detector, the three-rung overflow ladder. | **No** — the *procedure* is the harness's. The *summary text* is produced by a model (the `summariser` role), so the quality of the summary is model-dependent. **This is the one place in this table where both sides contribute**, and it is called out rather than buried. |
| 5 | **Session persistence** | 8 | The append-only JSONL transcript, the resume path, the checkpoint store, the cost ledger, the memory index, the compaction-boundary records. | **No.** |
| 6 | **Subagent orchestration** | 5 | Spawn, the capability caps, the depth limit, the worktree isolation, the ledger, the join, the report framing as non-authoritative. | **No** for the machinery. **Yes** for the quality of the decomposition — but the decomposition is *proposed* by the model. |
| 7 | **The test suite** | 10 | 240 test cases, the attack matrix, the property tests, the determinism contract, the golden transcripts. | **No.** |
| 8 | **The sandbox** | 6 | OS-level confinement where the platform provides it; on native Windows, a symbolic layer plus a loud diagnostic, and a `fail-if-unavailable` option. | **No.** |
| 9 | **The tool surface itself** | 6 | Which tools exist, what their schemas are, what their descriptions say. | **Partly.** The *existence* and *semantics* of a tool are the harness's. The **description text is prompt**, and prompt is the experimental variable (`benchmark-and-evaluation-plan.md` §9.2, RC4). A different tool description is a different prompt. |
| 10 | **The context assembly** | 7 / 8 | What the model is told, in what order, and what is withheld. | **No.** The model does not choose. See §7. |
| 11 | **The loop and its limits** | 5 | The turn state machine, the turn and budget caps, the never-resend rule, the stop conditions. | **No.** |
| 12 | **The audit trail** | 8 / X2 | The decision records, the event stream, the tamper-evident design. | **No.** |
| 13 | **The disclosure surface** | 8 / X2 | The init descriptor, the model picker, the cost ledger, the provider attribution. | **No.** |

**`AMB-402`** — Thirteen of the fourteen entries in this table survive a model swap unchanged. This is the harness's actual contribution, and it is the honest answer to "what is Keel?" — the harness, in full, plus whatever model it is driving.

### 5.3 Two specific mechanisms, in detail

#### 5.3.1 Permission evaluation

**`AMB-403`** — The permission engine evaluates in a fixed order — deny, then allow, then mode, then human callback, then deny-if-no-callback — with first-match-wins inside a category, and with the Tier-2 analyser running **after** and **independently of** the Tier-1 rule engine (`security-plan.md` §5.1, §5.7). An allow rule for a destructive command does not suppress the analyser.

**`AMB-404`** — The relevance to this document: **the permission decision is not a model output.** The model proposes; the engine disposes. Therefore a permission decision is never evidence of model capability, and a run in which the model was denied 40 times and completed the task is a run where the *harness* did 40 pieces of work that the model did not have to do.

**`AMB-405`** — The project's own design deliberately strengthens this relative to the reference: a bare-name deny removes the tool from the schema **and** the dispatch table, and the schema removal is not relied upon as the defence (`security-plan.md` §5.5, D-3). Schema removal is a hint to the model; the dispatch refusal is the guarantee. This is principle X1 (`prompt-pattern-analysis.md`) applied to the permission system, and it is a *harness* contribution that is entirely independent of model quality.

#### 5.3.2 The tool descriptions — where the harness leaks into the prompt

**`AMB-406`** — The tool `description` field is **prompt**. It is read by the model and it shapes the model's behaviour. This is the one place where a harness artefact is simultaneously (a) a harness artefact, and (b) part of the experimental variable.

**`AMB-407`** — The consequence for attribution: **changing a tool description changes the model.** Therefore:

- A benchmark that changes tool descriptions between arms is not holding the model constant.
- A product that improves its tool descriptions will produce better agent behaviour **without any model change**, and that improvement is a harness improvement.
- The reference evidence records the tool `description` field as model-authored and sitting directly on the trust path (`benchmark-and-evaluation-plan.md` §9.2, citing L12) — which is an observation about the reference, not a claim about ours.

**`AMB-408`** — Therefore, in the disclosure register (§12), the phrase "improved agent quality" **MUST** be attributed to the model, the harness, or the pair — and the tool descriptions belong to the harness side. A product that improved only its tool descriptions and reports "our agent is better" has misattributed a harness change to a model.

### 5.4 The implication: two models, one harness, two products

**`AMB-409`** — Two different models driven by the same harness produce **measurably different products**, in at least these observable dimensions:

| Dimension | Why it differs |
| :- | :- |
| Task success rate | The model's planning and tool-selection competence. |
| Number of turns to completion | The model's efficiency in reaching a working state. |
| Tool-call error rate | The model's argument construction. |
| Recovery from a failed tool call | The model's diagnosis of an error message. |
| Rate of "the model gave up and said so" | The model's calibration. |
| Cost per successful task | The combination of both, plus the provider's price table. |
| The *shape* of the failures | Different models fail differently; a failure taxonomy is more informative than a scalar (`benchmark-and-evaluation-plan.md` §1.1). |

**`AMB-410`** — Therefore, **benchmarking "our agent" against "their agent" without controlling for the harness is invalid.** The comparison is product-vs-product if both products are involved, and is a model comparison only if the harness is held constant — which requires the RC3, RC4, RC5, RC6, and RC9 controls (`benchmark-and-evaluation-plan.md` §9.2).

**`AMB-411`** — The full statement of the rule, inherited from `benchmark-and-evaluation-plan.md` §1.1 and §9.5:

> The observed difference is a difference between **(model, harness)** pairs, measured on **task set T**. It does not by itself establish that the models differ in capability. To distinguish the model from the harness, the comparison must be repeated under a second harness variant (A/B/C) with the direction of the difference tested for consistency.

**`AMB-412`** — The two directions of misattribution, restated here because both apply to this project and not only to comparisons against other people's models:

- **Direction 1 — a stronger model scores higher on the harness, not intrinsically.** The reference product's own error messages are, in the reference's own framing, designed to be recoverable from — a uniqueness error described as "load-bearing in the agent loop — the model recovers by adding context", and the whole error path described as "a diagnosis, not a category" (`benchmark-and-evaluation-plan.md` §9.5, citing OBSERVED-CLI F4.3 and F6.2). A model shaped to read that particular style will recover from it more often. That is an advantage of the reference *system*, correctly attributable to the reference system, and misattributable to the model.
- **Direction 2 — a stronger model scores lower because the harness suits it less.** A model with a different tool-call idiom may score lower against the same harness without being worse at the task. This is why Variant B (harness-matched emulation) exists.

**`AMB-413`** — A third direction, specific to this project and stated here so it is not discovered later: **our harness will be tuned to our model, over time, for exactly the reason any harness gets tuned.** The prompt is written for the model that will run it; the tool descriptions are written for the model that will read them; the error messages are written for the model that will read them. Once our own model is the default, our harness is quietly co-adapted to it, and a comparison against a third-party model through our harness is a comparison against a model *not* co-adapted to it. This is not a reason to avoid the comparison; it is a reason to **declare** it, and the declaration is the harness variant field.

### 5.5 What the harness contribution is worth, in one line

**`AMB-414`** — The harness's contribution is the difference between a language model and an agent. It is worth a great deal, and it is worth **zero** of the model's competence. The two are not substitutes and not additive in any simple way; the pair is the product.

---

## 6. What the model contributes that the harness does not

### 6.1 The accounting

The reciprocal of §5. The test applied here: **would this capability still exist if the harness were replaced by a different, minimal harness that does the same tool calls?** If no, it is a model capability.

### 6.2 The model's capabilities, one by one

| # | Capability | What the model actually does | Harness's role | Model-dependent? |
| :- | :- | :- | :- | :- |
| 1 | **The plan** | Decides what the task is, what order to do things in, what to skip, what "done" means. | Provides the plan artifact, the plan-mode gate, the approval signal, and the file the plan is written to (`prompt-pattern-analysis.md` X12). | **Yes.** The harness can hold a plan and can require one; it cannot produce one. |
| 2 | **The code** | Writes the code, the test, the refactor, the migration. | Executes, formats, lints, and persists it. | **Yes.** |
| 3 | **The tool-call decision** | Chooses which tool, with which arguments, in which order, and whether to call a tool at all versus answering in prose. | Publishes the schemas and executes the chosen call. | **Yes.** The choice is the model's. The execution is not. |
| 4 | **Failure recovery** | Reads an error message, a stack trace, a test failure, or a diff, and decides what it means: retry, read more, change approach, ask, or stop. | Delivers the error faithfully, in the dual representation (`interface-spec.md` §4.4), and records the outcome. | **Yes** — and it is the single most model-dependent capability in the table, because it depends on the model understanding a harness-specific error format. |
| 5 | **Language understanding** | The whole of reading the user's request, the repository's conventions, the issue text, the diff, the documentation, and the requirements. | Provides the bytes. | **Yes.** |
| 6 | **Judgement about relevance** | Deciding that a file matters, that a search result is a false positive, that a proposed approach is wrong, that a test is testing the right thing. | Provides the search results, the file contents, and the observations. | **Yes.** |
| 7 | **Knowing when to stop** | Recognising that the task is complete, or that it cannot be completed. | Enforces the turn cap, the budget cap, and the terminal result envelope regardless. | **Yes** for the *decision*; the harness enforces the *limits*. |
| 8 | **The natural-language output** | The final text the user reads. | Renders it, and refuses to present it on a failure subtype (`interface-spec.md` §17.4). | **Yes.** |
| 9 | **The compaction summary** | Writes the summary that replaces the compacted middle of the conversation. | Selects the head/anchor/tail, writes the boundary record, counts the dropped tokens, runs the thrash detector. | **Partly** — the *procedure* is the harness's, the *text* is the model's. §5.2 item 4. |

### 6.3 The consequential asymmetry

**`AMB-501`** — Every one of the nine capabilities above is **unavailable to the harness in the absence of a model**. The harness can enforce a limit, but it cannot decide that a task is done. It can hold a plan, but it cannot write one. It can execute a call, but it cannot choose the call.

**`AMB-502`** — This asymmetry is exactly why the disclosure rule (`AMB-001`) is necessary rather than pedantic. The harness *is* the product in the sense that a user experiences it — the permissions, the transcripts, the refusals, the resumption, the sandbox are all ours and all good. And the part that decides what the agent is trying to do is not ours. A product that is 90% ours in engineering and 100% borrowed in judgement can easily be misread as ours in judgement too.

### 6.4 The consequence for how benchmark results must be reported

**`AMB-503`** — The following reporting rules follow directly from §5 and §6, and they are stated as rules rather than as advice because `benchmark-and-evaluation-plan.md` §9.9 lists the prohibited uses.

| Rule | Statement | Identifier |
| :- | :- | :- |
| No headline number may be attributed to the model alone | A single-arm number is a number about a configuration. | `AMB-504` |
| Every model-attributed number names the model **and** the provider **and** the harness fingerprint | The pair is the unit of measurement. | `AMB-505` |
| Every harness-attributed number names the harness **and** states the model configuration it was measured on | Otherwise the reader cannot tell which change caused the delta. | `AMB-506` |
| A number that mixes arms with different harnesses MUST carry the harness variant on every row | `benchmark-and-evaluation-plan.md` §9.4. | `AMB-507` |
| A failure taxonomy MUST accompany any pass rate | A scalar hides the shape of the failures, and the shape is where the actionable information is. | `AMB-508` |
| A cost number MUST carry its basis and its date, and `costBasis: unknown` MUST NOT be rendered as zero-cost | `benchmark-and-evaluation-plan.md` §9.6; `interface-spec.md` §12.8. | `AMB-509` |
| A "we improved X%" claim MUST name what changed — the model, the prompt, the tool descriptions, the permissions, or the harness | §5.3.2 and `AMB-408`. | `AMB-510` |
| A run's stage MUST be published with its results | `AMB-314`. | `AMB-511` |
| The comparison against a third-party product MUST be labelled a product comparison unless the harness is held constant | `AMB-410`. | `AMB-512` |
| No published result may be a single clean run of a single task presented as a rate | `benchmark-and-evaluation-plan.md` §1.1: one run is evidence of feasibility, not of rate. | `AMB-513` |

**`AMB-514`** — The **reference-model comparison protocol** (`benchmark-and-evaluation-plan.md` §9) applies to this project with one addition, stated here so it is not forgotten when that plan is executed: **when the arm is our own model and the other arm is a provider model, the comparison is a comparison of our model against a provider's model, not of "Keel" against "our model."** Our harness is the harness in both arms (Variant A), and the disclosure of that fact — plus the `model_base` field, if our model is a fine-tune — is what makes the result interpretable.

**`AMB-515`** — The project's own evidence base already demonstrates the danger with a concrete instance: the reference product's own evidence base contains 33 numbered limitations of the reference product, and several of them are **harness** properties that would depress or inflate any model measured through it (`benchmark-and-evaluation-plan.md` §1.1, OBSERVED-CLI `agent-evidence.md` §6 — L1 failed-command output with no file pointer; L13 `Glob` ignoring `.gitignore` while `Grep` respects it; L14 `Read` refusing files over 256 KB; L11 a 40–64 second visible compaction pause). A model measured through a harness with those four properties is being measured through *that* harness, and the number is a property of the pair.

---

## 7. The context boundary

### 7.1 The rule

**`AMB-601`** — **The model never decides what context it receives.** The harness assembles the context; the model consumes it. This is the single most load-bearing rule in this section, and it is the direct consequence of `AMB-105` (the model is blind to the harness and there is no channel by which the harness could be described to it beyond the context it assembles).

**`AMB-602`** — The model therefore has **no mechanism to request context**. It cannot say "give me the file" as a special request; it must call the read tool, which returns the file as a tool result — a *different* channel with different properties (§7.5). This is a deliberate design, and it has three consequences:

1. The context the model sees is exactly what the harness decided to put there, at a known cost, with a known order.
2. The context budget is **enforceable**, because the harness knows the size of everything it assembles.
3. The model's own attempts to expand context are visible, countable, and attributable — a tool call asking for a file is an event in the transcript.

### 7.2 The assembly order

**`AMB-603`** — The harness assembles the model-visible request in a **fixed order**. The order is normative, and it is the order below.

| # | Layer of context | Channel | Loaded when | Size behaviour |
| :- | :- | :- | :- | :- |
| 1 | **System prompt** | The system-role message | Every request | Small, fixed, byte-stable across turns and resumes |
| 2 | **Tool schemas** | The `tools` array, not the message body | Every request for core tools; deferred tools on demand | The single largest fixed cost in most requests |
| 3 | **Skill and command descriptions** | Within the system context or as user-role attachments | Session start | Names always; descriptions truncated to fit, least-used-first |
| 4 | **Project instructions** | **User-role attachments** (never the system role) | Session start, plus lazy loads | Full content, but cacheable |
| 5 | **Path-scoped rules** | User-role attachments | On first touch of a file in that subtree | Small |
| 6 | **The environment snapshot** | Structured data | Every request | Small |
| 7 | **The user's message** | User-role message | Every turn | Varies |
| 8 | **Conversation history** | User and assistant messages | Accumulates | Grows; the dominant cost over a long session |
| 9 | **Tool results** | User-role tool-result messages | As they occur | Grows; the other dominant cost |

**`AMB-604`** — Instruction files are delivered in the **user channel**, and the system prompt is **byte-identical with and without them** (`security-plan.md` §7.3, PR-2). This is a security property (PR-1: no content from outside the harness may be placed in the harness's instruction channel) and it is also an attribution property: it keeps the system prompt — the one thing that is unambiguously ours — separable from content we did not write.

**`AMB-605`** — The system prompt is **snapshotted per conversation and reused verbatim on resume** (`architecture.md` §9.6). This keeps the request prefix stable, which keeps prompt caching effective, which keeps transcripts comparable. A resumed session does not silently change its instructions.

### 7.3 The four context-producing layers, as inputs to the model

#### 7.3.1 The rules layer

**`AMB-606`** — The rules layer contributes: the project's operating instructions, the permission-mode semantics as the model experiences them (which tools will prompt, which will be refused), and the path-scoped rules.

**`AMB-607`** — The rules layer is **authored by us and delivered as data**. It contains no provider-specific content and no third-party content. Where a rule can be enforced by mechanism, the mechanism is used and the rule is removed from the prompt — this is X1 (`prompt-pattern-analysis.md`), and the rule of thumb recorded there applies: **the prompt should shrink as the harness grows**.

**`AMB-608`** — The rules layer's contribution is **harness-attributed**. A change to it changes the model-visible prompt and therefore the model's behaviour, and it is a harness change (`AMB-408`).

#### 7.3.2 The memory layer

**`AMB-609`** — The memory layer contributes: the per-project memory index, truncated at whichever of **200 lines or 25 KB** comes first, plus the memory files the model explicitly reads (`architecture.md` §9.3).

**`AMB-610`** — The memory layer is **written by the model** and **governed by the harness**. The harness owns the directory layout, the index format, the truncation limit, and the near-limit prompt to shorten. The model owns the content.

**`AMB-611`** — The attribution here is **mixed and must be reported as mixed**. A memory index that improves a later session is a joint product of what the model wrote and what the harness retained. It is neither a model metric nor a harness metric.

**`AMB-612`** — The memory files are excluded from the transcript retention sweep and persist until edited or deleted (`architecture.md` §9.3). This makes them a durable sink and therefore a place where injected content could persist; the injection rules (`security-plan.md` §7.3, PR-13) apply to them exactly as to any other retrieved content.

#### 7.3.3 The compaction layer

**`AMB-613`** — The compaction layer contributes: the head segment, the anchor message, the tail segment, and the summary that replaces the middle — **written as a user-role message**, so that the request assembly treats it uniformly with any other user content (`interface-spec.md` §14.5, §14.8).

**`AMB-614`** — The compaction layer is **the most attribution-sensitive layer in the system**, because it is the one place where the harness's procedure and the model's text are fused into a single artefact that then shapes all subsequent behaviour.

- The **selection** (which messages are preserved) is entirely the harness's.
- The **summary text** is entirely the model's.
- The **boundary record** — `preTokens`, `postTokens`, `cumulativeDroppedTokens`, `durationMs`, the preserved UUIDs — is entirely the harness's, and it is the auditable one.

**`AMB-615`** — Therefore, when reporting the effect of compaction, the report names the harness's contribution (the procedure, the counter, the thrash detector) and the model's contribution (the summary) separately. A claim that "compaction improved results" without that separation is a claim about the pair.

**`AMB-616`** — The `cumulativeDroppedTokens` counter is the honest measure of the harness's compaction work, because the per-event drop understates the total: a session that compacts five times has lost far more than the sum of any individual deltas suggests it has (`architecture.md` §9.2).

#### 7.3.4 The tool schema layer

**`AMB-617`** — The tool schema layer contributes: each tool's name, its JSON Schema, and its **description**. It is the largest fixed component of most requests.

**`AMB-618`** — The tool schema layer is the harness's, with one caveat that is stated everywhere it matters: **the description is prompt** (`AMB-406`). It is authored by us, it is delivered to the model, and it shapes the model's behaviour.

**`AMB-619`** — The tool schema layer is **tiered by capability**, not by policy alone. A tool that a bare-name deny rule removes is **absent from the schema** (`security-plan.md` §5.1, item 5) — the model is never told it exists. A tool that a capability matrix marks unavailable is absent by subtraction (`AMB-212`). A tool that is present but scoped-denied is visible and refused at dispatch.

**`AMB-620`** — Three distinct mechanisms remove a tool from the model's reach, and the distinction matters because they have different failure modes:

| Mechanism | Effect | Failure mode if it fails |
| :- | :- | :- |
| **Schema removal** (bare-name deny, capability absence) | The model cannot see the tool. | The model attempts it anyway; the dispatch table refuses it. Defence in depth. |
| **Dispatch refusal** (scoped deny, Tier-2 interlock) | The model sees the tool and is refused. | The model may retry or work around; the refusal repeats. |
| **Consent-required** (`requiresUserInteraction: true`) | The call is always refused without a human. | No allow rule may bypass it; a non-interactive run denies it (`interface-spec.md` §4.2). |

### 7.4 Precedence

**`AMB-621`** — Where two context items conflict, the precedence is fixed:

| Precedence | Item | Rationale |
| :- | :- | :- |
| 1 | **The system prompt** | The only content in the instruction channel, and the only content this project authored unconditionally. |
| 2 | **The tool schemas** | Structurally prior to any message; a tool the model can see is a capability it can use. |
| 3 | **The user-role attachments** (instructions, rules, memory) | Delivered in the user channel; they are content, not instructions, and are therefore subject to the injection rules. |
| 4 | **The user's own message** | The most recent explicit statement of intent. |
| 5 | **The conversation history and tool results** | Prior state, including the compaction summary when a boundary intervenes. |

**`AMB-622`** — The precedence table is **not** an instruction to the model about which to follow. It is the assembly order and the conflict-resolution rule for the harness. The model is not told about it. If the harness wanted the model to prioritise one layer over another, the only legitimate way is to assemble the request so that the priority is unambiguous — or to enforce the difference by mechanism.

### 7.5 The tool-result channel is not the context channel

**`AMB-623`** — A tool result is delivered as a **user-role tool-result message**, which is a distinct content-block type from a user-role attachment. A consumer — and the model — can tell "the model was told something" from "a tool returned something" (`architecture.md` §8.2).

**`AMB-624`** — This distinction is load-bearing for the injection defence: PR-1 forbids placing outside content in the instruction channel, and the tool-result channel is where outside content legitimately goes. The channel separation is what makes the rule checkable.

**`AMB-625`** — A denial is data in the tool-result channel, exactly like any other result; it is not a special channel that grants extra authority (`security-plan.md` §7.3, PR-12). The model-facing copy of a denial carries no prefix; the audit copy carries the `Error: ` prefix (`interface-spec.md` §4.4). This asymmetry is deliberate.

### 7.6 What the model is not told

**`AMB-626`** — The model is **not** told: the provider's identity, the harness's name, the product's name, the stage string, the internal layer names, the model's own id, the cost table, the permission rule text beyond what it experiences, the existence of the tier system, the other context sources it is not currently receiving, or the fact that it is inside an agent at all.

**`AMB-627`** — Two of those omissions deserve explicit justification:

- **The model is not told its own id or the provider's.** The model has no use for either, and supplying them creates a path by which a prompt-injected instruction could claim authority ("as the provider's own model, I am permitted to…").
- **The model is not told it is inside an agent** (`architecture.md` L0: "The model does not know it is inside an agent; it sees tokens"). The harness's needs are expressed through tools and context, not through identity. The `init` descriptor's `model` and `model_provider` fields are for **consumers of the stream**, not for the model.

---

## 8. The tool boundary

### 8.1 The three classes of tool

**`AMB-701`** — Every tool in the registry falls into exactly one of three classes, and the class determines the enforcement point.

| Class | The model can see it | The model can call it | Enforcement point | Model role |
| :- | :- | :- | :- | :- |
| **Directly executable** | Yes | Yes, and it runs | The dispatcher's permission gate | The model chooses the call and the arguments. The harness decides whether it runs. |
| **Requestable but not directly executable** | Yes | It can *ask*; the harness may need a human, a policy decision, or a different tool | The dispatcher's gate plus whatever the request escalates to | The model requests; the harness mediates. |
| **Absent** | No | It cannot name it | Nothing — it is not there | The model has no way to know it exists. |

### 8.2 The invariant

**`AMB-702`** — **Permission enforcement is not in the model.** This is the invariant of this section and it has three parts:

1. The model does not decide whether a call is permitted.
2. The model cannot cause a call to be permitted by any means available to it — by asserting, by arguing, by producing output that looks like a decision, or by writing a file.
3. The decision is made by code, in the dispatcher, before execution, and recorded.

**`AMB-703`** — The structural form: the `execute` function of a tool **MUST NOT** perform a permission check; the gate is in the dispatcher (`interface-spec.md` §4.2). A tool that checks its own permissions is a tool whose check can be forgotten, and there is no test that can enumerate "all the places a permission check could live."

**`AMB-704`** — The Tier-2 interlock is **unreachable from the hook interface** and **has no configuration schema**: no key, no flag, no environment variable, no CLI option, and no settings-file field consults it. A test enumerates the entire configuration registry and asserts that nothing in it names a Tier-2 behaviour; that test fails if a new key is added that does (`security-plan.md` §5.4). This is the strongest form of X1 in the project, and it is entirely a harness property.

**`AMB-705`** — A hook's verdict is an input to **Tier 1 only**. A hook that returns "allow" for a protected path does not cause the call to be permitted; a hook that returns "deny" for a benign call cannot cause Tier 2 to be consulted differently (`security-plan.md` §5.4).

### 8.3 The tool surface is a harness artefact, and it is also prompt

**`AMB-706`** — The set of tools the model sees is determined by the harness, from: the core registry, the capability matrix (absence by subtraction), the permission rule set (bare-name denial → schema removal), the deferred-loading rules, and the MCP server inventory. **The model has no say in any of it.**

**`AMB-707`** — A tool's `description` is prompt and is on the trust path (`AMB-406`, `AMB-408`). Two tool sets with identical schemas but different descriptions are different experimental conditions, and the RC3/RC4 controls in `benchmark-and-evaluation-plan.md` §9.2 treat them as such.

**`AMB-708`** — PR-3 (`security-plan.md` §7.3) is the invariant that keeps the description honest: a tool's `description` field may not widen a permission decision. Two calls differing only in that field resolve identically. A test asserts it. A model that writes a persuasive description of its own tool cannot thereby widen its own permissions.

### 8.4 The MCP surface

**`AMB-709`** — MCP tools are named `mcp__<server>__<tool>`, so permission rules and hook matchers can address them. Three properties hold regardless of what the server says about itself:

- A server's self-description never widens a permission decision (PR-5).
- A server's response cannot cause another server's tools to load, the permission mode to change, or a call to be approved (PR-6).
- A server's failure is isolated into its own channel and does not fail the run (`interface-spec.md` §8.9).

**`AMB-710`** — The MCP server is **not the model** and **not the harness**. It is a tool provider, and a third party. A server that supplies a strong tool is a harness-affecting change, and its tools' descriptions are prompt.

### 8.5 The skill-security surface

This is the most important subsection of this document after §1, because a skill is the one extension surface where a *third party can write prose that the model reads as instructions*.

**`AMB-711`** — **A skill's instructions are data delivered to the model, and must be treated as untrusted.** The rule is stated here in the strongest available form and it is not a matter of degree: a skill body is content, not a harness directive. It cannot change the permission mode, add rules, or load a plugin (PR-9). A skill is *instructions for a human or a model*, and it is delivered in a channel that carries no authority.

**`AMB-712`** — The enforcement, in four mechanisms:

| # | Mechanism | Statement | Source |
| :- | :- | :- | :- |
| 1 | **Two-tier loading** | At session start only the skill's **name and description** are loaded; the **body** loads only at invocation. A skill's prose is not in the context until the skill is actually invoked. | `interface-spec.md` §9.7 |
| 2 | **Budgeted listing** | The listing is budgeted; names are always kept; descriptions are truncated least-used-first. A skill cannot inflate the context by existing. | `interface-spec.md` §9.7 |
| 3 | **No template re-scan** | Substituted values are **never re-scanned** for further substitution, so a second-order injection cannot be created by substitution. | `interface-spec.md` §9.6; PR-10 |
| 4 | **Injected-command policy** | A shell command embedded in a skill body is **denied by default for untrusted sources** (project scope, plugin scope), or prompted in an interactive session; every execution is logged with the resolved command pattern; a denied or failed injected command **aborts the invocation** rather than producing a partially rendered body. | `interface-spec.md` §9.8 |

**`AMB-713`** — The rationale for the injected-command policy, quoted because it is the sharpest single statement of the risk: *a skill in a repository is code the repository ships. Executing it silently at render time is remote code execution by repository.*

**`AMB-714`** — The trust classification is **by source trust**, not by scope name alone, because a user-scope skill can be planted by a malicious plugin (`interface-spec.md` §9.8). Trust is a managed setting.

**`AMB-715`** — The scope of the skill-security rules is not just "the skill's body". It also covers: the skill's frontmatter (three distinct failure modes are distinguished, and names are never dropped from the listing), the skill's `allowed-tools` patterns (which are substituted, and which therefore narrow the turn's tool set — a skill cannot widen it), and the command's arguments (substituted literally, never re-scanned).

**`AMB-716`** — A skill's effect on the tool set is a **narrowing** operation. `allowed-tools` restricts the turn's tools; it never adds. This is consistent with the general rule that a repository may only narrow (`security-plan.md` §5.6, D-2 and the lattice).

### 8.6 Subagents and the delegation surface

**`AMB-717`** — A subagent's report is framed **in-band as non-authoritative**, and instruction-shaped content in it is flagged to the operator (PR-8). The report is a tool result, so it enters the context through the tool-result channel, not the instruction channel.

**`AMB-718`** — The subagent's report is a **model-authored** artefact. Its quality is the model + the delegated model's contribution; the framing, the isolation, the caps, and the flagging are the harness's. A report that contains an instruction is a *model* behaviour to be diagnosed (§9), not a harness defect — unless the flagging failed, in which case it is a harness defect.

### 8.7 The denial message as a boundary artefact

**`AMB-719`** — A denial message tells the model it may try a **naturally equivalent** tool, and that it must not attempt to work around the denial in malicious ways — and the harness enforces the same thing at dispatch, so the advice is never the only defence (PR-4).

**`AMB-720`** — The denial message is therefore doing something unusual: it is giving the model *judgement-shaped* guidance from the harness. This does not violate `AMB-601` (the model does not decide what context it receives) — the denial is context, and the harness decides to deliver it. But it does mean the denial text is **prompt**, it is **harness-authored**, and it shapes model behaviour. Its improvement is a harness contribution, and a report claiming a model improvement from better denial text is misattributing (`AMB-408`).

---

## 9. The failure boundary

### 9.1 The question

> **The agent made a mistake. Do we fix the model, the prompt, the tools, or the permissions?**

This is the question this section answers, and it is asked constantly during development. Answering it ad hoc produces a team that fixes the model for a harness bug, or tunes the prompt for a model limitation.

### 9.2 The diagnostic procedure

**`AMB-801`** — A failure is diagnosed by **re-running the same failure with a different variable changed**. Exactly one variable at a time, in a fixed order, from the most-controlled swap to the least.

| Step | Change | What it isolates | If the failure disappears |
| :- | :- | :- | :- |
| 1 | Same task, **same model, same harness**, second run | Run-to-run variance | The failure is stochastic. Do not fix it yet; measure the rate. |
| 2 | Same task, **same model, a different harness configuration** — e.g. a different prompt, a different tool description, a different permission mode | The prompt/tools/permissions | The fault is in the **harness**, in the named element. |
| 3 | Same task, **a different model**, same harness | The model | The fault is in the **model**. |
| 4 | Same task, **a different model AND a different harness** | Nothing — confirms nothing | Proceed; the failure is not reproducible in either single-variable swap. |
| 5 | The **same failure with a hand-built request** — the exact model-visible request, sent directly, with no harness | The harness's contribution to the request | If the model still fails on the raw request, the fault is in the **model or the prompt content**. If the raw request succeeds and the harness run fails, the fault is in the **harness's assembly**. |

**`AMB-802`** — Step 5 is the most decisive and the most often skipped. The harness can produce a *bad request* — a mis-assembled context, a truncated tool result, a corrupted instruction attachment — and the symptom is a model failure. Because the model's behaviour is the observable, the model gets blamed. The raw-request reproduction is what distinguishes "the model could not do this" from "the harness asked the wrong question."

### 9.3 The classification

**`AMB-803`** — After diagnosis, the failure is in exactly one of these classes, and the class determines the owner and the remedy.

| Class | Definition | Owner | Fixable by training? | Remedy |
| :- | :- | :- | :- | :- |
| **M — Model error** | The model, given a correct and sufficient request, produced a wrong or unusable output: a malformed tool call, an incorrect plan, a misreading of the code, a wrong argument, a failure to recover from a legible error. | The model programme (layers 1–3) | **Yes** — this is the only class where training is the right first answer. | Add to the training/eval mixture; add a regression case to the held-out suite; or fix with better prompting if the failure is idiosyncratic rather than systematic. |
| **H — Harness error** | The harness produced a wrong request, a wrong tool result, a wrong decision, or a wrong record: a mis-assembled context, a permission decision that was too strict or too lax, a tool result that lost information, a compaction that dropped the wrong thing, a transcript that misstates what happened. | The harness (layers 5–9) | **No.** Training does not fix a bug in the dispatcher. | Fix the harness. Add a test. This is an ordinary software defect. |
| **P — Prompt error** | The request was correct and sufficient, but the *instruction text* — the system prompt, a tool description, a denial message, an instruction attachment — did not say what it needed to, or said it in a way the model reasonably misread. | The harness's authoring (which is harness work) | **Sometimes** — but training on the fix is a way of papering over a prompt defect, and it makes the prompt worse over time. | Fix the prompt, then re-measure. If the same class of failure recurs, consider a mechanism instead of more prompt (`prompt-pattern-analysis.md` X1). |
| **T — Tool-design error** | The tool exists and works, but its interface invites misuse: a schema that allows the wrong thing, a result format the model cannot parse, an error message that does not say what went wrong. | The harness (layer 6) | **No.** | Change the interface. Prefer a schema that makes the error unrepresentable over a prompt that discourages it. |
| **S — Systemic / expected** | The failure is the model refusing, exceeding a limit, or behaving as designed under a constraint: a refusal, a turn-cap stop, a budget-cap stop, a permission denial the model did not work around. | Nobody — it is the design working | **No.** | **Do not "fix" it.** The system did what it was supposed to do. |
| **E — Environmental** | The failure came from the environment: a network outage, a disk-full, a dependency that would not install, a test that is flaky for reasons unrelated to either side. | The environment | **No.** | Fix or isolate the environment. A flaky test is a test defect; a network failure is a network failure. |

**`AMB-804`** — The classes are **not** mutually exclusive in practice, and the diagnosis must name the *primary* class and the contributing classes. A model that mis-reads a file because the harness truncated the read is primarily an **H** error with a contributing **M** error; fixing it in the model would be treating the symptom.

### 9.4 The decision rule

**`AMB-805`** — **The decision rule, in one procedure:**

1. **Reproduce it.** Not once — the failure rate matters. A 5% failure is a different problem from a 90% failure, and the remedies are different.
2. **Is it the design working?** (Class S.) If the system refused, stopped, or declined as designed, **stop.** Do not train. Do not re-prompt. A system that fails correctly is not broken.
3. **Is it environmental?** (Class E.) Fix or isolate the environment. Stop.
4. **Run the raw-request reproduction** (step 5 of `AMB-802`). This splits H from M/P/T in one test.
   - **The raw request fails too** → the fault is **M** or **P** or **T**.
     - If the raw request is *correct and sufficient* and the model still failed → **M**. Go to step 5.
     - If the raw request is *insufficient* — the harness withheld something the model needed, or the instruction text was unclear → **H** or **P**. Fix it in the harness. (An insufficient request is an H error; an unclear one is a P error.)
   - **The raw request succeeds** → the fault is **H**. The harness's assembly or execution is at fault. Fix the harness.
5. **If it is M, ask: is this a systematic class of failure or an idiosyncratic one?**
   - **Systematic and recurring** → the right first remedy is **training** (layers 2–3) plus a regression case in the held-out suite. Before training, check whether a **mechanism** could prevent it instead (`prompt-pattern-analysis.md` X1) — a capability that is enforced is worth more than a capability that is taught.
   - **Idiosyncratic** → fix with a targeted prompt change, and log it. A prompt change for an idiosyncratic failure is cheap and reversible; a training run is neither.

**`AMB-806`** — The rule in one sentence, for the design review checklist:

> **If the model was asked a bad question, fix the harness. If the model was asked a good question and answered badly, fix the model. If the model was asked a good question and answered reasonably but the answer was hard to use, fix the tool or the prompt. If the model was told to stop and stopped, fix nothing.**

### 9.5 The order of preference for remedies

**`AMB-807`** — When a failure could be fixed in more than one place, the preference order is fixed, and it is the mechanism-first principle X1 made operational:

| Preference | Remedy | Why |
| :- | :- | :- |
| 1 | **A mechanism** — remove the capability, constrain the schema, add a check | A mechanism is a guarantee. Instructions are requests. |
| 2 | **A tool-design change** — make the error unrepresentable | The model cannot misuse an interface that does not permit the misuse. |
| 3 | **A prompt change** — say it better | Cheap, reversible, and it degrades the prompt, which should shrink as the harness grows. |
| 4 | **A harness defect fix** — for class H, this is the only correct answer | It is a bug. |
| 5 | **Training** — for systematic, recurring class-M failures | Expensive, slow, and the correct answer only once mechanisms and tools have been exhausted. |
| 6 | **Nothing** — for class S | The design is working. |

**`AMB-808`** — The precedence of (1) over (5) has a cost that must be stated: a mechanism that hides a capability from the model removes a capability the product could otherwise offer. This is a real trade, not a free win. A read-only mode that removes the edit tool makes the agent unable to edit, and that is the point — but the product must say so rather than present the reduced agent as the full one.

### 9.6 Failure modes specific to the boundary

**`AMB-809`** — Four failure modes are specific to the agent/model boundary and must be in the failure taxonomy:

1. **Model-provoked failure** — the model's tool call was malformed or wrong, and the harness faithfully reported it. The fault is M. The harness's job was to report it accurately, which it did.
2. **Harness-induced failure** — the harness's request or result was wrong, and the model's response was reasonable given what it received. The fault is H, even though the symptom appears in the model's output.
3. **Adapter-induced failure** — the adapter mis-translated a tool call, mangled a stream fragment, or mis-mapped an error category. The fault is in layer 4, and it is the class most likely to be misattributed to the model, because the symptom is a model that appears to have made a mistake. **`AMB-204` (no repairing malformed tool calls) and `AMB-209` (no re-sending committed requests) exist to keep this class small and visible.**
4. **Attribution failure** — a report, a status message, or a UI surface attributed a pair-level result to one side. The fault is in the disclosure discipline, and it is the failure this document exists to prevent. It is diagnosed by §12's register review.

**`AMB-810`** — The diagnostic for class 3 is mechanical: the adapter's request/response pairs are logged, and a test replays a recorded provider response through the adapter and asserts the harness-visible result is identical. A divergence is an adapter defect by definition, because the harness-visible contract is the adapter's output.

---

## 10. The evaluation boundary

### 10.1 The rule

**`AMB-901`** — **Every published number MUST declare which of the three it measures: the model, the harness, or the pair.** A number that does not declare is not publishable.

This is the concrete form of `benchmark-and-evaluation-plan.md` §1.2's three kinds of number (harness metric, external leaderboard figure, human judgement), extended with the model/pair distinction, because this project produces numbers that are *about the model* and that must therefore be labelled as such.

### 10.2 The attribution table

**`AMB-902`** — The catalogue below assigns every metric the project knows how to produce to exactly one of the three classes. It is not exhaustive; it is the set this project has defined so far, and it is the set every report must select from.

| Metric | Class | Why | Where it comes from |
| :- | :- | :- | :- |
| Task success rate under a pinned configuration | **Pair** | It is the interaction of model, prompt, tools, and harness on a task set. | `benchmark-and-evaluation-plan.md` §7 |
| Per-task pass/fail deltas between two configurations | **Pair** | Same, and the pairing is the only thing that makes it interpretable. | §8.4 |
| Failure-mode taxonomy shape | **Pair** | The shape reflects both the model's habits and the harness's error formats. | §1.1 |
| Turns to completion | **Pair** (mostly model) | The loop is the harness's; the number of rounds is the model's. | §4 |
| Cost per successful task | **Pair** | Combines the model's efficiency with the provider's price table. | §9.6 |
| Token counts (input, output, cache read, cache write, thinking) | **Model** (usage) / **Harness** (accounting) | The counts are the provider's; the *ledger* that aggregates them is ours. | `interface-spec.md` §17.3 |
| Time to first token | **Provider** (a fourth class) | It measures the serving stack, not the model and not the harness. | §17.2 |
| Total wall-clock duration | **Pair** | The model's decisions and the harness's execution both consume it. | §17.2 |
| Permission denial count | **Harness** | A property of the rule set, the mode, and the model's requests. **Harness behaviour under a model's stimulus** — the count is harness-side, the stimuli are model-side. | §17.2 |
| Permission denial *rate per tool call* | **Pair** | Depends on both. | — |
| Tool-call error rate | **Pair** | The model's argument construction and the tool's contract. | §3.3 |
| Schema-fingerprint stability across versions | **Harness** | Purely ours. | `benchmark-and-evaluation-plan.md` §6.2 |
| Permission-decision matrix conformance | **Harness** | Purely ours, and testable without a model. | `test-plan.md` §3.4 |
| Compaction correctness (boundary records, monotonic counter, thrash detection) | **Harness** | Purely ours. | `test-plan.md` §3.7 |
| Resume fidelity | **Harness** | Purely ours. | `test-plan.md` §3.5 |
| Determinism (byte-identical output across runs) | **Harness** | Purely ours — the fake model makes it testable. | `test-plan.md` §5 |
| Contract conformance per interface | **Harness** | Purely ours. | `test-plan.md` §3 |
| Injection-defence properties (PR-1 … PR-14) | **Harness** | Purely ours. | `security-plan.md` §7.3 |
| Code-generation pass@1 on a public benchmark | **Model** | Measured without the harness. | `compute-feasibility.md` Gate 1–2 |
| The model's tool-call format correctness rate | **Model** | Measured directly, without the harness's tool layer. | — |
| The model's adherence to the tool-call schema on a held-out set | **Model** | Same. | — |
| The model's recovery rate from a legibly-signalled error | **Model**, when the error format is held constant | It becomes a pair measurement the moment the error format varies. | — |
| The model's context-window discipline (does it compact correctly when told to) | **Model**, with a fixed harness context | Same caveat. | — |
| Our model's "own-model" status | **Not a metric** | It is a provenance fact, established by `AMB-304`, and it is published in the provenance manifest, not in a scoreboard. | §4.3 |

**`AMB-903`** — The class "Provider" appears in the table for time-to-first-token. It is included because it is measurable, it is reported, and it is **not** ours and not the model's — it belongs to the serving stack. A report that presents TTFT next to a pass rate without distinguishing the classes is blending a provider property with a pair property.

### 10.3 The publication requirements

**`AMB-904`** — A published result MUST carry:

| Field | Requirement | Source |
| :- | :- | :- |
| `score` | The value. | — |
| `metric_class` | `model` \| `harness` \| `pair` \| `provider`. | `AMB-901` |
| `model` | The serving model id, including the snapshot where one exists. | `benchmark-and-evaluation-plan.md` §9.3 |
| `model_provider` | The provider. **Required.** | `AMB-011` |
| `model_ownership` | `provider-hosted` \| `keel-own` \| `third-party-local`. | `AMB-011` |
| `model_base` | The base model, where our model is a derivative. | `AMB-011`, `AMB-305` |
| `harness` | The harness name and commit. | `benchmark-and-evaluation-plan.md` §2 |
| `tool_fingerprint` | The schema and description hashes. | §6.2 |
| `system_prompt_sha256` | The prompt hash. | §9.2 RC5 |
| `harness_variant` | `A` \| `B` \| `C`, where a comparison spans harnesses. | §9.4 |
| `tasks` | The task set and its version. | §9.2 RC1 |
| `verifier` | The verifier version. | §9.2 RC11 |
| `cost_basis` | `standard` \| `unknown`, plus the price and its date where known. | §9.6 |
| `stage` | The product stage that produced the result. | `AMB-314` |
| `n` and uncertainty | The sample size and the interval, for any rate. | §10 |
| `controls_passed` | Which of RC1–RC11 held, and which did not. | §9.2 |

**`AMB-905`** — A result **without** `metric_class`, `model_provider`, `harness`, `tool_fingerprint`, and `tasks` **is not publishable**. This mirrors `benchmark-and-evaluation-plan.md` §2's "a result without its L2 harness fingerprint is not a result; it is an anecdote," extended to include the provider.

### 10.4 The self-benchmarking trap

**`AMB-906`** — The project's own task suite is written by the project, for the project, and the model's training data may inadvertently contain the same shapes. `benchmark-and-evaluation-plan.md` §5.4 records this as the "self-benchmarking trap" for M2 onward, and §5.5 records what "held out" does *not* buy. The requirements carry over unchanged.

**`AMB-907`** — Two specific self-benchmarking risks apply to the model programme and are recorded here so that they are handled when the model programme starts, not after:

1. **Task-shape contamination.** If our model is trained on corpora that resemble our task suite's shapes, the suite flatters it. The mitigation is a held-out split with a documented protocol (`benchmark-and-evaluation-plan.md` §5.2, §5.3) and a human-written held-out set, since public benchmarks are contaminated and small models overfit them fast (`compute-feasibility.md` §10, risk 3).
2. **Harness-shaped training.** If our model is trained on tool-call traces generated by our harness, then our harness's tool descriptions and error formats are in its training distribution, and the pair measurement becomes partly a measurement of memorised harness idiom. This is the sharpest form of Direction 2 in `AMB-412`, it is a consequence of S1's deliberate coupling (`AMB-304`, criterion S1-4), and it MUST be declared in every comparison where our model is the arm. **[UNKNOWN]** — the contamination consequence of harness-shaped training has not been measured in this project, and the measurement plan for it does not yet exist. What would settle it: a controlled comparison of our model on the harness it was shaped for and on a harness with materially different tool descriptions and error formats, under the Variant A/B protocol, with the direction of the difference tested. Until that measurement exists, the coupling is declared and the number is treated as an upper bound on the model's portability.

### 10.5 The prohibition on the headline number

**`AMB-908`** — A published headline MUST be either a **harness** metric (clearly attributed to the harness) or a **paired** metric (with both sides pinned). A headline that is a model-only number is permitted **only** if it was measured without the harness and is labelled as such, with the caveat that a model-only number says nothing about agent quality.

**`AMB-909`** — The reasoning is worth stating, because it is the argument a marketing team will push against: a model-only number is the *most* flattering and the *least* relevant. A model that scores well on code generation and cannot be driven by an agent is, in the language of `compute-feasibility.md` Gate 3, "a text model that happens to emit code" — and Gate 3 is explicit that this is a **stop condition**: *the agent harness on R1/R2 does not complete end-to-end tasks* means the model programme stops, and the correct engineering decision is to rent and spend the remaining budget on the harness.

---

## 11. Interface contracts

### 11.1 The rule

**`AMB-1001`** — The **authoritative** definition of every interface is `interface-spec.md`. This section does **not** duplicate it. It records, for each boundary interface, **who owns it**, **what the other side is forbidden to assume**, and **the compatibility rule when either side changes**. The link is the contract; the row is the responsibility.

### 11.2 The boundary interface table

| # | Interface (`interface-spec.md` §) | Owned by | The other side MUST NOT assume | Compatibility rule when one side changes |
| :- | :- | :- | :- | :- |
| **IF-1** | **Model adapter** (§12) | Layer 4 (inference and adapters) | That the adapter can repair a malformed tool call, synthesise a missing capability, or influence a permission decision. | A new adapter MUST satisfy the existing `ModelAdapter` type without changing it. A change to the type is a **major** change: the lint rule (`AMB-233`) catches provider-specific leakage, and every registered adapter is re-conformanced. |
| **IF-2** | **Agent turn** (§3) | Layer 5 (orchestration) | That a turn's outcome is a statement about model quality. | The `TurnRequest`/`TurnOutcome` shape is stable. Additive optional fields are a **minor** change; removing or retyping a field is **major** and requires a compatibility path for the headless envelope. |
| **IF-3** | **Tool interface and tool-result envelope** (§4) | Layer 6 | That a tool performs its own permission check, or that `content` and `toolUseResult` are the same string. | The dual representation (`interface-spec.md` §4.4) is load-bearing for the model: `content` is the model's copy, `toolUseResult` is the audit copy. A change to either is **major** and requires a re-audit of the model-facing channel. |
| **IF-4** | **Permission decision interface** (§5) | Layer 6 | That a denial is advisory, or that a hook can widen a decision. | The evaluation order is a single, versioned thing. A change to the order is the **hardest to roll back** in the project (`implementation-plan.md` §8 notes it is baked into saved user configuration and audit records); it requires a **migration** that rewrites saved rules, and the audit record format carries the evaluation-order version it was produced under. |
| **IF-5** | **Rule and rule-set model** (§6) | Layer 6 | — | The rule *syntax* is a compatibility surface (user-authored text). The rule *semantics* are ours. A syntax change is **major** and needs a converter. |
| **IF-6** | **Hook interface** (§7) | Layer 6 / X1 | That a hook verdict can reach Tier 2 or change the permission mode. | Hook input is data; an unknown field is ignored; a verdict outside the vocabulary is rejected as a malformed hook, not honoured (PR-7). Additive payload fields are **minor**. |
| **IF-7** | **MCP client interface** (§8) | Layer 6 | That a server's self-description or response can widen a decision, load another server's tools, or change the mode (PR-6). | The `mcp__<server>__<tool>` naming convention is a compatibility surface. Server-side changes are outside our control; the isolation guarantees (three channels) are not negotiable. |
| **IF-8** | **Skill and slash-command registration** (§9) | Layer 6 / Layer 8 | That a skill body is an instruction channel, that a skill can widen the tool set, or that a substituted argument is re-scanned. | The frontmatter field names are a compatibility surface. A new field is **minor** and MUST be optional. The two-tier loading and the injected-command policy are **not** negotiable and are not changed by a frontmatter change. |
| **IF-9** | **Subagent spawn and join** (§10) | Layer 5 | That a subagent's report is authoritative, or that a subagent can exceed the caps. | The caps, the depth limit, and the worktree isolation are invariants. The report framing as non-authoritative is invariant. |
| **IF-10** | **Session and state interface** (§11) | Layer 8 | — | The JSONL transcript layout and the per-project directory slug are compatibility surfaces. A change is **major** and needs a reader for the old format. |
| **IF-11** | **Config and settings interface** (§11, §13) | Layer 8 | That any key can widen a control, or that a repository can opt itself into a permissive mode. | The key names, the scope names, and the merge semantics are compatibility surfaces. The **monotonic restriction lattice** is ours and is not changed by a key rename. A new key MUST NOT name a Tier-2 behaviour — the registry-enumeration test fails if one does (`security-plan.md` §5.4). |
| **IF-12** | **Context-compaction interface** (§14) | Layer 8 | That a compaction is complete without a boundary record. | The boundary record's shape is load-bearing for resume. A compaction that leaves no boundary record is not complete (`interface-spec.md` §14.8). The auto-compact window's valid range is a compatibility obligation. |
| **IF-13** | **Event-stream interface** (§15) | Layer 2 (X2, telemetry) | That the stream ends at the terminal result. | The `type`/`subtype` vocabulary is a compatibility surface. **This document's disclosure requirements add required fields to the `init` event** (`AMB-011`) — `model_provider`, `model_ownership`, `model_base` — and those are **major** changes to consumers that validate the field set, and are **minor** for consumers that follow the open-set rule. The `capabilities` array is an open set: a consumer MUST ignore unknown entries. |
| **IF-14** | **CLI surface** (§16) | Layer 5 | — | Flag names and the output-mode names (`stream-json`, `json`, `text`) are compatibility surfaces. A new flag is **minor**. |
| **IF-15** | **Headless structured output envelope** (§17) | Layer 2 (X2) | That `usage` is the total spend, or that `result` being present means success. | The `subtype` enum is the **authoritative** failure discriminator, and `result` MUST be absent on every non-`success` subtype. The envelope's `modelUsage[*]` fields are where the disclosure requirements land (`AMB-013`). |

### 11.3 The change rules for the boundary

**`AMB-1002`** — Three change rules apply to every interface above.

| Rule | Statement | Identifier |
| :- | :- | :- |
| **The model side may not require a harness change** | If our own model needs a feature the harness does not have, the harness adds it **generically**, or the capability is declared absent for every model (`AMB-212`). A model-specific special case in the harness is a boundary violation, because it makes the harness a function of one model and breaks the fairness of any comparison against that model. | `AMB-1003` |
| **The harness side may not require a model change** | A harness improvement that requires model cooperation is a *prompt* or *tool* change, and it is attributed to the harness (`AMB-408`). | `AMB-1004` |
| **A disclosure field is added, never removed** | The disclosure fields (`model_provider`, `model_ownership`, `model_base`) are the mechanism for `AMB-001`. A version that removes one is a **major** regression, and the disclosure register's review treats its absence as a blocking finding. | `AMB-1005` |

**`AMB-1006`** — The `model_base` field deserves a specific note. It exists because a fine-tune of someone else's model is a real and useful artefact, and because the phrase "our model" is only truthful for one of the two cases. Publishing the base model is the cheapest way to keep the phrase honest, and it costs one field.

**`AMB-1007`** — The `stage` field has the same status. It is derived, it travels with every result, and its removal is a regression.

### 11.4 What is *not* an interface

**`AMB-1008`** — The following are **not** interfaces, and treating them as interfaces is how a boundary leaks:

- The **system prompt's prose**. It is ours, it is not published, and it changes whenever the harness changes. Its *hash* is a benchmark field, not an interface.
- The **tool descriptions' prose**. Same.
- The **internal layer names**. They are architecture, not contract.
- The **adapter's internals** — endpoints, auth, retries. Only the boundary shape is a contract.
- **The provider's wire format.** It is consumed through the adapter and is explicitly out of scope for the interface spec (`interface-spec.md` §1).

---

## 12. Disclosure register

### 12.1 Purpose and method

This register lists **every place the product could mislead**, the exact truthful wording required in each, and the mechanism that enforces it. It is a checklist: a reviewer walks it and asks, per row, "is the wording present in the shipped artefact?"

**`AMB-1101`** — A surface that is not in this register is a surface whose disclosure wording has not been decided. Adding a user-visible surface **requires** adding a row here. The register is the enforcement mechanism for `AMB-001` in the same way the lint rule is the enforcement mechanism in code.

**`AMB-1102`** — The review of this register happens at every stage promotion (`AMB-306`, S2-6) and at every release. A row that cannot be satisfied in the shipped artefact is a **blocking finding**, not a warning.

### 12.2 The register

| # | Surface | The misleading version | The **required truthful wording** | Enforcement mechanism | Owner |
| :- | :- | :- | :- | :- | :- |
| D-01 | **Model picker** | `Sonnet 5.5` | `Sonnet 5.5 (via Anthropic)`; for our own: `keel-1.5b (Keel's own model, based on <base>)` | The picker component cannot render an entry without a provider string (`AMB-035`). | Front end |
| D-02 | **Session-start banner** | `Model: Sonnet 5.5` | `Model: Sonnet 5.5 (via Anthropic)` / `Model: keel-1.5b (Keel's own model, served locally)` | The banner renderer requires the attribution (`AMB-036`); a lint rule fails the build otherwise (`AMB-037`). | Front end |
| D-03 | **`init` event** | `model: "Sonnet 5.5"` | Adds `model_provider`, `model_ownership`, `model_base` as **required** fields (`AMB-011`). | The type requires them; the event is invalid without them. | Protocol |
| D-04 | **Headless envelope** | `modelUsage` with no provider | `modelUsage[*].provider` and `.canonicalModel` retained; `costBasis: "unknown"` preserved (`AMB-013`). | Field is required by the envelope type. | Protocol |
| D-05 | **Assistant event** | `message.model` with no provider | `message.provider` retained alongside `message.model` (`AMB-012`). | Field is required by the event type. | Protocol |
| D-06 | **Transcript** | A transcript that does not say which provider served each turn | Each assistant turn records the serving model and its provider (`AMB-016`). | The transcript writer requires the field; the transcript is the audit artefact and must survive being read by a third party. | State |
| D-07 | **Per-request log line** | `POST /v1/messages 200 in 3.2s` | Includes `model=<id>` and `provider=<provider>` at the same verbosity (`AMB-017`). | Log-format test. | Observability |
| D-08 | **Cost panel / status line** | `$0.00` for an unpriced model | `costBasis: unknown` is shown as **"token usage only"** or equivalent — never as a monetary zero (`AMB-015`). | The status-line payload carries the basis; a test asserts the human-facing string. | Front end |
| D-09 | **"Offline" / "private" / "on-device" claims** | "Your code never leaves your machine" while a provider-hosted model is in use | "Your code never leaves your machine" **only** in a session whose `model_ownership` is `keel-own` or `third-party-local`. For a provider-hosted session: "Your repository contents and prompts are sent to <provider> to run the model." | A session-level check reads `model_ownership` before the claim may be rendered (`AMB-028`). | Product |
| D-10 | **"No API cost" / "free" claims** | "Free forever" | For a provider-hosted model: "Uses <provider>'s API; you pay your provider's rates." For our own model: "No per-token API cost; you pay for the hardware and the energy." (`AMB-029`) | Same mechanism as D-09. | Product |
| D-11 | **Benchmark tables** | A single `Model` column | Every result cell carries the model id and the provider; every comparison table carries the harness variant (`AMB-008`, `AMB-507`). | The report generator refuses to emit a table missing the fields (`AMB-038`). | Evaluation |
| D-12 | **Headline claims** | "Our agent solves 61% of tasks" | Either a harness-attributed metric or a paired metric with both sides pinned (`AMB-010`, `AMB-908`). | The report generator refuses a headline without `metric_class`. | Evaluation |
| D-13 | **Comparison to another product** | "We outperform Claude Code" | "Product comparison, not model comparison" appears in the results section, with the harness variant attached, when the arms ran under different harnesses (`AMB-009`, `AMB-512`). | The §8.7 comparison template has the required sentence as a non-optional field. | Evaluation |
| D-14 | **Documentation landing page** | "An independent AI coding agent" | "Keel is a coding agent harness. The behaviour comes from the model it drives; on a provider-hosted model, that intelligence is the provider's." (`AMB-005`) | Copy review at release; the disclosure register is re-signed. | Docs |
| D-15 | **Marketing / landing page** | A quality claim with no model named | Every agent-quality claim names the model or says "model-dependent" in the same sentence (`AMB-007`). | Copy review; a checklist item, not automatable. | Product |
| D-16 | **Model card / model page** | Describing a fine-tune as "our model" | "Keel's model, based on <base-model>." The base is named in the first sentence (`AMB-305`, `AMB-1006`). | Copy review; `model_base` is required in the metadata. | Model programme |
| D-17 | **"Our AI" / "our intelligence"** | Used for a provider-hosted model | **Forbidden** (`AMB-020`). | Copy review; a copy-lint checklist item; the model picker and banner never use it. | Product |
| D-18 | **"Our agent" as the subject of a quality claim** | "Our agent is more reliable" | "The agent — <model-id> via <provider>, driven by Keel's harness — is more reliable." Or "Keel's harness is more reliable at…" when the change was harness-side (`AMB-021`, `AMB-408`, `AMB-510`). | Copy review. | Product |
| D-19 | **Skill and plugin descriptions** | A skill that claims to be "official" or "by the Keel team" | The skill's source and trust class are visible in the listing (`interface-spec.md` §9.7, §9.8). | The skills registry carries the source; the listing renders it. | Extensions |
| D-20 | **MCP server listings** | A server described as part of Keel | The server's name, its source, and its status are shown separately from Keel's own tools (`interface-spec.md` §8.3, §8.9). | The init event's `mcp_servers` carries `{name, status, source}`. | Extensions |
| D-21 | **Error and diagnostic messages** | A provider error presented as a Keel internal error | Provider-origin errors name the provider and the category; the provider-independent category enum is used (`interface-spec.md` §12.7). The `Error: ` prefix separates the audit copy from the model copy. | The adapter's error mapping; the diagnostic formatter requires the category. | Observability |
| D-22 | **Issue tracker and commit messages** | "Fixed the model" for a prompt change; "Fixed the prompt" for a harness bug | The failure class from §9.3 is named in the issue: model / harness / prompt / tool-design / systemic / environmental. | Team convention, with the taxonomy in this document as the reference. | Engineering |
| D-23 | **The "no independent model" claim** | Claiming independent model intelligence at S0/S1/S2 | **Forbidden** at S0, S1, and S2 (`AMB-303`). The stage string is published and the claim is checked against it. | The stage is derived and published; the copy review reads it. | Product |
| D-24 | **Third-party model comparisons in the docs** | "Our model beats X" | "Our model, driven by Keel's harness, scored <n> on <task set v> under harness variant <A/B/C>; X, driven by <their harness>, scored <m> on the same set. The two are not directly comparable." (`AMB-025`) | The comparison template; the report generator. | Evaluation |
| D-25 | **Screenshots and demos** | A demo showing output with no provider visible | A demo that includes a provider-hosted model shows the provider in the frame (the banner is visible in a TUI demo by default). | Copy review; the banner is always on screen. | Product |
| D-26 | **The "independent AI coding agent" project framing** | The repository description | "An independent open-source coding agent *harness*. The model is a separate, swappable layer." | Copy review. | Product |
| D-27 | **Cost of a provider-hosted run** | Reporting only `total_cost_usd` | Report `total_cost_usd` **and** the token counts, and the basis, and the price date (`AMB-509`). | The envelope's `modelUsage` carries the basis; the report template requires the date. | Evaluation |
| D-28 | **"Our harness" vs "our model" in a changelog** | "Keel 0.9: 30% better task success" | The changelog entry names the changed layer: harness, prompt, tools, permissions, or model (`AMB-510`). | Team convention. | Engineering |
| D-29 | **Subagent and multi-agent claims** | "Keel runs 50 agents in parallel" | The claim is about the harness's concurrency capability and names the model that runs each agent (`AMB-502`). | Copy review. | Product |
| D-30 | **The "autonomy" claim** | "Fully autonomous" | "Runs unattended up to your turn and budget limits, with the permission rules you set. It is not autonomous: every action passes through Keel's permission engine." (`AMB-027`) | Copy review. | Product |

### 12.3 The review procedure

**`AMB-1103`** — The register is reviewed as follows:

1. **At every stage promotion** (`AMB-306`), because the wording depends on the stage.
2. **At every release**, as a blocking checklist.
3. **Whenever a user-visible surface is added**, as a register amendment before the surface ships (`AMB-1101`).
4. **Whenever a benchmark report is produced**, against the reporting fields in §10.3.

**`AMB-1104`** — The register's own failure mode is the one it is designed to prevent: a disclosure that is present but buried, present but hedged, or present in one surface and absent in another. The mitigation is that the register names the surface and gives exact wording, and that the mechanisms — a required field, a component that cannot render without it, a generator that refuses to emit — are structural where a mechanism exists (`AMB-032`).

---

## 13. Open questions

These are the questions this document **cannot** answer. They are ordered by how much they matter, and each carries what would settle it.

### 13.1 OQ-1 — The fully-offline user, before our own model exists

**The question.** A user wants a coding agent that works with no network egress at all: their code never leaves the machine, no telemetry, no provider calls. Our own model does not exist at S0. What do we give them?

**The candidate answers, and why each fails or works.**

| Option | Description | Assessment |
| :- | :- | :- |
| (a) | Ship nothing for this user until S3. | **Rejected.** A user with a hard air-gap requirement is exactly the user who needs the harness's permission model, its determinism, its transcript, and its audit trail. Deferring them to S3 — which `compute-feasibility.md` puts at an R2-scale cost of $13k–$134k and 3–39 days per run, and which may never be reached — defers the whole product for a class of user whose *problem* is the harness's problem. |
| (b) | Offer a local model (a downloaded open-weights model on the user's own hardware) and call it "Keel's model". | **Rejected as wording, and it is a serious trap.** A third-party open-weights model is not our model (`AMB-304` fails element 1 and element 3), and calling it ours would be the exact misrepresentation this document exists to prevent. It is, however, a legitimate **deployment** of the harness, and the honest label is `third-party-local` — which `AMB-011` already provides. |
| (c) | Offer the harness with a **text-only** local model, and let the tool-calling come from the harness. | **Rejected.** The harness cannot supply the tool-call decision (`AMB-230`, `AMB-501`). A text-only agent is a chat product with a file browser, not a coding agent. Weakening the product and calling it the same product is the failure this document is about. |
| (d) | Offer the harness with a local model, honestly labelled, and support a **model-agnostic** user contract so that swapping in Keel's own model later is a one-line config change. | **This is the answer we are willing to live with.** |

**`AMB-1201` — The answer we are willing to live with.** A fully-offline user at S0 or S1 gets:

1. **The harness, in full**, with every layer above the adapter unchanged. The permission engine, the Tier-2 interlock, the tool surface, the transcript, the compaction, the subagents, the test suite — all of it, and all of it ours.
2. **A local model, honestly labelled `third-party-local`**, with the provider field reading the model's actual origin. If it is a fine-tune of a named base, `model_base` names the base.
3. **An explicit statement of what it is**: "Keel is driving <model-id>, a local model from <origin>, which is not Keel's own model. Keel's own model is not yet released. What Keel contributes is the harness: the permission model, the tools, the safety envelope, the transcript, and the determinism."
4. **A documented, tested path to our own model**: when `keel-own` becomes available, the same configuration selects it, and the disclosure surfaces update with it. The offline user is then a first-class beneficiary of S3, not a user who was sold a substitute.
5. **An honest statement of the limits**: a local model of the size this project's hardware can run will be weaker than a frontier hosted model on hard coding tasks, and the task suite's results for that configuration will show that. We do not present the offline configuration as equivalent to the hosted one.

**`AMB-1202`** — The uncomfortable part of this answer, stated plainly: **at S0, the offline user gets a materially less capable agent than the hosted user, and we should not pretend otherwise.** What they get that is *better* is the determinism, the auditability, the permission model, and the fact that nothing leaves the machine. The honest framing is a trade, not a win.

**`AMB-1203`** — What we are **not** willing to live with: a local model silently presented as Keel's own; an "offline" badge on a configuration that egresses; or a claim that the offline configuration matches the hosted one on task success. Each of these is a D-row violation in §12.

**`AMB-1204`** — **[UNKNOWN]** — The magnitude of the quality gap between a local model runnable on this project's hardware and a frontier hosted model, measured on this project's own task suite, is **not known**. The hardware facts are known (AMD Ryzen 7 5700U, 8c/16t, 13.85 GiB RAM, AMD iGPU 2 GB, no CUDA, torch 2.14.1+cpu, measured 1.72e11 FP32 FLOP/s, 159.2 GB free disk, Windows 11) and `compute-feasibility.md` §11 records that R2 and above are impossible on this hardware on both compute and memory (27 GB of state against 13.85 GiB of RAM), and that R0 (30M) and R1 (360M) are the only rungs that fit. What would settle it: the R0/R1 training runs and a paired evaluation of the resulting checkpoints under the §9.2 controls. Until then, the gap is described qualitatively and no number is published.

**`AMB-1205`** — A related **[UNKNOWN]**: whether a model of the R1 class (360M) can be driven by this harness through multi-step tasks at all. `compute-feasibility.md` Gate 3 names this as the stop condition — *a model that cannot be driven by an agent is not a code model for our purposes; it is a text model that happens to emit code* — and Gate 2 is the point at which the question gets its first evidence. This is the single most important unknown in the model programme, and it is why Gate 3 is called "the real fork."

### 13.2 OQ-2 — The §D.4 question, and what it changes here

**The question.** `licensing-and-provenance-review.md` §12 (OPEN-Q1) asks whether Anthropic's Commercial Terms §D.4 "prohibits attempting to access the Services to build a competing product or service" reaches *running* a provider service as our product's runtime model provider.

**Why it is listed here and not only there:** the answer changes **which providers are named in our disclosure surfaces at S0/S1** — and therefore what the disclosure wording says. The review's recommended default is option (b): build the Phase-1 slice against a **different, non-Anthropic provider** and keep the Anthropic path out of the product entirely, with written comfort as an optional accelerator for evaluation only.

**Status:** unresolved, and not resolvable by this project. The review's stated position is that the implementation plan is built so the answer changes nothing we do (`AMB-311`).

**`AMB-1206`** — The disclosure consequence, stated so it is not decided late: **the provider name in D-01, D-02, D-03, and D-14 is a variable, and the wording templates are written to accommodate any provider name.** The product's disclosure discipline does not depend on which provider is used, and the choice of provider is a legal decision, not a design decision.

### 13.3 OQ-3 — What the model's own tool-call competence must be

**The question.** How much of the harness's work can be moved *out* of the harness and *into* the model — and should it be?

**The tension.** A model with excellent tool-call competence needs less schema engineering from the harness. A model with poor tool-call competence needs the harness to constrain it — through schema design, through mechanism, through refusal. Since we will eventually train our own model, the harness's design and the model's training are coupled (S1 criterion S1-4; `AMB-304`).

**`AMB-1207`** — The project's working position, and it is a position rather than a settled fact: **the harness must be designed for the weakest model we intend to support, and the model programme must not be allowed to justify weakening it.** A harness that is only safe with a strong model is not a harness; it is a harness plus an assumption. The mechanism-first discipline (X1) is what makes a weak model survivable, and it is also what makes the harness portable to our own model later.

**`AMB-1208`** — **[UNKNOWN]** — the tool-call competence of our own future model. There is no measurement, because there is no model. What would settle it: a direct evaluation of tool-call schema adherence and recovery rate, measured without the harness, at each training checkpoint, against a held-out set. The `compute-feasibility.md` Gate 1 and Gate 2 evidence requirements are the place this gets measured first.

### 13.4 OQ-4 — How much context the harness should withhold, and who decides

**The question.** The harness assembles the context (`AMB-601`), and the tool descriptions and instruction attachments are effectively prompt. How much of the judgement about *what to tell the model* should be automated, and how much should be exposed to the user?

**The tension.** A harness that hides everything relevant gives the model a poor request and the user no recourse. A harness that tells the model everything defeats the budget. A harness that lets the user tune it moves prompt engineering to the user, who may not know what they are doing.

**`AMB-1209`** — The working position: the harness decides the *categories* (§7.3) and the *mechanisms* (capability matrix, schema removal, compaction), and the **user may adjust the content within a category** — their own instruction files, their own memory, their own permission rules. The harness does not let the user change the *order* or the *precedence*, because those are the safety properties.

**`AMB-1210`** — **[UNKNOWN]** — whether user-tunable context is a net positive for task success. The project's own task suite cannot answer this without a user-study design that does not exist. What would settle it: an A/B study on the task suite with a randomised context-tuning treatment, with the same model and the same harness in both arms. Until then, the design defaults to the safer option and the question is recorded rather than answered.

### 13.5 OQ-5 — Whether the "harness-variant" problem will be soluble for our own model

**The question.** `benchmark-and-evaluation-plan.md` §9.4 establishes that Variant A (common harness) is preferred and isolates the model, and that Variant B (harness-matched emulation) is the strongest form when the independent harness cannot host the reference model natively. For **our own model**, which will natively run in our own harness, Variant A is trivially available — and therefore, is the comparison meaningful?

**The tension.** A model that is co-adapted to our harness (Direction 2, `AMB-412`) will look better in it. Variant A is the *preferred* variant and it is also, for a co-adapted model, the *flattering* one. The controls (RC3, RC4, RC5 — identical schemas, descriptions, and system prompt) are satisfied by construction, and yet the model has been shaped for exactly those artefacts.

**`AMB-1211`** — The working position: **Variant A is the correct protocol and the co-adaptation is disclosed as a declared difference, exactly as `benchmark-and-evaluation-plan.md` §9.3's "permitted differences" table handles a native tool-call format.** The measurement of the co-adaptation effect (`AMB-907`) is the thing that is missing.

**`AMB-1212`** — **[UNKNOWN]** — the size of the co-adaptation effect. No measurement exists. What would settle it: our model evaluated under Variant A and under a deliberately different harness (materially different tool descriptions, error formats, and system prompt), with the direction of the difference tested for consistency, per `AMB-907` and `benchmark-and-evaluation-plan.md` §9.5.

### 13.6 OQ-6 — What the register cannot cover

**The question.** The disclosure register covers the product's *surfaces*. It cannot cover the product's *conversations* — a sales call, a conference talk, a Slack message, a README badge someone else writes, a user's own blog post.

**`AMB-1213`** — The honest position: **the register is necessary and not sufficient.** The mechanism that covers the surfaces does not cover the speech. What the register can do is make the *material* available — a one-paragraph statement of what the product is, what the model is, and who owns the intelligence — so that anyone describing the product has the truthful sentence at hand. That one paragraph is D-14 and D-15, and it is the highest-leverage item in the register.

**`AMB-1214`** — A related residual: **a user can still misuse the product's output** — for example, publishing our agent's output as its own work, or using our agent to write a competitor's code. Nothing in this document governs that, and it is out of scope.

### 13.7 OQ-7 — The measurement of the disclosure discipline itself

**The question.** How do we know the disclosure discipline is working, beyond reviewing the register?

**`AMB-1215`** — The proposed measurement, which is cheap and mechanical:

| Measurement | What it detects | Mechanism |
| :- | :- | :- |
| Surface coverage | A user-visible surface that renders a model id without a provider | A UI-surface scanner; the lint rule (`AMB-037`). |
| Report completeness | A published report missing a required attribution field | The report generator's refusal (`AMB-038`). |
| Consumer independence | Whether a downstream consumer *can* determine the provider | A test that reads only the `init` event and the envelope and asserts the provider is recoverable. |
| Stage consistency | A surface's wording inconsistent with the current stage | The stage-comparison check at promotion. |

**`AMB-1216`** — **[UNKNOWN]** — no baseline measurement of disclosure completeness exists yet, because no product exists. What would settle it: running the surface scanner against the first release candidate.

### 13.8 OQ-8 — The naming problem

**The question.** The product needs a name that does not imply independent model intelligence, and the working codename "Keel" is not settled.

**`AMB-1217`** — The constraint the name must satisfy: it names **the harness**, not the intelligence. Any name that reads as an AI — as opposed to a tool, a vessel, a mechanism, a system — will be read by a user as claiming a mind. The name is therefore a disclosure surface (`AMB-1101`), and it is in the register even though it is a single word.

**`AMB-1218`** — **[UNKNOWN]** — no name has been tested with users for implied-claim effects. What would settle it: a comprehension test in which participants read a product description under candidate names and report what they think the product's intelligence is. This is a real, cheap study, and it is not a priority until there is a product to describe.

---

## 14. Closing statement

### 14.1 The rule, restated

> **THE EXISTENCE OF A PROVIDER ADAPTER MUST NEVER BE REPRESENTED AS INDEPENDENT MODEL INTELLIGENCE.**

Everything above is an attempt to make that sentence **true in the artefact** rather than true in the document. The mechanisms are the required fields, the components that cannot render without the attribution, the generator that refuses to publish an unattributed score, the lint rule that fails the build, the stage string, and the register.

### 14.2 The two accounting summaries

**What the harness contributes** (§5): permission evaluation, the Tier-2 safety envelope, tool execution, context compaction, session persistence, subagent orchestration, the test suite, the sandbox, the tool surface, the context assembly, the loop and its limits, the audit trail, the disclosure surface. Thirteen of these survive a model swap unchanged. The one place both sides contribute is the compaction summary — the harness selects what to preserve, the model writes the text.

**What the model contributes** (§6): the plan, the code, the tool-call decision, failure recovery, language understanding, judgement about relevance, knowing when to stop, the natural-language output, and the compaction summary's text.

The product is the pair. The disclosure rule exists so that the pair is never mis-sold as half of itself.

### 14.3 What a reviewer should take away

1. **The disclosure is structural, not editorial.** If the provider is a required field, the disclosure cannot be forgotten in a hurry. If it is a habit, it will be lost the week before a launch.
2. **The harness is most of the product, and that is not the same as the product being ours.** The permission model, the transcript, the safety envelope, the determinism, and the audit trail are unambiguously our work. The judgement is not, until S3.
3. **A model swap changes the product.** A weaker model behind the same adapter is a different product, and the product's description must change with it (`AMB-222`).
4. **The evidence for a claim must name the pair.** Model, provider, harness fingerprint, prompt hash, tool schemas, task set, verifier, cost basis, stage. A number without those is an anecdote with a decimal point.
5. **The failure diagnosis is mechanical.** Reproduce, then swap one variable, then replay the raw request. The model is blamed only after the harness is cleared.
6. **The register is the checklist.** Walk it per release, per stage promotion, and per new surface. A row that cannot be satisfied is a blocking finding.

### 14.4 Cross-reference index

| This document's topic | Authoritative source |
| :- | :- |
| The layer stack, the dependency rule, the provider abstraction | `architecture.md` §2, §5, §17 (ADRs 004, 008, 009) |
| The fifteen interfaces, the adapter contract, the compaction interface, the event stream, the headless envelope | `interface-spec.md` §3–§17 |
| The two-tier safety model, the injection rules PR-1…PR-14, the Tier-2 unoverridability argument | `security-plan.md` §5, §7 |
| The fifteen subsystems and their per-feature acceptance criteria | `feature-checklist.md` (S1–S15) |
| Metric attribution, the reference-comparison protocol, the three kinds of number | `benchmark-and-evaluation-plan.md` §1, §6, §9 |
| Principles X1–X18, and in particular X1 "enforce by mechanism, not by instruction" | `prompt-pattern-analysis.md` |
| The rung ladder, the gates, the local hardware, the wall-clock constraint | `compute-feasibility.md` §2, §9, §10, §11 |
| The §D.4 constraint, the licence posture, the training-data prohibition | `licensing-and-provenance-review.md` §2, §8, §12 |
| The phases, the milestones, the rollbacks, the "not our code" statement | `implementation-plan.md` §3, §6, §8, and `architecture.md` §16 |
| The test taxonomy, the determinism contract, the attack matrix | `test-plan.md` §2–§7 |

### 14.5 Document control

| Field | Value |
| :- | :- |
| Document | `agent-and-model-boundary.md` |
| Part | 6 of the planning deliverable set |
| Status | Normative planning document. No implementation exists. |
| Depends on | `architecture.md`, `interface-spec.md`, `security-plan.md`, `feature-checklist.md`, `benchmark-and-evaluation-plan.md`, `prompt-pattern-analysis.md`, `compute-feasibility.md`, `licensing-and-provenance-review.md`, `implementation-plan.md`, `test-plan.md`, `agent-evidence.md` |
| Review triggers | Every stage promotion; every release; any new user-visible surface; any published benchmark |
| Requirement identifiers | `AMB-001` … `AMB-1218`, all stable, all walkable as a checklist |
| Next revision trigger | The first implementation of the adapter boundary, or the first published benchmark report, whichever comes first |













# Licensing and Provenance Review

**Project:** independent clean-room coding agent + independent LLM
**Date:** 2026-10-21
**Scope:** every third-party artifact this project intends to consult, study, or incorporate — the system-prompt research collection, the REA toolchain, the reference product's documentation, and the candidate corpora and weights for model training.
**Status:** planning document. No source code has been written. No artifact has been incorporated into a product. This review is a gate, not a post-hoc summary.

---

## 0. Executive summary — the five things that must be understood

| # | Finding | Consequence |
| :- | :- | :- |
| **L1** | The prompt collection's root `LICENSE` is **CC0 1.0** — but it was applied **retroactively on 2026-05-28** to a collection that had been public under MIT since 2025-05-03, after 524 commits | CC0 on the *collection* is **not** a grant of rights over the *captured content*. See §3. |
| **L2** | Six of the captured Anthropic skill bundles carry **Anthropic's own restrictive licence**, inside the CC0 repo, explicitly forbidding extraction, reproduction, derivative works, and redistribution | Those files are **excluded** from use. A CC0 file in the tree does not override a narrower licence attached to the material. See §4. |
| **L3** | Anthropic's **Commercial Terms §D.4** prohibits using the Services "to build a competing product or service, including to train competing AI models" | Using the reference product as a data source or a teacher for our own model is **blocked** without separate written authorisation. This is the single most consequential constraint in the project. See §2. |
| **L4** | The captures are **corroborated for the Claude 5.x family** (86–92 % of Anthropic's *own published* prompt text appears verbatim in the captures) but **not** for the 4.x family (14–29 %) | The 5.x captures are **high-confidence** as faithful to a real served prompt. The Claude Code captures specifically remain **uncorroborated** — no official Claude Code prompt is published. See §5. |
| **L5** | REA is **MIT** with an explicit responsible-use disclaimer that itself forbids "copying proprietary software or reproducing its protected code and assets" and "evading the usage policies or safety measures of AI model providers" | REA is **safe to use as a tool** for our own artifacts and for non-Anthropic targets, and its **own MIT-licensed code and docs are reusable** — but using it against Anthropic binaries would breach both its licence posture and the Anthropic terms. See §6. |

**Bottom line.** The project can proceed on the plan as written — *study for principles, reimplement independently, never copy* — and the licence position is in fact **stronger** than it looks, because the corroboration result (L4) means we can treat the 5.x captures as a faithful specification rather than a rumour, and because the corpus we would train on need not come from these captures at all.

**One question remains genuinely open** and is recorded in §12: whether the *clean-room discipline we are adopting* is sufficient to answer the Anthropic Commercial Terms §D.4 "build a competing product" clause, or whether it needs a written comfort letter. We do not answer that here; we are not qualified to, and the plan does not depend on the answer (§12.1).

---

## 1. Method and limits of this review

### 1.1 What was examined

| Artifact | Access method | Extent |
| :- | :- | :- |
| `asgeirtj/system_prompts_leaks` | Read-only blobless `git clone`; `git show HEAD:<path>`; full `git log` (866 commits) | Structural: tree, licence files, licence history, README, provenance statements, the Anthropic subtree, the `official/` subtree. Content: 11 official-vs-capture comparisons, 7 Claude Code capture headers, 9 embedded licence files, the `## Tools` region of one capture. |
| `morluto/rea` | Read-only blobless `git clone`; `git show HEAD:<path>` | `LICENSE`, `DISCLAIMER.md`, `THIRD_PARTY_NOTICES.md`, `package.json`, `licenses/`, `AGENTS.md`, `docs/process-capture.md`, `.agents/skills/`. |
| Anthropic Commercial Terms | `WebFetch` of `https://www.anthropic.com/legal/commercial-terms` | §D.4 Use Restrictions; B. Customer Content; F. Intellectual Property; E.2 Obligations of Parties. |
| Anthropic system-prompt release notes | `WebFetch` of `https://platform.claude.com/docs/en/release-notes/system-prompts/overview` | The published product list and the statement that these prompts do not apply to the Claude API. |
| Prior investigation | `agent-reference-shots/TERMS-NOTES.md`; `agent-evidence.md` §2 | The terms basis established on 2026-10-21, before inspection. |

### 1.2 What this review does **not** do

- It is **not legal advice.** It is an engineering risk register with citations, produced by an engineer, to be reviewed by counsel before any incorporation decision.
- It does **not** determine copyright ownership of any specific captured file. It identifies the licence *stated* in each artefact and the *conflict* between them.
- It does **not** evaluate non-Anthropic dataset licences (CodeSearchNet, SWE-bench, the Stack, etc.) in detail — those are inventoried with pointers in §9 and must each clear this same gate before use.
- It reached no conclusion on any question of law. Where the answer depends on jurisdiction, on facts not in evidence, or on a court or regulator, it is listed in §12 as open.

### 1.3 Classification used throughout

| Tag | Meaning |
| :- | :- |
| **OBSERVED** | Directly verified in a file during this review, with the command or path that shows it. |
| **INFERRED** | A conclusion drawn from observed facts, with the inference stated. |
| **UNKNOWN** | Not determinable from the material examined. |
| **OPEN** | A question that requires counsel or a rights-holder, not an engineer. |

---

## 2. The controlling constraint: Anthropic Commercial Terms §D.4

**OBSERVED.** The Commercial Terms, §D.4 "Use Restrictions", prohibit attempting to:

- "reverse engineer or duplicate the Services";
- "support any third party's attempt at any of the conduct restricted in this sentence";
- "access the Services to build a competing product or service", including "to train competing AI models or resell the Services", "except as expressly approved by Anthropic".

The Consumer Terms §3 separately prohibits "decompile, reverse engineer, disassemble, or otherwise reduce our Services to human-readable form, except when these restrictions are prohibited by applicable law."

The prior investigation's `TERMS-NOTES.md` adds the `code.claude.com/docs/en/legal-and-compliance` statement that "The Claude Code binary must not be modified", and records the April 2025 DMCA enforcement precedent against a developer who de-obfuscated the bundled JS source.

### 2.1 What this means, concretely

| Activity | Status | Reasoning |
| :- | :- | :- |
| Reading the reference product's **public documentation** | **Permitted** | Publicly published material, offered for the purpose of being read. |
| **Black-box observation** of the published CLI (running it, reading its output, reading files it writes) | **Permitted** | Ordinary use; no reverse engineering; the "compatibility with the Services" carve-out in §D.4 does not reach it. |
| Recording the **observable interface** (event names, settings keys, file formats) | **Permitted** | Facts about a published interface, not protected implementation. This is the "clean-room compatibility" position. |
| **Decompiling / disassembling / de-minifying** the binary, recovering JS sources or source maps, modifying the binary | **Prohibited — and not performed** | §D.4 and Consumer Terms §3. Also destroys the clean-room property. |
| Reading the **private system prompt** of the running product, or any hidden internal API | **Prohibited — and not performed** | §D.4. |
| Using the reference product **as a training data source** for our own model | **Prohibited** | §D.4, explicitly: "including to train competing AI models". |
| Using the reference product as a **teacher / distillation source** — i.e. collecting its outputs to train our model | **Prohibited** | Same clause. Distillation is training a competing model from the Services' outputs. |
| Using the reference product as a **runtime provider** for our product's model calls, with our own independent implementation around it | **OPEN** — see §12.1 | The product is a competing *service* in a literal sense. The narrow argument is that the prohibition targets using the Services to *build* the competing product, not to run a permitted account. **This review does not resolve it**, and the plan in `implementation-plan.md` is built so the answer does not change what we do. |
| Studying a **third-party publication** of the reference product's prompts, to extract *design principles* | **Permitted in principle, tightly constrained** | The third party published the material under CC0 (subject to §3 and §4). The risk is not the copyright in the capture; it is §D.4 if our use of the capture amounts to using the Services to build a competing product. We constrain this by §3.3 and §4 below. |
| Training our model on **our own original, licensed, independently-sourced corpus** | **Permitted** | No connection to the Services. This is the path the training-data plan takes. |

### 2.2 The boundary we adopt

**A system prompt is a specification, not an asset.** What makes a coding agent good is: which tools exist, what their schemas are, how the harness gates them, how context is managed, how the loop recovers from failure, and what the model is told to prioritise. **All of that is observable, all of it is documentable, and all of it can be re-derived from first principles.**

**A system prompt's *prose* is an asset.** Copying Anthropic's sentences into our product would be copying a copyrighted work (and, for the skill bundles, would breach an explicit additional restriction). We therefore treat every prompt file as a **read-only reference from which we derive engineering principles in our own words**, and our product ships our own prose.

**This is not a lawyerly distinction. It is operational.** §5 of the `prompt-pattern-analysis.md` (produced in Part 1) records, for each of the twelve principle categories, the independent implementation and the test that proves it. If a principle can be stated without reference to the original wording, we can implement it without copying. Where a principle cannot be stated without quoting — i.e. where the value is the specific phrasing rather than the structural idea — we do not use it. That test is mechanical, and it is the one the implementation plan relies on.

---

## 3. The system-prompt research collection

**Repository:** `https://github.com/asgeirtj/system_prompts_leaks`
**HEAD at review time:** `e7e53f2bc29199dfada98aa9f5d24621c2f65684` ("Add built in mod 'you-should-know' prompt"), 2026-10-19.
**History:** 866 commits, first commit 2025-05-03. All commits by the repository owner.
**Size:** 1,314 files total; 624 under `Anthropic/`.

### 3.1 The licence history is the important part

**OBSERVED** (`git log --follow -- LICENSE`):

| Commit | Date | Subject |
| :- | :- | :- |
| `ff6b49b` | 2026-04-11 | "Add MIT license" |
| `e917d62` | 2026-05-28 | "Switch license to CC0 1.0, reorganize Anthropic section, add .gitignore" |
| `71ca513` | 2026-06-05 | "Move CONTRIBUTING.md and LICENSE to .github/" |
| `e80c088` | 2026-06-05 | "Move LICENSE back to root — GitHub only detects it there" |

**OBSERVED.** The repository's first commit is 2025-05-03 and the MIT licence was not added until 2026-04-11 — 524 commits, and roughly eleven months, after the first captured prompt was published. The switch to CC0 came on 2026-05-28, and that commit also deleted `Anthropic/claude.ai-human-readable.md` (3,837 lines) and reorganised the Anthropic subtree.

**INFERRED.** The collection was public for a substantial period before any licence was stated, and the licence has been changed at least once. The current CC0 is a *later* act applying to *earlier* material.

### 3.2 Why the CC0 does not settle the question

**OBSERVED.** The root `LICENSE` is the full CC0 1.0 Universal text. Its §4 (Limitations and Disclaimers) states, in the affirmer's own words:

- **(b)** the Affirmer "offers the Work as-is and makes no representations or warranties of any kind concerning the Work, express, implied, statutory or otherwise, including without limitation warranties of title, merchantability, fitness for a particular purpose, non infringement, or the absence of latent or other defects, accuracy, or the presence or absence of errors";
- **(c)** the Affirmer "disclaims responsibility for clearing rights of other persons that may apply to the Work or any use thereof … Affirmer disclaims responsibility for obtaining any necessary consents, permissions or other rights required for any use of the Work";
- **(a)** no trademark or patent rights are waived.

**INFERRED — and this is the crux of the whole review.** A CC0 dedication is a *waiver by the person making it*. It is only as broad as that person's rights. The repository owner compiled a collection whose contents are, for the Anthropic subtree, the **output of a commercial service**. The CC0's own §4(c) concedes this: the person applying it disclaims any responsibility for clearing third-party rights.

Therefore:

- **CC0 covers the compilation** — the repository owner's own editorial arrangement (file selection, directory structure, README, formatting) is dedicated to the public domain. That is genuinely useful: it means the *structure* of the collection, and any original text the owner wrote, are free to use.
- **CC0 does not necessarily cover the captured content.** For the Anthropic subtree, the underlying text was produced by a service whose terms reserve the rights and impose the §D.4 restrictions in §2. The owner cannot waive rights he does not hold, and has expressly disclaimed responsibility for clearing them.
- **Practical consequence: treat the Anthropic subtree as "no licence granted" and apply the §2.2 clean-room discipline.** We are not relying on the CC0 for the captured Anthropic text at all. We are relying on it only for the compilation and for the non-Anthropic parts of the tree.

This is the conservative reading, and it costs us nothing: the plan never needed to copy the text.

### 3.3 The non-Anthropic subtrees

**OBSERVED.** The repository also contains `OpenAI/`, `Google/`, `Microsoft/`, `Meta/`, `xAI/`, `Mistral/`, `DeepSeek/`, `Qwen/`, `GLM/`, `Kimi/`, `Cursor/`, `Notion/`, `Perplexity/`, `Pi/`, and `Misc/`.

**INFERRED.** The same §4(c) reasoning applies with equal force to each vendor's captured prompts — each is output of that vendor's service, under that vendor's terms. We therefore apply the **same exclusion** to the whole repository: no captured vendor prompt text is copied into our product, and no captured vendor prompt text is used as a training input.

**What the collection is legitimately useful for**, and this is the whole of our permitted use:

1. **A catalogue of design patterns** — the structural knowledge of *what* a production coding agent does, distilled into our own words in `prompt-pattern-analysis.md`. Independent third-party analysis of a public product is not a copyrightable work in the way a specific expression is, and we are not reproducing the expression.
2. **A cross-vendor comparative view** — the collection spans many agent products, which is what makes it valuable as *research* rather than as a source of copyable text.
3. **A pointer list** — where to look for authoritative material (the `official/` subtree points at Anthropic's own release-notes page, which we then read directly).

### 3.4 The `official/` subtree — a distinction that changes the analysis

**OBSERVED.** `Anthropic/official/` (42 files) contains prompts **Anthropic itself publishes** at `platform.claude.com/docs/en/release-notes/system-prompts`, dated by release. The `official/README.md` states they are "Archives from https://platform.claude.com/docs/en/release-notes/system-prompts — the `claude_behavior` system prompts Anthropic publishes for claude.ai and the mobile apps", and adds a note that "release-notes versions" are "shorter than the real served prompts above".

**OBSERVED.** We fetched that page directly. It publishes 24 model prompts and **no `claude_code` product**; the page states these updates "do not apply to the Claude API".

**INFERRED.** There is a **three-tier provenance** in this repository, and conflating the tiers is the main analytical trap:

| Tier | What it is | Provenance | Our use |
| :- | :- | :- | :- |
| **A — Official** | `Anthropic/official/*` | Published by Anthropic for public release | The **most** reliable tier. Publicly offered. Freely citable. Directly comparable to the captures. |
| **B — Captured** | `Anthropic/claude-code/*`, `Anthropic/claude-*.md` | Third-party capture of a served prompt. Method undocumented. | **Corroborated for 5.x (§5)**; **uncorroborated for Claude Code**. Used as research input under §2.2 discipline. |
| **C — Vendors** | `OpenAI/*`, `Google/*`, etc. | Third-party capture of *their* products | Excluded from copying and from training by §3.3. Usable for comparative pattern analysis. |

**Consequence.** Because Tier A exists and is public, **we do not need to rely on Tier B for the claude.ai behaviour prompts at all.** The analysis in `prompt-pattern-analysis.md` can be anchored on Tier A and cross-checked against Tier B. Only the **Claude Code agent-harness** prompts exist solely at Tier B — and that is precisely where the corroboration gap in §5 matters.

---

## 4. Embedded restrictive licences inside the collection

**OBSERVED.** Nine licence files ship inside the collection:

| Path | Licence |
| :- | :- |
| `LICENSE` (root) | CC0 1.0 Universal |
| `Anthropic/claude-code/skills/{built-in-browser, chrome-browser, computer-use, docx, pdf, pptx, xlsx}/LICENSE.txt` | **© 2025 Anthropic, PBC. All rights reserved.** — proprietary, with additional restrictions |
| `Anthropic/claude-code/skills/skill-creator/LICENSE.txt` | Apache 2.0 |
| `Meta/muse-code/skills/LICENSE` | Apache 2.0 |
| `Anthropic/claude-code/skills/morning/assets/fonts/Fraunces-OFL.txt` | SIL Open Font License 1.1 |

**OBSERVED — the Anthropic proprietary licence text.** The seven Anthropic skill bundles carry a licence stating: "Use of these materials (including all code, prompts, assets, files, and other components of this Skill) is governed by your agreement with Anthropic regarding use of Anthropic's services…". Its "ADDITIONAL RESTRICTIONS" section states users may not:

- "Extract these materials from the Services or retain copies of these materials outside the Services";
- "Reproduce or copy these materials, except for temporary copies created automatically during authorized use of the Services";
- "Create derivative works based on these materials";
- "Distribute, sublicense, or transfer these materials to any third party";
- "Make, offer to sell, sell, or import any inventions embodied in these materials";
- "Reverse engineer, decompile, or disassemble these materials";

and concludes: "The receipt, viewing, or possession of these materials does not convey or imply any license or right beyond those expressly granted above."

### 4.1 Analysis

**INFERRED — with confidence.** These seven skill bundles are the **most clearly restricted material in the entire project**. They do not merely lack a CC0 grant; they carry an **explicit, on-the-face, additional restriction** that directly contradicts the use we might otherwise make of them:

- The licence is **narrower than the root CC0**. Where the root licence covers the compilation, these files state that the *materials themselves* are governed by the Anthropic agreement and may not be copied, derived from, or redistributed. A sub-file licence that is more restrictive governs that file.
- The restriction **names the exact acts** our clean-room discipline performs (extraction, reproduction, derivative works). "Create derivative works based on these materials" is precisely what a reimplemented skill would be, if it were derived from these files rather than independently conceived.
- "Extract these materials from the Services or retain copies of these materials outside the Services" appears to forbid even the **capture** step that put them in this repository. That is a question about the *collector*, not about us, and it is recorded in §12 as **OPEN-Q2**.

**INFERRED — a reading we do not need to rely on.** One could argue that a downstream reader who never received the materials "from the Services" has not "extracted" them, and that independent reimplementation from observed *behaviour* is not a "derivative work based on these materials". That argument has some force. **We do not need it.** Our position is stronger and simpler:

> **The seven Anthropic skill bundles are excluded from this project entirely.** Not as a licensed input, not as a training input, not as a source of derived text, and not as a source of derived *structure*. Our skills subsystem is designed from the general principles in `prompt-pattern-analysis.md` §3 (skill composition, tool restriction, progressive disclosure) and from the **observable** behaviour of the running product — never from these files.

### 4.2 The two permissive exceptions

**`skill-creator/LICENSE.txt` (Apache 2.0) and `Meta/muse-code/skills/LICENSE` (Apache 2.0)** are genuinely permissive licences and are, on their face, usable. **But** Apache 2.0 §4 requires retention of attribution and licence notices, and the underlying *content* still carries the same provenance question as the rest of the capture: the content is a capture of a service's output, and Apache 2.0 in a repository does not make the captured text Apache-licensed. The same §4(c) reasoning applies.

**Decision: excluded as well.** The cost of excluding them is zero — they are two skill bundles out of a much larger corpus, and the relevant *principles* are recorded in `prompt-pattern-analysis.md` from the general corpus. We take the Apache 2.0 licence at face value for its **code** (if we ever wanted to reuse REA's or another project's Apache-licensed code) and not for captured Anthropic *text*.

**`Fraunces-OFL.txt` (SIL OFL 1.1)** is a genuine, self-contained, well-known font licence with an explicit permission to use, modify, and redistribute provided the licence travels with the font and the font is not sold by itself. **This one is usable in principle** — but a font is not what this project needs, and shipping a third-party font would require preserving the OFL text and naming the font. **Not used.** Recorded so that if a design surface later needs a typeface, the licence has already been cleared.

---

## 5. Corroboration: how far can we trust the captures?

This is the empirical half of the review, and it is the most useful thing in it.

### 5.1 Method

**OBSERVED.** `Anthropic/official/` (Tier A) and the captured files (Tier B) can be compared directly, because both contain the claude.ai `claude_behavior` prompt for the same model. Method: strip Markdown headings from both, take the set of non-empty prose lines, and count how many of the Tier A prose lines appear **exactly** in the Tier B capture.

**OBSERVED — results:**

| Tier A file | Tier B capture | Tier A prose lines | Exact matches | Match rate |
| :- | :- | :-: | :-: | :-: |
| `2026-09-01-claude-fable-5.1.md` | `claude-fable-5.1.md` | 96 | 88 | **91.7 %** |
| `2026-07-24-claude-opus-5.md` | `claude-opus-5.md` | 71 | 64 | **90.1 %** |
| `2026-09-22-claude-opus-5.5.md` | `claude-opus-5.5.md` | 89 | 79 | **88.8 %** |
| `2026-06-30-claude-sonnet-5.md` | `claude-sonnet-5.md` | 69 | 61 | **88.4 %** |
| `2026-06-09-claude-fable-5.md` | `claude-fable-5.md` | 70 | 61 | **87.1 %** |
| `2026-09-28-claude-sonnet-5.5.md` | `claude-sonnet-5.5.md` | 62 | 54 | **87.1 %** |
| `2026-05-28-claude-opus-4.8.md` | `claude-opus-4.8.md` | 81 | 70 | **86.4 %** |
| `2026-10-07-claude-haiku-5.5.md` | `claude-haiku-5.5.md` | 78 | 56 | **71.8 %** |
| `2026-02-17-claude-sonnet-4.6.md` | `claude-opus-4.6.md` | 55 | 16 | 29.1 % |
| `2026-04-16-claude-opus-4.7.md` | `claude-opus-4.7.md` | 69 | 14 | 20.3 % |
| `2026-02-05-claude-opus-4.6.md` | `claude-opus-4.6.md` | 55 | 8 | 14.5 % |

### 5.2 Interpretation — the 5.x/4.x split

**INFERRED (high confidence).** The 4.x-era Tier A files are *condensed* release-note versions — the repo's own README says so ("release-notes versions — shorter than the real served prompts"). A condensed summary and a full served prompt share only their invariant sentences. We verified this directly: for Opus 4.6 the Tier A file's 55 prose lines are a *summary* ("This iteration of Claude is Claude Opus 4.6 from the Claude 4.5 model family"), and the lines that matched the capture were the invariant ones ("Claude can discuss virtually any topic factually and objectively"; "Claude avoids saying 'genuinely', 'honestly', or 'straightforward'"). The low 4.x numbers measure **the brevity of the Tier A file**, not the unfaithfulness of the capture.

**INFERRED (high confidence).** For the 5.x family the Tier A files are *not* condensed — they are long and structurally parallel to the captures — and 86–92 % of their prose is present **verbatim** in the captures. A 5.x Tier A file and its Tier B capture are two independent transcriptions of the same text that agree on 86–92 % of their non-trivial lines, including awkward specifics (e.g. the exact export-control suspension timeline; the exact ordering of the product list; the exact list of injectable reminder names).

**INFERRED (high confidence).** The 5.x captures are therefore **faithful transcriptions of a real served prompt**. The probability that ~90 % of an Anthropic-published 27 KB document appears verbatim in a fabricated file is negligible.

### 5.3 The remaining gap — and it is the important one

**OBSERVED.** The Tier A corpus covers **only** the claude.ai / mobile `claude_behavior` prompt. **There is no officially published Claude Code system prompt.** We confirmed this directly against the release-notes page: 24 model prompts, no `claude_code` product.

**Therefore, and this is the honest statement of confidence:**

| Subject | Corroboration | Confidence |
| :- | :- | :- |
| claude.ai behaviour prompts, 5.x family | 86–92 % verbatim overlap with Anthropic's own published text | **HIGH** — these are real |
| claude.ai behaviour prompts, 4.x family | consistent, but the comparison is against condensed summaries | **MEDIUM-HIGH** |
| **Claude Code agent-harness prompts (all variants)** | **none available** | **UNKNOWN** — plausible, internally consistent, and consistent with the Tier A method, but not independently corroborated |

**INFERRED.** The Claude Code captures carry *internal* evidence of authenticity that is worth recording:
- The `## Tools` introduction block (specifying the on-the-wire invocation syntax) is **byte-identical across all seven variants** — consistent with one renderer.
- Native tool sections are **strictly alphabetical in all seven**; MCP sections are **grouped contiguously by server, alphabetical within group** — a machine-generated ordering, not a human transcription.
- The captured surfaces are **mutually consistent**: headless lacks the interactive-approval tools; cloud lacks the persistent-memory section and adds remote-container and model-identity sections; desktop adds the app-integration surface. These differences are exactly what the feature set predicts.
- The `## Memory` block is byte-identical across six of seven variants; the `## Delivering work` / `## Writing for the user` block is byte-identical between Fable 5.1 and headless Fable 5.1.
- The tool descriptions' **cross-references are internally consistent** — e.g. `Monitor` says "Use TaskStop to cancel early" and `TaskStop` exists; `Read` says "Strip the Read line prefix" and `Edit` says exactly that; `ExitPlanMode` says "use AskUserQuestion first" and that tool exists.

**But INFERRED clearly: internal consistency is not authentication.** A careful fabrication would also be internally consistent. So the correct engineering position is:

> The Claude Code captures are treated as a **high-quality, unverified specification**. Where a claim from them is load-bearing for a design decision, it is **cross-checked against the reference product's observable behaviour** (which the prior investigation did extensively and independently) or against **official documentation**. Where it cannot be, it is marked as a *design hypothesis* in `feature-checklist.md` and implemented so that the behaviour is *reasonable* rather than *faithful*.

This is exactly what `feature-checklist.md` does: every feature row carries an evidence reference, and rows that rest only on the prompt collection are distinguished from rows confirmed by black-box observation.

### 5.4 A consistency note worth recording

**OBSERVED.** The tool-description analysis found that the Opus 5.5 capture's preamble carries a runtime date of `2026-10-13`, and the commit that last touched the file (`ce95741`, "Update claude-code system prompts") is also dated 2026-10-13 — while the Fable 5.1 capture was updated on 2026-10-19 and carries `2026-10-19`. The `Today's date` value in these captures tracks the commit date of the corresponding update, not a fixed capture date.

**INFERRED.** The date in the prompt is the *session* date at capture time; it does date the capture approximately, and it corroborates the capture/update correspondence. It does **not** establish which Claude Code build was running.

**OBSERVED.** No capture contains a Claude Code version string. The version numbers that appear (`2.1.304`, `2.1.295`, …) exist **only in commit subjects**, never in the prompt bodies. So the mapping "capture X corresponds to build 2.1.304" rests on the collector's commit-message discipline, not on anything inside the capture.

---

## 6. The REA toolchain

**OBSERVED.** `morluto/rea` (`rea-agents` v6.7.0) is MIT-licensed (`LICENSE`, "Copyright (c) 2026 morluto"). Its `DISCLAIMER.md` states it is built for "lawful analysis" and that the project "does not support, and will not help with": circumventing DRM; developing game cheats; bypassing authentication on systems you are not authorized to test; **"copying proprietary software or reproducing its protected code and assets"**; **"evading the usage policies or safety measures of AI model providers"**; reselling or sharing AI accounts or API access.

Its `THIRD_PARTY_NOTICES.md` is thorough: a locked npm dependency inventory, preserved licence texts for MIT/Apache-2.0/GPL-3.0-with-GCC-Runtime-Library-Exception/LGPL-2.0/BSD-3-Clause components, and — notably — an honest record of two upstream packages (`clean-git-ref@2.0.1`, `minimisted@2.0.1`) that "omit a full license/copyright document in their published archives", handled by preserving the declared licence and author metadata with "a clearly labeled standard license text", explicitly described as "documented upstream notice gaps, not recovered copyright notices or a claim that attribution has been fully verified."

### 6.1 Permitted uses

| Use | Status | Reasoning |
| :- | :- | :- |
| Run REA against **our own** binaries and artifacts | **Permitted** | MIT licence; our own artefacts, our own authority. |
| Reuse REA's **MIT-licensed code and documentation** as reference for our own tooling, with attribution | **Permitted** | MIT permits copying, modification, and distribution with the notice retained. Our REA-based investigation workflow (subsystem S15) may cite and learn from `docs/process-capture.md`, `docs/mcp-contracts.md`, `AGENTS.md`, and the `.agents/skills/` structure. |
| Use REA's **process/terminal-capture** mode against the reference product's published CLI | **Permitted, and already the established method** | Same black-box-observation basis as §2.1. REA's own disclaimer targets "copying proprietary software or reproducing its protected code and assets" — recording observable terminal behaviour is neither. |
| Study REA's **evidence-provenance discipline** (observation / derivation / inference / unknown; Evidence records; fail-closed integration) | **Permitted** | It is a *method*, and it is MIT-licensed, and it is independently valuable. Our `security-plan.md` and `test-plan.md` adopt the same epistemic discipline. |
| Use REA's decompilation / JS-recovery / native-binary / instrumentation facilities against **Anthropic artefacts** | **Prohibited — and not performed** | Breaches Anthropic Commercial Terms §D.4, Consumer Terms §3, `code.claude.com/docs/en/legal-and-compliance`, and REA's own disclaimer. Also destroys the clean-room property. |

**INFERRED.** The agreement of the two constraints is convenient and was the basis of the prior investigation's `TERMS-NOTES.md` conclusion: the licence boundary and the clean-room requirement point the same way. We do not use REA to reach behind the product's observable interface at any point in this project.

### 6.2 A hard environmental constraint discovered

**OBSERVED** (`docs/process-capture.md`): "Capturing a new scenario currently requires Linux or macOS and a working native PTY backend. Native Windows capture is unavailable because the PTY adapter does not yet verify descendant cleanup… Comparing existing capture Evidence through the CLI or MCP remains available on Windows and does not launch a PTY or the captured target."

**INFERRED — and it changes the Part 2 plan.** This project runs on Windows 11. REA's *new* process capture is therefore **unavailable on this host**; only *comparison* of existing capture evidence works there. The prior investigation's captures were made on this host through the product's own documented CLI surfaces (`--output-format stream-json`, `claude logs`), which is unaffected. But any *new* REA-driven capture as part of Part 2 must either (a) run under WSL with Linux REA, or (b) be replaced by direct invocation of the published CLI. This is recorded as a constraint in `feature-checklist.md` (S15) rather than left implicit.

### 6.3 REA's "no workaround after refusal" clause — worth adopting

**OBSERVED.** REA's `AGENTS.md` and `CONTRIBUTING.md` require a "fail-closed integration rule": "Do not integrate capabilities while material scope, authority, side-effect, or required verification questions remain unresolved," and for new providers involving "target execution, injection, mutation, or protection recovery," a maintainer scope decision is required before implementation. It also requires that "Unresolved identity or applicability must remain unknown rather than be treated as absent, foreign, or aligned."

**INFERRED.** This is a *better* engineering rule than most, and we adopt it in our own words in `security-plan.md`: the "unknown" is a first-class state that must not be silently resolved. It is the same discipline the earlier investigation used with its OBSERVED / INFERRED / UNKNOWN tagging, arrived at independently — which is a useful cross-check that the discipline is sound rather than idiosyncratic.

---

## 7. The reference product's documentation

**OBSERVED.** The prior investigation cached 28 pages from `code.claude.com/docs/en/*` into `agent-reference-shots/docs-cache/`.

**INFERRED — status: usable.** Publicly published product documentation, offered by Anthropic for the purpose of being read and implemented against. Reading it, quoting it in an internal engineering document, and implementing the documented behaviour are all ordinary use. What is *not* ordinary use is reverse-engineering the implementation behind it (§2.1) or using the service to build a competing model (§D.4).

**One caveat, carried forward.** The cache contains the Anthropic **Commercial Terms** text and the **`legal-and-compliance`** page. Those are *instructions to us*, not engineering material, and they set the boundary — they are cited in this review as constraints, never mined for design.

**Recommendation.** Keep the cached docs as an internal engineering reference. Do **not** ship them, do not quote them at length in user-facing product documentation, and cite them rather than reproduce them in our own docs.

---

## 8. Model training inputs — the plan must not touch the reference product

This is where §D.4 has the sharpest edge, and where the training-data plan must be disciplined.

### 8.1 The prohibition

**OBSERVED.** Commercial Terms §D.4: "access the Services to build a competing product or service", including "to train competing AI models", except as expressly approved by Anthropic.

### 8.2 The rule we adopt

**A training corpus for our own model must have no path to the reference product.** Concretely, the following are **excluded from every training and fine-tuning corpus**:

| Excluded | Why |
| :- | :- |
| Output of the reference product (its completions, its tool-call sequences, its transcripts) | §D.4 — distillation from the Services is training a competing model. |
| The prompt captures in the research collection | §3.2 — the corpus is output of the Services; and the collection is not a licensed dataset (§7 of the user's brief: "Do not use the collection automatically as a training dataset"). |
| Any dataset built by scraping a coding agent's traffic | Same reason. |
| Anthropic's own model weights, or derivatives (distillation, fine-tuning, quantisation, adapters) | Not a licence question — a market question. "Competing AI models" is the phrase in §D.4. |
| Synthetic data generated *by* the reference product | Output of the Services. |

**Permitted, and the actual plan:**

| Permitted | Notes |
| :- | :- |
| Permissively-licensed source code from public repositories | Per-repository licence check; see §9. |
| Permissively-licensed documentation (e.g. permissively licensed project READMEs, published specifications) | Per-item licence check. |
| Public issue-tracker data under terms that permit it | Terms vary; see §9. |
| Human-authored data we write ourselves | Original; no licence issue. |
| Data from a permissively-licensed base model we start from (Stage F onward) | The base model's licence governs the weights; the data licence governs each corpus. They are independent. |

### 8.3 The decontamination requirement

**INFERRED.** Because §D.4 is aimed at *competing* models, and because the general rule of thumb in the field is that a model trained on data that contains a benchmark has not been evaluated on that benchmark, our `benchmark-and-evaluation-plan.md` includes a contamination gate: every evaluation task must be checked for presence in the training corpus, and a task that fails the check is either excluded or the corpus is deduplicated. This is both an evaluation-integrity measure *and* the practical way to demonstrate that §D.4 was respected — a corpus built from permissively-licensed public sources demonstrably has no path to the reference service's outputs.

**This is a genuinely strong position.** Our model can be trained entirely on material that has no connection to the reference product, and we can *prove* it by construction rather than by assertion.

---

## 9. Register of candidate corpora and their licence status

**Every row below is a candidate, not an approval.** Each requires the same gate: an item-level licence check, a terms check on the specific source, and a contamination check, before use.

| Source | Stated licence | Status | Notes and required checks |
| :- | :- | :- | :- |
| The Stack (v2 / v1) | per-repo, mostly permissive | **CANDIDATE** | Opt-out honoured; must exclude opt-out repos; store the opt-out list hash at build time and re-verify. |
| SWE-bench / SWE-bench Verified | per-instance repo licences; benchmark licence is separate | **CANDIDATE for evaluation, CANDIDATE for training with care** | The *evaluation* use and the *training* use have different licence questions. A model trained on a benchmark's instances cannot be evaluated on it. |
| MBPP / HumanEval | permissive (Apache-2.0 / MIT) | **CANDIDATE** | Small; decontamination is easy; use as a held-out set **only**. |
| LiveCodeBench | see benchmark licence | **CANDIDATE for evaluation** | Time-sliced contamination control is part of its design. |
| Aider Polyglot | permissive | **CANDIDATE for evaluation** | Exercise-based, not repo-based. |
| The Stack v2 permissively-licensed subset | permissive per-repo | **CANDIDATE** | Decontamination is the dominant cost, not licensing. |
| GitHub code under MIT/Apache/BSD | per-repo | **CANDIDATE** | The highest-value, lowest-risk corpus class. **Requires an automated per-repo licence classifier** at ingest. |
| Public issue/PR data (GitHub Archive, GHTorrent) | GitHub ToS; per-repo licence | **CANDIDATE with care** | GitHub's ToS permits research use but places conditions on redistribution; **we would not redistribute the raw corpus**. Verify current ToS text at ingest time and re-verify annually. |
| Model-generated synthetic code | depends on the generating model | **CANDIDATE with care** | Only from models whose licences permit it and with no §D.4 path. If the generator is the reference product, **excluded** (§8.2). |
| Our own original data (specs, tests, reviews) | ours | **APPROVED IN PRINCIPLE** | Original; the highest-quality, lowest-risk class. |
| Anthropic system-prompt captures | none granted / restricted | **EXCLUDED** | §3.2, §3.3, §4. |
| The reference product's outputs | n/a | **EXCLUDED** | §D.4. |
| Anthropic weights | n/a | **EXCLUDED** | §D.4. |

### 9.1 The gate every candidate must pass

1. **Licence identification** — per-item, from the source's own licence file, not from a directory-level assumption. Where the licence is ambiguous, the item is excluded.
2. **Terms-of-service check** — for any site whose terms constrain automated collection, the current terms are read and recorded at ingest time with a date.
3. **Contamination check** — a match against every evaluation task, at the level of the task's oracle (the test file, the patch, the answer).
4. **Provenance record** — a manifest entry per ingested item: source URL, licence text hash, ingestion date, and the licence-check result. This manifest is an artifact we ship, and it is what makes the corpus auditable.
5. **Human sign-off** — the `licensing-and-provenance-review.md` gate is re-run for any *new class* of source, not per-item.

---

## 10. Provenance record for what we have already used

For auditability, this is what has been consulted so far and under what basis.

| Artifact | Basis | Incorporated into a product? | Recorded where |
| :- | :- | :- | :- |
| `code.claude.com/docs/*` (28 pages) | Public documentation | No | `agent-reference-shots/docs-cache/` |
| Anthropic Commercial / Consumer Terms; `legal-and-compliance` | Public legal pages | No | `agent-reference-shots/TERMS-NOTES.md`; this document |
| Reference product black-box observations | Ordinary use of a published CLI | No | `agent-reference-shots/` (44 entries), `agent-evidence.md` |
| `platform.claude.com/docs/en/release-notes/system-prompts` | Publicly published by Anthropic | No | This document; `prompt-pattern-analysis.md` |
| `system_prompts_leaks` (research only) | Research use; no licence reliance (§3.2) | No | `prompt-pattern-analysis.md`; this document |
| `system_prompts_leaks` — 7 Anthropic skill bundles | **Excluded** (§4) | No | Not used beyond confirming the restriction |
| `morluto/rea` — MIT code and docs | MIT | No | Method reference for S15 |
| `morluto/rea` — tool execution | MIT tool, permitted use | No | Evidence tree |
| Anthropic model weights | **Excluded** | No | — |
| Any dataset | — | — | None ingested |

**No third-party code, prompt text, or asset has been copied into any artifact this project has produced.** The deliverables to date are original documents.

---

## 11. Third-party components we will deliberately depend on

| Component | Licence | Obligation | Our plan |
| :- | :- | :- | :- |
| REA (as a tool) | MIT | Notice retention if redistributed | Use as an installed tool; not vendored. |
| A runtime language and its standard library (to be chosen) | TBD | — | Selected in `architecture.md`; licence reviewed at selection. |
| A terminal-rendering library (if any) | TBD | — | Prefer a permissive licence; review at selection. |
| A JSON-Schema validation library (if any) | TBD | — | Same. |
| A tokenizer implementation | TBD | — | Must be a permissive, independently implementable licence; **not** a copy of any vendor's vocabulary file without checking the vocabulary's provenance separately. See `model-architecture-proposal.md`. |
| Training framework | TBD | — | Prefer Apache-2.0/MIT; review at selection. |

**INFERRED.** Every one of these is a selection that has not yet been made, and each will clear §9.1's gate before it enters the build. The `architecture.md` ADRs deliberately defer the runtime-language choice to a decision point with an explicit licence check attached.

---

## 12. Open questions

These are the questions this review **cannot** answer. They are ordered by how much they matter.

### OPEN-Q1 — Does the §D.4 "competing product" clause reach *using* the reference service as our product's runtime model provider? *(highest priority)*

**The question.** Anthropic's Commercial Terms §D.4 prohibits "access to the Services to build a competing product or service … except as expressly approved by Anthropic". Our product would be, in a literal sense, a competing service. Does merely *running* the published CLI under our own authorised account, with our own independent implementation around it, constitute "access … to build a competing product"?

**Arguments each way.**
- *Against restriction:* the clause's object is *building* a competing product using the Services — i.e. using the Services as a source of reverse-engineering insight or training signal. Ordinary authorised use of a published tool is not "building" anything. The clause also sits in a section about how a customer may use the services, and the Services remain available to any user.
- *For restriction:* the clause says "access … to build a competing product or service", and the "except as expressly approved" proviso admits that Anthropic contemplates gating competitive use. A product that directly substitutes for the reference product's core function, and does so using the reference product, is uncomfortably close to the concern the clause is addressing.

**Why we do not resolve it.** This turns on the construction of a commercial contract term. We are not qualified to opine, and the honest position is that a reasonable reading exists on each side.

**Why the plan does not depend on it.** `implementation-plan.md` is built so that the answer changes *nothing we do*:
- The **Phase 1 vertical slice** uses a model provider to make the harness real. The user already runs Claude Code under their own authorised account in this environment; that is a *pre-existing* authorised use, and our harness would connect to the same authorised account, not "build" the competing product with it.
- Every deliverable in this planning stage is a **document**, not a product.
- The product's own model path (`llm-development-roadmap.md` Stage F onward) requires **no reference service at all** (§8.2).

**Action.** Before implementation begins, the user should either (a) obtain Anthropic's written comfort on the specific intended use, or (b) adopt a stricter posture — for example, build the Phase-1 slice against a **different, non-Anthropic** provider, which the gateway in this environment makes trivially available at zero cost, and keep the Anthropic path out of the product entirely. **Option (b) costs nothing and is recommended as the default**, with (a) as an optional accelerator for evaluation only. This is recorded as a decision for the user in the final approval gate.

### OPEN-Q2 — Did the collection's own capture of the seven Anthropic skill bundles breach Anthropic's "Extract these materials from the Services" restriction?

**The question.** The seven skill bundles carry a licence stating users may not "extract these materials from the Services or retain copies of these materials outside the Services". If the capture of those bundles was an extraction, then the copies in the repository were made without right.

**Why it matters to us only indirectly.** We do not use them (§4.1). The question matters because it bears on the *reliability* of the collection as a source generally: if one subtree was captured in breach of an explicit restriction, is the rest of the collection trustworthy? Our §5 corroboration is the answer — for the 5.x claude.ai family, the captures are demonstrably faithful, and the skill bundles are in a different subtree and a different provenance class.

**Action.** None for our use. Recorded so that no future contributor treats the whole collection as uniformly licensed.

### OPEN-Q3 — Does the retroactive MIT→CC0 switch create any historical exposure?

**The question.** The collection was published under MIT from 2026-04-11 and switched to CC0 on 2026-05-28. Material published during the MIT window may have been incorporated by third parties under MIT terms; CC0 is irrevocable, so this is unlikely to be a live issue, but the collection's own licence history is not spotless.

**Why it matters to us.** Marginally — it reinforces that we should not rely on the collection's licence at all (§3.2), which is our position regardless.

**Action.** None.

### OPEN-Q4 — Are the non-Anthropic vendor captures in the collection usable at all?

**The question.** Each vendor's captured prompts are output of that vendor's service, under that vendor's terms, and the CC0 does not clear them (§3.3).

**Our position.** They are usable for **comparative pattern analysis only** — reading them to understand what problems a production agent solves and how, then writing our own principles. Not copied, not trained on. This matches the treatment of the Anthropic subtree, so it is not an open question in practice; it is recorded because the collection's *scope* invites the error.

**Action.** None.

### OPEN-Q5 — Is a recorded "no Anthropic path" corpus enough to satisfy §D.4 for the model roadmap?

**The question.** We assert that our training corpus has no path to the Services' outputs. Does that assertion, backed by a provenance manifest, discharge any burden §D.4 places on a model developer?

**Our position.** We believe a demonstrably independent corpus is the strongest available evidence of good faith, and §D.4's concern — using the Services' output or behaviour to build a competing model — is not engaged when no output or behaviour was used. But "believes" is doing real work in that sentence.

**Action.** If the model roadmap reaches Stage E (scaling) or beyond, have counsel review the corpus manifest before the first substantial training run. Do this at that point, not now — the roadmap's early stages need no corpus from any questionable source.

### OPEN-Q6 — Trademark and branding

**The question.** Our product will be a functional equivalent of a product named "Claude Code". How far may we go in describing the relationship?

**Our position.** We will not use Anthropic's name, logos, or trademarks in our product's name, branding, or marketing. In *internal* engineering documents, factual reference ("the reference product's documented behaviour for X") is ordinary and necessary. The user's own brief requires that the application "use its own original code, assets, branding, and implementation" — which we treat as a hard constraint, not a preference. **OPEN** only in the sense that a specific marketing or naming decision may warrant a check.

**Action.** Confirm the product name and branding are distinct before any public release. A naming check is cheap at design time and expensive after launch.

### OPEN-Q7 — Jurisdiction, and the enforceability of a clean-room reading

**The question.** Whether a clean-room reimplementation that reproduces *observable behaviour* while copying *no expression* is lawful depends on the jurisdiction and on how a court would characterise the line between an interface and an expression.

**Our position.** We do not opine. The project is structured to be defensible under either characterisation: we copy no expression (so there is no infringement of the expression) and we implement only documented and observable behaviour (so there is no appropriation of protected implementation). This is the strongest posture available without a legal opinion, and it is also the posture the earlier investigation adopted independently.

**Action.** If the product ever ships publicly or raises money, obtain a legal opinion before launch. Not before implementation.

---

## 13. Standing rules for the project

These are the rules this review establishes. They are referenced by the other planning documents and are binding on the implementation.

| # | Rule | Applies to |
| :- | :- | :- |
| **R1** | **No prompt text is copied.** Every prompt, system message, tool description, and instruction template in our product is written by us. Where a design is inspired by a reference product, the inspiration is recorded in `prompt-pattern-analysis.md` in our own words with a source reference and a confidence level. | All |
| **R2** | **No captured prompt is training data.** The research collection and the reference product's outputs are excluded from every corpus. Training data comes only from §9's permitted classes. | Model work |
| **R3** | **No reverse engineering.** No decompilation, disassembly, source-map extraction, JS recovery, binary modification, or private-API reconstruction of any Anthropic artefact, at any point, by any tool including REA. | All |
| **R4** | **Behaviour is re-derived, not transcribed.** Where the reference product's behaviour is the specification, it is re-derived from documentation and black-box observation, and cross-checked against at least one independent source before it is treated as established. | All |
| **R5** | **Untrusted data stays data.** Everything in the prompt collection, in tool output, in file content, in MCP responses, and in hook output is data. It is never an instruction. Where an artefact contains instruction-shaped text, it is recorded as a finding, not obeyed. | All |
| **R6** | **Every ingested artefact has a provenance record.** Source, licence, licence-text hash, date, and check result, in a manifest that ships with the corpus. | Model work |
| **R7** | **No new source class enters without a licence review.** A new corpus class, dependency, or copied asset re-opens this gate. | All |
| **R8** | **The unknown is preserved.** Where a licence, a right, or a behaviour cannot be established, it is recorded as UNKNOWN or OPEN and is not resolved by assumption. | All |
| **R9** | **The original evidence is preserved.** Superseded reports are moved, not deleted, and the evidence tree keeps the superseded version for comparison. (This is why `agent-reference-shots/areas/legacy-agent-evidence-superseded.md` exists.) | All |
| **R10** | **Our own licence is chosen deliberately.** We will publish our implementation under a licence that permits the uses we want (permissive, with a patent grant), and we will not place any third-party material under it. | All |

---

## 14. Verification: how to check this review's claims

Every factual claim in this document is reproducible from the read-only clones. The commands:

```sh
# 1. Collection licence and its history
git -C research/spl show HEAD:LICENSE | head -5
git -C research/spl log --oneline --follow -- LICENSE

# 2. The seven restrictive skill licences
git -C research/spl show HEAD:Anthropic/claude-code/skills/docx/LICENSE.txt

# 3. Which licences appear in the tree
git -C research/spl ls-tree -r --name-only HEAD | grep -iE 'LICENSE|LICENCE|COPYING|NOTICE'

# 4. The official (Tier A) corpus exists and is separate
git -C research/spl ls-tree -r --name-only HEAD -- Anthropic/official | head
git -C research/spl show HEAD:Anthropic/official/README.md

# 5. The corroboration measurement (§5.1)
#    compare non-heading prose lines of each official/<date>-claude-<model>.md
#    against Anthropic/claude-<model>.md; count exact matches

# 6. REA's licence and disclaimer
git -C research/rea show HEAD:LICENSE | head -3
git -C research/rea show HEAD:DISCLAIMER.md | head -20
git -C research/rea show HEAD:docs/process-capture.md | head -20
```

**No artifact was checked out, executed, or modified in either clone.** Both were cloned with `--depth 1 --filter=blob:none --no-checkout` and read exclusively through `git show` / `git ls-tree` / `git log`, so the working trees were never populated and no repository content was ever run.

---

## 15. Summary of the licence position

| Asset | Licence status | Usable for | Not usable for |
| :- | :- | :- | :- |
| Reference product's public docs | Public | Understanding documented behaviour; quoting in internal docs | Shipping them; reverse-engineering behind them |
| Reference product's observed behaviour | Ordinary use | Deriving and testing an independent implementation | Copying implementation; training a competing model |
| Anthropic *published* system prompts (Tier A) | Publicly offered by Anthropic | Citing, comparing, studying the claude.ai behaviour prompt | Being a Claude Code prompt (it is not one) |
| Research collection — compilation | CC0 1.0 | Structure, editorial organisation, the owner's own text | — |
| Research collection — captured vendor text | **No reliable grant** | Reading for pattern analysis only | Copying; training on; distributing |
| Research collection — 7 Anthropic skill bundles | **Explicitly restricted** | Nothing | Everything, including derivative structure |
| REA code and docs | MIT | Reuse with notice; use as a tool | Its use against Anthropic binaries for reverse engineering |
| REA's own evidence discipline | MIT | Adopting the method in our own words | — |
| Reference product's outputs | §D.4 bars it | Nothing | Training; distillation |
| Anthropic weights | §D.4 / market | Nothing | Anything |
| Permissively-licensed public corpora | Per-item (permissive) | Training and evaluation, after the §9.1 gate | Redistributing raw issue-tracker data without checking the ToS |
| Our own original material | Ours | Anything | — |

**The position is sound and the plan is unaffected.** The project proceeds as designed: study for principles, reimplement independently, never copy, never train on anything that touched the reference service.

---

*Prepared 2026-10-21. Engineering risk assessment, not legal advice. Findings are reproducible via §14. The open questions in §12 require counsel before any public release, before substantial model training, or before any decision that depends on the answer; none of them blocks the planning work in this deliverable set.*

---

## Addendum — Keel's vendored default skills (2026-11-12)

Per the Phase B approval recorded in the 2026-11-12 session, Keel vendors Anthropic's openly published **anthropics/skills** repository at pinned commit `2c5958ecac7cee2b583967a2c4981d0f4a75c579` into `keel/resources/default-skills/` (18 of 19 example skills).

- **Licence:** Apache License 2.0. Each vendored skill carries its own `LICENSE.txt`; the upstream `THIRD_PARTY_NOTICES.md` is retained as `UPSTREAM_THIRD_PARTY_NOTICES.md`. Copyright and licence notices are preserved; these are Anthropic's works under Apache-2.0 and Keel claims no authorship over them.
- **Excluded:** `doc-coauthoring` — it ships without a licence file, and absent an explicit licence Keel does not redistribute it. Any future inclusion requires an explicit licence grant.
- **Provenance manifest:** `keel/resources/default-skills/PROVENANCE.md` records the source URL, commit, exclusion, and update policy.
- **Clean-room unaffected:** nothing from the Claude Code binary, Claude Desktop, or any product-internal/unpublished skill was used, inspected, or copied. The vendored skills are input data to an independent reimplementation of a public loader format.
- This addendum records provenance only; no legal conclusion is drawn, and this review's OPEN-Q items remain unchanged.

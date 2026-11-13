---
name: keel-meta
description: How to develop the Keel harness repository itself — layout, test strategy, the phase discipline, and the honesty rules this project runs on. Use when modifying keel/ (the harness), its docs, or when a change would touch the compliance boundary.
when_to_use: Editing keel/ source or tests; deciding where new code belongs (Phase 0 vs Phase 1 vs Phase 2); reviewing changes for overclaiming; adding a provider or tool; touching the clean-room boundary.
allowed-tools: [run_shell, read_file, edit_file, write_file]
argument-hint: <what you intend to change>
---

# Keel Project Conventions

Rules this repository lives by. Breaking them is the fastest way to make the
project worthless — treat every bullet as load-bearing.

## Layout map
- `src/keel/shell_ast.py` — Phase 0 (shell decomposition + effect classification).
- `src/keel/events.py`, `toolresult.py`, `transcript.py`, `session.py`, `runner.py`,
  `permissions.py`, `fakes.py` — Phase 1 spine.
- `src/keel/providers/` — adapters (OpenAI-compatible, Gemini, Anthropic) + registry.
- `src/keel/skills.py` — SKILL.md loader; never executes skill bodies.
- `resources/default-skills/` — vendored Apache-2.0 Anthropic skills (see PROVENANCE.md).
- `tests/` — pytest; `tests/corpus/shell_forms.json` is the Phase 0 corpus.

## Non-negotiables
1. **No new dependencies without a pinned version + lockfile note.** Stdlib-first.
2. **No tool executes without a Tier-1 decision.** `read_file` is not exempt from the gate.
3. **No live network calls in tests.** Fake transport / fixtures only. Live key checks
   belong to `keel provider smoke`, run by the user, never in CI.
4. **No fabricated numbers in docs.** If it wasn't measured, write "not measured".
   Targets are labeled [TARGET]; [ESTIMATE] shows its arithmetic.
5. **The clean-room boundary is absolute.** Never describe Claude Code's internals
   beyond what public docs and black-box observation support; never touch the binary.
6. **Determinism seams stay sealed.** `fakes.py` owns clock/RNG/FS/subprocess; no
   production module may read them directly.

## Phase discipline
- Phase 0 artifacts feed Phase 3 (Tier 2), not just Phase 1.
- A feature from a later phase (MCP, subagents, compaction, TUI) does not sneak into
  Phase 1 just because it is easy. Deferral lists in the docs exist for a reason.
- If a test fails after a change, the change is wrong until proven otherwise — never
  edit the test to pass.

## Testing
- `python -m pytest -q` from `keel/` must stay green (currently 137 + provider tests).
- Byte-identical determinism: same fixture, same seed ⇒ same stdout across runs.
- New capability ⇒ new test in the same commit. No exceptions for "it's obvious".

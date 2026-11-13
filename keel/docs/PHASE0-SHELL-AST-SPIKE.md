# Phase 0 — Windows Shell-AST Viability Spike (M0 / U-B)

**Date:** 2026-11-12
**Status:** first cut. 128/128 tests pass on this host (Windows 11, Python 3.11.9, Windows PowerShell 5.1 + pwsh) — 120 corpus cases (60 POSIX, 32 cmd, 28 PowerShell) plus 8 invariant tests.
**Owner question:** can a command be decomposed into its *operations* — not its spelling — reliably enough on Windows to enforce a permission rule by effect?

## Verdict (provisional)

**Yes, for the supported subset — and declining the rest is cheap and safe.**
The PowerShell front end uses the platform's own parser
(`System.Management.Automation.Language.Parser`) via a subprocess with the
command on stdin (never argv), so the AST is authoritative and our lexer never
sees it. The POSIX and cmd.exe paths are hand-rolled quote/escape-aware
lexers that decline outside the subset. The all-or-nothing contract holds:
every corpus case yields either a **complete** operation set or a `Decline`;
there is no partial answer, and a subcommand-dropping parse cannot be returned
by construction (a raise aborts the whole analysis).

This retires U-B at the *viability* level. It does **not** make the Windows
AST production-safe: see "What this does not yet prove" below before treating
M8 (shell matching) as achievable from this code alone.

## What was built

| Artefact | Path |
| :- | :- |
| Decomposer + classifier | `keel/src/keel/shell_ast.py` |
| Corpus (120 cases, 3 shell families) | `keel/tests/corpus/shell_forms.json` |
| Corpus runner + invariant tests | `keel/tests/test_shell_ast.py` |

Classification axes (effect, not verb): `read · mutate_local · execute ·
network · process_control · irreversible`. Compounds (`; && || |`, including
cmd's lone `&`) are split and every subcommand evaluated; redirections to a
file target are counted as `mutate_local`; fd-dups (`2>&1`) are not; wrappers
(`env sudo nice time xargs nohup command stdbuf watch`, `bash/sh -c`,
`cmd /c`, `powershell[.exe] -Command`) are stripped and `-c` chains are parsed
recursively; `VAR=value` prefixes are stripped (POSIX); PowerShell aliases are
canonicalised (`rm/del/erase/ri → Remove-Item`, etc.); `git`/`reg` subcommands
are matched two-word (plus `git reset --hard` three-word).

## Results on this host

| Shell family | Cases | Pass | Notes |
| :- | :- | :- | :- |
| POSIX (lexer) | 60 | 60/60 | declines `$()`, backticks, `<<` here-docs, `VAR=value`-only, empty/truncated compounds |
| cmd.exe (lexer) | 32 | 32/32 | declines `%VAR%`, `!delayed!`, parenthesised blocks |
| PowerShell (real AST) | 28 | 28/28 | declines dynamic command names (`& $exe`) and parser errors; finds commands inside pipelines/scriptblocks; redirections classified |
| **Total** | **120** | **120/120** | `python -m pytest tests/test_shell_ast.py` → 128 passed (incl. 8 invariant tests) in ~24 s |

## Decisions that need review (not silently inherited)

1. **Indeterminate → `mutate_local`.** The FINAL-APPROVAL-GATE rule is followed
   literally: an unparseable/unknown effect is `mutate_local`. A read of that
   rule applied to *unknown commands* (`./deploy.sh` → `mutate_local`)
   overstates danger for genuinely inert oddities and understates nothing. The
   alternative (`execute`) is defensible; this needs a security-owner call.
2. **Redirection = mutation.** `ls > ~/.bashrc` classifies as `read +
   mutate_local`, not `read`. Any `>`/`>>` with a file target counts; `<`
   counts as `read`; `2>&1` counts as nothing.
3. **`unknown cmd constructs decline`:** `%VAR%`, `!x!`, `()` blocks, `^`
   handling is minimal (escape char only).
4. **Wrapper flag stripping drops unknown flags without validation.** A flag
   cannot change the effect class of the wrapped command, so this is safe for
   classification — but if a wrapper *silently rewrites* the command (e.g.
   `sudo -u`) we consume the right number of tokens only for a small known
   table (`-u -g -h -n -o -e -i -p`); anything else with an unknown
   arity is a candidate for mis-strip. Mitigation for now: decline-prone
   review in Phase 3; the corpus pins the common shapes.
5. **`reg delete` → `mutate_local`** (chosen because registry deletes are
   routinely recoverable via backup/restore semantics); if unacceptable, it is
   a one-line table change to `irreversible`.
6. **`dd of=` → `mutate_local`**; block-device destruction is not
   special-cased yet (table-only classification).
7. **PowerShell per-call cost ≈ 150 ms** (subprocess spawn). Fine for a gate;
   Phase 3 should keep a persistent parser or an in-process runspace.

## What this does not yet prove (honest limits)

- The **≥2,000-command differential corpus** required by risk-register R-01
  (canonical PowerShell, aliases, pipelines, redirections, here-strings,
  sub-expressions, `&&`/`||`, encoded-command forms) does not exist yet. This
  spike ran 120 hand-written cases.
- **Here-strings, sub-expressions, encoded commands (`-enc`)** are not
  handled; they decline (safe) but are not yet classified.
- **Attribute flags** (`-Force`, `-Recurse`) are not interpreted; the table is
  command-name + subcommand only.
- **The `cmd` family is tokenised by our lexer, not by a real cmd parser.**
  For anything with nested expansion or blocks, the correct answer is what it
  gives: `Decline`.
- Cross-platform (macOS/Linux) behaviour untested — U-E remains open.
- This is *effect classification for a permission gate*, not a shell executor.
  It does not evaluate expressions, expand variables, or resolve paths.

## Consequences for the plan

- **U-B: provisionally retired** (viability shown, not productionised).
- **M0** can be signed off for the spike, subject to the six review decisions
  above.
- **M8** requires: the 2,000-case corpus, encoded-command handling,
  here-string/subexpression policy, and the alias-table expansion process —
  all Phase 3.
- The **Tier-1 evaluator** already consumes this classifier
  (`permissions.operation_class_for`); indeterminate commands flow to
  `mutate_local` → mode policy → (print mode) `consent_required` deny, which is
  the safe default for CI.

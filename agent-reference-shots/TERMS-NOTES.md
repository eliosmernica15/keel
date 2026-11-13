# Compliance boundary for this investigation

Established 2026-10-21, before any inspection was performed.

## Applicable terms

Claude Code is a proprietary, closed-source product. Two instruments apply:

- **Anthropic Consumer Terms of Service, Section 3** — prohibits users from
  "decompile, reverse engineer, disassemble, or otherwise reduce our Services
  to human-readable form, except when these restrictions are prohibited by
  applicable law."
- **Anthropic Commercial Terms of Service, Section D.4** — prohibits reverse
  engineering or duplicating the Services; also bars using the Services to
  build a competing product or to train competing AI models.
- **code.claude.com/docs/en/legal-and-compliance** — "The Claude Code binary
  must not be modified. Claude Code must be installed and run as published by
  Anthropic."
- Enforcement precedent: Anthropic issued a DMCA takedown (reported April 2025)
  against a developer who de-obfuscated the bundled JS source and republished it.

Source: https://code.claude.com/docs/en/legal-and-compliance
        https://raw.githubusercontent.com/anthropics/claude-code/main/LICENSE.md
        https://www.anthropic.com/legal/commercial-terms

## Consequence for this task

**Prohibited, and NOT performed:**
- Decompiling / disassembling `claude.exe` or the bundled `versions/2.1.306` blob
- Extracting, de-minifying, or de-obfuscating the bundled JavaScript source
- Dumping source maps, or recovering the proprietary function bodies
- Modifying the binary in any way
- Reading credential stores, keychains, licence files, or account data
- Reverse-engineering the Anthropic model gateway to reproduce private APIs

**Permitted, and IS the method used here:**
- Publicly documented functionality (code.claude.com/docs, Anthropic legal pages)
- Direct black-box observation: running the published CLI and recording what it
  does, prints, and returns
- The product's own self-description surfaces (`--help`, `doctor`, `mcp`,
  `plugin`, `agents`, `auto-mode` subcommands, `--output-format json`)
- Recording the interface as a user sees it (terminal captures / screenshots)
- Observing traffic on the account's own API boundary, insofar as it is the
  documented Messages API

## Note on REA applicability

REA was used only in its **process/terminal-capture** mode: launching the
published binary and recording its terminal output and screen. REA's
decompilation, disassembly, JavaScript-source-recovery, and native-binary
analysis facilities were deliberately **not** invoked against Claude Code,
because doing so would breach the terms above and would also destroy the
clean-room property this study requires.

The two considerations agree, which is convenient: a clean-room reimplementation
and the licence boundary point to the same methodology.

## Environment note

This machine runs Claude Code 2.1.306 (native build) against a **custom
`ANTHROPIC_BASE_URL`** — a third-party model gateway serving
`minimax/minimax-m3.1-flash:free`, not `api.anthropic.com`. `claude doctor`
confirms: "Not connected to the Anthropic API (api.anthropic.com)".
Consequences for the study are recorded in the report.

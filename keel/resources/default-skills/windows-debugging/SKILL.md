---
name: windows-debugging
description: Diagnose Windows console, PowerShell, and build-tool failures on this class of host (ConPTY, pwsh 7 vs Windows PowerShell 5.1, winget, PATH, encoding). Use when a command fails only on Windows, when ANSI color codes or mojibake appears in tool output, when a tool hangs waiting for input, or when bash-isms break under cmd/powershell.
when_to_use: A build, test, or CLI command fails on Windows but would pass on Unix; a path with spaces breaks a script; mouse-reporting sequences style sequences pollute output; winget/npm/pip produce encoding errors; git-bash mixed into PowerShell sessions.
allowed-tools: [run_shell, read_file]
argument-hint: <the failing command or the exact error text>
---

# Windows Debugging

A short, battle-tested playbook for Windows hosts. Follow it in order; stop at the
first step that fixes the issue.

## 1. Identify the shell you are actually in
- `$PSVersionTable.PSVersion` — 5.1 (Windows PowerShell) vs 7.x (pwsh). Syntax
  that works in one breaks in the other (`&&` chains, heredocs, `$env:VAR` quoting).
- `echo $env:ComSpec` / `$env:SHELL` — cmd.exe vs a POSIX layer.
- When in doubt, prefer `pwsh -NoProfile -Command` for reproducibility, or
  `cmd.exe /d /c` for bit-exact legacy behavior.

## 2. Read the actual bytes, not the rendered text
- `Get-Content -Raw file | Format-Hex | Select-Object -First 4` — check for BOMs,
  CRLF vs LF, and UTF-16 (`FF FE`). Python with `open(..., encoding='utf-8')`
  will raise `UnicodeDecodeError` on UTF-16; Node will not.
- `[Console]::OutputEncoding` vs `[Console]::InputEncoding` — set both to
  `[Text.Encoding]::UTF8` if you see mojibake (`â€”`, `Ø§`).

## 3. Paths and quoting
- Quote every path with spaces. In PowerShell use single quotes; in cmd use double
  quotes and escape inner quotes with `\"`.
- `%PATH%` and `$env:Path` — inspect with
  `$env:Path -split ';' | Select-String -Pattern 'node|python|cargo'`.
- `where.exe <tool>` shows path resolution conflicts (e.g. Python from
  `WindowsApps` shadowing a real install).

## 4. Processes and ConPTY
- A process that "hangs forever" is usually blocked on **stdin**, not slow.
  Add `< NUL` (cmd) or `$null |` (PowerShell) to close stdin.
- Node and Python under ConPTY: set `NODE_DISABLE_COLORS=1` and
  `PYTHONIOENCODING=utf-8` to strip ANSI noise and encoding crashes.
- For CI-like runs, `$env:TERM='dumb'` suppresses interactive renderer output.

## 5. winget / npm / pip specifics
- `winget list | Select-String python` beats guessing what's installed.
- npm: `npm config get prefix` and check it is on PATH before debugging `npx` errors.
- pip: use the same interpreter you test with — `python -m pip` is never ambiguous.

## 6. When it is a real bug
Capture, in order: shell + version, exact command, exact stdout/stderr bytes
(`2>&1 | Tee-Object log.txt`), exit code, and whether it reproduces under
`cmd.exe /d /c` vs `pwsh -NoProfile -Command`. That bundle is what any maintainer
needs — file it before poking any further.

## Rules
- Never run a fix you have not scoped: prefer `--dry-run` flags (`winget install
  --dry-run`) before anything mutating.
- Do not edit PATH or registry keys without showing the user the old and new value
  and confirming.
- Do not treat a workaround (alias, shim, detour) as a fix; name it as one.


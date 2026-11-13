# Sanitized workflow captures — auto mode configuration (Claude Code 2.1.306)

All commands were run in a scratch directory on this host. No credentials, tokens,
account identifiers, or personal paths are included. The `$HOME` used in items 6-7 was
a throwaway directory created for the probe.

## 1. Effective config equals defaults when no user `autoMode` block exists

`claude auto-mode config` -> same rule counts as `claude auto-mode defaults`:
`allow`=17, `soft_deny`=72, `hard_deny`=1, `environment`=21.

## 2. `$defaults` splicing (`--settings` scope, inline JSON)

```
claude --settings override.json auto-mode config
```

`override.json`:

```json
{
  "autoMode": {
    "environment": ["$defaults", "Source control: github.example.com/acme-corp"],
    "soft_deny": ["Never run terraform apply"]
  }
}
```

Result: `environment` = 22 (21 defaults + 1 custom), `soft_deny` = 1 — the 72 built-in
soft-deny rules were **replaced**, because that array had no `"$defaults"` token.

## 3. `$defaults` splice position is literal

`environment` = `["FIRST_CUSTOM_ENTRY", "$defaults", "SECOND_CUSTOM_ENTRY"]` produced
23 entries: `env[0]` = FIRST_CUSTOM_ENTRY, `env[1..21]` = the built-in entries,
`env[22]` = SECOND_CUSTOM_ENTRY. The token is replaced in place.

## 4. Scope combination is additive (user scope + `--settings`)

- user `settings.json` `soft_deny` = `["$defaults", "USER_SCOPE_RULE"]`
- `--settings` `soft_deny` = `["$defaults", "SETTINGS_FLAG_RULE"]`

Result: `soft_deny` = 72 defaults + USER_SCOPE_RULE + SETTINGS_FLAG_RULE = 74. The
`--settings`-scope entry was last; the user-scope entry second-to-last.

## 5. Project scope is NOT read

A project-level `.claude/settings.json` containing
`{"autoMode":{"allow":["PROJECT_SCOPE_ALLOW_RULE"]}}` produced `allow` = 17 (the
defaults) and `PROJECT_SCOPE_ALLOW_RULE` was **absent** from the effective config.

## 6. User scope IS read

A throwaway `$HOME/.claude/settings.json` containing
`{"autoMode":{"allow":["USER_SCOPE_ALLOW_RULE"]}}` produced `allow` = 1 (defaults
replaced, since no `"$defaults"` token) and `USER_SCOPE_ALLOW_RULE` was present.

## 7. `reset` removes only the `autoMode` section

```
before: {"theme":"dark","autoMode":{"soft_deny":["$defaults","R"]},"permissions":{"allow":["Bash(echo *)"]}}
after : {"permissions":{"allow":["Bash(echo *)"]},"theme":"dark"}
```

`claude auto-mode reset --yes` printed:

```
This resets auto mode to the shipped defaults by removing the autoMode section from
<...>\.claude\settings.json:
  - soft_deny (2 entries)
Auto mode configuration reset to defaults - autoMode section removed from <...>\.claude\settings.json.
Run `claude auto-mode config` to see the effective rules.
```

The sibling keys `theme` and `permissions` survived; only `autoMode` was removed.

## 8. `defaults` is unaffected by `--settings`

`claude --settings override.json auto-mode defaults` was byte-identical to plain
`claude auto-mode defaults` (72 `soft_deny` entries in both).

## 9. `critique` with no custom rules

```
No custom auto mode rules found.

Add rules to your settings file under autoMode.{allow, soft_deny, hard_deny, environment}.
Run `claude auto-mode defaults` to see the default rules for reference.
```

With a custom rule supplied via `--settings`, the command printed
`Analyzing your auto mode rules...` and then `No critique was generated. Please try again.`
(the review is a separate model call; on this host it did not return a critique).

## 10. `reset` with no `autoMode` section

`claude auto-mode reset` -> `Auto mode configuration is already at defaults - <path> has
no autoMode section.` (exit code 0).

## 11. Live classifier denial observed on this host (auto mode active)

- Attempt: write a `.claude/settings.json` containing an `autoMode` block.
  Result: `Permission for this action was denied by the Claude Code auto mode classifier.
  Reason: [Self-Modification]`
- A second attempt writing the same file with an empty `autoMode` object `{}` was
  **allowed**.

=> The `Self-Modification` `soft_deny` rule is live and inspectable on this build, and
it distinguishes widening the agent's own config from merely touching it.

## 12. `ask` rules are evaluated before the classifier (cross-check)

- `permissions.ask = ["Bash(mkdir *)"]` + `--permission-mode auto`: the model's
  **Bash** call was denied by the permission system ("the Bash tool call was denied
  permission, so I used PowerShell's `New-Item` instead"). The subsequent
  **PowerShell** call was not covered by that rule, so it went to the classifier,
  which returned the documented no-verdict error (see item 13).
- `permissions.ask = ["PowerShell(mkdir *)"]` + `--permission-mode auto`: the
  PowerShell `mkdir` call executed with no classifier round trip and no no-verdict
  error.

=> INFERRED: an ask rule that matches the tool call short-circuits the classifier for
that call; a non-matching ask rule leaves the call to the classifier. This matches the
documented "evaluated before the classifier" ordering. The evidence is a differential
observation on one gateway build, not a direct trace of classifier invocation count.

## 13. A classifier round trip is observable and can fail with a named error

With `--permission-mode auto` and a rule that needed classifying, a session returned:

```
minimax/minimax-m3.1-flash:free is temporarily unavailable (timed out), so auto mode
cannot determine the safety of PowerShell right now. Wait a moment and then try this
action again. ...
```

This is the documented "no verdict" path
(`https://code.claude.com/docs/en/errors#auto-mode-cannot-determine-the-safety-of-an-action`),
exercised against a non-Anthropic gateway. Note the trailing sentence: read-only
operations continue to work without the classifier.

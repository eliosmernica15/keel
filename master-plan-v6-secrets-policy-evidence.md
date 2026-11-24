# Master Plan v6 — Secrets & Policy Hardening Evidence

Agent 19-20 (permissions, policy and secrets specialist) · worktree `agent/f-secrets`
Baseline: `cc6240e4bd707b05bfeb650ff57c9e808ab605b1`

All credentials used in reproduction and tests are **synthetic, non-functional
placeholders** (fake AWS-shaped, Slack-shaped and generic strings). No real
secret value appears in code, test output, or this evidence file.

## Test environment note

`keel` is also installed editable from a different workspace, so every pytest
run below uses `PYTHONPATH=src` from `keel/` to guarantee the edited worktree
source is imported. Verified with `python -c "import keel; print(keel.__file__)"`
→ `...worktree\final\secrets\keel\src\keel\__init__.py`.

---

## Weaknesses found and fixed

### W1 — Redaction missed live credential families (`redaction.py`)

**Reproduction (real functions, baseline):** `redaction.redact_text()` returned
the input unchanged and `check_output_dlp()` returned `[]` for a synthetic
AWS **temporary** access key (`ASIA` + 16 chars) and a Slack **enterprise**
token (`xoxe-...`). The AWS pattern covered only `AKIA` (long-term) and the
Slack pattern covered only `xox[baprs]`.

**Impact:** both outbound redaction and output DLP silently passed these live
credential formats to providers / to persisted files.

**Fix:** widened the AWS pattern to the full access-key-ID family
(`AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA|AGPA|APKA` + 16 chars) and the Slack
pattern to include `xoxe-`. Specific patterns only — ordinary text remains
unchanged (existing `test_ordinary_text_is_unchanged` still passes).

**Tests:** `test_redaction_masks_aws_temporary_and_long_term_keys`,
`test_redaction_masks_slack_enterprise_tokens`.

### W2 — `merge_import(include_keys=True)` stored imported keys in plaintext (`settings_store.py`)

**Reproduction:** `settings_store.merge_import({"providerKeys": {"google":
{"key": <synthetic>}}}, include_keys=True)` wrote the raw key into
`settings.json` with no `enc` marker, bypassing the AES-256-GCM-at-rest
guarantee that `save_provider_key()` provides.

**Fix:** imported plaintext keys are now encrypted with
`secret_store.encrypt_secret()` and stored with `ENC_MARKER`. Already-encrypted
imported entries are preserved verbatim (no double encryption), and an
existing hint is retained.

**Test:** `test_merge_import_encrypts_imported_provider_keys`.

### W3 — Master key file created world-readable before chmod (`secret_store.py`)

**Reproduction:** an `os.open` spy showed **zero** `os.open` calls with an
explicit mode while creating `master.key`; the baseline used
`Path.write_text()` (umask mode, typically 0644) and only then `os.chmod(0600)`,
leaving a group/world-readable window containing the master encryption key.

**Fix:** added `create_private_file()` which creates with
`O_WRONLY|O_CREAT|O_EXCL` (+ `O_NOFOLLOW` where available) and mode `0600` in a
single step. Existing files are tightened before being rewritten.

**Test:** `test_master_key_file_created_atomically_owner_only` (stubs the OS
keyring and passphrase for determinism).

### W4 — Settings temp file / backup written with permissive mode (`settings_store.py`)

**Reproduction:** same `os.open` spy showed no explicit mode for the `settings.json.tmp`
staging file, and `save()` never hardened `settings.json.bak` — both can
contain encrypted-but-sensitive configuration and the backup inherits legacy
permissive modes via `shutil.copy2`.

**Fix:** the temp file is now created via `os.open(..., 0o600)` (with `O_TRUNC`
for stale-temp robustness) and hardened before `replace()`; the rolling backup
is hardened after `copy2`. Final `settings.json` remains hardened.

**Tests:** `test_settings_temp_file_created_atomically_owner_only`,
`test_settings_backup_is_hardened`.

### W5 — Binding policy evaded by absolute executable paths (`policy_enforcement.py`, `exec_policy.py`)

**Reproduction:** with a saved `default` policy forbidding
`git reset --hard`, `enforce("run_shell", {"command": "git reset --hard"}, ...)`
denied, but `"/usr/bin/git reset --hard"` and `C:\bin\git.exe reset --hard`
both returned `None` (allowed). Root causes: `enforce()` called
`policy.check(command)` without `resolve_host_executables`; the Windows branch
of `ExecPolicy.check()` collapsed the **entire** command into one token;
`_host_matches()` did not strip `.exe`-style extensions; and it referenced an
unbound `resolved` when no path constraint existed.

**Fix:** `enforce()` now checks with `resolve_host_executables=True`;
`_split_windows_command()` keeps the executable path intact while tokenizing
arguments; `_host_matches()` resolves basenames with common executable
extensions and initializes `resolved = None`.

**Tests:** `test_absolute_executable_path_cannot_evade_forbidden_rule`
(parameterized POSIX + Windows),
`test_windows_host_executable_tokenization_keeps_command_arguments`.

### W6 — Saved policy's `prompt` default failed open for egress (`policy_enforcement.py`)

**Reproduction:** with a policy containing only an explicit host rule, an
unlisted HTTPS host produced `evaluate_network() == PROMPT`, but `enforce()`
returned `None` for both interactive and non-interactive calls. In
`bypassPermissions` mode this fell through to the mode baseline and **allowed**
the egress. Commands already treated `prompt` correctly.

**Fix:** the network branch now mirrors the command branch:
`forbidden → deny`; `prompt` → allow only with recorded `confirmed`, else
`ask` when interactive, else `deny`; `allow → allow`.

**Tests:** `test_unlisted_network_host_denied_without_interactive_approval`,
`test_unlisted_network_host_asks_with_interactive_approval`.

### W7 — Policy file check/read TOCTOU and non-atomic, world-readable save (`exec_policy.py`)

**Reproduction:** `active_policy()` used `is_file()` followed by `read_text()`;
a file vanishing or being swapped in between raised `FileNotFoundError` out of
the permission evaluator. `ExecPolicyStore.save()` wrote directly to the final
path with default umask mode, so a concurrent reader could observe a truncated
document (which parses as an empty, effectively permissive policy).

**Fix:** ported the lead's remediation and strengthened it:
- `read_policy_doc()` reads exactly once under `_POLICY_IO_LOCK` from the
  in-memory byte snapshot; no `is_file()` pre-check; missing files return
  `None`.
- `active_policy()` and `load_policy()` use `read_policy_doc()` + `from_dict()`.
- `ExecPolicyStore.save()` writes to a `secrets.token_hex`-suffixed temp file
  created with mode `0600` via `os.open`, then `os.replace()` (5 retries with
  backoff and temp cleanup on `OSError`). `self._lock` added per store.

**Tests:** `test_active_policy_handles_file_vanishing_between_check_and_read`,
`test_policy_save_writes_atomically_owner_only`,
`test_provider_config_file_created_owner_only` (`secret_providers.py` config
file now also created with `0600`).

---

## Port of lead-identified origin/main remediation (explicit)

The lead identified two failures in the shared branch:
`test_policy_bypass_regression.py::test_command_from_covers_argv_code_prompt`
and `::test_saved_policy_denies_argv_capability` — argv[]-based capabilities
(`core.os.sandbox.run`) bypassed the policy boundary.

Ported into my two owned files (merged with the hardening above, not
overwritten):

1. `policy_enforcement.py`: `COMMAND_FIELDS` extended with
   `argv, args, code, prompt, script, input`; `command_from()` joins non-empty
   list/tuple members with spaces; `active_policy()` uses `from_dict` +
   `read_policy_doc`.
2. `exec_policy.py`: added `os, secrets, threading, time` imports and
   `_POLICY_IO_LOCK`; added `read_policy_doc()`; `load_policy()` uses it;
   `ExecPolicyStore.__init__` gained `self._lock`; `save()` stages through a
   random temp file + `os.replace` with retry/backoff and temp cleanup. The
   staged temp file additionally uses explicit mode `0600`.

Companion files `sandbox_policy.py` / `webapp.py` and the three new regression
test files are owned by the lead and were **not** modified/committed here; for
verification they were temporarily taken from `origin/main` and then restored.
The two policy-bypass tests pass with this port.

---

## Test results

New regression suite (14 tests) against **baseline** source: `14 failed` —
every weakness reproduced. Against fixed source: `14 passed`.

Targeted suite (exact command):

```
cd .../secrets/keel
$env:PYTHONPATH = "src"
python -m pytest -q tests/test_secrets_policy_hardening.py tests/test_redaction.py `
  tests/test_secret_storage.py tests/test_secret_providers.py tests/test_exec_policy.py `
  tests/test_policy_enforcement.py tests/test_security_validation.py
```

Result: **68 passed** (14 new + 54 pre-existing), 0 failed.

Lead's ported tests plus targeted suites (with the lead's companion files
temporarily applied):

```
python -m pytest -q tests/test_policy_bypass_regression.py `
  tests/test_security_remediation.py tests/test_sandbox_multipath.py `
  tests/test_exec_policy.py tests/test_policy_enforcement.py `
  tests/test_secrets_policy_hardening.py
```

Result: **48 passed**, 0 failed. Specifically
`test_policy_bypass_regression.py::test_command_from_covers_argv_code_prompt`
and `::test_saved_policy_denies_argv_capability` now pass.

Full suite: **1299 passed, 49 skipped, 8 failed** in 555 s. The 8 failures are
unrelated to this work: 6 reproduce identically on pristine baseline source
(release-manifest / checksum / airgap-bundle / plan-hash checks that depend on
worktree-absent build artifacts), and 2 were transient HTTP socket timeouts
that passed on a targeted retry against baseline. No owned-file regression was
observed.

## Referred to lead (out of scope — exact location)

- `keel/src/keel/capability_registry.py:718-725` — `_execpolicy_activate` only
  validates and reports a named policy; unlike the CLI (`cli/main.py:755-761`)
  it never copies the named document to `exec-policies/default.json`, so a
  capability-driven "activate" of a non-default name does not actually bind it.
- `keel/src/keel/capabilities.py:99-103` — `confirmed` is taken from arbitrary
  caller-supplied `context["confirm"]`, so a caller can satisfy a policy
  `prompt` without a real interactive approval. Consider gating it on a trusted
  confirmation workflow.
- `keel/src/keel/cli/main.py:755-761` — CLI `activate` uses non-atomic
  `write_bytes` for `default.json`; it would benefit from the same
  `read_policy_doc` / atomic-write helpers now in `exec_policy.py`.

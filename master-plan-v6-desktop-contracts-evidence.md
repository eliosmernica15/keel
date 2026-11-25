# Desktop lifecycle, isolation and release/upload contracts (E5.x) — evidence

Branch `agent/a7-e5`, baseline `a454640`. New files only (no existing file edited):
`keel/src/keel/desktop_contracts.py`, `keel/tests/test_desktop_contracts.py`,
this evidence document.

Implemented IDs (all six `not_started` **P0** E5.x rows in `PLAN-INDEX.json`):
**E5.1, E5.4, E5.9, E5.12, E5.14, E5.15**. All use `implementation_tier:
local_module`, so the deliverable is pure descriptors/policies in the stdlib —
no network, no subprocess, no filesystem writes, no real credentials.

## 1. What each row now has

| ID | Contract in `keel.desktop_contracts` | Property enforced |
| --- | --- | --- |
| E5.1 | `framed_transport_descriptor()`, `assert_no_listening_port()`, `encode_frame()` / `decode_frames()` | Bundled-child backend; length-prefixed framed bytes for requests and streaming responses with a 16 MiB frame cap and partial-frame buffering (backpressure); Node IPC is `lifecycle_control_only`; assets via `app://`; `listening_port=None`, `loopback_tcp=False`, decision `C-19` (loopback + token stays in web/CLI). A descriptor with a port or loopback fails closed. |
| E5.4 | `single_instance_lock_descriptor()`, `SingleInstanceGuard`, `shared_product_data()`, `desktop_only_state()`, `plugin_environments()` | Process-lifetime lock acquired *before* any profile access; profile is desktop-exclusive; a second instance or access to a different profile is rejected. CLI/desktop share only sessions, settings, credentials, workspaces; executable packages, plugin activation, lockfiles and site-packages are desktop-only; separate desktop/CLI plugin environments. |
| E5.9 | `plugin_install_decision()`, `INSTALL_TIME_HOOKS` | Reject-by-default for any install-time lifecycle script (`setup.py`, build, pre/post install, etc.) and for sdists (which build at install time). Only an exact reviewed `(name, version)` allowlist pair admits a scripted/sdist plugin. Clean wheels without scripts are allowed ("prefer wheels only"). Missing identity fails closed as a rejection decision. |
| E5.12 | `target_build_layout()`, `assert_target_confined()`, `shared_cache_entry()`, `verify_shared_cache()` | Each target owns `targets/<target>/{inputs,runtime,seed,artifacts}`; two targets' layouts are disjoint. Path confinement normalises `..` and rejects absolute/backslash/cross-target paths and the shared `targets/` parent. The shared download cache is addressed by name **and** SHA-256; a name or hash mismatch is refused. |
| E5.14 | `find_upload_secrets()`, `is_upload_secret_env()`, `assert_no_upload_secret()`, `strip_upload_credentials()`, `packaging_env()`, `build_completion_record()` | Packaging env is provably credential-free: exact secret names plus suffix patterns (`_TOKEN`, `_SECRET`, `_PASSWORD`, `_API_KEY`, `_ACCESS_KEY`, `_PRIVATE_KEY`, `CREDENTIALS`, case-insensitive) are stripped into a copy and re-asserted clean. A target completion record is produced only when every build/sign step reports success; a failed or empty step list raises `StepIncompleteError`. |
| E5.15 | `authorize_upload()`, `UploadPlan`, `channel_metadata_name()`, `assert_no_deletes()` | The uploader first checks the completion record against environment, target, public URL, version, channel and `complete` flag, then checks artifact names, sizes and SHA-512 — all **before** invoking the injected `credential_reader`. The plan puts immutable versioned artifacts first and channel metadata last with `cache_control=no-cache`; no delete operations and `retains_history=True`. Stable and prerelease use distinct channel files (`stable.json`, `prerelease.json`). |

## 2. Adversarial coverage (`keel/tests/test_desktop_contracts.py`, 30 tests)

- **Secret leakage:** a dirty packaging env (upload token, AWS secret, GitHub
  token, notarisation password) is detected and named; `assert_no_upload_secret`
  raises; the stripped copy passes the proof and preserves benign vars without
  mutating the original. Lowercase names and obfuscated patterns
  (`MY_API_KEY`, `CLIENT_SECRET`, `AWS_SESSION_TOKEN`, `KEEL_PRIVATE_KEY`,
  `AWS_ACCESS_KEY_ID`) are also caught.
- **Path / record mismatch:** cross-target paths, `..` traversal, the shared
  parent, absolute/backslash paths and invalid target names are rejected;
  cache name/hash substitution is refused. For E5.15, each of environment,
  target, public URL and version is parameterised as a mismatch, plus artifact
  name, size and SHA-512 substitution — and the injected credential reader is
  a `pytest.fail` callback, so any read before validation fails the test.
- **Rejected scripts:** every install-time hook is rejected by default; unknown
  hooks and sdists are rejected; allowlist mismatches (wrong version, wrong
  name, blank version) do not authorise a script.
- Additional fail-closed checks: listening port / loopback reintroduction,
  partial frames never dispatched, oversized frames, lock-before-access /
  double-acquire / wrong-profile access, and incomplete completion records.

## 3. Test commands and results

Run from the worktree root with `sys.path` inserted (an editable install in the
environment points at the original clone):

```
python -c "import sys; sys.path.insert(0, r'<worktree>\keel\src'); import pytest; sys.exit(pytest.main(['-q','keel/tests/test_desktop_contracts.py']))"
```

- New suite only: **30 passed**.
- Neighbouring sanity set (`test_desktop_contracts.py`, `test_desktop_hardening.py`,
  `test_desktop_artifacts.py`, `test_release_no_secrets.py`,
  `test_release_integrity.py`): **51 passed, 3 skipped, 1 failed**. The single
  failure is `test_release_integrity.py::test_integrity_cli_on_real_artifacts`,
  which requires the gitignored generated `keel/dist` and `keel/release`
  directories (missing `RELEASE-SHA256SUMS.txt`, `RELEASE-MANIFEST.json`, etc.).
  It is a pre-existing environment prerequisite documented in
  `master-plan-v6-signing-evidence.md`; it is not caused by and does not touch
  this change. No generated artifacts were created or committed.

## 4. Scope / owner actions (deliberate limitations)

These are pure contract descriptors and policy helpers, as required by the
`local_module` tier. They are **not** a rewrite of the Electron shell or the
CI release workflow. Realising them end-to-end still requires the owning teams
to: bind the framed transport to actual child-process stdio, acquire a real OS
lock on desktop startup, wire `plugin_install_decision` into the plugin
installer, use `target_build_layout` in the build jobs, call `packaging_env`
for every packaging subprocess, and invoke `authorize_upload` before the
uploader reads credentials. No credentials, network endpoints or deployment
actions were introduced here.

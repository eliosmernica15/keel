# PROD-MCP — production hardening evidence (MCP / plugins / extensions)

Branch `agent/prod-mcp`, candidate HEAD `e6e7efc`.
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\production\mcp`.
No files outside the owned set were modified; no frontend changes; no push.

## Owned files

| File | Change |
|---|---|
| `keel/src/keel/mcp_contracts.py` | 5 confirmed defects fixed + 4 additive hardening APIs |
| `keel/src/keel/plugin_contracts.py` | 1 confirmed defect fixed + 2 additive hardening APIs |
| `keel/tests/test_prod_mcp.py` | NEW — 50 real tests (permission probe, lifecycle fakes, trust boundaries) |
| `PROD-MCP-EVIDENCE.md` | NEW — this file |

## Audit (what was examined)

* **Manifest/config validation** — `parse_servers` (runtime, not owned), `resolve_search_options`,
  `validate_formatter_config`, `validate_compaction_config`, and the new extension-manifest path.
* **Discovery / capability registration** — `McpManager.tool_schemas`, `tools/list` mapping in
  `keel.mcp`, canonical MCP permission naming, and the new fail-closed discovery registrar.
* **Lifecycle / connection / cleanup** — `McpServer.start/call_tool/health/reconnect/shutdown/_kill`
  and `McpManager.start_all/shutdown_all` exercised with in-process fakes.
* **Compatibility / version** — protocol version was hardcoded in the runtime with no validation;
  added a pure allowlist/policy check at the contract seam.
* **Dependencies** — `PluginPart.dependencies` existed but was never validated; added graph checks.
* **Trust boundaries / permissions / enable-disable / error isolation** — ordered rule evaluator,
  policies layer, extension blocks, plugin DSL, malformed rule handling, secret redaction.
* **SSRF / secret handling** — `validate_fetch_target` (scheme only), HTTP MCP URLs (no validation
  before this change), `{env:...}`/`{file:...}` substitution warnings, `redact_config` / `assert_no_secrets`.

## Confirmed defects fixed (failing-then-passing tests)

The new suite was run **before** any source edit: **41 failed, 9 passed**. All failures were expected
(and are described per defect below). After the fixes: **50 passed**.

1. **HIGH — permission escalation: config `ask` widened to `allow`.**
   `evaluate_permissions` evaluated the policies layer with `default="allow"`. With no matching
   policy rule this produced an implicit `allow` that overrode a config `ask`, so a discovered MCP
   capability that required consent was silently granted. Fixed by treating only *explicit* policy
   rules as having an opinion: explicit policy deny → config deny → explicit policy ask → explicit
   policy allow → config decision → default deny. Tests:
   `test_config_ask_is_not_escalated_to_allow_without_policy_rules`,
   `test_config_ask_survives_an_unrelated_policy_rule`,
   `test_permission_parity_probe_native_and_mcp_capability` (all asserted `ask`, got `allow` before).

2. **MEDIUM — raw `KeyError`/`TypeError` on malformed permission rules.**
   `_as_rule` indexed mapping keys directly; one bad rule from an untrusted config aborted the
   session with an untyped exception. Now normalised to `PermissionRuleError("bad_rule")`.
   Test: `test_malformed_rules_raise_typed_permission_error` (3 of 5 cases failed before).

3. **MEDIUM — unvalidated rule timeout.** `PermissionRule(timeout_seconds="30")` was accepted.
   Now bool/non-int/non-positive values raise `PermissionRuleError("bad_timeout")`.
   Test: `test_rule_timeout_is_type_checked`.

4. **MEDIUM — `PluginPart.from_dict` leaked raw `ValueError`/`TypeError` and silently accepted
   a non-mapping `config` (`[] or {}`).** Now all malformed descriptor data raises typed
   `PartDescriptorError`. Test: `test_plugin_part_from_dict_raises_typed_error`.

5. **GAP (HIGH impact) — no compatibility check.** Added
   `check_protocol_compatibility(version, supported=..., policy=...)`: strict `YYYY-MM-DD`
   shape, known-version allowlist, caller policy seam, typed `McpCompatibilityError`.

6. **GAP (HIGH impact) — SSRF via MCP server URL.** Added `validate_mcp_server_url(...)`:
   HTTP(S) only, no embedded credentials/fragments/control characters, literal loopback / private /
   link-local / multicast / reserved IPs rejected by default, optional explicit host allowlist and
   policy seam. Returns a structured `McpServerUrl`. Tests cover the metadata endpoint
   (`169.254.169.254`), `127.0.0.1`, `[::1]`, RFC1918, `file://`, credentialed URLs and allowlists.

7. **GAP (HIGH impact) — capabilities could self-grant at discovery.** Added
   `register_discovered_capabilities(...)`: every `tools/list` entry is mapped to
   `mcp.<server>.<tool>` and decided by the **same** `evaluate_permissions` used for native rules;
   default deny, `ask` not exposed, forbidden capabilities always denied, malformed entries skipped
   (error isolation), and `assert_unique_mcp_permissions` rejects collisions caused by the legacy
   non-injective `_` sanitizer.

8. **GAP (MEDIUM) — plugin dependencies never validated.** Added
   `PluginRegistry.validate_dependencies()` → missing / self-referential / cyclic dependencies raise
   typed `DependencyError`; returns a stable topological order for a healthy graph.

9. **GAP (MEDIUM) — no extension trust boundary.** Added `ExtensionManifest` and
   `validate_extension_manifest(...)`: safe id/version/kind, forbidden capability set
   (`sampling`, `elicitation`, `roots`, `exec`, `shell`, `spawn`, `write`, `patch`, `network`, ...),
   unsigned / explicitly untrusted / untrusted-publisher rejection, shell-safe command and args,
   caller policy seam; the signature is omitted from `to_dict()` so dumps cannot leak it.

## Permission parity probe (requirement 4)

`test_permission_parity_probe_native_and_mcp_capability` proves both layers:

* contract layer: one rule list containing `tool_use_rule("shell", "git push", "deny")` and
  `mcp_permission_rule("github", "push", effect="ask")` yields `deny` for the native action and
  `ask` for the MCP action — the MCP capability did **not** get widened to `allow`;
* production layer: `keel.permissions.evaluate` receives the mapped MCP name
  `mcp__github__push` and a native `run_shell` through the *same function and rule tuple*;
  an explicit deny wins for both (even in `bypassPermissions` mode), and a capability with no
  allow rule fails closed.

Discovery cannot grant itself permission: `test_discovered_capabilities_do_not_self_grant` shows
that a native `tool.use` allow does not expose an MCP capability; only an explicit MCP rule does.

## Lifecycle / cleanup / secret tests

Using in-process fakes against the real `keel.mcp` runtime (no sockets, no OS subprocess):

* start failure raises `McpError`, kills the process handle, `health()` is false;
* `reconnect()` recovers after a failed start and re-discovers tools;
* a server disabled via `mc.parse_plugin_dsl("active -disabled")` is excluded from `start_all`;
* a stale connection added before disable is shut down by `shutdown_all`, which clears `_clients`;
* one client raising during shutdown does not prevent the others or leak state; `shutdown()` is idempotent;
* substituted secret values stay out of warnings and are redacted by `redact_config`;
  `assert_no_secrets` detects a known secret in rendered config text.

## Verification

```
python -c "import sys,pytest; sys.path.insert(0,'keel/src'); raise SystemExit(pytest.main(['-q','keel/tests/test_prod_mcp.py','keel/tests/test_mcp_contracts.py','keel/tests/test_plugin_contracts.py']))"
=> 146 passed
```

Additional regression check (not required by the task): `test_mcp.py`, `test_mcp_presets.py`,
`test_capability_seams.py`, `test_plugin_contracts.py` → **80 passed**.

## Platform and external limitations (honest)

* **No runtime wiring.** These modules are a contract layer: no socket, subprocess, file write or
  import of an extension happens here. The real `keel.mcp` client still hardcodes protocol version
  `2024-11-05` and does not call `check_protocol_compatibility`, `validate_mcp_server_url` or
  `register_discovered_capabilities` before accepting tools. `keel.mcp` is not an owned file, so the
  integration seam must be wired by its owner; until then the new validators protect only callers
  that invoke them.
* **No DNS / TLS verification.** `validate_mcp_server_url` is purely lexical: it blocks literal
  private/loopback addresses but cannot detect a public hostname that resolves into RFC1918 space
  (DNS rebinding) or validate certificates. The socket-owning layer must resolve, re-check the
  address and enforce host pinning before connecting.
* **No cryptographic signature verification.** Manifest validation checks trust *metadata*, not an
  actual signature or package digest. Verifying signatures and integrity is the installer/platform
  responsibility. `trusted_publishers` is an explicit caller-supplied allowlist, not a PKI.
* **Ask needs an approval workflow.** Discovery records `ask` as not exposed; promoting it to an
  active capability requires the host's approval broker, which is outside this contract layer.
* **Legacy name sanitisation is not injective.** `canonical_mcp_permission` keeps the historical
  `_` substitution for compatibility; `assert_unique_mcp_permissions` rejects collisions at
  registration time, but already-persisted colliding rule names remain ambiguous and need migration.
* **Disable while connected is not automatic at runtime.** The contract-level enabled set plus
  `McpManager.shutdown_all()` are proven by tests; the live manager has no disable hook, so the host
  must apply a disable decision by calling `shutdown_all()` and rebuilding the manager.
* **Transport coverage.** The runtime implements stdio and a minimal JSON-RPC-over-POST HTTP client;
  SSE/streamable-HTTP transports are unbuilt. The lifecycle tests use fakes rather than a real
  MCP server process, so they cover logic, not OS-level signal/kill behaviour.
* **Environment.** Verified with Python 3.11 on Windows 11 (worktree path above). No network or
  real subprocess was used by the new tests.

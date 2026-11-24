# Windows per-process network isolation — implementation evidence (Agent 08)

**Outcome: a real, non-elevated, kernel-enforced network boundary was achieved.**

Host: Windows 10 AMD64, Python 3.11.9, `ctypes.windll.shell32.IsUserAnAdmin() == 0`.
Baseline: `cc6240e4bd707b05bfeb650ff57c9e808ab605b1`, branch `agent/f-win-network`.

A capability-less **AppContainer** process is launchable by a normal user when
the AppContainer SID comes from a real per-user profile created with
`userenv!CreateAppContainerProfile`. `CreateProcessW` +
`PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` then enforces default-deny
network traffic (ALE/WFP) for the child and all descendants that inherit its
token. This disproves the baseline claim that AppContainer requires
`SeImpersonatePrivilege`/`SeAssignPrimaryTokenPrivilege` and fails with
`ERROR_INVALID_PARAMETER (87)` for non-elevated callers.

## 1. APIs attempted and exact results

| # | API / operation | Exact result | Interpretation |
|---|---|---|---|
| 1 | `IsUserAnAdmin()` | `0` | Non-elevated token. |
| 2 | `GetTokenInformation(TokenPrivileges)` for `SeImpersonatePrivilege`, `SeAssignPrimaryTokenPrivilege` | `held_in_token=False` for both; `AdjustTokenPrivileges(SE_PRIVILEGE_ENABLED)` returned `ok=1` with last error **1300** (`ERROR_NO_SUCH_PRIVILEGE` / not all privileges assigned) | Privileges are absent and cannot be enabled. |
| 3 | `DeriveAppContainerSidFromAppContainerName[W]` in `advapi32`, `kernelbase`, `ntdll`, `sechost` | `GetProcAddress` → not exported | Wrong DLLs. PE export scan of `%System32%\*.dll` found it in **`userenv.dll`** (and `DeriveAppContainerSidFromAppContainerNameWorker` in `profext.dll`); `CreateAppContainerProfile` is in `userenv.dll`. |
| 4 | `userenv!DeriveAppContainerSidFromAppContainerName("KeelProbeContainer")` | `HRESULT 0x00000000`, SID `S-1-15-2-686368902-3677269804-1095829968-3264423830-3444018881-2214207247-915348858` | Derivation itself needs no elevation. |
| 5 | `SECURITY_CAPABILITIES{CapabilityCount=0}` + `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` (`0x00020009`) with a **fabricated** SID `S-1-15-2-1-2-3-4-5-6-7-8` | `UpdateProcThreadAttribute` OK; `CreateProcessW` failed with **ERROR 4250** (`0x109A`, "This operation is only valid in the context of an app container") | A syntactically valid but profile-less package SID is rejected. |
| 6 | Same, with the *derived* SID but no profile created | `CreateProcessW` failed with **ERROR 2** (`ERROR_FILE_NOT_FOUND`) | Profile creation is required, not just SID derivation. |
| 7 | `userenv!CreateAppContainerProfile("KeelProbeProfile", ...)` then `CreateProcessW` with the returned SID + zero capabilities | `HRESULT 0x00000000`; `CreateProcessW` OK; child printed `AC-PROFILE-OK`, exit 0 | **Working mechanism.** No admin, no privilege manipulation, no undocumented API. |
| 8 | AppContainer process with a deliberately **minimal** Unicode environment (only `SystemRoot`, `TEMP`, `TMP`, `PATH`, `NUMBER_OF_PROCESSORS`) | `CreateProcessW` failed with **ERROR 203** (`ERROR_ENVVAR_NOT_FOUND`) | AppContainer needs the ordinary environment (USERPROFILE/APPDATA/ComSpec/...). Implementation uses full `os.environ` minus secret-looking keys; that variant succeeded. |
| 9 | `fwpuclnt!FwpmEngineOpen0` (dynamic session flag `0x1`, `RPC_C_AUTHN_WINNT=10`) | `rc = 0`, engine handle returned | Everyone has `FWPM_ACTRL_OPEN`; opening the engine is not the blocker. |
| 10 | `fwpuclnt!FwpmFilterAdd0` with correct `FWPM_FILTER0` (ALE_AUTH_CONNECT_V4, FWP_EMPTY weight, action `0x1001` BLOCK / `0x1002` PERMIT, zero conditions), both **static and dynamic** sessions | `rc = 5` — **`ERROR_ACCESS_DENIED`** for both actions and both session types | Per-process WFP rules are impossible here. BFE's default DACL grants `FWPM_ACTRL_ADD` only to Administrators / Network Configuration Operators / named services. Wrong action constants (`0x1`, `0x2`, `0x10001`, ...) returned `FWP_E_INVALID_ACTION_TYPE 0x80320024`, confirming the struct was parsed correctly. |
| 11 | Firewall COM `HNetCfg.FwPolicy2.Rules.Add` with an outbound BLOCK rule | `com_error` with embedded HRESULT `0x80070005` (**ERROR_ACCESS_DENIED**); `HNetCfg.FwRule.LocalUser` is read-only ("Property ... can not be set") | Per-user firewall rules also require admin. Not used. |
| 12 | Export scan for `SetNetworkInformation` (found in `IPHLPAPI.DLL`), `NetworkIsolationSetAppContainerConfig` (found in `FirewallAPI.dll`), `AuthzSetAppContainerInformation` (`authz.dll`) | Present, but these configure global/interface/IPsec state or AuthZ contexts — not per-process ALE policy — and require elevation | Not used. |
| 13 | `CreateProcessAsUserW` with the module's restricted token **and** the AppContainer security-capabilities attribute | `ok=1`, exit 0 | Both boundaries can be combined; the shipped implementation uses AppContainer-only for `allow_network=False` so that PowerShell/Python children (which fail to load under the restricted SID) remain usable, and keeps the restricted-token path unchanged for `allow_network=True`. |

## 2. Real child-process behaviour

Everything below used actual child processes, not configuration inspection.

* **Baseline control (no AppContainer):** PowerShell connected to a parent-owned
  TCP listener on `127.0.0.1` → `LOCALHOST=OK`; `DNS=OK` for `example.com`;
  listener accepted the connection.
* **Confined (`allow_network=False`):** `LOCALHOST=FAIL`, `DNS=FAIL`; listener
  accepted **0** connections from the confined process. `SOCKET_CREATE=OK` —
  AppContainer blocks traffic, not the `socket()` API; this is stated in
  `capabilities()['limitations']` and in every `ConfinementResult.limitations`.
* **Inherited token:** AppContainer `cmd.exe` spawned a PowerShell grandchild;
  the grandchild printed `CHILD-LOCALHOST=FAIL` and the listener accepted 0
  connections. The equivalent unconfined control printed
  `CHILD-LOCALHOST=OK` and the listener accepted 1.
* **Filesystem:** confined child read a workspace file (`WORKSPACE-OK`) but
  reading an outside file produced `Access is denied.` and no secret content.
* **Fail-closed:** with `capabilities()['network_enforcement']` forced False,
  `run_confined` raised `SandboxUnavailable` and no marker file was created.

## 3. Implementation

* `keel/src/keel/win_network.py` (new): ctypes-only AppContainer profile/SID
  helpers, `SecurityCapabilities`, `free_sid`, SID-string helper, and a
  `wfp_filter_add_status()` evidence helper that performs the live WFP probe.
* `keel/src/keel/sandbox_windows.py`:
  * `allow_network=False` now creates a per-user AppContainer profile
    (`Keel.Sandbox.NetworkDeny.v1`, created once and deliberately retained),
    grants its SID on the workspace DACL, passes the capability-less
    `SECURITY_CAPABILITIES` attribute, and launches with `CreateProcessW`.
    Job Object, handle list, suspended start and env scrubbing are preserved.
  * `allow_network=True` keeps the original restricted-token path byte-for-byte
    in behaviour (mechanism string `windows-restricted-token+workspace-acl+job-object`).
  * Any failure in the AppContainer path raises `SandboxUnavailable`; there is
    no permissive fallback.
  * `capabilities()` now reports `windows_appcontainer=True`,
    `network_enforcement=True`, `wfp_filter_add_error` from the live probe, and
    `mechanism=windows-appcontainer+workspace-acl+job-object`, with honest
    limitations about `socket()` and WFP.

## 4. Test commands and exact results

Command (worktree root):

```
$env:PYTHONPATH = 'keel/src'
python -m pytest -q keel/tests/test_sandbox_windows.py keel/tests/test_win_network.py
```

Final result:

```
FF.............s...........                                              [100%]
2 failed, 24 passed, 1 skipped in 40.92s
```

New file alone:

```
python -m pytest -q keel/tests/test_win_network.py
...........                                                              [100%]
11 passed in 23.24s
```

Baseline before the change (for comparison): `15 passed, 1 skipped in 13.68s`.

### Two expected failures in `test_sandbox_windows.py`

I did **not** edit that file because it is outside my file ownership. Both
failures are assertions of the obsolete "network enforcement unavailable"
contract that this work intentionally replaced:

1. `test_capabilities_honest_about_network_and_appcontainer` (line 64):
   `assert caps["network_enforcement"] is False` → `assert True is False`.
   The other assertions in that test (limitations contain `blocked`, `network`,
   `firewall`, `job object`, `appcontainer`) still pass.
2. `test_default_call_fails_closed_without_network_enforcement` (line 79):
   `with pytest.raises(SandboxUnavailable)` → `Failed: DID NOT RAISE
   <class 'keel.os_sandbox.SandboxUnavailable'>`; the default call now runs a
   genuinely network-denied child, as requested.

Suggested owner updates: assert `caps["network_enforcement"] is True` and
`caps["windows_appcontainer"] is True` in test 1; replace test 2 with an
assertion that the default call succeeds and that `result.limitations` reports
AppContainer denial (the fail-closed branch is already covered by
`test_fails_closed_when_appcontainer_is_unavailable` in the new file).

The single skip is the pre-existing, environment-gated
`test_main_bootstrap_escape_is_contained` (Python interpreter cannot start
under the restricted SID on this host); it is unrelated to this work.

## 5. Blocker status

No blocker for the achieved mechanism. Residual, honestly documented limits:

* `socket()`/`WSAStartup` calls themselves still succeed; only traffic is
  denied (AppContainer design; a WFP BLOCK filter would still not stop
  `socket()` creation).
* Per-process WFP rule installation is blocked by `ERROR_ACCESS_DENIED (5)`
  for non-elevated callers; firewall COM rule add is likewise blocked
  (`0x80070005`). Neither is needed for the shipped boundary.
* The AppContainer profile persists under the user profile (stable SID). It is
  intentionally not deleted while processes may still hold derived tokens.

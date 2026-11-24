# Master Plan v6 — Independent Final Acceptance Review

Reviewer: independent final acceptance subagent (read-only; no implementation changes).
Worktree: `C:\Users\Admin\.local\share\opencode\worktree\completion\acceptance-review` @ `20bf5c3`.
Completed state inspected read-only via a clean temp checkout of `integration/v6-completion` @ `d9e5d2e` (the baseline worktree lacks `sandbox_macos.py` and the macOS dispatch added after the baseline). No files other than this review were created or modified; nothing was pushed.
All tools executed successfully; every result below was reproduced, not assumed.

## Findings

### [Medium] "Live repository governance" SHA-pinning claim is true only for the local branch, not the live repository
Evidence:
- Local integration checkout: `python wf_local.py` → 4 workflow files, **20/20** `uses:` refs match `@[0-9a-f]{40} # tag`, 0 unpinned.
- All five distinct pins are genuine: `python sha_check.py` → `actions/checkout@v7`, `setup-python@v7`, `setup-node@v7`, `upload-artifact@v7`, `download-artifact@v8` each `MATCH=True` against `gh api repos/<repo>/git/ref/tags/<tag>` (`object.type=commit`).
- Live repo, read-only `gh api` via `python wf_check.py`: **23/23 `uses:` refs are tag-pinned (0 SHA-pinned)** across 7 workflows (default branch `main`).
- `git ls-remote origin refs/heads/integration/v6-completion` → no output (completion branch is not pushed).
- The extra live-only workflows are `lifecycle.yml`, `provider-validation.yml`, `signing-readiness.yml` (4 tag-pinned `uses:` refs). They were added to `origin/main` after the divergence at merge base `107a427`; they were **not** deleted by the completion operation (no `--diff-filter=D` commits in integration history), but they are unpinned on the live remote.

Conclusion: C11.2's "Actions pinned to full commit SHA … PASS" is accurate for the integration branch's code, but the document places it under "Live repository governance (lead verification)". The live repository still has zero SHA pinning. The claim must be scoped to the local branch or the change must be merged/pushed before being reported as live governance.

### [Informational] Feature verification is registry-based plus spot-check, not exhaustive
`python scripts/verify_v6_audit.py` (worktree root) → `registry count: 228 matrix rows: 228; parity identical: True; tier counts: {'operational': 52, 'local_module': 168, 'external_dependency': 3, 'descriptor': 3, 'owner_gated': 2}; verified: 220; flagged: [B4.8,B6.2,B6.3,B6.5,B6.6,C11.1,C11.2,C11.8]; CONSISTENCY OK; EXIT=0`.
This proves internal consistency of the matrix/registry, **not** that 220 implementations exist. Independent spot-check via `keel.capabilities.invoke` (PYTHONPATH pinned to integration `keel/src`): 8 diverse capabilities across core/code/cowork/fleet/web/release/duet returned real structured data (`core.os.sandbox.capabilities`, `code.sandbox.status`, `cowork.tutorial.whats_new`, `fleet.view.activity`, `web.status`, `release.health`, `duet.roles`, `core.flags.list`); `code.sandbox.run` with `allowed_permissions={'read'}` correctly raised `CapabilityError: permission_denied`. Two `{}` results (`release.health`, `core.flags.list`) were traced to real handlers reading empty state, not placeholders. Registry exposes 226 capabilities in the integration tree (the test-evidence doc's 224 is for older baseline `cadb343` — different metric/commit, not a contradiction).

### [Informational] Native sandbox dispatch fix is correct; Linux/macOS enforcement remains locally unverified
`os_sandbox.py::run_confined` lines 255–269 route `os.name == 'nt'` → `sandbox_windows`, `sys.platform.startswith('linux')` → `sandbox_linux`, `sys.platform == 'darwin'` → `sandbox_macos`, each with an early `return _backend(...)`; unsupported platforms fall through to `SandboxUnavailable`. Confirmed by reading all four backend files and `Select-String run_confined`.
Required command: `python -m pytest -q keel/tests/test_os_sandbox.py -k "bpf or dispatched or backends"` → **2 passed, 8 deselected, EXIT=0**.
The BPF regression test is meaningful: `test_inproc_seccomp_filter_layout_is_correct` implements its own `verdict()` interpreter and asserts `verdict(41)=0x50001`, `verdict(42)=0x50001`, `verdict(1)=0x7fff0000`, plus instruction-level layout checks. Caveat: it exercises the legacy in-process builder that is now dead after dispatch; the active Linux backend's `build_network_filter()` is separately tested at `test_sandbox_linux.py:76`.
Full sandbox run: `python -m pytest -q -rs keel/tests/test_os_sandbox.py keel/tests/test_sandbox_linux.py keel/tests/test_sandbox_macos.py keel/tests/test_sandbox_windows.py` → **20 passed, 36 skipped**. Skips are OS/hardware gates (Linux-only, macOS-only, Windows network denial unavailable), disclosed rather than converted to passes. No real Linux kernel or macOS host execution was possible here, so those backends are **UNVERIFIED locally** — consistent with the red-team doc's own verdict.

### [Informational] Test quality: no deletions or weakening found; 10 provider skips legitimate
`git diff --name-status 20bf5c3..integration/v6-completion -- keel/tests` → 7 modified/added files, **no deletions**; `git diff --stat` → 436 insertions, 1 deletion. `git diff --diff-filter=D 20bf5c3..integration/v6-completion` → empty.
The 10 skips in `master-plan-v6-test-evidence.md` are `test_live_smoke.py` 5 providers × 2 parametrized tests, each gated on `KEEL_{OPENROUTER,GOOGLE,NVIDIA,COMPAT,ANTHROPIC}_API_KEY` (`test_live_smoke.py:30-37,58-63`). Legitimate external-credential gates, reported as blocked, not as passes.

### [Informational] Red-team used real processes; Low findings defensible but scoped
`master-plan-v6-sandbox-verification.md` attacks used real `cmd.exe` processes under `sandbox_windows.run_confined(allow_network=True)` with real out-of-workspace secret files (outside read/write, `..` traversal, junction escape, child inheritance, timeout tree kill) — policy-inspection-only is **not** an accurate characterization of the Windows portion. Linux/macOS conclusions are explicitly static/simulated (BPF interpreters, Landlock ABI analysis) and are labelled unverified.
F-02 (env scrubbing is name-heuristic when a caller supplies `env`) and F-03 (transient `Everyone GENERIC_ALL` ACE on the workspace DACL) are correctly Low for the normal per-run temp-workspace use case; F-03 would warrant Medium if a caller supplied a persistent/sensitive workspace. Both are disclosed with reproduction and are not boundary bypasses of a claimed control. F-01 (Windows network unenforced) is correctly Informational because `allow_network=False` fails closed and the doc verifies `capability_registry.py:677` defaults to False.

### [Informational] Release readiness: no fabricated signing identity or device pairing
`master-plan-v6-release-acceptance.md` explicitly reports "Device found: NO", "Signing identity found: NO", `gh api .../actions/secrets` `total_count=0`, no push/publish/signing performed, and names the required owner setup rather than claiming it exists. Independent checks: `git grep -n -E -- '--signing-key|--public-key|secrets\.' -- .github` returns only `secrets.GITHUB_TOKEN` (no signing step); `keel/src/keel/release/common.py:35,39,44` and `publish.py:49` say "Unsigned"; `core.companion.identity` produces only a local URI/certificate with no phone client. No fabrication found.

## Claims challenged

| Major claim | Independent verdict |
| --- | --- |
| 228 IDs / 220 verified / parity / tier counts | **CONFIRMED** — `verify_v6_audit.py` reproduced exactly; 8-capability runtime spot-check passed. Scope: registry consistency + spot-check, not exhaustive proof of all 220. |
| Native sandbox dispatch routes all three platforms to dedicated backends | **CONFIRMED** — read `os_sandbox.py` lines 255–269 and all three backends; grep of `run_confined` matches. |
| BPF regression test is meaningful | **CONFIRMED** — simulates verdicts with an independent interpreter; note it targets the legacy in-process builder, while the active Linux filter has its own test. |
| Sandbox tests prove cross-platform enforcement | **UNVERIFIABLE** locally — 36 skips on this Windows host; Linux/macOS backends never executed. Honestly disclosed by the red-team doc. |
| C11.1 source hosting PASS (private) | **CONFIRMED** live — `gh api repos/eliosmernica15/keel --jq '{private,visibility,fork}'` → `{"fork":false,"private":true,"visibility":"private"}`. |
| C11.2 PARTIAL (branch protection lost, owner-gated controls) | **CONFIRMED** live — `GET .../branches/main/protection` → HTTP 403 "Upgrade to GitHub Pro…", `branches/main` → `{"protected":false}`; 2FA/signed commits/fork policy owner-gated. |
| C11.2 "Actions pinned to full commit SHA … PASS" as *live* governance | **CONTRADICTED** for the live repo (23/23 tag-pinned on `main`); **CONFIRMED** only for the local integration branch (20/20 pinned, 5/5 SHAs genuine). Completion branch is not pushed. |
| No tests deleted, weakened, or converted to skips; 10 skips legitimate | **CONFIRMED** — no `--diff-filter=D` changes; 436 insertions to tests; skips are explicit credential/platform gates. |
| Red-team attacks were real processes, Low findings correctly rated | **CONFIRMED with scope qualification** — real processes on Windows; Linux/macOS static/simulation only, explicitly labelled; F-02/F-03 Low defensible for normal workspace usage. |
| No fabricated signing identity or device pairing | **CONFIRMED** — evidence and independent checks both show none; unsigned releases and blocked owner actions stated plainly. |

## Required fixes before acceptance

1. **Correct the governance evidence before ratifying it as "live"** (Medium; reproduction above). Either (a) merge/push `integration/v6-completion` (or at least the SHA-pinning change) to the live default branch so `gh api` shows 20/20 pinned on `main`, or (b) amend `master-plan-v6-repository-security-evidence.md` to state that the 20/20 SHA pinning is a local-branch result and that the live repository still has 23 tag-pinned `uses:` refs across 7 workflows. No implementation change is needed for the functional claims.
2. **Do not accept Linux/macOS native enforcement as verified** — no code fix is required, but acceptance must retain the documented "unverified locally / requires on-target run" status until a real Linux and macOS host executes `test_sandbox_linux.py` and `test_sandbox_macos.py` (36 skips reproduced here).

## Verdict

- **Master plan completeness: PASS (with scope note).** 228/220 matrix consistency reproduced and runtime spot-checks pass; completeness is evidenced by the audited registry plus sampling, not by re-verifying every one of the 220 implementations.
- **Security hardening: PARTIAL.** Windows filesystem/process/resource enforcement demonstrated with real processes and fails-closed network default; Linux/macOS backends dispatch correctly but are statically/simulated only. Repository action pinning exists on the branch but not on the live remote.
- **Repository governance: PARTIAL.** Live privacy confirmed; loss of branch protection honestly reported; SHA pinning genuine but local-only. C11.2 remains correctly gated/partial, and its "live" characterization needs the correction in Required fixes #1.
- **Production release readiness: NOT READY (owner-gated, honestly disclosed).** No signing identity, no signing CI job, unsigned installers, no device/emulator or phone client, no publishing performed. These are documented blockers, not hidden failures.

# Risk register and rollback plans

> Covers addendum3 X0.9: `RISKS.md` with likelihood, impact, mitigation, owner and a
> revert plan for every milestone kickoff. Scope: the 13 significant milestones
> M0, M1, M2, M5, M11, M12, M15, M17, M19, M22, M23, M25, M26 of the 865-row
> `PLAN-INDEX.json` registry. Evidence for environment-blocked items is from
> `master-plan-v6-final-report.md` and the platform evidence files in this repo.
>
> **Owner** is always a role, never a person. **Rollback** means a concrete revert
> or containment action that can be executed without waiting for a new design.

## 0. Ratings and coverage

Likelihood: **high** (expected on this host / already observed), **med** (plausible
at a gate), **low** (unlikely if mitigations hold). Impact: **fatal** (legal,
safety or release-blocking), **high**, **med**, **low**.

| Required topic | Where it is covered (risk IDs) |
| :- | :- |
| Sandbox platform gaps | M2-R3, M5-R1, M11-R2, M15-R4, M19-R3, M25-R2 |
| macOS read isolation BLOCKED | M17-R4, M19-R2, M25-R3 |
| Provider credentials absent | M1-R2, M2-R1, M5-R3, M12-R3, M15-R3, M17-R3, M26-R2 |
| Phone hardware absent | M17-R2, M19-R4, M26-R2 |
| Signing identity absent | M1-R3, M19-R5, M22-R1, M23-R3, M26-R2 |
| GitHub Free plan branch-protection limit | M1-R1, M22-R3 |
| 434 unimplemented rows | M0-R1, M25-R4, M26-R1 |
| Priority re-ranking risk | M0-R2, M5-R4, M26-R3 |
| License / IP risk | M0-R4, M1-R4, M2-R2, M11-R1, M17-R1, M23-R4 |
| Offline-network test risk | M2-R3, M5-R2, M11-R4, M15-R1, M17-R3, M19-R6, M22-R4, M25-R1 |

Cross-cutting environment facts (all observed, not hypothetical):

- Native Windows sandbox has real FS/process enforcement; network denial works only
  via a capability-less AppContainer (WFP per-process filters need elevation).
  Linux Landlock/seccomp and macOS Seatbelt backends are integrated but have no
  native runner here. **macOS read isolation is BLOCKED on macOS 26** (`sandbox-exec`
  SIGABRT).
- No non-empty `KEEL_*` provider credential is configured; no live provider call
  was made. No phone device or emulator exists (`adb`/`fastboot`/`xcrun`/
  `idevice_id` absent); QR/payload generation is not real pairing.
- No signing identity: 0 GitHub Actions secrets, no certificate/private key, no
  signing env vars; unsigned packages must not be published as signed releases.
- GitHub Free private plan: branch protection 403, signed-commit enforcement 404,
  fork restriction 422; 2FA is owner-account controlled. Local compensating
  controls are the fail-closed pre-push hook + gitleaks + signed commits once a
  key exists.
- 865 registry rows: **429 verified, 2 blocked, 434 not_started**. All 551
  addenda 3–7 rows are unimplemented; none may be promoted without real evidence.

## M0 — foundation: plan index, gates, seams, clean-room rules

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M0-R1 — 434 rows are `not_started`; a milestone is declared complete from the 226 verified base rows.** | high | high | Keep statuses honest in `PLAN-INDEX.json`; consume `REMAINING-WORK-MATRIX.md` and `DEPENDENCY-GRAPH.md` §6 at every gate; CI gate fails on unverified rows in a claimed-complete milestone. | Plan maintainer / registry owner | Revert the milestone-completion commit; restore the previous `PLAN-INDEX.json`; re-open the gate and re-run the status audit. Never bulk-flip `not_started` → `verified`. |
| **M0-R2 — priority re-ranking (X0.1) drifts or loses meaning; P0 is 240/865 (~28%, above the ~25% cap) and owners re-label to make work look done.** | med | med | Preserve `original_priority`; require owner sign-off for any P0 change; re-check cap and distribution at each gate; report deltas in the matrix. | Product owner | Restore `original_priority` values from the prior registry snapshot and regenerate reports; revert the re-ranking commit. |
| **M0-R3 — no usable dependency order: 14 unresolved tokens (`Master 10`, `C-1`, `G7`, `E1.x`, …), 21 backward milestone edges, 72 not-started rows with unmet dependencies.** | high | med | Generated graph with SCC-collapsed cycles; X0.3 gate blocks starting any row whose deps are not green; unresolved tokens listed, never guessed; regenerate with `--check` in CI. | Build engineering | Disable the affected row's work item, not the gate; regenerate the report from the last known-good registry; revert any merge that started a row with unmet deps. |
| **M0-R4 — clean-room/IP breach: implementation copied from reference source instead of a behavior spec, or licence provenance missing.** | med | fatal | X0.10 two-step process (analyst writes spec with no pasted code → builder implements from spec); SPDX headers / `LicenseRef-Keel-Proprietary`; provenance log per module; licensing review before merge. | Licensing & IP reviewer | Quarantine the module (remove from build/artifact), replace with a clean-room implementation, and purge derived files; if anything shipped, escalate to owner for legal review. |

## M1 — repository governance, licence/EULA, trust boundaries

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M1-R1 — GitHub Free private plan cannot enforce branch protection (403), signed commits (404) or fork restriction (422).** | high | high | Record C11.1/C11.2 as blocked in the registry; use fail-closed local pre-push hook + gitleaks + SHA-pinned Actions on the integration branch; document the accepted exception or move to a forge with free protected branches (gate G6). | Repository governance owner | Revert the visibility/plan decision commit; restore protected-branch settings on the prior remote; if already merged, freeze the branch and require two-person review until a protected forge is live. |
| **M1-R2 — provider credentials absent: credential test-fire and live provider paths cannot be exercised.** | high | high | Separate deterministic fixtures from live tests with explicit env gates (`KEEL_*_API_KEY`); record exact secret names and secure validation workflow; claim only what was observed. | Integration engineering / owner credential delegate | Revert any "live verified" status or evidence string; keep fixture-only tests green; disable the live lane until credentials are configured through masked CI secrets or the encrypted store. |
| **M1-R3 — no signing identity: signed commits, notarization and release verification impossible; unsigned artifacts could be published as signed.** | high | high | `--require-signed` / `KEEL_REQUIRE_SIGNED` hard-fail; CI `verify-release-signatures` job; no release tag until owner provides keys and decides on paid platform certificates. | Release engineering | Revert the tagging/publish commit; delete unsigned release assets; fail the release job closed; keep only the internal build artifact with an explicit "unsigned" label. |
| **M1-R4 — licence/IP gap in SPDX headers, EULA storage or third-party notices.** | med | fatal | REUSE-style metadata with custom `LicenseRef-Keel-Proprietary`; EULA version stored locally with re-prompt; per-item licence identification; ambiguous items excluded. | Licensing & IP reviewer | Block the release, regenerate notices/SPDX from the last known-good manifest, and remove the unlicensed asset from the package. |

## M2 — model/provider plumbing, config layering, free-tier traps

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M2-R1 — no provider credentials: circuit breaker, retry/backoff, failover and model routing cannot be validated live.** | high | high | Fixtures for failure injection; live tests env-gated; never treat a fixture pass as live evidence. | Integration engineering | Revert live-readiness claims; keep failover behind the existing config flag; disable the live provider profile until keys exist. |
| **M2-R2 — model/voice and service licence traps (Vercel Hobby non-commercial, VirusTotal public API non-commercial, Docker Desktop commercial terms, model weights).** | med | high | `FREE-TIER-REGISTER.md` (service, terms, date verified, exit plan) and `MODEL-AND-VOICE-LICENSES.json` consumed by a CI gate; re-verify each release gate. | Dependency & licensing reviewer | Remove the offending provider/model from the default profile, switch to the documented exit plan, and rebuild the config; revert the commit that introduced it. |
| **M2-R3 — offline-network test risk: model download manager and constrained decoding tests silently reach the network.** | high | med | Run the full smoke suite with network namespace removed; seeded offline archive; update checks disabled in that CI job; fail on any outbound attempt. | QA / test engineering | Revert the test change; mark the affected test platform/credential-gated; keep the zero-network lane as the release gate. |
| **M2-R4 — sandbox platform gaps: model downloads and plugin loading run outside native enforcement on Linux/macOS hosts.** | med | high | Dedicated per-OS backends with no permissive fallback; environment-gated tests; fail-closed preflight when capabilities are unavailable. | Platform engineering | Disable the affected backend path and fall back to the fail-closed preflight (never to an unsandboxed run); revert the backend commit. |

## M5 — agent tools, trash, background jobs

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M5-R1 — tool execution isolation depends on sandbox backends that are unverified natively on Linux/macOS.** | med | high | Execute tool calls through the capability hub; treat `mutate_local` conservatively; platform-matrix tests with environment gates and fail-closed capability check. | Platform engineering | Revoke the capability grant for the affected tool; route to the conservative profile; revert the tool registration commit. |
| **M5-R2 — `webfetch`/`websearch` free backends have non-commercial terms or leak prompts; network egress in tests.** | high | med | Allow-listed backends in `FREE-TIER-REGISTER.md`; offline fixtures for tests; real network only in an opt-in lane; no secrets in URLs. | Dependency & licensing reviewer | Disable the backend via config, restore fixture tests, revert the provider registration. |
| **M5-R3 — no provider credentials blocks `questions`, model-backed tools and background-job orchestration verification.** | high | med | Scripted/deterministic agent fixture (A3.3) for UI and loop tests; live paths env-gated and explicitly unclaimed. | Integration engineering | Revert live-verification labels; keep job service behind its feature flag. |
| **M5-R4 — priority re-ranking pulls v1.x tools into v1.0; M5 has 51 not-started rows, 32 of them P0.** | med | med | Re-review P0 at the M5 gate against "v1.0 can ship safely"; keep lower tiers behind flags. | Product owner | Restore prior priorities and regenerate reports; move deferred rows back to `not_started` with a flag entry. |

## M11 — code intelligence (core) and engineering tools (split)

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M11-R1 — licence/IP risk in LSP servers, static analysers, SARIF tools and language packs.** | med | high | Per-tool licence record in `FREE-TIER-REGISTER.md`; prefer permissive bundled tools; user-installed tools never redistributed; licence gate before packaging. | Licensing & IP reviewer | Remove the tool from the default bundle, revert its manifest entry, rebuild the package without it. |
| **M11-R2 — indexing and LSP subprocesses run outside the sandbox on some platforms; workspace watches leak paths.** | med | med | Run indexers in the dedicated profile with path containment tests; fuzz path handling; no listening port outside the local transport. | Platform engineering | Disable incremental indexing/LSP adapter via config; revert the adapter registration; keep static fallback. |
| **M11-R3 — X0.2b split ambiguity: 30 rows split into "code-intel core" vs "engineering tools" by heuristic; dependencies mostly absent.** | med | med | Generated split nodes with documented classifier; unclassifiable rows stay on parent M11; owners confirm the split at kickoff; no synthetic edges. | Plan maintainer | Restore parent-M11 tagging in the generated report; re-run classifier after an explicit row-to-split mapping is agreed. |
| **M11-R4 — offline-network test risk: dependency upgrade assistant and coverage hints need package metadata/cache.** | med | low | Read only the local package cache; fixture-based changelogs; network lane opt-in. | QA / test engineering | Disable the assistant through config; revert to fixture tests. |

## M12 — agent orchestration and Duet (two modes, one surface)

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M12-R1 — Duet was defined three ways (Master D4, Add.1 B2.3, Add.2 C2.3); shipping incompatible surfaces.** | high | med | X0.4: one surface with *Live Pair* (ghost text, handoff) and *Review Pair* (builder + independent reviewer); owner confirms D4 before kickoff. | Product owner | Disable one mode via config and ship the other; revert the surface merge if the two modes conflict at runtime. |
| **M12-R2 — subagent launch permissions and handoff let a child exceed the parent's authority.** | med | high | Parent `subagent` rules gate every launch; tests for deny-all and allow-list cases; no `agent` provenance may satisfy a permission gate. | Security engineering | Revoke the subagent capability; revert the launch-path commit; keep the parent-only agent loop. |
| **M12-R3 — no provider credentials blocks live pairing and reviewer handoff verification.** | high | med | Scripted agent fixture for both modes; live e2e env-gated; record only observed behaviour. | Integration engineering | Revert live claims; keep pairing behind its feature flag. |

## M15 — webhooks, inbound channels, credential test-fire

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M15-R1 — offline-network test risk: webhook signature/replay tests use loopback, conflicting with the zero-network suite.** | med | med | Test the verifier as a pure function with fixtures; keep loopback e2e in a separate opt-in lane; update checks disabled in the zero-network job. | QA / test engineering | Revert the loopback test; run pure-function verification only; keep the zero-network gate green. |
| **M15-R2 — forged or replayed inbound webhook starts a trusted session.** | med | high | Constant-time signature compare, 300 s window, de-duplication, refusal on clock skew; inbound rules default-deny. | Security engineering | Disable inbound rules globally via config; revert the rule commit; rotate any exposed webhook secret. |
| **M15-R3 — no provider credentials prevents test-fire validation after saving credentials.** | high | med | Test-fire uses fixtures for shape validation; live fire env-gated and reported as untested. | Integration engineering | Revert "tested" evidence; disable the live test-fire button until keys exist. |
| **M15-R4 — sandbox platform gaps: webhook-triggered sessions may run outside native isolation on Linux/macOS.** | med | high | Start sessions through the capability hub with fail-closed preflight; platform-gated tests. | Platform engineering | Disable webhook-triggered sessions via config; revert the adapter registration. |

## M17 — voice / documents / meetings (split)

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M17-R1 — licence/IP risk: Piper licence changed between versions, Whisper weights, Kokoro voices, gated/non-commercial diarization models, ffmpeg GPL vs LGPL flags (X0.7).** | high | fatal | `MODEL-AND-VOICE-LICENSES.json` consumed by UI display and CI gate; verify at each gate; user-installed engines are never bundled. | Licensing & IP reviewer | Remove the model/voice from the bundle, revert the registry entry, rebuild artifacts; escalate any shipped redistribution to owner. |
| **M17-R2 — no phone hardware/emulator: mobile mic control and meeting capture cannot be paired or tested.** | high | med | Local pairing/TLS/approval/outbox is implemented but explicitly not claimed as real pairing; device-free tests limited to protocol fixtures. | Mobile QA / hardware owner | Revert any "pairing verified" status; keep the companion feature flag off; no QR claim in docs. |
| **M17-R3 — no provider credentials blocks browser `speechToText` authenticated remote and voice handoff.** | high | med | Local recognizers for offline paths; remote path env-gated; fixture transcripts for deterministic tests. | Integration engineering | Revert live claims; disable the remote recognizer profile. |
| **M17-R4 — macOS read isolation BLOCKED (sandbox-exec SIGABRT) prevents verifying document/OCR file denial and mic-file separation.** | high | high | Mark native macOS tests environment-gated and honestly BLOCKED; verify what can be verified (write/network confinement); no permissive fallback. | Platform engineering (macOS) | Skip the affected native lane with an explicit BLOCKED record; revert any claim of macOS read denial; keep fail-closed preflight. |

## M19 — desktop UI (M19a–M19f), shell, composer, docks, safety notices

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M19-R1 — X0.2 split overload: 87 rows across 6 sub-milestones; heuristic assignment can scatter related work.** | high | med | Generated split nodes; unclassifiable rows stay on parent M19; owner reviews the split at each sub-milestone kickoff; split report is regenerated from registry. | Plan maintainer | Restore parent-M19 grouping in the report; defer a sub-milestone without changing row statuses. |
| **M19-R2 — macOS read isolation BLOCKED: desktop file preview, `@file` completion and workspace picker cannot be safety-verified on macOS 26.** | high | high | Native macOS lane marked BLOCKED with observed SIGABRT evidence; test only on Windows here; docs disclose the gap; no permissive fallback. | Platform engineering (macOS) | Disable macOS file-preview/read paths behind the feature flag in unverified builds; revert any "verified on macOS" claim. |
| **M19-R3 — sandbox platform gaps: no-listening-port transport, single-instance lock and packaged runtime need native per-OS verification.** | high | high | Local socket/pipe spike (V31) with streaming/backpressure tests; per-OS capability assertions; environment-gated native lanes. | Desktop platform engineering | Revert to the in-process development transport; keep the desktop profile disabled on unverified platforms. |
| **M19-R4 — no phone hardware/emulator blocks deep-link and companion-approval UI verification.** | med | med | Protocol-level fixtures for `keel://` payloads; real pairing claims withheld; QR is not pairing proof. | Mobile QA | Disable deep-link handlers via config; revert any pairing-evidence claim. |
| **M19-R5 — no signing identity: D1.10 requires signed resources; unsigned desktop builds could be mistaken for official builds.** | high | high | Build identity shows unsigned/dirty state; `--require-signed` gate; no "Verified official build" indicator until signature checks pass. | Release engineering | Remove the official-build indicator, revert the packaging commit, and label artifacts unsigned. |
| **M19-R6 — offline-network test risk: update checks, plugin artwork fetches and help links break the zero-network claim.** | med | med | All help/art assets local; update checks disabled in CI; outbound-attempt detection in the smoke suite. | QA / test engineering | Revert the network-touching UI change; restore local assets. |

## M22 — packaging, update feed, stores

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M22-R1 — no signing identity: no hardened runtime, timestamp, notarization or signed update unit; releases blocked.** | high | fatal | Fail-closed publish guard (completion record + signature check); zero Actions secrets recorded as BLOCKED; owner must supply identity and decide on paid certificates. | Release engineering | Delete unsigned release assets; stop the staged rollout (blocked-version manifest); revert the release tag; rebuild only as an internal unsigned artifact. |
| **M22-R2 — X0.5 store conflict: Flathub/some stores require public manifests, violating "no source/no GitHub for users".** | high | high | Per-store register: accepts proprietary freeware? public manifest required? Drop failing stores; AUR binary package and self-hosted APT/YUM remain. | Product owner / release engineering | Remove the store target from the release matrix, revert its package recipe, and update the download page. |
| **M22-R3 — GitHub Free limitation: private GitHub Pages may require a paid plan; branch protection already unavailable.** | med | med | Mirror docs to a free static host or accept the documented exception in `FREE-TIER-REGISTER.md`; keep local `latest.json`/feeds self-hostable. | Repository governance owner | Revert the Pages-based URL change; restore the previous static host and feed origin. |
| **M22-R4 — offline-network test risk: mirror failover, air-gapped installs and update-unit checks require controlled networks.** | med | high | Local fixture mirrors and offline sideload bundles; signature check on every mirror; no live network in CI lanes. | QA / test engineering | Revert to a single known-good mirror; disable auto-update via config; keep the signed update unit unchanged. |
| **M22-R5 — no native macOS/Linux runners: clean-VM install/upgrade/rollback and package-manager lifecycle unverified.** | high | high | Mark platform lanes BLOCKED; rebuild Windows installer from final source with integrity checks but label unsigned; record exact clean-VM commands. | Release QA | Halt the release; revert to the last verified artifact set; do not promote a build-integrity pass to a release-readiness claim. |

## M23 — website, docs, release feed and notices

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M23-R1 — download page/SHA-256 guide advertises builds that are unsigned or not rebuilt from final source.** | med | high | Publish hashes only for artifacts produced by the final-source build; mark unsigned/native-gap statuses explicitly; generate pages from the release manifest. | Release engineering | Roll back the download page to the previous manifest; remove the offending hashes; restore the last verified feed entry. |
| **M23-R2 — offline docs search index drifts from shipped behaviour while 434 rows remain unimplemented.** | med | med | Generate docs from source/config catalog; mark unimplemented features as such; gate doc-sync in CI. | Documentation owner | Revert the generated index, regenerate from the last known-good source snapshot. |
| **M23-R3 — no signing identity blocks the "how to verify" guide and official-build messaging.** | high | med | Write the guide for signed releases only; show current unsigned status in the UI and docs; no verification claims before keys exist. | Release engineering | Remove the verification instructions from the published page; restore the explicit unsigned notice. |
| **M23-R4 — licence/IP risk in press kit, screenshots, third-party notices and trademark page.** | med | high | All assets from own builds with documented provenance; notices generated from dependency manifests; lawyer review flag on trademark/export-control page. | Licensing & IP reviewer | Remove the asset/page, revert the commit, regenerate notices. |

## M25 — verification gates: zero-network, contracts, fuzz

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M25-R1 — X0.8 "zero network without account" is asserted with no test list; an outbound call slips through.** | high | high | CI job runs full smoke suite with network namespace removed, update checks disabled, fails on any outbound attempt; maintain explicit test list. | QA / test engineering | Revert the change that introduced egress; keep the zero-network lane as a required gate; do not weaken the test to pass. |
| **M25-R2 — sandbox platform gaps make path-containment/fuzz results non-transferable across OSes.** | high | med | Run platform-matrix lanes; mark Linux/macOS native lanes environment-gated; report per-OS coverage, not a single global pass. | Platform engineering | Revert the global-pass claim; restore per-OS skip records; keep fail-closed preflight on unsupported hosts. |
| **M25-R3 — macOS read isolation BLOCKED (sandbox-exec SIGABRT) leaves a permanent hole in read-denial evidence.** | high | high | Record BLOCKED with observed evidence; verify write/network/rlimits where possible; native macOS runner required to close it. | Platform engineering (macOS) | Keep the affected assertions skipped with an explicit BLOCKED reason; revert any report line claiming macOS read denial. |
| **M25-R4 — 434 not-started rows cannot be covered by contract-regression specs; a green suite is mistaken for full coverage.** | med | high | Mark coverage scope in the test evidence; gate milestone claims against the registry status, not suite count; matrix lists every uncovered row. | Plan maintainer / QA lead | Revert the coverage claim; re-scope the gate to implemented rows only; never delete or weaken tests to improve the ratio. |

## M26 — honest disclosure and known limitations

| Risk | Likelihood | Impact | Mitigation | Owner (role) | Rollback / revert |
| :- | :- | :- | :- | :- | :- |
| **M26-R1 — "Project status"/known-limitations pages overstate parity while 434 rows are `not_started`.** | high | high | Status page generated from `PLAN-INDEX.json` counts (429/2/434); separate "proven end-to-end" from "built but unproven"; link the matrix. | Product owner / documentation owner | Revert the status page commit; restore counts from the last audited registry; add the missing limitation explicitly. |
| **M26-R2 — omitted external blockers (no provider credentials, no phone hardware, no signing identity, macOS/Linux native gaps) create false user expectations.** | high | med | Limitations list names each blocker with its observed evidence and owner action; release notes must carry the same list. | Product owner | Revert the release note; republish with the blocker list; halt any claim of live/production readiness. |
| **M26-R3 — priority re-ranking hides deferred P1/P2 work behind a "complete" label.** | med | low | Keep `original_priority` and the matrix; disclose tier definitions (P0 v1.0 / P1 v1.x / P2 later) in the status page. | Plan maintainer | Restore prior priority labels and regenerate reports; reword the status page. |

## Rollback conventions for every milestone kickoff

Each milestone kickoff file must carry a `Revert plan:` line with these standard
moves, specialised by the tables above:

1. **Stop the gate:** mark the affected CI lane red or blocked; never delete a test
   to make it green.
2. **Revert the code:** `git revert` the feature commit(s) on the integration
   branch; keep the commit that records the honest BLOCKED status.
3. **Revert the claim:** restore the prior `PLAN-INDEX.json` status/evidence values;
   regenerate `DEPENDENCY-GRAPH.md` and the matrix; do not flip `not_started`.
4. **Contain external dependencies:** revoke keys, disable profiles/flags, remove
   unsigned assets from release channels, stop rollouts via the blocked-version
   manifest.
5. **Record the outcome:** add an entry to the evidence file with the observed
   failure, the owner role and the follow-up gate; re-run the affected test lane.

## Owner action checklist (external blockers, unchanged by this document)

1. Repository plan/forge decision for C11.1/C11.2 (branch protection).
2. Signing identity + `KEEL_RELEASE_SIGNING_*` secrets and paid-certificate decision.
3. Provider credentials via masked secrets / encrypted store; no values in chat or git.
4. Phone device/emulator and companion client for real pairing.
5. Native macOS and Linux runners (macOS 26 read-isolation investigation).
6. Clean-VM install/upgrade/rollback/uninstall validation per OS.
7. Owner review/merge of the unpushed integration branch (live CI is still tag-pinned).

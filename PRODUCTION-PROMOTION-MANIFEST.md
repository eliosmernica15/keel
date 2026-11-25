# Production promotion manifest â€” backend completion plan

| Field | Value |
|---|---|
| Source branch | `integration/backend-completion-2026-11-24` |
| Source SHA | `fe6cdd778731a35b339da86643c092109f8ce44c` |
| Main baseline | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` |
| Operation baseline | `a64cd5dae8d760c164106be01496e2a9e6b7d530` |
| Merge base | `ecba9d2b9678ab7a3a744c62683eea28a1ce01ee` |
| Exclusive source commits | 264 |
| This plan's commits (baseline..tip) | 47 |
| Prior backend dependency commits | 217 |
| Changed paths (whole range) | 383 |

## Scope rule

`main` is the merge base; all 264 commits are local-only. The 47 commits from the
operation baseline are this plan's work; the preceding 217 commits supply the
backend implementation those commits depend on (20 modules, 865-row registry,
capability hub, tests). Both sets are included as REQUIRED_BACKEND_DEPENDENCY or
PLAN_BACKEND_IMPLEMENTATION. Frontend/desktop, research, review-probe and
frontend-only evidence are explicitly excluded.

## Path classification

| Path | Classification | Reason | Destination action | Verification |
|---|---|---|---|---|
| `.githooks/pre-push` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/build-desktop.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/offline-license.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/provider-validation.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/python-tests.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/secret-scan.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/signing-readiness.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.github/workflows/verify-install.yml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.gitignore` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `.gitleaks.toml` | BACKEND_TEST_OR_CI | CI/supply-chain/security control | checkout from source SHA | full backend suite + strict gate |
| `ADDENDA-OPERATION-STATUS.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `AUDIT-REMEDIATION-SUMMARY.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `AUDIT-TESTING.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-COMPLETION-ACCOUNTING.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-COMPLETION-BACKLOG.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-DATABASE-RECOVERY.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-DEPLOYMENT.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-IMPLEMENTATION-DETAIL.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-INCIDENT-RESPONSE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-MONITORING.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-OPERATION-TASKBOARD.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-OPERATIONS-RUNBOOK.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKEND-SECURITY-REVIEW.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `BACKLOG-traceability-failures.txt` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `DECISIONS.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `DEPENDENCY-GRAPH.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `FINAL-ENGINEERING-REPORT.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `FINAL-RELEASE-ACCEPTANCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `FREE-TIER-REGISTER.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `Keel_Master_Plan_v6.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `MODEL-AND-VOICE-LICENSES.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `P0-BATCHES.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PLAN-INDEX.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-API-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-AUTH-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-MCP-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-OBSERVABILITY-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-PERFORMANCE-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-PLATFORM-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-PROVIDER-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-RELIABILITY-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-SUPPLY-CHAIN-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROD-TOOLS-EVIDENCE.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PRODUCTION-ARCHITECTURE-AUDIT.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PRODUCTION-PROMOTION-MANIFEST.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PRODUCTION-READINESS-MATRIX.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PRODUCTION-READINESS-REPORT.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PRODUCTION-REQUIREMENT-RECONCILIATION.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `PROMOTION-PATH-INVENTORY.txt` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REGISTRY-EVIDENCE-INTEGRITY.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REMAINING-BACKEND-ANALYSIS.txt` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REMAINING-WORK-MATRIX.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REVIEW-CORE-FINDINGS.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REVIEW-FINAL-QUALITY.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REVIEW-FINAL-SECURITY.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `REVIEW-PLANNING-FINDINGS.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `RISKS.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `backend-declared-coverage.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `backend-final-attribution.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `backend-module-id-coverage.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/README.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/desktop/src-tauri/Cargo.toml` | REQUIRED_BACKEND_DEPENDENCY | One-line version constant required by backend version gate | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/CHECKLIST.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/FINAL-RELEASE-OPERATIONS.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/IMPLEMENTATION-PROGRESS.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/RESPONSIBLE-USE.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/Keel_Plan_v5_Addendum_4_Sourced_Features_and_Builder_Guide.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/Keel_Plan_v5_Addendum_5_DeepSeek_Harness_and_Deep_Reads.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/Keel_Plan_v5_Addendum_6_DeepSeek_Harness_Full_Teardown.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/Keel_Plan_v5_Addendum_7_DeepSeek_Deep_Reads.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/addendum3.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/addendum4.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/addendum5.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/addendum6.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/addendum7.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/plan-sources/extracted/base-verification.json` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/edit-format-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/external-readiness.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/final-independent-audit.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/macos-sandbox-mechanism.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/model-dialect-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/README.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/clawdbot-channel-linq-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/deepseek-harness-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/nicks-stack-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/opencode-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/openman-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/reference-behavior/orgo-teammates-behavior.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/remaining-work-matrix.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/sandbox-conformance.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/docs/research/source-repository-register.md` | BACKEND_DOCUMENTATION | Backend/plan documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/requirements-sbom.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/requirements.lock.txt` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `keel/scripts/build_dependency_graph.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `keel/scripts/build_plan_index.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `keel/scripts/build_v6_plan.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `keel/scripts/check_version_sync.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/agent_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/api_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/automation.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backend_contracts.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backend_events.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backend_hub.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backend_observability.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backend_workflows.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/backups.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/builder_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/capabilities.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/capability_registry.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/capability_seams.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/channel_ops.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/circuit_breaker.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/cli/main.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/clipboard_guard.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/codemod.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/command_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/commercial_seams.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/composition_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/config_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/d3_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/d6_reliability_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/d7_workflow_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/desktop_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/documents.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/e3_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/e5_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/e6_x5_x6_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/e7_runtime_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/edit_formats.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/events.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/exec_guard.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/exec_policy.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/fleet/service.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/gate_scheduler.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/hardware.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/identity_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/intelligence_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/invariant_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/mcp.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/mcp_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/message_state.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/model_dialects.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/os_sandbox.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/performance_budgets.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/permission_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/permissions.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/plan_corrections.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/plugin_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/policy_enforcement.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/product_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/provider_catalog.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/provider_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/redaction.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/__init__.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/cli.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/common.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/licenses.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/publish.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/release/signing.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/reliability_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/repo_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/repo_map.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/resilience.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/resource_caps.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/responsible_use.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/result_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/runner.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/runtime_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/safety.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/sandbox_macos.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/sandbox_windows.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/secret_providers.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/secret_store.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/security_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/session_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/settings_store.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/small_groups_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/status_page.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/steering.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/tool_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/tool_contracts_bridge.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/transcript_contracts.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/trash.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/tui.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/v_series_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/w1_security_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/w4_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/w7_x1_y5_d1_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/webapp.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/webhook_delivery.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/webhooks.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/win_network.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/workflows.py` | REQUIRED_BACKEND_DEPENDENCY | Backend runtime dependency of the plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/x2_orchestration_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/x3_memory_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/x8_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/y1_config_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/y2_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/y3_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/y4_d4_x7_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/src/keel/z_backend.py` | PLAN_BACKEND_IMPLEMENTATION | v6 backend module from this plan | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_agent_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_api_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_contracts_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_events.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_hub_integration.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_observability.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_backend_workflows.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_bridge_e2e_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_builder_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_capability_seams.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_cli_surface_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_clipboard_guard.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_command_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_commercial_seams.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_composition_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_config_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_d3_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_d6_reliability_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_d7_workflow_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_db_persistence_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_desktop_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_distribution_package.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_e3_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_e5_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_e6_x5_x6_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_e7_runtime_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_edit_formats.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_enterprise_seams.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_event_bus_persistence.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_exec_path_coverage.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_gap_closure.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_gate_scheduler.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_identity_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_intelligence_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_invariant_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_mcp.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_mcp_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_model_dialects.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_offline_runtime.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_os_sandbox.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_perf_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_permission_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_plan_corrections.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_plan_index.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_plugin_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_api.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_auth_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_cap_gate.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_db_recovery.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_mcp.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_observe.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_perffix.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_provider.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_recovery.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_secfix.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_prod_tools.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_product_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_product_defects.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_provider_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_recovery_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_redaction.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_release_controls.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_release_integrity.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_reliability_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_repo_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_repo_map.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_responsible_use.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_result_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_runtime_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_sandbox_macos.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_sandbox_windows.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_secret_providers.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_secret_storage.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_secrets_policy_hardening.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_security_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_security_validation.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_session_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_signing_gate.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_small_groups_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_status_page.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_steering.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_tool_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_tool_contracts_bridge.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_transcript_contracts.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_v_series_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_validation_script.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_version_sync.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_w1_security_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_w4_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_w7_x1_y5_d1_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_webhook_security.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_website_download_only.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_win_network.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_x2_orchestration_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_x3_memory_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_x8_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_y1_config_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_y2_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_y3_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_y4_d4_x7_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `keel/tests/test_z_backend.py` | BACKEND_TEST_OR_CI | Backend/acceptance test | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-agent-commit-index.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-agent-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-agent-execution.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-api-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-architecture-map.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-builder-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-capability-seams-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-cli-surface-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-clipboard-guard-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-command-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-composition-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-config-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-d3-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-d6-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-d7-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-db-persistence-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-dialects-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-e3-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-e5-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-e6-x5-x6-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-e7-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-edit-formats-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-exec-path-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-final-completion-report.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-final-delivery-report.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-final-matrix.csv` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-final-matrix.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-final-report.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-fleet-events-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-gate-scheduler-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-git-provenance.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-governance-live-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-high-findings-fix.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-identity-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-independent-acceptance.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-integration-strategy.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-intelligence-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-invariant-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-mcp-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-performance-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-permission-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-plan-corrections-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-platform-compatibility.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-plugin-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-product-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-product-defects-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-provider-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-recovery-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-release-acceptance-addendum.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-release-acceptance.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-release-audit.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-reliability-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-remaining-work-closure.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-repo-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-repomap-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-repository-security-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-responsible-use-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-result-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-review-group1.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-review-group2.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-review-group3.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-review-group4.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-runtime-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-sandbox-verification.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-secrets-policy-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-security-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-security-findings.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-session-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-small-groups-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-steering-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-supply-chain-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-test-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-tool-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-transcript-contracts-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-v-series-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-w1-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-w4-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-w7-x1-y5-d1-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-webhooks-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-win-network-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-x2-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-x3-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-x8-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-y1-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-y2-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-y3-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-y4-d4-x7-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `master-plan-v6-z-backend-evidence.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `parity.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/README.md` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_cap.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_db.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_http.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_http_backlog.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_resilience.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/bench_startup.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/benchcommon.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/child_startup.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/imp.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/import_breakdown.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/jsoncheck.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/memtest.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/per_module.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/probe.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_backlog.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_cap.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_db.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_http.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_resilience.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/result_startup.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `perf-harness/sig.py` | REQUIRED_BACKEND_DEPENDENCY | Required local dependency | checkout from source SHA | full backend suite + strict gate |
| `promotion-classification.json` | BACKEND_DOCUMENTATION | Plan registry/evidence documentation | checkout from source SHA | full backend suite + strict gate |
| `scripts/build_v6_audit_matrix.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `scripts/check_model_licenses.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `scripts/plan_p0_batches.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `scripts/verify_backend_operation.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |
| `scripts/verify_v6_audit.py` | BACKEND_TEST_OR_CI | Registry/verification/build script | checkout from source SHA | full backend suite + strict gate |

## Explicit scope exception â€” required version-sync constant

`keel/desktop/src-tauri/Cargo.toml` contains a **single version string** change
(`0.1.0` -> `0.1.1`). It is classified `REQUIRED_BACKEND_DEPENDENCY` because the
backend release/version-consistency gate (`tests/test_signing_gate.py` ->
`keel/release/common.py::validate_version`) fails collection without it. It is
not a UI, styling, component or behavior change: no desktop source logic is
imported. Documented here so the promotion contains no unexplained path.

## Excluded frontend-only tests

The following test files were part of the delivery branch but test **frontend/desktop
source that is explicitly excluded** from this backend-only promotion. They were removed
from the candidate only (not from the delivery branch) so the candidate contains a coherent
backend test suite; their failures were purely due to absent frontend source, not backend
defects:

- keel/tests/test_accessibility_hardening.py (static checks of site HTML/CSS)
- keel/tests/test_desktop_hardening.py (Electron main.js invariants)
- keel/tests/test_web_surface_hardening.py (site/PWA assets)
- keel/tests/test_validation_script.py (desktop validation script)
- keel/tests/test_website_download_only.py (public website content/policy)

No backend test was removed or weakened. keel/scripts/check_version_sync.py is included
as REQUIRED_BACKEND_DEPENDENCY because the backend release version gate
(	est_version_sync.py) imports it.

## Authoritative clean candidate — v2

The first candidate branch `release/backend-production-readiness-2026-11-24` received an
unrelated frontend commit (`6970867 feat(site): rebuild /download...`) from concurrent work
sharing the checkout. To preserve that work without importing it, the authoritative candidate
was rebuilt as `release/backend-production-readiness-2026-11-24-v2` from `origin/main` with
only the backend paths listed in this manifest. The earlier branch and the frontend commit
remain untouched. All backend fixes from the earlier candidate are present in v2.

| Field | Value |
|---|---|
| Authoritative candidate branch | `release/backend-production-readiness-2026-11-24-v2` |
| Authoritative candidate SHA | `CANDIDATE_HEADd0994986223dd802e47a078a0aeaf5203` |
| Excluded unrelated commit | `6970867` (frontend `/download` rebuild) |
| Frontend/desktop paths in v2 | only the documented one-line `Cargo.toml` version constant |

## Latest main merge before promotion

The repository owner advanced `origin/main` during this operation with frontend-only
commits (`7d48236`, `b2d7403` — Keel-in-Chrome pages, Web Store clone, MV3 extension).
Those changes were merged into the candidate so the final promotion is a clean
fast-forward and no owner work is overwritten or discarded. They are **pre-existing on
main**, not backend work imported by this plan. All backend paths in this manifest remain
the only changes this plan contributes.

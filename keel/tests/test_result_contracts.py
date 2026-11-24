"""P0 result-contract tests (stdlib-only, no model/subprocess/network).

This suite covers the pure descriptor/policy surface of
``keel.result_contracts`` that supports five addendum-7 registry rows:

* **E3.3**  -- agent-name validation, reserved root, default names and pure
  name -> session-id resolution (identity only, never a permission);
* **E3.8**  -- result object (last non-empty assistant message), optional
  schema-validated structured output, 4,096-byte sanitized diagnostics, closed
  stop-reason enum and child failures that resolve instead of raising;
* **E4.5**  -- snapshot scenarios (versioned parent/child filenames, header
  agreement, snapshot.yml config, typed identity tokens, immutable
  workspace.expected tree, mode gates and read-only CI replay);
* **E4.8**  -- test-process isolation (shared port/path/namespace/child
  detection, teardown ownership, complete fork-exit diagnostics, flake
  classification where solo-only passes are defects);
* **E4.15** -- keyless recorded change log and plan-time test tiers.

Every unknown/malformed value must fail closed, and no credential may survive
any boundary.  Run with the standard-library runner::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_result_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import keel.result_contracts as rc
from keel.result_contracts import (
    AGENT_NAME_NOT_FOUND,
    DEFAULT_AGENT_PREFIX,
    DIAGNOSTIC_BYTE_LIMIT,
    EXPECTED_TREE_ROOT,
    FEATURE_IDS,
    MAX_AGENT_NAME_LEN,
    REQUIRED_TIERS_FOR_NEW_SURFACE,
    TEST_TIERS,
    AgentNameNotFoundError,
    AgentRegistry,
    ChangeLog,
    ChangeRecord,
    ContractValidationError,
    FlakeClass,
    ForkExit,
    RecordingPolicy,
    ResourceKind,
    SessionHeader,
    SnapshotConfig,
    SnapshotMode,
    StopReason,
    TestTier as Tier,
    TokenKind,
    TypedToken,
    WorkspaceManifest,
    add_change,
    assert_all_nontrivial_covered,
    assert_clean_diagnostics,
    assert_expected_immutable,
    assert_isolated,
    assert_keyless,
    assert_snapshot_write_allowed,
    build_result,
    can_run_mode,
    child_failure_to_result,
    classify_flake,
    compare_workspace,
    default_agent_name,
    detect_isolation_violations,
    flake_report,
    fork_exit_diagnostic,
    is_read_only_mode,
    is_reserved_agent_name,
    last_assistant_message,
    make_agent_name,
    make_agent_path,
    make_change_log,
    make_change_record,
    make_lease,
    make_registry,
    make_snapshot_config,
    make_snapshot_pair,
    make_workspace_manifest,
    mode_requirements,
    parent_agent_path,
    parse_session_file,
    parse_stop_reason,
    parse_test_tier,
    resolve_child_outcome,
    resolve_name,
    review_all_diffs,
    sanitize_diagnostics,
    snapshot_write_allowed,
    solo_only_is_defect,
    validate_agent_name,
    validate_agent_path,
    validate_change_record,
    validate_structured,
    verify_identity_tokens,
)


KEY = "sk-abcdefghijklmnopqrstuvwxyz"


def _config(**kw):
    return make_snapshot_config("default", "session.v1", **kw)


def _pair(version=3):
    config = _config()
    parent = parse_session_file("parent-v%d.json" % version)
    child = parse_session_file("child-v%d.jsonl" % version)
    p_header = SessionHeader(version, "s-parent", "parent", "session.v1")
    c_header = SessionHeader(version, "s-child", "child", "session.v1", "s-parent")
    return make_snapshot_pair(parent, p_header, child, c_header, config)


def _registry():
    return make_registry({
        "lead": "s-root",
        "lead/researcher": "s-research",
        "lead/researcher/writer": "s-writer",
    })


# ---------------------------------------------------------------------------
# E3.3 -- agent names
# ---------------------------------------------------------------------------

class TestAgentNames(unittest.TestCase):
    def test_feature_ids_declared(self):
        self.assertEqual(FEATURE_IDS, ("E3.3", "E3.8", "E4.5", "E4.8", "E4.15"))
        self.assertEqual(MAX_AGENT_NAME_LEN, 32)
        self.assertEqual(DEFAULT_AGENT_PREFIX, "agent-")
        self.assertEqual(AGENT_NAME_NOT_FOUND, "AGENT_NAME_NOT_FOUND")

    def test_valid_names(self):
        for name in ("a", "agent-1", "research-2", "a-b-c", "a" + "b" * 31):
            with self.subTest(name=name):
                self.assertEqual(validate_agent_name(name), ())
                self.assertEqual(make_agent_name(name), name)

    def test_invalid_names_fail_closed(self):
        for name in ("", None, 12, "Lead", "1agent", "-agent", "has space",
                     "under_score", "ünicode", "a" * 33, "lead", "a.b", "a/b"):
            with self.subTest(name=name):
                self.assertTrue(validate_agent_name(name))
                with self.assertRaises(ContractValidationError):
                    make_agent_name(name)

    def test_reserved_root_name(self):
        self.assertTrue(is_reserved_agent_name("lead"))
        self.assertFalse(is_reserved_agent_name("agent-1"))

    def test_valid_full_paths(self):
        for path in ("lead", "lead/a", "lead/a/b", "lead/agent-9/a-b"):
            with self.subTest(path=path):
                self.assertEqual(validate_agent_path(path), ())
                self.assertEqual(make_agent_path(path), path)

    def test_bad_paths_rejected(self):
        for path in ("", "a/b", "lead//a", "lead/../a", "lead/./a",
                     "lead\\a", "lead/A", "lead/lead", "lead/a b"):
            with self.subTest(path=path):
                self.assertTrue(validate_agent_path(path))
                with self.assertRaises(ContractValidationError):
                    make_agent_path(path)

    def test_parent_path(self):
        self.assertIsNone(parent_agent_path("lead"))
        self.assertEqual(parent_agent_path("lead/a"), "lead")
        self.assertEqual(parent_agent_path("lead/a/b"), "lead/a")

    def test_default_names_skip_used(self):
        self.assertEqual(default_agent_name(), "agent-1")
        self.assertEqual(default_agent_name(["agent-1", "agent-3"]), "agent-2")
        self.assertEqual(default_agent_name(["agent-1", "agent-2"]), "agent-3")

    def test_registry_requires_root_and_rejects_bad_rows(self):
        with self.assertRaises(ContractValidationError):
            make_registry({"lead/a": "s-a"})  # no root
        with self.assertRaises(ContractValidationError):
            make_registry({"lead": "s-root", "lead/a": "s-root", "lead/A": "s-x"})
        with self.assertRaises(ContractValidationError):
            make_registry({"lead": ""})
        self.assertEqual(len(_registry().entries), 3)

    def test_resolve_returns_only_the_session_id(self):
        resolved = resolve_name(_registry(), "lead/researcher/writer")
        self.assertIsInstance(resolved, str)
        self.assertEqual(resolved, "s-writer")
        self.assertEqual(resolve_name(_registry(), "lead"), "s-root")

    def test_resolve_unknown_path_fails_with_code(self):
        with self.assertRaises(AgentNameNotFoundError) as ctx:
            resolve_name(_registry(), "lead/nope")
        self.assertEqual(ctx.exception.code, "AGENT_NAME_NOT_FOUND")
        self.assertIn("AGENT_NAME_NOT_FOUND", str(ctx.exception))

    def test_resolve_malformed_path_fails_closed(self):
        for path in ("lead/../x", "nope/x", "lead/A", "", None):
            with self.subTest(path=path):
                with self.assertRaises(AgentNameNotFoundError):
                    resolve_name(_registry(), path)

    def test_names_are_references_session_ids_are_authority(self):
        registry = make_registry({"lead": "s-root", "lead/alias": "s-root"})
        self.assertEqual(resolve_name(registry, "lead"), "s-root")
        self.assertEqual(resolve_name(registry, "lead/alias"), "s-root")
        self.assertTrue(registry.has_session("s-root"))
        self.assertFalse(registry.has_session("s-missing"))

    def test_resolve_without_registry_object_fails_closed(self):
        with self.assertRaises(AgentNameNotFoundError):
            resolve_name({"lead": "s-root"}, "lead")


# ---------------------------------------------------------------------------
# E3.8 -- result object
# ---------------------------------------------------------------------------

class TestResultObject(unittest.TestCase):
    def test_last_non_empty_assistant_message(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "   "},
            {"role": "tool", "content": "tool output"},
            {"role": "assistant", "content": "first answer"},
            {"role": "assistant", "content": "final answer"},
        ]
        self.assertEqual(last_assistant_message(messages), "final answer")

    def test_message_content_blocks_and_missing_content(self):
        messages = [
            {"role": "assistant", "content": [{"type": "text", "text": "block one"}]},
            {"role": "assistant", "content": None},
            "not a message",
            {"role": "assistant"},
        ]
        self.assertEqual(last_assistant_message(messages), "block one")
        self.assertEqual(last_assistant_message([]), "")
        self.assertEqual(last_assistant_message(None), "")

    def test_stop_reason_enum_is_closed(self):
        self.assertEqual(
            tuple(r.value for r in StopReason),
            ("completed", "aborted", "error", "max-tokens", "refusal"),
        )
        self.assertEqual(parse_stop_reason("max_tokens"), StopReason.MAX_TOKENS)
        self.assertEqual(parse_stop_reason("failed"), StopReason.ERROR)
        with self.assertRaises(ContractValidationError):
            parse_stop_reason("banana")

    def test_build_result_uses_last_assistant_message(self):
        result = build_result([
            {"role": "assistant", "content": "old"},
            {"role": "assistant", "content": "new"},
        ])
        self.assertEqual(result.final_output, "new")
        self.assertEqual(result.stop_reason, StopReason.COMPLETED)
        self.assertEqual(result.diagnostics, "")
        self.assertEqual(result.diagnostics_bytes, 0)

    def test_explicit_output_and_stop_reason(self):
        result = build_result(final_output="override", stop_reason="max_tokens")
        self.assertEqual(result.final_output, "override")
        self.assertEqual(result.stop_reason, StopReason.MAX_TOKENS)

    def test_structured_output_validated_against_schema(self):
        schema = {
            "type": "object",
            "required": ["ok"],
            "properties": {
                "ok": {"type": "boolean"},
                "count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        }
        result = build_result(structured={"ok": True, "count": 3}, schema=schema)
        self.assertTrue(result.has_structured_output)
        self.assertEqual(result.structured, {"ok": True, "count": 3})
        for bad in ({"ok": "yes"}, {"ok": True, "extra": 1},
                    {"ok": True, "count": -1}, {}):
            with self.subTest(bad=bad):
                with self.assertRaises(ContractValidationError):
                    build_result(structured=bad, schema=schema)

    def test_schema_gate_is_fail_closed(self):
        with self.assertRaises(ContractValidationError):
            build_result(schema={"type": "object"})  # schema without value
        with self.assertRaises(ContractValidationError):
            build_result(structured={"x": 1}, schema={"type": "object", "bogus": 1})
        with self.assertRaises(ContractValidationError):
            validate_structured({"x": 1}, {"type": "nonsense"})

    def test_enum_const_and_array_items(self):
        schema = {
            "type": "object",
            "properties": {
                "color": {"enum": ["red", "blue"]},
                "tag": {"const": "v1"},
                "scores": {"type": "array", "items": {"type": "integer"},
                           "minItems": 1},
            },
        }
        self.assertEqual(validate_structured(
            {"color": "red", "tag": "v1", "scores": [1, 2]}, schema), ())
        self.assertTrue(validate_structured({"color": "green"}, schema))
        self.assertTrue(validate_structured({"tag": "v2"}, schema))
        self.assertTrue(validate_structured({"scores": []}, schema))
        self.assertTrue(validate_structured({"scores": ["x"]}, schema))

    def test_non_json_and_secret_structured_output_rejected(self):
        with self.assertRaises(ContractValidationError):
            build_result(structured={"bad": object()})
        with self.assertRaises(ContractValidationError):
            build_result(structured={"api_key": KEY})

    def test_result_round_trip(self):
        result = build_result(final_output="done", stop_reason="aborted",
                              diagnostics="a short note")
        rebuilt = rc.Result.from_dict(result.to_dict())
        self.assertEqual(rebuilt, result)

    def test_diagnostics_byte_limit_and_multibyte(self):
        # Many short lines exercise the byte cap (a single long line is instead
        # truncated as a suspected file dump by the line-length rule).
        text = "\n".join(["🙂" * 40] * 100)  # 12,000 UTF-8 bytes
        sanitized = sanitize_diagnostics(text)
        self.assertLessEqual(len(sanitized.encode("utf-8")), DIAGNOSTIC_BYTE_LIMIT)
        self.assertTrue(sanitized.endswith("..."))
        with self.assertRaises(ContractValidationError):
            assert_clean_diagnostics("🙂" * (DIAGNOSTIC_BYTE_LIMIT // 4 + 1))

    def test_diagnostics_strip_credentials_env_and_assignments(self):
        raw = "%s\nOPENAI_API_KEY=%s\napi_key=%s" % (KEY, KEY, KEY)
        clean = sanitize_diagnostics(raw)
        self.assertNotIn(KEY, clean)
        self.assertIn("[env:OPENAI_API_KEY=REDACTED]", clean)
        self.assertEqual(clean, sanitize_diagnostics(clean))  # idempotent
        self.assertEqual(assert_clean_diagnostics(clean), clean)

    def test_diagnostics_strip_tool_inputs_and_raw_payloads(self):
        clean = sanitize_diagnostics('tool_input={"cmd": "rm -rf /"}')
        self.assertNotIn("rm -rf", clean)
        self.assertIn("[TOOL_INPUT_REDACTED]", clean)
        self.assertNotIn("SGVsbG8=", sanitize_diagnostics("base64_blob=SGVsbG8="))

    def test_diagnostics_strip_file_contents_and_pem(self):
        clean = sanitize_diagnostics("<file>top secret text</file>")
        self.assertNotIn("top secret text", clean)
        self.assertIn("[FILE_CONTENT_REDACTED]", clean)
        pem = "-----BEGIN RSA PRIVATE KEY-----\nABCDEFGH\n-----END RSA PRIVATE KEY-----"
        self.assertNotIn("ABCDEFGH", sanitize_diagnostics(pem))
        long_dump = "x" * 400
        self.assertNotIn("x" * 300, sanitize_diagnostics(long_dump))

    def test_assert_clean_rejects_dirty_text(self):
        with self.assertRaises(ContractValidationError):
            assert_clean_diagnostics("api_key=" + KEY)

    def test_child_failure_resolves_with_error_not_exception(self):
        result = child_failure_to_result(RuntimeError("boom " + KEY))
        self.assertEqual(result.stop_reason, StopReason.ERROR)
        self.assertNotIn(KEY, result.diagnostics)
        self.assertIn("child failure:", result.diagnostics)
        self.assertIn("[REDACTED]", result.diagnostics)

    def test_child_failure_never_raises_on_weird_input(self):
        class Exploding:
            def __str__(self):
                raise RuntimeError("cannot stringify")

        result = child_failure_to_result(Exploding(), messages="bad messages")
        self.assertEqual(result.stop_reason, StopReason.ERROR)
        self.assertIsInstance(result.final_output, str)

    def test_resolve_child_outcome_maps_failures_and_success(self):
        failed = resolve_child_outcome({"ok": False, "error": "tool died"})
        self.assertEqual(failed.stop_reason, StopReason.ERROR)
        self.assertEqual(resolve_child_outcome({"stop_reason": "error"}).stop_reason,
                         StopReason.ERROR)
        self.assertEqual(resolve_child_outcome({"error": "x"}).stop_reason,
                         StopReason.ERROR)
        success = resolve_child_outcome({
            "messages": [{"role": "assistant", "content": "child answer"}],
            "stop_reason": "completed",
        })
        self.assertEqual(success.stop_reason, StopReason.COMPLETED)
        self.assertEqual(success.final_output, "child answer")
        self.assertEqual(resolve_child_outcome(42).stop_reason, StopReason.ERROR)
        self.assertEqual(resolve_child_outcome({"schema": {"type": "bogus"}}).stop_reason,
                         StopReason.ERROR)


# ---------------------------------------------------------------------------
# E4.5 -- snapshot scenarios
# ---------------------------------------------------------------------------

class TestSnapshots(unittest.TestCase):
    def test_versioned_filenames(self):
        parent = parse_session_file("parent-v3.json")
        self.assertEqual((parent.role, parent.version, parent.extension),
                         ("parent", 3, "json"))
        child = parse_session_file("child-v12.jsonl")
        self.assertEqual((child.role, child.version), ("child", 12))
        for bad in ("session.json", "parent.json", "parent-v.json", "parent-v3.txt",
                    "root-v3.json", "parent-v3.json/../../x", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ContractValidationError):
                    parse_session_file(bad)

    def test_valid_pair_carries_typed_tokens(self):
        pair = _pair()
        self.assertEqual(len(pair.tokens), 8)
        self.assertEqual(verify_identity_tokens(pair.tokens), ())
        self.assertEqual(pair.config.recording_policy, RecordingPolicy.KEYLESS)

    def test_snapshot_config_validation(self):
        self.assertEqual(mode_requirements(SnapshotMode.RECORD), frozenset({"api_key"}))
        with self.assertRaises(ContractValidationError):
            make_snapshot_config("unknown", "session.v1")
        with self.assertRaises(ContractValidationError):
            make_snapshot_config("default", "session.v9")
        with self.assertRaises(ContractValidationError):
            make_snapshot_config("default", "session.v1", recording_policy="magic")
        with self.assertRaises(ContractValidationError):
            make_snapshot_config("default", "session.v1",
                                 workspace_facts={"api_key": KEY})

    def test_pair_version_must_agree_with_header(self):
        config = _config()
        parent = parse_session_file("parent-v3.json")
        child = parse_session_file("child-v3.jsonl")
        p_header = SessionHeader(3, "s-parent", "parent", "session.v1")
        bad_child = SessionHeader(4, "s-child", "child", "session.v1", "s-parent")
        with self.assertRaises(ContractValidationError) as ctx:
            make_snapshot_pair(parent, p_header, child, bad_child, config)
        self.assertIn("version mismatch", str(ctx.exception))

    def test_pair_identity_relations(self):
        config = _config()
        parent = parse_session_file("parent-v3.json")
        child = parse_session_file("child-v3.jsonl")
        p_header = SessionHeader(3, "s-parent", "parent", "session.v1")
        # child points at the wrong parent
        wrong_link = SessionHeader(3, "s-child", "child", "session.v1", "s-other")
        with self.assertRaises(ContractValidationError):
            make_snapshot_pair(parent, p_header, child, wrong_link, config)
        # parent and child share a session id
        same_id = SessionHeader(3, "s-parent", "child", "session.v1", "s-parent")
        with self.assertRaises(ContractValidationError):
            make_snapshot_pair(parent, p_header, child, same_id, config)
        # header class does not match snapshot.yml
        wrong_class = SessionHeader(3, "s-child", "child", "session.v2", "s-parent")
        with self.assertRaises(ContractValidationError):
            make_snapshot_pair(parent, p_header, child, wrong_class, config)

    def test_typed_tokens_fail_closed_on_tampering(self):
        pair = _pair()
        tampered = tuple(
            TypedToken(TokenKind.CHILD_PARENT_LINK, "s-evil", "child")
            if token.kind == TokenKind.CHILD_PARENT_LINK else token
            for token in pair.tokens
        )
        self.assertTrue(verify_identity_tokens(tampered))
        self.assertTrue(verify_identity_tokens(pair.tokens[:-1]))  # missing token
        self.assertTrue(verify_identity_tokens((*pair.tokens, pair.tokens[0])))  # duplicate
        wrong_owner = tuple(
            TypedToken(token.kind, token.value, "wrong")
            if token.kind == TokenKind.CHILD_SESSION_ID else token
            for token in pair.tokens
        )
        self.assertTrue(verify_identity_tokens(wrong_owner))

    def test_workspace_manifest_is_pure_and_sorted(self):
        manifest = make_workspace_manifest({
            "workspace.expected/b.txt": "two",
            "workspace.expected/a.txt": "one",
        })
        self.assertEqual([p for p, _ in manifest.entries],
                         ["workspace.expected/a.txt", "workspace.expected/b.txt"])
        self.assertEqual(manifest, make_workspace_manifest({
            "workspace.expected/a.txt": "one",
            "workspace.expected/b.txt": "two",
        }))
        for bad in ({"../escape": "x"}, {"C:\\evil": "x"},
                    {"workspace.expected/%2e%2e/x": "x"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ContractValidationError):
                    make_workspace_manifest(bad)
        with self.assertRaises(ContractValidationError):
            make_workspace_manifest(["not", "a", "mapping"])
        # Manifest stores only digests, so even secret-bearing input stays keyless.
        digest_manifest = make_workspace_manifest({"workspace.expected/x": KEY})
        self.assertNotIn(KEY, str(digest_manifest.to_dict()))

    def test_workspace_diff_and_expected_immutability(self):
        before = make_workspace_manifest({
            "workspace.expected/a.txt": "one",
            "workspace.expected/b.txt": "two",
        })
        after = make_workspace_manifest({
            "workspace.expected/a.txt": "one",
            "workspace.expected/b.txt": "CHANGED",
            "workspace.expected/c.txt": "new",
        })
        diff = compare_workspace(before, after)
        self.assertEqual(diff.added, ("workspace.expected/c.txt",))
        self.assertEqual(diff.changed, ("workspace.expected/b.txt",))
        self.assertEqual(diff.removed, ())
        self.assertIn("workspace.expected/b.txt", diff.paths())
        self.assertFalse(diff.is_empty)
        assert_expected_immutable(before, before)
        with self.assertRaises(ContractValidationError):
            assert_expected_immutable(before, after)

    def test_mode_preconditions(self):
        self.assertFalse(can_run_mode(SnapshotMode.RECORD))
        self.assertTrue(can_run_mode(SnapshotMode.RECORD, key_present=True))
        self.assertFalse(can_run_mode(SnapshotMode.REFRESH, key_present=True))
        self.assertTrue(can_run_mode(SnapshotMode.REFRESH, replay_input_valid=True))
        self.assertFalse(can_run_mode(SnapshotMode.REVIEW))
        self.assertTrue(can_run_mode(SnapshotMode.REVIEW, diff_reviewed=True))
        self.assertTrue(can_run_mode(SnapshotMode.CI_REPLAY))
        self.assertTrue(is_read_only_mode(SnapshotMode.CI_REPLAY))
        self.assertTrue(is_read_only_mode(SnapshotMode.REVIEW))
        self.assertFalse(is_read_only_mode(SnapshotMode.RECORD))
        with self.assertRaises(ContractValidationError):
            mode_requirements("nonsense")

    def test_expected_tree_never_written_and_ci_read_only(self):
        self.assertTrue(snapshot_write_allowed(SnapshotMode.RECORD, "recorded/s.jsonl"))
        self.assertTrue(snapshot_write_allowed(SnapshotMode.REFRESH, "recorded/s.jsonl"))
        self.assertFalse(snapshot_write_allowed(
            SnapshotMode.REFRESH, "workspace.expected/a.txt"))
        self.assertFalse(snapshot_write_allowed(
            SnapshotMode.CI_REPLAY, "recorded/s.jsonl"))
        self.assertFalse(snapshot_write_allowed(
            SnapshotMode.RECORD, "../escape.json"))
        self.assertEqual(EXPECTED_TREE_ROOT, "workspace.expected")
        assert_snapshot_write_allowed(SnapshotMode.RECORD, "recorded/s.jsonl")
        with self.assertRaises(ContractValidationError):
            assert_snapshot_write_allowed(SnapshotMode.CI_REPLAY, "recorded/s.jsonl")

    def test_review_every_diff(self):
        diff = compare_workspace(
            make_workspace_manifest({"workspace.expected/a": "1"}),
            make_workspace_manifest({"workspace.expected/a": "2"}),
        )
        review_all_diffs([diff], ["workspace.expected/a"])
        with self.assertRaises(ContractValidationError) as ctx:
            review_all_diffs([diff], [])
        self.assertIn("workspace.expected/a", str(ctx.exception))


# ---------------------------------------------------------------------------
# E4.8 -- test-process isolation
# ---------------------------------------------------------------------------

class TestIsolation(unittest.TestCase):
    def test_leases_require_owner_and_teardown(self):
        lease = make_lease(ResourceKind.PORT, "tcp://127.0.0.1:9100",
                           owner_test="test_a", worker_id="gw0")
        self.assertTrue(lease.teardown_owned)
        with self.assertRaises(ContractValidationError):
            make_lease(ResourceKind.PORT, "tcp://127.0.0.1:9100",
                       owner_test="", worker_id="gw0")
        with self.assertRaises(ContractValidationError):
            make_lease(ResourceKind.PATH, "/tmp/x", owner_test="test_a",
                       worker_id="gw0", teardown_owned=False)
        with self.assertRaises(ContractValidationError):
            make_lease("socket", "x", owner_test="test_a", worker_id="gw0")

    def test_shared_resources_detected_across_workers(self):
        port_a = make_lease(ResourceKind.PORT, "tcp://127.0.0.1:9100",
                            owner_test="test_a", worker_id="gw0")
        port_b = make_lease(ResourceKind.PORT, "tcp://127.0.0.1:9100",
                            owner_test="test_b", worker_id="gw1")
        path_c = make_lease(ResourceKind.PATH, "/tmp/unique-dir",
                            owner_test="test_c", worker_id="gw0")
        violations = detect_isolation_violations([port_a, port_b, path_c])
        self.assertTrue(any("shared port" in v for v in violations))
        with self.assertRaises(ContractValidationError):
            assert_isolated([port_a, port_b])
        assert_isolated([port_a, path_c])

    def test_namespace_and_child_process_leases(self):
        ns_a = make_lease(ResourceKind.NAMESPACE, "ns-alpha",
                          owner_test="test_a", worker_id="gw0")
        child_a = make_lease(ResourceKind.CHILD_PROCESS, "pid:4242",
                             owner_test="test_a", worker_id="gw0")
        self.assertEqual(detect_isolation_violations([ns_a, child_a]), ())

    def test_fork_exit_reports_pid_file_code_signal(self):
        diagnostic = fork_exit_diagnostic(
            ForkExit(pid=4242, file="tests/test_x.py", code=1, signal=None))
        for fragment in ("pid=4242", "file=tests/test_x.py", "code=1", "signal=n/a"):
            self.assertIn(fragment, diagnostic)
        by_signal = fork_exit_diagnostic({
            "pid": 7, "file": "worker.py", "code": None, "signal": "SIGKILL",
        })
        self.assertIn("code=n/a", by_signal)
        self.assertIn("signal=SIGKILL", by_signal)

    def test_fork_exit_missing_fields_fail_closed(self):
        for info in (
            {"pid": 0, "file": "x.py", "code": 0, "signal": None},
            {"pid": 5, "file": "", "code": 0, "signal": None},
            {"pid": 5, "file": "x.py", "code": None, "signal": None},
            "not a mapping",
        ):
            with self.subTest(info=info):
                with self.assertRaises(ContractValidationError):
                    fork_exit_diagnostic(info)

    def test_solo_only_pass_is_a_defect(self):
        self.assertTrue(solo_only_is_defect(True, False))
        self.assertFalse(solo_only_is_defect(True, True))
        self.assertFalse(solo_only_is_defect(False, False))
        self.assertFalse(solo_only_is_defect(False, True))

    def test_flake_classification(self):
        self.assertEqual(classify_flake("t1", solo_passed=True, suite_passed=False,
                                        repeated_runs=[True, True]),
                         FlakeClass.ISOLATION_DEFECT)
        self.assertEqual(classify_flake("t2", solo_passed=True, suite_passed=True,
                                        repeated_runs=[True, False, True]),
                         FlakeClass.PROBABILISTIC)
        self.assertEqual(classify_flake("t3", solo_passed=True, suite_passed=True,
                                        repeated_runs=[True, True]),
                         FlakeClass.DETERMINISTIC_PASS)
        self.assertEqual(classify_flake("t4", solo_passed=False, suite_passed=False,
                                        repeated_runs=[False, False]),
                         FlakeClass.DETERMINISTIC_FAIL)
        self.assertEqual(classify_flake("t5", solo_passed=False, suite_passed=True,
                                        repeated_runs=[True, True]),
                         FlakeClass.ORDER_DEPENDENT)
        self.assertEqual(classify_flake("t6", solo_passed=True, suite_passed=True),
                         FlakeClass.UNKNOWN)
        with self.assertRaises(ContractValidationError):
            classify_flake("", solo_passed=True, suite_passed=True)

    def test_flake_report_is_deterministic_and_fail_closed(self):
        report = flake_report([
            {"test_id": "z", "solo_passed": True, "suite_passed": True,
             "repeated_runs": [True]},
            {"test_id": "a", "solo_passed": True, "suite_passed": False,
             "repeated_runs": [True]},
        ])
        self.assertEqual(list(report["classifications"]), ["a", "z"])
        self.assertEqual(report["classifications"]["a"], "isolation_defect")
        with self.assertRaises(ContractValidationError):
            flake_report([
                {"test_id": "x", "solo_passed": True, "suite_passed": False},
                {"test_id": "x", "solo_passed": True, "suite_passed": True,
                 "repeated_runs": [True, False]},
            ])


# ---------------------------------------------------------------------------
# E4.15 -- keyless change log
# ---------------------------------------------------------------------------

class TestChangeLog(unittest.TestCase):
    def test_test_tiers_mirror_plan_legend(self):
        self.assertEqual(len(TEST_TIERS), 10)
        self.assertEqual(parse_test_tier("u"), Tier.UNIT)
        self.assertEqual(parse_test_tier("C"), Tier.CONTRACT)
        self.assertEqual(parse_test_tier("e"), Tier.E2E)
        self.assertEqual(parse_test_tier("fault injection"), Tier.FAULT_INJECTION)
        with self.assertRaises(ContractValidationError):
            parse_test_tier("vibes")

    def test_nontrivial_change_requires_scenario_and_tiers(self):
        good = make_change_record(
            "E3.8-result", "result object", human_visible=True,
            scenario_ref="scenarios/e3-8-result", test_tiers=["unit", "contract", "A"],
        )
        self.assertTrue(good.is_nontrivial)
        self.assertEqual(good.test_tiers, ("unit", "contract", "adversarial"))
        with self.assertRaises(ContractValidationError):
            make_change_record("x", "no scenario", human_visible=True)
        with self.assertRaises(ContractValidationError):
            make_change_record("x", "no tiers", protocol_visible=True,
                               scenario_ref="scenarios/x")
        with self.assertRaises(ContractValidationError):
            make_change_record("x", "bad tier", model_visible=True,
                               scenario_ref="scenarios/x", test_tiers=["vibes"])
        with self.assertRaises(ContractValidationError):
            make_change_record("x", "bad ref", model_visible=True,
                               scenario_ref="../escape")

    def test_trivial_change_needs_no_scenario(self):
        trivial = make_change_record("typo-fix", "typo in a comment")
        self.assertFalse(trivial.is_nontrivial)
        self.assertEqual(trivial.scenario_ref, "")

    def test_new_surface_names_every_required_tier(self):
        tiers = sorted(REQUIRED_TIERS_FOR_NEW_SURFACE)
        good = make_change_record(
            "seam-1", "new capability seam", new_capability_seam=True,
            scenario_ref="scenarios/seam-1", test_tiers=tiers,
        )
        self.assertEqual(set(good.test_tiers), REQUIRED_TIERS_FOR_NEW_SURFACE)
        with self.assertRaises(ContractValidationError) as ctx:
            make_change_record(
                "seam-2", "new seam", lifecycle_variant=True,
                scenario_ref="scenarios/seam-2", test_tiers=["unit", "contract"],
            )
        self.assertIn("e2e", str(ctx.exception))

    def test_change_records_reject_secrets(self):
        with self.assertRaises(ContractValidationError) as ctx:
            make_change_record("leak", "api_key=" + KEY, human_visible=True,
                               scenario_ref="scenarios/x", test_tiers=["unit"])
        self.assertNotIn(KEY, str(ctx.exception))
        with self.assertRaises(ContractValidationError):
            make_change_record("leak2", "fine summary", human_visible=True,
                               scenario_ref="scenarios/" + KEY, test_tiers=["unit"])

    def test_change_log_is_sorted_unique_and_keyless(self):
        a = make_change_record("b", "change b")
        b = make_change_record("a", "change a")
        log = make_change_log([a, b])
        self.assertEqual([r.change_id for r in log.records], ["a", "b"])
        self.assertEqual(log.by_id("a"), b)
        with self.assertRaises(ContractValidationError):
            make_change_log([a, a])
        bigger = add_change(log, make_change_record("c", "change c"))
        self.assertEqual(len(bigger.records), 3)
        assert_keyless(bigger)
        for field, value in bigger.to_dict().items():
            if field == "records":
                for record in value:
                    self.assertFalse(
                        {"key", "api_key", "token", "secret", "password"} & set(record))

    def test_assert_keyless_and_coverage_fail_closed(self):
        dirty = ChangeLog(records=(ChangeRecord(
            change_id="dirty", summary="api_key=" + KEY, model_visible=True,
            protocol_visible=False, human_visible=False,
            scenario_ref="scenarios/x", test_tiers=("unit",),
        ),))
        with self.assertRaises(ContractValidationError):
            assert_keyless(dirty)
        uncovered = ChangeLog(records=(ChangeRecord(
            change_id="uncovered", summary="visible change", model_visible=True,
            protocol_visible=False, human_visible=False,
            scenario_ref="", test_tiers=(),
        ),))
        with self.assertRaises(ContractValidationError):
            assert_all_nontrivial_covered(uncovered)
        assert_all_nontrivial_covered(make_change_log([
            make_change_record("covered", "visible", human_visible=True,
                               scenario_ref="scenarios/covered", test_tiers=["unit"]),
        ]))


# ---------------------------------------------------------------------------
# Purity -- stdlib-only, no host state
# ---------------------------------------------------------------------------

class TestPurity(unittest.TestCase):
    def test_module_imports_are_stdlib_only(self):
        path = Path(rc.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = {"__future__", "hashlib", "json", "re", "dataclasses",
                   "enum", "typing"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        self.assertTrue(imported <= allowed, imported - allowed)

    def test_module_makes_no_host_calls(self):
        path = Path(rc.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden_names = {"open", "exec", "eval", "input", "__import__"}
        forbidden_attrs = {"system", "popen", "spawn", "unlink", "remove",
                           "sleep", "socket", "subprocess", "environ"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    self.assertNotIn(func.id, forbidden_names)
                elif isinstance(func, ast.Attribute):
                    self.assertNotIn(func.attr, forbidden_attrs)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)

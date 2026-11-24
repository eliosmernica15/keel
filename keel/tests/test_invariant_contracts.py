"""Adversarial P0 tests for ``keel.invariant_contracts`` (a9-v).

Covers the seven registry rows V1, V2, V5, V16, V24, V26 and V31 with a
stdlib-only suite: scope lifecycle/leak detection, ordered policy traces with
winning rules, strictness monotonicity, invariant-gate failing fixtures,
tool-conformance failing fixtures, byte-exact request reconstruction and a
descriptor-only local-socket spike decision.  No network, socket, subprocess,
model, clock or chance is used.

Run from the worktree root::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_invariant_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import keel.invariant_contracts as ic

CONFORMANCE_CHECKS = ic.CONFORMANCE_CHECKS


KEY = "sk-abcdefghijklmnopqrstuvwxyz"


class TestModuleSurface(unittest.TestCase):
    def test_feature_ids_exact(self):
        self.assertEqual(ic.FEATURE_IDS,
                         ("V1", "V2", "V5", "V16", "V24", "V26", "V31"))

    def test_errors_are_fail_closed_and_scrubbed(self):
        err = ic.ContractValidationError("bad token=" + KEY)
        self.assertIsInstance(err, ic.ContractError)
        self.assertNotIn(KEY, str(err))
        self.assertIn("[REDACTED]", str(err))

    def test_secret_detection(self):
        for value in (KEY, "ghp_" + "a" * 20, "password: hunter2"):
            with self.subTest(value=value):
                self.assertTrue(ic.is_secret_like(value))
                self.assertNotIn(value, ic.redact_text(value))
        self.assertFalse(ic.is_secret_like("read config file"))

    def test_canonical_hash_is_order_independent(self):
        a = ic.content_hash({"b": 2, "a": 1})
        b = ic.content_hash({"a": 1, "b": 2})
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_no_host_imports_in_source(self):
        """The module must stay pure: no socket/subprocess/time/random I/O."""
        path = Path(ic.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        banned = {"socket", "subprocess", "time", "random", "os", "asyncio",
                  "pathlib", "http", "urllib", "keel"}
        self.assertFalse(imported & banned, "banned imports: %s" % (imported & banned))


class TestV1ScopeTree(unittest.TestCase):
    """Plugin scopes dispose everything on unload and never escalate."""

    def tearDown(self):
        # Always drain any scope left active by a failed test.
        while ic.active_scope() is not None:
            ic.active_scope().__exit__(None, None, None)

    def test_registration_requires_active_scope(self):
        with self.assertRaises(ic.ScopeError):
            ic.register("tool", "orphan")

    def test_known_registration_kinds(self):
        self.assertEqual(ic.REGISTRATION_KINDS,
                         frozenset({"tool", "hook", "route", "ui_panel", "timer", "subprocess"}))

    def test_active_scope_and_auto_dispose(self):
        events = []
        with ic.plugin_scope("plugin-a", permissions={"tool.use"}) as scope:
            self.assertIs(ic.active_scope(), scope)
            h1 = ic.register("tool", "shell", lambda: events.append("tool"))
            h2 = ic.register("hook", "on_message", lambda: events.append("hook"))
            ic.register("timer", "tick")
            self.assertTrue(callable(h1._on_dispose))
            self.assertFalse(h1.disposed)
        self.assertIsNone(ic.active_scope())
        self.assertTrue(scope.closed)
        # LIFO disposal: last registered disposed first.
        self.assertEqual(events, ["hook", "tool"])
        self.assertTrue(all(h.disposed for h in (h1, h2)))

    def test_unknown_kind_and_bad_on_dispose_rejected(self):
        with ic.plugin_scope("p") as scope:
            with self.assertRaises(ic.ContractValidationError):
                scope.register("backdoor", "x")
            with self.assertRaises(ic.ContractValidationError):
                scope.register("tool", "x", on_dispose="not-callable")
            with self.assertRaises(ic.ContractValidationError):
                scope.register("tool", "")

    def test_closed_scope_fails_closed(self):
        scope = ic.plugin_scope("p", permissions={"a"})
        scope.close()
        for action in (
            lambda: scope.register("tool", "x"),
            lambda: scope.child("c"),
            lambda: scope.grant_permission("a"),
            lambda: scope.__enter__(),
        ):
            with self.subTest(action=action):
                with self.assertRaises(ic.ScopeError):
                    action()
        self.assertFalse(scope.has_permission("a"))
        self.assertEqual(scope.effective_permissions(), frozenset())

    def test_permissions_inherit_down_never_up(self):
        root = ic.plugin_scope("root", permissions={"read", "write", "exec"})
        with root:
            child = root.child("child", permissions={"read"})
            self.assertTrue(child.has_permission("read"))
            self.assertFalse(child.has_permission("write"))
            self.assertTrue(root.has_permission("write"))
            # a child cannot hold a permission the parent never had
            with self.assertRaises(ic.ContractValidationError):
                root.child("evil", permissions={"sudo"})
            # nor can it escalate to a permission the parent never held
            with self.assertRaises(ic.ContractValidationError):
                child.grant_permission("sudo")
            # a permission the parent does hold may legitimately flow down
            child.grant_permission("write")
            self.assertTrue(child.has_permission("write"))
            child.require_permission("read")
            with self.assertRaises(ic.ScopeError):
                child.require_permission("exec")
            # parent never gains child's permissions (it has none unique here)
            self.assertNotIn("child-only", root.effective_permissions())

    def test_child_close_disposes_children_and_registrations(self):
        events = []
        with ic.plugin_scope("root") as root:
            child = root.child("c")
            child.register("subprocess", "node", lambda: events.append("proc"))
            root.register("hook", "h", lambda: events.append("hook"))
            self.assertEqual(child.close(), 1)
            self.assertEqual(events, ["proc"])
        self.assertEqual(events, ["proc", "hook"])
        self.assertIn(child, root.children)

    def test_load_unload_100_times_leaks_nothing(self):
        live = {"count": 0}

        def make():
            live["count"] += 1
            return lambda: live.__setitem__("count", live["count"] - 1)

        for i in range(100):
            with ic.plugin_scope("plugin-%d" % i, permissions={"tool.use"}) as scope:
                for kind in ic.REGISTRATION_KINDS:
                    ic.register(kind, "%s-%d" % (kind, i), make())
        self.assertEqual(live["count"], 0)
        self.assertTrue(scope.closed)
        self.assertEqual(ic.live_disposables(), ())
        ic.assert_no_leaks()

    def test_assert_no_leaks_detects_live_registration(self):
        scope = ic.plugin_scope("leaky")
        scope.register("timer", "forgotten")
        with self.assertRaises(ic.ScopeError):
            ic.assert_no_leaks()
        scope.close()
        ic.assert_no_leaks()

    def test_to_dict_is_serializable(self):
        with ic.plugin_scope("p", permissions={"b", "a"}) as scope:
            ic.register("tool", "t")
        payload = scope.to_dict()
        self.assertEqual(payload["permissions"], ["a", "b"])
        json.dumps(payload, sort_keys=True)
        self.assertTrue(payload["closed"])
        self.assertTrue(payload["registrations"][0]["disposed"])


class TestV2PolicySimulator(unittest.TestCase):
    """Ordered rules, winning rule, multi-resource denial and Tier-2 verdict."""

    def test_ordered_trace_and_winner(self):
        rules = (
            ic.make_rule("r1", ic.Effect.DENY, "exec", "*"),
            ic.make_rule("r2", ic.Effect.ALLOW, "read", "file:*"),
            ic.make_rule("r3", ic.Effect.ALLOW, "read", "*"),
        )
        trace = ic.simulate(ic.make_operation("read", "file:a"), rules)
        self.assertEqual(trace.verdict, ic.Verdict.ALLOW)
        self.assertEqual(trace.winner_id, "r2")
        self.assertEqual([e.rule_id for e in trace.evaluations], ["r1", "r2", "r3"])
        self.assertTrue(trace.evaluations[0].matched is False)
        self.assertTrue(trace.evaluations[1].matched)
        self.assertIn("winner", trace.to_json())
        json.loads(trace.to_json())

    def test_deny_rule_wins_over_earlier_allow(self):
        rules = (
            ic.make_rule("allow", ic.Effect.ALLOW, "*", "*"),
            ic.make_rule("deny", ic.Effect.DENY, "exec", "*"),
        )
        trace = ic.simulate(ic.make_operation("exec", "shell"), rules)
        self.assertEqual(trace.verdict, ic.Verdict.DENY)
        self.assertEqual(trace.winner_id, "deny")
        self.assertIn("matched deny rule 'deny'", trace.denial_reason)

    def test_multi_resource_denial_reason(self):
        rules = (
            ic.make_rule("allow-file", ic.Effect.ALLOW, "write", "file:*"),
            ic.make_rule("deny-secret", ic.Effect.DENY, "*", "secret:*"),
        )
        trace = ic.simulate(
            ic.make_operation("write", ("file:ok", "secret:key")), rules)
        self.assertEqual(trace.verdict, ic.Verdict.DENY)
        self.assertIn("secret:key", trace.denial_reason)
        self.assertIn("deny rule 'deny-secret'", trace.denial_reason)
        decisions = {d.resource: d for d in trace.per_resource}
        self.assertEqual(decisions["file:ok"].effect, ic.Verdict.ALLOW)
        self.assertEqual(decisions["secret:key"].effect, ic.Verdict.DENY)

    def test_default_deny_when_no_rule_matches(self):
        trace = ic.simulate(ic.make_operation("delete", "db"), ())
        self.assertEqual(trace.verdict, ic.Verdict.DENY)
        self.assertIsNone(trace.winner_id)
        self.assertIn("default deny", trace.denial_reason)

    def test_tier2_verdicts(self):
        rules = (ic.make_rule("allow", ic.Effect.ALLOW, "read", "*"),)
        op = ic.make_operation("read", "file:x", tier=2)
        t1 = ic.simulate(op, rules)
        self.assertEqual(t1.tier2, ic.Tier2Verdict.REQUIRES_APPROVAL)
        self.assertEqual(t1.verdict, ic.Verdict.DENY)
        t2 = ic.simulate(op, rules, tier2_approved=True)
        self.assertEqual(t2.tier2, ic.Tier2Verdict.PASS)
        self.assertEqual(t2.verdict, ic.Verdict.ALLOW)
        t3 = ic.simulate(ic.make_operation("read", "file:x", tier=1), rules)
        self.assertEqual(t3.tier2, ic.Tier2Verdict.NOT_APPLICABLE)
        deny_rules = (ic.make_rule("d", ic.Effect.DENY, "*", "secret:*"),)
        t4 = ic.simulate(ic.make_operation("read", "secret:x", tier=2), deny_rules)
        self.assertEqual(t4.tier2, ic.Tier2Verdict.BLOCKED)

    def test_invalid_inputs_fail_closed(self):
        op = ic.make_operation("read", "file:x")
        for bad in (
            lambda: ic.make_rule("x", "maybe", "*", "*"),
            lambda: ic.make_rule("", ic.Effect.ALLOW, "*", "*"),
            lambda: ic.make_rule("x", ic.Effect.ALLOW, (), "*"),
            lambda: ic.make_operation("", "file:x"),
            lambda: ic.make_operation("read", ()),
            lambda: ic.make_operation("read", "x", tier=3),
            lambda: ic.simulate("not-an-operation", ()),
            lambda: ic.simulate(op, ("not-a-rule",)),
            lambda: ic.simulate(op, (), tier2_approved="yes"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ic.ContractValidationError):
                    bad()


class TestV5StrictnessPresets(unittest.TestCase):
    """Cautious / Balanced / Trusted are ordered, monotonic rule sets."""

    def test_preset_order_and_structure(self):
        self.assertEqual([s.value for s in ic.STRICTNESS_ORDER],
                         ["cautious", "balanced", "trusted"])
        for level in ic.STRICTNESS_ORDER:
            with self.subTest(level=level):
                rules = ic.preset_rules(level)
                self.assertTrue(rules)
                self.assertEqual(len({r.id for r in rules}), len(rules))
                self.assertTrue(all(isinstance(r, ic.Rule) for r in rules))
        self.assertEqual(ic.describe_preset("balanced")["strictness"], "balanced")
        self.assertGreater(ic.describe_preset("trusted")["rule_count"], 0)

    def test_monotonic_permissiveness(self):
        ops = (
            ic.make_operation("read", "file:a"),
            ic.make_operation("write", "file:a"),
            ic.make_operation("exec", "shell"),
        )
        for op in ops:
            with self.subTest(op=op.to_dict()):
                verdicts = [
                    ic.simulate(op, ic.preset_rules(level)).verdict
                    for level in ic.STRICTNESS_ORDER
                ]
                # once allowed by a stricter preset it stays allowed
                allowed = [v is ic.Verdict.ALLOW for v in verdicts]
                self.assertEqual(allowed, sorted(allowed))

    def test_secrets_always_denied(self):
        for level in ic.STRICTNESS_ORDER:
            trace = ic.simulate(ic.make_operation("read", "secret:key"),
                                ic.preset_rules(level))
            self.assertEqual(trace.verdict, ic.Verdict.DENY)

    def test_tier2_presets(self):
        op = ic.make_operation("read", "file:a", tier=2)
        cautious = ic.simulate(op, ic.preset_rules(ic.Strictness.CAUTIOUS))
        balanced = ic.simulate(op, ic.preset_rules(ic.Strictness.BALANCED))
        self.assertEqual(cautious.tier2, ic.Tier2Verdict.REQUIRES_APPROVAL)
        self.assertEqual(balanced.tier2, ic.Tier2Verdict.PASS)

    def test_unknown_preset_fails_closed(self):
        for value in ("paranoid", "", None, 7):
            with self.subTest(value=value):
                with self.assertRaises(ic.ContractValidationError):
                    ic.preset_rules(value)
                with self.assertRaises(ic.ContractValidationError):
                    ic.describe_preset(value)


class TestV16InvariantGates(unittest.TestCase):
    """Every catalog gate rejects its failing fixture and missing input."""

    def test_catalog_ids(self):
        self.assertEqual(len(ic.GATE_CATALOG), 8)
        self.assertEqual(len({g.id for g in ic.GATE_CATALOG}), 8)
        self.assertTrue(all(g.failing_fixture for g in ic.GATE_CATALOG))

    def test_all_failing_fixtures_are_rejected(self):
        for gate_id, result in ic.check_all_failing_fixtures().items():
            with self.subTest(gate=gate_id):
                self.assertFalse(result.passed, result.reason)
                self.assertTrue(result.reason)

    def test_good_observations_pass(self):
        table = {"tier2": ["rule-a", "rule-b"]}
        observations = {
            "V16.TIER2_HASH": {"table": table,
                               "expected_hash": ic.compute_tier2_hash(table)},
            "V16.OFFLINE_NET": {"offline": True, "network_calls": 0},
            "V16.NO_SECRET_LOGS": {"log_lines": ["tool ok", "request 200"]},
            "V16.TOOL_PRESENTER": {"tools": {"shell": {"presenter": True}}},
            "V16.PLUGIN_PERMISSIONS": {"manifests": {"p": {"permissions": []}}},
            "V16.NO_HARDCODED_COPY": {"ui_strings": ["i18n:save"]},
            "V16.MIGRATION_MATRIX": {"matrix": {"v1": ["v2"]},
                                     "from_version": "v1", "to_version": "v2"},
            "V16.ANY_BASELINE": {"any_count": 5, "baseline_any_count": 5},
        }
        results = ic.run_all_gates(observations)
        self.assertEqual(len(results), 8)
        self.assertTrue(ic.all_gates_pass(results),
                        [r.to_dict() for r in results if not r.passed])

    def test_hash_drift_sandboxed(self):
        table = {"tier2": ["a"]}
        good = ic.check_gate("V16.TIER2_HASH",
                             {"table": table, "expected_hash": ic.compute_tier2_hash(table)})
        bad = ic.check_gate("V16.TIER2_HASH",
                            {"table": {"tier2": ["b"]},
                             "expected_hash": ic.compute_tier2_hash(table)})
        self.assertTrue(good.passed)
        self.assertFalse(bad.passed)

    def test_missing_observation_fails_closed(self):
        results = ic.run_all_gates({})
        self.assertFalse(ic.all_gates_pass(results))
        self.assertTrue(all(not r.passed for r in results))
        self.assertFalse(ic.check_gate("V16.NO_SECRET_LOGS", {}).passed)

    def test_unknown_gate_fails_closed(self):
        with self.assertRaises(ic.ContractValidationError):
            ic.check_gate("V16.UNKNOWN", {})
        with self.assertRaises(ic.ContractValidationError):
            ic.gate_fixture_result("V16.UNKNOWN")

    def test_secret_in_log_reason_is_redacted(self):
        result = ic.check_gate("V16.NO_SECRET_LOGS", {"log_lines": ["api_key=" + KEY]})
        self.assertFalse(result.passed)
        self.assertNotIn(KEY, result.reason)
        self.assertIn("[REDACTED]", result.reason)

    def test_malformed_observation_rejected(self):
        self.assertFalse(ic.check_gate("V16.OFFLINE_NET", "not-a-mapping").passed)
        self.assertFalse(ic.check_gate("V16.ANY_BASELINE",
                                       {"any_count": "many", "baseline_any_count": 3}).passed)


class TestV24ToolConformanceKit(unittest.TestCase):
    """Descriptor/checker with one failing fixture per conformance check."""

    def test_check_catalog(self):
        self.assertEqual([c.id for c in CONFORMANCE_CHECKS], [
            "output_schema_declared", "presenter_pure_on_replay",
            "cancel_within_budget", "no_leaked_fields",
            "concurrency_read_only", "timeout_cooperative", "errors_typed",
        ])

    def test_conformant_metadata_passes(self):
        report = ic.check_tool_conformance("shell", ic.conformant_metadata())
        self.assertTrue(report.passed)
        json.dumps(report.to_dict(), sort_keys=True)

    def test_each_failing_fixture_is_rejected(self):
        for check in CONFORMANCE_CHECKS:
            with self.subTest(check=check.id):
                meta = ic.failing_conformance_metadata(check.id)
                report = ic.check_tool_conformance("tool", meta)
                self.assertFalse(report.passed)
                failed = {r.check_id for r in report.results if not r.passed}
                self.assertIn(check.id, failed)

    def test_missing_metadata_keys_fail(self):
        report = ic.check_tool_conformance("tool", {})
        self.assertFalse(report.passed)
        self.assertEqual(len(report.results), len(CONFORMANCE_CHECKS))
        self.assertTrue(all(not r.passed for r in report.results))

    def test_gate_fails_on_unregistered_tool(self):
        report = ic.conformance_gate({
            "good": {"conformance": ic.conformant_metadata()},
            "unregistered": {"name": "new-tool"},
        })
        self.assertFalse(report.passed)
        self.assertEqual(report.missing_metadata, ("unregistered",))
        self.assertEqual(report.tools, ("good", "unregistered"))

    def test_gate_passes_when_all_tools_register(self):
        report = ic.conformance_gate({
            "a": {"conformance": ic.conformant_metadata()},
            "b": {"conformance": ic.conformant_metadata()},
        })
        self.assertTrue(report.passed)

    def test_assert_conformant_raises_on_failure(self):
        ic.assert_conformant({"ok": {"conformance": ic.conformant_metadata()}})
        with self.assertRaises(ic.ContractValidationError):
            ic.assert_conformant({"bad": {"conformance": ic.failing_conformance_metadata(
                "concurrency_read_only")}})
        with self.assertRaises(ic.ContractValidationError):
            ic.assert_conformant({"missing": {}})

    def test_unknown_inputs_fail_closed(self):
        for bad in (
            lambda: ic.check_tool_conformance("t", "not-a-mapping"),
            lambda: ic.failing_conformance_metadata("no-such-check"),
            lambda: ic.conformance_gate("not-a-registry"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ic.ContractValidationError):
                    bad()


class TestV26RequestReconstruction(unittest.TestCase):
    """Replay a session log into the exact provider request (D2.11)."""

    def _fixture(self):
        log = ic.session_log_fixture()
        request = ic.reconstruct_request(log)
        return log, request, ic.content_hash(request)

    def test_replay_matches_recorded_hash(self):
        log, request, digest = self._fixture()
        record = ic.record_request("step-1", request)
        self.assertEqual(record.request_hash, digest)
        result = ic.verify_reconstruction(log, record.request_hash,
                                          sent_request=request)
        self.assertTrue(result.passed, result.reason)
        self.assertEqual(result.computed_hash, digest)
        self.assertEqual(result.expected_hash, digest)
        json.dumps(result.to_dict(), sort_keys=True)

    def test_request_shape(self):
        _, request, _ = self._fixture()
        self.assertEqual(request["model"], "keel-test-model")
        self.assertEqual(request["system"], "You are Keel.")
        self.assertEqual(len(request["messages"]), 1)
        self.assertEqual(len(request["tools"]), 1)
        self.assertEqual(request["params"], {"temperature": 0})

    def test_any_tampered_byte_is_detected(self):
        log, _, digest = self._fixture()
        tampered = (
            ic.tamper_log(log, 0, "value", "different-model"),
            ic.tamper_log(log, 1, "value", "You are Evil."),
            ic.tamper_log(log, 2, "content", "different prompt"),
            ic.tamper_log(log, 4, "value", 1),
            log + [{"kind": "param", "key": "temperature", "value": 2}],
            log[:-1],
        )
        for index, altered in enumerate(tampered):
            with self.subTest(tamper=index):
                result = ic.verify_reconstruction(altered, digest)
                self.assertFalse(result.passed)
                self.assertNotEqual(result.computed_hash, digest)

    def test_sent_request_mismatch_detected(self):
        log, _, digest = self._fixture()
        result = ic.verify_reconstruction(log, digest, sent_request={"model": "other"})
        self.assertFalse(result.passed)
        self.assertIn("sent request bytes differ", result.reason)

    def test_explicit_hash_mismatch_detected(self):
        log, _, _ = self._fixture()
        result = ic.verify_reconstruction(log, "f" * 64)
        self.assertFalse(result.passed)
        self.assertIn("hash differs", result.reason)

    def test_empty_system_prompt_clears(self):
        log = ic.session_log_fixture()
        log.append({"kind": "system_prompt", "value": ""})
        self.assertIsNone(ic.reconstruct_request(log)["system"])

    def test_malformed_logs_fail_closed(self):
        base = ic.session_log_fixture()
        for bad in (
            [{"kind": "unknown", "value": "x"}],
            base + [{"kind": "message", "role": "user", "content": 5}],
            base + [{"kind": "tool_spec", "name": "x", "schema": []}],
            base + [{"kind": "param", "key": "", "value": 1}],
            [e for e in base if e["kind"] != "model"],
            "not-a-log",
            [None],
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ic.ContractValidationError):
                    ic.reconstruct_request(bad)

    def test_bad_expected_hash_and_tamper_index(self):
        log = ic.session_log_fixture()
        for bad_hash in ("short", 42, "G" * 64):
            with self.subTest(bad_hash=bad_hash):
                with self.assertRaises(ic.ContractValidationError):
                    ic.verify_reconstruction(log, bad_hash)
        with self.assertRaises(ic.ContractValidationError):
            ic.tamper_log(log, 99, "value", "x")

    def test_model_override(self):
        log = [e for e in ic.session_log_fixture() if e["kind"] != "model"]
        self.assertEqual(ic.reconstruct_request(log, model="override")["model"], "override")


class TestV31LocalSocketSpike(unittest.TestCase):
    """Descriptor-only spike verdict: no socket is ever opened."""

    def test_candidates_and_selection(self):
        self.assertEqual([d.transport for d in ic.TRANSPORT_CANDIDATES],
                         [ic.Transport.NAMED_PIPE, ic.Transport.UDS,
                          ic.Transport.TCP_TOKEN])
        self.assertTrue(all(d.viable for d in ic.TRANSPORT_CANDIDATES))
        self.assertEqual(ic.select_transport("windows"), ic.Transport.NAMED_PIPE)
        self.assertEqual(ic.select_transport("linux"), ic.Transport.UDS)
        self.assertEqual(ic.select_transport("darwin"), ic.Transport.UDS)

    def test_platform_support(self):
        self.assertTrue(ic.platform_support("named_pipe", "windows"))
        self.assertFalse(ic.platform_support("named_pipe", "linux"))
        self.assertTrue(ic.platform_support("uds", "darwin"))
        self.assertTrue(ic.platform_support("tcp_token", "windows"))

    def test_spike_decision_complete(self):
        decision = ic.spike_decision()
        self.assertTrue(decision.complete)
        self.assertEqual(decision.covered_os, frozenset(ic.SUPPORTED_OS))
        self.assertEqual(set(decision.primaries),
                         {ic.Transport.NAMED_PIPE, ic.Transport.UDS})
        self.assertEqual(decision.fallback, ic.Transport.TCP_TOKEN)
        self.assertTrue(decision.streaming and decision.backpressure)
        self.assertTrue(decision.peer_auth and decision.fallback_available)
        self.assertTrue(json.loads(json.dumps(decision.to_dict()))["complete"])
        self.assertEqual(ic.evaluate_spike(), decision)

    def test_nonviable_descriptor_rejected(self):
        bad = ic.TransportDescriptor(ic.Transport.UDS, "no backpressure",
                                     frozenset({"linux"}), True, False, True,
                                     True, False)
        self.assertFalse(bad.viable)
        with self.assertRaises(ic.ContractValidationError):
            ic.validate_transport(bad)
        with self.assertRaises(ic.ContractValidationError):
            ic.validate_transport("uds")

    def test_unknown_transport_and_os_fail_closed(self):
        for bad in (
            lambda: ic.platform_support("carrier-pigeon", "linux"),
            lambda: ic.platform_support("uds", "plan9"),
            lambda: ic.select_transport("plan9"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ic.ContractValidationError):
                    bad()


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)

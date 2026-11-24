"""E3 backend tests: the thirteen P1/P2 subagent rows plus P0 verification.

Covers E3.1, E3.2, E3.4, E3.5, E3.6, E3.7, E3.9, E3.10, E3.11, E3.12,
E3.13, E3.14 and E3.15 against ``keel.e3_backend``.  E3.3/E3.8 are already
implemented in ``keel.result_contracts`` and are checked through
``verify_p0_contracts`` and result sanitisation.  Stdlib-only runner::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_e3_backend.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import inspect
import unittest

import keel.e3_backend as e3
from keel.e3_backend import (
    ERR_AT_CAPACITY,
    ERR_CAPABILITY,
    ERR_IMAGE_NOT_ACCEPTED,
    ERR_INPUT_CLOSED,
    ERR_INTERRUPT_DENIED,
    ERR_INVALID_ROUTE,
    ERR_NO_FOLLOW_UP,
    ERR_ROUTE_NOT_ALLOWED,
    FEATURE_IDS,
    P0_VERIFIED_IDS,
    USER_ACTOR,
    ActivationRequest,
    ActivationStatus,
    AlreadyActive,
    AlreadySettled,
    Attachment,
    BranchDiagnostic,
    Capability,
    CapabilityNotSupported,
    DeliveryOutcome,
    DeliveryPolicy,
    DeliveryUnavailable,
    E3ValidationError,
    ImageNotAccepted,
    InputClosed,
    InterruptDeniedError,
    LifecycleKind,
    Message,
    MessageSource,
    ModelRoute,
    NoFollowUp,
    ProviderCapabilities,
    ProviderKind,
    RouteError,
    RouteNotAllowed,
    SpawnMode,
    StartOptions,
    SubagentManager,
    TurnStep,
    compute_fork_prefix,
    parse_model_route,
    resolve_child_cwd,
    set_route_allowlist,
    verify_p0_contracts,
)


SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}


def caps(provider_id: str = "local", *extra: Capability, images: bool = False) -> ProviderCapabilities:
    """Local-capability set plus optional extras, matching the built-in provider."""
    flags = frozenset(set(e3.E3_1_CAPABILITIES) | set(extra))
    return ProviderCapabilities(provider_id, flags, accepts_images=images)


def req(agent_id: str, parent_id: str = "lead", provider_id: str = "local",
        kind: ProviderKind = ProviderKind.LOCAL, **kw) -> ActivationRequest:
    return ActivationRequest(agent_id, parent_id, provider_id, kind, **kw)


def parked_message(recipient: str, label: str = "park") -> Message:
    """Caller-constructed unclaimed inbox item (parked input)."""
    return Message(
        message_id="parked-%s" % label,
        source=MessageSource.AGENT_MESSAGE,
        sender_id="lead",
        recipient_id=recipient,
        text="parked",
        sequence=9000,
        accepted=True,
        claimed=False,
    )


class TestP0Verification(unittest.TestCase):
    """E3.3/E3.8 are implemented in result_contracts; prove they are live."""

    def test_all_thirteen_ids_and_two_p0_ids(self):
        self.assertEqual(len(FEATURE_IDS), 13)
        self.assertNotIn("E3.3", FEATURE_IDS)
        self.assertNotIn("E3.8", FEATURE_IDS)
        self.assertEqual(P0_VERIFIED_IDS, ("E3.3", "E3.8"))

    def test_verify_p0_contracts_reports_both(self):
        self.assertEqual(verify_p0_contracts(), {"E3.3": True, "E3.8": True})

    def test_settle_reuses_result_contracts_sanitizer(self):
        m = SubagentManager()
        aid = m.start(req("writer"))
        result = m.settle(aid, final_text="ok", diagnostics="token sk-abcdefghijklmnopqrstuvwxyz").result
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", result.diagnostics)


class TestE31Capabilities(unittest.TestCase):
    """One activation API; validate the four options before anything starts."""

    def test_all_four_options_accepted(self):
        m = SubagentManager()
        opts = StartOptions({"x": 1}, "preset-a", SCHEMA, 3)
        aid = m.start(req("researcher", options=opts))
        act = m.activations[aid]
        self.assertEqual(act.options.depth_limit, 3)
        self.assertEqual(act.options.agent_preset, "preset-a")

    def test_each_unsupported_option_is_rejected_before_mutation(self):
        opts = StartOptions({"x": 1}, "preset-a", SCHEMA, 3)
        cases = (
            (Capability.AGENT_OPTIONS, "agent_options"),
            (Capability.AGENT_PRESET, "agent_preset"),
            (Capability.OUTPUT_SCHEMA, "output_schema"),
            (Capability.DEPTH_LIMIT, "depth_limit"),
        )
        for missing, label in cases:
            with self.subTest(missing=missing):
                flags = frozenset(e3.E3_1_CAPABILITIES - {missing})
                m = SubagentManager()
                m.register_provider(ProviderCapabilities("thin", flags))
                with self.assertRaises(CapabilityNotSupported) as ctx:
                    m.start(req("child", provider_id="thin", options=opts))
                self.assertEqual(ctx.exception.code, ERR_CAPABILITY)
                self.assertIn(label, str(ctx.exception))
                self.assertNotIn("child", m.nodes)
                self.assertEqual(m.activations, {})
                self.assertEqual(m.events_for_root("lead"), ())

    def test_unknown_capability_fails_closed(self):
        with self.assertRaises(E3ValidationError):
            ProviderCapabilities("p", frozenset({"telepathy"}))

    def test_external_needs_capability(self):
        m = SubagentManager()
        with self.assertRaises(CapabilityNotSupported):
            m.start(req("ext", provider_id="local", kind=ProviderKind.EXTERNAL))

    def test_malformed_request_types_rejected(self):
        m = SubagentManager()
        with self.assertRaises(E3ValidationError):
            m.start({"agent_id": "x"})
        with self.assertRaises(E3ValidationError):
            StartOptions(depth_limit=-1)
        with self.assertRaises(E3ValidationError):
            ProviderCapabilities("bad id")

    def test_duplicate_provider_registration_is_rejected(self):
        m = SubagentManager()
        original = m.providers["local"]
        events_before = len(m.events)
        weak = ProviderCapabilities("local", frozenset(), accepts_images=False)
        with self.assertRaises(E3ValidationError) as ctx:
            m.register_provider(weak)
        self.assertIn("local", str(ctx.exception))
        # The built-in provider (and its capabilities) must survive intact.
        self.assertIs(m.providers["local"], original)
        self.assertEqual(m.providers["local"].capabilities, original.capabilities)
        self.assertEqual(len(m.events), events_before)

    def test_settle_error_without_error_value_fails_closed(self):
        m = SubagentManager()
        aid = m.start(req("child"))
        with self.assertRaises(E3ValidationError):
            m.settle(aid, stop_reason=e3.StopReason.ERROR)
        self.assertIs(m.activations[aid].status, e3.ActivationStatus.LIVE)
        # An explicit error still settles into a typed failure result.
        settlement = m.settle(aid, stop_reason=e3.StopReason.ERROR, error="boom")
        self.assertIs(settlement.result.stop_reason, e3.StopReason.ERROR)
        self.assertIn("boom", settlement.result.diagnostics)


class TestE32Delivery(unittest.TestCase):
    """Parent notification vs caller-only result."""

    def test_parent_delivers_settled_notice(self):
        m = SubagentManager()
        aid = m.start(req("child"))
        settlement = m.settle(aid, final_text="secret answer")
        self.assertTrue(settlement.delivery.delivered_to_parent)
        self.assertFalse(settlement.delivery.returned_to_caller)
        notice = next(msg for msg in m.messages if msg.message_id == settlement.delivery.message_id)
        self.assertIs(notice.source, MessageSource.SUBAGENT_SETTLED)
        self.assertFalse(notice.attributed_to_child)
        self.assertNotIn("secret answer", notice.text)
        self.assertIs(notice.settled_result, settlement.result)

    def test_caller_only_returns_result(self):
        m = SubagentManager()
        aid = m.start(req("child", delivery=DeliveryPolicy.CALLER))
        settlement = m.settle(aid, final_text="value")
        self.assertEqual(settlement.delivery, DeliveryOutcome(False, True, None, "caller-policy"))
        self.assertEqual(settlement.result.final_output, "value")
        self.assertEqual(m.messages, [])

    def test_double_settle_rejected(self):
        m = SubagentManager()
        aid = m.start(req("child"))
        m.settle(aid, final_text="x")
        with self.assertRaises(AlreadySettled):
            m.settle(aid, final_text="y")


class TestE34WorkingDirectory(unittest.TestCase):
    """Admission cwd, parent project retention and logged resume state."""

    def test_relative_resolves_against_parent(self):
        parent = resolve_child_cwd(e3.ChildWorkingDirectory(".", "/proj", "main"), "work", "main")
        child = resolve_child_cwd(parent, "logs", "main")
        self.assertEqual(child.resolved, "/proj/work/logs")
        self.assertEqual(child.requested, "logs")

    def test_absolute_cwd_is_not_rebased(self):
        cwd = resolve_child_cwd(e3.ChildWorkingDirectory(".", "/proj", "main"), "C:/tools", "main")
        self.assertEqual(cwd.resolved, "C:/tools")

    def test_local_child_keeps_parent_project(self):
        m = SubagentManager()
        m.register_provider(caps("proj", images=True))
        root_act = m.start(req("child", cwd_request="work"))
        m.settle(root_act, final_text="x")
        root_node = m.nodes["child"]
        self.assertEqual(root_node.project, "")
        self.assertEqual(root_node.cwd.resolved, "work")
        # Grandchild resolves against child's cwd and keeps the same project.
        m2 = SubagentManager()
        m2.start(req("child", cwd_request="/proj/work"))
        m2.start(req("grand", parent_id="child", cwd_request="logs"))
        self.assertEqual(m2.nodes["grand"].cwd.resolved, "/proj/work/logs")
        self.assertEqual(m2.nodes["grand"].project, m2.nodes["child"].project)

    def test_resume_retains_logged_directory(self):
        m = SubagentManager()
        aid = m.start(req("child", provider_id="local", cwd_request="admitted/place"))
        logged = m.activations[aid].cwd
        m.settle(aid, final_text="x")
        m.send_message("lead", "child", "wake up")
        resumed = m._last_activation("child")
        self.assertEqual(resumed.cwd, logged)
        self.assertEqual(resumed.cwd.resolved, "admitted/place")


class TestE35DurableChild(unittest.TestCase):
    """One live activation, capacity, input closure and child-first disposal."""

    def test_at_most_one_live_activation(self):
        m = SubagentManager()
        m.start(req("child"))
        with self.assertRaises(AlreadyActive):
            m.start(req("child"))

    def test_capacity_rejection_is_typed(self):
        m = SubagentManager(capacity=1)
        first = m.start(req("first"))
        m.settle(first, final_text="x")
        m.start(req("second"))
        with self.assertRaises(DeliveryUnavailable) as ctx:
            m.send_message("lead", "first", "resume")
        self.assertEqual(ctx.exception.code, ERR_AT_CAPACITY)

    def test_structured_capture_closes_input_and_resume_drops_schema(self):
        m = SubagentManager()
        aid = m.start(req("child", options=StartOptions(output_schema=SCHEMA)))
        m.settle(aid, final_text="ok", structured={"ok": True})
        self.assertTrue(m.activations[aid].input_closed)
        # A fresh activation for the same durable child must not keep the schema.
        m.send_message("lead", "child", "continue")
        resumed = m._last_activation("child")
        self.assertIsNone(resumed.options.output_schema)
        self.assertFalse(resumed.input_closed)

    def test_steering_a_closed_activation_is_rejected(self):
        m = SubagentManager()
        aid = m.start(req("child", options=StartOptions(output_schema=SCHEMA)))
        # Simulate an activation that captured output but has not settled yet.
        m.activations[aid].input_closed = True
        with self.assertRaises(InputClosed) as ctx:
            m.send_message("lead", "child", "late")
        self.assertEqual(ctx.exception.code, ERR_INPUT_CLOSED)
        self.assertEqual(m.messages, [])

    def test_child_first_disposal_order(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        m.start(req("c", parent_id="b"))
        self.assertEqual(m.dispose_tree("lead"), ("c", "b", "a", "lead"))
        self.assertEqual(m.nodes, {})


class TestE36Fork(unittest.TestCase):
    """Contiguous, lossless, balanced completed-turn prefix; spawn is fresh."""

    def test_happy_path_prefix(self):
        seed = compute_fork_prefix([
            TurnStep("t1"),
            TurnStep("call", opens="g1"),
            TurnStep("result", closes="g1"),
            TurnStep("t4"),
            TurnStep("incomplete", complete=False),
        ], source_agent_id="lead")
        self.assertEqual(seed.tokens, ("t1", "call", "result", "t4"))
        self.assertEqual(seed.source_agent_id, "lead")

    def test_gap_after_incomplete_rejected(self):
        with self.assertRaises(e3.ForkPrefixError):
            compute_fork_prefix([
                TurnStep("partial", complete=False), TurnStep("done"),
            ])

    def test_unbalanced_and_mismatched_groups_rejected(self):
        with self.assertRaises(e3.ForkPrefixError):
            compute_fork_prefix([TurnStep("open", opens="g")])
        with self.assertRaises(e3.ForkPrefixError):
            compute_fork_prefix([TurnStep("close", closes="g")])
        with self.assertRaises(e3.ForkPrefixError):
            compute_fork_prefix([
                TurnStep("a", opens="g1"), TurnStep("b", closes="g2"),
            ])

    def test_fork_requires_seed_and_records_it(self):
        m = SubagentManager()
        with self.assertRaises(e3.ForkPrefixError):
            m.start(req("child", spawn_mode=SpawnMode.FORK))
        seed = compute_fork_prefix([TurnStep("one")])
        aid = m.start(req("child", spawn_mode=SpawnMode.FORK, fork_seed=seed))
        self.assertEqual(m.activations[aid].fork_seed, seed)
        spawn = m.start(req("fresh"))
        self.assertIsNone(m.activations[spawn].fork_seed)

    def test_inherits_parent_context_is_wording_only(self):
        states = []
        for flag in (False, True):
            m = SubagentManager()
            aid = m.start(req("child", inherits_parent_context=flag))
            act = m.activations[aid]
            states.append((
                act.status, act.options, act.cwd, act.delivery, act.spawn_mode,
                act.fork_seed, act.model_route, act.one_shot,
            ))
            self.assertIs(act.inherits_parent_context_is_wording, flag)
        self.assertEqual(states[0], states[1])


class TestE37External(unittest.TestCase):
    """One execution, no follow-ups, results to creator only while online."""

    def setUp(self):
        self.m = SubagentManager()
        self.m.register_provider(caps("cli", Capability.EXTERNAL_EXECUTION, images=True))

    def test_external_activation_is_one_shot(self):
        aid = self.m.start(req("ext", provider_id="cli", kind=ProviderKind.EXTERNAL))
        self.assertTrue(self.m.activations[aid].one_shot)
        self.assertIs(self.m.nodes["ext"].mode, e3.AgentMode.EXTERNAL)

    def test_no_follow_up_after_settle(self):
        aid = self.m.start(req("ext", provider_id="cli", kind=ProviderKind.EXTERNAL))
        self.m.settle(aid, final_text="done")
        with self.assertRaises(NoFollowUp) as ctx:
            self.m.send_message("lead", "ext", "again")
        self.assertEqual(ctx.exception.code, ERR_NO_FOLLOW_UP)

    def test_offline_creator_withholds_result(self):
        aid = self.m.start(req("ext", provider_id="cli", kind=ProviderKind.EXTERNAL))
        self.m.unregister_provider("cli")
        settlement = self.m.settle(aid, final_text="done")
        self.assertFalse(settlement.delivery.delivered_to_parent)
        self.assertEqual(settlement.delivery.reason, "creator-offline")
        self.assertEqual(settlement.result.final_output, "done")

    def test_provider_removed_event_is_global(self):
        self.m.unregister_provider("cli")
        event = self.m.events[-1]
        self.assertIs(event.kind, LifecycleKind.PROVIDER_REMOVED)
        self.assertIsNone(event.tree_root)


class TestE39Messaging(unittest.TestCase):
    """Steer, cold resume, identity recheck, immutable accepted messages."""

    def test_steer_running_target(self):
        m = SubagentManager()
        aid = m.start(req("child"))
        msg = m.send_message("lead", "child", "turn left")
        self.assertTrue(msg.claimed)
        self.assertEqual(m.activations[aid].steered, [msg.message_id])
        self.assertIs(msg.source, MessageSource.AGENT_MESSAGE)
        self.assertTrue(msg.attributed_to_child)

    def test_absent_target_cold_resumes_and_parks_input(self):
        m = SubagentManager()
        first = m.start(req("child"))
        m.settle(first, final_text="x")
        msg = m.send_message("lead", "child", "wake")
        self.assertFalse(msg.claimed)
        self.assertIsNotNone(m._live_activation("child"))

    def test_sender_identity_rechecked(self):
        m = SubagentManager()
        m.start(req("child"))
        with self.assertRaises(e3.NotFoundError):
            m.send_message("ghost", "child", "hi")
        with self.assertRaises(e3.NotFoundError):
            m.send_message("lead", "ghost", "hi")

    def test_accepted_messages_never_retracted(self):
        m = SubagentManager()
        m.start(req("child"))
        msg = m.send_message("lead", "child", "first")
        m.send_message("lead", "child", "second")
        aid = m._live_activation("child").activation_id
        m.settle(aid, final_text="x")
        m.drain_tree("lead")
        self.assertIn(msg, m.messages)
        self.assertEqual([x.message_id for x in m.messages if x.message_id == msg.message_id], [msg.message_id])

    def test_duplicate_message_id_rejected(self):
        m = SubagentManager()
        m.start(req("child"))
        m.send_message("lead", "child", "first", message_id="m-1")
        with self.assertRaises(E3ValidationError):
            m.send_message("lead", "child", "second", message_id="m-1")


class TestE310Interrupt(unittest.TestCase):
    """Authority, fire-and-return and preservation guarantees."""

    def setUp(self):
        self.m = SubagentManager()
        self.m.start(req("a"))
        self.m.start(req("b", parent_id="a"))
        self.m.start(req("c"))
        self.m.start(req("d", parent_id="b"))

    def test_user_and_live_ancestor_authorized(self):
        for actor in (USER_ACTOR, "a"):
            with self.subTest(actor=actor):
                m = SubagentManager()
                m.start(req("a"))
                m.start(req("b", parent_id="a"))
                receipt = m.interrupt("b", actor)
                self.assertTrue(receipt.authorized)
                self.assertTrue(receipt.requested)
                act = m._live_activation("b")
                self.assertIs(act.status, ActivationStatus.INTERRUPT_REQUESTED)
                self.assertTrue(act.interrupt_requested)

    def test_non_ancestor_and_dead_ancestor_denied(self):
        with self.assertRaises(InterruptDeniedError) as ctx:
            self.m.interrupt("b", "c")
        self.assertEqual(ctx.exception.code, ERR_INTERRUPT_DENIED)
        self.m.settle(self.m._live_activation("a").activation_id, final_text="x")
        with self.assertRaises(InterruptDeniedError):
            self.m.interrupt("b", "a")

    def test_absent_target_is_noop(self):
        receipt = self.m.interrupt("ghost", USER_ACTOR)
        self.assertEqual((receipt.found, receipt.authorized, receipt.requested), (False, False, False))

    def test_preserves_inbox_activation_descendants_and_claims(self):
        steered = self.m.send_message("lead", "b", "steer")
        unclaimed = parked_message("b")
        self.m.messages.append(unclaimed)
        receipt = self.m.interrupt("b", USER_ACTOR)
        self.assertEqual(receipt.preserved_inbox, 2)
        self.assertEqual(receipt.preserved_descendants, 1)
        self.assertIs(self.m._live_activation("b").status, ActivationStatus.INTERRUPT_REQUESTED)
        self.assertIsNotNone(self.m._live_activation("d"))
        self.assertTrue(steered.claimed)
        self.assertFalse(unclaimed.claimed)
        self.assertEqual(self.m.activations[self.m._live_activation("b").activation_id].steered,
                         [steered.message_id])


class TestE311Drain(unittest.TestCase):
    """Whole-tree drain and non-blocking parked input."""

    def test_live_work_blocks_host_completion(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        status = m.wait_for_tree_work("lead")
        self.assertEqual(len(status.live_activations), 2)
        self.assertFalse(status.host_can_complete)

    def test_parked_input_stays_resident_and_does_not_block(self):
        m = SubagentManager()
        aid = m.start(req("a"))
        m.settle(aid, final_text="x")
        parked = parked_message("a")
        m.messages.append(parked)
        status = m.wait_for_tree_work("lead")
        # The settled notice to the root is also parked input; both stay resident.
        self.assertIn("a", status.parked_members)
        self.assertTrue(status.host_can_complete)
        self.assertIn("a", m.nodes)

    def test_drain_settles_child_first(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        m.start(req("c", parent_id="b"))
        report = m.drain_tree("lead")
        self.assertEqual(report.disposal_order, ("c", "b", "a", "lead"))
        self.assertEqual(len(report.settled), 3)
        self.assertTrue(m.wait_for_tree_work("lead").host_can_complete)
        # Resident nodes are not removed by a drain.
        self.assertIn("c", m.nodes)


class TestE312Catalog(unittest.TestCase):
    """Parent-owned membership projection, no status, per-branch diagnostics."""

    def test_entries_have_membership_shape_not_status(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        entries = m.list_descendants("lead")
        self.assertEqual([e.agent_id for e in entries], ["a", "b"])
        self.assertEqual([e.depth for e in entries], [1, 2])
        self.assertEqual([e.parent_id for e in entries], ["lead", "a"])
        self.assertEqual(entries[1].path, ("lead", "a", "b"))
        field_names = {f.name for f in e3.CatalogEntry.__dataclass_fields__.values()}
        self.assertFalse(field_names & {"status", "result", "activation", "stop_reason"})

    def test_corrupt_branch_stops_only_that_branch(self):
        m = SubagentManager()
        m.start(req("bad"))
        m.start(req("hidden", parent_id="bad"))
        m.start(req("good"))
        m.nodes["bad"].descriptor_corrupt = True
        entries = m.list_descendants("lead")
        self.assertEqual([e.agent_id for e in entries], ["bad", "good"])
        self.assertIs(entries[0].diagnostic, BranchDiagnostic.CORRUPT)
        self.assertFalse(entries[0].continuation_rights)

    def test_unavailable_descriptor_and_unsupported_provider(self):
        m = SubagentManager()
        m.start(req("gone"))
        m.start(req("unsupported"))
        m.nodes["gone"].descriptor_available = False
        m.register_provider(caps("cli", Capability.EXTERNAL_EXECUTION))
        m.start(req("ext", provider_id="cli", kind=ProviderKind.EXTERNAL))
        # Provider is online again but no longer advertises external_execution.
        m.providers["cli"].capabilities = caps("cli")
        entries = {e.agent_id: e for e in m.list_descendants("lead")}
        self.assertIs(entries["gone"].diagnostic, BranchDiagnostic.UNAVAILABLE)
        self.assertIs(entries["gone"].mode, e3.AgentMode.UNKNOWN)
        self.assertFalse(entries["gone"].continuation_rights)
        self.assertIs(entries["ext"].diagnostic, BranchDiagnostic.UNSUPPORTED)
        self.assertFalse(entries["ext"].continuation_rights)

    def test_historical_child_with_removed_provider_is_unknown(self):
        m = SubagentManager()
        m.register_provider(caps("cli", Capability.EXTERNAL_EXECUTION))
        m.start(req("old", provider_id="cli", kind=ProviderKind.EXTERNAL))
        m.unregister_provider("cli")
        entries = {e.agent_id: e for e in m.list_descendants("lead")}
        self.assertIs(entries["old"].mode, e3.AgentMode.UNKNOWN)
        self.assertIs(entries["old"].diagnostic, BranchDiagnostic.UNAVAILABLE)
        self.assertFalse(entries["old"].continuation_rights)

    def test_cycles_and_repeats_are_skipped(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        m.nodes["b"].child_ids = ("a", "b")
        m.nodes["lead"].child_ids = m.nodes["lead"].child_ids + ("b",)
        entries = m.list_descendants("lead")
        self.assertEqual([e.agent_id for e in entries], ["a", "b"])


class TestE313Routes(unittest.TestCase):
    """Default-off allowlist, read live on each delegation."""

    def test_default_off_rejects_route(self):
        m = SubagentManager()
        with self.assertRaises(RouteNotAllowed) as ctx:
            m.start(req("child", model_route=parse_model_route("openai/gpt-x")))
        self.assertEqual(ctx.exception.code, ERR_ROUTE_NOT_ALLOWED)

    def test_allowlist_takes_effect_live(self):
        m = SubagentManager()
        set_route_allowlist(m, True, ["openai/gpt-x"])
        aid = m.start(req("child", model_route=ModelRoute("openai", "gpt-x")))
        self.assertEqual(str(m.activations[aid].model_route), "openai/gpt-x")
        set_route_allowlist(m, True, ["other/model"])
        with self.assertRaises(RouteNotAllowed):
            m.start(req("child2", model_route=ModelRoute("openai", "gpt-x")))

    def test_disable_allowlist_again(self):
        m = SubagentManager()
        set_route_allowlist(m, True, ["openai/gpt-x"])
        set_route_allowlist(m, False)
        with self.assertRaises(RouteNotAllowed):
            m.start(req("child", model_route="openai/gpt-x"))
        # No route still uses the provider default.
        m.start(req("plain"))

    def test_malformed_and_duplicate_routes_error(self):
        m = SubagentManager()
        for bad in ("nope", "/model", "provider/", "pro/v1/../v2"):
            with self.subTest(bad=bad), self.assertRaises(RouteError):
                parse_model_route(bad)
        with self.assertRaises(RouteError) as ctx:
            set_route_allowlist(m, True, ["openai/gpt-x", "openai/gpt-x"])
        self.assertEqual(ctx.exception.code, ERR_INVALID_ROUTE)


class TestE314Attachments(unittest.TestCase):
    """User-authored UI message with image parts, timezone and capacity error."""

    def test_image_attachment_accepted_when_model_accepts_images(self):
        m = SubagentManager()
        m.start(req("child"))
        att = Attachment("img-1", "image/png", "store://img-1")
        msg = m.send_message("lead", "child", "look", attachments=[att], client_timezone="Europe/Paris")
        self.assertEqual(msg.attachments, (att,))
        self.assertEqual(msg.client_timezone, "Europe/Paris")

    def test_image_rejected_when_model_does_not_accept_images(self):
        m = SubagentManager()
        m.register_provider(ProviderCapabilities("noimg", e3.E3_1_CAPABILITIES, accepts_images=False))
        m.start(req("child", provider_id="noimg"))
        with self.assertRaises(ImageNotAccepted) as ctx:
            m.send_message("lead", "child", "look", attachments=[
                Attachment("img-1", "image/png", "store://img-1")
            ])
        self.assertEqual(ctx.exception.code, ERR_IMAGE_NOT_ACCEPTED)
        self.assertEqual(m.messages, [])

    def test_non_image_attachment_needs_no_image_capability(self):
        m = SubagentManager()
        m.register_provider(ProviderCapabilities("noimg", e3.E3_1_CAPABILITIES, accepts_images=False))
        m.start(req("child", provider_id="noimg"))
        msg = m.send_message("lead", "child", "file", attachments=[
            Attachment("doc-1", "text/plain", "store://doc-1")
        ])
        self.assertEqual(msg.attachments[0].media_type, "text/plain")

    def test_cold_resume_at_capacity_is_typed_delivery_unavailable(self):
        m = SubagentManager(capacity=1)
        first = m.start(req("first"))
        m.settle(first, final_text="x")
        m.start(req("busy"))
        with self.assertRaises(DeliveryUnavailable) as ctx:
            m.send_message("lead", "first", "wake", client_timezone="UTC")
        self.assertEqual(ctx.exception.code, ERR_AT_CAPACITY)


class TestE315Events(unittest.TestCase):
    """subagent/start, subagent/end scoped to root; provider events global."""

    def test_subagent_events_scoped_to_tree_root(self):
        m = SubagentManager()
        m.start(req("a"))
        m.start(req("b", parent_id="a"))
        aid = m._live_activation("b").activation_id
        m.settle(aid, final_text="x")
        events = m.events_for_root("lead")
        self.assertEqual([e.kind for e in events], [
            LifecycleKind.SUBAGENT_START,
            LifecycleKind.SUBAGENT_START,
            LifecycleKind.SUBAGENT_END,
        ])
        self.assertTrue(all(e.tree_root == "lead" for e in events))
        self.assertEqual(m.events_for_root("a"), ())

    def test_provider_events_are_not_tree_scoped(self):
        m = SubagentManager()
        m.register_provider(caps("cli", Capability.EXTERNAL_EXECUTION))
        m.unregister_provider("cli")
        kinds = [e.kind for e in m.events]
        self.assertIn(LifecycleKind.PROVIDER_ADDED, kinds)
        self.assertIn(LifecycleKind.PROVIDER_REMOVED, kinds)
        self.assertTrue(all(e.tree_root is None for e in m.events))
        self.assertEqual(m.events_for_root("lead"), ())


class TestAdversarialAndPurity(unittest.TestCase):
    """Fail-closed boundaries, coded errors and stdlib-only implementation."""

    def test_all_custom_errors_have_codes(self):
        for error_type in (
            CapabilityNotSupported, DeliveryUnavailable, AlreadyActive, AlreadySettled,
            NoFollowUp, InterruptDeniedError, RouteError, RouteNotAllowed,
            e3.ForkPrefixError, ImageNotAccepted, InputClosed, e3.NotFoundError,
        ):
            with self.subTest(error=error_type.__name__):
                err = error_type("boom")
                self.assertTrue(err.code)
                self.assertIn(err.code, str(err))

    def test_no_credentials_in_stored_state(self):
        m = SubagentManager()
        aid = m.start(req("child"))
        with self.assertRaises(E3ValidationError):
            m.settle(aid, final_text="x", structured={"token": "sk-abcdefghijklmnop"})
        # Structured output is refused before any message or result is stored.
        self.assertIsNone(m.activations[aid].settled_result)

    def test_module_imports_are_stdlib_only(self):
        tree = ast.parse(inspect.getsource(e3))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {
            "os", "sys", "socket", "subprocess", "time", "random", "datetime",
            "tempfile", "threading", "asyncio", "urllib", "http", "shutil", "pathlib",
        }
        self.assertFalse(imported & forbidden)

    def test_unknown_enum_values_fail_closed(self):
        with self.assertRaises(E3ValidationError):
            req("child", kind="teleport")
        with self.assertRaises(E3ValidationError):
            req("child", delivery="whisper")
        with self.assertRaises(E3ValidationError):
            req("child", spawn_mode="clone")


if __name__ == "__main__":
    unittest.main()

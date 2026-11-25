"""Production-hardening specs for the tool pipeline and bounded delegation.

Every test here targets a lifecycle/delegation property that is required in
production: centralized authorization, replay-safe approval, resource bounds,
typed failures with durable audit events, and bounded child agents.

These specs are additive -- they import only ``keel.tool_contracts`` and never
touch the live native registry.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

import keel.tool_contracts as tc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _obj(properties=None, required=(), additional=True):
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": additional,
    }


OUTPUT = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": True,
}


def _echo(args, ctx):
    return {"ok": True}


def _spec(name="echo", *, handler=_echo, input_schema=None,
          output_schema=None, permission="read", **kw):
    return tc.ToolSpec(
        name=name,
        description=f"{name} tool",
        input_schema=input_schema if input_schema is not None else _obj(
            {"a": {"type": "integer"}}, ["a"]),
        output_schema=output_schema if output_schema is not None else dict(OUTPUT),
        handler=handler,
        renderer=kw.pop("renderer", lambda args, value: "ok"),
        permission=permission,
        **kw,
    )


def _registry(*specs, policy=None):
    reg = tc.ToolRegistry()
    for spec in specs:
        reg.register(spec)
    if policy is not None:
        reg.set_policy(policy)
    return reg


def _policy(*permissions):
    return tc.PermissionPolicy({"agent": frozenset(permissions)})


def _flatten(results):
    for result in results:
        yield result
        yield from _flatten(result.child_results)


# ---------------------------------------------------------------------------
# 1. malicious arguments / resource bounds
# ---------------------------------------------------------------------------

def test_deeply_nested_args_cannot_escape_typed_pipeline():
    reg = _registry(_spec(name="deep", input_schema=_obj({}, additional=True)))
    args: dict = {}
    cursor = args
    for _ in range(5000):
        cursor["x"] = {}
        cursor = cursor["x"]
    result = tc.execute_tool(reg, "deep", args)
    assert result.ok is False
    assert result.code in {"ARGS_RESOURCE_LIMIT", "INVALID_ARGS"}
    assert "RecursionError" not in result.display
    assert "Traceback" not in result.display


def test_oversized_string_and_array_are_typed_failures():
    reg = _registry(_spec(name="bounded", input_schema=_obj({
        "text": {"type": "string"},
        "items": {"type": "array", "items": {"type": "integer"}},
    })))
    huge_text = tc.execute_tool(reg, "bounded", {"text": "x" * 200_000})
    huge_array = tc.execute_tool(reg, "bounded", {"items": list(range(20_000))})
    assert huge_text.code == "ARGS_RESOURCE_LIMIT"
    assert huge_array.code == "ARGS_RESOURCE_LIMIT"
    assert huge_text.ok is False and huge_array.ok is False


def test_const_and_enum_do_not_confuse_bool_with_integer():
    schema = _obj({
        "a": {"const": 1},
        "b": {"enum": [1, 2]},
    }, ["a", "b"])
    reg = _registry(_spec(name="typed", input_schema=schema))
    result = tc.execute_tool(reg, "typed", {"a": True, "b": False})
    assert result.code == "INVALID_ARGS"
    assert result.ok is False
    assert tc.validate_value({"const": 1}, 1) == []
    assert tc.validate_value({"const": 1}, True)


def test_non_json_args_are_typed_not_raised():
    reg = _registry(_spec())
    result = tc.execute_tool(reg, "echo", {object(): 1})
    assert result.code == "INVALID_ARGS"
    assert "object keys" in (result.durable_reason or "")


# ---------------------------------------------------------------------------
# 2. centralized authorization
# ---------------------------------------------------------------------------

def test_permission_class_is_enforced_by_central_policy():
    called = []
    reg = _registry(
        _spec(name="wipe", permission="destructive", input_schema=_obj(),
              handler=lambda a, c: called.append(1) or {"ok": True}),
        policy=tc.PermissionPolicy({"agent": frozenset({"read"})}),
    )
    result = tc.execute_tool(reg, "wipe", {})
    assert result.code == "PERMISSION_DENIED"
    assert result.ok is False
    assert called == []
    assert "destructive" not in result.display
    assert result.durable_reason is not None


def test_authorization_governs_discovery_and_execution():
    reg = _registry(
        _spec(name="allowed", permission="read", input_schema=_obj()),
        _spec(name="hidden", permission="network", input_schema=_obj()),
        policy=_policy("read"),
    )
    assert [s["name"] for s in reg.schemas()] == ["allowed"]
    assert tc.execute_tool(reg, "hidden", {}).code == "PERMISSION_DENIED"
    # Unknown agents fail closed.
    assert tc.execute_tool(reg, "allowed", {}, agent_id="stranger").code \
        == "PERMISSION_DENIED"


def test_scoped_flag_cannot_self_exempt_under_policy():
    reg = _registry(
        _spec(name="sneaky", scoped=True, permission="read",
              input_schema=_obj()),
        policy=tc.PermissionPolicy(
            {"agent": frozenset({"read"})},
            restrictions={"agent": tc.ToolRestriction.from_lists(
                deny=["sneaky"])},
        ),
    )
    assert tc.execute_tool(reg, "sneaky", {}).code == "APPROVAL_REJECTED"
    assert [s["name"] for s in reg.schemas()] == []

    trusted = _registry(
        _spec(name="sneaky", scoped=True, permission="read",
              input_schema=_obj()),
        policy=tc.PermissionPolicy(
            {"agent": frozenset({"read"})},
            restrictions={"agent": tc.ToolRestriction.from_lists(
                deny=["sneaky"])},
            trust_scoped=True,
        ),
    )
    assert tc.execute_tool(trusted, "sneaky", {}).ok is True


def test_replace_cannot_widen_permission_class():
    reg = _registry(_spec(name="read_tool", permission="read"))
    with pytest.raises(ValueError, match="permission"):
        reg.register(_spec(name="read_tool", permission="destructive"),
                     replace=True)


# ---------------------------------------------------------------------------
# 3. alternate transports
# ---------------------------------------------------------------------------

def test_ptc_proxy_cannot_bypass_policy():
    reg = _registry(_spec(name="wipe", permission="destructive",
                          input_schema=_obj()),
                    policy=_policy("read"))
    ptc = tc.PTCExecutor(reg)
    with pytest.raises(tc.PTCError) as exc:
        asyncio.run(ptc.call("wipe", {}))
    assert "PERMISSION_DENIED" in str(exc.value)
    assert ptc.model_direct_call("wipe", {}).code == "MODEL_DIRECT_CALL_DENIED"


def test_ptc_cannot_bypass_call_restriction():
    reg = _registry(_spec(name="hidden", input_schema=_obj()))
    ptc = tc.PTCExecutor(
        reg, restriction=tc.ToolRestriction.from_lists(deny=["hidden"]))
    with pytest.raises(tc.PTCError) as exc:
        asyncio.run(ptc.call("hidden", {}))
    assert "APPROVAL_REJECTED" in str(exc.value)


def test_execute_batch_honours_restriction_and_policy():
    reg = _registry(_spec(name="hidden", input_schema=_obj()))
    results = tc.execute_batch(
        reg, [tc.ToolCall("hidden", {})],
        restriction=tc.ToolRestriction.from_lists(deny=["hidden"]))
    assert len(results) == 1
    assert results[0].code == "APPROVAL_REJECTED"

    guarded = _registry(_spec(name="wipe", permission="destructive",
                              input_schema=_obj()),
                        policy=_policy("read"))
    out = tc.execute_batch(guarded, [tc.ToolCall("wipe", {})])
    assert out[0].code == "PERMISSION_DENIED"


def test_step_admission_guard_blocks_every_transport():
    reg = _registry(
        _spec(name="vision", input_schema=_obj()),
        _spec(name="text", input_schema=_obj()))
    admission = tc.StepAdmission([
        tc.ToolActivation("vision", lambda sel: sel.get("images") is True),
        tc.ToolActivation("text", lambda sel: True),
    ], reg)
    admission.attach(reg)
    admission.admit({"images": False})

    assert tc.execute_tool(reg, "vision", {}).code == "MODEL_DIRECT_CALL_DENIED"
    assert tc.execute_tool(reg, "text", {}).ok is True
    assert tc.execute_batch(reg, [tc.ToolCall("vision", {})])[0].code \
        == "MODEL_DIRECT_CALL_DENIED"
    with pytest.raises(tc.PTCError):
        asyncio.run(tc.PTCExecutor(reg).call("vision", {}))


def test_cancelled_batch_and_ptc_never_dispatch():
    called = []
    reg = _registry(_spec(
        name="side", input_schema=_obj(),
        handler=lambda a, c: called.append(1) or {"ok": True},
        concurrency=tc.ConcurrencyClass.SAFE))
    cancel = tc.CancelSignal()
    cancel.cancel()
    results = tc.execute_batch(reg, [tc.ToolCall("side", {})], cancel=cancel)
    assert all(r.code in {"ABORTED", "ABORTED_BEFORE_DISPATCH"}
               for r in results)
    ptc = tc.PTCExecutor(reg, cancel=cancel, selected=False)
    assert ptc.model_direct_call("side", {}).code in {
        "ABORTED", "ABORTED_BEFORE_DISPATCH"}
    assert called == []


# ---------------------------------------------------------------------------
# 4. approval replay
# ---------------------------------------------------------------------------

def test_approval_is_single_use_and_bound_to_args():
    reg = _registry(_spec(name="guarded"))
    reg.add_pre_hook(lambda n, s: tc.Decision.ask("needs approval"))
    responder = lambda n, s, d: tc.Decision.allow("approved")

    first = tc.execute_tool(reg, "guarded", {"a": 1},
                            approval_responder=responder)
    replay = tc.execute_tool(reg, "guarded", {"a": 1},
                             approval_responder=responder)
    fresh = tc.execute_tool(reg, "guarded", {"a": 2},
                            approval_responder=responder)

    assert first.ok is True
    assert replay.code == "APPROVAL_REPLAY_REJECTED"
    assert replay.ok is False
    assert fresh.ok is True


def test_explicit_grant_binds_agent_and_args():
    reg = _registry(_spec(name="guarded"))
    reg.add_pre_hook(lambda n, s: tc.Decision.ask("needs approval"))
    grant = tc.ApprovalGrant.issue(
        "guarded", tc.snapshot_args({"a": 1}), "agent")
    responder = lambda n, s, d: grant

    wrong_agent = tc.execute_tool(reg, "guarded", {"a": 1},
                                  agent_id="other",
                                  approval_responder=responder)
    wrong_args = tc.execute_tool(reg, "guarded", {"a": 2},
                                 approval_responder=responder)
    assert wrong_agent.code == "APPROVAL_REJECTED"
    assert wrong_args.code == "APPROVAL_REJECTED"

    assert tc.execute_tool(
        reg, "guarded", {"a": 1}, approval_responder=responder).ok is True
    replay = tc.execute_tool(reg, "guarded", {"a": 1},
                             approval_responder=responder)
    assert replay.code == "APPROVAL_REPLAY_REJECTED"


# ---------------------------------------------------------------------------
# 5. timeout, cancellation, audit/persistence
# ---------------------------------------------------------------------------

def test_timeout_is_typed_and_handler_observes_cancellation():
    observed = {}

    def waiter(args, ctx):
        while not ctx.cancel.cancelled:
            time.sleep(0.002)
        observed["cancelled"] = True
        return {"ok": True}

    reg = _registry(_spec(name="wait", input_schema=_obj(),
                          handler=waiter, timeout_s=0.05))
    result = tc.execute_tool(reg, "wait", {})
    assert result.code == "TOOL_TIMEOUT"
    assert result.timed_out is True
    assert observed.get("cancelled") is True
    assert "exceeded" not in result.display


def test_blocked_result_scrubs_context_and_keeps_audit():
    secret = "TOPSECRET_payload"

    def handler(args, ctx):
        ctx.defer_context({"note": secret})
        return {"ok": True, "secret": secret}

    reg = _registry(_spec(name="leaky", input_schema=_obj(), handler=handler))
    reg.add_post_hook(tc.dlp_block("DLP blocked the result"))
    result = tc.execute_tool(reg, "leaky", {})
    assert result.code == "APPROVAL_REJECTED"
    assert secret not in str(result.attached_context)
    assert secret not in str(result.presentation_meta)
    assert secret not in result.display
    assert result.audit  # the rejection must remain durable


def test_every_outcome_emits_exactly_one_audit_event():
    reg = _registry(_spec(name="echo"))
    tc.execute_tool(reg, "echo", {"a": 1})
    tc.execute_tool(reg, "echo", {})
    tc.execute_tool(reg, "missing", {})
    events = reg.audit_log
    assert len(events) == 3
    assert [e.code for e in events] == [None, "INVALID_ARGS", "UNKNOWN_TOOL"]
    assert all(e.name in {"echo", "missing"} for e in events)
    reg.dispose()
    assert reg.audit_log == []


# ---------------------------------------------------------------------------
# 6. bounded delegation
# ---------------------------------------------------------------------------

def test_child_cannot_gain_privileges():
    reg = _registry(
        _spec(name="read_tool", permission="read"),
        _spec(name="wipe", permission="destructive"),
    )
    parent = tc.AgentScope("root", frozenset({"read", "subagent"}))
    with pytest.raises(tc.ToolError) as exc:
        parent.child("escalated", permissions=("destructive",))
    assert exc.value.code == "PERMISSION_DENIED"

    child = parent.child("kid", permissions=("read",))
    report = tc.DelegationManager(reg).run(
        child, [tc.DelegationTask("c1", "wipe", {})])
    assert report.results[0].code == "PERMISSION_DENIED"
    assert report.results[0].ok is False


def test_recursive_delegation_cap():
    reg = _registry(_spec(name="noop", input_schema=_obj()))
    parent = tc.AgentScope(
        "root", frozenset({"read", "subagent"}),
        policy=tc.DelegationPolicy(max_depth=2))
    scope = parent
    for _ in range(2):
        scope = scope.child("level")
    with pytest.raises(tc.ToolError) as exc:
        scope.child("too-deep")
    assert exc.value.code == "DELEGATION_DEPTH_EXCEEDED"

    def nest(level):
        if level == 0:
            return None
        return lambda s, m: [tc.DelegationTask(
            "nested", "noop", {}, nested=nest(level - 1))]

    report = tc.DelegationManager(reg).run(
        parent, [tc.DelegationTask("c1", "noop", {}, nested=nest(4))])
    codes = [r.code for r in _flatten(report.results)]
    assert "DELEGATION_DEPTH_EXCEEDED" in codes


def test_concurrent_children_are_bounded():
    lock = threading.Lock()
    state = {"active": 0, "max": 0}

    def handler(args, ctx):
        with lock:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return {"ok": True}

    reg = _registry(_spec(
        name="work", input_schema=_obj(), handler=handler,
        concurrency=tc.ConcurrencyClass.SAFE))
    parent = tc.AgentScope(
        "root", frozenset({"read", "subagent"}),
        policy=tc.DelegationPolicy(max_concurrent=2, max_children=8))
    report = tc.DelegationManager(reg).run(
        parent, [tc.DelegationTask(f"c{i}", "work") for i in range(6)])
    assert len(report.results) == 6
    assert all(r.ok for r in report.results)
    assert 1 <= state["max"] <= 2


def test_child_count_cap_produces_typed_failures():
    called = []
    reg = _registry(_spec(
        name="work", input_schema=_obj(),
        handler=lambda a, c: called.append(1) or {"ok": True}))
    parent = tc.AgentScope(
        "root", frozenset({"read", "subagent"}),
        policy=tc.DelegationPolicy(max_children=2))
    report = tc.DelegationManager(reg).run(
        parent, [tc.DelegationTask(f"c{i}", "work") for i in range(5)])
    assert len(report.results) == 5
    assert sum(r.ok for r in report.results) == 2
    assert len(called) == 2
    assert [r.code for r in report.results[2:]] \
        == ["DELEGATION_LIMIT_EXCEEDED"] * 3


def test_partial_failure_aggregation_and_failure_propagation():
    def handler(args, ctx):
        if args["n"] == 2:
            raise RuntimeError("boom")
        return {"ok": True, "n": args["n"]}

    reg = _registry(_spec(
        name="work", input_schema=_obj({"n": {"type": "integer"}}, ["n"]),
        handler=handler))
    parent = tc.AgentScope("root", frozenset({"read", "subagent"}))
    report = tc.DelegationManager(reg).run(
        parent, [tc.DelegationTask(f"c{i}", "work", {"n": i})
                 for i in range(3)])
    assert report.ok is False
    assert [r.ok for r in report.results] == [True, True, False]
    assert len(report.failures) == 1
    assert report.failures[0].code == "TOOL_EXECUTION_ERROR"
    assert "boom" not in report.failures[0].display
    assert "boom" in (report.failures[0].durable_reason or "")


def test_checkpoint_recovery_does_not_reexecute():
    calls = []

    def handler(args, ctx):
        calls.append(args["n"])
        return {"ok": True, "n": args["n"]}

    reg = _registry(_spec(
        name="work", input_schema=_obj({"n": {"type": "integer"}}, ["n"]),
        handler=handler))
    mgr = tc.DelegationManager(reg)
    parent = tc.AgentScope("root", frozenset({"read", "subagent"}))
    tasks = [tc.DelegationTask(f"c{i}", "work", {"n": i}) for i in range(3)]

    first = mgr.run(parent, tasks, checkpoint_id="cp-1")
    second = mgr.run(parent, tasks, checkpoint_id="cp-1")
    assert sorted(calls) == [0, 1, 2]  # concurrency makes dispatch order free
    assert second.ok is True
    assert [r.value for r in second.results] \
        == [r.value for r in first.results]


def test_resume_retries_only_failed_children():
    attempts = []

    def handler(args, ctx):
        n = args["n"]
        attempts.append(n)
        if n == 1 and attempts.count(1) == 1:
            raise RuntimeError("flaky child")
        return {"ok": True, "n": n}

    reg = _registry(_spec(
        name="work", input_schema=_obj({"n": {"type": "integer"}}, ["n"]),
        handler=handler))
    mgr = tc.DelegationManager(reg)
    parent = tc.AgentScope("root", frozenset({"read", "subagent"}))
    tasks = [tc.DelegationTask(f"c{i}", "work", {"n": i}) for i in range(3)]

    first = mgr.run(parent, tasks, checkpoint_id="cp-2")
    assert first.ok is False
    resumed = mgr.run(parent, tasks, checkpoint_id="cp-2",
                      resume_failed=True, force=True)
    assert resumed.ok is True
    assert attempts.count(0) == 1
    assert attempts.count(1) == 2
    assert attempts.count(2) == 1

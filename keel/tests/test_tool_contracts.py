"""Permanent contract-regression specs for Addendum 7 tool pipelines.

One or more tests per named contract in ``metadata.tool_contracts`` (E1.1-E1.21,
E2.1-E2.5, E4.x).  These specs are additive: they import only
``keel.tool_contracts`` and never mutate the live tool registry.
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

def _obj(properties=None, required=(), additional=False):
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": additional,
    }


OUTPUT = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}, "sum": {"type": "integer"}},
    "required": ["ok"],
    "additionalProperties": True,
}


def _echo(args, ctx):
    return {"ok": True, "echo": dict(args)}


def _render(args, value):
    return f"ok={value.get('ok')}"


def _spec(name="echo", *, handler=_echo, renderer=_render,
          input_schema=None, output_schema=None, **kw):
    return tc.ToolSpec(
        name=name,
        description=f"{name} tool",
        input_schema=input_schema if input_schema is not None else _obj(
            {"a": {"type": "integer"}}, ["a"]),
        output_schema=output_schema if output_schema is not None else dict(OUTPUT),
        handler=handler,
        renderer=renderer,
        **kw,
    )


def _registry(*specs):
    reg = tc.ToolRegistry()
    for spec in specs:
        reg.register(spec)
    return reg


# ---------------------------------------------------------------------------
# 1. canonical output + pure renderer (E1.1)
# ---------------------------------------------------------------------------

def test_contract1_output_schema_mandatory_at_registration():
    reg = tc.ToolRegistry()
    spec = tc.ToolSpec(
        name="no_output", description="d",
        input_schema=_obj(), output_schema={}, handler=_echo, renderer=_render)
    with pytest.raises(ValueError, match="output_schema"):
        reg.register(spec)


def test_contract1_handler_returns_value_renderer_builds_display():
    reg = _registry(_spec())
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.ok is True
    assert result.value == {"ok": True, "echo": {"a": 1}}
    assert result.display == "ok=True"
    # Callers never parse prose for ids: the value is a lossless JSON object.
    assert isinstance(result.value, dict)


def test_contract1_renderer_is_pure():
    seen = []
    def renderer(args, value):
        seen.append((args, value))
        return "same"
    reg = _registry(_spec(renderer=renderer))
    first = tc.execute_tool(reg, "echo", {"a": 1})
    second = tc.execute_tool(reg, "echo", {"a": 1})
    assert first.display == second.display == "same"
    assert seen[0] == seen[1]


# ---------------------------------------------------------------------------
# 2. model-facing schema allowlist (E1.2)
# ---------------------------------------------------------------------------

def test_contract2_schema_projects_only_name_description_parameters():
    reg = _registry(_spec(timeout_s=0.5,
                          concurrency=tc.ConcurrencyClass.SAFE,
                          metadata={"secret": "internal"}))
    schemas = reg.schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert set(schema) == {"name", "description", "input_schema"}
    assert "output_schema" not in schema
    assert "handler" not in schema
    assert "renderer" not in schema
    assert "timeout_s" not in schema
    assert "concurrency" not in schema
    assert "metadata" not in schema


def test_contract2_schemas_are_deep_copies():
    reg = _registry(_spec())
    schemas = reg.schemas()
    schemas[0]["input_schema"]["properties"]["a"]["type"] = "mutated"
    assert reg.get("echo").input_schema["properties"]["a"]["type"] == "integer"


# ---------------------------------------------------------------------------
# 3. one schema vocabulary + unsupported keyword rejection (E1.3)
# ---------------------------------------------------------------------------

def test_contract3_unsupported_keyword_rejected_not_ignored():
    reg = tc.ToolRegistry()
    bad = _obj({"a": {"type": "integer", "$ref": "#/defs/A"}}, ["a"])
    with pytest.raises(tc.SchemaError, match="unsupported schema keyword"):
        reg.register(_spec(input_schema=bad))


def test_contract3_internal_metadata_keyword_rejected():
    reg = tc.ToolRegistry()
    bad = _obj({"a": {"type": "integer", "_handler_callback": True}}, ["a"])
    with pytest.raises(tc.SchemaError, match="unsupported schema keyword"):
        reg.register(_spec(input_schema=bad))


def test_contract3_object_without_explicit_additional_properties_rejected():
    reg = tc.ToolRegistry()
    bad = {"type": "object", "properties": {"a": {"type": "integer"}}}
    with pytest.raises(tc.SchemaError, match="additionalProperties"):
        reg.register(_spec(input_schema=bad))


def test_contract3_oneof_is_exact_one():
    schema = {
        "oneOf": [
            _obj({"a": {"type": "integer"}}, ["a"]),
            _obj({"b": {"type": "string"}}, ["b"]),
        ]
    }
    assert tc.validate_value(schema, {"a": 1}) == []
    assert tc.validate_value(schema, {"b": "x"}) == []
    # Matches both branches -> invalid.
    both = tc.validate_value(schema, {"a": 1, "b": "x"})
    assert any("exactly one" in e for e in both)
    # Matches neither -> invalid.
    none = tc.validate_value(schema, {"c": 2})
    assert any("exactly one" in e for e in none)


def test_contract3_enum_const_and_inferred_type():
    const = {"const": 7}
    assert tc.infer_schema_type(const) == "integer"
    assert tc.validate_value(const, 7) == []
    assert tc.validate_value(const, 8)
    enum = {"enum": ["a", "b"]}
    assert tc.infer_schema_type(enum) == "string"
    assert tc.validate_value(enum, "a") == []
    assert tc.validate_value(enum, "c")


def test_contract3_numeric_types_follow_json_schema_widening():
    """M1: integer satisfies number; integral float satisfies integer."""
    assert tc.validate_value({"type": "number"}, 5) == []
    assert tc.validate_value({"type": "integer"}, 5.0) == []
    assert tc.validate_value({"type": "integer"}, 5.5)  # fractional float rejected
    assert tc.validate_value({"type": "number"}, True)  # bool is not a number
    assert tc.validate_value({"type": "integer"}, "5")  # string is not a number

    number_reg = _registry(_spec(input_schema=_obj({"a": {"type": "number"}}, ["a"])))
    assert tc.execute_tool(number_reg, "echo", {"a": 5}).ok is True
    integer_reg = _registry(_spec(input_schema=_obj({"a": {"type": "integer"}}, ["a"])))
    assert tc.execute_tool(integer_reg, "echo", {"a": 5.0}).ok is True


def test_contract3_invalid_args_and_invalid_output_codes():
    reg = _registry(_spec())
    assert tc.execute_tool(reg, "echo", {}).code == "INVALID_ARGS"

    bad_handler = lambda args, ctx: {"ok": "not-a-boolean"}
    reg2 = _registry(_spec(name="bad", handler=bad_handler))
    assert tc.execute_tool(reg2, "bad", {"a": 1}).code == "INVALID_TOOL_OUTPUT"


# ---------------------------------------------------------------------------
# 4. argument snapshotting + immutability (E1.4)
# ---------------------------------------------------------------------------

def test_contract4_args_deep_copied_before_policy_runs():
    captured = {}
    def pre_hook(name, snapshot):
        captured["frozen"] = snapshot.frozen
        captured["canonical"] = snapshot.canonical
        return tc.Decision.allow()

    reg = _registry(_spec())
    reg.add_pre_hook(pre_hook)
    original = {"a": 1}
    tc.execute_tool(reg, "echo", original)
    original["a"] = 999  # caller mutation after dispatch
    assert captured["frozen"]["a"] == 1
    assert captured["canonical"] == '{"a":1}'


def test_contract4_args_frozen_for_handler_and_policy():
    from types import MappingProxyType

    def handler(args, ctx):
        assert isinstance(args, MappingProxyType)
        assert isinstance(args["nested"], tuple)
        args["nested"] = (3,)  # type: ignore[index] - must be rejected
        return {"ok": True}

    reg = _registry(_spec(
        name="frozen", handler=handler,
        input_schema=_obj({"nested": {"type": "array", "items": {"type": "integer"}}},
                          ["nested"])))
    result = tc.execute_tool(reg, "frozen", {"nested": [1, 2]})
    # The attempted rewrite is raised inside the handler and surfaces as a
    # typed failure, never as a mutated argument.
    assert result.code == "TOOL_EXECUTION_ERROR"


def test_contract4_policy_hook_cannot_rewrite_args():
    def hostile_hook(name, snapshot):
        with pytest.raises(TypeError):
            snapshot.frozen["a"] = 42  # type: ignore[index]
        return tc.Decision.allow()
    reg = _registry(_spec())
    reg.add_pre_hook(hostile_hook)
    assert tc.execute_tool(reg, "echo", {"a": 1}).ok is True


# ---------------------------------------------------------------------------
# 5. pre-execute decision model (E1.5)
# ---------------------------------------------------------------------------

def test_contract5_allow_proceeds_deny_cancel_block():
    reg = _registry(_spec())
    assert tc.execute_tool(reg, "echo", {"a": 1}).ok is True

    reg_deny = _registry(_spec())
    reg_deny.add_pre_hook(lambda n, s: tc.Decision.deny("nope"))
    denied = tc.execute_tool(reg_deny, "echo", {"a": 1})
    assert denied.code == "APPROVAL_REJECTED"
    assert "nope" not in denied.display  # raw reason never in model content

    reg_cancel = _registry(_spec())
    reg_cancel.add_pre_hook(lambda n, s: tc.Decision.cancel("user cancelled"))
    cancelled = tc.execute_tool(reg_cancel, "echo", {"a": 1})
    assert cancelled.code == "ABORTED"


def test_contract5_ask_with_approval_responder():
    reg = _registry(_spec())
    reg.add_pre_hook(lambda n, s: tc.Decision.ask("needs approval"))
    approved = tc.execute_tool(
        reg, "echo", {"a": 1},
        approval_responder=lambda n, s, d: tc.Decision.allow("approved"))
    assert approved.ok is True
    rejected = tc.execute_tool(
        reg, "echo", {"a": 1},
        approval_responder=lambda n, s, d: tc.Decision.deny("refused"))
    assert rejected.code == "APPROVAL_REJECTED"
    cancelled = tc.execute_tool(
        reg, "echo", {"a": 1},
        approval_responder=lambda n, s, d: tc.Decision.cancel("user cancelled prompt"))
    assert cancelled.code == "APPROVAL_CANCELLED"


def test_contract5_missing_approval_channel_and_agentless_are_denials():
    reg = _registry(_spec())
    reg.add_pre_hook(lambda n, s: tc.Decision.ask("needs approval"))
    unavailable = tc.execute_tool(reg, "echo", {"a": 1})
    assert unavailable.code == "APPROVAL_UNAVAILABLE"

    agentless = tc.execute_tool(reg, "echo", {"a": 1}, agent_id=None)
    assert agentless.code == "TOOL_CONTEXT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 6. monotonic guards (E1.6)
# ---------------------------------------------------------------------------

def test_contract6_guard_cannot_turn_deny_into_allow():
    reg = _registry(_spec())
    reg.add_pre_hook(lambda n, s: tc.Decision.deny("hard deny"))
    reg.add_guard(lambda n, s, d: tc.Decision.allow("trying to override"))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.code == "APPROVAL_REJECTED"


def test_contract6_guard_order_independent_and_can_tighten():
    deny = tc.Decision.deny("deny")
    allow = tc.Decision.allow("allow")
    assert tc.combine_decisions(deny, allow) is deny
    assert tc.combine_decisions(allow, deny) is deny

    reg = _registry(_spec())
    reg.add_guard(lambda n, s, d: tc.Decision.deny("guard veto"))
    assert tc.execute_tool(reg, "echo", {"a": 1}).code == "APPROVAL_REJECTED"


# ---------------------------------------------------------------------------
# 7. post-execute decisions: content vs value / DLP (E1.7)
# ---------------------------------------------------------------------------

def test_contract7_replace_content_is_presentation_only():
    reg = _registry(_spec())
    reg.add_post_hook(lambda n, s, r: tc.PostDecision.replace_content("pretty"))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.display == "pretty"
    assert result.value == {"ok": True, "echo": {"a": 1}}  # value survives


def test_contract7_replace_value_protects_actual_value():
    reg = _registry(_spec())
    reg.add_post_hook(tc.dlp_replace_value("[REDACTED]"))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.value == "[REDACTED]"
    assert "[REDACTED]" in result.display
    assert "echo" not in str(result.value)


def test_contract7_replace_value_scrubs_every_result_surface():
    """H1 regression: a DLP replace must not leave pre-DLP bytes in any field."""
    secret = "SECRET_VALUE_here"

    def read_file(args, ctx):
        return {"ok": True, "path": "x", "offset": 1, "lines": [secret],
                "total_lines": None, "language": None}

    reg = _registry(_spec(
        name="read_file", handler=read_file, input_schema=_obj(),
        renderer=lambda args, value: f"[tool result: {value}]"))
    reg.add_post_hook(tc.dlp_replace_value("[REDACTED]"))
    result = tc.execute_tool(reg, "read_file", {})

    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for key, value in node.items():
                yield str(key)
                yield from strings(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                yield from strings(value)

    # 'renderer' is a callable, not a persisted data surface.
    for field in ("value", "display", "presentation_meta", "attached_context",
                  "audit", "durable_reason", "code"):
        assert all(secret not in s for s in strings(getattr(result, field))), field
    assert result.value == "[REDACTED]"
    assert result.presentation_meta.get("fields", {}).get("lines") != [secret]


def test_contract7_replace_value_discards_pre_dlp_attached_context():
    """H1 regression: deferred/injected context is also a durable surface."""
    secret = "SECRET_IN_DEFERRED_CONTEXT"

    def handler(args, ctx):
        ctx.defer_context({"note": secret})
        return {"ok": True, "echo": secret}

    reg = _registry(_spec(name="ctx", handler=handler, input_schema=_obj()))
    reg.add_post_hook(tc.dlp_replace_value("[REDACTED]"))
    result = tc.execute_tool(reg, "ctx", {})
    assert result.attached_context == []
    assert secret not in str(result.attached_context)
    assert secret not in str(result.presentation_meta)


def test_contract7_block_hides_value_and_stays_typed():
    reg = _registry(_spec())
    reg.add_post_hook(tc.dlp_block("DLP: secret detected"))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.ok is False
    assert result.value is None
    assert result.code == "APPROVAL_REJECTED"
    assert "secret" not in result.display
    assert result.durable_reason == "DLP: secret detected"


def test_contract7_content_and_value_are_mutually_exclusive():
    with pytest.raises(ValueError, match="never both|value|content"):
        tc.PostDecision(
            tc.PostAction.REPLACE_CONTENT,
            content="visible", value="[REDACTED]")
    with pytest.raises(ValueError):
        tc.PostDecision(
            tc.PostAction.REPLACE_VALUE, content="visible", value=[1])


def test_contract7_attach_context_appends_after_result():
    reg = _registry(_spec())
    reg.add_post_hook(lambda n, s, r: tc.PostDecision.attach_context({"hint": "x"}))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert result.attached_context == [{"hint": "x"}]


# ---------------------------------------------------------------------------
# 8. around-dispatch, timeout, cancellation propagation (E1.8/E1.9/E1.18)
# ---------------------------------------------------------------------------

def _waiter(args, ctx):
    while not ctx.cancel.cancelled:
        time.sleep(0.005)
    return {"ok": True}


def test_contract8_caller_cancel_propagates_through_wrapper():
    reg = _registry(_spec(
        name="wait", handler=_waiter,
        input_schema=_obj(), output_schema=OUTPUT))
    # Wrapper tries to replace the signal with a fresh, never-cancelled one.
    reg.add_wrapper(lambda dispatch, signal: (dispatch, tc.CancelSignal()))
    caller = tc.CancelSignal()
    caller.cancel()
    result = tc.execute_tool(reg, "wait", {}, cancel=caller)
    assert result.code == "ABORTED"


def test_contract8_pre_cancelled_call_never_dispatches_handler():
    """H2 regression: an already-cancelled call must not run side effects."""
    called = []

    def side_effect(args, ctx):
        called.append(True)
        return {"ok": True}

    reg = _registry(_spec(name="side", handler=side_effect, input_schema=_obj()))
    cancel = tc.CancelSignal()
    cancel.cancel()
    result = tc.execute_tool(reg, "side", {}, cancel=cancel)
    assert called == []
    assert result.ok is False
    assert result.code in {"ABORTED", "ABORTED_BEFORE_DISPATCH"}


def test_contract8_pre_cancelled_wrapper_signal_never_dispatches():
    """H2 regression: a wrapper-supplied signal is part of the pre-dispatch gate."""
    called = []

    def side_effect(args, ctx):
        called.append(True)
        return {"ok": True}

    reg = _registry(_spec(name="side", handler=side_effect, input_schema=_obj()))
    extra = tc.CancelSignal()
    extra.cancel()
    reg.add_wrapper(lambda dispatch, signal: (dispatch, extra))
    result = tc.execute_tool(reg, "side", {})
    assert called == []
    assert result.ok is False
    assert result.code in {"ABORTED", "ABORTED_BEFORE_DISPATCH"}


def test_contract8_cooperative_timeout_and_timed_out_flag():
    reg = _registry(_spec(name="wait", handler=_waiter,
                          input_schema=_obj(), timeout_s=0.05))
    result = tc.execute_tool(reg, "wait", {})
    assert result.code == "TOOL_TIMEOUT"
    assert result.timed_out is True


def test_contract8_wrapper_can_add_cancellation_signal():
    reg = _registry(_spec(name="wait", handler=_waiter, input_schema=_obj()))
    extra = tc.CancelSignal()
    reg.add_wrapper(lambda dispatch, signal: (dispatch, extra))
    thread = threading.Thread(
        target=lambda: (time.sleep(0.03), extra.cancel()), daemon=True)
    thread.start()
    result = tc.execute_tool(reg, "wait", {})
    assert result.code == "ABORTED"
    thread.join()


def test_contract8_timeout_not_exposed_to_model():
    reg = _registry(_spec(timeout_s=0.5))
    assert "timeout_s" not in reg.schemas()[0]


# ---------------------------------------------------------------------------
# 9 & 10. concurrency classification, barriers, ordering, cleanup (E1.10/E1.11)
# ---------------------------------------------------------------------------

def test_contract9_only_explicit_true_opts_in():
    safe = _spec(name="safe", concurrency=tc.ConcurrencyClass.SAFE)
    exclusive = _spec(name="exclusive")
    assert tc.classify(safe, {}) is True
    assert tc.classify(exclusive, {}) is False


def test_contract9_classifier_exception_or_nonbool_is_exclusive():
    bad = _spec(name="bad", concurrency_safe=lambda a: (_ for _ in ()).throw(RuntimeError()))
    nonbool = _spec(name="nonbool", concurrency_safe=lambda a: "yes")
    assert tc.classify(bad, {}) is False
    assert tc.classify(nonbool, {}) is False
    good = _spec(name="good", concurrency_safe=lambda a: a.get("safe") is True)
    assert tc.classify(good, {"safe": True}) is True
    assert tc.classify(good, {"safe": False}) is False


def test_contract9_bounded_parallel_and_deterministic_order():
    lock = threading.Lock()
    state = {"active": 0, "max": 0}

    def handler(args, ctx):
        with lock:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return {"ok": True, "which": args["a"]}

    reg = _registry(_spec(name="par", handler=handler,
                          concurrency=tc.ConcurrencyClass.SAFE))
    calls = [tc.ToolCall("par", {"a": i}) for i in range(8)]
    results = tc.execute_batch(reg, calls, max_parallel=2)
    assert [r.value["which"] for r in results] == list(range(8))
    assert state["max"] <= 2
    assert state["max"] >= 1


def test_contract9_exclusive_barrier_drains_safe_work():
    lock = threading.Lock()
    state = {"active": 0, "violation": False}

    def safe_handler(args, ctx):
        with lock:
            state["active"] += 1
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return {"ok": True}

    def exclusive_handler(args, ctx):
        with lock:
            if state["active"] != 0:
                state["violation"] = True
        return {"ok": True}

    reg = _registry(
        _spec(name="safe", handler=safe_handler, input_schema=_obj(),
              concurrency=tc.ConcurrencyClass.SAFE),
        _spec(name="excl", handler=exclusive_handler, input_schema=_obj(),
              concurrency=tc.ConcurrencyClass.EXCLUSIVE),
    )
    calls = [
        tc.ToolCall("safe", {}), tc.ToolCall("safe", {}),
        tc.ToolCall("excl", {}),
        tc.ToolCall("safe", {}),
    ]
    results = tc.execute_batch(reg, calls, max_parallel=4)
    assert len(results) == 4
    assert all(r.ok for r in results)
    assert state["violation"] is False


def test_contract10_one_outcome_per_call_including_skipped():
    reg = _registry(_spec())
    cancel = tc.CancelSignal()
    cancel.cancel()
    calls = [tc.ToolCall("echo", {"a": i}) for i in range(4)]
    results = tc.execute_batch(reg, calls, cancel=cancel)
    assert len(results) == 4
    assert all(r.code == "ABORTED_BEFORE_DISPATCH" for r in results)


def test_contract10_internal_failure_drains_then_typed_batch_error(monkeypatch):
    reg = _registry(
        _spec(name="a"), _spec(name="b"), _spec(name="boom"))

    def fake_execute(registry, name, args, **kw):
        if name == "boom":
            raise RuntimeError("injected infra failure")
        return tc.success_result(name, {"ok": True}, "ok")

    monkeypatch.setattr(tc, "execute_tool", fake_execute)
    calls = [tc.ToolCall("a", {}), tc.ToolCall("b", {}), tc.ToolCall("boom", {})]
    with pytest.raises(tc.ToolBatchExecutionError) as exc:
        tc.execute_batch(reg, calls)
    assert exc.value.code == "BATCH_EXECUTION_ERROR"
    assert any(r.name == "a" for r in exc.value.outcomes)
    assert any(r.name == "b" for r in exc.value.outcomes)


def test_contract10_dispatched_baseexception_failure_is_not_reported_as_skipped(monkeypatch):
    """M2: a dispatched safe call that raises BaseException is not 'skipped'."""
    real_execute = tc.execute_tool

    def fake_execute(registry, name, args, **kw):
        if name == "boom":
            raise KeyboardInterrupt("injected handler interrupt")
        return real_execute(registry, name, args, **kw)

    monkeypatch.setattr(tc, "execute_tool", fake_execute)
    reg = _registry(
        _spec(name="ok", input_schema=_obj(), concurrency=tc.ConcurrencyClass.SAFE),
        _spec(name="boom", input_schema=_obj(), concurrency=tc.ConcurrencyClass.SAFE),
    )
    calls = [tc.ToolCall("ok", {}), tc.ToolCall("boom", {})]
    with pytest.raises(tc.ToolBatchExecutionError) as exc:
        tc.execute_batch(reg, calls, max_parallel=4)
    by_name = {r.name: r for r in exc.value.outcomes}
    assert set(by_name) == {"ok", "boom"}
    assert by_name["ok"].ok is True
    assert by_name["boom"].code == "TOOL_EXECUTION_ERROR"
    assert all(r.code != "ABORTED_BEFORE_DISPATCH" for r in exc.value.outcomes)


# ---------------------------------------------------------------------------
# 11. per-agent restriction intersection (E1.12)
# ---------------------------------------------------------------------------

def test_contract11_deny_only_admits_later_tools_allow_list_excludes():
    deny_only = tc.ToolRestriction.from_lists(deny=["bad"])
    assert deny_only.admits("later_tool") is True
    assert deny_only.admits("bad") is False

    allow_list = tc.ToolRestriction.from_lists(allow=["read"])
    assert allow_list.admits("read") is True
    assert allow_list.admits("later_tool") is False


def test_contract11_intersection_and_scoped_exempt():
    first = tc.ToolRestriction.from_lists(allow=["a", "b"], deny=["b"])
    second = tc.ToolRestriction.from_lists(allow=["b", "c"], scoped_exempt=["s"])
    combined = tc.intersect_restrictions(first, second)
    assert combined.admits("b") is False  # denied by first
    assert combined.admits("a") is False  # not in second's allow list
    assert combined.admits("s") is True   # scoped registration stays exempt


def test_contract11_declaration_and_execution_use_same_admission_decision():
    reg = _registry(
        _spec(name="visible"),
        _spec(name="hidden"),
        _spec(name="scoped", scoped=True),
    )
    restriction = tc.ToolRestriction.from_lists(allow=["visible"])
    declared = {s["name"] for s in reg.schemas(restriction=restriction)}
    assert declared == {"visible", "scoped"}
    # A tool hidden from the declaration cannot be invoked directly.
    hidden = tc.execute_tool(reg, "hidden", {"a": 1}, restriction=restriction)
    assert hidden.code == "APPROVAL_REJECTED"
    # The scoped registration stays exempt in both declaration and execution.
    assert tc.execute_tool(
        reg, "scoped", {"a": 1}, restriction=restriction).ok is True


# ---------------------------------------------------------------------------
# 12. conditional activation (E1.13)
# ---------------------------------------------------------------------------

def test_contract12_conditional_activation_governs_declarations_and_calls():
    reg = _registry(_spec(name="vision"), _spec(name="text"))
    admission = tc.StepAdmission([
        tc.ToolActivation("vision", lambda sel: sel.get("images", False)),
        tc.ToolActivation("text", lambda sel: True),
    ], reg)
    admitted = admission.admit({"images": False})
    assert admitted == frozenset({"text"})
    assert [s["name"] for s in admission.declarations()] == ["text"]
    admission.enforce("text")
    with pytest.raises(tc.ToolError):
        admission.enforce("vision")
    # Late results cannot restore removed tools after disposal.
    admission.dispose()
    with pytest.raises(tc.ToolError):
        admission.enforce("text")


# ---------------------------------------------------------------------------
# 13 & 14. stable error codes + typed failures (E1.14/E1.15)
# ---------------------------------------------------------------------------

def test_contract13_all_mandatory_codes_are_stable():
    available = {code.value for code in tc.ToolErrorCode}
    assert tc.MANDATORY_ERROR_CODES <= available
    err = tc.ToolError("INVALID_ARGS", "echo", reason="secret detail")
    assert err.model_facing == {"name": "echo", "code": "INVALID_ARGS"}
    assert err.to_dict()["reason"] == "secret detail"


def test_contract13_raw_reason_never_in_model_facing_content():
    reg = _registry(_spec())
    reg.add_pre_hook(lambda n, s: tc.Decision.deny("super-secret reason"))
    result = tc.execute_tool(reg, "echo", {"a": 1})
    assert "super-secret" not in result.model_content()
    assert "super-secret" in (result.durable_reason or "")
    assert result.error_info == {"name": "echo", "code": "APPROVAL_REJECTED"}


def test_contract14_expected_failure_is_typed_domain_value_is_not_exception():
    def nonzero_exit(args, ctx):
        return {"ok": True, "exit_code": 2}  # a domain value, not an exception
    reg = _registry(_spec(name="shell", handler=nonzero_exit, input_schema=_obj()))
    result = tc.execute_tool(reg, "shell", {})
    assert result.ok is True
    assert result.value["exit_code"] == 2

    def raise_typed(args, ctx):
        raise tc.ToolError("INVALID_ARGS", "shell", reason="bad flag")
    reg2 = _registry(_spec(name="bad", handler=raise_typed, input_schema=_obj()))
    failure = tc.execute_tool(reg2, "bad", {})
    assert failure.ok is False
    assert failure.code == "INVALID_ARGS"


# ---------------------------------------------------------------------------
# 15. turn completion + deferred context (E1.16)
# ---------------------------------------------------------------------------

def test_contract15_conclude_turn_and_defer_context():
    def handler(args, ctx):
        ctx.conclude_turn()
        ctx.defer_context({"note": "after result"})
        return {"ok": True}
    reg = _registry(_spec(name="finisher", handler=handler, input_schema=_obj()))
    result = tc.execute_tool(reg, "finisher", {})
    assert result.conclude_turn is True
    assert result.attached_context == [{"note": "after result"}]


def test_contract15_composite_forwards_only_authoritative_success():
    ok = tc.success_result("a", None, "", conclude_turn=True)
    fail = tc.failure_result("b", "INVALID_ARGS")
    assert tc.forward_conclude_turn([ok]) is True
    assert tc.forward_conclude_turn([ok, fail]) is False
    assert tc.forward_conclude_turn([]) is False


# ---------------------------------------------------------------------------
# 16. typed source kind for injected context (E1.17)
# ---------------------------------------------------------------------------

def test_contract16_typed_injection_admitted_and_untyped_rejected():
    msg = tc.InjectedMessage(tc.SourceKind.AGENT_MESSAGE, "hello")
    assert tc.admit_injection(msg) is msg
    with pytest.raises(tc.ToolError) as exc:
        tc.admit_injection({"text": "old untyped wrapper"})
    assert exc.value.code == "INJECTION_REJECTED"


def test_contract16_inject_goes_through_typed_admission():
    def handler(args, ctx):
        ctx.inject(tc.InjectedMessage(tc.SourceKind.SUBAGENT_SETTLED, "child done"))
        return {"ok": True}
    reg = _registry(_spec(name="injector", handler=handler, input_schema=_obj()))
    result = tc.execute_tool(reg, "injector", {})
    assert result.attached_context[0]["kind"] == "subagent-settled"


# ---------------------------------------------------------------------------
# 17. long-running background lifecycle (E1.18)
# ---------------------------------------------------------------------------

def test_contract17_background_handle_and_job_lifecycle():
    manager = tc.JobManager()
    handle = manager.start(lambda signal: 42)
    assert handle.kind == "background"
    assert handle.job_id
    job = manager.get(handle.job_id)
    assert job.output_source() == f"background:{handle.job_id}"
    assert job.done() == 42
    manager.dispose()


def test_contract17_call_cancel_does_not_kill_published_work():
    manager = tc.JobManager()
    started = threading.Event()

    def work(signal):
        started.set()
        while not signal.cancelled:
            time.sleep(0.005)
        return "cleaned-up"

    call_cancel = tc.CancelSignal()
    call_cancel.cancel()
    handle, returned = tc.call_cancel_stops_waiting_not_work(
        manager, call_cancel, work)
    assert returned is None  # call stopped waiting
    job = manager.get(handle.job_id)
    assert started.wait(1.0) is True
    assert job.settled is False  # published work still alive
    manager.job_kill(handle.job_id)
    assert job.done() == "cleaned-up"  # non-rejecting done after cleanup
    manager.dispose()


# ---------------------------------------------------------------------------
# 18. programmatic tool-call mode (E1.19/E1.20/E1.21)
# ---------------------------------------------------------------------------

def test_contract18_run_code_is_reserved():
    reg = tc.ToolRegistry()
    with pytest.raises(ValueError, match="reserved"):
        reg.register(_spec(name="run_code"))


def test_contract18_programmatic_call_reenters_pipeline():
    def add(args, ctx):
        return {"ok": True, "sum": args["a"] + args["b"]}
    reg = _registry(_spec(
        name="add", handler=add,
        input_schema=_obj({"a": {"type": "integer"}, "b": {"type": "integer"}},
                          ["a", "b"])))
    ptc = tc.PTCExecutor(reg)

    async def run():
        return await ptc.tools.add({"a": 2, "b": 3})

    value = asyncio.run(run())
    assert value == {"ok": True, "sum": 5}


def test_contract18_failure_rejects_with_limited_error():
    ptc = tc.PTCExecutor(_registry())
    with pytest.raises(tc.PTCError) as exc:
        asyncio.run(ptc.call("missing", {}))
    assert set(vars(exc.value)) == {"name", "tool_name", "message"}


def test_contract18_model_direct_denied_while_ptc_selected():
    reg = _registry(_spec())
    ptc = tc.PTCExecutor(reg, selected=True)
    result = ptc.model_direct_call("echo", {"a": 1})
    assert result.code == "MODEL_DIRECT_CALL_DENIED"
    ptc.selected = False
    assert ptc.model_direct_call("echo", {"a": 1}).ok is True


def test_contract18_dispatch_log_minimal_and_prompt_sections_disposed():
    reg = _registry(_spec())
    ptc = tc.PTCExecutor(reg)
    ptc.register_prompt_section("guidance")
    asyncio.run(ptc.call("echo", {"a": 1}))
    start_event = ptc.dispatch_log.events[0]
    assert set(start_event) == {"event", "name", "args"}
    assert "schema" not in start_event and "description" not in start_event
    copy = ptc.dispatch_log.durable_log_copy(tc.success_result("echo", None, "x" * 900))
    assert len(copy["display"]) <= 513
    ptc.dispose()
    assert ptc.prompt_sections == []


# ---------------------------------------------------------------------------
# 19. UI presentation purity + card contract (E2.1-E2.5)
# ---------------------------------------------------------------------------

def test_contract19_presenters_are_pure_and_never_crash():
    card1 = tc.present_result("run_shell", {"command": "ls"},
                              {"exit_code": 0, "output": "a"})
    card2 = tc.present_result("run_shell", {"command": "ls"},
                              {"exit_code": 0, "output": "a"})
    assert card1 == card2
    # Malformed / old args fall back to a generic card, never raise.
    generic = tc.present_result("anything", None, None)
    assert generic.kind == tc.CardKind.GENERIC
    assert generic.status == "completed"
    assert tc.present_call("anything", object()).kind == tc.CardKind.GENERIC


def test_contract19_card_kinds_and_partial_result_flags():
    terminal = tc.present_result("run_shell", {"command": "ls"},
                                 {"exit_code": 1, "output": "x", "signal": "SIGTERM"})
    assert terminal.kind == tc.CardKind.TERMINAL
    assert terminal.fields["exit_code"] == 1
    assert terminal.fields["signal"] == "SIGTERM"

    search = tc.present_result("grep", {"pattern": "x"},
                               {"matches": [1], "truncated": True, "total": 99})
    assert search.kind == tc.CardKind.SEARCH
    assert search.fields["truncated"] is True
    assert search.fields["total"] == 99  # partial never shown as complete

    read = tc.present_result("read_file", {}, {"offset": 1, "total_lines": 10})
    assert read.kind == tc.CardKind.READ
    assert read.fields["offset"] == 1


def test_contract19_presentation_meta_stored_without_canonical_value():
    meta = tc.presentation_meta(
        "grep", {}, {"matches": [1], "truncated": False, "total": 1})
    assert meta["card_kind"] == "search"
    assert "matches" in meta["fields"]
    assert meta["fields"]["truncated"] is False


def test_contract19_ui_formatting_stays_out_of_model_content():
    def renderer(args, value):
        return "lines=3"  # pure model-facing text: no fences/relativized paths
    reg = _registry(_spec(name="read_file", renderer=renderer))
    result = tc.execute_tool(reg, "read_file", {"a": 1})
    assert "```" not in result.display
    assert "echo" not in result.display  # UI/card facts stay out of model content
    assert "card_kind" in result.presentation_meta
    assert "tool" in result.presentation_meta


# ---------------------------------------------------------------------------
# 20. verification: disposal, conformance, byte compare, fuzz (E4.x/V24-V28)
# ---------------------------------------------------------------------------

def test_contract20_registry_dispose_is_hmr_safe():
    reg = _registry(_spec())
    reg.add_pre_hook(lambda n, s: tc.Decision.allow())
    reg.add_guard(lambda n, s, d: d)
    reg.add_post_hook(lambda n, s, r: tc.PostDecision.accept())
    reg.add_wrapper(lambda d, s: (d, None))
    assert reg.has("echo")
    reg.dispose()
    assert reg.names() == []
    assert reg.pre_hooks == []
    assert reg.guards == []
    assert reg.post_hooks == []
    assert reg.wrappers == []
    assert tc.execute_tool(reg, "echo", {"a": 1}).code == "UNKNOWN_TOOL"


def test_contract20_conformance_kit_detects_bad_renderer():
    good = _spec()
    assert tc.conformance_check(good) == []

    counter = {"n": 0}

    def nondeterministic(args, value):
        counter["n"] += 1
        return str(counter["n"])
    bad = _spec(name="bad", renderer=nondeterministic)
    assert any("not pure" in p for p in tc.conformance_check(bad))


def test_contract20_request_reconstruction_byte_compare():
    assert tc.request_reconstruction_byte_compare("abc", "abc") is True
    assert tc.request_reconstruction_byte_compare("abc", "abd") is False


def test_contract20_fuzz_tool_produces_only_stable_codes():
    results = tc.fuzz_tool(_spec(), cases=12, cancel_points=(0, 5))
    codes = {r.code for r in results}
    assert codes <= {None, "INVALID_ARGS", "ABORTED"}
    assert len(results) == 12

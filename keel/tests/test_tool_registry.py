from __future__ import annotations

import pytest

from keel.tools.registry import Tool, ToolRegistry, create_native_registry


def make_tool(name="echo", handler=None, schema=None, permission="read"):
    if handler is None:
        handler = lambda tool_input: ("ok", {"echoed": tool_input})
    if schema is None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    return Tool(name=name, description="echo tool", input_schema=schema,
                handler=handler, permission=permission)


def test_register_and_lookup():
    reg = ToolRegistry()
    t = make_tool()
    reg.register(t)
    assert reg.has("echo")
    assert reg.get("echo") is t
    assert "echo" in reg.names()


def test_duplicate_registration_rejected():
    reg = ToolRegistry()
    reg.register(make_tool())
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(make_tool())


def test_replace_registration():
    reg = ToolRegistry()
    reg.register(make_tool())
    reg.register(make_tool(handler=lambda i: ("replaced", {})), replace=True)
    assert reg.execute("echo", {"x": "y"})[0] == "replaced"


def test_invalid_tool_definition_rejected():
    reg = ToolRegistry()
    with pytest.raises(ValueError):
        reg.register(Tool(name="", description="d", input_schema={}, handler=lambda i: None))
    with pytest.raises(ValueError):
        reg.register(Tool(name="x", description="", input_schema={}, handler=lambda i: None))
    with pytest.raises(ValueError):
        reg.register(Tool(name="x", description="d", input_schema="notdict", handler=lambda i: None))
    with pytest.raises(TypeError):
        reg.register("not a tool")  # type: ignore[arg-type]


def test_list_and_schemas():
    reg = ToolRegistry()
    reg.register(make_tool("a"))
    reg.register(make_tool("b"))
    names = [t.name for t in reg.list_tools()]
    assert names == ["a", "b"]
    schemas = reg.schemas()
    assert {s["name"] for s in schemas} == {"a", "b"}
    assert all("input_schema" in s for s in schemas)
    assert reg.schemas(["a"]) == [schemas[0]] or reg.schemas(["a"])[0]["name"] == "a"


def test_validate_valid_input():
    reg = ToolRegistry()
    reg.register(make_tool())
    assert reg.validate("echo", {"x": "hi"}) == []


def test_validate_invalid_input():
    reg = ToolRegistry()
    reg.register(make_tool())
    errs = reg.validate("echo", {})
    assert any("missing required" in e for e in errs)
    errs = reg.validate("echo", {"x": 5})
    assert any("expected string" in e for e in errs)


def test_dispatch_success():
    reg = ToolRegistry()
    reg.register(make_tool())
    result = reg.execute("echo", {"x": "hi"})
    assert result == ("ok", {"echoed": {"x": "hi"}})


def test_dispatch_unknown_tool():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.execute("nope", {})


def test_dispatch_validation_error():
    reg = ToolRegistry()
    reg.register(make_tool())
    with pytest.raises(ValueError):
        reg.execute("echo", {})


def test_dispatch_handler_error_propagates():
    def boom(i):
        raise RuntimeError("boom")
    reg = ToolRegistry()
    reg.register(make_tool(handler=boom))
    with pytest.raises(RuntimeError, match="boom"):
        reg.execute("echo", {"x": "hi"})


def test_unavailable_tool_not_executed():
    reg = ToolRegistry()
    t = make_tool()
    t.available = False
    reg.register(t)
    with pytest.raises(RuntimeError, match="not available"):
        reg.execute("echo", {"x": "hi"})


def test_permission_metadata():
    reg = ToolRegistry()
    reg.register(make_tool(permission="write"))
    assert reg.get("echo").permission == "write"


def test_create_native_registry():
    class FakeExecutor:
        def invoke(self, name, tool_input):
            return f"ran {name}", {"tool": name}
    reg = create_native_registry(FakeExecutor())
    assert "read_file" in reg.names()
    assert "run_shell" in reg.names()
    # Task raises because session handles it
    with pytest.raises(RuntimeError):
        reg.execute("Task", {"prompt": "x"})
    # A native tool dispatches to executor
    out = reg.execute("read_file", {"path": "foo.txt"})
    assert out[0] == "ran read_file"


def test_native_registry_schemas_match_session():
    from keel.session import TOOL_SCHEMAS, ALL_TOOLS
    from keel.tools.native import NATIVE_TOOL_SCHEMAS, NATIVE_TOOL_NAMES
    assert TOOL_SCHEMAS == NATIVE_TOOL_SCHEMAS
    assert ALL_TOOLS == list(NATIVE_TOOL_NAMES)


def test_session_uses_registry_for_schemas():
    from keel.fakes import ScriptedModel
    from keel.session import Session, SessionConfig
    cfg = SessionConfig(cwd=".", state_root="/tmp/keel-test", session_id="s1")
    sess = Session(model_client=ScriptedModel([[]], model="m"), executor=object(),
                   config=cfg)
    assert hasattr(sess, "tools")
    assert "read_file" in sess.tools.names()
    assert sess.allowed_tools == tuple(sess.tools.names())


def test_session_dispatch_uses_registry(monkeypatch):
    from keel.fakes import ScriptedModel
    from keel.session import Session, SessionConfig
    from keel.tools.registry import Tool

    class FakeExecutor:
        def invoke(self, name, tool_input):
            return f"ran {name}", {"tool": name}

    cfg = SessionConfig(cwd=".", state_root="/tmp/keel-test", session_id="s2")
    sess = Session(model_client=ScriptedModel([[]], model="m"), executor=FakeExecutor(),
                   config=cfg)
    # Replace a tool handler to prove dispatch goes through registry
    sess.tools.register(Tool(
        name="read_file",
        description="read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        handler=lambda ti: ("registry-handled", {"path": ti["path"]}),
        permission="read",
    ), replace=True)
    out = sess.tools.execute("read_file", {"path": "x"})
    assert out[0] == "registry-handled"

"""B1.1/B1.2 — constrained schemas and tolerant tool-call parsing."""

from __future__ import annotations

from keel.fakes import SeededRng, VirtualClock
from keel.session import Session, SessionConfig
from keel.tool_json import (coerce_tool_input, constrain_tool_schema,
                            constrain_tool_schemas, parse_tool_args,
                            repair_json, validate_tool_input)

SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "count": {"type": "integer"},
        "mode": {"type": "string", "enum": ["fast", "slow"]},
    },
    "required": ["path"],
}


def test_repair_handles_common_local_model_quirks():
    assert repair_json('{"path": "a.txt",}') == {"path": "a.txt"}
    assert repair_json("{'path': 'a.txt'}") == {"path": "a.txt"}
    assert repair_json("here: {path: 'a.txt'} done") == {"path": "a.txt"}
    assert repair_json("```json\n{\"path\": \"a.txt\"}\n```") == {"path": "a.txt"}
    assert repair_json('{"path": "a.txt"') == {"path": "a.txt"}


def test_validation_reports_missing_and_wrong_types():
    errors = validate_tool_input({"count": "x"}, SCHEMA)
    assert any("missing required field: path" in e for e in errors)
    assert any("count must be integer" in e for e in errors)
    assert validate_tool_input({"path": "a", "mode": "fast"}, SCHEMA) == []


def test_coercion_and_parse_pipeline():
    data = parse_tool_args("{'path': 1, 'count': '3', 'mode': 'fast'}", SCHEMA)
    assert data == {"path": "1", "count": 3, "mode": "fast"}


def test_constrained_schemas_mark_additional_properties_false():
    constrained = constrain_tool_schema(
        {"name": "x", "description": "d", "input_schema": SCHEMA})
    assert constrained["input_schema"]["additionalProperties"] is False
    assert constrained["_constrained"] is True
    assert len(constrain_tool_schemas([{"name": "x"}])) == 1


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="ffffffff-ffff-4fff-ffff-ffffffffffff",
                         model="boom-1", seed=0)


class _Executor:
    def __init__(self):
        self.calls = []

    def invoke(self, name, tool_input):
        self.calls.append((name, tool_input))
        return "ok", {}


def test_session_repairs_string_tool_input(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return [{"type": "tool_use", "name": "read_file",
                         "input": "{'path': 'a.txt',}"}]
            return [{"type": "text", "text": "done"}]

    executor = _Executor()
    session = Session(model_client=Model(), executor=executor,
                      config=_cfg(tmp_path),
                      rules=((), (), ("read_file",)),
                      clock=VirtualClock(), rng=SeededRng(0))
    session.run("read a file")
    assert executor.calls[0][1] == {"path": "a.txt"}

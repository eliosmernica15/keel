"""X1.1 / X1.2 / X1.3 — model dialect adapters, chat templates, reasoning output.

Tests are written before the implementation (TDD). Every assertion here is a
clean-room behavioural contract derived from the reconciled registry entries;
no reference implementation was consulted.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from keel.model_dialects import (
    DIALECTS,
    ChatTemplateRecord,
    ReasoningBlock,
    ToolCall,
    collapse_reasoning,
    count_reasoning_tokens,
    count_total_reasoning_tokens,
    detect_dialect,
    detect_dialect_scores,
    dialect_for_model_family,
    format_tool_call,
    load_chat_template,
    parse_tool_calls,
    select_dialect_for_model,
    should_include_in_history,
    split_reasoning,
    strip_reasoning,
    template_warning,
)


# ---------------------------------------------------------------------------
# X1.1 — tool-call dialect adapters
# ---------------------------------------------------------------------------

JSON_CALL = '{"name": "read_file", "arguments": {"path": "a.txt"}}'
XML_CALL = (
    "<tool_call><name>read_file</name>"
    '<arguments>{"path": "a.txt"}</arguments></tool_call>'
)
HERMES_CALL = (
    "<|im_start|>assistant<|channel|>commentary to=functions.read_file "
    '<|constrain|>json\n{"path": "a.txt"}<|im_end|>'
)
REACT_CALL = (
    "Thought: I should read the file.\n"
    "Action: read_file\n"
    'Action Input: {"path": "a.txt"}\n'
    "Observation: contents"
)
MISTRAL_CALL = '[TOOL_CALLS] [{"name": "read_file", "arguments": {"path": "a.txt"}}]'
QWEN_CALL = '<tool_call>\n{"name": "read_file", "arguments": {"path": "a.txt"}}\n</tool_call>'
DEEPSEEK_CALL = (
    "<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>read_file<｜tool▁sep｜>"
    '{"path": "a.txt"}<｜tool▁call▁end｜><｜tool▁calls▁end｜>'
)


@pytest.mark.parametrize(
    "text,expected",
    [
        (JSON_CALL, "json"),
        (XML_CALL, "xml"),
        (HERMES_CALL, "hermes"),
        (REACT_CALL, "react"),
        (MISTRAL_CALL, "mistral"),
        (QWEN_CALL, "qwen"),
        (DEEPSEEK_CALL, "deepseek"),
    ],
)
def test_detect_dialect_recognizes_each_family(text, expected):
    assert detect_dialect(text) == expected


def test_detect_dialect_unknown_for_plain_text():
    assert detect_dialect("Just a normal answer with no tool machinery.") == "unknown"
    assert detect_dialect("") == "unknown"


def test_detect_dialect_scores_are_bounded_and_explain_choice():
    scores = detect_dialect_scores(REACT_CALL)
    assert isinstance(scores, dict)
    assert scores["react"] > scores["json"]
    assert all(isinstance(v, (int, float)) and v >= 0 for v in scores.values())


def test_detect_dialect_conflicting_formats_is_deterministic():
    # ReAct scoring is stronger than a bare JSON object; choice must be stable.
    conflict = "Thought: use a tool\nAction: read_file\nAction Input: " + JSON_CALL
    first = detect_dialect(conflict)
    assert first == detect_dialect(conflict) == detect_dialect(conflict)
    assert first == "react"
    auto = parse_tool_calls(conflict, dialect="auto")
    explicit = parse_tool_calls(conflict, dialect=first)
    assert [c.name for c in auto] == [c.name for c in explicit]


def test_dialects_constant_exposes_expected_names():
    assert {"json", "xml", "hermes", "react", "mistral", "qwen", "deepseek"} <= set(DIALECTS)


@pytest.mark.parametrize(
    "text",
    [JSON_CALL, XML_CALL, HERMES_CALL, REACT_CALL, MISTRAL_CALL, QWEN_CALL, DEEPSEEK_CALL],
)
def test_parse_tool_calls_extracts_name_and_arguments(text):
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ToolCall)
    assert call.name == "read_file"
    assert call.arguments == {"path": "a.txt"}
    assert not call.incomplete


def test_parse_json_wrapped_and_list_shapes():
    wrapped = parse_tool_calls('{"function": {"name": "ping", "arguments": {"n": 1}}}', "json")
    assert wrapped[0].name == "ping"
    assert wrapped[0].arguments == {"n": 1}
    batch = parse_tool_calls(
        '{"tool_calls": [{"name": "a", "arguments": {"x": 1}}, '
        '{"name": "b", "arguments": {"y": 2}}]}',
        "json",
    )
    assert [c.name for c in batch] == ["a", "b"]


def test_parse_json_truncated_output_recovers_partial_call():
    truncated = '{"name": "read_file", "arguments": {"path": "a.txt"'
    calls = parse_tool_calls(truncated, "json")
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert calls[0].arguments.get("path") == "a.txt"
    assert calls[0].incomplete is True


def test_parse_json_tolerates_fences_and_single_quotes():
    fenced = '```json\n{"name": "ping", "arguments": {"host": "x"}}\n```'
    assert parse_tool_calls(fenced, "json")[0].arguments == {"host": "x"}
    single = "{'name': 'ping', 'arguments': {'host': 'x'}}"
    assert parse_tool_calls(single, "json")[0].name == "ping"


def test_parse_xml_nested_structure_and_nested_same_name_tags():
    nested = (
        "<function_calls>"
        "<invoke><tool_name>write</tool_name>"
        "<parameters><path>out.txt</path><opts><mode>fast</mode></opts></parameters>"
        "</invoke>"
        "<invoke><tool_name>read</tool_name>"
        "<tool_call><name>inner</name></tool_call>"
        "</invoke>"
        "</function_calls>"
    )
    calls = parse_tool_calls(nested, "xml")
    names = [c.name for c in calls]
    assert "write" in names and "read" in names
    write = next(c for c in calls if c.name == "write")
    assert write.arguments["path"] == "out.txt"
    assert isinstance(write.arguments["opts"], dict)
    assert write.arguments["opts"]["mode"] == "fast"


def test_parse_xml_truncated_fragment_is_flagged_incomplete():
    calls = parse_tool_calls("<tool_call><name>read_file</name><arguments>{}", "xml")
    assert calls
    assert calls[0].name == "read_file"
    assert calls[0].incomplete is True


def test_parse_hermes_and_react_stop_at_boundaries():
    hermes = parse_tool_calls(HERMES_CALL + "\nFinal answer", "hermes")
    assert hermes[0].arguments == {"path": "a.txt"}
    react = parse_tool_calls(REACT_CALL, "react")
    assert react[0].name == "read_file"
    assert react[0].arguments == {"path": "a.txt"}


def test_parse_react_action_input_key_value_form():
    calls = parse_tool_calls("Action: ping\nAction Input: host=example count=2", "react")
    assert calls[0].name == "ping"
    assert calls[0].arguments == {"host": "example", "count": "2"}


def test_parse_variant_dialects_roundtrip_emitters():
    for dialect in ("mistral", "qwen", "deepseek"):
        emitted = format_tool_call("ping", {"host": "x"}, dialect)
        parsed = parse_tool_calls(emitted, dialect)
        assert parsed[0].name == "ping", dialect
        assert parsed[0].arguments == {"host": "x"}, dialect


def test_parse_never_executes_embedded_code():
    # Tool arguments are data only. No eval/exec/subprocess is used.
    hostile = (
        '{"name": "shell", "arguments": {"cmd": "os.system(\'touch /tmp/pwned\')", '
        '"payload": "__import__(\'os\').system(\'id\')"}}'
    )
    calls = parse_tool_calls(hostile, "json")
    assert calls[0].arguments["cmd"].startswith("os.system")
    assert calls[0].arguments["payload"].startswith("__import__")
    assert not os.path.exists("/tmp/pwned")


def test_parse_malformed_input_returns_empty_list():
    assert parse_tool_calls("not a tool call at all", "json") == []
    assert parse_tool_calls("", "xml") == []
    assert parse_tool_calls("<<<>>>", "react") == []


@pytest.mark.parametrize("dialect", ["json", "xml", "hermes", "react", "mistral", "qwen", "deepseek"])
def test_format_then_parse_roundtrip(dialect):
    emitted = format_tool_call("read_file", {"path": "a.txt"}, dialect)
    assert isinstance(emitted, str) and emitted
    parsed = parse_tool_calls(emitted, dialect)
    assert parsed[0].name == "read_file"
    assert parsed[0].arguments == {"path": "a.txt"}


def test_format_json_is_stable_and_unicode_preserving():
    out = format_tool_call("ping", {"b": 2, "a": "café 😀"}, "json")
    assert json.loads(out)["arguments"]["a"] == "café 😀"
    assert out.index('"a"') < out.index('"b"')
    # deterministic for identical inputs
    assert format_tool_call("ping", {"b": 2, "a": "café 😀"}, "json") == out


def test_format_xml_escapes_special_characters():
    out = format_tool_call("write", {"path": "a&b<c>.txt"}, "xml")
    assert "&amp;" in out and "&lt;" in out
    parsed = parse_tool_calls(out, "xml")
    assert parsed[0].arguments["path"] == "a&b<c>.txt"


def test_format_rejects_unknown_dialect():
    with pytest.raises(ValueError):
        format_tool_call("x", {}, "not-a-dialect")


def test_dialect_for_model_family_and_probe_selection():
    assert dialect_for_model_family("meta-llama/Llama-3.1-8B") == "llama"
    assert dialect_for_model_family("mistralai/Mistral-7B") == "mistral"
    assert dialect_for_model_family("Qwen/Qwen2.5-7B-Instruct") == "qwen"
    assert dialect_for_model_family("deepseek-ai/DeepSeek-V3") == "deepseek"
    assert dialect_for_model_family("nousresearch/hermes-3-llama-3.1") == "hermes"
    assert dialect_for_model_family("totally-unknown-model") == "json"

    probes = {
        "models": {
            "org/model": {"dialect": "xml", "score": 0.9},
            "org/other": {"json": 0.2, "react": 0.8},
        }
    }
    assert select_dialect_for_model("org/model", probes) == "xml"
    assert select_dialect_for_model("org/other", probes) == "react"
    assert select_dialect_for_model("org/unknown", probes) == "json"


def test_tool_call_is_data_only_dataclass():
    call = ToolCall("ping", {"host": "x"}, "json")
    assert call.name == "ping" and call.arguments == {"host": "x"}
    with pytest.raises(Exception):
        call.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# X1.2 — chat-template handling
# ---------------------------------------------------------------------------


def _write(catalog, rel, text):
    path = catalog / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_load_chat_template_from_per_model_override(tmp_path):
    _write(tmp_path, "overrides/org/model.json", json.dumps({
        "chat_template": "{{ user }} / {{ assistant }}", "dialect": "hermes"
    }))
    record = load_chat_template("org/model", str(tmp_path))
    assert isinstance(record, ChatTemplateRecord)
    assert record.found is True
    assert record.template == "{{ user }} / {{ assistant }}"
    assert record.overrides["dialect"] == "hermes"
    assert "overrides" in record.source


def test_load_chat_template_from_template_file_and_catalog(tmp_path):
    _write(tmp_path, "models/org/model/chat_template.jinja", "FILE {{ content }}")
    rec_file = load_chat_template("org/model", str(tmp_path))
    assert rec_file.found and rec_file.template == "FILE {{ content }}"
    assert rec_file.source.endswith("chat_template.jinja")

    _write(tmp_path, "catalog.json", json.dumps({
        "models": {"other/model": {"chat_template": "INLINE {{ x }}", "eos": "<|end|>"}}
    }))
    rec_cat = load_chat_template("other/model", str(tmp_path))
    assert rec_cat.found and rec_cat.template == "INLINE {{ x }}"
    assert rec_cat.overrides["eos"] == "<|end|>"


def test_load_chat_template_catalog_template_file_is_contained(tmp_path):
    _write(tmp_path, "catalog.json", json.dumps({
        "models": {"m": {"template_file": "templates/m.jinja"}}
    }))
    _write(tmp_path, "templates/m.jinja", "FROM FILE")
    assert load_chat_template("m", str(tmp_path)).template == "FROM FILE"


def test_load_chat_template_override_beats_catalog(tmp_path):
    _write(tmp_path, "catalog.json", json.dumps({
        "models": {"m": {"chat_template": "CATALOG"}}
    }))
    _write(tmp_path, "overrides/m.json", json.dumps({"chat_template": "OVERRIDE"}))
    assert load_chat_template("m", str(tmp_path)).template == "OVERRIDE"


def test_load_chat_template_missing_returns_not_found(tmp_path):
    rec = load_chat_template("nobody/model", str(tmp_path))
    assert rec.found is False and rec.template is None and rec.source is None


@pytest.mark.parametrize("model_id", [
    "../../etc/passwd",
    "..\\..\\windows\\win.ini",
    "org/../../etc/passwd",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "org/%2e%2e/etc/passwd",
    "org//model",
    ".",
    "..",
    "",
])
def test_load_chat_template_rejects_traversal_in_model_id(tmp_path, model_id):
    with pytest.raises(ValueError):
        load_chat_template(model_id, str(tmp_path))


def test_load_chat_template_rejects_template_file_traversal(tmp_path):
    outside = tmp_path.parent / "outside-template.txt"
    outside.write_text("SECRET OUTSIDE CONTENT", encoding="utf-8")
    _write(tmp_path, "catalog.json", json.dumps({
        "models": {"m": {"template_file": "../outside-template.txt",
                         "chat_template": "SAFE INLINE"}}
    }))
    rec = load_chat_template("m", str(tmp_path))
    assert rec.template == "SAFE INLINE"
    assert all("SECRET OUTSIDE CONTENT" not in str(w) for w in rec.warnings)
    assert any("containment" in w.lower() or "escape" in w.lower() for w in rec.warnings)


def test_load_chat_template_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("LEAK", encoding="utf-8")
    link_root = tmp_path / "models" / "m"
    link_root.mkdir(parents=True)
    link = link_root / "chat_template.jinja"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    rec = load_chat_template("m", str(tmp_path))
    assert rec.template is None or "LEAK" not in rec.template
    assert any("containment" in w.lower() or "symlink" in w.lower() for w in rec.warnings)


def test_template_warning_detects_family_mismatch():
    good = "<|im_start|>user\n{{ user }}<|im_end|><|im_start|>assistant\n{{ assistant }}"
    assert template_warning(good, "nousresearch/hermes-3") is None
    bad = template_warning("[INST] {{ user }} [/INST]", "nousresearch/hermes-3")
    assert bad is not None and "hermes-3" in bad and "im_start" in bad


def test_template_warning_for_missing_and_empty_template():
    assert "no chat template" in template_warning(None, "org/model").lower()
    assert "no chat template" in template_warning("", "org/model").lower()


def test_template_warning_flags_missing_tool_markers():
    plain = "<|im_start|>user\n{{ u }}<|im_end|><|im_start|>assistant\n{{ a }}<|im_end|>"
    warning = template_warning(plain, "org/model", dialect="hermes")
    assert warning is not None and "tool" in warning.lower()


# ---------------------------------------------------------------------------
# X1.3 — reasoning-model output handling
# ---------------------------------------------------------------------------


def test_split_reasoning_basic():
    visible, blocks = split_reasoning("<think>plan step 1</think>\nAnswer here.")
    assert visible == "\nAnswer here."
    assert len(blocks) == 1
    assert isinstance(blocks[0], ReasoningBlock)
    assert blocks[0].text == "plan step 1"
    assert blocks[0].tag == "think"
    assert blocks[0].closed is True


def test_split_reasoning_variants_and_multiple_blocks():
    text = (
        "<thinking>A</thinking>one"
        "<|analysis|>B<|/analysis|>two"
        "<｜reasoning｜>C<｜/reasoning｜>three"
    )
    visible, blocks = split_reasoning(text)
    assert visible == "onetwothree"
    assert [b.text for b in blocks] == ["A", "B", "C"]
    assert [b.tag for b in blocks] == ["thinking", "analysis", "reasoning"]


def test_split_reasoning_unclosed_block_is_flagged():
    visible, blocks = split_reasoning("Hello<think>unfinished thought")
    assert visible == "Hello"
    assert len(blocks) == 1
    assert blocks[0].text == "unfinished thought"
    assert blocks[0].closed is False


def test_split_reasoning_oversized_block_is_linear_and_intact():
    body = "x" * 200_000
    text = f"<think>{body}</think>visible"
    visible, blocks = split_reasoning(text)
    assert visible == "visible"
    assert len(blocks) == 1 and blocks[0].text == body


def test_split_reasoning_preserves_unicode():
    visible, blocks = split_reasoning("<think>计划🤔</think> answer 日本語")
    assert blocks[0].text == "计划🤔"
    assert visible == " answer 日本語"


def test_strip_and_collapse_reasoning():
    text = "Before<think>secret</think>After"
    assert strip_reasoning(text) == "BeforeAfter"
    collapsed = collapse_reasoning(text, placeholder="[R]")
    assert collapsed == "Before[R]After"
    assert "[R]" not in strip_reasoning(text)


def test_should_include_in_history_default_false_and_optin():
    block = ReasoningBlock("internal plan", "think", 0, 0, True)
    assert should_include_in_history(block) is False
    assert should_include_in_history("<think>x</think>") is False
    assert should_include_in_history([block]) is False
    assert should_include_in_history(block, include_reasoning_in_history=True) is True
    assert should_include_in_history(block, include_reasoning=True) is True


def test_count_reasoning_tokens_uses_context_estimator_by_default():
    text = "a" * 40
    assert count_reasoning_tokens(text) == math.ceil(len(text.encode("utf-8")) / 4)


def test_count_reasoning_tokens_accepts_custom_estimator():
    seen = []

    def estimator(text):
        seen.append(text)
        return len(text)

    block = ReasoningBlock("abc", "think", 0, 0, True)
    assert count_reasoning_tokens(block, estimator=estimator) == 3
    assert seen == ["abc"]


def test_count_reasoning_tokens_unicode_and_lists():
    assert count_reasoning_tokens("计划🤔") == math.ceil(len("计划🤔".encode("utf-8")) / 4)
    blocks = [ReasoningBlock("abcd", "think", 0, 0, True), ReasoningBlock("ef", "think", 0, 0, False)]
    assert count_reasoning_tokens(blocks) == math.ceil(6 / 4)


def test_count_total_reasoning_tokens_from_full_output():
    text = "<think>aaaaaaaa</think>visible<reasoning>bbbb</reasoning>done"
    assert count_total_reasoning_tokens(text) == math.ceil(12 / 4)
    assert count_total_reasoning_tokens("no reasoning here") == 0

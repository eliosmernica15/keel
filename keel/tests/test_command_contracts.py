"""Permanent contract-regression specs for the W5.x command contracts.

Covers the four not_started P0 rows from the 865-row registry:
W5.1 (definition format / nested ids / scope precedence / hot reload),
W5.2 (frontmatter fields, true/false/omit, legacy alias, typed validation),
W5.3 (argument substitution with quote grouping and remainder),
W5.4 (shell ``!`cmd` `` descriptors, explicit approval, no injection).

These specs are additive: they import only ``keel.command_contracts``.  The
module is a pure parser/descriptor layer -- no subprocess, no file writes, no
live command execution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import keel.command_contracts as cc


def _md(text: str, rel: str = "review.md",
        scope: cc.Scope = cc.Scope.PROJECT,
        *, command_id: str | None = None) -> cc.CommandSource:
    return cc.CommandSource(relative_path=rel, text=text, scope=scope,
                            command_id=command_id)


def _frontmatter(body: str, **fields: str) -> str:
    lines = ["---"]
    lines.extend(f"{k}: {v}" for k, v in fields.items())
    lines.extend(["---", "", body])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# W5.1 -- definitions, nested ids, containment, scope precedence, reload
# ---------------------------------------------------------------------------


def test_nested_paths_become_slash_command_ids():
    assert cc.command_id_from_path("review.md") == "review"
    assert cc.command_id_from_path("team/review.md") == "team/review"
    assert cc.command_id_from_path("team\\deep\\ship.json") == "team/deep/ship"
    descriptor = cc.parse_command_source(
        _md("Do the review.", "team/review.md"))
    assert descriptor.id == "team/review"
    assert descriptor.name == "review"
    assert descriptor.title == "/team/review"
    assert descriptor.scope is cc.Scope.PROJECT
    assert descriptor.format is cc.CommandFormat.MARKDOWN


def test_path_containment_for_command_files():
    root = Path("/proj/.keel/commands")
    assert cc.is_contained_command_path("team/review.md", root)
    assert cc.assert_contained_command_path("team\\review.md", root) == (
        "team/review.md")
    for bad in ("../evil.md", "team/../../evil.md", "/abs.md",
                "C:\\Windows\\evil.md", "\\\\server\\share\\evil.md",
                "team//review.md", "team/./review.md", "", "team/"):
        assert not cc.is_contained_command_path(bad, root), bad
        with pytest.raises(cc.CommandPathError) as exc:
            cc.assert_contained_command_path(bad, root)
        assert isinstance(exc.value, cc.CommandContractError)


def test_project_overrides_global_and_nearer_overrides_ancestor():
    text = _frontmatter("winner", description="d")
    sources = [
        _md(text, "team/review.md", cc.Scope.GLOBAL),
        _md(text, "team/review.md", cc.Scope.PROJECT),
        _md("nearer text", "review.md", cc.Scope.PROJECT,
            command_id="team/review"),
        _md("ancestor text", "deep/ancestor/review.md", cc.Scope.PROJECT,
            command_id="team/review"),
    ]
    registry = cc.CommandRegistry.build(sources)
    winner = registry.get("team/review")
    assert winner.template == "nearer text"
    assert winner.scope is cc.Scope.PROJECT

    without_nearer = cc.CommandRegistry.build(sources[:2])
    assert without_nearer.get("team/review").scope is cc.Scope.PROJECT


def test_custom_replaces_builtin_and_precedence_is_deterministic():
    sources = [
        _md(_frontmatter("custom body", description="custom"),
            "review.md", cc.Scope.GLOBAL),
        _md(_frontmatter("custom body", description="custom"),
            "team\\review.md", cc.Scope.GLOBAL, command_id="review"),
    ]
    first = cc.CommandRegistry.build(sources, builtin_ids=("help", "review"))
    second = cc.CommandRegistry.build(list(reversed(sources)),
                                      builtin_ids=("review", "help"))
    assert first.fingerprint == second.fingerprint
    assert first.list_ids() == second.list_ids() == ("help", "review")
    assert first.get("review").source_kind is cc.SourceKind.CUSTOM
    assert first.get("review").template == "custom body"
    assert first.get("help").source_kind is cc.SourceKind.BUILTIN
    assert first.get("help").template == ""


def test_hot_reload_is_content_addressed():
    source = _md(_frontmatter("v1", description="d"), "team/review.md")
    registry = cc.CommandRegistry.build([source])
    same = cc.hot_reload(registry, [source])
    assert same.changed is False
    assert same.registry.fingerprint == registry.fingerprint

    changed = cc.hot_reload(registry, [
        _md(_frontmatter("v2", description="d"), "team/review.md")])
    assert changed.changed is True
    assert changed.registry.fingerprint != registry.fingerprint
    assert changed.changed_ids == ("team/review",)
    assert changed.previous_fingerprint == registry.fingerprint


# ---------------------------------------------------------------------------
# W5.2 -- frontmatter fields, booleans, legacy alias, typed validation
# ---------------------------------------------------------------------------


def test_frontmatter_description_agent_model_subagent_true_false_omit():
    def parse(subagent: str | None) -> cc.CommandDescriptor:
        fields = {"description": "Ship it", "agent": "reviewer",
                  "model": "gpt-5"}
        if subagent is not None:
            fields["subagent"] = subagent
        return cc.parse_command_source(_md(_frontmatter("body", **fields)))

    yes = parse("true")
    assert (yes.description, yes.agent, yes.model) == (
        "Ship it", "reviewer", "gpt-5")
    assert yes.subagent is True
    assert yes.subagent_source == "field"
    assert parse("false").subagent is False
    omitted = parse(None)
    assert omitted.subagent is None
    assert omitted.subagent_source == "omitted"


def test_legacy_subtask_alias_maps_to_subagent():
    legacy = cc.parse_command_source(_md(_frontmatter(
        "body", description="d", subtask="false")))
    assert legacy.subagent is False
    assert legacy.subagent_source == "legacy"
    both = cc.parse_command_source(_md(_frontmatter(
        "body", description="d", subagent="true", subtask="true")))
    assert both.subagent is True and both.subagent_source == "field"
    with pytest.raises(cc.CommandValidationError) as exc:
        cc.parse_command_source(_md(_frontmatter(
            "body", description="d", subagent="true", subtask="false")))
    assert exc.value.field == "subagent"


def test_frontmatter_validation_errors_are_typed():
    cases = [
        ("subagent", "yes"),
        ("subagent", "1"),
        ("agent", "[a, b]"),
        ("model", "42"),
        ("description", "[x]"),
    ]
    for field, value in cases:
        fields = {"description": "d"}
        fields[field] = value
        with pytest.raises(cc.CommandValidationError) as exc:
            cc.parse_command_source(_md(_frontmatter("body", **fields)))
        assert exc.value.field == field
        assert isinstance(exc.value, cc.CommandContractError)


def test_json_command_definition_and_parse_errors():
    obj = {
        "description": "JSON command", "agent": "reviewer",
        "model": "gpt-5", "subagent": False,
        "argument-hint": "<path>", "template": "Review $1",
    }
    descriptor = cc.parse_command_source(cc.CommandSource(
        relative_path="team/review.json", text=json.dumps(obj),
        scope=cc.Scope.PROJECT))
    assert descriptor.format is cc.CommandFormat.JSON
    assert descriptor.description == "JSON command"
    assert descriptor.subagent is False
    assert descriptor.argument_hint == "<path>"
    assert descriptor.template == "Review $1"

    with pytest.raises(cc.CommandParseError) as exc:
        cc.parse_command_source(cc.CommandSource(
            relative_path="bad.json", text="{nope",
            scope=cc.Scope.PROJECT))
    assert isinstance(exc.value, cc.CommandContractError)
    with pytest.raises(cc.CommandParseError):
        cc.parse_frontmatter("no frontmatter fence here")
    # A frontmatter-less markdown file is a valid prompt-only command.
    plain = cc.parse_command_source(_md("Just do the thing."))
    assert plain.template == "Just do the thing."
    assert plain.subagent is None


# ---------------------------------------------------------------------------
# W5.3 -- argument substitution
# ---------------------------------------------------------------------------


def test_tokenize_arguments_quote_grouping():
    assert cc.tokenize_arguments('alpha "two words" \'three four\' "" tail') == (
        "alpha", "two words", "three four", "", "tail")
    assert cc.tokenize_arguments('say "a \\"quoted\\" b"') == (
        'say', 'a "quoted" b')
    assert cc.tokenize_arguments("") == ()
    with pytest.raises(cc.ArgumentParseError):
        cc.tokenize_arguments('"unclosed')


def test_arguments_and_positional_placeholders():
    out = cc.substitute_arguments(
        "$ARGUMENTS | $1 | $2 | $1 again", "one 'two words' three")
    assert out.text == (
        "one 'two words' three | one | two words three | one again")
    assert out.placeholders == ("ARGUMENTS", "1", "2", "1")
    assert out.tokens == ("one", "two words", "three")
    assert out.fallback_appended is False


def test_last_placeholder_takes_the_remainder_and_missing_is_empty():
    assert cc.substitute_arguments("$1", "a b c").text == "a b c"
    assert cc.substitute_arguments("$1 -- $2", "a b c d").text == (
        "a -- b c d")
    assert cc.substitute_arguments("[$1][$2][$3]", "only").text == "[only][][]"
    assert cc.substitute_arguments("[${1}]", "x y").text == "[x y]"


def test_fallback_appends_arguments_when_no_placeholder():
    out = cc.substitute_arguments("Review the diff.", "now please")
    assert out.text == "Review the diff.\n\nnow please"
    assert out.fallback_appended is True
    assert cc.substitute_arguments("Review the diff.", "").text == (
        "Review the diff.")


def test_no_shell_interpolation_or_recursive_expansion():
    args = '$2; echo $(id) `touch pwned` $1'
    out = cc.substitute_arguments("literal $1", args)
    assert out.text == f"literal {args}"
    assert "$2" in out.text and "$(id)" in out.text and "`touch pwned`" in out.text
    # A substituted argument is never re-scanned for placeholders.
    assert cc.substitute_arguments("$1", "x $ARGUMENTS").text == "x $ARGUMENTS"


# ---------------------------------------------------------------------------
# W5.4 -- shell descriptors, explicit approval, no injection via substitution
# ---------------------------------------------------------------------------


def test_shell_descriptor_and_permission_gate():
    template = "Before:\n!`git status --short`\nAfter"
    descriptors = cc.parse_shell_descriptors(template)
    assert len(descriptors) == 1
    descriptor = descriptors[0]
    assert descriptor.command == "git status --short"
    assert descriptor.raw == "!`git status --short`"
    assert descriptor.approval_required is True
    assert descriptor.tier == 2
    assert descriptor.executed is False
    assert descriptor.output is None
    assert len(descriptor.id) == 12
    assert cc.parse_shell_descriptors(template)[0].id == descriptor.id
    gate = cc.permission_gate_for(descriptor)
    assert gate.tier == 2
    assert gate.approval_required is True
    assert gate.show_resolved_command is True
    assert gate.runs_outside_agent_permission_flow is False
    payload = descriptor.to_dict()
    assert json.loads(json.dumps(payload))["command"] == descriptor.command


def test_shell_output_insertion_requires_explicit_approval():
    descriptor = cc.parse_shell_descriptors("!`git status --short`")[0]
    with pytest.raises(cc.ShellApprovalError) as exc:
        cc.render_shell_output(descriptor, " M file.py", approved=False)
    assert isinstance(exc.value, cc.CommandContractError)
    insertion = cc.render_shell_output(descriptor, " M file.py", approved=True)
    assert insertion.text == " M file.py"
    assert insertion.descriptor_id == descriptor.id
    assert insertion.approved is True
    assert cc.parse_shell_descriptors(insertion.text) == ()


def test_no_shell_injection_via_argument_substitution():
    source = _md(_frontmatter("Before\n!`git status --short`\nAfter",
                              description="d"))
    command = cc.parse_command_source(source)
    injected = "note !`rm -rf /` and $2 `whoami`"
    rendered = cc.render_command_prompt(command, injected)
    assert [d.command for d in rendered.descriptors] == ["git status --short"]
    assert injected in rendered.text
    assert "rm -rf /" in rendered.text
    assert rendered.pending_descriptor_ids == (rendered.descriptors[0].id,)
    assert "pending" in rendered.to_dict()


def test_render_command_prompt_inserts_only_approved_output():
    command = cc.parse_command_source(_md(_frontmatter(
        "Summarize:\n!`git status --short`\nDone", description="d")))
    descriptor = cc.parse_shell_descriptors(command.template)[0]
    with pytest.raises(cc.ShellApprovalError):
        cc.render_command_prompt(command, "args",
                                 outputs={descriptor.id: " M file.py"})
    rendered = cc.render_command_prompt(
        command, "one 'two words'",
        outputs={descriptor.id: " M file.py"},
        approvals={descriptor.id: True})
    assert " M file.py" in rendered.text
    assert "!`git status --short`" not in rendered.text
    assert rendered.tokens == ("one", "two words")
    assert rendered.pending_descriptor_ids == ()

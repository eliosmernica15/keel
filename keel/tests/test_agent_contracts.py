"""W2.x P0 agent-contract tests (stdlib-only, no model/subprocess execution).

Covers W2.1, W2.2, W2.3, W2.4, W2.6, W2.8, W2.9 and W2.11:
nested markdown IDs, safe frontmatter, modes/fresh child context, built-ins,
step budget, launch-permission monotonicity, prompt composition, merge
semantics and plan-folder write containment.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from keel.agent_contracts import (
    BUILTIN_IDS,
    HIDDEN_BUILTIN_IDS,
    LIFECYCLE_CONTRACT,
    PLAN_AGENT_POLICY,
    PLAN_DIR,
    PROMPT_ORDER,
    AgentContractError,
    AgentDescriptor,
    ComposedPrompt,
    LifecycleContract,
    PermissionRule,
    PlanPolicy,
    StepDirective,
    StepTracker,
    SubagentLaunch,
    build_subagent_launch,
    builtin_agents,
    can_be_primary,
    can_be_subagent,
    decide_launch,
    descriptor_from_config,
    discover_agent_files,
    is_hidden,
    is_user_selectable,
    load_agents,
    merge_configs,
    merge_descriptors,
    model_role,
    normalize_mode,
    parse_agent_markdown,
    parse_permission,
    step_directive,
    agent_id_from_path,
    compose_system_prompt,
)


def R(action: str, resource: str, effect: str = "allow") -> dict:
    return {"action": action, "resource": resource, "effect": effect}


def _agent(agent_id: str, **over) -> AgentDescriptor:
    base = dict(
        id=agent_id,
        system=f"SYSTEM_FOR_{agent_id.replace('/', '_')}",
        mode="primary",
        permission={},
    )
    base.update(over)
    return descriptor_from_config(agent_id, base)


# ---------------------------------------------------------------------------
# W2.1 — markdown files, YAML frontmatter, nested IDs, safe parser
# ---------------------------------------------------------------------------

def test_agent_id_from_nested_path(tmp_path):
    root = tmp_path / ".keel" / "agents"
    assert agent_id_from_path(root / "team" / "reviewer.md", root) == "team/reviewer"
    assert agent_id_from_path(root / "lead.md", root) == "lead"
    assert agent_id_from_path(root / "team" / "deep" / "x.md", root) == "team/deep/x"
    # without an explicit root, a conventional .keel/agents prefix is stripped
    assert agent_id_from_path(Path(".keel/agents/team/reviewer.md")) == "team/reviewer"


def test_parse_markdown_fields_body_is_system_prompt():
    text = textwrap.dedent("""\
        ---
        description: Reviews code changes
        mode: subagent
        model: provider/model#variant
        steps: 4
        hidden: false
        web: true
        read_only: true
        permission:
          subagent:
            - deny: "*"
            - allow: reviewer
        ---
        You are a reviewer. Be concise.
        """)
    agent = parse_agent_markdown(text, agent_id="team/reviewer")
    assert agent.id == "team/reviewer"
    assert agent.description == "Reviews code changes"
    assert agent.mode == "subagent"
    assert agent.model == "provider/model#variant"
    assert agent.steps == 4
    assert agent.hidden is False
    assert agent.web is True and agent.read_only is True
    assert agent.system.strip() == "You are a reviewer. Be concise."
    rules = agent.permission["subagent"]
    assert any(r.effect == "deny" and r.resource == "*" for r in rules)
    assert any(r.effect == "allow" and r.resource == "reviewer" for r in rules)


def test_parse_nested_canonical_permission_frontmatter():
    text = textwrap.dedent("""\
        ---
        permission:
          allow:
            - action: read
              resource: "**"
              effect: allow
          deny:
            - action: write
              resource: "src/**"
              effect: deny
        ---
        body
        """)
    agent = parse_agent_markdown(text, agent_id="x")
    assert agent.permission["allow"][0] == PermissionRule("read", "**", "allow")
    assert agent.permission["deny"][0] == PermissionRule("write", "src/**", "deny")


@pytest.mark.parametrize("payload", [
    'description: !!python/object/apply:os.system ["echo pwnd"]',
    'description: !custom {a: 1}',
    'description: "${ENV_SECRET}"',
    'description: "$(rm -rf /)"',
    "description: `whoami`",
    "description: \"{{ evil }}\"",
    "defaults: &anchor\nref: *anchor",
])
def test_rejects_unsafe_yaml_tags_and_expressions(payload):
    with pytest.raises(AgentContractError):
        parse_agent_markdown(f"---\n{payload}\n---\nbody", agent_id="x")


def test_rejects_malformed_frontmatter():
    with pytest.raises(AgentContractError):
        parse_agent_markdown("no frontmatter here", agent_id="x")
    with pytest.raises(AgentContractError):
        parse_agent_markdown("---\nmode: primary\nno closing fence", agent_id="x")


def test_discover_and_load_nested_agents_from_global_and_project(tmp_path):
    global_root = tmp_path / "global" / ".keel" / "agents"
    project_root = tmp_path / "project" / ".keel" / "agents"
    (global_root / "team").mkdir(parents=True)
    (project_root / "team").mkdir(parents=True)
    (global_root / "team" / "reviewer.md").write_text(
        "---\nmodel: global-model\npermission:\n  allow:\n"
        '    - action: read\n      resource: "**"\n      effect: allow\n'
        "---\nglobal reviewer body\n", encoding="utf-8")
    (project_root / "team" / "reviewer.md").write_text(
        "---\nsteps: 2\npermission:\n  subagent:\n    - deny: evil\n"
        "---\nproject reviewer body\n", encoding="utf-8")
    (project_root / "solo.md").write_text(
        "---\nmode: all\n---\nsolo body\n", encoding="utf-8")

    found = {agent_id_from_path(p, project_root) for p in discover_agent_files(project_root)}
    assert found == {"team/reviewer", "solo"}

    agents = load_agents(global_root, project_root, include_builtins=False)
    assert set(agents) == {"team/reviewer", "solo"}
    reviewer = agents["team/reviewer"]
    assert reviewer.model == "global-model"       # project did not set model
    assert reviewer.steps == 2                    # project scalar applied
    assert reviewer.system.strip() == "project reviewer body"
    # permission rules append: global rule first, project rule second
    assert [r.resource for r in reviewer.permission["allow"]] == ["**"]
    assert [r.resource for r in reviewer.permission["subagent"]] == ["evil"]
    assert agents["solo"].mode == "all"


# ---------------------------------------------------------------------------
# W2.2 — modes and fresh-context child sessions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("mode", "primary", "sub"), [
    ("primary", True, False),
    ("subagent", False, True),
    ("all", True, True),
])
def test_modes(mode, primary, sub):
    assert normalize_mode(mode) == mode
    assert can_be_primary(mode) is primary
    assert can_be_subagent(mode) is sub
    assert can_be_primary(_agent("x", mode=mode).mode) is primary


def test_invalid_mode_rejected():
    with pytest.raises(AgentContractError):
        normalize_mode("superuser")


def test_subagent_launch_fresh_context_and_own_permissions():
    parent = _agent("parent", permission={
        "subagent": (PermissionRule("subagent", "team/reviewer", "allow"),)})
    child = _agent("team/reviewer", mode="subagent", system="REVIEWER_SYSTEM",
                   permission={
                       "allow": (PermissionRule("read", "**", "allow"),),
                       "subagent": (PermissionRule("subagent", "*", "deny"),)})
    launch = build_subagent_launch(
        parent, child, prompt="review the diff",
        parent_history=["PARENT_HISTORY_SENTINEL: secret context"])

    assert isinstance(launch, SubagentLaunch)
    assert launch.launch_decision == "allow"
    assert launch.lifecycle.fresh_context is True
    assert launch.lifecycle.inherits_parent_history is False
    assert launch.history == ()                     # parent history dropped
    assert launch.descriptor.permission == child.permission
    assert launch.descriptor.permission["subagent"] == child.permission["subagent"]

    ctx = launch.build_context(
        provider_base_prompt="PROVIDER_BASE",
        project_instructions=["PROJECT_RULE"],
        skills=["SKILL_REVIEW"], references=["REF_DOC"])
    assert "REVIEWER_SYSTEM" in ctx.text
    assert "PROJECT_RULE" in ctx.text and "SKILL_REVIEW" in ctx.text
    assert "REF_DOC" in ctx.text
    assert "PROVIDER_BASE" not in ctx.text           # agent system replaced it
    assert "PARENT_HISTORY_SENTINEL" not in ctx.text
    assert LIFECYCLE_CONTRACT.strip()[:40] in ctx.text


# ---------------------------------------------------------------------------
# W2.3 — built-ins, hidden maintenance agents
# ---------------------------------------------------------------------------

def test_builtin_set_and_user_selectability():
    builtins = builtin_agents()
    assert BUILTIN_IDS <= set(builtins)
    assert HIDDEN_BUILTIN_IDS <= set(builtins)
    for hidden_id in HIDDEN_BUILTIN_IDS:
        assert is_hidden(builtins[hidden_id]) is True
        assert is_user_selectable(builtins[hidden_id]) is False
    for visible_id in ("build", "plan", "general", "explore"):
        assert is_hidden(builtins[visible_id]) is False
    for primary_id in ("build", "plan", "general"):
        assert is_user_selectable(builtins[primary_id]) is True
    # explore is a subagent-only helper, so it is not a primary pick
    assert is_user_selectable(builtins["explore"]) is False
    assert model_role(builtins["title"]) == "title"
    assert model_role(builtins["summary"]) == "summarizer"
    assert model_role(builtins["compaction"]) == "summarizer"
    # factory returns independent copies
    builtins["build"].system = "MUTATED"
    assert builtin_agents()["build"].system != "MUTATED"


def test_general_cannot_launch_further_subagents():
    general = builtin_agents()["general"]
    rules = general.permission["subagent"]
    assert decide_launch(rules, "reviewer") == "deny"
    assert decide_launch(rules, "*") == "deny"


def test_explore_is_read_only_including_web():
    explore = builtin_agents()["explore"]
    assert explore.read_only is True and explore.web is True
    allowed = [r for group in explore.permission.values() for r in group
               if r.effect == "allow"]
    assert allowed
    assert all(r.action in ("read", "webfetch", "websearch", "glob", "grep")
               for r in allowed)
    assert not any(r.action in ("write", "edit", "bash", "shell", "mutate")
                   for r in allowed)


def test_hidden_builtins_deny_all_except_their_job():
    for hidden_id in HIDDEN_BUILTIN_IDS:
        agent = builtin_agents()[hidden_id]
        denies = [r for group in agent.permission.values() for r in group
                  if r.effect == "deny"]
        assert any(r.resource == "*" for r in denies)
        assert can_be_subagent(agent.mode) is False or is_hidden(agent)


# ---------------------------------------------------------------------------
# W2.4 — steps limit, forced-summary final step, reset on new input
# ---------------------------------------------------------------------------

def test_step_boundary_removes_tools_and_forces_summary():
    tracker = StepTracker(3)
    assert tracker.peek().tools_available is True
    assert tracker.advance().is_final is False       # step 1
    assert tracker.advance().is_final is False       # step 2
    final = tracker.advance()                        # step 3 == max
    assert isinstance(final, StepDirective)
    assert final.step == 3 and final.max_steps == 3
    assert final.is_final is True
    assert final.tools_available is False
    assert final.must_summarize is True
    assert "summar" in final.instruction.lower()
    assert "tool" in final.instruction.lower()


def test_single_step_is_final_immediately():
    directive = step_directive(max_steps=1, step=1)
    assert directive.is_final and not directive.tools_available
    assert StepTracker(1).peek().is_final is True


def test_new_user_input_resets_step_count():
    tracker = StepTracker(2)
    tracker.advance()
    tracker.advance()
    assert tracker.advance().is_final is True
    tracker.reset()                                  # new user turn
    assert tracker.step == 0
    assert tracker.peek().tools_available is True
    assert tracker.advance().is_final is False


def test_invalid_step_budgets_rejected():
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            StepTracker(bad)
    assert StepTracker(None).peek().is_final is False


# ---------------------------------------------------------------------------
# W2.6 — launch permissions: parent rules, monotonic deny, independent child
# ---------------------------------------------------------------------------

def test_launch_deny_cannot_be_overridden_by_allow():
    rules = [
        PermissionRule("subagent", "*", "allow"),
        PermissionRule("subagent", "reviewer", "deny"),
    ]
    assert decide_launch(rules, "reviewer") == "deny"
    assert decide_launch(rules, "build") == "allow"
    parent = _agent("p", permission={"subagent": tuple(rules)})
    assert can_be_primary("all") and parent.id == "p"


def test_launch_default_ask_and_ask_precedence():
    assert decide_launch([], "anything") == "ask"
    rules = [PermissionRule("subagent", "reviewer", "allow")]
    assert decide_launch(rules, "reviewer") == "allow"
    assert decide_launch(rules, "other") == "ask"
    rules.append(PermissionRule("subagent", "other", "ask"))
    assert decide_launch(rules, "other") == "ask"


def test_launch_rules_append_with_global_before_agent_and_stay_monotonic():
    merged = merge_configs(
        {"permission": {"subagent": [R("subagent", "*", "allow")]}},
        {"permission": {"subagent": [R("subagent", "evil", "deny")]}},
    )
    rules = parse_permission(merged["permission"])["subagent"]
    assert [(r.effect, r.resource) for r in rules] == [
        ("allow", "*"), ("deny", "evil")]
    assert decide_launch(rules, "evil") == "deny"
    assert decide_launch(rules, "safe") == "allow"


# ---------------------------------------------------------------------------
# W2.8 — system replaces provider base prompt, project context preserved
# ---------------------------------------------------------------------------

def test_system_replaces_provider_base_but_preserves_project_context():
    agent = _agent("x", system="AGENT_SYSTEM")
    composed = compose_system_prompt(
        agent,
        provider_base_prompt="PROVIDER_BASE",
        project_instructions=["PROJECT_INSTRUCTION"],
        skills=["SKILL_A", "SKILL_B"],
        references=["REFERENCE_A"],
        lifecycle="LIFECYCLE_TEXT",
    )
    assert isinstance(composed, ComposedPrompt)
    assert composed.base_source == "agent"
    assert composed.order == PROMPT_ORDER
    assert "PROVIDER_BASE" not in composed.text
    for expected in ("AGENT_SYSTEM", "PROJECT_INSTRUCTION", "SKILL_A",
                     "SKILL_B", "REFERENCE_A", "LIFECYCLE_TEXT"):
        assert expected in composed.text
    assert composed.text.index("AGENT_SYSTEM") < composed.text.index("SKILL_A")


def test_no_agent_system_keeps_provider_base_and_skills():
    agent = _agent("x", system=None)
    composed = compose_system_prompt(
        agent, provider_base_prompt="PROVIDER_BASE",
        project_instructions=["PROJECT_INSTRUCTION"], skills=["SKILL_A"])
    assert composed.base_source == "provider"
    assert "PROVIDER_BASE" in composed.text
    assert "PROJECT_INSTRUCTION" in composed.text
    assert "SKILL_A" in composed.text


# ---------------------------------------------------------------------------
# W2.9 — merge semantics: scalars replace, maps merge, rules append
# ---------------------------------------------------------------------------

def test_merge_configs_semantics():
    base = {
        "model": "old-model",
        "description": "base description",
        "tools": {"read": True, "write": False},
        "permission": {
            "allow": [R("read", "**")],
            "deny": [R("write", "*")],
        },
    }
    overlay = {
        "model": "new-model",
        "tools": {"write": True, "shell": False},
        "permission": {
            "allow": [R("webfetch", "domain:**")],
            "subagent": [R("subagent", "*", "deny")],
        },
    }
    out = merge_configs(base, overlay)
    assert out["model"] == "new-model"
    assert out["description"] == "base description"
    assert out["tools"] == {"read": True, "write": True, "shell": False}
    perms = parse_permission(out["permission"])
    assert [r.resource for r in perms["allow"]] == ["**", "domain:**"]
    assert len(perms["deny"]) == 1 and perms["deny"][0].action == "write"
    assert len(perms["subagent"]) == 1
    assert perms["subagent"][0].effect == "deny"
    # inputs not mutated
    assert base["model"] == "old-model"
    assert overlay["tools"] == {"write": True, "shell": False}


def test_merge_descriptors_replaces_scalar_merges_maps_appends_rules():
    base = _agent("x", model="old", tools={"read": True, "write": False},
                  permission={"allow": (PermissionRule("read", "**", "allow"),)})
    overlay = _agent("x", model="new", steps=3,
                     tools={"write": True, "shell": False},
                     permission={"allow": (PermissionRule("webfetch", "domain:**", "allow"),)})
    merged = merge_descriptors(base, overlay)
    assert merged.model == "new"
    assert merged.steps == 3
    assert merged.tools == {"read": True, "write": True, "shell": False}
    assert [r.resource for r in merged.permission["allow"]] == ["**", "domain:**"]


# ---------------------------------------------------------------------------
# W2.11 — plan agent write containment, shell stays permission-controlled
# ---------------------------------------------------------------------------

def test_plan_folder_containment(tmp_path):
    policy = PlanPolicy()
    assert PLAN_DIR == ".keel/plans"
    assert policy.permits_write(".keel/plans/design.md")
    assert policy.permits_write(".keel/plans/nested/spec.md")
    absolute = str(tmp_path / ".keel" / "plans" / "absolute.md").replace("\\", "/")
    assert policy.permits_write(absolute)
    assert not policy.permits_write("src/app.py")
    assert not policy.permits_write(".keel/plans/../../secret.md")
    assert not policy.permits_write("C:/repo/.keel/plans/../app.py")
    assert not policy.permits_write(".keel/plans/app.py")   # not a plan file


def test_plan_agent_policy_descriptor_only_allows_plan_files():
    permission = PLAN_AGENT_POLICY.permission_config()
    allow = parse_permission(permission)["allow"]
    assert allow
    assert all(r.action in ("write", "edit", "create") for r in allow)
    assert all(r.resource.startswith(PLAN_DIR + "/") for r in allow)
    assert PLAN_AGENT_POLICY.shell_rules() == ()            # no shell widening
    plan = builtin_agents()["plan"]
    assert plan.permission == parse_permission(permission)
    assert not any(r.action in ("bash", "shell") for group in plan.permission.values()
                   for r in group if r.effect == "allow")


def test_lifecycle_contract_is_snapshot_only():
    lifecycle = LifecycleContract(fresh_context=True, inherits_parent_history=False)
    assert lifecycle.fresh_context is True
    assert lifecycle.inherits_parent_history is False
    assert "fresh" in LIFECYCLE_CONTRACT.lower()

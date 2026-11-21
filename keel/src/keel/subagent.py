"""keel.subagent — minimal Task-tool implementation (Spec: delegation).

Design constraints, deliberately tight for this slice:

- depth 1: subagents cannot call Task themselves (task tool removed from the
  subagent allowlist);
- the child shares the parent's model, executor, rules, hooks, MCP manager,
  transcript and event stream; events are tagged with `parent_tool_use_id`;
- the child sees the parent's *final summary only* — the parent never receives
  the raw subagent transcript;
- the child runs `bare` (no CLAUDE.md re-injection; the child already lives
  inside the parent's context);
- the child's cap is parent.subagent_max_turns (default 5).
"""

from __future__ import annotations

from .hooks import fire
from .session import ALL_TOOLS, Session, SessionConfig


def run_subagent(*, parent: Session, prompt: str,
                 parent_tool_use_id: str):
    sub_config = SessionConfig(
        cwd=parent.config.cwd,
        state_root=parent.config.state_root,
        bare=True,
        permission_mode=parent.config.permission_mode,
        session_id=parent.config.session_id,
        model=parent.config.model,
        max_turns=parent.config.subagent_max_turns,
        interactive=parent.config.interactive,
        seed=parent.config.seed + 1,
        parent_tool_use_id=parent_tool_use_id,
        tool_allowlist=tuple(n for n in ALL_TOOLS if n != "Task"),
        # F1: the child inherits the parent's approval gate verbatim —
        # a subagent never gets a weaker gate than its caller.
        approval_decider=parent.config.approval_decider,
        approval_audit=parent.config.approval_audit,
    )
    sub = Session(
        model_client=parent.model,
        executor=parent.executor,
        config=sub_config,
        rules=parent._rules_raw,
        clock=parent.clock,
        rng=parent.rng,
        fs=parent.fs,
        hooks=parent.hooks,
        mcp=parent.mcp,
    )
    if parent.hooks:
        fire(parent.hooks, "SubagentStart", {
            "session_id": parent.config.session_id,
            "cwd": parent.config.cwd,
            "parent_tool_use_id": parent_tool_use_id,
            "prompt": prompt,
        })
    try:
        return sub.run(prompt)
    finally:
        if parent.hooks:
            fire(parent.hooks, "SubagentStop", {
                "session_id": parent.config.session_id,
                "cwd": parent.config.cwd,
                "parent_tool_use_id": parent_tool_use_id,
            })

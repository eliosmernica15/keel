"""keel.session — the headless turn loop (Phase 1 vertical slice).

prompt in → init event → model turn → permission-gated tool call(s) →
tool result(s) → final answer → one result envelope + transcript.
"""

from __future__ import annotations

import json
from typing import Callable
from dataclasses import dataclass, field

from . import events as ev
from .context import (Budget, CompactionState, THRESHOLD_NOTE,
                      estimate_tokens, select_preserved)
from .fakes import VirtualClock
from .instructions import build_attachment, discover, notes_attachment
from .permissions import (MODE_DONT_ASK, dont_ask_tools, evaluate,
                          Decision, manifest_tools, normalize_mode, parse_rules)
from .hooks import fire
from .safety import tier2_check
from .toolresult import Persist, machine_error, render_failure, render_success
from .transcript import TranscriptWriter

SUMMARY_PROMPT = (
    "You are compacting a coding session. Summarise the dropped messages "
    "losslessly enough for work to continue: decisions made, files touched, "
    "errors seen, open TODOs. Be terse. Output only the summary.\n\n"
    "Dropped messages:\n")

ALL_TOOLS = ["read_file", "write_file", "edit_file", "glob", "grep",
             "run_shell", "Task", "send_to_bot",
             "create_task", "update_task", "list_tasks", "save_file",
             "ask_user"]

TOOL_SCHEMAS = [
    {"name": "read_file", "description": "Read a text file from disk.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write a text file to disk.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Exact-match edit of a text file.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_string": {"type": "string"},
                                     "new_string": {"type": "string"}},
                      "required": ["path", "old_string", "new_string"]}},
    {"name": "glob", "description": "List files matching a glob.",
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
    {"name": "grep", "description": "Search file contents (regex).",
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"},
                                     "root": {"type": "string"}},
                      "required": ["pattern"]}},
    {"name": "run_shell", "description": "Run a shell command and return its output.",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"},
                                     "shell": {"type": "string",
                                               "enum": ["posix", "powershell", "cmd"]}},
                      "required": ["command"]}},
    {"name": "Task", "description": "Delegate a bounded sub-task to a subagent and receive its final summary. The subagent inherits the current tool allowlist minus Task itself.",
     "input_schema": {"type": "object",
                      "properties": {"description": {"type": "string",
                                                      "description": "short title for the subtask"},
                                     "prompt": {"type": "string",
                                                "description": "the full task for the subagent to perform"}},
                      "required": ["prompt"]}},
    {"name": "send_to_bot", "description": "Send a message or task to another agent in the fleet and receive its reply. The receiving agent runs with its own provider, model and permissions; none of your permissions transfer. Depth cap: 2 nested delegations; circular delegation is refused.",
      "input_schema": {"type": "object",
                       "properties": {"bot_slug": {"type": "string",
                                                   "description": "fleet id (slug) of the receiving agent, e.g. 'sage'"},
                                      "message": {"type": "string",
                                                  "description": "the task or question to hand off"},
                                      "task_id": {"type": "string",
                                                  "description": "optional Fleet task id this delegation is linked to (kept on both sides and on the task's history)"}},
                       "required": ["bot_slug", "message"]}},
    {"name": "create_task", "description": "Create a tracked task in the Fleet task list. You can assign it to yourself, unassigned, or another agent by id. Returns the task id.",
      "input_schema": {"type": "object",
                       "properties": {"title": {"type": "string",
                                                "description": "short title of the task"},
                                      "description": {"type": "string",
                                                      "description": "what done looks like"},
                                      "priority": {"type": "string",
                                                   "enum": ["low", "normal", "high"]},
                                      "assignee": {"type": "string",
                                                   "description": "fleet id of the agent to assign; omit for yourself, or 'unassigned'"}},
                       "required": ["title"]}},
    {"name": "update_task", "description": "Update the status, progress (0-100) or note of a task you created or are assigned to. Status moves through pending | in_progress | completed | failed | cancelled.",
      "input_schema": {"type": "object",
                       "properties": {"task_id": {"type": "string"},
                                      "status": {"type": "string",
                                                 "enum": ["pending", "in_progress",
                                                          "completed", "failed",
                                                          "cancelled"]},
                                      "progress": {"type": "integer",
                                                   "minimum": 0,
                                                   "maximum": 100},
                                      "note": {"type": "string"}},
                       "required": ["task_id"]}},
    {"name": "list_tasks", "description": "List tasks. Defaults to tasks assigned to you; pass assigned_to='all' for everything, or another agent's id.",
      "input_schema": {"type": "object",
                       "properties": {"assigned_to": {"type": "string"},
                                      "status": {"type": "string",
                                                 "enum": ["pending", "in_progress",
                                                          "completed", "failed",
                                                          "cancelled"]},
                                      "limit": {"type": "integer",
                                                "minimum": 1,
                                                "maximum": 25}},
                       "required": []}},
    {"name": "ask_user", "description": "Ask the operator a question mid-turn and wait for their answer (max 5 minutes). Use for real decisions only — which framework, which approach, the user's actual preference — never for trivia. Renders as a pop-up with clickable options and free text. If the operator doesn't answer, you get a refusal and must proceed without operator input.",
      "input_schema": {"type": "object",
                       "properties": {"question": {"type": "string",
                                                   "description": "one focused, self-contained question"},
                                      "options": {"type": "array",
                                                  "items": {"type": "string"},
                                                  "description": "up to 6 short clickable answers; omit to let the operator type freely"}},
                       "required": ["question"]}},
    {"name": "save_file", "description": "Save a deliverable into your Fleet Library. Stored under your agent, organised by optional task. Returns the file id. Text content is UTF-8; set encoding='base64' for binary (images, archives).",
      "input_schema": {"type": "object",
                       "properties": {"filename": {"type": "string"},
                                      "content": {"type": "string"},
                                      "encoding": {"type": "string",
                                                   "enum": ["utf8", "base64"]},
                                      "mime": {"type": "string"},
                                      "task_id": {"type": "string"}},
                       "required": ["filename", "content"]}},
]


@dataclass
class SessionConfig:
    cwd: str
    state_root: str
    bare: bool = True
    permission_mode: str = "default"
    # cooperative cancellation: set by operator "Stop"; the agentic loop
    # checks it between model round-trips and before tool execution
    cancel_event: object | None = None
    session_id: str = ""
    model: str = "keel-fake-1"
    max_turns: int = 10
    interactive: bool = False
    seed: int = 0
    context_window: int = 128_000
    reserved_output: int = 8_192
    auto_compact: bool = True
    local_command: str | None = None
    parent_tool_use_id: str | None = None
    tool_allowlist: tuple[str, ...] | None = None
    subagent_max_turns: int = 5
    notes_attachment: str | None = None
    history_attachment: str | None = None
    extra_attachment: str | None = None   # Fleet group briefs etc.
    # F1 (Fleet approvals): opaque decider consultable at the tool boundary.
    # Only a `consent_required` verdict may be converted; every other Tier-1
    # outcome stays exactly as the evaluator produced it.
    approval_decider: "Callable[[dict], object] | None" = None
    # F1 (Fleet approvals): outcome hook, invoked for fleet-sourced decisions
    # only. Signature: ({tool_name, tool_input, source, reason_type,
    # matched_rule, outcome}) -> None. Never raises into the session.
    approval_audit: "Callable[[dict], None] | None" = None
    # F3 (Fleet collaboration): delegation chain for the Fleet send_to_bot
    # tool — ids of the agents that delegated into this turn, oldest first.
    delegation_chain: tuple = ()


@dataclass
class RunOutcome:
    events: list[dict]
    envelope: dict
    transcript_path: str
    permission_denials: list[dict] = field(default_factory=list)


def _schema_for(name: str) -> dict:
    return next(t for t in TOOL_SCHEMAS if t["name"] == name)


def _model_usage_payload(model: str, usage) -> dict:
    if usage is None:
        return {}
    return {
        model: {
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "cacheReadInputTokens": usage.cache_read_input_tokens,
            "cacheCreationInputTokens": usage.cache_creation_input_tokens,
            "webSearchRequests": 0,
            "costUSD": 0,
            "contextWindow": 0,
            "maxOutputTokens": 0,
            "thinkingTokens": usage.thinking_tokens,
            "canonicalModel": model,
            "provider": "configured-provider",
            "costBasis": "unknown",
        }
    }


class Session:
    def __init__(self, *, model_client: Any, executor: Any,
                 config: SessionConfig,
                 rules: tuple[list[str], list[str], list[str]] = ([], [], []),
                 clock: VirtualClock | None = None,
                 rng: Any = None,
                 fs: Any = None,
                 hooks: list | None = None,
                 mcp: Any = None):
        self.model = model_client
        self.executor = executor
        self.config = config
        self.clock = clock or VirtualClock()
        self.rng = rng
        self.fs = fs
        self.hooks = list(hooks) if hooks else []
        self.mcp = mcp
        self.allowed_tools = tuple(config.tool_allowlist or ALL_TOOLS)
        self._rules_raw = tuple(rules)
        self.deny_rules, diag1 = parse_rules("deny", rules[0])
        self.ask_rules, diag2 = parse_rules("ask", rules[1])
        self.allow_rules, diag3 = parse_rules("allow", rules[2])
        self.rule_diagnostics = diag1 + diag2 + diag3
        self.ids = ev.Ids(rng)
        if not config.session_id:
            config.session_id = self.ids.session_id()
        self.persist = Persist(self._session_dir(), fs)
        self.budget = Budget(context_window=config.context_window,
                             reserved_output=config.reserved_output)
        self.compaction = CompactionState()
        self.safety_stops = 0

    def _session_dir(self) -> str:
        import os

        from .transcript import project_slug
        return os.path.join(self.config.state_root, "projects",
                            project_slug(self.config.cwd), self.config.session_id)

    def _transcript_path(self) -> str:
        from .transcript import project_slug
        import os
        return os.path.join(self.config.state_root, "projects",
                            project_slug(self.config.cwd),
                            f"{self.config.session_id}.jsonl")

    def _run_task(self, *, prompt: str, description: str,
                  tool_use_id: str) -> dict:
        """Delegate to an inline subagent; return a rendered tool_result dict."""
        from .subagent import run_subagent
        from .toolresult import render_success, render_failure

        outcome = run_subagent(parent=self,
                               prompt=prompt or description,
                               parent_tool_use_id=tool_use_id)
        if self._event_sink is not None:
            self._event_sink.extend(outcome.events)
        sub_envelope = outcome.envelope
        failures = [e for e in outcome.events
                    if e.get("subtype") == "permission_denied"
                    or e.get("subtype") == "compact_boundary"]
        denials = len(outcome.permission_denials)
        text = sub_envelope.get("result") or "(no final subagent message)"
        if sub_envelope.get("subtype") != "success":
            rendered = render_failure(
                tool_use_id,
                machine_error(
                    f"subagent failed ({sub_envelope.get('subtype')}): "
                    f"{text}"),
                self.persist)
        else:
            body = (f"<subagent_output>\n{text}\n"
                    f"[turns={sub_envelope.get('num_turns')} "
                    f"denials={denials}]\n</subagent_output>")
            rendered = render_success(
                tool_use_id,
                {"subagent": description,
                 "turns": sub_envelope.get("num_turns"),
                 "denials": denials},
                body, self.persist)
        return rendered

    def _maybe_compact(self, messages: list[dict], emit) -> list[dict]:
        """Compact once if over budget. All-or-nothing: never partial."""
        selection = select_preserved(messages, self.budget)
        if selection is None:
            return messages
        t0 = self.clock.monotonic()
        try:
            summary_blocks = self.model.complete(
                [{"role": "user", "content":
                  SUMMARY_PROMPT
                  + json.dumps(selection.dropped, default=str,
                               ensure_ascii=False)}],
                [])
        except Exception:
            summary_blocks = [{"type": "text", "text": "summary unavailable"}]
        summary = "".join(
            b.get("text", "")
            for b in summary_blocks if b.get("type") == "text"
        ).strip() or "summary unavailable"

        logical_parent = self.ids.event_uuid()
        summary_message = {
            "role": "user",
            "isCompactSummary": True,
            "content": f"<isCompactSummary>\n{summary}\n</isCompactSummary>",
            "uuid": logical_parent,
        }
        preserved_uuids = [m["uuid"] for m in selection.preserved
                           if m.get("uuid")]
        self.compaction.cumulative_dropped_tokens += selection.dropped_tokens
        self.compaction.compaction_count += 1
        post_tokens = estimate_tokens([summary_message] + selection.preserved)
        duration_ms = int((self.clock.monotonic() - t0) * 1000)
        boundary = ev.compact_boundary(
            session_id=self.config.session_id,
            uuid=self.ids.event_uuid(),
            timestamp=self.clock.now_iso(),
            pre_tokens=selection.pre_tokens,
            post_tokens=post_tokens,
            cumulative_dropped=self.compaction.cumulative_dropped_tokens,
            duration_ms=duration_ms,
            preserved_head=selection.preserved[0]["uuid"],
            preserved_tail=selection.preserved[-1]["uuid"],
            preserved_uuids=preserved_uuids,
            logical_parent=logical_parent,
            trigger="auto")
        emit(boundary, dict(boundary))
        if self.compaction.thrash_detected:
            self.compaction.disabled = True
            self.compaction.disable_reason = THRESHOLD_NOTE
            emit(ev.system_informational(
                text=THRESHOLD_NOTE,
                session_id=self.config.session_id,
                uuid=self.ids.event_uuid(),
                timestamp=self.clock.now_iso(),
                level="warn"),
                {"type": "system", "subtype": "informational",
                 "content": THRESHOLD_NOTE,
                 "sessionId": self.config.session_id})
        return [summary_message] + list(selection.preserved)

    def run(self, prompt) -> RunOutcome:  # str or list[block] (text/image blocks)
        mode = normalize_mode(self.config.permission_mode)
        events: list[dict] = []
        self._event_sink = events
        denials: list[dict] = []
        writer = TranscriptWriter(self._transcript_path(), self.fs)
        t0 = self.clock.monotonic()

        def emit(event: dict, transcript_entry: dict | None = None) -> None:
            events.append(event)
            writer.write(transcript_entry if transcript_entry is not None else event)

        # MCP: start approved servers eagerly so the manifest is complete
        mcp_statuses: list[dict] = []
        mcp_schemas: list[dict] = []
        if self.mcp is not None:
            try:
                mcp_statuses = self.mcp.start_all()
            except Exception:
                mcp_statuses = []
            mcp_schemas = self.mcp.tool_schemas()
        mcp_names = [s["name"] for s in mcp_schemas]

        builtin_enabled = {t for t in self.allowed_tools
                           if t in {t2["name"] for t2 in TOOL_SCHEMAS}}
        mcp_kept = list(mcp_names)  # mcp names are always provisioned; rules govern
        all_schemas = {t["name"]: t for t in TOOL_SCHEMAS
                       if t["name"] in builtin_enabled}
        all_schemas.update({s["name"]: s for s in mcp_schemas})

        tools = manifest_tools([t for t in builtin_enabled] + mcp_kept,
                               self.deny_rules)
        if mode == MODE_DONT_ASK:
            tools = dont_ask_tools(tools, self.allow_rules)
        init = ev.system_init(
            cwd=self.config.cwd,
            session_id=self.config.session_id,
            model=self.config.model,
            permission_mode=mode,
            tools=tools,
            uuid=self.ids.event_uuid(),
            timestamp=self.clock.now_iso(),
            mcp_servers=mcp_statuses,
        )
        emit(init, {"type": "system", "subtype": "init",
                    "sessionId": self.config.session_id,
                    "uuid": init["uuid"], "cwd": self.config.cwd,
                    "tools": tools, "model": self.config.model})
        writer.write({"type": "permission-mode", "permissionMode": mode,
                      "sessionId": self.config.session_id})

        messages: list[dict] = [{"role": "user", "content": prompt,
                                 "uuid": self.ids.event_uuid()}]
        attachment_parts: list[str] = []
        attachment_sources: list[str] = []
        if not self.config.bare:
            paths = discover(self.config.cwd)
            if paths:
                attachment_parts.append(build_attachment(paths))
                attachment_sources += [str(p) for p in paths]
        if self.config.notes_attachment:
            attachment_parts.append(self.config.notes_attachment)
            attachment_sources.append("fleet_notes")
        if self.config.history_attachment:
            attachment_parts.append(self.config.history_attachment)
            attachment_sources.append("fleet_history")
        if self.config.extra_attachment:
            attachment_parts.append(self.config.extra_attachment)
            attachment_sources.append("fleet_extra")
        if attachment_parts:
            combined = "\n\n".join(p.rstrip("\n") for p in attachment_parts)
            if isinstance(prompt, list):
                new_content: object = ([{"type": "text",
                                         "text": combined + "\n\n---\n\n"}]
                                        + list(prompt))
            else:
                new_content = combined + "\n\n---\n\n" + prompt
            messages[0] = {
                "role": "user",
                "content": new_content,
                "uuid": messages[0]["uuid"],
            }
            writer.write({"type": "attachment",
                          "kind": "context",
                          "sources": attachment_sources,
                          "sessionId": self.config.session_id})
        writer.write({"type": "user", "message": {"role": "user",
                                                  "content": prompt},
                      "uuid": messages[0]["uuid"],
                      "sessionId": self.config.session_id})
        tool_schemas = [all_schemas[t] for t in tools]
        self.budget = Budget(context_window=self.config.context_window,
                             reserved_output=self.config.reserved_output)
        self.compaction = CompactionState()
        num_turns = 0
        final_text = None
        stop_reason = "end_turn"
        subtype = "success"
        terminal_reason = "completed"

        while True:
            cancel_ev = getattr(self.config, "cancel_event", None)
            if cancel_ev is not None and cancel_ev.is_set():
                envelope = ev.result(subtype="success",
                                     session_id=self.config.session_id,
                                     uuid=self.ids.event_uuid(),
                                     timestamp=self.clock.now_iso(),
                                     num_turns=num_turns,
                                     duration_ms=int((self.clock.monotonic() - t0) * 1000),
                                     duration_api_ms=0, stop_reason=None,
                                     terminal_reason="cancelled",
                                     result_text=None, model=self.config.model,
                                     permission_denials=denials,
                                     errors=[],
                                     local_command=self.config.local_command,
                                     safety_stops=self.safety_stops)
                envelope["timestamp"] = self.clock.now_iso()
                emit(envelope, {"type": "cost-state",
                                "sessionId": self.config.session_id,
                                "totalCostUsd": 0.0})
                writer.close()
                return RunOutcome(events, envelope, writer.path, denials)
            if self.config.auto_compact and not self.compaction.disabled:
                messages = self._maybe_compact(messages, emit)
            try:
                blocks = self.model.complete(messages, tool_schemas)
            except Exception as exc:
                # operator Stop mid-round: don't treat it as a provider
                # error — route back through the loop-top check, which
                # builds the cancelled envelope and closes the transcript
                from .providers.base import TurnCancelled
                if isinstance(exc, TurnCancelled):
                    continue
                from .providers.base import ProviderError
                category = getattr(exc, "category", "unknown")
                retryable = bool(getattr(exc, "retryable", False))
                if not isinstance(exc, ProviderError):
                    category = f"internal:{type(exc).__name__}"
                errors = [{"code": "provider_error",
                           "category": category,
                           "message": str(exc)[:2000],
                           "retryable": retryable}]
                envelope = ev.result(
                    subtype="error_during_execution",
                    session_id=self.config.session_id,
                    uuid=self.ids.event_uuid(),
                    timestamp=self.clock.now_iso(),
                    num_turns=num_turns,
                    duration_ms=int((self.clock.monotonic() - t0) * 1000),
                    duration_api_ms=0, stop_reason=None,
                    terminal_reason="provider_error",
                    result_text=None, model=self.config.model,
                    permission_denials=denials,
                    errors=errors,
                    local_command=self.config.local_command,
                    safety_stops=self.safety_stops)
                emit(envelope, {"type": "cost-state",
                                "sessionId": self.config.session_id,
                                "totalCostUsd": 0.0})
                writer.close()
                return RunOutcome(events, envelope, writer.path, denials)
            tool_blocks = [b for b in blocks if b.get("type") == "tool_use"]
            text_blocks = [b for b in blocks if b.get("type") == "text"]

            # one assistant event per content block, shared message id
            message_id = self.ids.message_id()
            request_id = f"req_{self.ids._gen()}"
            ts = self.clock.now_iso()
            tool_use_ids: dict[int, str] = {}
            for idx, block in enumerate(blocks):
                out_block = dict(block)
                if block.get("type") == "tool_use":
                    # provider-assigned ids win; fall back to a generated one
                    tool_use_ids[idx] = block.get("id") or \
                        f"call_{self.ids._gen()}"
                    out_block = {
                        "type": "tool_use",
                        "id": tool_use_ids[idx],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    }
                content = [out_block]
                emit(ev.assistant_message(
                    message_id=message_id, request_id=request_id,
                    session_id=self.config.session_id,
                    uuid=self.ids.event_uuid(), timestamp=ts,
                    model=self.config.model, content=content,
                    stop_reason=None,
                    parent_tool_use_id=self.config.parent_tool_use_id,
                ), {"type": "assistant", "message": {"id": message_id,
                                                     "content": content},
                    "sessionId": self.config.session_id,
                    "parentToolUseId": self.config.parent_tool_use_id})

            if tool_blocks:
                num_turns += 1
            if num_turns > self.config.max_turns:
                subtype, is_err = "error_max_turns", True
                stop_reason, terminal_reason = None, "max_turns"
                errors = [{"code": "max_turns", "category": "resource_exhausted",
                           "message": f"turn cap of {self.config.max_turns} exceeded",
                           "retryable": False}]
                envelope = ev.result(subtype=subtype, session_id=self.config.session_id,
                                     uuid=self.ids.event_uuid(),
                                     timestamp=self.clock.now_iso(),
                                     num_turns=num_turns, duration_ms=int(
                                         (self.clock.monotonic() - t0) * 1000),
                                     duration_api_ms=0, stop_reason=stop_reason,
                                     terminal_reason=terminal_reason,
                                     result_text=None, model=self.config.model,
                                     permission_denials=denials,
                                     errors=errors,
                                     local_command=self.config.local_command,
                                     safety_stops=self.safety_stops)
                envelope["timestamp"] = self.clock.now_iso()
                emit(envelope, {"type": "cost-state", "sessionId": self.config.session_id,
                                "totalCostUsd": 0.0})
                writer.close()
                return RunOutcome(events, envelope, writer.path, denials)

            tool_results = []
            block_indices = [i for i, b in enumerate(blocks)
                             if b.get("type") == "tool_use"]
            cancel_ev = getattr(self.config, "cancel_event", None)
            if cancel_ev is not None and cancel_ev.is_set():
                # skip all tool execution; the loop-top check turns this
                # into the cancelled envelope on the next iteration
                continue
            for block_idx in block_indices:
                block = blocks[block_idx]
                tool_use_id = tool_use_ids[block_idx]
                tool_input = block.get("input", {})
                hook_blocked_reason: str | None = None

                def hook_emit(kind, item, event_name, tuid):
                    if kind == "started":
                        emit(ev.hook_started(
                            session_id=self.config.session_id,
                            uuid=self.ids.event_uuid(),
                            timestamp=self.clock.now_iso(),
                            hook_name=item.name, hook_event=event_name,
                            tool_use_id=tuid))
                    else:
                        emit(ev.hook_response(
                            session_id=self.config.session_id,
                            uuid=self.ids.event_uuid(),
                            timestamp=self.clock.now_iso(),
                            hook_name=item.name, hook_event=event_name,
                            tool_use_id=tuid, exit_code=item.exit_code,
                            duration_ms=item.duration_ms,
                            verdict=item.verdict))

                if self.hooks is not None and self.hooks:
                    hook_payload = {
                        "session_id": self.config.session_id,
                        "cwd": self.config.cwd,
                        "tool_name": block["name"],
                        "tool_input": tool_input,
                        "tool_use_id": tool_use_id,
                        "permission_mode": mode,
                        "stop_hook_active": False,
                        "transcript_path": writer.path,
                    }
                    pre = fire(self.hooks, "PreToolUse", hook_payload,
                               emit=hook_emit)
                    if pre.denied or (pre.ask and not self.config.interactive):
                        hook_blocked_reason = pre.reason() or "hook blocked"
                    elif pre.updated_input is not None:
                        tool_input = pre.updated_input
                        block = {**block, "input": tool_input}

                if hook_blocked_reason is not None:
                    meta = [{"id": tool_use_id,
                             "permission_decision": {"decision": "deny",
                                                     "source": "hook",
                                                     "reason_type": "policy"}}]
                    rendered = render_failure(
                        tool_use_id,
                        machine_error(f"hook blocked: {hook_blocked_reason}"),
                        self.persist)
                    tool_result_content = rendered["content"]
                    tool_use_result = rendered["toolUseResult"]
                    is_error = True
                    decision = None
                else:
                    decision = evaluate(
                        tool_name=block["name"], tool_input=tool_input,
                        rules=(self.deny_rules, self.ask_rules,
                               self.allow_rules),
                        mode=mode, interactive=self.config.interactive)
                    if (decision.decision != "allow"
                            and decision.reason_type == "consent_required"
                            and self.config.approval_decider is not None):
                        # F1: the one verdict Fleet may convert — a standing
                        # refusal because there was nobody to ask. Deny
                        # rules, hooks and Tier 2 are never revisited.
                        try:
                            decision = self.config.approval_decider({
                                "tool_name": block["name"],
                                "tool_input": tool_input,
                                "tool_use_id": tool_use_id,
                            })
                        except Exception:
                            decision = Decision(
                                "deny", "fleet_error",
                                "approval decider failed; refused closed",
                                "fleet", None, None, False)
                    meta = [decision.record_meta(tool_use_id)]
                    if decision.decision == "allow":
                        if block["name"] == "Task":
                            rendered = self._run_task(
                                prompt=str(tool_input.get("prompt") or ""),
                                description=str(tool_input.get("description")
                                               or "subagent task")[:120],
                                tool_use_id=tool_use_id)
                            tool_result_content = rendered["content"]
                            tool_use_result = rendered["toolUseResult"]
                            is_error = rendered["isError"]
                        else:
                            tier2 = tier2_check(block["name"], tool_input)
                            if not tier2.allowed:
                                rendered = render_failure(
                                    tool_use_id,
                                    machine_error(f"tier-2 refused: {tier2.reason}"),
                                    self.persist)
                                self.safety_stops += 1
                                tool_result_content = rendered["content"]
                                tool_use_result = rendered["toolUseResult"]
                                is_error = True
                            else:
                                try:
                                    if block["name"].startswith("mcp__") and \
                                            self.mcp is not None:
                                        emit_step = getattr(self.executor,
                                                            "_emit_step", None)
                                        if callable(emit_step):
                                            try:
                                                emit_step({"name": block["name"],
                                                           "status": "running",
                                                           "detail": str(tool_input)[:180]})
                                            except Exception:
                                                pass  # steps are best-effort
                                        ok, text = self.mcp.call(
                                            block["name"], tool_input)
                                        if callable(emit_step):
                                            try:
                                                emit_step({"name": block["name"],
                                                           "status": "done" if ok
                                                           else "error",
                                                           "detail": str(text)[:180]})
                                            except Exception:
                                                pass
                                        if ok:
                                            rendered = render_success(
                                                tool_use_id,
                                                {"mcp_server_tool":
                                                    block["name"],
                                                 "is_error": False},
                                                text, self.persist)
                                        else:
                                            rendered = render_failure(
                                                tool_use_id, machine_error(text),
                                                self.persist)
                                    else:
                                        inline, typed = self.executor.invoke(
                                            block["name"], tool_input)
                                        rendered = render_success(
                                            tool_use_id, typed, inline,
                                            self.persist)
                                except Exception as exc:  # tool crash -> is_error
                                    rendered = render_failure(
                                        tool_use_id, machine_error(str(exc)),
                                        self.persist)
                                tool_result_content = rendered["content"]
                                tool_use_result = rendered["toolUseResult"]
                                is_error = rendered["isError"]
                    else:
                        msg = f"permission denied: {decision.reason}"
                        rendered = render_failure(tool_use_id,
                                                  machine_error(msg),
                                                  self.persist)
                        denials.append({"tool_name": block["name"],
                                        "tool_use_id": tool_use_id,
                                        "tool_input": tool_input})
                        deny_event = ev.system_permission_denied(
                            tool_name=block["name"], tool_use_id=tool_use_id,
                            tool_input=tool_input,
                            decision_reason_type=decision.reason_type,
                            decision_reason=decision.reason,
                            session_id=self.config.session_id,
                            uuid=self.ids.event_uuid(),
                            timestamp=self.clock.now_iso())
                        emit(deny_event, {"type": "system",
                                          "subtype": "permission_denied",
                                          "sessionId": self.config.session_id,
                                          "uuid": deny_event["uuid"]})
                        tool_result_content = rendered["content"]
                        tool_use_result = rendered["toolUseResult"]
                        is_error = True
                if (self.config.approval_audit is not None
                        and decision is not None
                        and getattr(decision, "source", None) == "fleet"):
                    try:
                        outcome = ("executed" if decision.decision == "allow"
                                   and not is_error else
                                   "error" if decision.decision == "allow" else
                                   "refused")
                        self.config.approval_audit({
                            "tool_name": block["name"],
                            "tool_input": tool_input,
                            "source": "fleet",
                            "reason_type": decision.reason_type,
                            "matched_rule": decision.matched_rule,
                            "outcome": outcome,
                        })
                    except Exception:
                        pass  # audit must never break a turn

                if self.hooks is not None and self.hooks:
                    post_payload = {
                        "session_id": self.config.session_id,
                        "cwd": self.config.cwd,
                        "tool_name": block["name"],
                        "tool_input": tool_input,
                        "tool_use_id": tool_use_id,
                        "permission_mode": mode,
                        "stop_hook_active": False,
                        "transcript_path": writer.path,
                        "tool_response_excerpt": (tool_result_content or "")[:512],
                    }
                    fire(self.hooks, "PostToolUse", post_payload,
                         emit=hook_emit)
                emit(ev.user_tool_result(
                    tool_use_id=tool_use_id, content=tool_result_content,
                    session_id=self.config.session_id,
                    uuid=self.ids.event_uuid(),
                    timestamp=self.clock.now_iso(),
                    tool_use_result=tool_use_result,
                    tool_result_meta=meta,
                    parent_tool_use_id=self.config.parent_tool_use_id),
                    {"type": "user", "toolUseResult": tool_use_result,
                     "sessionId": self.config.session_id,
                     "parentToolUseId": self.config.parent_tool_use_id})
                tool_results.append({"type": "tool_result",
                                     "tool_use_id": tool_use_id,
                                     "tool_name": block["name"],
                                     "content": tool_result_content})

            if tool_blocks:
                messages.append({"role": "assistant", "content": blocks,
                                 "uuid": self.ids.event_uuid()})
                messages.append({"role": "user", "content": tool_results,
                                 "uuid": self.ids.event_uuid()})
                continue

            final_text = "".join(b.get("text", "") for b in text_blocks)
            break

        duration_ms = int((self.clock.monotonic() - t0) * 1000)
        client_usage = getattr(self.model, "total_usage", None)
        usage_tokens = None
        if client_usage is not None:
            usage_tokens = {
                "input_tokens": client_usage.input_tokens,
                "output_tokens": client_usage.output_tokens,
                "cache_read_input_tokens": client_usage.cache_read_input_tokens,
                "cache_creation_input_tokens":
                    client_usage.cache_creation_input_tokens,
            }
        envelope = ev.result(
            subtype="success", session_id=self.config.session_id,
            uuid=self.ids.event_uuid(), timestamp=self.clock.now_iso(),
            num_turns=num_turns, duration_ms=duration_ms, duration_api_ms=0,
            stop_reason="end_turn", terminal_reason=terminal_reason,
            result_text=final_text, model=self.config.model,
            permission_denials=denials,
            usage_tokens=usage_tokens,
            model_usage=_model_usage_payload(self.config.model, client_usage)
            or None,
            safety_stops=self.safety_stops,
            local_command=self.config.local_command)
        emit(envelope, {"type": "cost-state", "sessionId": self.config.session_id,
                        "totalCostUsd": 0.0})
        writer.close()
        return RunOutcome(events, envelope, writer.path, denials)

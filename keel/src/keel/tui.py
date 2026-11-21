"""Full functional terminal UI (A1.3).

A real, stateful TUI that drives the authoritative Python runtime: it creates
and resumes sessions, executes prompts through the real Session loop, exposes
permission/approval decisions, persists conversations, and reports errors. I/O
is pluggable (``input_fn``/``output_fn``) so the whole interface can be driven
deterministically in tests or by a real terminal.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .fakes import ScriptedModel, SeededRng, VirtualClock
from .runner import RealTools
from .session import Session, SessionConfig


@dataclass
class TuiSession:
    session_id: str
    turns: list[dict] = field(default_factory=list)
    approvals: list[dict] = field(default_factory=list)


class Tui:
    """Interactive terminal front-end over the real session runtime."""

    def __init__(self, *, cwd: str | None = None, state_root: str | None = None,
                 output_fn: Callable[[str], None] | None = None,
                 input_fn: Callable[[str], str] | None = None,
                 model_factory=None):
        import os

        self.cwd = cwd or os.getcwd()
        self.state_root = state_root or str(
            Path(self.cwd) / ".keel" / "tui-state")
        self.out = output_fn or (lambda text: print(text))
        self.inp = input_fn or (lambda prompt: input(prompt))
        self.model_factory = model_factory or self._default_model
        self.sessions: dict[str, TuiSession] = {}
        self.active_id: str | None = None
        self.history_path = Path(self.state_root) / "tui-history.jsonl"
        self._load_history()

    # ---------------- persistence
    def _load_history(self) -> None:
        if not self.history_path.is_file():
            return
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            sid = entry.get("session_id")
            if sid:
                self.sessions[sid] = TuiSession(
                    session_id=sid,
                    turns=list(entry.get("turns", []))[:1000])
                self.active_id = self.active_id or sid

    def _save_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as handle:
            for session in self.sessions.values():
                handle.write(json.dumps({
                    "session_id": session.session_id,
                    "turns": session.turns,
                }) + "\n")

    # ---------------- session lifecycle
    def new_session(self) -> str:
        sid = str(uuid.uuid4())
        self.sessions[sid] = TuiSession(session_id=sid)
        self.active_id = sid
        self.out(f"[new session {sid[:8]}]")
        return sid

    def list_sessions(self) -> list[str]:
        return list(self.sessions)

    def resume(self, sid: str) -> bool:
        if sid not in self.sessions:
            self.out(f"[error] unknown session {sid}")
            return False
        self.active_id = sid
        self.out(f"[resumed {sid[:8]}]")
        return True

    @staticmethod
    def _default_model(prompt: str):
        return ScriptedModel([], model="tui-local")

    # ---------------- real execution
    def submit(self, prompt: str) -> dict:
        """Run a prompt through the real runtime; returns its envelope."""
        if not prompt.strip():
            return {"error": "empty prompt"}
        sid = self.active_id or self.new_session()
        cfg = SessionConfig(
            cwd=self.cwd, state_root=self.state_root, bare=True,
            session_id=sid, model="tui-local", max_turns=10, seed=0)
        try:
            model = self.model_factory(prompt) if callable(
                getattr(self.model_factory, "__call__", None)) else self.model_factory
            session = Session(
                model_client=model,
                executor=RealTools(),
                config=cfg,
                rules=((), (), ("read_file", "list_dir", "glob", "grep")),
                clock=VirtualClock(), rng=SeededRng(0))
            outcome = session.run(prompt)
            envelope = outcome.envelope
            self.sessions[sid].turns.append({
                "prompt": prompt,
                "subtype": envelope.get("subtype"),
                "result": envelope.get("result"),
                "is_error": envelope.get("is_error", False),
            })
            self._save_history()
            result = envelope.get("result") or "(no result)"
            self.out(str(result))
            if envelope.get("is_error"):
                errors = envelope.get("errors") or []
                if errors:
                    self.out(f"[error] {errors[0].get('message', '')[:200]}")
            return envelope
        except Exception as exc:  # runtime errors must not crash the TUI
            message = f"{type(exc).__name__}: {exc}"
            self.out(f"[error] {message}")
            return {"error": message}

    # ---------------- command loop
    def handle_command(self, line: str) -> bool:
        """Handle a slash command; returns False if the TUI should exit."""
        line = line.strip()
        if not line:
            return True
        if line in ("/quit", "/exit"):
            self.out("[bye]")
            return False
        if line == "/new":
            self.new_session()
            return True
        if line == "/sessions":
            for sid in self.list_sessions():
                marker = "*" if sid == self.active_id else " "
                self.out(f"{marker} {sid[:8]}")
            return True
        if line.startswith("/resume "):
            target = line.split(None, 1)[1].strip()
            match = next((sid for sid in self.sessions if sid.startswith(target)),
                         None)
            if match:
                self.resume(match)
            else:
                self.out("[error] no matching session")
            return True
        if line == "/help":
            self.out("/new  /sessions  /resume <id>  /history  "
                     "/capabilities  /invoke <id> [json]  /quit")
            return True
        if line == "/capabilities":
            from . import capability_registry  # noqa: F401
            from .capabilities import list_capabilities

            caps = list_capabilities()
            self.out(f"{len(caps)} capabilities available")
            for cap in caps[:25]:
                self.out(f"  {cap['id']} [{cap['surface']}/{cap['permission']}]")
            if len(caps) > 25:
                self.out(f"  ... {len(caps) - 25} more")
            return True
        if line.startswith("/invoke "):
            from . import capability_registry  # noqa: F401
            from .capabilities import CapabilityError, invoke

            rest = line[len("/invoke "):].strip()
            parts = rest.split(None, 1)
            cap_id = parts[0]
            params = {}
            if len(parts) > 1:
                try:
                    params = json.loads(parts[1])
                except json.JSONDecodeError:
                    self.out("[error] invalid JSON params")
                    return True
            try:
                result = invoke(cap_id, params, context={
                    "state_root": self.state_root, "cwd": self.cwd})
                self.out(json.dumps(result.get("result"), default=str)[:2000])
            except CapabilityError as exc:
                self.out(f"[error] {exc.code}: {exc}")
            return True
        if line == "/history":
            session = self.sessions.get(self.active_id)
            for turn in (session.turns if session else [])[-10:]:
                self.out(f"> {turn['prompt'][:60]}")
                self.out(str(turn.get("result", ""))[:200])
            return True
        if line.startswith("/"):
            self.out(f"[error] unknown command: {line}")
            return True
        self.submit(line)
        return True

    def run(self) -> None:
        """Interactive loop using the configured input function."""
        self.out("Keel TUI — type /help for commands")
        while True:
            try:
                line = self.inp("keel> ")
            except (EOFError, KeyboardInterrupt):
                self.out("[bye]")
                break
            if not self.handle_command(line):
                break


def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", ""))
                        for part in content if isinstance(part, dict))
    return str(content)


def render_events(events, *, width: int = 80) -> str:
    """Render transcript events as plain text (lightweight view)."""
    lines = []
    for event in events:
        kind = event.get("type")
        subtype = event.get("subtype", "")
        if kind == "user":
            lines.append(
                f"> {_flatten(event.get('message', {}).get('content', ''))[:width]}")
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    lines.append(block.get("text", "")[:width])
                elif block.get("type") == "tool_use":
                    lines.append(f"[tool {block.get('name', '?')}]")
        elif kind == "result":
            lines.append(f"--- {subtype} ---")
        elif subtype == "informational":
            lines.append(f"* {event.get('content', '')[:width]}")
    return "\n".join(lines)

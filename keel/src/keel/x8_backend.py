"""keel.x8_backend -- additive backend contracts for the X8 UI/UX-depth set.

This module turns the 15 ``not_started`` X8 registry rows (X8.3 - X8.17) into
real, testable, stdlib-only backend behavior.  It deliberately implements
*contracts and services*, never widgets, stylesheets, animations, OS toasts,
native windows or any other frontend/visual component.  The purely visual
scope of each row is named in ``master-plan-v6-x8-backend-evidence.md``.

X8.1 (local component catalog) and X8.2 (design-token contract) are already
implemented in :mod:`keel.builder_contracts`; this module reuses that module as
the single source of truth for tokens/token validation (X8.14, X8.15) and the
test suite re-verifies those two contracts rather than duplicating them.

Design constraints (identical in spirit to ``builder_contracts.py``):

* standard library only; no network, subprocess, filesystem I/O, SQL,
  credential value or import-time side effect;
* no uuid / rng -- every id and fingerprint is a deterministic SHA-256 prefix
  of canonical JSON bytes;
* every input is validated, every output is immutable or freshly copied;
* typed errors fail closed.

The in-memory stores (layouts, activity, recovery, undo, displays) are pure
state holders: a lead can persist their deterministic ``to_dict()`` documents
through the existing settings store.  No file is ever written here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence

from keel.builder_contracts import (
    DEFAULT_TOKENS,
    TokenContractError,
    flatten_tokens,
    validate_tokens,
)


# ---------------------------------------------------------------------------
# shared helpers: canonical bytes, content hashes, typed errors
# ---------------------------------------------------------------------------


def canonical_bytes(value: Any) -> bytes:
    """Deterministic UTF-8 encoding used by every hash in this module."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class X8BackendError(ValueError):
    """Base class for every typed X8 backend failure."""


class LayoutError(X8BackendError):
    """A density / zoom / saved-layout document was invalid."""


class NotificationError(X8BackendError):
    """A notification or activity-feed operation was invalid."""


class ActionError(X8BackendError):
    """An actionable-notification command was not permitted."""


class TrayError(X8BackendError):
    """A tray snapshot or kill-switch command was invalid."""


class SelectionError(X8BackendError):
    """A text selection or selection action was invalid."""


class ThreadError(X8BackendError):
    """A thread outline / pin / jump / timeline index was invalid."""


class CompareError(X8BackendError):
    """A session-comparison input was invalid."""


class CitationError(X8BackendError):
    """A citation could not be validated or resolved."""


class DiffError(X8BackendError):
    """A diff / file-preview request was invalid."""


class RecoveryError(X8BackendError):
    """A draft checkpoint or recovery request was invalid."""


class UndoError(X8BackendError):
    """An undo transaction was unknown, duplicate or already undone."""


class ThemeError(X8BackendError):
    """A theme import/export or contrast request was invalid."""


class PreferenceError(X8BackendError):
    """An accessibility-preference override was invalid."""


class DisplayError(X8BackendError):
    """A display / window-position / dock document was invalid."""


class CopyDeckError(X8BackendError):
    """A copy-deck key, placeholder or coverage request was invalid."""


def _safe_path(value: Any) -> str:
    """Normalize a relative source path, rejecting traversal and abs paths."""
    if not isinstance(value, str) or not value.strip():
        raise CitationError("a source path is required")
    path = value.strip().replace("\\", "/")
    while "//" in path:
        path = path.replace("//", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path) \
            or ".." in path.split("/") or path.endswith("/"):
        raise CitationError(f"unsafe source path: {value!r}")
    return path


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


# ===========================================================================
# X8.3 -- density modes, per-pane zoom and saved layouts
# ===========================================================================


class DensityMode(str, Enum):
    COMPACT = "compact"
    COMFORTABLE = "comfortable"


ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
ZOOM_DEFAULT = 1.0
LAYOUT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def normalize_zoom(value: Any) -> float:
    """Clamp-free validation + 2-decimal quantization of a zoom factor."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LayoutError("zoom must be a number")
    zoom = float(value)
    if not math.isfinite(zoom) or not (ZOOM_MIN <= zoom <= ZOOM_MAX):
        raise LayoutError(f"zoom {value!r} outside [{ZOOM_MIN}, {ZOOM_MAX}]")
    return round(zoom, 2)


@dataclass(frozen=True)
class PaneZoom:
    pane: str
    zoom: float = ZOOM_DEFAULT

    def __post_init__(self) -> None:
        if not isinstance(self.pane, str) or not self.pane.strip():
            raise LayoutError("a pane id is required")
        object.__setattr__(self, "pane", self.pane.strip())
        object.__setattr__(self, "zoom", normalize_zoom(self.zoom))

    def to_dict(self) -> dict:
        return {"pane": self.pane, "zoom": self.zoom}


@dataclass(frozen=True)
class LayoutState:
    density: DensityMode = DensityMode.COMFORTABLE
    panes: tuple[PaneZoom, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "density", DensityMode(self.density))
        panes = tuple(self.panes)
        if any(not isinstance(p, PaneZoom) for p in panes):
            raise LayoutError("panes must contain PaneZoom entries")
        names = [p.pane for p in panes]
        if len(names) != len(set(names)):
            raise LayoutError("duplicate pane in layout")
        object.__setattr__(self, "panes", panes)

    def to_dict(self) -> dict:
        return {"density": self.density.value,
                "panes": [p.to_dict() for p in self.panes]}

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]


@dataclass(frozen=True)
class SavedLayout:
    name: str
    state: LayoutState

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not LAYOUT_NAME_RE.fullmatch(self.name):
            raise LayoutError(f"invalid saved-layout name: {self.name!r}")
        if not isinstance(self.state, LayoutState):
            raise LayoutError("a saved layout needs a LayoutState")

    def to_dict(self) -> dict:
        return {"name": self.name, "state": self.state.to_dict(),
                "fingerprint": self.fingerprint}

    @property
    def fingerprint(self) -> str:
        return content_hash(self.state.to_dict())[:16]


DEFAULT_LAYOUT = SavedLayout(
    "default", LayoutState(DensityMode.COMFORTABLE,
                           (PaneZoom("chat"), PaneZoom("dock"),
                            PaneZoom("sidebar"))))


class LayoutStore:
    """In-memory registry of saved layouts (no filesystem I/O)."""

    def __init__(self, initial: Sequence[SavedLayout] = ()) -> None:
        self._items: dict[str, SavedLayout] = {}
        for layout in initial:
            self.save(layout)

    def save(self, layout: SavedLayout) -> SavedLayout:
        if not isinstance(layout, SavedLayout):
            raise LayoutError("expected a SavedLayout")
        self._items[layout.name] = layout
        return layout

    def get(self, name: str) -> SavedLayout | None:
        return self._items.get(name)

    def remove(self, name: str) -> bool:
        return self._items.pop(name, None) is not None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def document(self) -> dict:
        docs = [self._items[name].to_dict() for name in self.names()]
        return {"schema_version": 1, "layouts": docs,
                "count": len(docs),
                "fingerprint": content_hash(docs)[:16]}


def validate_layout_state(state: LayoutState) -> bool:
    """Re-validate a layout state that was built without constructor checks."""
    if not isinstance(state, LayoutState):
        raise LayoutError("expected a LayoutState")
    _ = state.fingerprint
    return True


# ===========================================================================
# X8.4 -- notification center / activity feed with filters
# ===========================================================================


class NotificationKind(str, Enum):
    APPROVAL = "approval"
    JOB_RESULT = "job_result"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Notification:
    id: str
    kind: NotificationKind
    title: str
    body: str
    ref: str
    seq: int
    status: NotificationStatus = NotificationStatus.UNREAD

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", NotificationKind(self.kind))
        object.__setattr__(self, "status", NotificationStatus(self.status))
        for label, value in (("title", self.title), ("body", self.body)):
            if not isinstance(value, str) or not value.strip():
                raise NotificationError(f"a notification needs a {label}")
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq < 0:
            raise NotificationError("notification seq must be a non-negative int")

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind.value, "title": self.title,
                "body": self.body, "ref": self.ref, "seq": self.seq,
                "status": self.status.value}


@dataclass(frozen=True)
class NotificationFilter:
    kinds: frozenset[NotificationKind] = frozenset()
    statuses: frozenset[NotificationStatus] = frozenset()
    query: str = ""
    limit: int = 100

    def __post_init__(self) -> None:
        try:
            kinds = frozenset(NotificationKind(k) for k in self.kinds)
            statuses = frozenset(NotificationStatus(s) for s in self.statuses)
        except ValueError as exc:
            raise NotificationError(str(exc)) from exc
        try:
            limit = _positive_int(self.limit, "limit")
        except ValueError as exc:
            raise NotificationError(str(exc)) from exc
        object.__setattr__(self, "kinds", kinds)
        object.__setattr__(self, "statuses", statuses)
        object.__setattr__(self, "query", str(self.query).strip().lower())
        object.__setattr__(self, "limit", limit)


class ActivityFeed:
    """Deterministic notification store, filter and unread accounting."""

    def __init__(self) -> None:
        self._items: dict[str, Notification] = {}
        self._seq = 0

    def emit(self, kind: NotificationKind | str, title: str, body: str,
             ref: str = "") -> Notification:
        kind = NotificationKind(kind)
        self._seq += 1
        ident = content_hash([kind.value, title, body, ref, self._seq])[:12]
        item = Notification(id=ident, kind=kind, title=title, body=body,
                            ref=ref, seq=self._seq)
        self._items[ident] = item
        return item

    def get(self, ident: str) -> Notification:
        try:
            return self._items[ident]
        except KeyError as exc:
            raise NotificationError(f"unknown notification {ident!r}") from exc

    def mark_read(self, ident: str) -> Notification:
        item = self.get(ident)
        updated = Notification(
            id=item.id, kind=item.kind, title=item.title, body=item.body,
            ref=item.ref, seq=item.seq, status=NotificationStatus.READ)
        self._items[ident] = updated
        return updated

    def archive(self, ident: str) -> Notification:
        item = self.get(ident)
        updated = Notification(
            id=item.id, kind=item.kind, title=item.title, body=item.body,
            ref=item.ref, seq=item.seq, status=NotificationStatus.ARCHIVED)
        self._items[ident] = updated
        return updated

    def unread_count(self) -> int:
        return sum(1 for item in self._items.values()
                   if item.status is NotificationStatus.UNREAD)

    def query(self, filt: NotificationFilter | None = None) -> tuple[Notification, ...]:
        filt = filt or NotificationFilter()
        if not isinstance(filt, NotificationFilter):
            raise NotificationError("expected a NotificationFilter")
        hits = [
            item for item in self._items.values()
            if (not filt.kinds or item.kind in filt.kinds)
            and (not filt.statuses or item.status in filt.statuses)
            and (not filt.query or filt.query in " ".join(
                (item.title, item.body, item.ref)).lower())
        ]
        hits.sort(key=lambda n: (-n.seq, n.id))
        return tuple(hits[:filt.limit])

    def document(self) -> dict:
        items = [n.to_dict() for n in self.query(NotificationFilter(limit=10 ** 6))]
        return {"schema_version": 1, "notifications": items,
                "unread": self.unread_count(),
                "fingerprint": content_hash(items)[:16]}


# ===========================================================================
# X8.5 -- actionable OS notifications (plan/validate the action; never render)
# ===========================================================================


class NotificationAction(str, Enum):
    APPROVE = "approve"
    DENY = "deny"
    OPEN_TASK = "open_task"


#: Conservative defaults; a lead replaces these with detected OS capabilities.
ACTION_CAPABILITIES: dict[str, frozenset[NotificationAction]] = {
    "win32": frozenset(NotificationAction),
    "darwin": frozenset(NotificationAction),
    # Linux desktop notifications are not guaranteed to expose action buttons.
    "linux": frozenset({NotificationAction.OPEN_TASK}),
}


def supported_actions(platform: str,
                      capabilities: Mapping[str, frozenset[NotificationAction]]
                      = ACTION_CAPABILITIES) -> frozenset[NotificationAction]:
    return capabilities.get(platform, frozenset())


@dataclass(frozen=True)
class ActionableNotification:
    notification_id: str
    actions: tuple[NotificationAction, ...]
    approval_id: str = ""
    task_ref: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.notification_id, str) or not self.notification_id.strip():
            raise ActionError("an actionable notification needs its source id")
        try:
            actions = tuple(dict.fromkeys(NotificationAction(a) for a in self.actions))
        except ValueError as exc:
            raise ActionError(str(exc)) from exc
        if not actions:
            raise ActionError("at least one notification action is required")
        if ({NotificationAction.APPROVE, NotificationAction.DENY} & set(actions)
                and not self.approval_id.strip()):
            raise ActionError("approve/deny needs a pending approval id")
        if NotificationAction.OPEN_TASK in actions and not self.task_ref.strip():
            raise ActionError("open_task needs a task reference")
        object.__setattr__(self, "actions", actions)

    def to_dict(self) -> dict:
        return {"notification_id": self.notification_id,
                "actions": [a.value for a in self.actions],
                "approval_id": self.approval_id, "task_ref": self.task_ref}


@dataclass(frozen=True)
class ActionCommand:
    notification_id: str
    action: NotificationAction
    target: str
    platform: str
    supported: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", NotificationAction(self.action))

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"notification_id": self.notification_id,
                "action": self.action.value, "target": self.target,
                "platform": self.platform, "supported": self.supported}


def plan_notification_action(
        notification: ActionableNotification,
        action: NotificationAction | str,
        platform: str,
        capabilities: Mapping[str, frozenset[NotificationAction]]
        = ACTION_CAPABILITIES) -> ActionCommand:
    """Validate an OS-notification action and return a dispatch-ready command.

    Nothing is dispatched and no OS API is called: the native layer decides if
    and how to present the toast.  Unknown platforms fail closed.
    """
    if not isinstance(notification, ActionableNotification):
        raise ActionError("expected an ActionableNotification")
    action = NotificationAction(action)
    if action not in notification.actions:
        raise ActionError(f"action {action.value} is not offered by this notification")
    if action not in supported_actions(platform, capabilities):
        raise ActionError(f"platform {platform!r} does not support {action.value}")
    target = (notification.approval_id if action in
              (NotificationAction.APPROVE, NotificationAction.DENY)
              else notification.task_ref)
    return ActionCommand(notification_id=notification.notification_id,
                         action=action, target=target, platform=platform)


# ===========================================================================
# X8.6 -- tray snapshot + kill-switch command (no native window is created)
# ===========================================================================


class AgentStatus(str, Enum):
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"


@dataclass(frozen=True)
class AgentRun:
    agent_id: str
    status: AgentStatus
    task_ref: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise TrayError("an agent run needs an id")
        object.__setattr__(self, "status", AgentStatus(self.status))

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "status": self.status.value,
                "task_ref": self.task_ref}


@dataclass(frozen=True)
class ApprovalRef:
    approval_id: str
    title: str

    def __post_init__(self) -> None:
        if not isinstance(self.approval_id, str) or not self.approval_id.strip():
            raise TrayError("an approval needs an id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise TrayError("an approval needs a title")

    def to_dict(self) -> dict:
        return {"approval_id": self.approval_id, "title": self.title}


@dataclass(frozen=True)
class TraySnapshot:
    running_agents: tuple[str, ...]
    pending_approvals: tuple[ApprovalRef, ...]
    quick_ask_enabled: bool = True

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"running_agents": list(self.running_agents),
                "pending_approvals": [a.to_dict() for a in self.pending_approvals],
                "quick_ask_enabled": self.quick_ask_enabled}


def build_tray_snapshot(agents: Iterable[AgentRun],
                        approvals: Iterable[ApprovalRef],
                        quick_ask_enabled: bool = True) -> TraySnapshot:
    runs = tuple(agents)
    approval_list = tuple(approvals)
    if any(not isinstance(a, AgentRun) for a in runs):
        raise TrayError("agents must contain AgentRun entries")
    if any(not isinstance(a, ApprovalRef) for a in approval_list):
        raise TrayError("approvals must contain ApprovalRef entries")
    running = tuple(sorted({a.agent_id for a in runs
                            if a.status is AgentStatus.RUNNING}))
    pending = tuple(sorted(approval_list, key=lambda a: a.approval_id))
    return TraySnapshot(running, pending, bool(quick_ask_enabled))


@dataclass(frozen=True)
class KillSwitchCommand:
    agent_id: str
    reason: str
    requires_confirmation: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise TrayError("kill switch needs a target agent")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise TrayError("kill switch needs a reason")
        # Fail closed: a kill switch can never be marked auto-confirmed.
        if not self.requires_confirmation:
            raise TrayError("kill switch must require confirmation")

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "reason": self.reason,
                "requires_confirmation": self.requires_confirmation}


def kill_switch(agent_id: str, reason: str) -> KillSwitchCommand:
    return KillSwitchCommand(agent_id=agent_id, reason=reason)


def validate_kill_switch(command: KillSwitchCommand) -> bool:
    if not isinstance(command, KillSwitchCommand):
        raise TrayError("expected a KillSwitchCommand")
    _ = command.fingerprint
    return command.requires_confirmation


# ===========================================================================
# X8.7 -- selection actions: ask / add to context / save to vault
# ===========================================================================


class SelectionAction(str, Enum):
    ASK_ABOUT = "ask_about"
    ADD_TO_CONTEXT = "add_to_context"
    SAVE_TO_VAULT = "save_to_vault"


MAX_SELECTION_CHARS = 10_000
SELECTION_ACTION_TARGETS: dict[SelectionAction, str] = {
    SelectionAction.ASK_ABOUT: "agent:primary",
    SelectionAction.ADD_TO_CONTEXT: "context:main",
    SelectionAction.SAVE_TO_VAULT: "vault:notes",
}


@dataclass(frozen=True)
class TextSelection:
    text: str
    source_ref: str = ""
    start: int = 0
    end: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise SelectionError("a selection needs non-empty text")
        if len(self.text) > MAX_SELECTION_CHARS:
            raise SelectionError("selection exceeds the character limit")
        start = _positive_int_or_zero(self.start, "start")
        end = len(self.text) if self.end is None else self.end
        if isinstance(end, bool) or not isinstance(end, int) or end <= start \
                or end > len(self.text):
            raise SelectionError("invalid selection range")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"text": self.text, "source_ref": self.source_ref,
                "start": self.start, "end": self.end}


def _positive_int_or_zero(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SelectionError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class SelectionCommand:
    action: SelectionAction
    target: str
    selection: TextSelection

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", SelectionAction(self.action))
        if not isinstance(self.target, str) or not self.target.strip():
            raise SelectionError("a selection action needs a target")
        if not isinstance(self.selection, TextSelection):
            raise SelectionError("expected a TextSelection")

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"action": self.action.value, "target": self.target,
                "selection": self.selection.to_dict()}


def plan_selection_action(selection: TextSelection,
                          action: SelectionAction | str,
                          target: str = "") -> SelectionCommand:
    if not isinstance(selection, TextSelection):
        raise SelectionError("expected a TextSelection")
    action = SelectionAction(action)
    resolved = target.strip() or SELECTION_ACTION_TARGETS[action]
    return SelectionCommand(action=action, target=resolved, selection=selection)


def selection_document(command: SelectionCommand) -> dict:
    if not isinstance(command, SelectionCommand):
        raise SelectionError("expected a SelectionCommand")
    return {"schema_version": 1, "command": command.to_dict()}


# ===========================================================================
# X8.8 -- thread tools: outline, pins, jump-to-tool-call, timeline index
# ===========================================================================


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ThreadError("a tool call needs an id")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ThreadError("a tool call needs a name")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True)
class Message:
    id: str
    seq: int
    role: str
    text: str = ""
    heading: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ThreadError("a message needs an id")
        seq = _positive_int_or_zero_thread(self.seq, "seq")
        object.__setattr__(self, "seq", seq)
        calls = tuple(self.tool_calls)
        if any(not isinstance(c, ToolCall) for c in calls):
            raise ThreadError("tool_calls must contain ToolCall entries")
        object.__setattr__(self, "tool_calls", calls)

    def to_dict(self) -> dict:
        return {"id": self.id, "seq": self.seq, "role": self.role,
                "text": self.text, "heading": self.heading,
                "tool_calls": [c.to_dict() for c in self.tool_calls]}


def _positive_int_or_zero_thread(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ThreadError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class Pin:
    message_id: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, str) or not self.message_id.strip():
            raise ThreadError("a pin needs a message id")

    def to_dict(self) -> dict:
        return {"message_id": self.message_id, "note": self.note}


@dataclass(frozen=True)
class OutlineEntry:
    seq: int
    label: str
    kind: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "label": self.label, "kind": self.kind}


@dataclass(frozen=True)
class TimelineEntry:
    seq: int
    message_id: str
    role: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "message_id": self.message_id,
                "role": self.role}


@dataclass(frozen=True)
class ThreadIndex:
    messages: tuple[Message, ...]
    pins: tuple[Pin, ...]
    tool_calls: tuple[tuple[str, int, str], ...]
    outline: tuple[OutlineEntry, ...]

    def jump_to_tool_call(self, tool_call_id: str) -> int:
        for ident, seq, _name in self.tool_calls:
            if ident == tool_call_id:
                return seq
        raise ThreadError(f"unknown tool call {tool_call_id!r}")

    def timeline(self) -> tuple[TimelineEntry, ...]:
        return tuple(sorted(
            (TimelineEntry(m.seq, m.id, m.role) for m in self.messages),
            key=lambda e: e.seq))

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"messages": [m.to_dict() for m in self.messages],
                "pins": [p.to_dict() for p in self.pins],
                "tool_calls": [{"id": i, "seq": s, "name": n}
                               for i, s, n in self.tool_calls],
                "outline": [e.to_dict() for e in self.outline],
                "timeline": [e.to_dict() for e in self.timeline()]}


def build_thread_index(messages: Iterable[Message],
                       pins: Iterable[Pin] = ()) -> ThreadIndex:
    msgs = tuple(messages)
    pin_list = tuple(pins)
    if any(not isinstance(m, Message) for m in msgs):
        raise ThreadError("messages must contain Message entries")
    if any(not isinstance(p, Pin) for p in pin_list):
        raise ThreadError("pins must contain Pin entries")
    ids = [m.id for m in msgs]
    seqs = [m.seq for m in msgs]
    if len(ids) != len(set(ids)) or len(seqs) != len(set(seqs)):
        raise ThreadError("duplicate message id or seq in thread")
    known = set(ids)
    for pin in pin_list:
        if pin.message_id not in known:
            raise ThreadError(f"pin references unknown message {pin.message_id!r}")
    calls: list[tuple[str, int, str]] = []
    call_ids: set[str] = set()
    outline: list[OutlineEntry] = []
    for message in sorted(msgs, key=lambda m: m.seq):
        if message.heading.strip():
            outline.append(OutlineEntry(message.seq, message.heading.strip(), "heading"))
        for call in message.tool_calls:
            if call.id in call_ids:
                raise ThreadError(f"duplicate tool call {call.id!r}")
            call_ids.add(call.id)
            calls.append((call.id, message.seq, call.name))
            outline.append(OutlineEntry(message.seq, f"tool: {call.name}", "tool"))
    return ThreadIndex(msgs, pin_list, tuple(calls), tuple(outline))


# ===========================================================================
# X8.9 -- side-by-side session compare (two models/branches/before-after)
# ===========================================================================


@dataclass(frozen=True)
class Turn:
    seq: int
    role: str
    text: str

    def __post_init__(self) -> None:
        seq = _positive_int_or_zero_thread(self.seq, "turn seq")
        object.__setattr__(self, "seq", seq)

    def signature(self) -> tuple[str, str]:
        return (self.role, self.text)

    def to_dict(self) -> dict:
        return {"seq": self.seq, "role": self.role, "text": self.text}


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    model_id: str
    branch: str
    turns: tuple[Turn, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (("session_id", self.session_id),
                             ("model_id", self.model_id),
                             ("branch", self.branch)):
            if not isinstance(value, str) or not value.strip():
                raise CompareError(f"a session needs a {label}")
        turns = tuple(self.turns)
        if any(not isinstance(t, Turn) for t in turns):
            raise CompareError("turns must contain Turn entries")
        seqs = [t.seq for t in turns]
        if len(seqs) != len(set(seqs)):
            raise CompareError("duplicate turn seq in session")
        object.__setattr__(self, "turns", turns)

    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "model_id": self.model_id,
                "branch": self.branch, "turns": [t.to_dict() for t in self.turns]}


@dataclass(frozen=True)
class ComparisonReport:
    left_id: str
    right_id: str
    model_before: str
    model_after: str
    branch_before: str
    branch_after: str
    added_turns: tuple[int, ...]
    removed_turns: tuple[int, ...]
    changed_turns: tuple[int, ...]

    @property
    def model_changed(self) -> bool:
        return self.model_before != self.model_after

    @property
    def branch_changed(self) -> bool:
        return self.branch_before != self.branch_after

    @property
    def identical(self) -> bool:
        return not (self.model_changed or self.branch_changed
                    or self.added_turns or self.removed_turns
                    or self.changed_turns)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"left_id": self.left_id, "right_id": self.right_id,
                "model_before": self.model_before, "model_after": self.model_after,
                "branch_before": self.branch_before,
                "branch_after": self.branch_after,
                "model_changed": self.model_changed,
                "branch_changed": self.branch_changed,
                "added_turns": list(self.added_turns),
                "removed_turns": list(self.removed_turns),
                "changed_turns": list(self.changed_turns),
                "identical": self.identical}


def compare_sessions(left: SessionRecord, right: SessionRecord) -> ComparisonReport:
    if not isinstance(left, SessionRecord) or not isinstance(right, SessionRecord):
        raise CompareError("expected two SessionRecord values")
    before = {t.seq: t for t in left.turns}
    after = {t.seq: t for t in right.turns}
    added = tuple(sorted(set(after) - set(before)))
    removed = tuple(sorted(set(before) - set(after)))
    changed = tuple(sorted(seq for seq in set(before) & set(after)
                           if before[seq].signature() != after[seq].signature()))
    return ComparisonReport(left_id=left.session_id, right_id=right.session_id,
                            model_before=left.model_id, model_after=right.model_id,
                            branch_before=left.branch, branch_after=right.branch,
                            added_turns=added, removed_turns=removed,
                            changed_turns=changed)


def comparison_document(report: ComparisonReport) -> dict:
    if not isinstance(report, ComparisonReport):
        raise CompareError("expected a ComparisonReport")
    return {"schema_version": 1, "comparison": report.to_dict()}


# ===========================================================================
# X8.10 -- citation chips: resolve source file / page / line (no hover UI)
# ===========================================================================


@dataclass(frozen=True)
class Citation:
    path: str
    page: int | None = None
    line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _safe_path(self.path))
        for label, value in (("page", self.page), ("line", self.line),
                             ("end_line", self.end_line)):
            if value is not None and (isinstance(value, bool)
                                      or not isinstance(value, int) or value < 1):
                raise CitationError(f"{label} must be a positive int or None")
        if self.line is not None and self.end_line is not None \
                and self.end_line < self.line:
            raise CitationError("end_line must not precede line")

    @property
    def id(self) -> str:
        return content_hash(self.to_dict())[:12]

    def to_dict(self) -> dict:
        return {"path": self.path, "page": self.page, "line": self.line,
                "end_line": self.end_line}


@dataclass(frozen=True)
class CitationPreview:
    citation: Citation
    lines: tuple[str, ...]
    start_line: int
    total_lines: int

    @property
    def end_line(self) -> int:
        return self.start_line + len(self.lines) - 1 if self.lines else self.start_line

    @property
    def excerpt(self) -> str:
        return "\n".join(self.lines)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"citation": self.citation.to_dict(), "lines": list(self.lines),
                "start_line": self.start_line, "end_line": self.end_line,
                "total_lines": self.total_lines}


def resolve_citation(citation: Citation,
                     source_map: Mapping[str, Sequence[str]]) -> CitationPreview:
    if not isinstance(citation, Citation):
        raise CitationError("expected a Citation")
    if citation.path not in source_map:
        raise CitationError(f"citation source is not available: {citation.path}")
    lines = tuple(str(line) for line in source_map[citation.path])
    start = citation.line or 1
    if start > len(lines):
        raise CitationError("citation line is past end of source")
    end = min(citation.end_line or start + 6 - 1, len(lines))
    return CitationPreview(citation=citation, lines=lines[start - 1:end],
                           start_line=start, total_lines=len(lines))


# ===========================================================================
# X8.11 -- inline diff, file preview and open-in-dock action
# ===========================================================================


@dataclass(frozen=True)
class DiffRow:
    tag: str
    text: str
    old_no: int | None
    new_no: int | None


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    rows: tuple[DiffRow, ...]

    def to_dict(self) -> dict:
        return {"old_start": self.old_start, "old_count": self.old_count,
                "new_start": self.new_start, "new_count": self.new_count,
                "rows": [{"tag": r.tag, "text": r.text,
                          "old_no": r.old_no, "new_no": r.new_no}
                         for r in self.rows]}


@dataclass(frozen=True)
class DiffReport:
    path: str
    hunks: tuple[DiffHunk, ...]
    added: int
    removed: int

    @property
    def clean(self) -> bool:
        return not self.hunks

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"path": self.path, "hunks": [h.to_dict() for h in self.hunks],
                "added": self.added, "removed": self.removed,
                "clean": self.clean}


MAX_DIFF_LINES = 2000


def _split_lines(text: str) -> list[str]:
    if not isinstance(text, str):
        raise DiffError("diff input must be a string")
    return text.splitlines()


def line_diff(old: str, new: str, *, context: int = 3,
              path: str = "") -> DiffReport:
    """A real line-level diff with context hunks and original line numbers."""
    if isinstance(context, bool) or not isinstance(context, int) or context < 0:
        raise DiffError("context must be a non-negative integer")
    old_lines = _split_lines(old)
    new_lines = _split_lines(new)
    if len(old_lines) + len(new_lines) > MAX_DIFF_LINES:
        raise DiffError(f"diff exceeds {MAX_DIFF_LINES} lines")
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    rows: list[DiffRow] = []
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                rows.append(DiffRow(" ", old_lines[i1 + offset],
                                    i1 + offset + 1, j1 + offset + 1))
        else:
            for offset in range(i1, i2):
                rows.append(DiffRow("-", old_lines[offset], offset + 1, None))
                removed += 1
            for offset in range(j1, j2):
                rows.append(DiffRow("+", new_lines[offset], None, offset + 1))
                added += 1
    changes = [idx for idx, row in enumerate(rows) if row.tag != " "]
    ranges: list[tuple[int, int]] = []
    for idx in changes:
        start = max(0, idx - context)
        end = min(len(rows), idx + context + 1)
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    hunks: list[DiffHunk] = []
    for start, end in ranges:
        segment = rows[start:end]
        old_numbers = [r.old_no for r in segment if r.old_no is not None]
        new_numbers = [r.new_no for r in segment if r.new_no is not None]
        old_start = old_numbers[0] if old_numbers else max(0, (new_numbers[0] - 1)
                                                            if new_numbers else 0)
        new_start = new_numbers[0] if new_numbers else max(0, old_start - 1)
        hunks.append(DiffHunk(old_start, len(old_numbers),
                              new_start, len(new_numbers), tuple(segment)))
    return DiffReport(path=path, hunks=tuple(hunks), added=added, removed=removed)


def render_unified(report: DiffReport) -> str:
    if not isinstance(report, DiffReport):
        raise DiffError("expected a DiffReport")
    lines = [f"--- {report.path} (before)", f"+++ {report.path} (after)"]
    for hunk in report.hunks:
        lines.append(f"@@ -{hunk.old_start},{hunk.old_count} "
                     f"+{hunk.new_start},{hunk.new_count} @@")
        lines.extend(row.tag + row.text for row in hunk.rows)
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class FilePreview:
    path: str
    start_line: int
    end_line: int
    total_lines: int
    lines: tuple[str, ...]
    truncated: bool

    def to_dict(self) -> dict:
        return {"path": self.path, "start_line": self.start_line,
                "end_line": self.end_line, "total_lines": self.total_lines,
                "lines": list(self.lines), "truncated": self.truncated}


def build_file_preview(path: str, source_map: Mapping[str, Sequence[str]],
                       start_line: int | None = None,
                       end_line: int | None = None,
                       max_lines: int = 200) -> FilePreview:
    safe = _safe_path(path)
    total = _positive_int(max_lines, "max_lines")
    if safe not in source_map:
        raise DiffError(f"file is not available for preview: {safe}")
    source = tuple(str(line) for line in source_map[safe])
    start = 1 if start_line is None else _positive_int_or_zero_thread(start_line, "start_line")
    if start < 1 or start > max(1, len(source)):
        raise DiffError("preview start_line is out of range")
    end = min(len(source), end_line) if end_line is not None \
        else min(len(source), start + total - 1)
    if isinstance(end_line, bool) or (end_line is not None
                                      and (not isinstance(end_line, int) or end_line < start)):
        raise DiffError("preview end_line is out of range")
    end = max(start, end)
    truncated = end < len(source) or start > 1 or (end - start + 1) >= total
    return FilePreview(safe, start, end, len(source), source[start - 1:end], truncated)


@dataclass(frozen=True)
class OpenInDockAction:
    path: str
    start_line: int
    end_line: int
    label: str

    def to_dict(self) -> dict:
        return {"path": self.path, "start_line": self.start_line,
                "end_line": self.end_line, "label": self.label}


def open_in_dock(preview: FilePreview) -> OpenInDockAction:
    if not isinstance(preview, FilePreview):
        raise DiffError("expected a FilePreview")
    return OpenInDockAction(path=preview.path, start_line=preview.start_line,
                            end_line=preview.end_line,
                            label=f"Open {preview.path} in dock")


# ===========================================================================
# X8.12 -- crash recovery: draft checkpoint service (error boundary is UI)
# ===========================================================================


@dataclass(frozen=True)
class DraftSnapshot:
    session_id: str
    text: str
    cursor: int = 0
    seq: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise RecoveryError("a draft needs a session id")
        if not isinstance(self.text, str):
            raise RecoveryError("draft text must be a string")
        for label, value in (("cursor", self.cursor), ("seq", self.seq)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RecoveryError(f"{label} must be a non-negative integer")
        if self.cursor > len(self.text):
            raise RecoveryError("cursor is past end of draft")

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "text": self.text,
                "cursor": self.cursor, "seq": self.seq}


@dataclass(frozen=True)
class RecoveryResult:
    session_id: str
    restored: bool
    text: str
    cursor: int
    checkpoint_seq: int
    stale: bool = False

    def to_dict(self) -> dict:
        return {"session_id": self.session_id, "restored": self.restored,
                "text": self.text, "cursor": self.cursor,
                "checkpoint_seq": self.checkpoint_seq, "stale": self.stale}


class RecoveryStore:
    """Latest-wins checkpoint store; survives a renderer restart logically."""

    def __init__(self) -> None:
        self._latest: dict[str, DraftSnapshot] = {}

    def checkpoint(self, snapshot: DraftSnapshot) -> DraftSnapshot:
        if not isinstance(snapshot, DraftSnapshot):
            raise RecoveryError("expected a DraftSnapshot")
        current = self._latest.get(snapshot.session_id)
        if current is not None and current.seq > snapshot.seq:
            return current  # never overwrite a newer checkpoint with a stale one
        self._latest[snapshot.session_id] = snapshot
        return snapshot

    def recover(self, session_id: str,
                current_seq: int | None = None) -> RecoveryResult:
        if not isinstance(session_id, str) or not session_id.strip():
            raise RecoveryError("a session id is required")
        snapshot = self._latest.get(session_id)
        if snapshot is None:
            return RecoveryResult(session_id, False, "", 0, 0)
        stale = (current_seq is not None and snapshot.seq < current_seq)
        return RecoveryResult(session_id, True, snapshot.text, snapshot.cursor,
                              snapshot.seq, stale)

    def clear(self, session_id: str) -> bool:
        return self._latest.pop(session_id, None) is not None

    def session_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._latest))

    def document(self) -> dict:
        docs = [self._latest[s].to_dict() for s in self.session_ids()]
        return {"schema_version": 1, "checkpoints": docs,
                "fingerprint": content_hash(docs)[:16]}


# ===========================================================================
# X8.13 -- undo toast backend: transactional undo with compensating commands
# ===========================================================================


class DestructiveKind(str, Enum):
    ARCHIVE = "archive"
    DELETE = "delete"
    REVOKE = "revoke"


@dataclass(frozen=True)
class UndoableAction:
    action_id: str
    kind: DestructiveKind
    label: str
    inverse: tuple[str, ...]
    details: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", DestructiveKind(self.kind))
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise UndoError("an undoable action needs an id")
        if not isinstance(self.label, str) or not self.label.strip():
            raise UndoError("an undoable action needs a label")
        inverse = tuple(self.inverse)
        if not inverse or any(not isinstance(step, str) or not step.strip()
                              for step in inverse):
            raise UndoError("an undoable action needs compensating steps")

    def to_dict(self) -> dict:
        return {"action_id": self.action_id, "kind": self.kind.value,
                "label": self.label, "inverse": list(self.inverse),
                "details": self.details}


@dataclass(frozen=True)
class UndoResult:
    action_id: str
    kind: DestructiveKind
    commands: tuple[str, ...]
    undone: bool = True

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"action_id": self.action_id, "kind": self.kind.value,
                "commands": list(self.commands), "undone": self.undone}


def build_undo_action(kind: DestructiveKind | str, label: str,
                      inverse: Sequence[str], details: str = "") -> UndoableAction:
    kind = DestructiveKind(kind)
    base = content_hash([kind.value, label, list(inverse), details])[:12]
    return UndoableAction(base, kind, label, tuple(inverse), details)


class UndoStack:
    """Bounded fail-closed undo stack; the toast itself is frontend-only."""

    def __init__(self, max_size: int = 50) -> None:
        self._max_size = _positive_int(max_size, "max_size")
        self._pending: dict[str, UndoableAction] = {}
        self._done: set[str] = set()
        self._order: list[str] = []  # insertion order -> FIFO eviction

    def push(self, action: UndoableAction) -> str:
        if not isinstance(action, UndoableAction):
            raise UndoError("expected an UndoableAction")
        token = action.action_id
        suffix = 2
        while token in self._pending or token in self._done:
            token = f"{action.action_id}-{suffix}"
            suffix += 1
        self._pending[token] = action
        self._order.append(token)
        self._done.discard(token)
        while len(self._pending) > self._max_size:
            evicted = self._order.pop(0)
            del self._pending[evicted]
        return token

    def undo(self, token: str) -> UndoResult:
        if token not in self._pending:
            raise UndoError(f"unknown or already undone token {token!r}")
        action = self._pending.pop(token)
        self._order = [t for t in self._order if t != token]
        self._done.add(token)
        return UndoResult(action.action_id, action.kind, action.inverse)

    def pending(self) -> tuple[UndoableAction, ...]:
        return tuple(sorted(self._pending.values(),
                            key=lambda a: (a.kind.value, a.action_id)))

    def document(self) -> dict:
        docs = [a.to_dict() for a in self.pending()]
        return {"schema_version": 1, "pending": docs, "count": len(docs),
                "fingerprint": content_hash(docs)[:16]}


# ===========================================================================
# X8.14 -- theme editor backend: WCAG contrast + theme import/export
# ===========================================================================


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex_to_rgb(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, str) or not HEX_COLOR_RE.fullmatch(value.strip()):
        raise ThemeError(f"invalid hex color: {value!r}")
    raw = value.strip()[1:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for component in rgb:
        c = component / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio in [1.0, 21.0], rounded to 4 decimals."""
    light = _relative_luminance(_hex_to_rgb(foreground))
    dark = _relative_luminance(_hex_to_rgb(background))
    high, low = max(light, dark), min(light, dark)
    return round((high + 0.05) / (low + 0.05), 4)


def wcag_level(ratio: float, *, large_text: bool = False) -> str:
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        raise ThemeError("ratio must be a number")
    aa_min, aaa_min = (3.0, 4.5) if large_text else (4.5, 7.0)
    if ratio >= aaa_min:
        return "AAA"
    if ratio >= aa_min:
        return "AA"
    return "FAIL"


@dataclass(frozen=True)
class ContrastReport:
    foreground: str
    background: str
    ratio: float
    level: str
    aa_pass: bool
    aaa_pass: bool

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"foreground": self.foreground, "background": self.background,
                "ratio": self.ratio, "level": self.level,
                "aa_pass": self.aa_pass, "aaa_pass": self.aaa_pass}


def check_contrast(foreground: str, background: str,
                   *, large_text: bool = False) -> ContrastReport:
    ratio = contrast_ratio(foreground, background)
    level = wcag_level(ratio, large_text=large_text)
    return ContrastReport(foreground=foreground.strip(),
                          background=background.strip(),
                          ratio=round(ratio, 2), level=level,
                          aa_pass=level in ("AA", "AAA"), aaa_pass=level == "AAA")


@dataclass(frozen=True)
class ThemeDocument:
    tokens: dict[str, dict[str, str]]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        validation = validate_tokens(self.tokens)
        if not validation.ok:
            raise ThemeError("; ".join(str(e) for e in validation.errors))
        object.__setattr__(self, "fingerprint",
                           validation.fingerprint or content_hash(self.tokens)[:16])

    def to_dict(self) -> dict:
        return {"tokens": self.tokens, "fingerprint": self.fingerprint}


def import_theme(text: str) -> ThemeDocument:
    if not isinstance(text, str):
        raise ThemeError("theme import expects JSON text")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ThemeError(f"invalid theme JSON at line {exc.lineno}: {exc.msg}") from exc
    return ThemeDocument(tokens=doc)


def export_theme(tokens: Mapping[str, Mapping[str, str]]) -> str:
    validation = validate_tokens(tokens)
    if not validation.ok:
        raise ThemeError("; ".join(str(e) for e in validation.errors))
    return json.dumps(tokens, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False) + "\n"


# ===========================================================================
# X8.15 -- accessibility preferences: sound off by default, motion honoring
# ===========================================================================


class SoundCue(str, Enum):
    APPROVAL = "approval"
    ERROR = "error"
    MESSAGE = "message"
    SUCCESS = "success"


@dataclass(frozen=True)
class AccessibilityPreferences:
    sound_enabled: bool = False          # off by default
    sound_cues: frozenset[SoundCue] = frozenset()
    reduced_motion: bool = False
    system_reduced_motion: bool = False

    def __post_init__(self) -> None:
        for label, value in (("sound_enabled", self.sound_enabled),
                             ("reduced_motion", self.reduced_motion),
                             ("system_reduced_motion", self.system_reduced_motion)):
            if not isinstance(value, bool):
                raise PreferenceError(f"{label} must be a boolean")
        try:
            cues = frozenset(SoundCue(c) for c in self.sound_cues)
        except ValueError as exc:
            raise PreferenceError(str(exc)) from exc
        object.__setattr__(self, "sound_cues", cues)

    @property
    def effective_reduced_motion(self) -> bool:
        return self.reduced_motion or self.system_reduced_motion

    def to_dict(self) -> dict:
        return {"sound_enabled": self.sound_enabled,
                "sound_cues": sorted(c.value for c in self.sound_cues),
                "reduced_motion": self.reduced_motion,
                "system_reduced_motion": self.system_reduced_motion,
                "effective_reduced_motion": self.effective_reduced_motion}


_PREFERENCE_KEYS = frozenset({"sound_enabled", "sound_cues", "reduced_motion",
                              "system_reduced_motion"})


def resolve_preferences(overrides: Mapping[str, Any] | None = None) -> AccessibilityPreferences:
    overrides = dict(overrides or {})
    unknown = set(overrides) - _PREFERENCE_KEYS
    if unknown:
        raise PreferenceError(f"unknown preference keys: {sorted(unknown)}")
    return AccessibilityPreferences(**overrides)


def apply_motion_preference(tokens: Mapping[str, Mapping[str, str]],
                            prefs: AccessibilityPreferences) -> dict[str, dict[str, str]]:
    """Collapse motion tokens to zero when reduced motion is effective."""
    if not isinstance(prefs, AccessibilityPreferences):
        raise PreferenceError("expected AccessibilityPreferences")
    validation = validate_tokens(tokens)
    if not validation.ok:
        raise PreferenceError("; ".join(str(e) for e in validation.errors))
    result = {category: dict(values) for category, values in tokens.items()}
    if prefs.effective_reduced_motion:
        motion = result.get("motion", {})
        for name, value in list(motion.items()):
            if name == "easing":
                motion[name] = "linear"
            elif isinstance(value, str) and (value.endswith("ms") or value.endswith("s")):
                motion[name] = "0ms"
    return result


def preference_document(prefs: AccessibilityPreferences) -> dict:
    if not isinstance(prefs, AccessibilityPreferences):
        raise PreferenceError("expected AccessibilityPreferences")
    doc = prefs.to_dict()
    return {"schema_version": 1, "preferences": doc,
            "fingerprint": content_hash(doc)[:16]}


# ===========================================================================
# X8.16 -- multi-monitor awareness: remember positions, remember dock screens
# ===========================================================================


@dataclass(frozen=True)
class DisplayInfo:
    display_id: str
    width: int
    height: int
    origin_x: int = 0
    origin_y: int = 0
    primary: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.display_id, str) or not self.display_id.strip():
            raise DisplayError("a display needs an id")
        try:
            width = _positive_int(self.width, "width")
            height = _positive_int(self.height, "height")
        except ValueError as exc:
            raise DisplayError(str(exc)) from exc
        for label, value in (("origin_x", self.origin_x), ("origin_y", self.origin_y)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise DisplayError(f"{label} must be an integer")
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)

    def to_dict(self) -> dict:
        return {"display_id": self.display_id, "width": self.width,
                "height": self.height, "origin_x": self.origin_x,
                "origin_y": self.origin_y, "primary": self.primary}


@dataclass(frozen=True)
class WindowRect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        for label, value in (("x", self.x), ("y", self.y),
                             ("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise DisplayError(f"{label} must be an integer")
        try:
            _positive_int(self.width, "width")
            _positive_int(self.height, "height")
        except ValueError as exc:
            raise DisplayError(str(exc)) from exc

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width,
                "height": self.height}


@dataclass(frozen=True)
class DockAssignment:
    dock_id: str
    display_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.dock_id, str) or not self.dock_id.strip():
            raise DisplayError("a dock needs an id")
        if not isinstance(self.display_id, str) or not self.display_id.strip():
            raise DisplayError("a dock needs a display id")

    def to_dict(self) -> dict:
        return {"dock_id": self.dock_id, "display_id": self.display_id}


@dataclass(frozen=True)
class DisplaySnapshot:
    displays: tuple[DisplayInfo, ...]
    positions: tuple[tuple[str, WindowRect], ...]
    docks: tuple[DockAssignment, ...]

    @property
    def fingerprint(self) -> str:
        return content_hash(self.to_dict())[:16]

    def to_dict(self) -> dict:
        return {"displays": [d.to_dict() for d in self.displays],
                "positions": [{"display_id": key, "rect": rect.to_dict()}
                              for key, rect in self.positions],
                "docks": [d.to_dict() for d in self.docks]}


class DisplayLayoutStore:
    """In-memory per-display window/dock memory (native windowing is UI)."""

    def __init__(self) -> None:
        self._displays: dict[str, DisplayInfo] = {}
        self._positions: dict[str, WindowRect] = {}
        self._docks: dict[str, DockAssignment] = {}

    def register(self, display: DisplayInfo) -> DisplayInfo:
        if not isinstance(display, DisplayInfo):
            raise DisplayError("expected a DisplayInfo")
        self._displays[display.display_id] = display
        return display

    def _display(self, display_id: str) -> DisplayInfo:
        try:
            return self._displays[display_id]
        except KeyError as exc:
            raise DisplayError(f"unknown display {display_id!r}") from exc

    def set_position(self, display_id: str, rect: WindowRect) -> WindowRect:
        display = self._display(display_id)
        if not isinstance(rect, WindowRect):
            raise DisplayError("expected a WindowRect")
        if not (display.origin_x <= rect.x
                and display.origin_y <= rect.y
                and rect.x + rect.width <= display.origin_x + display.width
                and rect.y + rect.height <= display.origin_y + display.height):
            raise DisplayError("window rect does not fit inside the display")
        self._positions[display_id] = rect
        return rect

    def assign_dock(self, dock_id: str, display_id: str) -> DockAssignment:
        self._display(display_id)
        assignment = DockAssignment(dock_id, display_id)
        self._docks[dock_id] = assignment
        return assignment

    def snapshot(self) -> DisplaySnapshot:
        displays = tuple(self._displays[d] for d in sorted(self._displays))
        positions = tuple((d, self._positions[d]) for d in sorted(self._positions))
        docks = tuple(self._docks[d] for d in sorted(self._docks))
        return DisplaySnapshot(displays, positions, docks)


# ===========================================================================
# X8.17 -- empty-state / onboarding copy deck (single source of words)
# ===========================================================================


COPY_DECK: dict[str, str] = {
    "empty.session.title": "A fresh start",
    "empty.session.body": "Ask Keel anything about this workspace. Your first step is a question.",
    "empty.files.title": "Nothing here yet",
    "empty.files.body": "Add a file to this workspace and it will show up here.",
    "empty.notifications.title": "All quiet",
    "empty.notifications.body": "Approvals, job results and errors will land here.",
    "empty.history.title": "No runs yet",
    "empty.history.body": "Past sessions appear here once you start one.",
    "onboarding.welcome.title": "Welcome to Keel",
    "onboarding.welcome.body": "Keel works locally, keeps your files private, and asks before it acts.",
    "onboarding.first_task.title": "Give Keel a task",
    "onboarding.first_task.body": "Describe the outcome you want. Keel will plan, ask when needed, and show its work.",
    "onboarding.privacy.title": "Private by default",
    "onboarding.privacy.body": "No account, no telemetry sent home, no cloud required.",
    "recovery.title": "Pick up where you left off",
    "recovery.body": "Your draft is safe. Keel restored it after the view restarted.",
    "error.title": "Something went wrong",
    "error.body": "Your session and draft are intact. Try again or reopen this view.",
    "greeting.personalized.title": "Hello, {name}",
    "greeting.personalized.body": "Pick up a thread or start something new, {name}.",
}

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class CopyDeckValidation:
    ok: bool
    errors: tuple[str, ...] = ()
    entry_count: int = 0
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": list(self.errors),
                "entry_count": self.entry_count, "fingerprint": self.fingerprint}


def validate_copy_deck(deck: Mapping[str, str] = COPY_DECK) -> CopyDeckValidation:
    errors: list[str] = []
    for key, text in sorted(deck.items()):
        if not isinstance(key, str) or not key.strip():
            errors.append("copy deck has an empty key")
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{key}: copy must be non-empty")
            continue
        if text.count("{") != text.count("}"):
            errors.append(f"{key}: unbalanced placeholders")
            continue
        allowed = _PLACEHOLDER_RE.findall(text)
        stripped = _PLACEHOLDER_RE.sub("", text)
        if "{" in stripped or "}" in stripped:
            errors.append(f"{key}: unsupported placeholder syntax")
        if len(allowed) != len(set(allowed)):
            errors.append(f"{key}: duplicate placeholder")
    fingerprint = content_hash(dict(sorted(deck.items())))[:16]
    return CopyDeckValidation(not errors, tuple(errors), len(deck), fingerprint)


def lookup_copy(key: str, deck: Mapping[str, str] = COPY_DECK,
                **variables: str) -> str:
    if key not in deck:
        raise CopyDeckError(f"unknown copy key {key!r}")
    text = deck[key]
    placeholders = set(_PLACEHOLDER_RE.findall(text))
    missing = placeholders - set(variables)
    if missing:
        raise CopyDeckError(f"copy key {key!r} needs variables {sorted(missing)}")
    try:
        return text.format(**variables)
    except (KeyError, ValueError, IndexError) as exc:
        raise CopyDeckError(f"cannot render copy key {key!r}: {exc}") from exc


def coverage_report(screens: Mapping[str, Sequence[str]],
                    deck: Mapping[str, str] = COPY_DECK) -> dict:
    report: dict[str, list[str]] = {}
    for screen, keys in sorted(screens.items()):
        report[screen] = sorted(key for key in keys if key not in deck)
    all_missing = sorted({key for keys in report.values() for key in keys})
    return {"screens": report, "missing": all_missing,
            "covered": not all_missing}


def copy_deck_document(deck: Mapping[str, str] = COPY_DECK) -> dict:
    validation = validate_copy_deck(deck)
    if not validation.ok:
        raise CopyDeckError("; ".join(validation.errors))
    return {"schema_version": 1, "source": "Keel's own words (write once)",
            "entries": dict(sorted(deck.items())),
            "entry_count": len(deck), "fingerprint": validation.fingerprint}


__all__ = [
    "X8BackendError", "LayoutError", "NotificationError", "ActionError",
    "TrayError", "SelectionError", "ThreadError", "CompareError",
    "CitationError", "DiffError", "RecoveryError", "UndoError", "ThemeError",
    "PreferenceError", "DisplayError", "CopyDeckError",
    "canonical_bytes", "content_hash",
    # X8.3
    "DensityMode", "ZOOM_MIN", "ZOOM_MAX", "ZOOM_DEFAULT", "LAYOUT_NAME_RE",
    "normalize_zoom", "PaneZoom", "LayoutState", "SavedLayout", "DEFAULT_LAYOUT",
    "LayoutStore", "validate_layout_state",
    # X8.4
    "NotificationKind", "NotificationStatus", "Notification", "NotificationFilter",
    "ActivityFeed",
    # X8.5
    "NotificationAction", "ACTION_CAPABILITIES", "supported_actions",
    "ActionableNotification", "ActionCommand", "plan_notification_action",
    # X8.6
    "AgentStatus", "AgentRun", "ApprovalRef", "TraySnapshot",
    "build_tray_snapshot", "KillSwitchCommand", "kill_switch",
    "validate_kill_switch",
    # X8.7
    "SelectionAction", "MAX_SELECTION_CHARS", "SELECTION_ACTION_TARGETS",
    "TextSelection", "SelectionCommand", "plan_selection_action",
    "selection_document",
    # X8.8
    "ToolCall", "Message", "Pin", "OutlineEntry", "TimelineEntry",
    "ThreadIndex", "build_thread_index",
    # X8.9
    "Turn", "SessionRecord", "ComparisonReport", "compare_sessions",
    "comparison_document",
    # X8.10
    "Citation", "CitationPreview", "resolve_citation",
    # X8.11
    "DiffRow", "DiffHunk", "DiffReport", "MAX_DIFF_LINES", "line_diff",
    "render_unified", "FilePreview", "build_file_preview", "OpenInDockAction",
    "open_in_dock",
    # X8.12
    "DraftSnapshot", "RecoveryResult", "RecoveryStore",
    # X8.13
    "DestructiveKind", "UndoableAction", "UndoResult", "build_undo_action",
    "UndoStack",
    # X8.14
    "HEX_COLOR_RE", "contrast_ratio", "wcag_level", "ContrastReport",
    "check_contrast", "ThemeDocument", "import_theme", "export_theme",
    # X8.15
    "SoundCue", "AccessibilityPreferences", "resolve_preferences",
    "apply_motion_preference", "preference_document",
    # X8.16
    "DisplayInfo", "WindowRect", "DockAssignment", "DisplaySnapshot",
    "DisplayLayoutStore",
    # X8.17
    "COPY_DECK", "CopyDeckValidation", "validate_copy_deck", "lookup_copy",
    "coverage_report", "copy_deck_document",
]

"""keel.model_dialects — clean-room tool-call, chat-template and reasoning adapters.

Feature IDs X1.1 / X1.2 / X1.3 (reconciled 865-row registry, Addendum 3, P0).

Scope and safety
----------------
* Stdlib only. No network, no eval/exec, no subprocess, no dynamic import of
  model code. Tool calls are *data* returned as :class:`ToolCall` records; this
  module never invokes anything a model wrote.
* Pure functions wherever possible. The only filesystem access is
  :func:`load_chat_template`, which reads local catalog files under a
  caller-supplied root and enforces path containment (including symlinks).
* Detection is heuristic and deterministic: a documented evidence score per
  dialect, with a fixed tie-break order. It never claims to *know* a model —
  callers may override with an explicit dialect or probe result.

The formats recognised here are documented in
``keel/docs/research/model-dialect-behavior.md``. Nothing was copied from a
reference implementation: the encodings are public wire formats, and the code
is original, written from the registry entries and Keel's own terminology.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from html import unescape as _html_unescape
from typing import Any, Callable, Iterable
from xml.sax.saxutils import escape as _xml_escape

# The project's stable byte-length estimator is preferred when available; the
# fallback keeps this module importable in isolation (e.g. tooling scripts).
try:  # pragma: no cover - import availability varies by host
    from keel.context import estimate_tokens as _context_estimate_tokens
except Exception:  # pragma: no cover
    _context_estimate_tokens = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# X1.1 — tool-call dialect adapters
# ---------------------------------------------------------------------------

#: Dialects with a dedicated parser/emitter. ``llama`` is a JSON-shaped alias.
DIALECTS: tuple[str, ...] = (
    "json", "xml", "hermes", "react", "mistral", "qwen", "deepseek", "llama",
)

#: Fixed tie-break order for :func:`detect_dialect` (highest specificity first).
DIALECT_PRIORITY: tuple[str, ...] = (
    "deepseek", "mistral", "hermes", "qwen", "xml", "react", "json", "llama",
)

# Containers such as <function_calls>/<tool_calls> are deliberately excluded:
# the parser descends into them to find the actual call nodes.
_TOOL_TAGS = frozenset({"tool_call", "function_call", "invoke", "tool", "function"})
_NAME_TAGS = frozenset({"name", "tool_name", "function_name", "function", "tool"})
_ARG_TAGS = frozenset({"arguments", "args", "parameters", "params", "input"})
_TOOL_KEYS = frozenset({"name", "tool", "tool_name", "function", "arguments",
                        "args", "parameters", "input", "tool_calls"})


@dataclass(frozen=True)
class ToolCall:
    """A parsed tool invocation. Pure data — never executable."""

    name: str
    arguments: dict
    dialect: str
    raw: str = ""
    call_id: str | None = None
    incomplete: bool = False


# ---- tolerant JSON helpers -------------------------------------------------

def _json_spans(text: str) -> list[tuple[int, int, bool]]:
    """Yield (start, end, unclosed) spans for top-level JSON objects/arrays.

    Quote-aware so braces inside strings do not perturb the scan. A truncated
    span ends at end-of-text with ``unclosed=True``.
    """
    spans: list[tuple[int, int, bool]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] not in "{[":
            i += 1
            continue
        start, depth, in_str, esc = i, 0, False, False
        while i < n:
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        spans.append((start, i, depth > 0 or in_str))
    return spans


def _repair_json(fragment: str) -> str:
    """Best-effort syntactic repair for truncated JSON (data only)."""
    out: list[str] = []
    stack: list[str] = []
    in_str, esc = False, False
    for ch in fragment:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
        out.append(ch)
    if in_str:
        out.append('"')
    repaired = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    while stack:
        repaired += "]" if stack.pop() == "[" else "}"
    return repaired


def _tolerant_json(value: str) -> tuple[Any, bool]:
    """Return ``(decoded, needed_repair)``; decoded is None on total failure."""
    if not isinstance(value, str):
        return None, True
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_+-]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text).strip()
    try:
        return json.loads(text), False
    except Exception:
        pass
    spans = _json_spans(text)
    if spans:
        start, end, _ = spans[0]
        candidate = text[start:end]
    else:
        candidate = text
    try:
        return json.loads(candidate), False
    except Exception:
        pass
    repaired = _repair_json(candidate)
    try:
        return json.loads(repaired), True
    except Exception:
        pass
    if "'" in candidate and '"' not in candidate:
        swapped = candidate.replace("'", '"')
        for attempt in (swapped, _repair_json(swapped)):
            try:
                return json.loads(attempt), True
            except Exception:
                continue
    return None, True


def _coerce_arguments(value: Any) -> tuple[dict, bool]:
    """Normalise an argument payload into a dict; report if it was repaired."""
    if isinstance(value, dict):
        return dict(value), False
    if not isinstance(value, str):
        return {}, False
    text = value.strip()
    if not text:
        return {}, False
    if text[0] in "{[":
        obj, repaired = _tolerant_json(text)
        if isinstance(obj, dict):
            return obj, repaired
        if isinstance(obj, list):
            return {"items": obj}, repaired
    pairs = re.findall(
        r"([\w.\-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s,]+))", text)
    if pairs:
        return {k: (a if a != "" else (b if b != "" else c))
                for k, a, b, c in pairs}, False
    obj, repaired = _tolerant_json(text)
    if isinstance(obj, dict):
        return obj, repaired
    return {"input": text}, False


def _looks_like_tool(obj: Any) -> bool:
    return isinstance(obj, dict) and bool(_TOOL_KEYS.intersection(obj))


def _calls_from_obj(obj: Any, dialect: str, incomplete: bool) -> list[ToolCall]:
    if isinstance(obj, list):
        calls: list[ToolCall] = []
        for item in obj:
            calls.extend(_calls_from_obj(item, dialect, incomplete))
        return calls
    if not isinstance(obj, dict):
        return []
    if "tool_calls" in obj:
        return _calls_from_obj(obj["tool_calls"], dialect, incomplete)
    fn = obj.get("function")
    if isinstance(fn, dict) and ("name" in fn or "arguments" in fn):
        obj = {**fn, **{k: v for k, v in obj.items() if k != "function"}}
    name = obj.get("name", obj.get("tool", obj.get("tool_name")))
    if not isinstance(name, str) or not name.strip():
        return []
    args_raw = next((obj[k] for k in ("arguments", "args", "parameters", "input")
                     if k in obj), {})
    args, repaired = _coerce_arguments(args_raw)
    call_id = obj.get("id", obj.get("call_id"))
    return [ToolCall(name=name.strip(), arguments=args, dialect=dialect,
                     raw=json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    default=str),
                     call_id=str(call_id) if call_id is not None else None,
                     incomplete=incomplete or repaired)]


def _parse_json_calls(text: str, dialect: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    covered_until = -1
    for start, end, unclosed in _json_spans(text):
        if start < covered_until:
            continue
        obj, repaired = _tolerant_json(text[start:end])
        if not _looks_like_tool(obj):
            continue
        made = _calls_from_obj(obj, dialect, unclosed or repaired)
        if made:
            calls.extend(made)
            covered_until = end
    return calls


# ---- tolerant XML helpers --------------------------------------------------

@dataclass
class _Node:
    tag: str
    text: str = ""
    children: list["_Node"] = field(default_factory=list)
    attrs: str = ""
    incomplete: bool = False


_TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z_][\w.:-]*)([^>]*?)(/?)>", re.DOTALL)


def _build_dom(text: str) -> list[_Node]:
    """Tolerant, dependency-free tag scanner (not an XML validator)."""
    root = _Node("#root")
    stack = [root]
    last = 0
    for match in _TAG_RE.finditer(text):
        segment = text[last:match.start()]
        if segment.strip():
            stack[-1].text += _html_unescape(segment)
        closing, tag, attrs, self_closing = match.groups()
        tag = tag.lower()
        if closing:
            for idx in range(len(stack) - 1, 0, -1):
                if stack[idx].tag == tag:
                    del stack[idx:]
                    break
        else:
            node = _Node(tag, attrs=attrs)
            stack[-1].children.append(node)
            if not self_closing:
                stack.append(node)
        last = match.end()
    tail = text[last:]
    if tail.strip():
        stack[-1].text += _html_unescape(tail)
    for node in stack[1:]:
        node.incomplete = True
    return root.children


def _iter_tool_nodes(nodes: Iterable[_Node]) -> Iterable[_Node]:
    for node in nodes:
        if node.tag in _TOOL_TAGS:
            yield node
            # A nested tool node is a separate candidate; do not double-count
            # the outer node's own field extraction by descending further.
            continue
        yield from _iter_tool_nodes(node.children)


def _first_child(node: _Node, tags: frozenset[str]) -> _Node | None:
    for child in node.children:
        if child.tag in tags:
            return child
    return None


def _node_text(node: _Node | None) -> str:
    if node is None:
        return ""
    text = node.text.strip()
    if text:
        return text
    return " ".join(_node_text(c) for c in node.children).strip()


def _scalar_or_object(text: str) -> Any:
    text = text.strip()
    if not text:
        return ""
    obj, _ = _tolerant_json(text)
    return obj if obj is not None else text


def _arguments_from_node(node: _Node) -> dict:
    if node.text.strip():
        direct, _ = _coerce_arguments(node.text)
        if direct:
            return direct
    result: dict[str, Any] = {}
    for child in node.children:
        if child.text.strip() or not child.children:
            result[child.tag] = _scalar_or_object(child.text)
        else:
            result[child.tag] = _arguments_from_node(child)
    return result


def _parse_xml_calls(text: str, dialect: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for node in _iter_tool_nodes(_build_dom(text)):
        name = _node_text(_first_child(node, _NAME_TAGS))
        if not name:
            continue
        args_node = _first_child(node, _ARG_TAGS)
        if args_node is not None:
            if args_node.text.strip():
                args, repaired = _coerce_arguments(args_node.text)
                if not args and args_node.children:
                    args = _arguments_from_node(args_node)
            else:
                args, repaired = _arguments_from_node(args_node), args_node.incomplete
        else:
            proxy = _Node("#args", "",
                          [c for c in node.children
                           if c.tag not in _NAME_TAGS and c.tag not in _ARG_TAGS])
            args, repaired = _arguments_from_node(proxy), False
        id_match = re.search(r"\b(?:call_)?id\s*=\s*[\"']([^\"']+)[\"']", node.attrs)
        calls.append(ToolCall(
            name=name, arguments=args, dialect=dialect,
            raw=node.text.strip()[:512],
            call_id=id_match.group(1) if id_match else None,
            incomplete=bool(node.incomplete or repaired),
        ))
    return calls


# ---- dialect-specific parsers ----------------------------------------------

def _parse_hermes_calls(text: str, dialect: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    marker = re.compile(r"to=functions\.([A-Za-z0-9_.\-]+)", re.IGNORECASE)
    for match in marker.finditer(text):
        name = match.group(1)
        remainder = text[match.end():]
        boundary = remainder.find("<|im_end|>")
        if boundary != -1:
            remainder = remainder[:boundary]
        spans = _json_spans(remainder)
        if not spans:
            continue
        start, end, unclosed = spans[0]
        obj, repaired = _tolerant_json(remainder[start:end])
        args = obj if isinstance(obj, dict) else {}
        if isinstance(obj, dict) and _looks_like_tool(obj):
            nested = _calls_from_obj(obj, dialect, unclosed or repaired)
            if nested:
                calls.extend(ToolCall(n.name, n.arguments, dialect, n.raw,
                                      n.call_id, n.incomplete)
                             for n in nested)
                continue
        calls.append(ToolCall(name, args, dialect, remainder[start:end].strip(),
                              incomplete=bool(unclosed or repaired)))
    if not calls:
        # A channel-marked turn can still carry a JSON tool envelope.
        calls = _parse_json_calls(text, dialect)
    return calls


def _parse_react_calls(text: str, dialect: str) -> list[ToolCall]:
    actions = list(re.finditer(r"^\s*Action:\s*([^\n]+)", text,
                               re.IGNORECASE | re.MULTILINE))
    calls: list[ToolCall] = []
    for idx, match in enumerate(actions):
        segment_end = actions[idx + 1].start() if idx + 1 < len(actions) else len(text)
        segment = text[match.end():segment_end]
        raw_name = match.group(1).strip()
        bracket = re.search(r"\[([^\]]*)\]", raw_name)
        if bracket:
            raw_name = raw_name[:bracket.start()].strip()
        raw_name = re.sub(r"[\s,;:]+$", "", raw_name)
        if not raw_name:
            continue
        inp = re.search(
            r"Action\s*Input:\s*(.+?)(?=\n\s*(?:Thought|Action|Observation|Final\s+Answer):|\Z)",
            segment, re.IGNORECASE | re.DOTALL)
        if inp:
            args, repaired = _coerce_arguments(inp.group(1))
        elif bracket:
            args, repaired = _coerce_arguments(bracket.group(1))
        else:
            args, repaired = {}, False
        calls.append(ToolCall(raw_name, args, dialect, match.group(0).strip(),
                              incomplete=bool(repaired)))
    return calls


def _parse_qwen_calls(text: str, dialect: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for match in re.finditer(r"<tool_call\b[^>]*>(.*?)</tool_call>", text,
                             re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        obj, repaired = _tolerant_json(body)
        calls.extend(_calls_from_obj(obj, dialect, bool(repaired)))
    if not calls:
        # ChatML turns may carry a bare JSON envelope between message markers.
        calls = _parse_json_calls(text, dialect)
    return calls


def _parse_mistral_calls(text: str, dialect: str) -> list[ToolCall]:
    match = re.search(r"\[TOOL_CALLS?\](.*)", text,
                      re.IGNORECASE | re.DOTALL)
    if not match:
        return _parse_json_calls(text, dialect)
    obj, repaired = _tolerant_json(match.group(1))
    return _calls_from_obj(obj, dialect, bool(repaired))


def _parse_deepseek_calls(text: str, dialect: str) -> list[ToolCall]:
    normal = text.replace("｜", "|").replace("▁", "_")
    pattern = re.compile(
        r"<\|tool_call_begin\|>(?P<name>.*?)<\|tool_sep\|>"
        r"(?P<args>.*?)<\|tool_call_end\|>", re.IGNORECASE | re.DOTALL)
    calls: list[ToolCall] = []
    for match in pattern.finditer(normal):
        name = match.group("name").strip()
        if not name:
            continue
        args, repaired = _coerce_arguments(match.group("args"))
        calls.append(ToolCall(name, args, dialect, match.group(0),
                              incomplete=bool(repaired)))
    return calls


_PARSERS: dict[str, Callable[[str, str], list[ToolCall]]] = {
    "json": _parse_json_calls,
    "llama": _parse_json_calls,
    "xml": _parse_xml_calls,
    "hermes": _parse_hermes_calls,
    "react": _parse_react_calls,
    "qwen": _parse_qwen_calls,
    "mistral": _parse_mistral_calls,
    "deepseek": _parse_deepseek_calls,
}


def detect_dialect_scores(text: str) -> dict[str, int]:
    """Evidence score per dialect. Higher is stronger; never raises."""
    scores = {name: 0 for name in DIALECTS}
    if not isinstance(text, str) or not text:
        return scores
    upper = text.upper()
    if "TOOL▁CALL" in text.upper() or "tool▁call" in text or "<|tool_call_begin|>" in text.replace("｜", "|").replace("▁", "_"):
        scores["deepseek"] = 5
    if "[TOOL_CALL]" in upper or "[TOOL_CALLS]" in upper:
        scores["mistral"] = 5
    if ("to=functions." in text.lower() or "<|channel|>" in text
            or "<|im_start|>assistant" in text and "to=" in text):
        scores["hermes"] = 5
    if re.search(r"<tool_call\b[^>]*>\s*\{", text, re.IGNORECASE):
        scores["qwen"] = 4
    if re.search(r"<(?:tool_call|function_call|function_calls|invoke|tool_name|parameters)\b",
                 text, re.IGNORECASE):
        scores["xml"] = 4
    if (re.search(r"\bAction:", text, re.IGNORECASE)
            and re.search(r"\b(?:Action Input|Thought|Observation):", text, re.IGNORECASE)):
        scores["react"] = 4
    for start, end, _ in _json_spans(text):
        obj, _ = _tolerant_json(text[start:end])
        if _looks_like_tool(obj):
            scores["json"] = 3
            break
    return scores


def detect_dialect(text: str) -> str:
    """Pick the best-supported dialect for a model output, or ``"unknown"``."""
    scores = detect_dialect_scores(text)
    best = max(scores.values())
    if best <= 0:
        return "unknown"
    for dialect in DIALECT_PRIORITY:
        if scores.get(dialect) == best:
            return dialect
    return "unknown"


def parse_tool_calls(text: str, dialect: str = "auto") -> list[ToolCall]:
    """Parse tool invocations from model text. Malformed input yields [].

    ``dialect="auto"`` runs :func:`detect_dialect`. Truncated calls are
    recovered when possible and flagged with ``incomplete=True``. Nothing is
    ever executed: results are inert :class:`ToolCall` records.
    """
    if not isinstance(text, str) or not text:
        return []
    chosen = detect_dialect(text) if dialect in ("auto", "best", None) else dialect
    if chosen not in _PARSERS:
        return []
    try:
        return _PARSERS[chosen](text, chosen)
    except Exception:
        # A hostile or pathological fragment must never crash the turn loop.
        return []


def _dump_args(arguments: Any) -> str:
    return json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)


def format_tool_call(name: str, arguments: dict | None = None,
                     dialect: str = "json", *, call_id: str | None = None) -> str:
    """Emit a tool invocation in ``dialect``. Inverse of :func:`parse_tool_calls`."""
    if dialect not in _PARSERS:
        raise ValueError(f"unknown tool-call dialect: {dialect!r}")
    args = arguments or {}
    envelope: dict[str, Any] = {"name": name, "arguments": args}
    if call_id is not None:
        envelope["id"] = call_id
    payload = _dump_args(args)
    if dialect in ("json", "llama"):
        return _dump_args(envelope)
    if dialect == "xml":
        safe_name = _xml_escape(name)
        safe_args = _xml_escape(payload)
        id_attr = f' id="{_xml_escape(call_id)}"' if call_id else ""
        return (f"<tool_call{id_attr}>\n  <name>{safe_name}</name>\n"
                f"  <arguments>{safe_args}</arguments>\n</tool_call>")
    if dialect == "hermes":
        return ("<|im_start|>assistant<|channel|>commentary to=functions."
                f"{name} <|constrain|>json\n{payload}<|im_end|>")
    if dialect == "react":
        return f"Action: {name}\nAction Input: {payload}"
    if dialect == "mistral":
        return "[TOOL_CALLS] " + _dump_args([envelope])
    if dialect == "qwen":
        return "<tool_call>\n" + _dump_args(envelope) + "\n</tool_call>"
    if dialect == "deepseek":
        return (
            "<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>" + name
            + "<｜tool▁sep｜>" + payload + "<｜tool▁call▁end｜>"
            "<｜tool▁calls▁end｜>"
        )
    raise ValueError(f"unsupported tool-call dialect: {dialect!r}")  # pragma: no cover


def dialect_for_model_family(model_id: str) -> str:
    """Fallback dialect inferred from a model identifier (no probe data)."""
    lowered = str(model_id).lower()
    for needle, dialect in (
        ("deepseek", "deepseek"), ("mistral", "mistral"), ("qwen", "qwen"),
        ("hermes", "hermes"), ("llama", "llama"), ("react", "react"),
    ):
        if needle in lowered:
            return dialect
    return "json"


def select_dialect_for_model(model_id: str,
                             probe_results: Any = None) -> str:
    """Auto-select a dialect from probe results, else from the model family.

    Accepted probe shapes: a dialect string, ``{"dialect": ..., "score": ...}``,
    a ``{dialect: score}`` mapping, a list of such records, or a wrapper with
    a ``"models"`` mapping keyed by model id.
    """
    candidate: Any = None
    if isinstance(probe_results, dict):
        models = probe_results.get("models")
        if isinstance(models, dict):
            candidate = models.get(model_id, models.get(str(model_id)))
        if candidate is None:
            candidate = probe_results.get(model_id)
        if candidate is None and "dialect" not in probe_results:
            candidate = probe_results
    elif isinstance(probe_results, (list, tuple)):
        for record in probe_results:
            if isinstance(record, dict) and record.get("model_id") == model_id:
                candidate = record
                break

    if isinstance(candidate, str) and candidate in _PARSERS:
        return candidate
    if isinstance(candidate, dict):
        named = candidate.get("dialect")
        if isinstance(named, str) and named in _PARSERS:
            return named
        scored = {k: v for k, v in candidate.items()
                  if k in _PARSERS and isinstance(v, (int, float))}
        if scored:
            return max(scored, key=lambda k: (scored[k], -DIALECT_PRIORITY.index(k)))
    return dialect_for_model_family(model_id)


# ---------------------------------------------------------------------------
# X1.2 — chat-template handling (local catalog only)
# ---------------------------------------------------------------------------

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TEMPLATE_FILENAMES = (
    "chat_template.jinja", "chat_template.jinja2", "chat_template.txt",
    "chat_template.tmpl", "template.jinja",
)
_TEMPLATE_JSON_FILENAMES = ("template.json", "model.json", "config.json",
                            "catalog_entry.json")


@dataclass
class ChatTemplateRecord:
    """Result of a local catalog lookup. Never contains remote data."""

    model_id: str
    template: str | None = None
    source: str | None = None
    overrides: dict = field(default_factory=dict)
    found: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id, "template": self.template,
            "source": self.source, "overrides": dict(self.overrides),
            "found": self.found, "warnings": list(self.warnings),
        }


def _safe_model_segments(model_id: str) -> tuple[str, ...]:
    """Validate a model id into harmless path segments (no traversal)."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must be a non-empty string")
    mid = model_id.strip()
    if ("\\" in mid or "\x00" in mid or "%" in mid or "://" in mid
            or re.match(r"^[A-Za-z]:", mid)):
        raise ValueError(f"unsafe model_id: {model_id!r}")
    segments = mid.split("/")
    for segment in segments:
        if segment in ("", ".", "..") or not _SEGMENT_RE.match(segment):
            raise ValueError(f"unsafe model_id segment: {segment!r}")
    return tuple(segments)


def _contained_path(root: str, parts: Iterable[str]) -> str | None:
    """Resolve ``root/parts``, returning None if it escapes the root."""
    candidate = os.path.join(root, *[p for p in parts if p])
    resolved = os.path.realpath(candidate)
    root_resolved = os.path.realpath(root)
    try:
        if os.path.commonpath([os.path.normcase(root_resolved),
                               os.path.normcase(resolved)]) != os.path.normcase(root_resolved):
            return None
    except (ValueError, OSError):
        return None
    return resolved


def _read_contained(root: str, parts: tuple[str, ...],
                    warnings: list[str]) -> tuple[str, str] | None:
    resolved = _contained_path(root, parts)
    if resolved is None:
        warnings.append(f"path containment escape rejected for {'/'.join(parts)}")
        return None
    try:
        with open(resolved, "r", encoding="utf-8") as handle:
            return handle.read(), "/".join(parts)
    except (OSError, UnicodeError):
        return None


def _template_from_data(data: Any) -> tuple[str | None, dict]:
    if isinstance(data, str):
        return data, {}
    if not isinstance(data, dict):
        return None, {}
    template = None
    for key in ("chat_template", "template", "chat_template_str"):
        if isinstance(data.get(key), str):
            template = data[key]
            break
    overrides = {k: v for k, v in data.items()
                 if k not in ("chat_template", "template", "chat_template_str")}
    return template, overrides


def load_chat_template(model_id: str, catalog_root: str | os.PathLike) -> ChatTemplateRecord:
    """Read a model's chat template from the offline catalog only.

    Lookup order: per-model override JSON → per-model template file →
    per-model metadata JSON → ``catalog.json``. Every resolved path is checked
    against ``catalog_root`` (symlinks included). No network access occurs.
    """
    segments = _safe_model_segments(model_id)
    record = ChatTemplateRecord(model_id=model_id)
    try:
        root = os.path.realpath(os.fspath(catalog_root))
    except TypeError:
        root = os.path.realpath(str(catalog_root))
    if not os.path.isdir(root):
        record.warnings.append("catalog root does not exist; no template loaded")
        return record

    candidates: list[tuple[tuple[str, ...], bool]] = [
        (("overrides",) + segments[:-1] + (f"{segments[-1]}.json",), False),
    ]
    candidates += [(("models",) + segments + (name,), True)
                   for name in _TEMPLATE_FILENAMES]
    candidates += [(("models",) + segments + (name,), False)
                   for name in _TEMPLATE_JSON_FILENAMES]

    for parts, is_raw in candidates:
        loaded = _read_contained(root, parts, record.warnings)
        if loaded is None:
            continue
        text, source = loaded
        if is_raw:
            record.template, record.overrides = text, {}
        else:
            try:
                template, overrides = _template_from_data(json.loads(text))
            except (ValueError, TypeError):
                record.warnings.append(f"invalid JSON in catalog file {source}")
                continue
            if template is None:
                continue
            record.template, record.overrides = template, overrides
        record.found, record.source = True, source
        break

    if not record.found:
        loaded = _read_contained(root, ("catalog.json",), record.warnings)
        if loaded is not None:
            text, source = loaded
            try:
                catalog = json.loads(text)
            except (ValueError, TypeError):
                catalog = {}
                record.warnings.append(f"invalid JSON in catalog file {source}")
            models = catalog.get("models", {}) if isinstance(catalog, dict) else {}
            entry = None
            if isinstance(models, dict):
                entry = models.get(model_id, models.get("/".join(segments)))
            template, overrides = _template_from_data(entry)
            if isinstance(entry, dict) and isinstance(entry.get("template_file"), str):
                # Always validate a declared template_file, even when an inline
                # template is present, so escapes are surfaced as warnings.
                tf_parts = tuple(entry["template_file"].replace("\\", "/").split("/"))
                tf_loaded = _read_contained(root, tf_parts, record.warnings)
                if template is None and tf_loaded is not None:
                    template, overrides = tf_loaded[0], {
                        k: v for k, v in entry.items() if k != "template_file"}
            if template is not None:
                record.template, record.overrides = template, overrides
                record.found, record.source = True, source + "#" + "/".join(segments)

    if record.found:
        warning = template_warning(record.template, model_id,
                                   dialect=record.overrides.get("dialect"))
        if warning:
            record.warnings.append(warning)
    return record


_ROLE_MARKERS = ("<|im_start|>", "<|im_end|>", "[INST]", "[/INST]", "<|user|>",
                 "<|assistant|>", "<human>", "<bot>", "### ", "{{ user }}",
                 "{{user}}", "<|start_header_id|>")
_TOOL_MARKERS = ("to=functions.", "<tool", "[TOOL", "tool_call", "▁tool")


def template_warning(template: str | None, model_id: str,
                     *, dialect: str | None = None) -> str | None:
    """Return a deterministic mismatch warning, or None when plausible."""
    if not isinstance(template, str) or not template.strip():
        return f"no chat template declared for {model_id}; using Keel default framing"

    expected: dict[str, tuple[str, ...]] = {
        "hermes": ("<|im_start|>",),
        "qwen": ("<|im_start|>",),
        "deepseek": ("<|im_start|>", "<｜"),
        "llama": ("[INST]",),
        "mistral": ("[INST]",),
    }
    family = dialect_for_model_family(model_id)
    if family in expected:
        missing = [marker for marker in expected[family] if marker not in template]
        if missing:
            return (f"chat template for {model_id} is missing expected "
                    f"{family} markers: {', '.join(missing)}")

    if not any(marker in template for marker in _ROLE_MARKERS):
        return (f"chat template for {model_id} has no recognizable "
                "user/assistant role markers")

    if dialect and not any(marker in template for marker in _TOOL_MARKERS):
        return (f"chat template for {model_id} declares no tool-call markers; "
                f"dialect {dialect!r} may not be honored")
    return None


# ---------------------------------------------------------------------------
# X1.3 — reasoning-model output handling
# ---------------------------------------------------------------------------

_REASONING_TAGS = ("thinking", "think", "reasoning", "analysis", "scratchpad", "cot")
_TAG_ALT = "|".join(_REASONING_TAGS)
# A tag is either <think> or <|think|>/<｜think｜>; the closing form places the
# slash after the pipe: </think> or <|/think|>/<｜/think｜>. The shared ``p``
# backreference ensures opening and closing styles agree.
_REASONING_RE = re.compile(
    r"<(?P<p>[|｜]?)(?P<tag>" + _TAG_ALT + r")(?P=p)\s*>"
    r"(?P<body>.*?)"
    r"<(?P=p)/(?P=tag)(?P=p)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_RE = re.compile(
    r"<(?P<p>[|｜]?)(?P<tag>" + _TAG_ALT + r")(?P=p)\s*>", re.IGNORECASE)


@dataclass
class ReasoningBlock:
    """A stripped reasoning span. Kept as data for the collapsible UI."""

    text: str
    tag: str
    start: int
    end: int
    closed: bool

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text


def _iter_reasoning_spans(text: str) -> list[tuple[int, int, ReasoningBlock]]:
    spans: list[tuple[int, int, ReasoningBlock]] = []
    if not isinstance(text, str) or not text:
        return spans
    cursor = 0
    for match in _REASONING_RE.finditer(text):
        block = ReasoningBlock(match.group("body"), match.group("tag").lower(),
                               match.start(), match.end(), True)
        spans.append((match.start(), match.end(), block))
        cursor = match.end()
    tail = text[cursor:]
    unclosed = _OPEN_RE.search(tail)
    if unclosed:
        start = cursor + unclosed.start()
        body = tail[unclosed.end():]
        spans.append((start, len(text),
                      ReasoningBlock(body, unclosed.group("tag").lower(),
                                     start, len(text), False)))
    return spans


def split_reasoning(text: str) -> tuple[str, list[ReasoningBlock]]:
    """Return ``(visible_text, reasoning_blocks)``.

    Handles ``<think>``, ``<thinking>``, ``<reasoning>``, ``<analysis>``,
    ``<scratchpad>`` and ``<cot>`` in ASCII, ``<|...|>`` and ``<｜...｜>``
    bracket styles. A trailing unclosed block is returned with ``closed=False``.
    """
    if not isinstance(text, str) or not text:
        return (text or ""), []
    spans = _iter_reasoning_spans(text)
    if not spans:
        return text, []
    parts: list[str] = []
    cursor = 0
    for start, end, _ in spans:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), [block for _, _, block in spans]


def strip_reasoning(text: str) -> str:
    """Convenience wrapper returning only the user-visible text."""
    return split_reasoning(text)[0]


def collapse_reasoning(text: str, placeholder: str = "[reasoning collapsed]") -> str:
    """Replace each reasoning span with a short placeholder for UI summaries."""
    if not isinstance(text, str) or not text:
        return text or ""
    spans = _iter_reasoning_spans(text)
    if not spans:
        return text
    parts: list[str] = []
    cursor = 0
    for start, end, _ in spans:
        parts.append(text[cursor:start])
        parts.append(placeholder)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def should_include_in_history(
    reasoning: Any,
    *,
    include_reasoning_in_history: bool = False,
    include_reasoning: bool | None = None,
) -> bool:
    """Reasoning is excluded from history by default; opt-in required."""
    if include_reasoning is not None:
        include_reasoning_in_history = include_reasoning
    return bool(include_reasoning_in_history)


def _reasoning_texts(reasoning: Any) -> list[str]:
    if reasoning is None:
        return []
    if isinstance(reasoning, ReasoningBlock):
        return [reasoning.text]
    if isinstance(reasoning, str):
        return [reasoning]
    if isinstance(reasoning, (list, tuple, set)):
        texts: list[str] = []
        for item in reasoning:
            texts.extend(_reasoning_texts(item))
        return texts
    return [str(reasoning)]


def _default_estimator(text: str) -> int:
    if _context_estimate_tokens is not None:
        try:
            return int(_context_estimate_tokens([{"content": text}]))
        except Exception:  # pragma: no cover - estimator contract is simple
            pass
    return math.ceil(len(text.encode("utf-8")) / 4)


def count_reasoning_tokens(reasoning: Any,
                           *, estimator: Callable[[str], int] | None = None) -> int:
    """Count reasoning tokens using Keel's stable estimator when available."""
    fn = estimator or _default_estimator
    return sum(int(fn(text)) for text in _reasoning_texts(reasoning))


def count_total_reasoning_tokens(text: str,
                                 *, estimator: Callable[[str], int] | None = None) -> int:
    """Split a full model output and total all of its reasoning tokens."""
    _, blocks = split_reasoning(text)
    return count_reasoning_tokens(blocks, estimator=estimator)

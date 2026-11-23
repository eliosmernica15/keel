"""X1.7 / X1.8 — repo map ranking and accurate token counting.

X1.7 builds a symbol graph from a path -> content mapping, scores symbols with
a small deterministic PageRank (reference centrality), blends in caller supplied
recency weights, and renders a budget-trimmed, reproducible repo map.

X1.8 provides :class:`TokenCounter`: an injected runtime tokenizer is used when
the caller supplies one, otherwise a context.py-style bytes/4 estimator with a
calibration table is used. The module makes no outbound calls of any kind; the
caller owns every side effect. Standard library only.
"""

from __future__ import annotations

import ast
import math
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable

# --- public limits ---------------------------------------------------------
MAX_NODES = 5_000
MAX_FILE_BYTES = 2_000_000
MAX_EDGES_PER_SYMBOL = 48
MAX_SIGNATURE_CHARS = 96
DEFAULT_TOKEN_BUDGET = 2_048
DEFAULT_TOP_N = 50

# --- X1.8 constants --------------------------------------------------------
DEFAULT_BYTES_PER_TOKEN = 4.0


# ==========================================================================
# X1.8 — token counting
# ==========================================================================

def _coerce_text(text: Any) -> str:
    """Return a string for text-like input; never raises for odd callers."""
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if isinstance(text, (bytes, bytearray, memoryview)):
        return bytes(text).decode("utf-8", errors="replace")
    try:
        return str(text)
    except Exception:
        return ""


class TokenCounter:
    """Count tokens with an injected tokenizer or a calibrated estimator.

    ``tokenizer_fn(text) -> int`` is the *only* integration point for a real
    runtime tokenizer. It is called verbatim; this class never reaches out to
    any service. A failing or malformed tokenizer degrades to the estimator,
    and the failure is recorded in :attr:`tokenizer_failures`.

    All mutable state is guarded by an ``RLock``; ``count`` and ``calibrate``
    may be called concurrently.
    """

    DEFAULT_RATIO = DEFAULT_BYTES_PER_TOKEN
    MIN_RATIO = 1.0
    MAX_RATIO = 12.0
    MAX_SAMPLES = 1_000

    def __init__(self, tokenizer_fn: Callable[[str], int] | None = None,
                 *, calibration: Sequence | None = None) -> None:
        self._lock = threading.RLock()
        self._tokenizer_fn = tokenizer_fn
        self._ratio = float(self.DEFAULT_RATIO)
        self._samples: tuple[tuple[str, int], ...] = ()
        self._failures = 0
        if calibration:
            self.calibrate(calibration)

    # -- configuration / introspection -------------------------------------
    def set_tokenizer(self, tokenizer_fn: Callable[[str], int] | None) -> "TokenCounter":
        with self._lock:
            self._tokenizer_fn = tokenizer_fn
        return self

    @property
    def ratio(self) -> float:
        """Current bytes-per-token ratio used by the fallback estimator."""
        with self._lock:
            return self._ratio

    @property
    def bytes_per_token(self) -> float:
        return self.ratio

    @property
    def calibration_table(self) -> dict[str, Any]:
        """Snapshot of the calibration table (stable for repeated calls)."""
        with self._lock:
            return {"default": self._ratio, "samples": len(self._samples)}

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def tokenizer_failures(self) -> int:
        with self._lock:
            return self._failures

    @property
    def uses_tokenizer(self) -> bool:
        with self._lock:
            return self._tokenizer_fn is not None

    # -- counting -----------------------------------------------------------
    @staticmethod
    def _estimate(text: str, ratio: float) -> int:
        if not text:
            return 0
        return int(math.ceil(len(text.encode("utf-8")) / ratio))

    @staticmethod
    def _valid_count(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, float) and value.is_integer() and value >= 0:
            return int(value)
        return None

    def count(self, text: Any) -> int:
        value = _coerce_text(text)
        tokenizer = self._tokenizer_fn
        if tokenizer is not None:
            try:
                counted = self._valid_count(tokenizer(value))
            except Exception:
                counted = None
            if counted is not None:
                return counted
            with self._lock:
                self._failures += 1
        with self._lock:
            ratio = self._ratio
        return self._estimate(value, ratio)

    def count_batch(self, texts: Sequence[Any]) -> list[int]:
        return [self.count(item) for item in texts]

    # -- calibration --------------------------------------------------------
    @staticmethod
    def _normalize_sample(sample: Any) -> tuple[str, int] | None:
        if isinstance(sample, Mapping):
            text = sample.get("text", sample.get("content", ""))
            tokens = sample.get("tokens", sample.get("actual_tokens",
                                                     sample.get("expected", 0)))
        elif isinstance(sample, (tuple, list)) and len(sample) >= 2:
            text, tokens = sample[0], sample[1]
        else:
            return None
        text = _coerce_text(text)
        try:
            count = int(tokens)
        except (TypeError, ValueError, OverflowError):
            return None
        if not text or count <= 0:
            return None
        return text, count

    def calibrate(self, samples: Sequence | None) -> "TokenCounter":
        """Recompute bytes/token from (text, observed_tokens) samples.

        The estimator ratio is the byte-weighted aggregate of all valid
        samples, clamped to ``[MIN_RATIO, MAX_RATIO]``. Recalibrating with the
        same samples is idempotent, so repeated calls are stable. Invalid or
        empty samples leave the current calibration untouched.
        """
        if not samples:
            return self
        valid = [sample for item in samples
                 if (sample := self._normalize_sample(item)) is not None]
        if not valid:
            return self
        total_bytes = sum(len(text.encode("utf-8")) for text, _ in valid)
        total_tokens = sum(tokens for _, tokens in valid)
        if total_bytes <= 0 or total_tokens <= 0:
            return self
        ratio = min(self.MAX_RATIO, max(self.MIN_RATIO,
                                        total_bytes / total_tokens))
        with self._lock:
            self._ratio = float(ratio)
            self._samples = tuple(valid[-self.MAX_SAMPLES:])
        return self


def estimate_tokens(text: Any) -> int:
    """Stateless bytes/4 heuristic, matching ``keel.context`` semantics."""
    return TokenCounter._estimate(_coerce_text(text), DEFAULT_BYTES_PER_TOKEN)


# ==========================================================================
# X1.7 — symbol graph
# ==========================================================================

@dataclass(frozen=True)
class Symbol:
    id: str
    name: str
    file: str
    kind: str
    line: int
    signature: str


@dataclass
class SymbolGraph:
    nodes: dict[str, Symbol] = field(default_factory=dict)
    # id -> ids of symbols referenced by this symbol
    edges: dict[str, set[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "nodes": {key: dict(vars(value)) for key, value in self.nodes.items()},
            "edges": {key: sorted(value) for key, value in self.edges.items()},
        }


@dataclass(frozen=True)
class RankedSymbol:
    symbol: Symbol
    score: float
    recency: float
    rank: int
    tokens: int

    def render_line(self) -> str:
        sig = self.symbol.signature
        if len(sig) > MAX_SIGNATURE_CHARS:
            sig = sig[:MAX_SIGNATURE_CHARS - 1] + "…"
        return (f"{self.symbol.file}:{self.symbol.line}: "
                f"{self.symbol.kind} {self.symbol.name} {sig} "
                f"score={self.score:.4f}").rstrip()

    def as_dict(self) -> dict:
        return {"symbol": dict(vars(self.symbol)), "score": self.score,
                "recency": self.recency, "rank": self.rank,
                "tokens": self.tokens}


_PY_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)", re.M)
_PY_CLASS = re.compile(r"^[ \t]*class[ \t]+([A-Za-z_]\w*)", re.M)
_JS_FUNC = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?"
    r"function[ \t]+([A-Za-z_$][\w$]*)", re.M)
_JS_DECL = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)"
    r"[ \t]*=", re.M)
_DECL_KINDS = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:interface|type|enum)[ \t]+"
    r"([A-Za-z_$][\w$]*)", re.M)
_FROM_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+['\"]?([A-Za-z_$./][\w./$-]*)['\"]?"
    r"(?:[ \t]+import\b.*)?$", re.M)
_PY_FROM = re.compile(r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]+", re.M)
_PY_IMPORT = re.compile(r"^[ \t]*import[ \t]+([\w.]+)", re.M)
_JS_FROM = re.compile(r"\bfrom[ \t]+['\"]([^'\"]+)['\"]")
_JS_REQUIRE = re.compile(r"\brequire\([ \t]*['\"]([^'\"]+)['\"]")
_JS_IMPORT = re.compile(r"^[ \t]*import[ \t]+['\"]([^'\"]+)['\"]", re.M)
_NAME = re.compile(r"[A-Za-z_]\w*")


def _normal_path(path: Any) -> str:
    return _coerce_text(path).replace("\\", "/").lstrip("./")


def _module_name(path: str) -> str:
    stem = path.rsplit("/", 1)[-1]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    prefix = path.rsplit("/", 1)[0].replace("/", ".") if "/" in path else ""
    return f"{prefix}.{stem}" if prefix else stem


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text[:MAX_SIGNATURE_CHARS]


def _resolved_module(spec: str, module_index: dict[str, list[tuple[str, str]]],
                     current_path: str) -> str | None:
    """Resolve an import specifier to a local module node id."""
    spec = spec.strip().lstrip("./")
    spec = spec.rsplit("/", 1)[-1].replace("\\", "/")
    parts = [part for part in re.split(r"[./]", spec) if part]
    if not parts:
        return None
    tail = parts[-1]
    candidates = module_index.get(tail, [])
    if not candidates:
        return None
    spec_tail = parts[-2] if len(parts) > 1 else ""
    for module, path in candidates:
        if module == spec or module.endswith("." + spec):
            return path
    if spec_tail:
        for module, path in candidates:
            if module.endswith("." + spec_tail + "." + tail):
                return path
    if len(candidates) == 1 and candidates[0][1] != current_path:
        return candidates[0][1]
    for module, path in candidates:
        if path != current_path:
            return path
    return None


def _import_specs(content: str) -> list[str]:
    specs: list[str] = []
    for regex in (_PY_FROM, _PY_IMPORT):
        specs.extend(match.group(1) for match in regex.finditer(content))
    for regex in (_JS_FROM, _JS_REQUIRE, _JS_IMPORT, _FROM_IMPORT):
        specs.extend(match.group(1) for match in regex.finditer(content))
    return specs


def _signature(node: ast.AST, source: str) -> str:
    try:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return _short("def " + node.name + ast.unparse(node.args))
        if isinstance(node, ast.ClassDef):
            return _short("class " + node.name)
    except Exception:
        pass
    return _short(source.splitlines()[getattr(node, "lineno", 1) - 1]
                  if source.splitlines() else "")


def _python_definitions(tree: ast.Module, source: str):
    """Yield (name, kind, line, signature, body_node) for module-level defs."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield (node.name, "function", node.lineno,
                   _signature(node, source), node)
        elif isinstance(node, ast.ClassDef):
            yield (node.name, "class", node.lineno,
                   _signature(node, source), node)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield (f"{node.name}.{child.name}", "method", child.lineno,
                           _signature(child, source), child)


def _referenced_names(node: ast.AST | None) -> set[str]:
    names: set[str] = set()
    if node is None:
        return names
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def build_symbol_graph(files: Mapping[str, str] | dict[str, str]) -> SymbolGraph:
    """Parse a path -> content mapping into a bounded symbol reference graph.

    Python sources use :mod:`ast` (falling back to regex on syntax errors);
    other sources use conservative regex parsing. Imports become module-level
    edges, and name/attribute usages become symbol-level reference edges. The
    result is sorted by path and id, cycle-safe, and capped at ``MAX_NODES``.
    """
    graph = SymbolGraph()
    if not files:
        return graph
    paths = sorted({_normal_path(path) for path in files})
    contents = {_normal_path(path): _coerce_text(files[path]) for path in files}
    module_names = {path: _module_name(path) for path in paths}

    module_index: dict[str, list[tuple[str, str]]] = {}
    for path, module in module_names.items():
        module_index.setdefault(module.rsplit(".", 1)[-1], []).append((module, path))
    for bucket in module_index.values():
        bucket.sort()

    def add_symbol(path: str, name: str, kind: str, line: int,
                   signature: str) -> str | None:
        if len(graph.nodes) >= MAX_NODES:
            return None
        symbol_id = f"{path}::{name}"
        if symbol_id in graph.nodes:
            return symbol_id
        graph.nodes[symbol_id] = Symbol(
            id=symbol_id, name=name, file=path, kind=kind,
            line=int(line or 0), signature=_short(signature))
        graph.edges[symbol_id] = set()
        return symbol_id

    def add_edge(source: str | None, target: str | None) -> None:
        if not source or not target or source == target:
            return
        if source not in graph.nodes or target not in graph.nodes:
            return
        bucket = graph.edges[source]
        if len(bucket) < MAX_EDGES_PER_SYMBOL:
            bucket.add(target)

    simple_names: dict[str, list[str]] = {}
    module_nodes: dict[str, str] = {}
    module_by_name: dict[str, str] = {}
    file_data: dict[str, dict] = {}

    # Pass 1: create every node before wiring any edge, so imports and
    # references may point forward to files parsed later in path order.
    for path in paths:
        content = contents[path]
        if len(content.encode("utf-8")) > MAX_FILE_BYTES or "\x00" in content:
            continue
        module = module_names[path]
        module_id = add_symbol(path, module, "module", 1, f"module {path}")
        if module_id is None:
            break
        module_nodes[path] = module_id
        module_by_name[module] = module_id

        parsed: ast.Module | None = None
        if path.endswith(".py") or "def " in content or "class " in content:
            try:
                parsed = ast.parse(content)
            except (SyntaxError, ValueError, RecursionError, MemoryError):
                parsed = None

        definitions: list[tuple[str, str, int, str, Any]] = []
        if parsed is not None:
            definitions = list(_python_definitions(parsed, content))
        else:
            for regex, kind in ((_PY_DEF, "function"), (_PY_CLASS, "class"),
                                (_JS_FUNC, "function"), (_JS_DECL, "declaration"),
                                (_DECL_KINDS, "declaration")):
                for match in regex.finditer(content):
                    line = content.count("\n", 0, match.start()) + 1
                    definitions.append((match.group(1), kind, line,
                                        match.group(0).strip(), None))
        definitions.sort(key=lambda item: (item[2], item[0]))

        def_ids: list[str] = []
        resolved: list[tuple[str, Any]] = []
        for name, kind, line, signature, body in definitions:
            qualified = f"{module}.{name}"
            symbol_id = add_symbol(path, qualified, kind, line, signature)
            if symbol_id is None:
                break
            def_ids.append(symbol_id)
            resolved.append((symbol_id, body))
            simple_names.setdefault(name.rsplit(".", 1)[-1], []).append(symbol_id)
        file_data[path] = {"module_id": module_id, "def_ids": def_ids,
                           "resolved": resolved, "parsed": parsed,
                           "content": content}

    # Pass 2: wire imports and reference edges over the complete node set.
    for path, data in file_data.items():
        content = data["content"]
        for spec in _import_specs(content):
            target_module = _resolved_module(spec, module_index, path)
            target = module_nodes.get(target_module or "")
            if target is None or target == data["module_id"]:
                continue
            add_edge(data["module_id"], target)

        for symbol_id, body in data["resolved"]:
            parsed = data["parsed"]
            if parsed is not None:
                refs = _referenced_names(body)
            else:
                refs = set(_NAME.findall(content))
            for ref in sorted(refs):
                for target_id in simple_names.get(ref, ()):
                    add_edge(symbol_id, target_id)
                module_id_target = module_by_name.get(ref)
                if module_id_target:
                    add_edge(symbol_id, module_id_target)

    return graph


# ==========================================================================
# X1.7 — PageRank, ranking, rendering
# ==========================================================================

def page_rank(graph: SymbolGraph, *, damping: float = 0.85,
              iterations: int = 64, tolerance: float = 1e-12) -> dict[str, float]:
    """Deterministic PageRank over the symbol graph (cycles are safe).

    Edges point from a referencing symbol to the referenced symbol, so mass
    accumulates at frequently referenced (central) symbols. Dangling nodes
    redistribute uniformly. The result is normalized to sum to 1.0.
    """
    ids = sorted(graph.nodes)
    count = len(ids)
    if count == 0:
        return {}
    damping = min(0.99, max(0.0, float(damping)))
    outgoing = {symbol_id: sorted(
        target for target in graph.edges.get(symbol_id, ())
        if target in graph.nodes and target != symbol_id)
        for symbol_id in ids}
    incoming: dict[str, list[str]] = {symbol_id: [] for symbol_id in ids}
    for source, targets in outgoing.items():
        for target in targets:
            incoming[target].append(source)

    rank = {symbol_id: 1.0 / count for symbol_id in ids}
    base = (1.0 - damping) / count
    for _ in range(max(1, int(iterations))):
        dangling = sum(rank[source] for source in ids if not outgoing[source])
        share = damping * dangling / count
        updated: dict[str, float] = {}
        for target in ids:
            inflow = 0.0
            for source in incoming[target]:
                inflow += rank[source] / len(outgoing[source])
            updated[target] = base + share + damping * inflow
        delta = sum(abs(updated[key] - rank[key]) for key in ids)
        rank = updated
        if delta < tolerance:
            break
    total = sum(rank.values())
    if total > 0:
        rank = {key: value / total for key, value in rank.items()}
    return rank


def _recency_for(symbol: Symbol, weights: Mapping[Any, Any] | None) -> float:
    if not weights:
        return 0.0
    for key in (symbol.id, symbol.name,
                symbol.name.rsplit(".", 1)[-1], symbol.file):
        if key in weights:
            try:
                return min(1.0, max(0.0, float(weights[key])))
            except (TypeError, ValueError, OverflowError):
                return 0.0
    return 0.0


_KIND_PRIOR = {"module": 1.0, "declaration": 1.0, "function": 1.1,
               "method": 1.1, "class": 1.1}


def rank_symbols(graph: SymbolGraph,
                 recency_weights: Mapping[Any, Any] | None = None,
                 top_n: int | None = DEFAULT_TOP_N,
                 token_budget: int = DEFAULT_TOKEN_BUDGET,
                 *, counter: TokenCounter | None = None) -> list[RankedSymbol]:
    """Rank symbols by PageRank centrality blended with recency.

    Ties break deterministically by (file, name, kind, line). The rendered
    token cost of each line is recorded and used to trim the map to
    ``token_budget`` before ``top_n`` is applied.
    """
    if not graph.nodes:
        return []
    tally = page_rank(graph)
    counter = counter or TokenCounter()
    scored: list[tuple[float, float, Symbol]] = []
    for symbol_id, symbol in graph.nodes.items():
        recency = _recency_for(symbol, recency_weights)
        prior = _KIND_PRIOR.get(symbol.kind, 1.0)
        score = round(tally.get(symbol_id, 0.0) * prior * (1.0 + recency), 12)
        scored.append((score, recency, symbol))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].file,
                                  item[2].name, item[2].kind, item[2].line))

    budget = max(0, int(token_budget))
    used = 0
    ranked: list[RankedSymbol] = []
    for score, recency, symbol in scored:
        line = RankedSymbol(symbol, score, recency, 0, 0)
        cost = counter.count(line.render_line() + "\n")
        if used + cost > budget:
            continue
        used += cost
        ranked.append(RankedSymbol(symbol, score, recency,
                                   len(ranked) + 1, cost))
    if top_n is not None:
        ranked = ranked[:max(0, int(top_n))]
        for index, record in enumerate(ranked, 1):
            ranked[index - 1] = RankedSymbol(record.symbol, record.score,
                                             record.recency, index, record.tokens)
    return ranked


def build_repo_map(files: Mapping[str, str] | dict[str, str],
                   recency_weights: Mapping[Any, Any] | None = None,
                   top_n: int | None = DEFAULT_TOP_N,
                   token_budget: int = DEFAULT_TOKEN_BUDGET,
                   *, counter: TokenCounter | None = None) -> dict:
    """Convenience entry point: graph -> ranking -> budgeted map text."""
    graph = build_symbol_graph(files)
    ranked = rank_symbols(graph, recency_weights, top_n, token_budget,
                          counter=counter)
    counter = counter or TokenCounter()
    text = render_repo_map(ranked, token_budget, counter=counter)
    return {"graph": graph, "ranked": ranked, "text": text,
            "tokens": counter.count(text), "symbols": len(graph.nodes),
            "shown": len(text.splitlines())}


def render_repo_map(ranked: Sequence[RankedSymbol],
                    budget: int = DEFAULT_TOKEN_BUDGET,
                    *, counter: TokenCounter | None = None) -> str:
    """Render ranked symbols as text, trimmed to ``budget`` tokens.

    Only complete lines are emitted, always in ranked order. A final trim by
    whole-text token count guards against estimator/tokenizer differences.
    """
    if not ranked:
        return ""
    limit = max(0, int(budget))
    if limit == 0:
        return ""
    counter = counter or TokenCounter()
    kept: list[str] = []
    used = 0
    for record in ranked:
        line = record.render_line()
        cost = record.tokens or counter.count(line + "\n")
        if used + cost > limit:
            continue
        kept.append(line)
        used += cost
    text = "\n".join(kept) + ("\n" if kept else "")
    while kept and counter.count(text) > limit:
        kept.pop()
        text = "\n".join(kept) + ("\n" if kept else "")
    return text

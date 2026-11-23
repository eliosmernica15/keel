"""X1.7 / X1.8 — repo map ranking and accurate token counting.

Tests first: the whole public surface exercised here is implemented in
``keel.repo_map`` (stdlib only, injected tokenizers, no outbound calls).
"""

from __future__ import annotations

import concurrent.futures
import inspect
from pathlib import Path

from keel.repo_map import (
    DEFAULT_BYTES_PER_TOKEN,
    MAX_NODES,
    TokenCounter,
    build_repo_map,
    build_symbol_graph,
    page_rank,
    rank_symbols,
    render_repo_map,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "keel" / "repo_map.py"


# --------------------------------------------------------------------------
# X1.7 — symbol graph construction
# --------------------------------------------------------------------------

def test_empty_repository():
    graph = build_symbol_graph({})
    assert graph.nodes == {} and graph.edges == {}
    assert page_rank(graph) == {}
    assert rank_symbols(graph) == []
    assert render_repo_map([], 2048) == ""


def test_python_defs_imports_and_methods():
    files = {
        "core.py": (
            "class Engine:\n"
            "    def run(self): pass\n"
            "def helper(): pass\n"
        ),
        "app.py": (
            "from core import Engine, helper\n"
            "import core\n"
            "def start():\n"
            "    return core.helper()\n"
        ),
    }
    graph = build_symbol_graph(files)
    names = {s.name for s in graph.nodes.values()}
    assert "core" in names
    assert "core.Engine" in names
    assert "core.Engine.run" in names
    assert "core.helper" in names
    assert "app" in names and "app.start" in names

    app_start = next(s for s in graph.nodes.values() if s.name == "app.start")
    targets = graph.edges[app_start.id]
    assert any(graph.nodes[t].name in ("core.helper", "core") for t in targets)


def test_import_cycle_is_finite_and_converges():
    graph = build_symbol_graph({
        "a.py": "import b\ndef fa(): return b.fb()\n",
        "b.py": "import a\ndef fb(): return a.fa()\n",
    })
    scores = page_rank(graph)
    assert len(scores) == len(graph.nodes)
    assert all(0.0 <= v <= 1.0 for v in scores.values())
    assert abs(sum(scores.values()) - 1.0) < 1e-6


def test_syntax_error_falls_back_to_regex():
    graph = build_symbol_graph({"broken.py": "def broken(:\n  pass\n"})
    names = {s.name for s in graph.nodes.values()}
    assert "broken" in names  # module node survives
    assert "broken.broken" in names  # regex recovered the definition


def test_non_python_files_use_regex_and_ignore_binary():
    graph = build_symbol_graph({
        "main.js": (
            "import { boot } from './core';\n"
            "function start() { return boot(); }\n"
        ),
        "blob.bin": "\x00\x01\x02def ghost()",
    })
    names = {s.name for s in graph.nodes.values()}
    assert "main.start" in names
    assert not any("blob" in n for n in names)


def test_build_order_is_deterministic():
    files = {
        "z.py": "from a import helper\ndef zz(): pass\n",
        "a.py": "def helper(): pass\n",
    }
    forward = build_symbol_graph(files)
    reverse = build_symbol_graph(dict(reversed(list(files.items()))))
    assert sorted(forward.nodes) == sorted(reverse.nodes)
    assert {k: sorted(v) for k, v in forward.edges.items()} == \
           {k: sorted(v) for k, v in reverse.edges.items()}


def test_huge_graph_is_bounded():
    files = {
        f"m{i}.py": "\n".join(f"def f{j}(): pass" for j in range(3))
        for i in range(MAX_NODES)
    }
    graph = build_symbol_graph(files)
    assert 0 < len(graph.nodes) <= MAX_NODES
    assert len(graph.nodes) == MAX_NODES
    scores = page_rank(graph, iterations=8)
    assert len(scores) == len(graph.nodes)


# --------------------------------------------------------------------------
# X1.7 — PageRank / ranking / rendering
# --------------------------------------------------------------------------

def test_pagerank_rewards_inbound_references_and_handles_isolates():
    graph = build_symbol_graph({
        "hub.py": "def central(): pass\ndef quiet(): pass\n",
        "a.py": "import hub\ndef a(): return hub.central()\n",
        "b.py": "import hub\ndef b(): return hub.central()\n",
        "c.py": "import hub\ndef c(): return hub.central()\n",
    })
    scores = page_rank(graph)
    by_name = {s.name: scores[s.id] for s in graph.nodes.values()}
    assert by_name["hub.central"] > by_name["hub.quiet"]
    assert by_name["hub.quiet"] > 0.0  # isolated nodes keep base mass
    assert abs(sum(by_name.values()) - 1.0) < 1e-6


def test_pagerank_self_loop_does_not_trap_mass():
    graph = build_symbol_graph({"s.py": "def loop(): return loop()\n"})
    scores = page_rank(graph)
    assert all(0.0 < v <= 1.0 for v in scores.values())
    assert abs(sum(scores.values()) - 1.0) < 1e-6


def test_rank_centrality_and_recency_and_top_n():
    graph = build_symbol_graph({
        "core.py": "def hot(): pass\ndef cold(): pass\n",
        "a.py": "import core\ndef a(): return core.hot()\n",
        "b.py": "import core\ndef b(): return core.hot()\n",
    })
    ranked = rank_symbols(graph, top_n=100)
    names = [record.symbol.name for record in ranked]
    assert names.index("core.hot") < names.index("core.cold")
    assert names.index("core.hot") < names.index("a.a")

    recency = {"core.cold": 1.0}
    boosted = rank_symbols(graph, recency_weights=recency, top_n=100)
    cold = next(r for r in boosted if r.symbol.name == "core.cold")
    assert cold.recency == 1.0
    assert boosted.index(cold) < ranked.index(
        next(r for r in ranked if r.symbol.name == "core.cold"))
    assert [r.rank for r in boosted] == list(range(1, len(boosted) + 1))
    assert len(rank_symbols(graph, top_n=2)) == 2
    assert rank_symbols(graph, top_n=0) == []


def test_budget_truncation_is_deterministic_and_bounded():
    files = {f"m{i}.py": f"def symbol{i}(): pass\n" for i in range(40)}
    graph = build_symbol_graph(files)
    first = rank_symbols(graph, top_n=None, token_budget=48)
    second = rank_symbols(graph, top_n=None, token_budget=48)
    assert first and first == second
    assert sum(r.tokens for r in first) <= 48
    assert render_repo_map(first, 48) == render_repo_map(second, 48)
    assert TokenCounter().count(render_repo_map(first, 48)) <= 48


def test_build_repo_map_end_to_end():
    result = build_repo_map({
        "api.py": "def handler(): return store()\n",
        "core.py": "def store(): pass\n",
    }, recency_weights={"core.store": 1.0}, token_budget=200)
    assert result["symbols"] == len(result["graph"].nodes)
    assert result["ranked"] and result["shown"] == len(result["text"].splitlines())
    assert "core.py" in result["text"]
    assert result["tokens"] <= 200
    assert result["tokens"] == TokenCounter().count(result["text"])


def test_render_repo_map_respects_tighter_budget():
    graph = build_symbol_graph({
        "one.py": "def alpha(): pass\n",
        "two.py": "def beta(): pass\n",
        "three.py": "def gamma(): pass\n",
    })
    ranked = rank_symbols(graph, top_n=None, token_budget=100_000)
    full = render_repo_map(ranked, 100_000)
    assert "one.py" in full and "alpha" in full
    tight = render_repo_map(ranked, 12)
    assert TokenCounter().count(tight) <= 12
    # Trimming keeps ranked order; it may skip an expensive line and keep a
    # cheaper later one, so the result is an ordered subsequence of the full map.
    full_lines = full.splitlines()
    kept_lines = tight.splitlines()
    assert kept_lines
    positions = [full_lines.index(line) for line in kept_lines]
    assert positions == sorted(positions)
    assert render_repo_map(ranked, 0) == ""


# --------------------------------------------------------------------------
# X1.8 — TokenCounter
# --------------------------------------------------------------------------

def test_default_estimator_matches_context_style():
    counter = TokenCounter()
    assert counter.ratio == DEFAULT_BYTES_PER_TOKEN == 4
    assert counter.count("abcd") == 1
    assert counter.count("abcdefgh") == 2
    assert counter.count("") == 0
    assert counter.count("a" * 9) == 3


def test_empty_unicode_and_crlf_text():
    counter = TokenCounter()
    assert counter.count("") == 0
    assert counter.count("\r\n") == 1
    assert counter.count("naïve") == 2  # 6 UTF-8 bytes -> ceil(6/4)
    assert counter.count("你好") == 2   # 6 UTF-8 bytes -> ceil(6/4)
    assert counter.count("🙂") == 1     # 4 UTF-8 bytes -> ceil(4/4)
    assert counter.count(b"abcd") == 1
    assert counter.count(None) == 0


def test_injected_tokenizer_is_used():
    calls = []

    def tokenizer(text):
        calls.append(text)
        return 7

    counter = TokenCounter(tokenizer_fn=tokenizer)
    assert counter.count("anything") == 7
    assert calls == ["anything"]
    assert counter.tokenizer_failures == 0

    counter.set_tokenizer(lambda text: 3)
    assert counter.count("next") == 3


def test_tokenizer_errors_and_bad_returns_fall_back():
    def boom(text):
        raise RuntimeError("runtime tokenizer unavailable")

    counter = TokenCounter(tokenizer_fn=boom)
    assert counter.count("abcd") == 1
    assert counter.tokenizer_failures == 1

    counter.set_tokenizer(lambda text: "not an int")
    assert counter.count("abcdefgh") == 2
    counter.set_tokenizer(lambda text: -1)
    assert counter.count("abcdefgh") == 2
    assert counter.tokenizer_failures == 3


def test_calibration_updates_ratio_and_estimates():
    counter = TokenCounter()
    counter.calibrate([("a" * 40, 5)])  # 40 bytes / 5 tokens = 8
    assert counter.ratio == 8.0
    assert counter.count("a" * 40) == 5
    assert counter.calibration_table["default"] == 8.0
    assert counter.sample_count == 1


def test_calibration_stability_repeated_and_batched():
    samples = [("a" * 40, 5), ("b" * 80, 10)]
    counter = TokenCounter()
    counter.calibrate(samples)
    once = counter.ratio
    counter.calibrate(samples)
    counter.calibrate(samples)
    assert counter.ratio == once == 8.0
    assert counter.count("c" * 80) == 10


def test_calibration_ignores_invalid_samples_and_clamps():
    counter = TokenCounter()
    counter.calibrate([])
    counter.calibrate([("", 0), ("abcd", 0)])
    assert counter.ratio == DEFAULT_BYTES_PER_TOKEN
    assert counter.sample_count == 0

    counter.calibrate([("a" * 1000, 10)])  # would be 100; clamped
    assert counter.ratio == counter.MAX_RATIO
    counter.calibrate([("a" * 10, 100)])  # would be 0.1; clamped
    assert counter.ratio == counter.MIN_RATIO


def test_calibration_accepts_mapping_samples():
    counter = TokenCounter()
    counter.calibrate([{"text": "a" * 40, "tokens": 5}])
    assert counter.ratio == 8.0


def test_token_counter_is_thread_safe():
    counting = TokenCounter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: counting.count("abcd"), range(200)))
    assert results == [1] * 200

    calibrating = TokenCounter()
    samples = [("a" * 40, 5)]

    def recalibrate(_):
        calibrating.calibrate(samples)
        return calibrating.ratio

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ratios = list(pool.map(recalibrate, range(50)))
    assert set(ratios) == {8.0}
    assert calibrating.ratio == 8.0


def test_module_makes_no_outbound_calls():
    source = SOURCE.read_text(encoding="utf-8")
    for banned in ("import urllib", "import socket", "import requests",
                   "http://", "https://"):
        assert banned not in source
    assert "tokenizer_fn" in inspect.signature(TokenCounter.__init__).parameters

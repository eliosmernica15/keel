"""B2.7 — real searchable offline documentation packs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.docpacks import DocPackStore, build_pack, search, tokenize

ROOT = Path(__file__).resolve().parents[1]


def _docs(tmp_path):
    root = tmp_path / "docs"
    (root / "api").mkdir(parents=True)
    (root / "README.md").write_text(
        "# Project Guide\n\nAuthentication uses signed tokens and rate limits.",
        encoding="utf-8")
    (root / "api" / "auth.md").write_text(
        "# Auth API\n\nThe authentication endpoint verifies signed tokens.",
        encoding="utf-8")
    (root / "api" / "billing.md").write_text(
        "# Billing\n\nInvoices are generated monthly for paid accounts.",
        encoding="utf-8")
    return root


def test_tokenize_filters_stopwords():
    tokens = tokenize("The authentication endpoint verifies SIGNED tokens.")
    assert "authentication" in tokens and "signed" in tokens
    assert "the" not in tokens


def test_build_pack_indexes_docs(tmp_path):
    pack = build_pack(_docs(tmp_path), "guide")
    assert pack["name"] == "guide" and pack["doc_count"] == 3
    assert "authentication" in pack["inverted"]
    assert pack["avg_length"] > 0


def test_search_ranks_relevant_docs(tmp_path):
    pack = build_pack(_docs(tmp_path), "guide")
    result = search(pack, "authentication signed tokens", limit=3)
    assert len(result["hits"]) >= 2
    top = result["hits"][0]
    assert "auth" in top["path"] or "README" in top["path"]
    assert top["score"] > 0
    assert top["matched"]
    assert result["terms"]


def test_search_no_terms(tmp_path):
    pack = build_pack(_docs(tmp_path), "guide")
    assert search(pack, "the and")["hits"] == []


def test_store_roundtrip(tmp_path):
    store = DocPackStore(tmp_path)
    pack = build_pack(_docs(tmp_path), "guide")
    store.save(pack)
    assert store.list() == ["guide"]
    assert store.load("guide")["doc_count"] == 3


def test_capability_integration(tmp_path):
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    root = str(_docs(tmp_path))
    built = invoke("cowork.docpack.build",
                   {"root": root, "name": "guide",
                    "state_root": str(tmp_path / "state")}, context={})["result"]
    assert built["doc_count"] == 3
    found = invoke("cowork.docpack.search",
                   {"name": "guide", "query": "authentication",
                    "state_root": str(tmp_path / "state")}, context={})["result"]
    assert found["hits"]


def test_cli_docpack(tmp_path):
    import os
    state = tmp_path / "state"
    env = {**os.environ, "KEEL_STATE_DIR": str(state)}
    root = _docs(tmp_path)
    build = subprocess.run(
        [sys.executable, "-m", "keel", "docpack", "build", "guide", str(root)],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert build.returncode == 0, build.stderr
    assert json.loads(build.stdout)["doc_count"] == 3
    found = subprocess.run(
        [sys.executable, "-m", "keel", "docpack", "search", "guide",
         "authentication", "--limit", "2"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert found.returncode == 0, found.stderr
    assert json.loads(found.stdout)["hits"]

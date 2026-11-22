"""B2.7 — offline documentation packs that the agent can actually search.

Builds an on-disk BM25 index over local Markdown documentation and answers
queries with ranked hits and highlighted snippets. Everything is local and
deterministic: no embeddings, no model, no network, no paid dependency. The
earlier ``misc_features.offline_doc_pack`` only enumerated file paths.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_STOPWORDS = frozenset({
    "the", "and", "for", "that", "with", "this", "from", "are", "but",
    "not", "you", "your", "how", "what", "when", "where", "which", "can",
    "into", "about", "then", "they", "them", "have", "has", "was", "were",
})
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    return [t for t in (m.group(0).lower() for m in _TOKEN.finditer(text or ""))
            if len(t) > 1 and t not in _STOPWORDS]


def build_pack(root: str | Path, name: str, *, max_files: int = 500) -> dict:
    """Scan Markdown files under *root* and return a serializable BM25 index."""
    path = Path(root)
    if not path.is_dir():
        raise ValueError(f"not a directory: {root}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        raise ValueError("invalid pack name")
    files = sorted(path.rglob("*.md"))[:max(1, int(max_files))]
    docs = []
    for file in files:
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        first = next((line.strip("# ").strip() for line in text.splitlines()
                      if line.strip().startswith("#")), file.stem)
        tokens = tokenize(text)
        docs.append({"path": str(file), "title": first, "text": text,
                     "tokens": tokens, "length": len(tokens)})
    inverted: dict[str, dict[str, list[int]]] = defaultdict(dict)
    for doc in docs:
        positions: dict[str, list[int]] = defaultdict(list)
        for index, token in enumerate(doc["tokens"]):
            positions[token].append(index)
        for token, pos in positions.items():
            inverted[token][doc["path"]] = pos
    total_tokens = sum(d["length"] for d in docs)
    return {
        "name": name,
        "root": str(path),
        "doc_count": len(docs),
        "avg_length": (total_tokens / len(docs)) if docs else 0.0,
        "documents": docs,
        "inverted": dict(inverted),
    }


def search(pack: dict, query: str, *, limit: int = 5) -> dict:
    """Rank pack documents for *query* with BM25 and return snippets."""
    terms = tokenize(query)
    docs = pack.get("documents", [])
    inverted = pack.get("inverted", {})
    if not terms or not docs:
        return {"query": query, "hits": [], "terms": terms}
    avg = pack.get("avg_length") or 1.0
    n = len(docs)
    length_by_path = {d["path"]: d["length"] for d in docs}
    text_by_path = {d["path"]: d["text"] for d in docs}
    title_by_path = {d["path"]: d["title"] for d in docs}
    scores: dict[str, float] = defaultdict(float)
    for term in terms:
        postings = inverted.get(term, {})
        df = len(postings)
        idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        for path, positions in postings.items():
            tf = len(positions)
            dl = length_by_path.get(path, 0)
            denom = tf + _K1 * (1 - _B + _B * dl / avg)
            scores[path] += idf * (tf * (_K1 + 1)) / denom if denom else 0.0
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    hits = []
    for path, score in ranked[:max(1, int(limit))]:
        text = text_by_path.get(path, "")
        hit_terms = [t for t in terms if t in inverted and path in inverted[t]]
        lower = text.lower()
        start = min((lower.find(t) for t in hit_terms if lower.find(t) >= 0),
                    default=0)
        snippet = text[max(0, start - 80):start + 220].strip()
        hits.append({
            "path": path, "title": title_by_path.get(path, ""),
            "score": round(score, 4), "snippet": snippet,
            "matched": hit_terms,
        })
    return {"query": query, "terms": terms, "hits": hits,
            "doc_count": n}


class DocPackStore:
    """Persist and retrieve built documentation packs in local state."""

    def __init__(self, state_root: str | Path):
        self.root = Path(state_root) / "docpacks"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            raise ValueError("invalid pack name")
        return self.root / f"{name}.json"

    def save(self, pack: dict) -> Path:
        path = self._path(pack["name"])
        path.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> dict:
        path = self._path(name)
        if not path.is_file():
            raise KeyError(name)
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))

"""Local RAG knowledge bases over folders (B2.6).

Deterministic lexical embeddings (TF-IDF style) with no cloud model and no
mandatory dependency. Indexes are JSON files under the Keel state directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
    "build", "release", ".pytest_cache",
})
TEXT_SUFFIXES = frozenset({".md", ".txt", ".py", ".js", ".ts", ".json",
                           ".yaml", ".yml", ".csv", ".rst", ".html"})
_WORD = re.compile(r"[A-Za-z0-9_]+")


def chunk_text(text: str, *, size: int = 800, overlap: int = 100) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(words), step):
        piece = " ".join(words[start:start + size])
        if piece:
            chunks.append(piece)
        if start + size >= len(words):
            break
    return chunks


def tokenize(text: str) -> Counter:
    return Counter(word.lower() for word in _WORD.findall(text))


class KnowledgeBase:
    def __init__(self, state_root: str, name: str = "default"):
        self.root = Path(state_root)
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64] or "default"
        self.path = self.root / "rag" / f"{safe}.json"

    def documents(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return doc.get("chunks", []) if isinstance(doc, dict) else []

    def index(self, folder: str | Path, *, max_files: int = 500) -> dict:
        root = Path(folder).resolve()
        chunks: list[dict] = []
        files = 0
        if root.is_file():
            paths = [root]
        else:
            paths = []
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                paths.append(path)
                if len(paths) >= max_files:
                    break
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files += 1
            for number, piece in enumerate(self.chunk(text)):
                counters = tokenize(piece)
                digest = hashlib.sha256(
                    (str(path) + piece).encode("utf-8")).hexdigest()[:16]
                chunks.append({
                    "id": digest,
                    "source": str(path),
                    "chunk": number,
                    "text": piece[:2000],
                    "tokens": dict(counters),
                })
        idf = Counter()
        for chunk in chunks:
            for word in chunk["tokens"]:
                idf[word] += 1
        doc = {
            "name": self.path.stem,
            "folder": str(root),
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": files,
            "idf": dict(idf),
            "chunks": chunks,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        return {"files": files, "chunks": len(chunks)}

    def chunk(self, text: str) -> list[str]:
        return chunk_text(text)

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        chunks = self.documents()
        if not chunks:
            return []
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        idf = doc.get("idf", {}) or {}
        q = tokenize(query)
        results = []
        for chunk in chunks:
            tokens = Counter(chunk.get("tokens", {}))
            score = 0.0
            for word, count in q.items():
                if word in tokens:
                    weight = math.log(1 + len(chunks) / (1 + idf.get(word, 1)))
                    score += count * tokens[word] * weight
            if score:
                results.append((score, chunk))
        results.sort(key=lambda item: item[0], reverse=True)
        return [{"score": round(score, 4), "source": chunk["source"],
                 "text": chunk["text"]}
                for score, chunk in results[:max(1, limit)]]

"""C6 — episodic/semantic/procedural memory, importance decay, consolidation."""

from __future__ import annotations

import pytest

from keel.memory import MemoryStore
from keel.memory_types import TypedMemory


def test_typed_memory(tmp_path):
    typed = TypedMemory(MemoryStore(str(tmp_path)))
    typed.remember("semantic", "Keel is local-first")
    typed.remember("episodic", "fixed the bug")
    assert len(typed.recall_kind("semantic")) == 1
    assert len(typed.recall_kind("episodic")) == 1
    with pytest.raises(ValueError):
        typed.remember("other", "x")


def test_importance_decay():
    assert TypedMemory.importance_decay(1.0, 0) == 1.0
    assert TypedMemory.importance_decay(1.0, 30) == 0.5
    assert TypedMemory.importance_decay(1.0, 60) == 0.25


def test_importance_scoring_and_dreaming(tmp_path):
    typed = TypedMemory(MemoryStore(str(tmp_path)))
    record = typed.remember("semantic", "scored", tags=["a", "b"])
    assert typed.importance(record) > 1.0
    result = typed.dreaming()
    assert result["remaining"] == 1


def test_consolidation(tmp_path):
    typed = TypedMemory(MemoryStore(str(tmp_path)))
    typed.remember("semantic", "duplicate fact")
    typed.remember("semantic", "Duplicate Fact")
    assert typed.consolidate() == 1
    assert len(typed.recall_kind("semantic")) == 1

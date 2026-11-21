"""B4.10/C1.6 — persistent agent profile management."""

from __future__ import annotations

from pathlib import Path

from keel.agent_profiles import AgentProfiles


def test_profile_lifecycle_and_persistence(tmp_path):
    manager = AgentProfiles(tmp_path)
    work = manager.create("work", agents=["cowork", "code"], layout="split")
    personal = manager.create("personal", agents=["cowork"], layout="single")
    assert work["data_dir"] != personal["data_dir"]
    assert Path(work["data_dir"]).is_dir()
    assert manager.active()["name"] == "work"  # first is active

    assert manager.activate("personal") is True
    assert manager.active()["name"] == "personal"
    assert manager.activate("missing") is False

    # persistence across instances
    restored = AgentProfiles(tmp_path)
    assert len(restored.list()) == 2
    assert restored.active()["name"] == "personal"


def test_agent_details_and_removal(tmp_path):
    manager = AgentProfiles(tmp_path)
    manager.create("work", agents=["cowork", "code"])
    details = manager.agent_details("work")
    assert len(details) == 2 and all(d["color"].startswith("#") for d in details)
    assert manager.agent_details("missing") == []
    assert manager.remove("work") is True
    assert manager.remove("work") is False
    assert manager.list() == []

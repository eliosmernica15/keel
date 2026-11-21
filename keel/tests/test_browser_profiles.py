"""A2.3 — persistent per-agent browser profiles and workspace folders."""

from __future__ import annotations

from keel.browser_profiles import BrowserProfiles


def test_profile_is_persistent_and_isolated(tmp_path):
    profiles = BrowserProfiles(tmp_path)
    a = profiles.profile("agent-a")
    b = profiles.profile("agent-b")
    assert a["profile_dir"] != b["profile_dir"]
    assert a["agent"] == "agent-a"

    # A new manager sees the same on-disk profiles.
    again = BrowserProfiles(tmp_path).profile("agent-a")
    assert again["profile_dir"] == a["profile_dir"]


def test_profile_dirs_exist(tmp_path):
    from pathlib import Path

    entry = BrowserProfiles(tmp_path).profile("writer")
    assert Path(entry["profile_dir"]).is_dir()
    assert Path(entry["workspace"]).is_dir()


def test_reset_and_list(tmp_path):
    profiles = BrowserProfiles(tmp_path)
    profiles.profile("a")
    profiles.profile("b")
    assert len(profiles.list_profiles()) == 2
    assert profiles.reset("a") is True
    assert profiles.reset("a") is False
    assert len(profiles.list_profiles()) == 1

"""A2.3 — real persistent browser profile management."""

from __future__ import annotations

from keel.browser_launch import find_browser, launch_command, prepare_profile


def test_profile_isolated_and_persistent(tmp_path):
    first = prepare_profile(tmp_path, "scout")
    second = prepare_profile(tmp_path, "writer")
    assert first != second
    assert first.is_dir() and (first / "README.txt").is_file()
    assert prepare_profile(tmp_path, "scout") == first


def test_launch_command_uses_profile_and_debug_port(tmp_path):
    profile = prepare_profile(tmp_path, "scout")
    args = launch_command("chrome", profile, url="https://example.test",
                          debug_port=9222)
    assert f"--user-data-dir={profile}" in args
    assert "--remote-debugging-port=9222" in args
    assert args[-1] == "https://example.test"


def test_find_browser_returns_path_or_none():
    found = find_browser()
    assert found is None or Path(found).exists()


from pathlib import Path  # noqa: E402

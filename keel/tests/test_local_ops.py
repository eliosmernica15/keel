"""Real local operations from descriptors (A1/A2/A3)."""

from __future__ import annotations

import time

from keel.local_ops import (IdleManager, config_reference, gc_temp_dirs,
                            generate_env_example, inline_shell_command,
                            open_editor_command, prune_old_versions,
                            resolve_instruction_globs, small_model_roles)


def test_instruction_globs_and_roles(tmp_path):
    (tmp_path / "GUIDE.md").write_text("x", encoding="utf-8")
    found = resolve_instruction_globs(tmp_path, ["*.md", "https://x/g.md"])
    assert any(item["kind"] == "file" for item in found)
    assert any(item["kind"] == "url" and "approval" in item["note"]
               for item in found)
    assert small_model_roles()["override_supported"] is True


def test_prune_inline_and_editor():
    result = prune_old_versions(["0.1.0", "0.2.0", "0.3.0", "0.4.0"], keep=2)
    assert result["remove"] == ["0.1.0", "0.2.0"]
    assert inline_shell_command("!git status")["kind"] == "shell"
    assert inline_shell_command("hello")["kind"] == "prompt"
    assert open_editor_command("a.py", editor="vim") == ["vim", "a.py"]


def test_idle_and_config(tmp_path):
    manager = IdleManager(timeout_s=10)
    manager.touch(now=0)
    assert manager.check(now=5) is False
    assert manager.check(now=11) is True
    manager.touch(now=12)
    assert "wake" in manager.events
    ref = config_reference({"KEEL_TEST": "x", "OTHER": "y"})
    assert ref == {"KEEL_TEST": "set"}


def test_env_and_gc(tmp_path):
    env = generate_env_example(tmp_path / ".env.example", ["KEEL_TOKEN"])
    assert "KEEL_TOKEN=" in env.read_text()
    old = tmp_path / "temp" / "old"
    old.mkdir(parents=True)
    os.utime(old, (time.time() - 100000,) * 2)
    removed = gc_temp_dirs(tmp_path / "temp", max_age_s=1000)
    assert "old" in removed


import os  # noqa: E402

"""B2.2/B2.14/B2.15 — macro recording, prompt improvement, spec scaffold."""

from __future__ import annotations

import json

from keel.authoring import improve_prompt, record_macro, save_macro, spec_scaffold


def test_macro_recording_and_save(tmp_path):
    transcript = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "write_file",
             "input": {"path": "a.txt"}}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "read_file", "input": {},
             "is_error": True}]}},
    ]
    macro = record_macro("setup", transcript)
    assert len(macro["steps"]) == 1 and macro["steps"][0]["tool"] == "write_file"
    path = save_macro(macro, tmp_path)
    assert json.loads(path.read_text())[0]["name"] == "setup"


def test_prompt_improvement():
    result = improve_prompt("do thing")
    assert len(result["suggestions"]) >= 2
    assert "Verify" in result["improved"]


def test_spec_scaffold():
    scaffold = spec_scaffold("add search")
    assert scaffold["approval_gate"] is True
    assert scaffold["tasks"][-1] == "verify"

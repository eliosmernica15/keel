"""B2.8 — real notebook execution, inline charts and persistence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keel.notebook import (NotebookStore, execute_notebook,
                           parse_notebook, render_html, render_markdown)

ROOT = Path(__file__).resolve().parents[1]


def test_parse_notebook_cells():
    cells = parse_notebook("intro\n```python\nx=1\n```\nmore\n```\ny=2\n```\nend")
    assert [c["kind"] for c in cells] == ["text", "code", "text", "code", "text"]
    assert cells[1]["source"] == "x=1"
    assert cells[0]["source"] == "intro"


def test_execute_captures_output_and_persists_state():
    src = ("```python\n"
           "x = 10\n"
           "print('value', x)\n"
           "```\n\n"
           "```python\n"
           "print('again', x + 5)\n"
           "```\n")
    result = execute_notebook(src)
    assert result["ok"] is True
    assert result["code_cell_count"] == 2
    outputs = [o["text"] for c in result["cells"]
               if c["kind"] == "code" for o in c["outputs"]]
    assert "value 10" in outputs[0]
    assert "again 15" in outputs[1]


def test_error_is_isolated_between_cells():
    src = ("```python\nprint('before')\n```\n"
           "```python\nraise ValueError('boom')\n```\n"
           "```python\nprint('after')\n```\n")
    result = execute_notebook(src)
    assert result["ok"] is False
    assert any("boom" in e for e in result["errors"])
    outputs = [o["text"] for c in result["cells"]
               if c["kind"] == "code" for o in c["outputs"]]
    assert "before" in outputs[0]
    assert "after" in outputs[2]


def test_inline_charts_render_svg():
    src = ("```python\n"
           "chart('bar', [3, 7, 2], ['a', 'b', 'c'])\n"
           "chart('sparkline', [1, 3, 2, 5])\n"
           "```\n")
    result = execute_notebook(src)
    assert result["ok"] is True
    assert result["chart_count"] == 2
    assert result["html"].count("<svg") == 2
    assert "[inline chart: bar]" in result["markdown"]


def test_sandbox_denies_filesystem_write():
    src = ("```python\n"
           "import pathlib\n"
           "pathlib.Path('C:/Windows/keel_evil.txt').write_text('x')\n"
           "```\n")
    result = execute_notebook(src)
    assert result["ok"] is False
    assert "sandbox" in result["sandbox_stderr"].lower() or result["errors"]


def test_notebook_store_roundtrip_and_recoverable_delete(tmp_path):
    store = NotebookStore(tmp_path)
    assert store.list() == []
    doc = store.save("analysis", "# Report\n```python\nprint(1)\n```")
    assert doc["name"] == "analysis"
    assert store.list() == ["analysis"]
    assert "Report" in store.load("analysis")
    meta = store.delete("analysis")
    assert meta["original_path"].endswith("analysis.json")
    assert store.list() == []


def test_notebook_store_rejects_bad_name(tmp_path):
    store = NotebookStore(tmp_path)
    try:
        store.save("../escape", "x")
    except ValueError:
        pass
    else:
        raise AssertionError("bad notebook name accepted")


def test_capability_integration():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    result = invoke("cowork.notebook.execute",
                    {"source": "```python\nprint('cap')\n```"}, context={})
    assert result["ok"] is True
    assert "cap" in result["result"]["markdown"]


def test_cli_notebook_run(tmp_path):
    nb = tmp_path / "report.md"
    nb.write_text("```python\nprint('cli-ok')\n```", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "run", str(nb)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "cli-ok" in proc.stdout


def test_cli_notebook_persistence(tmp_path):
    state = tmp_path / "state"
    nb = tmp_path / "report.md"
    nb.write_text("# stored", encoding="utf-8")
    env = {"KEEL_STATE_DIR": str(state)}
    import os
    env = {**os.environ, **env}
    saved = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "save", "demo", str(nb)],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert saved.returncode == 0, saved.stderr
    listed = subprocess.run(
        [sys.executable, "-m", "keel", "notebook", "list"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
    assert "demo" in listed.stdout

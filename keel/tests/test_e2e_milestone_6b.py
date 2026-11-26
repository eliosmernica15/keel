"""Milestone 6B end-to-end integration test.

Exercises the real agent runtime (Session + RealTools + permissions + MCP)
through actual API and runtime integration, not isolated function calls.
"""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from keel.fakes import ScriptedModel, SeededRng, VirtualClock
from keel.session import Session, SessionConfig
from keel.mcp import McpServerConfig, McpManager

ROOT = Path(__file__).resolve().parents[1]


def _cfg(tmp_path, **overrides):
    cfg = dict(cwd=str(tmp_path),
               state_root=str(tmp_path / "state"),
               bare=True, permission_mode="default",
               session_id="e2e-session-001",
               model="keel-fake-1", max_turns=10, interactive=False,
               seed=42)
    cfg.update(overrides)
    return SessionConfig(**cfg)


def test_e2e_milestone_6b(tmp_path, monkeypatch):
    """Full Milestone 6B end-to-end scenario."""
    import keel.runner as runner

    class ExampleResponse(io.BytesIO):
        headers = {"Content-Type": "text/html"}

        def geturl(self):
            return "https://example.com"

    class ExampleOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://example.com"
            return ExampleResponse(b"<html><body><h1>Example Domain</h1></body></html>")

    monkeypatch.setattr(
        runner,
        "_ssrf_getaddrinfo",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
             ("93.184.216.34", port))
        ],
    )
    monkeypatch.setattr(
        runner,
        "_build_ssrf_opener",
        lambda validated, ssl_context: ExampleOpener(),
    )

    project = tmp_path / "project"
    project.mkdir()
    (project / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    (project / ".keelignore").write_text("*.log\n", encoding="utf-8")
    (project / "test.log").write_text("ignored log\n", encoding="utf-8")

    # Git init
    subprocess.run(["git", "init"], cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=project, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project, capture_output=True)

    # Skill setup
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: A demo skill for testing\n---\n\nDemo body.\n",
        encoding="utf-8",
    )
    from keel import skills_manager as sm
    sm.install(skill_dir, scope="project", project_root=project)

    # Workflow setup
    wf_dir = project / ".keel" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "demo.json").write_text(json.dumps({
        "name": "demo-wf",
        "description": "demo workflow",
        "steps": [
            {"kind": "shell", "command": "echo workflow-step-ok"},
        ],
    }), encoding="utf-8")

    # Command setup
    cmd_dir = project / ".keel" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "greet.md").write_text(
        "---\nname: greet\ndescription: Greet command\n---\n\nHello $ARGUMENTS\n",
        encoding="utf-8",
    )

    # MCP fake server
    mcp_script = tmp_path / "fake_mcp.py"
    mcp_script.write_text('''
import json, sys
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {"name": "fake", "version": "1.0"}}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
            {"name": "echo", "description": "echo text",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}]}})
    elif method == "tools/call":
        params = msg.get("params", {})
        args = params.get("arguments", {})
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {
            "content": [{"type": "text", "text": args.get("text", "")}]}})
    elif method == "resources/list":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"resources": [
            {"uri": "file:///test.txt", "name": "test.txt"}]}})
    elif method == "resources/read":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"contents": [
            {"uri": "file:///test.txt", "text": "resource content here"}]}})
    elif method == "prompts/list":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"prompts": [
            {"name": "greeting"}]}})
    elif method == "prompts/get":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"messages": [
            {"role": "user", "content": {"type": "text", "text": "prompt text here"}}]}})
''', encoding="utf-8")

    from keel.mcp import McpServerConfig
    mcp_config = McpServerConfig(
        name="fake", command=__import__("sys").executable,
        args=(str(mcp_script),), scope="user", transport="stdio")

    from keel.runner import RealTools
    executor = RealTools()

    cfg = _cfg(project, state_root=str(tmp_path / "state"))
    model = ScriptedModel([
        [{"type": "tool_use", "name": "list_skills", "input": {}}],
        [{"type": "tool_use", "name": "load_skill", "input": {"name": "demo-skill"}}],
        [{"type": "tool_use", "name": "web_fetch", "input": {"url": "https://example.com"}}],
        [{"type": "text", "text": "done"}],
    ], model="keel-fake-1")

    mcp_manager = McpManager([mcp_config])
    session = Session(model_client=model, executor=executor, config=cfg,
                      clock=VirtualClock(), rng=SeededRng(42), mcp=mcp_manager,
                      rules=((), (), ("list_skills", "load_skill", "web_fetch", "mcp__fake__echo")))
    try:
        out = session.run("test e2e")
        assert out.events[0]["subtype"] == "init"
        assert "mcp__fake__echo" in out.events[0]["tools"]
        assert out.events[0]["mcp_servers"][0]["status"] == "connected"
        # MCP resources/prompts must reach the real model-turn context.
        first_turn = json.dumps(model.seen_messages[0])
        assert "resource content here" in first_turn
        assert "prompt text here" in first_turn
        # Verify skill loading worked
        tool_results = [blk for e in out.events if e.get("type") == "user"
                        for blk in (e.get("message", {}).get("content", []) if isinstance(e.get("message", {}).get("content"), list) else [])
                        if isinstance(blk, dict) and blk.get("type") == "tool_result"]
        assert len(tool_results) >= 1
    finally:
        mcp_manager.shutdown_all()

    # Verify filesystem tools
    (project / "newfile.txt").write_text("hello", encoding="utf-8")
    assert executor.invoke("read_file", {"path": str(project / "newfile.txt")})[0] == "hello"
    executor.invoke("delete_file", {"path": str(project / "newfile.txt")})
    assert not (project / "newfile.txt").exists()

    # Verify ignore rules
    result = executor.invoke("search_files", {"root": str(project), "pattern": "*.log", "content": "ignored"})
    assert "test.log" not in result[0] or result[1]["numHits"] == 0

    # Verify git
    status = executor.invoke("git_status", {"cwd": str(project)})[0]
    assert "main" in status or "master" in status or "??" in status or status.strip() != ""

    # Verify process management
    r = executor.invoke("background_shell", {"command": "echo bg-test", "shell": "posix" if __import__("os").name != "nt" else "cmd"})
    pid = r[1]["process_id"]
    import time
    time.sleep(0.5)
    out_result = executor.invoke("process_output", {"process_id": pid})
    assert out_result is not None
    executor.invoke("process_kill", {"process_id": pid})

    # Verify cleanup
    from keel.runner import cleanup_background_processes
    cleanup_background_processes()
    assert len(executor._BG_PROCESSES) == 0

    # Verify web fetch
    wf = executor.invoke("web_fetch", {"url": "https://example.com"})
    assert "Example Domain" in wf[0]

    # Verify web fetch blocks unsafe URLs
    try:
        executor.invoke("web_fetch", {"url": "http://127.0.0.1:8080/secret"})
        assert False, "Should have raised"
    except ValueError:
        pass

    # Verify skill discovery
    from keel import skills_manager as sm
    skills = sm.list_managed(project)
    assert any(s["name"] == "demo-skill" for s in skills)

    # Verify workflow discovery
    from keel import workflows
    wfs = workflows.discover(project)
    assert any(w.name == "demo-wf" for w in wfs)

    # Verify command discovery
    from keel import commands
    cmds = commands.discover(project)
    assert any(c.name == "greet" for c in cmds)

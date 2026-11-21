"""Registers all local modules as invokable capabilities.

Kept separate from capabilities.py so the core stays small. Importing this
module populates the global capability registry.
"""

from __future__ import annotations

import json
from pathlib import Path

from .capabilities import CapabilityError, capability


def _s(state_root, *parts):
    """State-root helper."""
    return Path(state_root or ".keel").joinpath(*parts)


def _resolve(value: str, ctx: dict) -> str:
    """Resolve a user-provided path against the context cwd when relative."""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((Path(ctx.get("cwd") or ".") / path).resolve())


# ---------------------------------------------------------------- core/system
@capability("core.hardware.detect", "hardware", "core", "read",
            "Detect local hardware capabilities")
def _hardware_detect(p, ctx):
    from .hardware import detect
    return detect()


@capability("core.hardware.advise_quantization", "hardware", "core", "read",
            "Recommend model quantization for available RAM",
            schema={"type": "object", "properties": {
                "params_b": {"type": "number"}}, "required": ["params_b"]})
def _hardware_advise(p, ctx):
    from .hardware import advise_quantization
    return advise_quantization(float(p["params_b"]), p.get("info"))


@capability("core.config.reference", "local_ops", "core", "read",
            "List KEEL_* environment overrides (values masked)")
def _config_reference(p, ctx):
    from .local_ops import config_reference
    return config_reference()


@capability("core.config.inline_shell", "local_ops", "core", "read",
            "Parse an inline !cmd shell request")
def _inline_shell(p, ctx):
    from .local_ops import inline_shell_command
    return inline_shell_command(str(p.get("text", "")))


@capability("core.config.editor_command", "local_ops", "core", "read",
            "Build an editor launch command")
def _editor_command(p, ctx):
    from .local_ops import open_editor_command
    return open_editor_command(str(p.get("path", "")), editor=p.get("editor", ""))


@capability("core.env.example", "ops_tools", "core", "write",
            "Generate a .env.example with placeholders", mutates=True)
def _env_example(p, ctx):
    from .ops_tools import setup_env_example
    return {"path": str(setup_env_example(
        _s(ctx.get("state_root"), ".env.example"), p.get("keys", [])))}


@capability("core.version.prune", "local_ops", "core", "read",
            "Compute old versions eligible for removal")
def _prune(p, ctx):
    from .local_ops import prune_old_versions
    return prune_old_versions(p.get("versions", []), int(p.get("keep", 3)))


@capability("core.repro.manifest", "build_repro", "core", "read",
            "Build a deterministic build manifest")
def _repro(p, ctx):
    from .build_repro import build_manifest
    m = build_manifest(str(p.get("version", "")), str(p.get("platform", "")),
                       p.get("inputs", {}))
    return {"version": m.version, "platform": m.platform, "digest": m.digest}


@capability("core.diagnostics", "diagnostics", "core", "read",
            "Collect redacted local diagnostics")
def _diagnostics(p, ctx):
    from .diagnostics import collect
    return collect()


@capability("core.error.catalog", "onboarding", "core", "read",
            "Look up a stable error code and fix steps")
def _error_catalog(p, ctx):
    from .onboarding import error_info
    return error_info(str(p.get("code", "")))


@capability("core.contextual_help", "onboarding", "core", "read",
            "Get contextual help for an error code")
def _context_help(p, ctx):
    from .onboarding import contextual_help
    return {"help": contextual_help(str(p.get("code", "")))}


@capability("core.feedback.export", "onboarding", "core", "read",
            "Export locally stored feedback (redacted)")
def _feedback_export(p, ctx):
    from .onboarding import FeedbackStore
    store = FeedbackStore(_s(ctx.get("state_root")))
    return {"entries": store.path.is_file() and [
        json.loads(line) for line in store.path.read_text().splitlines()
        if line.strip()] or []}


@capability("core.flags.list", "feature_flags", "core", "read",
            "List feature flags and kill switches")
def _flags_list(p, ctx):
    from .feature_flags import FeatureFlags
    return FeatureFlags(_s(ctx.get("state_root"))).all()


@capability("core.flags.set", "feature_flags", "core", "write",
            "Set a feature flag (kill switch)", mutates=True)
def _flags_set(p, ctx):
    from .feature_flags import FeatureFlags
    return FeatureFlags(_s(ctx.get("state_root"))).set(
        str(p["name"]), bool(p.get("enabled")),
        kill_switch=bool(p.get("kill_switch")))


@capability("core.performance.budgets", "performance_budgets", "core", "read",
            "Check measurements against performance budgets")
def _budgets(p, ctx):
    from .performance_budgets import all_within, check
    results = check(p.get("measurements", {}))
    return {"within": all_within(results),
            "results": [r.__dict__ for r in results]}


@capability("core.ci.kickoff", "ci_helpers", "core", "read",
            "Get a milestone kickoff prompt with stop condition")
def _kickoff(p, ctx):
    from .ci_helpers import kickoff_prompt
    return {"prompt": kickoff_prompt(str(p.get("milestone", "")))}


@capability("core.ci.accessibility_gate", "ci_helpers", "core", "read",
            "Evaluate accessibility CI results")
def _a11y_gate(p, ctx):
    from .ci_helpers import accessibility_gate
    return {"pass": accessibility_gate(p.get("results", {}))}


@capability("core.ci.flaky_quarantine", "ci_helpers", "core", "write",
            "Quarantine a flaky test with owner and expiry", mutates=True)
def _flaky(p, ctx):
    from .ci_helpers import FlakyQuarantine
    q = FlakyQuarantine(_s(ctx.get("state_root")))
    return q.add(str(p["test"]), str(p.get("owner", "")),
                 days=int(p.get("days", 14)))


@capability("core.golden.check", "golden", "core", "read",
            "Check text against a golden snapshot")
def _golden(p, ctx):
    from .golden import check_golden
    return {"match": check_golden(
        str(p.get("text", "")), str(p.get("path", "")),
        update=bool(p.get("update")))}


@capability("core.redteam.suite", "red_team", "core", "read",
            "Run the deterministic local red-team suite")
def _redteam(p, ctx):
    from .red_team import run_suite
    return run_suite()


@capability("core.trust.injection", "trust_tools", "core", "read",
            "Classify text for prompt-injection patterns")
def _injection(p, ctx):
    from .trust_tools import classify_injection
    return classify_injection(str(p.get("text", "")))


@capability("core.trust.audit_verify", "trust_tools", "core", "read",
            "Verify an audit bundle checksum")
def _audit_verify(p, ctx):
    from .trust_tools import verify_audit_bundle
    return {"valid": verify_audit_bundle(str(p.get("path", "")))}


@capability("core.trust.audit_create", "trust_tools", "core", "write",
            "Create a verifiable audit bundle", mutates=True)
def _audit_create(p, ctx):
    from .trust_tools import audit_bundle
    path = audit_bundle(_s(ctx.get("state_root")), p.get("events", []))
    return {"path": str(path)}


@capability("core.audit.bundles", "diagnostics", "core", "read",
            "Get local diagnostics bundle status")
def _diag_status(p, ctx):
    from .diagnostics import collect
    return {"available": bool(collect()), "note": "local diagnostics"}


@capability("core.audit.capability_log", "capabilities", "core", "read",
            "Read the capability invocation audit log")
def _cap_log(p, ctx):
    from .capabilities import audit_path
    path = audit_path(_s(ctx.get("state_root")))
    if not path.is_file():
        return {"entries": []}
    return {"entries": [json.loads(line) for line in
                        path.read_text().splitlines() if line.strip()][-200:]}


# ---------------------------------------------------------------- cowork
@capability("cowork.doc.read", "documents", "cowork", "read",
            "Read text from a DOCX file")
def _docx_read(p, ctx):
    from .documents import read_docx
    return {"text": read_docx(_resolve(str(p.get("path", "")), ctx))}


@capability("cowork.doc.write", "documents", "cowork", "write",
            "Write a DOCX file", mutates=True)
def _docx_write(p, ctx):
    from .documents import write_docx
    return {"path": str(write_docx(_resolve(str(p["path"]), ctx),
                                   str(p.get("text", ""))))}


@capability("cowork.sheet.read", "documents", "cowork", "read",
            "Read an XLSX worksheet")
def _xlsx_read(p, ctx):
    from .documents import read_xlsx
    return {"grid": read_xlsx(_resolve(str(p.get("path", "")), ctx),
                              sheet=int(p.get("sheet", 0)))}


@capability("cowork.sheet.write", "documents", "cowork", "write",
            "Write an XLSX workbook", mutates=True)
def _xlsx_write(p, ctx):
    from .documents import write_xlsx
    return {"path": str(write_xlsx(_resolve(str(p["path"]), ctx),
                                   p.get("rows", [])))}


@capability("cowork.sheet.stats", "documents", "cowork", "read",
            "Compute numeric column statistics for a grid")
def _sheet_stats(p, ctx):
    from .documents import spreadsheet_stats
    return spreadsheet_stats(p.get("grid", []))


@capability("cowork.csv.convert", "documents", "cowork", "read",
            "Convert CSV text to a grid")
def _csv(p, ctx):
    from .documents import csv_to_grid, grid_to_csv
    if "grid" in p:
        return {"csv": grid_to_csv(p["grid"])}
    return {"grid": csv_to_grid(str(p.get("text", "")))}


@capability("cowork.doc.qa", "documents", "cowork", "read",
            "Document Q&A with cited offsets")
def _doc_qa(p, ctx):
    from .documents import document_answer
    return {"hits": document_answer(str(p.get("question", "")),
                                    str(p.get("text", "")))}


@capability("cowork.email.compose", "cowork_channels", "cowork", "read",
            "Compose an RFC-5322 email draft")
def _email_compose(p, ctx):
    from .cowork_channels import compose_email
    return compose_email(str(p.get("to", "")), str(p.get("subject", "")),
                         str(p.get("body", "")), cc=p.get("cc", ""))


@capability("cowork.email.send", "cowork_channels", "cowork", "execute",
            "Send an email via the user's SMTP server (dry-run default)")
def _email_send(p, ctx):
    from .cowork_channels import send_email_draft
    return send_email_draft(p.get("draft", {}),
                            host=str(p.get("host", "")),
                            user=str(p.get("user", "")),
                            password=str(p.get("password", "")),
                            dry_run=bool(p.get("dry_run", True)))


@capability("cowork.calendar.parse", "cowork_channels", "cowork", "read",
            "Parse events from an ICS calendar")
def _ics(p, ctx):
    from .cowork_channels import parse_ics
    return {"events": parse_ics(str(p.get("text", "")))}


@capability("cowork.meeting.audio", "cowork_channels", "cowork", "write",
            "Write a WAV meeting recording", mutates=True)
def _wav(p, ctx):
    import base64
    from .cowork_channels import write_wav
    data = base64.b64decode(p.get("b64", ""))
    return {"path": str(write_wav(str(p["path"]), data))}


@capability("cowork.voice.transcribe", "cowork_channels", "cowork", "read",
            "Describe a local transcription job")
def _transcribe(p, ctx):
    from .cowork_channels import transcribe_if_available
    return transcribe_if_available(str(p.get("path", "")), p.get("engine", ""))


@capability("cowork.voice.tasks", "voice_tasks", "cowork", "write",
            "Enqueue a voice-to-task item with confirmation", mutates=True)
def _voice_enqueue(p, ctx):
    from .voice_tasks import VoiceTaskQueue
    q = VoiceTaskQueue(_s(ctx.get("state_root")))
    return q.enqueue(str(p.get("transcript", "")),
                     session_id=str(p.get("session_id", "")),
                     confidence=float(p.get("confidence", 1.0)))


@capability("cowork.voice.confirm", "voice_tasks", "cowork", "write",
            "Confirm a queued voice task", mutates=True)
def _voice_confirm(p, ctx):
    from .voice_tasks import VoiceTaskQueue
    q = VoiceTaskQueue(_s(ctx.get("state_root")))
    return q.confirm(str(p["id"])) or {"error": "not found"}


@capability("cowork.notes.backlinks", "content_skills", "cowork", "read",
            "Compute notes-vault backlinks")
def _backlinks(p, ctx):
    from .content_skills import backlinks
    return {"graph": backlinks(p.get("notes", {}))}


@capability("cowork.drafts.create", "content_skills", "cowork", "write",
            "Create a draft-only content skill", mutates=True)
def _draft(p, ctx):
    from .content_skills import DraftStore
    store = DraftStore(_s(ctx.get("state_root")))
    return store.create(str(p.get("kind", "post")), str(p.get("text", "")))


@capability("cowork.db.tables", "db_explorer", "cowork", "read",
            "List tables in a local SQLite database")
def _db_tables(p, ctx):
    from .db_explorer import DBExplorer
    return {"tables": DBExplorer(_resolve(str(p["path"]), ctx)).tables()}


@capability("cowork.db.query", "db_explorer", "cowork", "read",
            "Run a read-only SELECT against a local SQLite database")
def _db_query(p, ctx):
    from .db_explorer import DBExplorer
    return {"rows": DBExplorer(_resolve(str(p["path"]), ctx)).query(
        str(p["sql"]), limit=int(p.get("limit", 100)))}


@capability("cowork.profile.get", "user_profile", "cowork", "read",
            "Read the editable local user profile")
def _profile_get(p, ctx):
    from .user_profile import get
    return get()


@capability("cowork.profile.update", "user_profile", "cowork", "write",
            "Update the local user profile", mutates=True)
def _profile_update(p, ctx):
    from .user_profile import update
    return update(p.get("patch", {}))


@capability("cowork.knowledge.add", "knowledge_graph", "cowork", "write",
            "Add an entity to the local knowledge graph", mutates=True)
def _kg_add(p, ctx):
    from .knowledge_graph import KnowledgeGraph
    return KnowledgeGraph(_s(ctx.get("state_root"))).add_entity(
        str(p["name"]), p.get("kind", "concept"))


@capability("cowork.knowledge.relate", "knowledge_graph", "cowork", "write",
            "Relate two knowledge-graph entities", mutates=True)
def _kg_relate(p, ctx):
    from .knowledge_graph import KnowledgeGraph
    ok = KnowledgeGraph(_s(ctx.get("state_root"))).relate(
        str(p["source"]), str(p["relation"]), str(p["target"]))
    return {"ok": ok}


@capability("cowork.contextpacks.define", "context_packs", "cowork", "write",
            "Define a reusable context pack", mutates=True)
def _cp_define(p, ctx):
    from .context_packs import ContextPackStore
    return ContextPackStore(_s(ctx.get("state_root"))).define(
        str(p["name"]), p.get("files", []), budget=int(p.get("budget", 8000)))


@capability("cowork.contextpacks.status", "context_packs", "cowork", "read",
            "Get context-pack budget status")
def _cp_status(p, ctx):
    from .context_packs import ContextPackStore
    return ContextPackStore(_s(ctx.get("state_root"))).budget_status(str(p["name"]))


@capability("cowork.authoring.improve", "authoring", "cowork", "read",
            "Improve a prompt locally")
def _improve(p, ctx):
    from .authoring import improve_prompt
    return improve_prompt(str(p.get("text", "")))


@capability("cowork.authoring.spec", "authoring", "cowork", "read",
            "Create a spec-driven scaffold")
def _spec(p, ctx):
    from .authoring import spec_scaffold
    return spec_scaffold(str(p.get("goal", "")))


@capability("cowork.rag.search", "rag", "cowork", "read",
            "Search a local RAG knowledge base")
def _rag_search(p, ctx):
    from .rag import KnowledgeBase
    return {"hits": KnowledgeBase(str(p.get("state_root", ctx.get("state_root", ".keel"))),
                                  p.get("name", "default")).search(
        str(p.get("query", "")), limit=int(p.get("limit", 5)))}


@capability("cowork.rag.index", "rag", "cowork", "write",
            "Index a folder into a local RAG knowledge base", mutates=True)
def _rag_index(p, ctx):
    from .rag import KnowledgeBase
    return KnowledgeBase(str(p.get("state_root", ctx.get("state_root", ".keel"))),
                         p.get("name", "default")).index(str(p["folder"]))


@capability("cowork.tutorial.state", "tutorial", "cowork", "read",
            "Get interactive tutorial progress")
def _tutorial(p, ctx):
    from .tutorial import tutorial_state
    return tutorial_state(p.get("completed", []))


# ---------------------------------------------------------------- code
@capability("code.codemod.preview", "codemod", "code", "read",
            "Preview an AST codemod as a unified diff")
def _codemod_preview(p, ctx):
    from .codemod import preview, rename_symbol, replace_call
    kind = p.get("kind", "rename")
    if kind == "replace_call":
        from functools import partial
        fn = partial(replace_call, old_call=p["old_call"], new_call=p["new_call"])
    else:
        from functools import partial
        fn = partial(rename_symbol, old=p["old"], new=p["new"])
    return preview(str(p["path"]), fn)


@capability("code.codemod.apply", "codemod", "code", "write",
            "Apply a verified AST codemod", mutates=True)
def _codemod_apply(p, ctx):
    from .codemod import apply, rename_symbol, replace_call
    from functools import partial
    if p.get("kind") == "replace_call":
        fn = partial(replace_call, old_call=p["old_call"], new_call=p["new_call"])
    else:
        fn = partial(rename_symbol, old=p["old"], new=p["new"])
    return apply(str(p["path"]), fn)


@capability("code.git.status", "git_extras_runtime", "code", "read",
            "Read git status for a repository")
def _git_status(p, ctx):
    from .git_extras_runtime import status
    return {"lines": status(str(p.get("repo", ctx.get("cwd", "."))))}


@capability("code.git.log", "git_extras_runtime", "code", "read",
            "Read git log for a repository")
def _git_log(p, ctx):
    from .git_extras_runtime import log
    return {"lines": log(str(p.get("repo", ctx.get("cwd", "."))),
                         int(p.get("count", 10)))}


@capability("code.git.commit", "git_extras_runtime", "code", "write",
            "Create a stacked git commit (requires allow_write)", mutates=True)
def _git_commit(p, ctx):
    from .git_extras_runtime import stacked_commit
    return {"output": stacked_commit(
        str(p.get("repo", ctx.get("cwd", "."))), str(p["message"]),
        allow_write=bool(p.get("allow_write")))}


@capability("code.sandbox.run", "sandbox_exec", "code", "execute",
            "Run Python in a bounded local subprocess")
def _sandbox_run(p, ctx):
    from .sandbox_exec import run_python
    r = run_python(str(p.get("code", "")), timeout_s=float(p.get("timeout_s", 5)))
    return {"ok": r.ok, "stdout": r.stdout[:4000], "stderr": r.stderr[:4000],
            "exit_code": r.exit_code, "timed_out": r.timed_out}


@capability("code.debug.inspect", "debugger", "code", "read",
            "Run a Python file under the debugger and inspect a stop")
def _debug(p, ctx):
    from .debugger import DebugSession
    session = DebugSession()
    if p.get("breakpoint"):
        session.set_breakpoint(p["breakpoint"], int(p.get("line", 1)))
    stops = session.run_file(str(p["path"]))
    frame = session.inspect(-1)
    return {"stops": len(stops),
            "frame": {"file": frame.file, "line": frame.line,
                      "function": frame.function, "locals": frame.locals}
            if frame else None}


@capability("code.api.spec", "api_tester", "code", "read",
            "Build a saved API request spec")
def _api_spec(p, ctx):
    from .api_tester import http_request_spec
    return http_request_spec(str(p.get("method", "GET")), str(p.get("url", "")),
                              body=p.get("body", ""), headers=p.get("headers"))


@capability("code.api.run", "api_tester", "code", "execute",
            "Execute a saved API request (loopback hosts only)")
def _api_run(p, ctx):
    from .api_tester import APICollection, run_request
    col = APICollection(_s(ctx.get("state_root")))
    col.save_request("__invoke__", str(p.get("method", "GET")),
                     str(p.get("url", "")), p.get("body", ""),
                     p.get("headers"))
    result = run_request("__invoke__", col)
    return result


@capability("code.sarif.to", "sarif", "code", "read",
            "Convert findings to SARIF 2.1.0")
def _sarif_to(p, ctx):
    from .sarif import to_sarif
    return to_sarif(p.get("findings", []))


@capability("code.sarif.from", "sarif", "code", "read",
            "Read findings from a SARIF document")
def _sarif_from(p, ctx):
    from .sarif import from_sarif
    return {"findings": from_sarif(p.get("doc", {}))}


@capability("code.audit.snapshot", "dev_tools", "code", "read",
            "Generate an architecture snapshot from local source")
def _arch(p, ctx):
    from .dev_tools import architecture_snapshot
    return architecture_snapshot(str(p.get("root", ctx.get("cwd", "."))))


@capability("code.security.scan", "dev_tools", "code", "read",
            "Scan a project for clear-text secrets")
def _secscan(p, ctx):
    from .dev_tools import security_scan
    return security_scan(str(p.get("root", ctx.get("cwd", "."))))


@capability("code.issue.plan", "issue_to_change", "code", "read",
            "Turn an issue into a change plan")
def _issue(p, ctx):
    from .issue_to_change import parse_issue, to_change_plan
    return to_change_plan(parse_issue(str(p.get("text", ""))))


@capability("code.interop.openapi", "interop", "code", "read",
            "Generate dormant tool descriptors from an OpenAPI spec")
def _openapi(p, ctx):
    from .interop import openapi_to_tools
    return {"tools": openapi_to_tools(p.get("spec", {}))}


@capability("code.interop.import_mcp", "interop", "code", "read",
            "Normalize another app's MCP config")
def _mcp_import(p, ctx):
    from .interop import import_mcp_config
    return {"servers": import_mcp_config(p.get("doc", {}))}


@capability("code.interop.standards", "interop", "code", "read",
            "List standards support status")
def _standards(p, ctx):
    from .interop import standards_checklist
    return standards_checklist()


@capability("code.web.compile", "markdown_render", "code", "read",
            "Detect and render rich Markdown blocks safely")
def _markdown(p, ctx):
    from .markdown_render import detect_blocks, render_preview
    text = str(p.get("text", ""))
    return {"blocks": [b.__dict__ for b in detect_blocks(text)],
            "html": render_preview(text)}


@capability("code.web.diagram", "charts", "code", "read",
            "Render an offline SVG diagram or chart")
def _chart(p, ctx):
    from .charts import bar_chart, flow_diagram, sparkline
    kind = p.get("kind", "flow")
    if kind == "bar":
        svg = bar_chart(p.get("values", []), p.get("labels"))
    elif kind == "sparkline":
        svg = sparkline(p.get("values", []))
    else:
        svg = flow_diagram(p.get("nodes", []), [tuple(e) for e in p.get("edges", [])])
    return {"svg": svg}


@capability("code.term.record", "terminal_replay", "code", "write",
            "Record a terminal command and output", mutates=True)
def _term_record(p, ctx):
    from .terminal_replay import TerminalRecorder
    r = TerminalRecorder(_s(ctx.get("state_root"), "terminal.jsonl"))
    return r.record(str(p.get("command", "")), str(p.get("output", "")),
                    exit_code=int(p.get("exit_code", 0)))


@capability("code.term.replay", "terminal_replay", "code", "read",
            "Replay recorded terminal entries")
def _term_replay(p, ctx):
    from .terminal_replay import TerminalRecorder
    r = TerminalRecorder(_s(ctx.get("state_root"), "terminal.jsonl"))
    return {"entries": r.entries()}


@capability("code.knowledge.entities", "knowledge_graph", "code", "read",
            "List knowledge-graph entities")
def _kg_list(p, ctx):
    from .knowledge_graph import KnowledgeGraph
    return {"entities": KnowledgeGraph(_s(ctx.get("state_root"))).entities()}


@capability("code.style.learn", "agent_intelligence", "code", "write",
            "Learn project style from an accepted sample", mutates=True)
def _style(p, ctx):
    from .agent_intelligence import learn_style
    return learn_style(_s(ctx.get("state_root")), str(p.get("sample", "")))


@capability("code.postmortem", "agent_intelligence", "code", "write",
            "Store a failure postmortem", mutates=True)
def _postmortem(p, ctx):
    from .agent_intelligence import record_postmortem
    return record_postmortem(_s(ctx.get("state_root")),
                             str(p.get("task", "")), str(p.get("error", "")))


@capability("code.estimate", "agent_intelligence", "code", "read",
            "Estimate run cost/time with confidence")
def _estimate(p, ctx):
    from .agent_intelligence import estimate_run
    return estimate_run(str(p.get("prompt", "")))


@capability("code.browser.profiles", "browser_profiles", "code", "read",
            "List persistent per-agent browser profiles")
def _bp_list(p, ctx):
    from .browser_profiles import BrowserProfiles
    return {"profiles": BrowserProfiles(_s(ctx.get("state_root"))).list_profiles()}


@capability("code.browser.launch_cmd", "browser_launch", "code", "read",
            "Build a local browser launch command with isolated profile")
def _bp_cmd(p, ctx):
    from .browser_launch import find_browser, launch_command
    profile = Path(str(p.get("profile", "")))
    return {"binary": find_browser(),
            "args": launch_command(str(p.get("binary", "browser")), profile,
                                   url=p.get("url", "about:blank"),
                                   debug_port=p.get("debug_port"))}


# ---------------------------------------------------------------- duet
@capability("duet.inline.suggest", "inline_completion", "duet", "read",
            "Generate local inline completion suggestions")
def _inline(p, ctx):
    from .inline_completion import suggest
    return {"suggestions": suggest(
        str(p.get("prefix", "")), str(p.get("suffix", "")),
        language=p.get("language", "python"))}


@capability("duet.reviewer.comments", "inline_completion", "duet", "read",
            "Generate reviewer comments for a builder report")
def _reviewer(p, ctx):
    from .inline_completion import reviewer_comments
    return {"comments": reviewer_comments(str(p.get("report", "")),
                                          p.get("files", []))}


@capability("duet.best_of_n", "best_of_n", "duet", "read",
            "Select the best of N local candidates by score")
def _bon(p, ctx):
    from .best_of_n import best_of_n
    candidates = p.get("candidates", [])
    result = best_of_n(
        str(p.get("prompt", "")), n=max(1, len(candidates)),
        generate=lambda prompt, i: candidates[i],
        select=lambda value: (float(value.get("score", 0)), str(value.get("evidence", ""))))
    return {"index": result.index, "value": result.value}


@capability("duet.roles", "agent_roles", "duet", "read",
            "Get a role prompt or checkpoint descriptor")
def _roles(p, ctx):
    from .agent_roles import (map_reduce_chunks, overnight_checkpoint,
                              reflection_gate, role_prompt)
    kind = p.get("kind", "prompt")
    if kind == "map_reduce":
        return {"chunks": map_reduce_chunks(str(p.get("text", "")),
                                             int(p.get("workers", 3)))}
    if kind == "reflection":
        return reflection_gate(str(p.get("reflection", "")),
                               approved=bool(p.get("approved")))
    if kind == "checkpoint":
        cp = overnight_checkpoint(int(p.get("step", 1)), int(p.get("total", 5)),
                                  needs_approval=bool(p.get("needs_approval")))
        return cp.__dict__
    return {"prompt": role_prompt(str(p.get("role", "")))}


@capability("duet.arena", "arena", "duet", "read",
            "Compare two local outputs with an optional preference")
def _arena(p, ctx):
    from .arena import compare, to_dict
    outs = p.get("outputs", ["", ""])
    winner = p.get("winner")
    judge = (lambda q, a, b: int(winner)) if winner in (0, 1) else None
    return to_dict(compare(str(p.get("prompt", "")),
                           generators=[lambda _q, i=idx: outs[i]
                                       for idx in range(len(outs))],
                           judge=judge))


@capability("duet.embeddings.rerank", "embeddings", "duet", "read",
            "Rerank documents with local lexical embeddings")
def _rerank(p, ctx):
    from .embeddings import rerank
    return {"results": rerank(str(p.get("query", "")), p.get("documents", []),
                              limit=int(p.get("limit", 5)))}


@capability("duet.think_harder", "agent_intelligence", "duet", "read",
            "Map an effort level to a reasoning-effort label")
def _effort(p, ctx):
    from .agent_intelligence import think_harder_effort
    return {"effort": think_harder_effort(int(p.get("level", 2)))}


@capability("duet.uncertainty", "agent_intelligence", "duet", "read",
            "Decide an uncertainty policy for a confidence value")
def _uncertainty(p, ctx):
    from .agent_intelligence import uncertainty_policy
    return {"policy": uncertainty_policy(float(p.get("confidence", 0.5)))}


# ---------------------------------------------------------------- fleet
@capability("fleet.workflow.version", "workflow_history", "fleet", "write",
            "Save a workflow definition version", mutates=True)
def _wf_save(p, ctx):
    from .workflow_history import WorkflowHistory
    return {"version": WorkflowHistory(_s(ctx.get("state_root"))).save(
        str(p["name"]), p.get("definition", {}))}


@capability("fleet.workflow.history", "workflow_history", "fleet", "read",
            "List workflow versions")
def _wf_versions(p, ctx):
    from .workflow_history import WorkflowHistory
    return {"versions": WorkflowHistory(_s(ctx.get("state_root"))).versions(
        str(p["name"]))}


@capability("fleet.anomaly", "workflow_history", "fleet", "read",
            "Score event sequences for behavioral anomalies")
def _anomaly(p, ctx):
    from .workflow_history import anomaly_score
    return {"score": anomaly_score(p.get("events", []))}


@capability("fleet.eventbus.publish", "automation", "fleet", "write",
            "Publish an event on the local bus", mutates=True)
def _bus(p, ctx):
    from .automation import EventBus
    bus = EventBus()
    bus.publish(str(p.get("topic", "")), p.get("payload", {}))
    return {"history": bus.history}


@capability("fleet.notifications.route", "automation", "fleet", "read",
            "Route a notification with quiet hours")
def _notify(p, ctx):
    from .automation import NotificationRules
    rules = NotificationRules(int(p.get("quiet_from", 22)),
                              int(p.get("quiet_to", 8)))
    hour = int(p.get("hour", 12))
    return {"quiet": rules.is_quiet(hour),
            "channel": rules.route(str(p.get("channel", "email")),
                                   str(p.get("severity", "normal")))}


@capability("fleet.mentions", "mention_guard", "fleet", "read",
            "Check an agent mention for loop limits")
def _mentions(p, ctx):
    from .fleet.mention_guard import MentionGuard
    guard = MentionGuard(max_per_pair=int(p.get("max_per_pair", 2)),
                         max_per_round=int(p.get("max_per_round", 8)))
    for author, text in p.get("history", []):
        guard.check(author, text)
    return {"blocked": guard.check(str(p.get("author", "")), str(p.get("text", "")))}


@capability("fleet.supply.review", "supply_chain", "fleet", "read",
            "Review a skill's capabilities against a baseline")
def _supply(p, ctx):
    from .supply_chain import permission_diff
    return permission_diff(p.get("skill", {}), set(p.get("baseline", [])))


@capability("fleet.benchmark.leaderboard", "swe_bench", "fleet", "read",
            "Aggregate SWE benchmark results into a leaderboard")
def _leaderboard(p, ctx):
    from .swe_bench import BenchmarkResult, leaderboard
    results = [BenchmarkResult(**r) for r in p.get("results", [])]
    return leaderboard(results)


@capability("fleet.audit.export", "resilience", "fleet", "write",
            "Create a SQLite backup for retention", mutates=True)
def _db_backup(p, ctx):
    from .resilience import db_backup
    return {"path": str(db_backup(str(p["db"]), str(p["target"])))}


# ---------------------------------------------------------------- desktop/web
@capability("desktop.profiles.layout", "desktop_state", "desktop", "write",
            "Save a workspace layout", mutates=True)
def _layout(p, ctx):
    from .desktop_state import DesktopState
    return DesktopState(_s(ctx.get("state_root"))).save_layout(
        str(p["name"]), p.get("panels", []))


@capability("desktop.quickask", "desktop_state", "desktop", "read",
            "Get the Quick Ask overlay descriptor")
def _quickask(p, ctx):
    from .desktop_state import quick_ask_descriptor
    return quick_ask_descriptor()


@capability("web.docs.index", "site_tools", "web", "read",
            "Build a static docs search index")
def _docs_index(p, ctx):
    from .site_tools import build_docs_index
    return build_docs_index(str(p.get("root", ctx.get("cwd", "."))))


@capability("web.status", "site_tools", "web", "read",
            "Build a static status page descriptor")
def _status(p, ctx):
    from .site_tools import status_page
    return status_page(bool(p.get("feeds_ok", True)), bool(p.get("mirrors_ok", True)))


@capability("web.deeplink", "site_tools", "web", "read",
            "Parse a keel:// deep link")
def _deeplink(p, ctx):
    from .site_tools import parse_deep_link
    return parse_deep_link(str(p.get("url", ""))) or {"error": "invalid deep link"}


@capability("web.release.latest", "release_feed", "web", "read",
            "Get the latest release descriptor")
def _latest(p, ctx):
    from .release_feed import latest_json
    return latest_json(p.get("base_url", ""))


@capability("web.release.history", "release_feed", "web", "read",
            "Get release version history")
def _history(p, ctx):
    from .release_feed import version_history
    return version_history()


@capability("web.release.rss", "release_feed", "web", "read",
            "Generate the release RSS feed")
def _rss(p, ctx):
    from .release_feed import rss_feed
    return {"xml": rss_feed(p.get("site_url", "http://localhost/"))}


@capability("web.localize", "final_features", "web", "read",
            "Look up a localized UI string")
def _localize(p, ctx):
    from .final_features import localized
    return {"text": localized(str(p.get("key", "")), p.get("lang", "en"))}


@capability("web.roadmap", "last_features", "web", "read",
            "Get the public roadmap document path")
def _roadmap(p, ctx):
    from .last_features import integration_guides
    return {"guides": integration_guides()}


@capability("web.ops.guide", "last_features", "web", "read",
            "Get the headless deployment guide")
def _opsguide(p, ctx):
    from .last_features import headless_ops_doc
    return {"guide": headless_ops_doc()}


@capability("web.compliance", "commercial_seams", "web", "read",
            "Get dormant compliance-pack status (no licensing enforced)")
def _compliance(p, ctx):
    from .commercial_seams import compliance_pack_status
    return compliance_pack_status()


@capability("web.edition", "commercial_seams", "web", "read",
            "Get the edition/channel field (standard, inactive)")
def _edition(p, ctx):
    from .commercial_seams import edition_field
    return edition_field()


@capability("web.license.format", "commercial_seams", "web", "read",
            "Get the reserved license-token format (inactive)")
def _license(p, ctx):
    from .commercial_seams import license_token_format
    return license_token_format()


@capability("web.silent_flags", "commercial_seams", "web", "read",
            "Get silent-install flag descriptors")
def _silent(p, ctx):
    from .commercial_seams import silent_install_flags
    return {"flags": silent_install_flags(str(p.get("platform", "windows")))}


# ---------------------------------------------------------------- release/dist
@capability("release.airgap", "distribution", "release", "read",
            "Describe an air-gapped offline bundle")
def _airgap(p, ctx):
    from .distribution import airgap_bundle
    return airgap_bundle(p.get("artifacts", []), str(p.get("base", ".")))


@capability("release.repo.layout", "distribution", "release", "read",
            "Check a static APT/YUM repository layout")
def _repo(p, ctx):
    from .distribution import static_repo_layout
    return static_repo_layout(str(p.get("root", ".")), p.get("distro", "apt"))


@capability("release.portable", "distribution", "release", "read",
            "Get a portable build manifest")
def _portable(p, ctx):
    from .distribution import portable_manifest
    return portable_manifest(str(p.get("version", "")), str(p.get("platform", "")))


@capability("release.smoke", "installer_smoke", "release", "read",
            "Verify staged installer checksums against a manifest")
def _smoke(p, ctx):
    from .installer_smoke import check_manifest
    return {"checks": [c.__dict__ for c in check_manifest(
        str(p.get("release_dir", "")), str(p.get("version", "")))]}


@capability("release.health", "start_health", "release", "read",
            "Read repeated failed-start health state")
def _health(p, ctx):
    from .start_health import _load
    return _load(str(p.get("state_root", ctx.get("state_root", ".keel"))))


@capability("release.health.record", "start_health", "release", "write",
            "Record a start outcome (for auto-rollback)", mutates=True)
def _health_record(p, ctx):
    from .start_health import record_start
    return record_start(str(p.get("state_root", ctx.get("state_root", ".keel"))),
                        str(p.get("version", "")), ok=bool(p.get("ok", True)))


@capability("release.official.verify", "eval_tools", "release", "read",
            "Verify an official build checksum")
def _official(p, ctx):
    from .eval_tools import verify_official_build
    return {"valid": verify_official_build(str(p["path"]), str(p["sha256"]))}


@capability("release.trends", "eval_tools", "release", "read",
            "Read stored release trend entries")
def _trends(p, ctx):
    from .eval_tools import TrendStore
    path = TrendStore(_s(ctx.get("state_root"))).path
    if not path.is_file():
        return {"entries": []}
    return {"entries": [json.loads(line) for line in
                        path.read_text().splitlines() if line.strip()]}


@capability("release.delta", "external_adapters", "release", "read",
            "Plan a delta update with opt-in beta channel")
def _delta(p, ctx):
    from .external_adapters import delta_update_plan
    return delta_update_plan(str(p.get("current", "")), str(p.get("target", "")),
                             p.get("channel", "stable"))


@capability("release.pairing", "pairing", "release", "read",
            "List paired LAN/headless clients")
def _pairing(p, ctx):
    from .pairing import PairingStore
    return {"clients": PairingStore(_s(ctx.get("state_root"))).list_clients()}


@capability("release.pair", "pairing", "release", "write",
            "Pair a LAN/headless client (explicit opt-in)", mutates=True)
def _pair(p, ctx):
    from .pairing import PairingStore
    return PairingStore(_s(ctx.get("state_root"))).pair(
        str(p.get("label", "")), scope=p.get("scope", "lan"))


@capability("release.revoke", "pairing", "release", "write",
            "Revoke a paired client", mutates=True)
def _revoke(p, ctx):
    from .pairing import PairingStore
    return {"ok": PairingStore(_s(ctx.get("state_root"))).revoke(str(p["id"]))}


@capability("release.backups.create", "backups", "release", "write",
            "Create an encrypted local backup", mutates=True)
def _backup_create(p, ctx):
    from .backups import create_backup
    return create_backup(_resolve(str(p["source"]), ctx),
                         _resolve(str(p["target"]), ctx),
                         str(p["passphrase"]))


@capability("release.backups.restore", "backups", "release", "write",
            "Restore an encrypted local backup with verification", mutates=True)
def _backup_restore(p, ctx):
    from .backups import restore_backup
    return {"restored": restore_backup(_resolve(str(p["backup"]), ctx),
                                       _resolve(str(p["target"]), ctx),
                                       str(p["passphrase"]))}


@capability("release.webhook.history", "webhook_delivery", "release", "read",
            "Read the webhook delivery log")
def _wh_history(p, ctx):
    from .webhook_delivery import WebhookDelivery
    return {"entries": WebhookDelivery(_s(ctx.get("state_root"))).history()}


@capability("release.webhook.send", "webhook_delivery", "release", "execute",
            "Send a signed webhook with retry/backoff")
def _wh_send(p, ctx):
    from .webhook_delivery import WebhookDelivery
    return WebhookDelivery(_s(ctx.get("state_root"))).send(
        str(p["url"]), p.get("payload", {}), str(p.get("secret", "")),
        attempts=int(p.get("attempts", 3)),
        allow_http=bool(p.get("allow_http")))


# ---------------------------------------------------------------- external ready
@capability("external.ci.run", "integrations", "external", "execute",
            "Run a prompt through a CI adapter transport")
def _ci_run(p, ctx):
    from .integrations import CIAdapter, MockTransport
    if p.get("mock", True):
        transport = MockTransport(ok=bool(p.get("ok", True)),
                                  output=str(p.get("output", "keel-ok")))
    else:
        transport = None
    result = CIAdapter(transport=transport).run(str(p.get("prompt", "")))
    return {"ok": result.ok, "detail": result.detail}


@capability("external.remote.cmd", "integrations", "external", "read",
            "Build a remote-target command (SSH/WSL/devcontainer)")
def _remote(p, ctx):
    from .integrations import RemoteTarget
    return {"args": RemoteTarget(str(p.get("kind", "ssh")),
                                 str(p.get("location", ""))).command(
        str(p.get("command", "")))}


@capability("external.wasm.cmd", "external_adapters", "external", "read",
            "Build a local WASM runtime command")
def _wasm(p, ctx):
    from .external_adapters import wasm_command
    return {"args": wasm_command(str(p.get("entry", "")), p.get("engine", "python"))}


@capability("external.container.cmd", "external_adapters", "external", "read",
            "Build a resource-limited container command")
def _container(p, ctx):
    from .external_adapters import container_command
    return {"args": container_command(
        str(p.get("image", "")), str(p.get("command", "")),
        cpus=float(p.get("cpus", 1.0)),
        memory_mb=int(p.get("memory_mb", 512)),
        network=bool(p.get("network", False)))}


@capability("external.image.cmd", "integrations", "external", "read",
            "Build a local image-generation command")
def _imagegen(p, ctx):
    from .integrations import image_gen_command
    return {"args": image_gen_command(str(p.get("prompt", "")),
                                      engine=p.get("engine", "comfyui"),
                                      output=str(p.get("output", "out.png")))}


@capability("external.judge", "external_adapters", "external", "read",
            "Score a trajectory with the local judge")
def _judge(p, ctx):
    from .external_adapters import judge_score
    return judge_score(p.get("trajectory", []))


@capability("external.companion.pair", "integrations", "external", "read",
            "Build an explicit LAN companion pairing payload")
def _companion(p, ctx):
    from .integrations import companion_pair_payload
    return companion_pair_payload(str(p.get("device", "")),
                                  str(p.get("secret", "")))


# ---------------------------------------------------------------- remaining modules
@capability("core.idle.status", "admin_ops", "core", "read",
            "Create an idle suspend/wake tracker state")
def _idle(p, ctx):
    from .admin_ops import IdleSuspend
    m = IdleSuspend(timeout_s=float(p.get("timeout_s", 300)))
    return {"timeout_s": m.timeout_s, "suspended": m.suspended}


@capability("cowork.channel.deliver", "channel_ops", "cowork", "execute",
            "Try a channel delivery fallback chain")
def _channel_deliver(p, ctx):
    from .channel_ops import deliver_with_fallback
    chain = p.get("chain", [])
    # No real send function can be serialized; report the chain and require
    # an explicit in-process caller for actual delivery.
    return {"chain": chain,
            "note": "delivery requires an in-process send callable"}


@capability("cowork.channel.troubleshoot", "channel_ops", "cowork", "read",
            "Get a per-channel troubleshooting checklist")
def _channel_trouble(p, ctx):
    from .channel_ops import checklist
    return {"steps": checklist(str(p.get("channel", "")))}


@capability("core.cli.env", "cli_extras", "core", "read",
            "List KEEL_* env overrides (masked) with agent spec helper")
def _cli_env(p, ctx):
    import os

    overrides = {k: "set" if v else "empty"
                 for k, v in sorted(os.environ.items()) if k.startswith("KEEL_")}
    return {"env": overrides}


@capability("core.composer.shell", "composer_tools", "core", "read",
            "Parse an inline shell command from the composer")
def _composer_shell(p, ctx):
    from .composer_tools import parse_inline_shell
    return parse_inline_shell(str(p.get("text", "")))


@capability("core.eula.status", "eula", "core", "read",
            "Check whether the current EULA version is accepted")
def _eula_status(p, ctx):
    from .eula import needs_acceptance, accepted_version
    return {"needs_acceptance": needs_acceptance(str(p.get("version", ""))),
            "accepted": accepted_version()}


@capability("core.eula.accept", "eula", "core", "write",
            "Record local EULA acceptance", mutates=True)
def _eula_accept(p, ctx):
    from .eula import accept
    return {"version": accept(str(p.get("version", "")))}


@capability("cowork.research.plan", "knowledge_work", "cowork", "read",
            "Build a deep-research plan with citation slots")
def _research(p, ctx):
    from .final_features import deep_research
    return deep_research(str(p.get("topic", "")), p.get("sources", []))


@capability("cowork.memory.types", "memory_types", "cowork", "read",
            "Recall typed memories by kind")
def _mem_types(p, ctx):
    from .memory import MemoryStore
    from .memory_types import TypedMemory
    typed = TypedMemory(MemoryStore(_s(ctx.get("state_root"))))
    return {"items": typed.recall_kind(str(p.get("kind", "semantic")),
                                       str(p.get("query", "")))}


@capability("cowork.memory.consolidate", "memory_types", "cowork", "write",
            "Consolidate duplicate semantic memories", mutates=True)
def _mem_consolidate(p, ctx):
    from .memory import MemoryStore
    from .memory_types import TypedMemory
    return TypedMemory(MemoryStore(_s(ctx.get("state_root")))).dreaming()


@capability("core.specialists", "misc_features", "core", "read",
            "List bundled specialist agent prompts")
def _specialists(p, ctx):
    from .misc_features import specialist_agents
    return specialist_agents()


@capability("code.model.load", "model_manager", "code", "write",
            "Load a local model into a bounded manager", mutates=True)
def _model_load(p, ctx):
    from .model_manager import ModelManager
    m = ModelManager(budget_bytes=int(p.get("budget_bytes", 1024 * 1024 * 1024)))
    ok = m.load(str(p.get("name", "")), int(p.get("bytes_est", 0)),
                str(p.get("command", "")))
    return {"loaded": ok, "status": m.status()}


@capability("code.model.runtime", "model_runtime", "code", "read",
            "Get local model runtime status with budget and LRU eviction")
def _model_rt(p, ctx):
    from .model_runtime import ModelRuntime
    m = ModelRuntime(budget_bytes=int(p.get("budget_bytes", 1024 * 1024 * 1024)))
    for item in p.get("models", []):
        m.load(str(item["name"]), int(item.get("bytes_est", 0)))
    return m.status()


@capability("core.prefix.cache", "prefix_cache", "core", "read",
            "Find the longest shared prefix in a cache")
def _prefix(p, ctx):
    from .prefix_cache import PrefixCache, speculative_enabled
    cache = PrefixCache()
    for item in p.get("prompts", []):
        cache.store(str(item))
    hit = cache.longest_prefix(str(p.get("prompt", "")))
    return {"length": hit.length, "text": hit.text,
            "speculative": speculative_enabled()}


@capability("core.secret.providers", "provider_sources", "core", "read",
            "List supported secret provider choices")
def _secret_providers(p, ctx):
    from .provider_sources import SECRET_PROVIDERS
    return SECRET_PROVIDERS


@capability("cowork.rag.autostart", "rag_watcher", "cowork", "write",
            "Start auto-reindexing a RAG knowledge base", mutates=True)
def _rag_auto(p, ctx):
    from .rag_watcher import RagAutoIndex
    idx = RagAutoIndex(str(p.get("state_root", ctx.get("state_root", ".keel"))),
                       str(p["folder"]), str(p.get("name", "default")))
    idx.reindex()
    return {"status": idx.base.search(str(p.get("sample", "")))[:3]}


@capability("core.resources.meters", "resource_caps", "core", "read",
            "Get per-feature resource cap meters")
def _res_meters(p, ctx):
    from .resource_caps import ResourceMeter
    m = ResourceMeter(low_power=bool(p.get("low_power")))
    return {"meters": [meter.__dict__ for meter in m.meters()]}


@capability("core.resources.limits", "resource_limits", "core", "read",
            "Get browser/workspace resource budget status")
def _res_limits(p, ctx):
    from .resource_limits import ResourceManager
    m = ResourceManager()
    return m.status()


@capability("code.sandbox.descriptor", "sandbox", "code", "read",
            "Build WASM/container sandbox descriptors")
def _sandbox_desc(p, ctx):
    from .sandbox import container_sandbox, wasm_sandbox
    return {"wasm": wasm_sandbox(str(p.get("code", ""))),
            "container": container_sandbox(str(p.get("image", "python:3.11")))}


@capability("code.virtual.window", "virtual_list", "code", "read",
            "Compute a virtualized visible list window")
def _virtual(p, ctx):
    from .virtual_list import Backpressure, visible_window
    w = visible_window(int(p.get("total", 100)), int(p.get("scroll_top", 0)),
                       int(p.get("viewport", 400)), int(p.get("item_height", 20)))
    return {"start": w.start, "end": w.end, "offset": w.offset}


@capability("cowork.workbench.notebook", "workbench", "cowork", "read",
            "Split a markdown notebook into cells")
def _notebook(p, ctx):
    from .workbench import notebook_cells
    return {"cells": notebook_cells(str(p.get("source", "")))}


@capability("cowork.workbench.spec", "workbench", "cowork", "read",
            "Create a spec-driven workbench plan")
def _wb_spec(p, ctx):
    from .workbench import spec_plan
    return spec_plan(str(p.get("goal", "")))

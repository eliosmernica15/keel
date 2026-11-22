"""keel — command-line entrypoint."""

from __future__ import annotations

import json
import sys

from ..providers import registry as provider_registry
from ..providers.base import ProviderError
from ..runner import CliValidationError, diagnostic, parse_argv, run


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in ("--version", "-V", "version"):
        from .. import __version__
        sys.stdout.write(f"keel {__version__}\n")
        return 0

    if argv and argv[0] == "init":
        return _init_cmd(argv[1:])
    if argv and argv[0] == "tools":
        return _tools_cmd(argv[1:])
    if argv and argv[0] == "attach":
        return _attach_cmd(argv[1:])
    if argv and argv[0] == "costs":
        return _costs_cmd(argv[1:])
    if argv and argv[0] == "model":
        return _model_cmd(argv[1:])
    if argv and argv[0] == "gateway":
        return _gateway_cmd(argv[1:])
    if argv and argv[0] == "webhook":
        return _webhook_cmd(argv[1:])
    if argv and argv[0] in ("doctor", "diagnostics"):
        if "--bundle" in argv:
            return _doctor_bundle_cmd(argv)
    if argv and argv[0] == "session":
        return _session_cmd(argv[1:])
    if argv and argv[0] == "capability":
        return _capability_cmd(argv[1:])
    if argv and argv[0] == "tui":
        from ..tui import Tui

        if "--help" in argv:
            sys.stderr.write("usage: keel tui  (interactive terminal UI)\n")
            return 0
        Tui().run()
        return 0
    if argv and argv[0] == "provider":
        return _provider_cmd(argv[1:])
    if argv and argv[0] == "notebook":
        return _notebook_cmd(argv[1:])
    if argv and argv[0] == "spec":
        return _spec_cmd(argv[1:])
    if argv and argv[0] == "docpack":
        return _docpack_cmd(argv[1:])
    if argv and argv[0] == "vault":
        return _vault_cmd(argv[1:])
    if argv and argv[0] == "repoindex":
        return _repoindex_cmd(argv[1:])
    if argv and argv[0] == "openapi":
        return _openapi_cmd(argv[1:])
    if argv and argv[0] == "skills":
        return _skills_cmd(argv[1:])
    if argv and argv[0] == "settings":
        return _settings_cmd(argv[1:])
    if argv and argv[0] == "mcp":
        return _mcp_cmd(argv[1:])
    if argv and argv[0] == "web":
        # A1.4: local web UI alias — same loopback server as `keel serve`.
        argv = ["serve", *argv[1:]]
    if argv and argv[0] == "serve":
        from ..webapp import serve
        port = 8739
        tail = argv[1:]
        if "--help" in tail or "-h" in tail:
            sys.stderr.write("usage: keel serve [--port N]\n"
                             "  serves the local webapp on 127.0.0.1 (default port 8739)\n"
                             "  prints the tokenized URL to open; Ctrl+C to stop\n")
            return 0
        if "--port" in tail:
            i = tail.index("--port")
            if i + 1 >= len(tail):
                sys.stderr.write("--port requires a value\n")
                return 1
            try:
                port = int(tail[i + 1])
            except ValueError:
                sys.stderr.write("--port must be an integer\n")
                return 1
        from ..fleet import scheduler
        scheduler.start_daemon()
        serve(port)
        return 0
    if argv and argv[0] == "fleet":
        from ..webapp import serve
        port = 8739
        tail = argv[1:]
        if "--help" in tail or "-h" in tail:
            sys.stderr.write("usage: keel fleet [--port N]\n"
                             "  serves Keel Fleet on 127.0.0.1 (default 8739)\n"
                             "  prints the tokenized URL for /fleet; Ctrl+C to stop\n")
            return 0
        if "--port" in tail:
            i = tail.index("--port")
            if i + 1 >= len(tail):
                sys.stderr.write("--port requires a value\n")
                return 1
            try:
                port = int(tail[i + 1])
            except ValueError:
                sys.stderr.write("--port must be an integer\n")
                return 1
        from ..fleet import scheduler
        scheduler.start_daemon()
        serve(port)
        return 0

    try:
        plan = parse_argv(argv)
    except CliValidationError as exc:
        diagnostic("cli_validation", {"errors": str(exc)})
        return 1
    return run(plan)


def _doctor_bundle_cmd(argv: list[str]) -> int:
    from ..diagnostics import write_bundle

    path = "keel-diagnostics.zip"
    if "--file" in argv and argv.index("--file") + 1 < len(argv):
        path = argv[argv.index("--file") + 1]
    try:
        target = write_bundle(path)
    except OSError as exc:
        sys.stderr.write(f"cannot write diagnostics bundle: {exc}\n")
        return 1
    sys.stdout.write(f"wrote redacted diagnostics bundle {target}\n")
    return 0


def _session_cmd(argv: list[str]) -> int:
    from ..fleet import routes as fleet_routes
    from ..session_export import (SessionExportError, export_bundle,
                                  import_bundle, read_bundle, statistics,
                                  write_bundle)

    usage = ("usage: keel session export <id> --file PATH\n"
             "       keel session import <file>\n"
             "       keel session stats <id>\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    action = argv[0]
    store = fleet_routes.store()
    try:
        if action == "export" and len(argv) >= 2:
            target = ""
            if "--file" in argv and argv.index("--file") + 1 < len(argv):
                target = argv[argv.index("--file") + 1]
            if not target:
                sys.stderr.write("--file is required\n")
                return 1
            path = write_bundle(export_bundle(store, argv[1]), target)
            sys.stdout.write(f"exported {path}\n")
            return 0
        if action == "import" and len(argv) >= 2:
            bot = import_bundle(store, read_bundle(argv[1]))
            sys.stdout.write(json.dumps(bot, indent=2) + "\n")
            return 0
        if action == "stats" and len(argv) >= 2:
            sys.stdout.write(json.dumps(
                statistics(store, argv[1]), indent=2) + "\n")
            return 0
    except SessionExportError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stderr.write(usage)
    return 1


def _capability_cmd(argv: list[str]) -> int:
    from .. import capability_registry  # noqa: F401
    from ..capabilities import (CapabilityError, audit_path, get, invoke,
                                list_capabilities, record_audit)
    import os
    from pathlib import Path

    usage = ("usage: keel capability list [--surface S]\n"
             "       keel capability describe <id>\n"
             "       keel capability invoke <id> [--params JSON] [--confirm]\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0

    cmd = argv[0]
    if cmd == "list":
        surface = None
        if "--surface" in argv and argv.index("--surface") + 1 < len(argv):
            surface = argv[argv.index("--surface") + 1]
        for cap in list_capabilities(surface=surface):
            sys.stdout.write(
                f"{cap['id']:<38} [{cap['surface']}/{cap['permission']}] "
                f"{cap['description'][:60]}\n")
        return 0
    if cmd == "describe" and len(argv) > 1:
        cap = get(argv[1])
        if cap is None:
            sys.stderr.write(f"unknown capability: {argv[1]}\n")
            return 1
        sys.stdout.write(json.dumps({
            "id": cap.id, "module": cap.module, "surface": cap.surface,
            "permission": cap.permission, "description": cap.description,
            "input_schema": cap.input_schema, "mutates": cap.mutates,
        }, indent=2) + "\n")
        return 0
    if cmd == "invoke" and len(argv) > 1:
        cap_id = argv[1]
        params = {}
        if "--params" in argv and argv.index("--params") + 1 < len(argv):
            try:
                params = json.loads(argv[argv.index("--params") + 1])
            except json.JSONDecodeError:
                sys.stderr.write("--params must be valid JSON\n")
                return 1
        cap = get(cap_id)
        if cap is None:
            sys.stderr.write(f"unknown capability: {cap_id}\n")
            return 1
        if (cap.permission in ("write", "execute") or cap.mutates) \
                and "--confirm" not in argv:
            sys.stderr.write(
                f"{cap_id} requires --confirm ({cap.permission})\n")
            return 1
        state_root = os.environ.get("KEEL_STATE_DIR",
                                    str(Path.home() / ".keel"))
        try:
            result = invoke(cap_id, params,
                            context={"state_root": state_root,
                                     "cwd": os.getcwd()})
            record_audit(state_root, {"capability": cap_id, "ok": True,
                                      "surface": "cli"})
        except CapabilityError as exc:
            record_audit(state_root, {"capability": cap_id, "ok": False,
                                      "code": exc.code, "surface": "cli"})
            sys.stderr.write(f"{exc.code}: {exc}\n")
            return 1
        sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
        return 0
    sys.stderr.write(usage)
    return 1


def _webhook_cmd(argv: list[str]) -> int:
    import os

    from ..webhooks import WebhookError, deliver

    usage = ("usage: keel webhook send <url> --payload JSON "
             "[--allow-http]\n"
             "  secret is read from KEEL_WEBHOOK_SECRET\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    if argv[0] != "send" or len(argv) < 2:
        sys.stderr.write(usage)
        return 1
    secret = os.environ.get("KEEL_WEBHOOK_SECRET", "")
    if not secret:
        sys.stderr.write("KEEL_WEBHOOK_SECRET is required\n")
        return 1
    payload_text = ""
    allow_http = False
    index = 2
    while index < len(argv):
        item = argv[index]
        if item == "--payload" and index + 1 < len(argv):
            payload_text = argv[index + 1]
            index += 2
            continue
        if item == "--allow-http":
            allow_http = True
        index += 1
    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        sys.stderr.write("--payload must be valid JSON\n")
        return 1
    from .. import settings as settings_mod
    from ..message_state import MessageStates

    state_root = os.environ.get(
        "KEEL_STATE_DIR", str(settings_mod.default_state_root()))
    states = MessageStates(state_root)
    record = states.queue(channel="webhook", destination=argv[1],
                          size=len(payload_text))
    try:
        result = deliver(argv[1], payload, secret, allow_http=allow_http)
        states.advance(record["id"], "sent")
    except WebhookError as exc:
        states.advance(record["id"], "failed")
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


def _gateway_cmd(argv: list[str]) -> int:
    import os

    from ..attach import AttachError, request

    usage = ("usage: keel gateway status [--port N] [--token TOK]\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    if argv[0] != "status":
        sys.stderr.write(usage)
        return 1
    token = os.environ.get("KEEL_TOKEN", "")
    port = 8739
    index = 1
    while index < len(argv):
        item = argv[index]
        if item in ("--port", "--token") and index + 1 < len(argv):
            if item == "--port":
                try:
                    port = int(argv[index + 1])
                except ValueError:
                    sys.stderr.write("--port must be an integer\n")
                    return 1
            else:
                token = argv[index + 1]
            index += 2
            continue
        index += 1
    if not token:
        sys.stderr.write("gateway status needs --token or KEEL_TOKEN\n")
        return 1
    try:
        sys.stdout.write(json.dumps(
            request(port, token, "/api/gateway"), indent=2) + "\n")
        return 0
    except AttachError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1


def _model_cmd(argv: list[str]) -> int:
    from ..model_downloads import DownloadError, download

    usage = ("usage: keel model download <url> --dest PATH "
             "[--sha256 HASH] [--allow-http]\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    if argv[0] != "download" or len(argv) < 2:
        sys.stderr.write(usage)
        return 1
    url = argv[1]
    dest = ""
    checksum = ""
    allow_http = False
    index = 2
    while index < len(argv):
        item = argv[index]
        if item in ("--dest", "--sha256") and index + 1 < len(argv):
            if item == "--dest":
                dest = argv[index + 1]
            else:
                checksum = argv[index + 1]
            index += 2
            continue
        if item == "--allow-http":
            allow_http = True
        index += 1
    if not dest:
        sys.stderr.write("--dest is required\n")
        return 1
    try:
        path = download(url, dest, sha256=checksum or None,
                        allow_http=allow_http)
    except DownloadError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(f"downloaded {path}\n")
    return 0


def _costs_cmd(argv: list[str]) -> int:
    import os

    from .. import settings as settings_mod
    from ..cost_caps import CostCaps

    usage = ("usage: keel costs status\n"
             "       keel costs cap <provider> [--daily USD] [--monthly USD]\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    state = os.environ.get("KEEL_STATE_DIR",
                           str(settings_mod.default_state_root()))
    manager = CostCaps(state)
    command = argv[0]
    if command == "status":
        doc = {}
        for provider in manager.caps():
            doc[provider] = {
                "caps": manager.caps()[provider],
                "daily_usd": manager.totals(provider, "daily"),
                "monthly_usd": manager.totals(provider, "monthly"),
            }
        sys.stdout.write(json.dumps(doc, indent=2) + "\n")
        return 0
    if command == "cap" and len(argv) >= 2:
        daily = monthly = None
        rest = argv[2:]
        for index, item in enumerate(rest):
            if item in ("--daily", "--monthly") and index + 1 < len(rest):
                try:
                    value = float(rest[index + 1])
                except ValueError:
                    sys.stderr.write(f"{item} must be a number\n")
                    return 1
                if item == "--daily":
                    daily = value
                else:
                    monthly = value
        manager.set_cap(argv[1], daily=daily, monthly=monthly)
        sys.stdout.write(json.dumps(manager.caps()[argv[1]], indent=2) + "\n")
        return 0
    sys.stderr.write(usage)
    return 1


def _attach_cmd(argv: list[str]) -> int:
    import os

    from .. import attach

    usage = ("usage: keel attach [--port N] [--token TOK]\n"
             "       keel attach <session-id> [--port N] [--token TOK]\n"
             "       keel attach <session-id> -p \"message\" [--port N]\n")
    if argv and argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    token = os.environ.get("KEEL_TOKEN", "")
    port = 8739
    prompt = ""
    positional: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in ("--port", "--token", "-p", "--print"):
            if index + 1 >= len(argv):
                sys.stderr.write(f"{item} requires a value\n")
                return 1
            value = argv[index + 1]
            if item == "--port":
                try:
                    port = int(value)
                except ValueError:
                    sys.stderr.write("--port must be an integer\n")
                    return 1
            elif item == "--token":
                token = value
            else:
                prompt = value
            index += 2
            continue
        positional.append(item)
        index += 1
    if not token:
        sys.stderr.write("attach needs --token or KEEL_TOKEN (see `keel serve`)\n")
        return 1
    try:
        if not positional:
            sessions = attach.list_sessions(port, token)
            sys.stdout.write(json.dumps(sessions, indent=2) + "\n")
            return 0
        sid = positional[0]
        if prompt:
            attach.send_message(sid, prompt, port, token)
        detail = attach.session_detail(sid, port, token)
        sys.stdout.write(json.dumps(detail, indent=2) + "\n")
        return 0
    except attach.AttachError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1


def _tools_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from .. import custom_tools

    usage = ("usage: keel tools list\n"
             "       keel tools approve <name>\n"
             "       keel tools revoke <name>\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    command, cwd = argv[0], Path(os.getcwd())
    specs = custom_tools.discover(cwd)
    by_name = {spec["name"]: spec for spec in specs}
    if command == "list":
        sys.stdout.write(json.dumps(specs, indent=2) + "\n")
        return 0
    if command in ("approve", "revoke") and len(argv) > 1:
        name = argv[1]
        if name not in by_name and command == "revoke":
            sys.stderr.write(f"unknown custom tool: {name}\n")
            return 1
        if command == "approve":
            if name not in by_name:
                sys.stderr.write(f"unknown custom tool: {name}\n")
                return 1
            custom_tools.approve(by_name[name]["path"])
            sys.stdout.write(f"approved {name}\n")
        else:
            sys.stdout.write(
                f"{'revoked' if custom_tools.revoke(name) else 'unknown'} {name}\n")
        return 0
    sys.stderr.write(usage)
    return 1


def _init_cmd(argv: list[str]) -> int:
    import os

    from ..init_project import write_agents_md

    if argv and argv[0] in ("-h", "--help", "help"):
        sys.stderr.write("usage: keel init [--force]\n"
                         "  scan the current repo and generate AGENTS.md\n")
        return 0
    force = "--force" in argv
    try:
        target = write_agents_md(os.getcwd(), force=force)
    except FileExistsError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(f"wrote {target}\n")
    return 0


def _settings_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from .. import settings as settings_mod

    usage = ("usage: keel settings show\n"
             "       keel settings schema\n"
             "       keel settings validate <directory>\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    cmd = argv[0]
    cwd = Path(os.getcwd())
    if cmd == "show":
        resolved = settings_mod.resolve(state_root=settings_mod.default_state_root(),
                                        cwd=cwd)
        out = {"value": resolved.value,
               "provenance": resolved.provenance,
               "diagnostics": [d.__dict__ for d in resolved.diagnostics]}
        sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
        return 0
    if cmd == "schema":
        from ..settings import _REGISTRY
        props = {}
        for entry in _REGISTRY:
            t = {"string": "string", "number": "number", "boolean": "boolean",
                 "string[]": "array", "object": "object"}[entry.type]
            item = {"type": "string"} if entry.type == "string[]" else {}
            props[entry.key] = {"type": t, **({"items": item} if item else {})}
            if entry.default is not None:
                props[entry.key]["default"] = entry.default
        sys.stdout.write(json.dumps(
            {"$schema": "https://json-schema.org/draft/2020-12/schema",
             "title": "keel settings", "type": "object",
             "properties": props}, indent=2) + "\n")
        return 0
    if cmd == "validate":
        if len(argv) < 2:
            sys.stderr.write(usage)
            return 1
        root = Path(argv[1])
        envelope = []
        for f in sorted(root.rglob("*.json")) if root.is_dir() else [Path(argv[1])]:
            diagnostics = []
            data = settings_mod._load_json_file(f, "validate", diagnostics)
            envelope.append({"file": str(f),
                             "ok": data is not None and not diagnostics,
                             "diagnostics": [d.__dict__ for d in diagnostics]})
        sys.stdout.write(json.dumps({"files": envelope}, indent=2) + "\n")
        return 0 if all(e["ok"] for e in envelope) else 1
    sys.stderr.write(usage)
    return 1


def _mcp_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from .. import settings as settings_mod
    from ..mcp import (approvals as mcp_approvals, approve, is_approved,
                       parse_servers, revoke)

    usage = ("usage: keel mcp list\n"
             "       keel mcp approve <name>\n"
             "       keel mcp revoke <name>\n")
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(usage)
        return 0
    cmd = argv[0]
    cwd = Path(os.getcwd())
    resolved = settings_mod.resolve(state_root=settings_mod.default_state_root(),
                                    cwd=cwd)
    servers = parse_servers(resolved.value.get("mcpServers", {}))

    if cmd == "list":
        rows = [{"name": s.name, "scope": s.scope,
                 "command": s.command,
                 "approved": is_approved(s) if s.scope == "project" else True,
                 "requires_approval": s.scope == "project"}
                for s in servers]
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
        return 0

    if len(argv) < 2:
        sys.stderr.write(usage)
        return 1
    name = argv[1]
    match = next((s for s in servers if s.name == name), None)
    if cmd == "approve":
        if match is None:
            diagnostic("mcp", {"error": f"no server named {name!r} in settings",
                               "known": [s.name for s in servers]})
            return 1
        approve(match)
        sys.stdout.write(f"approved {name} ({match.scope} scope); "
                         "the exact command shape was recorded.\n")
        return 0
    if cmd == "revoke":
        ok = revoke(name)
        sys.stdout.write(f"{'revoked' if ok else 'was not approved'}: {name}\n")
        return 0 if ok else 1
    sys.stderr.write(usage)
    return 1


_SKILLS_USAGE = (
    "usage: keel skills list [--json]\n"
    "       keel skills show <name>\n"
    "       keel skills audit <name>\n"
    "       keel skills invoke <name> [--args TEXT]\n")


def _skills_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from .. import skills as skills_mod

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(_SKILLS_USAGE)
        return 0
    cmd = argv[0]
    project_root = Path(os.getcwd())
    if cmd == "list":
        found = skills_mod.discover(project_root)
        rows = [{"name": s.name, "scope": s.scope,
                 "description": s.description, "sha256": s.sha256[:16],
                 "untrusted": not s.trusted,
                 "injection_suspects": len(s.injection_suspects)}
                for s in found]
        if "--json" in argv:
            sys.stdout.write(json.dumps(rows, indent=2) + "\n")
            return 0
        for row in rows:
            flag = " [untrusted]" if row["untrusted"] else ""
            sys.stdout.write(f"{row['name']:<32} {row['scope']:<9} {row['sha256']}"
                             f"{flag}  {row['description']}\n")
        return 0
    if len(argv) < 2:
        sys.stderr.write(_SKILLS_USAGE)
        return 1
    name = argv[1]
    try:
        skill = skills_mod.show(name, project_root)
    except skills_mod.SkillError as exc:
        diagnostic("skills", {"action": cmd, "error": str(exc)})
        return 1
    if cmd == "show":
        sys.stdout.write(skill.body)
        if not skill.body.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    if cmd == "audit":
        report = {"name": skill.name, "scope": skill.scope, "path": str(skill.path),
                  "sha256": skill.sha256, "trusted": skill.trusted,
                  "injection_suspects": list(skill.injection_suspects),
                  "frontmatter": skill.frontmatter}
        sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
        return 0
    if cmd == "invoke":
        arguments = ""
        if "--args" in argv:
            i = argv.index("--args")
            arguments = argv[i + 1] if i + 1 < len(argv) else ""
        sys.stdout.write(skills_mod.render_prompt(skill, arguments))
        return 0
    sys.stderr.write(_SKILLS_USAGE)
    return 1


def _openapi_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from ..openapi_tools import (ToolRegistry, approve_tool, build_request,
                                 generate_tools)

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel openapi generate <name> <spec.json>\n"
            "       keel openapi approve <name> <tool>\n"
            "       keel openapi request <name> <tool> <args.json>\n"
            "       keel openapi list\n")
        return 0
    cmd = argv[0]
    store = ToolRegistry(str(os.environ.get("KEEL_STATE_DIR", ".keel")))
    try:
        if cmd == "generate":
            spec = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
            tools = generate_tools(spec)
            store.save(argv[1], tools)
            sys.stdout.write(json.dumps({"count": len(tools),
                                         "dormant": True}) + "\n")
            return 0
        if cmd == "approve":
            tools = store.load(argv[1])
            tool = next((t for t in tools if t["name"] == argv[2]), None)
            if tool is None:
                raise KeyError(argv[2])
            approve_tool(tool, approver=os.environ.get(
                "KEEL_TOOL_APPROVER", "owner"))
            store.save(argv[1], tools)
            sys.stdout.write(json.dumps({"approved": True}) + "\n")
            return 0
        if cmd == "request":
            tools = store.load(argv[1])
            tool = next((t for t in tools if t["name"] == argv[2]), None)
            if tool is None:
                raise KeyError(argv[2])
            args = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
            sys.stdout.write(json.dumps(build_request(tool, args),
                                        indent=2) + "\n")
            return 0
        if cmd == "list":
            sys.stdout.write(json.dumps(store.list()) + "\n")
            return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        diagnostic("openapi_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"openapi: {exc}\n")
        return 1
    sys.stderr.write(f"unknown openapi command: {cmd}\n")
    return 1


def _repoindex_cmd(argv: list[str]) -> int:
    import os

    from ..repo_index import IndexStore, build_index, search_index, update_index

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel repoindex build <name> <dir> [--ext .py,.md]\n"
            "       keel repoindex update <name> <dir>\n"
            "       keel repoindex search <name> <query> [--content]\n"
            "       keel repoindex list\n")
        return 0
    cmd = argv[0]
    store = IndexStore(str(os.environ.get("KEEL_STATE_DIR", ".keel")))
    try:
        if cmd == "build":
            exts = None
            if "--ext" in argv:
                exts = argv[argv.index("--ext") + 1].split(",")
            index = build_index(argv[2], extensions=exts)
            store.save(argv[1], index)
            sys.stdout.write(json.dumps({"count": index["count"]}) + "\n")
            return 0
        if cmd == "update":
            result = update_index(store.load(argv[1]), argv[2])
            store.save(argv[1], result)
            sys.stdout.write(json.dumps({k: result[k] for k in
                                         ("added", "modified", "removed",
                                          "rehashed")}) + "\n")
            return 0
        if cmd == "search":
            query_parts = [a for a in argv[2:] if a != "--content"]
            result = search_index(store.load(argv[1]), " ".join(query_parts),
                                  content="--content" in argv)
            sys.stdout.write(json.dumps(result, indent=2) + "\n")
            return 0
        if cmd == "list":
            sys.stdout.write(json.dumps(store.list()) + "\n")
            return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        diagnostic("repoindex_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"repoindex: {exc}\n")
        return 1
    sys.stderr.write(f"unknown repoindex command: {cmd}\n")
    return 1


def _vault_cmd(argv: list[str]) -> int:
    from ..notes_vault import Vault

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel vault backlinks <dir>   keel vault graph <dir>\n"
            "       keel vault tags <dir>         keel vault daily <dir> [date]\n"
            "       keel vault orphans <dir>\n")
        return 0
    cmd = argv[0]
    try:
        if len(argv) < 2:
            return 1
        vault = Vault(argv[1])
        if cmd == "backlinks":
            out = vault.backlinks()
        elif cmd == "graph":
            out = vault.graph()
        elif cmd == "tags":
            out = vault.tags()
        elif cmd == "daily":
            out = vault.daily(argv[2] if len(argv) > 2 else None)
        elif cmd == "orphans":
            out = {"orphans": vault.orphans()}
        else:
            sys.stderr.write(f"unknown vault command: {cmd}\n")
            return 1
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
        return 0
    except (OSError, ValueError, IndexError) as exc:
        diagnostic("vault_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"vault: {exc}\n")
        return 1


def _docpack_cmd(argv: list[str]) -> int:
    import os

    from ..docpacks import DocPackStore, build_pack, search

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel docpack build <name> <dir>\n"
            "       keel docpack search <name> <query> [--limit N]\n"
            "       keel docpack list\n")
        return 0
    cmd = argv[0]
    store = DocPackStore(str(os.environ.get("KEEL_STATE_DIR", ".keel")))
    try:
        if cmd == "build":
            pack = build_pack(argv[2], argv[1])
            store.save(pack)
            sys.stdout.write(json.dumps({"name": pack["name"],
                                         "doc_count": pack["doc_count"]}) + "\n")
            return 0
        if cmd == "search":
            limit = 5
            query_parts = list(argv[2:])
            if "--limit" in query_parts:
                idx = query_parts.index("--limit")
                limit = int(query_parts[idx + 1])
                del query_parts[idx:idx + 2]
            result = search(store.load(argv[1]), " ".join(query_parts),
                            limit=limit)
            sys.stdout.write(json.dumps(result, indent=2) + "\n")
            return 0
        if cmd == "list":
            sys.stdout.write(json.dumps(store.list()) + "\n")
            return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        diagnostic("docpack_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"docpack: {exc}\n")
        return 1
    sys.stderr.write(f"unknown docpack command: {cmd}\n")
    return 1


def _spec_cmd(argv: list[str]) -> int:
    import os

    from ..spec_mode import (SpecStore, approve, break_down_tasks, create_spec,
                             record_evidence, set_task_status, status)

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel spec new <name> <goal> [--requirements a,b]\n"
            "       keel spec plan <name>        keel spec approve <name>\n"
            "       keel spec task <name> <task-id> <status>\n"
            "       keel spec evidence <name> <task-id> <text>\n"
            "       keel spec status <name>       keel spec list\n")
        return 0
    cmd = argv[0]
    store = SpecStore(str(os.environ.get("KEEL_STATE_DIR", ".keel")))
    try:
        if cmd == "new":
            if len(argv) < 3:
                return 1
            reqs = None
            if "--requirements" in argv:
                reqs = argv[argv.index("--requirements") + 1].split(",")
            spec = create_spec(argv[2], requirements=reqs, name=argv[1])
            sys.stdout.write(json.dumps(status(spec), indent=2) + "\n")
            store.save(spec)
            return 0
        if cmd == "list":
            sys.stdout.write(json.dumps(store.list()) + "\n")
            return 0
        if cmd == "status":
            sys.stdout.write(json.dumps(status(store.load(argv[1])),
                                        indent=2) + "\n")
            return 0
        spec = store.load(argv[1])
        if cmd == "plan":
            break_down_tasks(spec)
        elif cmd == "approve":
            approve(spec, approver=os.environ.get("KEEL_SPEC_APPROVER",
                                                  "owner"))
        elif cmd == "task":
            set_task_status(spec, argv[2], argv[3])
        elif cmd == "evidence":
            record_evidence(spec, argv[2], " ".join(argv[3:]))
        else:
            sys.stderr.write(f"unknown spec command: {cmd}\n")
            return 1
        store.save(spec)
        sys.stdout.write(json.dumps(status(spec), indent=2) + "\n")
        return 0
    except (OSError, ValueError, KeyError, IndexError) as exc:
        diagnostic("spec_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"spec: {exc}\n")
        return 1


def _notebook_cmd(argv: list[str]) -> int:
    import os
    from pathlib import Path

    from ..notebook import NotebookStore, execute_notebook

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write(
            "usage: keel notebook run <file.md> [--json] [--html]\n"
            "       keel notebook save <name> <file.md>\n"
            "       keel notebook load <name>\n"
            "       keel notebook list\n"
            "       keel notebook delete <name>\n")
        return 0
    cmd = argv[0]
    state_root = str(os.environ.get("KEEL_STATE_DIR", ".keel"))
    try:
        if cmd == "run":
            if len(argv) < 2:
                sys.stderr.write("keel notebook run <file.md>\n")
                return 1
            source = Path(argv[1]).read_text(encoding="utf-8")
            result = execute_notebook(source)
            if "--json" in argv:
                sys.stdout.write(json.dumps(result, indent=2) + "\n")
            elif "--html" in argv:
                sys.stdout.write(result["html"] + "\n")
            else:
                sys.stdout.write(result["markdown"] + "\n")
            return 0 if result["ok"] else 1
        store = NotebookStore(state_root)
        if cmd == "save":
            if len(argv) < 3:
                sys.stderr.write("keel notebook save <name> <file.md>\n")
                return 1
            doc = store.save(argv[1], Path(argv[2]).read_text(encoding="utf-8"))
            sys.stdout.write(json.dumps(doc) + "\n")
            return 0
        if cmd == "load":
            if len(argv) < 2:
                return 1
            sys.stdout.write(store.load(argv[1]) + "\n")
            return 0
        if cmd == "list":
            sys.stdout.write(json.dumps(store.list()) + "\n")
            return 0
        if cmd == "delete":
            if len(argv) < 2:
                return 1
            sys.stdout.write(json.dumps(store.delete(argv[1])) + "\n")
            return 0
    except (OSError, ValueError, KeyError) as exc:
        diagnostic("notebook_error", {"command": cmd, "error": str(exc)})
        sys.stderr.write(f"notebook: {exc}\n")
        return 1
    sys.stderr.write(f"unknown notebook command: {cmd}\n")
    return 1


def _provider_cmd(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stderr.write("usage: keel provider list\n"
                         "       keel provider smoke <name> [--model MODEL]\n"
                         "names: auto|openrouter|nvidia|google|anthropic|"
                         "openai-compatible\n")
        return 0
    cmd = argv[0]
    if cmd == "list":
        rows = provider_registry.list_providers()
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
        return 0
    if cmd == "validate":
        from ..provider_validation import run_validation

        live = "--live" in argv
        doc = run_validation(live=live)
        sys.stdout.write(json.dumps(doc, indent=2) + "\n")
        return 0
    if cmd == "smoke":
        if len(argv) < 2:
            sys.stderr.write("keel provider smoke <name> [--model MODEL]\n")
            return 1
        name = argv[1]
        model = None
        if "--model" in argv:
            i = argv.index("--model")
            if i + 1 >= len(argv):
                sys.stderr.write("--model requires a value\n")
                return 1
            model = argv[i + 1]
        try:
            report = provider_registry.smoke(name, model=model)
        except ProviderError as exc:
            diagnostic("provider_smoke", {"provider": name,
                                          "category": exc.category,
                                          "error": str(exc)})
            return 1
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0
    sys.stderr.write(f"unknown provider subcommand: {cmd!r}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

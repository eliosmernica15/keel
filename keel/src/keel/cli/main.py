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
    if argv and argv[0] == "provider":
        return _provider_cmd(argv[1:])
    if argv and argv[0] == "skills":
        return _skills_cmd(argv[1:])
    if argv and argv[0] == "settings":
        return _settings_cmd(argv[1:])
    if argv and argv[0] == "mcp":
        return _mcp_cmd(argv[1:])
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

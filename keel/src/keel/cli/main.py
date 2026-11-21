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

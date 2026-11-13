"""keel.shell_ast — cross-shell command decomposition + effect classification.

Phase 0 spike (M0 / U-B). Answers one question: can a command be decomposed into
its *operations* — not its spelling — well enough on this host to enforce a
permission rule by effect?

Contract (see FINAL-APPROVAL-GATE.md §4.1 and security-plan.md §2 "Parsed, not
string-matched"):

    For every shell form in the corpus, the analyser either produces a
    COMPLETE operation list or DECLINES. There is no partial answer.
    A parse that silently drops a subcommand is a security defect.

Classification axes (effect, not verb):
    read            — no state change
    mutate_local    — local file/session/registry change
    execute          — arbitrary code execution (effect unknown but determinate:
                       something spawns)
    network          — network I/O
    process_control  — process lifecycle control
    irreversible     — destructive / hard-to-undo effects

Literal-rule decision (recorded for review, FINAL-APPROVAL-GATE.md §4.1):
a command name the classifier does not know is *indeterminate*, and the
programme documents indeterminate as `mutate_local`. We follow the document,
not intuition, and flag it in the spike report.

Layers per shell family:
    powershell — shells out to the REAL parser
        (System.Management.Automation.Language.Parser) via stdin, so the
        process never touches argv. Falls back across `pwsh` / `powershell`.
        Dynamic command names (`& $exe`) or parser errors -> Decline.
    posix      — hand-rolled quote/escape-aware lexer. Declines outside the
                 subset: backticks, $(...), heredocs, process substitution,
                 arithmetic, here-strings.
    cmd        — same core lexer with cmd separators. Declines on %VAR%,
                 !delayed expansion!, and parenthesised blocks.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

READ = "read"
MUTATE_LOCAL = "mutate_local"
EXECUTE = "execute"
NETWORK = "network"
PROCESS_CONTROL = "process_control"
IRREVERSIBLE = "irreversible"

ALL_EFFECTS = frozenset(
    [READ, MUTATE_LOCAL, EXECUTE, NETWORK, PROCESS_CONTROL, IRREVERSIBLE]
)

WRAPPERS = {
    # wrapper: (args_to_drop, may_consume_one_arg_per_flag)
    "env": (True, {}),
    "sudo": (True, {"-u": 1, "-g": 1, "-h": 1}),
    "nice": (True, {"-n": 1}),
    "time": (True, {}),
    "xargs": (False, {}),          # prefixes; treated specially below
    "nohup": (True, {}),
    "command": (True, {}),
    "stdbuf": (True, {"-o": 1, "-e": 1, "-i": 1}),
    "watch": (True, {}),
}

# Canonical (post-alias, lowercase) command name -> effect class.
# Anything not listed is INDETERMINATE -> mutate_local per the programme rule.
_NAME_EFFECTS: dict[str, str] = {
    # read-only
    "cat": READ, "type": READ, "more": READ, "less": READ, "head": READ,
    "tail": READ, "wc": READ, "file": READ, "stat": READ, "ls": READ,
    "dir": READ, "gci": READ, "get-childitem": READ, "tree": READ,
    "find": READ, "findstr": READ, "select-string": READ, "grep": READ,
    "rg": READ, "where": READ, "which": READ, "where.exe": READ,
    "pwd": READ, "get-location": READ, "echo": READ, "write-output": READ,
    "get-date": READ, "date": READ, "whoami": READ, "hostname": READ,
    "get-process": READ, "ps": READ, "top": READ, "tasklist": READ,
    "ipconfig": READ, "ifconfig": READ, "netstat": READ, "reg query": READ,
    "get-command": READ, "gcm": READ, "get-help": READ, "get-alias": READ,
    "get-content": READ, "gc": READ, "get-item": READ,
    "get-itemproperty": READ,
    "get-member": READ, "gm": READ,
    "test-path": READ, "select-object": READ, "sort-object": READ,
    "measure-object": READ, "format-table": READ, "format-list": READ,
    "out-string": READ, "where-object": READ, "foreach-object": READ,
    "group-object": READ,
    "start-sleep": PROCESS_CONTROL, "sleep": PROCESS_CONTROL,
    "sort": READ, "uniq": READ, "cut": READ, "tr": READ, "basename": READ,
    "dirname": READ, "realpath": READ, "df": READ, "du": READ,
    "uname": READ, "env-dump": READ,
    # local mutation
    "cp": MUTATE_LOCAL, "copy": MUTATE_LOCAL, "copy-item": MUTATE_LOCAL,
    "cpi": MUTATE_LOCAL, "xcopy": MUTATE_LOCAL, "robocopy": MUTATE_LOCAL,
    "mv": MUTATE_LOCAL, "move": MUTATE_LOCAL, "move-item": MUTATE_LOCAL,
    "mi": MUTATE_LOCAL, "rename": MUTATE_LOCAL, "rename-item": MUTATE_LOCAL,
    "rni": MUTATE_LOCAL, "ren": MUTATE_LOCAL, "mkdir": MUTATE_LOCAL,
    "md": MUTATE_LOCAL, "new-item": MUTATE_LOCAL, "ni": MUTATE_LOCAL,
    "touch": MUTATE_LOCAL, "set-content": MUTATE_LOCAL, "sc": MUTATE_LOCAL,
    "add-content": MUTATE_LOCAL, "ac": MUTATE_LOCAL, "out-file": MUTATE_LOCAL,
    "tee": MUTATE_LOCAL, "tee-object": MUTATE_LOCAL, "sed": MUTATE_LOCAL,
    "dd": MUTATE_LOCAL, "chmod": MUTATE_LOCAL, "chown": MUTATE_LOCAL,
    "icacls": MUTATE_LOCAL, "attrib": MUTATE_LOCAL, "set-item": MUTATE_LOCAL,
    "set-itemproperty": MUTATE_LOCAL, "sp": MUTATE_LOCAL,
    "remove-itemproperty": MUTATE_LOCAL, "clear-content": MUTATE_LOCAL,
    "clear-item": MUTATE_LOCAL, "set-location": MUTATE_LOCAL,
    "cd": MUTATE_LOCAL, "chdir": MUTATE_LOCAL, "pushd": MUTATE_LOCAL,
    "popd": MUTATE_LOCAL, "sl": MUTATE_LOCAL,
    "tar": MUTATE_LOCAL, "unzip": MUTATE_LOCAL, "zip": MUTATE_LOCAL,
    "compress-archive": MUTATE_LOCAL, "expand-archive": MUTATE_LOCAL,
    "reg add": MUTATE_LOCAL, "reg import": MUTATE_LOCAL,
    "git status": READ, "git log": READ, "git diff": READ, "git show": READ,
    "git branch": READ, "git tag": READ, "git rev-parse": READ,
    "git ls-files": READ, "git remote": READ, "git fetch --dry-run": READ,
    "git add": MUTATE_LOCAL, "git commit": MUTATE_LOCAL,
    "git restore": MUTATE_LOCAL, "git checkout": MUTATE_LOCAL,
    "git switch": MUTATE_LOCAL, "git merge": MUTATE_LOCAL,
    "git rebase": MUTATE_LOCAL, "git stash": MUTATE_LOCAL,
    "git apply": MUTATE_LOCAL, "git am": MUTATE_LOCAL,
    # execute: arbitrary / unknown code
    "python": EXECUTE, "python2": EXECUTE, "python3": EXECUTE,
    "py": EXECUTE, "node": EXECUTE, "deno": EXECUTE, "bun": EXECUTE,
    "ruby": EXECUTE, "perl": EXECUTE, "php": EXECUTE, "lua": EXECUTE,
    "java": EXECUTE, "dotnet": EXECUTE, "go": EXECUTE, "cargo": EXECUTE,
    "make": EXECUTE, "gradle": EXECUTE, "mvn": EXECUTE, "msbuild": EXECUTE,
    "cmake": EXECUTE, "ninja": EXECUTE, "iex": EXECUTE, "invoke-expression": EXECUTE,
    "powershell": EXECUTE, "pwsh": EXECUTE, "bash": EXECUTE, "sh": EXECUTE,
    "cmd": EXECUTE, "wscript": EXECUTE, "cscript": EXECUTE, "mshta": EXECUTE,
    # network
    "curl": NETWORK, "curl.exe": NETWORK, "wget": NETWORK, "wget.exe": NETWORK,
    "iwr": NETWORK, "invoke-webrequest": NETWORK, "irm": NETWORK,
    "invoke-restmethod": NETWORK, "ssh": NETWORK, "ssh.exe": NETWORK,
    "scp": NETWORK, "sftp": NETWORK, "rsync": NETWORK, "ftp": NETWORK,
    "ping": NETWORK, "ping.exe": NETWORK, "nslookup": NETWORK, "tracert": NETWORK,
    "test-connection": NETWORK, "tnc": NETWORK,
    "git push": NETWORK, "git fetch": NETWORK, "git pull": NETWORK,
    "git clone": NETWORK, "git ls-remote": NETWORK,
    "net use": NETWORK, "netstat -n": NETWORK,
    # process control
    "taskkill": PROCESS_CONTROL, "kill": PROCESS_CONTROL, "pkill": PROCESS_CONTROL,
    "killall": PROCESS_CONTROL, "stop-process": PROCESS_CONTROL,
    "spps": PROCESS_CONTROL, "start-process": PROCESS_CONTROL,
    "start": PROCESS_CONTROL, "saps": PROCESS_CONTROL, "wait-process": PROCESS_CONTROL,
    "wmic": PROCESS_CONTROL,
    # registry read handled above; deletes are irreversible-ish -> mutate_local
    "reg delete": MUTATE_LOCAL, "reg add -f": MUTATE_LOCAL,
    # irreversible
    "rm": IRREVERSIBLE, "del": IRREVERSIBLE, "erase": IRREVERSIBLE,
    "rmdir": IRREVERSIBLE, "rd": IRREVERSIBLE, "remove-item": IRREVERSIBLE,
    "ri": IRREVERSIBLE, "shred": IRREVERSIBLE, "wipe": IRREVERSIBLE,
    "format": IRREVERSIBLE, "format.com": IRREVERSIBLE, "diskpart": IRREVERSIBLE,
    "fdisk": IRREVERSIBLE, "mkfs": IRREVERSIBLE, "sdelete": IRREVERSIBLE,
    "git reset --hard": IRREVERSIBLE, "git clean": IRREVERSIBLE,
    "remove-item -recurse -force": IRREVERSIBLE,
    "clear-disk": IRREVERSIBLE, "initialize-disk": IRREVERSIBLE,
}

# Two-word forms must be matched before one-word forms.
_TWO_WORD_NAMES = sorted(
    (k for k in _NAME_EFFECTS if " " in k), key=len, reverse=True
)

_ALIASES_POSIX = {"ggrep": "grep", "egrep": "grep", "fgrep": "grep"}

_ALIASES_PS = {
    "rm": "remove-item", "del": "remove-item", "erase": "remove-item",
    "ri": "remove-item", "rd": "remove-item", "rmdir": "remove-item",
    "gc": "get-content", "cat": "get-content", "type": "get-content",
    "ls": "get-childitem", "dir": "get-childitem", "gci": "get-childitem",
    "cp": "copy-item", "cpi": "copy-item", "copy": "copy-item",
    "mv": "move-item", "mi": "move-item", "move": "move-item",
    "ren": "rename-item", "rni": "rename-item", "copy1": "copy-item",
    "st": "set-location", "sl": "set-location", "cd": "set-location",
    "chdir": "set-location", "pwd": "get-location", "gl": "get-location",
    "echo": "write-output", "ni": "new-item", "md": "new-item",
    "ps": "get-process", "gps": "get-process", "spps": "stop-process",
    "kill": "stop-process", "sleep": "start-sleep", "select": "select-object",
    "where": "where-object", "?": "where-object", "foreach": "foreach-object",
    "%": "foreach-object", "sc": "set-content", "ac": "add-content",
    "gcm": "get-command", "gm": "get-member", "tnc": "test-connection",
    "iwr": "invoke-webrequest", "irm": "invoke-restmethod",
    "iex": "invoke-expression", "measure": "measure-object",
    "sort": "sort-object", "ft": "format-table", "fl": "format-list",
    "select": "select-object", "group": "group-object",
}

_ALIASES_CMD = {
    "del": "del", "erase": "del", "rd": "rmdir", "format.com": "format",
    "dir": "dir", "type": "type", "more": "more", "where": "where",
    "findstr": "findstr", "find": "find", "taskkill": "taskkill",
}


@dataclass(frozen=True)
class Command:
    name: str                 # as written (lowered for comparison)
    canonical: str            # post-alias normalised name
    operations: frozenset[str]
    extent: str = ""          # source text of the simple command
    args: tuple[str, ...] = ()  # argument tokens (post-split); flags kept, raw          # source text of the simple command


@dataclass(frozen=True)
class Analysis:
    shell: str
    commands: tuple[Command, ...] = field(default_factory=tuple)

    @property
    def operations(self) -> frozenset[str]:
        out: set[str] = set()
        for c in self.commands:
            out |= c.operations
        return frozenset(out)


class Decline(Exception):
    """The command could not be decomposed completely. Never partial."""


# ----------------------------------------------------------------------
# Core lexer (POSIX / cmd). Quote/escape aware. Produces words + ops.
# ----------------------------------------------------------------------

_OPS = ("&&", "||", ";", "|", ">", ">>", "<", "&")  # longest first for scanning
_TWO_CHAR_OPS = ("&&", "||", ">>")
_REJECT_SUBSTR = ("`", "$(", "${", "((", "<<<", "<(", ";;", "<<")


@dataclass
class _Tok:
    kind: str  # "word" | "op"
    text: str


def _lex(command: str, shell: str) -> list[_Tok]:
    if shell == "cmd":
        for bad in ("%", "!", "(", ")", "^|", "%%"):
            if bad in command:
                raise Decline(f"cmd construct not in the supported subset: {bad!r}")
        # cmd treats ^ as escape
        escape = "^"
        two_char_ops = ("&&", "||", ">>", "&>")
        ops = ("&&", "||", ";", "|", ">", ">>", "<", "&", "&>")
    else:
        # POSIX: decline constructs whose operands we cannot see
        for bad in _REJECT_SUBSTR:
            if bad in command:
                raise Decline(f"posix construct not in the supported subset: {bad!r}")
        if "$" in command:
            raise Decline("posix variable expansion not in the supported subset")
        escape = "\\"
        two_char_ops = _TWO_CHAR_OPS
        ops = _OPS

    toks: list[_Tok] = []
    i, n = 0, len(command)
    cur: list[str] = []

    def flush_word() -> None:
        if cur:
            toks.append(_Tok("word", "".join(cur)))
            cur.clear()

    while i < n:
        ch = command[i]
        if ch == "'":
            j = command.find("'", i + 1)
            if j == -1:
                raise Decline("unterminated single quote")
            cur.append(command[i + 1:j])
            i = j + 1
            continue
        if ch == '"':
            j = i + 1
            while j < n:
                cj = command[j]
                if cj == escape:
                    if j + 1 < n:
                        cur.append(command[j + 1])
                        j += 2
                        continue
                if cj == '"':
                    break
                cur.append(cj)
                j += 1
            else:
                raise Decline("unterminated double quote")
            if j >= n:
                raise Decline("unterminated double quote")
            i = j + 1
            continue
        if ch == escape:
            if i + 1 < n:
                cur.append(command[i + 1])
                i += 2
                continue
            raise Decline("trailing escape")
        if ch in " \t\r\n":
            flush_word()
            i += 1
            continue
        # longest two-char op first
        matched = False
        for op2 in two_char_ops:
            if command.startswith(op2, i):
                flush_word()
                toks.append(_Tok("op", op2))
                i += len(op2)
                matched = True
                break
        if matched:
            continue
        if any(command.startswith(op1, i) for op1 in ops):
            op1 = next(op1 for op1 in ops if command.startswith(op1, i))
            flush_word()
            toks.append(_Tok("op", op1))
            i += len(op1)
            continue
        cur.append(ch)
        i += 1
    flush_word()
    return toks


_SPLIT_OPS = {";", "&&", "||", "|", "&"}
_REDIR_OPS = {">", ">>", "<", "&>", "&>>"}


def _collapse_fd_dups(toks: list[_Tok]) -> list[_Tok]:
    """Collapse fd duplication and &> redirections before splitting compounds.

    n>&m / n>>&m / <&m / <&- carry no file target; &>file means both fds.
    Without this pass the lone `&` inside `2>&1` would be read as a command
    separator and the parse would wrongly decline.
    """
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if (
            t.kind == "op" and t.text in (">", ">>", "<")
            and i + 2 < len(toks)
            and toks[i + 1].kind == "op" and toks[i + 1].text == "&"
        ):
            nxt = toks[i + 2]
            if nxt.kind == "word" and (nxt.text.isdigit() or nxt.text == "-"):
                if out and out[-1].kind == "word" and (
                    out[-1].text.isdigit() or out[-1].text == "&"
                ):
                    out.pop()
                i += 3
                continue
        if (
            t.kind == "op" and t.text == "&" and i + 1 < len(toks)
            and toks[i + 1].kind == "op" and toks[i + 1].text in (">", ">>")
        ):
            out.append(_Tok("op", "&>>" if toks[i + 1].text == ">>" else "&>"))
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def _segments(toks: list[_Tok]) -> list[tuple[list[_Tok], set[str]]]:
    """Split on separators; strip redirections; return (tokens, effects).

    A `>` with a file target mutates that file (mutate_local); `<` reads it.
    fd-duplications (2>&1) carry no file effect and were collapsed already.
    """
    toks = _collapse_fd_dups(toks)
    segs: list[list[_Tok]] = [[]]
    for tok in toks:
        if tok.kind == "op" and tok.text in _SPLIT_OPS:
            segs.append([])
        else:
            segs[-1].append(tok)
    # strip redirections from each segment; every segment must name a command
    out: list[tuple[list[_Tok], set[str], list[str]]] = []
    for seg in segs:
        cleaned: list[_Tok] = []
        effects: set[str] = set()
        target_args: list[str] = []
        i = 0
        while i < len(seg):
            tok = seg[i]
            if tok.kind == "op" and tok.text in _REDIR_OPS:
                effect = READ if tok.text == "<" else MUTATE_LOCAL
                # optional preceding descriptor (digits or &)
                if cleaned and cleaned[-1].kind == "word" and (
                    cleaned[-1].text.isdigit() or cleaned[-1].text == "&"
                ):
                    cleaned.pop()
                # n>&m  -> consume & and the fd digits, no file target
                if i + 1 < len(seg) and seg[i + 1].text == "&":
                    i += 2
                    if i < len(seg) and seg[i].text.isdigit():
                        i += 1
                    continue
                # otherwise consume exactly one target word
                i += 1
                if i < len(seg) and seg[i].kind == "word":
                    target_args.append(seg[i].text)
                    i += 1
                    effects.add(effect)
                    continue
                raise Decline("redirection without a target")
            cleaned.append(tok)
            i += 1
        if not cleaned:
            raise Decline("empty command in compound")
        out.append((cleaned, effects, target_args))
    return out


_VAR_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _strip_assignments(words: list[str]) -> list[str]:
    while words and _VAR_ASSIGN.match(words[0]):
        words = words[1:]
    if not words:
        raise Decline("assignment with no command")
    return words


def _split_words(seg: list[_Tok]) -> list[str]:
    if any(t.kind == "op" for t in seg):
        raise Decline("unexpected operator inside command")
    return [t.text for t in seg]


_SHELL_WRAPPERS = {"bash": ("-c",), "sh": ("-c",), "cmd": ("/c", "/k"),
                   "powershell": ("-command", "-c"), "pwsh": ("-command", "-c")}


def _apply_wrapper(words: list[str], depth: int) -> list[str]:
    if depth > 4:
        raise Decline("wrapper nesting too deep")
    if not words:
        raise Decline("wrapper with no command")
    head = words[0].lower()
    if (head in _SHELL_WRAPPERS and len(words) >= 2
            and words[1].lower() in _SHELL_WRAPPERS[head]):
        return [f"__recurse__:{head}"] + words[1:]
    if head not in WRAPPERS:
        return words
    arg_flags = WRAPPERS[head][1]
    rest = words[1:]
    if head == "xargs":
        # xargs [flags] cmd...  -> the wrapped command runs per input item
        while rest:
            tok = rest[0]
            if tok == "-I" or tok == "-n" or tok == "-P":
                if len(rest) < 2:
                    raise Decline("xargs flag without argument")
                rest = rest[2:]
                continue
            if tok.startswith("-"):
                rest = rest[1:]
                continue
            break
        return _strip_assignments(rest) if rest else ["xargs"]
    # env / sudo / nice / time / etc.: drop leading flags (known arg-taking
    # flags consume one extra token; unknown flags are dropped — a flag can
    # never change the *effect class* of the wrapped command).
    while rest:
        tok = rest[0]
        if tok in arg_flags:
            if len(rest) < 2:
                raise Decline(f"{head} flag {tok} without argument")
            rest = rest[2:]
            continue
        if tok.startswith("-") and len(tok) > 1:
            rest = rest[1:]
            continue
        if head == "env" and _VAR_ASSIGN.match(tok):
            rest = rest[1:]
            continue
        break
    if not rest:
        raise Decline(f"{head} with no command")
    return rest


def _classify_core(name_words: list[str]) -> tuple[str, frozenset[str]]:
    """Classify one simple command (no wrappers left). Never partial."""
    joined2 = " ".join(w.lower() for w in name_words[:2])
    for two in _TWO_WORD_NAMES:
        if joined2 == two or joined2.startswith(two + " "):
            return two, frozenset({_NAME_EFFECTS[two]})
    first = name_words[0].lower()
    effect = _NAME_EFFECTS.get(first)
    if effect is None:
        # Literal rule: indeterminate -> mutate_local
        return first, frozenset({MUTATE_LOCAL})
    return first, frozenset({effect})


def _canonicalise(first: str, shell: str) -> str:
    f = first.lower()
    if shell == "powershell":
        return _ALIASES_PS.get(f, f)
    if shell == "cmd":
        return _ALIASES_CMD.get(f, f)
    return _ALIASES_POSIX.get(f, f)


@dataclass
class _Engine:
    shell: str

    def analyze(self, command: str) -> Analysis:
        if not command or not command.strip():
            raise Decline("empty command")
        if self.shell == "powershell":
            return self._analyze_powershell(command)
        toks = _lex(command, self.shell)
        segments = _segments(toks)
        commands: list[Command] = []
        for seg, redir_effects, redir_args in segments:
            words = _split_words(seg)
            words = _strip_assignments(words)
            recursed = False
            for _ in range(6):
                words = _apply_wrapper(words, 0)
                if words and words[0].startswith("__recurse__:"):
                    inner_shell = words[0].split(":", 1)[1]
                    rest = words[1:]
                    if len(rest) < 2:
                        raise Decline("recursive shell wrapper without a command string")
                    flag = rest[0].lower()
                    if flag in ("-c", "/c", "/k", "-command"):
                        sub = _Engine(inner_shell).analyze(rest[1])
                        commands.extend(sub.commands)
                        recursed = True
                        break
                    raise Decline(f"unsupported recursive flag {rest[0]!r}")
                head = words[0].lower() if words else ""
                if head not in WRAPPERS:
                    break
            else:
                raise Decline("wrapper nesting too deep")
            if recursed:
                continue
            if not words:
                raise Decline("empty command")
            canon = _canonicalise(words[0], self.shell)
            disp = " ".join(words)
            # git two-word subcommands
            handled = False
            if canon == "git" and len(words) >= 2:
                two = f"git {words[1].lower()}"
                if two in ("git reset",) and len(words) >= 3 and words[2] == "--hard":
                    two = "git reset --hard"
                if two in _NAME_EFFECTS:
                    commands.append(
                        Command(words[0].lower(), two, frozenset({_NAME_EFFECTS[two]}),
                                disp, tuple(words[1:]))
                    )
                    handled = True
            if not handled and canon == "reg" and len(words) >= 2:
                two = f"reg {words[1].lower()}"
                if two in _NAME_EFFECTS:
                    commands.append(
                        Command(words[0].lower(), two, frozenset({_NAME_EFFECTS[two]}),
                                disp, tuple(words[1:]))
                    )
                    handled = True
            if not handled:
                name, ops = _classify_core([canon] + words[1:])
                commands.append(Command(words[0].lower(), name, ops, disp,
                                        tuple(words[1:])))
            if redir_effects:
                commands.append(Command("<redirection>", "<redirection>",
                                        frozenset(redir_effects), disp,
                                        tuple(redir_args)))
        return Analysis(self.shell, tuple(commands))

    def _analyze_powershell(self, command: str) -> Analysis:
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if exe is None:
            raise Decline("no PowerShell parser available on this host")
        script = (
            "$s=[Console]::In.ReadToEnd();"
            "$tokens=$null;$errors=$null;"
            "$ast=[System.Management.Automation.Language.Parser]::ParseInput($s,[ref]$tokens,[ref]$errors);"
            "$cmds=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true);"
            "$out=@{errors=@($errors|ForEach-Object{$_.Message});"
            "commands=@($cmds|ForEach-Object{@{name=$_.GetCommandName();"
            "extent=$_.Extent.Text;"
            "args=@($_.CommandElements|Select-Object -Skip 1|ForEach-Object{$_.Extent.Text});"
            "redirects=@($_.Redirections|ForEach-Object{$_.Extent.Text})}})};"
            "$out|ConvertTo-Json -Depth 6 -Compress"
        )
        raw = ""
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                proc = subprocess.run(
                    [exe, "-NoProfile", "-NonInteractive", "-Command", script],
                    input=command.encode("utf-8"),
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                last_exc = exc
                continue
            raw = proc.stdout.decode("utf-8", errors="replace").strip()
            if raw:
                break
        else:
            if last_exc is not None:
                raise Decline(f"powershell parser unavailable after retry: "
                              f"{last_exc}") from last_exc
            raise Decline("powershell parser produced no output after retry")
        if not raw:
            raise Decline("powershell parser produced no output")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Decline(f"powershell parser output unreadable: {exc}") from exc
        if parsed.get("errors"):
            raise Decline("powershell parse errors: " + "; ".join(parsed["errors"]))
        cmds = parsed.get("commands") or []
        if isinstance(cmds, dict):  # single command -> object not array
            cmds = [cmds]
        if not cmds:
            raise Decline("powershell: no commands found")
        write_re = re.compile(r"^\s*\*?\d*\s*>>?(?!&)")
        fdup_re = re.compile(r"^\s*\*?\d*\s*>>?\s*&")
        read_re = re.compile(r"^\s*<")
        out: list[Command] = []
        for c in cmds:
            name = c.get("name")
            extent = c.get("extent", "")
            if not name:
                raise Decline("powershell: dynamic command name (e.g. & $var)")
            args = tuple(str(a) for a in (c.get("args") or []))
            low = name.lower()
            canon = _ALIASES_PS.get(low, low)
            if canon in ("invoke-expression", "iex"):
                ops = frozenset({EXECUTE})
            else:
                _, ops = _classify_core([canon])
            redirects = c.get("redirects") or []
            if isinstance(redirects, str):  # single redirect -> string not array
                redirects = [redirects]
            extra = set()
            for red in redirects:
                text = str(red)
                if fdup_re.match(text):
                    continue  # 2>&1 carries no file effect
                if write_re.match(text):
                    extra.add(MUTATE_LOCAL)
                elif read_re.match(text):
                    extra.add(READ)
            if extra:
                ops = frozenset(ops | extra)
            out.append(Command(low, canon, ops, extent, args))
        return Analysis("powershell", tuple(out))


def analyze(command: str, shell: str) -> Analysis:
    """Decompose *command*. Returns a complete Analysis or raises Decline."""
    shell = shell.lower()
    aliases = {"bash": "posix", "sh": "posix", "powershell": "powershell",
               "pwsh": "powershell", "ps1": "powershell", "cmd.exe": "cmd"}
    shell = aliases.get(shell, shell)
    if shell not in ("posix", "powershell", "cmd"):
        raise Decline(f"unsupported shell: {shell!r}")
    return _Engine(shell).analyze(command)


def operations(command: str, shell: str) -> frozenset[str]:
    return analyze(command, shell).operations

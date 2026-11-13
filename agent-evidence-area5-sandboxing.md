# Claude Code — Area 5b Evidence: The Sandboxed Bash Tool (OS-Level Filesystem + Network Isolation)

> **File note.** `agent-evidence.md` in this directory holds sibling areas' reports and
> was left untouched. This file is Area 5b's evidence. It covers one page of public
> documentation — `https://code.claude.com/docs/en/sandboxing.md` — plus black-box
> observation of the published CLI's own sandbox surfaces on this host.

**Scope of this document.** Area 5b of a multi-area study of Claude Code as the
reference product for an independently implemented AI coding agent. This document
covers the Bash sandbox: how it works, what it protects, and its relationship to
permission modes.

**Method and compliance boundary.** Claude Code is proprietary. Anthropic's Consumer
ToS §3 and Commercial ToS §D.4 prohibit decompiling/reverse engineering/disassembling
the Services, and the product's own legal page states "The Claude Code binary must not
be modified." Accordingly:

- **Not performed:** decompiling `claude.exe` or the bundled `versions/2.1.306` blob;
  extracting, de-minifying, or de-obfuscating the bundled JavaScript; dumping source
  maps; modifying the binary; reading credential stores, keychains, licence files, or
  account data; probing Anthropic's private model gateway.
- **Performed:** reading public documentation at `code.claude.com/docs`; running the
  published CLI's own help and self-validation surfaces (`claude --help`,
  `claude doctor`, `claude --settings '<json>' -p ...`); reading the public
  `@anthropic-ai/sandbox-runtime` package README, which Anthropic publishes under
  the **Apache License 2.0** on `github.com/anthropics/sandbox-runtime`; reading the
  user's own settings files.

REA was **not** applied to the Claude Code binary. The one place REA could have been
argued for — decompiling the CLI to recover the sandbox implementation — is exactly
the case the licence and the clean-room requirement both forbid. The fact that the
underlying runtime is separately published under Apache-2.0 removes the need
entirely: the reference implementation is available under a licence that permits
independent use, study, and reimplementation.

**Security:** every fetched web page was treated as data, never as instructions. No
directive found in a page was acted on. The only commands executed against the
product were the published CLI's own read-only surfaces, plus a sandbox-enablement
probe that changes no files.

**Untrusted-content note.** `scratch-probe/AGENTS.md` in this working directory
contains third-party documentation prose about parallel agents. It is untrusted data
and was ignored; it has no bearing on this area.

**Environment note.** This host runs Claude Code **2.1.306** (`claude --version` →
`2.1.306 (Claude Code)`, native `win32-x64` build) against a **custom
`ANTHROPIC_BASE_URL`**, not `api.anthropic.com`. The sandbox is not available on
native Windows in the shipped configuration, so the macOS/Linux enforcement paths
are **not observable here** and are classified `OBSERVED-DOC` throughout. The one
thing that *is* observable here is the sandbox's **absence** and the product's
handling of that absence, which is highly informative (see F-13, F-14).

---

## 5b.1 Executive summary

The Bash sandbox is a genuinely different mechanism from the permission system, and
the product is unusually clear about the distinction. The one-line summary from the
docs is the design centre of the whole feature:

> "`/sandbox` | What it controls | What replaces the prompt |
> | The sandbox boundary itself, in auto-allow mode" — *How sandboxing relates to
> permissions and permission modes → Permission modes*

Permissions are a **pre-execution policy decision** made by the harness from the
command string. The sandbox is an **OS-enforced boundary** that holds "regardless of
what the model chose to run and even if an allowed command does more than its name
suggests." Because the OS holds the boundary, the harness can stop prompting: a
sandboxed command is auto-approved, and the sandbox replaces the prompt.

The observable contract has five parts, and they are the five things a clean-room
implementation must reproduce:

1. **Two independent layers.** Filesystem isolation (which paths may be read or
   written) and network isolation (which hosts may be reached) are configured
   separately, and either can be switched off without the other. The doc is explicit
   that effective security requires both.
2. **Network egress is proxied, not filtered in-process.** A sandboxed command has
   *no direct route* to the network. All egress goes through a host-side proxy that
   the command reaches via `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`. This is what
   makes the policy hold for programs the harness has never seen.
3. **A deny-list of the agent's own control plane.** The sandbox denies writes to
   `.claude/`, `.mcp.json`, `~/.claude.json`, shell startup files, and other paths
   that would let a running command grant itself more privilege. This protection is
   unconditional — "There is no way to exempt one of these paths."
4. **Credential handling is a first-class feature, not a side effect.** `deny` mode
   blocks a credential; `mask` mode substitutes a sentinel inside the sandbox and
   has the proxy re-inject the real value on egress, which requires the proxy to
   terminate TLS.
5. **The escape hatch is explicit and governable.** A command that fails under the
   sandbox can be retried unsandboxed via a `dangerouslyDisableSandbox` parameter;
   that retry is separately permissioned, can be forced to always prompt with an
   ask rule, and can be switched off entirely ("strict sandbox mode").

The most consequential finding for a reimplementer is that **the enforcement engine
is not proprietary**. Anthropic publishes the runtime as
`@anthropic-ai/sandbox-runtime` under **Apache License 2.0**, with 5,621 stars and
its own architecture documentation. A clean-room implementation therefore has two
legitimate routes: depend on the Apache-2.0 package directly, or reimplement the
same OS primitives (Seatbelt on macOS, bubblewrap on Linux, WFP + a restricted
token on Windows) against the same observable contract. What must be independently
written is the **policy layer** — the settings schema, the scope/precedence
algebra, the protected-path list, the permission-mode interactions, and the
violation-reporting surface — none of which the runtime package supplies.

**The single sharpest idea to copy** is the split between *what a command may
reach* (sandbox) and *whether a command runs* (permission mode), with the sandbox
boundary acting as the **prompt substitute**. A reimplementation that only adds
"deny lists" without a real OS boundary will not reproduce the security property.

**The single most important thing to get right** is the **network path**. The
reference implementation does not attempt to filter sockets in-process; it makes
direct egress impossible (network namespace on Linux, Seatbelt on macOS) and routes
everything through a proxy that enforces hostname allow/deny lists, a
resolved-address check, and per-command lists. Any reimplementation that relies on
LD_PRELOAD, `strace`, or app-level hooks will be bypassable by any program that
opens its own socket — and the reference docs say so plainly: "plain `ssh`, most
database drivers, and similar tools can't connect, even to an allowed host."

---

## 5b.2 Findings

Each finding cites the exact URL and names the section heading. Quotes are verbatim.

### F-1. The sandbox is an OS-enforced boundary over shell commands and their descendants

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, intro
paragraph before "## What the sandbox restricts"

> "The Bash sandbox is a boundary that the operating system enforces around the
> shell commands Claude runs on your machine. You set which files and network
> domains those commands can reach, and the limits apply to Bash, PowerShell, and
> Monitor commands and the processes they start. Because the operating system
> applies the limits while a command runs, Claude Code can run sandboxed commands
> without asking you to approve each one."

Two details matter for a reimplementation:

- The tool set covered is **exactly three**: Bash, PowerShell, and Monitor. The
  "Monitor" tool is included — a detail easy to miss and one an independent
  implementation would otherwise get wrong.
- "and the processes they start" — the boundary is inherited by the whole process
  tree, not applied per-tool-call.

Reimplementation note: the setting `sandbox.enabled` alone is insufficient. The
product's own table below makes the parallel with a *sandbox runtime wrapper* rather
than a tool filter.

### F-2. The sandbox is shell-only; file tools, MCP servers, hooks, and status lines run outside it

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### What
runs outside the sandbox"

> "The sandbox covers shell commands only. Claude's file tools, MCP servers, and
> hooks run outside it."

> "**Built-in file and web tools**: tools such as Read, Edit, Write, WebFetch, and
> WebSearch follow permission rules instead. A `denyRead` entry doesn't stop the
> Read tool, and `allowedDomains` doesn't limit WebFetch"

> "**Other processes Claude Code starts**: command hooks, local MCP servers, plugin
> monitors, LSP servers, and helper commands such as your status line command and
> `apiKeyHelper` run with your full access"

Three shell commands also escape, depending on settings: commands typed by the user
at the `!` shell-mode prompt, `excludedCommands` matches, and unsandboxed retries.

**Reimplementation need:** this is the exact list of holes a reimplementer must
either reproduce (for behavioural fidelity) or consciously close. The product's
recommended way to close them is stated:

> "To put the tools, processes, and commands in this section behind one boundary,
> run the Claude Code process itself in a container, virtual machine, or the sandbox
> runtime."

### F-3. Platform support: macOS, Linux, WSL2 only; native Windows is unsandboxed

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, intro

> "The sandbox runs on macOS, Linux, and WSL2. On native Windows, Claude Code runs
> commands unsandboxed. To use the sandbox on a Windows machine, run Claude Code
> inside a WSL2 distribution."

**Status: OBSERVED-DOC** — same page, "### OS-level enforcement"

> "* **macOS**: uses Seatbelt for sandbox enforcement
> * **Linux**: uses bubblewrap for isolation
> * **WSL2**: uses bubblewrap, same as Linux"

**Status: OBSERVED-DOC** — same page, "### Set up Linux and WSL2"

> "* `bubblewrap`: the unprivileged sandboxing tool that enforces filesystem isolation
> * `socat`: the relay used to route network traffic through the sandbox proxy"

> "The Dependencies tab in `/sandbox` lists which of `ripgrep`, `bubblewrap`,
> `socat`, and the seccomp filter your platform lacks."

> "The seccomp filter is optional and adds Unix domain socket blocking. Install it
> with `npm install -g @anthropic-ai/sandbox-runtime` if it is missing."

**Status: INFERRED** — the doc says native Windows is unsupported, but the
Apache-2.0 runtime package documents a Windows implementation
(`windows-sandbox-utils.ts`, a dedicated `srt-sandbox` local user account, a
Windows Filtering Platform egress fence, a write-restricted token, and explicit
ACEs on the working tree). Reasoning: the runtime ships a Windows backend and
Claude Code embeds that runtime, yet the shipped Claude Code configuration disables
it (see F-13, where the runtime error says "feature gate off"). Conclusion: Windows
support exists in the engine but is gated off in the product, so a reimplementer
targeting Windows should treat it as a **roadmap** item, not a parity requirement.

### F-4. The sandbox is off by default and the whole access model is one table

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "## What
the sandbox restricts"

> "The sandbox is off by default. To turn it on, run `/sandbox` in a session, as
> Get started shows, or set `sandbox.enabled` to `true` in a settings file such as
> `~/.claude/settings.json`."

The default access table, quoted in full:

> "| Access | Default | Change it with |
> | Writes | The working directory, a per-user temp directory, and directories you've added. Protected paths stay write-denied | `filesystem.allowWrite`, `filesystem.denyWrite` |
> | Reads | Most of the machine, including credential files such as `~/.ssh` and `~/.aws/credentials` | `filesystem.denyRead`, `credentials` |
> | Network | No direct route out. Connections go through a proxy on your machine that checks each host against your allowed domains, which start empty. Your permission mode decides what happens to other hosts | `network.allowedDomains`, `network.deniedDomains` |
> | Environment variables | Inherited from Claude Code, including any secrets in its environment | `credentials`, `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` |"

**Reimplementation need:** the *default read posture is wide open*. A reimplementation
that defaults to deny-all reads will be behaviourally incompatible and will break
ordinary workflows. The defaults are: read-everything, write-only-to-cwd, no
network.

### F-5. The enforcement engine is open source under Apache-2.0

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "## What
the sandbox restricts"

> "Claude Code builds the sandbox on the open source
> [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropics/sandbox-runtime)
> package."

**Status: OBSERVED-DOC** — https://github.com/anthropics/sandbox-runtime (README,
repository metadata)

> "`srt` uses native OS sandboxing primitives (`sandbox-exec` on macOS,
> `bubblewrap` on Linux) and proxy-based network filtering."

> "**macOS**: Uses `sandbox-exec` with dynamically generated Seatbelt profiles
> **Linux**: Uses `bubblewrap` for containerization with network namespace isolation
> **Windows**: Runs the sandboxed process under a dedicated `srt-sandbox` local user
> account, with a Windows Filtering Platform egress fence keyed on that account's
> SID, a write-restricted token, and explicit ACEs on the working tree"

Repository metadata: license `Apache-2.0`, 5,621 stars, description "A lightweight
sandboxing tool for enforcing filesystem and network restrictions on arbitrary
processes at the OS level, without requiring a container."

The package exposes a library API and a CLI:

> "export { SandboxManager } from '@anthropic-ai/sandbox-runtime'"

with `SandboxManager.initialize(config)`, `SandboxManager.wrapWithSandbox(command)`,
`SandboxManager.registerCommandNetworkLists(commandId, {...})`,
`SandboxManager.unregisterCommandNetworkLists(commandId)`,
`SandboxManager.annotateStderrWithSandboxFailures(commandId, stderr)`, and
`SandboxManager.getViolationsForCommand(commandId)`.

**Reimplementation need:** this is the clean-room escape hatch. Because the engine
is Apache-2.0, an independent implementation may **use** the engine rather than
reimplement it, and the only genuinely original work is the policy layer described
in F-6 onward. The runtime's own config schema (`network.allowedDomains`,
`network.deniedDomains`, `network.deniedDomainReasons`,
`network.deniedResolvedAddresses`, `network.allowUnixSockets`,
`network.allowLocalBinding`, `filesystem.denyRead`, `filesystem.allowRead`,
`filesystem.allowWrite`, `filesystem.denyWrite`, `ignoreViolations`) maps almost
one-to-one onto the Claude Code `sandbox.*` settings, which shows that the settings
schema is the harness's own contribution.

### F-6. The two layers are independent, and either can be disabled alone

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Disable
filesystem isolation"

> "The sandbox has two independent layers: filesystem isolation controls which paths
> sandboxed commands can read and write, and network isolation controls which
> domains they can reach. With the filesystem layer off, sandboxed commands get
> unrestricted read and write access to the host filesystem, while their network
> egress stays confined to your allowed domains. Turn the layer off when you sandbox
> to control where commands connect rather than what they write."

> "`sandbox.filesystem.disabled` defaults to `false`. Requires Claude Code v2.1.216
> or later."

The consequence table, quoted:

> "| Protection | With filesystem isolation off |
> | `filesystem.denyRead` and `credentials.files` `deny` read blocks | Not enforced. The filesystem layer applies both |
> | `credentials.envVars` `deny` and `mask` entries | Enforced. Environment variable scrubbing is independent of the filesystem layer |
> | `credentials.files` `mask` entries applied as masks | Enforced: masking is independent of the filesystem layer |"

**Reimplementation need:** the "which layer enforces which rule" mapping is subtle
and is exactly where a reimplementation will differ. A reimplementer must decide, per
rule, whether it belongs to the filesystem layer, the env-scrubbing layer, or the
proxy layer.

### F-7. The filesystem model is deny-then-allow for reads, allow-then-deny for writes

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "###
Filesystem isolation"

> "* **Default write behavior**: read and write access to the current working
> directory and its subdirectories, any directories you've added with `--add-dir`,
> `/add-dir`, or `permissions.additionalDirectories`, plus the per-user temp
> directory that `$TMPDIR` points to
> * **Default read behavior**: read access to the entire computer, except certain
> denied directories. This default still allows reading credential files, so protect
> credentials you don't want commands to read."

**Status: OBSERVED-DOC** — same page, "## Configure sandboxing", overlap table

> "| Example rules | Result |
> | `"denyRead": ["~/"]` with `"allowRead": ["~/projects"]` | `~/projects` is readable and the rest of the home directory stays blocked. The narrower allow re-opens that part of the denied region |
> | `"allowRead": ["~/"]` with `"denyRead": ["~/.env"]` | `~/.env` stays blocked and the rest of the home directory is readable. The deny holds inside a wider allow, so a broad allow can't silently re-expose a secret |
> | `"allowRead": ["~/"]` with `"denyRead": ["~/**/.env"]` | Every `.env` under the home directory stays blocked and the rest is readable. A wildcard deny holds inside a wider allow the same way an exact path does |"

**Status: OBSERVED-DOC** — same page, "### Protect credentials" (the runtime README
states the same rule from the other direction)

The runtime README is more explicit about precedence, and it is worth quoting
because it is the engine's contract:

> "**Read** (deny-then-allow pattern): By default, read access is allowed everywhere.
> You can deny broad regions (e.g. `/Users`) and then re-allow specific paths
> (e.g. `.`). `allowRead` takes precedence over `denyRead` — the opposite of write,
> where `denyWrite` takes precedence over `allowWrite`. A `denyRead` entry that is
> more specific than the `allowRead` region it falls inside (e.g. `denyRead:
> ["**/.env"]` or `["./secrets"]` with `allowRead: ["."]`) still stays denied.
> * **Write** (allow-only pattern): By default, write access is denied everywhere.
> You must explicitly allow paths (e.g. `.`, `/tmp`). An empty allow list means no
> write access."

**Reimplementation need:** this is a precise, implementable rule set. Read: widest
allow wins, but a deny that is *more specific* than the containing allow still
holds. Write: only an explicit allow grants write; deny always wins. The
"more specific" test is the hard part and needs a defined specificity metric
(nesting depth, then path-component count, then exact-match-beats-glob).

### F-8. Sandbox path syntax differs from permission-rule path syntax

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "##
Configure sandboxing"

> "Sandbox filesystem paths use standard conventions: `/tmp/build` is absolute and
> `~/.kube` is relative to your home directory. This differs from Read and Edit
> permission rules, which use `//path` for absolute and `/path` for project-relative."

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/settings-reference.md,
"#### Sandbox path prefixes"

> "| Prefix | Meaning | Example |
> | `/` | Absolute path from filesystem root | `/tmp/build` stays `/tmp/build` |
> | `~/` | Relative to home directory | `~/.kube` becomes `$HOME/.kube` |
> | `./` or no prefix | Relative to the project root for project settings, or to `~/.claude` for user settings | `./output` in `.claude/settings.json` resolves to `<project-root>/output` |"

> "The `//path` prefix for absolute paths also works. If you use single-slash
> `/path` expecting project-relative resolution, switch to `./path`."

> "Braces match as ordinary characters in a name, so `~/data/{keys,tokens}` covers
> a directory literally named `{keys,tokens}`, not two alternatives."

**Reimplementation need:** the no-prefix case is *scope-dependent* — `.` means the
project root in project settings but `~/.claude` in user settings. A reimplementation
that resolves relative paths against the process CWD will be wrong for user-scope
settings.

### F-9. Protected paths: the agent's own control plane is unconditionally write-denied

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "###
Protected paths"

> "Inside the directories that sandboxed commands can write to, the sandbox still
> denies writes to the files Claude Code loads configuration and code from. A
> command that could edit those files could grant itself permissions, or add a hook
> or MCP server that Claude Code runs outside the sandbox."

> "It covers four groups of paths:
> * **In your working directory and the directories above it**: the `.claude` settings
>   files, the `.claude/skills`, `.claude/agents`, `.claude/commands`, and
>   `.claude/hooks` directories, `.mcp.json`, and the files Claude Code runs on its
>   own, such as `.claude/workflows` and `.claude/scheduled_tasks.json`
> * **In your working directory only**: shell startup files such as `.bashrc` and
>   `.zshrc`, `.gitconfig`, the `.vscode` and `.idea` directories, and `hooks` and
>   `config` inside `.git`
> * **Files that would turn your working directory into a bare git repository**:
>   `HEAD`, `objects`, and `refs` at the top level, plus existing `config` and
>   `hooks` entries there when a `HEAD` sits beside them.
> * **In `~/.claude`, or the directory `CLAUDE_CONFIG_DIR` points to**: most of its
>   contents, plus `~/.claude.json` and the `.credentials.json` credential store"

> "There is no way to exempt one of these paths: an `allowWrite` entry or an `Edit`
> allow rule that covers the path doesn't lift the protection. The only way to turn
> the protection off is `filesystem.disabled`."

> "If a symlink appears at a protected settings file's path during the session, the
> sandbox also denies writes to the file it points to, starting with the next
> command."

**Reimplementation need:** the symlink-following rule is called out explicitly and
is a real bypass vector (a symlink planted at `.claude/settings.json` pointing at
`~/.claude.json`). The doc also notes the macOS-specific extension:

> "On macOS, when a denied path passes through a symlink, such as a `~/.claude` that
> is a link into a dotfiles repository, the sandbox also denies the path's real
> location."

Note the difference from the *permission* system's protected-path list
(https://code.claude.com/docs/en/permission-modes.md, "## Protected paths"), which is
a superset including `.husky`, `.cargo`, `.devcontainer`, `.yarn`, `.mvn`,
`.npmrc`, `.bash_profile`, `.zshrc`, `.profile`, `.envrc`, `lefthook.yml`,
`gradle-wrapper.properties`, `.devcontainer.json`, `.ripgreprc`, `pyrightconfig.json`,
and so on. The two lists are **not** the same, and the doc is explicit that they are
different mechanisms:

> "The permission system has its own protected paths, which control what Claude Code
> approves before a tool runs; the sandbox's list applies to a command that is
> already running."

### F-10. Network isolation is a proxy, and the proxy is the enforcement point

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "###
Network isolation"

> "A sandboxed command has no direct route to the network:
> * **Linux and WSL2**: the command runs in a separate network namespace that has no
>   connection to your network
> * **macOS**: the Seatbelt sandbox framework by default blocks connections other
>   than the one to the sandbox proxy"

> "Claude Code runs the sandbox proxy on your machine, outside the sandbox, and
> directs commands to it with `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and related
> environment variables. The proxy checks the hostname of each connection against
> your allowed and denied domains."

> "* **Tools that read the proxy variables**: `curl`, `npm`, `git` over HTTPS, and
>   similar tools connect once their host is allowed. An `allowedDomains` entry with
>   no port allows every port on that host
> * **Tools that ignore the proxy variables**: plain `ssh`, most database drivers, and
>   similar tools can't connect, even to an allowed host.
> * **Anything that isn't TCP**: UDP, HTTP/3 over QUIC, and ICMP tools such as `ping`
>   can't leave the sandbox"

**Status: OBSERVED-DOC** — same page, "## What the sandbox restricts", for the
default posture:

> "Network | No direct route out. Connections go through a proxy on your machine
> that checks each host against your allowed domains, which start empty."

**Reimplementation need:** the `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` mechanism is
the single most portable piece of the design. A reimplementation on any OS can get
80% of the network isolation by (a) removing direct egress by whatever means
available, and (b) running a filtering HTTP/HTTPS + SOCKS proxy and exporting the
standard proxy environment variables. The runtime README confirms the SOCKS half:
"Both HTTP/HTTPS (via HTTP proxy) and other TCP traffic (via SOCKS5 proxy) are
mediated by these proxies."

### F-11. The proxy resolves hostnames and refuses local-address resolutions

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "####
Hostnames that resolve to local addresses"

> "After a hostname passes the allowlist, the sandbox proxy resolves it and refuses
> the connection when the name resolves only to local addresses. Local addresses
> include loopback addresses such as `127.0.0.1`, link-local addresses such as the
> `169.254.169.254` cloud metadata endpoint, and addresses assigned to your own
> machine. The names `localhost` and `*.localhost` are allowed to resolve to
> loopback."

> "An allowed intranet hostname that resolves to a private range such as
> `10.0.0.0/8` connects. To let a name resolve to a refused address, add that IP
> address to `allowedDomains`, such as `"127.0.0.1:8080"`."

> "The check applies to hostnames. Your allowed domains and permission mode decide a
> connection to an IP address. The proxy also skips the check for connections it
> sends through an upstream corporate proxy, because that proxy resolves the name."

**Status: OBSERVED-DOC** — the runtime README documents the full denied set:

> "The denied set is: loopback (`127.0.0.0/8`, `::1`), unspecified (`0.0.0.0/8`,
> `::`), link-local (`169.254.0.0/16`, `fe80::/10`), multicast (`224.0.0.0/4`,
> `ff00::/8`), broadcast, the cloud instance-metadata / platform endpoints that
> live outside link-local (`100.100.100.200`, `168.63.129.16`, `192.0.0.192`,
> `fd00:ec2::/32`, `fd20:ce::254`, `fd00:c1::a9fe:a9fe`, `fd00:42::42`), every
> address currently assigned to one of this host's own network interfaces..."

> "The check is not evaluated for connections routed through `parentProxy` ... or
> `mitmProxy` — that hop resolves the name and owns its own address policy"

**Reimplementation need:** this is DNS-rebinding / SSRF defence, and it is the
difference between a toy allowlist and a real one. The rule to implement: match
by name, resolve once, filter the *answers*, dial the surviving address (no second
lookup), and refuse when nothing survives. The cloud-metadata address list
(`169.254.169.254`, `100.100.100.200`, `168.63.129.16`, `192.0.0.192`) is worth
hard-coding.

### F-12. Permission mode decides what happens to a host outside the allowlist

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "####
Hosts outside your allowed domains"

> "When a sandboxed command connects to a host that isn't in your allowed domains,
> the command stays in the sandbox and waits for a decision. In an interactive
> terminal session, the decision depends on your permission mode:"

> "| Permission mode | What happens to the connection |
> | `bypassPermissions` mode, and plan mode with bypass permissions available | Allowed without a prompt |
> | Manual mode, `acceptEdits` mode, and plan mode otherwise | You get a prompt |
> | Auto mode | Refused unless the command listed the host and the classifier approved the list |
> | `dontAsk` mode | Refused |"

> "With `strictAllowlist` or `allowManagedDomainsOnly` on, the built-in sandbox
> proxy refuses the connection in every permission mode. ... A connection to a host
> in `deniedDomains` is refused in every permission mode too."

**Status: OBSERVED-DOC** — same page, "### Network isolation", for how approvals
persist:

> "**Approval choices**: if you choose Yes when prompted, Claude Code allows the
> host for the rest of the current session. If you choose "Yes, and don't ask
> again", Claude Code saves a `WebFetch(domain:...)` allow rule to your local
> settings, so the host stays allowed in future sessions. While the sandbox is
> admin-required, Claude Code saves the rule to your user settings, where it applies
> in every project."

**Reimplementation need:** the persistence mechanism is elegant and worth copying:
approving a *network* host writes a **permission rule** (`WebFetch(domain:...)`),
not a sandbox setting. One rule shape then governs both the in-process WebFetch
tool and the sandboxed Bash egress, so the two cannot drift. A reimplementation
that keeps separate "sandbox allowed domains" and "tool allowed domains" lists
will produce inconsistent behaviour.

### F-13. `sandbox.failIfUnavailable` makes the product refuse to start — directly observed

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "## Get
started", warning block

> "By default, if the sandbox can't start because a dependency is missing or the
> platform is unsupported, Claude Code runs commands without sandboxing. To make
> Claude Code exit at startup instead, set `sandbox.failIfUnavailable` to `true`.
> Managed deployments that require sandboxing as a security gate can use this
> setting."

**Status: OBSERVED** — directly observed on this host, 2026-10-21, Claude Code
2.1.306 native win32-x64. Command:

```
claude --settings '{"sandbox": {"enabled": true, "failIfUnavailable": true}}' -p "reply with OK only"
```

Actual output (captured in
`agent-reference-shots/area5-sandboxing/observed-sandbox-failifunavailable.txt`):

```
Error: sandbox required but unavailable: sandbox is enabled but the Windows sandbox is not active on this session (feature gate off)
  sandbox.failIfUnavailable is set — refusing to start without a working sandbox.
```

**Status: OBSERVED** — the same command without `failIfUnavailable`:

```
⚠ Sandbox disabled: sandbox is enabled but the Windows sandbox is not active on this session (feature gate off)
  Commands will run WITHOUT sandboxing. Network and filesystem restrictions will NOT be enforced.
```

**Status: INFERRED** — the "feature gate off" wording indicates the Windows
sandbox backend exists in the embedded runtime but is not enabled in this build
configuration, consistent with the runtime's documented
`windows-sandbox-utils.ts` and the doc's statement that the sandbox runs on macOS,
Linux, and WSL2. Reasoning: the error distinguishes "not supported on this
platform" (the doc's claim) from "not active in this session (feature gate off)"
(a build/config flag), and the runtime ships Windows code. The two-stage behaviour
— fail loudly with `failIfUnavailable`, warn and continue without it — is exactly
what the doc prescribes.

**Reimplementation need:** the **fail-open default with a loud warning** is
observable and correct to reproduce, but a security product should default to
fail-closed for any deployment where the sandbox is a control. The reference
product's own managed-settings guidance is:

> "```json
> { "sandbox": { "enabled": true, "failIfUnavailable": true, "allowUnsandboxedCommands": false } }
> ```"

### F-14. Two sandbox modes; auto-allow substitutes the boundary for the prompt

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Sandbox
modes"

> "Claude Code offers two sandbox modes. In both, the sandbox enforces the same
> filesystem and network restrictions; the difference is only in whether sandboxed
> commands are auto-approved or require explicit permission."

> "#### Auto-allow mode
> Claude Code approves a command automatically, with no prompt, when the command runs
> inside the sandbox."

> "#### Regular permissions mode
> All Bash commands go through the regular permission flow, even when sandboxed.
> This provides more control but requires more approvals."

**Status: OBSERVED-DOC** — same page, "#### Auto-allow mode", the exceptions list

> "Even in auto-allow mode, the following still apply:
> * A command in a form that a `Bash` deny rule matches is still blocked
> * `rm` or `rmdir` commands recognized as targeting a critical path still go
>   through the regular permission flow
> * Content-scoped ask rules like `Bash(git push *)` still force a prompt even for
>   sandboxed commands
> * A bare `Bash` ask rule, or the equivalent `Bash(*)` form, is skipped for
>   commands that run sandboxed; it still applies to commands that run outside the
>   sandbox. In plan mode, the rule isn't skipped: it prompts for sandboxed
>   commands too, including read-only ones
> * Monitor tool commands aren't approved automatically, though they still run in
>   the sandbox. To skip the prompt, add an allow rule that matches the command,
>   such as `Bash(npm run *)`"

**Status: OBSERVED-DOC** — same page, note under auto-allow mode

> "Auto-allow mode works independently of your permission mode setting, with three
> exceptions: plan mode, an auto mode command that carries per-command allowed
> domains, and server-side classifier review of sandboxed commands in auto mode.
> Even if you're not in "accept edits" mode, sandboxed Bash commands run
> automatically when auto-allow is enabled. This means Bash commands that modify
> files within the sandbox boundaries execute without prompting, even in Manual
> mode, where the file edit tools would prompt."

**Status: OBSERVED-DOC** — the setting that implements this, from
https://code.claude.com/docs/en/settings-reference.md, "### `sandbox.autoAllowBashIfSandboxed`"

> "**Default**: `true`"

**Reimplementation need:** the interaction table is the most intricate part of the
feature and a reimplementation must reproduce it as a matrix. Note the asymmetry:
a *bare* `Bash` ask rule is skipped for sandboxed commands, but a *content-scoped*
ask rule (`Bash(git push *)`) is not. That is a deliberate design: a content-scoped
ask rule expresses intent about a specific dangerous command, while a bare ask rule
expresses "ask me about shell in general", which the sandbox already answers
structurally.

### F-15. The unsandboxed retry is a first-class, separately-governed escape hatch

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "#### The
unsandboxed retry escape hatch"

> "The unsandboxed retry is an escape hatch for commands that fail inside the
> sandbox, such as tools that are incompatible with it. When the sandbox blocks a
> network connection, Claude Code names the denied host in the command's result, so
> Claude sees what was blocked. Claude analyzes the failure and may retry the
> command with the `dangerouslyDisableSandbox` parameter."

> "The retried command runs unsandboxed. In an interactive terminal session, who
> approves it depends on your permission mode:
> * **`bypassPermissions` mode**: the retry runs without a prompt
> * **Manual mode and `acceptEdits` mode**: you get a prompt titled "Bash command (unsandboxed)"
> * **Auto mode**: a separate classifier model evaluates the underlying command
> * **`dontAsk` mode**: Claude Code denies the retry"

> "* **A matching allow rule**: if an allow rule such as `Bash(curl *)` matches the
>   command, it also approves the retry, so the command runs outside the sandbox
>   with no prompt
> * **An ask rule for the parameter**: add an ask rule for
>   `Bash(dangerouslyDisableSandbox:true)` to be prompted on Bash retries. You get
>   the prompt in auto mode and `bypassPermissions` mode too, and the rule takes
>   precedence over a matching allow rule"

**Status: OBSERVED-DOC** — same page, "#### Turn off the retry with strict sandbox
mode"

> "You can disable the unsandboxed retry by setting `"allowUnsandboxedCommands":
> false` in your sandbox settings. With the retry disabled, Claude Code ignores the
> `dangerouslyDisableSandbox` parameter. While the sandbox is running, commands
> Claude runs are then sandboxed unless they match an `excludedCommands` entry."

> "The `/sandbox` **Overrides** tab shows this setting as **Strict sandbox mode**."

**Status: OBSERVED-DOC** — the runtime supports the per-command list by proxy
username, from the sandbox-runtime README:

> "**Per-command network allow lists (`registerCommandNetworkLists`).** One
> invocation can carry an allow list of its own, in addition to the configured one,
> for as long as it runs"

> "The proxy learns which connection belongs to an allow list from the proxy
> username, and the username is presented by the client inside the sandbox. The id
> is therefore the **only** thing binding a connection to an allow list. It **must**
> be unguessable: at least 128 bits of randomness"

> "The order of evaluation for a connection is: 1. a `network.deniedDomains` match
> denies; 2. a `network.allowedDomains` match allows; 3. `network.strictAllowlist`
> denies; 4. a match in the list registered for the id the connection presents
> allows; 5. the ask callback decides if there is one, and otherwise the connection
> is denied."

**Reimplementation need:** the retry design is a good pattern to copy in
substance: a failure inside the sandbox produces a *named* diagnostic (the denied
host), the model may request an escalation, the escalation is separately
permissioned, and the escalation can be disabled organization-wide. The
"denied host is named in the result" detail is what makes model-driven escalation
possible at all.

### F-16. `excludedCommands` has a strict matching grammar, and the doc is candid about the risk

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Run
commands outside the sandbox with `excludedCommands`"

> "Claude Code checks your entries against each Bash and Monitor call. A call is the
> whole command line Claude sends, which can chain several commands. The following
> rules decide whether a call leaves the sandbox:
> * **End the pattern with ` *`**: entries use the same syntax as a `Bash(...)`
>   permission rule, where a pattern with no wildcard is an exact match. `docker`
>   matches only `docker` with no arguments. `docker *` matches `docker` with or
>   without arguments
> * **Every command in the call has to match**: `npm ci && docker compose build`
>   stays sandboxed unless another entry covers `npm ci`
> * **Claude Code matches the text of the call**: a script or `make` target that
>   calls `docker` internally doesn't match, and neither does `/usr/local/bin/docker`
> * **Some calls stay sandboxed**: a redirect to a file, a `cd`, or a command
>   substitution such as `$(...)` keeps the whole call sandboxed."

**Status: OBSERVED-DOC** — the warning:

> "An excluded command runs with your full access. A broad entry such as `docker *`
> covers everything that tool can do. If you write a pattern that covers an
> interpreter, a script inside your working directory, or a tool that acts on a
> file there, as `docker compose` does with its compose file, Claude can write that
> file and then run it outside the sandbox."

**Status: OBSERVED-DOC** — the settings reference adds a longer list of shapes that
stay sandboxed (https://code.claude.com/docs/en/settings-reference.md, "### `sandbox.excludedCommands`"):

> "* A command starting with `sudo`, `eval`, or `xargs`
> * A `cd`, `pushd`, or `popd`, wherever it appears in the call
> * A command substitution, a subshell, or a control-flow block such as `if` or `for`
> * A redirection, such as `docker build . > build.log`, other than one that only
>   duplicates a file descriptor, as `2>&1` does
> * A command name that comes from a variable
> * A `git clone`, `git init`, `git worktree add`, `git worktree move`, or `git
>   bundle create` with a path argument that is absolute, starts with `~`, or
>   contains a `..` segment"

**Reimplementation need:** the *default-deny* posture of this list is the correct
and safe design: a compound call is excluded only when every part matches and the
call has no ambiguous shell construct. A reimplementation that matches
substrings or prefixes will be materially less safe.

### F-17. Credentials: `deny` blocks, `mask` substitutes on egress, and masking requires TLS termination

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Protect
credentials"

> "The `sandbox.credentials` setting declares credential files and environment
> variables to protect from sandboxed commands. Each entry names a file path or an
> environment variable and a `mode`."

> "For entries with `"mode": "deny"`, file paths are denied for reads inside the
> sandbox, the same restriction that `filesystem.denyRead` applies, and environment
> variables are unset before each sandboxed command runs."

> "There is no built-in credential deny list, so only the files and variables you
> list are restricted."

**Status: OBSERVED-DOC** — same page, "### Mask credentials"

> "When you mask a credential, Claude Code shows sandboxed commands a per-session
> placeholder called the sentinel, and the sandbox proxy substitutes the real value
> on outbound requests to hosts you allow. A `deny` entry under Protect credentials
> blocks the credential instead."

> "Masking requires the following:
> * **TLS termination**: the proxy substitutes the real value inside request
>   contents, so it has to see them. Set `network.tlsTerminate` so the proxy
>   terminates TLS itself. Without it, masking fails without exposing anything: the
>   command still sees only the sentinel, but the sentinel reaches the server
>   unchanged and authentication fails. To check for this misconfiguration, run
>   `claude doctor` in your terminal and look for the `TLS termination is
>   unavailable` warning.
> * **An allowed destination**: each `mask` entry can list `injectHosts`, the hosts
>   the real value is allowed to reach.
> * **A trusted settings scope**: masking authorizes the proxy to send your real
>   credential somewhere, so Claude Code honors `mask` entries, `network.tlsTerminate`,
>   `credentials.allowPlaintextInject`, `awsPairs`, and `sigv4` only from user
>   settings, managed settings, and the `--settings` flag."

**Status: OBSERVED-DOC** — same page, "### Mask credential files", the platform
difference:

> "* **Linux and WSL2**: sandboxed commands read a sentinel copy of the file, and
>   the proxy substitutes the real value on outbound requests.
> * **macOS**: sandboxed commands can't read the file at all. Claude Code builds no
>   sentinel copy, so tools that authenticate with the file don't work inside the
>   sandbox, the same effect as `deny`."

**Status: OBSERVED-DOC** — the AWS re-signing case, same page, "#### Re-sign AWS
requests"

> "AWS requests carry SigV4 signatures over the request contents, so mask
> `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` together. The proxy detects a
> SigV4 request by the access key's sentinel and re-signs the request with the real
> values."

**Status: OBSERVED-DOC** — the exact settings-reference field names
(https://code.claude.com/docs/en/settings-reference.md, "#### Mask fields for files"
and "#### Mask fields for environment variables"):

> "| `extract` | string, a regular expression with at least one capturing group | Mask only the text captured by group 1 of each match, so the rest of the file stays parseable. With `decode` also set, Claude Code checks each capture as a possible JWT instead of replacing it outright. |
> | `onExtractNoMatch` | `"warn"`, `"deny"`, or `"error"`; default `"warn"` | What happens when `extract` or `decode` finds nothing to mask. `warn` leaves the file readable as-is inside the sandbox, `deny` makes it unreadable, and `error` stops sandbox setup until you fix the configuration. |
> | `decode` | the string `"jwt"` | Find JSON Web Tokens (JWTs) in the file, with a built-in pattern or with `extract` when set, verify each candidate, and replace it with a structurally valid fake token, so code inside the sandbox that decodes the token keeps working. |
> | `maskClaims` | array of strings, at least one claim name; requires `decode` | Mask only the named top-level payload claims inside each verified JWT and rebuild the token around the modified payload, so the other claims stay readable. |
> | `maskDuplicates` | Boolean, default `false` | Also replace verbatim copies of each masked value elsewhere in the file, such as a secret pasted into a comment. |
> | `injectHosts` | array of strings, each a host that `sandbox.network.allowedDomains` also admits | Narrow the hosts where the sandbox proxy substitutes the real value. When unset, the proxy substitutes it on requests to every host in `sandbox.network.allowedDomains`. |"

**Reimplementation need:** the `mask` mechanism is the most advanced part of the
feature and the most expensive to reproduce correctly (TLS termination, a
session CA, sentinel generation, structured JWT re-issuance, SigV4 re-signing,
and a proxy that injects into request bodies). It is also the part most likely to
be dropped in a first implementation. The `extract` + `decode` + `maskClaims`
vocabulary is a good model for a "structured secret" masking API generally.

### F-18. The sandbox is not a permission mode, and the doc says so explicitly

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Permission
modes"

> "`/sandbox` is not a permission mode. Permission modes decide whether a tool call
> runs and whether you are prompted first, while the sandbox restricts what a Bash
> command can access once it runs. They differ in what they control and what
> replaces the per-action prompt:"

> "| | What it controls | What replaces the prompt |
> | `/sandbox` | What a Bash command can access once it runs | The sandbox boundary itself, in auto-allow mode |
> | Auto mode | Whether each tool call runs | A classifier that reviews actions |
> | `--dangerously-skip-permissions` | Whether each tool call runs | Nothing. Protected path checks are also skipped; the actions no mode auto-approves still apply |"

> "The sandbox's auto-allow mode is separate from auto mode: auto-allow approves
> Bash commands because the sandbox boundary contains them, while auto mode uses a
> classifier to review actions. The two work independently and can be combined."

**Status: OBSERVED-DOC** — same page, "### Permission rules", for the layering:

> "* **Permission rules** control which tools Claude Code can use and are evaluated
>   before any tool runs. They apply to every tool: Bash, Read, Edit, WebFetch, MCP,
>   and others, except that a deny or ask rule can't block `EndConversation` while
>   any other tool remains.
> * **Sandboxing** provides OS-level enforcement that restricts what shell commands
>   can access at the filesystem and network level. It applies to Bash, PowerShell,
>   and Monitor tool commands and their child processes."

> "The two layers also differ in how they are enforced. Claude Code evaluates
> permission decisions before a command runs, based on the command string and, in
> auto mode, a separate classifier's judgment about whether the command is safe.
> The operating system enforces the sandbox boundary on the running process, so it
> holds regardless of what the model chose to run and even if an allowed command
> does more than its name suggests."

**Status: OBSERVED-DOC** — same page, "### Permission rules", the merge table
showing that the two layers' rules combine into one sandbox configuration:

> "| `sandbox.filesystem.allowWrite` | Grants subprocess write access to paths outside the working directory |
> | `sandbox.filesystem.denyWrite` and `sandbox.filesystem.denyRead` | Block subprocess access to specific paths |
> | `sandbox.filesystem.allowRead` | Re-allows reading specific paths within a `denyRead` region |
> | `Edit` allow rules | Grant write access to specific paths, the same way `sandbox.filesystem.allowWrite` does |
> | `Read` and `Edit` deny rules | Block access to specific files or directories |
> | `WebFetch(domain:...)` allow and deny rules | Control domain access |
> | Sandbox `allowedDomains` | Controls which domains Bash commands can reach |
> | Sandbox `deniedDomains` | Blocks specific domains even when a broader `allowedDomains` wildcard would otherwise permit them |"

> "Paths and domains from both sandbox settings and permission rules are merged into
> the final sandbox configuration."

**Reimplementation need:** the merge is the crux. Permission rules and sandbox
settings are **not** two separate systems that both apply — permission rules are
*translated into* sandbox rules. `Edit` allow rules become `allowWrite` entries;
`Read` deny rules become `denyRead` entries; `WebFetch(domain:...)` rules become
network allow/deny entries. A reimplementation that keeps them separate will
produce the security bug the product is explicitly guarding against: the agent
writes a file via the Edit tool that Bash could then read, or a domain is allowed
for WebFetch but not for Bash.

### F-19. Scope of the boundary: subagents, background sessions, computer use, mods

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Scope"

> "* **Computer use**: when Claude opens apps and controls your screen, it runs on
>   your actual desktop rather than in an isolated environment. Per-app permission
>   prompts gate each application.
> * **Subagents**: subagents run in the same process as the parent session and use
>   the same sandbox configuration. Bash commands inside a subagent are sandboxed
>   when sandboxing is enabled in the parent session.
> * **Background sessions**: a background session runs in its own process, and its
>   Bash commands are sandboxed when its settings enable sandboxing.
> * **Mods**: a mod is a plugin that runs its own code inside Claude Code, and a
>   process that a mod starts runs outside the sandbox."

**Reimplementation need:** the "same process, same configuration" rule for
subagents is a process-topology requirement: a reimplementation that runs
subagents as separate processes with separate settings would break the guarantee.

### F-20. The product documents its own security limitations candidly

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Security
limitations"

> "* **Network filtering**: the sandbox restricts which domains processes can
>   connect to. By default the built-in proxy does not terminate or inspect TLS on
>   outbound traffic, so the contents of encrypted connections are not examined. ...
>   You are responsible for ensuring that only trusted domains are allowed in your
>   policy."

> "Allowing broad domains such as `github.com` can create paths for data
> exfiltration. Because the proxy makes its allow decision from the client-supplied
> hostname without inspecting TLS, code running inside the sandbox can potentially
> use domain fronting or similar techniques to reach hosts outside the allowlist."

> "* **Privilege escalation via Unix sockets**: the `allowUnixSockets` configuration
>   can inadvertently grant access to system services that could lead to sandbox
>   bypasses. For example, allowing access to `/var/run/docker.sock` effectively
>   grants access to the host system through the Docker socket."

> "* **Filesystem permission escalation**: overly broad filesystem write permissions
>   can enable privilege escalation attacks. Allowing writes to directories
>   containing executables in `$PATH`, system configuration directories, or user
>   shell configuration files such as `.bashrc` or `.zshrc` can lead to code
>   execution in different security contexts when other users or system processes
>   access these files."

> "* **Linux sandbox strength**: the Linux implementation provides strong filesystem
>   and network isolation but includes an `enableWeakerNestedSandbox` mode that
>   enables it to work inside Docker environments without privileged namespaces.
>   This option considerably weakens security."

And the overall warning, from "### Scope":

> "Effective sandboxing requires both filesystem and network isolation. Without
> network isolation, a compromised agent could exfiltrate sensitive files like SSH
> keys. Without filesystem isolation, whether from a permissive policy or from
> disabling the filesystem layer, a compromised agent could backdoor system
>   resources to gain network access."

**Reimplementation need:** a reimplementation should reproduce the *warning
surface*, not just the mechanism. `claude doctor` is the diagnostic channel the
product uses for sandbox misconfiguration (TLS termination unavailable, ambiguous
IPv6 entries, unreliably spelled domain entries, stale mask files). A
reimplementation that silently misconfigures is worse than one that refuses.

### F-21. Administrative control: managed settings, admin-required mode, and the scope algebra

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Keep
developers from widening the policy"

> "When managed settings set a Boolean key such as `enabled` or `failIfUnavailable`,
> Claude Code uses the managed value and ignores anything a developer sets locally.
> For array keys such as `allowRead`, Claude Code merges entries from the scopes the
> session loads, so a developer can append entries that widen the policy unless a
> lock covers that key."

> "Set `allowManagedReadPathsOnly` to `true` in managed settings so that only
> `allowRead` entries from managed settings are honored."

> "When managed settings configure `sandbox.filesystem` or list any
> `sandbox.credentials.files` entry with `"mode": "deny"`, only managed settings can
> set `filesystem.disabled`, so developers can't switch off administrator-deployed
> filesystem restrictions."

**Status: OBSERVED-DOC** — same page, "### Repository settings under an
admin-required sandbox"

> "The sandbox is admin-required while one of these settings is in effect:
> * `allowUnsandboxedCommands` set to `false` in managed settings, or with the
>   `--settings` flag unless managed settings set it to `true`
> * `allowManagedDomainsOnly` set to `true` in managed settings"

And the table of what a repository may no longer do while admin-required, including:

> "| `excludedCommands`, `ignoreViolations`, `network.allowedDomains`,
> `network.allowUnixSockets`, `network.allowMachLookup`, `network.httpProxyPort`,
> `network.socksProxyPort` | Every entry |"

**Status: OBSERVED-DOC** — the "weaker sandbox" toggles, same page, "### Keep
developers from widening the policy"

> "* `enableWeakerNestedSandbox`
> * `enableWeakerNetworkIsolation`
> * `network.allowAllUnixSockets`
> * `network.allowLocalBinding`
> * `allowAppleEvents`, which a repository can't turn on"

**Reimplementation need:** the scope algebra is Booleans-vs-arrays plus explicit
locks. Booleans: managed value wins outright. Arrays: merged across scopes, so
they can only be *widened* by a developer unless a lock applies. Locks are
per-key. A reimplementation must implement the lock table exactly, because it is
the difference between "a repo can loosen the sandbox" and "a repo cannot".

### F-22. A custom proxy can replace the built-in one — and the built-in controls then stop applying

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "### Custom
proxy configuration"

> "To direct sandboxed commands to your proxy, set the localhost ports it listens on
> in sandbox settings:"

> "```json
> { "sandbox": { "network": { "httpProxyPort": 8080, "socksProxyPort": 8081 } } }
> ```"

> "If you set a port and also set `HTTPS_PROXY` or `HTTP_PROXY`, Claude Code
> doesn't forward what sandboxed commands send to your proxy on to the proxy those
> variables name. To reach a corporate proxy, configure your own proxy to forward
> to it."

> "Once either port applies, your proxy is responsible for filtering everything
> sent to it. Claude Code's own network controls, such as `allowedDomains`,
> `deniedDomains`, `strictAllowlist`, approval prompts, and the local-address
> check, stop applying to that traffic. A sandboxed command can connect to either
> proxy, so if you set only one port, Claude Code's domain lists on the other proxy
> don't limit what the command reaches through yours."

**Reimplementation need:** this is a footgun the product documents rather than
prevents. A reimplementation could do better (e.g. keep the resolved-address check
in force even with a custom proxy), but behavioural parity means reproducing the
warning.

### F-23. Diagnostics: `claude doctor` is the misconfiguration channel

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "##
Troubleshooting"

> "To find ambiguous entries, run `claude doctor` in your terminal and look for the
> `Sandbox network domain entries have unreliable spellings` warning."

> "To check for this misconfiguration, run `claude doctor` in your terminal and look
> for the `TLS termination is unavailable` warning."

> "Run `claude doctor` in your terminal to list the leftover placeholder files. The
> `Stale sandbox mask files left by a killed session` warning names some of them
> and counts the rest."

**Status: OBSERVED** — `claude doctor` on this host reports no sandbox diagnostics,
because the sandbox is not active on native Windows. The observed output is
captured in `agent-reference-shots/area5-sandboxing/observed-sandbox-failifunavailable.txt`
context and in the existing `agent-reference-shots/area5-bash-permissions/claude-doctor.txt`.
The doctor output does confirm the host's constraints, which matter for this area:

> "Managed settings (remote): not fetched — not available with a custom `ANTHROPIC_BASE_URL`
> Organization policy: not fetched with a custom `ANTHROPIC_BASE_URL`"

**Reimplementation need:** a `doctor`-equivalent with sandbox-specific checks
(TLS termination availability, ambiguous IPv6 entries, stale mask placeholders,
missing `bubblewrap`/`socat`/seccomp dependencies, unused `injectHosts` that can
never match) is a small, high-value surface.

### F-23b. The `/sandbox` panel is an interactive TUI that could not be driven headlessly

**Status: OBSERVED** — three attempts on this host, 2026-10-21, all non-mutating:

1. `claude -p "/sandbox"` — hung and was terminated at the 120 s timeout with no
   output. The panel is a local-render control, so a non-interactive print-mode
   invocation has nothing to drive it.
2. `claude attach <id>` with `/sandbox` piped to stdin — the attach reproduced the
   full TUI (banner, prompt, spinner) but the piped keystrokes did not register as
   a slash command; the panel never opened.
3. The TUI is rendered locally rather than by the model — the same pattern already
   recorded in `agent-reference-shots/PROTOCOL-NOTES.md` for
   `terminal_slash_commands: ["doctor","color","focus","reload-plugins"]`.

**Status: OBSERVED-DOC** — the panel's structure, from
https://code.claude.com/docs/en/sandboxing.md, "## Get started"

> "This opens the sandbox panel with three tabs, plus a Dependencies tab on Linux
> when the optional seccomp filter is missing:
> * **Mode**: choose how sandboxed commands are approved, covered in the next step
> * **Overrides**: choose whether commands that fail under the sandbox can fall back
> to running unsandboxed. This is the `allowUnsandboxedCommands` setting
> * **Config**: view the resolved sandbox settings"

and

> "If the panel shows only a Dependencies tab, a required package is missing. Install
> it as described in Set up Linux and WSL2, restart Claude Code, and run `/sandbox`
> again."

and, from "### Protected paths"

> "To see most of these paths resolved for your machine, run `/sandbox` and open the
> **Config** tab, which lists them under **Denied within allowed**, mixed in with
> your own `denyWrite` entries."

**Reimplementation need:** the panel is a **local render**, not a model call, and it
is the product's only surface that shows the *resolved* policy. A reimplementation
should provide the same: a local view of the effective config and the protected
path set, since that is what a user needs when a command unexpectedly fails. Note
also the persistence rule — "When you select a mode in the panel, Claude Code saves
it to your project's local settings at `.claude/settings.local.json`" — and the
error path when that write fails:

> "✗ Sandbox settings not changed: /home/you/project/.claude/settings.local.json couldn't be updated (EACCES). Start Claude Code in a project folder you can write to."

### F-24. Known non-obvious behaviours a reimplementation must decide on

**Status: OBSERVED-DOC** — https://code.claude.com/docs/en/sandboxing.md, "####
Temporary directories"

> "Unless you disable filesystem isolation, Claude Code sets `$TMPDIR` to this
> directory for sandboxed commands, so tools that write temporary files work without
> extra configuration."

> "Unsandboxed commands inherit your shell's `$TMPDIR` when it is set, so while
> filesystem isolation is on, sandboxed and unsandboxed commands resolve `$TMPDIR` to
> different directories."

**Status: OBSERVED-DOC** — same page, "### Confirm commands run inside the sandbox"

> "| Command | Result inside the sandbox |
> | `touch ~/sandbox-probe` | Fails with `Operation not permitted` on macOS, or `Read-only file system` on Linux and WSL2 |
> | `curl --noproxy '*' https://example.com` | Fails with `Could not resolve host`, because the command has no route around the sandbox proxy |"

**Status: OBSERVED-DOC** — the Linux placeholder mechanism, same page, "### 0-byte
read-only files appear at `.claude` settings paths"

> "On Linux and WSL2, the sandbox holds a write denial on a file that doesn't exist
> yet by creating a 0-byte read-only placeholder there while a sandboxed command
> runs. The sandbox removes the placeholder afterward. If a session is killed before
> that cleanup runs, for example by SIGKILL, the placeholders stay behind."

**Status: OBSERVED-DOC** — the `!` prompt behaviour, same page, "### Turn off the
retry with strict sandbox mode"

> "Strict sandbox mode applies to the commands Claude runs. Commands you type
> yourself at the `!` shell-mode prompt run outside the sandbox unless the session
> is one of these:
> * **A background session**: strict sandbox mode covers shell-mode commands too
> * **A Linux session with `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` set**: every command
>   runs sandboxed, shell-mode commands included"

**Status: OBSERVED-DOC** — the `excludedCommands` verify recipe, same page, "### Run
commands outside the sandbox with `excludedCommands`"

> "To confirm an entry matches, switch to Manual mode and ask Claude to run a
> matching command that changes something, such as `docker compose up -d`. The
> permission prompt is titled "Bash command (unsandboxed)"."

**Reimplementation need:** the last two items together are a coherent testing
protocol a reimplementation should adopt: a **prompt-title convention** that makes
sandbox state legible in the UI ("Bash command (unsandboxed)" vs. a normal Bash
prompt), and a **two-command verification** (`touch ~/sandbox-probe` must fail;
`curl --noproxy '*' https://example.com` must fail to resolve).

---

## 5b.3 Capability table

| Capability | Status | Evidence | Needed to reimplement? |
| :- | :- | :- | :- |
| OS-enforced boundary over Bash/PowerShell/Monitor + descendants | OBSERVED-DOC | F-1 | Yes — core |
| Sandbox covers shell tools only; Read/Edit/Write/WebFetch/WebSearch, MCP, hooks, LSP, status line outside | OBSERVED-DOC | F-2 | Yes — define the holes |
| macOS Seatbelt / Linux bubblewrap / WSL2 bubblewrap; native Windows unsandboxed | OBSERVED-DOC | F-3, F-13 | Yes — platform matrix |
| Underlying engine published as `@anthropic-ai/sandbox-runtime`, Apache-2.0 | OBSERVED-DOC | F-5 | Yes — use or reimplement |
| Off by default; enable via `/sandbox` or `sandbox.enabled` | OBSERVED-DOC | F-4 | Yes |
| Default access model (wide-open reads, cwd+tmp writes, empty net allowlist, inherited env) | OBSERVED-DOC | F-4 | Yes |
| Filesystem and network layers independently switchable | OBSERVED-DOC | F-6 | Yes |
| Read precedence: wider allow wins unless a narrower deny holds | OBSERVED-DOC | F-7 | Yes |
| Write precedence: explicit allow required; deny always wins | OBSERVED-DOC | F-7 | Yes |
| Sandbox path prefixes `/`, `~/`, `./`; differs from permission-rule syntax | OBSERVED-DOC | F-8 | Yes — easy to get wrong |
| Protected paths: `.claude/**`, `.mcp.json`, `~/.claude.json`, `.credentials.json`, shell rc files, bare-repo `HEAD`/`objects`/`refs` | OBSERVED-DOC | F-9 | Yes — core |
| Protected paths cannot be exempted by `allowWrite` or an `Edit` allow rule | OBSERVED-DOC | F-9 | Yes |
| Symlink at a protected settings path extends the denial to the target | OBSERVED-DOC | F-9 | Yes — bypass vector |
| No direct network route; egress via `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` to a host proxy | OBSERVED-DOC | F-10 | Yes — core |
| Non-TCP (UDP, QUIC, ICMP) cannot leave the sandbox | OBSERVED-DOC | F-10 | Yes |
| Proxy resolves allowed hostnames once and refuses local-address resolutions; metadata endpoints denied | OBSERVED-DOC | F-11 | Yes — SSRF defence |
| Permission mode decides the outcome for a host outside the allowlist | OBSERVED-DOC | F-12 | Yes |
| Approving a host persists as a `WebFetch(domain:...)` permission rule | OBSERVED-DOC | F-12 | Yes — keeps one rule set in sync |
| `strictAllowlist` / `allowManagedDomainsOnly` deny in every permission mode | OBSERVED-DOC | F-12 | Yes |
| Two sandbox modes: auto-allow and regular permissions | OBSERVED-DOC | F-14 | Yes |
| `sandbox.autoAllowBashIfSandboxed` defaults to `true` | OBSERVED-DOC | F-14 | Yes |
| Auto-allow still honours deny rules, critical-path `rm`, content-scoped ask rules; bare `Bash` ask rule skipped | OBSERVED-DOC | F-14 | Yes — the tricky matrix |
| Unsandboxed retry via `dangerouslyDisableSandbox`, separately permissioned, per-mode | OBSERVED-DOC | F-15 | Yes |
| Ask rule `Bash(dangerouslyDisableSandbox:true)` forces a prompt, outranking an allow rule | OBSERVED-DOC | F-15 | Yes |
| Strict sandbox mode = `allowUnsandboxedCommands: false`; the parameter is ignored | OBSERVED-DOC | F-15 | Yes |
| Per-command allowed domains reviewed by a classifier; scoped to one command | OBSERVED-DOC | F-15 | Yes — needs a reviewer |
| `excludedCommands` requires every command in the call to match; ambiguous shapes stay sandboxed | OBSERVED-DOC | F-16 | Yes — default-deny matching |
| Credential `deny` mode: file read block + env unset | OBSERVED-DOC | F-17 | Yes |
| Credential `mask` mode: sentinel in-sandbox, real value injected by proxy on egress | OBSERVED-DOC | F-17 | Yes — advanced |
| Masking requires `network.tlsTerminate` and `injectHosts` | OBSERVED-DOC | F-17 | Yes |
| Mask file fields: `extract`, `decode:"jwt"`, `maskClaims`, `maskDuplicates`, `onExtractNoMatch`, `injectHosts` | OBSERVED-DOC | F-17 | Yes |
| SigV4 re-signing of masked AWS credentials | OBSERVED-DOC | F-17 | Optional |
| Sandbox is not a permission mode; the boundary replaces the prompt in auto-allow | OBSERVED-DOC | F-18 | Yes — the core idea |
| Permission rules are merged into the sandbox config (`Edit`→`allowWrite`, `Read` deny→`denyRead`, `WebFetch(domain:)`→network lists) | OBSERVED-DOC | F-18 | Yes — core |
| Subagents share the parent's process and sandbox config; background sessions have their own | OBSERVED-DOC | F-19 | Yes |
| Managed-settings scope algebra: Booleans overridden, arrays merged, per-key locks | OBSERVED-DOC | F-21 | Yes — the lock table |
| Admin-required mode ignores repository `excludedCommands`, `allowedDomains`, `allowWrite`, etc. | OBSERVED-DOC | F-21 | Yes |
| Custom proxy ports replace the built-in proxy and disable the built-in network controls | OBSERVED-DOC | F-22 | Yes |
| `claude doctor` reports sandbox misconfiguration (TLS, IPv6 spelling, stale placeholders) | OBSERVED-DOC | F-23 | Yes — high value |
| `failIfUnavailable` refuses startup when the sandbox cannot run | **OBSERVED** (this host) + OBSERVED-DOC | F-13 | Yes |
| Fail-open with a loud warning when the sandbox cannot run | **OBSERVED** (this host) + OBSERVED-DOC | F-13 | Yes |
| Linux 0-byte read-only placeholders for not-yet-existing denied paths | OBSERVED-DOC | F-24 | Platform-specific |
| `$TMPDIR` redirected to a per-user temp dir for sandboxed commands | OBSERVED-DOC | F-24 | Yes |
| Domain-fronting weakness of a non-TLS-inspecting proxy | OBSERVED-DOC | F-20 | Document it |
| The macOS/Linux enforcement paths themselves | UNKNOWN | — | Not observable on this host |

---

## 5b.4 Dependencies

### Required for the sandbox to function at all

| Dependency | Platform | Why | Source |
| :- | :- | :- | :- |
| `bubblewrap` (`bwrap`) | Linux, WSL2 | Filesystem isolation + network namespace | F-3 |
| `socat` | Linux, WSL2 | Relay traffic to the sandbox proxy | F-3 |
| macOS Seatbelt (`sandbox-exec`) | macOS | Built in; no install | F-3 |
| Ripgrep | all | Bundled with the native binary; used for file search inside the sandbox | F-3 |
| seccomp filter (optional) | Linux, WSL2 | Unix-domain-socket blocking | F-3 |
| `@anthropic-ai/sandbox-runtime` | all | The engine; installable with `npm install -g @anthropic-ai/sandbox-runtime` | F-3, F-5 |
| A local HTTP/HTTPS proxy + SOCKS5 proxy | all | The network enforcement point; the runtime starts them | F-10, F-5 |
| Node.js / a Node runtime | all | The runtime is published as an npm package | F-5 |

### Required only for specific sub-features

| Dependency | Needed for | Source |
| :- | :- | :- |
| `network.tlsTerminate` (ephemeral CA or `caCertPath`/`caKeyPath`) | Credential `mask` mode | F-17 |
| `sandbox.credentials.allowPlaintextInject` | `mask` over plain HTTP on trusted test networks | F-17 |
| `network.allowMachLookup` | macOS XPC tools (iOS Simulator, Playwright) | settings-reference |
| `network.allowAllUnixSockets` | Unix sockets on Linux/WSL2 (where the seccomp filter blocks them) | settings-reference |
| `network.allowLocalBinding` | macOS: listening on ports / reaching localhost | F-24 |
| `allowAppleEvents` | macOS: `open`, `osascript`, browser auth flows | settings-reference |
| `enableWeakerNestedSandbox` | Running inside an unprivileged Docker container | F-20 |
| `enableWeakerNetworkIsolation` | `gh`/`gcloud`/`terraform` behind a MITM proxy on macOS | settings-reference |
| `sandbox.bwrapPath`, `sandbox.socatPath`, `sandbox.ripgrep` | Air-gapped hosts with vendored binaries | settings-reference |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` | Stripping credentials from **all** subprocesses, not just sandboxed Bash | F-4, settings-reference |
| `CLAUDE_CODE_TMPDIR` | Overriding the temp directory | F-24 |
| `CLAUDE_CONFIG_DIR` | Relocating `~/.claude`; changes which paths are protected | F-9 |
| `permissions.blockReadsOutsideWorkingDirectories` | Denying reads of home dirs and mounted volumes while keeping working dirs readable | F-7 |

### External services and account dependencies

- **None for the sandbox itself.** The sandbox is a local OS facility. It does not
  require network access, an Anthropic account, or a model provider to be *present*.
- **The auto-mode classifier is a separate service.** Per-command host lists and
  auto-mode decisions "are evaluated by a separate classifier model" (F-14, F-15);
  that review is a network call and, on paid API tiers, consumes tokens.
- **Managed settings and organization policy** are delivered via MDM or
  server-managed settings, and the latter require a claude.ai organization. On this
  host they are explicitly unavailable: "Managed settings (remote): not fetched —
  not available with a custom `ANTHROPIC_BASE_URL`" (F-23).
- **`WebFetch(domain:...)` allow rules** are shared between the permission system
  and the sandbox allowlist (F-12, F-18), so the permission system must be
  implemented for the sandbox's network approval flow to work as designed.

---

## 5b.5 Limitations of this investigation

1. **The sandbox does not run on this host.** Native Windows, feature gate off.
   Every macOS/Linux enforcement behaviour in this report is `OBSERVED-DOC`, quoted
   from the page, not observed. The two behaviours I *could* observe — the
   fail-open warning and the fail-closed refusal — are recorded as `OBSERVED`.
2. **`/sandbox` is an interactive TUI panel** and could not be driven from a
   non-interactive `-p` invocation (the command hung and was terminated), nor from
   a background session with the keystrokes piped to stdin (F-23b). The panel's tab
   structure — Mode, Overrides, Config, plus Dependencies on Linux — is
   `OBSERVED-DOC` from the "Get started" section. Its contents on this host would
   have been the most informative single artifact, and getting it requires a real
   TTY.
3. **No decompilation, no source-map extraction, no binary modification** was
   performed, per Anthropic's ToS and the product's own statement that "The Claude
   Code binary must not be modified." The runtime's internals were read only from
   its **published Apache-2.0 README**, which is a legitimate public source and,
   notably, is *more* permissive than the clean-room requirement demands.
4. **The classifier was not exercised.** Auto mode and per-command host review
   require a server-side classifier; this host uses a custom `ANTHROPIC_BASE_URL`
   and `claude doctor` reports that organization policy is unavailable.
5. **Credentials were not exercised.** `mask` mode, SigV4 re-signing, and TLS
   termination were not run, to avoid touching real secrets and to avoid
   generating a session CA against a live endpoint. The behaviour is `OBSERVED-DOC`.
6. **Version-gated behaviour was read, not tested.** The page cites minimum
   versions for ~20 features (v2.1.186 through v2.1.285). This host runs 2.1.306,
   so all of them are nominally available, but only the Windows-unavailable ones
   could be exercised.

---

## 5b.6 Unresolved questions

1. **What exactly is the Windows "feature gate"?** The runtime ships
   `windows-sandbox-utils.ts` and a documented WFP egress fence, but the product
   disables it. Is the gate a server-side flag, a build flag, or an account-tier
   flag? A reimplementation targeting Windows needs this answered.
2. **How is the resolved-address check kept correct under DNS rebinding?** The doc
   says the proxy "resolves it once" and dials the surviving address. Is the
   resolution cached per connection or per lookup, and what is the TTL policy?
3. **What is the exact violation-report format the model sees?** The runtime
   mentions a `<sandbox_violations>` block and a generic `user denied` reason, but
   the Claude Code page does not show the rendered text. A reimplementation needs
   the format to be model-legible.
4. **How does `ignoreViolations` interact with the runtime's `commandText`
   parameter?** The runtime says `ignoreViolations` patterns match against
   `commandText` (the logical command) while the wrapped string is what actually
   executes. A reimplementation must carry both.
5. **What are the semantics of `sandbox.credentials.allowPlaintextInject` beyond
   "plain HTTP on trusted test networks"?** The settings reference names it but the
   sandboxing page gives only one sentence.
6. **How are the sandbox's own protected paths kept in sync with the permission
   system's protected paths?** The two lists differ (F-9 vs. the permission-modes
   page). Is there a single source of truth with two projections, or two lists?
7. **Does the Windows path (when enabled) implement the resolved-address check,
   the mask/sentinel mechanism, and the SIGV4 re-signing?** The runtime README
   documents the WFP egress fence and ACE-based write restrictions, but not
   whether the full credential feature set is implemented there.
8. **What is the exact proxy-username mechanism** that binds a connection to a
   per-command allow list? The runtime says the id travels in the proxy username
   and must be ≥128 bits of randomness. The precise format is undocumented.
9. **How are `sandbox.filesystem.allowWrite` entries and `Edit(...)` allow rules
   deduplicated** when both grant the same path? The doc says they are merged; it
   does not say whether the merge is a set union with normalisation.
10. **What is the interaction between `permissions.blockReadsOutsideWorkingDirectories`
    and the sandbox's protected paths** when both are on, and with the worktree
    carve-out? The settings reference describes a re-open list; the sandboxing page
    does not cross-reference it.

---

## 5b.7 Clean-room implementation recommendations for Area 5b

**Legal basis for the clean-room position.** The enforcement engine Anthropic uses
is published as `@anthropic-ai/sandbox-runtime` under the **Apache License 2.0**
(github.com/anthropics/sandbox-runtime, 5,621 stars, updated 2026-10-21).
Apache-2.0 permits use, modification, and redistribution with attribution and a
NOTICE file. An independent implementation therefore has two lawful routes, and
the second is the more interesting one:

- **Route A — depend on the package.** Wrap commands with
  `SandboxManager.wrapWithSandbox`, supply a `SandboxRuntimeConfig`, and implement
  the entire policy layer yourself. This is the fastest path to a *correct*
  boundary, and the boundary is the hard part.
- **Route B — reimplement the engine.** Write your own Seatbelt-profile generator,
  bubblewrap argv builder, and filtering proxy, matching the documented observable
  contract. Legal under Apache-2.0 (which is why the reference is published), and
  it is the only route if the target platform is one the package does not cover
  well (e.g. Windows before the gate opens).

**What must be independently written either way — the policy layer.** The runtime
supplies a mechanism and a config shape; it supplies none of the following, and
all of it is the product's actual contribution:

### Tier 1 — the contract you cannot afford to get wrong

1. **The sandbox/permission split.** Two named mechanisms with different jobs:
   *sandbox* = "what may this command reach, once it runs" (OS-enforced);
   *permission mode* = "does this tool call run, and do I get asked" (harness
   decision). The sandbox boundary is the **prompt substitute** in auto-allow mode.
   Implement it as: *if* the command is wrapped in the sandbox *and* the mode is
   auto-allow *and* no deny rule matches *and* the command is not a critical-path
   removal *and* no content-scoped ask rule matches → run without prompting.
   The bare-`Bash`-ask-rule skip and the content-scoped-ask-rule non-skip are
   both required and easy to confuse.
2. **The rule merge.** Permission rules must be *translated into* sandbox rules
   before the sandbox is configured, not evaluated alongside it: `Edit` allow →
   `allowWrite`; `Edit` deny → `denyWrite`; `Read` deny → `denyRead`;
   `WebFetch(domain:…)` allow/deny → network allow/deny. One rule vocabulary, one
   enforcement point, no drift between "what the agent may write" and "what a
   command may write."
3. **The protected-path list and its "no exemption" rule.** A hard-coded deny set
   that `allowWrite` and `Edit` allow rules cannot lift, that follows symlinks, and
   that covers `.claude/**`, `.mcp.json`, `~/.claude.json`, `.credentials.json`,
   `~/.claude/`, shell rc files, `.gitconfig`, `.vscode`/`.idea`, and bare-repo
   `HEAD`/`objects`/`refs`/`config`/`hooks`. It is the difference between "the
   agent's shell is confined" and "the agent can rewrite its own leash".
4. **Network egress through a proxy, with no direct route.** Set `HTTP_PROXY`,
   `HTTPS_PROXY`, `ALL_PROXY` (and `NO_PROXY` for loopback) for sandboxed commands;
   remove direct egress by the platform's own means; enforce hostname
   allow/deny lists in the proxy, including wildcard and `:port` forms and
   bracketed IPv6.
5. **The resolved-address check.** Resolve once, filter the answers against
   loopback / link-local / metadata / own-interface / multicast / broadcast sets,
   dial the survivor, refuse if none survives. Skip only for upstream-corporate-proxy
   traffic. This is the single most commonly missed element of a naive allowlist.

### Tier 2 — the parts that are easy to defer but visible when missing

6. **Credential `deny` mode** — file read block plus environment-variable unset
   before each command. Cheap, high value, and a prerequisite for `mask`.
7. **The unsandboxed retry path** — a named diagnostic on failure (the denied
   host), an explicit model-requested escalation, a separate approval decision,
   an ask rule that can force a prompt (`Bash(dangerouslyDisableSandbox:true)`)
   outranking an allow rule, and a global switch to disable the escalation
   entirely ("strict sandbox mode"). Idiomatically: represent escalation as a
   distinct, separately-permissioned tool parameter, not as a silent fallback.
8. **`excludedCommands` matching with a default-deny grammar** — every command in
   a compound call must match; `cd`/`pushd`/`popd`, redirects, command
   substitutions, subshells, control-flow blocks, `sudo`/`eval`/`xargs` prefixes,
   variable-derived command names, and absolute/`~`/`..`-bearing `git clone`
   destinations all keep the call sandboxed. This is a parser problem, and a
   conservative parser that refuses to exclude is correct.
9. **Path resolution and precedence** — sandbox prefixes (`/`, `~/`, `./`, with
   `.` meaning project-root in project scope and `~/.claude` in user scope) versus
   permission-rule prefixes (`//` absolute, `/` project-relative). Read
   precedence: widest allow wins, but a more-specific deny inside it holds. Write
   precedence: explicit allow required, deny always wins. Trailing slashes and
   trailing `/**` are stripped; braces are literal, not alternatives.
10. **A `doctor`-equivalent for the sandbox.** Checks for: TLS termination
    unavailable (masking will silently fail); ambiguous IPv6 entries; domain
    entries that can never match their destination; `injectHosts` outside the
    allowlist; missing `bubblewrap`/`socat`/seccomp; stale mask placeholders from
    a killed session; an `excludeCommands` pattern that silently never matches.

### Tier 3 — advanced, deferrable

11. **Credential `mask` mode** — session sentinel, proxy-side injection,
    `network.tlsTerminate` (ephemeral CA or `caCertPath`/`caKeyPath`),
    `injectHosts` scoping, `extract` regex with a capturing group, `decode:"jwt"`
    with structurally valid fake tokens, `maskClaims`, `maskDuplicates`,
    `onExtractNoMatch` ∈ {`warn`,`deny`,`error`}. If deferred, ship `deny` mode
    and say so.
12. **SigV4 re-signing** and `credentials.awsPairs` for custom-named AWS
    variables; `credentials.sigv4` to pass through streaming/presigned/SigV4A
    requests.
13. **Per-command allowed-domain lists** with a classifier review, scoped to a
    single command, bound to the invocation by an unguessable id carried in the
    proxy username, and evaluated *after* `deniedDomains` and
    `strictAllowlist`.
14. **The administrative scope algebra** — Booleans overridden by managed
    settings, arrays merged across scopes, and the per-key lock table
    (`allowManagedDomainsOnly`, `allowManagedReadPathsOnly`, the
    `filesystem.disabled` lock, the `credentials.files` deny lock) that makes a
    checked-out repository unable to loosen the policy. For a multi-tenant or
    enterprise product this tier is not optional; for a single-developer tool it
    is.

### Observable contract to aim for

A user of a reimplementation should be able to observe all of the following,
because the reference product exposes them:

- `/sandbox` (or an equivalent) opens a panel with **Mode**, **Overrides**, and
  **Config** tabs; the Config tab lists the resolved settings and the protected
  paths under "Denied within allowed".
- An unsandboxed command's approval prompt is **titled differently** from a normal
  Bash prompt — the reference uses "Bash command (unsandboxed)". A user can tell
  from the prompt whether the command is inside or outside the boundary.
- The two-command verification works: `touch ~/sandbox-probe` fails with
  "Operation not permitted" or "Read-only file system", and
  `curl --noproxy '*' https://example.com` fails with "Could not resolve host".
- When the sandbox cannot start, the product says so **loudly and specifically**,
  naming the reason, and either refuses to start (fail-closed) or continues with
  an explicit warning that restrictions are not enforced (fail-open).
- A denied network connection names the **host** in the tool result, so the model
  can decide whether to escalate.

### Idiomatic ways to build it

- **Sandbox mechanism:** `bubblewrap` on Linux (unprivileged user namespaces —
  mind the Ubuntu 24.04+ AppArmor `userns` restriction, and provide a
  weaker-nested mode for unprivileged containers), `sandbox-exec` with a generated
  Seatbelt profile on macOS, and on Windows either the Apache-2.0 package's
  dedicated low-privilege account + WFP egress fence, or defer and refuse to start
  when `failIfUnavailable` is set.
- **Network enforcement:** a local HTTP CONNECT + plain-HTTP proxy and a SOCKS5
  proxy, both binding loopback, advertised through the standard `*_PROXY`
  environment variables, with an optional TLS-terminating front end (an ephemeral
  CA per session) for credential masking. Use a per-invocation unguessable id in
  the proxy username to bind per-command allow lists.
- **Policy representation:** a small, typed, serialisable config object with
  explicit layers (`filesystem`, `network`, `credentials`) and a scope resolver
  that produces the effective config plus a record of *which* scope won each
  Boolean and *which* lock excluded each array entry. Keeping the resolver's
  output explainable (a "why is this allowed / why is this denied" trace) is
  what makes a `doctor` implementation cheap.
- **Command analysis:** a shell parser that decomposes a command line into its
  constituent commands, flags the constructs that make static matching unsafe
  (substitution, redirection, `cd`, control flow, variable-derived names), and
  returns "cannot decide" for anything it does not fully understand. A
  conservative "cannot decide" is the safe default.
- **Violation reporting:** a per-invocation attribution key (not the command
  string alone — long commands sharing a prefix would cross-attribute) plus a
  structured violation record per denial: the rule that fired, the path or host
  involved, and a short, model-legible reason. Surface these in the tool result
  so the model can reason about the denial rather than guessing.

---

## 5b.8 Evidence artifacts

| Path | Contents |
| :- | :- |
| `agent-reference-shots/area5-sandboxing/doc-sandboxing.md` | The assigned page, verbatim, 95,397 bytes. Fetched 2026-10-21 from `https://code.claude.com/docs/en/sandboxing.md`. |
| `agent-reference-shots/area5-sandboxing/sandbox-runtime-README.md` | The Apache-2.0 `@anthropic-ai/sandbox-runtime` README, 156,873 bytes, from `https://raw.githubusercontent.com/anthropics/sandbox-runtime/main/README.md`. Public upstream source, not decompiled. |
| `agent-reference-shots/area5-sandboxing/observed-sandbox-failifunavailable.txt` | Directly observed CLI output: `sandbox.enabled` + `failIfUnavailable: true` → startup refusal with the exact reason; and `sandbox.enabled` alone → fail-open warning, both on native Windows 2.1.306. |
| `agent-reference-shots/area5-sandboxing/observed-sandbox-panel-not-drivable.txt` | Directly observed: the `/sandbox` panel is a **local TUI render**, not drivable from `-p` mode or from piped stdin. Records all three attempts and the cleanup. |
| `agent-reference-shots/cli-help/claude-help-sandboxing-capture.txt` | `claude --help` output, showing `--settings`, `--setting-sources`, `--add-dir`, and the absence of a dedicated `--sandbox` flag (sandbox is configured through settings, not the command line). |

**Supporting public documentation also fetched for this area** (all 2026-10-21):

| URL | Bytes | Used for |
| :- | :- | :- |
| `https://code.claude.com/docs/en/sandboxing.md` | 95,397 | The assigned page (F-1 … F-24) |
| `https://code.claude.com/docs/en/settings-reference.md` | 404,714 | Exact key names, types, defaults, scopes, and minimum versions |
| `https://code.claude.com/docs/en/permission-modes.md` | — | Protected paths, critical paths, per-mode protected-path table |
| `https://code.claude.com/docs/en/permissions.md` | — | Read-only command set, Bash rule limits, `WebFetch(domain:…)` semantics |
| `https://code.claude.com/docs/en/env-vars.md` | — | `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`, `CLAUDE_CODE_TMPDIR` |
| `https://code.claude.com/docs/en/commands.md` | — | `/sandbox` slash-command entry |
| `https://code.claude.com/docs/en/cli-reference.md` | — | Confirmation of no dedicated sandbox CLI flag |
| `https://github.com/anthropics/sandbox-runtime` (+ raw README) | 156,873 | The Apache-2.0 engine, its API, and its config schema |

**Untrusted-content handling:** every page above was treated as data. No directive,
instruction, or command found in any fetched page was acted on. The only commands
executed against the product were its published read-only surfaces (`--help`,
`doctor`, `--settings` with a sandbox config in `-p` mode). No files were created
or modified by the probes, no credentials were read, and no secrets appear in any
artifact.

**Secret hygiene note.** The host's `~/.claude/settings.json` contains an
`ANTHROPIC_AUTH_TOKEN` and an `ANTHROPIC_BASE_URL`. Neither was copied into any
artifact, and neither is reproduced in this report. The referenced file was read
only to establish which environment the observations were made under.

---

*End of Area 5b. Overall findings for all areas: `agent-evidence.md` (this file). Shared protocol and terms notes: `agent-reference-shots/PROTOCOL-NOTES.md`, `agent-reference-shots/TERMS-NOTES.md`.*

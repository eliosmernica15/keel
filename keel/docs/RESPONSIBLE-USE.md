# Keel Responsible Use and Safety Notice

> Generated from `keel.responsible_use` by `render_document()`. Edit the module, not this file.

Keel is a coding harness that can take actions on your computer. Read this before your first agent run. If you do not accept these terms, do not run the agent.

## What Keel can do

### What Keel can do to your host

Keel executes model-generated code and commands. It can also load third-party plugins and access your network, processes, credentials and files. Defects, misconfiguration, malicious input or untrusted plugins can damage the host, destroy data or leak secrets. Treat each agent run as you would treat running an untrusted program.

### Sandboxing reduces risk; it does not guarantee isolation

Sandboxing, approvals and permissions reduce risk but do not guarantee isolation. Do not rely on them as the sole control for untrusted workloads.

This is the first-run safety notice (W1.10) in plain language. It is not a promise about the behaviour of any particular model, plugin or workload.

## Before your first agent run

Work through this checklist before you let an agent change anything:

1. **Use least privilege** - Give the agent the minimum permissions, file scope, network access and token rights it needs. Prefer read-only, one-time approvals and ordinary user accounts; avoid administrator/root accounts and standing 'always allow' rules.
2. **Run in a disposable VM or container** - Run unfamiliar projects, plugins and untrusted workloads in a disposable VM or container that you can throw away afterwards, not on a machine holding your real accounts and data.
3. **Keep backups** - Keep current, restorable backups of everything the agent can write. Confirm a backup exists before the first agent run so a mistake or a bad command can be undone.
4. **Do not expose sensitive credentials** - Do not expose production keys, tokens, passwords, SSH keys or cloud credentials in the workspace, environment, prompt, logs, screenshots or recordings. Use narrow, short-lived, test-only credentials instead.
5. **Review plugins, configuration and proposed commands** - Review third-party plugins, configuration changes and every proposed command before approving it. The model can be wrong or can be acting on hostile input it read from a file or the web.

If the setup wizard is available it also offers:
- **Run in disposable container** (source: V17).
- **Create backup before first agent run** (source: D5.3).

## Warranty and liability

No warranty; limitation of liability

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT.

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE AUTHORS AND DISTRIBUTORS ARE NOT LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL OR PUNITIVE DAMAGES, OR FOR LOSS OF DATA, PROFITS OR CREDENTIALS, OR FOR HOST DAMAGE ARISING FROM USE OF THE SOFTWARE, INCLUDING MODEL-GENERATED CODE, PLUGINS OR AGENT ACTIONS.

This software is licensed, not sold, under the license agreement (EULA) supplied with your distribution (package metadata: license = Proprietary). The EULA controls; this summary does not change it.

Draft for legal review (G5) - not legal advice.

## Known limits

The sandbox reduces the blast radius of agent actions; it does not make arbitrary code harmless.

Sandboxing, approvals and permissions reduce risk but do not guarantee isolation. Do not rely on them as the sole control for untrusted workloads.

The same limits appear on the in-app known-limits page (W7.19). Permissions are a risk control, not a safety guarantee.

## How we handle host sandbox failures

When a required command fails in our own development sandbox, the builder may retry the exact same command with the narrowest possible dev-sandbox exception for the blocked resource, and only with evidence of that cause. Test failures and the product sandbox are never bypassed. These are the builder stop rules:

- A dev-sandbox failure is real only with evidence naming the blocked credential, network or IPC resource; suspicion is not evidence.
- Retry the exact same command unchanged; changing arguments makes it a new command, not a retry.
- Use only the narrowest escalation for the specific blocked resource; never widen it and never turn it off.
- Never bypass, skip or weaken a failing test to make a command pass.
- Never disable or bypass the product sandbox; builder escalation is only for the developer's dev sandbox.
- Fail closed on any unknown, mixed or unproven cause: stop and report rather than silently downgrading the sandbox.

## Source references

| Section | Plan row |
| --- | --- |
| What Keel can do | D5.1 |
| Sandboxing reduces risk | D5.2 |
| Checklist and wizard offers | D5.3 (V17) |
| Warranty and liability | D5.4 (G5) |
| Host sandbox failures | D5.5 (X10.4) |

"use client";

// Tools and Commands. There is no tool catalogue route in this bridge, so the
// Tools tab says so and only lists tool names actually observed in live bot
// rows plus the client's real slash-command list. Commands uses the real
// bridge catalogue and real guarded execution.

import React, { useMemo, useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, SectionTitle, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage, SLASH_COMMANDS } from "@/lib/api";
import type { Bot, BotRow } from "@/lib/types";
import s from "./capabilities.module.css";
import { asArray, PanelState, readRecord, safeResult, useBridgeData } from "./capabilitiesShared";

interface ObservedTool { name: string; count: number }
interface CommandRow {
  name?: string;
  description?: string;
  source?: string;
  argument_hint?: string;
  usage?: string;
  [key: string]: unknown;
}
interface ExecResult { ok: boolean; text: string; name: string }

export function ToolsPanel() {
  const observedQ = useBridgeData(async () => {
    const bots = asArray<Bot>(await bridge.listBots(), "bots").slice(0, 5);
    const rows = await Promise.allSettled(bots.map((bot) => bridge.botRows(bot.id)));
    const counts = new Map<string, number>();
    for (const result of rows) {
      if (result.status !== "fulfilled") continue;
      for (const row of asArray<BotRow>(result.value, "rows")) {
        const body = readRecord(row.body);
        const kind = row.kind ?? row.type;
        const candidate = typeof body.tool_name === "string" ? body.tool_name
          : typeof body.tool === "string" ? body.tool
          : typeof body.name === "string" && (kind === "step" || kind === "tool") ? body.name
          : undefined;
        if (candidate) counts.set(candidate, (counts.get(candidate) ?? 0) + 1);
      }
    }
    return Array.from(counts, ([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
  });

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Tools</h2>
          <p className={s.muted}>Keel's tool availability and permission class are decided by the Python runtime for each run.</p>
        </div>
      </div>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="info" size={16} /> No tool catalogue endpoint in this bridge build</div>
        <p>There is no route that lists tool schemas or availability here, so this page does not render a fabricated catalogue. Tool calls appear in each session's work log when the runtime actually uses them.</p>
      </Card>

      <SectionTitle action={<Button size="sm" variant="ghost" onClick={observedQ.reload}>Refresh activity</Button>}>
        Tool names seen in recent session activity
      </SectionTitle>
      <PanelState query={observedQ}>
        {(tools: ObservedTool[]) => tools.length === 0 ? (
          <EmptyState icon={<Icon name="terminal" />} title="No tool calls in recent rows"
            description="Nothing to list. Tool names appear here only when a real session row reports one." />
        ) : (
          <ul className={s.chipList}>
            {tools.map((tool) => (
              <li key={tool.name} className={s.toolChip}>
                <code className={s.code}>{tool.name}</code>
                <span className={s.muted}>{tool.count} observed row{tool.count === 1 ? "" : "s"}</span>
              </li>
            ))}
          </ul>
        )}
      </PanelState>

      <SectionTitle>Command catalogue in this client</SectionTitle>
      <p className={s.muted}>These slash commands are defined in this frontend client (not invented here). The full bridge-backed command catalogue is on the Commands tab.</p>
      <ul className={s.chipList}>
        {SLASH_COMMANDS.map((cmd) => (
          <li key={cmd.name} className={s.toolChip}><code className={s.code}>{cmd.usage ?? `/${cmd.name}`}</code><span className={s.muted}>{cmd.description}</span></li>
        ))}
      </ul>
      <p className={s.footerNote}>Permission classes and schemas are enforced at execution time by the bridge; this view never claims a tool is available without a real observation.</p>
    </div>
  );
}

export function CommandsPanel() {
  const commandsQ = useBridgeData(() => bridge.commands());
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState<CommandRow | null>(null);
  const [args, setArgs] = useState("");
  const [projectRoot, setProjectRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExecResult | null>(null);

  const all = useMemo<CommandRow[]>(() => {
    const backend = asArray<CommandRow>(commandsQ.data, "commands");
    const names = new Set(backend.map((c) => String(c.name ?? "").toLowerCase()));
    const client: CommandRow[] = SLASH_COMMANDS
      .filter((c) => !names.has(c.name.toLowerCase()))
      .map((c) => ({ name: c.name, description: c.description, argument_hint: c.usage, source: "fleet-next client" }));
    return [...backend, ...client];
  }, [commandsQ.data]);

  const visible = all.filter((cmd) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [cmd.name, cmd.description, cmd.source, cmd.argument_hint]
      .filter((v): v is string => typeof v === "string")
      .some((v) => v.toLowerCase().includes(q));
  });

  async function execute() {
    if (!target?.name) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const name = target.name;
      const payload: Record<string, unknown> = { name, args };
      if (projectRoot.trim()) payload.project_root = projectRoot.trim();
      const body = readRecord(await bridge.executeCommand(payload));
      if (typeof body.error === "string") {
        setError(body.error);
        return;
      }
      setResult({ ok: body.ok === true, name, text: safeResult(body.result ?? "No result body reported.") });
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Commands</h2>
          <p className={s.muted}>The real command catalogue from the bridge. Execution is a guarded backend operation; its actual result is shown below.</p>
        </div>
        <div className={s.actionRow}>
          <Button onClick={() => { setResult(null); commandsQ.reload(); }}><Icon name="refresh" size={14} /> Reload catalogue</Button>
        </div>
      </div>

      {error && <p className={s.error} role="alert">Execution failed: {error}</p>}
      {result && (
        <Card className={result.ok ? s.resultOk : s.resultFail}>
          <strong>{result.ok ? `Command ${result.name} completed` : `Command ${result.name} reported failure`}</strong>
          <pre className={s.pre}>{result.text}</pre>
        </Card>
      )}

      <PanelState query={commandsQ}>
        {() => (
          <>
            <TextField type="search" label="Search commands" placeholder="Filter by name, description or source"
              value={query} onChange={(e) => setQuery(e.target.value)} className={s.filter} />
            {visible.length === 0 ? (
              <EmptyState icon={<Icon name="command" />} title="No commands match"
                description="The bridge reported no matching command in its catalogue or the client list." />
            ) : (
              <ul className={s.list}>
                {visible.map((cmd, i) => (
                  <li className={s.row} key={String(cmd.name ?? i)}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}><code className={s.code}>/{cmd.name}</code></h3>
                        <Badge tone="neutral">{cmd.source ?? "source not reported"}</Badge>
                      </div>
                      <p className={s.rowDesc}>{cmd.description ?? "No description reported."}</p>
                      {(cmd.argument_hint ?? cmd.usage) && <p className={s.mono}>Usage: {cmd.argument_hint ?? cmd.usage}</p>}
                    </div>
                    <div className={s.rowActions}>
                      <Button size="sm" onClick={() => { setTarget(cmd); setResult(null); setError(null); }}>Run…</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </PanelState>

      <Dialog open={target !== null} onClose={() => setTarget(null)} title={`Run /${target?.name ?? ""}`}
        footer={<>
          <Button variant="ghost" onClick={() => setTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => { void execute(); }}>Run command</Button>
        </>}>
        <p className={s.muted}>The bridge executes this command under Keel's guarded tool path. Only the real response will be shown; nothing is assumed successful.</p>
        <TextField label="Arguments" value={args} onChange={(e) => setArgs(e.target.value)} placeholder={target?.argument_hint ?? ""} />
        <TextField label="Project root (optional)" value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} />
      </Dialog>
    </div>
  );
}

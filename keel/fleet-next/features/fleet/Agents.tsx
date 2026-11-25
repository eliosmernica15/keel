"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, TextField, Textarea } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, BotRow, FleetEvent, FleetTask } from "@/lib/types";
import s from "./fleet.module.css";
import { ActivityBadge, ActivityDot, Avatar, ResourceNotice, StreamNotice } from "./Bits";
import ActivityPanel from "./Activity";
import AgentDetails from "./AgentDetails";
import {
  deriveActivity, fmtDate, number, text, unwrap, wrapped,
  useBridgeResource, useNow, type Resource,
} from "./support";

export default function Agents({ botsResource, events, streamError, onRetryStream, onChanged, focusBotId }: {
  botsResource: Resource<Bot[]>;
  events: FleetEvent[];
  streamError: boolean;
  onRetryStream: () => void;
  onChanged: () => void;
  focusBotId?: string | null;
}) {
  const { notify } = useApp();
  const now = useNow(5000);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [forkBot, setForkBot] = useState<Bot | null>(null);
  const [deleteBot, setDeleteBot] = useState<Bot | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (focusBotId) setSelectedId(focusBotId); }, [focusBotId]);

  const bots = botsResource.data ?? [];
  const botKey = bots.map((b) => b.id).join(",");
  const rowsResource = useBridgeResource(
    useCallback(async () => {
      const entries = await Promise.all(bots.map(async (b) =>
        [b.id, wrapped<BotRow>(await bridge.botRows(b.id), "rows")] as const));
      return Object.fromEntries(entries) as Record<string, BotRow[]>;
    }, [botKey]), // eslint-disable-line react-hooks/exhaustive-deps
    [botKey],
  );
  const tasksResource = useBridgeResource(
    useCallback(() => bridge.tasks().then((r) => wrapped<FleetTask>(r, "tasks")), []), []);

  const taskCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const t of tasksResource.data ?? []) {
      const id = text(t.assignee) || text((t as Record<string, unknown>).assigned_bot_id);
      if (id) m[id] = (m[id] ?? 0) + 1;
    }
    return m;
  }, [tasksResource.data]);

  const filtered = bots.filter((b) => {
    const q = search.trim().toLowerCase();
    return !q || text(b.name).toLowerCase().includes(q) || text(b.role).toLowerCase().includes(q) || b.id.toLowerCase().includes(q);
  });
  const selected = bots.find((b) => b.id === selectedId) ?? filtered[0] ?? bots[0];
  const detailsBot = bots.find((b) => b.id === detailsId) ?? null;

  async function createAgent(name: string, role: string, engine: string, notes: string, hue: string) {
    setBusy(true);
    try {
      const created = unwrap<Bot>(await bridge.createBot({
        name: name.trim(), role: role.trim(), engine, notes: notes.trim(),
        ...(hue.trim() ? { avatar_hue: number(hue, 210) } : {}),
      }), "bot");
      notify(`Agent ${created.name || name.trim()} created.`, "success");
      setCreateOpen(false);
      setSelectedId(created.id);
      onChanged(); botsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function fork(target: Bot, name: string, upToSeq: string) {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {};
      if (name.trim()) payload.name = name.trim();
      if (upToSeq.trim()) payload.up_to_seq = number(upToSeq, 0);
      const created = unwrap<Bot>(await bridge.forkBot(target.id, payload), "bot");
      notify(`Forked ${target.name || target.id} into ${created.name || created.id}.`, "success");
      setForkBot(null);
      onChanged(); botsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function remove(target: Bot) {
    setBusy(true);
    try {
      await bridge.deleteBot(target.id);
      notify(`Agent ${target.name || target.id} deleted.`, "success");
      setDeleteBot(null);
      if (selectedId === target.id) setSelectedId(null);
      onChanged(); botsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className={s.stack}>
      <StreamNotice streamError={streamError} onRetry={onRetryStream} />
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Agent roster</h3>
          <p className={s.panelHint}>Names, engines and activity come from the bridge. Echo agents are labelled scripted and never shown as a live model run.</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New agent</Button>
      </div>

      <ResourceNotice resource={botsResource} emptyTitle="No agents yet" emptyDescription="Create an agent with a provider engine, or an Echo scripted test agent, to get started."
        emptyAction={<Button variant="primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New agent</Button>}>
        {() => (
          <div className={s.split}>
            <div className={s.stack}>
              <div className={s.search}>
                <Icon name="search" size={15} />
                <input aria-label="Search agents" placeholder="Search agents…" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <div className={s.grid}>
                {filtered.map((b) => {
                  const rows = rowsResource.data?.[b.id] ?? [];
                  const act = deriveActivity(rows, events.filter((e) => !e.bot_id || e.bot_id === b.id), now, text(b.engine));
                  return (
                    <div key={b.id} className={`${s.agentCard} ${selected?.id === b.id ? s.isSelected : ""}`}>
                      <button className={s.cardMain} onClick={() => setSelectedId(b.id)} aria-label={`Select ${b.name || b.id}`}>
                        <div className={s.agentTop}>
                          <Avatar bot={b} />
                          <div className={s.grow}>
                            <div className={s.agentName}>{b.name || b.id}</div>
                            <div className={s.agentRole}>{text(b.role) || "generalist"}</div>
                          </div>
                          <ActivityDot state={act.state} />
                        </div>
                        <div className={s.activityPhrase}>{act.phrase}</div>
                        <div className={s.agentMeta}>
                          <Badge tone={text(b.engine) === "echo" ? "neutral" : "accent"}>{text(b.engine) === "echo" ? "scripted (Echo)" : "provider"}</Badge>
                          <Badge tone="neutral">{text(b.provider, "auto")}</Badge>
                          {text(b.model) && <Badge tone="neutral">{text(b.model)}</Badge>}
                        </div>
                        <div className={s.line}><span className={s.lineLabel}>Tasks</span><span className={s.lineValue}>{taskCounts[b.id] ?? 0}</span></div>
                        <div className={s.line}><span className={s.lineLabel}>Last activity</span><span className={s.lineValue}>{fmtDate(b.last_activity)}</span></div>
                      </button>
                      <div className={s.actions}>
                        <Button size="sm" variant="secondary" onClick={() => setDetailsId(b.id)}><Icon name="panel" size={14} /> Details</Button>
                        <Button size="sm" variant="ghost" onClick={() => setForkBot(b)}><Icon name="copy" size={14} /> Fork</Button>
                        <Button size="sm" variant="ghost" onClick={() => setDeleteBot(b)}><Icon name="trash" size={14} /> Delete</Button>
                      </div>
                    </div>
                  );
                })}
                {filtered.length === 0 && <EmptyState title="No agents match this search" description="Clear the search field or create a new agent." />}
              </div>
              {rowsResource.error !== null && <div className={s.errorText}>Could not load some activity rows: {errMessage(rowsResource.error)}</div>}
            </div>

            <div className={s.panel}>
              {selected ? (
                <>
                  <div className={s.panelHead}>
                    <div className={s.row}>
                      <Avatar bot={selected} small />
                      <div>
                        <h3 className={s.panelTitle}>{selected.name || selected.id}</h3>
                        <p className={s.panelHint}>{text(selected.role) || "generalist"} · {text(selected.provider, "auto")} {text(selected.model) ? `· ${text(selected.model)}` : ""}</p>
                      </div>
                    </div>
                    <div className={s.row}>
                      <IconButton label="Open agent details" onClick={() => setDetailsId(selected.id)}><Icon name="panel" size={16} /></IconButton>
                      <Button size="sm" variant="secondary" onClick={botsResource.reload}><Icon name="refresh" size={14} /> Refresh</Button>
                    </div>
                  </div>
                  <ActivityPanel
                    bot={selected}
                    bots={bots}
                    events={events}
                    onOpenBot={(id) => setSelectedId(id)}
                    onChanged={() => { onChanged(); botsResource.reload(); }}
                  />
                </>
              ) : (
                <EmptyState icon={<Icon name="agents" size={26} />} title="Select an agent" description="Pick a card from the roster to see live activity, the work log and delegation links." />
              )}
            </div>
          </div>
        )}
      </ResourceNotice>

      <CreateAgentDialog open={createOpen} busy={busy} onClose={() => setCreateOpen(false)} onCreate={createAgent} />
      <ForkDialog bot={forkBot} busy={busy} onClose={() => setForkBot(null)} onFork={fork} />
      <Dialog open={!!deleteBot} onClose={() => setDeleteBot(null)} title={`Delete ${deleteBot?.name || deleteBot?.id || "agent"}?`}
        footer={<><Button variant="ghost" onClick={() => setDeleteBot(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => deleteBot && void remove(deleteBot)}>Delete agent</Button></>}>
        <p className={s.hintNote}>This removes the agent and its stored rows from the bridge. This cannot be undone from this UI.</p>
      </Dialog>
      {detailsBot && <AgentDetails bot={detailsBot} onClose={() => setDetailsId(null)} onChanged={() => { onChanged(); botsResource.reload(); }} />}
    </div>
  );
}

function CreateAgentDialog({ open, busy, onClose, onCreate }: {
  open: boolean; busy: boolean; onClose: () => void;
  onCreate: (name: string, role: string, engine: string, notes: string, hue: string) => void;
}) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [engine, setEngine] = useState("provider");
  const [notes, setNotes] = useState("");
  const [hue, setHue] = useState("");
  return (
    <Dialog open={open} onClose={onClose} title="New agent"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!name.trim()} onClick={() => onCreate(name, role, engine, notes, hue)}>Create agent</Button></>}>
      <div className={s.stack}>
        <p className={s.hintNote}>Provider agents use a configured provider at run time. Echo agents are scripted test agents and are never presented as live model runs.</p>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} required />
        <TextField label="Role" value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} placeholder="generalist" />
        <div className={s.field}><label htmlFor="new-engine">Engine</label><select id="new-engine" value={engine} onChange={(e) => setEngine(e.target.value)}><option value="provider">Provider</option><option value="echo">Echo (scripted/test)</option></select></div>
        <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4096} />
        <TextField label="Avatar hue (optional)" type="number" min={0} max={359} value={hue} onChange={(e) => setHue(e.target.value)} />
      </div>
    </Dialog>
  );
}

function ForkDialog({ bot, busy, onClose, onFork }: {
  bot: Bot | null; busy: boolean; onClose: () => void;
  onFork: (bot: Bot, name: string, upToSeq: string) => void;
}) {
  const [name, setName] = useState("");
  const [upToSeq, setUpToSeq] = useState("");
  return (
    <Dialog open={!!bot} onClose={onClose} title={`Fork ${bot?.name || bot?.id || "agent"}`}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => bot && onFork(bot, name, upToSeq)}>Fork agent</Button></>}>
      <div className={s.stack}>
        <p className={s.hintNote}>A fork copies the agent settings and replays its stored rows. Leave the sequence blank to copy all rows.</p>
        <TextField label="New name (optional)" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} />
        <TextField label="Copy rows up to seq (optional)" type="number" min={0} value={upToSeq} onChange={(e) => setUpToSeq(e.target.value)} />
      </div>
    </Dialog>
  );
}

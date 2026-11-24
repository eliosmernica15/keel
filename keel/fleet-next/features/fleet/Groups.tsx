"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, FleetEvent } from "@/lib/types";
import s from "./fleet.module.css";
import { Avatar, ResourceNotice, StreamNotice } from "./Bits";
import {
  fmtDate, number, redact, statusTone, text, unwrap,
  useBridgeResource, type FleetGroup, type GroupRow, type Resource,
} from "./support";

const ROUND_TERMINAL = new Set(["done", "failed", "denied", "busy"]);

export default function Groups({ bots, groupsResource, events, streamError, onRetryStream }: {
  bots: Bot[];
  groupsResource: Resource<FleetGroup[]>;
  events: FleetEvent[];
  streamError: boolean;
  onRetryStream: () => void;
}) {
  const { notify } = useApp();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FleetGroup | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  // A round is tracked from the real `seq` returned by the 202 response until
  // every member has a terminal member_status row after that seq. This closes
  // the gap between posting a message and the first "running" row arriving.
  const [round, setRound] = useState<{ startSeq: number; memberCount: number } | null>(null);
  const [roundConflict, setRoundConflict] = useState(false);

  const detailResource = useBridgeResource(
    useCallback(() => bridge.group(selectedId as string).then((r) => r as { group?: FleetGroup; rows?: GroupRow[] }), [selectedId]),
    [selectedId]);

  const groups = groupsResource.data ?? [];
  const selected = groups.find((g) => g.id === selectedId) ?? null;

  // Live group rows arrive as named SSE frames with `group_id`; dedupe by seq.
  const liveRows = useMemo(() => events.filter((e) => text(e.bot_id ?? (e as Record<string, unknown>).group_id) === selectedId)
    .map((e) => ({ ...(e.body ?? {}), seq: number(e.seq ?? (e as Record<string, unknown>).seq, 0), kind: text(e.kind ?? e.type), author: text(e.author), created_at: text((e as Record<string, unknown>).created_at ?? e.ts) }) as GroupRow),
    [events, selectedId]);
  const rows = useMemo(() => {
    const map = new Map<number, GroupRow>();
    for (const r of [...(detailResource.data?.rows ?? []), ...liveRows]) {
      if (typeof r.seq === "number") map.set(r.seq, r);
    }
    return [...map.values()].sort((a, b) => number(a.seq, 0) - number(b.seq, 0));
  }, [detailResource.data, liveRows]);

  const activeMembers = rows.filter((r) => text(r.kind) === "member_status" && text((r.body as Record<string, unknown> | undefined)?.status) === "running");
  const terminalCount = round
    ? rows.filter((r) => number(r.seq, 0) > round.startSeq && text(r.kind) === "member_status" &&
        ROUND_TERMINAL.has(text((r.body as Record<string, unknown> | undefined)?.status))).length
    : 0;
  const roundActive = Boolean(round && terminalCount < round.memberCount) || activeMembers.length > 0;

  useEffect(() => { setRound(null); setRoundConflict(false); setDraft(""); }, [selectedId]);

  async function createGroup(name: string, ids: string[]) {
    setBusy(true);
    try {
      const created = unwrap<FleetGroup>(await bridge.createGroup({ name: name.trim(), bot_ids: ids }), "group");
      notify(`Group “${created?.name || name.trim()}” created.`, "success");
      setCreateOpen(false);
      groupsResource.reload();
      if (created?.id) setSelectedId(created.id);
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function remove(group: FleetGroup) {
    setBusy(true);
    try {
      await bridge.deleteGroup(group.id);
      notify(`Group “${group.name || group.id}” deleted.`, "success");
      setDeleteTarget(null);
      if (selectedId === group.id) setSelectedId(null);
      groupsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function send() {
    const content = draft.trim();
    if (!content || !selectedId || busy || roundActive) return;
    setBusy(true);
    setRoundConflict(false);
    try {
      const res = await bridge.groupMessage(selectedId, content) as { queued?: boolean; seq?: number; busy?: boolean };
      if (res && res.queued === false) throw new Error("busy");
      // The 202 body really carries the user-row seq (routes.py:1331).
      setRound({ startSeq: number(res?.seq, 0), memberCount: (selected?.members ?? []).length });
      notify("Message posted; the group round is running.", "success");
      setDraft("");
      detailResource.reload();
    } catch (e) {
      const msg = errMessage(e);
      if (/409|busy/i.test(msg)) {
        setRoundConflict(true);
        notify("A group round is already active — wait for it to finish before sending again.", "warning");
        detailResource.reload();
      } else notify(msg, "error");
    } finally { setBusy(false); }
  }

  return (
    <div className={s.stack}>
      <StreamNotice streamError={streamError} onRetry={onRetryStream} />
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Groups</h3>
          <p className={s.panelHint}>Shared conversations between 2–3 agents. Member roles come from the agent roster; the bridge enforces the round limit.</p>
        </div>
        <Button variant="primary" disabled={bots.length < 2} onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New group</Button>
      </div>

      <ResourceNotice resource={groupsResource} emptyTitle="No groups yet" emptyDescription="Create a group from two or three existing agents to start a shared conversation."
        emptyAction={<Button variant="primary" disabled={bots.length < 2} onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New group</Button>}>
        {() => (
          <div className={s.split}>
            <div className={s.stack}>
              {groups.map((g) => (
                <div className={s.item} key={g.id}>
                  <button className={s.linkBtn} aria-label={`Open group ${g.name || g.id}`} onClick={() => setSelectedId(g.id)}>
                    <span className={s.itemTitle}>{g.name || g.id}</span>
                  </button>
                  <div className={s.grow}>
                    <div className={s.itemMeta}>{(g.members ?? []).map((m) => `${m.name || m.id}${m.role ? ` (${m.role})` : ""}`).join(" · ") || "no members reported"}</div>
                    <div className={s.itemMeta}>updated {fmtDate(g.updated_at)}</div>
                  </div>
                  <IconButton label={`Delete group ${g.name || g.id}`} onClick={() => setDeleteTarget(g)}><Icon name="trash" size={15} /></IconButton>
                </div>
              ))}
            </div>

            <div className={s.panel}>
              {!selected ? (
                <EmptyState icon={<Icon name="fleet" size={26} />} title="Select a group" description="Pick a group to read its shared ledger and post a message." />
              ) : (
                <div className={s.stack}>
                  <div className={s.panelHead}>
                    <div>
                      <h4 className={s.panelTitle}>{selected.name || selected.id}</h4>
                      <p className={s.panelHint}>Members: {(selected.members ?? []).map((m) => m.name || m.id).join(", ") || "—"}</p>
                    </div>
                    <IconButton label="Refresh group" onClick={detailResource.reload}><Icon name="refresh" size={16} /></IconButton>
                  </div>
                  {detailResource.error !== null && <div className={s.errorText}>Could not load group rows: {errMessage(detailResource.error)}</div>}
                  <div className={s.log} aria-label="Group messages">
                    {rows.map((r, i) => {
                      const b = (r.body ?? {}) as Record<string, unknown>;
                      const author = text(r.author);
                      const member = (selected.members ?? []).find((m) => m.id === author);
                      if (text(r.kind) === "message") {
                        return (
                          <div className={s.logRow} key={`${number(r.seq, 0)}-${i}`}>
                            <span className={s.logKind}>{author === "user" ? "you" : member?.name || author}</span>
                            <span className={s.logBody}>{redact(b.content)}</span>
                            <span className={s.logTime}>{fmtDate(r.created_at)}</span>
                          </div>
                        );
                      }
                      if (text(r.kind) === "member_status") {
                        const st = text(b.status);
                        return (
                          <div className={s.logRow} key={`${number(r.seq, 0)}-${i}`}>
                            <Badge tone={statusTone(st)} dot>{st}</Badge>
                            <span className={s.logBody}>{text(b.bot_name || member?.name || author)}</span>
                            <span className={s.logTime}>{fmtDate(r.created_at)}</span>
                          </div>
                        );
                      }
                      return (
                        <div className={s.logRow} key={`${number(r.seq, 0)}-${i}`}>
                          <span className={s.logKind}>{text(r.kind)}</span>
                          <span className={s.logBody}>{redact(b.text || b.name || b.detail || "")}</span>
                          <span className={s.logTime}>{fmtDate(r.created_at)}</span>
                        </div>
                      );
                    })}
                    {rows.length === 0 && <div className={s.emptyNote}>No messages in this group yet.</div>}
                  </div>

                  <div className={s.item}>
                    <Icon name={roundConflict ? "warning" : "info"} size={16} />
                    <span className={s.hintNote} role="status">
                      {roundConflict
                        ? "The bridge refused a second message with 409/busy. Sending stays disabled until the current round finishes."
                        : busy || roundActive
                          ? "A round is active — sending is disabled until every member has a terminal status, preventing duplicate or recursive triggers."
                          : "The bridge runs one round per message; each member replies at most once."}
                    </span>
                    {roundConflict && <Button size="sm" variant="secondary" onClick={() => { setRoundConflict(false); detailResource.reload(); }}>Recheck round</Button>}
                  </div>
                  <div className={s.composer}>
                    <textarea aria-label="Group message" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={`Message ${selected.name || "group"}…`} className={s.composerText} />
                    <Button variant="primary" disabled={!draft.trim() || busy || roundActive || roundConflict} onClick={() => void send()}>
                      <Icon name="send" size={15} /> Send
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </ResourceNotice>

      <CreateGroupDialog open={createOpen} bots={bots} busy={busy} onClose={() => setCreateOpen(false)} onCreate={createGroup} />
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title={`Delete ${deleteTarget?.name || "group"}?`}
        footer={<><Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => deleteTarget && void remove(deleteTarget)}>Delete group</Button></>}>
        <p className={s.hintNote}>The shared ledger for this group is removed with it. Agent conversations are unaffected.</p>
      </Dialog>
    </div>
  );
}

function CreateGroupDialog({ open, bots, busy, onClose, onCreate }: {
  open: boolean; bots: Bot[]; busy: boolean; onClose: () => void;
  onCreate: (name: string, ids: string[]) => void;
}) {
  const [name, setName] = useState("");
  const [ids, setIds] = useState<string[]>([]);
  const valid = name.trim().length > 0 && ids.length >= 2 && ids.length <= 3;
  function toggle(id: string) {
    setIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) return prev; // back-end limit: 2–3 agents
      return [...prev, id];
    });
  }
  return (
    <Dialog open={open} onClose={onClose} title="New group"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!valid} onClick={() => onCreate(name, ids)}>Create group</Button></>}>
      <div className={s.stack}>
        <p className={s.hintNote}>Select 2–3 distinct agents. The create button stays disabled outside that range.</p>
        <TextField label="Group name" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} />
        <div className={s.fieldGrid}>
          {bots.map((b) => (
            <label key={b.id} className={s.item} style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={ids.includes(b.id)} onChange={() => toggle(b.id)} aria-label={`Include ${b.name || b.id}`} />
              <Avatar bot={b} small />
              <span className={s.grow}>
                <span className={s.itemTitle}>{b.name || b.id}</span>
                <span className={s.itemMeta}>{text(b.role) || "generalist"} · {text(b.engine) === "echo" ? "scripted" : "provider"}</span>
              </span>
            </label>
          ))}
        </div>
        <div className={s.small} aria-live="polite">{ids.length} of 2–3 agents selected</div>
      </div>
    </Dialog>
  );
}

"use client";

import React, { useCallback, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, TextField, Textarea, Toggle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, Routine } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import {
  statusTone, text, wrapped, useBridgeResource,
  type Resource, type RoutineRun,
} from "./support";

const TEMPLATES = [
  { id: "daily", label: "Every day at 09:00", cron: "0 9 * * *" },
  { id: "weekdays", label: "Weekdays at 09:00", cron: "0 9 * * 1-5" },
  { id: "hourly", label: "Every hour", cron: "0 * * * *" },
  { id: "weekly", label: "Mondays at 08:00", cron: "0 8 * * 1" },
  { id: "scratch", label: "Custom expression", cron: "" },
];

function field(r: Routine, key: string): unknown {
  return (r as Record<string, unknown>)[key];
}
function fmtInZone(value: unknown, tz?: string): string {
  const iso = text(value);
  if (!iso) return "Not reported by bridge";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Not reported by bridge";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "short", ...(tz ? { timeZone: tz } : {}),
    }).format(d) + (tz ? ` (${tz})` : "");
  } catch { return `${d.toLocaleString()} (unknown timezone: ${tz})`; }
}

export default function Routines({ routinesResource, bots }: {
  routinesResource: Resource<Routine[]>;
  bots: Bot[];
}) {
  const { notify } = useApp();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Routine | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Routine | null>(null);
  const [busy, setBusy] = useState(false);

  const detailResource = useBridgeResource(
    useCallback(() => selectedId
      ? bridge.routine(selectedId).then((r) => r as { routine?: Routine; runs?: RoutineRun[] })
      : Promise.resolve({} as { routine?: Routine; runs?: RoutineRun[] }), [selectedId]),
    [selectedId]);
  const runsResource = useBridgeResource(
    useCallback(() => selectedId
      ? bridge.routineRuns(selectedId).then((r) => wrapped<RoutineRun>(r as Record<string, unknown>, "runs"))
      : Promise.resolve([] as RoutineRun[]), [selectedId]),
    [selectedId]);

  const selected = routinesResource.data?.find((r) => r.id === selectedId) ?? null;
  const runs = runsResource.data ?? [];

  async function action(id: string, act: "enable" | "disable" | "pause" | "resume" | "run" | "delete", payload?: unknown) {
    setBusy(true);
    try {
      await bridge.routineAction(id, act, payload);
      const labels: Record<string, string> = {
        enable: "Routine enabled.", disable: "Routine disabled.", pause: "Routine paused.",
        resume: "Routine resumed.", run: "Run queued.", delete: "Routine deleted.",
      };
      notify(labels[act] || "Routine updated.", "success");
      if (act === "delete" && selectedId === id) setSelectedId(null);
      routinesResource.reload(); detailResource.reload(); runsResource.reload();
    } catch (e) {
      const msg = errMessage(e);
      if (/409|paused|disabled|already running/i.test(msg)) notify(`Run not started: ${msg}`, "warning");
      else notify(msg, "error");
    } finally { setBusy(false); }
  }

  async function saveEdit(id: string, patch: Record<string, unknown>) {
    setBusy(true);
    try {
      await bridge.routineAction(id, "update", patch);
      notify("Routine updated.", "success");
      setEditTarget(null);
      routinesResource.reload(); detailResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Routines</h3>
          <p className={s.panelHint}>Scheduled agent runs. Next and last run times are shown only when the bridge reports them; missed runs and approval requirements are explained honestly.</p>
        </div>
        <Button variant="primary" disabled={bots.length === 0} onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New routine</Button>
      </div>

      <ResourceNotice resource={routinesResource} emptyTitle="No routines yet" emptyDescription="Create a routine from a schedule template or a custom cron expression."
        emptyAction={<Button variant="primary" disabled={bots.length === 0} onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New routine</Button>}>
        {(data) => (
          <div className={s.split}>
            <div className={s.stack}>
              {data.map((r) => {
                const enabled = field(r, "enabled") !== false;
                const paused = Boolean(field(r, "paused"));
                const running = Boolean(field(r, "running"));
                const status = running ? "running" : paused ? "paused" : enabled ? "enabled" : "disabled";
                return (
                  <div className={`${s.item} ${selected?.id === r.id ? s.isSelected : ""}`} key={r.id}>
                    <button className={s.linkBtn} onClick={() => setSelectedId(r.id)} aria-label={`Open routine ${text(r.name) || r.id}`}><span className={s.itemTitle}>{text(r.name) || r.id}</span></button>
                    <div className={s.grow}>
                      <div className={s.itemMeta}>{text(r.cron_expr || field(r, "cron_expr"))} · {text(r.timezone, "UTC")}</div>
                      <div className={s.itemMeta}>next {fmtInZone(r.next_run ?? field(r, "next_run_at"), text(r.timezone, "UTC"))}</div>
                    </div>
                    <Badge tone={statusTone(status)} dot>{status}</Badge>
                  </div>
                );
              })}
            </div>

            <div className={s.panel}>
              {!selected ? (
                <EmptyState icon={<Icon name="routine" size={26} />} title="Select a routine" description="Inspect its schedule, run history and controls." />
              ) : (
                <RoutineDetail
                  routine={selected} detail={detailResource.data ?? undefined} runs={runs} busy={busy}
                  onAction={action} onEdit={() => setEditTarget(selected)} onDelete={() => setDeleteTarget(selected)}
                  onRefresh={() => { routinesResource.reload(); detailResource.reload(); runsResource.reload(); }}
                  error={detailResource.error === null && runsResource.error === null ? null : "Some routine details could not be loaded."}
                />
              )}
            </div>
          </div>
        )}
      </ResourceNotice>

      <CreateRoutineDialog open={createOpen} bots={bots} busy={busy} onClose={() => setCreateOpen(false)}
        onCreate={async (payload) => {
          setBusy(true);
          try {
            await bridge.createRoutine(payload);
            notify("Routine created.", "success");
            setCreateOpen(false); routinesResource.reload();
          } catch (e) { notify(errMessage(e), "error"); }
          finally { setBusy(false); }
        }} />
      <EditRoutineDialog routine={editTarget} busy={busy} onClose={() => setEditTarget(null)} onSave={saveEdit} />
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title={`Delete ${deleteTarget?.name || "routine"}?`}
        footer={<><Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => deleteTarget && void action(deleteTarget.id, "delete")}>Delete routine</Button></>}>
        <p className={s.hintNote}>The schedule and its stored run history are removed by the bridge.</p>
      </Dialog>
    </div>
  );
}

function RoutineDetail({ routine, detail, runs, busy, onAction, onEdit, onDelete, onRefresh, error }: {
  routine: Routine;
  detail?: { routine?: Routine; runs?: RoutineRun[] };
  runs: RoutineRun[];
  busy: boolean;
  onAction: (id: string, act: "enable" | "disable" | "pause" | "resume" | "run" | "delete", payload?: unknown) => void;
  onEdit: () => void;
  onDelete: () => void;
  onRefresh: () => void;
  error: string | null;
}) {
  const tz = text(routine.timezone, "UTC");
  const enabled = field(routine, "enabled") !== false;
  const paused = Boolean(field(routine, "paused"));
  const running = Boolean(field(routine, "running"));
  const r = detail?.routine ?? routine;
  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h4 className={s.panelTitle}>{text(r.name) || r.id}</h4>
          <p className={s.panelHint}>Cron <span className={s.mono}>{text(r.cron_expr || field(r, "cron_expr"))}</span> · timezone {tz}</p>
        </div>
        <Badge tone={running ? "warning" : paused ? "neutral" : enabled ? "success" : "neutral"} dot>{running ? "running" : paused ? "paused" : enabled ? "enabled" : "disabled"}</Badge>
      </div>
      {error && <div className={s.errorText}>{error}</div>}
      <div className={s.fieldGrid}>
        <div className={s.stat}><span className={s.statNum}>{fmtInZone(r.next_run ?? field(r, "next_run_at"), tz)}</span><span className={s.statLabel}>Next run (reported by bridge)</span></div>
        <div className={s.stat}><span className={s.statNum}>{fmtInZone(r.last_run ?? field(r, "last_run_at"), tz)}</span><span className={s.statLabel}>Last run · {text(r.last_status || field(r, "last_status"), "no status")}</span></div>
      </div>
      {text(r.pause_reason || field(r, "pause_reason")) && <p className={s.hintNote}>Pause reason: {text(r.pause_reason || field(r, "pause_reason"))}</p>}
      <p className={s.hintNote}>
        Unattended runs still pass through Keel&apos;s permission gates: without a standing policy or Autopilot mode, an agent action that needs approval will wait in its conversation instead of running unattended.
      </p>
      <div className={s.actions}>
        <Button size="sm" variant="primary" disabled={busy || paused || !enabled || running} onClick={() => void onAction(r.id, "run")}><Icon name="play" size={14} /> Run now</Button>
        {paused
          ? <Button size="sm" variant="secondary" disabled={busy} onClick={() => void onAction(r.id, "resume")}>Resume</Button>
          : <Button size="sm" variant="secondary" disabled={busy} onClick={() => void onAction(r.id, "pause", { reason: "paused from UI" })}><Icon name="pause" size={14} /> Pause</Button>}
        {enabled
          ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void onAction(r.id, "disable")}>Disable</Button>
          : <Button size="sm" variant="ghost" disabled={busy} onClick={() => void onAction(r.id, "enable")}>Enable</Button>}
        <Button size="sm" variant="ghost" disabled={busy} onClick={onEdit}><Icon name="edit" size={14} /> Edit</Button>
        <Button size="sm" variant="danger" disabled={busy} onClick={onDelete}><Icon name="trash" size={14} /> Delete</Button>
        <Button size="sm" variant="ghost" onClick={onRefresh}><Icon name="refresh" size={14} /> Refresh</Button>
      </div>
      <div className={s.panelHead} style={{ marginTop: 6 }}><h4 className={s.panelTitle}>Run history</h4><Badge tone="neutral">{runs.length}</Badge></div>
      {runs.length === 0 ? <div className={s.emptyNote}>No runs recorded by the bridge yet.</div> : runs.slice().reverse().map((run, i) => {
        const st = text(run.status);
        return (
          <div className={s.item} key={`${text(run.id)}-${i}`}>
            <div className={s.grow}>
              <div className={s.itemTitle}>{st}</div>
              <div className={s.itemMeta}>scheduled {fmtInZone(run.scheduled_at, tz)} · started {fmtInZone(run.started_at, tz)} · finished {fmtInZone(run.finished_at, tz)}</div>
              {text(run.summary) && <div className={s.itemMeta}>{run.summary}</div>}
              {st === "skipped_missed" && <div className={s.hintNote}>Missed scheduled run — the bridge skipped it rather than firing a stale task.</div>}
              {st === "awaiting_approval" && <div className={s.hintNote}>Waiting for an operator decision in the agent conversation.</div>}
              {text(run.error) && <div className={s.errorText}>{text(run.error)}</div>}
            </div>
            <Badge tone={statusTone(st)}>{st}</Badge>
          </div>
        );
      })}
    </div>
  );
}

function CreateRoutineDialog({ open, bots, busy, onClose, onCreate }: {
  open: boolean; bots: Bot[]; busy: boolean; onClose: () => void;
  onCreate: (payload: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [bot, setBot] = useState("");
  const [prompt, setPrompt] = useState("");
  const [template, setTemplate] = useState(TEMPLATES[0].id);
  const [cron, setCron] = useState(TEMPLATES[0].cron);
  const [timezone, setTimezone] = useState("UTC");
  const [enabled, setEnabled] = useState(true);
  const valid = name.trim() && bot && prompt.trim() && cron.trim();
  return (
    <Dialog open={open} onClose={onClose} title="New routine"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!valid} onClick={() => onCreate({
        name: name.trim(), bot_id: bot, prompt: prompt.trim(), cron_expr: cron.trim(), timezone: timezone.trim() || "UTC", enabled,
      })}>Create routine</Button></>}>
      <div className={s.stack}>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className={s.field}><label htmlFor="routine-bot">Agent</label><select id="routine-bot" value={bot} onChange={(e) => setBot(e.target.value)}><option value="">Choose an agent…</option>{bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}</select></div>
        <Textarea label="Prompt (sent to the agent on each run)" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <div className={s.field}><label htmlFor="routine-template">Schedule template</label><select id="routine-template" value={template} onChange={(e) => { setTemplate(e.target.value); const t = TEMPLATES.find((x) => x.id === e.target.value); if (t && t.cron) setCron(t.cron); }}>
          {TEMPLATES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select></div>
        <TextField label="Cron expression" value={cron} onChange={(e) => { setCron(e.target.value); setTemplate("scratch"); }} />
        <TextField label="IANA timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)} hint="For example UTC, Europe/London, America/New_York." />
        <Toggle checked={enabled} onChange={setEnabled} label="Enabled" description="Disabled routines do not run on schedule." />
      </div>
    </Dialog>
  );
}

function EditRoutineDialog({ routine, busy, onClose, onSave }: {
  routine: Routine | null; busy: boolean; onClose: () => void;
  onSave: (id: string, patch: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [cron, setCron] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  React.useEffect(() => {
    if (routine) {
      setName(text(routine.name)); setPrompt(text(routine.prompt));
      setCron(text(routine.cron_expr || field(routine, "cron_expr")));
      setTimezone(text(routine.timezone, "UTC"));
    }
  }, [routine]);
  return (
    <Dialog open={!!routine} onClose={onClose} title={`Edit ${routine?.name || "routine"}`}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!name.trim() || !cron.trim()} onClick={() => routine && onSave(routine.id, { name: name.trim(), prompt, cron_expr: cron.trim(), timezone: timezone.trim() || "UTC" })}>Save routine</Button></>}>
      <div className={s.stack}>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea label="Prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <TextField label="Cron expression" value={cron} onChange={(e) => setCron(e.target.value)} />
        <TextField label="IANA timezone" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
      </div>
    </Dialog>
  );
}

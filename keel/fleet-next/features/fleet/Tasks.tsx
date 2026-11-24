"use client";

import React, { useCallback, useMemo, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, Progress, TextField, Textarea } from "@/components/ui";
import { Icon } from "@/components/icons";
import { api, bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, FleetTask } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import {
  fmtDate, number, reorderByIds, statusTone, text, unwrap, wrapped,
  useBridgeResource, type TaskEvent, type Resource,
} from "./support";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "overdue", label: "Overdue" },
];

function assigneeOf(t: FleetTask): string {
  return text(t.assignee) || text((t as Record<string, unknown>).assigned_bot_id);
}
function dueOf(t: FleetTask): string {
  return text(t.due) || text((t as Record<string, unknown>).due_at) || text((t as Record<string, unknown>).due_date);
}

export default function Tasks({ tasksResource, bots, onOpenBot }: {
  tasksResource: Resource<FleetTask[]>;
  bots: Bot[];
  onOpenBot: (id: string) => void;
}) {
  const { notify } = useApp();
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FleetTask | null>(null);
  const [busy, setBusy] = useState(false);

  const tasks = tasksResource.data ?? [];
  const selected = tasks.find((t) => t.id === selectedId) ?? null;

  const eventsResource = useBridgeResource(
    useCallback(() => tasksResource.data && selectedId
      ? bridge.taskEvents(selectedId).then((r) => wrapped<TaskEvent>(r as Record<string, unknown>, "events"))
      : Promise.resolve([] as TaskEvent[]), [selectedId, tasksResource.data]),
    [selectedId]);

  const visible = useMemo(() => tasks.filter((t) => {
    const q = search.trim().toLowerCase();
    if (q && !`${text(t.title)} ${text((t as Record<string, unknown>).description)} ${t.id}`.toLowerCase().includes(q)) return false;
    const st = text(t.status).toLowerCase();
    if (filter === "overdue") return Boolean(dueOf(t)) && st !== "completed" && st !== "cancelled" && new Date(dueOf(t)).getTime() < Date.now();
    if (filter !== "all" && st !== filter) return false;
    return true;
  }), [tasks, filter, search]);

  async function create(payload: Record<string, unknown>) {
    setBusy(true);
    try {
      const t = unwrap<FleetTask>(await bridge.createTask(payload), "task");
      notify(`Task “${text(t.title) || t.id}” created.`, "success");
      setCreateOpen(false);
      setSelectedId(t.id);
      tasksResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function patch(id: string, patchObj: Record<string, unknown>, label: string) {
    setBusy(true);
    try {
      await bridge.updateTask(id, patchObj);
      notify(label, "success");
      tasksResource.reload(); eventsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function assign(id: string, botId: string) {
    setBusy(true);
    try {
      // Verified real route: routes.py `tasks/<id>/assign` (bridge client does
      // not expose a dedicated assign method, but re-exports `api`).
      await api(`tasks/${id}/assign`, { method: "POST", body: JSON.stringify({ assigned_bot_id: botId || null }) });
      notify(botId ? "Task assigned." : "Task unassigned.", "success");
      tasksResource.reload(); eventsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function cancel(id: string) {
    await patch(id, { status: "cancelled" }, "Task cancelled.");
  }
  async function undo(id: string) {
    setBusy(true);
    try {
      await bridge.undoTask(id);
      notify("Task restored to its previous state.", "success");
      tasksResource.reload(); eventsResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }
  async function remove(t: FleetTask) {
    setBusy(true);
    try {
      await bridge.deleteTask(t.id);
      notify("Task deleted.", "success");
      setDeleteTarget(null);
      if (selectedId === t.id) setSelectedId(null);
      tasksResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }
  async function move(id: string, targetId: string) {
    const ids = reorderByIds(tasks, id, targetId);
    setBusy(true);
    try {
      await bridge.reorderTasks({ ids });
      tasksResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Fleet tasks</h3>
          <p className={s.panelHint}>Shared tasks from the bridge. Status, priority, progress and history are recorded by the Python runtime.</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New task</Button>
      </div>

      <ResourceNotice resource={tasksResource} emptyTitle="No tasks yet" emptyDescription="Create a shared task, assign it to an agent and track progress here."
        emptyAction={<Button variant="primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> New task</Button>}>
        {(data) => (
          <div className={s.stack}>
            <div className={s.filters}>
              {FILTERS.map((f) => <button key={f.value} className={s.chip} aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>{f.label}</button>)}
              <div className={s.search}>
                <Icon name="search" size={14} />
                <input aria-label="Search tasks" placeholder="Search tasks…" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
            </div>
            <div className={s.split}>
              <div className={s.stack}>
                {visible.length === 0 ? (
                  <EmptyState title="No tasks match this filter" description="Try a different filter or clear the search." />
                ) : visible.map((t, i) => {
                  const st = text(t.status);
                  const overdue = Boolean(dueOf(t)) && st !== "completed" && st !== "cancelled" && new Date(dueOf(t)).getTime() < Date.now();
                  return (
                    <div className={`${s.item} ${selected?.id === t.id ? s.isSelected : ""}`} key={t.id}>
                      <button className={s.linkBtn} onClick={() => setSelectedId(t.id)} aria-label={`Open task ${text(t.title) || t.id}`}>
                        <span className={s.itemTitle}>{text(t.title) || t.id}</span>
                      </button>
                      <div className={s.grow}>
                        <div className={s.itemMeta}>
                          {st || "unknown"} · {text(t.priority, "normal")} · {number(t.progress, 0)}%
                          {assigneeOf(t) ? ` · ${bots.find((b) => b.id === assigneeOf(t))?.name || assigneeOf(t)}` : " · unassigned"}
                          {overdue && " · OVERDUE"}
                        </div>
                        <div className={s.progress}><span style={{ width: `${Math.max(0, Math.min(100, number(t.progress, 0)))}%` }} /></div>
                      </div>
                      <Badge tone={overdue ? "danger" : statusTone(st)}>{overdue ? "overdue" : st || "unknown"}</Badge>
                      <div className={s.actions}>
                        <IconButton label="Move up" disabled={i === 0 || busy} onClick={() => void move(t.id, visible[i - 1].id)}><Icon name="chevron" size={14} style={{ transform: "rotate(-90deg)" }} /></IconButton>
                        <IconButton label="Move down" disabled={i === visible.length - 1 || busy} onClick={() => void move(t.id, visible[i + 1].id)}><Icon name="chevron" size={14} style={{ transform: "rotate(90deg)" }} /></IconButton>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className={s.panel}>
                {!selected ? (
                  <EmptyState icon={<Icon name="tasks" size={26} />} title="Select a task" description="Open a task to change its status, progress, assignee and see its history." />
                ) : (
                  <TaskDetail
                    task={selected} bots={bots} busy={busy} events={eventsResource.data ?? []}
                    onPatch={patch} onAssign={assign} onCancel={cancel} onUndo={undo}
                    onDelete={() => setDeleteTarget(selected)} onOpenBot={onOpenBot}
                    onRefresh={() => { tasksResource.reload(); eventsResource.reload(); }}
                  />
                )}
              </div>
            </div>
            <p className={s.hintNote}>{data.length} task{data.length === 1 ? "" : "s"} reported by the bridge.</p>
          </div>
        )}
      </ResourceNotice>

      <CreateTaskDialog open={createOpen} bots={bots} busy={busy} onClose={() => setCreateOpen(false)} onCreate={create} />
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="Delete task?"
        footer={<><Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => deleteTarget && void remove(deleteTarget)}>Delete task</Button></>}>
        <p className={s.hintNote}>“{text(deleteTarget?.title)}” will be removed. Use Undo from the task list where the bridge supports restoring a previous state.</p>
      </Dialog>
    </div>
  );
}

function TaskDetail({ task, bots, busy, events, onPatch, onAssign, onCancel, onUndo, onDelete, onOpenBot, onRefresh }: {
  task: FleetTask; bots: Bot[]; busy: boolean; events: TaskEvent[];
  onPatch: (id: string, patch: Record<string, unknown>, label: string) => void;
  onAssign: (id: string, botId: string) => void;
  onCancel: (id: string) => void;
  onUndo: (id: string) => void;
  onDelete: () => void;
  onOpenBot: (id: string) => void;
  onRefresh: () => void;
}) {
  const [status, setStatus] = useState(text(task.status, "pending"));
  const [progress, setProgress] = useState(String(number(task.progress, 0)));
  const [note, setNote] = useState("");
  const sourceId = text((task as Record<string, unknown>).source_task_id);
  const sourceAgent = assigneeOf(task) || text((task as Record<string, unknown>).created_by);
  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h4 className={s.panelTitle}>{text(task.title) || task.id}</h4>
          <p className={s.panelHint}>{text((task as Record<string, unknown>).description) || "No description."}</p>
        </div>
        <Badge tone={statusTone(status)}>{status}</Badge>
      </div>
      <div className={s.fieldGrid}>
        <div className={s.field}><label htmlFor="task-status">Status</label><select id="task-status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="pending">pending</option><option value="in_progress">in_progress</option><option value="completed">completed</option><option value="failed">failed</option><option value="cancelled">cancelled</option></select></div>
        <div className={s.field}><label htmlFor="task-progress">Progress %</label><input id="task-progress" type="number" min={0} max={100} value={progress} onChange={(e) => setProgress(e.target.value)} /></div>
      </div>
      <div className={s.field}><label htmlFor="task-note">Note (recorded in task history)</label><Textarea id="task-note" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      <div className={s.row}>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onPatch(task.id, { status, progress: number(progress, 0), ...(note.trim() ? { note: note.trim() } : {}) }, "Task updated.")}>Save changes</Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={onRefresh}><Icon name="refresh" size={14} /> Refresh</Button>
      </div>
      <div className={s.field}>
        <label htmlFor="task-assignee">Assignee</label>
        <select id="task-assignee" value={assigneeOf(task)} onChange={(e) => onAssign(task.id, e.target.value)}>
          <option value="">Unassigned</option>
          {bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}
        </select>
      </div>
      <div className={s.hintNote}>
        Source: {text((task as Record<string, unknown>).source, "user")} · created by {sourceAgent || "unknown"} · created {fmtDate(task.created)}
        {dueOf(task) && ` · due ${fmtDate(dueOf(task))}`}
        {sourceId && ` · source task ${sourceId}`}
      </div>
      <div className={s.row}>
        {sourceAgent && bots.some((b) => b.id === sourceAgent) && <Button size="sm" variant="ghost" onClick={() => onOpenBot(sourceAgent)}><Icon name="link" size={14} /> Open source agent</Button>}
        {status !== "cancelled" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => onCancel(task.id)}>Cancel task</Button>}
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => onUndo(task.id)}>Undo</Button>
        <Button size="sm" variant="danger" disabled={busy} onClick={onDelete}><Icon name="trash" size={14} /> Delete</Button>
      </div>
      <div className={s.panelHead} style={{ marginTop: 6 }}><h4 className={s.panelTitle}>Task history</h4><Badge tone="neutral">{events.length}</Badge></div>
      {events.length === 0 ? <div className={s.emptyNote}>No task events reported by the bridge.</div> : events.slice().reverse().map((e, i) => (
        <div className={s.item} key={`${text(e.id)}-${i}`}>
          <div className={s.grow}>
            <div className={s.itemTitle}>{redactEvent(e.event)}</div>
            {e.note && <div className={s.itemMeta}>{e.note}</div>}
            {e.from_status || e.to_status ? <div className={s.itemMeta}>{text(e.from_status, "—")} → {text(e.to_status, "—")}</div> : null}
          </div>
          <span className={s.itemMeta}>{fmtDate(e.created_at)}</span>
        </div>
      ))}
    </div>
  );
}
function redactEvent(value?: string): string { return text(value).replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-••••"); }

function CreateTaskDialog({ open, bots, busy, onClose, onCreate }: {
  open: boolean; bots: Bot[]; busy: boolean; onClose: () => void;
  onCreate: (payload: Record<string, unknown>) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const [assignee, setAssignee] = useState("");
  return (
    <Dialog open={open} onClose={onClose} title="New task"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!title.trim()} onClick={() => onCreate({
        title: title.trim(), description: description.trim(), priority,
        ...(assignee ? { assigned_bot_id: assignee } : {}),
      })}>Create task</Button></>}>
      <div className={s.stack}>
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className={s.field}><label htmlFor="new-priority">Priority</label><select id="new-priority" value={priority} onChange={(e) => setPriority(e.target.value)}><option value="low">low</option><option value="normal">normal</option><option value="high">high</option></select></div>
        <div className={s.field}><label htmlFor="new-assignee">Assignee</label><select id="new-assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">Unassigned</option>{bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}</select></div>
      </div>
    </Dialog>
  );
}

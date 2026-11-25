"use client";

// Kanban board built from the task rows the Python bridge actually returns.
// Column identity is the real `fleet_tasks.status` CHECK values (db.py);
// every mutation goes through the real `tasks/:id/update` / `tasks/:id/assign`
// routes. No status, priority or assignment is invented client-side.

import React, { useMemo, useState } from "react";
import { Badge, Button } from "@/components/ui";
import { Icon } from "@/components/icons";
import { api, bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, FleetTask } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import { fmtDate, number, statusTone, text, type Resource } from "./support";

/** Exact status values from `fleet_tasks.status` (keel/src/keel/fleet/db.py). */
const COLUMNS = [
  { id: "pending", label: "Pending" },
  { id: "in_progress", label: "In progress" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
  { id: "cancelled", label: "Cancelled" },
] as const;
const PRIORITIES = ["all", "low", "normal", "high"] as const;

function assigneeOf(t: FleetTask): string {
  return text(t.assignee) || text((t as Record<string, unknown>).assigned_bot_id);
}
function dueOf(t: FleetTask): string {
  return text(t.due) || text((t as Record<string, unknown>).due_at) || text((t as Record<string, unknown>).due_date);
}

export default function Board({ tasksResource, bots, onOpenBot }: {
  tasksResource: Resource<FleetTask[]>;
  bots: Bot[];
  onOpenBot: (id: string) => void;
}) {
  const { notify } = useApp();
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const tasks = tasksResource.data ?? [];

  const { buckets, unclassified } = useMemo(() => {
    const map = new Map<string, FleetTask[]>(COLUMNS.map((c) => [c.id, []]));
    const other: FleetTask[] = [];
    for (const t of tasks) {
      if (priority !== "all" && text(t.priority, "normal") !== priority) continue;
      const status = text(t.status).toLowerCase();
      const bucket = map.get(status);
      if (bucket) bucket.push(t);
      else other.push(t);
    }
    return { buckets: map, unclassified: other };
  }, [tasks, priority]);

  async function move(id: string, status: string) {
    const task = tasks.find((t) => t.id === id);
    if (!task || text(task.status) === status) return;
    setBusyId(id);
    try {
      // Verified real mutation route: routes.py `tasks/<id>/update` accepts status.
      await bridge.updateTask(id, { status });
      notify(`Task moved to ${status}.`, "success");
      tasksResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusyId(null); }
  }

  async function assign(id: string, botId: string) {
    setBusyId(id);
    try {
      // Verified real mutation route: routes.py `tasks/<id>/assign`.
      await api(`tasks/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ assigned_bot_id: botId || null }),
      });
      notify(botId ? "Task assigned." : "Task unassigned.", "success");
      tasksResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusyId(null); }
  }

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Task board</h3>
          <p className={s.panelHint}>Columns are the bridge&apos;s real task statuses. Cards are the bridge&apos;s real tasks; drag a card or use its status selector to call the update route.</p>
        </div>
        <div className={s.filters} role="group" aria-label="Filter by reported priority">
          {PRIORITIES.map((p) => (
            <button key={p} className={s.chip} aria-pressed={priority === p} onClick={() => setPriority(p)}>{p === "all" ? "All priorities" : p}</button>
          ))}
        </div>
      </div>

      <ResourceNotice resource={tasksResource} emptyTitle="No tasks reported"
        emptyDescription="The board is empty because the bridge reported no tasks. No placeholder cards are shown."
        emptyAction={<Button size="sm" variant="secondary" onClick={tasksResource.reload}>Reload tasks</Button>}>
        {() => (
          <div className={s.stack}>
            <div className={s.board}>
              {COLUMNS.map((col) => {
                const items = buckets.get(col.id) ?? [];
                return (
                  <section
                    key={col.id}
                    className={s.boardCol}
                    aria-label={`${col.label} column`}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const id = e.dataTransfer.getData("text/plain");
                      if (id) void move(id, col.id);
                    }}
                  >
                    <div className={s.boardColHead}>
                      <h4 className={s.panelTitle}>{col.label}</h4>
                      <Badge tone="neutral">{items.length}</Badge>
                    </div>
                    {items.length === 0 ? (
                      <p className={s.emptyNote}>No tasks reported in this status.</p>
                    ) : items.map((t) => {
                      const title = text(t.title) || t.id;
                      const assignee = assigneeOf(t);
                      const due = dueOf(t);
                      const overdue = Boolean(due) && text(t.status) !== "completed" && text(t.status) !== "cancelled" && new Date(due).getTime() < Date.now();
                      return (
                        <article
                          key={t.id}
                          className={s.boardCard}
                          role="group"
                          aria-label={`Task ${title}: ${text(t.status, "unknown")}, ${text(t.priority, "normal")} priority`}
                          draggable={busyId !== t.id}
                          onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                        >
                          <div className={s.itemTitle}>{title}</div>
                          <div className={s.itemMeta}>
                            {text(t.priority, "normal")} priority · {number(t.progress, 0)}% · created {fmtDate(t.created)}
                          </div>
                          {due && <div className={s.itemMeta}>due {fmtDate(due)}{overdue ? " · OVERDUE" : ""}</div>}
                          <div className={s.row}>
                            <Badge tone={overdue ? "danger" : statusTone(text(t.status))}>{text(t.status, "unknown")}</Badge>
                            {assignee && <Badge tone="info">{bots.find((b) => b.id === assignee)?.name || assignee}</Badge>}
                          </div>
                          <div className={s.progress}><span style={{ width: `${Math.max(0, Math.min(100, number(t.progress, 0)))}%` }} /></div>
                          <label className={s.field}>
                            <span>Move “{title}” to status</span>
                            <select
                              aria-label={`Move ${title} to status`}
                              value={text(t.status)}
                              disabled={busyId === t.id}
                              onChange={(e) => void move(t.id, e.target.value)}
                            >
                              {COLUMNS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                            </select>
                          </label>
                          <label className={s.field}>
                            <span>Assign “{title}”</span>
                            <select
                              aria-label={`Assign ${title}`}
                              value={assignee}
                              disabled={busyId === t.id}
                              onChange={(e) => void assign(t.id, e.target.value)}
                            >
                              <option value="">Unassigned</option>
                              {bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}
                            </select>
                          </label>
                          {assignee && bots.some((b) => b.id === assignee) && (
                            <button className={s.linkBtn} onClick={() => onOpenBot(assignee)}>Open assignee in Agents</button>
                          )}
                        </article>
                      );
                    })}
                  </section>
                );
              })}
            </div>
            {unclassified.length > 0 && (
              <p className={s.hintNote} role="status">
                {unclassified.length} task{unclassified.length === 1 ? "" : "s"} reported with a status outside the bridge&apos;s known set; shown in no column rather than relabelled.
              </p>
            )}
            <p className={s.hintNote}>
              {tasks.length} task{tasks.length === 1 ? "" : "s"} reported by the bridge.
              {" "}<Button size="sm" variant="ghost" onClick={tasksResource.reload}><Icon name="refresh" size={13} /> Refresh board</Button>
            </p>
          </div>
        )}
      </ResourceNotice>
    </div>
  );
}

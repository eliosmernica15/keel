"use client";

// Collapsible work log. Every line is derived from real rows/events; raw tool
// input and output are only rendered when the user opens a disclosure.

import React, { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import { Badge, StatusDot } from "@/components/ui";
import {
  formatDuration, formatTime, humanSummary, safeJson, stepProgress, textOf, toolVerb,
  type RowView, type StatusInfo, type WorkState,
} from "./shared";
import s from "./cowork.module.css";

interface Props {
  rows: RowView[];
  status: StatusInfo;
  activeSince: number | null;
  expanded: boolean;
  onToggle: () => void;
}

type Group =
  | { type: "steps"; rows: RowView[]; key: string; ts?: string | number }
  | { type: "event"; row: RowView; key: string };

const TONE: Record<WorkState, "success" | "warning" | "danger" | "info" | "neutral"> = {
  running: "info", queued: "warning", paused: "warning", "waiting-for-user": "warning",
  failed: "danger", cancelled: "danger", completed: "success", idle: "neutral",
};

const ACTIVE_TEXT: Record<WorkState, string> = {
  running: "Agent is working",
  queued: "Queued — waiting for the current turn to finish",
  paused: "Paused",
  "waiting-for-user": "Waiting for your decision",
  failed: "Turn failed",
  cancelled: "Turn cancelled",
  completed: "Turn completed",
  idle: "Ready",
};

function groupsOf(rows: RowView[]): Group[] {
  const out: Group[] = [];
  let buffer: RowView[] = [];
  const flush = () => {
    if (!buffer.length) return;
    out.push({ type: "steps", rows: buffer, key: `g-${buffer[0].key}`, ts: buffer[0].ts });
    buffer = [];
  };
  for (const row of rows) {
    if (row.kind === "step") { buffer.push(row); continue; }
    flush();
    if (row.kind === "turn_end" || row.kind === "approval" || row.kind === "ask" || row.kind === "notice") {
      out.push({ type: "event", row, key: `e-${row.key}` });
    }
  }
  flush();
  return out;
}

export default function WorkLog({ rows, status, activeSince, expanded, onToggle }: Props) {
  const [now, setNow] = useState(0); // deterministic on server + first client render
  useEffect(() => {
    if (activeSince == null) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [activeSince]);

  const groups = useMemo(() => groupsOf(rows), [rows]);
  const progress = useMemo(() => stepProgress(rows), [rows]);
  const elapsed = activeSince == null ? null : formatDuration(now - activeSince);
  const stepCount = rows.filter((r) => r.kind === "step").length;
  const active = status.state !== "idle" && status.state !== "completed";
  const finishedSteps = progress ? progress.done + progress.failed : 0;
  const percent = progress && progress.total > 0 ? Math.round((finishedSteps / progress.total) * 100) : 0;

  return (
    <section className={s.worklog} aria-label="Work log">
      <button type="button" className={s.worklogHead} onClick={onToggle} aria-expanded={expanded}>
        <Icon name="chevron" size={14} className={`${s.chev} ${expanded ? s.chevOpen : ""}`} />
        <span className={s.worklogTitle}>Work log</span>
        <span className={s.worklogSummary}>
          {progress ? `${finishedSteps}/${progress.total} steps reported` : stepCount ? `${stepCount} tool step${stepCount === 1 ? "" : "s"}` : "No tool steps yet"}
        </span>
        <Badge tone={TONE[status.state]} dot>{status.label}</Badge>
      </button>

      {expanded && (
        <div className={s.worklogBody}>
          {active && (
            <div className={`${s.activeRow} ${status.state === "waiting-for-user" ? s.activeWaiting : ""}`} role="status" aria-live="polite">
              <StatusDot tone={TONE[status.state]} label={status.label} />
              <span className={s.activeText}>
                {ACTIVE_TEXT[status.state]}
                {status.reason ? ` · ${status.reason}` : ""}
              </span>
              {elapsed && <span className={s.elapsed}>{elapsed}</span>}
            </div>
          )}

          {progress && (
            <div className={s.progressRow}>
              <span role="progressbar" aria-label="Reported tool steps completed"
                aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={finishedSteps}
                aria-valuetext={`${finishedSteps} of ${progress.total} steps reported`}
                className={s.progressTrack}>
                <span className={s.progressFill} style={{ width: `${percent}%` }} />
              </span>
              <span className={s.progressText}>
                {progress.done} done{progress.failed ? ` · ${progress.failed} failed` : ""}{progress.running ? ` · ${progress.running} running` : ""} of {progress.total}
              </span>
            </div>
          )}

          {groups.length === 0 && (
            <p className={s.worklogEmpty}>Tool activity will appear here as the agent works. Nothing is shown until the bridge reports a real step.</p>
          )}

          <ol className={s.timelineList} aria-label="Execution timeline">
          {groups.map((g) => g.type === "steps" ? (
            <li className={s.logGroup} key={g.key}>
              <div className={s.logLine}>
                <Icon name="terminal" size={14} />
                <span className={s.logText}>{humanSummary(g.rows)}</span>
                {g.ts != null && <span className={s.logTime}>{formatTime(g.ts)}</span>}
              </div>
              <details className={s.rawDetails}>
                <summary>Raw tool calls ({g.rows.length})</summary>
                <ul>
                  {g.rows.map((r) => (
                    <li key={r.key}>
                      <b>{toolVerb(textOf(r.body.name ?? r.body.tool) || "tool")}</b>
                      {r.body.detail != null && <span> · {textOf(r.body.detail)}</span>}
                      {r.body.status != null && <span> · {textOf(r.body.status)}</span>}
                      {(r.body.input !== undefined || r.body.args !== undefined) && (
                        <pre>input {safeJson(r.body.input ?? r.body.args)}</pre>
                      )}
                      {(r.body.output !== undefined || r.body.result !== undefined) && (
                        <pre>output {safeJson(r.body.output ?? r.body.result)}</pre>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ) : (
            <li className={`${s.logLine} ${s.logEvent}`} key={g.key}>
              <Icon name={g.row.kind === "approval" ? "shield" : g.row.kind === "turn_end" ? "check" : g.row.kind === "ask" ? "info" : "info"} size={14} />
              <span className={s.logText}>
                {g.row.kind === "approval" && `Approval requested · ${textOf(g.row.body.tool_name ?? g.row.body.operation ?? "tool")}`}
                {g.row.kind === "ask" && `Question · ${textOf(g.row.body.question ?? "waiting for you")}`}
                {g.row.kind === "turn_end" && `Turn ${textOf(g.row.body.terminal_reason) || "ended"}${typeof g.row.body.duration_ms === "number" ? ` · ${formatDuration(g.row.body.duration_ms)}` : ""}`}
                {g.row.kind === "notice" && textOf(g.row.body.text)}
              </span>
              {g.row.ts != null && <span className={s.logTime}>{formatTime(g.row.ts)}</span>}
            </li>
          ))}
          </ol>
        </div>
      )}
    </section>
  );
}

"use client";

// Durable conversation timeline. Cards are rendered only from real row bodies;
// tool detail is disclosed on demand and no outcome is shown before the API
// confirms it.

import React, { useState } from "react";
import { Icon, IconButton } from "@/components/icons";
import { Badge } from "@/components/ui";
import { bridge } from "@/lib/api";
import { Markdown } from "./Markdown";
import {
  changedFiles, formatDuration, formatTime, humanSummary, safeJson, textOf, toolVerb,
  usageFacts, type LibraryView, type RowView, type StatusInfo,
} from "./shared";
import type { Usage } from "@/lib/types";
import s from "./cowork.module.css";

export interface TimelineProps {
  rows: RowView[];
  streamText: string;
  streaming: boolean;
  botName: string;
  status: StatusInfo;
  library: LibraryView[];
  usage: Usage | null;
  onCopy: (row: RowView) => void;
  onFork: (row: RowView) => void;
  onRewind: (row: RowView) => void;
  onDecide: (row: RowView, decision: "once" | "always" | "never") => Promise<boolean>;
  onAnswer: (row: RowView, answer: string) => Promise<boolean>;
}

function isResolved(row: RowView): boolean {
  const st = textOf(row.body.status ?? row.body.decision).toLowerCase();
  return ["approved", "denied", "never", "refused", "rejected", "resolved", "decided", "answered"].includes(st);
}

function AskCard({ row, onAnswer }: { row: RowView; onAnswer: (r: RowView, a: string) => Promise<boolean> }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [answered, setAnswered] = useState<string | null>(null);
  const options: string[] = Array.isArray(row.body.options) ? row.body.options.filter((o): o is string => typeof o === "string") : [];

  if (isResolved(row) || answered !== null) {
    return (
      <div className={s.resolvedCard} role="status">
        <Icon name="check" size={14} /> <b>Answered</b>
        <span>{answered ?? textOf(row.body.answer)}</span>
      </div>
    );
  }

  const answer = async (text: string) => {
    if (!text.trim() || busy) return;
    setBusy(true);
    const ok = await onAnswer(row, text.trim());
    setBusy(false);
    if (ok) setAnswered(text.trim());
  };

  return (
    <section className={`${s.card} ${s.askCard}`} aria-label="Agent question">
      <header className={s.cardHead}>
        <Icon name="info" size={16} />
        <h4>Agent is asking · waiting for you</h4>
      </header>
      <p className={s.askQuestion}>{textOf(row.body.question ?? row.body.text)}</p>
      {options.length > 0 && (
        <div className={s.optionRow}>
          {options.map((o) => (
            <button key={o} type="button" className={s.optionBtn} disabled={busy} onClick={() => void answer(o)}>{o}</button>
          ))}
        </div>
      )}
      <form className={s.answerForm} onSubmit={(e) => { e.preventDefault(); void answer(value); }}>
        <label className={s.srOnly} htmlFor={`ask-${row.key}`}>Your answer</label>
        <input id={`ask-${row.key}`} value={value} onChange={(e) => setValue(e.target.value)} placeholder="Type your answer…" disabled={busy} />
        <button type="submit" disabled={!value.trim() || busy}>Answer</button>
      </form>
    </section>
  );
}

function ApprovalCard({ row, onDecide }: { row: RowView; onDecide: TimelineProps["onDecide"] }) {
  const [pending, setPending] = useState(false);
  const [resolved, setResolved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const operation = textOf(row.body.operation ?? row.body.tool_name ?? row.body.tool ?? "tool call");
  const scope = textOf(row.body.scope ?? row.body.description ?? "");
  const approvalId = textOf(row.body.approval_id);

  if (isResolved(row) || resolved) {
    return (
      <div className={s.resolvedCard} role="status">
        <Icon name="check" size={14} /> <b>{resolved ?? "Resolved"}</b>
        <span>{operation}{scope ? ` · ${scope}` : ""}</span>
      </div>
    );
  }

  const decide = async (decision: "once" | "always" | "never") => {
    if (pending || !approvalId) return;
    setPending(true); setError(null);
    const ok = await onDecide(row, decision);
    setPending(false);
    if (ok) setResolved(decision === "never" ? "Don't allow" : decision === "always" ? "Always allowed" : "Allowed once");
    else setError("The bridge did not confirm this decision. Nothing was granted.");
  };

  return (
    <section className={`${s.card} ${s.approvalCard}`} aria-label="Permission request">
      <header className={s.cardHead}>
        <Icon name="shield" size={16} />
        <h4>Approval required</h4>
        {row.ts != null && <time className={s.cardTime}>{formatTime(row.ts)}</time>}
      </header>
      <p className={s.approvalOp}>{operation}</p>
      {scope && <p className={s.approvalScope}><span>Scope</span> {scope}</p>}
      {!approvalId && <p className={s.inlineWarn}><Icon name="warning" size={13} /> No approval id was reported — this request cannot be decided.</p>}
      {error && <p className={s.inlineError} role="alert">{error}</p>}
      <div className={s.approvalActions}>
        <button type="button" className={s.approveBtn} disabled={pending || !approvalId} onClick={() => void decide("once")}>Allow once</button>
        <button type="button" className={s.approveBtn} disabled={pending || !approvalId} onClick={() => void decide("always")}>Always allow</button>
        <button type="button" className={s.denyBtn} disabled={pending || !approvalId} onClick={() => void decide("never")}>Don&apos;t allow</button>
      </div>
    </section>
  );
}

function PlanCard({ row }: { row: RowView }) {
  const raw = row.body.steps ?? row.body.plan ?? row.body.tasks;
  if (!Array.isArray(raw)) return null;
  const steps = raw.filter((x): x is Record<string, unknown> => !!x && typeof x === "object");
  if (!steps.length) return null;
  return (
    <section className={s.card} aria-label="Plan from the agent">
      <header className={s.cardHead}><Icon name="tasks" size={16} /><h4>Plan reported by the agent</h4></header>
      <ol className={s.planList}>
        {steps.map((step, i) => {
          const state = textOf(step.status ?? step.state).toLowerCase();
          const done = /done|complete|ok/.test(state);
          const active = /active|running|progress/.test(state);
          return (
            <li key={i} className={`${s.planStep} ${done ? s.planDone : ""} ${active ? s.planActive : ""}`}>
              <Icon name={done ? "check" : active ? "clock" : "file"} size={14} />
              <span>{textOf(step.title ?? step.text ?? step.description ?? step.step ?? `Step ${i + 1}`)}</span>
              {state && <span className={s.planState}>{state}</span>}
            </li>
          );
        })}
      </ol>
      <p className={s.cardNote}>Steps come from the agent&apos;s own report. Tool calls still go through their normal approval flow.</p>
    </section>
  );
}

function DeliverableCard({ row }: { row: RowView }) {
  const files = Array.isArray(row.body.files) ? row.body.files : null;
  if (!files && !row.body.path && !row.body.name) return null;
  return (
    <section className={s.card} aria-label="Deliverable reported by the agent">
      <header className={s.cardHead}><Icon name="file" size={16} /><h4>Deliverable</h4></header>
      {files ? (
        <ul className={s.fileList}>
          {files.filter((f): f is Record<string, unknown> => !!f && typeof f === "object").map((f, i) => {
            const id = textOf(f.id);
            const name = textOf(f.name ?? f.path ?? `file ${i + 1}`);
            return id
              ? <li key={i}><a href={bridge.downloadUrl(id)} className={s.downloadLink} download><Icon name="download" size={14} />{name}</a></li>
              : <li key={i}><span>{name}</span></li>;
          })}
        </ul>
      ) : (
        <p className={s.cardNote}>{textOf(row.body.path ?? row.body.name)}</p>
      )}
    </section>
  );
}

export default function Timeline(props: TimelineProps) {
  const { rows, streamText, streaming, botName, status, library, usage, onCopy, onFork, onRewind, onDecide, onAnswer } = props;
  const [decided, setDecided] = useState<Record<string, string>>({});
  const lastEnd = [...rows].reverse().find((r) => r.kind === "turn_end");
  const files = changedFiles(rows);
  const facts = usageFacts(usage);
  const showSummary = !!lastEnd && (files.length > 0 || facts.length > 0 || typeof lastEnd.body.duration_ms === "number");

  const decide = async (row: RowView, decision: "once" | "always" | "never") => {
    const ok = await onDecide(row, decision);
    if (ok) setDecided((prev) => ({ ...prev, [row.key]: decision }));
    return ok;
  };

  const out: React.ReactNode[] = [];
  let steps: RowView[] = [];
  const flushSteps = (key: string) => {
    if (!steps.length) return;
    const group = steps; steps = [];
    out.push(
      <details className={s.stepGroup} key={`steps-${key}`}>
        <summary><Icon name="chevron" size={13} /><span>{humanSummary(group)}</span><span className={s.stepCount}>{group.length}</span></summary>
        <ul>
          {group.map((r) => (
            <li key={r.key}>
              <b>{toolVerb(textOf(r.body.name ?? r.body.tool) || "tool")}</b>
              {r.body.detail != null && <span> — {textOf(r.body.detail)}</span>}
              {r.body.status != null && <span className={s.stepStatus}> · {textOf(r.body.status)}</span>}
              {r.ts != null && <time>{formatTime(r.ts)}</time>}
              {(r.body.input !== undefined || r.body.args !== undefined || r.body.output !== undefined) && (
                <pre>{safeJson({ input: r.body.input ?? r.body.args, output: r.body.output })}</pre>
              )}
            </li>
          ))}
        </ul>
      </details>,
    );
  };

  for (const row of rows) {
    if (row.kind === "step") { steps.push(row); continue; }
    flushSteps(row.key);
    const b = row.body;
    // A real row body may carry a plan under any kind — only render it when
    // the bridge actually returned steps.
    if (Array.isArray(b.steps) || Array.isArray(b.plan)) {
      out.push(<PlanCard row={row} key={row.key} />);
      continue;
    }
    if (row.kind === "message") {
      const role = (row.role ?? textOf(b.role)) === "user" ? "user" : "assistant";
      out.push(
        <article className={`${s.bubble} ${role === "user" ? s.bubbleUser : s.bubbleAssistant}`} key={row.key}>
          <header className={s.bubbleHead}>
            <span className={s.role}>{role === "user" ? "You" : botName}</span>
            {row.ts != null && <time>{formatTime(row.ts)}</time>}
          </header>
          <Markdown text={textOf(b.content)} />
          <div className={s.msgActions}>
            <IconButton label="Copy message" onClick={() => onCopy(row)}><Icon name="copy" size={14} /></IconButton>
            <IconButton label="Fork from here" onClick={() => onFork(row)}><Icon name="link" size={14} /></IconButton>
            <IconButton label="Rewind to before this message" onClick={() => onRewind(row)}><Icon name="refresh" size={14} /></IconButton>
          </div>
        </article>,
      );
    } else if (row.kind === "approval") {
      if (decided[row.key]) {
        out.push(<div className={s.resolvedCard} key={row.key} role="status"><Icon name="check" size={14} /> <b>{decided[row.key]}</b><span>{textOf(b.tool_name ?? b.operation)}</span></div>);
      } else {
        out.push(<ApprovalCard row={row} onDecide={decide} key={row.key} />);
      }
    } else if (row.kind === "ask") {
      out.push(<AskCard row={row} onAnswer={onAnswer} key={row.key} />);
    } else if (row.kind === "plan") {
      out.push(<PlanCard row={row} key={row.key} />);
    } else if (row.kind === "deliverable" || row.kind === "artifact") {
      out.push(<DeliverableCard row={row} key={row.key} />);
    } else if (row.kind === "notice") {
      out.push(<div className={s.notice} key={row.key}><Icon name={/warn|error/i.test(textOf(b.level)) ? "warning" : "info"} size={13} />{textOf(b.text)}</div>);
    } else if (row.kind === "turn_end") {
      // the finish-of-turn summary is rendered once, after the loop
    } else if (textOf(b.text) || textOf(b.content)) {
      out.push(<p className={s.systemLine} key={row.key}>{textOf(b.text ?? b.content)}</p>);
    }
  }
  flushSteps("end");

  if (streaming && streamText) {
    out.push(
      <article className={`${s.bubble} ${s.bubbleAssistant} ${s.streamBubble}`} key="stream" aria-live="polite">
        <header className={s.bubbleHead}><span className={s.role}>{botName}</span><span className={s.streamingLabel}>streaming</span></header>
        <Markdown text={streamText} /><span className={s.caret} aria-hidden="true" />
      </article>,
    );
  }

  if (showSummary && lastEnd) {
    const dur = typeof lastEnd.body.duration_ms === "number" ? formatDuration(lastEnd.body.duration_ms as number) : null;
    out.push(
      <section className={s.summary} key="summary" aria-label="Turn summary">
        <header><Icon name="check" size={14} /><b>Turn complete</b>{dur && <span>{dur}</span>}{textOf(lastEnd.body.terminal_reason) && <Badge tone="neutral">{textOf(lastEnd.body.terminal_reason)}</Badge>}</header>
        {files.length > 0 && (
          <div className={s.summaryBlock}><span className={s.summaryLabel}>Changed files</span><ul>{files.map((f) => <li key={f}><code>{f}</code></li>)}</ul></div>
        )}
        {facts.length > 0 && (
          <div className={s.summaryBlock}><span className={s.summaryLabel}>Usage</span><span>{facts.join(" · ")}</span></div>
        )}
      </section>,
    );
  }

  if (library.length > 0) {
    out.push(
      <section className={s.card} key="library" aria-label="Deliverables from the library">
        <header className={s.cardHead}><Icon name="library" size={16} /><h4>Deliverables</h4></header>
        <ul className={s.fileList}>
          {library.slice(0, 8).map((f) => (
            <li key={f.id}>
              <a href={bridge.downloadUrl(f.id)} className={s.downloadLink} download>
                <Icon name="download" size={14} />{f.name ?? f.id}
                {typeof f.size === "number" && <span className={s.fileSize}>{f.size} B</span>}
              </a>
            </li>
          ))}
        </ul>
      </section>,
    );
  }

  return <div className={s.timeline}>{out}</div>;
}

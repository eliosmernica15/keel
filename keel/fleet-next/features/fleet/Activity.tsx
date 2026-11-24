"use client";

import React, { useCallback, useState } from "react";
import { Badge, Button, IconButton, Textarea } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, BotRow, FleetEvent } from "@/lib/types";
import s from "./fleet.module.css";
import { ActivityBadge, ActivityDot } from "./Bits";
import {
  deriveActivity, delegations, fmtDate, fmtElapsed, number, redact, text, wrapped,
  useBridgeResource, useNow, type DelegationLink,
} from "./support";

const ROW_KINDS = ["step", "approval", "ask", "turn_end", "message", "notice"] as const;

function rowText(row: BotRow): string {
  const b = (row.body ?? {}) as Record<string, unknown>;
  switch (text(row.kind)) {
    case "message":
      return `${text(b.role) === "user" ? "You" : "Agent"}: ${redact(b.content).slice(0, 200)}`;
    case "step":
      return `${text(b.name) || "step"} — ${redact(b.detail || b.status).slice(0, 200)}`;
    case "approval":
      return `${text(b.tool_name || b.tool || "tool")} · ${text(b.status)}${b.scope ? ` · ${redact(b.scope)}` : ""}`;
    case "ask":
      return `Question: ${redact(b.question || b.text).slice(0, 200)}`;
    case "turn_end":
      return `Turn complete · ${number(b.duration_ms, 0)} ms${b.terminal_reason ? ` · ${text(b.terminal_reason)}` : ""}`;
    default:
      return redact(b.text).slice(0, 200);
  }
}

/** Live one-liner, expanded work log, real approvals/questions and delegation. */
export default function ActivityPanel({ bot, bots, events, onOpenBot, onChanged }: {
  bot: Bot;
  bots: Bot[];
  events: FleetEvent[];
  onOpenBot: (id: string) => void;
  onChanged: () => void;
}) {
  const { notify } = useApp();
  const now = useNow();
  const [logOpen, setLogOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"build" | "plan" | "acceptEdits" | "autopilot">("build");
  const [busy, setBusy] = useState(false);

  const rowsResource = useBridgeResource(
    useCallback(() => bridge.botRows(bot.id).then((r) => wrapped<BotRow>(r, "rows")), [bot.id]),
    [bot.id],
  );

  const rows = rowsResource.data ?? [];
  const activity = deriveActivity(rows, events.filter((e) => !e.bot_id || e.bot_id === bot.id), now, text(bot.engine));
  const links: DelegationLink[] = delegations(rows, bots);
  const pendingApprovals = rows.filter((r) => text(r.kind) === "approval" && text((r.body as Record<string, unknown> | undefined)?.status) === "pending");
  const pendingAsks = rows.filter((r) => text(r.kind) === "ask");

  const refresh = useCallback(() => { rowsResource.reload(); onChanged(); }, [rowsResource.reload, onChanged]);

  async function decide(approvalId: string, decision: "once" | "always" | "never") {
    setBusy(true);
    try {
      await bridge.decideApproval(bot.id, approvalId, decision);
      notify(decision === "always" ? "Always allowed — a standing policy was recorded." : decision === "never" ? "Denied — a standing Never policy was recorded." : "Allowed once.", "success");
      refresh();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function answer(askId: string, answerText: string) {
    if (!answerText.trim()) return;
    setBusy(true);
    try {
      await bridge.answerAsk(bot.id, askId, answerText.trim());
      notify("Answer sent to the agent.", "success");
      setDraft("");
      refresh();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  async function send() {
    const content = draft.trim();
    if (!content || busy) return;
    setBusy(true);
    try {
      await bridge.sendMessage(bot.id, { content, mode });
      notify("Message sent to the agent.", "success");
      setDraft("");
      refresh();
    } catch (e) {
      const msg = errMessage(e);
      if (/busy/i.test(msg)) notify("The agent is busy with a current turn — wait for it to finish.", "warning");
      else notify(msg, "error");
    }
    finally { setBusy(false); }
  }

  async function stop() {
    setBusy(true);
    try {
      const res = await bridge.cancel(bot.id) as { cancelled?: boolean };
      notify(res?.cancelled ? "Active turn cancelled." : "No active turn to cancel.", res?.cancelled ? "success" : "info");
      refresh();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className={s.stack}>
      <div className={s.activity}>
        <ActivityDot state={activity.state} />
        <div className={s.grow}>
          <div className={s.activityPhrase}>{activity.phrase}</div>
          {activity.detail && <div className={s.activityDetail}>{activity.detail}</div>}
          <div className={s.row} style={{ marginTop: 6 }}>
            <ActivityBadge state={activity.state} />
            {activity.elapsedMs !== null && <span className={s.activityElapsed}>{fmtElapsed(activity.elapsedMs)}</span>}
            <span className={s.activityElapsed}>last activity {fmtDate(activity.lastAt)}</span>
          </div>
        </div>
        <IconButton label={logOpen ? "Hide work log" : "Show work log"} active={logOpen} onClick={() => setLogOpen((v) => !v)}>
          <Icon name="chevron" size={16} />
        </IconButton>
      </div>

      {pendingApprovals.map((r, i) => {
        const b = (r.body ?? {}) as Record<string, unknown>;
        const id = text(b.approval_id);
        if (!id) return null;
        return (
          <div key={`${id}-${i}`} className={s.item} role="group" aria-label={`Approval request for ${text(b.tool_name || b.tool || "tool")}`}>
            <Icon name="shield" size={18} />
            <div className={s.grow}>
              <div className={s.itemTitle}>Approval needed: {text(b.tool_name || b.tool || "tool")}</div>
              <div className={s.itemMeta}>{redact(b.explanation || b.args_summary || "Operation requires your permission.")}</div>
              {b.scope ? <div className={s.itemMeta}>Scope: {redact(b.scope)}</div> : null}
            </div>
            <div className={s.actions}>
              <Button size="sm" variant="danger" disabled={busy} onClick={() => void decide(id, "never")}>Don&apos;t allow</Button>
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => void decide(id, "once")}>Allow once</Button>
              <Button size="sm" variant="primary" disabled={busy} onClick={() => void decide(id, "always")}>Always allow</Button>
            </div>
          </div>
        );
      })}

      {pendingAsks.map((r, i) => {
        const b = (r.body ?? {}) as Record<string, unknown>;
        const id = text(b.ask_id ?? b.id);
        return (
          <AskRow key={`${id}-${i}`} question={redact(b.question || b.text)} options={Array.isArray(b.options) ? b.options.map((o) => text(o)) : []} disabled={busy} onAnswer={(v) => void answer(id, v)} />
        );
      })}

      {logOpen && (
        <div className={s.log} aria-label="Detailed work log">
          {rows.slice().reverse().filter((r) => (ROW_KINDS as readonly string[]).includes(text(r.kind))).map((r, i) => (
            <div className={s.logRow} key={`${text((r as Record<string, unknown>).created_at)}-${i}`}>
              <span className={s.logKind}>{text(r.kind)}</span>
              <span className={s.logBody}>{rowText(r)}</span>
              <span className={s.logTime}>{fmtDate(text((r as Record<string, unknown>).created_at))}</span>
            </div>
          ))}
          {rows.length === 0 && <div className={s.emptyNote}>No work-log rows reported by the bridge.</div>}
        </div>
      )}

      <div className={s.panel}>
        <div className={s.panelHead}>
          <h4 className={s.panelTitle}>Subagents &amp; delegation</h4>
          <Badge tone="neutral">{links.length} reported</Badge>
        </div>
        {links.length === 0 ? (
          <p className={s.hintNote}>
            The bridge reports delegation links on tool rows only; it does not expose
            <code> parent_id</code> / child-id hierarchy fields. No subagent tree is shown rather than inventing one.
          </p>
        ) : (
          <div className={s.tree}>
            {links.map((l, i) => (
              <div className={s.treeNode} key={`${l.to}-${i}`}>
                <Badge tone={l.ok ? "info" : "danger"} dot>{l.ok ? "delegated" : "delegation failed"}</Badge>
                <span className={s.lineValue}>{l.from} → {l.to}</span>
                {l.detail && <span className={`${s.itemMeta} ${s.truncate}`} title={l.detail}>{l.detail}</span>}
                {l.toId ? (
                  <button className={s.linkBtn} onClick={() => onOpenBot(l.toId as string)}>Open conversation</button>
                ) : (
                  <span className={s.hintNote}>child session not in fleet roster (bridge lists agents only)</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={s.panel}>
        <div className={s.panelHead}>
          <h4 className={s.panelTitle}>Message {bot.name || bot.id}</h4>
          <span className={s.hintNote}>{text(bot.engine) === "echo" ? "Echo engine — scripted replies, not a live model" : "Provider engine"}</span>
        </div>
        <div className={s.composer}>
          <Textarea aria-label="Message" placeholder={`Message ${bot.name || bot.id}…`} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <select aria-label="Permission mode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
            <option value="build">Build</option>
            <option value="plan">Plan</option>
            <option value="acceptEdits">Accept edits</option>
            <option value="autopilot">Autopilot</option>
          </select>
          <Button variant="primary" disabled={!draft.trim() || busy} onClick={() => void send()}><Icon name="send" size={15} /> Send</Button>
          {activity.state === "working" && (
            <Button variant="secondary" disabled={busy} onClick={() => void stop()}><Icon name="stop" size={15} /> Stop</Button>
          )}
        </div>
        {rowsResource.error !== null && <div className={s.errorText}>Could not refresh rows: {errMessage(rowsResource.error)}</div>}
      </div>
    </div>
  );
}

function AskRow({ question, options, disabled, onAnswer }: {
  question: string; options: string[]; disabled: boolean; onAnswer: (v: string) => void;
}) {
  const [value, setValue] = useState("");
  const choices = options.length ? options : [];
  return (
    <div className={s.item} role="group" aria-label="Agent question">
      <Icon name="info" size={18} />
      <div className={s.grow}>
        <div className={s.itemTitle}>The agent is waiting for you</div>
        <div className={s.itemMeta}>{question || "A question was asked."}</div>
      </div>
      <div className={s.actions}>
        {choices.map((c, i) => <Button key={i} size="sm" variant="secondary" disabled={disabled} onClick={() => onAnswer(c)}>{c}</Button>)}
        <input className={s.filtersInput} aria-label="Your answer" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Your answer" />
        <Button size="sm" variant="primary" disabled={disabled || !value.trim()} onClick={() => { onAnswer(value); setValue(""); }}>Answer</Button>
      </div>
    </div>
  );
}

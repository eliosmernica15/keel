"use client";

import React, { useCallback, useMemo, useState } from "react";
import { Badge, Button, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import type { Bot } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import {
  fmtDate, redact, statusTone, text, wrapped,
  useBridgeResource, type AuditEntry, type Resource,
} from "./support";

interface Row extends AuditEntry { agent_id: string; agent_name: string }

export default function Audit({ botsResource }: { botsResource: Resource<Bot[]> }) {
  const bots = botsResource.data ?? [];
  const key = bots.map((b) => b.id).join(",");
  const auditResource = useBridgeResource(
    useCallback(async () => {
      const groups = await Promise.all(bots.map(async (b) => {
        const res = await bridge.botAudit(b.id, 100);
        return wrapped<AuditEntry>(res as Record<string, unknown>, "audit")
          .map((a) => ({ ...a, agent_id: b.id, agent_name: b.name || b.id }));
      }));
      return groups.flat().sort((a, b) => text(b.created_at).localeCompare(text(a.created_at)));
    }, [key]), // eslint-disable-line react-hooks/exhaustive-deps
    [key]);

  const [agent, setAgent] = useState("");
  const [tool, setTool] = useState("");
  const [result, setResult] = useState("all");
  const [date, setDate] = useState("");

  const rows: Row[] = auditResource.data ?? [];
  const filtered = useMemo(() => rows.filter((a) => {
    if (agent && a.agent_id !== agent) return false;
    if (tool && !text(a.tool_name).toLowerCase().includes(tool.toLowerCase())) return false;
    if (date && !text(a.created_at).startsWith(date)) return false;
    if (result !== "all" && text(a.outcome ?? a.decision ?? a.event).toLowerCase() !== result) return false;
    return true;
  }), [rows, agent, tool, date, result]);

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Decision history</h3>
          <p className={s.panelHint}>Audit rows recorded by the bridge: tool, event, permission decision and outcome. Raw tool arguments are never stored in this log; displayed text is redacted defensively.</p>
        </div>
        <Button size="sm" variant="secondary" onClick={auditResource.reload}><Icon name="refresh" size={14} /> Refresh</Button>
      </div>

      <ResourceNotice resource={auditResource} emptyTitle="No decisions recorded" emptyDescription="Permission decisions appear here when an agent requests a tool call." >
        {(data) => (
          <div className={s.stack}>
            <div className={s.filters}>
              <select aria-label="Filter by agent" value={agent} onChange={(e) => setAgent(e.target.value)}>
                <option value="">All agents</option>
                {bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}
              </select>
              <input aria-label="Filter by tool" placeholder="Filter tool…" value={tool} onChange={(e) => setTool(e.target.value)} />
              <select aria-label="Filter by result" value={result} onChange={(e) => setResult(e.target.value)}>
                <option value="all">All results</option>
                <option value="requested">requested</option>
                <option value="decided">decided</option>
                <option value="granted">granted</option>
                <option value="refused">refused</option>
                <option value="executed">executed</option>
                <option value="error">error</option>
                <option value="timeout">timeout</option>
                <option value="policy_revoked">policy revoked</option>
              </select>
              <input aria-label="Filter by date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
              <span className={s.hintNote}>{filtered.length} of {data.length} entries</span>
            </div>
            {filtered.length === 0 ? (
              <EmptyState title="No entries match these filters" description="Try widening the date, tool or result filters." />
            ) : filtered.map((a, i) => {
              const outcome = text(a.outcome ?? a.decision ?? a.event);
              return (
                <div className={s.item} key={`${text(a.id)}-${i}`}>
                  <Icon name="shield" size={16} />
                  <div className={s.grow}>
                    <div className={s.itemTitle}>{redact(a.tool_name)} · {redact(a.event)}</div>
                    <div className={s.itemMeta}>agent {a.agent_name} · {fmtDate(text(a.created_at))}</div>
                    <div className={s.itemMeta}>
                      {a.decision ? `decision ${redact(a.decision)}` : "no decision"}
                      {a.outcome ? ` · outcome ${redact(a.outcome)}` : ""}
                      {a.approval_id ? ` · scope: approval ${redact(a.approval_id)}` : ""}
                    </div>
                    {a.fingerprint && <div className={s.itemMeta}>fingerprint <span className={s.mono}>{redact(a.fingerprint)}</span></div>}
                  </div>
                  <Badge tone={statusTone(outcome)}>{outcome}</Badge>
                </div>
              );
            })}
            {auditResource.error !== null && <div className={s.errorText}>Some agents could not be loaded: {errMessage(auditResource.error)}</div>}
          </div>
        )}
      </ResourceNotice>
    </div>
  );
}

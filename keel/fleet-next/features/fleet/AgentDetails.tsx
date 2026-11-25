"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, Textarea, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, BotRow, FleetEvent, FleetTask } from "@/lib/types";
import s from "./fleet.module.css";
import { Drawer } from "./Bits";
import {
  fmtDate, number, redact, statusTone, text, wrapped,
  useBridgeResource, type AuditEntry, type Policy,
} from "./support";

type Section = "profile" | "engine" | "notes" | "tasks" | "permissions" | "history";
const SECTIONS: Array<{ value: Section; label: string }> = [
  { value: "profile", label: "Studio / Profile" },
  { value: "engine", label: "Engine" },
  { value: "notes", label: "Notes" },
  { value: "tasks", label: "Tasks" },
  { value: "permissions", label: "Permissions" },
  { value: "history", label: "Activity / History" },
];

/** Sequence numbers are the only stable history points the bridge exposes
 *  (`rows.seq` — see db.py); a row without a positive integer seq is not a
 *  usable rewind target and is deliberately not offered. */
function seqOf(row: BotRow): number | null {
  const raw = (row as Record<string, unknown>).seq;
  const n = typeof raw === "number" ? raw : Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

function safeFilename(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
  return cleaned || "transcript";
}

interface Recovery {
  fromSeq: number;
  rows: BotRow[];
  deleted: number;
}
interface TranscriptNotice { tone: "ok" | "error"; text: string }

export default function AgentDetails({ bot, onClose, onChanged }: {
  bot: Bot;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { notify } = useApp();
  const [section, setSection] = useState<Section>("profile");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState(text(bot.name));
  const [role, setRole] = useState(text(bot.role));
  const [hue, setHue] = useState(String(number(bot.avatar_hue, 210)));
  const [provider, setProvider] = useState(text(bot.provider, "auto"));
  const [model, setModel] = useState(text(bot.model));
  const [engine, setEngine] = useState(text(bot.engine, "provider"));
  const [reasoning, setReasoning] = useState(text((bot as Record<string, unknown>).reasoning_effort));
  const [notes, setNotes] = useState(text(bot.notes));

  // Transcript controls. Deleted rows live only in this component's memory:
  // agent data is never persisted by the frontend (UI-ARCHITECTURE §4).
  const [rewindOpen, setRewindOpen] = useState(false);
  const [rewindSeq, setRewindSeq] = useState("");
  const [rewindBusy, setRewindBusy] = useState(false);
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [transcriptNotice, setTranscriptNotice] = useState<TranscriptNotice | null>(null);
  const [exportState, setExportState] = useState<"checking" | "available" | "unavailable">("checking");
  const mutationBusy = useRef(false);

  const tasksResource = useBridgeResource(
    useCallback(() => bridge.tasks().then((r) => wrapped<FleetTask>(r, "tasks")), []), [section === "tasks"],
  );
  const policiesResource = useBridgeResource(
    useCallback(() => bridge.botPolicies(bot.id).then((r) => wrapped<Policy>(r as Record<string, unknown>, "policies")), [bot.id]),
    [bot.id, section === "permissions"],
  );
  const auditResource = useBridgeResource(
    useCallback(() => bridge.botAudit(bot.id, 50).then((r) => wrapped<AuditEntry>(r as Record<string, unknown>, "audit")), [bot.id]),
    [bot.id, section === "history"],
  );
  const rowsResource = useBridgeResource(
    useCallback(() => bridge.botRows(bot.id).then((r) => wrapped<BotRow>(r, "rows")), [bot.id]),
    [bot.id, section === "history"],
  );

  const changed = useCallback(() => { onChanged(); }, [onChanged]);

  /* ------------------------------------------------ transcript: lifecycle */

  // Closing the drawer unmounts this component, which discards the temporary
  // recovery snapshot. Clearing it here as well makes the contract explicit
  // (and also handles a drawer reused for a different agent id).
  const closeDrawer = useCallback(() => {
    setRewindOpen(false);
    setRecovery(null);
    setTranscriptNotice(null);
    onClose();
  }, [onClose]);

  useEffect(() => {
    setRewindOpen(false);
    setRewindSeq("");
    setRecovery(null);
    setTranscriptNotice(null);
    setExportState("checking");
    mutationBusy.current = false;
  }, [bot.id]);

  // The confirmation dialog sits inside the drawer. Drawer's document-capture
  // Escape handler would otherwise close the whole drawer first; a capture
  // listener on `window` runs before it, so Escape cancels only the dialog.
  useEffect(() => {
    if (!rewindOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      if (!mutationBusy.current) { setRewindOpen(false); setTranscriptNotice(null); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [rewindOpen]);

  // Probe the real export route. Only a genuine Markdown attachment from the
  // bridge earns a download link; anything else is reported as unavailable.
  useEffect(() => {
    let alive = true;
    setExportState("checking");
    fetch(bridge.exportUrl(bot.id), { cache: "no-store" })
      .then((resp) => {
        if (!alive) return;
        const ct = (resp.headers.get("content-type") ?? "").toLowerCase();
        const cd = resp.headers.get("content-disposition") ?? "";
        setExportState(resp.ok && ct.includes("text/markdown") && /attachment/i.test(cd)
          ? "available" : "unavailable");
      })
      .catch(() => { if (alive) setExportState("unavailable"); });
    return () => { alive = false; };
  }, [bot.id]);

  const seqRows = useMemo(() => {
    const out: Array<{ seq: number; row: BotRow }> = [];
    for (const row of rowsResource.data ?? []) {
      const seq = seqOf(row);
      if (seq !== null) out.push({ seq, row });
    }
    return out.sort((a, b) => a.seq - b.seq);
  }, [rowsResource.data]);

  const selectedSeq = Number(rewindSeq);
  const validSeq = Number.isInteger(selectedSeq) && selectedSeq > 0 ? selectedSeq : null;
  const rowsToDelete = validSeq === null ? 0 : seqRows.filter(({ seq }) => seq >= validSeq).length;
  const maxSeq = seqRows.length ? seqRows[seqRows.length - 1].seq : 0;

  const openRewind = useCallback(() => {
    // Default to the latest real sequence point: the smallest possible rewind.
    setRewindSeq(seqRows.length ? String(seqRows[seqRows.length - 1].seq) : "");
    setTranscriptNotice(null);
    setRewindOpen(true);
  }, [seqRows]);

  async function confirmRewind() {
    if (mutationBusy.current || validSeq === null) return;
    mutationBusy.current = true;
    setRewindBusy(true);
    setTranscriptNotice(null);
    try {
      // The bridge returns the exact deleted rows: { rows, deleted }.
      const res = await bridge.rewind(bot.id, { from_seq: validSeq }) as { rows?: BotRow[]; deleted?: number };
      const rows = Array.isArray(res?.rows) ? res.rows : [];
      if (rows.length === 0) {
        // No fake success: without rows there is nothing to restore.
        setTranscriptNotice({ tone: "error", text: `The bridge reported no deleted rows from sequence ${validSeq}. Nothing was rewound; there is nothing to restore.` });
      } else {
        const deleted = typeof res?.deleted === "number" ? res.deleted : rows.length;
        setRecovery({ fromSeq: validSeq, rows, deleted });
        setTranscriptNotice({ tone: "ok", text: `Deleted ${deleted} transcript row(s) from sequence ${validSeq}. The deleted rows are held in memory in this drawer and can be restored.` });
      }
      setRewindOpen(false);
      rowsResource.reload();
      changed();
    } catch (e) {
      setTranscriptNotice({ tone: "error", text: `Rewind failed: ${errMessage(e)}` });
    } finally {
      mutationBusy.current = false;
      setRewindBusy(false);
    }
  }

  async function restoreRows() {
    if (mutationBusy.current || !recovery) return;
    mutationBusy.current = true;
    setRestoreBusy(true);
    setTranscriptNotice(null);
    const snapshot = recovery;
    try {
      // Capture the bridge's real count; restore re-appends rows with fresh
      // sequence numbers (db.py: seq INTEGER PRIMARY KEY AUTOINCREMENT).
      const res = await bridge.restore(bot.id, { rows: snapshot.rows }) as { restored?: number };
      const restored = typeof res?.restored === "number" ? res.restored : null;
      setTranscriptNotice({
        tone: "ok",
        text: restored === null
          ? `Restored the transcript rows from sequence ${snapshot.fromSeq}. The bridge re-appends them with new sequence numbers.`
          : `Restored ${restored} transcript row(s) from sequence ${snapshot.fromSeq}. The bridge re-appends them with new sequence numbers.`,
      });
      setRecovery(null);
      rowsResource.reload();
      changed();
    } catch (e) {
      setTranscriptNotice({ tone: "error", text: `Restore failed: ${errMessage(e)}` });
    } finally {
      mutationBusy.current = false;
      setRestoreBusy(false);
    }
  }

  async function save(patch: Record<string, unknown>, label: string) {
    setSaving(true); setSaved(null); setError(null);
    try {
      await bridge.updateBot(bot.id, patch);
      setSaved(`${label} saved.`);
      notify(`${label} saved.`, "success");
      changed();
    } catch (e) { setError(errMessage(e)); notify(errMessage(e), "error"); }
    finally { setSaving(false); }
  }

  async function revoke(toolName: string) {
    setSaving(true); setError(null);
    try {
      await bridge.revokePolicy(bot.id, toolName);
      notify(`Standing permission for ${toolName} revoked.`, "success");
      policiesResource.reload(); changed();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setSaving(false); }
  }

  const assigned = useMemo(
    () => (tasksResource.data ?? []).filter((t) => text(t.assignee) === bot.id || text((t as Record<string, unknown>).assigned_bot_id) === bot.id),
    [tasksResource.data, bot.id],
  );

  return (
    <Drawer
      title={bot.name || bot.id}
      subtitle={<span className={s.muted}>Agent id <span className={s.mono}>{bot.id}</span> · {text(bot.engine) === "echo" ? "scripted Echo engine" : "provider engine"}</span>}
      onClose={closeDrawer}
      tabs={SECTIONS}
      active={section}
      onTab={(v) => { setSection(v as Section); setSaved(null); setError(null); }}
    >
      {(saved || error) && <div className={error ? s.errorText : s.okText} role="status">{error || saved}</div>}

      {section === "profile" && (
        <div className={s.stack}>
          <p className={s.hintNote}>Identity shown across Fleet. Stored locally by the Python bridge via <code>updateBot</code>.</p>
          <div className={s.fieldGrid}>
            <div className={s.field}><label htmlFor="agent-name">Name</label><input id="agent-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} /></div>
            <div className={s.field}><label htmlFor="agent-role">Role</label><input id="agent-role" value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} placeholder="generalist" /></div>
            <div className={s.field}><label htmlFor="agent-hue">Avatar hue (0–359)</label><input id="agent-hue" type="number" min={0} max={359} value={hue} onChange={(e) => setHue(e.target.value)} /></div>
          </div>
          <div><Button variant="primary" loading={saving} disabled={!name.trim()} onClick={() => void save({ name: name.trim(), role: role.trim(), avatar_hue: number(hue, 210) }, "Profile")}>Save profile</Button></div>
        </div>
      )}

      {section === "engine" && (
        <div className={s.stack}>
          <p className={s.hintNote}>Provider keys are never shown or stored by this UI. Session keys live only in the bridge process; <code>auto</code> means a configured provider is selected at run time.</p>
          <div className={s.fieldGrid}>
            <div className={s.field}>
              <label htmlFor="agent-engine">Engine</label>
              <select id="agent-engine" value={engine} onChange={(e) => setEngine(e.target.value)}>
                <option value="provider">Provider (live model)</option>
                <option value="echo">Echo (scripted/test)</option>
              </select>
            </div>
            <div className={s.field}><label htmlFor="agent-provider">Provider</label><input id="agent-provider" value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="auto" /></div>
            <div className={s.field}><label htmlFor="agent-model">Model</label><input id="agent-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="model id" /></div>
            <div className={s.field}>
              <label htmlFor="agent-reasoning">Reasoning effort</label>
              <select id="agent-reasoning" value={reasoning} onChange={(e) => setReasoning(e.target.value)}>
                <option value="">auto (not set)</option>
                {["minimal", "none", "low", "medium", "high", "xhigh", "max"].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </div>
          </div>
          <div><Button variant="primary" loading={saving} onClick={() => void save({ engine, provider: provider.trim() || "auto", model: model.trim(), reasoning_effort: reasoning.trim() }, "Engine")}>Save engine</Button></div>
        </div>
      )}

      {section === "notes" && (
        <div className={s.stack}>
          <p className={s.hintNote}>Free-form operator notes. Treated as text, never executed.</p>
          <Textarea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4096} />
          <div><Button variant="primary" loading={saving} onClick={() => void save({ notes }, "Notes")}>Save notes</Button></div>
        </div>
      )}

      {section === "tasks" && (
        <div className={s.stack}>
          <div className={s.panelHead}>
            <h4 className={s.panelTitle}>Tasks assigned to this agent</h4>
            <Badge tone="neutral">{assigned.length}</Badge>
          </div>
          {tasksResource.error ? <div className={s.errorText}>{errMessage(tasksResource.error)}</div> : null}
          {assigned.length === 0 ? (
            <EmptyState title="No assigned tasks" description="Assign a task from the Fleet Tasks tab. Assignments are recorded by the bridge." />
          ) : assigned.map((t) => (
            <div className={s.item} key={t.id}>
              <div className={s.grow}>
                <div className={s.itemTitle}>{text(t.title) || t.id}</div>
                <div className={s.itemMeta}>{text(t.status)} · {text(t.priority)} · {number(t.progress, 0)}%</div>
              </div>
              <Badge tone={statusTone(text(t.status))}>{text(t.status)}</Badge>
            </div>
          ))}
        </div>
      )}

      {section === "permissions" && (
        <div className={s.stack}>
          <p className={s.hintNote}>
            Standing permissions are created when you choose “Always allow” or “Don&apos;t allow” on a live approval card.
            The bridge enforces them; this view lists and revokes what it actually stores.
          </p>
          <div className={s.panelHead}><h4 className={s.panelTitle}>Standing policies</h4><IconButton label="Refresh policies" onClick={policiesResource.reload}><Icon name="refresh" size={15} /></IconButton></div>
          {policiesResource.error ? <div className={s.errorText}>{errMessage(policiesResource.error)}</div> : null}
          {(policiesResource.data ?? []).length === 0 ? (
            <EmptyState title="No standing policies" description="This agent has no always/never rules recorded by the bridge." />
          ) : (policiesResource.data ?? []).map((p) => (
            <div className={s.item} key={`${text(p.tool_name)}-${text(p.updated_at)}`}>
              <Icon name="shield" size={16} />
              <div className={s.grow}>
                <div className={s.itemTitle}>{text(p.tool_name)}</div>
                <div className={s.itemMeta}>Updated {fmtDate(text(p.updated_at) || text(p.created_at))}</div>
              </div>
              <Badge tone={text(p.decision) === "always" ? "success" : "danger"}>{text(p.decision)}</Badge>
              <Button size="sm" variant="ghost" disabled={saving} onClick={() => void revoke(text(p.tool_name))}>Revoke</Button>
            </div>
          ))}
        </div>
      )}

      {section === "history" && (
        <HistorySection
          botId={bot.id}
          botName={text(bot.name) || bot.id}
          auditResource={auditResource}
          rowsResource={rowsResource}
          seqRows={seqRows}
          exportState={exportState}
          recovery={recovery}
          notice={transcriptNotice}
          rewindBusy={rewindBusy}
          restoreBusy={restoreBusy}
          onOpenRewind={openRewind}
          onRestore={() => void restoreRows()}
          onDismissRecovery={() => { setRecovery(null); setTranscriptNotice(null); }}
        />
      )}

      <Dialog
        open={rewindOpen}
        onClose={() => { if (!mutationBusy.current) { setRewindOpen(false); setTranscriptNotice(null); } }}
        title="Rewind transcript?"
        footer={<>
          <Button variant="ghost" disabled={rewindBusy} onClick={() => { setRewindOpen(false); setTranscriptNotice(null); }}>Cancel</Button>
          <Button variant="danger" loading={rewindBusy} disabled={validSeq === null} onClick={() => void confirmRewind()}>
            {validSeq === null ? "Delete rows" : `Delete rows from seq ${validSeq}`}
          </Button>
        </>}
      >
        <p className={s.hintNote}>
          This sends <code>{'{ from_seq: N }'}</code> to the bridge. Every transcript row with sequence number <strong>N or higher</strong> is deleted. The bridge returns the deleted rows; they are kept only in this open drawer so you can restore them.
        </p>
        {seqRows.length === 0 ? (
          <div className={s.errorText} role="status">No sequence-numbered rows were reported by the bridge. Nothing can be rewound.</div>
        ) : (
          <>
            <div className={s.field}>
              <label htmlFor="rewind-seq">Rewind from sequence</label>
              <select id="rewind-seq" value={rewindSeq} disabled={rewindBusy} onChange={(e) => setRewindSeq(e.target.value)}>
                {seqRows.map(({ seq, row }) => (
                  <option key={seq} value={seq}>
                    {seq} · {text(row.kind)} · {fmtDate(text((row as Record<string, unknown>).created_at ?? row.ts))}
                  </option>
                ))}
              </select>
            </div>
            <p className={s.itemMeta} role="status">
              Exact history point: sequence <span className={s.mono}>{validSeq ?? "—"}</span>
              {" · "}{rowsToDelete} row(s) deleted (seq {validSeq ?? "—"}–{maxSeq}).
            </p>
          </>
        )}
        {transcriptNotice && (
          <div className={transcriptNotice.tone === "error" ? s.errorText : s.okText}
            role={transcriptNotice.tone === "error" ? "alert" : "status"}>
            {transcriptNotice.text}
          </div>
        )}
      </Dialog>
    </Drawer>
  );
}

interface TinyResource<T> { data: T | null; error: unknown; loading: boolean; reload: () => void }
function HistorySection({ botId, botName, auditResource, rowsResource, seqRows, exportState, recovery, notice, rewindBusy, restoreBusy, onOpenRewind, onRestore, onDismissRecovery }: {
  botId: string;
  botName: string;
  auditResource: TinyResource<AuditEntry[]>;
  rowsResource: TinyResource<BotRow[]>;
  seqRows: Array<{ seq: number; row: BotRow }>;
  exportState: "checking" | "available" | "unavailable";
  recovery: Recovery | null;
  notice: TranscriptNotice | null;
  rewindBusy: boolean;
  restoreBusy: boolean;
  onOpenRewind: () => void;
  onRestore: () => void;
  onDismissRecovery: () => void;
}) {
  const [tool, setTool] = useState("");
  const [result, setResult] = useState("all");
  const [date, setDate] = useState("");
  const audits = auditResource.data ?? [];
  const filtered = audits.filter((a) => {
    if (tool && !text(a.tool_name).toLowerCase().includes(tool.toLowerCase())) return false;
    if (result !== "all" && ![a.event, a.decision, a.outcome].some((v) => text(v).toLowerCase() === result)) return false;
    if (date && !text(a.created_at).startsWith(date)) return false;
    return true;
  });
  return (
    <div className={s.stack}>
      {/* Transcript export + guarded rewind/restore. Every value here comes
          from the bridge; no success is shown until the bridge responds. */}
      <div className={s.stack}>
        <div className={s.panelHead}>
          <h4 className={s.panelTitle}>Transcript</h4>
          <Badge tone="neutral">{(rowsResource.data ?? []).length} rows</Badge>
        </div>
        <p className={s.hintNote}>
          The bridge exports the full transcript as Markdown. Rewind deletes every row from a chosen sequence onward; the deleted rows can be restored only while this drawer stays open.
        </p>
        {exportState === "checking" ? (
          <div className={s.itemMeta} role="status">Checking Markdown export…</div>
        ) : exportState === "available" ? (
          <div>
            <a
              className={s.linkBtn}
              href={bridge.exportUrl(botId)}
              download={`${safeFilename(botName)}.md`}
              aria-label="Download Markdown transcript"
            >Download Markdown transcript (.md)</a>
          </div>
        ) : (
          <div className={s.errorText} role="status">Markdown export unavailable — the bridge did not return a downloadable file. No download link is shown.</div>
        )}
        {notice && (
          <div className={notice.tone === "error" ? s.errorText : s.okText}
            role={notice.tone === "error" ? "alert" : "status"}>
            {notice.text}
          </div>
        )}
        {recovery ? (
          <div className={s.item} role="status">
            <Icon name="info" size={16} />
            <div className={s.grow}>
              <div className={s.itemTitle}>Rewound from sequence {recovery.fromSeq} · {recovery.deleted} row(s) deleted</div>
              <div className={s.itemMeta}>The deleted rows are held in memory in this drawer. Restore re-appends them with new sequence numbers assigned by the bridge.</div>
            </div>
            <Button size="sm" variant="secondary" loading={restoreBusy} disabled={rewindBusy} onClick={onRestore}>Restore rows</Button>
            <IconButton label="Dismiss recovery" disabled={rewindBusy || restoreBusy} onClick={onDismissRecovery}><Icon name="close" size={14} /></IconButton>
          </div>
        ) : (
          <div>
            <Button size="sm" variant="secondary" disabled={seqRows.length === 0 || rewindBusy || restoreBusy} onClick={onOpenRewind}>Rewind transcript…</Button>
            {seqRows.length === 0 && <div className={s.itemMeta}>No sequence-numbered rows reported by the bridge; rewind is unavailable.</div>}
          </div>
        )}
      </div>

      <div className={s.panelHead}><h4 className={s.panelTitle}>Permission decisions &amp; audit</h4><Badge tone="neutral">{filtered.length}</Badge></div>
      <p className={s.hintNote}>Audit rows contain a tool name, event, decision and a fingerprint — never raw arguments or secrets. Row contents below are redacted defensively.</p>
      <div className={s.filters}>
        <input aria-label="Filter by tool" placeholder="Filter tool…" value={tool} onChange={(e) => setTool(e.target.value)} />
        <select aria-label="Filter by result" value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="all">All results</option>
          <option value="requested">requested</option>
          <option value="decided">decided</option>
          <option value="outcome">outcome</option>
          <option value="policy_revoked">policy_revoked</option>
          <option value="granted">granted</option>
          <option value="refused">refused</option>
          <option value="executed">executed</option>
          <option value="error">error</option>
          <option value="timeout">timeout</option>
          <option value="delegate">delegate</option>
        </select>
        <input aria-label="Filter by date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      {auditResource.error ? <div className={s.errorText}>{errMessage(auditResource.error)}</div> : null}
      {filtered.length === 0 ? (
        <EmptyState title="No matching decisions" description="No audit rows match these filters. Decisions appear here as the bridge records them." />
      ) : filtered.map((a, i) => (
        <div className={s.item} key={`${text(a.id)}-${i}`}>
          <div className={s.grow}>
            <div className={s.itemTitle}>{redact(a.tool_name)} · {redact(a.event)}</div>
            <div className={s.itemMeta}>
              {a.decision ? `decision ${redact(a.decision)}` : "no decision"} {a.outcome ? `· outcome ${redact(a.outcome)}` : ""} · {fmtDate(text(a.created_at))}
            </div>
            {a.approval_id && <div className={s.itemMeta}>scope: approval {redact(a.approval_id)}</div>}
            {a.fingerprint && <div className={s.itemMeta}>fingerprint <span className={s.mono}>{redact(a.fingerprint)}</span></div>}
          </div>
          <Badge tone={statusTone(text(a.outcome ?? a.decision))}>{text(a.outcome ?? a.decision ?? a.event)}</Badge>
        </div>
      ))}
      <div className={s.panelHead} style={{ marginTop: 10 }}><h4 className={s.panelTitle}>Recent work-log rows</h4><Badge tone="neutral">{(rowsResource.data ?? []).length}</Badge></div>
      {(rowsResource.data ?? []).slice(-12).reverse().map((r, i) => {
        const b = (r.body ?? {}) as Record<string, unknown>;
        return (
          <div className={s.item} key={`${text((r as Record<string, unknown>).created_at)}-${i}`}>
            <div className={s.grow}>
              <div className={s.itemTitle}>{text(r.kind)}</div>
              <div className={s.itemMeta}>{redact(b.text || b.detail || b.content || b.tool_name || b.name || "")}</div>
            </div>
            <span className={s.itemMeta}>{fmtDate(text((r as Record<string, unknown>).created_at))}</span>
          </div>
        );
      })}
      {(rowsResource.data ?? []).length === 0 && <div className={s.emptyNote}>No work-log rows reported by the bridge.</div>}
    </div>
  );
}

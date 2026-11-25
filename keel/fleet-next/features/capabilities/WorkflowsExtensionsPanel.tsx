"use client";

// Workflows are discoverable and runnable through real bridge routes. This is
// a runner, not a builder: the bridge reports a step count and execution
// results, not editable node schemas. The marketplace tab is intentionally an
// explicit unavailable state.

import React, { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import s from "./capabilities.module.css";
import { asArray, PanelState, readRecord, safeResult, useBridgeData } from "./capabilitiesShared";

interface WorkflowRow {
  name?: string;
  description?: string;
  source?: string;
  steps?: number;
  [key: string]: unknown;
}
interface RunResult { ok: boolean; name: string; results: unknown[] }

export function WorkflowsPanel() {
  const workflowsQ = useBridgeData(() => bridge.workflows());
  const [target, setTarget] = useState<WorkflowRow | null>(null);
  const [projectRoot, setProjectRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunResult | null>(null);

  async function execute() {
    if (!target?.name) return;
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      const payload: Record<string, unknown> = { name: target.name };
      if (projectRoot.trim()) payload.project_root = projectRoot.trim();
      const body = readRecord(await bridge.executeWorkflow(payload));
      if (typeof body.error === "string") { setError(body.error); return; }
      setRun({
        ok: body.ok === true,
        name: String(body.name ?? target.name),
        results: Array.isArray(body.results) ? body.results : [],
      });
      setTarget(null);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Workflows</h2>
          <p className={s.muted}>A runner, not a builder: the bridge exposes discovery and guarded execution, but no node-schema, versioning or dry-run API for a visual editor.</p>
        </div>
        <Button onClick={workflowsQ.reload}><Icon name="refresh" size={14} /> Reload</Button>
      </div>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="info" size={16} /> How execution is gated</div>
        <p>The bridge runs workflows non-interactively: every tool step must pass Keel's Tier-1 gate, and Tier-2 rules stay inside the runtime's tool executor. A refused step fails the run — the UI shows the real per-step results.</p>
      </Card>

      {error && <p className={s.error} role="alert">Run failed: {error}</p>}
      {run && (
        <Card className={run.ok ? s.resultOk : s.resultFail}>
          <strong>{run.ok ? `${run.name}: all reported steps succeeded` : `${run.name}: at least one step failed`}</strong>
          <ol className={s.stepResults}>
            {run.results.length === 0 && <li className={s.muted}>The bridge returned no step results.</li>}
            {run.results.map((item, i) => {
              const rec = readRecord(item);
              const ok = rec.ok === true;
              return (
                <li key={i}>
                  <Badge tone={ok ? "success" : "danger"} dot>{ok ? "OK" : "Failed"}</Badge>
                  <span className={s.mono}>Step {i + 1}</span>
                  <pre className={s.pre}>{safeResult(rec.detail ?? rec.error ?? rec.result ?? rec, 800)}</pre>
                </li>
              );
            })}
          </ol>
        </Card>
      )}

      <PanelState query={workflowsQ}>
        {(data) => {
          const workflows = asArray<WorkflowRow>(data, "workflows");
          return workflows.length === 0 ? (
            <EmptyState icon={<Icon name="routine" />} title="No workflows discovered"
              description="Keel found no workflow definitions in the bundled or user folders." />
          ) : (
            <ul className={s.list}>
              {workflows.map((wf, i) => (
                <li className={s.row} key={String(wf.name ?? i)}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h3 className={s.rowTitle}>{wf.name ?? "Unnamed workflow"}</h3>
                      <Badge tone="neutral">{typeof wf.steps === "number" ? `${wf.steps} step${wf.steps === 1 ? "" : "s"}` : "step count not reported"}</Badge>
                      {wf.source && <Badge tone="neutral">{wf.source}</Badge>}
                    </div>
                    <p className={s.rowDesc}>{wf.description ?? "No description reported by the bridge."}</p>
                    <p className={s.rowMeta}>The bridge reports a step count, not the individual step definitions. Run it to see real per-step outcomes.</p>
                  </div>
                  <div className={s.rowActions}>
                    <Button size="sm" onClick={() => { setTarget(wf); setError(null); }}><Icon name="play" size={13} /> Run…</Button>
                  </div>
                </li>
              ))}
            </ul>
          );
        }}
      </PanelState>

      <Dialog open={target !== null} onClose={() => setTarget(null)} title={`Run workflow: ${target?.name ?? ""}`}
        footer={<>
          <Button variant="ghost" onClick={() => setTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => { void execute(); }}>Run workflow</Button>
        </>}>
        <p className={s.muted}>This executes real, guarded tool steps on this machine. Results and refusals will be shown exactly as the bridge reports them.</p>
        <TextFieldProjectRoot value={projectRoot} onChange={setProjectRoot} />
      </Dialog>
    </div>
  );
}

function TextFieldProjectRoot({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className={s.selectLabel}>Project root (optional)
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="Absolute path, or leave empty for the bridge default" />
    </label>
  );
}

export function ExtensionsPanel() {
  return (
    <div className={s.panel}>
      <div className={s.sectionHead}><div><h2>Extensions &amp; plugins</h2></div></div>
      <EmptyState
        icon={<Icon name="capabilities" size={26} />}
        title="Extension marketplace is not available in this build"
        description="There is no plugin marketplace or extension install API in this bridge build, so no install controls are shown. Keel's extension points today are Skills and MCP connectors — use those tabs for real, bridge-backed management."
        action={<span className={s.badgeRow}><Badge tone="neutral">Skills ✓</Badge><Badge tone="neutral">MCP connectors ✓</Badge><Badge tone="neutral">Marketplace — not available</Badge></span>}
      />
    </div>
  );
}

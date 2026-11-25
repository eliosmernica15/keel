"use client";

// Privacy/data and diagnostics. Usage numbers and health checks are read from
// real bridge routes; anything the bridge does not report is stated plainly.

import React, { useState } from "react";
import { Badge, Button, Card, EmptyState, SectionTitle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { api, bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import s from "./settings.module.css";
import { PanelState, readRecord, useBridgeData } from "./settingsShared";

const USAGE_LABELS: Record<string, string> = {
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  cache_read_input_tokens: "Cache-read input tokens",
  cache_creation_input_tokens: "Cache-creation input tokens",
  tokens: "Tokens",
  cost: "Cost",
  requests: "Requests",
};

export function PrivacyPanel() {
  const usageQ = useBridgeData(() => bridge.usage());

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Privacy &amp; data</h2>
          <p className={s.muted}>Keel is local-first: Keel owns transcripts and usage on this machine. Only data the bridge reports is shown.</p>
        </div>
        <Button onClick={usageQ.reload}><Icon name="refresh" size={14} /> Reload</Button>
      </div>

      <PanelState query={usageQ}>
        {(data) => {
          const root = readRecord(data);
          const usage = readRecord(root.usage ?? data);
          const entries = Object.entries(usage).filter(([, value]) => typeof value === "number" && Number.isFinite(value));
          return (
            <Card className={s.usageCard}>
              <SectionTitle>Usage reported by the bridge</SectionTitle>
              {entries.length === 0 ? (
                <EmptyState icon={<Icon name="info" />} title="No usage counters reported" description="The bridge returned no numeric usage fields." />
              ) : (
                <dl className={s.usageGrid}>
                  {entries.map(([key, value]) => (
                    <div key={key}>
                      <dt>{USAGE_LABELS[key] ?? key}</dt>
                      <dd>{typeof value === "number" ? value.toLocaleString() : "—"}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className={s.muted}>These are approximate totals across finished turns on this install, not a per-project bill. Cost is shown only if the bridge reports it.</p>
            </Card>
          );
        }}
      </PanelState>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="shield" size={16} /> Storage, retention and export</div>
        <p>Transcripts and agent state are kept locally by the bridge. This build exposes no routes for retention policy, transcript cleanup, export/import or a diagnostics cleanup bundle, so no controls are rendered here. Provider keys are covered on the Credentials page.</p>
      </Card>
    </div>
  );
}

interface HealthState {
  ok: boolean;
  message: string;
  unavailable: boolean;
  servers: Record<string, boolean>;
}

export function DiagnosticsPanel() {
  const [state, setState] = useState<HealthState | null>(null);
  const [busy, setBusy] = useState(false);

  async function probe() {
    setBusy(true);
    try {
      // A real bridge call through the same-origin BFF; no invented health URL.
      const body = readRecord(await api("mcp/health", { method: "POST", body: "{}" }));
      if (typeof body.error === "string") {
        setState({ ok: false, message: body.error, unavailable: false, servers: {} });
        return;
      }
      const raw = body.health;
      const servers: Record<string, boolean> = {};
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        for (const [name, value] of Object.entries(raw as Record<string, unknown>)) {
          if (typeof value === "boolean") servers[name] = value;
          else if (value && typeof value === "object" && typeof (value as Record<string, unknown>).ok === "boolean") {
            servers[name] = Boolean((value as Record<string, unknown>).ok);
          }
        }
      } else if (Array.isArray(raw)) {
        for (const item of raw) {
          const rec = readRecord(item);
          if (typeof rec.name === "string") servers[rec.name] = Boolean(rec.ok ?? rec.healthy);
        }
      }
      setState({ ok: true, message: "The bridge answered a real /mcp/health probe.", unavailable: false, servers });
    } catch (err) {
      setState({ ok: false, message: errMessage(err), unavailable: isBridgeUnavailable(err), servers: {} });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>System diagnostics</h2>
          <p className={s.muted}>An actual request is made to the local bridge. Nothing here is a simulated green indicator.</p>
        </div>
        <Button onClick={() => { void probe(); }} loading={busy}><Icon name="play" size={14} /> Probe bridge</Button>
      </div>

      {state ? (
        <Card className={state.ok ? s.resultOk : s.resultFail}>
          <div className={s.rowTitleLine}>
            <Badge tone={state.ok ? "success" : state.unavailable ? "warning" : "danger"} dot>{state.ok ? "Bridge responded" : state.unavailable ? "Bridge unavailable" : "Probe failed"}</Badge>
          </div>
          <p className={s.rowMeta}>{state.message}</p>
          {Object.keys(state.servers).length > 0 && (
            <ul className={s.healthList}>
              {Object.entries(state.servers).map(([name, ok]) => (
                <li key={name}><Badge tone={ok ? "success" : "danger"} dot>{ok ? "Healthy" : "Unhealthy"}</Badge><code className={s.code}>{name}</code></li>
              ))}
            </ul>
          )}
          <p className={s.muted}>The MCP health route briefly starts configured servers, checks them and shuts them down again.</p>
        </Card>
      ) : (
        <EmptyState icon={<Icon name="info" />} title="No probe run yet" description="Press “Probe bridge” to make a real health request and see its outcome." />
      )}

      <SectionTitle>Not exposed by this bridge build</SectionTitle>
      <ul className={s.factList}>
        <li><strong>Version / build information</strong> — no route reports it here.</li>
        <li><strong>Startup checks and state</strong> — no route reports them here.</li>
        <li><strong>Redacted diagnostics bundle</strong> — no export route exists in this bridge client.</li>
        <li><strong>Resource budgets and background jobs</strong> — not available through this bridge contract.</li>
      </ul>
    </div>
  );
}

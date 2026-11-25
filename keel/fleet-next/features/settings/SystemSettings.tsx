"use client";

// Privacy/data, diagnostics and updates. Usage numbers and health checks are
// read from real bridge routes; anything the bridge does not report is stated
// plainly. Every section renders as a card (title, description, controls).

import React, { useState } from "react";
import { Badge, Button, Card, EmptyState } from "@/components/ui";
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

function sectionHead(title: string, description: string, action?: React.ReactNode) {
  return (
    <div className={s.sectionHeader}>
      <div>
        <h2 className={s.sectionTitle}>{title}</h2>
        <p className={s.muted}>{description}</p>
      </div>
      {action}
    </div>
  );
}

export function PrivacyPanel() {
  const usageQ = useBridgeData(() => bridge.usage());

  return (
    <>
      {sectionHead("Privacy & data", "Keel is local-first: Keel owns transcripts and usage on this machine. Only data the bridge reports is shown.", <Button onClick={usageQ.reload}><Icon name="refresh" size={14} /> Reload</Button>)}
      <PanelState query={usageQ}>
        {(data) => {
          const root = readRecord(data);
          const usage = readRecord(root.usage ?? data);
          const entries = Object.entries(usage).filter(([, value]) => typeof value === "number" && Number.isFinite(value));
          return (
            <Card className={s.settingCard}>
              <div className={s.settingHead}>
                <h3 className={s.cardTitle}>Usage reported by the bridge</h3>
              </div>
              {entries.length === 0 ? (
                <EmptyState icon={<Icon name="info" />} title="No usage counters reported" description="The bridge returned no numeric usage fields." />
              ) : (
                <dl className={s.usageGrid}>
                  {entries.map(([key, value]) => (
                    <div key={key}>
                      <dt>{USAGE_LABELS[key] ?? key}</dt>
                      <dd className={s.mono}>{typeof value === "number" ? value.toLocaleString() : "—"}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className={s.muted}>These are approximate totals across finished turns on this install, not a per-project bill. Cost is shown only if the bridge reports it.</p>
            </Card>
          );
        }}
      </PanelState>
      <Card className={s.settingCard}>
        <div className={s.settingHead}>
          <h3 className={s.cardTitle}>Storage, retention and export</h3>
        </div>
        <p>Transcripts and agent state are kept locally by the bridge. This build exposes no routes for retention policy, transcript cleanup, export/import or a diagnostics cleanup bundle, so no controls are rendered here. Provider keys are covered on the Credentials page.</p>
      </Card>
    </>
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
    <>
      {sectionHead("System diagnostics", "An actual request is made to the local bridge. Nothing here is a simulated green indicator.", <Button onClick={() => { void probe(); }} loading={busy}><Icon name="play" size={14} /> Probe bridge</Button>)}
      {state ? (
        <Card className={s.settingCard}>
          <div className={s.settingHead}>
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
      <div className={s.sectionHeader}>
        <h2 className={s.sectionTitle}>Not exposed by this bridge build</h2>
      </div>
      <ul className={s.factList}>
        <li><strong>Version / build information</strong> — no route reports it here.</li>
        <li><strong>Startup checks and state</strong> — no route reports them here.</li>
        <li><strong>Redacted diagnostics bundle</strong> — no export route exists in this bridge client.</li>
        <li><strong>Resource budgets and background jobs</strong> — not available through this bridge contract.</li>
      </ul>
    </>
  );
}

export function UpdatesPanel() {
  const [status, setStatus] = useState<"idle" | "checking" | "up-to-date" | "available" | "error">("idle");
  const [latest, setLatest] = useState<{ tag: string; url: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setStatus("checking");
    setError(null);
    try {
      const res = await fetch("https://api.github.com/repos/eliosmernica15/keel/releases/latest", {
        headers: { Accept: "application/vnd.github+json" },
      });
      if (!res.ok) throw new Error(`GitHub returned ${res.status}`);
      const data = await res.json();
      const current = "0.1.1";
      const latestTag = String(data.tag_name || "").replace(/^v/, "");
      if (latestTag && latestTag !== current) {
        const asset = Array.isArray(data.assets)
          ? data.assets.find((a: { name?: string }) => /Keel-Setup.*\.exe$/i.test(String(a?.name || "")))
          : null;
        setLatest({
          tag: latestTag,
          url: asset?.browser_download_url || data.html_url || "https://github.com/eliosmernica15/keel/releases/latest",
          name: asset?.name || "Keel installer",
        });
        setStatus("available");
      } else {
        setStatus("up-to-date");
      }
    } catch (e) {
      setError(errMessage(e));
      setStatus("error");
    }
  }

  return (
    <>
      {sectionHead("Updates", "Check for new Keel releases and download them directly.", <Button onClick={check} disabled={status === "checking"}> <Icon name="refresh" size={14} /> {status === "checking" ? "Checking…" : "Check for updates"}</Button>)}
      {status === "up-to-date" && (
        <Card className={s.settingCard}>
          <div className={s.settingHead}>
            <div className={s.noteTitle}><Icon name="check" size={16} /> Up to date</div>
          </div>
          <p>You are running the latest version of Keel.</p>
        </Card>
      )}
      {status === "available" && latest && (
        <Card className={s.settingCard}>
          <div className={s.settingHead}>
            <div className={s.noteTitle}><Icon name="download" size={16} /> Update available: v{latest.tag}</div>
          </div>
          <p>A new version of Keel is available. Download the installer and run it to update.</p>
          <a className={s.exportLink} href={latest.url} target="_blank" rel="noopener noreferrer">
            <Icon name="download" size={15} /> <span>Download {latest.name}</span>
          </a>
        </Card>
      )}
      {status === "error" && (
        <Card className={s.settingCard}>
          <div className={s.settingHead}>
            <div className={s.noteTitle}><Icon name="info" size={16} /> Could not check for updates</div>
          </div>
          <p>{error}</p>
        </Card>
      )}
    </>
  );
}

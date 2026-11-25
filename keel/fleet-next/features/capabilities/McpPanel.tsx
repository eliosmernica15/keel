"use client";

// MCP servers and Connectors. Both are real bridge routes; connection state is
// only ever reported after a real `mcpHealth` / `connectorsTest` response.

import React, { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, IconButton, SectionTitle, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { CapabilityState } from "@/lib/types";
import s from "./capabilities.module.css";
import { asArray, PanelState, readRecord, safeResult, StateBadge, useBridgeData } from "./capabilitiesShared";

interface ServerRow {
  name?: string;
  transport?: string;
  scope?: string;
  command?: string;
  url?: string;
  [key: string]: unknown;
}
interface ConnectorRow {
  name?: string;
  command?: string;
  args?: string[];
  env_keys?: string[];
  type?: string;
  transport?: string;
  enabled?: boolean;
  error?: string;
  last_error?: string;
  logs?: unknown;
  tools?: unknown[];
  resources?: unknown[];
  prompts?: unknown[];
  [key: string]: unknown;
}
interface PresetRow {
  name?: string;
  label?: string;
  description?: string;
  command?: string;
  [key: string]: unknown;
}
type TestResult =
  | { state: "testing" }
  | { state: "ok"; tool_count?: number; tools?: Array<{ name?: string; description?: string }>; resources?: unknown[]; prompts?: unknown[] }
  | { state: "fail"; error: string };

function healthMap(value: unknown): Record<string, boolean> {
  if (Array.isArray(value)) {
    const out: Record<string, boolean> = {};
    for (const entry of value) {
      const rec = readRecord(entry);
      const name = rec.name ?? rec.server;
      if (typeof name === "string") out[name] = Boolean(rec.ok ?? rec.healthy ?? rec.health);
    }
    return out;
  }
  const rec = readRecord(value);
  const out: Record<string, boolean> = {};
  for (const [key, val] of Object.entries(rec)) {
    if (typeof val === "boolean") out[key] = val;
    else {
      const nested = readRecord(val);
      if (typeof nested.ok === "boolean") out[key] = nested.ok;
    }
  }
  return out;
}

export function McpPanel() {
  const serversQ = useBridgeData(() => bridge.mcpServers());
  const [health, setHealth] = useState<Record<string, boolean> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runHealth() {
    setBusy(true);
    setError(null);
    try {
      const body = readRecord(await bridge.mcpHealth());
      if (typeof body.error === "string") { setError(body.error); return; }
      setHealth(healthMap(body.health));
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
          <h2>MCP servers</h2>
          <p className={s.muted}>Servers come from Keel settings. Health is only shown after a real bridge probe (the bridge starts, checks and stops each server).</p>
        </div>
        <div className={s.actionRow}>
          <Button onClick={() => { void runHealth(); }} loading={busy}><Icon name="play" size={14} /> Run health check</Button>
          <IconButton label="Reload MCP servers" onClick={serversQ.reload}><Icon name="refresh" size={15} /></IconButton>
        </div>
      </div>
      {error && <p className={s.error} role="alert">Health check failed: {error}</p>}
      <PanelState query={serversQ}>
        {(data) => {
          const servers = asArray<ServerRow>(data, "servers");
          return servers.length === 0 ? (
            <EmptyState icon={<Icon name="link" />} title="No MCP servers configured"
              description="Add one from the Connectors tab. Keel speaks MCP over stdio/HTTP; nothing connects until you configure it." />
          ) : (
            <ul className={s.list}>
              {servers.map((server, i) => {
                const checked = health !== null && Object.prototype.hasOwnProperty.call(health, String(server.name));
                const ok = checked ? health[String(server.name)] : undefined;
                const state: CapabilityState = ok === true ? "available" : ok === false ? "blocked" : "requires-setup";
                return (
                  <li className={s.row} key={String(server.name ?? i)}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}>{server.name ?? "Unnamed server"}</h3>
                        <StateBadge state={state} label={checked ? (ok ? "Healthy" : "Unhealthy") : "Not checked"} />
                        {server.transport && <Badge tone="neutral">{server.transport}</Badge>}
                        {server.scope && <Badge tone="neutral">{server.scope} scope</Badge>}
                      </div>
                      <p className={s.mono}>
                        {server.command ? `${server.command}${(server as { args?: string[] }).args?.length ? ` ${(server as { args?: string[] }).args?.join(" ")}` : ""}` : server.url ?? "No command or URL reported"}
                      </p>
                      <p className={s.rowMeta}>Tool calls from this server pass through Keel's normal permission gate. The bridge does not expose per-server policies here.</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>
      <p className={s.footerNote}>Environment variable <strong>names</strong> may appear in connector data; their values are never returned or rendered.</p>
    </div>
  );
}

export function ConnectorsPanel() {
  const { notify } = useApp();
  const connectorsQ = useBridgeData(() => bridge.connectors());
  const [tests, setTests] = useState<Record<string, TestResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState<{ name: string; command: string; args: string; preset: string }>({ name: "", command: "", args: "", preset: "" });
  const [removeTarget, setRemoveTarget] = useState<ConnectorRow | null>(null);

  const payload = readRecord(connectorsQ.data);
  const connectors = asArray<ConnectorRow>(connectorsQ.data, "connectors");
  const presets = asArray<PresetRow>(payload.presets, "presets");

  async function runTest(name: string) {
    setTests((prev) => ({ ...prev, [name]: { state: "testing" } }));
    try {
      const body = readRecord(await bridge.testConnector({ name }));
      if (body.ok === true) {
        setTests((prev) => ({
          ...prev,
          [name]: {
            state: "ok",
            tool_count: typeof body.tool_count === "number" ? body.tool_count : undefined,
            tools: Array.isArray(body.tools) ? body.tools.map((t) => readRecord(t)) as Array<{ name?: string; description?: string }> : undefined,
            resources: Array.isArray(body.resources) ? body.resources : undefined,
            prompts: Array.isArray(body.prompts) ? body.prompts : undefined,
          },
        }));
        notify(`${name}: handshake succeeded (${String(body.tool_count ?? 0)} tools).`, "success");
      } else {
        setTests((prev) => ({ ...prev, [name]: { state: "fail", error: String(body.error ?? body.detail ?? "Handshake failed") } }));
      }
    } catch (err) {
      setTests((prev) => ({ ...prev, [name]: { state: "fail", error: errMessage(err) } }));
    }
  }

  function openAdd(preset?: PresetRow) {
    setForm({
      name: preset?.name ?? "",
      command: typeof preset?.command === "string" ? preset.command : "",
      args: "",
      preset: preset?.name ?? "",
    });
    setError(null);
    setAddOpen(true);
  }

  async function confirmAdd() {
    const name = form.name.trim();
    if (!name) { setError("A connector name is required."); return; }
    setBusy("__add");
    setError(null);
    try {
      const args = form.args.trim() ? form.args.trim().split(/\s+/) : [];
      const body = readRecord(form.preset
        ? await bridge.addConnector({ preset: form.preset, args, name })
        : await bridge.addConnector({ name, command: form.command.trim(), args }));
      if (typeof body.error === "string") { setError(body.error); return; }
      const added = String(body.name ?? name);
      notify(`${added} added.`, "success");
      setAddOpen(false);
      await connectorsQ.reload();
      void runTest(added);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function confirmRemove() {
    if (!removeTarget?.name) return;
    const name = removeTarget.name;
    setBusy(name);
    try {
      const body = readRecord(await bridge.removeConnector({ name }));
      if (typeof body.error === "string") { setError(body.error); return; }
      notify(`${name} removed.`, "success");
      setRemoveTarget(null);
      setTests((prev) => { const next = { ...prev }; delete next[name]; return next; });
      await connectorsQ.reload();
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function connectorState(row: ConnectorRow, test?: TestResult): { state: CapabilityState; label?: string; reason: string } {
    if (row.enabled === false) return { state: "blocked", label: "Disabled", reason: "Reported disabled by the bridge." };
    if (row.error || row.last_error) return { state: "blocked", reason: `Last error: ${row.error ?? row.last_error}` };
    if (test?.state === "ok") return { state: "available", label: "Verified", reason: `Handshake verified; ${String(test.tool_count ?? 0)} tool(s) reported.` };
    if (test?.state === "fail") return { state: "blocked", label: "Test failed", reason: test.error };
    if (test?.state === "testing") return { state: "requires-setup", label: "Testing…", reason: "Connection test in progress." };
    return { state: "unconfigured", label: "Not verified", reason: "Configured, but no connection test has succeeded yet." };
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Connectors</h2>
          <p className={s.muted}>The same MCP servers as the MCP tab, managed through the bridge's connector API. Test results come from a real handshake.</p>
        </div>
        <div className={s.actionRow}>
          <Button onClick={() => openAdd()}><Icon name="plus" size={14} /> Add custom</Button>
          <IconButton label="Reload connectors" onClick={connectorsQ.reload}><Icon name="refresh" size={15} /></IconButton>
        </div>
      </div>

      {typeof payload.error === "string" && <p className={s.error} role="alert">Bridge reported: {payload.error}</p>}
      {error && <p className={s.error} role="alert">{error}</p>}

      {presets.length > 0 && (
        <Card className={s.presetBox}>
          <SectionTitle>Available presets</SectionTitle>
          <div className={s.presetGrid}>
            {presets.map((preset, i) => (
              <div className={s.preset} key={String(preset.name ?? i)}>
                <div>
                  <strong>{preset.label ?? preset.name ?? "Unnamed preset"}</strong>
                  <p className={s.rowMeta}>{preset.description ?? "No description reported."}</p>
                  {typeof preset.command === "string" && <code className={s.code}>{preset.command}</code>}
                </div>
                <Button size="sm" onClick={() => openAdd(preset)}>Add</Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <PanelState query={connectorsQ}>
        {() => (connectors.length === 0 ? (
          <EmptyState icon={<Icon name="link" />} title="No connectors configured"
            description="Add a preset or a custom stdio server above. Nothing connects until you do." />
        ) : (
          <ul className={s.list}>
            {connectors.map((row, i) => {
              const name = String(row.name ?? i);
              const test = tests[name];
              const status = connectorState(row, test);
              return (
                <li className={s.row} key={name}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h3 className={s.rowTitle}>{row.name ?? "Unnamed connector"}</h3>
                      <StateBadge state={status.state} label={status.label} />
                      <Badge tone="neutral">{row.type ?? row.transport ?? (row.command ? "stdio" : "type not reported")}</Badge>
                    </div>
                    <p className={s.rowMeta}>{status.reason}</p>
                    <p className={s.mono}>{row.command ? `${row.command}${(row.args ?? []).length ? ` ${row.args?.join(" ")}` : ""}` : "No command reported"}</p>
                    {Array.isArray(row.env_keys) && row.env_keys.length > 0 && (
                      <p className={s.muted}>Env vars (values hidden): {row.env_keys.map((k) => <code className={s.code} key={String(k)}>{String(k)}</code>)}</p>
                    )}
                    {test?.state === "ok" && (
                      <div className={s.testResult}>
                        <strong>Verified tools ({String(test.tool_count ?? test.tools?.length ?? 0)})</strong>
                        {test.tools && test.tools.length > 0 ? (
                          <ul>{test.tools.map((tool, ti) => (
                            <li key={String(tool.name ?? ti)}><code className={s.code}>{tool.name ?? "unnamed"}</code>{tool.description ? ` — ${tool.description}` : ""}</li>
                          ))}</ul>
                        ) : <p className={s.muted}>No tools were listed by the test response.</p>}
                        {Array.isArray(test.resources) && <p className={s.muted}>Resources reported: {test.resources.length}</p>}
                        {Array.isArray(test.prompts) && <p className={s.muted}>Prompts reported: {test.prompts.length}</p>}
                      </div>
                    )}
                    {test?.state === "fail" && <p className={s.error} role="alert">Test error: {test.error}</p>}
                    {row.logs !== undefined && <pre className={s.pre}>{safeResult(row.logs, 1500)}</pre>}
                  </div>
                  <div className={s.rowActions}>
                    <Button size="sm" onClick={() => { void runTest(name); }} disabled={test?.state === "testing"}>
                      {test?.state === "testing" ? "Testing…" : "Test"}
                    </Button>
                    <IconButton label={`Remove ${name}`} onClick={() => setRemoveTarget(row)} disabled={busy !== null}><Icon name="trash" size={15} /></IconButton>
                  </div>
                </li>
              );
            })}
          </ul>
        ))}
      </PanelState>

      <p className={s.footerNote}>Connector tools are subject to the same approval path as built-in tools. Per-connector permission policies and log retention are not exposed by this bridge route.</p>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title={form.preset ? `Add ${form.preset} preset` : "Add a custom connector"}
        footer={<>
          <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy === "__add"} onClick={() => { void confirmAdd(); }}>Add connector</Button>
        </>}>
        <TextField label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        {!form.preset && <TextField label="Command" value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="npx" />}
        <TextField label="Arguments (space separated)" value={form.args} onChange={(e) => setForm({ ...form, args: e.target.value })} />
        <p className={s.muted}>The bridge stores the command and arguments in Keel settings. Secrets are not entered here and are never echoed back.</p>
        {error && <p className={s.error} role="alert">{error}</p>}
      </Dialog>

      <Dialog open={removeTarget !== null} onClose={() => setRemoveTarget(null)} title="Remove connector?"
        footer={<>
          <Button variant="ghost" onClick={() => setRemoveTarget(null)}>Cancel</Button>
          <Button variant="danger" loading={busy === (removeTarget?.name ?? "")} onClick={() => { void confirmRemove(); }}>Remove</Button>
        </>}>
        <p>This removes <strong>{removeTarget?.name}</strong> from Keel settings. Files and external services are not deleted. The bridge reports the actual outcome.</p>
      </Dialog>
    </div>
  );
}

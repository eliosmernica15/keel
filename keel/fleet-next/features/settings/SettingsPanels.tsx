"use client";

// Settings panels backed by the real bridge routes described in lib/api.ts.
// Every control here either performs a live bridge request or navigates to an
// existing surface; nothing is decorative and nothing is invented locally.
// The panel loading/error/empty wrappers follow the Fleet support patterns
// (`wrapped` + `useBridgeResource`) against the same BFF proxy.

import React, { useMemo, useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, Toggle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { useApp } from "@/lib/state";
import { useBridgeResource, wrapped } from "@/features/fleet/support";
import s from "./settings.module.css";
import { PanelState, readRecord, type BridgeData } from "./settingsShared";

type Row = Record<string, unknown>;

/** Fleet's `wrapped` accepts untyped bridge envelopes; narrow to rows. */
function rows(value: unknown, key: string): Row[] {
  return wrapped<Row>(value as Record<string, unknown> | Row[] | null | undefined, key);
}

/** The Fleet resource hook normalised to the settings panel shape. */
function useResource<T>(load: () => Promise<T>): BridgeData<T> {
  const resource = useBridgeResource(load, []);
  const message = resource.error ? errMessage(resource.error) : null;
  return {
    data: resource.data,
    loading: resource.loading,
    error: message,
    unavailable: resource.error ? isBridgeUnavailable(resource.error) : false,
    reload: resource.reload,
    setData: resource.setData,
  };
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}
function label(value: unknown, fallback: string): string {
  return stringValue(value) ?? fallback;
}
function redact(value: string): string {
  return value
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, "sk-••••")
    .replace(/Bearer\s+[A-Za-z0-9._-]{8,}/gi, "Bearer ••••")
    .replace(/(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+/gi, "$1=••••");
}
function renderValue(value: unknown, limit = 1200): string {
  const raw = typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2);
  return redact(raw.length > limit ? `${raw.slice(0, limit)}\n…` : raw);
}
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
  const out: Record<string, boolean> = {};
  for (const [name, val] of Object.entries(readRecord(value))) {
    if (typeof val === "boolean") out[name] = val;
    else {
      const nested = readRecord(val);
      if (typeof nested.ok === "boolean") out[name] = nested.ok;
    }
  }
  return out;
}

function PanelCard({ title, description, action, children }: {
  title: string;
  description: string;
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>{title}</h3>
        {action}
      </div>
      <p className={s.cardDesc}>{description}</p>
      {children}
    </Card>
  );
}

function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={s.errorBox} role="alert">
      <strong>That request did not complete</strong>
      <p>{message}</p>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

function DownloadLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <a className="keel-btn keel-btn--sm keel-btn--secondary" href={href} download>{children}</a>;
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? "").split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("The selected file could not be read."));
    reader.readAsDataURL(file);
  });
}

/* ------------------------------------------------------------------ Skills */

export function SkillsSettingsPanel() {
  const { notify } = useApp();
  const skillsQ = useResource(() => bridge.skills());
  const managedQ = useResource(() => bridge.skillsManage());
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ name: string; message: string } | null>(null);

  const managed = new Map(wrapped<Row>(managedQ.data, "skills").map((row) => [String(row.name ?? ""), row]));
  const rows = wrapped<Row>(skillsQ.data, "skills").map((row) => {
    const state = managed.get(String(row.name ?? ""));
    return state ? { ...row, ...state } : row;
  });
  const canToggle = managedQ.data !== null;

  function reloadAll() { skillsQ.reload(); managedQ.reload(); }

  async function toggle(row: Row) {
    const name = stringValue(row.name);
    if (!name || busy) return;
    setBusy(name);
    setFailed(null);
    try {
      const body = readRecord(await bridge.enableSkill({ name, enabled: row.enabled === false }));
      if (body.ok !== true && body.enabled === undefined) {
        setFailed({ name, message: stringValue(body.error) ?? "The skill could not be updated." });
        return;
      }
      notify(`${name} ${row.enabled === false ? "enabled" : "disabled"}.`, "success");
      reloadAll();
    } catch (err) {
      setFailed({ name, message: errMessage(err) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <PanelCard
      title="Skills"
      description="Skills discovered by the bridge. Enable state is read from the skill manager and changed through its real route."
      action={<Button size="sm" variant="secondary" onClick={reloadAll}>Refresh</Button>}
    >
      {!canToggle && managedQ.error && (
        <ErrorNotice message={managedQ.error} onRetry={managedQ.reload} />
      )}
      {failed && (
        <ErrorNotice message={failed.message} onRetry={() => {
          const row = rows.find((item) => item.name === failed.name);
          if (row) void toggle(row);
        }} />
      )}
      <PanelState query={skillsQ}>
        {() => rows.length === 0 ? (
          <EmptyState icon={<Icon name="spark" />} title="No skills found"
            description="Keel found no skills in the bundled or user folders."
            action={<Button size="sm" onClick={reloadAll}>Refresh skills</Button>} />
        ) : (
          <ul className={s.list}>
            {rows.map((row, i) => {
              const name = label(row.name, "Unnamed skill");
              return (
                <li className={s.row} key={String(row.name ?? i)}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h4 className={s.rowTitle}>{name}</h4>
                      <Badge tone={row.enabled === false ? "neutral" : "success"}>
                        {row.enabled === false ? "Disabled" : "Enabled"}
                      </Badge>
                      {stringValue(row.scope) && <Badge tone="neutral">{String(row.scope)}</Badge>}
                    </div>
                    {stringValue(row.description) && <p className={s.muted}>{String(row.description)}</p>}
                  </div>
                  <div className={s.rowActions}>
                    <Toggle
                      checked={row.enabled !== false}
                      disabled={!canToggle || busy !== null}
                      onChange={() => { void toggle(row); }}
                      label={`Enable ${name}`}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </PanelState>
    </PanelCard>
  );
}

/* ---------------------------------------------------------------- Commands */

interface CommandRow extends Row {
  name?: string;
  description?: string;
  source?: string;
  argument_hint?: string;
}

export function CommandsSettingsPanel() {
  const commandsQ = useResource(() => bridge.commands());
  const [target, setTarget] = useState<CommandRow | null>(null);
  const [args, setArgs] = useState("");
  const [projectRoot, setProjectRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function execute() {
    if (!target?.name) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Row = { name: target.name, args };
      if (projectRoot.trim()) payload.project_root = projectRoot.trim();
      const body = readRecord(await bridge.executeCommand(payload));
      if (typeof body.error === "string") { setError(body.error); return; }
      setResult({ ok: body.ok === true, text: renderValue(body.result) });
      setTarget(null);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelCard
      title="Commands"
      description="The command catalogue from the bridge. Running a command is a guarded backend action; its real output is shown here."
      action={<Button size="sm" variant="secondary" onClick={commandsQ.reload}>Refresh</Button>}
    >
      {result && (
        <Card className={result.ok ? s.resultOk : s.resultFail}>
          <strong>{result.ok ? "Command completed" : "Command reported a failed step"}</strong>
          <pre className={s.mono}>{result.text}</pre>
        </Card>
      )}
      <PanelState query={commandsQ}>
        {() => {
          const rows = wrapped<CommandRow>(commandsQ.data, "commands");
          return rows.length === 0 ? (
            <EmptyState icon={<Icon name="command" />} title="No commands found"
              description="The bridge catalogue is empty on this machine."
              action={<Button size="sm" onClick={commandsQ.reload}>Refresh commands</Button>} />
          ) : (
            <ul className={s.list}>
              {rows.map((row, i) => (
                <li className={s.row} key={String(row.name ?? i)}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h4 className={s.rowTitle}><code className={s.code}>/{label(row.name, "command")}</code></h4>
                      {stringValue(row.source) && <Badge tone="neutral">{String(row.source)}</Badge>}
                    </div>
                    {stringValue(row.description) && <p className={s.muted}>{String(row.description)}</p>}
                    {stringValue(row.argument_hint) && <p className={s.mono}>Usage: {String(row.argument_hint)}</p>}
                  </div>
                  <div className={s.rowActions}>
                    <Button size="sm" onClick={() => { setTarget(row); setArgs(""); setProjectRoot(""); setError(null); }}>
                      Run…
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          );
        }}
      </PanelState>
      <Dialog open={target !== null} onClose={() => setTarget(null)} title={`Run /${target?.name ?? ""}`}
        footer={<>
          <Button variant="ghost" onClick={() => setTarget(null)}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={() => { void execute(); }}>Run command</Button>
        </>}>
        <p className={s.muted}>This runs the real guarded command through the bridge. Arguments and the result are passed exactly as reported.</p>
        <label className={s.selectLabel}>Arguments
          <input value={args} onChange={(e) => setArgs(e.target.value)} placeholder="Optional arguments" />
        </label>
        <label className={s.selectLabel}>Project root (optional)
          <input value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} placeholder="Absolute path, or leave empty for the bridge default" />
        </label>
        {error && <ErrorNotice message={error} onRetry={() => { void execute(); }} />}
      </Dialog>
    </PanelCard>
  );
}

/* ---------------------------------------------------------------- Workflows */

interface WorkflowRow extends Row {
  name?: string;
  description?: string;
  source?: string;
  steps?: number;
}

export function WorkflowsSettingsPanel() {
  const workflowsQ = useResource(() => bridge.workflows());
  const [target, setTarget] = useState<WorkflowRow | null>(null);
  const [projectRoot, setProjectRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; name: string; results: number } | null>(null);

  async function execute() {
    if (!target?.name) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Row = { name: target.name };
      if (projectRoot.trim()) payload.project_root = projectRoot.trim();
      const body = readRecord(await bridge.executeWorkflow(payload));
      if (typeof body.error === "string") { setError(body.error); return; }
      setResult({
        ok: body.ok === true,
        name: label(body.name, label(target.name, "Workflow")),
        results: Array.isArray(body.results) ? body.results.length : 0,
      });
      setTarget(null);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelCard
      title="Workflows"
      description="Workflows discovered by the bridge. Execution is non-interactive and every tool step passes Keel's permission gate."
      action={<Button size="sm" variant="secondary" onClick={workflowsQ.reload}>Refresh</Button>}
    >
      {result && (
        <Card className={result.ok ? s.resultOk : s.resultFail}>
          <strong>{result.ok
            ? `${result.name}: ${result.results} step${result.results === 1 ? "" : "s"} completed`
            : `${result.name}: at least one step failed`}</strong>
        </Card>
      )}
      <PanelState query={workflowsQ}>
        {() => {
          const rows = wrapped<WorkflowRow>(workflowsQ.data, "workflows");
          return rows.length === 0 ? (
            <EmptyState icon={<Icon name="routine" />} title="No workflows found"
              description="Keel found no workflow definitions in the bundled or user folders."
              action={<Button size="sm" onClick={workflowsQ.reload}>Refresh workflows</Button>} />
          ) : (
            <ul className={s.list}>
              {rows.map((row, i) => (
                <li className={s.row} key={String(row.name ?? i)}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h4 className={s.rowTitle}>{label(row.name, "Unnamed workflow")}</h4>
                      {typeof row.steps === "number" && <Badge tone="neutral">{row.steps} step{row.steps === 1 ? "" : "s"}</Badge>}
                      {stringValue(row.source) && <Badge tone="neutral">{String(row.source)}</Badge>}
                    </div>
                    {stringValue(row.description) && <p className={s.muted}>{String(row.description)}</p>}
                  </div>
                  <div className={s.rowActions}>
                    <Button size="sm" onClick={() => { setTarget(row); setProjectRoot(""); setError(null); }}>Run…</Button>
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
        <p className={s.muted}>This runs real guarded steps on this machine. The bridge's reported outcome is shown after the run.</p>
        <label className={s.selectLabel}>Project root (optional)
          <input value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} placeholder="Absolute path, or leave empty for the bridge default" />
        </label>
        {error && <ErrorNotice message={error} onRetry={() => { void execute(); }} />}
      </Dialog>
    </PanelCard>
  );
}

/* -------------------------------------------------------------- MCP servers */

export function McpServersSettingsPanel() {
  const serversQ = useResource(() => bridge.mcpServers());
  const [health, setHealth] = useState<Record<string, boolean> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function probe() {
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
    <PanelCard
      title="MCP servers"
      description="Servers are read from Keel settings. Health is shown only after a real bridge probe, which starts and checks each server."
      action={<Button size="sm" variant="secondary" onClick={() => { setHealth(null); serversQ.reload(); }}>Refresh</Button>}
    >
      <div className={s.controls}>
        <Button size="sm" onClick={() => { void probe(); }} loading={busy}>Run health check</Button>
        {health && <span className={s.muted}>{Object.keys(health).length} server{Object.keys(health).length === 1 ? "" : "s"} checked</span>}
      </div>
      {error && <ErrorNotice message={error} onRetry={() => { void probe(); }} />}
      <PanelState query={serversQ}>
        {() => {
          const rows = wrapped<Row>(serversQ.data, "servers");
          return rows.length === 0 ? (
            <EmptyState icon={<Icon name="link" />} title="No MCP servers configured"
              description="Add an MCP connector in Plugins to extend Keel with real tools."
              action={<Button size="sm" onClick={serversQ.reload}>Refresh servers</Button>} />
          ) : (
            <ul className={s.list}>
              {rows.map((row, i) => {
                const name = label(row.name, "Unnamed server");
                const checked = health !== null && Object.prototype.hasOwnProperty.call(health, name);
                return (
                  <li className={s.row} key={String(row.name ?? i)}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h4 className={s.rowTitle}>{name}</h4>
                        {checked && <Badge tone={health[name] ? "success" : "danger"}>{health[name] ? "Healthy" : "Unhealthy"}</Badge>}
                        {stringValue(row.transport) && <Badge tone="neutral">{String(row.transport)}</Badge>}
                        {stringValue(row.scope) && <Badge tone="neutral">{String(row.scope)} scope</Badge>}
                      </div>
                      {stringValue(row.command) && <p className={s.mono}>{String(row.command)}</p>}
                      {stringValue(row.url) && <p className={s.mono}>{String(row.url)}</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>
    </PanelCard>
  );
}

/* ------------------------------------------------------ Plugins/connectors */

export function PluginsSettingsPanel() {
  const connectorsQ = useResource(() => bridge.connectors());
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ name: "", command: "", args: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; retry?: () => void } | null>(null);
  const [tests, setTests] = useState<Record<string, string>>({});
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  async function add() {
    const name = form.name.trim();
    if (!name) { setError({ message: "Enter a connector name." }); return; }
    setBusy("__add");
    setError(null);
    try {
      const payload: Row = { name, command: form.command.trim(), args: form.args.trim() ? form.args.trim().split(/\s+/) : [] };
      const body = readRecord(await bridge.addConnector(payload));
      if (typeof body.error === "string") { setError({ message: body.error, retry: () => { void add(); } }); return; }
      setAddOpen(false);
      setForm({ name: "", command: "", args: "" });
      connectorsQ.reload();
    } catch (err) {
      setError({ message: errMessage(err), retry: () => { void add(); } });
    } finally {
      setBusy(null);
    }
  }

  async function test(name: string) {
    setBusy(name);
    setError(null);
    try {
      const body = readRecord(await bridge.testConnector({ name }));
      setTests((prev) => ({ ...prev, [name]: body.ok === true
        ? `Handshake succeeded (${typeof body.tool_count === "number" ? body.tool_count : 0} tools).`
        : stringValue(body.error) ?? stringValue(body.detail) ?? "The connector could not be reached." }));
    } catch (err) {
      setTests((prev) => ({ ...prev, [name]: errMessage(err) }));
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!removeTarget) return;
    setBusy("__remove");
    setError(null);
    try {
      const body = readRecord(await bridge.removeConnector({ name: removeTarget }));
      if (typeof body.error === "string") { setError({ message: body.error, retry: () => { void remove(); } }); return; }
      setRemoveTarget(null);
      connectorsQ.reload();
    } catch (err) {
      setError({ message: errMessage(err), retry: () => { void remove(); } });
    } finally {
      setBusy(null);
    }
  }

  return (
    <PanelCard
      title="Plugins & connectors"
      description="Keel's extension points are skills and MCP connectors. Add, test and remove connectors here; the bridge performs each action."
      action={<Button size="sm" variant="secondary" onClick={connectorsQ.reload}>Refresh</Button>}
    >
      {error && <ErrorNotice message={error.message} onRetry={error.retry} />}
      <PanelState query={connectorsQ}>
        {() => {
          const rows = wrapped<Row>(connectorsQ.data, "connectors");
          return rows.length === 0 ? (
            <EmptyState icon={<Icon name="capabilities" />} title="No connectors configured"
              description="Add an MCP connector to extend Keel with tools from another process."
              action={<Button size="sm" onClick={() => { setError(null); setAddOpen(true); }}>Add connector</Button>} />
          ) : (
            <ul className={s.list}>
              {rows.map((row, i) => {
                const name = label(row.name, "Unnamed connector");
                return (
                  <li className={s.row} key={String(row.name ?? i)}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h4 className={s.rowTitle}>{name}</h4>
                        {stringValue(row.command) && <Badge tone="neutral">{String(row.command)}</Badge>}
                      </div>
                      {tests[name] && <p className={tests[name].startsWith("Handshake") ? s.success : s.error}>{tests[name]}</p>}
                    </div>
                    <div className={s.rowActions}>
                      <Button size="sm" variant="ghost" onClick={() => { void test(name); }} loading={busy === name}>Test</Button>
                      <Button size="sm" variant="ghost" onClick={() => setRemoveTarget(name)}>Remove…</Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>
      <div className={s.controls}>
        <Button size="sm" onClick={() => { setError(null); setAddOpen(true); }}>Add connector</Button>
      </div>
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Add connector"
        footer={<>
          <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy === "__add"} onClick={() => { void add(); }}>Add connector</Button>
        </>}>
        <p className={s.muted}>The bridge stores the connection in Keel settings. Variable values are never displayed here.</p>
        <label className={s.selectLabel}>Name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Connector name" />
        </label>
        <label className={s.selectLabel}>Command
          <input value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="Executable for the MCP server" />
        </label>
        <label className={s.selectLabel}>Arguments (space separated)
          <input value={form.args} onChange={(e) => setForm({ ...form, args: e.target.value })} placeholder="Optional arguments" />
        </label>
        {error && <ErrorNotice message={error.message} onRetry={error.retry} />}
      </Dialog>
      <Dialog open={removeTarget !== null} onClose={() => setRemoveTarget(null)} title={`Remove ${removeTarget ?? "connector"}?`}
        footer={<>
          <Button variant="ghost" onClick={() => setRemoveTarget(null)}>Cancel</Button>
          <Button variant="danger" loading={busy === "__remove"} onClick={() => { void remove(); }}>Remove connector</Button>
        </>}>
        <p className={s.muted}>This calls the bridge to remove the saved connector. Skills and other connectors are unaffected.</p>
      </Dialog>
    </PanelCard>
  );
}

/* ---------------------------------------------------------------- Keel Code */

export function KeelCodePanel() {
  const { setSurface } = useApp();
  const projectsQ = useResource(() => bridge.projects());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; id?: string } | null>(null);

  async function open(row: Row) {
    const id = stringValue(row.id);
    if (!id) return;
    setBusy(id);
    setError(null);
    try {
      const body = readRecord(await bridge.openProject(id));
      if (typeof body.error === "string") { setError({ message: body.error, id }); return; }
      setSurface("code");
    } catch (err) {
      setError({ message: errMessage(err), id });
    } finally {
      setBusy(null);
    }
  }

  return (
    <PanelCard
      title="Projects in Keel Code"
      description="Folders added to this Keel install. Opening one calls the bridge and switches to the Code surface."
      action={<Button size="sm" variant="secondary" onClick={projectsQ.reload}>Refresh</Button>}
    >
      {error && <ErrorNotice message={error.message} onRetry={() => {
        const row = error.id ? projectsQ.data && rows(projectsQ.data, "projects").find((p) => p.id === error.id) : null;
        if (row) void open(row);
      }} />}
      <PanelState query={projectsQ}>
        {() => {
          const projects = rows(projectsQ.data, "projects");
          return projects.length === 0 ? (
            <EmptyState icon={<Icon name="code" />} title="No projects added"
              description="Add a folder in Code to read, review and edit files with Keel."
              action={<Button size="sm" onClick={() => setSurface("code")}>Open Code</Button>} />
          ) : (
            <ul className={s.list}>
              {projects.map((row, i) => (
                <li className={s.row} key={String(row.id ?? i)}>
                  <div className={s.rowMain}>
                    <div className={s.rowTitleLine}>
                      <h4 className={s.rowTitle}>{label(row.name, label(row.path, "Project"))}</h4>
                      <Badge tone={row.trusted === true ? "success" : "neutral"}>
                        {row.trusted === true ? "Trusted" : "Not trusted"}
                      </Badge>
                    </div>
                    {stringValue(row.path) && <p className={s.mono}>{String(row.path)}</p>}
                  </div>
                  <div className={s.rowActions}>
                    <Button size="sm" loading={busy === row.id} onClick={() => { void open(row); }}>
                      Open in Code
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          );
        }}
      </PanelState>
      <p className={s.muted}>Keel only reads and writes folders that the bridge has marked as trusted.</p>
    </PanelCard>
  );
}

/* ------------------------------------------------------------- Keel Desktop */

export function KeelDesktopPanel() {
  const { notify } = useApp();
  const statusQ = useResource<unknown>(async () => bridge.keepAwake());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; on: boolean } | null>(null);
  const body = readRecord(statusQ.data);
  const supported = body.supported !== false;
  const on = body.on === true;

  async function set(next: boolean) {
    setBusy(true);
    setError(null);
    try {
      const result = readRecord(await bridge.keepAwake(next));
      if (result.ok === false) { setError({ message: stringValue(result.error) ?? "The bridge could not change this setting.", on: next }); return; }
      notify(next ? "Keep-awake is on." : "Keep-awake is off.", "success");
      statusQ.reload();
    } catch (err) {
      setError({ message: errMessage(err), on: next });
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelCard
      title="Desktop behaviour"
      description="This preference is applied by the bridge process on this machine, not stored in the browser."
      action={<Button size="sm" variant="secondary" onClick={statusQ.reload}>Refresh</Button>}
    >
      {error && <ErrorNotice message={error.message} onRetry={() => { void set(error.on); }} />}
      <PanelState query={statusQ}>
        {() => (
          <>
            <Toggle checked={on} disabled={!supported || busy} onChange={(v) => { void set(v); }}
              label="Keep this machine awake while Keel runs" />
            {!supported && <p className={s.muted}>This bridge reports that keep-awake is unavailable on the current platform.</p>}
            {stringValue(body.handle) && <p className={s.mono}>Process handle: {String(body.handle)}</p>}
          </>
        )}
      </PanelState>
    </PanelCard>
  );
}

/* ------------------------------------------------------------ Import/export */

export function ImportExportPanel() {
  const { notify, setSurface } = useApp();
  const dataQ = useResource(async () => {
    const [bots, files] = await Promise.all([bridge.listBots(), bridge.library()]);
    return { bots: wrapped<Row>(bots, "bots"), files: wrapped<Row>(files, "files") };
  });
  const [botId, setBotId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; retry?: () => void } | null>(null);

  async function upload() {
    if (!botId || !file) return;
    setBusy(true);
    setError(null);
    try {
      const contentBase64 = await readFileAsBase64(file);
      const payload: Row = {
        bot_id: botId,
        filename: file.name,
        content_base64: contentBase64,
        mime: file.type || undefined,
      };
      const body = readRecord(await bridge.uploadLibrary(payload));
      if (typeof body.error === "string") { setError({ message: body.error, retry: () => { void upload(); } }); return; }
      notify(`${file.name} imported into the library.`, "success");
      setFile(null);
      dataQ.reload();
    } catch (err) {
      setError({ message: errMessage(err), retry: () => { void upload(); } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelCard
      title="Import & export"
      description="Export chat transcripts and library files, or import a file into a chat's library. All transfers go through the bridge; no credentials are shown."
      action={<Button size="sm" variant="secondary" onClick={dataQ.reload}>Refresh</Button>}
    >
      {error && <ErrorNotice message={error.message} onRetry={error.retry} />}
      <PanelState query={dataQ}>
        {({ bots, files }) => (
          <>
            {bots.length === 0 && files.length === 0 ? (
              <EmptyState icon={<Icon name="download" />} title="Nothing to export yet"
                description="Start a chat or add a file to its library to create something you can download."
                action={<Button size="sm" onClick={() => setSurface("cowork")}>Open Cowork</Button>} />
            ) : (
              <>
                {bots.length > 0 && (
                  <div className={s.subPanel}>
                    <h4 className={s.rowTitle}>Chat transcripts</h4>
                    <ul className={s.list}>
                      {bots.map((bot, i) => (
                        <li className={s.row} key={String(bot.id ?? i)}>
                          <div className={s.rowMain}>
                            <div className={s.rowTitleLine}>
                              <h5 className={s.rowTitle}>{label(bot.name, "Chat")}</h5>
                            </div>
                          </div>
                          <div className={s.rowActions}>
                            {stringValue(bot.id) && <DownloadLink href={bridge.exportUrl(String(bot.id))}>Download .md</DownloadLink>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {files.length > 0 && (
                  <div className={s.subPanel}>
                    <h4 className={s.rowTitle}>Library files</h4>
                    <ul className={s.list}>
                      {files.map((item, i) => (
                        <li className={s.row} key={String(item.id ?? i)}>
                          <div className={s.rowMain}>
                            <div className={s.rowTitleLine}>
                              <h5 className={s.rowTitle}>{label(item.name, "File")}</h5>
                              {typeof item.size === "number" && <Badge tone="neutral">{String(item.size)} B</Badge>}
                            </div>
                          </div>
                          <div className={s.rowActions}>
                            {stringValue(item.id) && <DownloadLink href={bridge.downloadUrl(String(item.id))}>Download</DownloadLink>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
            {bots.length > 0 && (
              <div className={s.subPanel}>
                <h4 className={s.rowTitle}>Import a file</h4>
                <label className={s.selectLabel}>Import into chat
                  <select value={botId} onChange={(e) => setBotId(e.target.value)}>
                    <option value="">Choose a chat</option>
                    {bots.map((bot, i) => (
                      <option key={String(bot.id ?? i)} value={String(bot.id ?? "")}>{label(bot.name, "Chat")}</option>
                    ))}
                  </select>
                </label>
                <input type="file" aria-label="File to import" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <div className={s.controls}>
                  <Button size="sm" loading={busy} disabled={!botId || file === null} onClick={() => { void upload(); }}>
                    Import file
                  </Button>
                  {file && <span className={s.muted}>{file.name}</span>}
                </div>
              </div>
            )}
          </>
        )}
      </PanelState>
    </PanelCard>
  );
}

/* ---------------------------------------------------------------- Developer */

export function DeveloperPanel() {
  const snapshotQ = useResource(async () => {
    const [skills, commands, workflows, servers] = await Promise.all([
      bridge.skills(), bridge.commands(), bridge.workflows(), bridge.mcpServers(),
    ]);
    return {
      skills: wrapped<Row>(skills, "skills").length,
      commands: wrapped<Row>(commands, "commands").length,
      workflows: wrapped<Row>(workflows, "workflows").length,
      servers: wrapped<Row>(servers, "servers").length,
    };
  });
  const [health, setHealth] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function probe() {
    setBusy(true);
    setError(null);
    try {
      const body = readRecord(await bridge.mcpHealth());
      if (typeof body.error === "string") { setError(body.error); return; }
      setHealth(body.health ?? body);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelCard
      title="Developer diagnostics"
      description="Counts below come from live bridge catalogue routes. The health check makes a real request and shows its result."
      action={<Button size="sm" variant="secondary" onClick={snapshotQ.reload}>Refresh</Button>}
    >
      <PanelState query={snapshotQ}>
        {(data) => (
          <dl className={s.usageGrid}>
            <div><dt>Skills discovered</dt><dd>{data.skills}</dd></div>
            <div><dt>Commands discovered</dt><dd>{data.commands}</dd></div>
            <div><dt>Workflows discovered</dt><dd>{data.workflows}</dd></div>
            <div><dt>MCP servers configured</dt><dd>{data.servers}</dd></div>
          </dl>
        )}
      </PanelState>
      <div className={s.subPanel}>
        <div className={s.controls}>
          <Button size="sm" onClick={() => { void probe(); }} loading={busy}>Run health check</Button>
        </div>
        {error && <ErrorNotice message={error} onRetry={() => { void probe(); }} />}
        {health !== null && <pre className={s.mono}>{renderValue(health)}</pre>}
      </div>
    </PanelCard>
  );
}

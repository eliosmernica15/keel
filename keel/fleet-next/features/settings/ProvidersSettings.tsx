"use client";

// Providers, models and credentials. Session keys are verified live and held
// in bridge process memory; persisted keys are encrypted by the bridge in
// ~/.keel/settings.json. This browser never stores or displays a full key.

import React, { useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState, SectionTitle, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import s from "./settings.module.css";
import { asArray, PanelState, readRecord, useBridgeData } from "./settingsShared";

interface ProviderRow {
  id?: string;
  name?: string;
  configured?: boolean;
  key_source?: string | null;
  key_hint?: string | null;
  default_model?: string;
  base_url?: string;
  notes?: string;
  session?: boolean;
  opt_in?: boolean;
  error?: string;
  [key: string]: unknown;
}
interface ModelMeta {
  id?: string;
  context_length?: number;
  supported_parameters?: string[];
  reasoning?: { supported_efforts?: string[]; default_effort?: string | null; mandatory?: boolean } | null;
  [key: string]: unknown;
}
interface CatalogPayload {
  ok?: boolean;
  provider?: string;
  source?: string;
  catalog_version?: string;
  models?: string[];
  model_count?: number;
  models_meta?: ModelMeta[];
  key_source?: string;
  error?: string;
  detail?: string;
}

export function ProvidersPanel() {
  const providersQ = useBridgeData(() => bridge.providers());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [catalogs, setCatalogs] = useState<Record<string, CatalogPayload>>({});
  const [modelQueries, setModelQueries] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function loadCatalog(name: string, offline = false) {
    setBusy(name);
    setErrors((prev) => ({ ...prev, [name]: "" }));
    try {
      const body = readRecord(await bridge.catalog(offline ? { name, source: "offline" } : { name })) as unknown as CatalogPayload;
      setCatalogs((prev) => ({ ...prev, [name]: body }));
      if (body.ok !== true) {
        setErrors((prev) => ({ ...prev, [name]: String(body.detail ?? body.error ?? "Catalogue request was not accepted.") }));
      }
    } catch (err) {
      setErrors((prev) => ({ ...prev, [name]: errMessage(err) }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Providers &amp; models</h2>
          <p className={s.muted}>Provider configuration is reported by the bridge. Model lists come from the live provider API when a key is available, or from the bundled offline catalogue on request.</p>
        </div>
        <Button onClick={providersQ.reload}><Icon name="refresh" size={14} /> Reload</Button>
      </div>

      <PanelState query={providersQ}>
        {(data) => {
          const providers = asArray<ProviderRow>(data, "providers");
          if (providers.length === 0) return <EmptyState icon={<Icon name="spark" />} title="No providers reported" description="The bridge returned an empty provider registry." />;
          return (
            <ul className={s.list}>
              {providers.map((p, i) => {
                const name = String(p.name ?? p.id ?? i);
                const catalog = catalogs[name];
                const metaByModel = new Map((catalog?.models_meta ?? []).map((m) => [String(m.id ?? ""), m]));
                const models = (catalog?.models ?? []).filter((m) => {
                  const q = (modelQueries[name] ?? "").trim().toLowerCase();
                  return !q || m.toLowerCase().includes(q);
                });
                return (
                  <li className={s.row} key={name}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}>{p.name ?? name}</h3>
                        <Badge tone={p.configured ? "success" : "warning"} dot>{p.configured ? "Configured" : "Not configured"}</Badge>
                        {p.session && <Badge tone="info">Session key active</Badge>}
                        {p.opt_in && <Badge tone="neutral">Opt-in provider</Badge>}
                      </div>
                      <dl className={s.facts}>
                        <div><dt>Key source</dt><dd className={s.mono}>{p.key_source ?? "none reported"}</dd></div>
                        <div><dt>Default model (reported)</dt><dd className={s.mono}>{p.default_model ?? "not reported"}</dd></div>
                        {p.base_url && <div><dt>Base URL</dt><dd className={s.mono}>{p.base_url}</dd></div>}
                      </dl>
                      {p.notes && <p className={s.rowMeta}>{p.notes}</p>}
                      {p.error && <p className={s.error} role="alert">{p.error}</p>}
                      <div className={s.actionRow}>
                        <Button size="sm" onClick={() => {
                          setExpanded(expanded === name ? null : name);
                          if (expanded !== name && !catalog) void loadCatalog(name);
                        }}>{expanded === name ? "Hide models" : "Load models"}</Button>
                        {catalog && <Badge tone="neutral">{catalog.source === "offline" ? "offline catalogue" : `live · ${String(catalog.key_source ?? "source not reported")}`}</Badge>}
                        {catalog?.catalog_version && <span className={s.muted}>catalog v{catalog.catalog_version}</span>}
                      </div>
                      {errors[name] && <p className={s.error} role="alert">{errors[name]}</p>}
                      {expanded === name && (
                        <div className={s.subPanel}>
                          {catalog?.ok !== true ? (
                            <div className={s.actionRow}>
                              <Button size="sm" variant="ghost" loading={busy === name} onClick={() => { void loadCatalog(name, true); }}>Browse offline catalogue</Button>
                              <span className={s.muted}>Live catalogues need a working key; the offline list needs none.</span>
                            </div>
                          ) : (
                            <>
                              <TextField type="search" label="Search models" placeholder="Filter model ids"
                                value={modelQueries[name] ?? ""} onChange={(e) => setModelQueries((prev) => ({ ...prev, [name]: e.target.value }))} />
                              <p className={s.muted}>{String(catalog.model_count ?? models.length)} model(s) reported by {catalog.source === "offline" ? "the offline catalogue" : "the live provider"}.</p>
                              {models.length === 0 ? <p className={s.muted}>No model matches this filter.</p> : (
                                <ul className={s.modelList}>
                                  {models.map((model) => {
                                    const meta = metaByModel.get(model);
                                    return (
                                      <li key={model} className={s.modelRow}>
                                        <code className={s.code}>{model}</code>
                                        {meta?.context_length && <Badge tone="neutral">{meta.context_length.toLocaleString()} ctx</Badge>}
                                        {Array.isArray(meta?.supported_parameters) && meta.supported_parameters.length > 0 && (
                                          <span className={s.muted}>params: {meta.supported_parameters.slice(0, 5).join(", ")}</span>
                                        )}
                                        {meta?.reasoning?.supported_efforts && meta.reasoning.supported_efforts.length > 0 && (
                                          <span className={s.muted}>efforts: {meta.reasoning.supported_efforts.join(", ")}</span>
                                        )}
                                      </li>
                                    );
                                  })}
                                </ul>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>
      <p className={s.footerNote}>There is no bridge route for a global default-model setting here. The "default model" shown above is reported by the bridge; per-agent and per-project model choices are managed in their own surfaces.</p>
    </div>
  );
}

interface AgentRow {
  id?: string;
  name?: string;
  provider?: string;
  model?: string;
  engine?: unknown;
  role?: string;
  [key: string]: unknown;
}

function agentModelState(input: unknown): AgentRow | null {
  // bots/:id/update answers with {bot: {...}}; accept a bare bot as well so a
  // changed bridge envelope cannot be mistaken for a failed save.
  const obj = readRecord(input);
  const bot = readRecord(obj.bot ?? obj);
  return typeof bot.id === "string" ? bot : null;
}

/**
 * Per-agent model settings. Every mutation goes through the real
 * `bots/:id/update` route with the `model` field the backend accepts
 * (fleet/service.py update_bot allow-list). Nothing is invented: a model id is
 * only offered after a real catalogue response, and the current value is the
 * one the bots list actually reported or the bridge confirmed on save.
 */
export function AgentModelsPanel() {
  const { notify } = useApp();
  const botsQ = useBridgeData<AgentRow[]>(async () => {
    const body = await bridge.listBots();
    return Array.isArray(body) ? body as AgentRow[] : asArray<AgentRow>(body, "bots");
  });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});
  const [catalogs, setCatalogs] = useState<Record<string, string[]>>({});
  const [catalogErrors, setCatalogErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [catalogBusy, setCatalogBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function currentModel(bot: AgentRow): string {
    const id = String(bot.id);
    const value = confirmed[id] ?? (typeof bot.model === "string" ? bot.model : "");
    return value.trim();
  }

  async function browseCatalog(bot: AgentRow) {
    const id = String(bot.id);
    const provider = String(bot.provider ?? "").trim();
    if (!provider) return;
    setCatalogBusy(id);
    setCatalogErrors((prev) => ({ ...prev, [id]: "" }));
    try {
      const body = readRecord(await bridge.catalog({ name: provider, source: "offline" })) as unknown as CatalogPayload;
      if (body.ok !== true) {
        setCatalogErrors((prev) => ({ ...prev, [id]: String(body.detail ?? body.error ?? "The bridge did not return a catalogue.") }));
        return;
      }
      setCatalogs((prev) => ({ ...prev, [id]: Array.isArray(body.models) ? body.models : [] }));
    } catch (err) {
      setCatalogErrors((prev) => ({ ...prev, [id]: errMessage(err) }));
    } finally {
      setCatalogBusy(null);
    }
  }

  async function applyModel(bot: AgentRow, model: string) {
    const id = String(bot.id);
    const name = bot.name ?? id;
    setBusy(id);
    setErrors((prev) => ({ ...prev, [id]: "" }));
    try {
      const updated = agentModelState(await bridge.updateBot(id, { model }));
      if (!updated) {
        setErrors((prev) => ({ ...prev, [id]: "The bridge did not confirm the agent update." }));
        return;
      }
      const value = typeof updated.model === "string" ? updated.model : model;
      setConfirmed((prev) => ({ ...prev, [id]: value }));
      setDrafts((prev) => ({ ...prev, [id]: value }));
      if (value) notify(`Model saved for ${name}: ${value}.`, "success");
      else notify(`Per-agent model cleared for ${name}; the provider default applies.`, "success");
    } catch (err) {
      setErrors((prev) => ({ ...prev, [id]: errMessage(err) }));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Agent models</h2>
          <p className={s.muted}>Each agent's model is stored by the bridge through the real agent-update route. A model is only selectable after the bridge returns it in a catalogue; leaving a model unset means the provider's own default applies.</p>
        </div>
        <Button onClick={botsQ.reload}><Icon name="refresh" size={14} /> Reload agents</Button>
      </div>

      <PanelState query={botsQ}>
        {(agentsData) => {
          const rows = agentsData.filter((bot) => typeof bot.id === "string");
          if (rows.length === 0) return <EmptyState icon={<Icon name="spark" />} title="No agents to configure" description="Create an agent on the Fleet surface first. Nothing is assumed about a model until an agent exists." />;
          return (
            <ul className={s.list}>
              {rows.map((bot) => {
                const id = String(bot.id);
                const name = bot.name ?? id;
                const model = currentModel(bot);
                const isEcho = bot.engine === "echo";
                const provider = typeof bot.provider === "string" ? bot.provider.trim() : "";
                const models = catalogs[id] ?? [];
                return (
                  <li className={s.row} key={id}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}>{name}</h3>
                        {isEcho ? <Badge tone="neutral">Scripted Echo agent</Badge>
                          : model ? <Badge tone="success" dot>Model: {model}</Badge>
                          : <Badge tone="warning" dot>Provider default</Badge>}
                        {provider && <Badge tone="neutral">{provider}</Badge>}
                      </div>
                      {isEcho ? (
                        <p className={s.rowMeta}>This agent uses the scripted Echo harness and does not call a model, so no model control is shown. Switch it to a provider agent on the Fleet surface to use a real model.</p>
                      ) : (
                        <>
                          <p className={s.rowMeta}>{model
                            ? `This agent sends ${model} to ${provider || "its provider"}.`
                            : "No per-agent model is set. The bridge falls back to the provider's own default."}</p>
                          <TextField
                            label={`Model for ${name}`}
                            placeholder="Model id, or leave empty for the provider default"
                            value={drafts[id] ?? model}
                            onChange={(e) => setDrafts((prev) => ({ ...prev, [id]: e.target.value }))}
                          />
                          <div className={s.actionRow}>
                            <Button size="sm" variant="primary" loading={busy === id}
                              onClick={() => { void applyModel(bot, (drafts[id] ?? model).trim()); }}>
                              Save model for {name}
                            </Button>
                            {model && (
                              <Button size="sm" variant="ghost" disabled={busy !== null}
                                onClick={() => { void applyModel(bot, ""); }}>
                                Clear model for {name}
                              </Button>
                            )}
                            {provider && (
                              <Button size="sm" variant="ghost" loading={catalogBusy === id}
                                onClick={() => { void browseCatalog(bot); }}>
                                Browse offline catalogue
                              </Button>
                            )}
                            {!provider && <span className={s.muted}>Provider not reported — catalogue selection is unavailable.</span>}
                          </div>
                          {models.length > 0 && (
                            <label className={s.selectLabel}>Pick a model from the offline catalogue for {provider}
                              <select value={drafts[id] ?? model} onChange={(e) => setDrafts((prev) => ({ ...prev, [id]: e.target.value }))}>
                                <option value="">Use provider default</option>
                                {models.map((m) => <option key={m} value={m}>{m}</option>)}
                              </select>
                            </label>
                          )}
                          {catalogs[id] && models.length === 0 && <p className={s.muted}>The offline catalogue returned no models for {provider}.</p>}
                          {catalogErrors[id] && <p className={s.error} role="alert">{catalogErrors[id]}</p>}
                        </>
                      )}
                      {errors[id] && <p className={s.error} role="alert">{errors[id]}</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>

      <p className={s.footerNote}>There is no bridge route for a global default-model setting. The save above writes only this agent's <code>model</code> field through <code>bots/:id/update</code>; per-project defaults are managed on the Code surface.</p>
    </div>
  );
}

type CredentialResult = { ok: boolean; text: string };
type PendingRemoval = { provider: string; kind: "session" | "saved" };

export function CredentialsPanel() {
  const { notify } = useApp();
  const providersQ = useBridgeData(() => bridge.providers());
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, CredentialResult>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [hints, setHints] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<PendingRemoval | null>(null);

  function keyFor(provider: string): string { return (keys[provider] ?? "").trim(); }

  function setError(provider: string, message: string) {
    setErrors((prev) => ({ ...prev, [provider]: message }));
    setResults((prev) => ({ ...prev, [provider]: { ok: false, text: message } }));
  }

  async function submit(provider: string, persist: boolean) {
    const key = keyFor(provider);
    if (!key) { setError(provider, "Enter a key first."); return; }
    const operation = persist ? "save" : "session";
    setBusy(`${provider}:${operation}`);
    setErrors((prev) => ({ ...prev, [provider]: "" }));
    try {
      const body = readRecord(persist
        ? await bridge.saveProvider({ name: provider, key })
        : await bridge.setCredential({ name: provider, key }));
      if (body.ok !== true) {
        setError(provider, String(body.detail ?? body.error ?? "The bridge did not accept the key."));
        return;
      }
      const count = typeof body.model_count === "number" ? ` (${body.model_count} models verified)` : "";
      const text = persist
        ? `Saved to this machine${count}. ${String(body.note ?? "")}`.trim()
        : `Accepted for this bridge process only${count}. ${String(body.note ?? "")}`.trim();
      setResults((prev) => ({ ...prev, [provider]: { ok: true, text } }));
      if (typeof body.hint === "string") setHints((prev) => ({ ...prev, [provider]: `••••${body.hint}` }));
      notify(`${provider}: key ${persist ? "saved on this machine" : "verified for this session"}${count}.`, "success");
      providersQ.reload();
    } catch (err) {
      setError(provider, errMessage(err));
    } finally {
      // The secret is never kept in this component after a submission attempt.
      setKeys((prev) => ({ ...prev, [provider]: "" }));
      setBusy(null);
    }
  }

  async function confirmRemove() {
    if (!pending) return;
    const { provider, kind } = pending;
    setBusy(`${provider}:remove-${kind}`);
    try {
      const body = readRecord(kind === "session"
        ? await bridge.clearCredential({ name: provider })
        : await bridge.removeProvider({ name: provider }));
      if (body.ok !== true) {
        setError(provider, String(body.detail ?? body.error ?? "The bridge did not confirm removal."));
        return;
      }
      setResults((prev) => ({ ...prev, [provider]: { ok: true, text: kind === "session" ? "Session key cleared." : "Saved key removed from Keel settings." } }));
      notify(kind === "session" ? `${provider}: session key cleared.` : `${provider}: saved key removed.`, "success");
      if (kind === "saved") setHints((prev) => { const next = { ...prev }; delete next[provider]; return next; });
      setPending(null);
      providersQ.reload();
    } catch (err) {
      setError(provider, errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Credentials</h2>
          <p className={s.muted}>Session keys are held in the bridge process memory only and disappear when it restarts. Saved keys are encrypted by the bridge in <code>~/.keel/settings.json</code> on this machine. This browser stores no key.</p>
        </div>
        <Button onClick={providersQ.reload}><Icon name="refresh" size={14} /> Reload</Button>
      </div>

      <PanelState query={providersQ}>
        {(data) => {
          const providers = asArray<ProviderRow>(data, "providers");
          if (providers.length === 0) return <EmptyState icon={<Icon name="shield" />} title="No providers reported" description="There is nothing to configure until the bridge reports a provider." />;
          return (
            <ul className={s.list}>
              {providers.map((p, i) => {
                const provider = String(p.name ?? p.id ?? i);
                const result = results[provider];
                return (
                  <li className={s.row} key={provider}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}>{p.name ?? provider}</h3>
                        <Badge tone={p.configured ? "success" : "warning"} dot>{p.configured ? "Key present" : "No key reported"}</Badge>
                        {p.session && <Badge tone="info">Session key active</Badge>}
                        {hints[provider] && <Badge tone="neutral">Saved {hints[provider]}</Badge>}
                      </div>
                      <p className={s.rowMeta}>Key source: <code className={s.code}>{p.key_source ?? "none"}</code>. Shell environment variables, when present, take precedence over saved keys.</p>
                      <TextField
                        label={`API key for ${provider}`}
                        type="password"
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="Paste a key — never prefilled or shown again"
                        value={keys[provider] ?? ""}
                        onChange={(e) => setKeys((prev) => ({ ...prev, [provider]: e.target.value }))}
                      />
                      <div className={s.actionRow}>
                        <Button size="sm" loading={busy === `${provider}:session`} onClick={() => { void submit(provider, false); }}>Verify for this session</Button>
                        <Button size="sm" variant="primary" loading={busy === `${provider}:save`} onClick={() => { void submit(provider, true); }}>Save on this machine</Button>
                        <Button size="sm" variant="ghost" onClick={() => setPending({ provider, kind: "session" })}>Forget session key</Button>
                        <Button size="sm" variant="ghost" onClick={() => setPending({ provider, kind: "saved" })}>Remove saved key</Button>
                      </div>
                      {result && <p className={result.ok ? s.success : s.error} role="status">{result.text}</p>}
                      {errors[provider] && !result && <p className={s.error} role="alert">{errors[provider]}</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="shield" size={16} /> Secure storage, as exposed by the bridge</div>
        <p>The validation call goes to the provider to fetch models; the bridge reports the model count and never returns the key. Keys typed here are cleared from the input immediately, never written to browser storage, and never shown in a notification. "Last checked" is not reported by this route, so it is not displayed.</p>
      </Card>

      <Dialog open={pending !== null} onClose={() => setPending(null)} title={pending?.kind === "saved" ? "Remove saved key?" : "Forget session key?"}
        footer={<>
          <Button variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
          <Button variant="danger" loading={busy !== null} onClick={() => { void confirmRemove(); }}>Confirm removal</Button>
        </>}>
        <p>
          {pending?.kind === "saved"
            ? `This deletes the key saved for ${pending.provider} in Keel's local settings. Environment variables are never touched.`
            : `This clears the in-memory session key for ${pending?.provider ?? "this provider"}. The bridge will report whether a key existed.`}
        </p>
      </Dialog>
    </div>
  );
}

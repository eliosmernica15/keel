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

"use client";

// Skills: real discovery + real skills/manage state (which is where `enabled`,
// path and hash come from). Enable/install/remove call real bridge routes.

import React, { useMemo, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, SectionTitle, TextField, Toggle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { CapabilityState } from "@/lib/types";
import s from "./capabilities.module.css";
import { asArray, PanelState, readRecord, safeResult, scopeLabel, StateBadge, useBridgeData } from "./capabilitiesShared";

interface SkillRow {
  id?: string;
  name?: string;
  description?: string;
  scope?: string;
  trusted?: boolean;
  enabled?: boolean;
  injection_suspects?: number | string[];
  source?: string;
  path?: string;
  sha256?: string;
  version?: string;
  error?: string;
  [key: string]: unknown;
}

function suspectCount(value: number | string[] | undefined): number {
  if (Array.isArray(value)) return value.length;
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function skillState(row: SkillRow): { state: CapabilityState; label?: string; reason: string } {
  if (row.error) return { state: "blocked", reason: `Skill could not be loaded: ${row.error}` };
  if (row.trusted === false) return { state: "blocked", reason: "Untrusted source — review provenance before relying on this skill." };
  if (suspectCount(row.injection_suspects) > 0) {
    return { state: "requires-setup", reason: `${suspectCount(row.injection_suspects)} injection suspect(s) reported — review before use.` };
  }
  if (row.enabled === false) return { state: "unconfigured", label: "Disabled", reason: "Disabled in the skill manager. Enable it to inject this skill." };
  if (typeof row.trusted !== "boolean" && row.injection_suspects === undefined) {
    return { state: "unconfigured", label: "Status not reported", reason: "The bridge did not report trust or injection data for this skill." };
  }
  return { state: "available", reason: "Trusted source; no injection suspects reported." };
}

export default function SkillsPanel() {
  const { notify } = useApp();
  const skillsQ = useBridgeData(() => bridge.skills());
  const managedQ = useBridgeData(() => bridge.skillsManage());
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<SkillRow | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [installOpen, setInstallOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<SkillRow | null>(null);
  const [source, setSource] = useState("");
  const [scope, setScope] = useState<"user" | "project">("user");
  const [name, setName] = useState("");
  const [projectRoot, setProjectRoot] = useState("");
  const [installError, setInstallError] = useState<string | null>(null);

  const rows = useMemo<SkillRow[]>(() => {
    const discovered = asArray<SkillRow>(skillsQ.data, "skills");
    const managed = asArray<SkillRow>(managedQ.data, "skills");
    const byName = new Map(managed.map((m) => [String(m.name ?? ""), m]));
    const merged = discovered.map((row) => ({ ...row, ...(byName.get(String(row.name ?? "")) ?? {}) }));
    const known = new Set(discovered.map((row) => String(row.name ?? "")));
    return [...merged, ...managed.filter((m) => !known.has(String(m.name ?? "")))];
  }, [skillsQ.data, managedQ.data]);

  const visible = rows.filter((row) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [row.name, row.description, row.scope, row.source]
      .filter((v): v is string => typeof v === "string")
      .some((v) => v.toLowerCase().includes(q));
  });

  function reloadAll() { skillsQ.reload(); managedQ.reload(); }

  function actionError(name: string, message: string) {
    setErrors((prev) => ({ ...prev, [name]: message }));
  }

  async function toggle(row: SkillRow) {
    const skillName = row.name;
    if (!skillName || busy) return;
    setBusy(skillName);
    setErrors((prev) => ({ ...prev, [skillName]: "" }));
    try {
      const res = readRecord(await bridge.enableSkill({ name: skillName, enabled: row.enabled === false }));
      if (res.ok !== true) {
        actionError(skillName, String(res.detail ?? res.error ?? "The bridge did not confirm the change."));
        return;
      }
      notify(`${skillName} ${row.enabled === false ? "enabled" : "disabled"}.`, "success");
      reloadAll();
    } catch (err) {
      actionError(skillName, errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function confirmInstall() {
    if (!source.trim()) { setInstallError("A source is required (local path or URL)."); return; }
    setBusy("__install");
    setInstallError(null);
    try {
      const payload: Record<string, unknown> = { source: source.trim(), scope };
      if (name.trim()) payload.name = name.trim();
      if (scope === "project" && projectRoot.trim()) payload.project_root = projectRoot.trim();
      const res = readRecord(await bridge.installSkill(payload));
      if (res.ok !== true) {
        setInstallError(String(res.detail ?? res.error ?? "The bridge did not confirm the install."));
        return;
      }
      const installed = String(res.name ?? name.trim() ?? "Skill");
      notify(`${installed} installed (${scope} scope).`, "success");
      setInstallOpen(false);
      setSource(""); setName(""); setProjectRoot("");
      reloadAll();
    } catch (err) {
      setInstallError(errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function confirmRemove() {
    if (!removeTarget?.name) return;
    const target = removeTarget;
    setBusy("__remove");
    try {
      const payload: Record<string, unknown> = { name: target.name, scope: target.scope ?? "user" };
      if (target.scope === "project" && projectRoot.trim()) payload.project_root = projectRoot.trim();
      const res = readRecord(await bridge.removeSkill(payload));
      if (res.ok !== true && res.removed === undefined) {
        actionError(String(target.name), String(res.detail ?? res.error ?? "The bridge did not confirm the removal."));
        return;
      }
      notify(`${target.name} removed.`, "success");
      setRemoveTarget(null);
      reloadAll();
    } catch (err) {
      actionError(String(target.name), errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Skills</h2>
          <p className={s.muted}>Discovered from the bridge. Trust, injection scan and enable state are read from real bridge data.</p>
        </div>
        <div className={s.actionRow}>
          <Button onClick={() => { setInstallOpen(true); setInstallError(null); }}><Icon name="plus" size={14} /> Install skill</Button>
          <IconButton label="Reload skills" onClick={reloadAll}><Icon name="refresh" size={15} /></IconButton>
        </div>
      </div>

      {managedQ.error && <p className={s.staleError} role="status">Enable state unavailable: {managedQ.error}. Toggles are disabled until the manager responds.</p>}

      <PanelState query={skillsQ}>
        {() => (
          <>
            <TextField
              type="search"
              label="Search skills"
              placeholder="Filter by name, description or scope"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className={s.filter}
            />
            {visible.length === 0 ? (
              <EmptyState icon={<Icon name="spark" />} title={rows.length ? "No skills match your search" : "No skills discovered"}
                description={rows.length ? "Try a different term." : "Keel found no SKILL.md files in the bundled or user skill folders."} />
            ) : (
              <ul className={s.list}>
                {visible.map((row, i) => {
                  const key = String(row.id ?? row.name ?? i);
                  const status = skillState(row);
                  const disabledToggle = !row.name || managedQ.data === null || busy !== null;
                  return (
                    <li className={s.row} key={key}>
                      <div className={s.rowMain}>
                        <div className={s.rowTitleLine}>
                          <h3 className={s.rowTitle}>{row.name ?? "Unnamed skill"}</h3>
                          <StateBadge state={status.state} label={status.label} />
                          <Badge tone="neutral">{scopeLabel(row.scope)}</Badge>
                          {row.version && <Badge tone="neutral">v{row.version}</Badge>}
                        </div>
                        <p className={s.rowDesc}>{row.description ?? "No description reported by the bridge."}</p>
                        <p className={s.rowMeta}>{status.reason}</p>
                        {suspectCount(row.injection_suspects) > 0 && (
                          <p className={s.warning}><Icon name="warning" size={14} /> Injection scan: {suspectCount(row.injection_suspects)} suspect(s)</p>
                        )}
                        {errors[row.name ?? ""] && <p className={s.error} role="alert">{errors[row.name ?? ""]}</p>}
                      </div>
                      <div className={s.rowActions}>
                        <Button size="sm" variant="ghost" onClick={() => setDetail(row)}>Details</Button>
                        <div title={managedQ.data === null ? "Enable state is not available" : undefined}>
                          <Toggle
                            checked={row.enabled !== false}
                            disabled={disabledToggle}
                            onChange={() => { void toggle(row); }}
                            label={`Enable ${row.name ?? "skill"}`}
                          />
                        </div>
                        <IconButton label={`Remove ${row.name ?? "skill"}`} onClick={() => setRemoveTarget(row)} disabled={busy !== null}>
                          <Icon name="trash" size={15} />
                        </IconButton>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <p className={s.footerNote}>Skill scope and trust come from discovery; enabled/path/hash come from <code>skills/manage</code>. Remove only affects installed skills, never bundled ones.</p>
          </>
        )}
      </PanelState>

      <Dialog open={detail !== null} onClose={() => setDetail(null)} title={detail?.name ?? "Skill details"} footer={<Button onClick={() => setDetail(null)}>Close</Button>}>
        {detail && (
          <div className={s.detail}>
            <p>{detail.description ?? "No description reported."}</p>
            <dl className={s.dl}>
              <div><dt>Scope</dt><dd>{scopeLabel(detail.scope)}</dd></div>
              <div><dt>Trusted</dt><dd>{typeof detail.trusted === "boolean" ? (detail.trusted ? "Yes" : "No") : "Not reported"}</dd></div>
              <div><dt>Enabled</dt><dd>{typeof detail.enabled === "boolean" ? (detail.enabled ? "Yes" : "No") : "Not reported"}</dd></div>
              <div><dt>Version</dt><dd>{detail.version ?? "Not reported"}</dd></div>
              <div><dt>Source path</dt><dd className={s.mono}>{detail.path ?? detail.source ?? "Not reported"}</dd></div>
              <div><dt>SHA-256</dt><dd className={s.mono}>{detail.sha256 ?? "Not reported"}</dd></div>
              <div><dt>Injection suspects</dt><dd>{safeResult(detail.injection_suspects ?? 0)}</dd></div>
              {detail.error && <div><dt>Load error</dt><dd className={s.error}>{detail.error}</dd></div>}
            </dl>
          </div>
        )}
      </Dialog>

      <Dialog open={installOpen} onClose={() => setInstallOpen(false)} title="Install a skill"
        footer={<>
          <Button variant="ghost" onClick={() => setInstallOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={busy === "__install"} onClick={() => { void confirmInstall(); }}>Install</Button>
        </>}>
        <p className={s.muted}>The bridge copies the skill into the selected scope. A local path or a URL is accepted by the backend.</p>
        <TextField label="Source (path or URL)" value={source} onChange={(e) => setSource(e.target.value)} placeholder="C:\\path\\to\\skill or https://…" />
        <div className={s.grid2}>
          <label className={s.selectLabel}>Scope
            <select value={scope} onChange={(e) => setScope(e.target.value as "user" | "project")}>
              <option value="user">User</option>
              <option value="project">Project</option>
            </select>
          </label>
          <TextField label="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {scope === "project" && <TextField label="Project root (optional)" value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} />}
        {installError && <p className={s.error} role="alert">{installError}</p>}
      </Dialog>

      <Dialog open={removeTarget !== null} onClose={() => setRemoveTarget(null)} title="Remove skill?"
        footer={<>
          <Button variant="ghost" onClick={() => setRemoveTarget(null)}>Cancel</Button>
          <Button variant="danger" loading={busy === "__remove"} onClick={() => { void confirmRemove(); }}>Remove skill</Button>
        </>}>
        <p>This removes <strong>{removeTarget?.name}</strong> from the <strong>{scopeLabel(removeTarget?.scope)}</strong> scope. Bundled skills are never removed. The bridge will report the actual result.</p>
        {removeTarget?.scope === "project" && <TextField label="Project root" value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} />}
      </Dialog>
    </div>
  );
}

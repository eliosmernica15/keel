"use client";

// Permission mode, workspace trust and network rules. Modes are the four the
// app's composer actually sends; trust calls the real bridge route.

import React, { useEffect, useState } from "react";
import { Badge, Button, Card, Dialog, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import s from "./settings.module.css";
import { asArray, PanelState, readRecord, useBridgeData } from "./settingsShared";

type Mode = "build" | "acceptEdits" | "plan" | "autopilot";
const MODES: Array<{ value: Mode; label: string; consequence: string }> = [
  { value: "build", label: "Build", consequence: "Keel asks before tool actions. The safe default for unfamiliar workspaces." },
  { value: "acceptEdits", label: "Accept edits", consequence: "File writes proceed without asking; shell commands still require approval." },
  { value: "plan", label: "Plan", consequence: "Read-only exploration — the agent plans but does not change files." },
  { value: "autopilot", label: "Autopilot", consequence: "The agent runs without asking first. Tier-2 and deny rules still bind." },
];

export function PermissionsPanel() {
  const { notify } = useApp();
  const [mode, setMode] = useState<Mode>("build");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("keel-mode");
      if (MODES.some((m) => m.value === stored)) setMode(stored as Mode);
    } catch { /* storage unavailable; keep the safe default */ }
  }, []);

  function choose(next: Mode) {
    setMode(next);
    try { window.localStorage.setItem("keel-mode", next); } catch { /* ignore */ }
    notify(`Permission mode set to ${MODES.find((m) => m.value === next)?.label ?? next}.`, "success");
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Permission mode</h2>
          <p className={s.muted}>These are the four modes the composer in this app actually sends. Unsupported modes are not offered.</p>
        </div>
        <Badge tone="info">Local preference</Badge>
      </div>

      <fieldset className={s.modeFieldset}>
        <legend className="sr-only">Permission mode</legend>
        {MODES.map((option) => (
          <label key={option.value} className={`${s.modeOption} ${mode === option.value ? s.modeActive : ""}`}>
            <input type="radio" name="permission-mode" value={option.value} checked={mode === option.value} onChange={() => choose(option.value)} />
            <span>
              <strong>{option.label}</strong>
              <span className={s.rowMeta}>{option.consequence}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="shield" size={16} /> What the runtime still enforces</div>
        <p>Permission mode is a UI preference applied to new composer sessions. Regardless of the choice, the Python bridge keeps its Tier-1 allow/ask/deny checks, Tier-2 confirmations and standing policies — the renderer cannot override them.</p>
      </Card>
    </div>
  );
}

interface ProjectRow {
  id?: string;
  name?: string;
  path?: string;
  trusted?: boolean | number;
  last_opened_at?: string;
  [key: string]: unknown;
}

function isTrusted(value: unknown): boolean {
  return value === true || Number(value) === 1;
}

function riskyPath(path: string): string | null {
  const normalized = path.trim().toLowerCase().replace(/\/+/g, "/");
  const withoutTrailing = normalized.replace(/\/+$/, "");
  if (["", "/", "c:", "c:/", "c:/users", "c:/windows", "c:/program files", "/etc", "/system", "/users"].includes(withoutTrailing)) {
    return "This is a root, home or system location. Trusting it can expose a very large tree — review it carefully.";
  }
  return null;
}

export function TrustPanel() {
  const { notify } = useApp();
  const projectsQ = useBridgeData(() => bridge.projects());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ project: ProjectRow; trusted: boolean } | null>(null);

  async function confirmTrust() {
    if (!pending?.project?.id) return;
    const { project, trusted } = pending;
    const id = String(project.id);
    setBusy(id);
    setError(null);
    try {
      const body = readRecord(await bridge.trustProject(id, trusted));
      if (typeof body.error === "string") { setError(body.error); return; }
      notify(`${project.name ?? project.path ?? "Workspace"} ${trusted ? "trusted" : "untrusted"}.`, "success");
      setPending(null);
      await projectsQ.reload();
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Workspace trust</h2>
          <p className={s.muted}>Keel only reads and writes folders you have explicitly trusted. Trust is stored by the bridge and can be revoked here.</p>
        </div>
        <Button onClick={projectsQ.reload}><Icon name="refresh" size={14} /> Reload</Button>
      </div>
      {error && <p className={s.error} role="alert">{error}</p>}

      <PanelState query={projectsQ}>
        {(data) => {
          const projects = asArray<ProjectRow>(data, "projects");
          return projects.length === 0 ? (
            <EmptyState icon={<Icon name="folder" />} title="No projects in the registry"
              description="Add a workspace from the Projects page in the Cowork surface. Nothing is trusted automatically." />
          ) : (
            <ul className={s.list}>
              {projects.map((project, i) => {
                const trusted = isTrusted(project.trusted);
                const warning = typeof project.path === "string" ? riskyPath(project.path) : null;
                return (
                  <li className={s.row} key={String(project.id ?? i)}>
                    <div className={s.rowMain}>
                      <div className={s.rowTitleLine}>
                        <h3 className={s.rowTitle}>{project.name ?? project.path ?? "Unnamed project"}</h3>
                        <Badge tone={trusted ? "success" : "warning"} dot>{trusted ? "Trusted" : "Not trusted"}</Badge>
                      </div>
                      <p className={s.mono}>{project.path ?? "Path not reported"}</p>
                      {project.last_opened_at && <p className={s.rowMeta}>Last opened: {project.last_opened_at}</p>}
                      {warning && <p className={s.warning}><Icon name="warning" size={14} /> {warning}</p>}
                    </div>
                    <div className={s.rowActions}>
                      <Button size="sm" variant={trusted ? "ghost" : "primary"} onClick={() => setPending({ project, trusted: !trusted })} disabled={busy !== null}>
                        {trusted ? "Revoke trust…" : "Trust this folder…"}
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </PanelState>

      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="info" size={16} /> Symlinks and scope</div>
        <p>This bridge route reports the registered path and its trust flag, but not symlink targets, so no symlink verdict is shown here. Verify the absolute path before trusting it. Adding or removing projects is handled by the Projects surface; this page only changes the trust flag for existing entries.</p>
      </Card>

      <Dialog open={pending !== null} onClose={() => setPending(null)} title={pending?.trusted ? "Trust this workspace?" : "Revoke workspace trust?"}
        footer={<>
          <Button variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
          <Button variant={pending?.trusted ? "primary" : "danger"} loading={busy !== null} onClick={() => { void confirmTrust(); }}>
            {pending?.trusted ? "Trust folder" : "Revoke trust"}
          </Button>
        </>}>
        <p className={s.mono}>{pending?.project.path ?? "Path not reported"}</p>
        <p>
          {pending?.trusted
            ? "Keel will allow read/write/execute tools in this folder. No files are changed by the trust flag itself."
            : "Tools will no longer be allowed to act in this folder until you trust it again. Existing files are not deleted."}
        </p>
      </Dialog>
    </div>
  );
}

export function NetworkPanel() {
  return (
    <div className={s.panel}>
      <div className={s.sectionHead}><div>
        <h2>Network &amp; egress</h2>
        <p className={s.muted}>What this bridge build can and cannot show about network rules.</p>
      </div></div>
      <EmptyState
        icon={<Icon name="link" size={26} />}
        title="No egress-rule API is exposed by this bridge build"
        description="Network egress and command safety are enforced by the Python runtime, not the renderer. Because the bridge exposes no rule list or rule-edit route, this page does not invent domains, rules or a dry-run button. Denied tool attempts are reported in the run's own permission events."
      />
      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="info" size={16} /> Where controls live</div>
        <p>Provider connections are configured on the Providers and Credentials pages. MCP connector endpoints are configured on the Capabilities page. Neither implies a general network allowlist in this build.</p>
      </Card>
    </div>
  );
}

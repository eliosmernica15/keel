"use client";

// First-run setup. Every action here calls a real bridge route or real global
// state; the tour only narrates capabilities the user performs themselves.
// No agent run, approval, file change or connection is ever simulated.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { useApp } from "@/lib/state";
import { Badge, Button, Card, IconButton, Progress, TextField } from "@/components/ui";
import { Icon, KeelMark, type IconName } from "@/components/icons";
import type { Surface } from "@/lib/types";
import { OPEN_HELP_EVENT } from "./SetupChecklist";
import {
  STEP_IDS, ITEM_IDS, readMode, readStep, restartAtStep, updateChecklist,
  useChecklist, writeMode, writeStep,
  type Checklist, type ItemId, type Mode, type StepId,
} from "./progress";
import s from "./onboarding.module.css";

/* ------------------------------ small helpers ------------------------------ */

function rows<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const found = (payload as Record<string, unknown>)[key];
    if (Array.isArray(found)) return found as T[];
  }
  return [];
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function trusted(v: unknown): boolean {
  return v === true || v === 1;
}

function isAbsolutePath(p: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(p) || p.startsWith("\\\\") || p.startsWith("/");
}

type StatusKind = "idle" | "loading" | "success" | "error" | "info";
interface Status { kind: StatusKind; message: string }
const IDLE: Status = { kind: "idle", message: "" };

function StatusLine({ status }: { status: Status }) {
  if (status.kind === "idle") return null;
  const cls = status.kind === "error" ? s.statusError
    : status.kind === "success" ? s.statusSuccess
      : status.kind === "loading" ? s.statusLoading : s.statusInfo;
  return (
    <p className={`${s.status} ${cls}`} role={status.kind === "error" ? "alert" : "status"}>
      <Icon name={status.kind === "error" ? "warning" : status.kind === "success" ? "check" : "info"} size={14} />
      <span>{status.message}</span>
    </p>
  );
}

interface ProviderRow { id?: string; name?: string; configured?: boolean; connected?: boolean; error?: string }
interface ProjectRow { id?: string; name?: string; path?: string; trusted?: boolean | number }
interface SkillRow { name?: string; id?: string; description?: string; scope?: string; trusted?: boolean | number; injection_suspects?: number }
interface ServerRow { name?: string; id?: string; transport?: string; scope?: string; command?: string; url?: string; state?: string }

interface CredentialResult {
  ok?: boolean; error?: string; detail?: string; note?: string; hint?: string;
  model_count?: number; models?: unknown[]; provider?: string;
}

const MODE_OPTIONS: Array<{ value: Mode; label: string; description: string }> = [
  {
    value: "plan", label: "Plan",
    description: "Safest default. Read-only: Keel can inspect files but mutations, shell commands and network calls are denied until you switch modes.",
  },
  {
    value: "build", label: "Build",
    description: "Normal working mode. Keel can edit the trusted workspace; tools still follow Keel's permission prompts and safety rules.",
  },
  {
    value: "acceptEdits", label: "Accept edits",
    description: "File edits are accepted without asking each time. Shell commands and network access still ask as usual.",
  },
  {
    value: "autopilot", label: "Autopilot",
    description: "Most hands-off: skips the consent pause. Deny rules, hooks and standing policies still bind, so it is not a safety bypass.",
  },
];

const SURFACE_CHOICES: Array<{ surface: Surface; icon: IconName; title: string; description: string }> = [
  { surface: "cowork", icon: "cowork", title: "Start with Cowork", description: "General work, research and multi-step tasks in one conversation." },
  { surface: "code", icon: "code", title: "Start with Code", description: "Work inside a trusted local folder with files, diffs and a terminal." },
  { surface: "fleet", icon: "fleet", title: "Set up Fleet", description: "Manage named agents, groups, tasks and scheduled routines." },
];

// All four work surfaces are introduced here. Duet is deliberately not a
// "start here" choice on the welcome step: it is a split view of the two
// surfaces below, so picking it before either exists would be misleading.
const SURFACE_TILES: Array<{ surface: Surface; icon: IconName; title: string; description: string }> = [
  { surface: "cowork", icon: "cowork", title: "Cowork", description: "One conversation for research, writing and multi-step work." },
  { surface: "code", icon: "code", title: "Code", description: "Real files, read-only review and a guarded terminal in a folder you trust." },
  { surface: "duet", icon: "duet", title: "Duet", description: "Cowork and Code side by side, so you can discuss a change while you edit it." },
  { surface: "fleet", icon: "fleet", title: "Fleet", description: "Named agents, groups, tasks and scheduled routines you can inspect." },
];

// Which checklist item a step's "Skip for now" defers. A skipped item is
// recorded as deferred so the sidebar checklist stops showing it, while the
// required-progress counter still counts only genuinely completed items.
const STEP_ITEM: Partial<Record<StepId, ItemId>> = {
  welcome: "surface",
  provider: "provider",
  workspace: "workspace",
  permission: "permission",
  capabilities: "capabilities",
  channels: "channels",
  tour: "tour",
};

/* ------------------------------- component -------------------------------- */

export default function Onboarding({ onDone }: { onDone: () => void }) {
  const { setSurface, notify, completeOnboarding, restartOnboarding, reduceMotion, registerCommands } = useApp();
  const checklist = useChecklist();
  const [step, setStep] = useState<StepId>(() => readStep());
  const stepIndex = Math.max(0, STEP_IDS.indexOf(step));
  const headingRef = useRef<HTMLHeadingElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // provider step
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [providersStatus, setProvidersStatus] = useState<Status>(IDLE);
  const [providerName, setProviderName] = useState("");
  const [secret, setSecret] = useState("");
  const [credentialStatus, setCredentialStatus] = useState<Status>(IDLE);
  const [sessionVerified, setSessionVerified] = useState(false);
  const [saveStatus, setSaveStatus] = useState<Status>(IDLE);
  const [catalog, setCatalog] = useState<{ loading: boolean; count: number | null; version: string; error: string }>(
    { loading: false, count: null, version: "", error: "" },
  );

  // workspace step
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [projectsStatus, setProjectsStatus] = useState<Status>(IDLE);
  const [pathInput, setPathInput] = useState("");
  const [addStatus, setAddStatus] = useState<Status>(IDLE);
  const [trustStatus, setTrustStatus] = useState<Status>(IDLE);
  const [pendingTrustId, setPendingTrustId] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState("");

  // permission step
  const [mode, setMode] = useState<Mode>(() => readMode() ?? "plan");

  // capabilities step
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [servers, setServers] = useState<ServerRow[]>([]);
  const [capsStatus, setCapsStatus] = useState<Status>(IDLE);

  const current = step;
  const requiredDoneCount = useMemo(
    () => ITEM_IDS.filter((id) => checklist[id] === "done" && ["surface", "provider", "workspace", "permission"].includes(id)).length,
    [checklist],
  );

  const goto = useCallback((next: StepId) => {
    writeStep(next);
    setStep(next);
    setCredentialStatus(IDLE);
    setSaveStatus(IDLE);
    setAddStatus(IDLE);
    setTrustStatus(IDLE);
  }, []);

  const advance = useCallback((skipItem?: ItemId) => {
    if (skipItem) updateChecklist({ [skipItem]: "deferred" } as Partial<Checklist>);
    const i = Math.max(0, STEP_IDS.indexOf(current));
    goto(STEP_IDS[Math.min(i + 1, STEP_IDS.length - 1)]);
  }, [current, goto]);

  const close = useCallback(() => {
    completeOnboarding();
    onDone();
  }, [completeOnboarding, onDone]);

  // "Skip for now" is a real decision: it records the current item as deferred
  // and moves on. On the final step it means "Finish later" — close without
  // claiming the tour was taken, so the setup stays resumable.
  const skipCurrent = useCallback(() => {
    if (stepIndex >= STEP_IDS.length - 1) { close(); return; }
    advance(STEP_ITEM[current]);
  }, [advance, close, current, stepIndex]);

  const finish = useCallback(() => {
    updateChecklist({ tour: "done" });
    completeOnboarding();
    onDone();
  }, [completeOnboarding, onDone]);

  // Keyboard: Escape closes; Tab stays inside the dialog; focus moves to the
  // heading whenever the step changes. No information is hidden behind motion.
  useEffect(() => {
    const node = rootRef.current as HTMLDivElement | null;
    if (!node) return;
    const focusables = (): HTMLElement[] => Array.from(node.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    ));
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    headingRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey, true);
  }, [step, close]);

  // Stay in sync when the shell or the sidebar checklist jumps to a step.
  useEffect(() => {
    const sync = () => setStep(readStep());
    window.addEventListener("keel-onboarding-change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("keel-onboarding-change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // Expose a real "Take the tour" command; Settings can also call
  // useApp().restartOnboarding() and SetupChecklist links to it.
  useEffect(() => {
    registerCommands([{
      id: "onboarding.tour",
      label: "Take the tour",
      group: "Help",
      run: () => { restartAtStep("tour"); restartOnboarding(); },
    }]);
  }, [registerCommands, restartOnboarding]);

  // Clear the secret from memory when the provider step is left.
  useEffect(() => () => setSecret(""), [current === "provider"]);

  /* --------------------------- real data loaders --------------------------- */

  const loadProviders = useCallback(async () => {
    setProvidersStatus({ kind: "loading", message: "Reading the provider registry from the local bridge…" });
    try {
      const data = await bridge.providers();
      const list = rows<ProviderRow>(data, "providers");
      setProviders(list);
      setProvidersStatus(list.length
        ? IDLE
        : { kind: "info", message: "The bridge reports no providers. You can still finish setup and add a key later in Settings → Providers." });
    } catch (err) {
      setProvidersStatus({
        kind: "error",
        message: isBridgeUnavailable(err)
          ? "The local bridge is unavailable. Start Keel's bridge to configure providers; skipping is still allowed."
          : `Could not read providers: ${errMessage(err)}`,
      });
    }
  }, []);

  useEffect(() => {
    if (current === "provider") void loadProviders();
  }, [current, loadProviders]);

  useEffect(() => {
    if (current !== "provider" || !providerName) {
      setCatalog({ loading: false, count: null, version: "", error: "" });
      return;
    }
    let alive = true;
    setCatalog({ loading: true, count: null, version: "", error: "" });
    bridge.catalog({ name: providerName, source: "offline" })
      .then((data) => {
        if (!alive) return;
        const res = (data ?? {}) as { ok?: boolean; model_count?: number; models?: unknown[]; catalog_version?: string; detail?: string; error?: string };
        if (res.ok) {
          setCatalog({
            loading: false,
            count: res.model_count ?? (Array.isArray(res.models) ? res.models.length : null),
            version: str(res.catalog_version),
            error: "",
          });
        } else {
          setCatalog({ loading: false, count: null, version: "", error: str(res.detail) || str(res.error) || "Offline catalogue unavailable" });
        }
      })
      .catch((err) => {
        if (alive) setCatalog({ loading: false, count: null, version: "", error: errMessage(err) });
      });
    return () => { alive = false; };
  }, [current, providerName]);

  const loadProjects = useCallback(async () => {
    setProjectsStatus({ kind: "loading", message: "Reading local projects from the bridge…" });
    try {
      const data = await bridge.projects();
      setProjects(rows<ProjectRow>(data, "projects"));
      setProjectsStatus(IDLE);
    } catch (err) {
      setProjectsStatus({
        kind: "error",
        message: isBridgeUnavailable(err)
          ? "The local bridge is unavailable. You can add a workspace later in Code."
          : `Could not read projects: ${errMessage(err)}`,
      });
    }
  }, []);

  useEffect(() => {
    if (current === "workspace") void loadProjects();
  }, [current, loadProjects]);

  useEffect(() => {
    if (current !== "capabilities") return;
    let alive = true;
    setCapsStatus({ kind: "loading", message: "Reading installed skills and MCP servers…" });
    Promise.allSettled([bridge.skills(), bridge.mcpServers()]).then(([skillRes, serverRes]) => {
      if (!alive) return;
      const sErr = skillRes.status === "rejected" ? errMessage(skillRes.reason)
        : str((skillRes.value as { error?: string } | null)?.error);
      const mErr = serverRes.status === "rejected" ? errMessage(serverRes.reason)
        : str((serverRes.value as { error?: string } | null)?.error);
      setSkills(skillRes.status === "fulfilled" ? rows<SkillRow>(skillRes.value, "skills") : []);
      setServers(serverRes.status === "fulfilled" ? rows<ServerRow>(serverRes.value, "servers") : []);
      setCapsStatus(sErr || mErr
        ? { kind: "error", message: `Some capability lists could not be read: ${[sErr, mErr].filter(Boolean).join("; ")}` }
        : IDLE);
    });
    return () => { alive = false; };
  }, [current]);

  /* ---------------------------- real actions ------------------------------- */

  const chooseSurface = (surface: Surface) => {
    setSurface(surface);
    updateChecklist({ surface: "done" });
    notify(`Started in ${surface[0].toUpperCase()}${surface.slice(1)}. You can switch surfaces any time.`);
    goto("local");
  };

  const verifyCredential = async () => {
    const name = providerName.trim();
    const key = secret.trim();
    if (!name || !key) {
      setCredentialStatus({ kind: "info", message: "Choose a provider and enter its key first." });
      return;
    }
    setCredentialStatus({ kind: "loading", message: "Asking the bridge to fetch this provider's live model list…" });
    setSaveStatus(IDLE);
    setSessionVerified(false);
    try {
      const data = (await bridge.setCredential({ name, key })) as CredentialResult | null;
      if (!data || data.ok !== true) {
        setCredentialStatus({
          kind: "error",
          message: data?.detail || data?.error
            ? `Key rejected by ${name}: ${str(data.detail) || str(data.error)}`
            : `Key was not accepted for ${name}; the bridge did not confirm success.`,
        });
        return;
      }
      const count = typeof data.model_count === "number" ? `${data.model_count} models available` : "live model list returned";
      setCredentialStatus({
        kind: "success",
        message: `Verified with the live provider — ${count}. The key is held in bridge process memory only and is forgotten when the bridge restarts.`,
      });
      setSessionVerified(true);
      updateChecklist({ provider: "done" });
    } catch (err) {
      setCredentialStatus({
        kind: "error",
        message: isBridgeUnavailable(err)
          ? "The local bridge is unavailable, so no verification happened. Add the key later in Settings → Providers."
          : `Verification failed: ${errMessage(err)}`,
      });
    }
  };

  const saveCredential = async () => {
    const name = providerName.trim();
    const key = secret.trim();
    if (!sessionVerified || !name || !key) {
      setSaveStatus({ kind: "info", message: "Verify the key for this session before saving it on this device." });
      return;
    }
    setSaveStatus({ kind: "loading", message: "Saving locally…" });
    try {
      const data = (await bridge.saveProvider({ name, key })) as CredentialResult | null;
      if (!data || data.ok !== true) {
        setSaveStatus({ kind: "error", message: data?.detail || data?.error || "The bridge did not confirm a local save." });
        return;
      }
      const hint = str(data.hint);
      setSaveStatus({
        kind: "success",
        message: `Saved on this device only${hint ? ` (hint: …${hint})` : ""}. Settings → Providers can replace or remove it; shell environment variables still take precedence.`,
      });
      setSecret("");
      updateChecklist({ provider: "done" });
    } catch (err) {
      setSaveStatus({ kind: "error", message: `Local save failed: ${errMessage(err)}` });
    }
  };

  const addProject = async () => {
    const path = pathInput.trim().replace(/^"|"$/g, "");
    if (!isAbsolutePath(path)) {
      setAddStatus({ kind: "info", message: "Enter an absolute path (for example C:\\Work\\app or /home/me/app)." });
      return;
    }
    setAddStatus({ kind: "loading", message: "Adding the folder to Keel's project registry…" });
    try {
      const data = (await bridge.addProject({ path })) as { project?: ProjectRow; error?: string } | null;
      const project = data?.project;
      if (!project?.id) {
        setAddStatus({ kind: "error", message: data?.error || "The bridge did not return a project. Nothing was trusted." });
        return;
      }
      setProjects((prev: ProjectRow[]) => [project, ...prev.filter((p: ProjectRow) => p.id !== project.id)]);
      setPathInput("");
      setPendingTrustId(project.id);
      setAddStatus({ kind: "info", message: `Folder added: ${project.path ?? path}. It is NOT trusted yet — make an explicit decision below.` });
      setTrustStatus(IDLE);
    } catch (err) {
      setAddStatus({
        kind: "error",
        message: isBridgeUnavailable(err) ? "The local bridge is unavailable; no folder was added." : `Could not add folder: ${errMessage(err)}`,
      });
    }
  };

  const trustProject = async (trusted: boolean) => {
    if (!pendingTrustId) return;
    setTrustStatus({ kind: "loading", message: "Recording your trust decision in the bridge…" });
    try {
      const data = (await bridge.trustProject(pendingTrustId, trusted)) as { project?: ProjectRow; error?: string } | null;
      if (!data?.project) {
        setTrustStatus({ kind: "error", message: data?.error || "The bridge did not confirm the trust decision." });
        return;
      }
      setProjects((prev: ProjectRow[]) => prev.map((p: ProjectRow) => (p.id === pendingTrustId ? data.project! : p)));
      setSelectedProjectId(pendingTrustId);
      setPendingTrustId("");
      updateChecklist({ workspace: trusted ? "done" : "deferred" });
      setTrustStatus({
        kind: trusted ? "success" : "info",
        message: trusted
          ? "Trusted. Keel can now work in this folder; trust is per-project and can be revoked in Code."
          : "Kept untrusted. The folder stays registered but you can decide later in Code.",
      });
    } catch (err) {
      setTrustStatus({ kind: "error", message: `Trust decision failed: ${errMessage(err)}` });
    }
  };

  const chooseMode = (next: Mode) => {
    setMode(next);
    writeMode(next);
    updateChecklist({ permission: "done" });
    const label = MODE_OPTIONS.find((m) => m.value === next)?.label ?? next;
    notify(`Permission mode saved: ${label}. The composer reads this preference at startup; reload if a session was already open.`, "info");
  };

  const tourActions: Array<{ icon: IconName; title: string; copy: string; surface?: Surface; guidance: string }> = [
    {
      icon: "plus", title: "Create your first task", surface: "cowork",
      copy: "Use New task in the sidebar, then send a prompt in Cowork.",
      guidance: "New task in the sidebar creates a real task through the bridge. Open it in Cowork and send a prompt to work on it. This tour does not create one for you.",
    },
    {
      icon: "send", title: "Send a first prompt", surface: "cowork",
      copy: "Type a real request in the Cowork composer and press Enter.",
      guidance: "Cowork is open. Send a prompt from the composer — Keel streams the response and saves the conversation.",
    },
    {
      icon: "terminal", title: "Inspect tool activity", surface: "cowork",
      copy: "Open a completed task and expand its tool steps.",
      guidance: "In a conversation, expand the work-log steps to see the tools Keel actually called and their targets.",
    },
    {
      icon: "shield", title: "Approve a safe action", surface: "cowork",
      copy: "Read the operation and scope before deciding.",
      guidance: "An approval card appears only when the agent requests a real action. Read the operation and scope, then choose Allow once, Always allow or Don't allow. This tour cannot create one.",
    },
    {
      icon: "file", title: "View a changed file", surface: "code",
      copy: "Open Code, then use the file tree or Review tab.",
      guidance: "Code shows real files from a trusted project. If you skipped the workspace step, add and trust a folder first.",
    },
    {
      icon: "pause", title: "Stop and resume", surface: "cowork",
      copy: "Use Stop while a run is active, then send a follow-up.",
      guidance: "Stop is available in the composer while a run is active. After it stops you can send another prompt to continue.",
    },
  ];

  /* --------------------------------- render -------------------------------- */

  const pendingProject = projects.find((p: ProjectRow) => p.id === pendingTrustId) ?? null;
  const selectedProvider = providers.find((p: ProviderRow) => (str(p.id) || str(p.name)) === providerName) ?? null;
  const footHint = stepIndex < STEP_IDS.length - 1 ? "Skip for now" : "Close";

  const renderStep = () => {
    switch (current) {
      case "welcome":
        return (
          <>
            <p className={s.lead}>One local work environment. Pick one of three places to begin below — you can switch surfaces at any time, including to Duet&apos;s split view.</p>
            <div className={s.choiceGrid}>
              {SURFACE_CHOICES.map((c) => (
                <button key={c.surface} type="button" className={s.choiceCard} onClick={() => chooseSurface(c.surface)}>
                  <span className={s.choiceIcon}><Icon name={c.icon} size={20} /></span>
                  <span className={s.choiceText}>
                    <b>{c.title}</b>
                    <small>{c.description}</small>
                  </span>
                  <Icon name="chevron" size={16} className={s.choiceArrow} />
                </button>
              ))}
            </div>
            <p className={s.fine}>No account or cloud service is required. Choose one of the three options to continue.</p>
          </>
        );

      case "local":
        return (
          <>
            <p className={s.lead}>Keel runs on this machine. Your folders, transcripts and agent data stay under Keel's local trust model.</p>
            <div className={s.factList}>
              <div className={s.fact}><Icon name="folder" size={18} /><div><b>Local-first</b><span>Agent work happens in local folders you choose, through the Python bridge running here.</span></div></div>
              <div className={s.fact}><Icon name="shield" size={18} /><div><b>Your provider, your key</b><span>Keel uses a provider you configure. There is no mandatory cloud account or paid Keel service.</span></div></div>
              <div className={s.fact}><Icon name="spark" size={18} /><div><b>Optional extras</b><span>Provider keys, workspace trust, capabilities and messaging are opt-in. Local use works without them.</span></div></div>
            </div>
            <div className={s.subhead}>Four work surfaces</div>
            <p className={s.fine}>Pick a tile to open that surface now; these are shortcuts, not gates. You can switch surfaces at any time from the top bar.</p>
            <div className={s.surfaceGrid}>
              {SURFACE_TILES.map((tile) => (
                <button key={tile.surface} type="button" className={s.surfaceTile} onClick={() => chooseSurface(tile.surface)}>
                  <Icon name={tile.icon} size={16} />
                  <span><b>{tile.title}</b><small>{tile.description}</small></span>
                </button>
              ))}
            </div>
          </>
        );

      case "provider":
        return (
          <>
            <p className={s.lead}>Connect a provider so Keel can answer. Verification is real: <b>Verify &amp; use for this session</b> asks the bridge to fetch the provider&apos;s live model list. Saving is a separate, optional step that stores the key on this device.</p>
            <StatusLine status={providersStatus} />
            {providers.length > 0 && (
              <div className={s.providerList} role="radiogroup" aria-label="Provider">
                {providers.map((p: ProviderRow) => {
                  const key = str(p.id) || str(p.name);
                  const active = key === providerName;
                  return (
                    <button
                      key={key} type="button" role="radio" aria-checked={active}
                      className={`${s.providerCard} ${active ? s.selected : ""}`}
                      onClick={() => { setProviderName(key); setCredentialStatus(IDLE); setSaveStatus(IDLE); setSessionVerified(false); }}
                    >
                      <span className={s.radioDot} aria-hidden="true" />
                      <span className={s.providerName}>{str(p.name) || key}</span>
                      {trusted(p.configured) || trusted(p.connected)
                        ? <Badge tone="info">configured</Badge>
                        : <Badge tone="neutral">not configured</Badge>}
                    </button>
                  );
                })}
              </div>
            )}
            {selectedProvider && (
              <div className={s.catalogLine} aria-live="polite">
                {catalog.loading ? "Reading offline model catalogue…"
                  : catalog.error ? `Offline catalogue unavailable: ${catalog.error}`
                    : catalog.count !== null
                      ? `Offline catalogue: ${catalog.count} model${catalog.count === 1 ? "" : "s"}${catalog.version ? ` (v${catalog.version})` : ""} — browsing only, not a connection test.`
                      : "No offline catalogue entry returned for this provider."}
              </div>
            )}
            <div className={s.fieldStack}>
              <TextField
                label="Provider API key"
                type="password"
                value={secret}
                autoComplete="off"
                spellCheck={false}
                placeholder="Paste your key — never shown again after this step"
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => { setSecret(e.target.value); setSessionVerified(false); setCredentialStatus(IDLE); setSaveStatus(IDLE); }}
                hint="The bridge never returns a full key to the UI."
              />
              <div className={s.buttonRow}>
                <Button variant="primary" onClick={() => void verifyCredential()} disabled={!providerName || !secret.trim() || credentialStatus.kind === "loading"}>
                  Verify &amp; use for this session
                </Button>
                {sessionVerified && (
                  <Button onClick={() => void saveCredential()} disabled={!secret.trim() || saveStatus.kind === "loading"}>
                    Save on this device
                  </Button>
                )}
              </div>
            </div>
            <StatusLine status={credentialStatus} />
            <StatusLine status={saveStatus} />
            <p className={s.fine}>Session keys live in bridge process memory only and die on restart. Saving writes an encrypted key to ~/.keel/settings.json on this machine; Settings → Providers can remove it. Verification is not a separate endpoint — it is performed by the credential call itself.</p>
          </>
        );

      case "workspace":
        return (
          <>
            <p className={s.lead}>Add a local folder to work in. Keel does not trust anything automatically — you decide, per project, and can revoke it in Code.</p>
            <StatusLine status={projectsStatus} />
            <TextField
              label="Absolute folder path"
              value={pathInput}
              placeholder="C:\\Users\\me\\Projects\\app  or  /home/me/app"
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => { setPathInput(e.target.value); setAddStatus(IDLE); }}
              hint="This bridge has no native folder-picker endpoint in the UI contract; paste an absolute path."
            />
            <div className={s.buttonRow}>
              <Button onClick={() => void addProject()} disabled={!pathInput.trim() || addStatus.kind === "loading"}>Add folder</Button>
            </div>
            <StatusLine status={addStatus} />
            {projects.length > 0 && (
              <div className={s.subhead}>Known local projects</div>
            )}
            <div className={s.projectList}>
              {projects.map((p: ProjectRow) => {
                const id = str(p.id);
                const active = id === selectedProjectId;
                return (
                  <button
                    key={id} type="button"
                    className={`${s.projectCard} ${active ? s.selected : ""}`}
                    onClick={() => {
                      setSelectedProjectId(id);
                      if (trusted(p.trusted)) {
                        updateChecklist({ workspace: "done" });
                        setTrustStatus({ kind: "success", message: `Using already-trusted project ${str(p.path)}.` });
                      } else {
                        setPendingTrustId(id);
                        setTrustStatus(IDLE);
                      }
                    }}
                  >
                    <Icon name="folder" size={16} />
                    <span className={s.projectPath}>{str(p.path) || str(p.name) || id}</span>
                    <Badge tone={trusted(p.trusted) ? "success" : "warning"}>{trusted(p.trusted) ? "trusted" : "untrusted"}</Badge>
                  </button>
                );
              })}
            </div>
            {projects.length === 0 && projectsStatus.kind === "idle" && (
              <p className={s.muted}>No local projects are registered yet. Paste an absolute path above to add one.</p>
            )}
            {pendingProject && (
              <Card className={s.trustCard}>
                <div className={s.subhead}>Explicit trust decision</div>
                <p className={s.trustPath}>{str(pendingProject.path) || str(pendingProject.name)}</p>
                <ul className={s.scopeList}>
                  <li><b>Read</b> — list and read files inside this folder (path containment is enforced by the bridge).</li>
                  <li><b>Write</b> — create and modify files inside this folder through guarded bridge operations.</li>
                  <li><b>Execute</b> — terminal commands start in this folder and still pass Keel's permission rules. A command itself can reach other paths, so trust is not a sandbox.</li>
                </ul>
                <p className={s.fine}>Trust is recorded per project, can be revoked in Code, and never grants access to other folders by itself.</p>
                <div className={s.buttonRow}>
                  <Button variant="primary" onClick={() => void trustProject(true)} disabled={trustStatus.kind === "loading"}>Trust this folder</Button>
                  <Button onClick={() => void trustProject(false)} disabled={trustStatus.kind === "loading"}>Keep it untrusted</Button>
                </div>
              </Card>
            )}
            {/* The decision card disappears once the choice is recorded; keep the
                result outside it so the user actually sees what the bridge did. */}
            <StatusLine status={trustStatus} />
          </>
        );

      case "permission":
        return (
          <>
            <p className={s.lead}>Permission modes control how much Keel may do without asking. They are sent to the bridge on every message; the four below are the modes this build accepts.</p>
            <div className={s.modeList} role="radiogroup" aria-label="Permission mode">
              {MODE_OPTIONS.map((o) => (
                <button
                  key={o.value} type="button" role="radio" aria-checked={mode === o.value}
                  className={`${s.modeCard} ${mode === o.value ? s.selected : ""}`}
                  onClick={() => chooseMode(o.value)}
                >
                  <span className={s.radioDot} aria-hidden="true" />
                  <span><b>{o.label}</b><small>{o.description}</small></span>
                </button>
              ))}
            </div>
            <p className={s.fine}>Plan is the safe default: read-only until you switch. Your choice is saved to the same preference the composer uses at startup.</p>
          </>
        );

      case "capabilities":
        return (
          <>
            <p className={s.lead}>Optional. Keel can use skills and MCP servers, but nothing here is installed or enabled by this setup step.</p>
            <StatusLine status={capsStatus} />
            <div className={s.subhead}>Built-in skills (bundled with Keel)</div>
            {skills.filter((sk: SkillRow) => str(sk.scope).toLowerCase() === "bundled").length === 0
              ? <p className={s.muted}>No bundled skills reported by the bridge.</p>
              : skills.filter((sk: SkillRow) => str(sk.scope).toLowerCase() === "bundled").map((sk: SkillRow) => (
                <div key={str(sk.id) || str(sk.name)} className={s.capRow}>
                  <Icon name="spark" size={15} />
                  <span><b>{str(sk.name) || str(sk.id)}</b><small>{str(sk.description)}</small></span>
                  <Badge tone="info">bundled</Badge>
                </div>
              ))}
            <div className={s.subhead}>Your skills (from this machine)</div>
            {skills.filter((sk: SkillRow) => str(sk.scope).toLowerCase() !== "bundled").length === 0
              ? <p className={s.muted}>No user or project skills found.</p>
              : skills.filter((sk: SkillRow) => str(sk.scope).toLowerCase() !== "bundled").map((sk: SkillRow) => (
                <div key={str(sk.id) || str(sk.name)} className={s.capRow}>
                  <Icon name="file" size={15} />
                  <span>
                    <b>{str(sk.name) || str(sk.id)}</b>
                    <small>{str(sk.description) || `Scope: ${str(sk.scope, "unknown")}`}{trusted(sk.trusted) ? " · trusted" : ""}{typeof sk.injection_suspects === "number" ? ` · ${sk.injection_suspects} injection suspects` : ""}</small>
                  </span>
                  <Badge tone="neutral">{str(sk.scope, "user")}</Badge>
                </div>
              ))}
            <div className={s.subhead}>Third-party MCP servers</div>
            {servers.length === 0
              ? <p className={s.muted}>No MCP servers configured.</p>
              : servers.map((srv: ServerRow) => (
                <div key={str(srv.id) || str(srv.name)} className={s.capRow}>
                  <Icon name="link" size={15} />
                  <span>
                    <b>{str(srv.name) || str(srv.id)}</b>
                    <small>{str(srv.transport, "transport unknown")}{str(srv.command) ? ` · ${str(srv.command)}` : ""}{str(srv.url) ? ` · ${str(srv.url)}` : ""}</small>
                  </span>
                  <Badge tone="warning">third-party</Badge>
                </div>
              ))}
            <p className={s.fine}>Skills add instructions to the agent's context; MCP servers expose tools that may call external services. Review their source and permissions before using them. Manage them in Settings → Capabilities.</p>
          </>
        );

      case "channels":
        return (
          <>
            <p className={s.lead}>Optional. Keel works fully without external messaging or voice services.</p>
            <div className={s.factList}>
              <div className={s.fact}><Icon name="info" size={18} /><div><b>External channels are not configured</b><span>No Linq, Telegram, phone or public webhook integration is available or required in this build.</span></div></div>
              <div className={s.fact}><Icon name="info" size={18} /><div><b>Dictation is not wired in this frontend</b><span>Type or paste prompts in the composer. No microphone permission is requested here.</span></div></div>
              <div className={s.fact}><Icon name="shield" size={18} /><div><b>Local by default</b><span>Nothing in this step sends messages, contacts or files off this machine.</span></div></div>
            </div>
          </>
        );

      case "tour":
        return (
          <>
            <p className={s.lead}>A short walkthrough of real controls. These buttons open the right surface and explain what to do — they do not run an agent or create approvals for you.</p>
            <div className={s.tourList}>
              {tourActions.map((a) => (
                <button key={a.title} type="button" className={s.tourRow} onClick={() => {
                  if (a.surface) setSurface(a.surface);
                  notify(a.guidance, "info");
                }}>
                  <span className={s.tourIcon}><Icon name={a.icon} size={17} /></span>
                  <span><b>{a.title}</b><small>{a.copy}</small></span>
                  <Icon name="chevron" size={15} />
                </button>
              ))}
            </div>
            <p className={s.fine}>Tool activity, approvals and file changes appear only when a real agent run produces them.</p>
          </>
        );
    }
  };

  const title = current === "welcome" ? "Welcome to Keel"
    : current === "local" ? "How Keel works"
      : current === "provider" ? "Connect a provider"
        : current === "workspace" ? "Choose a workspace"
          : current === "permission" ? "Permission mode"
            : current === "capabilities" ? "Capabilities (optional)"
              : current === "channels" ? "Voice & channels (optional)" : "Take the tour";

  return (
    <div className={`${s.overlay} ${reduceMotion ? s.reduceMotion : ""}`}>
      <div ref={rootRef} className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
        <header className={s.header}>
          <div className={s.brand}><KeelMark size={26} /><span>Keel setup</span></div>
          <div className={s.headerRight}>
            <span className={s.stepCount}>Step {stepIndex + 1} of {STEP_IDS.length}</span>
            <IconButton
              label="Help & troubleshooting"
              title="Help & troubleshooting"
              onClick={() => window.dispatchEvent(new Event(OPEN_HELP_EVENT))}
            ><Icon name="info" size={16} /></IconButton>
            <IconButton label="Close setup" onClick={close}><Icon name="close" size={16} /></IconButton>
          </div>
        </header>
        <div className={s.progressWrap}>
          <Progress value={Math.round((requiredDoneCount / 4) * 100)} label="Required setup progress" />
          <span>{requiredDoneCount}/4 required</span>
        </div>
        <div className={s.body}>
          <h1 id="onboarding-title" ref={headingRef} tabIndex={-1} className={s.title}>{title}</h1>
          {renderStep()}
        </div>
        <footer className={s.footer}>
          <div className={s.footerLeft}>
            {stepIndex > 0 && (
              <Button size="sm" variant="ghost" onClick={() => goto(STEP_IDS[stepIndex - 1])}>Back</Button>
            )}
            {current === "tour" && (
              <Button size="sm" variant="ghost" onClick={() => goto("tour")}>Restart tour</Button>
            )}
          </div>
          <div className={s.footerRight}>
            {current !== "welcome" && (
              <Button size="sm" variant="ghost" onClick={skipCurrent}>
                {footHint === "Close" ? "Finish later" : "Skip for now"}
              </Button>
            )}
            <Button size="sm" variant="primary" onClick={current === "tour" ? finish : () => advance()}>
              {current === "tour" ? "Finish setup" : current === "local" ? "Continue" : "Continue"}
            </Button>
          </div>
        </footer>
      </div>
    </div>
  );
}

"use client";

// Phase 5 — Duet: a keyboard-friendly, multi-pane developer workbench.
// Tabs and layout persist locally and are always scoped to one bridge project.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Project } from "@/lib/types";
import { Badge, Button, Dialog, EmptyState, IconButton, ResizeHandle, Spinner, Tabs, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import {
  BridgeError, ContextView, EmptyProject, EnvironmentView, FileView, ReviewView,
  TerminalView, TreeView, useNarrow, useProjects, useTree,
  type TerminalState,
} from "@/features/code/workspace";
import ReviewPairView from "./reviewPair";
import s from "./duet.module.css";

// `pair` is opened on demand (button / command), never added to DEFAULT_TABS:
// the default four tabs and their persisted layout stay exactly as before.
type TabKind = "review" | "terminal" | "openfile" | "browser" | "file" | "pair";
interface WorkspaceTab { id: string; kind: TabKind; path?: string }
type ContextTab = "context" | "environment";

const DEFAULT_TABS: WorkspaceTab[] = [
  { id: "review", kind: "review" },
  { id: "terminal", kind: "terminal" },
  { id: "openfile", kind: "openfile" },
  { id: "browser", kind: "browser" },
];

const CONTEXT_TABS: Array<{ value: ContextTab; label: string; icon: React.ReactNode }> = [
  { value: "context", label: "Context", icon: <Icon name="info" size={14} /> },
  { value: "environment", label: "Environment", icon: <Icon name="settings" size={14} /> },
];

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));

function loadJson<T>(key: string, fallback: T, validate?: (v: unknown) => boolean): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as T;
    if (validate && !validate(parsed)) return fallback;
    return parsed;
  } catch { return fallback; }
}

function store(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

interface SavedLayout {
  tabs: WorkspaceTab[];
  activeId: string;
  recent: WorkspaceTab[];
  explorerWidth?: number;
  contextWidth?: number;
  explorerOpen?: boolean;
  contextOpen?: boolean;
  contextTab?: ContextTab;
}

/** Layouts are stored as a map keyed by project id. A single-record shape
 *  could be overwritten while switching projects, leaking one project's tabs
 *  into another's (or clearing the previous project's saved layout). */
function readLayouts(): Record<string, SavedLayout> {
  try {
    const raw = localStorage.getItem("keel-duet:tabs:v1");
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    // Migrate the older single-project record if one is present.
    if (Array.isArray(parsed.tabs) && typeof parsed.projectId === "string") {
      return { [parsed.projectId]: { tabs: parsed.tabs as WorkspaceTab[], activeId: String(parsed.activeId ?? ""), recent: Array.isArray(parsed.recent) ? parsed.recent as WorkspaceTab[] : [] } };
    }
    return parsed as Record<string, SavedLayout>;
  } catch { return {}; }
}

function tabIcon(kind: TabKind): React.ReactNode {
  switch (kind) {
    case "review": return <Icon name="tasks" size={14} />;
    case "terminal": return <Icon name="terminal" size={14} />;
    case "openfile": return <Icon name="search" size={14} />;
    case "browser": return <Icon name="browser" size={14} />;
    case "file": return <Icon name="file" size={14} />;
    case "pair": return <Icon name="duet" size={14} />;
  }
}

function tabLabel(tab: WorkspaceTab): string {
  if (tab.kind === "file" && tab.path) return tab.path.split("/").pop() ?? tab.path;
  if (tab.kind === "browser") return "Browser";
  if (tab.kind === "openfile") return "Open file";
  if (tab.kind === "terminal") return "Terminal";
  if (tab.kind === "pair") return "Review pair";
  return "Review";
}

/** Only a loopback URL actually supplied by the bridge may be previewed. */
function localPreviewUrl(project: Project | null): string | null {
  if (!project) return null;
  const raw = project as unknown as Record<string, unknown>;
  const candidate = raw.preview_url ?? raw.previewUrl ?? raw.dev_server_url ?? raw.preview;
  let value = typeof candidate === "string" ? candidate : null;
  if (!value && candidate && typeof candidate === "object") {
    value = String((candidate as Record<string, unknown>).url ?? "");
  }
  if (!value) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (host !== "localhost" && host !== "127.0.0.1" && host !== "[::1]" && host !== "::1") return null;
    return url.toString();
  } catch { return null; }
}

function LocalPreview({ project, onClose }: { project: Project | null; onClose: () => void }) {
  const previewUrl = localPreviewUrl(project);
  const [reload, setReload] = useState(0);
  const parsed = useMemo(() => { try { return previewUrl ? new URL(previewUrl) : null; } catch { return null; } }, [previewUrl]);
  return (
    <section className={s.preview} aria-label="Local preview">
      <header className={s.panelHead}>
        <div>
          <h3>Local preview</h3>
          <p className={s.muted}>{parsed ? <>Origin: <code className={s.mono}>{parsed.origin}</code> · port {parsed.port || (parsed.protocol === "https:" ? "443" : "80")}</> : "Sandboxed local origin only"}</p>
        </div>
        <div className={s.rowGap}>
          {parsed && (
            <>
              <IconButton label="Reload local preview" onClick={() => setReload((n) => n + 1)}><Icon name="refresh" size={15} /></IconButton>
            </>
          )}
          <IconButton label="Close local preview" onClick={onClose}><Icon name="close" size={15} /></IconButton>
        </div>
      </header>
      {parsed ? (
        <>
          <p className={s.note}>This is a sandboxed iframe for a loopback URL reported by the bridge. It is not a general internet browser.</p>
          <iframe
            key={`${parsed.href}:${reload}`}
            className={s.iframe}
            src={parsed.href}
            title="Local preview of the selected project"
            sandbox="allow-scripts allow-forms allow-modals"
            referrerPolicy="no-referrer"
          />
        </>
      ) : (
        <EmptyState
          icon={<Icon name="browser" size={28} />}
          title="Local preview is not exposed by this bridge"
          description="The bridge does not report a project preview URL, so Keel will not guess a port or open a general browser here. A sandboxed iframe is shown only when the bridge supplies a loopback URL."
        />
      )}
    </section>
  );
}

export default function Duet() {
  const { notify, registerCommands } = useApp();
  const projects = useProjects("keel-duet:project");
  const selectedId = projects.selectedId;
  const project = projects.selected;
  const trusted = Boolean(project?.trusted);
  const narrow = useNarrow(900);

  const [explorerWidth, setExplorerWidth] = useState(() => clamp(loadJson<number>("keel-duet:explorer-width", 264), 220, 440));
  const [contextWidth, setContextWidth] = useState(() => clamp(loadJson<number>("keel-duet:context-width", 300), 240, 480));
  const [explorerOpen, setExplorerOpen] = useState(() => loadJson<boolean>("keel-duet:explorer-open", true));
  const [contextOpen, setContextOpen] = useState(() => loadJson<boolean>("keel-duet:context-open", true));
  const [contextTab, setContextTab] = useState<ContextTab>(() => loadJson<ContextTab>("keel-duet:context-tab", "context"));

  const [tabs, setTabs] = useState<WorkspaceTab[]>(DEFAULT_TABS);
  const [activeId, setActiveId] = useState<string>("review");
  const [recent, setRecent] = useState<WorkspaceTab[]>([]);
  const [hydratedFor, setHydratedFor] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [dragId, setDragId] = useState<string | null>(null);
  const [terminalStates, setTerminalStates] = useState<Record<string, TerminalState>>({});
  const [dirtyTabs, setDirtyTabs] = useState<Record<string, boolean>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [addPath, setAddPath] = useState("");
  const [addName, setAddName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [trustBusy, setTrustBusy] = useState(false);
  const [trustError, setTrustError] = useState<string | null>(null);
  const [reopenMenu, setReopenMenu] = useState(false);
  const fileFilterRef = useRef<HTMLInputElement>(null);

  const tree = useTree(selectedId, trusted && explorerOpen);

  // Narrow windows show one drawer at a time so panes never overlap.
  useEffect(() => {
    if (narrow && explorerOpen && contextOpen) setContextOpen(false);
  }, [narrow, explorerOpen, contextOpen]);

  // Only the mounted (active) terminal is polled. Drop other tabs' status so
  // a stale "running" dot is never shown for a process we cannot observe.
  useEffect(() => {
    setTerminalStates((prev) => {
      if (!Object.keys(prev).length) return prev;
      const next: typeof prev = {};
      if (activeId && prev[activeId]) next[activeId] = prev[activeId];
      return next;
    });
  }, [activeId]);

  /* ---- persistence ------------------------------------------------ */
  useEffect(() => { store("keel-duet:explorer-width", explorerWidth); }, [explorerWidth]);
  useEffect(() => { store("keel-duet:context-width", contextWidth); }, [contextWidth]);
  useEffect(() => { store("keel-duet:explorer-open", explorerOpen); }, [explorerOpen]);
  useEffect(() => { store("keel-duet:context-open", contextOpen); }, [contextOpen]);
  useEffect(() => { store("keel-duet:context-tab", contextTab); }, [contextTab]);

  useEffect(() => {
    let nextTabs = DEFAULT_TABS;
    let nextActive = "review";
    let nextRecent: WorkspaceTab[] = [];
    try {
      const saved = selectedId ? readLayouts()[selectedId] : undefined;
      if (saved && Array.isArray(saved.tabs)) {
        nextTabs = saved.tabs.filter((t) => t && typeof t.id === "string" && typeof t.kind === "string");
        nextActive = typeof saved.activeId === "string" ? saved.activeId : (nextTabs[0]?.id ?? "");
        nextRecent = Array.isArray(saved.recent) ? saved.recent : [];
        if (typeof saved.explorerWidth === "number") setExplorerWidth(clamp(saved.explorerWidth, 220, 440));
        if (typeof saved.contextWidth === "number") setContextWidth(clamp(saved.contextWidth, 240, 480));
        if (typeof saved.explorerOpen === "boolean") setExplorerOpen(saved.explorerOpen);
        if (typeof saved.contextOpen === "boolean") setContextOpen(saved.contextOpen);
        if (saved.contextTab === "context" || saved.contextTab === "environment") setContextTab(saved.contextTab);
      }
    } catch { /* ignore malformed state */ }
    setTabs(nextTabs);
    setActiveId(nextActive);
    setRecent(nextRecent);
    setTerminalStates({});
    setDirtyTabs({});
    setTreeQuery("");
    setHydratedFor(selectedId);
  }, [selectedId]);

  useEffect(() => {
    if (hydratedFor !== selectedId || !selectedId) return;
    try {
      const layouts = readLayouts();
      layouts[selectedId] = {
        tabs, activeId, recent,
        explorerWidth, contextWidth, explorerOpen, contextOpen, contextTab,
      };
      store("keel-duet:tabs:v1", layouts);
    } catch { /* ignore */ }
  }, [hydratedFor, selectedId, tabs, activeId, recent,
    explorerWidth, contextWidth, explorerOpen, contextOpen, contextTab]);

  /* ---- tab actions ------------------------------------------------ */
  const openFile = useCallback((path: string) => {
    const id = `file:${path}`;
    setTabs((prev) => prev.some((t) => t.id === id) ? prev : [...prev, { id, kind: "file", path }]);
    setActiveId(id);
  }, []);

  const openKind = useCallback((kind: TabKind) => {
    const id = kind;
    setTabs((prev) => prev.some((t) => t.id === id) ? prev : [...prev, { id, kind }]);
    setActiveId(id);
  }, []);

  const closeTab = useCallback((id: string) => {
    if (dirtyTabs[id] && !window.confirm("This file has unsaved edits. Close it and discard them?")) return;
    const idx = tabs.findIndex((t) => t.id === id);
    if (idx < 0) return;
    const target = tabs[idx];
    const next = tabs.filter((t) => t.id !== id);
    setTabs(next);
    setActiveId((current) => current === id ? (next[Math.min(idx, next.length - 1)]?.id ?? "") : current);
    setRecent((r) => [target, ...r.filter((x) => x.id !== id)].slice(0, 8));
    setDirtyTabs((prev) => { const copy = { ...prev }; delete copy[id]; return copy; });
  }, [tabs, dirtyTabs]);

  const restoreRecent = useCallback(() => {
    if (!recent.length) return;
    const [first, ...remainder] = recent;
    setTabs((prev) => prev.some((t) => t.id === first.id) ? prev : [...prev, first]);
    setRecent(remainder);
    setActiveId(first.id);
    setReopenMenu(false);
  }, [recent]);

  const reorder = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    setTabs((prev) => {
      const next = [...prev];
      const from = next.findIndex((t) => t.id === fromId);
      const to = next.findIndex((t) => t.id === toId);
      if (from < 0 || to < 0) return prev;
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const resetLayout = () => {
    setTabs(DEFAULT_TABS);
    setActiveId("review");
    setRecent([]);
    setTerminalStates({});
    setDirtyTabs({});
    setExplorerWidth(264);
    setContextWidth(300);
    setExplorerOpen(true);
    setContextOpen(true);
    setContextTab("context");
    notify("Duet layout reset to the default tabs and panes.", "info");
  };

  const selectProject = (id: string | null) => {
    // Switching projects clears stale tabs immediately; the hydration effect
    // then reloads only that project's saved tabs, never another project's.
    setTabs(DEFAULT_TABS);
    setActiveId("review");
    setRecent([]);
    setTerminalStates({});
    setDirtyTabs({});
    setTreeQuery("");
    projects.select(id);
  };

  /* ---- project actions -------------------------------------------- */
  const submitAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const path = addPath.trim();
    if (!path) { setAddError("Enter an absolute path to a folder on this machine."); return; }
    setAdding(true); setAddError(null);
    try {
      await projects.add(path, addName.trim() || undefined);
      setAddOpen(false); setAddPath(""); setAddName("");
      notify("Project added. Trust is required before any file is read.", "success");
    } catch (err) {
      setAddError(isBridgeUnavailable(err) ? `Bridge unavailable: ${errMessage(err)}` : errMessage(err));
    } finally { setAdding(false); }
  };

  const decideTrust = async (value: boolean) => {
    if (!selectedId) return;
    setTrustBusy(true); setTrustError(null);
    try {
      await projects.trust(selectedId, value);
      notify(value ? "Folder trusted. File access is now allowed." : "Folder rejected. No files were read.", value ? "success" : "info");
    } catch (err) { setTrustError(errMessage(err)); }
    finally { setTrustBusy(false); }
  };

  /* ---- keyboard ---------------------------------------------------- */
  useEffect(() => {
    registerCommands([
      { id: "duet.quickOpen", label: "Quick open file", group: "Duet", hint: "Ctrl/Cmd+P", run: () => openKind("openfile") },
      { id: "duet.review", label: "Open Review tab", group: "Duet", run: () => openKind("review") },
      { id: "duet.terminal", label: "Open Terminal tab", group: "Duet", run: () => openKind("terminal") },
      { id: "duet.pair", label: "Open review pair (builder and reviewer)", group: "Duet", run: () => openKind("pair") },
      { id: "duet.resetLayout", label: "Reset Duet layout", group: "Duet", run: resetLayout },
    ]);
  }, [registerCommands, openKind]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault(); openKind("openfile");
        window.setTimeout(() => fileFilterRef.current?.focus(), 0); return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w" && tabs.length) {
        e.preventDefault(); if (activeId) closeTab(activeId); return;
      }
      if (e.ctrlKey && (e.key === "Tab" || e.key === "PageDown" || e.key === "PageUp") && tabs.length > 1) {
        e.preventDefault();
        const idx = tabs.findIndex((t) => t.id === activeId);
        const dir = e.key === "PageUp" || e.shiftKey ? -1 : 1;
        setActiveId(tabs[(idx + dir + tabs.length) % tabs.length].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tabs, activeId, closeTab, openKind]);

  const activeTab = tabs.find((t) => t.id === activeId) ?? null;
  const quickFiles = useMemo(() => {
    const q = treeQuery.trim().toLowerCase();
    return (q ? tree.files.filter((f) => f.path.toLowerCase().includes(q)) : tree.files).slice(0, 250);
  }, [tree.files, treeQuery]);

  const gate = project && !trusted ? (
    <section className={s.gate} aria-labelledby="duet-trust-title">
      <div className={s.gateIcon}><Icon name="shield" size={28} /></div>
      <h2 id="duet-trust-title">Trust this folder before using Duet</h2>
      <p className={s.gateLead}>
        <strong>{project.path ?? "(path not available)"}</strong> is not trusted. Keel will not list files, read files or run commands until you decide. There is no automatic trust.
      </p>
      <ul className={s.scopeList}>
        <li><strong>Read</strong> — list and view text files in this folder.</li>
        <li><strong>Write</strong> — save edits only after an explicit confirmed save.</li>
        <li><strong>Execute</strong> — run commands in this folder under the bridge permission policy.</li>
        <li><strong>Limit</strong> — the bridge blocks paths outside this folder. Rejecting changes nothing on disk.</li>
      </ul>
      {trustError && <p className={s.errorBox} role="alert">{trustError}</p>}
      <div className={s.rowGap}>
        <Button variant="primary" loading={trustBusy} onClick={() => void decideTrust(true)}><Icon name="shield" size={15} /> Trust</Button>
        <Button variant="ghost" disabled={trustBusy} onClick={() => void decideTrust(false)}>Reject</Button>
      </div>
    </section>
  ) : null;

  return (
    <div className={s.duet} data-narrow={narrow ? "true" : "false"}>
      <header className={s.tabbar} role="tablist" aria-label="Duet workspace tabs">
        <span className={s.brand}><Icon name="duet" size={16} /> Duet</span>
        <label className={s.srOnly} htmlFor="duet-project">Active project</label>
        <select id="duet-project" className={s.projectSelect} value={selectedId ?? ""}
          disabled={projects.loading || !projects.projects.length}
          onChange={(e) => selectProject(e.target.value || null)} aria-label="Active project">
          {!projects.projects.length && <option value="">{projects.loading ? "Loading…" : "No projects"}</option>}
          {projects.projects.map((p) => <option key={p.id} value={p.id}>{p.name ?? p.path ?? p.id}</option>)}
        </select>
        <span className={s.divider} aria-hidden="true" />

        <div className={s.tabsStrip}>
          {tabs.map((tab) => (
            <div
              key={tab.id}
              role="tab"
              aria-selected={activeId === tab.id}
              tabIndex={activeId === tab.id ? 0 : -1}
              draggable
              className={`${s.tab} ${activeId === tab.id ? s.tabActive : ""} ${dragId === tab.id ? s.tabDragging : ""}`}
              title={tab.kind === "file" ? tab.path : tabLabel(tab)}
              onClick={() => setActiveId(tab.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setActiveId(tab.id); }
              }}
              onDragStart={(e) => { setDragId(tab.id); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", tab.id); }}
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}
              onDrop={(e) => {
                e.preventDefault();
                const from = dragId || e.dataTransfer.getData("text/plain");
                if (from) reorder(from, tab.id);
                setDragId(null);
              }}
              onDragEnd={() => setDragId(null)}
            >
              <span className={s.tabIcon}>{tabIcon(tab.kind)}</span>
              <span className={s.tabText}>{tabLabel(tab)}</span>
              {tab.kind === "terminal" && terminalStates[tab.id]?.running ? (
                <span className={s.processDot} role="img" aria-label="process running" title="Process running" />
              ) : null}
              {tab.kind === "file" && dirtyTabs[tab.id] ? (
                <span className={s.dirtyDot} role="img" aria-label="Unsaved changes" title="Unsaved changes" />
              ) : null}
              <button type="button" className={s.tabClose} aria-label={`Close ${tabLabel(tab)}`}
                onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}>
                <Icon name="close" size={12} />
              </button>
            </div>
          ))}
        </div>

        <div className={s.tabActions}>
          <div className={s.relative}>
            <IconButton label="Restore a recently closed tab" disabled={!recent.length} active={reopenMenu} onClick={() => setReopenMenu((v) => !v)}>
              <Icon name="clock" size={15} />
            </IconButton>
            {reopenMenu && recent.length > 0 && (
              <div className={s.menu} role="menu" aria-label="Recently closed tabs">
                {recent.map((t) => (
                  <button key={t.id} role="menuitem" type="button" onClick={() => {
                    setTabs((prev) => prev.some((x) => x.id === t.id) ? prev : [...prev, t]);
                    setActiveId(t.id);
                    setRecent((r) => r.filter((x) => x.id !== t.id));
                    setReopenMenu(false);
                  }}>
                    <Icon name="clock" size={13} /> {tabLabel(t)}
                    {t.path && <span className={s.muted}>{t.path}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <IconButton label="Open review pair (builder and reviewer)" active={activeTab?.kind === "pair"} onClick={() => openKind("pair")}>
            <Icon name="duet" size={15} />
          </IconButton>
          <IconButton label="Reset Duet layout" onClick={resetLayout}><Icon name="refresh" size={15} /></IconButton>
          <IconButton label="Add a local project" onClick={() => { setAddError(null); setAddOpen(true); }}><Icon name="plus" size={15} /></IconButton>
          {narrow && (
            <>
              <IconButton label="Toggle project explorer" active={explorerOpen} onClick={() => {
                const next = !explorerOpen; setExplorerOpen(next); if (next) setContextOpen(false);
              }}><Icon name="folder" size={15} /></IconButton>
              <IconButton label="Toggle context pane" active={contextOpen} onClick={() => {
                const next = !contextOpen; setContextOpen(next); if (next) setExplorerOpen(false);
              }}><Icon name="panel" size={15} /></IconButton>
            </>
          )}
        </div>
      </header>

      <BridgeError message={projects.error} onRetry={projects.refresh} />

      <div className={s.body}>
        {explorerOpen && (
          <aside className={`${s.explorer} ${narrow ? s.drawer : ""}`} style={narrow ? undefined : { width: explorerWidth }} aria-label="Duet project explorer">
            <div className={s.paneHead}>
              <strong>Files</strong>
              <IconButton label="Refresh file tree" disabled={!trusted} onClick={() => tree.refresh()}><Icon name="refresh" size={14} /></IconButton>
            </div>
            {!trusted ? <p className={s.hint}>Trust the selected folder to list files.</p> : (
              <>
                <div className={s.searchRow}>
                  <Icon name="search" size={14} />
                  <label className={s.srOnly} htmlFor="duet-tree-filter">Filter files</label>
                  <input id="duet-tree-filter" value={treeQuery} onChange={(e) => setTreeQuery(e.target.value)} placeholder="Filter files…" spellCheck={false} />
                </div>
                {tree.loading && <div className={s.inlineLoad}><Spinner label="Loading file tree" /> Reading folder…</div>}
                <BridgeError message={tree.error} onRetry={tree.refresh} />
                <TreeView nodes={tree.nodes} activePath={activeTab?.kind === "file" ? activeTab.path : null} filter={treeQuery} onOpen={openFile} />
                <p className={s.treeFoot}>Hidden and ignored paths are filtered by the bridge.</p>
              </>
            )}
          </aside>
        )}

        {!narrow && explorerOpen && (
          <ResizeHandle orientation="vertical" label="Resize Duet file explorer"
            value={explorerWidth} min={220} max={440}
            onDrag={(delta) => setExplorerWidth((w) => clamp(w + delta, 220, 440))} />
        )}

        <main className={s.main} aria-label="Duet active workspace">
          {/* Review pair reads bots/rows, not project files, so it is available
              without trusting a folder. It never edits or executes anything. */}
          {activeTab?.kind === "pair" ? (
            <section className={s.pane}><ReviewPairView /></section>
          ) : gate ?? (
            !project ? <EmptyProject onAdd={() => setAddOpen(true)} /> :
              !activeTab ? (
                <EmptyState icon={<Icon name="panel" size={28} />} title="No tabs open"
                  description="Restore a recent tab or reset the layout to return to Review, Terminal, Open file and Local preview."
                  action={<Button variant="primary" onClick={resetLayout}>Reset layout</Button>} />
              ) : activeTab.kind === "review" ? (
                <section className={s.pane}><ReviewView projectId={selectedId as string} /></section>
              ) : activeTab.kind === "terminal" ? (
                <section className={s.pane}>
                  <TerminalView
                    key={`${selectedId}:${activeTab.id}`}
                    projectId={selectedId as string}
                    cwd={project.path}
                    onStateChange={(state) => setTerminalStates((prev) => ({ ...prev, [activeTab.id]: state }))}
                  />
                </section>
              ) : activeTab.kind === "openfile" ? (
                <section className={s.pane}>
                  <div className={s.panelHead}>
                    <div><h3>Open file</h3><p className={s.muted}>Search the trusted project tree</p></div>
                    <Button size="sm" variant="ghost" onClick={() => fileFilterRef.current?.focus()}><Icon name="search" size={14} /> Focus search</Button>
                  </div>
                  <div className={s.searchRow}>
                    <Icon name="search" size={14} />
                    <label className={s.srOnly} htmlFor="duet-quick-filter">File path</label>
                    <input id="duet-quick-filter" ref={fileFilterRef} value={treeQuery} onChange={(e) => setTreeQuery(e.target.value)}
                      placeholder="Type a path and press Enter to open…" spellCheck={false}
                      disabled={!trusted}
                      onKeyDown={(e) => { if (e.key === "Enter" && quickFiles[0]) openFile(quickFiles[0].path); }} />
                  </div>
                  {!trusted ? <p className={s.hint}>Trust the folder to search its files.</p> : tree.loading
                    ? <p className={s.hint}>Reading the project tree…</p>
                    : quickFiles.length ? (
                      <ul className={s.fileList}>
                        {quickFiles.map((f) => (
                          <li key={f.path}>
                            <button type="button" className={s.fileItem} onClick={() => openFile(f.path)}>
                              <Icon name="file" size={14} /><span>{f.path}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : <EmptyState icon={<Icon name="file" size={24} />} title="No matching files" description="The bridge returned no files matching this filter." />}
                </section>
              ) : activeTab.kind === "browser" ? (
                <LocalPreview project={project} onClose={() => closeTab(activeTab.id)} />
              ) : activeTab.kind === "file" && activeTab.path ? (
                // Mounted file panes keep their in-memory buffers and change
                // indicators while other tabs are active. Nothing is persisted.
                <section className={s.pane}>
                  <div className={s.fileStack}>
                    {tabs.filter((t) => t.kind === "file" && t.path).map((t) => (
                      <div key={`${selectedId}:${t.id}`} className={s.filePane} hidden={t.id !== activeTab.id}>
                        <FileView
                          projectId={selectedId as string}
                          path={t.path as string}
                          onDirtyChange={(dirty) => setDirtyTabs((prev) => ({ ...prev, [t.id]: dirty }))}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              ) : (
                <EmptyState icon={<Icon name="error" size={24} />} title="File tab has no path" description="Close this tab and open a file from the explorer." />
              )
          )}
        </main>

        {!narrow && contextOpen && (
          <ResizeHandle orientation="vertical" label="Resize Duet context pane"
            value={contextWidth} min={240} max={480}
            onDrag={(delta) => setContextWidth((w) => clamp(w - delta, 240, 480))} />
        )}

        {contextOpen && (
          <aside className={`${s.context} ${narrow ? s.drawer : ""}`} style={narrow ? undefined : { width: contextWidth }} aria-label="Duet context panel">
            <div className={s.contextTabs}><Tabs tabs={CONTEXT_TABS} value={contextTab} onChange={setContextTab} label="Context panels" /></div>
            <div className={s.contextBody}>
              {!project ? (
                <EmptyState icon={<Icon name="info" size={24} />} title="No project context" description="Add a project to see bridge-reported context." />
              ) : contextTab === "context" ? <ContextView project={project} />
                : <EnvironmentView project={project} projectId={selectedId} />}
            </div>
          </aside>
        )}
      </div>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Add a local project"
        footer={<>
          <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={adding} type="submit" form="duet-add-form">Add folder</Button>
        </>}>
        <p className={s.muted}>The bridge runs locally. Provide an absolute path it can see; trust is required afterwards.</p>
        <form id="duet-add-form" onSubmit={(e) => void submitAdd(e)}>
          <TextField label="Absolute folder path" value={addPath} onChange={(e) => setAddPath(e.target.value)} placeholder="C:\\work\\my-project" autoComplete="off" spellCheck={false} required />
          <TextField label="Display name (optional)" value={addName} onChange={(e) => setAddName(e.target.value)} />
          {addError && <p role="alert" className={s.errorBox}>{addError}</p>}
        </form>
      </Dialog>
    </div>
  );
}

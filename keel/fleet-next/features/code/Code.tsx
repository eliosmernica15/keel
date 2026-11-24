"use client";

// Phase 4 — Code: a project-aware coding workspace.
// All data comes from the bridge; trust is never assumed or auto-granted.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Project } from "@/lib/types";
import { Badge, Button, Dialog, EmptyState, IconButton, ResizeHandle, Spinner, Tabs, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import {
  BridgeError, ContextView, EmptyProject, EnvironmentView, FileView, ReviewView,
  TerminalView, TreeView, useNarrow, useProjects, useTree,
} from "./workspace";
import s from "./code.module.css";

type RightTab = "review" | "terminal" | "context" | "environment" | "files";
interface OpenTab { path: string; dirty: boolean }

const RIGHT_TABS: Array<{ value: RightTab; label: string; icon: React.ReactNode }> = [
  { value: "review", label: "Review", icon: <Icon name="tasks" size={14} /> },
  { value: "terminal", label: "Terminal", icon: <Icon name="terminal" size={14} /> },
  { value: "context", label: "Context", icon: <Icon name="info" size={14} /> },
  { value: "environment", label: "Environment", icon: <Icon name="settings" size={14} /> },
  { value: "files", label: "Files", icon: <Icon name="file" size={14} /> },
];

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));

function storedNumber(key: string, fallback: number, min: number, max: number): number {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const n = Number(JSON.parse(raw));
    return Number.isFinite(n) ? clamp(n, min, max) : fallback;
  } catch { return fallback; }
}

export default function Code() {
  const { notify, registerCommands } = useApp();
  const projects = useProjects("keel-code:project");
  const selectedId = projects.selectedId;
  const project = projects.selected;
  const trusted = Boolean(project?.trusted);

  const [explorerWidth, setExplorerWidth] = useState(() => storedNumber("keel-code:explorer-width", 264, 220, 440));
  const [rightWidth, setRightWidth] = useState(() => storedNumber("keel-code:right-width", 352, 280, 560));
  // Hydrate in the lazy initialiser. Previously the write effect ran before
  // the read effect on mount and overwrote a saved panel choice with "review".
  const [rightTab, setRightTab] = useState<RightTab>(() => {
    try {
      const raw = localStorage.getItem("keel-code:right-tab");
      if (raw) {
        const value = JSON.parse(raw) as RightTab;
        if (RIGHT_TABS.some((t) => t.value === value)) return value;
      }
    } catch { /* ignore malformed local state */ }
    return "review";
  });
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [hydratedFor, setHydratedFor] = useState<string | null>(null);
  const [treeQuery, setTreeQuery] = useState("");
  const [quickOpen, setQuickOpen] = useState(false);
  const [quickQuery, setQuickQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [addPath, setAddPath] = useState("");
  const [addName, setAddName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [trustBusy, setTrustBusy] = useState(false);
  const [trustError, setTrustError] = useState<string | null>(null);
  const [chatBusy, setChatBusy] = useState(false);
  const [mobilePane, setMobilePane] = useState<"explorer" | "right" | null>(null);
  const narrow = useNarrow(900);
  const quickInput = useRef<HTMLInputElement>(null);

  const tree = useTree(selectedId, trusted);

  /* ---- persistence ------------------------------------------------ */
  useEffect(() => { try { localStorage.setItem("keel-code:explorer-width", JSON.stringify(explorerWidth)); } catch {} }, [explorerWidth]);
  useEffect(() => { try { localStorage.setItem("keel-code:right-width", JSON.stringify(rightWidth)); } catch {} }, [rightWidth]);
  useEffect(() => { try { localStorage.setItem("keel-code:right-tab", JSON.stringify(rightTab)); } catch {} }, [rightTab]);

  // Hydrate file tabs and pane geometry only for the project they belong to;
  // never show stale paths or another project's layout.
  useEffect(() => {
    let paths: string[] = [];
    let active: string | null = null;
    try {
      const raw = localStorage.getItem("keel-code:tabs");
      if (raw) {
        const saved = JSON.parse(raw) as {
          projectId?: string; paths?: unknown; active?: unknown;
          explorerWidth?: unknown; rightWidth?: unknown; rightTab?: unknown;
        };
        if (saved.projectId === selectedId) {
          paths = Array.isArray(saved.paths) ? saved.paths.filter((p): p is string => typeof p === "string") : [];
          active = typeof saved.active === "string" ? saved.active : paths[0] ?? null;
          if (typeof saved.explorerWidth === "number") setExplorerWidth(clamp(saved.explorerWidth, 220, 440));
          if (typeof saved.rightWidth === "number") setRightWidth(clamp(saved.rightWidth, 280, 560));
          if (RIGHT_TABS.some((t) => t.value === saved.rightTab)) setRightTab(saved.rightTab as RightTab);
        }
      }
    } catch { /* ignore malformed local state */ }
    setTabs(paths.map((path) => ({ path, dirty: false })));
    setActivePath(active);
    setHydratedFor(selectedId);
  }, [selectedId]);

  useEffect(() => {
    if (hydratedFor !== selectedId || !selectedId) return;
    try {
      localStorage.setItem("keel-code:tabs", JSON.stringify({
        projectId: selectedId,
        paths: tabs.map((t) => t.path),
        active: activePath,
        explorerWidth, rightWidth, rightTab,
      }));
    } catch { /* ignore */ }
  }, [hydratedFor, selectedId, tabs, activePath, explorerWidth, rightWidth, rightTab]);

  /* ---- actions ----------------------------------------------------- */
  const selectProject = useCallback((id: string | null) => {
    setTabs([]);
    setActivePath(null);
    setTreeQuery("");
    setTrustError(null);
    projects.select(id);
  }, [projects]);

  const openPath = useCallback((path: string) => {
    setTabs((prev) => prev.some((t) => t.path === path) ? prev : [...prev, { path, dirty: false }]);
    setActivePath(path);
    setQuickOpen(false);
    setQuickQuery("");
    setMobilePane(null);
  }, []);

  const closeTab = useCallback((path: string) => {
    if (tabs.find((t) => t.path === path)?.dirty &&
        !window.confirm("This file has unsaved edits. Close it and discard them?")) return;
    const next = tabs.filter((t) => t.path !== path);
    setTabs(next);
    if (activePath === path) setActivePath(next[next.length - 1]?.path ?? null);
  }, [tabs, activePath]);

  const setDirty = useCallback((path: string, dirty: boolean) => {
    setTabs((prev) => prev.map((t) => t.path === path ? { ...t, dirty } : t));
  }, []);

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
      setAddError(isBridgeUnavailable(err)
        ? `Bridge unavailable: ${errMessage(err)}`
        : errMessage(err));
    } finally { setAdding(false); }
  };

  const decideTrust = async (trustedValue: boolean) => {
    if (!selectedId) return;
    setTrustBusy(true); setTrustError(null);
    try {
      await projects.trust(selectedId, trustedValue);
      notify(trustedValue ? "Folder trusted. File access is now allowed." : "Folder rejected. No files were read.", trustedValue ? "success" : "info");
    } catch (err) {
      setTrustError(errMessage(err));
    } finally { setTrustBusy(false); }
  };

  const openChat = async () => {
    if (!selectedId) return;
    setChatBusy(true);
    try {
      const res = await bridge.startChat(selectedId) as { bot?: { name?: string; id?: string } };
      const name = res?.bot?.name ?? res?.bot?.id;
      notify(name ? `Project chat is ready: ${name}` : "Project chat is ready.", "success");
    } catch (err) { notify(errMessage(err), "error"); }
    finally { setChatBusy(false); }
  };

  const removeProject = async () => {
    if (!selectedId) return;
    const name = project?.name ?? selectedId;
    if (!window.confirm(`Remove ${name} from Keel? Files on disk are untouched.`)) return;
    try { await projects.remove(selectedId); notify("Project removed. Files on disk were untouched.", "info"); }
    catch (err) { notify(errMessage(err), "error"); }
  };

  const refreshProject = async () => {
    if (selectedId) {
      try { await projects.open(selectedId); } catch (err) { notify(errMessage(err), "error"); }
    }
    projects.refresh();
    tree.refresh();
  };

  /* ---- keyboard ---------------------------------------------------- */
  useEffect(() => {
    registerCommands([
      { id: "code.quickOpen", label: "Quick open file", group: "Code", hint: "Ctrl/Cmd+P", run: () => setQuickOpen(true) },
      { id: "code.refreshTree", label: "Refresh project files", group: "Code", run: () => tree.refresh() },
    ]);
  }, [registerCommands, tree.refresh]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault(); setQuickOpen(true); setQuickQuery(""); return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w" && tabs.length) {
        e.preventDefault(); if (activePath) closeTab(activePath); return;
      }
      if (e.ctrlKey && (e.key === "Tab" || e.key === "PageDown" || e.key === "PageUp") && tabs.length > 1) {
        e.preventDefault();
        const idx = tabs.findIndex((t) => t.path === activePath);
        const dir = e.key === "PageUp" || e.shiftKey ? -1 : 1;
        setActivePath(tabs[(idx + dir + tabs.length) % tabs.length].path);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tabs, activePath, closeTab]);

  useEffect(() => { if (quickOpen) window.setTimeout(() => quickInput.current?.focus(), 0); }, [quickOpen]);

  const quickMatches = useMemo(() => {
    const q = quickQuery.trim().toLowerCase();
    return (q ? tree.files.filter((f) => f.path.toLowerCase().includes(q)) : tree.files).slice(0, 100);
  }, [tree.files, quickQuery]);

  const activeTab = tabs.find((t) => t.path === activePath) ?? null;
  const dirtyCount = tabs.filter((t) => t.dirty).length;

  /* ---- trust gate -------------------------------------------------- */
  const trustGate = project && !trusted ? (
    <div className={s.gateWrap}>
      <section className={s.gate} aria-labelledby="trust-title">
        <div className={s.gateIcon}><Icon name="shield" size={30} /></div>
        <h2 id="trust-title">Trust this local folder?</h2>
        <p className={s.gateLead}>
          Keel has not been granted access to <strong>{project.path ?? "(path not reported by bridge)"}</strong>.
          Nothing is read or run until you decide. Keel never trusts a folder automatically.
        </p>
        <dl className={s.scopeList}>
          <div><dt>Read</dt><dd>List files, view text files and calculate a review inside this folder.</dd></div>
          <div><dt>Write</dt><dd>Save edits to files inside this folder, only after you explicitly confirm a save.</dd></div>
          <div><dt>Execute</dt><dd>Run shell commands with this folder as the working directory, still subject to Keel&apos;s permission policy.</dd></div>
          <div><dt>Limit</dt><dd>The bridge blocks paths outside this folder. Trust lasts until it is revoked here; files on disk are never changed by trusting or rejecting.</dd></div>
        </dl>
        {trustError && <p className={s.errorBox} role="alert">{trustError}</p>}
        <div className={s.gateActions}>
          <Button variant="primary" loading={trustBusy} onClick={() => void decideTrust(true)}>
            <Icon name="shield" size={15} /> Trust this folder
          </Button>
          <Button variant="ghost" disabled={trustBusy} onClick={() => void decideTrust(false)}>Reject</Button>
          <Button variant="ghost" disabled={trustBusy} onClick={() => void removeProject()}>Remove project</Button>
        </div>
        {project.trusted === false && <p className={s.hint}>You rejected trust. No files were read; you can trust the folder later or remove it.</p>}
      </section>
    </div>
  ) : null;

  /* ---- render ------------------------------------------------------ */
  return (
    <div className={s.code} data-narrow={narrow ? "true" : "false"}>
      <header className={s.topbar}>
        <div className={s.topbarLeft}>
          <span className={s.crumb}><Icon name="code" size={16} /> Code</span>
          <label className={s.srOnly} htmlFor="code-project">Active project</label>
          <select
            id="code-project"
            className={s.projectSelect}
            value={selectedId ?? ""}
            disabled={projects.loading || Boolean(!projects.projects.length)}
            onChange={(e) => selectProject(e.target.value || null)}
            aria-label="Active project"
          >
            {!projects.projects.length && <option value="">{projects.loading ? "Loading projects…" : "No projects"}</option>}
            {projects.projects.map((p) => <option key={p.id} value={p.id}>{p.name ?? p.path ?? p.id}</option>)}
          </select>
          {project && (
            <Badge tone={trusted ? "success" : "warning"} dot>{trusted ? "Trusted workspace" : "Not trusted"}</Badge>
          )}
        </div>
        <div className={s.topbarRight}>
          <IconButton label="Add a local project" onClick={() => { setAddError(null); setAddOpen(true); }}><Icon name="plus" size={16} /></IconButton>
          <IconButton label="Refresh project state" onClick={() => void refreshProject()}><Icon name="refresh" size={16} /></IconButton>
          <IconButton label="Quick open file" onClick={() => setQuickOpen(true)}><Icon name="search" size={16} /></IconButton>
          {narrow && (
            <>
              <IconButton label="Toggle project explorer" active={mobilePane === "explorer"} onClick={() => setMobilePane((p) => p === "explorer" ? null : "explorer")}><Icon name="folder" size={16} /></IconButton>
              <IconButton label="Toggle right panel" active={mobilePane === "right"} onClick={() => setMobilePane((p) => p === "right" ? null : "right")}><Icon name="panel" size={16} /></IconButton>
            </>
          )}
        </div>
      </header>

      <BridgeError message={projects.error} onRetry={projects.refresh} />

      <div className={s.body}>
        {(!narrow || mobilePane === "explorer") && (
          <aside className={`${s.explorer} ${narrow ? s.drawer : ""}`} style={narrow ? undefined : { width: explorerWidth }} aria-label="Project explorer">
            <div className={s.paneHead}>
              <strong>Explorer</strong>
              <IconButton label="Refresh file tree" disabled={!trusted} onClick={() => tree.refresh()}><Icon name="refresh" size={14} /></IconButton>
            </div>
            {!trusted ? (
              <p className={s.hint}>Trust the selected folder to list its files.</p>
            ) : (
              <>
                <div className={s.searchRow}>
                  <Icon name="search" size={14} />
                  <label className={s.srOnly} htmlFor="tree-filter">Filter files</label>
                  <input id="tree-filter" value={treeQuery} onChange={(e) => setTreeQuery(e.target.value)} placeholder="Filter files…" spellCheck={false} />
                </div>
                {tree.loading && <div className={s.inlineLoad}><Spinner label="Loading file tree" /> Reading folder…</div>}
                <BridgeError message={tree.error} onRetry={tree.refresh} />
                <TreeView nodes={tree.nodes} activePath={activePath} filter={treeQuery} onOpen={openPath} />
                <p className={s.treeFoot}>Hidden and ignored paths are filtered by the bridge; this view does not add or remove files.</p>
              </>
            )}
            {project && !narrow && (
              <div className={s.explorerFoot}>
                <Button size="sm" variant="ghost" loading={chatBusy} onClick={() => void openChat()}>
                  <Icon name="cowork" size={14} /> Open project chat
                </Button>
                <IconButton label="Remove project from Keel" onClick={() => void removeProject()}><Icon name="trash" size={14} /></IconButton>
              </div>
            )}
          </aside>
        )}

        {!narrow && (
          <ResizeHandle orientation="vertical" label="Resize project explorer"
            value={explorerWidth} min={220} max={440}
            onDrag={(delta) => setExplorerWidth((w) => clamp(w + delta, 220, 440))} />
        )}

        <main className={s.main} aria-label="Code workspace">
          <div className={s.tabbar} role="tablist" aria-label="Open files">
            {tabs.map((tab) => (
              <div key={tab.path} className={`${s.tab} ${activePath === tab.path ? s.tabActive : ""}`}>
                <button type="button" role="tab" aria-selected={activePath === tab.path} className={s.tabLabel} onClick={() => setActivePath(tab.path)} title={tab.path}>
                  <Icon name="file" size={13} />
                  <span>{tab.path.split("/").pop() ?? tab.path}</span>
                  {tab.dirty && <span className={s.dirtyDot} title="Unsaved changes" aria-label="Unsaved changes" />}
                </button>
                <IconButton label={`Close ${tab.path}`} className={s.tabClose} onClick={() => closeTab(tab.path)}><Icon name="close" size={12} /></IconButton>
              </div>
            ))}
            {dirtyCount > 0 && <Badge tone="warning">{dirtyCount} unsaved</Badge>}
            <div className={s.tabSpacer} />
            <Button size="sm" variant="ghost" onClick={() => setQuickOpen(true)}><Icon name="search" size={13} /> Quick open</Button>
          </div>
          <div className={s.workArea}>
            {trustGate ?? (
              !project ? (
                <EmptyProject onAdd={() => setAddOpen(true)} />
              ) : tabs.length === 0 || !activeTab ? (
                <EmptyState
                  icon={<Icon name="file" size={28} />}
                  title="No file open"
                  description="Choose a file in the explorer, or use Quick open (Ctrl/Cmd+P) to jump to a path."
                  action={<Button variant="primary" onClick={() => setQuickOpen(true)}><Icon name="search" size={15} /> Quick open</Button>}
                />
              ) : (
                // Keep every open file mounted so an unsaved buffer and its
                // change indicator survive a tab switch. Only the active pane
                // is visible; no file contents are persisted in localStorage.
                <div className={s.fileStack}>
                  {tabs.map((tab) => (
                    <div key={`${selectedId}:${tab.path}`} className={s.filePane} hidden={tab.path !== activePath}>
                      <FileView
                        projectId={selectedId as string}
                        path={tab.path}
                        onDirtyChange={(dirty) => setDirty(tab.path, dirty)}
                      />
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </main>

        {!narrow && (
          <ResizeHandle orientation="vertical" label="Resize right panel"
            value={rightWidth} min={280} max={560}
            onDrag={(delta) => setRightWidth((w) => clamp(w - delta, 280, 560))} />
        )}

        {(!narrow || mobilePane === "right") && (
          <aside className={`${s.right} ${narrow ? s.drawer : ""}`} style={narrow ? undefined : { width: rightWidth }} aria-label="Code context panels">
            <div className={s.rightTabs}>
              <Tabs tabs={RIGHT_TABS} value={rightTab} onChange={setRightTab} label="Context panels" />
            </div>
            <div className={s.rightBody}>
              {!project ? (
                <EmptyState icon={<Icon name="panel" size={24} />} title="No project context" description="Add a trusted project to see review, terminal and environment details." />
              ) : !trusted ? (
                <EmptyState icon={<Icon name="shield" size={24} />} title="Trust required" description="Review and terminal access stay disabled until you trust this folder." />
              ) : rightTab === "review" ? <ReviewView projectId={selectedId as string} />
                : rightTab === "terminal" ? <TerminalView key={selectedId as string} projectId={selectedId as string} cwd={project.path} />
                  : rightTab === "context" ? <ContextView project={project} />
                    : rightTab === "environment" ? <EnvironmentView project={project} projectId={selectedId} />
                      : (
                        <div className={s.panelBody}>
                          <h3>Open files</h3>
                          {tabs.length ? (
                            <ul className={s.fileList}>
                              {tabs.map((t) => (
                                <li key={t.path}>
                                  <button type="button" className={s.fileListItem} onClick={() => setActivePath(t.path)}>
                                    <Icon name="file" size={14} /> <span>{t.path}</span>
                                    {t.dirty && <Badge tone="warning">unsaved</Badge>}
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : <p className={s.hint}>No files are open.</p>}
                          <Button size="sm" onClick={() => setQuickOpen(true)}><Icon name="search" size={14} /> Quick open</Button>
                          <p className={s.hint}>Recent files are restored per project after a restart. The bridge does not expose a separate recent-files endpoint.</p>
                        </div>
                      )}
            </div>
          </aside>
        )}
      </div>

      <Dialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Add a local project"
        footer={<>
          <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form="add-project-form" loading={adding}>Add folder</Button>
        </>}
      >
        <p className={s.muted}>The bridge runs on this machine. Give it an absolute path it can see; Keel will ask for trust before touching any file.</p>
        <form id="add-project-form" onSubmit={(e) => void submitAdd(e)}>
          <TextField label="Absolute folder path" value={addPath} onChange={(e) => setAddPath(e.target.value)} placeholder="C:\\work\\my-project" autoComplete="off" spellCheck={false} required />
          <TextField label="Display name (optional)" value={addName} onChange={(e) => setAddName(e.target.value)} placeholder="my-project" />
          {addError && <p role="alert" className={s.errorBox}>{addError}</p>}
        </form>
      </Dialog>

      <Dialog open={quickOpen} onClose={() => setQuickOpen(false)} title="Quick open file" size="md">
        <div className={s.searchRow}>
          <Icon name="search" size={15} />
          <label className={s.srOnly} htmlFor="quick-open-input">Path filter</label>
          <input id="quick-open-input" ref={quickInput} value={quickQuery} onChange={(e) => setQuickQuery(e.target.value)}
            placeholder="Type a path…" spellCheck={false}
            onKeyDown={(e) => { if (e.key === "Enter" && quickMatches[0]) openPath(quickMatches[0].path); }} />
        </div>
        {tree.loading ? <p className={s.hint}>Reading the project tree…</p> : quickMatches.length ? (
          <ul className={s.quickList} role="listbox" aria-label="Matching files">
            {quickMatches.map((f) => (
              <li key={f.path} role="option" aria-selected={false}>
                <button type="button" className={s.quickItem} onClick={() => openPath(f.path)}>
                  <Icon name="file" size={14} /><span>{f.path}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={s.hint}>{trusted ? "No files match this filter." : "Trust the folder to search its files."}</p>
        )}
      </Dialog>
    </div>
  );
}

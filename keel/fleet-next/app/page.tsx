"use client";

// Keel unified application shell.
// One frame, one navigation model, four work surfaces plus global destinations.
// Feature modules own their own data and state; the shell owns only geometry,
// navigation, theme, notices and the command palette.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppProvider, useApp } from "@/lib/state";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { Icon, KeelMark, type IconName } from "@/components/icons";
import { Badge, Button, IconButton, SegmentedControl, StatusDot } from "@/components/ui";
import ErrorBoundary from "@/components/ErrorBoundary";
import Cowork from "@/features/cowork/Cowork";
import Code from "@/features/code/Code";
import Duet from "@/features/duet/Duet";
import Fleet from "@/features/fleet/Fleet";
import Capabilities from "@/features/capabilities/Capabilities";
import Settings from "@/features/settings/Settings";
import Onboarding from "@/features/onboarding/Onboarding";
import SetupChecklist from "@/features/onboarding/SetupChecklist";
import { restartAtStep } from "@/features/onboarding/progress";
import type { CommandAction, Surface, Theme } from "@/lib/types";

type Destination = Surface | "capabilities" | "settings";
type BridgeStatus = "checking" | "online" | "offline" | "unconfigured";

const SURFACE_ITEMS: Array<{ value: Surface; label: string; icon: IconName }> = [
  { value: "cowork", label: "Cowork", icon: "cowork" },
  { value: "code", label: "Code", icon: "code" },
  { value: "duet", label: "Duet", icon: "duet" },
  { value: "fleet", label: "Fleet", icon: "fleet" },
];

const GLOBAL_ITEMS: Array<{ value: Destination; label: string; icon: IconName }> = [
  { value: "capabilities", label: "Capabilities", icon: "capabilities" },
  { value: "settings", label: "Settings", icon: "settings" },
];

function useBridgeStatus() {
  const [status, setStatus] = useState<BridgeStatus>("checking");
  const [detail, setDetail] = useState("");
  const probe = useCallback(async () => {
    setStatus("checking");
    try {
      await bridge.providers();
      setStatus("online");
      setDetail("Local bridge connected");
    } catch (err) {
      const msg = errMessage(err);
      if (isBridgeUnavailable(err)) { setStatus("unconfigured"); setDetail("Bridge not configured — start `keel fleet`"); }
      else { setStatus("offline"); setDetail(msg); }
    }
  }, []);
  useEffect(() => { void probe(); }, [probe]);
  return { status, detail, probe };
}

function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: CommandAction[] }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? commands.filter((c) => (c.label + " " + (c.group ?? "") + " " + (c.hint ?? "")).toLowerCase().includes(q)) : commands;
    return list.slice(0, 40);
  }, [query, commands]);

  // Reset and focus only when the dialog OPENS. Depending this effect on
  // `filtered` erased the query on every keystroke (D-E2E-004).
  useEffect(() => {
    if (!open) return;
    setQuery(""); setActive(0);
    const prev = document.activeElement as HTMLElement | null;
    window.setTimeout(() => input.current?.focus(), 0);
    return () => { prev?.focus?.(); };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
      else if (e.key === "Tab" && panel.current) {
        const nodes = Array.from(panel.current.querySelectorAll<HTMLElement>('input, button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'));
        if (!nodes.length) return;
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (e.shiftKey && (document.activeElement === first || !panel.current.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || !panel.current.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
      }
      else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[active];
        if (cmd) { onClose(); cmd.run(); }
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => { document.removeEventListener("keydown", onKey, true); };
  }, [open, onClose, filtered, active]);

  if (!open) return null;
  let lastGroup = "";
  return (
    <div className="keel-cmd-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="keel-cmd" role="dialog" aria-modal="true" aria-label="Command palette" ref={panel}>
        <div className="keel-cmd__input-wrap">
          <Icon name="search" size={18} />
          <input ref={input} value={query} onChange={(e) => { setQuery(e.target.value); setActive(0); }} placeholder="Search pages, actions and settings…" aria-label="Search commands" />
          <kbd className="keel-cmd__hint">ESC</kbd>
        </div>
        <div className="keel-cmd__list" role="group" aria-label="Available commands">
          {filtered.length === 0 && <div className="keel-cmd__empty">No matching commands</div>}
          {filtered.map((c, i) => {
            const group = c.group ?? "Actions";
            const showGroup = group !== lastGroup;
            lastGroup = group;
            return (
              <React.Fragment key={c.id}>
                {showGroup && <div className="keel-cmd__group">{group}</div>}
                <button type="button" className={`keel-cmd__item ${i === active ? "is-active" : ""}`} aria-current={i === active ? "true" : undefined} onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onClick={() => { onClose(); c.run(); }}>
                  <Icon name="chevron" size={14} /><span>{c.label}</span>{c.hint && <kbd className="keel-cmd__hint">{c.hint}</kbd>}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Shell() {
  const app = useApp();
  const [destination, setDestination] = useState<Destination>("cowork");
  const surfaceRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const { status: bridgeStatus, detail: bridgeDetail, probe } = useBridgeStatus();

  // AppProvider hydrates the persisted surface after mount. Mirror it here so
  // reloading restores the work surface, not just the stored preference.
  useEffect(() => { setDestination(app.surface); }, [app.surface]);

  const goto = useCallback((d: Destination) => {
    setDestination(d);
    if (d !== "capabilities" && d !== "settings") app.setSurface(d);
    if (window.innerWidth <= 1100) app.setSidebarOpen(false);
  // Only stable setters belong here; depending on the whole `app` object made
  // this callback change on every context update and re-trigger the command
  // registration effect (D-E2E-001).
  }, [app.setSurface, app.setSidebarOpen]);

  const onSurfaceKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (index + 1) % SURFACE_ITEMS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (index - 1 + SURFACE_ITEMS.length) % SURFACE_ITEMS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = SURFACE_ITEMS.length - 1;
    else return;
    e.preventDefault();
    goto(SURFACE_ITEMS[next].value);
    surfaceRefs.current[next]?.focus();
  };

  // "New task" must actually create a task through the bridge, not just
  // navigate. The selected bot is handed to Cowork via its persisted key.
  const [creatingTask, setCreatingTask] = useState(false);
  const startNewTask = useCallback(async () => {
    if (creatingTask) return;
    setCreatingTask(true);
    try {
      const result = await bridge.createBot({
        name: `New task · ${new Date().toLocaleString()}`,
        role: "",
        engine: "provider",
        notes: "",
      }) as { bot?: { id?: string } } | null;
      const id = result?.bot?.id;
      if (id) {
        try { localStorage.setItem("keel-cowork-bot", id); } catch { /* storage disabled */ }
      }
      goto("cowork");
      app.notify(id ? "New task created in Cowork." : "Opened Cowork — create a task from the composer.", id ? "success" : "info");
    } catch (err) {
      app.notify(`Could not create task: ${errMessage(err)}`, "error");
    } finally {
      setCreatingTask(false);
    }
  }, [creatingTask, goto, app]);

  // Register navigation + palette commands once.
  useEffect(() => {
    const nav: CommandAction[] = [
      ...SURFACE_ITEMS.map((s) => ({ id: `nav-${s.value}`, label: `Go to ${s.label}`, group: "Navigate", hint: s.value === "cowork" ? "1" : undefined, run: () => goto(s.value) })),
      ...GLOBAL_ITEMS.map((g) => ({ id: `nav-${g.value}`, label: `Open ${g.label}`, group: "Navigate", run: () => goto(g.value) })),
      { id: "ui-sidebar", label: "Toggle sidebar", group: "Interface", hint: "[", run: () => app.setSidebarOpen(!app.sidebarOpen) },
      { id: "ui-right", label: "Toggle context panel", group: "Interface", hint: "\\", run: () => app.setRightPanelOpen(!app.rightPanelOpen) },
      { id: "ui-theme", label: "Toggle dark / light theme", group: "Interface", run: () => app.setTheme(app.resolvedTheme === "dark" ? "light" : "dark") },
      { id: "tour", label: "Take the product tour", group: "Help", run: () => { restartAtStep("tour"); app.restartOnboarding(); } },
      { id: "bridge-recheck", label: "Re-check bridge connection", group: "System", run: () => void probe() },
    ];
    app.registerCommands(nav);
  }, [app.registerCommands, goto, probe, app.resolvedTheme, app.sidebarOpen, app.rightPanelOpen]);

  // Global keyboard shortcuts — never fire while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); app.setCommandOpen(!app.commandOpen); return; }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Escape" && window.innerWidth <= 1100 && (app.sidebarOpen || app.rightPanelOpen)) {
        e.preventDefault(); app.setSidebarOpen(false); app.setRightPanelOpen(false); return;
      }
      if (e.key === "[") app.setSidebarOpen(!app.sidebarOpen);
      else if (e.key === "\\") app.setRightPanelOpen(!app.rightPanelOpen);
      else if (["1", "2", "3", "4"].includes(e.key)) goto(SURFACE_ITEMS[Number(e.key) - 1].value);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [app, goto]);

  const activeSurface = destination === "capabilities" || destination === "settings" ? null : destination;

  const canvas = useMemo(() => {
    switch (destination) {
      case "code": return <Code />;
      case "duet": return <Duet />;
      case "fleet": return <Fleet />;
      case "capabilities": return <Capabilities />;
      case "settings": return <Settings />;
      default: return <Cowork />;
    }
  }, [destination]);

  const bridgeTone = bridgeStatus === "online" ? "success" : bridgeStatus === "checking" ? "warning" : "danger";
  const bridgeLabel = bridgeStatus === "online" ? "Bridge online" : bridgeStatus === "checking" ? "Checking bridge" : bridgeStatus === "unconfigured" ? "Bridge not configured" : "Bridge offline";

  return (
    <div className="keel-app">
      <a href="#main" className="keel-skip-link">Skip to main content</a>
      <header className="keel-topbar">
        <div className="keel-brand"><KeelMark size={24} /><span className="keel-brand__name">Keel</span></div>
        <IconButton label="Toggle sidebar" onClick={() => app.setSidebarOpen(!app.sidebarOpen)}><Icon name="menu" /></IconButton>
        <div className="keel-topbar__divider" />
        <div className="keel-surface-switch" role="tablist" aria-label="Work surface">
          {SURFACE_ITEMS.map((s, i) => (
            <button
              key={s.value}
              ref={(el) => { surfaceRefs.current[i] = el; }}
              type="button"
              role="tab"
              aria-selected={activeSurface === s.value}
              aria-controls="keel-surface-panel"
              tabIndex={activeSurface === s.value || (!activeSurface && i === 0) ? 0 : -1}
              className={activeSurface === s.value ? "is-active" : ""}
              onClick={() => goto(s.value)}
              onKeyDown={(e) => onSurfaceKeyDown(e, i)}
              title={s.label}
            >
              <Icon name={s.icon} size={15} /><span className="keel-label">{s.label}</span>
            </button>
          ))}
        </div>
        <div className="keel-topbar__spacer" />
        <div className="keel-context-chip" title="Local-first workspace"><Icon name="shield" size={14} /> Local workspace</div>
        <IconButton label="Command palette (Ctrl+K)" onClick={() => app.setCommandOpen(true)}><Icon name="command" /></IconButton>
        <div className="keel-context-chip" title={bridgeDetail}><StatusDot tone={bridgeTone} label={bridgeLabel} /><span>{bridgeStatus === "online" ? "Connected" : "Bridge"}</span></div>
        <IconButton label="Toggle theme" onClick={() => app.setTheme(app.resolvedTheme === "dark" ? "light" : "dark")}><Icon name={app.resolvedTheme === "dark" ? "sun" : "moon"} /></IconButton>
        <IconButton label="Toggle context panel" onClick={() => app.setRightPanelOpen(!app.rightPanelOpen)} active={app.rightPanelOpen}><Icon name="panel" /></IconButton>
      </header>

      <div className="keel-body">
        <aside className={`keel-sidebar ${app.sidebarOpen ? "is-open" : ""}`} style={{ width: app.sidebarWidth }} aria-label="Main navigation">
          <div className="keel-sidebar__head">
            <span className="keel-sidebar__label" style={{ padding: 0 }}>Workspace</span>
            <Badge tone="accent">Local</Badge>
          </div>
          <Button variant="primary" size="md" loading={creatingTask} style={{ margin: "4px 8px 8px" }} onClick={() => void startNewTask()}>
            <Icon name="plus" size={15} /> New task
          </Button>
          <nav className="keel-sidebar__section" aria-label="Surfaces">
            {SURFACE_ITEMS.map((s) => (
              <button key={s.value} className={`keel-nav-item ${destination === s.value ? "is-active" : ""}`} onClick={() => goto(s.value)}>
                <Icon name={s.icon} size={16} /><span className="keel-nav-item__label">{s.label}</span>
              </button>
            ))}
          </nav>
          <div className="keel-sidebar__label">Manage</div>
          <nav className="keel-sidebar__section" aria-label="Management">
            {GLOBAL_ITEMS.map((g) => (
              <button key={g.value} className={`keel-nav-item ${destination === g.value ? "is-active" : ""}`} onClick={() => goto(g.value)}>
                <Icon name={g.icon} size={16} /><span className="keel-nav-item__label">{g.label}</span>
              </button>
            ))}
          </nav>
          <div className="keel-sidebar__foot">
            <SetupChecklist onNavigate={goto} />
            {/* The single contextual desktop entry point in the unified shell.
                A native <a> keeps keyboard/Enter behaviour; Keel's shared
                button classes and icon set keep it visually consistent. */}
            <a
              className="keel-btn keel-btn--ghost keel-btn--sm"
              href="https://keel-desktop.vercel.app/download"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Get Keel Desktop"
              title="Get Keel Desktop (opens in a new tab)"
              style={{ width: "100%", justifyContent: "flex-start", textDecoration: "none" }}
            >
              <Icon name="download" size={15} />
              <span style={{ flex: 1, textAlign: "left" }}>Get Keel Desktop</span>
              <Icon name="external" size={13} />
            </a>
          </div>
        </aside>

        <button
          type="button"
          className={`keel-drawer-scrim ${app.sidebarOpen || app.rightPanelOpen ? "is-open" : ""}`}
          aria-label="Close navigation panels"
          tabIndex={app.sidebarOpen || app.rightPanelOpen ? 0 : -1}
          onClick={() => { app.setSidebarOpen(false); app.setRightPanelOpen(false); }}
        />

        <main className="keel-canvas" id="main" tabIndex={-1}>
          <div id="keel-surface-panel" role="tabpanel" aria-label={destination} style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <ErrorBoundary label={destination} key={destination}>{canvas}</ErrorBoundary>
          </div>
        </main>

        <aside className={`keel-right ${app.rightPanelOpen ? "is-open" : ""}`} style={{ width: app.rightWidth }} aria-label="Context panel">
          <div className="keel-panel-head">
            <h2>Context</h2>
            <IconButton label="Close context panel" onClick={() => app.setRightPanelOpen(false)}><Icon name="close" size={15} /></IconButton>
          </div>
          <div className="keel-panel-body">
            <div className="keel-card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>Runtime</span>
                <Badge tone={bridgeTone} dot>{bridgeStatus === "online" ? "Connected" : bridgeStatus === "checking" ? "Checking" : "Offline"}</Badge>
              </div>
              <p style={{ fontSize: 12, color: "var(--k-muted)", lineHeight: 1.5 }}>{bridgeDetail}</p>
              <Button variant="ghost" size="sm" onClick={() => void probe()}><Icon name="refresh" size={13} /> Re-check</Button>
            </div>

            <div>
              <div className="keel-section-title"><h4>Appearance</h4></div>
              <SegmentedControl<Theme> value={app.theme} onChange={app.setTheme} label="Theme" options={[
                { value: "dark", label: "Dark", icon: <Icon name="moon" size={13} /> },
                { value: "light", label: "Light", icon: <Icon name="sun" size={13} /> },
                { value: "system", label: "System", icon: <Icon name="settings" size={13} /> },
              ]} />
            </div>

            <div>
              <div className="keel-section-title"><h4>Keyboard</h4></div>
              <div style={{ display: "grid", gap: 7, fontSize: 12, color: "var(--k-muted)" }}>
                {[
                  ["Command palette", "Ctrl / ⌘ K"], ["Switch surface", "1 – 4"],
                  ["Toggle sidebar", "["], ["Toggle context", "\\"],
                ].map(([label, key]) => (
                  <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>{label}</span><kbd className="keel-cmd__hint">{key}</kbd>
                  </div>
                ))}
              </div>
            </div>

            <div className="keel-card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600 }}>Local-first by design</div>
              <p style={{ fontSize: 12, color: "var(--k-muted)", lineHeight: 1.55 }}>
                Your files, transcripts and provider keys stay on this machine. The Python runtime enforces permissions and workspace trust.
              </p>
              <Button variant="ghost" size="sm" onClick={() => goto("settings")}>Open settings <Icon name="chevron" size={13} /></Button>
            </div>
          </div>
        </aside>
      </div>

      <footer className="keel-statusbar">
        <span className="keel-statusbar__item"><StatusDot tone={bridgeTone} /> {bridgeLabel}</span>
        <span className="keel-statusbar__item keel-statusbar__item--optional">Surface: <strong style={{ color: "var(--k-text)" }}>{destination}</strong></span>
        <span className="keel-statusbar__item keel-statusbar__item--optional">Theme: {app.theme}</span>
        {app.reduceMotion && <span className="keel-statusbar__item">Reduced motion</span>}
        <span className="keel-statusbar__spacer" />
        <span className="keel-statusbar__item">Keel · local build</span>
      </footer>

      <div className="keel-notices" aria-live="polite" aria-atomic="false">
        {app.notices.map((n) => (
          <div key={n.id} className={`keel-notice keel-notice--${n.kind}`} role={n.kind === "error" ? "alert" : "status"}>
            <Icon name={n.kind === "success" ? "check" : n.kind === "error" ? "error" : n.kind === "warning" ? "warning" : "info"} size={16} />
            <span className="keel-notice__text">{n.message}</span>
            <IconButton label="Dismiss notification" onClick={() => app.dismissNotice(n.id)}><Icon name="close" size={13} /></IconButton>
          </div>
        ))}
      </div>

      <CommandPalette open={app.commandOpen} onClose={() => app.setCommandOpen(false)} commands={app.commands} />

      {!app.onboardingDone && <div className="keel-onboarding-layer"><Onboarding onDone={app.completeOnboarding} /></div>}
    </div>
  );
}

export default function Page() {
  return <AppProvider><Shell /></AppProvider>;
}

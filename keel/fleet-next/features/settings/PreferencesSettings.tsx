"use client";

// Appearance, accessibility status and a narrowly scoped reset. Only settings
// owned by this UI (theme + panel geometry from useApp) can be reset here.

import React, { useState } from "react";
import { Badge, Button, Card, Dialog, SegmentedControl } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useApp } from "@/lib/state";
import type { Theme } from "@/lib/types";
import s from "./settings.module.css";

export function AppearancePanel() {
  const { theme, setTheme, resolvedTheme } = useApp();
  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Appearance</h2>
          <p className={s.muted}>The shared app shell applies this choice to every surface and persists it across restarts.</p>
        </div>
        <Badge tone="info">Resolved: {resolvedTheme}</Badge>
      </div>
      <Card className={s.settingCard}>
        <h3>Theme</h3>
        <p className={s.rowMeta}>Choose dark, light, or follow your operating system.</p>
        <SegmentedControl<Theme>
          label="Theme"
          value={theme}
          onChange={setTheme}
          options={[
            { value: "dark", label: "Dark", icon: <Icon name="moon" size={14} /> },
            { value: "light", label: "Light", icon: <Icon name="sun" size={14} /> },
            { value: "system", label: "System", icon: <Icon name="settings" size={14} /> },
          ]}
        />
      </Card>
    </div>
  );
}

export function AccessibilityPanel() {
  const { reduceMotion, theme, resolvedTheme } = useApp();
  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Accessibility</h2>
          <p className={s.muted}>Real values from the app shell, with honest gaps where this build has no control.</p>
        </div>
      </div>
      <ul className={s.list}>
        <li className={s.row}>
          <div className={s.rowMain}>
            <div className={s.rowTitleLine}><h3 className={s.rowTitle}>Reduced motion</h3><Badge tone={reduceMotion ? "success" : "neutral"} dot>{reduceMotion ? "On (from your OS)" : "Off (from your OS)"}</Badge></div>
            <p className={s.rowMeta}>The shell follows your system's reduced-motion setting. No separate in-app toggle is exposed.</p>
          </div>
        </li>
        <li className={s.row}>
          <div className={s.rowMain}>
            <div className={s.rowTitleLine}><h3 className={s.rowTitle}>Theme &amp; contrast</h3><Badge tone="neutral">{theme} → {resolvedTheme}</Badge></div>
            <p className={s.rowMeta}>Themes use the shared Obsidian &amp; Gold tokens. A separate high-contrast mode is not exposed in this build.</p>
          </div>
        </li>
        <li className={s.row}>
          <div className={s.rowMain}>
            <div className={s.rowTitleLine}><h3 className={s.rowTitle}>Text scale &amp; fonts</h3><Badge tone="warning">Not exposed by the shell</Badge></div>
            <p className={s.rowMeta}>The shell does not provide text/code size or font-picker state, so no control is shown here. Use your browser zoom or OS font settings instead.</p>
          </div>
        </li>
        <li className={s.row}>
          <div className={s.rowMain}>
            <div className={s.rowTitleLine}><h3 className={s.rowTitle}>Keyboard</h3><Badge tone="success">Shared components</Badge></div>
            <p className={s.rowMeta}>Buttons, dialogs and fields use the shared primitives with visible focus, Escape handling in dialogs and labelled controls.</p>
          </div>
        </li>
      </ul>
    </div>
  );
}

export function ResetPanel() {
  const { notify, theme, sidebarOpen, rightPanelOpen, sidebarWidth, rightWidth, setTheme, setSidebarOpen, setRightPanelOpen, setSidebarWidth, setRightWidth } = useApp();
  const [confirmOpen, setConfirmOpen] = useState(false);

  function reset() {
    setTheme("dark");
    setSidebarOpen(true);
    setRightPanelOpen(true);
    setSidebarWidth(272);
    setRightWidth(340);
    setConfirmOpen(false);
    notify("Theme and panel layout reset to defaults.", "success");
  }

  return (
    <div className={s.panel}>
      <div className={s.sectionHead}>
        <div>
          <h2>Reset to defaults</h2>
          <p className={s.muted}>Only preferences owned by this UI are reset. Bridge data, credentials, projects and agent state are never touched.</p>
        </div>
        <Button variant="danger" onClick={() => setConfirmOpen(true)}>Preview reset…</Button>
      </div>
      <Card className={s.noteCard}>
        <div className={s.noteTitle}><Icon name="info" size={16} /> Scope of this action</div>
        <p>The preview below lists every value this action changes. Nothing happens until you confirm.</p>
      </Card>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Preview reset"
        footer={<>
          <Button variant="ghost" onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button variant="danger" onClick={reset}>Apply these defaults</Button>
        </>}>
        <table className={s.resetTable}>
          <thead><tr><th scope="col">Setting</th><th scope="col">Current</th><th scope="col">After reset</th></tr></thead>
          <tbody>
            <tr><td>Theme</td><td>{theme}</td><td>dark</td></tr>
            <tr><td>Sidebar</td><td>{sidebarOpen ? "open" : "closed"}</td><td>open</td></tr>
            <tr><td>Right panel</td><td>{rightPanelOpen ? "open" : "closed"}</td><td>open</td></tr>
            <tr><td>Sidebar width</td><td>{sidebarWidth}px</td><td>272px</td></tr>
            <tr><td>Right panel width</td><td>{rightWidth}px</td><td>340px</td></tr>
          </tbody>
        </table>
      </Dialog>
    </div>
  );
}

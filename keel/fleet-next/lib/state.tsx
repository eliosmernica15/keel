"use client";

// Global UI state: theme, active surface, panel geometry, notices, command
// palette and onboarding. Persisted preferences live in localStorage; agent
// data never does (it always comes from the bridge).

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { CommandAction, Notice, Surface, Theme } from "./types";

interface AppState {
  surface: Surface;
  setSurface: (s: Surface) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  resolvedTheme: "dark" | "light";
  sidebarOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
  rightPanelOpen: boolean;
  setRightPanelOpen: (v: boolean) => void;
  sidebarWidth: number;
  setSidebarWidth: (n: number) => void;
  rightWidth: number;
  setRightWidth: (n: number) => void;
  commandOpen: boolean;
  setCommandOpen: (v: boolean) => void;
  notices: Notice[];
  notify: (message: string, kind?: Notice["kind"]) => void;
  dismissNotice: (id: string) => void;
  commands: CommandAction[];
  registerCommands: (commands: CommandAction[]) => void;
  onboardingDone: boolean;
  completeOnboarding: () => void;
  restartOnboarding: () => void;
  reduceMotion: boolean;
}

const Ctx = createContext<AppState | null>(null);

const SURFACES: Surface[] = ["cowork", "code", "duet", "fleet"];
const THEMES: Theme[] = ["dark", "light", "system"];

function readStored<T>(key: string, fallback: T, valid: (v: unknown) => v is T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return valid(parsed) ? parsed : fallback;
  } catch { return fallback; }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [surface, setSurfaceState] = useState<Surface>("cowork");
  // Match the pre-paint script: with no stored preference, follow the OS.
  const [theme, setThemeState] = useState<Theme>("system");
  const [systemDark, setSystemDark] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(272);
  const [rightWidth, setRightWidth] = useState(340);
  const [commandOpen, setCommandOpen] = useState(false);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [commands, setCommands] = useState<CommandAction[]>([]);
  const [onboardingDone, setOnboardingDone] = useState(true);
  const [reduceMotion, setReduceMotion] = useState(false);
  // Do not overwrite the pre-paint values set by layout.tsx until preferences
  // have actually been hydrated, otherwise a saved light theme flashes dark.
  const [hydrated, setHydrated] = useState(false);
  const noticeSeq = useRef(0);

  // hydrate persisted preferences after mount
  useEffect(() => {
    setSurfaceState(readStored("keel-surface", "cowork", (v): v is Surface => SURFACES.includes(v as Surface)));
    setThemeState(readStored<Theme>("keel-theme-v2", "system", (v): v is Theme => THEMES.includes(v as Theme)));
    const narrow = window.innerWidth <= 1100;
    // On compact desktops the shell context panel plus Code/Duet's own right
    // panel collapse the editor to ~42px. Keep the shell panel closed by
    // default until there is enough width; users can still open it manually.
    const compact = window.innerWidth <= 1440;
    setSidebarOpen(narrow ? false : readStored("keel-sidebar-open", true, (v): v is boolean => typeof v === "boolean"));
    setRightPanelOpen(compact ? false : readStored("keel-right-open", true, (v): v is boolean => typeof v === "boolean"));
    setSidebarWidth(readStored("keel-sidebar-width", 272, (v): v is number => typeof v === "number" && v >= 200 && v <= 460));
    setRightWidth(readStored("keel-right-width", 340, (v): v is number => typeof v === "number" && v >= 260 && v <= 620));
    setOnboardingDone(readStored("keel-onboarding-done", false, (v): v is boolean => typeof v === "boolean"));

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    const mqr = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mqr.matches);
    const onMotion = (e: MediaQueryListEvent) => setReduceMotion(e.matches);

    // addEventListener is missing on older Safari MediaQueryList objects.
    if (mq.addEventListener) mq.addEventListener("change", onChange); else mq.addListener(onChange);
    if (mqr.addEventListener) mqr.addEventListener("change", onMotion); else mqr.addListener(onMotion);

    // Batched with the state updates above, so the first committed render after
    // hydration already has the stored theme and the live media-query values.
    setHydrated(true);

    return () => {
      if (mq.removeEventListener) mq.removeEventListener("change", onChange); else mq.removeListener(onChange);
      if (mqr.removeEventListener) mqr.removeEventListener("change", onMotion); else mqr.removeListener(onMotion);
    };
  }, []);

  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    if (!hydrated) return;
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
    document.documentElement.dataset.reducedMotion = reduceMotion ? "true" : "false";
  }, [hydrated, resolvedTheme, reduceMotion]);

  const setSurface = useCallback((s: Surface) => {
    setSurfaceState(s);
    try { localStorage.setItem("keel-surface", JSON.stringify(s)); } catch { /* ignore */ }
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try { localStorage.setItem("keel-theme-v2", JSON.stringify(t)); } catch { /* ignore */ }
  }, []);

  // Drawer state on narrow screens is session-only; only persist desktop
  // panel preferences so a mobile visit cannot close panels on desktop.
  useEffect(() => { if (window.innerWidth <= 1100) return; try { localStorage.setItem("keel-sidebar-open", JSON.stringify(sidebarOpen)); } catch {} }, [sidebarOpen]);
  useEffect(() => { if (window.innerWidth <= 1440) return; try { localStorage.setItem("keel-right-open", JSON.stringify(rightPanelOpen)); } catch {} }, [rightPanelOpen]);
  useEffect(() => { try { localStorage.setItem("keel-sidebar-width", JSON.stringify(sidebarWidth)); } catch {} }, [sidebarWidth]);
  useEffect(() => { try { localStorage.setItem("keel-right-width", JSON.stringify(rightWidth)); } catch {} }, [rightWidth]);

  const dismissNotice = useCallback((id: string) => setNotices((n) => n.filter((x) => x.id !== id)), []);

  const notify = useCallback((message: string, kind: Notice["kind"] = "info") => {
    const id = `n${Date.now()}-${noticeSeq.current++}`;
    setNotices((prev) => [...prev, { id, message, kind, ts: Date.now() }].slice(-4));
    window.setTimeout(() => setNotices((prev) => prev.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4500);
  }, []);

  const registerCommands = useCallback((next: CommandAction[]) => {
    setCommands((prev) => {
      // Bail out when the catalogue is unchanged. Without this guard a caller
      // whose effect depends on app state re-registers on every render and
      // triggers an infinite "Maximum update depth exceeded" loop.
      if (prev.length === next.length && prev.every((c, i) =>
        c.id === next[i].id && c.label === next[i].label &&
        c.group === next[i].group && c.hint === next[i].hint)) return prev;
      const ids = new Set(next.map((c) => c.id));
      return [...next, ...prev.filter((c) => !ids.has(c.id))];
    });
  }, []);

  const completeOnboarding = useCallback(() => {
    setOnboardingDone(true);
    try { localStorage.setItem("keel-onboarding-done", "true"); } catch { /* ignore */ }
  }, []);
  const restartOnboarding = useCallback(() => {
    setOnboardingDone(false);
    try { localStorage.setItem("keel-onboarding-done", "false"); } catch { /* ignore */ }
  }, []);

  const value = useMemo<AppState>(() => ({
    surface, setSurface, theme, setTheme, resolvedTheme,
    sidebarOpen, setSidebarOpen, rightPanelOpen, setRightPanelOpen,
    sidebarWidth, setSidebarWidth, rightWidth, setRightWidth,
    commandOpen, setCommandOpen, notices, notify, dismissNotice,
    commands, registerCommands, onboardingDone, completeOnboarding, restartOnboarding,
    reduceMotion,
  }), [surface, setSurface, theme, setTheme, resolvedTheme, sidebarOpen, rightPanelOpen,
    sidebarWidth, rightWidth, commandOpen, notices, notify, dismissNotice, commands,
    registerCommands, onboardingDone, completeOnboarding, restartOnboarding, reduceMotion]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

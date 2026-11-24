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
  const [theme, setThemeState] = useState<Theme>("dark");
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
  const noticeSeq = useRef(0);

  // hydrate persisted preferences after mount
  useEffect(() => {
    setSurfaceState(readStored("keel-surface", "cowork", (v): v is Surface => SURFACES.includes(v as Surface)));
    setThemeState(readStored<Theme>("keel-theme-v2", "dark", (v): v is Theme => THEMES.includes(v as Theme)));
    setSidebarOpen(readStored("keel-sidebar-open", true, (v): v is boolean => typeof v === "boolean"));
    setRightPanelOpen(readStored("keel-right-open", true, (v): v is boolean => typeof v === "boolean"));
    setSidebarWidth(readStored("keel-sidebar-width", 272, (v): v is number => typeof v === "number" && v >= 200 && v <= 460));
    setRightWidth(readStored("keel-right-width", 340, (v): v is number => typeof v === "number" && v >= 260 && v <= 620));
    setOnboardingDone(readStored("keel-onboarding-done", false, (v): v is boolean => typeof v === "boolean"));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    const mqr = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mqr.matches);
    const onMotion = (e: MediaQueryListEvent) => setReduceMotion(e.matches);
    mqr.addEventListener("change", onMotion);
    return () => {
      mq.removeEventListener("change", onChange);
      mqr.removeEventListener("change", onMotion);
    };
  }, []);

  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.reducedMotion = reduceMotion ? "true" : "false";
  }, [resolvedTheme, reduceMotion]);

  const setSurface = useCallback((s: Surface) => {
    setSurfaceState(s);
    try { localStorage.setItem("keel-surface", JSON.stringify(s)); } catch { /* ignore */ }
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try { localStorage.setItem("keel-theme-v2", JSON.stringify(t)); } catch { /* ignore */ }
  }, []);

  useEffect(() => { try { localStorage.setItem("keel-sidebar-open", JSON.stringify(sidebarOpen)); } catch {} }, [sidebarOpen]);
  useEffect(() => { try { localStorage.setItem("keel-right-open", JSON.stringify(rightPanelOpen)); } catch {} }, [rightPanelOpen]);
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

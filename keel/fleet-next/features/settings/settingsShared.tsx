"use client";

// Shared settings helpers: a single bridge loader with honest error states and
// the canonical section registry used by both navigation and search.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, Skeleton } from "@/components/ui";
import { errMessage, isBridgeUnavailable } from "@/lib/api";
import type { IconName } from "@/components/icons";
import s from "./settings.module.css";

export interface BridgeData<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  unavailable: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

export function useBridgeData<T>(loader: () => Promise<T>): BridgeData<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [data, setDataState] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await loaderRef.current();
      setDataState(result);
      setError(null);
      setUnavailable(false);
    } catch (err) {
      setError(errMessage(err));
      setUnavailable(isBridgeUnavailable(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const setData = useCallback((value: T | null) => setDataState(value), []);
  return { data, loading, error, unavailable, reload, setData };
}

export function PanelState<T>({ query, children }: { query: BridgeData<T>; children: (data: T) => React.ReactNode }) {
  if (query.loading && query.data === null) {
    return (
      <div className={s.skeletonList} role="status" aria-label="Loading settings data">
        <Skeleton height={64} className={s.skeletonRow} />
        <Skeleton height={64} className={s.skeletonRow} />
        <Skeleton height={64} className={s.skeletonRow} />
      </div>
    );
  }
  if (query.data === null) {
    return (
      <div className={s.errorBox} role="alert">
        <strong>{query.unavailable ? "The local bridge is unavailable" : "Could not load this setting"}</strong>
        <p>{query.error ?? "No response from the bridge."}</p>
        <p className={s.muted}>Start `keel fleet` and confirm this app's bridge token matches the bridge process.</p>
        <Button onClick={query.reload}>Retry</Button>
      </div>
    );
  }
  return (
    <>
      {query.error && <p className={s.staleError} role="status">Last refresh failed: {query.error}. Showing the last loaded data.</p>}
      {children(query.data)}
    </>
  );
}

export function asArray<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const candidate = (value as Record<string, unknown>)[key];
    if (Array.isArray(candidate)) return candidate as T[];
  }
  return [];
}

export function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export type SectionId =
  | "providers" | "agent-models" | "credentials" | "permissions" | "trust" | "network"
  | "privacy" | "diagnostics" | "appearance" | "accessibility" | "reset";

export interface SectionDef {
  id: SectionId;
  title: string;
  category: string;
  description: string;
  keywords: string;
  icon: IconName;
}

export const SETTINGS_SECTIONS: SectionDef[] = [
  { id: "providers", title: "Providers & models", category: "Models & providers", description: "Configured providers, model catalogue and real model metadata.", keywords: "model catalog catalogue api key provider default", icon: "spark" },
  { id: "agent-models", title: "Agent models", category: "Models & providers", description: "Set each agent's model through the real agent-update route, or clear it to use the provider default.", keywords: "agent model default per agent bots update provider catalog select", icon: "spark" },
  { id: "credentials", title: "Credentials", category: "Models & providers", description: "Session-only and persisted keys — never stored in this browser.", keywords: "secret key password credential token save remove secure", icon: "shield" },
  { id: "permissions", title: "Permission mode", category: "Security & trust", description: "Choose how much the agent may do before asking you.", keywords: "mode build plan autopilot accept edits approval policy", icon: "shield" },
  { id: "trust", title: "Workspace trust", category: "Security & trust", description: "Folders Keel may read and write, with explicit trust decisions.", keywords: "project folder path symlink revoke trusted workspace", icon: "folder" },
  { id: "network", title: "Network & egress", category: "Security & trust", description: "What the bridge exposes about network rules.", keywords: "egress firewall domains allowed network rules", icon: "link" },
  { id: "privacy", title: "Privacy & data", category: "Privacy & system", description: "Real usage totals and local-first storage facts.", keywords: "usage tokens transcripts retention export privacy data", icon: "user" },
  { id: "diagnostics", title: "System diagnostics", category: "Privacy & system", description: "Bridge health probe and what this build can report.", keywords: "health version startup logs diagnostics bridge bundle", icon: "info" },
  { id: "appearance", title: "Appearance", category: "Preferences", description: "Dark, light or system theme, applied everywhere by the app shell.", keywords: "theme dark light system color appearance", icon: "moon" },
  { id: "accessibility", title: "Accessibility", category: "Preferences", description: "Motion state, keyboard access and supported display options.", keywords: "reduced motion text scale font contrast screen reader keyboard", icon: "user" },
  { id: "reset", title: "Reset to defaults", category: "Preferences", description: "Preview and confirm resets for settings this UI owns.", keywords: "reset defaults theme panels restore", icon: "refresh" },
];

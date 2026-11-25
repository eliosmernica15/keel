"use client";

// Shared settings helpers: a single bridge loader with honest error states and
// the canonical section registry used by both navigation and search.
//
// The registry mirrors the settings screenshot: a left sidebar grouped into
// SETTINGS, THIS COMPUTER and CUSTOMIZE, each section rendered as a card in
// the main content area.

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
  | "general" | "providers" | "agent-models" | "credentials" | "usage" | "privacy" | "import-export" | "keel-code" | "keel-desktop"
  | "policies" | "admin" | "network" | "system" | "developer" | "appearance" | "accessibility" | "reset"
  | "skills" | "commands" | "workflows" | "mcp-servers" | "plugins";

export interface SectionDef {
  id: SectionId;
  title: string;
  category: string;
  description: string;
  keywords: string;
  icon: IconName;
}

// Canonical registry, grouped into the screenshot's sidebar categories:
// SETTINGS · THIS COMPUTER · CUSTOMIZE
export const SETTINGS_SECTIONS: SectionDef[] = [
  // SETTINGS
  { id: "general", title: "General", category: "SETTINGS", description: "Your account, this device and general preferences.", keywords: "account device general preferences local", icon: "user" },
  { id: "providers", title: "Providers & models", category: "SETTINGS", description: "Configured providers and the model catalogue.", keywords: "provider model catalogue", icon: "spark" },
  { id: "agent-models", title: "Agent models", category: "SETTINGS", description: "Choose a model for each provider-backed agent.", keywords: "agent model per-agent", icon: "agents" },
  { id: "credentials", title: "Credentials", category: "SETTINGS", description: "Manage provider keys stored on this machine or in the current bridge session.", keywords: "credentials api keys provider secrets", icon: "shield" },
  { id: "usage", title: "Usage", category: "SETTINGS", description: "Usage totals reported by the bridge.", keywords: "usage tokens requests cost", icon: "clock" },
  { id: "privacy", title: "Privacy & data", category: "SETTINGS", description: "Privacy and local-first data handling.", keywords: "privacy data retention storage", icon: "shield" },
  { id: "import-export", title: "Import & export", category: "SETTINGS", description: "Import and export settings and data.", keywords: "import export backup restore", icon: "download" },
  { id: "keel-code", title: "Keel Code", category: "SETTINGS", description: "Keel Code integration settings.", keywords: "keel code", icon: "code" },
  { id: "keel-desktop", title: "Keel Desktop", category: "SETTINGS", description: "Keel Desktop application settings.", keywords: "keel desktop electron", icon: "panel" },
  // THIS COMPUTER
  { id: "policies", title: "Permission mode", category: "THIS COMPUTER", description: "Permission mode for new composer sessions.", keywords: "policy permission mode", icon: "shield" },
  { id: "admin", title: "Workspace trust", category: "THIS COMPUTER", description: "Review and manage trusted workspaces.", keywords: "admin trust workspace projects", icon: "settings" },
  { id: "network", title: "Network & egress", category: "THIS COMPUTER", description: "Network egress capabilities exposed by this build.", keywords: "network egress domains rules", icon: "link" },
  { id: "system", title: "System diagnostics", category: "THIS COMPUTER", description: "System diagnostics and updates.", keywords: "system diagnostics updates health", icon: "info" },
  { id: "developer", title: "Developer", category: "THIS COMPUTER", description: "Developer tools and options.", keywords: "developer debug", icon: "terminal" },
  { id: "appearance", title: "Appearance", category: "THIS COMPUTER", description: "Theme and display preferences.", keywords: "theme dark light system", icon: "sun" },
  { id: "accessibility", title: "Accessibility", category: "THIS COMPUTER", description: "Motion, contrast and keyboard accessibility.", keywords: "accessibility motion contrast keyboard", icon: "info" },
  { id: "reset", title: "Reset to defaults", category: "THIS COMPUTER", description: "Review and reset local interface preferences.", keywords: "reset defaults layout theme", icon: "refresh" },
  // CUSTOMIZE
  { id: "skills", title: "Skills", category: "CUSTOMIZE", description: "Skills and capabilities.", keywords: "skills capability", icon: "spark" },
  { id: "commands", title: "Commands", category: "CUSTOMIZE", description: "Slash commands.", keywords: "commands slash", icon: "command" },
  { id: "workflows", title: "Workflows", category: "CUSTOMIZE", description: "Workflows and routines.", keywords: "workflow routine", icon: "routine" },
  { id: "mcp-servers", title: "MCP Servers", category: "CUSTOMIZE", description: "MCP server connections.", keywords: "mcp server connector", icon: "link" },
  { id: "plugins", title: "Plugins", category: "CUSTOMIZE", description: "Plugins.", keywords: "plugin", icon: "more" },
];

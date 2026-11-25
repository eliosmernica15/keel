"use client";

// Shared, evidence-only helpers for the Capability Hub. Nothing here invents a
// capability: every status comes from a bridge response or a real test result.

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Skeleton } from "@/components/ui";
import { errMessage, isBridgeUnavailable } from "@/lib/api";
import type { CapabilityState } from "@/lib/types";
import s from "./capabilities.module.css";

export interface BridgeData<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  unavailable: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

/** Load one bridge resource. Keeps the last good data on refresh failure. */
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

/** The bridge wraps lists either as a bare array or as { key: [...] }. */
export function asArray<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const candidate = (value as Record<string, unknown>)[key];
    if (Array.isArray(candidate)) return candidate as T[];
  }
  return [];
}

const STATE_META: Record<CapabilityState, { label: string; tone: "neutral" | "success" | "warning" | "danger" | "info" }> = {
  available: { label: "Available", tone: "success" },
  unconfigured: { label: "Not configured", tone: "warning" },
  "requires-setup": { label: "Needs attention", tone: "warning" },
  blocked: { label: "Blocked", tone: "danger" },
  unsupported: { label: "Not in this build", tone: "neutral" },
};

export function StateBadge({ state, label }: { state: CapabilityState; label?: string }) {
  const meta = STATE_META[state];
  return <Badge tone={meta.tone} dot>{label ?? meta.label}</Badge>;
}

/** Loading skeleton, bridge error with retry, then real data. */
export function PanelState<T>({
  query,
  children,
}: {
  query: BridgeData<T>;
  children: (data: T) => React.ReactNode;
}) {
  if (query.loading && query.data === null) {
    return (
      <div className={s.skeletonList} role="status" aria-label="Loading capability data">
        <Skeleton height={72} className={s.skeletonRow} />
        <Skeleton height={72} className={s.skeletonRow} />
        <Skeleton height={72} className={s.skeletonRow} />
      </div>
    );
  }
  if (query.data === null) {
    return (
      <div className={s.errorBox} role="alert">
        <strong>{query.unavailable ? "The local bridge is unavailable" : "Could not load this capability"}</strong>
        <p>{query.error ?? "No response from the bridge."}</p>
        <p className={s.muted}>
          {query.unavailable
            ? "Start `keel fleet`, then make sure this app's KEEL_BRIDGE_TOKEN matches the token printed by the bridge."
            : "Retry the request, or check the bridge process."}
        </p>
        <Button onClick={query.reload}><span aria-hidden="true">↻</span> Retry</Button>
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

/** A source/scope label that never guesses a scope the bridge did not report. */
export function scopeLabel(scope: unknown): string {
  if (typeof scope !== "string" || !scope) return "Scope not reported";
  if (scope === "bundled" || scope === "builtin" || scope === "built-in") return "Built-in (bundled)";
  if (scope === "user") return "User";
  if (scope === "project") return "Project";
  return scope;
}

export function formatCount(n: unknown): string {
  return typeof n === "number" && Number.isFinite(n) ? String(n) : "not reported";
}

/** Bridge payloads are untyped in places; narrow them without guessing values. */
export function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function textOf(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export function safeResult(value: unknown, limit = 4000): string {
  const raw = typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2);
  return raw.length > limit ? `${raw.slice(0, limit)}\n… (truncated)` : raw;
}

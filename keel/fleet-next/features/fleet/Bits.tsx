"use client";

import React, { useEffect, useRef } from "react";
import { Badge, Button, EmptyState, IconButton, Skeleton } from "@/components/ui";
import { Icon } from "@/components/icons";
import { errMessage, isBridgeUnavailable } from "@/lib/api";
import type { Bot } from "@/lib/types";
import s from "./fleet.module.css";
import { activityTone, type ActivityView, type Resource } from "./support";

export function Avatar({ bot, small = false }: { bot: { id: string; name?: string; avatar_hue?: unknown }; small?: boolean }) {
  const hue = typeof bot.avatar_hue === "number" ? bot.avatar_hue : 210;
  const name = bot.name || bot.id || "?";
  const initials = name.split(/\s+/).map((p) => p[0]).filter(Boolean).slice(0, 2).join("").toUpperCase() || "?";
  return <span className={`${s.avatar} ${small ? s.avatarSm : ""}`} style={{ ["--hue" as string]: String(hue) }} aria-hidden="true">{initials}</span>;
}

export function ActivityDot({ state }: { state: ActivityView["state"] }) {
  const cls = state === "working" ? s.dotWorking : state === "waiting" ? s.dotWaiting : state === "idle" ? s.dotIdle : state === "failed" ? s.dotFailed : "";
  const labels: Record<ActivityView["state"], string> = {
    working: "Active run", waiting: "Waiting for you", idle: "Turn complete", failed: "Failed", unknown: "State not reported",
  };
  return <span className={`${s.dot} ${cls}`} role="img" aria-label={labels[state]} />;
}

export function ActivityBadge({ state }: { state: ActivityView["state"] }) {
  const labels: Record<ActivityView["state"], string> = {
    working: "working", waiting: "waiting for you", idle: "idle", failed: "failed", unknown: "not reported",
  };
  return <Badge tone={activityTone(state)} dot>{labels[state]}</Badge>;
}

/** Honest error/offline state for a bridge resource, with a real retry. */
export function ResourceNotice<T>({
  resource, emptyTitle, emptyDescription, emptyAction, children,
}: {
  resource: Resource<T>;
  emptyTitle: string;
  emptyDescription?: string;
  emptyAction?: React.ReactNode;
  children: (data: T) => React.ReactNode;
}) {
  if (resource.loading && resource.data === null) {
    return <div aria-busy="true" aria-label="Loading">{Array.from({ length: 3 }, (_, i) => <div key={i} className={s.skeletonLine} />)}</div>;
  }
  if (resource.error && resource.data === null) {
    const offline = resource.unavailable || isBridgeUnavailable(resource.error);
    return (
      <EmptyState
        icon={<Icon name={offline ? "warning" : "error"} size={26} />}
        title={offline ? "Local bridge unavailable" : "Could not load this view"}
        description={offline
          ? "Start `keel fleet` (or check KEEL_BRIDGE_URL / KEEL_BRIDGE_TOKEN) and retry. No data is shown while the bridge is offline."
          : errMessage(resource.error)}
        action={<Button variant="secondary" onClick={resource.reload}><Icon name="refresh" size={15} /> Retry</Button>}
      />
    );
  }
  const data = resource.data;
  if (data === null || (Array.isArray(data) && data.length === 0)) {
    return <EmptyState icon={<Icon name="fleet" size={26} />} title={emptyTitle} description={emptyDescription} action={emptyAction} />;
  }
  return <>{children(data)}</>;
}

/** Banner for a failed SSE stream; the data view may still be stale-but-real. */
export function StreamNotice({ streamError, onRetry }: { streamError: boolean; onRetry: () => void }) {
  if (!streamError) return null;
  return (
    <div className={s.banner} role="status">
      <Icon name="warning" size={17} />
      <span className={s.bannerText}>
        <strong>Live event stream disconnected.</strong>
        <small>Showing the last rows loaded from the bridge. Reconnect to resume live updates.</small>
      </span>
      <Button variant="secondary" onClick={onRetry}><Icon name="refresh" size={15} /> Reconnect</Button>
    </div>
  );
}

export function Drawer({ title, subtitle, onClose, tabs, active, onTab, children }: {
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  tabs: Array<{ value: string; label: string }>;
  active: string;
  onTab: (v: string) => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab" || !panelRef.current) return;
      const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    panelRef.current?.querySelector<HTMLElement>("button, input, select, textarea")?.focus();
    return () => { document.removeEventListener("keydown", onKey, true); previous?.focus?.(); };
  }, [onClose]);
  return (
    <div className={s.drawer} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className={s.drawerPanel} role="dialog" aria-modal="true" aria-label={`${title} details`} ref={panelRef}>
        <div className={s.drawerHead}>
          <div style={{ minWidth: 0 }}>
            <h2 className={s.drawerTitle}>{title}</h2>
            {subtitle && <div className={s.small}>{subtitle}</div>}
          </div>
          <IconButton label="Close details" onClick={onClose}><Icon name="close" size={17} /></IconButton>
        </div>
        <div className={s.drawerTabs} role="tablist" aria-label="Agent details sections">
          {tabs.map((t) => (
            <button key={t.value} role="tab" className={s.drawerTab} aria-selected={t.value === active} onClick={() => onTab(t.value)}>{t.label}</button>
          ))}
        </div>
        <div className={s.drawerBody}>{children}</div>
      </aside>
    </div>
  );
}

"use client";

// Fleet command centre. Every section reads and writes the Python bridge via
// the shared lib/api.ts contract; no status, progress or audit data is faked.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { Icon, type IconName } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, FleetEvent, FleetTask, LibraryItem, Routine } from "@/lib/types";
import s from "./fleet.module.css";
import Agents from "./Agents";
import Groups from "./Groups";
import Tasks from "./Tasks";
import Routines from "./Routines";
import Library from "./Library";
import Audit from "./Audit";
import Board from "./Board";
import OrgChart from "./OrgChart";
import LiveWall from "./LiveWall";
import CostPanel from "./CostPanel";
import {
  wrapped, useBridgeResource, useFleetEvents, useAllBotRows, type FleetGroup,
} from "./support";

type Tab = "agents" | "groups" | "tasks" | "board" | "org" | "live" | "cost" | "routines" | "library" | "audit";
// Fleet tab matrix (surface fix plan Section 7.2): hide tabs that have no
// real data yet; show them only when their backing data exists.
const TABS: Array<{ value: Tab; label: string; icon: IconName; hidden?: boolean }> = [
  { value: "agents", label: "Agents", icon: "agents" },
  { value: "groups", label: "Groups", icon: "fleet", hidden: true },
  { value: "tasks", label: "Tasks", icon: "tasks" },
  { value: "board", label: "Board", icon: "tasks" },
  { value: "cost", label: "Cost", icon: "info" },
  { value: "routines", label: "Routines", icon: "routine" },
  { value: "library", label: "Library", icon: "library" },
  { value: "org", label: "Delegation map", icon: "fleet", hidden: true },
  { value: "live", label: "Live wall", icon: "agents", hidden: true },
  { value: "audit", label: "Decision history", icon: "shield" },
];

export default function Fleet() {
  const { registerCommands, notify } = useApp();
  const [tab, setTab] = useState<Tab>("agents");
  const [focusBotId, setFocusBotId] = useState<string | null>(null);
  const [events, setEvents] = useState<FleetEvent[]>([]);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  /** WAI-ARIA tablist: one tab in the tab order, arrow/Home/End move focus. */
  const onTabKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>, index: number, visibleTabs: typeof TABS) => {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % visibleTabs.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + visibleTabs.length) % visibleTabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = visibleTabs.length - 1;
    else return;
    event.preventDefault();
    setTab(visibleTabs[next].value);
    tabRefs.current[next]?.focus();
  }, []);

  const botsResource = useBridgeResource(
    useCallback(() => bridge.listBots().then((r) => wrapped<Bot>(r as Record<string, unknown>, "bots")), []), []);
  const groupsResource = useBridgeResource(
    useCallback(() => bridge.groups().then((r) => wrapped<FleetGroup>(r as Record<string, unknown>, "groups")), []), []);
  const tasksResource = useBridgeResource(
    useCallback(() => bridge.tasks().then((r) => wrapped<FleetTask>(r as Record<string, unknown>, "tasks")), []), []);
  const routinesResource = useBridgeResource(
    useCallback(() => bridge.routines().then((r) => wrapped<Routine>(r as Record<string, unknown>, "routines")), []), []);
  const libraryResource = useBridgeResource(
    useCallback(() => bridge.library(), []), []);

  const onEvent = useCallback((e: MessageEvent) => {
    try {
      const data = JSON.parse(String(e.data)) as FleetEvent;
      if (!data || typeof data !== "object") return;
      setEvents((prev) => [...prev.slice(-399), data]);
    } catch { /* ignore non-JSON keep-alives */ }
  }, []);
  const { streamError, retry: retryStream } = useFleetEvents(onEvent);

  const bots = botsResource.data ?? [];
  // Shared transcript rows for the real-data views. Loaded once per roster;
  // no agent state or usage value is fabricated from these rows.
  const rowsResource = useAllBotRows(bots);
  const counts: Record<Tab, number> = {
    agents: bots.length,
    groups: (groupsResource.data ?? []).length,
    tasks: (tasksResource.data ?? []).length,
    board: (tasksResource.data ?? []).length,
    org: bots.length,
    live: bots.length,
    cost: 0,
    routines: (routinesResource.data ?? []).length,
    library: wrapped<LibraryItem>(libraryResource.data as Record<string, unknown>, "files").length,
    audit: 0,
  };
  const visibleTabs = TABS.filter((t) => !t.hidden || counts[t.value] > 0);

  const refreshAll = useCallback(() => {
    botsResource.reload(); groupsResource.reload(); tasksResource.reload(); routinesResource.reload(); libraryResource.reload(); rowsResource.reload();
  }, [botsResource.reload, groupsResource.reload, tasksResource.reload, routinesResource.reload, libraryResource.reload, rowsResource.reload]);

  const unavailable = botsResource.unavailable || groupsResource.unavailable || tasksResource.unavailable || routinesResource.unavailable || libraryResource.unavailable;
  const primaryError = botsResource.error ?? groupsResource.error ?? tasksResource.error ?? routinesResource.error ?? libraryResource.error;

  useEffect(() => {
    registerCommands([
      { id: "fleet.refresh", label: "Fleet: refresh all sections", group: "Fleet", run: refreshAll },
      { id: "fleet.agents", label: "Fleet: open agents", group: "Fleet", run: () => setTab("agents") },
      { id: "fleet.tasks", label: "Fleet: open tasks", group: "Fleet", run: () => setTab("tasks") },
      { id: "fleet.board", label: "Fleet: open task board", group: "Fleet", run: () => setTab("board") },
      { id: "fleet.org", label: "Fleet: open delegation map", group: "Fleet", run: () => setTab("org") },
      { id: "fleet.live", label: "Fleet: open live wall", group: "Fleet", run: () => setTab("live") },
      { id: "fleet.cost", label: "Fleet: open cost view", group: "Fleet", run: () => setTab("cost") },
    ]);
  }, [registerCommands, refreshAll]);

  const openAgent = useCallback((id: string) => { setFocusBotId(id); setTab("agents"); }, []);

  const content = useMemo(() => {
    switch (tab) {
      case "agents":
        return <Agents botsResource={botsResource} events={events} streamError={streamError} onRetryStream={retryStream} onChanged={refreshAll} focusBotId={focusBotId} />;
      case "groups":
        return <Groups bots={bots} groupsResource={groupsResource} events={events} streamError={streamError} onRetryStream={retryStream} />;
      case "tasks":
        return <Tasks tasksResource={tasksResource} bots={bots} onOpenBot={openAgent} />;
      case "board":
        return <Board tasksResource={tasksResource} bots={bots} onOpenBot={openAgent} />;
      case "org":
        return <OrgChart bots={bots} rowsResource={rowsResource} onOpenBot={openAgent} />;
      case "live":
        return <LiveWall bots={bots} rowsResource={rowsResource} events={events} streamError={streamError} onRetryStream={retryStream} onOpenBot={openAgent} />;
      case "cost":
        return <CostPanel bots={bots} rowsResource={rowsResource} />;
      case "routines":
        return <Routines routinesResource={routinesResource} bots={bots} />;
      case "library":
        return <Library libraryResource={libraryResource} bots={bots} tasks={tasksResource.data ?? []} />;
      case "audit":
        return <Audit botsResource={botsResource} />;
    }
  }, [tab, botsResource, bots, groupsResource, events, streamError, retryStream, refreshAll, tasksResource, routinesResource, libraryResource, focusBotId, rowsResource, openAgent]);

  return (
    <div className={s.root}>
      <header className={s.head}>
        <div style={{ minWidth: 0 }}>
          <h1 className={s.headTitle}>Fleet</h1>
          <p className={s.headSub}>Named agents, shared groups, tasks, routines, library files and the bridge&apos;s own decision record — all read from the local Python bridge.</p>
        </div>
        <div className={s.headActions}>
          <Button size="sm" variant="secondary" onClick={() => { refreshAll(); notify("Fleet sections refreshed."); }}><Icon name="refresh" size={14} /> Refresh all</Button>
        </div>
      </header>

      {unavailable && (
        <div className={s.banner} role="status">
          <Icon name="warning" size={18} />
          <div className={s.bannerText}>
            <strong>Local bridge unavailable.</strong>
            <small>{errMessage(primaryError)} — start `keel fleet` or check the bridge URL/token, then retry. No offline placeholder data is shown.</small>
          </div>
          <Button variant="secondary" onClick={refreshAll}><Icon name="refresh" size={15} /> Retry</Button>
        </div>
      )}

      <div className={s.tabs} role="tablist" aria-label="Fleet sections">
        {visibleTabs.map((t, i) => (
          <button
            key={t.value}
            ref={(el) => { tabRefs.current[i] = el; }}
            role="tab"
            id={`fleet-tab-${t.value}`}
            aria-selected={tab === t.value}
            aria-controls="fleet-sections"
            tabIndex={tab === t.value ? 0 : -1}
            className={s.tab}
            onClick={() => setTab(t.value)}
            onKeyDown={(e) => onTabKeyDown(e, i, visibleTabs)}
          >
            <Icon name={t.icon} size={15} /> {t.label}
            {counts[t.value] > 0 && <span className={s.tabCount}>{counts[t.value]}</span>}
          </button>
        ))}
      </div>

      <main id="fleet-sections" aria-labelledby={`fleet-tab-${tab}`}>{content}</main>
    </div>
  );
}

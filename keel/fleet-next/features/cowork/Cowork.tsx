"use client";

// Cowork — a calm task workspace built entirely on the real bridge contract.
// No invented bots, rows, files, statuses or successful outcomes.

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon, IconButton, KeelMark } from "@/components/icons";
import { Badge, Button, Skeleton, TextField } from "@/components/ui";
import { bridge, errMessage, isBridgeUnavailable, subscribeEvents } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, CatalogResponse, Notice, Provider, Usage } from "@/lib/types";
import Composer, { COMPOSER_MODES, type ComposerMode, type UploadedFile } from "./Composer";
import Timeline from "./Timeline";
import WorkLog from "./WorkLog";
import SearchPanel from "./Search";
import { LiveBubble, StreamBuffer } from "./LiveStream";
import {
  deriveStatus, findRowMatches, formatTime, textOf, toBots, toLibrary, toProjects, toRows,
  type LibraryView, type ProjectView, type RowView,
} from "./shared";
import s from "./cowork.module.css";

const QUICK_PROMPTS = [
  "Summarize the key points of a document in this workspace.",
  "Find where a feature is implemented and explain how it works.",
  "Draft a short project update from my notes.",
  "Review recent changes and list what needs attention.",
];

// Long transcripts are rendered as a bounded window; older rows are added a
// page at a time. This keeps token streaming and scrolling cheap.
const WINDOW_SIZE = 150;
const WINDOW_PAGE = 100;

interface ScrollRestore {
  /** Stable row sequence from data-cowork-seq, when an anchor was available. */
  seq: string | null;
  /** Row top relative to the scroll viewport's top (bottom-aligned for jump). */
  offset: number;
  /** Fallback: distance from the viewport top to the bottom before the change. */
  distance: number;
}

function rowNodes(el: HTMLElement): HTMLElement[] {
  return Array.from(el.querySelectorAll<HTMLElement>("[data-cowork-seq]"));
}

function captureRowAnchor(el: HTMLElement, align: "top" | "bottom"): ScrollRestore {
  const viewportTop = el.getBoundingClientRect().top;
  const nodes = rowNodes(el).filter((node) => node.getBoundingClientRect().height > 0);
  const node = align === "bottom"
    ? nodes[nodes.length - 1]
    : nodes.find((candidate) => {
      const rect = candidate.getBoundingClientRect();
      return rect.bottom > viewportTop + 1 && rect.top < viewportTop + el.clientHeight;
    });
  const rect = node?.getBoundingClientRect();
  return {
    seq: node?.getAttribute("data-cowork-seq") ?? null,
    offset: rect ? (align === "bottom" ? el.clientHeight - rect.height : rect.top - viewportTop) : 0,
    distance: align === "bottom" ? 0 : Math.max(0, el.scrollHeight - el.scrollTop),
  };
}

const TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  idle: "neutral", running: "info", completed: "success",
  "waiting-for-user": "warning", queued: "warning", paused: "warning",
  failed: "danger", cancelled: "danger",
};

function unwrapBot(input: unknown): Bot | null {
  if (!input || typeof input !== "object") return null;
  const obj = input as Record<string, unknown>;
  const bot = (obj.bot ?? obj) as Record<string, unknown>;
  return typeof bot.id === "string" ? (bot as unknown as Bot) : null;
}

function normalizeProviders(input: unknown): Provider[] {
  const list = Array.isArray(input) ? input : (input && typeof input === "object" ? (input as Record<string, unknown>).providers : null);
  return Array.isArray(list) ? (list as Provider[]).filter((p): p is Provider => !!p && typeof p.id === "string") : [];
}

export default function Cowork() {
  const { notify, reduceMotion } = useApp();

  const [bots, setBots] = useState<Bot[]>([]);
  const [botsLoading, setBotsLoading] = useState(true);
  const [botsError, setBotsError] = useState<string | null>(null);
  const [botId, setBotId] = useState<string | null>(null);

  const [rows, setRows] = useState<RowView[]>([]);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);

  const [providers, setProviders] = useState<Provider[]>([]);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [library, setLibrary] = useState<LibraryView[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);

  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [runStart, setRunStart] = useState<number | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const [sendError, setSendError] = useState<string | null>(null);

  const [mode, setMode] = useState<ComposerMode>("build");
  const [offline, setOffline] = useState(false);
  const [answeredAsks, setAnsweredAsks] = useState<Set<string>>(new Set());
  const [models, setModels] = useState<string[]>([]);
  const [modelSaving, setModelSaving] = useState(false);

  // Provider / model selection on the home page (before a task exists).
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [catalogModels, setCatalogModels] = useState<string[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  // Permission mode is a user preference shared with Settings and Onboarding.
  // Read it after mount (localStorage is unavailable during prerender) and
  // persist changes so the choice survives reloads.
  useEffect(() => {
    try {
      const raw = localStorage.getItem("keel-mode");
      if (raw === "build" || raw === "plan" || raw === "autopilot" || raw === "acceptEdits") setMode(raw);
    } catch { /* storage disabled; keep the safe default */ }
  }, []);
  const changeMode = useCallback((next: ComposerMode) => {
    setMode(next);
    try { localStorage.setItem("keel-mode", next); } catch { /* ignore */ }
  }, []);
  const [seed, setSeed] = useState<{ text: string; nonce: number }>({ text: "", nonce: 0 });
  const [focusSignal, setFocusSignal] = useState(0);
  const [workLogOpen, setWorkLogOpen] = useState(false);

  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeMatch, setActiveMatch] = useState(-1);
  const [searchFocusTick, setSearchFocusTick] = useState(0);
  const [windowCount, setWindowCount] = useState(WINDOW_SIZE);
  const [anchorTick, setAnchorTick] = useState(0);

  const botIdRef = useRef<string | null>(null);
  const rowsReq = useRef(0);
  const lastEventSeq = useRef(0);
  const lastAttempt = useRef<{ text: string; uploaded: UploadedFile[]; botId: string } | null>(null);
  const reloadTimer = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const scrollRestore = useRef<ScrollRestore | null>(null);
  const pendingSeq = useRef<string | null>(null);
  const streamRef = useRef<StreamBuffer | null>(null);
  if (!streamRef.current) streamRef.current = new StreamBuffer();
  const stream = streamRef.current;

  useEffect(() => { botIdRef.current = botId; }, [botId]);
  useEffect(() => () => stream.dispose(), [stream]);

  // One stable start time per turn, so the live elapsed timer never resets.
  useEffect(() => {
    if (busy || streaming) setRunStart((prev) => prev ?? Date.now());
    else setRunStart(null);
  }, [busy, streaming]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("keel-cowork-bot");
      if (stored) setBotId(stored);
    } catch { /* storage disabled */ }
  }, []);

  // Honest offline state: reflect the browser's own connectivity signal and
  // re-check the bridge when connectivity returns. Never claim "connected"
  // from this alone — the bridge probe remains the source of truth.
  useEffect(() => {
    const sync = () => setOffline(!navigator.onLine);
    sync();
    window.addEventListener("offline", sync);
    window.addEventListener("online", sync);
    return () => {
      window.removeEventListener("offline", sync);
      window.removeEventListener("online", sync);
    };
  }, []);

  const selectBot = useCallback((id: string | null) => {
    setBotId(id);
    try {
      if (id) localStorage.setItem("keel-cowork-bot", id);
      else localStorage.removeItem("keel-cowork-bot");
    } catch { /* storage disabled */ }
    setSendError(null);
    setRowsError(null);
    setStreamError(null);
    setSearchOpen(false); setQuery(""); setActiveMatch(-1);
    setWindowCount(WINDOW_SIZE);
    scrollRestore.current = null; pendingSeq.current = null;
    stream.clear();
    lastEventSeq.current = 0;
    lastAttempt.current = null;
  }, [stream]);

  /* --------------------------- bridge loaders --------------------------- */

  const loadBots = useCallback(async () => {
    setBotsLoading(true); setBotsError(null);
    try {
      setBots(toBots(await bridge.listBots()));
    } catch (err) {
      setBotsError(isBridgeUnavailable(err)
        ? "The local bridge is unavailable. Start Keel's local bridge and retry."
        : errMessage(err));
    } finally { setBotsLoading(false); }
  }, []);

  const loadRows = useCallback(async (id?: string | null) => {
    const target = id ?? botIdRef.current;
    if (!target) { setRows([]); return; }
    const req = ++rowsReq.current;
    setRowsLoading(true); setRowsError(null);
    try {
      const next = toRows(await bridge.botRows(target));
      if (req === rowsReq.current) setRows(next);
    } catch (err) {
      if (req === rowsReq.current) {
        setRowsError(isBridgeUnavailable(err)
          ? "Conversation could not load — the local bridge is unavailable."
          : errMessage(err));
      }
    } finally { if (req === rowsReq.current) setRowsLoading(false); }
  }, []);

  const loadUsage = useCallback(async () => {
    try { setUsage(await bridge.usage()); } catch { /* usage is optional metadata */ }
  }, []);

  const loadMeta = useCallback(async () => {
    setMetaLoading(true); setMetaError(null);
    const [providersResult, projectsResult, libraryResult] = await Promise.allSettled([
      bridge.providers(), bridge.projects(), bridge.library(),
    ]);
    if (providersResult.status === "fulfilled") setProviders(normalizeProviders(providersResult.value));
    else setMetaError(isBridgeUnavailable(providersResult.reason)
      ? "The local bridge is unavailable — workspace and provider status are unknown."
      : errMessage(providersResult.reason));
    if (projectsResult.status === "fulfilled") setProjects(toProjects(projectsResult.value));
    if (libraryResult.status === "fulfilled") setLibrary(toLibrary(libraryResult.value));
    setMetaLoading(false);
  }, []);

  const loadCatalog = useCallback(async (providerId: string) => {
    setCatalogLoading(true); setCatalogError(null); setCatalogModels([]); setSelectedModel(null);
    try {
      const result = await bridge.catalog({ name: providerId, source: "offline" }) as CatalogResponse;
      const list = Array.isArray(result?.models) ? result.models.map((m) => m.id).filter((id): id is string => typeof id === "string") : [];
      setCatalogModels(list);
      if (list.length > 0) setSelectedModel(list[0]);
    } catch (err) {
      setCatalogError(errMessage(err));
    } finally { setCatalogLoading(false); }
  }, []);

  useEffect(() => { void loadBots(); void loadMeta(); void loadUsage(); }, [loadBots, loadMeta, loadUsage]);

  useEffect(() => {
    stream.clear();
    setWindowCount(WINDOW_SIZE);
    setSearchOpen(false); setQuery(""); setActiveMatch(-1);
    scrollRestore.current = null; pendingSeq.current = null;
    if (!botId) { setRows([]); setBusy(false); setAnsweredAsks(new Set()); setModels([]); return; }
    void loadRows(botId);
    setWorkLogOpen(true);
    try {
      const raw = localStorage.getItem(`keel-ask-answered:${botId}`);
      const ids = raw ? JSON.parse(raw) : [];
      setAnsweredAsks(new Set(Array.isArray(ids) ? ids.filter((id): id is string => typeof id === "string") : []));
    } catch { setAnsweredAsks(new Set()); }
  }, [botId, loadRows, stream]);

  /* --------------------------- live event stream ------------------------ */

  useEffect(() => {
    let disposed = false;
    lastEventSeq.current = 0;
    const unsubscribe = subscribeEvents(
      (message: MessageEvent) => {
        if (disposed) return;
        let ev: Record<string, unknown>;
        try { ev = JSON.parse(message.data) as Record<string, unknown>; } catch { return; }
        if (!ev || typeof ev !== "object") return;

        // The stream carries a monotonic cursor/seq; never process an event twice.
        const seq = typeof ev.seq === "number" ? ev.seq : typeof ev.cursor === "number" ? ev.cursor : null;
        if (seq != null) {
          if (seq <= lastEventSeq.current) return;
          lastEventSeq.current = seq;
        }

        const eventBot = typeof ev.bot_id === "string" ? ev.bot_id : null;
        if (eventBot && eventBot !== botIdRef.current) return;

        if (ev.type === "stream" || ev.kind === "stream") {
          const delta = typeof ev.delta === "string" ? ev.delta : typeof ev.text === "string" ? ev.text : "";
          // Only the isolated live bubble subscribes to this buffer; no parent
          // state changes here, so the durable timeline never re-renders per
          // token. LiveBubble reads the buffer's own active flag.
          stream.append(delta);
          return;
        }

        if (ev.kind === "error" || ev.type === "error") {
          setStreamError(textOf(ev.error ?? ev.message ?? "The event stream reported an error."));
          setStreaming(false); setBusy(false);
          stream.clear();
          return;
        }

        const durable = ["turn_end", "message", "step", "approval", "ask", "notice", "plan"];
        if (typeof ev.kind === "string" && durable.includes(ev.kind)) {
          if (ev.kind === "turn_end") {
            setBusy(false);
            setStreaming(false);
            stream.clear();
            void loadUsage();
            void loadMeta();
          }
          if (reloadTimer.current != null) window.clearTimeout(reloadTimer.current);
          reloadTimer.current = window.setTimeout(() => {
            reloadTimer.current = null;
            if (botIdRef.current) void loadRows(botIdRef.current);
          }, 180);
        }
      },
      () => {
        if (disposed) return;
        // A dropped SSE connection does not mean the agent's turn ended. Keep
        // the last known stream visible and offer an explicit reconnect; only
        // a real turn_end or backend error event clears the live state.
        setStreamError("The event stream was interrupted. Reconnect to resume live updates.");
      },
    );
    return () => {
      disposed = true;
      unsubscribe();
      if (reloadTimer.current != null) window.clearTimeout(reloadTimer.current);
      reloadTimer.current = null;
    };
  }, [streamKey, loadRows, loadUsage, loadMeta, stream]);

  /* --------------------- windowed history, scroll and search ------------ */

  // Only the newest WINDOW_SIZE rows are in the DOM. Search still sees every
  // loaded row and expands the window when a match lives further back.
  const visibleRows = useMemo(
    () => rows.length > windowCount ? rows.slice(rows.length - windowCount) : rows,
    [rows, windowCount],
  );
  const hiddenCount = rows.length - visibleRows.length;
  const matches = useMemo(() => findRowMatches(rows, query), [rows, query]);
  const activeSeq = searchOpen && activeMatch >= 0 ? matches[activeMatch]?.seq ?? null : null;

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (pendingSeq.current != null) {
      const seq = pendingSeq.current;
      pendingSeq.current = null;
      const raf = requestAnimationFrame(() => {
        const node = rowNodes(el).find((n) => n.getAttribute("data-cowork-seq") === seq);
        if (!node) return;
        const details = node.closest("details");
        if (details) details.open = true;
        node.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
      });
      return () => cancelAnimationFrame(raf);
    }
    const restore = scrollRestore.current;
    if (restore) {
      scrollRestore.current = null;
      // Prefer the stable row seq: layout changes in neighbouring rows (new
      // group headings, different bubble heights) cannot shift the anchor.
      const node = restore.seq
        ? rowNodes(el).find((n) => n.getAttribute("data-cowork-seq") === restore.seq)
        : null;
      if (node) {
        const offset = node.getBoundingClientRect().top - el.getBoundingClientRect().top;
        el.scrollTop += offset - restore.offset;
      } else {
        // The anchor left the window (e.g. a collapse): keep the old distance
        // from the bottom instead of jumping unpredictably.
        el.scrollTop = Math.max(0, el.scrollHeight - restore.distance);
      }
      return;
    }
    if (!atBottom.current) return;
    const raf = requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    return () => cancelAnimationFrame(raf);
  }, [visibleRows.length, anchorTick, reduceMotion]);

  // Follow new streamed text only while the user is already near the bottom.
  // This subscription updates scrollTop directly — no React state, no history
  // render, no lost scroll position.
  useEffect(() => stream.subscribe(() => {
    // React bails out when the value is unchanged: tokens after the first do
    // not re-render the page. The first token marks the turn live; clear()
    // marks it finished.
    setStreaming(stream.getLiveSnapshot());
    if (!atBottom.current) return;
    const el = scrollRef.current;
    if (!el) return;
    requestAnimationFrame(() => { if (atBottom.current) el.scrollTop = el.scrollHeight; });
  }), [stream]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    atBottom.current = near;
    setShowJump(!near);
  }, []);

  const showEarlier = useCallback(() => {
    const el = scrollRef.current;
    // Anchor the row currently at the top of the viewport; the distance is
    // only used if that row is no longer rendered after paging.
    if (el) scrollRestore.current = captureRowAnchor(el, "top");
    setWindowCount((count) => Math.min(rows.length, count + WINDOW_PAGE));
  }, [rows.length]);

  const jumpToLatest = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (hiddenCount > 0) {
      // Collapsing the window keeps the newest row; bottom-align it through
      // the same anchored restore path (distance fallback = scroll to bottom).
      scrollRestore.current = captureRowAnchor(el, "bottom");
      setWindowCount(WINDOW_SIZE);
    } else {
      el.scrollTo({ top: el.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    }
    atBottom.current = true; setShowJump(false);
  }, [hiddenCount, reduceMotion]);

  const openSearch = useCallback(() => {
    if (!botIdRef.current) return;
    setSearchOpen(true);
    setSearchFocusTick((n) => n + 1);
  }, []);

  const closeSearch = useCallback(() => {
    setSearchOpen(false); setActiveMatch(-1);
  }, []);

  const selectMatch = useCallback((index: number) => {
    const match = matches[index];
    if (!match) return;
    setActiveMatch(index);
    pendingSeq.current = String(match.seq);
    const windowStart = rows.length - visibleRows.length;
    if (match.index < windowStart) {
      setWindowCount(rows.length - match.index + Math.floor(WINDOW_SIZE / 2));
    } else {
      setAnchorTick((n) => n + 1);
    }
  }, [matches, rows.length, visibleRows.length]);

  const stepMatch = useCallback((delta: number) => {
    if (!matches.length) return;
    const base = activeMatch < 0 ? (delta > 0 ? -1 : 0) : activeMatch;
    selectMatch((base + delta + matches.length) % matches.length);
  }, [matches.length, activeMatch, selectMatch]);

  // Ctrl/⌘+F opens search from anywhere in the Cowork session; the input
  // handles Enter / Shift+Enter / arrows / Escape itself.
  useEffect(() => {
    if (!botId) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        openSearch();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [botId, openSearch]);

  /* --------------------------- actions ---------------------------------- */

  const createTask = useCallback(async (): Promise<Bot | null> => {
    try {
      const created = unwrapBot(await bridge.createBot({
        name: "Cowork task",
        role: "General assistant",
        engine: "provider",
        provider: selectedProviderId ?? undefined,
        model: selectedModel ?? undefined,
      }));
      if (!created?.id) throw new Error("The bridge did not return a new task id.");
      setBots((prev) => [created, ...prev]);
      selectBot(created.id);
      notify("New Cowork task created.", "success");
      return created;
    } catch (err) {
      notify(`Could not create a task: ${errMessage(err)}`, "error");
      return null;
    }
  }, [notify, selectBot, selectedProviderId, selectedModel]);

  // The composer ensures a real bot exists before uploading files to its library.
  const ensureBot = useCallback(async (): Promise<string | null> => {
    if (botIdRef.current) return botIdRef.current;
    const created = await createTask();
    return created?.id ?? null;
  }, [createTask]);

  const send = useCallback(async (text: string, uploaded: UploadedFile[], id: string): Promise<boolean> => {
    let content = text;
    if (uploaded.length) {
      const names = uploaded.map((f) => f.name).join(", ");
      content += `\n\n[Library files added to this agent's library and referenced by name (not attached to the model prompt): ${names}]`;
    }
    if (content.length > 32000) {
      setSendError("Message is too long — the bridge accepts at most 32,000 characters.");
      return false;
    }
    lastAttempt.current = { text, uploaded, botId: id };
    setSendError(null);
    setBusy(true);
    try {
      const result = await bridge.sendMessage(id, { content, mode }) as { queued?: boolean; busy?: boolean } | null;
      if (result && result.queued === false) {
        await loadRows(id); // the bridge still records the user row on a busy turn
        setSendError("The agent is busy — your message was not queued. Retry after this turn ends.");
        notify("Agent is busy — message not queued.", "info");
        return false;
      }
      stream.clear();
      await loadRows(id);
      setBusy(false);
      return true;
    } catch (err) {
      const msg = errMessage(err);
      const busyTurn = /409/.test(msg) || /busy/i.test(msg);
      await loadRows(id);
      setBusy(false);
      setSendError(busyTurn
        ? "The agent is busy — your message was not queued. Retry after this turn ends."
        : `Message failed: ${msg}`);
      notify(busyTurn ? "Agent is busy — message not queued." : `Message failed: ${msg}`, busyTurn ? "info" : "error");
      return false;
    }
  }, [loadRows, mode, notify, stream]);

  const stop = useCallback(() => {
    const id = botIdRef.current;
    if (!id) return;
    void (async () => {
      try {
        await bridge.cancel(id);
        setBusy(false); setStreaming(false);
        stream.clear();
        notify("Stop requested — the turn ends at the next model boundary.", "info");
        await loadRows(id);
      } catch (err) {
        notify(`Stop failed: ${errMessage(err)}`, "error");
      }
    })();
  }, [loadRows, notify, stream]);

  const decide = useCallback(async (row: RowView, decision: "once" | "always" | "never") => {
    const id = botIdRef.current;
    const approvalId = textOf(row.body.approval_id);
    if (!id || !approvalId) { notify("No approval id was reported by the bridge.", "error"); return false; }
    try {
      await bridge.decideApproval(id, approvalId, decision);
      await loadRows(id);
      notify("Permission decision recorded.", "success");
      return true;
    } catch (err) {
      notify(`Approval decision failed: ${errMessage(err)}`, "error");
      return false;
    }
  }, [loadRows, notify]);

  const answer = useCallback(async (row: RowView, value: string) => {
    const id = botIdRef.current;
    const askId = textOf(row.body.ask_id ?? row.body.id);
    if (!id || !askId) { notify("No question id was reported by the bridge.", "error"); return false; }
    try {
      await bridge.answerAsk(id, askId, value);
      // The bridge does not rewrite the ask row on answer. Remember only the
      // confirmed id (never the answer text) so a reload cannot show a stale
      // "waiting for you" card.
      setAnsweredAsks((prev) => {
        const next = new Set(prev).add(askId);
        try { localStorage.setItem(`keel-ask-answered:${id}`, JSON.stringify([...next])); } catch { /* ignore */ }
        return next;
      });
      await loadRows(id);
      notify("Answer sent.", "success");
      return true;
    } catch (err) {
      notify(`Answer failed: ${errMessage(err)}`, "error");
      return false;
    }
  }, [loadRows, notify]);

  const changeModel = useCallback(async (model: string) => {
    const id = botIdRef.current;
    if (!id) return;
    setModelSaving(true);
    try {
      const updated = unwrapBot(await bridge.updateBot(id, { model }));
      setBots((prev) => prev.map((b) => b.id === id ? ((updated ?? { ...b, model }) as Bot) : b));
      notify(`Model saved on this task: ${model}.`, "success");
    } catch (err) {
      notify(`Could not save the model: ${errMessage(err)}`, "error");
    } finally { setModelSaving(false); }
  }, [notify]);

  const copy = useCallback((row: RowView) => {
    void (async () => {
      try {
        await navigator.clipboard.writeText(textOf(row.body.content));
        notify("Message copied.", "success");
      } catch { notify("Clipboard access was denied.", "error"); }
    })();
  }, [notify]);

  const fork = useCallback((row: RowView) => {
    const id = botIdRef.current;
    if (!id) return;
    void (async () => {
      try {
        const result = unwrapBot(await bridge.forkBot(id, { up_to_seq: row.seq }));
        await loadBots();
        if (result?.id) selectBot(result.id);
        notify("A new branch was created from this message.", "success");
      } catch (err) { notify(`Fork failed: ${errMessage(err)}`, "error"); }
    })();
  }, [loadBots, notify, selectBot]);

  const rewind = useCallback((row: RowView) => {
    const id = botIdRef.current;
    if (!id || !window.confirm("Rewind the conversation to before this message?")) return;
    void (async () => {
      try {
        await bridge.rewind(id, { from_seq: row.seq });
        await loadRows(id);
        notify("Conversation rewound.", "success");
      } catch (err) { notify(`Rewind failed: ${errMessage(err)}`, "error"); }
    })();
  }, [loadRows, notify]);

  const usePrompt = (prompt: string) => {
    setSeed({ text: prompt, nonce: Date.now() });
    setFocusSignal((n) => n + 1);
  };

  /* --------------------------- derived view ----------------------------- */

  const bot = useMemo(() => bots.find((b) => b.id === botId) ?? null, [bots, botId]);

  // Offline model catalogue for the active task. Only real bridge models are
  // offered; if the catalog fails, the composer shows a read-only model label.
  useEffect(() => {
    let disposed = false;
    setModels([]);
    const provider = bot?.provider;
    if (!botId || !provider) return () => { disposed = true; };
    void (async () => {
      try {
        const result = await bridge.catalog({ name: provider, source: "offline" }) as { models?: unknown };
        const list = Array.isArray(result?.models) ? result.models.filter((m): m is string => typeof m === "string") : [];
        if (!disposed) setModels(list);
      } catch { if (!disposed) setModels([]); }
    })();
    return () => { disposed = true; };
  }, [botId, bot?.provider]);

  const status = useMemo(
    () => deriveStatus(bot, rows, busy || streaming, answeredAsks),
    [bot, rows, busy, streaming, answeredAsks],
  );
  const providerReady = providers.length === 0 ? null : providers.some((p) => p.configured || p.connected);
  const workspace = projects[0];
  const activeSince = status.state === "running" ? runStart : null;

  // Memoised so parent state changes (and stream status flips) cannot
  // re-render the durable transcript; only LiveBubble subscribes to tokens.
  const liveBubble = useMemo(
    () => <LiveBubble stream={stream} active={streaming || busy} botName={bot?.name ?? "Keel"} />,
    [stream, streaming, busy, bot?.name],
  );

  const composer = (
    <Composer
      key={botId ?? "home"}
      botId={botId}
      busy={busy || streaming}
      onSend={send}
      ensureBot={ensureBot}
      onStop={stop}
      mode={mode}
      onModeChange={changeMode}
      modelLabel={bot?.model}
      providerLabel={bot?.provider}
      models={models}
      modelSaving={modelSaving}
      onModelChange={(m) => { void changeModel(m); }}
      error={sendError}
      onRetry={() => {
        const attempt = lastAttempt.current;
        if (!attempt) { setSendError(null); return; }
        void send(attempt.text, attempt.uploaded, attempt.botId);
      }}
      seed={seed}
      focusSignal={focusSignal}
      notify={notify}
    />
  );

  return (
    <div className={`${s.root} ${reduceMotion ? s.reduceMotion : ""}`}>
      {!botId ? (
        <div className={s.home}>
          <div className={s.homeInner}>
            <div className={s.homeMark}><KeelMark size={34} /></div>
            <h1 className={s.homeTitle}>Chat with Keel</h1>
            <p className={s.homeSub}>Choose your AI provider and model to start.</p>

            {metaLoading ? (
              <div className={s.warnBanner} role="status">
                <Icon name="refresh" size={15} className={s.loaderSpin} /> Loading providers…
              </div>
            ) : providers.length === 0 ? (
              <div className={s.errorBanner} role="alert">
                <Icon name="warning" size={15} />
                <span>No providers configured yet. Add a provider in Settings to start chatting.</span>
              </div>
            ) : (
              <div className={s.providerPicker}>
                <label className={s.pickLabel}>
                  <span>Provider</span>
                  <select
                    className={s.select}
                    value={selectedProviderId ?? ""}
                    onChange={(e) => {
                      setSelectedProviderId(e.target.value);
                      setSelectedModel(null);
                      if (e.target.value) void loadCatalog(e.target.value);
                    }}
                    aria-label="AI provider"
                  >
                    <option value="">Choose provider…</option>
                    {providers.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name ?? p.id} {p.configured ? "" : " · not configured"}
                      </option>
                    ))}
                  </select>
                </label>

                {selectedProviderId && (
                  <>
                    <label className={s.pickLabel}>
                      <span>Model</span>
                      <select
                        className={s.select}
                        value={selectedModel ?? ""}
                        disabled={catalogLoading || catalogModels.length === 0}
                        onChange={(e) => setSelectedModel(e.target.value || null)}
                        aria-label="Model"
                      >
                        <option value="">Choose model…</option>
                        {catalogModels.map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                      {catalogLoading && <span className={s.muted}>Loading models…</span>}
                      {catalogError && <span className={s.muted} style={{ color: "var(--danger)" }}>{catalogError}</span>}
                    </label>

                    <Button
                      variant="primary"
                      size="md"
                      disabled={!selectedModel || catalogLoading}
                      onClick={() => { void createTask(); }}
                    >
                      <Icon name="spark" size={15} /> Start new chat
                    </Button>
                  </>
                )}
              </div>
            )}

            <div className={s.quickHead}>Quick starts <span>— clicking puts the text in the composer</span></div>
            <div className={s.quickGrid}>
              {QUICK_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" className={s.quick} onClick={() => usePrompt(prompt)}>
                  <span className={s.quickIcon}><Icon name="spark" size={17} /></span>
                  <span><b>{prompt.split(" ").slice(0, 5).join(" ")}…</b><span className={s.quickFull}>{prompt}</span></span>
                </button>
              ))}
            </div>

            <div className={s.homeFoot}>
              <label className={s.pickLabel}>
                <span>Permission mode</span>
                <select
                  className={s.select}
                  value={mode}
                  onChange={(e) => changeMode(e.target.value as ComposerMode)}
                  aria-label="Permission mode"
                >
                  {COMPOSER_MODES.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              {bots.length > 0 && (
                <label className={s.pickLabel}>
                  <span>Continue an existing task</span>
                  <select
                    className={s.select}
                    value=""
                    onChange={(e) => { if (e.target.value) selectBot(e.target.value); }}
                    aria-label="Open an existing task"
                  >
                    <option value="">Choose…</option>
                    {bots.map((b) => <option key={b.id} value={b.id}>{b.name ?? b.id}</option>)}
                  </select>
                </label>
              )}
            </div>

            {providerReady === false && (
              <p className={s.warnBanner} role="status">
                <Icon name="warning" size={15} /> No configured provider was reported by the bridge. Add a provider key in Keel settings before starting a task.
              </p>
            )}
            {metaError && (
              <div className={s.errorBanner} role="alert">
                <Icon name="error" size={15} /> <span>{metaError}</span>
                <button type="button" onClick={() => void loadMeta()}>Recheck</button>
              </div>
            )}
            {offline && (
              <div className={s.warnBanner} role="status">
                <Icon name="warning" size={15} /> <span>You appear to be offline. Bridge status and live updates are unavailable until connectivity returns.</span>
                <button type="button" onClick={() => { void loadBots(); void loadMeta(); }}>Recheck</button>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className={s.session}>
          <header className={s.sessionHead}>
            <IconButton label="Back to Cowork home" onClick={() => selectBot(null)}><Icon name="panel" size={17} /></IconButton>
            {botsLoading ? <Skeleton width={130} /> : <h1>{bot?.name ?? "Cowork task"}</h1>}
            <Badge tone={TONE[status.state] || "neutral"} dot>{status.label}</Badge>
            {status.reason && <span className={s.statusReason}>{status.reason}</span>}
            <button
              type="button"
              className={s.searchBtn}
              onClick={openSearch}
              aria-label="Search conversation"
              aria-keyshortcuts="Control+F Meta+F"
              title="Search this conversation (Ctrl/⌘+F)"
            >
              <Icon name="search" size={15} /> <span>Search</span>
            </button>
            <span className={s.headSpacer} />
            {bots.length > 1 && (
              <select
                className={s.select}
                value={botId}
                onChange={(e) => selectBot(e.target.value)}
                aria-label="Switch task"
                title="Switch task"
              >
                {bots.map((b) => <option key={b.id} value={b.id}>{b.name ?? b.id}</option>)}
              </select>
            )}
            <IconButton label="New task" onClick={() => { void createTask(); }}><Icon name="plus" size={17} /></IconButton>
            <div className={s.exportGroup}>
              <a className={s.exportLink} href={bridge.exportUrl(botId)} download title="Export this conversation as Markdown">
                <Icon name="download" size={15} /> <span>Export</span>
              </a>
              {/* Honest gap: the bridge has a real export.md route but no route
                  that accepts this Markdown back. Import is hidden (not disabled)
                  until a route exists, per the surface fix plan G13. */}
            </div>
          </header>

          {searchOpen && (
            <SearchPanel
              query={query}
              matches={matches}
              active={activeMatch}
              focusTick={searchFocusTick}
              onQuery={(value) => { setQuery(value); setActiveMatch(-1); }}
              onClose={closeSearch}
              onStep={stepMatch}
              onSelect={selectMatch}
            />
          )}

          {(botsError || rowsError || streamError || metaError || providerReady === false || offline) && (
            <div className={s.banners}>
              {botsError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{botsError}</span><button type="button" onClick={() => void loadBots()}>Retry</button></div>}
              {rowsError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{rowsError}</span><button type="button" onClick={() => void loadRows(botId)}>Retry</button></div>}
              {streamError && <div className={s.errorBanner} role="alert"><Icon name="warning" size={15} /><span>{streamError}</span><button type="button" onClick={() => { setStreamError(null); setStreamKey((k) => k + 1); void loadRows(botId); }}>Reconnect</button></div>}
              {metaError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{metaError}</span><button type="button" onClick={() => void loadMeta()}>Recheck</button></div>}
              {providerReady === false && <div className={s.warnBanner} role="status"><Icon name="warning" size={15} /> No configured provider was reported — messages may be rejected until a provider key is added.</div>}
              {offline && <div className={s.warnBanner} role="status"><Icon name="warning" size={15} /><span>You appear to be offline. Live updates and bridge data may be stale.</span><button type="button" onClick={() => { void loadRows(botId); void loadBots(); }}>Recheck</button></div>}
            </div>
          )}

          <div
            className={s.scroll}
            ref={scrollRef}
            onScroll={onScroll}
            role="log"
            aria-label="Cowork conversation"
          >
            <WorkLog
              rows={visibleRows}
              status={status}
              activeSince={activeSince}
              expanded={workLogOpen}
              onToggle={() => setWorkLogOpen((v) => !v)}
            />

            {hiddenCount > 0 && (
              <div className={s.windowBar}>
                <button type="button" className={s.windowEarlier} onClick={showEarlier}>
                  <Icon name="chevron" size={13} /> Show earlier messages — {Math.min(WINDOW_PAGE, hiddenCount)} of {hiddenCount} hidden
                </button>
              </div>
            )}

            {rowsLoading && rows.length === 0 ? (
              <div className={s.skeletonWrap} aria-label="Loading conversation">
                <Skeleton width="60%" height={18} /><Skeleton width="85%" /><Skeleton width="72%" />
                <Skeleton width="45%" height={18} /><Skeleton width="90%" />
              </div>
            ) : rows.length === 0 && !streaming ? (
              <div className={s.sessionEmpty}>
                <Icon name="cowork" size={26} />
                <h2>No messages yet</h2>
                <p>Send a message below. Tool activity and results will appear here as the bridge reports them.</p>
              </div>
            ) : (
              <Timeline
                rows={visibleRows}
                botName={bot?.name ?? "Keel"}
                library={library}
                usage={usage}
                answeredAskIds={answeredAsks}
                onCopy={copy}
                onFork={fork}
                onRewind={rewind}
                onDecide={decide}
                onAnswer={answer}
                activeSeq={activeSeq}
                live={liveBubble}
              />
            )}

            {showJump && (
              <button type="button" className={s.jump} onClick={jumpToLatest}>
                <Icon name="chevron" size={14} /> Jump to latest
              </button>
            )}
          </div>

          <div className={s.composerWrap}>{composer}</div>
          <p className={s.footerNote}>
            {bot?.last_activity ? `Last activity ${formatTime(bot.last_activity) || textOf(bot.last_activity)}` : "Local-first — transcripts stay with your Keel bridge."}
          </p>
        </div>
      )}
    </div>
  );
}

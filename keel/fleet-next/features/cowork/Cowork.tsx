"use client";

// Cowork — a calm task workspace built entirely on the real bridge contract.
// No invented bots, rows, files, statuses or successful outcomes.

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Icon, IconButton, KeelMark } from "@/components/icons";
import { Badge, Button, Skeleton } from "@/components/ui";
import { bridge, errMessage, isBridgeUnavailable, subscribeEvents } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, Notice, Provider, Usage } from "@/lib/types";
import Composer, { type ComposerMode, type UploadedFile } from "./Composer";
import Timeline from "./Timeline";
import WorkLog from "./WorkLog";
import {
  deriveStatus, formatTime, textOf, toBots, toLibrary, toProjects, toRows,
  type LibraryView, type ProjectView, type RowView,
} from "./shared";
import s from "./cowork.module.css";

const QUICK_PROMPTS = [
  "Summarize the key points of a document in this workspace.",
  "Find where a feature is implemented and explain how it works.",
  "Draft a short project update from my notes.",
  "Review recent changes and list what needs attention.",
];

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
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [runStart, setRunStart] = useState<number | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const [sendError, setSendError] = useState<string | null>(null);

  const [mode, setMode] = useState<ComposerMode>("build");

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

  const botIdRef = useRef<string | null>(null);
  const rowsReq = useRef(0);
  const lastEventSeq = useRef(0);
  const lastAttempt = useRef<{ text: string; uploaded: UploadedFile[]; botId: string } | null>(null);
  const pendingDelta = useRef("");
  const flushRaf = useRef<number | null>(null);
  const reloadTimer = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [showJump, setShowJump] = useState(false);

  useEffect(() => { botIdRef.current = botId; }, [botId]);

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

  const selectBot = useCallback((id: string | null) => {
    setBotId(id);
    try {
      if (id) localStorage.setItem("keel-cowork-bot", id);
      else localStorage.removeItem("keel-cowork-bot");
    } catch { /* storage disabled */ }
    setSendError(null);
    setRowsError(null);
    setStreamError(null);
    lastEventSeq.current = 0;
    lastAttempt.current = null;
  }, []);

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

  useEffect(() => { void loadBots(); void loadMeta(); void loadUsage(); }, [loadBots, loadMeta, loadUsage]);

  useEffect(() => {
    if (!botId) { setRows([]); setBusy(false); setStreamText(""); return; }
    void loadRows(botId);
    setWorkLogOpen(true);
  }, [botId, loadRows]);

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
          if (!delta) return;
          pendingDelta.current += delta;
          setStreaming(true);
          if (flushRaf.current == null) {
            flushRaf.current = requestAnimationFrame(() => {
              flushRaf.current = null;
              const chunk = pendingDelta.current;
              pendingDelta.current = "";
              if (chunk) setStreamText((prev) => prev + chunk);
            });
          }
          return;
        }

        if (ev.kind === "error" || ev.type === "error") {
          setStreamError(textOf(ev.error ?? ev.message ?? "The event stream reported an error."));
          setStreaming(false);
          setBusy(false);
          return;
        }

        const durable = ["turn_end", "message", "step", "approval", "ask", "notice", "plan"];
        if (typeof ev.kind === "string" && durable.includes(ev.kind)) {
          if (ev.kind === "turn_end") {
            setBusy(false);
            setStreaming(false);
            setStreamText("");
            pendingDelta.current = "";
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
        setStreamError("The event stream was interrupted. Reconnect to resume live updates.");
        setStreaming(false);
      },
    );
    return () => {
      disposed = true;
      unsubscribe();
      if (flushRaf.current != null) cancelAnimationFrame(flushRaf.current);
      if (reloadTimer.current != null) window.clearTimeout(reloadTimer.current);
      flushRaf.current = null; reloadTimer.current = null;
    };
  }, [streamKey, loadRows, loadUsage, loadMeta]);

  /* --------------------------- scroll behaviour ------------------------- */

  useLayoutEffect(() => {
    if (!atBottom.current) return;
    const el = scrollRef.current;
    if (!el) return;
    const raf = requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    return () => cancelAnimationFrame(raf);
  }, [rows, streamText]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    atBottom.current = near;
    setShowJump(!near);
  }, []);

  const jumpToLatest = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    atBottom.current = true; setShowJump(false);
  }, [reduceMotion]);

  /* --------------------------- actions ---------------------------------- */

  const createTask = useCallback(async (): Promise<Bot | null> => {
    try {
      const created = unwrapBot(await bridge.createBot({ name: "Cowork task", role: "General assistant", engine: "provider" }));
      if (!created?.id) throw new Error("The bridge did not return a new task id.");
      setBots((prev) => [created, ...prev]);
      selectBot(created.id);
      notify("New Cowork task created.", "success");
      return created;
    } catch (err) {
      notify(`Could not create a task: ${errMessage(err)}`, "error");
      return null;
    }
  }, [notify, selectBot]);

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
      setStreamText("");
      pendingDelta.current = "";
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
  }, [loadRows, mode, notify]);

  const stop = useCallback(() => {
    const id = botIdRef.current;
    if (!id) return;
    void (async () => {
      try {
        await bridge.cancel(id);
        setBusy(false); setStreaming(false);
        notify("Stop requested — the turn ends at the next model boundary.", "info");
        await loadRows(id);
      } catch (err) {
        notify(`Stop failed: ${errMessage(err)}`, "error");
      }
    })();
  }, [loadRows, notify]);

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
      await loadRows(id);
      notify("Answer sent.", "success");
      return true;
    } catch (err) {
      notify(`Answer failed: ${errMessage(err)}`, "error");
      return false;
    }
  }, [loadRows, notify]);

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
  const status = deriveStatus(bot, rows, busy || streaming);
  const providerReady = providers.length === 0 ? null : providers.some((p) => p.configured || p.connected);
  const workspace = projects[0];
  const activeSince = status.state === "running" ? runStart : null;

  const composer = (
    <Composer
      botId={botId}
      busy={busy || streaming}
      onSend={send}
      ensureBot={ensureBot}
      onStop={stop}
      mode={mode}
      onModeChange={changeMode}
      modelLabel={bot?.model}
      providerLabel={bot?.provider}
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
            <h1 className={s.homeTitle}>A calm place to <em>get work done.</em></h1>
            <p className={s.homeSub}>Describe a task and Keel will work in your local workspace — visibly, step by step.</p>

            <div className={s.contextRow}>
              <Icon name="folder" size={15} />
              {metaLoading ? <Skeleton width={190} /> : workspace
                ? <span>Workspace: <b>{workspace.name ?? workspace.path ?? workspace.id}</b>{workspace.path && workspace.name ? ` — ${workspace.path}` : ""}{workspace.trusted ? " · trusted" : ""}</span>
                : <span>No workspace selected — Keel uses your local folders when you grant access.</span>}
            </div>

            <div className={s.homeComposer}>{composer}</div>

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
              <Button variant="secondary" size="sm" onClick={() => { void createTask(); }}><Icon name="plus" size={14} /> New task</Button>
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
          </div>
        </div>
      ) : (
        <div className={s.session}>
          <header className={s.sessionHead}>
            <IconButton label="Back to Cowork home" onClick={() => selectBot(null)}><Icon name="panel" size={17} /></IconButton>
            {botsLoading ? <Skeleton width={130} /> : <h1>{bot?.name ?? "Cowork task"}</h1>}
            <Badge tone={TONE[status.state] || "neutral"} dot>{status.label}</Badge>
            {status.reason && <span className={s.statusReason}>{status.reason}</span>}
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
            <a className={s.exportLink} href={bridge.exportUrl(botId)} download title="Export this conversation as Markdown">
              <Icon name="download" size={15} /> <span>Export</span>
            </a>
          </header>

          {(botsError || rowsError || streamError || metaError || providerReady === false) && (
            <div className={s.banners}>
              {botsError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{botsError}</span><button type="button" onClick={() => void loadBots()}>Retry</button></div>}
              {rowsError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{rowsError}</span><button type="button" onClick={() => void loadRows(botId)}>Retry</button></div>}
              {streamError && <div className={s.errorBanner} role="alert"><Icon name="warning" size={15} /><span>{streamError}</span><button type="button" onClick={() => { setStreamError(null); setStreamKey((k) => k + 1); void loadRows(botId); }}>Reconnect</button></div>}
              {metaError && <div className={s.errorBanner} role="alert"><Icon name="error" size={15} /><span>{metaError}</span><button type="button" onClick={() => void loadMeta()}>Recheck</button></div>}
              {providerReady === false && <div className={s.warnBanner} role="status"><Icon name="warning" size={15} /> No configured provider was reported — messages may be rejected until a provider key is added.</div>}
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
              rows={rows}
              status={status}
              activeSince={activeSince}
              expanded={workLogOpen}
              onToggle={() => setWorkLogOpen((v) => !v)}
            />

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
                rows={rows}
                streamText={streamText}
                streaming={streaming || busy}
                botName={bot?.name ?? "Keel"}
                status={status}
                library={library}
                usage={usage}
                onCopy={copy}
                onFork={fork}
                onRewind={rewind}
                onDecide={decide}
                onAnswer={answer}
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

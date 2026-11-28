"use client";

// Duet Live Pair: one workspace, two drivers. Hand-off and take-over use only
// real bridge routes: POST projects/:id/chat (project session), POST
// bots/:id/messages (turn) and POST bots/:id/cancel (take-over). The bridge has
// no cursor position route and no completion route, so neither is invented.

import React, { useCallback, useEffect, useState } from "react";
import { bridge, errMessage } from "@/lib/api";
import { wrapped } from "@/features/fleet/support";
import type { Bot, BotRow, Notice } from "@/lib/types";
import { Badge, Button, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { MISSING_COMPLETION_ENDPOINT, unwrapBot } from "./pairSupport";
import s from "./duet.module.css";

type Driver = "you" | "agent";

interface Props {
  projectId: string | null;
  notify?: (message: string, kind?: Notice["kind"]) => void;
  onReviewPair: () => void;
}

export default function LivePairView({ projectId, notify, onReviewPair }: Props) {
  const [driver, setDriver] = useState<Driver>("you");
  const [follow, setFollow] = useState(true);
  const [agentBot, setAgentBot] = useState<Bot | null>(null);
  const [lastSeq, setLastSeq] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /* A project switch drops the old session binding; no stale driver is kept. */
  useEffect(() => {
    setDriver("you");
    setAgentBot(null);
    setNotice(null);
  }, [projectId]);

  /* The "cursor" is a local follow view over real transcript rows. The bridge
   * reports no editor cursor position, so no position is drawn or guessed. */
  useEffect(() => {
    if (!agentBot) { setLastSeq(null); return; }
    let alive = true;
    const read = () => {
      void bridge.botRows(agentBot.id).then((raw) => {
        if (!alive) return;
        const rows = wrapped<BotRow>(raw, "rows");
        const tail = rows[rows.length - 1];
        setLastSeq(typeof tail?.seq === "number" ? tail.seq : null);
      }).catch(() => { if (alive) setLastSeq(null); });
    };
    read();
    const timer = window.setInterval(read, 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [agentBot]);

  const handOff = useCallback(async () => {
    if (!projectId) { setNotice("Select a project before handing off the workspace."); return; }
    setBusy(true); setNotice(null);
    try {
      const bot = unwrapBot(await bridge.startChat(projectId));
      const result = await bridge.sendMessage(bot.id, {
        content: "Hand-off: you now drive this workspace. Continue the current task in the trusted project.",
        mode: "build",
      }) as { queued?: boolean; seq?: number } | null;
      setAgentBot(bot);
      setDriver("agent");
      setNotice(result?.queued === false
        ? `Project chat ${bot.id} is busy (seq ${result.seq ?? "unknown"}); the driver switched to the agent but no new turn was queued.`
        : `Handed off to project chat ${bot.name || bot.id} via POST /api/bridge/bots/${bot.id}/messages${result?.seq ? ` (row seq ${result.seq})` : ""}.`);
      notify?.(`Agent drives: ${bot.name || bot.id}.`, "info");
    } catch (err) {
      setNotice(`Hand-off failed: ${errMessage(err)}`);
      notify?.(`Hand-off failed: ${errMessage(err)}`, "error");
    } finally { setBusy(false); }
  }, [projectId, notify]);

  const takeOver = useCallback(async () => {
    if (driver === "you") return;
    setBusy(true); setNotice(null);
    try {
      if (agentBot) {
        const result = await bridge.cancel(agentBot.id) as { cancelled?: boolean } | null;
        setNotice(result?.cancelled
          ? `You drive again. The active turn in ${agentBot.id} was cancelled via POST /api/bridge/bots/${agentBot.id}/cancel.`
          : `You drive again. No active turn was cancelled for ${agentBot.id}.`);
      } else {
        setNotice("You drive again. No agent session is bound in this view, so no cancel call was made.");
      }
      setDriver("you");
      notify?.("You drive again.", "info");
    } catch (err) {
      setNotice(`Take-over failed: ${errMessage(err)}`);
    } finally { setBusy(false); }
  }, [driver, agentBot, notify]);

  /* Esc takes back control while the agent drives. Dialogs capture Escape
   * before this window listener, and text controls keep their own Esc. */
  useEffect(() => {
    if (driver !== "agent") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.repeat) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      e.preventDefault();
      void takeOver();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [driver, takeOver]);

  return (
    <div className={s.pair} data-live-root="true" data-live-driver={driver} data-live-follow={String(follow)}>
      <header className={s.panelHead}>
        <div>
          <h3>Live pair</h3>
          <p className={s.muted}>One workspace, explicit hand-off — no inferred cursor or completion</p>
        </div>
        <Badge tone={driver === "agent" ? "info" : "success"} dot>
          {driver === "agent" ? "Agent drives" : "You drive"}
        </Badge>
      </header>

      <section className={s.pairState} data-live-section="driver">
        <h4>Who drives</h4>
        <div className={s.pairActionRow}>
          <Button size="sm" variant={driver === "you" ? "primary" : "secondary"}
            aria-pressed={driver === "you"} disabled={driver === "you" || busy}
            onClick={() => void takeOver()}>
            <Icon name="user" size={14} /> You drive
          </Button>
          <Button size="sm" variant={driver === "agent" ? "primary" : "secondary"}
            aria-pressed={driver === "agent"} disabled={driver === "agent" || busy}
            onClick={() => void handOff()}>
            <Icon name="duet" size={14} /> Agent drives
          </Button>
          <Button size="sm" variant="ghost" aria-pressed={follow}
            onClick={() => setFollow((v) => !v)}>
            <Icon name="info" size={14} /> Follow agent cursor
          </Button>
        </div>
        <div className={s.liveStatus}>
          <span className={`${s.cursorMark} ${driver === "agent" && follow ? s.cursorMarkOn : ""}`}
            role="img" aria-label={follow ? "Following agent" : "Not following agent"} />
          <span>Follow state: <strong>{follow ? "following" : "not following"}</strong></span>
          <span data-live-cursor="true">
            Agent cursor: {driver === "agent" && follow && lastSeq !== null
              ? `viewing real transcript row ${lastSeq}`
              : "not reported by bridge"}
          </span>
        </div>
        {driver === "agent" && <p className={s.hint}>Press <kbd>Esc</kbd> to take over immediately.</p>}
        {notice && <p className={s.note} role="status" data-live-notice="true">{notice}</p>}
        {!projectId && <EmptyState icon={<Icon name="folder" size={22} />} title="No active project"
          description="Select a project in the Duet tab bar before handing the workspace to an agent." />}
      </section>

      <section className={s.pairState} data-live-section="ghost">
        <h4>Ghost text</h4>
        <p className={s.hint} data-ghost="unavailable">
          Off by default and kept hidden: this bridge exposes no completion endpoint
          (<code className={s.mono}>{MISSING_COMPLETION_ENDPOINT}</code>). Keel will not guess a completion or
          display a control that cannot return real data. Use the review pair to get real reviewer findings instead.
        </p>
        <Button size="sm" variant="ghost" onClick={onReviewPair}>
          <Icon name="duet" size={14} /> Switch to review pair
        </Button>
      </section>

      <footer className={s.pairFoot}>
        Sources: <code>POST /api/bridge/projects/:id/chat</code>,
        {" "}<code>POST /api/bridge/bots/:id/messages</code>, <code>POST /api/bridge/bots/:id/cancel</code> and
        {" "}<code>GET /api/bridge/bots/:id/rows</code>. No cursor-position or completion route exists in this bridge.
      </footer>
    </div>
  );
}

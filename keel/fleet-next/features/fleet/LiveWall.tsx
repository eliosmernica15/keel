"use client";

// Live agent wall. Every card is derived from the agent's persisted rows and
// the bridge's SSE frames via `deriveActivity`. The bridge has no bots.state
// column, so an agent with no reported activity is shown as "not reported" —
// never as busy, idle-by-guess or fabricated activity.

import React from "react";
import { Button, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { errMessage } from "@/lib/api";
import type { Bot, FleetEvent } from "@/lib/types";
import s from "./fleet.module.css";
import { ActivityBadge, ActivityDot, Avatar, StreamNotice } from "./Bits";
import {
  deriveActivity, fmtDate, fmtElapsed, text, useNow,
  type BotRowsView, type Resource,
} from "./support";

export default function LiveWall({ bots, rowsResource, events, streamError, onRetryStream, onOpenBot }: {
  bots: Bot[];
  rowsResource: Resource<BotRowsView[]>;
  events: FleetEvent[];
  streamError: boolean;
  onRetryStream: () => void;
  onOpenBot: (id: string) => void;
}) {
  const now = useNow();

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Live agent wall</h3>
          <p className={s.panelHint}>State is derived only from reported rows and SSE frames. An agent with no reported activity stays “not reported”.</p>
        </div>
        <Button size="sm" variant="secondary" onClick={rowsResource.reload}><Icon name="refresh" size={14} /> Refresh rows</Button>
      </div>

      <StreamNotice streamError={streamError} onRetry={onRetryStream} />
      {rowsResource.loading && rowsResource.data === null && (
        <div aria-busy="true" aria-label="Loading agent rows">{Array.from({ length: 3 }, (_, i) => <div key={i} className={s.skeletonLine} />)}</div>
      )}
      {rowsResource.error !== null && (
        <div className={s.banner} role="status">
          <Icon name="warning" size={17} />
          <span className={s.bannerText}>
            <strong>Some agent transcripts could not be loaded.</strong>
            <small>{errMessage(rowsResource.error)} — no state is guessed for those agents.</small>
          </span>
          <Button variant="secondary" onClick={rowsResource.reload}><Icon name="refresh" size={15} /> Retry</Button>
        </div>
      )}

      {bots.length === 0 ? (
        <div role="status">
          <EmptyState icon={<Icon name="agents" size={26} />} title="No agents reported"
            description="The bridge reported no agents, so there is no wall to render."
            action={<Button size="sm" variant="secondary" onClick={rowsResource.reload}>Reload agent rows</Button>} />
        </div>
      ) : (
        <div className={s.wallGrid}>
          {bots.map((bot) => {
            const rows = rowsResource.data?.find((v) => v.botId === bot.id)?.rows ?? [];
            const mine = events.filter((e) => !e.bot_id || e.bot_id === bot.id);
            const activity = deriveActivity(rows, mine, now, text(bot.engine));
            return (
              <article className={s.wallCard} key={bot.id} aria-label={`Agent ${bot.name || bot.id} activity`}>
                <div className={s.agentTop}>
                  <Avatar bot={bot} />
                  <div className={s.grow}>
                    <div className={s.agentName}>{bot.name || bot.id}</div>
                    <div className={s.agentRole}>{text(bot.role, "agent")}</div>
                  </div>
                  <ActivityDot state={activity.state} />
                </div>
                <div className={s.activityPhrase}>{activity.phrase}</div>
                {activity.detail && <div className={s.activityDetail}>{activity.detail}</div>}
                <div className={s.row}>
                  <ActivityBadge state={activity.state} />
                  {activity.elapsedMs !== null && <span className={s.activityElapsed}>{fmtElapsed(activity.elapsedMs)}</span>}
                </div>
                <div className={s.itemMeta}>last activity {fmtDate(activity.lastAt)}</div>
                <button className={s.linkBtn} onClick={() => onOpenBot(bot.id)}>Open agent</button>
              </article>
            );
          })}
        </div>
      )}
      <p className={s.hintNote}>
        {events.length} live SSE frame{events.length === 1 ? "" : "s"} received in this session. Frames carry real row payloads; keep-alives are ignored.
      </p>
    </div>
  );
}

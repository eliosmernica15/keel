"use client";

// Reporting hierarchy is NOT available from the bridge: the bots table has no
// parent_id / child-id column (keel/src/keel/fleet/db.py) and no route exposes
// one. This view therefore states that plainly and only draws the flat links
// that the runtime actually writes into transcript rows.

import React, { useMemo } from "react";
import { Badge, Button, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { errMessage } from "@/lib/api";
import type { Bot } from "@/lib/types";
import s from "./fleet.module.css";
import { Avatar, ResourceNotice } from "./Bits";
import {
  delegationEdges, fmtDate,
  type BotRowsView, type Resource,
} from "./support";

export default function OrgChart({ bots, rowsResource, onOpenBot }: {
  bots: Bot[];
  rowsResource: Resource<BotRowsView[]>;
  onOpenBot: (id: string) => void;
}) {
  const edges = useMemo(
    () => delegationEdges(bots, rowsResource.data ?? []),
    [bots, rowsResource.data],
  );
  const botById = useMemo(() => new Map(bots.map((b) => [b.id, b])), [bots]);

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Agent organization</h3>
          <p className={s.panelHint}>Only links written into real transcript rows are shown. No reporting tree is invented.</p>
        </div>
        <Button size="sm" variant="secondary" onClick={rowsResource.reload}><Icon name="refresh" size={14} /> Refresh rows</Button>
      </div>

      <div className={s.unavailable} role="status">
        <Icon name="info" size={18} />
        <div className={s.grow}>
          <strong>Organization hierarchy is unavailable from the bridge.</strong>
          <p className={s.hintNote}>
            The bot schema has no <code>parent_id</code> / child-id column and no hierarchy route exists.
            A nested org chart would be fabricated, so it is not rendered. The runtime only records
            delegation as row fields (<code>delegated</code> on a parent&apos;s <code>send_to_bot</code> step,
            <code> delegated_from</code> on a child&apos;s user row); those real links are listed below.
          </p>
        </div>
      </div>

      <ResourceNotice resource={rowsResource} emptyTitle="No transcripts reported"
        emptyDescription="The bridge reported no agent transcripts, so no delegation can be derived.">
        {() => edges.length === 0 ? (
          <EmptyState
            icon={<Icon name="fleet" size={26} />}
            title="No delegation reported by the bridge"
            description="No send_to_bot delegation fields or delegated_from parent fields were found in the reported transcripts."
          />
        ) : (
          <div className={s.panel}>
            <div className={s.panelHead}>
              <h4 className={s.panelTitle}>Reported delegation links</h4>
              <Badge tone="neutral">{edges.length} reported</Badge>
            </div>
            <p className={s.hintNote}>Flat, row-derived edges — this is not a hierarchy tree.</p>
            <div className={s.edgeList}>
              {edges.map((edge) => {
                const from = botById.get(edge.fromId ?? "");
                const to = botById.get(edge.toId ?? "");
                return (
                  <div className={s.edge} key={edge.key} aria-label={`${edge.fromName} to ${edge.toName}`}>
                    <Badge tone={edge.direction === "out" ? "info" : "accent"} dot>
                      {edge.direction === "out" ? (edge.ok ? "delegated" : "delegation failed") : "received from parent"}
                    </Badge>
                    <div className={s.grow}>
                      <div className={s.line}>
                        {from ? <Avatar bot={from} small /> : null}
                        <span className={s.lineValue}>{edge.fromName}</span>
                        <Icon name="chevron" size={14} />
                        {to ? <Avatar bot={to} small /> : null}
                        <span className={s.lineValue}>{edge.toName}</span>
                      </div>
                      <div className={s.itemMeta}>
                        {edge.taskId ? `task ${edge.taskId} · ` : ""}
                        {edge.ts ? `reported ${fmtDate(edge.ts)}` : "timestamp not reported"}
                      </div>
                    </div>
                    <div className={s.actions}>
                      {edge.fromId && botById.has(edge.fromId) && (
                        <button className={s.linkBtn} onClick={() => onOpenBot(edge.fromId as string)}>Open source agent</button>
                      )}
                      {edge.toId && botById.has(edge.toId) && (
                        <button className={s.linkBtn} onClick={() => onOpenBot(edge.toId as string)}>Open target agent</button>
                      )}
                      {!edge.toId && <span className={s.hintNote}>child session not in fleet roster</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </ResourceNotice>
      {bots.length === 0 && <p className={s.hintNote}>No agents are reported by the bridge.</p>}
      {rowsResource.error !== null && (
        <div className={s.errorText}>Could not refresh transcripts: {errMessage(rowsResource.error)}</div>
      )}
    </div>
  );
}

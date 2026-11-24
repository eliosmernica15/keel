"use client";

// Cost per agent. A dollar figure is rendered ONLY when a real `cost_usd`
// field is present in bridge-reported `usage` rows. The current bridge emits
// token counts with `cost_basis: "unknown (no provider-reported cost)"` and no
// per-agent cost route, so the honest unavailable state is the normal case.
// No token-to-dollar conversion, estimate or inference happens here.

import React from "react";
import { Badge, Button } from "@/components/ui";
import { Icon } from "@/components/icons";
import { errMessage } from "@/lib/api";
import type { Bot } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import { agentUsage, type AgentUsage, type BotRowsView, type Resource } from "./support";

export default function CostPanel({ bots, rowsResource }: {
  bots: Bot[];
  rowsResource: Resource<BotRowsView[]>;
}) {
  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Cost per agent</h3>
          <p className={s.panelHint}>Only bridge-reported cost is shown. Token counts are not a cost estimate.</p>
        </div>
        <Button size="sm" variant="secondary" onClick={rowsResource.reload}><Icon name="refresh" size={14} /> Refresh rows</Button>
      </div>

      <ResourceNotice resource={rowsResource} emptyTitle="No usage rows reported"
        emptyDescription="The bridge reported no agent transcripts, so no usage or cost data is available.">
        {(views) => <CostContent bots={bots} rows={views} />}
      </ResourceNotice>
      {rowsResource.error !== null && (
        <div className={s.errorText}>Could not refresh usage rows: {errMessage(rowsResource.error)}</div>
      )}
    </div>
  );
}

function CostContent({ bots, rows }: { bots: Bot[]; rows: BotRowsView[] }) {
  const usage = agentUsage(bots, rows);
  const withCost = usage
    .filter((u) => u.costUsd !== null)
    .sort((a, b) => (b.costUsd ?? 0) - (a.costUsd ?? 0));
  const withTokens = usage.filter((u) => u.records > 0);

  return (
    <div className={s.stack}>
      {withCost.length === 0 ? (
        <div className={s.unavailable} role="status">
          <Icon name="info" size={18} />
          <div className={s.grow}>
            <strong>Not reported by bridge</strong>
            <p className={s.hintNote}>
              No provider-reported cost is available per agent. The bridge&apos;s <code>usage</code> rows
              carry token counts with <code>cost_basis: &quot;unknown (no provider-reported cost)&quot;</code>,
              and <code>GET /api/fleet/usage</code> returns global token totals only — there is no
              per-agent cost route. No cost is estimated, converted or inferred here.
            </p>
          </div>
        </div>
      ) : (
        <div className={s.panel}>
          <div className={s.panelHead}>
            <h4 className={s.panelTitle}>Reported cost by agent</h4>
            <Badge tone="success">{withCost.length} reported</Badge>
          </div>
          <p className={s.hintNote}>Ranked from the bridge&apos;s own <code>cost_usd</code> field; no derived values.</p>
          <table className={s.costTable}>
            <thead><tr><th scope="col">Agent</th><th scope="col">Reported cost (USD)</th><th scope="col">Basis</th></tr></thead>
            <tbody>
              {withCost.map((u) => (
                <tr key={u.botId}>
                  <th scope="row">{u.name}</th>
                  <td>{String(u.costUsd)}</td>
                  <td>{u.costBasis || "not reported"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {withTokens.length > 0 && (
        <div className={s.panel}>
          <div className={s.panelHead}>
            <h4 className={s.panelTitle}>Reported token usage (not cost)</h4>
            <Badge tone="neutral">{withTokens.reduce((n, u) => n + u.records, 0)} usage rows</Badge>
          </div>
          <table className={s.costTable}>
            <thead><tr><th scope="col">Agent</th><th scope="col">Input tokens</th><th scope="col">Output tokens</th></tr></thead>
            <tbody>
              {withTokens.map((u: AgentUsage) => (
                <tr key={u.botId}>
                  <th scope="row">{u.name}</th>
                  <td>{String(u.inputTokens)}</td>
                  <td>{String(u.outputTokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {withTokens.length === 0 && withCost.length === 0 && (
        <p className={s.hintNote}>No agent reported any usage rows. Nothing is shown as a cost.</p>
      )}
    </div>
  );
}

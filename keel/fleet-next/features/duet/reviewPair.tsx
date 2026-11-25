"use client";

// Phase 5 — Duet Review Pair: an explicit builder / independent reviewer pair.
//
// Honesty rules, enforced here rather than assumed:
//  - Identity, model and prompt/notes come only from real `bots` rows.
//  - Review requests, findings/comments and accept/revision state come only
//    from real `bots/:id/rows` message rows of those two agents.
//  - The bridge has NO dedicated reviewer-role, review-request or review-status
//    field. A bot is treated as an independent reviewer only when its
//    operator-supplied `role` text says so, and it must be a different bot from
//    the builder. Otherwise an honest "not configured by this bridge" state is
//    shown; no reviewer, comment or status is invented.
//  - The reviewer is comment-only. This pane never renders an edit, save,
//    write, trust, apply or execute control for it (or for anyone).

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { asArray, BridgeError } from "@/features/code/workspace";
import { Badge, EmptyState, IconButton, Spinner } from "@/components/ui";
import { Icon } from "@/components/icons";
import s from "./duet.module.css";

interface PairBot {
  id: string;
  name: string;
  role: string;
  provider?: string;
  model?: string;
  notes?: string;
}

interface PairRow {
  seq: number;
  kind: string;
  role: string;
  content: string;
  createdAt?: string;
}

type ReviewStatus = "accepted" | "revision requested" | "not reported";

interface PairState {
  bots: PairBot[];
  builder: PairBot | null;
  reviewer: PairBot | null;
  builderRows: PairRow[];
  reviewerRows: PairRow[];
}

const REVIEWER_ROLE = /review|critic|audit|\bqa\b|independent/i;
const BUILDER_ROLE = /builder|implement|develop|engineer|coder|author/i;
const REVIEW_REQUEST = /\breview\b/i;
const ACCEPT = /\b(accept|accepted|approve|approved|lgtm|looks good|no issues|no changes needed)\b/i;
const REVISION = /\b(revision|revisions|request changes|changes requested|reject|rejected|blocked|needs work|must fix)\b/i;

function normalizeBot(value: unknown): PairBot | null {
  if (!value || typeof value !== "object") return null;
  const o = value as Record<string, unknown>;
  const id = String(o.id ?? "").trim();
  if (!id) return null;
  return {
    id,
    name: typeof o.name === "string" && o.name.trim() ? o.name.trim() : id,
    role: typeof o.role === "string" ? o.role.trim() : "",
    provider: typeof o.provider === "string" && o.provider.trim() ? o.provider.trim() : undefined,
    model: typeof o.model === "string" && o.model.trim() ? o.model.trim() : undefined,
    notes: typeof o.notes === "string" && o.notes.trim() ? o.notes.trim() : undefined,
  };
}

function normalizeRows(raw: unknown): PairRow[] {
  return asArray<Record<string, unknown>>(raw, ["rows"]).map((r, i) => {
    const body = r.body && typeof r.body === "object" ? r.body as Record<string, unknown> : {};
    const content = typeof body.content === "string" ? body.content
      : typeof body.text === "string" ? body.text : "";
    return {
      seq: typeof r.seq === "number" ? r.seq : i + 1,
      kind: String(r.kind ?? ""),
      role: String(body.role ?? r.role ?? ""),
      content,
      createdAt: typeof r.created_at === "string" ? r.created_at : undefined,
    };
  });
}

/** A reviewer must be explicitly labelled as one AND be a different bot. */
export function classifyPair(bots: PairBot[]): { builder: PairBot | null; reviewer: PairBot | null } {
  const reviewer = bots.find((b) => REVIEWER_ROLE.test(b.role)) ?? null;
  const builder = bots.find((b) => b.id !== reviewer?.id && BUILDER_ROLE.test(b.role)) ?? null;
  return { builder, reviewer: reviewer && reviewer.id !== builder?.id ? reviewer : null };
}

/** Derive review state from message rows only. `status` is explicitly marked in
 *  the UI as inferred from the reviewer's last real message, never a bridge
 *  field, so an inference can never be mistaken for a reported fact. */
export function deriveReviewState(builderRows: PairRow[], reviewerRows: PairRow[]) {
  const requests = builderRows.filter(
    (r) => r.kind === "message" && r.role === "user" && REVIEW_REQUEST.test(r.content),
  );
  const comments = reviewerRows.filter(
    (r) => r.kind === "message" && r.role !== "user" && r.content.trim(),
  );
  const lastComment = comments[comments.length - 1];
  const text = lastComment?.content ?? "";
  const status: ReviewStatus = ACCEPT.test(text) ? "accepted"
    : REVISION.test(text) ? "revision requested" : "not reported";
  return {
    request: requests[requests.length - 1] ?? null,
    requests,
    comments,
    status,
    statusFromSeq: lastComment?.seq ?? null,
  };
}

function Fact({ label, value, title }: { label: string; value?: string; title?: string }) {
  return (
    <div className={s.factPair}>
      <dt>{label}</dt>
      <dd>{value
        ? <span className={s.mono} title={title ?? value}>{value}</span>
        : <span className={s.notReported}>not reported</span>}</dd>
    </div>
  );
}

function AgentCard({ bot, role, reviewer }: { bot: PairBot | null; role: "builder" | "reviewer"; reviewer?: boolean }) {
  if (!bot) {
    return (
      <section className={s.pairCard} data-pair-role={role} data-pair-state="unconfigured">
        <div className={s.pairCardHead}>
          <h4>{reviewer ? "Independent reviewer" : "Builder"}</h4>
          <Badge tone="warning">Not configured</Badge>
        </div>
        <EmptyState
          icon={<Icon name={reviewer ? "shield" : "user"} size={22} />}
          title={reviewer
            ? "Independent reviewer not configured by this bridge"
            : "Builder not configured by this bridge"}
          description={reviewer
            ? "The bridge reports bots, but none carries a reviewer role and is distinct from the builder. Keel will not invent a reviewer or grant any agent edit or execute rights here."
            : "The bridge reports bots, but none carries a builder role. Keel will not guess which agent performs the work."}
        />
      </section>
    );
  }
  return (
    <section className={s.pairCard} data-pair-role={role} data-pair-state="configured">
      <div className={s.pairCardHead}>
        <h4>{reviewer ? "Independent reviewer" : "Builder"}</h4>
        <Badge tone={reviewer ? "info" : "accent"} dot>{reviewer ? "Comment-only" : "Builds"}</Badge>
      </div>
      <dl className={s.pairFacts}>
        <Fact label="Name" value={bot.name} />
        <Fact label="Agent id" value={bot.id} />
        <Fact label="Role (as reported)" value={bot.role || undefined} title={bot.role || undefined} />
        <Fact label="Provider" value={bot.provider} />
        <Fact label="Model" value={bot.model} />
        <Fact label="Prompt / notes" value={bot.notes} title={bot.notes || undefined} />
      </dl>
      <p className={s.pairCardNote}>
        {reviewer
          ? "Comment-only: this agent cannot edit files, write files or run tools in Keel. Only its real transcript rows are shown below."
          : "The builder performs the work in the trusted project panes. This panel never edits or executes anything on its behalf."}
      </p>
    </section>
  );
}

export default function ReviewPairView() {
  const [state, setState] = useState<PairState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    // A delayed bots/rows read from an older refresh must not replace newer
    // identity or review state.
    const id = ++requestId.current;
    const current = () => id === requestId.current;
    setLoading(true);
    setError(null);
    setBridgeDown(false);
    try {
      const raw = await bridge.listBots();
      const bots = asArray<Record<string, unknown>>(raw, ["bots"])
        .map(normalizeBot)
        .filter((b): b is PairBot => b !== null);
      const { builder, reviewer } = classifyPair(bots);
      const [builderRaw, reviewerRaw] = await Promise.all([
        builder ? bridge.botRows(builder.id) : Promise.resolve([]),
        reviewer ? bridge.botRows(reviewer.id) : Promise.resolve([]),
      ]);
      if (!current()) return;
      setState({
        bots, builder, reviewer,
        builderRows: normalizeRows(builderRaw),
        reviewerRows: normalizeRows(reviewerRaw),
      });
    } catch (err) {
      if (!current()) return;
      setError(errMessage(err));
      setBridgeDown(isBridgeUnavailable(err));
      setState(null);
    } finally {
      if (current()) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load, tick]);

  const review = useMemo(
    () => deriveReviewState(state?.builderRows ?? [], state?.reviewerRows ?? []),
    [state?.builderRows, state?.reviewerRows],
  );

  if (loading) return (
    <div className={s.pair}>
      <div className={s.centered}><Spinner label="Reading review pair" /><p>Reading the two agents from the bridge…</p></div>
    </div>
  );
  if (bridgeDown) return (
    <div className={s.pair}>
      <BridgeError message={error ?? "The bridge is unavailable."} onRetry={() => setTick((t) => t + 1)} />
    </div>
  );
  if (error || !state) return (
    <div className={s.pair}>
      <EmptyState
        icon={<Icon name="error" size={26} />}
        title="Review pair could not be read"
        description={error ?? "The bridge returned no bot data."}
        action={<button type="button" onClick={() => setTick((t) => t + 1)}>Retry</button>}
      />
    </div>
  );

  const statusTone = review.status === "accepted" ? "success"
    : review.status === "revision requested" ? "warning" : "neutral";

  return (
    <div className={s.pair} data-pair-root="true">
      <header className={s.panelHead}>
        <div>
          <h3>Review pair</h3>
          <p className={s.muted}>Builder and independent reviewer, from real bridge bots and rows</p>
        </div>
        <div className={s.rowGap}>
          <Badge tone="info">Read-only review</Badge>
          <IconButton label="Refresh review pair" onClick={() => setTick((t) => t + 1)}>
            <Icon name="refresh" size={15} />
          </IconButton>
        </div>
      </header>

      <div className={s.pairCards}>
        <AgentCard bot={state.builder} role="builder" />
        <AgentCard bot={state.reviewer} role="reviewer" reviewer />
      </div>

      <section className={s.pairState} data-pair-section="state">
        <h4>Review state</h4>
        {!state.reviewer ? (
          <p className={s.hint}>
            Review requests, findings and accept/revision status are unavailable: this bridge does not
            report an independent reviewer. No state is inferred from a reviewer that does not exist.
          </p>
        ) : (
          <>
            <dl className={s.pairFacts}>
              <Fact label="Review request"
                value={review.request?.content}
                title={review.request ? `Builder message row seq ${review.request.seq}` : undefined} />
              <Fact label="Accept / revision"
                value={review.status === "not reported" ? undefined : review.status}
                title={review.statusFromSeq ? `Inferred from reviewer message row seq ${review.statusFromSeq}` : undefined} />
            </dl>
            <p className={s.hint}>
              {review.status === "not reported"
                ? "The bridge has no review-status field. The reviewer's real messages contain no explicit accept or revision wording."
                : `Inferred from the reviewer's last real message row (seq ${review.statusFromSeq ?? "unknown"}); the bridge does not expose a structured review-status field.`}
            </p>
            <h4>Reviewer findings / comments</h4>
            {review.comments.length ? (
              <ul className={s.commentList}>
                {review.comments.map((c) => (
                  <li key={c.seq} className={s.comment} data-pair-comment={c.seq}>
                    <div className={s.commentHead}>
                      <span className={s.mono}>row {c.seq}</span>
                      {c.createdAt && <span className={s.muted}>{c.createdAt}</span>}
                      <Badge tone="neutral">Comment only</Badge>
                    </div>
                    <pre className={s.commentBody}>{c.content}</pre>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={s.hint}>
                The independent reviewer has not posted any comment rows in its real bot transcript.
              </p>
            )}
          </>
        )}
      </section>

      <footer className={s.pairFoot}>
        Source: <code>GET /api/bridge/bots</code> and <code>GET /api/bridge/bots/:id/rows</code>.
        The bridge does not expose a dedicated reviewer role, review-request route, file-diff route,
        apply route or accept/reject field. Values above are real reported rows or are explicitly
        labelled as inferred from them; nothing is fabricated.
      </footer>
    </div>
  );
}

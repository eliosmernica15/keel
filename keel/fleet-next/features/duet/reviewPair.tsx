"use client";

// Phase 5 — Duet Review Pair: an explicit builder / independent reviewer pair.
//
// Honesty rules, enforced here rather than assumed:
//  - Identity, model and prompt/notes come only from real `bots` rows.
//  - Review requests, findings/comments and accept/revision state come only
//    from real `bots/:id/rows` message rows of those two agents.
//  - The bridge has NO dedicated reviewer-role, review-request, structured
//    comment or comment-resolution route. Requests use the real
//    `bots/:id/messages` route; "Send to builder" uses the real `tasks` and
//    `bots/:id/messages` routes; resolve/dismiss is a local, labelled choice.
//  - A reviewer bot is created through the real `POST bots` route. Its standing
//    edit/shell approvals are revoked with `POST bots/:id/policies/revoke`;
//    the resulting policy list is read back from `GET bots/:id/policies`.
//    The bridge has no "deny" policy, so only verified facts are displayed.
//  - The reviewer is comment-only. This pane never renders an edit, save,
//    write, trust, apply or execute control for it (or for anyone).

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { asArray, BridgeError } from "@/features/code/workspace";
import type { Notice } from "@/lib/types";
import { Badge, Button, EmptyState, IconButton, Spinner } from "@/components/ui";
import { Icon } from "@/components/icons";
import { usePairComments, type CommentResolution } from "./pairComments";
import {
  MISSING_COMMENT_ENDPOINT, MISSING_RESOLVE_ENDPOINT, REVIEW_TOOLS,
  parseReviewComments, policiesOf, reviewPaths, unwrapBot, unwrapTask,
} from "./pairSupport";
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
  policies: Awaited<ReturnType<typeof policiesOf>>;
}

type Resolution = CommentResolution;

interface Props {
  projectId: string | null;
  trusted: boolean;
  notify?: (message: string, kind?: Notice["kind"]) => void;
}

const REVIEWER_ROLE = /review|critic|audit|\bqa\b|independent/i;
const BUILDER_ROLE = /builder|implement|develop|engineer|coder|author/i;
const REVIEW_REQUEST = /\breview\b/i;
const ACCEPT = /\b(accept|accepted|approve|approved|lgtm|looks good|no issues|no changes needed)\b/i;
const REVISION = /\b(revision|revisions|request changes|changes requested|reject|rejected|blocked|needs work|must fix)\b/i;

const REVIEWER_NAME = "Keel Reviewer";
const REVIEWER_ROLE_TEXT = "Independent reviewer — comment only (no edits, no shell)";
const REVIEWER_NOTES =
  "Reply with comment-only review findings. Never edit files, write files, run shell commands or apply changes. Use a JSON comments array with file, line, severity, message and suggestion when reviewing a diff.";

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

function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : fallback;
  } catch { return fallback; }
}
function writeLocal(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

function Fact({ label, value, title }: { label: string; value?: string; title?: string }) {
  return (
    <div className={s.factPair}>
      <dt>{label}</dt>
      <dd>{value
        ? <span className={s.mono} title={title ?? value}>{value}</span>
        : <span className={s.notReported}>not reported by bridge</span>}</dd>
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

export default function ReviewPairView({ projectId, trusted, notify }: Props) {
  const { setComments: publishComments } = usePairComments();
  const [state, setState] = useState<PairState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);

  const [reviewerId, setReviewerId] = useState<string | null>(null);
  const [builderId, setBuilderId] = useState<string | null>(null);
  const [resolution, setResolution] = useState<Record<string, Resolution>>({});
  const [sentTasks, setSentTasks] = useState<Record<string, string>>({});
  const [reviewFiles, setReviewFiles] = useState<string[]>([]);
  const [requestFile, setRequestFile] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  /* Project-scoped local choices. These are UI preferences, never bridge facts. */
  useEffect(() => {
    if (!projectId) return;
    setReviewerId(readLocal<string | null>(`keel-duet:pair:reviewer:${projectId}`, null));
    setBuilderId(readLocal<string | null>(`keel-duet:pair:builder:${projectId}`, null));
    setResolution(readLocal<Record<string, Resolution>>(`keel-duet:pair:resolution:${projectId}`, {}));
    setSentTasks(readLocal<Record<string, string>>(`keel-duet:pair:sent:${projectId}`, {}));
    // Do not carry another project's findings into this one's Review tab.
    publishComments([]);
  }, [projectId, publishComments]);
  useEffect(() => { if (projectId) writeLocal(`keel-duet:pair:reviewer:${projectId}`, reviewerId); }, [projectId, reviewerId]);
  useEffect(() => { if (projectId) writeLocal(`keel-duet:pair:builder:${projectId}`, builderId); }, [projectId, builderId]);
  useEffect(() => { if (projectId) writeLocal(`keel-duet:pair:resolution:${projectId}`, resolution); }, [projectId, resolution]);
  useEffect(() => { if (projectId) writeLocal(`keel-duet:pair:sent:${projectId}`, sentTasks); }, [projectId, sentTasks]);

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
      const auto = classifyPair(bots);
      const resolvedReviewer = bots.find((b) => b.id === reviewerId && REVIEWER_ROLE.test(b.role))
        ?? (reviewerId ? null : auto.reviewer);
      const resolvedBuilder = bots.find((b) => b.id === builderId && b.id !== resolvedReviewer?.id)
        ?? (builderId ? null : auto.builder);
      const [builderRaw, reviewerRaw, policyRaw] = await Promise.all([
        resolvedBuilder ? bridge.botRows(resolvedBuilder.id) : Promise.resolve([]),
        resolvedReviewer ? bridge.botRows(resolvedReviewer.id) : Promise.resolve([]),
        resolvedReviewer ? bridge.botPolicies(resolvedReviewer.id) : Promise.resolve({ policies: [] }),
      ]);
      if (!current()) return;
      setState({
        bots, builder: resolvedBuilder, reviewer: resolvedReviewer,
        builderRows: normalizeRows(builderRaw),
        reviewerRows: normalizeRows(reviewerRaw),
        policies: policiesOf(policyRaw),
      });
    } catch (err) {
      if (!current()) return;
      setError(errMessage(err));
      setBridgeDown(isBridgeUnavailable(err));
      setState(null);
    } finally {
      if (current()) setLoading(false);
    }
  }, [reviewerId, builderId]);

  useEffect(() => { void load(); }, [load, tick]);

  /* File choices come from the real git review endpoint, never a guess. */
  useEffect(() => {
    if (!projectId || !trusted) { setReviewFiles([]); return; }
    let alive = true;
    void bridge.review(projectId).then((raw) => {
      if (alive) setReviewFiles(reviewPaths((raw as { status?: unknown })?.status));
    }).catch(() => { if (alive) setReviewFiles([]); });
    return () => { alive = false; };
  }, [projectId, trusted, tick]);

  const review = useMemo(
    () => deriveReviewState(state?.builderRows ?? [], state?.reviewerRows ?? []),
    [state?.builderRows, state?.reviewerRows],
  );
  const comments = useMemo(
    () => parseReviewComments(review.comments),
    [review.comments],
  );

  /* Publish to the Review tab so the same real comments appear inline there. */
  useEffect(() => {
    publishComments(comments.map((c) => ({
      ...c,
      resolution: resolution[c.key],
      sentTaskId: sentTasks[c.key],
    })));
  }, [comments, resolution, sentTasks, publishComments]);

  const reviewerCandidates = useMemo(
    () => (state?.bots ?? []).filter((b) => REVIEWER_ROLE.test(b.role) && b.id !== builderId),
    [state?.bots, builderId],
  );
  const builderCandidates = useMemo(
    () => (state?.bots ?? []).filter((b) => b.id !== reviewerId),
    [state?.bots, reviewerId],
  );
  const standingReviewTools = useMemo(
    () => (state?.policies ?? []).filter(
      (p) => (REVIEW_TOOLS as readonly string[]).includes(String(p.tool_name ?? ""))
        && String(p.decision ?? "").toLowerCase() === "always",
    ),
    [state?.policies],
  );

  async function createCommentOnlyReviewer() {
    setBusy("create"); setNotice(null);
    try {
      const created = unwrapBot(await bridge.createBot({
        name: REVIEWER_NAME,
        role: REVIEWER_ROLE_TEXT,
        engine: "provider",
        notes: REVIEWER_NOTES,
      }));
      const before = policiesOf(await bridge.botPolicies(created.id));
      const revoked: string[] = [];
      const absent: string[] = [];
      for (const tool of REVIEW_TOOLS) {
        const standing = before.some(
          (p) => p.tool_name === tool && String(p.decision ?? "").toLowerCase() === "always",
        );
        if (!standing) { absent.push(tool); continue; }
        await bridge.revokePolicy(created.id, tool);
        revoked.push(tool);
      }
      setReviewerId(created.id);
      setNotice(
        `Created ${created.name || created.id} with a comment-only role. Standing edit/shell permissions revoked: ${revoked.join(", ") || "none present"}; already absent: ${absent.join(", ") || "none"}. The bridge has no deny policy — revoking removes standing approvals only.`,
      );
      notify?.(`Comment-only reviewer ${created.name || created.id} created.`, "success");
      setTick((t) => t + 1);
    } catch (err) {
      setNotice(`Could not create reviewer: ${errMessage(err)}`);
      notify?.(`Could not create reviewer: ${errMessage(err)}`, "error");
    } finally { setBusy(null); }
  }

  async function requestReview() {
    const reviewer = state?.reviewer;
    if (!reviewer) { setNotice("Select or create an independent reviewer first."); return; }
    setBusy("request"); setNotice(null);
    try {
      const file = reviewFiles.includes(requestFile) ? requestFile : null;
      let context = "";
      if (file && projectId) {
        const data = await bridge.review(projectId) as { diff_stat?: unknown };
        if (typeof data.diff_stat === "string" && data.diff_stat.trim()) {
          context = `\n\nBridge diff_stat (real):\n${data.diff_stat.trim().slice(0, 6000)}`;
        }
      }
      const content = `Review request${file ? ` for ${file}` : " for the current turn"}. ` +
        `Comment only: do not edit files, write files or run shell commands. Reply with file, line, severity and suggestion when available.${context}`;
      const result = await bridge.sendMessage(reviewer.id, { content, mode: "plan" }) as
        | { queued?: boolean; seq?: number; busy?: boolean } | null;
      setNotice(result?.queued === false
        ? `Reviewer is busy (seq ${result.seq ?? "unknown"}); no review was queued.`
        : `Review requested through POST /api/bridge/bots/${reviewer.id}/messages${result?.seq ? ` (row seq ${result.seq})` : ""}.`);
      await load();
    } catch (err) {
      setNotice(`Review request failed: ${errMessage(err)}`);
    } finally { setBusy(null); }
  }

  async function sendToBuilder(comment: (typeof comments)[number]) {
    const builder = state?.builder;
    if (!builder) { setNotice("Select a builder agent before sending a finding."); return; }
    setBusy(`send:${comment.key}`); setNotice(null);
    const location = comment.file
      ? `${comment.file}${comment.line !== null && comment.line !== undefined ? `:${comment.line}` : ""}`
      : "current turn";
    const detail = [
      `Reviewer finding${comment.seq !== null ? ` (reviewer row seq ${comment.seq})` : ""}: ${comment.message}`,
      comment.suggestion ? `Suggestion: ${comment.suggestion}` : "",
    ].filter(Boolean).join("\n");
    try {
      const task = unwrapTask(await bridge.createTask({
        title: `Review: ${location}`,
        description: detail,
        priority: "normal",
        assigned_bot_id: builder.id,
      }));
      const result = await bridge.sendMessage(builder.id, {
        content: `Task ${task.id ?? "unknown"} assigned by you (from reviewer): ${detail}`.slice(0, 32000),
        mode: "build",
      }) as { queued?: boolean; seq?: number } | null;
      setSentTasks((prev) => ({ ...prev, [comment.key]: String(task.id ?? "unknown") }));
      setNotice(result?.queued === false
        ? `Task ${task.id ?? "unknown"} created for ${builder.name || builder.id}; the builder is busy so no message was queued.`
        : `Task ${task.id ?? "unknown"} created and queued to ${builder.name || builder.id}.`);
      notify?.(`Review finding sent to ${builder.name || builder.id}.`, "success");
      await load();
    } catch (err) {
      setNotice(`Send to builder failed: ${errMessage(err)}`);
      notify?.(`Send to builder failed: ${errMessage(err)}`, "error");
    } finally { setBusy(null); }
  }

  function resolveComment(comment: (typeof comments)[number], value: Resolution) {
    setResolution((prev) => ({ ...prev, [comment.key]: value }));
    setNotice(
      `${value === "resolved" ? "Resolved" : "Dismissed"} in this browser only. ` +
      `${MISSING_RESOLVE_ENDPOINT} does not exist on this bridge, so nothing was changed for the reviewer or builder.`,
    );
  }

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

      <section className={s.pairSetup} data-pair-section="setup">
        <h4>Pair setup</h4>
        <div className={s.pairSelectors}>
          <label className={s.fieldLabel} htmlFor="duet-pair-reviewer">Reviewer (comment-only)</label>
          <select id="duet-pair-reviewer" className={s.pairSelect} value={state.reviewer?.id ?? ""}
            onChange={(e) => setReviewerId(e.target.value || null)}>
            <option value="">{reviewerCandidates.length ? "No reviewer selected" : "No reviewer role reported"}</option>
            {reviewerCandidates.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.id})</option>)}
          </select>
          <label className={s.fieldLabel} htmlFor="duet-pair-builder">Builder</label>
          <select id="duet-pair-builder" className={s.pairSelect} value={state.builder?.id ?? ""}
            onChange={(e) => setBuilderId(e.target.value || null)}>
            <option value="">{builderCandidates.length ? "No builder selected" : "No builder role reported"}</option>
            {builderCandidates.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.id})</option>)}
          </select>
        </div>
        {!state.reviewer ? (
          <div className={s.pairActionRow}>
            <Button variant="primary" size="sm" loading={busy === "create"} onClick={() => void createCommentOnlyReviewer()}>
              <Icon name="plus" size={14} /> Create comment-only reviewer
            </Button>
            <span className={s.muted}>Uses <code className={s.mono}>POST /api/bridge/bots</code>, then revokes standing edit/shell approvals.</span>
          </div>
        ) : (
          <p className={s.hint} data-pair-policy="summary">
            Standing edit/shell approvals for this reviewer: {standingReviewTools.length
              ? <span className={s.mono}>{standingReviewTools.map((p) => p.tool_name).join(", ")}</span>
              : <strong>none reported</strong>}.
            {" "}The bridge exposes no deny policy, only revocation of standing approvals; Keel offers no edit, write or execute control here.
          </p>
        )}
      </section>

      <section className={s.pairState} data-pair-section="state">
        <h4>Review state</h4>
        {!state.reviewer ? (
          <p className={s.hint}>
            Review requests, findings and accept/revision status are unavailable: this bridge does not
            report an independent reviewer. Create a comment-only reviewer above; no state is inferred
            from a reviewer that does not exist.
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

            <div className={s.pairActionRow} data-pair-section="request">
              <label className={s.fieldLabel} htmlFor="duet-pair-file">Review target</label>
              <select id="duet-pair-file" className={s.pairSelect} value={reviewFiles.includes(requestFile) ? requestFile : ""}
                onChange={(e) => setRequestFile(e.target.value)}
                disabled={!reviewFiles.length}>
                <option value="">{reviewFiles.length ? "Current turn (no file selected)" : "No files reported by git review"}</option>
                {reviewFiles.map((file) => <option key={file} value={file}>{file}</option>)}
              </select>
              <Button size="sm" variant="secondary" loading={busy === "request"} onClick={() => void requestReview()}>
                <Icon name="send" size={14} /> Request review
              </Button>
            </div>

            <h4>Reviewer findings / comments</h4>
            {notice && <p className={s.note} role="status" data-pair-notice="true">{notice}</p>}
            <p className={s.hint} data-pair-rule="builder-cannot-resolve">
              The builder cannot resolve or dismiss reviewer comments here. Only you can; resolution is
              stored in this browser. The bridge has no comment-resolution endpoint
              (<code className={s.mono}>{MISSING_RESOLVE_ENDPOINT}</code>), and no structured comment endpoint
              (<code className={s.mono}>{MISSING_COMMENT_ENDPOINT}</code>).
            </p>
            {comments.length ? (
              <ul className={s.commentList}>
                {comments.map((c) => (
                  <li key={c.key} className={s.comment} data-pair-comment={c.seq ?? c.key}
                    data-comment-file={c.file ?? ""} data-comment-severity={c.severity ?? ""}>
                    <div className={s.commentHead}>
                      <span className={s.mono}>{c.file ? `${c.file}${c.line !== null && c.line !== undefined ? `:${c.line}` : ""}` : `row ${c.seq ?? "unknown"}`}</span>
                      {c.severity && <Badge tone={/high|critical|blocker/i.test(c.severity) ? "danger" : "warning"}>{c.severity}</Badge>}
                      <Badge tone="neutral">{c.structured ? "Structured finding" : "Comment only"}</Badge>
                      {c.createdAt && <span className={s.muted}>{c.createdAt}</span>}
                      {resolution[c.key] && <Badge tone={resolution[c.key] === "resolved" ? "success" : "neutral"}>{resolution[c.key]} locally</Badge>}
                      {sentTasks[c.key] && <Badge tone="info">Sent to builder · task {sentTasks[c.key]}</Badge>}
                    </div>
                    <pre className={s.commentBody}>{c.message}</pre>
                    {c.suggestion && <p className={s.commentSuggestion}><strong>Suggestion:</strong> {c.suggestion}</p>}
                    <div className={s.commentActions}>
                      <Button size="sm" variant="ghost" disabled={!state.builder || Boolean(sentTasks[c.key])}
                        loading={busy === `send:${c.key}`} onClick={() => void sendToBuilder(c)}>
                        <Icon name="send" size={13} /> {sentTasks[c.key] ? "Sent to builder" : "Send to builder"}
                      </Button>
                      <Button size="sm" variant="ghost" disabled={Boolean(resolution[c.key])}
                        onClick={() => resolveComment(c, "resolved")}>
                        <Icon name="check" size={13} /> Resolve
                      </Button>
                      <Button size="sm" variant="ghost" disabled={Boolean(resolution[c.key])}
                        onClick={() => resolveComment(c, "dismissed")}>
                        <Icon name="close" size={13} /> Dismiss
                      </Button>
                    </div>
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
        Source: <code>GET /api/bridge/bots</code>, <code>POST /api/bridge/bots</code>,
        {" "}<code>GET /api/bridge/bots/:id/rows</code>, <code>POST /api/bridge/bots/:id/messages</code>,
        {" "}<code>GET /api/bridge/bots/:id/policies</code>, <code>POST /api/bridge/bots/:id/policies/revoke</code>,
        {" "}<code>POST /api/bridge/tasks</code> and <code>GET /api/bridge/projects/:id/review</code>.
        The bridge does not expose a dedicated reviewer role, structured comment route, file-diff apply route
        or accept/reject field. Values above are real reported rows or are explicitly labelled as inferred
        from them or stored locally; nothing is fabricated.
      </footer>
    </div>
  );
}

"use strict";

/* Keel Fleet — F0 front-end. Token comes from ?t= (stripped) or sessionStorage.
   Every request carries X-Keel-Token; EventSource falls back to ?t=. */

const state = {
  token: null,
  bots: [],
  groups: [],
  view: "agent",          // "agent" | "group" | "tasks" | "library" | "routines"
  selectedId: null,
  selectedGroupId: null,
  tasks: [],
  taskFilter: "active",   // active|pending|in_progress|completed|failed|cancelled|all
  tasksAssignedTo: null,  // null = everyone, or a bot id
  selectedTaskId: null,
  files: [],
  libraryAgentFilter: null, // null = all agents
  selectedFileId: null,
  routines: [],
  selectedRoutineId: null,
  rows: [],
  groupRows: [],
  lastGroupSeq: 0,   // max group seq seen anywhere; drives SSE catch-up
  streamBuf: "",     // accumulated live token text (ephemeral, unrendered in db)
  streamNode: null,  // the transient streaming bubble, if any
  pendingSteps: [],
  liveStepsOpen: false,
  es: null,
  sending: false,
  botActivity: {}, // bot_id -> count of open steps
  approvalStates: {}, // approval_id -> merged card body (last row wins)
  approvalNodes: {},  // approval_id -> DOM node for in-place updates
  lastSeq: 0,         // max row seq seen anywhere; drives SSE catch-up
};

const $ = (id) => document.getElementById(id);
const rowsEl = $("rows");
const listEl = $("fleet-list");
const composerInput = $("composer-input");
const sendBtn = $("send-btn");
const panelEl = $("panel");

/* ---------------- token + helpers ---------------- */

function bootToken() {
  const params = new URLSearchParams(location.search);
  const t = params.get("t");
  if (t) {
    sessionStorage.setItem("keel_fleet_token", t);
    const clean = new URL(location.href);
    clean.searchParams.delete("t");
    history.replaceState(null, "", clean.pathname + clean.search);
    state.token = t;
    return;
  }
  state.token = sessionStorage.getItem("keel_fleet_token") || "";
}

async function api(path, opts = {}) {
  const resp = await fetch(path, {
    ...opts,
    headers: {
      "X-Keel-Token": state.token,
      ...(opts.headers || {}),
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  const text = await resp.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
  if (!resp.ok) {
    const err = new Error((body && (body.error || body.refused)) || `http ${resp.status}`);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "lf-toast";
  el.textContent = msg;
  document.body.appendChild(el);
  window.setTimeout(() => el.remove(), 3400);
}

function avatarInitials(name) {
  const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

function paintAvatar(el, bot) {
  if (!el) return;
  el.textContent = avatarInitials(bot?.name);
  const hue = Number(bot?.avatar_hue ?? 210);
  el.style.setProperty("--lf-hue", hue);
  el.style.background = `hsl(${hue} 45% 22%)`;
  el.style.borderColor = `hsl(${hue} 60% 38%)`;
}

/* ---------------- rail ---------------- */

function botStatusColor(botId) {
  const open = state.botActivity[botId] || 0;
  return open > 0 ? "is-working" : "";
}

function renderRail() {
  listEl.innerHTML = "";
  if (state.bots.length === 0) {
    listEl.appendChild(Object.assign(document.createElement("div"), {
      className: "lf-empty",
      innerHTML: "No agents yet.<small>Create one with the + button.</small>",
    }));
    return;
  }
  const sorted = [...state.bots].sort((a, b) =>
    String(a.last_active_at).localeCompare(String(b.last_active_at)) * -1);
  for (const bot of sorted) {
    const card = document.createElement("div");
    card.className = "lf-botcard" + (bot.id === state.selectedId ? " is-active" : "") +
                     " " + botStatusColor(bot.id);
    card.dataset.id = bot.id;
    card.innerHTML = `
      <div class="lf-avatar" style="--lf-hue:${bot.avatar_hue ?? 210}"></div>
      <div class="lf-botcard-meta">
        <div class="lf-botcard-name"></div>
        <div class="lf-botcard-role"></div>
      </div>
      <div class="lf-botcard-dot" title="activity"></div>`;
    paintAvatar(card.querySelector(".lf-avatar"), bot);
    card.querySelector(".lf-botcard-name").textContent = bot.name;
    card.querySelector(".lf-botcard-role").textContent = bot.role || "generalist";
    card.addEventListener("click", () => selectBot(bot.id));
    listEl.appendChild(card);
  }
}

async function loadBots(selectId) {
  const body = await api("/api/fleet/bots");
  state.bots = body.bots || [];
  if (selectId && state.bots.some((b) => b.id === selectId)) {
    state.selectedId = selectId;
  } else if (!state.bots.some((b) => b.id === state.selectedId)) {
    state.selectedId = state.bots[0]?.id ?? null;
  }
  renderRail();
  renderTopPills();
  if (state.selectedId && state.view === "agent") renderSelectedHeader();
  loadGroups();
  refreshWorkspaceCounts();
}

async function refreshWorkspaceCounts() {
  try {
    const [tasksBody, filesBody, routinesBody] = await Promise.all([
      api("/api/fleet/tasks"),
      api("/api/fleet/library"),
      api("/api/fleet/routines"),
    ]);
    state.tasks = tasksBody.tasks || [];
    state.files = filesBody.files || [];
    state.routines = routinesBody.routines || [];
    renderWsRailCounts();
  } catch {
    // counts are decorative; ignore failures
  }
}

function selectedBot() {
  return state.view === "agent"
    ? state.bots.find((b) => b.id === state.selectedId) || null
    : null;
}

function selectedGroup() {
  return state.groups.find((g) => g.id === state.selectedGroupId) || null;
}

function memberById(id) {
  const group = selectedGroup();
  return (group?.members || []).find((m) => m.id === id)
    || state.bots.find((b) => b.id === id)
    || null;
}

async function selectBot(id) {
  state.view = "agent";
  clearStreamBubble();
  state.selectedId = id;
  state.selectedGroupId = null;
  state.rows = [];
  state.groupRows = [];
  state.pendingSteps = [];
  state.liveStepsOpen = false;
  resetApprovalState();
  rowsEl.innerHTML = "";
  syncViewChrome();
  renderRail();
  renderSelectedHeader();
  const bot = selectedBot();
  if (bot) syncPanelFromBot(bot);
  await loadRows();
  loadPermissions();
}

async function renderAgentTasks(bot) {
  const host = $("agent-tasks");
  if (!host) return;
  const nameEl = $("agent-tasks-name");
  if (nameEl) nameEl.textContent = bot?.name || "this agent";
  if (!bot) { host.innerHTML = ""; return; }
  try {
    const body = await api(`/api/fleet/tasks?assigned=${encodeURIComponent(bot.id)}`);
    const tasks = (body.tasks || []).filter(
      (t) => t.status === "pending" || t.status === "in_progress");
    host.innerHTML = "";
    if (tasks.length === 0) {
      host.innerHTML = '<div class="lf-empty">No open tasks for this agent.</div>';
      return;
    }
    for (const task of tasks.slice(0, 12)) {
      const el = document.createElement("div");
      el.className = "lf-agent-task";
      el.innerHTML = `<span class="lf-task-glyph">${TASK_GLYPH[task.status] || "○"}</span>
        <span class="lf-agent-task-title"></span>
        <span class="lf-agent-task-status">${esc(task.status.replace("_", " "))} · ${task.progress || 0}%</span>`;
      el.querySelector(".lf-agent-task-title").textContent = task.title;
      el.addEventListener("click", () => {
        selectTasksView({ assignedTo: bot.id });
      });
      host.appendChild(el);
    }
  } catch (err) {
    host.innerHTML = `<div class="lf-empty">Tasks unavailable: ${err.message}</div>`;
  }
}

function syncViewChrome() {
  const chatVisible = state.view === "agent" || state.view === "group";
  $("view-chat").hidden = !chatVisible;
  $("view-tasks").hidden = state.view !== "tasks";
  $("view-library").hidden = state.view !== "library";
  $("view-routines").hidden = state.view !== "routines";
  const agentOnly = state.view === "agent";
  document.querySelectorAll(".lf-agent-only").forEach((el) => { el.hidden = !agentOnly; });
  $("chat-members").hidden = state.view !== "group";
  document.querySelectorAll(".lf-ws-item").forEach((el) => {
    el.classList.toggle("is-active", el.id === `ws-${state.view}-btn`);
  });
  document.querySelectorAll(".lf-groupcard").forEach((el) => {
    el.classList.toggle("is-active",
      state.view === "group" && el.dataset.id === state.selectedGroupId);
  });
}

function renderSelectedHeader() {
  const head = $("chat-head");
  const composer = $("composer-input");
  if (state.view === "group") {
    const group = selectedGroup();
    if (!group) {
      $("chat-name").textContent = "Pick an agent or group";
      $("chat-role").textContent = "…or create one with the + button";
      $("chat-members").innerHTML = "";
      composerInput.value = "";
      composerInput.disabled = true;
      sendBtn.disabled = true;
      $("status-right").textContent = "no group selected";
      $("status-mid").textContent = "idle";
      return;
    }
    $("chat-name").textContent = group.name;
    $("chat-role").textContent = `group · ${group.members.length} agents · each answers once per round`;
    paintAvatar($("chat-avatar"), { name: group.name, avatar_hue: 265 });
    const chips = group.members.map((m) =>
      `<span class="lf-mchip"><span class="lf-avatar" style="--lf-hue:${m.avatar_hue ?? 210};width:18px;height:18px;border-radius:5px;font-size:.55rem;display:grid;place-items:center;">${avatarInitials(m.name)}</span><b>${esc(m.name)}</b><span class="lf-muted">${esc(m.role || "")}</span></span>`).join("");
    $("chat-members").innerHTML = chips;
    composerInput.disabled = false;
    composerInput.placeholder = `Message ${group.name}…`;
    sendBtn.disabled = false;
    $("status-right").textContent = `group ${group.id}`;
    $("status-mid").textContent = "ready";
    return;
  }
  const bot = selectedBot();
  if (!bot) {
    $("chat-name").textContent = "Pick an agent";
    $("chat-role").textContent = "…or create one with the + button";
    composerInput.value = "";
    composerInput.disabled = true;
    sendBtn.disabled = true;
    $("status-right").textContent = "no agent selected";
    $("status-mid").textContent = "idle";
    return;
  }
  $("chat-name").textContent = bot.name;
  const isEcho = bot.engine === "echo";
  $("chat-role").textContent =
    (bot.role || "generalist") + " · " +
    (isEcho ? "scripted test"
            : `provider ${bot.provider || "auto"}` +
              ((bot.model || "").trim() ? ` · ${bot.model.trim()}` : ""));
  paintAvatar($("chat-avatar"), bot);
  $("chat-members").innerHTML = "";
  composerInput.disabled = false;
  composerInput.placeholder = `Message ${bot.name}…`;
  sendBtn.disabled = false;
  $("status-right").textContent = `agent ${bot.id}`;
  $("status-mid").textContent =
    (state.botActivity[bot.id] || 0) > 0 ? "working…" : "ready";
}

/* ---------------- delegation chips (F3) ---------------- */

function appendDelegateChip(row) {
  const d = row.body.delegated || {};
  const holder = document.createElement("div");
  holder.className = "lf-delegate" + (d.ok === false ? " is-failed" : "");
  const to = d.to || d.to_id || "agent";
  holder.innerHTML = `
    <div class="lf-delegate-head">
      <span class="lf-delegate-badge">${d.ok === false ? "delegation failed" : "delegated"}</span>
      <span class="lf-delegate-title"></span>
      <button type="button" class="lf-delegate-toggle" aria-expanded="false">show reply</button>
    </div>
    <div class="lf-delegate-body" hidden></div>`;
  holder.querySelector(".lf-delegate-title").textContent = `→ ${to}`;
  const titleEl = holder.querySelector(".lf-delegate-title");
  const target = state.bots.find((b) => b.id === d.to_id || b.name === d.to);
  if (target) {
    titleEl.style.cursor = "pointer";
    titleEl.title = `Open ${target.name}'s conversation`;
    titleEl.addEventListener("click", () => selectBot(target.id));
  }
  holder.querySelector(".lf-delegate-body").textContent = d.reply || "(no reply)";
  const toggle = holder.querySelector(".lf-delegate-toggle");
  toggle.addEventListener("click", () => {
    const body = holder.querySelector(".lf-delegate-body");
    body.hidden = !body.hidden;
    const open = !body.hidden;
    toggle.textContent = open ? "hide reply" : "show reply";
    toggle.setAttribute("aria-expanded", String(open));
  });
  rowsEl.appendChild(holder);
  rowsEl.scrollTop = rowsEl.scrollHeight;
}

/* ---------------- approval cards ---------------- */

const _approvalMerged = (aid, body) => {
  const prior = state.approvalStates[aid] || {};
  // superseding rows only carry the decision keys; keep request metadata
  const merged = { ...prior, ...body };
  if (!merged.summary && prior.summary) merged.summary = prior.summary;
  state.approvalStates[aid] = merged;
  return merged;
};

function _approvalFoot(stateBody) {
  if (stateBody.status === "pending") {
    return "Unanswered cards are refused automatically after 5 minutes.";
  }
  if (stateBody.status === "approved" && stateBody.decision === "once") {
    return "Approved once — this single call ran; the next call asks again.";
  }
  if (stateBody.status === "approved" && stateBody.decision === "always") {
    return "Always allowed for this agent — revoke in the Permissions tab.";
  }
  if (stateBody.status === "denied") {
    return "Denied — this call did not run.";
  }
  if (stateBody.status === "expired") {
    return stateBody.decision === "restart"
      ? "Expired — the server restarted before a decision was made; refused."
      : "Timed out — no decision was made; the call was refused.";
  }
  return "";
}

function renderApprovalCard(node, body) {
  node.className = `lf-approval is-${body.status}`;
  node.innerHTML = "";
  const head = document.createElement("div");
  head.className = "lf-approval-head";
  const icon = document.createElement("span");
  icon.className = "lf-approval-icon";
  icon.textContent = body.status === "pending" ? "!" : body.status === "approved" ? "✓" : "×";
  const titles = document.createElement("div");
  titles.className = "lf-approval-titles";
  const title = document.createElement("div");
  title.className = "lf-approval-title";
  title.textContent = `${selectedBot()?.name || "agent"} requests permission`;
  const tool = document.createElement("div");
  tool.className = "lf-approval-tool";
  tool.textContent = body.tool_name || "tool";
  titles.append(title, tool);
  const pill = document.createElement("span");
  pill.className = `lf-approval-pill is-${body.status}`;
  pill.textContent = body.status;
  head.append(icon, titles, pill);

  const explain = document.createElement("div");
  explain.className = "lf-approval-explain";
  explain.textContent = body.explanation || "";

  const args = document.createElement("pre");
  args.className = "lf-approval-args";
  args.textContent = body.summary || "(no arguments)";

  const foot = document.createElement("div");
  foot.className = "lf-approval-foot";
  foot.textContent = _approvalFoot(body);

  node.append(head, explain, args);

  if (body.status === "pending") {
    const actions = document.createElement("div");
    actions.className = "lf-approval-actions";
    const bot = selectedBot();
    const fuse = [
      { label: "Don't allow", decision: "never", kind: "lf-ghost" },
      { label: "Allow once", decision: "once", kind: "lf-ghost" },
      { label: "Always allow", decision: "always", kind: "lf-primary" },
    ];
    for (const spec of fuse) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = spec.kind;
      btn.textContent = spec.label;
      btn.addEventListener("click", () => decideApproval(bot?.id, body.approval_id, spec.decision, node, fuse));
      actions.appendChild(btn);
    }
    node.appendChild(actions);
  }
  node.appendChild(foot);
}

async function decideApproval(botId, approvalId, decision, node, siblings) {
  if (!botId || !approvalId) return;
  for (const btn of node.querySelectorAll("button")) btn.disabled = true;
  try {
    const res = await api(`/api/fleet/bots/${botId}/approvals/${approvalId}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
    const approval = res.approval || {};
    const merged = _approvalMerged(approvalId, {
      status: approval.status,
      decision: approval.decision,
      decided_at: approval.decided_at,
    });
    renderApprovalCard(node, merged);
    toast(decision === "always" ? "Always allowed."
        : decision === "once" ? "Approved once."
        : "Denied.");
    loadPermissions();
  } catch (err) {
    if (err.status === 409) {
      const body = err.body?.approval || {};
      const merged = _approvalMerged(approvalId, body);
      renderApprovalCard(node, merged);
      toast("That card was already resolved.");
    } else {
      toast(err.message || "failed to record decision");
      for (const btn of node.querySelectorAll("button")) btn.disabled = false;
    }
  }
}

function upsertApprovalRow(row) {
  const body = row.body || {};
  const aid = body.approval_id || "";
  if (!aid) return;
  const merged = _approvalMerged(aid, body);
  const existing = state.approvalNodes[aid];
  if (existing) {
    renderApprovalCard(existing, merged);
    return;
  }
  const node = document.createElement("div");
  node.dataset.approvalId = aid;
  state.approvalNodes[aid] = node;
  renderApprovalCard(node, merged);
  rowsEl.appendChild(node);
  rowsEl.scrollTop = rowsEl.scrollHeight;
}

function resetApprovalState() {
  state.approvalStates = {};
  state.approvalNodes = {};
}

/* ---------------- groups (F3) ---------------- */

async function loadGroups() {
  const body = await api("/api/fleet/groups");
  state.groups = body.groups || [];
  renderGroupList();
}

function renderGroupList() {
  const host = $("group-list");
  host.innerHTML = "";
  for (const group of state.groups) {
    const card = document.createElement("div");
    card.className = "lf-groupcard" + (group.id === state.selectedGroupId ? " is-active" : "");
    card.dataset.id = group.id;
    const memberNames = (group.members || []).map((m) => m.name).join(" · ");
    card.innerHTML = `
      <span class="lf-group-ic">G</span>
      <span class="lf-groupcard-meta">
        <span class="lf-groupcard-name"></span>
        <span class="lf-groupcard-members"></span>
      </span>
      <button class="lf-groupcard-del" title="Delete group" aria-label="Delete group">✕</button>`;
    card.querySelector(".lf-groupcard-name").textContent = group.name;
    card.querySelector(".lf-groupcard-members").textContent = memberNames;
    card.addEventListener("click", (ev) => {
      if (ev.target.closest(".lf-groupcard-del")) return;
      selectGroup(group.id);
    });
    card.querySelector(".lf-groupcard-del").addEventListener("click", async () => {
      if (!window.confirm(`Delete group ${group.name}? History of the shared ledger goes with it.`)) return;
      try {
        await api(`/api/fleet/groups/${group.id}/delete`, { method: "POST", body: "{}" });
        if (state.selectedGroupId === group.id) {
          state.selectedGroupId = null;
          state.view = "agent";
          state.groupRows = [];
          rowsEl.innerHTML = "";
          if (state.selectedId) {
            selectBot(state.selectedId);
            return;
          }
        }
        await loadGroups();
        toast("Group deleted.");
      } catch (err) { toast(err.message); }
    });
    host.appendChild(card);
  }
}

async function selectGroup(id) {
  state.view = "group";
  state.selectedGroupId = id;
  state.selectedId = null;
  state.groupRows = [];
  state.pendingSteps = [];
  rowsEl.innerHTML = "";
  resetApprovalState();
  syncViewChrome();
  renderRail();
  await loadGroupDetail();
  renderGroupsSelection();
  renderSelectedHeader();
}

function renderGroupsSelection() {
  document.querySelectorAll(".lf-groupcard").forEach((el) =>
    el.classList.toggle("is-active", el.dataset.id === state.selectedGroupId));
}

async function loadGroupDetail() {
  if (!state.selectedGroupId) return;
  const body = await api(`/api/fleet/groups/${state.selectedGroupId}`);
  const group = body.group;
  if (group) {
    state.groups = state.groups.map((g) => (g.id === group.id ? group : g));
  }
  for (const row of body.rows || []) handleGroupRow(row);
}

function handleGroupRow(row) {
  if (row && row.seq && row.seq > state.lastGroupSeq) {
    state.lastGroupSeq = row.seq;
  }
  const belongs = row.group_id === state.selectedGroupId;
  if (!belongs) return;
  const node = document.createElement("div");
  const body = row.body || {};
  if (row.kind === "message") {
    if (row.author === "user") {
      node.className = "lf-msg user";
      node.innerHTML = `<span class="lf-bubble-role">you</span><div class="lf-bubble-text"></div>`;
      node.querySelector(".lf-bubble-text").textContent = body.content || "";
    } else {
      const member = memberById(row.author);
      const name = member?.name || row.author;
      const hue = member?.avatar_hue ?? 210;
      node.className = "lf-gmsg";
      node.innerHTML = `
        <div class="lf-gmsg-head">
          <span class="lf-gmsg-avatar" style="background: hsl(${hue} 45% 22%); border: 1px solid hsl(${hue} 60% 38%)"></span>
          <span class="lf-gmsg-name"></span>
          <span class="lf-gmsg-meta">${esc(body.engine || "")}${(body.model || "").trim() ? " · " + esc(body.model.trim()) : ""}</span>
        </div>
        <div class="lf-gmsg-text"></div>`;
      node.querySelector(".lf-gmsg-avatar").textContent = avatarInitials(name);
      node.querySelector(".lf-gmsg-name").textContent = name;
      node.querySelector(".lf-gmsg-text").textContent = body.content || "";
    }
  } else if (row.kind === "member_status") {
    node.className = `lf-gstatus is-${body.status || "done"}`;
    const label = { running: "thinking…", done: "done", failed: "failed",
                    denied: "denied a tool call", busy: "busy — skipped" }[body.status] || body.status;
    node.innerHTML = `<span class="lf-gdot"></span><span></span>`;
    node.querySelector("span:last-child").textContent =
      `${body.bot_name || body.bot_id} — ${label}`;
  } else if (row.kind === "step") {
    node.className = "lf-gstatus is-running";
    node.innerHTML = `<span class="lf-gdot"></span><span></span>`;
    node.querySelector("span:last-child").textContent =
      `${memberById(row.author)?.name || row.author}: ${body.name || "step"} ${body.status === "done" ? "✓" : "…"}`;
  } else if (row.kind === "notice") {
    node.className = "lf-turn-end";
    node.textContent = body.text || "";
  } else if (row.kind === "turn_end") {
    node.className = "lf-turn-end";
    node.textContent = "turn complete";
  } else {
    return;
  }
  rowsEl.appendChild(node);
  rowsEl.scrollTop = rowsEl.scrollHeight;
}

async function sendGroupMessage(text) {
  const res = await api(`/api/fleet/groups/${state.selectedGroupId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content: text }),
  });
  return res;
}

function wireNewGroup() {
  const form = $("newgroup-form");
  const picker = $("newgroup-members");
  const submitBtn = form.querySelector("button[type=submit]");
  const refresh = () => {
    const checked = picker.querySelectorAll("input:checked").length;
    submitBtn.disabled = checked < 2 || checked > 3;
  };
  const renderPicks = () => {
    picker.innerHTML = "";
    for (const bot of state.bots) {
      const label = document.createElement("label");
      const hue = bot.avatar_hue ?? 210;
      label.innerHTML = `
        <input type="checkbox" value="${esc(bot.id)}" />
        <span class="lf-avatar" style="--lf-hue:${hue};width:22px;height:22px;border-radius:6px;font-size:.55rem;display:grid;place-items:center;">${avatarInitials(bot.name)}</span>
        <span>${esc(bot.name)}</span>`;
      picker.appendChild(label);
      label.querySelector("input").addEventListener("change", refresh);
    }
    refresh();
  };
  $("new-group-btn").addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) { renderPicks(); $("newgroup-name").focus(); }
  });
  $("newgroup-cancel").addEventListener("click", () => { form.hidden = true; });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("newgroup-name").value.trim();
    const ids = [...picker.querySelectorAll("input:checked")].map((el) => el.value);
    if (!name || ids.length < 2) return;
    try {
      const body = await api("/api/fleet/groups", {
        method: "POST",
        body: JSON.stringify({ name, bot_ids: ids }),
      });
      form.hidden = true;
      $("newgroup-name").value = "";
      picker.innerHTML = "";
      await loadGroups();
      await selectGroup(body.group.id);
      toast(`Group “${body.group.name}” created.`);
    } catch (err) { toast(err.message); }
  });
}

/* ---------------- workspace: tasks & library (F2) ---------------- */

function showChatView() {
  state.view = "agent";
  if (!state.selectedGroupId && state.bots.length) {
    state.selectedId = state.selectedId || state.bots[0].id;
  }
  syncViewChrome();
}

async function selectTasksView({ assignedTo = null } = {}) {
  state.view = "tasks";
  state.tasksAssignedTo = assignedTo;
  state.selectedTaskId = null;
  $("task-detail").hidden = true;
  syncViewChrome();
  await loadTasks();
}

async function selectLibraryView({ agent = null } = {}) {
  state.view = "library";
  state.libraryAgentFilter = agent;
  state.selectedFileId = null;
  $("library-detail").hidden = true;
  syncViewChrome();
  await loadLibrary();
}

function renderWsRailCounts() {
  const activeTasks = state.tasks.filter(
    (t) => t.status === "pending" || t.status === "in_progress").length;
  $("ws-tasks-count").textContent = activeTasks > 0 ? `${activeTasks} open` : "all clear";
  $("ws-library-count").textContent =
    state.files.length ? `${state.files.length} file${state.files.length === 1 ? "" : "s"}` : "empty";
}

const TASK_FILTERS = [
  ["active", "active"], ["pending", "pending"],
  ["in_progress", "in progress"], ["completed", "done"],
  ["failed", "failed"], ["cancelled", "cancelled"], ["all", "all"],
];
const TASK_GLYPH = { pending: "○", in_progress: "◐", completed: "✓",
                     failed: "✗", cancelled: "⊘" };

async function loadTasks() {
  const params = new URLSearchParams();
  if (state.tasksAssignedTo) params.set("assigned", state.tasksAssignedTo);
  if (state.taskFilter === "pending" || state.taskFilter === "in_progress"
      || state.taskFilter === "completed" || state.taskFilter === "failed"
      || state.taskFilter === "cancelled") {
    params.set("status", state.taskFilter);
  }
  const body = await api(`/api/fleet/tasks?${params}`);
  let tasks = body.tasks || [];
  if (state.taskFilter === "active") {
    tasks = tasks.filter((t) => t.status === "pending" || t.status === "in_progress");
  }
  state.tasks = tasks;
  renderTaskFilters();
  renderTaskList();
  renderWsRailCounts();
  populateAssigneeSelects();
}

function taskMatchesFilter(t) {
  if (state.taskFilter === "active") {
    return t.status === "pending" || t.status === "in_progress";
  }
  if (state.taskFilter === "all") return true;
  return t.status === state.taskFilter;
}

function renderTaskFilters() {
  const host = $("task-filters");
  host.innerHTML = "";
  for (const [key, label] of TASK_FILTERS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "lf-filter-chip" + (state.taskFilter === key ? " is-active" : "");
    b.textContent = label;
    b.addEventListener("click", async () => {
      state.taskFilter = key;
      await loadTasks();
    });
    host.appendChild(b);
  }
  if (state.tasksAssignedTo) {
    const scope = document.createElement("span");
    scope.className = "lf-filter-chip is-active";
    scope.textContent = `assigned to ${state.tasksAssignedTo} ✕`;
    scope.title = "Clear assignment filter";
    scope.style.cursor = "pointer";
    scope.addEventListener("click", async () => {
      state.tasksAssignedTo = null;
      await loadTasks();
    });
    host.appendChild(scope);
  }
}

function botName(id) {
  if (!id) return "unassigned";
  return state.bots.find((b) => b.id === id)?.name || id;
}

function assigneeOptions(selected) {
  const opts = ['<option value="">unassigned</option>'];
  for (const bot of state.bots) {
    const sel = bot.id === selected ? " selected" : "";
    opts.push(`<option value="${esc(bot.id)}"${sel}>${esc(bot.name)}</option>`);
  }
  return opts.join("");
}

function populateAssigneeSelects() {
  const newSel = $("task-new-assignee");
  if (newSel) newSel.innerHTML = assigneeOptions();
  const filterSel = $("library-agent-filter");
  if (filterSel) {
    const current = state.libraryAgentFilter || "";
    filterSel.innerHTML =
      '<option value="">All agents</option>' +
      state.bots.map((b) =>
        `<option value="${esc(b.id)}"${b.id === current ? " selected" : ""}>${esc(b.name)}</option>`)
        .join("");
  }
}

function renderTaskList() {
  const host = $("tasks-list");
  host.innerHTML = "";
  const tasks = state.tasks.filter(taskMatchesFilter);
  if (tasks.length === 0) {
    host.innerHTML = '<div class="lf-empty">No tasks here.<small>Agents add tasks as they work; you can too.</small></div>';
    return;
  }
  for (const task of tasks) {
    const card = document.createElement("div");
    card.className = "lf-task-card" + (task.id === state.selectedTaskId ? " is-active" : "");
    card.dataset.id = task.id;
    const age = relTime(task.updated_at);
    card.innerHTML = `
      <div class="lf-task-top">
        <span class="lf-task-glyph">${TASK_GLYPH[task.status] || "○"}</span>
        <span class="lf-task-title"></span>
        <span class="lf-task-pri ${esc(task.priority)}">${esc(task.priority)}</span>
      </div>
      <div class="lf-task-meta">
        <span class="lf-task-chip">${esc(botName(task.assigned_bot_id))}</span>
        <span>${esc(task.status.replace("_", " "))}</span>
        <span>${esc(age)}</span>
        <span>${task.progress || 0}%</span>
      </div>
      <div class="lf-task-progress"><div style="width:${task.progress || 0}%"></div></div>`;
    card.querySelector(".lf-task-title").textContent = task.title;
    card.addEventListener("click", () => openTaskDetail(task.id));
    host.appendChild(card);
  }
}

function relTime(iso) {
  try {
    const then = new Date(iso).getTime();
    const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  } catch { return ""; }
}

async function openTaskDetail(taskId) {
  state.selectedTaskId = taskId;
  renderTaskList();
  const body = await api(`/api/fleet/tasks/${taskId}`);
  const task = body.task;
  $("task-detail").hidden = false;
  $("task-detail-title").value = task.title;
  $("task-detail-description").value = task.description || "";
  $("task-detail-priority").value = task.priority;
  $("task-detail-assignee").innerHTML = assigneeOptions(task.assigned_bot_id || "");
  $("task-detail-progress").value = task.progress || 0;
  $("task-progress-label").textContent = String(task.progress || 0);
  renderTaskStatusButtons(task);
  renderTaskEvents(body.events || []);
}

const TASK_STATUS_FLOW = [["pending", "pending"], ["in_progress", "in progress"],
                          ["completed", "complete"], ["failed", "fail"],
                          ["cancelled", "cancel"]];

function renderTaskStatusButtons(task) {
  const host = $("task-detail-status");
  host.innerHTML = "";
  for (const [status, label] of TASK_STATUS_FLOW) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "lf-ghost" + (task.status === status ? " is-active" : "");
    b.textContent = label;
    b.style.cssText = task.status === status ? "border-color: var(--accent); color: var(--accent);" : "";
    b.addEventListener("click", async () => {
      await api(`/api/fleet/tasks/${task.id}/update`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await loadTasks();
      await openTaskDetail(task.id);
    });
    host.appendChild(b);
  }
}

function renderTaskEvents(events) {
  const host = $("task-events");
  host.innerHTML = "";
  if (!events.length) {
    host.innerHTML = '<div class="lf-muted">no history yet</div>';
    return;
  }
  for (const e of events) {
    const div = document.createElement("div");
    const actor = e.actor === "user" ? "you" : (botName(e.actor) || e.actor);
    const when = relTime(e.created_at);
    let text = "";
    if (e.event === "status") text = `${e.from_status || "?"} → ${e.to_status}`;
    else if (e.event === "created") text = `created${e.note ? ` — ${e.note}` : ""}`;
    else if (e.event === "reassigned") text = `reassigned ${e.note}`;
    else if (e.event === "note") text = e.note;
    else if (e.event === "progress") text = e.note;
    else if (e.event === "delegated") text = e.note;
    else text = `${e.event}${e.note ? ` — ${e.note}` : ""}`;
    div.innerHTML = `<b></b> <span></span> <span class="lf-muted"></span>`;
    div.querySelector("b").textContent = actor;
    div.querySelector("span").textContent = text;
    div.querySelector("span.lf-muted").textContent = ` · ${when}`;
    host.appendChild(div);
  }
}

async function wireTasksView() {
  $("ws-tasks-btn").addEventListener("click", () => selectTasksView());
  $("ws-library-btn").addEventListener("click", () => selectLibraryView());

  $("task-new-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const title = $("task-new-title").value.trim();
    if (!title) return;
    const assigned = $("task-new-assignee").value;
    try {
      await api("/api/fleet/tasks", {
        method: "POST",
        body: JSON.stringify({
          title,
          priority: $("task-new-priority").value,
          assigned_bot_id: assigned || undefined,
        }),
      });
      $("task-new-title").value = "";
      await loadTasks();
      toast("Task created.");
    } catch (err) { toast(err.message); }
  });

  $("task-detail-progress").addEventListener("input", () => {
    $("task-progress-label").textContent = String($("task-detail-progress").value);
  });

  $("task-save").addEventListener("click", async () => {
    const id = state.selectedTaskId;
    if (!id) return;
    try {
      await api(`/api/fleet/tasks/${id}/update`, {
        method: "POST",
        body: JSON.stringify({
          title: $("task-detail-title").value,
          description: $("task-detail-description").value,
          priority: $("task-detail-priority").value,
          progress: Number($("task-detail-progress").value),
        }),
      });
      await api(`/api/fleet/tasks/${id}/assign`, {
        method: "POST",
        body: JSON.stringify({ assigned_bot_id: $("task-detail-assignee").value || null }),
      });
      await loadTasks();
      await openTaskDetail(id);
      toast("Task saved.");
    } catch (err) { toast(err.message); }
  });

  $("task-cancel-forever").addEventListener("click", async () => {
    const id = state.selectedTaskId;
    if (!id) return;
    if (!window.confirm("Delete this task and its history?")) return;
    await api(`/api/fleet/tasks/${id}/delete`, { method: "POST", body: "{}" });
    state.selectedTaskId = null;
    $("task-detail").hidden = true;
    await loadTasks();
    toast("Task deleted.");
  });
}

/* ---------------- library view (F2) ---------------- */

function humanBytes(n) {
  n = Number(n || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function fileIcon(name, mime) {
  const ext = String(name).split(".").pop()?.toLowerCase();
  if (/^(png|jpe?g|gif|webp|svg)$/.test(ext)) return "🖼";
  if (ext === "pdf") return "📕";
  if (/^(zip|tar|gz|7z)$/.test(ext)) return "🗜";
  if (/^(md|txt|rst)$/.test(ext)) return "📄";
  if (/^(py|js|ts|css|html|json|yaml|yml|sql|sh)$/.test(ext)) return "⌨";
  if (/^(csv|xlsx?)$/.test(ext)) return "📊";
  return "▤";
}

async function loadLibrary() {
  const params = new URLSearchParams();
  if (state.libraryAgentFilter) params.set("bot_id", state.libraryAgentFilter);
  const body = await api(`/api/fleet/library?${params}`);
  state.files = body.files || [];
  renderLibraryGrid();
  renderWsRailCounts();
  populateAssigneeSelects();
  const usage = $("library-usage");
  if (state.libraryAgentFilter) {
    usage.textContent = `${humanBytes(body.usage_bytes)} of 25 MB`;
  } else {
    usage.textContent = `${state.files.length} files`;
  }
}

function renderLibraryGrid() {
  const host = $("library-grid");
  host.innerHTML = "";
  if (state.files.length === 0) {
    host.innerHTML = '<div class="lf-empty">Library is empty.<small>Agents save deliverables here via save_file.</small></div>';
    return;
  }
  for (const file of state.files) {
    const card = document.createElement("div");
    card.className = "lf-file-card" + (file.id === state.selectedFileId ? " is-active" : "");
    card.innerHTML = `
      <span class="lf-file-ic">${fileIcon(file.name, file.mime)}</span>
      <span class="lf-file-name"></span>
      <span class="lf-file-meta">
        <span>${esc(humanBytes(file.size))}</span>
        <span>${esc(relTime(file.created_at))}</span>
        <span>${esc(botName(file.bot_id))}</span>
      </span>`;
    card.querySelector(".lf-file-name").textContent = file.name;
    card.addEventListener("click", () => openFileDetail(file.id));
    host.appendChild(card);
  }
}

async function openFileDetail(fileId) {
  state.selectedFileId = fileId;
  renderLibraryGrid();
  const body = await api(`/api/fleet/library/${fileId}`);
  const file = body.file;
  $("library-detail").hidden = false;
  $("library-detail-name").textContent = file.name;
  $("library-detail-meta").innerHTML = `
    <div>owner: <b>${esc(botName(file.bot_id))}</b> <span class="lf-muted">(${esc(file.bot_id)})</span></div>
    <div>size: <b>${esc(humanBytes(file.size))}</b></div>
    <div>mime: <b>${esc(file.mime)}</b></div>
    <div>sha256: <b>${esc((file.sha256 || "").slice(0, 16))}…</b></div>
    <div>saved: <b>${esc(new Date(file.created_at).toLocaleString())}</b></div>
    <div>source: <b>${esc(file.source)}</b>${file.task_id ? ` · task <b>${esc(file.task_id)}</b>` : ""}</div>`;
  $("library-download").href =
    `/api/fleet/library/${fileId}/download?t=${encodeURIComponent(state.token)}`;
  renderFilePreview(file);
}

async function renderFilePreview(file) {
  const host = $("library-preview");
  host.innerHTML = "";
  const url = `/api/fleet/library/${file.id}/preview?t=${encodeURIComponent(state.token)}`;
  const mime = String(file.mime || "");
  if (mime.startsWith("image/")) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = file.name;
    host.appendChild(img);
    return;
  }
  if (mime === "application/pdf") {
    const frame = document.createElement("iframe");
    frame.src = url;
    frame.title = file.name;
    host.appendChild(frame);
    return;
  }
  if (/^(text\/|application\/(json|xml|yaml)|image\/svg)/.test(mime) || /\.(txt|md|py|js|ts|css|html|json|yaml|yml|sh|sql|csv|xml)$/i.test(file.name)) {
    try {
      const resp = await fetch(url);
      const text = await resp.text();
      const pre = document.createElement("pre");
      pre.textContent = text.slice(0, 100_000);
      host.appendChild(pre);
      return;
    } catch {
      // fall through to the generic message
    }
  }
  const div = document.createElement("div");
  div.className = "lf-muted";
  div.textContent = "No inline preview for this file — use Download.";
  host.appendChild(div);
}

function wireLibraryView() {
  $("library-agent-filter").addEventListener("change", async () => {
    state.libraryAgentFilter = $("library-agent-filter").value || null;
    state.selectedFileId = null;
    $("library-detail").hidden = true;
    await loadLibrary();
  });
  $("library-delete").addEventListener("click", async () => {
    const fileId = state.selectedFileId;
    if (!fileId) return;
    if (!window.confirm("Delete this file from the Library?")) return;
    await api(`/api/fleet/library/${fileId}/delete`, { method: "POST", body: "{}" });
    state.selectedFileId = null;
    $("library-detail").hidden = true;
    await loadLibrary();
    toast("File deleted.");
  });
  $("library-upload-input").addEventListener("change", async () => {
    const input = $("library-upload-input");
    const file = input.files && input.files[0];
    if (!file) return;
    const botId = state.libraryAgentFilter || state.bots[0]?.id;
    if (!botId) { toast("Create an agent first — library files are agent-owned."); return; }
    if (file.size > 2 * 1024 * 1024) { toast("Max 2 MB per file."); return; }
    const b64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    try {
      await api("/api/fleet/library", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, content_base64: b64,
                               bot_id: botId }),
      });
      await loadLibrary();
      toast(`Saved ${file.name} to ${botName(botId)}'s library.`);
    } catch (err) { toast(err.message); }
    input.value = "";
  });
}

/* ---------------- routines view (F4) ---------------- */

const TIMEZONES = [
  "UTC", "Europe/London", "Europe/Berlin", "Europe/Paris", "Europe/Madrid",
  "Europe/Amsterdam", "Europe/Rome", "Europe/Stockholm", "Europe/Helsinki",
  "Europe/Athens", "Europe/Istanbul", "Europe/Moscow",
  "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
  "America/Toronto", "America/Vancouver", "America/Sao_Paulo", "America/Argentina/Buenos_Aires",
  "America/Mexico_City", "America/Phoenix", "America/Anchorage",
  "Asia/Tokyo", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore", "Asia/Seoul",
  "Asia/Dubai", "Asia/Kolkata", "Asia/Jakarta",
  "Australia/Sydney", "Australia/Melbourne", "Australia/Perth", "Pacific/Auckland",
  "Pacific/Fiji", "Africa/Cairo", "Africa/Johannesburg",
];

function tzOptions(selected) {
  return TIMEZONES.map((tz) =>
    `<option value="${tz}"${tz === selected ? " selected" : ""}>${tz}</option>`).join("");
}

function agentOptions(selected) {
  const opts = [];
  for (const bot of state.bots) {
    const sel = bot.id === selected ? " selected" : "";
    opts.push(`<option value="${esc(bot.id)}"${sel}>${esc(bot.name)}</option>`);
  }
  return opts.join("");
}

function routineState(routine) {
  if (routine.running) return { key: "is-running", label: "running" };
  if (routine.paused) return { key: "is-paused", label: "paused" };
  if (!routine.enabled) return { key: "is-disabled", label: "disabled" };
  return { key: "is-on", label: "enabled" };
}

function fmtWhen(iso) {
  if (!iso) return "never";
  try {
    const d = new Date(iso);
    return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  } catch { return iso; }
}

async function selectRoutinesView() {
  state.view = "routines";
  state.selectedRoutineId = null;
  $("routine-detail").hidden = true;
  syncViewChrome();
  await loadRoutines();
}

async function loadRoutines() {
  const body = await api("/api/fleet/routines");
  state.routines = body.routines || [];
  renderRoutineList();
  renderWsRailCounts();
  populateRoutineCreateSelects();
}

function renderWsRailCounts() {
  const activeTasks = state.tasks.filter(
    (t) => t.status === "pending" || t.status === "in_progress").length;
  $("ws-tasks-count").textContent = activeTasks > 0 ? `${activeTasks} open` : "all clear";
  $("ws-library-count").textContent =
    state.files.length ? `${state.files.length} file${state.files.length === 1 ? "" : "s"}` : "empty";
  const activeRoutines = state.routines.filter((r) => r.enabled && !r.paused).length;
  $("ws-routines-count").textContent =
    activeRoutines > 0 ? `${activeRoutines} active` : "idle";
}

function populateRoutineCreateSelects() {
  $("routine-agent").innerHTML =
    state.bots.map((b) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("")
    || '<option value="">no agents</option>';
  $("routine-timezone").innerHTML = tzOptions(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
}

function renderRoutineList() {
  const host = $("routines-list");
  host.innerHTML = "";
  if (state.routines.length === 0) {
    host.innerHTML = '<div class="lf-empty">No routines yet.<small>Agents can do scheduled work — cron-driven, timezone-aware.</small></div>';
    return;
  }
  for (const routine of state.routines) {
    const rstate = routineState(routine);
    const card = document.createElement("div");
    card.className = "lf-routine-card" + (routine.id === state.selectedRoutineId ? " is-active" : "");
    card.innerHTML = `
      <div class="lf-routine-top">
        <span class="lf-routine-state ${rstate.key}"></span>
        <span class="lf-routine-name"></span>
        <span class="lf-routine-cron"></span>
      </div>
      <div class="lf-routine-meta">
        <span class="lf-task-chip">${esc(botName(routine.bot_id))}</span>
        <span>${esc(rstate.label)}</span>
        <span>next: ${esc(fmtWhen(routine.next_run_at))}</span>
        <span>last: ${esc(fmtWhen(routine.last_run_at))} ${routine.last_status ? "· " + esc(routine.last_status) : ""}</span>
      </div>`;
    card.querySelector(".lf-routine-name").textContent = routine.name;
    card.querySelector(".lf-routine-cron").textContent = routine.cron_expr;
    card.addEventListener("click", () => openRoutineDetail(routine.id));
    host.appendChild(card);
  }
}

async function openRoutineDetail(routineId) {
  state.selectedRoutineId = routineId;
  renderRoutineList();
  const body = await api(`/api/fleet/routines/${routineId}`);
  const routine = body.routine;
  $("routine-detail").hidden = false;
  $("routine-detail-name").textContent = routine.name;
  const rstate = routineState(routine);
  const stateEl = $("routine-detail-state");
  stateEl.textContent = rstate.label;
  stateEl.className = "lf-routine-chip " +
    (rstate.key === "is-on" ? "is-ok" : rstate.key === "is-paused" ? "is-warn" : "");
  $("routine-detail-agent").innerHTML = agentOptions(routine.bot_id);
  $("routine-detail-prompt").value = routine.prompt;
  $("routine-detail-cron").value = routine.cron_expr;
  $("routine-detail-timezone").innerHTML = tzOptions(routine.timezone);
  $("routine-detail-meta").innerHTML = `
    <div>next run: <b>${esc(fmtWhen(routine.next_run_at))}</b></div>
    <div>last run: <b>${esc(fmtWhen(routine.last_run_at))}</b>${routine.last_status ? ` · <b>${esc(routine.last_status)}</b>` : ""}</div>
    ${routine.last_summary ? `<div>last result: <b>${esc(routine.last_summary.slice(0, 200))}</b></div>` : ""}
    ${routine.paused && routine.pause_reason ? `<div>paused: <b>${esc(routine.pause_reason)}</b></div>` : ""}
    <div>timezone: <b>${esc(routine.timezone)}</b></div>`;
  $("routine-enable-toggle").textContent = routine.enabled ? "Disable" : "Enable";
  $("routine-pause-toggle").textContent = routine.paused ? "Resume" : "Pause";
  $("routine-run-now").disabled = routine.paused || !routine.enabled || routine.running;
  renderRoutineRuns(body.runs || []);
}

function renderRoutineRuns(runs) {
  const host = $("routine-runs");
  host.innerHTML = "";
  if (!runs.length) {
    host.innerHTML = '<div class="lf-muted">no executions yet</div>';
    return;
  }
  for (const run of runs) {
    const div = document.createElement("div");
    div.className = "lf-run-row";
    const when = esc(fmtWhen(run.started_at || run.scheduled_at));
    div.innerHTML = `
      <span class="lf-run-status ${esc(run.status)}">${esc(run.status.replace("_", " "))}</span>
      <span class="lf-run-when">${when}</span>
      <span>${run.task_id ? `task ${esc(run.task_id)}` : "—"}</span>`;
    if (run.error) {
      const err = document.createElement("div");
      err.className = "lf-run-err";
      err.style.gridColumn = "1 / -1";
      err.textContent = run.error;
      host.appendChild(div);
      host.appendChild(err);
      continue;
    }
    if (run.summary) {
      const sum = document.createElement("div");
      sum.style.gridColumn = "1 / -1";
      sum.style.color = "var(--muted)";
      sum.textContent = run.summary.slice(0, 160);
      div.appendChild(sum);
    }
    host.appendChild(div);
  }
}

async function wireRoutinesView() {
  $("ws-routines-btn").addEventListener("click", () => selectRoutinesView());

  $("routine-create-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("routine-name").value.trim();
    const cron = $("routine-cron").value.trim();
    const prompt = $("routine-prompt").value.trim();
    const botId = $("routine-agent").value;
    if (!name || !botId || !prompt) { toast("Name, agent and prompt are required."); return; }
    try {
      const body = await api("/api/fleet/routines", {
        method: "POST",
        body: JSON.stringify({
          name, bot_id: botId, prompt,
          cron_expr: cron,
          timezone: $("routine-timezone").value || "UTC",
        }),
      });
      $("routine-name").value = "";
      $("routine-prompt").value = "";
      await loadRoutines();
      await openRoutineDetail(body.routine.id);
      toast("Routine created.");
    } catch (err) { toast(err.message); }
  });

  $("routine-run-now").addEventListener("click", async () => {
    const id = state.selectedRoutineId;
    if (!id) return;
    try {
      await api(`/api/fleet/routines/${id}/run`, { method: "POST", body: "{}" });
      toast("Routine started.");
      setTimeout(() => openRoutineDetail(id), 1200);
    } catch (err) { toast(err.status === 409 ? "Already running (or paused/disabled)." : err.message); }
  });

  $("routine-enable-toggle").addEventListener("click", async () => {
    const id = state.selectedRoutineId;
    if (!id) return;
    const routine = state.routines.find((r) => r.id === id);
    const enable = !routine?.enabled;
    await api(`/api/fleet/routines/${id}/${enable ? "enable" : "disable"}`,
              { method: "POST", body: "{}" });
    await loadRoutines();
    await openRoutineDetail(id);
  });

  $("routine-pause-toggle").addEventListener("click", async () => {
    const id = state.selectedRoutineId;
    if (!id) return;
    const routine = state.routines.find((r) => r.id === id);
    const pause = !routine?.paused;
    await api(`/api/fleet/routines/${id}/${pause ? "pause" : "resume"}`, {
      method: "POST",
      body: pause ? JSON.stringify({ reason: "paused from UI" }) : "{}",
    });
    await loadRoutines();
    await openRoutineDetail(id);
  });

  $("routine-save").addEventListener("click", async () => {
    const id = state.selectedRoutineId;
    if (!id) return;
    try {
      await api(`/api/fleet/routines/${id}/update`, {
        method: "POST",
        body: JSON.stringify({
          bot_id: $("routine-detail-agent").value,
          prompt: $("routine-detail-prompt").value,
          cron_expr: $("routine-detail-cron").value.trim(),
          timezone: $("routine-detail-timezone").value,
        }),
      });
      await loadRoutines();
      await openRoutineDetail(id);
      toast("Routine saved.");
    } catch (err) { toast(err.message); }
  });

  $("routine-delete").addEventListener("click", async () => {
    const id = state.selectedRoutineId;
    if (!id) return;
    if (!window.confirm("Delete this routine and its run history?")) return;
    await api(`/api/fleet/routines/${id}/delete`, { method: "POST", body: "{}" });
    state.selectedRoutineId = null;
    $("routine-detail").hidden = true;
    await loadRoutines();
    toast("Routine deleted.");
  });
}

/* ---------------- rows ---------------- */

function appendRowNode(row) {
  const holder = document.createElement("div");
  if (row.kind === "message") {
    const role = row.body.role || "assistant";
    const delegatedFrom = row.body.delegated_from;
    if (role === "user" && delegatedFrom) {
      holder.className = "lf-msg user delegated";
      const meta = document.createElement("span");
      meta.className = "lf-bubble-role";
      meta.textContent = `delegated from ${delegatedFrom.name || delegatedFrom.id}`;
      const text = document.createElement("div");
      text.className = "lf-bubble-text";
      text.textContent = row.body.content || "";
      holder.append(meta, text);
      rowsEl.appendChild(holder);
      rowsEl.scrollTop = rowsEl.scrollHeight;
      return { node: holder, inlineStep: false };
    }
    holder.className = `lf-msg ${role}`;
    const meta = document.createElement("span");
    meta.className = "lf-bubble-role";
    let badge = "";
    if (role !== "user") {
      const engine = row.body.engine || "";
      const model = (row.body.model || "").trim();
      if (engine === "echo") badge = " · echo (test)";
      else if (engine) badge = ` · ${engine}${model ? " / " + model : ""}`;
    }
    meta.textContent = (role === "user" ? "you" : (selectedBot()?.name || "agent")) + badge;
    const text = document.createElement("div");
    text.className = "lf-bubble-text";
    text.textContent = row.body.content || "";
    holder.append(meta, text);
  } else if (row.kind === "step") {
    const stepStatus = row.body.status === "error" ? "is-error"
      : row.body.status === "done" ? "is-done" : "is-running";
    holder.className = `lf-step ${stepStatus}`;
    holder.dataset.stepName = row.body.name || "";
    holder.innerHTML = `<span class="lf-step-dot"></span><span class="lf-step-text"></span>`;
    holder.querySelector(".lf-step-text").textContent =
      `${row.body.name || "step"} — ${row.body.detail || ""}`;
    return { node: holder, inlineStep: true };
  } else if (row.kind === "turn_end") {
    holder.className = "lf-turn-end";
    const secs = ((row.body.duration_ms || 0) / 1000).toFixed(1);
    holder.textContent = `turn complete · ${secs}s · ${row.body.num_steps || 0} steps`;
  } else if (row.kind === "notice") {
    holder.className = "lf-turn-end";
    holder.textContent = row.body.text || "";
  }
  rowsEl.appendChild(holder);
  rowsEl.scrollTop = rowsEl.scrollHeight;
  return { node: holder, inlineStep: row.kind === "step" };
}

/* ---------------- live token streaming (ephemeral) ---------------- */

function handleStreamFrame(row) {
  if (row.bot_id !== state.selectedId) return;
  state.streamBuf = (state.streamBuf || "") + (row.delta || "");
  if (!state.streamNode) {
    const holder = document.createElement("div");
    holder.className = "lf-msg assistant streaming";
    const meta = document.createElement("span");
    meta.className = "lf-bubble-role";
    meta.textContent = (selectedBot()?.name || "agent") + " · streaming";
    const text = document.createElement("div");
    text.className = "lf-bubble-text";
    holder.append(meta, text);
    rowsEl.appendChild(holder);
    state.streamNode = { holder, text };
  }
  state.streamNode.text.textContent = state.streamBuf;
  rowsEl.scrollTop = rowsEl.scrollHeight;
}

function clearStreamBubble() {
  state.streamBuf = "";
  if (state.streamNode) {
    state.streamNode.holder.remove();
    state.streamNode = null;
  }
}

function flushPendingSteps(foldTurnEnd) {
  if (state.pendingSteps.length === 0) return null;
  const steps = state.pendingSteps.splice(0, state.pendingSteps.length);
  const wrap = document.createElement("div");
  wrap.className = "lf-steps-fold-wrap";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "lf-steps-fold";
  const label = foldTurnEnd
    ? `Worked for ${((foldTurnEnd.body.duration_ms || 0) / 1000).toFixed(1)}s · ${steps.length} steps`
    : `worked · ${steps.length} steps`;
  toggle.innerHTML = `<span class="lf-fold-caret">▸</span> ${label}`;
  const list = document.createElement("div");
  list.className = "lf-steps-list";
  list.hidden = true;
  for (const s of steps) list.appendChild(s.node);
  toggle.addEventListener("click", () => {
    list.hidden = !list.hidden;
    toggle.querySelector(".lf-fold-caret").textContent = list.hidden ? "▸" : "▾";
  });
  wrap.append(toggle, list);
  rowsEl.appendChild(wrap);
  rowsEl.scrollTop = rowsEl.scrollHeight;
  return wrap;
}

function handleRow(row) {
  if (row && row.seq && row.seq > state.lastSeq) {
    state.lastSeq = row.seq;
  }
  const belongs = row.bot_id === state.selectedId;

  // activity accounting for the rail + header
  if (row.kind === "step") {
    const delta = row.body?.status === "running" ? 1 : (row.body?.status === "done" ? -1 : 0);
    state.botActivity[row.bot_id] = Math.max(0, (state.botActivity[row.bot_id] || 0) + delta);
    renderRail();
    if (belongs) renderSelectedHeader();
  } else if (row.kind === "turn_end") {
    if (row.bot_id) state.botActivity[row.bot_id] = 0;
    renderRail();
    if (belongs) renderSelectedHeader();
    refreshWorkspaceCounts();
  }

  if (!belongs) return;

  if (row.kind === "step") {
    const delegated = row.body && row.body.delegated && row.body.name === "send_to_bot";
    if (delegated) {
      flushPendingSteps(null);
      appendDelegateChip(row);
      return;
    }
    const r = appendRowNode(row);
    state.pendingSteps.push(r);
    return;
  }
  if (row.kind === "approval") {
    flushPendingSteps(row.kind === "turn_end" ? row : null);
    upsertApprovalRow(row);
    return;
  }
  if (row.kind === "message"
      && row.body && row.body.role === "assistant") {
    clearStreamBubble(); // persisted reply takes over from the stream bubble
  }
  if (row.kind === "turn_end") {
    clearStreamBubble();
  }
  flushPendingSteps(row.kind === "turn_end" ? row : null);
  appendRowNode(row);
}

async function loadRows() {
  if (!state.selectedId) return;
  const body = await api(`/api/fleet/bots/${state.selectedId}/rows`);
  for (const row of body.rows || []) handleRow(row);
}

/* ---------------- SSE ---------------- */

function connectSSE() {
  if (state.es) state.es.close();
  const url = `/api/fleet/events?t=${encodeURIComponent(state.token)}`;
  try {
    state.es = new EventSource(url);
  } catch (err) {
    console.error("SSE connect failed", err);
    return;
  }
  state.es.addEventListener("row", (ev) => {
    try {
      const row = JSON.parse(ev.data);
      if (row && row.type === "stream") {
        handleStreamFrame(row);
        return;
      }
      if (row.group_id) {
        handleGroupRow(row);
        refreshWorkspaceCounts();
        return;
      }
      handleRow(row);
    } catch (err) {
      console.error("bad row", err);
    }
  });
  state.es.onerror = () => {
    // EventSource auto-reconnects; surface transient state in the header
    $("status-mid").textContent = "reconnecting…";
  };
  state.es.onopen = () => {
    $("status-mid").textContent = "ready";
    // rows that landed while we were disconnected are absent from the DOM
    refreshRowsAfterReconnect();
  };
}

async function refreshRowsAfterReconnect() {
  // SSE drops are silent; recover anything that landed while we were down
  if (state.view === "group" && state.selectedGroupId) {
    try {
      const body = await api(
        `/api/fleet/groups/${state.selectedGroupId}/rows?after=${state.lastGroupSeq || 0}`);
      for (const row of body.rows || []) handleGroupRow(row);
    } catch (err) {
      console.error("SSE group catch-up failed", err);
    }
  }
  if (!state.selectedId) return;
  try {
    const body = await api(
      `/api/fleet/bots/${state.selectedId}/rows?after=${state.lastSeq || 0}`);
    for (const row of body.rows || []) handleRow(row);
  } catch (err) {
    console.error("SSE catch-up failed", err);
  }
}

/* ---------------- composing ---------------- */

async function sendMessage(ev) {
  if (ev) ev.preventDefault();
  const text = composerInput.value.trim();
  if (!text || state.sending) return;
  if (state.view === "group") {
    if (!state.selectedGroupId) return;
    state.sending = true;
    composerInput.disabled = true;
    sendBtn.disabled = true;
    try {
      await sendGroupMessage(text);
      composerInput.value = "";
      composerInput.style.height = "auto";
    } catch (err) {
      toast(err.status === 409 ? "Group round already running — wait for it to finish" :
               err.message || "failed to send");
    } finally {
      state.sending = false;
      composerInput.disabled = false;
      sendBtn.disabled = false;
      composerInput.focus();
    }
    return;
  }
  const bot = selectedBot();
  if (!bot) return;
  state.sending = true;
  composerInput.disabled = true;
  sendBtn.disabled = true;
  try {
    await api(`/api/fleet/bots/${bot.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: text }),
    });
    composerInput.value = "";
    composerInput.style.height = "auto";
  } catch (err) {
    toast(err.status === 409 ? "Agent is busy — try again in a moment" :
             err.message || "failed to send");
  } finally {
    state.sending = false;
    composerInput.disabled = false;
    sendBtn.disabled = false;
    composerInput.focus();
  }
}

/* ---------------- permissions tab ---------------- */

async function loadPermissions() {
  const bot = selectedBot();
  const listEl = $("perm-list");
  const auditEl = $("perm-audit");
  const nameEl = $("perm-bot-name");
  if (!listEl || !auditEl || !nameEl) return;
  if (!bot) {
    listEl.innerHTML = '<div class="lf-empty">Pick an agent to inspect its policies.</div>';
    auditEl.innerHTML = "";
    nameEl.textContent = "no agent selected";
    return;
  }
  nameEl.textContent = bot.name;
  try {
    const [policiesBody, auditBody] = await Promise.all([
      api(`/api/fleet/bots/${bot.id}/policies`),
      api(`/api/fleet/bots/${bot.id}/audit?limit=12`),
    ]);
    renderPolicyList(listEl, bot, policiesBody.policies || []);
    renderAuditList(auditEl, auditBody.audit || []);
  } catch (err) {
    listEl.innerHTML = `<div class="lf-empty">Permissions unavailable: ${err.message}</div>`;
    auditEl.textContent = "";
  }
}

function renderPolicyList(host, bot, policies) {
  host.innerHTML = "";
  if (policies.length === 0) {
    host.innerHTML = '<div class="lf-empty">No standing policies.<small>Tools ask inline in the conversation.</small></div>';
    return;
  }
  for (const policy of policies) {
    const row = document.createElement("div");
    row.className = "lf-policy";
    const badge = policy.decision === "always" ? "always allowed" : "never allowed";
    row.innerHTML = `
      <span class="lf-policy-badge is-${esc(policy.decision)}">${badge}</span>
      <span class="lf-policy-tool"></span>
      <span class="lf-policy-meta">${new Date(policy.updated_at || policy.created_at).toLocaleString()}</span>
      <button type="button" class="lf-ghost lf-policy-revoke">Revoke</button>`;
    row.querySelector(".lf-policy-tool").textContent = policy.tool_name;
    row.querySelector(".lf-policy-revoke").addEventListener("click", async () => {
      try {
        await api(`/api/fleet/bots/${bot.id}/policies/revoke`, {
          method: "POST",
          body: JSON.stringify({ tool_name: policy.tool_name }),
        });
        toast(`Policy revoked for ${policy.tool_name}.`);
        loadPermissions();
      } catch (err) { toast(err.message); }
    });
    host.appendChild(row);
  }
}

function renderAuditList(host, entries) {
  host.innerHTML = "";
  if (entries.length === 0) {
    host.innerHTML = '<div class="lf-empty">No decisions recorded yet.</div>';
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "lf-audit-row";
    const when = new Date(entry.created_at).toLocaleString();
    const outcome = entry.outcome ? ` → ${entry.outcome}` : "";
    const decision = entry.decision ? ` (${entry.decision})` : "";
    row.innerHTML = `
      <span class="lf-audit-when">${esc(when)}</span>
      <span class="lf-audit-what">${esc(entry.tool_name)} · ${esc(entry.event)}${esc(decision)}${esc(outcome)}</span>`;
    host.appendChild(row);
  }
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------------- panel tabs ---------------- */

function bindTabs() {
  document.querySelectorAll(".lf-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      document.querySelectorAll(".lf-tab").forEach((b) =>
        b.classList.toggle("is-active", b === btn));
      document.querySelectorAll(".lf-page").forEach((p) =>
        p.classList.toggle("is-active", p.id === `page-${target}`));
      if (target === "permissions") loadPermissions();
      if (target === "tasks") {
        const bot = selectedBot();
        if (bot) renderAgentTasks(bot);
      }
    });
  });
}

function syncPanelFromBot(bot) {
  if (!bot) return;
  paintAvatar($("panel-avatar"), bot);
  $("studio-name").value = bot.name || "";
  $("studio-role").value = bot.role || "";
  $("hue-slider").value = bot.avatar_hue ?? 210;
  $("notes-text").value = bot.notes || "";
  $("notes-count").textContent = String((bot.notes || "").length);
  $("engine-model").value = bot.model || "";
  const provSel = $("engine-provider");
  if ([...provSel.options].some((o) => o.value === bot.provider)) {
    provSel.value = bot.provider;
  } else {
    provSel.value = "auto";
  }
  renderEngineStatus(bot.provider);
  renderAgentTasks(bot);
}

function renderEngineStatus(provider) {
  const host = $("engine-status");
  host.textContent = "";
  const summary = (window.__providers || []).find((p) =>
    p.name === provider) || null;
  if (provider === "auto") {
    const autoChain = ["openrouter", "google", "nvidia", "openai-compatible"];
    const configured = (window.__providers || []).filter(
      (p) => autoChain.includes(p.name) && p.configured);
    if (configured.length > 0) {
      host.innerHTML = `<span class="ok">● auto</span> — ${configured.length} provider(s) configured; follows Keel's fallback chain (OpenRouter → Google → NIM).`;
    } else {
      host.innerHTML = `<span class="miss">● auto</span> — no providers configured; the agent cannot run. Set a key first (<code>keel provider list</code>).`;
    }
    return;
  }
  if (summary && summary.configured) {
    host.innerHTML = summary.session
      ? `<span class="ok">● configured</span> — session key in use (never stored).`
      : `<span class="ok">● configured</span> — key present (not stored by Fleet).`;
  } else {
    host.innerHTML = `<span class="miss">● not configured</span> — paste a key below, or set it in your shell (<code>keel provider list</code>).`;
  }
}

function fillModelDatalist(models) {
  const dl = $("engine-models");
  dl.innerHTML = "";
  for (const id of models || []) {
    const opt = document.createElement("option");
    opt.value = id;
    dl.appendChild(opt);
  }
}

async function validateSessionKey() {
  const provider = $("engine-provider").value;
  const status = $("engine-key-status");
  const input = $("engine-key");
  const key = input.value.trim();
  if (provider === "auto") {
    status.textContent = "Pick the specific provider first (not auto), then validate.";
    return;
  }
  const btn = $("engine-key-save");
  btn.disabled = true;
  status.textContent = key ? "Validating…" : "Loading models from your configured key…";
  try {
    if (key) {
      const body = await api("/api/fleet/providers/credential", {
        method: "POST",
        body: JSON.stringify({ name: provider, key }),
      });
      input.value = "";
      if (!body.ok) {
        status.textContent = `Key not accepted — ${body.detail || body.error}`;
        return;
      }
      fillModelDatalist(body.models);
      status.textContent = `Key accepted — ${body.model_count} models loaded for ${provider} (this session only).`;
      toast(`${provider}: ${body.model_count} models available.`);
    } else {
      input.value = "";
      const body = await api("/api/fleet/providers/catalog", {
        method: "POST",
        body: JSON.stringify({ name: provider }),
      });
      if (!body.ok) {
        status.textContent = `Models unavailable — ${body.detail || body.error}`;
        return;
      }
      fillModelDatalist(body.models);
      status.textContent = `${body.model_count} models loaded from key (${body.key_source}).`;
      toast(`${provider}: ${body.model_count} models available.`);
    }
    await loadProvidersIntoSelect();
    renderEngineStatus(provider);
  } catch (err) {
    input.value = "";
    status.textContent = `Validation failed — ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function clearSessionKey() {
  const provider = $("engine-provider").value;
  const status = $("engine-key-status");
  try {
    const body = await api("/api/fleet/providers/credential/clear", {
      method: "POST",
      body: JSON.stringify({ name: provider }),
    });
    if (!body.ok) {
      status.textContent = body.detail || "No session key to clear.";
      return;
    }
    fillModelDatalist([]);
    status.textContent = `Session key for ${provider} forgotten.`;
    toast(`Session key for ${provider} cleared.`);
    await loadProvidersIntoSelect();
    renderEngineStatus(provider);
  } catch (err) {
    status.textContent = err.message;
  }
}

async function loadProvidersIntoSelect() {
  try {
    const body = await api("/api/fleet/providers");
    window.__providers = body.providers || [];
    const select = $("engine-provider");
    select.innerHTML = "";
    const autoOpt = document.createElement("option");
    autoOpt.value = "auto";
    autoOpt.textContent = "auto (Keel chain)";
    select.appendChild(autoOpt);
    for (const provider of window.__providers) {
      const opt = document.createElement("option");
      opt.value = provider.name;
      opt.textContent = `${provider.name} ${provider.configured ? (provider.session ? "⦿ configured · session" : "⦿ configured") : "— not configured"}`;
      select.appendChild(opt);
    }
    const bot = selectedBot();
    if (bot) syncPanelFromBot(bot);
  } catch (err) {
    console.error("providers load failed", err);
  }
}

function wirePanelActions() {
  $("studio-save").addEventListener("click", async () => {
    const bot = selectedBot();
    if (!bot) return;
    try {
      const body = await api(`/api/fleet/bots/${bot.id}/update`, {
        method: "POST",
        body: JSON.stringify({
          name: $("studio-name").value,
          role: $("studio-role").value,
          avatar_hue: Number($("hue-slider").value),
        }),
      });
      Object.assign(bot, body.bot);
      renderRail();
      renderSelectedHeader();
      paintAvatar($("panel-avatar"), bot);
      toast("Agent updated.");
    } catch (err) { toast(err.message); }
  });

  $("hue-slider").addEventListener("input", () => {
    const bot = selectedBot();
    paintAvatar($("panel-avatar"),
                bot ? { ...bot, avatar_hue: Number($("hue-slider").value) } : bot);
  });

  $("delete-bot").addEventListener("click", async () => {
    const bot = selectedBot();
    if (!bot) return;
    if (!window.confirm(`Delete ${bot.name}? This removes its history for good.`)) return;
    try {
      await api(`/api/fleet/bots/${bot.id}/delete`, { method: "POST", body: "{}" });
      state.selectedId = null;
      await loadBots();
      toast("Agent deleted.");
    } catch (err) { toast(err.message); }
  });

  $("engine-save").addEventListener("click", async () => {
    const bot = selectedBot();
    if (!bot) return;
    try {
      const body = await api(`/api/fleet/bots/${bot.id}/update`, {
        method: "POST",
        body: JSON.stringify({
          provider: $("engine-provider").value,
          model: $("engine-model").value,
        }),
      });
      Object.assign(bot, body.bot);
      renderEngineStatus(bot.provider);
      toast("Engine saved.");
    } catch (err) { toast(err.message); }
  });

  $("engine-key-save").addEventListener("click", validateSessionKey);
  $("engine-key-clear").addEventListener("click", clearSessionKey);
  $("engine-key").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      validateSessionKey();
    }
  });

  $("engine-provider").addEventListener("change", () =>
    renderEngineStatus($("engine-provider").value));

  $("notes-save").addEventListener("click", async () => {
    const bot = selectedBot();
    if (!bot) return;
    try {
      const body = await api(`/api/fleet/bots/${bot.id}/update`, {
        method: "POST",
        body: JSON.stringify({ notes: $("notes-text").value }),
      });
      Object.assign(bot, body.bot);
      toast("Notes saved.");
    } catch (err) { toast(err.message); }
  });

  $("notes-text").addEventListener("input", () => {
    $("notes-count").textContent = String($("notes-text").value.length);
  });
}

function wireNewBot() {
  const form = $("newbot-form");
  $("new-bot-btn").addEventListener("click", () => {
    form.hidden = !form.hidden;
    if (!form.hidden) $("newbot-name").focus();
  });
  $("newbot-cancel").addEventListener("click", () => { form.hidden = true; });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("newbot-name").value.trim();
    const role = $("newbot-role").value.trim();
    const engine = $("newbot-engine").value;
    if (!name) return;
    try {
      const body = await api("/api/fleet/bots", {
        method: "POST",
        body: JSON.stringify({ name, role, engine }),
      });
      const engineMeta = body.bot.engine === "provider" ? "provider" : "scripted test bot";
      form.hidden = true;
      $("newbot-name").value = "";
      $("newbot-role").value = "";
      await loadBots(body.bot.id);
      const sel = selectedBot();
      if (sel) syncPanelFromBot(sel);
      toast(`${body.bot.name} joined the fleet (${engineMeta}).`);
    } catch (err) { toast(err.message); }
  });
}

function wireComposer() {
  $("composer-form").addEventListener("submit", sendMessage);
  composerInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendMessage(ev);
    }
  });
  composerInput.addEventListener("input", () => {
    composerInput.style.height = "auto";
    composerInput.style.height = Math.min(240, composerInput.scrollHeight) + "px";
  });
}

function wirePanelToggle() {
  $("panel-toggle").addEventListener("click", () => {
    if (window.innerWidth <= 1100) {
      panelEl.classList.toggle("open");
    } else {
      const visible = window.getComputedStyle(panelEl).display !== "none";
      panelEl.style.display = visible ? "none" : "flex";
    }
  });
}

/* ---------------- boot ---------------- */

async function boot() {
  bootToken();
  bindTabs();
  wirePanelToggle();
  wirePanelActions();
  wireNewBot();
  wireNewGroup();
  wireTasksView();
  wireLibraryView();
  wireRoutinesView();
  wireComposer();
  try {
    await loadProvidersIntoSelect();
    await loadBots();
    await loadGroups();
  } catch (err) {
    $("status-mid").textContent = "connection error";
    toast(`Fleet failed to load: ${err.message}`);
    return;
  }
  connectSSE();
  renderSelectedHeader();
  if (state.selectedId && state.view === "agent") {
    await loadRows();
  } else if (!state.bots.length && !state.groups.length) {
    rowsEl.innerHTML = '<div class="lf-empty">No agents yet.<small>Create your first agent with the + button.</small></div>';
  }
  const bot = selectedBot();
  if (bot) syncPanelFromBot(bot);
}

function renderTopPills() {
  const providerAgent = state.bots.find((b) => b.engine === "provider");
  $("engine-mini").textContent = providerAgent ? "provider fleet" : "scripted test bots";
  $("provider-mini").textContent =
    `provider: ${providerAgent ? providerAgent.provider : "auto"}`;
}

boot();

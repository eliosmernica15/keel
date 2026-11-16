"use strict";

/* Keel Desktop & Keel Code — one PWA, two surfaces, one settings system.
   Both surfaces ride the same local bridge (/api/run, NDJSON). Settings and
   provider keys are saved on this machine only (~/.keel/settings.json).
   Works standalone in a browser (clearly labelled demo) or inside Tauri
   against the real keel sidecar (window.__TAURI__). */

const $ = (id) => document.getElementById(id);
const rootEl = document.querySelector(".app");

const threads = { chat: $("thread-chat"), code: $("thread-code") };
const views = { chat: $("view-chat"), code: $("view-code") };
const prompts = { chat: $("prompt-chat"), code: $("prompt-code") };
const sendBtns = { chat: $("btn-send-chat"), code: $("btn-send-code") };

const state = {
  running: false,
  runSurface: null,
  surface: "chat",
  sessionId: null,
  turns: 0,
  tokens: 0,
};
const surfaceName = { chat: "Keel Desktop", code: "Keel Code" };

/* local(Storage)-only helpers used across modules */
const fsToken = () => {
  const p = new URLSearchParams(location.search);
  return p.get("t") || sessionStorage.getItem("keel_token") || "";
};
const fsHeaders = () => ({ "X-Keel-Token": fsToken() });
const jsonHeaders = () => ({ ...fsHeaders(), "Content-Type": "application/json" });
const els = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ============================================================ surfaces */

function setSurface(name, { focus = true } = {}) {
  if (!views[name]) return;
  state.surface = name;
  for (const [key, view] of Object.entries(views)) {
    view.classList.toggle("hidden", key !== name);
  }
  for (const key of Object.keys(views)) {
    const seg = $(`seg-${key}`);
    const on = key === name;
    seg.classList.toggle("on", on);
    seg.setAttribute("aria-selected", String(on));
  }
  $("head-title").textContent = state.sessionId
    ? `session ${String(state.sessionId).slice(0, 8)}`
    : surfaceName[name];
  try { localStorage.setItem("keel_surface", name); } catch { /* private mode */ }
  if (focus) prompts[name]?.focus();
}
$("seg-chat").addEventListener("click", () => setSurface("chat"));
$("seg-code").addEventListener("click", () => setSurface("code"));

/* ===================================================================== bridge */

function mkBridge() {
  if (window.__TAURI__) {
    return {
      live: true,
      send(payload) { return window.__TAURI__.core.invoke("keel_send", payload); },
      listen(event, cb) { return window.__TAURI__.event.listen(event, cb); },
      providers() {
        return window.__TAURI__.core.invoke("keel_providers")
          .then((rows) => rows)
          .catch(() => []);
      },
    };
  }
  if (location.protocol === "http:" || location.protocol === "https:") {
    const params = new URLSearchParams(location.search);
    const token = params.get("t") || sessionStorage.getItem("keel_token") || "";
    if (token) sessionStorage.setItem("keel_token", token);
    const headers = () => ({ "X-Keel-Token": token });
    const trimmedQuery = () => {
      const url = new URL(location.href);
      url.searchParams.delete("t");
      history.replaceState(null, "", url.pathname + url.search);
    };
    return {
      live: true,
      send(payload) {
        return fetch("/api/run", {
          method: "POST",
          headers: { ...headers(), "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).then(async (resp) => {
          if (!resp.ok || !resp.body) {
            const text = await resp.text().catch(() => "");
            throw new Error(`http ${resp.status} ${text.slice(0, 300)}`);
          }
          trimmedQuery();
          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          const surface = state.runSurface;
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
              if (!line.trim()) continue;
              try { handleEvent(JSON.parse(line), surface); } catch { /* skip */ }
            }
          }
          if (buffer.trim()) {
            try { handleEvent(JSON.parse(buffer), surface); } catch { /* skip */ }
          }
          return "bridge";
        });
      },
      providers() {
        return fetch("/api/providers", { headers: headers() })
          .then((r) => (r.ok ? r.json() : { providers: [] }))
          .then((doc) => doc.providers || [])
          .catch(() => []);
      },
      listen() { return Promise.resolve(() => {}); },
    };
  }
  return {
    live: false,
    send(payload) {
      const surface = state.runSurface;
      const plan = [
        { type: "system", subtype: "init", session_id: "demo-0001",
          tools: ["read_file", "write_file", "edit_file", "glob", "grep", "run_shell"],
          model: "demo (not a real model)", permissionMode: payload.permission_mode },
        { type: "assistant", message: { content: [
          { type: "tool_use", id: "call_demo1", name: "run_shell",
            input: { command: "echo demo: it ran a shell command", shell: "posix" } } ] } },
        { type: "user", message: { content: [
          { type: "tool_result", tool_use_id: "call_demo1",
            content: "demo output (mock backend — no process was executed)" } ] } },
        { type: "assistant", message: { content: [
          { type: "text", text: "[demo mode] This transcript is generated by a built-in fixture; no model and no keel backend are connected. Start `keel serve` and open the printed URL for the real thing." } ] } },
        { type: "result", subtype: "success", is_error: false, num_turns: 1,
          total_cost_usd: 0, usage: { input_tokens: 0, output_tokens: 0 },
          stop_reason: "end_turn", terminal_reason: "completed",
          result: "demo run complete", session_id: "demo-0001" },
      ];
      for (const evt of plan) handleEvent(evt, surface);
      finishRun();
      return Promise.resolve("demo");
    },
    listen() { return Promise.resolve(() => {}); },
    providers() { return Promise.resolve([]); },
  };
}

const bridge = mkBridge();

/* ================================================================= rendering */

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key.startsWith("data-") || key === "role" || key.startsWith("aria-")) {
      node.setAttribute(key, String(value));
    } else {
      node[key] = value;
    }
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}
const threadOf = (surface) => threads[surface] || threads[state.surface];

function hideEmptyState(surface) {
  const id = surface === "chat" ? "hero-chat" : "start-code";
  const target = $(id);
  if (target) target.classList.add("hidden");
}
function showEmptyState(surface) {
  const id = surface === "chat" ? "hero-chat" : "start-code";
  const target = $(id);
  if (target) target.classList.remove("hidden");
}

function appendMessage(kind, role, build, surface) {
  const target = threadOf(surface);
  hideEmptyState(surface || state.surface);
  const msg = el("div", { className: `msg ${kind}` });
  msg.appendChild(el("small", { className: "role", textContent: role }));
  const body = el("div", { className: "body" });
  build(body);
  msg.appendChild(body);
  target.appendChild(msg);
  target.scrollTop = target.scrollHeight;
  return msg;
}
function systemNote(text, cls = "system", surface) {
  appendMessage(cls, "system", (body) => { body.textContent = text; }, surface);
}
function renderToolUse(block, surface) {
  appendMessage("tool", "tool call", (body) => {
    const box = el("div", { className: "tool-call" });
    box.appendChild(el("span", { className: "tool-name", textContent: String(block.name) }));
    box.appendChild(document.createTextNode("  " + JSON.stringify(block.input || {})));
    body.appendChild(box);
  }, surface);
}
function renderToolResult(block, surface) {
  const text = String(block.content ?? "");
  const isError = text.startsWith("<tool_use_error>");
  appendMessage(isError ? "denied" : "tool", "tool result", (body) => {
    body.appendChild(el("div", {
      className: isError ? "tool-result-error" : "tool-call",
      textContent: text.slice(0, 4000),
    }));
  }, surface);
}
function renderResult(evt, surface) {
  const u = evt.usage || {};
  state.tokens += (u.input_tokens || 0) + (u.output_tokens || 0);
  state.turns = evt.num_turns ?? state.turns + 1;
  appendMessage("result", "result", (body) => {
    const grid = el("div", { className: "result-grid" });
    const cell = (label, value) => {
      const div = el("div");
      div.appendChild(el("span", { textContent: label }));
      div.appendChild(el("strong", { textContent: String(value) }));
      grid.appendChild(div);
    };
    cell("turns", evt.num_turns ?? 0);
    cell("tokens", (u.input_tokens || 0) + (u.output_tokens || 0));
    cell("cost", `$${(evt.total_cost_usd ?? 0).toFixed(4)}`);
    cell("stop", evt.stop_reason ?? "?");
    cell("is error", evt.is_error ? "yes" : "no");
    body.appendChild(grid);
  }, surface);
  $("turn-count").textContent = `${evt.num_turns ?? state.turns} turns`;
  $("token-count").textContent = `${state.tokens} tokens`;
  updateRing();
  notifyResponseDone(evt);
}
function updateRing() {
  const ring = $("usage-ring");
  if (ring) ring.title = `${state.turns} turn(s) · ${state.tokens} token(s) this session`;
}

function handleEvent(evt, surface) {
  const s = surface || state.runSurface || state.surface;
  switch (evt.type) {
    case "system": {
      const sub = evt.subtype;
      if (sub === "init") {
        state.sessionId = evt.session_id;
        $("session-id-label").textContent = `session ${String(evt.session_id).slice(0, 8)}`;
        $("head-title").textContent = `session ${String(evt.session_id).slice(0, 8)}`;
        const toolCount = Array.isArray(evt.tools) ? evt.tools.length : 0;
        const mcp = Array.isArray(evt.mcp_servers) ? evt.mcp_servers.length : 0;
        systemNote(`session started — ${toolCount} tools, ${mcp} MCP server(s), model ${evt.model}`, "system", s);
        return;
      }
      if (sub === "permission_denied") {
        systemNote(`permission denied: ${evt.tool_name} — ${evt.decision_reason}`, "denied", s);
        return;
      }
      if (sub === "informational" || sub === "compact_boundary") {
        systemNote(evt.content || JSON.stringify(evt), "system", s);
        return;
      }
      if (sub === "hook_response") { systemNote(`hook ${evt.hook_name}: ${evt.verdict}`, "system", s); return; }
      return;
    }
    case "assistant": {
      for (const block of evt.message?.content || []) {
        if (block.type === "text") {
          appendMessage("assistant", s === "code" ? "keel code" : "keel", (body) => { body.textContent = block.text; }, s);
        } else if (block.type === "tool_use") {
          renderToolUse(block, s);
        } else if (block.type === "thinking") {
          appendMessage("system", "thinking", (body) => { body.textContent = block.thinking || block.text || ""; }, s);
        }
      }
      return;
    }
    case "user": {
      for (const block of evt.message?.content || []) {
        if (block.type === "tool_result") renderToolResult(block, s);
      }
      return;
    }
    case "result":
      renderResult(evt, s);
      finishRun();
      return;
  }
}

/* ================================================================ control */

function setStatus(text, kind) {
  $("status-text").textContent = text;
  const dot = $("status-dot");
  dot.className = `dot ${kind === "busy" ? "dot-busy" : kind === "err" ? "dot-err" : "dot-ok"}`;
}
function finishRun() {
  state.running = false;
  state.runSurface = null;
  for (const btn of Object.values(sendBtns)) btn.disabled = false;
  setStatus("idle", "ok");
}
function startRun() {
  state.running = true;
  for (const btn of Object.values(sendBtns)) btn.disabled = true;
  setStatus("running…", "busy");
}

const MODE_LABEL = { default: "manual", acceptEdits: "accept edits", dontAsk: "dont ask", bypassPermissions: "bypass" };
const MODE_CYCLE = ["default", "acceptEdits", "dontAsk", "bypassPermissions"];
const MODE_TO_PROVIDER_ENV = {
  openrouter: "KEEL_OPENROUTER_MODEL", google: "KEEL_GOOGLE_MODEL",
  nvidia: "KEEL_NVIDIA_MODEL", anthropic: "KEEL_ANTHROPIC_MODEL",
};
const currentMode = () => $("mode-select").value;
const acceptRisk = () => $("accept-risk").checked;
const currentProvider = () => providerConfig.preferred || "auto";
const pinnedModelFor = (provider) => (providerConfig.models && providerConfig.models[provider]) || "";

function syncModeUI() {
  const label = MODE_LABEL[currentMode()] || currentMode();
  $("mode-pill").textContent = label;
  $("chip-mode-label").textContent = label;
  $("provider-pill").textContent = currentProvider();
  const pinned = pinnedModelFor(currentProvider());
  $("model-pill-chat").textContent = pinned
    ? `${currentProvider()} · ${pinned.split("/").pop().slice(0, 34)}`
    : `Keel · ${currentProvider()}`;
}
function requestMode(mode) {
  if (mode === "bypassPermissions" && !acceptRisk()) {
    systemNote("bypass requires 'I accept the risk of bypass mode' in Providers → Session — not enabling it.", "denied", state.surface);
    openSettings("providers");
    return false;
  }
  $("mode-select").value = mode;
  syncModeUI();
  return true;
}

function notifyResponseDone(evt) {
  if (!uiSettings.notifications || uiSettings.notifications.response === false) return;
  if (!document.hidden) return;
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  try {
    new Notification("Keel finished", {
      body: `${evt.num_turns ?? 0} turn(s) · ${
        ((evt.usage?.input_tokens || 0) + (evt.usage?.output_tokens || 0))} token(s)`,
      icon: "/ui/icons/icon-192.png",
    });
  } catch { /* permission revoked mid-run */ }
}

function send(surface) {
  const active = surface || state.surface;
  const promptEl = prompts[active];
  const raw = promptEl.value.trim();
  if (!raw || state.running) return;

  const permission_mode = currentMode();
  if (permission_mode === "bypassPermissions" && !acceptRisk()) {
    systemNote("bypass mode requires 'I accept the risk' before sending", "denied", active);
    openSettings("providers");
    return;
  }

  const instructions = (uiSettings.instructions || "").trim();
  const outbound = instructions ? `${instructions}\n\n${raw}` : raw;
  appendMessage("user", "you", (body) => { body.textContent = outbound; }, active);
  addRecent(raw, active);
  state.runSurface = active;
  startRun();

  const provider = currentProvider();
  const payload = {
    prompt: outbound,
    provider,
    permission_mode,
    accept_risk: acceptRisk(),
    model: pinnedModelFor(provider),
  };
  const maybePromise = bridge.send(payload);
  if (maybePromise && maybePromise.catch) {
    maybePromise.catch((err) => {
      systemNote(`backend error: ${err}`, "denied", state.runSurface || active);
      finishRun();
    });
  }
  promptEl.value = "";
  if (promptEl.tagName === "TEXTAREA") promptEl.style.height = "";
}
function handleEnter(ev, surface) {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(surface); }
}
$("form-chat").addEventListener("submit", (ev) => { ev.preventDefault(); send("chat"); });
$("form-code").addEventListener("submit", (ev) => { ev.preventDefault(); send("code"); });
prompts.chat.addEventListener("keydown", (ev) => handleEnter(ev, "chat"));
prompts.code.addEventListener("keydown", (ev) => handleEnter(ev, "code"));
$("attach-chat").addEventListener("click", () =>
  systemNote("Attach: drop a file path into your prompt — the agent reads it with its tools (read_file / glob / grep).", "system", "chat"));
$("attach-code").addEventListener("click", () =>
  systemNote("Add context: name the file or folder in your prompt — Keel Code reads it with its tools (read_file / glob / grep).", "system", "code"));

/* ================================================================ recents */

const RECENT_KEY = "keel_recents_v1";
const RECENT_CAP = 50;
let recentFilter = "";
function loadRecents() { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } }
function saveRecents(items) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, RECENT_CAP))); } catch { /* full/private */ }
}
function addRecent(text, surface) {
  const items = loadRecents();
  items.unshift({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, text, surface, ts: Date.now(), pinned: false });
  saveRecents(items);
  renderRecents();
}
function togglePin(id) {
  const items = loadRecents().map((item) => (item.id === id ? { ...item, pinned: !item.pinned } : item));
  saveRecents(items);
  renderRecents();
}
function renderRecents() {
  const items = loadRecents();
  const match = (item) => !recentFilter || item.text.toLowerCase().includes(recentFilter);
  const pinned = items.filter((item) => item.pinned && match(item));
  const rest = items.filter((item) => !item.pinned && match(item)).slice(0, 20);
  const paint = (container, list) => {
    container.textContent = "";
    for (const item of list) {
      const row = el("div", { className: `item${item.pinned ? " pinned" : ""}`, tabindex: "0", role: "button", title: item.text });
      const icon = el("svg", { className: "ic", viewBox: "0 0 16 16" });
      icon.innerHTML = item.surface === "code"
        ? '<path d="M5.5 5L2.5 8l3 3M10.5 5l3 3-3 3M9 4l-2 8"/>'
        : '<path d="M9.5 3.5h-5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h.5v2l2.5-2h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2z"/>';
      row.appendChild(icon);
      row.appendChild(el("span", { className: "t", textContent: item.text }));
      const pin = el("button", { className: "pin", "aria-label": item.pinned ? "Unpin" : "Pin", type: "button" });
      const pinSvg = el("svg", { viewBox: "0 0 16 16" });
      pinSvg.innerHTML = '<path d="M9.6 2.4l4 4-2 .6-2.2 2.2.4 2.6-1.6 1.6-3-3-3.6 3.6-.4-.4 3.6-3.6-3-3 1.6-1.6 2.6.4 2.2-2.2z"/>';
      pin.appendChild(pinSvg);
      pin.addEventListener("click", (ev) => { ev.stopPropagation(); togglePin(item.id); });
      row.appendChild(pin);
      const launch = () => {
        setSurface(item.surface === "code" ? "code" : "chat");
        prompts[state.surface].value = item.text;
        prompts[state.surface].focus();
      };
      row.addEventListener("click", launch);
      row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); launch(); } });
      container.appendChild(row);
    }
  };
  paint($("pinned-list"), pinned);
  paint($("recents-list"), rest);
  $("recents-empty").style.display = items.length === 0 ? "" : "none";
}
$("btn-clear-recents").addEventListener("click", () => {
  if (!confirm("Clear all locally stored prompts? This only affects this machine.")) return;
  saveRecents([]);
  renderRecents();
});
$("btn-search-recents").addEventListener("click", () => {
  const next = window.prompt("Filter recents (empty to clear filter):", recentFilter);
  if (next === null) return;
  recentFilter = next.trim().toLowerCase();
  renderRecents();
});

/* ===================================================================== wiring */

$("nav-new").addEventListener("click", () => {
  for (const thread of Object.values(threads)) thread.textContent = "";
  $("session-id-label").textContent = "no session";
  $("turn-count").textContent = "0 turns";
  $("token-count").textContent = "0 tokens";
  state.sessionId = null;
  state.turns = 0;
  state.tokens = 0;
  updateRing();
  for (const [key, thread] of Object.entries(threads)) {
    if (!thread.children.length) showEmptyState(key);
  }
  $("head-title").textContent = surfaceName[state.surface];
  setStatus("idle", "ok");
});

/* ------------------------------------------------------------- settings */

let uiSettings = {};
let providerConfig = { preferred: "auto", models: {} };

const settingsPanel = $("settings-panel");
function openSettings(pane = "general") {
  settingsPanel.hidden = false;
  showPane(pane);
  refreshProviders();
}
const openConfig = openSettings; // legacy alias used by legacy handlers
function closeSettings() { settingsPanel.hidden = true; }
$("nav-customize").addEventListener("click", () => openSettings("general"));
$("settings-close").addEventListener("click", closeSettings);
$("settings-backdrop").addEventListener("click", closeSettings);
$("model-pill-chat").addEventListener("click", () => openSettings("general"));

function showPane(name) {
  els(".rail-item").forEach((b) => b.classList.toggle("on", b.dataset.section === name));
  els(".pane").forEach((p) => p.classList.toggle("on", p.id === `pane-${name}`));
  if (name === "skills") loadSkills();
  if (name === "connectors") loadConnectors();
  if (name === "system") refreshSystem();
  if (name === "privacy") refreshStorageUsage();
  if (name === "usage") refreshUsage();
  if (name === "keel-code" || name === "keel-desktop") refreshBridgeStatus();
  if (name === "general") hydrateGeneral();
  if (name === "providers") { loadSettings().then(refreshProviders); }
}
els(".rail-item").forEach((btn) => btn.addEventListener("click", () => showPane(btn.dataset.section)));
$("settings-search").addEventListener("input", (ev) => {
  const needle = ev.target.value.trim().toLowerCase();
  els(".rail-item").forEach((btn) => {
    btn.classList.toggle("hidden-by-filter", !!needle && !btn.textContent.toLowerCase().includes(needle));
  });
  els(".rail-group").forEach((group) => {
    let el = group.nextElementSibling;
    let visible = 0;
    while (el && el.classList.contains("rail-item")) {
      if (!el.classList.contains("hidden-by-filter")) visible++;
      el = el.nextElementSibling;
    }
    group.style.display = visible || !needle ? "" : "none";
  });
});

async function fetchJson(url, options) {
  try {
    const r = await fetch(url, options);
    if (!r.ok) return { __status: r.status };
    return await r.json();
  } catch {
    return { __status: 0 };
  }
}

async function loadSettings() {
  const doc = await fetchJson("/api/settings", { headers: fsHeaders() });
  if (doc.__status !== undefined) {
    uiSettings = {};
    providerConfig = { preferred: "auto", models: {} };
    return doc;
  }
  uiSettings = (doc && doc.ui) || {};
  providerConfig = (doc && doc.providerConfig) || { preferred: "auto", models: {} };
  providerConfig.models = providerConfig.models || {};
  return doc;
}

async function saveSettingsPatch(patch) {
  const doc = await fetchJson("/api/settings", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(patch),
  });
  if (doc.__status !== undefined || doc.error) {
    throw new Error(doc.error || `settings save failed (${doc.__status})`);
  }
  uiSettings = doc.ui || uiSettings;
  providerConfig = doc.providerConfig || providerConfig;
  syncModeUI();
  return doc;
}

/* ---------- General section ---------- */

const instructionsEl = $("instructions");
const instructionsMeta = $("instructions-meta");
function hydrateGeneral() {
  $("work-select").value = uiSettings.work || "";
  if (document.activeElement !== instructionsEl) instructionsEl.value = uiSettings.instructions || "";
  instructionsMeta.textContent = `${(uiSettings.instructions || "").length} characters`;
  const font = uiSettings.font || "body";
  els("#font-chips button").forEach((b) => b.classList.toggle("on", b.dataset.font === font));
  document.body.dataset.font = font;
  const motion = uiSettings.motion || "system";
  els("#motion-seg button").forEach((b) => b.classList.toggle("on", b.dataset.motion === motion));
  document.body.classList.toggle("reduce-motion", motion === "reduced");
  const notif = !uiSettings.notifications || uiSettings.notifications.response !== false;
  $("notif-toggle").checked = notif;
  applyTheme(uiSettings.theme || "dark");
}
$("work-select").addEventListener("change", (ev) => {
  saveSettingsPatch({ ui: { work: ev.target.value } }).catch(() => {});
});
instructionsEl.addEventListener("input", () => {
  instructionsMeta.textContent = `${instructionsEl.value.length} characters`;
});
$("save-instructions").addEventListener("click", async () => {
  try {
    await saveSettingsPatch({ ui: { instructions: instructionsEl.value.trim() } });
    instructionsMeta.textContent = `${instructionsEl.value.length} characters · saved`;
    instructionsMeta.className = "hint ok";
  } catch {
    instructionsMeta.textContent = "could not save — is the bridge running?";
    instructionsMeta.className = "hint err";
  }
});
els("#font-chips button").forEach((btn) => btn.addEventListener("click", () => {
  document.body.dataset.font = btn.dataset.font;
  els("#font-chips button").forEach((b) => b.classList.toggle("on", b === btn));
  saveSettingsPatch({ ui: { font: btn.dataset.font } }).catch(() => {});
}));
function applyTheme(mode) {
  if (mode === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
  document.querySelectorAll("#theme-seg button").forEach((b) => b.classList.toggle("on", b.dataset.theme === mode));
}
els("#theme-seg button").forEach((btn) => btn.addEventListener("click", () => {
  applyTheme(btn.dataset.theme);
  saveSettingsPatch({ ui: { theme: btn.dataset.theme } }).catch(() => {});
}));
els("#motion-seg button").forEach((btn) => btn.addEventListener("click", () => {
  document.body.classList.toggle("reduce-motion", btn.dataset.motion === "reduced");
  els("#motion-seg button").forEach((b) => b.classList.toggle("on", b === btn));
  saveSettingsPatch({ ui: { motion: btn.dataset.motion } }).catch(() => {});
}));
$("notif-toggle").addEventListener("change", async (ev) => {
  const wanted = ev.target.checked;
  if (wanted && typeof Notification !== "undefined" && Notification.permission === "default") {
    try { await Notification.requestPermission(); } catch { /* denied silently */ }
  }
  saveSettingsPatch({ ui: { notifications: { response: wanted } } }).catch(() => {});
});

/* ---------- Providers section ---------- */

const PROVIDER_DEFS = [
  { name: "openrouter", label: "OpenRouter", tag: "unified gateway", hint: "sk-or-…" },
  { name: "google", label: "Google AI Studio", tag: "gemini", hint: "AIza…" },
  { name: "nvidia", label: "NVIDIA NIM", tag: "build.nvidia.com", hint: "nvapi-…" },
  { name: "anthropic", label: "Anthropic", tag: "opt-in only", hint: "sk-ant-…" },
  { name: "openai-compatible", label: "OpenAI-compatible", tag: "your endpoint", hint: "sk-…" },
];

function providerStatusLine(p) {
  if (!p) return { text: "status unavailable", cls: "" };
  if (!p.configured) return { text: "not linked", cls: "unset" };
  if (p.key_source === "settings.json") {
    return { text: `saved •• ${p.key_hint || "…"}`, cls: "" };
  }
  return { text: "env var set", cls: "" };
}

async function refreshProviders() {
  const list = await fetchJson("/api/providers", { headers: fsHeaders() });
  const rows = Array.isArray(list.providers) ? list.providers : [];
  const byName = Object.fromEntries(rows.map((r) => [r.name, r]));
  const linked = rows.filter((r) => r.configured).length;
  $("rail-configured").textContent = `${linked} linked`;
  $("preferred-select").value = providerConfig.preferred || "auto";
  $("provider-select").value = providerConfig.preferred || "auto";

  const wrap = $("provider-rows");
  wrap.textContent = "";
  for (const def of PROVIDER_DEFS) {
    const info = byName[def.name] || null;
    const st = providerStatusLine(info);
    const pinned = pinnedModelFor(def.name);
    const row = el("div", { className: `provider-row${info && info.configured ? " is-linked" : ""}`, "data-provider": def.name });
    row.innerHTML = `
      <div class="provider-head">
        <span class="provider-name">${def.label}</span>
        <span class="provider-src${st.cls === "unset" ? " unset" : ""}">${st.text}</span>
      </div>
      <div class="provider-model">${info && info.default_model ? `default: ${info.default_model}` : ""}${def.tag ? " · " + def.tag : ""}</div>
      <div class="provider-actions">
        <button class="btn-ghost small save-btn">${info && info.configured && info.key_source === "settings.json" ? "Replace key…" : "Save key…"}</button>
        <button class="btn-ghost small use-btn">Use this provider</button>
        <button class="btn-ghost small models-btn">Models…</button>
        ${info && info.key_source === "settings.json" ? '<button class="btn-ghost small danger remove-btn">Remove saved key</button>' : ""}
      </div>
      <div class="provider-verify">
        <input type="password" class="key-input" placeholder="${def.hint}" aria-label="API key for ${def.label}" autocomplete="off">
        <button class="btn-primary small verify-btn">Verify &amp; save</button>
        <span class="hint verify-msg"></span>
      </div>
      <div class="provider-models">
        <input class="model-filter" type="text" placeholder="Filter models…" aria-label="Filter models" autocomplete="off">
        <p class="hint models-meta">loading catalog…</p>
        <div class="model-options" role="listbox" aria-label="Models"></div>
        <p class="pinned-line" hidden></p>
      </div>`;
    wrap.appendChild(row);

    const verifyBox = els(".provider-verify", row)[0];
    const modelsBox = els(".provider-models", row)[0];
    const keyInput = els(".key-input", row)[0];
    const verifyMsg = els(".verify-msg", row)[0];

    els(".save-btn", row)[0].addEventListener("click", () => row.classList.toggle("verifying"));
    els(".use-btn", row)[0].addEventListener("click", async () => {
      await saveSettingsPatch({ providerConfig: { preferred: def.name } });
      syncModeUI();
      refreshProviders();
    });
    els(".remove-btn", row)[0]?.addEventListener("click", async () => {
      if (!confirm(`Forget the saved ${def.label} key on this machine?`)) return;
      const res = await fetchJson("/api/fleet/providers/remove", {
        method: "POST", headers: jsonHeaders(), body: JSON.stringify({ name: def.name }),
      });
      if (res.ok) { await loadSettings(); refreshProviders(); }
    });
    els(".verify-btn", row)[0].addEventListener("click", async () => {
      const key = keyInput.value.trim();
      if (!key) { verifyMsg.textContent = "key is empty"; verifyMsg.className = "hint err"; return; }
      verifyMsg.textContent = "verifying against the provider…";
      verifyMsg.className = "hint";
      const res = await fetchJson("/api/fleet/providers/save", {
        method: "POST", headers: jsonHeaders(), body: JSON.stringify({ name: def.name, key }),
      });
      if (res.ok) {
        verifyMsg.textContent = `saved — ${res.model_count} models reachable`;
        verifyMsg.className = "hint ok";
        keyInput.value = "";
        await loadSettings();
        refreshProviders();
      } else {
        verifyMsg.textContent = res.detail || res.error || "provider rejected the key";
        verifyMsg.className = "hint err";
      }
    });
    els(".models-btn", row)[0].addEventListener("click", async () => {
      const open = row.classList.toggle("models-open");
      if (!open) return;
      const meta = els(".models-meta", row)[0];
      const options = els(".model-options", row)[0];
      const filter = els(".model-filter", row)[0];
      const pinnedLine = els(".pinned-line", row)[0];
      meta.textContent = "loading catalog from the provider…";
      options.textContent = "";
      const res = await fetchJson("/api/fleet/providers/catalog", {
        method: "POST", headers: jsonHeaders(), body: JSON.stringify({ name: def.name }),
      });
      if (!res.ok) {
        meta.textContent = res.detail || res.error || "no key configured — save one first";
        meta.className = "hint err";
        return;
      }
      const models = (res.models || []).map((m) => (typeof m === "string" ? m : m.id)).filter(Boolean);
      meta.textContent = `${models.length} models — click to pin one`;
      meta.className = "hint ok";
      const renderOptions = () => {
        const needle = filter.value.trim().toLowerCase();
        options.textContent = "";
        let shown = 0;
        for (const id of models) {
          if (needle && !id.toLowerCase().includes(needle)) continue;
          if (shown >= 80) break;
          shown++;
          const opt = el("button", { className: "model-option", type: "button", role: "option" });
          opt.appendChild(el("span", { className: "id", textContent: id }));
          opt.appendChild(el("span", { className: "pin", textContent: "pin" }));
          opt.addEventListener("click", async () => {
            const modelsMap = { ...(providerConfig.models || {}), [def.name]: id };
            await saveSettingsPatch({ providerConfig: { models: modelsMap } });
            syncModeUI();
            const note = `pinned: ${id}`;
            pinnedLine.hidden = false;
            pinnedLine.textContent = note;
          });
          options.appendChild(opt);
        }
        if (!shown) options.appendChild(el("p", { className: "hint", textContent: "no match" }));
      };
      filter.addEventListener("input", renderOptions);
      renderOptions();
      if (pinned) {
        pinnedLine.hidden = false;
        pinnedLine.textContent = `pinned: ${pinned}`;
      }
    });
  }
  syncModeUI();
}
$("preferred-select").addEventListener("change", async (ev) => {
  await saveSettingsPatch({ providerConfig: { preferred: ev.target.value } });
  $("provider-select").value = providerConfig.preferred;
  syncModeUI();
  refreshProviders();
});
$("mode-select").addEventListener("change", syncModeUI);
$("accept-risk").addEventListener("change", () => {
  if (!$("accept-risk").checked && currentMode() === "bypassPermissions") $("mode-select").value = "default";
  syncModeUI();
});
$("provider-select").addEventListener("change", syncModeUI); // hidden carrier

/* ---------- Usage / Privacy / Import ---------- */

function refreshUsage() {
  $("stat-turns").textContent = String(state.turns);
  $("stat-tokens").textContent = String(state.tokens);
}
function storageBytes() {
  let total = 0;
  for (const key of Object.keys(localStorage)) total += localStorage.getItem(key)?.length || 0;
  return total;
}
function refreshStorageUsage() {
  const kb = storageBytes() / 1024;
  $("storage-usage").textContent = `localStorage on this machine: ~${kb.toFixed(1)} KB across ${localStorage.length} key(s) — cleared only by you.`;
}
$("clear-recents-pwa").addEventListener("click", () => { saveRecents([]); renderRecents(); refreshStorageUsage(); });
$("clear-visit-prompts").addEventListener("click", () => {
  try { sessionStorage.removeItem("keel_visit_prompts_v1"); } catch {}
  refreshStorageUsage();
});
$("export-settings").addEventListener("click", async () => {
  const doc = await fetchJson("/api/settings/export", { headers: fsHeaders() });
  if (doc.__status !== undefined) return;
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "keel-settings.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
const importFile = $("import-file");
$("import-pick").addEventListener("click", () => importFile.click());
importFile.addEventListener("change", async () => {
  const file = importFile.files && importFile.files[0];
  if (!file) return;
  const note = $("import-result");
  let doc;
  try { doc = JSON.parse(await file.text()); } catch {
    note.textContent = "not valid JSON";
    note.className = "hint err";
    return;
  }
  if (!confirm("Merge this file into ~/.keel/settings.json? A backup (settings.json.bak) is kept.")) return;
  const includeKeys = $("import-include-keys").checked;
  const res = await fetchJson("/api/settings/import", {
    method: "POST", headers: jsonHeaders(),
    body: JSON.stringify({ doc, include_keys: includeKeys }),
  });
  if (res.ok) {
    note.textContent = includeKeys
      ? "imported — UI, providers and saved keys merged"
      : "imported — UI and provider preferences merged (keys untouched)";
    note.className = "hint ok";
    await loadSettings();
    refreshProviders();
  } else {
    note.textContent = res.error || "import failed";
    note.className = "hint err";
  }
});

/* ---------- Keel Code / Desktop / System / Developer ---------- */

function refreshBridgeStatus() {
  fetchJson("/api/health", { headers: fsHeaders() }).then((doc) => {
    const text = doc.ok ? `online · v${doc.version}` : "unreachable";
    $("keelcode-status").textContent = text;
    $("keeldesktop-status").textContent = text;
  }).catch(() => {
    $("keelcode-status").textContent = "unreachable";
    $("keeldesktop-status").textContent = "unreachable";
  });
}
async function refreshSystem() {
  const health = await fetchJson("/api/health", { headers: fsHeaders() });
  $("sys-version").textContent = health.version ? `v${health.version}` : "unknown";
  $("sys-origin").textContent = `${location.origin} (loopback only)`;
  $("sys-workdir").textContent = workdir || "not set — the bridge's launch folder is used";
}
$("goto-code").addEventListener("click", () => { setSurface("code"); closeSettings(); });
$("goto-desktop").addEventListener("click", () => { setSurface("chat"); closeSettings(); });
$("goto-connectors").addEventListener("click", () => showPane("connectors"));

/* ---------- Skills / Connectors ---------- */

async function loadSkills() {
  const wrap = $("skills-list");
  wrap.innerHTML = '<p class="hint">Loading…</p>';
  const doc = await fetchJson("/api/fleet/skills", { headers: fsHeaders() });
  const skills = Array.isArray(doc.skills) ? doc.skills : [];
  wrap.textContent = "";
  if (!skills.length) {
    wrap.innerHTML = '<p class="hint">No skills found on this machine — Keel reads user and bundled skill files at run time.</p>';
    return;
  }
  for (const skill of skills.slice(0, 60)) {
    const item = el("div", { className: "list-item" });
    const head = el("div");
    head.appendChild(el("b", { textContent: skill.name || "unnamed" }));
    if (skill.scope) head.appendChild(el("span", { className: "tag", textContent: skill.scope }));
    item.appendChild(head);
    if (skill.description) {
      item.appendChild(el("p", { textContent: String(skill.description).slice(0, 180) }));
    }
    wrap.appendChild(item);
  }
}
async function loadConnectors() {
  const wrap = $("connectors-list");
  wrap.innerHTML = '<p class="hint">Loading…</p>';
  const doc = await fetchJson("/api/fleet/connectors", { headers: fsHeaders() });
  const connectors = Array.isArray(doc.connectors) ? doc.connectors : [];
  const presets = Array.isArray(doc.presets) ? doc.presets : [];
  const openFleet = $("open-fleet");
  if (fsToken()) openFleet.href = `/fleet?t=${encodeURIComponent(fsToken())}`;
  wrap.textContent = "";
  if (!connectors.length) {
    wrap.innerHTML = `<p class="hint">No connectors configured. ${presets.length} preset(s) available in the fleet console — GitHub, filesystem, memory, sequential-thinking and more.</p>`;
    return;
  }
  for (const c of connectors) {
    const item = el("div", { className: "list-item" });
    const head = el("div");
    head.appendChild(el("b", { textContent: c.name || "unnamed" }));
    item.appendChild(head);
    if (c.command) item.appendChild(el("p", { textContent: String(c.command) }));
    wrap.appendChild(item);
  }
}

/* ---------- folder picker (unchanged behaviour) ---------- */

const picker = $("fs-picker");
const fsListEl = $("fs-list");
const fsErrorEl = $("fs-error");
const fsPathEl = $("fs-path");
const fsRootsEl = $("fs-roots");
let pickerPath = "";
let workdir = null;

function fsError(msg) {
  fsErrorEl.hidden = !msg;
  fsErrorEl.textContent = msg || "";
}
function joinPath(base, name) {
  const sep = base.includes("\\") ? "\\" : "/";
  return base.endsWith("\\") || base.endsWith("/") ? base + name : base + sep + name;
}
function baseName(path) {
  const parts = String(path).split(/[\\/]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : path;
}
function openFsPicker() {
  picker.hidden = false;
  fsError("");
  loadFs(workdir || "");
}
function closeFsPicker() { picker.hidden = true; }
async function loadFs(path) {
  fsError("");
  try {
    const q = path ? `?path=${encodeURIComponent(path)}` : "";
    const r = await fetch(`/api/fs/list${q}`, { headers: fsHeaders() });
    if (r.status === 404 || r.status === 405) {
      fsPathEl.textContent = "—";
      fsRootsEl.textContent = "";
      fsListEl.textContent = "";
      fsError("This folder browser needs the updated bridge — quit and restart `keel serve`, then reopen this window.");
      return;
    }
    if (!r.ok) { fsError(`bridge refused the listing (http ${r.status}).`); return; }
    const doc = await r.json();
    pickerPath = doc.path || "";
    fsPathEl.textContent = pickerPath;
    fsRootsEl.textContent = "";
    for (const root of doc.roots || []) {
      const chip = el("button", { className: "root-chip", type: "button", textContent: root });
      chip.addEventListener("click", () => loadFs(root));
      fsRootsEl.appendChild(chip);
    }
    const rows = [];
    if (doc.parent) rows.push({ name: "..", up: true });
    for (const dir of doc.dirs || []) rows.push({ name: dir.name });
    fsListEl.textContent = "";
    if (!rows.length) {
      fsListEl.appendChild(el("p", { className: "picker-empty", textContent: "No subfolders here — this folder itself can be used." }));
    } else {
      for (const row of rows) {
        const btn = el("button", { className: "picker-row", type: "button", role: "option" });
        const icon = el("svg", { viewBox: "0 0 16 16" });
        icon.innerHTML = row.up
          ? '<path d="M8 13V3M3.5 7.5L8 3l4.5 4.5"/>'
          : '<path d="M2.5 6.5h11v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM4 4.5h8M5 2.5h6"/>';
        btn.appendChild(icon);
        btn.appendChild(el("span", { className: "name", textContent: row.name }));
        btn.addEventListener("click", () => loadFs(row.up ? doc.parent : joinPath(pickerPath, row.name)));
        fsListEl.appendChild(btn);
      }
    }
    if (doc.warning) fsError(doc.warning);
    if (doc.truncated) fsError("Showing the first folders only.");
  } catch {
    fsError("Bridge unreachable — is `keel serve` running?");
  }
}
function setWorkdirUI(path) {
  workdir = path || null;
  for (const id of ["workdir-pill-chat", "workdir-pill-code"]) {
    const pill = $(id);
    if (!pill) continue;
    pill.hidden = !workdir;
    pill.querySelector("span").textContent = workdir ? `working in: ${baseName(workdir)}` : "";
    pill.title = workdir ? `Working folder: ${workdir}` : "No working folder set";
  }
}

/* recent working folders — kept in THIS machine's storage, capped */
const RECENT_DIRS_KEY = "keel_recent_workdirs_v1";
function loadRecentDirs() {
  try { return JSON.parse(localStorage.getItem(RECENT_DIRS_KEY) || "[]"); } catch { return []; }
}
function saveRecentDirs(list) {
  try { localStorage.setItem(RECENT_DIRS_KEY, JSON.stringify(list.slice(0, 10))); } catch {}
}
function recordRecentDir(path) {
  if (!path) return;
  const rest = loadRecentDirs().filter((p) => p !== path);
  saveRecentDirs([path, ...rest]);
}
const folderMenu = $("folder-menu");
const fmSearch = $("fm-search");
const fmList = $("fm-list");
function renderFolderList(filter) {
  const needle = (filter || "").trim().toLowerCase();
  fmList.textContent = "";
  const dirs = loadRecentDirs().filter((p) => !needle || p.toLowerCase().includes(needle));
  if (!dirs.length) {
    fmList.appendChild(el("p", { className: "fm-empty", textContent: needle
      ? "No folder matches that name."
      : "Nothing picked yet — choose one below." }));
    return;
  }
  for (const path of dirs) {
    const btn = el("button", { className: "fm-item", type: "button", role: "menuitem", title: path });
    const icon = el("svg", { viewBox: "0 0 16 16" });
    icon.innerHTML = '<path d="M2.5 6.5h11v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM4 4.5h8M5 2.5h6"/>';
    btn.appendChild(icon);
    btn.appendChild(el("span", { className: "n", textContent: baseName(path) }));
    const parent = path.split(/[\\/]+/).filter(Boolean);
    btn.appendChild(el("span", { className: "d", textContent: parent.length >= 2 ? parent[parent.length - 2] : "" }));
    btn.addEventListener("click", () => { toggleFolderMenu(false); applyWorkdir(path); });
    fmList.appendChild(btn);
  }
}
function toggleFolderMenu(open) {
  const show = open === undefined ? folderMenu.hidden : open;
  folderMenu.hidden = !show;
  if (show) {
    fmSearch.value = "";
    renderFolderList("");
    fmSearch.focus();
  }
}
fmSearch.addEventListener("input", () => renderFolderList(fmSearch.value));
$("fm-open").addEventListener("click", () => { toggleFolderMenu(false); openFsPicker(); });
document.addEventListener("click", (ev) => {
  if (folderMenu.hidden) return;
  if (!folderMenu.contains(ev.target) && !ev.target.closest("#chip-computer")) toggleFolderMenu(false);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !folderMenu.hidden) toggleFolderMenu(false);
});
async function applyWorkdir(path) {
  try {
    const r = await fetch("/api/workdir", {
      method: "POST", headers: jsonHeaders(), body: JSON.stringify({ path }),
    });
    const doc = await r.json().catch(() => ({}));
    if (!r.ok) { fsError(doc.error || `bridge refused (http ${r.status}).`); return; }
    recordRecentDir(doc.path);
    setWorkdirUI(doc.path);
    closeFsPicker();
    systemNote(doc.path
      ? `working folder set to ${doc.path} — the agent's tools will run there.`
      : "working folder reset — the agent runs from the bridge's folder.", "system", state.surface);
  } catch {
    fsError("Bridge unreachable — is `keel serve` running?");
  }
}
$("fs-use").addEventListener("click", () => applyWorkdir(pickerPath));
$("fs-reset").addEventListener("click", () => applyWorkdir(null));
$("fs-close").addEventListener("click", closeFsPicker);
$("fs-backdrop").addEventListener("click", closeFsPicker);
$("fs-up").addEventListener("click", () => {
  if (!pickerPath) return;
  const trimmed = pickerPath.replace(/[\\/]+$/, "");
  const idx = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  loadFs(idx > 0 ? trimmed.slice(0, idx) : trimmed.slice(0, idx + 1));
});

/* ---------- key bindings shared by overlays ---------- */
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    if (!picker.hidden) closeFsPicker();
    if (!settingsPanel.hidden) closeSettings();
  }
});

/* ---------- window chrome / sidebar ---------- */
const toggleSidebar = () => rootEl.classList.toggle("sidebar-hidden");
$("tgl-menu").addEventListener("click", toggleSidebar);
$("tgl-sidebar").addEventListener("click", toggleSidebar);
$("win-min").addEventListener("click", toggleSidebar);
$("win-restore").addEventListener("click", () => rootEl.classList.toggle("sidebar-hidden"));
$("win-close").addEventListener("click", () => window.close());
$("nav-back").addEventListener("click", () => history.back());
$("nav-forward").addEventListener("click", () => history.forward());
$("folder-chat").addEventListener("click", openFsPicker);
document.querySelectorAll(".idea").forEach((btn) =>
  btn.addEventListener("click", () => {
    setSurface("chat");
    prompts.chat.value = btn.dataset.prompt || "";
    prompts.chat.focus();
  }));
$("start-new").addEventListener("click", () => { prompts.code.focus(); });
$("start-auto").addEventListener("click", () => {
  if (!acceptRisk()) {
    systemNote("Autopilot first needs 'I accept the risk of bypass mode' in Providers → Session.", "denied", "code");
    openSettings("providers");
    return;
  }
  requestMode("bypassPermissions");
  systemNote("Autopilot armed — Keel will not ask before running tools. Stay nearby.", "system", "code");
});
$("chip-computer").addEventListener("click", () => toggleFolderMenu());
$("chip-mode").addEventListener("click", () => {
  const idx = MODE_CYCLE.indexOf(currentMode());
  requestMode(MODE_CYCLE[(idx + 1) % MODE_CYCLE.length]);
});
$("btn-term").addEventListener("click", () =>
  systemNote("There is no terminal inside this browser surface. The live terminal lives in the Keel Fleet console — this surface drives the agent with prompts.", "system", state.surface));
$("btn-files").addEventListener("click", () =>
  systemNote("No file browser here — ask the agent instead: it reads and writes your tree with its tools. Try: “list the project tree and find the tests”.", "system", state.surface));

$("copy-transcript").addEventListener("click", () => {
  const text = [...threads[state.surface].querySelectorAll(".msg")]
    .map((m) => `[${m.querySelector(".role")?.textContent || "?"}] ${m.querySelector(".body")?.textContent || ""}`)
    .join("\n\n");
  navigator.clipboard?.writeText(text).catch(() => {});
});
$("clear-transcript").addEventListener("click", () => {
  threads[state.surface].textContent = "";
  showEmptyState(state.surface);
});

/* ================================================================= startup */

syncModeUI();
renderRecents();
setSurface(localStorage.getItem("keel_surface") === "code" ? "code" : "chat", { focus: false });
if (window.innerWidth <= 900) rootEl.classList.add("sidebar-hidden");
loadSettings().then(() => { refreshProviders(); hydrateGeneral(); refreshUsage(); }).catch(() => {});
fetch("/api/workdir", { headers: fsHeaders() })
  .then((r) => (r.ok ? r.json() : null))
  .then((doc) => { if (doc && doc.path) setWorkdirUI(doc.path); })
  .catch(() => {});

if (!bridge.live) {
  systemNote("demo mode — open the URL printed by `keel serve` for the real backend", "system", state.surface);
} else {
  bridge.listen("keel:event", (message) => {
    const line = typeof message === "string" ? message :
      (message && typeof message.payload === "string" ? message.payload : "");
    try { handleEvent(JSON.parse(line), state.runSurface || state.surface); } catch { /* malformed line */ }
  });
  bridge.listen("keel:done", () => finishRun());
}

if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

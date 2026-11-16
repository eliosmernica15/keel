"use strict";

/* Keel Desktop & Keel Code — one PWA, two surfaces.
   Surface A (Keel Desktop): the Keel chat hero. Surface B (Keel Code): the
   coding console. Both ride the same local bridge (/api/run, NDJSON) and
   share one permission/provider config (Customize panel) and one session
   state. Works standalone in a browser (demo mode, clearly labelled) or
   inside Tauri against the real keel sidecar (window.__TAURI__). */

const $ = (id) => document.getElementById(id);
const rootEl = document.querySelector(".app");

const threads = { chat: $("thread-chat"), code: $("thread-code") };
const views = { chat: $("view-chat"), code: $("view-code") };
const prompts = { chat: $("prompt-chat"), code: $("prompt-code") };
const sendBtns = { chat: $("btn-send-chat"), code: $("btn-send-code") };

const state = {
  running: false,
  runSurface: null,          // surface the live run belongs to
  surface: "chat",
  sessionId: null,
  turns: 0,
  tokens: 0,
};

const surfaceName = { chat: "Keel Desktop", code: "Keel Code" };

/* ============================================================ surface switch */

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
          .then((r) => r.ok ? r.json() : { providers: [] })
          .then((doc) => doc.providers || [])
          .catch(() => []);
      },
      listen() { return Promise.resolve(() => {}); },
    };
  }
  // file:// fallback — clearly labelled fixture, no network, no process
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
  Object.assign(node, props || {});
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

const threadOf = (surface) => threads[surface] || threads[state.surface];

function hideEmptyState(surface) {
  if (surface === "chat") {
    const hero = $("hero-chat");
    if (hero) hero.classList.add("hidden");
  } else {
    const start = $("start-code");
    if (start) start.classList.add("hidden");
  }
}

function showEmptyState(surface) {
  if (surface === "chat") {
    const hero = $("hero-chat");
    if (hero) hero.classList.remove("hidden");
  } else {
    const start = $("start-code");
    if (start) start.classList.remove("hidden");
  }
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
    const pre = el("div", { className: isError ? "tool-result-error" : "tool-call", textContent: text.slice(0, 4000) });
    body.appendChild(pre);
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
      if (sub === "hook_response") {
        systemNote(`hook ${evt.hook_name}: ${evt.verdict}`, "system", s);
        return;
      }
      return;
    }
    case "assistant": {
      const blocks = evt.message?.content || [];
      for (const block of blocks) {
        if (block.type === "text") {
          appendMessage("assistant", s === "code" ? "keel code" : "keel", (body) => {
            body.textContent = block.text;
          }, s);
        } else if (block.type === "tool_use") {
          renderToolUse(block, s);
        } else if (block.type === "thinking") {
          appendMessage("system", "thinking", (body) => {
            body.textContent = block.thinking || block.text || "";
          }, s);
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

/* ----------------------------------------------------------------- control */

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

function currentMode() { return $("mode-select").value; }
function acceptRisk() { return $("accept-risk").checked; }

function syncModeUI() {
  const label = MODE_LABEL[currentMode()] || currentMode();
  $("mode-pill").textContent = label;
  $("chip-mode-label").textContent = label;
  $("provider-pill").textContent = $("provider-select").value;
  $("model-pill-chat").textContent = `Keel · ${$("provider-select").value}`;
}

function requestMode(mode) {
  if (mode === "bypassPermissions" && !acceptRisk()) {
    systemNote("bypass requires 'I accept the risk of bypass mode' in Customize → Session — not enabling it.", "denied", state.surface);
    return false;
  }
  $("mode-select").value = mode;
  syncModeUI();
  return true;
}

function send(surface) {
  const active = surface || state.surface;
  const promptEl = prompts[active];
  const prompt = promptEl.value.trim();
  if (!prompt || state.running) return;

  const permission_mode = currentMode();
  const okRisk = acceptRisk();
  if (permission_mode === "bypassPermissions" && !okRisk) {
    systemNote("bypass mode requires 'I accept the risk' before sending", "denied", active);
    openConfig();
    return;
  }

  appendMessage("user", "you", (body) => { body.textContent = prompt; }, active);
  addRecent(prompt, active);
  state.runSurface = active;
  startRun();

  const provider = $("provider-select").value;
  const payload = { prompt, provider, permission_mode, accept_risk: okRisk };
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

/* --------------------------------------------------------------- recents */

const RECENT_KEY = "keel_recents_v1";
const RECENT_CAP = 50;
let recentFilter = "";

function loadRecents() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}
function saveRecents(items) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, RECENT_CAP))); } catch { /* storage full or private mode */ }
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
      if (item.surface === "code") {
        icon.innerHTML = '<path d="M5.5 5L2.5 8l3 3M10.5 5l3 3-3 3M9 4l-2 8"/>';
      } else {
        icon.innerHTML = '<path d="M9.5 3.5h-5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h.5v2l2.5-2h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2z"/>';
      }
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

/* -------------------------------------------------------- folder picker */
/* Local-bridge directory navigator. Works only against `keel serve` — the
   public site doesn't have it, by design. */

const fsToken = () => {
  const p = new URLSearchParams(location.search);
  return p.get("t") || sessionStorage.getItem("keel_token") || "";
};
const fsHeaders = () => ({ "X-Keel-Token": fsToken() });
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
    if (doc.parent) {
      rows.push({ name: "..", up: true });
    }
    for (const dir of doc.dirs || []) rows.push({ name: dir.name });
    fsListEl.textContent = "";
    if (!rows.length) {
      fsListEl.appendChild(el("p", { className: "picker-empty", textContent: "No subfolders here — this folder itself can be used." }));
    } else {
      for (const row of rows) {
        const btn = el("button", { className: "picker-row", type: "button", role: "option" });
        const icon = el("svg", { viewBox: "0 0 16 16" });
        if (row.up) {
          icon.innerHTML = '<path d="M8 13V3M3.5 7.5L8 3l4.5 4.5"/>';
        } else {
          icon.innerHTML = '<path d="M2.5 6.5h11v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM4 4.5h8M5 2.5h6"/>';
        }
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

async function applyWorkdir(path) {
  try {
    const r = await fetch("/api/workdir", {
      method: "POST",
      headers: { ...fsHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const doc = await r.json().catch(() => ({}));
    if (!r.ok) { fsError(doc.error || `bridge refused (http ${r.status}).`); return; }
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
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !picker.hidden) closeFsPicker(); });

/* ----------------------------------------------------------------- wiring */

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
$("nav-new").addEventListener("keydown", (ev) => { if (ev.key === "Enter") $("nav-new").click(); });

const configPanel = $("config-panel");
const openConfig = () => { configPanel.hidden = false; };
$("nav-customize").addEventListener("click", openConfig);
$("nav-customize").addEventListener("keydown", (ev) => { if (ev.key === "Enter") openConfig(); });
$("btn-close-config").addEventListener("click", () => { configPanel.hidden = true; });
$("model-pill-chat").addEventListener("click", openConfig);

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
    systemNote("Autopilot first needs 'I accept the risk of bypass mode' in Customize → Session.", "denied", "code");
    openConfig();
    return;
  }
  requestMode("bypassPermissions");
  systemNote("Autopilot armed — Keel will not ask before running tools. Stay nearby.", "system", "code");
});

$("chip-computer").addEventListener("click", openFsPicker);
$("chip-mode").addEventListener("click", () => {
  const idx = MODE_CYCLE.indexOf(currentMode());
  const next = MODE_CYCLE[(idx + 1) % MODE_CYCLE.length];
  requestMode(next);
});

$("btn-term").addEventListener("click", () =>
  systemNote("There is no terminal inside this browser surface. The live terminal lives in the Keel Fleet console — this surface drives the agent with prompts.", "system", state.surface));
$("btn-files").addEventListener("click", () =>
  systemNote("No file browser here — ask the agent instead: it reads and writes your tree with its tools. Try: “list the project tree and find the tests”.", "system", state.surface));

$("mode-select").addEventListener("change", syncModeUI);
$("provider-select").addEventListener("change", syncModeUI);
$("accept-risk").addEventListener("change", () => {
  if (!$("accept-risk").checked && currentMode() === "bypassPermissions") {
    $("mode-select").value = "default";
  }
  syncModeUI();
});

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

/* ----------------------------------------------------------------- startup */

mkBridge; // (bridge already constructed above)
syncModeUI();
renderRecents();
setSurface(localStorage.getItem("keel_surface") === "code" ? "code" : "chat", { focus: false });
if (window.innerWidth <= 900) rootEl.classList.add("sidebar-hidden");
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
    try { handleEvent(JSON.parse(line), state.runSurface || state.surface); } catch { /* skip malformed line */ }
  });
  bridge.listen("keel:done", () => finishRun());
  bridge.providers().then((rows) => {
    for (const row of rows) {
      const key = `KEEL_${String(row.name).toUpperCase().replace(/-/g, "_")}_API_KEY`;
      const item = document.querySelector(`.key-list li[data-key="${key}"]`);
      if (item) {
        const stateEl = item.querySelector(".key-state");
        stateEl.textContent = row.configured ? "set" : "unset";
        stateEl.classList.toggle("on", row.configured);
      }
    }
  }).catch(() => {});
}

// PWA: register the app-shell service worker (only over http(s))
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

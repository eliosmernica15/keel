"use strict";

/* Keel — public mirror build for https://keel-desktop.vercel.app
   Same UI as the local app (http://127.0.0.1:8744 via `keel serve`), but the
   backend is entirely client-side: this page has NO local bridge, no agent,
   no file access. Chat streams straight from your browser to your provider
   (OpenRouter / Google AI Studio) with the key you save in Settings →
   Providers — the key lives in THIS browser's localStorage and nowhere
   else. Anything that needs a local backend (folder attach, agent runs,
   skills, connectors, import/export) says so honestly in the UI. */

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

/* ====================================================================
   mirror build — client-side provider engine (no local bridge exists).
   Keys/models come from THIS browser's localStorage (keel_mirror_settings_v1).
   ==================================================================== */
const MIRROR_SETTINGS_KEY = "keel_mirror_settings_v1";
const MIRROR_USAGE_KEY = "keel_mirror_usage_v1";
const REPO = "https://github.com/eliosmernica15/keel";
const mirrorNote = "Keel is a local, private agent — nothing runs on this page. "
  + "Install it and this exact screen becomes the real thing: git clone " + REPO + ".git, then `cd keel` and `python -m keel serve`. "
  + "Or add an OpenRouter / Google AI Studio key in Settings → Providers — replies will stream straight from your browser (no tools, no files).";
// openrouter/google only — the mirror cannot reach providers that need a
// server-side agent loop. Attribution headers identify Keel to OpenRouter.
const OPENROUTER_ATTRIBUTION = {
  "HTTP-Referer": "https://keel-desktop.vercel.app",
  "X-OpenRouter-Title": "Keel",
  "X-OpenRouter-Categories": "general-chat",
};
const MIRROR_PROVIDER_DEFS = {
  openrouter: {
    name: "openrouter", label: "OpenRouter", tag: "unified gateway · browser → openrouter.ai", hint: "sk-or-.",
    defaultModel: "openrouter/auto",
    verifyUrl: (key) => "https://openrouter.ai/api/v1/auth/key",
    verifyHeaders: (key) => ({ Authorization: `Bearer ${key}`, ...OPENROUTER_ATTRIBUTION }),
    catalogUrl: () => "https://openrouter.ai/api/v1/models",
    catalogHeaders: () => ({ ...OPENROUTER_ATTRIBUTION }),
    parseCatalog: (doc) => (Array.isArray(doc?.data) ? doc.data.map((m) => m?.id) : []),
    chat: (key, model, messages) => ({
      url: "https://openrouter.ai/api/v1/chat/completions",
      init: {
        method: "POST",
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json", ...OPENROUTER_ATTRIBUTION },
        body: JSON.stringify({ model, stream: true, usage: { include: true }, messages }),
      },
      extractDelta: (evt) => evt?.choices?.[0]?.delta?.content || "",
      extractUsage: (evt) => (evt?.usage
        ? { prompt_tokens: evt.usage.prompt_tokens || 0, completion_tokens: evt.usage.completion_tokens || 0 }
        : null),
    }),
  },
  google: {
    name: "google", label: "Google AI Studio", tag: "gemini · browser → googleapis.com", hint: "AIza.",
    defaultModel: "gemini-2.0-flash",
    verifyUrl: (key) => `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
    verifyHeaders: () => ({}),
    catalogUrl: (key) => `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
    catalogHeaders: () => ({}),
    parseCatalog: (doc) => (Array.isArray(doc?.models) ? doc.models.map((m) => String(m?.name || "").replace(/^models\//, "")) : []),
    chat: (key, model, messages) => {
      const sys = messages.find((m) => m.role === "system");
      const convo = messages.filter((m) => m.role !== "system");
      return {
        url: `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?alt=sse&key=${encodeURIComponent(key)}`,
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...(sys ? { systemInstruction: { parts: [{ text: sys.content }] } } : {}),
            contents: convo.map((m) => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] })),
          }),
        },
        extractDelta: (evt) => (evt?.candidates?.[0]?.content?.parts || []).map((p) => p?.text || "").join(""),
        extractUsage: (evt) => (evt?.usageMetadata
          ? { prompt_tokens: evt.usageMetadata.promptTokenCount || 0, completion_tokens: evt.usageMetadata.candidatesTokenCount || 0 }
          : null),
      };
    },
  },
};
function loadMirrorSettings() {
  try { return JSON.parse(localStorage.getItem(MIRROR_SETTINGS_KEY) || "{}") || {}; } catch { return {}; }
}
let mirrorSettings = loadMirrorSettings();
const getProviders = () => (mirrorSettings.providers && typeof mirrorSettings.providers === "object" ? mirrorSettings.providers : {});
const configuredProvider = () => {
  const p = getProviders();
  if (p.openrouter?.key) return "openrouter";
  if (p.google?.key) return "google";
  return null;
};
const providerModel = (name) => (getProviders()[name] && getProviders()[name].model) || MIRROR_PROVIDER_DEFS[name].defaultModel;
function saveMirrorSettings(patch) {
  mirrorSettings = {
    ...mirrorSettings,
    ...patch,
    ui: { ...(mirrorSettings.ui || {}), ...(patch.ui || {}) },
    providerConfig: {
      ...(mirrorSettings.providerConfig || {}),
      ...(patch.providerConfig || {}),
      models: { ...((mirrorSettings.providerConfig || {}).models || {}), ...((patch.providerConfig || {}).models || {}) },
    },
  };
  try { localStorage.setItem(MIRROR_SETTINGS_KEY, JSON.stringify(mirrorSettings)); } catch {}
  return mirrorSettings;
}
function loadUsage() {
  try { return JSON.parse(sessionStorage.getItem(MIRROR_USAGE_KEY) || '{"prompts":0,"replies":0,"tokens":0}'); } catch { return { prompts: 0, replies: 0, tokens: 0 }; }
}
function bumpUsage(kind) {
  try {
    const u = loadUsage();
    u[kind] = (u[kind] || 0) + 1;
    sessionStorage.setItem(MIRROR_USAGE_KEY, JSON.stringify(u));
  } catch {}
  if (typeof refreshUsage === "function") refreshUsage();
}
function bumpTokens(n) {
  if (!n) return;
  try {
    const u = loadUsage();
    u.tokens = (u.tokens || 0) + n;
    sessionStorage.setItem(MIRROR_USAGE_KEY, JSON.stringify(u));
  } catch {}
  if (typeof refreshUsage === "function") refreshUsage();
}
function fetchCatalog(name) {
  const def = MIRROR_PROVIDER_DEFS[name];
  const key = getProviders()[name]?.key || "";
  return fetch(def.catalogUrl(key), { headers: def.catalogHeaders() })
    .then((r) => { if (!r.ok) throw new Error(`catalog http ${r.status}`); return r.json(); })
    .then((doc) => def.parseCatalog(doc).filter(Boolean).slice(0, 300));
}

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
/* mirror build - no local bridge exists. Chat streams client-side to the
   provider you linked in Settings -> Providers (BYOK). */
async function mirrorSend(payload) {
  const surface = state.runSurface;
  bumpUsage("prompts");
  const history = [...threadOf(surface).querySelectorAll(".msg")].map((m) => {
    const role = (m.querySelector(".role")?.textContent || "").trim();
    const text = (m.querySelector(".body")?.textContent || "").trim();
    const isUser = role === "you";
    const isKeel = /^keel/i.test(role);
    return text && (isUser || isKeel) ? { role: isUser ? "user" : "assistant", content: text } : null;
  }).filter(Boolean);
  const configured = configuredProvider();
  const named = payload && payload.provider && payload.provider !== "auto"
    && MIRROR_PROVIDER_DEFS[payload.provider] && getProviders()[payload.provider]?.key
    ? payload.provider : null;
  const picked = named || configured;
  if (!picked) {
    appendMessage("assistant", surface === "code" ? "keel code" : "keel", (body) => {
      body.textContent = mirrorNote;
    }, surface);
    bumpUsage("replies");
    finishRun();
    return "mirror";
  }
  const def = MIRROR_PROVIDER_DEFS[picked];
  const key = getProviders()[picked].key;
  const model = providerModel(picked);
  const instructions = (uiSettings.instructions || "").trim();
  const messages = [
    ...(instructions ? [{ role: "system", content: instructions }] : []),
    ...history,
  ];
  const holder = { body: null };
  appendMessage("assistant", surface === "code" ? "keel code" : "keel", (body) => {
    holder.body = body;
    body.textContent = "";
  }, surface);
  const scroll = () => { const t = threadOf(surface); if (t) t.scrollTop = t.scrollHeight; };
  try {
    const { url, init, extractDelta, extractUsage } = def.chat(key, model, messages);
    const resp = await fetch(url, init);
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => "");
      throw new Error(`http ${resp.status} - ${text.slice(0, 200)}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let full = "";
    let usage = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const linesOut = buffer.split("\n");
      buffer = linesOut.pop() || "";
      for (const raw of linesOut) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (!data || data === "[DONE]") continue;
        let evt;
        try { evt = JSON.parse(data); } catch { continue; }
        const delta = extractDelta(evt);
        if (delta) {
          full += delta;
          holder.body.textContent = full;
          scroll();
        }
        const u = extractUsage(evt);
        if (u) usage = u;
      }
    }
    if (!holder.body.textContent.trim()) holder.body.textContent = full || "(empty reply)";
    if (usage) {
      bumpTokens((usage.prompt_tokens || 0) + (usage.completion_tokens || 0));
      state.tokens += (usage.prompt_tokens || 0) + (usage.completion_tokens || 0);
    }
    state.turns += 1;
    const tEl = $("turn-count"); if (tEl) tEl.textContent = `${state.turns} turns`;
    const kEl = $("token-count"); if (kEl) kEl.textContent = `${state.tokens} tokens`;
    updateRing();
  } catch (err) {
    holder.body.textContent = `the provider refused: ${String((err && err.message) || err).slice(0, 240)}`;
  }
  bumpUsage("replies");
  finishRun();
  return "mirror";
}
function mkBridge() {
  return {
    live: false,
    send(payload) { return mirrorSend(payload); },
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
  const cap = label.charAt(0).toUpperCase() + label.slice(1);
  $("mode-pill").textContent = label;
  $("chip-perm-label").textContent = cap;
  $("chip-perm").classList.toggle("bypass", currentMode() === "bypassPermissions");
  document.querySelectorAll("#pop-perm .pop-item").forEach((item) => {
    item.classList.toggle("sel", item.dataset.mode === currentMode());
  });
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
  const pending = attachments[active];
  const attachNote = pending.length
    ? `\n\n[attachments: ${pending.map((f) => f.name).join(", ")}]`
    : "";
  const outbound = (instructions ? `${instructions}\n\n` : "") + raw;
  const wire = pending.length ? outbound + attachmentBlock(pending) : outbound;
  appendMessage("user", "you", (body) => { body.textContent = outbound + attachNote; }, active);
  addRecent(raw, active);
  state.runSurface = active;
  attachments[active] = [];
  renderAttachments(active);
  startRun();

  const provider = currentProvider();
  const payload = {
    prompt: wire,
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
/* ================================================================ attachments
   The + (Add) button in either composer opens an attach menu: upload files
   (Ctrl+U) or pick a folder on this machine via the File System Access API.
   Attachments are read as text and inlined into the next message as
   read-only context. Caps keep payloads sane: 40 files, 256 KB per file,
   512 KB total. Binary files are skipped. */
const attachments = { chat: [], code: [] };
const ATTACH_MAX_FILES = 40;
const ATTACH_MAX_FILE = 256 * 1024;
const ATTACH_MAX_TOTAL = 512 * 1024;
const attachInput = $("attach-file-input");
const attachmentBytes = (list) => list.reduce((sum, f) => sum + f.bytes, 0);
const fmtBytes = (n) => (n >= 1024 * 1024 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

function renderAttachments(surface) {
  const box = $(`attachments-${surface}`);
  if (!box) return;
  const list = attachments[surface];
  box.textContent = "";
  box.hidden = list.length === 0;
  list.forEach((file, index) => {
    const chip = el("span", { className: "attach-chip", title: file.name });
    const icon = el("svg", { viewBox: "0 0 16 16" });
    icon.innerHTML = '<path d="M3 3.5a1.5 1.5 0 0 1 1.5-1.5h4.2L13 6.3V12.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 3 12.5z"/><path d="M9 2v4.5h4.5"/>';
    chip.appendChild(icon);
    chip.appendChild(el("span", { className: "n", textContent: file.name }));
    chip.appendChild(el("span", { className: "sz", textContent: fmtBytes(file.bytes) }));
    const drop = el("button", { className: "x", type: "button", "aria-label": `Remove ${file.name}`, title: "Remove" });
    drop.innerHTML = '<svg viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg>';
    drop.addEventListener("click", () => {
      attachments[surface].splice(index, 1);
      renderAttachments(surface);
    });
    chip.appendChild(drop);
    box.appendChild(chip);
  });
}
function noteSkipped(surface, reasons) {
  if (!reasons.length) return;
  systemNote(`skipped ${reasons.length}: ${reasons.slice(0, 3).join("; ")}${reasons.length > 3 ? "; …" : ""}`, "system", surface);
}
function attachmentBlock(list) {
  return `\n\n[Attached files — read-only context, ${list.length} file(s)]\n` + list.map((f) =>
    `### ${f.name} (${fmtBytes(f.bytes)})\n${f.content}`).join("\n\n");
}
function addAttachments(surface, files) {
  const skipped = [];
  let total = attachmentBytes(attachments[surface]);
  for (const file of files) {
    if (attachments[surface].length >= ATTACH_MAX_FILES) { skipped.push(`${file.name} (file cap)`); continue; }
    if (file.bytes > ATTACH_MAX_FILE) { skipped.push(`${file.name} (too big)`); continue; }
    if (total + file.bytes > ATTACH_MAX_TOTAL) { skipped.push(`${file.name} (size cap)`); continue; }
    attachments[surface].push(file);
    total += file.bytes;
  }
  renderAttachments(surface);
  noteSkipped(surface, skipped);
}
async function fileToAttachment(file) {
  const text = await file.text();
  if (text.includes("\0")) return null; // binary
  return { name: file.name, bytes: file.size, content: text };
}
async function readFileHandle(handle, relName) {
  try {
    const file = await handle.getFile();
    if (file.size > ATTACH_MAX_FILE) return { skip: `${relName} (too big)` };
    const text = await file.text();
    if (text.includes("\0")) return { skip: `${relName} (binary)` };
    return { file: { name: relName, bytes: file.size, content: text } };
  } catch (err) {
    return { skip: `${relName} (unreadable)` };
  }
}
async function collectFromDirectory(dirHandle, prefix, out, skipped, depth = 0) {
  if (depth > 3 || out.length >= ATTACH_MAX_FILES) return;
  for await (const entry of dirHandle.values()) {
    if (out.length >= ATTACH_MAX_FILES) return;
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.kind === "directory") {
      await collectFromDirectory(entry, rel, out, skipped, depth + 1);
    } else if (entry.kind === "file") {
      const result = await readFileHandle(entry, rel);
      if (result.file) out.push(result.file);
      else skipped.push(result.skip);
    }
  }
}

let attachSurface = "chat";
function closeAttachMenu() {
  const menu = $("attach-menu");
  if (!menu) return;
  menu.hidden = true;
  for (const id of ["attach-chat", "attach-code"]) $(id).classList.remove("on");
}
function openAttachMenu(surface) {
  const menu = $("attach-menu");
  attachSurface = surface;
  const btn = $(surface === "code" ? "attach-code" : "attach-chat");
  const r = btn.getBoundingClientRect();
  menu.hidden = false;
  const h = menu.offsetHeight;
  menu.style.left = `${Math.max(8, Math.min(r.left - 4, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.bottom = `${window.innerHeight - r.top + 8}px`;
  menu.style.top = "";
  btn.classList.add("on");
}
function toggleAttachMenu(surface) {
  const menu = $("attach-menu");
  const opening = menu.hidden;
  closeAttachMenu();
  if (opening) openAttachMenu(surface);
}
for (const surface of ["chat", "code"]) {
  $(surface === "code" ? "attach-code" : "attach-chat").addEventListener("click", (ev) => {
    ev.stopPropagation();
    toggleAttachMenu(surface);
  });
}
$("attach-menu").addEventListener("click", (ev) => ev.stopPropagation());
document.addEventListener("click", closeAttachMenu);
window.addEventListener("resize", closeAttachMenu);

$("attach-menu-files").addEventListener("click", () => {
  closeAttachMenu();
  attachInput.click();
});
$("attach-menu-folder").addEventListener("click", async () => {
  closeAttachMenu();
  const surface = attachSurface;
  if (!window.showDirectoryPicker) {
    systemNote("Picking a folder needs Chrome or Edge on this page — use Attach files…, or run `keel serve` and use its folder picker.", "system", surface);
    return;
  }
  let dirHandle;
  try {
    dirHandle = await window.showDirectoryPicker({ mode: "read" });
  } catch (err) {
    if (err && err.name === "AbortError") return;
    systemNote(`couldn't open the folder picker: ${String((err && err.message) || err).slice(0, 120)}`, "system", surface);
    return;
  }
  const collected = [];
  const skipped = [];
  try {
    await collectFromDirectory(dirHandle, dirHandle.name, collected, skipped);
  } catch (err) {
    systemNote(`couldn't read the folder: ${String((err && err.message) || err).slice(0, 120)}`, "system", surface);
    return;
  }
  if (!collected.length) {
    systemNote("no readable text files found there (binaries and oversize files are skipped)", "system", surface);
    if (skipped.length) noteSkipped(surface, skipped);
    return;
  }
  addAttachments(surface, collected);
  if (skipped.length) noteSkipped(surface, skipped);
  systemNote(`attached ${collected.length} file(s) from “${dirHandle.name}” — sent with your next message as read-only context`, "system", surface);
});
attachInput.addEventListener("change", async () => {
  const surface = attachSurface;
  const files = [];
  const skipped = [];
  for (const file of attachInput.files || []) {
    try {
      const result = await fileToAttachment(file);
      if (result) files.push(result);
      else skipped.push(`${file.name} (binary)`);
    } catch {
      skipped.push(`${file.name} (unreadable)`);
    }
  }
  attachInput.value = "";
  if (files.length) addAttachments(surface, files);
  if (skipped.length) noteSkipped(surface, skipped);
});

/* ================================================================ recents */

const RECENT_KEY = "keel_recents_v1";
const RECENT_CAP = 50;
let recentFilter = "";
let showArchived = false;
function loadRecents() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}
function saveRecents(items) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(items.slice(0, RECENT_CAP))); } catch { /* full/private */ }
}
function patchItem(id, patch) {
  saveRecents(loadRecents().map((item) => (item.id === id ? { ...item, ...patch } : item)));
  renderRecents();
}
function addRecent(text, surface) {
  const items = loadRecents();
  items.unshift({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, text, surface, ts: Date.now(), pinned: false, unread: false, archived: false });
  saveRecents(items);
  renderRecents();
}
function togglePin(id) {
  const items = loadRecents();
  const target = items.find((i) => i.id === id);
  patchItem(id, { pinned: !(target && target.pinned) });
}
function toggleUnread(id) {
  const items = loadRecents();
  const target = items.find((i) => i.id === id);
  patchItem(id, { unread: !(target && target.unread) });
}

/* ---------------------------------------------------- chat item context menu */

const recentsMenu = $("recents-menu");
let menuItemId = null;

function populateSectionFlyout(container, currentItem) {
  container.textContent = "";
  const items = loadRecents();
  const names = [...new Set(items.map((i) => i.section).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })).slice(0, 8);
  for (const name of names) {
    const b = el("button", { className: "fly-item", type: "button" });
    b.textContent = name;
    if (currentItem.section === name) b.appendChild(el("span", { className: "tag", textContent: "current" }));
    b.addEventListener("click", () => { patchItem(menuItemId, { section: name }); closeRecentsMenu(); });
    container.appendChild(b);
  }
  const fresh = el("button", { className: "fly-item fly-new", type: "button" });
  fresh.textContent = "New section…";
  fresh.addEventListener("click", () => {
    const name = window.prompt("New section name:");
    if (name && name.trim()) patchItem(menuItemId, { section: name.trim() });
    closeRecentsMenu();
  });
  container.appendChild(fresh);
}

function openRecentsMenu(item, anchor) {
  menuItemId = item.id;
  recentsMenu.hidden = false;
  // position: open upwards when near the bottom
  const mw = 240, mh = recentsMenu.offsetHeight || 320;
  let left = Math.max(8, Math.min(window.innerWidth - mw - 8, anchor.right - mw));
  let top = anchor.bottom + 6;
  if (top + mh > window.innerHeight - 8) top = Math.max(8, anchor.top - mh - 6);
  recentsMenu.style.left = `${left}px`;
  recentsMenu.style.top = `${top}px`;
  // reflect item state
  recentsMenu.querySelector('[data-action="unread"] .ctx-label').textContent = item.unread ? "Mark as read" : "Mark as unread";
  recentsMenu.querySelector('[data-action="pin"] .ctx-label').textContent = item.pinned ? "Unpin" : "Pin";
  recentsMenu.querySelector('[data-action="archive"] .ctx-label').textContent = item.archived ? "Unarchive" : "Archive";
  $("ctx-detach").hidden = !item.section;
  // fill flyouts
  populateFlyout("project", $("project-list"), item.project, "Remove from project");
  populateFlyout("group", $("group-list"), item.group, "Move out of group");
  populateSectionFlyout($("section-list"), item);
  anchor.focus?.({ preventScroll: true });
}
function closeRecentsMenu() {
  recentsMenu.hidden = true;
  menuItemId = null;
}
function menuAction(action) {
  const id = menuItemId;
  if (!id) return;
  const items = loadRecents();
  const item = items.find((i) => i.id === id);
  if (!item) { closeRecentsMenu(); return; }
  switch (action) {
    case "unread": toggleUnread(id); break;
    case "pin": togglePin(id); break;
    case "rename": {
      const next = window.prompt("Rename this chat:", item.text);
      if (next && next.trim()) patchItem(id, { text: next.trim() });
      break;
    }
    case "fork": {
      const fork = { ...item, id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, ts: Date.now(), pinned: false, unread: true, archived: false };
      items.unshift(fork);
      saveRecents(items.slice(0, RECENT_CAP));
      renderRecents();
      setSurface(item.surface === "code" ? "code" : "chat");
      prompts[state.surface].value = item.text;
      updateRing();
      prompts[state.surface].focus();
      systemNote("Forked — prompt ready in a fresh conversation.", "system", state.surface);
      break;
    }
    case "detach":
      patchItem(id, { section: undefined });
      break;
    case "open-new-tab":
      window.open(location.href, "_blank", "noopener");
      break;
    case "open-new-window":
      window.open(location.href, "_blank", "width=1280,height=860,noopener");
      break;
    case "archive":
      patchItem(id, { archived: !item.archived });
      if (!item.archived) systemNote("Archived — hidden from Recents; toggle “Archived” to see it again.", "system", state.surface);
      break;
    case "delete":
      if (!window.confirm("Delete this chat from this machine? This can't be undone.")) break;
      saveRecents(items.filter((i) => i.id !== id));
      renderRecents();
      break;
  }
  closeRecentsMenu();
}
recentsMenu.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-action]");
  if (btn) { ev.stopPropagation(); menuAction(btn.dataset.action); }
});
document.addEventListener("click", (ev) => {
  if (!recentsMenu.hidden && !recentsMenu.contains(ev.target)) closeRecentsMenu();
});
document.addEventListener("keydown", (ev) => {
  if (!recentsMenu.hidden) {
    if (ev.key === "Escape") { closeRecentsMenu(); return; }
    const k = ev.key.toLowerCase();
    if (k === "u") { ev.preventDefault(); menuAction("unread"); }
    else if (k === "p") { ev.preventDefault(); menuAction("pin"); }
    else if (k === "r") { ev.preventDefault(); menuAction("rename"); }
    else if (k === "f") { ev.preventDefault(); menuAction("fork"); }
    else if (k === "a") { ev.preventDefault(); menuAction("archive"); }
    else if (k === "d") { ev.preventDefault(); menuAction("delete"); }
  }
});

function populateFlyout(kind, container, current, clearLabel) {
  container.textContent = "";
  const items = loadRecents();
  const names = [...new Set(items.map((i) => i[kind]).filter(Boolean))].slice(0, 6);
  for (const name of names) {
    const b = el("button", { className: "fly-item", type: "button" });
    b.textContent = name;
    if (name === current) b.appendChild(el("span", { className: "tag", textContent: "current" }));
    b.addEventListener("click", () => { patchItem(menuItemId, { [kind]: name }); closeRecentsMenu(); });
    container.appendChild(b);
  }
  if (current) {
    const clear = el("button", { className: "fly-item fly-clear", type: "button" });
    clear.textContent = clearLabel;
    clear.addEventListener("click", () => { patchItem(menuItemId, { [kind]: undefined }); closeRecentsMenu(); });
    container.appendChild(clear);
  }
  const fresh = el("button", { className: "fly-item fly-new", type: "button" });
  fresh.textContent = kind === "project" ? "New project…" : "New group…";
  fresh.addEventListener("click", () => {
    const name = window.prompt(kind === "project" ? "New project name:" : "New group name:");
    if (name && name.trim()) patchItem(menuItemId, { [kind]: name.trim() });
    closeRecentsMenu();
  });
  container.appendChild(fresh);
}

function refreshArchivedToggle(items) {
  const archived = (items || loadRecents()).filter((i) => i.archived).length;
  const btn = $("btn-show-archived");
  btn.hidden = archived === 0;
  btn.textContent = `Archived (${archived})`;
  btn.classList.toggle("on", showArchived);
}
$("btn-show-archived").addEventListener("click", () => { showArchived = !showArchived; renderRecents(); });

const moreIconSvg = '<svg viewBox="0 0 16 16"><circle cx="3.5" cy="8" r="1.3"/><circle cx="8" cy="8" r="1.3"/><circle cx="12.5" cy="8" r="1.3"/></svg>';

function makeVisitRow(item) {
  const row = el("div", { className: `item${item.pinned ? " pinned" : ""}${item.unread ? " unread" : ""}${item.archived ? " archived" : ""}`, tabindex: "0", role: "button", title: item.text });
  if (item.unread) row.appendChild(el("span", { className: "dot" }));
  const icon = el("svg", { className: "ic", viewBox: "0 0 16 16" });
  icon.innerHTML = item.surface === "code"
    ? '<path d="M5.5 5L2.5 8l3 3M10.5 5l3 3-3 3M9 4l-2 8"/>'
    : '<path d="M9.5 3.5h-5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h.5v2l2.5-2h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2z"/>';
  row.appendChild(icon);
  row.appendChild(el("span", { className: "t", textContent: item.text }));
  const tag = item.project || item.group;
  if (tag) row.appendChild(el("span", { className: "tag-chip", textContent: tag }));
  const more = el("button", { className: "more", "aria-label": "Chat options", type: "button" });
  more.innerHTML = moreIconSvg;
  more.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (!recentsMenu.hidden && menuItemId === item.id) { closeRecentsMenu(); return; }
    openRecentsMenu(item, more.getBoundingClientRect());
  });
  row.appendChild(more);
  const launch = () => {
    setSurface(item.surface === "code" ? "code" : "chat");
    prompts[state.surface].value = item.text;
    patchItem(item.id, { unread: false });
    prompts[state.surface].focus();
  };
  row.addEventListener("click", launch);
  row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); launch(); } });
  return row;
}

function renderRecents() {
  const items = loadRecents();
  const match = (item) => !recentFilter || item.text.toLowerCase().includes(recentFilter);
  const pinnedList = $("pinned-list");
  const recentsList = $("recents-list");
  const groupsBox = $("recents-groups");
  pinnedList.textContent = "";
  recentsList.textContent = "";
  groupsBox.textContent = "";
  const visible = items.filter((item) => showArchived || !item.archived);
  const pinned = visible.filter((item) => item.pinned && match(item));
  const restAll = visible.filter((item) => !item.pinned && match(item));
  const sectionNames = [...new Set(restAll.map((i) => i.section).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  for (const name of sectionNames) {
    const lbl = el("div", { className: "lbl" });
    lbl.appendChild(el("span", { textContent: name }));
    groupsBox.appendChild(lbl);
    const box = el("div", { className: "recents" });
    for (const item of restAll.filter((i) => i.section === name && match(i))) box.appendChild(makeVisitRow(item));
    groupsBox.appendChild(box);
  }
  for (const item of pinned) pinnedList.appendChild(makeVisitRow(item));
  for (const item of restAll.filter((i) => !i.section).slice(0, 20)) {
    if (match(item)) recentsList.appendChild(makeVisitRow(item));
  }
  $("recents-empty").style.display = items.length === 0 ? "" : "none";
  refreshArchivedToggle(items);
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

/* mirror: settings live in THIS browser (localStorage), never on a server */
async function loadSettings() {
  const m = loadMirrorSettings();
  uiSettings = m.ui || {};
  providerConfig = m.providerConfig || { preferred: configuredProvider() || "auto", models: {} };
  providerConfig.models = providerConfig.models || {};
  return m;
}

async function saveSettingsPatch(patch) {
  const merged = saveMirrorSettings(patch || {});
  uiSettings = merged.ui || uiSettings;
  providerConfig = merged.providerConfig || providerConfig;
  providerConfig.models = providerConfig.models || {};
  syncModeUI();
  return merged;
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
  { name: "openrouter", label: "OpenRouter", tag: "browser → openrouter.ai", hint: "sk-or-…" },
  { name: "google", label: "Google AI Studio", tag: "gemini · browser → googleapis.com", hint: "AIza…" },
];

function providerStatusLine(p) {
  if (!p) return { text: "not linked", cls: "unset" };
  return { text: `saved •• ${p.key_hint || "…"} — this browser only`, cls: "" };
}

async function refreshProviders() {
  const providers = getProviders();
  const infoByName = Object.fromEntries(Object.entries(providers).map(([name, entry]) => [
    name, { configured: Boolean(entry && entry.key), key_source: "mirror", key_hint: (entry && entry.hint) || String((entry && entry.key) || "").slice(-4), default_model: MIRROR_PROVIDER_DEFS[name]?.defaultModel },
  ]));
  const linked = Object.keys(MIRROR_PROVIDER_DEFS).filter((name) => infoByName[name]?.configured).length;
  $("rail-configured").textContent = `${linked} linked`;
  const preferred = providerConfig.preferred && providerConfig.preferred !== "auto"
    ? providerConfig.preferred
    : (configuredProvider() || "auto");
  $("preferred-select").value = preferred;
  $("provider-select").value = preferred;

  const wrap = $("provider-rows");
  wrap.textContent = "";
  for (const def of PROVIDER_DEFS) {
    const info = infoByName[def.name] || null;
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
        ${info && info.configured ? '<button class="btn-ghost small danger remove-btn">Remove saved key</button>' : ""}
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
      if (!confirm(`Forget the saved ${def.label} key in this browser?`)) return;
      const next = { ...getProviders() };
      delete next[def.name];
      saveMirrorSettings({ providers: next });
      const msg = els(".verify-msg", row)[0];
      if (msg) { msg.textContent = "forgotten"; msg.className = "hint"; }
      await loadSettings();
      refreshProviders();
    });
    els(".verify-btn", row)[0].addEventListener("click", async () => {
      const key = keyInput.value.trim();
      if (!key) { verifyMsg.textContent = "key is empty"; verifyMsg.className = "hint err"; return; }
      verifyMsg.textContent = "verifying against the provider…";
      verifyMsg.className = "hint";
      const mdef = MIRROR_PROVIDER_DEFS[def.name];
      try {
        const resp = await fetch(mdef.verifyUrl(key), { headers: mdef.verifyHeaders(key) });
        if (!resp.ok) {
          verifyMsg.textContent = `rejected — HTTP ${resp.status}`;
          verifyMsg.className = "hint err";
          return;
        }
        const prior = getProviders()[def.name] || {};
        saveMirrorSettings({ providers: { ...getProviders(), [def.name]: { key, hint: key.slice(-4), model: prior.model || mdef.defaultModel } } });
        verifyMsg.textContent = "saved — this browser only; nothing else can read it";
        verifyMsg.className = "hint ok";
        keyInput.value = "";
        await loadSettings();
        refreshProviders();
      } catch {
        verifyMsg.textContent = "could not reach the provider — offline, or it refused us";
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
      let models = [];
      try {
        models = await fetchCatalog(def.name);
      } catch (err) {
        meta.textContent = getProviders()[def.name]?.key
          ? `could not reach the provider (${String((err && err.message) || err).slice(0, 80)})`
          : "no key configured — save one first";
        meta.className = "hint err";
        return;
      }
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
            const current = getProviders()[def.name];
            if (current) saveMirrorSettings({ providers: { ...getProviders(), [def.name]: { ...current, model: id } } });
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
  const u = loadUsage();
  $("stat-turns").textContent = String(u.replies || 0);
  $("stat-tokens").textContent = String(u.tokens || 0);
}
function storageBytes() {
  let total = 0;
  for (const key of Object.keys(localStorage)) total += localStorage.getItem(key)?.length || 0;
  return total;
}
function refreshStorageUsage() {
  const kb = storageBytes() / 1024;
  $("storage-usage").textContent = `localStorage on this browser: ~${kb.toFixed(1)} KB across ${localStorage.length} key(s) — cleared only by you.`;
}
$("clear-recents-pwa").addEventListener("click", () => { saveRecents([]); renderRecents(); refreshStorageUsage(); });
$("clear-visit-prompts").addEventListener("click", () => {
  try { sessionStorage.removeItem(MIRROR_USAGE_KEY); } catch {}
  refreshUsage();
  refreshStorageUsage();
});
/* mirror: export carries UI + provider preferences, never keys */
$("export-settings").addEventListener("click", () => {
  const m = loadMirrorSettings();
  const doc = {
    ui: m.ui || {},
    providerConfig: m.providerConfig || {},
    providers: Object.fromEntries(Object.entries(m.providers || {}).map(([name, p]) => [
      name, { hint: p.hint, model: p.model },
    ])),
    _kind: "keel-mirror-settings",
  };
  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "keel-mirror-settings.json";
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
  if (!confirm("Merge this file into this browser's mirror settings?")) return;
  const includeKeys = $("import-include-keys").checked;
  try {
    const patch = {};
    if (doc.ui && typeof doc.ui === "object") patch.ui = doc.ui;
    if (doc.providerConfig && typeof doc.providerConfig === "object") patch.providerConfig = doc.providerConfig;
    if (includeKeys && doc.providers && typeof doc.providers === "object") {
      const next = { ...getProviders() };
      for (const [name, p] of Object.entries(doc.providers)) {
        if (p && typeof p === "object" && p.key) next[name] = { key: p.key, hint: p.hint || String(p.key).slice(-4), model: p.model || MIRROR_PROVIDER_DEFS[name]?.defaultModel };
      }
      patch.providers = next;
    }
    saveMirrorSettings(patch);
    note.textContent = includeKeys
      ? "imported — UI, preferences and keys merged into this browser"
      : "imported — UI and provider preferences merged (keys untouched)";
    note.className = "hint ok";
    await loadSettings();
    refreshProviders();
  } catch {
    note.textContent = "import failed";
    note.className = "hint err";
  }
});

/* ---------- Keel Code / Desktop / System / Developer ---------- */

function refreshBridgeStatus() {
  $("keelcode-status").textContent = "n/a — the mirror has no local bridge; chat works client-side";
  $("keeldesktop-status").textContent = "n/a — the mirror has no local bridge; chat works client-side";
}
async function refreshSystem() {
  $("sys-version").textContent = "mirror";
  $("sys-origin").textContent = "none — this browser only";
  $("sys-workdir").textContent = "not available — the mirror cannot see your disk";
}
$("goto-code").addEventListener("click", () => { setSurface("code"); closeSettings(); });
$("goto-desktop").addEventListener("click", () => { setSurface("chat"); closeSettings(); });
$("goto-connectors").addEventListener("click", () => showPane("connectors"));

/* ---------- Skills / Connectors ---------- */

async function loadSkills() {
  const wrap = $("skills-list");
  wrap.textContent = "";
  wrap.innerHTML = '<p class="hint">Not available on the mirror — skills live on your machine and run inside `keel serve`. Install Keel to use them.</p>';
}
async function loadConnectors() {
  const wrap = $("connectors-list");
  wrap.textContent = "";
  wrap.innerHTML = '<p class="hint">Not available on the mirror — MCP connectors live in the local fleet console (`keel fleet`). Install Keel to use them.</p>';
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
  if (!bridge.live) {
    systemNote("the folder browser is part of the local app — this mirror cannot list your files. Run `keel serve` and open the printed URL.", "system", state.surface);
    return;
  }
  picker.hidden = false;
  fsError("");
  loadFs(workdir || "");
}
function closeFsPicker() { picker.hidden = true; }
async function loadFs(path) {
  if (!bridge.live) return;
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
  const chip = $("chip-folder");
  if (chip) {
    chip.querySelector("span").textContent = workdir ? baseName(workdir) : "Select folder…";
    chip.title = workdir
      ? `Working folder: ${workdir}\nThe agent's tools run inside this folder`
      : "Choose the working folder — the agent's tools run inside it";
  }
  const sysWorkdir = $("sys-workdir");
  if (sysWorkdir) sysWorkdir.textContent = workdir || "not available — the mirror cannot see your disk";
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
/* footer popovers — environment · folder · permissions (Keel Code footer) */
const pops = { env: $("pop-env"), folder: $("pop-folder"), perm: $("pop-perm") };
const chips = { env: $("chip-env"), folder: $("chip-folder"), perm: $("chip-perm") };
const anyPopOpen = () => Object.values(pops).some((p) => p && !p.hidden);
function closePops(except) {
  for (const key of Object.keys(pops)) {
    if (key === except || !pops[key]) continue;
    pops[key].hidden = true;
    if (chips[key]) chips[key].classList.remove("on");
  }
}
function togglePop(key) {
  const pop = pops[key];
  if (!pop) return;
  const show = pop.hidden;
  closePops();
  if (!show) return;
  pop.hidden = false;
  const r = chips[key].getBoundingClientRect();
  const w = pop.offsetWidth;
  pop.style.left = `${Math.max(8, Math.min(r.left - 1, window.innerWidth - w - 8))}px`;
  pop.style.bottom = `${window.innerHeight - r.top + 6}px`;
  pop.style.top = "";
  chips[key].classList.add("on");
  if (key === "folder") {
    const search = $("pop-folder-search");
    search.value = "";
    renderPopFolder("");
    search.focus();
  }
}
function renderPopFolder(filter) {
  const needle = (filter || "").trim().toLowerCase();
  const list = $("pop-folder-list");
  list.textContent = "";
  const dirs = loadRecentDirs().filter((p) => !needle || p.toLowerCase().includes(needle));
  if (!dirs.length) {
    const empty = el("p", { className: "pop-empty" });
    empty.textContent = needle
      ? "No recent folder matches — press Enter to try it as a full path, or Open folder… to browse the disk."
      : "No recent folders yet — Open folder… to browse the disk.";
    list.appendChild(empty);
    return;
  }
  for (const path of dirs) {
    const btn = el("button", {
      className: `pop-row${path === workdir ? " active" : ""}`,
      type: "button", role: "option", title: path,
    });
    const icon = el("svg", { viewBox: "0 0 16 16" });
    icon.innerHTML = '<path d="M2 4.2a1 1 0 0 1 1-1h3.2l1.5 1.6H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z"/>';
    btn.appendChild(icon);
    btn.appendChild(el("span", { className: "n", textContent: baseName(path) }));
    const parts = path.split(/[\\/]+/).filter(Boolean);
    btn.appendChild(el("span", {
      className: "d",
      textContent: path === workdir ? "current" : (parts.length >= 2 ? parts[parts.length - 2] : ""),
    }));
    btn.addEventListener("click", () => { closePops(); applyWorkdir(path); });
    list.appendChild(btn);
  }
}
$("chip-env").addEventListener("click", (ev) => { ev.stopPropagation(); togglePop("env"); });
$("chip-folder").addEventListener("click", (ev) => { ev.stopPropagation(); togglePop("folder"); });
$("chip-perm").addEventListener("click", (ev) => { ev.stopPropagation(); togglePop("perm"); });
for (const pop of Object.values(pops)) {
  if (pop) pop.addEventListener("click", (ev) => ev.stopPropagation());
}
$("pop-folder-search").addEventListener("input", (ev) => renderPopFolder(ev.target.value));
$("pop-folder-search").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    const value = ev.target.value.trim();
    if (value) { closePops(); applyWorkdir(value); }
  }
});
$("pop-folder-open").addEventListener("click", () => { closePops(); openFsPicker(); });
$("pop-perm").addEventListener("click", (ev) => {
  const item = ev.target.closest(".pop-item");
  if (!item) return;
  if (requestMode(item.dataset.mode)) closePops();
});
$("pop-env").addEventListener("click", (ev) => {
  if (ev.target.closest(".pop-sel")) closePops();
});
document.addEventListener("click", () => closePops());
window.addEventListener("resize", () => closePops());
async function applyWorkdir(path) {
  if (!bridge.live) {
    systemNote("this public mirror cannot see or bind your disk — folder attach is part of the local app. Run `keel serve` and open the printed URL.", "system", state.surface);
    return;
  }
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
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "u") {
    ev.preventDefault();
    attachSurface = state.surface;
    closeAttachMenu();
    attachInput.click();
    return;
  }
  if (ev.key === "Escape") {
    if (!$("attach-menu").hidden) { closeAttachMenu(); return; }
    if (anyPopOpen()) { closePops(); return; }
    if (!recentsMenu.hidden) { closeRecentsMenu(); return; }
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
if (bridge.live) {
  fetch("/api/workdir", { headers: fsHeaders() })
    .then((r) => (r.ok ? r.json() : null))
    .then((doc) => { if (doc && doc.path) setWorkdirUI(doc.path); })
    .catch(() => {});
}

if (!bridge.live) {
  systemNote("mirror mode — this page is running fully in your browser. Chat streams straight from your browser to your provider via the key in Settings → Providers (OpenRouter or Google AI Studio). No key yet? Replies here explain how to install the local app.", "system", state.surface);
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

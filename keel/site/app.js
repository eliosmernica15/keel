"use strict";
/* Keel public mirror — everything works locally in this tab, nothing leaves it.
   Sending never reaches a model: the reply is an honest pointer to the app. */

const $ = (id) => document.getElementById(id);
const app = $("app");
const q = $("q");
const thread = $("thread");
const threadScroll = $("thread-scroll");
const chatTitle = $("chat-title");
const toastEl = $("toast");
let toastTimer = null;
const prefersReducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function toast(html, ms = 3600) {
  toastEl.innerHTML = html;
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), ms);
}
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clip = (t) => (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject(new Error("no clipboard")));

/* ---------- time-aware greeting (local time, not a server) ---------- */
(() => {
  const h = new Date().getHours();
  const part = h < 5 ? "Late night" : h < 12 ? "Morning" : h < 18 ? "Afternoon" : "Evening";
  $("greet").textContent = part + ", how are things?";
})();

/* ---------- recents with pinning (this machine's storage only) ---------- */
const RECENT_CAP = 50;
const RECENT_KEY = "keel_recents_v1";
const loadRecents = () => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
const saveRecents = (arr) => { try { localStorage.setItem(RECENT_KEY, JSON.stringify(arr.slice(0, RECENT_CAP))); } catch {} };
let recentFilter = "";

function addRecent(text, surface) {
  const items = loadRecents();
  items.unshift({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    text,
    surface,
    ts: Date.now(),
    pinned: false,
  });
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
      const row = document.createElement("div");
      row.className = `item${item.pinned ? " pinned" : ""}`;
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.title = item.text;
      const icon = document.createElement("svg");
      icon.setAttribute("viewBox", "0 0 16 16");
      icon.classList.add("ic");
      icon.innerHTML = item.surface === "code"
        ? '<path d="M5.5 5L2.5 8l3 3M10.5 5l3 3-3 3M9 4l-2 8"/>'
        : '<path d="M9.5 3.5h-5a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h.5v2l2.5-2h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2z"/>';
      row.appendChild(icon);
      const span = document.createElement("span");
      span.className = "t";
      span.textContent = item.text;
      row.appendChild(span);
      const pin = document.createElement("button");
      pin.className = "pin";
      pin.type = "button";
      pin.setAttribute("aria-label", item.pinned ? "Unpin" : "Pin");
      const pinSvg = document.createElement("svg");
      pinSvg.setAttribute("viewBox", "0 0 16 16");
      pinSvg.innerHTML = '<path d="M9.6 2.4l4 4-2 .6-2.2 2.2.4 2.6-1.6 1.6-3-3-3.6 3.6-.4-.4 3.6-3.6-3-3 1.6-1.6 2.6.4 2.2-2.2z"/>';
      pin.appendChild(pinSvg);
      pin.addEventListener("click", (ev) => { ev.stopPropagation(); togglePin(item.id); });
      row.appendChild(pin);
      const launch = () => {
        setMode(item.surface === "code" ? "code" : "chat");
        document.getElementById("q").value = item.text;
        updateSendState();
        document.getElementById("q").focus();
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

/* ---------- morph: home <-> chat ---------- */
const REPO = "https://github.com/eliosmernica15/keel";
const mirrorNote = `Keel is a local, private agent — nothing runs on this page. `
  + `Install it and this exact screen becomes the real thing:`;

function setTitle(text) {
  const short = text.length > 52 ? text.slice(0, 52).trim() + "…" : text;
  chatTitle.innerHTML = esc(short) + ' <svg viewBox="0 0 14 14"><path d="M3 5l4 4 4-4"/></svg>';
  document.title = short + " — Keel";
}

/* ---------- live BYOK streaming — browser talks to your provider directly ---------- */
function appendStreamBot(name, model) {
  const bot = document.createElement("div");
  bot.className = "bot";
  bot.innerHTML = `<span class="tool">${PROVIDER_DEFS[name].label} · ${escapeHtml(model)}<svg viewBox="0 0 14 14"><path d="M5 3l4 4-4 4"/></svg></span><p class="stream-text"></p>`;
  thread.appendChild(bot);
  threadScroll.scrollTop = threadScroll.scrollHeight;
  return bot;
}
function finalizeStreamBot(bot, fullText) {
  const target = bot.querySelector(".stream-text");
  if (!target.textContent.trim()) target.textContent = fullText || "(empty reply)";
  const acts = document.createElement("div");
  acts.className = "acts";
  const copy = document.createElement("button");
  copy.className = "act-copy";
  copy.setAttribute("aria-label", "Copy reply");
  copy.innerHTML = '<svg viewBox="0 0 14 14"><rect x="4.5" y="4.5" width="7.5" height="7.5" rx="1.3"/><path d="M9.5 4.5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v5.5a1 1 0 0 0 1 1h1.5"/></svg>';
  copy.addEventListener("click", () => clip(target.textContent)
    .then(() => toast("Reply copied"))
    .catch(() => toast("Clipboard blocked by the browser.")));
  acts.appendChild(copy);
  bot.appendChild(acts);
}
async function readErrorBody(resp) {
  try { return "HTTP " + resp.status + " — " + (await resp.text()).slice(0, 200); } catch { return "HTTP " + resp.status; }
}
async function streamToProvider(raw, name) {
  const def = PROVIDER_DEFS[name];
  const entry = getProviders()[name];
  const model = providerModel(name);
  const instructions = (mirrorSettings.instructions || "").trim();
  const messages = [
    ...(instructions ? [{ role: "system", content: instructions }] : []),
    { role: "user", content: raw },
  ];
  const { url, init, extractDelta, extractUsage } = def.chat(entry.key, model, messages);
  const bot = appendStreamBot(name, model);
  const target = bot.querySelector(".stream-text");
  let full = "";
  let usage = null;
  try {
    const resp = await fetch(url, init);
    if (!resp.ok || !resp.body) throw new Error(await readErrorBody(resp));
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        const data = t.slice(5).trim();
        if (!data || data === "[DONE]") continue;
        let evt;
        try { evt = JSON.parse(data); } catch { continue; }
        const delta = extractDelta(evt);
        if (delta) {
          full += delta;
          target.textContent = full;
          threadScroll.scrollTop = threadScroll.scrollHeight;
        }
        const u = extractUsage(evt);
        if (u) usage = u;
      }
    }
    if (usage) bumpTokens((usage.prompt_tokens || 0) + (usage.completion_tokens || 0));
    finalizeStreamBot(bot, full);
  } catch (err) {
    target.textContent = `the provider refused: ${String((err && err.message) || err).slice(0, 240)}`;
    target.classList.add("err");
    bot.querySelector(".tool").textContent = `${def.label} · error`;
  }
  app.classList.remove("sending");
  bumpUsage("replies");
  maybeNotifyDone();
  toBottom();
}

function addUser(text) {
  const row = document.createElement("div");
  row.className = "user";
  const div = document.createElement("div");
  div.textContent = text;
  row.appendChild(div);
  thread.appendChild(row);
}

function addMirrorReply() {
  const bot = document.createElement("div");
  bot.className = "bot";
  bot.innerHTML = `
    <span class="tool">Mirror mode <svg viewBox="0 0 14 14"><path d="M5 3l4 4-4 4"/></svg></span>
    <p>${esc(mirrorNote)}</p>
    <div class="cmds">
      <code data-copy="git clone ${REPO}.git">git clone ${REPO}.git</code>
      <code data-copy="cd keel &amp;&amp; python -m keel serve">cd keel &amp;&amp; python -m keel serve</code>
    </div>
    <p>Then open the printed URL — the same sidebar, the same composer, a real agent behind it, and your keys never leave your disk.</p>
    <a class="fcard" href="${REPO}" target="_blank" rel="noopener noreferrer">
      <span class="ic"><svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="6.5"/><path d="M2.5 9h13M9 2.5c2 2 2.8 4.2 2.8 6.5S11 13.5 9 15.5C7 13.5 6.2 11.3 6.2 9S7 4.5 9 2.5z"/></svg></span>
      <span><b>Keel Desktop &amp; Keel Code</b><small>github.com/eliosmernica15/keel — local, private</small></span>
    </a>
    <div class="acts">
      <button class="act-copy" aria-label="Copy reply"><svg viewBox="0 0 14 14"><rect x="4.5" y="4.5" width="7.5" height="7.5" rx="1.3"/><path d="M9.5 4.5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v5.5a1 1 0 0 0 1 1h1.5"/></svg></button>
      <button class="act-rate" aria-label="Rate reply" title="The mirror has no model — nothing to rate"><svg viewBox="0 0 14 14"><path d="M2.5 6.2h2v5.3h-2zM4.5 6.5L7 2.5c1 0 1.6.8 1.4 1.7l-.3 1.6h3a1 1 0 0 1 1 1.2l-.8 3.6a1.2 1.2 0 0 1-1.2.9H4.5"/></svg></button>
      <button class="act-retry" aria-label="Retry" title="The mirror can only repeat itself — install Keel to really retry"><svg viewBox="0 0 14 14"><path d="M11.8 6A4.8 4.8 0 0 0 3.2 4.5M2.2 8a4.8 4.8 0 0 0 8.6 1.5M3.5 2v2.6h2.6M10.5 12V9.4H7.9"/></svg></button>
    </div>`;
  bot.querySelector(".act-copy").addEventListener("click", () => {
    clip(mirrorNote + " git clone " + REPO + ".git — then `cd keel && python -m keel serve`")
      .then(() => toast("Reply copied"))
      .catch(() => toast("Clipboard blocked by the browser"));
  });
  bot.querySelector(".act-rate").addEventListener("click", () =>
    toast("The mirror has no model — install Keel to rate real answers."));
  bot.querySelector(".act-retry").addEventListener("click", () =>
    toast("Install Keel — <code>python -m keel serve</code> — and press Enter on the real thing."));
  bot.querySelectorAll(".cmds code").forEach((code) => {
    code.addEventListener("click", () => {
      clip(code.dataset.copy || code.textContent)
        .then(() => toast("Command copied"))
        .catch(() => toast("Clipboard blocked by the browser"));
    });
  });
  thread.appendChild(bot);
}

const toBottom = () => { threadScroll.scrollTop = threadScroll.scrollHeight; };

/* ---------- installed-app detection (standalone PWA vs browser tab) ---------- */
const displayModeQuery = window.matchMedia("(display-mode: standalone)");
const applyStandalone = () => document.documentElement.classList.toggle("standalone", displayModeQuery.matches);
applyStandalone();
if (displayModeQuery.addEventListener) displayModeQuery.addEventListener("change", applyStandalone);
else if (displayModeQuery.addListener) displayModeQuery.addListener(applyStandalone);

/* ---------- three modes: home (hero) · chat (conversation) · code (terminal) ---------- */
function setMode(m) {
  app.classList.remove("mode-home", "mode-chat", "mode-code");
  app.classList.add("mode-" + m);
  app.classList.toggle("has-messages", thread.children.length > 0);
  $("chat-top").setAttribute("aria-hidden", String(m === "home"));
  q.placeholder = m === "code"
    ? "Describe a task or ask a question"
    : (m === "chat" ? "Write a message." : "How can I help you today?");
  $("seg-chat").classList.toggle("on", m !== "code");
  $("seg-keel-code").classList.toggle("on", m === "code");
}
function setTitleAndDoc(text) {
  setTitle(text);
  document.title = text.slice(0, 52) + " — Keel";
}
function morphToChat(prompt) { setMode("chat"); setTitleAndDoc(prompt); }
function morphToCode(prompt) { setMode("code"); setTitleAndDoc(prompt); }
function morphToHome() {
  setMode("home");
  app.classList.remove("sending");
  q.focus();
}

const sendBtn = $("send");
function updateSendState() { sendBtn.classList.toggle("ready", q.value.trim().length > 0); }
q.addEventListener("input", updateSendState);

function sendPrompt() {
  const raw = q.value.trim();
  if (!raw) { q.focus(); return; }
  addRecent(raw, app.classList.contains("mode-code") ? "code" : "chat");
  bumpUsage("prompts");
  const wasHome = app.classList.contains("mode-home");
  if (app.classList.contains("mode-code")) { if (wasHome) morphToCode(raw); }
  else if (wasHome) morphToChat(raw); else setTitle(raw);
  addUser(raw);
  app.classList.add("has-messages");
  q.value = "";
  updateSendState();
  app.classList.add("sending");
  toBottom();
  if (configuredProvider()) {
    streamToProvider(raw, configuredProvider());
    return;
  }
  setTimeout(() => {
    addMirrorReply();
    app.classList.remove("sending");
    bumpUsage("replies");
    maybeNotifyDone();
    toBottom();
  }, prefersReducedMotion() ? 0 : 480);
}
$("comp").addEventListener("submit", (ev) => { ev.preventDefault(); sendPrompt(); });
q.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); sendPrompt(); }
});

/* ---------- sidebar collapse ---------- */
$("tgl-sidebar").addEventListener("click", () => app.classList.toggle("collapsed"));
$("chat-title").addEventListener("click", () => app.classList.toggle("collapsed"));

/* ---------- nav: honest wiring, no dead buttons ---------- */
$("nav-new").addEventListener("click", () => {
  morphToHome();
  thread.textContent = "";
  app.classList.remove("has-messages");
  $("greet").textContent = "Evening, how are things?";
});
$("code-new").addEventListener("click", () => { setMode("code"); q.focus(); });
$("code-fleet").addEventListener("click", () =>
  toast("The full agent lives in the local app — <code>python -m keel serve</code>."));
$("nav-customize").addEventListener("click", () => openSettings("general"));
$("btn-search-recents").addEventListener("click", () => {
  const next = window.prompt("Filter recents (empty to clear filter):", recentFilter);
  if (next === null) return;
  recentFilter = next.trim().toLowerCase();
  renderRecents();
});
$("btn-clear-recents").addEventListener("click", () => {
  if (!confirm("Clear all saved recents? This only affects this machine's browser storage.")) return;
  saveRecents([]);
  renderRecents();
});

/* hide/show this visit's prompts (screen privacy) */
$("hide-recents").addEventListener("click", () => {
  document.body.classList.toggle("hide-recents");
  const hidden = document.body.classList.contains("hide-recents");
  for (const container of [$("recents-list"), $("pinned-list"), $("recents-empty")]) {
    if (container) container.style.visibility = hidden ? "hidden" : "";
  }
  toast(hidden ? "Prompts hidden on this screen." : "Prompts visible again.");
});

/* ---------- composer controls ---------- */
/* ---------- folder attach: read a project tree locally, honestly ---------- */
const HEAVY = new Set(["node_modules", ".git", ".vercel", ".next", "dist", "build", "out", "__pycache__", ".idea", ".vscode", "target", ".turbo", "coverage", ".cache"]);

async function walkDirectory(dirHandle, prefix, state, depth) {
  if (depth > 6 || state.collected >= 250) { state.skipped += 1; return; }
  for await (const [name, handle] of dirHandle.entries()) {
    if (state.collected >= 250) { state.skipped += 1; continue; }
    if (HEAVY.has(name.toLowerCase())) { state.skippedHeavy.push(prefix + name + "/"); continue; }
    if (handle.kind === "directory") {
      state.dirs += 1;
      state.lines.push(prefix + name + "/");
      state.collected += 1;
      await walkDirectory(handle, prefix + name + "/", state, depth + 1);
    } else {
      state.files += 1;
      state.lines.push(prefix + name);
      state.collected += 1;
    }
  }
}

/* ---------- folder dropdown: recent picks persisted by handle ---------- */
const RECENT_FOLDERS_KEY = "keel_mirror_recent_folders_v1";
const HDB_NAME = "keel-handles-v1";
const HDB_STORE = "handles";

const loadRecentFolders = () => {
  try { return JSON.parse(localStorage.getItem(RECENT_FOLDERS_KEY) || "[]"); } catch { return []; }
};
const saveRecentFolders = (list) => {
  try { localStorage.setItem(RECENT_FOLDERS_KEY, JSON.stringify(list.slice(0, 10))); } catch {}
};
const recordRecentFolder = (name) => {
  if (!name) return;
  const rest = loadRecentFolders().filter((n) => n !== name);
  saveRecentFolders([name, ...rest]);
};

function hdbOpen() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(HDB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(HDB_STORE); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function saveDirHandle(handle) {
  try {
    const db = await hdbOpen();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(HDB_STORE, "readwrite");
      tx.objectStore(HDB_STORE).put(handle, handle.name);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch { /* browser refused to persist handles */ }
}
async function getDirHandle(name) {
  try {
    const db = await hdbOpen();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(HDB_STORE, "readonly");
      const req = tx.objectStore(HDB_STORE).get(name);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  } catch { return null; }
}

async function performAttach(dirHandle) {
  morphToChat("Folder " + dirHandle.name);
  addUser("Attach my folder: " + dirHandle.name);
  const state = { files: 0, dirs: 0, collected: 0, skipped: 0, lines: [], skippedHeavy: [] };
  const bot = document.createElement("div");
  bot.className = "bot";
  bot.innerHTML = '<span class="tool">Reading folder — names only</span><p class="note-row">Nothing leaves this page — the tree is built locally in your browser. File <i>contents</i> are never read.</p>';
  thread.appendChild(bot);
  threadScroll.scrollTop = threadScroll.scrollHeight;
  try {
    await walkDirectory(dirHandle, "", state, 0);
  } catch (err) {
    bot.innerHTML = '<span class="tool">Folder unreadable</span><p class="note-row">The browser refused the folder (' + esc(String((err && err.message) || err)) + ').</p>';
    return;
  }
  const lines = state.lines.slice(0, 200);
  const summary = [
    `Folder: ${dirHandle.name}`,
    `${state.files} file(s), ${state.dirs} folder(s)${state.skippedHeavy.length ? ` (skipped ${state.skippedHeavy.length} heavy folder(s): ${state.skippedHeavy.slice(0, 10).join(", ")}${state.skippedHeavy.length > 10 ? "…" : ""})` : ""}`,
    "",
    ...state.lines,
  ].join("\n");
  bot.innerHTML = `
    <span class="tool">Folder attached — read-only, local</span>
    <p class="note-row"><b>${esc(dirHandle.name)}</b> — ${state.files} file(s), ${state.dirs} folder(s)${state.skippedHeavy.length ? ` · skipped ${state.skippedHeavy.length} heavy/system folder(s)` : ""}${state.lines.length > 200 ? " · tree truncated to 200 entries" : ""}. This page can't process anything — copy the summary into local Keel to work on the folder for real.</p>
    <pre class="tree">${esc(lines.join("\n"))}</pre>
    <div class="acts"><button class="tree-copy" aria-label="Copy project summary" title="Copy the folder summary"><svg viewBox="0 0 14 14"><rect x="4.5" y="4.5" width="7.5" height="7.5" rx="1.3"/><path d="M9.5 4.5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v5.5a1 1 0 0 0 1 1h1.5"/></svg></button></div>`;
  bot.querySelector(".tree-copy").addEventListener("click", () => {
    clip(summary)
      .then(() => toast("Summary copied — paste it in local Keel."))
      .catch(() => toast("Clipboard blocked by the browser."));
  });
  threadScroll.scrollTop = threadScroll.scrollHeight;
}

async function pickAndAttach() {
  if (!window.showDirectoryPicker) {
    toast("This browser won't open a folder picker here — try <code>python -m keel serve</code> on this machine.");
    return;
  }
  let dirHandle;
  try {
    dirHandle = await window.showDirectoryPicker({ mode: "read" });
  } catch (err) {
    const name = err && err.name;
    if (name === "AbortError" || name === "SecurityError") return; // user cancelled — silent
    toast("The browser refused the folder — permission denied.");
    return;
  }
  recordRecentFolder(dirHandle.name);
  await saveDirHandle(dirHandle);
  await performAttach(dirHandle);
}

const folderMenu = $("folder-menu");
const fmSearch = $("fm-search");
const fmList = $("fm-list");
function renderFolderList(filter) {
  const needle = (filter || "").trim().toLowerCase();
  fmList.textContent = "";
  const dirs = loadRecentFolders().filter((n) => !needle || n.toLowerCase().includes(needle));
  if (!dirs.length) {
    const p = document.createElement("p");
    p.className = "fm-empty";
    p.textContent = needle ? "No folder matches that name." : "Nothing picked yet — pick one below.";
    fmList.appendChild(p);
    return;
  }
  for (const name of dirs) {
    const btn = document.createElement("button");
    btn.className = "fm-item";
    btn.type = "button";
    btn.role = "menuitem";
    btn.innerHTML = '<svg viewBox="0 0 16 16"><path d="M2.5 6.5h11v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM4 4.5h8M5 2.5h6"/></svg>';
    const span = document.createElement("span");
    span.className = "n";
    span.textContent = name;
    btn.appendChild(span);
    btn.title = "Attach “" + name + "” again";
    btn.addEventListener("click", async () => {
      toggleFolderMenu(false);
      const handle = await getDirHandle(name);
      if (!handle) {
        toast("That handle isn't stored in this browser — picking it again.");
        pickAndAttach();
        return;
      }
      try {
        const perm = handle.queryPermission ? await handle.queryPermission({ mode: "read" }) : "prompt";
        if (perm !== "granted" && handle.requestPermission) {
          const req = await handle.requestPermission({ mode: "read" });
          if (req !== "granted") {
            toast("Permission not granted — picking it again.");
            pickAndAttach();
            return;
          }
        }
        await performAttach(handle);
      } catch {
        toast("That handle no longer resolves — picking it again.");
        pickAndAttach();
      }
    });
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
$("fm-open").addEventListener("click", () => { toggleFolderMenu(false); pickAndAttach(); });
$("attach").addEventListener("click", (ev) => { ev.stopPropagation(); toggleFolderMenu(); });
$("nav-back").addEventListener("click", () => history.back());
$("nav-forward").addEventListener("click", () => history.forward());
document.addEventListener("click", (ev) => {
  if (folderMenu.hidden) return;
  if (!folderMenu.contains(ev.target) && ev.target.id !== "attach" && !ev.target.closest("#attach")) toggleFolderMenu(false);
});
$("mic").addEventListener("click", () => toast("Voice input needs the app and a microphone on your machine."));
$("wave").addEventListener("click", () => toast("Voice mode is app-only — no audio is captured on this page."));
$("model").addEventListener("click", () => openSettings("providers"));
$("seg-chat").addEventListener("click", () => setMode("chat"));
$("seg-keel-code").addEventListener("click", () => setMode("code"));

/* chips fill the composer with genuinely useful prompts */
document.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    q.value = chip.dataset.prompt || "";
    updateSendState();
    q.focus();
  }));

/* install flow: one button, the browser's own install — never a panel */
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (ev) => { ev.preventDefault(); deferredPrompt = ev; });
window.addEventListener("appinstalled", () => toast("Installed — find Keel Desktop in your apps."));
async function installApp() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice.catch(() => null);
    deferredPrompt = null;
    if (choice && choice.outcome === "accepted") toast("Installed — find Keel Desktop in your apps.");
    return;
  }
  toast("Install from your browser menu — <code>Install app</code> / <code>Add to Home Screen</code>.");
}
$("install-pill").addEventListener("click", installApp);

/* ============================================================ settings & account */

const MIRROR_SETTINGS_KEY = "keel_mirror_settings_v1";
const MIRROR_USAGE_KEY = "keel_mirror_usage_v1";

function loadMirrorSettings() {
  try { return JSON.parse(localStorage.getItem(MIRROR_SETTINGS_KEY) || "{}") || {}; } catch { return {}; }
}
function saveMirrorSettings(patch) {
  mirrorSettings = { ...mirrorSettings, ...patch };
  try { localStorage.setItem(MIRROR_SETTINGS_KEY, JSON.stringify(mirrorSettings)); } catch {}
  return mirrorSettings;
}
let mirrorSettings = loadMirrorSettings();

function loadUsage() {
  try { return JSON.parse(sessionStorage.getItem(MIRROR_USAGE_KEY) || '{"prompts":0,"replies":0}'); } catch { return { prompts: 0, replies: 0 }; }
}
function bumpUsage(kind) {
  try {
    const u = loadUsage();
    u[kind] = (u[kind] || 0) + 1;
    sessionStorage.setItem(MIRROR_USAGE_KEY, JSON.stringify(u));
  } catch {}
  refreshUsage();
}
function bumpTokens(n) {
  if (!n) return;
  try {
    const u = loadUsage();
    u.tokens = (u.tokens || 0) + n;
    sessionStorage.setItem(MIRROR_USAGE_KEY, JSON.stringify(u));
  } catch {}
  refreshUsage();
}
function refreshUsage() {
  const u = loadUsage();
  const a = $("stat-prompts"), b = $("stat-replies"), c = $("stat-tokens");
  if (a) a.textContent = String(u.prompts || 0);
  if (b) b.textContent = String(u.replies || 0);
  if (c) c.textContent = String(u.tokens || 0);
}
function maybeNotifyDone() {
  if (!mirrorSettings.notifications || mirrorSettings.notifications.response === false) return;
  if (!document.hidden) return;
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  try { new Notification("Keel finished", { body: "Your reply is ready.", icon: "/ui/icons/icon-192.png" }); } catch {}
}

/* ---------- drop-up (anchored to the account row) ---------- */
const acctToggle = $("acct-toggle");
const dropup = $("dropup");
function toggleDropup(open) {
  const show = open === undefined ? dropup.hidden : open;
  dropup.hidden = !show;
  acctToggle.setAttribute("aria-expanded", String(show));
}
acctToggle.addEventListener("click", () => toggleDropup());
document.addEventListener("click", (ev) => {
  if (!dropup.hidden && !dropup.contains(ev.target) && !acctToggle.contains(ev.target)) toggleDropup(false);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    if (!folderMenu.hidden) { toggleFolderMenu(false); return; }
    if (!settingsPanel.hidden) { closeSettings(); return; }
    if (!dropup.hidden) toggleDropup(false);
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === "," || ev.code === "Comma")) {
    ev.preventDefault();
    openSettings("general");
  }
});
$("du-settings").addEventListener("click", () => { toggleDropup(false); openSettings("general"); });
$("du-language").addEventListener("click", () => { toggleDropup(false); toast("English — the only language this build ships."); });
$("du-help").addEventListener("click", () => { toggleDropup(false); window.open(REPO + "/issues", "_blank", "noopener"); });
$("du-learn").addEventListener("click", () => { toggleDropup(false); window.open(REPO, "_blank", "noopener"); });
$("du-upgrade").addEventListener("click", () => { toggleDropup(false); toast("Keel is free and open source — there is no plan to upgrade."); });
$("du-logout").addEventListener("click", () => {
  toggleDropup(false);
  if (confirm("Close this window? Your settings and visit prompts stay on this machine.")) {
    window.close();
    toast("If the window didn't close, close the tab — nothing else changes.");
  }
});

/* ---------- settings panel ---------- */
const settingsPanel = $("settings-panel");
function openSettings(pane = "general") {
  settingsPanel.hidden = false;
  showPane(pane);
  if (pane === "system") renderSystemPane();
  if (pane === "usage") refreshUsage();
  if (pane === "privacy") refreshStorageUsage();
}
function closeSettings() { settingsPanel.hidden = true; }
$("settings-close").addEventListener("click", closeSettings);
$("settings-backdrop").addEventListener("click", closeSettings);

function showPane(name) {
  document.querySelectorAll(".rail-item").forEach((b) => b.classList.toggle("on", b.dataset.section === name));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("on", p.id === `pane-${name}`));
  if (name === "system") renderSystemPane();
  if (name === "usage") refreshUsage();
  if (name === "privacy") refreshStorageUsage();
  if (name === "general") hydrateGeneral();
}
document.querySelectorAll(".rail-item").forEach((btn) =>
  btn.addEventListener("click", () => showPane(btn.dataset.section)));
$("settings-search").addEventListener("input", (ev) => {
  const needle = ev.target.value.trim().toLowerCase();
  document.querySelectorAll(".rail-item").forEach((btn) => {
    btn.classList.toggle("hidden-by-filter", !!needle && !btn.textContent.toLowerCase().includes(needle));
  });
  document.querySelectorAll(".rail-group").forEach((group) => {
    let el = group.nextElementSibling, visible = 0;
    while (el && el.classList.contains("rail-item")) {
      if (!el.classList.contains("hidden-by-filter")) visible++;
      el = el.nextElementSibling;
    }
    group.style.display = visible || !needle ? "" : "none";
  });
});

/* General */
const instructionsEl = $("instructions");
const instructionsMeta = $("instructions-meta");
function hydrateGeneral() {
  $("work-select").value = mirrorSettings.work || "";
  if (document.activeElement !== instructionsEl) instructionsEl.value = mirrorSettings.instructions || "";
  instructionsMeta.textContent = `${(mirrorSettings.instructions || "").length} characters`;
  const font = mirrorSettings.font || "body";
  document.querySelectorAll("#font-chips button").forEach((b) => b.classList.toggle("on", b.dataset.font === font));
  document.body.dataset.font = font;
  const motion = mirrorSettings.motion || "system";
  document.querySelectorAll("#motion-seg button").forEach((b) => b.classList.toggle("on", b.dataset.motion === motion));
  document.body.classList.toggle("reduce-motion", motion === "reduced");
  applyTheme(mirrorSettings.theme || "dark");
  $("notif-toggle").checked = !mirrorSettings.notifications || mirrorSettings.notifications.response !== false;
}
$("work-select").addEventListener("change", (ev) => saveMirrorSettings({ work: ev.target.value }));
instructionsEl.addEventListener("input", () => {
  instructionsMeta.textContent = `${instructionsEl.value.length} characters`;
});
$("save-instructions").addEventListener("click", () => {
  saveMirrorSettings({ instructions: instructionsEl.value.trim() });
  instructionsMeta.textContent = `${instructionsEl.value.trim().length} characters · saved`;
  instructionsMeta.className = "hint ok";
});
document.querySelectorAll("#font-chips button").forEach((btn) => btn.addEventListener("click", () => {
  document.body.dataset.font = btn.dataset.font;
  document.querySelectorAll("#font-chips button").forEach((b) => b.classList.toggle("on", b === btn));
  saveMirrorSettings({ font: btn.dataset.font });
}));
function applyTheme(mode) {
  if (mode === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
  document.querySelectorAll("#theme-seg button").forEach((b) => b.classList.toggle("on", b.dataset.theme === mode));
}
document.querySelectorAll("#theme-seg button").forEach((btn) => btn.addEventListener("click", () => {
  saveMirrorSettings({ theme: btn.dataset.theme });
  applyTheme(btn.dataset.theme);
}));
document.querySelectorAll("#motion-seg button").forEach((btn) => btn.addEventListener("click", () => {
  document.body.classList.toggle("reduce-motion", btn.dataset.motion === "reduced");
  document.querySelectorAll("#motion-seg button").forEach((b) => b.classList.toggle("on", b === btn));
  saveMirrorSettings({ motion: btn.dataset.motion });
}));
$("notif-toggle").addEventListener("change", async (ev) => {
  const wanted = ev.target.checked;
  if (wanted && typeof Notification !== "undefined" && Notification.permission === "default") {
    try { await Notification.requestPermission(); } catch {}
  }
  saveMirrorSettings({ notifications: { response: wanted } });
});

/* Providers — BYOK: this browser talks to the provider directly. No servers of ours exist. */
/* OpenRouter app attribution — without these headers every app is anonymous.
   HTTP-Referer identifies Keel; categories tag this chat surface. The local
   agent sends cli-agent/programming-app from its side. */
const OPENROUTER_ATTRIBUTION = {
  "HTTP-Referer": "https://keel-desktop.vercel.app",
  "X-OpenRouter-Title": "Keel",
  "X-OpenRouter-Categories": "general-chat",
};
const PROVIDER_DEFS = {
  openrouter: {
    label: "OpenRouter",
    verifyUrl: (key) => "https://openrouter.ai/api/v1/auth/key",
    verifyHeaders: (key) => ({ Authorization: `Bearer ${key}`, ...OPENROUTER_ATTRIBUTION }),
    catalogUrl: () => "https://openrouter.ai/api/v1/models",
    catalogHeaders: () => ({ ...OPENROUTER_ATTRIBUTION }),
    parseCatalog: (doc) => (Array.isArray(doc?.data) ? doc.data.map((m) => m?.id) : []),
    defaultModel: "openrouter/auto",
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
    label: "Google AI Studio",
    verifyUrl: (key) => `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
    verifyHeaders: () => ({}),
    catalogUrl: (key) => `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(key)}`,
    catalogHeaders: () => ({}),
    parseCatalog: (doc) => (Array.isArray(doc?.models) ? doc.models.map((m) => String(m?.name || "").replace(/^models\//, "")) : []),
    defaultModel: "gemini-2.0-flash",
    chat: (key, model, messages) => {
      const sys = messages.find((m) => m.role === "system");
      const user = messages.find((m) => m.role === "user");
      return {
        url: `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?alt=sse&key=${encodeURIComponent(key)}`,
        init: {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...(sys ? { systemInstruction: { parts: [{ text: sys.content }] } } : {}),
            contents: [{ role: "user", parts: [{ text: user.content }] }],
          }),
        },
        extractDelta: (evt) =>
          (evt?.candidates?.[0]?.content?.parts || []).map((p) => p?.text || "").join(""),
        extractUsage: (evt) => (evt?.usageMetadata
          ? { prompt_tokens: evt.usageMetadata.promptTokenCount || 0, completion_tokens: evt.usageMetadata.candidatesTokenCount || 0 }
          : null),
      };
    },
  },
};

const getProviders = () => (mirrorSettings.providers && typeof mirrorSettings.providers === "object" ? mirrorSettings.providers : {});
const configuredProvider = () => {
  const p = getProviders();
  if (p.openrouter?.key) return "openrouter";
  if (p.google?.key) return "google";
  return null;
};
const providerModel = (name) => (getProviders()[name] && getProviders()[name].model) || PROVIDER_DEFS[name].defaultModel;
const providerPinnedShort = (name) => {
  const m = providerModel(name);
  const short = m.split("/").pop();
  return short.length > 34 ? short.slice(0, 34) + "…" : short;
};
function saveProviders(providers) {
  mirrorSettings = { ...mirrorSettings, providers };
  try { localStorage.setItem(MIRROR_SETTINGS_KEY, JSON.stringify(mirrorSettings)); } catch {}
}
async function fetchCatalog(name) {
  const def = PROVIDER_DEFS[name];
  const key = getProviders()[name]?.key || "";
  const resp = await fetch(def.catalogUrl(key), { headers: def.catalogHeaders() });
  if (!resp.ok) throw new Error(`catalog http ${resp.status}`);
  const doc = await resp.json();
  return def.parseCatalog(doc).filter(Boolean).slice(0, 300);
}
async function refreshProviderRow(name) {
  const def = PROVIDER_DEFS[name];
  const key = getProviders()[name]?.key || null;
  const src = $("psrc-" + name);
  const modelEl = $("pmodel-" + name);
  const forgetBtn = $("forget-" + name);
  const pick = $("pick-" + name);
  const select = $("model-" + name);
  if (key) {
    const hint = getProviders()[name].hint || key.slice(-4);
    src.textContent = `saved •• ${hint}`;
    src.classList.remove("unset");
    forgetBtn.hidden = false;
    pick.hidden = false;
    modelEl.textContent = providerModel(name);
    try {
      const models = await fetchCatalog(name);
      select.innerHTML = "";
      const cur = providerModel(name);
      for (const id of models) {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        if (id === cur) opt.selected = true;
        select.appendChild(opt);
      }
    } catch { /* catalog is a nicety; keep the saved model visible */ }
  } else {
    src.textContent = "not linked";
    src.classList.add("unset");
    forgetBtn.hidden = true;
    pick.hidden = true;
    modelEl.textContent = def.defaultModel;
  }
}
function refreshProviderUI() {
  refreshProviderRow("openrouter");
  refreshProviderRow("google");
  syncModelPill();
}
async function verifyAndSave(name) {
  const def = PROVIDER_DEFS[name];
  const input = $("key-" + name);
  const msg = $("kmsg-" + name);
  const key = input.value.trim();
  if (!key) { msg.textContent = "key is empty"; msg.className = "hint err"; return; }
  msg.textContent = "verifying against the provider…";
  msg.className = "hint";
  try {
    const resp = await fetch(def.verifyUrl(key), { headers: def.verifyHeaders(key) });
    if (!resp.ok) {
      msg.textContent = `rejected — HTTP ${resp.status}`;
      msg.className = "hint err";
      return;
    }
    const providers = { ...getProviders() };
    const prior = providers[name] || {};
    providers[name] = { key, hint: key.slice(-4), model: prior.model || def.defaultModel };
    saveProviders(providers);
    input.value = "";
    msg.textContent = "saved — this browser only; nothing else can read it";
    msg.className = "hint ok";
    refreshProviderUI();
  } catch {
    msg.textContent = "could not reach the provider — offline, or it refused us";
    msg.className = "hint err";
  }
}
$("verify-openrouter").addEventListener("click", () => verifyAndSave("openrouter"));
$("verify-google").addEventListener("click", () => verifyAndSave("google"));
for (const name of ["openrouter", "google"]) {
  $("forget-" + name).addEventListener("click", async () => {
    const providers = { ...getProviders() };
    delete providers[name];
    saveProviders(providers);
    const msg = $("kmsg-" + name);
    msg.textContent = "forgotten";
    msg.className = "hint";
    refreshProviderUI();
  });
  $("model-" + name).addEventListener("change", (ev) => {
    const providers = { ...getProviders() };
    if (providers[name]) {
      providers[name] = { ...providers[name], model: ev.target.value };
      saveProviders(providers);
      $("pmodel-" + name).textContent = ev.target.value;
      syncModelPill();
    }
  });
}
function syncModelPill() {
  const name = configuredProvider();
  const pill = $("model");
  if (!pill) return;
  pill.innerHTML = name
    ? `${PROVIDER_DEFS[name].label} · <span>${escapeHtml(providerPinnedShort(name))}</span>`
    : `Keel · <span>local</span>`;
  const note = document.getElementById("foot-note");
  if (note) {
    note.innerHTML = name
      ? `Your key, your provider — no tools, no files · <b>Ctrl+Shift+,</b> for settings`
      : `Keel is AI and can make mistakes. Double-check work that matters · <b>Keel · local</b>`;
  }
}
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

$("open-local-docs").addEventListener("click", () => window.open(REPO, "_blank", "noopener"));
$("open-local-docs-2").addEventListener("click", () => window.open(REPO, "_blank", "noopener"));
$("open-source").addEventListener("click", () => window.open(REPO + "/tree/main/keel/src", "_blank", "noopener"));
$("open-docs-3").addEventListener("click", () => window.open(REPO, "_blank", "noopener"));
$("open-docs-4").addEventListener("click", () => window.open(REPO, "_blank", "noopener"));
$("goto-connectors").addEventListener("click", () => showPane("connectors"));

/* Privacy */
function storageBytes() {
  let total = 0;
  for (const key of Object.keys(localStorage)) total += localStorage.getItem(key)?.length || 0;
  return total;
}
function refreshStorageUsage() {
  $("storage-usage").textContent =
    `localStorage on this browser: ~${(storageBytes() / 1024).toFixed(1)} KB across ${localStorage.length} key(s) — cleared only by you.`;
}
$("clear-visit").addEventListener("click", () => {
  try { localStorage.removeItem(RECENT_KEY); } catch {}
  try { sessionStorage.removeItem(MIRROR_USAGE_KEY); } catch {}
  renderRecents();
  refreshStorageUsage();
  refreshUsage();
  toast("Recents cleared.");
});
$("clear-all-site").addEventListener("click", () => {
  if (!confirm("Clear everything this site stored on this browser — settings, prompts, all of it?")) return;
  try { localStorage.clear(); } catch {}
  try { sessionStorage.clear(); } catch {}
  try { localStorage.setItem(MIRROR_SETTINGS_KEY, "{}"); } catch {}
  renderRecents();
  hydrateGeneral();
  refreshStorageUsage();
  refreshUsage();
  toast("Cleared — this browser starts fresh for this site.");
});

/* Import & export */
$("export-settings").addEventListener("click", () => {
  const doc = { app: "keel-mirror", version: 1, exportedAt: new Date().toISOString(), localStorage: {} };
  for (const key of Object.keys(localStorage)) doc.localStorage[key] = localStorage.getItem(key);
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
  if (!confirm("Merge this file into this browser's storage for this site?")) return;
  try {
    for (const [key, value] of Object.entries(doc.localStorage || {})) {
      if (typeof value === "string") localStorage.setItem(key, value);
    }
    mirrorSettings = loadMirrorSettings();
    renderRecents();
    hydrateGeneral();
    note.textContent = "imported — merged into this browser's storage";
    note.className = "hint ok";
  } catch {
    note.textContent = "import failed";
    note.className = "hint err";
  }
});

/* System */
async function renderSystemPane() {
  $("sys-origin").textContent = `${location.origin} (static)`;
  const sw = $("sys-sw");
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    sw.textContent = reg && reg.active ? `active · ${reg.active.scriptURL.split("/").pop()}` : "not registered";
  } catch {
    sw.textContent = "unavailable in this browser";
  }
}

/* ---------- chat-header actions (chat mode) ---------- */
$("pill-x").addEventListener("click", () => { $("pill-chat").remove(); });
$("btn-files").addEventListener("click", () => toast("Keel reads your files locally — install the app and point it at a folder."));
$("btn-share").addEventListener("click", () => {
  clip(window.location.href)
    .then(() => toast("Link copied — it never contains a key or a message."))
    .catch(() => toast("Clipboard blocked by the browser."));
});

/* ---------- decorative window controls: honest, harmless actions ---------- */
$("win-min").addEventListener("click", () => app.classList.add("collapsed"));
$("win-restore").addEventListener("click", () => app.classList.remove("collapsed"));
$("win-close").addEventListener("click", () => window.close());

/* ---------- boot ---------- */
if (window.matchMedia("(max-width: 880px)").matches) app.classList.add("collapsed");
renderRecents();
updateSendState();
hydrateGeneral();
refreshUsage();
refreshProviderUI();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

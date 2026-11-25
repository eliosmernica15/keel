/* Keel in Chrome — background service worker.
 * Local-first: all state lives in chrome.storage.local. No network requests.
 * Every Chrome API access is feature-detected so this worker never throws,
 * even in browsers with partial MV3 side-panel support.
 */
'use strict';

var chromeApi = null;
try {
  chromeApi = globalThis.chrome || globalThis.browser || null;
} catch (_e) {
  chromeApi = null;
}

var DEFAULT_STATE = {
  welcomeSeen: false,
  installedAt: null,
  model: 'Mythos',
  approvalMode: 'Ask before each action',
  activeTab: 'Keel',
  mode: 'Chat',
  contextSource: 'full',
  sessions: [],
  pendingAction: null,
  lastContext: null,
  settings: {
    stream: true,
    autoSave: true,
    keyboardHints: true,
    reduceMotion: false
  }
};

var MODELS = ['Mythos', 'Opus', 'Sonnet', 'Haiku'];
var APPROVAL_MODES = ['Ask before each action', 'Permissions Mode', 'Work autonomously'];
var MAX_SESSIONS = 60;
var MAX_CONTEXT_CHARS = 30000;

function copyDefaults() {
  return JSON.parse(JSON.stringify(DEFAULT_STATE));
}

function normalizeState(raw) {
  var base = copyDefaults();
  if (!raw || typeof raw !== 'object') return base;
  Object.keys(base).forEach(function (key) {
    if (Object.prototype.hasOwnProperty.call(raw, key) && raw[key] !== undefined && raw[key] !== null) {
      base[key] = raw[key];
    }
  });
  if (typeof base.welcomeSeen !== 'boolean') base.welcomeSeen = false;
  if (MODELS.indexOf(base.model) === -1) base.model = DEFAULT_STATE.model;
  if (APPROVAL_MODES.indexOf(base.approvalMode) === -1) base.approvalMode = DEFAULT_STATE.approvalMode;
  if (!Array.isArray(base.sessions)) base.sessions = [];
  else base.sessions = base.sessions.filter(function (s) { return s && typeof s === 'object'; }).slice(0, MAX_SESSIONS);
  if (typeof base.settings !== 'object' || Array.isArray(base.settings)) base.settings = copyDefaults().settings;
  var defaults = copyDefaults().settings;
  Object.keys(defaults).forEach(function (key) {
    if (typeof base.settings[key] !== 'boolean') base.settings[key] = defaults[key];
  });
  return base;
}

function storageArea() {
  try {
    return chromeApi && chromeApi.storage && chromeApi.storage.local ? chromeApi.storage.local : null;
  } catch (_e) {
    return null;
  }
}

async function getState() {
  var area = storageArea();
  if (!area || typeof area.get !== 'function') return copyDefaults();
  try {
    var data = await area.get(null);
    return normalizeState(data);
  } catch (_e) {
    return copyDefaults();
  }
}

async function setState(patch) {
  if (!patch || typeof patch !== 'object') return getState();
  var area = storageArea();
  if (area && typeof area.set === 'function') {
    try {
      await area.set(patch);
    } catch (_e) {
      /* storage is best-effort */
    }
  }
  return getState();
}

function runtimeApi() {
  try {
    return chromeApi && chromeApi.runtime ? chromeApi.runtime : null;
  } catch (_e) {
    return null;
  }
}

function extensionUrl(path) {
  var rt = runtimeApi();
  try {
    if (rt && typeof rt.getURL === 'function') return rt.getURL(path);
  } catch (_e) {
    /* ignore */
  }
  return path;
}

function withTimeout(promise, ms, fallback) {
  return new Promise(function (resolve) {
    var settled = false;
    var timer = setTimeout(function () {
      if (!settled) {
        settled = true;
        resolve(fallback);
      }
    }, ms);
    Promise.resolve(promise).then(function (value) {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        resolve(value);
      }
    }, function () {
      if (!settled) {
        settled = true;
        clearTimeout(timer);
        resolve(fallback);
      }
    });
  });
}

function makeId(prefix) {
  try {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
      return prefix + '-' + globalThis.crypto.randomUUID();
    }
  } catch (_e) {
    /* fall through */
  }
  return prefix + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

function domainOf(url) {
  if (!url || typeof url !== 'string') return '';
  try {
    return new URL(url).hostname.replace(/^www\./i, '');
  } catch (_e) {
    return '';
  }
}

function normalizeContext(ctx, tab) {
  var fallback = fallbackContext(tab);
  var out = {};
  out.title = (ctx && typeof ctx.title === 'string' && ctx.title.trim()) ? ctx.title.trim().slice(0, 500) : fallback.title;
  out.url = (ctx && typeof ctx.url === 'string') ? ctx.url : fallback.url;
  out.domain = (ctx && typeof ctx.domain === 'string' && ctx.domain) ? ctx.domain : (domainOf(out.url) || fallback.domain);
  var text = (ctx && typeof ctx.text === 'string') ? ctx.text : '';
  var selection = (ctx && typeof ctx.selection === 'string') ? ctx.selection : '';
  out.text = text.slice(0, MAX_CONTEXT_CHARS);
  out.selection = selection.slice(0, 5000);
  out.wordCount = (ctx && Number.isFinite(ctx.wordCount)) ? ctx.wordCount : countWords(out.text);
  out.truncated = !!(ctx && ctx.truncated) || text.length > MAX_CONTEXT_CHARS;
  out.source = (ctx && typeof ctx.source === 'string') ? ctx.source : 'content-script';
  out.capturedAt = (ctx && typeof ctx.capturedAt === 'string') ? ctx.capturedAt : new Date().toISOString();
  return out;
}

function countWords(text) {
  if (!text) return 0;
  var parts = String(text).match(/[A-Za-z0-9']+/g);
  return parts ? parts.length : 0;
}

function fallbackContext(tab) {
  var title = (tab && typeof tab.title === 'string' && tab.title.trim()) ? tab.title.trim() : 'Untitled page';
  var url = (tab && typeof tab.url === 'string') ? tab.url : '';
  return {
    title: title,
    url: url,
    domain: domainOf(url),
    text: '',
    selection: '',
    wordCount: 0,
    truncated: false,
    source: 'tab-metadata',
    capturedAt: new Date().toISOString()
  };
}

async function getActiveTab() {
  var tabs = chromeApi && chromeApi.tabs;
  if (!tabs || typeof tabs.query !== 'function') return null;
  try {
    var found = await tabs.query({ active: true, currentWindow: true });
    return (Array.isArray(found) && found[0]) ? found[0] : null;
  } catch (_e) {
    return null;
  }
}

async function requestPageContext(tabId) {
  var rt = runtimeApi();
  if (!tabId || !rt || typeof rt.sendMessage !== 'function') return null;
  try {
    var response = await withTimeout(rt.sendMessage(tabId, { type: 'KEEL_GET_CONTEXT' }), 2000, null);
    if (!response || typeof response !== 'object') return null;
    if (response.ok === false) return null;
    return response.context || response;
  } catch (_e) {
    return null;
  }
}

async function openPanel() {
  var sidePanel = chromeApi && chromeApi.sidePanel;
  if (!sidePanel || typeof sidePanel.open !== 'function') {
    return { ok: false, reason: 'sidePanel API unavailable' };
  }
  var windowId = null;
  try {
    if (chromeApi.windows && typeof chromeApi.windows.getCurrent === 'function') {
      var window = await withTimeout(chromeApi.windows.getCurrent(), 1000, null);
      if (window && window.id != null) windowId = window.id;
    }
  } catch (_e) {
    /* ignore */
  }
  if (windowId == null) {
    var tab = await getActiveTab();
    if (tab && tab.windowId != null) windowId = tab.windowId;
  }
  if (windowId == null) return { ok: false, reason: 'no active window' };
  try {
    await sidePanel.open({ windowId: windowId });
    return { ok: true, method: 'sidePanel' };
  } catch (e) {
    return { ok: false, reason: String((e && e.message) || e) };
  }
}

async function openPanelFallback() {
  try {
    if (chromeApi && chromeApi.tabs && typeof chromeApi.tabs.create === 'function') {
      var tab = await chromeApi.tabs.create({ url: extensionUrl('sidepanel.html'), active: true });
      return { ok: true, method: 'tab', tabId: tab && tab.id };
    }
  } catch (_e) {
    /* ignore */
  }
  return { ok: false, reason: 'unable to open panel' };
}

async function createContextMenus() {
  var menus = chromeApi && chromeApi.contextMenus;
  if (!menus || typeof menus.create !== 'function') return;
  if (typeof menus.removeAll === 'function') {
    try {
      await withTimeout(menus.removeAll(), 1000, null);
    } catch (_e) {
      /* ignore */
    }
  }
  var items = [
    { id: 'keel-ask-page', title: 'Ask Keel about this page', type: 'ask' },
    { id: 'keel-convert-page', title: 'Convert this page with Keel', type: 'convert' }
  ];
  items.forEach(function (item) {
    try {
      menus.create({
        id: item.id,
        title: item.title,
        contexts: ['page', 'frame', 'selection', 'link']
      });
    } catch (_e) {
      /* menu may already exist */
    }
  });
}

async function handleContextMenuClick(info, tab) {
  var type = (info && info.menuItemId === 'keel-convert-page') ? 'convert' : 'ask';
  await setState({
    pendingAction: {
      type: type,
      at: Date.now(),
      tabId: tab && tab.id != null ? tab.id : null,
      title: (tab && tab.title) || ''
    },
    mode: type === 'convert' ? 'Convert' : 'Chat'
  });
  var result = await openPanel();
  if (!result.ok) await openPanelFallback();
  return result;
}

function sortSessions(sessions) {
  return sessions.slice().sort(function (a, b) {
    var ta = Date.parse(a.updatedAt || a.createdAt || 0) || 0;
    var tb = Date.parse(b.updatedAt || b.createdAt || 0) || 0;
    return tb - ta;
  });
}

async function newSession(payload) {
  var state = await getState();
  var session = {
    id: makeId('keel'),
    title: (payload && payload.title) || 'New Keel session',
    mode: (payload && payload.mode) || state.mode || 'Chat',
    model: (payload && payload.model) || state.model,
    context: (payload && payload.context) || state.lastContext || null,
    messages: (payload && Array.isArray(payload.messages)) ? payload.messages : [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  var sessions = sortSessions([session].concat(state.sessions)).slice(0, MAX_SESSIONS);
  await setState({ sessions: sessions });
  return { ok: true, session: session, sessions: sessions };
}

async function saveSession(payload) {
  if (!payload || typeof payload !== 'object' || !payload.id) return newSession(payload);
  var state = await getState();
  var existing = state.sessions.filter(function (s) { return s.id !== payload.id; });
  var session = Object.assign({}, payload, {
    id: payload.id,
    title: payload.title || 'Keel session',
    messages: Array.isArray(payload.messages) ? payload.messages : [],
    createdAt: payload.createdAt || new Date().toISOString(),
    updatedAt: new Date().toISOString()
  });
  var sessions = sortSessions([session].concat(existing)).slice(0, MAX_SESSIONS);
  await setState({ sessions: sessions });
  return { ok: true, session: session, sessions: sessions };
}

async function openTabGroup(payload) {
  var data = payload || {};
  var tabsApi = chromeApi && chromeApi.tabs;
  if (!tabsApi || typeof tabsApi.create !== 'function') {
    return { ok: false, grouped: false, error: 'Tabs API unavailable' };
  }
  var ids = [];
  if (Array.isArray(data.tabIds)) {
    ids = data.tabIds.filter(function (id) { return typeof id === 'number'; });
  }
  var urls = Array.isArray(data.urls) ? data.urls.filter(function (u) {
    return typeof u === 'string' && /^https?:\/\//i.test(u);
  }).slice(0, 10) : [];
  for (var i = 0; i < urls.length; i += 1) {
    try {
      var tab = await tabsApi.create({ url: urls[i], active: false });
      if (tab && tab.id != null) ids.push(tab.id);
    } catch (_e) {
      /* skip tabs we cannot open */
    }
  }
  if (!ids.length) return { ok: false, grouped: false, error: 'No tabs to group' };

  if (typeof tabsApi.group === 'function') {
    try {
      var groupId = await tabsApi.group({ tabIds: ids });
      var groups = chromeApi && chromeApi.tabGroups;
      if (data.title && groups && typeof groups.update === 'function') {
        try {
          await groups.update(groupId, { title: String(data.title).slice(0, 120) });
        } catch (_e) {
          /* title is optional */
        }
      }
      return { ok: true, grouped: true, groupId: groupId, tabIds: ids };
    } catch (_e) {
      /* fall through to plain tabs */
    }
  }
  return {
    ok: true,
    grouped: false,
    tabIds: ids,
    reason: 'Tab grouping unavailable; tabs were opened normally'
  };
}

async function handleMessage(message, sender) {
  if (!message || typeof message !== 'object' || typeof message.type !== 'string') {
    return { ok: false, error: 'Invalid message' };
  }
  var payload = message.payload !== undefined ? message.payload : message;
  switch (message.type) {
    case 'PING':
      return { ok: true, pong: true };

    case 'GET_STATE':
      return { ok: true, state: await getState() };

    case 'GET_PAGE_CONTEXT': {
      var tab = await getActiveTab();
      if (message.tabId && typeof message.tabId === 'number' && chromeApi.tabs && typeof chromeApi.tabs.get === 'function') {
        try {
          var explicit = await chromeApi.tabs.get(message.tabId);
          if (explicit) tab = explicit;
        } catch (_e) {
          /* keep active tab */
        }
      }
      var ctx = tab ? await requestPageContext(tab.id) : null;
      var normalized = normalizeContext(ctx, tab);
      await setState({
        lastContext: {
          title: normalized.title,
          url: normalized.url,
          domain: normalized.domain,
          capturedAt: normalized.capturedAt
        }
      });
      return { ok: true, context: normalized };
    }

    case 'SET_PENDING_ACTION':
      await setState({ pendingAction: (payload && payload.action) ? payload.action : payload });
      return { ok: true };

    case 'GET_PENDING_ACTION':
      return { ok: true, action: (await getState()).pendingAction };

    case 'CLEAR_PENDING_ACTION':
      await setState({ pendingAction: null });
      return { ok: true };

    case 'NEW_SESSION':
      return newSession(payload);

    case 'SAVE_SESSION':
      return saveSession(payload);

    case 'LIST_SESSIONS': {
      var state = await getState();
      return { ok: true, sessions: sortSessions(state.sessions) };
    }

    case 'SAVE_SESSIONS_REPLACE': {
      var replacement = (payload && Array.isArray(payload.sessions)) ? payload.sessions : [];
      var clean = replacement.filter(function (s) { return s && typeof s === 'object' && s.id; }).slice(0, MAX_SESSIONS);
      await setState({ sessions: sortSessions(clean) });
      return { ok: true, sessions: clean };
    }

    case 'CLEAR_SESSIONS':
      await setState({ sessions: [] });
      return { ok: true };

    case 'SET_WELCOME_SEEN': {
      var seen = (payload && typeof payload.seen === 'boolean') ? payload.seen : payload;
      await setState({ welcomeSeen: !!seen });
      return { ok: true, welcomeSeen: !!seen };
    }

    case 'OPEN_TAB_GROUP':
      return openTabGroup(payload);

    case 'SET_APPROVAL_MODE': {
      var value = (payload && payload.mode) || payload;
      if (typeof value !== 'string' || APPROVAL_MODES.indexOf(value) === -1) {
        return { ok: false, error: 'Unknown approval mode' };
      }
      await setState({ approvalMode: value });
      return { ok: true, approvalMode: value };
    }

    case 'SET_MODEL': {
      var model = (payload && payload.model) || payload;
      if (MODELS.indexOf(model) === -1) return { ok: false, error: 'Unknown model' };
      await setState({ model: model });
      return { ok: true, model: model };
    }

    case 'SET_SETTINGS': {
      var current = await getState();
      var nextSettings = Object.assign({}, current.settings);
      var patch = (message.settings && typeof message.settings === 'object')
        ? message.settings
        : ((payload && typeof payload === 'object') ? payload : {});
      Object.keys(patch).forEach(function (key) {
        if (typeof patch[key] === 'boolean') nextSettings[key] = patch[key];
      });
      await setState({ settings: nextSettings });
      return { ok: true, settings: nextSettings };
    }

    case 'SET_MODE': {
      var mode = (payload && payload.mode) || payload;
      if (mode !== 'Chat' && mode !== 'Convert') return { ok: false, error: 'Unknown mode' };
      await setState({ mode: mode });
      return { ok: true, mode: mode };
    }

    case 'SET_ACTIVE_TAB': {
      var active = (payload && payload.tab) || payload;
      await setState({ activeTab: active });
      return { ok: true, activeTab: active };
    }

    case 'SET_CONTEXT_SOURCE': {
      var source = (payload && payload.source) || payload;
      if (source !== 'full' && source !== 'selection') return { ok: false, error: 'Unknown context source' };
      await setState({ contextSource: source });
      return { ok: true, contextSource: source };
    }

    case 'OPEN_PANEL': {
      var opened = await openPanel();
      if (!opened.ok) opened = await openPanelFallback();
      return opened;
    }

    default:
      return { ok: false, error: 'Unknown message type: ' + message.type };
  }
}

/* ------------------------------- wiring ------------------------------- */

var rt = runtimeApi();

if (rt && rt.onInstalled && typeof rt.onInstalled.addListener === 'function') {
  rt.onInstalled.addListener(function (details) {
    (async function () {
      var reason = details && details.reason;
      var patch = { pendingAction: null };
      if (reason === 'install') {
        patch.welcomeSeen = false;
        patch.installedAt = new Date().toISOString();
      }
      await setState(patch);
      await createContextMenus();
      /* Best effort: on install the welcome/setup state is already in storage.
         The panel may need a user gesture, so a failed open is not an error. */
      await openPanel();
    })().catch(function () {
      /* never let a listener reject */
    });
  });
}

if (rt && rt.onStartup && typeof rt.onStartup.addListener === 'function') {
  rt.onStartup.addListener(function () {
    createContextMenus().catch(function () { /* ignore */ });
  });
}

if (rt && rt.onMessage && typeof rt.onMessage.addListener === 'function') {
  rt.onMessage.addListener(function (message, sender, sendResponse) {
    handleMessage(message, sender).then(function (result) {
      try { sendResponse(result); } catch (_e) { /* channel closed */ }
    }).catch(function (error) {
      try {
        sendResponse({ ok: false, error: String((error && error.message) || error) });
      } catch (_e) {
        /* channel closed */
      }
    });
    return true;
  });
}

try {
  if (chromeApi && chromeApi.action && chromeApi.action.onClicked && typeof chromeApi.action.onClicked.addListener === 'function') {
    chromeApi.action.onClicked.addListener(function () {
      openPanel().catch(function () { /* ignore */ });
    });
  }
} catch (_e) {
  /* ignore */
}

try {
  var menus = chromeApi && chromeApi.contextMenus;
  if (menus && menus.onClicked && typeof menus.onClicked.addListener === 'function') {
    menus.onClicked.addListener(function (info, tab) {
      handleContextMenuClick(info, tab).catch(function () { /* ignore */ });
    });
  }
} catch (_e) {
  /* ignore */
}

try {
  var tabsApi = chromeApi && chromeApi.tabs;
  if (tabsApi && tabsApi.onActivated && typeof tabsApi.onActivated.addListener === 'function') {
    tabsApi.onActivated.addListener(function (info) {
      /* Let an open panel refresh its context chip when the user switches tabs. */
      try {
        if (rt && typeof rt.sendMessage === 'function') {
          rt.sendMessage({ type: 'KEEL_PAGE_CHANGED', windowId: info && info.windowId }).catch(function () { /* no listeners */ });
        }
      } catch (_e) {
        /* ignore */
      }
    });
  }
} catch (_e) {
  /* ignore */
}

/* Boot context menus for already-installed extensions without a fresh install. */
createContextMenus().catch(function () { /* ignore */ });

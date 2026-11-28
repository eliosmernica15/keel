/* Keel in Chrome — side panel UI.
 * Fully local, deterministic demo: page text is read from the active tab via
 * the background worker, and answers are built with rules in this file.
 * No network requests, no API keys, no external scripts.
 */
(function () {
  'use strict';

  var DEFAULT_SETTINGS = {
    stream: true,
    autoSave: true,
    keyboardHints: true,
    reduceMotion: false
  };
  var MODELS = ['Mythos', 'Opus', 'Sonnet', 'Haiku'];
  var APPROVAL_MODES = ['Ask before each action', 'Permissions Mode', 'Work autonomously'];
  var TABS = ['Keel', 'Keel Code', 'Everyday tools', 'Background tasks'];
  /* IDs must not contain spaces: aria-labelledby is a space-separated IDREF list. */
  var TAB_IDS = {
    'Keel': 'tab-Keel',
    'Keel Code': 'tab-KeelCode',
    'Everyday tools': 'tab-EverydayTools',
    'Background tasks': 'tab-BackgroundTasks'
  };

  var state = {
    model: 'Mythos',
    approvalMode: 'Ask before each action',
    mode: 'Chat',
    activeTab: 'Keel',
    contextSource: 'full',
    settings: Object.assign({}, DEFAULT_SETTINGS),
    welcomeSeen: false,
    sessions: [],
    session: null,
    context: null,
    listening: false,
    streaming: false,
    token: 0,
    timer: null,
    activeAction: null,
    activeMessage: null
  };

  var ICON_PATHS = {
    chart: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M3 16.5h14M5.5 13V8m4.5 5V4.5m4.5 8.5V10"/>',
    folder: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M2.8 5.5h5l1.6 2h7.8v8.7H2.8z"/>',
    calendar: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M3.5 5.5h13v11h-13zM3.5 9h13M7 3v4m6-4v4"/>',
    compare: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M3 4.5h6v11H3zM11 4.5h6v11h-6zM4.5 8h3M12.5 8h3"/>',
    phone: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M5 3.5h3l1.4 3.3-1.8 1.4a10 10 0 0 0 4.2 4.2l1.4-1.8 3.3 1.4v3a1.5 1.5 0 0 1-1.7 1.5A13.5 13.5 0 0 1 3.5 5.2 1.5 1.5 0 0 1 5 3.5z"/>',
    mail: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M2.5 5h15v10h-15zM2.5 5.5l7.5 6 7.5-6"/>',
    code: '<path fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" d="M7.5 6L3 10l4.5 4M12.5 6L17 10l-4.5 4"/>',
    bug: '<path fill="none" stroke="currentColor" stroke-width="1.6" d="M6 8a4 4 0 0 1 8 0v4a4 4 0 0 1-8 0zM3.5 9h2.5m8 0h2.5M3.5 14h2.5m8 0h2.5M7 5L5.5 3.5M13 5l1.5-1.5"/>',
    test: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M4 4l3 3m9-3l-3 3M7 7l6 6M5 14l5-5m-1 8l6-6"/>',
    refactor: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" d="M4 6h9a3 3 0 0 1 0 6H7m0 0l3-3m-3 3l3 3M16 14h-6"/>',
    doc: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M5 2.8h7l3 3v11.4H5zM12 2.8v3h3M7.5 10h5m-5 3h5"/>',
    diff: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M5 5v10M3.5 6.5h3M3.5 13.5h3M14 5v10M12.5 6.5h3M12.5 13.5h3M8 10h4"/>',
    reply: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M8 6L3 10l5 4v-3h5a4 4 0 0 1 4 4v1a6 6 0 0 0-6-6H8z"/>',
    check: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" d="M3.5 10l4 4 9-9"/>',
    text: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M4 5h12M4 9h12M4 13h8M4 17h6"/>',
    users: '<path fill="none" stroke="currentColor" stroke-width="1.6" d="M7 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zm6.5-.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM2.5 16c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4M12 12.5c2.8 0 5.5 1.2 5.5 3.5"/>',
    plane: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M3 10l14-6-5 14-2.5-5.5z"/>',
    globe: '<path fill="none" stroke="currentColor" stroke-width="1.6" d="M10 2.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15zM2.8 10h14.4M10 2.5c2 2 3 4.6 3 7.5s-1 5.5-3 7.5c-2-2-3-4.6-3-7.5s1-5.5 3-7.5z"/>',
    eye: '<path fill="none" stroke="currentColor" stroke-width="1.6" d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z"/><circle cx="10" cy="10" r="2" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    clock: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M10 3v7l4 2M10 2.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15z"/>',
    tag: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M2.5 3.5h7l8 8-7 7-8-8zM6 7h.01"/>',
    bolt: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M11 2L4 11h5l-1 7 8-10h-5z"/>',
    layers: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" d="M10 2.5l7 4-7 4-7-4zM3 10l7 4 7-4M3 13.5l7 4 7-4"/>',
    list: '<path fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" d="M7 5h10M7 10h10M7 15h10M3.5 5h.01M3.5 10h.01M3.5 15h.01"/>'
  };

  function icon(name) {
    return '<svg viewBox="0 0 20 20" width="15" height="15" aria-hidden="true" focusable="false">' +
      (ICON_PATHS[name] || ICON_PATHS.list) + '</svg>';
  }

  var QUICK_SETS = {
    'Keel': [
      { id: 'metrics', icon: 'chart', label: 'Pull metrics from analytics dashboards', prompt: 'Pull the key metrics from this analytics dashboard and explain what changed.' },
      { id: 'drive', icon: 'folder', label: 'Organize files in Google Drive', prompt: 'Organize the files in this Drive view into a clean folder structure with a naming convention.' },
      { id: 'calendar', icon: 'calendar', label: 'Prepare and plan from your calendar', prompt: 'Read this calendar and prepare a focused plan with time blocks and priorities.' },
      { id: 'competitor', icon: 'compare', label: 'Research competitors, get a comparison deck', prompt: 'Research the competitors mentioned here and outline a comparison deck.' },
      { id: 'crm', icon: 'phone', label: 'Log sales calls to your CRM', prompt: 'Turn this sales call into structured CRM notes with next steps.' },
      { id: 'email', icon: 'mail', label: 'Clean up promotional emails', prompt: 'Summarize these promotional emails, group duplicates, and draft a clean-up plan.' }
    ],
    'Keel Code': [
      { id: 'code', icon: 'code', label: 'Explain this code in plain language', prompt: 'Explain what this code does, in plain language.' },
      { id: 'bug', icon: 'bug', label: 'Find bugs and edge cases', prompt: 'Find likely bugs and edge cases in the code shown on this page.' },
      { id: 'test', icon: 'test', label: 'Write a practical test plan', prompt: 'Write a practical test plan for the code on this page.' },
      { id: 'refactor', icon: 'refactor', label: 'Draft a small refactor', prompt: 'Suggest a small, safe refactor for this code.' },
      { id: 'doc', icon: 'doc', label: 'Document the API here', prompt: 'Write concise developer documentation for the API shown here.' },
      { id: 'diff', icon: 'diff', label: 'Review this diff', prompt: 'Review this diff and list what looks risky.' }
    ],
    'Everyday tools': [
      { id: 'reply', icon: 'reply', label: 'Draft a thoughtful reply', prompt: 'Draft a short, thoughtful reply to the message on this page.' },
      { id: 'checklist', icon: 'check', label: 'Turn this into a checklist', prompt: 'Turn this page into a clear, actionable checklist.' },
      { id: 'simplify', icon: 'text', label: 'Simplify the wording', prompt: 'Simplify the wording on this page without losing the meaning.' },
      { id: 'contacts', icon: 'users', label: 'Extract names and contacts', prompt: 'Extract the names, roles, and contact details mentioned here.' },
      { id: 'travel', icon: 'plane', label: 'Plan from this itinerary', prompt: 'Plan a clear day-by-day itinerary from this page.' },
      { id: 'translate', icon: 'globe', label: 'Translate the key points', prompt: 'Translate the key points of this page into concise English.' }
    ],
    'Background tasks': [
      { id: 'watch', icon: 'eye', label: 'Watch this page for changes', prompt: 'Set up a local watch on this page and describe what changes to flag.' },
      { id: 'digest', icon: 'list', label: 'Build a daily digest', prompt: 'Build a daily digest outline from the content on this page.' },
      { id: 'prices', icon: 'tag', label: 'Track prices mentioned here', prompt: 'Track the prices on this page and list the ones worth watching.' },
      { id: 'updates', icon: 'bolt', label: 'Monitor for updates', prompt: 'Monitor this page for updates and summarize what matters.' },
      { id: 'threads', icon: 'layers', label: 'Summarize new threads', prompt: 'Summarize the threads on this page into a short brief.' },
      { id: 'recurring', icon: 'clock', label: 'Queue a recurring report', prompt: 'Queue a recurring local report based on this page.' }
    ]
  };

  var STOPWORDS = ('a an and or but if then than to of in on for with at by from is are was were be been being this that these those it its as into about over after before you your we our they their he she his her i me my not no so can will just also more most some any all one two three use using how what when where why who which get got has have had do does did each other only very own same s t don now page site web click read more less here there them then would could should may might must shall up down out off again further once because while during until against between under above below about').split(' ');
  var STOP = {};
  STOPWORDS.forEach(function (word) { STOP[word] = true; });

  var INTENTS = {
    metrics: {
      line: 'I would anchor the answer in the numbers visible on the page: record the current values, compare them with the previous period where shown, and call out the largest movers before writing any narrative.',
      next: 'Export the date range and the three biggest metric movements, then turn them into a two-sentence readout.',
      actions: [
        'Record the current values for each metric and the reporting date range.',
        'Flag the three metrics with the largest change and propose an owner for each.',
        'Draft a short readout for the team using only numbers present on the page.'
      ]
    },
    drive: {
      line: 'Treat the file names on this page as the inventory. Group them by project, then use a consistent prefix so that search and sorting stay predictable.',
      next: 'Draft a folder tree and a short naming convention, then apply it to the highest-value folder first.',
      actions: [
        'List the files that are visible and mark likely duplicates.',
        'Propose a folder tree with no more than two levels.',
        'Write a naming convention and rename three example files.'
      ]
    },
    calendar: {
      line: 'The calendar entries suggest a mix of fixed meetings and focus work. Protect the largest open block for the task with the highest stated priority.',
      next: 'Time-block the day, add buffers around meetings, and write a short pre-meeting checklist.',
      actions: [
        'List the fixed commitments and their durations.',
        'Reserve one uninterrupted block for the top priority.',
        'Prepare a one-line agenda for each meeting that has no agenda.'
      ]
    },
    competitor: {
      line: 'A useful comparison needs the same axes for every competitor: positioning, price signal, target customer, and proof points. I extracted the facts the page actually states and left gaps marked as unknown.',
      next: 'Build a four-column comparison table and fill unknowns with a research task instead of a guess.',
      actions: [
        'List competitors named on the page with a one-line positioning sentence.',
        'Compare pricing, audience, and proof points; mark missing facts as unknown.',
        'Outline a five-slide deck: landscape, axes, winners, gaps, recommendation.'
      ]
    },
    crm: {
      line: 'For CRM logging, separate facts from interpretation: capture the account, participants, stated pain, and explicit commitments, then add a suggested follow-up.',
      next: 'Create the CRM record fields and schedule the next touchpoint.',
      actions: [
        'Fill account, contact, and participant fields from the page.',
        'Record stated pains and objections verbatim where possible.',
        'Add next steps with an owner and a date.'
      ]
    },
    email: {
      line: 'The promotional messages can be grouped by sender and intent. Keeping one representative per campaign and archiving the rest is the safest first pass.',
      next: 'Group duplicates, unsubscribe from the noisiest senders, and archive the remainder.',
      actions: [
        'Group messages by sender and campaign theme.',
        'Mark duplicates and keep one representative per group.',
        'Draft a short unsubscribe note for the senders you want to stop.'
      ]
    },
    code: {
      line: 'I read the code as a flow: inputs, transformations, outputs, and failure points. The most useful next step is a short explanation plus a list of assumptions.',
      next: 'Write a five-line explanation and list the assumptions that need checking.',
      actions: [
        'Describe the inputs and outputs in one sentence each.',
        'List the functions or blocks that carry the most risk.',
        'Add a short comment to the least obvious section.'
      ]
    },
    bug: {
      line: 'Likely trouble spots are unchecked inputs, empty collections, and branches that assume a value is always present. I would verify those before changing behavior.',
      next: 'Write three failing test cases, then fix the smallest root cause.',
      actions: [
        'List null, empty, and boundary cases not handled in the page.',
        'Add a regression test for the highest-risk case.',
        'Review any error path that silently drops information.'
      ]
    },
    test: {
      line: 'A good test plan covers the happy path, the obvious failure paths, and one realistic edge case per external dependency.',
      next: 'Write the test cases in priority order and run the smallest slice first.',
      actions: [
        'List the happy-path cases with expected outputs.',
        'Add failure cases for bad input and missing data.',
        'Name one edge case per dependency shown on the page.'
      ]
    },
    default: {
      line: 'I focused on the parts of the page that carry the most signal: repeated terms, concrete statements, and anything that reads like a next step.',
      next: 'Turn the summary into three decisions and assign an owner to each.',
      actions: [
        'Verify the key facts against the source page.',
        'Turn the summary into a short decision list.',
        'Share the brief with the person who owns the next step.'
      ]
    }
  };

  function byId(id) { return document.getElementById(id); }

  var el = {};
  function cacheElements() {
    [
      'newSessionBtn', 'historyBtn', 'accountBtn', 'accountMenu', 'settingsMenuItem',
      'contextChip', 'contextTitle', 'contextMeta', 'refreshContextBtn',
      'modeChat', 'modeKey', 'modeConvert', 'mainContent', 'hero', 'heroTitle',
      'heroSubtitle', 'copyMarkdownBtn', 'welcomeNote', 'dismissWelcomeBtn',
      'conversation', 'quickHint', 'quickActions',
      'listeningNote', 'stopListeningBtn', 'attachedBar', 'attachedLabel',
      'clearAttachBtn', 'composerInput', 'attachBtn', 'attachMenu', 'micBtn',
      'sourceLabel', 'modelSelect', 'approvalSelect', 'sendBtn', 'sendIcon',
      'drawerBackdrop', 'historyDrawer', 'closeHistoryBtn', 'sessionList',
      'settingsDrawer', 'closeSettingsBtn', 'settingStream', 'settingAutoSave',
      'settingHints', 'settingReduceMotion', 'clearHistoryBtn', 'resetPrefsBtn',
      'toast'
    ].forEach(function (id) { el[id] = byId(id); });
  }

  function sendMessage(message) {
    return new Promise(function (resolve) {
      try {
        var runtime = globalThis.chrome && globalThis.chrome.runtime;
        if (!runtime || typeof runtime.sendMessage !== 'function') {
          resolve({ ok: false, error: 'Chrome runtime unavailable' });
          return;
        }
        var result = runtime.sendMessage(message);
        if (result && typeof result.then === 'function') {
          result.then(resolve, function (error) {
            resolve({ ok: false, error: String((error && error.message) || error) });
          });
        } else {
          resolve({ ok: true });
        }
      } catch (error) {
        resolve({ ok: false, error: String((error && error.message) || error) });
      }
    });
  }

  function clone(value) {
    try { return JSON.parse(JSON.stringify(value)); } catch (_e) { return value; }
  }

  var toastTimer = null;
  function toast(message) {
    if (!el.toast) return;
    el.toast.textContent = message;
    el.toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.toast.hidden = true; }, 2600);
  }

  /* --------------------------- menus & drawers -------------------------- */
  function closeMenus() {
    if (el.attachMenu) el.attachMenu.hidden = true;
    if (el.accountMenu) el.accountMenu.hidden = true;
    if (el.attachBtn) el.attachBtn.setAttribute('aria-expanded', 'false');
    if (el.accountBtn) el.accountBtn.setAttribute('aria-expanded', 'false');
  }

  function toggleMenu(menu, button) {
    if (!menu || !button) return;
    var willOpen = menu.hidden;
    closeMenus();
    menu.hidden = !willOpen;
    button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  }

  function closeDrawers() {
    if (el.historyDrawer) el.historyDrawer.hidden = true;
    if (el.settingsDrawer) el.settingsDrawer.hidden = true;
    if (el.drawerBackdrop) el.drawerBackdrop.hidden = true;
    if (el.historyBtn) el.historyBtn.setAttribute('aria-expanded', 'false');
  }

  function openDrawer(which) {
    closeMenus();
    if (el.drawerBackdrop) el.drawerBackdrop.hidden = false;
    if (which === 'history') {
      if (el.settingsDrawer) el.settingsDrawer.hidden = true;
      if (el.historyDrawer) el.historyDrawer.hidden = false;
      if (el.historyBtn) el.historyBtn.setAttribute('aria-expanded', 'true');
      loadSessions();
      if (el.closeHistoryBtn) el.closeHistoryBtn.focus();
    } else {
      if (el.historyDrawer) el.historyDrawer.hidden = true;
      if (el.settingsDrawer) el.settingsDrawer.hidden = false;
      if (el.settingsMenuItem) el.settingsMenuItem.blur();
      if (el.closeSettingsBtn) el.closeSettingsBtn.focus();
    }
  }

  /* --------------------------- state & rendering ------------------------ */
  function applyState(raw) {
    if (!raw || typeof raw !== 'object') return;
    if (typeof raw.model === 'string' && MODELS.indexOf(raw.model) !== -1) state.model = raw.model;
    if (APPROVAL_MODES.indexOf(raw.approvalMode) !== -1) state.approvalMode = raw.approvalMode;
    if (raw.mode === 'Chat' || raw.mode === 'Convert') state.mode = raw.mode;
    if (TABS.indexOf(raw.activeTab) !== -1) state.activeTab = raw.activeTab;
    if (raw.contextSource === 'full' || raw.contextSource === 'selection') state.contextSource = raw.contextSource;
    if (typeof raw.welcomeSeen === 'boolean') state.welcomeSeen = raw.welcomeSeen;
    if (Array.isArray(raw.sessions)) state.sessions = raw.sessions;
    if (raw.settings && typeof raw.settings === 'object') {
      Object.keys(DEFAULT_SETTINGS).forEach(function (key) {
        if (typeof raw.settings[key] === 'boolean') state.settings[key] = raw.settings[key];
      });
    }
  }

  function applySettingsUI() {
    if (el.settingStream) el.settingStream.checked = state.settings.stream;
    if (el.settingAutoSave) el.settingAutoSave.checked = state.settings.autoSave;
    if (el.settingHints) el.settingHints.checked = state.settings.keyboardHints;
    if (el.settingReduceMotion) el.settingReduceMotion.checked = state.settings.reduceMotion;
    document.body.classList.toggle('reduce-motion', !!state.settings.reduceMotion);
    if (el.modeKey) el.modeKey.hidden = !state.settings.keyboardHints;
  }

  function setModel(model, persist) {
    if (MODELS.indexOf(model) === -1) return;
    state.model = model;
    if (el.modelSelect) el.modelSelect.value = model;
    if (persist) sendMessage({ type: 'SET_MODEL', model: model });
  }

  function setApprovalMode(mode, persist) {
    if (APPROVAL_MODES.indexOf(mode) === -1) return;
    state.approvalMode = mode;
    if (el.approvalSelect) el.approvalSelect.value = mode;
    if (persist) sendMessage({ type: 'SET_APPROVAL_MODE', mode: mode });
  }

  function setMode(mode, persist) {
    state.mode = mode;
    var isChat = mode === 'Chat';
    if (el.modeChat) {
      el.modeChat.classList.toggle('is-active', isChat);
      el.modeChat.setAttribute('aria-pressed', isChat ? 'true' : 'false');
    }
    if (el.modeConvert) {
      el.modeConvert.classList.toggle('is-active', !isChat);
      el.modeConvert.setAttribute('aria-pressed', isChat ? 'false' : 'true');
    }
    if (el.heroTitle) el.heroTitle.textContent = isChat ? 'Ask questions about this page' : 'Convert this page into a deliverable';
    if (el.heroSubtitle) el.heroSubtitle.textContent = isChat
      ? 'Keel reads the page you’re on and answers locally — nothing is uploaded.'
      : 'Generate a structured brief with a summary, action items, and a key-facts table.';
    if (el.composerInput) el.composerInput.placeholder = isChat ? 'Ask Keel about this page…' : 'Describe what to convert this page into…';
    if (persist) sendMessage({ type: 'SET_MODE', mode: mode });
  }

  function toggleMode() { setMode(state.mode === 'Chat' ? 'Convert' : 'Chat', true); }

  function setActiveTab(tab) {
    if (TABS.indexOf(tab) === -1) return;
    state.activeTab = tab;
    var tabs = document.querySelectorAll('.tool-tab');
    Array.prototype.forEach.call(tabs, function (button) {
      var active = button.getAttribute('data-tab') === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
      button.setAttribute('tabindex', active ? '0' : '-1');
    });
    var panel = el.quickActions;
    if (panel) panel.setAttribute('aria-labelledby', TAB_IDS[tab] || TAB_IDS.Keel);
    if (el.quickHint) el.quickHint.textContent = tab === 'Keel' ? 'with page context' : 'for ' + tab.toLowerCase();
    renderQuickActions();
    sendMessage({ type: 'SET_ACTIVE_TAB', tab: tab });
  }

  function renderQuickActions() {
    if (!el.quickActions) return;
    var actions = QUICK_SETS[state.activeTab] || QUICK_SETS.Keel;
    el.quickActions.innerHTML = '';
    actions.forEach(function (action) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'quick-btn';
      button.setAttribute('aria-label', action.label + ' — fill and run this prompt');
      button.innerHTML = '<span class="quick-icon" aria-hidden="true">' + icon(action.icon) + '</span>' +
        '<span class="quick-label"></span><span class="quick-arrow" aria-hidden="true">&nearr;</span>';
      var label = button.querySelector('.quick-label');
      if (label) label.textContent = action.label;
      button.addEventListener('click', function () {
        state.activeAction = action.id;
        if (el.composerInput) {
          el.composerInput.value = action.prompt;
          autoResize();
          el.composerInput.focus();
        }
        runTurn(action.prompt);
      });
      el.quickActions.appendChild(button);
    });
  }

  function setContextSource(source, persist) {
    if (source !== 'full' && source !== 'selection') return;
    state.contextSource = source;
    if (el.sourceLabel) el.sourceLabel.textContent = source === 'selection' ? 'Selection' : 'Full page';
    if (el.attachedLabel) el.attachedLabel.textContent = source === 'selection' ? 'Page selection attached' : 'Full page attached';
    if (el.attachedBar) el.attachedBar.hidden = false;
    if (el.attachMenu) {
      Array.prototype.forEach.call(el.attachMenu.querySelectorAll('[data-source]'), function (item) {
        item.setAttribute('role', 'menuitemradio');
        item.setAttribute('aria-checked', item.getAttribute('data-source') === source ? 'true' : 'false');
      });
    }
    if (persist) sendMessage({ type: 'SET_CONTEXT_SOURCE', source: source });
  }

  function setListening(on) {
    state.listening = on;
    if (el.micBtn) el.micBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (el.listeningNote) el.listeningNote.hidden = !on;
    if (on) {
      toast('Simulated listening is on — type your request below.');
    } else if (el.composerInput && !el.composerInput.value.trim()) {
      el.composerInput.value = 'Summarize this page and list the key takeaways.';
      autoResize();
      toast('Draft prompt added. Edit it or press Enter to send.');
    }
  }

  function autoResize() {
    var input = el.composerInput;
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = Math.min(130, Math.max(34, input.scrollHeight)) + 'px';
  }

  /* ------------------------------- context ------------------------------ */
  function domainFromUrl(url) {
    try { return new URL(url).hostname.replace(/^www\./i, ''); } catch (_e) { return ''; }
  }

  function updateContextChip() {
    var ctx = state.context || {};
    if (el.contextTitle) el.contextTitle.textContent = ctx.title || 'No page context yet';
    var parts = [];
    if (ctx.domain) parts.push(ctx.domain);
    if (ctx.wordCount) parts.push(ctx.wordCount.toLocaleString() + ' words');
    if (ctx.source === 'tab-metadata') parts.push('limited page access');
    if (!parts.length) parts.push('Waiting for page context');
    if (el.contextMeta) el.contextMeta.textContent = parts.join(' · ');
    if (el.contextChip) el.contextChip.title = [ctx.title, ctx.url].filter(Boolean).join('\n');
  }

  async function loadContext(announce) {
    var response = await sendMessage({ type: 'GET_PAGE_CONTEXT' });
    if (response && response.ok && response.context) {
      state.context = response.context;
      updateContextChip();
      if (announce) toast('Page context refreshed.');
      return state.context;
    }
    if (!state.context) {
      state.context = {
        title: 'This page', url: '', domain: '', text: '', selection: '',
        wordCount: 0, source: 'unavailable', capturedAt: new Date().toISOString()
      };
      updateContextChip();
    }
    if (announce) toast('Could not read the page. Try a regular web page.');
    return state.context;
  }

  function cleanInline(value) {
    return String(value == null ? '' : value)
      .replace(/[\r\n]+/g, ' ')
      .replace(/[|`*_\[\]]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function contextMarkdown() {
    var ctx = state.context || {};
    var lines = [
      '# Page context — ' + cleanInline(ctx.title || 'Untitled page'),
      '',
      '- Source: ' + (ctx.url || 'unavailable'),
      '- Domain: ' + (ctx.domain || 'unknown'),
      '- Captured: ' + (ctx.capturedAt || 'just now'),
      '- Words: ' + (ctx.wordCount || 0),
      '- Attached context: ' + (state.contextSource === 'selection' ? 'Page selection' : 'Full page'),
      ''
    ];
    if (state.contextSource === 'selection' && ctx.selection) {
      lines.push('## Selection', '', ctx.selection, '');
    }
    var body = String(ctx.text || '');
    lines.push('## Page text' + (body.length > 8000 ? ' (first 8,000 characters)' : ''), '', body.slice(0, 8000) || '(No readable page text was available.)', '');
    return lines.join('\n');
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (_e) { /* fall through */ }
    try {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      var copied = document.execCommand('copy');
      area.remove();
      return !!copied;
    } catch (_e) {
      return false;
    }
  }

  /* -------------------------- demo answer engine ------------------------ */
  function categorize(domain) {
    var d = String(domain || '').toLowerCase();
    if (/github|gitlab|stackoverflow|developer|docs|npm|readthedocs/.test(d)) {
      return { name: 'developer documentation', note: 'This looks like developer material, so I treated code and API details as the primary evidence.' };
    }
    if (/analytics|looker|tableau|mixpanel|amplitude|metabase/.test(d)) {
      return { name: 'analytics dashboard', note: 'This looks like an analytics surface, so I prioritized labelled numbers and date ranges.' };
    }
    if (/calendar|outlook|timekit|calendly/.test(d)) {
      return { name: 'calendar', note: 'This looks like a calendar, so I separated fixed events from flexible time.' };
    }
    if (/drive|dropbox|notion|docs\.google/.test(d)) {
      return { name: 'file workspace', note: 'This looks like a file workspace, so I grouped items by project and ownership.' };
    }
    if (/mail|gmail|inbox|outlook/.test(d)) {
      return { name: 'inbox', note: 'This looks like mail, so I separated actionable messages from bulk promotions.' };
    }
    if (/crm|salesforce|hubspot|linkedin|pipedrive/.test(d)) {
      return { name: 'sales surface', note: 'This looks like a sales tool, so I favored named accounts and explicit next steps.' };
    }
    if (/shop|store|amazon|product|pricing|price/.test(d)) {
      return { name: 'commerce page', note: 'This looks like a product or pricing page, so I favored concrete claims and price signals.' };
    }
    return { name: 'web page', note: 'I treated repeated statements and concrete numbers as the strongest signals on the page.' };
  }

  function intentOf(text, actionId) {
    var t = String(text || '').toLowerCase();
    if (actionId && INTENTS[actionId]) return actionId;
    if (/metric|analytics|dashboard|kpi|revenue|numbers|chart/.test(t)) return 'metrics';
    if (/drive|folder|file|organi[sz]e/.test(t)) return 'drive';
    if (/calendar|schedule|meeting|plan (my|the) day|time block/.test(t)) return 'calendar';
    if (/competitor|comparison|compare|deck/.test(t)) return 'competitor';
    if (/crm|sales call|log the call|pipeline/.test(t)) return 'crm';
    if (/email|inbox|promotion|unsubscribe/.test(t)) return 'email';
    if (/bug|edge case|risky|error/.test(t)) return 'bug';
    if (/test plan|tests|coverage/.test(t)) return 'test';
    if (/refactor|clean up code/.test(t)) return 'refactor';
    if (/document|readme|api/.test(t)) return 'code';
    if (/code|function|diff|review/.test(t)) return 'code';
    return 'default';
  }

  function analyze(ctx, sourceText) {
    var title = cleanInline(ctx.title || 'Untitled page') || 'Untitled page';
    var domain = cleanInline(ctx.domain || domainFromUrl(ctx.url || ''));
    var body = String(sourceText || ctx.text || '');
    var words = (body.toLowerCase().match(/[a-z][a-z'-]{2,}/g) || []);
    var freq = {};
    words.forEach(function (word) {
      if (!STOP[word] && word.length > 2) freq[word] = (freq[word] || 0) + 1;
    });
    var terms = Object.keys(freq)
      .sort(function (a, b) { return freq[b] - freq[a] || a.localeCompare(b); })
      .filter(function (word) { return freq[word] > 1 || Object.keys(freq).length < 8; })
      .slice(0, 7);
    if (!terms.length) terms = ['page', 'context', 'notes'];

    var sentences = body.replace(/\s+/g, ' ').split(/[.!?]+\s+/)
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length >= 40 && s.length <= 280 && !/^https?:/i.test(s); });
    var ranked = sentences.map(function (sentence, index) {
      var lower = sentence.toLowerCase();
      var score = terms.reduce(function (sum, term) {
        return sum + (lower.indexOf(term) !== -1 ? freq[term] : 0);
      }, 0) / Math.sqrt(Math.max(24, sentence.length));
      return { sentence: sentence, index: index, score: score };
    }).sort(function (a, b) { return b.score - a.score; }).slice(0, 3)
      .sort(function (a, b) { return a.index - b.index; })
      .map(function (item) { return cleanInline(item.sentence); });
    if (!ranked.length) {
      var excerpt = cleanInline(body.slice(0, 360));
      ranked = [excerpt || 'The page did not expose readable text, so this answer is based on its title and URL only.'];
    }
    return {
      title: title,
      domain: domain,
      body: body,
      words: words.length,
      terms: terms,
      sentences: ranked,
      category: categorize(domain)
    };
  }

  function selectionLine(ctx) {
    var selection = ctx.selection ? cleanInline(ctx.selection.slice(0, 300)) : '';
    if (selection) {
      return 'You highlighted “' + selection + (ctx.selection.length > 300 ? '…' : '') + '”, which I treated as the focus.';
    }
    if (state.contextSource === 'selection') {
      return 'Selection mode is on, but nothing is highlighted right now — I used the full page text instead.';
    }
    return 'No text was highlighted, so I used the full readable page text.';
  }

  function generateChat(ctx, prompt, actionId) {
    var sourceText = state.contextSource === 'selection' && ctx.selection ? ctx.selection : ctx.text;
    var info = analyze(ctx, sourceText);
    var intent = INTENTS[intentOf(prompt, actionId)] || INTENTS.default;
    var lines = [];
    lines.push('Here’s a quick read of **' + info.title + '**' + (info.domain ? ' on ' + info.domain : '') + '.');
    lines.push('');
    lines.push('### What the page says');
    info.sentences.forEach(function (sentence) { lines.push(sentence + '.'); });
    lines.push('');
    lines.push('### On your question');
    lines.push('“' + cleanInline(prompt) + '” — ' + intent.line);
    lines.push('');
    lines.push('### Signals I picked up');
    lines.push('- ' + info.words.toLocaleString() + ' words of readable text. ' + selectionLine(ctx));
    lines.push('- Key terms: ' + info.terms.join(', ') + '.');
    lines.push('- ' + info.category.note);
    lines.push('');
    lines.push('### Suggested next step');
    lines.push(intent.next);
    lines.push('');
    lines.push('*Local demo answer · ' + state.model + ' · ' + state.approvalMode + '. Nothing left this browser.*');
    return lines.join('\n');
  }

  function generateConvert(ctx, prompt, actionId) {
    var sourceText = state.contextSource === 'selection' && ctx.selection ? ctx.selection : ctx.text;
    var info = analyze(ctx, sourceText);
    var intent = INTENTS[intentOf(prompt, actionId)] || INTENTS.default;
    var lines = [];
    lines.push('# ' + info.title + ' — converted brief');
    lines.push('');
    lines.push('> Source: ' + (ctx.url || 'unavailable'));
    lines.push('> Generated locally by Keel · ' + (ctx.capturedAt || new Date().toISOString()) + ' · ' + state.model);
    lines.push('');
    lines.push('## Summary');
    lines.push(info.sentences.join(' ') + (info.sentences.length && !/[.!?]$/.test(info.sentences[info.sentences.length - 1]) ? '.' : ''));
    lines.push('');
    lines.push('## Action items');
    intent.actions.forEach(function (action) { lines.push('- [ ] ' + action); });
    lines.push('- [ ] Verify the top term “' + info.terms[0] + '” against the source page.');
    lines.push('');
    lines.push('## Key facts');
    lines.push('');
    lines.push('| Fact | Detail |');
    lines.push('| --- | --- |');
    lines.push('| Page | ' + info.title + ' |');
    lines.push('| Domain | ' + (info.domain || 'unknown') + ' |');
    lines.push('| Surface | ' + info.category.name + ' |');
    lines.push('| Reading length | ' + info.words.toLocaleString() + ' words |');
    lines.push('| Key terms | ' + info.terms.join(', ') + ' |');
    lines.push('| Highlighted selection | ' + (ctx.selection ? cleanInline(ctx.selection.slice(0, 120)) + '…' : 'none') + ' |');
    lines.push('| Attached context | ' + (state.contextSource === 'selection' ? 'Page selection' : 'Full page') + ' |');
    lines.push('');
    lines.push('## Key terms');
    info.terms.forEach(function (term) { lines.push('- **' + term + '** — appears ' + (info.body.toLowerCase().match(new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length + ' times on the page.'); });
    lines.push('');
    lines.push('## Next steps');
    lines.push('1. ' + intent.next);
    lines.push('2. Assign an owner and a due date to each action item.');
    lines.push('3. Recheck the source page before sharing the brief.');
    lines.push('');
    lines.push('*Deterministic local demo · ' + state.approvalMode + ' · no network requests, no page modifications.*');
    return lines.join('\n');
  }

  /* ------------------------- tiny markdown renderer --------------------- */
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function inlineMd(value) {
    var text = escapeHtml(value)
      .replace(/\[ \]/g, '☐').replace(/\[x\]/g, '☑')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    return text.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  function renderMarkdown(markdown) {
    var lines = String(markdown || '').split('\n');
    var out = [];
    var paragraph = [];
    var listType = null;
    var i = 0;

    function flushParagraph() {
      if (paragraph.length) {
        out.push('<p>' + inlineMd(paragraph.join(' ')) + '</p>');
        paragraph = [];
      }
    }
    function closeList() {
      if (listType) {
        out.push('</' + listType + '>');
        listType = null;
      }
    }

    while (i < lines.length) {
      var line = lines[i];
      var trimmed = line.trim();
      if (!trimmed) {
        flushParagraph(); closeList(); i += 1; continue;
      }
      var heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph(); closeList();
        out.push('<h3>' + inlineMd(heading[2]) + '</h3>');
        i += 1; continue;
      }
      if (/^>\s?/.test(trimmed)) {
        flushParagraph(); closeList();
        out.push('<blockquote>' + inlineMd(trimmed.replace(/^>\s?/, '')) + '</blockquote>');
        i += 1; continue;
      }
      if (/^\|.*\|$/.test(trimmed)) {
        flushParagraph(); closeList();
        var rows = [];
        while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
          rows.push(lines[i].trim()); i += 1;
        }
        var table = '<table>';
        rows.forEach(function (row, rowIndex) {
          var cells = row.slice(1, -1).split('|').map(function (cell) { return cell.trim(); });
          if (cells.every(function (cell) { return /^:?-{3,}:?$/.test(cell); })) return;
          var tag = rowIndex === 0 ? 'th' : 'td';
          table += '<tr>' + cells.map(function (cell) {
            return '<' + tag + '>' + inlineMd(cell) + '</' + tag + '>';
          }).join('') + '</tr>';
        });
        out.push(table + '</table>');
        continue;
      }
      var bullet = trimmed.match(/^[-*]\s+(.*)$/);
      if (bullet) {
        flushParagraph();
        if (listType !== 'ul') { closeList(); out.push('<ul>'); listType = 'ul'; }
        out.push('<li>' + inlineMd(bullet[1]) + '</li>');
        i += 1; continue;
      }
      var numbered = trimmed.match(/^\d+\.\s+(.*)$/);
      if (numbered) {
        flushParagraph();
        if (listType !== 'ol') { closeList(); out.push('<ol>'); listType = 'ol'; }
        out.push('<li>' + inlineMd(numbered[1]) + '</li>');
        i += 1; continue;
      }
      paragraph.push(trimmed);
      i += 1;
    }
    flushParagraph(); closeList();
    return out.join('');
  }

  /* ---------------------------- conversation --------------------------- */
  function scrollToBottom() {
    if (el.mainContent) el.mainContent.scrollTop = el.mainContent.scrollHeight;
  }

  function appendMessage(role, content) {
    if (!el.conversation) return null;
    el.conversation.hidden = false;
    var root = document.createElement('div');
    root.className = 'msg ' + (role === 'user' ? 'user' : 'assistant');
    var body = document.createElement('div');
    body.className = 'msg-body';
    root.appendChild(body);
    el.conversation.appendChild(root);
    if (role === 'user') body.textContent = content || '';
    else if (content) body.innerHTML = renderMarkdown(content);
    scrollToBottom();
    return { root: root, body: body };
  }

  function renderConversation() {
    if (!el.conversation) return;
    el.conversation.innerHTML = '';
    var messages = state.session && Array.isArray(state.session.messages) ? state.session.messages : [];
    if (messages.length) {
      if (el.hero) el.hero.hidden = true;
      messages.forEach(function (message) {
        appendMessage(message.role === 'user' ? 'user' : 'assistant', message.content || '');
      });
    } else if (el.hero) {
      el.hero.hidden = false;
      el.conversation.hidden = true;
    }
  }

  function updateSendButton() {
    if (!el.sendBtn) return;
    el.sendBtn.classList.toggle('is-stop', state.streaming);
    el.sendBtn.setAttribute('aria-label', state.streaming ? 'Stop generating' : 'Send message');
    el.sendBtn.title = state.streaming ? 'Stop generating' : 'Send message';
    if (el.sendIcon) {
      el.sendIcon.innerHTML = state.streaming
        ? '<rect x="6" y="6" width="8" height="8" rx="1" fill="currentColor"/>'
        : '<path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M10 16V4M5 9l5-5 5 5"/>';
    }
  }

  function streamInto(body, text, token) {
    return new Promise(function (resolve) {
      if (!state.settings.stream || state.settings.reduceMotion) {
        body.innerHTML = renderMarkdown(text);
        scrollToBottom();
        resolve(true);
        return;
      }
      var index = 0;
      var step = Math.max(3, Math.ceil(text.length / 115));
      function tick() {
        if (token !== state.token) { resolve(false); return; }
        index = Math.min(text.length, index + step);
        body.textContent = text.slice(0, index);
        scrollToBottom();
        if (index < text.length) {
          state.timer = setTimeout(tick, 13);
        } else {
          body.innerHTML = renderMarkdown(text);
          scrollToBottom();
          resolve(true);
        }
      }
      tick();
    });
  }

  function recordMessage(role, content) {
    if (!state.session) return;
    if (!Array.isArray(state.session.messages)) state.session.messages = [];
    state.session.messages.push({ role: role, content: content, at: new Date().toISOString() });
    state.session.updatedAt = new Date().toISOString();
  }

  async function saveSession() {
    if (!state.session || !state.settings.autoSave) return;
    var response = await sendMessage({ type: 'SAVE_SESSION', session: clone(state.session) });
    if (response && response.ok) {
      if (Array.isArray(response.sessions)) state.sessions = response.sessions;
    }
  }

  function stopRun() {
    if (!state.streaming) return;
    state.token += 1;
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    var active = state.activeMessage;
    if (active && active.body) {
      var partial = active.body.textContent.trim();
      var footer = document.createElement('div');
      footer.className = 'msg-footer';
      footer.textContent = '— Stopped' + (partial ? ' after ' + partial.length + ' characters' : '');
      if (active.root) active.root.appendChild(footer);
      recordMessage('assistant', partial ? partial + '\n\n— Stopped.' : '— Stopped.');
    }
    state.streaming = false;
    state.activeMessage = null;
    updateSendButton();
    saveSession();
    toast('Generation stopped. The partial answer was saved.');
  }

  async function ensureSession(title) {
    if (state.session) return;
    var ctx = state.context || {};
    var response = await sendMessage({
      type: 'NEW_SESSION',
      title: title || 'New Keel session',
      mode: state.mode,
      model: state.model,
      context: { title: ctx.title, url: ctx.url, domain: ctx.domain }
    });
    if (response && response.ok && response.session) {
      state.session = clone(response.session);
      if (Array.isArray(response.sessions)) state.sessions = response.sessions;
    } else {
      state.session = {
        id: 'local-' + Date.now(),
        title: title || 'New Keel session',
        mode: state.mode,
        model: state.model,
        context: null,
        messages: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
    }
  }

  async function runTurn(prompt) {
    if (state.streaming || !prompt || !prompt.trim()) return;
    var text = prompt.trim();
    if (!state.context || !state.context.text) await loadContext(false);

    await ensureSession(text.slice(0, 52));
    if (state.session) {
      state.session.title = text.length > 52 ? text.slice(0, 52) + '…' : text;
      if (!state.session.mode) state.session.mode = state.mode;
    }
    recordMessage('user', text);
    appendMessage('user', text);
    if (el.composerInput) { el.composerInput.value = ''; autoResize(); }
    if (el.hero) el.hero.hidden = true;
    if (el.welcomeNote) el.welcomeNote.hidden = true;

    var answer = state.mode === 'Convert'
      ? generateConvert(state.context || {}, text, state.activeAction)
      : generateChat(state.context || {}, text, state.activeAction);
    state.activeAction = null;

    var message = appendMessage('assistant', '');
    if (!message) { saveSession(); return; }
    if (message.root) message.root.classList.add('is-streaming');
    state.activeMessage = message;
    state.streaming = true;
    state.token += 1;
    var token = state.token;
    updateSendButton();

    var completed = await streamInto(message.body, answer, token);
    if (message.root) message.root.classList.remove('is-streaming');
    if (!completed || token !== state.token) {
      state.streaming = false;
      state.activeMessage = null;
      updateSendButton();
      return;
    }
    var footer = document.createElement('div');
    footer.className = 'msg-footer';
    footer.textContent = state.mode + ' · ' + state.model + ' · ' + state.approvalMode + ' · generated locally';
    if (message.root) message.root.appendChild(footer);
    recordMessage('assistant', answer);
    state.streaming = false;
    state.activeMessage = null;
    updateSendButton();
    saveSession();
  }

  async function newSession() {
    if (state.streaming) stopRun();
    state.session = null;
    state.activeAction = null;
    if (el.composerInput) { el.composerInput.value = ''; autoResize(); }
    renderConversation();
    if (el.hero) el.hero.hidden = false;
    if (el.conversation) el.conversation.hidden = true;
    if (el.mainContent) el.mainContent.scrollTop = 0;
    await sendMessage({ type: 'CLEAR_PENDING_ACTION' });
    toast('New session started. Saved sessions remain in History.');
  }

  /* --------------------------- session history -------------------------- */
  async function loadSessions() {
    var response = await sendMessage({ type: 'LIST_SESSIONS' });
    if (response && response.ok && Array.isArray(response.sessions)) {
      state.sessions = response.sessions;
    }
    renderSessions();
  }

  function renderSessions() {
    if (!el.sessionList) return;
    el.sessionList.innerHTML = '';
    if (!state.sessions.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'Nothing saved yet. Ask a question and the session will appear here.';
      el.sessionList.appendChild(empty);
      return;
    }
    state.sessions.forEach(function (session) {
      var card = document.createElement('div');
      card.className = 'session-card';
      var open = document.createElement('button');
      open.type = 'button';
      open.className = 'session-open';
      var title = document.createElement('span');
      title.className = 'session-title';
      title.textContent = session.title || 'Keel session';
      var meta = document.createElement('span');
      meta.className = 'session-meta';
      var count = Array.isArray(session.messages) ? session.messages.length : 0;
      meta.textContent = (session.mode || 'Chat') + ' · ' + count + ' messages · ' +
        new Date(session.updatedAt || Date.now()).toLocaleDateString();
      open.appendChild(title);
      open.appendChild(meta);
      open.addEventListener('click', function () { restoreSession(session.id); });
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'session-delete';
      remove.setAttribute('aria-label', 'Delete session ' + (session.title || ''));
      remove.textContent = '×';
      remove.addEventListener('click', function () { deleteSession(session.id); });
      card.appendChild(open);
      card.appendChild(remove);
      el.sessionList.appendChild(card);
    });
  }

  function restoreSession(id) {
    var found = state.sessions.filter(function (session) { return session.id === id; })[0];
    if (!found) return;
    state.session = clone(found);
    setMode(state.session.mode === 'Convert' ? 'Convert' : 'Chat', true);
    setModel(state.session.model || state.model, true);
    renderConversation();
    closeDrawers();
    toast('Session restored.');
  }

  async function deleteSession(id) {
    var next = state.sessions.filter(function (session) { return session.id !== id; });
    var response = await sendMessage({ type: 'SAVE_SESSIONS_REPLACE', sessions: next });
    if (!response || !response.ok) {
      /* fallback: remove locally and refresh from storage */
    }
    state.sessions = next;
    renderSessions();
    toast('Session removed.');
  }

  async function clearAllSessions() {
    await sendMessage({ type: 'CLEAR_SESSIONS' });
    state.sessions = [];
    renderSessions();
    toast('Session history cleared.');
  }

  /* ------------------------------- settings ----------------------------- */
  async function updateSettings(patch) {
    Object.keys(patch).forEach(function (key) { state.settings[key] = patch[key]; });
    applySettingsUI();
    var response = await sendMessage({ type: 'SET_SETTINGS', settings: patch });
    if (response && response.ok && response.settings) state.settings = Object.assign({}, DEFAULT_SETTINGS, response.settings);
    applySettingsUI();
  }

  async function resetPreferences() {
    state.settings = Object.assign({}, DEFAULT_SETTINGS);
    setModel('Mythos', true);
    setApprovalMode('Ask before each action', true);
    setMode('Chat', true);
    setActiveTab('Keel');
    setContextSource('full', true);
    await updateSettings(state.settings);
    toast('Preferences reset.');
  }

  /* -------------------------------- events ------------------------------ */
  function bindEvents() {
    if (el.newSessionBtn) el.newSessionBtn.addEventListener('click', newSession);
    if (el.historyBtn) el.historyBtn.addEventListener('click', function () {
      if (!el.historyDrawer || el.historyDrawer.hidden) openDrawer('history'); else closeDrawers();
    });
    if (el.closeHistoryBtn) el.closeHistoryBtn.addEventListener('click', closeDrawers);
    if (el.closeSettingsBtn) el.closeSettingsBtn.addEventListener('click', closeDrawers);
    if (el.drawerBackdrop) el.drawerBackdrop.addEventListener('click', closeDrawers);

    if (el.accountBtn) el.accountBtn.addEventListener('click', function () { toggleMenu(el.accountMenu, el.accountBtn); });
    if (el.settingsMenuItem) el.settingsMenuItem.addEventListener('click', function () { openDrawer('settings'); });

    var tabs = document.querySelectorAll('.tool-tab');
    Array.prototype.forEach.call(tabs, function (button) {
      button.addEventListener('click', function () { setActiveTab(button.getAttribute('data-tab')); });
      button.addEventListener('keydown', function (event) {
        var index = TABS.indexOf(button.getAttribute('data-tab'));
        var next = null;
        if (event.key === 'ArrowRight') next = TABS[(index + 1) % TABS.length];
        if (event.key === 'ArrowLeft') next = TABS[(index - 1 + TABS.length) % TABS.length];
        if (next) {
          event.preventDefault();
          setActiveTab(next);
          var target = byId(TAB_IDS[next]);
          if (target) target.focus();
        }
      });
    });

    if (el.refreshContextBtn) el.refreshContextBtn.addEventListener('click', function () { loadContext(true); });
    if (el.contextChip) el.contextChip.addEventListener('click', function () {
      var ctx = state.context || {};
      copyText([ctx.title, ctx.url].filter(Boolean).join('\n') || 'No page context available.').then(function (ok) {
        toast(ok ? 'Page title and URL copied.' : 'Copy failed in this context.');
      });
    });

    if (el.modeChat) el.modeChat.addEventListener('click', function () { setMode('Chat', true); });
    if (el.modeConvert) el.modeConvert.addEventListener('click', function () { setMode('Convert', true); });
    if (el.modeKey) el.modeKey.addEventListener('click', toggleMode);

    if (el.copyMarkdownBtn) el.copyMarkdownBtn.addEventListener('click', function () {
      copyText(contextMarkdown()).then(function (ok) {
        toast(ok ? 'Page context copied as markdown.' : 'Copy failed in this context.');
        if (el.copyMarkdownBtn) el.copyMarkdownBtn.focus();
      });
    });
    if (el.dismissWelcomeBtn) el.dismissWelcomeBtn.addEventListener('click', function () {
      state.welcomeSeen = true;
      if (el.welcomeNote) el.welcomeNote.hidden = true;
      sendMessage({ type: 'SET_WELCOME_SEEN', seen: true });
    });

    if (el.attachBtn) el.attachBtn.addEventListener('click', function () { toggleMenu(el.attachMenu, el.attachBtn); });
    if (el.attachMenu) {
      Array.prototype.forEach.call(el.attachMenu.querySelectorAll('[data-source]'), function (item) {
        item.addEventListener('click', function () {
          setContextSource(item.getAttribute('data-source'), true);
          el.attachMenu.hidden = true;
          if (el.attachBtn) el.attachBtn.setAttribute('aria-expanded', 'false');
          toast(item.getAttribute('data-source') === 'selection'
            ? 'Using your highlighted text when available.'
            : 'Using the full page text.');
        });
      });
    }
    if (el.clearAttachBtn) el.clearAttachBtn.addEventListener('click', function () {
      if (el.attachedBar) el.attachedBar.hidden = true;
      toast('Attachment cleared.');
    });
    if (el.micBtn) el.micBtn.addEventListener('click', function () { setListening(!state.listening); });
    if (el.stopListeningBtn) el.stopListeningBtn.addEventListener('click', function () { setListening(false); });

    if (el.modelSelect) el.modelSelect.addEventListener('change', function () {
      setModel(el.modelSelect.value, true);
      toast('Model set to ' + state.model + ' (local demo).');
    });
    if (el.approvalSelect) el.approvalSelect.addEventListener('change', function () {
      setApprovalMode(el.approvalSelect.value, true);
      toast('Approval mode: ' + state.approvalMode + '.');
    });

    if (el.composerInput) {
      el.composerInput.addEventListener('input', autoResize);
      el.composerInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (state.streaming) stopRun(); else runTurn(el.composerInput.value);
        }
      });
    }
    if (el.sendBtn) el.sendBtn.addEventListener('click', function () {
      if (state.streaming) stopRun(); else if (el.composerInput) runTurn(el.composerInput.value);
    });

    if (el.settingStream) el.settingStream.addEventListener('change', function () { updateSettings({ stream: el.settingStream.checked }); });
    if (el.settingAutoSave) el.settingAutoSave.addEventListener('change', function () { updateSettings({ autoSave: el.settingAutoSave.checked }); });
    if (el.settingHints) el.settingHints.addEventListener('change', function () { updateSettings({ keyboardHints: el.settingHints.checked }); });
    if (el.settingReduceMotion) el.settingReduceMotion.addEventListener('change', function () { updateSettings({ reduceMotion: el.settingReduceMotion.checked }); });
    if (el.clearHistoryBtn) el.clearHistoryBtn.addEventListener('click', clearAllSessions);
    if (el.resetPrefsBtn) el.resetPrefsBtn.addEventListener('click', resetPreferences);

    document.addEventListener('click', function (event) {
      var target = event.target;
      if (el.attachMenu && !el.attachMenu.hidden && !el.attachMenu.contains(target) && el.attachBtn && !el.attachBtn.contains(target)) {
        el.attachMenu.hidden = true;
        el.attachBtn.setAttribute('aria-expanded', 'false');
      }
      if (el.accountMenu && !el.accountMenu.hidden && !el.accountMenu.contains(target) && el.accountBtn && !el.accountBtn.contains(target)) {
        el.accountMenu.hidden = true;
        el.accountBtn.setAttribute('aria-expanded', 'false');
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        closeMenus();
        closeDrawers();
        setListening(false);
        return;
      }
      var tag = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : '';
      var typing = tag === 'textarea' || tag === 'input' || tag === 'select' || (event.target && event.target.isContentEditable);
      if (!typing && !event.ctrlKey && !event.metaKey && !event.altKey &&
          state.settings.keyboardHints && (event.key === 'k' || event.key === 'K')) {
        event.preventDefault();
        toggleMode();
      }
    });

    if (globalThis.chrome && globalThis.chrome.runtime && globalThis.chrome.runtime.onMessage &&
        typeof globalThis.chrome.runtime.onMessage.addListener === 'function') {
      globalThis.chrome.runtime.onMessage.addListener(function (message) {
        if (message && message.type === 'KEEL_PAGE_CHANGED') loadContext(false);
      });
    }
  }

  /* --------------------------------- boot ------------------------------- */
  async function init() {
    cacheElements();
    bindEvents();
    var response = await sendMessage({ type: 'GET_STATE' });
    if (response && response.ok && response.state) applyState(response.state);

    setModel(state.model, false);
    setApprovalMode(state.approvalMode, false);
    setActiveTab(state.activeTab);
    setMode(state.mode, false);
    setContextSource(state.contextSource, false);
    if (el.attachedBar) el.attachedBar.hidden = true;
    applySettingsUI();
    if (el.welcomeNote) el.welcomeNote.hidden = state.welcomeSeen;
    updateSendButton();

    await loadContext(false);

    var pending = await sendMessage({ type: 'GET_PENDING_ACTION' });
    if (pending && pending.ok && pending.action && pending.action.type) {
      var isConvert = pending.action.type === 'convert';
      setMode(isConvert ? 'Convert' : 'Chat', true);
      var prompt = isConvert
        ? 'Turn this page into a structured deliverable.'
        : 'What should I know about this page?';
      if (el.composerInput) el.composerInput.value = prompt;
      await sendMessage({ type: 'CLEAR_PENDING_ACTION' });
      runTurn(prompt);
    }
  }

  init().catch(function (error) {
    toast('Keel panel could not start: ' + String((error && error.message) || error));
  });
})();

/* Keel — /new page behaviour. Uses the shared window.KeelChat module. */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }

  var app = $('n-app');
  var sidebarToggle = $('n-sidebar-toggle');
  var collapse = $('n-collapse');
  var scrim = $('n-scrim');
  var settingsBtn = $('n-settings');
  var helpBtn = $('n-help');

  var recentsToggle = $('n-recents-toggle');
  var recentsScroll = $('n-recents-scroll');
  var recentsFilter = $('n-recents-filter');
  var recentsList = $('n-recents-list');
  var recentsEmpty = $('n-recents-empty');
  var recentsViewAll = $('n-recents-view-all');
  var searchWrap = $('n-recents-search-wrap');
  var searchInput = $('n-recents-search');
  var searchClose = $('n-recents-search-close');

  var accountBtn = $('n-account');
  var accountMenu = $('n-account-menu');
  var accountUpgrade = $('n-account-upgrade');
  var accountSettings = $('n-account-settings');

  var upgradeBtn = $('n-upgrade');
  var conversation = $('n-conversation');
  var input = $('n-input');
  var attachBtn = $('n-attach');
  var fileInput = $('n-file-input');
  var attachmentsEl = $('n-attachments');
  var sendBtn = $('n-send');
  var stopBtn = $('n-stop');
  var clearBtn = $('n-clear');
  var errorEl = $('n-chat-error');
  var errorText = $('n-chat-error-text');
  var errorAction = $('n-chat-error-action');
  var micBtn = $('n-mic');
  var voiceChevron = $('n-voice-chevron');
  var voiceWave = $('n-voice-wave');
  var voiceStatus = $('n-voice-status');
  var voiceStatusText = $('n-voice-status-text');
  var voiceStop = $('n-voice-stop');

  var providerBtn = $('n-provider-btn');
  var providerName = $('n-provider-name');
  var providerDot = $('n-provider-dot');
  var modelBtn = $('n-model-btn');
  var modelName = $('n-model-name');
  var modelWeight = $('n-model-weight');
  var usageEl = $('n-usage');

  var artifactsAll = $('n-artifacts-all');
  var artifactCards = Array.prototype.slice.call(document.querySelectorAll('.n-artifact-card'));

  var infoPanel = $('n-info-panel');
  var infoTitle = $('n-info-title');
  var infoText = $('n-info-text');
  var infoLink = $('n-info-link');
  var infoClose = $('n-info-close');
  var infoTimer = null;

  var dialog = $('n-dialog');
  var dialogCard = $('n-dialog-card');
  var dialogClose = $('n-dialog-close');
  var dialogBackdrop = $('n-dialog-backdrop');
  var dialogTitle = $('n-dialog-title');
  var dialogTabs = $('n-dialog-tabs');
  var dialogTabButtons = Array.prototype.slice.call(dialogTabs.querySelectorAll('.n-dialog-tab'));
  var dialogViews = Array.prototype.slice.call(dialog.querySelectorAll('.n-dialog-view'));
  var providerCards = $('n-provider-cards');
  var preferredSelect = $('n-preferred');
  var settingsStatus = $('n-settings-status');
  var instructionsEl = $('n-instructions');
  var instructionsMeta = $('n-instructions-meta');
  var saveInstructions = $('n-save-instructions');
  var fontSeg = $('n-font-seg');
  var generalStatus = $('n-general-status');
  var helpSettings = $('n-help-settings');
  var accountDialogUpgrade = $('n-account-dialog-upgrade');
  var lastFocused = null;

  var RECENTS_KEY = 'keel_new_recents_v1';
  var recents = [];
  var allRecents = false;

  var attached = [];
  var chatHistory = [];
  var streaming = false;
  var cancelled = false;
  var controller = null;
  var voiceSource = null;

  /* ------------------------------ helpers ------------------------------ */

  function api() {
    if (!window.KeelChat && !Chat) return null;
    if (!Chat && window.KeelChat) Chat = window.KeelChat;
    return Chat;
  }
  var Chat = window.KeelChat || null;

  function shortError(err) {
    var text = (err && err.message) || String(err || 'error');
    return text.slice(0, 180);
  }

  function getSettingsSafe() {
    try {
      var engine = api();
      return (engine && engine.getSettings && engine.getSettings()) || {};
    } catch (error) { return {}; }
  }

  function saveSettingsSafe(patch) {
    try {
      var engine = api();
      if (engine && engine.saveSettings) return engine.saveSettings(patch);
    } catch (error) { /* private browsing or bad storage — keep UI working */ }
    return null;
  }

  function getProvidersSafe() {
    try {
      var engine = api();
      return (engine && engine.getProviders && engine.getProviders()) || {};
    } catch (error) { return {}; }
  }

  function configuredName() {
    try {
      var engine = api();
      return (engine && engine.configuredProvider && engine.configuredProvider()) || '';
    } catch (error) { return ''; }
  }

  function activeProvider() {
    var settings = getSettingsSafe();
    var preferred = (settings.providerConfig && settings.providerConfig.preferred) || 'auto';
    var providers = getProvidersSafe();
    if (preferred && preferred !== 'auto' && providers[preferred] && providers[preferred].key) return preferred;
    return configuredName();
  }

  function modelFor(name) {
    if (!name) return '';
    try {
      var engine = api();
      if (engine && engine.providerModel) {
        var model = engine.providerModel(name);
        if (model) return model;
      }
    } catch (error) { /* fall through to local lookup */ }
    var entry = getProvidersSafe()[name] || {};
    var defs = (api() && api().PROVIDERS) || {};
    return entry.model || (defs[name] && defs[name].defaultModel) || '';
  }

  function providerLabel(name) {
    if (name === 'openrouter') return 'OpenRouter';
    if (name === 'google') return 'Google AI Studio';
    return name || 'Provider';
  }

  function hideInfo() {
    if (infoTimer !== null) {
      window.clearTimeout(infoTimer);
      infoTimer = null;
    }
    infoPanel.hidden = true;
  }

  function showInfo(title, text, href) {
    infoTitle.textContent = title;
    infoText.textContent = text;
    if (href) {
      infoLink.href = href;
      infoLink.hidden = false;
    } else {
      infoLink.hidden = true;
    }
    infoPanel.hidden = false;
    if (infoTimer !== null) window.clearTimeout(infoTimer);
    infoTimer = window.setTimeout(hideInfo, 12000);
  }

  infoClose.addEventListener('click', hideInfo);

  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }

  function scrollConversation() {
    conversation.scrollTop = conversation.scrollHeight;
  }

  function formatSize(bytes) {
    var n = Number(bytes) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return Math.round(n / 1024) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
  }

  /* ------------------------------ sidebar ------------------------------ */

  var mobileQuery = window.matchMedia ? window.matchMedia('(max-width: 860px)') : null;

  function isMobile() { return !!(mobileQuery && mobileQuery.matches); }

  function isSidebarOpen() {
    if (isMobile()) return app.classList.contains('sidebar-open');
    return !app.classList.contains('sidebar-collapsed');
  }

  function syncSidebarToggles() {
    var open = isSidebarOpen();
    sidebarToggle.setAttribute('aria-expanded', String(open));
    collapse.setAttribute('aria-expanded', String(open));
    collapse.setAttribute('aria-label', open ? 'Collapse sidebar' : 'Expand sidebar');
  }

  function setSidebar(open) {
    app.classList.remove('sidebar-open');
    app.classList.remove('sidebar-collapsed');
    if (isMobile()) {
      if (open) app.classList.add('sidebar-open');
    } else if (!open) {
      app.classList.add('sidebar-collapsed');
    }
    syncSidebarToggles();
  }

  function onViewportChange() {
    app.classList.remove('sidebar-open');
    app.classList.remove('sidebar-collapsed');
    syncSidebarToggles();
  }

  sidebarToggle.addEventListener('click', function () { setSidebar(!isSidebarOpen()); });
  collapse.addEventListener('click', function () { setSidebar(!isSidebarOpen()); });
  scrim.addEventListener('click', function () { setSidebar(false); });

  if (mobileQuery) {
    if (mobileQuery.addEventListener) mobileQuery.addEventListener('change', onViewportChange);
    else if (mobileQuery.addListener) mobileQuery.addListener(onViewportChange);
  }
  onViewportChange();

  /* ------------------------------ recents ------------------------------ */

  function recentText(item) {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') return item.title || item.prompt || '';
    return '';
  }

  function recentPrompt(item) {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') return item.prompt || item.title || '';
    return '';
  }

  function loadRecents() {
    try {
      var parsed = JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]');
      recents = Array.isArray(parsed) ? parsed.filter(function (item) {
        return !!recentText(item);
      }).slice(0, 50) : [];
    } catch (error) { recents = []; }
  }

  function saveRecent(text) {
    var clean = String(text || '').replace(/\s+/g, ' ').trim();
    var title = clean.slice(0, 60) || 'Untitled chat';
    var next = [{ title: title, prompt: clean, ts: Date.now() }];
    recents.forEach(function (item) {
      if (recentText(item) !== title) next.push(item);
    });
    recents = next.slice(0, 30);
    try { localStorage.setItem(RECENTS_KEY, JSON.stringify(recents)); } catch (error) { /* storage disabled */ }
    allRecents = false;
    renderRecents();
  }

  function applyRecents() {
    var query = searchInput.value.trim().toLowerCase();
    var rows = Array.prototype.slice.call(recentsList.children);
    var visible = 0;
    rows.forEach(function (li, index) {
      var button = li.querySelector('.n-recent');
      var title = (button ? button.getAttribute('data-title') : '').toLowerCase();
      var isExtra = index >= 4;
      var show = (!query || title.indexOf(query) !== -1) && (!isExtra || allRecents || !!query);
      li.hidden = !show;
      if (show) visible += 1;
    });

    if (!recents.length) {
      recentsEmpty.textContent = 'No recent chats yet';
      recentsEmpty.hidden = false;
    } else if (query && visible === 0) {
      recentsEmpty.textContent = 'No matching chats.';
      recentsEmpty.hidden = false;
    } else {
      recentsEmpty.hidden = true;
    }

    var useful = recents.length > 4;
    recentsViewAll.hidden = !useful;
    recentsViewAll.textContent = allRecents ? 'Show less' : 'View all';
    recentsViewAll.setAttribute('aria-expanded', String(allRecents));
    recentsViewAll.setAttribute('aria-label', allRecents ? 'Show fewer recent chats' : 'Show all recent chats');
  }

  function renderRecents() {
    recentsList.textContent = '';
    recents.forEach(function (item) {
      var title = recentText(item);
      if (!title) return;
      var li = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'n-recent';
      button.setAttribute('data-title', title);
      button.setAttribute('data-prompt', recentPrompt(item));
      button.innerHTML = '<svg class="n-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#n-chat"/></svg>';
      var label = document.createElement('span');
      label.textContent = title;
      button.appendChild(label);
      button.addEventListener('click', function () {
        var prompt = button.getAttribute('data-prompt') || title;
        input.value = prompt;
        autoResize();
        hideError();
        if (isMobile()) setSidebar(false);
        input.focus();
        input.setSelectionRange(prompt.length, prompt.length);
        showInfo('Recent chat', 'Loaded into the composer. Press Enter to send it again.', null);
      });
      li.appendChild(button);
      recentsList.appendChild(li);
    });
    applyRecents();
  }

  function openRecentsFilter() {
    searchWrap.hidden = false;
    recentsFilter.setAttribute('aria-expanded', 'true');
    searchInput.focus();
  }

  function closeRecentsFilter(restoreFocus) {
    searchWrap.hidden = true;
    recentsFilter.setAttribute('aria-expanded', 'false');
    searchInput.value = '';
    applyRecents();
    if (restoreFocus) recentsFilter.focus();
  }

  recentsFilter.addEventListener('click', function () {
    if (searchWrap.hidden) openRecentsFilter(); else closeRecentsFilter(false);
  });
  searchClose.addEventListener('click', function () { closeRecentsFilter(true); });
  searchInput.addEventListener('input', applyRecents);

  recentsToggle.addEventListener('click', function () {
    var willShow = recentsScroll.hidden;
    recentsScroll.hidden = !willShow;
    recentsFilter.hidden = !willShow;
    recentsViewAll.hidden = !willShow || recents.length <= 4;
    if (!willShow) closeRecentsFilter(false);
    recentsToggle.setAttribute('aria-expanded', String(willShow));
  });

  recentsViewAll.addEventListener('click', function () {
    allRecents = !allRecents;
    applyRecents();
  });

  /* ------------------------------- menus -------------------------------- */

  var menuPairs = [{ btn: accountBtn, menu: accountMenu }];

  function getMenuItems(menu) {
    return Array.prototype.slice.call(menu.querySelectorAll('[role="menuitemradio"], [role="menuitem"]'))
      .filter(function (item) { return !item.hidden && item.offsetParent !== null; });
  }

  function closeMenus() {
    menuPairs.forEach(function (pair) {
      pair.menu.hidden = true;
      pair.btn.setAttribute('aria-expanded', 'false');
    });
  }

  function toggleMenu(pair) {
    var willOpen = pair.menu.hidden;
    closeMenus();
    if (willOpen) {
      pair.menu.hidden = false;
      pair.btn.setAttribute('aria-expanded', 'true');
      var items = getMenuItems(pair.menu);
      if (items.length) items[0].focus();
    } else {
      pair.btn.focus();
    }
  }

  menuPairs.forEach(function (pair) {
    pair.btn.addEventListener('click', function (event) {
      event.stopPropagation();
      toggleMenu(pair);
    });
    pair.menu.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMenus();
        pair.btn.focus();
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      var items = getMenuItems(pair.menu);
      if (!items.length) return;
      var index = items.indexOf(document.activeElement);
      event.preventDefault();
      if (event.key === 'ArrowDown') items[(index + 1) % items.length].focus();
      else items[(index - 1 + items.length) % items.length].focus();
    });
  });

  accountUpgrade.addEventListener('click', function () { closeMenus(); openDialog('plans'); });
  accountSettings.addEventListener('click', function () { closeMenus(); openDialog('providers'); });
  accountMenu.addEventListener('click', function () { closeMenus(); });

  document.addEventListener('click', function (event) {
    if (!event.target.closest('#n-account-wrap')) closeMenus();
  });

  /* ------------------------------- dialog ------------------------------- */

  var dialogTitles = {
    plans: 'Keel plans',
    help: 'Help with Keel',
    providers: 'Provider settings',
    general: 'General settings',
    account: 'Account'
  };
  var settingsViews = ['providers', 'general', 'account'];

  function showDialogView(view) {
    dialogTitle.textContent = dialogTitles[view] || 'Keel';
    dialogCard.classList.toggle('is-wide', settingsViews.indexOf(view) !== -1);
    dialogTabs.hidden = settingsViews.indexOf(view) === -1;
    dialogViews.forEach(function (section) {
      section.hidden = section.getAttribute('data-view') !== view;
    });
    dialogTabButtons.forEach(function (tab) {
      tab.setAttribute('aria-selected', String(tab.getAttribute('data-view') === view));
    });
    if (view === 'providers') renderProviderCards();
    if (view === 'general') hydrateGeneral();
  }

  function openDialog(view) {
    lastFocused = document.activeElement;
    showDialogView(view);
    dialog.hidden = false;
    dialogClose.focus();
  }

  function closeDialog() {
    dialog.hidden = true;
    dialogViews.forEach(function (section) { section.hidden = true; });
    if (lastFocused && document.contains(lastFocused) && typeof lastFocused.focus === 'function') {
      lastFocused.focus();
    }
    lastFocused = null;
  }

  dialogTabButtons.forEach(function (tab) {
    tab.addEventListener('click', function () { showDialogView(tab.getAttribute('data-view')); });
  });

  upgradeBtn.addEventListener('click', function () { openDialog('plans'); });
  helpBtn.addEventListener('click', function () { openDialog('help'); });
  settingsBtn.addEventListener('click', function () { openDialog('general'); });
  providerBtn.addEventListener('click', function () { openDialog('providers'); });
  modelBtn.addEventListener('click', function () { openDialog('providers'); });
  helpSettings.addEventListener('click', function () { openDialog('providers'); });
  accountDialogUpgrade.addEventListener('click', function () { showDialogView('plans'); });
  dialogClose.addEventListener('click', closeDialog);
  dialogBackdrop.addEventListener('click', closeDialog);

  dialogCard.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = Array.prototype.slice.call(dialogCard.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (element) { return element.offsetParent !== null; });
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  /* --------------------------- provider pane ---------------------------- */

  function setStatus(node, text, kind) {
    node.textContent = text;
    node.className = 'n-provider-msg' + (kind ? ' is-' + kind : '');
  }

  function setSettingsStatus(text, kind) {
    settingsStatus.textContent = text;
    settingsStatus.className = 'n-settings-status' + (kind ? ' is-' + kind : '');
  }

  function loadModels(name, select, msg) {
    var engine = api();
    var defs = (engine && engine.PROVIDERS) || {};
    var def = defs[name] || {};
    var current = modelFor(name);

    function addOption(id) {
      if (!id) return;
      var option = document.createElement('option');
      option.value = id;
      option.textContent = id;
      select.appendChild(option);
    }

    select.textContent = '';
    addOption(current || def.defaultModel || '');
    if (!engine || typeof engine.fetchModels !== 'function') {
      setStatus(msg, 'Model catalog is unavailable here. The default model is still usable.', 'error');
      return;
    }
    setStatus(msg, 'Loading models…', '');
    Promise.resolve().then(function () { return engine.fetchModels(name); }).then(function (models) {
      var list = Array.isArray(models) ? models.filter(Boolean).slice(0, 300) : [];
      select.textContent = '';
      if (!list.length) addOption(current || def.defaultModel || '');
      list.forEach(addOption);
      if (current && select.offsetParent !== null) {
        var found = false;
        Array.prototype.forEach.call(select.options, function (option) {
          if (option.value === current) found = true;
        });
        if (!found) addOption(current);
      }
      select.value = current || def.defaultModel || (select.options[0] && select.options[0].value) || '';
      setStatus(msg, list.length ? list.length + ' models available — pick one to pin it.' : 'No catalog found; using the default model.', list.length ? 'ok' : 'error');
    }).catch(function (err) {
      setStatus(msg, 'Could not load models (' + shortError(err) + '). The default is still usable.', 'error');
    });
  }

  function syncChips() {
    var name = activeProvider();
    providerDot.classList.toggle('is-ready', !!name);
    providerName.textContent = name ? 'Provider: ' + providerLabel(name) : 'Set up a provider';
    var model = name ? modelFor(name) : '';
    modelName.textContent = model || 'Choose a model';
    modelWeight.textContent = name ? 'Settings' : 'Setup';
    var settings = getSettingsSafe();
    var preferred = (settings.providerConfig && settings.providerConfig.preferred) || 'auto';
    preferredSelect.value = preferred;
  }

  function renderProviderCards() {
    providerCards.textContent = '';
    var engine = api();
    var defs = (engine && engine.PROVIDERS) || {};
    var providers = getProvidersSafe();
    var names = ['openrouter', 'google'];

    names.forEach(function (name) {
      var def = defs[name] || {};
      var label = providerLabel(name);
      var entry = providers[name] || {};
      var ready = !!entry.key;
      var hint = def.hint || (name === 'openrouter' ? 'sk-or-…' : 'AIza…');
      var card = document.createElement('section');
      card.className = 'n-provider-card' + (ready ? ' is-ready' : '');
      card.setAttribute('data-provider', name);
      card.innerHTML =
        '<div class="n-provider-head"><span class="n-provider-name"></span><span class="n-provider-state"></span></div>' +
        '<p class="n-provider-tag"></p>' +
        '<div class="n-provider-row"><input type="password" class="n-key-input" autocomplete="off" spellcheck="false">' +
        '<button type="button" class="n-btn" data-action="verify">Verify &amp; save</button></div>' +
        '<p class="n-provider-msg" role="status" aria-live="polite"></p>' +
        '<div class="n-provider-row"><label>Model</label><select class="n-model-select"></select>' +
        '<button type="button" class="n-btn" data-action="refresh">Refresh</button></div>' +
        '<div class="n-provider-links">' +
        '<button type="button" data-action="use">Use this provider</button>' +
        '<button type="button" data-action="remove" hidden>Forget saved key</button></div>';

      var keyInput = card.querySelector('.n-key-input');
      var msg = card.querySelector('.n-provider-msg');
      var select = card.querySelector('.n-model-select');
      var verifyBtn = card.querySelector('[data-action="verify"]');
      var refreshBtn = card.querySelector('[data-action="refresh"]');
      var useBtn = card.querySelector('[data-action="use"]');
      var removeBtn = card.querySelector('[data-action="remove"]');

      card.querySelector('.n-provider-name').textContent = label;
      card.querySelector('.n-provider-state').textContent = ready
        ? 'Connected · ••' + (entry.hint || String(entry.key).slice(-4)) + ' · this browser only'
        : 'Not connected';
      card.querySelector('.n-provider-tag').textContent = def.tag ||
        (name === 'openrouter' ? 'unified gateway · browser → openrouter.ai' : 'gemini · browser → googleapis.com');
      card.querySelector('.n-provider-row label').setAttribute('for', 'n-model-' + name);
      select.id = 'n-model-' + name;
      keyInput.setAttribute('aria-label', 'API key for ' + label);
      keyInput.placeholder = hint;
      removeBtn.hidden = !ready;
      providerCards.appendChild(card);
      loadModels(name, select, msg);

      verifyBtn.addEventListener('click', function () {
        var key = keyInput.value.trim();
        if (!key) {
          setStatus(msg, 'Paste a ' + label + ' key first.', 'error');
          keyInput.focus();
          return;
        }
        if (!engine || typeof engine.verifyKey !== 'function') {
          setStatus(msg, 'Provider verification is unavailable on this page.', 'error');
          return;
        }
        verifyBtn.disabled = true;
        setStatus(msg, 'Verifying with ' + label + '…', '');
        Promise.resolve().then(function () { return engine.verifyKey(name, key); }).then(function (ok) {
          verifyBtn.disabled = false;
          if (!ok) {
            setStatus(msg, 'That key was rejected. Check it and try again.', 'error');
            return;
          }
          var next = {};
          var currentProviders = getProvidersSafe();
          Object.keys(currentProviders).forEach(function (keyName) { next[keyName] = currentProviders[keyName]; });
          var prior = next[name] || {};
          next[name] = { key: key, hint: key.slice(-4), model: prior.model || modelFor(name) };
          saveSettingsSafe({ providers: next });
          keyInput.value = '';
          setStatus(msg, 'Saved in this browser only.', 'ok');
          renderProviderCards();
          syncChips();
          updateUsage();
        }).catch(function (err) {
          verifyBtn.disabled = false;
          setStatus(msg, 'Could not reach ' + label + ' (' + shortError(err) + ').', 'error');
        });
      });

      select.addEventListener('change', function () {
        var id = select.value;
        if (!id) return;
        var nextProviders = {};
        var currentProviders = getProvidersSafe();
        Object.keys(currentProviders).forEach(function (keyName) { nextProviders[keyName] = currentProviders[keyName]; });
        var prior = nextProviders[name] || {};
        prior.model = id;
        nextProviders[name] = prior;

        var settings = getSettingsSafe();
        var oldModels = (settings.providerConfig && settings.providerConfig.models) || {};
        var modelsMap = {};
        Object.keys(oldModels).forEach(function (keyName) { modelsMap[keyName] = oldModels[keyName]; });
        modelsMap[name] = id;

        saveSettingsSafe({ providers: nextProviders, providerConfig: { models: modelsMap } });
        setStatus(msg, 'Model pinned: ' + id, 'ok');
        syncChips();
      });

      refreshBtn.addEventListener('click', function () { loadModels(name, select, msg); });

      useBtn.addEventListener('click', function () {
        saveSettingsSafe({ providerConfig: { preferred: name } });
        setSettingsStatus(label + ' is now the preferred provider.', 'ok');
        syncChips();
      });

      removeBtn.addEventListener('click', function () {
        var next = {};
        var currentProviders = getProvidersSafe();
        Object.keys(currentProviders).forEach(function (keyName) {
          if (keyName !== name) next[keyName] = currentProviders[keyName];
        });
        saveSettingsSafe({ providers: next });
        setStatus(msg, 'Saved key forgotten.', 'ok');
        renderProviderCards();
        syncChips();
      });
    });

    var settings = getSettingsSafe();
    preferredSelect.value = (settings.providerConfig && settings.providerConfig.preferred) || 'auto';
    syncChips();
  }

  preferredSelect.addEventListener('change', function () {
    saveSettingsSafe({ providerConfig: { preferred: preferredSelect.value } });
    setSettingsStatus('Preferred provider saved in this browser.', 'ok');
    syncChips();
  });

  /* ---------------------------- general pane ---------------------------- */

  function hydrateGeneral() {
    var ui = getSettingsSafe().ui || {};
    if (document.activeElement !== instructionsEl) instructionsEl.value = ui.instructions || '';
    instructionsMeta.textContent = instructionsEl.value.length + ' characters';
    var font = ui.font === 'serif' ? 'serif' : 'body';
    document.body.setAttribute('data-n-font', font);
    Array.prototype.forEach.call(fontSeg.querySelectorAll('button'), function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-font') === font));
    });
  }

  instructionsEl.addEventListener('input', function () {
    instructionsMeta.textContent = instructionsEl.value.length + ' characters';
  });

  saveInstructions.addEventListener('click', function () {
    var value = instructionsEl.value.trim();
    saveSettingsSafe({ ui: { instructions: value } });
    instructionsMeta.textContent = value.length + ' characters · saved';
    generalStatus.textContent = 'Saved. This setting is shared with /app.';
    generalStatus.className = 'n-settings-status is-ok';
  });

  Array.prototype.forEach.call(fontSeg.querySelectorAll('button'), function (button) {
    button.addEventListener('click', function () {
      var font = button.getAttribute('data-font') === 'serif' ? 'serif' : 'body';
      document.body.setAttribute('data-n-font', font);
      Array.prototype.forEach.call(fontSeg.querySelectorAll('button'), function (other) {
        other.setAttribute('aria-pressed', String(other === button));
      });
      saveSettingsSafe({ ui: { font: font } });
    });
  });

  /* ---------------------------- in-page notes --------------------------- */

  artifactsAll.addEventListener('click', function () {
    var expanded = artifactsAll.getAttribute('aria-expanded') !== 'true';
    artifactsAll.setAttribute('aria-expanded', String(expanded));
    artifactsAll.textContent = expanded ? 'Show less' : 'View all';
    artifactCards.forEach(function (card) {
      if (card.getAttribute('data-extra') === 'true') card.hidden = !expanded;
    });
  });

  artifactCards.forEach(function (card) {
    card.addEventListener('click', function () {
      showInfo(card.getAttribute('data-title'), 'Artifact preview. Open the Keel app for the full document.', '/app');
    });
  });

  /* ------------------------------ composer ------------------------------ */

  function showError(message, withAction) {
    errorText.textContent = message;
    errorAction.hidden = !withAction;
    errorEl.hidden = false;
  }

  function hideError() {
    errorEl.hidden = true;
    errorAction.hidden = true;
  }

  errorAction.addEventListener('click', function () { openDialog('providers'); });

  function renderAttachments() {
    attachmentsEl.textContent = '';
    attached.forEach(function (file, index) {
      var name = file && file.name ? file.name : 'file';
      var isImage = !!(file && file.kind === 'image');
      var chip = document.createElement('span');
      chip.className = 'n-chip';
      chip.innerHTML = '<svg class="n-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#n-' +
        (isImage ? 'starburst' : 'doc') + '"/></svg>';
      var label = document.createElement('span');
      label.className = 'n-chip-name';
      label.textContent = name;
      label.title = name;
      var size = document.createElement('span');
      size.className = 'n-chip-size';
      size.textContent = formatSize(file && file.bytes);
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'n-chip-remove';
      remove.setAttribute('aria-label', 'Remove ' + name);
      remove.textContent = '\u00d7';
      remove.addEventListener('click', function () {
        attached.splice(index, 1);
        renderAttachments();
      });
      chip.appendChild(label);
      chip.appendChild(size);
      chip.appendChild(remove);
      attachmentsEl.appendChild(chip);
    });
    attachmentsEl.hidden = attached.length === 0;
  }

  attachBtn.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', function () {
    var list = fileInput.files ? Array.prototype.slice.call(fileInput.files) : [];
    fileInput.value = '';
    if (!list.length) return;
    var engine = api();
    if (!engine || typeof engine.attachFiles !== 'function') {
      showError('Attachments are unavailable on this page.', false);
      return;
    }
    var incoming = list;
    if (attached.length + incoming.length > 8) {
      showInfo('Attachments', 'Up to 8 files can be attached at a time.', null);
      incoming = incoming.slice(0, Math.max(0, 8 - attached.length));
      if (!incoming.length) return;
    }
    Promise.resolve().then(function () { return engine.attachFiles(incoming); }).then(function (result) {
      var files = (result && result.files) || [];
      attached = attached.concat(files).slice(0, 8);
      renderAttachments();
      var skipped = (result && result.skipped) || [];
      if (skipped.length) {
        showInfo('Some files were skipped', skipped.length + ' file(s) could not be read. Text files, images and .zip archives work best.', null);
      }
      if (files.length) hideError();
    }).catch(function (err) {
      showError('Could not read those files: ' + shortError(err), false);
    });
  });

  function setStreaming(on) {
    streaming = on;
    sendBtn.hidden = on;
    stopBtn.hidden = !on;
    attachBtn.disabled = on;
    input.readOnly = on;
  }

  function appendUserBubble(text, count) {
    var message = document.createElement('div');
    message.className = 'n-msg n-msg-user';
    message.textContent = text + (count ? '\n(' + count + ' attachment' + (count === 1 ? '' : 's') + ')' : '');
    conversation.appendChild(message);
  }

  function appendKeelBubble(metaText) {
    var message = document.createElement('div');
    message.className = 'n-msg n-msg-keel is-streaming';
    var meta = document.createElement('span');
    meta.className = 'n-msg-meta';
    meta.textContent = metaText;
    var body = document.createElement('span');
    body.className = 'n-msg-body';
    message.appendChild(meta);
    message.appendChild(body);
    conversation.appendChild(message);
    return { el: message, meta: meta, body: body };
  }

  function formatUsage(usage) {
    if (!usage) return 'done';
    var inputTokens = usage.prompt_tokens || usage.promptTokens || 0;
    var outputTokens = usage.completion_tokens || usage.completionTokens || 0;
    if (!inputTokens && !outputTokens) return 'done';
    return inputTokens + ' in · ' + outputTokens + ' out';
  }

  function updateUsage() {
    var usage = { prompts: 0, replies: 0, tokens: 0 };
    try {
      var engine = api();
      if (engine && engine.usage) usage = engine.usage() || usage;
    } catch (error) { /* keep zeroed counters */ }
    usageEl.textContent = (usage.prompts || 0) + ' prompts · ' + (usage.tokens || 0) + ' tokens';
  }

  function sendMessage() {
    if (streaming) return;
    var raw = (input.value || '').trim();
    var files = attached.slice();
    if (!raw && !files.length) return;

    var engine = api();
    var name = activeProvider();
    if (!engine || typeof engine.send !== 'function' || !name) {
      showError('No provider is connected. Add an OpenRouter or Google AI Studio key in Settings — keys stay in this browser and go only to that provider.', true);
      return;
    }
    hideError();

    var display = raw || '(attached files)';
    var wire = raw;
    try {
      if (typeof engine.buildPrompt === 'function') {
        var built = engine.buildPrompt(raw, files);
        if (built && String(built).trim()) wire = String(built);
      }
    } catch (error) { /* fall back to the plain prompt */ }

    var images = [];
    files.forEach(function (file) {
      if (file && file.kind === 'image' && file.data) {
        var mime = file.mime || 'image/png';
        images.push({ mime: mime, data: file.data, url: 'data:' + mime + ';base64,' + file.data });
      }
    });

    appendUserBubble(display, files.length);
    saveRecent(display);
    input.value = '';
    autoResize();
    attached = [];
    renderAttachments();
    scrollConversation();

    chatHistory.push({ role: 'user', content: String(wire) });

    var model = modelFor(name);
    var label = providerLabel(name);
    var bubble = appendKeelBubble(label + ' · ' + (model || 'default model') + ' · streaming');
    var full = '';
    var settings = getSettingsSafe();
    var instructions = (settings.ui && settings.ui.instructions) || '';

    cancelled = false;
    controller = typeof AbortController === 'function' ? new AbortController() : null;
    setStreaming(true);

    function finish(usage) {
      bubble.el.classList.remove('is-streaming');
      if (!bubble.body.textContent.trim()) bubble.body.textContent = '(empty reply)';
      bubble.meta.textContent = label + ' · ' + (model || 'default model') + ' · ' + formatUsage(usage);
      chatHistory.push({ role: 'assistant', content: bubble.body.textContent });
      setStreaming(false);
      updateUsage();
      scrollConversation();
    }

    function fail(err) {
      bubble.el.classList.remove('is-streaming');
      var partial = bubble.body.textContent.trim();
      if (partial) {
        bubble.meta.textContent = label + ' · ' + (model || 'default model') + ' · stopped early';
        chatHistory.push({ role: 'assistant', content: bubble.body.textContent });
      } else {
        bubble.el.hidden = true;
      }
      setStreaming(false);
      var message = shortError(err);
      if (/no-provider/i.test(message) || /no provider/i.test(message)) {
        showError('No provider key found. Add one in Settings → Providers — it stays in this browser.', true);
      } else {
        showError('Keel could not reach ' + label + ' (' + message + '). Check the key, the model and your connection in Settings.', true);
      }
      updateUsage();
    }

    var options = {
      messages: chatHistory.slice(),
      provider: name,
      model: model,
      instructions: instructions,
      images: images,
      onDelta: function (delta, fullText) {
        if (cancelled) return;
        if (typeof fullText === 'string' && fullText.length >= full.length) full = fullText;
        else full += (delta || '');
        bubble.body.textContent = full;
        scrollConversation();
      },
      onDone: function (result) {
        if (cancelled) return;
        finish(result && result.usage);
      },
      onError: function (err) {
        if (cancelled) return;
        fail(err);
      }
    };
    if (controller) options.signal = controller.signal;

    try {
      var promise = engine.send(options);
      if (promise && typeof promise.catch === 'function') {
        promise.catch(function (err) { if (!cancelled) fail(err); });
      }
    } catch (err) {
      fail(err);
    }
  }

  sendBtn.addEventListener('click', sendMessage);

  input.addEventListener('input', autoResize);
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });

  stopBtn.addEventListener('click', function () {
    cancelled = true;
    if (controller && typeof controller.abort === 'function') controller.abort();
    var active = conversation.querySelector('.n-msg.is-streaming');
    if (active) {
      active.classList.remove('is-streaming');
      var body = active.querySelector('.n-msg-body');
      var meta = active.querySelector('.n-msg-meta');
      var text = body ? body.textContent.trim() : '';
      if (text) {
        if (meta) meta.textContent = 'Stopped by you';
        chatHistory.push({ role: 'assistant', content: body.textContent });
      } else {
        active.hidden = true;
      }
    }
    setStreaming(false);
    showInfo('Reply stopped', 'You can send another message whenever you are ready.', null);
    input.focus();
  });

  clearBtn.addEventListener('click', function () {
    if (controller && typeof controller.abort === 'function') controller.abort();
    cancelled = true;
    chatHistory = [];
    conversation.textContent = '';
    hideError();
    setStreaming(false);
    input.value = '';
    autoResize();
    attached = [];
    renderAttachments();
    input.focus();
  });

  /* ------------------------------- voice -------------------------------- */

  function hideVoice() {
    voiceSource = null;
    voiceStatus.hidden = true;
    micBtn.setAttribute('aria-pressed', 'false');
    voiceWave.setAttribute('aria-pressed', 'false');
    voiceChevron.setAttribute('aria-expanded', 'false');
  }

  function toggleVoice(source, message) {
    if (voiceSource === source) {
      hideVoice();
      return;
    }
    voiceSource = source;
    voiceStatusText.textContent = message;
    voiceStatus.hidden = false;
    micBtn.setAttribute('aria-pressed', String(source === 'mic'));
    voiceWave.setAttribute('aria-pressed', String(source === 'wave'));
    voiceChevron.setAttribute('aria-expanded', String(source === 'chevron'));
  }

  micBtn.addEventListener('click', function () {
    toggleVoice('mic', 'Microphone is a preview here. Keel voice input lives in the downloadable app.');
  });
  voiceChevron.addEventListener('click', function () {
    toggleVoice('chevron', 'Voice options live in the downloadable Keel app.');
  });
  voiceWave.addEventListener('click', function () {
    toggleVoice('wave', 'Voice mode is a preview here. Get the full experience in the Keel app.');
  });
  voiceStop.addEventListener('click', function () {
    hideVoice();
    input.focus();
  });

  /* ---------------------------- global escape --------------------------- */

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    if (window.KeelSearchPalette && typeof window.KeelSearchPalette.isOpen === 'function' && window.KeelSearchPalette.isOpen()) return;

    if (!dialog.hidden) {
      closeDialog();
      return;
    }

    var openPair = null;
    menuPairs.forEach(function (pair) {
      if (!pair.menu.hidden) openPair = pair;
    });
    if (openPair) {
      closeMenus();
      openPair.btn.focus();
      return;
    }

    if (!searchWrap.hidden) {
      closeRecentsFilter(true);
      return;
    }

    if (isMobile() && app.classList.contains('sidebar-open')) {
      setSidebar(false);
      sidebarToggle.focus();
      return;
    }

    if (!voiceStatus.hidden) {
      hideVoice();
      input.focus();
    }
  });

  /* ------------------------------- init --------------------------------- */

  loadRecents();
  renderRecents();
  syncChips();
  updateUsage();
  hydrateGeneral();
  autoResize();
})();

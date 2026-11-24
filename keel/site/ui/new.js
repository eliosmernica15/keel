/* Keel — /new page behaviour. Dependency-free, no network calls. */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }

  var app = $('n-app');
  var sidebarToggle = $('n-sidebar-toggle');
  var collapse = $('n-collapse');
  var scrim = $('n-scrim');
  var navNew = $('n-nav-new');
  var navSearch = $('n-nav-search');
  var recentsToggle = $('n-recents-toggle');
  var recentsList = $('n-recents-list');
  var recentsEmpty = $('n-recents-empty');
  var recentsViewAll = $('n-recents-view-all');
  var searchWrap = $('n-recents-search-wrap');
  var searchInput = $('n-recents-search');
  var searchClose = $('n-recents-search-close');
  var accountBtn = $('n-account');
  var accountMenu = $('n-account-menu');

  var upgradeBtn = $('n-upgrade');
  var helpBtn = $('n-help');
  var conversation = $('n-conversation');
  var input = $('n-input');
  var attachBtn = $('n-attach');
  var micBtn = $('n-mic');
  var voiceChevron = $('n-voice-chevron');
  var voiceWave = $('n-voice-wave');
  var voiceStatus = $('n-voice-status');
  var voiceStatusText = $('n-voice-status-text');
  var voiceStop = $('n-voice-stop');

  var projectBtn = $('n-project-btn');
  var projectLabel = $('n-project-label');
  var projectMenu = $('n-project-menu');
  var modelBtn = $('n-model-btn');
  var modelName = $('n-model-name');
  var modelWeight = $('n-model-weight');
  var modelMenu = $('n-model-menu');
  var autoBtn = $('n-auto-btn');
  var autoLabel = $('n-auto-label');
  var autoMenu = $('n-auto-menu');

  var artifactsAll = $('n-artifacts-all');
  var artifactCards = Array.prototype.slice.call(document.querySelectorAll('.n-artifact-card'));

  var infoPanel = $('n-info-panel');
  var infoTitle = $('n-info-title');
  var infoText = $('n-info-text');
  var infoLink = $('n-info-link');
  var infoClose = $('n-info-close');
  var infoTimer = null;

  var dialog = $('n-dialog');
  var dialogCard = dialog.querySelector('.n-modal-card');
  var dialogClose = $('n-dialog-close');
  var dialogBackdrop = $('n-dialog-backdrop');
  var dialogTitle = $('n-dialog-title');
  var dialogViews = Array.prototype.slice.call(dialog.querySelectorAll('.n-dialog-view'));
  var lastFocused = null;

  var pendingReplies = [];
  var voiceSource = null;
  var allRecents = true;

  /* ------------------------------ helpers ------------------------------ */

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

  /* ------------------------------ sidebar ------------------------------ */

  var mobileQuery = window.matchMedia('(max-width: 860px)');

  function isSidebarOpen() {
    if (mobileQuery.matches) return app.classList.contains('sidebar-open');
    return !app.classList.contains('sidebar-collapsed');
  }

  function syncSidebarToggles() {
    var open = isSidebarOpen();
    sidebarToggle.setAttribute('aria-expanded', String(open));
    collapse.setAttribute('aria-expanded', String(open));
    collapse.setAttribute('aria-label', open ? 'Collapse sidebar' : 'Expand sidebar');
  }

  function setSidebar(open) {
    if (mobileQuery.matches) {
      app.classList.remove('sidebar-collapsed');
      app.classList.toggle('sidebar-open', open);
    } else {
      app.classList.remove('sidebar-open');
      app.classList.toggle('sidebar-collapsed', !open);
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

  if (mobileQuery.addEventListener) {
    mobileQuery.addEventListener('change', onViewportChange);
  } else if (mobileQuery.addListener) {
    mobileQuery.addListener(onViewportChange);
  }
  syncSidebarToggles();

  /* ------------------------------ recents ------------------------------ */

  var recentItems = Array.prototype.slice.call(recentsList.querySelectorAll('li'));

  function applyRecents() {
    var query = searchInput.value.trim().toLowerCase();
    var visible = 0;
    recentItems.forEach(function (li) {
      var button = li.querySelector('.n-recent');
      var title = (button.getAttribute('data-title') || '').toLowerCase();
      var isExtra = li.getAttribute('data-extra') === 'true';
      var show = (!query || title.indexOf(query) !== -1) && (allRecents || !isExtra);
      li.hidden = !show;
      if (show) visible += 1;
    });
    recentsEmpty.hidden = !(query && visible === 0);
  }

  function openRecentsSearch() {
    searchWrap.hidden = false;
    navSearch.setAttribute('aria-expanded', 'true');
    searchInput.focus();
  }

  function closeRecentsSearch(restoreFocus) {
    searchWrap.hidden = true;
    navSearch.setAttribute('aria-expanded', 'false');
    searchInput.value = '';
    applyRecents();
    if (restoreFocus) navSearch.focus();
  }

  navSearch.addEventListener('click', function () {
    if (searchWrap.hidden) openRecentsSearch(); else closeRecentsSearch(true);
  });
  searchClose.addEventListener('click', function () { closeRecentsSearch(true); });
  searchInput.addEventListener('input', applyRecents);

  recentsToggle.addEventListener('click', function () {
    var willShow = recentsList.hidden;
    recentsList.hidden = !willShow;
    recentsViewAll.hidden = !willShow;
    if (!willShow) closeRecentsSearch(false);
    recentsToggle.setAttribute('aria-expanded', String(willShow));
  });

  recentsViewAll.addEventListener('click', function () {
    allRecents = !allRecents;
    recentsViewAll.setAttribute('aria-expanded', String(allRecents));
    recentsViewAll.setAttribute('aria-label', allRecents ? 'Show fewer recent chats' : 'Show all recent chats');
    applyRecents();
  });

  recentItems.forEach(function (li) {
    var button = li.querySelector('.n-recent');
    button.addEventListener('click', function () {
      var title = button.getAttribute('data-title') || '';
      input.value = title;
      autoResize();
      showInfo('Recent chat', 'Loaded "' + title + '" into the composer. This static mirror does not reopen chats.', null);
      input.focus();
      input.setSelectionRange(title.length, title.length);
    });
  });

  /* --------------------------- in-page notes --------------------------- */

  var panelMessages = {
    projects: [
      'Projects',
      'Projects keep related chats, files and artifacts together. Manage them in the Keel app.',
      '/app'
    ],
    artifacts: [
      'Artifacts',
      'Artifacts are the documents and designs Keel creates for you. Browse the full set in the app.',
      '/app'
    ],
    plugins: [
      'Plugins',
      'Plugins extend Keel with the tools you already use. Add them from the local Keel app.',
      '/download'
    ]
  };

  Array.prototype.slice.call(document.querySelectorAll('[data-info-panel]')).forEach(function (button) {
    button.addEventListener('click', function () {
      var message = panelMessages[button.getAttribute('data-info-panel')];
      if (message) showInfo(message[0], message[1], message[2]);
    });
  });

  attachBtn.addEventListener('click', function () {
    showInfo('Attach a file', 'File upload belongs to the local Keel desktop app. This web mirror keeps prompts in your browser.', '/download');
  });

  artifactCards.forEach(function (card) {
    card.addEventListener('click', function () {
      showInfo(card.getAttribute('data-title'), 'This artifact is a preview in the static Keel mirror. Open Keel to view the full document.', '/app');
    });
  });

  artifactsAll.addEventListener('click', function () {
    var expanded = artifactsAll.getAttribute('aria-expanded') !== 'true';
    artifactsAll.setAttribute('aria-expanded', String(expanded));
    artifactsAll.textContent = expanded ? 'Show less' : 'View all';
    artifactCards.forEach(function (card) {
      if (card.getAttribute('data-extra') === 'true') card.hidden = !expanded;
    });
  });

  /* ------------------------------ composer ------------------------------ */

  navNew.addEventListener('click', function () {
    input.value = '';
    autoResize();
    conversation.textContent = '';
    pendingReplies.forEach(function (timer) { window.clearTimeout(timer); });
    pendingReplies = [];
    hideVoice();
    showInfo('New chat', 'A fresh Keel chat is ready. Type below and press Enter to send.', null);
    input.focus();
  });

  input.addEventListener('input', autoResize);
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });

  function sendMessage() {
    var text = input.value.trim();
    if (!text) return;

    var userMessage = document.createElement('div');
    userMessage.className = 'n-msg n-msg-user';
    userMessage.textContent = text;
    conversation.appendChild(userMessage);

    input.value = '';
    autoResize();
    conversation.scrollTop = conversation.scrollHeight;

    var timer = window.setTimeout(function () {
      var reply = document.createElement('div');
      reply.className = 'n-msg n-msg-keel';
      reply.textContent = 'This is a static Keel mirror — your message stays in this browser. Open Keel to keep the conversation going.';
      conversation.appendChild(reply);
      conversation.scrollTop = conversation.scrollHeight;
    }, 450);
    pendingReplies.push(timer);
  }

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
    toggleVoice('mic', 'Microphone is on (demo) — Keel is listening.');
  });
  voiceChevron.addEventListener('click', function () {
    toggleVoice('chevron', 'Voice options: dictation and voice mode live in the Keel app.');
  });
  voiceWave.addEventListener('click', function () {
    toggleVoice('wave', 'Voice mode is on (demo) — Keel is ready to listen.');
  });
  voiceStop.addEventListener('click', function () {
    hideVoice();
    input.focus();
  });

  /* ------------------------------- menus -------------------------------- */

  var menuPairs = [
    { btn: projectBtn, menu: projectMenu },
    { btn: modelBtn, menu: modelMenu },
    { btn: autoBtn, menu: autoMenu },
    { btn: accountBtn, menu: accountMenu }
  ];

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

  function selectRadio(menu, chosen) {
    getMenuItems(menu).forEach(function (item) {
      item.setAttribute('aria-checked', String(item === chosen));
    });
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

  projectMenu.addEventListener('click', function (event) {
    var item = event.target.closest('[role="menuitemradio"]');
    if (!item || !projectMenu.contains(item)) return;
    selectRadio(projectMenu, item);
    var name = item.textContent.trim();
    projectLabel.textContent = name === 'No project' ? 'Project' : 'Project: ' + name;
    closeMenus();
    projectBtn.focus();
  });

  modelMenu.addEventListener('click', function (event) {
    var item = event.target.closest('[role="menuitemradio"]');
    if (!item || !modelMenu.contains(item)) return;
    selectRadio(modelMenu, item);
    modelName.textContent = item.getAttribute('data-name');
    modelWeight.textContent = item.getAttribute('data-weight');
    closeMenus();
    modelBtn.focus();
  });

  autoMenu.addEventListener('click', function (event) {
    var item = event.target.closest('[role="menuitemradio"]');
    if (!item || !autoMenu.contains(item)) return;
    selectRadio(autoMenu, item);
    autoLabel.textContent = item.textContent.trim();
    closeMenus();
    autoBtn.focus();
  });

  accountMenu.addEventListener('click', function () { closeMenus(); });

  document.addEventListener('click', function (event) {
    if (!event.target.closest('.n-option-wrap') && !event.target.closest('#n-account-wrap')) closeMenus();
  });

  /* ------------------------------- dialog ------------------------------- */

  var dialogTitles = { plans: 'Keel plans', help: 'Help with Keel' };

  function openDialog(view) {
    lastFocused = document.activeElement;
    dialogTitle.textContent = dialogTitles[view] || 'Keel';
    dialogViews.forEach(function (section) {
      section.hidden = section.getAttribute('data-view') !== view;
    });
    dialog.hidden = false;
    dialogClose.focus();
  }

  function closeDialog() {
    dialog.hidden = true;
    dialogViews.forEach(function (section) { section.hidden = true; });
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
  }

  upgradeBtn.addEventListener('click', function () { openDialog('plans'); });
  helpBtn.addEventListener('click', function () { openDialog('help'); });
  dialogClose.addEventListener('click', closeDialog);
  dialogBackdrop.addEventListener('click', closeDialog);

  dialogCard.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = Array.prototype.slice.call(dialogCard.querySelectorAll('a[href], button:not([disabled])'))
      .filter(function (element) { return element.offsetParent !== null; });
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

  /* ---------------------------- global escape --------------------------- */

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;

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

    if (!searchWrap.hidden && document.activeElement === searchInput) {
      closeRecentsSearch(true);
      return;
    }

    if (!voiceStatus.hidden) {
      hideVoice();
      input.focus();
    }
  });

  autoResize();
})();

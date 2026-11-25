/* Keel — /projects page behaviour. Dependency-free, no network calls. */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function $$(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  var STORAGE_KEY = 'keel.projects.v1';

  var app = $('pr-app');
  var sidebarToggle = $('pr-sidebar-toggle');
  var collapse = $('pr-collapse');
  var scrim = $('pr-scrim');
  var navNew = $('pr-nav-new');
  var navSearch = $('pr-nav-search');
  var navProjects = $('pr-nav-projects');
  var recentsToggle = $('pr-recents-toggle');
  var recentsList = $('pr-recents-list');
  var recentsEmpty = $('pr-recents-empty');
  var recentsViewAll = $('pr-recents-view-all');
  var recentsSearchWrap = $('pr-recents-search-wrap');
  var recentsSearch = $('pr-recents-search');
  var recentsSearchClose = $('pr-recents-search-close');
  var accountBtn = $('pr-account');
  var accountMenu = $('pr-account-menu');
  var helpBtn = $('pr-help');

  var searchBtn = $('pr-search-btn');
  var searchRow = $('pr-search-row');
  var projectSearch = $('pr-project-search');
  var searchClear = $('pr-search-clear');
  var sortBtn = $('pr-sort-btn');
  var sortMenu = $('pr-sort-menu');
  var newBtn = $('pr-new-btn');
  var emptyNewBtn = $('pr-empty-new');
  var emptyState = $('pr-empty');
  var gridSection = $('pr-grid-section');
  var grid = $('pr-grid');
  var noResults = $('pr-no-results');
  var clearSearchBtn = $('pr-clear-search');

  var detailLayer = $('pr-detail-layer');
  var detailBackdrop = $('pr-detail-backdrop');
  var detailClose = $('pr-detail-close');
  var detailName = $('pr-detail-name');
  var detailDesc = $('pr-detail-desc');
  var detailDate = $('pr-detail-date');
  var sessionsList = $('pr-sessions');
  var sessionsEmpty = $('pr-sessions-empty');
  var addSessionBtn = $('pr-add-session');

  var infoPanel = $('pr-info-panel');
  var infoTitle = $('pr-info-title');
  var infoText = $('pr-info-text');
  var infoLink = $('pr-info-link');
  var infoClose = $('pr-info-close');
  var infoTimer = null;

  var dialog = $('pr-dialog');
  var dialogCard = $('pr-dialog-card');
  var dialogClose = $('pr-dialog-close');
  var dialogBackdrop = $('pr-dialog-backdrop');
  var dialogTitle = $('pr-dialog-title');
  var dialogViews = $$('.pr-dialog-view', dialog);
  var dialogCancel = $('pr-dialog-cancel');
  var dialogConfirm = $('pr-dialog-confirm');
  var createName = $('pr-field-name');
  var createDesc = $('pr-field-desc');
  var createError = $('pr-field-error');
  var addMaterials = $('pr-add-materials');
  var materialsNote = $('pr-materials-note');
  var renameName = $('pr-rename-name');
  var renameError = $('pr-rename-error');
  var deleteText = $('pr-delete-text');

  /* ------------------------------ state ------------------------------ */

  var projects = [];
  var sortMode = 'newest';
  var activeProjectId = null;
  var dialogState = null;
  var lastFocused = null;
  var openMenu = null;
  var allRecents = true;

  function uid() {
    return 'p-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function normalizeProject(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var name = typeof raw.name === 'string' ? raw.name.trim() : '';
    if (!name) return null;
    var sessions = Array.isArray(raw.sessions)
      ? raw.sessions.filter(function (s) { return typeof s === 'string'; })
      : [];
    return {
      id: typeof raw.id === 'string' && raw.id ? raw.id : uid(),
      name: name.slice(0, 80),
      description: typeof raw.description === 'string' ? raw.description.slice(0, 300) : '',
      createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : new Date().toISOString(),
      sessions: sessions
    };
  }

  function loadProjects() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.map(normalizeProject).filter(function (p) { return !!p; });
    } catch (error) {
      return [];
    }
  }

  function saveProjects() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
    } catch (error) {
      /* Storage may be unavailable in a restricted context; keep in-memory state. */
    }
  }

  function findProject(id) {
    for (var i = 0; i < projects.length; i += 1) {
      if (projects[i].id === id) return projects[i];
    }
    return null;
  }

  function formatDate(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) return 'Recently';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  /* ------------------------------ notes ------------------------------ */

  function hideInfo() {
    if (infoTimer !== null) {
      window.clearTimeout(infoTimer);
      infoTimer = null;
    }
    infoPanel.hidden = true;
  }

  function showInfo(title, text, href, linkText) {
    infoTitle.textContent = title;
    infoText.textContent = text;
    if (href) {
      infoLink.href = href;
      infoLink.textContent = linkText || 'Open in Keel';
      infoLink.hidden = false;
    } else {
      infoLink.hidden = true;
    }
    infoPanel.hidden = false;
    if (infoTimer !== null) window.clearTimeout(infoTimer);
    infoTimer = window.setTimeout(hideInfo, 12000);
  }

  infoClose.addEventListener('click', hideInfo);

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

  var recentItems = $$('li', recentsList);

  function applyRecents() {
    var query = recentsSearch.value.trim().toLowerCase();
    var visible = 0;
    recentItems.forEach(function (item) {
      var button = $('.pr-recent', item);
      if (!button) { item.hidden = true; return; }
      var title = (button.getAttribute('data-title') || '').toLowerCase();
      var isExtra = item.getAttribute('data-extra') === 'true';
      var show = (!query || title.indexOf(query) !== -1) && (allRecents || !isExtra);
      item.hidden = !show;
      if (show) visible += 1;
    });
    recentsEmpty.hidden = !(query && visible === 0);
  }

  function openRecentsSearch() {
    recentsSearchWrap.hidden = false;
    navSearch.setAttribute('aria-expanded', 'true');
    recentsSearch.focus();
  }

  function closeRecentsSearch(restoreFocus) {
    recentsSearchWrap.hidden = true;
    navSearch.setAttribute('aria-expanded', 'false');
    recentsSearch.value = '';
    applyRecents();
    if (restoreFocus) navSearch.focus();
  }

  function hasSharedPalette() {
    return !!(window.KeelSearchPalette && typeof window.KeelSearchPalette.open === 'function');
  }

  navSearch.addEventListener('click', function () {
    /* The shared palette auto-binds [data-search-trigger] and owns this click. */
    if (hasSharedPalette()) return;
    if (recentsSearchWrap.hidden) openRecentsSearch(); else closeRecentsSearch(true);
  });
  recentsSearchClose.addEventListener('click', function () { closeRecentsSearch(true); });
  recentsSearch.addEventListener('input', applyRecents);

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

  recentItems.forEach(function (item) {
    var button = $('.pr-recent', item);
    if (!button) return;
    button.addEventListener('click', function () {
      var title = button.getAttribute('data-title') || '';
      showInfo('Recent chat', 'This static mirror does not reopen chats. "' + title + '" is shown here for reference.', '/app');
    });
  });

  navNew.addEventListener('click', function () {
    showInfo('New chat', 'Start a fresh conversation in Keel.', '/new', 'Go to new chat');
  });
  navProjects.addEventListener('click', function () {
    showInfo('Projects', 'You are viewing your projects. Create one to keep related sessions together.', null);
  });

  var panelMessages = {
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
  $$('[data-info-panel]').forEach(function (button) {
    button.addEventListener('click', function () {
      var message = panelMessages[button.getAttribute('data-info-panel')];
      if (message) showInfo(message[0], message[1], message[2]);
    });
  });

  /* ------------------------------ menus ------------------------------ */

  function getMenuItems(menu) {
    return $$('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]', menu)
      .filter(function (item) { return !item.hidden && item.offsetParent !== null; });
  }

  function closeMenus() {
    if (!openMenu) return;
    openMenu.menu.hidden = true;
    openMenu.btn.setAttribute('aria-expanded', 'false');
    openMenu = null;
  }

  function onMenuKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      var pair = openMenu;
      closeMenus();
      if (pair) pair.btn.focus();
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    var items = getMenuItems(openMenu ? openMenu.menu : this);
    if (!items.length) return;
    var index = items.indexOf(document.activeElement);
    event.preventDefault();
    if (event.key === 'ArrowDown') items[(index + 1) % items.length].focus();
    else items[(index - 1 + items.length) % items.length].focus();
  }

  function bindMenu(button, menu) {
    button.addEventListener('click', function (event) {
      event.stopPropagation();
      var willOpen = !(openMenu && openMenu.menu === menu);
      closeMenus();
      if (!willOpen) {
        button.focus();
        return;
      }
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      openMenu = { btn: button, menu: menu };
      var items = getMenuItems(menu);
      if (items.length) items[0].focus();
    });
    menu.addEventListener('keydown', onMenuKeydown);
  }

  bindMenu(sortBtn, sortMenu);
  bindMenu(accountBtn, accountMenu);

  accountMenu.addEventListener('click', function () { closeMenus(); });

  document.addEventListener('click', function (event) {
    if (!openMenu) return;
    var target = event.target;
    if (openMenu.menu.contains(target) || target === openMenu.btn) return;
    closeMenus();
  });

  /* ------------------------------ sorting ------------------------------ */

  sortMenu.addEventListener('click', function (event) {
    var target = event.target;
    var item = target && target.closest ? target.closest('[data-sort]') : null;
    if (!item || !sortMenu.contains(item)) return;
    sortMode = item.getAttribute('data-sort');
    $$('[data-sort]', sortMenu).forEach(function (option) {
      option.setAttribute('aria-checked', String(option === item));
    });
    closeMenus();
    sortBtn.focus();
    render();
  });

  function sortedProjects() {
    var list = projects.slice();
    list.sort(function (a, b) {
      if (sortMode === 'name-asc') return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      if (sortMode === 'name-desc') return b.name.localeCompare(a.name, undefined, { sensitivity: 'base' });
      var delta = new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      if (sortMode === 'oldest') delta = -delta;
      return delta || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
    return list;
  }

  /* ------------------------------ cards ------------------------------ */

  function createCard(project) {
    var card = el('div', 'pr-card');
    card.setAttribute('data-id', project.id);

    var main = el('button', 'pr-card-main');
    main.type = 'button';
    main.setAttribute('aria-label', 'Open project ' + project.name);

    var icon = el('span', 'pr-card-icon');
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = '<svg class="pr-ico" viewBox="0 0 20 20" aria-hidden="true"><use href="#pr-layers"/></svg>';

    var text = el('span', 'pr-card-text');
    text.appendChild(el('span', 'pr-card-name', project.name));
    text.appendChild(el('span', 'pr-card-desc', project.description || 'No description yet.'));
    text.appendChild(el('span', 'pr-card-meta',
      'Created ' + formatDate(project.createdAt) + ' · ' + project.sessions.length +
      (project.sessions.length === 1 ? ' session' : ' sessions')));
    main.appendChild(icon);
    main.appendChild(text);
    main.addEventListener('click', function () { openDetail(project.id); });
    card.appendChild(main);

    var wrap = el('div', 'pr-wrap pr-card-wrap');
    var more = el('button', 'pr-icon-btn pr-card-more');
    more.type = 'button';
    more.setAttribute('aria-label', 'More options for ' + project.name);
    more.setAttribute('aria-haspopup', 'menu');
    more.setAttribute('aria-expanded', 'false');
    more.setAttribute('aria-controls', 'pr-card-menu-' + project.id);
    more.innerHTML = '<svg class="pr-ico" viewBox="0 0 20 20" aria-hidden="true"><use href="#pr-more"/></svg>';

    var menu = el('div', 'pr-menu pr-popover pr-menu-right');
    menu.id = 'pr-card-menu-' + project.id;
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', project.name + ' options');
    menu.hidden = true;

    [
      { action: 'rename', label: 'Rename' },
      { action: 'duplicate', label: 'Duplicate' },
      { action: 'delete', label: 'Delete' }
    ].forEach(function (item) {
      var button = el('button', null, item.label);
      button.type = 'button';
      button.setAttribute('role', 'menuitem');
      button.setAttribute('data-action', item.action);
      menu.appendChild(button);
    });

    menu.addEventListener('click', function (event) {
      var target = event.target;
      var item = target && target.closest ? target.closest('[data-action]') : null;
      if (!item || !menu.contains(item)) return;
      var current = findProject(project.id);
      if (!current) return;
      var action = item.getAttribute('data-action');
      closeMenus();
      if (action === 'rename') openRenameDialog(current);
      else if (action === 'duplicate') duplicateProject(current);
      else if (action === 'delete') openDeleteDialog(current);
    });

    bindMenu(more, menu);
    wrap.appendChild(more);
    wrap.appendChild(menu);
    card.appendChild(wrap);
    return card;
  }

  function applyFilter() {
    var query = projectSearch.value.trim().toLowerCase();
    var visible = 0;
    $$('.pr-card', grid).forEach(function (card) {
      var project = findProject(card.getAttribute('data-id'));
      var match = !!project && (!query ||
        project.name.toLowerCase().indexOf(query) !== -1 ||
        project.description.toLowerCase().indexOf(query) !== -1);
      card.hidden = !match;
      if (match) visible += 1;
    });
    noResults.hidden = !(query && visible === 0);
    searchClear.hidden = !query;
  }

  function render() {
    grid.textContent = '';
    sortedProjects().forEach(function (project) {
      grid.appendChild(createCard(project));
    });
    var hasProjects = projects.length > 0;
    emptyState.hidden = hasProjects;
    gridSection.hidden = !hasProjects;
    applyFilter();
  }

  /* ------------------------------ search ------------------------------ */

  function trySharedPalette() {
    var names = ['KeelSearchPalette', 'SearchPalette', 'keelSearchPalette', 'searchPalette'];
    for (var i = 0; i < names.length; i += 1) {
      var api = window[names[i]];
      if (!api || typeof api !== 'object') continue;
      var methods = ['open', 'show', 'toggle', 'openPalette'];
      for (var j = 0; j < methods.length; j += 1) {
        if (typeof api[methods[j]] === 'function') {
          try { api[methods[j]](searchBtn); } catch (error) { return false; }
          return true;
        }
      }
    }
    return false;
  }

  function toggleProjectSearch() {
    if (trySharedPalette()) return;

    var handled = false;
    try {
      handled = !document.dispatchEvent(new CustomEvent('keel:open-search', {
        bubbles: true,
        cancelable: true
      }));
    } catch (error) {
      handled = false;
    }
    if (handled) return;

    var willOpen = searchRow.hidden;
    searchRow.hidden = !willOpen;
    searchBtn.setAttribute('aria-expanded', String(willOpen));
    if (willOpen) {
      projectSearch.focus();
    } else {
      projectSearch.value = '';
      applyFilter();
    }
  }

  searchBtn.addEventListener('click', toggleProjectSearch);
  projectSearch.addEventListener('input', applyFilter);
  searchClear.addEventListener('click', function () {
    projectSearch.value = '';
    projectSearch.focus();
    applyFilter();
  });
  clearSearchBtn.addEventListener('click', function () {
    projectSearch.value = '';
    applyFilter();
    projectSearch.focus();
  });

  /* ------------------------------ dialog ------------------------------ */

  function setDialogView(view) {
    dialogViews.forEach(function (section) {
      section.hidden = section.getAttribute('data-view') !== view;
    });
  }

  function openDialog(state) {
    lastFocused = document.activeElement;
    dialogState = state;
    createError.hidden = true;
    renameError.hidden = true;
    dialogConfirm.hidden = false;
    dialogConfirm.removeAttribute('data-danger');
    dialogCancel.textContent = 'Cancel';

    if (state.mode === 'create') {
      dialogTitle.textContent = 'Create project';
      dialogConfirm.textContent = 'Create';
      createName.value = '';
      createDesc.value = '';
      setDialogView('create');
    } else if (state.mode === 'rename') {
      dialogTitle.textContent = 'Rename project';
      dialogConfirm.textContent = 'Save';
      renameName.value = state.project.name;
      setDialogView('rename');
    } else if (state.mode === 'delete') {
      dialogTitle.textContent = 'Delete project';
      dialogConfirm.textContent = 'Delete';
      dialogConfirm.setAttribute('data-danger', 'true');
      deleteText.textContent = 'Delete “' + state.project.name + '”? This cannot be undone.';
      setDialogView('delete');
    } else {
      dialogTitle.textContent = 'Help with Keel';
      dialogConfirm.hidden = true;
      dialogCancel.textContent = 'Close';
      setDialogView('help');
    }

    dialog.hidden = false;
    var focusTarget = state.mode === 'create' ? createName
      : state.mode === 'rename' ? renameName : dialogClose;
    focusTarget.focus();
  }

  function closeDialog() {
    dialog.hidden = true;
    setDialogView('');
    dialogState = null;
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
  }

  function openCreateDialog() { openDialog({ mode: 'create' }); }
  function openRenameDialog(project) { openDialog({ mode: 'rename', project: project }); }
  function openDeleteDialog(project) { openDialog({ mode: 'delete', project: project }); }

  newBtn.addEventListener('click', openCreateDialog);
  emptyNewBtn.addEventListener('click', openCreateDialog);
  helpBtn.addEventListener('click', function () { openDialog({ mode: 'help' }); });
  dialogClose.addEventListener('click', closeDialog);
  dialogBackdrop.addEventListener('click', closeDialog);
  dialogCancel.addEventListener('click', closeDialog);
  addMaterials.addEventListener('click', function () {
    materialsNote.textContent = 'File upload belongs to the local Keel desktop app. This page keeps project details in your browser.';
    showInfo('Add materials', 'Materials are attached to projects in the local Keel app.', '/download');
  });

  dialogConfirm.addEventListener('click', function () {
    if (!dialogState) return;
    var mode = dialogState.mode;

    if (mode === 'create') {
      var name = createName.value.trim();
      if (!name) {
        createError.hidden = false;
        createName.focus();
        return;
      }
      var project = {
        id: uid(),
        name: name.slice(0, 80),
        description: createDesc.value.trim().slice(0, 300),
        createdAt: new Date().toISOString(),
        sessions: []
      };
      projects.push(project);
      saveProjects();
      render();
      closeDialog();
      showInfo('Project created', '“' + project.name + '” is ready. Open it to see its details.', null);
      return;
    }

    if (mode === 'rename') {
      var nextName = renameName.value.trim();
      if (!nextName) {
        renameError.hidden = false;
        renameName.focus();
        return;
      }
      var target = findProject(dialogState.project.id);
      if (target) {
        target.name = nextName.slice(0, 80);
        saveProjects();
        render();
        if (activeProjectId === target.id) populateDetail(target);
        showInfo('Project renamed', 'The project is now called “' + target.name + '”.', null);
      }
      closeDialog();
      return;
    }

    if (mode === 'delete') {
      var id = dialogState.project.id;
      projects = projects.filter(function (p) { return p.id !== id; });
      saveProjects();
      render();
      if (activeProjectId === id) closeDetail();
      closeDialog();
      showInfo('Project deleted', 'The project was removed from this browser.', null);
    }
  });

  function duplicateProject(project) {
    var copy = {
      id: uid(),
      name: (project.name.slice(0, 76) + ' copy').slice(0, 80),
      description: project.description,
      createdAt: new Date().toISOString(),
      sessions: project.sessions.slice()
    };
    projects.push(copy);
    saveProjects();
    render();
    showInfo('Project duplicated', '“' + copy.name + '” was created.', null);
  }

  function trapFocus(container, event) {
    if (event.key !== 'Tab') return;
    var focusable = $$('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled])', container)
      .filter(function (node) { return node.offsetParent !== null; });
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
  }

  dialogCard.addEventListener('keydown', function (event) { trapFocus(dialogCard, event); });
  createName.addEventListener('input', function () { createError.hidden = true; });
  renameName.addEventListener('input', function () { renameError.hidden = true; });
  createName.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') { event.preventDefault(); dialogConfirm.click(); }
  });
  renameName.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') { event.preventDefault(); dialogConfirm.click(); }
  });

  /* ------------------------------ detail panel ------------------------------ */

  function renderSessions(project) {
    sessionsList.textContent = '';
    project.sessions.forEach(function (name) {
      var item = el('li');
      var icon = el('span');
      icon.innerHTML = '<svg class="pr-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#pr-chat"/></svg>';
      icon.setAttribute('aria-hidden', 'true');
      item.appendChild(icon);
      item.appendChild(el('span', null, name));
      sessionsList.appendChild(item);
    });
    sessionsEmpty.hidden = project.sessions.length > 0;
  }

  function populateDetail(project) {
    detailName.textContent = project.name;
    detailDesc.textContent = project.description || 'No description added yet.';
    detailDate.textContent = 'Created ' + formatDate(project.createdAt);
    renderSessions(project);
  }

  function openDetail(id) {
    var project = findProject(id);
    if (!project) return;
    activeProjectId = id;
    populateDetail(project);
    detailLayer.hidden = false;
    detailClose.focus();
  }

  function closeDetail() {
    detailLayer.hidden = true;
    activeProjectId = null;
  }

  detailClose.addEventListener('click', closeDetail);
  detailBackdrop.addEventListener('click', closeDetail);
  $('pr-detail').addEventListener('keydown', function (event) {
    trapFocus($('pr-detail'), event);
  });

  addSessionBtn.addEventListener('click', function () {
    if (!activeProjectId) return;
    var project = findProject(activeProjectId);
    if (!project) return;
    var name = 'Session ' + (project.sessions.length + 1);
    project.sessions.push(name);
    saveProjects();
    renderSessions(project);
    render();
    showInfo('Session added', '“' + name + '” is linked to this project in this browser.', null);
  });

  /* ------------------------------ global escape ------------------------------ */

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;

    if (!dialog.hidden) {
      event.preventDefault();
      closeDialog();
      return;
    }
    if (!detailLayer.hidden) {
      event.preventDefault();
      closeDetail();
      return;
    }
    if (openMenu) {
      event.preventDefault();
      var pair = openMenu;
      closeMenus();
      pair.btn.focus();
      return;
    }
    if (!searchRow.hidden && document.activeElement === projectSearch) {
      event.preventDefault();
      projectSearch.value = '';
      applyFilter();
      toggleProjectSearch();
      return;
    }
    if (!recentsSearchWrap.hidden && document.activeElement === recentsSearch) {
      event.preventDefault();
      closeRecentsSearch(true);
    }
  });

  /* ------------------------------ init ------------------------------ */

  projects = loadProjects();
  render();
  syncSidebarToggles();
})();

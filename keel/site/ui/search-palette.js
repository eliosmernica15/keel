/* ===========================================================================
   Keel — reusable sidebar Search palette behaviour.
   No dependencies, no network calls. Exposes window.KeelSearchPalette.
   =========================================================================== */
(function () {
  'use strict';

  var TABS = [
    { id: 'all', label: 'All' },
    { id: 'artifacts', label: 'Artifacts' },
    { id: 'sessions', label: 'Sessions' },
    { id: 'code', label: 'Code' },
    { id: 'projects', label: 'Projects' },
    { id: 'scheduled', label: 'Scheduled' }
  ];

  var ICONS = {
    chat: '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 2.5c-3.3 0-6 2.2-6 4.9 0 1.6.9 3 2.3 3.9l-.5 2.2 2.3-1.2c.6.1 1.2.2 1.9.2 3.3 0 6-2.2 6-4.9s-2.7-5.1-6-5.1Z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>',
    doc: '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M4 2h5l3 3v9H4V2Z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M9 2v3h3M6 8h4M6 10.5h4" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/></svg>',
    plus: '<svg viewBox="0 0 20 20" aria-hidden="true" focusable="false"><path d="M10 4v12M4 10h12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
  };

  var ROWS = [
    { title: 'Keel harness build plan', icon: 'chat', kind: 'session', types: ['sessions', 'code', 'projects'] },
    { title: 'GPT-6.2 vs Fable 5.2 Prompts', icon: 'chat', kind: 'session', types: ['sessions'], annotation: 'Shared with you' },
    { title: 'Keel project review and plan', icon: 'chat', kind: 'session', types: ['sessions', 'projects'] },
    { title: 'Keel project plan review', icon: 'chat', kind: 'session', types: ['sessions', 'projects'] },
    { title: 'Test exercise answers', icon: 'chat', kind: 'session', types: ['sessions'] },
    { title: 'Team member project reports', icon: 'chat', kind: 'artifact', types: ['artifacts', 'sessions'] },
    { title: 'Discover Kosovo: Team Member Reports, Sprint 1 and 2 · Docs', icon: 'doc', kind: 'artifact', types: ['artifacts'] },
    { title: 'Connecting AutoCAD with MCP', icon: 'chat', kind: 'project', types: ['sessions', 'code', 'projects'] }
  ];

  var root, dialog, backdrop, input, closeBtn, tabsEl, bodyEl, noteEl, menuEl, actionRow, emptyEl;
  var tabButtons = [];
  var rowEls = [];
  var visibleRows = [];
  var selectedRow = null;
  var activeTab = 'all';
  var menuAnchor = null;
  var menuRow = null;
  var lastFocus = null;
  var openingTrigger = null;
  var isOpen = false;
  var inited = false;
  var noteTimer = null;
  var savedOverflow = null;

  /* ---------------------------------------------------------------- utils */
  function make(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function allRows() { return rowEls.concat([actionRow]); }

  /* ----------------------------------------------------------------- build */
  function buildRow(data, index) {
    var row = make('div', 'ksp-row');
    row.dataset.index = String(index);
    row.setAttribute('role', 'option');
    row.setAttribute('aria-selected', 'false');
    row.tabIndex = -1;

    var icon = make('span', 'ksp-row-ico' + (data.icon === 'doc' ? ' is-doc' : ''), ICONS[data.icon] || ICONS.chat);
    var title = make('span', 'ksp-row-title');
    title.textContent = data.title;
    row.appendChild(icon);
    row.appendChild(title);

    if (data.annotation) {
      var note = make('span', 'ksp-row-note');
      note.textContent = data.annotation;
      row.appendChild(note);
    }

    var tools = make('span', 'ksp-row-tools');
    var more = make('button', 'ksp-tool ksp-more', '&hellip;');
    more.type = 'button';
    more.setAttribute('aria-label', 'More options for ' + data.title);
    more.setAttribute('aria-haspopup', 'menu');
    more.setAttribute('aria-expanded', 'false');
    var ret = make('button', 'ksp-tool ksp-tool-return', '\u21A9');
    ret.type = 'button';
    ret.setAttribute('aria-label', 'Open ' + data.title);
    tools.appendChild(more);
    tools.appendChild(ret);
    row.appendChild(tools);

    row._kspData = data;
    rowEls.push(row);
    return row;
  }

  function buildActionRow() {
    var row = make('div', 'ksp-row ksp-action-row');
    row.dataset.action = 'new-session';
    row.setAttribute('role', 'option');
    row.setAttribute('aria-selected', 'false');
    row.tabIndex = -1;

    var icon = make('span', 'ksp-row-ico', ICONS.plus);
    var title = make('span', 'ksp-row-title');
    title.textContent = 'New session';
    row.appendChild(icon);
    row.appendChild(title);
    return row;
  }

  function buildMenu() {
    var menu = make('div', 'ksp-menu');
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Row actions');
    menu.hidden = true;
    ['Copy link', 'Rename', 'Delete'].forEach(function (label) {
      var button = make('button');
      button.type = 'button';
      button.setAttribute('role', 'menuitem');
      button.dataset.action = label;
      button.textContent = label;
      menu.appendChild(button);
    });
    return menu;
  }

  function makeHint(label, key, cls) {
    var wrap = make('span', 'ksp-hint' + (cls ? ' ' + cls : ''));
    wrap.appendChild(document.createTextNode(label + ' '));
    var kbd = make('kbd', 'ksp-key');
    kbd.textContent = key;
    wrap.appendChild(kbd);
    return wrap;
  }

  function build() {
    if (root) return;

    root = make('div', 'ksp-root');
    root.hidden = true;
    root.setAttribute('data-keel-search-palette', '');

    backdrop = make('div', 'ksp-backdrop');

    dialog = make('div', 'ksp-dialog');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', 'Search');

    /* search field */
    var search = make('div', 'ksp-search');
    var label = make('label', 'ksp-sr-only');
    label.htmlFor = 'ksp-search-input';
    label.textContent = 'Search';
    input = make('input', 'ksp-input');
    input.type = 'search';
    input.id = 'ksp-search-input';
    input.placeholder = 'Search';
    input.autocomplete = 'off';
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('aria-label', 'Search');
    closeBtn = make('button', 'ksp-close', '&times;');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close search');
    search.appendChild(label);
    search.appendChild(input);
    search.appendChild(closeBtn);

    /* tabs */
    tabsEl = make('div', 'ksp-tabs');
    tabsEl.setAttribute('role', 'tablist');
    tabsEl.setAttribute('aria-label', 'Search type');
    TABS.forEach(function (tab) {
      var button = make('button', 'ksp-tab' + (tab.id === 'all' ? ' is-active' : ''));
      button.type = 'button';
      button.dataset.tab = tab.id;
      button.textContent = tab.label;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', tab.id === 'all' ? 'true' : 'false');
      button.tabIndex = tab.id === 'all' ? 0 : -1;
      tabsEl.appendChild(button);
      tabButtons.push(button);
    });

    /* result list */
    bodyEl = make('div', 'ksp-body');
    bodyEl.setAttribute('role', 'listbox');
    bodyEl.setAttribute('aria-label', 'Search results');

    var recents = make('div', 'ksp-section');
    recents.dataset.section = 'recents';
    recents.setAttribute('role', 'group');
    recents.setAttribute('aria-label', 'Recents');
    var recentsLabel = make('div', 'ksp-label');
    recentsLabel.textContent = 'Recents';
    var recentsRows = make('div', 'ksp-rows');
    ROWS.forEach(function (data, index) { recentsRows.appendChild(buildRow(data, index)); });
    recents.appendChild(recentsLabel);
    recents.appendChild(recentsRows);

    var actions = make('div', 'ksp-section');
    actions.dataset.section = 'actions';
    actions.setAttribute('role', 'group');
    actions.setAttribute('aria-label', 'Actions');
    var actionsLabel = make('div', 'ksp-label');
    actionsLabel.textContent = 'Actions';
    var actionsRows = make('div', 'ksp-rows');
    actionRow = buildActionRow();
    actionsRows.appendChild(actionRow);
    actions.appendChild(actionsLabel);
    actions.appendChild(actionsRows);

    bodyEl.appendChild(recents);
    bodyEl.appendChild(actions);
    emptyEl = make('p', 'ksp-empty');
    emptyEl.textContent = 'No results.';
    emptyEl.hidden = true;
    bodyEl.appendChild(emptyEl);
    menuEl = buildMenu();
    bodyEl.appendChild(menuEl);

    noteEl = make('div', 'ksp-note');
    noteEl.setAttribute('role', 'status');
    noteEl.setAttribute('aria-live', 'polite');
    noteEl.hidden = true;

    /* footer */
    var footer = make('div', 'ksp-footer');
    var left = make('div', 'ksp-hints');
    left.appendChild(makeHint('Close', 'Esc'));
    left.appendChild(makeHint('Change type', '\u2190 \u2192', 'ksp-hint--wide'));
    left.appendChild(makeHint('Filters', '/', 'ksp-hint--mid'));
    left.appendChild(makeHint('Actions', 'Alt \u21A9', 'ksp-hint--wide'));
    var right = make('div', 'ksp-hints ksp-hints-right');
    right.appendChild(makeHint('Compose', 'Tab'));
    footer.appendChild(left);
    footer.appendChild(right);

    dialog.appendChild(search);
    dialog.appendChild(tabsEl);
    dialog.appendChild(bodyEl);
    dialog.appendChild(noteEl);
    dialog.appendChild(footer);

    root.appendChild(backdrop);
    root.appendChild(dialog);
    document.body.appendChild(root);

    wireEvents();
  }

  /* -------------------------------------------------------------- filtering */
  function applyFilter() {
    var query = (input.value || '').trim().toLowerCase();

    visibleRows = [];
    allRows().forEach(function (row) {
      var data = row._kspData;
      var title = data ? data.title : 'New session';
      var matchesText = !query || title.toLowerCase().indexOf(query) !== -1;
      var matchesTab = data ? (activeTab === 'all' || data.types.indexOf(activeTab) !== -1) : activeTab === 'all';
      var show = matchesText && matchesTab;
      row.hidden = !show;
      if (show) visibleRows.push(row);
    });

    Array.prototype.forEach.call(bodyEl.querySelectorAll('.ksp-section'), function (section) {
      var any = Array.prototype.some.call(section.querySelectorAll('.ksp-row'), function (row) {
        return !row.hidden;
      });
      section.hidden = !any;
    });

    emptyEl.hidden = visibleRows.length > 0;

    if (selectedRow && selectedRow.hidden) selectedRow = null;
    if (!selectedRow && visibleRows.length) selectedRow = visibleRows[0];
    setSelected(selectedRow);
    closeMenu();
  }

  function setSelected(row) {
    if (selectedRow && selectedRow !== row) {
      selectedRow.classList.remove('is-selected');
      selectedRow.setAttribute('aria-selected', 'false');
    }
    selectedRow = row || null;
    if (selectedRow) {
      selectedRow.classList.add('is-selected');
      selectedRow.setAttribute('aria-selected', 'true');
    }
  }

  function selectTab(id, focusIt) {
    activeTab = id;
    tabButtons.forEach(function (button) {
      var on = button.dataset.tab === id;
      button.classList.toggle('is-active', on);
      button.setAttribute('aria-selected', on ? 'true' : 'false');
      button.tabIndex = on ? 0 : -1;
      if (on && focusIt) button.focus();
    });
    applyFilter();
  }

  function cycleTab(direction) {
    var current = tabButtons.filter(function (button) { return button.dataset.tab === activeTab; })[0];
    var index = tabButtons.indexOf(current);
    if (index < 0) index = 0;
    var next = tabButtons[(index + direction + tabButtons.length) % tabButtons.length];
    selectTab(next.dataset.tab, true);
  }

  /* ------------------------------------------------------------------- menu */
  function openMenu(button, row) {
    if (!menuEl.hidden && menuAnchor === button) { closeMenu(); return; }
    closeMenu();
    menuAnchor = button;
    menuRow = row;
    button.setAttribute('aria-expanded', 'true');
    menuEl.hidden = false;

    var bodyRect = bodyEl.getBoundingClientRect();
    var buttonRect = button.getBoundingClientRect();
    var menuWidth = menuEl.offsetWidth || 156;
    var menuHeight = menuEl.offsetHeight || 100;
    var top = buttonRect.bottom - bodyRect.top + bodyEl.scrollTop + 6;
    var left = buttonRect.left - bodyRect.left;
    var maxLeft = bodyEl.clientWidth - menuWidth - 8;
    left = Math.max(8, Math.min(left, Math.max(8, maxLeft)));
    if (top + menuHeight > bodyEl.scrollTop + bodyEl.clientHeight - 4) {
      top = buttonRect.top - bodyRect.top + bodyEl.scrollTop - menuHeight - 6;
    }
    menuEl.style.top = top + 'px';
    menuEl.style.left = left + 'px';

    var first = menuEl.querySelector('button');
    if (first) first.focus();
  }

  function closeMenu() {
    if (!menuEl || menuEl.hidden) return;
    menuEl.hidden = true;
    if (menuAnchor) menuAnchor.setAttribute('aria-expanded', 'false');
    menuAnchor = null;
    menuRow = null;
  }

  /* ------------------------------------------------------------------- note */
  function showNote(message) {
    if (!noteEl) return;
    noteEl.textContent = message;
    noteEl.hidden = false;
    if (noteTimer) clearTimeout(noteTimer);
    noteTimer = setTimeout(function () {
      noteEl.hidden = true;
      noteTimer = null;
    }, 2600);
  }

  /* --------------------------------------------------------------- activation */
  function activate(row) {
    if (!row || row.hidden) return;
    setSelected(row);

    if (row._kspData) {
      var data = row._kspData;
      var event = new CustomEvent('keel:search-select', {
        detail: { title: data.title, type: data.kind },
        bubbles: true,
        cancelable: true
      });
      document.dispatchEvent(event);
      showNote('Selected: ' + data.title);
      return;
    }

    var actionEvent = new CustomEvent('keel:search-action', {
      detail: { action: 'new-session' },
      bubbles: true,
      cancelable: true
    });
    document.dispatchEvent(actionEvent);
    if (actionEvent.defaultPrevented) {
      showNote('New session requested.');
      return;
    }
    close();
    if (window.location.pathname.replace(/\/$/, '') !== '/new') {
      window.location.assign('/new');
    }
  }

  /* -------------------------------------------------------------- navigation */
  function revealRow(row) {
    if (!row) return;
    var rowRect = row.getBoundingClientRect();
    var bodyRect = bodyEl.getBoundingClientRect();
    if (rowRect.top < bodyRect.top) {
      bodyEl.scrollTop -= (bodyRect.top - rowRect.top) + 6;
    } else if (rowRect.bottom > bodyRect.bottom) {
      bodyEl.scrollTop += (rowRect.bottom - bodyRect.bottom) + 6;
    }
  }

  function moveSelection(direction, keepInputFocus) {
    if (!visibleRows.length) return;
    var index = visibleRows.indexOf(selectedRow);
    index = index < 0 ? 0 : (index + direction + visibleRows.length) % visibleRows.length;
    var row = visibleRows[index];
    setSelected(row);
    revealRow(row);
    if (!keepInputFocus) row.focus();
  }

  function getFocusables() {
    var list = [input];
    visibleRows.forEach(function (row) { list.push(row); });
    tabButtons.forEach(function (button) { list.push(button); });
    list.push(closeBtn);
    if (!menuEl.hidden) {
      var items = Array.prototype.slice.call(menuEl.querySelectorAll('button'));
      var at = menuAnchor ? list.indexOf(menuAnchor) + 1 : 1;
      if (at <= 0) at = 1;
      list.splice.apply(list, [at, 0].concat(items));
    }
    return list.filter(function (node) {
      return node && node.isConnected && !node.hidden;
    });
  }

  function handleTab(event) {
    event.preventDefault();
    var list = getFocusables();
    if (!list.length) return;
    var index = list.indexOf(document.activeElement);
    var next;
    if (event.shiftKey) {
      next = index <= 0 ? list[list.length - 1] : list[index - 1];
    } else {
      next = index < 0 ? list[0] : list[(index + 1) % list.length];
    }
    next.focus();
  }

  /* -------------------------------------------------------------- key events */
  function onDocumentKeydown(event) {
    if (!isOpen) return;
    var key = event.key;
    var target = event.target;

    if (key === 'Escape') {
      event.preventDefault();
      if (!menuEl.hidden) { closeMenu(); return; }
      close();
      return;
    }

    if (event.altKey && key === 'Enter') {
      event.preventDefault();
      showNote('Actions — New session is listed below.');
      return;
    }

    if (key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (!(target === input)) {
        event.preventDefault();
        input.focus();
        showNote('Filters — type to narrow results.');
        return;
      }
    }

    if (key === 'Tab') { handleTab(event); return; }

    if (key.indexOf('Arrow') === 0) {
      if (tabButtons.indexOf(target) !== -1) {
        event.preventDefault();
        cycleTab(key === 'ArrowRight' || key === 'ArrowDown' ? 1 : -1);
        return;
      }
      if (key === 'ArrowDown' || key === 'ArrowUp') {
        event.preventDefault();
        moveSelection(key === 'ArrowDown' ? 1 : -1, target === input);
      }
      return;
    }

    if (key === 'Enter') {
      if (tabButtons.indexOf(target) !== -1) {
        event.preventDefault();
        selectTab(target.dataset.tab, false);
        return;
      }
      if (target === input) {
        event.preventDefault();
        activate(selectedRow);
        return;
      }
      if (target && target.classList && target.classList.contains('ksp-row')) {
        event.preventDefault();
        activate(target);
      }
    }
  }

  function onFocusIn(event) {
    if (!isOpen) return;
    if (dialog.contains(event.target)) return;
    if (!menuEl.hidden && menuEl.contains(event.target)) return;
    input.focus();
  }

  /* ------------------------------------------------------------------ events */
  function wireEvents() {
    input.addEventListener('input', applyFilter);
    closeBtn.addEventListener('click', close);
    backdrop.addEventListener('click', close);

    bodyEl.addEventListener('click', function (event) {
      var target = event.target;
      var tool = target && target.closest ? target.closest('.ksp-tool') : null;
      if (tool) {
        var toolRow = tool.closest('.ksp-row');
        if (tool.classList.contains('ksp-more')) openMenu(tool, toolRow);
        else activate(toolRow);
        return;
      }
      if (target && target.closest && target.closest('.ksp-menu')) return;
      var row = target && target.closest ? target.closest('.ksp-row') : null;
      if (row) activate(row);
    });

    menuEl.addEventListener('click', function (event) {
      var target = event.target;
      var button = target && target.closest ? target.closest('button') : null;
      if (!button) return;
      var label = button.dataset.action;
      var title = menuRow && menuRow._kspData ? menuRow._kspData.title : 'this item';
      var message;
      if (label === 'Copy link') message = 'Link copied for \u201c' + title + '\u201d.';
      else if (label === 'Rename') message = 'Rename \u201c' + title + '\u201d (preview only).';
      else message = 'Delete \u201c' + title + '\u201d (preview only).';
      closeMenu();
      showNote(message);
    });

    document.addEventListener('mousedown', function (event) {
      if (!isOpen || menuEl.hidden) return;
      if (menuEl.contains(event.target)) return;
      if (menuAnchor && menuAnchor.contains(event.target)) return;
      closeMenu();
    }, true);
  }

  /* -------------------------------------------------------------- public API */
  function open(trigger) {
    if (isOpen || !document.body) return;
    build();

    isOpen = true;
    lastFocus = document.activeElement;
    openingTrigger = trigger || null;
    savedOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    if (openingTrigger && openingTrigger.setAttribute) openingTrigger.setAttribute('aria-expanded', 'true');

    root.hidden = false;
    input.value = '';
    selectedRow = null;
    selectTab('all', false);

    document.addEventListener('keydown', onDocumentKeydown, true);
    document.addEventListener('focusin', onFocusIn, true);

    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () {
        if (!isOpen) return;
        input.focus();
        if (typeof input.setSelectionRange === 'function') input.setSelectionRange(0, 0);
      });
    } else {
      input.focus();
    }
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    closeMenu();
    root.hidden = true;
    document.removeEventListener('keydown', onDocumentKeydown, true);
    document.removeEventListener('focusin', onFocusIn, true);

    if (noteTimer) {
      clearTimeout(noteTimer);
      noteTimer = null;
    }
    if (noteEl) noteEl.hidden = true;

    if (savedOverflow !== null) {
      document.body.style.overflow = savedOverflow;
      savedOverflow = null;
    }
    if (openingTrigger && openingTrigger.setAttribute) openingTrigger.setAttribute('aria-expanded', 'false');

    var target = lastFocus;
    lastFocus = null;
    openingTrigger = null;
    if (target && target.isConnected && typeof target.focus === 'function') {
      try { target.focus(); } catch (error) { /* focus restoration is best effort */ }
    }
  }

  function toggle(trigger) {
    if (isOpen) close();
    else open(trigger);
  }

  window.KeelSearchPalette = {
    open: open,
    close: close,
    toggle: toggle,
    isOpen: function () { return isOpen; }
  };

  /* --------------------------------------------------------------- autobind */
  function bindTriggers() {
    var triggers = [];
    var seen = [];

    function add(element) {
      if (!element || seen.indexOf(element) !== -1) return;
      seen.push(element);
      triggers.push(element);
    }

    Array.prototype.forEach.call(document.querySelectorAll('[data-search-trigger]'), add);
    Array.prototype.forEach.call(document.querySelectorAll('a[id="nav-search"]'), add);

    var candidates = document.querySelectorAll('button, a, [role="button"]');
    Array.prototype.forEach.call(candidates, function (element) {
      var tag = element.tagName ? element.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (element.closest('form, .n-search-wrap, .ksp-root, [data-search-input]')) return;
      var text = (element.textContent || '').trim();
      var aria = element.getAttribute('aria-label') || '';
      if (text !== 'Search' && aria.trim() !== 'Search') return;
      var className = typeof element.className === 'string' ? element.className : '';
      var inSidebar = !!element.closest('aside, nav, [class*="sidebar"], [class*="side-nav"], [id*="sidebar"]');
      if (!inSidebar && !/(^|\s)nav/i.test(className)) return;
      add(element);
    });

    triggers.forEach(function (element) {
      if (element.dataset && element.dataset.kspBound) return;
      if (element.dataset) element.dataset.kspBound = '1';
      if (element.hasAttribute && !element.hasAttribute('aria-expanded')) element.setAttribute('aria-expanded', 'false');
      element.addEventListener('click', function (event) {
        event.preventDefault();
        open(element);
      });
    });
  }

  function initOnce() {
    if (inited) return;
    inited = true;
    build();
    bindTriggers();
  }

  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initOnce);
    } else {
      initOnce();
    }
  }

  init();
})();

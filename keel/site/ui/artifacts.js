/* Keel — /artifacts page behaviour. Dependency-free, no network calls. */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function toArray(list) { return Array.prototype.slice.call(list); }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  /* ------------------------------- data ------------------------------- */

  var STORAGE_KEY = 'keel.artifacts.v1';

  var seeds = [
    {
      id: 'seed-prompts',
      title: 'GPT-6.2 vs Fable 5.2 Prompts',
      previewTitle: 'GPT-6.2 vs Fable 5.2 Prompts',
      type: 'Design',
      owner: 'shared',
      dateLabel: 'Nov 21',
      dateISO: '2026-11-21',
      views: 381,
      shared: true,
      thumb: 'wire'
    },
    {
      id: 'seed-kosovo',
      title: 'Discover Kosovo: Team Member Report…',
      previewTitle: 'Discover Kosovo: Team Member Reports, Sprint 1 and 2',
      type: 'Docs',
      owner: 'yours',
      dateLabel: 'Oct 27',
      dateISO: '2026-10-27',
      views: null,
      shared: false,
      thumb: 'docs'
    }
  ];

  function copySeeds() {
    return seeds.map(function (item) {
      var copy = {};
      Object.keys(item).forEach(function (key) { copy[key] = item[key]; });
      return copy;
    });
  }

  function isValidArtifact(item) {
    return item && typeof item === 'object' && typeof item.id === 'string' && typeof item.title === 'string';
  }

  function loadArtifacts() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed.filter(isValidArtifact).map(function (item) {
            var normalized = {
              id: item.id,
              title: item.title,
              previewTitle: typeof item.previewTitle === 'string' ? item.previewTitle : item.title,
              type: ['Docs', 'Slides', 'Design'].indexOf(item.type) !== -1 ? item.type : 'Docs',
              owner: item.owner === 'shared' ? 'shared' : 'yours',
              dateLabel: typeof item.dateLabel === 'string' ? item.dateLabel : '',
              dateISO: typeof item.dateISO === 'string' ? item.dateISO : '',
              views: typeof item.views === 'number' ? item.views : null,
              shared: item.shared === true,
              thumb: typeof item.thumb === 'string' ? item.thumb : 'docs'
            };
            return normalized;
          });
        }
      }
    } catch (error) {
      /* Storage can be unavailable; the page still works in memory. */
    }
    return copySeeds();
  }

  var artifacts = loadArtifacts();

  function saveArtifacts() {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(artifacts));
    } catch (error) {
      /* Keep the in-memory copy when storage is blocked. */
    }
  }

  function dateParts(date) {
    function pad(value) { return value < 10 ? '0' + value : String(value); }
    return {
      label: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      iso: date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
    };
  }

  function newId() {
    return 'local-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
  }

  /* ------------------------------ shell ------------------------------ */

  var app = $('ar-app');
  var sidebarToggle = $('ar-sidebar-toggle');
  var collapse = $('ar-collapse');
  var scrim = $('ar-scrim');
  var navSearch = $('ar-nav-search');
  var recentsToggle = $('ar-recents-toggle');
  var recentsList = $('ar-recents-list');
  var recentsEmpty = $('ar-recents-empty');
  var recentsViewAll = $('ar-recents-view-all');
  var accountBtn = $('ar-account');
  var accountMenu = $('ar-account-menu');
  var helpBtn = $('ar-help');

  var mobileQuery = window.matchMedia('(max-width: 860px)');
  var RECENTS_KEY = 'keel_new_recents_v1';
  var RECENTS_PREVIEW = 5;

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

  /* One authoritative state class on the app root at a time: `sidebar-open`
     on small screens, `sidebar-collapsed` on wide screens, none otherwise. */
  function setSidebar(open) {
    app.classList.remove('sidebar-open', 'sidebar-collapsed');
    if (mobileQuery.matches) {
      if (open) app.classList.add('sidebar-open');
    } else if (!open) {
      app.classList.add('sidebar-collapsed');
    }
    syncSidebarToggles();
  }

  function onViewportChange() {
    app.classList.remove('sidebar-open', 'sidebar-collapsed');
    syncSidebarToggles();
  }

  function paletteOpen() {
    return !!(window.KeelSearchPalette &&
      typeof window.KeelSearchPalette.isOpen === 'function' &&
      window.KeelSearchPalette.isOpen());
  }

  function openSearchPalette() {
    if (window.KeelSearchPalette && typeof window.KeelSearchPalette.open === 'function') {
      window.KeelSearchPalette.open(navSearch);
    }
  }

  sidebarToggle.addEventListener('click', function () { setSidebar(!isSidebarOpen()); });
  collapse.addEventListener('click', function () { setSidebar(!isSidebarOpen()); });
  scrim.addEventListener('click', function () { setSidebar(false); });
  if (mobileQuery.addEventListener) mobileQuery.addEventListener('change', onViewportChange);
  else if (mobileQuery.addListener) mobileQuery.addListener(onViewportChange);
  syncSidebarToggles();

  /* ------------------------------ recents ------------------------------ */

  /* Recents are empty until Keel saves real chats in keel_new_recents_v1. */
  function loadRecents() {
    try {
      var raw = window.localStorage.getItem(RECENTS_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      var titles = [];
      parsed.forEach(function (entry) {
        var title = '';
        if (typeof entry === 'string') {
          title = entry;
        } else if (entry && typeof entry === 'object') {
          title = typeof entry.title === 'string' ? entry.title
            : typeof entry.prompt === 'string' ? entry.prompt
            : typeof entry.text === 'string' ? entry.text
            : typeof entry.label === 'string' ? entry.label : '';
        }
        title = String(title).replace(/\s+/g, ' ').trim();
        if (title && titles.indexOf(title) === -1) titles.push(title.slice(0, 90));
      });
      return titles;
    } catch (error) {
      return [];
    }
  }

  var recentItems = [];
  var allRecents = false;

  function buildRecentItem(title) {
    var li = document.createElement('li');
    var button = document.createElement('button');
    button.className = 'ar-recent';
    button.type = 'button';
    button.setAttribute('data-title', title);
    button.innerHTML = '<svg class="ar-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#ar-chat"/></svg>';
    var label = document.createElement('span');
    label.textContent = title;
    button.appendChild(label);
    button.addEventListener('click', function () { window.location.assign('/new'); });
    li.appendChild(button);
    recentsList.appendChild(li);
    return li;
  }

  loadRecents().forEach(function (title) { recentItems.push(buildRecentItem(title)); });

  function applyRecents() {
    recentItems.forEach(function (li, index) {
      li.hidden = !allRecents && index >= RECENTS_PREVIEW;
    });
    recentsEmpty.hidden = recentItems.length > 0;
    var showAll = recentItems.length > RECENTS_PREVIEW;
    recentsViewAll.hidden = !showAll || recentsList.hidden;
    recentsViewAll.setAttribute('aria-expanded', String(allRecents));
    recentsViewAll.setAttribute('aria-label', allRecents ? 'Show fewer recent chats' : 'Show all recent chats');
  }

  navSearch.addEventListener('click', function () {
    if (mobileQuery.matches) setSidebar(false);
    openSearchPalette();
  });

  recentsToggle.addEventListener('click', function () {
    var willShow = recentsList.hidden;
    recentsList.hidden = !willShow;
    if (willShow) {
      applyRecents();
    } else {
      recentsEmpty.hidden = true;
      recentsViewAll.hidden = true;
    }
    recentsToggle.setAttribute('aria-expanded', String(willShow));
  });

  recentsViewAll.addEventListener('click', function () {
    allRecents = !allRecents;
    applyRecents();
  });

  helpBtn.addEventListener('click', function () {
    showInfo('Help with Keel', 'Use the tabs, search and filter controls to find artifacts. Create one from the + button or the tiles, then open it to duplicate or delete it.', '/download', 'Download Keel');
  });

  /* --------------------------- note / toast --------------------------- */

  var infoPanel = $('ar-info-panel');
  var infoTitle = $('ar-info-title');
  var infoText = $('ar-info-text');
  var infoLink = $('ar-info-link');
  var infoClose = $('ar-info-close');
  var infoTimer = null;

  function hideInfo() {
    if (infoTimer !== null) { window.clearTimeout(infoTimer); infoTimer = null; }
    infoPanel.hidden = true;
  }

  function showInfo(title, text, href, linkLabel) {
    infoTitle.textContent = title;
    infoText.textContent = text;
    if (href) {
      infoLink.href = href;
      infoLink.textContent = linkLabel || (href === '/download' ? 'Download Keel' : 'Open in Keel');
      infoLink.hidden = false;
    } else {
      infoLink.hidden = true;
    }
    infoPanel.hidden = false;
    if (infoTimer !== null) window.clearTimeout(infoTimer);
    infoTimer = window.setTimeout(hideInfo, 6000);
  }

  infoClose.addEventListener('click', hideInfo);

  /* ------------------------------ menus ------------------------------ */

  var filterBtn = $('ar-filter-btn');
  var filterMenu = $('ar-filter-menu');

  var menuPairs = [
    { btn: filterBtn, menu: filterMenu },
    { btn: accountBtn, menu: accountMenu }
  ];

  function getMenuItems(menu) {
    return toArray(menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]'))
      .filter(function (item) { return !item.hidden && item.offsetParent !== null; });
  }

  function closeMenus() {
    menuPairs.forEach(function (pair) {
      pair.menu.hidden = true;
      pair.btn.setAttribute('aria-expanded', 'false');
    });
  }

  function toggleMenu(pair, focusFirst) {
    var willOpen = pair.menu.hidden;
    closeMenus();
    if (willOpen) {
      pair.menu.hidden = false;
      pair.btn.setAttribute('aria-expanded', 'true');
      if (focusFirst !== false) {
        var items = getMenuItems(pair.menu);
        if (items.length) items[0].focus();
      }
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

  accountMenu.addEventListener('click', function () { closeMenus(); });

  document.addEventListener('click', function (event) {
    if (!event.target.closest('.ar-wrap') && !event.target.closest('#ar-account-wrap')) closeMenus();
  });

  /* ---------------------------- page state ---------------------------- */

  var state = { tab: 'all', query: '', type: 'all', sort: 'newest', list: false };

  var tabButtons = toArray(document.querySelectorAll('.ar-tab'));
  var grid = $('ar-card-grid');
  var emptyState = $('ar-empty');
  var results = $('ar-results');
  var artifactSearchRow = $('ar-search-row');
  var artifactSearch = $('ar-artifact-search');
  var searchClear = $('ar-search-clear');
  var viewBtn = $('ar-view-btn');
  var viewIconUse = $('ar-view-icon-use');
  var addBtn = $('ar-add-btn');

  function selectTab(tab) {
    state.tab = tab;
    tabButtons.forEach(function (button) {
      var on = button.getAttribute('data-tab') === tab;
      button.classList.toggle('is-active', on);
      button.setAttribute('aria-selected', String(on));
      button.tabIndex = on ? 0 : -1;
      if (on) results.setAttribute('aria-labelledby', button.id);
    });
    render();
  }

  tabButtons.forEach(function (button) {
    button.addEventListener('click', function () { selectTab(button.getAttribute('data-tab')); });
    button.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      event.preventDefault();
      var index = tabButtons.indexOf(button);
      var next = tabButtons[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabButtons.length) % tabButtons.length];
      selectTab(next.getAttribute('data-tab'));
      next.focus();
    });
  });

  function paletteAvailable() {
    return !!(window.KeelSearchPalette && typeof window.KeelSearchPalette.toggle === 'function');
  }

  $('ar-search-btn').addEventListener('click', function (event) {
    if (paletteAvailable()) {
      window.KeelSearchPalette.toggle(event.currentTarget);
      return;
    }
    var willOpen = artifactSearchRow.hidden;
    artifactSearchRow.hidden = !willOpen;
    event.currentTarget.setAttribute('aria-expanded', String(willOpen));
    if (willOpen) {
      artifactSearch.focus();
    } else {
      artifactSearch.value = '';
      searchClear.hidden = true;
      state.query = '';
      render();
    }
  });

  artifactSearch.addEventListener('input', function () {
    state.query = artifactSearch.value.trim().toLowerCase();
    searchClear.hidden = !artifactSearch.value;
    render();
  });

  searchClear.addEventListener('click', function () {
    artifactSearch.value = '';
    searchClear.hidden = true;
    state.query = '';
    render();
    artifactSearch.focus();
  });

  document.addEventListener('keel:search-select', function (event) {
    var title = event.detail && event.detail.title;
    if (!title) return;
    var match = findByTitle(title);
    if (match) openDetail(match.id);
    else showInfo('Search result', 'Selected "' + title + '" in Keel Search.', null);
  });

  function normalizedTitle(value) {
    return String(value).toLowerCase().replace(/[…\.\s]+$/, '').replace(/\s*·.*$/, '').trim();
  }

  function findByTitle(title) {
    var target = normalizedTitle(title);
    if (!target) return null;
    for (var i = 0; i < artifacts.length; i += 1) {
      var candidate = normalizedTitle(artifacts[i].title);
      if (candidate && (target.indexOf(candidate) === 0 || candidate.indexOf(target) === 0)) return artifacts[i];
    }
    return null;
  }

  filterMenu.addEventListener('click', function (event) {
    var item = event.target.closest('button[role="menuitemradio"]');
    if (!item || !filterMenu.contains(item)) return;
    if (item.hasAttribute('data-type')) {
      state.type = item.getAttribute('data-type');
      toArray(filterMenu.querySelectorAll('[data-type]')).forEach(function (radio) {
        radio.setAttribute('aria-checked', String(radio === item));
      });
    } else if (item.hasAttribute('data-sort')) {
      state.sort = item.getAttribute('data-sort');
      toArray(filterMenu.querySelectorAll('[data-sort]')).forEach(function (radio) {
        radio.setAttribute('aria-checked', String(radio === item));
      });
    }
    closeMenus();
    filterBtn.focus();
    render();
  });

  viewBtn.addEventListener('click', function () {
    state.list = !state.list;
    viewBtn.setAttribute('aria-pressed', String(state.list));
    viewBtn.setAttribute('aria-label', state.list ? 'Switch to grid view' : 'Switch to list view');
    viewIconUse.setAttribute('href', state.list ? '#ar-list' : '#ar-grid');
    render();
  });

  addBtn.addEventListener('click', function () { openCreate(''); });
  toArray(document.querySelectorAll('.ar-tile')).forEach(function (tile) {
    tile.addEventListener('click', function () { openCreate(tile.getAttribute('data-type') || ''); });
  });

  $('ar-clear-filters').addEventListener('click', function () { resetFilters(); });

  function resetFilters() {
    state.tab = 'all';
    state.query = '';
    state.type = 'all';
    state.sort = 'newest';
    artifactSearch.value = '';
    searchClear.hidden = true;
    artifactSearchRow.hidden = true;
    $('ar-search-btn').setAttribute('aria-expanded', 'false');
    toArray(filterMenu.querySelectorAll('button[role="menuitemradio"]')).forEach(function (radio) {
      var value = radio.hasAttribute('data-type') ? radio.getAttribute('data-type') : radio.getAttribute('data-sort');
      radio.setAttribute('aria-checked', String(value === 'all' || value === 'newest'));
    });
    selectTab('all');
  }

  /* ----------------------------- rendering ----------------------------- */

  function visibleArtifacts() {
    var query = state.query;
    var list = artifacts.filter(function (item) {
      if (state.tab === 'yours' && item.owner !== 'yours') return false;
      if (state.tab === 'shared' && item.owner !== 'shared') return false;
      if (state.type !== 'all' && item.type !== state.type) return false;
      if (query && (item.title + ' ' + item.type + ' ' + (item.previewTitle || '')).toLowerCase().indexOf(query) === -1) return false;
      return true;
    });

    list.sort(function (a, b) {
      if (state.sort === 'oldest') return (a.dateISO || '').localeCompare(b.dateISO || '');
      if (state.sort === 'name-asc') return a.title.localeCompare(b.title);
      if (state.sort === 'name-desc') return b.title.localeCompare(a.title);
      return (b.dateISO || '').localeCompare(a.dateISO || '');
    });

    return list;
  }

  function thumbHtml(item) {
    if (item.thumb === 'wire') {
      return '<span class="ar-thumb ar-thumb--wire" aria-hidden="true">' +
        '<span class="ar-wire"><i class="ar-wire-bar"></i><i class="ar-wire-bar short"></i>' +
        '<span class="ar-wire-blocks"><i class="ar-wire-block"></i><i class="ar-wire-block"></i>' +
        '<i class="ar-wire-block"></i><i class="ar-wire-block"></i></span></span></span>';
    }
    if (item.thumb === 'docs') {
      return '<span class="ar-thumb ar-thumb--docs" aria-hidden="true">' +
        '<span class="ar-mini-doc"><span class="ar-mini-doc-head">' + escapeHtml(item.previewTitle || item.title) + '</span>' +
        '<i class="ar-mini-doc-line wide"></i><i class="ar-mini-doc-line"></i>' +
        '<i class="ar-mini-doc-line mid"></i><i class="ar-mini-doc-line wide"></i>' +
        '<i class="ar-mini-doc-line narrow"></i></span></span>';
    }
    if (item.thumb === 'slides') {
      return '<span class="ar-thumb ar-thumb--slides" aria-hidden="true">' +
        '<span class="ar-mini-slide"><i class="ar-mini-slide-bar"></i><i class="ar-mini-slide-bar short"></i>' +
        '<i class="ar-mini-slide-block"></i></span></span>';
    }
    return '<span class="ar-thumb ar-thumb--design" aria-hidden="true">' +
      '<span class="ar-mini-design"><svg class="ar-ico" viewBox="0 0 24 24"><use href="#ar-palette"/></svg></span></span>';
  }

  function footHtml(item) {
    if (item.shared || typeof item.views === 'number') {
      var views = typeof item.views === 'number'
        ? '<span class="ar-card-stat"><svg class="ar-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#ar-eye"/></svg>' + item.views + '</span>'
        : '';
      var globe = item.shared
        ? '<span class="ar-card-stat ar-shared" aria-label="Shared"><svg class="ar-ico" viewBox="0 0 16 16" aria-hidden="true"><use href="#ar-globe"/></svg></span>'
        : '';
      return '<span class="ar-card-foot"><span>' + escapeHtml(item.dateLabel) + '</span>' + views + globe + '</span>';
    }
    return '<span class="ar-card-foot">' + escapeHtml(item.type) + ' · ' + escapeHtml(item.dateLabel) + '</span>';
  }

  function render() {
    var list = visibleArtifacts();
    grid.classList.toggle('is-list', state.list);
    grid.innerHTML = list.map(function (item) {
      return '<button class="ar-card" type="button" data-id="' + escapeHtml(item.id) + '" aria-label="Open artifact: ' + escapeHtml(item.title) + '">' +
        thumbHtml(item) +
        '<span class="ar-card-meta"><span class="ar-card-title">' + escapeHtml(item.title) + '</span>' +
        footHtml(item) + '</span></button>';
    }).join('');
    emptyState.hidden = list.length > 0;
  }

  grid.addEventListener('click', function (event) {
    var card = event.target.closest('.ar-card');
    if (card) openDetail(card.getAttribute('data-id'));
  });

  /* --------------------------- modal system --------------------------- */

  var createModal = $('ar-create-modal');
  var createCard = $('ar-create-card');
  var detailModal = $('ar-detail-modal');
  var detailCard = $('ar-detail-card');
  var activeModal = null;
  var lastFocused = null;
  var currentId = null;

  function openModal(modal, card, focusTarget) {
    lastFocused = document.activeElement;
    activeModal = { modal: modal, card: card };
    modal.hidden = false;
    (focusTarget || card.querySelector('button')).focus();
  }

  function closeModal() {
    if (!activeModal) return;
    activeModal.modal.hidden = true;
    var target = lastFocused;
    activeModal = null;
    lastFocused = null;
    if (target && document.contains(target) && typeof target.focus === 'function') target.focus();
  }

  toArray(document.querySelectorAll('[data-close-modal]')).forEach(function (backdrop) {
    backdrop.addEventListener('click', closeModal);
  });

  $('ar-create-close').addEventListener('click', closeModal);
  $('ar-create-cancel').addEventListener('click', closeModal);
  $('ar-detail-close').addEventListener('click', closeModal);

  [createCard, detailCard].forEach(function (card) {
    card.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab' || !activeModal || activeModal.card !== card) return;
      var focusable = toArray(card.querySelectorAll('a[href], button:not([disabled]), input:not([disabled])'))
        .filter(function (element) { return element.offsetParent !== null && !element.hidden; });
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
  });

  /* -------------------------- create artifact -------------------------- */

  var nameField = $('ar-create-name');
  var nameError = $('ar-create-error');
  var typeRadios = toArray(document.querySelectorAll('input[name="ar-create-type"]'));

  function openCreate(preselect) {
    var wanted = ['Docs', 'Slides', 'Design'].indexOf(preselect) !== -1 ? preselect : 'Docs';
    typeRadios.forEach(function (radio) { radio.checked = radio.value === wanted; });
    nameField.value = '';
    nameError.hidden = true;
    openModal(createModal, createCard, nameField);
  }

  nameField.addEventListener('input', function () { nameError.hidden = true; });

  nameField.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') { event.preventDefault(); confirmCreate(); }
  });

  $('ar-create-confirm').addEventListener('click', confirmCreate);

  function confirmCreate() {
    var name = nameField.value.trim();
    if (!name) {
      nameError.hidden = false;
      nameField.focus();
      return;
    }
    var type = 'Docs';
    typeRadios.forEach(function (radio) { if (radio.checked) type = radio.value; });
    var now = new Date();
    var parts = dateParts(now);
    artifacts.unshift({
      id: newId(),
      title: name,
      previewTitle: name,
      type: type,
      owner: 'yours',
      dateLabel: parts.label,
      dateISO: parts.iso,
      views: null,
      shared: false,
      thumb: type === 'Docs' ? 'docs' : type === 'Slides' ? 'slides' : 'design'
    });
    saveArtifacts();
    closeModal();
    resetFilters();
    showInfo('Artifact created', '"' + name + '" was added to your artifacts.', null);
  }

  /* ------------------------- artifact details ------------------------- */

  var detailsView = $('ar-detail-details');
  var fullView = $('ar-detail-full');
  var detailPreview = $('ar-detail-preview');
  var detailKicker = $('ar-detail-kicker');
  var detailTitle = $('ar-detail-title');
  var fullTitle = $('ar-full-title');
  var fullPreview = $('ar-full-preview');

  function findArtifact(id) {
    for (var i = 0; i < artifacts.length; i += 1) {
      if (artifacts[i].id === id) return artifacts[i];
    }
    return null;
  }

  function openDetail(id) {
    var item = findArtifact(id);
    if (!item) return;
    currentId = id;
    detailPreview.innerHTML = thumbHtml(item);
    fullPreview.innerHTML = thumbHtml(item);
    detailKicker.textContent = item.type + ' · ' + item.dateLabel + (item.shared ? ' · Shared with you' : '');
    detailTitle.textContent = item.title;
    fullTitle.textContent = item.title;
    detailsView.hidden = false;
    fullView.hidden = true;
    openModal(detailModal, detailCard, $('ar-detail-open'));
  }

  $('ar-detail-open').addEventListener('click', function () {
    detailsView.hidden = true;
    fullView.hidden = false;
    $('ar-full-back').focus();
  });

  $('ar-full-back').addEventListener('click', function () {
    fullView.hidden = true;
    detailsView.hidden = false;
    $('ar-detail-open').focus();
  });

  $('ar-detail-duplicate').addEventListener('click', function () {
    var item = findArtifact(currentId);
    if (!item) return;
    var now = new Date();
    var parts = dateParts(now);
    var base = item.title.replace(/\s*…\s*$/, '');
    var copy = {};
    Object.keys(item).forEach(function (key) { copy[key] = item[key]; });
    copy.id = newId();
    copy.title = base + ' (copy)';
    copy.previewTitle = base + ' (copy)';
    copy.owner = 'yours';
    copy.shared = false;
    copy.views = null;
    copy.dateLabel = parts.label;
    copy.dateISO = parts.iso;
    artifacts.unshift(copy);
    saveArtifacts();
    closeModal();
    render();
    showInfo('Artifact duplicated', '"' + copy.title + '" was added to your artifacts.', null);
  });

  $('ar-detail-delete').addEventListener('click', function () {
    var item = findArtifact(currentId);
    if (!item) return;
    artifacts = artifacts.filter(function (candidate) { return candidate.id !== item.id; });
    saveArtifacts();
    closeModal();
    render();
    showInfo('Artifact deleted', '"' + item.title + '" was removed from this browser.', null);
  });

  /* ---------------------------- global escape -------------------------- */

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    if (paletteOpen()) return;

    if (activeModal) { closeModal(); return; }

    var openPair = null;
    menuPairs.forEach(function (pair) { if (!pair.menu.hidden) openPair = pair; });
    if (openPair) { closeMenus(); openPair.btn.focus(); return; }

    if (!artifactSearchRow.hidden && document.activeElement === artifactSearch) {
      $('ar-search-btn').click();
      return;
    }
    if (mobileQuery.matches && isSidebarOpen()) setSidebar(false);
  });

  /* ------------------------------- init ------------------------------- */

  applyRecents();
  selectTab('all');
})();

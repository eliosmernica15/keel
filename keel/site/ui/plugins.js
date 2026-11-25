/* Keel — /plugins page behaviour. Dependency-free, no network calls. */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function toArray(list) { return Array.prototype.slice.call(list); }
  function attr(element, name) { return element.getAttribute('data-' + name) || ''; }

  /* ------------------------------ shell ------------------------------ */

  var app = $('p-app');
  var sidebarToggle = $('p-sidebar-toggle');
  var collapse = $('p-collapse');
  var scrim = $('p-scrim');
  var navNew = $('p-nav-new');
  var navSearch = $('p-nav-search');
  var navPlugins = $('p-nav-plugins');
  var recentsToggle = $('p-recents-toggle');
  var recentsList = $('p-recents-list');
  var recentsEmpty = $('p-recents-empty');
  var recentsViewAll = $('p-recents-view-all');
  var searchWrap = $('p-recents-search-wrap');
  var searchInput = $('p-recents-search');
  var searchClose = $('p-recents-search-close');
  var accountBtn = $('p-account');
  var accountMenu = $('p-account-menu');
  var helpBtn = $('p-help');
  var main = document.querySelector('.p-main');

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
  if (mobileQuery.addEventListener) mobileQuery.addEventListener('change', onViewportChange);
  else if (mobileQuery.addListener) mobileQuery.addListener(onViewportChange);
  syncSidebarToggles();

  /* ------------------------------ recents ------------------------------ */

  var recentItems = toArray(recentsList.querySelectorAll('li'));
  var allRecents = true;

  function applyRecents() {
    var query = searchInput.value.trim().toLowerCase();
    var visible = 0;
    recentItems.forEach(function (li) {
      var button = li.querySelector('.p-recent');
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
    var button = li.querySelector('.p-recent');
    button.addEventListener('click', function () {
      var title = button.getAttribute('data-title') || '';
      if (mobileQuery.matches) setSidebar(false);
      showInfo('Recent chat', 'Open "' + title + '" in a new Keel chat.', '/new');
    });
  });

  navNew.addEventListener('click', function () { window.location.assign('/new'); });
  navPlugins.addEventListener('click', function () {
    if (mobileQuery.matches) setSidebar(false);
    if (main) main.scrollTop = 0;
  });

  /* --------------------------- in-page notes --------------------------- */

  var infoPanel = $('p-info-panel');
  var infoTitle = $('p-info-title');
  var infoText = $('p-info-text');
  var infoLink = $('p-info-link');
  var infoClose = $('p-info-close');
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
    infoTimer = window.setTimeout(hideInfo, 12000);
  }

  infoClose.addEventListener('click', hideInfo);

  var panelMessages = {
    projects: ['Projects', 'Projects keep related chats, files and artifacts together. Manage them in the Keel app.', '/app'],
    artifacts: ['Artifacts', 'Artifacts are the documents and designs Keel creates for you. Browse the full set in the app.', '/app']
  };

  toArray(document.querySelectorAll('[data-info-panel]')).forEach(function (button) {
    button.addEventListener('click', function () {
      if (mobileQuery.matches) setSidebar(false);
      var message = panelMessages[button.getAttribute('data-info-panel')];
      if (message) showInfo(message[0], message[1], message[2]);
    });
  });

  helpBtn.addEventListener('click', function () {
    showInfo('Help with Keel', 'Search or filter the directory to find connectors, skills and MCP servers. Install them from the Keel desktop app.', '/download');
  });

  var toast = $('p-toast');
  var toastTimer = null;

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    if (toastTimer !== null) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toast.hidden = true; toastTimer = null; }, 3200);
  }

  /* ------------------------------ menus ------------------------------ */

  var menuPairs = [
    { btn: $('p-head-more'), menu: $('p-head-menu') },
    { btn: $('p-sort-btn'), menu: $('p-sort-menu') },
    { btn: $('p-add-btn'), menu: $('p-add-menu') },
    { btn: $('p-github-more'), menu: $('p-github-menu') },
    { btn: accountBtn, menu: accountMenu }
  ];

  function getMenuItems(menu) {
    return toArray(menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]'))
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
    pair.menu.addEventListener('click', function (event) {
      var item = event.target.closest('[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]');
      if (!item || !pair.menu.contains(item)) return;
      handleMenuItem(item, pair);
    });
  });

  accountMenu.addEventListener('click', closeMenus);

  document.addEventListener('click', function (event) {
    if (!event.target.closest('.p-wrap, #p-account-wrap')) closeMenus();
  });

  /* ---------------------------- directory ---------------------------- */

  var search = $('p-search');
  var searchClear = $('p-search-clear');
  var filterButtons = toArray(document.querySelectorAll('.p-filter'));
  var rows = toArray(document.querySelectorAll('.p-plugin-row'));
  var sections = toArray(document.querySelectorAll('.p-section[data-section]'));
  var categoryButtons = toArray(document.querySelectorAll('.p-category'));
  var categoryBanner = $('p-category-banner');
  var categoryBannerName = $('p-category-banner-name');
  var categoryClear = $('p-category-clear');
  var noResults = $('p-no-results');
  var clearFilters = $('p-clear-filters');
  var sortMenu = $('p-sort-menu');

  var state = {
    query: '',
    type: 'all',
    category: null,
    sort: 'default',
    verifiedOnly: false,
    expanded: { 'your': true, 'most': true, 'popular': true, 'trending': true, 'new': true, 'categories': true }
  };

  function matchesFilters(row) {
    var haystack = (attr(row, 'name') + ' ' + attr(row, 'desc') + ' ' + attr(row, 'meta')).toLowerCase();
    if (state.query && haystack.indexOf(state.query) === -1) return false;
    var type = attr(row, 'type');
    if (state.type === 'connector' && type.indexOf('connector') === -1) return false;
    if (state.type === 'skill' && type.indexOf('skill') === -1) return false;
    if (state.category) {
      var categories = attr(row, 'categories').split('|');
      if (categories.indexOf(state.category) === -1) return false;
    }
    if (state.verifiedOnly && attr(row, 'verified') !== 'true') return false;
    return true;
  }

  function applyFilters() {
    var total = 0;
    var counts = {};
    rows.forEach(function (row) {
      var section = row.closest('.p-section');
      var key = section ? section.getAttribute('data-section') : '';
      var show = state.expanded[key] !== false && matchesFilters(row);
      row.hidden = !show;
      if (show) {
        total += 1;
        counts[key] = (counts[key] || 0) + 1;
      }
    });

    var filtering = !!(state.query || state.type !== 'all' || state.category || state.verifiedOnly);
    sections.forEach(function (section) {
      var key = section.getAttribute('data-section');
      var grid = section.querySelector('.p-grid, .p-cat-grid');
      if (grid) grid.hidden = state.expanded[key] === false;
      if (key !== 'categories') section.hidden = filtering && !counts[key];
    });

    noResults.hidden = !(filtering && total === 0);
    searchClear.hidden = !state.query;
    categoryBanner.hidden = !state.category;
    if (state.category) categoryBannerName.textContent = state.category;
    categoryButtons.forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-category') === state.category));
    });
  }

  function applySort() {
    toArray(document.querySelectorAll('.p-grid')).forEach(function (grid) {
      var list = toArray(grid.querySelectorAll('.p-plugin-row'));
      list.sort(function (a, b) {
        if (state.sort === 'name-asc') return attr(a, 'name').localeCompare(attr(b, 'name'));
        if (state.sort === 'name-desc') return attr(b, 'name').localeCompare(attr(a, 'name'));
        return Number(attr(a, 'order')) - Number(attr(b, 'order'));
      });
      list.forEach(function (row) { grid.appendChild(row); });
    });
  }

  search.addEventListener('input', function () {
    state.query = search.value.trim().toLowerCase();
    applyFilters();
  });
  searchClear.addEventListener('click', function () {
    search.value = '';
    state.query = '';
    applyFilters();
    search.focus();
  });

  filterButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      state.type = button.getAttribute('data-filter');
      filterButtons.forEach(function (item) {
        var active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      applyFilters();
    });
  });

  toArray(document.querySelectorAll('[data-section-toggle]')).forEach(function (button) {
    button.addEventListener('click', function () {
      var key = button.getAttribute('data-section-toggle');
      state.expanded[key] = !state.expanded[key];
      button.setAttribute('aria-expanded', String(state.expanded[key]));
      applyFilters();
    });
  });

  categoryButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      var category = button.getAttribute('data-category');
      state.category = state.category === category ? null : category;
      applyFilters();
    });
  });

  categoryClear.addEventListener('click', function () {
    state.category = null;
    applyFilters();
  });

  clearFilters.addEventListener('click', resetDirectory);

  function resetDirectory() {
    state.query = '';
    state.type = 'all';
    state.category = null;
    state.sort = 'default';
    state.verifiedOnly = false;
    search.value = '';
    filterButtons.forEach(function (item) {
      var active = item.getAttribute('data-filter') === 'all';
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', String(active));
    });
    toArray(sortMenu.querySelectorAll('[data-sort]')).forEach(function (item) {
      item.setAttribute('aria-checked', String(item.getAttribute('data-sort') === 'default'));
    });
    var verifiedItem = sortMenu.querySelector('[data-flag="verified"]');
    if (verifiedItem) verifiedItem.setAttribute('aria-checked', 'false');
    toArray(document.querySelectorAll('[data-section-toggle]')).forEach(function (button) {
      state.expanded[button.getAttribute('data-section-toggle')] = true;
      button.setAttribute('aria-expanded', 'true');
    });
    applySort();
    applyFilters();
  }

  function browseCategories() {
    state.expanded.categories = true;
    var toggle = $('p-categories-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    applyFilters();
    var section = $('p-section-categories');
    if (section && typeof section.scrollIntoView === 'function') {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (categoryButtons.length) categoryButtons[0].focus();
  }

  function copyPageLink() {
    var url = window.location.href.split('#')[0];
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () {
        showToast('Page link copied.');
      }, function () {
        showInfo('Copy page link', 'Copy this address: ' + url, null);
      });
    } else {
      showInfo('Copy page link', 'Copy this address: ' + url, null);
    }
  }

  /* ------------------------------ dialogs ------------------------------ */

  var pluginModal = $('p-modal');
  var pluginCard = pluginModal.querySelector('.p-modal-card');
  var modalTile = $('p-modal-tile');
  var modalTitle = $('p-modal-title');
  var modalMeta = $('p-modal-meta');
  var modalDesc = $('p-modal-desc');
  var modalConfirm = $('p-modal-confirm');
  var addToKeel = $('p-add-to-keel');
  var addModal = $('p-add-modal');
  var addCard = addModal.querySelector('.p-modal-card');
  var activeModal = null;
  var lastFocused = null;

  function openDialog(modal, focus) {
    lastFocused = document.activeElement;
    activeModal = modal;
    modal.hidden = false;
    (focus || modal.querySelector('.p-modal-close')).focus();
  }

  function closeDialog() {
    if (!activeModal) return;
    activeModal.hidden = true;
    activeModal = null;
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
  }

  function openPluginDialog(row) {
    var tile = row.querySelector('.p-tile');
    modalTitle.textContent = attr(row, 'name');
    modalMeta.textContent = attr(row, 'meta');
    modalDesc.textContent = attr(row, 'desc');
    if (tile) {
      modalTile.className = tile.className;
      modalTile.textContent = tile.textContent;
    }
    modalConfirm.hidden = true;
    modalConfirm.textContent = '';
    addToKeel.disabled = false;
    addToKeel.textContent = 'Add to Keel';
    openDialog(pluginModal, $('p-modal-close'));
  }

  rows.forEach(function (row) {
    var button = row.querySelector('.p-plugin-main');
    if (button) button.addEventListener('click', function () { openPluginDialog(row); });
  });

  addToKeel.addEventListener('click', function () {
    var name = modalTitle.textContent;
    addToKeel.disabled = true;
    addToKeel.textContent = '✓ Added to Keel';
    modalConfirm.textContent = name + ' has been added to Keel.';
    modalConfirm.hidden = false;
    showToast(name + ' added to Keel.');
  });

  function openAddDialog() { openDialog(addModal, $('p-add-close')); }

  $('p-modal-close').addEventListener('click', closeDialog);
  $('p-modal-cancel').addEventListener('click', closeDialog);
  $('p-modal-backdrop').addEventListener('click', closeDialog);
  $('p-add-close').addEventListener('click', closeDialog);
  $('p-add-cancel').addEventListener('click', closeDialog);
  $('p-add-backdrop').addEventListener('click', closeDialog);

  [pluginCard, addCard].forEach(function (card) {
    card.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab') return;
      var focusable = toArray(card.querySelectorAll('a[href], button:not([disabled])'))
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
  });

  /* --------------------------- menu actions --------------------------- */

  function handleMenuItem(item, pair) {
    var action = item.getAttribute('data-action');
    var sort = item.getAttribute('data-sort');
    var flag = item.getAttribute('data-flag');

    if (action === 'refresh') {
      resetDirectory();
      showInfo('Directory refreshed', 'The Keel plugin directory is up to date.', null);
    } else if (action === 'submit') {
      showInfo('Submit a plugin', 'Share your connector or skill with the Keel community. Submissions are reviewed before listing.', '/download');
    } else if (action === 'copy') {
      copyPageLink();
    } else if (action === 'add-plugin') {
      openAddDialog();
    } else if (action === 'browse-categories') {
      browseCategories();
    } else if (action === 'plugin-info') {
      var row = rows.filter(function (candidate) {
        return attr(candidate, 'name') === item.getAttribute('data-plugin');
      })[0];
      if (row) openPluginDialog(row);
    } else if (action === 'manage-connection') {
      showInfo('Manage connection', 'GitHub is connected to Keel. Connection settings live in the app.', '/app');
    } else if (action === 'remove-plugin') {
      showInfo('Remove plugin', 'Disconnect GitHub from the Keel app to remove it from your plugins.', '/app');
    } else if (sort) {
      state.sort = sort;
      toArray(sortMenu.querySelectorAll('[data-sort]')).forEach(function (option) {
        option.setAttribute('aria-checked', String(option === item));
      });
      applySort();
    } else if (flag === 'verified') {
      state.verifiedOnly = item.getAttribute('aria-checked') !== 'true';
      item.setAttribute('aria-checked', String(state.verifiedOnly));
      applyFilters();
      /* keep this menu open so the choice can be reversed immediately */
      return;
    }

    closeMenus();
    if (pair && activeModal === null) pair.btn.focus();
  }

  /* ---------------------------- global escape --------------------------- */

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    if (activeModal) { closeDialog(); return; }

    var openPair = null;
    menuPairs.forEach(function (pair) {
      if (!pair.menu.hidden) openPair = pair;
    });
    if (openPair) { closeMenus(); openPair.btn.focus(); return; }

    if (!searchWrap.hidden && document.activeElement === searchInput) {
      closeRecentsSearch(true);
      return;
    }
    if (!state.query && !infoPanel.hidden) hideInfo();
  });

  applySort();
  applyFilters();
})();

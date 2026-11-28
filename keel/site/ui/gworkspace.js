/* ===========================================================================
   Keel for Google Workspace — page enhancements.
   Vanilla, local-only, no network calls. Every control has a real in-page
   action or a real site destination (/login, /download, existing routes).
   Each handler is guarded so a missing element never stops the rest of the
   page. Motion is rAF throttled, passive, transform-based and reduced-motion
   aware.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('gworkspace-page')) {
    return;
  }

  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }
  function byId(id) { return document.getElementById(id); }
  function all(selector, root) {
    return Array.prototype.slice.call(
      (root || document).querySelectorAll(selector)
    );
  }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

  var motionQuery = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null;
  function reducedMotion() { return !!(motionQuery && motionQuery.matches); }

  function scrollToElement(el) {
    if (!el || typeof el.scrollIntoView !== 'function') return;
    try {
      el.scrollIntoView({
        behavior: reducedMotion() ? 'auto' : 'smooth',
        block: 'start'
      });
    } catch (error) { el.scrollIntoView(); }
  }

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* private mode */ }
  }

  /* -------------------------- In-page scrolling --------------------------- */
  function initScrollLinks() {
    all('[data-scroll]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        var target = byId(link.getAttribute('data-scroll'));
        if (!target) return;
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        scrollToElement(target);
        if (window.history && typeof window.history.replaceState === 'function') {
          window.history.replaceState(null, '', '#' + target.id);
        }
      });
    });

    var hash = window.location.hash ? window.location.hash.slice(1) : '';
    if (hash) {
      var landing = byId(hash);
      if (landing) window.setTimeout(function () { scrollToElement(landing); }, 0);
    }
  }

  /* -------------------------- Spreadsheet cells --------------------------- */
  function initSheetCells() {
    var cells = all('.s-cell');
    var ref = byId('cellRef');
    var formula = byId('formulaValue');
    var status = byId('sheetStatus');
    if (!cells.length) return;
    cells.forEach(function (cell) {
      cell.addEventListener('click', function () {
        cells.forEach(function (other) { other.classList.remove('is-selected'); });
        cell.classList.add('is-selected');
        if (ref) ref.textContent = cell.getAttribute('data-cell') || '';
        if (formula) formula.textContent = cell.getAttribute('data-value') || '';
        if (status) {
          status.textContent = 'Selected ' + (cell.getAttribute('data-cell') || 'cell') +
            '. Value: ' + (cell.getAttribute('data-value') || '—') + '.';
        }
      });
    });
  }

  /* --------------------------- Spreadsheet tabs --------------------------- */
  function setSheetTab(name) {
    var tabs = all('[data-sheet-tab]');
    tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-sheet-tab') === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    all('[data-sheet-panel]').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-sheet-panel') !== name;
    });
  }
  function initSheetTabs() {
    all('[data-sheet-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        setSheetTab(tab.getAttribute('data-sheet-tab'));
        var status = byId('sheetStatus');
        if (status) status.textContent = 'Switched to the ' + tab.textContent.trim() + ' sheet.';
      });
    });
  }

  /* ---------------------------- Panel tabs -------------------------------- */
  function setPanelTab(name) {
    var tabs = all('[data-panel-tab]');
    tabs.forEach(function (tab) {
      var active = tab.getAttribute('data-panel-tab') === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    all('[data-panel-view]').forEach(function (view) {
      view.hidden = view.getAttribute('data-panel-view') !== name;
    });
  }
  function initPanelTabs() {
    all('[data-panel-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        setPanelTab(tab.getAttribute('data-panel-tab'));
      });
    });
  }

  /* ------------------------- Change suggestions --------------------------- */
  function initSuggestions() {
    var status = byId('sheetStatus');
    var cards = all('[data-suggest]');
    cards.forEach(function (card) {
      var name = card.getAttribute('data-suggest');
      var text = card.querySelector('.s-suggest-text');
      var editor = card.querySelector('.s-suggest-edit');
      var input = editor ? editor.querySelector('textarea') : null;
      var editButton = all('[data-edit]', card)[0];

      function setEditing(open) {
        if (editor) editor.hidden = !open;
        if (editButton) editButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open && input && typeof input.focus === 'function') {
          input.focus({ preventScroll: true });
        }
      }

      var accept = all('[data-accept]', card)[0];
      if (accept) {
        accept.addEventListener('click', function () {
          if (card.classList.contains('is-applied')) return;
          var message = 'Change accepted.';
          var cellId = card.getAttribute('data-target-cell');
          var targetValue = card.getAttribute('data-target-value') || '';
          if (cellId) {
            var cell = all('.s-cell').filter(function (item) {
              return item.getAttribute('data-cell') === cellId;
            })[0];
            if (cell) {
              cell.textContent = targetValue;
              cell.setAttribute('data-value', targetValue);
              cell.classList.add('is-changed');
              if (byId('cellRef')) byId('cellRef').textContent = cellId;
              if (byId('formulaValue')) byId('formulaValue').textContent = targetValue;
              message = 'Change accepted: ' + cellId + ' updated.';
            }
          }
          var targetId = card.getAttribute('data-target-id');
          var targetNode = targetId ? byId(targetId) : null;
          if (targetNode) {
            targetNode.textContent = targetValue;
            message = 'Change accepted: Notes sheet updated.';
          }
          card.classList.add('is-applied');
          all('button', card).forEach(function (button) {
            if (button.classList.contains('s-accept') || button.classList.contains('s-edit')) {
              button.disabled = true;
            }
          });
          setEditing(false);
          if (status) status.textContent = message;
        });
      }

      if (editButton) {
        editButton.addEventListener('click', function () {
          if (card.classList.contains('is-applied')) return;
          setEditing(!!editor && editor.hidden);
        });
      }
      var cancel = all('[data-cancel]', card)[0];
      if (cancel) {
        cancel.addEventListener('click', function () {
          setEditing(false);
          if (status) status.textContent = 'Edit canceled. No change applied.';
        });
      }
      var save = all('[data-save]', card)[0];
      if (save) {
        save.addEventListener('click', function () {
          if (!input || !text) return;
          var next = String(input.value || '').trim();
          if (!next) {
            if (status) status.textContent = 'Add some text before saving.';
            return;
          }
          text.textContent = next;
          setEditing(false);
          if (status) status.textContent = 'Suggestion wording saved. Review it before accepting.';
        });
      }
    });
  }

  /* --------------------------- Preview reset ------------------------------ */
  function initPreviewReset() {
    var reset = document.querySelector('[data-reset-sheet]');
    if (!reset) return;
    var originals = all('.s-cell').map(function (cell) {
      return { cell: cell, value: cell.getAttribute('data-value') || cell.textContent };
    });
    var suggestionTexts = all('[data-suggest]').map(function (card) {
      var text = card.querySelector('.s-suggest-text');
      var input = card.querySelector('.s-suggest-edit textarea');
      return { card: card, text: text, input: input,
        label: text ? text.textContent : '',
        value: input ? input.value : '' };
    });
    var notes = byId('notesSummary');
    var notesOriginal = notes ? notes.textContent : '';

    reset.addEventListener('click', function () {
      originals.forEach(function (item) {
        item.cell.textContent = item.value;
        item.cell.setAttribute('data-value', item.value);
        item.cell.classList.remove('is-changed');
        item.cell.classList.remove('is-selected');
      });
      var first = originals.filter(function (item) {
        return item.cell.getAttribute('data-cell') === 'D2';
      })[0];
      if (first) first.cell.classList.add('is-selected');
      if (byId('cellRef')) byId('cellRef').textContent = 'D2';
      if (byId('formulaValue')) byId('formulaValue').textContent = first ? first.value : '';
      suggestionTexts.forEach(function (item) {
        item.card.classList.remove('is-applied');
        if (item.text) item.text.textContent = item.label;
        if (item.input) item.input.value = item.value;
        var editor = item.card.querySelector('.s-suggest-edit');
        if (editor) editor.hidden = true;
        all('button', item.card).forEach(function (button) { button.disabled = false; });
        var editButton = item.card.querySelector('[data-edit]');
        if (editButton) editButton.setAttribute('aria-expanded', 'false');
      });
      if (notes) notes.textContent = notesOriginal;
      setSheetTab('q3');
      setPanelTab('suggestions');
      var status = byId('sheetStatus');
      if (status) status.textContent = 'Preview reset. No changes were saved.';
    });
  }

  /* ------------------------------- dialogs -------------------------------- */
  var lastFocus = null;
  function openModal(id) {
    var modal = byId(id);
    if (!modal) return;
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add('gw-modal-open');
    var close = modal.querySelector('.l-modal-close');
    if (close && typeof close.focus === 'function') {
      window.setTimeout(function () { close.focus({ preventScroll: true }); }, 0);
    }
  }
  function closeModal(id) {
    var modal = byId(id);
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (!all('.gw-modal').some(function (node) { return !node.hidden; })) {
      document.body.classList.remove('gw-modal-open');
    }
    if (lastFocus && typeof lastFocus.focus === 'function') {
      window.setTimeout(function () { lastFocus.focus({ preventScroll: true }); }, 0);
    }
  }
  function initModals() {
    all('[data-modal-close]').forEach(function (button) {
      button.addEventListener('click', function () {
        closeModal(button.getAttribute('data-modal-close'));
      });
    });
    document.addEventListener('keydown', function (event) {
      if (!event || (event.key !== 'Escape' && event.key !== 'Esc')) return;
      all('.gw-modal').forEach(function (modal) {
        if (!modal.hidden) closeModal(modal.id);
      });
    });
  }
  function initTryButtons() {
    all('[data-try]').forEach(function (button) {
      button.addEventListener('click', function () { openModal('tryDialog'); });
    });
  }

  /* ---------------------------- Admin demo ------------------------------- */
  function initAdminDemo() {
    var show = document.querySelector('[data-admin-demo]');
    var status = byId('adminStatus');
    var steps = all('[data-admin-step]');
    if (show) {
      show.addEventListener('click', function () { openModal('adminDialog'); });
    }
    steps.forEach(function (step) {
      step.addEventListener('click', function () {
        var done = step.getAttribute('aria-pressed') === 'true';
        step.setAttribute('aria-pressed', done ? 'false' : 'true');
        var completed = all('[data-admin-step]').filter(function (item) {
          return item.getAttribute('aria-pressed') === 'true';
        }).length;
        if (status) {
          status.textContent = completed + ' of ' + steps.length +
            ' steps reviewed. This checklist is local to your browser.';
        }
      });
    });
  }

  /* --------------------------- Learn more cards --------------------------- */
  function initLearnMore() {
    all('[data-learn]').forEach(function (button) {
      var target = byId(button.getAttribute('aria-controls'));
      var label = button.firstChild;
      button.addEventListener('click', function () {
        var open = button.getAttribute('aria-expanded') !== 'true';
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (target) target.hidden = !open;
        if (label && label.nodeType === 3) {
          label.nodeValue = open ? 'Show less ' : 'Learn more ';
        }
      });
    });
  }

  /* ---------------------------- FAQ accordion ----------------------------- */
  function initAccordion() {
    var items = all('.s-acc-item');
    if (!items.length) return;
    items.forEach(function (item) {
      var button = item.querySelector('.s-acc-btn');
      var panel = item.querySelector('.s-acc-panel');
      if (!button) return;
      button.addEventListener('click', function () {
        var willOpen = button.getAttribute('aria-expanded') !== 'true';
        items.forEach(function (other) {
          var otherButton = other.querySelector('.s-acc-btn');
          var otherPanel = other.querySelector('.s-acc-panel');
          var otherOpen = other === item && willOpen;
          other.classList.toggle('is-open', otherOpen);
          if (otherButton) otherButton.setAttribute('aria-expanded', otherOpen ? 'true' : 'false');
          if (otherPanel) {
            otherPanel.setAttribute('aria-hidden', otherOpen ? 'false' : 'true');
            otherPanel.hidden = !otherOpen;
          }
        });
      });
    });
  }

  /* ---------------------------- Mega navigation --------------------------- */
  function initMegaMenus() {
    var triggers = all('.l-nav-trigger[aria-controls]');
    if (!triggers.length) return;
    var openTimer = null;
    var closeTimer = null;

    function clearTimers() {
      if (openTimer !== null) { window.clearTimeout(openTimer); openTimer = null; }
      if (closeTimer !== null) { window.clearTimeout(closeTimer); closeTimer = null; }
    }
    function itemFor(trigger) {
      return typeof trigger.closest === 'function'
        ? trigger.closest('.l-nav-item') : trigger.parentNode;
    }
    function setMega(trigger, open) {
      var item = itemFor(trigger);
      if (!item) return;
      var id = trigger.getAttribute('aria-controls');
      var mega = id ? byId(id) : null;
      item.classList.toggle('is-open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (mega) mega.setAttribute('aria-hidden', open ? 'false' : 'true');
    }
    function closeAll() {
      clearTimers();
      triggers.forEach(function (trigger) { setMega(trigger, false); });
    }
    function openOne(trigger) {
      clearTimers();
      triggers.forEach(function (other) {
        if (other !== trigger) setMega(other, false);
      });
      setMega(trigger, true);
    }

    triggers.forEach(function (trigger) {
      var item = itemFor(trigger);
      trigger.addEventListener('click', function () {
        if (item && item.classList.contains('is-open')) {
          clearTimers();
          setMega(trigger, false);
        } else {
          openOne(trigger);
        }
      });
      if (!item) return;
      item.addEventListener('mouseenter', function () {
        clearTimers();
        openTimer = window.setTimeout(function () { openOne(trigger); }, 60);
      });
      item.addEventListener('mouseleave', function () {
        clearTimers();
        closeTimer = window.setTimeout(function () { setMega(trigger, false); }, 140);
      });
    });

    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === 'function' &&
          target.closest('.l-nav-item')) return;
      closeAll();
    });
    document.addEventListener('keydown', function (event) {
      if (event && (event.key === 'Escape' || event.key === 'Esc')) closeAll();
    });
  }

  /* --------------------------- Mobile navigation -------------------------- */
  function initMobileNav() {
    var toggle = byId('navToggle');
    var menu = byId('mobileMenu');
    if (!toggle || !menu) return;
    function setOpen(open) {
      menu.hidden = !open;
      menu.classList.toggle('is-open', open);
      toggle.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    }
    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });
    all('a, button', menu).forEach(function (link) {
      link.addEventListener('click', function () { setOpen(false); });
    });
    document.addEventListener('keydown', function (event) {
      if (event && (event.key === 'Escape' || event.key === 'Esc')) setOpen(false);
    });
  }

  /* ---------------------------- Footer search ----------------------------- */
  function initFooterSearch() {
    var input = byId('footerSearch');
    if (!input) return;
    var status = byId('searchStatus');
    var statusText = byId('searchStatusText');
    var clear = byId('clearSearch');
    var links = all('.l-footer-col a');
    var questions = all('.s-acc-item');
    var form = typeof input.closest === 'function' ? input.closest('form') : null;

    function applyFilter() {
      var needle = String(input.value || '').trim().toLowerCase();
      var matches = 0;
      links.forEach(function (link) {
        var match = !needle ||
          String(link.textContent || '').toLowerCase().indexOf(needle) !== -1;
        link.hidden = !match;
        if (match) matches += 1;
      });
      questions.forEach(function (item) {
        var question = item.querySelector('.s-acc-q');
        var match = !needle ||
          String(question ? question.textContent : item.textContent || '')
            .toLowerCase().indexOf(needle) !== -1;
        item.hidden = !match;
      });
      if (status) status.hidden = !needle;
      if (statusText && needle) {
        statusText.textContent = matches
          ? matches + ' matching link' + (matches === 1 ? '' : 's')
          : 'No matching links';
      }
    }
    input.addEventListener('input', applyFilter);
    if (form) {
      form.addEventListener('submit', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        applyFilter();
        var footer = byId('footer');
        if (footer) scrollToElement(footer);
      });
    }
    if (clear) {
      clear.addEventListener('click', function () {
        input.value = '';
        applyFilter();
        input.focus();
      });
    }
  }

  /* ---------------------------- Language picker --------------------------- */
  function initLanguage() {
    var select = byId('languageSelect');
    if (!select) return;
    var stored = storageGet('keel_gworkspace_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      var label = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text : select.value;
      document.documentElement.lang = select.value;
      storageSet('keel_gworkspace_language', select.value);
      select.setAttribute('aria-label', 'Language: ' + label + ' (saved)');
    });
  }

  /* --------------------- Reveals + parallax + sticky ---------------------- */
  function initReveals() {
    var nodes = all('.s-reveal');
    if (!nodes.length || reducedMotion() || !('IntersectionObserver' in window)) {
      return; /* Content stays visible without JS support. */
    }
    document.body.classList.add('s-animate');
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    nodes.forEach(function (node) { observer.observe(node); });
  }

  function initScrollEffects() {
    var header = document.querySelector('.l-header');
    var card = document.querySelector('.s-sheet-card');
    var pending = false;

    function update() {
      pending = false;
      var y = window.scrollY;
      if (typeof y !== 'number') {
        y = window.pageYOffset || document.documentElement.scrollTop || 0;
      }
      if (header) header.classList.toggle('is-scrolled', y > 16);
      if (reducedMotion() || !card) return;
      var rect = card.getBoundingClientRect();
      if (rect.bottom < -80 || rect.top > window.innerHeight + 80) return;
      var shift = (rect.top + rect.height / 2 - window.innerHeight / 2) * -0.012;
      card.style.setProperty('--gw-shift', clamp(shift, -6, 6).toFixed(1) + 'px');
    }
    function onScroll() {
      if (pending) return;
      pending = true;
      window.requestAnimationFrame(update);
    }

    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
  }

  /* -------------------------------- Boot -------------------------------- */
  function init() {
    safe(initScrollLinks);
    safe(initSheetCells);
    safe(initSheetTabs);
    safe(initPanelTabs);
    safe(initSuggestions);
    safe(initPreviewReset);
    safe(initModals);
    safe(initTryButtons);
    safe(initAdminDemo);
    safe(initLearnMore);
    safe(initAccordion);
    safe(initMegaMenus);
    safe(initMobileNav);
    safe(initFooterSearch);
    safe(initLanguage);
    safe(initReveals);
    safe(initScrollEffects);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

/* ===========================================================================
   Keel Science page enhancements — vanilla, local-only, no network calls.
   Every control has a real in-page action or a real destination (/login and
   the other site routes). Handlers are guarded so a missing element never
   stops the rest of the page.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('science-page')) {
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
  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); return true; }
    catch (error) { return false; }
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
        block: 'center'
      });
    } catch (error) { el.scrollIntoView(); }
  }

  function toast(message) {
    var node = document.createElement('div');
    node.className = 's-toast';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.textContent = message || 'Done.';
    document.body.appendChild(node);
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 3200);
  }

  /* ----------------------------- Modal helper ---------------------------- */
  function openModal(title, paragraphs, options) {
    var config = options || {};
    var previousFocus = document.activeElement;
    var overlay = document.createElement('div');
    overlay.className = 's-modal-overlay';

    var card = document.createElement('div');
    card.className = 's-modal';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', title || 'Keel Science');

    var closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 's-modal-close';
    closeButton.setAttribute('aria-label', 'Close');
    closeButton.textContent = '\u00d7';

    var heading = document.createElement('h2');
    heading.textContent = title || 'Keel Science';

    (paragraphs || []).forEach(function (text) {
      var p = document.createElement('p');
      p.textContent = text;
      card.appendChild(p);
    });

    if (config.visual) {
      var visual = document.createElement('div');
      visual.className = 's-storyboard';
      visual.textContent = config.visual;
      card.insertBefore(visual, card.firstChild);
    }

    if (config.actions) {
      var actions = document.createElement('div');
      actions.className = 's-modal-actions';
      config.actions.forEach(function (action) {
        var el = document.createElement(action.href ? 'a' : 'button');
        if (action.href) el.href = action.href;
        else el.type = 'button';
        el.className = 's-modal-btn' + (action.ghost ? ' s-modal-btn-ghost' : '');
        el.textContent = action.label;
        if (action.onClick) el.addEventListener('click', action.onClick);
        actions.appendChild(el);
      });
      card.appendChild(actions);
    }

    card.insertBefore(heading, card.firstChild);
    card.insertBefore(closeButton, card.firstChild);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
      if (config.onClose) config.onClose();
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      document.removeEventListener('keydown', onKeydown);
      if (previousFocus && typeof previousFocus.focus === 'function' &&
          document.contains(previousFocus)) {
        previousFocus.focus();
      }
    }
    function onKeydown(event) {
      var key = event && event.key;
      if (key === 'Escape' || key === 'Esc') {
        event.preventDefault();
        close();
        return;
      }
      if (key !== 'Tab') return;
      var focusables = all(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        card
      );
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    closeButton.addEventListener('click', close);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close();
    });
    document.addEventListener('keydown', onKeydown);
    closeButton.focus();
    return { close: close, card: card };
  }

  /* --------------------------- Announcement ------------------------------ */
  var ANNOUNCEMENT = [
    'Keel Science walks with you through every step of the research process, ' +
    'from the first idea to the final publication.',
    'Search the literature, follow citations, open the code behind a method, ' +
    'analyse your data, and build figures — with the sources attached to the work.',
    'Keel Science is available to everyone. Start with a question and keep ' +
    'going as far as the research takes you.'
  ];

  function initAnnouncement() {
    all('[data-announcement]').forEach(function (button) {
      button.addEventListener('click', function () {
        openModal('Introducing Keel Science', ANNOUNCEMENT, {
          actions: [{ label: 'Start research', href: '/login' }]
        });
      });
    });
  }

  /* ------------------------- Floating chat card -------------------------- */
  function initChat() {
    var reply = byId('science-reply');
    var toggle = document.querySelector('[data-show-reply]');
    var prompt = document.querySelector('[data-chat-prompt]');
    if (!reply || !toggle) return;

    function setOpen(open) {
      reply.hidden = !open;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.textContent = open ? 'Hide reply' : 'Show reply';
    }

    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });
    if (prompt) {
      prompt.addEventListener('click', function () {
        setOpen(true);
        if (typeof reply.scrollIntoView === 'function') {
          try { reply.scrollIntoView({ block: 'nearest' }); }
          catch (error) { /* scrolling is an enhancement only */ }
        }
      });
    }
  }

  /* --------------------------- Video walkthrough ------------------------- */
  var FRAMES = [
    { label: '1 / 4 · Start with a question', text: 'Ask what the field already knows.' },
    { label: '2 / 4 · Read the literature', text: 'Follow citations to their source papers.' },
    { label: '3 / 4 · Analyse and visualize', text: 'Turn your data into a clear, captioned figure.' },
    { label: '4 / 4 · Write it up', text: 'Draft the result with every claim sourced.' }
  ];

  function openVideoModal() {
    var index = 0;
    var timer = null;
    var visiblePlay = null;
    var frame = document.createElement('div');
    frame.className = 's-storyboard';
    var caption = document.createElement('p');
    caption.setAttribute('role', 'status');
    caption.setAttribute('aria-live', 'polite');

    function render() {
      frame.textContent = FRAMES[index].label;
      caption.textContent = FRAMES[index].text;
    }
    function stop() {
      if (timer !== null) { window.clearTimeout(timer); timer = null; }
      if (visiblePlay) visiblePlay.textContent = 'Play';
    }
    function toggle() {
      if (timer !== null) { stop(); return; }
      if (index >= FRAMES.length - 1) index = -1;
      if (visiblePlay) visiblePlay.textContent = 'Pause';
      advance();
    }
    function advance() {
      if (index >= FRAMES.length - 1) { stop(); return; }
      index += 1;
      render();
      timer = window.setTimeout(advance, 1500);
    }

    var dialog = openModal('Keel Science walkthrough', [], {
      actions: [
        { label: 'Play' },
        { label: 'Next step', ghost: true },
        { label: 'Get started', href: '/login' }
      ],
      onClose: stop
    });

    var actions = all('.s-modal-actions .s-modal-btn', dialog.card);
    visiblePlay = actions[0] || null;
    if (visiblePlay) visiblePlay.addEventListener('click', toggle);
    if (actions[1]) {
      actions[1].addEventListener('click', function () {
        stop();
        index = (index + 1) % FRAMES.length;
        render();
      });
    }
    var insertAt = dialog.card.querySelector('.s-modal-actions');
    dialog.card.insertBefore(frame, insertAt);
    dialog.card.insertBefore(caption, insertAt);
    render();
  }

  function initVideo() {
    var play = document.querySelector('[data-video-play]');
    if (play) play.addEventListener('click', openVideoModal);
  }

  /* ------------------------------ Tab groups ----------------------------- */
  function bindTabs(tabs, onSelect) {
    function select(tab) {
      tabs.forEach(function (other) {
        var active = other === tab;
        other.setAttribute('aria-selected', active ? 'true' : 'false');
        other.tabIndex = active ? 0 : -1;
        var panel = byId(other.getAttribute('aria-controls'));
        if (panel) panel.hidden = !active;
      });
      if (onSelect) onSelect(tab);
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { select(tab); });
      tab.addEventListener('keydown', function (event) {
        var key = event && event.key;
        if (key !== 'ArrowRight' && key !== 'ArrowLeft' &&
            key !== 'ArrowDown' && key !== 'ArrowUp') return;
        event.preventDefault();
        var step = (key === 'ArrowRight' || key === 'ArrowDown') ? 1 : -1;
        var next = tabs[(i + step + tabs.length) % tabs.length];
        select(next);
        next.focus();
      });
    });
    select(tabs[0]);
  }

  function initPaperTabs() {
    var tabs = all('[data-paper-tab]');
    if (tabs.length) bindTabs(tabs);
  }
  function initWorkflowTabs() {
    var tabs = all('[data-workflow]');
    if (tabs.length) bindTabs(tabs);
  }

  /* ------------------------------- Draft demo ---------------------------- */
  function initDraft() {
    var button = document.querySelector('[data-draft]');
    var output = byId('draft-output');
    if (!button || !output) return;
    button.addEventListener('click', function () {
      var open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      output.hidden = !open;
      if (open) toast('Draft outline added below the prompt.');
    });
  }

  /* ---------------------- Figures, stories, integrations ----------------- */
  var FIGURES = {
    'Study overview': 'A one-page map of the question, methods, and findings, kept alongside the paper.',
    'Spectral analysis': 'A peak comparison across conditions with the original labels preserved.',
    'Field notes': 'Observations from the field, linked to the passage that motivated them.',
    'Cited literature': 'The papers behind a claim, opened without losing your place in the draft.',
    'Lab notebook': 'A dated record of protocol changes and results for the current experiment.'
  };
  var STORIES = {
    'anna': [
      'Anna is a doctoral candidate reviewing a fast-moving field. She starts each ' +
      'morning by asking Keel Science what changed since her last read.',
      'The answers point back to the original papers, so she can check every ' +
      'claim before it enters her thesis.'
    ],
    'dimitris': [
      'Dimitris is a postdoc reproducing published methods. He follows citations ' +
      'from a paper to its repository and reads the code beside the method section.',
      'That shortens the distance between an interesting result and a working ' +
      'analysis in his own lab.'
    ],
    'ug': [
      'A research group uses Keel Science to turn rough experiment ideas into a ' +
      'protocol the whole team can comment on.',
      'Figures and captions stay attached to the data, which makes lab meetings ' +
      'shorter and decisions easier to document.'
    ]
  };
  var INTEGRATIONS = {
    'arXiv': 'Find preprints and follow new versions as a field moves.',
    'GitHub': 'Open the code referenced by a paper and reproduce the analysis.',
    'Zotero': 'Bring your existing library and citations into the same workflow.',
    'Google Scholar': 'Trace a citation trail across the literature you already search.',
    'Python': 'Work from the scripts and notebooks behind your data.',
    'Jupyter': 'Inspect and adapt analysis notebooks without leaving your project.'
  };
  var MODELS = {
    'Literature search': 'Search across papers and preprints, with links back to each source.',
    'Data analysis': 'Explore a dataset, check an assumption, and build a clear plot.',
    'Experiment design': 'Turn a question into a protocol with variables and controls.',
    'Publication': 'Shape the write-up around the evidence you actually collected.'
  };

  function initFigures() {
    all('[data-figure]').forEach(function (button) {
      button.addEventListener('click', function () {
        var name = button.getAttribute('data-figure') || 'Research figure';
        openModal(name, [FIGURES[name] || 'A figure from a research project.'], {
          actions: [{ label: 'Work with your figures', href: '/login' }]
        });
      });
    });
  }
  function initStories() {
    all('[data-story]').forEach(function (button) {
      button.addEventListener('click', function () {
        var who = button.getAttribute('data-story') || 'anna';
        openModal('Research story · @' + who, STORIES[who] || STORIES.anna, {
          actions: [{ label: 'Start research', href: '/login' }]
        });
      });
    });
  }
  function initIntegrations() {
    all('[data-integration]').forEach(function (button) {
      button.addEventListener('click', function () {
        var name = button.getAttribute('data-integration') || 'Keel Science';
        openModal(name, [INTEGRATIONS[name] || 'Connect your research tools in Keel.'], {
          actions: [
            { label: 'Get started', href: '/login' },
            { label: 'More integrations', href: '/plugins', ghost: true }
          ]
        });
      });
    });
  }
  function initModelInfo() {
    all('[data-model]').forEach(function (button) {
      button.addEventListener('click', function () {
        var name = button.getAttribute('data-model') || 'Research with Keel';
        openModal(name, [MODELS[name] || MODELS['Literature search']], {
          actions: [{ label: 'Get started', href: '/login' }]
        });
      });
    });
  }

  /* --------------------------- FAQ accordion ----------------------------- */
  function initAccordion() {
    var items = all('.s-acc-item');
    if (!items.length) return;

    function setState(item, open) {
      var button = item.querySelector('.s-acc-btn');
      var panel = item.querySelector('.s-acc-panel');
      item.classList.toggle('is-open', open);
      if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (panel) {
        panel.setAttribute('aria-hidden', open ? 'false' : 'true');
        panel.style.maxHeight = open ? panel.scrollHeight + 'px' : '0px';
      }
    }

    items.forEach(function (item) {
      var button = item.querySelector('.s-acc-btn');
      if (!button) return;
      setState(item, item.classList.contains('is-open'));
      button.addEventListener('click', function () {
        var willOpen = !item.classList.contains('is-open');
        items.forEach(function (other) {
          if (other !== item) setState(other, false);
        });
        setState(item, willOpen);
      });
    });

    var resizePending = false;
    window.addEventListener('resize', function () {
      if (resizePending) return;
      resizePending = true;
      window.requestAnimationFrame(function () {
        resizePending = false;
        items.forEach(function (item) {
          if (!item.classList.contains('is-open')) return;
          var panel = item.querySelector('.s-acc-panel');
          if (panel) panel.style.maxHeight = panel.scrollHeight + 'px';
        });
      });
    }, { passive: true });
  }

  /* --------------------------- Mega navigation --------------------------- */
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

  /* --------------------------- Mobile navigation ------------------------- */
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

  /* -------------------------- Footer FAQ search -------------------------- */
  function initFooterSearch() {
    var input = byId('s-footer-search');
    if (!input) return;
    var status = byId('searchStatus');
    var statusText = byId('searchStatusText');
    var clear = byId('clearSearch');
    var empty = byId('s-search-empty');
    var items = all('.s-acc-item');

    function applyFilter() {
      var needle = String(input.value || '').trim().toLowerCase();
      var matches = 0;
      items.forEach(function (item) {
        var question = item.querySelector('.s-acc-q');
        var text = question ? question.textContent : item.textContent;
        var match = !needle || String(text || '').toLowerCase().indexOf(needle) !== -1;
        item.hidden = !match;
        if (match) matches += 1;
      });
      if (empty) empty.hidden = !(needle && matches === 0);
      if (status) status.hidden = !needle;
      if (statusText && needle) {
        statusText.textContent = matches
          ? matches + ' matching question' + (matches === 1 ? '' : 's')
          : 'No matching questions';
      }
    }

    input.addEventListener('input', applyFilter);
    var form = typeof input.closest === 'function' ? input.closest('form') : null;
    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        applyFilter();
        scrollToElement(byId('faq'));
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

  /* ---------------------------- Language picker -------------------------- */
  function initLanguage() {
    var select = byId('languageSelect');
    if (!select) return;
    var stored = storageGet('keel_science_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_science_language', select.value);
      var label = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text : select.value;
      toast('Language preference saved: ' + label);
    });
  }

  /* --------------------- Reveals + parallax + sticky --------------------- */
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
    var card = document.querySelector('.s-chat-card');
    var pending = false;

    function update() {
      pending = false;
      var y = window.scrollY;
      if (typeof y !== 'number') {
        y = window.pageYOffset || document.documentElement.scrollTop || 0;
      }
      if (header) header.classList.toggle('is-scrolled', y > 16);
      if (reducedMotion() || !card) return;
      var r = card.getBoundingClientRect();
      if (r.bottom > -80 && r.top < window.innerHeight + 80) {
        var shift = (r.top + r.height / 2 - window.innerHeight / 2) * -0.03;
        card.style.setProperty('--science-card-shift',
          clamp(shift, -8, 8).toFixed(1) + 'px');
      }
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
    safe(initAnnouncement);
    safe(initChat);
    safe(initVideo);
    safe(initPaperTabs);
    safe(initWorkflowTabs);
    safe(initDraft);
    safe(initFigures);
    safe(initStories);
    safe(initIntegrations);
    safe(initModelInfo);
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

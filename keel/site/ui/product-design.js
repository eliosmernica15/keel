/* ===========================================================================
   Keel Design page enhancements — vanilla, local-only, no network calls.
   Every control has a real in-page action or a real site destination
   (/login and the existing routes). Handlers are guarded so a missing
   element never stops the rest of the page.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('design-page')) {
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
  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); return true; }
    catch (error) { return false; }
  }

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
    node.className = 'd-toast';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.textContent = message || 'Done.';
    document.body.appendChild(node);
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 3200);
  }

  function appendArrow(button) {
    var arrow = document.createElement('span');
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '→';
    button.appendChild(arrow);
  }

  /* ------------------------- Frontier work tabs --------------------------- */
  function selectDesignTab(tab, tabs) {
    tabs.forEach(function (other) {
      var active = other === tab;
      other.setAttribute('aria-selected', active ? 'true' : 'false');
      other.tabIndex = active ? 0 : -1;
      var panel = byId(other.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
    });
  }

  function initDesignTabs() {
    var tabs = all('[data-design-tab]');
    if (!tabs.length) return;
    selectDesignTab(tabs[0], tabs);
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () { selectDesignTab(tab, tabs); });
      tab.addEventListener('keydown', function (event) {
        var key = event && event.key;
        if (key !== 'ArrowRight' && key !== 'ArrowLeft' &&
            key !== 'ArrowDown' && key !== 'ArrowUp') return;
        event.preventDefault();
        var index = tabs.indexOf(tab);
        var step = (key === 'ArrowRight' || key === 'ArrowDown') ? 1 : -1;
        var next = tabs[(index + step + tabs.length) % tabs.length];
        selectDesignTab(next, tabs);
        next.focus();
      });
    });
  }

  /* --------------------- Mega menu demo shortcuts ------------------------- */
  function initNavDemos() {
    var demos = all('[data-model]');
    if (!demos.length) return;
    var tabMap = {
      product: 'product',
      marketing: 'marketing',
      brand: 'brand',
      system: 'product'
    };
    demos.forEach(function (button) {
      button.addEventListener('click', function () {
        var name = tabMap[button.getAttribute('data-model')] || 'product';
        var tab = document.querySelector('[data-design-tab="' + name + '"]');
        if (tab && typeof tab.click === 'function') tab.click();
        scrollToElement(byId('frontier'));
      });
    });
  }

  /* --------------------------- Hero chat card ----------------------------- */
  function initHeroChat() {
    var reply = byId('d-chat-reply');
    var ask = document.querySelector('[data-hero-chat]');
    if (!reply || !ask) return;

    function open(text) {
      if (text) {
        var paragraph = reply.querySelector('p');
        if (paragraph) paragraph.textContent = text;
      }
      reply.hidden = false;
      ask.setAttribute('aria-expanded', 'true');
      ask.textContent = 'Ask another question';
      appendArrow(ask);
    }

    ask.addEventListener('click', function () {
      open('Pick a starting point, describe the outcome, and Keel Design ' +
           'builds a first version inside your design tool.');
    });
    all('[data-chat-chip]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        open('Working on ' + (chip.getAttribute('data-chat-chip') || 'that idea') +
             '. Here is a first direction using your components and tokens.');
      });
    });
  }

  /* ------------------------- Keel Code prompts ---------------------------- */
  function initCodePrompts() {
    all('[data-code-prompt]').forEach(function (button) {
      var output = byId(button.getAttribute('aria-controls'));
      button.addEventListener('click', function () {
        var willOpen = !output || output.hidden;
        if (output) output.hidden = !willOpen;
        button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      });
    });
  }

  /* ------------------------ Customer story cards ------------------------- */
  function initStories() {
    all('[data-story]').forEach(function (button) {
      var more = byId(button.getAttribute('aria-controls'));
      button.addEventListener('click', function () {
        var willOpen = !more || more.hidden;
        if (more) more.hidden = !willOpen;
        button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        var label = button.textContent || '';
        button.textContent = willOpen
          ? label.replace('Read the full story', 'Hide full story')
          : label.replace('Hide full story', 'Read the full story');
        appendArrow(button);
      });
    });
  }

  /* --------------------------- FAQ accordion ----------------------------- */
  function initAccordion() {
    var items = all('.d-acc-item');
    if (!items.length) return;

    function setState(item, open) {
      var button = item.querySelector('.d-acc-btn');
      var panel = item.querySelector('.d-acc-panel');
      item.classList.toggle('is-open', open);
      if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (panel) {
        panel.setAttribute('aria-hidden', open ? 'false' : 'true');
        panel.style.maxHeight = open ? panel.scrollHeight + 'px' : '0px';
      }
    }

    items.forEach(function (item) {
      var button = item.querySelector('.d-acc-btn');
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
          var panel = item.querySelector('.d-acc-panel');
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
    var input = byId('d-footer-search');
    if (!input) return;
    var status = byId('searchStatus');
    var statusText = byId('searchStatusText');
    var clear = byId('clearSearch');
    var empty = byId('d-search-empty');
    var items = all('.d-acc-item');

    function applyFilter() {
      var needle = String(input.value || '').trim().toLowerCase();
      var matches = 0;
      items.forEach(function (item) {
        var question = item.querySelector('.d-acc-q');
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
    var stored = storageGet('keel_design_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_design_language', select.value);
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
    var cards = all('.d-parallax');
    var pending = false;

    function update() {
      pending = false;
      var y = window.scrollY;
      if (typeof y !== 'number') {
        y = window.pageYOffset || document.documentElement.scrollTop || 0;
      }
      if (header) header.classList.toggle('is-scrolled', y > 16);
      if (reducedMotion()) return;
      cards.forEach(function (card) {
        var depth = parseFloat(card.getAttribute('data-depth')) || 1;
        var rect = card.getBoundingClientRect();
        if (rect.bottom < -80 || rect.top > window.innerHeight + 80) return;
        var shift = (rect.top + rect.height / 2 - window.innerHeight / 2) * -0.02 * depth;
        card.style.setProperty('--d-shift', clamp(shift, -8, 8).toFixed(1) + 'px');
      });
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
    safe(initDesignTabs);
    safe(initNavDemos);
    safe(initHeroChat);
    safe(initCodePrompts);
    safe(initStories);
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

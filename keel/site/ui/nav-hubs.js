/* ===========================================================================
   Keel top-nav hubs — progressive enhancement for /developers, /enterprise
   and /resources. No inline handlers, no network calls, no data URIs.
   Everything marked "local" stays in the browser and nothing is sent.
   =========================================================================== */
(function () {
  'use strict';

  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function byId(id) { return document.getElementById(id); }
  function safe(fn) {
    return function () {
      try { return fn.apply(this, arguments); }
      catch (error) { /* Enhancement only; the page works without it. */ }
    };
  }
  function reducedMotion() {
    if (!window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function storageGet(key) {
    try { return window.localStorage ? window.localStorage.getItem(key) : null; }
    catch (error) { return null; }
  }
  function storageSet(key, value) {
    try { if (window.localStorage) window.localStorage.setItem(key, value); }
    catch (error) { /* Private mode or disabled storage: still works locally. */ }
  }
  function setHidden(node, hidden) {
    if (!node) return;
    if (hidden) node.setAttribute('hidden', '');
    else node.removeAttribute('hidden');
  }

  /* ------------------------------- mega menu ------------------------------- */
  function initMegaMenus() {
    var items = all('.l-nav-item[data-menu]');
    if (!items.length) return;

    function close(item) {
      var trigger = item.querySelector('.l-nav-trigger');
      var panel = item.querySelector('.l-mega');
      item.classList.remove('is-open');
      if (panel) {
        panel.classList.remove('is-open');
        panel.setAttribute('aria-hidden', 'true');
      }
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }
    function closeAll(except) {
      items.forEach(function (item) { if (item !== except) close(item); });
    }
    function open(item) {
      closeAll(item);
      var trigger = item.querySelector('.l-nav-trigger');
      var panel = item.querySelector('.l-mega');
      item.classList.add('is-open');
      if (panel) {
        panel.classList.add('is-open');
        panel.setAttribute('aria-hidden', 'false');
      }
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
    }

    items.forEach(function (item) {
      var trigger = item.querySelector('.l-nav-trigger');
      var panel = item.querySelector('.l-mega');
      if (!trigger || !panel) return;

      trigger.addEventListener('click', function (event) {
        event.preventDefault();
        var expanded = trigger.getAttribute('aria-expanded') === 'true';
        if (expanded) close(item); else open(item);
      });
      item.addEventListener('mouseenter', function () { open(item); });
      item.addEventListener('mouseleave', function () { close(item); });
      item.addEventListener('focusout', function (event) {
        if (!item.contains(event.relatedTarget)) close(item);
      });
      panel.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          close(item);
          if (trigger && typeof trigger.focus === 'function') trigger.focus();
        }
      });
    });

    document.addEventListener('click', function (event) {
      if (!event.target.closest('.l-nav-item[data-menu]')) closeAll(null);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeAll(null);
    });
  }

  /* ------------------------------ mobile menu ------------------------------ */
  function initMobileMenu() {
    var toggle = document.querySelector('.l-nav-toggle');
    var menu = byId('mobileMenu');
    if (!toggle || !menu) return;

    function setOpen(open) {
      setHidden(menu, !open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    }
    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });
    all('a', menu).forEach(function (link) {
      link.addEventListener('click', function () { setOpen(false); });
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setOpen(false);
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 980) setOpen(false);
    }, { passive: true });
  }

  /* --------------------------------- tabs ---------------------------------- */
  function initTabs() {
    var tabs = all('[data-nh-tab]');
    if (!tabs.length) return;

    function select(tab, focus) {
      var group = tab.closest('[data-nh-tabs]');
      var siblings = all('[data-nh-tab]', group || document);
      siblings.forEach(function (sibling) {
        var selected = sibling === tab;
        sibling.setAttribute('aria-selected', selected ? 'true' : 'false');
        sibling.setAttribute('tabindex', selected ? '0' : '-1');
        var panel = byId(sibling.getAttribute('aria-controls'));
        setHidden(panel, !selected);
      });
      if (focus && typeof tab.focus === 'function') tab.focus();
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () { select(tab, false); });
      tab.addEventListener('keydown', function (event) {
        var group = tab.closest('[data-nh-tabs]');
        var siblings = all('[data-nh-tab]', group || document);
        var index = siblings.indexOf(tab);
        var next = null;
        if (event.key === 'ArrowRight') next = siblings[(index + 1) % siblings.length];
        if (event.key === 'ArrowLeft') next = siblings[(index - 1 + siblings.length) % siblings.length];
        if (event.key === 'Home') next = siblings[0];
        if (event.key === 'End') next = siblings[siblings.length - 1];
        if (!next) return;
        event.preventDefault();
        select(next, true);
      });
    });
  }

  /* ------------------------------- accordion ------------------------------- */
  function initAccordion() {
    var buttons = all('.nh-acc-btn');
    if (!buttons.length) return;
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var panel = byId(button.getAttribute('aria-controls'));
        var open = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', open ? 'false' : 'true');
        setHidden(panel, open);
      });
    });
  }

  /* -------------------------------- copy button ---------------------------- */
  function initCopyButtons() {
    var buttons = all('[data-nh-copy]');
    if (!buttons.length) return;

    function legacyCopy(text) {
      var field = document.createElement('textarea');
      field.value = text;
      field.setAttribute('readonly', '');
      field.style.position = 'absolute';
      field.style.left = '-9999px';
      document.body.appendChild(field);
      field.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (error) { ok = false; }
      document.body.removeChild(field);
      return ok;
    }

    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var block = button.closest('.nh-code');
        var code = block ? block.querySelector('code') : null;
        var status = block ? block.querySelector('.nh-code-status') : null;
        if (!code) return;
        var text = code.textContent;
        var original = button.textContent;

        function finish(ok) {
          var message = ok
            ? 'Copied to your clipboard on this device. Nothing sent.'
            : 'Copy failed — select the code manually. Nothing sent.';
          if (status) status.textContent = message;
          button.textContent = ok ? 'Copied' : 'Try again';
          window.setTimeout(function () {
            button.textContent = original;
          }, 1800);
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () { finish(true); }, function () {
            finish(legacyCopy(text));
          });
        } else {
          finish(legacyCopy(text));
        }
      });
    });
  }

  /* -------------------------- local-only quickstart ------------------------ */
  function initQuickstartForm() {
    var form = document.querySelector('[data-nh-form="quickstart"]');
    if (!form) return;
    var input = form.querySelector('[data-nh-input]');
    var output = form.querySelector('[data-nh-output]');
    var status = form.querySelector('[data-nh-status]');
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (!input || !output) return;
      var name = (input.value || 'my-app').trim().toLowerCase()
        .replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'my-app';
      output.textContent = 'Local preview · project: ' + name + ' · no request made · nothing saved.';
      if (status) status.textContent = 'Preview created in this browser. Nothing sent or saved.';
    });
  }

  /* --------------------------- local-only selection ------------------------ */
  function initChoiceForm() {
    var form = document.querySelector('[data-nh-form="choice"]');
    if (!form) return;
    var select = form.querySelector('select');
    var status = form.querySelector('[data-nh-status]');
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (!status) return;
      var value = select && select.value ? select.value : 'default';
      status.textContent = 'Selection "' + value + '" stays on this page. Nothing sent.';
    });
  }

  /* --------------------- local-only page/footer search --------------------- */
  function initLocalSearch() {
    var forms = all('[data-nh-search]');
    var cards = all('[data-nh-searchable]');
    if (!forms.length || !cards.length) return;

    function apply(query, statusNode) {
      var needle = (query || '').trim().toLowerCase();
      var shown = 0;
      cards.forEach(function (card) {
        var haystack = (card.textContent || '').toLowerCase();
        var match = !needle || haystack.indexOf(needle) !== -1;
        setHidden(card, !match);
        if (match) shown += 1;
      });
      if (statusNode) {
        var message = needle
          ? 'Showing ' + shown + ' of ' + cards.length + ' items on this page. Nothing sent.'
          : 'Showing all ' + cards.length + ' items. Nothing sent.';
        var label = statusNode.id === 'searchStatus' ? byId('searchStatusText') : null;
        if (label) label.textContent = message;
        else statusNode.textContent = message;
        setHidden(statusNode, false);
      }
    }

    forms.forEach(function (form) {
      var input = form.querySelector('input[type="search"]');
      var status = form.parentNode.querySelector(form.getAttribute('data-nh-search'));
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        apply(input ? input.value : '', status);
      });
      if (input) {
        input.addEventListener('input', function () {
          if (!input.value) apply('', status);
        });
      }
      var clear = form.parentNode.querySelector('#clearSearch');
      if (clear) {
        clear.addEventListener('click', function () {
          if (input) input.value = '';
          apply('', status);
        });
      }
    });
  }

  /* -------------------------------- language -------------------------------- */
  function initLanguage() {
    var select = byId('languageSelect');
    var status = byId('nh-lang-status');
    if (!select) return;
    var stored = storageGet('keel_navhubs_language');
    if (stored && all('option', select).some(function (option) { return option.value === stored; })) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_navhubs_language', select.value);
      var option = select.options[select.selectedIndex];
      if (status) {
        status.textContent = 'Language set to ' + (option ? option.text : select.value) +
          ' in this browser. Nothing sent.';
      }
    });
  }

  /* --------------------------- reveals + sticky ----------------------------- */
  function initReveals() {
    var nodes = all('.nh-reveal');
    if (!nodes.length || reducedMotion() || !('IntersectionObserver' in window)) {
      return; /* Content stays visible without JS support. */
    }
    document.body.classList.add('nh-animate');
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
    if (!header) return;
    var pending = false;
    function update() {
      pending = false;
      var y = window.scrollY;
      if (typeof y !== 'number') y = window.pageYOffset || document.documentElement.scrollTop || 0;
      header.classList.toggle('is-scrolled', y > 16);
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

  /* ---------------------------------- boot ---------------------------------- */
  function init() {
    safe(initMegaMenus)();
    safe(initMobileMenu)();
    safe(initTabs)();
    safe(initAccordion)();
    safe(initCopyButtons)();
    safe(initQuickstartForm)();
    safe(initChoiceForm)();
    safe(initLocalSearch)();
    safe(initLanguage)();
    safe(initReveals)();
    safe(initScrollEffects)();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

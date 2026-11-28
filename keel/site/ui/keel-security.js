/* ===========================================================================
   Keel Security page enhancements — vanilla, local-only, no network calls.
   Every handler is guarded so a missing element never stops the rest of the
   page. Motion is opt-in: reveals only run when IntersectionObserver exists
   and the visitor has not asked for reduced motion.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('security-page')) {
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

  var motionQuery = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null;
  function reducedMotion() { return !!(motionQuery && motionQuery.matches); }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

  function scrollToElement(el) {
    if (!el || typeof el.scrollIntoView !== 'function') return;
    try {
      el.scrollIntoView({
        behavior: reducedMotion() ? 'auto' : 'smooth',
        block: 'center'
      });
    } catch (error) { el.scrollIntoView(); }
  }

  /* ---------------------------- Toast helper ---------------------------- */
  function toast(message) {
    var node = document.createElement('div');
    node.className = 'ks-toast';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.textContent = message || 'Done.';
    document.body.appendChild(node);
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 3500);
  }

  /* ----------------------------- Modal helper ---------------------------- */
  function openModal(title, paragraphs, options) {
    var previousFocus = document.activeElement;
    var opts = options || {};
    var overlay = document.createElement('div');
    overlay.className = 'ks-modal-overlay';

    var backdrop = document.createElement('button');
    backdrop.type = 'button';
    backdrop.className = 'ks-modal-backdrop';
    backdrop.setAttribute('aria-label', 'Close dialog');

    var card = document.createElement('div');
    card.className = 'ks-modal';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', title || 'Keel Security');

    var closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'ks-modal-close';
    closeButton.setAttribute('aria-label', 'Close');
    closeButton.textContent = '\u00d7';

    var heading = document.createElement('h2');
    heading.textContent = title || 'Keel Security';
    card.appendChild(closeButton);
    card.appendChild(heading);

    (paragraphs || []).forEach(function (text) {
      var p = document.createElement('p');
      p.textContent = text;
      card.appendChild(p);
    });

    if (opts.code) {
      var code = document.createElement('code');
      code.textContent = opts.code;
      card.appendChild(code);
    }

    if (opts.action && opts.action.href && opts.action.label) {
      var action = document.createElement('a');
      action.className = 'ks-btn ks-btn-dark ks-modal-action';
      action.href = opts.action.href;
      action.textContent = opts.action.label;
      card.appendChild(action);
    }

    overlay.appendChild(backdrop);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
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
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
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
    backdrop.addEventListener('click', close);
    document.addEventListener('keydown', onKeydown);
    closeButton.focus();
  }

  /* --------------------------- Mega navigation --------------------------- */
  function initMegaMenus() {
    var triggers = all('.ks-nav-trigger[aria-controls]');
    if (!triggers.length) return;
    var openTimer = null;
    var closeTimer = null;

    function clearTimers() {
      if (openTimer !== null) { window.clearTimeout(openTimer); openTimer = null; }
      if (closeTimer !== null) { window.clearTimeout(closeTimer); closeTimer = null; }
    }
    function itemFor(trigger) {
      return typeof trigger.closest === 'function'
        ? trigger.closest('.ks-nav-item') : trigger.parentNode;
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
          target.closest('.ks-nav-item')) return;
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

  /* ---------------------------- FAQ accordion ---------------------------- */
  function initAccordion() {
    var items = all('.ks-acc-item');
    if (!items.length) return;

    function setState(item, open) {
      var button = item.querySelector('.ks-acc-btn');
      var panel = item.querySelector('.ks-acc-panel');
      item.classList.toggle('is-open', open);
      if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (panel) {
        panel.setAttribute('aria-hidden', open ? 'false' : 'true');
        panel.style.maxHeight = open ? panel.scrollHeight + 'px' : '0px';
      }
    }

    items.forEach(function (item) {
      var button = item.querySelector('.ks-acc-btn');
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
          var panel = item.querySelector('.ks-acc-panel');
          if (panel) panel.style.maxHeight = panel.scrollHeight + 'px';
        });
      });
    }, { passive: true });
  }

  /* -------------------------- Announcement modal ------------------------- */
  function initAnnouncement() {
    var buttons = all('[data-announcement]');
    if (!buttons.length) return;
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        openModal('Keel Security public beta', [
          'Keel scans your codebase with Keel Mythos, validates real risks in ' +
          'context, and suggests and tracks fixes for your approval.',
          'This capability is available in public beta for Keel Enterprise. ' +
          'Contact sales to ask about access for your team.'
        ], {
          action: { href: '/resources/articles', label: 'Read the blog' }
        });
      });
    });
  }

  /* ----------------------- Floating card: Show issue --------------------- */
  function initShowIssue() {
    var button = document.querySelector('[data-show-issue]');
    var band = byId('data-flow');
    if (!button) return;
    button.addEventListener('click', function () {
      if (band) {
        scrollToElement(band);
        band.classList.add('is-flash');
        window.setTimeout(function () { band.classList.remove('is-flash'); }, 900);
      }
      toast('Example issue: an untrusted login value reaches password recovery.');
    });
  }

  /* --------------------------- Copy the snippet -------------------------- */
  function initCopyFlow() {
    var button = document.querySelector('[data-copy-flow]');
    var code = byId('flowCode');
    if (!button || !code) return;
    button.addEventListener('click', function () {
      var text = String(code.textContent || '').trim();
      function fallback() {
        var field = document.createElement('textarea');
        field.value = text;
        field.setAttribute('readonly', 'readonly');
        field.style.position = 'fixed';
        field.style.opacity = '0';
        document.body.appendChild(field);
        field.select();
        var copied = false;
        try { copied = document.execCommand('copy'); } catch (error) { copied = false; }
        if (field.parentNode) field.parentNode.removeChild(field);
        toast(copied ? 'Snippet copied to clipboard.' : 'Select the snippet to copy it.');
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          toast('Snippet copied to clipboard.');
        }, fallback);
      } else {
        fallback();
      }
    });
  }

  /* ---------------------- Badge, video and resource cards ---------------- */
  function initProofCards() {
    var award = document.querySelector('[data-award]');
    if (award) {
      award.addEventListener('click', function () {
        openModal('Y Combinator award', [
          'This badge reproduces the award-style element in the design ' +
          'reference; it is not a claim about Keel.',
          'For verified company news, open Keel News.'
        ], { action: { href: '/notices', label: 'Open Keel News' } });
      });
    }

    var video = document.querySelector('[data-video="beta-launch"]');
    if (video) {
      video.addEventListener('click', function () {
        openModal('Beta launch about Keel Security video', [
          'This page does not host video. The preview panel is a static ' +
          'stand-in for the layout in the design reference.',
          'For announcements about the Keel Security public beta, open ' +
          'Keel News or contact sales.'
        ], { action: { href: '/notices', label: 'Open Keel News' } });
      });
    }
  }

  function initResources() {
    var cards = all('.ks-resource-card[data-resource]');
    if (!cards.length) return;
    var KEY = 'keel_security_resources';
    cards.forEach(function (card) {
      card.addEventListener('click', function () {
        var name = card.getAttribute('data-resource') || 'resource';
        var stored = storageGet(KEY);
        var recent = [];
        if (stored) {
          try { recent = JSON.parse(stored) || []; } catch (error) { recent = []; }
        }
        if (!Array.isArray(recent)) recent = [];
        recent = recent.filter(function (item) { return item !== name; });
        recent.unshift(name);
        storageSet(KEY, JSON.stringify(recent.slice(0, 8)));
        /* The real href navigates; the handler only remembers the selection. */
      });
    });
  }

  /* -------------------------- Footer FAQ search -------------------------- */
  function initFaqSearch() {
    var input = byId('ks-footer-search');
    if (!input) return;
    var status = byId('searchStatus');
    var statusText = byId('searchStatusText');
    var clear = byId('clearSearch');
    var empty = byId('faqEmpty');
    var items = all('.ks-acc-item');

    function applyFilter() {
      var needle = String(input.value || '').trim().toLowerCase();
      var matches = 0;
      items.forEach(function (item) {
        var question = item.querySelector('.ks-acc-q');
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
    var stored = storageGet('keel_security_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_security_language', select.value);
      var label = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text : select.value;
      toast('Language preference saved: ' + label);
    });
  }

  /* ---------------------- Reveals, parallax and sticky ------------------- */
  function initReveals() {
    var nodes = all('.ks-reveal');
    if (!nodes.length || reducedMotion() || !('IntersectionObserver' in window)) {
      return; /* Content stays visible without JS support. */
    }
    document.body.classList.add('ks-animate');
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
    var header = byId('siteHeader');
    var card = byId('floatCard');
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
        var shift = (r.top + r.height / 2 - window.innerHeight / 2) * -0.025;
        card.style.setProperty('--ks-card-shift',
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
    safe(initMegaMenus);
    safe(initMobileNav);
    safe(initAccordion);
    safe(initAnnouncement);
    safe(initShowIssue);
    safe(initCopyFlow);
    safe(initProofCards);
    safe(initResources);
    safe(initFaqSearch);
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

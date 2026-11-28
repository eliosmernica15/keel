/* ===========================================================================
   Keel Skills page enhancements — vanilla, local-only, no network calls.
   Every control has a real in-page action or a real site destination
   (/login, /download, the existing product routes and this page's sections).
   Handlers are guarded so a missing element never stops the rest of the page.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('skills-page')) {
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
        block: 'start'
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
    }, 3000);
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

  /* --------------------------- Hero document tabs ------------------------- */
  function initFileTabs() {
    var tabs = all('[data-file-tab]');
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var name = tab.getAttribute('data-file-tab');
        tabs.forEach(function (other) {
          var active = other === tab;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        all('[data-file-panel]').forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-file-panel') !== name;
        });
      });
    });
  }

  function copyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', 'readonly');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try {
        var ok = document.execCommand('copy');
        ok ? resolve() : reject(new Error('copy failed'));
      } catch (error) { reject(error); }
      if (area.parentNode) area.parentNode.removeChild(area);
    });
  }

  /* ------------------------------ Copy buttons ---------------------------- */
  function initCopyButtons() {
    all('[data-copy]').forEach(function (button) {
      button.addEventListener('click', function () {
        var id = button.getAttribute('data-copy');
        var visible = id === 'doc-copy'
          ? all('[data-file-panel]').filter(function (panel) { return !panel.hidden; })[0]
          : null;
        var source = visible || byId(id);
        if (!source) return;
        var raw = source.textContent || '';
        var text = source.tagName === 'PRE'
          ? raw.trim()
          : raw.replace(/\s+/g, ' ').trim();
        copyText(text).then(function () {
          toast('Copied to clipboard');
          var original = button.textContent;
          button.textContent = 'Copied';
          window.setTimeout(function () { button.textContent = original; }, 1600);
        }).catch(function () {
          toast('Copy is unavailable in this browser');
        });
      });
    });
  }

  /* --------------------------- Hero build action -------------------------- */
  function initHeroBuild() {
    var button = document.querySelector('[data-hero-build]');
    var status = byId('s-hero-status');
    if (!button || !status) return;
    button.addEventListener('click', function () {
      var added = button.getAttribute('aria-pressed') === 'true';
      button.setAttribute('aria-pressed', added ? 'false' : 'true');
      button.textContent = added ? 'Add to my skills' : 'Added to my skills';
      status.textContent = added
        ? ''
        : 'Saved locally. The skill will be offered when this task comes up again.';
    });
  }

  /* -------------------------- Benefit disclosures ------------------------- */
  function initBenefits() {
    all('[data-benefit]').forEach(function (button) {
      var panel = byId(button.getAttribute('aria-controls'));
      button.addEventListener('click', function () {
        var open = button.getAttribute('aria-expanded') === 'true';
        if (panel) panel.hidden = open;
        button.setAttribute('aria-expanded', open ? 'false' : 'true');
        var mark = button.querySelector('span');
        if (mark) mark.textContent = open ? '→' : '−';
      });
    });
  }

  /* ---------------------------- Mock card tabs ---------------------------- */
  function initMockTabs() {
    var tabs = all('[data-mock-tab]');
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var name = tab.getAttribute('data-mock-tab');
        tabs.forEach(function (other) {
          var active = other === tab;
          other.classList.toggle('is-active', active);
          other.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        var group = tab.closest('.s-mock');
        if (!group) return;
        all('[data-mock-panel]', group).forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-mock-panel') !== name;
        });
      });
    });
  }

  function initStoryFocus() {
    all('[data-story-focus]').forEach(function (button) {
      button.addEventListener('click', function () {
        var section = byId(button.getAttribute('data-story-focus'));
        if (!section) return;
        scrollToElement(section);
        var mock = section.querySelector('.s-mock');
        if (mock && typeof mock.focus === 'function') {
          mock.setAttribute('tabindex', '-1');
          mock.focus({ preventScroll: true });
        }
      });
    });
  }

  /* --------------------------- FAQ accordion ------------------------------ */
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

  /* ---------------------------- Story cards ------------------------------- */
  function initStories() {
    all('[data-story]').forEach(function (button) {
      var more = byId(button.getAttribute('aria-controls'));
      button.addEventListener('click', function () {
        var open = button.getAttribute('aria-expanded') === 'true';
        if (more) more.hidden = open;
        button.setAttribute('aria-expanded', open ? 'false' : 'true');
        button.innerHTML = (open ? 'Read the full story' : 'Hide full story') +
          ' <span aria-hidden="true">→</span>';
      });
    });
  }

  /* --------------------------- Mega navigation ---------------------------- */
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

  /* ------------------------------ Footer search --------------------------- */
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
    var stored = storageGet('keel_skills_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_skills_language', select.value);
      var label = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text : select.value;
      toast('Language preference saved: ' + label);
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
    var cards = all('.s-parallax');
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
        card.style.setProperty('--s-shift', clamp(shift, -8, 8).toFixed(1) + 'px');
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
    safe(initScrollLinks);
    safe(initFileTabs);
    safe(initCopyButtons);
    safe(initHeroBuild);
    safe(initBenefits);
    safe(initMockTabs);
    safe(initStoryFocus);
    safe(initAccordion);
    safe(initStories);
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

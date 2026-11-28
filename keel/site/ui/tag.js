/* ===========================================================================
   Keel Tag page enhancements — vanilla JS, local-only, no network calls.
   This file is the single owner of every interactive control on /product/tag.
   It never loads or expects the shared landing.js, so nothing is bound twice.
   A missing element never breaks the rest of the page; every setup is guarded.
   =========================================================================== */
(function () {
  'use strict';

  /* ------------------------------ helpers ------------------------------ */
  function qs(selector, root) {
    try { return (root || document).querySelector(selector) || null; }
    catch (error) { return null; }
  }

  function qsa(selector, root) {
    try { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    catch (error) { return []; }
  }

  function closest(node, selector) {
    if (!node || typeof node.closest !== 'function') return null;
    try { return node.closest(selector) || null; }
    catch (error) { return null; }
  }

  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function scrollToId(id) {
    if (!id) return;
    var el = document.getElementById(id);
    if (!el || typeof el.scrollIntoView !== 'function') return;
    try {
      el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
    } catch (error) {
      try { el.scrollIntoView(); } catch (ignored) { /* no scroll API */ }
    }
  }

  var reduceMotion = (function () {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)'); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  function onScrollFrame(handler) {
    var ticking = false;
    return function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () {
        ticking = false;
        handler();
      });
    };
  }

  function store(key, value) {
    try { window.localStorage.setItem(key, value); } catch (error) { /* optional */ }
  }

  function read(key) {
    try { return window.localStorage.getItem(key); } catch (error) { return null; }
  }

  /* ---------------------- 0a. Scroll reveal (IO) ----------------------- */
  function initReveal() {
    var targets = qsa('[data-reveal]');
    if (!targets.length) return;

    /* Staggered groups use a CSS custom property, never inline handlers. */
    qsa('[data-reveal-group]').forEach(function (group) {
      qsa('[data-reveal]', group).forEach(function (node, index) {
        if (!node.style || node.style.getPropertyValue('--t-reveal-delay')) return;
        node.style.setProperty('--t-reveal-delay', Math.min(index * 40, 180) + 'ms');
      });
    });

    if (prefersReducedMotion() || typeof IntersectionObserver !== 'function') {
      targets.forEach(function (node) { node.classList.add('is-revealed'); });
      return;
    }

    document.documentElement.classList.add('t-reveal-ready');
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-revealed');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    targets.forEach(function (node) { observer.observe(node); });
  }

  /* ------------- 0b. Sticky shadow + subtle hero parallax ---------- */
  function initScrollEffects() {
    var header = qs('#siteHeader, .l-header');
    var layers = qsa('[data-parallax]');
    var allowParallax = !prefersReducedMotion() && layers.length > 0;

    function update() {
      var y = window.pageYOffset || window.scrollY || 0;
      if (header && header.classList) header.classList.toggle('is-scrolled', y > 12);
      if (!allowParallax) return;
      layers.forEach(function (node) {
        var speed = parseFloat(node.getAttribute('data-parallax')) || 0;
        var offset = Math.max(-12, Math.min(12, y * speed));
        /* Transform only — no top/left or layout churn. */
        node.style.transform = 'translate3d(0,' + offset.toFixed(2) + 'px,0)';
      });
    }

    var frame = onScrollFrame(update);
    window.addEventListener('scroll', frame, { passive: true });
    window.addEventListener('resize', frame, { passive: true });
    update();

    if (reduceMotion && typeof reduceMotion.addEventListener === 'function') {
      reduceMotion.addEventListener('change', function () {
        allowParallax = !reduceMotion.matches;
        if (!allowParallax) layers.forEach(function (node) { node.style.transform = ''; });
        document.documentElement.classList.remove('t-reveal-ready');
        update();
      });
    }
  }

  /* ------------------------- 1. Toast helper ------------------------ */
  var toastTimer = null;

  function tToast(message) {
    var toast = document.getElementById('tToast');
    if (!toast) return;
    toast.textContent = String(message == null || message === '' ? 'Done.' : message);
    toast.hidden = false;
    if (toast.classList) toast.classList.add('is-visible');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      toast.hidden = true;
      if (toast.classList) toast.classList.remove('is-visible');
    }, 3200);
  }

  /* ---------------------- 2. Generic modal -------------------------- */
  var modalLastFocus = null;

  var MODAL_CONTENT = {
    teams: {
      title: 'Keel in Microsoft Teams',
      html: '<p>Ask Keel a question in any Teams channel and it answers using the projects, files and conversations your team has already shared — with links back to each source.</p>' +
        '<ul><li>Works in channel conversations and in direct messages.</li>' +
        '<li>Admins choose which channels Keel can read.</li>' +
        '<li>Every reply includes its sources so teammates can check the answer.</li></ul>' +
        '<p><a class="l-btn l-btn-dark" href="/login">Try Keel Tag</a> ' +
        '<a class="l-btn l-btn-outline" href="mailto:hello@keel.ai?subject=Keel%20in%20Microsoft%20Teams">Contact sales</a></p>'
    },
    admin: {
      title: 'Admin controls for Keel Tag',
      html: '<p>Keel Tag gives admins a single place to decide who can use Keel, where it can respond and what it can access.</p>' +
        '<ul><li>Directory sync and approvals keep membership in your directory.</li>' +
        '<li>A searchable audit log records what Keel read and wrote.</li>' +
        '<li>Allowed channels limit Keel to the conversations you choose.</li></ul>' +
        '<p><a class="l-btn l-btn-dark" href="/pricing">See Enterprise plans</a> ' +
        '<a class="l-btn l-btn-outline" href="/product/tag#admins">Back to admin controls</a></p>'
    }
  };

  function genericContent() {
    return {
      title: 'Keel Tag',
      html: '<p>Tag Keel in a thread and it joins the conversation with the context your team has already shared.</p>' +
        '<p><a class="l-btn l-btn-dark" href="/login">Get started for free</a> ' +
        '<a class="l-btn l-btn-outline" href="/product/tag#how-it-works">See how it works</a></p>'
    };
  }

  function openTModal(title, html) {
    var modal = document.getElementById('tModal');
    if (!modal) return;
    var titleEl = document.getElementById('t-modal-title');
    var bodyEl = document.getElementById('t-modal-body');
    if (titleEl) titleEl.textContent = String(title == null ? '' : title);
    if (bodyEl) bodyEl.innerHTML = String(html == null ? '' : html);
    modalLastFocus = document.activeElement;
    modal.hidden = false;
    if (modal.classList) modal.classList.add('is-open');
    document.body.classList.add('t-modal-open');
    closeMobileMenu();
    if (cMegaCloseAll) cMegaCloseAll();

    var closeButton = qs('.t-modal-close', modal);
    if (closeButton && typeof closeButton.focus === 'function') {
      try { closeButton.focus(); } catch (error) { /* focus is a nice-to-have */ }
    }
  }

  function closeTModal() {
    var modal = document.getElementById('tModal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (modal.classList) modal.classList.remove('is-open');
    document.body.classList.remove('t-modal-open');
    if (modalLastFocus && typeof document.contains === 'function' &&
        document.contains(modalLastFocus) && typeof modalLastFocus.focus === 'function') {
      try { modalLastFocus.focus(); } catch (error) { /* ignore */ }
    }
    modalLastFocus = null;
  }

  function initModalControls() {
    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;

      var trigger = target.closest('[data-modal]');
      if (trigger) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var key = trigger.getAttribute('data-modal') || '';
        var content = MODAL_CONTENT[key] || genericContent();
        openTModal(content.title, content.html);
        return;
      }

      var closer = target.closest('[data-t-close]');
      var modal = document.getElementById('tModal');
      if (closer && modal && typeof modal.contains === 'function' && modal.contains(closer)) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        closeTModal();
      }
    });

    document.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key === 'Escape' || key === 'Esc') {
        var modal = document.getElementById('tModal');
        if (modal && !modal.hidden) {
          if (event && typeof event.preventDefault === 'function') event.preventDefault();
          closeTModal();
        }
        return;
      }
      if (key !== 'Tab') return;
      var dialog = document.getElementById('tModal');
      if (!dialog || dialog.hidden) return;
      var card = qs('.t-modal-card', dialog) || dialog;
      var focusables = qsa(
        'a[href], button:not([disabled]), input:not([disabled]), ' +
        'select:not([disabled]), [tabindex]:not([tabindex="-1"])', card
      ).filter(function (node) {
        return !node.hidden && !!(node.offsetWidth || node.offsetHeight ||
          (typeof node.getClientRects === 'function' && node.getClientRects().length));
      });
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
    });
  }

  /* ------------------------- 3. Mega menus ------------------------- */
  var cMegaCloseAll = null;

  function initMegaMenus() {
    var items = qsa('.l-nav-item[data-menu]');
    if (!items.length) return;
    var openTimer = null;
    var closeTimer = null;

    function clearTimers() {
      if (openTimer !== null) { clearTimeout(openTimer); openTimer = null; }
      if (closeTimer !== null) { clearTimeout(closeTimer); closeTimer = null; }
    }

    function state(item) {
      if (!item.__tMegaState) item.__tMegaState = { pinned: false, byHover: false };
      return item.__tMegaState;
    }

    function parts(item) {
      var trigger = qs('.l-nav-trigger', item);
      var mega = null;
      if (trigger) {
        var id = trigger.getAttribute('aria-controls');
        if (id) mega = document.getElementById(id);
      }
      if (!mega) mega = qs('.l-mega', item);
      return { trigger: trigger, mega: mega };
    }

    function isOpen(item) {
      return !!(item.classList &&
        (item.classList.contains('open') || item.classList.contains('is-open')));
    }

    function setOpen(item, open) {
      var pair = parts(item);
      if (pair.trigger) {
        pair.trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (pair.trigger.classList) {
          pair.trigger.classList.toggle('open', open);
          pair.trigger.classList.toggle('is-open', open);
        }
      }
      if (item.classList) {
        item.classList.toggle('open', open);
        item.classList.toggle('is-open', open);
      }
      if (pair.mega) {
        pair.mega.setAttribute('aria-hidden', open ? 'false' : 'true');
        pair.mega.hidden = !open;
        if (pair.mega.classList) {
          pair.mega.classList.toggle('open', open);
          pair.mega.classList.toggle('is-open', open);
        }
      }
      if (!open) {
        var s = state(item);
        s.pinned = false;
        s.byHover = false;
      }
    }

    function closeAll(except) {
      items.forEach(function (item) {
        if (item !== except) setOpen(item, false);
      });
    }

    function openOne(item, byHover) {
      clearTimers();
      closeAll(item);
      setOpen(item, true);
      state(item).byHover = !!byHover;
    }

    items.forEach(function (item) {
      var pair = parts(item);
      setOpen(item, false);

      if (pair.trigger && !pair.trigger.__tMegaBound) {
        pair.trigger.__tMegaBound = true;
        /* Native button clicks already cover Enter and Space. */
        pair.trigger.addEventListener('click', function (event) {
          if (event && typeof event.preventDefault === 'function') event.preventDefault();
          var s = state(item);
          if (isOpen(item) && s.byHover && !s.pinned) {
            s.byHover = false;
            s.pinned = true;
            return;
          }
          if (isOpen(item)) {
            setOpen(item, false);
          } else {
            openOne(item, false);
            state(item).pinned = true;
          }
        });
      }

      item.addEventListener('mouseenter', function () {
        clearTimers();
        openTimer = setTimeout(function () { openOne(item, true); }, 40);
      });
      item.addEventListener('mouseleave', function () {
        clearTimers();
        closeTimer = setTimeout(function () {
          if (!state(item).pinned) setOpen(item, false);
        }, 140);
      });
      item.addEventListener('focusin', function (event) {
        if (!event || !event.target || typeof event.target.matches !== 'function') return;
        var visible = false;
        try { visible = event.target.matches(':focus-visible'); } catch (error) { visible = false; }
        if (!visible) return;
        clearTimers();
        openOne(item, false);
      });
      item.addEventListener('focusout', function (event) {
        if (state(item).pinned) return;
        var next = event && event.relatedTarget;
        if (next && typeof item.contains === 'function' && item.contains(next)) return;
        clearTimers();
        closeTimer = setTimeout(function () {
          var active = document.activeElement;
          if (active && typeof item.contains === 'function' && item.contains(active)) return;
          if (!state(item).pinned) setOpen(item, false);
        }, 120);
      });
    });

    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === 'function' && target.closest('.l-nav-item')) return;
      clearTimers();
      closeAll();
    });

    cMegaCloseAll = function () { clearTimers(); closeAll(); };
  }

  /* ------------------------- 4. Mobile menu ------------------------- */
  function initMobileMenu() {
    var toggle = document.getElementById('navToggle');
    var menu = document.getElementById('mobileMenu');
    if (!toggle || !menu || toggle.__tMobileBound) return;
    toggle.__tMobileBound = true;

    function close() {
      menu.classList.remove('open');
      menu.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open menu');
    }

    toggle.addEventListener('click', function (event) {
      if (event) event.stopPropagation();
      var willOpen = menu.hidden || !menu.classList.contains('open');
      menu.classList.toggle('open', willOpen);
      menu.hidden = !willOpen;
      toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      toggle.setAttribute('aria-label', willOpen ? 'Close menu' : 'Open menu');
    });

    menu.addEventListener('click', function (event) {
      var target = event && event.target;
      if (target && (target.closest('a') || target.closest('button'))) close();
    });
    document.addEventListener('click', function (event) {
      if (menu.hidden) return;
      var target = event && event.target;
      if (!target || !target.closest('.l-nav-inner')) close();
    });
  }

  /* ---------------------- 5. Slack thread mock ---------------------- */
  function initThread() {
    var form = document.getElementById('threadForm');
    var input = document.getElementById('threadReply');
    var extra = document.getElementById('threadExtra');

    var moreButton = qs('[data-thread-more]');
    if (moreButton && extra && !moreButton.__tThreadBound) {
      moreButton.__tThreadBound = true;
      moreButton.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var open = extra.hidden;
        extra.hidden = !open;
        moreButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        moreButton.textContent = open ? 'Hide follow-up' : 'View follow-up';
      });
    }

    var replyButton = qs('[data-thread-reply]');
    if (replyButton && input && !replyButton.__tReplyBound) {
      replyButton.__tReplyBound = true;
      replyButton.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        scrollToId('how-it-works');
        if (typeof input.focus === 'function') {
          try { input.focus({ preventScroll: true }); }
          catch (error) {
            try { input.focus(); } catch (ignored) { /* focus is optional */ }
          }
        }
        tToast('Reply composer ready — write your message below.');
      });
    }

    if (!form || !input || form.__tThreadFormBound) return;
    form.__tThreadFormBound = true;

    form.addEventListener('submit', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      var text = String(input.value || '').replace(/\s+/g, ' ').trim();
      if (!text) {
        tToast('Write a reply before sending.');
        return;
      }

      var thread = qs('.t-thread-body') || qs('.t-slack-thread');
      if (!thread) return;
      var article = document.createElement('article');
      article.className = 't-msg';
      var avatar = document.createElement('span');
      avatar.className = 't-avatar t-avatar-a';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = 'Y';
      var wrap = document.createElement('div');
      var meta = document.createElement('p');
      meta.className = 't-msg-meta';
      var name = document.createElement('strong');
      name.textContent = 'You';
      var time = document.createElement('time');
      time.textContent = 'Just now';
      meta.appendChild(name);
      meta.appendChild(time);
      var body = document.createElement('p');
      body.className = 't-msg-text';
      body.textContent = text; /* textContent — never inject user HTML */
      wrap.appendChild(meta);
      wrap.appendChild(body);
      article.appendChild(avatar);
      article.appendChild(wrap);
      thread.appendChild(article);
      input.value = '';
      tToast('Reply added to the thread.');
    });
  }

  /* ------------------- 6. How-teams-use tabs ----------------------- */
  function initUseTabs() {
    var tabs = qsa('[data-use-tab]');
    if (!tabs.length) return;

    function panelFor(tab) {
      var id = tab.getAttribute('aria-controls');
      return id ? document.getElementById(id) : null;
    }

    function select(tab, moveFocus) {
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle('is-active', active);
        other.setAttribute('aria-selected', active ? 'true' : 'false');
        other.tabIndex = active ? 0 : -1;
        var panel = panelFor(other);
        if (panel) panel.hidden = !active;
      });
      if (moveFocus && typeof tab.focus === 'function') {
        try { tab.focus(); } catch (error) { /* ignore */ }
      }
    }

    tabs.forEach(function (tab, index) {
      if (tab.__tUseBound) return;
      tab.__tUseBound = true;
      tab.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        select(tab, false);
      });
      tab.addEventListener('keydown', function (event) {
        var key = event && event.key;
        var next = -1;
        if (key === 'ArrowRight' || key === 'ArrowDown') next = (index + 1) % tabs.length;
        else if (key === 'ArrowLeft' || key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length;
        else if (key === 'Home') next = 0;
        else if (key === 'End') next = tabs.length - 1;
        if (next < 0 || next === index) return;
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        select(tabs[next], true);
      });
    });

    var initial = tabs.filter(function (tab) {
      return tab.classList && tab.classList.contains('is-active');
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ------------------- 7. Capability accordion -------------------- */
  function initCapabilities() {
    var buttons = qsa('[data-cap]');
    if (!buttons.length) return;

    function panelFor(button) {
      var id = button.getAttribute('aria-controls');
      return id ? document.getElementById(id) : null;
    }

    function setItem(button, open) {
      var panel = panelFor(button);
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (panel) panel.hidden = !open;
    }

    buttons.forEach(function (button) {
      setItem(button, false);
      if (button.__tCapBound) return;
      button.__tCapBound = true;
      button.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var open = button.getAttribute('aria-expanded') === 'true';
        buttons.forEach(function (other) {
          if (other !== button) setItem(other, false);
        });
        setItem(button, !open);
      });
    });
  }

  /* ------------------- 8. Admin toggle switches ------------------- */
  function initAdminToggles() {
    var switches = qsa('[data-admin-toggle]');
    if (!switches.length) return;

    var ROW_INDEX = { directory: 1, audit: 2, channels: 3 };
    var LABELS = {
      directory: ['Off', 'On'],
      audit: ['Off', 'On'],
      channels: ['All channels', 'Limited']
    };

    function reflect(key, on) {
      /* Row 0 is the workspace summary; the three switches map to 1-3. */
      var row = qsa('.t-admin-row', qs('.t-admin-window'))[ROW_INDEX[key] || 1];
      if (!row) return;
      var strong = qs('strong', row);
      if (!strong) return;
      var labels = LABELS[key] || ['Off', 'On'];
      strong.textContent = on ? labels[1] : labels[0];
      strong.className = on ? 't-state-on' : 't-state-off';
    }

    switches.forEach(function (button) {
      var key = button.getAttribute('data-admin-toggle') || '';
      var saved = read('keel_tag_admin_' + key);
      var initial = saved === null ? button.getAttribute('aria-pressed') === 'true' : saved === '1';
      button.setAttribute('aria-pressed', initial ? 'true' : 'false');
      reflect(key, initial);

      if (button.__tAdminBound) return;
      button.__tAdminBound = true;
      button.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var on = button.getAttribute('aria-pressed') !== 'true';
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
        store('keel_tag_admin_' + key, on ? '1' : '0');
        reflect(key, on);
        tToast((key === 'channels' ? 'Allowed channels' : key === 'audit' ? 'Audit log' : 'Directory sync') +
          (on ? ' enabled.' : ' disabled.'));
      });
    });
  }

  /* ---------------------- 9. Copy buttons -------------------------- */
  function legacyCopy(text, button) {
    var textarea = document.createElement('textarea');
    textarea.value = String(text);
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    try {
      document.body.appendChild(textarea);
      textarea.select();
      if (typeof document.execCommand === 'function') document.execCommand('copy');
    } catch (error) { /* best effort only */ }
    if (textarea.parentNode) textarea.parentNode.removeChild(textarea);
    markCopied(button);
  }

  function markCopied(button) {
    if (!button) return;
    if (button.__tCopyTimer) {
      clearTimeout(button.__tCopyTimer);
      button.__tCopyTimer = null;
    }
    if (typeof button.__tCopyLabel !== 'string') button.__tCopyLabel = button.textContent || 'Copy';
    button.textContent = 'Copied';
    tToast('Link copied to clipboard.');
    button.__tCopyTimer = setTimeout(function () {
      button.__tCopyTimer = null;
      button.textContent = button.__tCopyLabel || 'Copy';
    }, 1800);
  }

  function initCopy() {
    document.addEventListener('click', function (event) {
      var button = closest(event && event.target, '[data-copy]');
      if (!button) return;
      event.preventDefault();
      var text = button.getAttribute('data-copy') || '';
      if (!text) return;
      if (typeof navigator !== 'undefined' && navigator.clipboard &&
          typeof navigator.clipboard.writeText === 'function') {
        var promise = null;
        try { promise = navigator.clipboard.writeText(text); } catch (error) { promise = null; }
        if (promise && typeof promise.then === 'function') {
          promise.then(function () { markCopied(button); }, function () { legacyCopy(text, button); });
          return;
        }
        markCopied(button);
        return;
      }
      legacyCopy(text, button);
    });
  }

  /* ---------------------- 10. Footer help search ------------------ */
  function initHelpSearch() {
    var form = document.getElementById('helpForm');
    var input = document.getElementById('helpSearch');
    var status = document.getElementById('searchStatus');
    var statusText = document.getElementById('searchStatusText');
    var clear = document.getElementById('clearSearch');
    if (!form || !input) return;

    var selector = '.l-footer-col a, .l-footer-sub, .l-footer-h';

    function apply() {
      var raw = String(input.value || '').replace(/\s+/g, ' ').trim();
      var query = raw.toLowerCase();
      var matches = 0;
      qsa(selector).forEach(function (element) {
        var found = !query ||
          String(element.textContent || '').toLowerCase().indexOf(query) !== -1;
        element.hidden = !found;
        if (found && query) matches += 1;
      });
      if (!query) {
        if (status) status.hidden = true;
        if (statusText) statusText.textContent = '';
        return;
      }
      if (status) status.hidden = false;
      if (statusText) {
        statusText.textContent = matches
          ? matches + (matches === 1 ? ' result for "' : ' results for "') + raw + '"'
          : 'No results for "' + raw + '"';
      }
    }

    function reset() {
      input.value = '';
      qsa(selector).forEach(function (element) { element.hidden = false; });
      if (status) status.hidden = true;
      if (statusText) statusText.textContent = '';
    }

    if (!input.__tHelpBound) {
      input.__tHelpBound = true;
      input.addEventListener('input', apply);
    }
    form.addEventListener('submit', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      apply();
    });
    if (clear) {
      clear.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        reset();
        if (typeof input.focus === 'function') {
          try { input.focus(); } catch (error) { /* ignore */ }
        }
      });
    }
  }

  /* ------------------- 11. Language + news chip ------------------- */
  function initLanguageSelect() {
    var select = document.getElementById('languageSelect');
    if (!select || select.__tLangBound) return;
    select.__tLangBound = true;
    var saved = read('keel_tag_language');
    if (saved) select.value = saved;
    select.addEventListener('change', function () {
      var option = select.options && select.options[select.selectedIndex];
      var label = option
        ? String(option.textContent || option.value || '').trim()
        : String(select.value || '');
      store('keel_tag_language', select.value);
      tToast('Language set to ' + label);
    });
  }

  function initNewsChip() {
    var chip = document.getElementById('newsChip');
    if (!chip) return;
    if (read('keel_tag_news_dismissed') === '1') chip.hidden = true;
    var close = qs('.l-news-close', chip);
    if (!close || close.__tNewsBound) return;
    close.__tNewsBound = true;
    close.addEventListener('click', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      chip.hidden = true;
      store('keel_tag_news_dismissed', '1');
    });
  }

  /* ------------------- 12. In-page anchors ------------------------ */
  function initAnchors() {
    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      var link = target.closest('a[href^="#"]');
      if (!link) return;
      var href = link.getAttribute('href') || '';
      var id = href.slice(1);
      if (!id) return;
      if (!document.getElementById(id)) return;
      event.preventDefault();
      closeTModal();
      scrollToId(id);
    });

    /* No dead anchors anywhere on this page. */
    qsa('a[href="#"]').forEach(function (link) {
      link.setAttribute('href', document.getElementById('top') ? '#top' : '/');
    });
  }

  /* ------------------------ 13. Global keys ----------------------- */
  function initGlobalKeys() {
    document.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key !== 'Escape' && key !== 'Esc') return;
      closeTModal();
      if (cMegaCloseAll) cMegaCloseAll();
      closeMobileMenu();
    });
  }

  /* ------------------------------- boot ---------------------------- */
  function boot() {
    if (!document.body || !document.body.classList ||
        !document.body.classList.contains('tag-page')) {
      return;
    }

    safe(initReveal);
    safe(initScrollEffects);
    safe(initMegaMenus);
    safe(initMobileMenu);
    safe(initModalControls);
    safe(initThread);
    safe(initUseTabs);
    safe(initCapabilities);
    safe(initAdminToggles);
    safe(initCopy);
    safe(initHelpSearch);
    safe(initLanguageSelect);
    safe(initNewsChip);
    safe(initAnchors);
    safe(initGlobalKeys);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();

/* ===========================================================================
   Keel Duet page enhancements — vanilla, local-only, no network calls.
   The waitlist is validated and stored in localStorage on this device; no
   account is created and nothing is transmitted. All handlers are guarded so
   a missing element never stops the rest of the page.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('duet-page')) {
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
    node.className = 'd-toast';
    node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
    node.textContent = message || 'Done.';
    document.body.appendChild(node);
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 3500);
  }

  /* ----------------------------- Modal helper ---------------------------- */
  function openModal(title, paragraphs) {
    var previousFocus = document.activeElement;
    var overlay = document.createElement('div');
    overlay.className = 'd-modal-overlay';

    var card = document.createElement('div');
    card.className = 'd-modal';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-label', title || 'Keel Duet');

    var closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'd-modal-close';
    closeButton.setAttribute('aria-label', 'Close');
    closeButton.textContent = '\u00d7';

    var header = document.createElement('div');
    header.className = 'd-modal-header';
    var heading = document.createElement('h2');
    heading.className = 'd-modal-title';
    heading.textContent = title || 'Keel Duet';
    header.appendChild(heading);

    var body = document.createElement('div');
    body.className = 'd-modal-body';
    (paragraphs || []).forEach(function (text) {
      var p = document.createElement('p');
      p.textContent = text;
      body.appendChild(p);
    });

    card.appendChild(closeButton);
    card.appendChild(header);
    card.appendChild(body);
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
        'a[href], button:not([disabled]), input:not([disabled]), ' +
        'textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
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
  }

  /* --------------------------- Waitlist form ---------------------------- */
  var WAITLIST_KEY = 'keel_duet_waitlist';
  var EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var PHONE_PATTERN = /^[+()\d\s.\-]{7,}$/;

  function initWaitlist() {
    var form = byId('duet-waitlist');
    if (!form) return;

    var errorEl = byId('d-form-error');
    var successEl = byId('d-form-success');
    var resetEl = byId('d-form-reset');
    var fields = [
      { id: 'd-first', label: 'First name' },
      { id: 'd-last', label: 'Last name' },
      { id: 'd-email', label: 'Email address', email: true },
      { id: 'd-company', label: 'Company name' },
      { id: 'd-phone', label: 'Phone number', phone: true }
    ].map(function (field) {
      field.el = byId(field.id);
      return field;
    });

    function readEntries() {
      var raw = storageGet(WAITLIST_KEY);
      if (!raw) return [];
      try {
        var value = JSON.parse(raw);
        return Array.isArray(value) ? value : [];
      } catch (error) { return []; }
    }

    function clearError() {
      fields.forEach(function (field) {
        if (field.el) field.el.removeAttribute('aria-invalid');
      });
      if (errorEl) { errorEl.textContent = ''; errorEl.hidden = true; }
    }

    function showSaved(message) {
      form.hidden = true;
      if (successEl) { successEl.textContent = message; successEl.hidden = false; }
      if (resetEl) resetEl.hidden = false;
      var announce = byId('duet-announce');
      if (announce) announce.hidden = true;
    }

    function showForm() {
      clearError();
      form.hidden = false;
      if (successEl) successEl.hidden = true;
      if (resetEl) resetEl.hidden = true;
      var first = byId('d-first');
      if (first && typeof first.focus === 'function') first.focus();
    }

    var existing = readEntries();
    if (existing.length) {
      showSaved('Saved locally on this device — no account created. ' +
        existing.length + (existing.length === 1 ? ' entry' : ' entries') +
        ' waiting here. We\'ll be in touch when a spot opens up.');
    }

    fields.forEach(function (field) {
      if (!field.el) return;
      field.el.addEventListener('input', function () {
        field.el.removeAttribute('aria-invalid');
        if (errorEl && !errorEl.hidden) clearError();
      });
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError();
      var problems = [];

      fields.forEach(function (field) {
        var value = field.el ? String(field.el.value || '').trim() : '';
        var invalid = !value;
        if (!invalid && field.email && !EMAIL_PATTERN.test(value)) invalid = true;
        if (!invalid && field.phone && !PHONE_PATTERN.test(value)) invalid = true;
        if (field.el) {
          if (invalid) field.el.setAttribute('aria-invalid', 'true');
          else field.el.removeAttribute('aria-invalid');
        }
        if (invalid) {
          problems.push(field.email && value ? 'a valid email address'
            : field.phone && value ? 'a valid phone number' : field.label);
        }
      });

      if (problems.length) {
        if (errorEl) {
          errorEl.textContent = 'Please check: ' + problems.join(', ') + '.';
          errorEl.hidden = false;
        }
        var firstInvalid = form.querySelector('[aria-invalid="true"]');
        if (firstInvalid && typeof firstInvalid.focus === 'function') {
          firstInvalid.focus();
        }
        return;
      }

      var checked = form.querySelector('input[name="platform"]:checked');
      var roleEl = byId('d-role');
      var record = {
        first: String(byId('d-first').value).trim(),
        last: String(byId('d-last').value).trim(),
        email: String(byId('d-email').value).trim(),
        company: String(byId('d-company').value).trim(),
        phone: String(byId('d-phone').value).trim(),
        platform: checked ? checked.value : '',
        role: roleEl ? String(roleEl.value || '').trim() : '',
        submittedAt: new Date().toISOString()
      };

      var entries = readEntries();
      entries.push(record);
      var saved = storageSet(WAITLIST_KEY, JSON.stringify(entries));
      if (saved) {
        showSaved('Saved locally on this device — no account created. ' +
          'Your entry is stored in this browser only; we\'ll be in touch ' +
          'when a spot opens up.');
        toast('Waitlist entry saved on this device.');
      } else {
        showSaved('This browser blocked local storage, so nothing was saved. ' +
          'No account was created.');
      }
    });

    if (resetEl) resetEl.addEventListener('click', function () {
      form.reset();
      showForm();
    });
  }

  /* ----------------------- Announcement + CTA --------------------------- */
  var ANNOUNCEMENT = [
    'Keel Duet is a proactive agent that understands what needs your attention. ' +
    'It takes on tasks of all sizes, keeps working while you are away, and waits ' +
    'for your OK when it matters.',
    'Tell Duet what you are working on and it gets to work on its own computer ' +
    'in the cloud, using the apps and tools you connect. It looks for pending ' +
    'invitations, unanswered emails, and gaps that need attention — then checks ' +
    'in when it needs your input.',
    'You set the boundaries. Powered by Keel 5, Opus, Sonnet, Haiku and the ' +
    'other Keel models. Join the waitlist to help shape what comes next.'
  ];

  var MODEL_INFO = {
    'Keel 5': 'Keel 5 is the everyday model for fast, reliable reasoning across ' +
      'the tasks Duet handles most often.',
    'Opus': 'Opus handles the deeper, multi-step work that needs careful ' +
      'judgment and a longer runway.',
    'Sonnet': 'Sonnet balances speed and capability for the steady stream of ' +
      'check-ins and updates Duet sends.',
    'Haiku': 'Haiku keeps small, frequent tasks quick so Duet can stay responsive ' +
      'while it works in the background.',
    'other Keel models': 'Duet chooses from the wider Keel model family for each ' +
      'step and can change models as a task evolves.'
  };

  var NEXT_STEPS = [
    'Join the waitlist so we can reach you when your spot is ready.',
    'Connect the apps Duet will work with — start with email and calendar.',
    'Set your boundaries: choose what Duet can do on its own and what needs ' +
    'your approval.',
    'Hand Duet a task and watch it work in the cloud.'
  ];

  function openAnnouncement() {
    openModal('Introducing Keel Duet', ANNOUNCEMENT);
  }

  function initAnnouncement() {
    var card = byId('duet-announce');
    if (!card) return;

    if (storageGet('keel_duet_announcement_dismissed') === 'true') {
      card.hidden = true;
    }
    var close = card.querySelector('.d-announce-close');
    if (close) {
      close.addEventListener('click', function () {
        card.hidden = true;
        storageSet('keel_duet_announcement_dismissed', 'true');
      });
    }
    all('[data-announcement]').forEach(function (button) {
      button.addEventListener('click', openAnnouncement);
    });
  }

  function initCta() {
    var join = document.querySelector('.d-cta-join');
    if (!join) return;
    join.addEventListener('click', function () {
      var form = byId('duet-waitlist');
      if (form && form.hidden) {
        toast('Your waitlist entry is already saved on this device.');
        return;
      }
      scrollToElement(byId('waitlist-card') || form);
      var first = byId('d-first');
      if (first && typeof first.focus === 'function') {
        try { first.focus({ preventScroll: true }); }
        catch (error) { first.focus(); }
      }
    });
  }

  /* ---------------------------- Model chips ----------------------------- */
  function initModelChips() {
    var chips = all('.d-model-chip[data-model]');
    chips.forEach(function (chip) {
      chip.addEventListener('click', function () {
        chips.forEach(function (other) {
          other.setAttribute('aria-pressed', 'false');
        });
        chip.setAttribute('aria-pressed', 'true');
        var name = chip.getAttribute('data-model') || 'Keel Duet';
        openModal(name, [MODEL_INFO[name] || MODEL_INFO['Keel 5']]);
      });
    });
  }

  function initNextStep() {
    var button = document.querySelector('[data-next-step]');
    if (button) {
      button.addEventListener('click', function () {
        openModal('Find next step', NEXT_STEPS);
      });
    }
  }

  /* --------------------------- FAQ accordion ---------------------------- */
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
      var open = item.classList.contains('is-open');
      setState(item, open);
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
        var isOpen = !!(item && item.classList.contains('is-open'));
        if (isOpen) { clearTimers(); setMega(trigger, false); }
        else openOne(trigger);
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
    var stored = storageGet('keel_duet_language');
    if (stored) {
      select.value = stored;
      document.documentElement.lang = stored;
    }
    select.addEventListener('change', function () {
      document.documentElement.lang = select.value;
      storageSet('keel_duet_language', select.value);
      var label = select.options[select.selectedIndex]
        ? select.options[select.selectedIndex].text : select.value;
      toast('Language preference saved: ' + label);
    });
  }

  /* --------------------- Reveals + parallax + sticky -------------------- */
  function initReveals() {
    var nodes = all('.d-reveal');
    if (!nodes.length || reducedMotion() || !('IntersectionObserver' in window)) {
      return; /* Content stays visible without JS support. */
    }
    document.body.classList.add('d-animate');
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
    var phone = document.querySelector('.d-phone');
    var announce = byId('duet-announce');
    var pending = false;

    function update() {
      pending = false;
      var y = window.scrollY;
      if (typeof y !== 'number') {
        y = window.pageYOffset || document.documentElement.scrollTop || 0;
      }
      if (header) header.classList.toggle('is-scrolled', y > 16);
      if (reducedMotion()) return;

      if (phone) {
        var r = phone.getBoundingClientRect();
        if (r.bottom > -120 && r.top < window.innerHeight + 120) {
          var shift = (r.top + r.height / 2 - window.innerHeight / 2) * -0.035;
          phone.style.setProperty('--duet-phone-shift',
            clamp(shift, -10, 10).toFixed(1) + 'px');
        }
      }
      if (announce && !announce.hidden) {
        var a = announce.getBoundingClientRect();
        if (a.bottom > -80 && a.top < window.innerHeight + 80) {
          var aShift = (a.top + a.height / 2 - window.innerHeight / 2) * -0.025;
          announce.style.setProperty('--duet-announce-shift',
            clamp(aShift, -8, 8).toFixed(1) + 'px');
        }
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
    safe(initWaitlist);
    safe(initAnnouncement);
    safe(initCta);
    safe(initModelChips);
    safe(initNextStep);
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

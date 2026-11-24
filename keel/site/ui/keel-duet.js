/* ===========================================================================
   Keel Duet page enhancements — vanilla, local-only, no network calls.
   Self-contained: navigation, mobile menu, auth and page chrome are wired up
   here so the page no longer depends on a shared landing.js. Everything is
   guarded so a missing element never breaks the rest of the page.
   =========================================================================== */
(function () {
  'use strict';

  if (!document.body || !document.body.classList ||
      !document.body.classList.contains('duet-page')) {
    return;
  }

  /* Runs a setup step without letting one broken section stop the others. */
  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function byId(id) { return document.getElementById(id); }

  /* Mutable module state used by global key handling. */
  var modalStack = [];
  var closeChatWidget = function () {};
  var closeAllAccordions = function () {};
  var closeMobileNavHandlers = [];
  var closeMobileNav = function () {
    closeMobileNavHandlers.forEach(function (fn) {
      try { fn(); } catch (error) { /* ignore */ }
    });
  };
  var closeAllMegas = function () {};
  var closeAuthModal = function () {};
  var submitted = false;

  function hasSubmittedBefore() {
    try {
      var raw = window.localStorage.getItem('keel_duet_waitlist');
      if (!raw) return false;
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) && parsed.length > 0;
    } catch (error) {
      return false;
    }
  }
  submitted = hasSubmittedBefore();

  /* ---------------------------- Toast helper ---------------------------- */
  function dToast(msg) {
    var toast = document.createElement('div');
    toast.className = 'd-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.textContent = msg || 'Done.';
    document.body.appendChild(toast);
    window.setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3500);
    return toast;
  }

  /* -------------------------- Generic modal -------------------------- */
  /* dOpenModal({ title, body, onClose }) builds:
       .d-modal-overlay > .d-modal > (.d-modal-header + .d-modal-body)
     with a close button, focus trap basics, Escape, and backdrop click.
     `body` may be an HTML string, a DOM node, an array of nodes, or a fn. */
  function dOpenModal(options) {
    options = options || {};
    var previousFocus = document.activeElement;

    var overlay = document.createElement('div');
    overlay.className = 'd-modal-overlay';

    var card = document.createElement('div');
    card.className = 'd-modal';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');

    var header = document.createElement('div');
    header.className = 'd-modal-header';

    var titleEl = document.createElement('h2');
    titleEl.className = 'd-modal-title';
    titleEl.textContent = options.title || 'Keel Duet';

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'd-modal-close';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.textContent = '\u00d7';

    header.appendChild(titleEl);
    header.appendChild(closeBtn);

    var bodyEl = document.createElement('div');
    bodyEl.className = 'd-modal-body';

    var content = options.body;
    if (typeof content === 'string') {
      bodyEl.innerHTML = content;
    } else if (content && typeof content.nodeType === 'number') {
      bodyEl.appendChild(content);
    } else if (typeof content === 'function') {
      var produced = content(bodyEl);
      if (produced && typeof produced.nodeType === 'number' && !produced.parentNode) {
        bodyEl.appendChild(produced);
      }
    } else if (Array.isArray(content)) {
      content.forEach(function (node) {
        if (node && typeof node.nodeType === 'number') bodyEl.appendChild(node);
      });
    }

    card.appendChild(header);
    card.appendChild(bodyEl);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    var closed = false;
    function close() {
      if (closed) return;
      closed = true;
      var index = modalStack.indexOf(api);
      if (index !== -1) modalStack.splice(index, 1);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (typeof options.onClose === 'function') {
        try { options.onClose(); } catch (error) { /* ignore */ }
      }
      if (previousFocus && typeof previousFocus.focus === 'function' &&
          document.contains(previousFocus)) {
        previousFocus.focus();
      }
    }

    var api = {
      overlay: overlay,
      card: card,
      body: bodyEl,
      closeButton: closeBtn,
      close: close
    };
    modalStack.push(api);

    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close();
    });

    overlay.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key === 'Escape' || key === 'Esc') {
        event.preventDefault();
        close();
        return;
      }
      if (key !== 'Tab') return;
      var focusables = Array.prototype.slice.call(card.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), ' +
        'textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter(function (node) {
        return !node.hidden && !!(node.offsetWidth || node.offsetHeight ||
          (node.getClientRects && node.getClientRects().length));
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

    if (closeBtn && typeof closeBtn.focus === 'function') closeBtn.focus();
    return api;
  }

  /* Expose helpers for any page-level integration, without clobbering others. */
  try {
    if (!window.dToast) window.dToast = dToast;
    if (!window.dOpenModal) window.dOpenModal = dOpenModal;
  } catch (error) { /* ignore */ }

  /* ------------------------ Segmented controls ------------------------ */
  function initSegments() {
    var buttons = Array.prototype.slice.call(
      document.querySelectorAll('.d-seg-btn[data-group]')
    );
    if (!buttons.length) return;

    var groups = {};
    buttons.forEach(function (button) {
      var name = button.getAttribute('data-group') || 'default';
      if (!groups[name]) groups[name] = [];
      groups[name].push(button);
    });

    Object.keys(groups).forEach(function (name) {
      var items = groups[name];

      function select(target) {
        items.forEach(function (button) {
          var active = button === target;
          button.classList.toggle('is-active', active);
          button.setAttribute('aria-checked', active ? 'true' : 'false');
          button.setAttribute('tabindex', active ? '0' : '-1');
        });
      }

      items.forEach(function (button, index) {
        var isActive = button.classList.contains('is-active');
        button.setAttribute('tabindex', isActive ? '0' : '-1');
        if (!button.hasAttribute('aria-checked')) {
          button.setAttribute('aria-checked', isActive ? 'true' : 'false');
        }

        button.addEventListener('click', function () { select(button); });

        button.addEventListener('keydown', function (event) {
          var key = event && event.key;
          var next = null;
          if (key === 'ArrowRight' || key === 'ArrowDown') {
            next = items[(index + 1) % items.length];
          } else if (key === 'ArrowLeft' || key === 'ArrowUp') {
            next = items[(index - 1 + items.length) % items.length];
          } else if (key === 'Home') {
            next = items[0];
          } else if (key === 'End') {
            next = items[items.length - 1];
          }
          if (next) {
            event.preventDefault();
            select(next);
            if (typeof next.focus === 'function') next.focus();
          }
        });
      });
    });
  }

  /* --------------------------- Waitlist form --------------------------- */
  function initForm() {
    var form = byId('duet-waitlist');
    if (!form) return;

    var errorEl = byId('d-form-error');
    var successEl = byId('d-form-success');
    var required = [
      { id: 'd-first', label: 'First name' },
      { id: 'd-last', label: 'Last name' },
      { id: 'd-email', label: 'Email address', email: true },
      { id: 'd-company', label: 'Company name' }
    ].map(function (field) {
      field.el = byId(field.id);
      return field;
    });

    var roleEl = byId('d-role');
    var consentEl = byId('d-consent');
    var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    function markInvalid(el, invalid) {
      if (!el) return;
      if (invalid) el.setAttribute('aria-invalid', 'true');
      else el.removeAttribute('aria-invalid');
    }

    function segmentValue(group, fallback) {
      var active = form.querySelector(
        '.d-seg-btn.is-active[data-group="' + group + '"]'
      );
      return (active && active.getAttribute('data-value')) || fallback;
    }

    function clearErrors() {
      required.forEach(function (field) { markInvalid(field.el, false); });
      if (errorEl) {
        errorEl.hidden = true;
        errorEl.textContent = '';
      }
    }

    /* Clearing a fixed field removes its error state. */
    required.forEach(function (field) {
      if (!field.el) return;
      field.el.addEventListener('input', function () {
        markInvalid(field.el, false);
        if (errorEl && !errorEl.hidden) clearErrors();
      });
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearErrors();

      var invalidFields = [];
      required.forEach(function (field) {
        var value = field.el ? String(field.el.value || '').trim() : '';
        var bad = !value;
        if (!bad && field.email) bad = !emailPattern.test(value);
        markInvalid(field.el, bad);
        if (bad) invalidFields.push(field);
      });

      if (invalidFields.length) {
        var problems = invalidFields.map(function (field) {
          return field.email && field.el && String(field.el.value || '').trim()
            ? 'a valid email address'
            : field.label;
        });
        if (errorEl) {
          errorEl.textContent = 'Please check: ' + problems.join(', ') + '.';
          errorEl.hidden = false;
        }
        var firstEl = invalidFields[0].el;
        if (firstEl && typeof firstEl.focus === 'function') firstEl.focus();
        return;
      }

      var record = {
        first: String(required[0].el.value).trim(),
        last: String(required[1].el.value).trim(),
        email: String(required[2].el.value).trim(),
        company: String(required[3].el.value).trim(),
        use: segmentValue('use', 'Personal'),
        device: segmentValue('device', 'Phone'),
        role: roleEl ? String(roleEl.value || '').trim() : '',
        consent: !!(consentEl && consentEl.checked),
        submittedAt: new Date().toISOString()
      };

      var list = [];
      try {
        var raw = window.localStorage.getItem('keel_duet_waitlist');
        var parsed = raw ? JSON.parse(raw) : [];
        if (Array.isArray(parsed)) list = parsed;
      } catch (error) { /* start a fresh list if storage is unavailable */ }
      list.push(record);
      try {
        window.localStorage.setItem('keel_duet_waitlist', JSON.stringify(list));
      } catch (error) { /* the demo still succeeds without persistence */ }

      submitted = true;
      form.hidden = true;
      if (successEl) successEl.hidden = false;
      dToast("Thanks — you're on the Keel Duet waitlist.");
    });
  }

  /* --------------------------- FAQ accordion --------------------------- */
  function initAccordion() {
    var items = Array.prototype.slice.call(
      document.querySelectorAll('.d-acc-item')
    );
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
      var initiallyOpen = item.classList.contains('is-open');
      if (!button.hasAttribute('aria-expanded')) {
        button.setAttribute('aria-expanded', initiallyOpen ? 'true' : 'false');
      }
      setState(item, initiallyOpen);

      button.addEventListener('click', function () {
        var willOpen = !item.classList.contains('is-open');
        items.forEach(function (other) {
          if (other !== item) setState(other, false);
        });
        setState(item, willOpen);
      });
    });

    closeAllAccordions = function () {
      items.forEach(function (item) { setState(item, false); });
    };

    /* Keep an open panel correctly sized when the viewport changes. */
    window.addEventListener('resize', function () {
      items.forEach(function (item) {
        if (!item.classList.contains('is-open')) return;
        var panel = item.querySelector('.d-acc-panel');
        if (panel) panel.style.maxHeight = panel.scrollHeight + 'px';
      });
    });
  }

  /* ------------------------ CTA + announcements ------------------------ */
  var ANNOUNCEMENT_HTML =
    '<p>Keel Duet is a proactive agent that understands what needs your ' +
    'attention. It takes on tasks of all sizes, keeps working while you’re ' +
    'away, and waits for your ok when it matters.</p>' +
    '<p>Tell Duet what you’re working on and it gets to work on its own ' +
    'computer in the cloud, using the apps and tools you connect. It looks ' +
    'for pending invitations, unanswered emails, and gaps that need ' +
    'attention — then checks in when it needs your input.</p>' +
    '<p>You set the boundaries. Powered by Opus 4.5, Sonnet 4.5 and ' +
    'Haiku 4.5. Join the waitlist to help us shape what comes next.</p>';

  var CHANGELOG_HTML =
    '<p><strong>October 13, 2026 — First look</strong></p>' +
    '<ul>' +
    '<li><strong>Proactive check-ins.</strong> Duet surfaces the things ' +
    'that need you, all in one place.</li>' +
    '<li><strong>Long-running tasks.</strong> Hand off multi-step work and ' +
    'keep moving while it runs in the cloud.</li>' +
    '<li><strong>Approval gates.</strong> You decide what Duet can do on ' +
    'its own and what needs a yes.</li>' +
    '<li><strong>6,000+ connectors.</strong> Works with Stripe, 1Password, ' +
    'Shopify, Gmail and the other apps you already use.</li>' +
    '<li><strong>Model choices.</strong> Powered by Opus 4.5, Sonnet 4.5 ' +
    'and Haiku 4.5.</li>' +
    '</ul>';

  function openAnnouncement() {
    dOpenModal({ title: 'Introducing Keel Duet', body: ANNOUNCEMENT_HTML });
  }

  function openChangelog() {
    dOpenModal({ title: "What's new in Keel Duet", body: CHANGELOG_HTML });
  }

  function initCta() {
    var join = document.querySelector('.d-cta-join');
    if (join) {
      join.addEventListener('click', function () {
        if (submitted) {
          dToast("You're already on the waitlist — we'll be in touch soon.");
          return;
        }
        var target = byId('duet-waitlist') ||
          document.querySelector('.d-signup-wrap') || byId('faq');
        if (target && typeof target.scrollIntoView === 'function') {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        var first = byId('d-first');
        if (first && typeof first.focus === 'function') {
          try { first.focus({ preventScroll: true }); }
          catch (error) { first.focus(); }
        }
      });
    }

    var announcement = document.querySelector('.d-cta-outline');
    if (announcement) announcement.addEventListener('click', openAnnouncement);
  }

  function initChangelog() {
    var button = document.querySelector('.d-changelog');
    if (button) button.addEventListener('click', openChangelog);
  }

  /* ---------------------------- Chat widget ---------------------------- */
  var KEEL_REPLIES = [
    {
      keys: ['price', 'cost', 'how much', 'pricing', 'free'],
      text: 'Keel Duet is joining the Keel family. We’re finalising pricing — ' +
            'join the waitlist and we’ll share details with you first.'
    },
    {
      keys: ['when', 'launch', 'available', 'release', 'access'],
      text: 'We’re rolling out access gradually. Add your details to the ' +
            'waitlist and we’ll reach out as soon as your spot is ready.'
    },
    {
      keys: ['safe', 'secure', 'privacy', 'private', 'approve', 'permission'],
      text: 'You’re in control. Duet works on its own computer in the cloud, ' +
            'and you choose what it can do automatically versus what needs ' +
            'your approval.'
    },
    {
      keys: ['what can', 'do', 'task', 'email', 'calendar', 'connector'],
      text: 'Duet can watch for pending invitations, unanswered emails and ' +
            'gaps that need attention, then take on multi-step tasks using ' +
            'the 6,000+ apps you connect.'
    },
    {
      keys: ['model', 'opus', 'sonnet', 'haiku'],
      text: 'Duet is powered by Opus 4.5, Sonnet 4.5 and Haiku 4.5, so it ' +
            'can pick the right model for each task.'
    },
    {
      keys: ['hello', 'hi', 'hey', 'help', 'start'],
      text: 'Hi! Tell me what you’re trying to get done and I’ll suggest ' +
            'where Duet can lend a hand.'
    }
  ];
  var DEFAULT_REPLY =
    'Got it. Keel Duet is built to take work off your plate — tell me a ' +
    'little more about the task and I’ll point you in the right direction. ' +
    'You can also join the waitlist above for early access.';

  function keelReply(text) {
    var lower = String(text || '').toLowerCase();
    for (var i = 0; i < KEEL_REPLIES.length; i += 1) {
      var entry = KEEL_REPLIES[i];
      for (var j = 0; j < entry.keys.length; j += 1) {
        if (lower.indexOf(entry.keys[j]) !== -1) return entry.text;
      }
    }
    return DEFAULT_REPLY;
  }

  function appendChatLine(log, who, text) {
    var line = document.createElement('div');
    line.className = 'd-chat-line d-chat-line--' + (who === 'user' ? 'user' : 'keel');
    var author = document.createElement('strong');
    author.textContent = who === 'user' ? 'You' : 'Keel Duet';
    var message = document.createElement('span');
    message.textContent = text;
    line.appendChild(author);
    line.appendChild(message);
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function openChatModal() {
    var log = document.createElement('div');
    log.className = 'd-chat-log';
    log.setAttribute('role', 'log');
    log.setAttribute('aria-live', 'polite');
    appendChatLine(log, 'keel',
      'Hi! I’m Keel Duet. Tell me what you need to work on and I’ll take it from there.');

    var form = document.createElement('form');
    form.className = 'd-chat-form';

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'd-chat-input';
    input.placeholder = 'Type your message…';
    input.setAttribute('aria-label', 'Message Keel Duet');

    var send = document.createElement('button');
    send.type = 'submit';
    send.className = 'l-btn l-btn-dark d-chat-send';
    send.textContent = 'Send';

    form.appendChild(input);
    form.appendChild(send);

    var wrapper = document.createElement('div');
    wrapper.className = 'd-chat-modal-body';
    wrapper.appendChild(log);
    wrapper.appendChild(form);

    dOpenModal({ title: 'Chat with Keel Duet', body: wrapper });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var value = String(input.value || '').trim();
      if (!value) return;
      appendChatLine(log, 'user', value);
      input.value = '';
      appendChatLine(log, 'keel', keelReply(value));
      if (typeof input.focus === 'function') input.focus();
    });

    if (typeof input.focus === 'function') input.focus();
  }

  var NEXT_STEPS_HTML =
    '<ol class="d-next-steps">' +
    '<li>Join the waitlist above so we can reach you when your spot is ready.</li>' +
    '<li>Connect the apps Duet will work with — start with email and calendar.</li>' +
    '<li>Set your boundaries: choose what Duet can do on its own and what ' +
    'needs your approval.</li>' +
    '<li>Hand Duet a task and watch it work in the cloud.</li>' +
    '</ol>';

  function openNextSteps() {
    dOpenModal({ title: 'Next steps with Keel Duet', body: NEXT_STEPS_HTML });
  }

  function initChat() {
    var fab = byId('duet-chat-fab');
    var chat = byId('duet-chat');
    if (!fab || !chat) return;

    if (!fab.hasAttribute('aria-expanded')) fab.setAttribute('aria-expanded', 'false');

    function setOpen(open) {
      chat.classList.toggle('is-open', open);
      fab.setAttribute('aria-expanded', open ? 'true' : 'false');
      fab.setAttribute('aria-label', open ? 'Close chat' : 'Open chat');
    }

    var userToggled = false;

    fab.addEventListener('click', function () {
      userToggled = true;
      setOpen(!chat.classList.contains('is-open'));
    });

    var close = chat.querySelector('.d-chat-close');
    if (close) {
      close.addEventListener('click', function () {
        userToggled = true;
        setOpen(false);
        if (typeof fab.focus === 'function') fab.focus();
      });
    }

    /* Reveal the widget near the page footer (as in the reference layout)
       without covering the waitlist form higher up the page. */
    var footer = byId('footer');
    if (footer && 'IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        var visible = entries.some(function (entry) { return entry.isIntersecting; });
        if (!userToggled) setOpen(visible);
      }, { rootMargin: '0px 0px -20% 0px', threshold: 0 });
      io.observe(footer);
    }

    var actions = Array.prototype.slice.call(chat.querySelectorAll('[data-chat]'));
    actions.forEach(function (button) {
      button.addEventListener('click', function () {
        var action = button.getAttribute('data-chat');
        if (action === 'start') openChatModal();
        else if (action === 'next') openNextSteps();
      });
    });

    closeChatWidget = function () { setOpen(false); };
  }

  /* -------------------------- Footer FAQ search -------------------------- */
  function initFooterSearch() {
    var input = byId('d-footer-search');
    if (!input) return;

    var items = Array.prototype.slice.call(
      document.querySelectorAll('.d-acc-item')
    );

    var empty = byId('d-search-empty');
    if (!empty) {
      empty = document.createElement('p');
      empty.id = 'd-search-empty';
      empty.className = 'd-search-empty';
      empty.setAttribute('role', 'status');
      empty.textContent = 'No results found. Try a different search.';
      empty.hidden = true;
      var accordion = document.querySelector('.d-accordion');
      if (accordion && accordion.parentNode) {
        accordion.parentNode.insertBefore(empty, accordion.nextSibling);
      } else {
        document.body.appendChild(empty);
      }
    }

    function scrollToFaq() {
      var faq = byId('faq');
      if (faq && typeof faq.scrollIntoView === 'function') {
        faq.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

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
      empty.hidden = !(needle && matches === 0);
    }

    input.addEventListener('input', applyFilter);
    input.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key === 'Enter' || key === 'ArrowDown') {
        event.preventDefault();
        scrollToFaq();
      }
    });

    var form = (typeof input.closest === 'function') ? input.closest('form') : null;
    if (form) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        applyFilter();
        scrollToFaq();
      });
    }
  }

  /* ----------------------------- News chip ----------------------------- */
  function initNewsChip() {
    var chip = document.querySelector('.d-news-chip');
    if (!chip) return;

    try {
      if (window.localStorage.getItem('keel_duet_news_dismissed') === 'true') {
        chip.hidden = true;
      }
    } catch (error) { /* ignore unavailable storage */ }

    var close = chip.querySelector('.d-news-close');
    if (!close) return;
    close.addEventListener('click', function () {
      chip.hidden = true;
      try {
        window.localStorage.setItem('keel_duet_news_dismissed', 'true');
      } catch (error) { /* ignore unavailable storage */ }
    });
  }

  /* --------------------------- Mega navigation --------------------------- */
  function initMegaMenus() {
    var triggers = Array.prototype.slice.call(
      document.querySelectorAll('.l-nav-trigger[aria-controls]')
    );
    if (!triggers.length) return;

    var openTimer = null;
    var closeTimer = null;

    function clearTimers() {
      if (openTimer !== null) { window.clearTimeout(openTimer); openTimer = null; }
      if (closeTimer !== null) { window.clearTimeout(closeTimer); closeTimer = null; }
    }

    function itemFor(trigger) {
      if (typeof trigger.closest === 'function') {
        return trigger.closest('.l-nav-item');
      }
      return trigger.parentNode;
    }

    function setMega(trigger, open) {
      var item = itemFor(trigger);
      if (!item) return;
      var id = trigger.getAttribute('aria-controls');
      var mega = id ? byId(id) : null;
      if (!mega && typeof item.querySelector === 'function') {
        mega = item.querySelector('.l-mega');
      }
      item.classList.toggle('is-open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (mega) mega.setAttribute('aria-hidden', open ? 'false' : 'true');
    }

    function closeAll(except) {
      triggers.forEach(function (trigger) {
        if (trigger !== except) setMega(trigger, false);
      });
    }

    function openOne(trigger) {
      clearTimers();
      closeAll(trigger);
      setMega(trigger, true);
    }

    function toggleOne(trigger) {
      var item = itemFor(trigger);
      var isOpen = !!(item && item.classList.contains('is-open'));
      if (isOpen) {
        clearTimers();
        setMega(trigger, false);
      } else {
        openOne(trigger);
      }
    }

    triggers.forEach(function (trigger) {
      var item = itemFor(trigger);

      trigger.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        toggleOne(trigger);
      });

      /* A button already emits click for Enter/Space. Preventing the default
         keydown stops that synthetic click, so this handler only toggles once. */
      trigger.addEventListener('keydown', function (event) {
        var key = event && event.key;
        if (key !== 'Enter' && key !== ' ' && key !== 'Spacebar') return;
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        toggleOne(trigger);
      });

      if (!item) return;

      item.addEventListener('mouseenter', function () {
        clearTimers();
        openTimer = window.setTimeout(function () { openOne(trigger); }, 60);
      });

      item.addEventListener('mouseleave', function () {
        clearTimers();
        closeTimer = window.setTimeout(function () {
          setMega(trigger, false);
        }, 140);
      });
    });

    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === 'function' &&
          target.closest('.l-nav-item')) return;
      clearTimers();
      closeAll();
    });

    closeAllMegas = function (returnFocus) {
      clearTimers();
      var opener = null;
      triggers.forEach(function (trigger) {
        var item = itemFor(trigger);
        if (!opener && item && item.classList.contains('is-open')) opener = trigger;
        setMega(trigger, false);
      });
      if (returnFocus && opener && typeof opener.focus === 'function') {
        try { opener.focus(); } catch (error) { /* ignore */ }
      }
    };
  }

  /* --------------------------- Mobile navigation -------------------------- */
  function bindMobileToggle(toggle, nav) {
    if (!toggle || !nav || typeof toggle.addEventListener !== 'function') return;
    if (toggle.__duetMobileBound) return;
    toggle.__duetMobileBound = true;

    if (!toggle.hasAttribute('aria-expanded')) {
      toggle.setAttribute('aria-expanded', 'false');
    }

    function setOpen(open) {
      nav.hidden = !open;
      nav.classList.toggle('open', open);
      nav.classList.toggle('is-open', open);
      toggle.classList.toggle('open', open);
      toggle.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    }

    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });

    Array.prototype.slice.call(nav.querySelectorAll('a, button')).forEach(function (link) {
      link.addEventListener('click', function () { setOpen(false); });
    });

    closeMobileNavHandlers.push(function () { setOpen(false); });
  }

  function initMobileNav() {
    /* Bind the header controls directly — no shared script required. */
    bindMobileToggle(byId('navToggle'), byId('mobileMenu'));
    /* Keep the d-* fallback for markup variants that lack those ids. */
    bindMobileToggle(
      document.querySelector('.d-nav-toggle'),
      document.querySelector('.d-mobile-nav')
    );
  }

  /* ------------------------------- Auth flow ------------------------------ */
  function initAuth() {
    var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    var modal = byId('authModal');
    var triggers = Array.prototype.slice.call(
      document.querySelectorAll('.js-auth, [data-auth]')
    );
    var previousFocus = null;

    function rememberLogin() {
      try {
        window.localStorage.setItem('keel_logged_in', 'true');
      } catch (error) { /* storage may be unavailable — the demo still works */ }
      dToast("You're signed in to Keel.");
    }

    function openFallbackAuth() {
      var input = document.createElement('input');
      input.type = 'email';
      input.className = 'd-auth-input';
      input.placeholder = 'you@example.com';
      input.setAttribute('aria-label', 'Email address');

      var error = document.createElement('p');
      error.className = 'd-auth-error';
      error.setAttribute('role', 'alert');
      error.hidden = true;
      error.textContent = 'Please enter a valid email address.';

      var form = document.createElement('form');
      form.className = 'd-auth-form';
      form.appendChild(input);
      form.appendChild(error);

      var submit = document.createElement('button');
      submit.type = 'submit';
      submit.className = 'l-btn l-btn-dark';
      submit.textContent = 'Continue';
      form.appendChild(submit);

      var api = dOpenModal({ title: 'Welcome to Keel', body: form });

      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var value = String(input.value || '').trim();
        var valid = emailPattern.test(value);
        error.hidden = valid;
        if (!valid) {
          if (typeof input.focus === 'function') input.focus();
          return;
        }
        rememberLogin();
        api.close();
        dOpenModal({
          title: "You're in",
          body: '<p>You\'re signed in to Keel. Keep exploring here, or open the app.</p>' +
                '<p><a class="l-btn l-btn-dark" href="/app">Continue to Keel</a></p>'
        });
      });

      if (typeof input.focus === 'function') input.focus();
    }

    if (modal && !modal.__duetAuthBound) {
      modal.__duetAuthBound = true;

      var formView = byId('authFormView');
      var successView = byId('authSuccessView');
      var authForm = byId('authForm');
      var email = byId('authEmail');
      var error = byId('authError');

      function show() {
        previousFocus = document.activeElement;
        modal.hidden = false;
        modal.removeAttribute('hidden');
        modal.classList.add('is-open', 'open');
        if (formView) formView.hidden = false;
        if (successView) successView.hidden = true;
        if (error) error.hidden = true;
        if (email) {
          email.value = '';
          email.removeAttribute('aria-invalid');
          window.setTimeout(function () {
            if (typeof email.focus === 'function') email.focus();
          }, 0);
        }
      }

      function hide() {
        modal.hidden = true;
        modal.classList.remove('is-open', 'open');
        if (previousFocus && typeof previousFocus.focus === 'function' &&
            document.contains(previousFocus)) {
          previousFocus.focus();
        }
        previousFocus = null;
      }

      modal.__duetOpenAuth = show;
      closeAuthModal = hide;

      Array.prototype.slice.call(
        modal.querySelectorAll('[data-modal-close]')
      ).forEach(function (button) {
        button.addEventListener('click', hide);
      });

      if (authForm && email) {
        authForm.addEventListener('submit', function (event) {
          event.preventDefault();
          var value = String(email.value || '').trim();
          var valid = emailPattern.test(value);
          if (error) error.hidden = valid;
          if (valid) email.removeAttribute('aria-invalid');
          else email.setAttribute('aria-invalid', 'true');
          if (!valid) {
            if (typeof email.focus === 'function') email.focus();
            return;
          }
          rememberLogin();
          if (formView) formView.hidden = true;
          if (successView) successView.hidden = false;
          var appLink = successView ? successView.querySelector('a[href="/app"]') : null;
          if (appLink && typeof appLink.focus === 'function') {
            window.setTimeout(function () { appLink.focus(); }, 0);
          }
        });
      }
    }

    function openAuth() {
      /* Never leave a mega open behind the dialog. */
      closeAllMegas(false);
      if (modal && typeof modal.__duetOpenAuth === 'function') {
        modal.__duetOpenAuth();
      } else {
        openFallbackAuth();
      }
    }

    triggers.forEach(function (el) {
      if (el.__duetAuthBound) return;
      el.__duetAuthBound = true;
      el.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        openAuth();
      });
    });
  }

  /* ---------------------------- Sticky header ----------------------------- */
  function initStickyHeader() {
    var header = document.querySelector('.l-header');
    if (!header) return;

    function update() {
      var y = window.scrollY;
      if (typeof y !== 'number') {
        y = window.pageYOffset || document.documentElement.scrollTop || 0;
      }
      header.classList.toggle('is-scrolled', y > 24);
    }

    update();
    window.addEventListener('scroll', update, { passive: true });
  }

  /* ----------------------------- Footer year ------------------------------ */
  function initFooterYear() {
    var year = byId('year');
    if (!year) return;
    year.textContent = String(new Date().getFullYear());
  }

  /* --------------------------- Global Escape --------------------------- */
  document.addEventListener('keydown', function (event) {
    var key = event && event.key;
    if (key !== 'Escape' && key !== 'Esc') return;
    var hadModal = modalStack.length > 0;
    if (hadModal) {
      var top = modalStack[modalStack.length - 1];
      if (top) top.close();
    }
    closeAuthModal();
    closeChatWidget();
    closeAllAccordions();
    closeMobileNav();
    closeAllMegas(!hadModal);
  });

  /* ------------------------------- Boot ------------------------------- */
  function init() {
    safe(initSegments);
    safe(initForm);
    safe(initAccordion);
    safe(initCta);
    safe(initChangelog);
    safe(initChat);
    safe(initFooterSearch);
    safe(initNewsChip);
    safe(initMegaMenus);
    safe(initMobileNav);
    safe(initAuth);
    safe(initStickyHeader);
    safe(initFooterYear);

    try {
      document.dispatchEvent(new CustomEvent('keel:duet-ready', { bubbles: true }));
    } catch (error) { /* CustomEvent unavailable — nothing depends on it */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

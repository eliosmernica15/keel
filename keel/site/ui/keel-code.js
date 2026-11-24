/* ===========================================================================
   Keel Code page enhancements — vanilla JS, local-only, no network calls.
   Loaded after /ui/landing.js. Everything is guarded so a missing element
   never breaks the rest of the page. The shared landing.js is intentionally
   minimal, so this file also owns the page's mega menus, FAQ accordion, plan
   tabs, auth modal, help search, news chip and language select. It never
   double-binds the mobile menu toggle (landing.js owns that click).
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

  /* One broken section must not stop the others. */
  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function scrollToId(id) {
    if (!id) return;
    var el = document.getElementById(id);
    if (!el || typeof el.scrollIntoView !== 'function') return;
    try {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) {
      try { el.scrollIntoView(); } catch (ignored) { /* no scroll API */ }
    }
  }

  /* ---------------------- fallback DOM (defensive) ---------------------- */
  /* The HTML agent owns the canonical #c-modal / #c-toast markup. These
     helpers only build a stand-in when that markup is not on the page yet,
     so this script is always functional and never throws. */
  function ensureModal() {
    var modal = document.getElementById('c-modal');
    if (modal) return modal;
    if (!document.body) return null;
    modal = document.createElement('div');
    modal.className = 'c-modal';
    modal.id = 'c-modal';
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML =
      '<div class="c-modal-backdrop" data-c-close></div>' +
      '<div class="c-modal-card" role="dialog" aria-modal="true" aria-labelledby="c-modal-title">' +
        '<button type="button" class="c-modal-close" data-c-close aria-label="Close dialog">\u00d7</button>' +
        '<h2 id="c-modal-title"></h2>' +
        '<div id="c-modal-body"></div>' +
        '<button type="button" class="l-btn l-btn-dark" data-c-close>Close</button>' +
      '</div>';
    document.body.appendChild(modal);
    return modal;
  }

  function ensureToast() {
    var toast = document.getElementById('c-toast');
    if (toast) return toast;
    if (!document.body) return null;
    toast = document.createElement('div');
    toast.className = 'c-toast';
    toast.id = 'c-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.hidden = true;
    document.body.appendChild(toast);
    return toast;
  }

  /* ------------------------ 1. Toast helper ------------------------ */
  var toastTimer = null;

  function cToast(message) {
    var toast = ensureToast();
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

  /* --------------------- 2. Generic modal helpers --------------------- */
  var modalLastFocus = null;

  function openCModal(title, html) {
    var modal = ensureModal();
    if (!modal) return;
    var titleEl = document.getElementById('c-modal-title');
    var bodyEl = document.getElementById('c-modal-body');
    if (titleEl) titleEl.textContent = String(title == null ? '' : title);
    if (bodyEl) bodyEl.innerHTML = String(html == null ? '' : html);

    modalLastFocus = document.activeElement;
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    if (modal.classList) modal.classList.add('is-open');
    document.body.classList.add('c-modal-open');

    var closeButton = qs('.c-modal-close', modal) || qs('[data-c-close]', modal);
    if (closeButton && typeof closeButton.focus === 'function') {
      try { closeButton.focus(); } catch (error) { /* focus is a nice-to-have */ }
    }
  }

  function closeCModal() {
    var modal = document.getElementById('c-modal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    if (modal.classList) modal.classList.remove('is-open');
    document.body.classList.remove('c-modal-open');

    if (modalLastFocus && typeof document.contains === 'function' &&
        document.contains(modalLastFocus) && typeof modalLastFocus.focus === 'function') {
      try { modalLastFocus.focus(); } catch (error) { /* ignore */ }
    }
    modalLastFocus = null;
  }

  function initModalControls() {
    /* Backdrop, X button and the bottom Close button all use [data-c-close]. */
    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      var trigger = target.closest('[data-c-close]');
      if (!trigger) return;
      var modal = document.getElementById('c-modal');
      if (!modal) return;
      if (trigger === modal || (typeof modal.contains === 'function' && modal.contains(trigger))) {
        event.preventDefault();
        closeCModal();
      }
    });

    /* Escape closes; Tab is trapped inside the dialog while it is open. */
    document.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key === 'Escape' || key === 'Esc') {
        var modal = document.getElementById('c-modal');
        if (modal && !modal.hidden) {
          event.preventDefault();
          closeCModal();
        }
        return;
      }
      if (key !== 'Tab') return;
      var dialog = document.getElementById('c-modal');
      if (!dialog || dialog.hidden) return;
      var card = qs('.c-modal-card', dialog) || dialog;
      var focusables = qsa(
        'a[href], button:not([disabled]), input:not([disabled]), ' +
        'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        card
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

  /* ------------------------- shared copy row ------------------------- */
  var INSTALL_CMD = 'curl -fsSL https://keel.ai/install.sh | bash';

  function copyRowHtml(command) {
    return "<div class='c-copy-row'><code>" + esc(command) + "</code>" +
      "<button type='button' class='c-copy' data-copy='" + esc(command) + "'>Copy</button></div>";
  }

  /* ------------------------ 3. data-way buttons ------------------------ */
  var WAY_CONTENT = {
    terminal: {
      title: 'Keel Code in your terminal',
      html: "<p>Install the Keel Code CLI and work alongside the command-line tools you already use. Keel reads your repo, asks before risky actions, and opens a pull request when the work is done.</p>" +
        copyRowHtml(INSTALL_CMD) +
        "<p>Run <code>keel</code> inside any project folder and sign in with your Keel account. Add a <code>KEEL.md</code> file to give the agent project-specific instructions.</p>" +
        "<p><button type='button' class='l-btn l-btn-dark' data-c-scroll='where-you-code'>See terminal setup</button> " +
        "<a href='/requirements' class='l-btn l-btn-outline'>CLI documentation</a></p>"
    },
    web: {
      title: 'Keel Code on the web',
      html: "<p>Open Keel Code in your browser at keel.ai/app. There is nothing to install: your projects, sessions and permission settings follow you from the desktop app.</p>" +
        "<p>The web is ideal for reviewing a running task, approving an action, or starting a quick fix while you are away from your machine.</p>" +
        "<p><a href='/app' class='l-btn l-btn-dark'>Open Keel Code</a> " +
        "<a href='/requirements' class='l-btn l-btn-outline'>Documentation</a></p>"
    },
    ios: {
      title: 'Keel Code for iOS',
      html: "<p>The Keel iOS app keeps you connected to tasks running on your Mac or in the cloud. Review diffs, answer Keel's questions and approve actions right from your phone.</p>" +
        "<p>Download the Keel app and sign in with the same account — your active Keel Code sessions appear automatically.</p>" +
        "<p><a href='/download' class='l-btn l-btn-dark'>Download the app</a> " +
        "<a href='/requirements' class='l-btn l-btn-outline'>Learn more</a></p>"
    },
    android: {
      title: 'Keel Code for Android',
      html: "<p>The Keel Android app keeps you connected to tasks running in the cloud. Review a pull request, answer a clarifying question and approve the next step from anywhere.</p>" +
        "<p>Install the Keel app, sign in with your Keel account, and pick up exactly where you left off on your desktop.</p>" +
        "<p><a href='/download' class='l-btn l-btn-dark'>Download the app</a> " +
        "<a href='/requirements' class='l-btn l-btn-outline'>Learn more</a></p>"
    },
    github: {
      title: 'Keel Code and GitHub',
      html: "<p>Connect Keel Code to GitHub and it can read issues, write code, run tests and open pull requests on your behalf — with your approval before changes land.</p>" +
        "<ol><li>Install the Keel integration for your repository from your Keel account settings.</li>" +
        "<li>Mention Keel in an issue with the task you want done.</li>" +
        "<li>Review the pull request Keel opens and merge it when you are happy.</li></ol>" +
        "<p><a href='/requirements' class='l-btn l-btn-outline'>See the GitHub workflow</a></p>"
    },
    vscode: {
      title: 'Keel Code for VS Code',
      html: "<p>Keel Code runs in VS Code, Cursor and Devin Desktop. The extension brings the same agent into your editor: select code, ask a question, and review every change as a diff.</p>" +
        "<ol><li>Open the Extensions view in your editor.</li>" +
        "<li>Search for Keel Code and install the extension.</li>" +
        "<li>Sign in with your Keel account and open a project folder to start a session.</li></ol>" +
        "<p><button type='button' class='l-btn l-btn-dark' data-modal='vscode'>Full install guide</button></p>"
    },
    jetbrains: {
      title: 'Keel Code for JetBrains',
      html: "<p>Use Keel Code inside PyCharm, IntelliJ IDEA, WebStorm and other JetBrains IDEs. Ask for a change in the editor and review the result without leaving your project.</p>" +
        "<ol><li>Open Settings, then Plugins, then Marketplace.</li>" +
        "<li>Search for Keel Code and install the plugin.</li>" +
        "<li>Restart your IDE and sign in with your Keel account.</li></ol>" +
        "<p><button type='button' class='l-btn l-btn-dark' data-modal='jetbrains'>Full install guide</button></p>"
    },
    slack: {
      title: 'Keel Code in Slack',
      html: "<p>Add Keel to Slack and kick off coding tasks from a channel. Mention @Keel with a bug or feature request; Keel asks clarifying questions, works in your repo and posts the pull request back in the thread.</p>" +
        "<p>You decide which channels and repositories the integration can touch.</p>" +
        "<p><button type='button' class='l-btn l-btn-dark' data-c-scroll='slack'>See Slack setup</button> " +
        "<button type='button' class='l-btn l-btn-outline' data-modal='slack'>How the integration works</button></p>"
    }
  };

  /* ------------------------ 4. data-modal buttons ------------------------ */
  var MODAL_CONTENT = {
    changelog: {
      title: "What's new in Keel Code",
      html: "<p>Here are the three most recent Keel Code releases.</p><ul>" +
        "<li><strong>Oct 15, 2026 — Code Review.</strong> Catch more bugs before they reach production. Now generally available for Team and Enterprise.</li>" +
        "<li><strong>Oct 1, 2026 — Mods.</strong> Change how Keel Code behaves and looks with a few lines of TypeScript. Available in the CLI and desktop app.</li>" +
        "<li><strong>Sep 17, 2026 — Projects.</strong> Group related coding sessions so you can run and easily supervise multiple Keel agents at once. Available on Keel Code Desktop.</li>" +
        "</ul><p><a href='/notices' class='l-btn l-btn-outline'>Read all announcements</a></p>"
    },
    vscode: {
      title: 'Install Keel Code for VS Code',
      html: "<p>Keel Code is available as an extension for VS Code, Cursor and Devin Desktop. It puts the agent next to your code so you can ask for a change and review it as a diff.</p>" +
        "<ol><li>Open the Extensions view (<code>Ctrl+Shift+X</code>, or <code>Cmd+Shift+X</code> on macOS).</li>" +
        "<li>Search for <strong>Keel Code</strong> and choose Install.</li>" +
        "<li>Sign in with your Keel account when prompted.</li>" +
        "<li>Open a project folder and run <code>Keel Code: Start session</code> from the command palette.</li></ol>" +
        copyRowHtml(INSTALL_CMD) +
        "<p><a href='/requirements' class='l-btn l-btn-outline'>Read the editor docs</a></p>"
    },
    jetbrains: {
      title: 'Install Keel Code for JetBrains IDEs',
      html: "<p>Keel Code plugs into PyCharm, IntelliJ IDEA, WebStorm, GoLand and other JetBrains IDEs. Start a session from the editor and review changes with the usual IDE diff tools.</p>" +
        "<ol><li>Open <strong>Settings</strong> (or <strong>Preferences</strong> on macOS).</li>" +
        "<li>Go to <strong>Plugins</strong>, then <strong>Marketplace</strong>.</li>" +
        "<li>Search for <strong>Keel Code</strong>, install it, and restart the IDE.</li>" +
        "<li>Sign in with your Keel account and open a project to begin.</li></ol>" +
        "<p><a href='/requirements' class='l-btn l-btn-outline'>Read the IDE docs</a></p>"
    },
    slack: {
      title: 'Keel Code in Slack',
      html: "<p>Add the Keel app to your Slack workspace to start coding tasks from a conversation. Mention <strong>@Keel</strong> in a channel with a bug, an issue link or a feature request.</p>" +
        "<ol><li>Add Keel to the workspace from your Keel account settings.</li>" +
        "<li>Choose the channels and repositories the integration may access.</li>" +
        "<li>Mention @Keel with a task. Keel asks clarifying questions and gets to work.</li>" +
        "<li>Keel posts the plan, progress updates and the pull request back in the thread.</li></ol>" +
        "<p><button type='button' class='l-btn l-btn-dark' data-c-scroll='slack'>Jump to the Slack section</button> " +
        "<a href='/requirements' class='l-btn l-btn-outline'>Integration docs</a></p>"
    }
  };

  function genericContent() {
    return {
      title: 'Keel Code',
      html: "<p>Keel Code works in your terminal, your editor, the web and the Keel desktop app. Wherever you start, your sessions, permissions and review history stay with you.</p>" +
        "<p><a href='/requirements' class='l-btn l-btn-dark'>Read the documentation</a> " +
        "<a href='/download' class='l-btn l-btn-outline'>Download Keel</a></p>"
    };
  }

  function initWays() {
    document.addEventListener('click', function (event) {
      var button = closest(event && event.target, '[data-way]');
      if (!button) return;
      event.preventDefault();
      var key = button.getAttribute('data-way') || '';
      var content = WAY_CONTENT[key] || genericContent();
      openCModal(content.title, content.html);
    });
  }

  function initModals() {
    document.addEventListener('click', function (event) {
      var button = closest(event && event.target, '[data-modal]');
      if (!button) return;
      event.preventDefault();
      var key = button.getAttribute('data-modal') || '';
      var content = MODAL_CONTENT[key] || genericContent();
      openCModal(content.title, content.html);
    });
  }

  /* -------------------- 5. Terminal demo tabs -------------------- */
  var DEMOS = {
    onboarding: [
      { c: 'prompt', t: '⏺  I am new here. Map the auth flow and tell me where sessions are created.' },
      { c: 'tool',   t: '  ⏺  Read KEEL.md and 12 source files' },
      { c: 'tool',   t: '  ⏺  Searched 148 files for "session"' },
      { c: 'file',   t: '  Read  src/auth/session.ts' },
      { c: 'edit',   t: '   +18 -3  src/auth/session.ts' },
      { c: 'file',   t: '  Read  src/middleware/requireUser.ts' },
      { c: 'edit',   t: '   +7 -1  src/middleware/requireUser.ts' },
      { c: 'file',   t: '  Write ARCHITECTURE.md' },
      { c: 'edit',   t: '   +26 -0  ARCHITECTURE.md' },
      { c: 'done',   t: '  ✓  Done — mapped the auth flow across 14 files. Sessions are created in src/auth/session.ts:42 and validated in requireUser.ts.' }
    ],
    triage: [
      { c: 'prompt', t: '⏺  Triage issue #482: checkout throws on an empty cart. Add a test, fix it, open a PR.' },
      { c: 'tool',   t: '  ⏺  Read issue #482 and 6 related files' },
      { c: 'tool',   t: '  ⏺  Reproduced with `npm run test:checkout`' },
      { c: 'file',   t: '  Read  src/checkout/total.ts' },
      { c: 'edit',   t: '   +12 -4  src/checkout/total.ts' },
      { c: 'file',   t: '  Read  tests/checkout.test.ts' },
      { c: 'edit',   t: '   +21 -0  tests/checkout.test.ts' },
      { c: 'tool',   t: '  ⏺  Ran `npm test -- checkout` → 24 passed' },
      { c: 'tool',   t: '  ⏺  Committed fix and opened PR #486' },
      { c: 'done',   t: '  ✓  Done — regression test and fix are in PR #486. All 24 checkout tests pass.' }
    ],
    migrate: [
      { c: 'prompt', t: '⏺  Migrate the API client from v2 to v3. Follow imports, update callers, keep tests green.' },
      { c: 'tool',   t: '  ⏺  Scanned 312 files for `api/v2` imports' },
      { c: 'file',   t: '  Read  src/lib/apiClient.ts' },
      { c: 'edit',   t: '   +64 -28  src/lib/apiClient.ts' },
      { c: 'file',   t: '  Read  src/routes/users.ts' },
      { c: 'edit',   t: '   +19 -11  src/routes/users.ts' },
      { c: 'file',   t: '  Read  src/routes/orders.ts' },
      { c: 'edit',   t: '   +15 -9  src/routes/orders.ts' },
      { c: 'tool',   t: '  ⏺  Ran `npm test` → 181 passed, 0 failed' },
      { c: 'file',   t: '  Write KEEL.md' },
      { c: 'edit',   t: '   +9 -2  KEEL.md' },
      { c: 'done',   t: '  ✓  Done — migrated 27 call sites across 9 files. Full suite passes (181 tests).' }
    ]
  };

  function termHtml(lines) {
    return lines.map(function (line) {
      return "<div class='c-term-line c-term-" + line.c + "'>" + esc(line.t) + '</div>';
    }).join('');
  }

  function initDemos() {
    var tabs = qsa('.c-ttab[data-demo]');
    if (!tabs.length) return;
    var body = qs('[data-terminal-body]');

    function select(tab, moveFocus) {
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle('is-active', active);
        other.setAttribute('aria-selected', active ? 'true' : 'false');
        other.tabIndex = active ? 0 : -1;
      });
      if (body) {
        var key = tab.getAttribute('data-demo') || '';
        var lines = DEMOS[key];
        if (lines) body.innerHTML = termHtml(lines);
      }
      if (moveFocus && typeof tab.focus === 'function') tab.focus();
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () { select(tab, false); });
      tab.addEventListener('keydown', function (event) {
        var key = event && event.key;
        var next = -1;
        if (key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
        else if (key === 'Home') next = 0;
        else if (key === 'End') next = tabs.length - 1;
        if (next < 0 || next === index) return;
        event.preventDefault();
        select(tabs[next], true);
      });
    });

    var initial = tabs.filter(function (tab) {
      return tab.classList && tab.classList.contains('is-active');
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ------------------------- 6. Copy buttons ------------------------- */
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
    if (button.__cCopyTimer) {
      clearTimeout(button.__cCopyTimer);
      button.__cCopyTimer = null;
    }
    if (typeof button.__cCopyLabel !== 'string') {
      button.__cCopyLabel = button.textContent || 'Copy';
    }
    button.textContent = 'Copied';
    cToast('Copied to clipboard.');
    button.__cCopyTimer = setTimeout(function () {
      button.__cCopyTimer = null;
      button.textContent = button.__cCopyLabel || 'Copy';
    }, 1800);
  }

  function initCopy() {
    /* Delegated so copy buttons rendered into a modal work too. */
    document.addEventListener('click', function (event) {
      var button = closest(event && event.target, '.c-copy[data-copy]');
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

  /* ------------------------ 7. Newsletter form ------------------------ */
  function initNewsletter() {
    var form = qs('#c-news-form');
    if (!form) return;
    var input = qs('#c-news-email', form) || qs('#c-news-email');
    var msg = qs('#c-news-msg', form) || qs('#c-news-msg');
    form.noValidate = true;

    function setMsg(text, state) {
      if (!msg) return;
      msg.textContent = text;
      msg.hidden = false;
      msg.setAttribute('data-state', state || '');
      if (msg.classList) {
        msg.classList.remove('is-error', 'is-success');
        if (state) msg.classList.add(state === 'error' ? 'is-error' : 'is-success');
      }
    }

    function clearMsg() {
      if (!msg) return;
      msg.textContent = '';
      msg.hidden = true;
      msg.setAttribute('data-state', '');
      if (msg.classList) msg.classList.remove('is-error', 'is-success');
    }

    if (input) {
      input.addEventListener('input', function () {
        if (input.getAttribute('aria-invalid') === 'true') input.removeAttribute('aria-invalid');
        if (msg && !msg.hidden && msg.classList && msg.classList.contains('is-error')) clearMsg();
      });
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var value = input ? String(input.value || '').replace(/\s+/g, ' ').trim() : '';
      var valid = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
      if (!valid) {
        setMsg('Please provide a valid email address.', 'error');
        if (input) {
          input.setAttribute('aria-invalid', 'true');
          if (typeof input.focus === 'function') input.focus();
        }
        return;
      }
      try { window.localStorage.setItem('keel_newsletter', value); } catch (error) { /* optional */ }
      setMsg("You're on the list — watch your inbox for the next Keel developer newsletter.", 'success');
      if (input) {
        input.value = '';
        input.removeAttribute('aria-invalid');
      }
      cToast('Subscribed to the Keel developer newsletter.');
    });
  }

  /* ------------- 8. In-page anchors and no dead anchors ------------- */
  function initAnchors() {
    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;

      var scroller = target.closest('[data-c-scroll]');
      if (scroller) {
        event.preventDefault();
        var scrollId = scroller.getAttribute('data-c-scroll') || '';
        closeCModal();
        scrollToId(scrollId);
        return;
      }

      var link = target.closest('a[href^="#"]');
      if (!link || link.hasAttribute('data-c-scroll')) return;
      var href = link.getAttribute('href') || '';
      var id = href.slice(1);
      if (!id) return;
      if (!document.getElementById(id)) return;
      event.preventDefault();
      scrollToId(id);
    });

    /* Safety net: replace placeholder anchors with a real destination. */
    qsa('a[href="#"]').forEach(function (link) {
      link.setAttribute('href', document.getElementById('top') ? '#top' : '/');
    });
  }

  /* =====================================================================
     Shared shell behaviours. landing.js on this deployment only provides
     sticky nav, the mobile-menu toggle, reveal and the footer year, so the
     interactions below are implemented here, defensively and idempotently.
     ===================================================================== */

  var cMegaCloseAll = null;
  var cFaqCloseAll = null;
  var cFaqReveal = null;
  var cAuthClose = null;

  /* ------------------------- 9. Mega menus ------------------------- */
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
      if (!item.__cMegaState) item.__cMegaState = { pinned: false, byHover: false };
      return item.__cMegaState;
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

    /* Mirrors the shell CSS conventions: .open/.is-open on the item and
       menu, aria-expanded on the trigger, aria-hidden on the menu, plus the
       hidden attribute when no shell stylesheet supplies the visibility. */
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

    function keyboardFocus(node) {
      try { return !!(node && node.matches && node.matches(':focus-visible')); }
      catch (error) { return false; }
    }

    items.forEach(function (item) {
      var pair = parts(item);
      setOpen(item, false); /* start closed, even if CSS omitted the rules */

      if (pair.trigger && !pair.trigger.__cMegaBound) {
        pair.trigger.__cMegaBound = true;
        /* Native button clicks already cover Enter and Space — no keydown
           handler here, so there is no chance of a double toggle. */
        pair.trigger.addEventListener('click', function (event) {
          if (event && typeof event.preventDefault === 'function') event.preventDefault();
          var s = state(item);
          if (isOpen(item) && s.byHover && !s.pinned) {
            /* The pointer already opened it; the first click pins it open
               instead of looking like a broken "close on click". */
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
        if (!keyboardFocus(event && event.target)) return;
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
      if (target && typeof target.closest === 'function' &&
          target.closest('.l-nav-item')) return;
      clearTimers();
      closeAll();
    });

    cMegaCloseAll = function () { clearTimers(); closeAll(); };
  }

  /* ------------------------ 10. FAQ accordion ------------------------ */
  function initFaq() {
    var buttons = qsa('button.l-faq-q');
    if (!buttons.length) return;

    function itemFor(button) {
      return closest(button, '.l-faq-item');
    }

    function panelFor(button) {
      var id = button.getAttribute('aria-controls');
      var panel = id ? document.getElementById(id) : null;
      if (!panel) {
        var item = itemFor(button);
        panel = item ? qs('.l-faq-a', item) : null;
      }
      return panel;
    }

    function setItem(button, open) {
      var item = itemFor(button);
      var panel = panelFor(button);
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (button.classList) button.classList.toggle('is-open', open);
      if (item && item.classList) {
        item.classList.toggle('open', open);
        item.classList.toggle('is-open', open);
      }
      if (panel) panel.hidden = !open;
    }

    function closeAll(except) {
      buttons.forEach(function (button) {
        if (button !== except) setItem(button, false);
      });
    }

    buttons.forEach(function (button) {
      setItem(button, false); /* restore a consistent closed state on load */
      if (button.__cFaqBound) return;
      button.__cFaqBound = true;
      button.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var open = button.getAttribute('aria-expanded') === 'true';
        if (open) {
          setItem(button, false);
        } else {
          closeAll(button); /* only one answer open at a time */
          setItem(button, true);
        }
      });
    });

    cFaqCloseAll = function () { closeAll(null); };
    cFaqReveal = function (button) { if (button) setItem(button, true); };
  }

  /* ------------------------- 11. Plan tabs ------------------------- */
  function initPlanTabs() {
    var tabs = qsa('[data-plan-tab]');
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
      if (tab.__cPlanBound) return;
      tab.__cPlanBound = true;
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
    })[0] || tabs.filter(function (tab) {
      return tab.getAttribute('aria-selected') === 'true';
    })[0] || tabs[0];
    if (initial) select(initial, false); /* Team visible, Individual hidden */
  }

  /* ------------------------ 12. Auth modal ------------------------ */
  function initAuthModal() {
    var modal = document.getElementById('authModal');
    var formView = document.getElementById('authFormView');
    var successView = document.getElementById('authSuccessView');
    var form = document.getElementById('authForm');
    var email = document.getElementById('authEmail');
    var error = document.getElementById('authError');
    var note = document.getElementById('authNote');
    var title = document.getElementById('authTitle');
    var desc = document.getElementById('authDesc');
    var previousFocus = null;

    var MODES = {
      login:  { title: 'Welcome back to Keel', desc: 'Enter your email to sign in to Keel.' },
      signup: { title: 'Create your Keel account', desc: 'Enter your email to get started with Keel Code.' },
      sales:  { title: 'Talk to the Keel team', desc: 'Enter your email and we will reach out about Keel Code for your team.' },
      google: { title: 'Continue with Google', desc: 'Enter any valid email to continue with Keel.' },
      email:  { title: 'Keel updates', desc: 'Enter your email for Keel product news and developer updates.' }
    };

    function show(mode) {
      var config = MODES[mode] || MODES.login;
      if (!modal) {
        /* Defensive fallback so an auth button is never dead. */
        openCModal(config.title, '<p>' + esc(config.desc) + '</p>' +
          '<p><a href="/app" class="l-btn l-btn-dark">Continue to Keel</a></p>');
        return;
      }
      previousFocus = document.activeElement;
      if (title) title.textContent = config.title;
      if (desc) desc.textContent = config.desc;
      if (note) note.hidden = mode !== 'google';
      if (formView) formView.hidden = false;
      if (successView) successView.hidden = true;
      if (error) error.hidden = true;
      if (email) {
        email.value = '';
        email.removeAttribute('aria-invalid');
      }
      modal.hidden = false;
      modal.removeAttribute('hidden');
      if (modal.classList) {
        modal.classList.add('is-open');
        modal.classList.add('open');
      }
      document.body.classList.add('l-modal-open');
      closeMobileMenu();
      if (cMegaCloseAll) cMegaCloseAll();

      if (email && typeof email.focus === 'function') {
        try { email.focus(); } catch (exception) { /* focus is optional */ }
      }
    }

    function hide() {
      if (!modal || modal.hidden) return;
      modal.hidden = true;
      if (modal.classList) {
        modal.classList.remove('is-open');
        modal.classList.remove('open');
      }
      document.body.classList.remove('l-modal-open');
      if (previousFocus && typeof document.contains === 'function' &&
          document.contains(previousFocus) && typeof previousFocus.focus === 'function') {
        try { previousFocus.focus(); } catch (exception) { /* ignore */ }
      }
      previousFocus = null;
    }

    cAuthClose = hide;

    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;

      var trigger = target.closest('[data-auth]');
      if (trigger) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        show(trigger.getAttribute('data-auth') || 'login');
        return;
      }

      var closer = target.closest('[data-modal-close]');
      if (closer && modal && typeof modal.contains === 'function' && modal.contains(closer)) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        hide();
      }
    });

    if (form && email) {
      form.addEventListener('submit', function (event) {
        if (event && typeof event.preventDefault === 'function') event.preventDefault();
        var value = String(email.value || '').trim();
        var valid = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
        if (error) error.hidden = valid;
        if (valid) email.removeAttribute('aria-invalid');
        else email.setAttribute('aria-invalid', 'true');
        if (!valid) {
          if (typeof email.focus === 'function') {
            try { email.focus(); } catch (exception) { /* ignore */ }
          }
          return;
        }
        try { window.localStorage.setItem('keel_logged_in', '1'); }
        catch (exception) { /* storage may be unavailable; demo still works */ }
        if (formView) formView.hidden = true;
        if (successView) successView.hidden = false;
        var appLink = successView ? qs('a[href="/app"]', successView) : null;
        if (appLink && typeof appLink.focus === 'function') {
          try { appLink.focus(); } catch (exception) { /* ignore */ }
        }
        /* The /app link keeps its native behaviour. */
      });
    }
  }

  /* ------------------------ 13. Help search ------------------------ */
  function initHelpSearch() {
    var form = document.getElementById('helpForm');
    var input = document.getElementById('helpSearch');
    var status = document.getElementById('searchStatus');
    var statusText = document.getElementById('searchStatusText');
    var clear = document.getElementById('clearSearch');
    if (!form || !input) return;

    var selector = '.l-footer-col a, .l-footer-col button, .l-footer-sub, ' +
                   '.l-footer-h, .l-faq-item';

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

      if (cFaqCloseAll) cFaqCloseAll();
      if (!query) {
        if (status) status.hidden = true;
        if (statusText) statusText.textContent = '';
        return;
      }

      /* Reveal the answers of matching FAQ items. */
      qsa('.l-faq-item').forEach(function (item) {
        if (item.hidden) return;
        if (String(item.textContent || '').toLowerCase().indexOf(query) === -1) return;
        var button = qs('button.l-faq-q', item);
        if (button && cFaqReveal) cFaqReveal(button);
      });

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
      if (cFaqCloseAll) cFaqCloseAll();
      if (status) status.hidden = true;
      if (statusText) statusText.textContent = '';
    }

    if (!input.__cHelpBound) {
      input.__cHelpBound = true;
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
          try { input.focus(); } catch (exception) { /* ignore */ }
        }
      });
    }
  }

  /* ------------------------ 14. News chip ------------------------ */
  function initNewsChip() {
    var chip = document.getElementById('newsChip');
    if (!chip) return;

    function dismissed() {
      try {
        var value = window.localStorage.getItem('keel_news_dismissed');
        return value === '1' || value === 'true';
      } catch (error) { return false; }
    }

    if (dismissed()) chip.hidden = true;

    var close = qs('.l-news-close', chip);
    if (!close || close.__cNewsBound) return;
    close.__cNewsBound = true;
    close.addEventListener('click', function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      chip.hidden = true;
      try { window.localStorage.setItem('keel_news_dismissed', '1'); }
      catch (error) { /* storage is optional */ }
    });
  }

  /* ---------------------- 15. Language select ---------------------- */
  function initLanguageSelect() {
    var select = document.getElementById('languageSelect');
    if (!select || select.__cLangBound) return;
    select.__cLangBound = true;
    select.addEventListener('change', function () {
      var option = select.options && select.options[select.selectedIndex];
      var label = option
        ? String(option.textContent || option.value || '').trim()
        : String(select.value || '');
      cToast('Language set to ' + label);
    });
  }

  /* ------------------- 16. Changelog header button ------------------ */
  function initChangelog() {
    document.addEventListener('click', function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      if (!target.closest('.js-changelog')) return;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      closeMobileMenu();
      var content = MODAL_CONTENT.changelog;
      openCModal(content.title, content.html);
    });
  }

  /* landing.js owns the navToggle click; this only closes an open menu on
     Escape or when another overlay takes over, so nothing toggles twice. */
  function closeMobileMenu() {
    var menu = document.getElementById('mobileMenu');
    var toggle = document.getElementById('navToggle');
    if (!menu || !menu.classList ||
        (!menu.classList.contains('open') && !menu.classList.contains('is-open'))) return;
    menu.classList.remove('open');
    menu.classList.remove('is-open');
    menu.hidden = true;
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open menu');
      if (toggle.classList) {
        toggle.classList.remove('open');
        toggle.classList.remove('is-open');
      }
    }
  }

  /* One Escape listener coordinates the layers we own. The generic modal's
     own handler (in initModalControls) closes #c-modal independently. */
  function initGlobalKeys() {
    document.addEventListener('keydown', function (event) {
      var key = event && event.key;
      if (key !== 'Escape' && key !== 'Esc') return;
      if (cAuthClose) cAuthClose();
      if (cFaqCloseAll) cFaqCloseAll();
      if (cMegaCloseAll) cMegaCloseAll();
      closeMobileMenu();
    });
  }

  /* --------------------------- mobile menu ---------------------------- */
  function initMobileMenu() {
    var toggle = document.getElementById('navToggle');
    var menu = document.getElementById('mobileMenu');
    if (!toggle || !menu || toggle.__cMobileBound) return;
    toggle.__cMobileBound = true;

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
      var target = event && event.target;
      if (menu.hidden) return;
      if (!target || !target.closest('.l-nav-inner')) close();
    });
    document.addEventListener('keydown', function (event) {
      if (event && (event.key === 'Escape' || event.key === 'Esc') && !menu.hidden) {
        close();
      }
    });
  }

  /* ------------------------------- boot ------------------------------- */
  function boot() {
    if (!document.body || !document.body.classList ||
        !document.body.classList.contains('code-page')) {
      return;
    }

    /* Shared shell behaviours. This page intentionally does not load the
       shared landing.js: it binds the same selectors and would toggle each
       control twice. keel-code.js is the single owner here. */
    safe(initMegaMenus);
    safe(initMobileMenu);
    safe(initFaq);
    safe(initPlanTabs);
    safe(initAuthModal);
    safe(initHelpSearch);
    safe(initNewsChip);
    safe(initLanguageSelect);
    safe(initChangelog);

    safe(initModalControls);
    safe(initWays);
    safe(initModals);
    safe(initDemos);
    safe(initCopy);
    safe(initNewsletter);
    safe(initAnchors);
    safe(initGlobalKeys);

    /* Small, non-clobbering bridge for page-level integrations. */
    try {
      if (!window.cToast) window.cToast = cToast;
      if (!window.openCModal) window.openCModal = openCModal;
      if (!window.closeCModal) window.closeCModal = closeCModal;
    } catch (error) { /* window may be unavailable */ }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();

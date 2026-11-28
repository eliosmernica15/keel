'use strict';

/* /keel-in-chrome — vanilla JS interactions only.
   No dependencies, no external network calls, no console errors.
   Every lookup is guarded so a missing element never breaks the page. */

(function () {
  /* Runs one setup step without letting a broken section stop the rest. */
  function safe(setup) {
    try { setup(); } catch { /* enhancements must never throw */ }
  }

  function setExpanded(node, expanded) {
    if (node && typeof node.setAttribute === 'function') {
      node.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  }

  function all(selector, root) {
    try { return Array.from((root || document).querySelectorAll(selector)); } catch { return []; }
  }

  /* ---------- 1. Mega menu: hover, click, keyboard, outside click ---------- */
  function initNav() {
    const items = all('.kp-nav-item[data-menu]');
    if (!items.length) return;
    const pins = new WeakMap();

    function setOpen(item, open) {
      if (!item || !item.classList) return;
      item.classList.toggle('open', open);
      if (!open) pins.set(item, false);
      setExpanded(item.querySelector('.kp-nav-trigger'), open);
      const mega = item.querySelector('.kp-mega');
      if (mega && typeof mega.setAttribute === 'function') {
        mega.setAttribute('aria-hidden', open ? 'false' : 'true');
      }
    }

    function closeAll(except) {
      items.forEach((item) => { if (item !== except) setOpen(item, false); });
    }
    initNav._closeAll = closeAll;

    items.forEach((item, index) => {
      const trigger = item.querySelector('.kp-nav-trigger');
      pins.set(item, false);
      if (trigger && !trigger.hasAttribute('aria-expanded')) setExpanded(trigger, false);
      const mega = item.querySelector('.kp-mega');
      if (mega && !mega.hasAttribute('aria-hidden')) mega.setAttribute('aria-hidden', 'true');

      let suppressFocus = false;
      let pointerDown = false;

      item.addEventListener('mouseenter', () => {
        if (suppressFocus) return;
        closeAll(item);
        setOpen(item, true);
      });
      item.addEventListener('mouseleave', () => {
        if (pins.get(item) === true) return;
        if (item.contains && item.contains(document.activeElement)) return;
        setOpen(item, false);
      });

      if (trigger) {
        trigger.addEventListener('pointerdown', () => { pointerDown = true; suppressFocus = true; });
        trigger.addEventListener('click', () => {
          pointerDown = false;
          const wasOpen = item.classList.contains('open');
          if (wasOpen) {
            setOpen(item, false);
            pins.set(item, false);
            suppressFocus = true;
          } else {
            closeAll(item);
            setOpen(item, true);
            pins.set(item, true);
          }
        });
        trigger.addEventListener('keydown', (event) => {
          if (!event) return;
          let next = -1;
          if (event.key === 'ArrowRight') next = (index + 1) % items.length;
          else if (event.key === 'ArrowLeft') next = (index - 1 + items.length) % items.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = items.length - 1;
          if (next < 0 || next === index) return;
          const nextTrigger = items[next].querySelector('.kp-nav-trigger');
          if (nextTrigger) {
            event.preventDefault();
            closeAll(items[next]);
            setOpen(items[next], true);
            nextTrigger.focus();
          }
        });
      }

      item.addEventListener('focusin', () => {
        if (suppressFocus || pointerDown) return;
        closeAll(item);
        setOpen(item, true);
      });
      item.addEventListener('focusout', (event) => {
        const next = event && event.relatedTarget;
        if (next && item.contains && item.contains(next)) return;
        if (pins.get(item) !== true) setOpen(item, false);
        suppressFocus = false;
      });
    });

    document.addEventListener('click', (event) => {
      const target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      if (!target.closest('.kp-nav-item')) closeAll();
    });
    window.addEventListener('pointerup', () => { pointerDown = false; });
    window.addEventListener('pointercancel', () => { pointerDown = false; });
  }

  /* ---------- 2. Mobile drawer ---------- */
  function initMobile() {
    const toggle = document.querySelector('.kp-nav-toggle');
    const menu = document.querySelector('.kp-mobile-menu');
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute('aria-expanded')) setExpanded(toggle, false);

    function close() {
      menu.classList.remove('open');
      setExpanded(toggle, false);
      toggle.setAttribute('aria-label', 'Open menu');
    }
    initMobile._close = close;

    toggle.addEventListener('click', () => {
      const willOpen = !menu.classList.contains('open');
      menu.classList.toggle('open', willOpen);
      setExpanded(toggle, willOpen);
      toggle.setAttribute('aria-label', willOpen ? 'Close menu' : 'Open menu');
    });
    menu.addEventListener('click', (event) => {
      const target = event && event.target;
      if (target && typeof target.closest === 'function' && target.closest('a, button')) close();
    });
    document.addEventListener('click', (event) => {
      const target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      if (target.closest('.kp-nav-toggle, .kp-mobile-menu')) return;
      if (menu.classList.contains('open')) close();
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth > 760 && menu.classList.contains('open')) close();
    });
  }

  /* ---------- 3. FAQ accordion ---------- */
  function initFaq() {
    const questions = all('.cl-faq-list button.kp-faq-q');
    if (!questions.length) return;
    questions.forEach((question) => {
      if (!question.hasAttribute('aria-expanded')) setExpanded(question, false);
      const panel = document.getElementById(question.getAttribute('aria-controls') || '');
      if (panel) panel.setAttribute('aria-hidden', 'true');

      question.addEventListener('click', () => {
        const item = question.closest('.kp-faq-item');
        if (!item) return;
        const wasOpen = item.classList.contains('open');
        questions.forEach((other) => {
          if (other === question) return;
          const otherItem = other.closest('.kp-faq-item');
          if (otherItem) otherItem.classList.remove('open');
          setExpanded(other, false);
          const otherPanel = otherItem && otherItem.querySelector('.kp-faq-a');
          if (otherPanel) otherPanel.setAttribute('aria-hidden', 'true');
        });
        item.classList.toggle('open', !wasOpen);
        setExpanded(question, !wasOpen);
        const ownPanel = item.querySelector('.kp-faq-a');
        if (ownPanel) ownPanel.setAttribute('aria-hidden', wasOpen ? 'true' : 'false');
      });
    });
  }

  /* ---------- 4. Hero browser mock carousel ---------- */
  function initCarousel() {
    const dots = all('[data-mock-dot]');
    const pages = all('[data-mock-page]');
    const threads = all('[data-mock-thread]');
    if (!dots.length) return;

    function show(index) {
      const i = Number(index);
      pages.forEach((page) => {
        if (typeof page.hidden === 'boolean') page.hidden = Number(page.getAttribute('data-mock-page')) !== i;
      });
      threads.forEach((thread) => {
        if (typeof thread.hidden === 'boolean') thread.hidden = Number(thread.getAttribute('data-mock-thread')) !== i;
      });
      dots.forEach((dot) => {
        const active = Number(dot.getAttribute('data-mock-dot')) === i;
        dot.classList.toggle('is-active', active);
        dot.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }

    dots.forEach((dot, index) => {
      dot.addEventListener('click', () => show(dot.getAttribute('data-mock-dot')));
      dot.addEventListener('keydown', (event) => {
        if (!event) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % dots.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + dots.length) % dots.length;
        if (next < 0) return;
        event.preventDefault();
        show(dots[next].getAttribute('data-mock-dot'));
        dots[next].focus();
      });
    });
    show(0);
  }

  /* ---------- 5. Workflow tabs + Chat / Convert toggle ---------- */
  function initDemo() {
    const tabs = all('[data-demo-tab]');
    const modeButtons = all('[data-mode]');
    if (!tabs.length) return;

    const copy = {
      keel: {
        kicker: 'PAGE CONTEXT',
        title: 'Summarize this report',
        prompt: '“Summarize this report for me.”',
        answerTitle: 'Keel reads the open page',
        answer: "Keel reads the page you're signed in to, then drafts a short summary you can use anywhere — without a single copy or paste."
      },
      code: {
        kicker: 'LOCALHOST:3000 / BUILD LOG',
        title: 'Why is this build failing?',
        prompt: '“Why is this build failing?”',
        answerTitle: 'Keel Code joins the tab',
        answer: 'Keel Code reads the error on the page, checks your project, and suggests the fix in your editor.'
      },
      everyday: {
        kicker: 'INBOX / PROMOTIONS',
        title: 'Tidy up these emails',
        prompt: '“Show me the newsletters I never read.”',
        answerTitle: 'A list, ready to review',
        answer: 'Keel identifies marketing emails and automated notifications, then presents them as a list for you to review before deleting.'
      },
      background: {
        kicker: 'SCHEDULED TASK / DAILY',
        title: 'Check these prices each morning',
        prompt: '“Check these prices every morning.”',
        answerTitle: 'Runs in the background',
        answer: 'Keel checks the sites on a schedule and leaves a short digest in your session history for whenever you pick it up.'
      }
    };

    function write(selector, value) {
      const node = document.querySelector(selector);
      if (node && typeof value === 'string') node.textContent = value;
    }

    function setTab(key, moveFocus) {
      const item = copy[key];
      if (!item) return;
      tabs.forEach((tab) => {
        const active = tab.getAttribute('data-demo-tab') === key;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        tab.tabIndex = active ? 0 : -1;
        if (active && moveFocus && typeof tab.focus === 'function') tab.focus();
      });
      write('[data-demo-kicker]', item.kicker);
      write('[data-demo-title]', item.title);
      write('[data-demo-prompt]', item.prompt);
      write('[data-demo-answer-title]', item.answerTitle);
      write('[data-demo-answer]', item.answer);
    }

    function setMode(mode) {
      modeButtons.forEach((button) => {
        const active = button.getAttribute('data-mode') === mode;
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      const convertView = document.querySelector('[data-mode-view="convert"]');
      const chatView = document.querySelector('.cl-demo-window');
      if (convertView) convertView.hidden = mode !== 'convert';
      if (chatView) chatView.hidden = mode === 'convert';
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => setTab(tab.getAttribute('data-demo-tab'), false));
      tab.addEventListener('keydown', (event) => {
        if (!event) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        if (next < 0) return;
        event.preventDefault();
        setTab(tabs[next].getAttribute('data-demo-tab'), true);
      });
    });
    modeButtons.forEach((button) => {
      button.addEventListener('click', () => setMode(button.getAttribute('data-mode')));
    });
    setTab('keel', false);
    setMode('chat');
  }

  /* ---------- 6. Capability preview switching ---------- */
  function initCapabilities() {
    const buttons = all('[data-cap]');
    if (!buttons.length) return;
    const copy = {
      api: {
        caption: 'Reach the web that has no API',
        message: 'I found three unpaid invoices in the portal and drafted a summary for you.'
      },
      panel: {
        caption: 'Your whole setup, in the side panel',
        message: 'Your skills, plugins, and connectors are ready to use right here — nothing to set up in the browser.'
      },
      session: {
        caption: 'Your session follows you',
        message: 'This conversation is saved to your account. Pick it up on desktop or mobile without re-explaining.'
      },
      access: {
        caption: 'Three ways to access the extension',
        message: 'Use the side panel, open Keel, or bring Keel Code into the conversation — it is the same session everywhere.'
      }
    };

    function setCap(key) {
      const item = copy[key];
      if (!item) return;
      buttons.forEach((button) => {
        const active = button.getAttribute('data-cap') === key;
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
      const preview = document.querySelector('[data-cap-preview]');
      if (preview && typeof preview.setAttribute === 'function') preview.setAttribute('data-cap-active', key);
      const caption = document.querySelector('[data-cap-caption]');
      if (caption) caption.textContent = item.caption;
      const message = document.querySelector('[data-cap-message]');
      if (message) message.textContent = item.message;
      const tools = document.querySelector('[data-cap-tools]');
      if (tools) tools.hidden = key !== 'panel';
    }
    buttons.forEach((button) => button.addEventListener('click', () => setCap(button.getAttribute('data-cap'))));
    setCap('api');
  }

  /* ---------- 7. Stay in control segmented tabs ---------- */
  function initSafety() {
    const tabs = all('[data-safety-tab]');
    const panels = all('[data-safety-panel]');
    if (!tabs.length) return;

    function setTab(key, moveFocus) {
      tabs.forEach((tab) => {
        const active = tab.getAttribute('data-safety-tab') === key;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        tab.tabIndex = active ? 0 : -1;
        if (active && moveFocus && typeof tab.focus === 'function') tab.focus();
      });
      panels.forEach((panel) => {
        if (typeof panel.hidden === 'boolean') {
          panel.hidden = panel.getAttribute('data-safety-panel') !== key;
        }
      });
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => setTab(tab.getAttribute('data-safety-tab'), false));
      tab.addEventListener('keydown', (event) => {
        if (!event) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
        if (next < 0) return;
        event.preventDefault();
        setTab(tabs[next].getAttribute('data-safety-tab'), true);
      });
    });
    setTab('builtin', false);
  }

  /* ---------- 8. Sign-in / contact modal ---------- */
  function initAuth() {
    const modal = document.getElementById('cl-auth-modal');
    if (!modal) return;
    const formView = modal.querySelector('[data-auth-form-view]');
    const success = modal.querySelector('[data-auth-success]');
    const form = modal.querySelector('.kp-auth-form');
    const input = document.getElementById('cl-auth-email');
    const error = document.getElementById('cl-auth-error');
    const demo = modal.querySelector('[data-auth-demo]');
    let lastFocus = null;

    function open(trigger) {
      lastFocus = trigger || document.activeElement;
      if (initNav._closeAll) initNav._closeAll();
      if (initMobile._close) initMobile._close();
      modal.hidden = false;
      if (formView) formView.hidden = false;
      if (success) success.hidden = true;
      if (error) error.hidden = true;
      if (input) {
        input.value = '';
        input.removeAttribute('aria-invalid');
        if (typeof input.focus === 'function') input.focus();
      }
    }
    function close() {
      modal.hidden = true;
      if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    }
    initAuth._close = close;

    function signIn() {
      try { localStorage.setItem('keel_logged_in', 'true'); } catch { /* storage unavailable */ }
      if (formView) formView.hidden = true;
      if (success) success.hidden = false;
      const link = success && success.querySelector('a[href="/login"]');
      if (link && typeof link.focus === 'function') link.focus();
    }

    document.addEventListener('click', (event) => {
      const target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      const trigger = target.closest('[data-auth-open]');
      if (!trigger) return;
      event.preventDefault();
      open(trigger);
    });
    all('[data-auth-close]', modal).forEach((button) => button.addEventListener('click', close));

    if (form && input && error) {
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const value = (input.value || '').trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
          error.hidden = false;
          input.setAttribute('aria-invalid', 'true');
          input.focus();
          return;
        }
        signIn();
      });
      input.addEventListener('input', () => {
        error.hidden = true;
        input.removeAttribute('aria-invalid');
      });
    }
    if (demo) demo.addEventListener('click', signIn);

    modal.addEventListener('keydown', (event) => {
      if (!event || event.key !== 'Tab') return;
      const focusable = all('a[href], button, input', modal)
        .filter((node) => !node.disabled && node.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  /* ---------- 9. Guide / news modal ---------- */
  function initGuides() {
    const modal = document.getElementById('cl-guide-modal');
    if (!modal) return;
    const labelNode = modal.querySelector('[data-guide-label]');
    const titleNode = document.getElementById('cl-guide-title');
    const bodyNode = document.getElementById('cl-guide-body');
    const closeButton = modal.querySelector('.kp-modal-close');
    let lastFocus = null;

    const guides = {
      troubleshooting: {
        label: 'Guide',
        title: 'Keel in Chrome Troubleshooting',
        html: '<p>This article helps you resolve common issues with Keel in Chrome and explains how to provide feedback.</p>' +
          '<ul><li>Confirm the extension is enabled for the site you are on and reload the tab.</li>' +
          '<li>Check that you are signed in to Keel and that the side panel is open.</li>' +
          '<li>If an action stops unexpectedly, review Permissions Mode and site access in the panel.</li></ul>' +
          '<p><a href="/requirements">Read the support docs</a></p>'
      },
      safetyguide: {
        label: 'Guide',
        title: 'Using Keel in Chrome safely',
        html: '<p>Pages can hide instructions meant to redirect Keel. These habits help you stay in control:</p>' +
          '<ul><li>Start with trusted sites and familiar workflows.</li>' +
          '<li>Avoid financial transactions, password management, and sensitive personal data.</li>' +
          '<li>Review what Keel proposes before it clicks, types, or submits.</li>' +
          '<li>Keep permissions narrow and remove site access you no longer need.</li></ul>' +
          '<p>Read more in the <a href="/privacy">safety and privacy documentation</a>.</p>'
      },
      news: {
        label: 'Latest news',
        title: 'Keel in Chrome is now generally available',
        html: '<p>Keel can work through tasks without approving each step, with a safety check before each action. ' +
          'You can still choose to approve one site at a time in Permissions Mode.</p>' +
          '<p><a href="/roadmap">Read the full announcement</a></p>'
      },
      sources: {
        label: 'Google',
        title: 'Add Keel to Preferred Sources',
        html: '<p>Preferred Sources lets you tell Google which publishers you want to see more of in Top Stories.</p>' +
          '<ol><li>Open your Google Search settings.</li><li>Choose <strong>Preferred Sources</strong>.</li>' +
          '<li>Add this site to your sources list.</li></ol>' +
          '<p>Learn more on the <a href="/roadmap">updates page</a>.</p>'
      }
    };

    function close() {
      modal.hidden = true;
      if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    }
    initGuides._close = close;

    document.addEventListener('click', (event) => {
      const target = event && event.target;
      if (!target || typeof target.closest !== 'function') return;
      const trigger = target.closest('[data-guide]');
      if (!trigger) return;
      const guide = guides[trigger.getAttribute('data-guide')];
      if (!guide) return;
      event.preventDefault();
      lastFocus = trigger;
      if (initNav._closeAll) initNav._closeAll();
      if (initMobile._close) initMobile._close();
      if (labelNode) labelNode.textContent = guide.label;
      if (titleNode) titleNode.textContent = guide.title;
      if (bodyNode) bodyNode.innerHTML = guide.html;
      modal.hidden = false;
      if (closeButton && typeof closeButton.focus === 'function') closeButton.focus();
    });
    all('[data-guide-close]', modal).forEach((button) => button.addEventListener('click', close));

    modal.addEventListener('keydown', (event) => {
      if (!event || event.key !== 'Tab') return;
      const focusable = all('a[href], button', modal)
        .filter((node) => !node.disabled && node.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  /* ---------- 10. Footer link search ---------- */
  function initFooterSearch() {
    const form = document.querySelector('.kp-footer-search');
    const input = form && form.querySelector('input[type="search"]');
    const status = document.getElementById('cl-search-status');
    if (!form || !input) return;
    const items = all('.cl-footer-cols li');

    function filter() {
      const query = (input.value || '').trim().toLowerCase();
      let shown = 0;
      items.forEach((item) => {
        const match = !query || (item.textContent || '').toLowerCase().includes(query);
        item.hidden = !match;
        if (match) shown += 1;
      });
      if (status) {
        status.textContent = !query ? '' : shown
          ? shown + (shown === 1 ? ' matching link' : ' matching links')
          : 'No matching links. Try “chrome”, “privacy” or “code”.';
      }
    }
    form.addEventListener('submit', (event) => { event.preventDefault(); filter(); });
    input.addEventListener('input', () => { if (!(input.value || '').trim()) filter(); });
  }

  /* ---------- 11. Language selector ---------- */
  function initLanguage() {
    const select = document.getElementById('cl-language');
    const status = document.getElementById('cl-lang-status');
    if (!select || !status) return;
    select.addEventListener('change', () => {
      const label = select.options && select.selectedIndex >= 0
        ? select.options[select.selectedIndex].textContent : select.value;
      status.textContent = 'Language preference: ' + label + ' (demo only — this page is shown in English).';
    });
  }

  /* ---------- 12. Global Escape ---------- */
  function initKeys() {
    document.addEventListener('keydown', (event) => {
      if (!event || (event.key !== 'Escape' && event.key !== 'Esc')) return;
      if (initAuth._close) initAuth._close();
      if (initGuides._close) initGuides._close();
      if (initNav._closeAll) initNav._closeAll();
      if (initMobile._close) initMobile._close();
    });
  }

  function init() {
    safe(initNav);
    safe(initMobile);
    safe(initFaq);
    safe(initCarousel);
    safe(initDemo);
    safe(initCapabilities);
    safe(initSafety);
    safe(initAuth);
    safe(initGuides);
    safe(initFooterSearch);
    safe(initLanguage);
    safe(initKeys);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

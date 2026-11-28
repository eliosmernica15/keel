'use strict';

/* Keel marketing landing page — vanilla JS interactions only.
   No dependencies, no fabricated URLs, no console errors.
   Every query is guarded; a missing element never breaks the page. */

function safe(setup) {
  try {
    setup();
  } catch {
    /* defensive: UI enhancements must never throw */
  }
}

function setExpanded(node, expanded) {
  if (node && typeof node.setAttribute === 'function') {
    node.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
}

/* ---------- 1. Mega-menu nav (hover, click, outside click, Escape, focus) ---------- */
function initNav() {
  const navItems = Array.from(document.querySelectorAll('.l-nav-item[data-menu]'));
  if (navItems.length === 0) return;

  const pins = new WeakMap();
  let pointerDown = false;

  function setNavOpen(item, openState) {
    if (!item || !item.classList) return;
    item.classList.toggle('open', openState);
    if (!openState) pins.set(item, false);
    const trigger = item.querySelector('.l-nav-trigger');
    setExpanded(trigger, openState);
    const mega = item.querySelector('.l-mega');
    if (mega && typeof mega.setAttribute === 'function') {
      mega.setAttribute('aria-hidden', openState ? 'false' : 'true');
    }
  }

  function closeAllNavItems(except) {
    navItems.forEach((item) => {
      if (item !== except) setNavOpen(item, false);
    });
  }

  navItems.forEach((item, index) => {
    const trigger = item.querySelector('.l-nav-trigger');
    pins.set(item, false);
    if (trigger && !trigger.hasAttribute('aria-expanded')) setExpanded(trigger, false);
    const mega = item.querySelector('.l-mega');
    if (mega && !mega.hasAttribute('aria-hidden')) mega.setAttribute('aria-hidden', 'true');

    let suppressFocusOpen = false;

    item.addEventListener('mouseenter', () => {
      if (suppressFocusOpen) return;
      closeAllNavItems(item);
      setNavOpen(item, true);
    });

    item.addEventListener('mouseleave', () => {
      if (pins.get(item) === true) return;
      if (item.contains(document.activeElement)) return;
      setNavOpen(item, false);
    });

    if (trigger) {
      trigger.addEventListener('pointerdown', () => {
        pointerDown = true;
        suppressFocusOpen = true;
      });
      trigger.addEventListener('click', () => {
        pointerDown = false;
        const wasOpen = pins.get(item) === true;
        if (wasOpen) {
          setNavOpen(item, false);
          pins.set(item, false);
          suppressFocusOpen = true;
        } else {
          closeAllNavItems(item);
          setNavOpen(item, true);
          pins.set(item, true);
        }
      });
      trigger.addEventListener('keydown', (event) => {
        if (!event) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % navItems.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + navItems.length) % navItems.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = navItems.length - 1;
        if (next < 0 || next === index) return;
        const nextTrigger = navItems[next].querySelector('.l-nav-trigger');
        if (nextTrigger) {
          event.preventDefault();
          closeAllNavItems(navItems[next]);
          setNavOpen(navItems[next], true);
          nextTrigger.focus();
        }
      });
    }

    item.addEventListener('focusin', () => {
      if (suppressFocusOpen || pointerDown) return;
      closeAllNavItems(item);
      setNavOpen(item, true);
    });

    item.addEventListener('focusout', (event) => {
      const next = event && event.relatedTarget;
      if (next && typeof item.contains === 'function' && item.contains(next)) return;
      if (pins.get(item) !== true) setNavOpen(item, false);
      suppressFocusOpen = false;
    });
  });

  document.addEventListener('click', (event) => {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;
    if (!target.closest('.l-nav-item')) closeAllNavItems();
  });
  window.addEventListener('pointerup', () => { pointerDown = false; });
  window.addEventListener('pointercancel', () => { pointerDown = false; });

  initNav._closeAll = closeAllNavItems;
}

/* ---------- 2. FAQ accordion (one item open at a time) ---------- */
function initFaq() {
  const questions = Array.from(document.querySelectorAll('button.l-faq-q'));
  if (questions.length === 0) return;

  questions.forEach((question) => {
    if (!question.hasAttribute('aria-expanded')) setExpanded(question, false);
    const panel = document.getElementById(question.getAttribute('aria-controls') || '');
    if (panel) panel.setAttribute('aria-hidden', 'true');

    question.addEventListener('click', () => {
      const item = question.closest('.l-faq-item');
      if (!item) return;
      const wasOpen = item.classList.contains('open');

      questions.forEach((other) => {
        if (other === question) return;
        const otherItem = other.closest('.l-faq-item');
        if (otherItem) otherItem.classList.remove('open');
        setExpanded(other, false);
        const otherPanel = otherItem && otherItem.querySelector('.l-faq-a');
        if (otherPanel) otherPanel.setAttribute('aria-hidden', 'true');
      });

      item.classList.toggle('open', !wasOpen);
      setExpanded(question, !wasOpen);
      const ownPanel = item.querySelector('.l-faq-a');
      if (ownPanel) ownPanel.setAttribute('aria-hidden', wasOpen ? 'true' : 'false');
    });
  });
}

/* ---------- 3. Individual / Team & Enterprise plan toggle ---------- */
function initPlanToggle() {
  const tabs = Array.from(document.querySelectorAll('[data-plan-tab]'));
  if (tabs.length === 0) return;

  const panels = Array.from(document.querySelectorAll('[data-plan-panel]'));

  function select(key, moveFocus) {
    if (!key) return;
    tabs.forEach((tab) => {
      const active = tab.getAttribute('data-plan-tab') === key;
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.hidden = panel.getAttribute('data-plan-panel') !== key;
    });
    if (moveFocus) {
      const target = tabs.find((tab) => tab.getAttribute('data-plan-tab') === key);
      if (target && typeof target.focus === 'function') target.focus();
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(tab.getAttribute('data-plan-tab'), false));
    tab.addEventListener('keydown', (event) => {
      if (!event) return;
      let next = -1;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      if (next < 0 || next === index) return;
      event.preventDefault();
      select(tabs[next].getAttribute('data-plan-tab'), true);
    });
  });

  select('individual', false);
}

/* ---------- 4. Mobile menu ---------- */
function initMobileMenu() {
  const toggle = document.querySelector('.l-nav-toggle');
  const menu = document.querySelector('.l-mobile-menu');
  if (!toggle || !menu) return;
  if (!toggle.hasAttribute('aria-expanded')) setExpanded(toggle, false);

  function closeMobileMenu() {
    menu.classList.remove('open');
    setExpanded(toggle, false);
    toggle.setAttribute('aria-label', 'Open menu');
  }
  initMobileMenu._close = closeMobileMenu;

  toggle.addEventListener('click', () => {
    const willOpen = !menu.classList.contains('open');
    menu.classList.toggle('open', willOpen);
    setExpanded(toggle, willOpen);
    toggle.setAttribute('aria-label', willOpen ? 'Close menu' : 'Open menu');
  });

  menu.addEventListener('click', (event) => {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;
    if (target.closest('a, button')) closeMobileMenu();
  });

  document.addEventListener('click', (event) => {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;
    if (target.closest('.l-nav-toggle, .l-mobile-menu')) return;
    if (menu.classList.contains('open')) closeMobileMenu();
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 980 && menu.classList.contains('open')) closeMobileMenu();
  });
}

/* ---------- 5. Dismissible latest news chip ---------- */
function initNews() {
  const news = document.querySelector('.l-news');
  const close = document.querySelector('.l-news-close');
  const KEY = 'keel_landing_news_dismissed';

  function hideNews(remember) {
    if (!news) return;
    news.classList.add('hidden');
    if (remember) {
      try { localStorage.setItem(KEY, 'true'); } catch { /* storage unavailable */ }
    }
  }
  try {
    if (localStorage.getItem(KEY) === 'true') hideNews(false);
  } catch { /* storage unavailable */ }
  if (close) close.addEventListener('click', () => hideNews(true));
}

/* ---------- 6. Sign-in / contact modal ---------- */
function initAuthModal() {
  const modal = document.getElementById('l-auth-modal');
  if (!modal) return;

  const formView = modal.querySelector('[data-auth-form-view]');
  const success = modal.querySelector('[data-auth-success]');
  const form = modal.querySelector('.l-auth-form');
  const input = document.getElementById('l-auth-email');
  const error = document.getElementById('l-auth-error');
  const demo = modal.querySelector('[data-auth-demo]');
  const title = document.getElementById('l-auth-title');
  const desc = document.getElementById('l-auth-desc');
  const submit = modal.querySelector('.l-auth-form .l-modal-submit');
  const google = modal.querySelector('.l-modal-google');
  const googleNote = modal.querySelector('.l-modal-note');
  const divider = modal.querySelector('.l-modal-divider');
  let lastFocus = null;

  const INTENTS = {
    login: {
      title: 'Continue with Keel',
      desc: 'Sign in to take your projects from desktop to web to mobile.',
      submit: 'Continue with email',
      google: true,
    },
    trial: {
      title: 'Try Keel',
      desc: 'Create your local Keel session and start a conversation.',
      submit: 'Continue with email',
      google: true,
    },
    sales: {
      title: 'Talk to Keel sales',
      desc: 'Tell us where you work and we will get in touch.',
      submit: 'Request a demo',
      google: false,
    },
  };

  function open(trigger) {
    lastFocus = trigger || document.activeElement;
    const intent = INTENTS[(trigger && trigger.getAttribute('data-auth-intent')) || 'login'] || INTENTS.login;

    if (title) title.textContent = intent.title;
    if (desc) desc.textContent = intent.desc;
    if (submit) submit.textContent = intent.submit;
    if (google) google.hidden = !intent.google;
    if (googleNote) googleNote.hidden = !intent.google;
    if (divider) divider.hidden = !intent.google;

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
    if (modal.hidden) return;
    modal.hidden = true;
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
  }

  function signIn() {
    try { localStorage.setItem('keel_logged_in', 'true'); } catch { /* storage unavailable */ }
    if (formView) formView.hidden = true;
    if (success) success.hidden = false;
    const continueLink = success && success.querySelector('a[href="/login"]');
    if (continueLink && typeof continueLink.focus === 'function') continueLink.focus();
  }

  document.addEventListener('click', (event) => {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;
    const trigger = target.closest('[data-auth-open]');
    if (!trigger) return;
    event.preventDefault();
    // Sign-in and sign-up now happen on the dedicated /login page.
    const intent = trigger.getAttribute('data-auth-intent') || 'login';
    const next = trigger.getAttribute('href') || trigger.getAttribute('data-next') || '';
    window.location.assign('/login?intent=' + encodeURIComponent(intent) +
      (next ? '&next=' + encodeURIComponent(next) : ''));
  });

  modal.querySelectorAll('[data-auth-close]').forEach((button) => {
    button.addEventListener('click', close);
  });

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
    const focusable = Array.from(modal.querySelectorAll('a[href], button, input'))
      .filter((node) => !node.disabled && node.getClientRects().length > 0);
    if (focusable.length === 0) return;
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

  initAuthModal._close = close;
}

/* ---------- 7. Footer help search (filters links + FAQ) ---------- */
function initFooterSearch() {
  const form = document.querySelector('.l-footer-search');
  const input = form && form.querySelector('input[type="search"]');
  const status = document.querySelector('.l-search-status');
  if (!form || !input) return;

  const items = Array.from(document.querySelectorAll('.l-footer-col li'));
  const faqs = Array.from(document.querySelectorAll('.l-faq-item'));

  function filter() {
    const query = (input.value || '').trim().toLowerCase();
    let shown = 0;

    items.forEach((item) => {
      const match = !query || (item.textContent || '').toLowerCase().includes(query);
      item.hidden = !match;
      if (match) shown += 1;
    });

    faqs.forEach((item) => {
      const match = !query || (item.textContent || '').toLowerCase().includes(query);
      item.hidden = !match;
      if (match) {
        shown += 1;
      } else {
        item.classList.remove('open');
        const button = item.querySelector('.l-faq-q');
        const panel = item.querySelector('.l-faq-a');
        setExpanded(button, false);
        if (panel) panel.setAttribute('aria-hidden', 'true');
      }
    });

    if (status) {
      status.textContent = !query ? '' : shown
        ? shown + (shown === 1 ? ' matching result' : ' matching results')
        : 'No matching results. Try “download”, “privacy” or “code”.';
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    filter();
  });
  input.addEventListener('input', filter);
}

/* ---------- 8. Preferred sources toggle ---------- */
function initPreferredSources() {
  const button = document.querySelector('.l-preferred');
  if (!button) return;
  const KEY = 'keel_preferred_sources';
  const ON = 'Add to Preferred Sources';
  const OFF = 'Added to Preferred Sources';

  function render(active) {
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    button.textContent = active ? OFF : ON;
  }

  let active = false;
  try { active = localStorage.getItem(KEY) === 'true'; } catch { /* storage unavailable */ }
  render(active);

  button.addEventListener('click', () => {
    active = !active;
    render(active);
    try { localStorage.setItem(KEY, active ? 'true' : 'false'); } catch { /* storage unavailable */ }
  });
}

/* ---------- 9. Language selector ---------- */
function initLanguage() {
  const select = document.querySelector('.l-lang');
  const status = document.querySelector('.l-lang-status');
  if (!select) return;
  const KEY = 'keel_language';

  function apply(announce) {
    const label = select.options && select.selectedIndex >= 0
      ? select.options[select.selectedIndex].text
      : select.value;
    if (status) status.textContent = announce ? 'Language preference: ' + label : '';
    try { localStorage.setItem(KEY, select.value); } catch { /* storage unavailable */ }
  }

  try {
    const saved = localStorage.getItem(KEY);
    if (saved && Array.from(select.options).some((option) => option.value === saved)) {
      select.value = saved;
    }
  } catch { /* storage unavailable */ }

  select.addEventListener('change', () => apply(true));
  apply(false);
}

/* ---------- Global Escape ---------- */
function initGlobalKeys() {
  document.addEventListener('keydown', (event) => {
    if (!event || (event.key !== 'Escape' && event.key !== 'Esc')) return;
    if (typeof initAuthModal._close === 'function') initAuthModal._close();
    if (typeof initNav._closeAll === 'function') initNav._closeAll();
    if (typeof initMobileMenu._close === 'function') initMobileMenu._close();
  });
}

/* ---------- Boot ---------- */
function init() {
  safe(initNav);
  safe(initFaq);
  safe(initPlanToggle);
  safe(initMobileMenu);
  safe(initNews);
  safe(initAuthModal);
  safe(initFooterSearch);
  safe(initPreferredSources);
  safe(initLanguage);
  safe(initGlobalKeys);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
  init();
}

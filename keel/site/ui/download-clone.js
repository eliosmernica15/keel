'use strict';

/* /download clone page — vanilla JS interactions only.
   No dependencies, no fabricated download URLs, no console errors.
   Every query is guarded; a missing element never breaks the page. */

/* Runs a setup step without letting one broken section stop the rest. */
function safe(setup) {
  try {
    setup();
  } catch {
    /* defensive: UI enhancements must never throw */
  }
}

/* Shared aria helper: only writes when the element exists. */
function setExpanded(node, expanded) {
  if (node && typeof node.setAttribute === 'function') {
    node.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
}

/* ---------- 1. Mega-menu nav (hover, click, outside click, Escape, focus) ---------- */
function initNav() {
  const navItems = Array.from(document.querySelectorAll('.kp-nav-item[data-menu]'));
  if (navItems.length === 0) return;

  // A click-pinned menu stays open until Escape, another menu or an outside click.
  const pins = new WeakMap();
  let pointerDown = false;

  function setNavOpen(item, openState) {
    if (!item || !item.classList) return;
    item.classList.toggle('open', openState);
    if (!openState) pins.set(item, false);
    const trigger = item.querySelector('.kp-nav-trigger');
    setExpanded(trigger, openState);
    const mega = item.querySelector('.kp-mega');
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
    const trigger = item.querySelector('.kp-nav-trigger');
    const mega = item.querySelector('.kp-mega');
    pins.set(item, false);
    if (trigger && !trigger.hasAttribute('aria-expanded')) setExpanded(trigger, false);
    if (mega && !mega.hasAttribute('aria-hidden')) mega.setAttribute('aria-hidden', 'true');

    // Closing by click should not be undone by the focus that the click just caused.
    let suppressFocusOpen = false;

    item.addEventListener('mouseenter', () => {
      if (suppressFocusOpen) return;
      closeAllNavItems(item);
      setNavOpen(item, true);
    });

    item.addEventListener('mouseleave', () => {
      if (pins.get(item) === true) return;
      if (item.contains(document.activeElement)) return; // keyboard user is inside
      setNavOpen(item, false);
    });

    if (trigger) {
      // Mouse focus must not pre-open a menu that the click is about to toggle.
      trigger.addEventListener('pointerdown', () => {
        pointerDown = true;
        suppressFocusOpen = true;
      });
      trigger.addEventListener('click', () => {
        pointerDown = false;
        // Decide from the explicit pin state, not the visual class: hover may
        // already have opened the menu before the click arrives.
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

      // Arrow keys and Home/End move between triggers and open the new menu.
      trigger.addEventListener('keydown', (event) => {
        if (!event) return;
        let next = -1;
        if (event.key === 'ArrowRight') next = (index + 1) % navItems.length;
        else if (event.key === 'ArrowLeft') next = (index - 1 + navItems.length) % navItems.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = navItems.length - 1;
        if (next < 0 || next === index) return;
        const nextTrigger = navItems[next].querySelector('.kp-nav-trigger');
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
    if (!target.closest('.kp-nav-item')) closeAllNavItems();
  });
  window.addEventListener('pointerup', () => { pointerDown = false; });
  window.addEventListener('pointercancel', () => { pointerDown = false; });

  initNav._closeAll = closeAllNavItems;
}

/* ---------- 2. FAQ accordion (one item open at a time) ---------- */
function initFaq() {
  const questions = Array.from(document.querySelectorAll('button.kp-faq-q'));
  if (questions.length === 0) return;

  questions.forEach((question) => {
    if (!question.hasAttribute('aria-expanded')) setExpanded(question, false);
    const initialPanel = document.getElementById(question.getAttribute('aria-controls') || '');
    if (initialPanel) initialPanel.setAttribute('aria-hidden', 'true');

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
      const panel = item.querySelector('.kp-faq-a');
      if (panel && typeof panel.setAttribute === 'function') {
        panel.setAttribute('aria-hidden', wasOpen ? 'true' : 'false');
      }
    });
  });
}

/* ---------- 3. Mobile menu (toggle, link click, outside click, Escape) ---------- */
function initMobileMenu() {
  const toggle = document.querySelector('.kp-nav-toggle');
  const menu = document.querySelector('.kp-mobile-menu');
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
    if (target.closest('.kp-nav-toggle, .kp-mobile-menu')) return;
    if (menu.classList.contains('open')) closeMobileMenu();
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth > 760 && menu.classList.contains('open')) closeMobileMenu();
  });
}

/* ---------- 4. Chat widget (toggle, close, graceful fallback trigger) ---------- */
function initChat() {
  const panel = document.querySelector('.kp-chat-panel');
  const close = document.querySelector('.kp-chat-close');
  let toggle = document.querySelector('.kp-chat-toggle');

  function usable(node) {
    return !!node && node !== close &&
      !(close && typeof close.contains === 'function' && close.contains(node)) &&
      !(panel && typeof panel.contains === 'function' && panel.contains(node));
  }
  if (!toggle && panel) {
    try {
      if (panel.id) {
        const escaped = (window.CSS && CSS.escape)
          ? CSS.escape(panel.id)
          : panel.id.replace(/["\\]/g, '\\$&');
        const candidate = document.querySelector('[aria-controls="' + escaped + '"]');
        if (usable(candidate)) toggle = candidate;
      }
    } catch { /* skip this strategy */ }
    try {
      if (!toggle) {
        const candidate = document.querySelector('[data-chat-toggle]');
        if (usable(candidate)) toggle = candidate;
      }
    } catch { /* skip this strategy */ }
    try {
      if (!toggle) {
        const buttons = document.querySelectorAll('button, [role="button"]');
        for (const button of buttons) {
          if (!usable(button)) continue;
          const cls = button.className;
          const className = (cls && typeof cls === 'object' && 'baseVal' in cls) ? cls.baseVal : (cls || '');
          const hay = className + ' ' + (button.getAttribute('aria-label') || '') + ' ' + (button.textContent || '');
          if (/chat/i.test(hay)) {
            toggle = button;
            break;
          }
        }
      }
    } catch { /* skip this strategy */ }
  }

  function closeChat() {
    if (panel) panel.classList.remove('open');
    setExpanded(toggle, false);
    if (toggle && typeof toggle.setAttribute === 'function') {
      toggle.setAttribute('aria-label', 'Open chat');
    }
  }
  initChat._close = closeChat;
  closeChat();

  if (toggle) {
    toggle.addEventListener('click', () => {
      if (!panel) return;
      const willOpen = !panel.classList.contains('open');
      panel.classList.toggle('open', willOpen);
      setExpanded(toggle, willOpen);
      toggle.setAttribute('aria-label', willOpen ? 'Close chat' : 'Open chat');
    });
  }
  if (close) close.addEventListener('click', closeChat);
}

/* ---------- 5. News chip (dismissible, dismissal remembered) ---------- */
function initNews() {
  const news = document.querySelector('.kp-news');
  const close = document.querySelector('.kp-news-close');
  const KEY = 'keel_news_dismissed';

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

/* ---------- 6. Copy buttons ([data-copy] with clipboard fallback) ---------- */
function initCopy() {
  const buttons = Array.from(document.querySelectorAll('[data-copy]'));
  if (buttons.length === 0) return;

  const originals = new WeakMap();
  const timers = new WeakMap();

  async function writeToClipboard(text) {
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch { /* fall through to legacy copy */ }
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-1000px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      let copied = false;
      try {
        copied = document.execCommand('copy');
      } catch { /* clipboard unavailable */ }
      textarea.remove();
      return copied;
    } catch {
      return false;
    }
  }

  buttons.forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await writeToClipboard(button.getAttribute('data-copy') || '');
        if (!originals.has(button)) originals.set(button, button.textContent);
        const original = originals.get(button);
        button.textContent = 'Copied';
        const previous = timers.get(button);
        if (previous) clearTimeout(previous);
        const timer = setTimeout(() => {
          button.textContent = original;
          originals.delete(button);
          timers.delete(button);
        }, 1600);
        timers.set(button, timer);
      } catch {
        /* never throw from a copy button */
      }
    });
  });
}

/* ---------- 7. Manifest-driven downloads + platform tabs ----------
   Sources are same-origin only. A button is enabled only when the manifest
   says available === true, verified === true, and carries an HTTPS URL,
   a positive byte size and a 64-character SHA-256. No fabricated URLs. */
const MANIFEST_SOURCES = ['/download.json', '/api/download-manifest'];
const SHA_RE = /^[0-9a-f]{64}$/i;
const PLATFORMS = {
  windows: 'Windows',
  'windows-arm64': 'Windows arm64',
  macos: 'macOS',
  linux: 'Linux',
};

function initDownloads() {
  const tabs = Array.from(document.querySelectorAll('.kp-platform-tab[data-platform]'));
  const panel = document.getElementById('kp-download-panel');
  const heroButton = document.querySelector('.kp-download-btn');
  const heroNote = panel ? panel.querySelector('[data-channel-note]') : null;
  let manifestDoc = null;
  let activePlatform = 'windows';

  async function fetchManifest() {
    for (const url of MANIFEST_SOURCES) {
      try {
        const response = await fetch(url, {
          cache: 'no-cache',
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) continue;
        const doc = await response.json();
        if (doc && typeof doc === 'object' && typeof doc.version === 'string'
            && doc.channels && typeof doc.channels === 'object') {
          return doc;
        }
      } catch {
        /* try the next same-origin source */
      }
    }
    return null;
  }

  function safeUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(String(value), window.location.href);
      if (url.protocol === 'https:') return url.href;
      if (url.protocol === 'http:' && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(url.hostname)) {
        return url.href;
      }
    } catch { /* malformed URL */ }
    return null;
  }

  function channelInfo(key) {
    return (manifestDoc && manifestDoc.channels && manifestDoc.channels[key]) || null;
  }

  function isDownloadable(channel) {
    return !!channel && channel.available === true && channel.verified === true
      && Number.isFinite(Number(channel.size)) && Number(channel.size) > 0
      && SHA_RE.test(String(channel.sha256 || '')) && safeUrl(channel.url) !== null;
  }

  function fmtBytes(bytes) {
    const n = Number(bytes);
    if (!Number.isFinite(n) || n <= 0) return null;
    const mb = n / 1024 / 1024;
    return (mb >= 100 ? mb.toFixed(1) : mb.toFixed(2)) + ' MB';
  }

  function noteFor(key, longForm) {
    const info = channelInfo(key);
    const label = PLATFORMS[key] || key;
    if (isDownloadable(info)) {
      const bits = ['v' + (info.version || ''), fmtBytes(info.size), 'SHA-256 verified'].filter(Boolean);
      return longForm ? 'Available: ' + bits.join(' · ') + '. Hosted over HTTPS.' : 'Available · ' + (fmtBytes(info.size) || 'verified');
    }
    if (key === 'windows-arm64') {
      return longForm
        ? 'No native Windows arm64 installer is published yet. The x64 build runs under emulation.'
        : 'No native build yet';
    }
    if (!manifestDoc) {
      return longForm
        ? 'Download manifest unavailable — links stay disabled until availability can be verified.'
        : 'Not verified yet';
    }
    return longForm
      ? 'No verified ' + label + ' installer is published yet. Links appear here only after an HTTPS-hosted release passes SHA-256 verification.'
      : 'Not published yet';
  }

  function syncButtons() {
    document.querySelectorAll('[data-channel]').forEach((button) => {
      const key = button.getAttribute('data-channel');
      const info = channelInfo(key);
      const ok = isDownloadable(info);
      if (ok) {
        button.setAttribute('href', safeUrl(info.url));
        button.removeAttribute('aria-disabled');
        button.setAttribute('rel', 'noopener');
        button.setAttribute('title', 'Download ' + (info.file || PLATFORMS[key] || 'Keel')
          + (fmtBytes(info.size) ? ' (' + fmtBytes(info.size) + ')' : '') + ' · SHA-256 verified');
      } else {
        button.setAttribute('href', '/download');
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('title', key === 'windows-arm64'
          ? 'No native Windows arm64 build published yet' : 'Not publicly available yet');
      }
      const label = button.querySelector('[data-download-label]');
      if (label && PLATFORMS[key]) label.textContent = 'Download for ' + PLATFORMS[key];
    });

    document.querySelectorAll('[data-channel-note]').forEach((note) => {
      const key = note.getAttribute('data-channel-note');
      if (!key) return;
      const longForm = note.classList.contains('kp-download-note');
      note.textContent = noteFor(key, longForm);
      note.classList.toggle('is-available', isDownloadable(channelInfo(key)));
    });
  }

  function setPlatform(key, moveFocus) {
    if (!PLATFORMS[key]) return;
    activePlatform = key;
    tabs.forEach((tab) => {
      const selected = tab.getAttribute('data-platform') === key;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
      tab.classList.toggle('is-active', selected);
    });
    if (panel) panel.setAttribute('aria-labelledby', 'kp-tab-' + key);
    if (heroButton) heroButton.setAttribute('data-channel', key);
    if (heroNote) heroNote.setAttribute('data-channel-note', key);
    syncButtons();
    if (moveFocus) {
      const target = tabs.find((tab) => tab.getAttribute('data-platform') === key);
      if (target && typeof target.focus === 'function') target.focus();
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setPlatform(tab.getAttribute('data-platform'), false));
    tab.addEventListener('keydown', (event) => {
      if (!event) return;
      let next = -1;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      if (next < 0 || next === index) return;
      event.preventDefault();
      setPlatform(tabs[next].getAttribute('data-platform'), true);
    });
  });

  function detectPlatform() {
    const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
    const ua = navigator.userAgent || '';
    if (/Windows/i.test(platform) || /Windows/i.test(ua)) {
      const architecture = (navigator.userAgentData && navigator.userAgentData.architecture) || '';
      const arm = /arm64|aarch64/i.test(ua) || /arm/i.test(architecture);
      return arm ? 'windows-arm64' : 'windows';
    }
    if (/Mac/i.test(platform) || /Macintosh|Mac OS/i.test(ua)) return 'macos';
    if (/Linux/i.test(platform) || /Linux/i.test(ua)) return 'linux';
    return activePlatform;
  }

  setPlatform(detectPlatform(), false); // disabled state is shown immediately
  fetchManifest().then((doc) => {
    if (doc) manifestDoc = doc;
    syncButtons();
  }).catch(() => { syncButtons(); });
}

/* ---------- 8. Sign-in / contact sales modal ---------- */
function initAuthModal() {
  const modal = document.getElementById('kp-auth-modal');
  if (!modal) return;
  const formView = modal.querySelector('[data-auth-form-view]');
  const success = modal.querySelector('[data-auth-success]');
  const form = modal.querySelector('.kp-auth-form');
  const input = document.getElementById('kp-auth-email');
  const error = document.getElementById('kp-auth-error');
  const demo = modal.querySelector('[data-auth-demo]');
  let lastFocus = null;

  function open(trigger) {
    lastFocus = trigger || document.activeElement;
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
    const continueLink = success && success.querySelector('a[href="/app"]');
    if (continueLink && typeof continueLink.focus === 'function') continueLink.focus();
  }

  document.addEventListener('click', (event) => {
    const target = event && event.target;
    if (!target || typeof target.closest !== 'function') return;
    const trigger = target.closest('[data-auth-open]');
    if (!trigger) return;
    event.preventDefault();
    open(trigger);
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

  // Keep Tab inside the dialog while it is open.
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

/* ---------- 9. Footer link search ---------- */
function initFooterSearch() {
  const form = document.querySelector('.kp-footer-search');
  const input = form && form.querySelector('input[type="search"]');
  const status = document.querySelector('.kp-search-status');
  if (!form || !input) return;
  const items = Array.from(document.querySelectorAll('.kp-footer-col li'));

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
        : 'No matching links. Try “download”, “privacy” or “code”.';
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    filter();
  });
  input.addEventListener('input', () => { if (!(input.value || '').trim()) filter(); });
}

/* ---------- 10. Hero platform-aware label ---------- */
function initHeroPlatform() {
  const hero = document.getElementById('hero-download');
  if (!hero) return;
  const ua = navigator.userAgent || '';
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
  let key = 'windows';
  if (/Mac/i.test(platform) || /Macintosh|Mac OS/i.test(ua)) key = 'macos';
  else if (/Linux/i.test(platform) || /Linux/i.test(ua)) key = 'linux';
  const labels = {
    windows: 'Download for Windows',
    macos: 'Download for macOS',
    linux: 'Download for Linux',
  };
  const label = hero.querySelector('span:last-child') || hero;
  if (label) label.textContent = labels[key];
  hero.setAttribute('href', '#' + key);
}

/* ---------- Global Escape: close all dismissible widgets ---------- */
function initGlobalKeys() {
  document.addEventListener('keydown', (event) => {
    if (!event || (event.key !== 'Escape' && event.key !== 'Esc')) return;
    if (typeof initAuthModal._close === 'function') initAuthModal._close();
    if (typeof initNav._closeAll === 'function') initNav._closeAll();
    if (typeof initMobileMenu._close === 'function') initMobileMenu._close();
    if (typeof initChat._close === 'function') initChat._close();
  });
}

/* ---------- Boot ---------- */
function init() {
  safe(initNav);
  safe(initFaq);
  safe(initMobileMenu);
  safe(initChat);
  safe(initNews);
  safe(initCopy);
  safe(initDownloads);
  safe(initHeroPlatform);
  safe(initAuthModal);
  safe(initFooterSearch);
  safe(initGlobalKeys);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init, { once: true });
} else {
  init();
}

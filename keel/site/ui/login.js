'use strict';

/* Keel sign-in / create-account page — vanilla JS, no dependencies.
   Every query is guarded; a missing element never breaks the page. */

(function () {
  var busy = false;

  function safe(setup) {
    try { setup(); } catch (e) { /* UI enhancements must never throw */ }
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function all(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }

  function validEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  /* ---------- query string: intent, next, optional plan ---------- */
  var params;
  try {
    params = new URLSearchParams(window.location.search);
  } catch (e) {
    params = { get: function () { return null; } };
  }

  var rawIntent = (params.get('intent') || '').toLowerCase();
  var explicitIntent = ['login', 'signup', 'sales'].indexOf(rawIntent) !== -1;
  var intent = explicitIntent ? rawIntent : 'login';

  /* Only accept a same-origin absolute path — never an open redirect. */
  var rawNext = params.get('next') || '';
  var destination = '/app';
  if (rawNext && /^\/(?![\/\\])/.test(rawNext) && !/[\r\n]/.test(rawNext)) {
    destination = rawNext;
  }

  /* ---------- shared UI helpers ---------- */
  function showNote(message) {
    var note = byId('login-demo-note');
    if (!note) return;
    note.textContent = message;
    note.hidden = false;
  }

  function focusEmail() {
    var input = byId('login-email');
    if (!input || typeof input.focus !== 'function') return;
    try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); }
  }

  function setError(message) {
    var input = byId('login-email');
    var error = byId('login-email-error');
    if (error) {
      error.textContent = message;
      error.hidden = !message;
    }
    if (input) {
      if (message) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    }
  }

  /* ---------- sign-in / sign-up flow ---------- */
  function finish(message) {
    if (busy) return;
    busy = true;
    showNote(message);
    setError('');
    storageSet('keel_logged_in', 'true');
    all('.login-auth-btn, .login-plan-btn').forEach(function (button) {
      button.disabled = true;
    });
    window.setTimeout(function () {
      window.location.assign(destination);
    }, 550);
  }

  function signIn(value) {
    if (busy) return;
    var email = (value || '').trim();
    if (!validEmail(email)) {
      setError('Please enter a valid email address.');
      focusEmail();
      return;
    }
    setError('');
    storageSet('keel_email', email);
    finish(intent === 'sales' ? 'Request received. Redirecting to Keel…' : 'Signing you in to Keel…');
  }

  function initAuth() {
    var form = document.querySelector('.login-email-form');
    var input = byId('login-email');

    if (form && input) {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        signIn(input.value || '');
      });
      input.addEventListener('input', function () { setError(''); });
    }

    all('[data-demo]').forEach(function (button) {
      button.addEventListener('click', function () {
        var provider = button.getAttribute('data-demo') === 'apple' ? 'Apple' : 'Google';
        finish('Demo only — no ' + provider + ' account is contacted. Redirecting to Keel…');
      });
    });

    all('[data-try]').forEach(function (button) {
      button.addEventListener('click', function () {
        var value = input ? (input.value || '').trim() : '';
        if (validEmail(value)) {
          signIn(value);
          return;
        }
        setError('');
        showNote('Enter your email above to create your Keel account.');
        focusEmail();
        if (input && typeof input.scrollIntoView === 'function') {
          try { input.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
          catch (e) { input.scrollIntoView(); }
        }
      });
    });
  }

  function applyIntent() {
    var submit = byId('login-submit');
    if (submit) {
      if (intent === 'signup') submit.textContent = 'Create account with email';
      else if (intent === 'sales') submit.textContent = 'Request a demo';
    }
    if (!explicitIntent) return;
    if (intent === 'login') {
      var saved = storageGet('keel_email');
      if (saved && byId('login-email') && !byId('login-email').value) {
        byId('login-email').value = saved;
      }
    }
    focusEmail();
  }

  /* ---------- FAQ accordion with rotating chevron ---------- */
  function initFaq() {
    var questions = all('.login-faq-q');
    if (questions.length === 0) return;

    questions.forEach(function (question) {
      var panel = byId(question.getAttribute('aria-controls') || '');
      if (panel) panel.setAttribute('aria-hidden', 'true');

      question.addEventListener('click', function () {
        var item = question.closest ? question.closest('.login-faq-item') : null;
        var willOpen = question.getAttribute('aria-expanded') !== 'true';

        questions.forEach(function (other) {
          if (other === question) return;
          other.setAttribute('aria-expanded', 'false');
          var otherItem = other.closest ? other.closest('.login-faq-item') : null;
          if (otherItem) otherItem.classList.remove('open');
          var otherPanel = byId(other.getAttribute('aria-controls') || '');
          if (otherPanel) otherPanel.setAttribute('aria-hidden', 'true');
        });

        question.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        if (item) item.classList.toggle('open', willOpen);
        if (panel) panel.setAttribute('aria-hidden', willOpen ? 'false' : 'true');
      });
    });
  }

  /* ---------- Individual / Team and Enterprise tabs ---------- */
  function initTabs() {
    var tabs = all('[data-plan-tab]');
    if (tabs.length === 0) return;
    var panels = all('[data-plan-panel]');

    function select(key, moveFocus) {
      tabs.forEach(function (tab) {
        var active = tab.getAttribute('data-plan-tab') === key;
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        tab.tabIndex = active ? 0 : -1;
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-plan-panel') !== key;
      });
      if (moveFocus) {
        tabs.forEach(function (tab) {
          if (tab.getAttribute('data-plan-tab') === key && typeof tab.focus === 'function') {
            tab.focus();
          }
        });
      }
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () {
        select(tab.getAttribute('data-plan-tab'), false);
      });
      tab.addEventListener('keydown', function (event) {
        if (!event) return;
        var next = -1;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          next = (index + 1) % tabs.length;
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          next = (index - 1 + tabs.length) % tabs.length;
        } else if (event.key === 'Home') {
          next = 0;
        } else if (event.key === 'End') {
          next = tabs.length - 1;
        }
        if (next < 0 || next === index) return;
        event.preventDefault();
        select(tabs[next].getAttribute('data-plan-tab'), true);
      });
    });

    select(params.get('plan') === 'team' ? 'team' : 'individual', false);
  }

  /* ---------- boot ---------- */
  function init() {
    safe(initAuth);
    safe(initFaq);
    safe(initTabs);
    safe(applyIntent);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

'use strict';

/* Keel sign-in / create-account page layout behaviour — vanilla JS.
   Authentication itself lives in ui/auth.js; this file only handles the page's
   FAQ, plan tabs and "Try Keel" buttons. Every query is guarded. */

(function () {
  function safe(setup) {
    try { setup(); } catch (e) { /* UI enhancements must never break the page */ }
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function all(selector) {
    return Array.prototype.slice.call(document.querySelectorAll(selector));
  }

  var params;
  try {
    params = new URLSearchParams(window.location.search);
  } catch (e) {
    params = { get: function () { return null; } };
  }

  /* ---------- plan CTAs: choose the create-account tab and show the card ---------- */
  function initPlanButtons() {
    var buttons = all('[data-try]');
    if (buttons.length === 0) return;
    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var signup = byId('auth-tab-signup');
        if (signup && typeof signup.click === 'function') signup.click();
        var card = document.querySelector('.login-auth-card');
        if (card && typeof card.scrollIntoView === 'function') {
          try { card.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
          catch (e) { card.scrollIntoView(); }
        }
      });
    });
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

  function init() {
    safe(initPlanButtons);
    safe(initFaq);
    safe(initTabs);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();

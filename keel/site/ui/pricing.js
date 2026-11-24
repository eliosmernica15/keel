/* ===========================================================================
   KEEL pricing page — progressive enhancement, no libraries, no network calls.
   Every lookup is guarded: a missing element never breaks another feature.
   =========================================================================== */
(function () {
  "use strict";

  /* ----------------------------- helpers ----------------------------- */
  function qs(selector, root) {
    try { return (root || document).querySelector(selector) || null; }
    catch (error) { return null; }
  }

  function qsa(selector, root) {
    try { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    catch (error) { return []; }
  }

  function childrenOf(node) {
    if (!node || !node.children) return [];
    try { return Array.prototype.slice.call(node.children); }
    catch (error) { return []; }
  }

  /* One broken section must not stop the others. */
  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function setAttr(node, name, value) {
    if (node && typeof node.setAttribute === "function") {
      node.setAttribute(name, value);
    }
  }

  function getAttr(node, name) {
    if (!node || typeof node.getAttribute !== "function") return null;
    return node.getAttribute(name);
  }

  function hasClass(node, name) {
    return !!(node && node.classList && typeof node.classList.contains === "function" &&
      node.classList.contains(name));
  }

  function toggleClass(node, name, on) {
    if (node && node.classList && typeof node.classList.toggle === "function") {
      node.classList.toggle(name, !!on);
    }
  }

  /* `hidden` is the contract; the class is a harmless extra hook for CSS. */
  function setHidden(node, hidden) {
    if (!node) return;
    var hide = !!hidden;
    node.hidden = hide;
    toggleClass(node, "is-hidden", hide);
  }

  function markActive(list, active) {
    list.forEach(function (node) {
      var on = node === active;
      toggleClass(node, "is-active", on);
      setAttr(node, "aria-selected", on ? "true" : "false");
    });
  }

  function initialTab(list) {
    return list.filter(function (node) { return hasClass(node, "is-active"); })[0] || list[0] || null;
  }

  var closeMegas = function () {};
  var closeMobile = function () {};
  var closeModal = function () {};

  /* ---------------------- 1. Billing period toggle --------------------- */
  function initBilling() {
    var options = qsa(".pr-billing-opt");
    if (!options.length) return;

    function apply(billing) {
      if (!billing) return;
      var attribute = "data-price-" + billing;
      qsa(".pr-card").forEach(function (card) {
        var raw = getAttr(card, attribute);
        if (raw == null) return; /* leave authored text when no price is declared */
        var pipe = raw.indexOf("|");
        var price = (pipe === -1 ? raw : raw.slice(0, pipe)).trim();
        var period = (pipe === -1 ? "" : raw.slice(pipe + 1)).trim();
        var amount = qs(".pr-amount", card);
        var cycle = qs(".pr-period", card);
        if (amount) amount.textContent = price;
        if (cycle) cycle.textContent = period;
      });
    }

    options.forEach(function (option) {
      option.addEventListener("click", function () {
        var billing = getAttr(option, "data-billing");
        if (!billing) return;
        markActive(options, option);
        apply(billing);
      });
    });

    var first = initialTab(options);
    apply(first ? getAttr(first, "data-billing") : "monthly");
  }

  /* ------------------------- 2. Plan tabs ------------------------------ */
  function initPlanTabs() {
    var tabs = qsa(".pr-plan-tab");
    if (!tabs.length) return;
    var cards = qsa(".pr-card");

    function apply(plan) {
      if (!plan) return;
      cards.forEach(function (card) {
        setHidden(card, getAttr(card, "data-plan-set") !== plan);
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var plan = getAttr(tab, "data-plan");
        if (!plan) return;
        markActive(tabs, tab);
        apply(plan);
      });
    });

    var first = initialTab(tabs);
    if (first) apply(getAttr(first, "data-plan"));
  }

  /* ---------------------- 3. Nav mega dropdowns ------------------------ */
  function initMegaMenus() {
    var triggers = qsa(".pr-nav-trigger");
    if (!triggers.length) return;

    function megaFor(trigger) {
      var item = trigger.closest ? trigger.closest(".pr-nav-item") : null;
      var mega = qs(".pr-mega", item || document);
      if (!mega) {
        var next = trigger.nextElementSibling;
        if (next && hasClass(next, "pr-mega")) mega = next;
      }
      return mega;
    }

    function closeAll(except) {
      triggers.forEach(function (trigger) {
        if (trigger === except) return;
        setAttr(trigger, "aria-expanded", "false");
        setHidden(megaFor(trigger), true);
      });
    }
    closeMegas = closeAll;

    triggers.forEach(function (trigger) {
      var mega = megaFor(trigger);
      trigger.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var wasOpen = getAttr(trigger, "aria-expanded") === "true";
        closeAll(trigger); /* only one dropdown open at a time */
        if (!wasOpen) {
          setAttr(trigger, "aria-expanded", "true");
          setHidden(mega, false);
        } else {
          setAttr(trigger, "aria-expanded", "false");
          setHidden(mega, true);
        }
      });
    });

    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") { closeAll(); return; }
      if (target.closest(".pr-nav-trigger") || target.closest(".pr-mega")) return;
      closeAll();
    });
  }

  /* ------------------------ 4. Mobile menu ----------------------------- */
  function initMobileMenu() {
    var toggle = qs(".pr-nav-toggle");
    var menu = qs("#pr-mobile-menu");
    if (!toggle || !menu) return;

    function close() {
      setHidden(menu, true);
      setAttr(toggle, "aria-expanded", "false");
      setAttr(toggle, "aria-label", "Open menu");
    }
    closeMobile = close;

    toggle.addEventListener("click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      var open = menu.hidden;
      setHidden(menu, !open);
      setAttr(toggle, "aria-expanded", open ? "true" : "false");
      setAttr(toggle, "aria-label", open ? "Close menu" : "Open menu");
    });

    document.addEventListener("click", function (event) {
      if (menu.hidden) return;
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") { close(); return; }
      if (target.closest(".pr-nav-toggle") || target.closest("#pr-mobile-menu")) return;
      close();
    });
  }

  /* -------------------------- 5. FAQ tabs ------------------------------ */
  function initFaqTabs() {
    var tabs = qsa(".pr-faq-tab");
    if (!tabs.length) return;
    var items = qsa(".pr-faq-item[data-faqgroup]");

    function apply(group) {
      if (!group) return;
      items.forEach(function (item) {
        setHidden(item, getAttr(item, "data-faqgroup") !== group);
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var group = getAttr(tab, "data-faqtab");
        if (!group) return;
        markActive(tabs, tab);
        apply(group);
      });
    });

    var first = initialTab(tabs);
    if (first) apply(getAttr(first, "data-faqtab"));
  }

  /* ----------------------- 6. FAQ accordion ---------------------------- */
  function initFaqAccordion() {
    var questions = qsa(".pr-faq-q");
    if (!questions.length) return;

    questions.forEach(function (question) {
      var item = question.closest ? question.closest(".pr-faq-item") : null;
      var answer = qs(".pr-faq-a", item || document);
      if (!answer) {
        var next = question.nextElementSibling;
        if (next && hasClass(next, "pr-faq-a")) answer = next;
      }
      if (!answer) return; /* multiple accordions may stay open at once */
      question.addEventListener("click", function () {
        var open = getAttr(question, "aria-expanded") !== "true";
        setAttr(question, "aria-expanded", open ? "true" : "false");
        setHidden(answer, !open);
      });
    });
  }

  /* ----------------------- 7. Comparison search ------------------------ */
  function initTableSearch() {
    var input = qs("#prSearch");
    if (!input) return;
    var scope = qs("#prTableBody") || qs(".pr-table tbody") || qs(".pr-table") || document;
    var featureRows = qsa("tr[data-feature]", scope);
    if (!featureRows.length) return;
    var allRows = qsa("tr", scope);
    var empty = qs("#prEmpty");

    function apply() {
      var query = String(input.value || "").toLowerCase().trim();
      var visible = 0;

      featureRows.forEach(function (row) {
        var label = String(getAttr(row, "data-feature") || "").toLowerCase();
        var show = !query || label.indexOf(query) !== -1;
        setHidden(row, !show);
        if (show) visible++;
      });

      /* A group heading is hidden when no visible feature row follows it
         before the next group heading. */
      allRows.forEach(function (row, index) {
        if (!hasClass(row, "pr-group-row")) return;
        var hasVisible = false;
        for (var i = index + 1; i < allRows.length; i++) {
          var next = allRows[i];
          if (hasClass(next, "pr-group-row")) break;
          if (!next.hidden) { hasVisible = true; break; }
        }
        setHidden(row, query ? !hasVisible : false);
      });

      if (empty) setHidden(empty, visible > 0 || !query);
    }

    input.addEventListener("input", apply);
    apply();
  }

  /* ----------------------------- 8. Modal ------------------------------ */
  function initModal() {
    var modal = qs("#prModal");
    if (!modal) return;
    var card = qs(".pr-modal-card", modal) || modal;
    var closeButton = qs(".pr-modal-close", modal);
    var form = qs("#prModalForm", modal);
    var email = qs("#prEmail", modal) || (form ? qs("input[type=email]", form) : null);
    var msg = qs("#prFormMsg", modal);
    var links = qs(".pr-modal-links", modal);
    var openers = qsa("[data-auth-open]");
    var lastFocused = null;
    var previousOverflow = null;

    function resetForm() {
      if (!form) return;
      if (typeof form.reset === "function") form.reset();
      childrenOf(form).forEach(function (child) { setHidden(child, false); });
      if (email) email.removeAttribute("aria-invalid");
      if (msg) { msg.textContent = ""; setHidden(msg, true); }
      toggleClass(form, "is-success", false);
    }

    function lockScroll(on) {
      var body = document.body;
      if (!body) return;
      toggleClass(body, "pr-modal-open", on);
      if (!body.style) return;
      if (on && previousOverflow === null) {
        previousOverflow = body.style.overflow;
        body.style.overflow = "hidden";
      } else if (!on && previousOverflow !== null) {
        body.style.overflow = previousOverflow;
        previousOverflow = null;
      }
    }

    function open(trigger) {
      lastFocused = trigger || document.activeElement;
      resetForm();
      setHidden(modal, false);
      toggleClass(modal, "is-open", true);
      lockScroll(true);
      var target = email || qs("input, button, a[href]", card);
      if (target && typeof target.focus === "function") target.focus();
    }

    function shut() {
      if (modal.hidden) return;
      setHidden(modal, true);
      toggleClass(modal, "is-open", false);
      lockScroll(false);
      if (lastFocused && typeof document.contains === "function" &&
          document.contains(lastFocused) && typeof lastFocused.focus === "function") {
        lastFocused.focus();
      }
      lastFocused = null;
    }
    closeModal = shut;

    openers.forEach(function (opener) {
      opener.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        open(opener);
      });
    });

    if (closeButton) closeButton.addEventListener("click", shut);

    /* The modal element itself is the backdrop; clicks inside the card do not
       bubble to it as the event target, so they are ignored. */
    document.addEventListener("click", function (event) {
      if (modal.hidden) return;
      var target = event && event.target;
      if (target === modal || hasClass(target, "pr-modal-backdrop")) shut();
    });

    if (form) {
      form.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var value = email ? String(email.value || "").trim() : "";
        var validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
        var nativeValid = typeof form.checkValidity === "function" ? form.checkValidity() : true;
        if (!nativeValid || (email && !validEmail)) {
          if (typeof form.reportValidity === "function") form.reportValidity();
          if (email) email.setAttribute("aria-invalid", "true");
          return;
        }
        if (email) email.removeAttribute("aria-invalid");
        childrenOf(form).forEach(function (child) {
          if (child !== msg) setHidden(child, true);
        });
        toggleClass(form, "is-success", true);
        if (msg) {
          msg.textContent = "Thanks — we'll be in touch.";
          setHidden(msg, false);
        }
        setHidden(links, false);
      });
    }
  }

  /* --------------------------- 9. Escape ------------------------------- */
  function initEscape() {
    document.addEventListener("keydown", function (event) {
      if (!event) return;
      var key = event.key || (event.keyCode === 27 ? "Escape" : "");
      if (key !== "Escape" && key !== "Esc") return;
      closeModal();
      closeMegas();
      closeMobile();
    });
  }

  /* ----------------------------- boot ---------------------------------- */
  function boot() {
    safe(initBilling);
    safe(initPlanTabs);
    safe(initMegaMenus);
    safe(initMobileMenu);
    safe(initFaqTabs);
    safe(initFaqAccordion);
    safe(initTableSearch);
    safe(initModal);
    safe(initEscape);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot(); /* the script was loaded with defer or injected after parsing */
  }
})();

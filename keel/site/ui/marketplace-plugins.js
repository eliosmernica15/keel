/* ===========================================================================
   Keel Marketplace — /marketplace/plugins behaviour.
   Dependency-free, no network calls, no installs. Search and filters run on
   the cards already in the page; dialogs offer honest, real next steps.
   Scroll listeners are passive and requestAnimationFrame-throttled.
   =========================================================================== */
(function () {
  "use strict";

  var VISIBLE_LIMIT = 12;
  var STORAGE_KEY = "keel-marketplace-plugin-submissions";

  function qs(selector, root) {
    try { return (root || document).querySelector(selector) || null; }
    catch (error) { return null; }
  }

  function qsa(selector, root) {
    try { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    catch (error) { return []; }
  }

  function safe(setup) {
    try { setup(); } catch (error) { /* one broken widget must not stop the rest */ }
  }

  function setHidden(node, hidden) {
    if (!node) return;
    node.hidden = !!hidden;
  }

  var reduceMotion = (function () {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)"); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  var statusTimer = null;
  function showStatus(message) {
    var node = qs("[data-status]");
    if (!node || !message) return;
    node.textContent = message;
    setHidden(node, false);
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(function () {
      statusTimer = null;
      setHidden(node, true);
    }, 3200);
  }

  /* ------------------------- progressive reveals ------------------------ */
  function markRevealed(node) {
    if (!node || !node.classList) return;
    node.classList.add("is-revealed");
    if (observer) observer.unobserve(node);
  }

  var observer = null;

  function initReveal() {
    var targets = qsa(".mp-reveal");
    if (!targets.length) return;

    targets.forEach(function (node, index) {
      if (!node.style || node.style.getPropertyValue("--mp-reveal-delay")) return;
      node.style.setProperty("--mp-reveal-delay", Math.min(index % 3 * 10, 20) + "ms");
    });

    if (prefersReducedMotion() || typeof IntersectionObserver !== "function") {
      targets.forEach(markRevealed);
      return;
    }

    document.documentElement.classList.add("mp-reveal-ready");
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) markRevealed(entry.target);
      });
    }, { rootMargin: "0px 0px -5% 0px", threshold: 0.05 });

    targets.forEach(function (node) {
      if (!node.hidden) observer.observe(node);
    });

    if (reduceMotion && typeof reduceMotion.addEventListener === "function") {
      reduceMotion.addEventListener("change", function () {
        if (!reduceMotion.matches) return;
        targets.forEach(markRevealed);
      });
    }
  }

  /* ------------------- sticky header shadow (rAF scroll) ---------------- */
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

  function initHeaderScroll() {
    var header = qs("#mp-header");
    if (!header) return;
    function update() {
      var y = window.pageYOffset || window.scrollY || 0;
      header.classList.toggle("is-scrolled", y > 12);
    }
    var frame = onScrollFrame(update);
    window.addEventListener("scroll", frame, { passive: true });
    window.addEventListener("resize", frame, { passive: true });
    update();
  }

  /* ---------------------------- mobile menu ----------------------------- */
  function initMobileMenu() {
    var toggle = qs(".mp-menu-toggle");
    var menu = qs("#mp-mobile-menu");
    if (!toggle || !menu) return;

    function close() {
      setHidden(menu, true);
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open menu");
    }
    function open() {
      setHidden(menu, false);
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Close menu");
    }
    toggle.addEventListener("click", function () {
      if (menu.hidden) open(); else close();
    });
    qsa("a", menu).forEach(function (link) {
      link.addEventListener("click", close);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !menu.hidden) {
        close();
        toggle.focus();
      }
    });
  }

  function initSearchJump() {
    var jump = qs("[data-search-jump]");
    var input = qs("[data-plugin-search]");
    if (!jump || !input) return;
    jump.addEventListener("click", function () {
      input.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" });
      input.focus();
    });
  }

  /* --------------------- search, filters and View more ------------------ */
  function initSearchAndFilters() {
    var cards = qsa("[data-plugin]");
    var input = qs("[data-plugin-search]");
    var checks = qsa("[data-works-filter]");
    var count = qs("[data-result-count]");
    var empty = qs("[data-empty]");
    var more = qs("[data-view-more]");
    var clear = qs("[data-clear-filters]");
    if (!cards.length || !input) return;

    var expanded = false;

    function selectedWorksWith() {
      return checks.filter(function (check) { return check.checked; })
        .map(function (check) { return check.value; });
    }

    function matches(card, query, selected) {
      var name = (card.getAttribute("data-name") || "").toLowerCase();
      var description = (card.getAttribute("data-description") || "").toLowerCase();
      if (query && name.indexOf(query) === -1 && description.indexOf(query) === -1) return false;
      if (!selected.length) return true;
      var tags = (card.getAttribute("data-works-with") || "").toLowerCase().split("|");
      return selected.some(function (value) {
        return tags.indexOf(value.toLowerCase()) !== -1;
      });
    }

    function render() {
      var query = input.value.trim().toLowerCase();
      var selected = selectedWorksWith();
      var matched = 0;
      var shown = 0;

      cards.forEach(function (card) {
        var isMatch = matches(card, query, selected);
        if (isMatch) matched += 1;
        var visible = isMatch && (expanded || shown < VISIBLE_LIMIT);
        if (visible) shown += 1;
        if (visible && card.hidden) markRevealed(card);
        setHidden(card, !visible);
      });

      if (count) count.textContent = "Showing " + shown + " of " + matched + " plugins";
      setHidden(empty, matched > 0);
      setHidden(more, expanded || matched <= VISIBLE_LIMIT);
    }

    input.addEventListener("input", render);
    checks.forEach(function (check) { check.addEventListener("change", render); });
    if (clear) {
      clear.addEventListener("click", function () {
        input.value = "";
        checks.forEach(function (check) { check.checked = false; });
        expanded = false;
        render();
        showStatus("Search and filters cleared.");
      });
    }
    if (more) {
      more.addEventListener("click", function () {
        expanded = true;
        render();
      });
    }
    render();
  }

  /* ------------------------- honest detail dialog ----------------------- */
  var activeDialog = null;
  var lastFocused = null;

  function focusables(root) {
    return qsa('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])', root);
  }

  function openDialog(backdrop, dialog) {
    if (!backdrop || !dialog) return;
    lastFocused = document.activeElement;
    activeDialog = dialog;
    setHidden(backdrop, false);
    document.body.style.overflow = "hidden";
    var close = qs("[data-close-detail], [data-close-submit]", dialog);
    if (close) close.focus();
  }

  function closeDialog() {
    if (!activeDialog) return;
    var backdrop = activeDialog.parentNode;
    setHidden(backdrop, true);
    activeDialog = null;
    document.body.style.overflow = "";
    if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
    lastFocused = null;
  }

  function initDialogShell() {
    qsa(".mp-backdrop").forEach(function (backdrop) {
      backdrop.addEventListener("click", function (event) {
        if (event.target === backdrop) closeDialog();
      });
    });
    qsa("[data-close-detail], [data-close-submit]").forEach(function (button) {
      button.addEventListener("click", closeDialog);
    });
    document.addEventListener("keydown", function (event) {
      if (!activeDialog) return;
      if (event.key === "Escape") {
        closeDialog();
        return;
      }
      if (event.key !== "Tab") return;
      var items = focusables(activeDialog).filter(function (node) { return !node.hidden; });
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  function copyCommand() {
    var command = qs("[data-install-command]");
    var text = command ? command.textContent.trim() : "";
    if (!text) return;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard.writeText(text).then(function () {
        showStatus("Install command copied to your clipboard.");
      }).catch(function () {
        showStatus("Copy failed. Select the command above and copy it manually.");
      });
      return;
    }
    showStatus("Copy is unavailable. Select the command above and copy it manually.");
  }

  function openDetail(card) {
    var backdrop = qs("[data-detail-backdrop]");
    var dialog = qs("[data-detail-dialog]");
    if (!backdrop || !dialog || !card) return;

    var name = card.getAttribute("data-name") || "Plugin";
    var description = card.getAttribute("data-description") || "";
    var worksWith = card.getAttribute("data-works-with") || "";
    var kind = card.getAttribute("data-kind") || "local";
    var slug = card.getAttribute("data-slug") || "";

    var title = qs("[data-detail-title]", dialog);
    if (title) title.textContent = name;
    var desc = qs("[data-detail-desc]", dialog);
    if (desc) desc.textContent = description;
    var meta = qs("[data-detail-meta]", dialog);
    if (meta) meta.textContent = "Works with " + worksWith.replace(/\|/g, " and ");

    var sourceIcon = qs(".mp-card-icon", card);
    var targetIcon = qs("[data-detail-icon]", dialog);
    if (sourceIcon && targetIcon) {
      var svg = qs("svg", sourceIcon);
      if (svg) {
        targetIcon.textContent = "";
        targetIcon.appendChild(svg.cloneNode(true));
      }
      targetIcon.setAttribute("class", "mp-dialog-icon " + (sourceIcon.className || "").split(" ").filter(function (cls) {
        return cls.indexOf("mp-c-") === 0;
      }).join(" "));
    }

    setHidden(qs("[data-action-download]", dialog), kind !== "download");
    setHidden(qs("[data-action-login]", dialog), kind !== "login");
    setHidden(qs("[data-action-local]", dialog), kind !== "local");
    var command = qs("[data-install-command]", dialog);
    if (command) command.textContent = "keel plugins add " + slug;

    var copy = qs("[data-copy-command]", dialog);
    if (copy) {
      copy.removeEventListener("click", copyCommand);
      copy.addEventListener("click", copyCommand);
    }

    openDialog(backdrop, dialog);
  }

  function initDetail() {
    qsa("[data-plugin]").forEach(function (card) {
      card.addEventListener("click", function () { openDetail(card); });
    });
  }

  /* ---------------------- local-only submission form -------------------- */
  function initSubmitForm() {
    var open = qs("[data-open-submit]");
    var backdrop = qs("[data-submit-backdrop]");
    var dialog = qs("[data-submit-dialog]");
    var form = qs("[data-submit-form]");
    var result = qs("[data-submit-result]");
    var message = qs("[data-submit-message]");
    var badge = qs("[data-local-badge]");
    var mail = qs("[data-submit-mailto]");
    if (!open || !backdrop || !dialog || !form) return;

    open.addEventListener("click", function () { openDialog(backdrop, dialog); });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (typeof form.checkValidity === "function" && !form.checkValidity()) return;

      var field = function (key) {
        var control = form.elements.namedItem(key);
        return control ? String(control.value || "") : "";
      };
      var values = {
        name: field("name").trim(),
        url: field("url").trim(),
        description: field("description").trim(),
        worksWith: field("worksWith"),
        email: field("email").trim(),
        status: "local-only",
        savedAt: new Date().toISOString()
      };

      var stored = false;
      try {
        var existing = [];
        try {
          var raw = window.localStorage.getItem(STORAGE_KEY);
          var parsed = raw ? JSON.parse(raw) : [];
          if (Array.isArray(parsed)) existing = parsed;
        } catch (readError) { existing = []; }
        existing.push(values);
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
        stored = true;
      } catch (storageError) { stored = false; }

      var subject = "Plugin submission: " + values.name;
      var body = [
        "Name: " + values.name,
        "URL: " + values.url,
        "Works with: " + values.worksWith,
        "Description: " + values.description,
        "Submitted by: " + values.email,
        "",
        "Sent from the Keel Marketplace plugin submission form."
      ].join("\n");

      if (mail) {
        mail.href = "mailto:plugins@keel.dev?subject=" + encodeURIComponent(subject) +
          "&body=" + encodeURIComponent(body);
      }
      if (badge) badge.textContent = stored ? "Local only — nothing sent" : "Nothing saved or sent";
      if (message) {
        message.textContent = stored
          ? "Saved in this browser only (local-only). Nothing was sent to Keel. Use the email link below to send your submission yourself."
          : "Local storage is unavailable, so nothing was saved and nothing was sent. Use the email link below to send your submission yourself.";
      }
      setHidden(result, false);
      if (result) result.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "nearest" });
    });
  }

  function initLanguage() {
    var select = qs("[data-language]");
    if (!select) return;
    select.addEventListener("change", function () {
      var option = select.options[select.selectedIndex];
      var label = option ? option.text : "Selected language";
      showStatus(label + " is not available on this page yet. Content remains in English.");
    });
  }

  function init() {
    safe(initReveal);
    safe(initHeaderScroll);
    safe(initMobileMenu);
    safe(initSearchJump);
    safe(initDialogShell);
    safe(initDetail);
    safe(initSearchAndFilters);
    safe(initSubmitForm);
    safe(initLanguage);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}());

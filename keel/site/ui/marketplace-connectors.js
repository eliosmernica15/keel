/* ===========================================================================
   Keel Marketplace - Connectors and plugins behaviour.
   Dependency-free. Search, category filters, sorting and "View more" change
   real card visibility; the add dialog never claims an install succeeded and
   the submission form is explicitly local-only. Scroll work is passive and
   requestAnimationFrame-throttled, and reduced motion disables reveals.
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

  function safe(setup) {
    try { setup(); } catch (error) { /* one widget must never break another */ }
  }

  function setHidden(node, hidden) {
    if (node) node.hidden = !!hidden;
  }

  function normalise(value) {
    return String(value == null ? "" : value).toLowerCase();
  }

  var reduceMotion = (function () {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)"); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  var refreshCards = function () {};
  var clearAllFilters = function () {};
  var observer = null;

  /* ------------------------- 1. scroll reveals ------------------------ */
  function initReveal() {
    var targets = qsa(".mc-reveal");
    if (!targets.length) return;

    qsa("[data-grid]").forEach(function (grid) {
      qsa(".mc-card", grid).forEach(function (card, index) {
        card.style.setProperty("--mc-reveal-delay", Math.min(index * 35, 140) + "ms");
      });
    });

    function revealAll() {
      targets.forEach(function (node) { node.classList.add("is-revealed"); });
      if (observer && typeof observer.disconnect === "function") observer.disconnect();
    }

    if (prefersReducedMotion() || typeof IntersectionObserver !== "function") {
      revealAll();
      return;
    }

    document.documentElement.classList.add("mc-reveal-ready");
    observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -5% 0px", threshold: 0.05 });

    targets.forEach(function (node) { observer.observe(node); });

    if (reduceMotion && typeof reduceMotion.addEventListener === "function") {
      reduceMotion.addEventListener("change", function () {
        if (reduceMotion.matches) revealAll();
      });
    }
  }

  /* ------------- 2. sticky header shadow (rAF throttled) ------------- */
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

  function initStickyHeader() {
    var header = qs("#mc-header");
    if (!header) return;
    var frame = onScrollFrame(function () {
      var y = window.pageYOffset || window.scrollY || 0;
      header.classList.toggle("is-scrolled", y > 12);
    });
    window.addEventListener("scroll", frame, { passive: true });
    window.addEventListener("resize", frame, { passive: true });
    frame();
  }

  /* --------------------- 3. navigation menus ------------------------ */
  function initMegaNav() {
    var items = qsa(".mc-nav-item");

    function closeAll(except) {
      items.forEach(function (item) {
        if (item === except) return;
        item.classList.remove("is-open");
        var trigger = qs(".mc-nav-link", item);
        var panel = qs(".mc-mega", item);
        if (trigger) trigger.setAttribute("aria-expanded", "false");
        if (panel) {
          panel.hidden = true;
          panel.setAttribute("aria-hidden", "true");
        }
      });
    }

    items.forEach(function (item) {
      var trigger = qs(".mc-nav-link", item);
      var panel = qs(".mc-mega", item);
      if (!trigger || !panel) return;

      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        var open = !item.classList.contains("is-open");
        closeAll(null);
        if (open) {
          item.classList.add("is-open");
          trigger.setAttribute("aria-expanded", "true");
          panel.hidden = false;
          panel.setAttribute("aria-hidden", "false");
        }
      });
    });

    document.addEventListener("click", function (event) {
      if (event.target && typeof event.target.closest === "function" &&
          event.target.closest(".mc-nav-item")) return;
      closeAll(null);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAll(null);
    });
  }

  function initMobileMenu() {
    var toggle = qs("#mc-menu-toggle");
    var links = qs("#mc-nav-links");
    var panel = qs("#mc-mobile-menu");
    if (!toggle || !panel) return;
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      setHidden(panel, !open);
      if (links) links.classList.toggle("is-open", open);
    });
  }

  function initNavSearch() {
    var button = qs("#mc-nav-search");
    var input = qs("#mc-search");
    if (!button || !input) return;
    button.addEventListener("click", function () {
      if (typeof input.scrollIntoView === "function") {
        input.scrollIntoView({ block: "center" });
      }
      input.focus();
    });
  }

  /* -------------- 4. search / category filter / sorting -------------- */
  function initFilters() {
    var input = qs("#mc-search");
    var select = qs("#mc-sort");
    var boxes = qsa('input[name="mc-category"]');
    var noResults = qs("#mc-no-results");
    var banner = qs("#mc-active-filter");
    var clearButton = qs("#mc-clear-filters");
    var noResultsClear = qs("#mc-no-results-clear");

    function selectedCategories() {
      return boxes.filter(function (box) { return box.checked; })
        .map(function (box) { return normalise(box.value); });
    }

    function matches(card, term, categories) {
      var haystack = normalise(card.getAttribute("data-name")) + " " +
                     normalise(card.getAttribute("data-desc"));
      if (term && haystack.indexOf(term) === -1) return false;
      if (!categories.length) return true;
      var onCard = normalise(card.getAttribute("data-categories")).split("|");
      return categories.some(function (category) { return onCard.indexOf(category) !== -1; });
    }

    function applyVisibility() {
      var cards = qsa(".mc-card");
      var term = normalise(input ? input.value.trim() : "");
      var categories = selectedCategories();
      var matched = 0;

      cards.forEach(function (card) {
        var fit = matches(card, term, categories);
        var grid = card.parentElement;
        var extra = card.getAttribute("data-extra") === "true";
        var expanded = !grid || grid.getAttribute("data-expanded") === "true";
        if (fit) matched += 1;
        card.hidden = !(fit && (!extra || expanded));
      });

      setHidden(noResults, matched !== 0);
      setHidden(clearButton, categories.length === 0 && !term && !selectHasChanged());
      if (banner) {
        setHidden(banner, categories.length === 0);
        if (categories.length) {
          banner.textContent = "Filtering by: " +
            boxes.filter(function (box) { return box.checked; })
              .map(function (box) { return box.value; }).join(", ") +
            ".";
        }
      }
    }

    function selectHasChanged() {
      return !!(select && select.value !== "recommended");
    }

    function sortCards() {
      var mode = select ? select.value : "recommended";
      qsa("[data-grid]").forEach(function (grid) {
        var items = qsa(".mc-card", grid);
        items.sort(function (a, b) {
          var orderA = Number(a.getAttribute("data-order")) || 0;
          var orderB = Number(b.getAttribute("data-order")) || 0;
          if (mode === "name") {
            return normalise(a.getAttribute("data-name"))
              .localeCompare(normalise(b.getAttribute("data-name")));
          }
          if (mode === "newest") {
            var addedA = Number(a.getAttribute("data-added")) || 0;
            var addedB = Number(b.getAttribute("data-added")) || 0;
            return addedB - addedA || orderA - orderB;
          }
          return orderA - orderB;
        });
        var fragment = document.createDocumentFragment();
        items.forEach(function (card) { fragment.appendChild(card); });
        grid.appendChild(fragment);
      });
    }

    function reset() {
      if (input) input.value = "";
      if (select) select.value = "recommended";
      boxes.forEach(function (box) { box.checked = false; });
      sortCards();
      applyVisibility();
    }

    refreshCards = applyVisibility;
    clearAllFilters = reset;

    if (input) input.addEventListener("input", applyVisibility);
    if (select) select.addEventListener("change", function () {
      sortCards();
      applyVisibility();
    });
    boxes.forEach(function (box) { box.addEventListener("change", applyVisibility); });
    if (clearButton) clearButton.addEventListener("click", reset);
    if (noResultsClear) noResultsClear.addEventListener("click", reset);

    applyVisibility();
  }

  function initViewMore() {
    var button = qs("#mc-view-more");
    var grid = qs("#mc-all-grid");
    if (!button || !grid) return;
    button.addEventListener("click", function () {
      var expanded = grid.getAttribute("data-expanded") === "true";
      grid.setAttribute("data-expanded", expanded ? "false" : "true");
      button.setAttribute("aria-expanded", expanded ? "false" : "true");
      button.textContent = expanded ? "View more" : "View less";
      refreshCards();
    });
  }

  /* --------------------- 5. honest add dialog ------------------------ */
  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
  }

  function initAddDialog() {
    var dialog = qs("#mc-install-dialog");
    var name = qs("#mc-install-name");
    if (!dialog) return;

    qsa("[data-add]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (name) name.textContent = button.getAttribute("data-add") || "This connector";
        openDialog(dialog);
      });
    });
    qsa("[data-close-dialog]", dialog).forEach(function (button) {
      button.addEventListener("click", function () { closeDialog(dialog); });
    });
  }

  /* ------------------ 6. local-only submit dialog -------------------- */
  var STORAGE_KEY = "keel.marketplace.submissions";

  function initSubmitDialog() {
    var dialog = qs("#mc-submit-dialog");
    var form = qs("#mc-submit-form");
    var title = qs("#mc-submit-title");
    var status = qs("#mc-submit-status");
    var mail = qs("#mc-submit-mail");
    if (!dialog || !form) return;

    function updateMail(kind) {
      if (!mail) return;
      var subject = "Keel Marketplace " + kind + " submission";
      mail.href = "mailto:hello@keel.dev?subject=" + encodeURIComponent(subject);
    }

    qsa("[data-submit]").forEach(function (button) {
      button.addEventListener("click", function () {
        var kind = button.getAttribute("data-submit") === "plugin" ? "plugin" : "connector";
        if (title) title.textContent = "Submit a " + kind;
        updateMail(kind);
        setHidden(status, true);
        openDialog(dialog);
      });
    });

    qsa("[data-close-dialog]", dialog).forEach(function (button) {
      button.addEventListener("click", function () { closeDialog(dialog); });
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var data = new FormData(form);
      var kind = title && normalise(title.textContent).indexOf("plugin") !== -1 ? "plugin" : "connector";
      var entry = {
        type: kind,
        name: String(data.get("name") || "").trim(),
        email: String(data.get("email") || "").trim(),
        item: String(data.get("item") || "").trim(),
        url: String(data.get("url") || "").trim(),
        description: String(data.get("description") || "").trim(),
        savedAt: new Date().toISOString()
      };

      var saved = false;
      try {
        var raw = window.localStorage.getItem(STORAGE_KEY);
        var list = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(list)) list = [];
        list.push(entry);
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
        saved = true;
      } catch (error) {
        saved = false;
      }

      setHidden(status, false);
      if (status) {
        status.textContent = saved
          ? "Saved locally on this device only. Nothing was sent to Keel, no " +
            kind + " was published, and nothing was installed."
          : "Local storage is unavailable in this browser. Nothing was saved or sent. " +
            "Use the email link below instead.";
      }
      form.reset();
      if (mail) {
        var body = entry.item + "\n" + entry.url + "\n\n" + entry.description +
                   "\n\nFrom: " + entry.name + " <" + entry.email + ">";
        mail.href = "mailto:hello@keel.dev?subject=" +
          encodeURIComponent("Keel Marketplace " + kind + " submission: " + entry.item) +
          "&body=" + encodeURIComponent(body);
      }
    });
  }

  /* ----------------------- 7. footer language ------------------------ */
  function initLanguage() {
    var button = qs("#mc-lang-button");
    var menu = qs("#mc-lang-menu");
    if (!button || !menu) return;
    button.addEventListener("click", function () {
      var open = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", open ? "true" : "false");
      setHidden(menu, !open);
    });
    qsa("[data-lang]", menu).forEach(function (option) {
      option.addEventListener("click", function () {
        qsa("[data-lang]", menu).forEach(function (other) {
          other.setAttribute("aria-checked", other === option ? "true" : "false");
        });
        if (button.childNodes && button.childNodes[0]) {
          button.childNodes[0].nodeValue = option.getAttribute("data-lang") + " ";
        }
        setHidden(menu, true);
        button.setAttribute("aria-expanded", "false");
      });
    });
    document.addEventListener("click", function (event) {
      if (event.target && typeof event.target.closest === "function" &&
          event.target.closest(".mc-lang-wrap")) return;
      setHidden(menu, true);
      button.setAttribute("aria-expanded", "false");
    });
  }

  /* ----------------------------- boot ------------------------------- */
  function boot() {
    safe(initReveal);
    safe(initStickyHeader);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initNavSearch);
    safe(initFilters);
    safe(initViewMore);
    safe(initAddDialog);
    safe(initSubmitDialog);
    safe(initLanguage);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}());

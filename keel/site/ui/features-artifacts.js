/* ===========================================================================
   Keel — Features / Artifacts page behaviour.
   Plain JavaScript, no dependencies, no network calls. Every listener is
   guarded; a missing element never breaks another section. Scrolling is
   passive and requestAnimationFrame-throttled, and reduced motion disables
   all parallax and reveal animation.
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
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function setHidden(node, hidden) {
    if (!node) return;
    node.hidden = !!hidden;
  }

  function setExpanded(node, expanded) {
    if (!node || typeof node.setAttribute !== "function") return;
    node.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  function setSelected(node, selected) {
    if (!node || typeof node.setAttribute !== "function") return;
    node.setAttribute("aria-selected", selected ? "true" : "false");
    if (node.classList) node.classList.toggle("is-active", !!selected);
  }

  var reduceMotion = (function () {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)"); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  var toastTimer = null;

  function showToast(message) {
    var toast = qs("#fa-toast");
    if (!toast || !message) return;
    toast.textContent = message;
    setHidden(toast, false);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      setHidden(toast, true);
    }, 3200);
  }

  /* ------------------------ 1. scroll reveals ------------------------ */
  function initReveal() {
    var targets = qsa(".fa-reveal");
    if (!targets.length) return;

    qsa("[data-reveal-group]").forEach(function (group) {
      qsa(".fa-reveal", group).forEach(function (node, index) {
        if (node.style && node.style.getPropertyValue("--fa-reveal-delay")) return;
        node.style.setProperty("--fa-reveal-delay", Math.min(index * 40, 160) + "ms");
      });
    });

    if (prefersReducedMotion() || typeof IntersectionObserver !== "function") {
      targets.forEach(function (node) { node.classList.add("is-revealed"); });
      return;
    }

    document.documentElement.classList.add("fa-reveal-ready");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });

    targets.forEach(function (node) { observer.observe(node); });
  }

  /* ------------- 2. header shadow + hero parallax (rAF) ------------- */
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

  function initScrollEffects() {
    var header = qs("#fa-header");
    var cards = qsa("[data-parallax]");
    var allowParallax = !prefersReducedMotion() && cards.length > 0;

    function update() {
      var y = window.pageYOffset || window.scrollY || 0;
      if (header && header.classList) header.classList.toggle("is-scrolled", y > 12);
      if (!allowParallax) return;
      cards.forEach(function (card) {
        var speed = parseFloat(card.getAttribute("data-parallax")) || 0;
        var offset = Math.max(-14, Math.min(14, y * speed));
        card.style.transform = "translate3d(0," + offset.toFixed(2) + "px,0)";
      });
    }

    var frame = onScrollFrame(update);
    window.addEventListener("scroll", frame, { passive: true });
    window.addEventListener("resize", frame, { passive: true });
    update();

    if (reduceMotion && typeof reduceMotion.addEventListener === "function") {
      reduceMotion.addEventListener("change", function () {
        allowParallax = !reduceMotion.matches;
        if (!allowParallax) cards.forEach(function (card) { card.style.transform = ""; });
        update();
      });
    }
  }

  /* --------------------- 3. mega dropdown menus --------------------- */
  function initMegaNav() {
    var items = qsa(".fa-nav-item[data-menu]");
    if (!items.length) return;

    var records = items.map(function (item) {
      return {
        item: item,
        trigger: qs(".fa-nav-trigger", item),
        mega: qs(".fa-mega", item),
        pinned: false,
        open: false,
        openTimer: null,
        closeTimer: null
      };
    });

    function clearTimers(record) {
      if (record.openTimer) { clearTimeout(record.openTimer); record.openTimer = null; }
      if (record.closeTimer) { clearTimeout(record.closeTimer); record.closeTimer = null; }
    }

    function render(record, open) {
      record.open = !!open;
      if (record.item && record.item.classList) record.item.classList.toggle("is-open", record.open);
      setExpanded(record.trigger, record.open);
      if (record.mega) record.mega.setAttribute("aria-hidden", record.open ? "false" : "true");
    }

    function closeAll(except, restoreFocus) {
      var focused = document.activeElement;
      var restore = null;
      if (restoreFocus) {
        records.forEach(function (record) {
          if (record.item && focused && typeof record.item.contains === "function" &&
              record.item.contains(focused)) restore = record;
        });
      }
      records.forEach(function (record) {
        if (record.item === except) return;
        clearTimers(record);
        record.pinned = false;
        if (record.open) render(record, false);
      });
      if (restore && restore.trigger && typeof restore.trigger.focus === "function") {
        restore.trigger.focus();
      }
    }

    function toggle(record) {
      clearTimers(record);
      if (record.pinned) {
        record.pinned = false;
        render(record, false);
      } else {
        closeAll(record.item);
        render(record, true);
        record.pinned = true;
      }
    }

    records.forEach(function (record) {
      var item = record.item;
      var trigger = record.trigger;
      render(record, false);

      if (trigger) {
        trigger.addEventListener("click", function (event) {
          event.preventDefault();
          toggle(record);
        });
        trigger.addEventListener("keydown", function (event) {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            if (!record.open) toggle(record);
            var first = record.mega && qs("a", record.mega);
            if (first && typeof first.focus === "function") first.focus();
          }
        });
      }

      item.addEventListener("mouseenter", function () {
        if (window.matchMedia && window.matchMedia("(hover: none)").matches) return;
        clearTimers(record);
        record.openTimer = setTimeout(function () {
          record.openTimer = null;
          if (!record.pinned) {
            closeAll(item);
            render(record, true);
          }
        }, 100);
      });

      item.addEventListener("mouseleave", function () {
        clearTimers(record);
        record.closeTimer = setTimeout(function () {
          record.closeTimer = null;
          if (!record.pinned) render(record, false);
        }, 180);
      });

      qsa("a", item).forEach(function (link) {
        link.addEventListener("click", function () {
          record.pinned = false;
          closeAll(null);
        });
      });
    });

    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || typeof target.closest !== "function") return;
      if (target.closest(".fa-nav-item[data-menu]")) return;
      closeAll(null);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      var wasOpen = records.some(function (record) { return record.open; });
      closeAll(null, true);
      if (wasOpen) showToast("Menu closed");
    });
  }

  /* ----------------------- 4. mobile navigation ---------------------- */
  function initMobileMenu() {
    var toggle = qs(".fa-nav-toggle");
    var menu = qs("#fa-mobile-menu");
    if (!toggle || !menu) return;

    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") !== "true";
      setExpanded(toggle, open);
      setHidden(menu, !open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    });

    qsa("a", menu).forEach(function (link) {
      link.addEventListener("click", function () {
        setExpanded(toggle, false);
        setHidden(menu, true);
      });
    });
  }

  /* ------------------------- 5. showcase tabs ------------------------ */
  function initShowcaseTabs() {
    var tabs = qsa("[data-showcase-tab]");
    if (!tabs.length) return;

    var groups = {};
    tabs.forEach(function (tab) {
      var name = tab.getAttribute("data-showcase-tab") || "";
      (groups[name] = groups[name] || []).push(tab);
    });

    Object.keys(groups).forEach(function (name) {
      var groupTabs = groups[name];
      var showcase = qs('[data-showcase="' + name + '"]');
      if (!showcase) return;
      var panels = qsa("[data-panel]", showcase);

      groupTabs.forEach(function (tab, index) {
        tab.addEventListener("click", function () {
          var key = tab.getAttribute("data-tab");
          groupTabs.forEach(function (other) { setSelected(other, other === tab); });
          panels.forEach(function (panel) {
            setHidden(panel, panel.getAttribute("data-panel") !== key);
          });
        });

        tab.addEventListener("keydown", function (event) {
          if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
          event.preventDefault();
          var direction = event.key === "ArrowRight" ? 1 : -1;
          var next = groupTabs[(index + direction + groupTabs.length) % groupTabs.length];
          if (next && typeof next.focus === "function") {
            next.focus();
            next.click();
          }
        });
      });
    });
  }

  /* --------------------------- 6. FAQ --------------------------- */
  function initFaq() {
    var filters = qsa("[data-faq-filter]");
    var items = qsa(".fa-faq-item[data-faq-category]");
    var empty = qs("#fa-faq-empty");

    filters.forEach(function (filter) {
      filter.addEventListener("click", function () {
        var category = filter.getAttribute("data-faq-filter");
        filters.forEach(function (other) { setSelected(other, other === filter); });
        var visible = 0;
        items.forEach(function (item) {
          var match = category === "all" || item.getAttribute("data-faq-category") === category;
          setHidden(item, !match);
          if (match) visible += 1;
          else {
            var button = qs("[data-faq-q]", item);
            var answer = button && qs("#" + button.getAttribute("aria-controls"));
            setExpanded(button, false);
            setHidden(answer, true);
          }
        });
        if (empty) setHidden(empty, visible !== 0);
      });
    });

    qsa("[data-faq-q]").forEach(function (button) {
      button.addEventListener("click", function () {
        var answer = qs("#" + button.getAttribute("aria-controls"));
        var open = button.getAttribute("aria-expanded") !== "true";
        setExpanded(button, open);
        setHidden(answer, !open);
      });
    });
  }

  /* ---------------------- 7. language selector ---------------------- */
  function initLanguage() {
    var button = qs("#fa-lang-button");
    var menu = qs("#fa-lang-menu");
    if (!button || !menu) return;

    button.addEventListener("click", function () {
      var open = button.getAttribute("aria-expanded") !== "true";
      setExpanded(button, open);
      setHidden(menu, !open);
    });

    qsa("[data-lang]", menu).forEach(function (option) {
      option.addEventListener("click", function () {
        var label = option.getAttribute("data-lang") || "English";
        qsa("[data-lang]", menu).forEach(function (other) {
          other.setAttribute("aria-checked", other === option ? "true" : "false");
        });
        button.firstChild.nodeValue = label + " ";
        setExpanded(button, false);
        setHidden(menu, true);
        showToast("Language set to " + label + " for this visit");
      });
    });

    document.addEventListener("click", function (event) {
      var target = event.target;
      if (target && typeof button.contains === "function" && button.contains(target)) return;
      if (target && typeof menu.contains === "function" && menu.contains(target)) return;
      setExpanded(button, false);
      setHidden(menu, true);
    });
  }

  /* ----------------------------- boot ----------------------------- */
  safe(initReveal);
  safe(initScrollEffects);
  safe(initMegaNav);
  safe(initMobileMenu);
  safe(initShowcaseTabs);
  safe(initFaq);
  safe(initLanguage);
}());

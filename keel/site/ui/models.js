/* ===========================================================================
   Keel future model concepts - progressive enhancement, no libraries, no network.

   All motion is opt-in: reveals only run when IntersectionObserver exists and
   the visitor has not asked for reduced motion. Scroll listeners are passive
   and throttled with requestAnimationFrame, so nothing busy-loops. Every
   lookup is guarded: a missing element never breaks another section.

   Nothing on these pages contacts a server. The "Get notified" form only
   writes a message into the page and says plainly that nothing was sent.
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

  function setExpanded(node, expanded) {
    if (node && typeof node.setAttribute === "function") {
      node.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function setHidden(node, hidden) {
    if (!node) return;
    var hide = !!hidden;
    node.hidden = hide;
    if (node.classList) node.classList.toggle("is-hidden", hide);
    if (node.style) node.style.display = hide ? "none" : "";
  }

  var reduceMotion = (function () {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)"); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  /* -------------------- 1. reveal on scroll (IO) -------------------- */
  function initReveal() {
    var targets = qsa("[data-reveal]");
    if (!targets.length) return;

    /* Staggered groups get a CSS custom property; no inline handlers. */
    qsa("[data-reveal-group]").forEach(function (group) {
      qsa("[data-reveal]", group).forEach(function (node, index) {
        if (!node.style || node.style.getPropertyValue("--mdl-reveal-delay")) return;
        node.style.setProperty("--mdl-reveal-delay", Math.min(index * 55, 330) + "ms");
      });
    });

    if (prefersReducedMotion() || typeof IntersectionObserver !== "function") {
      targets.forEach(function (node) { node.classList.add("is-revealed"); });
      return;
    }

    /* No-JS visitors never see this class, so their content stays visible. */
    document.documentElement.classList.add("mdl-reveal-ready");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach(function (node) { observer.observe(node); });
  }

  /* ------------- 2. header shadow + per-model parallax (rAF) ------------- */
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
    var header = qs(".mdl-header");
    var layers = qsa("[data-parallax]");
    var allowParallax = !prefersReducedMotion() && layers.length > 0;

    function update() {
      var y = window.pageYOffset || window.scrollY || 0;
      if (header && header.classList) {
        header.classList.toggle("is-scrolled", y > 12);
      }
      if (!allowParallax) return;
      layers.forEach(function (layer) {
        var speed = parseFloat(layer.getAttribute("data-parallax")) || 0;
        var offset = Math.max(-18, Math.min(18, y * speed));
        /* Transform only - no top/left/layout churn. */
        layer.style.transform = "translate3d(0," + offset.toFixed(2) + "px,0)";
      });
    }

    var frame = onScrollFrame(update);
    window.addEventListener("scroll", frame, { passive: true });
    window.addEventListener("resize", frame, { passive: true });
    update();

    if (reduceMotion && typeof reduceMotion.addEventListener === "function") {
      reduceMotion.addEventListener("change", function () {
        allowParallax = !reduceMotion.matches;
        if (!allowParallax) {
          layers.forEach(function (layer) { layer.style.transform = ""; });
        }
        update();
      });
    }
  }

  /* -------------------------------- 3. mega menu ------------------------ */
  function initMegaNav() {
    var triggers = qsa("[data-mega-trigger]");
    if (!triggers.length) return;

    function panelFor(trigger) {
      var id = trigger.getAttribute("aria-controls");
      return id ? document.getElementById(id) : null;
    }

    function closeAll(except) {
      triggers.forEach(function (trigger) {
        if (trigger === except) return;
        var panel = panelFor(trigger);
        var item = trigger.closest ? trigger.closest(".mdl-nav-item") : null;
        setExpanded(trigger, false);
        if (panel) setHidden(panel, true);
        if (item && item.classList) item.classList.remove("is-open");
      });
    }

    triggers.forEach(function (trigger) {
      trigger.addEventListener("click", function (event) {
        if (event) event.stopPropagation();
        var isOpen = trigger.getAttribute("aria-expanded") === "true";
        closeAll(trigger);
        var panel = panelFor(trigger);
        var item = trigger.closest ? trigger.closest(".mdl-nav-item") : null;
        setExpanded(trigger, !isOpen);
        if (panel) setHidden(panel, isOpen);
        if (item && item.classList) item.classList.toggle("is-open", !isOpen);
      });

      var panel = panelFor(trigger);
      if (panel) {
        panel.addEventListener("click", function (event) { if (event) event.stopPropagation(); });
      }
    });

    document.addEventListener("click", function () { closeAll(null); });
    initMegaNav._closeAll = function () { closeAll(null); };
  }

  /* ----------------------------- 4. mobile menu ------------------------- */
  function initMobileMenu() {
    var toggle = qs("[data-mobile-toggle]");
    var menu = qs("#mdl-mobile-menu");
    if (!toggle || !menu) return;

    function close() {
      setExpanded(toggle, false);
      setHidden(menu, true);
      toggle.setAttribute("aria-label", "Open menu");
    }
    function open() {
      setExpanded(toggle, true);
      setHidden(menu, false);
      toggle.setAttribute("aria-label", "Close menu");
    }
    toggle.addEventListener("click", function (event) {
      if (event) event.stopPropagation();
      var isOpen = toggle.getAttribute("aria-expanded") === "true";
      if (isOpen) close(); else open();
      if (typeof initMegaNav._closeAll === "function") initMegaNav._closeAll();
    });
    qsa("a", menu).forEach(function (link) {
      link.addEventListener("click", close);
    });
    initMobileMenu._close = close;
  }

  /* -------------------------------- 5. tabs ----------------------------- */
  function initTabs() {
    var tabs = qsa("[data-tab]");
    if (!tabs.length) return;

    function activate(tab, focus) {
      var group = tab.getAttribute("data-tab");
      var sameGroup = qsa('[data-tab="' + group + '"]');
      sameGroup.forEach(function (other) {
        var selected = other === tab;
        other.setAttribute("aria-selected", selected ? "true" : "false");
        other.tabIndex = selected ? 0 : -1;
        var target = other.getAttribute("aria-controls");
        var panel = target ? document.getElementById(target) : null;
        if (panel) setHidden(panel, !selected);
      });
      if (focus && typeof tab.focus === "function") tab.focus();
    }

    tabs.forEach(function (tab) {
      activate(tab, false);
      tab.addEventListener("click", function () { activate(tab, false); });
      tab.addEventListener("keydown", function (event) {
        if (!event || (event.key !== "ArrowRight" && event.key !== "ArrowLeft")) return;
        var group = tab.getAttribute("data-tab");
        var siblings = qsa('[data-tab="' + group + '"]');
        var index = siblings.indexOf(tab);
        if (index < 0) return;
        var next = event.key === "ArrowRight"
          ? (index + 1) % siblings.length
          : (index - 1 + siblings.length) % siblings.length;
        event.preventDefault();
        activate(siblings[next], true);
      });
    });
  }

  /* -------------------------------- 6. FAQ ------------------------------ */
  function initFaq() {
    var questions = qsa("[data-faq-q]");
    if (!questions.length) return;
    /* Answers are visible by default; this class opts them into animation. */
    document.documentElement.classList.add("mdl-faq-ready");

    function panelFor(question) {
      var controls = question.getAttribute("aria-controls");
      var panel = controls ? document.getElementById(controls) : null;
      if (!panel) {
        var item = question.closest ? question.closest(".mdl-faq-item") : null;
        panel = item ? qs(".mdl-faq-a", item) : null;
      }
      return panel;
    }

    function setOpen(question, open, animate) {
      var panel = panelFor(question);
      var item = question.closest ? question.closest(".mdl-faq-item") : null;
      var shouldAnimate = animate && !prefersReducedMotion();
      setExpanded(question, open);
      if (item && item.classList) item.classList.toggle("is-open", open);
      if (!panel) return;
      panel.setAttribute("aria-hidden", open ? "false" : "true");
      if (!shouldAnimate) {
        if (panel.style) {
          panel.style.visibility = open ? "visible" : "hidden";
          panel.style.maxHeight = open ? "none" : "0px";
        }
        return;
      }
      if (panel.style) panel.style.visibility = "visible";
      if (open) {
        panel.style.maxHeight = panel.scrollHeight + "px";
      } else {
        if (panel.style.maxHeight === "none") panel.style.maxHeight = panel.scrollHeight + "px";
        window.requestAnimationFrame(function () { panel.style.maxHeight = "0px"; });
        setTimeout(function () {
          if (question.getAttribute("aria-expanded") === "false" && panel.style) {
            panel.style.visibility = "hidden";
          }
        }, 260);
      }
    }

    questions.forEach(function (question) {
      setOpen(question, question.getAttribute("aria-expanded") === "true", false);
      question.addEventListener("click", function () {
        var wasOpen = question.getAttribute("aria-expanded") === "true";
        questions.forEach(function (other) {
          if (other !== question && other.getAttribute("aria-expanded") === "true") {
            setOpen(other, false, true);
          }
        });
        setOpen(question, !wasOpen, true);
      });
    });

    var frame = onScrollFrame(function () {
      questions.forEach(function (question) {
        if (question.getAttribute("aria-expanded") !== "true") return;
        var panel = panelFor(question);
        if (panel && panel.style) panel.style.maxHeight = panel.scrollHeight + "px";
      });
    });
    window.addEventListener("resize", frame, { passive: true });
  }

  /* ---------------- 7. Get notified (explicit local-only form) ---------- */
  function initNotify() {
    var form = qs("[data-notify-form]");
    if (!form) return;
    var input = qs("[data-notify-input]", form);
    var result = qs("[data-notify-result]");
    if (!input || !result) return;
    form.noValidate = true;

    function show(message) {
      result.textContent = message;
      setHidden(result, false);
    }

    form.addEventListener("submit", function (event) {
      if (event) event.preventDefault();
      var email = String(input.value || "").replace(/\s+/g, "").trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        show("Please enter a valid email address. Nothing was sent.");
        input.focus();
        return;
      }
      show("Local demo only: " + email + " has been noted in this browser. " +
        "Nothing was sent, no account was created, and no email will arrive. " +
        "Check the roadmap for real availability.");
    });
  }

  /* ---------------------------- 8. language selector -------------------- */
  function initLangSelector() {
    var toggle = qs("[data-lang-toggle]");
    var menu = qs("[data-lang-menu]");
    if (!toggle || !menu) return;

    function close() {
      setExpanded(toggle, false);
      setHidden(menu, true);
      initLangSelector._close = null;
    }
    function open() {
      setExpanded(toggle, true);
      setHidden(menu, false);
      initLangSelector._close = close;
    }
    toggle.addEventListener("click", function (event) {
      if (event) event.stopPropagation();
      if (toggle.getAttribute("aria-expanded") === "true") close(); else open();
    });
    qsa("[data-lang-option]", menu).forEach(function (option) {
      option.addEventListener("click", function () {
        var label = toggle.firstChild;
        if (label && label.nodeType === 3) label.nodeValue = option.textContent + " ";
        close();
      });
    });
    menu.addEventListener("click", function (event) { if (event) event.stopPropagation(); });
    document.addEventListener("click", function () { if (toggle.getAttribute("aria-expanded") === "true") close(); });
    initLangSelector._close = null;
    initLangSelector._closeAll = close;
  }

  /* ---------------------------- 9. global keys -------------------------- */
  function initGlobalKeys() {
    document.addEventListener("keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      if (typeof initLangSelector._closeAll === "function") initLangSelector._closeAll();
      if (typeof initMegaNav._closeAll === "function") initMegaNav._closeAll();
      if (typeof initMobileMenu._close === "function") initMobileMenu._close();
    });
  }

  /* -------------------------------- boot -------------------------------- */
  function init() {
    safe(initReveal);
    safe(initScrollEffects);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initTabs);
    safe(initFaq);
    safe(initNotify);
    safe(initLangSelector);
    safe(initGlobalKeys);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

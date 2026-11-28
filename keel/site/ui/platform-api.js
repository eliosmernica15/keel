/* KEEL — Platform / API page behaviour.
 * Progressive enhancement only: every control works without network access.
 * Scroll work is rAF-throttled, listeners are passive where possible, and all
 * motion is disabled when the visitor prefers reduced motion.
 */
(function () {
  "use strict";

  var doc = document;
  var win = window;

  function qs(selector, root) { return (root || doc).querySelector(selector); }
  function qsa(selector, root) {
    return Array.prototype.slice.call((root || doc).querySelectorAll(selector));
  }
  function on(target, type, handler, options) {
    if (target && target.addEventListener) target.addEventListener(type, handler, options);
  }
  function setHidden(element, hidden) {
    if (!element) return;
    if (hidden) element.setAttribute("hidden", "");
    else element.removeAttribute("hidden");
  }
  function prefersReducedMotion() {
    return !!(win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function closest(element, selector) {
    return element && element.closest ? element.closest(selector) : null;
  }

  /* ------------------------------ toast ------------------------------ */
  var toastTimer = null;
  function showToast(message) {
    var toast = qs(".pa-toast, #pa-toast");
    if (!toast) return;
    toast.textContent = message;
    setHidden(toast, false);
    if (toastTimer) win.clearTimeout(toastTimer);
    toastTimer = win.setTimeout(function () {
      setHidden(toast, true);
      toastTimer = null;
    }, 2400);
  }

  /* ------------------------- scroll reveals ------------------------- */
  function initReveal() {
    var targets = qsa("[data-reveal]");
    if (!targets.length) return;
    if (prefersReducedMotion() || typeof win.IntersectionObserver !== "function") {
      targets.forEach(function (target) { target.classList.add("is-visible"); });
      return;
    }
    var observer = new win.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach(function (target, index) {
      target.style.setProperty("--pa-reveal-delay", (index % 4) * 35 + "ms");
      observer.observe(target);
    });
  }

  /* -------------- progress bar, sticky shadow, parallax -------------- */
  function initScroll() {
    var fill = qs("#pa-progress-fill");
    var header = qs("#pa-header");
    var art = qs(".pa-hero-art, [data-pa-parallax]");
    var ticking = false;

    function update() {
      var root = doc.documentElement || doc.body;
      var top = win.pageYOffset || root.scrollTop || 0;
      var travel = Math.max(1, (root.scrollHeight || 0) - (win.innerHeight || 0));

      if (fill && fill.style) {
        fill.style.width = Math.min(100, Math.max(0, (top / travel) * 100)).toFixed(2) + "%";
      }
      if (header) header.classList.toggle("is-scrolled", top > 6);

      if (art && art.style) {
        if (prefersReducedMotion()) {
          art.style.transform = "none";
        } else {
          var shift = Math.max(-12, Math.min(12, top * 0.035));
          art.style.transform = "translate3d(0, " + shift.toFixed(1) + "px, 0)";
        }
      }
    }

    function frame() {
      if (ticking) return;
      ticking = true;
      if (typeof window.requestAnimationFrame === "function") {
        window.requestAnimationFrame(function () { update(); ticking = false; });
      } else {
        update();
        ticking = false;
      }
    }

    win.addEventListener("scroll", frame, { passive: true });
    win.addEventListener("resize", frame, { passive: true });
    update();
  }

  /* ---------------------- product mega menu ---------------------- */
  function initNav() {
    var items = qsa("[data-pa-nav]");
    function closeAll(except) {
      items.forEach(function (item) {
        if (item === except) return;
        item.classList.remove("is-open");
        var trigger = qs(".pa-nav-trigger", item);
        var panel = qs(".pa-mega", item);
        if (trigger) trigger.setAttribute("aria-expanded", "false");
        setHidden(panel, true);
      });
    }
    items.forEach(function (item) {
      var trigger = qs(".pa-nav-trigger", item);
      var panel = qs(".pa-mega", item);
      function setOpen(open) {
        closeAll(open ? item : null);
        item.classList.toggle("is-open", open);
        if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
        setHidden(panel, !open);
      }
      on(trigger, "click", function (event) {
        event.preventDefault();
        var open = trigger.getAttribute("aria-expanded") !== "true";
        setOpen(open);
      });
      on(item, "mouseenter", function () { setOpen(true); });
      on(item, "mouseleave", function () { setOpen(false); });
      on(panel, "click", function (event) {
        if (closest(event.target, "a")) setOpen(false);
      });
    });
    on(doc, "click", function (event) {
      if (closest(event.target, "[data-pa-nav]")) return;
      closeAll(null);
    });
  }

  /* ------------------------- mobile menu ------------------------- */
  function initMobile() {
    var button = qs(".pa-hamburger");
    var panel = qs("#pa-mobile-menu");
    if (!button || !panel) return;
    function setOpen(open) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
      button.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      setHidden(panel, !open);
    }
    on(button, "click", function () {
      setOpen(button.getAttribute("aria-expanded") !== "true");
    });
    on(panel, "click", function (event) {
      if (closest(event.target, "a")) setOpen(false);
    });
    doc.closeMobileMenu = function () { setOpen(false); };
  }

  /* --------------------------- tabs --------------------------- */
  function initTabs(selector) {
    var tabs = qsa(selector);
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
      on(tab, "click", function () {
        tabs.forEach(function (other) {
          var active = other === tab;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-selected", active ? "true" : "false");
          var panel = qs("#" + other.getAttribute("aria-controls"));
          if (panel) setHidden(panel, !active);
        });
      });
    });
  }

  /* -------------------------- accordions -------------------------- */
  function initAccordions() {
    qsa(".pa-accordion-q").forEach(function (button) {
      on(button, "click", function () {
        var item = closest(button, ".pa-accordion-item");
        var panel = qs("#" + button.getAttribute("aria-controls"));
        var open = button.getAttribute("aria-expanded") !== "true";
        button.setAttribute("aria-expanded", open ? "true" : "false");
        if (item) item.classList.toggle("is-open", open);
        if (panel) panel.setAttribute("aria-hidden", open ? "false" : "true");
      });
    });
  }

  /* --------------------------- copy --------------------------- */
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var helper = doc.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      doc.body.appendChild(helper);
      helper.select();
      var ok = false;
      try { ok = doc.execCommand("copy"); } catch (error) { ok = false; }
      doc.body.removeChild(helper);
      if (ok) resolve();
      else reject(new Error("clipboard unavailable"));
    });
  }

  function initCopy() {
    on(doc, "click", function (event) {
      var button = closest(event.target, ".pa-copy, [data-pa-copy]");
      if (!button) return;
      event.preventDefault();
      var id = button.getAttribute("data-pa-copy");
      var source = qs("#" + id);
      if (!source) return;
      copyToClipboard(source.textContent).then(function () {
        button.classList.add("is-done");
        button.textContent = "Copied";
        showToast("Copied " + id.replace(/^pa-code-/, "") + " to clipboard");
        win.setTimeout(function () {
          button.classList.remove("is-done");
          button.textContent = "Copy";
        }, 1600);
      }).catch(function () {
        showToast("Clipboard unavailable — select the code and copy it manually");
      });
    });
  }

  /* --------------------------- modal --------------------------- */
  var modalState = { lastTrigger: null, saved: null };

  function appendText(tag, text, className, parent) {
    var node = doc.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    parent.appendChild(node);
    return node;
  }
  function appendLink(text, href, parent) {
    var link = appendText("a", text, "", parent);
    link.setAttribute("href", href);
    return link;
  }
  function resetModal(title, desc, body) {
    if (!title || !desc || !body) return;
    title.textContent = "Keel API quick reference";
    desc.textContent = "A short local reference for the Keel Platform API. No network request is made.";
    if (modalState.saved) body.innerHTML = modalState.saved;
  }
  function buildModal(mode, trigger) {
    var title = qs("#pa-modal-title");
    var desc = qs("#pa-modal-desc");
    var body = qs("#pa-modal-body");
    if (!title || !desc || !body) return;
    if (!modalState.saved) modalState.saved = body.innerHTML;

    var infoTitle = trigger && trigger.getAttribute("data-pa-info-title");
    var infoBody = trigger && trigger.getAttribute("data-pa-info-body");

    if (mode === "docs") {
      resetModal(title, desc, body);
      return;
    }

    clearBody(body);
    if (mode === "contact") {
      title.textContent = "Contact sales";
      desc.textContent = "Reach the Keel team directly.";
      appendText("p", "Email our sales team or sign in to the console for enterprise options.", "", body);
      appendLink("sales@keel.dev", "mailto:sales@keel.dev?subject=Contact%20sales", body);
    } else if (mode === "signup") {
      title.textContent = "Get API key";
      desc.textContent = "API keys are created in the Keel Console.";
      appendText("p", "Sign in to create and manage keys, members, and token limits for your workspace.", "", body);
      appendLink("Open the console", "/login", body);
    } else if (mode === "video") {
      title.textContent = infoTitle || "Introducing Keel Managed Agents";
      desc.textContent = "Local demo — no video is streamed in this static build.";
      appendText("p", infoBody || "Managed Agents keep state across long-running sessions and trace every step.", "", body);
      appendLink("Get started with Managed Agents", "/login", body);
    } else {
      title.textContent = infoTitle || "Keel Platform";
      desc.textContent = "Local detail panel";
      appendText("p", infoBody || "See the documentation for current details.", "", body);
      appendLink("Read the docs", "/requirements", body);
    }
  }

  function clearBody(body) {
    body.textContent = "";
  }

  function openModal(mode, trigger) {
    var modal = qs("#pa-modal");
    if (!modal) return;
    modalState.lastTrigger = trigger || null;
    buildModal(mode, trigger);
    setHidden(modal, false);
    doc.body.classList.add("pa-modal-open");
    var close = qs("[data-pa-modal-close]", modal);
    if (close && close.focus) close.focus();
  }

  function closeModal() {
    var modal = qs("#pa-modal");
    if (!modal || modal.hasAttribute("hidden")) return;
    setHidden(modal, true);
    doc.body.classList.remove("pa-modal-open");
    if (modalState.lastTrigger && modalState.lastTrigger.focus) modalState.lastTrigger.focus();
    modalState.lastTrigger = null;
  }

  function initModal() {
    on(doc, "click", function (event) {
      var target = event.target;
      if (!target || typeof target.closest !== "function") return;

      if (closest(target, ".pa-modal-close, [data-pa-modal-close], .pa-modal-backdrop, [data-pa-modal-backdrop]")) {
        closeModal();
        return;
      }
      var copy = closest(target, ".pa-copy, [data-pa-copy]");
      if (copy) return;

      var video = closest(target, ".pa-video-card, [data-pa-video]");
      if (video) {
        event.preventDefault();
        openModal("video", video);
        return;
      }
      var trigger = closest(target, "[data-pa-modal]");
      if (trigger) {
        event.preventDefault();
        openModal(trigger.getAttribute("data-pa-modal") || "info", trigger);
      }
    });
    on(doc, "keydown", function (event) {
      if (event.key === "Escape") {
        closeModal();
        if (doc.closeMobileMenu) doc.closeMobileMenu();
      }
    });
  }

  /* ------------------------- language select ------------------------- */
  function initLanguage() {
    on(doc, "change", function (event) {
      var select = closest(event.target, ".pa-lang");
      if (!select) return;
      var option = qs("option:checked", select);
      showToast("Language set to " + (option ? option.textContent : select.value) + " (local demo)");
    });
  }

  /* ------------------------------- boot ------------------------------- */
  function boot() {
    initReveal();
    initScroll();
    initNav();
    initMobile();
    initTabs(".pa-connect-tab");
    initTabs(".pa-cost-tab");
    initAccordions();
    initCopy();
    initModal();
    initLanguage();
  }

  if (doc.readyState === "loading") on(doc, "DOMContentLoaded", boot);
  else boot();
})();

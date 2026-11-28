/* Keel for Microsoft 365 — local page interactions.
 *
 * Nothing here signs in to Microsoft, installs an add-in, or changes a tenant.
 * Every action either moves within the page, follows an existing site route,
 * or opens an honest dialog with real next steps.
 */
(function setupMicrosoft365Page() {
  "use strict";

  if (!document.body || !document.body.classList.contains("m365-page")) return;

  var dialog = document.getElementById("m365-dialog");
  var dialogContent = document.getElementById("m365-dialog-content");
  var lastTrigger = null;

  var STORY_STEPS = [
    "Step 1: Open Word and tell Keel what the brief should cover. It drafts a first version inside the document.",
    "Step 2: Add your own notes and ask for a tighter summary. The change stays visible so you can compare it.",
    "Step 3: Review the result, share the file with your team, and keep the session with it for later."
  ];
  var storyIndex = 0;

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* ------------------------------ navigation ----------------------------- */
  function initMegaMenu() {
    var items = document.querySelectorAll("[data-m365-mega]");
    if (!items.length) return;

    function setOpen(item, open) {
      item.classList.toggle("is-open", open);
      var trigger = item.querySelector("[data-m365-mega-trigger]");
      if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    function closeAll(except) {
      for (var i = 0; i < items.length; i += 1) {
        if (items[i] !== except) setOpen(items[i], false);
      }
    }

    for (var i = 0; i < items.length; i += 1) {
      (function (item) {
        var trigger = item.querySelector("[data-m365-mega-trigger]");
        if (trigger) {
          trigger.addEventListener("click", function (event) {
            event.preventDefault();
            var open = !item.classList.contains("is-open");
            closeAll(item);
            setOpen(item, open);
          });
        }
        item.addEventListener("mouseenter", function () {
          closeAll(item);
          setOpen(item, true);
        });
        item.addEventListener("mouseleave", function () { setOpen(item, false); });
      })(items[i]);
    }

    document.addEventListener("click", function (event) {
      if (event.target.closest && !event.target.closest("[data-m365-mega]")) closeAll();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAll();
    });
  }

  function initMobileNav() {
    var toggle = document.querySelector("[data-m365-nav-toggle]");
    var menu = document.getElementById("m365-mobile-menu");
    if (!toggle || !menu) return;
    toggle.addEventListener("click", function () {
      var open = !menu.classList.contains("is-open");
      menu.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.classList.contains("is-open")) {
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open menu");
      }
    });
  }

  /* ------------------------------ dialogs -------------------------------- */
  function focusableIn(node) {
    return node.querySelectorAll('a[href], button:not([disabled]), select, [tabindex]:not([tabindex="-1"])');
  }

  function setStoryStep(index) {
    if (!dialog) return;
    var text = dialog.querySelector("[data-m365-story-text]");
    var count = dialog.querySelector("[data-m365-story-count]");
    var previous = dialog.querySelector('[data-m365-story-step="-1"]');
    var next = dialog.querySelector('[data-m365-story-step="1"]');
    if (!text) return;
    storyIndex = Math.max(0, Math.min(STORY_STEPS.length - 1, index));
    text.textContent = STORY_STEPS[storyIndex];
    if (count) count.textContent = (storyIndex + 1) + " / " + STORY_STEPS.length;
    if (previous) previous.disabled = storyIndex === 0;
    if (next) next.disabled = storyIndex === STORY_STEPS.length - 1;
  }

  function setDemoTab(value) {
    if (!dialog) return;
    var tabs = dialog.querySelectorAll("[data-m365-demo-tab]");
    var panels = dialog.querySelectorAll("[data-m365-demo-panel]");
    var found = false;
    for (var i = 0; i < tabs.length; i += 1) {
      var active = tabs[i].getAttribute("data-m365-demo-tab") === value;
      tabs[i].classList.toggle("is-active", active);
      tabs[i].setAttribute("aria-selected", active ? "true" : "false");
      tabs[i].tabIndex = active ? 0 : -1;
      if (active) found = true;
    }
    if (!found) return;
    for (var j = 0; j < panels.length; j += 1) {
      panels[j].hidden = panels[j].getAttribute("data-m365-demo-panel") !== value;
    }
  }

  function openDialog(kind, trigger) {
    var template = document.getElementById("m365-tpl-" + kind);
    if (!dialog || !dialogContent || !template || !template.content) return;
    lastTrigger = trigger || null;
    while (dialogContent.firstChild) dialogContent.removeChild(dialogContent.firstChild);
    dialogContent.appendChild(template.content.cloneNode(true));
    dialog.hidden = false;
    document.body.classList.add("m365-dialog-open");
    if (kind === "story") setStoryStep(0);
    if (kind === "admin") setDemoTab("assign");
    var close = dialog.querySelector(".m365-dialog-close");
    if (close) close.focus();
  }

  function closeDialog() {
    if (!dialog || dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove("m365-dialog-open");
    if (lastTrigger && lastTrigger.focus) lastTrigger.focus();
    lastTrigger = null;
  }

  function initDialog() {
    if (!dialog) return;
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      var opener = target.closest("[data-m365-dialog-open]");
      if (opener) {
        event.preventDefault();
        openDialog(opener.getAttribute("data-m365-dialog-open"), opener);
        return;
      }
      var step = target.closest("[data-m365-story-step]");
      if (step) {
        setStoryStep(storyIndex + Number(step.getAttribute("data-m365-story-step")));
        return;
      }
      var tab = target.closest("[data-m365-demo-tab]");
      if (tab) {
        setDemoTab(tab.getAttribute("data-m365-demo-tab"));
        return;
      }
      if (target.closest("[data-m365-dialog-close]") || target === dialog) closeDialog();
    });

    document.addEventListener("keydown", function (event) {
      if (dialog.hidden) return;
      if (event.key === "Escape") {
        closeDialog();
        return;
      }
      var tab = event.target.closest && event.target.closest("[data-m365-demo-tab]");
      if (tab && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
        var tabs = dialog.querySelectorAll("[data-m365-demo-tab]");
        var index = Array.prototype.indexOf.call(tabs, tab);
        var step = event.key === "ArrowRight" ? 1 : -1;
        var next = tabs[(index + step + tabs.length) % tabs.length];
        setDemoTab(next.getAttribute("data-m365-demo-tab"));
        next.focus();
        return;
      }
      if (event.key === "Tab") {
        var focusable = focusableIn(dialog);
        if (!focusable.length) return;
        var first = focusable[0];
        var last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    });
  }

  /* -------------------------------- accordion ---------------------------- */
  function initFaq() {
    var questions = document.querySelectorAll("[data-m365-faq]");
    if (!questions.length) return;
    function closeAll() {
      for (var i = 0; i < questions.length; i += 1) {
        questions[i].setAttribute("aria-expanded", "false");
        var answer = document.getElementById(questions[i].getAttribute("aria-controls"));
        if (answer) answer.hidden = true;
      }
    }
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      var button = target.closest("[data-m365-faq]");
      if (!button) return;
      var wasOpen = button.getAttribute("aria-expanded") === "true";
      closeAll();
      if (!wasOpen) {
        button.setAttribute("aria-expanded", "true");
        var answer = document.getElementById(button.getAttribute("aria-controls"));
        if (answer) answer.hidden = false;
      }
    });
  }

  /* --------------------------------- reveal ------------------------------ */
  function initReveal() {
    var nodes = document.querySelectorAll(".m365-reveal");
    if (!nodes.length) return;
    if (reducedMotion() || !("IntersectionObserver" in window)) {
      for (var i = 0; i < nodes.length; i += 1) nodes[i].classList.add("is-visible");
      return;
    }
    var observer = new IntersectionObserver(function (entries, obs) {
      for (var i = 0; i < entries.length; i += 1) {
        if (!entries[i].isIntersecting) continue;
        entries[i].target.classList.add("is-visible");
        obs.unobserve(entries[i].target);
      }
    }, { threshold: 0.1, rootMargin: "0px 0px -30px 0px" });
    for (var j = 0; j < nodes.length; j += 1) observer.observe(nodes[j]);
  }

  /* ------------------------------ sticky header -------------------------- */
  function initStickyHeader() {
    var header = document.getElementById("site-header");
    if (!header) return;
    var queued = false;
    function update() {
      header.classList.toggle("is-scrolled", window.pageYOffset > 8);
      queued = false;
    }
    window.addEventListener("scroll", function () {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(update);
    }, { passive: true });
    update();
  }

  /* ------------------------------- language ------------------------------ */
  function initLanguage() {
    var select = document.querySelector("[data-m365-language]");
    var status = document.getElementById("m365-lang-status");
    if (!select || !status) return;
    select.addEventListener("change", function () {
      var label = select.options[select.selectedIndex].text;
      status.textContent = "Language preference saved: " + label + ". This page stays in English.";
    });
  }

  function init() {
    initMegaMenu();
    initMobileNav();
    initDialog();
    initFaq();
    initReveal();
    initStickyHeader();
    initLanguage();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

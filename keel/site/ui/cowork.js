/* ===========================================================================
   KEEL Cowork — progressive enhancement, no libraries, no network calls.
   Every lookup is guarded, every scroll listener is passive + rAF-throttled,
   and reduced motion disables the reveal/parallax layer entirely.
   =========================================================================== */
(function () {
  "use strict";

  function qs(selector, root) {
    try { return (root || document).querySelector(selector) || null; }
    catch (error) { return null; }
  }
  function qsa(selector, root) {
    try { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
    catch (error) { return []; }
  }
  function safe(setup) { try { setup(); } catch (error) { /* never break the page */ } }
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
  function nodeText(node) {
    return node ? String(node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }
  function storageGet(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function storageSet(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* blocked */ } }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  var reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  /* ------------------------------- toast ------------------------------- */
  var toastTimer = null;
  function showToast(message) {
    var toast = qs("#cw-toast");
    if (!toast || !message) return;
    toast.textContent = message;
    setHidden(toast, false);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      setHidden(toast, true);
    }, 3600);
  }

  /* ------------------- scroll reveal + parallax + header ---------------- */
  function initScrollMotion() {
    var header = qs("#cw-header");
    var parallaxNodes = qsa("[data-parallax]").filter(function (node) {
      return !reduced && node && node.style;
    });
    var pending = false;

    function apply() {
      pending = false;
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      if (header && header.classList) header.classList.toggle("cw-scrolled", y > 8);
      if (!reduced) {
        parallaxNodes.forEach(function (node) {
          var factor = parseFloat(node.getAttribute("data-parallax")) || 0;
          var offset = Math.max(-14, Math.min(14, y * factor));
          node.style.transform = "translate3d(0, " + offset.toFixed(1) + "px, 0)";
        });
      }
    }
    function onScroll() {
      if (pending) return;
      pending = true;
      window.requestAnimationFrame(apply);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    apply();

    var targets = qsa("[data-reveal]");
    if (reduced || !("IntersectionObserver" in window)) {
      targets.forEach(function (node) { if (node.classList) node.classList.add("is-visible"); });
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        if (entry.target.classList) entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.08 });
    targets.forEach(function (node) { observer.observe(node); });
  }

  /* -------------------------- mega navigation -------------------------- */
  function initMegaNav() {
    var items = qsa("[data-nav]");
    if (!items.length) return;
    var records = items.map(function (item) {
      return {
        item: item,
        trigger: qs("button", item),
        mega: qs(".cw-mega", item),
        open: false
      };
    });
    var pointerDown = false;

    function render(record, open) {
      record.open = !!open;
      if (record.item && record.item.classList) record.item.classList.toggle("is-open", record.open);
      if (record.trigger) setExpanded(record.trigger, record.open);
      if (record.mega) setHidden(record.mega, !record.open);
    }
    function closeAll(except) {
      records.forEach(function (record) {
        if (record.item !== except && record.open) render(record, false);
      });
    }
    function toggle(record) {
      var willOpen = !record.open;
      closeAll(record.item);
      render(record, willOpen);
    }
    records.forEach(function (record, index) {
      if (!record.trigger && !record.mega) return;
      render(record, false);
      if (record.item) {
        record.item.addEventListener("mouseenter", function () {
          if (pointerDown) return;
          closeAll(record.item);
          render(record, true);
        });
        record.item.addEventListener("mouseleave", function () {
          if (record.item.contains && record.item.contains(document.activeElement)) return;
          render(record, false);
        });
      }
      if (record.trigger) {
        record.trigger.addEventListener("pointerdown", function () { pointerDown = true; });
        record.trigger.addEventListener("click", function (event) {
          if (event && event.preventDefault) event.preventDefault();
          pointerDown = false;
          toggle(record);
        });
        record.trigger.addEventListener("keydown", function (event) {
          if (!event) return;
          if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
            if (event.repeat) { event.preventDefault(); return; }
            event.preventDefault();
            toggle(record);
            return;
          }
          var next = -1;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            closeAll(record.item);
            render(record, true);
            var first = record.mega ? qs("a[href], button", record.mega) : null;
            if (first && first.focus) first.focus();
            return;
          }
          if (event.key === "ArrowRight") next = (index + 1) % records.length;
          else if (event.key === "ArrowLeft") next = (index - 1 + records.length) % records.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = records.length - 1;
          if (next >= 0 && next !== index) {
            event.preventDefault();
            closeAll();
            render(records[next], true);
            if (records[next].trigger && records[next].trigger.focus) records[next].trigger.focus();
          }
        });
      }
      if (record.mega) {
        record.mega.addEventListener("click", function (event) {
          var target = event && event.target;
          if (target && target.closest && target.closest("a, button")) render(record, false);
        });
      }
    });
    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (target && target.closest && !target.closest("[data-nav]")) closeAll();
    });
    window.addEventListener("pointerup", function () { pointerDown = false; });
    window.addEventListener("pointercancel", function () { pointerDown = false; });
    initMegaNav._closeAll = function () { closeAll(); };
  }

  /* ---------------------------- mobile menu ---------------------------- */
  function initMobileMenu() {
    var toggle = qs(".cw-hamburger");
    var menu = qs("#cw-mobile-menu");
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, false);
    function render(open) {
      setHidden(menu, !open);
      setExpanded(toggle, !!open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      if (document.body && document.body.classList) document.body.classList.toggle("cw-menu-open", !!open);
    }
    initMobileMenu._close = function () { render(false); };
    toggle.addEventListener("click", function () { render(menu.hidden); });
    menu.addEventListener("click", function (event) {
      var target = event && event.target;
      if (target && target.closest && target.closest("a, button")) render(false);
    });
    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || menu.hidden) return;
      if (target.closest && target.closest(".cw-hamburger, #cw-mobile-menu")) return;
      render(false);
    });
    var resizePending = false;
    window.addEventListener("resize", function () {
      if (resizePending) return;
      resizePending = true;
      window.requestAnimationFrame(function () {
        resizePending = false;
        if (window.innerWidth > 1099 && !menu.hidden) render(false);
      });
    }, { passive: true });
  }

  /* Generic tab helper used by the window demo, task demo and plan cards. */
  function initTabs(selector, keyName, onSelect) {
    var tabs = qsa(selector);
    if (!tabs.length) return;
    function select(tab, moveFocus) {
      tabs.forEach(function (other) {
        var active = other === tab;
        other.setAttribute("aria-selected", active ? "true" : "false");
        if (other.classList) other.classList.toggle("is-active", active);
        other.tabIndex = active ? 0 : -1;
      });
      if (onSelect) onSelect(tab.getAttribute(keyName) || "", tabs);
      if (moveFocus && tab.focus) tab.focus();
    }
    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () { select(tab, false); });
      tab.addEventListener("keydown", function (event) {
        if (!event) return;
        var next = -1;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        if (next < 0 || next === index) return;
        event.preventDefault();
        select(tabs[next], true);
      });
    });
    var initial = tabs.filter(function (tab) {
      return tab.getAttribute("aria-selected") === "true";
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ------------------------- hero window tabs -------------------------- */
  function initWindowTabs() {
    var panels = qsa("[data-window-panel]");
    initTabs("[data-window-tab]", "data-window-tab", function (key) {
      panels.forEach(function (panel) {
        setHidden(panel, panel.getAttribute("data-window-panel") !== key);
      });
    });
  }

  /* ---------------------------- task tabs ------------------------------ */
  var TASK_DATA = {
    reports: {
      prompt: "Every Monday morning, build last week's marketing readout. Pull web views and signups from Amplitude, and the newsletter, social, and webinar numbers from Marketing/Channel-tracker in Drive. Compare everything to the week before. Slide one: company name and the week. Slide two: awareness metrics with anything that moved more than 10% flagged. Slide three: consideration metrics, same flags. Note any trend worth watching and anything you couldn't pull. Save to Marketing/Weekly in Drive.",
      connectors: ["Amplitude", "Microsoft 365"],
      slidesAlt: "Generated weekly marketing readout deck",
      dataAlt: "Weekly marketing metrics table",
      caption: "Schedule recurring reports, ready for review",
      body: "Schedule a report once and get it daily, weekly, or monthly. KEEL pulls the numbers, compares them to the period before, and builds the deck, so Monday starts with the readout instead of the assembly."
    },
    sheets: {
      prompt: "Take the sales export in Microsoft 365 and build a spreadsheet that breaks revenue by region and rep, adds month-over-month growth, and highlights the three biggest movers. Keep the source tabs intact and add a clean summary tab at the front.",
      connectors: ["Microsoft 365", "Amplitude"],
      slidesAlt: "Generated revenue spreadsheet preview",
      dataAlt: "Revenue breakdown data table",
      caption: "Build spreadsheets from your own files",
      body: "KEEL works directly in your folders, keeps your originals untouched, and delivers a spreadsheet you can open, check, and share."
    },
    review: {
      prompt: "Review every support ticket closed this week. Flag the ones with unresolved customer questions, summarize the common themes, and draft a short reply for each flagged ticket. Leave the rest as they are.",
      connectors: ["Microsoft 365", "Amplitude"],
      slidesAlt: "Generated bulk review summary",
      dataAlt: "Support ticket review table",
      caption: "Review in bulk without losing the detail",
      body: "Point KEEL at a folder of documents and it works through them one by one, surfacing what matters and drafting changes for your approval."
    },
    notes: {
      prompt: "Read all of this week's customer call notes, group the feedback by theme, and write a one-page summary with the top requests, the biggest complaints, and direct quotes worth keeping. Flag anything you are unsure about.",
      connectors: ["Amplitude", "Microsoft 365"],
      slidesAlt: "Generated notes analysis deck",
      dataAlt: "Customer feedback theme table",
      caption: "Turn scattered notes into clear answers",
      body: "KEEL reads across your notes, finds the patterns, and writes up the findings with the source material close at hand so you can verify every point."
    }
  };

  function initTaskTabs() {
    var panel = qs("#cw-task-panel");
    var prompt = qs("[data-prompt]", panel);
    var caption = qs("[data-task-caption]", panel);
    var desc = qs("[data-task-desc]", panel);
    var images = qsa("[data-view-image]", panel);
    var chips = qsa("[data-connector]", panel);
    var viewButtons = qsa("[data-view]", panel);
    var note = qs(".cw-task-note", panel);

    function setView(view) {
      viewButtons.forEach(function (button) {
        var active = button.getAttribute("data-view") === view;
        button.setAttribute("aria-pressed", active ? "true" : "false");
        if (button.classList) button.classList.toggle("is-active", active);
      });
      images.forEach(function (image) {
        setHidden(image, image.getAttribute("data-view-image") !== view);
      });
    }
    function setConnector(chip, name) {
      if (!chip || !name) return;
      var label = qs(".cw-connector-name", chip);
      if (label) label.textContent = name;
    }
    initTabs("[data-task]", "data-task", function (key) {
      var data = TASK_DATA[key];
      if (!data) return;
      if (prompt) prompt.textContent = data.prompt;
      if (caption) caption.textContent = data.caption;
      if (desc) desc.textContent = data.body;
      if (images[0]) images[0].setAttribute("alt", data.slidesAlt);
      if (images[1]) images[1].setAttribute("alt", data.dataAlt);
      chips.forEach(function (chip, index) {
        if (data.connectors[index]) setConnector(chip, data.connectors[index]);
      });
      setView("slides");
    });
    viewButtons.forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        setView(button.getAttribute("data-view") || "slides");
      });
    });
    if (note) note.setAttribute("aria-live", "polite");
  }

  /* ---------------------------- checklist ------------------------------ */
  function initChecklist() {
    var boxes = qsa("[data-check]");
    var progress = qs("[data-check-progress]");
    if (!boxes.length || !progress) return;
    function update() {
      var done = boxes.filter(function (box) { return box.checked; }).length;
      progress.textContent = done + " of " + boxes.length + " complete";
    }
    boxes.forEach(function (box) { box.addEventListener("change", update); });
    update();
  }

  /* ----------------------------- plan tabs ----------------------------- */
  function initPlanTabs() {
    var panels = qsa("[data-plan-panel]");
    initTabs("[data-plan]", "data-plan", function (key) {
      panels.forEach(function (panel) {
        setHidden(panel, panel.getAttribute("data-plan-panel") !== key);
      });
    });
  }

  /* ------------------------------ accordion ---------------------------- */
  function initAccordion() {
    var questions = qsa("[data-faq]");
    if (!questions.length) return;
    function panelFor(question) {
      var controls = question.getAttribute("aria-controls");
      var panel = controls ? document.getElementById(controls) : null;
      if (!panel && question.closest) {
        var item = question.closest(".cw-acc-item");
        panel = item ? qs(".cw-acc-a", item) : null;
      }
      return panel;
    }
    function setOpen(question, open) {
      setExpanded(question, open);
      if (question.classList) question.classList.toggle("is-active", open);
      var item = question.closest ? question.closest(".cw-acc-item") : null;
      if (item && item.classList) item.classList.toggle("is-open", open);
      var panel = panelFor(question);
      if (panel) setHidden(panel, !open);
    }
    questions.forEach(function (question) {
      setOpen(question, false);
      question.addEventListener("click", function () {
        var wasOpen = question.getAttribute("aria-expanded") === "true";
        questions.forEach(function (other) { if (other !== question) setOpen(other, false); });
        setOpen(question, !wasOpen);
      });
    });
  }

  /* ------------------------------- modals ------------------------------ */
  var lastFocused = null;
  var openModalNode = null;
  var MODAL_FOR_ACTION = { "open-contact": "contact-modal", "open-video": "video-modal" };

  function dialogOf(modal) { return qs(".cw-modal-dialog", modal) || modal; }
  function focusableIn(modal) {
    return qsa('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])', dialogOf(modal));
  }
  function openModal(modal, trigger) {
    if (!modal) return;
    closeModal();
    lastFocused = trigger || document.activeElement;
    openModalNode = modal;
    setHidden(modal, false);
    modal.setAttribute("aria-hidden", "false");
    if (document.body && document.body.classList) document.body.classList.add("cw-modal-open");
    var focusables = focusableIn(modal);
    var target = focusables[0];
    if (target && target.focus) target.focus();
  }
  function closeModal() {
    if (!openModalNode) return;
    var modal = openModalNode;
    openModalNode = null;
    setHidden(modal, true);
    modal.setAttribute("aria-hidden", "true");
    if (document.body && document.body.classList) document.body.classList.remove("cw-modal-open");
    if (lastFocused && document.contains && document.contains(lastFocused) && lastFocused.focus) {
      lastFocused.focus();
    }
    lastFocused = null;
  }
  function initModals() {
    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || !target.closest) return;
      var actionNode = target.closest("[data-action]");
      var action = actionNode ? actionNode.getAttribute("data-action") : "";
      if (action && MODAL_FOR_ACTION[action]) {
        event.preventDefault();
        openModal(document.getElementById(MODAL_FOR_ACTION[action]), actionNode);
        return;
      }
      if (target.closest("[data-close-modal]") || target.closest(".cw-modal-backdrop") || target === openModalNode) {
        closeModal();
      }
    });
    qsa(".cw-modal").forEach(function (modal) {
      modal.addEventListener("keydown", function (event) {
        if (!event || event.key !== "Tab" || modal.hidden) return;
        var focusables = focusableIn(modal);
        if (!focusables.length) return;
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      });
    });
  }

  /* -------------------------------- forms ------------------------------ */
  function wrapFor(field) {
    return (field.closest && (field.closest(".cw-field") || field.parentNode)) || field.parentNode;
  }
  function errorFor(field) {
    var wrap = wrapFor(field);
    if (!wrap) return null;
    var error = qs(".cw-field-error", wrap);
    if (!error) {
      error = document.createElement("span");
      error.className = "cw-field-error";
      error.setAttribute("role", "alert");
      setHidden(error, true);
      wrap.appendChild(error);
    }
    return error;
  }
  function setFieldError(field, message) {
    var error = errorFor(field);
    if (error) { error.textContent = message || ""; setHidden(error, !message); }
    if (message) field.setAttribute("aria-invalid", "true");
    else field.removeAttribute("aria-invalid");
  }
  function initForms() {
    var contact = qs('[data-form="contact"]');
    if (contact) {
      contact.noValidate = true;
      contact.addEventListener("submit", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        var valid = true;
        qsa("[required]", contact).forEach(function (field) {
          var value = String(field.value || "").trim();
          var message = "";
          if (!value) message = "This field is required.";
          else if (field.type === "email" && !EMAIL_RE.test(value)) message = "Enter a valid work email.";
          setFieldError(field, message);
          if (message) valid = false;
        });
        if (!valid) return;
        showToast("Thanks — we'll be in touch.");
        contact.reset();
        qsa("input, textarea", contact).forEach(function (field) { setFieldError(field, ""); });
        closeModal();
      });
      qsa("input, textarea", contact).forEach(function (field) {
        field.addEventListener("input", function () { setFieldError(field, ""); });
      });
    }
    var search = qs('[data-form="footer-search"]');
    if (search) {
      search.noValidate = true;
      search.addEventListener("submit", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        var input = qs("input", search);
        var term = input ? String(input.value || "").trim() : "";
        if (!term) { if (input && input.focus) input.focus(); return; }
        showToast("Searching KEEL for “" + term + "”");
      });
    }
  }

  /* --------------------------- video control --------------------------- */
  function initVideo() {
    var play = qs("[data-video-play]");
    var label = qs(".cw-video-label", play);
    if (!play) return;
    play.addEventListener("click", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      var playing = play.getAttribute("aria-pressed") === "true";
      play.setAttribute("aria-pressed", playing ? "false" : "true");
      play.setAttribute("aria-label", playing ? "Play video" : "Pause video");
      if (label) label.textContent = playing ? "Play" : "Playing";
    });
  }

  /* -------------------------- language picker -------------------------- */
  function initLanguage() {
    var select = qs("[data-lang]");
    if (!select) return;
    select.addEventListener("change", function () {
      var option = select.options && select.options[select.selectedIndex];
      showToast("Language set to " + (option ? nodeText(option) : select.value) + " (demo)");
    });
  }

  /* ---------------------------- global keys ---------------------------- */
  function initGlobalKeys() {
    document.addEventListener("keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      if (openModalNode) { closeModal(); return; }
      if (initMegaNav._closeAll) initMegaNav._closeAll();
      if (initMobileMenu._close) initMobileMenu._close();
    });
  }

  /* -------------------------------- boot ------------------------------- */
  function init() {
    safe(initScrollMotion);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initWindowTabs);
    safe(initTaskTabs);
    safe(initChecklist);
    safe(initPlanTabs);
    safe(initAccordion);
    safe(initModals);
    safe(initVideo);
    safe(initForms);
    safe(initLanguage);
    safe(initGlobalKeys);
    /* Remember the choice so a language change survives a reload. */
    safe(function () {
      var select = qs("[data-lang]");
      var saved = select ? storageGet("cw-lang") : null;
      if (select && saved) select.value = saved;
      if (select) select.addEventListener("change", function () { storageSet("cw-lang", select.value); });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

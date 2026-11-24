/* ===========================================================================
   KEEL Cowork — progressive enhancement, no libraries, no network calls.
   Every lookup is guarded: a missing hook never breaks the rest of the page.
   All selectors use data-* hooks, never styling classes, per the shared
   implementation contract (KEEL_COWORK_CONTRACT.md).
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

  /* One broken section must not stop the others. */
  function safe(setup) {
    try { setup(); } catch (error) { /* UI enhancements must never throw */ }
  }

  function setExpanded(node, expanded) {
    if (node && typeof node.setAttribute === "function") {
      node.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function nodeText(node) {
    return node ? String(node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  /* hidden plus an inline display keeps state authoritative even when a
     stylesheet sets display on the same selector. */
  function setHidden(node, hidden) {
    if (!node) return;
    var hide = !!hidden;
    node.hidden = hide;
    if (node.classList) node.classList.toggle("is-hidden", hide);
    if (node.style) node.style.display = hide ? "none" : "";
  }

  function storageGet(key) {
    try { return window.localStorage.getItem(key); }
    catch (error) { return null; }
  }

  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); }
    catch (error) { /* storage may be blocked — the UI still works */ }
  }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  /* ------------------------------ toast ------------------------------ */
  var toastTimer = null;

  function showToast(message) {
    var toast = qs("#cw-toast");
    if (!toast || !message) return;
    toast.textContent = message;
    setHidden(toast, false);
    if (toast.classList) toast.classList.add("is-visible");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      setHidden(toast, true);
      if (toast.classList) toast.classList.remove("is-visible");
    }, 3800);
  }

  /* ------------------- 1. Header scrolled state ------------------- */
  function initHeaderScroll() {
    var header = qs("#cw-header");
    if (!header) return;
    function apply() {
      var scrolled = (window.pageYOffset || document.documentElement.scrollTop || 0) > 8;
      if (header.classList) header.classList.toggle("cw-scrolled", scrolled);
    }
    window.addEventListener("scroll", apply, { passive: true });
    apply();
  }

  /* -------------------- 2. Mega dropdown menus -------------------- */
  function initMegaNav() {
    var items = qsa("[data-nav]");
    if (!items.length) return;

    var records = items.map(function (item) {
      return {
        item: item,
        trigger: qs(".cw-nav-trigger", item) || qs("button", item),
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
        if (record.item === except) return;
        if (record.open) render(record, false);
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

      if (record.trigger && !record.trigger.hasAttribute("aria-expanded")) {
        setExpanded(record.trigger, false);
      }

      /* Hovering another trigger closes the previously open menu. */
      if (record.item) {
        record.item.addEventListener("mouseenter", function () {
          if (pointerDown) return;
          closeAll(record.item);
          render(record, true);
        });
        record.item.addEventListener("mouseleave", function () {
          if (typeof record.item.contains === "function" &&
              record.item.contains(document.activeElement)) return;
          render(record, false);
        });
      }

      if (record.trigger) {
        record.trigger.addEventListener("pointerdown", function () { pointerDown = true; });
        record.trigger.addEventListener("click", function (event) {
          if (event && typeof event.preventDefault === "function") event.preventDefault();
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
            if (first && typeof first.focus === "function") first.focus();
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
            if (records[next].trigger && typeof records[next].trigger.focus === "function") {
              records[next].trigger.focus();
            }
          }
        });
      }

      /* Following a link inside a panel dismisses it. */
      if (record.mega) {
        record.mega.addEventListener("click", function (event) {
          var target = event && event.target;
          if (target && typeof target.closest === "function" && target.closest("a, button")) {
            record.item.classList.remove("is-open");
            render(record, false);
          }
        });
      }
    });

    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest === "function") {
        if (target && !target.closest("[data-nav]")) closeAll();
      }
    });
    window.addEventListener("pointerup", function () { pointerDown = false; });
    window.addEventListener("pointercancel", function () { pointerDown = false; });

    initMegaNav._closeAll = function () { closeAll(); };
  }

  /* ---------------------- 3. Mobile drawer ---------------------- */
  function initMobileMenu() {
    var toggle = qs(".cw-hamburger");
    var menu = qs("#cw-mobile-menu");
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, false);

    function render(open) {
      setHidden(menu, !open);
      setExpanded(toggle, !!open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      if (document.body && document.body.classList) {
        document.body.classList.toggle("cw-menu-open", !!open);
      }
    }
    function close() { render(false); }
    initMobileMenu._close = close;

    toggle.addEventListener("click", function () { render(menu.hidden); });

    menu.addEventListener("click", function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === "function" && target.closest("a, button")) close();
    });

    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || menu.hidden) return;
      if (typeof target.closest === "function" &&
          target.closest(".cw-hamburger, #cw-mobile-menu")) return;
      close();
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 900 && !menu.hidden) close();
    });
  }

  /* ---------------------- 4. News toast ---------------------- */
  function initNews() {
    var news = qs("#cw-news");
    var button = qs('[data-action="dismiss-news"]');
    if (!news) return;
    if (storageGet("cw-news-dismissed") === "1") setHidden(news, true);
    if (!button) return;
    button.addEventListener("click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      setHidden(news, true);
      storageSet("cw-news-dismissed", "1");
    });
  }

  /* ---------------------- 5. Task tabs ---------------------- */
  var TASK_DATA = {
    reports: {
      prompt: "Every Monday morning, build last week's marketing readout. Pull web views and signups from Amplitude, and the newsletter, social, and webinar numbers from Marketing/Channel-tracker in Drive. Compare everything to the week before. Slide one: company name and the week. Slide two: awareness metrics with anything that moved more than 10% flagged. Slide three: consideration metrics, same flags. Note any trend worth watching and anything you couldn't pull. Save to Marketing/Weekly in Drive.",
      connectors: ["Amplitude", "Microsoft 365"],
      slidesAlt: "Generated weekly marketing readout deck",
      dataAlt: "Weekly marketing metrics table",
      slidesLabel: "Slides",
      dataLabel: "Data",
      caption: "Schedule recurring reports, ready for review",
      body: "Schedule a report once and get it daily, weekly, or monthly. KEEL pulls the numbers, compares them to the period before, and builds the deck, so Monday starts with the readout instead of the assembly."
    },
    sheets: {
      prompt: "Take the sales export in Microsoft 365 and build a spreadsheet that breaks revenue by region and rep, adds month-over-month growth, and highlights the three biggest movers. Keep the source tabs intact and add a clean summary tab at the front.",
      connectors: ["Microsoft 365", "Amplitude"],
      slidesAlt: "Generated revenue spreadsheet preview",
      dataAlt: "Revenue breakdown data table",
      slidesLabel: "Slides",
      dataLabel: "Data",
      caption: "Build spreadsheets from your own files",
      body: "KEEL works directly in your folders, keeps your originals untouched, and delivers a spreadsheet you can open, check, and share."
    },
    review: {
      prompt: "Review every support ticket closed this week. Flag the ones with unresolved customer questions, summarize the common themes, and draft a short reply for each flagged ticket. Leave the rest as they are.",
      connectors: ["Microsoft 365", "Amplitude"],
      slidesAlt: "Generated bulk review summary",
      dataAlt: "Support ticket review table",
      slidesLabel: "Slides",
      dataLabel: "Data",
      caption: "Review in bulk without losing the detail",
      body: "Point KEEL at a folder of documents and it works through them one by one, surfacing what matters and drafting changes for your approval."
    },
    notes: {
      prompt: "Read all of this week's customer call notes, group the feedback by theme, and write a one-page summary with the top requests, the biggest complaints, and direct quotes worth keeping. Flag anything you are unsure about.",
      connectors: ["Amplitude", "Microsoft 365"],
      slidesAlt: "Generated notes analysis deck",
      dataAlt: "Customer feedback theme table",
      slidesLabel: "Slides",
      dataLabel: "Data",
      caption: "Turn scattered notes into clear answers",
      body: "KEEL reads across your notes, finds the patterns, and writes up the findings with the source material close at hand so you can verify every point."
    }
  };

  function initTaskTabs() {
    var tabs = qsa("[data-task]");
    if (!tabs.length) return;
    var panel = qs(".cw-task-panel") || (tabs[0].closest ? tabs[0].closest("section") : null) || document;
    var prompt = qs("[data-prompt]", panel);
    var caption = qs(".cw-task-caption", panel);
    var captionBody = caption && caption.nextElementSibling ? caption.nextElementSibling : null;
    var visual = qs(".cw-task-visual", panel);
    var images = visual ? qsa("img", visual) : [];
    var chips = qsa(".cw-connector, [data-connector]", panel);
    var viewButtons = qsa("[data-view]", panel);
    var note = qs(".cw-task-note", panel);

    function setConnector(chip, name) {
      if (!chip || !name) return;
      var label = qs(".cw-connector-name", chip);
      if (!label) {
        var img = qs("img", chip);
        label = document.createElement("span");
        label.className = "cw-connector-name";
        if (img && img.nextSibling) chip.insertBefore(label, img.nextSibling);
        else chip.appendChild(label);
      }
      label.textContent = name;
    }

    function setView(view) {
      viewButtons.forEach(function (button) {
        var active = (button.getAttribute("data-view") || "slides") === view;
        button.setAttribute("aria-pressed", active ? "true" : "false");
        if (button.classList) button.classList.toggle("is-active", active);
      });
      if (images.length >= 2) {
        setHidden(images[0], view !== "slides");
        setHidden(images[1], view !== "data");
      }
    }

    function select(tab, moveFocus) {
      var key = tab.getAttribute("data-task") || "reports";
      var data = TASK_DATA[key];
      tabs.forEach(function (other) {
        var active = other === tab;
        other.setAttribute("aria-selected", active ? "true" : "false");
        if (other.classList) other.classList.toggle("is-active", active);
        other.tabIndex = active ? 0 : -1;
      });
      if (data) {
        if (prompt) prompt.textContent = data.prompt;
        if (caption) caption.textContent = data.caption;
        if (captionBody) captionBody.textContent = data.body;
        if (images[0]) images[0].setAttribute("alt", data.slidesAlt);
        if (images[1]) images[1].setAttribute("alt", data.dataAlt);
        chips.forEach(function (chip, index) {
          if (data.connectors && data.connectors[index]) setConnector(chip, data.connectors[index]);
        });
        setView("slides");
      }
      if (moveFocus && typeof tab.focus === "function") tab.focus();
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

    viewButtons.forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        setView(button.getAttribute("data-view") || "slides");
      });
    });

    if (note) note.setAttribute("aria-live", "polite");
    var initial = tabs.filter(function (tab) {
      return tab.getAttribute("aria-selected") === "true" ||
        (tab.classList && tab.classList.contains("is-active"));
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ---------------------- 6. Carousels ---------------------- */
  function initCarousels() {
    ["plugins", "quotes"].forEach(function (name) {
      var controls = qsa('[data-carousel="' + name + '"]');
      if (!controls.length) return;

      var root = null;
      controls.some(function (button) {
        var found = button.closest ? button.closest(".cw-carousel") : null;
        if (found) { root = found; return true; }
        return false;
      });
      if (!root) root = name === "plugins" ? qs("#plugins-list") : qs("#control");
      if (!root) return;

      var slides = qsa(".cw-slide, [data-slide]", root);
      if (!slides.length) return;
      var count = qs(".cw-carousel-count", root) || qs(".cw-carousel-count");
      var index = 0;

      function render() {
        slides.forEach(function (slide, i) { setHidden(slide, i !== index); });
        if (count) count.textContent = (index + 1) + " of " + slides.length;
      }

      function move(direction) {
        index = (index + direction + slides.length) % slides.length;
        render();
      }

      controls.forEach(function (button) {
        var isPrev = /prev/i.test(String(button.className || "")) ||
          button.getAttribute("data-dir") === "prev";
        button.addEventListener("click", function (event) {
          if (event && typeof event.preventDefault === "function") event.preventDefault();
          move(isPrev ? -1 : 1);
        });
      });

      /* Arrow keys work while focus is inside this carousel. */
      function onKey(event) {
        if (!event || !root.contains || !root.contains(document.activeElement)) return;
        if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
        else if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
      }
      document.addEventListener("keydown", onKey);

      if (count) count.setAttribute("aria-live", "polite");
      render();
    });
  }

  /* ---------------------- 7. Persona tabs ---------------------- */
  var PERSONA_DATA = {
    marketing: {
      title: "KEEL Cowork for marketing",
      desc: "See how KEEL uses KEEL Cowork to gather weekly reviews on a schedule.",
      poster: "/assets/img/cw-video-marketing.svg"
    },
    sales: {
      title: "KEEL Cowork for sales",
      desc: "See how a sales team uses KEEL Cowork to prepare for calls and follow up with accounts.",
      poster: "/assets/img/cw-video-sales.svg"
    },
    legal: {
      title: "KEEL Cowork for legal",
      desc: "See how a legal team uses KEEL Cowork to review contracts and flag the terms that matter.",
      poster: "/assets/img/cw-video-legal.svg"
    }
  };

  function initPersonaTabs() {
    var tabs = qsa("[data-persona]");
    if (!tabs.length) return;
    var section = tabs[0].closest ? tabs[0].closest("section") : (qs("#usecase") || document);
    var poster = qs(".cw-video-poster", section) || qs('img[src*="cw-video"]', section);
    var caption = qs(".cw-usecase-caption", section);
    var heading = caption ? qs("h3", caption) : qs("h3", section);
    var desc = caption ? qs("p", caption) : (heading && heading.nextElementSibling);

    function select(tab, moveFocus) {
      var key = tab.getAttribute("data-persona") || "marketing";
      var data = PERSONA_DATA[key];
      tabs.forEach(function (other) {
        var active = other === tab;
        other.setAttribute("aria-selected", active ? "true" : "false");
        if (other.classList) other.classList.toggle("is-active", active);
        other.tabIndex = active ? 0 : -1;
      });
      if (data) {
        if (poster) poster.setAttribute("src", data.poster);
        if (heading) heading.textContent = data.title;
        if (desc) desc.textContent = data.desc;
      }
      if (moveFocus && typeof tab.focus === "function") tab.focus();
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
      return tab.getAttribute("aria-selected") === "true" ||
        (tab.classList && tab.classList.contains("is-active"));
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ---------------------- 8. Plan tabs ---------------------- */
  function initPlanTabs() {
    var tabs = qsa("[data-plan]");
    if (!tabs.length) return;
    var panels = qsa("[data-plan-panel], [data-plan-set], .cw-plan-set");
    var cards = qsa(".cw-plan-card[data-plan]");

    function keyOf(node) {
      return node.getAttribute("data-plan-panel") ||
        node.getAttribute("data-plan-set") || node.getAttribute("data-plan") || "";
    }

    function select(tab, moveFocus) {
      var key = tab.getAttribute("data-plan") || "individual";
      tabs.forEach(function (other) {
        var active = other === tab;
        other.setAttribute("aria-selected", active ? "true" : "false");
        if (other.classList) other.classList.toggle("is-active", active);
        other.tabIndex = active ? 0 : -1;
      });
      panels.forEach(function (panel) { setHidden(panel, keyOf(panel) !== key); });
      cards.forEach(function (card) { setHidden(card, card.getAttribute("data-plan") !== key); });
      if (moveFocus && typeof tab.focus === "function") tab.focus();
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
      return tab.getAttribute("aria-selected") === "true" ||
        (tab.classList && tab.classList.contains("is-active"));
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ---------------------- 9. FAQ accordion ---------------------- */
  function initFaq() {
    var questions = qsa("[data-faq]");
    if (!questions.length) questions = qsa(".cw-faq-q");
    if (!questions.length) return;

    function panelFor(question) {
      var controls = question.getAttribute("aria-controls");
      var panel = controls ? document.getElementById(controls) : null;
      if (!panel) {
        var item = question.closest ? question.closest(".cw-faq-item") : null;
        panel = item ? qs(".cw-faq-a", item) : null;
      }
      return panel;
    }

    function setOpen(question, open) {
      setExpanded(question, open);
      if (question.classList) question.classList.toggle("is-active", open);
      var item = question.closest ? question.closest(".cw-faq-item") : null;
      if (item && item.classList) item.classList.toggle("is-open", open);
      var panel = panelFor(question);
      if (panel) setHidden(panel, !open);
    }

    questions.forEach(function (question) {
      setOpen(question, false);
      question.addEventListener("click", function () {
        var wasOpen = question.getAttribute("aria-expanded") === "true";
        questions.forEach(function (other) {
          if (other !== question) setOpen(other, false);
        });
        setOpen(question, !wasOpen);
      });
    });
  }

  /* ---------------------- 10. Form validation ---------------------- */
  function wrapFor(field) {
    if (field.closest) {
      return field.closest("[data-field]") || field.closest(".cw-field") || field.parentNode;
    }
    return field.parentNode;
  }

  function errorFor(field) {
    var wrap = wrapFor(field);
    if (!wrap) return null;
    var error = qs(".cw-field-error", wrap);
    if (!error) {
      error = document.createElement("p");
      error.className = "cw-field-error";
      error.setAttribute("role", "alert");
      setHidden(error, true);
      wrap.appendChild(error);
    }
    return error;
  }

  function setFieldError(field, message) {
    var error = errorFor(field);
    if (error) {
      error.textContent = message || "";
      setHidden(error, !message);
    }
    if (message) field.setAttribute("aria-invalid", "true");
    else field.removeAttribute("aria-invalid");
  }

  function validateForm(form) {
    var valid = true;
    var fields = qsa("input[required], textarea[required], select[required], [data-required]", form);
    fields.forEach(function (field) {
      var value = String(field.value || "").replace(/\s+/g, " ").trim();
      var isEmail = field.type === "email" ||
        field.getAttribute("data-validate") === "email" ||
        /email/i.test(field.name || "");
      var message = "";
      if (!value) message = "This field is required.";
      else if (isEmail && !EMAIL_RE.test(value)) {
        message = "Enter a valid email address, like you@company.com.";
      }
      setFieldError(field, message);
      if (message) valid = false;
    });
    return valid;
  }

  function initForms() {
    /* Contact / sales modal form. */
    var contact = qs('[data-form="contact"]');
    if (contact) {
      contact.noValidate = true;
      contact.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        if (!validateForm(contact)) return;
        showToast("Thanks — we'll be in touch.");
        contact.reset();
        qsa("input, textarea", contact).forEach(function (field) { setFieldError(field, ""); });
      });
      qsa("input, textarea", contact).forEach(function (field) {
        field.addEventListener("input", function () { setFieldError(field, ""); });
      });
    }

    /* Auth modal form. */
    var auth = qs('[data-form="auth"]') || qs("#auth-modal form");
    var authModal = qs("#auth-modal");
    if (auth) {
      auth.noValidate = true;
      auth.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var input = qs('input[type="email"]', auth) || qs("input", auth);
        if (!input) return;
        var value = String(input.value || "").trim();
        if (!EMAIL_RE.test(value)) {
          setFieldError(input, "Enter a valid email address, like you@company.com.");
          if (typeof input.focus === "function") input.focus();
          return;
        }
        setFieldError(input, "");
        showToast("Signed in as " + value + ".");
        auth.reset();
        if (typeof closeModal === "function") closeModal(authModal);
      });
      var authInput = qs('input[type="email"]', auth) || qs("input", auth);
      if (authInput) authInput.addEventListener("input", function () { setFieldError(authInput, ""); });
    }

    /* Google (demo) button inside the auth modal. */
    if (authModal) {
      var google = qs('[data-action="auth-google"], .cw-auth-google', authModal);
      if (!google) {
        google = qsa("button", authModal).filter(function (button) {
          return /google/i.test(nodeText(button));
        })[0] || null;
      }
      if (google) {
        google.setAttribute("type", "button");
        google.addEventListener("click", function (event) {
          if (event && typeof event.preventDefault === "function") event.preventDefault();
          showToast("Signed in as demo@google.com.");
          if (typeof closeModal === "function") closeModal(authModal);
        });
      }
    }

    /* Footer search. */
    var search = qs('[data-form="footer-search"]');
    if (search) {
      search.noValidate = true;
      search.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var input = qs("input", search) || qs('[data-search-input]');
        var term = input ? String(input.value || "").replace(/\s+/g, " ").trim() : "";
        if (!term) {
          if (input && typeof input.focus === "function") input.focus();
          return;
        }
        showToast("Searching KEEL for '" + term + "'");
      });
    }
  }

  /* ---------------------- 11. Modals ---------------------- */
  var MODAL_FOR_ACTION = {
    "open-contact": "contact-modal",
    "open-auth": "auth-modal",
    "open-video": "video-modal"
  };
  var lastFocused = null;
  var openModalNode = null;

  function dialogOf(modal) {
    return qs(".cw-modal-dialog", modal) || modal;
  }

  function focusableIn(modal) {
    return qsa(
      'a[href], button:not([disabled]), input:not([disabled]), ' +
      'textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      dialogOf(modal)
    ).filter(function (node) {
      return !node.hidden && !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
    });
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
    var target = focusables[0] || qs("button, input, a[href]", dialogOf(modal));
    if (target && typeof target.focus === "function") target.focus();
  }

  function closeModal() {
    if (!openModalNode) return;
    var modal = openModalNode;
    openModalNode = null;
    setHidden(modal, true);
    modal.setAttribute("aria-hidden", "true");
    if (document.body && document.body.classList) document.body.classList.remove("cw-modal-open");
    /* Let the video modal stop its progress interval when it closes. */
    if (modal.id === "video-modal" && typeof modal.dispatchEvent === "function" &&
        typeof Event === "function") {
      modal.dispatchEvent(new Event("cw:close"));
    }
    if (lastFocused && typeof document.contains === "function" &&
        document.contains(lastFocused) && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
    lastFocused = null;
  }

  function initModals() {
    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      var actionNode = target.closest("[data-action]");
      var action = actionNode ? actionNode.getAttribute("data-action") : "";
      if (action && MODAL_FOR_ACTION[action]) {
        event.preventDefault();
        var id = MODAL_FOR_ACTION[action];
        openModal(document.getElementById(id), actionNode);
        return;
      }
      if (action === "close-modal") {
        event.preventDefault();
        closeModal();
        return;
      }
      if (target.closest(".cw-modal-close") || target.closest(".cw-modal-backdrop") ||
          target.closest("[data-close-modal]")) {
        closeModal();
        return;
      }
      /* Clicking the modal padding (outside the dialog) closes it. */
      if (openModalNode && target === openModalNode) closeModal();
    });

    qsa(".cw-modal").forEach(function (modal) {
      var closeButton = qs(".cw-modal-close", modal);
      var backdrop = qs(".cw-modal-backdrop", modal);
      if (closeButton) closeButton.addEventListener("click", closeModal);
      if (backdrop) backdrop.addEventListener("click", closeModal);

      modal.addEventListener("keydown", function (event) {
        if (!event || event.key !== "Tab" || modal.hidden) return;
        var focusables = focusableIn(modal);
        if (!focusables.length) return;
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });
    });

    qsa(".cw-modal").forEach(function (modal) {
      if (!modal.hasAttribute("aria-hidden")) modal.setAttribute("aria-hidden", "true");
    });
  }

  /* ---------------------- 12. Video modal ---------------------- */
  function initVideo() {
    var modal = qs("#video-modal");
    if (!modal) return;
    var play = qs(".cw-video-play", modal) || qs('[data-action="toggle-video"]', modal);
    var bar = qs(".cw-video-bar", modal) || qs(".cw-video-progress span", modal) ||
      qs(".cw-video-progress", modal);
    var label = qs(".cw-video-label", modal) || qs(".cw-video-label", play);
    if (!play) return;
    if (!label) {
      label = document.createElement("span");
      label.className = "cw-video-label";
      play.appendChild(label);
    }

    var timer = null;
    var progress = 0;
    var DURATION = 12000;
    var STEP = 1; /* percent added per tick */

    function paint() {
      if (bar) bar.style.width = progress + "%";
    }

    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
      if (label) label.textContent = "Play";
      play.setAttribute("aria-label", "Play video");
    }

    function start() {
      if (timer) return;
      if (progress >= 100) progress = 0;
      if (label) label.textContent = "Pause";
      play.setAttribute("aria-label", "Pause video");
      timer = setInterval(function () {
        progress += STEP;
        if (progress >= 100) { progress = 100; paint(); stop(); return; }
        paint();
      }, DURATION / 100);
    }

    play.addEventListener("click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      if (timer) stop(); else start();
    });

    modal.addEventListener("cw:close", stop);
    paint();
  }

  /* ---------------------- 13. Cookie consent ---------------------- */
  function initCookies() {
    var banner = qs("#cw-cookie");
    if (!banner) return;
    if (storageGet("cw-cookie-choice")) setHidden(banner, true);

    qsa('[data-action="cookie-accept"], [data-action="cookie-decline"]').forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var choice = button.getAttribute("data-action") === "cookie-accept" ? "accepted" : "declined";
        storageSet("cw-cookie-choice", choice);
        setHidden(banner, true);
      });
    });
  }

  /* ---------------------- 14. Language select ---------------------- */
  function initLanguage() {
    var select = qs("[data-lang]");
    if (!select) return;
    select.addEventListener("change", function () {
      var option = select.options && select.options[select.selectedIndex];
      var label = option ? nodeText(option) : String(select.value || "");
      showToast("Language set to " + label + " (demo)");
    });
  }

  /* ---------------------- 15. Global keys ---------------------- */
  function initGlobalKeys() {
    document.addEventListener("keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      if (openModalNode) {
        event.preventDefault();
        closeModal();
        return;
      }
      if (typeof initMegaNav._closeAll === "function") initMegaNav._closeAll();
      if (typeof initMobileMenu._close === "function") initMobileMenu._close();
    });
  }

  /* ----------------------------- Boot ----------------------------- */
  function init() {
    safe(initHeaderScroll);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initNews);
    safe(initTaskTabs);
    safe(initCarousels);
    safe(initPersonaTabs);
    safe(initPlanTabs);
    safe(initFaq);
    safe(initModals);
    safe(initVideo);
    safe(initForms);
    safe(initCookies);
    safe(initLanguage);
    safe(initGlobalKeys);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

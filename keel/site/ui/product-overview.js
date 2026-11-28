/* ===========================================================================
   Keel product overview — progressive enhancement, no libraries, no network.

   All motion is opt-in: reveals only run when IntersectionObserver exists and
   the visitor has not asked for reduced motion. Scroll listeners are passive
   and throttled with requestAnimationFrame, so nothing busy-loops.
   Every lookup is guarded: a missing element never breaks another section.
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

  function nodeText(node) {
    return node ? String(node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  function setHidden(node, hidden) {
    if (!node) return;
    var hide = !!hidden;
    node.hidden = hide;
    if (node.classList) node.classList.toggle("is-hidden", hide);
    if (node.style) node.style.display = hide ? "none" : "";
  }

  function norm(value) {
    return String(value == null ? "" : value)
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  function tokens(value) {
    return String(value == null ? "" : value).split(/[,\s|]+/).map(norm).filter(Boolean);
  }

  var ACRONYMS = {
    ai: "AI", api: "API", crm: "CRM", hr: "HR", okr: "OKR", qbr: "QBR",
    q1: "Q1", q2: "Q2", q3: "Q3", q4: "Q4"
  };
  var MINOR_WORDS = {
    a: true, an: true, and: true, as: true, at: true, but: true, by: true,
    for: true, from: true, in: true, into: true, of: true, on: true,
    or: true, the: true, to: true, with: true
  };

  function titleCase(value) {
    var words = String(value == null ? "" : value).trim().split(/\s+/).filter(Boolean);
    return words.map(function (word, index) {
      var lower = word.toLowerCase();
      if (ACRONYMS[lower]) return ACRONYMS[lower];
      if (index > 0 && MINOR_WORDS[lower]) return lower;
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    }).join(" ");
  }

  var reduceMotion = (function () {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)"); }
    catch (error) { return { matches: false, addEventListener: null }; }
  }());

  function prefersReducedMotion() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  /* ------------------------ shared toast / auth bridge ---------------- */
  var toastTimer = null;

  function showToast(message) {
    var toast = qs("#po-toast");
    if (!toast || !message) return;
    toast.textContent = message;
    setHidden(toast, false);
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      setHidden(toast, true);
    }, 3800);
  }

  var authBridge = { open: null, close: null, setContext: null };
  var pendingPrompt = "";

  function rememberPrompt(prompt) {
    pendingPrompt = String(prompt == null ? "" : prompt).replace(/\s+/g, " ").trim();
    var askInput = qs("#po-ask-input");
    if (askInput && askInput.type !== "email") askInput.value = pendingPrompt;
    if (authBridge.setContext) authBridge.setContext(pendingPrompt);
  }

  /* -------------------- 1. reveal on scroll (IO) -------------------- */
  function initReveal() {
    var targets = qsa("[data-reveal]");
    if (!targets.length) return;

    /* Give staggered groups a CSS custom property; no inline handlers. */
    qsa("[data-reveal-group]").forEach(function (group) {
      qsa("[data-reveal]", group).forEach(function (node, index) {
        if (!node.style || node.style.getPropertyValue("--po-reveal-delay")) return;
        node.style.setProperty("--po-reveal-delay", Math.min(index * 55, 330) + "ms");
      });
    });

    if (prefersReducedMotion() || typeof IntersectionObserver !== "function") {
      targets.forEach(function (node) { node.classList.add("is-revealed"); });
      return;
    }

    document.documentElement.classList.add("po-reveal-ready");
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
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
    var header = qs("#po-header, .po-site-header");
    var cards = qsa("[data-parallax]");
    var allowParallax = !prefersReducedMotion() && cards.length > 0;

    function update() {
      var y = window.pageYOffset || window.scrollY || 0;
      if (header && header.classList) {
        header.classList.toggle("is-scrolled", y > 12);
      }
      if (!allowParallax) return;
      cards.forEach(function (card) {
        var speed = parseFloat(card.getAttribute("data-parallax")) || 0;
        var offset = Math.max(-20, Math.min(20, y * speed));
        /* Transform only — no top/left/layout churn. */
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

  /* --------------------- 3. Mega dropdown menus --------------------- */
  function initMegaNav() {
    var items = qsa(".po-nav-item[data-nav]");
    if (!items.length) return;

    var records = items.map(function (item) {
      return {
        item: item,
        trigger: qs(".po-nav-trigger", item),
        mega: qs(".po-mega", item),
        pinned: false,
        open: false,
        openTimer: null,
        closeTimer: null,
        suppressFocus: false,
        keyHandledUntil: 0
      };
    });
    var pointerDown = false;

    function clearTimers(record) {
      if (record.openTimer) { clearTimeout(record.openTimer); record.openTimer = null; }
      if (record.closeTimer) { clearTimeout(record.closeTimer); record.closeTimer = null; }
    }

    function render(record, open) {
      record.open = !!open;
      if (record.item && record.item.classList) record.item.classList.toggle("is-open", record.open);
      if (record.trigger) setExpanded(record.trigger, record.open);
      if (record.mega) {
        setHidden(record.mega, !record.open);
        if (record.mega.classList) record.mega.classList.toggle("is-open", record.open);
      }
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
        record.suppressFocus = true;
      } else {
        closeAll(record.item);
        render(record, true);
        record.pinned = true;
      }
    }

    records.forEach(function (record, index) {
      var item = record.item;
      var trigger = record.trigger;
      if (trigger && !trigger.hasAttribute("aria-expanded")) setExpanded(trigger, false);
      render(record, false);

      /* Hover intent: quick open, leisurely close. */
      item.addEventListener("mouseenter", function () {
        if (pointerDown) return;
        clearTimers(record);
        record.openTimer = setTimeout(function () {
          record.openTimer = null;
          closeAll(item);
          render(record, true);
        }, 90);
      });
      item.addEventListener("mouseleave", function () {
        clearTimers(record);
        record.closeTimer = setTimeout(function () {
          record.closeTimer = null;
          if (record.pinned) return;
          if (typeof item.contains === "function" && item.contains(document.activeElement)) return;
          render(record, false);
        }, 180);
      });

      if (trigger) {
        trigger.addEventListener("pointerdown", function () {
          pointerDown = true;
          record.suppressFocus = true;
          clearTimers(record);
        });
        trigger.addEventListener("click", function () {
          pointerDown = false;
          if (Date.now() < record.keyHandledUntil) {
            record.keyHandledUntil = 0;
            return;
          }
          toggle(record);
        });
        trigger.addEventListener("keydown", function (event) {
          if (!event) return;
          var key = event.key;
          if (key === "Enter" || key === " " || key === "Spacebar") {
            if (event.repeat) { event.preventDefault(); return; }
            event.preventDefault();
            record.keyHandledUntil = Date.now() + 500;
            toggle(record);
            return;
          }
          if (key === "ArrowDown") {
            event.preventDefault();
            closeAll(item);
            render(record, true);
            record.pinned = true;
            var firstLink = record.mega ? qs("a[href], button", record.mega) : null;
            if (firstLink && typeof firstLink.focus === "function") firstLink.focus();
            return;
          }
          var next = -1;
          if (key === "ArrowRight") next = (index + 1) % records.length;
          else if (key === "ArrowLeft") next = (index - 1 + records.length) % records.length;
          else if (key === "Home") next = 0;
          else if (key === "End") next = records.length - 1;
          if (next >= 0 && next !== index) {
            event.preventDefault();
            closeAll();
            var other = records[next];
            render(other, true);
            other.pinned = true;
            if (other.trigger && typeof other.trigger.focus === "function") other.trigger.focus();
          }
        });
      }

      item.addEventListener("focusin", function () {
        if (record.suppressFocus || pointerDown) return;
        clearTimers(record);
        closeAll(item);
        render(record, true);
      });
      item.addEventListener("focusout", function (event) {
        var next = event && event.relatedTarget;
        if (next && typeof item.contains === "function" && item.contains(next)) return;
        clearTimers(record);
        if (!record.pinned) render(record, false);
        record.suppressFocus = false;
      });

      item.addEventListener("click", function (event) {
        var target = event && event.target;
        if (!target || typeof target.closest !== "function") return;
        if (target.closest(".po-nav-trigger")) return;
        if (target.closest("a, button")) {
          record.pinned = false;
          closeAll();
        }
      });
    });

    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      if (!target.closest(".po-nav-item")) closeAll();
    });
    window.addEventListener("pointerup", function () { pointerDown = false; });
    window.addEventListener("pointercancel", function () { pointerDown = false; });

    initMegaNav._closeAll = function () { closeAll(null, true); };
  }

  /* ------------------------ 4. Mobile menu ------------------------ */
  function initMobileMenu() {
    var toggle = qs(".po-hamburger, #po-hamburger");
    var menu = qs("#po-mobile-menu");
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, false);

    function render(open) {
      setHidden(menu, !open);
      setExpanded(toggle, !!open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
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
      if (!target || typeof target.closest !== "function") return;
      if (menu.hidden) return;
      if (target.closest(".po-hamburger, #po-mobile-menu")) return;
      close();
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900 && !menu.hidden) close();
    });
  }

  /* ---------------- 5. Put Keel to work: surface tabs ---------------- */
  function initWorkTabs() {
    var tabs = qsa(".po-work-tab[data-work-tab]");
    var panels = qsa(".po-work-panel[data-work-panel]");
    if (!tabs.length || !panels.length) return;

    function select(tab, moveFocus) {
      var key = norm(tab.getAttribute("data-work-tab") || "");
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
        other.tabIndex = active ? 0 : -1;
      });
      panels.forEach(function (panel) {
        setHidden(panel, norm(panel.getAttribute("data-work-panel")) !== key);
      });
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
      return tab.classList && tab.classList.contains("is-active");
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ------------- 6. Hub filter tabs (All / knowledge / dev) ------------- */
  function initCapabilities() {
    var input = qs("#po-cap-search");
    var section = qs(".po-capabilities, #po-capabilities");
    var nodes = qsa(".po-hub-node[data-caps]");
    var cards = qsa(".po-cap-card[data-caps]");
    var tabs = qsa(".po-cap-tab[data-cap-tab]");
    if (!nodes.length && !cards.length) return;

    var empty = qs("#po-cap-empty");
    if (!empty && section) {
      empty = document.createElement("p");
      empty.id = "po-cap-empty";
      empty.className = "po-cap-empty";
      empty.textContent = "No work matches that filter.";
      section.appendChild(empty);
    }

    var activeTab = "all";
    var activeTabNode = tabs.filter(function (tab) {
      return tab.classList && tab.classList.contains("is-active");
    })[0];
    if (activeTabNode) activeTab = norm(activeTabNode.getAttribute("data-cap-tab") || "all");

    /* Per-node timers keep a pending fade-out from hiding a node that a
       newer filter/search has just brought back. */
    var hideTimers = [];

    function clearHideTimer(node) {
      if (node._poHideTimer) {
        clearTimeout(node._poHideTimer);
        node._poHideTimer = null;
      }
    }

    function tabMatches(node) {
      if (!activeTab || activeTab === "all" || activeTab === "all-work") return true;
      var values = tokens(node.getAttribute("data-caps") || "");
      return values.indexOf(activeTab) !== -1;
    }

    function textMatches(node, needle) {
      if (!needle) return true;
      var haystack = [
        node.getAttribute("data-search"),
        node.getAttribute("data-caps"),
        nodeText(node)
      ].join(" ").toLowerCase();
      return haystack.indexOf(needle) !== -1;
    }

    function show(node) {
      clearHideTimer(node);
      setHidden(node, false);
      if (prefersReducedMotion() || !node.classList) {
        node.classList.remove("is-entering", "is-filtering-out");
        return;
      }
      node.classList.add("is-entering");
      window.requestAnimationFrame(function () { node.classList.remove("is-entering"); });
    }

    function hide(node) {
      clearHideTimer(node);
      if (prefersReducedMotion() || !node.classList) {
        setHidden(node, true);
        node.classList.remove("is-entering", "is-filtering-out");
        return;
      }
      node.classList.add("is-filtering-out");
      node._poHideTimer = setTimeout(function () {
        node._poHideTimer = null;
        setHidden(node, true);
        node.classList.remove("is-filtering-out");
      }, 180);
      hideTimers.push(node._poHideTimer);
    }

    function apply() {
      var needle = input ? String(input.value || "").replace(/\s+/g, " ").trim().toLowerCase() : "";
      var shown = 0;
      nodes.concat(cards).forEach(function (node) {
        var visible = tabMatches(node) && textMatches(node, needle);
        if (visible) { show(node); shown += 1; }
        else hide(node);
      });
      if (empty) {
        setHidden(empty, shown > 0);
        if (!shown) empty.textContent = "No work matches that filter.";
      }
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activeTab = norm(tab.getAttribute("data-cap-tab") || "all");
        if (activeTab === "all" && input) input.value = "";
        tabs.forEach(function (other) {
          var active = other === tab;
          if (other.classList) other.classList.toggle("is-active", active);
          other.setAttribute("aria-selected", active ? "true" : "false");
          other.tabIndex = active ? 0 : -1;
        });
        hideTimers.forEach(clearTimeout);
        hideTimers = [];
        apply();
      });
    });

    if (input) {
      input.addEventListener("input", apply);
      input.addEventListener("change", apply);
      input.addEventListener("search", apply);
    }
    apply();
  }

  /* ---------------------- 7. Marketing scenario ---------------------- */
  function initUseCase() {
    var section = qs(".po-usecase, #po-usecase");
    if (!section) return;
    var roles = qsa(".po-role[data-role]", section);
    var sizes = qsa(".po-size[data-size]", section);
    var tasks = qsa(".po-task[data-task]", section);
    if (!roles.length && !sizes.length && !tasks.length) return;

    var heading = qs("#po-usecase-heading", section);
    var caption = qs(".po-usecase-caption, [data-usecase-caption]", section);
    var promptPane = qs("#po-stage-prompt, .po-stage-prompt p", section);
    var view = qs(".po-view-usecase", section);

    function initial(list) {
      var found = list.filter(function (node) {
        return node.classList && node.classList.contains("is-active");
      })[0] || list[0];
      if (!found) return "";
      return found.getAttribute("data-role") || found.getAttribute("data-size") ||
        found.getAttribute("data-task") || nodeText(found);
    }

    var role = initial(roles) || "Marketing";
    var size = initial(sizes) || "Any";
    var task = initial(tasks) || "Q3 campaign rendition";

    function select(list, node, attribute) {
      var value = node.getAttribute(attribute) || nodeText(node);
      list.forEach(function (other) {
        var active = other === node;
        if (other.classList) other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", active ? "true" : "false");
      });
      return value;
    }

    function sizeClause() {
      if (norm(size) === "any") return "";
      var article = /^[aeiou]/i.test(String(size)) ? "an" : "a";
      return " at " + article + " " + titleCase(size) + " company";
    }

    function promptText() {
      var company = norm(size) === "any" ? "" :
        " at " + (/^[aeiou]/i.test(String(size)) ? "an" : "a") + " " + size + " company";
      return "Help me make the " + task + " for a " + role + " team" + company + ".";
    }

    function render() {
      if (heading) {
        heading.textContent = "I'm in " + titleCase(role) + sizeClause() +
          " and I need to make the " + titleCase(task) + ".";
      }
      if (promptPane) promptPane.textContent = promptText();
      if (caption) {
        caption.textContent = "Preview · " + titleCase(role) + " · " +
          (norm(size) === "any" ? "any company size" : titleCase(size) + " company") +
          " · " + titleCase(task) + ".";
      }
      section.setAttribute("data-role", norm(role));
      section.setAttribute("data-size", norm(size));
      section.setAttribute("data-task", norm(task));
    }

    roles.forEach(function (node) {
      node.addEventListener("click", function () { role = select(roles, node, "data-role"); render(); });
    });
    sizes.forEach(function (node) {
      node.addEventListener("click", function () { size = select(sizes, node, "data-size"); render(); });
    });
    tasks.forEach(function (node) {
      node.addEventListener("click", function () { task = select(tasks, node, "data-task"); render(); });
    });

    if (view) {
      view.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        rememberPrompt(promptText());
        if (authBridge.open) authBridge.open(view);
        else showToast("Open Keel to try this prompt: " + pendingPrompt);
      });
    }
    render();
  }

  /* ---------------------- 8. FAQ animated accordion ---------------------- */
  function initFaq() {
    var questions = qsa(".po-faq-q");
    if (!questions.length) return;

    function panelFor(question) {
      var controls = question.getAttribute("aria-controls");
      var panel = controls ? document.getElementById(controls) : null;
      if (!panel) {
        var item = question.closest ? question.closest(".po-faq-item") : null;
        panel = item ? qs(".po-faq-a", item) : null;
      }
      return panel;
    }

    function setOpen(question, open, animate) {
      var panel = panelFor(question);
      var item = question.closest ? question.closest(".po-faq-item") : null;
      var shouldAnimate = animate && !prefersReducedMotion();
      setExpanded(question, open);
      if (item && item.classList) item.classList.toggle("is-open", open);
      if (!panel) return;
      panel.setAttribute("aria-hidden", open ? "false" : "true");
      /* visibility:hidden removes links inside a collapsed panel from the
         tab order while max-height animates. */
      if (!shouldAnimate) {
        if (panel.style) {
          panel.style.visibility = open ? "visible" : "hidden";
          /* Keep the panel in the flow when JS animation is unavailable. */
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
        /* Drop links out of the tab order once the height animation ends. */
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

    /* Recalculate open panels after a resize so text never gets clipped. */
    var frame = onScrollFrame(function () {
      questions.forEach(function (question) {
        if (question.getAttribute("aria-expanded") !== "true") return;
        var panel = panelFor(question);
        if (panel && panel.style) panel.style.maxHeight = panel.scrollHeight + "px";
      });
    });
    window.addEventListener("resize", frame, { passive: true });
  }

  /* ---------------------- 9. Ask Keel (honest demo) ---------------------- */
  function answerFor(email) {
    return "Local demo only: " + email + " has been noted in this browser. " +
      "Nothing was sent, no account was created, and no email will arrive. " +
      "Open Keel to start a real conversation.";
  }

  function initAsk() {
    var form = qs("#po-ask-form, .po-ask-form");
    if (!form) return;
    var input = qs("#po-ask-input");
    form.noValidate = true;

    var result = qs("#po-ask-result");
    if (!result) {
      result = document.createElement("p");
      result.id = "po-ask-result";
      result.className = "po-ask-result";
      result.setAttribute("role", "status");
      result.setAttribute("aria-live", "polite");
      setHidden(result, true);
      if (form.parentNode) form.parentNode.appendChild(result);
    }

    form.addEventListener("submit", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      var value = input ? String(input.value || "").trim() : "";
      var nativeOk = input && typeof input.checkValidity === "function" ? input.checkValidity() : true;
      var validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
      if (!value || !nativeOk || !validEmail) {
        setHidden(result, false);
        result.textContent = "Enter a valid email address, like you@company.com. Nothing will be sent.";
        if (input) {
          if (typeof input.setAttribute === "function") input.setAttribute("aria-invalid", "true");
          if (typeof input.focus === "function") input.focus();
        }
        return;
      }
      if (input && typeof input.removeAttribute === "function") input.removeAttribute("aria-invalid");
      try { window.localStorage.setItem("keel_ask_email", value); }
      catch (storageError) { /* storage may be blocked — the message is still honest */ }
      setHidden(result, false);
      result.textContent = answerFor(value);
      if (input) input.value = "";
    });

    if (input) {
      input.addEventListener("input", function () {
        if (typeof input.removeAttribute === "function") input.removeAttribute("aria-invalid");
      });
    }
  }

  /* ------------------------- 10. Auth modal ------------------------- */
  function initAuthModal() {
    var modal = qs("#po-auth-modal");
    if (!modal) return;
    var dialog = qs(".po-modal-dialog", modal) || modal;
    var form = qs("#po-auth-form", modal);
    var input = qs("#po-auth-email", modal);
    var error = qs("#po-auth-error, .po-auth-error, [data-auth-error]", modal);
    var google = qs(".po-google-btn", modal);
    var context = qs("#po-auth-context, .po-auth-context, [data-auth-context]", modal);
    var backdrop = qs(".po-modal-backdrop", modal);
    var closeButton = qs(".po-modal-close", modal);
    var lastFocused = null;
    var redirectTimer = null;

    if (!error && input && input.parentNode) {
      error = document.createElement("p");
      error.id = "po-auth-error";
      error.className = "po-auth-error";
      error.setAttribute("role", "alert");
      setHidden(error, true);
      input.parentNode.appendChild(error);
    }

    function setError(message) {
      if (!error) return;
      error.textContent = message || "";
      setHidden(error, !message);
    }

    function setContext(prompt) {
      if (!context) return;
      var clean = String(prompt || "").trim();
      if (clean) {
        context.textContent = "Your Keel prompt: " + clean;
        setHidden(context, false);
      } else {
        context.textContent = "";
        setHidden(context, true);
      }
    }
    authBridge.setContext = setContext;

    function open(trigger) {
      if (redirectTimer) { clearTimeout(redirectTimer); redirectTimer = null; }
      lastFocused = trigger || document.activeElement;
      if (form) form.reset();
      if (input) input.removeAttribute("aria-invalid");
      setError("");
      setContext(pendingPrompt);
      setHidden(modal, false);
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("po-modal-open");
      var target = input || qs("button, a[href], input", dialog);
      if (target && typeof target.focus === "function") target.focus();
    }

    function close() {
      if (modal.hidden) return;
      if (redirectTimer) { clearTimeout(redirectTimer); redirectTimer = null; }
      setHidden(modal, true);
      modal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("po-modal-open");
      if (form) form.reset();
      if (input) input.removeAttribute("aria-invalid");
      setError("");
      if (lastFocused && typeof document.contains === "function" &&
          document.contains(lastFocused) && typeof lastFocused.focus === "function") {
        lastFocused.focus();
      }
      lastFocused = null;
    }
    authBridge.open = open;
    authBridge.close = close;

    function finishSignIn(byEmail) {
      try { window.localStorage.setItem("keel_logged_in", "1"); }
      catch (storageError) { /* optional */ }
      pendingPrompt = "";
      setContext("");
      if (byEmail) {
        showToast("Demo sign-in — no real account was created. Opening the Keel app…");
        close();
        window.location.assign("/login");
        return;
      }
      showToast("Demo sign-in — no real Google account is connected. Opening the Keel app…");
      close();
      redirectTimer = setTimeout(function () {
        redirectTimer = null;
        window.location.assign("/login");
      }, 1000);
    }

    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      var trigger = target.closest(".po-auth-open");
      if (trigger) {
        event.preventDefault();
        open(trigger);
        return;
      }
      if (target.closest(".po-modal-close") || target.closest("[data-modal-close]") ||
          target.closest(".po-modal-backdrop") || target === modal) {
        event.preventDefault();
        close();
      }
    });

    if (backdrop) backdrop.addEventListener("click", close);
    if (closeButton) closeButton.addEventListener("click", close);

    if (form) {
      form.noValidate = true;
      form.addEventListener("submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var value = input ? String(input.value || "").trim() : "";
        var nativeOk = input && typeof input.checkValidity === "function" ? input.checkValidity() : true;
        var validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
        if (!value || !nativeOk || !validEmail) {
          setError("Enter a valid email address, like you@company.com.");
          if (input) {
            input.setAttribute("aria-invalid", "true");
            if (typeof input.focus === "function") input.focus();
          }
          return;
        }
        setError("");
        if (input) input.removeAttribute("aria-invalid");
        try { window.localStorage.setItem("keel_auth_email", value); }
        catch (storageError) { /* optional */ }
        finishSignIn(true);
      });
    }

    if (input) {
      input.addEventListener("input", function () {
        setError("");
        input.removeAttribute("aria-invalid");
      });
    }
    if (google) {
      google.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        finishSignIn(false);
      });
    }

    /* Keep Tab focus inside the dialog while it is open. */
    modal.addEventListener("keydown", function (event) {
      if (!event || event.key !== "Tab") return;
      var focusable = qsa(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        dialog
      ).filter(function (node) {
        return !node.hidden && !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length);
      });
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
    });

    setHidden(modal, true);
    modal.setAttribute("aria-hidden", "true");
  }

  /* ------------------------ 11. Try-prompt link ------------------------ */
  function initTryPrompts() {
    qsa(".po-text-link[data-try-prompt]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        rememberPrompt(link.getAttribute("data-try-prompt") || "");
        if (authBridge.open) authBridge.open(link);
        else showToast("Open Keel to try this prompt: " + pendingPrompt);
      });
    });
  }

  /* ---------------------- 12. Footer language selector ---------------------- */
  var LANGUAGES = [
    { code: "en", label: "English" },
    { code: "es", label: "Español" },
    { code: "fr", label: "Français" },
    { code: "de", label: "Deutsch" },
    { code: "ja", label: "日本語" },
    { code: "ko", label: "한국어" }
  ];

  function initLangSelector() {
    var buttons = qsa(".po-lang");
    if (!buttons.length) return;
    var closers = [];

    buttons.forEach(function (button, index) {
      var menuId = "po-lang-menu-" + (index + 1);
      var label = document.createElement("span");
      label.className = "po-lang-label";
      var chevron = qs(".po-chevron", button);
      Array.prototype.slice.call(button.childNodes).forEach(function (child) {
        if (child.nodeType === 3) {
          label.appendChild(document.createTextNode(child.nodeValue || ""));
          if (button.removeChild) button.removeChild(child);
        }
      });
      if (button.insertBefore) button.insertBefore(label, chevron || null);
      else button.appendChild(label);

      var wrapper = document.createElement("div");
      wrapper.className = "po-lang-wrap";
      if (button.parentNode && button.parentNode.insertBefore) {
        button.parentNode.insertBefore(wrapper, button);
      }
      wrapper.appendChild(button);

      var menu = document.createElement("div");
      menu.className = "po-lang-menu";
      menu.id = menuId;
      menu.setAttribute("role", "menu");
      menu.setAttribute("aria-label", "Choose a language");
      wrapper.appendChild(menu);

      button.setAttribute("aria-haspopup", "menu");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", menuId);
      setHidden(menu, true);

      var open = false;
      var items = LANGUAGES.map(function (lang) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "po-lang-option";
        item.setAttribute("role", "menuitemradio");
        item.setAttribute("aria-checked", "false");
        item.textContent = lang.label;
        item.addEventListener("click", function () { choose(lang); });
        menu.appendChild(item);
        return item;
      });

      function render(state, moveFocus) {
        open = !!state;
        setHidden(menu, !open);
        setExpanded(button, open);
        if (open && moveFocus) {
          var checked = items.filter(function (item) {
            return item.getAttribute("aria-checked") === "true";
          })[0] || items[0];
          if (checked && typeof checked.focus === "function") checked.focus();
        }
      }

      function close(restoreFocus) {
        if (!open) return false;
        render(false, false);
        if (restoreFocus && typeof button.focus === "function") button.focus();
        return true;
      }
      closers.push(close);

      function findLanguage(value) {
        var clean = String(value == null ? "" : value).trim();
        if (!clean) return null;
        return LANGUAGES.filter(function (lang) {
          return lang.code === clean.toLowerCase() || lang.label.toLowerCase() === clean.toLowerCase();
        })[0] || null;
      }

      function markSelected(lang) {
        items.forEach(function (item, i) {
          item.setAttribute("aria-checked", lang && LANGUAGES[i] === lang ? "true" : "false");
        });
      }

      function choose(lang) {
        markSelected(lang);
        if (label) label.textContent = lang.label;
        close(true);
        try { window.localStorage.setItem("keel_lang", lang.code); }
        catch (storageError) { /* storage may be blocked — selection still applies */ }
        showToast("Language set to " + lang.label + " (localized copy is a demo)");
      }

      button.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        render(!open, false);
      });
      button.addEventListener("keydown", function (event) {
        if (!event) return;
        if (event.key === "Escape" || event.key === "Esc") {
          if (close(true) && typeof event.preventDefault === "function") event.preventDefault();
          return;
        }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          if (typeof event.preventDefault === "function") event.preventDefault();
          if (!open) { render(true, true); return; }
          if (!items.length) return;
          var current = items.indexOf(document.activeElement);
          var next = event.key === "ArrowDown"
            ? (current + 1 + items.length) % items.length
            : (current - 1 + items.length) % items.length;
          if (items[next] && typeof items[next].focus === "function") items[next].focus();
        }
      });
      menu.addEventListener("keydown", function (event) {
        if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
        if (close(true) && typeof event.preventDefault === "function") event.preventDefault();
      });
      document.addEventListener("click", function (event) {
        if (!open) return;
        var target = event && event.target;
        if (target && typeof target.closest === "function" &&
            (target.closest(".po-lang") || target.closest(".po-lang-menu"))) return;
        close(false);
      });

      var stored = "";
      try { stored = String(window.localStorage.getItem("keel_lang") || ""); }
      catch (storageError) { stored = ""; }
      var initial = findLanguage(stored) || LANGUAGES[0];
      markSelected(initial);
      if (label) label.textContent = initial.label;
    });

    initLangSelector._close = function (restoreFocus) {
      var closed = false;
      closers.forEach(function (close) {
        if (close(restoreFocus)) closed = true;
      });
      return closed;
    };
  }

  /* ------------------------ Global Escape ------------------------ */
  function initGlobalKeys() {
    document.addEventListener("keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      var modal = qs("#po-auth-modal");
      if (modal && !modal.hidden && typeof authBridge.close === "function") {
        event.preventDefault();
        authBridge.close();
        return;
      }
      if (typeof initLangSelector._close === "function" &&
          initLangSelector._close(true)) {
        event.preventDefault();
        return;
      }
      if (typeof initMegaNav._closeAll === "function") initMegaNav._closeAll();
      if (typeof initMobileMenu._close === "function") initMobileMenu._close();
    });
  }

  /* ----------------------------- Boot ----------------------------- */
  function init() {
    safe(initReveal);
    safe(initScrollEffects);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initWorkTabs);
    safe(initCapabilities);
    safe(initUseCase);
    safe(initFaq);
    safe(initAsk);
    safe(initAuthModal);
    safe(initTryPrompts);
    safe(initLangSelector);
    safe(initGlobalKeys);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

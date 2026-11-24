/* ===========================================================================
   Keel Platform API page — progressive enhancement, no libraries, no network.
   Every lookup is guarded: a missing element never breaks the rest of the page.
   Every initializer runs through safe(), so one broken section cannot stop the
   others. All copy in this file is local demo copy — nothing here calls out.
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

  function on(node, type, handler, options) {
    if (node && typeof node.addEventListener === "function") {
      node.addEventListener(type, handler, options);
    }
  }

  function setExpanded(node, expanded) {
    if (node && typeof node.setAttribute === "function") {
      node.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function nodeText(node) {
    return node ? String(node.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  function norm(value) {
    return String(value == null ? "" : value)
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  /* hidden plus a class plus inline display keeps visibility authoritative
     even when a stylesheet sets display on the same selector. */
  function setHidden(node, hidden) {
    if (!node) return;
    var hide = !!hidden;
    node.hidden = hide;
    if (node.classList) node.classList.toggle("is-hidden", hide);
    if (node.style) node.style.display = hide ? "none" : "";
  }

  function isVisible(node) {
    if (!node || node.hidden) return false;
    return !!(node.offsetWidth || node.offsetHeight ||
      (typeof node.getClientRects === "function" && node.getClientRects().length));
  }

  function focusNode(node) {
    if (node && typeof node.focus === "function") {
      try { node.focus(); } catch (error) { /* focus is best-effort */ }
    }
  }

  function focusable(root) {
    return qsa(
      'a[href], button:not([disabled]), input:not([disabled]), ' +
      'textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      root
    ).filter(isVisible);
  }

  function reducedMotion() {
    return !!(typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* --------------------- shared toast / modal bridge --------------------- */
  var toastTimer = null;

  function showToast(message) {
    var toast = qs("#pa-toast");
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

  var modalBridge = { open: null, openInfo: null, close: null };

  /* ------------------------ 1. Mega dropdowns ------------------------ */
  function initMegaNav() {
    var items = qsa(".pa-nav-item[data-pa-nav]");
    if (!items.length) return;

    var records = items.map(function (item) {
      return {
        item: item,
        trigger: qs(".pa-nav-trigger", item),
        mega: qs(".pa-mega", item),
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
      if (record.item && record.item.classList) {
        record.item.classList.toggle("is-open", record.open);
      }
      if (record.trigger) {
        setExpanded(record.trigger, record.open);
        if (!record.trigger.hasAttribute("aria-haspopup")) {
          record.trigger.setAttribute("aria-haspopup", "true");
        }
      }
      if (record.mega) {
        setHidden(record.mega, !record.open);
        if (record.mega.classList) record.mega.classList.toggle("is-open", record.open);
        record.mega.setAttribute("aria-hidden", record.open ? "false" : "true");
      }
    }

    function closeAll(except, restoreFocus) {
      var current = document.activeElement;
      var restore = null;
      if (restoreFocus) {
        records.forEach(function (record) {
          if (record.item && current && typeof record.item.contains === "function" &&
              record.item.contains(current)) restore = record;
        });
      }
      records.forEach(function (record) {
        if (record.item === except) return;
        clearTimers(record);
        record.pinned = false;
        if (record.open) render(record, false);
      });
      if (restore && restore.trigger) focusNode(restore.trigger);
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
      if (record.mega && !record.mega.hasAttribute("aria-hidden")) {
        record.mega.setAttribute("aria-hidden", "true");
      }
      render(record, false);

      /* Hover intent: short delay to open, longer grace period to close. */
      on(item, "mouseenter", function () {
        if (pointerDown) return;
        clearTimers(record);
        record.openTimer = setTimeout(function () {
          record.openTimer = null;
          closeAll(item);
          render(record, true);
        }, 90);
      });
      on(item, "mouseleave", function () {
        clearTimers(record);
        record.closeTimer = setTimeout(function () {
          record.closeTimer = null;
          if (record.pinned) return;
          if (typeof item.contains === "function" && item.contains(document.activeElement)) return;
          render(record, false);
        }, 180);
      });

      if (trigger) {
        /* Pointer focus must not pre-open a menu the click is about to toggle. */
        on(trigger, "pointerdown", function () {
          pointerDown = true;
          record.suppressFocus = true;
          clearTimers(record);
        });

        on(trigger, "click", function () {
          pointerDown = false;
          /* Enter/Space are handled in keydown; ignore the synthetic click. */
          if (Date.now() < record.keyHandledUntil) {
            record.keyHandledUntil = 0;
            return;
          }
          toggle(record);
        });

        on(trigger, "keydown", function (event) {
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
            var firstLink = record.mega
              ? (qs(".pa-mega-link", record.mega) || qs("a[href], button", record.mega))
              : null;
            focusNode(firstLink);
            return;
          }
          if (key === "Escape" || key === "Esc") {
            if (record.open) {
              event.preventDefault();
              closeAll(null, true);
            }
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
            focusNode(other.trigger);
          }
        });
      }

      on(item, "focusin", function () {
        if (record.suppressFocus || pointerDown) return;
        clearTimers(record);
        closeAll(item);
        render(record, true);
      });
      on(item, "focusout", function (event) {
        var next = event && event.relatedTarget;
        if (next && typeof item.contains === "function" && item.contains(next)) return;
        clearTimers(record);
        if (!record.pinned) render(record, false);
        record.suppressFocus = false;
      });

      /* Tab stays inside an open menu; Escape returns focus to the trigger. */
      on(item, "keydown", function (event) {
        if (!event || !record.open) return;
        if (event.key === "Escape" || event.key === "Esc") {
          event.preventDefault();
          closeAll(null, true);
          return;
        }
        if (event.key !== "Tab") return;
        var nodes = focusable(item);
        if (!nodes.length) return;
        var first = nodes[0];
        var last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          focusNode(last);
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          focusNode(first);
        }
      });

      /* Following a link or button inside a panel dismisses it. */
      on(item, "click", function (event) {
        var target = event && event.target;
        if (!target || typeof target.closest !== "function") return;
        if (target.closest(".pa-nav-trigger")) return;
        if (target.closest("a, button")) {
          record.pinned = false;
          closeAll();
        }
      });
    });

    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      if (!target.closest(".pa-nav-item")) closeAll();
    });
    on(window, "pointerup", function () { pointerDown = false; });
    on(window, "pointercancel", function () { pointerDown = false; });

    initMegaNav._closeAll = function () { closeAll(null, true); };
  }

  /* ------------------------ 2. Mobile menu ------------------------ */
  function initMobileMenu() {
    var toggle = qs("#pa-hamburger");
    var menu = qs("#pa-mobile-menu");
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, false);

    function render(open) {
      setHidden(menu, !open);
      if (menu.classList) menu.classList.toggle("is-open", !!open);
      setExpanded(toggle, !!open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
    function close() { render(false); }
    initMobileMenu._close = close;

    on(toggle, "click", function () { render(menu.hidden); });

    on(menu, "click", function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === "function" && target.closest("a, button")) close();
    });
    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      if (menu.hidden) return;
      if (target.closest("#pa-hamburger, #pa-mobile-menu")) return;
      close();
    });
    on(window, "resize", function () {
      if (window.innerWidth > 900 && !menu.hidden) close();
    });
  }

  /* ---------------- 3. Explore rail toggle + scroll spy ---------------- */
  function initExplore() {
    var toggle = qs("#pa-explore-toggle");
    var list = qs("#pa-explore-list");
    var rail = qs("#pa-explore");
    var links = qsa(".pa-explore-link");

    if (toggle && list) {
      if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, !list.hidden);
      on(toggle, "click", function () {
        var open = !!list.hidden;
        setHidden(list, !open);
        setExpanded(toggle, open);
        if (rail && rail.classList) rail.classList.toggle("is-collapsed", !open);
        var icon = qs(".pa-explore-icon", toggle);
        if (icon) icon.textContent = open ? "—" : "+";
      });
    }

    if (!links.length) return;
    var sections = links.map(function (link) {
      var href = String(link.getAttribute("href") || "");
      return { link: link, target: href.charAt(0) === "#" ? qs(href) : null };
    }).filter(function (record) { return !!record.target; });
    if (!sections.length) return;

    function activate(link) {
      links.forEach(function (other) {
        if (other.classList) other.classList.toggle("is-active", other === link);
      });
    }

    if (typeof window.IntersectionObserver === "function") {
      var observer = new window.IntersectionObserver(function (entries) {
        var visible = entries.filter(function (entry) { return entry.isIntersecting; });
        if (!visible.length) return;
        visible.sort(function (a, b) {
          return a.boundingClientRect.top - b.boundingClientRect.top;
        });
        for (var i = 0; i < sections.length; i += 1) {
          if (sections[i].target === visible[0].target) {
            activate(sections[i].link);
            break;
          }
        }
      }, { rootMargin: "-10% 0px -65% 0px", threshold: 0 });
      sections.forEach(function (record) { observer.observe(record.target); });
    } else {
      /* Older browsers: a plain, throttled scroll handler. */
      var frame = null;
      function updateSpy() {
        frame = null;
        var best = null;
        sections.forEach(function (record) {
          var rect = record.target.getBoundingClientRect();
          if (rect.top <= 160 && (!best || rect.top > best.top)) {
            best = { link: record.link, top: rect.top };
          }
        });
        if (best) activate(best.link);
      }
      function requestSpy() {
        if (frame !== null) return;
        if (typeof window.requestAnimationFrame === "function") {
          frame = window.requestAnimationFrame(updateSpy);
        } else { updateSpy(); }
      }
      on(window, "scroll", requestSpy, { passive: true });
      on(window, "resize", requestSpy);
      updateSpy();
    }
  }

  /* --------------------- 4. Reading progress bar --------------------- */
  function initProgress() {
    var fill = qs("#pa-progress-fill");
    var bar = qs("#pa-progress");
    if (!fill || !fill.style) return;
    var frame = null;

    function update() {
      frame = null;
      var doc = document.documentElement || document.body || {};
      var top = window.pageYOffset || doc.scrollTop || 0;
      var height = Math.max(1, (doc.scrollHeight || 0) - (window.innerHeight || 0));
      var percent = Math.min(100, Math.max(0, (top / height) * 100));
      fill.style.width = percent.toFixed(2) + "%";
      if (bar && bar.classList) bar.classList.toggle("is-scrolled", top > 4);
    }
    function request() {
      if (frame !== null) return;
      if (typeof window.requestAnimationFrame === "function") {
        frame = window.requestAnimationFrame(update);
      } else { update(); }
    }
    on(window, "scroll", request, { passive: true });
    on(window, "resize", request);
    update();
  }

  /* ---------------- 5. Model detail buttons ---------------- */
  var MODELS = {
    "fable-5": {
      name: "Fable 5",
      tagline: "Next generation intelligence for long-running agents.",
      uses: "Multi-day autonomous projects, expert-level work for frontier research.",
      pricing: "Input $8 / MTok · Output $40 / MTok · Cache read $0.20 / MTok · Cache write $10 / MTok."
    },
    "opus-4-6": {
      name: "Opus 4.6",
      tagline: "Powerful, thoughtful intelligence for complex work.",
      uses: "Advanced coding and reasoning, long-running agents and enterprise workflows.",
      pricing: "Input $5 / MTok · Output $25 / MTok · Cache read $0.50 / MTok · Cache write $6.25 / MTok."
    },
    "sonnet-4-5": {
      name: "Sonnet 4.5",
      tagline: "The practical blend of speed and capability.",
      uses: "Everyday coding and analysis, production agents at scale.",
      pricing: "Input $3 / MTok · Output $15 / MTok · Cache read $0.30 / MTok · Cache write $3.75 / MTok."
    },
    "haiku-4-5": {
      name: "Haiku 4.5",
      tagline: "The fastest, most compact model for near-instant tasks.",
      uses: "Low-latency assistants, high-volume classification and extraction.",
      pricing: "≤100K tokens: input $1 / MTok · output $5 / MTok · cache read $0.10 / MTok · cache write $1.25 / MTok. >100K tokens: cache read $0.15 / MTok · cache write $1.50 / MTok (input and output rates remain $1 and $5 / MTok). Two-tier caching: higher rates above 100K tokens."
    }
  };
  MODELS.fable = MODELS["fable-5"];
  MODELS.opus = MODELS["opus-4-6"];
  MODELS.sonnet = MODELS["sonnet-4-5"];
  MODELS.haiku = MODELS["haiku-4-5"];

  function initModelDetails() {
    var buttons = qsa("[data-pa-model-detail]");
    if (!buttons.length) return;
    buttons.forEach(function (button) {
      on(button, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var key = norm(button.getAttribute("data-pa-model-detail"));
        var card = typeof button.closest === "function" ? button.closest("[data-pa-model]") : null;
        var cardKey = card ? norm(card.getAttribute("data-pa-model")) : "";
        var data = MODELS[key] || MODELS[cardKey] || null;
        if (!data) {
          showToast(nodeText(button) + " — see the Models section for KEEL pricing.");
          return;
        }
        var blocks = [
          { label: "Tagline", text: data.tagline },
          { label: "Uses", text: data.uses },
          { label: "Pricing", text: data.pricing }
        ];
        if (modalBridge.openInfo) {
          modalBridge.openInfo({ title: data.name, subtitle: "KEEL model", blocks: blocks }, button);
        } else {
          showToast(data.name + " · " + data.tagline + " · " + data.pricing);
        }
      });
    });
  }

  /* ------------- 6. Hub nodes and Agent SDK flow nodes ------------- */
  var HUB_INFO = {
    "keel-models": "KEEL models — frontier models you can route between, from fast Haiku 4.5 to long-running Fable 5.",
    "keel": "KEEL models — frontier models you can route between, from fast Haiku 4.5 to long-running Fable 5.",
    "code-execution": "Code execution — let agents run sandboxed code to compute results, transform data and verify their own work.",
    "structured-outputs": "Structured outputs — get responses that conform to a schema so they drop straight into your application.",
    "tool-use": "Tool use — give models real functions to call, with clear arguments and validated results.",
    "computer-use": "Computer use — let agents navigate a browser and interact with software the way a person does.",
    "citations": "Citations — ground answers in sources and show exactly where each claim came from.",
    "files": "Files — upload documents and let agents search, read and reason over them in context.",
    "context-window": "Context window — keep long documents and conversations in a single coherent request.",
    "compaction": "Compaction — summarize older context automatically so long-running agents stay fast and focused.",
    "web-search-and-fetch": "Web search and fetch — pull in current information and cite it inside the answer."
  };
  var FLOW_INFO = {
    mcp: "MCP tools — connect agents to external tools and data sources through the Model Context Protocol, with a single reusable integration.",
    memory: "Memory — persist context across sessions so agents remember decisions, preferences and prior work.",
    sandbox: "Sandbox — run code and tool calls in an isolated environment with strict limits and no access to your host.",
    skills: "Skills — package instructions and capabilities into reusable folders your agents load only when they need them."
  };
  var HUB_DEFAULT = "Select a capability to see how KEEL uses it.";
  var FLOW_DEFAULT = "Select a building block to learn more.";

  function hubCopy(node) {
    var attr = String(node.getAttribute("data-pa-hub-detail") || "");
    var label = nodeText(node);
    return HUB_INFO[norm(attr)] || HUB_INFO[norm(label)] ||
      (attr.length > 24 ? attr : label + " — part of the KEEL platform's AI-first design.");
  }

  function flowCopy(node) {
    var attr = norm(node.getAttribute("data-pa-flow"));
    return FLOW_INFO[attr] || nodeText(node) + " — a building block of the KEEL Agent SDK.";
  }

  function initNodes() {
    var hubNodes = qsa(".pa-hub-node[data-pa-hub-detail]");
    var hubDetail = qs("#pa-hub-detail");
    var flowNodes = qsa(".pa-flow-node[data-pa-flow]");
    var flowDetail = qs("#pa-flow-detail");

    function select(nodes, node, detail, text) {
      nodes.forEach(function (other) {
        if (other.classList) other.classList.toggle("is-active", other === node);
        if (other.setAttribute) other.setAttribute("aria-pressed", other === node ? "true" : "false");
      });
      if (detail) detail.textContent = text;
    }

    hubNodes.forEach(function (node) {
      on(node, "click", function () { select(hubNodes, node, hubDetail, hubCopy(node)); });
    });

    flowNodes.forEach(function (node) {
      /* Flow tiles are divs in the markup: make them keyboard reachable. */
      if (!node.hasAttribute("tabindex")) node.setAttribute("tabindex", "0");
      if (!node.hasAttribute("role")) node.setAttribute("role", "button");
      var handled = 0;
      on(node, "click", function () { select(flowNodes, node, flowDetail, flowCopy(node)); });
      on(node, "keydown", function (event) {
        if (!event || (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar")) return;
        event.preventDefault();
        if (Date.now() < handled) return;
        handled = Date.now() + 400;
        select(flowNodes, node, flowDetail, flowCopy(node));
      });
    });

    /* Leave the HTML's sensible default copy in place until a selection. */
    if (hubDetail && !nodeText(hubDetail)) hubDetail.textContent = HUB_DEFAULT;
    if (flowDetail && !nodeText(flowDetail)) flowDetail.textContent = FLOW_DEFAULT;
  }

  /* ------------------------- 7. Cost tabs ------------------------- */
  function initCostTabs() {
    var tabs = qsa(".pa-cost-tab[data-pa-cost]");
    if (!tabs.length) return;
    var panels = qsa(".pa-cost-panel[data-pa-cost-panel]");
    var captions = qsa(".pa-cost-caption, [data-pa-cost-caption]");

    function select(tab, moveFocus) {
      var key = norm(tab.getAttribute("data-pa-cost"));
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
        other.tabIndex = active ? 0 : -1;
      });
      panels.forEach(function (panel) {
        var active = norm(panel.getAttribute("data-pa-cost-panel")) === key;
        setHidden(panel, !active);
        if (panel.classList) {
          panel.classList.toggle("is-active", active);
          panel.classList.toggle("is-hidden", !active);
        }
      });
      var description = qs("span", tab);
      var caption = nodeText(description) || nodeText(tab);
      captions.forEach(function (node) { node.textContent = caption; });
      if (moveFocus) focusNode(tab);
    }

    tabs.forEach(function (tab, index) {
      on(tab, "click", function () { select(tab, false); });
      on(tab, "keydown", function (event) {
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

  /* ------------- 8. Console tabs, staged run and copy ------------- */
  var CONSOLE_COPY = {
    build: "Prototype prompts, upload skills and files, configure your agents.",
    deploy: "Deploy agents to production with versioned releases and safe rollouts.",
    monitor: "Trace every step, inspect tool calls and catch failures before users do.",
    manage: "Manage permissions, usage and budgets across your whole organization."
  };

  function initConsoleTabs() {
    var tabs = qsa(".pa-console-tab[data-pa-console]");
    var detail = qs("#pa-console-detail");
    if (!tabs.length) return;

    function select(tab, moveFocus) {
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
        other.tabIndex = active ? 0 : -1;
      });
      var key = norm(tab.getAttribute("data-pa-console"));
      if (detail && CONSOLE_COPY[key]) detail.textContent = CONSOLE_COPY[key];
      if (moveFocus) focusNode(tab);
    }

    tabs.forEach(function (tab, index) {
      on(tab, "click", function () { select(tab, false); });
      on(tab, "keydown", function (event) {
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

  var RUN_LINES = [
    "→  Sending request to Fable 5…",
    "▸  Reading 2 support tickets from Files…",
    "▸  Classifying ticket #1042 — billing · resolved",
    "▸  Classifying ticket #1043 — access · escalated",
    "✓  Trace complete · 2 classified · 1 escalated · 412 ms"
  ];

  function initRunRequest() {
    var button = qs("#pa-run");
    var output = qs("#pa-console-output");
    if (!button || !output) return;
    var code = qs("code", output) || output;
    var buttonHTML = button.innerHTML;
    var running = false;
    var timers = [];

    function writeLines(lines) { code.textContent = lines.join("\n"); }
    function finish() {
      running = false;
      timers.forEach(function (timer) { clearTimeout(timer); });
      timers = [];
      button.disabled = false;
      button.innerHTML = buttonHTML;
      showToast("Request complete");
    }

    on(button, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      if (running) return;
      running = true;
      button.disabled = true;
      button.textContent = "Running…";
      writeLines([]);

      if (reducedMotion()) {
        writeLines(RUN_LINES);
        timers.push(setTimeout(finish, 400));
        return;
      }

      RUN_LINES.forEach(function (line, index) {
        timers.push(setTimeout(function () {
          writeLines(RUN_LINES.slice(0, index + 1));
        }, 180 + index * 260));
      });
      /* ~1.6s after the last line: enable the button and toast. */
      timers.push(setTimeout(finish, 1600));
    });
  }

  function fallbackCopy(text) {
    var copied = false;
    try {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.top = "-9999px";
      document.body.appendChild(area);
      area.select();
      if (typeof document.execCommand === "function") copied = document.execCommand("copy");
      document.body.removeChild(area);
    } catch (error) { copied = false; }
    showToast(copied ? "Copied to clipboard" : "Copy unavailable — select the text and copy manually");
  }

  function copyText(text) {
    if (typeof navigator !== "undefined" && navigator.clipboard &&
        typeof navigator.clipboard.writeText === "function") {
      try {
        var result = navigator.clipboard.writeText(text);
        if (result && typeof result.then === "function") {
          result.then(function () { showToast("Copied to clipboard"); }, function () { fallbackCopy(text); });
          return;
        }
        showToast("Copied to clipboard");
        return;
      } catch (error) { /* fall through to the legacy path */ }
    }
    fallbackCopy(text);
  }

  function initCopyButtons() {
    /* Covers .pa-copy in code/terminal heads and the CTA install command. */
    qsa("[data-pa-copy]").forEach(function (button) {
      on(button, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var id = String(button.getAttribute("data-pa-copy") || "");
        var target = id ? document.getElementById(id) : null;
        if (!target) return;
        var text = String(target.textContent || "");
        if (!text) return;
        copyText(text);
      });
    });
  }

  /* --------------------- 9. Testimonial carousel --------------------- */
  function initQuotes() {
    var slides = qsa(".pa-quote-slide");
    if (!slides.length) return;
    var container = qs("#pa-quotes") || slides[0].parentNode;
    var prev = qs("#pa-quote-prev");
    var next = qs("#pa-quote-next");
    var count = qs("#pa-quote-count");
    var dotsWrap = qs("#pa-quote-dots");
    var index = 0;
    var dots = [];
    var timer = null;
    var paused = false;

    slides.forEach(function (slide, i) {
      if (slide.classList && slide.classList.contains("is-active")) index = i;
    });

    if (dotsWrap) {
      dots = qsa("button", dotsWrap);
      if (!dots.length && slides.length > 1) {
        dots = slides.map(function (slide, i) {
          var dot = document.createElement("button");
          dot.type = "button";
          dot.className = "pa-quote-dot";
          dot.setAttribute("aria-label", "Show testimonial " + (i + 1));
          dot.textContent = String(i + 1);
          on(dot, "click", function () { go(i); resetAutoplay(); });
          dotsWrap.appendChild(dot);
          return dot;
        });
      }
    }

    function render() {
      slides.forEach(function (slide, i) {
        var active = i === index;
        if (slide.classList) slide.classList.toggle("is-active", active);
        setHidden(slide, !active);
        slide.setAttribute("aria-hidden", active ? "false" : "true");
      });
      if (count) count.textContent = (index + 1) + " / " + slides.length;
      dots.forEach(function (dot, i) {
        if (dot.classList) dot.classList.toggle("is-active", i === index);
        dot.setAttribute("aria-current", i === index ? "true" : "false");
      });
    }

    function go(to) {
      index = (to + slides.length) % slides.length;
      render();
    }
    function stopAutoplay() {
      if (timer) { clearInterval(timer); timer = null; }
    }
    function startAutoplay() {
      if (timer || reducedMotion() || slides.length < 2) return;
      timer = setInterval(function () { if (!paused) go(index + 1); }, 6000);
    }
    function resetAutoplay() { stopAutoplay(); startAutoplay(); }

    on(prev, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      go(index - 1);
      resetAutoplay();
    });
    on(next, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      go(index + 1);
      resetAutoplay();
    });

    if (container) {
      on(container, "mouseenter", function () { paused = true; });
      on(container, "mouseleave", function () { paused = false; });
      on(container, "focusin", function () { paused = true; });
      on(container, "focusout", function () { paused = false; });
      on(container, "keydown", function (event) {
        if (!event) return;
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          go(index - 1);
          resetAutoplay();
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          go(index + 1);
          resetAutoplay();
        }
      });
    } else {
      [prev, next].forEach(function (button, direction) {
        on(button, "keydown", function (event) {
          if (!event || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
          event.preventDefault();
          go(index + (direction === 0 ? -1 : 1));
          resetAutoplay();
        });
      });
    }

    render();
    startAutoplay();
  }

  /* --------------------- 11. Footer search --------------------- */
  function initFooterSearch() {
    var form = qs("#pa-footer-search");
    var input = qs("#pa-footer-q");
    if (!form || !input) return;
    var results = qs("#pa-search-results");
    if (!results) {
      results = document.createElement("div");
      results.id = "pa-search-results";
      results.className = "pa-search-results";
      setHidden(results, true);
      if (form.parentNode) form.parentNode.appendChild(results);
    }

    var entries = [];
    qsa(".pa-footer-col").forEach(function (column) {
      var heading = qs("h1, h2, h3, h4, .pa-footer-heading", column);
      if (heading) entries.push({ label: nodeText(heading), href: "", target: heading });
      qsa("a", column).forEach(function (link) {
        entries.push({
          label: nodeText(link),
          href: String(link.getAttribute("href") || ""),
          target: link
        });
      });
    });

    function clear() {
      input.value = "";
      while (results.firstChild) results.removeChild(results.firstChild);
      setHidden(results, true);
    }
    initFooterSearch._clear = clear;

    function apply() {
      while (results.firstChild) results.removeChild(results.firstChild);
      var query = String(input.value || "").replace(/\s+/g, " ").trim();
      var needle = query.toLowerCase();
      if (!needle) { setHidden(results, true); return; }
      var matches = entries.filter(function (entry) {
        return entry.label.toLowerCase().indexOf(needle) !== -1;
      });
      setHidden(results, false);
      if (!matches.length) {
        var empty = document.createElement("p");
        empty.className = "pa-search-empty";
        empty.textContent = 'No results for “' + query + '”. Try “pricing”, “apps” or “privacy”.';
        results.appendChild(empty);
        return;
      }
      matches.forEach(function (match) {
        var link = document.createElement("a");
        link.className = "pa-search-result";
        link.href = match.href || "#";
        link.textContent = match.label;
        on(link, "click", function (event) {
          var anchor = match.href.charAt(0) === "#" ? qs(match.href) : null;
          if (anchor) {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            if (typeof anchor.scrollIntoView === "function") anchor.scrollIntoView({ behavior: "smooth" });
          } else if (!match.href) {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            if (match.target && typeof match.target.scrollIntoView === "function") {
              match.target.scrollIntoView({ behavior: "smooth" });
            }
          }
          clear();
        });
        results.appendChild(link);
      });
    }

    on(form, "submit", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      apply();
    });
    on(input, "input", apply);
    on(input, "change", apply);
    on(input, "search", apply);
    on(input, "keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      event.preventDefault();
      clear();
    });
  }

  /* ------------------------- 12. Modal ------------------------- */
  var INFO_COPY = {
    docs: {
      title: "KEEL documentation",
      subtitle: "Guides and reference for the KEEL Platform",
      blocks: [
        { label: "Get started", text: "Install the SDK and make your first API call in a few minutes." },
        { label: "Explore", text: "Read the API reference, prompt caching guide and Agent SDK examples." }
      ]
    },
    model: {
      title: "KEEL models",
      subtitle: "Choose the right model for the job",
      blocks: [
        { label: "Fable 5", text: "Long-running agents and frontier research." },
        { label: "Opus 4.6", text: "Complex coding, reasoning and enterprise workflows." },
        { label: "Sonnet 4.5", text: "Production agents that balance speed and quality." },
        { label: "Haiku 4.5", text: "Fast, compact and economical for high-volume tasks." }
      ]
    },
    info: {
      title: "KEEL Platform",
      subtitle: "Frontier models and infrastructure that work together",
      blocks: [
        { label: "Models", text: "Four model families, from near-instant Haiku to long-running Fable." },
        { label: "Platform", text: "Prompt caching, batch processing, the Agent SDK and the KEEL Console." }
      ]
    }
  };

  function initModal() {
    var modal = qs("#pa-modal");
    if (!modal) return;
    var card = qs(".pa-modal-card", modal) || modal;
    var title = qs("#pa-modal-title", modal);
    var desc = qs("#pa-modal-desc", modal);
    var authForm = qs("#pa-auth-form", modal);
    var contactForm = qs("#pa-contact-form", modal);
    var emailInput = qs("#pa-email", modal);
    var google = qs("#pa-google", modal);
    var lastFocused = null;

    var info = document.createElement("div");
    info.className = "pa-modal-info";
    info.setAttribute("role", "status");
    info.tabIndex = -1;
    setHidden(info, true);
    card.appendChild(info);

    var note = document.createElement("p");
    note.className = "pa-modal-note";
    note.textContent = "Demo sign-in — no real account is created";
    setHidden(note, true);
    if (google && google.parentNode) google.parentNode.insertBefore(note, google.nextSibling);
    else card.appendChild(note);

    var success = document.createElement("div");
    success.className = "pa-modal-success";
    success.tabIndex = -1;
    setHidden(success, true);
    card.appendChild(success);

    function resetPanels() {
      setHidden(authForm, true);
      setHidden(contactForm, true);
      setHidden(info, true);
      setHidden(success, true);
      setHidden(note, true);
    }

    function setHeading(heading, copy) {
      if (title) title.textContent = heading;
      if (desc) desc.textContent = copy;
    }

    function fillInfo(spec) {
      var data = spec || {};
      while (info.firstChild) info.removeChild(info.firstChild);
      var blocks = data.blocks || [];
      blocks.forEach(function (block) {
        if (!block) return;
        var paragraph = document.createElement("p");
        paragraph.className = "pa-modal-info-row";
        if (block.label) {
          var strong = document.createElement("strong");
          strong.textContent = block.label + ": ";
          paragraph.appendChild(strong);
        }
        paragraph.appendChild(document.createTextNode(block.text || ""));
        info.appendChild(paragraph);
      });
      setHeading(data.title || "KEEL Platform", data.subtitle || "More information");
      setHidden(info, false);
    }

    function open(trigger, mode) {
      lastFocused = trigger || document.activeElement;
      var kind = norm(mode || "signup");
      resetPanels();
      setHidden(modal, false);
      if (modal.classList) modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      if (document.body && document.body.classList) document.body.classList.add("pa-modal-open");

      if (kind === "contact") {
        setHeading("Contact sales", "Tell us what you're building and we'll get back to you.");
        setHidden(contactForm, false);
        focusNode(qs("#pa-name", modal) || qs("input", contactForm));
        return;
      }
      if (kind === "docs" || kind === "model" || kind === "info" || kind === "model-detail") {
        var data = INFO_COPY[kind] || INFO_COPY.info;
        fillInfo({ title: data.title, subtitle: data.subtitle, blocks: data.blocks });
        focusNode(info);
        return;
      }
      setHeading("Sign in to KEEL", "Demo sign-in — no real account required.");
      if (emailInput) emailInput.removeAttribute("aria-invalid");
      setHidden(authForm, false);
      focusNode(emailInput || qs("button", authForm));
    }

    function close() {
      if (modal.hidden) return;
      setHidden(modal, true);
      if (modal.classList) modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      if (document.body && document.body.classList) document.body.classList.remove("pa-modal-open");
      resetPanels();
      if (lastFocused && typeof document.contains === "function" &&
          document.contains(lastFocused)) focusNode(lastFocused);
      lastFocused = null;
    }

    function showSuccess(heading, copy) {
      resetPanels();
      while (success.firstChild) success.removeChild(success.firstChild);
      var h = document.createElement("h3");
      h.textContent = heading;
      var p = document.createElement("p");
      p.textContent = copy;
      var link = document.createElement("a");
      link.className = "pa-btn pa-btn-dark";
      link.href = "/app";
      link.textContent = "Open the KEEL app ↗";
      success.appendChild(h);
      success.appendChild(p);
      success.appendChild(link);
      setHeading("You're all set", "Continue to the KEEL app when you're ready.");
      setHidden(success, false);
      focusNode(link);
    }

    modalBridge.open = open;
    modalBridge.close = close;
    modalBridge.openInfo = function (spec, trigger) {
      open(trigger || null, "info");
      fillInfo(spec);
      focusNode(info);
    };

    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      var trigger = target.closest("[data-pa-modal]");
      if (trigger) {
        event.preventDefault();
        open(trigger, trigger.getAttribute("data-pa-modal"));
        return;
      }
      if (target.closest("[data-pa-close]") || target === modal) {
        event.preventDefault();
        close();
      }
    });

    on(modal, "keydown", function (event) {
      if (!event) return;
      if (event.key === "Escape" || event.key === "Esc") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      var nodes = focusable(card);
      if (!nodes.length) return;
      var active = document.activeElement;
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      /* Info/success panels are focused on a tabindex="-1" node, which is not
         part of `nodes`. Wrap from there too so Tab can never leave the dialog. */
      if (!active || nodes.indexOf(active) === -1 ||
          (typeof card.contains === "function" && !card.contains(active))) {
        event.preventDefault();
        focusNode(event.shiftKey ? last : first);
        return;
      }
      if (event.shiftKey && active === first) {
        event.preventDefault();
        focusNode(last);
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        focusNode(first);
      }
    });

    if (authForm) {
      authForm.noValidate = true;
      on(authForm, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var value = emailInput ? String(emailInput.value || "").trim() : "";
        var nativeOk = emailInput && typeof emailInput.checkValidity === "function"
          ? emailInput.checkValidity() : true;
        var valid = !!value && nativeOk && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
        if (!valid) {
          showToast("Please enter a valid email address to continue.");
          if (emailInput) {
            emailInput.setAttribute("aria-invalid", "true");
            focusNode(emailInput);
          }
          return;
        }
        if (emailInput) emailInput.removeAttribute("aria-invalid");
        try { window.localStorage.setItem("keel_logged_in", "1"); }
        catch (storageError) { /* storage may be blocked — the demo still continues */ }
        showSuccess("You're signed in", "You're logged in to the KEEL demo. No real account was created.");
      });
    }

    if (contactForm) {
      contactForm.noValidate = true;
      on(contactForm, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var fields = qsa("input, textarea", contactForm);
        var invalid = fields.filter(function (field) {
          return typeof field.checkValidity === "function" && !field.checkValidity();
        })[0];
        if (invalid) {
          showToast("Please complete the contact form before sending.");
          focusNode(invalid);
          return;
        }
        contactForm.reset();
        showToast("Thanks — we'll be in touch");
        close();
      });
    }

    on(google, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      setHidden(note, false);
      try { window.localStorage.setItem("keel_logged_in", "1"); }
      catch (storageError) { /* storage may be blocked — the demo still continues */ }
      showToast("Demo sign-in — no real account is created");
      showSuccess("Demo sign-in complete", "Demo sign-in — no real account is created. Your session is ready when you are.");
    });

    setHidden(modal, true);
    modal.setAttribute("aria-hidden", "true");
  }

  /* ----- 13. Newsletter / placeholder CTAs always do something ----- */
  function initFallbackCTAs() {
    qsa('a[href="#"]').forEach(function (link) {
      if (link.hasAttribute("data-pa-modal") || link.hasAttribute("data-pa-copy") ||
          link.hasAttribute("data-pa-close")) return;
      on(link, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var text = nodeText(link).toLowerCase();
        var mode = /contact|sales|talk|enterprise/.test(text) ? "contact" : "signup";
        if (modalBridge.open) modalBridge.open(link, mode);
        else showToast(mode === "contact" ? "Contact sales — we'll be in touch." : "Sign in to KEEL to continue.");
      });
    });
    qsa("form[data-pa-newsletter], .pa-newsletter-form").forEach(function (form) {
      on(form, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        showToast("Thanks for subscribing — this is a demo.");
        if (typeof form.reset === "function") form.reset();
      });
    });
  }

  /* ------------------------ Global Escape ------------------------ */
  function initGlobalKeys() {
    on(document, "keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      var modal = qs("#pa-modal");
      if (modal && !modal.hidden && typeof modalBridge.close === "function") {
        event.preventDefault();
        modalBridge.close();
        return;
      }
      if (typeof initMobileMenu._close === "function") initMobileMenu._close();
      if (typeof initMegaNav._closeAll === "function") initMegaNav._closeAll();
      if (typeof initFooterSearch._clear === "function") initFooterSearch._clear();
    });
  }

  /* ----------------------------- Boot ----------------------------- */
  function init() {
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initExplore);
    safe(initProgress);
    safe(initModelDetails);
    safe(initNodes);
    safe(initCostTabs);
    safe(initConsoleTabs);
    safe(initRunRequest);
    safe(initCopyButtons);
    safe(initQuotes);
    safe(initFooterSearch);
    safe(initModal);
    safe(initFallbackCTAs);
    safe(initGlobalKeys);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

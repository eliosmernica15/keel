/* ===========================================================================
   Keel product overview — progressive enhancement, no libraries, no network.
   Every lookup is guarded: a missing element never breaks the rest of the page.
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

  /* hidden plus a class plus an inline display keeps filtering authoritative
     even when a stylesheet sets display on the same selector. */
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
    ai: "AI", api: "API", crm: "CRM", hr: "HR", jd: "JD", kpi: "KPI",
    okr: "OKR", qbr: "QBR", roi: "ROI", sla: "SLA", esg: "ESG",
    h1: "H1", h2: "H2", h3: "H3", q1: "Q1", q2: "Q2", q3: "Q3", q4: "Q4"
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

  /* --------------------- shared toast / auth bridge --------------------- */
  var toastTimer = null;

  function showToast(message) {
    var toast = qs("#po-toast");
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

  var authBridge = { open: null, close: null, setContext: null };
  var pendingPrompt = "";

  function rememberPrompt(prompt) {
    pendingPrompt = String(prompt == null ? "" : prompt).replace(/\s+/g, " ").trim();
    var askInput = qs("#po-ask-input");
    if (askInput) askInput.value = pendingPrompt;
    if (authBridge.setContext) authBridge.setContext(pendingPrompt);
  }

  /* --------------------- 1. Mega dropdown menus --------------------- */
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
        record.mega.setAttribute("aria-hidden", record.open ? "false" : "true");
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
      if (record.mega && !record.mega.hasAttribute("aria-hidden")) {
        record.mega.setAttribute("aria-hidden", "true");
      }
      render(record, false);

      /* Hover intent: a short delay to open, a longer grace period to close. */
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
        /* Pointer focus must not pre-open a menu the click is about to toggle. */
        trigger.addEventListener("pointerdown", function () {
          pointerDown = true;
          record.suppressFocus = true;
          clearTimers(record);
        });

        trigger.addEventListener("click", function () {
          pointerDown = false;
          /* Enter/Space are handled in keydown; ignore the synthetic click. */
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

      /* Following a link or button inside a panel dismisses it. */
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

  /* ------------------------ 2. Mobile menu ------------------------ */
  function initMobileMenu() {
    var toggle = qs(".po-hamburger, #po-hamburger");
    var menu = qs("#po-mobile-menu");
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

    toggle.addEventListener("click", function () { render(menu.hidden); });

    menu.addEventListener("click", function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === "function" && target.closest("a, button")) close();
    });
    document.addEventListener("click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      if (menu.hidden) return;
      if (target.closest(".po-hamburger, #po-mobile-menu, #po-mobile-nav")) return;
      close();
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900 && !menu.hidden) close();
    });
  }

  /* -------------------- 3. Persona showcase tabs -------------------- */
  var PERSONAS = {
    everyone: {
      time: "8:00 AM · Everyone",
      title: "Keep up with meetings all day",
      desc: "Keel joins your calls, pulls out the decisions and next steps, and turns them into a recap you can actually use.",
      prompt: "After each of my meetings, send me a short recap with decisions, owners and due dates.",
      steps: ["Listen to the call", "Capture decisions", "Share the recap"],
      model: "Opus High"
    },
    marketing: {
      time: "9:15 AM · Marketing",
      title: "Turn a brief into a launch",
      desc: "Give Keel the campaign brief and past results. It drafts channel copy, builds the readout and flags what is working.",
      prompt: "Draft a launch email and a campaign readout from this brief, then list the numbers I still need.",
      steps: ["Read the brief", "Draft channel assets", "Build the readout"],
      model: "Opus High"
    },
    sales: {
      time: "7:45 AM · Sales",
      title: "Walk into every call prepared",
      desc: "Keel reads the CRM notes, the last email thread and the account plan, then hands you a one-page brief before the call.",
      prompt: "Build a call prep brief for tomorrow's meetings using the CRM notes and recent email threads.",
      steps: ["Pull account context", "Spot open questions", "Write the brief"],
      model: "Sonnet"
    },
    finance: {
      time: "6:30 AM · Finance",
      title: "Close the books with fewer tabs",
      desc: "Keel checks the numbers, writes the variance commentary and assembles a month-end package your team can review.",
      prompt: "Compare this month's spend to the budget and draft the variance commentary for the close deck.",
      steps: ["Gather the data", "Check the variance", "Draft commentary"],
      model: "Opus High"
    },
    "human-resources": {
      time: "10:00 AM · People",
      title: "Make every policy easy to understand",
      desc: "Keel checks job descriptions against your rubric, summarizes policy changes and drafts clear answers for employees.",
      prompt: "Review this job description for inclusive language and draft a concise version for our careers page.",
      steps: ["Read the document", "Check the language", "Draft the update"],
      model: "Sonnet"
    },
    legal: {
      time: "11:20 AM · Legal",
      title: "Get to the clause that matters",
      desc: "Keel reads the contract, flags non-standard terms and drafts a redline with plain-language reasoning for each change.",
      prompt: "Summarize the risks in this contract and propose a redline for the liability and termination clauses.",
      steps: ["Read the contract", "Flag the risk", "Draft the redline"],
      model: "Opus High"
    },
    product: {
      time: "8:50 AM · Product",
      title: "Ship with the context intact",
      desc: "Keel turns research notes and feedback into a spec, keeps decisions in one place and drafts the update for stakeholders.",
      prompt: "Turn these customer interviews into a one-page PRD with open questions and a success metric.",
      steps: ["Cluster the feedback", "Draft the spec", "Share the update"],
      model: "Opus High"
    }
  };
  PERSONAS.hr = PERSONAS["human-resources"];

  function initPersonas() {
    var tabs = qsa(".po-persona-tab[data-persona]");
    if (!tabs.length) return;
    var title = qs(".po-showcase-title");
    var desc = qs(".po-showcase-desc");
    var time = qs(".po-showcase-time");
    var prompt = qs(".po-chat-prompt");
    var model = qs(".po-chat-model");
    var visual = qs(".po-showcase-visual");
    var steps = qsa(".po-chat-step", visual || document);

    function select(tab, moveFocus) {
      var key = norm(tab.getAttribute("data-persona") || "");
      var data = PERSONAS[key];
      tabs.forEach(function (other) {
        var active = other === tab;
        if (other.classList) other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
        other.tabIndex = active ? 0 : -1;
        var controls = other.getAttribute("aria-controls");
        var panel = controls ? document.getElementById(controls) : null;
        if (panel) setHidden(panel, !active);
      });
      if (data) {
        if (title) title.textContent = data.title;
        if (desc) desc.textContent = data.desc;
        if (time) time.textContent = data.time;
        if (prompt) prompt.textContent = data.prompt;
        if (model) model.textContent = data.model;
        steps.forEach(function (step, index) {
          if (data.steps && data.steps[index]) step.textContent = data.steps[index];
        });
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
      return tab.classList && tab.classList.contains("is-active");
    })[0] || tabs[0];
    if (initial) select(initial, false);
  }

  /* ------------- 4. Capability search and category tabs ------------- */
  function initCapabilities() {
    var input = qs("#po-cap-search");
    var section = qs(".po-capabilities, #po-capabilities");
    var nodes = qsa(".po-hub-node[data-search]");
    var cards = qsa(".po-cap-card");
    var tabs = qsa(".po-cap-tab[data-cap-tab]");
    if (!nodes.length && !cards.length) return;

    var empty = qs("#po-cap-empty");
    if (!empty && section) {
      empty = document.createElement("p");
      empty.id = "po-cap-empty";
      empty.className = "po-cap-empty";
      empty.textContent = "No use cases match that search.";
      section.appendChild(empty);
    }

    var activeTab = "all";
    var activeTabNode = tabs.filter(function (tab) {
      return tab.classList && tab.classList.contains("is-active");
    })[0];
    if (activeTabNode) activeTab = norm(activeTabNode.getAttribute("data-cap-tab") || "all");

    function tabMatches(node, tab) {
      if (!tab || tab === "all" || tab === "all-use-cases") return true;
      var aliases = [tab];
      if (tab === "software-engineering") aliases.push("engineering", "software");
      if (tab === "engineering") aliases.push("software-engineering", "software");
      if (tab === "human-resources" || tab === "hr") aliases.push("hr", "human-resources", "people");
      if (tab === "customer-success") aliases.push("support", "customer-support");
      var cat = norm(node.getAttribute("data-category") || "");
      var caps = tokens(node.getAttribute("data-caps") || "");
      return aliases.some(function (alias) {
        return cat === alias || caps.indexOf(alias) !== -1;
      });
    }

    function textMatches(node, needle) {
      if (!needle) return true;
      var haystack = [
        node.getAttribute("data-search"),
        node.getAttribute("data-caps"),
        node.getAttribute("data-category"),
        nodeText(node)
      ].join(" ").toLowerCase();
      return haystack.indexOf(needle) !== -1;
    }

    function apply() {
      var needle = input ? String(input.value || "").replace(/\s+/g, " ").trim().toLowerCase() : "";
      var shown = 0;
      nodes.concat(cards).forEach(function (node) {
        var visible = tabMatches(node, activeTab) && textMatches(node, needle);
        setHidden(node, !visible);
        if (visible) shown += 1;
      });
      if (empty) {
        setHidden(empty, shown > 0);
        if (!shown) empty.textContent = "No use cases match that search.";
      }
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activeTab = norm(tab.getAttribute("data-cap-tab") || "all");
        /* The All tab is a true reset, including a pending search. */
        if (activeTab === "all" && input) input.value = "";
        tabs.forEach(function (other) {
          var active = other === tab;
          if (other.classList) other.classList.toggle("is-active", active);
          other.setAttribute("aria-selected", active ? "true" : "false");
          other.tabIndex = active ? 0 : -1;
        });
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

  /* ---------------------- 5. Use case demo ---------------------- */
  function initUseCase() {
    var section = qs(".po-usecase, #po-usecase");
    if (!section) return;
    var roles = qsa(".po-role[data-role]", section);
    var sizes = qsa(".po-size[data-size]", section);
    var tasks = qsa(".po-task[data-task]", section);
    if (!roles.length && !sizes.length && !tasks.length) return;

    var heading = qs("#po-usecase-heading", section);
    var stage = qs("#po-usecase-stage, .po-usecase-stage", section);
    var caption = qs("#po-usecase-caption, .po-usecase-caption, .po-stage-caption, [data-usecase-caption]", section);
    if (!caption && stage) {
      caption = document.createElement("p");
      caption.id = "po-usecase-caption";
      caption.className = "po-usecase-caption";
      caption.setAttribute("aria-live", "polite");
      stage.appendChild(caption);
    }

    var view = qs(".po-view-usecase", section);
    if (!view) {
      view = document.createElement("button");
      view.type = "button";
      view.className = "po-view-usecase po-btn po-btn-dark";
      view.textContent = "View this use case in Keel";
      (qs(".po-usecase-tasks", section) || section).appendChild(view);
    }

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
    var task = initial(tasks) || "Campaign readout";

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

    function render() {
      if (heading) {
        heading.textContent = "I'm in " + titleCase(role) + sizeClause() +
          " and I need to make the " + titleCase(task) + ".";
      }
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

    view.addEventListener("click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      var company = norm(size) === "any" ? "" :
        " at " + (/^[aeiou]/i.test(String(size)) ? "an" : "a") + " " + size + " company";
      var prompt = "Help me with " + task + " for a " + role + " team" + company + ".";
      rememberPrompt(prompt);
      if (authBridge.open) authBridge.open(view);
      else showToast("Open Keel to try this prompt: " + prompt);
    });

    render();
  }

  /* ---------------------- 6. FAQ accordion ---------------------- */
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

    function setOpen(question, open) {
      setExpanded(question, open);
      if (question.classList) question.classList.toggle("is-open", open);
      var item = question.closest ? question.closest(".po-faq-item") : null;
      if (item && item.classList) item.classList.toggle("is-open", open);
      var icon = qs(".po-faq-icon", question);
      if (icon && icon.classList) icon.classList.toggle("is-open", open);
      var panel = panelFor(question);
      if (panel) {
        setHidden(panel, !open);
        panel.setAttribute("aria-hidden", open ? "false" : "true");
      }
    }

    questions.forEach(function (question) {
      setOpen(question, question.getAttribute("aria-expanded") === "true");
      question.addEventListener("click", function () {
        var wasOpen = question.getAttribute("aria-expanded") === "true";
        questions.forEach(function (other) {
          if (other !== question) setOpen(other, false);
        });
        setOpen(question, !wasOpen);
      });
    });
  }

  /* ------------------------- 7. Ask Keel ------------------------- */
  function answerFor(question) {
    var q = question.toLowerCase();
    if (/summar|meeting|transcript|notes|recap|readout/.test(q)) {
      return "For “" + question + "”, give Keel the transcript or notes and ask for a recap with decisions, owners and dates. " +
        "It will pull out the action items and leave unclear points flagged so nothing gets lost.";
    }
    if (/writ|draft|email|copy|blog|post/.test(q)) {
      return "For “" + question + "”, start with the audience, the outcome you want and one example you like. " +
        "Keel can draft a first version, match your tone and offer a shorter alternative you can edit before it goes out.";
    }
    if (/data|analy|spreadsheet|budget|number|metric|chart/.test(q)) {
      return "For “" + question + "”, upload the spreadsheet and ask Keel to clean it, compare the key columns and " +
        "explain the changes in plain language. You can check every figure before it goes into a deck.";
    }
    if (/code|build|app|bug|script|api/.test(q)) {
      return "For “" + question + "”, describe the feature and the constraints. Keel can sketch the approach, " +
        "write the first pass, explain the trade-offs and help you review the result before you ship it.";
    }
    return "Keel can help with “" + question + "”. Add the source material and the outcome you want, then ask it to " +
      "draft a first pass. You stay in control: review, edit and steer everything before it is shared.";
  }

  function initAsk() {
    var form = qs("#po-ask-form, .po-ask-form");
    if (!form) return;
    var input = qs("#po-ask-input");
    /* Handle an empty question in-page instead of relying on native bubbles. */
    form.noValidate = true;

    var result = qs("#po-ask-result");
    if (!result) {
      result = document.createElement("div");
      result.id = "po-ask-result";
      result.className = "po-ask-result";
      result.setAttribute("aria-live", "polite");
      setHidden(result, true);
      if (form.parentNode) form.parentNode.appendChild(result);
    }

    var timer = null;
    form.addEventListener("submit", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      var question = input ? String(input.value || "").replace(/\s+/g, " ").trim() : "";
      if (!question) {
        if (timer) { clearTimeout(timer); timer = null; }
        if (result.classList) result.classList.remove("is-thinking");
        setHidden(result, false);
        result.textContent = "Type a question first — for example, “Summarize this meeting into action items.”";
        if (input && typeof input.focus === "function") input.focus();
        return;
      }
      if (timer) clearTimeout(timer);
      setHidden(result, false);
      if (result.classList) result.classList.add("is-thinking");
      result.textContent = "Keel is thinking…";
      if (input) input.value = "";
      timer = setTimeout(function () {
        timer = null;
        if (result.classList) result.classList.remove("is-thinking");
        result.textContent = answerFor(question);
      }, 700);
    });
  }

  /* --------------------- 8. Footer link search --------------------- */
  function initFooterSearch() {
    var form = qs("#po-footer-search-form, .po-footer-search");
    var input = qs("#po-footer-search");
    if (!form || !input) return;
    var links = qsa(".po-footer-link");
    var footer = qs(".po-footer, #po-footer");
    var result = qs("#po-footer-search-result");
    if (!result) {
      result = document.createElement("p");
      result.id = "po-footer-search-result";
      result.className = "po-footer-search-result";
      result.setAttribute("aria-live", "polite");
      setHidden(result, true);
      if (footer) footer.appendChild(result);
      else if (form.parentNode) form.parentNode.appendChild(result);
    }

    function apply() {
      var query = String(input.value || "").replace(/\s+/g, " ").trim();
      var needle = query.toLowerCase();
      var shown = 0;
      links.forEach(function (link) {
        var match = !needle || nodeText(link).toLowerCase().indexOf(needle) !== -1;
        setHidden(link, !match);
        if (match) shown += 1;
      });
      if (!needle) {
        setHidden(result, true);
        result.textContent = "";
        return;
      }
      setHidden(result, false);
      result.textContent = shown
        ? shown + (shown === 1 ? " matching link" : " matching links") + " for “" + query + "”."
        : "No footer links match “" + query + "”. Try “download”, “privacy” or “code”.";
    }

    form.addEventListener("submit", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      apply();
    });
    input.addEventListener("input", apply);
    input.addEventListener("change", apply);
    input.addEventListener("search", apply);
    /* The button is type=submit, so the form handler covers it; wire it
       explicitly too so clicking never depends on implicit submit behaviour. */
    qsa(".po-footer-search-btn", footer || document).forEach(function (button) {
      button.addEventListener("click", apply);
    });
    var clear = qs(".po-footer-search-clear, [data-footer-search-clear]", form);
    if (clear) {
      clear.addEventListener("click", function () {
        input.value = "";
        apply();
        if (typeof input.focus === "function") input.focus();
      });
    }
  }

  /* ------------------------- 9. Auth modal ------------------------- */
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
      if (modal.classList) modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("po-modal-open");
      var target = input || qs("button, a[href], input", dialog);
      if (target && typeof target.focus === "function") target.focus();
    }

    function close() {
      if (modal.hidden) return;
      if (redirectTimer) { clearTimeout(redirectTimer); redirectTimer = null; }
      setHidden(modal, true);
      if (modal.classList) modal.classList.remove("is-open");
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

    function noRedirect() {
      return !!(form && form.hasAttribute && form.hasAttribute("data-no-redirect")) ||
        !!(modal && modal.hasAttribute && modal.hasAttribute("data-no-redirect")) ||
        !!(lastFocused && lastFocused.hasAttribute && lastFocused.hasAttribute("data-no-redirect"));
    }

    function finishSignIn(byEmail) {
      try {
        window.localStorage.setItem("keel_logged_in", "1");
      } catch (storageError) { /* storage may be blocked — the demo still continues */ }
      pendingPrompt = "";
      setContext("");
      if (noRedirect()) {
        showToast("Demo sign-in complete — you're logged in to Keel. No real account was created.");
        close();
        return;
      }
      if (byEmail) {
        setHidden(modal, true);
        if (modal.classList) modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("po-modal-open");
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
        try { window.localStorage.setItem("keel_auth_email", value); } catch (storageError) { /* optional */ }
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

  /* ------------- 10/12. Try-prompt links and news chip ------------- */
  function initTryPrompts() {
    var links = qsa(".po-text-link[data-try-prompt]");
    links.forEach(function (link) {
      link.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        rememberPrompt(link.getAttribute("data-try-prompt") || "");
        if (authBridge.open) authBridge.open(link);
        else showToast("Open Keel to try this prompt: " + pendingPrompt);
      });
    });
  }

  function initNews() {
    qsa(".po-news-dismiss").forEach(function (button) {
      button.addEventListener("click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var chip = button.closest ? (
          button.closest(".po-news-chip") ||
          button.closest("[data-news-chip]") ||
          button.closest("#po-news-chip")
        ) : null;
        if (!chip) chip = qs(".po-news-chip");
        if (!chip) return;
        setHidden(chip, true);
        if (chip.classList) chip.classList.add("is-dismissed");
      });
    });
  }

  /* ------------------- 13. Footer language selector ------------------- */
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

      /* Move the existing text into a dedicated span so the decorative
         chevron survives every label update. */
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

      /* Wrap the button in JS — the HTML file stays untouched. */
      var wrapper = document.createElement("div");
      wrapper.className = "po-lang-wrap";
      wrapper.style.position = "relative";
      wrapper.style.display = "inline-flex";
      wrapper.style.alignItems = "center";
      if (button.parentNode && button.parentNode.insertBefore) {
        button.parentNode.insertBefore(wrapper, button);
      }
      wrapper.appendChild(button);

      var menu = document.createElement("div");
      menu.className = "po-lang-menu";
      menu.id = menuId;
      menu.setAttribute("role", "menu");
      menu.setAttribute("aria-label", "Choose a language");
      menu.style.position = "absolute";
      menu.style.bottom = "calc(100% + 8px)";
      menu.style.right = "0";
      menu.style.minWidth = "152px";
      menu.style.padding = "6px";
      menu.style.border = "1px solid rgba(255,255,255,.18)";
      menu.style.borderRadius = "12px";
      menu.style.background = "#1d1a17";
      menu.style.boxShadow = "0 12px 32px rgba(0,0,0,.35)";
      menu.style.zIndex = "120";
      wrapper.appendChild(menu);

      button.setAttribute("aria-haspopup", "menu");
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", menuId);
      setHidden(menu, true);

      var open = false;

      function render(state, moveFocus) {
        open = !!state;
        setHidden(menu, !open);
        setExpanded(button, open);
        if (button.classList) button.classList.toggle("is-open", open);
        if (menu.classList) menu.classList.toggle("is-open", open);
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
          return lang.code === clean.toLowerCase() ||
            lang.label.toLowerCase() === clean.toLowerCase();
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

      var items = LANGUAGES.map(function (lang) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "po-lang-option";
        item.setAttribute("role", "menuitemradio");
        item.setAttribute("aria-checked", "false");
        item.textContent = lang.label;
        item.style.display = "block";
        item.style.width = "100%";
        item.style.padding = "7px 10px";
        item.style.border = "0";
        item.style.borderRadius = "8px";
        item.style.background = "transparent";
        item.style.color = "#f7f6f2";
        item.style.font = "inherit";
        item.style.fontSize = "12px";
        item.style.textAlign = "left";
        item.style.cursor = "pointer";
        item.addEventListener("mouseenter", function () {
          item.style.background = "rgba(255,255,255,.12)";
        });
        item.addEventListener("mouseleave", function () {
          item.style.background = "transparent";
        });
        item.addEventListener("click", function () { choose(lang); });
        menu.appendChild(item);
        return item;
      });

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

      /* Restore a previously chosen language silently. */
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
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initPersonas);
    safe(initCapabilities);
    safe(initUseCase);
    safe(initFaq);
    safe(initAsk);
    safe(initFooterSearch);
    safe(initAuthModal);
    safe(initTryPrompts);
    safe(initNews);
    safe(initLangSelector);
    safe(initGlobalKeys);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

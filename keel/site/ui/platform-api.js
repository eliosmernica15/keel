/* ===========================================================================
   KEEL Platform API page — progressive enhancement, no libraries, no network.
   Every initializer runs through safe(); every lookup is guarded. The page is
   being rebuilt, so each feature discovers its controls through several
   candidate selectors and falls back to text/structure matching. Missing
   infrastructure (toast, progress, dialog) is created locally so that no
   control can ever be a dead click.
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

  function firstOf(selectors, root) {
    var list = typeof selectors === "string" ? [selectors] : (selectors || []);
    for (var i = 0; i < list.length; i += 1) {
      var found = qs(list[i], root);
      if (found) return found;
    }
    return null;
  }

  function allOf(selectors, root) {
    var out = [];
    (selectors || []).forEach(function (selector) {
      qsa(selector, root).forEach(function (node) {
        if (out.indexOf(node) === -1) out.push(node);
      });
    });
    return out;
  }

  /* One broken section must never stop the others. */
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

  function focusable(root) {
    return qsa(
      'a[href], button:not([disabled]), input:not([disabled]), ' +
      'textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      root
    ).filter(isVisible);
  }

  function focusNode(node) {
    if (node && typeof node.focus === "function") {
      try { node.focus(); } catch (error) { /* focus is best effort */ }
    }
  }

  function reducedMotion() {
    return !!(typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className && node.className !== undefined) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function inline(node, styles) {
    if (!node || !node.style) return node;
    Object.keys(styles || {}).forEach(function (key) { node.style[key] = styles[key]; });
    return node;
  }

  function closest(node, selectors) {
    if (!node || typeof node.closest !== "function") return null;
    try { return node.closest(selectors); } catch (error) { return null; }
  }

  function controlsMatching(root, pattern) {
    return qsa('button, a[href], [role="button"], input[type="button"]', root)
      .filter(function (node) {
        return pattern.test(nodeText(node) + " " + String(node.getAttribute("aria-label") || ""));
      });
  }

  function elementsMatching(selector, pattern, root) {
    return qsa(selector, root).filter(function (node) { return pattern.test(nodeText(node)); });
  }

  function scrollTo(node) {
    if (!node || typeof node.scrollIntoView !== "function") return;
    try {
      node.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
    } catch (error) {
      try { node.scrollIntoView(true); } catch (ignored) { /* scroll is best effort */ }
    }
  }

  /* ----------------------- infrastructure ----------------------- */
  function ensureToast() {
    var toast = qs("#pa-toast");
    if (toast || !document.body) return toast;
    toast = el("div", "pa-toast");
    toast.id = "pa-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    inline(toast, {
      position: "fixed", left: "50%", bottom: "24px", transform: "translateX(-50%)",
      maxWidth: "min(92vw, 520px)", padding: "12px 20px", borderRadius: "999px",
      background: "#191919", color: "#f7f6f2", fontSize: "13px", lineHeight: "1.4",
      boxShadow: "0 12px 40px rgba(0,0,0,.28)", zIndex: "10001", textAlign: "center"
    });
    document.body.appendChild(toast);
    setHidden(toast, true);
    return toast;
  }

  var toastTimer = null;

  function showToast(message) {
    var toast = ensureToast();
    if (!toast || !message) return;
    toast.textContent = String(message);
    setHidden(toast, false);
    toast.style.display = "block";
    if (toast.classList) toast.classList.add("is-visible");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastTimer = null;
      setHidden(toast, true);
      if (toast.classList) toast.classList.remove("is-visible");
    }, 4000);
  }

  function copyText(value, label) {
    var text = String(value == null ? "" : value);
    var message = label || "Copied to clipboard";
    function fallback() {
      var area = null;
      try {
        area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        inline(area, { position: "fixed", top: "-9999px", left: "0", opacity: "0" });
        document.body.appendChild(area);
        area.select();
        var copied = false;
        try { copied = document.execCommand("copy"); } catch (error) { copied = false; }
        showToast(copied ? message : "Copy unavailable — please select the text manually.");
      } catch (error) {
        showToast("Copy unavailable — please select the text manually.");
      }
      if (area && area.parentNode) area.parentNode.removeChild(area);
    }
    if (typeof navigator !== "undefined" && navigator.clipboard &&
        typeof navigator.clipboard.writeText === "function") {
      try {
        var result = navigator.clipboard.writeText(text);
        if (result && typeof result.then === "function") result.then(function () { showToast(message); }, fallback);
        else showToast(message);
        return;
      } catch (error) { /* fall through to execCommand */ }
    }
    fallback();
  }

  /* ---- shared "ask this page" search used by both modal variants ---- */
  function searchPageAndRender(query, results, onPick) {
    if (!results) return;
    var cleaned = String(query == null ? "" : query).replace(/\s+/g, " ").trim();
    while (results.firstChild) results.removeChild(results.firstChild);
    if (!cleaned) {
      results.appendChild(el("p", "pa-ask-empty", "Type a question first — for example, “How does batch pricing work?”"));
      return;
    }
    var words = cleaned.toLowerCase().split(/\s+/).filter(function (word) { return word.length > 2; });
    var sections = qsa("main section, section").map(function (section) {
      var heading = firstOf("h1, h2, h3, h4", section);
      return {
        node: section,
        title: nodeText(heading) || String(section.id || "Section"),
        text: nodeText(section)
      };
    });
    function score(record) {
      var haystack = record.text.toLowerCase();
      return words.reduce(function (count, word) {
        return count + (haystack.indexOf(word) !== -1 ? 1 : 0);
      }, 0);
    }
    var matches = sections.filter(function (record) { return score(record) > 0; })
      .sort(function (a, b) { return score(b) - score(a); }).slice(0, 8);
    if (!matches.length) {
      results.appendChild(el("p", "pa-ask-empty", "No sections on this page match “" + cleaned + "”."));
      showToast("No sections on this page match “" + cleaned + "”.");
      return;
    }
    results.appendChild(el("p", "pa-ask-summary", matches.length + " matching section" +
      (matches.length === 1 ? "" : "s") + " for “" + cleaned + "”:"));
    matches.forEach(function (record) {
      var button = el("button", "pa-ask-result");
      button.type = "button";
      button.appendChild(el("strong", "", record.title));
      var snippet = record.text.length > 150 ? record.text.slice(0, 147) + "…" : record.text;
      button.appendChild(el("span", "", snippet));
      inline(button, {
        display: "block", width: "100%", textAlign: "left", padding: "9px 12px",
        margin: "6px 0", border: "1px solid #dedcd6", borderRadius: "10px",
        background: "#fff", cursor: "pointer", color: "inherit", font: "inherit"
      });
      on(button, "click", function () {
        if (typeof onPick === "function") onPick(record);
        else scrollTo(record.node);
      });
      results.appendChild(button);
    });
  }

  /* --------------------- generic info copy --------------------- */
  var INFO_COPY = {
    docs: {
      title: "KEEL documentation",
      subtitle: "Guides, references and quickstarts",
      blocks: [
        { label: "Get started", text: "Create an API key, install the SDK and send your first request in a few minutes." },
        { label: "API reference", text: "Messages, models, batch processing, prompt caching and tool use are all documented with copyable examples." },
        { label: "Build with agents", text: "Use the Agent SDK, Model Context Protocol skills and Managed Agents to ship long-running workflows." }
      ]
    },
    info: {
      title: "KEEL Platform",
      subtitle: "Models, harnesses, context and infrastructure that work together.",
      blocks: [
        { label: "Models", text: "Fable 5.2, Opus 5.5, Sonnet 5.5 and Haiku 5.5 cover everything from multi-day agents to real-time responses." },
        { label: "Platform", text: "Code execution, structured outputs, tool use, computer use, citations, files, compaction and web search." },
        { label: "Enterprise", text: "US-only inference, residency controls, sandbox isolation and deployment on all major cloud providers." }
      ]
    },
    mcp: {
      title: "Model Context Protocol (MCP)",
      subtitle: "Connect KEEL to your tools and data through an open standard.",
      blocks: [
        { label: "One integration", text: "Expose a tool or data source once and let any MCP-compatible KEEL agent call it." },
        { label: "Composable", text: "Combine your internal APIs, databases and metrics with the growing ecosystem of MCP servers." },
        { label: "Control", text: "Permissions and tool descriptions stay in your hands, so agents only reach what you allow." }
      ]
    },
    skills: {
      title: "Skills",
      subtitle: "Teach KEEL your expertise, procedures and best practices.",
      blocks: [
        { label: "Reusable", text: "Package instructions and scripts into a skill that agents load only when the task calls for it." },
        { label: "Customizable", text: "Start from a pre-built skill or write your own to match how your team actually works." },
        { label: "Portable", text: "Skills work across the API, KEEL Code and Managed Agents." }
      ]
    },
    memory: {
      title: "Memory stores",
      subtitle: "Agents remember across sessions.",
      blocks: [
        { label: "Your infrastructure", text: "Keep memory files on infrastructure you control, with the retention and access rules you choose." },
        { label: "Continuity", text: "Agents pick up conventions, decisions and prior work without re-reading everything." },
        { label: "Auditable", text: "Every remembered fact is a file you can inspect, edit or remove." }
      ]
    },
    partners: {
      title: "KEEL Marketplace",
      subtitle: "Use your existing KEEL commitment to pay for partner solutions.",
      blocks: [
        { label: "Partner-built", text: "Discover KEEL-powered products from partners across productivity, engineering and operations." },
        { label: "One commitment", text: "Pay with your existing KEEL commitment instead of procuring each tool separately." },
        { label: "Curated", text: "Every listing is reviewed for quality and security before it appears in the marketplace." }
      ]
    },
    batch: {
      title: "Batch processing",
      subtitle: "Save 50% on asynchronous API work.",
      blocks: [
        { label: "Half the price", text: "Submit thousands of requests in one batch and pay 50% less for input and output tokens." },
        { label: "Asynchronous", text: "Results arrive when the batch completes, with the same reliability as the standard API." },
        { label: "Ideal for", text: "Classification, summarization, evals and any workload that does not need a real-time response." }
      ]
    },
    caching: {
      title: "Prompt caching",
      subtitle: "Reuse repeated context for a fraction of the price.",
      blocks: [
        { label: "Five-minute TTL", text: "Cached prefixes stay available for five minutes, with extended caching available for longer runs." },
        { label: "Lower latency", text: "Long prompts are read back quickly, so context-heavy assistants feel faster." },
        { label: "Transparent", text: "Cache reads and writes are reported separately in your usage and cost metrics." }
      ]
    },
    enterprise: {
      title: "Built for enterprise workloads",
      subtitle: "Controls and safeguards for your data.",
      blocks: [
        { label: "Safeguards", text: "Enterprise Frontier Safeguards, residency options and controls that keep your data yours." },
        { label: "Deployment", text: "Available on AWS, Google Cloud and Microsoft Foundry, with US-only inference where required." },
        { label: "Assurance", text: "Encryption, access controls and audit logs are built in from the first request." }
      ]
    },
    console: {
      title: "KEEL Console",
      subtitle: "Observe and manage your agents in one place.",
      blocks: [
        { label: "Build", text: "Prototype prompts, upload skills and files, and configure agents before deployment." },
        { label: "Deploy and monitor", text: "Ship to production, then inspect every session trace, tool call and cost signal." },
        { label: "Manage", text: "Control keys, limits and team access from a single console." }
      ]
    },
    resource: {
      title: "KEEL resource",
      subtitle: "Guides and ideas for building with the KEEL Platform.",
      blocks: [
        { label: "Learn", text: "Read the full article in the KEEL resources library for examples and implementation detail." },
        { label: "Apply", text: "Bring the patterns back to your own agents, prompts and evaluation setup." }
      ]
    }
  };

  function infoForText(text, fallback) {
    var value = String(text || "").toLowerCase();
    if (/mcp|model context protocol/.test(value)) return INFO_COPY.mcp;
    if (/skill/.test(value)) return INFO_COPY.skills;
    if (/memory/.test(value)) return INFO_COPY.memory;
    if (/partner|marketplace/.test(value)) return INFO_COPY.partners;
    if (/batch/.test(value)) return INFO_COPY.batch;
    if (/cach/.test(value)) return INFO_COPY.caching;
    if (/enterprise|residency|your data|safeguard/.test(value)) return INFO_COPY.enterprise;
    if (/console|observ|monitor/.test(value)) return INFO_COPY.console;
    if (/documentation|docs|reference|quickstart/.test(value)) return INFO_COPY.docs;
    return fallback || INFO_COPY.info;
  }

  /* ------------------------- modal engine ------------------------- */
  var modalEngine = null;

  var modalBridge = {
    open: function (trigger, mode) {
      var engine = getModalEngine();
      if (engine) engine.open(trigger, mode);
    },
    openMode: function (trigger, mode) { modalBridge.open(trigger, mode); },
    openInfo: function (spec, trigger) {
      var engine = getModalEngine();
      if (engine) engine.openInfo(spec, trigger);
      else showToast(spec && spec.title ? spec.title : "KEEL Platform");
    },
    close: function () {
      var engine = getModalEngine();
      if (engine) engine.close();
    }
  };

  function getModalEngine() {
    if (modalEngine) return modalEngine;
    try { modalEngine = buildModalEngine(); }
    catch (error) { modalEngine = null; }
    return modalEngine;
  }

  function buildModalEngine() {
    var created = false;
    var root = firstOf([
      "#pa-modal", "#pa-auth-modal", "[data-pa-modal-root]", ".pa-modal", '[role="dialog"]'
    ]);
    if (!root || !document.body) {
      created = true;
      root = el("div", "pa-modal");
      root.id = "pa-modal";
      root.setAttribute("role", "dialog");
      root.setAttribute("aria-modal", "true");
      inline(root, {
        position: "fixed", top: "0", right: "0", bottom: "0", left: "0",
        display: "none", alignItems: "center", justifyContent: "center",
        padding: "20px", background: "rgba(18,17,15,.56)", zIndex: "10000"
      });
      document.body.appendChild(root);
    }
    var card = firstOf([
      ".pa-modal-card", ".pa-modal-dialog", ".pa-modal-inner", ".pa-dialog", "[data-pa-modal-card]"
    ], root) || root;
    if (created) {
      inline(card, {
        position: "relative", width: "100%", maxWidth: "480px", maxHeight: "90vh",
        overflow: "auto", padding: "30px", borderRadius: "18px", background: "#fff",
        color: "#191919", boxShadow: "0 24px 80px rgba(0,0,0,.32)", fontFamily: "inherit"
      });
    }

    var title = firstOf(["#pa-modal-title", ".pa-modal-title", "h1, h2, h3"], card);
    if (!title) {
      title = el("h2", "pa-modal-title", "Sign in to KEEL");
      title.id = "pa-modal-title";
      card.insertBefore(title, card.firstChild);
    }
    var desc = firstOf(["#pa-modal-desc", ".pa-modal-desc", ".pa-modal-subtitle"], card);
    if (!desc && title.parentNode) {
      desc = el("p", "pa-modal-desc");
      desc.id = "pa-modal-desc";
      title.parentNode.insertBefore(desc, title.nextSibling);
    }

    var forms = qsa("form", card);
    var authForm = firstOf(["#pa-auth-form", ".pa-auth-form", "form[data-pa-auth]"], card) ||
      forms.filter(function (form) {
        return /sign|log|email|get started|try keel/i.test(nodeText(form) + " " + String(form.id || ""));
      })[0] || forms[0] || null;
    var contactForm = firstOf(["#pa-contact-form", ".pa-contact-form", "form[data-pa-contact]"], card) ||
      forms.filter(function (form) {
        return form !== authForm && /contact|sales|message|full name/i.test(nodeText(form) + " " + String(form.id || ""));
      })[0] || null;

    if (!authForm) {
      authForm = el("form", "pa-auth-form");
      authForm.id = "pa-auth-form";
      var google = el("button", "pa-btn pa-btn-outline pa-google-btn", "Continue with Google");
      google.type = "button";
      google.id = "pa-google";
      authForm.appendChild(google);
      var label = el("label", "pa-sr-only", "Email");
      label.setAttribute("for", "pa-email");
      authForm.appendChild(label);
      var emailInput = el("input", "pa-input");
      emailInput.type = "email";
      emailInput.id = "pa-email";
      emailInput.placeholder = "you@example.com";
      authForm.appendChild(emailInput);
      var submit = el("button", "pa-btn pa-btn-dark", "Continue with email");
      submit.type = "submit";
      authForm.appendChild(submit);
      card.appendChild(authForm);
    }

    var emailInput = firstOf(["#pa-email", "#pa-auth-email", ".pa-auth-email", 'input[type="email"]'], authForm);
    if (!emailInput) {
      emailInput = el("input", "pa-input");
      emailInput.type = "email";
      emailInput.id = "pa-email";
      emailInput.placeholder = "you@example.com";
      authForm.insertBefore(emailInput, authForm.firstChild);
    }
    var google = firstOf(["#pa-google", ".pa-google-btn", "[data-pa-google]"], card) ||
      controlsMatching(authForm, /google/i)[0] || null;
    if (!google) {
      google = el("button", "pa-btn pa-btn-outline pa-google-btn", "Continue with Google");
      google.type = "button";
      authForm.insertBefore(google, emailInput);
    }

    if (!contactForm) {
      contactForm = el("form", "pa-contact-form");
      contactForm.id = "pa-contact-form";
      [["text", "Full name", "pa-name"], ["email", "Work email", "pa-work-email"]].forEach(function (spec) {
        var input = el("input", "pa-input");
        input.type = spec[0];
        input.placeholder = spec[1];
        input.id = spec[2];
        input.required = true;
        contactForm.appendChild(input);
      });
      var message = el("textarea", "pa-input");
      message.id = "pa-message";
      message.rows = 4;
      message.placeholder = "How can we help?";
      message.required = true;
      contactForm.appendChild(message);
      var contactSubmit = el("button", "pa-btn pa-btn-dark", "Send message");
      contactSubmit.type = "submit";
      contactForm.appendChild(contactSubmit);
      card.appendChild(contactForm);
    }
    setHidden(contactForm, true);

    var closeButton = firstOf(["[data-pa-close]", "[data-pa-modal-close]", ".pa-modal-close"], card);
    if (!closeButton) {
      closeButton = el("button", "pa-modal-close", "×");
      closeButton.type = "button";
      closeButton.setAttribute("aria-label", "Close");
      closeButton.setAttribute("data-pa-close", "");
      inline(closeButton, {
        position: "absolute", top: "10px", right: "14px", border: "0",
        background: "transparent", fontSize: "24px", cursor: "pointer", color: "inherit"
      });
      card.insertBefore(closeButton, card.firstChild);
    }

    function region(className, id) {
      var node = firstOf(["#" + id], card);
      if (!node) {
        node = el("div", "pa-ui-region " + className);
        node.id = id;
        node.tabIndex = -1;
        inline(node, { margin: "12px 0", fontSize: "14px", lineHeight: "1.6" });
        card.appendChild(node);
      }
      setHidden(node, true);
      return node;
    }
    var info = region("pa-modal-info", "pa-ui-info");
    var success = region("pa-modal-success", "pa-ui-success");
    var ask = region("pa-modal-ask", "pa-ui-ask");
    var player = region("pa-modal-player", "pa-ui-player");
    var askForm = firstOf(["#pa-ask-form", ".pa-ask-form", "form[data-pa-ask]"], card);
    var askInput = askForm ? firstOf(["#pa-ask-q", "#pa-ask-input", 'input[type="search"]'], askForm) : null;
    var askResults = askForm ? firstOf(["#pa-ask-results", ".pa-ask-results"], askForm) : null;
    var note = firstOf([".pa-modal-note", "[data-pa-demo-note]"], card);
    if (!note) {
      note = el("p", "pa-modal-note", "Demo sign-in — no real Google account is connected.");
      if (google && google.parentNode) google.parentNode.insertBefore(note, google.nextSibling);
      else card.appendChild(note);
    }
    setHidden(note, true);

    var lastFocused = null;

    function setHeading(heading, copy) {
      if (title) title.textContent = heading || "";
      if (desc) desc.textContent = copy || "";
    }

    function resetPanels() {
      setHidden(authForm, true);
      setHidden(contactForm, true);
      setHidden(info, true);
      setHidden(success, true);
      setHidden(ask, true);
      setHidden(askForm, true);
      setHidden(player, true);
      setHidden(note, true);
      if (emailInput) emailInput.removeAttribute("aria-invalid");
    }

    function fillInfo(spec) {
      var data = spec || {};
      while (info.firstChild) info.removeChild(info.firstChild);
      (data.blocks || []).forEach(function (block) {
        if (!block) return;
        var row = el("p", "pa-modal-info-row");
        if (block.label) row.appendChild(el("strong", "", block.label + ": "));
        row.appendChild(document.createTextNode(block.text || ""));
        info.appendChild(row);
      });
      setHeading(data.title || "KEEL Platform", data.subtitle || "More information");
      setHidden(info, false);
    }

    function showSuccess(heading, copy) {
      resetPanels();
      while (success.firstChild) success.removeChild(success.firstChild);
      success.appendChild(el("h3", "", heading || "You're signed in"));
      success.appendChild(el("p", "", copy || "Your demo session is ready."));
      var link = el("a", "pa-btn pa-btn-dark", "Open the KEEL app ↗");
      link.href = "/login";
      success.appendChild(link);
      setHeading("You're all set", "Continue to KEEL when you're ready.");
      setHidden(success, false);
      focusNode(link);
    }

    function open(trigger, mode) {
      lastFocused = trigger || document.activeElement;
      resetPanels();
      setHidden(root, false);
      root.style.display = "flex";
      if (root.classList) root.classList.add("is-open");
      root.setAttribute("aria-hidden", "false");
      if (document.body && document.body.classList) document.body.classList.add("pa-modal-open");
      var kind = norm(mode || "signup");
      if (kind === "contact") {
        setHeading("Contact sales", "Tell us what you're building and we'll get back to you.");
        setHidden(contactForm, false);
        focusNode(firstOf("input, textarea", contactForm));
        return;
      }
      if (kind === "ask") {
        setHeading("Ask questions about this page", "Search the visible page and jump to a matching section.");
        if (askForm && askInput) {
          if (askResults) {
            while (askResults.firstChild) askResults.removeChild(askResults.firstChild);
          }
          setHidden(askForm, false);
          focusNode(askInput);
        } else {
          buildAskRegion();
          setHidden(ask, false);
          focusNode(qs("#pa-ask-input", ask));
        }
        return;
      }
      if (kind === "player") {
        setHeading("KEEL Managed Agents", "A simulated preview — no video is streamed in this demo.");
        buildPlayerRegion();
        setHidden(player, false);
        focusNode(firstOf("button", player));
        return;
      }
      if (kind === "docs" || kind === "info" || kind === "model" || kind === "model-detail") {
        var data = INFO_COPY[kind] || INFO_COPY.info;
        fillInfo(data);
        focusNode(info);
        return;
      }
      setHeading("Sign in to KEEL", "Demo sign-in — no real account is required.");
      setHidden(note, false);
      setHidden(authForm, false);
      focusNode(emailInput || google || firstOf("button", authForm));
    }

    function close() {
      if (!root || root.hidden) return;
      setHidden(root, true);
      root.style.display = "none";
      if (root.classList) root.classList.remove("is-open");
      root.setAttribute("aria-hidden", "true");
      if (document.body && document.body.classList) document.body.classList.remove("pa-modal-open");
      resetPanels();
      if (lastFocused && typeof document.contains === "function" &&
          document.contains(lastFocused)) focusNode(lastFocused);
      lastFocused = null;
    }

    /* ---- ask region: search visible page text ---- */
    function buildAskRegion() {
      if (qs("#pa-ask-input", ask)) return;
      while (ask.firstChild) ask.removeChild(ask.firstChild);
      var input = el("input", "pa-input");
      input.type = "search";
      input.id = "pa-ask-input";
      input.placeholder = "What would you like to know about this page?";
      inline(input, { width: "100%", boxSizing: "border-box", padding: "10px 12px", marginBottom: "10px" });
      var search = el("button", "pa-btn pa-btn-dark", "Search this page");
      search.type = "button";
      search.id = "pa-ask-submit";
      var results = el("div", "pa-ask-results");
      results.id = "pa-ask-results";
      results.setAttribute("role", "status");
      results.setAttribute("aria-live", "polite");
      ask.appendChild(input);
      ask.appendChild(search);
      ask.appendChild(results);

      function runSearch() {
        searchPageAndRender(input.value, results, function (record) {
          close();
          scrollTo(record.node);
          showToast("Jumped to " + record.title);
        });
      }
      on(search, "click", runSearch);
      on(input, "keydown", function (event) {
        if (event && (event.key === "Enter" || event.key === "Spacebar")) {
          if (typeof event.preventDefault === "function") event.preventDefault();
          runSearch();
        }
      });
    }

    if (askForm) {
      askForm.noValidate = true;
      on(askForm, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        searchPageAndRender(askInput ? askInput.value : "", askResults, function (record) {
          close();
          scrollTo(record.node);
          showToast("Jumped to " + record.title);
        });
      });
      if (askInput) {
        on(askInput, "input", function () {
          if (askResults) {
            while (askResults.firstChild) askResults.removeChild(askResults.firstChild);
          }
        });
      }
    }

    /* ---- simulated Managed Agents player ---- */
    function buildPlayerRegion() {
      if (qs("#pa-player-toggle", player)) return;
      while (player.firstChild) player.removeChild(player.firstChild);
      var screen = el("div", "pa-player-screen", "▶");
      screen.id = "pa-player-screen";
      inline(screen, {
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "180px", borderRadius: "12px", background: "#191919",
        color: "#f7f6f2", fontSize: "46px", marginBottom: "12px"
      });
      var track = el("div", "pa-player-track");
      var fillBar = el("span", "pa-player-fill");
      track.appendChild(fillBar);
      inline(track, { height: "4px", borderRadius: "999px", background: "#e8e5db", overflow: "hidden" });
      inline(fillBar, { display: "block", width: "18%", height: "100%", background: "#d97757" });
      var toggle = el("button", "pa-btn pa-btn-outline", "Pause preview");
      toggle.type = "button";
      toggle.id = "pa-player-toggle";
      var noteText = el("p", "pa-player-note", "Simulated preview — no video is streamed in this demo.");
      player.appendChild(screen);
      player.appendChild(track);
      player.appendChild(toggle);
      player.appendChild(noteText);
      var playing = true;
      on(toggle, "click", function () {
        playing = !playing;
        screen.textContent = playing ? "▶" : "❚❚";
        toggle.textContent = playing ? "Pause preview" : "Play preview";
        fillBar.style.width = playing ? "42%" : "18%";
        showToast(playing ? "Preview playing (simulated)" : "Preview paused");
      });
    }

    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      var trigger = target.closest("[data-pa-modal], [data-pa-modal-open]");
      if (trigger) {
        if (typeof event.preventDefault === "function") event.preventDefault();
        var infoTitle = trigger.getAttribute("data-pa-info-title");
        var infoBody = trigger.getAttribute("data-pa-info-body");
        if (infoTitle || infoBody) {
          openInfo({
            title: infoTitle || "KEEL Platform",
            subtitle: nodeText(trigger) || "More information",
            blocks: infoBody ? [{ label: "Details", text: infoBody }] : []
          }, trigger);
        } else {
          open(trigger, trigger.getAttribute("data-pa-modal") ||
            trigger.getAttribute("data-pa-modal-open") || "signup");
        }
        return;
      }
      if (target.closest("[data-pa-close], [data-pa-modal-close], .pa-modal-close, .pa-modal-backdrop") ||
          target === root) {
        if (typeof event.preventDefault === "function") event.preventDefault();
        close();
      }
    });

    on(root, "keydown", function (event) {
      if (!event) return;
      if (event.key === "Escape" || event.key === "Esc") {
        if (typeof event.preventDefault === "function") event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      var nodes = focusable(card);
      if (!nodes.length) return;
      var active = document.activeElement;
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (!active || nodes.indexOf(active) === -1) {
        if (typeof event.preventDefault === "function") event.preventDefault();
        focusNode(event.shiftKey ? last : first);
        return;
      }
      if (event.shiftKey && active === first) {
        if (typeof event.preventDefault === "function") event.preventDefault();
        focusNode(last);
      } else if (!event.shiftKey && active === last) {
        if (typeof event.preventDefault === "function") event.preventDefault();
        focusNode(first);
      }
    });

    if (authForm) {
      authForm.noValidate = true;
      on(authForm, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var value = String(emailInput ? emailInput.value || "" : "").trim();
        var valid = !!value && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value) &&
          (typeof emailInput.checkValidity !== "function" || emailInput.checkValidity());
        if (!valid) {
          if (emailInput) {
            emailInput.setAttribute("aria-invalid", "true");
            focusNode(emailInput);
          }
          showToast("Enter a valid email address, like you@company.com.");
          return;
        }
        if (emailInput) emailInput.removeAttribute("aria-invalid");
        try {
          window.localStorage.setItem("keel_logged_in", "1");
          window.localStorage.setItem("keel_auth_email", value);
        } catch (storageError) { /* storage may be blocked — the demo still continues */ }
        showSuccess("You're signed in", "You're logged in to the KEEL demo. No real account was created.");
      });
    }

    if (contactForm) {
      contactForm.noValidate = true;
      on(contactForm, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var fields = qsa("input, textarea", contactForm);
        var bad = fields.filter(function (field) {
          var value = String(field.value || "").trim();
          if (!value) return true;
          if (field.type === "email") return !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
          return false;
        })[0];
        if (bad) {
          bad.setAttribute("aria-invalid", "true");
          focusNode(bad);
          showToast("Please complete the contact form before sending.");
          return;
        }
        if (typeof contactForm.reset === "function") contactForm.reset();
        showToast("Thanks — we'll be in touch soon.");
        close();
      });
    }

    on(google, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      setHidden(note, false);
      try { window.localStorage.setItem("keel_logged_in", "1"); }
      catch (storageError) { /* storage may be blocked — the demo still continues */ }
      showToast("Demo sign-in — no real Google account is connected.");
      showSuccess("Demo sign-in complete", "Your session is ready. No real Google account was connected.");
    });

    setHidden(root, true);
    root.style.display = "none";
    root.setAttribute("aria-hidden", "true");
    return { open: open, close: close, openInfo: function (spec, trigger) {
      open(trigger || null, "info");
      fillInfo(spec);
      focusNode(info);
    } };
  }

  /* ------------------------- closers ------------------------- */
  var closers = { nav: null, mobile: null, explore: null, footer: null };

  /* --------------------- 1. Mega dropdowns --------------------- */
  function initMegaNav() {
    var items = qsa(".pa-nav-item[data-pa-nav], .pa-nav-item, [data-pa-nav]");
    if (!items.length) return;

    var records = items.map(function (item) {
      var trigger = firstOf([".pa-nav-trigger", ".pa-nav-button", "button", "[aria-haspopup]"], item);
      var mega = firstOf([".pa-mega", ".pa-mega-menu", ".pa-dropdown", "[data-pa-mega]"], item);
      if (!mega && trigger) {
        var controls = trigger.getAttribute("aria-controls");
        var controlled = controls ? document.getElementById(controls) : null;
        if (controlled) mega = controlled;
      }
      if (!mega && item.nextElementSibling &&
          /mega|dropdown|menu/i.test(String(item.nextElementSibling.className || ""))) {
        mega = item.nextElementSibling;
      }
      return {
        item: item,
        trigger: trigger,
        mega: mega,
        pinned: false, open: false, openTimer: null, closeTimer: null,
        suppressFocus: false, keyHandledUntil: 0
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
      if (record.trigger) {
        setExpanded(record.trigger, record.open);
        if (!record.trigger.hasAttribute("aria-haspopup")) record.trigger.setAttribute("aria-haspopup", "true");
      }
      if (record.mega) {
        setHidden(record.mega, !record.open);
        if (record.mega.classList) record.mega.classList.toggle("is-open", record.open);
        record.mega.setAttribute("aria-hidden", record.open ? "false" : "true");
      }
    }

    function closeAll(except, restoreFocus) {
      var focused = document.activeElement;
      var restore = null;
      if (restoreFocus && focused) {
        records.forEach(function (record) {
          if (record.item && typeof record.item.contains === "function" &&
              record.item.contains(focused)) restore = record;
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
      if (!record.mega) return;
      if (trigger && !trigger.hasAttribute("aria-expanded")) setExpanded(trigger, false);
      if (!record.mega.hasAttribute("aria-hidden")) record.mega.setAttribute("aria-hidden", "true");
      render(record, false);

      on(item, "mouseenter", function () {
        if (pointerDown) return;
        clearTimers(record);
        record.openTimer = setTimeout(function () {
          record.openTimer = null;
          closeAll(item);
          render(record, true);
        }, 100);
      });
      on(item, "mouseleave", function () {
        clearTimers(record);
        record.closeTimer = setTimeout(function () {
          record.closeTimer = null;
          if (record.pinned) return;
          if (typeof item.contains === "function" && item.contains(document.activeElement)) return;
          render(record, false);
        }, 200);
      });

      if (trigger) {
        on(trigger, "pointerdown", function () {
          pointerDown = true;
          record.suppressFocus = true;
          clearTimers(record);
        });
        on(trigger, "click", function (event) {
          pointerDown = false;
          if (Date.now() < record.keyHandledUntil) {
            record.keyHandledUntil = 0;
            return;
          }
          if (event && typeof event.preventDefault === "function") event.preventDefault();
          toggle(record);
        });
        on(trigger, "keydown", function (event) {
          if (!event) return;
          var key = event.key;
          if (key === "Enter" || key === " " || key === "Spacebar") {
            if (event.repeat) { if (event.preventDefault) event.preventDefault(); return; }
            if (event.preventDefault) event.preventDefault();
            record.keyHandledUntil = Date.now() + 500;
            toggle(record);
            return;
          }
          if (key === "ArrowDown") {
            if (event.preventDefault) event.preventDefault();
            closeAll(item);
            render(record, true);
            record.pinned = true;
            focusNode(firstOf("a[href], button", record.mega));
            return;
          }
          var next = -1;
          if (key === "ArrowRight") next = (index + 1) % records.length;
          else if (key === "ArrowLeft") next = (index - 1 + records.length) % records.length;
          else if (key === "Home") next = 0;
          else if (key === "End") next = records.length - 1;
          if (next >= 0 && next !== index) {
            if (event.preventDefault) event.preventDefault();
            closeAll();
            var other = records[next];
            render(other, true);
            other.pinned = true;
            focusNode(other.trigger);
          }
        });
      }

      /* Escape closes and restores focus; Tab stays inside the open panel. */
      on(item, "keydown", function (event) {
        if (!event || !record.open) return;
        if (event.key === "Escape" || event.key === "Esc") {
          if (event.preventDefault) event.preventDefault();
          closeAll(null, true);
          return;
        }
        if (event.key !== "Tab") return;
        var nodes = [];
        if (record.trigger) nodes.push(record.trigger);
        focusable(record.mega).forEach(function (node) {
          if (nodes.indexOf(node) === -1) nodes.push(node);
        });
        if (!nodes.length) return;
        var active = document.activeElement;
        var first = nodes[0];
        var last = nodes[nodes.length - 1];
        if (event.shiftKey && active === first) {
          if (event.preventDefault) event.preventDefault();
          focusNode(last);
        } else if (!event.shiftKey && active === last) {
          if (event.preventDefault) event.preventDefault();
          focusNode(first);
        }
      });

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

      on(item, "click", function (event) {
        var target = event && event.target;
        if (!target || typeof target.closest !== "function") return;
        if (target.closest(".pa-nav-trigger, .pa-nav-button")) return;
        if (target.closest("a, button")) {
          record.pinned = false;
          closeAll();
        }
      });
    });

    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function") return;
      if (!target.closest(".pa-nav-item, [data-pa-nav]")) closeAll();
    });
    on(window, "pointerup", function () { pointerDown = false; });
    on(window, "pointercancel", function () { pointerDown = false; });
    closers.nav = function () { closeAll(null, true); };
  }

  /* --------------------- 2. Mobile menu --------------------- */
  function initMobileMenu() {
    var toggle = firstOf(["#pa-hamburger", ".pa-hamburger", "[data-pa-menu-toggle]"]);
    var menu = firstOf(["#pa-mobile-menu", ".pa-mobile-menu", "[data-pa-mobile-menu]"]);
    if (!toggle || !menu) return;
    if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, false);

    function render(open) {
      setHidden(menu, !open);
      if (menu.classList) menu.classList.toggle("is-open", !!open);
      setExpanded(toggle, !!open);
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
    closers.mobile = function () { render(false); };
    on(toggle, "click", function () { render(!!menu.hidden); });
    on(menu, "click", function (event) {
      var target = event && event.target;
      if (target && typeof target.closest === "function" && target.closest("a, button")) render(false);
    });
    on(document, "click", function (event) {
      var target = event && event.target;
      if (!target || typeof target.closest !== "function" || menu.hidden) return;
      if (target.closest("#pa-hamburger, .pa-hamburger, #pa-mobile-menu, .pa-mobile-menu")) return;
      render(false);
    });
    on(window, "resize", function () {
      if (window.innerWidth > 900 && !menu.hidden) render(false);
    });
  }

  /* ----------- 3. Explore panel + ask / markdown actions ----------- */
  function initExplorePanel() {
    var toggle = firstOf([
      "#pa-explore-toggle", ".pa-explore-toggle", "[data-pa-explore-toggle]", "[data-pa-panel-toggle]"
    ]) || controlsMatching(document, /^explore here/i)[0] || null;
    var panel = firstOf([
      "#pa-explore-list", "#pa-explore-panel", ".pa-explore-list", ".pa-explore-panel",
      "[data-pa-explore-panel]", "[data-pa-panel]"
    ]);
    var host = firstOf(["#pa-explore", ".pa-explore", "[data-pa-explore]"]);

    if (!panel && toggle && document.body) {
      panel = el("nav", "pa-explore-panel");
      panel.id = "pa-explore-panel";
      inline(panel, {
        position: "absolute", right: "0", top: "calc(100% + 8px)", zIndex: "60",
        minWidth: "260px", padding: "10px", background: "#fff",
        border: "1px solid #dedcd6", borderRadius: "12px", boxShadow: "0 14px 40px rgba(0,0,0,.12)"
      });
      if (toggle.parentNode) toggle.parentNode.insertBefore(panel, toggle.nextSibling);
      else document.body.appendChild(panel);
    }
    if (!panel) {
      /* No toggle and no panel: still expose the two actions in the page. */
      var askFallback = controlsMatching(document, /ask questions about this page/i)[0];
      var mdFallback = controlsMatching(document, /copy as markdown/i)[0];
      if (askFallback) on(askFallback, "click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        modalBridge.openMode(askFallback, "ask");
      });
      if (mdFallback) on(mdFallback, "click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        copyText(pageOutline(), "Page outline copied as markdown");
      });
      return;
    }

    var ask = firstOf([
      "[data-pa-ask]", "[data-pa-ask-page]", "[data-pa-action='ask']", "#pa-ask-page",
      ".pa-ask-page", ".pa-explore-action"
    ], panel) || controlsMatching(panel, /ask questions|ask about this page/i)[0] || null;
    var markdown = firstOf([
      "[data-pa-markdown]", "[data-pa-copy-md]", "[data-pa-action='markdown']", "#pa-copy-markdown", ".pa-copy-md"
    ], panel) || controlsMatching(panel, /copy as markdown/i)[0] || null;

    if (!ask) {
      ask = el("button", "pa-explore-action", "Ask questions about this page");
      ask.type = "button";
      ask.setAttribute("data-pa-ask", "");
      panel.insertBefore(ask, panel.firstChild);
    }
    if (!markdown) {
      markdown = el("button", "pa-explore-action", "Copy as markdown");
      markdown.type = "button";
      markdown.setAttribute("data-pa-markdown", "");
      panel.appendChild(markdown);
    }

    on(ask, "click", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      setHidden(panel, true);
      if (toggle) setExpanded(toggle, false);
      modalBridge.openMode(ask, "ask");
    });
    on(markdown, "click", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      /* The real page supplies a prebuilt outline via data-pa-copy; the
         generic copy handler owns that action, so only close the panel. */
      if (!markdown.hasAttribute("data-pa-copy")) {
        copyText(pageOutline(), "Page outline copied as markdown");
      }
      setHidden(panel, true);
      if (toggle) setExpanded(toggle, false);
    });

    if (toggle) {
      if (!toggle.hasAttribute("aria-expanded")) setExpanded(toggle, !panel.hidden);
      on(toggle, "click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        var open = !!panel.hidden;
        setHidden(panel, !open);
        setExpanded(toggle, open);
        if (host && host.classList) host.classList.toggle("is-open", open);
        var icon = qs(".pa-explore-icon, .pa-chevron, [aria-hidden='true']", toggle);
        if (icon && icon.textContent !== undefined) icon.textContent = open ? "—" : "+";
      });
      closers.explore = function () {
        setHidden(panel, true);
        setExpanded(toggle, false);
      };
      on(document, "click", function (event) {
        var target = event && event.target;
        if (!target || typeof target.closest !== "function" || panel.hidden) return;
        if (target.closest("#pa-explore, .pa-explore, [data-pa-explore], [data-pa-panel-toggle]")) return;
        closers.explore();
      });
    }

    /* Active section highlighting when the panel links are present. */
    var links = allOf([".pa-explore-link", ".pa-explore-panel a[href^='#']"], panel);
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
      try {
        var observer = new window.IntersectionObserver(function (entries) {
          var visible = entries.filter(function (entry) { return entry.isIntersecting; });
          if (!visible.length) return;
          visible.sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });
          for (var i = 0; i < sections.length; i += 1) {
            if (sections[i].target === visible[0].target) { activate(sections[i].link); break; }
          }
        }, { rootMargin: "-10% 0px -65% 0px", threshold: 0 });
        sections.forEach(function (record) { observer.observe(record.target); });
      } catch (error) { /* observer is optional */ }
    }
  }

  function pageOutline() {
    var lines = ["KEEL Platform", ""];
    var main = qs("main") || document.body;
    var headings = qsa("h1, h2, h3, h4", main).filter(function (node) {
      return isVisible(node) && nodeText(node);
    });
    if (!headings.length) headings = qsa("h1, h2, h3", document.body);
    headings.forEach(function (heading) {
      var level = Number(String(heading.tagName).replace(/\D/g, "") || "2");
      var prefix = new Array(Math.max(1, Math.min(4, level - 1)) + 1).join("#");
      lines.push(prefix + " " + nodeText(heading));
      var section = closest(heading, "section, article");
      if (section) {
        var items = qsa("li", section).slice(0, 4);
        items.forEach(function (item) { lines.push("- " + nodeText(item)); });
      }
      lines.push("");
    });
    return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim() + "\n";
  }

  /* --------------------- 4. Reading progress --------------------- */
  function initProgress() {
    var fill = firstOf(["#pa-progress-fill", ".pa-progress-fill", "[data-pa-progress-fill]"]);
    var bar = firstOf(["#pa-progress", ".pa-progress", "[data-pa-progress]"]);
    if (!fill && document.body) {
      bar = el("div", "pa-progress");
      bar.id = "pa-progress";
      inline(bar, { position: "fixed", top: "0", left: "0", right: "0", height: "3px", zIndex: "80", background: "transparent" });
      fill = el("span", "pa-progress-fill");
      fill.id = "pa-progress-fill";
      inline(fill, { display: "block", height: "100%", width: "0%", background: "#d97757" });
      bar.appendChild(fill);
      document.body.appendChild(bar);
    }
    if (!fill || !fill.style) return;
    var frame = null;
    function update() {
      frame = null;
      var doc = document.documentElement || document.body || {};
      var top = window.pageYOffset || doc.scrollTop || 0;
      var height = Math.max(1, (doc.scrollHeight || 0) - (window.innerHeight || 0));
      fill.style.width = Math.min(100, Math.max(0, (top / height) * 100)).toFixed(2) + "%";
      if (bar && bar.classList) bar.classList.toggle("is-scrolled", top > 4);
    }
    function request() {
      if (frame !== null) return;
      if (typeof window.requestAnimationFrame === "function") frame = window.requestAnimationFrame(update);
      else update();
    }
    on(window, "scroll", request, { passive: true });
    on(window, "resize", request);
    update();
  }

  /* --------------------- 5. Model details --------------------- */
  var MODELS = {
    "fable-5-2": {
      name: "Fable 5.2",
      tagline: "Next generation intelligence for long-running agents",
      uses: "Multi-day autonomous projects; expert-level work for frontier research.",
      pricing: "Prompt caching: Read $0.20 / MTok, Write $10 / MTok. Input $8 / MTok, Output $40 / MTok."
    },
    "opus-5-5": {
      name: "Opus 5.5",
      tagline: "Daily driver for agentic coding and enterprise work",
      uses: "Long-horizon coding and large migrations; multi-step agents across enterprise tools and data.",
      pricing: "Prompt caching: Read $0.20 / MTok, Write $5 / MTok. Input $4 / MTok, Output $20 / MTok."
    },
    "sonnet-5-5": {
      name: "Sonnet 5.5",
      tagline: "High-performance model for coding and agents",
      uses: "Everyday coding and developer loops; customer-facing agents and multi-tool workflows at scale.",
      pricing: "Prompt caching: Read $0.10 / MTok, Write $2.50 / MTok. Input $2 / MTok, Output $10 / MTok."
    },
    "haiku-5-5": {
      name: "Haiku 5.5",
      tagline: "Fastest, most cost-effective model",
      uses: "Real-time, latency-sensitive product experiences; sub-agents inside larger multi-model systems.",
      pricing: "Prompt caching ≤100K: Read $0.01 / MTok, Write $0.125 / MTok; >100K: Read $0.05 / MTok, Write $0.625 / MTok. Input ≤100K $0.10 / MTok, >100K $0.50 / MTok. Output ≤100K $0.50 / MTok, >100K $2.50 / MTok."
    }
  };
  var MODEL_ALIASES = {
    fable: "fable-5-2", "fable-5": "fable-5-2", "fable52": "fable-5-2",
    opus: "opus-5-5", "opus-5": "opus-5-5", "opus55": "opus-5-5",
    sonnet: "sonnet-5-5", "sonnet-5": "sonnet-5-5", "sonnet55": "sonnet-5-5",
    haiku: "haiku-5-5", "haiku-5": "haiku-5-5", "haiku55": "haiku-5-5"
  };
  /* Legacy numbers from the previous page resolve to the new families. */
  MODEL_ALIASES["opus-4-6"] = "opus-5-5";
  MODEL_ALIASES["sonnet-4-5"] = "sonnet-5-5";
  MODEL_ALIASES["haiku-4-5"] = "haiku-5-5";

  function lookupModel(value) {
    var key = norm(value).replace(/^explore-/, "");
    if (MODELS[key]) return MODELS[key];
    if (MODEL_ALIASES[key]) return MODELS[MODEL_ALIASES[key]];
    var match = Object.keys(MODEL_ALIASES).filter(function (alias) { return key.indexOf(alias) === 0; })[0];
    return match ? MODELS[MODEL_ALIASES[match]] : null;
  }

  function initModels() {
    var buttons = allOf([
      "[data-pa-model-detail]", "[data-pa-model] button", ".pa-model-card button",
      ".pa-model-card [role='button']", "[data-pa-model-link]"
    ]);
    controlsMatching(document, /^explore (fable|opus|sonnet|haiku)/i).forEach(function (node) {
      if (buttons.indexOf(node) === -1) buttons.push(node);
    });
    if (!buttons.length) return;
    buttons.forEach(function (button) {
      on(button, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var raw = button.getAttribute("data-pa-model-detail") ||
          button.getAttribute("data-pa-model-link") || "";
        var card = closest(button, "[data-pa-model], .pa-model-card");
        var cardName = card ? nodeText(firstOf(".pa-model-name, h3, h2", card)) : "";
        var data = lookupModel(raw) || lookupModel(cardName) || lookupModel(nodeText(button));
        if (!data) {
          showToast("See the Models section for KEEL pricing.");
          return;
        }
        modalBridge.openInfo({
          title: data.name,
          subtitle: data.tagline,
          blocks: [
            { label: "Built for", text: data.uses },
            { label: "Pricing", text: data.pricing },
            { label: "Batch", text: "Save 50% with batch processing. All rates are per million tokens (MTok)." }
          ]
        }, button);
      });
    });
  }

  /* --------------------- 6. Batch-processing toggle --------------------- */
  function initBatchToggle() {
    var candidates = allOf([
      "[data-pa-batch-toggle]", "[data-pa-toggle]", "#pa-batch-toggle",
      ".pa-batch-toggle", ".pa-toggle", '[role="switch"]', 'input[type="checkbox"]'
    ]);
    var toggle = candidates.filter(function (node) {
      var context = closest(node, "[data-pa-batch], .pa-batch, .pa-batch-banner, [class*='batch']") || node.parentNode;
      return /batch/i.test(String(node.getAttribute("aria-label") || "") + " " +
        nodeText(node) + " " + String(node.getAttribute("data-pa-batch-toggle") || "") +
        " " + (context ? nodeText(context).slice(0, 220) : ""));
    })[0] || null;
    if (!toggle) return;

    var banner = closest(toggle, "[data-pa-batch], .pa-batch, .pa-batch-banner, [class*='batch']") ||
      firstOf(["[data-pa-batch]", ".pa-batch-banner", ".pa-batch", "#pa-batch"]) ||
      elementsMatching("section p, section div, aside", /save 50%|batch processing/i, document.body)
        .filter(function (node) { return nodeText(node).length < 240; })[0] || null;

    var explicitFalse = toggle.getAttribute("aria-checked") === "false" ||
      toggle.getAttribute("data-state") === "off" ||
      (toggle.type === "checkbox" && !toggle.checked) ||
      !!(toggle.classList && toggle.classList.contains("is-off"));
    var state = !explicitFalse;

    function replaceSentence(rootNode, replacement) {
      if (!rootNode) return false;
      var walker = document.createTreeWalker(rootNode, 4 /* NodeFilter.SHOW_TEXT */, null, false);
      var node = walker.nextNode();
      while (node) {
        if (/save 50%[^.]*\.|batch processing is off[^.]*\./i.test(node.nodeValue || "")) {
          node.nodeValue = String(node.nodeValue).replace(
            /save 50%[^.]*\.|batch processing is off[^.]*\./i, replacement);
          return true;
        }
        node = walker.nextNode();
      }
      return false;
    }

    function render() {
      var copy = state ? "Batch processing is on — eligible requests save 50%."
        : "Save 50% with batch processing.";
      var offCopy = firstOf(["#pa-banner-off", "[data-pa-banner-off]"], banner || document);
      var onCopy = firstOf(["#pa-banner-on", "[data-pa-banner-on]"], banner || document);
      if (offCopy && onCopy) {
        setHidden(offCopy, state);
        setHidden(onCopy, !state);
      } else {
        var target = firstOf(["[data-pa-batch-copy]", ".pa-batch-copy", ".pa-batch-text"], banner) || banner;
        if (!replaceSentence(target, copy) && banner) {
          var added = qs("[data-pa-ui-batch-copy]", banner);
          if (!added) {
            added = el("span", "pa-batch-copy", copy);
            added.setAttribute("data-pa-ui-batch-copy", "");
            banner.insertBefore(added, banner.firstChild);
          } else added.textContent = copy;
        }
      }
      toggle.setAttribute("aria-checked", state ? "true" : "false");
      toggle.setAttribute("data-state", state ? "on" : "off");
      if (toggle.type === "checkbox") toggle.checked = state;
      if (toggle.classList) {
        toggle.classList.toggle("is-on", state);
        toggle.classList.toggle("is-off", !state);
      }
      if (banner) banner.setAttribute("data-batch-state", state ? "on" : "off");
    }

    function flip() {
      state = !state;
      render();
      showToast(state
        ? "Batch processing on — save 50% on async requests."
        : "Batch processing off — standard token prices apply.");
    }

    on(toggle, "click", flip);
    on(toggle, "keydown", function (event) {
      if (!event || (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar")) return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      flip();
    });
    if (!toggle.hasAttribute("role") && toggle.tagName !== "INPUT") toggle.setAttribute("role", "switch");
    render();
  }

  /* --------------------- 7. Managed Agents --------------------- */
  function initManagedAgents() {
    var managed = firstOf(["#pa-managed", "[data-pa-managed]", ".pa-managed", ".pa-agents"]) || null;
    if (managed && !/managed agent/i.test(nodeText(managed))) {
      var better = elementsMatching("section", /managed agents/i, document.body)[0];
      if (better) managed = better;
    }
    var scope = managed || document;
    var play = firstOf(["[data-pa-play]", "[data-pa-video]", ".pa-play", "button[aria-label*='lay']"], scope) ||
      controlsMatching(scope, /play|watch preview|see it in action/i)[0] || null;
    if (play) {
      on(play, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        modalBridge.openMode(play, "player");
      });
    }
    var seeFeatures = firstOf(["[data-pa-features]", ".pa-see-features", "#pa-see-features"], scope) ||
      controlsMatching(scope, /^see features/i)[0] || null;
    if (seeFeatures) {
      on(seeFeatures, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var target = firstOf(["#pa-agent-features", "#pa-features", ".pa-feature-rows",
          ".pa-agent-rows", "[data-pa-features-list]", ".pa-feature-row"]) ||
          elementsMatching("section, div", /security by design/i, document.body)
            .filter(function (node) { return nodeText(node).length < 1200; }).slice(-1)[0] || null;
        scrollTo(target);
        if (target) showToast("Jumped to the Managed Agents features.");
      });
    }
  }

  /* ----------- 8. Info pills, resource cards, dead links ----------- */
  function initInfoLinks() {
    qsa("[data-pa-info]").forEach(function (node) {
      on(node, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        modalBridge.openInfo(infoForText(node.getAttribute("data-pa-info")), node);
      });
    });

    var pattern = /^(learn more|read more|read documentation|explore mcp|explore partners|explore skills|explore memory|explore [a-z ]+|documentation|overview)$/i;
    var buttons = qsa("button, [role='button']").filter(function (node) {
      if (node.hasAttribute("data-pa-modal") || node.hasAttribute("data-pa-copy") ||
          node.hasAttribute("data-pa-close") || node.hasAttribute("data-pa-model-detail") ||
          node.hasAttribute("data-pa-quote-dot") || node.hasAttribute("data-pa-nav") ||
          node.hasAttribute("data-pa-panel-toggle") || node.hasAttribute("data-pa-ask") ||
          node.hasAttribute("data-pa-markdown") || node.hasAttribute("data-pa-batch-toggle") ||
          node.hasAttribute("data-pa-play") || node.hasAttribute("data-pa-features")) return false;
      if (node.type === "submit" || node.getAttribute("role") === "switch") return false;
      if (/^explore (fable|opus|sonnet|haiku)/i.test(nodeText(node))) return false;
      if (/^explore here$/i.test(nodeText(node))) return false;
      if (closest(node, "#pa-explore, .pa-explore, [data-pa-explore], [data-pa-panel]")) return false;
      if (/explore-toggle/.test(String(node.className || ""))) return false;
      return pattern.test(nodeText(node));
    });
    buttons.forEach(function (button) {
      on(button, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        modalBridge.openInfo(infoForText(nodeText(button)), button);
      });
    });

    /* Resource card pills with placeholder destinations. */
    qsa("[data-pa-resource], .pa-resource-card, .pa-resource").forEach(function (card) {
      qsa("a[href='#'], a:not([href]), button", card).forEach(function (pill) {
        if (pill.hasAttribute("data-pa-modal") || pill.hasAttribute("data-pa-copy")) return;
        on(pill, "click", function (event) {
          if (event && typeof event.preventDefault === "function") event.preventDefault();
          var heading = firstOf("h2, h3, h4, .pa-resource-title", card);
          modalBridge.openInfo({
            title: nodeText(heading) || nodeText(card).slice(0, 70) || "KEEL resource",
            subtitle: nodeText(pill) || "Blog · Docs · Cookbook",
            blocks: INFO_COPY.resource.blocks
          }, pill);
        });
      });
    });

    /* Any remaining placeholder anchor does something useful. */
    qsa("a[href='#']").forEach(function (link) {
      if (link.hasAttribute("data-pa-modal") || link.hasAttribute("data-pa-copy") ||
          link.hasAttribute("data-pa-close") || link.hasAttribute("data-pa-info") ||
          link.hasAttribute("data-pa-ask") || link.hasAttribute("data-pa-markdown") ||
          link.hasAttribute("data-pa-panel-toggle") ||
          closest(link, "#pa-explore, .pa-explore, [data-pa-explore], [data-pa-panel]")) return;
      on(link, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var text = nodeText(link);
        if (/contact|sales/i.test(text)) modalBridge.openMode(link, "contact");
        else if (/start building|try keel|get started|sign in|login/i.test(text)) modalBridge.openMode(link, "signup");
        else modalBridge.openInfo(infoForText(text), link);
      });
    });
  }

  /* --------------------- 9. Testimonials --------------------- */
  function initTestimonials() {
    var wrap = firstOf([
      "#pa-quotes", "#pa-testimonials", ".pa-quotes", ".pa-testimonials", "[data-pa-quotes]"
    ]);
    var slides = allOf([
      "[data-pa-quote-slide]", ".pa-quote-slide", ".pa-quote-card", ".pa-testimonial", "[data-pa-slide]"
    ], wrap || document);
    if (!slides.length && wrap) slides = qsa("article, blockquote", wrap);
    if (!slides.length) return;

    var dotsWrap = firstOf(["#pa-quote-dots", ".pa-quote-dots", "[data-pa-dots]"], wrap || document) ||
      (wrap ? wrap.parentNode : null);
    if (!dotsWrap) return;
    var dots = qsa("[data-pa-quote-dot], .pa-quote-dot, [data-pa-dot]", dotsWrap);
    if (!dots.length) {
      dots = qsa("button", dotsWrap).filter(function (node) {
        var meta = String(node.className || "") + " " + String(node.getAttribute("aria-label") || "");
        return /dot/i.test(meta) || (nodeText(node) === "" && !/prev|next|arrow|close/i.test(meta));
      });
    }
    var pageMode = slides.length >= dots.length * 3;
    var total = Math.max(dots.length, pageMode ? Math.ceil(slides.length / 3) : 1, 1);
    if (!dots.length) {
      for (var i = 0; i < total; i += 1) {
        var dot = el("button", "pa-quote-dot");
        dot.type = "button";
        dot.setAttribute("data-pa-quote-dot", String(i));
        dot.setAttribute("aria-label", "Go to testimonial " + (i + 1));
        dotsWrap.appendChild(dot);
        dots.push(dot);
      }
    }
    total = dots.length;
    var index = 0;
    var count = firstOf(["#pa-quote-count", ".pa-quote-count", "[data-pa-quote-count]"], document);
    var prev = firstOf(["#pa-quote-prev", "[data-pa-quote-prev]", ".pa-quote-arrow[data-dir='prev']"]) ||
      controlsMatching(document, /^←|^prev|^previous/i)[0] || null;
    var next = firstOf(["#pa-quote-next", "[data-pa-quote-next]", ".pa-quote-arrow[data-dir='next']"]) ||
      controlsMatching(document, /^→|^next/i)[0] || null;

    function visibleIndexes() {
      var out = [];
      for (var offset = 0; offset < 3; offset += 1) {
        var position = pageMode ? index * 3 + offset : index + offset;
        out.push(((position % slides.length) + slides.length) % slides.length);
      }
      return out;
    }

    function render() {
      var visible = visibleIndexes();
      slides.forEach(function (slide, position) {
        setHidden(slide, visible.indexOf(position) === -1);
        if (slide.classList) slide.classList.toggle("is-active", visible.indexOf(position) !== -1);
      });
      dots.forEach(function (dot, position) {
        var active = position === index;
        if (dot.classList) dot.classList.toggle("is-active", active);
        dot.setAttribute("aria-current", active ? "true" : "false");
      });
      if (count) count.textContent = (index + 1) + " / " + total;
    }

    function go(nextIndex) {
      index = ((nextIndex % total) + total) % total;
      render();
    }

    dots.forEach(function (dot, position) {
      on(dot, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        go(position);
      });
    });
    on(prev, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      go(index - 1);
    });
    on(next, "click", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      go(index + 1);
    });
    var keyScope = wrap || dotsWrap;
    on(keyScope, "keydown", function (event) {
      if (!event) return;
      if (event.key === "ArrowLeft") {
        if (event.preventDefault) event.preventDefault();
        go(index - 1);
      } else if (event.key === "ArrowRight") {
        if (event.preventDefault) event.preventDefault();
        go(index + 1);
      }
    });

    var timer = null;
    function start() {
      if (timer || reducedMotion() || total < 2) return;
      timer = setInterval(function () { go(index + 1); }, 6500);
    }
    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
    }
    on(wrap, "mouseenter", stop);
    on(wrap, "mouseleave", start);
    on(wrap, "focusin", stop);
    on(wrap, "focusout", start);
    render();
    start();
  }

  /* --------------------- 10. Newsletter --------------------- */
  function initNewsletter() {
    var forms = qsa("form[data-pa-newsletter], .pa-newsletter-form, form").filter(function (form) {
      if (form.id === "pa-auth-form" || form.id === "pa-contact-form") return false;
      if (form.hasAttribute("data-pa-auth") || form.hasAttribute("data-pa-contact")) return false;
      var input = qs('input[type="email"]', form);
      var context = nodeText(closest(form, "section, aside") || form);
      return !!input && (/newsletter|developer|updates|subscrib/i.test(context + " " + nodeText(form)) ||
        /newsletter/i.test(String(form.className || "")));
    });
    forms.forEach(function (form) {
      form.noValidate = true;
      var input = qs('input[type="email"]', form);
      on(form, "submit", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var value = String(input ? input.value || "" : "").trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value)) {
          if (input) {
            input.setAttribute("aria-invalid", "true");
            focusNode(input);
          }
          showToast("Enter a valid email address to subscribe.");
          return;
        }
        if (input) input.removeAttribute("aria-invalid");
        if (typeof form.reset === "function") form.reset();
        showToast("You're subscribed to the developer newsletter (demo).");
      });
    });
  }

  /* --------------------- 11. Footer search --------------------- */
  function initFooterSearch() {
    var form = firstOf(["#pa-footer-search", ".pa-footer-search", "[data-pa-footer-search]"]);
    var input = firstOf(["#pa-footer-q", "#pa-footer-search-input", ".pa-footer-search input", 'input[type="search"]'], form) ||
      qs('input[type="search"]');
    var footer = firstOf(["footer", "#pa-footer", ".pa-footer"]);
    var results = firstOf(["#pa-search-results", ".pa-search-results", "[data-pa-search-results]"], footer || document);
    if (!form && !input) return;
    if (!results && document.body) {
      results = el("div", "pa-search-results");
      results.id = "pa-search-results";
      results.setAttribute("role", "status");
      results.setAttribute("aria-live", "polite");
      inline(results, { marginTop: "12px", fontSize: "13px" });
      (form && form.parentNode) ? form.parentNode.appendChild(results) : document.body.appendChild(results);
    }
    if (!results) return;
    setHidden(results, true);

    var links = qsa(".pa-footer-col a, .pa-footer-link, footer a[href]", footer || document)
      .filter(function (link) {
        return !closest(link, "form") && !link.hasAttribute("data-pa-modal") &&
          !/social|preferred sources/i.test(nodeText(link));
      });

    function renderResults() {
      var query = String(input ? input.value || "" : "").replace(/\s+/g, " ").trim();
      while (results.firstChild) results.removeChild(results.firstChild);
      if (!query) { setHidden(results, true); results.textContent = ""; return; }
      var needle = query.toLowerCase();
      var matches = links.filter(function (link) {
        return nodeText(link).toLowerCase().indexOf(needle) !== -1;
      });
      setHidden(results, false);
      var summary = el("p", "pa-search-summary", matches.length
        ? matches.length + " matching link" + (matches.length === 1 ? "" : "s") + " for “" + query + "”."
        : "No footer links match “" + query + "”. Try “pricing”, “privacy” or “code”.");
      results.appendChild(summary);
      matches.forEach(function (link) {
        var href = String(link.getAttribute("href") || "#");
        var result = href && href !== "#" && href.charAt(0) !== "#"
          ? el("a", "pa-search-result", nodeText(link)) : el("button", "pa-search-result", nodeText(link));
        if (result.tagName === "A") result.href = href;
        else result.type = "button";
        inline(result, {
          display: "block", padding: "6px 0", background: "transparent", border: "0",
          color: "inherit", textAlign: "left", cursor: "pointer", font: "inherit"
        });
        on(result, "click", function (event) {
          if (result.tagName === "BUTTON") {
            if (event && typeof event.preventDefault === "function") event.preventDefault();
            modalBridge.openInfo(infoForText(nodeText(link)), result);
            return;
          }
          if (href.charAt(0) === "#" && event && typeof event.preventDefault === "function") {
            event.preventDefault();
            scrollTo(qs(href));
          }
        });
        results.appendChild(result);
      });
    }

    on(form, "submit", function (event) {
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      renderResults();
    });
    on(input, "input", renderResults);
    on(input, "change", renderResults);
    on(input, "search", renderResults);
    var submitButton = firstOf("button[type='submit']", form);
    if (submitButton) on(submitButton, "click", renderResults);
    closers.footer = function () {
      if (input) input.value = "";
      renderResults();
    };
  }

  /* --------------------- 12. Copy buttons --------------------- */
  function initCopyButtons() {
    var buttons = allOf(["[data-pa-copy]", ".pa-copy", "[data-copy]"]);
    buttons.forEach(function (button) {
      on(button, "click", function (event) {
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        var id = button.getAttribute("data-pa-copy") || button.getAttribute("data-copy") || "";
        var source = id ? document.getElementById(id) : null;
        if (!source) {
          var pane = closest(button, ".pa-window, .pa-pane, .pa-code-window, .pa-terminal-card, pre");
          source = pane ? firstOf("pre, code", pane) || pane : null;
        }
        var text = source ? (source.textContent || source.value || "") : "";
        copyText(text, "Copied " + (id ? id.replace(/^pa-/, "") : "content") + " to clipboard");
      });
    });
  }

  /* --------------------- 13. In-page anchors --------------------- */
  function initAnchorSmoothing() {
    qsa('a[href^="#"]').forEach(function (link) {
      var href = String(link.getAttribute("href") || "");
      if (href === "#" || href.length < 2) return;
      if (link.hasAttribute("data-pa-modal") || link.hasAttribute("data-pa-copy") ||
          link.hasAttribute("data-pa-quote-dot") || link.hasAttribute("data-pa-nav")) return;
      on(link, "click", function (event) {
        var target = qs(href);
        if (!target) return;
        if (event && typeof event.preventDefault === "function") event.preventDefault();
        scrollTo(target);
      });
    });
  }

  /* --------------------- Global Escape --------------------- */
  function initGlobalKeys() {
    on(document, "keydown", function (event) {
      if (!event || (event.key !== "Escape" && event.key !== "Esc")) return;
      var engine = getModalEngine();
      if (engine) {
        var root = firstOf(["#pa-modal", "#pa-auth-modal", "[data-pa-modal-root]", ".pa-modal", '[role="dialog"]']);
        if (root && !root.hidden) {
          if (typeof event.preventDefault === "function") event.preventDefault();
          engine.close();
          return;
        }
      }
      if (closers.nav) closers.nav();
      if (closers.mobile) closers.mobile();
      if (closers.explore) closers.explore();
      if (closers.footer) closers.footer();
    });
  }

  /* ----------------------------- Boot ----------------------------- */
  function init() {
    safe(ensureToast);
    safe(initProgress);
    safe(initModalEngineBoot);
    safe(initMegaNav);
    safe(initMobileMenu);
    safe(initExplorePanel);
    safe(initModels);
    safe(initBatchToggle);
    safe(initManagedAgents);
    safe(initInfoLinks);
    safe(initTestimonials);
    safe(initNewsletter);
    safe(initFooterSearch);
    safe(initCopyButtons);
    safe(initAnchorSmoothing);
    safe(initGlobalKeys);
  }

  function initModalEngineBoot() {
    var engine = getModalEngine();
    if (engine) engine.close();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

/* KEEL editorial article page — all interactivity.
   Plain ES5/ES2017-compatible JavaScript. No modules, no dependencies,
   no network calls. IIFE-wrapped and defer-loaded. Every DOM query is
   guarded, so this file is safe to load on any page. */
(function () {
  "use strict";

  /* Helpers — all defensive: missing nodes are simply ignored. */
  function byId(id) { return document.getElementById(id); }
  function select(sel, root) {
    try { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    catch (e) { return []; }
  }
  function one(sel, root) {
    try { return (root || document).querySelector(sel); } catch (e) { return null; }
  }
  function hasClass(n, c) { return !!(n && n.classList && n.classList.contains(c)); }
  function addClass(n, c) { if (n && n.classList) n.classList.add(c); }
  function removeClass(n, c) { if (n && n.classList) n.classList.remove(c); }
  function tag(n) { return n && n.tagName ? String(n.tagName).toUpperCase() : ""; }
  function text(n) { return n && n.textContent ? String(n.textContent) : ""; }
  function containsNode(parent, child) {
    return !!(parent && child && child.nodeType && parent.contains && parent.contains(child));
  }
  function closest(n, sel) {
    var cur = n;
    while (cur && cur.nodeType === 1) {
      if (cur.matches) { try { if (cur.matches(sel)) return cur; } catch (e) {} }
      cur = cur.parentNode;
    }
    return null;
  }
  function isEscape(e) { return !!e && (e.key === "Escape" || e.key === "Esc" || e.keyCode === 27); }
  function scrollBehavior() {
    var reduce = false;
    try { reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) {}
    return reduce ? "auto" : "smooth";
  }
  function scrollTop() { return window.pageYOffset || document.documentElement.scrollTop || 0; }
  function onFrame(fn) {
    var ticking = false;
    return function () {
      if (ticking) return;
      ticking = true;
      var run = function () { ticking = false; fn(); };
      if (window.requestAnimationFrame) window.requestAnimationFrame(run); else run();
    };
  }
  function escapeHtml(v) {
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function escapeRe(v) { return String(v).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function highlight(v, q) {
    var safe = escapeHtml(v);
    if (!q) return safe;
    try { return safe.replace(new RegExp("(" + escapeRe(escapeHtml(q)) + ")", "ig"), "<mark>$1</mark>"); }
    catch (e) { return safe; }
  }
  function truncate(v, max) {
    var s = String(v || "").replace(/\s+/g, " ").trim();
    return s.length > max ? s.slice(0, max - 1).trim() + "…" : s;
  }
  function safeHref(href) {
    var h = String(href || "");
    if (!h) return "#";
    if (h.charAt(0) === "#" || h.charAt(0) === "/") return h;
    try {
      if (typeof URL !== "undefined") {
        var u = new URL(h, window.location.href);
        if (u.protocol === "http:" || u.protocol === "https:") return h;
      }
    } catch (e) {}
    return "#";
  }

  /* 1. Mega-nav dropdowns — one open at a time; hover + click + Escape. */
  function initMegaNav() {
    var groups = select(".ks-nav-group");
    if (!groups.length) return;
    var openTimer = null, closeTimer = null;

    function clearTimers() {
      if (openTimer) { clearTimeout(openTimer); openTimer = null; }
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
    }
    function isOpen(g) {
      var mega = one(".ks-mega", g);
      return !!mega && !mega.hidden;
    }
    function closeGroup(g) {
      if (!g) return;
      var mega = one(".ks-mega", g), btn = one(".ks-nav-btn", g);
      if (mega) mega.hidden = true;
      if (btn) btn.setAttribute("aria-expanded", "false");
      removeClass(g, "is-active"); removeClass(btn, "is-active");
    }
    function closeAll(except) {
      groups.forEach(function (g) { if (g !== except) closeGroup(g); });
    }
    function openGroup(g) {
      closeAll(g);
      var mega = one(".ks-mega", g), btn = one(".ks-nav-btn", g);
      if (mega) mega.hidden = false;
      if (btn) btn.setAttribute("aria-expanded", "true");
      addClass(g, "is-active"); // CSS rotates .ks-chevron from this / aria-expanded
      addClass(btn, "is-active");
    }

    groups.forEach(function (g) {
      var btn = one(".ks-nav-btn", g);
      if (btn) btn.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation(); clearTimers();
        if (isOpen(g)) closeGroup(g); else openGroup(g);
      });
      g.addEventListener("mouseenter", function () {
        if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
        openTimer = setTimeout(function () { openTimer = null; openGroup(g); }, 120);
      });
      g.addEventListener("mouseleave", function () {
        if (openTimer) { clearTimeout(openTimer); openTimer = null; }
        closeTimer = setTimeout(function () { closeTimer = null; closeGroup(g); }, 180);
      });
    });

    document.addEventListener("click", function (e) {
      var target = e.target, inside = false;
      groups.forEach(function (g) { if (containsNode(g, target)) inside = true; });
      if (!inside) closeAll(null);
      else if (target && target.nodeType === 1 && closest(target, ".ks-mega a")) closeAll(null);
    });
    document.addEventListener("keydown", function (e) { if (isEscape(e)) closeAll(null); });
  }

  /* 2. Mobile menu. */
  function initMobileMenu() {
    var toggle = byId("ks-menu-toggle"), menu = byId("ks-mobile-menu");
    if (!toggle || !menu) return;
    function setMenu(open) {
      menu.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) addClass(menu, "is-visible"); else removeClass(menu, "is-visible");
    }
    toggle.setAttribute("aria-expanded", menu.hidden ? "false" : "true"); // sync initial state
    toggle.addEventListener("click", function (e) { e.stopPropagation(); setMenu(menu.hidden); });
    document.addEventListener("click", function (e) {
      if (!menu.hidden && !containsNode(menu, e.target) && !containsNode(toggle, e.target)) setMenu(false);
    });
    document.addEventListener("keydown", function (e) { if (isEscape(e) && !menu.hidden) setMenu(false); });
    select("a", menu).forEach(function (link) {
      link.addEventListener("click", function () { setMenu(false); });
    });
    window.addEventListener("resize", onFrame(function () {
      if (window.innerWidth > 900 && !menu.hidden) setMenu(false);
    }), { passive: true });
  }

  /* 3. Search overlay — in-memory index built from visible page text. */
  function initSearch() {
    var openBtn = byId("ks-search-open"), overlay = byId("ks-search");
    if (!openBtn || !overlay) return;
    var form = byId("ks-search-form"), input = byId("ks-search-input");
    var closeBtn = byId("ks-search-close"), results = byId("ks-search-results");
    var lastFocus = null, firstHref = null, index = null;

    var STATIC_PAGES = [
      { title: "Keel overview", href: "/product-overview", snippet: "What Keel is and how the pieces fit together." },
      { title: "Download", href: "/download", snippet: "Get the Keel desktop app for Windows, macOS and Linux." },
      { title: "Requirements", href: "/requirements", snippet: "Supported platforms and system requirements." },
      { title: "Privacy", href: "/privacy", snippet: "How Keel handles your data locally and in the cloud." },
      { title: "Roadmap", href: "/roadmap", snippet: "What is shipping next and what is planned." },
      { title: "Keel Duet", href: "/product/keel-duet", snippet: "Pair sessions and keep work in sync across devices." },
      { title: "Keel Code", href: "/product/keel-code", snippet: "The subagent that carries context into your codebase." }
    ];

    function anchorFor(node) {
      if (node && node.id) return "#" + node.id;
      var p = node ? node.parentNode : null;
      while (p && p.nodeType === 1 && p !== document.body) {
        if (p.id) return "#" + p.id;
        p = p.parentNode;
      }
      return "#";
    }
    function snippetFor(h) {
      var sib = h.nextElementSibling;
      while (sib && tag(sib) !== "P") sib = sib.nextElementSibling;
      if (sib) return truncate(text(sib), 140);
      var parent = h.parentNode, p = parent ? one("p", parent) : null;
      return truncate(p ? text(p) : "", 140);
    }
    function addHeading(items, h, href) {
      var title = truncate(text(h), 90);
      if (title) items.push({ title: title, href: href || anchorFor(h), snippet: snippetFor(h) });
    }
    function buildIndex() {
      var items = STATIC_PAGES.slice(), prose = one(".ks-prose");
      if (prose) select("h2, h3", prose).forEach(function (h) { addHeading(items, h, anchorFor(h)); });
      select(".ks-related-card h3").forEach(function (h) {
        var card = closest(h, ".ks-related-card");
        var link = card && tag(card) === "A" ? card : (card ? one("a", card) : null);
        addHeading(items, h, link ? link.getAttribute("href") : anchorFor(h));
      });
      index = items;
    }

    function render(query) {
      if (!results) return;
      if (!index) buildIndex();
      var q = String(query || "").trim(), lower = q.toLowerCase();
      var terms = lower ? lower.split(/\s+/) : [], matches = [], i, j, ok;
      for (i = 0; i < (index || []).length && matches.length < 8; i++) {
        var item = index[i];
        if (!lower) { matches.push(item); continue; }
        var hay = (item.title + " " + item.snippet + " " + item.href).toLowerCase();
        ok = true;
        for (j = 0; j < terms.length; j++) {
          if (hay.indexOf(terms[j]) === -1) { ok = false; break; }
        }
        if (ok) matches.push(item);
      }
      firstHref = null;
      results.innerHTML = "";
      if (!matches.length) {
        var empty = document.createElement("div");
        empty.className = "ks-search-result is-empty";
        empty.textContent = q ? 'No matches for “' + q + '”. Try a different term.' : "Nothing to search yet.";
        results.appendChild(empty);
        return;
      }
      matches.forEach(function (entry) {
        var a = document.createElement("a");
        a.className = "ks-search-result";
        a.href = safeHref(entry.href);
        a.innerHTML = '<span class="ks-search-result-title">' + highlight(entry.title, q) +
          '</span><span class="ks-search-result-snippet">' + highlight(entry.snippet, q) + "</span>";
        results.appendChild(a);
      });
      var first = one("a.ks-search-result", results);
      firstHref = first ? first.getAttribute("href") : null;
    }

    function open() {
      if (!overlay.hidden) return;
      lastFocus = document.activeElement;
      overlay.hidden = false;
      addClass(overlay, "is-visible");
      openBtn.setAttribute("aria-expanded", "true");
      if (input) input.value = "";
      render("");
      if (input) { try { input.focus(); } catch (e) {} }
    }
    function close() {
      if (overlay.hidden) return;
      overlay.hidden = true;
      removeClass(overlay, "is-visible");
      openBtn.setAttribute("aria-expanded", "false");
      if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
    }

    openBtn.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      if (overlay.hidden) open(); else close();
    });
    if (closeBtn) closeBtn.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation(); close();
    });
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); }); // backdrop
    document.addEventListener("keydown", function (e) { if (isEscape(e) && !overlay.hidden) close(); });
    if (form) form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (firstHref) { close(); window.location.href = firstHref; }
    });
    if (input) {
      var debounce = null;
      input.addEventListener("input", function () {
        if (debounce) clearTimeout(debounce);
        debounce = setTimeout(function () { debounce = null; render(input.value); }, 80);
      });
    }
    if (results) results.addEventListener("click", function (e) {
      if (e.target && e.target.nodeType === 1 && closest(e.target, "a.ks-search-result")) close();
    });
  }

  /* 4. Table-of-contents scroll-spy. */
  function initToc() {
    var toc = byId("ks-toc"), prose = one(".ks-prose");
    if (!toc || !prose) return;
    var entries = [];
    select("a", toc).forEach(function (link) {
      var href = link.getAttribute("href") || "";
      if (href.charAt(0) !== "#" || href.length < 2) return;
      var id = href.slice(1);
      try { id = decodeURIComponent(id); } catch (e) {}
      var section = byId(id);
      if (section && containsNode(prose, section)) entries.push({ id: id, section: section, link: link });
    });
    if (!entries.length) return;

    function update() {
      var boundary = scrollTop() + 120, active = null, doc = document.documentElement;
      entries.forEach(function (entry) {
        if (entry.section.getBoundingClientRect().top + scrollTop() <= boundary + 1) active = entry;
      });
      if (window.innerHeight + scrollTop() >= doc.scrollHeight - 2) active = entries[entries.length - 1];
      entries.forEach(function (entry) {
        if (entry === active) {
          addClass(entry.link, "is-active");
          entry.link.setAttribute("aria-current", "location");
        } else {
          removeClass(entry.link, "is-active");
          entry.link.removeAttribute("aria-current");
        }
      });
    }
    entries.forEach(function (entry) {
      entry.link.addEventListener("click", function (e) {
        e.preventDefault();
        try { entry.section.scrollIntoView({ behavior: scrollBehavior(), block: "start" }); }
        catch (err) { entry.section.scrollIntoView(); }
        if (window.history && window.history.replaceState) window.history.replaceState(null, "", "#" + entry.id);
        update();
      });
    });
    var onScroll = onFrame(update);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    window.addEventListener("hashchange", update);
    window.addEventListener("load", update);
    update(); // initialize from location.hash / current scroll
  }

  /* 5. Copy buttons inside pre.ks-code. */
  function copyText(value, done) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = value;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-9999px";
      document.body.appendChild(ta);
      var ok = false;
      try { ta.select(); ok = !!document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      done(ok);
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(function () { done(true); }, fallback);
        return;
      }
    } catch (e) {}
    fallback();
  }
  function initCopy() {
    select("button.ks-copy").forEach(function (btn) {
      var pre = closest(btn, "pre"), code = pre ? one("code", pre) : null;
      var label = btn.getAttribute("data-label") || text(btn) || "Copy", resetTimer = null;
      btn.addEventListener("click", function () {
        copyText(code ? text(code) : "", function (ok) {
          if (ok) { btn.textContent = "Copied!"; addClass(btn, "copied"); }
          else {
            btn.textContent = "Select text"; removeClass(btn, "copied");
            if (code) {
              try {
                var range = document.createRange();
                range.selectNodeContents(code);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
              } catch (e) {}
            }
          }
          if (resetTimer) clearTimeout(resetTimer);
          resetTimer = setTimeout(function () {
            btn.textContent = label; removeClass(btn, "copied");
          }, 1800);
        });
      });
    });
  }

  /* 6. Newsletter form — local-only, no network calls. */
  function initNewsletter() {
    var form = byId("ks-newsletter"), email = byId("ks-email"), msg = byId("ks-news-msg");
    if (!form || !email) return;
    var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    function setMessage(value, cls) {
      if (!msg) return;
      msg.textContent = value;
      removeClass(msg, "is-ok"); removeClass(msg, "is-error");
      if (cls) addClass(msg, cls);
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var value = String(email.value || "").trim();
      if (!EMAIL_RE.test(value)) { setMessage("Please enter a valid email address.", "is-error"); return; }
      setMessage("Thanks — you're on the list.", "is-ok");
      email.value = "";
      try { window.localStorage.setItem("ks_newsletter_email", value); } catch (err) {}
    });
    email.addEventListener("input", function () { setMessage("", ""); });
  }

  /* 7. Back-to-top button. */
  function initToTop() {
    var btn = byId("ks-to-top");
    if (!btn) return;
    var update = onFrame(function () {
      if (scrollTop() > 600) addClass(btn, "is-visible"); else removeClass(btn, "is-visible");
    });
    window.addEventListener("scroll", update, { passive: true });
    update();
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      try { window.scrollTo({ top: 0, behavior: scrollBehavior() }); }
      catch (err) { window.scrollTo(0, 0); }
    });
  }

  /* 8. Scrolled-header state and current year. */
  function initMisc() {
    var header = byId("ks-header");
    var updateHeader = onFrame(function () {
      if (!header) return;
      if (scrollTop() > 8) addClass(header, "is-scrolled"); else removeClass(header, "is-scrolled");
    });
    window.addEventListener("scroll", updateHeader, { passive: true });
    updateHeader();
    select("[data-year]").forEach(function (node) { node.textContent = String(new Date().getFullYear()); });
  }

  /* Boot — wrapped in DOMContentLoaded (or run immediately if already ready). */
  function init() {
    initMegaNav(); initMobileMenu(); initSearch(); initToc();
    initCopy(); initNewsletter(); initToTop(); initMisc();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}());

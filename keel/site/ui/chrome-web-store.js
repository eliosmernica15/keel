/* Keel — Chrome Web Store listing replica (/chrome-web-store).
   Dependency-free, same-origin only. All controls are wired here. */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ---------------- toast ---------------- */
  var toastEl = $("#cws-toast");
  var toastTimer = null;
  function showToast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toastEl.hidden = true; }, 2800);
  }

  /* ---------------- popovers (menus) ---------------- */
  var popovers = [
    { btn: $("#cws-store-menu-btn"), el: $("#cws-store-menu") },
    { btn: $("#cws-apps-btn"), el: $("#cws-apps-pop") },
    { btn: $("#cws-avatar-btn"), el: $("#cws-avatar-menu") }
  ].filter(function (p) { return p.btn && p.el; });

  function closePopovers(except) {
    popovers.forEach(function (p) {
      if (p === except) return;
      p.el.hidden = true;
      p.btn.setAttribute("aria-expanded", "false");
    });
  }
  popovers.forEach(function (p) {
    p.btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var willOpen = p.el.hidden;
      closePopovers(p);
      p.el.hidden = !willOpen;
      p.btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      hideTip();
    });
    p.el.addEventListener("click", function (e) { e.stopPropagation(); });
  });

  /* ---------------- ratings tooltip ---------------- */
  var tipBtn = $("#cws-ratings-info");
  var tip = $("#cws-ratings-tip");
  function showTip() {
    if (!tip || !tipBtn) return;
    tip.hidden = false;
    tipBtn.setAttribute("aria-expanded", "true");
  }
  function hideTip() {
    if (!tip || !tipBtn) return;
    tip.hidden = true;
    tipBtn.setAttribute("aria-expanded", "false");
  }
  if (tipBtn && tip) {
    tipBtn.addEventListener("mouseenter", showTip);
    tipBtn.addEventListener("mouseleave", hideTip);
    tipBtn.addEventListener("focus", showTip);
    tipBtn.addEventListener("blur", hideTip);
    tipBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (tip.hidden) showTip(); else hideTip();
    });
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    var insidePopover = false;
    popovers.forEach(function (p) { if (p.el.contains(t) || p.btn.contains(t)) insidePopover = true; });
    if (!insidePopover) closePopovers();
    if (tip && !tip.contains(t) && tipBtn && !tipBtn.contains(t)) hideTip();
  });

  $$("[data-toast]").forEach(function (btn) {
    btn.addEventListener("click", function () { showToast(btn.getAttribute("data-toast")); });
  });

  /* ---------------- tabs ---------------- */
  var tabBtns = $$(".cws-tab-item");
  var panels = {
    discover: $("#panel-discover"),
    extensions: $("#panel-extensions"),
    themes: $("#panel-themes")
  };
  function selectTab(name, focus) {
    if (!Object.prototype.hasOwnProperty.call(panels, name)) return;
    tabBtns.forEach(function (btn) {
      var active = btn.getAttribute("data-tab") === name;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.tabIndex = active ? 0 : -1;
      if (active && focus) btn.focus();
    });
    Object.keys(panels).forEach(function (key) {
      if (panels[key]) panels[key].hidden = key !== name;
    });
  }
  tabBtns.forEach(function (btn, i) {
    btn.addEventListener("click", function () { selectTab(btn.getAttribute("data-tab")); });
    btn.addEventListener("keydown", function (e) {
      var idx = -1;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") idx = (i + 1) % tabBtns.length;
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") idx = (i - 1 + tabBtns.length) % tabBtns.length;
      else if (e.key === "Home") idx = 0;
      else if (e.key === "End") idx = tabBtns.length - 1;
      if (idx >= 0) {
        e.preventDefault();
        selectTab(tabBtns[idx].getAttribute("data-tab"), true);
      }
    });
  });
  $$("[data-goto]").forEach(function (btn) {
    btn.addEventListener("click", function () { selectTab(btn.getAttribute("data-goto")); });
  });

  /* ---------------- search ---------------- */
  var searchInput = $("#cws-search-input");
  var searchBtn = $("#cws-search-btn");
  var searchClear = $("#cws-search-clear");
  var listing = $("#cws-listing");
  var noResults = $("#cws-no-results");
  var noResultsText = $("#cws-no-results-text");
  var keywords = ["keel", "chrome", "extension", "extensions", "tools", "assistant", "browser",
    "ai", "agent", "automate", "read", "click", "type", "fill", "form", "approval", "tab", "tabs"];

  function runSearch() {
    if (!searchInput) return;
    var q = searchInput.value.trim().toLowerCase();
    selectTab("extensions");
    if (searchClear) searchClear.hidden = !q;
    if (!q) {
      if (listing) listing.hidden = false;
      if (noResults) noResults.hidden = true;
      return;
    }
    var words = q.split(/\s+/);
    var match = words.some(function (w) {
      return keywords.some(function (k) { return k.indexOf(w) !== -1 || w.indexOf(k) !== -1; });
    });
    if (match) {
      if (listing) listing.hidden = false;
      if (noResults) noResults.hidden = true;
    } else {
      if (listing) listing.hidden = true;
      if (noResultsText) noResultsText.textContent = 'We couldn\'t find anything matching "' + searchInput.value.trim() + '".';
      if (noResults) noResults.hidden = false;
    }
  }
  function clearSearch() {
    if (!searchInput) return;
    searchInput.value = "";
    if (searchClear) searchClear.hidden = true;
    if (listing) listing.hidden = false;
    if (noResults) noResults.hidden = true;
    searchInput.focus();
  }
  if (searchBtn) searchBtn.addEventListener("click", runSearch);
  if (searchInput) searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); runSearch(); }
    if (e.key === "Escape" && searchInput.value) { e.stopPropagation(); clearSearch(); }
  });
  if (searchClear) searchClear.addEventListener("click", clearSearch);
  var clearBtn = $("#cws-clear-search");
  if (clearBtn) clearBtn.addEventListener("click", clearSearch);

  /* ---------------- carousel ---------------- */
  var slides = $$(".cws-slide");
  var dots = $$(".cws-dot");
  var slideIndex = 0;
  function goToSlide(i) {
    if (!slides.length) return;
    slideIndex = (i + slides.length) % slides.length;
    slides.forEach(function (s, n) {
      var active = n === slideIndex;
      s.classList.toggle("is-active", active);
      s.setAttribute("aria-hidden", active ? "false" : "true");
    });
    dots.forEach(function (d, n) {
      var active = n === slideIndex;
      d.classList.toggle("is-active", active);
      if (active) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current");
    });
  }
  var prev = $("#cws-prev");
  var next = $("#cws-next");
  if (prev) prev.addEventListener("click", function () { goToSlide(slideIndex - 1); });
  if (next) next.addEventListener("click", function () { goToSlide(slideIndex + 1); });
  dots.forEach(function (d) {
    d.addEventListener("click", function () { goToSlide(parseInt(d.getAttribute("data-slide"), 10) || 0); });
  });
  var carousel = $(".cws-carousel");
  if (carousel) carousel.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { e.preventDefault(); goToSlide(slideIndex - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); goToSlide(slideIndex + 1); }
  });

  /* ---------------- share ---------------- */
  var shareBtn = $("#cws-share-btn");
  if (shareBtn) shareBtn.addEventListener("click", function () {
    var url = window.location.href;
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = url;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      var copied = false;
      try { copied = document.execCommand("copy"); } catch (err) { copied = false; }
      document.body.removeChild(ta);
      shareBtn.focus();
      showToast(copied ? "Link copied to clipboard" : "Copy unavailable — copy the URL from the address bar");
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(function () {
        showToast("Link copied to clipboard");
      }).catch(fallback);
    } else {
      fallback();
    }
  });

  /* ---------------- modal dialogs ---------------- */
  var activeModal = null;
  var modalReturnFocus = null;
  var focusableSel = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';
  function modalFocusables(el) {
    return $$(focusableSel, el).filter(function (n) { return !n.hidden && n.offsetParent !== null; });
  }
  function openModal(id, trigger) {
    var el = $("#" + id);
    if (!el) return;
    closePopovers();
    hideTip();
    activeModal = el;
    modalReturnFocus = trigger || document.activeElement;
    el.hidden = false;
    document.body.classList.add("cws-modal-open");
    var f = modalFocusables(el);
    if (f.length) f[0].focus();
  }
  function closeModal() {
    if (!activeModal) return;
    activeModal.hidden = true;
    activeModal = null;
    document.body.classList.remove("cws-modal-open");
    if (modalReturnFocus && typeof modalReturnFocus.focus === "function") modalReturnFocus.focus();
    modalReturnFocus = null;
  }
  var addBtn = $("#cws-add-btn");
  if (addBtn) addBtn.addEventListener("click", function () { openModal("cws-install-modal", addBtn); });
  var playBtn = $("#cws-play");
  if (playBtn) playBtn.addEventListener("click", function () { openModal("cws-video-modal", playBtn); });
  $$("[data-close]").forEach(function (btn) {
    btn.addEventListener("click", function () { closeModal(); });
  });
  $$(".cws-overlay").forEach(function (overlay) {
    overlay.addEventListener("mousedown", function (e) { if (e.target === overlay) closeModal(); });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (activeModal) { e.preventDefault(); closeModal(); return; }
    if (popovers.some(function (p) { return !p.el.hidden; })) { closePopovers(); return; }
    hideTip();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab" || !activeModal) return;
    var f = modalFocusables(activeModal);
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
})();

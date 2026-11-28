/* Keel — direct install for the Chrome extension + small page interactions.
 *
 * The extension is a local MV3 package (keel-extension.zip). No Chrome Web
 * Store item is published yet: extension/README.md still records a pending
 * item ID, so every install action downloads the ZIP and opens a clear
 * load-unpacked guide. Nothing here reports a fake successful install.
 *
 * If a real store item is published later, set window.KEEL_CHROME_WEB_STORE_URL
 * to that item URL and flip window.KEEL_INSTALL_MODE to "store".
 */
window.KEEL_CHROME_WEB_STORE_URL = "";
window.KEEL_INSTALL_MODE = "download";

(function setupKeelInstall() {
  "use strict";

  var ZIP_URL = "/keel-extension.zip";
  var MODAL_ID = "cl-install-modal";
  var STYLE_ID = "cl-install-style";

  function publishedStoreUrl() {
    var url = window.KEEL_CHROME_WEB_STORE_URL;
    return window.KEEL_INSTALL_MODE === "store" &&
      typeof url === "string" &&
      /^https:\/\/chromewebstore\.google\.com\/detail\//.test(url)
      ? url : "";
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      "#" + MODAL_ID + "{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;",
      "justify-content:center;padding:24px;background:rgba(15,14,13,.62);}",
      "#" + MODAL_ID + "[hidden]{display:none!important;}",
      "#" + MODAL_ID + " .cl-install-card{position:relative;background:#fff;color:#191918;",
      "border-radius:18px;max-width:560px;width:100%;padding:32px 34px;box-shadow:0 24px 80px rgba(0,0,0,.28);",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}",
      "#" + MODAL_ID + " h2{font:500 27px Georgia,'Times New Roman',serif;margin:0 0 8px;letter-spacing:-.02em;}",
      "#" + MODAL_ID + " p{color:#6c6b66;font-size:14px;line-height:1.55;margin:0 0 18px;}",
      "#" + MODAL_ID + " ol{padding-left:22px;margin:0 0 12px;font-size:14px;line-height:1.7;}",
      "#" + MODAL_ID + " li{margin-bottom:6px;}",
      "#" + MODAL_ID + " code{background:#f2f0ea;padding:1px 6px;border-radius:4px;}",
      "#" + MODAL_ID + " .cl-install-note{font-size:12px;color:#8a877f;}",
      "#" + MODAL_ID + " .cl-install-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px;}",
      "#" + MODAL_ID + " .cl-install-btn{display:inline-block;border-radius:999px;padding:10px 20px;",
      "font-size:14px;font-weight:600;text-decoration:none;cursor:pointer;border:1px solid #191918;",
      "transition:transform .15s ease,background-color .15s ease;}",
      "#" + MODAL_ID + " .cl-install-btn:hover{transform:translateY(-1px);}",
      "#" + MODAL_ID + " .cl-install-btn-primary{background:#191918;color:#fff;}",
      "#" + MODAL_ID + " .cl-install-btn-secondary{background:#fff;color:#191918;}",
      "#" + MODAL_ID + " [data-install-close]{position:absolute;top:12px;right:16px;border:0;background:none;",
      "font-size:22px;line-height:1;cursor:pointer;color:#6c6b66;}",
      "#" + MODAL_ID + " :focus-visible{outline:2px solid #d97757;outline-offset:2px;}",
      "@media(prefers-reduced-motion:reduce){#" + MODAL_ID + " .cl-install-btn{transition:none;}}",
    ].join("");
    document.head.appendChild(style);
  }

  function buildModal() {
    if (document.getElementById(MODAL_ID)) return;
    injectStyles();
    var modal = document.createElement("div");
    modal.id = MODAL_ID;
    modal.hidden = true;
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "cl-install-title");
    modal.innerHTML = [
      '<div class="cl-install-card">',
      '<button type="button" class="cl-install-close" data-install-close aria-label="Close install guide">×</button>',
      '<h2 id="cl-install-title">Install Keel in Chrome — free</h2>',
      '<p>No Chrome Web Store listing is published yet. Download the MV3 extension and load it unpacked in Chrome. Nothing is installed automatically.</p>',
      '<ol>',
      '<li>Download <strong>keel-extension.zip</strong> with the button below.</li>',
      '<li>Unzip it into a folder you can find again (<code>manifest.json</code> must be at the folder root).</li>',
      '<li>Open <code>chrome://extensions</code> in Chrome.</li>',
      '<li>Turn on <strong>Developer mode</strong> in the top-right corner.</li>',
      '<li>Click <strong>Load unpacked</strong> and select the unzipped folder.</li>',
      '<li>Pin the Keel icon, then click it to open the side panel.</li>',
      '</ol>',
      '<p class="cl-install-note">The extension is a local-first demo: no account, no payment and no store sign-in required.</p>',
      '<div class="cl-install-actions">',
      '<a class="cl-install-btn cl-install-btn-primary" href="' + ZIP_URL + '" download="keel-extension.zip">Download extension (.zip)</a>',
      '<button type="button" class="cl-install-btn cl-install-btn-secondary" data-install-close>Got it</button>',
      '</div>',
      '</div>',
    ].join("");
    document.body.appendChild(modal);
  }

  function openModal() {
    buildModal();
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    modal.hidden = false;
    var close = modal.querySelector("[data-install-close]");
    if (close) close.focus();
  }

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.hidden = true;
  }

  function applyLinks() {
    var links = document.querySelectorAll("[data-store-install]");
    var store = publishedStoreUrl();
    for (var i = 0; i < links.length; i += 1) {
      var link = links[i];
      link.setAttribute("aria-label", "Install Keel in Chrome");
      if (store) {
        link.setAttribute("href", store);
        link.removeAttribute("download");
        link.removeAttribute("data-install-modal");
      } else {
        link.setAttribute("href", ZIP_URL);
        link.setAttribute("download", "keel-extension.zip");
        link.setAttribute("data-install-modal", "");
      }
    }
  }

  function onClick(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var modal = document.getElementById(MODAL_ID);
    if (target.closest("[data-install-close]") || (modal && target === modal)) {
      closeModal();
      return;
    }
    var trigger = target.closest("[data-install-modal]");
    if (trigger) {
      // Let the browser start the download, then show the honest guide.
      window.setTimeout(openModal, 0);
    }
  }

  function onKey(event) {
    if (event.key === "Escape") closeModal();
  }

  function init() {
    applyLinks();
    buildModal();
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

/* ------- /keel-in-chrome page: menu, tabs, accordion, reveal, scroll ------- */
(function setupKeelInChromePage() {
  "use strict";

  if (!document.body || !document.body.classList.contains("kic-page")) return;

  function initMegaMenu() {
    var items = document.querySelectorAll("[data-kic-mega]");

    function setOpen(item, open) {
      item.classList.toggle("is-open", open);
      var trigger = item.querySelector("[data-kic-mega-trigger]");
      if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    function closeAll(except) {
      for (var i = 0; i < items.length; i += 1) {
        if (items[i] !== except) setOpen(items[i], false);
      }
    }

    for (var i = 0; i < items.length; i += 1) {
      (function (item) {
        var trigger = item.querySelector("[data-kic-mega-trigger]");
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
      if (!event.target.closest || !event.target.closest("[data-kic-mega]")) closeAll();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAll();
    });
  }

  function initMobileNav() {
    var toggle = document.querySelector("[data-kic-nav-toggle]");
    var menu = document.getElementById("kic-mobile-menu");
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

  function initDemoTabs() {
    var tabs = document.querySelectorAll("[data-kic-tab]");
    var modes = document.querySelectorAll("[data-kic-mode]");
    var panels = document.querySelectorAll("[data-kic-panel]");
    if (!tabs.length) return;

    function setVariant(value) {
      if (value !== "chat" && value !== "cowork") return;
      for (var i = 0; i < tabs.length; i += 1) {
        var on = tabs[i].getAttribute("data-kic-tab") === value;
        tabs[i].classList.toggle("is-active", on);
        tabs[i].setAttribute("aria-selected", on ? "true" : "false");
        tabs[i].tabIndex = on ? 0 : -1;
      }
      for (var j = 0; j < modes.length; j += 1) {
        var active = modes[j].getAttribute("data-kic-mode") === value;
        modes[j].classList.toggle("is-active", active);
        modes[j].setAttribute("aria-pressed", active ? "true" : "false");
      }
      for (var k = 0; k < panels.length; k += 1) {
        panels[k].hidden = panels[k].getAttribute("data-kic-panel") !== value;
      }
    }

    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      var trigger = target.closest("[data-kic-tab],[data-kic-mode]");
      if (!trigger) return;
      setVariant(trigger.getAttribute("data-kic-tab") || trigger.getAttribute("data-kic-mode"));
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      var tab = event.target.closest && event.target.closest("[data-kic-tab]");
      if (!tab) return;
      event.preventDefault();
      var index = Array.prototype.indexOf.call(tabs, tab);
      var step = event.key === "ArrowRight" ? 1 : -1;
      var next = tabs[(index + step + tabs.length) % tabs.length];
      setVariant(next.getAttribute("data-kic-tab"));
      next.focus();
    });
  }

  function initFaq() {
    var questions = document.querySelectorAll("[data-kic-faq]");
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
      var button = target.closest("[data-kic-faq]");
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

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function initReveal() {
    var nodes = document.querySelectorAll(".kic-reveal");
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

  function initLanguage() {
    var select = document.querySelector("[data-kic-language]");
    var status = document.getElementById("kic-lang-status");
    if (!select || !status) return;
    select.addEventListener("change", function () {
      var label = select.options[select.selectedIndex].text;
      status.textContent = "Language preference saved: " + label + ". This preview stays in English.";
    });
  }

  function init() {
    initMegaMenu();
    initMobileNav();
    initDemoTabs();
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

/* Keel — free direct install for the Chrome extension.
 *
 * The extension is installable without a Chrome Web Store account or fee.
 * Every element carrying data-store-install downloads the MV3 ZIP and opens a
 * short load-unpacked guide. If a Web Store item is published later, set
 * window.KEEL_CHROME_WEB_STORE_URL to that item URL and flip
 * window.KEEL_INSTALL_MODE to "store" below — no other edits are needed.
 */
window.KEEL_CHROME_WEB_STORE_URL = "https://chromewebstore.google.com/detail/keel/PENDING_ITEM_ID";
window.KEEL_INSTALL_MODE = "download";

(function setupKeelInstall() {
  var ZIP_URL = "/keel-extension.zip";
  var MODAL_ID = "cl-install-modal";
  var STYLE_ID = "cl-install-style";

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      "#" + MODAL_ID + "{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;",
      "justify-content:center;padding:24px;background:rgba(15,14,13,.62);}",
      "#" + MODAL_ID + "[hidden]{display:none;}",
      "#" + MODAL_ID + " .cl-install-card{position:relative;background:#fff;color:#191918;",
      "border-radius:18px;max-width:560px;width:100%;padding:32px 34px;box-shadow:0 24px 80px rgba(0,0,0,.28);",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;}",
      "#" + MODAL_ID + " h2{font:700 28px Georgia,'Times New Roman',serif;margin:0 0 8px;}",
      "#" + MODAL_ID + " p{color:#6c6b66;font-size:14px;line-height:1.55;margin:0 0 18px;}",
      "#" + MODAL_ID + " ol{padding-left:22px;margin:0 0 22px;font-size:14px;line-height:1.7;}",
      "#" + MODAL_ID + " li{margin-bottom:6px;}",
      "#" + MODAL_ID + " code{background:#f2f0ea;padding:1px 6px;border-radius:4px;}",
      "#" + MODAL_ID + " .cl-install-actions{display:flex;gap:10px;flex-wrap:wrap;}",
      "#" + MODAL_ID + " .cl-install-btn{display:inline-block;border-radius:999px;padding:10px 20px;",
      "font-size:14px;font-weight:600;text-decoration:none;cursor:pointer;border:1px solid #191918;}",
      "#" + MODAL_ID + " .cl-install-btn-primary{background:#191918;color:#fff;}",
      "#" + MODAL_ID + " .cl-install-btn-secondary{background:#fff;color:#191918;}",
      "#" + MODAL_ID + " [data-install-close]{position:absolute;top:12px;right:16px;border:0;background:none;",
      "font-size:22px;line-height:1;cursor:pointer;color:#6c6b66;}",
      "#" + MODAL_ID + " :focus-visible{outline:2px solid #d97757;outline-offset:2px;}",
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
      '<p>No account, no payment and no browser-store listing required. The extension runs locally in your browser.</p>',
      '<ol>',
      '<li>Download <strong>keel-extension.zip</strong> with the button below.</li>',
      '<li>Unzip it into a folder you can find again.</li>',
      '<li>Open <code>chrome://extensions</code> in Chrome.</li>',
      '<li>Turn on <strong>Developer mode</strong> in the top-right corner.</li>',
      '<li>Click <strong>Load unpacked</strong> and select the unzipped folder.</li>',
      '<li>Pin the Keel icon and click it to open the side panel.</li>',
      '</ol>',
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
    for (var i = 0; i < links.length; i += 1) {
      var link = links[i];
      var target = window.KEEL_INSTALL_MODE === "store" && window.KEEL_CHROME_WEB_STORE_URL
        ? window.KEEL_CHROME_WEB_STORE_URL
        : ZIP_URL;
      link.setAttribute("href", target);
      if (target === ZIP_URL) {
        link.setAttribute("download", "keel-extension.zip");
        link.setAttribute("data-install-modal", "");
      }
      link.setAttribute("aria-label", "Install Keel in Chrome");
    }
  }

  function onClick(event) {
    var trigger = event.target.closest && event.target.closest("[data-install-modal]");
    if (trigger) {
      // Let the browser start the download, then show the guide.
      window.setTimeout(openModal, 0);
      return;
    }
    if (event.target.closest && event.target.closest("[data-install-close]")) closeModal();
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

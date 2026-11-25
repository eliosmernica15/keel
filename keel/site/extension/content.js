/* Keel in Chrome — read-only page context provider.
 * Never mutates the page: text is extracted from a detached clone of <body>.
 */
(function () {
  'use strict';

  if (globalThis.__KEEL_CONTENT_SCRIPT_READY__) return;
  globalThis.__KEEL_CONTENT_SCRIPT_READY__ = true;

  var MAX_TEXT = 30000;
  var NOISE_SELECTOR = [
    'script', 'style', 'noscript', 'template', 'svg', 'canvas', 'iframe',
    'nav', 'footer', 'header', 'aside', 'form', 'button', 'select', 'textarea',
    '[role="navigation"]', '[role="banner"]', '[role="dialog"]',
    '[aria-hidden="true"]', '.cookie-banner', '.cookie-consent', '[data-keel-ignore]'
  ].join(',');

  function collapseWhitespace(value) {
    return String(value || '')
      .replace(/\u00a0/g, ' ')
      .replace(/[ \t]+/g, ' ')
      .replace(/ *\n */g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function readBodyText() {
    if (!document.body) return '';
    var clone = document.body.cloneNode(true);
    var nodes = [];
    try {
      nodes = Array.prototype.slice.call(clone.querySelectorAll(NOISE_SELECTOR));
    } catch (_e) {
      nodes = [];
    }
    nodes.forEach(function (node) {
      try { node.remove(); } catch (_e) { /* ignore detached nodes */ }
    });
    try {
      return collapseWhitespace(clone.innerText || clone.textContent || '').slice(0, MAX_TEXT);
    } catch (_e) {
      return '';
    }
  }

  function readSelection() {
    try {
      var selection = globalThis.getSelection ? globalThis.getSelection() : window.getSelection();
      if (!selection || selection.isCollapsed) return '';
      return collapseWhitespace(selection.toString()).slice(0, 5000);
    } catch (_e) {
      return '';
    }
  }

  function countWords(text) {
    var parts = String(text || '').match(/[A-Za-z0-9']+/g);
    return parts ? parts.length : 0;
  }

  function domainOf(url) {
    try {
      return new URL(url).hostname.replace(/^www\./i, '');
    } catch (_e) {
      return '';
    }
  }

  function getContext() {
    var url = (globalThis.location && location.href) ? location.href : '';
    var title = (document.title && document.title.trim()) ? document.title.trim() : 'Untitled page';
    var text = readBodyText();
    return {
      ok: true,
      title: title.slice(0, 500),
      url: url,
      domain: domainOf(url),
      text: text,
      selection: readSelection(),
      wordCount: countWords(text),
      truncated: text.length >= MAX_TEXT,
      source: 'content-script',
      capturedAt: new Date().toISOString()
    };
  }

  try {
    if (globalThis.chrome && globalThis.chrome.runtime && typeof globalThis.chrome.runtime.onMessage.addListener === 'function') {
      globalThis.chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
        if (!message || message.type !== 'KEEL_GET_CONTEXT') return false;
        try {
          var context = getContext();
          if (typeof sendResponse === 'function') sendResponse(context);
        } catch (_e) {
          if (typeof sendResponse === 'function') sendResponse({ ok: false, error: 'Could not read page context' });
        }
        return false;
      });
    }
  } catch (_e) {
    /* no runtime available (e.g. page opened directly) */
  }
})();

/* ===========================================================================
   Keel — /downloads page behaviour.
   Dependency-free. Every listener is guarded so a missing node never throws.
   =========================================================================== */
(function () {
  'use strict';

  /* ---------- Back navigation ---------- */
  function initBack() {
    var back = document.getElementById('dl-back');
    if (!back) return;

    back.addEventListener('click', function () {
      var referrer = document.referrer || '';
      var sameOrigin = false;
      if (referrer) {
        try {
          sameOrigin = new URL(referrer, window.location.href).origin === window.location.origin;
        } catch (error) {
          sameOrigin = false;
        }
      }
      if (sameOrigin && window.history && window.history.length > 1) {
        window.history.back();
      } else {
        window.location.assign('/download');
      }
    });
  }

  /* ---------- Dialog helper: open / close / focus trap ---------- */
  function dialogController(modal) {
    var dialog = modal ? modal.querySelector('.dl-dialog') : null;
    if (!dialog) return { open: function () {}, close: function () {} };

    var lastFocused = null;

    function focusable() {
      var nodes = dialog.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])');
      return Array.prototype.filter.call(nodes, function (node) {
        return node.offsetParent !== null || node === document.activeElement;
      });
    }

    function open(trigger) {
      lastFocused = trigger || document.activeElement;
      modal.hidden = false;
      document.body.classList.add('dl-modal-open');
      var initial = dialog.querySelector('[data-dl-initial-focus]') || dialog.querySelector('.dl-dialog-close');
      if (initial && typeof initial.focus === 'function') initial.focus();
    }

    function close() {
      if (modal.hidden) return;
      modal.hidden = true;
      document.body.classList.remove('dl-modal-open');
      if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
    }

    Array.prototype.forEach.call(modal.querySelectorAll('[data-dl-close]'), function (closer) {
      closer.addEventListener('click', close);
    });

    document.addEventListener('keydown', function (event) {
      if (modal.hidden || !event) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      var items = focusable();
      if (!items.length) {
        event.preventDefault();
        return;
      }
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    return { open: open, close: close };
  }

  /* ---------- Upgrade dialog ---------- */
  function initUpgrade() {
    var modal = document.getElementById('dl-upgrade-modal');
    if (!modal) return;
    var controller = dialogController(modal);
    var description = document.getElementById('dl-upgrade-desc');

    Array.prototype.forEach.call(document.querySelectorAll('[data-upgrade]'), function (button) {
      button.addEventListener('click', function () {
        var name = button.getAttribute('data-upgrade') || 'Keel';
        var subject = name === 'Keel Code' ? 'Keel Code'
          : name === 'Chrome' ? 'the Chrome extension'
          : 'Keel for ' + name;
        if (description) {
          description.textContent = subject + ' is available on a paid Keel plan. Compare plans or create an account to get started.';
        }
        controller.open(button);
      });
    });
  }

  /* ---------- Integration detail dialog ---------- */
  function initIntegrations() {
    var modal = document.getElementById('dl-integration-modal');
    if (!modal) return;
    var controller = dialogController(modal);
    var title = document.getElementById('dl-integration-title');
    var description = document.getElementById('dl-integration-desc');
    var link = document.getElementById('dl-integration-link');
    var allowed = ['/app', '/download', '/plugins'];

    Array.prototype.forEach.call(document.querySelectorAll('[data-integration]'), function (button) {
      button.addEventListener('click', function () {
        var label = button.getAttribute('data-title') || button.textContent.trim();
        var detail = button.getAttribute('data-desc') || 'Use Keel alongside your tools.';
        var target = button.getAttribute('data-link') || '/plugins';
        if (allowed.indexOf(target) === -1) target = '/plugins';

        if (title) title.textContent = label;
        if (description) description.textContent = detail;
        if (link) {
          link.href = target;
          link.setAttribute('aria-label', 'Open ' + label + ' in Keel');
        }
        controller.open(button);
      });
    });
  }

  /* ---------- Manifest-driven download ----------
     A link points at a real installer only when the same-origin manifest says
     available === true, verified === true, and carries an HTTPS URL, a positive
     byte size and a 64-character SHA-256. Otherwise it stays on /download with
     an honest platform note. */
  function initDownload() {
    var button = document.getElementById('dl-download');
    var note = document.getElementById('dl-download-note');
    if (!button) return;

    var shaPattern = /^[0-9a-f]{64}$/i;
    var platformNames = {
      windows: 'Windows',
      'windows-arm64': 'Windows arm64',
      macos: 'macOS',
      linux: 'Linux'
    };
    var unavailableNote = note ? note.textContent : '';

    function safeUrl(value) {
      if (!value) return null;
      try {
        var url = new URL(String(value), window.location.href);
        if (url.protocol === 'https:') return url.href;
        if (url.protocol === 'http:' && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(url.hostname)) {
          return url.href;
        }
      } catch (error) {
        return null;
      }
      return null;
    }

    function verifiedChannel(doc, key) {
      if (!doc || !doc.channels) return null;
      var channel = doc.channels[key];
      if (!channel) return null;
      var ok = channel.available === true
        && channel.verified === true
        && Number.isFinite(Number(channel.size))
        && Number(channel.size) > 0
        && shaPattern.test(String(channel.sha256 || ''))
        && safeUrl(channel.url) !== null;
      return ok ? channel : null;
    }

    function formatSize(bytes) {
      var value = Number(bytes);
      if (!Number.isFinite(value) || value <= 0) return null;
      var mb = value / 1024 / 1024;
      return (mb >= 100 ? mb.toFixed(1) : mb.toFixed(2)) + ' MB';
    }

    function detectPlatform() {
      var hints = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
      var ua = navigator.userAgent || '';
      if (/Windows/i.test(hints) || /Windows/i.test(ua)) {
        var arch = (navigator.userAgentData && navigator.userAgentData.architecture) || '';
        return (/arm64|aarch64/i.test(ua) || /arm/i.test(arch)) ? 'windows-arm64' : 'windows';
      }
      if (/Mac/i.test(hints) || /Macintosh|Mac OS/i.test(ua)) return 'macos';
      if (/Linux/i.test(hints) || /Linux/i.test(ua)) return 'linux';
      return 'windows';
    }

    function applyChannel(channel) {
      if (channel) {
        var url = safeUrl(channel.url);
        button.href = url;
        button.removeAttribute('aria-disabled');
        button.setAttribute('title', 'Download ' + (channel.file || 'Keel Desktop')
          + (formatSize(channel.size) ? ' (' + formatSize(channel.size) + ')' : '') + ' · SHA-256 verified');
        if (note) {
          var bits = ['v' + (channel.version || ''), formatSize(channel.size), 'SHA-256 verified'].filter(Boolean);
          note.textContent = 'Available: ' + bits.join(' · ') + ' over HTTPS.';
          note.classList.add('is-available');
        }
        return;
      }

      button.href = '/download';
      button.setAttribute('aria-disabled', 'true');
      button.setAttribute('title', 'No verified installer published yet — see the download page for details');
      if (note) {
        var platform = detectPlatform();
        var prefix = platform === 'windows' || platform === 'windows-arm64'
          ? '' : 'You are browsing on ' + (platformNames[platform] || platform) + '. ';
        note.textContent = prefix + unavailableNote;
        note.classList.remove('is-available');
      }
    }

    applyChannel(null);

    fetch('/download.json', { cache: 'no-cache', headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) return null;
        return response.json();
      })
      .then(function (doc) {
        if (!doc || typeof doc.version !== 'string' || !doc.channels) return;
        applyChannel(verifiedChannel(doc, 'windows'));
      })
      .catch(function () {
        /* Offline or malformed manifest: keep the honest /download fallback. */
      });
  }

  initBack();
  initUpgrade();
  initIntegrations();
  initDownload();
})();

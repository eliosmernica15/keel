/* /download — manifest-driven, honest platform download UX.
 *
 * Sources, in order:
 *   1. /api/download-manifest  (same-origin proxy of the published manifest)
 *   2. /download.json          (committed fallback; all channels unavailable)
 *
 * Nothing on this page invents a URL, size or checksum. A control is enabled
 * only when the release manifest says available === true AND verified === true
 * AND verified_at is set AND the channel has a public HTTPS URL, a positive
 * byte size and a full SHA-256. Every other state is described in plain text.
 *
 * The visual design lives in download-clone.css; download-ux.css only adds the
 * small status/selection affordances. Pure decision functions are exported on
 * globalThis.__KEEL_DOWNLOAD__ so the Node/Playwright tests can exercise them
 * without a browser build step.
 */
(function () {
  "use strict";

  var MANIFEST_SOURCES = ["/api/download-manifest", "/download.json"];
  var SHA_RE = /^[0-9a-f]{64}$/i;
  var OS_LABELS = { windows: "Windows", macos: "macOS", linux: "Linux" };

  /* SEC-F-02: a checksum from the manifest does not bind the download to a
     trusted origin. Only first-party release hosts are accepted, plus hosts
     supplied by a NON-SECRET deploy-time config value (never by the manifest
     itself, which a tampered source could self-authorize). */
  var DEFAULT_APPROVED_HOSTS = ["github.com", "objects.githubusercontent.com"];

  function approvedHosts() {
    var hosts = DEFAULT_APPROVED_HOSTS.slice();
    try {
      if (typeof location !== "undefined") {
        if (location.hostname) hosts.push(location.hostname);
        else if (location.href) hosts.push(new URL(location.href).hostname);
      }
    } catch (_) { /* no location in a test harness */ }
    try {
      if (typeof globalThis !== "undefined") {
        var configuredHosts = globalThis.KEEL_DOWNLOAD_HOSTS;
        if (configuredHosts) hosts.push(String(configuredHosts));
        // Derive the approved host from the configured first-party manifest
        // endpoint when one is supplied. The manifest document cannot add hosts.
        var manifestUrl = globalThis.KEEL_DOWNLOAD_MANIFEST_URL;
        if (manifestUrl) {
          var parsed = new URL(String(manifestUrl));
          if (parsed.protocol === "https:") hosts.push(parsed.hostname);
        }
      }
    } catch (_) { /* invalid config must not widen the allowlist */ }
    try {
      if (typeof document !== "undefined" && document.querySelector) {
        var meta = document.querySelector('meta[name="keel-download-hosts"]');
        if (meta && meta.getAttribute("content")) hosts.push(meta.getAttribute("content"));
      }
    } catch (_) { /* no meta tag outside the page */ }
    var allowed = Object.create(null);
    hosts.forEach(function (entry) {
      String(entry).split(/[\s,]+/).forEach(function (host) {
        var normalized = String(host).trim().toLowerCase();
        if (normalized) allowed[normalized] = true;
      });
    });
    return allowed;
  }

  var PRIMARY = null;
  var STATUS = null;
  var VARIANTS = null;
  var OTHER = null;
  var DETAILS = null;
  var manifestDoc = null;
  var detected = { os: null, arch: null };
  var activeOs = null;
  var selection = null; // explicit variant key chosen by the user
  var userOverrodePlatform = false;
  var currentState = "detecting";

  /* ------------------------------------------------------------------ */
  /* pure helpers                                                       */
  /* ------------------------------------------------------------------ */

  function safeUrl(value, base) {
    if (!value) return null;
    try {
      var origin = base || (typeof location !== "undefined" ? location.href : "https://keel-desktop.vercel.app/download");
      var url = new URL(String(value), origin);
      if (url.protocol === "https:") {
        return approvedHosts()[url.hostname.toLowerCase()] ? url.href : null;
      }
      // Loopback HTTP is allowed only for local development; the release
      // pipeline never emits it and production keeps HTTPS-only links.
      if (url.protocol === "http:" && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(url.hostname)) return url.href;
    } catch (_) { /* malformed URL */ }
    return null;
  }

  function isDownloadable(channel) {
    if (!channel || channel.available !== true || channel.verified !== true) return false;
    if (!channel.verified_at || !/^\d{4}-\d{2}-\d{2}/.test(String(channel.verified_at))) return false;
    if (!(Number.isFinite(Number(channel.size)) && Number(channel.size) > 0)) return false;
    if (!SHA_RE.test(String(channel.sha256 || ""))) return false;
    return safeUrl(channel.url) !== null;
  }

  function unavailableReason(channel) {
    if (!channel) return "No build is listed in the release manifest.";
    if (channel.available !== true) return "No verified installer is published for this build.";
    if (channel.verified !== true) return "The build has not passed checksum verification.";
    if (!channel.verified_at) return "The verified-at timestamp is missing.";
    if (!(Number.isFinite(Number(channel.size)) && Number(channel.size) > 0)) return "The published size is missing.";
    if (!SHA_RE.test(String(channel.sha256 || ""))) return "The SHA-256 checksum is missing.";
    if (!safeUrl(channel.url)) return "No public HTTPS download URL is published.";
    return "This build is not available.";
  }

  function fmtBytes(bytes) {
    var n = Number(bytes);
    if (!Number.isFinite(n) || n <= 0) return null;
    var mb = n / 1024 / 1024;
    return (mb >= 100 ? mb.toFixed(1) : mb.toFixed(2)) + " MB";
  }

  function validManifest(doc) {
    return !!doc && typeof doc === "object"
      && typeof doc.version === "string"
      && !!doc.channels && typeof doc.channels === "object";
  }

  async function fetchManifest(fetcher) {
    var doFetch = fetcher || (typeof fetch === "function" ? fetch : null);
    if (!doFetch) return null;
    for (var i = 0; i < MANIFEST_SOURCES.length; i += 1) {
      try {
        var response = await doFetch(MANIFEST_SOURCES[i], {
          cache: "no-cache",
          headers: { Accept: "application/json" },
        });
        if (!response || !response.ok) continue;
        var doc = await response.json();
        if (validManifest(doc)) return doc;
      } catch (_) { /* try the next same-origin source */ }
    }
    return null;
  }

  /* Detect OS first, architecture only when the browser actually tells us.
     userAgentData.getHighEntropyValues() is async; the static `.architecture`
     property is used as a synchronous fallback for browsers that expose it. */
  async function detectPlatform(nav) {
    var n = nav || (typeof navigator !== "undefined" ? navigator : {});
    var ua = String(n.userAgent || "");
    var uad = n.userAgentData || {};
    var platform = String(uad.platform || n.platform || "");

    if (/iPhone|iPad|iPod/i.test(ua) || /iPadOS|iOS/i.test(platform)) return { os: "ios", arch: null };
    if (/Android/i.test(ua) || /Android/i.test(platform)) return { os: "android", arch: null };

    var arch = null;
    try {
      if (typeof uad.getHighEntropyValues === "function") {
        var hints = await uad.getHighEntropyValues(["architecture", "bitness", "platform"]);
        var a = String((hints && hints.architecture) || "").toLowerCase();
        var bits = String((hints && hints.bitness) || "");
        if (a === "arm" || a === "arm64" || a === "aarch64") arch = bits === "64" || !bits ? "arm64" : "arm";
        else if (a === "x86") arch = bits === "32" ? "x86" : "x64";
        else if (a) arch = a;
      }
    } catch (_) { /* hint API unavailable; keep arch unknown */ }
    if (!arch && uad.architecture) {
      var staticArch = String(uad.architecture).toLowerCase();
      if (staticArch === "arm" || staticArch === "arm64" || staticArch === "aarch64") arch = "arm64";
      else if (staticArch === "x86") arch = "x64";
    }

    var os = null;
    if (/Windows/i.test(platform) || /Windows/i.test(ua)) {
      os = "windows";
      if (!arch && /Win64|x64|WOW64/i.test(ua)) arch = "x64";
    } else if (/Macintosh|Mac OS X|Mac OS/i.test(ua) || /^Mac/i.test(platform) || /macos/i.test(platform)) {
      os = "macos"; // browsers do not reliably expose Intel vs Apple Silicon
    } else if (/Linux|X11/i.test(ua) || /linux/i.test(platform)) {
      os = "linux";
      // Package format (DEB vs RPM) is never guessed from the UA.
    }
    return { os: os, arch: arch };
  }

  function normalizeArch(value) {
    var a = String(value || "").toLowerCase();
    if (a === "aarch64" || a === "arm64") return "arm64";
    if (a === "x86_64" || a === "amd64" || a === "x64") return "x64";
    return a || null;
  }

  function formatOf(channel) {
    var file = String((channel && channel.file) || "").toLowerCase();
    if (/\.rpm$/.test(file)) return "rpm";
    if (/\.deb$/.test(file)) return "deb";
    if (/appimage/.test(file)) return "appimage";
    if (/\.dmg$|\.pkg$/.test(file)) return "dmg";
    if (/\.zip$/.test(file)) return "zip";
    if (/\.exe$/.test(file)) return "exe";
    return null;
  }

  function labelOf(os, channel, key) {
    if (os === "macos") {
      var a = normalizeArch(channel.arch);
      if (a === "arm64") return "Apple Silicon";
      if (a === "x64") return "Intel";
    }
    if (os === "linux") {
      var f = formatOf(channel);
      if (f === "deb") return "DEB";
      if (f === "rpm") return "RPM";
      if (f === "appimage") return "AppImage";
    }
    return channel.label || channel.name || (key ? key.split(":")[1] : OS_LABELS[os]) || "Keel";
  }

  function variantKey(os, channel, index) {
    var arch = normalizeArch(channel.arch);
    var format = formatOf(channel);
    if (os === "macos") return "macos:" + (arch || ("alt-" + index));
    if (os === "linux") return "linux:" + (format || ("alt-" + index));
    return "windows:" + (arch || "x64");
  }

  /* Build the complete, deduplicated candidate set for one OS. Primary
     channel first, then explicit alternatives (DEB/RPM, Intel/Apple Silicon,
     ZIP/DMG). Alternatives are only ever offered from the manifest. */
  function variantsFor(manifest, os) {
    if (!manifest || !manifest.channels || !manifest.channels[os]) return [];
    var primary = manifest.channels[os];
    var raw = [primary].concat(Array.isArray(primary.alternatives) ? primary.alternatives : []);
    var seen = Object.create(null);
    var out = [];
    for (var i = 0; i < raw.length; i += 1) {
      var channel = raw[i];
      if (!channel || typeof channel !== "object") continue;
      var key = variantKey(os, channel, i);
      if (seen[key]) continue;
      seen[key] = true;
      out.push({
        key: key,
        os: os,
        label: labelOf(os, channel, key),
        arch: normalizeArch(channel.arch),
        format: formatOf(channel),
        file: String(channel.file || ""),
        size: channel.size,
        version: channel.version || manifest.version,
        channel: channel,
        downloadable: isDownloadable(channel),
        reason: unavailableReason(channel),
      });
    }
    return out;
  }

  /* Pure decision function: which candidate should be the primary action,
     and which of the five honest states should the page be in? */
  function resolvePrimary(variants, platform, chosen, haveManifest) {
    var detectedOs = platform && platform.os;
    var detectedArch = platform && platform.arch;
    if (!haveManifest) return { variant: null, state: "unavailable", note: "Download manifest unavailable — no link can be verified." };
    if (!variants || variants.length === 0) return { variant: null, state: "unavailable", note: "No builds are listed for this platform." };

    var chosenVariant = chosen ? variants.filter(function (v) { return v.key === chosen; })[0] : null;
    if (chosenVariant) {
      return chosenVariant.downloadable
        ? { variant: chosenVariant, state: "ready", note: "" }
        : { variant: chosenVariant, state: "unavailable", note: chosenVariant.label + ": " + chosenVariant.reason };
    }

    if (detectedOs === "macos" && !detectedArch) {
      // Two real builds may exist; never silently pick the wrong one.
      if (variants.length > 1) return { variant: null, state: "arch-confirm", note: "We couldn't confirm your Mac's architecture. Choose Apple Silicon or Intel." };
    }

    var preference = [];
    if (detectedOs === "macos") {
      if (detectedArch === "arm64") preference = ["macos:arm64", "macos:x64"];
      else if (detectedArch === "x64") preference = ["macos:x64", "macos:arm64"];
    } else if (detectedOs === "linux") {
      preference = ["linux:deb", "linux:rpm", "linux:appimage"];
    } else if (detectedOs === "windows") {
      preference = detectedArch === "arm64" ? ["windows:arm64", "windows:x64"] : ["windows:x64", "windows:arm64"];
    }

    var pick = null;
    for (var i = 0; i < preference.length && !pick; i += 1) {
      var candidate = variants.filter(function (v) { return v.key === preference[i] && v.downloadable; })[0];
      if (candidate) pick = candidate;
    }
    if (!pick) pick = variants.filter(function (v) { return v.downloadable; })[0];

    if (pick) {
      var note = "";
      if (detectedOs === "linux" && pick.key === "linux:rpm" && variants.some(function (v) { return v.key === "linux:deb" && !v.downloadable; })) {
        note = "DEB is not published yet; showing the verified RPM instead.";
      }
      return { variant: pick, state: "ready", note: note };
    }
    return { variant: variants[0], state: "unavailable", note: "No verified " + (OS_LABELS[detectedOs] || "desktop") + " installer is published yet." };
  }

  function platformDescription(platform) {
    if (!platform || !platform.os) return "your device";
    var label = OS_LABELS[platform.os] || platform.os;
    if (platform.os === "macos" && platform.arch === "arm64") return "macOS (Apple Silicon)";
    if (platform.os === "macos" && platform.arch === "x64") return "macOS (Intel)";
    if (platform.arch && platform.os === "windows") return label + " " + platform.arch;
    return label;
  }

  function isUnsupported(platform) {
    if (!platform || !platform.os) return false;
    if (platform.os === "ios" || platform.os === "android") return true;
    return platform.os === "windows" && platform.arch === "arm64";
  }

  function unsupportedNote(platform) {
    if (platform.os === "ios" || platform.os === "android") {
      return "Keel is a desktop app for Windows, macOS and Linux. It doesn't run on " +
        (platform.os === "ios" ? "iOS" : "Android") + ".";
    }
    return "A native Windows on ARM build is not published yet. The x64 installer can run under emulation on Windows 11 ARM.";
  }

  /* ------------------------------------------------------------------ */
  /* DOM rendering                                                      */
  /* ------------------------------------------------------------------ */

  function byId(id) {
    return typeof document !== "undefined" && document.getElementById ? document.getElementById(id) : null;
  }

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function setState(state, message) {
    currentState = state;
    if (STATUS) {
      STATUS.setAttribute("data-state", state);
      STATUS.textContent = message;
    }
    if (PRIMARY) PRIMARY.setAttribute("data-state", state);
  }

  function setPrimary(result) {
    if (!PRIMARY) return;
    var variant = result.variant;
    var ready = result.state === "ready" && variant && variant.downloadable;
    var label = PRIMARY.querySelector("#kp-download-primary-label");
    if (ready) {
      var url = safeUrl(variant.channel.url);
      PRIMARY.setAttribute("href", url);
      PRIMARY.setAttribute("download", variant.file || "Keel installer");
      PRIMARY.setAttribute("rel", "noopener");
      PRIMARY.setAttribute("title", "Download " + variant.file + " · " +
        (fmtBytes(variant.size) || "size verified") + " · SHA-256 verified");
      PRIMARY.removeAttribute("aria-disabled");
      PRIMARY.classList.remove("is-disabled");
      if (label) label.textContent = "Download for " + variant.label +
        (variant.version ? " · v" + variant.version : "");
    } else {
      PRIMARY.removeAttribute("href");
      PRIMARY.removeAttribute("download");
      PRIMARY.setAttribute("aria-disabled", "true");
      PRIMARY.setAttribute("role", "link");
      PRIMARY.classList.add("is-disabled");
      var text = result.state === "unsupported" ? "Not available on this device"
        : result.state === "arch-confirm" ? "Confirm your architecture"
        : result.state === "checking" ? "Checking availability…"
        : result.state === "detecting" ? "Detecting your device…"
        : "Not published yet";
      PRIMARY.setAttribute("title", result.note || "No verified installer is available.");
      if (label) label.textContent = text;
    }
  }

  /* Secondary rows only SELECT a build; the single primary action performs the
     download. An unverified build never gets an enabled control. */
  function actionFor(variant) {
    var node = make("button", "kp-btn kp-btn-outline kp-btn-sm kp-row-action");
    node.type = "button";
    if (variant.downloadable) {
      node.textContent = "Select";
      node.setAttribute("aria-label", "Select " + variant.label);
      node.setAttribute("title", variant.file + " · " + (fmtBytes(variant.size) || "verified") + " · SHA-256 verified");
      node.addEventListener("click", function () {
        selection = variant.key;
        apply();
      });
    } else {
      node.disabled = true;
      node.setAttribute("aria-disabled", "true");
      node.textContent = "Unavailable";
      node.setAttribute("aria-label", variant.label + " unavailable");
      node.setAttribute("title", variant.reason);
    }
    return node;
  }

  function renderVariants(variants) {
    if (!VARIANTS) return;
    VARIANTS.textContent = "";
    variants.forEach(function (variant) {
      var row = make("div", "kp-row kp-variant-row");
      var label = make("span", "kp-row-label");
      label.appendChild(make("span", null, variant.label + (variant.arch && variant.os === "macos" ? " · " + variant.arch : "")));
      if (variant.version) label.appendChild(make("small", null, "v" + variant.version));
      if (variant.size) label.appendChild(make("small", null, fmtBytes(variant.size) + " · SHA-256 verified"));
      else label.appendChild(make("small", null, variant.reason));
      // Manifest-supplied notes (e.g. "Unsigned — Gatekeeper will warn") are
      // always rendered as text, never as HTML.
      if (variant.channel.notes) label.appendChild(make("small", "kp-variant-note", variant.channel.notes));
      row.appendChild(label);
      row.appendChild(actionFor(variant));
      VARIANTS.appendChild(row);
    });
  }

  function renderOther(currentOs) {
    if (!OTHER) return;
    OTHER.textContent = "";
    ["windows", "macos", "linux"].forEach(function (os) {
      if (!manifestDoc || !manifestDoc.channels || !manifestDoc.channels[os]) return;
      var button = make("button", "kp-other-option", OS_LABELS[os]);
      button.type = "button";
      button.setAttribute("aria-pressed", os === currentOs ? "true" : "false");
      button.addEventListener("click", function () {
        activeOs = os;
        selection = null;
        userOverrodePlatform = true;
        if (DETAILS) DETAILS.open = false;
        apply();
      });
      OTHER.appendChild(button);
    });
  }

  function apply() {
    var variants = variantsFor(manifestDoc, activeOs);
    // When the user deliberately switches OS, the host CPU cannot be assumed
    // to describe that other platform: ask for an explicit architecture/build.
    var platformForSelection = userOverrodePlatform ? { os: activeOs, arch: null } : detected;
    var decision = resolvePrimary(variants, platformForSelection, selection, !!manifestDoc);
    var message = decision.note;

    if (isUnsupported(detected) && !userOverrodePlatform) {
      // Wrong OS or an unsupported architecture: never offer a download for
      // the detected device, even if another platform's build is verified.
      decision = { variant: null, state: "unsupported", note: unsupportedNote(detected) };
      message = decision.note;
    } else if (decision.state === "ready") {
      message = decision.note || "Ready — " + decision.variant.label +
        (decision.variant.version ? " · v" + decision.variant.version : "") +
        " · SHA-256 verified over HTTPS.";
    } else if (decision.state === "arch-confirm") {
      message = decision.note;
    } else if (decision.state === "unavailable" && !decision.note) {
      message = "No verified installer is available for " + platformDescription(detected) + ".";
    }

    setState(decision.state, message);
    setPrimary(decision);
    renderVariants(variants);
    renderOther(activeOs);
  }

  function boot() {
    PRIMARY = byId("kp-download-primary");
    STATUS = byId("kp-download-status");
    VARIANTS = byId("kp-download-variants");
    OTHER = byId("kp-other-options");
    DETAILS = byId("kp-other-platforms");
    if (!PRIMARY && !STATUS && !VARIANTS) return;

    setState("detecting", "Detecting your device…");
    setPrimary({ variant: null, state: "detecting", note: "" });

    (async function () {
      detected = await detectPlatform();
      if (detected.os) {
        setState("detected", "Detected " + platformDescription(detected) + ".");
        setState("checking", "Checking the release manifest…");
      }
      manifestDoc = await fetchManifest();
      activeOs = (detected.os && manifestDoc && manifestDoc.channels && manifestDoc.channels[detected.os])
        ? detected.os
        : (manifestDoc && manifestDoc.channels && Object.keys(manifestDoc.channels)[0]) || detected.os;
      if (!manifestDoc || !activeOs) {
        setState("unavailable", "Download manifest unavailable — links stay disabled until a release is verified.");
        setPrimary({ variant: null, state: "unavailable", note: "Manifest unavailable." });
        renderVariants([]);
        renderOther(null);
        return;
      }
      apply();
    })();

    PRIMARY.addEventListener("click", function () {
      if (PRIMARY.hasAttribute("href")) {
        setState("started", "Download started. Verify the SHA-256 checksum before installing.");
      }
    });
  }

  var API = {
    safeUrl: safeUrl,
    isDownloadable: isDownloadable,
    unavailableReason: unavailableReason,
    validManifest: validManifest,
    fetchManifest: fetchManifest,
    detectPlatform: detectPlatform,
    variantsFor: variantsFor,
    resolvePrimary: resolvePrimary,
    platformDescription: platformDescription,
    isUnsupported: isUnsupported,
    MANIFEST_SOURCES: MANIFEST_SOURCES,
  };
  if (typeof globalThis !== "undefined") globalThis.__KEEL_DOWNLOAD__ = API;

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
    else boot();
  }
})();

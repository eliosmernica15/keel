/* /download - OS detection + platform cards
   Manifest sources, in order:
     1. /api/download-manifest  (Vercel function proxying the published R2
        manifest; lets the site flip availability without a redeploy)
     2. /download.json          (committed fallback; stays unavailable until
        a real release has been published and verified)
   No build step. Honest availability: a button is enabled only when the
   manifest marks the channel available, its URL is a public HTTPS URL, and
   size + SHA-256 are present. Never fabricate URLs or point at unhosted files.

   Detection: userAgentData where available (Chromium) for architecture,
   falling back to UA sniffing. Architectures we do not build (Windows ARM,
   Intel macOS) and platforms Keel is not for (iOS, Android) are told
   honestly instead of being handed the wrong installer. */

const GRID = document.getElementById("download-grid");
const DETECT = document.getElementById("detect-note");
const VERSION_PILL = document.getElementById("version-pill");
const HOSTING_NOTE = document.getElementById("hosting-note");

const MANIFEST_SOURCES = ["/api/download-manifest", "/download.json"];
const SHA_RE = /^[0-9a-f]{64}$/i;

async function fetchManifest() {
  for (const url of MANIFEST_SOURCES) {
    try {
      const r = await fetch(url, {
        cache: "no-cache",
        headers: { Accept: "application/json" },
      });
      if (!r.ok) continue;
      const doc = await r.json();
      if (validManifest(doc)) return doc;
    } catch {
      /* try the next source */
    }
  }
  return null;
}

function validManifest(doc) {
  return !!doc && typeof doc === "object"
    && typeof doc.version === "string"
    && !!doc.channels && typeof doc.channels === "object";
}

/* Public links must be HTTPS. Loopback HTTP is accepted only so the page can
   be exercised locally; it is never emitted by the release pipeline. */
function safeUrl(value) {
  if (!value) return null;
  try {
    const u = new URL(String(value), window.location.href);
    if (u.protocol === "https:") return u.href;
    if (u.protocol === "http:" && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(u.hostname)) {
      return u.href;
    }
  } catch {
    /* malformed URL */
  }
  return null;
}

function isDownloadable(ch) {
  return !!ch && ch.available === true
    && ch.verified === true
    && Number.isFinite(Number(ch.size)) && Number(ch.size) > 0
    && SHA_RE.test(String(ch.sha256 || ""))
    && safeUrl(ch.url) !== null;
}

function fmtBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return null;
  const mb = n / 1024 / 1024;
  return `${mb >= 100 ? mb.toFixed(1) : mb.toFixed(2)} MB`;
}

/* Returns { os: 'windows'|'macos'|'linux'|'ios'|'android'|null, arch: 'x64'|'arm64'|'arm'|null } */
async function detectPlatform() {
  const ua = navigator.userAgent || "";

  if (/iPhone|iPad|iPod/.test(ua)) return { os: "ios", arch: null };
  if (/Android/.test(ua)) return { os: "android", arch: null };

  // Architecture, when the browser tells us (Chromium userAgentData).
  let arch = null;
  try {
    if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
      const hints = await navigator.userAgentData.getHighEntropyValues(["architecture", "bitness", "platform"]);
      const a = (hints.architecture || "").toLowerCase();
      if (a === "arm") arch = hints.bitness === "64" || !hints.bitness ? "arm64" : "arm";
      else if (a === "x86") arch = "x64";
      else if (a) arch = a;
    }
  } catch {
    /* hints unavailable; UA only */
  }

  let os = null;
  if (/Windows/.test(ua) || (navigator.userAgentData && /windows/i.test(navigator.userAgentData.platform || ""))) {
    os = "windows";
    if (!arch && /Win64|x64|WOW64/.test(ua)) arch = "x64";
  } else if (/Mac OS|Macintosh|Mac OS X/.test(ua) || (navigator.userAgentData && /macos/i.test(navigator.userAgentData.platform || ""))) {
    os = "macos"; // arch stays null unless hints told us (Apple Silicon exposes arm)
  } else if (/Linux/.test(ua) || (navigator.userAgentData && /linux/i.test(navigator.userAgentData.platform || ""))) {
    os = "linux";
    if (!arch) arch = "x64";
  }
  return { os, arch };
}

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function copyButton(sha256) {
  const btn = el("button", "copy-btn", "Copy SHA-256");
  btn.type = "button";
  btn.title = "Copy the SHA-256 checksum";
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(sha256);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = sha256;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch { /* clipboard unavailable */ }
      ta.remove();
    }
    btn.textContent = "Copied";
    btn.disabled = true;
    setTimeout(() => { btn.textContent = "Copy SHA-256"; btn.disabled = false; }, 1600);
  });
  return btn;
}

function renderCard(os, channel, version, highlight) {
  const card = el("article", "card" + (highlight ? " card-highlight" : ""));
  const downloadable = isDownloadable(channel);
  const osName = channel.name || (os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux x64");

  const head = el("div", "channel-head");
  head.appendChild(el("small", null, `Keel for ${osName}`));
  if (downloadable && channel.verified) {
    head.appendChild(el("span", "verified", "SHA-256 verified"));
  }

  const h = el("h2", null, channel.name || osName);
  const metaLines = [];
  metaLines.push(`Version: ${channel.version || version}  ·  ${channel.arch || "unknown arch"}`);
  if (channel.file) metaLines.push(channel.file);
  const size = fmtBytes(channel.size);
  if (size) metaLines.push(`Size: ${size} (${Number(channel.size).toLocaleString()} bytes)`);
  const meta = el("p", "meta", metaLines.join("\n"));

  const parts = [head, h, meta];

  if (channel.sha256) {
    const row = el("div", "checkrow");
    const code = el("code", null, String(channel.sha256));
    row.appendChild(code);
    row.appendChild(copyButton(String(channel.sha256)));
    parts.push(
      el("small", null, downloadable ? "SHA-256 (verified over HTTPS)" : "SHA-256 (last CI build; not hosted)"),
      row
    );
  }
  if (channel.notes) parts.push(el("p", "notes", channel.notes));
  if (channel.installation) parts.push(el("p", "notes", channel.installation));

  const btn = document.createElement(downloadable ? "a" : "span");
  btn.className = "btn-download";
  if (downloadable) {
    btn.href = safeUrl(channel.url);
    btn.rel = "noopener";
    btn.textContent = "Download " + (channel.file || osName);
  } else {
    btn.setAttribute("aria-disabled", "true");
    btn.setAttribute("role", "link");
    btn.textContent = "Not currently available";
    btn.style.pointerEvents = "none";
  }
  parts.push(btn);

  const alternatives = (channel.alternatives || [])
    .map((alt) => ({ alt, href: safeUrl(alt && alt.url) }))
    .filter(({ alt, href }) => href && alt && alt.file && SHA_RE.test(String(alt.sha256 || "")));
  if (alternatives.length) {
    const row = el("div", "alts");
    row.appendChild(el("span", null, "Also available:"));
    for (const { alt, href } of alternatives) {
      const a = document.createElement("a");
      a.href = href;
      a.rel = "noopener";
      a.textContent = alt.label || alt.file;
      a.title = [alt.file, fmtBytes(alt.size), alt.sha256].filter(Boolean).join(" · ");
      row.appendChild(a);
    }
    parts.push(row);
  }

  card.append(...parts);
  return card;
}

function renderUnavailable(title, note) {
  const card = el("article", "card card-highlight");
  card.append(el("h2", null, title), el("p", "notes", note));
  return card;
}

function setHostingNote(anyAvailable) {
  if (!HOSTING_NOTE) return;
  HOSTING_NOTE.textContent = anyAvailable
    ? "Download links point at Keel-controlled storage. Every published file was " +
      "downloaded over public HTTPS and matched against its SHA-256 by the release " +
      "workflow before this page listed it. Installers are unsigned: SmartScreen and " +
      "Gatekeeper will warn until code signing is configured. Uninstalling never " +
      "touches your ~/.keel directory."
    : "No installer is publicly available yet. The release workflow publishes a " +
      "download only after uploading it and verifying its SHA-256 over public HTTPS. " +
      "Uninstalling never touches your ~/.keel directory. Installers are unsigned: " +
      "SmartScreen and Gatekeeper will warn until code signing is configured.";
}

async function main() {
  const m = await fetchManifest();
  if (VERSION_PILL && m && m.version) VERSION_PILL.textContent = "v" + m.version;

  if (!GRID) return;

  if (!m) {
    if (DETECT) DETECT.textContent = "Download manifest unavailable.";
    GRID.append(renderUnavailable(
      "Keel is not yet publicly available",
      "Downloads will appear on this page once installers are built, hosted and checksum-verified. Check back soon."
    ));
    setHostingNote(false);
    return;
  }

  const detected = await detectPlatform();
  const anyAvailable = Object.values(m.channels || {}).some(isDownloadable);
  setHostingNote(anyAvailable);

  // Platforms Keel is not a product for, and architectures we do not build yet.
  if (detected.os === "ios" || detected.os === "android") {
    if (DETECT) DETECT.textContent = "Keel is a desktop app for Windows, macOS and Linux.";
    GRID.append(renderUnavailable(
      "Keel doesn't run on " + (detected.os === "ios" ? "iOS" : "Android"),
      "Keel is a local, private coding workspace for desktop machines. The installers below are for Windows, macOS (Apple Silicon) and Linux (x64)."
    ));
    return renderCards(m, null);
  }
  if (detected.os === "windows" && detected.arch === "arm64") {
    if (DETECT) DETECT.textContent = "Detected Windows on ARM — not supported by the current build yet.";
    GRID.append(renderUnavailable(
      "Windows on ARM isn't supported yet",
      "The current installer is x64. Run it under emulation (Prism) on Windows 11 ARM, or wait for a native build."
    ));
    return renderCards(m, null);
  }
  if (detected.os === "macos" && detected.arch === "x64") {
    if (DETECT) DETECT.textContent = "Detected an Intel Mac — the current build is Apple Silicon only.";
    GRID.append(renderUnavailable(
      "Intel Macs aren't supported by this build yet",
      "Keel currently ships macOS arm64 only. An Intel build needs a separate target; the page will list it here once it exists."
    ));
    return renderCards(m, null);
  }

  if (detected.os) {
    const label = detected.os === "windows" ? "Windows" + (detected.arch ? " " + detected.arch : "")
      : detected.os === "macos" ? "macOS" + (detected.arch === "arm64" ? " (Apple Silicon)" : "")
      : "Linux";
    if (DETECT) DETECT.textContent = `Detected ${label}.`;
  } else {
    if (DETECT) DETECT.textContent = "Could not detect your platform - pick one below.";
  }

  renderCards(m, detected.os);
}

function renderCards(m, detected) {
  const order = ["windows", "macos", "linux"].filter((k) => m.channels && m.channels[k]);
  if (detected && order.includes(detected)) {
    order.splice(order.indexOf(detected), 1);
    order.unshift(detected);
  }
  for (const os of order) {
    const ch = m.channels && m.channels[os];
    if (!ch) continue;
    GRID.append(renderCard(os, ch, m.version, os === detected));
  }
}

main();

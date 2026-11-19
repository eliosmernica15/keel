/* /download — OS detection + platform cards
   Reads /download.json. No build step.
   Honest availability: only 'available' channels render a download button.
   Do not fabricate URLs or point at unhosted artifacts. */

const GRID = document.getElementById("download-grid");
const DETECT = document.getElementById("detect-note");
const VERSION_PILL = document.getElementById("version-pill");

const MANIFEST_CANDIDATES = ["download.json"];

async function fetchManifest() {
  for (const path of MANIFEST_CANDIDATES) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (r.ok) return r.json();
    } catch {
      /* try next */
    }
  }
  return null;
}

function detectOS() {
  const ua = navigator.userAgent || "";
  if (/Windows/.test(ua)) return "windows";
  if (/Mac OS/.test(ua)) return "macos";
  if (/Linux/.test(ua)) return "linux";
  if (/Android/.test(ua)) return "linux";
  if (/iPhone|iPad/.test(ua)) return "macos";
  return null;
}

function channelFromManifest(m, os) {
  return (m && m.channels && m.channels[os]) || null;
}

function el(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function renderCard(os, channel, highlight) {
  const osName = channel.name || (os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux x64");
  const card = el("article", "card" + (highlight ? " card-highlight" : ""));
  const small = el("small", null, `Keel for ${osName}`);
  const h = el("h2", null, channel.name || osName);
  const metaLines = [channel.file];
  if (channel.size) metaLines.push("Size: " + (channel.size / 1024 / 1024).toFixed(1) + " MB");
  if (channel.sha256) metaLines.push("SHA-256: " + channel.sha256);
  const meta = el("p", "meta", metaLines.join("\n"));
  const notes = el("p", "notes", channel.notes || "");
  const install = channel.installation ? el("p", "notes", channel.installation) : null;

  const btn = document.createElement("a");
  btn.className = "btn-download";
  const canDownload = channel.available && channel.url;
  if (canDownload) {
    btn.href = channel.url;
    btn.rel = "noopener";
    btn.textContent = "Download " + (channel.file || "");
  } else {
    btn.setAttribute("aria-disabled", "true");
    btn.setAttribute("role", "link");
    btn.textContent = "Not currently available";
    btn.style.pointerEvents = "none";
  }

  card.append(small, h, meta, notes);
  if (install) card.append(install);
  card.append(btn);
  return card;
}

async function main() {
  const m = await fetchManifest();
  if (VERSION_PILL && m?.version) VERSION_PILL.textContent = "v" + m.version;

  if (!m) {
    if (DETECT) DETECT.textContent = "Download manifest unavailable.";
    const card = el("article", "card");
    card.innerHTML = '<h2>Keel is not yet publicly available</h2><p class="notes">Downloads will be available from this page once installers are built and hosted. Check back soon.</p>';
    GRID.append(card);
    return;
  }

  const detected = detectOS();
  if (detected && channelFromManifest(m, detected)) {
    DETECT.textContent = `Detected ${detected === "windows" ? "Windows" : detected === "macos" ? "macOS" : "Linux"}.`;
  } else {
    DETECT.textContent = "Could not detect your platform — pick one below.";
  }

  const order = ["windows", "macos", "linux"].filter((k) => channelFromManifest(m, k));
  if (detected && order.includes(detected)) {
    order.splice(order.indexOf(detected), 1);
    order.unshift(detected);
  }

  for (const os of order) {
    const ch = channelFromManifest(m, os);
    if (!ch) continue;
    GRID.append(renderCard(os, ch, os === detected));
  }
}

main();

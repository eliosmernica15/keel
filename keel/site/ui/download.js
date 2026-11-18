/* /download — OS detection + platform cards
   Reads /download.json (served next to this page). No build step.
   Release-note text links to the tag. destinations are read from the json,
   which makes switching hosting providers a config change, not a code change. */

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
  const arch = ((navigator.userAgentData && navigator.userAgentData.platform) || "").toLowerCase();
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
  const card = el("article", "card" + (highlight ? " card-highlight" : ""));
  const small = el("small", null, "Keel for " + (channel.osName || os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux"));
  const h = el("h2", null, channel.name);
  const badge = el("span", "badge", "SHA-256 shown");
  const meta = el("p", "meta", [
    `${channel.file}`,
    channel.size ? `Size: ${(channel.size / 1024 / 1024).toFixed(1)} MB` : null,
    channel.sha256 ? `sha256: ${channel.sha256}` : null,
  ].filter(Boolean).join("\n"));
  const notes = el("p", "notes", channel.notes || "");
  const btn = document.createElement("a");
  btn.className = "btn-download";
  if (channel.url) {
    btn.href = channel.url;
    btn.rel = "noopener";
    btn.textContent = "Download " + (channel.file || "");
  } else {
    btn.setAttribute("aria-disabled", "true");
    btn.setAttribute("role", "link");
    btn.textContent = "Artifact not yet hosted";
  }
  card.append(small, h, badge, meta, notes, btn);
  return card;
}

async function main() {
  const m = await fetchManifest();
  const detected = detectOS();

  if (m?.version && VERSION_PILL) VERSION_PILL.textContent = "v" + m.version;

  if (!m) {
    DETECT.textContent = "Download manifest unavailable — see the GitHub release page.";
    const card = el("article", "card");
    card.innerHTML = '<h2>Manual download</h2><p class="notes">The download manifest failed to load. You can still download the installer from the GitHub Releases page.</p>';
    const btn = document.createElement("a");
    btn.className = "btn-download";
    btn.href = "https://github.com/eliosmernica15/keel/releases/latest";
    btn.textContent = "Open GitHub Releases";
    card.append(btn);
    GRID.append(card);
    return;
  }

  const order = ["windows", "macos", "linux"].filter((k) => channelFromManifest(m, k));
  if (detected && order.includes(detected)) {
    // move detected OS first
    order.splice(order.indexOf(detected), 1);
    order.unshift(detected);
  }

  const label = detected === "windows" ? "Windows" : detected === "macos" ? "macOS" : detected === "linux" ? "Linux" : null;
  DETECT.textContent = label ? `Detected ${label}. Download below.` : "Could not detect your platform — pick one below.";

  for (const os of order) {
    const ch = channelFromManifest(m, os);
    GRID.append(renderCard(os, ch, os === detected));
  }

  if (!detected) {
    DETECT.textContent = "Could not detect your platform — pick one below.";
  }
}

main();

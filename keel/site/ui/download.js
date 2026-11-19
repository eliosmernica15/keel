/* /download - OS detection + platform cards
   Reads /download.json. No build step.
   Honest availability: only 'available' channels render a download button.
   Do not fabricate URLs or point at unhosted artifacts.

   Detection: userAgentData where available (Chromium) for architecture,
   falling back to UA sniffing. Architecture we do not build (Windows ARM,
   Intel macOS) and platforms Keel is not for (iOS, Android) are told
   honestly instead of being handed the wrong installer. */

const GRID = document.getElementById("download-grid");
const DETECT = document.getElementById("detect-note");
const VERSION_PILL = document.getElementById("version-pill");

async function fetchManifest() {
  try {
    const r = await fetch("download.json", { cache: "no-cache" });
    if (r.ok) return r.json();
  } catch {
    /* manifest unreachable */
  }
  return null;
}

/* Returns { os: 'windows'|'macos'|'linux'|'ios'|'android'|null, arch: 'x64'|'arm64'|'arm'|null, note } */
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

function renderCard(os, channel, highlight) {
  const card = el("article", "card" + (highlight ? " card-highlight" : ""));
  const osName = channel.name || (os === "windows" ? "Windows" : os === "macos" ? "macOS" : "Linux x64");
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
  if (channel.available && channel.url) {
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

function renderUnavailable(title, note) {
  const card = el("article", "card card-highlight");
  card.append(el("h2", null, title), el("p", "notes", note));
  return card;
}

async function main() {
  const m = await fetchManifest();
  if (VERSION_PILL && m && m.version) VERSION_PILL.textContent = "v" + m.version;

  if (!GRID) return;

  if (!m) {
    if (DETECT) DETECT.textContent = "Download manifest unavailable.";
    GRID.append(renderUnavailable(
      "Keel is not yet publicly available",
      "Downloads will appear on this page once installers are built and hosted. Check back soon."
    ));
    return;
  }

  const detected = await detectPlatform();

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
    GRID.append(renderCard(os, ch, os === detected));
  }
}

main();

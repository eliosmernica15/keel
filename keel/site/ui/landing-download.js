/* Landing-page availability, driven by the same verified manifest as /download.
   No hardcoded URLs or checksums: an installer button is enabled only when the
   manifest marks the channel available with an HTTPS URL, byte size and
   SHA-256. If the manifest cannot be read, the static "not available" state
   stays in place. */

const SOURCES = ["/api/download-manifest", "/download.json"];
const SHA_RE = /^[0-9a-f]{64}$/i;
const PLATFORM_LABEL = { windows: "Windows", macos: "macOS", linux: "Linux" };
const PLATFORM_DETAIL = {
  windows: ["NSIS · per-user install, no admin"],
  macos: ["Apple Silicon", "DMG + ZIP"],
  linux: ["AppImage + .deb"],
};

async function fetchManifest() {
  for (const url of SOURCES) {
    try {
      const response = await fetch(url, {
        cache: "no-cache",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) continue;
      const doc = await response.json();
      if (doc && typeof doc === "object" && typeof doc.version === "string"
          && doc.channels && typeof doc.channels === "object") {
        return doc;
      }
    } catch {
      /* try the next source */
    }
  }
  return null;
}

function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(String(value), window.location.href);
    if (url.protocol === "https:") return url.href;
    if (url.protocol === "http:" && /^(localhost|127\.0\.0\.1|\[::1\])$/.test(url.hostname)) {
      return url.href;
    }
  } catch {
    /* malformed */
  }
  return null;
}

function downloadable(channel) {
  return !!channel && channel.available === true
    && channel.verified === true
    && Number.isFinite(Number(channel.size)) && Number(channel.size) > 0
    && SHA_RE.test(String(channel.sha256 || ""))
    && safeUrl(channel.url) !== null;
}

function fmtBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return null;
  const mb = n / 1024 / 1024;
  return `${mb >= 100 ? mb.toFixed(1) : mb.toFixed(2)} MB`;
}

function appendItem(list, fragments) {
  const item = document.createElement("li");
  for (const fragment of fragments) {
    item.append(fragment);
  }
  list.append(item);
}

function updateCard(card, channel) {
  const os = card.dataset.os;
  const ok = downloadable(channel);
  const name = channel && channel.name ? channel.name : PLATFORM_LABEL[os] || os;

  const badge = card.querySelector("[data-badge]");
  if (badge) {
    badge.textContent = ok ? "Available" : "Not available";
    badge.classList.toggle("badge-available", ok);
    badge.classList.toggle("badge-pending", !ok);
  }

  const file = card.querySelector("[data-file]");
  if (file && channel && channel.file) file.textContent = channel.file;

  const meta = card.querySelector("[data-meta]");
  if (meta && channel) {
    meta.replaceChildren();
    for (const detail of PLATFORM_DETAIL[os] || []) {
      appendItem(meta, [document.createTextNode(detail)]);
    }
    if (channel.arch) {
      appendItem(meta, [document.createTextNode(`${channel.arch} · ${channel.version || ""}`.trim())]);
    }
    const size = fmtBytes(channel.size);
    if (size) appendItem(meta, [document.createTextNode(size)]);
    if (channel.sha256) {
      const code = document.createElement("code");
      code.textContent = String(channel.sha256).slice(0, 12) + "…";
      appendItem(meta, [
        document.createTextNode("SHA-256 "),
        code,
        document.createTextNode(ok ? " (verified over HTTPS)" : " (CI build; not hosted)"),
      ]);
    }
    appendItem(meta, [document.createTextNode(
      ok ? "Unsigned — SmartScreen/Gatekeeper will warn" : "Unsigned — no public download yet"
    )]);
  }

  const cta = card.querySelector("[data-cta]");
  if (!cta) return;
  if (ok) {
    cta.href = safeUrl(channel.url);
    cta.textContent = `Download for ${PLATFORM_LABEL[os] || name}`;
    cta.removeAttribute("aria-disabled");
    cta.classList.remove("btn-disabled");
    cta.setAttribute("rel", "noopener");
  } else {
    cta.href = "/download";
    cta.textContent = "Not publicly available";
    cta.setAttribute("aria-disabled", "true");
    cta.classList.add("btn-disabled");
  }
}

async function main() {
  const manifest = await fetchManifest();
  if (!manifest) return;

  const cards = document.querySelectorAll("#platform-grid [data-os]");
  let anyAvailable = false;
  for (const card of cards) {
    const channel = manifest.channels[card.dataset.os];
    if (!channel) continue;
    if (downloadable(channel)) anyAvailable = true;
    updateCard(card, channel);
  }

  const note = document.getElementById("landing-download-note");
  if (note) {
    note.textContent = anyAvailable
      ? "Download links point at Keel-controlled storage. Every published file was downloaded over public HTTPS and matched against its SHA-256 before this page listed it."
      : "Installers will appear on /download the moment a release is built, published and SHA-256 verified over public HTTPS. Until then, nothing here is secretly downloadable — that's deliberate.";
  }
}

main();

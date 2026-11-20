/* Same-origin proxy for the published download manifest.
 *
 * The site is static. In production the public, non-secret environment
 * variable KEEL_DOWNLOAD_MANIFEST_URL must point at the first-party,
 * binaries-only download endpoint. No source-repository URL is embedded here.
 * Until that endpoint exists this function returns 503 and the page falls back
 * to the committed /download.json, which reports no available installer.
 *
 * Never place credentials here.
 */

const DEFAULT_MANIFEST_URL = "";
const MAX_BYTES = 256 * 1024;

function fail(res, status, error) {
  res.status(status).json({ error });
}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return fail(res, 405, "method_not_allowed");
  }

  const configured = process.env.KEEL_DOWNLOAD_MANIFEST_URL || DEFAULT_MANIFEST_URL;
  if (!configured) {
    return fail(res, 503, "manifest_not_configured");
  }
  let target;
  try {
    target = new URL(configured);
  } catch {
    return fail(res, 503, "manifest_url_invalid");
  }
  if (target.protocol !== "https:") {
    return fail(res, 503, "manifest_url_insecure");
  }

  let upstream;
  try {
    upstream = await fetch(target, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      redirect: "follow",
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    return fail(res, 502, "manifest_unreachable");
  }
  if (!upstream.ok) {
    return fail(res, 502, "manifest_unreachable");
  }

  let text;
  try {
    text = await upstream.text();
  } catch {
    return fail(res, 502, "manifest_unreadable");
  }
  if (text.length > MAX_BYTES) {
    return fail(res, 502, "manifest_too_large");
  }

  let doc;
  try {
    doc = JSON.parse(text);
  } catch {
    return fail(res, 502, "manifest_not_json");
  }
  if (!doc || typeof doc !== "object"
      || typeof doc.version !== "string"
      || !doc.channels || typeof doc.channels !== "object") {
    return fail(res, 502, "manifest_invalid");
  }

  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "public, max-age=60, s-maxage=60, stale-while-revalidate=300");
  res.status(200).send(text);
};

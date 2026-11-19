/* Same-origin proxy for the published download manifest.
 *
 * The site is static; the Python release manager publishes download.json as an
 * asset of the latest GitHub Release attached to this repository. Fetching it
 * here (rather than in the browser) keeps the page free of third-party
 * connect-src rules and lets availability change without redeploying the
 * website.
 *
 * Configure the origin with the public, non-secret Vercel environment
 * variable KEEL_DOWNLOAD_MANIFEST_URL (defaults to the latest GitHub Release
 * asset). Never place credentials here.
 */

const DEFAULT_MANIFEST_URL =
  "https://github.com/eliosmernica15/keel/releases/latest/download/download.json";
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

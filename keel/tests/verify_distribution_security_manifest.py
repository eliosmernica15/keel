"""Agent F — distribution security: manifest proxy, download page, service worker.

Deterministic checks only: the serverless handler is executed in-process under
Node with a mocked ``fetch`` (no network), and the browser/SW sources are
inspected as text. Known gaps are marked ``xfail(strict=False)`` with the
offending file:line in the reason, so the suite stays green while the defect is
visible and turns into an XPASS when the control is actually added.

Nothing in this file modifies the controls it checks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PROXY = SITE / "api" / "download-manifest.js"
DOWNLOAD_JS = SITE / "ui" / "download.js"
SW_JS = SITE / "sw.js"
FALLBACK = SITE / "download.json"

NODE = shutil.which("node")


# Node harness: loads the real CommonJS handler and drives it with a mocked
# global fetch. Every scenario captures status, headers, body and fetch options.
_HARNESS = r"""
const handler = require(process.argv[2]);

function mockFetch(spec) {
  return async (url, opts) => {
    globalThis.__captured = { url: String(url), opts: opts || {} };
    if (spec.throw) throw new Error("mock fetch failure");
    return {
      ok: spec.ok !== false,
      status: spec.status || 200,
      text: async () => spec.body,
    };
  };
}

async function invoke(method, envUrl, fetchImpl) {
  const oldFetch = globalThis.fetch;
  const hadEnv = Object.prototype.hasOwnProperty.call(
    process.env, "KEEL_DOWNLOAD_MANIFEST_URL");
  const oldEnv = process.env.KEEL_DOWNLOAD_MANIFEST_URL;
  if (envUrl === null) delete process.env.KEEL_DOWNLOAD_MANIFEST_URL;
  else process.env.KEEL_DOWNLOAD_MANIFEST_URL = envUrl;
  globalThis.fetch = fetchImpl;
  const out = { status: null, headers: {}, body: null, fetch: null };
  const res = {
    status(code) { out.status = code; return this; },
    setHeader(k, v) { out.headers[String(k).toLowerCase()] = String(v); return this; },
    json(obj) { out.body = JSON.stringify(obj); return this; },
    send(text) { out.body = text; return this; },
  };
  globalThis.__captured = null;
  try {
    await handler({ method: method }, res);
  } finally {
    globalThis.fetch = oldFetch;
    if (hadEnv) process.env.KEEL_DOWNLOAD_MANIFEST_URL = oldEnv;
    else delete process.env.KEEL_DOWNLOAD_MANIFEST_URL;
  }
  out.fetch = globalThis.__captured;
  return out;
}

(async () => {
  const good = JSON.stringify({ version: "0.1.1", channels: { windows: {} } });
  const multibyte = JSON.stringify({
    version: "0.1.1", channels: {}, pad: "\u00e9".repeat(200000)
  });
  const r = {};
  r.method = await invoke("POST", "https://example.com/m.json", mockFetch({ body: good }));
  r.unset = await invoke("GET", null, mockFetch({ body: good }));
  r.insecure = await invoke("GET", "http://example.com/m.json", mockFetch({ body: good }));
  r.oversize = await invoke("GET", "https://example.com/m.json",
    mockFetch({ body: "x".repeat(256 * 1024 + 1) }));
  r.multibyte = await invoke("GET", "https://example.com/m.json", mockFetch({ body: multibyte }));
  r.notjson = await invoke("GET", "https://example.com/m.json", mockFetch({ body: "not json" }));
  r.invalid = await invoke("GET", "https://example.com/m.json",
    mockFetch({ body: JSON.stringify({ hello: 1 }) }));
  r.ok = await invoke("GET", "https://example.com/m.json", mockFetch({ body: good }));
  r.upstream_fail = await invoke("GET", "https://example.com/m.json",
    mockFetch({ ok: false, status: 503, body: "" }));
  r.fetch_throw = await invoke("GET", "https://example.com/m.json",
    mockFetch({ throw: true, body: "" }));
  console.log(JSON.stringify(r));
})().catch((e) => { console.error(e); process.exitCode = 1; });
"""


@pytest.fixture(scope="module")
def proxy_results(tmp_path_factory):
    """Run the real handler once; all proxy tests share its observed results."""
    if NODE is None:
        pytest.skip("node is required to execute the JS handler")
    out = tmp_path_factory.mktemp("download-proxy")
    harness = out / "harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(harness), str(PROXY)],
        capture_output=True, text=True, timeout=30, cwd=str(SITE),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# The download page exports its pure decision functions on globalThis so they
# can be exercised without a browser. Drive those real functions under Node.
_DOWNLOAD_HARNESS = r"""
require(process.argv[2]);
var api = globalThis.__KEEL_DOWNLOAD__;
if (!api || typeof api.isDownloadable !== "function") {
  console.error("download page did not export __KEEL_DOWNLOAD__");
  process.exit(2);
}
var sha = "a".repeat(64);
function channel(extra) {
  return Object.assign({
    available: true, verified: true,
    verified_at: "2026-11-25T00:00:00Z", size: 1234, sha256: sha,
    url: "https://github.com/example/keel/releases/download/v0.1.1/Keel-Setup-0.1.1.exe",
    file: "Keel-Setup-0.1.1.exe", arch: "x64"
  }, extra || {});
}
var r = {};
r.safe_https = api.safeUrl("https://github.com/example/keel/setup.exe");
r.safe_http_public = api.safeUrl("http://evil.example/setup.exe");
r.safe_js = api.safeUrl("javascript:alert(1)");
r.safe_first_party = api.safeUrl("https://evil.example/Keel-Setup.exe");
r.good = api.isDownloadable(channel());
r.not_verified = api.isDownloadable(channel({ verified: false }));
r.no_timestamp = api.isDownloadable(channel({ verified_at: null }));
r.bad_sha = api.isDownloadable(channel({ sha256: "short" }));
r.bad_size = api.isDownloadable(channel({ size: 0 }));
r.http_url = api.isDownloadable(channel({ url: "http://evil.example/setup.exe" }));
r.not_available = api.isDownloadable(channel({ available: false }));
r.sources = api.MANIFEST_SOURCES;
console.log(JSON.stringify(r));
"""


@pytest.fixture(scope="module")
def download_api(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is required to execute the download decision functions")
    out = tmp_path_factory.mktemp("download-api")
    harness = out / "harness.js"
    harness.write_text(_DOWNLOAD_HARNESS, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(harness), str(DOWNLOAD_JS)],
        capture_output=True, text=True, timeout=30, cwd=str(SITE),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# 1. Manifest proxy
# --------------------------------------------------------------------------

def test_proxy_is_get_only(proxy_results):
    r = proxy_results["method"]
    assert r["status"] == 405
    assert r["headers"].get("allow") == "GET"
    assert "method_not_allowed" in r["body"]


def test_proxy_returns_503_without_configured_manifest(proxy_results):
    r = proxy_results["unset"]
    assert r["status"] == 503
    assert "manifest_not_configured" in r["body"]
    assert r["fetch"] is None  # never reaches the network


def test_proxy_rejects_insecure_upstream(proxy_results):
    r = proxy_results["insecure"]
    assert r["status"] == 503
    assert "manifest_url_insecure" in r["body"]
    assert r["fetch"] is None


def test_proxy_enforces_size_cap(proxy_results):
    r = proxy_results["oversize"]
    assert r["status"] == 502
    assert "manifest_too_large" in r["body"]


def test_proxy_rejects_non_json_and_invalid_shape(proxy_results):
    assert proxy_results["notjson"]["status"] == 502
    assert "manifest_not_json" in proxy_results["notjson"]["body"]
    assert proxy_results["invalid"]["status"] == 502
    assert "manifest_invalid" in proxy_results["invalid"]["body"]


def test_proxy_fails_closed_on_upstream_errors(proxy_results):
    assert proxy_results["upstream_fail"]["status"] == 502
    assert "manifest_unreachable" in proxy_results["upstream_fail"]["body"]
    assert proxy_results["fetch_throw"]["status"] == 502
    assert "manifest_unreachable" in proxy_results["fetch_throw"]["body"]


def test_proxy_valid_response_has_json_type_cache_control_and_no_credentials(proxy_results):
    r = proxy_results["ok"]
    assert r["status"] == 200
    assert r["headers"].get("content-type", "").startswith("application/json")
    assert "max-age" in r["headers"].get("cache-control", "")
    assert r["fetch"] is not None
    opts = r["fetch"]["opts"]
    assert opts.get("cache") == "no-store"
    headers = {str(k).lower(): str(v) for k, v in (opts.get("headers") or {}).items()}
    assert headers == {"accept": "application/json"}  # no Authorization/Cookie


def test_proxy_does_not_follow_unvalidated_redirects(proxy_results):
    assert proxy_results["ok"]["fetch"]["opts"].get("redirect") != "follow"


def test_proxy_size_cap_is_enforced_in_bytes(proxy_results):
    assert proxy_results["multibyte"]["status"] == 502


# --------------------------------------------------------------------------
# 2. Download page integrity (Agent A owns download.js — read-only review)
# --------------------------------------------------------------------------

def test_download_page_only_accepts_https_or_loopback_urls(download_api):
    assert download_api["safe_https"].startswith("https://")
    assert download_api["safe_http_public"] is None
    assert download_api["safe_js"] is None


def test_download_page_requires_available_verified_timestamp_size_sha_and_url(download_api):
    assert download_api["good"] is True
    for key in ("not_verified", "no_timestamp", "bad_sha", "bad_size",
                "http_url", "not_available"):
        assert download_api[key] is False, key


def test_download_page_renders_manifest_text_without_html_injection():
    src = DOWNLOAD_JS.read_text(encoding="utf-8")
    assert ".innerHTML" not in src
    assert ".textContent" in src


def test_download_page_has_no_fabricated_or_hardcoded_asset_url(download_api):
    assert download_api["sources"] == ["/api/download-manifest", "/download.json"]
    src = DOWNLOAD_JS.read_text(encoding="utf-8")
    assert "https://github.com/" not in src
    assert "http://" not in src.replace("http://127.0.0.1", "").replace(
        "http://localhost", "").replace("http://[::1]", "")


def test_download_page_restricts_urls_to_approved_first_party_hosts(download_api):
    assert download_api["safe_first_party"] is None, (
        "safeUrl() accepted an unapproved https origin (https://evil.example)")


def test_download_page_discloses_unsigned_os_signing_status():
    text = (DOWNLOAD_JS.read_text(encoding="utf-8")
            + (SITE / "download.html").read_text(encoding="utf-8")).lower()
    assert "unsigned" in text
    assert "smartscreen" in text or "gatekeeper" in text


def test_fallback_manifest_never_claims_availability_or_verification():
    doc = json.loads(FALLBACK.read_text(encoding="utf-8"))
    assert doc.get("base_url") is None
    assert doc.get("release_manifest_url") is None
    assert doc.get("published_at") is None
    assert doc.get("verified_at") is None
    for name, ch in doc["channels"].items():
        assert ch["available"] is False, name
        assert ch["verified"] is False, name
        assert ch["url"] is None and ch["size"] is None and ch["sha256"] is None, name
        for alt in ch.get("alternatives", []):
            assert alt["available"] is False and alt["verified"] is False, (name, alt)


# --------------------------------------------------------------------------
# 3. Service worker
# --------------------------------------------------------------------------

def test_service_worker_caches_app_shell_only():
    src = SW_JS.read_text(encoding="utf-8")
    shell = src.split("const SHELL = [", 1)[1].split("];", 1)[0]
    assert '"/app"' in shell  # the real application route, never /download
    assert '"/download"' not in shell
    for forbidden in (".exe", ".dmg", ".deb", ".rpm", ".AppImage", ".zip",
                      "download.json", "/api/"):
        assert forbidden not in shell, forbidden
    assert "const CACHEABLE = new Set(SHELL);" in src
    assert "const NEVER_CACHE = [" in src


def test_service_worker_never_caches_release_metadata_or_binaries():
    src = SW_JS.read_text(encoding="utf-8")
    assert '/^\\/api\\//' in src
    assert '/^\\/download\\.json$/' in src
    assert "(exe|msi|dmg|pkg|deb|rpm|AppImage|zip" in src
    # Every cache write must be gated by the explicit isCacheable check.
    assert src.count("cache.put(") >= 1
    assert src.count("isCacheable(") >= src.count("cache.put(")
    assert "headers.has(\"Content-Disposition\")" in src


def test_service_worker_ignores_cross_origin_traffic_and_secrets():
    src = SW_JS.read_text(encoding="utf-8")
    assert "url.origin !== location.origin" in src
    assert "request.method !== \"GET\"" in src
    for secret in ("token", "Authorization", "Bearer", "secret", "KEEL_TOKEN"):
        assert secret.lower() not in src.lower(), secret

"""Contract tests for the W7.x P0 security features.

Additive, stdlib-only contracts in ``keel.security_contracts``. These tests
pin the security invariants without importing or patching the live
application: no network, no subprocess, no cryptography dependency.

Feature coverage:
    W7.1  typed trust boundaries (client / daemon / agent / host API / third party)
    W7.3  AES-256-GCM sealing (12-byte IV, auth tag, AAD) + session cookie
    W7.4  API keys: prefixed token, SHA-256-only storage, rate limit, idempotency
    W7.5  staged secret files, never secrets in argv
    W7.6  log redaction + keyed pseudonyms for identifiers
    W7.8  trusted-proxy client address, pairing rate limits, relative return path
    W7.10 SSRF-safe fetch: resolve-then-pin, redirect re-check, caps, no leaks
    W7.13 served-UI security headers (CSP / XFO / HSTS / nosniff / COOP / PP)
    W7.14 rendering safety: escaped Markdown, link allowlist, sandboxed previews
    W7.16 publish path selector: containment, no hidden files, no symlinks
    W7.17 inbound channel rules: constant-time HMAC, freshness, replay, fail-closed
    W7.19 honest known-limitations list
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

import pytest

from keel.security_contracts import (
    API_KEY_PREFIX,
    FRESHNESS_WINDOW_SECONDS,
    KNOWN_LIMITATIONS,
    LINK_SCHEME_ALLOWLIST,
    SECRET_KEY_BYTES,
    TRUST_BOUNDARIES,
    TRUST_MODEL,
    AdmissionDecision,
    ApiKeyDecision,
    ApiKeyIssueResult,
    ApiKeyStore,
    BodyTooLargeError,
    Channel,
    ChannelRule,
    ClientAddress,
    FetchPlan,
    HeaderSecretLeakError,
    InboundChannelVerifier,
    InboundVerificationError,
    LogRedactor,
    NoHashKeyError,
    PairingRateLimiter,
    PublishFile,
    PublishManifest,
    SafePathError,
    SSRFValidationError,
    SealedSecret,
    SessionCookiePolicy,
    SessionRevokedError,
    StagedSecretPlan,
    TrustBoundary,
    TrustRole,
    UnsafeLinkError,
    UnsafeRedirectError,
    WeakCSPError,
    aes_gcm_open,
    aes_gcm_seal,
    admit_channel_message,
    assert_address_allowed,
    assert_no_dangerous_html_api,
    assert_no_secrets_in_argv,
    assert_strong_csp,
    build_csp,
    build_publish_manifest,
    build_security_headers,
    build_setup_script,
    classify_address,
    client_address_from_headers,
    consume_staged_secrets,
    default_channel_rules,
    hash_api_key,
    is_clean_email_body,
    issue_api_key,
    open_secret,
    open_session_cookie,
    parse_redirect_location,
    redact_url,
    render_safe_markdown,
    render_sandboxed_iframe,
    render_trust_model,
    safe_return_path,
    sandbox_headers_for_content_type,
    sandboxed_iframe_attrs,
    seal_secret,
    seal_session_cookie,
    select_publish_files,
    session_cookie_header,
    stage_secrets,
    stream_limited,
    validate_fetch_url,
    validate_redirect_chain,
    validate_request_headers,
    verify_api_key,
    W7_IDS,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolver(mapping):
    """Injectable DNS resolver returning the configured address list."""
    def resolve(host):
        return mapping[host]
    return resolve


def _sign(secret="s3cr3t-channel-key", sender="owner@example.com", ts=None,
          nonce="nonce-1", body="please do the thing"):
    if ts is None:
        ts = int(time.time())
    sig = InboundChannelVerifier.sign(secret, sender, ts, nonce, body)
    return dict(sender=sender, timestamp=ts, nonce=nonce, body=body, signature=sig)


# ---------------------------------------------------------------------------
# W7.1 - typed trust boundaries
# ---------------------------------------------------------------------------

def test_w71_trust_roles_are_typed_and_distinct():
    assert {r.value for r in TrustRole} == {
        "client", "daemon", "agent", "host_api", "third_party",
    }
    assert TrustRole("client") is TrustRole.CLIENT
    with pytest.raises(ValueError):
        TrustRole("root")


def test_w71_four_required_boundaries_are_explicit():
    pairs = {(b.source, b.target) for b in TRUST_BOUNDARIES}
    assert (TrustRole.CLIENT, TrustRole.DAEMON) in pairs
    assert (TrustRole.DAEMON, TrustRole.AGENT) in pairs
    assert (TrustRole.AGENT, TrustRole.HOST_API) in pairs
    assert (TrustRole.DAEMON, TrustRole.THIRD_PARTY) in pairs
    assert all(isinstance(b, TrustBoundary) for b in TRUST_BOUNDARIES)


def test_w71_boundaries_state_untrusted_client_and_secret_holding_daemon():
    text = render_trust_model().lower()
    assert "untrusted" in text
    assert "daemon" in text and "secret" in text
    assert "restricted" in text
    assert "privileged" in text
    assert TRUST_MODEL["client"]["trust"] == "untrusted"
    assert TRUST_MODEL["daemon"]["holds_secrets"] is True
    assert TRUST_MODEL["agent"]["environment"] == "restricted"
    assert TRUST_MODEL["host_api"]["privileged"] is True
    assert TRUST_MODEL["third_party"]["trust"] == "untrusted"


# ---------------------------------------------------------------------------
# W7.10 - SSRF-safe fetch validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("address", [
    "127.0.0.1", "127.1.2.3", "10.0.0.1", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "0.0.0.0", "100.64.0.1", "192.0.2.10",
    "::1", "fd00::1", "fe80::1", "2001:db8::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
    "2002:7f00:1::1", "64:ff9b::7f00:1", "::127.0.0.1",
])
def test_w710_private_and_special_addresses_rejected(address):
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url("http://example.test/x", resolver=_resolver({"example.test": [address]}))
    assert exc.value.reason in {"UNSAFE_ADDRESS", "METADATA_ADDRESS"}


@pytest.mark.parametrize("address", ["8.8.8.8", "93.184.216.34", "2606:4700:4700::1111", "::ffff:8.8.8.8"])
def test_w710_public_addresses_allowed_and_pinned(address):
    plan = validate_fetch_url("https://example.test:8443/a?b=1", resolver=_resolver({"example.test": [address]}))
    assert isinstance(plan, FetchPlan)
    assert plan.address == address
    assert plan.host == "example.test"
    assert plan.port == 8443
    assert plan.connection_target == (address, 8443)
    assert plan.tls_server_name == "example.test"


def test_w710_every_dns_answer_is_checked_not_just_the_first():
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url("http://example.test/", resolver=_resolver(
            {"example.test": ["93.184.216.34", "127.0.0.1"]}))
    assert exc.value.reason == "UNSAFE_ADDRESS"


def test_w710_metadata_rejected_even_when_link_local_is_allowed():
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url("http://example.test/", resolver=_resolver({"example.test": ["169.254.169.254"]}),
                           allowed_networks=("169.254.0.0/16",))
    assert exc.value.reason == "METADATA_ADDRESS"
    with pytest.raises(SSRFValidationError):
        validate_fetch_url("http://example.test/", resolver=_resolver({"example.test": ["fd00:ec2::254"]}))


def test_w710_explicit_loopback_allowlist_is_opt_in():
    plan = validate_fetch_url("http://localhost:8000/x", resolver=_resolver({"localhost": ["127.0.0.1"]}),
                              allowed_networks=("127.0.0.0/8",))
    assert plan.address == "127.0.0.1"


def test_w710_address_classification_helper():
    assert classify_address("8.8.8.8").value == "global"
    assert classify_address("127.0.0.1").value == "loopback"
    assert classify_address("10.1.2.3").value == "private"
    assert classify_address("169.254.1.1").value == "link_local"
    assert classify_address("169.254.169.254").value == "metadata"
    assert classify_address("bad-ip").value == "invalid"
    assert_address_allowed("8.8.8.8")
    with pytest.raises(SSRFValidationError):
        assert_address_allowed("::1")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.test/x", "javascript:alert(1)",
    "data:text/html,<script>x</script>", "gopher://127.0.0.1/1",
])
def test_w710_only_http_https_schemes(url):
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url(url, resolver=_resolver({}))
    assert exc.value.reason == "SCHEME_NOT_ALLOWED"


@pytest.mark.parametrize("url", [
    "http://user:password@example.test/", "http://sk-live-abcdef@example.test/",
])
def test_w710_credentials_in_url_rejected_without_leaking_them(url):
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url(url, resolver=_resolver({"example.test": ["8.8.8.8"]}))
    assert exc.value.reason == "CREDENTIALS_IN_URL"
    assert "password" not in str(exc.value)
    assert "sk-live-abcdef" not in str(exc.value)
    assert redact_url(url) == "http://example.test/"


def test_w710_malformed_urls_and_ports_fail_closed():
    for url, reason in [
        ("http:///missing-host", "MISSING_HOST"),
        ("http://example.test:notaport/", "INVALID_PORT"),
        ("http://example.test:0/", "INVALID_PORT"),
        ("http://example.test:70000/", "INVALID_PORT"),
        ("http://[broken/", "MALFORMED_URL"),
    ]:
        with pytest.raises(SSRFValidationError) as exc:
            validate_fetch_url(url, resolver=_resolver({"example.test": ["8.8.8.8"]}))
        assert exc.value.reason == reason


def test_w710_dns_failure_and_empty_answers_fail_closed():
    def boom(host):
        raise OSError("name resolution failed")
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url("http://example.test/", resolver=boom)
    assert exc.value.reason == "RESOLUTION_FAILED"
    with pytest.raises(SSRFValidationError) as exc:
        validate_fetch_url("http://example.test/", resolver=_resolver({"example.test": []}))
    assert exc.value.reason == "RESOLUTION_FAILED"


def test_w710_time_and_size_caps_are_in_the_plan():
    plan = validate_fetch_url("https://example.test/", resolver=_resolver({"example.test": ["8.8.8.8"]}),
                              connect_timeout=1.5, read_timeout=2.5, max_bytes=4096, total_timeout=9)
    assert plan.connect_timeout == 1.5
    assert plan.read_timeout == 2.5
    assert plan.max_bytes == 4096
    assert plan.total_timeout == 9
    with pytest.raises(ValueError):
        validate_fetch_url("https://example.test/", resolver=_resolver({"example.test": ["8.8.8.8"]}), max_bytes=0)


def test_w710_streaming_size_cap_does_not_trust_content_length():
    assert b"".join(stream_limited([b"abc", b"def"], 6)) == b"abcdef"
    with pytest.raises(BodyTooLargeError):
        list(stream_limited([b"abcd", b"efg"], 6))


@pytest.mark.parametrize("headers", [
    {"X-Trace": "abc\r\nSet-Cookie: session=leak"},
    {"X-Trace": "abc\nSet-Cookie: session=leak"},
    {"X-Trace": "abc\x00def"},
    {"Bad\r\nName": "x"},
    {"Host": "evil.test"},
    {"Authorization": "Bearer topsecret"},
    {"Cookie": "session=topsecret"},
])
def test_w710_malformed_or_credential_headers_rejected_without_value_leak(headers):
    with pytest.raises(SSRFValidationError) as exc:
        validate_request_headers(headers, forbidden_values=("topsecret",))
    assert exc.value.reason in {"MALFORMED_HEADER", "FORBIDDEN_HEADER"}
    assert "topsecret" not in str(exc.value)
    assert "Set-Cookie" not in str(exc.value)


def test_w710_valid_request_headers_are_returned_as_plain_dict():
    assert validate_request_headers({"Accept": "application/json"}) == {"Accept": "application/json"}


def test_w710_redirect_chain_rechecks_every_hop():
    resolver = _resolver({
        "good.test": ["8.8.8.8"],
        "second.test": ["1.1.1.1"],
        "evil.test": ["127.0.0.1"],
    })
    plans = validate_redirect_chain(
        ["https://good.test/a", "https://second.test/b", "https://1.1.1.1/c"], resolver=resolver)
    assert [p.address for p in plans] == ["8.8.8.8", "1.1.1.1", "1.1.1.1"]
    with pytest.raises(SSRFValidationError) as exc:
        validate_redirect_chain(["https://good.test/a", "https://evil.test/b"], resolver=resolver)
    assert exc.value.reason == "UNSAFE_ADDRESS"


def test_w710_redirect_relative_resolution_and_malformed_location():
    assert parse_redirect_location("https://good.test/a/b", "../c") == "https://good.test/c"
    assert parse_redirect_location("https://good.test/a/b", "/d") == "https://good.test/d"
    for loc in ["https://good.test/a\r\nX: y", "javascript:alert(1)", "http://u:p@good.test/", "data:text/html,x"]:
        with pytest.raises(SSRFValidationError):
            parse_redirect_location("https://good.test/a", loc)


def test_w710_redirect_downgrade_loop_and_cap_rejected():
    resolver = _resolver({"good.test": ["8.8.8.8"]})
    with pytest.raises(SSRFValidationError) as exc:
        validate_redirect_chain(["https://good.test/a", "http://good.test/b"], resolver=resolver)
    assert exc.value.reason == "HTTPS_DOWNGRADE"
    with pytest.raises(SSRFValidationError) as exc:
        validate_redirect_chain(["https://good.test/a", "https://good.test/a"], resolver=resolver)
    assert exc.value.reason == "REDIRECT_LOOP"
    with pytest.raises(SSRFValidationError) as exc:
        validate_redirect_chain(["https://good.test/%d" % i for i in range(7)], resolver=resolver)
    assert exc.value.reason == "TOO_MANY_REDIRECTS"


# ---------------------------------------------------------------------------
# W7.13 - security headers
# ---------------------------------------------------------------------------

def test_w713_required_header_set():
    headers = build_security_headers(https=True)
    expected = {
        "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
        "Referrer-Policy", "Cross-Origin-Opener-Policy", "Permissions-Policy",
        "Strict-Transport-Security", "X-Permitted-Cross-Domain-Policies",
    }
    assert expected.issubset(headers)
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "31536000" in headers["Strict-Transport-Security"]


def test_w713_csp_has_no_unsafe_eval_and_frame_ancestors_none():
    csp = build_csp()
    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "Strict-Transport-Security" not in build_security_headers(https=False)


def test_w713_hsts_only_for_https():
    assert "Strict-Transport-Security" not in build_security_headers(https=False)
    from keel.security_contracts import security_headers_for_url
    assert "Strict-Transport-Security" not in security_headers_for_url("http://example.test/")
    assert "Strict-Transport-Security" in security_headers_for_url("https://example.test/")
    with pytest.raises(ValueError):
        security_headers_for_url("ftp://example.test/")


def test_w713_permissions_policy_microphone_scope_and_no_secret():
    pp = build_security_headers(https=True)["Permissions-Policy"]
    assert "microphone=(self)" in pp
    assert "camera=()" in pp
    assert "geolocation=()" in pp


@pytest.mark.parametrize("csp", [
    "default-src 'self'; script-src 'self' 'unsafe-eval'; frame-ancestors 'none'",
    "default-src 'self'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
    "default-src *; frame-ancestors 'none'",
    "default-src 'self'; script-src 'self'",
    "default-src 'self'; frame-ancestors *",
    "default-src 'self'; frame-ancestors 'self'",
    "default-src 'self'; object-src *; frame-ancestors 'none'",
])
def test_w713_weak_csp_rejected(csp):
    with pytest.raises(WeakCSPError):
        assert_strong_csp(csp)
    with pytest.raises(WeakCSPError):
        build_security_headers(https=True, csp=csp)


def test_w713_extra_headers_cannot_smuggle_secrets_or_set_cookies():
    with pytest.raises(HeaderSecretLeakError) as exc:
        build_security_headers(https=True, extra_headers={"X-Debug": "token=sk-live-abcdefghijklmnop"})
    assert "abcdefghijklmnop" not in str(exc.value)
    with pytest.raises(HeaderSecretLeakError):
        build_security_headers(https=True, extra_headers={"Set-Cookie": "session=abc"})
    with pytest.raises(HeaderSecretLeakError):
        build_security_headers(https=True, extra_headers={"X-Secret": "x"}, forbidden_values=("x",))
    with pytest.raises(HeaderSecretLeakError):
        build_security_headers(https=True, extra_headers={"X-Trace": "a\r\nX-Leak: b"})
    safe = build_security_headers(https=True, extra_headers={"X-Request-Id": "req-123"})
    assert safe["X-Request-Id"] == "req-123"


# ---------------------------------------------------------------------------
# W7.14 - rendering safety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "<svg/onload=alert(1)>",
    "<ScRiPt>alert(1)</ScRiPt>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",
    "<iframe src='javascript:alert(1)'></iframe>",
    '<a href="javascript:alert(1)">click</a>',
])
def test_w714_raw_html_is_always_escaped(payload):
    out = render_safe_markdown("hello " + payload)
    assert "<script" not in out.lower()
    assert "<img" not in out.lower()
    assert "<svg" not in out.lower()
    assert "<iframe" not in out.lower()
    assert 'onerror="alert' not in out.lower()
    assert "&#x27;" in out or "&quot;" in out or "&lt;" in out or "&amp;lt;" in out
    assert "hello" in out


def test_w714_fenced_code_does_not_execute_html():
    out = render_safe_markdown("```html\n<script>alert(1)</script>\n```")
    assert "<script" not in out.lower()
    assert "&lt;script&gt;" in out
    assert "language-html" in out


@pytest.mark.parametrize("url", ["https://example.test/a", "http://example.test/", "mailto:owner@example.test"])
def test_w714_link_scheme_allowlist_allows_safe_links(url):
    out = render_safe_markdown("[label](%s)" % url)
    assert 'href="%s"' % url in out
    assert ">label</a>" in out


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)", "file:///etc/passwd", "//evil.test/x", "java\x00script:alert(1)",
])
def test_w714_dangerous_link_schemes_are_blocked(url):
    out = render_safe_markdown("[label](%s)" % url)
    assert "href" not in out
    assert "javascript" not in out.lower()
    assert "data:" not in out.lower()
    assert "label" in out


def test_w714_link_allowlist_is_exact():
    assert LINK_SCHEME_ALLOWLIST == frozenset({"http", "https", "mailto"})
    with pytest.raises(UnsafeLinkError):
        from keel.security_contracts import validate_link_url
        validate_link_url("javascript:alert(1)")
    assert validate_link_url("/relative/path") == "/relative/path"


def test_w714_external_images_are_not_autoloaded_by_default():
    out = render_safe_markdown("![alt](https://cdn.test/track.png)")
    assert "<img" not in out
    assert "External image blocked" in out
    enabled = render_safe_markdown("![alt](https://cdn.test/track.png)", allow_external_images=True)
    assert '<img src="https://cdn.test/track.png"' in enabled
    assert 'referrerpolicy="no-referrer"' in enabled


def test_w714_relative_images_allowed_but_data_images_never_allowed():
    assert '<img src="/logo.png"' in render_safe_markdown("![logo](/logo.png)")
    for enabled in (False, True):
        out = render_safe_markdown("![x](data:image/svg+xml;base64,PHN2Zz4=)", allow_external_images=enabled)
        assert "<img" not in out


def test_w714_no_dangerous_inner_html_api():
    with pytest.raises(ValueError):
        assert_no_dangerous_html_api('<div dangerouslySetInnerHTML={{__html: x}} />')
    with pytest.raises(ValueError):
        assert_no_dangerous_html_api("node.innerHTML = payload")
    assert_no_dangerous_html_api("<div>{escapedText}</div>")


def test_w714_inline_documents_get_sandboxing_csp():
    headers = sandbox_headers_for_content_type("text/html")
    assert "sandbox" in headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "script-src 'none'" in headers["Content-Security-Policy"]
    assert sandbox_headers_for_content_type("image/svg+xml") == headers
    assert sandbox_headers_for_content_type("application/xml") == headers
    assert sandbox_headers_for_content_type("text/plain") == {}


def test_w714_generated_site_preview_is_sandboxed_iframe():
    attrs = sandboxed_iframe_attrs("https://preview.test/site/")
    assert attrs["sandbox"] == "allow-scripts"
    assert "allow-same-origin" not in attrs["sandbox"]
    assert attrs["referrerpolicy"] == "no-referrer"
    assert "sandbox" in attrs["csp"]
    html = render_sandboxed_iframe("https://preview.test/site/", title='A "quoted" title')
    assert 'sandbox="allow-scripts"' in html
    assert "&quot;" in html
    with pytest.raises(UnsafeLinkError):
        sandboxed_iframe_attrs("javascript:alert(1)")


# ---------------------------------------------------------------------------
# W7.16 - publish path selection
# ---------------------------------------------------------------------------

def _make_site(root):
    (root / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "app.css").write_text("body{}", encoding="utf-8")
    (root / ".secret").write_text("hidden", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("origin", encoding="utf-8")
    (root / ".git" / "objects").mkdir()
    (root / ".git" / "objects" / "blob").write_text("x", encoding="utf-8")
    (root / "assets" / ".env").write_text("KEY=x", encoding="utf-8")
    return root


def test_w716_selects_only_visible_files_from_site_folder(tmp_path):
    site = tmp_path / "site"
    site.mkdir(parents=True)
    _make_site(site)
    files = select_publish_files(site)
    assert [f.relative for f in files] == ["assets/app.css", "index.html"]
    assert all(isinstance(f, PublishFile) for f in files)
    assert all(not any(part.startswith(".") for part in f.relative.split("/")) for f in files)


def test_w716_candidate_paths_are_contained_and_relative(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("ok", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    assert [f.relative for f in select_publish_files(site, ["index.html"])] == ["index.html"]
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site, ["../outside.txt"])
    assert exc.value.reason == "TRAVERSAL"
    with pytest.raises(SafePathError):
        select_publish_files(site, [str(tmp_path / "outside.txt")])
    with pytest.raises(SafePathError):
        select_publish_files(site, ["/etc/passwd"])
    with pytest.raises(SafePathError):
        select_publish_files(site, ["./assets/../../outside.txt"])


def test_w716_hidden_candidates_and_missing_files_rejected(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / ".env").write_text("KEY=x", encoding="utf-8")
    (site / ".hidden_dir").mkdir()
    (site / ".hidden_dir" / "file.txt").write_text("x", encoding="utf-8")
    for candidate in [".env", ".hidden_dir/file.txt", "assets/.env"]:
        with pytest.raises(SafePathError) as exc:
            select_publish_files(site, [candidate])
        assert exc.value.reason == "HIDDEN"
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site, ["nope.txt"])
    assert exc.value.reason == "MISSING"
    with pytest.raises(SafePathError):
        select_publish_files(site, ["."])


def test_w716_symlinks_rejected_via_injectable_check(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("ok", encoding="utf-8")
    (site / "assets").mkdir()
    (site / "assets" / "app.css").write_text("x", encoding="utf-8")
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site, ["assets/app.css"],
                             is_symlink=lambda p: p.name == "assets")
    assert exc.value.reason == "SYMLINK"
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site, is_symlink=lambda p: p.name == "site")
    assert exc.value.reason == "SYMLINK"
    # Enumeration must not return a symlinked leaf either.
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site, is_symlink=lambda p: p.name == "index.html")
    assert exc.value.reason == "SYMLINK"


def test_w716_real_symlink_rejected_when_supported(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("ok", encoding="utf-8")
    try:
        os.symlink(site / "index.html", site / "link.html")
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    with pytest.raises(SafePathError) as exc:
        select_publish_files(site)
    assert exc.value.reason == "SYMLINK"


def test_w716_manifest_is_deterministic_and_digest_addressed(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    (site / "assets").mkdir()
    (site / "assets" / "app.css").write_text("body{}", encoding="utf-8")
    a = build_publish_manifest(site)
    b = build_publish_manifest(site)
    assert isinstance(a, PublishManifest)
    assert a.version == "1"
    assert a.digest == b.digest
    assert a.to_json() == b.to_json()
    assert str(site).replace("\\", "/") not in a.to_json()
    assert a.to_json() == json.dumps(json.loads(a.to_json()), sort_keys=True, separators=(",", ":"))
    assert len(a.digest) == 64
    expected = hashlib.sha256(b"<h1>ok</h1>").hexdigest()
    assert a.files[1].sha256 == expected
    assert a.files[1].size == len(b"<h1>ok</h1>")


# ---------------------------------------------------------------------------
# W7.17 - inbound channel rules
# ---------------------------------------------------------------------------

def test_w717_valid_signature_verifies():
    v = InboundChannelVerifier("s3cr3t-channel-key", approved_senders=["owner@example.com"])
    assert v.verify(**_sign()).sender == "owner@example.com"


def test_w717_missing_or_empty_secret_fails_closed():
    for secret in (None, "", b""):
        v = InboundChannelVerifier(secret, approved_senders=["owner@example.com"])
        with pytest.raises(InboundVerificationError) as exc:
            v.verify(**_sign())
        assert exc.value.reason == "NO_SECRET"
    with pytest.raises(InboundVerificationError):
        InboundChannelVerifier.sign("", "s", 1, "n", "b")


@pytest.mark.parametrize("field,value", [
    ("body", "tampered"), ("sender", "attacker@example.com"),
    ("nonce", "nonce-2"), ("timestamp", 12344),
])
def test_w717_tampered_payload_rejected(field, value):
    v = InboundChannelVerifier("s3cr3t-channel-key", approved_senders=["owner@example.com", "attacker@example.com"], now=lambda: 12345)
    msg = _sign(ts=12345)
    msg[field] = value
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**msg)
    assert exc.value.reason == "BAD_SIGNATURE"


@pytest.mark.parametrize("signature", ["", "zz", "deadbeef", "sha256=nothex", "a" * 64])
def test_w717_malformed_signature_fail_closed(signature):
    v = InboundChannelVerifier("s3cr3t-channel-key", approved_senders=["owner@example.com"], now=lambda: 12345)
    msg = _sign(ts=12345)
    msg["signature"] = signature
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**msg)
    assert exc.value.reason == "BAD_SIGNATURE"


def test_w717_freshness_window_is_300_seconds():
    assert FRESHNESS_WINDOW_SECONDS == 300
    now = 1_700_000_000
    v = InboundChannelVerifier("k", approved_senders=["s"], now=lambda: now)
    assert v.verify(**_sign(secret="k", sender="s", ts=now - 300, nonce="a")).nonce == "a"
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**_sign(secret="k", sender="s", ts=now - 301, nonce="b"))
    assert exc.value.reason == "STALE"
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**_sign(secret="k", sender="s", ts=now + 301, nonce="c"))
    assert exc.value.reason == "FUTURE"
    malformed = _sign(secret="k", sender="s", ts=now, nonce="d")
    malformed["timestamp"] = "not-a-number"
    with pytest.raises(InboundVerificationError):
        v.verify(**malformed)


def test_w717_nonce_replay_defense_and_bounded_cache():
    now = 1_700_000_000
    v = InboundChannelVerifier("k", approved_senders=["s"], now=lambda: now, nonce_cache_size=2)
    v.verify(**_sign(secret="k", sender="s", ts=now, nonce="one", body="a"))
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**_sign(secret="k", sender="s", ts=now, nonce="one", body="a"))
    assert exc.value.reason == "NONCE_REPLAY"
    v.verify(**_sign(secret="k", sender="s", ts=now, nonce="two", body="b"))
    v.verify(**_sign(secret="k", sender="s", ts=now, nonce="three", body="c"))
    assert len(v.nonce_cache) <= 2
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**_sign(secret="k", sender="s", ts=now, nonce="two", body="b"))
    assert exc.value.reason == "NONCE_REPLAY"


def test_w717_sender_allowlist_fails_closed():
    v = InboundChannelVerifier("k", approved_senders=["owner@example.com"])
    with pytest.raises(InboundVerificationError) as exc:
        v.verify(**_sign(secret="k", sender="other@example.com"))
    assert exc.value.reason == "SENDER_NOT_APPROVED"
    v2 = InboundChannelVerifier("k")
    with pytest.raises(InboundVerificationError):
        v2.verify(**_sign(secret="k"))


def test_w717_email_owner_only_and_clean_mail():
    rules = default_channel_rules("owner@example.com")
    assert isinstance(rules[Channel.EMAIL], ChannelRule)
    assert admit_channel_message("owner@example.com", Channel.EMAIL, "<h1>hi</h1>", rules).allowed is False
    assert admit_channel_message("attacker@example.com", Channel.EMAIL, "hello", rules).allowed is False
    assert admit_channel_message("owner@example.com", Channel.EMAIL, "hello", rules).allowed is True
    assert is_clean_email_body("plain text\nsecond line")
    assert not is_clean_email_body('<img src=x onerror="alert(1)">')
    assert not is_clean_email_body("click javascript:alert(1)")


def test_w717_voice_tasks_require_confirmation_code():
    rules = default_channel_rules("owner@example.com")
    decision = admit_channel_message("owner@example.com", Channel.VOICE, "start work", rules)
    assert isinstance(decision, AdmissionDecision)
    assert decision.allowed is False
    again = admit_channel_message("owner@example.com", Channel.VOICE, "start work", rules,
                                  confirmation_code="123456", expected_confirmation_code="123456")
    assert again.allowed is True
    wrong = admit_channel_message("owner@example.com", Channel.VOICE, "start work", rules,
                                  confirmation_code="000000", expected_confirmation_code="123456")
    assert wrong.allowed is False
    assert admit_channel_message("owner@example.com", Channel.CHAT, "hi", rules).allowed is False


# ---------------------------------------------------------------------------
# W7.3 - AES-256-GCM sealing and session cookie
# ---------------------------------------------------------------------------

def test_w73_known_answer_vectors_match_nist_aes256_gcm():
    key = bytes(SECRET_KEY_BYTES)
    tag = aes_gcm_open(SealedSecret(1, bytes(12), b"", bytes.fromhex(
        "530f8afbc74536b9a963b4f1c4cb738b")), key, b"")
    assert tag == b""
    ct = bytes.fromhex("cea7403d4d606b6e074ec5d3baf39d18")
    assert aes_gcm_open(SealedSecret(1, bytes(12), ct, bytes.fromhex(
        "d0d1c8a799996bf0265b98b5d48ab919")), key, b"") == bytes(16)


def test_w73_seal_uses_random_12_byte_iv_and_auth_tag():
    key = bytes(range(32))
    a = seal_secret("sk-live-abcdef", key, b"keel-secret-v1")
    b = seal_secret("sk-live-abcdef", key, b"keel-secret-v1")
    assert isinstance(a, SealedSecret)
    assert len(a.iv) == 12
    assert len(a.tag) == 16
    assert a.iv != b.iv
    assert a.ciphertext != b.ciphertext
    assert open_secret(a, key, b"keel-secret-v1") == "sk-live-abcdef"


def test_w73_wrong_key_tag_ciphertext_or_aad_fails_closed():
    key = bytes(range(32))
    sealed = seal_secret("secret-value", key, b"ctx")
    with pytest.raises(Exception):
        open_secret(sealed, bytes(32), b"ctx")
    with pytest.raises(Exception):
        open_secret(sealed, key, b"other-context")
    with pytest.raises(Exception):
        aes_gcm_open(SealedSecret(1, sealed.iv, sealed.ciphertext[:-1] + bytes([sealed.ciphertext[-1] ^ 1]), sealed.tag), key, b"ctx")
    with pytest.raises(Exception):
        aes_gcm_open(SealedSecret(1, sealed.iv, sealed.ciphertext, bytes(16)), key, b"ctx")
    with pytest.raises(ValueError):
        seal_secret("x", b"short-key")


def test_w73_session_cookie_round_trip_expiry_revocation_and_flags():
    secret_key = bytes(range(32))
    session_key = bytes(range(32, 64))
    policy = SessionCookiePolicy()
    now = 1_700_000_000
    payload = {"sid": "session-abc", "uid": "user-1", "exp": now + policy.max_age}
    token = seal_session_cookie(payload, session_key, now=now)
    assert open_session_cookie(token, session_key, now=now) == payload
    with pytest.raises(Exception):
        open_session_cookie(token, secret_key, now=now)
    with pytest.raises(SessionRevokedError):
        open_session_cookie(token, session_key, now=now, revoked_session_ids={"session-abc"})
    with pytest.raises(Exception):
        open_session_cookie(token, session_key, now=now + policy.max_age + 1)
    header = session_cookie_header("keel_session", token, https=True)
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header
    assert "Secure" in header
    assert "Max-Age=2592000" in header
    assert "Secure" not in session_cookie_header("keel_session", token, https=False)
    with pytest.raises(ValueError):
        seal_session_cookie(payload, session_key, aad=b"wrong-aad", now=now)


# ---------------------------------------------------------------------------
# W7.4 - API keys
# ---------------------------------------------------------------------------

def test_w74_api_key_is_prefixed_random_and_stored_only_as_sha256():
    issued = issue_api_key()
    assert isinstance(issued, ApiKeyIssueResult)
    assert issued.token.startswith(API_KEY_PREFIX)
    assert issued.digest == hashlib.sha256(issued.token.encode()).hexdigest()
    assert issued.token not in issued.digest
    assert len(issued.digest) == 64
    assert verify_api_key(issued.token, issued.digest)


def test_w74_bad_or_empty_api_key_fails_closed():
    issued = issue_api_key()
    assert not verify_api_key(issued.token + "x", issued.digest)
    assert not verify_api_key("", issued.digest)
    assert not verify_api_key(issued.token, "")
    assert hash_api_key("") == "" or len(hash_api_key("")) == 64


def test_w74_per_key_rate_limit_and_per_user_idempotency():
    store = ApiKeyStore(rate_limit=2, window_seconds=60, now=lambda: 1000.0)
    issued = issue_api_key()
    store.register(issued.key_id, issued.digest, owner="user-1")
    assert store.consume(issued.key_id, "user-1", "idem-1", "fingerprint-a").allowed is True
    assert store.consume(issued.key_id, "user-1", "idem-1", "fingerprint-a").duplicate is True
    conflict = store.consume(issued.key_id, "user-1", "idem-1", "fingerprint-b")
    assert conflict.allowed is False and conflict.reason == "IDEMPOTENCY_CONFLICT"
    assert store.consume(issued.key_id, "user-1", "idem-2", "fingerprint-c").allowed is True
    denied = store.consume(issued.key_id, "user-1", "idem-3", "fingerprint-d")
    assert isinstance(denied, ApiKeyDecision)
    assert denied.allowed is False and denied.reason == "RATE_LIMITED"
    assert denied.retry_after > 0
    unknown = store.consume("keel_live_unknown", "user-1", "idem-x", "fp")
    assert unknown.allowed is False and unknown.reason == "UNKNOWN_KEY"


# ---------------------------------------------------------------------------
# W7.5 - staged secrets for child processes
# ---------------------------------------------------------------------------

def test_w75_staged_file_is_restricted_and_secret_free_in_argv(tmp_path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    plan = stage_secrets({"OPENAI_API_KEY": "sk-super-secret", "GITHUB_TOKEN": "ghp_secret"}, stage_dir)
    assert isinstance(plan, StagedSecretPlan)
    staged = Path(plan.file_path)
    assert staged.exists()
    assert "sk-super-secret" not in plan.file_path
    assert "sk-super-secret" not in " ".join(plan.argv)
    assert all("ghp_secret" not in v for v in plan.env.values() if v != plan.file_path)
    mode = stat.S_IMODE(staged.stat().st_mode)
    assert mode & 0o022 == 0  # no group/other write (0o600 on POSIX, read-only bit on Windows)
    assert mode & 0o400
    assert "KEEL_STAGED_SECRETS" in plan.env
    assert_no_secrets_in_argv(["keel", "mcp", "--config", "x.json"], ["sk-super-secret", "ghp_secret"])
    with pytest.raises(ValueError) as exc:
        assert_no_secrets_in_argv(["keel", "--token", "sk-super-secret"], ["sk-super-secret"])
    assert "sk-super-secret" not in str(exc.value)


def test_w75_setup_script_reads_then_deletes_and_consume_removes_file(tmp_path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    plan = stage_secrets({"TOKEN": "abc123"}, stage_dir)
    script = build_setup_script(["TOKEN"])
    assert "KEEL_STAGED_SECRETS" in script
    assert "unlink" in script
    assert "finally" in script
    assert "abc123" not in script
    values = consume_staged_secrets(plan.file_path)
    assert values == {"TOKEN": "abc123"}
    assert not Path(plan.file_path).exists()
    with pytest.raises(FileNotFoundError):
        consume_staged_secrets(plan.file_path)


# ---------------------------------------------------------------------------
# W7.6 - log redaction and keyed pseudonyms
# ---------------------------------------------------------------------------

def test_w76_redacts_known_secret_patterns_and_explicit_values():
    redactor = LogRedactor(secret_values=("sk-live-abcdefghijklmnop", "owner@example.test"))
    line = "key=sk-live-abcdefghijklmnop user=owner@example.test Bearer sk-anotherkey1234567890"
    red = redactor.redact(line)
    assert "sk-live-abcdefghijklmnop" not in red
    assert "owner@example.test" not in red
    assert "sk-anotherkey1234567890" not in red
    assert "[REDACTED]" in red
    assert redactor.redact("plain message") == "plain message"


def test_w76_keyed_pseudonyms_are_stable_and_do_not_leak_ids():
    redactor = LogRedactor(hash_key=b"a-32-byte-key-used-only-for-hashing")
    a = redactor.pseudonymize("user@example.test")
    assert a == redactor.pseudonymize("user@example.test")
    assert "user@example.test" not in a
    assert a.startswith("user_")
    assert redactor.pseudonymize("user@example.test", namespace="session") != a
    other = LogRedactor(hash_key=b"another-key-used-only-for-hashing!")
    assert other.pseudonymize("user@example.test") != a
    with pytest.raises(NoHashKeyError):
        LogRedactor().pseudonymize("user@example.test")


# ---------------------------------------------------------------------------
# W7.8 - pairing rate limit, trusted proxy, relative return path
# ---------------------------------------------------------------------------

def test_w78_trusted_proxy_hop_count_controls_client_address():
    headers = {"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 203.0.113.9"}
    a = client_address_from_headers(headers, remote_addr="10.0.0.5", trusted_proxy_hops=0)
    assert a.address == "10.0.0.5" and a.source == "direct"
    b = client_address_from_headers(headers, remote_addr="10.0.0.5", trusted_proxy_hops=1,
                                    trusted_proxy_ips=("10.0.0.5",))
    assert b.address == "203.0.113.9" and b.source == "trusted_proxy"
    c = client_address_from_headers(headers, remote_addr="10.0.0.5", trusted_proxy_hops=2,
                                    trusted_proxy_ips=("10.0.0.5",))
    assert c.address == "2.2.2.2" and c.source == "trusted_proxy"
    d = client_address_from_headers(headers, remote_addr="10.0.0.5", trusted_proxy_hops=2)
    assert d.address == "10.0.0.5"


def test_w78_malformed_and_missing_addresses_fail_closed():
    assert client_address_from_headers({}, remote_addr=None).source == "missing"
    assert client_address_from_headers({"X-Forwarded-For": "not-an-ip"}, remote_addr="8.8.8.8",
                                       trusted_proxy_hops=1, trusted_proxy_ips=("8.8.8.8",)).address == "8.8.8.8"


def test_w78_open_redirect_guard_only_allows_same_origin_relative_paths():
    assert safe_return_path("/dashboard?tab=1") == "/dashboard?tab=1"
    assert safe_return_path("/") == "/"
    for bad in ["https://evil.test/", "//evil.test/", "/\\evil.test/", "/../etc/passwd",
                "javascript:alert(1)", "/a\r\nSet-Cookie: x=y", "\\evil.test", ""]:
        with pytest.raises(UnsafeRedirectError):
            safe_return_path(bad)


def test_w78_pairing_rate_limits_per_address_and_globally():
    limiter = PairingRateLimiter(max_per_address=2, max_global=3, window_seconds=60, now=lambda: 1000.0)
    first = limiter.check("1.1.1.1")
    assert isinstance(first, ApiKeyDecision)
    assert first.allowed is True
    assert limiter.check("1.1.1.1").allowed is True
    denied = limiter.check("1.1.1.1")
    assert denied.allowed is False and denied.reason == "RATE_LIMITED"
    assert limiter.check("2.2.2.2").allowed is True
    assert limiter.check("3.3.3.3").allowed is False
    assert limiter.check("").allowed is False


# ---------------------------------------------------------------------------
# registry / evidence
# ---------------------------------------------------------------------------

def test_registry_ids_are_all_covered():
    assert set(W7_IDS) == {
        "W7.1", "W7.3", "W7.4", "W7.5", "W7.6", "W7.8",
        "W7.10", "W7.13", "W7.14", "W7.16", "W7.17", "W7.19",
    }
    assert len(KNOWN_LIMITATIONS) == 4
    assert all(lim.statement for lim in KNOWN_LIMITATIONS)

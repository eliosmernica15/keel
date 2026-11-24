"""Tests for the remaining W7.*, X1.*, Y5.* and D1.* backend rows (31 features).

Each test is named after its feature ID and exercises real stdlib-only backend
behavior. No network calls, subprocesses or external services are used.
"""

from __future__ import annotations

import json
import threading

import pytest

from keel import w7_x1_y5_d1_backend as m


# ---------------------------------------------------------------------------
# D1.* — plugins, profiles, bundles, entrypoints and transactions
# ---------------------------------------------------------------------------


def test_d1_2_reversible_effects_and_leak_detector():
    unwound: list[str] = []
    scope = m.ReversibleEffectScope("plugin-a")
    first = scope.register("route", lambda: unwound.append("route"))
    scope.register("hook", lambda: unwound.append("hook"))
    assert set(scope.leaked()) == {"route", "hook"}
    assert set(m.detect_effect_leaks(scope)["plugin-a"]) == {"route", "hook"}
    assert first.active is True
    assert first() is True  # dispose via returned disposer
    assert first.active is False
    assert scope.leaked() == ["hook"]
    assert scope.unload() == ["hook"]
    assert unwound == ["route", "hook"]  # LIFO
    assert scope.leaked() == []

    # context manager unwinds on exit
    with m.ReversibleEffectScope("scoped") as s:
        s.register("temp", lambda: unwound.append("temp"))
    assert "temp" in unwound
    assert m.detect_effect_leaks() == {}


def test_d1_3_profiles_bundles_and_config_rows():
    web = m.resolve_profile("web")
    assert web.name == "web"
    assert "hmr" in web.bundles
    assert web.patch.endswith("web.patch.json")
    assert m.validate_profile(web) == []
    rows = m.profile_config_rows(web)
    assert any(r.startswith("bundle:") for r in rows)
    assert rows[-1].startswith("patch:")

    m.register_bundle("finance", config_rows=2, code_modules=("ledger",))
    custom = m.resolve_profile("headless", extra_bundles=("finance",),
                               extra_plugins=("acme.plugin",))
    assert "finance" in custom.bundles
    assert custom.plugins == ("acme.plugin",)
    assert m.validate_profile(custom) == []
    assert len([r for r in m.profile_config_rows(custom) if "finance" in r]) == 2

    with pytest.raises(m.BackendError):
        m.resolve_profile("does-not-exist")
    with pytest.raises(m.BackendError):
        m.resolve_profile("web", extra_bundles=("missing-bundle",))


def test_d1_6_hmr_toggle_per_profile():
    assert m.hmr_enabled("web") is True
    for profile in ("headless", "sdk", "sdk-minimal", "acp"):
        assert m.hmr_enabled(profile) is False
    assert m.hmr_enabled(m.resolve_profile("web")) is True
    cfg = m.hmr_config("headless")
    assert cfg["plugins.load.hmr"]["enabled"] is False
    assert cfg["plugins.load.hmr"]["mode"] == "config-only"


def test_d1_7_entrypoint_gate():
    assert m.classify_entrypoint("keel --profile web") == "profile_launcher"
    assert m.classify_entrypoint("keel serve") == "bypass"
    assert m.classify_entrypoint("python -m keel.cli.main") == "bypass"
    manifest = {
        "scripts": {"start": "keel --profile web", "demo": "python -m keel.demo"},
        "bins": {"keel-raw": "keel run --raw"},
    }
    report = m.verify_application_entrypoints(manifest)
    assert report["ok"] is False
    assert report["checked"] == 3
    assert {v["name"] for v in report["violations"]} == {"demo", "keel-raw"}
    assert m.verify_application_entrypoints(
        {"scripts": {"start": "keel --profile sdk"}})["ok"] is True


def test_d1_8_sdk_runtime_launch():
    assert m.sdk_wheel_name("windows").endswith("-win_amd64.whl")
    assert "manylinux" in m.sdk_wheel_name("linux")
    with pytest.raises(m.BackendError):
        m.sdk_wheel_name("plan9")
    argv = m.sdk_launch_args(home_dir="C:/sdk-data", profile="sdk-minimal")
    assert argv == ["keel", "--profile", "sdk-minimal", "--home", "C:/sdk-data"]
    assert m.validate_sdk_args(argv) is True
    assert m.validate_sdk_args(["keel", "--profile", "sdk"]) is False
    with pytest.raises(m.BackendError):
        m.sdk_launch_args(home_dir="", profile="sdk")
    with pytest.raises(m.BackendError):
        m.sdk_launch_args(home_dir="/data", profile="web")


def test_d1_9_reserved_command():
    assert m.is_reserved_command("plugin") is True
    assert m.is_reserved_command("someprofile") is False
    with pytest.raises(m.BackendError):
        m.validate_profile_name("plugin")
    assert m.validate_profile_name("plugin", allow_reserved=True) == "plugin"
    with pytest.raises(m.BackendError):
        m.validate_profile_name("../escape")


def test_d1_11_plugin_install_transaction(tmp_path):
    trace: list[str] = []
    tx = m.PluginTransaction("web", tmp_path)
    tx.add("download", lambda: trace.append("download"), lambda: trace.append("undo-download"))
    tx.add("install", lambda: trace.append("install"), lambda: trace.append("undo-install"))
    result = tx.run()
    assert result["ok"] is True
    assert result["applied"] == 2
    assert (tx.env_path).is_dir()
    assert trace == ["download", "install"]

    failing = m.PluginTransaction("sdk", tmp_path)
    failing.add("stage", lambda: "staged", lambda: trace.append("undo-stage"))
    failing.add("build", lambda: (_ for _ in ()).throw(RuntimeError("build failed")),
                lambda: trace.append("undo-build"))
    out = failing.run()
    assert out["ok"] is False
    assert out["failed_step"] == "build"
    assert out["rolled_back"] == 1
    assert "undo-stage" in trace
    assert any(e["action"] == "rollback" for e in out["log"])


# ---------------------------------------------------------------------------
# W7.* — web/daemon security backend
# ---------------------------------------------------------------------------


def test_w7_2_owner_only_live_view():
    headers = m.live_view_headers()
    assert "no-store" in headers["Cache-Control"]
    assert headers["Pragma"] == "no-cache"
    assert "X-Robots-Tag" in headers
    url = m.live_view_url("https://keel.test/live?x=1", "tok")
    assert "view=tok" in url and "x=1" in url
    assert m.authorize_live_view("alice", "alice") is True
    assert m.authorize_live_view("bob", "alice") is False


def test_w7_7_browser_bound_signin():
    key = b"synthetic-test-key-32-bytes-long!!"
    fp_browser_a = m.browser_fingerprint({"User-Agent": "BrowserA", "Accept-Language": "en"})
    fp_browser_b = m.browser_fingerprint({"User-Agent": "BrowserB", "Accept-Language": "en"})
    assert fp_browser_a != fp_browser_b

    signin = m.BrowserBoundSignIn(key)
    started = signin.start(fp_browser_a, redirect="/dashboard")
    assert "SameSite=Strict" in started["set_cookie"]
    assert "HttpOnly" in started["set_cookie"]
    assert "Secure" in started["set_cookie"]
    assert signin.complete(started["state"], started["cookie"], fp_browser_b) is False
    assert signin.complete(started["state"], started["cookie"], fp_browser_a) is True
    # replay / consumed state
    assert signin.complete(started["state"], started["cookie"], fp_browser_a) is False

    # expiry
    expired = m.seal_value({"state": "s", "fp": "f", "kind": "signin"}, key, ttl=1, now=1000)
    assert m.unseal_value(expired, key, now=2000) is None
    assert m.unseal_value("garbage.token", key) is None

    # pairing code only completable on initiating client
    pairing_cookie = signin.bind_pairing("client-1", fp_browser_a)
    assert signin.complete_pairing(pairing_cookie, "client-1", fp_browser_a, "CODE") is True
    assert signin.complete_pairing(pairing_cookie, "client-2", fp_browser_a, "CODE") is False
    assert signin.complete_pairing(pairing_cookie, "client-1", fp_browser_b, "CODE") is False


def test_w7_9_csrf_origin_check():
    ok, reason = m.check_csrf_origin(
        {"Origin": "https://keel.test"}, expected_origin="https://keel.test", method="POST")
    assert ok is True and reason == "origin-match"
    assert m.check_csrf_origin({"Origin": "https://evil.test"},
                               expected_origin="https://keel.test", method="PUT")[0] is False
    assert m.check_csrf_origin({}, expected_origin="https://keel.test", method="POST")[1] == "missing-origin"
    assert m.check_csrf_origin({"Origin": "null"}, expected_origin="https://keel.test",
                               method="POST")[1] == "invalid-origin"
    assert m.check_csrf_origin({}, expected_origin="https://keel.test", method="GET")[1] == "safe-method"
    assert m.check_csrf_origin({"Authorization": "Bearer abc"},
                               expected_origin="https://keel.test", method="DELETE")[1] == "bearer-exempt"


def test_w7_11_streaming_body_and_upload_bounds():
    limiter = m.StreamingBodyLimiter(max_bytes=10)
    assert limiter.feed(b"12345") == b"12345"
    with pytest.raises(m.BodyTooLargeError):
        limiter.feed(b"123456")
    # cap applies without any Content-Length: streamed chunks are counted
    limiter2 = m.StreamingBodyLimiter(max_bytes=100)
    limiter2.feed_all([b"a" * 40, b"b" * 40])
    with pytest.raises(m.BodyTooLargeError):
        limiter2.feed(b"c" * 21)

    fields = m.bounded_multipart([("a", b"x" * 10), ("b", b"y" * 10)],
                                 max_part_bytes=16, max_total_bytes=32)
    assert set(fields) == {"a", "b"}
    with pytest.raises(m.BodyTooLargeError):
        m.bounded_multipart([("big", b"x" * 100)], max_part_bytes=16)
    with pytest.raises(m.BodyTooLargeError):
        m.bounded_multipart([("a", b"x"), ("b", b"y")], max_parts=1)

    capped = m.cap_recording([{"n": i} for i in range(100)], max_events=5)
    assert len(capped) == 5
    assert len(m.cap_recording([{"n": "x" * 100} for _ in range(100)], max_bytes=500)) < 100


def test_w7_12_generic_errors_and_server_log(tmp_path):
    detail = "DB password=sk-abcdefghijklmnopqrst"
    response = m.generic_error("req-42")
    assert response["error"]["request_id"] == "req-42"
    assert "password" not in json.dumps(response)
    assert "sk-" not in json.dumps(response)
    logfile = m.log_error_detail(tmp_path / "server.log", "req-42", detail)
    contents = logfile.read_text(encoding="utf-8")
    assert "req-42" in contents and "sk-" in contents
    assert len(m.generic_error()["error"]["request_id"]) == 16


def test_w7_15_share_tokens_and_public_redaction():
    token = m.new_share_token()
    assert m.share_token_entropy_bits(token) == 144
    assert len(token) == 24
    transcript = {
        "owner": {"name": "Alice", "email": "alice@example.com"},
        "instructions": "SECRET SYSTEM PROMPT",
        "messages": [
            {"role": "user", "content": "Ping alice@example.com with key sk-abcdefghijklmnopqrst"},
        ],
        "tool_calls": [{"args": "x" * 200}],
    }
    view = m.public_share_view(transcript, preview_chars=400)
    assert view["owner"] is None and view["instructions"] is None
    assert "alice@example.com" not in view["text"]
    assert "sk-" not in view["text"]
    assert "SECRET SYSTEM PROMPT" not in json.dumps(view)
    assert len(view["tool_previews"][0]) == 60
    rendered = m.render_share_html(view)
    assert rendered.startswith("<!doctype html>")
    assert "<script>" not in m.render_share_html({"text": "<script>alert(1)</script>"})


def test_w7_18_atomic_spend_ledger():
    ledger = m.AtomicSpendLedger({"vendor-a": 10.0})
    for _ in range(10):
        receipt = ledger.authorize_and_charge("vendor-a", 1.0)
        assert receipt["vendor"] == "vendor-a"
    assert ledger.spent("vendor-a") == 10.0
    with pytest.raises(m.SpendLimitExceeded):
        ledger.authorize_and_charge("vendor-a", 1.0)

    # concurrency: exactly as many charges succeed as the cap allows
    concurrent = m.AtomicSpendLedger({"vendor-b": 10.0})
    successes: list[int] = []
    guard = threading.Lock()

    def charge() -> None:
        try:
            concurrent.authorize_and_charge("vendor-b", 1.0)
            with guard:
                successes.append(1)
        except m.SpendLimitExceeded:
            pass

    threads = [threading.Thread(target=charge) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(successes) == 10
    assert concurrent.spent("vendor-b") == 10.0


def test_w7_20_deployment_hygiene():
    good = {
        "key_scope": "narrow", "display_redaction": True, "recording_redaction": True,
        "provider_spend_limits": True, "always_allow": False,
        "private_vuln_reporting": True, "latest_branch_only": True,
        "best_effort_fixes": True,
    }
    report = m.deployment_hygiene_report(good)
    assert report["ok"] is True and report["failures"] == []
    bad = m.deployment_hygiene_report({"always_allow": True})
    assert bad["ok"] is False
    assert "narrowest_scope_keys" in bad["failures"]
    assert "always_allow_guarded" in bad["failures"]
    assert "[REDACTED]" in m.redact_keys_for_display("api_key=sk-abcdefghijklmnopqrst")
    assert "only the latest release branch" in m.support_policy().lower()


# ---------------------------------------------------------------------------
# X1.* — model/tool intelligence backend
# ---------------------------------------------------------------------------


def test_x1_6_apply_model_merge_guard():
    original = "one\ntwo\nthree\n"
    sketch = "one\nCHANGED\nthree\n"
    result = m.apply_model_merge(original, sketch, max_diff_lines=10)
    assert result["applied"] is True
    assert result["content"] == sketch
    assert result["diff_lines"] == 2
    rejected = m.apply_model_merge(original, sketch, max_diff_lines=1)
    assert rejected["applied"] is False
    assert rejected["content"] == original
    assert "guard" in rejected["reason"]


def test_x1_9_few_shot_exemplars():
    assert len(m.exemplars_for_probe(0.1)) == 2
    assert len(m.exemplars_for_probe(0.5)) == 1
    assert m.exemplars_for_probe(0.9) == []


def test_x1_10_self_consistency_vote():
    majority = m.self_consistency_vote(["a", "a", "b"], think_harder_level=2)
    assert majority.winner == "a" and majority.counts["a"] == 2
    assert majority.disabled is False
    tie = m.self_consistency_vote(["a", "b"], think_harder_level=1,
                                  judge=lambda samples: "judge-pick")
    assert tie.winner == "judge-pick" and tie.judge_used is True
    disabled = m.self_consistency_vote(["a"], think_harder_level=0)
    assert disabled.disabled is True and disabled.winner is None


def test_x1_11_streaming_partial_json_parser():
    parser = m.PartialJSONParser()
    parser.feed('{"path": "README.md"')
    assert parser.partial_view()["keys"] == ["path"]
    assert parser.partial_view()["complete"] is False
    with pytest.raises(m.BackendError):
        parser.result()  # must not execute incomplete args
    state = parser.feed(', "recursive": true}')
    assert state["complete"] is True
    assert parser.result() == {"path": "README.md", "recursive": True}


def test_x1_12_parallel_tool_batches():
    calls = [
        m.ToolCall("r1", "read_file", True),
        m.ToolCall("r2", "list_dir", True),
        m.ToolCall("w1", "write_file", False),
        m.ToolCall("r3", "read_file", True, depends_on=("w1",)),
    ]
    batches = m.plan_tool_batches(calls)
    assert [c.id for c in batches[0]] == ["r1", "r2"]  # parallel reads
    assert [c.id for c in batches[1]] == ["w1"]  # write serialized
    assert [c.id for c in batches[2]] == ["r3"]  # dependent read after write
    with pytest.raises(m.BackendError):
        m.plan_tool_batches([
            m.ToolCall("a", "x", True, ("b",)),
            m.ToolCall("b", "y", True, ("a",)),
        ])
    with pytest.raises(m.BackendError):
        m.plan_tool_batches([m.ToolCall("a", "x", True, ("missing",))])


def test_x1_14_model_switch_mid_session():
    session = {"model": "claude-3", "history": [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]}]}
    switched = m.switch_model(session, "gpt-4o", dialect="openai", capacity=100000)
    assert switched["model"] == "gpt-4o"
    assert switched["history"][0]["content"] == "hello"
    assert isinstance(switched["history"][0]["content"], str)
    assert "warning" not in switched
    tight = m.switch_model(session, "gpt-4o", dialect="openai", capacity=1)
    assert "warning" in tight
    anthropic = m.render_history(session["history"], "anthropic")
    assert anthropic[0]["content"][0]["type"] == "text"


def test_x1_15_per_model_prompt_profiles():
    assert m.model_family("claude-3-haiku") == "small"
    assert m.model_family("claude-3-opus") == "claude"
    assert m.model_family("gpt-4o-mini") == "small"
    assert m.model_family("gpt-4o") == "gpt"
    profile = m.prompt_profile("claude-3-opus")
    assert profile["family"] == "claude"
    assert profile["version"] == 2
    assert "coding assistant" in profile["system"]
    assert m.prompt_profile("gpt-4o")["version"] == 1


def test_x1_16_model_health_check():
    healthy = m.model_health_check({"tool_call": True, "json_validity": True,
                                    "long_context": True})
    assert healthy["ok"] is True and healthy["badge"] == "healthy"
    degraded = m.model_health_check({"tool_call": True, "json_validity": False,
                                     "long_context": True})
    assert degraded["ok"] is False and degraded["badge"] == "degraded"
    assert set(degraded["probes"]) == {"tool_call", "json_validity", "long_context"}


# ---------------------------------------------------------------------------
# Y5.* — channel plugins, webhooks and operations backend
# ---------------------------------------------------------------------------


def test_y5_1_plugin_manifest_and_namespace():
    valid = {"name": "telegram-channel", "version": "1.2.3",
             "keel": {"channel": "telegram"}}
    assert m.validate_plugin_manifest(valid) == []
    assert m.validate_plugin_manifest({"name": "Bad Name", "version": "x"}) != []
    ns = m.config_namespace("telegram-channel")
    assert ns["channels"] == "channels.telegram-channel"
    assert ns["load_paths_key"] == "plugins.load.paths"
    assert ns["local_dev"]["plugins.load.paths"][0].endswith("telegram-channel")


def test_y5_2_install_from_git_url():
    plan = m.parse_install_source("https://github.com/acme/keel-telegram.git")
    assert plan["method"] == "git" and plan["scheme"] == "https"
    assert "build" in plan["prepare"]
    ssh = m.parse_install_source("git@github.com:acme/keel-telegram.git")
    assert ssh["scheme"] == "ssh"
    link = m.parse_install_source("./plugins/local", link=True)
    assert link["method"] == "link" and link["link"] is True
    with pytest.raises(m.BackendError):
        m.parse_install_source("ftp://example.com/plugin")
    with pytest.raises(m.BackendError):
        m.parse_install_source("", link=True)


def test_y5_3_webhook_subscription_lifecycle(tmp_path):
    manager = m.WebhookSubscriptionManager(tmp_path / "credentials")
    sub = manager.subscribe("https://example.test/hook",
                            ["message.received", "reaction.added"], label="main")
    assert len(sub["signing_secret"]) >= 32
    assert sub["active"] is True
    assert manager.get(sub["id"]) == sub
    assert len(manager.list()) == 1

    # programmatic helper
    other = m.create_webhook_subscription(manager, "https://example.test/hook2",
                                          ["typing.started"])
    assert other["id"] in {s["id"] for s in manager.list()}
    assert manager.unsubscribe(sub["id"]) is True
    assert manager.get(sub["id"])["active"] is False
    assert manager.unsubscribe("missing") is False

    # persistence across instances
    reloaded = m.WebhookSubscriptionManager(tmp_path / "credentials")
    assert len(reloaded.list()) == 2
    with pytest.raises(m.BackendError):
        manager.subscribe("https://example.test/hook", ["event.unknown"])
    with pytest.raises(m.BackendError):
        manager.subscribe("http://example.test/hook", ["message.read"])


def test_y5_3_concurrent_subscribers_do_not_lose_updates(tmp_path):
    manager = m.WebhookSubscriptionManager(tmp_path / "credentials")
    count = 24
    barrier = threading.Barrier(count)
    errors = []

    def worker(index):
        try:
            barrier.wait()
            manager.subscribe(f"https://example.test/hook/{index}",
                              ["message.received"], label=f"sub-{index}")
        except BaseException as exc:  # surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(manager.list()) == count
    assert len(m.WebhookSubscriptionManager(tmp_path / "credentials").list()) == count


def test_y5_3_caller_paths_reject_traversal(tmp_path):
    traversal = tmp_path / "ok" / ".." / "escape"
    with pytest.raises(m.BackendError, match="traversal"):
        m.WebhookSubscriptionManager(traversal)
    with pytest.raises(m.BackendError, match="traversal"):
        m.ChatIdCache(traversal)
    with pytest.raises(m.BackendError, match="traversal"):
        m.log_error_detail(traversal / "server.log", "req", "detail")


def test_y5_5_reaction_mapping():
    assert m.map_reaction("👍")["native"] == "thumbsup"
    variant = m.map_reaction("👍🏽")
    assert variant["native"] == "thumbsup" and variant["skin_tone"] == "🏽"
    assert m.map_reaction("🤯") is None
    action = m.react_action("👍", "msg-1")
    assert action["action"] == "react" and action["native"] == "thumbsup"
    removal = m.react_action("🎉", "msg-1", remove=True)
    assert removal["action"] == "unreact"
    with pytest.raises(m.BackendError):
        m.react_action("🤯", "msg-1")


def test_y5_6_chat_id_cache(tmp_path):
    cache = m.ChatIdCache(tmp_path / "credentials")
    assert cache.get("telegram", "external-1") is None
    cache.put("telegram", "external-1", "internal-1")
    assert cache.get("telegram", "external-1") == "internal-1"
    assert cache.size() == 1
    reloaded = m.ChatIdCache(tmp_path / "credentials")
    assert reloaded.get("telegram", "external-1") == "internal-1"
    assert cache.reset() is True
    assert reloaded.get("telegram", "external-1") is None
    assert cache.reset() is False


def test_y5_7_status_and_gateway_commands():
    status = m.channel_status({
        "telegram": {"enabled": True, "state": "connected"},
        "discord": {"enabled": False},
    })
    assert status["count"] == 2
    assert status["channels"][0]["id"] == "discord"
    assert status["channels"][1]["state"] == "connected"
    started = m.gateway_start({"channels": {
        "telegram": {"enabled": True}, "discord": {"enabled": False}}})
    assert started["command"] == "gateway start" and started["channels"] == ["telegram"]
    with pytest.raises(m.BackendError):
        m.gateway_start({"channels": {}})


def test_y5_8_troubleshooting_exact_strings():
    assert m.troubleshoot("token not configured")["remediation"]
    assert m.troubleshoot("fromNumber not configured")["remediation"]
    assert m.troubleshoot("webhook not receiving")["remediation"]
    assert m.troubleshoot("Token Not Configured") is None  # exact match only
    assert m.troubleshoot("something else") is None


def test_y5_9_excluded_channels():
    for name in ("linq-api", "imessage", "rcs", "sms"):
        assert m.channel_availability(name) == "Blocked for free"
    assert m.channel_availability("telegram") == "available"
    assert m.channel_availability("carrier-pigeon") == "unknown"


# ---------------------------------------------------------------------------
# Registry consistency guard
# ---------------------------------------------------------------------------


def test_all_31_not_started_feature_ids_are_covered():
    """Guard that this module documents/tests every target feature ID."""
    ids = {
        "W7.2", "W7.7", "W7.9", "W7.11", "W7.12", "W7.15", "W7.18", "W7.20",
        "X1.6", "X1.9", "X1.10", "X1.11", "X1.12", "X1.14", "X1.15", "X1.16",
        "Y5.1", "Y5.2", "Y5.3", "Y5.5", "Y5.6", "Y5.7", "Y5.8", "Y5.9",
        "D1.2", "D1.3", "D1.6", "D1.7", "D1.8", "D1.9", "D1.11",
    }
    assert len(ids) == 31
    source = open(m.__file__, encoding="utf-8").read()
    test_source = open(__file__, encoding="utf-8").read()
    for feature_id in ids:
        assert feature_id in source, feature_id
        assert feature_id in test_source, feature_id

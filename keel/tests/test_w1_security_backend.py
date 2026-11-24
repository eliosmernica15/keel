"""Adversarial backend tests for every implemented W1.* feature.

Run with: python -c "import sys; sys.path.insert(0,'keel/src'); ..."
W1.18 is owner-gated and is only checked as an exclusion.
"""

from __future__ import annotations

import io
import json
import math

import pytest

import keel.w1_security_backend as w1
from keel.w1_security_backend import (
    BrandGuidelines, BuilderInstructionScanner, BenchmarkStore, I18nDocumentStore,
    LaunchPolicyError, PluginError, PluginIndexError, PluginScopeTree,
    PortableCIMirror, PrivatePluginIndex, RgIgnore, VendorPolicy, W1BackendError,
    EXCLUDED_FEATURES, IMPLEMENTED_FEATURES, REQUIRED_SUITES,
    bundle_digest, build_feedback_bundle, ci_jobs, detect_ssh_session,
    feedback_policy, find_duplicate_blocks, launch_display, make_help,
    parse_simple_yaml, plan_target, plan_web_launch, pytest_ini_section,
    python_sdk_surface, redact_feedback, sdk_compatibility, stability_info,
    staged_lint_plan, suite_config, typescript_client_source, validate_payload,
    validate_suite_matrix, valid_vendor_license_text,
)


# ---------------------------------------------------------------- inventory

def test_inventory_and_owner_gated_exclusion():
    assert len(IMPLEMENTED_FEATURES) == 16
    assert len(set(IMPLEMENTED_FEATURES)) == 16
    assert "W1.18" in EXCLUDED_FEATURES
    assert "MIT" in EXCLUDED_FEATURES["W1.18"]
    assert "W1.18" not in IMPLEMENTED_FEATURES
    exported = {name.lower() for name in dir(w1)}
    assert not any("mit_license" in name or "third_party_notices" in name
                   for name in exported)


# ------------------------------------------------------------------- W1.1

def test_w11_all_plugin_kinds_share_one_api():
    tree = PluginScopeTree()
    for index, kind in enumerate(w1.PLUGIN_KINDS):
        registration = tree.register(f"plugin{index}", kind)
        assert registration.kind == kind
        assert tree.resolve(f"plugin{index}") == registration
    assert len(tree.resolve_all("tool")) == 1
    assert [reg.name for reg in tree.list_plugins(kind="tool")] == ["plugin1"]


def test_w11_rejects_invalid_registrations():
    tree = PluginScopeTree()
    with pytest.raises(PluginError):
        tree.register("x", "not_a_kind")
    with pytest.raises(PluginError):
        tree.register("../escape", "tool")
    with pytest.raises(PluginError):
        tree.register("x", "tool", "core..tools")
    tree.register("x", "tool", "core")
    with pytest.raises(PluginError):
        tree.register("x", "tool", "core")
    with pytest.raises(PluginError):
        tree.register("y", "tool", replaces="missing")
    with pytest.raises(PluginError):
        tree.register("y", "tool", depends_on=["y"])


def test_w11_scope_precedence_disable_fallback_and_replace():
    tree = PluginScopeTree()
    tree.register("provider", "provider", "core")
    tree.register("provider", "provider", "session")
    assert tree.resolve("provider").scope == "session"
    tree.disable("session", "provider")
    assert tree.resolve("provider").scope == "core"
    tree.enable("session", "provider")
    assert tree.resolve("provider").scope == "session"
    tree.register("new_provider", "provider", "user", replaces="core:provider")
    assert tree.resolve("provider").scope == "session"
    assert [reg.scope for reg in tree.list_plugins(kind="provider")] == ["session", "user"]
    assert tree.resolve("new_provider").scope == "user"
    solo = PluginScopeTree()
    solo.register("old", "provider", "core")
    solo.register("new", "provider", "user", replaces="old")
    assert solo.resolve("old") is None
    assert solo.resolve("new").scope == "user"
    with pytest.raises(PluginError):
        tree.register("bad", "tool", replaces="session:provider")
    tree.unregister("user", "new_provider")
    assert tree.resolve("provider").scope == "session"


def test_w11_dependency_graph_reports_missing_and_cycles():
    tree = PluginScopeTree()
    tree.register("a", "tool", depends_on=["missing", "b"])
    tree.register("b", "tool", depends_on=["a"])
    report = tree.validate()
    assert report["ok"] is False
    assert any("missing dependency missing" in issue for issue in report["issues"])
    assert any("dependency cycle" in issue for issue in report["issues"])
    clean = PluginScopeTree()
    clean.register("a", "tool")
    clean.register("b", "channel", depends_on=["a"])
    assert clean.validate() == {"ok": True, "issues": []}


# ---------------------------------------------------------------- W1.2/3

def test_w12_loopback_only_launch_plan():
    plan = plan_web_launch()
    assert plan.host == "127.0.0.1" and plan.port == 3080
    assert plan.url == "http://127.0.0.1:3080/"
    assert plan.command == ("keel", "web", "--host", "127.0.0.1", "--port", "3080")
    assert plan_web_launch(host="LOCALHOST", port=9).url == "http://localhost:9/"
    assert plan_web_launch(host="[::1]", port=9).url == "http://[::1]:9/"
    assert "--no-open" in plan_web_launch(no_open=True).command


def test_w12_rejects_hosts_ports_and_paths():
    for host in ("0.0.0.0", "192.168.1.10", "example.com", "", "  ", "127.999.0.1"):
        with pytest.raises(LaunchPolicyError):
            plan_web_launch(host=host)
    for port in (0, -1, 65536, "3080", True, 3.5):
        with pytest.raises(LaunchPolicyError):
            plan_web_launch(port=port)
    for path in ("relative", "/a/../b", "", None):
        with pytest.raises(LaunchPolicyError):
            plan_web_launch(path=path)
    assert plan_web_launch(path="/a b").url.endswith("/a%20b")


def test_w13_ssh_detection_and_never_open_browser(monkeypatch):
    assert detect_ssh_session({}) is False
    assert detect_ssh_session({"SSH_CONNECTION": "  "}) is False
    assert detect_ssh_session({"SSH_TTY": " /dev/pts/1 "}) is True
    assert detect_ssh_session({"SSH_CLIENT": "1.2.3.4 5 6"}) is True
    plan = plan_web_launch(environ={"SSH_CONNECTION": "1.2.3.4 1 5.6.7.8 2"})
    assert plan.ssh is True and plan.open_browser is False
    stream = io.StringIO()
    display = launch_display(plan_web_launch(), environ={"SSH_TTY": "/dev/pts/0"},
                             stream=stream)
    assert display["mode"] == "ssh" and display["open_browser"] is False
    assert "ssh -L 3080:127.0.0.1:3080" in display["hint"]
    assert "SSH" in stream.getvalue()
    local = launch_display(plan_web_launch(), environ={})
    assert local["mode"] == "local" and local["open_browser"] is True
    assert "--no-open" in plan_web_launch(no_open=True).command


# ------------------------------------------------------------------- W1.4

def test_w14_one_bundle_for_both_targets():
    sources = {"b.js": "b", "a.js": "a"}
    assert bundle_digest(sources) == bundle_digest(dict(reversed(list(sources.items()))))
    web = plan_target("web", sources=sources)
    desktop = plan_target("desktop", sources=sources)
    assert web.bundle_sha256 == desktop.bundle_sha256
    assert web.bundle == desktop.bundle
    assert web.command[:2] == ("keel", "web")
    assert desktop.command[:2] == ("keel", "desktop")
    assert desktop.open_browser is False
    assert plan_target("web", no_open=True, sources=sources).open_browser is False
    with pytest.raises(W1BackendError):
        plan_target("electron", sources=sources)
    with pytest.raises(W1BackendError):
        bundle_digest({})
    help_text = make_help()
    assert "  web" in help_text and "  desktop" in help_text


# ------------------------------------------------------------------- W1.5

def test_w15_eight_suites_and_separate_ci_jobs():
    assert REQUIRED_SUITES == (
        "unit", "bench", "e2e", "golden", "snapshot", "web", "web-stress", "web-perf",
    )
    jobs = ci_jobs()
    assert [job["name"] for job in jobs] == list(REQUIRED_SUITES)
    assert len({job["name"] for job in jobs}) == 8
    assert all(job["stage"] == "test" and job["command"].startswith("python -m pytest")
               for job in jobs)
    assert "golden" in suite_config("golden")["pytest_args"][-1]
    markers = pytest_ini_section()
    for marker in ("web_stress", "golden", "web_perf", "benchmark"):
        assert f"    {marker}:" in markers


def test_w15_rejects_broken_suite_matrix():
    with pytest.raises(W1BackendError):
        suite_config("webstress")
    with pytest.raises(W1BackendError):
        validate_suite_matrix(list(REQUIRED_SUITES[:-1]))
    with pytest.raises(W1BackendError):
        validate_suite_matrix(list(REQUIRED_SUITES) + ["unit"])
    with pytest.raises(W1BackendError):
        validate_suite_matrix(list(REQUIRED_SUITES[:-1]) + ["Unit"])
    with pytest.raises(W1BackendError):
        validate_suite_matrix("unit")


# ------------------------------------------------------------------- W1.6

METHOD = "# Method\nrun each suite 3x\n# Hardware\nlocal x86_64\n# Command\npython -m pytest\n# Metric\nwall_ms (lower is better)\n"


def test_w16_benchmark_round_trip(tmp_path):
    store = BenchmarkStore(tmp_path)
    with pytest.raises(W1BackendError):
        store.initialize("# Method only\n")
    store.initialize(METHOD)
    entry = store.record("v1.2.0", "unit", {"wall_ms": 1.0},
                         snapshot="run output")
    assert entry["snapshot_sha256"]
    store.record("v1.2.0", "unit", {"wall_ms": 3.0})
    assert len(store.results(suite="unit")) == 2
    summary = store.summary(release="v1.2.0")
    assert summary["runs"] == 2
    assert summary["suites"]["unit"]["metrics"]["wall_ms"] == 2.0
    assert store.validate_layout() == []


def test_w16_rejects_unsafe_records(tmp_path):
    store = BenchmarkStore(tmp_path)
    store.initialize(METHOD)
    with pytest.raises(W1BackendError):
        store.record("../escape", "unit", {"ms": 1})
    with pytest.raises(W1BackendError):
        store.record("v1.0.0", "made-up", {"ms": 1})
    for metrics in ({"ms": -1}, {"ms": True}, {"ms": "fast"},
                    {"ms": math.nan}, {}, {"ok": object()}):
        with pytest.raises(W1BackendError):
            store.record("v1.0.0", "unit", metrics)
    with pytest.raises(W1BackendError):
        store.record("v1.0.0", "unit", {"ms": 1}, snapshot=123)
    assert BenchmarkStore(tmp_path / "empty").validate_layout()


# ------------------------------------------------------------------- W1.7

def test_w17_rgignore_patterns_negation_and_escapes():
    ignore = RgIgnore.from_text("# comment\n*.pyc\nvendor/\n!vendor/keep.py\n\n")
    assert ignore.ignored("src/a.pyc") is True
    assert ignore.ignored("vendor/lib/a.py") is True
    assert ignore.ignored("vendor/keep.py") is False
    assert ignore.ignored("src/a.py") is False
    assert ignore.filter(["a.py", "b.pyc"]) == ["a.py"]
    with pytest.raises(W1BackendError):
        ignore.ignored("../secret.py")
    with pytest.raises(W1BackendError):
        ignore.ignored("/etc/passwd")


def test_w17_staged_lint_only_python_and_not_ignored():
    ignore = RgIgnore.from_text("vendor/\n")
    plan = staged_lint_plan(
        ["a.py", "b.py", "docs/readme.md", "vendor/x.py", "../evil.py"],
        rgignore=ignore,
    )
    assert plan.files == ("a.py", "b.py")
    assert plan.command == ("ruff", "check", "--no-cache", "a.py", "b.py")
    assert plan.duplicate_command[-2:] == ("a.py", "b.py")
    assert any("vendor/x.py" in reason for reason in plan.skipped)
    assert staged_lint_plan(["notes.txt"]).command == ()


def test_w17_duplicate_code_detector():
    block = "\n".join(f"line {n}" for n in range(8))
    duplicates = find_duplicate_blocks(
        {"a.py": block, "b.py": "  line 0  \n" + "\n".join(f"line {n} " for n in range(1, 8)),
         "c.py": "x\n"},
        min_lines=5,
    )
    assert len(duplicates) == 1
    assert duplicates[0]["files"] == ["a.py", "b.py"]
    assert find_duplicate_blocks({"a.py": "x\n"}, min_lines=2) == []
    with pytest.raises(W1BackendError):
        find_duplicate_blocks({}, min_lines=1)


# ------------------------------------------------------------------- W1.8

def test_w18_ci_parity_and_generated_configs():
    mirror = PortableCIMirror()
    for job in REQUIRED_SUITES:
        mirror.add_job(job, steps=[f"python -m pytest -m {job}"])
    report = mirror.validate()
    assert report["ok"] is True and len(report["jobs"]) == 8
    assert "branches: [main]" in mirror.github_workflow()
    assert 'CI_COMMIT_BRANCH == "main"' in mirror.gitlab_config()
    with pytest.raises(W1BackendError):
        mirror.add_job("unit")
    with pytest.raises(W1BackendError):
        mirror.add_job("bad; rm -rf /")


def test_w18_detects_job_drift():
    mirror = PortableCIMirror()
    mirror.add_job("unit", forge="github")
    mirror.add_job("e2e", forge="gitlab")
    report = mirror.parity_report()
    assert report["ok"] is False
    assert report["missing_in_github"] == ["e2e"]
    assert report["missing_in_gitlab"] == ["unit"]
    with pytest.raises(W1BackendError):
        mirror.validate()


# ------------------------------------------------------------------- W1.9

YAML_TEXT = """title: Keel
intro: "Local-first AI workspace #1"
notes: |
  first line
  second line
links:
  docs: https://docs.keel.example
"""


def test_w19_yaml_subset_and_locale_fallback():
    parsed = parse_simple_yaml(YAML_TEXT)
    assert parsed["intro"] == "Local-first AI workspace #1"
    assert parsed["notes"] == "first line\nsecond line"
    assert parsed["links"]["docs"] == "https://docs.keel.example"
    with pytest.raises(W1BackendError):
        parse_simple_yaml("title: one\ntitle: two\n")
    with pytest.raises(W1BackendError):
        parse_simple_yaml("title:\n\tindented\n")

    store = I18nDocumentStore()
    store.load_yaml("README", "en", YAML_TEXT)
    store.load_yaml("README", "zh", "title: Keel 中文\n")
    assert store.get("README", "intro", "zh") == "Local-first AI workspace #1"
    assert store.get("README", "title", "zh") == "Keel 中文"
    assert store.missing_keys("README", "zh") == ["intro", "links.docs", "notes"]
    rendered = store.render_html("README", "zh")
    assert "<dt>intro</dt>" in rendered
    assert store.render_markdown("README", "en").startswith("# README (en)")
    files = I18nDocumentStore.document_files("SAFETY")
    assert files["SAFETY.i18n.yaml"] == "en" and files["SAFETY.zh.md"] == "zh"
    with pytest.raises(W1BackendError):
        store.load_yaml("NOPE", "en", "title: x\n")
    with pytest.raises(W1BackendError):
        store.load_yaml("README", "../evil", "title: x\n")


def test_w19_html_is_escaped():
    store = I18nDocumentStore()
    store.load_yaml("SAFETY", "en", 'body: "<script>alert(1)</script>"\n')
    assert "<script>" not in store.render_html("SAFETY")
    assert "&lt;script&gt;" in store.render_html("SAFETY")


# ------------------------------------------------------------------ W1.11

def test_w111_stability_channels_and_banner():
    stable = stability_info("1.2.3")
    assert stable.preview is False and stable.banner == ""
    assert "Stable release" in stable.about["notice"]
    dev = stability_info("1.2.3", "dev", labels=["preview", "preview"])
    assert dev.preview is True and dev.labels == ("preview",)
    assert "Compatibility-breaking changes will happen" in dev.banner
    assert dev.breaking_changes_allowed is True
    beta = stability_info("1.2.3", "BETA")
    assert beta.channel == "beta" and beta.preview is True
    assert stability_info("1.2.3", "experimental").breaking_changes_allowed is True
    for bad in ("<script>", "1.2", "", "1.2.3; rm -rf /"):
        with pytest.raises(W1BackendError):
            stability_info(bad)
    with pytest.raises(W1BackendError):
        stability_info("1.2.3", "nightly")
    with pytest.raises(W1BackendError):
        stability_info("1.2.3", "dev", labels=["unknown-label"])


# ------------------------------------------------------------------ W1.12

BRAND_YAML = """name: Keel
tagline: Local-first AI workspace
logo: wordmark.svg
colors: ink, paper, accent
usage: Keep the wordmark on clear space
prohibited: Do not stretch or recolor the mark
"""


def test_w112_brand_guidelines_validation_and_website_render():
    brand = BrandGuidelines.from_yaml(BRAND_YAML)
    assert brand.validate() == []
    assert brand.render_markdown().startswith("# Brand guidelines (en)")
    assert "<dt>name</dt><dd>Keel</dd>" in brand.render_html()
    assert brand.website_filename("zh") == "BRAND_GUIDELINES.zh.html"
    with pytest.raises(W1BackendError):
        brand.website_filename("../secret")
    missing = BrandGuidelines.from_yaml("name: Keel\n")
    assert missing.validate() == ["colors", "logo", "prohibited", "tagline", "usage"]
    unsafe = BrandGuidelines({"name": "K", "tagline": "T", "logo": "L", "colors": "C",
                              "usage": "U", "prohibited": "<script>x</script>"})
    assert "<script>" not in unsafe.render_html()
    assert "&lt;script&gt;" in unsafe.render_html()


# ------------------------------------------------------------------ W1.13

def test_w113_builder_instructions_load_and_pointer(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Rules\nAlways local-first.\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "style.md").write_text("# Style\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "extra.md").write_text("# Extra\n", encoding="utf-8")
    scanner = BuilderInstructionScanner(tmp_path)
    discovered = scanner.discover()
    assert set(discovered) == {
        "AGENTS.md", "CLAUDE.md", ".agents/style.md", ".claude/extra.md",
    }
    loaded = scanner.load()
    assert "CLAUDE.md" not in loaded
    assert loaded["AGENTS.md"].startswith("# Rules")
    assert "# Source: AGENTS.md" in scanner.merged_instructions()
    with pytest.raises(W1BackendError):
        scanner.read("../../secret.md")
    with pytest.raises(W1BackendError):
        scanner.read("missing.md")


def test_w113_oversized_and_path_escape(tmp_path):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "big.md").write_text("x" * 100, encoding="utf-8")
    scanner = BuilderInstructionScanner(tmp_path, max_bytes=10)
    with pytest.raises(W1BackendError):
        scanner.read(".agents/big.md")
    scanner.load()
    assert any("too large" in issue for issue in scanner.issues)
    for unsafe in ("..\\outside.md", "/etc/passwd", "C:\\secret.md"):
        with pytest.raises(W1BackendError):
            scanner.read(unsafe)


# ------------------------------------------------------------------ W1.14

def _write_index(tmp_path, plugins):
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
    return PrivatePluginIndex(path, root=tmp_path)


def test_w114_private_index_load_search_and_cache(tmp_path):
    index = _write_index(tmp_path, [{
        "name": "search-tool", "version": "v1.0.0", "kind": "tool",
        "path": "plugins/search", "tags": ["search"], "description": "local search",
    }])
    assert index.get("search-tool")["kind"] == "tool"
    assert [p["name"] for p in index.search(kind="tool", tag="search")] == ["search-tool"]
    assert index.search(query="missing") == []
    with pytest.raises(PluginIndexError):
        PrivatePluginIndex.reject_public_topic("dsh-plugin")
    index.plugins()  # prime cache
    _write_index(tmp_path, [{
        "name": "search-tool", "version": "v1.0.0", "kind": "tool", "path": "plugins/search",
    }, {
        "name": "memory", "version": "v2.0.0", "kind": "memory_backend", "path": "plugins/memory",
    }])
    assert index.get("memory") is not None


@pytest.mark.parametrize("mutate", [
    lambda p: {**p, "path": "../../outside"},
    lambda p: {**p, "topic": "dsh-plugin"},
    lambda p: {**p, "version": "bad"},
    lambda p: {**p, "kind": "unknown"},
])
def test_w114_rejects_unsafe_entries(tmp_path, mutate):
    base = {"name": "search-tool", "version": "v1.0.0", "kind": "tool",
            "path": "plugins/search"}
    with pytest.raises(PluginIndexError):
        _write_index(tmp_path, [mutate(base)]).plugins()


def test_w114_rejects_corrupt_and_duplicate_index(tmp_path):
    with pytest.raises(PluginIndexError):
        _write_index(tmp_path, [{"name": "a", "version": "v1.0.0", "kind": "tool",
                                 "path": "a"},
                                {"name": "a", "version": "v1.0.0", "kind": "tool",
                                 "path": "b"}]).plugins()
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PluginIndexError):
        PrivatePluginIndex(path).plugins()


# ------------------------------------------------------------------ W1.15

def test_w115_python_sdk_contract_and_generated_client():
    surface = python_sdk_surface()
    assert set(surface) == {"run", "list_sessions", "send"}
    assert surface["run"]["required"] == ["prompt"]
    assert surface["run"]["defaults"] == {"stream": False}
    assert validate_payload("run", {"prompt": "hi"}) == {"prompt": "hi", "stream": False}
    with pytest.raises(W1BackendError):
        validate_payload("run")
    with pytest.raises(W1BackendError):
        validate_payload("run", {"prompt": "hi", "extra": 1})
    with pytest.raises(W1BackendError):
        validate_payload("run", {"prompt": 1})
    with pytest.raises(W1BackendError):
        validate_payload("send", {"session_id": "s"})
    with pytest.raises(W1BackendError):
        validate_payload("unknown", {})
    source = typescript_client_source()
    assert "async run(prompt: string, stream?: boolean): Promise<RunResult>" in source
    assert "async list_sessions(): Promise<SessionSummary[]>" in source
    assert "this.bridge.call(\"send\"" in source
    assert sdk_compatibility("1.4.0", "1.5.0") is True
    assert sdk_compatibility("1.6.0", "1.5.0") is False
    assert sdk_compatibility("2.0.0", "1.9.0") is False
    with pytest.raises(W1BackendError):
        sdk_compatibility("v1.x", "1.5.0")


# ------------------------------------------------------------------ W1.16

LICENSE = ("Copyright 2026 Example. Permission is hereby granted, free of charge, "
           "to any person obtaining a copy of this software under the MIT License.")


def test_w116_vendor_policy_valid_and_invalid(tmp_path):
    vendor = tmp_path / "vendor" / "libfoo"
    vendor.mkdir(parents=True)
    (vendor / "LICENSE").write_text(LICENSE, encoding="utf-8")
    (tmp_path / "PATCHES.md").write_text(
        "## libfoo\n- upstream: https://example.invalid/libfoo\n- issue: 42\n",
        encoding="utf-8",
    )
    audit = VendorPolicy(tmp_path).audit()
    assert audit["ok"] is True and audit["packages"] == ["libfoo"]
    assert valid_vendor_license_text("MIT") is False
    assert valid_vendor_license_text(LICENSE) is True

    (vendor / "LICENSE").write_text("MIT", encoding="utf-8")
    violations = VendorPolicy(tmp_path).audit()["violations"]
    assert any("missing or invalid LICENSE" in v for v in violations)
    (vendor / "LICENSE").write_text(LICENSE, encoding="utf-8")
    (tmp_path / "PATCHES.md").write_text("## libfoo\n- upstream: url\n", encoding="utf-8")
    assert any("missing issue" in v for v in VendorPolicy(tmp_path).audit()["violations"])
    (tmp_path / "PATCHES.md").write_text("## ghost\n- upstream: url\n- issue: 1\n",
                                         encoding="utf-8")
    assert any("orphan" in v for v in VendorPolicy(tmp_path).audit()["violations"])
    with pytest.raises(W1BackendError):
        VendorPolicy(tmp_path, vendor_dir="../outside")


# ------------------------------------------------------------------ W1.17

FEEDBACK = ("Contact alice@example.com. token=sk-abcdef1234567890. "
            "API_KEY=supersecretvalue123 from C:\\Users\\alice\\secret.txt. "
            "See https://github.com/org/repo and https://docs.keel.example/guide. "
            "Host 10.2.3.4. Please add Discord and an issues tab.")


def test_w117_redaction_and_feedback_bundle():
    redacted, counts = redact_feedback(FEEDBACK)
    assert "alice@example.com" not in redacted
    assert "supersecretvalue123" not in redacted
    assert "sk-abcdef1234567890" not in redacted
    assert "C:\\Users\\alice" not in redacted
    assert counts["emails"] == 1 and counts["paths"] >= 1
    assert counts["ips"] == 1

    bundle = build_feedback_bundle(FEEDBACK)
    assert bundle["channel"] == "in-app"
    assert bundle["docs_site"] == "https://docs.keel.example"
    assert "https://docs.keel.example/guide" in bundle["redacted"]
    assert bundle["violations"] == ["discord", "github.com/", "issues tab"]
    assert bundle["safe_to_send"] is False
    assert "supersecretvalue123" not in json.dumps(bundle)
    clean = build_feedback_bundle("The UI is slow when loading a large session.")
    assert clean["safe_to_send"] is True and clean["redactions"] == {}
    assert feedback_policy()["channels"] == ["email", "in-app"]
    with pytest.raises(W1BackendError):
        build_feedback_bundle("x", channel="issues")
    with pytest.raises(W1BackendError):
        redact_feedback(None)

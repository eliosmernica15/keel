"""Unit tests for the Y4 / D4 / X7 backend feature module.

Run with::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests', \
pattern='test_y4_d4_x7_backend.py'); \
raise SystemExit(0 if unittest.TextTestRunner().run(suite).wasSuccessful() else 1)"

Every not_started Y4.*/D4.*/X7.* feature has a dedicated test class.  No test
needs a network, a daemon or a third-party package.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from keel import y4_d4_x7_backend as m


class Y4D4X7BehaviorCoverageTests(unittest.TestCase):
    """Replace the old descriptor-only coverage guards with real execution.

    The previous tests here only counted IDs and checked that mapped symbol
    names existed in ``globals()`` (via ``verify_coverage()``).  A module whose
    every function was a stub returning ``None`` still passed.  Each feature ID
    below is now *executed* with concrete inputs and its concrete output
    asserted, so a no-op implementation fails the test.
    """

    def test_y4_unknown_removal_keys_are_reported(self):
        """Operator precedence must not hide keys outside the contract."""
        issues = m.verify_clean_removal(set(), {"totally-unknown"})
        self.assertTrue(issues)
        self.assertTrue(any(i.code == "unknown_removal" and
                            i.location == "totally-unknown" for i in issues))
        # A contract key removed while still registered is also reported.
        keys = {op["key"] for op in m.association_registration_plan()}
        if keys:
            contract_key = sorted(keys)[0]
            issues2 = m.verify_clean_removal({contract_key}, set())
            self.assertTrue(any(i.code == "association_left_behind" for i in issues2))

    def test_y4_d4_x7_all_31_ids_execute_real_behavior(self):
        # Every entry calls the real function/class that FEATURE_BEHAVIORS maps
        # the ID to, with concrete inputs, and returns a value we pin exactly.
        probes = {
            "Y4.1": lambda: self._reviver(),
            "Y4.2": lambda: (lambda p: (p.qr_text == p.deep_link,
                                        "channel=telegram" in p.deep_link,
                                        len(p.manual_code)))(
                m.build_onboarding_payload("telegram", "tok")),
            "Y4.4": lambda: self._secret_provider(),
            "Y4.5": lambda: self._bridge(),
            "Y4.6": lambda: self._trace_store(),
            "Y4.7": lambda: (len(m.desktop_tool_manifest()),
                             m.validate_desktop_tools(m.KEYLESS_DESKTOP_TOOLS) == ()),
            "Y4.8": lambda: self._vault(),
            "Y4.10": lambda: (len(m.list_runbooks()), m.validate_skill_library() == ()),
            "Y4.11": lambda: m.two_line_switch(model="openai/gpt",
                                               provider="openai").lines(),
            "Y4.12": lambda: (len(m.deterministic_tarball({"a.txt": b"x"})[1]),
                              m.check_artifact_budget(100, "publish_api")["ok"]),
            "Y4.14": lambda: (len(m.preset_bundle()["plugins"]),
                              len(m.preset_bundle()["mcp_servers"])),
            "D4.1": lambda: self._provider_registry(),
            "D4.3": lambda: self._workspace_gate(),
            "D4.4": lambda: m.resolve_picker_mode(m.PickerMode.NATIVE,
                                                   headless=True).value,
            "D4.5": lambda: self._node_registry(),
            "D4.6": lambda: self._settings_card(),
            "D4.8": lambda: m.t({"en": {"greet": "Hello there"}}, "greet"),
            "D4.9": lambda: (m.check_icon("notes", "plug") is None,
                             m.check_icon("notes", "new").code),
            "D4.10": lambda: self._design_guide(),
            "D4.12": lambda: (m.desktop_startup_plan().first_paint_phase.value,
                              m.desktop_startup_plan().plugins_after_ready),
            "D4.13": lambda: (m.select_port(m.PortMode.DESKTOP).port,
                              m.WEB_DEFAULT_PORT),
            "X7.1": lambda: (len(m.BUILD_TARGETS),
                             m.verify_target_matrix(m.BUILD_TARGETS) == ()),
            "X7.2": lambda: (m.windows_install_plan("per_user",
                                                    username="alice")["requires_admin"],
                             m.windows_install_plan(m.InstallScope.PER_MACHINE,
                                                    username="alice")["requires_admin"]),
            "X7.3": lambda: m.uninstall_plan(
                "keep_data",
                paths={"app": "/app", "data": "/data", "config": "/cfg",
                       "models": "/models"})["would_delete"],
            "X7.4": lambda: len(m.association_registration_plan()),
            "X7.5": lambda: (m.detect_linux_session({"WAYLAND_DISPLAY": "1"}),
                             m.detect_linux_session({})),
            "X7.6": lambda: m.checksum_manifest({"a": b"one"})["a"]
            == hashlib.sha256(b"one").hexdigest(),
            "X7.7": lambda: m.installer_text(
                {"en": {"install": "Install", "next": "Next"},
                 "de": {"install": "Installieren"}}, "next", "de"),
            "X7.8": lambda: self._download(),
            "X7.9": lambda: self._import_plan(),
            "X7.10": lambda: self._disk_usage(),
        }
        expected = {
            "Y4.1": (True, "active", True),
            "Y4.2": (True, True, 8),
            "Y4.4": (True, "KEEL_API_KEY", "s.env"),
            "Y4.5": ("running", False, True, 1),
            "Y4.6": (1, ("model:gpt", "tool:bash")),
            "Y4.7": (11, True),
            "Y4.8": (True, "# Hello", ("hello.md",)),
            "Y4.10": (21, True),
            "Y4.11": ("model: openai/gpt", "provider: openai"),
            "Y4.12": (64, True),
            "Y4.14": (16, 13),
            "D4.1": (False, "openai", 1),
            "D4.3": (False, True),
            "D4.4": "in_page",
            "D4.5": (["status"], ("tool_call",)),
            "D4.6": {"mode": "safe"},
            "D4.8": "Hello there",
            "D4.9": (True, "designer_approval_required"),
            "D4.10": (1, "guide_not_loaded", 5),
            "D4.12": ("packaged_assets", True),
            "D4.13": (0, m.WEB_DEFAULT_PORT),
            "X7.1": (7, True),
            "X7.2": (False, True),
            "X7.3": ["/app"],
            "X7.4": 4,
            "X7.5": ("wayland", "headless"),
            "X7.6": True,
            "X7.7": "Next",
            "X7.8": (True, "sha256 mismatch"),
            "X7.9": ["n.md"],
            "X7.10": (100, ["models/m.bin"]),
        }
        self.assertEqual(set(probes), set(expected))
        for fid in sorted(expected):
            with self.subTest(fid=fid):
                self.assertEqual(probes[fid](), expected[fid])

    def test_y4_d4_x7_prior_p0_rows_execute_verified_contracts(self):
        """The 6 prior P0 rows must point at modules with real, callable contracts."""
        from keel import composition_contracts as cc
        from keel import identity_contracts as ic

        boot = ic.first_boot_decision(())
        self.assertFalse(boot.allowed)
        self.assertIn("no_probe_results", boot.reasons[0])
        soul = ic.default_soul("keel")
        self.assertEqual(soul.agent_id, "keel")
        self.assertTrue(ic.render_soul(soul).startswith("# SOUL.md"))
        self.assertEqual(ic.parse_version("1.2.3"), "1.2.3")
        self.assertEqual(ic.scan_secrets(()), ())
        provider = cc.make_provider("openai", base_url="https://api.openai.com/v1")
        self.assertEqual(cc.endpoint_scope(provider), "remote")
        self.assertEqual(cc.make_presenter("bash").tool_name, "bash")
        self.assertEqual(cc.validate_plugin(cc.make_plugin("notes", "Notes")), ())

    # -- helpers used by the dispatch table ---------------------------------
    def _reviver(self):
        r = m.McpServerReviver(["wiki"], probe_interval_s=300).reload("wiki")
        return (r.instant, r.phase.value, "revived" in r.detail)

    def _secret_provider(self):
        store = m.SecretProviderMap()
        store.add_binding("vault", {"API_KEY": "KEEL_API_KEY"}, token_env_file="s.env")
        store.enable("op", token_present=True, stdin_isatty=False)
        return (store.enabled, store.resolve("API_KEY"), store.token_file("vault"))

    def _bridge(self):
        b = m.SupervisedBridge()
        b.start("https://t.example/h", key="k")
        return (b.phase.value, b.wake_if_keyed("wrong"),
                b.wake_if_keyed("k"), b.deliver({"e": 1})["seq"])

    def _trace_store(self):
        store = m.TraceStore()
        store.record("model", "gpt", ts=1)
        store.record("tool", "bash", detail="ls", ts=2)
        return (len(store.query(kind="tool")), store.what_did_you_do())

    def _vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = m.ObsidianVault(Path(tmp) / "v")
            note = v.create_note("hello", "# Hello")
            return (note["path"].endswith("hello.md"), v.read_note("hello"),
                    v.list_notes())

    def _provider_registry(self):
        reg = m.ProviderRegistry()
        applied = reg.configure("openai", key_ref="K", model="gpt")
        return (applied["restart_required"], reg.resolve("gpt"),
                reg.snapshot()["version"])

    def _workspace_gate(self):
        gate = m.WorkspaceGate("/d")
        before = gate.can_compose()
        gate.select("/c")
        return (before, gate.can_compose())

    def _node_registry(self):
        reg = m.NodeRendererRegistry()
        reg.register(m.ConversationNodeDefinition(
            "tool_call", "tool_card", ("name", "status")))
        return (reg.render({"type": "tool_call", "name": "bash"})["missing_fields"],
                reg.types())

    def _settings_card(self):
        reg = m.SettingsCardRegistry()
        manifest = {"plugin": "notes", "settings_cards": [
            {"id": "general", "title": "G", "fields": [
                {"key": "mode", "type": "enum", "default": "fast",
                 "options": ["fast", "safe"]}]}]}
        reg.register_manifest(manifest)
        return reg.render_form("general", {"mode": "safe"})["values"]

    def _design_guide(self):
        skill = m.DesignGuideSkill()
        issues = skill.gate(["site/ui/app.ts"])
        return (len(issues), issues[0].code, len(skill.load()))

    def _download(self):
        data = b"bytes"
        digest = hashlib.sha256(data).hexdigest()
        return (m.verify_download(data, digest, filename="f",
                                  expected_size=len(data)).ok,
                m.verify_download(data, "0" * 64).reason)

    def _import_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "v"
            src.mkdir()
            (src / "n.md").write_text("# n", encoding="utf-8")
            return m.plan_import(src, "obsidian")["files"]

    def _disk_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models").mkdir()
            (root / "models" / "m.bin").write_bytes(b"x" * 100)
            report = m.scan_disk_usage(
                root, caps={"models": 10, "caches": 0, "sessions": 0, "trash": 0})
            return (report["models"]["bytes"],
                    m.safe_clean_plan(report, "models")["remove"])


# ---------------------------------------------------------------- Y4
class Y4_1McpRevivalTests(unittest.TestCase):
    def test_reload_revives_instantly_and_probe_is_configurable(self):
        r = m.McpServerReviver(["wiki"], probe_interval_s=300)
        self.assertIs(r.phase("wiki"), m.ServerPhase.ACTIVE)
        self.assertIs(r.mark_dormant("wiki"), m.ServerPhase.DORMANT)
        result = r.reload("wiki")
        self.assertTrue(result.instant)
        self.assertIs(result.phase, m.ServerPhase.ACTIVE)
        self.assertIn("revived", result.detail)

        r.mark_dormant("wiki")
        self.assertFalse(r.probe_due("wiki", 0))
        r.record_probe("wiki", 100)
        self.assertFalse(r.probe_due("wiki", 399))
        self.assertTrue(r.probe_due("wiki", 400))

    def test_due_servers_is_deterministic(self):
        r = m.McpServerReviver(["b", "a"], probe_interval_s=10)
        r.mark_dormant("a")
        r.mark_dormant("b")
        r.record_probe("a", 0)
        r.record_probe("b", 50)
        self.assertEqual(r.due_servers(10), ("a",))
        self.assertEqual(r.due_servers(60), ("a", "b"))

    def test_bad_interval_rejected(self):
        with self.assertRaises(m.BackendError):
            m.McpServerReviver(probe_interval_s=0)


class Y4_2PairingTests(unittest.TestCase):
    def test_deep_link_qr_and_manual_fallback(self):
        p = m.build_onboarding_payload(m.PairingChannel.TELEGRAM, "token123")
        self.assertEqual(p.qr_text, p.deep_link)
        self.assertIn("channel=telegram", p.deep_link)
        self.assertIn("token=token123", p.deep_link)
        self.assertTrue(m.has_manual_fallback(p))
        self.assertEqual(len(p.manual_code), 8)
        self.assertEqual(p.manual_code,
                         m.build_onboarding_payload("telegram", "token123").manual_code)

    def test_deep_link_url_encodes_token_and_cannot_inject_query_parameters(self):
        token = "abc&host=evil.example&port=1"
        p = m.build_onboarding_payload("telegram", token,
                                       host="127.0.0.1", port=8739)
        query = parse_qs(urlparse(p.deep_link).query)
        self.assertEqual(query["token"], [token])
        self.assertEqual(query["host"], ["127.0.0.1"])
        self.assertEqual(query["port"], ["8739"])
        self.assertEqual(p.deep_link.count("host="), 1)
        self.assertEqual(p.deep_link.count("port="), 1)
        self.assertIn("token=abc%26host%3Devil.example%26port%3D1", p.deep_link)

    def test_empty_token_rejected(self):
        with self.assertRaises(m.BackendError):
            m.build_onboarding_payload("telegram", "  ")


class Y4_4SecretProviderTests(unittest.TestCase):
    def test_disabled_until_token_and_noninteractive(self):
        store = m.SecretProviderMap()
        self.assertIsNone(store.resolve("API_KEY"))
        store.add_binding("vault", {"API_KEY": "KEEL_API_KEY"},
                          token_env_file="secrets.env")
        with self.assertRaises(m.BackendError):
            store.enable("op", token_present=False, stdin_isatty=False)
        store.enable("op", token_present=True, stdin_isatty=False)
        self.assertTrue(store.enabled)
        self.assertEqual(store.resolve("API_KEY"), "KEEL_API_KEY")
        self.assertEqual(store.token_file("vault"), "secrets.env")

    def test_enabling_prompt_provider_is_refused(self):
        store = m.SecretProviderMap()
        self.assertFalse(store.is_non_interactive(token_present=True,
                                                  stdin_isatty=False,
                                                  prompt_required=True))
        with self.assertRaises(m.BackendError):
            store.enable("bw", token_present=True, stdin_isatty=False,
                         prompt_required=True)

    def test_token_file_must_be_separate_and_fields_upper_snake(self):
        store = m.SecretProviderMap()
        with self.assertRaises(m.BackendError):
            store.add_binding("v", {"a": "B"}, token_env_file="config.yaml")
        with self.assertRaises(m.BackendError):
            store.add_binding("v", {"lower": "OK"}, token_env_file="s.env")


class Y4_5BridgeTests(unittest.TestCase):
    def test_wake_key_and_user_tunnel(self):
        b = m.SupervisedBridge()
        with self.assertRaises(m.BackendError):
            b.deliver({"x": 1})
        self.assertEqual(len(b.provision_plan()), 4)
        b.start("https://tunnel.example/hook", key="k")
        self.assertIs(b.phase, m.BridgePhase.RUNNING)
        self.assertFalse(b.wake_if_keyed("wrong"))
        self.assertTrue(b.wake_if_keyed("k"))
        first = b.deliver({"event": "ping"})
        self.assertEqual(first["seq"], 1)
        self.assertEqual(len(first["id"]), 12)
        self.assertEqual(b.deliver({"event": "ping"})["seq"], 2)
        b.suspend()
        self.assertIs(b.phase, m.BridgePhase.SUSPENDED)

    def test_insecure_or_unprovided_tunnel_rejected(self):
        b = m.SupervisedBridge()
        with self.assertRaises(m.BackendError):
            b.start("http://tunnel.example", key="k")
        with self.assertRaises(m.BackendError):
            b.start("https://tunnel.example", key="k", user_provided=False)


class Y4_6TraceTests(unittest.TestCase):
    def test_record_query_and_summarize(self):
        store = m.TraceStore()
        store.record("model", "gpt", ts=1)
        store.record("tool", "bash", detail="ls", ts=2)
        found = store.query(kind="tool")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "bash")
        self.assertEqual(store.what_did_you_do(), ("model:gpt", "tool:bash"))
        self.assertEqual(store.query(since_seq=1, limit=1)[0].seq, 2)
        self.assertEqual(store.mcp_tool_descriptor()["name"], "traces")
        self.assertIn("kind", store.mcp_tool_descriptor()["inputSchema"]["properties"])

    def test_unknown_kind_rejected(self):
        with self.assertRaises(m.BackendError):
            m.TraceStore().record("bogus", "x")


class Y4_7DesktopToolTests(unittest.TestCase):
    def test_eleven_keyless_tools(self):
        manifest = m.desktop_tool_manifest()
        self.assertEqual(len(manifest), 11)
        self.assertTrue(all(t["requires_key"] is False for t in manifest))
        self.assertTrue(all(t["auth"] == "vm_auth" for t in manifest))
        self.assertEqual(m.validate_desktop_tools(m.KEYLESS_DESKTOP_TOOLS), ())
        issues = m.validate_desktop_tools(["screenshot"])
        self.assertEqual(len(issues), 10)
        self.assertTrue(all(i.code == "missing_desktop_tool" for i in issues))


class Y4_8VaultTests(unittest.TestCase):
    def test_markdown_notes_and_path_containment(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = m.ObsidianVault(Path(tmp) / "vault")
            note = v.create_note("hello", "# Hello")
            self.assertTrue(note["path"].endswith("hello.md"))
            self.assertEqual(v.read_note("hello"), "# Hello")
            self.assertEqual(v.list_notes(), ("hello.md",))
            self.assertTrue(v.note_path("../../evil.md").parent == v.root)
            self.assertTrue(v.note_path("plain").name.endswith(".md"))
            with self.assertRaises(m.BackendError):
                v.create_note("hello", "again")

    def test_editor_command_never_uses_shell(self):
        self.assertEqual(m.ObsidianVault.editor_command("/a/b.md", "code"),
                         ("code", "--goto", "/a/b.md"))
        self.assertEqual(m.ObsidianVault.editor_command("/a/b.md", "nvim"),
                         ("nvim", "/a/b.md"))


class Y4_10SkillLibraryTests(unittest.TestCase):
    def test_21_runbooks_each_mapped(self):
        books = m.list_runbooks()
        self.assertEqual(len(books), 21)
        self.assertEqual(m.validate_skill_library(), ())
        self.assertEqual(m.resolve_runbook("telegram")["target"], "channel:telegram")
        self.assertIsNone(m.resolve_runbook("missing"))


class Y4_11ConfigSwitchTests(unittest.TestCase):
    def test_two_line_switch_and_reference(self):
        sw = m.two_line_switch(model="openai/gpt", provider="openai")
        self.assertEqual(sw.lines(), ("model: openai/gpt", "provider: openai"))
        examples = m.config_reference_examples(["beta", "alpha"])
        self.assertEqual(list(examples), ["alpha", "beta"])
        self.assertEqual(examples["alpha"]["config"]["secrets"],
                         {"api_key": "${KEEL_API_KEY}"})
        self.assertTrue(m.is_two_line_switch(["a:1", "b:2", "c:3"],
                                             ["a:1", "b:9", "c:8"]))
        self.assertFalse(m.is_two_line_switch(["a:1", "b:2"], ["a:9", "b:2"]))


class Y4_12DeterministicBuildTests(unittest.TestCase):
    def test_reproducible_tarball_and_budget(self):
        files = {"b.txt": b"second", "a.txt": b"first"}
        blob, digest = m.deterministic_tarball(files)
        blob2, digest2 = m.deterministic_tarball(dict(reversed(list(files.items()))))
        self.assertEqual(blob, blob2)
        self.assertEqual(digest, digest2)
        self.assertEqual(len(digest), 64)
        self.assertTrue(m.check_artifact_budget(100, "publish_api")["ok"])
        over = m.check_artifact_budget(11 * 1024 * 1024, "publish_api")
        self.assertFalse(over["ok"])
        self.assertGreater(over["over_by"], 0)
        with self.assertRaises(m.BackendError):
            m.check_artifact_budget(1, "unknown")

    def test_tarball_rejects_path_traversal_members(self):
        """Members must never escape the archive root on extraction."""
        for bad in ("../escape", "a/../../escape", "/etc/passwd", "C:\\evil", ".."):
            with self.subTest(bad=bad), self.assertRaises(m.BackendError):
                m.deterministic_tarball({bad: b"x"})
        # A normal nested path is still accepted and normalized with "/".
        blob, _ = m.deterministic_tarball({"a/../b.txt": b"x"})
        import io as _io
        import tarfile as _tarfile
        names = [ti.name for ti in _tarfile.open(fileobj=_io.BytesIO(blob)).getmembers()]
        self.assertEqual(names, ["b.txt"])


class Y4_14PresetTests(unittest.TestCase):
    def test_16_plugins_and_13_free_mcp(self):
        bundle = m.preset_bundle()
        self.assertEqual(len(bundle["plugins"]), 16)
        self.assertEqual(len(bundle["mcp_servers"]), 13)
        self.assertEqual(m.validate_preset(bundle), ())
        bad = dict(bundle, all_mcp_free_tier=False)
        self.assertEqual(m.validate_preset(bad)[0].code, "paid_mcp")


# ---------------------------------------------------------------- D4
class D4_1HotApplyTests(unittest.TestCase):
    def test_save_applies_route_without_restart(self):
        reg = m.ProviderRegistry()
        applied = reg.configure("openai", key_ref="KEEL_KEY", model="gpt")
        self.assertFalse(applied["restart_required"])
        self.assertEqual(reg.resolve("gpt"), "openai")
        self.assertEqual(reg.snapshot()["version"], 1)
        result = reg.test("openai", ok=True, model="gpt", latency_ms=12,
                          message="connected")
        self.assertEqual(result.as_dict()["message"], "connected")
        self.assertTrue(result.ok)


class D4_3WorkspaceGateTests(unittest.TestCase):
    def test_composer_locked_until_explicit_selection(self):
        gate = m.WorkspaceGate("/process/default")
        self.assertFalse(gate.can_compose())
        empty = gate.empty_state()
        self.assertFalse(empty["default_is_selection"])
        self.assertEqual(empty["action"], "select_workspace")
        self.assertTrue(gate.chat_allowed())
        gate.select("/chosen")
        self.assertTrue(gate.can_compose())
        gate.clear()
        self.assertFalse(gate.can_compose())
        self.assertFalse(m.WorkspaceGate("/d", chat_without_workspace=False).chat_allowed())


class D4_4PickerTests(unittest.TestCase):
    def test_headless_and_overlay_pin(self):
        self.assertIs(m.resolve_picker_mode(m.PickerMode.NATIVE, headless=True),
                      m.PickerMode.IN_PAGE)
        pinned = m.PickerConfig(overlay_pin=m.PickerMode.NATIVE)
        self.assertIs(m.resolve_picker_mode(m.PickerMode.IN_PAGE, headless=True,
                                            config=pinned), m.PickerMode.NATIVE)
        self.assertIs(m.resolve_picker_mode("native"), m.PickerMode.NATIVE)

    def test_list_directories_skips_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "src").mkdir()
            (Path(tmp) / "docs").mkdir()
            (Path(tmp) / ".git").mkdir()
            self.assertEqual(m.list_directories(tmp), ("docs", "src"))
            self.assertEqual(m.list_directories(tmp, include_hidden=True),
                             (".git", "docs", "src"))


class D4_5NodeRegistryTests(unittest.TestCase):
    def test_register_render_and_validation(self):
        reg = m.NodeRendererRegistry()
        defn = m.ConversationNodeDefinition("tool_call", "tool_card",
                                            ("name", "status"))
        reg.register(defn)
        with self.assertRaises(m.BackendError):
            reg.register(defn)
        partial = reg.render({"type": "tool_call", "name": "bash"})
        self.assertEqual(partial["missing_fields"], ["status"])
        self.assertFalse(partial["renderable"])
        full = reg.render({"type": "tool_call", "name": "bash", "status": "ok"})
        self.assertTrue(full["renderable"])
        self.assertEqual(reg.types(), ("tool_call",))
        with self.assertRaises(KeyError):
            reg.render({"type": "unknown"})


class D4_6SettingsCardTests(unittest.TestCase):
    def test_manifest_registration_and_form(self):
        reg = m.SettingsCardRegistry()
        manifest = {"plugin": "notes", "settings_cards": [
            {"id": "general", "title": "General", "fields": [
                {"key": "mode", "type": "enum", "default": "fast",
                 "options": ["fast", "safe"]},
                {"key": "enabled", "type": "boolean", "default": True},
            ]},
            {"id": "bad", "title": "Bad", "fields": [
                {"key": "x", "type": "unknown"},
            ]},
        ]}
        issues = reg.register_manifest(manifest)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "bad_field_type")
        self.assertEqual(len(reg.cards_for("notes")), 1)
        form = reg.render_form("general", {"mode": "safe"})
        self.assertEqual(form["values"], {"mode": "safe", "enabled": True})
        self.assertEqual(form["errors"], [])
        bad_form = reg.render_form("general", {"mode": "nope"})
        self.assertEqual(len(bad_form["errors"]), 1)


class D4_8CopyGateTests(unittest.TestCase):
    def test_catalog_lookup_and_hardcoded_copy_gate(self):
        catalog = {"en": {"greet": "Hello there"}}
        self.assertEqual(m.t(catalog, "greet"), "Hello there")
        self.assertEqual(m.t(catalog, "absent"), "absent")
        sources = {"a.js": 'const a = "Hardcoded phrase";\nconst b = t("greet");\n'}
        issues = m.verify_ui_copy(sources, catalog)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "hardcoded_copy")
        self.assertEqual(m.verify_ui_copy({}, catalog,
                                          plugin_titles={"p": "Connect Your Calendar"})[0].code,
                         "title_case_plugin_title")

    def test_sentence_case(self):
        self.assertTrue(m.is_sentence_case("Connect your calendar"))
        self.assertFalse(m.is_sentence_case("Connect Your Calendar"))


class D4_9ArtworkTests(unittest.TestCase):
    def test_approved_icons_and_approval_gate(self):
        self.assertIsNone(m.check_icon("notes", "plug"))
        issue = m.check_icon("notes", "newglyph")
        self.assertEqual(issue.code, "designer_approval_required")
        self.assertIsNone(m.check_icon("notes", "newglyph", designer_approved=True))
        issues = m.verify_bundled_icons({"a": "plug", "b": "newglyph"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].location, "b")


class D4_10DesignGuideTests(unittest.TestCase):
    def test_guide_must_load_before_ui_change(self):
        skill = m.DesignGuideSkill()
        issues = skill.gate(["site/ui/app.ts", "README.md"])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "guide_not_loaded")
        self.assertEqual(len(skill.load()), 5)
        self.assertEqual(skill.gate(["site/ui/app.ts"]), ())
        self.assertTrue(skill.is_ui_change("site/ui/app.js"))
        self.assertFalse(skill.is_ui_change("README.md"))
        self.assertEqual(skill.load_reference("tokens"), "docs/design/tokens.json")
        with self.assertRaises(KeyError):
            skill.load_reference("unknown")


class D4_12StartupTests(unittest.TestCase):
    def test_assets_paint_first_plugins_last(self):
        plan = m.desktop_startup_plan()
        self.assertEqual(plan.first_paint_phase, m.StartupPhase.PACKAGED_ASSETS)
        self.assertTrue(plan.plugins_after_ready)
        self.assertTrue(m.is_valid_startup_order(m.STARTUP_PHASES))
        self.assertFalse(m.is_valid_startup_order(reversed(m.STARTUP_PHASES)))
        self.assertEqual(plan.as_dict()["phases"][0], "packaged_assets")


class D4_13PortTests(unittest.TestCase):
    def test_web_default_desktop_ephemeral_profile_override(self):
        web = m.select_port(m.PortMode.WEB)
        self.assertEqual(web.port, m.WEB_DEFAULT_PORT)
        self.assertEqual(web.source, "web_default")
        desk = m.select_port(m.PortMode.DESKTOP)
        self.assertEqual(desk.port, 0)
        self.assertEqual(desk.source, "os_assigned")
        profile = m.select_port(m.PortMode.WEB, profile_port=9999, occupied=[8739])
        self.assertEqual(profile.port, 9999)
        self.assertFalse(profile.conflict)
        conflict = m.select_port(m.PortMode.WEB, occupied=[8739])
        self.assertTrue(conflict.conflict)
        self.assertIn("already in use", conflict.message)
        with self.assertRaises(m.BackendError):
            m.select_port(m.PortMode.WEB, profile_port=70000)


# ---------------------------------------------------------------- X7
class X7_1BuildTargetsTests(unittest.TestCase):
    def test_required_matrix_and_native_deps(self):
        self.assertEqual(len(m.required_build_targets()), 7)
        self.assertEqual(m.verify_target_matrix(m.BUILD_TARGETS), ())
        issues = m.verify_target_matrix([m.PlatformTarget("linux", "arm64")])
        self.assertEqual(len(issues), 6)
        self.assertEqual(m.verify_native_deps(m.PlatformTarget("linux", "arm64"),
                                              ["zlib", "sqlite", "ssl"]), ())
        self.assertEqual(len(m.verify_native_deps(m.PlatformTarget("windows", "arm64"),
                                                  [])), 3)


class X7_2InstallScopeTests(unittest.TestCase):
    def test_per_user_needs_no_admin(self):
        per_user = m.windows_install_plan("per_user", username="alice")
        self.assertFalse(per_user["requires_admin"])
        self.assertIn("AppData", per_user["install_root"])
        per_machine = m.windows_install_plan(m.InstallScope.PER_MACHINE,
                                             username="alice")
        self.assertTrue(per_machine["requires_admin"])
        self.assertIn("Program Files", per_machine["install_root"])


class X7_3UninstallTests(unittest.TestCase):
    def test_deletion_lists_by_mode(self):
        paths = {"app": "/app", "data": "/data", "config": "/cfg", "models": "/models"}
        keep = m.uninstall_plan("keep_data", paths=paths)
        self.assertEqual(keep["would_delete"], ["/app"])
        remove = m.uninstall_plan("remove_data", paths=paths)
        self.assertEqual(remove["would_delete"], ["/app", "/cfg", "/data"])
        allmode = m.uninstall_plan("remove_data_and_models", paths=paths)
        self.assertEqual(allmode["would_delete"], ["/app", "/cfg", "/data", "/models"])
        self.assertTrue(allmode["dry_run"] and allmode["requires_confirmation"])


class X7_4AssociationsTests(unittest.TestCase):
    def test_registration_and_clean_removal(self):
        reg = m.association_registration_plan()
        self.assertEqual(len(reg), 4)
        removal = m.association_removal_plan()
        self.assertTrue(all(op["action"] == "remove" for op in removal))
        keys = [op["key"] for op in reg]
        self.assertEqual(m.verify_clean_removal(keys, keys), ())
        issues = m.verify_clean_removal(keys, keys[:-1])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "association_left_behind")


class X7_5LinuxTests(unittest.TestCase):
    def test_session_tray_appimage_and_sandbox(self):
        self.assertEqual(m.detect_linux_session({"WAYLAND_DISPLAY": "1"}), "wayland")
        self.assertEqual(m.detect_linux_session({"DISPLAY": ":0"}), "x11")
        self.assertEqual(m.detect_linux_session({}), "headless")
        plan = m.linux_tray_plan("headless", has_tray=False)
        self.assertTrue(plan["fallback_required"])
        self.assertIn("Name=Keel", m.appimage_desktop_entry())
        self.assertNotIn("--no-sandbox", m.sandbox_flags())
        self.assertIn("--no-sandbox", m.sandbox_flags("user_opt_in_no_sandbox"))


class X7_6AntivirusTests(unittest.TestCase):
    def test_playbook_and_checksums(self):
        manifest = m.checksum_manifest({"b": b"two", "a": b"one"})
        self.assertEqual(list(manifest), ["a", "b"])
        self.assertEqual(manifest["a"], hashlib.sha256(b"one").hexdigest())
        book = m.antivirus_playbook()
        self.assertEqual(len(book["steps"]), 4)
        self.assertEqual(len(book["submission_channels"]), 3)


class X7_7InstallerLocalesTests(unittest.TestCase):
    def test_catalog_parity_and_fallback(self):
        catalog = {"en": {"install": "Install", "next": "Next"},
                   "de": {"install": "Installieren"}}
        self.assertEqual(m.installer_text(catalog, "next", "de"), "Next")
        issues = m.installer_catalog_issues(catalog)
        self.assertTrue(any(i.code == "untranslated_installer_key" for i in issues))
        self.assertEqual(len(m.INSTALLER_LOCALES), 7)


class X7_8DownloadIntegrityTests(unittest.TestCase):
    def test_verify_and_parse_checksum(self):
        data = b"installer-bytes"
        digest = hashlib.sha256(data).hexdigest()
        ok = m.verify_download(data, digest, filename="keel.exe", expected_size=len(data))
        self.assertTrue(ok.ok)
        self.assertEqual(ok.reason, "integrity verified")
        self.assertEqual(m.verify_download(data, "0" * 64).reason, "sha256 mismatch")
        self.assertEqual(m.verify_download(data, digest, expected_size=1).reason,
                         "size mismatch")
        parsed = m.parse_checksum_line(f"{digest}  keel.exe")
        self.assertEqual(parsed, {"sha256": digest, "filename": "keel.exe"})
        self.assertIsNone(m.parse_checksum_line("not a checksum"))


class X7_9ImportWizardTests(unittest.TestCase):
    def test_dry_run_then_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vault"
            source.mkdir()
            (source / "note.md").write_text("# note", encoding="utf-8")
            (source / "ignored.txt").write_text("x", encoding="utf-8")
            plan = m.plan_import(source, "obsidian")
            self.assertEqual(plan["files"], ["note.md"])
            self.assertTrue(plan["dry_run"])
            target = Path(tmp) / "out"
            preview = m.execute_import(plan, target, dry_run=True)
            self.assertEqual(preview["copied"], [])
            self.assertFalse(target.exists())
            done = m.execute_import(plan, target, dry_run=False)
            self.assertEqual(done["copied"], ["note.md"])
            self.assertEqual((target / "note.md").read_text(encoding="utf-8"), "# note")
        with self.assertRaises(m.BackendError):
            m.plan_import(".", "unsupported_tool")


class X7_10DiskUsageTests(unittest.TestCase):
    def test_scan_and_safe_clean_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models").mkdir()
            (root / "caches").mkdir()
            big = root / "models" / "m.bin"
            big.write_bytes(b"x" * 100)
            report = m.scan_disk_usage(root, caps={"models": 10, "caches": 0,
                                                  "sessions": 0, "trash": 0})
            self.assertEqual(report["models"]["bytes"], 100)
            self.assertEqual(report["models"]["over_by"], 90)
            plan = m.safe_clean_plan(report, "models")
            self.assertEqual(plan["remove"], ["models/m.bin"])
            self.assertTrue(plan["dry_run"])
            self.assertTrue(big.exists())  # planning never deletes
        with self.assertRaises(m.BackendError):
            m.safe_clean_plan({"x": {}}, "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)

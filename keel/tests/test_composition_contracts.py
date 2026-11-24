"""P0 composition-contract tests (stdlib-only, no model/subprocess/network).

This suite covers the pure descriptor/policy surface of
``keel.composition_contracts`` that supports the registry rows:

* **D4.2**  -- custom OpenAI-compatible endpoints as a first-class provider
  kind (local servers / LAN), with secret references that never leak;
* **D4.7**  -- tool UI presenters as pure functions over raw events plus
  persisted result metadata (summary, icon, expanded view);
* **D4.11** -- the bundled Plugin Manager and extension activation gated by
  approval, inside a deterministic typed layer composition where protected
  core/bundle contributions win and paths stay contained.

Invariants under test: typed layering descriptors, deterministic (order
independent) merge, protected-core precedence, lexical path containment,
no secret leakage (including through errors and serialization), and
fail-closed validation of every unknown/invalid value.

Run from the worktree root with the standard-library runner::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_composition_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import keel.composition_contracts as cc
from keel.composition_contracts import (
    FEATURE_IDS,
    PROTECTED_ORIGINS,
    BUNDLE,
    CORE,
    PLUGIN,
    USER,
    ContractValidationError,
    LayerOrigin,
    PluginDescriptor,
    Presentation,
    PresenterDescriptor,
    ProviderDescriptor,
    ProviderKind,
    SecretRef,
    can_activate_plugin,
    compose_layers,
    endpoint_scope,
    is_contained,
    is_secret_reference,
    looks_like_secret,
    make_layer,
    make_plugin,
    make_presenter,
    make_provider,
    make_secret_ref,
    merge_presenters,
    merge_providers,
    present,
    redact,
    render_tool_card,
    safe_join,
    set_plugin_enabled,
    validate_composition,
    validate_plugin,
    validate_presenter,
    validate_provider,
    with_plugin_enabled,
)


KEY = "sk-abcdefghijklmnopqrstuvwxyz"


def _provider(name="local-llm", url="http://127.0.0.1:11434/v1", **kw):
    return make_provider(name, base_url=url, **kw)


def _presenter(tool="shell", origin=CORE, **kw):
    return make_presenter(tool, origin=origin, **kw)


def _plugin(pid="ext", origin=PLUGIN, **kw):
    return make_plugin(pid, pid.title(), origin=origin, **kw)


class TestSecretHandling(unittest.TestCase):
    """Secrets are references only; literal values are detected and scrubbed."""

    def test_registry_ids_declared(self):
        self.assertEqual(tuple(FEATURE_IDS), ("D4.2", "D4.7", "D4.11"))

    def test_literal_secret_prefixes_detected(self):
        for value in (
            KEY,
            "ghp_abcdefghijklmnopqrstuvwxyz",
            "xoxb-abcdefghijklmnopqrstuvwxyz",
            "AKIAABCDEFGHIJKLMNOP",
            "api_key=" + KEY,
        ):
            with self.subTest(value=value):
                self.assertTrue(looks_like_secret(value))

    def test_plain_text_is_not_a_secret(self):
        for value in ("acme-provider", "http://localhost:11434/v1", "shell tool", ""):
            with self.subTest(value=value):
                self.assertFalse(looks_like_secret(value))

    def test_references_are_not_literal_secrets(self):
        for ref in (
            "env:KEEL_KEY", "keyring:keel/key", "secret://vault/k",
            "file:/run/secrets/k",
        ):
            with self.subTest(ref=ref):
                self.assertTrue(is_secret_reference(ref))
                self.assertFalse(looks_like_secret(ref))

    def test_redact_removes_assignment_and_prefixed_secrets(self):
        out = redact("api_key=%s failed" % KEY)
        self.assertNotIn(KEY, out)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz",
                         redact("header ghp_abcdefghijklmnopqrstuvwxyz"))

    def test_redact_keeps_non_secret_text(self):
        self.assertEqual(redact("provider acme is ready"), "provider acme is ready")

    def test_secret_ref_public_form_and_validation(self):
        ref = make_secret_ref("env", "KEEL_KEY")
        self.assertEqual(ref.describe(), "env:KEEL_KEY")
        self.assertEqual(
            ref.to_public_dict(),
            {"source": "env", "name": "KEEL_KEY", "required": True},
        )
        self.assertEqual(SecretRef.from_dict(ref.to_public_dict()), ref)

    def test_invalid_secret_ref_fails_closed(self):
        for source, name in (
            ("env", ""), ("env", "A B"), ("env", "K=secret"),
            ("inline", "x"), ("env", "../../etc/passwd"),
        ):
            with self.subTest(source=source, name=name):
                with self.assertRaises(ContractValidationError):
                    make_secret_ref(source, name)

    def test_serialized_secret_value_is_ignored(self):
        ref = SecretRef.from_dict(
            {"source": "env", "name": "K", "value": KEY}
        )
        self.assertNotIn("value", ref.to_public_dict())
        self.assertNotIn(KEY, json.dumps(ref.to_public_dict()))


class TestPathContainment(unittest.TestCase):
    """Path handling is purely lexical; no filesystem or symlink lookup."""

    def test_safe_join_normalizes_separators_and_dots(self):
        self.assertEqual(safe_join("plugins", "core", "ui.js"), "plugins/core/ui.js")
        self.assertEqual(safe_join("plugins", "a//b", "./c"), "plugins/a/b/c")
        self.assertEqual(safe_join("plugins\\core", "ui.js"), "plugins/core/ui.js")

    def test_parent_traversal_rejected(self):
        for parts in (
            ("../etc/passwd",), ("plugins/../../etc",),
            ("a", "..", "..", "x"), ("ok/../..",),
        ):
            with self.subTest(parts=parts):
                with self.assertRaises(ContractValidationError):
                    safe_join("plugins", *parts)

    def test_absolute_drive_and_unc_rejected(self):
        for path in ("/etc/passwd", "C:\\Windows\\x", "\\\\server\\share\\x", "//host/share"):
            with self.subTest(path=path):
                with self.assertRaises(ContractValidationError):
                    safe_join("plugins", path)

    def test_encoded_traversal_rejected(self):
        for path in ("%2e%2e/etc", "a/%2E%2E/b", "a%2fb", "a%5cb"):
            with self.subTest(path=path):
                with self.assertRaises(ContractValidationError):
                    safe_join("plugins", path)

    def test_nul_and_control_chars_rejected(self):
        for path in ("a\x00b", "a\nb", "a\rb"):
            with self.subTest(path=repr(path)):
                with self.assertRaises(ContractValidationError):
                    safe_join("plugins", path)

    def test_is_contained(self):
        self.assertTrue(is_contained("plugins", "plugins/core/ui.js"))
        self.assertTrue(is_contained("plugins", "plugins"))
        self.assertFalse(is_contained("plugins", "plugins/../secret"))
        self.assertFalse(is_contained("plugins", "/plugins/ui.js"))
        self.assertFalse(is_contained("plugins", "other/ui.js"))
        self.assertFalse(is_contained("plugins", "plugins/%2e%2e/ui.js"))


class TestProviderContracts(unittest.TestCase):
    """D4.2: OpenAI-compatible endpoints are typed, scoped and secret-safe."""

    def test_openai_compatible_is_first_class(self):
        provider = make_provider(
            "local-llm", kind="OpenAI-compatible",
            base_url="http://127.0.0.1:11434/v1",
        )
        self.assertEqual(provider.kind, ProviderKind.OPENAI_COMPATIBLE)
        self.assertTrue(provider.is_openai_compatible)

    def test_known_kinds_and_aliases(self):
        self.assertEqual(
            make_provider("p", base_url="https://x/v1", kind="openai").kind,
            ProviderKind.OPENAI,
        )
        self.assertEqual(
            make_provider("p", base_url="http://localhost:1/v1", kind="llama.cpp").kind,
            ProviderKind.LOCAL,
        )

    def test_endpoint_scope(self):
        self.assertEqual(endpoint_scope(_provider(url="http://localhost:11434/v1")), "local")
        self.assertEqual(endpoint_scope(_provider(url="http://127.0.0.1:1/v1")), "local")
        self.assertEqual(endpoint_scope(_provider(url="http://192.168.1.10:8000/v1")), "lan")
        self.assertEqual(endpoint_scope(_provider(url="http://10.0.0.5:1/v1")), "lan")
        self.assertEqual(endpoint_scope(_provider(url="https://api.example.com/v1")), "remote")

    def test_bad_urls_fail_closed(self):
        for url in (
            "", "not-a-url", "ftp://x/v1", "http:///v1",
            "http://user:pass@host/v1", "http://host/v1#frag",
            "http://host/v1?api_key=" + KEY, "http://host/\n/v1",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ContractValidationError):
                    _provider(url=url)

    def test_unknown_kind_fails_closed(self):
        with self.assertRaises(ContractValidationError):
            make_provider("p", base_url="https://x/v1", kind="mystery")

    def test_public_form_has_no_secret(self):
        provider = _provider(secret_ref="env:KEEL_KEY")
        public = provider.to_public_dict()
        self.assertTrue(public["has_secret"])
        self.assertEqual(public["secret_ref"], "env:KEEL_KEY")
        self.assertEqual(public["kind"], "openai_compatible")
        self.assertNotIn("sk-", json.dumps(public))

    def test_literal_key_as_secret_ref_rejected_without_leak(self):
        with self.assertRaises(ContractValidationError) as caught:
            _provider(secret_ref=KEY)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_metadata_secret_rejected_without_leak(self):
        with self.assertRaises(ContractValidationError) as caught:
            _provider(metadata={"note": KEY})
        self.assertNotIn(KEY, str(caught.exception))

    def test_provider_roundtrip_and_tamper(self):
        provider = _provider(secret_ref="env:KEEL_KEY", models=("m1", "m2"))
        self.assertEqual(ProviderDescriptor.from_dict(provider.to_dict()), provider)
        payload = provider.to_dict()
        payload["secret_ref"] = {"source": "env", "name": "K", "value": KEY}
        rebuilt = ProviderDescriptor.from_dict(payload)
        self.assertNotIn(KEY, json.dumps(rebuilt.to_public_dict()))

    def test_validate_reports_multiple_errors(self):
        errors = validate_provider(ProviderDescriptor(
            name="", kind=ProviderKind.UNKNOWN, base_url="bad",
            secret_ref=None, models=(), origin=CORE, metadata=(),
        ))
        self.assertGreaterEqual(len(errors), 3)


class TestPresenterContracts(unittest.TestCase):
    """D4.7: presenters are pure functions of events + persisted metadata."""

    def test_present_produces_summary_icon_and_expanded_view(self):
        spec = _presenter(
            icon="terminal",
            summary_fields=("command", "status"),
            expanded_fields=("exit_code",),
            metadata_fields=("duration_ms",),
        )
        card = present(
            spec,
            {"command": "ls", "status": "ok", "exit_code": 0},
            {"duration_ms": 5},
        )
        self.assertEqual(card.icon, "terminal")
        self.assertIn("command=ls", card.summary)
        self.assertIn("status=ok", card.summary)
        self.assertTrue(any("exit_code: 0" in line for line in card.expanded))
        self.assertTrue(any("duration_ms: 5" in line for line in card.expanded))
        self.assertEqual(
            set(card.fields_used),
            {"command", "status", "exit_code", "duration_ms"},
        )

    def test_present_is_deterministic_and_event_wins(self):
        spec = _presenter(summary_fields=("status",))
        a = present(spec, {"status": "ok"}, {"status": "stale"})
        b = present(spec, {"status": "ok"}, {"status": "stale"})
        self.assertEqual(a, b)
        self.assertIn("status=ok", a.summary)
        self.assertNotIn("stale", a.summary)

    def test_secret_field_rejected_at_construction(self):
        for field in ("api_key", "token", "password"):
            with self.subTest(field=field):
                with self.assertRaises(ContractValidationError):
                    _presenter(summary_fields=(field,))

    def test_secret_value_in_event_is_redacted(self):
        spec = _presenter(summary_fields=("command",))
        card = present(spec, {"command": "curl -H api_key=" + KEY}, {})
        self.assertNotIn(KEY, card.summary)
        self.assertIn("[REDACTED]", card.summary)

    def test_generic_fallback_for_unknown_tool(self):
        card = render_tool_card(
            [_presenter("shell")], {"tool_name": "never_registered"}, {}
        )
        self.assertEqual(card.icon, "tool")
        self.assertIn("never_registered", card.summary)

    def test_render_uses_winner_not_plugin_impostor(self):
        core = _presenter("shell", origin=CORE, icon="terminal",
                          summary_fields=("command",))
        plugin = _presenter("shell", origin=PLUGIN, icon="evil",
                            summary_fields=("command",))
        card = render_tool_card(
            [plugin, core], {"tool_name": "shell", "command": "pwd"}, {}
        )
        self.assertEqual(card.icon, "terminal")
        self.assertEqual(merge_presenters([plugin, core]), (core,))

    def test_presenter_roundtrip_and_validation(self):
        spec = _presenter(summary_fields=("command",), metadata_fields=("duration_ms",))
        self.assertEqual(PresenterDescriptor.from_dict(spec.to_dict()), spec)
        self.assertEqual(validate_presenter(spec), ())
        bad = PresenterDescriptor(
            tool_name="", icon="x/y", summary_fields=("../x",),
            expanded_fields=(), metadata_fields=(), origin=CORE, version=1,
        )
        self.assertTrue(validate_presenter(bad))


class TestPluginContracts(unittest.TestCase):
    """D4.11: bundled manager is protected; extensions need approval."""

    def test_bundled_plugin_manager_is_protected(self):
        manager = make_plugin(
            "plugin-manager", "Plugin Manager", origin=BUNDLE,
            requires_approval=False, capabilities=("ui", "tools"),
        )
        self.assertTrue(manager.is_protected)
        self.assertTrue(can_activate_plugin(manager))

    def test_agent_use_requires_approval_fail_closed(self):
        extension = _plugin(requires_approval=True)
        self.assertFalse(can_activate_plugin(extension))
        self.assertFalse(can_activate_plugin(extension, approved=False))
        self.assertTrue(can_activate_plugin(extension, approved=True))

    def test_disabled_plugin_cannot_activate(self):
        extension = with_plugin_enabled(
            _plugin(requires_approval=False), False
        )
        self.assertFalse(can_activate_plugin(extension, approved=True))

    def test_unknown_origin_cannot_activate(self):
        extension = make_plugin("x", "X", origin="mystery", requires_approval=False)
        self.assertFalse(can_activate_plugin(extension, approved=True))

    def test_unknown_capability_fails_closed(self):
        with self.assertRaises(ContractValidationError):
            _plugin(capabilities=("ui", "telepathy"))

    def test_resource_paths_contained(self):
        with self.assertRaises(ContractValidationError):
            _plugin(resource_paths=("../../etc/passwd",))
        plugin = _plugin(resource_paths=("plugins/ext/ui.js",))
        self.assertEqual(plugin.resource_paths, ("plugins/ext/ui.js",))
        self.assertEqual(validate_plugin(plugin), ())

    def test_protected_core_cannot_be_disabled(self):
        manager = make_plugin(
            "plugin-manager", "Plugin Manager", origin=BUNDLE,
            requires_approval=False,
        )
        composition = compose_layers([make_layer(BUNDLE, "base", plugins=(manager,))])
        with self.assertRaises(ContractValidationError):
            set_plugin_enabled(composition, "plugin-manager", False)

    def test_plugin_roundtrip(self):
        plugin = _plugin(requires_approval=True, capabilities=("ui",))
        self.assertEqual(PluginDescriptor.from_dict(plugin.to_dict()), plugin)


class TestComposition(unittest.TestCase):
    """Layered composition: deterministic, protected-core-first, fail closed."""

    def test_protected_core_wins_over_plugin_provider(self):
        core = _provider("local-llm", "http://127.0.0.1:1/v1", origin=CORE)
        plugin = _provider("local-llm", "http://evil.example/v1", origin=PLUGIN)
        composition = compose_layers([
            make_layer(CORE, "core", providers=(core,)),
            make_layer(PLUGIN, "plug", providers=(plugin,)),
        ])
        self.assertEqual(composition.provider("local-llm").base_url,
                         "http://127.0.0.1:1/v1")

    def test_bundle_presenter_wins_over_plugin(self):
        bundle = _presenter("shell", origin=BUNDLE, icon="terminal")
        plugin = _presenter("shell", origin=PLUGIN, icon="evil")
        composition = compose_layers([
            make_layer(PLUGIN, "plug", presenters=(plugin,)),
            make_layer(BUNDLE, "bundle", presenters=(bundle,)),
        ])
        self.assertEqual(composition.presenter("shell").icon, "terminal")

    def test_merge_is_independent_of_input_order(self):
        core = _provider("shared", "http://127.0.0.1:1/v1", origin=CORE)
        plugin = _provider("shared", "http://evil.example/v1", origin=PLUGIN)
        extra = _provider("extra", "https://x.example/v1", origin=USER)
        providers = [plugin, extra, core]
        self.assertEqual(merge_providers(providers),
                         merge_providers(list(reversed(providers))))
        a = compose_layers([
            make_layer(PLUGIN, "p", providers=(plugin, extra)),
            make_layer(CORE, "c", providers=(core,)),
        ])
        b = compose_layers([
            make_layer(CORE, "c", providers=(core,)),
            make_layer(PLUGIN, "p", providers=(plugin, extra)),
        ])
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_user_can_override_plugin_but_not_bundle(self):
        plugin = _provider("p", "http://plugin/v1", origin=PLUGIN)
        user = _provider("p", "http://user/v1", origin=USER)
        composition = compose_layers([
            make_layer(PLUGIN, "p", providers=(plugin,)),
            make_layer(USER, "u", providers=(user,)),
        ])
        self.assertEqual(composition.provider("p").base_url, "http://user/v1")
        bundle = _provider("p", "http://bundle/v1", origin=BUNDLE)
        composition = compose_layers([
            make_layer(BUNDLE, "b", providers=(bundle,)),
            make_layer(USER, "u", providers=(user,)),
        ])
        self.assertEqual(composition.provider("p").base_url, "http://bundle/v1")

    def test_disabled_and_unknown_layers_contribute_nothing(self):
        core = _provider("p", "http://core/v1", origin=CORE)
        composition = compose_layers([
            make_layer(PLUGIN, "off", enabled=False, providers=(_provider(
                "p", "http://off/v1", origin=PLUGIN),)),
            make_layer("mystery", "unknown", providers=(_provider(
                "p", "http://unknown/v1"),)),
            make_layer(CORE, "c", providers=(core,)),
        ])
        self.assertEqual([p.name for p in composition.providers], ["p"])
        self.assertEqual(composition.provider("p").base_url, "http://core/v1")

    def test_from_dict_reapplies_protected_precedence(self):
        core = _provider("p", "http://core/v1", origin=CORE)
        plugin = _provider("p", "http://evil/v1", origin=PLUGIN)
        composition = compose_layers([
            make_layer(CORE, "c", providers=(core,)),
            make_layer(PLUGIN, "p", providers=(plugin,)),
        ])
        payload = composition.to_dict()
        # An attacker appends a plugin-origin override for the same key;
        # re-merging on load must still select the protected core row.
        forged = dict(payload["providers"][0])
        forged["base_url"] = "http://evil/v1"
        forged["origin"] = "plugin"
        payload["providers"].append(forged)
        rebuilt = cc.Composition.from_dict(payload)
        self.assertEqual(rebuilt.provider("p").base_url, "http://core/v1")

    def test_missing_lookups_return_none_and_validation_is_clean(self):
        composition = compose_layers([
            make_layer(CORE, "c", providers=(_provider(),),
                       presenters=(_presenter(),),
                       plugins=(make_plugin(
                           "plugin-manager", "Plugin Manager", origin=BUNDLE,
                           requires_approval=False),)),
        ])
        self.assertIsNone(composition.provider("missing"))
        self.assertIsNone(composition.presenter("missing"))
        self.assertIsNone(composition.plugin("missing"))
        self.assertEqual(validate_composition(composition), ())
        self.assertNotIn("sk-", json.dumps(composition.to_public_dict()))

    def test_protected_origins_declared(self):
        self.assertEqual(set(PROTECTED_ORIGINS), {CORE, BUNDLE})
        self.assertNotIn(PLUGIN, PROTECTED_ORIGINS)
        self.assertEqual(LayerOrigin.CORE.precedence < LayerOrigin.PLUGIN.precedence, True)


class TestFailClosedValidation(unittest.TestCase):
    """Every malformed or unknown descriptor is rejected, not guessed."""

    def test_empty_identifiers_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_provider("", base_url="https://x/v1")
        with self.assertRaises(ContractValidationError):
            _presenter("")
        with self.assertRaises(ContractValidationError):
            make_plugin("", "X", origin=PLUGIN)

    def test_bad_icons_and_field_names_rejected(self):
        with self.assertRaises(ContractValidationError):
            _presenter(icon="../outside")
        with self.assertRaises(ContractValidationError):
            _presenter(expanded_fields=("bad field",))

    def test_purity_of_module(self):
        path = Path(__file__).resolve().parents[1] / "src" / "keel" / "composition_contracts.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = {"__future__", "json", "re", "dataclasses", "enum",
                   "typing", "urllib", "ipaddress"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported - allowed, imported - allowed)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                self.assertNotIn(name, {"open", "system", "popen", "spawn"})


if __name__ == "__main__":
    unittest.main()

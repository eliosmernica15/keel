"""Permanent contract-regression specs for the D1.x plugin architecture.

Groups (one or more tests per owned registry ID):
  D1.1  every part is a plugin with a typed descriptor; safety core protected
  D1.4  deterministic layered composition, patch semantics, core precedence
  D1.5  --dump-config: exact boot tree, provenance on every row, no secrets
  D1.10 desktop shell descriptor: completeness and fail-closed validation
  D1.12 core package map: six context service keys with responsibilities

These specs import only ``keel.plugin_contracts``.  They never load, import or
execute a plugin and never touch the live runtime.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re

import pytest

import keel.plugin_contracts as pc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _bundle(rows=None, name="core-bundle"):
    return pc.Bundle(name=name, rows=tuple(rows or (
        pc.row("llm", source=name, config={"provider": "local"}),
        pc.row("tools", source=name, config={"guarded": True}),
        pc.row("sessions", source=name, config={"backend": "jsonl"}),
        pc.row("approval_broker", source=name, protected=True,
               config={"timeout_s": 60}),
        pc.row("agent_loop", source=name, config={"max_turns": 8}),
        pc.row("system_prompt", source=name, config={"sections": []}),
        pc.row("agents", source=name, config={"registry": "live"}),
        pc.row("permission_core", source=name, protected=True,
               config={"mode": "enforce"}),
        pc.row("safety_core", source=name, protected=True,
               config={"injection_guard": True}),
    )))


def _doc(layer, source, *patches):
    return pc.PatchDocument(layer=layer, source=source, patches=tuple(patches))


def _tree_lines(text):
    return [line for line in text.splitlines() if line.startswith("- id=")]


# ---------------------------------------------------------------------------
# D1.1 -- typed part descriptors, single registration API, protected core
# ---------------------------------------------------------------------------


def test_every_core_part_is_a_typed_plugin_descriptor():
    parts = pc.core_parts()
    assert len(parts) == 9
    assert all(isinstance(p, pc.PluginPart) for p in parts)
    kinds = {p.kind for p in parts}
    assert {pc.PartKind.MODEL_ADAPTER, pc.PartKind.TOOL_REGISTRY,
            pc.PartKind.SESSION_LOG, pc.PartKind.APPROVAL_BROKER,
            pc.PartKind.AGENT_LOOP, pc.PartKind.PERMISSION_CORE,
            pc.PartKind.SAFETY_CORE} <= kinds
    by_id = {p.id: p for p in parts}
    assert {p.kind for p in parts if not p.protected} >= {
        pc.PartKind.MODEL_ADAPTER, pc.PartKind.TOOL_REGISTRY,
        pc.PartKind.SESSION_LOG, pc.PartKind.AGENT_LOOP}
    assert by_id["approval_broker"].kind is pc.PartKind.APPROVAL_BROKER
    assert all(p.implementation and p.responsibility for p in parts)
    assert all(isinstance(p.implementation, str) for p in parts)  # never imported


def test_permission_and_safety_core_are_protected_non_replaceable():
    protected = {p.id: p for p in pc.core_parts() if p.protected}
    assert {"permission_core", "safety_core", "approval_broker"} <= set(protected)
    assert pc.PROTECTED_CORE_IDS == tuple(protected)
    for part in protected.values():
        assert part.tier is pc.ServiceTier.TIER_2_SAFETY
        assert part.replaceable is False
    registry = pc.default_registry()
    for part_id in protected:
        assert registry.is_protected(part_id)
        with pytest.raises(pc.ProtectedCoreOverride):
            registry.assert_replaceable(part_id)


def test_same_registration_api_for_core_and_extensions():
    registry = pc.default_registry()
    extension = pc.PluginPart(
        id="my_adapter", kind=pc.PartKind.MODEL_ADAPTER,
        implementation="my_pkg.adapters:Custom", tier=pc.ServiceTier.EXTENSION,
        responsibility="Drop-in model adapter")
    assert registry.register(extension) is extension
    assert registry.part("my_adapter") is extension
    assert registry.part("llm").kind is pc.PartKind.MODEL_ADAPTER
    with pytest.raises(pc.PartDescriptorError):
        registry.register(extension)


def test_part_descriptor_validation_and_round_trip():
    with pytest.raises(pc.PartDescriptorError):
        pc.PluginPart(id="", kind=pc.PartKind.TOOL_REGISTRY,
                      implementation="a:b")
    with pytest.raises(pc.PartDescriptorError):
        pc.PluginPart(id="x", kind=pc.PartKind.TOOL_REGISTRY,
                      implementation="import os; os.system('rm')")
    with pytest.raises(pc.PartDescriptorError):  # protected but replaceable
        pc.PluginPart(id="x", kind=pc.PartKind.SAFETY_CORE,
                      implementation="a:b", protected=True, replaceable=True)
    with pytest.raises(pc.PartDescriptorError):  # tier 2 but not protected
        pc.PluginPart(id="x", kind=pc.PartKind.SAFETY_CORE,
                      implementation="a:b", tier=pc.ServiceTier.TIER_2_SAFETY)
    original = pc.core_parts()[0]
    restored = pc.PluginPart.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
    assert original.service_key == original.id


# ---------------------------------------------------------------------------
# D1.4 -- layering, deterministic merge, patches, protected precedence
# ---------------------------------------------------------------------------


def test_layer_order_is_bundles_then_profile_home_project_patch():
    docs = pc.ordered_layer_docs(
        [pc.Bundle("b1", ()), pc.Bundle("b2", ())],
        profile=_doc(pc.Layer.PROFILE, "profile:web"),
        home=_doc(pc.Layer.HOME, "home"),
        project=_doc(pc.Layer.PROJECT, "project"),
        overlays=[_doc(pc.Layer.PATCH, "--patch:a.yml"),
                  _doc(pc.Layer.PATCH, "--patch:b.yml")])
    assert [(layer.value, source) for layer, source, _ in docs] == [
        ("bundle", "b1"), ("bundle", "b2"), ("profile", "profile:web"),
        ("home", "home"), ("project", "project"),
        ("patch", "--patch:a.yml"), ("patch", "--patch:b.yml")]


def test_later_layers_win_on_config_and_provenance_but_keep_position():
    comp = pc.compose([_bundle()],
                      profile=_doc(pc.Layer.PROFILE, "profile:web",
                                   pc.Patch(pc.PatchAction.REPLACE, "llm",
                                            source="profile:web",
                                            config={"provider": "remote"})))
    assert comp.ids() == pc.CORE_PART_IDS
    assert comp.row("llm").config == {"provider": "remote"}
    assert comp.row("llm").provenance == {
        "layer": "profile", "source": "profile:web"}
    assert comp.row("tools").provenance == {
        "layer": "bundle", "source": "core-bundle"}
    assert comp.applied_layers[0] == "bundle:core-bundle"
    assert comp.applied_layers[1] == "profile:profile:web"


def test_composition_is_deterministic_and_fingerprint_stable():
    args = ([_bundle()],)
    kwargs = {"profile": _doc(pc.Layer.PROFILE, "profile:web",
                              pc.Patch(pc.PatchAction.REPLACE, "llm",
                                       source="profile:web",
                                       config={"provider": "x"})),
              "overlays": [_doc(pc.Layer.PATCH, "--patch:one",
                                pc.Patch(pc.PatchAction.INSERT, "extra",
                                         source="--patch:one",
                                         config={"enabled": True}))]}
    a = pc.compose(*args, **kwargs)
    b = pc.compose(*args, **kwargs)
    assert a == b
    assert a.fingerprint == b.fingerprint == pc.content_hash(
        [r.to_dict() for r in a.rows])
    assert a.ids()[-1] == "extra"


def test_protected_core_cannot_be_replaced_by_any_later_layer():
    for layer, source in ((pc.Layer.PROFILE, "profile:web"),
                          (pc.Layer.HOME, "home"),
                          (pc.Layer.PROJECT, "project"),
                          (pc.Layer.PATCH, "--patch:x.yml")):
        for part_id in ("permission_core", "safety_core", "approval_broker"):
            patch = pc.Patch(pc.PatchAction.REPLACE, part_id, source=source,
                             config={"mode": "off"})
            kwargs = {_kw(layer): _doc(layer, source, patch)}
            if layer is pc.Layer.PATCH:
                kwargs["overlays"] = [kwargs.pop("overlays")]
            with pytest.raises(pc.ProtectedCoreOverride):
                pc.compose([_bundle()], **kwargs)


def _kw(layer):
    return {pc.Layer.PROFILE: "profile", pc.Layer.HOME: "home",
            pc.Layer.PROJECT: "project", pc.Layer.PATCH: "overlays"}[layer]


def test_protected_core_cannot_be_disabled_or_inserted_over():
    with pytest.raises(pc.ProtectedCoreOverride):
        pc.compose([_bundle()], profile=_doc(
            pc.Layer.PROFILE, "profile:web",
            pc.Patch(pc.PatchAction.DISABLE, "safety_core",
                     source="profile:web")))
    with pytest.raises(pc.ProtectedCoreOverride):
        pc.compose([], profile=_doc(
            pc.Layer.PROFILE, "profile:web",
            pc.Patch(pc.PatchAction.INSERT, "permission_core",
                     source="profile:web", config={})))


def test_protected_core_restated_identically_is_a_noop():
    base = pc.row("safety_core", source="core-bundle", protected=True,
                  config={"injection_guard": True})
    comp = pc.compose([pc.Bundle("core-bundle", (base,))],
                      profile=_doc(pc.Layer.PROFILE, "profile:web",
                                   pc.Patch(pc.PatchAction.REPLACE,
                                            "safety_core", source="profile:web",
                                            config={"injection_guard": True})))
    assert comp.row("safety_core").provenance == {
        "layer": "bundle", "source": "core-bundle"}


def test_patch_replace_insert_disable_and_preset_plugin_list():
    preset = pc.row("preset:web", source="core-bundle", kind=pc.RowKind.PRESET,
                    config={"plugins": ["llm", "tools"]})
    comp = pc.compose([pc.Bundle("core-bundle", (preset,))],
        profile=_doc(pc.Layer.PROFILE, "profile:web",
            pc.Patch(pc.PatchAction.PRESET, "preset:web", source="profile:web",
                     plugin_list_op=pc.PluginListOp.ADD,
                     plugin_list=("sessions", "sessions")),
            pc.Patch(pc.PatchAction.INSERT, "extra_tool", source="profile:web",
                     config={"timeout": 5}),
            pc.Patch(pc.PatchAction.DISABLE, "extra_tool",
                     source="profile:web")),
        overlays=[_doc(pc.Layer.PATCH, "--patch:final",
            pc.Patch(pc.PatchAction.PRESET, "preset:web",
                     source="--patch:final",
                     plugin_list_op=pc.PluginListOp.REMOVE,
                     plugin_list=("tools",)))])
    assert comp.row("preset:web").config["plugins"] == ["llm", "sessions"]
    assert comp.row("extra_tool").enabled is False
    assert comp.row("extra_tool").provenance == {
        "layer": "profile", "source": "profile:web"}


def test_preset_replace_operation_and_bad_patch_targets():
    preset = pc.row("preset:x", source="core-bundle", kind=pc.RowKind.PRESET,
                    config={"plugins": ["a"]})
    comp = pc.compose([pc.Bundle("b", (preset,))], home=_doc(
        pc.Layer.HOME, "home",
        pc.Patch(pc.PatchAction.PRESET, "preset:x", source="home",
                 plugin_list_op=pc.PluginListOp.REPLACE,
                 plugin_list=("b", "c"))))
    assert comp.row("preset:x").config["plugins"] == ["b", "c"]
    with pytest.raises(pc.PatchError):
        pc.compose([_bundle()], project=_doc(pc.Layer.PROJECT, "project",
            pc.Patch(pc.PatchAction.REPLACE, "missing", source="project")))
    with pytest.raises(pc.PatchError):
        pc.compose([_bundle()], project=_doc(pc.Layer.PROJECT, "project",
            pc.Patch(pc.PatchAction.INSERT, "llm", source="project")))
    with pytest.raises(pc.PatchError):
        pc.compose([_bundle()], project=_doc(pc.Layer.PROJECT, "project",
            pc.Patch(pc.PatchAction.PRESET, "llm", source="project")))
    with pytest.raises(pc.CompositionError):
        pc.compose([], profile=pc.PatchDocument(pc.Layer.BUNDLE, "bad"))


def test_composition_rows_and_config_are_not_aliases():
    original = pc.row("llm", source="b", config={"nested": {"x": 1}})
    comp = pc.compose([pc.Bundle("b", (original,))])
    comp.row("llm").config["nested"]["x"] = 99
    assert original.config["nested"]["x"] == 1
    copied = pc.Composition.from_dict if hasattr(pc.Composition, "from_dict") else None
    assert copied is None  # composition is built only through compose()


# ---------------------------------------------------------------------------
# D1.5 -- dump-config: exact tree, provenance, no secrets
# ---------------------------------------------------------------------------


def test_dump_config_prints_exact_boot_tree_with_provenance():
    comp = pc.compose([_bundle()], profile=_doc(
        pc.Layer.PROFILE, "profile:web",
        pc.Patch(pc.PatchAction.REPLACE, "llm", source="profile:web",
                 config={"provider": "remote"})))
    text = pc.dump_config(comp)
    lines = _tree_lines(text)
    assert len(lines) == len(comp.rows)
    for line, item in zip(lines, comp.rows):
        assert f"id={item.id}" in line
        assert f"kind={item.kind.value}" in line
        assert f"plugin={item.plugin_id}" in line
        assert f"[layer={item.layer.value} source={item.source}]" in line
    assert "fingerprint: " + comp.fingerprint in text
    assert "protected-core: " in text
    assert re.search(r"id=permission_core .*protected=true", text)


def test_dump_rows_are_the_composition_with_redaction_and_layer_field():
    comp = pc.compose([_bundle([pc.row("llm", source="b", config={
        "api_key": "sk-SUPERSECRET0123456789", "provider": "local"})])])
    rows = pc.dump_config_rows(comp)
    assert [r["id"] for r in rows] == list(comp.ids())
    assert all({"source_layer", "source", "config"} <= set(r) for r in rows)
    assert rows[0]["config"] == {"api_key": pc.REDACTED, "provider": "local"}
    assert "sk-SUPERSECRET0123456789" not in json.dumps(rows)


def test_no_secret_values_in_dump_known_and_pattern_based():
    secret = "sk-LIVEKEY-abcdefghijklmnop"
    comp = pc.compose([_bundle([
        pc.row("llm", source="b", config={
            "api_key": secret,
            "nested": {"auth_token": "ghp_abcdefghijklmnopqrstuvwxyz"},
            "provider": "local"}),
        pc.row("tools", source="b", config={
            "headers": {"Authorization": "Bearer abcdefghijklmnop"}}),
    ])])
    text = pc.dump_config(comp)
    assert secret not in text
    assert "abcdefghijklmnopqrstuvwxyz" not in text
    assert "Bearer abcdefghijklmnop" not in text
    assert pc.REDACTED in text
    assert pc.find_secret_patterns(text) == ()
    pc.assert_no_secrets(text, secrets=(secret, "ghp_abcdefghijklmnopqrstuvwxyz"))
    with pytest.raises(pc.SecretLeakError):
        pc.assert_no_secrets("token=sk-LIVEKEY-abcdefghijklmnop")
    with pytest.raises(pc.SecretLeakError):
        pc.assert_no_secrets("all good", secrets=("good",))


def test_redaction_is_recursive_and_does_not_mutate_source():
    source = {"password": "hunter2",
              "list": [{"client_secret": "s3cr3t"}, "plain"],
              "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----\nxyz"}
    redacted = pc.redact_config(source)
    assert redacted["password"] == pc.REDACTED
    assert redacted["list"][0]["client_secret"] == pc.REDACTED
    assert redacted["list"][1] == "plain"
    assert redacted["private_key_pem"] == pc.REDACTED
    assert source["password"] == "hunter2"
    assert source["list"][0]["client_secret"] == "s3cr3t"


def test_dump_config_json_matches_text_view_and_is_secret_free():
    comp = pc.compose([_bundle()], overlays=[_doc(
        pc.Layer.PATCH, "--patch:extra",
        pc.Patch(pc.PatchAction.INSERT, "extra", source="--patch:extra",
                 config={"api_key": "sk-abcdefghijklmnop"}))])
    payload = json.loads(pc.dump_config_json(comp))
    assert payload["fingerprint"] == comp.fingerprint
    assert payload["protected_core"] == list(comp.protected_ids)
    assert [r["id"] for r in payload["rows"]] == list(comp.ids())
    assert "sk-abcdefghijklmnop" not in pc.dump_config_json(comp)
    assert payload["rows"][-1]["config"]["api_key"] == pc.REDACTED


# ---------------------------------------------------------------------------
# D1.10 -- desktop shell descriptor completeness
# ---------------------------------------------------------------------------


def test_canonical_desktop_descriptor_is_complete():
    descriptor = pc.desktop_shell_descriptor()
    assert descriptor.is_reserved_profile
    assert descriptor.profile == pc.RESERVED_DESKTOP_PROFILE
    assert descriptor.ui_owner == "electron_shell"
    assert descriptor.runtime_source == "signed_resources"
    assert descriptor.signed and not descriptor.repackaging_allowed
    assert descriptor.host_port == "os_assigned" and descriptor.host_port_value == 0
    assert descriptor.wait_for_boot_injections
    assert descriptor.activate_plugins_in_same_document
    assert tuple(descriptor.boot_sequence) == pc.BOOT_SEQUENCE
    assert set(descriptor.ipc_channels) == set(pc.IPC_CHANNELS)
    assert descriptor.shared_product_data
    assert all((descriptor.separate_plugin_packages,
                descriptor.separate_activation_state,
                descriptor.separate_lockfiles))
    assert descriptor.packaging == "descriptor_only"
    assert descriptor.validate() is descriptor
    restored = pc.DesktopShellDescriptor.from_dict(
        json.loads(json.dumps(descriptor.to_dict())))
    assert restored == descriptor


def test_boot_sequence_loads_assets_before_activating_plugins():
    assert pc.BOOT_SEQUENCE == (
        "load_packaged_web_assets", "start_private_desktop_host",
        "wait_for_boot_injections", "activate_client_plugins_same_document")
    assert set(pc.IPC_CHANNELS) == {c.value for c in pc.IpcChannel}


@pytest.mark.parametrize("changes", [
    {"profile": "web"},
    {"runtime_source": "local_build"},
    {"signed": False},
    {"repackaging_allowed": True},
    {"ui_owner": "web_view"},
    {"host_port_value": 9222},
    {"host_bind": "0.0.0.0"},
    {"boot_sequence": tuple(reversed(pc.BOOT_SEQUENCE))},
    {"wait_for_boot_injections": False},
    {"activate_plugins_in_same_document": False},
    {"ipc_channels": ("ready",)},
    {"fatal_error_screen": False},
    {"separate_lockfiles": False},
    {"packaging": "built_here"},
])
def test_incomplete_descriptors_fail_closed(changes):
    descriptor = dataclasses.replace(pc.desktop_shell_descriptor(), **changes)
    with pytest.raises(pc.DescriptorError):
        pc.assert_descriptor_complete(descriptor)


def test_descriptor_is_data_only_no_packaging_side_effects():
    data = pc.desktop_shell_descriptor().to_dict()
    assert isinstance(data, dict)
    assert not ({"subprocess", "spawn", "write", "bundle_bytes"} & set(data))
    assert data["packaging"] == "descriptor_only"
    assert copy.deepcopy(data) == data


# ---------------------------------------------------------------------------
# D1.12 -- core package map
# ---------------------------------------------------------------------------


def test_core_map_has_exactly_six_context_service_keys():
    assert pc.core_service_keys() == (
        "sessions", "system_prompt", "tools", "agents", "agent_loop", "llm")
    assert tuple(pc.core_package_map()) == pc.CORE_SERVICE_KEYS
    assert all(isinstance(s, pc.CoreService) for s in pc.core_package_map().values())


def test_every_core_service_has_responsibility_and_part_reference():
    registry = pc.default_registry()
    pc.assert_core_map_complete(registry)
    for key, service in pc.core_package_map().items():
        assert service.key == key
        assert service.context_exposed is True
        assert service.part_id in registry.ids()
        assert service.responsibility and service.package
        assert service.to_dict()["key"] == key


def test_tool_registry_service_is_marked_guarded():
    tools = pc.core_package_map()["tools"]
    assert tools.guarded is True
    assert "guarded" in tools.responsibility.lower()
    assert pc.core_package_map()["llm"].part_id == "llm"


def test_core_map_copy_cannot_mutate_canonical_and_validation_fails_closed():
    mapping = pc.core_package_map()
    mapping.clear()
    assert tuple(pc.core_package_map()) == pc.CORE_SERVICE_KEYS
    with pytest.raises(pc.PluginContractError):
        pc.assert_core_map_complete(pc.PluginRegistry())
    with pytest.raises(pc.PluginContractError):
        pc.CoreService("x", "missing", "pkg", "")
    with pytest.raises(pc.PluginContractError):
        pc.CoreService("", "x", "pkg", "responsibility")

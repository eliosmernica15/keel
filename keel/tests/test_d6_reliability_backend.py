"""Permanent contract-regression specs for the additive D6 reliability backend.

One or more tests per implemented D6 registry ID:
D6.1, D6.3, D6.4, D6.5, D6.6, D6.7, D6.8, D6.9, D6.10, D6.11, D6.12,
D6.13, D6.15, D6.16, D6.19, D6.22, D6.24, D6.25.

The specs are additive: they import only ``keel.d6_reliability_backend`` and do
not mutate the registry, the filesystem or any existing test.  Every check is
computed from the supplied data; failures are adversarial cases that must be
rejected by a typed ``KeelError`` subclass.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import keel.d6_reliability_backend as d6


# ---------------------------------------------------------------------------
# D6.1 -- public API change recorder / upgrade guide / monotonic schema
# ---------------------------------------------------------------------------


def test_api_change_recorder_checks_consumers_and_upgrade_note():
    recorder = d6.ApiChangeRecorder(known_consumers=["sdk-py", "sdk-ts"])
    breaking = d6.ApiChange(
        change_id="CHG-1", symbol="keel.run", kind=d6.ChangeKind.BREAKING,
        summary="run() now requires a resolved Spec",
        upgrade_note="Call resolve(request) before run().",
        consumers_updated=["sdk-py"],
    )
    recorder.record(breaking)
    result = recorder.validate()
    assert result.ok is False
    assert result.missing_consumers == {"CHG-1": ("sdk-ts",)}
    assert result.unrecorded_breaking == ()

    complete = d6.ApiChange(
        change_id="CHG-2", symbol="keel.config.load", kind=d6.ChangeKind.ADDITIVE,
        summary="new optional field", consumers_updated=["sdk-py", "sdk-ts"],
    )
    recorder.record(complete)
    assert recorder.validate().missing_consumers == {"CHG-1": ("sdk-ts",)}
    assert [c.change_id for c in recorder.breaking_changes()] == ["CHG-1"]

    fixed = d6.ApiChange(
        change_id="CHG-1", symbol="keel.run", kind=d6.ChangeKind.BREAKING,
        summary="run() now requires a resolved Spec",
        upgrade_note="Call resolve(request) before run().",
        consumers_updated=["sdk-py", "sdk-ts"],
    )
    clean = d6.ApiChangeRecorder(known_consumers=["sdk-py", "sdk-ts"])
    clean.record(fixed)
    clean.record(complete)
    assert clean.validate().ok is True

    with pytest.raises(d6.ApiStabilityError):
        d6.ApiChange(change_id="CHG-3", symbol="x", kind=d6.ChangeKind.BREAKING,
                     summary="no note")
    with pytest.raises(d6.ApiStabilityError):
        recorder.record(breaking)


def test_upgrade_guide_check_detects_unrecorded_breaking_changes():
    changes = [
        d6.ApiChange("CHG-A", "a", d6.ChangeKind.BREAKING, "a", "use b"),
        d6.ApiChange("CHG-B", "b", d6.ChangeKind.DEPRECATION, "b", "use c"),
        d6.ApiChange("CHG-C", "c", d6.ChangeKind.FIX, "c"),
    ]
    assert d6.check_upgrade_guide(changes, "CHG-A moved; CHG-B removed") == ()
    assert d6.check_upgrade_guide(changes, "# Upgrade\nCHG-A only") == ("CHG-B",)


def test_schema_version_is_positive_monotonic_and_literal():
    assert d6.SchemaVersion(1).next() == d6.SchemaVersion(2)
    with pytest.raises(d6.SchemaVersionError):
        d6.SchemaVersion(0)
    with pytest.raises(d6.SchemaVersionError):
        d6.assert_monotonic(d6.SchemaVersion(4), d6.SchemaVersion(4))
    with pytest.raises(d6.SchemaVersionError):
        d6.assert_monotonic(d6.SchemaVersion(5), d6.SchemaVersion(2))
    assert d6.scan_schema_version("SCHEMA_VERSION = 9\n") == 9
    with pytest.raises(d6.SchemaVersionError):
        d6.scan_schema_version("SCHEMA_VERSION = LATEST\n")
    with pytest.raises(d6.SchemaVersionError):
        d6.scan_schema_version("VERSION = 3\n")


# ---------------------------------------------------------------------------
# D6.3 -- typed events, exhaustive closed unions, documented default
# ---------------------------------------------------------------------------


def test_event_catalog_documents_modes_payloads_and_defaults():
    catalog = d6.EventCatalog()
    catalog.register(d6.EventSpec("request.start", d6.EventMode.REQUEST,
                                  ("session_id", "prompt"), d6.UnionStyle.CLOSED,
                                  "a new request entered the loop"))
    catalog.register(d6.EventSpec("response.done", d6.EventMode.RESPONSE,
                                  ("session_id", "text"), d6.UnionStyle.CLOSED,
                                  "the model finished a turn"))
    catalog.register(d6.EventSpec("telemetry", d6.EventMode.NOTIFICATION,
                                  ("name",), d6.UnionStyle.EXTENSIBLE,
                                  "a plugin notification", "ignore unknown plugin events"))
    assert catalog.validate().ok is True
    assert catalog.dispatch("request.start", {"session_id": "s1"}).missing_fields == ("prompt",)
    fallback = catalog.dispatch("plugin.custom", {"name": "x"})
    assert fallback.matched is False and fallback.used_default is True and fallback.ok is True

    strict = d6.EventCatalog()
    strict.register(d6.EventSpec("request.start", d6.EventMode.REQUEST,
                                 ("prompt",), d6.UnionStyle.CLOSED, "request"))
    with pytest.raises(d6.EventUnionError):
        strict.dispatch("unknown.event", {})
    with pytest.raises(d6.EventUnionError):
        d6.EventSpec("bad", d6.EventMode.REQUEST, ("p",), d6.UnionStyle.CLOSED,
                     "closed with default", "should be illegal")
    with pytest.raises(d6.EventUnionError):
        d6.EventSpec("bad", d6.EventMode.REQUEST, ("p",), d6.UnionStyle.EXTENSIBLE,
                     "extensible without default")


def test_closed_union_exhaustive_check_rejects_unknown_member():
    assert [d6.render_mode(m) for m in d6.EventMode] == ["->", "<-", "!!"]
    with pytest.raises(d6.EventUnionError):
        d6.assert_never("unexpected")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# D6.4 -- explicit resolve(request) -> Spec
# ---------------------------------------------------------------------------


def test_resolve_records_defaults_and_run_refuses_unresolved_request():
    spec = d6.resolve(d6.Request())
    assert spec.applied_defaults == ("model", "max_tokens", "temperature")
    assert spec.model == d6.DEFAULT_MODEL and spec.max_tokens == d6.DEFAULT_MAX_TOKENS
    assert json.loads(d6.run(spec)) == spec.to_dict()
    assert "applied_defaults" in d6.run(spec)
    specified = d6.resolve(d6.Request(model="m", max_tokens=8, temperature=0.5))
    assert specified.applied_defaults == ()
    with pytest.raises(d6.ResolutionError):
        d6.run(d6.Request())  # type: ignore[arg-type]
    with pytest.raises(d6.ResolutionError):
        d6.resolve(d6.Request(max_tokens=0))


def test_find_hidden_defaults_flags_or_fallback_inside_run():
    dirty = "def run(spec):\n    value = spec.model or 'fallback'\n    return value\n"
    findings = d6.find_hidden_defaults(dirty)
    assert findings and "hidden 'or' default" in findings[0]
    clean = "def run(spec):\n    return spec.model\n"
    assert d6.find_hidden_defaults(clean) == ()


# ---------------------------------------------------------------------------
# D6.5 -- plugin tunables are validated config, not magic numbers
# ---------------------------------------------------------------------------


def test_plugin_config_validates_missing_unknown_and_out_of_range():
    good = d6.validate_plugin_config({"timeout_ms": 1500, "max_retries": 2,
                                      "backoff_factor": 1.5})
    assert good.to_dict()["max_retries"] == 2
    with pytest.raises(d6.PluginConfigError):
        d6.validate_plugin_config({"timeout_ms": 1500})
    with pytest.raises(d6.PluginConfigError):
        d6.validate_plugin_config({"timeout_ms": 1500, "max_retries": 2,
                                   "backoff_factor": 1.5, "secret": "x"})
    with pytest.raises(d6.PluginConfigError):
        d6.validate_plugin_config({"timeout_ms": 999_999, "max_retries": 2,
                                   "backoff_factor": 1.5})


def test_plugin_lint_allowlist_and_magic_number_detection():
    source = ("TIMEOUT_MS = 2500\n"
              "MAX_RETRIES = 3\n"
              "delay_ms = 300\n")
    findings = d6.lint_plugin_source(source, "plugins/retry.py")
    assert [f.literal for f in findings] == ["300"]
    assert findings[0].line == 3
    with pytest.raises(d6.PluginConfigError):
        d6.assert_no_magic_numbers(source, "plugins/retry.py")
    assert d6.lint_plugin_source("MAX_PAYLOAD_BYTES = 4096\n", "plugins/a.py") == ()


# ---------------------------------------------------------------------------
# D6.6 -- misconfiguration fails loud at load
# ---------------------------------------------------------------------------


def test_missing_referent_aborts_load_with_known_names():
    registry = d6.ReferenceRegistry()
    registry.register("main-model", "gpt-x")
    with pytest.raises(d6.MisconfigurationError) as exc:
        d6.load_with_references({"model": "$ref:main-model",
                                 "nested": {"tools": ["$ref:missing-tool"]}}, registry)
    assert exc.value.details["name"] == "missing-tool"
    assert "main-model" in exc.value.details["known"]


def test_reference_load_resolves_nested_referents_and_rejects_duplicates():
    registry = d6.ReferenceRegistry()
    registry.register("tool", {"name": "fs"})
    loaded = d6.load_with_references({"a": {"b": ["$ref:tool", 7]}}, registry)
    assert loaded.resolved == {"a": {"b": [{"name": "fs"}, 7]}}
    assert loaded.skipped == ()
    with pytest.raises(d6.MisconfigurationError):
        registry.register("tool", "other")


# ---------------------------------------------------------------------------
# D6.7 -- opaque cross-boundary ids are branded NewTypes
# ---------------------------------------------------------------------------


def test_brand_id_rejects_empty_and_unknown_kind():
    assert d6.brand_id(d6.SessionId, "s-42") == "s-42"
    with pytest.raises(d6.TypedIdError):
        d6.brand_id(d6.SessionId, "")
    with pytest.raises(d6.TypedIdError):
        d6.brand_id(d6.SessionId, "has space")
    with pytest.raises(d6.TypedIdError):
        d6.brand_id(str, "s-42")  # type: ignore[arg-type]


def test_audit_id_annotations_flags_bare_str_ids():
    source = ("def handle(session_id: str, request_id: d6.RequestId):\n"
              "    return None\n")
    findings = d6.audit_id_annotations(source, "p.py")
    assert len(findings) == 1
    assert findings[0].parameter == "session_id" and findings[0].line == 1
    assert d6.audit_id_annotations(
        "def handle(session_id: d6.SessionId):\n    return None\n", "p.py") == ()


# ---------------------------------------------------------------------------
# D6.8 -- validate at boundaries, trust in-process values
# ---------------------------------------------------------------------------


def test_boundary_registry_validates_shape_and_fails_on_unknown_boundary():
    registry = d6.BoundaryRegistry()
    registry.register(d6.ValidatorSpec(d6.Boundary.PARSER_CONFIG,
                                       ("model", "max_tokens"),
                                       {"model": str, "max_tokens": int}))
    ok = registry.validate(d6.Boundary.PARSER_CONFIG,
                           {"model": "m", "max_tokens": 12})
    assert ok.ok is True and ok.trusted is False and len(ok.checked_fields) == 2
    with pytest.raises(d6.BoundaryError):
        registry.validate(d6.Boundary.PARSER_CONFIG, {"model": "m"})
    with pytest.raises(d6.BoundaryError):
        registry.validate(d6.Boundary.PARSER_CONFIG,
                          {"model": "m", "max_tokens": "12"})
    with pytest.raises(d6.BoundaryError):
        registry.validate(d6.Boundary.WIRE, {"model": "m"})


def test_in_process_values_must_be_explicitly_trusted():
    registry = d6.BoundaryRegistry()
    trusted = registry.validate(d6.Boundary.IN_PROCESS, d6.trust({"x": 1}))
    assert trusted.trusted is True and trusted.ok is True
    with pytest.raises(d6.BoundaryError):
        registry.validate(d6.Boundary.IN_PROCESS, {"x": 1})
    assert d6.EXTERNAL_BOUNDARIES == frozenset(b for b in d6.Boundary
                                               if b is not d6.Boundary.IN_PROCESS)


# ---------------------------------------------------------------------------
# D6.9 -- no new casts beyond a recorded, reasoned baseline
# ---------------------------------------------------------------------------


def test_cast_baseline_flags_new_unreasoned_casts():
    source = ("from typing import Any, cast\n"
              "a = cast(Any, raw)  # reason: legacy wire payload\n"
              "b = cast(object, raw)\n")
    observed = d6.scan_cast_calls(source, "m.py")
    assert [(r.line, r.target) for r in observed] == [(2, "Any"), (3, "object")]
    assert observed[0].reason == "legacy wire payload"
    baseline = d6.CastBaseline([observed[0]])
    report = baseline.check(observed)
    assert report.ok is False
    assert report.new_casts == ("m.py:3:object",)
    assert report.missing_reasons == ("m.py:3:object",)
    with pytest.raises(d6.CastBaselineError):
        baseline.add(d6.CastRecord("m.py", 9, "Any", ""))
    baseline.add(d6.CastRecord("m.py", 3, "object", "external plugin boundary"))
    assert baseline.check(observed).ok is True


# ---------------------------------------------------------------------------
# D6.10 -- source plane vs artifact plane
# ---------------------------------------------------------------------------


def test_source_only_gate_rejects_artifact_imports():
    assert d6.classify_path("src/keel/runner.py") is d6.Plane.SOURCE
    assert d6.classify_path("dist/keel/runner.pyc") is d6.Plane.ARTIFACT
    assert d6.classify_path("C:/repo/node_modules/pkg/index.js") is d6.Plane.ARTIFACT
    gate = d6.ImportGate([d6.GateDeclaration("unit-tests", False)])
    assert gate.resolve("unit-tests", "keel.runner", "src/keel/runner.py").plane is d6.Plane.SOURCE
    with pytest.raises(d6.PlaneError):
        gate.resolve("unit-tests", "keel.runner", "build/keel/runner.py")
    with pytest.raises(d6.PlaneError):
        d6.assert_source_import("keel", "dist/keel/__init__.py")


def test_artifact_gate_requires_declared_dependency():
    with pytest.raises(d6.PlaneError):
        d6.GateDeclaration("smoke", True)
    gate = d6.ImportGate([d6.GateDeclaration("smoke", True, "build:wheel")])
    assert gate.resolve("smoke", "keel", "dist/keel/__init__.py").plane is d6.Plane.ARTIFACT
    assert gate.validate() == ()
    with pytest.raises(d6.PlaneError):
        gate.resolve("missing-gate", "keel", "src/keel/__init__.py")


# ---------------------------------------------------------------------------
# D6.11 -- typed errors and empty-except gate
# ---------------------------------------------------------------------------


def test_keel_error_hierarchy_codes_are_unique_and_structured():
    error = d6.UntrustedStateError("bad state", details={"state": "model"})
    assert error.code == "D6.11.UNTRUSTED_STATE"
    assert str(error) == "[D6.11.UNTRUSTED_STATE] bad state"
    assert error.to_dict() == {"type": "UntrustedStateError",
                               "code": "D6.11.UNTRUSTED_STATE",
                               "message": "bad state", "details": {"state": "model"}}
    codes = d6.all_error_codes()
    assert len(codes) >= 20 and all(code.startswith("D6.") for code in codes)
    assert all(cls.__mro__[1] is d6.KeelError or issubclass(cls, d6.KeelError)
               for cls in codes.values())


def test_untrusted_state_and_unknown_outcome_stop_dependent_work():
    with pytest.raises(d6.UntrustedStateError) as untrusted:
        d6.fail_on_untrusted("tool_json", "schema mismatch")
    assert untrusted.value.details["state"] == "tool_json"
    with pytest.raises(d6.UnknownOutcomeError) as unknown:
        d6.fail_on_unknown_outcome("provider.cancel")
    assert unknown.value.details["operation"] == "provider.cancel"


def test_except_gate_requires_named_error_and_reason():
    source = (
        "try:\n    work()\n"
        "except ValueError:  # expected ValueError: why: tool JSON is untrusted\n    pass\n"
        "except KeyError:  # expected KeyError: because the field is optional\n    ...\n"
        "except TypeError:\n    pass\n"
        "except:\n    pass\n"
    )
    findings = d6.audit_except_handlers(source, "p.py")
    assert [f.ok for f in findings] == [True, True, False, False]
    assert "comment_must_name_caught_error" in findings[2].reasons
    assert "comment_must_explain_why" in findings[2].reasons
    assert "bare_except_must_name_an_error" in findings[3].reasons
    with pytest.raises(d6.EmptyExceptError):
        d6.assert_handled_excepts(source, "p.py")
    assert d6.assert_handled_excepts(
        "try:\n    work()\nexcept ValueError:  # expected ValueError: why: known\n    pass\n",
        "ok.py") is None


# ---------------------------------------------------------------------------
# D6.12 -- docstrings and word budgets
# ---------------------------------------------------------------------------


def test_docstring_audit_reports_missing_args_returns_and_budget():
    source = ('"""Module docs."""\n'
              "def public(value: int) -> int:\n"
              '    """Return the value."""\n'
              "    return value\n")
    findings = d6.audit_docstrings(source, "m.py")
    problems = {f.problem for f in findings}
    assert "missing_args_section" in problems and "missing_returns_section" in problems
    documented = ('"""Module docs."""\n'
                  "def public(value: int) -> int:\n"
                  '    """Return the value.\n\n'
                  "    Args:\n        value: input.\n\n"
                  "    Returns:\n        The same value.\n    \"\"\"\n"
                  "    return value\n")
    assert d6.audit_docstrings(documented, "m.py") == ()
    assert d6.assert_documented(documented, "m.py") is None
    long_doc = '"""' + " ".join(["word"] * 130) + '"""\n'
    assert any("word_budget_exceeded" in f.problem
               for f in d6.audit_docstrings(long_doc, "long.py"))
    with pytest.raises(d6.DocstringError):
        d6.assert_documented("def public():\n    pass\n", "bad.py")


def test_restating_comments_are_flagged():
    assert d6.find_restating_comments("x = 1  # x = 1\n", "m.py")[0].problem \
        == "restating_comment"
    assert d6.find_restating_comments("# Set the value.\nx = 1\n", "m.py") == ()


# ---------------------------------------------------------------------------
# D6.13 -- docs accompany code
# ---------------------------------------------------------------------------


def test_doc_coverage_requires_docs_for_matching_changes():
    checker = d6.DocCoverageChecker()
    changed = ("C:/repo/keel/src/keel/api.py",)
    missing = checker.check(changed, ())
    assert missing.ok is False
    assert "public_python_source" in missing.missing
    covered = checker.check(changed, ("README.md",))
    assert covered.ok is True and covered.covered_rules == ("public_python_source",)

    checker.add(d6.DocRule("public_api", "*/keel/src/keel/api_*.py",
                           ("UPGRADE.md",), "externally visible API change"))
    both = checker.check(("C:/repo/keel/src/keel/api_run.py",), ("README.md",))
    assert both.missing == {"public_api": ("UPGRADE.md",)}
    assert checker.check(("C:/repo/keel/src/keel/api_run.py",),
                         ("README.md", "keel/UPGRADE.md")).ok is True
    assert checker.check(("C:/repo/other/file.txt",), ()).ok is True
    with pytest.raises(d6.DocSyncError):
        d6.assert_docs_in_sync(changed, ())


# ---------------------------------------------------------------------------
# D6.15 -- keyless recorded-session snapshots
# ---------------------------------------------------------------------------


def test_snapshot_registry_replays_exactly():
    fixture = d6.SnapshotFixture("snap-1", ("session.created", "turn.done"),
                                 {"text": "hello", "items": [1, 2]})
    registry = d6.SnapshotRegistry()
    registry.register(fixture)
    assert fixture.digest == d6.SnapshotFixture(
        "snap-1", ("session.created", "turn.done"),
        {"text": "hello", "items": [1, 2]}).digest
    exact = registry.replay("snap-1", fixture.input_events, fixture.expected_output)
    assert exact.ok is True and exact.events_match is True and exact.output_match is True
    drifted = registry.replay("snap-1", fixture.input_events, {"text": "changed"})
    assert drifted.ok is False and drifted.output_match is False
    assert registry.replay_all({"snap-1": (fixture.input_events,
                                          fixture.expected_output)})[0].ok is True
    with pytest.raises(d6.SnapshotError):
        registry.replay("missing", (), {})
    with pytest.raises(d6.SnapshotError):
        registry.register(fixture)


def test_keyless_fixtures_reject_volatile_keys_values_and_platforms():
    for payload in ({"timestamp": 1}, {"created_at": "x"}, {"session_id": "s"},
                    {"nested": {"uuid": "x"}}, ["2026-01-02T03:04:05Z"],
                    "123e4567-e89b-12d3-a456-426614174000",
                    "C:\\Users\\admin\\repo", "/home/admin/repo"):
        with pytest.raises(d6.SnapshotError):
            d6.assert_keyless(payload)
    assert d6.assert_keyless({"text": "ok", "items": ["a"]}) is None
    with pytest.raises(d6.SnapshotError):
        d6.SnapshotFixture("p", ("e",), {}, platforms=("linux",))
    with pytest.raises(d6.SnapshotError):
        d6.SnapshotFixture("v", ("e",), {"meta": {"run_id": "r1"}})
    with pytest.raises(d6.SnapshotError):
        d6.assert_snapshot_updated(True, [])
    assert d6.assert_snapshot_updated(True, ["snap-1"]) is None


def test_normalizers_are_banned_in_fixture_code():
    with pytest.raises(d6.SnapshotError):
        d6.assert_no_normalizers(
            "def normalize_output(value):\n    return value\n", "fixture.py")
    assert d6.assert_no_normalizers("def replay(value):\n    return value\n", "fixture.py") is None


# ---------------------------------------------------------------------------
# D6.16 -- both SDKs project the loop
# ---------------------------------------------------------------------------


def _projection() -> d6.SdkProjection:
    events = {"session.created": "SessionCreated", "turn.done": "TurnDone"}
    lifecycle = {"session.closed": "SessionClosed"}
    sdk = dict(events, **lifecycle)
    return d6.SdkProjection(events, tuple(lifecycle), dict(sdk), dict(sdk))


def test_sdk_projection_detects_missing_mismatched_and_stale_expectations():
    projection = _projection()
    assert d6.validate_projection(projection).ok is True
    d6.assert_projection_in_sync(projection)

    missing_python = d6.SdkProjection(projection.event_map, projection.lifecycle,
                                      {"turn.done": "TurnDone"}, dict(projection.typescript_events))
    report = d6.validate_projection(missing_python)
    assert "session.created" in report.missing["python"]

    mismatch = d6.SdkProjection(projection.event_map, projection.lifecycle,
                                dict(projection.python_events),
                                dict(projection.typescript_events, **{"turn.done": "OldName"}))
    assert d6.validate_projection(mismatch).mismatched == ("turn.done",)

    stale = d6.SdkProjection(projection.event_map, projection.lifecycle,
                             dict(projection.python_events, **{"legacy": "Legacy"}),
                             dict(projection.typescript_events))
    assert d6.validate_projection(stale).stale == ("legacy",)
    with pytest.raises(d6.SdkProjectionError):
        d6.assert_projection_in_sync(mismatch)


def test_sdk_projection_validator_registry_and_manifest():
    validator = d6.SdkProjectionValidator()
    validator.register("sdk-py", _projection())
    validator.register("sdk-ts", _projection())
    assert validator.names == ("sdk-py", "sdk-ts")
    assert all(r.ok for r in validator.validate_all().values())
    manifest = d6.projection_manifest(_projection())
    assert manifest["fingerprint"] == d6.projection_manifest(_projection())["fingerprint"]
    with pytest.raises(d6.SdkProjectionError):
        validator.register("sdk-py", _projection())


# ---------------------------------------------------------------------------
# D6.19 -- vendoring policy: pinned SHAs, manifest updates, logged patches
# ---------------------------------------------------------------------------


def _package() -> d6.VendoredPackage:
    patch_sha = hashlib.sha256(b"patched").hexdigest()
    return d6.VendoredPackage("libfoo", "a" * 40, "vendor/libfoo",
                              (d6.LocalPatch("SEC-1", patch_sha, "pin upstream fix"),))


def test_vendor_manifest_pins_shas_and_logs_local_patches():
    manifest = d6.VendorManifest()
    manifest.register(_package())
    assert manifest.validate() == ()
    assert manifest.check_tree_sha("libfoo", "a" * 40) is True
    assert manifest.check_tree_sha("libfoo", "patched") is True
    with pytest.raises(d6.VendorManifestError):
        manifest.check_tree_sha("libfoo", "b" * 40)
    with pytest.raises(d6.VendorManifestError):
        d6.VendoredPackage("bad", "not-a-sha", "vendor/bad")
    with pytest.raises(d6.VendorManifestError):
        d6.LocalPatch("p", "short", "reason")
    rendered = d6.render_vendor_manifest(manifest)
    assert '"upstream_sha":"' + "a" * 40 + '"' in rendered
    assert d6.render_vendor_manifest(manifest) == rendered


def test_vendor_changes_require_manifest_update():
    manifest = d6.VendorManifest()
    manifest.register(_package())
    assert manifest.changes_require_manifest_update(("src/keel/normal.py",)) == ()
    assert manifest.changes_require_manifest_update(("vendor/libfoo/core.py",)) == ("libfoo",)
    assert manifest.changes_require_manifest_update(
        ("vendor/libfoo/core.py", "vendor/manifest.json")) == ()


# ---------------------------------------------------------------------------
# D6.22 -- TODO marker urgency and release gate
# ---------------------------------------------------------------------------


def test_release_gate_fails_on_open_fixme():
    findings = d6.scan_markers(
        "# FIXME: release blocker\n# TODO: next sprint\n# XXX: someday\n", "m.py")
    assert [f.marker for f in findings] == [d6.MarkerUrgency.FIXME,
                                            d6.MarkerUrgency.TODO,
                                            d6.MarkerUrgency.XXX]
    blocking = d6.release_gate(findings)
    assert len(blocking) == 1 and blocking[0].line == 1
    with pytest.raises(d6.MarkerError) as exc:
        d6.assert_release_ready(findings)
    assert exc.value.code == "D6.22.OPEN_FIXME"
    assert d6.assert_release_ready(d6.release_gate(findings[1:])) is None


# ---------------------------------------------------------------------------
# D6.24 -- strict typing with narrow justified exceptions
# ---------------------------------------------------------------------------


def test_typing_audit_flags_untyped_public_functions():
    source = "def public(value):\n    return value\n"
    findings = d6.TypingAudit().audit(source, "m.py")
    assert {f.problem for f in findings} == {"missing_return_annotation",
                                             "missing_parameter_annotation"}
    with pytest.raises(d6.TypingAuditError):
        d6.TypingAudit().assert_strict(source, "m.py")
    justified = d6.TypingAudit([d6.JustifiedDynamic(
        "m.py", "public", "wire boundary returns untyped JSON today")])
    assert justified.audit(source, "m.py") == ()
    with pytest.raises(d6.TypingAuditError):
        d6.JustifiedDynamic("m.py", "public", "legacy")


# ---------------------------------------------------------------------------
# D6.25 -- top-level gate with per-gate invalid-case proof
# ---------------------------------------------------------------------------


def test_gate_registry_requires_each_gate_to_reject_its_invalid_case():
    registry = d6.GateRegistry()
    registry.register(d6.InvariantGate("structured-errors",
                                       lambda v: isinstance(v, d6.KeelError) and bool(v.code),
                                       d6.KeelError("x"), "plain string"))
    assert [p.ok for p in registry.probe_all()] == [True]
    report = d6.top_level_gate(registry)
    assert report.ok is True and report.probes[0].name == "structured-errors"

    always_false = d6.InvariantGate("broken", lambda v: False, {"ok": True}, "bad")
    registry.register(always_false)
    probes = {p.name: p for p in registry.probe_all()}
    assert probes["broken"].ok is False and probes["structured-errors"].ok is True
    assert d6.top_level_gate(registry).ok is False
    with pytest.raises(d6.GateError):
        registry.assert_proven()

    with pytest.raises(d6.GateError):
        d6.GateException("structured-errors", "global", "temporarily disabled")
    narrow = d6.GateException("structured-errors", "legacy-plugin-only",
                              "only the legacy plugin boundary is exempt")
    registry.exempt(narrow)
    assert "structured-errors" in d6.top_level_gate(registry).exceptions
    with pytest.raises(d6.GateError):
        d6.top_level_gate("not-a-registry")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cross-cutting guarantees
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_deterministic_and_side_effect_free():
    import ast

    path = d6.__file__
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "ast", "fnmatch", "hashlib", "io",
                        "json", "re", "tokenize", "dataclasses", "enum", "typing"}
    forbidden_calls = {"open", "exec", "eval", "__import__", "urlopen", "run", "Popen"}
    assert not any(isinstance(node, ast.Call) and
                   ((isinstance(node.func, ast.Name) and node.func.id in forbidden_calls) or
                    (isinstance(node.func, ast.Attribute) and
                     node.func.attr in forbidden_calls)) for node in ast.walk(tree))
    assert d6.fingerprint({"a": [1, 2]}) == d6.fingerprint({"a": [1, 2]})
    assert d6.canonical_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    assert d6.all_error_codes() == d6.all_error_codes()

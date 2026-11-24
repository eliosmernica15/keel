"""Permanent contract-regression specs for the additive builder contracts.

One or more tests per not_started P0 registry ID implemented here:
X10.1, X10.2, X10.4, X6.7, X8.1, X8.2.

These specs are additive: they import only ``keel.builder_contracts`` and never
mutate the live settings store, the registry, the filesystem or any existing
test.  The required edit-distance/suggestion, token-validation, stop-list
completeness, fail-closed and determinism guarantees are exercised here.
"""

from __future__ import annotations

import json

import pytest

import keel.builder_contracts as bc


# ---------------------------------------------------------------------------
# X10.1 -- definition-of-done template
# ---------------------------------------------------------------------------


def test_dod_template_has_all_six_required_fields():
    assert bc.DOD_FIELDS == (
        "code_path", "test_path", "e2e_run_id", "docs_updated",
        "license_notice_check", "rollback_note",
    )
    assert set(bc.DOD_FIELD_LABELS) == set(bc.DOD_FIELDS)
    template = bc.dod_template("X10.1")
    assert template.complete is False
    assert template.missing_fields == bc.DOD_FIELDS
    assert all(str(getattr(template, name)) == "" for name in bc.DOD_FIELDS)


def test_dod_validation_and_markdown_render():
    filled = bc.DefinitionOfDone(
        feature_id="X10.2", code_path="src/keel/builder_contracts.py",
        test_path="tests/test_builder_contracts.py", e2e_run_id="run-42",
        docs_updated="master-plan-v6-builder-contracts-evidence.md",
        license_notice_check="stdlib only; no copied code",
        rollback_note="delete the three additive files",
    )
    validation = bc.validate_dod(filled)
    assert validation.ok is True and validation.missing == ()
    assert validation.fingerprint == filled.fingerprint
    assert filled.complete is True

    markdown = filled.render_markdown()
    for label in bc.DOD_FIELD_LABELS.values():
        assert label in markdown
    assert "- [x]" in markdown
    assert "- [ ]" not in markdown

    restored = bc.DefinitionOfDone.from_dict(json.loads(json.dumps(filled.to_dict())))
    assert restored == filled


def test_dod_requires_feature_id_and_reports_missing_sections():
    with pytest.raises(bc.DoDError):
        bc.DefinitionOfDone(feature_id="")
    partial = bc.DefinitionOfDone("X8.2", code_path="keel/src/keel/x.py")
    result = bc.validate_dod(partial)
    assert result.ok is False
    assert "code_path" not in result.missing
    assert "rollback_note" in result.missing
    assert "[ ]" in partial.render_markdown()


# ---------------------------------------------------------------------------
# X10.2 -- provenance file generator
# ---------------------------------------------------------------------------


def test_provenance_record_round_trip_and_fingerprint():
    record = bc.build_provenance(
        module="keel.builder_contracts",
        spec_source="Keel_Plan_v5_Addendum_3_Gaps_and_Advanced.md",
        reviewer="owner-pending",
        snippets=(bc.CopiedSnippet("keel/src/keel/jsonc.py", "Proprietary",
                                   "comment stripping idea"),),
        notes="clean-room reimplementation",
    )
    assert bc.validate_provenance(record) is True
    doc = json.loads(json.dumps(record.to_dict()))
    assert doc["copied_snippets"][0]["license"] == "Proprietary"
    assert bc.ProvenanceRecord.from_dict(doc) == record
    assert record.fingerprint == bc.build_provenance(
        record.module, record.spec_source, record.reviewer,
        record.copied_snippets, record.notes).fingerprint


def test_render_provenance_is_deterministic_and_machine_readable():
    record = bc.build_provenance("keel.builder_contracts", "Addendum 3 X10.2",
                                 "owner-pending")
    rendered = bc.render_provenance(record)
    assert rendered == bc.render_provenance(record)
    assert rendered.endswith("\n")
    parsed = json.loads(rendered)
    assert parsed["module"] == "keel.builder_contracts"
    assert parsed["spec_source"] == "Addendum 3 X10.2"
    assert parsed["reviewer"] == "owner-pending"
    assert parsed["copied_snippets"] == []

    markdown = bc.render_provenance(record, fmt="markdown")
    assert "Spec source: Addendum 3 X10.2" in markdown
    assert "None (original clean-room implementation)." in markdown
    with pytest.raises(bc.ProvenanceError):
        bc.render_provenance(record, fmt="yaml")


def test_provenance_rejects_missing_license_spec_source_or_reviewer():
    with pytest.raises(bc.ProvenanceError):
        bc.CopiedSnippet("somewhere", "unknown")
    with pytest.raises(bc.ProvenanceError):
        bc.build_provenance("m", "", "reviewer")
    with pytest.raises(bc.ProvenanceError):
        bc.build_provenance("m", "Addendum 3", "")


# ---------------------------------------------------------------------------
# X10.4 -- builder stop list (owner-paused actions, mirrored from G1-G7)
# ---------------------------------------------------------------------------


def test_stop_list_mirrors_all_seven_owner_gates():
    gate_ids = {e.id for e in bc.STOP_LIST if e.category == "owner_gate"}
    assert gate_ids == {gate.value for gate in bc.Gate}
    assert bc.GATE_TITLES[bc.Gate.G1] == "Changing repo visibility"
    by_id = {e.id: e for e in bc.STOP_LIST}
    assert "visibility" in by_id["G1"].description.lower()
    assert "payment" in by_id["G6"].description.lower()
    assert "private by default" in by_id["G7"].description.lower()


def test_stop_list_is_complete_and_fail_closed():
    result = bc.validate_stop_list(bc.STOP_LIST)
    assert result.ok is True and result.errors == ()
    assert result.entry_count == len(bc.STOP_LIST) == 14
    assert all(e.paused and e.requires_owner_approval for e in bc.STOP_LIST)
    assert all(e.source == bc.STOP_SOURCE for e in bc.STOP_LIST)
    assert any(e.category == "destructive_repo_action" for e in bc.STOP_LIST)

    tampered = [e for e in bc.STOP_LIST if e.id != "G1"]
    assert bc.validate_stop_list(tampered).ok is False
    with pytest.raises(bc.StopListError):
        bc.StopListEntry("G8", "x", "y", "owner_gate", paused=False)
    with pytest.raises(bc.StopListError):
        bc.StopListEntry("G8", "x", "y", "owner_gate",
                         requires_owner_approval=False)


def test_stop_list_document_is_deterministic_machine_readable_file():
    doc = bc.stop_list_document()
    assert doc["filename"] == bc.STOP_LIST_FILENAME
    assert doc["source"] == bc.STOP_SOURCE
    assert len(doc["entries"]) == 14
    assert json.loads(bc.stop_list_json()) == doc
    assert bc.stop_list_json() == bc.stop_list_json()
    assert doc["fingerprint"] == bc.validate_stop_list().fingerprint


def test_check_action_pauses_gates_and_destructive_repo_actions():
    assert bc.check_action("G2").matched_id == "G2"
    assert bc.check_action("change repo visibility to public").matched_id == "G1"
    assert bc.check_action("git push --force to main").matched_id == "DR1"
    decision = bc.check_action("adopt final EULA text")
    assert decision.paused is True and decision.requires_owner_approval is True
    assert decision.reasons

    benign = bc.check_action("run the unit tests")
    assert benign.paused is False and benign.matched_id == ""
    assert bc.assert_not_paused("run the unit tests") is True
    with pytest.raises(bc.StopListError):
        bc.assert_not_paused("G1")


# ---------------------------------------------------------------------------
# X6.7 -- config validation: edit distance, JSONC line/column, config explain
# ---------------------------------------------------------------------------


def test_edit_distance_known_values():
    assert bc.edit_distance("kitten", "sitting") == 3
    assert bc.edit_distance("theme", "theme") == 0
    assert bc.edit_distance("", "model") == 5
    assert bc.edit_distance("model", "") == 5
    assert bc.edit_distance("ab", "ba") == 2
    assert bc.edit_distance("flaw", "lawn") == 2
    assert bc.edit_distance("kitten", "sitting") == bc.edit_distance("sitting", "kitten")
    with pytest.raises(TypeError):
        bc.edit_distance(None, "x")  # type: ignore[arg-type]


def test_did_you_mean_ranks_deduplicates_and_limits():
    assert bc.did_you_mean("thme", sorted(bc.KNOWN_CONFIG_KEYS)) == ("theme",)
    assert "model" in bc.did_you_mean("modle", sorted(bc.KNOWN_CONFIG_KEYS))
    # Case-insensitive scoring returns the original candidate spelling and
    # never echoes the misspelled input.
    assert bc.did_you_mean("THME", ("theme", "Theme", "themes"),
                           max_distance=1) == ("theme",)
    assert bc.did_you_mean("thme", ("Theme", "theme"), max_distance=1) == ("Theme",)
    assert bc.did_you_mean("theme", ("theme", "thme")) == ("thme",)
    assert len(bc.did_you_mean("t", sorted(bc.KNOWN_CONFIG_KEYS), limit=2)) <= 2
    assert bc.did_you_mean("zzzzzzzzzz", sorted(bc.KNOWN_CONFIG_KEYS),
                           max_distance=1) == ()
    assert bc.did_you_mean("thme", ("theme",), limit=0) == ()


def test_validate_config_text_reports_jsonc_key_typo_with_line_column():
    text = ('{\n'
            '  // primary theme\n'
            '  "thme": "dark",\n'
            '  "model": "local",\n'
            '}\n')
    result = bc.validate_config_text(text)
    assert result.ok is False and result.key_count == 2
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.key == "thme"
    assert (diag.line, diag.column) == (3, 3)
    assert diag.suggestions == ("theme",)
    assert "line 3 column 3" in str(diag)
    assert json.loads(json.dumps(result.to_dict()))["ok"] is False

    valid = text.replace('"thme"', '"theme"')
    assert bc.validate_config_text(valid).ok is True


def test_validate_config_text_reports_json_decode_line_column():
    text = ('{\n'
            '  "theme": "dark"\n'
            '  "model": "local"\n'
            '}\n')
    result = bc.validate_config_text(text)
    assert result.ok is False
    diag = result.diagnostics[0]
    assert (diag.line, diag.column) == (3, 3)
    assert diag.message
    assert "did you mean" not in str(diag)


def test_config_explain_found_and_suggestions():
    found = bc.explain_key("Theme")
    assert found.found is True
    assert "theme" in found.description.lower()
    assert found.command == "keel config explain Theme"

    missing = bc.explain_key("thme")
    assert missing.found is False
    assert missing.suggestions == ("theme",)
    assert "did you mean theme" in missing.render()
    assert bc.explain_key("zzzzzzzzzz").suggestions == ()


# ---------------------------------------------------------------------------
# X8.2 -- design-token contract and hard-coded value lint
# ---------------------------------------------------------------------------


def test_default_tokens_pass_validation():
    result = bc.validate_tokens(bc.DEFAULT_TOKENS)
    assert result.ok is True and result.errors == ()
    assert result.categories == tuple(sorted(bc.TOKEN_CATEGORIES))
    assert set(result.categories) == set(bc.TOKEN_CATEGORIES)
    assert result.token_count == sum(len(v) for v in bc.DEFAULT_TOKENS.values())
    assert len(bc.flatten_tokens(bc.DEFAULT_TOKENS)) == result.token_count
    assert bc.flatten_tokens(bc.DEFAULT_TOKENS)["color.accent"] == "#4c8dff"


def test_token_validation_rejects_missing_category_bad_name_and_empty_value():
    missing = {k: v for k, v in bc.DEFAULT_TOKENS.items() if k != "motion"}
    result = bc.validate_tokens(missing)
    assert result.ok is False
    assert any("motion" in e.pointer and "missing" in e.message for e in result.errors)

    bad = json.loads(json.dumps(bc.DEFAULT_TOKENS))
    bad["color"]["Bad Name"] = "#ffffff"
    bad["spacing"]["md"] = ""
    result2 = bc.validate_tokens(bad)
    assert result2.ok is False
    assert any("invalid token name" in e.message for e in result2.errors)
    assert any("non-empty string" in e.message for e in result2.errors)
    assert bc.validate_tokens([]).ok is False


def test_tokens_json_is_canonical_and_deterministic():
    rendered = bc.tokens_json()
    assert rendered == bc.tokens_json()
    assert rendered.endswith("\n")
    assert json.loads(rendered) == bc.DEFAULT_TOKENS
    assert rendered.index('"color"') < rendered.index('"type"')
    with pytest.raises(bc.TokenContractError):
        bc.tokens_json({"color": {"bg": "#ffffff"}})


def test_lint_rejects_hardcoded_values_with_line_column_and_suggestion():
    source = ('<style>\n'
              '  .button { color: #4c8dff; padding: 12px; transition: 120ms; }\n'
              '</style>\n')
    report = bc.lint_source(source, path="site/ui/app.css")
    assert report.clean is False and len(report.findings) == 3
    first = report.findings[0]
    assert (first.kind, first.value, first.line, first.column) == (
        "color", "#4c8dff", 2, 20)
    assert first.suggestion == "color.accent"
    assert {f.suggestion for f in report.findings} == {
        "color.accent", "spacing.md", "motion.fast",
    }
    assert report.fingerprint == bc.lint_source(source).fingerprint
    assert json.loads(json.dumps(report.to_dict()))["clean"] is False

    clean = "color: var(--color-accent); padding: var(--spacing-md);"
    assert bc.lint_source(clean).clean is True


def test_assert_no_hardcoded_values_raises_on_violation():
    assert bc.assert_no_hardcoded_values("color: var(--color-accent);") is True
    with pytest.raises(bc.TokenContractError):
        bc.assert_no_hardcoded_values("border: 1px solid #ff5c5c;")


# ---------------------------------------------------------------------------
# X8.1 -- local component catalog
# ---------------------------------------------------------------------------


def test_catalog_covers_every_component_in_every_declared_state():
    result = bc.validate_catalog()
    assert result.ok is True and result.errors == ()
    assert result.component_count == len(bc.LOCAL_COMPONENT_CATALOG) == 9
    assert result.variant_count == sum(
        len(c.states) for c in bc.LOCAL_COMPONENT_CATALOG)
    assert all(bc.ComponentState.DEFAULT in c.states
               for c in bc.LOCAL_COMPONENT_CATALOG)
    assert all(c.token_refs for c in bc.LOCAL_COMPONENT_CATALOG)
    assert {s.value for s in bc.ComponentState} >= {"default", "loading", "error"}


def test_catalog_manifest_resolves_tokens_deterministically():
    manifest = bc.catalog_manifest()
    assert manifest["source"] == "tokens.json"
    assert manifest["variant_count"] == len(manifest["variants"])
    assert manifest == bc.catalog_manifest()
    assert bc.render_catalog_json() == bc.render_catalog_json()
    assert json.loads(bc.render_catalog_json()) == manifest
    for variant in manifest["variants"]:
        for ref, value in variant["tokens"].items():
            assert bc.flatten_tokens(bc.DEFAULT_TOKENS)[ref] == value

    bad = (bc.ComponentDescriptor(
        "Ghost", (bc.ComponentState.DEFAULT,), ("color.does-not-exist",)),)
    assert bc.validate_catalog(bad).ok is False
    with pytest.raises(bc.TokenContractError):
        bc.catalog_manifest(bad)


# ---------------------------------------------------------------------------
# cross-cutting: purity and determinism
# ---------------------------------------------------------------------------


def test_all_fingerprints_are_reproducible():
    dod = bc.dod_template("X")
    record = bc.build_provenance("m", "s", "r")
    assert bc.validate_dod(dod).fingerprint == bc.validate_dod(dod).fingerprint
    assert record.fingerprint == bc.build_provenance("m", "s", "r").fingerprint
    assert bc.validate_stop_list().fingerprint == bc.validate_stop_list().fingerprint
    assert bc.validate_config_text("{}").fingerprint == \
        bc.validate_config_text("{}").fingerprint
    assert bc.validate_tokens(bc.DEFAULT_TOKENS).fingerprint == \
        bc.validate_tokens(bc.DEFAULT_TOKENS).fingerprint
    assert bc.validate_catalog().fingerprint == bc.validate_catalog().fingerprint


def test_module_has_no_runtime_side_effects_or_external_dependencies():
    from pathlib import Path

    source = (Path(bc.__file__).parent / "builder_contracts.py").read_text(
        encoding="utf-8")
    for forbidden in ("import socket", "import subprocess", "import urllib",
                      "import requests", "os.system", "open(", "Path("):
        assert forbidden not in source
    assert "__all__" in source

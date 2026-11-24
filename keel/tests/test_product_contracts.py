"""P0 product contracts — W1.10, W4.3, W6.1, W6.3.

All checks are adversarial and pure: the tests never open a socket, spawn a
process, read a file, read the clock or consume randomness.  The module's
import graph is asserted to be stdlib-only, and every descriptor is checked to
carry ``network=False`` / ``runtime_claimed=False`` / no secret values.

W1.18 (MIT license) is explicitly **not** implemented: it is owner-gated and
conflicts with the proprietary license requirement.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from keel import product_contracts as pc

REPO = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parents[1] / "src" / "keel"

VALID_NOTICE = """\
# Keel Safety Notice

Version: 1.2.0

## Scope
This notice describes the safety envelope.

## Reporting
Report issues at https://example.com/safety/report.
"""

DISCOVERY = {
    "issuer": "https://mcp.example.com",
    "authorization_endpoint": "https://mcp.example.com/authorize",
    "token_endpoint": "https://mcp.example.com/token",
    "code_challenge_methods_supported": ["S256"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "response_types_supported": ["code"],
}
# RFC 7636 Appendix B test vector.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _metadata(**overrides):
    data = dict(DISCOVERY)
    data.update(overrides)
    return pc.validate_discovery_document(data, server_url="https://mcp.example.com")


def _flow(**overrides):
    kwargs = {
        "redirect_uri": "https://client.example.com/callback",
        "client_id": "keel-client",
        "verifier": RFC_VERIFIER,
        "state": "a" * 32,
        "scope": ("mcp:read", "mcp:write"),
    }
    kwargs.update(overrides)
    return pc.oauth_flow_descriptor("mcp-server", _metadata(), **kwargs)


def _claim(**overrides):
    kwargs = {
        "text": "The build passed.",
        "status": pc.ClaimStatus.VERIFIED,
        "sources": ("https://ci.example.com/build/42",),
        "topic": "build",
        "value": "",
        "origin": "tool",
    }
    kwargs.update(overrides)
    return pc.make_claim(**kwargs)


def _draft(**overrides):
    kwargs = {
        "text": "The build passed. Verified from the CI output.",
        "claims": (_claim(),),
    }
    kwargs.update(overrides)
    return pc.make_response_draft(**kwargs)


# ---------------------------------------------------------------------------
# Registry coverage and purity
# ---------------------------------------------------------------------------


def test_feature_ids_are_exactly_the_four_assigned_rows():
    assert pc.FEATURE_IDS == ("W1.10", "W4.3", "W6.1", "W6.3")
    assert pc.OWNER_GATED_NOT_IMPLEMENTED == ("W1.18",)
    assert "W1.18" not in pc.FEATURE_IDS


def test_registry_rows_are_the_assigned_p0_rows():
    registry = json.loads((REPO / "PLAN-INDEX.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in registry["features"]}
    for fid in pc.FEATURE_IDS:
        row = by_id[fid]
        assert row["priority"] == "P0"
        assert row["source_feature_id"] == fid
        assert row["acceptance_criteria"]
    assert "MIT" in by_id["W1.18"]["feature"]  # owner-gated, deliberately absent


def test_all_feature_descriptors_are_descriptor_only():
    rows = pc.feature_descriptors()
    assert set(rows) == set(pc.FEATURE_IDS)
    for row in rows.values():
        assert row["layer"] == "descriptor_only"
        assert row["io_performed"] is False
        assert row["network"] is False
        assert row["runtime_claimed"] is False
        assert row["secret_values"] is False
        assert row["contract"]


def test_module_imports_are_stdlib_and_pure():
    tree = ast.parse((SRC / "product_contracts.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    full_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                full_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            full_names.add(node.module)
    assert imported <= {"__future__", "base64", "hashlib", "re", "dataclasses",
                        "enum", "typing"}
    forbidden = {"socket", "subprocess", "os", "urllib.request", "http.client",
                 "requests", "sqlite3", "pathlib", "secrets", "keyring", "time"}
    assert not (full_names & forbidden)


def test_error_messages_never_leak_secret_material():
    with pytest.raises(pc.ProductContractError) as exc:
        pc.credential_ref("keychain", "sk-abcdefghijklmnop")
    assert "sk-abcdefghijklmnop" not in str(exc.value)
    with pytest.raises(pc.ProductContractError) as exc:
        pc._text("Authorization: Bearer sk-abcdefghijklmnop", "blob")
    assert "sk-abcdefghijklmnop" not in str(exc.value)


# ---------------------------------------------------------------------------
# W1.10 — SAFETY.md first-run notice
# ---------------------------------------------------------------------------


def test_w110_notice_descriptor_and_digest():
    notice = pc.safety_notice_descriptor(VALID_NOTICE)
    assert notice.version == "1.2.0"
    assert notice.title == "Keel Safety Notice"
    assert notice.sections == ("Scope", "Reporting")
    assert notice.content_sha256 == pc._digest(VALID_NOTICE)
    assert notice.to_dict()["filename"] == "SAFETY.md"
    assert notice.to_dict()["io_performed"] is False


def test_w110_first_run_and_acknowledgement():
    notice = pc.safety_notice_descriptor(VALID_NOTICE)
    descriptor = pc.first_run_descriptor(notice)
    assert descriptor["show"] is True
    assert descriptor["first_run"] is True
    assert descriptor["reason"] == "first_run"
    state = pc.acknowledge_notice(None, notice)
    assert pc.needs_notice(state, notice) is False
    assert pc.first_run_descriptor(notice, state)["reason"] == "acknowledged"


def test_w110_version_change_and_content_change_are_re_shown():
    notice = pc.safety_notice_descriptor(VALID_NOTICE)
    state = pc.acknowledge_notice(None, notice)
    newer = pc.safety_notice_descriptor(VALID_NOTICE.replace("Version: 1.2.0",
                                                              "Version: 1.3.0"))
    assert pc.notice_reason(state, newer) == "version_changed"
    # Same version, different bytes: digest change must also re-show the notice.
    edited = pc.safety_notice_descriptor(VALID_NOTICE + "\n## Extra\nMore detail.\n")
    assert edited.version == notice.version
    assert pc.notice_reason(state, edited) == "content_changed"
    assert pc.first_run_descriptor(edited, state)["show"] is True
    declined = pc.decline_notice(state)
    assert pc.notice_reason(declined, notice) == "first_run"


@pytest.mark.parametrize("bad,expected", [
    (VALID_NOTICE.replace("Version: 1.2.0\n", ""), "Version: marker"),
    (VALID_NOTICE.replace("Version: 1.2.0", "Version: 1.0\nVersion: 2.0"), "more than one"),
    (VALID_NOTICE.replace("# Keel Safety Notice", "# Keel User Guide"), "mention safety"),
    (VALID_NOTICE.replace("## Scope\nThis notice describes the safety envelope.\n", "")
                  .replace("## Reporting\nReport issues at "
                           "https://example.com/safety/report.\n", ""),
     "at least one section"),
    (VALID_NOTICE + "\napi_key=sk-abcdefghijklmnop\n", "credentials"),
    (VALID_NOTICE.replace("https://example.com/safety/report",
                          "javascript:alert(1)").replace(
                              "Report issues at javascript:alert(1).",
                              "Report issues [here](javascript:alert(1))."),
     "notice link"),
    (123, "must be text"),
    (VALID_NOTICE + "\x00", "control characters"),
])
def test_w110_content_check_rejects_bad_notice(bad, expected):
    errors = pc.validate_safety_notice_text(bad)
    assert errors
    assert any(expected in error for error in errors)
    with pytest.raises(pc.ProductContractError) as exc:
        pc.safety_notice_descriptor(bad)
    assert exc.value.code == "invalid_safety_notice"


def test_w110_oversized_notice_rejected():
    oversized = VALID_NOTICE + ("x" * (pc.MAX_SAFETY_BYTES + 1))
    errors = pc.validate_safety_notice_text(oversized)
    assert any("64 KiB" in error for error in errors)


def test_w110_notice_state_is_validated_fail_closed():
    notice = pc.safety_notice_descriptor(VALID_NOTICE)
    with pytest.raises(pc.ProductContractError):
        pc.notice_reason(pc.SafetyNoticeState(None, "a" * 64), notice)
    with pytest.raises(pc.ProductContractError):
        pc.notice_reason(pc.SafetyNoticeState("1.2.0", "not-a-digest"), notice)
    with pytest.raises(pc.ProductContractError):
        pc.notice_reason("acknowledged", notice)
    with pytest.raises(pc.ProductContractError):
        pc.safety_notice_descriptor(VALID_NOTICE, website_link="file:///etc/passwd")


# ---------------------------------------------------------------------------
# W4.3 — OAuth PKCE / discovery / refresh / out-of-project credentials
# ---------------------------------------------------------------------------


def test_w43_pkce_matches_rfc7636_vector_and_drops_verifier():
    challenge = pc.pkce_challenge(RFC_VERIFIER)
    assert challenge.method == "S256"
    assert challenge.challenge == RFC_CHALLENGE
    assert challenge.verifier_length == len(RFC_VERIFIER)
    data = challenge.to_dict()
    assert RFC_VERIFIER not in str(data)
    assert data["verifier_retained"] is False


@pytest.mark.parametrize("verifier,method,code", [
    ("short", "S256", "bad_pkce_verifier_length"),
    ("!" * 50, "S256", "bad_pkce_verifier_chars"),
    (RFC_VERIFIER, "plain", "plain_pkce_rejected"),
    ("sk-" + "a" * 50, "S256", "secret_in_pkce_verifier"),
    (RFC_VERIFIER.encode(), "S256", "bad_pkce_verifier_length"),
])
def test_w43_pkce_rejects_bad_input(verifier, method, code):
    with pytest.raises(pc.ProductContractError) as exc:
        pc.pkce_challenge(verifier, method=method)
    assert exc.value.code == code


def test_w43_discovery_validation_and_loopback_exception():
    assert _metadata().token_endpoint == "https://mcp.example.com/token"
    with pytest.raises(pc.ProductContractError) as exc:
        pc.validate_discovery_document(
            {**DISCOVERY, "token_endpoint": "http://mcp.example.com/token"},
            server_url="https://mcp.example.com")
    assert exc.value.code == "insecure_token_endpoint"
    local = pc.validate_discovery_document({
        "issuer": "http://127.0.0.1:3000",
        "authorization_endpoint": "http://127.0.0.1:3000/authorize",
        "token_endpoint": "http://127.0.0.1:3000/token",
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
    }, server_url="http://127.0.0.1:3000/mcp")
    assert local.issuer == "http://127.0.0.1:3000"


@pytest.mark.parametrize("overrides,code", [
    ({"issuer": "https://evil.example.com"}, "issuer_origin_mismatch"),
    ({"code_challenge_methods_supported": ["plain"]}, "s256_not_supported"),
    ({"grant_types_supported": ["authorization_code"]}, "missing_required_grants"),
    ({"response_types_supported": ["token"]}, "code_response_not_supported"),
    ({"client_secret": "sk-abcdefghijklmnop"}, "secret_in_discovery"),
])
def test_w43_discovery_fails_closed(overrides, code):
    with pytest.raises(pc.ProductContractError) as exc:
        pc.validate_discovery_document(
            {**DISCOVERY, **overrides}, server_url="https://mcp.example.com")
    assert exc.value.code == code


def test_w43_discovery_rejects_non_mapping_and_bad_server_url():
    with pytest.raises(pc.ProductContractError):
        pc.validate_discovery_document([], server_url="https://mcp.example.com")
    with pytest.raises(pc.ProductContractError):
        pc.validate_discovery_document(DISCOVERY, server_url="ftp://mcp.example.com")


def test_w43_credential_refs_are_opaque_and_outside_project():
    ref = pc.credential_ref("keychain", "keel/mcp/mcp-server/oauth")
    assert ref.outside_project is True and ref.never_in_config is True
    assert ref.to_dict()["credential_value"] is None
    assert pc.credential_ref_from_config(
        "credential-ref:keel/mcp/mcp-server/header") == pc.credential_ref(
            "keychain", "keel/mcp/mcp-server/header")
    with pytest.raises(pc.ProductContractError) as exc:
        pc.credential_ref("filesystem", "some/path")
    assert exc.value.code == "unknown_credential_store"
    with pytest.raises(pc.ProductContractError):
        pc.credential_ref("keychain", "/absolute/path")
    with pytest.raises(pc.ProductContractError):
        pc.assert_credential_store_outside_project(
            "C:/Users/Admin/project/creds", "C:/Users/Admin/project")
    assert pc.assert_credential_store_outside_project(
        "C:/Users/Admin/.keel/credentials", "C:/Users/Admin/project")


def test_w43_literal_credentials_in_config_are_rejected():
    bad = {"oauth": False, "headers": {"Authorization": "Bearer sk-abcdefghijklmnop"}}
    with pytest.raises(pc.ProductContractError) as exc:
        pc.assert_no_credentials_in_config(bad)
    assert exc.value.code == "literal_credential_in_config"
    with pytest.raises(pc.ProductContractError):
        pc.assert_no_credentials_in_config({"client_secret": "literal-secret"})
    pc.assert_no_credentials_in_config({
        "oauth": False,
        "headerKeyRef": "credential-ref:keel/mcp/mcp-server/header",
    })


def test_w43_oauth_flow_descriptor_is_data_only():
    flow = _flow()
    assert flow.authorization_url.startswith("https://mcp.example.com/authorize?")
    for fragment in ("response_type=code", "client_id=keel-client",
                     "code_challenge=" + RFC_CHALLENGE, "code_challenge_method=S256",
                     "state=" + "a" * 32):
        assert fragment in flow.authorization_url
    data = flow.to_dict()
    assert RFC_VERIFIER not in str(data)
    assert data["network"] is False and data["secret_values"] is False
    assert data["token_endpoint"] == "https://mcp.example.com/token"
    with pytest.raises(pc.ProductContractError) as exc:
        _flow(client_secret="sk-abcdefghijklmnop")
    assert exc.value.code == "client_secret_must_be_keychain_ref"
    _flow(client_secret=pc.credential_ref("keychain", "keel/mcp/client/secret"))


@pytest.mark.parametrize("overrides,code", [
    ({"redirect_uri": "http://evil.example.com/callback"}, "insecure_redirect_uri"),
    ({"redirect_uri": "https://client.example.com/"}, "bad_redirect_uri"),
    ({"state": "too-short"}, "bad_oauth_state"),
    ({"scope": ("mcp:read", "a b")}, "bad_scope"),
])
def test_w43_oauth_flow_rejects_bad_input(overrides, code):
    with pytest.raises(pc.ProductContractError) as exc:
        _flow(**overrides)
    assert exc.value.code == code


def test_w43_header_server_has_oauth_false_and_never_starts_a_flow():
    config = {"oauth": False, "headerKeyRef": "credential-ref:keel/mcp/mcp-server/header"}
    auth = pc.remote_auth_descriptor("mcp-server", "https://mcp.example.com/mcp", config)
    assert auth.to_dict()["oauth"] is False
    assert auth.mode is pc.AuthMode.HEADER
    assert auth.oauth_attempted is False
    assert auth.static_header_authoritative is True
    assert auth.flow is None
    with pytest.raises(pc.ProductContractError) as exc:
        pc.remote_auth_descriptor("mcp-server", "https://mcp.example.com/mcp",
                                  config, flow=_flow())
    assert exc.value.code == "oauth_disabled_with_flow"


def test_w43_header_on_oauth_server_fails_closed_instead_of_falling_back():
    config = {"oauth": True, "headerKeyRef": "credential-ref:keel/mcp/mcp-server/header"}
    with pytest.raises(pc.ProductContractError) as exc:
        pc.remote_auth_descriptor("mcp-server", "https://mcp.example.com/mcp", config)
    assert exc.value.code == "header_auth_takes_precedence"


def test_w43_oauth_server_requires_a_matching_flow():
    url = "https://mcp.example.com/mcp"
    with pytest.raises(pc.ProductContractError) as exc:
        pc.remote_auth_descriptor("mcp-server", url, {"oauth": True})
    assert exc.value.code == "missing_or_mismatched_oauth_flow"
    with pytest.raises(pc.ProductContractError):
        pc.remote_auth_descriptor("other-server", url, {"oauth": True}, flow=_flow())
    auth = pc.remote_auth_descriptor("mcp-server", url, {"oauth": True}, flow=_flow())
    assert auth.mode is pc.AuthMode.OAUTH and auth.oauth_attempted is True
    assert auth.static_header_authoritative is False
    with pytest.raises(pc.ProductContractError):
        pc.oauth_switch({"oauth": "false"})


def test_w43_refresh_is_bounded_and_token_state_has_no_secret():
    cred = pc.credential_ref("keychain", "keel/mcp/mcp-server/oauth")
    state = pc.token_state(cred, expires_at=100, scopes=("mcp:read",),
                           refresh_available=True)
    assert state.to_dict()["token_value"] is None
    assert pc.refresh_decision(state, now=200, attempts=0).action is pc.RefreshAction.REFRESH
    assert pc.refresh_decision(state, now=200, attempts=1).action is \
        pc.RefreshAction.REAUTHENTICATE
    assert pc.refresh_decision(state, now=50).reason == "not_expired"
    assert pc.refresh_decision(
        pc.token_state(cred, refresh_available=True), now=200).reason == "no_expiry"
    no_refresh = pc.token_state(cred, expires_at=100)
    assert pc.refresh_decision(no_refresh, now=200).reason == "no_refresh_token"
    with pytest.raises(pc.ProductContractError):
        pc.refresh_decision(state, now=-1)
    first = pc.refresh_decision(state, now=200, attempts=0)
    second = pc.refresh_decision(state, now=200, attempts=1)
    pc.assert_refresh_bounded([first, second])
    with pytest.raises(pc.ProductContractError) as exc:
        pc.assert_refresh_bounded([first, first])
    assert exc.value.code == "refresh_loop"


# ---------------------------------------------------------------------------
# W6.1 — accuracy-over-approval response contract
# ---------------------------------------------------------------------------


def test_w61_claims_require_real_sources_and_never_trust_user_assertions():
    assert _claim().status is pc.ClaimStatus.VERIFIED
    with pytest.raises(pc.ProductContractError) as exc:
        pc.make_claim("It works", pc.ClaimStatus.VERIFIED)
    assert exc.value.code == "verified_claim_needs_source"
    with pytest.raises(pc.ProductContractError) as exc:
        pc.make_claim("2+2=5", pc.ClaimStatus.VERIFIED,
                      sources=("https://example.com/x",), origin="user")
    assert exc.value.code == "user_assertion_not_verification"
    with pytest.raises(pc.ProductContractError):
        pc.make_claim("guess", pc.ClaimStatus.ESTIMATE)
    with pytest.raises(pc.ProductContractError):
        pc.make_claim("unknown", pc.ClaimStatus.UNKNOWN,
                      sources=("https://example.com/x",))


@pytest.mark.parametrize("citation", [
    "javascript:alert(1)", "https://example.com/a/../b",
    "https://example.com/token?key=sk-abcdefghijklmnop", "",
])
def test_w61_citations_fail_closed(citation):
    with pytest.raises(pc.ProductContractError):
        pc.validate_citation(citation)


def test_w61_clean_response_finalizes():
    contract = pc.assert_finalizable(_draft())
    assert contract.finalizable is True and contract.errors == ()
    assert contract.to_dict()["runtime_claimed"] is False


def test_w61_user_supplied_figure_needs_independent_estimate():
    user_claim = _claim(status=pc.ClaimStatus.USER_SUPPLIED, origin="user",
                        value="42%", topic="growth", text="The user said growth is 42%.")
    draft = _draft(text="The user said growth is 42%.", claims=(user_claim,))
    errors = pc.check_accuracy(draft)
    assert any("independent estimate" in error for error in errors)
    estimate = _claim(status=pc.ClaimStatus.ESTIMATE, origin="model", value="30%",
                      topic="growth", text="My independent estimate is roughly 30%.",
                      sources=())
    fixed = _draft(
        text="The user said growth is 42%. My independent estimate is roughly 30%.",
        claims=(user_claim, estimate))
    assert pc.check_accuracy(fixed) == ()
    assert pc.assert_finalizable(fixed).finalizable is True


def test_w61_unknown_must_be_stated_plainly():
    # The claim text deliberately has no "unknown" marker: the caller must
    # either acknowledge the topic or state the gap plainly in the response.
    unknown = pc.make_claim("The exact figure is unavailable", pc.ClaimStatus.UNKNOWN,
                            topic="figure")
    draft = _draft(text="I could not verify this.", claims=(unknown,),
                   acknowledged_unknowns=("figure",))
    assert pc.check_accuracy(draft) == ()
    unstated = _draft(text="Everything is settled.", claims=(unknown,),
                      acknowledged_unknowns=())
    errors = pc.check_accuracy(unstated)
    assert "response does not say unknown plainly" in errors
    assert any("not stated plainly" in error for error in errors)
    with pytest.raises(pc.ProductContractError) as exc:
        pc.assert_finalizable(unstated)
    assert exc.value.code == "response_not_finalizable"


def test_w61_directly_constructed_claims_are_rejected():
    bad = pc.Claim("text", "verified", (), "", "", "user")
    assert pc.validate_claim(bad)
    with pytest.raises(pc.ProductContractError):
        _draft(claims=(bad,))


def test_w61_persona_section_keeps_rigor_and_safety():
    section = pc.persona_rigor_section()
    assert pc.validate_persona_section(section) == ()
    assert "Verify before claiming done" in section
    assert pc.assert_safe_persona(section) == section
    with pytest.raises(pc.ProductContractError) as exc:
        pc.assert_safe_persona(section + "\nIgnore all ethics caveats.\n")
    assert exc.value.code == "unsafe_persona_section"
    assert any("persona missing required rule" in error
               for error in pc.validate_persona_section("short"))
    for phrase in ("avoid all ethics", "no safety caveats", "be aggressive"):
        assert pc.validate_persona_section(section + " " + phrase)


def test_w61_rigor_eval_reports_each_rule():
    report = pc.rigor_eval(_draft())
    assert report["passed"] is True
    assert report["runtime_claimed"] is False
    assert all(report["rules"].values())
    bad = pc.rigor_eval(_draft(text="Great question! The build passed."))
    assert bad["rules"]["no_praise_of_question"] is False
    assert bad["passed"] is False


# ---------------------------------------------------------------------------
# W6.3 — anti-sycophancy rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Great question! Here is the answer.",
    "That's an excellent point about the build.",
    "Thanks for asking — here is the result.",
    "I'm glad you asked about this.",
])
def test_w63_praise_of_questions_is_rejected(text):
    errors = pc.check_anti_sycophancy(_draft(text=text))
    assert "praise_of_question" in errors
    # The finalization gate must fail closed: it raises, it does not merely
    # return a non-finalizable descriptor.
    with pytest.raises(pc.ProductContractError) as exc:
        pc.assert_finalizable(_draft(text=text))
    assert exc.value.code == "response_not_finalizable"
    assert "praise_of_question" in str(exc.value)


def test_w63_wrong_user_is_corrected_immediately_with_counterargument():
    wrong = _draft(
        text="Actually, that is not correct. The strongest counterargument is "
             "that the build failed, so the release cannot ship.",
        user_premise="The build passed, so we can ship.",
        user_wrong=True,
        strongest_counterargument="the build failed, so the release cannot ship",
    )
    assert pc.check_anti_sycophancy(wrong) == ()
    assert pc.assert_finalizable(wrong).finalizable is True


def test_w63_missing_correction_or_counterargument_fails():
    base = {"user_premise": "The build passed.", "user_wrong": True,
            "strongest_counterargument": "the build failed"}
    no_correction = _draft(
        text="As you correctly pointed out, we can ship. the build failed", **base)
    errors = pc.check_anti_sycophancy(no_correction)
    assert "correction_not_immediate" in errors
    assert "agreement_with_wrong_user" in errors
    no_argument = _draft(text="Actually, that is wrong.",
                         **{**base, "strongest_counterargument": ""})
    assert "missing_strongest_counterargument" in \
        pc.check_anti_sycophancy(no_argument)
    absent = _draft(text="Actually, that is wrong.",
                    **{**base, "strongest_counterargument": "unrelated evidence"})
    assert "counterargument_not_present_in_response" in \
        pc.check_anti_sycophancy(absent)
    unassessed = _draft(text="Maybe.", user_premise="The build passed.")
    assert "user_correctness_not_assessed" in pc.check_anti_sycophancy(unassessed)


def test_w63_no_capitulation_without_new_evidence():
    pushback = _draft(text="I still think the build failed.",
                      pushback=True, position_changed=True)
    assert "capitulation_without_new_evidence" in pc.check_anti_sycophancy(pushback)
    with_evidence = _draft(text="I still think the build failed.",
                           pushback=True, position_changed=True,
                           new_evidence=("https://ci.example.com/build/43",))
    assert pc.check_anti_sycophancy(with_evidence) == ()


def test_w63_persona_does_not_copy_safety_removal():
    section = pc.persona_rigor_section()
    assert "safety messaging" in section and "Tier-2" in section
    stripped = section.replace("Tier-2", "Tier-1")
    assert any("Tier-2" in error for error in pc.validate_persona_section(stripped))


def test_w61_and_w63_errors_combine_in_one_contract():
    draft = _draft(
        text="Great question! The figure is 42% — accurate.",
        user_premise="The figure is 42%.",
        user_wrong=True,
        pushback=True,
        position_changed=True,
        claims=(_claim(status=pc.ClaimStatus.USER_SUPPLIED, origin="user",
                       value="42%", topic="figure", text="42%"),),
    )
    contract = pc.response_contract(draft)
    assert contract.finalizable is False
    assert any("independent estimate" in error for error in contract.accuracy_errors)
    assert "praise_of_question" in contract.anti_sycophancy_errors
    assert "capitulation_without_new_evidence" in contract.anti_sycophancy_errors

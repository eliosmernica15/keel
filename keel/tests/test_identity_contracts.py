"""P0 identity-contract tests (stdlib-only; no model, host I/O or network).

Covers the pure descriptor/policy surface of ``keel.identity_contracts``:

* Y4.9 — agent identity/SOUL descriptors: required PERSONA.md sections, an
  original rigor contract, a deterministic coding-agent/desktop control-plane
  routing table, and a "no copied prompts/assets" originality gate;
* Y4.3 — first-boot sign-in test-fire: a strictly one-token probe that fails
  loudly with the exact provider error (zero-credit accounts must not pass);
* Y4.13 — version badge and zero-secrets release scan: strict VERSION parsing,
  the ``VERSION=x.y.z build`` pattern, deterministic secret detection that
  never echoes the secret, and a fail-closed release gate.

Run from the worktree root with::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_identity_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

import keel.identity_contracts as ic
from keel.identity_contracts import (
    DEFAULT_RIGOR_RULES,
    DEFAULT_ROUTING_RULES,
    PROBE_TOKEN_BUDGET,
    Artifact,
    BootDecision,
    IdentityContractError,
    PromptAsset,
    PromptOrigin,
    ProbeResponse,
    ProbeResult,
    ProbeStatus,
    ProviderError,
    ReleaseVerification,
    RouteDecision,
    RouteTarget,
    RoutingRule,
    RoutingTable,
    SecretFinding,
    Severity,
    SignInProbe,
    SoulDescriptor,
    SoulSection,
    ValidationIssue,
    VersionBadge,
    ZeroSecretsScan,
    assert_original,
    build_command,
    canonical_digest,
    default_soul,
    evaluate_probe,
    first_boot_decision,
    is_valid_version,
    is_verbatim_copy,
    is_zero_credit,
    parse_build_command,
    parse_version,
    redact_secrets,
    render_soul,
    scan_secrets,
    skipped_probe,
    tokenize,
    validate_soul,
    verify_release,
)


def _clean_result(provider="openai"):
    probe = SignInProbe(provider, "model-x", "PROVIDER_API_KEY")
    return evaluate_probe(probe, ProbeResponse(200, tokens_used=1))


def _fail_result(code="insufficient_quota", message="Your account has no credits"):
    probe = SignInProbe("openai", "model-x", "PROVIDER_API_KEY")
    return evaluate_probe(probe, ProbeResponse(
        status_code=402, error_code=code, error_message=message, tokens_used=1))


class TestValidationPrimitives(unittest.TestCase):
    """Issues and digests are immutable, serializable and deterministic."""

    def test_issue_is_frozen_and_serializable(self):
        issue = ValidationIssue("code_x", "soul.routing", "a message")
        self.assertEqual(issue.severity, Severity.ERROR)
        self.assertEqual(issue.as_dict(), {
            "code": "code_x", "location": "soul.routing",
            "message": "a message", "severity": "error"})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            issue.code = "changed"

    def test_issue_warning_severity(self):
        issue = ValidationIssue("w", "loc", "msg", severity=Severity.WARNING)
        self.assertEqual(issue.as_dict()["severity"], "warning")

    def test_canonical_digest_is_order_independent(self):
        a = canonical_digest({"b": 1, "a": [2, 3]})
        b = canonical_digest({"a": [2, 3], "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        self.assertNotEqual(a, canonical_digest({"a": [2, 4], "b": 1}))

    def test_tokenize_is_lowercase_alphanumeric(self):
        self.assertEqual(tokenize("Keel's SOUL_v2!"), ("keel", "s", "soul", "v2"))


class TestOriginality(unittest.TestCase):
    """Persona prompts are original; verbatim upstream copies are refused."""

    def test_default_prompt_is_original_and_valid(self):
        soul = default_soul()
        self.assertIs(soul.prompt.origin, PromptOrigin.ORIGINAL)
        self.assertEqual(soul.prompt.validate(), ())

    def test_verbatim_copy_is_detected(self):
        upstream = default_soul().prompt.text
        copied = PromptAsset("copied", upstream, PromptOrigin.ORIGINAL)
        self.assertTrue(is_verbatim_copy(copied.text, upstream))
        codes = [i.code for i in copied.validate()]
        self.assertIn("verbatim_copy", codes)
        with self.assertRaises(IdentityContractError):
            assert_original(copied.text, upstream)

    def test_short_overlap_is_not_a_copy(self):
        upstream = " ".join(tokenize(default_soul().prompt.text)[:6])
        candidate = default_soul().prompt.text
        self.assertFalse(is_verbatim_copy(candidate, upstream))
        assert_original(candidate, upstream)

    def test_attributed_adaptation_requires_attribution(self):
        upstream = " ".join(tokenize(default_soul().prompt.text)[:6])
        candidate = default_soul().prompt.text
        missing = PromptAsset("adapted", candidate,
                              PromptOrigin.ATTRIBUTED_ADAPTATION)
        self.assertIn("attribution_missing",
                      {i.code for i in missing.validate()})
        attributed = dataclasses.replace(missing, attribution="Keel original spec")
        self.assertEqual(attributed.validate(), ())

    def test_empty_prompt_rejected(self):
        asset = PromptAsset("empty", "   ", PromptOrigin.ORIGINAL)
        self.assertIn("empty_text", {i.code for i in asset.validate()})

    def test_soul_rejects_copied_prompt(self):
        soul = default_soul()
        copied = PromptAsset("copied", soul.prompt.text, PromptOrigin.ORIGINAL)
        bad = dataclasses.replace(soul, prompt=copied)
        issues = validate_soul(bad)
        self.assertIn("copied_prompt", {i.code for i in issues})


class TestSoulAndRigor(unittest.TestCase):
    """Y4.9: SOUL.md/PERSONA.md sections, rigor contract, original wording."""

    def test_default_soul_valid_and_immutable(self):
        soul = default_soul()
        self.assertEqual(validate_soul(soul), ())
        self.assertEqual(soul.version, "1.0.0")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            soul.agent_id = "other"

    def test_required_sections_enforced(self):
        soul = default_soul()
        partial = dataclasses.replace(
            soul, sections=(SoulSection.IDENTITY, SoulSection.RIGOR))
        codes = {i.code for i in validate_soul(partial)}
        self.assertIn("missing_section", codes)
        self.assertEqual(len([i for i in validate_soul(partial)
                              if i.code == "missing_section"]), 3)

    def test_rigor_rules_nonempty_and_unique(self):
        soul = default_soul()
        self.assertIn("rule_id", DEFAULT_RIGOR_RULES[0].as_dict())
        empty = dataclasses.replace(soul, rigor=())
        self.assertIn("rigor_empty", {i.code for i in validate_soul(empty)})
        dupes = dataclasses.replace(soul, rigor=(DEFAULT_RIGOR_RULES[0],
                                                 DEFAULT_RIGOR_RULES[0]))
        self.assertIn("duplicate_rigor_rule",
                      {i.code for i in validate_soul(dupes)})

    def test_rigor_contract_is_original_and_substantive(self):
        soul = default_soul()
        text = " ".join(r.statement for r in soul.rigor).lower()
        for phrase in ("evidence", "never fabricate", "unknown",
                       "independent", "anchor", "pushback"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_render_is_deterministic_and_sectioned(self):
        soul = default_soul()
        first = render_soul(soul)
        self.assertEqual(first, render_soul(soul))
        for section in SoulSection:
            self.assertIn(section.value, first)
        self.assertIn(soul.agent_id, first)

    def test_soul_digest_is_stable(self):
        self.assertEqual(default_soul().digest(), default_soul().digest())

    def test_empty_agent_id_rejected(self):
        soul = default_soul()
        bad = dataclasses.replace(soul, agent_id="")
        self.assertIn("empty_agent_id", {i.code for i in validate_soul(bad)})


class TestRoutingTable(unittest.TestCase):
    """Y4.9: a deterministic routing table consumable by the router."""

    def setUp(self):
        self.table = RoutingTable(DEFAULT_ROUTING_RULES)

    def test_desktop_prefers_local_when_healthy(self):
        decision = self.table.resolve("desktop.control",
                                      capabilities={"local_desktop_healthy"})
        self.assertIs(decision.target, RouteTarget.LOCAL_DESKTOP)
        self.assertFalse(decision.used_fallback)

    def test_desktop_falls_back_when_local_unhealthy(self):
        decision = self.table.resolve("desktop.control", capabilities=set())
        self.assertIs(decision.target, RouteTarget.GENERAL)
        self.assertTrue(decision.used_fallback)

    def test_dom_prefers_browser_then_local(self):
        browser = self.table.resolve("dom.inspect",
                                     capabilities={"browser_available"})
        self.assertIs(browser.target, RouteTarget.BROWSER)
        local = self.table.resolve("dom.inspect",
                                   capabilities={"local_desktop_healthy"})
        self.assertIs(local.target, RouteTarget.LOCAL_DESKTOP)
        self.assertTrue(local.used_fallback)

    def test_multi_file_code_requires_single_writer(self):
        decision = self.table.resolve(
            "code.multi_file",
            capabilities={"coding_specialist_available", "single_writer"})
        self.assertIs(decision.target, RouteTarget.CODING_SPECIALIST)
        blocked = self.table.resolve("code.multi_file",
                                     capabilities={"coding_specialist_available"})
        self.assertIs(blocked.target, RouteTarget.CONDUCTOR)
        self.assertTrue(blocked.used_fallback)

    def test_unknown_intent_uses_general(self):
        decision = self.table.resolve("something.new")
        self.assertIs(decision.target, RouteTarget.GENERAL)
        self.assertEqual(decision.matched_rule, "")

    def test_resolution_is_priority_ordered_and_input_independent(self):
        intents = ("desktop.control", "dom.inspect", "code.multi_file", "x.y")
        caps = {"local_desktop_healthy", "browser_available",
                "coding_specialist_available", "single_writer"}
        a = [self.table.resolve(i, capabilities=caps) for i in intents]
        b = [RoutingTable(tuple(reversed(self.table.rules))).resolve(
            i, capabilities=caps) for i in intents]
        self.assertEqual(a, b)

    def test_duplicate_intent_is_invalid(self):
        rules = self.table.rules + (self.table.rules[0],)
        codes = {i.code for i in RoutingTable(rules).validate()}
        self.assertIn("duplicate_intent", codes)

    def test_decision_serialization_and_immutability(self):
        decision = self.table.resolve("general")
        self.assertIsInstance(decision, RouteDecision)
        self.assertIn("target", decision.as_dict())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.target = RouteTarget.REFUSE

    def test_soul_delegates_route_resolution(self):
        soul = default_soul()
        self.assertEqual(
            soul.resolve_route("general"),
            soul.routing.resolve("general"))


class TestSignInProbe(unittest.TestCase):
    """Y4.3: one-token first-boot probe with the exact provider error."""

    def test_probe_budget_is_exactly_one(self):
        probe = SignInProbe("openai", "model-x", "PROVIDER_API_KEY")
        self.assertEqual(probe.token_budget, 1)
        self.assertEqual(PROBE_TOKEN_BUDGET, 1)
        self.assertEqual(probe.validate(), ())

    def test_budget_tampering_rejected(self):
        probe = dataclasses.replace(
            SignInProbe("openai", "model-x", "PROVIDER_API_KEY"),
            token_budget=7)
        self.assertIn("budget_must_be_one", {i.code for i in probe.validate()})

    def test_credential_ref_must_not_be_a_secret(self):
        probe = SignInProbe("openai", "model-x",
                            "sk-ABCDEFGHIJKLMNOPQRSTUVWX")
        self.assertIn("credential_ref_is_secret",
                      {i.code for i in probe.validate()})

    def test_success_with_one_token(self):
        result = _clean_result()
        self.assertIs(result.status, ProbeStatus.PASS)
        self.assertIsNone(result.error)
        self.assertEqual(result.tokens_used, 1)
        self.assertEqual(result.validate(), ())

    def test_zero_credit_fails_loudly_with_exact_provider_error(self):
        message = "Your account has insufficient credits for model-x"
        result = _fail_result("insufficient_quota", message)
        self.assertIs(result.status, ProbeStatus.FAIL)
        self.assertEqual(result.error.code, "insufficient_quota")
        self.assertEqual(result.error.message, message)
        loud = result.loud_message()
        for fragment in ("openai", "insufficient_quota", message):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, loud)
        self.assertTrue(is_zero_credit(result.error))

    def test_generic_error_never_replaces_provider_message(self):
        result = _fail_result("billing_hard_limit_reached",
                              "hard limit reached for workspace 42")
        self.assertNotIn("authentication failed", result.loud_message())
        self.assertIn("hard limit reached for workspace 42",
                      result.loud_message())

    def test_budget_exceeded_on_success_response_fails(self):
        probe = SignInProbe("openai", "model-x", "PROVIDER_API_KEY")
        result = evaluate_probe(probe, ProbeResponse(200, tokens_used=5))
        self.assertIs(result.status, ProbeStatus.FAIL)
        self.assertEqual(result.error.code, "probe_budget_exceeded")
        self.assertIn("5", result.loud_message())

    def test_failed_result_missing_error_is_invalid(self):
        result = _fail_result()
        broken = dataclasses.replace(result, error=None)
        self.assertIn("missing_error", {i.code for i in broken.validate()})

    def test_passing_result_with_error_is_invalid(self):
        result = dataclasses.replace(_clean_result(), error=_fail_result().error)
        self.assertIn("unexpected_error", {i.code for i in result.validate()})

    def test_missing_provider_error_text_is_synthesized_loudly(self):
        probe = SignInProbe("openai", "model-x", "PROVIDER_API_KEY")
        result = evaluate_probe(probe, ProbeResponse(500))
        self.assertIs(result.status, ProbeStatus.FAIL)
        self.assertEqual(result.error.code, "http_500")
        self.assertIn("HTTP 500", result.error.message)
        self.assertIn("error_message_missing", result.evidence)

    def test_zero_credit_code_detection_is_case_insensitive(self):
        for code in ("INSUFFICIENT_QUOTA", "credit_balance_exhausted",
                     "payment_required", "quota_exceeded"):
            with self.subTest(code=code):
                self.assertTrue(is_zero_credit(code))
        self.assertFalse(is_zero_credit("rate_limit_exceeded"))

    def test_error_redacts_secret_but_keeps_diagnosis(self):
        raw = "bad key sk-ABCDEFGHIJKLMNOPQRSTUVWX for model-x"
        error = ProviderError("invalid_api_key", raw)
        public = error.public_message()
        self.assertIn("bad key", public)
        self.assertIn("model-x", public)
        self.assertNotIn("sk-ABCDEFGHIJKLMNOPQRSTUVWX", public)
        self.assertEqual(error.message, raw)
        self.assertNotIn("sk-ABCDEFGHIJKLMNOPQRSTUVWX",
                         str(error.as_dict()))
        self.assertIn("sk-ABCDEFGHIJKLMNOPQRSTUVWX",
                      str(error.as_dict(reveal=True)))

    def test_redact_secrets_is_pure(self):
        text = "token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 used"
        redacted = redact_secrets(text)
        self.assertNotIn("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", redacted)
        self.assertEqual(redact_secrets(text), redacted)

    def test_provider_error_is_frozen(self):
        error = ProviderError("x", "y")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            error.code = "z"


class TestFirstBootGate(unittest.TestCase):
    """First boot is fail-closed: only a clean probe allows it."""

    def test_all_pass_allows(self):
        decision = first_boot_decision([_clean_result("openai"),
                                        _clean_result("anthropic")])
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ())

    def test_failed_probe_blocks(self):
        decision = first_boot_decision([_fail_result()])
        self.assertFalse(decision.allowed)
        self.assertTrue(any("insufficient_quota" in r for r in decision.reasons))
        self.assertIsInstance(decision, BootDecision)

    def test_skip_blocks_unless_explicitly_allowed(self):
        probe = SignInProbe("openai", "model-x", "PROVIDER_API_KEY")
        result = skipped_probe(probe, "no credential configured")
        self.assertFalse(first_boot_decision([result]).allowed)
        self.assertTrue(first_boot_decision(
            [result], allow_unverified=True).allowed)

    def test_empty_results_blocks(self):
        decision = first_boot_decision([])
        self.assertFalse(decision.allowed)
        self.assertIn("no_probe_results", decision.as_dict()["reasons"][0])

    def test_reasons_are_sorted_and_serializable(self):
        results = [_fail_result("a_code", "first"),
                   _fail_result("b_code", "second")]
        forward = first_boot_decision(results)
        backward = first_boot_decision(list(reversed(results)))
        self.assertEqual(forward, backward)
        self.assertEqual(list(forward.reasons), sorted(forward.reasons))
        self.assertIn("reasons", forward.as_dict())

    def test_zero_credit_reason_names_the_condition(self):
        decision = first_boot_decision([_fail_result()])
        self.assertTrue(any("zero credit" in r.lower() for r in decision.reasons))


class TestVersionAndBadge(unittest.TestCase):
    """Y4.13: strict VERSION=x.y.z build and honest version badges."""

    def test_valid_versions(self):
        for version in ("1.2.3", "0.0.0", "10.20.30", "1.2.3-rc.1+build.5"):
            with self.subTest(version=version):
                self.assertTrue(is_valid_version(version))
                self.assertEqual(parse_version(version), version)

    def test_invalid_versions_rejected(self):
        for version in ("1.2", "v1.2.3", "1.2.3.4", "", "latest", "1.2.x"):
            with self.subTest(version=version):
                self.assertFalse(is_valid_version(version))
                with self.assertRaises(IdentityContractError):
                    parse_version(version)

    def test_build_command_roundtrip(self):
        command = build_command("1.2.3")
        self.assertEqual(command, "VERSION=1.2.3 build")
        self.assertEqual(parse_build_command(command), "1.2.3")

    def test_build_command_rejects_other_verbs(self):
        for command in ("VERSION=1.2.3 test", "BUILD=1.2.3 build", "build"):
            with self.subTest(command=command):
                with self.assertRaises(IdentityContractError):
                    parse_build_command(command)

    def test_badge_never_claims_clean_without_a_scan(self):
        unverified = VersionBadge("1.2.3", "stable", False)
        self.assertIn("unverified", unverified.text())
        self.assertNotIn("clean", unverified.text())
        verified = VersionBadge("1.2.3", "stable", True)
        self.assertIn("clean", verified.text())
        self.assertIn("1.2.3", verified.text())

    def test_badge_validates_version(self):
        badge = VersionBadge("v1.2", "stable", True)
        self.assertIn("invalid_version", {i.code for i in badge.validate()})


class TestZeroSecretsScan(unittest.TestCase):
    """Y4.13: deterministic secret detection without echoing the secret."""

    def test_clean_artifacts_have_no_findings(self):
        artifacts = (Artifact("app.js", "const answer = 42;"),
                     Artifact("manifest.json", '{"version":"1.2.3"}'))
        self.assertEqual(scan_secrets(artifacts), ())

    def test_api_key_detected_without_echo(self):
        secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
        artifacts = (Artifact("app.js", f'const key = "{secret}";'),)
        findings = scan_secrets(artifacts)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIsInstance(finding, SecretFinding)
        self.assertEqual(finding.artifact, "app.js")
        self.assertEqual(finding.line, 1)
        self.assertNotIn(secret, str(finding.as_dict()))
        self.assertNotIn(secret, ZeroSecretsScan(
            "1.2.3", findings, 1).summary())

    def test_multiple_secret_families_detected(self):
        samples = (
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            "AKIAIOSFODNN7EXAMPLE",
            "AIza" + "A" * 35,
            "-----BEGIN RSA PRIVATE KEY-----",
            "xoxb-123456789012-abcdefghijklmnop",
        )
        for secret in samples:
            with self.subTest(secret=secret[:8]):
                findings = scan_secrets((Artifact("f", f"value={secret}"),))
                self.assertTrue(findings)

    def test_short_token_is_not_a_false_positive(self):
        self.assertEqual(scan_secrets((Artifact("f", "sk-short"),)), ())

    def test_findings_sorted_and_input_independent(self):
        artifacts = (
            Artifact("b.txt", "sk-ABCDEFGHIJKLMNOPQRSTUVWX"),
            Artifact("a.txt", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"),
        )
        forward = scan_secrets(artifacts)
        backward = scan_secrets(tuple(reversed(artifacts)))
        self.assertEqual(forward, backward)
        self.assertEqual([f.artifact for f in forward], ["a.txt", "b.txt"])

    def test_empty_scan_fails_closed(self):
        scan = ZeroSecretsScan("1.2.3", (), 0)
        self.assertFalse(scan.ok)
        scan = ZeroSecretsScan("1.2.3", (), 2)
        self.assertTrue(scan.ok)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            scan.ok = True

    def test_artifact_validation(self):
        self.assertIn("empty_name",
                      {i.code for i in Artifact("", "text").validate()})
        self.assertIn("empty_text",
                      {i.code for i in Artifact("a", "   ").validate()})


class TestReleaseVerification(unittest.TestCase):
    """Y4.13: release gate ties the badge to a real zero-secrets scan."""

    def test_clean_release_passes(self):
        artifacts = (Artifact("app.js", "const answer = 42;"),
                     Artifact("RELEASE-MANIFEST.json", '{"version":"1.2.3"}'))
        verification = verify_release("1.2.3", artifacts)
        self.assertTrue(verification.ok)
        self.assertEqual(verification.checks, ())
        self.assertIn("clean", verification.badge.text())
        self.assertEqual(len(verification.scan.findings), 0)

    def test_secret_blocks_release_and_badge_stays_honest(self):
        artifacts = (Artifact("app.js", "key=sk-ABCDEFGHIJKLMNOPQRSTUVWX"),)
        verification = verify_release("1.2.3", artifacts)
        self.assertFalse(verification.ok)
        self.assertIn("secrets_found", {i.code for i in verification.checks})
        self.assertIn("unverified", verification.badge.text())

    def test_no_artifacts_blocks_release(self):
        verification = verify_release("1.2.3", ())
        self.assertFalse(verification.ok)
        self.assertIn("no_artifacts_scanned",
                      {i.code for i in verification.checks})

    def test_manifest_version_mismatch_blocks(self):
        artifacts = (Artifact("RELEASE-MANIFEST.json", '{"version":"9.9.9"}'),)
        verification = verify_release("1.2.3", artifacts)
        self.assertFalse(verification.ok)
        self.assertIn("manifest_version_mismatch",
                      {i.code for i in verification.checks})

    def test_invalid_version_blocks(self):
        verification = verify_release("latest",
                                      (Artifact("a", "clean"),))
        self.assertFalse(verification.ok)
        self.assertIn("invalid_version",
                      {i.code for i in verification.checks})

    def test_verification_is_frozen_and_reproducible(self):
        artifacts = (Artifact("a", "clean"),)
        a = verify_release("1.2.3", artifacts)
        b = verify_release("1.2.3", artifacts)
        self.assertEqual(a, b)
        self.assertIsInstance(a, ReleaseVerification)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.ok = False


class TestPurityAndDeterminism(unittest.TestCase):
    """The module is a stdlib-only, immutable, host-free policy surface."""

    def test_only_stdlib_imports(self):
        tree = ast.parse(Path(ic.__file__).read_text(encoding="utf-8"))
        allowed = {"__future__", "dataclasses", "enum", "hashlib", "json",
                   "re", "typing", "collections.abc"}
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertTrue(found <= allowed, f"unexpected imports: {found - allowed}")

    def test_no_host_io_or_clock_calls(self):
        tree = ast.parse(Path(ic.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.id if isinstance(node.func, ast.Name)
                        else node.func.attr if isinstance(node.func, ast.Attribute)
                        else "")
                self.assertNotIn(name, {"open", "input", "print", "exit"})

    def test_public_collections_are_immutable_tuples(self):
        soul = default_soul()
        for result in (soul.validate(), soul.rigor, soul.sections,
                       scan_secrets((Artifact("a", "clean"),)),
                       first_boot_decision([_clean_result()]).reasons):
            self.assertIsInstance(result, tuple)

    def test_validation_issues_are_sorted(self):
        def key(issue):
            return (issue.code, issue.location, issue.message)
        for result in (default_soul().validate(),
                       verify_release("bad", ()).checks,
                       RoutingTable((RoutingRule("a", RouteTarget.GENERAL,
                                                 "a", RouteTarget.GENERAL, (), 1, ""),
                                     RoutingRule("a", RouteTarget.GENERAL,
                                                 "b", RouteTarget.GENERAL, (), 2, ""))).validate()):
            self.assertEqual(list(result), sorted(result, key=key))


if __name__ == "__main__":
    unittest.main(verbosity=2)

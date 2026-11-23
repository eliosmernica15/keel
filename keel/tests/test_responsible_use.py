"""D5.1-D5.5 (P0) - responsible-use disclosures, checklist, disclaimer and
host-sandbox-failure rule.

Stdlib-only tests (``unittest``) covering:

* typed disclosure statements (executes model-generated code; sandboxing is
  risk reduction, not a guarantee of isolation),
* the responsible-use checklist and wizard offers,
* the no-warranty / no-liability data referencing the license,
* the builder's fail-closed host-sandbox-failure rule (retry unchanged with
  the narrowest escalation, evidence required, never bypass tests or the
  product sandbox), and
* the checked-in user-facing RESPONSIBLE-USE.md being derived from that data
  with no false security guarantees.

Run from the worktree root::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_responsible_use.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path

import keel.responsible_use as ru
from keel.responsible_use import (
    BUILDER_STOP_RULES,
    CHECKLIST,
    DISCLOSURES,
    EXECUTION_DISCLOSURE,
    SANDBOX_LIMITS_DISCLOSURE,
    WIZARD_OFFERS,
    WARRANTY_DISCLAIMER,
    BlockedResource,
    ChecklistItem,
    Decision,
    Disclosure,
    Escalation,
    FailureDecision,
    SandboxFailure,
    StopRule,
    WizardOffer,
    disclosure_by_id,
    evaluate_failure,
    fail_closed,
    narrowest_escalation,
    render_builder_stop_rules,
    render_document,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "keel" / "docs" / "RESPONSIBLE-USE.md"

# Phrases that would turn the risk-reduction disclosure into a false promise.
# Kept local to the tests on purpose: an identical copy in the module would
# make the check tautological.
FORBIDDEN_GUARANTEE_PHRASES = (
    "guaranteed isolation",
    "guarantees isolation",
    "fully isolated",
    "completely safe",
    "100% safe",
    "totally secure",
    "no risk",
    "cannot damage",
    "will not damage",
    "safe to run untrusted",
    "sandbox guarantees",
    "is guaranteed to",
    "zero chance",
)


def _flatten(value):
    """Yield every string inside nested dataclasses / tuples / dicts."""
    if isinstance(value, str):
        yield value
    elif dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            yield from _flatten(getattr(value, field.name))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten(key)
            yield from _flatten(item)
    elif isinstance(value, (tuple, list, frozenset, set)):
        for item in value:
            yield from _flatten(item)


def _all_copy():
    return list(_flatten((DISCLOSURES, CHECKLIST, WIZARD_OFFERS,
                          WARRANTY_DISCLAIMER, BUILDER_STOP_RULES)))


class TestDisclosureStatements(unittest.TestCase):
    """D5.1 / D5.2 are typed, immutable, plain data."""

    def test_disclosures_are_typed_frozen_records(self):
        self.assertTrue(DISCLOSURES)
        self.assertEqual(len({d.id for d in DISCLOSURES}), len(DISCLOSURES))
        for disclosure in DISCLOSURES:
            with self.subTest(id=disclosure.id):
                self.assertIsInstance(disclosure, Disclosure)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    disclosure.text = "changed"
                payload = disclosure.as_dict()
                self.assertEqual(payload["id"], disclosure.id)
                self.assertEqual(payload["feature_id"], disclosure.feature_id)
                json.dumps(payload)  # plain JSON-serialisable data

    def test_d51_plain_execution_statement_is_complete(self):
        self.assertEqual(EXECUTION_DISCLOSURE.feature_id, "D5.1")
        text = EXECUTION_DISCLOSURE.text.lower()
        for phrase in ("executes", "model-generated", "plugins", "network",
                       "processes", "credentials", "files", "defects",
                       "misconfiguration", "malicious input",
                       "untrusted plugins", "damage"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_d52_states_risk_reduction_and_no_sole_control(self):
        self.assertEqual(SANDBOX_LIMITS_DISCLOSURE.feature_id, "D5.2")
        self.assertIn(
            "Sandboxing, approvals and permissions reduce risk but do not "
            "guarantee isolation",
            SANDBOX_LIMITS_DISCLOSURE.text,
        )
        self.assertIn("sole control", SANDBOX_LIMITS_DISCLOSURE.text.lower())

    def test_lookup_by_id_is_exact_and_fails_closed(self):
        self.assertIs(disclosure_by_id(EXECUTION_DISCLOSURE.id),
                      EXECUTION_DISCLOSURE)
        self.assertIs(disclosure_by_id(SANDBOX_LIMITS_DISCLOSURE.id),
                      SANDBOX_LIMITS_DISCLOSURE)
        self.assertIsNone(disclosure_by_id("does-not-exist"))


class TestResponsibleUseChecklist(unittest.TestCase):
    """D5.3 checklist plus the two onboarding wizard offers."""

    def test_checklist_items_are_typed_frozen_records(self):
        self.assertGreaterEqual(len(CHECKLIST), 5)
        self.assertEqual(len({i.id for i in CHECKLIST}), len(CHECKLIST))
        for item in CHECKLIST:
            with self.subTest(id=item.id):
                self.assertIsInstance(item, ChecklistItem)
                self.assertEqual(item.feature_id, "D5.3")
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    item.title = "changed"

    def test_all_five_responsible_use_points_are_present(self):
        text = " ".join(i.title + " " + i.text for i in CHECKLIST).lower()
        for phrase in ("least privilege", "disposable", "vm", "container",
                       "backup", "credential", "review", "plugin",
                       "config", "proposed command"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_wizard_offers_map_to_checklist_items(self):
        ids = {i.id for i in CHECKLIST}
        self.assertEqual(len(WIZARD_OFFERS), 2)
        self.assertEqual({o.label for o in WIZARD_OFFERS}, {
            "Run in disposable container",
            "Create backup before first agent run",
        })
        for offer in WIZARD_OFFERS:
            with self.subTest(id=offer.id):
                self.assertIsInstance(offer, WizardOffer)
                self.assertIn(offer.checklist_item_id, ids)
        self.assertTrue(any(o.source_id == "V17" for o in WIZARD_OFFERS))


class TestWarrantyDisclaimer(unittest.TestCase):
    """D5.4 data: no warranty, no liability, reference to the license."""

    def test_disclaimer_data_is_complete(self):
        self.assertEqual(WARRANTY_DISCLAIMER.feature_id, "D5.4")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            WARRANTY_DISCLAIMER.no_warranty = "changed"
        self.assertIn("AS IS", WARRANTY_DISCLAIMER.no_warranty)
        self.assertIn("WITHOUT WARRANTY", WARRANTY_DISCLAIMER.no_warranty)
        self.assertIn("NOT LIABLE", WARRANTY_DISCLAIMER.no_liability)
        self.assertIn("license", WARRANTY_DISCLAIMER.license_reference.lower())
        self.assertIn("EULA", WARRANTY_DISCLAIMER.license_reference)
        self.assertIn("G5", WARRANTY_DISCLAIMER.review_status)
        self.assertIn("review", WARRANTY_DISCLAIMER.review_status.lower())

    def test_rendered_paragraphs_contain_every_part(self):
        paragraphs = WARRANTY_DISCLAIMER.paragraphs()
        for part in (WARRANTY_DISCLAIMER.no_warranty,
                     WARRANTY_DISCLAIMER.no_liability,
                     WARRANTY_DISCLAIMER.license_reference,
                     WARRANTY_DISCLAIMER.review_status):
            with self.subTest(part=part[:24]):
                self.assertIn(part, paragraphs)
                self.assertIn(part, WARRANTY_DISCLAIMER.text())


class TestNoFalseSecurityGuarantees(unittest.TestCase):
    """Copy never promotes sandboxing or permissions into a promise."""

    def test_no_affirmative_guarantee_phrase_in_any_statement(self):
        for copy in _all_copy():
            for phrase in FORBIDDEN_GUARANTEE_PHRASES:
                with self.subTest(phrase=phrase):
                    self.assertNotIn(phrase, copy.lower())

    def test_limiting_wording_is_present_in_rendered_copy(self):
        for renderer in (ru.render_safety_notice, ru.render_known_limits,
                         render_document):
            with self.subTest(renderer=renderer.__name__):
                text = renderer()
                self.assertIn("do not guarantee isolation", text.lower())
                self.assertIn("sole control", text.lower())
        self.assertIn("reduce risk", ru.render_safety_notice().lower())

    def test_disclaimer_is_not_a_security_promise(self):
        text = WARRANTY_DISCLAIMER.text().lower()
        self.assertIn("without warranty", text)
        self.assertIn("not liable", text)


class TestHostSandboxFailureRule(unittest.TestCase):
    """D5.5: fail closed, require evidence, narrowest escalation only."""

    def test_stop_rules_cover_the_builder_stop_list(self):
        self.assertTrue(BUILDER_STOP_RULES)
        self.assertEqual(len({r.id for r in BUILDER_STOP_RULES}),
                         len(BUILDER_STOP_RULES))
        expected = {
            "require-sandbox-evidence": "evidence",
            "retry-unchanged": "unchanged",
            "narrowest-escalation-only": "narrowest",
            "never-bypass-tests": "test",
            "never-bypass-product-sandbox": "sandbox",
            "fail-closed-on-unknown": "fail closed",
        }
        ids = {r.id for r in BUILDER_STOP_RULES}
        for rule_id, keyword in expected.items():
            with self.subTest(rule_id=rule_id):
                self.assertIn(rule_id, ids)
                rule = next(r for r in BUILDER_STOP_RULES if r.id == rule_id)
                self.assertIsInstance(rule, StopRule)
                self.assertEqual(rule.feature_id, "D5.5")
                self.assertIn(keyword, rule.text.lower())
        for rule_text in render_builder_stop_rules().splitlines():
            if rule_text.strip():
                self.assertIn(rule_text.strip().lstrip("- "),
                              [r.text for r in BUILDER_STOP_RULES])

    def test_narrowest_escalation_mapping(self):
        self.assertEqual(narrowest_escalation(BlockedResource.CREDENTIALS),
                         Escalation.CREDENTIALS)
        self.assertEqual(narrowest_escalation(BlockedResource.NETWORK),
                         Escalation.NETWORK)
        self.assertEqual(narrowest_escalation(BlockedResource.IPC),
                         Escalation.IPC)
        for unknown in (BlockedResource.NONE, BlockedResource.OTHER,
                        "dns-server", "", None):
            with self.subTest(unknown=unknown):
                self.assertEqual(narrowest_escalation(unknown), Escalation.NONE)

    def test_no_broad_or_off_switch_escalation_is_representable(self):
        values = {e.value.lower() for e in Escalation}
        for forbidden in ("all", "full", "unbounded", "unsandbox", "off",
                          "every", "bypass"):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(any(forbidden in v for v in values))

    def _failure(self, **overrides):
        kwargs = {
            "command": "pytest -q keel/tests/test_commands.py",
            "blocked_resource": BlockedResource.CREDENTIALS,
            "evidence": ("host sandbox denied env credential read: EPERM",),
        }
        kwargs.update(overrides)
        return SandboxFailure(**kwargs)

    def test_proven_dev_sandbox_block_retries_unchanged(self):
        for resource in (BlockedResource.CREDENTIALS, BlockedResource.NETWORK,
                         BlockedResource.IPC):
            with self.subTest(resource=resource.value):
                failure = self._failure(blocked_resource=resource)
                decision = evaluate_failure(
                    failure, narrowest_escalation(resource))
                self.assertIsInstance(decision, FailureDecision)
                self.assertEqual(decision.decision, Decision.RETRY)
                self.assertTrue(decision.allowed)
                self.assertFalse(decision.is_stop)
                self.assertEqual(decision.escalation,
                                 narrowest_escalation(resource))
                self.assertEqual(decision.evidence, failure.evidence)
                self.assertIn("unchanged", decision.reason.lower())
                self.assertIn("narrowest", decision.reason.lower())
                json.dumps(decision.as_dict())

    def test_fail_closed_cases_never_escalate(self):
        cases = {
            "no evidence": (self._failure(evidence=()), Escalation.CREDENTIALS),
            "blank evidence": (
                self._failure(evidence=("", "   ")), Escalation.CREDENTIALS),
            "unknown cause": (
                self._failure(blocked_resource="dns-server"),
                Escalation.CREDENTIALS),
            "no block": (
                self._failure(blocked_resource=BlockedResource.NONE),
                Escalation.CREDENTIALS),
            "other cause": (
                self._failure(blocked_resource=BlockedResource.OTHER),
                Escalation.CREDENTIALS),
            "test failure": (
                self._failure(test_failure=True), Escalation.CREDENTIALS),
            "bypass tests": (
                self._failure(bypass_tests=True), Escalation.CREDENTIALS),
            "bypass product sandbox": (
                self._failure(bypass_product_sandbox=True),
                Escalation.CREDENTIALS),
            "changed command": (
                self._failure(retry_command="pytest -q --no-sandbox"),
                Escalation.CREDENTIALS),
            "no escalation requested": (self._failure(), Escalation.NONE),
            "broader escalation": (self._failure(), Escalation.NETWORK),
            "wrong escalation": (self._failure(), Escalation.IPC),
            "all escalation": (self._failure(), "all"),
            "full unsandbox": (self._failure(), "full-unsandboxed"),
        }
        for name, (failure, escalation) in cases.items():
            with self.subTest(case=name):
                decision = evaluate_failure(failure, escalation)
                self.assertEqual(decision.decision, Decision.STOP)
                self.assertFalse(decision.allowed)
                self.assertTrue(decision.is_stop)
                self.assertEqual(decision.escalation, Escalation.NONE)
                self.assertEqual(decision.evidence, ())
                self.assertTrue(decision.reason.strip())
                json.dumps(decision.as_dict())

    def test_bypass_attempt_with_perfect_evidence_still_stops(self):
        failure = self._failure(
            test_failure=True,
            bypass_tests=True,
            bypass_product_sandbox=True,
            retry_command="pytest -q --disable-product-sandbox",
        )
        decision = evaluate_failure(failure, Escalation.CREDENTIALS)
        self.assertTrue(decision.is_stop)
        self.assertEqual(decision.escalation, Escalation.NONE)
        self.assertIn("test", decision.reason.lower())

    def test_fail_closed_helper_is_a_stop_without_escalation(self):
        decision = fail_closed("no evidence of a dev-sandbox cause")
        self.assertTrue(decision.is_stop)
        self.assertEqual(decision.escalation, Escalation.NONE)
        self.assertEqual(decision.evidence, ())
        self.assertIn("no evidence", decision.reason)

    def test_decisions_and_failures_are_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self._failure().command = "other"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fail_closed("x").reason = "y"


class TestUserFacingDocument(unittest.TestCase):
    """RESPONSIBLE-USE.md is real prose generated from the typed data."""

    def test_document_exists_and_matches_renderer_exactly(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        actual = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertEqual(actual, render_document())

    def test_document_has_readable_sections(self):
        text = render_document()
        for heading in ("# Keel Responsible Use and Safety Notice",
                        "## What Keel can do",
                        "## Before your first agent run",
                        "## Warranty and liability",
                        "## Known limits",
                        "## How we handle host sandbox failures"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        self.assertIn("first-run", text.lower())
        self.assertIn("known-limits", text.lower())

    def test_document_contains_all_typed_copy(self):
        text = render_document()
        for copy in _all_copy():
            if len(copy) > 40:  # long-form paragraphs and checklist details
                with self.subTest(copy=copy[:40]):
                    self.assertIn(copy, text)
        self.assertIn(EXECUTION_DISCLOSURE.text, text)
        self.assertIn(SANDBOX_LIMITS_DISCLOSURE.text, text)

    def test_document_has_no_false_guarantees(self):
        text = render_document().lower()
        for phrase in FORBIDDEN_GUARANTEE_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, text)


class TestPurity(unittest.TestCase):
    """The policy module is stdlib-only and cannot touch the host."""

    def test_no_host_or_network_imports(self):
        source = Path(ru.__file__).read_text(encoding="utf-8")
        for forbidden in ("import os", "import socket", "import subprocess",
                          "import pathlib", "open(", "urllib",
                          "import requests", "import time", "import random"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

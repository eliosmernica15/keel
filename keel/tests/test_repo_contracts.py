"""P0 repository-contract tests: pure, stdlib-only, no host I/O.

Covers the four implemented ``not_started`` P0 registry rows:

* **Y5.4** -- signed webhook headers, five-minute freshness, constant-time
  comparison, and unconditional 401 rejection when no secret is configured;
* **Y6.1** -- evidence-document cross-walk with uncovered/missing/out-of-scope
  rows and dangling plan-ID detection;
* **Y6.2** -- ``.verify-*``/``.build`` detection, ignore patterns, publish
  allowlist and artifact exclusion (never deletion);
* **Z4** -- a write-ahead turn journal with single-record atomic appends, a
  hash chain, torn-tail recovery and the exact "retry or skip" resume point.

Every structural anomaly fails closed.  An AST guard proves the module imports
only stdlib pure modules and performs no filesystem, process, clock, network,
environment or chance operation.  The journal uses an in-memory sink only.

Run from the worktree root::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_repo_contracts.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import unittest
from pathlib import Path

import keel.repo_contracts as rc
from keel.repo_contracts import (
    ACTION_EXCLUDE_FROM_PUBLISH,
    ACTION_IGNORE,
    ACTION_PUBLISH,
    ACTION_RETRY,
    ACTION_SKIP,
    ARTIFACT_DIR_NAMES,
    ARTIFACT_DIR_PREFIX,
    DEFAULT_MAX_AGE_SECONDS,
    FEATURE_IDS,
    GENESIS_DIGEST,
    GITIGNORE_PATTERNS,
    MAX_JOURNAL_BYTES,
    OUT_OF_SCOPE_DOCS,
    PROMPT_TEXT,
    REQUIRED_EVIDENCE_DOCS,
    SIGNATURE_HEADER,
    SIGNATURE_ALGORITHM,
    STATUS_ACCEPT,
    STATUS_EMPTY,
    STATUS_MAPPED,
    STATUS_MISSING,
    STATUS_REJECT,
    STATUS_UNCOVERED,
    TIMESTAMP_HEADER,
    ArtifactAllowlist,
    ContractValidationError,
    CrossWalk,
    InterruptedTool,
    Journal,
    MemorySink,
    RecoveryAction,
    RecoveryDescriptor,
    WebhookVerifier,
    artifact_disposition,
    build_cross_walk,
    classify_path,
    cross_walk_dict,
    filter_publishable,
    gitignore_patterns,
    interrupted_tool_prompt,
    is_allowed,
    is_publishable,
    make_allowlist,
    recover,
    resume_journal,
    scan_artifacts,
    secret_configured,
    sign_webhook,
    validate_artifact_scan,
    verify_cross_walk,
    verify_evidence_documents,
    verify_webhook,
    webhook_headers,
)

SECRET = "whsec_test_secret_9f8e7d"
NOW = 1_700_000_000


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _signed(body: bytes, timestamp: int = NOW, secret: str = SECRET) -> dict:
    return webhook_headers(body, secret, timestamp)


def _docs(**extra):
    """A complete, consistent document snapshot for the cross-walk."""
    docs = {name: "# Evidence\n\nTracked against Y6.1 and Y6.2.\n"
            for name in REQUIRED_EVIDENCE_DOCS}
    docs.update(extra)
    return docs


KNOWN_IDS = ("Y5.4", "Y6.1", "Y6.2", "Z4", "D7.1", "C13.1")


def _mutate_line(data: bytes, index: int, change) -> bytes:
    lines = data.rstrip(b"\n").split(b"\n")
    record = json.loads(lines[index].decode("utf-8"))
    change(record)
    lines[index] = json.dumps(record, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode("utf-8")
    return b"\n".join(lines) + b"\n"


class TestFeatureAndPurity(unittest.TestCase):
    """The module is pure, deterministic, additive and stdlib-only."""

    def test_registry_ids_declared(self):
        self.assertEqual(tuple(FEATURE_IDS), ("Y5.4", "Y6.1", "Y6.2", "Z4"))

    def test_public_api_exports_exist(self):
        for name in rc.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(rc, name))

    def test_imports_are_stdlib_only(self):
        source = Path(rc.__file__).read_text(encoding="utf-8")
        allowed = {"__future__", "dataclasses", "enum", "hashlib", "hmac",
                   "json", "re", "typing"}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    with self.subTest(module=alias.name):
                        self.assertIn(alias.name.split(".")[0], allowed)
            elif isinstance(node, ast.ImportFrom):
                with self.subTest(module=node.module):
                    self.assertIn((node.module or "").split(".")[0], allowed)

    def test_no_host_effects_in_source(self):
        source = Path(rc.__file__).read_text(encoding="utf-8")
        forbidden_names = {
            "open", "unlink", "rmtree", "remove", "rmdir", "system", "popen",
            "spawn", "spawnl", "fork", "exec", "execv", "sleep", "random",
            "choice", "urlopen", "socket", "write_text", "read_text", "mkdir",
            "replace", "getenv", "environ",
        }
        forbidden_modules = {
            "os", "subprocess", "socket", "time", "random", "shutil",
            "pathlib", "tempfile", "multiprocessing", "urllib", "requests",
        }
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                target = node.func
                name = target.id if isinstance(target, ast.Name) else (
                    target.attr if isinstance(target, ast.Attribute) else "")
                with self.subTest(call=name):
                    self.assertNotIn(name, forbidden_names)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([alias.name for alias in node.names]
                        if isinstance(node, ast.Import) else [node.module or ""])
                for module in mods:
                    with self.subTest(module=module):
                        self.assertNotIn(module.split(".")[0], forbidden_modules)

    def test_errors_are_value_errors(self):
        self.assertTrue(issubclass(ContractValidationError, ValueError))
        with self.assertRaises(ValueError):
            sign_webhook(b"body", "", NOW)

    def test_y6_4_is_not_implemented_here(self):
        self.assertNotIn("Y6.4", FEATURE_IDS)
        # Y6.4 is owner-gated (G1) and conflicts with private source; it is
        # only mentioned in the docstring as explicitly out of scope.
        self.assertIn("Y6.4", rc.__doc__)
        self.assertIn("owner-gated", rc.__doc__)


# ---------------------------------------------------------------------------
# Y5.4 -- webhook signature headers and no-secret rejection
# ---------------------------------------------------------------------------


class TestWebhookSignatures(unittest.TestCase):

    def test_header_names_and_algorithm(self):
        self.assertEqual(SIGNATURE_HEADER, "X-Webhook-Signature")
        self.assertEqual(TIMESTAMP_HEADER, "X-Webhook-Timestamp")
        self.assertEqual(SIGNATURE_ALGORITHM, "sha256")
        self.assertEqual(DEFAULT_MAX_AGE_SECONDS, 300)
        self.assertEqual(STATUS_ACCEPT, 200)
        self.assertEqual(STATUS_REJECT, 401)

    def test_signature_is_hex_hmac_over_timestamp_dot_raw_body(self):
        body = b'{"event":"ping"}\xc3\xa9'
        headers = _signed(body, NOW - 7)
        message = str(NOW - 7).encode("ascii") + b"." + body
        expected = hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()
        self.assertEqual(headers[SIGNATURE_HEADER], expected)
        self.assertRegex(headers[SIGNATURE_HEADER], r"^[0-9a-f]{64}$")
        self.assertEqual(headers[TIMESTAMP_HEADER], str(NOW - 7))
        self.assertEqual(set(headers), {SIGNATURE_HEADER, TIMESTAMP_HEADER})

    def test_verify_round_trip(self):
        body = b"raw-body"
        decision = verify_webhook(_signed(body), body, secret=SECRET, now=NOW)
        self.assertEqual(decision.as_dict(),
                         {"ok": True, "status": 200, "reason": "verified"})

    def test_no_secret_rejects_every_request(self):
        body = b"attack"
        forged = {
            SIGNATURE_HEADER: "0" * 64,
            TIMESTAMP_HEADER: str(NOW),
        }
        for blank in (None, "", "   ", "\t\n", 0, [], object()):
            for headers in (forged, _signed(body), {},
                            {SIGNATURE_HEADER.lower(): "a" * 64,
                             TIMESTAMP_HEADER.lower(): str(NOW)}):
                with self.subTest(blank=blank, headers=headers):
                    decision = verify_webhook(headers, body,
                                              secret=blank, now=NOW)
                    self.assertFalse(decision.ok)
                    self.assertEqual(decision.status, 401)
        self.assertFalse(secret_configured(None))
        self.assertFalse(secret_configured("  "))
        self.assertTrue(secret_configured(SECRET))

    def test_no_secret_verifier_cannot_sign_but_always_rejects(self):
        verifier = WebhookVerifier(None)
        with self.assertRaises(ContractValidationError):
            verifier.headers(b"body", NOW)
        self.assertEqual(verifier.verify(_signed(b"body"), b"body",
                                         now=NOW).status, 401)

    def test_missing_headers_rejected(self):
        body = b"body"
        signed = _signed(body)
        for headers in ({}, {SIGNATURE_HEADER: signed[SIGNATURE_HEADER]},
                        {TIMESTAMP_HEADER: signed[TIMESTAMP_HEADER]}):
            with self.subTest(headers=headers):
                self.assertEqual(
                    verify_webhook(headers, body, secret=SECRET, now=NOW).status,
                    401)

    def test_malformed_signature_rejected(self):
        body = b"body"
        for signature in ("", "sha256=" + "a" * 64, "a" * 63, "a" * 65,
                          "g" * 64, "a" * 64 + "\n", "A" * 63 + "z"):
            with self.subTest(signature=signature):
                headers = {SIGNATURE_HEADER: signature,
                           TIMESTAMP_HEADER: str(NOW)}
                decision = verify_webhook(headers, body, secret=SECRET, now=NOW)
                self.assertFalse(decision.ok)
                self.assertEqual(decision.reason, "bad_signature")

    def test_uppercase_hex_signature_accepted(self):
        body = b"body"
        signed = _signed(body)
        headers = dict(signed)
        headers[SIGNATURE_HEADER] = signed[SIGNATURE_HEADER].upper()
        self.assertTrue(verify_webhook(headers, body, secret=SECRET, now=NOW).ok)

    def test_freshness_window_is_five_minutes_both_directions(self):
        body = b"body"
        for delta in (-300, 0, 300):
            with self.subTest(delta=delta):
                self.assertTrue(verify_webhook(
                    _signed(body, NOW + delta), body, secret=SECRET,
                    now=NOW).ok)
        for delta in (-301, -100_000, 301, 100_000):
            with self.subTest(delta=delta):
                decision = verify_webhook(_signed(body, NOW + delta), body,
                                          secret=SECRET, now=NOW)
                self.assertFalse(decision.ok)
                self.assertEqual(decision.reason, "stale_timestamp")

    def test_tampered_body_and_timestamp_rejected(self):
        signed = _signed(b"original")
        self.assertFalse(verify_webhook(signed, b"tampered", secret=SECRET,
                                        now=NOW).ok)
        shifted = {SIGNATURE_HEADER: signed[SIGNATURE_HEADER],
                   TIMESTAMP_HEADER: str(NOW - 1)}
        self.assertFalse(verify_webhook(shifted, b"original", secret=SECRET,
                                        now=NOW).ok)

    def test_malformed_timestamps_rejected(self):
        body = b"body"
        for value in ("", "abc", "-1", "+1", "1.0", "17 00000000",
                      "9" * 20, "0x10"):
            with self.subTest(value=value):
                headers = {SIGNATURE_HEADER: sign_webhook(body, SECRET, NOW),
                           TIMESTAMP_HEADER: value}
                decision = verify_webhook(headers, body, secret=SECRET, now=NOW)
                self.assertFalse(decision.ok)
                self.assertIn(decision.reason, ("bad_timestamp", "stale_timestamp"))

    def test_duplicate_or_non_string_headers_rejected(self):
        body = b"body"
        signed = _signed(body)
        for headers in (
            {SIGNATURE_HEADER: signed[SIGNATURE_HEADER],
             SIGNATURE_HEADER.lower(): signed[SIGNATURE_HEADER],
             TIMESTAMP_HEADER: str(NOW)},
            {SIGNATURE_HEADER: signed[SIGNATURE_HEADER],
             TIMESTAMP_HEADER: str(NOW), 7: "x"},
            {SIGNATURE_HEADER: signed[SIGNATURE_HEADER],
             TIMESTAMP_HEADER: str(NOW), "X-Other": 7},
        ):
            with self.subTest(headers=headers):
                decision = verify_webhook(headers, body, secret=SECRET, now=NOW)
                self.assertFalse(decision.ok)
                self.assertIn(decision.reason,
                              ("invalid_header", "ambiguous_header"))

    def test_case_insensitive_header_names_accepted(self):
        body = b"body"
        signed = _signed(body)
        headers = {key.lower(): value for key, value in signed.items()}
        self.assertTrue(verify_webhook(headers, body, secret=SECRET, now=NOW).ok)

    def test_optional_header_whitespace_is_normalized(self):
        body = b"body"
        signed = _signed(body)
        headers = {
            " " + SIGNATURE_HEADER + " ": "  " + signed[SIGNATURE_HEADER] + "  ",
            TIMESTAMP_HEADER: "  " + str(NOW) + "  ",
        }
        self.assertTrue(verify_webhook(headers, body, secret=SECRET, now=NOW).ok)

    def test_structural_misuse_raises(self):
        signed = _signed(b"body")
        for headers in (None, [], "header"):
            with self.subTest(headers=headers), self.assertRaises(
                    ContractValidationError):
                verify_webhook(headers, b"body", secret=SECRET, now=NOW)
        for body in ("body", None, 7):
            with self.subTest(body=body), self.assertRaises(ContractValidationError):
                verify_webhook(signed, body, secret=SECRET, now=NOW)
        for now in (True, -1, "1", None):
            with self.subTest(now=now), self.assertRaises(ContractValidationError):
                verify_webhook(signed, b"body", secret=SECRET, now=now)
        for max_age in (0, -1, True, 1.5, 100_000):
            with self.subTest(max_age=max_age), self.assertRaises(
                    ContractValidationError):
                verify_webhook(signed, b"body", secret=SECRET, now=NOW,
                               max_age=max_age)

    def test_comparison_is_constant_time(self):
        source = Path(rc.__file__).read_text(encoding="utf-8")
        self.assertIn("hmac.compare_digest(expected, signature)", source)
        self.assertIn("import hmac", source)


# ---------------------------------------------------------------------------
# Y6.1 -- evidence-document cross-walk
# ---------------------------------------------------------------------------


class TestEvidenceCrossWalk(unittest.TestCase):

    def test_required_doc_set_and_out_of_scope(self):
        self.assertEqual(len(REQUIRED_EVIDENCE_DOCS), 17)
        self.assertEqual(len(set(REQUIRED_EVIDENCE_DOCS)), 17)
        self.assertIn("feature-checklist.md", REQUIRED_EVIDENCE_DOCS)
        self.assertIn("interface-spec.md", REQUIRED_EVIDENCE_DOCS)
        self.assertIn("llm-development-roadmap.md", REQUIRED_EVIDENCE_DOCS)
        for doc in OUT_OF_SCOPE_DOCS:
            self.assertNotIn(doc, REQUIRED_EVIDENCE_DOCS)
        self.assertIn("training-data-plan.md", OUT_OF_SCOPE_DOCS)
        self.assertIn("model-architecture-proposal.md", OUT_OF_SCOPE_DOCS)

    def test_complete_snapshot_has_no_errors(self):
        walk = build_cross_walk(_docs(), KNOWN_IDS)
        self.assertIsInstance(walk, CrossWalk)
        self.assertEqual(verify_cross_walk(walk), ())
        self.assertEqual(verify_evidence_documents(_docs(), KNOWN_IDS), ())
        self.assertEqual(len(walk.rows), len(REQUIRED_EVIDENCE_DOCS))
        self.assertTrue(all(row.status == STATUS_MAPPED for row in walk.rows))
        self.assertEqual(walk.missing, ())
        self.assertEqual(walk.uncovered, ())

    def test_out_of_scope_documents_are_ignored(self):
        docs = _docs(**{name: "no plan ids here" for name in OUT_OF_SCOPE_DOCS})
        walk = build_cross_walk(docs, KNOWN_IDS)
        self.assertEqual(walk.out_of_scope_ignored, tuple(sorted(OUT_OF_SCOPE_DOCS)))
        self.assertEqual(verify_cross_walk(walk), ())
        self.assertTrue(all(row.doc not in OUT_OF_SCOPE_DOCS for row in walk.rows))

    def test_missing_required_document_becomes_a_row(self):
        docs = _docs()
        docs.pop("test-plan.md")
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows if row.doc == "test-plan.md")
        self.assertEqual(row.status, STATUS_MISSING)
        self.assertEqual(row.plan_ids, ())
        self.assertEqual(walk.missing, ("test-plan.md",))
        self.assertEqual(len(walk.uncovered), 1)
        errors = verify_cross_walk(walk)
        self.assertEqual(len(errors), 1)
        self.assertIn("test-plan.md", errors[0])

    def test_document_without_plan_ids_becomes_uncovered_row(self):
        docs = _docs()
        docs["feature-checklist.md"] = "# Checklist\n\nNo identifiers.\n"
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows if row.doc == "feature-checklist.md")
        self.assertEqual(row.status, STATUS_UNCOVERED)
        self.assertIn("feature-checklist.md", " ".join(verify_cross_walk(walk)))

    def test_empty_document_is_reported(self):
        docs = _docs(**{"interface-spec.md": "   \n\t"})
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows if row.doc == "interface-spec.md")
        self.assertEqual(row.status, STATUS_EMPTY)
        self.assertEqual(verify_cross_walk(walk) != (), True)

    def test_unknown_plan_id_references_are_inconsistencies(self):
        docs = _docs(**{"test-plan.md": "Covers Y6.1 and Q9.9 (fake).\n"})
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows if row.doc == "test-plan.md")
        self.assertEqual(row.status, STATUS_MAPPED)
        self.assertEqual(row.plan_ids, ("Y6.1",))
        self.assertEqual(row.unknown_ids, ("Q9.9",))
        self.assertTrue(any("Q9.9" in error for error in verify_cross_walk(walk)))

    def test_plan_id_extraction_handles_punctuation_and_dedupes(self):
        docs = _docs(**{"test-plan.md": "Y6.1, (D7.1) Z4! Y6.1 Y6.1; Y6.1x.\n"})
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows if row.doc == "test-plan.md")
        self.assertEqual(row.plan_ids, ("D7.1", "Y6.1", "Z4"))

    def test_extra_in_scope_document_becomes_a_row(self):
        docs = _docs(**{"agent-evidence-area11-extra.md": "Maps to Z4.\n"})
        walk = build_cross_walk(docs, KNOWN_IDS)
        row = next(row for row in walk.rows
                   if row.doc == "agent-evidence-area11-extra.md")
        self.assertEqual(row.status, STATUS_MAPPED)
        self.assertEqual(row.plan_ids, ("Z4",))
        self.assertEqual(len(walk.rows), len(REQUIRED_EVIDENCE_DOCS) + 1)

    def test_determinism_and_serialization(self):
        docs = _docs(**{"agent-evidence-area11-extra.md": "Maps to Z4.\n"})
        first = build_cross_walk(docs, KNOWN_IDS)
        second = build_cross_walk(dict(reversed(list(docs.items()))),
                                  tuple(reversed(KNOWN_IDS)))
        self.assertEqual(first.as_dict(), second.as_dict())
        encoded = json.dumps(cross_walk_dict(first), sort_keys=True)
        self.assertEqual(json.loads(encoded), first.as_dict())
        self.assertEqual(first.rows_with_status(STATUS_MAPPED), first.rows)
        self.assertEqual(first.rows_with_status(STATUS_MISSING), ())

    def test_unsafe_documents_and_ids_fail_closed(self):
        for name in ("../evil.md", "dir/evil.md", "..\\evil.md",
                     "%2e%2e/evil.md", "C:\\evil.md", "bad\nname.md", 7):
            with self.subTest(name=name), self.assertRaises(ContractValidationError):
                build_cross_walk({name: "Y6.1"}, KNOWN_IDS)
        with self.assertRaises(ContractValidationError):
            build_cross_walk(None, KNOWN_IDS)
        with self.assertRaises(ContractValidationError):
            build_cross_walk({"test-plan.md": b"bytes"}, KNOWN_IDS)
        for known in ("Y6.1", 7, "y6.1", "Y6.x", None):
            with self.subTest(known=known), self.assertRaises(ContractValidationError):
                build_cross_walk(_docs(), known)

    def test_cross_walk_dict_rejects_invalid_walks(self):
        with self.assertRaises(ContractValidationError):
            cross_walk_dict(None)
        docs = _docs()
        docs.pop("test-plan.md")
        with self.assertRaises(ContractValidationError):
            cross_walk_dict(build_cross_walk(docs, KNOWN_IDS))


# ---------------------------------------------------------------------------
# Y6.2 -- artifact detection, ignore and publish exclusion (no deletion)
# ---------------------------------------------------------------------------


class TestArtifactHandling(unittest.TestCase):

    def test_constants(self):
        self.assertEqual(ARTIFACT_DIR_PREFIX, ".verify-")
        self.assertEqual(ARTIFACT_DIR_NAMES, frozenset({".build"}))
        self.assertIn(".verify-*/", GITIGNORE_PATTERNS)
        self.assertIn(".build/", GITIGNORE_PATTERNS)
        self.assertEqual(gitignore_patterns(), GITIGNORE_PATTERNS)

    def test_detection_of_known_and_nested_artifacts(self):
        for path in (".verify-automode/a.json", ".build/out.bin",
                     "docs/.verify-raw/a", "keel/.build/x/y",
                     ".BUILD/Out", "a/.VERIFY-Skills/z"):
            with self.subTest(path=path):
                self.assertEqual(classify_path(path), "artifact")
                self.assertFalse(is_publishable(path))

    def test_normal_source_paths_are_publishable(self):
        for path in ("keel/src/keel/repo_contracts.py", "docs/notes.md",
                     "verify-notes.md", "build.py", "agent-evidence-area9-mcp.md"):
            with self.subTest(path=path):
                self.assertEqual(classify_path(path), "source")
                self.assertTrue(is_publishable(path))

    def test_unsafe_paths_fail_closed(self):
        for path in ("/etc/passwd", "C:\\secret", "../evil", "docs/../secret",
                     "docs/%2e%2e/secret", "docs/%2Fevil", "a\x00b", "", "  ",
                     "\\\\server\\share", 7, None):
            with self.subTest(path=path):
                with self.assertRaises(ContractValidationError):
                    classify_path(path)
                self.assertFalse(is_publishable(path))

    def test_scan_is_deterministic_and_deduplicated(self):
        paths = [".verify-raw/a", "keel/src/x.py", ".build/y",
                 "keel\\src\\x.py", "docs/z.md", ".verify-raw/a"]
        scan = scan_artifacts(paths)
        self.assertEqual(scan.artifacts, (".build/y", ".verify-raw/a"))
        self.assertEqual(scan.publishable, ("docs/z.md", "keel/src/x.py"))
        self.assertEqual(json.loads(json.dumps(scan.as_dict())), scan.as_dict())

    def test_scan_rejects_non_iterables_and_unsafe_paths(self):
        with self.assertRaises(ContractValidationError):
            scan_artifacts("docs/x.md")
        with self.assertRaises(ContractValidationError):
            scan_artifacts(["docs/x.md", None])
        with self.assertRaises(ContractValidationError):
            scan_artifacts(["docs/x.md", "../escape"])

    def test_allowlist_rejects_artifacts_wildcards_and_duplicates(self):
        for entries in ([".build/out"], ["docs/.verify-x/a"],
                        ["docs/*.md"], ["docs?"]):
            with self.subTest(entries=entries), self.assertRaises(
                    ContractValidationError):
                make_allowlist(entries)
        # Equivalent spellings of the same path canonicalise to one entry.
        self.assertEqual(make_allowlist(["a/b", "a\\b", "a/b"]).entries, ("a/b",))
        allowed = make_allowlist(["keel/src/x.py", "docs\\notes.md"])
        self.assertEqual(allowed.entries, ("docs/notes.md", "keel/src/x.py"))
        self.assertTrue(is_allowed("docs/notes.md", allowed))
        self.assertTrue(is_allowed("docs\\notes.md", allowed))
        self.assertFalse(is_allowed("docs/other.md", allowed))
        self.assertFalse(is_allowed(".build/out", allowed))
        self.assertFalse(is_allowed("../escape", allowed))
        self.assertFalse(is_allowed("docs/notes.md", None))

    def test_filter_publishable_excludes_artifacts_and_unlisted(self):
        paths = [".verify-raw/a", "keel/src/x.py", "docs/z.md", ".build/out"]
        allowed = make_allowlist(["keel/src/x.py"])
        self.assertEqual(filter_publishable(paths, allowed), ("keel/src/x.py",))
        self.assertEqual(filter_publishable(paths, make_allowlist(())), ())
        with self.assertRaises(ContractValidationError):
            filter_publishable(paths, None)

    def test_disposition_has_no_delete_action(self):
        paths = [".verify-raw/a", "keel/src/x.py", "docs/z.md", ".build/out"]
        allowed = make_allowlist(["keel/src/x.py"])
        dispositions = artifact_disposition(paths, allowed)
        by_path = {item.path: item.action for item in dispositions}
        self.assertEqual(by_path[".verify-raw/a"], ACTION_IGNORE)
        self.assertEqual(by_path[".build/out"], ACTION_IGNORE)
        self.assertEqual(by_path["keel/src/x.py"], ACTION_PUBLISH)
        self.assertEqual(by_path["docs/z.md"], ACTION_EXCLUDE_FROM_PUBLISH)
        self.assertTrue(all(item.action != "delete" for item in dispositions))
        self.assertEqual({item.action for item in dispositions},
                         {ACTION_IGNORE, ACTION_PUBLISH,
                          ACTION_EXCLUDE_FROM_PUBLISH})
        for item in dispositions:
            self.assertTrue(item.as_dict()["reason"])

    def test_default_allowlist_excludes_everything_publishable(self):
        dispositions = artifact_disposition(["docs/a.md", ".build/b"])
        self.assertEqual([item.action for item in dispositions],
                         [ACTION_IGNORE, ACTION_EXCLUDE_FROM_PUBLISH])

    def test_artifact_scan_validation_catches_smuggled_artifacts(self):
        scan = scan_artifacts([".verify-raw/a", "docs/x.md"])
        forged = ArtifactAllowlist(entries=(".verify-raw/a", "docs/*.md",
                                             "docs/x.md"))
        errors = validate_artifact_scan(scan, forged)
        self.assertTrue(any(".verify-raw/a" in error for error in errors))
        self.assertTrue(any("wildcard" in error for error in errors))
        self.assertEqual(validate_artifact_scan(scan, make_allowlist(
            ["docs/x.md"])), ())
        self.assertEqual(len(validate_artifact_scan(None, forged)), 1)


# ---------------------------------------------------------------------------
# Z4 -- crash-safe turn journal
# ---------------------------------------------------------------------------


class TestCrashSafeJournal(unittest.TestCase):

    def test_write_ahead_round_trip(self):
        journal = Journal()
        self.assertEqual(journal.begin_tool("turn-1", "call-1", "bash",
                                            _hex("args")), _hex(
            json.dumps({"seq": 1, "kind": "tool_started", "turn_id": "turn-1",
                        "tool_call_id": "call-1", "name": "bash",
                        "args_digest": _hex("args"), "prev": GENESIS_DIGEST},
                       sort_keys=True, separators=(",", ":"))))
        self.assertEqual(journal.pending_tool_calls(), ("call-1",))
        journal.finish_tool("call-1", _hex("result"))
        self.assertEqual(journal.pending_tool_calls(), ())
        records = journal.records()
        self.assertEqual([record["kind"] for record in records],
                         ["tool_started", "tool_done"])
        self.assertEqual(records[1]["prev"], records[0]["digest"])
        descriptor = recover(journal.bytes())
        self.assertEqual(descriptor.seq, 2)
        self.assertTrue(descriptor.clean)
        self.assertEqual(descriptor.interrupted, ())
        self.assertFalse(descriptor.tail_discarded)
        self.assertEqual(descriptor.durable_bytes, len(journal.bytes()))
        self.assertEqual(interrupted_tool_prompt(descriptor), "")

    def test_headers_are_newline_framed_and_chained(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        data = journal.bytes()
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 1)
        lines = data.rstrip(b"\n").split(b"\n")
        record = json.loads(lines[0])
        self.assertEqual(record["prev"], GENESIS_DIGEST)
        self.assertNotIn("digest", {k: v for k, v in record.items()
                                    if k != "digest"})

    def test_torn_tail_is_discarded_atomicly(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        journal.finish_tool("call-1", _hex("result"))
        # A third record is the one torn by power loss: both the write-ahead
        # start and its matching done are already durable.
        journal.begin_tool("turn-1", "call-2", "web", _hex("args2"))
        data = journal.bytes()
        torn = data[:-9]
        descriptor = recover(torn)
        lines = data.rstrip(b"\n").split(b"\n")
        expected_bytes = len(lines[0]) + 1 + len(lines[1]) + 1
        self.assertTrue(descriptor.tail_discarded)
        self.assertEqual(descriptor.seq, 2)
        self.assertEqual(descriptor.durable_bytes, expected_bytes)
        self.assertEqual(descriptor.errors != (), True)
        self.assertEqual(descriptor.interrupted, ())
        self.assertFalse(descriptor.clean)

    def test_torn_tool_done_leaves_an_interrupted_tool(self):
        journal = Journal()
        journal.begin_tool("turn-7", "call-9", "editor", _hex("patch"))
        journal.finish_tool("call-9", _hex("ok"))
        data = journal.bytes()
        last_line = data.rstrip(b"\n").split(b"\n")[-1]
        torn = data[: len(data) - len(last_line) - 1 + 11]
        descriptor = recover(torn)
        self.assertTrue(descriptor.tail_discarded)
        self.assertEqual(descriptor.seq, 1)
        self.assertEqual(len(descriptor.interrupted), 1)
        item = descriptor.interrupted[0]
        self.assertIsInstance(item, InterruptedTool)
        self.assertEqual((item.turn_id, item.tool_call_id, item.name,
                          item.started_seq),
                         ("turn-7", "call-9", "editor", 1))
        self.assertEqual(item.as_dict()["actions"], [ACTION_RETRY, ACTION_SKIP])
        self.assertIn(PROMPT_TEXT, interrupted_tool_prompt(descriptor))
        self.assertIn("call-9", interrupted_tool_prompt(descriptor))
        self.assertEqual(descriptor.actions(),
                         {"call-9": (ACTION_RETRY, ACTION_SKIP)})
        self.assertEqual(str(RecoveryAction.RETRY), "retry")
        self.assertEqual(str(RecoveryAction.SKIP), "skip")

    def test_resume_rebuilds_only_durable_records(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        journal.finish_tool("call-1", _hex("result"))
        journal.begin_tool("turn-1", "call-2", "web", _hex("args2"))
        data = journal.bytes()
        resumed = resume_journal(data[:-9])
        self.assertEqual(len(resumed.records()), 2)
        self.assertEqual(resumed.pending_tool_calls(), ())
        digest = resumed.begin_tool("turn-2", "call-3", "web", _hex("args3"))
        self.assertEqual(digest, resumed.records()[-1]["digest"])
        self.assertEqual(resumed.records()[-1]["seq"], 3)
        self.assertEqual(resumed.records()[-1]["prev"],
                         resumed.records()[1]["digest"])
        self.assertTrue(recover(resumed.bytes()).tail_discarded is False)

    def test_manual_retry_and_skip_paths(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        descriptor = recover(journal.bytes())
        resumed = resume_journal(journal.bytes())
        self.assertEqual(descriptor.actions()["call-1"][0], ACTION_RETRY)
        with self.assertRaises(ContractValidationError):
            resumed.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        resumed.finish_tool("call-1", _hex("result"))  # retry: mark done
        skip_journal = resume_journal(journal.bytes())
        skip_journal.begin_tool("turn-1", "call-2", "web", _hex("args2"))
        self.assertEqual(recover(skip_journal.bytes()).seq, 2)

    def test_bad_chain_and_digest_stop_recovery(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        journal.finish_tool("call-1", _hex("result"))
        data = journal.bytes()
        bad_prev = _mutate_line(data, 1, lambda rec: rec.update(prev="0" * 64))
        bad_digest = _mutate_line(data, 1, lambda rec: rec.update(digest="0" * 64))
        extra_field = _mutate_line(data, 0, lambda rec: rec.update(smuggled=True))
        for mutated in (bad_prev, bad_digest, extra_field):
            with self.subTest(mutated=mutated):
                descriptor = recover(mutated)
                self.assertTrue(descriptor.tail_discarded)
                self.assertLess(descriptor.seq, 2)
                self.assertTrue(descriptor.errors)

    def test_seq_gap_and_duplicate_start_stop_recovery(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        journal.finish_tool("call-1", _hex("result"))
        data = journal.bytes()
        gap = _mutate_line(data, 1, lambda rec: rec.update(seq=7))
        duplicate = _mutate_line(data, 1, lambda rec: rec.update(
            kind="tool_started", name="bash", args_digest=_hex("args")))
        for mutated in (gap, duplicate):
            descriptor = recover(mutated)
            self.assertTrue(descriptor.tail_discarded)
            self.assertEqual(descriptor.seq, 1)
            self.assertEqual(descriptor.errors != (), True)

    def test_invalid_json_utf8_and_blank_lines_are_discarded(self):
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        data = journal.bytes()
        first_line = data.split(b"\n")[0]
        for stream in (first_line + b"\nnot json\n",
                       first_line + b"\n\xff\xfe\n",
                       first_line + b"\n\n" + first_line + b"\n"):
            with self.subTest(stream=stream):
                descriptor = recover(stream)
                self.assertTrue(descriptor.tail_discarded)
                self.assertEqual(descriptor.seq, 1)
                self.assertTrue(descriptor.errors)

    def test_recover_empty_and_serialization(self):
        descriptor = recover(b"")
        self.assertEqual(descriptor.as_dict(), {
            "seq": 0, "records": [], "interrupted": [], "durable_bytes": 0,
            "tail_discarded": False, "errors": [], "clean": True,
        })
        journal = Journal()
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        descriptor = recover(journal.bytes())
        self.assertEqual(json.loads(json.dumps(descriptor.as_dict())),
                         descriptor.as_dict())
        self.assertEqual(journal.as_dict()["pending"], ["call-1"])

    def test_recover_rejects_oversized_and_non_bytes_streams(self):
        with self.assertRaises(ContractValidationError):
            recover("text")
        with self.assertRaises(ContractValidationError):
            recover(b"x" * (MAX_JOURNAL_BYTES + 1))

    def test_memory_sink_is_atomic_and_in_memory(self):
        sink = MemorySink()
        self.assertEqual(sink.snapshot(), b"")
        sink.append(b'{"a":1}\n')
        for chunk in (b"partial", b"a\nb\n", b"", "text"):
            with self.subTest(chunk=chunk), self.assertRaises(
                    ContractValidationError):
                sink.append(chunk)
        self.assertEqual(sink.chunks(), (b'{"a":1}\n',))
        self.assertEqual(sink.snapshot(), b'{"a":1}\n')

    def test_invalid_tool_calls_fail_closed(self):
        journal = Journal()
        with self.assertRaises(ContractValidationError):
            journal.finish_tool("call-1", _hex("result"))
        with self.assertRaises(ContractValidationError):
            journal.begin_tool("../turn", "call-1", "bash", _hex("args"))
        with self.assertRaises(ContractValidationError):
            journal.begin_tool("turn-1", "call-1", "bash", "UPPERCASE")
        journal.begin_tool("turn-1", "call-1", "bash", _hex("args"))
        with self.assertRaises(ContractValidationError):
            journal.begin_tool("turn-1", "call-1", "web", _hex("args2"))
        with self.assertRaises(ContractValidationError):
            journal.finish_tool("call-1", "not-a-digest")

    def test_prompt_rejects_non_descriptors(self):
        with self.assertRaises(ContractValidationError):
            interrupted_tool_prompt(None)


if __name__ == "__main__":
    unittest.main()

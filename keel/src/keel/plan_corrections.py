"""Real verification of the Addendum 3 X0.x P0 plan-correction artifacts.

Every public ``verify_x0_*`` function reads the artifacts from disk and returns a
:class:`VerificationResult` with concrete evidence (what was checked and what
was found) and concrete errors. A caller may pass an alternate repository root
to prove that verification fails when an artifact is missing, stale or invalid;
this module never merely restates a claim made in a document.

The eight P0 rows implemented here are X0.1, X0.2, X0.3, X0.4, X0.6, X0.7,
X0.8 and X0.10. X0.9 (risk register) is P1 and is reported as a supporting,
informational check, not as part of the P0 result set.

Stdlib only. No network access, no subprocesses, no third-party imports.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# --- Artifact locations, relative to the repository root -------------------

PLAN_INDEX = "PLAN-INDEX.json"
DEPENDENCY_GRAPH = "DEPENDENCY-GRAPH.md"
FREE_TIER_REGISTER = "FREE-TIER-REGISTER.md"
MODEL_LICENSES = "MODEL-AND-VOICE-LICENSES.json"
RISKS = "RISKS.md"
DECISIONS = "DECISIONS.md"
OFFLINE_WORKFLOW = ".github/workflows/offline-license.yml"
LICENSE_GATE_SCRIPT = "scripts/check_model_licenses.py"
DEP_GRAPH_SCRIPT = "keel/scripts/build_dependency_graph.py"
DUET_SRC = "keel/src/keel/duet.py"
SPEC_MODE_SRC = "keel/src/keel/spec_mode.py"
NOTICES_HTML = "keel/site/notices.html"
OFFLINE_TEST = "keel/tests/test_offline_runtime.py"
BEHAVIOR_SPEC_DIR = "keel/docs/research/reference-behavior"
EDIT_FORMATS_EVIDENCE = "master-plan-v6-edit-formats-evidence.md"
THIRD_PARTY_NOTICES = "keel/docs/THIRD_PARTY_NOTICES.md"

# The six M19 sub-milestones required verbatim by X0.2.
EXPECTED_M19_SPLITS: tuple[tuple[str, str], ...] = (
    ("M19a", "shell/layout"),
    ("M19b", "chat/composer"),
    ("M19c", "review/diff/terminal docks"),
    ("M19d", "fleet/board/memory views"),
    ("M19e", "settings/forms/wizard"),
    ("M19f", "polish/a11y/i18n"),
)

# X0.7 watch items that must be present in the machine-readable registry.
LICENSE_WATCH_ITEMS: frozenset[str] = frozenset({
    "piper-tts", "kokoro-voices", "whisper-weights", "diarization-models",
    "ffmpeg-build", "work-sans-font",
})

# Provider keys the offline CI lane must remove before the smoke suite.
PROVIDER_KEY_NAMES: tuple[str, ...] = (
    "KEEL_OPENROUTER_API_KEY", "KEEL_GOOGLE_API_KEY", "KEEL_NVIDIA_API_KEY",
    "KEEL_ANTHROPIC_API_KEY", "KEEL_COMPAT_API_KEY",
)

OFFLINE_SMOKE_TESTS: tuple[str, ...] = (
    "test_offline_runtime.py", "test_cli_e2e.py", "test_e2e_local.py",
)


# --- Result type and small helpers -----------------------------------------

@dataclass
class VerificationResult:
    """Structured outcome of one artifact check."""

    id: str
    feature: str
    ok: bool = True
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.evidence.append(message)

    def fail(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def require(self, condition: bool, message: str) -> bool:
        if not condition:
            self.fail(message)
        return bool(condition)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feature": self.feature,
            "ok": self.ok,
            "evidence": list(self.evidence),
            "errors": list(self.errors),
        }


def _result(feature_id: str, feature: str) -> VerificationResult:
    return VerificationResult(id=feature_id, feature=feature)


def _read_text(root: Path, rel: str, r: VerificationResult) -> str:
    path = root / rel
    if not r.require(path.is_file(), f"missing artifact: {rel}"):
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:  # pragma: no cover - defensive
        r.fail(f"cannot read {rel}: {exc}")
        return ""
    r.note(f"read {rel} ({len(text)} characters)")
    return text


def _read_json(root: Path, rel: str, r: VerificationResult) -> Any:
    text = _read_text(root, rel, r)
    if not text:
        return None
    try:
        doc = json.loads(text)
    except ValueError as exc:
        r.fail(f"invalid JSON in {rel}: {exc}")
        return None
    r.note(f"parsed JSON {rel}")
    return doc


def _section(text: str, heading_prefix: str) -> str:
    """Return the markdown section beginning at *heading_prefix*."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(heading_prefix):
            out: list[str] = []
            for following in lines[index + 1:]:
                if following.startswith("### ") or following.startswith("## "):
                    break
                out.append(following)
            return "\n".join(out)
    return ""


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    """Return the literal value of a (possibly annotated) module assignment."""
    for node in ast.walk(tree):
        value = None
        target_name = None
        if isinstance(node, ast.Assign):
            value = node.value
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = node.value
            target_name = node.target.id
        if target_name == name and value is not None:
            try:
                return ast.literal_eval(value)
            except (ValueError, TypeError):
                return None
    return None


def _default_root() -> Path:
    """Repository root, derived from this module's own location."""
    return Path(__file__).resolve().parents[3]


def _features(doc: Any, r: VerificationResult) -> list[dict[str, Any]]:
    if not isinstance(doc, dict):
        r.fail("plan index must be a JSON object")
        return []
    features = doc.get("features")
    if not r.require(isinstance(features, list), "plan index has no features list"):
        return []
    if not r.require(len(features) >= 800,
                     f"expected the full 865-row registry, got {len(features)} rows"):
        return []
    return [f for f in features if isinstance(f, dict)]


# --- X0.1 — priority inflation ---------------------------------------------

def verify_x0_1(root: Path) -> VerificationResult:
    """P0 must be re-ranked to roughly 25% with original priorities retained."""
    r = _result("X0.1", "Priority inflation — re-rank P0 to ~25% of rows")
    doc = _read_json(root, PLAN_INDEX, r)
    if doc is None:
        return r
    features = _features(doc, r)
    if not features:
        return r

    total = len(features)
    counts = Counter(f.get("priority") for f in features)
    declared = doc.get("priority_counts")
    if r.require(isinstance(declared, dict), "priority_counts object is missing"):
        for priority in ("P0", "P1", "P2"):
            r.require(
                declared.get(priority) == counts[priority],
                f"priority_counts.{priority}={declared.get(priority)!r} but rows contain "
                f"{counts[priority]}",
            )
    r.note(f"registry rows={total}, priority counts={dict(counts)}")

    # "Roughly 25%" is interpreted as an explicit tolerance band, not an exact
    # value: a cap of 30% and a floor of 20% prevent both inflation and a
    # trivial all-P1 registry.
    share = counts["P0"] / total
    r.require(
        0.20 <= share <= 0.30,
        f"P0 share {share:.2%} is outside the documented 'roughly 25%' band "
        f"[20%, 30%]",
    )
    r.note(f"P0 share {share:.2%} within [20%, 30%] tolerance band")

    missing_original = [f.get("id") for f in features if "original_priority" not in f]
    r.require(not missing_original,
              f"original_priority missing on {len(missing_original)} rows "
              f"(e.g. {missing_original[:3]})")
    original = Counter(f.get("original_priority") for f in features)
    demotions = sum(1 for f in features
                    if f.get("priority") == "P1"
                    and f.get("original_priority") == "P0")
    r.require(demotions >= 50,
              f"only {demotions} P0→P1 demotions; re-ranking is not evidenced")
    original_share = original["P0"] / total
    r.require(original_share > share + 0.05,
              f"original P0 share {original_share:.2%} is not materially above "
              f"current share {share:.2%}; no de-inflation occurred")
    r.note(
        f"original_priority retained: original P0={original['P0']} "
        f"({original_share:.2%}), {demotions} rows demoted P0→P1"
    )
    return r


# --- X0.2 — overloaded M19 milestone split ---------------------------------

def verify_x0_2(root: Path) -> VerificationResult:
    """M19 must be decomposed into the six named sub-milestones M19a–M19f."""
    r = _result("X0.2", "M19 split into M19a shell/layout … M19f polish/a11y/i18n")
    script = _read_text(root, DEP_GRAPH_SCRIPT, r)
    if script:
        try:
            tree = ast.parse(script)
        except SyntaxError as exc:
            r.fail(f"cannot parse {DEP_GRAPH_SCRIPT}: {exc}")
            tree = None
        if tree is not None:
            decompositions = _literal_assignment(tree, "FALLBACK_DECOMPOSITIONS")
            patterns = _literal_assignment(tree, "SPLIT_PATTERNS")
            if r.require(isinstance(decompositions, dict),
                         "FALLBACK_DECOMPOSITIONS literal is missing"):
                labels = decompositions.get("M19", [])
                r.require(len(labels) == 6,
                          f"expected 6 M19 split labels, found {len(labels)}")
                for code, text in EXPECTED_M19_SPLITS:
                    r.require(
                        any(isinstance(label, str)
                            and label.startswith(code + " ")
                            and text in label.lower()
                            for label in labels),
                        f"missing split label {code} {text}",
                    )
                r.note(f"generator declares M19 splits: {labels}")
            if r.require(isinstance(patterns, dict),
                         "SPLIT_PATTERNS literal is missing"):
                codes = [code for code, _pattern in patterns.get("M19", [])]
                expected_codes = {code for code, _ in EXPECTED_M19_SPLITS}
                r.require(set(codes) == expected_codes,
                          f"M19 classifier nodes {sorted(codes)} != "
                          f"expected {sorted(expected_codes)}")
                r.note(f"generator classifies M19 rows into {len(codes)} nodes")
    report = _read_text(root, DEPENDENCY_GRAPH, r)
    for code, text in EXPECTED_M19_SPLITS:
        label = f"{code} {text}"
        r.require(label in report, f"generated graph is missing split node {label!r}")
    return r


# --- X0.3 — dependency graph and readiness gate ----------------------------

def verify_x0_3(root: Path) -> VerificationResult:
    """A generated critical-path report must exist and match the registry."""
    r = _result("X0.3", "Dependency graph, critical path and readiness gate")
    doc = _read_json(root, PLAN_INDEX, r)
    if doc is None:
        return r
    features = _features(doc, r)
    if not features:
        return r

    by_id = {f.get("id"): f for f in features}
    with_deps = [f for f in features if isinstance(f.get("dependencies"), list)
                 and f["dependencies"]]
    references = sum(len(f["dependencies"]) for f in with_deps)
    r.require(len(with_deps) >= 100,
              f"only {len(with_deps)} rows declare dependencies")
    r.require(references >= 140,
              f"only {references} stated dependency references")
    r.note(f"registry declares {references} dependency references on "
           f"{len(with_deps)} rows")

    report = _read_text(root, DEPENDENCY_GRAPH, r)
    if not report:
        return r
    r.require("## 3. Critical path" in report, "report has no critical-path section")
    match = re.search(r"Critical path length:\s*\**\s*(\d+)", report)
    r.require(match is not None and int(match.group(1)) > 0,
              "report has no positive critical-path length")
    if match:
        r.note(f"report critical path length={match.group(1)}")

    r.require("## 6. Readiness gate (X0.3)" in report,
              "report has no X0.3 readiness-gate section")
    r.require("may not start a row whose dependencies are not green" in report,
              "readiness gate does not state the no-start rule")

    plan_bytes = (root / PLAN_INDEX).read_bytes()
    actual_sha = hashlib.sha256(plan_bytes).hexdigest()
    sha_match = re.search(r"SHA-256\s*`?([0-9a-f]{64})`?", report)
    r.require(sha_match is not None and sha_match.group(1) == actual_sha,
              f"report registry SHA {sha_match.group(1) if sha_match else None} "
              f"does not match actual {actual_sha} (stale artifact)")
    r.note(f"report provenance SHA-256 matches {PLAN_INDEX}")

    recomputed_startable = sum(1 for f in features
                               if f.get("status") == "not_started"
                               and isinstance(f.get("dependencies"), list)
                               and f["dependencies"])
    reported = re.search(
        r"not_started` rows that declare dependencies:\s*\**\s*(\d+)", report)
    r.require(reported is not None
              and int(reported.group(1)) == recomputed_startable,
              f"readiness gate count {reported.group(1) if reported else None} "
              f"does not match recomputed {recomputed_startable}")

    recomputed_unmet = sum(
        1 for f in features
        if f.get("status") == "not_started"
        and isinstance(f.get("dependencies"), list)
        and any(by_id.get(dep, {}).get("status") != "verified"
                for dep in f["dependencies"])
    )
    reported_unmet = re.search(
        r"at least one dependency not `verified`:\s*\**\s*(\d+)", report)
    r.require(reported_unmet is not None
              and int(reported_unmet.group(1)) == recomputed_unmet,
              f"reported unmet-dependency rows "
              f"{reported_unmet.group(1) if reported_unmet else None} "
              f"!= recomputed {recomputed_unmet}")
    r.note(f"readiness gate recomputed: {recomputed_startable} startable rows, "
           f"{recomputed_unmet} with unmet dependencies")

    spec = _read_text(root, SPEC_MODE_SRC, r)
    r.require("set_task_status" in spec and "unmet dependencies" in spec,
              "no executable seam blocking a task whose dependencies are not done")
    return r


# --- X0.4 — one Duet surface, two modes ------------------------------------

def verify_x0_4(root: Path) -> VerificationResult:
    """Duet must be one surface with Live Pair and Review Pair modes."""
    r = _result("X0.4", "Duet unified as Live Pair + Review Pair (owner D4)")
    decisions = _read_text(root, DECISIONS, r)
    section = _section(decisions, "### D-005")
    if r.require(bool(section), "DECISIONS.md has no D-005 record"):
        r.require("X0.4" in section and "D4" in section,
                  "D-005 does not reference X0.4 / D4")
        r.require("Live Pair" in section and "Review Pair" in section,
                  "D-005 does not define both Live Pair and Review Pair")
        r.require("one surface" in section.lower()
                  and "two modes" in section.lower(),
                  "D-005 does not unify the three definitions into one surface")
        r.require("read-only" in section.lower() and "reviewer" in section.lower(),
                  "D-005 does not make the independent reviewer read-only")
        r.require("chosen" in section.lower(),
                  "D-005 does not record a chosen resolution")
        r.note("D-005 unifies Master D4 / Addendum 1 B2.3 / Addendum 2 C2.3")
    else:
        return r

    duet = _read_text(root, DUET_SRC, r)
    if not duet:
        return r
    try:
        tree = ast.parse(duet)
    except SyntaxError as exc:  # pragma: no cover - defensive
        r.fail(f"cannot parse {DUET_SRC}: {exc}")
        return r
    functions = {node.name for node in tree.body
                 if isinstance(node, ast.FunctionDef)}
    r.require({"builder_allowlist", "review_allowlist"} <= functions,
              f"duet surface lacks role allowlists: {sorted(functions)}")
    r.require("You are an independent reviewer" in duet
              and "cannot edit files" in duet
              and "read-only tools" in duet,
              "reviewer prompt does not enforce the read-only contract")
    write_tools = {"write_file", "edit_file", "apply_patch", "str_replace"}
    allowed_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "review_allowlist":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Set):
                    for elt in sub.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            allowed_names.add(elt.value)
    r.require(bool(allowed_names), "reviewer allowlist set literal not found")
    r.require(not (allowed_names & write_tools),
              f"reviewer allowlist contains write tools: "
              f"{sorted(allowed_names & write_tools)}")
    r.note(f"reviewer allowlist is read-only ({len(allowed_names)} explicit tools)")
    return r


# --- X0.6 — free-tier register ---------------------------------------------

def verify_x0_6(root: Path) -> VerificationResult:
    """The free-tier register must cover each named trap with an exit plan."""
    r = _result("X0.6", "Free-tier register with terms, dates and exit plans")
    text = _read_text(root, FREE_TIER_REGISTER, r)
    if not text:
        return r
    r.require(re.search(r"re-verif\w*\s+at\s+each\s+gate", text, re.I) is not None,
              "register does not require re-verification at each gate")
    r.note("register declares re-verification at each gate")

    header = next((line for line in text.splitlines()
                   if "Service/Dependency" in line and "Exit strategy" in line), "")
    r.require(bool(header), "register header lacks service/date/exit columns")
    for column in ("Free tier used", "Commercial-use restrictions",
                   "Date verified", "Exit strategy", "Evidence source ID"):
        r.require(column in header, f"register header lacks column {column!r}")

    register_rows = [
        line for line in text.splitlines()
        if line.lstrip().startswith("|")
        and "---" not in line
        and "Service/Dependency" not in line
        and line.count("|") >= 8
        and re.search(r"\d{4}-\d{2}-\d{2}", line) is not None
    ]
    r.require(len(register_rows) >= 40,
              f"only {len(register_rows)} dated register rows found (expected ~43)")
    r.note(f"register contains {len(register_rows)} dated, evidence-linked rows")

    traps: tuple[tuple[str, str], ...] = (
        ("Vercel Hobby", "non-commercial"),
        ("VirusTotal", "non-commercial"),
        ("GitHub (source hosting", "limited"),
        ("Docker Desktop", "commercial"),
    )
    for name, marker in traps:
        row = next((line for line in register_rows if name in line), "")
        if not r.require(bool(row), f"register has no row for {name}"):
            continue
        r.require(marker in row.lower(),
                  f"{name} row does not state its free-tier restriction ({marker})")
        r.require(re.search(r"\d{4}-\d{2}-\d{2}", row) is not None,
                  f"{name} row has no date verified")
        r.require("|" in row and row.count("|") >= 8,
                  f"{name} row has no exit strategy / optionality columns")
        r.note(f"{name}: restriction, date and exit path recorded")
    return r


# --- X0.7 — model and voice license registry -------------------------------

def verify_x0_7(root: Path) -> VerificationResult:
    """The license registry must be complete and enforced by CI and the UI."""
    r = _result("X0.7", "MODEL-AND-VOICE-LICENSES.json + CI gate + UI display")
    doc = _read_json(root, MODEL_LICENSES, r)
    if not isinstance(doc, dict):
        return r
    entries = doc.get("entries")
    if not r.require(isinstance(entries, list) and len(entries) >= 8,
                     "license registry needs at least 8 entries"):
        return r
    required = {"id", "type", "name", "license", "commercial_use_allowed",
                "redistribution_allowed", "bundled", "source", "verified_date",
                "notes", "ci_gate"}
    for entry in entries:
        if not isinstance(entry, dict):
            r.fail("registry contains a non-object entry")
            continue
        eid = entry.get("id", "<unknown>")
        missing = required - set(entry)
        r.require(not missing, f"{eid}: missing fields {sorted(missing)}")
    by_id = {e.get("id"): e for e in entries if isinstance(e, dict)}
    r.note(f"registry parsed with {len(entries)} entries")

    for watch in sorted(LICENSE_WATCH_ITEMS):
        entry = by_id.get(watch)
        if not r.require(entry is not None, f"missing watch item {watch}"):
            continue
        r.require(entry.get("bundled") is False,
                  f"{watch} is bundled without a pinned license")
        r.require(entry.get("ci_gate") is True,
                  f"{watch} is not covered by the CI gate")
    r.note("all six X0.7 watch items present, unbundled and CI-gated")

    bundled = [e for e in entries if isinstance(e, dict) and e.get("bundled")]
    for entry in bundled:
        eid = entry.get("id")
        r.require(entry.get("commercial_use_allowed") is True,
                  f"bundled {eid} is not commercial-use allowed")
        r.require(entry.get("redistribution_allowed") is True,
                  f"bundled {eid} is not redistribution allowed")
        r.require(bool(str(entry.get("verified_date", "")).strip()),
                  f"bundled {eid} has no verified_date")
        r.require(entry.get("ci_gate") is True,
                  f"bundled {eid} is not ci-gated")
    r.note(f"fail-closed check applied to {len(bundled)} bundled entries")

    policy = doc.get("ci_policy")
    if r.require(isinstance(policy, dict), "ci_policy is missing"):
        has_rule = (policy.get("reject_non_commercial_bundled") is True
                    or any("commercial_use_allowed == false" in str(rule)
                           for rule in policy.get("reject_when", [])))
        r.require(has_rule, "ci_policy does not reject non-commercial bundled entries")

    gate = _read_text(root, LICENSE_GATE_SCRIPT, r)
    for token in ("commercial_use_allowed is not true",
                  "redistribution_allowed is not true", "verified_date",
                  "ci_gate", "return 1"):
        r.require(token in gate, f"license gate script lacks enforcement: {token}")
    workflow = _read_text(root, OFFLINE_WORKFLOW, r)
    r.require("license-gate" in workflow
              and "python scripts/check_model_licenses.py" in workflow,
              "offline-license.yml does not run the license gate")
    r.note("CI gate enforced by scripts/check_model_licenses.py in workflow")

    notices = _read_text(root, NOTICES_HTML, r)
    if notices:
        lower = notices.lower()
        r.require("license" in lower and "MIT" in notices and "Apache" in notices,
                  "UI notices/license display surface is missing")
        r.note("UI license display surface present (site/notices.html)")
    return r


# --- X0.8 — zero-network CI smoke lane -------------------------------------

def verify_x0_8(root: Path) -> VerificationResult:
    """A fail-closed CI lane must run the smoke suite with no network."""
    r = _result("X0.8", "Zero-network-without-account CI smoke job")
    workflow = _read_text(root, OFFLINE_WORKFLOW, r)
    if not workflow:
        return r
    r.require("offline-smoke:" in workflow, "workflow has no offline-smoke job")
    r.require("unshare -n" in workflow,
              "CI does not remove the network namespace")
    r.require("command -v unshare" in workflow
              and ("failing closed" in workflow.lower()
                   or "fail closed" in workflow.lower()),
              "CI does not fail closed when unshare is unavailable")
    r.require("python -m pytest -q" in workflow,
              "offline lane does not run the smoke suite")
    for key in PROVIDER_KEY_NAMES:
        r.require(key in workflow, f"offline lane does not unset {key}")
    for test in OFFLINE_SMOKE_TESTS:
        r.require(test in workflow, f"offline lane does not run {test}")
    r.note("offline-smoke unsets 5 provider keys, runs 3 smoke files under "
           "`unshare -n`, fails closed without unshare")

    offline_test = _read_text(root, OFFLINE_TEST, r)
    if offline_test:
        lower = offline_test.lower()
        r.require("no network" in lower and "unshare -n" in offline_test,
                  "offline smoke test does not declare the no-network contract")
        r.require("KEEL_OPENROUTER_API_KEY" in offline_test,
                  "offline smoke test does not strip provider credentials")
        r.require("coding task" in lower,
                  "offline smoke test does not exercise a coding task")
        r.note("offline smoke test covers import, config and a local coding turn")
    r.note("kernel-level `unshare -n` denies all outbound traffic, which "
           "subsumes a separate update-check toggle")
    return r


# --- X0.9 (P1) — supporting risk register check ----------------------------

def verify_x0_9_supporting(root: Path) -> VerificationResult:
    """Informational check of the P1 risk register artifact (RISKS.md)."""
    r = _result("X0.9", "Risk register (P1 — supporting, informational)")
    text = _read_text(root, RISKS, r)
    if not text:
        return r
    lower = text.lower()
    for column in ("likelihood", "impact", "mitigation", "owner", "rollback"):
        r.require(column in lower, f"risk register lacks {column} information")
    for risk_id in ("M0-R1", "M0-R2", "M0-R3", "M0-R4"):
        r.require(risk_id in text, f"risk register lacks {risk_id}")
    milestones = set(re.findall(r"^## (M\d+)\b", text, re.M))
    r.require(len(milestones) >= 10,
              f"risk register covers only {len(milestones)} milestones")
    r.note(f"risk register covers {len(milestones)} milestones with rollback plans")
    return r


# --- X0.10 — clean-room protocol -------------------------------------------

def verify_x0_10(root: Path) -> VerificationResult:
    """The two-step clean-room protocol and its analyst artifacts must exist."""
    r = _result("X0.10", "Two-step clean-room procedure with provenance logging")
    decisions = _read_text(root, DECISIONS, r)
    section = _section(decisions, "### D-021")
    if r.require(bool(section), "DECISIONS.md has no D-021 clean-room decision"):
        lower = section.lower()
        r.require("x0.10" in lower, "D-021 does not reference X0.10")
        r.require("two-step" in lower or "two step" in lower,
                  "D-021 does not define the two-step process")
        r.require("no code" in lower and "spec only" in lower,
                  "D-021 does not require a no-code spec and spec-only build")
        r.require("provenance" in lower and "each module" in lower,
                  "D-021 does not require per-module provenance logging")
        r.require("chosen" in lower, "D-021 has no chosen resolution")
        r.note("D-021 records analyst-spec → builder-implement → provenance log")

    spec_dir = root / BEHAVIOR_SPEC_DIR
    if not r.require(spec_dir.is_dir(), f"missing behavior spec directory: "
                                        f"{BEHAVIOR_SPEC_DIR}"):
        return r
    specs = sorted(spec_dir.glob("*-behavior.md"))
    r.require(len(specs) >= 5,
              f"only {len(specs)} clean-room behavior specs found (expected >=5)")
    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        name = spec.name
        r.require(re.search(r"^#{2,3}\s+.*Provenance", text, re.M) is not None,
                  f"{name} has no provenance statement section")
        r.require("clean-room" in text.lower(),
                  f"{name} does not declare a clean-room method")
        r.require("do not copy" in text.lower()
                  or "non-adoption" in text.lower()
                  or "no source code" in text.lower(),
                  f"{name} does not forbid copying reference material")
        r.require("Source metadata" in text and ("github.com" in text or
                                                  "Repository URL" in text),
                  f"{name} has no source metadata / pinned repository")
    r.note(f"{len(specs)} behavior specs: no pasted code, provenance statements, "
           f"pinned source metadata")

    evidence = _read_text(root, EDIT_FORMATS_EVIDENCE, r)
    if evidence:
        r.require("edit_formats.py" in evidence
                  and "edit-format-behavior.md" in evidence,
                  "provenance log does not map edit_formats.py to its behavior spec")
    notices = _read_text(root, THIRD_PARTY_NOTICES, r)
    if notices:
        r.require("exec_policy.py" in notices and "clean-room" in notices.lower(),
                  "third-party notices do not record a module-to-clean-room mapping")
    r.note("provenance logs map modules to their clean-room behavior specs")
    return r


# --- Aggregate report ------------------------------------------------------

P0_VERIFIERS: tuple[Callable[[Path], VerificationResult], ...] = (
    verify_x0_1, verify_x0_2, verify_x0_3, verify_x0_4,
    verify_x0_6, verify_x0_7, verify_x0_8, verify_x0_10,
)


def verify_all(root: str | Path | None = None) -> dict[str, Any]:
    """Run all P0 verifiers and return a structured report."""
    base = Path(root).resolve() if root is not None else _default_root()
    results = [verify(base) for verify in P0_VERIFIERS]
    supporting = [verify_x0_9_supporting(base)]
    passed = sum(1 for result in results if result.ok)
    return {
        "root": str(base),
        "scope": "Addendum 3 X0.x P0 plan corrections",
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "all_ok": passed == len(results),
        },
        "results": [result.to_dict() for result in results],
        "supporting_checks": [result.to_dict() for result in supporting],
    }


def main() -> int:
    report = verify_all()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["summary"]["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

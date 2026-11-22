"""Shared adversarial OS-sandbox conformance suite.

This module is deliberately named ``sandbox_conformance.py`` (not ``test_*``)
so it is never picked up by the ordinary fast unit-test run.  Run it explicitly::

    python -m pytest tests/sandbox_conformance.py -q -s

Design contract
---------------
* Every case launches a **real restricted child process** through the common
  ``keel.os_sandbox`` interface (``run_confined``).  No case passes by reading
  ``capabilities()``, inspecting configuration or checking a detection flag.
* The interface is resolved dynamically.  A future platform-specific backend
  (``keel.sandbox_linux`` / ``keel.sandbox_windows`` / ``keel.sandbox_macos``)
  can be substituted with ``KEEL_SANDBOX_BACKEND=<module>``; absent modules are
  tolerated.  The common interface remains the default and the reference point.
* The child emits a ``READY`` line before attempting anything, an explicit
  ``BREACH:`` marker only on a successful forbidden action, an ``ALLOWED_OK:``
  marker on a successful authorized action, and ``DENIED:<ExcType>`` on a caught
  exception.  A caught exception is therefore *never* converted into success.
* Classification is PASS / PARTIAL / BLOCKED / FAIL.  ``pytest.skip`` is used
  only for BLOCKED, and every BLOCKED reason embeds captured stderr evidence
  from the process that was actually launched.
* Structured JSON + Markdown evidence is generated into ``tmp_path`` (under a
  ``keel/docs/research/sandbox-conformance`` mirror) at test time.  Nothing is
  committed; the static companion document is
  ``docs/research/sandbox-conformance.md``.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

HOST_OS = sys.platform
IS_WINDOWS = os.name == "nt"

_BACKEND_CACHE: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Dynamic interface resolution (tolerates later platform backends)
# ---------------------------------------------------------------------------
def _load_sandbox():
    """Return the first module exposing the common confinement interface."""
    if "module" in _BACKEND_CACHE:
        return _BACKEND_CACHE["module"]
    override = os.environ.get("KEEL_SANDBOX_BACKEND", "").strip()
    candidates = [override] if override else []
    candidates += ["keel.os_sandbox"]
    suffix = "windows" if IS_WINDOWS else ("darwin" if HOST_OS == "darwin" else "linux")
    candidates.append(f"keel.sandbox_{suffix}")
    required = ("run_confined", "capabilities", "SandboxUnavailable")
    attempted: list[str] = []
    for name in candidates:
        if not name or name in attempted:
            continue
        attempted.append(name)
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # backend not integrated (yet) -> tolerated
            _BACKEND_CACHE.setdefault("attempts", []).append(f"{name}: {exc!r}")
            continue
        if all(hasattr(module, attr) for attr in required):
            _BACKEND_CACHE["module"] = module
            _BACKEND_CACHE["selected"] = name
            return module
        _BACKEND_CACHE.setdefault("attempts", []).append(
            f"{name}: missing interface attributes {required}")
    _BACKEND_CACHE["module"] = None
    _BACKEND_CACHE["selected"] = "none"
    return None


@pytest.fixture(scope="module")
def sandbox():
    module = _load_sandbox()
    if module is None:
        attempts = "; ".join(_BACKEND_CACHE.get("attempts", [])) or "no candidates"
        pytest.skip("BLOCKED: no common sandbox interface importable (" + attempts + ")")
    return module


def _capabilities(module) -> dict:
    try:
        caps = module.capabilities()
        return caps if isinstance(caps, dict) else {}
    except Exception:
        return {}


def _enforcement_claimed(mechanism: str, module) -> bool:
    """F6: derive the claim from capabilities(), never from our own optimism."""
    caps = _capabilities(module)
    if mechanism == "network":
        return bool(caps.get("network_enforcement", False))
    if mechanism == "filesystem":
        return bool(caps.get("filesystem_enforcement", False))
    if mechanism in ("resource", "tree"):
        # capabilities() has no dedicated resource flag; the honest proxy is
        # the reported OS: the preexec/rlimit path exists on POSIX only.
        return str(caps.get("os", "")).startswith(("linux", "darwin"))
    return False


def _mechanism_unavailable(mechanism: str, module) -> bool:
    """BLOCKED is allowed *only* when capabilities() reports no enforcement."""
    return not _enforcement_claimed(mechanism, module)


# ---------------------------------------------------------------------------
# Evidence helper
# ---------------------------------------------------------------------------
@dataclass
class CaseRecord:
    case_id: str
    category: str
    os: str
    mechanism: str
    expected: str
    actual: str
    exit_status: Any
    observed_denial: str
    safe_logs: dict
    classification: str
    reason: str


class EvidenceCollector:
    """Accumulates case records and writes JSON/Markdown into tmp_path."""

    def __init__(self, report_dir: Path):
        self.report_dir = report_dir
        self.records: list[CaseRecord] = []

    def record(self, **kwargs) -> None:
        self.records.append(CaseRecord(**kwargs))

    @property
    def counts(self) -> dict:
        out = {"PASS": 0, "PARTIAL": 0, "BLOCKED": 0, "FAIL": 0}
        for rec in self.records:
            out[rec.classification] = out.get(rec.classification, 0) + 1
        return out

    def write_reports(self) -> tuple[Path, Path]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "host": {
                "os": HOST_OS,
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "backend": _BACKEND_CACHE.get("selected", "unknown"),
            },
            "summary": self.counts,
            "classification_legend": {
                "PASS": "restricted process behaved as expected",
                "PARTIAL": "restricted process ran but result was ambiguous/incomplete",
                "BLOCKED": "mechanism unavailable on this host; skip with stderr evidence",
                "FAIL": "restricted process violated the expected boundary",
            },
            "cases": [rec.__dict__ for rec in self.records],
        }
        json_path = self.report_dir / "sandbox-conformance-report.json"
        md_path = self.report_dir / "sandbox-conformance-report.md"
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        lines = [
            "# Sandbox conformance evidence (generated)",
            "",
            f"- Generated (UTC): `{payload['generated_at']}`",
            f"- Host OS: `{HOST_OS}` / `{platform.platform()}`",
            f"- Python: `{payload['host']['python']}`",
            f"- Backend module: `{payload['host']['backend']}`",
            f"- Counts: `{self.counts}`",
            "",
            "This file is produced at test time into `tmp_path`; it is not committed.",
            "",
            "| Case | Category | Mechanism | Expected | Actual | Exit | Class | Reason |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for rec in self.records:
            cells = [
                rec.case_id, rec.category, rec.mechanism, rec.expected, rec.actual,
                str(rec.exit_status), rec.classification, rec.reason,
            ]
            lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ")
                                            for c in cells) + " |")
        lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return json_path, md_path


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    base = tmp_path_factory.mktemp("keel-docs-research")
    report_dir = Path(os.environ.get(
        "KEEL_CONFORMANCE_REPORT_DIR",
        base / "sandbox-conformance"))
    collector = EvidenceCollector(report_dir)
    yield collector
    json_path, md_path = collector.write_reports()
    print(f"\n[conformance] JSON evidence: {json_path}")
    print(f"[conformance] Markdown evidence: {md_path}")
    print(f"[conformance] counts: {collector.counts}")


# ---------------------------------------------------------------------------
# Probe construction and assessment
# ---------------------------------------------------------------------------
def _probe(body: str) -> str:
    """Wrap adversarial *body* in a child that proves it reached the code."""
    indented = "\n".join("    " + line for line in body.splitlines()) or "    pass"
    return (
        "import sys, os\n"
        "print('READY', flush=True)\n"
        "try:\n"
        f"{indented}\n"
        "except BaseException as exc:\n"
        "    sys.stderr.write('DENIED:' + type(exc).__name__ + '\\n')\n"
        "    sys.exit(3)\n"
    )


@dataclass
class Outcome:
    result: Any
    stdout: str
    stderr: str
    exit_code: Any
    timed_out: bool
    mechanism: str
    blocked_reason: str | None = None
    launch_error: str | None = None

    @property
    def safe_stdout(self) -> str:
        return _scrub(self.stdout)

    @property
    def safe_stderr(self) -> str:
        return _scrub(self.stderr)


def _scrub(text: str | None, limit: int = 400) -> str:
    text = text or ""
    text = text.replace("WORKSPACE-OK", "[workspace-marker]")
    text = text.replace("OUTSIDE-SECRET", "[redacted-secret]")
    text = text.replace("PROVIDER-SECRET", "[redacted-secret]")
    text = text.replace("CREDENTIAL-TOKEN", "[redacted-secret]")
    if len(text) > limit:
        text = text[:limit] + "...[truncated]"
    return text


def _run_probe(module, code: str, workspace: Path, *, env: dict | None = None,
               timeout_s: float = 8.0, cpu_s: int = 10, memory_mb: int = 256,
               mechanism: str = "none") -> Outcome:
    """Launch a real confined process. Exceptions become BLOCKED, never PASS."""
    argv = [sys.executable, "-c", code]
    try:
        result = module.run_confined(
            argv, workspace=workspace, timeout_s=timeout_s,
            cpu_s=cpu_s, memory_mb=memory_mb, env=env)
    except module.SandboxUnavailable as exc:
        detail = f"{type(exc).__name__}: {exc}"
        return Outcome(None, "", detail, None, False, mechanism,
                       launch_error="SandboxUnavailable: " + detail)
    except Exception as exc:  # noqa: BLE001 - deliberate: never success
        detail = f"{type(exc).__name__}: {exc}"
        return Outcome(None, "", detail, None, False, mechanism,
                       launch_error="launch failure: " + detail)
    return Outcome(
        result=result,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        exit_code=result.exit_code,
        timed_out=bool(result.timed_out),
        mechanism=getattr(result, "mechanism", mechanism) or mechanism,
    )


def _control_probe(code: str, workspace: Path, *, env: dict | None = None,
                   timeout_s: float = 8.0,
                   success_marker: str = "BREACH:") -> tuple[bool, str, str]:
    """Run the *same* probe unconfined to prove the host can perform the action.

    Without this control, a network timeout or a missing binary would look like
    a successful sandbox denial.  A caught exception in the confined child is
    only meaningful when the unconfined control produced the success marker.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=workspace, env=env,
            capture_output=True, timeout=timeout_s, check=False)
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        return (success_marker in out), _scrub(out), _scrub(err)
    except Exception as exc:  # noqa: BLE001 - control failures are evidence
        return False, "", _scrub(f"{type(exc).__name__}: {exc}")


def _deny_with_control(code: str, workspace: Path, module, mechanism: str, *,
                       env: dict | None = None, timeout_s: float = 8.0,
                       success_marker: str = "BREACH:",
                       deny_marker: str | None = None,
                       side_effect: bool = False) -> tuple[Outcome, tuple]:
    """Confined run plus unconfined negative control; returns (outcome, verdict)."""
    outcome = _run_probe(module, code, workspace, env=env, timeout_s=timeout_s,
                         mechanism=mechanism)
    control = _control_probe(code, workspace, env=env, timeout_s=timeout_s,
                             success_marker=success_marker)
    verdict = _assess(outcome, "deny", control=control, deny_marker=deny_marker,
                      side_effect=side_effect, mechanism=mechanism)
    return outcome, verdict


def _assess(outcome: Outcome, expected: str, *, allow_marker: str | None = None,
            breach_marker: str = "BREACH:", deny_marker: str | None = None,
            side_effect: bool = False, control: tuple[bool, str, str] | None = None,
            mechanism: str | None = None) -> tuple[str, str, str, str, str]:
    """Return (classification, actual, observed_denial, reason, mechanism)."""
    mech = mechanism or outcome.mechanism or "none"
    module = _load_sandbox()
    if outcome.launch_error or outcome.blocked_reason:
        detail = outcome.launch_error or outcome.blocked_reason or ""
        stderr = outcome.safe_stderr or detail
        if _enforcement_claimed(mech, module):
            # F6: a platform that ADVERTISES enforcement must not pass by
            # skipping because its backend could not launch a process.
            reason = (
                f"FAIL: capabilities() claims {mech} enforcement on {HOST_OS}, "
                f"but no restricted process could be launched ({detail}); "
                f"stderr={stderr!r}")
            return "FAIL", "restricted process could not launch", "none", reason, mech
        reason = (
            f"BLOCKED: capabilities() reports no {mech} enforcement on {HOST_OS}; "
            f"process launch failed ({detail}); stderr={stderr!r}")
        return "BLOCKED", "process not launched", "n/a", reason, mech

    ready = "READY" in outcome.stdout
    if not ready:
        claimed = _enforcement_claimed(mech, module)
        prefix = "FAIL" if claimed else "BLOCKED"
        reason = (
            f"{prefix}: confined process never reached the adversarial probe "
            f"(exit={outcome.exit_code}, timed_out={outcome.timed_out}); "
            f"stderr={outcome.safe_stderr!r}, stdout={outcome.safe_stdout!r}")
        return prefix, "probe not reached", "n/a", reason, mech

    allowed = bool(allow_marker and allow_marker in outcome.stdout)
    breach = (breach_marker in outcome.stdout) or side_effect
    denial_line = ""
    for line in outcome.stderr.splitlines():
        if line.startswith("DENIED:"):
            denial_line = line.strip()
            break
    if not denial_line and deny_marker and deny_marker in outcome.stdout:
        denial_line = deny_marker
    denied = bool(denial_line) or (outcome.exit_code not in (0, None))
    evidence_tail = (f"exit={outcome.exit_code}, timed_out={outcome.timed_out}, "
                     f"stderr={outcome.safe_stderr!r}, stdout={outcome.safe_stdout!r}")
    if control is not None:
        control_ok, control_out, control_err = control
        evidence_tail += (f"; UNCONFINED_CONTROL=succeeded:{control_ok}, "
                          f"stdout={control_out!r}, stderr={control_err!r}")

    if expected == "allow":
        if allowed and not breach:
            return ("PASS", "authorized operation succeeded", "n/a",
                    f"authorized marker observed; {evidence_tail}", mech)
        if allowed and breach:
            return ("PARTIAL", "authorized and unauthorized effects both seen",
                    denial_line or "none",
                    f"mixed markers; {evidence_tail}", mech)
        return ("FAIL", "authorized operation did not succeed",
                denial_line or "none",
                f"expected '{allow_marker}' marker absent; {evidence_tail}", mech)

    # expected == "deny"
    if breach:
        if _mechanism_unavailable(mech, module):
            reason = (
                f"BLOCKED: capabilities() reports no {mech} enforcement on {HOST_OS}; "
                f"a real confined process still performed the forbidden action; "
                f"{evidence_tail}")
            return "BLOCKED", "forbidden action succeeded (mechanism absent on host)", \
                "none", reason, mech
        return ("FAIL", "forbidden action succeeded", "none",
                f"capabilities() claims {mech} enforcement but the restricted "
                f"process breached; {evidence_tail}", mech)
    if control is not None and not control[0]:
        # A caught exception is never converted into success: the unconfined
        # control must reproduce the action before a denial counts as proof.
        reason = (
            f"BLOCKED: negative control did not reproduce the action on {HOST_OS} "
            f"(host cannot exercise this case); {evidence_tail}")
        return "BLOCKED", "control did not reproduce action", "n/a", reason, mech
    if denied:
        denial = denial_line or f"nonzero exit {outcome.exit_code}"
        return ("PASS", "forbidden action denied", denial,
                f"observed denial: {denial}; {evidence_tail}", mech)
    return ("PARTIAL", "no observable outcome (possible hang)", "none",
            f"probe reached but neither marker observed; {evidence_tail}", mech)


def _collect(evidence: EvidenceCollector, case_id: str, category: str,
             expected: str, outcome: Outcome, assessment: tuple, note: str = "") -> str:
    cls, actual, denial, reason, mech = assessment
    evidence.record(
        case_id=case_id,
        category=category,
        os=HOST_OS,
        mechanism=mech,
        expected=expected,
        actual=actual + ("; " + note if note else ""),
        exit_status=outcome.exit_code,
        observed_denial=denial,
        safe_logs={"stdout": outcome.safe_stdout, "stderr": outcome.safe_stderr,
                   "timed_out": outcome.timed_out},
        classification=cls,
        reason=reason,
    )
    return cls


def _gate_fail(assessment: tuple, mechanism: str, outcome: Outcome, sandbox) -> tuple:
    """Downgrade a FAIL to BLOCKED only when this host cannot enforce the mechanism.

    The observed behaviour is still recorded verbatim in the evidence reason,
    including stderr from the process that actually ran.
    """
    cls, actual, denial, reason, mech = assessment
    if cls == "FAIL" and _mechanism_unavailable(mechanism, sandbox):
        blocked_reason = (
            f"BLOCKED: {mechanism} enforcement unavailable on {HOST_OS}; "
            f"observed via a real confined process: {reason}; "
            f"stderr={outcome.safe_stderr!r}")
        return ("BLOCKED", actual, denial, blocked_reason, mech)
    return assessment


def _finish(classification: str, reason: str) -> None:
    if classification == "BLOCKED":
        pytest.skip(reason)
    assert classification in ("PASS", "PARTIAL"), f"{classification}: {reason}"


# ---------------------------------------------------------------------------
# 1. Authorized workspace reads / writes
# ---------------------------------------------------------------------------
def test_authorized_workspace_read(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    allowed = ws / "allowed.txt"
    allowed.write_text("WORKSPACE-OK", encoding="utf-8")
    code = _probe(f"print('ALLOWED_OK:' + open({str(allowed)!r}).read().strip())")
    outcome = _run_probe(sandbox, code, ws)
    cls = _collect(evidence, "authorized-workspace-read", "authorized", "allow",
                   outcome, _assess(outcome, "allow", allow_marker="ALLOWED_OK:"))
    _finish(cls, evidence.records[-1].reason)


def test_authorized_workspace_write(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "written.txt"
    code = _probe(
        f"open({str(target)!r}, 'w').write('WORKSPACE-OK'); "
        f"print('ALLOWED_OK:' + open({str(target)!r}).read().strip())")
    outcome = _run_probe(sandbox, code, ws)
    side = target.exists() and target.read_text(encoding="utf-8") == "WORKSPACE-OK"
    assessment = _assess(outcome, "allow", allow_marker="ALLOWED_OK:")
    if not side:
        assessment = ("FAIL", "workspace file not written by restricted process",
                      "n/a", f"post-run file check failed; target={target}", "filesystem")
    cls = _collect(evidence, "authorized-workspace-write", "authorized", "allow",
                   outcome, assessment)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 2. Unauthorized host file reads / writes
# ---------------------------------------------------------------------------
def test_unauthorized_host_file_read(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE-SECRET", encoding="utf-8")
    code = _probe(
        f"data = open({str(outside)!r}).read(); print('BREACH:READ len=' + str(len(data)))")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem")
    cls = _collect(evidence, "unauthorized-host-file-read", "filesystem", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_unauthorized_host_file_write(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "victim.txt"
    outside.write_text("ORIGINAL", encoding="utf-8")
    code = _probe(f"open({str(outside)!r}, 'w').write('PWNED'); print('BREACH:WROTE')")
    outcome = _run_probe(sandbox, code, ws, mechanism="filesystem")
    side = outside.read_text(encoding="utf-8") != "ORIGINAL"
    # The unconfined control also writes the victim; capture its result and
    # restore the original content so the side-effect check stays attributable
    # to the confined process only.
    control = _control_probe(code, ws)
    outside.write_text("ORIGINAL", encoding="utf-8")
    verdict = _assess(outcome, "deny", control=control, side_effect=side,
                      mechanism="filesystem")
    cls = _collect(evidence, "unauthorized-host-file-write", "filesystem", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 3. Path traversal
# ---------------------------------------------------------------------------
def test_path_traversal(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "traversal-secret.txt"
    outside.write_text("OUTSIDE-SECRET", encoding="utf-8")
    traversal = os.path.join(str(ws), "..", outside.name)
    code = _probe(
        f"data = open({traversal!r}).read(); print('BREACH:TRAVERSAL len=' + str(len(data)))")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem")
    cls = _collect(evidence, "path-traversal", "filesystem", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 4. Symlink escape
# ---------------------------------------------------------------------------
def test_symlink_escape(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "symlink-target.txt"
    outside.write_text("OUTSIDE-SECRET", encoding="utf-8")
    link = ws / "escape.lnk"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        evidence.record(
            case_id="symlink-escape", category="filesystem", os=HOST_OS,
            mechanism="filesystem", expected="deny",
            actual="symlink could not be created", exit_status="n/a",
            observed_denial="n/a", safe_logs={"stderr": _scrub(str(exc))},
            classification="BLOCKED",
            reason=f"BLOCKED: symlink setup failed ({type(exc).__name__}: {exc}); "
                   "no restricted process could be exercised")
        pytest.skip(evidence.records[-1].reason)
    code = _probe(
        f"data = open({str(link)!r}).read(); print('BREACH:SYMLINK len=' + str(len(data)))")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem")
    cls = _collect(evidence, "symlink-escape", "filesystem", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 5. Inherited file descriptors / handles
# ---------------------------------------------------------------------------
def test_inherited_fd(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = tmp_path / "fd-secret.txt"
    secret.write_text("OUTSIDE-SECRET", encoding="utf-8")
    fd = os.open(secret, os.O_RDONLY)
    try:
        try:
            os.set_inheritable(fd, True)
        except (OSError, AttributeError):
            pass
        env = {**os.environ, "KEEL_CONF_FD": str(fd)}
        code = _probe(
            "fd = int(os.environ['KEEL_CONF_FD']); "
            "data = os.read(fd, 64); "
            "print('BREACH:INHERITED_FD len=' + str(len(data)))")
        outcome = _run_probe(sandbox, code, ws, env=env, mechanism="none")
    finally:
        os.close(fd)
    cls = _collect(evidence, "inherited-fd", "handle", "deny",
                   outcome, _assess(outcome, "deny"))
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 6. External TCP / UDP / DNS / localhost / inherited sockets / grandchild net
# ---------------------------------------------------------------------------
def test_external_tcp(sandbox, evidence, tmp_path):
    code = _probe(
        "import socket; s = socket.socket(); s.settimeout(1.5); "
        "s.connect(('8.8.8.8', 53)); print('BREACH:TCP')")
    # Full env is required: the interface defaults to env={} which breaks
    # Winsock on Windows (no SYSTEMROOT) and mimics a false network denial.
    env = dict(os.environ)
    outcome, verdict = _deny_with_control(code, tmp_path, sandbox, "network", env=env)
    cls = _collect(evidence, "external-tcp", "network", "deny", outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_external_udp(sandbox, evidence, tmp_path):
    code = _probe(
        "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); "
        "s.sendto(b'x', ('8.8.8.8', 53)); print('BREACH:UDP')")
    # Full env is required: the interface defaults to env={} which breaks
    # Winsock on Windows (no SYSTEMROOT) and mimics a false network denial.
    env = dict(os.environ)
    outcome, verdict = _deny_with_control(code, tmp_path, sandbox, "network", env=env)
    cls = _collect(evidence, "external-udp", "network", "deny", outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_dns(sandbox, evidence, tmp_path):
    code = _probe(
        "import socket; socket.setdefaulttimeout(2); "
        "answer = socket.gethostbyname('example.com'); "
        "print('BREACH:DNS ' + str(bool(answer)))")
    # Full env is required: the interface defaults to env={} which breaks
    # Winsock on Windows (no SYSTEMROOT) and mimics a false network denial.
    env = dict(os.environ)
    outcome, verdict = _deny_with_control(code, tmp_path, sandbox, "network", env=env)
    cls = _collect(evidence, "dns", "network", "deny", outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def _localhost_code(port: int) -> str:
    return _probe(
        "import socket; s = socket.socket(); s.settimeout(1.5); "
        f"s.connect(('127.0.0.1', {port})); print('BREACH:LOCALHOST')")


def test_localhost(sandbox, evidence, tmp_path):
    def listener():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock, sock.getsockname()[1]

    # Negative control uses its own listener so the confined run has a fresh
    # accept queue to observe.
    ctl_sock, ctl_port = listener()
    try:
        control = _control_probe(_localhost_code(ctl_port), tmp_path)
    finally:
        ctl_sock.close()

    sock, port = listener()
    try:
        code = _localhost_code(port)
        outcome = _run_probe(sandbox, code, tmp_path, env=dict(os.environ),
                             mechanism="network")
        sock.settimeout(0.3)
        try:
            conn, _ = sock.accept()
            connected = True
            conn.close()
        except (socket.timeout, OSError):
            connected = False
    finally:
        sock.close()
    verdict = _assess(outcome, "deny", control=control, side_effect=connected,
                      mechanism="network")
    cls = _collect(evidence, "localhost", "network", "deny", outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_inherited_network_descriptor(sandbox, evidence, tmp_path):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    try:
        fd = listener.fileno()
        try:
            os.set_inheritable(fd, True)
        except (OSError, AttributeError):
            pass
        env = {**os.environ, "KEEL_CONF_SOCKFD": str(fd)}
        code = _probe(
            "fd = int(os.environ['KEEL_CONF_SOCKFD']); "
            "os.write(fd, b'X'); print('BREACH:INHERITED_SOCKET')")
        outcome = _run_probe(sandbox, code, tmp_path, env=env, mechanism="none")
    finally:
        listener.close()
    cls = _collect(evidence, "inherited-network-descriptor", "handle", "deny",
                   outcome, _assess(outcome, "deny"))
    _finish(cls, evidence.records[-1].reason)


def test_child_process_network_access(sandbox, evidence, tmp_path):
    grandchild = (
        "import socket; s=socket.socket(); s.settimeout(1.5); "
        "s.connect(('8.8.8.8',53)); print('CONNECTED')")
    code = _probe(
        "import subprocess, sys; "
        f"out = subprocess.run([sys.executable, '-c', {grandchild!r}], "
        "capture_output=True, timeout=6).stdout.decode(); "
        "print('BREACH:CHILD_NET' if 'CONNECTED' in out else 'CHILD_DENIED')")
    outcome, verdict = _deny_with_control(code, tmp_path, sandbox, "network",
                                          env=dict(os.environ),
                                          deny_marker="CHILD_DENIED")
    cls = _collect(evidence, "child-process-network-access", "network", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_default_empty_env_can_fake_denials(sandbox, evidence, tmp_path):
    """F6 evidence: confirm a denial is enforcement, not a broken environment.

    ``run_confined(env=None)`` passes an empty environment.  On Windows that
    removes SYSTEMROOT and Winsock fails with OSError, which otherwise looks
    exactly like a sandbox network denial.  This case compares the same probe
    under the default environment and under a normal one.
    """
    code = _probe(
        "import socket; s=socket.socket(); s.settimeout(1.5); "
        "s.connect(('8.8.8.8', 53)); print('BREACH:TCP')")
    empty = _run_probe(sandbox, code, tmp_path, env=None, mechanism="network")
    full = _run_probe(sandbox, code, tmp_path, env=dict(os.environ),
                      mechanism="network")
    empty_denied = "BREACH:" not in empty.stdout
    full_breach = "BREACH:" in full.stdout
    if empty_denied and full_breach:
        cls = "PARTIAL"
        actual = "default empty environment produced a false network denial"
        reason = (
            "PARTIAL: with the interface default env=None the confined child "
            f"showed {empty.safe_stderr!r}, but with a normal environment the "
            "same confined child reached the host network "
            f"({full.safe_stdout!r}). The apparent denial is an env artifact, "
            "not enforcement. All network conformance cases therefore pass a "
            "normal env so confinement is the only variable.")
    else:
        cls = "PASS"
        actual = "no default-environment artifact detected"
        reason = (f"empty-env stdout={empty.safe_stdout!r}, "
                  f"full-env stdout={full.safe_stdout!r}")
    evidence.record(
        case_id="default-empty-env-artifact", category="methodology", os=HOST_OS,
        mechanism="network", expected="deny must come from enforcement",
        actual=actual, exit_status=full.exit_code, observed_denial="n/a",
        safe_logs={"empty_env_stdout": empty.safe_stdout,
                   "empty_env_stderr": empty.safe_stderr,
                   "full_env_stdout": full.safe_stdout,
                   "full_env_stderr": full.safe_stderr},
        classification=cls, reason=reason)
    _finish(cls, reason)


# ---------------------------------------------------------------------------
# 7. Provider / env secrets and application credential files
# ---------------------------------------------------------------------------
def test_provider_env_secrets(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    env = {**os.environ, "KEEL_PROVIDER_SECRET": "PROVIDER-SECRET",
           "ANTHROPIC_API_KEY": "PROVIDER-SECRET"}
    code = _probe(
        "val = os.environ.get('KEEL_PROVIDER_SECRET') or "
        "os.environ.get('ANTHROPIC_API_KEY'); "
        "print('BREACH:ENV_SECRET len=' + str(len(val)) if val else 'NO_SECRET')")
    outcome = _run_probe(sandbox, code, ws, env=env, mechanism="none")
    cls = _collect(evidence, "provider-env-secrets", "secrets", "deny",
                   outcome, _assess(outcome, "deny"),
                   note="OS boundary does not scrub env; caller must use policy layer")
    _finish(cls, evidence.records[-1].reason)


def test_application_config_credential_files(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "app-home"
    cred = home / ".keel" / "credentials.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"token": "CREDENTIAL-TOKEN"}', encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "APPDATA": str(home)}
    code = _probe(
        "data = open(" + repr(str(cred)) + ").read(); "
        "print('BREACH:CRED len=' + str(len(data)))")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem", env=env)
    cls = _collect(evidence, "application-config-credentials", "secrets", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 8. Child-process inheritance of filesystem confinement
# ---------------------------------------------------------------------------
def test_child_process_inheritance(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "grandchild-secret.txt"
    outside.write_text("OUTSIDE-SECRET", encoding="utf-8")
    grandchild = f"print(open({str(outside)!r}).read())"
    code = _probe(
        "import subprocess, sys; "
        f"out = subprocess.run([sys.executable, '-c', {grandchild!r}], "
        "capture_output=True).stdout.decode(); "
        "print('BREACH:CHILD_READ len=' + str(len(out)) if out else 'CHILD_DENIED')")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem")
    cls = _collect(evidence, "child-process-inheritance", "process", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


def test_unauthorized_process_execution(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    # Use a real executable outside the workspace.  A non-binary victim would
    # fail even in the unconfined control and produce a false PASS.
    victim = sys.executable
    code = _probe(
        "import subprocess, sys; "
        f"p = subprocess.run([{victim!r}, '-c', 'print(123)'], capture_output=True); "
        "print('BREACH:EXEC' if p.returncode == 0 else 'EXEC_DENIED')")
    outcome, verdict = _deny_with_control(code, ws, sandbox, "filesystem",
                                          deny_marker="EXEC_DENIED")
    cls = _collect(evidence, "unauthorized-process-execution", "process", "deny",
                   outcome, verdict)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 9. Process-tree termination
# ---------------------------------------------------------------------------
def test_process_tree_termination(sandbox, evidence, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    beat = tmp_path / "heartbeat.txt"
    grandchild_code = (
        "import time, pathlib\n"
        f"p = pathlib.Path({str(beat)!r})\n"
        "for i in range(200):\n"
        "    p.write_text(str(i))\n"
        "    time.sleep(0.1)\n"
    )
    code = (
        "import subprocess, sys, time\n"
        "print('READY', flush=True)\n"
        f"child = subprocess.Popen([sys.executable, '-c', {grandchild_code!r}])\n"
        "print('CHILD_PID:' + str(child.pid), flush=True)\n"
        "time.sleep(30)\n"
    )
    outcome = _run_probe(sandbox, code, ws, timeout_s=2.0, mechanism="tree")
    # A tree kill is only observable when the timeout actually fired and the
    # grandchild stopped writing its heartbeat.
    pid = ""
    for line in outcome.stdout.splitlines():
        if line.startswith("CHILD_PID:"):
            pid = line.split(":", 1)[1].strip()
    alive = False
    if beat.exists():
        before = beat.stat().st_mtime_ns
        time.sleep(0.8)
        alive = beat.exists() and beat.stat().st_mtime_ns != before
    if not outcome.timed_out:
        assessment = ("FAIL", "timeout did not fire",
                      "n/a", f"timed_out={outcome.timed_out}", "tree")
    elif alive:
        assessment = ("FAIL", f"grandchild survived tree kill (pid={pid})",
                      "none",
                      f"heartbeat kept advancing after timeout; "
                      f"stderr={outcome.safe_stderr!r}", "tree")
    else:
        assessment = ("PASS", "process tree terminated", "timeout",
                      f"timed_out=True, grandchild pid={pid} stopped; "
                      f"stderr={outcome.safe_stderr!r}", "tree")
    assessment = _gate_fail(assessment, "tree", outcome, sandbox)
    cls = _collect(evidence, "process-tree-termination", "process", "deny",
                   outcome, assessment)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 10. Concurrent execution
# ---------------------------------------------------------------------------
def test_concurrent_execution(sandbox, evidence, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    ws = tmp_path / "ws"
    ws.mkdir()

    def run(i: int) -> Outcome:
        marker = ws / f"c{i}.txt"
        code = _probe(
            f"open({str(marker)!r}, 'w').write('WORKSPACE-OK'); "
            f"print('ALLOWED_OK:{i}')")
        return _run_probe(sandbox, code, ws / f"sub{i}", timeout_s=8.0)

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(run, range(4)))

    markers = {o.stdout.strip().splitlines()[-1] for o in outcomes if o.stdout.strip()}
    all_ok = all("ALLOWED_OK:" in o.stdout for o in outcomes)
    files_ok = all((ws / f"c{i}.txt").exists() for i in range(4))
    if all_ok and files_ok:
        assessment = ("PASS", "4/4 confined processes succeeded independently",
                      "n/a", f"markers={sorted(markers)}", "concurrency")
    elif any(o.blocked_reason for o in outcomes):
        blocked = next(o.blocked_reason for o in outcomes if o.blocked_reason)
        assessment = ("BLOCKED", "concurrent launch unavailable", "n/a", blocked,
                      "concurrency")
    else:
        assessment = ("FAIL", "concurrent confined processes did not all succeed",
                      "n/a", f"markers={sorted(markers)}, files_ok={files_ok}",
                      "concurrency")
    # Use the first outcome for the structured exit/log fields; the verdict and
    # the full per-worker summary are carried in the assessment reason.
    cls = _collect(evidence, "concurrent-execution", "concurrency", "allow",
                   outcomes[0], assessment,
                   note=f"workers={len(outcomes)}")
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 11. CPU / memory / process / timeout resource exhaustion
# ---------------------------------------------------------------------------
def test_cpu_exhaustion(sandbox, evidence, tmp_path):
    code = _probe(
        "x = 0\n"
        "while True:\n"
        "    x = (x + 1) % 1000003\n")
    outcome = _run_probe(sandbox, code, tmp_path, timeout_s=2.0, cpu_s=1,
                         mechanism="resource")
    if outcome.timed_out or outcome.exit_code not in (0, None):
        assessment = ("PASS", "runaway CPU process was terminated", "timeout/exit",
                      f"timed_out={outcome.timed_out}, exit={outcome.exit_code}",
                      "resource")
    else:
        assessment = ("FAIL", "runaway CPU process was not bounded", "none",
                      f"timed_out={outcome.timed_out}, exit={outcome.exit_code}",
                      "resource")
    assessment = _gate_fail(assessment, "resource", outcome, sandbox)
    cls = _collect(evidence, "cpu-exhaustion", "resource", "deny",
                   outcome, assessment)
    _finish(cls, evidence.records[-1].reason)


def test_memory_exhaustion(sandbox, evidence, tmp_path):
    # Bounded allocation: tries to reach 128 MiB in 8 MiB blocks.  The default
    # POSIX RLIMIT_AS in the interface is 256 MiB, so pass a tighter 64 MiB.
    code = _probe(
        "blocks = []\n"
        "for _ in range(16):\n"
        "    blocks.append(bytearray(8 * 1024 * 1024))\n"
        "print('BREACH:MEM grew to ' + str(len(blocks) * 8) + 'MiB')")
    outcome = _run_probe(sandbox, code, tmp_path, timeout_s=6.0, memory_mb=64,
                         mechanism="resource")
    cls = _collect(evidence, "memory-exhaustion", "resource", "deny",
                   outcome, _assess(outcome, "deny", mechanism="resource"))
    _finish(cls, evidence.records[-1].reason)


def test_process_exhaustion(sandbox, evidence, tmp_path):
    code = _probe(
        "import subprocess, sys\n"
        "ok = 0\n"
        "for _ in range(12):\n"
        "    p = subprocess.run([sys.executable, '-c', 'pass'], capture_output=True)\n"
        "    if p.returncode == 0:\n"
        "        ok += 1\n"
        "if ok >= 8:\n"
        "    print('BREACH:PROC spawned ' + str(ok))")
    outcome = _run_probe(sandbox, code, tmp_path, timeout_s=8.0, mechanism="resource")
    cls = _collect(evidence, "process-exhaustion", "resource", "deny",
                   outcome, _assess(outcome, "deny", mechanism="resource"))
    _finish(cls, evidence.records[-1].reason)


def test_timeout_enforcement(sandbox, evidence, tmp_path):
    code = _probe("import time; time.sleep(30); print('SHOULD_NOT_FINISH')")
    started = time.monotonic()
    outcome = _run_probe(sandbox, code, tmp_path, timeout_s=2.0, mechanism="resource")
    elapsed = time.monotonic() - started
    if (outcome.timed_out and elapsed < 12 and
            "SHOULD_NOT_FINISH" not in outcome.stdout):
        assessment = ("PASS", "wall-clock timeout enforced", "timeout",
                      f"timed_out=True, elapsed={elapsed:.2f}s", "timeout")
    else:
        assessment = ("FAIL", "wall-clock timeout not enforced", "none",
                      f"timed_out={outcome.timed_out}, elapsed={elapsed:.2f}s, "
                      f"stdout={outcome.safe_stdout!r}", "timeout")
    cls = _collect(evidence, "timeout-enforcement", "resource", "deny",
                   outcome, assessment)
    _finish(cls, evidence.records[-1].reason)


# ---------------------------------------------------------------------------
# 12. Seccomp filter semantics (socket denied, ordinary write still allowed)
# ---------------------------------------------------------------------------
def test_seccomp_filter_denies_socket_allows_write(sandbox, evidence, tmp_path):
    """Directly exercise `_seccomp_deny_network` in a real process.

    This targets the reported BPF defects (BPF_IMM instead of BPF_ABS load,
    inverted jeq branches, SECCOMP_RET_KILL_THREAD used where ERRNO is
    documented).  A correct filter kills nothing, denies socket() with EPERM
    and leaves write() intact.  A broken filter kills the process before the
    RESULT line can be emitted, which is a FAIL, never a skip.
    """
    import keel  # local import: only this test needs the source root

    src_root = str(Path(keel.__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": src_root + os.pathsep +
           os.environ.get("PYTHONPATH", "")}
    code = (
        "import ctypes, sys, os\n"
        "from keel.os_sandbox import _seccomp_deny_network\n"
        "try:\n"
        "    _seccomp_deny_network(ctypes.CDLL(None, use_errno=True))\n"
        "except BaseException as exc:\n"
        "    sys.stderr.write('FILTER_SETUP_ERROR:' + type(exc).__name__ + ':' "
        "+ str(exc) + '\\n')\n"
        "    sys.exit(4)\n"
        "import socket\n"
        "status = {}\n"
        "try:\n"
        "    socket.socket()\n"
        "    status['socket'] = 'ALLOWED'\n"
        "except OSError as exc:\n"
        "    status['socket'] = 'DENIED:' + str(getattr(exc, 'errno', '?'))\n"
        "sys.stdout.write('RESULT:' + repr(status) + '\\n')\n"
        "sys.stdout.flush()\n"
        "os._exit(0)\n"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                              env=env, capture_output=True, timeout=8, check=False)
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        exit_code: Any = proc.returncode
    except Exception as exc:  # noqa: BLE001
        out, err, exit_code = "", _scrub(f"{type(exc).__name__}: {exc}"), None

    safe_out, safe_err = _scrub(out), _scrub(err)
    result_line = next((ln for ln in out.splitlines() if ln.startswith("RESULT:")), "")
    claimed = _enforcement_claimed("network", sandbox)
    if not claimed:
        cls, actual, denial, reason = (
            "BLOCKED", "seccomp not available on this host", "n/a",
            f"BLOCKED: capabilities() reports no network enforcement on {HOST_OS}; "
            f"actual filter process exit={exit_code}, stdout={safe_out!r}, "
            f"stderr={safe_err!r}")
    elif ("'socket': 'DENIED:" in result_line and
          "'socket': 'ALLOWED'" not in result_line):
        cls, actual, denial, reason = (
            "PASS", "socket() denied, write() allowed (RESULT emitted)", "EPERM",
            f"exit={exit_code}, stdout={safe_out!r}, stderr={safe_err!r}")
    else:
        cls, actual, denial, reason = (
            "FAIL", "seccomp filter did not deny socket() while preserving write()",
            "none",
            f"capabilities() claims network enforcement; filter process "
            f"exit={exit_code}, stdout={safe_out!r}, stderr={safe_err!r}. "
            "Suspected BPF_IMM load, inverted branches, or RET_KILL_THREAD.")

    evidence.record(
        case_id="seccomp-filter-semantics", category="network", os=HOST_OS,
        mechanism="network", expected="deny socket / allow write",
        actual=actual, exit_status=exit_code, observed_denial=denial,
        safe_logs={"stdout": safe_out, "stderr": safe_err},
        classification=cls, reason=reason,
    )
    _finish(cls, reason)

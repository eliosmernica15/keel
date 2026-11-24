"""Responsible-use disclosures, checklist, disclaimer and builder rules (D5.x).

This module is the single source of truth for Keel's safety/trust copy. It is
deliberately stdlib-only and pure: immutable data plus small policy functions,
with no file IO, no host inspection, no network and no clock/random input.
``keel/docs/RESPONSIBLE-USE.md`` is generated verbatim from this module by
``render_document()``; the tests assert that equality.

Contracts implemented (all P0, section 6 of the master plan):

* D5.1 - a plain statement that the software executes model-generated
  code/commands, loads third-party plugins and accesses network, processes,
  credentials and files, and that defects, misconfiguration, malicious input
  or untrusted plugins can damage the host;
* D5.2 - the exact risk-reduction wording: sandboxing, approvals and
  permissions reduce risk but do not guarantee isolation, so they must not be
  the sole control for untrusted workloads;
* D5.3 - the responsible-use checklist plus the two onboarding wizard offers;
* D5.4 - no-warranty / no-liability data referencing the license (draft for
  legal review, G5);
* D5.5 - the builder's host-sandbox-failure rule: a command that fails because
  the *dev* sandbox blocked credentials/network/IPC is retried *unchanged*
  with the *narrowest* escalation, only with evidence of the sandbox cause;
  test failures and the *product* sandbox are never bypassed.

The rule in D5.5 is fail-closed. There is no representation for an
"everything off" escalation: an unproven cause, a changed command, a broad or
unknown escalation, or a bypass attempt always produces ``Decision.STOP``
with ``Escalation.NONE``. A stop is never a silent downgrade - it carries a
written reason.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# D5.1 / D5.2 - typed disclosure statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Disclosure:
    """One immutable, user-facing safety statement."""

    id: str
    title: str
    text: str
    feature_id: str
    audience: str = "all users"

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


EXECUTION_DISCLOSURE = Disclosure(
    id="executes-model-generated-code",
    title="What Keel can do to your host",
    feature_id="D5.1",
    text=(
        "Keel executes model-generated code and commands. It can also "
        "load third-party plugins and access your network, processes, "
        "credentials and files. Defects, misconfiguration, malicious input or "
        "untrusted plugins can damage the host, destroy data or leak secrets. "
        "Treat each agent run as you would treat running an untrusted program."
    ),
)

SANDBOX_LIMITS_DISCLOSURE = Disclosure(
    id="sandbox-is-risk-reduction-not-isolation",
    title="Sandboxing reduces risk; it does not guarantee isolation",
    feature_id="D5.2",
    text=(
        "Sandboxing, approvals and permissions reduce risk but do not "
        "guarantee isolation. Do not rely on them as the sole control for "
        "untrusted workloads."
    ),
)

DISCLOSURES: tuple[Disclosure, ...] = (
    EXECUTION_DISCLOSURE,
    SANDBOX_LIMITS_DISCLOSURE,
)


def disclosure_by_id(disclosure_id: Any) -> Disclosure | None:
    """Exact lookup; an unknown id returns None (no guessed disclosure)."""
    for disclosure in DISCLOSURES:
        if disclosure.id == disclosure_id:
            return disclosure
    return None


# ---------------------------------------------------------------------------
# D5.3 - responsible-use checklist and onboarding wizard offers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChecklistItem:
    """One actionable responsible-use step shown during onboarding."""

    id: str
    title: str
    text: str
    feature_id: str = "D5.3"


CHECKLIST: tuple[ChecklistItem, ...] = (
    ChecklistItem(
        id="least-privilege",
        title="Use least privilege",
        text=(
            "Give the agent the minimum permissions, file scope, network "
            "access and token rights it needs. Prefer read-only, one-time "
            "approvals and ordinary user accounts; avoid administrator/root "
            "accounts and standing 'always allow' rules."
        ),
    ),
    ChecklistItem(
        id="disposable-vm",
        title="Run in a disposable VM or container",
        text=(
            "Run unfamiliar projects, plugins and untrusted workloads in a "
            "disposable VM or container that you can throw away afterwards, "
            "not on a machine holding your real accounts and data."
        ),
    ),
    ChecklistItem(
        id="backups",
        title="Keep backups",
        text=(
            "Keep current, restorable backups of everything the agent can "
            "write. Confirm a backup exists before the first agent run so a "
            "mistake or a bad command can be undone."
        ),
    ),
    ChecklistItem(
        id="no-sensitive-credentials",
        title="Do not expose sensitive credentials",
        text=(
            "Do not expose production keys, tokens, passwords, SSH keys or "
            "cloud credentials in the workspace, environment, prompt, logs, "
            "screenshots or recordings. Use narrow, short-lived, test-only "
            "credentials instead."
        ),
    ),
    ChecklistItem(
        id="review-changes",
        title="Review plugins, configuration and proposed commands",
        text=(
            "Review third-party plugins, configuration changes and every "
            "proposed command before approving it. The model can be wrong or "
            "can be acting on hostile input it read from a file or the web."
        ),
    ),
)


@dataclass(frozen=True)
class WizardOffer:
    """An onboarding shortcut that maps back to a checklist item."""

    id: str
    label: str
    checklist_item_id: str
    source_id: str


WIZARD_OFFERS: tuple[WizardOffer, ...] = (
    WizardOffer(
        id="run-in-disposable-container",
        label="Run in disposable container",
        checklist_item_id="disposable-vm",
        source_id="V17",
    ),
    WizardOffer(
        id="create-backup-before-first-run",
        label="Create backup before first agent run",
        checklist_item_id="backups",
        source_id="D5.3",
    ),
)


# ---------------------------------------------------------------------------
# D5.4 - no warranty / no liability data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Disclaimer:
    """Warranty/liability copy; a draft for legal review (G5), not legal advice."""

    id: str
    title: str
    no_warranty: str
    no_liability: str
    license_reference: str
    review_status: str
    feature_id: str = "D5.4"

    def paragraphs(self) -> tuple[str, ...]:
        return (
            self.no_warranty,
            self.no_liability,
            self.license_reference,
            self.review_status,
        )

    def text(self) -> str:
        return "\n\n".join(self.paragraphs())


WARRANTY_DISCLAIMER = Disclaimer(
    id="no-warranty-no-liability",
    title="No warranty; limitation of liability",
    no_warranty=(
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, "
        "EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF "
        "MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND "
        "NON-INFRINGEMENT."
    ),
    no_liability=(
        "TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE AUTHORS AND "
        "DISTRIBUTORS ARE NOT LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, "
        "CONSEQUENTIAL, SPECIAL OR PUNITIVE DAMAGES, OR FOR LOSS OF DATA, "
        "PROFITS OR CREDENTIALS, OR FOR HOST DAMAGE ARISING FROM USE OF THE "
        "SOFTWARE, INCLUDING MODEL-GENERATED CODE, PLUGINS OR AGENT ACTIONS."
    ),
    license_reference=(
        "This software is licensed, not sold, under the license agreement "
        "(EULA) supplied with your distribution (package metadata: license = "
        "Proprietary). The EULA controls; this summary does not change it."
    ),
    review_status="Draft for legal review (G5) - not legal advice.",
)


# ---------------------------------------------------------------------------
# D5.5 - host sandbox failures rule (builder stop-list, X10.4)
# ---------------------------------------------------------------------------


class BlockedResource(str, Enum):
    """Resource classes a developer's (host) sandbox may deny."""

    NONE = "none"
    CREDENTIALS = "credentials"
    NETWORK = "network"
    IPC = "ipc"
    OTHER = "other"

    def __str__(self) -> str:
        return self.value


class Escalation(str, Enum):
    """The only permitted escalation scopes: one dev-sandbox resource each.

    There is intentionally no 'all', 'full', 'off' or 'unsandboxed' member.
    A builder cannot represent a silent downgrade with this type.
    """

    NONE = "none"  # fail-closed marker, never a permission to retry
    CREDENTIALS = "dev-sandbox-credentials"
    NETWORK = "dev-sandbox-network"
    IPC = "dev-sandbox-ipc"

    def __str__(self) -> str:
        return self.value


def narrowest_escalation(resource: Any) -> Escalation:
    """Return the narrowest scope for a proven blocked resource.

    Unknown, absent or non-sandbox causes map to ``Escalation.NONE`` so an
    unclassified failure can never be used to justify an escalation.
    """
    value = resource.value if isinstance(resource, BlockedResource) else str(
        resource or "").strip().lower()
    return {
        BlockedResource.CREDENTIALS.value: Escalation.CREDENTIALS,
        BlockedResource.NETWORK.value: Escalation.NETWORK,
        BlockedResource.IPC.value: Escalation.IPC,
    }.get(value, Escalation.NONE)


@dataclass(frozen=True)
class SandboxFailure:
    """A builder's report of a required command that failed on the host."""

    command: str
    blocked_resource: Any
    evidence: tuple[str, ...] = ()
    retry_command: str | None = None
    test_failure: bool = False
    bypass_tests: bool = False
    bypass_product_sandbox: bool = False


class Decision(str, Enum):
    RETRY = "retry-unchanged-with-narrowest-escalation"
    STOP = "stop"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class FailureDecision:
    """Typed disposition of a host-sandbox failure, with a written reason."""

    decision: Decision
    escalation: Escalation
    reason: str
    evidence: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.RETRY

    @property
    def is_stop(self) -> bool:
        return self.decision is Decision.STOP

    def as_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "escalation": self.escalation.value,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "allowed": self.allowed,
        }


def fail_closed(reason: str) -> FailureDecision:
    """Stop, with no escalation and no evidence suggesting a bypass."""
    text = str(reason or "").strip() or "sandbox cause not proven - failing closed"
    return FailureDecision(Decision.STOP, Escalation.NONE, text)


def _nonblank_evidence(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(text for text in (str(v).strip() for v in values or ()) if text)


def _rejection_reason(failure: SandboxFailure, escalation: Any) -> str:
    """Return a stop reason, or an empty string when the retry is justified."""
    # Explicit bypass attempts and real test failures are never reclassified.
    if failure.bypass_tests:
        return "never bypass tests: a failing test is not a sandbox failure"
    if failure.bypass_product_sandbox:
        return ("never bypass the product sandbox: dev-sandbox escalation is "
                "the only permitted exception")
    if failure.test_failure:
        return ("test failure reported: fix the code, do not relabel it as a "
                "sandbox failure")

    narrowest = narrowest_escalation(failure.blocked_resource)
    if narrowest is Escalation.NONE:
        return "no proven dev-sandbox cause (credentials/network/IPC) - fail closed"
    if not _nonblank_evidence(failure.evidence):
        return "no evidence of the dev-sandbox cause - fail closed"
    if (failure.retry_command is not None
            and str(failure.retry_command) != str(failure.command)):
        return "retry must run the exact same command unchanged - fail closed"
    if not isinstance(escalation, Escalation):
        return "escalation must be a typed narrowest dev-sandbox scope - fail closed"
    if escalation is not narrowest:
        return ("requested escalation is broader or unrelated to the blocked "
                "resource - fail closed")
    return ""


def evaluate_failure(failure: SandboxFailure,
                     escalation: Any = Escalation.NONE) -> FailureDecision:
    """Decide whether a failed command may be retried with a narrow escalation.

    Fail-closed by construction: a retry is authorised only when every rule
    holds - the cause is a known dev-sandbox block, it is evidenced, the
    command is unchanged, and the caller requests exactly the narrowest scope.
    Anything else stops with ``Escalation.NONE`` and a written reason.
    """
    reason = _rejection_reason(failure, escalation)
    if reason:
        return fail_closed(reason)
    narrowest = narrowest_escalation(failure.blocked_resource)
    return FailureDecision(
        Decision.RETRY,
        narrowest,
        ("Dev-sandbox cause evidenced; retry the exact same command unchanged "
         f"with the narrowest escalation ({narrowest.value}) only."),
        _nonblank_evidence(failure.evidence),
    )


@dataclass(frozen=True)
class StopRule:
    """One line of the builder stop-list (X10.4)."""

    id: str
    text: str
    feature_id: str = "D5.5"


BUILDER_STOP_RULES: tuple[StopRule, ...] = (
    StopRule(
        id="require-sandbox-evidence",
        text=("A dev-sandbox failure is real only with evidence naming the "
              "blocked credential, network or IPC resource; suspicion is not "
              "evidence."),
    ),
    StopRule(
        id="retry-unchanged",
        text=("Retry the exact same command unchanged; changing arguments "
              "makes it a new command, not a retry."),
    ),
    StopRule(
        id="narrowest-escalation-only",
        text=("Use only the narrowest escalation for the specific blocked "
              "resource; never widen it and never turn it off."),
    ),
    StopRule(
        id="never-bypass-tests",
        text="Never bypass, skip or weaken a failing test to make a command pass.",
    ),
    StopRule(
        id="never-bypass-product-sandbox",
        text=("Never disable or bypass the product sandbox; builder escalation "
              "is only for the developer's dev sandbox."),
    ),
    StopRule(
        id="fail-closed-on-unknown",
        text=("Fail closed on any unknown, mixed or unproven cause: stop and "
              "report rather than silently downgrading the sandbox."),
    ),
)


# ---------------------------------------------------------------------------
# Rendering - the Markdown document is generated from the data above
# ---------------------------------------------------------------------------


def render_safety_notice() -> str:
    """Copy for the first-run safety notice (W1.10)."""
    return "\n\n".join(
        f"{disclosure.title}: {disclosure.text}" for disclosure in DISCLOSURES
    )


def render_known_limits() -> str:
    """Copy for the Known-limits page (W7.19)."""
    return "\n\n".join((
        "The sandbox reduces the blast radius of agent actions; it does not "
        "make arbitrary code harmless.",
        SANDBOX_LIMITS_DISCLOSURE.text,
    ))


def render_checklist() -> str:
    """Numbered responsible-use checklist plus the two wizard offers."""
    lines = [f"{number}. **{item.title}** - {item.text}"
             for number, item in enumerate(CHECKLIST, start=1)]
    lines.append("")
    lines.append("If the setup wizard is available it also offers:")
    lines.extend(f"- **{offer.label}** (source: {offer.source_id})."
                 for offer in WIZARD_OFFERS)
    return "\n".join(lines)


def render_disclaimer() -> str:
    """No-warranty / no-liability paragraphs for the EULA/DISCLAIMER."""
    return "\n\n".join((WARRANTY_DISCLAIMER.title,) + WARRANTY_DISCLAIMER.paragraphs())


def render_builder_stop_rules() -> str:
    """Builder stop-list lines (D5.5 / X10.4), one rule per line."""
    return "\n".join(f"- {rule.text}" for rule in BUILDER_STOP_RULES)


def render_document() -> str:
    """Render the complete user-facing RESPONSIBLE-USE.md from typed data."""
    return "\n".join((
        "# Keel Responsible Use and Safety Notice",
        "",
        "> Generated from `keel.responsible_use` by `render_document()`. "
        "Edit the module, not this file.",
        "",
        "Keel is a coding harness that can take actions on your computer. "
        "Read this before your first agent run. If you do not accept these "
        "terms, do not run the agent.",
        "",
        "## What Keel can do",
        "",
        f"### {EXECUTION_DISCLOSURE.title}",
        "",
        EXECUTION_DISCLOSURE.text,
        "",
        f"### {SANDBOX_LIMITS_DISCLOSURE.title}",
        "",
        SANDBOX_LIMITS_DISCLOSURE.text,
        "",
        "This is the first-run safety notice (W1.10) in plain language. It is "
        "not a promise about the behaviour of any particular model, plugin "
        "or workload.",
        "",
        "## Before your first agent run",
        "",
        "Work through this checklist before you let an agent change anything:",
        "",
        render_checklist(),
        "",
        "## Warranty and liability",
        "",
        render_disclaimer(),
        "",
        "## Known limits",
        "",
        render_known_limits(),
        "",
        "The same limits appear on the in-app known-limits page (W7.19). "
        "Permissions are a risk control, not a safety guarantee.",
        "",
        "## How we handle host sandbox failures",
        "",
        "When a required command fails in our own development sandbox, the "
        "builder may retry the exact same command with the narrowest possible "
        "dev-sandbox exception for the blocked resource, and only with "
        "evidence of that cause. Test failures and the product sandbox are "
        "never bypassed. These are the builder stop rules:",
        "",
        render_builder_stop_rules(),
        "",
        "## Source references",
        "",
        "| Section | Plan row |",
        "| --- | --- |",
        "| What Keel can do | D5.1 |",
        "| Sandboxing reduces risk | D5.2 |",
        "| Checklist and wizard offers | D5.3 (V17) |",
        "| Warranty and liability | D5.4 (G5) |",
        "| Host sandbox failures | D5.5 (X10.4) |",
        "",
    ))

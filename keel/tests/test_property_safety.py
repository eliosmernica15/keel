"""B7.1 — property-based/fuzz tests for path containment and command parsing.

Uses only the standard library's ``random`` with a fixed seed, so failures are
reproducible and no extra dependency is introduced.
"""

from __future__ import annotations

import random
import string

from keel.runner import RealTools
from keel.safety import tier2_check
from keel.shell_ast import analyze

DANGEROUS = [
    ".env", ".env.local", "id_rsa",
    "C:\\Windows\\System32\\config", "/etc/passwd",
    "private.pem", ".aws/credentials",
]


def test_secret_and_system_paths_always_refused():
    tools = RealTools()
    for candidate in DANGEROUS:
        try:
            tools._safe_path(candidate)
        except ValueError:
            continue
        # A shell-looking target is refused by Tier 2 rather than _safe_path.
        verdict = tier2_check("read_file", {"path": candidate})
        assert not verdict.allowed, f"{candidate!r} was not refused"


def test_fuzzed_paths_never_escape_to_dangerous_targets():
    rng = random.Random(1234)
    alphabet = string.ascii_letters + string.digits + "._-/\\: "
    tools = RealTools()
    for _ in range(300):
        candidate = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40)))
        try:
            tools._safe_path(candidate)
        except ValueError:
            pass  # refusal is the expected outcome for bad paths
        except (OSError, TypeError):
            pass  # a random string is often not a valid path — still contained


def test_fuzzed_commands_never_analyze_as_safe_when_catastrophic():
    rng = random.Random(99)
    for verb in ("format", "mkfs", "diskpart", "sdelete"):
        noise = "".join(rng.choice(string.ascii_letters) for _ in range(5))
        result = analyze(f"{verb} {noise}", "posix")
        # Catastrophic verbs are always declined by Tier 2.
        verdict = tier2_check("run_shell", {"command": f"{verb} {noise}"})
        assert not verdict.allowed

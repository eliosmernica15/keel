"""Composer helpers (A1.6, A1.8): inline shell prefix and open-in-editor.

The `!cmd` prefix is parsed locally and the caller must pass it through the
normal permission gate; this module never executes a command itself. Editor
opening produces a command line for the caller to run only with approval.
"""

from __future__ import annotations

import os
import shlex


def parse_inline_shell(text: str) -> str | None:
    """Return the command after a leading `!`, or None for normal text."""
    stripped = (text or "").strip()
    if not stripped.startswith("!"):
        return None
    command = stripped[1:].strip()
    return command or None


def editor_command(path: str, *, editor: str | None = None) -> list[str]:
    editor = editor or os.environ.get("EDITOR", "")
    if not editor:
        # Fall back to a documented default the caller can gate.
        return ["code", "--goto", str(path)]
    try:
        parts = shlex.split(editor)
    except ValueError:
        parts = [editor]
    return parts + [str(path)]

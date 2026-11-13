"""keel.toolresult — tool-result rendering (Phase 1).

Dual representation (success = typed object; failure = stable-prefixed string)
plus overflow handling. Overflow policy (ORIGINAL DESIGN DECISION vs the
reference): the *failure* path also returns a file pointer. See
interface-spec.md §4.6 / §18.4 divergence #1.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

INLINE_CAP_SUCCESS = 30_000
INLINE_CAP_FAILURE = 10_000
HARD_KILL_BYTES = 5 * 1024 * 1024 * 1024
PREVIEW_CHARS = 2_000

TOOL_USE_ERROR_PREFIX = "<tool_use_error>"


@dataclass
class Persist:
    """Writes overflow payloads into <session-dir>/tool-results/."""

    session_dir: str
    fs: Any = None  # in-memory FS or None -> real os.makedirs/open

    def write(self, tool_use_id: str, payload: str) -> str:
        directory = os.path.join(self.session_dir, "tool-results")
        path = os.path.join(directory, f"{tool_use_id}.txt")
        if self.fs is not None:
            self.fs.makedirs(directory)
            self.fs.write_text(path, payload)
            return path
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8", errors="replace", newline="\n") as fh:
            fh.write(payload)
        return path


def render_success(tool_use_id: str, typed: Any, inline_text: str,
                   persist: Persist | None = None) -> dict:
    """Success outcome: inline ≤ cap, else <persisted-output> + file pointer."""
    if len(inline_text) <= INLINE_CAP_SUCCESS:
        return {
            "toolUseResult": typed,
            "content": inline_text,
            "isError": False,
        }
    pointer = None
    if persist is not None:
        pointer = persist.write(tool_use_id, inline_text)
    preview = inline_text[:PREVIEW_CHARS]
    content = (
        "<persisted-output>\n"
        f"{preview}\n"
        + (f"[output truncated — full output: {pointer}]\n" if pointer else
           "[output truncated]\n")
        + "</persisted-output>"
    )
    return {
        "toolUseResult": {
            "inline_preview": preview,
            "output_file_path": pointer,
            "total_bytes": len(inline_text.encode("utf-8", errors="replace")),
            "truncated": True,
        },
        "content": content,
        "isError": False,
    }


def render_failure(tool_use_id: str, message: str,
                   persist: Persist | None = None) -> dict:
    """Failure outcome: stable 'Error: ' prefix in toolUseResult only.

    interface-spec.md §4.4: content carries the message WITHOUT the prefix;
    toolUseResult carries it WITH the prefix.
    """
    text = message if len(message) <= INLINE_CAP_FAILURE else _excerpt(message)
    payload = f"Error: {text}"
    out: dict[str, Any] = {
        "toolUseResult": payload,
        "content": text,
        "isError": True,
    }
    if len(message) > INLINE_CAP_FAILURE and persist is not None:
        path = persist.write(tool_use_id, message)
        out["toolUseResult"] = {
            "inline_preview": text,
            "output_file_path": path,
            "truncated": True,
        }
        out["content"] = (
            "<persisted-output>\n"
            f"{text}\n"
            f"[output truncated — full output: {path}]\n"
            "</persisted-output>"
        )
    return out


def _excerpt(text: str) -> str:
    half = INLINE_CAP_FAILURE // 2
    return text[:half] + "\n…[elided]…\n" + text[-half:]


def machine_error(message: str) -> str:
    return f"{TOOL_USE_ERROR_PREFIX} {message}"

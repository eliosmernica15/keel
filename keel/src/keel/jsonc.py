"""Minimal JSON-with-comments parser for Keel configuration files.

Supports // and /* */ comments plus trailing commas, outside string literals.
Comments are replaced with whitespace so error line/column numbers still match
the original document. No secrets are included in error messages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class JsoncError(ValueError):
    message: str
    line: int
    column: int

    def __str__(self) -> str:
        return f"invalid JSONC at line {self.line} column {self.column}: {self.message}"


def strip_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escaped = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            out.append("  ")
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append("  ")
                i += 2
            continue
        out.append(ch)
        i += 1

    # Remove trailing commas outside strings.
    cleaned = "".join(out)
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in cleaned:
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            continue
        result.append(ch)
    text2 = "".join(result)
    # A comma is trailing when the next non-whitespace char closes a container.
    out2: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text2):
        ch = text2[i]
        if in_string:
            out2.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out2.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(text2) and text2[j].isspace():
                j += 1
            if j < len(text2) and text2[j] in "}]":
                i += 1
                continue
        out2.append(ch)
        i += 1
    return "".join(out2)


def loads(text: str) -> object:
    stripped = strip_comments(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JsoncError(exc.msg, exc.lineno, exc.colno) from None

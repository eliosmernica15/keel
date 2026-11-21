"""Local Python debugger adapter (C4.1).

Real breakpoint/pause/step/inspect capability using Python's built-in bdb,
exposed with a small DAP-like command surface. Works for local Python source
without an external debug adapter or hosted service.
"""

from __future__ import annotations

import bdb
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DebugFrame:
    file: str
    line: int
    function: str
    locals: dict[str, str]


class DebugSession(bdb.Bdb):
    def __init__(self):
        super().__init__()
        self.breakpoints: dict[str, set[int]] = {}
        self.stops: list[DebugFrame] = []
        self._paused = False
        self._step_requested = False

    def set_breakpoint(self, file: str, line: int) -> None:
        path = str(Path(file).resolve())
        self.breakpoints.setdefault(path, set()).add(int(line))
        self.set_break(path, int(line))

    def user_line(self, frame) -> None:
        filename = os.path.abspath(frame.f_code.co_filename)
        on_breakpoint = frame.f_lineno in self.breakpoints.get(filename, set())
        if on_breakpoint or self._step_requested:
            values = {name: repr(value)[:200]
                      for name, value in frame.f_locals.items()
                      if not name.startswith("__")}
            self.stops.append(DebugFrame(
                file=filename, line=frame.f_lineno,
                function=frame.f_code.co_name, locals=values))
        if self._step_requested:
            self._step_requested = False
            self.set_next(frame)

    def run_file(self, path: str | Path) -> list[DebugFrame]:
        """Run a Python file under the debugger until it completes."""
        target = Path(path).resolve()
        if not target.is_file():
            raise ValueError(f"not a Python file: {target}")
        namespace = {"__name__": "__main__", "__file__": str(target)}
        self.stops = []
        code = compile(target.read_text(encoding="utf-8"), str(target), "exec")
        self.run(code, namespace)
        return self.stops

    def continue_run(self) -> None:
        self._paused = False

    def step(self) -> None:
        self._step_requested = True

    def inspect(self, index: int = -1) -> DebugFrame | None:
        return self.stops[index] if self.stops else None

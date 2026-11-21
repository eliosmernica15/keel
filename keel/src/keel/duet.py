"""Keel Duet: builder plus independent reviewer (B2.3).

The builder performs the task; the reviewer runs afterwards with read-only
tools and a fresh context, so it cannot simply trust the builder's own claims.
Both summaries are returned for the operator to inspect.
"""

from __future__ import annotations

from .session import ALL_TOOLS

BUILDER_PROMPT = """\
You are the Keel Duet builder. Perform the requested task in the workspace.
Run the project's verification commands after changes. Report exactly what
you changed and which checks you ran; never claim success without evidence.

Task:
"""

REVIEWER_PROMPT = """\
You are an independent reviewer. You cannot edit files. Re-examine the
builder's work using read-only tools, verify its claims with evidence, and
list concrete problems or confirm the work with cited observations. Do not
repeat the builder's assertions without checking them.

Task:
"""


def review_allowlist() -> tuple[str, ...]:
    """Read-only tool set for the reviewer role."""
    from .safety import READ_TOOLS, SHELL_TOOLS

    allowed = {"read_file", "list_dir", "glob", "grep", "diff_files",
               "project_summary", "git_status", "git_diff", "git_log",
               "git_branch_list", "symbol_search", "recall", "list_tasks"}
    allowed.update(READ_TOOLS)
    return tuple(sorted(name for name in ALL_TOOLS if name in allowed
                        and name not in SHELL_TOOLS))


def builder_allowlist() -> tuple[str, ...]:
    return tuple(name for name in ALL_TOOLS
                 if name not in ("Task", "Duet"))

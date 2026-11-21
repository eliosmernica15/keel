"""Issue-to-change pipeline (C4.13).

Turns a markdown backlog item or an issue description into a structured change
plan locally. No tracker API is contacted; the caller supplies the text.
"""

from __future__ import annotations

import re


def parse_issue(text: str) -> dict:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    title = lines[0] if lines else "(no title)"
    body = "\n".join(lines[1:])
    labels = re.findall(r"(?:^|\s)#([A-Za-z0-9_-]+)", body)
    acceptance = [line[2:].strip() for line in lines
                  if line.startswith("- [ ]") or line.startswith("- [x]")]
    return {"title": title[:200], "body": body[:4000],
            "labels": labels[:20], "acceptance": acceptance[:50]}


def to_change_plan(issue: dict) -> dict:
    steps = ["Understand the request", "Locate relevant code",
             "Implement the change"]
    if issue.get("acceptance"):
        steps.append("Verify each acceptance criterion")
    steps.append("Run the project's verification commands")
    return {"issue": issue.get("title", ""),
            "steps": steps,
            "criteria": issue.get("acceptance", []),
            "draft_only": True}

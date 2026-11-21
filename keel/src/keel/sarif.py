"""SARIF ingestion and emission (C4.5).

Converts local security/lint findings to and from the SARIF 2.1.0 shape without
external tooling. Used by the admin/observability views.
"""

from __future__ import annotations

import json
from pathlib import Path


def finding(level: str, message: str, *, rule: str = "",
            file: str = "", line: int = 0) -> dict:
    return {"level": level, "message": message, "rule": rule,
            "file": file, "line": max(0, int(line))}


def to_sarif(findings: list[dict]) -> dict:
    rules = []
    results = []
    seen = set()
    for item in findings:
        rule_id = item.get("rule") or "keel-finding"
        if rule_id not in seen:
            seen.add(rule_id)
            rules.append({"id": rule_id,
                          "shortDescription": {"text": rule_id}})
        result = {
            "ruleId": rule_id,
            "level": item.get("level", "warning"),
            "message": {"text": item.get("message", "")[:1000]},
        }
        if item.get("file"):
            result["locations"] = [{
                "physicalLocation": {
                    "artifactLocation": {"uri": item["file"]},
                    "region": {"startLine": item.get("line", 0)},
                }}]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Keel", "rules": rules}},
                  "results": results}],
    }


def from_sarif(doc: dict) -> list[dict]:
    findings = []
    for run in doc.get("runs", []):
        for result in run.get("results", []):
            location = (result.get("locations") or [{}])[0]
            physical = location.get("physicalLocation", {})
            findings.append({
                "level": result.get("level", "warning"),
                "message": result.get("message", {}).get("text", ""),
                "rule": result.get("ruleId", ""),
                "file": physical.get("artifactLocation", {}).get("uri", ""),
                "line": physical.get("region", {}).get("startLine", 0),
            })
    return findings


def write_sarif(doc: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return target

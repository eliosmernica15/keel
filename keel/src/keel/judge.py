"""C13.2 — deterministic local judge with trajectory scoring.

Scores an agent trajectory on four transparent criteria — task completion,
policy compliance, tool-call efficiency and latency — with no external model
and no network. Every criterion carries its raw inputs, weight and a short
human-readable finding, so the score is auditable rather than a black box.
Multiple trajectories can be compared for best-of-N/arena selection.
"""

from __future__ import annotations

from collections import Counter

DEFAULT_WEIGHTS = {
    "completion": 0.40,
    "policy": 0.25,
    "efficiency": 0.20,
    "latency": 0.15,
}
GRADES = ((0.9, "A"), (0.75, "B"), (0.6, "C"), (0.4, "D"))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def evaluate(trajectory: list[dict], *, weights: dict | None = None,
             expected_steps: int | None = None,
             max_wasted: int | None = None) -> dict:
    """Score one trajectory. Each step may carry ``ok``, ``policy_violation``,
    ``wasted``, ``tool`` and ``duration_s`` fields."""
    steps = list(trajectory or [])
    n = len(steps)
    if n == 0:
        return {"score": 0.0, "grade": "F", "steps": 0, "violations": 0,
                "wasted": 0, "criteria": {}, "findings": ["empty trajectory"],
                "deterministic": True, "model_called": False}
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_weight = sum(weights.values()) or 1.0

    successes = sum(1 for s in steps if s.get("ok"))
    violations = sum(1 for s in steps if s.get("policy_violation"))

    # Repeated identical tool calls with the same input signal wasted effort.
    calls = Counter(
        (str(s.get("tool", "")), str(s.get("input", "")))
        for s in steps if s.get("tool"))
    duplicate_calls = sum(c - 1 for c in calls.values() if c > 1)
    explicit_wasted = sum(1 for s in steps if s.get("wasted"))
    wasted = max(explicit_wasted, duplicate_calls)

    completion = successes / n if n else 0.0
    policy = 1.0 - _clamp(violations * 0.2)
    efficiency = 1.0 - _clamp((wasted / n) if n else 0.0)
    if expected_steps and expected_steps > 0:
        latency = _clamp(expected_steps / max(n, 1))
    else:
        budgets = [float(s.get("duration_s", 0) or 0) for s in steps]
        total_duration = sum(budgets)
        latency = 1.0 if total_duration <= 30 else _clamp(30 / total_duration)
    if max_wasted is not None and max_wasted >= 0:
        efficiency = min(efficiency,
                         1.0 if wasted <= max_wasted else
                         _clamp(max_wasted / max(wasted, 1)))

    raw = {
        "completion": _clamp(completion),
        "policy": _clamp(policy),
        "efficiency": _clamp(efficiency),
        "latency": _clamp(latency),
    }
    criteria = {}
    for name, value in raw.items():
        criteria[name] = {
            "score": round(value, 3),
            "weight": round(weights.get(name, 0) / total_weight, 3),
            "evidence": {
                "successes": successes, "steps": n,
                "violations": violations, "wasted": wasted,
            } if name == "completion" else (
                {"violations": violations} if name == "policy" else
                {"wasted": wasted, "duplicate_calls": duplicate_calls}
                if name == "efficiency" else
                {"steps": n, "expected_steps": expected_steps}),
        }

    score = round(sum(raw[k] * weights.get(k, 0) / total_weight
                      for k in raw), 3)
    grade = next((g for threshold, g in GRADES if score >= threshold), "F")
    findings = []
    if successes < n:
        findings.append(f"{n - successes} of {n} steps failed")
    if violations:
        findings.append(f"{violations} policy violation(s)")
    if wasted:
        findings.append(f"{wasted} wasted/repeated call(s)")
    if not findings:
        findings.append("all steps succeeded with no violations or waste")

    return {
        "score": score,
        "grade": grade,
        "steps": n,
        "violations": violations,
        "wasted": wasted,
        "criteria": criteria,
        "findings": findings,
        "deterministic": True,
        "model_called": False,
    }


def compare(trajectories: list[list[dict]], *, names: list[str] | None = None,
            **kwargs) -> dict:
    """Evaluate and rank several trajectories (best-of-N / arena)."""
    labels = names or [f"candidate-{i+1}" for i in range(len(trajectories))]
    results = []
    for label, trajectory in zip(labels, trajectories):
        report = evaluate(trajectory, **kwargs)
        report["name"] = label
        results.append(report)
    results.sort(key=lambda r: r["score"], reverse=True)
    for rank, report in enumerate(results, 1):
        report["rank"] = rank
    winner = results[0]["name"] if results else None
    return {"candidates": results, "winner": winner,
            "deterministic": True, "model_called": False}


def rubric_report(report: dict) -> str:
    """Render a score report as a compact Markdown table."""
    lines = [
        f"**Score:** {report['score']:.3f} ({report['grade']})  "
        f"— {report['steps']} steps",
        "",
        "| Criterion | Score | Weight |",
        "| --- | ---: | ---: |",
    ]
    for name, data in report.get("criteria", {}).items():
        lines.append(f"| {name} | {data['score']:.3f} | {data['weight']:.2f} |")
    lines.append("")
    lines.extend(f"- {f}" for f in report.get("findings", []))
    lines.append("")
    lines.append("_Deterministic local scoring; no model was called._")
    return "\n".join(lines)

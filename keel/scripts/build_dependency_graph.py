#!/usr/bin/env python3
"""Generate DEPENDENCY-GRAPH.md from the 865-row PLAN-INDEX.json registry.

Implements addendum3 X0.3 ("generate a dependency graph plus a critical-path
report"). The report is generated, not hand-maintained:

    python keel/scripts/build_dependency_graph.py            # regenerate
    python keel/scripts/build_dependency_graph.py --check    # CI freshness gate

Inputs
------
* PLAN-INDEX.json (865-row registry). Default: the canonical copy referenced
  by the task, falling back to the worktree-root copy. Override with --plan.
* plan-extract/addendum3.json (optional; supplies the X0.2 / X0.2b milestone
  decomposition labels). Override with --extract.

Design notes / assumptions are written into the generated report:
* Edges come only from the registry's ``dependencies`` fields; unresolved
  tokens are reported, never invented.
* Milestone numbers are labels, not a topological order (the data contains
  backward edges); cycles are collapsed with Tarjan SCCs before the longest
  path is computed.
* X0.2 / X0.2b split nodes are derived by a deterministic keyword classifier
  over each row's title+detail. Rows that cannot be classified confidently
  remain on the parent Mxx roll-up node. No synthetic parent/child edges are
  added, so the critical path is always backed by stated dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_PLAN = Path(r"C:\Users\Admin\Desktop\Claude clone\PLAN-INDEX.json")
BASE_MILESTONES = [f"M{i}" for i in range(27)]

# X0.2 / X0.2b. Used verbatim when plan-extract/addendum3.json is available.
FALLBACK_DECOMPOSITIONS: dict[str, list[str]] = {
    "M19": [
        "M19a shell/layout",
        "M19b chat/composer",
        "M19c review/diff/terminal docks",
        "M19d fleet/board/memory views",
        "M19e settings/forms/wizard",
        "M19f polish/a11y/i18n",
    ],
    "M11": ["M11a code-intel core", "M11b engineering tools"],
    "M17": ["M17a voice", "M17b documents", "M17c meetings"],
    "M22": ["M22a packaging", "M22b update feed", "M22c stores"],
}

# Ordered specificity hint only; actual choice is by number of matched patterns.
SPLIT_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "M19": [
        ("M19f", r"\b(a11y|accessib\w*|i18n|locali\w*|locale|reduced.motion|dyslexia|font|sound cue|contrast|error boundary|crash.recovery|undo toast|empty.state|onboarding copy|safe mode|screen.share|brand strings)\b"),
        ("M19e", r"\b(settings|setting|wizard|first.run|tutorial|guided tour|form|model setup|provisioning|sign.in|preferences|config|import from other tools|contextual help)\b"),
        ("M19c", r"\b(diff|terminal|review|annotation|citation|file preview|tool card|event row|open in dock|\$editor|inline shell|code block|apply button|jump.to.tool.call)\b"),
        ("M19d", r"\b(fleet|board|memory|compare mode|arena|session compare|kanban|notification center|activity feed|multi.monitor|thread tools|pinned messages|timeline scrubber)\b"),
        ("M19a", r"\b(window|panel|layout|multi.window|detach|split|dock|theme|design token|tokens.json|density|zoom|workspace|shell|desktop|deep link|hotkey|surface switcher|context budget ui|tray|menu.bar|saved layouts|virtualized lists|rendering)\b"),
        ("M19b", r"\b(composer|chat|message|prompt|keybind|leader.key|@file|paste|think.harder|markdown|streaming|reject|vim keybind|quick.ask|image generation|action cards|plugin artifact)\b"),
    ],
    "M11": [
        ("M11b", r"\b(dap|debugger|breakpoint|codemod|structural search|sarif|static analysis|security scan|gitleaks|cve|sbom|profiling|benchmark agent|git extras|stacked commit|hunk staging|conflict resolver|test.runner|pytest|jest|cargo test|coverage|merge queue|worktree|dependency upgrade|forge seam|architecture docs|monorepo task graph|language packs|change.risk)\b"),
        ("M11a", r"\b(index|embedding|reranker|repo map|ranking|symbol|call graph|dependency graph|lsp|language server|diagnostic|incremental|workspac echanges|workspaceChanges|semantic|search|style learning|code.intel|references|file watching|low.power)\b"),
    ],
    "M17": [
        ("M17c", r"\b(meeting|per.meeting|consent re|speaker labels)\b"),
        ("M17b", r"\b(document|ocr|pdf|office|spreadsheet|contract|receipt|invoice|csv|diagram|mermaid|graphviz|image generat|writing coach|grammar|finance|redaction|deep.research|report|parsing|finance|finance csv)\b"),
        ("M17a", r"\b(voice|speech|stt|tts|dictation|push.to.talk|barge.in|wake word|audio|mic|transcri|spoken|half.duplex|translator|real.time secrets|hand_off_task|accessibility.*voice)\b"),
    ],
    "M22": [
        ("M22c", r"\b(store|flathub|snap|aur|scoop|chocolatey|nix|apt|yum|marketplace|public manifest|proprietary freeware|browser extension store)\b"),
        ("M22b", r"\b(update|manifest|rollout|staged|blocked versions|mirror|delta|beta channel|sideload|air.gapped|breaking.change notice|release channels|version badge|verified official build|min_version|security advisories|failover)\b"),
        ("M22a", r"\b(packag|build|installer|sign|notari|portable|artifact|seed|bundle|reproducible|uninstall|file association|arm64|per.user|per.machine|tar|zip|msi|dmg|deb|rpm|appimage|hardened runtime|obfuscat|entrypoint|publish|release dry.run|zero.secrets|smoke test|rehearsal|hygiene|identity|dirty marker|pre.flight|household|os.user)\b"),
    ],
}

# Strong overrides: these are unambiguous in the source text.
SPLIT_OVERRIDES: dict[str, list[tuple[str, str]]] = {
    "M17": [
        (r"\bmeeting recorder\b|\bmeeting\b", "M17c"),
        (r"\bofficekit\b|\bocr\b|\bpdf\b|\bspreadsheet\b", "M17b"),
    ],
    "M19": [
        (r"\btokens\.json\b|\bdesign.token\b", "M19a"),
        (r"\bcomposer\b", "M19b"),
    ],
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def resolve_plan_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("KEEL_PLAN_INDEX")
    if env:
        return Path(env).resolve()
    if CANONICAL_PLAN.exists():
        return CANONICAL_PLAN
    local = ROOT / "PLAN-INDEX.json"
    if local.exists():
        return local
    raise SystemExit("PLAN-INDEX.json not found; pass --plan PATH")


def decompositions_from(extract_path: Path | None) -> dict[str, list[str]]:
    """Merge extract labels with the built-in X0.2/X0.2b fallback.

    The extract's M11/M17/M22 labels carry no node IDs, so fallback node IDs
    are paired with the extract's textual labels by position.
    """
    out = {parent: list(labels) for parent, labels in FALLBACK_DECOMPOSITIONS.items()}
    if extract_path and extract_path.exists():
        raw = load_json(extract_path).get("metadata", {}).get("milestone_decompositions", {})
        for parent, labels in raw.items():
            if parent not in out or len(labels) != len(out[parent]):
                continue
            fallback_ids = [label.split(" ", 1)[0] for label in out[parent]]
            merged = []
            for node, label in zip(fallback_ids, labels):
                text = label.split(" ", 1)[1].strip() if " " in label else ""
                found = re.search(r"\bM\d+[a-f]\b", label)
                node = found.group(0) if found else node
                merged.append(f"{node} {text}" if text else node)
            out[parent] = merged
    return out


def classify(feature: dict[str, Any], decomp: dict[str, list[str]]) -> str:
    """Return the node id for one registry row (deterministic, heuristic)."""
    parent = feature["milestone"]
    if parent not in decomp:
        return parent
    text = f"{feature.get('feature') or ''} {feature.get('detail') or ''}".lower()
    for pattern, node in SPLIT_OVERRIDES.get(parent, []):
        if re.search(pattern, text):
            return node
    scores: Counter[str] = Counter()
    for node, pattern in SPLIT_PATTERNS.get(parent, []):
        if re.search(pattern, text):
            scores[node] += 1
    if not scores:
        return parent  # unclassifiable rows stay on the parent roll-up
    priority = {node: i for i, node in enumerate(decomp[parent])}
    return sorted(scores, key=lambda n: (-scores[n], priority.get(n, 99)))[0]


def node_labels(decomp: dict[str, list[str]]) -> dict[str, str]:
    labels = {f"M{i}": f"M{i}" for i in range(27)}
    for children in decomp.values():
        for child in children:
            labels[child.split(" ", 1)[0]] = child
    return labels


def tarjan_scc(nodes: list[str], adj: dict[str, set[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    sccs: list[list[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(adj[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(sorted(comp))

    for v in nodes:
        if v not in index:
            visit(v)
    return sccs


def longest_path(
    nodes: list[str], edges: dict[tuple[str, str], list[tuple[str, str]]]
) -> tuple[list[list[str]], int, list[tuple[str, str] | None]]:
    """Longest path over SCC condensation; weight = number of milestone nodes.

    Returns (chain of SCCs, length, per-step evidence) where evidence[i] is the
    contributing (dependency id, dependent id) for the edge into chain[i].
    """
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
    sccs = tarjan_scc(nodes, adj)
    comp_of = {node: i for i, comp in enumerate(sccs) for node in comp}
    cadj: dict[int, set[int]] = defaultdict(set)
    evidence: dict[tuple[int, int], tuple[str, str]] = {}
    for (a, b), pairs in edges.items():
        ca, cb = comp_of[a], comp_of[b]
        if ca == cb:
            continue
        cadj[ca].add(cb)
        evidence.setdefault((ca, cb), pairs[0])

    indeg = {i: 0 for i in range(len(sccs))}
    for ca, cbs in cadj.items():
        for cb in cbs:
            indeg[cb] += 1
    queue = deque(i for i, d in indeg.items() if d == 0)
    topo: list[int] = []
    while queue:
        n = queue.popleft()
        topo.append(n)
        for m in sorted(cadj[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)

    weight = {i: len(comp) for i, comp in enumerate(sccs)}
    dist = {i: weight[i] for i in range(len(sccs))}
    prev: dict[int, int] = {}
    for n in topo:
        for m in sorted(cadj[n]):
            if dist.get(m, 0) < dist[n] + weight[m]:
                dist[m] = dist[n] + weight[m]
                prev[m] = n
    if not dist:
        return [], 0, []
    best = max(dist, key=lambda i: (dist[i], -i))
    chain: list[list[str]] = []
    step_evidence: list[tuple[str, str] | None] = [None]
    cur = best
    while True:
        chain.append(sccs[cur])
        if cur not in prev:
            break
        step_evidence.append(evidence.get((prev[cur], cur)))
        cur = prev[cur]
    chain.reverse()
    step_evidence.reverse()
    return chain, dist[best], step_evidence


def counts_by_status(features: list[dict[str, Any]]) -> str:
    c = Counter(f["status"] for f in features)
    return ", ".join(f"{n} {c[n]}" for n in ("verified", "not_started", "blocked") if c[n])


def md_cell(text: Any, limit: int | None = None) -> str:
    s = str(text or "").replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    if limit and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def build_report(
    plan_path: Path,
    extract_path: Path | None,
    features: list[dict[str, Any]],
    decomp: dict[str, list[str]],
) -> str:
    by_id = {f["id"]: f for f in features}
    labels = node_labels(decomp)
    node_of = {f["id"]: classify(f, decomp) for f in features}

    all_nodes = list(BASE_MILESTONES) + [
        child.split(" ", 1)[0] for children in decomp.values() for child in children
    ]
    extra = sorted({node_of[f["id"]] for f in features} - set(all_nodes))
    all_nodes += extra

    rows_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in features:
        rows_by_node[node_of[f["id"]]].append(f)

    edges: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    unresolved: list[tuple[str, str, str]] = []
    intra = 0
    for f in features:
        src = node_of[f["id"]]
        for dep in f.get("dependencies") or []:
            g = by_id.get(dep)
            if not g:
                unresolved.append((f["id"], src, dep))
                continue
            dst = node_of[dep]
            if dst == src:
                intra += 1
            else:
                edges[(dst, src)].append((dep, f["id"]))

    chain, path_len, chain_evidence = longest_path(all_nodes, edges)
    chain_ids = [node for comp in chain for node in comp]

    # Canonical (un-split) graph: roll children back to their parent Mxx.
    base_edges: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    base_node = lambda n: n if re.fullmatch(r"M\d+|unassigned", n) else n[:3].rstrip("abcdef")
    for (a, b), pairs in edges.items():
        ba, bb = base_node(a), base_node(b)
        if ba != bb:
            base_edges[(ba, bb)].extend(pairs)
    base_chain, base_len, _ = longest_path(
        sorted({base_node(n) for n in all_nodes}), base_edges
    )

    # Reachability / bottleneck analysis over the condensation graph.
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
    reachable: dict[str, set[str]] = {}
    for n in all_nodes:
        seen: set[str] = set()
        stack = list(adj[n])
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            stack.extend(adj[v])
        reachable[n] = seen
    roots = [n for n in all_nodes if not any(n in reachable[m] for m in all_nodes if m != n)]
    bottlenecks = sorted(all_nodes, key=lambda n: (-len(adj[n]), -len(reachable[n]), n))

    status_of_node = {
        n: counts_by_status(rows_by_node.get(n, [])) for n in all_nodes
    }
    unmet: list[dict[str, Any]] = []
    for f in features:
        if f["status"] != "not_started" or not f.get("dependencies"):
            continue
        bad = [d for d in f["dependencies"] if (by_id.get(d) or {}).get("status") != "verified"]
        if bad:
            unmet.append({"id": f["id"], "node": node_of[f["id"]], "bad": bad})

    backward = []
    order = {f"M{i}": i for i in range(27)}
    for f in features:
        for dep in f.get("dependencies") or []:
            g = by_id.get(dep)
            if g and g["milestone"] in order and f["milestone"] in order:
                if order[g["milestone"]] > order[f["milestone"]]:
                    backward.append((f["id"], f["milestone"], dep, g["milestone"]))

    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    out: list[str] = []
    w = out.append
    w("# Milestone dependency graph and critical path")
    w("")
    w("> Generated by `keel/scripts/build_dependency_graph.py`. Regenerate with")
    w("> `python keel/scripts/build_dependency_graph.py --plan <path>`; verify with `--check`.")
    w("")
    w("## 1. Provenance and scope")
    w("")
    w(f"- Registry: `{plan_path}` — SHA-256 `{digest}`.")
    w(f"- Rows: **{len(features)}** (status: {counts_by_status(features)}).")
    w(f"- Decomposition source: `{extract_path}` if found, otherwise built-in X0.2/X0.2b labels.")
    w(f"- Stated dependency references: **{sum(len(f.get('dependencies') or []) for f in features)}**;")
    w(f"  **{sum(1 for f in features if f.get('dependencies'))}** rows declare at least one dependency.")
    w(f"- Graph nodes: **{len(all_nodes)}** ({len(BASE_MILESTONES)} canonical milestones + "
      f"{len(all_nodes) - len(BASE_MILESTONES) - len(extra)} X0.2/X0.2b split nodes"
      + (f" + {len(extra)} unassigned" if extra else "") + ").")
    w(f"- Graph edges: **{len(edges)}** distinct milestone-level edges from stated row dependencies "
      f"({intra} intra-node edges ignored).")
    w(f"- Unresolved dependency tokens: **{len(unresolved)}** references (not used as edges).")
    w("")
    w("## 2. Assumptions (important)")
    w("")
    w("1. **Only stated dependencies become edges.** The registry has no `deps` field with")
    w("   milestone-level links, so edges are derived by resolving each row's `dependencies`")
    w("   feature IDs to their owning milestone/split node. No dependency is inferred from")
    w("   milestone numbering, source order, or priority.")
    w("2. **Milestone numbers are labels, not a topological order.**")
    w(f"   {len(backward)} edges point from a higher-numbered milestone to a lower-numbered one")
    w("   (e.g. an M0 row depending on an M7 row). Cyclic groups are collapsed with Tarjan")
    w("   strongly-connected components before computing the critical path; the length below")
    w("   counts SCC members, so a cycle involving several milestones counts each once.")
    w("3. **Split nodes are derived, not stated in the registry.** X0.2/X0.2b require M19a-f,")
    w("   M11a-b, M17a-c and M22a-c, but rows remain tagged with the parent milestone. A")
    w("   deterministic keyword classifier over title+detail assigns each row; unclassifiable")
    w("   rows stay on the parent Mxx roll-up node. No synthetic parent→child edges are added,")
    w("   so every reported path edge is backed by real stated dependencies.")
    w("4. **Unresolved tokens are reported, never guessed.** They are listed in §7.")
    w("5. **The critical path is a dependency chain, not a schedule.** It assumes unlimited")
    w("   capacity; it does not model owner gates, blocked external prerequisites or effort.")
    w("")
    w("## 3. Critical path")
    w("")
    w(f"**Critical path length: {path_len} milestone-nodes** in the full (split-expanded) graph.")
    w(f"At canonical M-level (splits rolled up) the longest chain is **{base_len} milestone-nodes**.")
    w("")
    w("Full-graph chain (dependency → dependent):")
    w("")
    for i, comp in enumerate(chain):
        rows = sum(len(rows_by_node.get(n, [])) for n in comp)
        w(f"{i + 1}. **{' ⟷ '.join(labels.get(n, n) for n in comp)}** — {rows} rows in cycle/group"
          f" ({counts_by_status([f for n in comp for f in rows_by_node.get(n, [])])})")
        if i and chain_evidence[i]:
            ev = chain_evidence[i]
            assert ev is not None
            w(f"   - edge evidence: `{ev[0]}` → `{ev[1]}`")
    w("")
    w("Canonical chain:")
    w("")
    w(" → ".join(
        " ⟷ ".join(labels.get(n, n) for n in comp) for comp in base_chain
    ) or "(none)")
    w("")
    w("## 4. Which feature groups must complete first")
    w("")
    w("Root nodes (no incoming stated dependency) are the first groups that can start;")
    w("the bottleneck table ranks nodes by how many distinct groups depend on them.")
    w("")
    w("| Root node | Rows | Status mix | Directly blocks | Downstream reach |")
    w("| :- | :-: | :- | :-: | :-: |")
    for n in sorted(roots):
        w(f"| {md_cell(labels.get(n, n))} | {len(rows_by_node.get(n, []))} | "
          f"{md_cell(status_of_node[n]) or 'roll-up only'} | {len(adj[n])} | {len(reachable[n])} |")
    w("")
    w("| Bottleneck node | Rows | Status mix | Directly blocks | Downstream reach |")
    w("| :- | :-: | :- | :-: | :-: |")
    for n in bottlenecks[:15]:
        w(f"| {md_cell(labels.get(n, n))} | {len(rows_by_node.get(n, []))} | "
          f"{md_cell(status_of_node[n]) or 'roll-up only'} | {len(adj[n])} | {len(reachable[n])} |")
    w("")
    critical_unready = [
        n for n in chain_ids if any(f["status"] != "verified" for f in rows_by_node.get(n, []))
    ]
    w(f"Nodes on the critical path with non-green rows: "
      f"**{', '.join(md_cell(labels.get(n, n)) for n in critical_unready) or 'none'}**.")
    w("")
    w("## 5. Mermaid graph")
    w("")
    w("```mermaid")
    w("flowchart LR")
    w("  classDef crit fill:#ffe6cc,stroke:#d79b00,stroke-width:2px;")
    w("  classDef root fill:#e1f5e1,stroke:#2d8a2d;")
    for n in all_nodes:
        kind = " crit" if n in chain_ids else (" root" if n in roots else "")
        w(f'  {n}["{md_cell(labels.get(n, n))}"]:::{kind.strip()}' if kind
          else f'  {n}["{md_cell(labels.get(n, n))}"]')
    for a, b in sorted(edges):
        pairs = edges[(a, b)]
        dep_ids = ", ".join(p[0] for p in pairs[:3])
        if len(pairs) > 3:
            dep_ids += f",+{len(pairs) - 3}"
        w(f'  {a} -->|"{md_cell(dep_ids)}"| {b}')
    w("```")
    w("")
    w("Legend: orange = on the critical path; green = root (no stated prerequisite);")
    w("edge labels are the contributing row dependency IDs.")
    w("")
    w("## 6. Readiness gate (X0.3)")
    w("")
    w("X0.3 says a builder may not start a row whose dependencies are not green.")
    w(f"- `not_started` rows that declare dependencies: **{sum(1 for f in features if f['status'] == 'not_started' and f.get('dependencies'))}**.")
    w(f"- Of those, rows with at least one dependency not `verified`: **{len(unmet)}**.")
    w(f"- Rows depending on a `blocked` row: **{sum(1 for u in unmet if any((by_id.get(d) or {}).get('status') == 'blocked' for d in u['bad']))}**.")
    w("")
    w("| Not-started row | Node | Unmet dependency | Dependency status |")
    w("| :- | :- | :- | :- |")
    for u in unmet:
        for d in u["bad"]:
            w(f"| {u['id']} | {md_cell(labels.get(u['node'], u['node']))} | {md_cell(d)} | "
              f"{(by_id.get(d) or {}).get('status', 'unresolved token')} |")
    w("")
    w("## 7. Unresolved dependency tokens")
    w("")
    w("These tokens appear in `dependencies` but do not resolve to a registry ID.")
    w("They are recorded as assumptions and excluded from the graph and critical path.")
    w("")
    w("| Row | Node | Token |")
    w("| :- | :- | :- |")
    for fid, node, tok in sorted(unresolved):
        w(f"| {fid} | {md_cell(labels.get(node, node))} | {md_cell(tok)} |")
    w("")
    w("## 8. All stated milestone-level edges")
    w("")
    w("| From (prerequisite) | To (dependent) | Contributing row dependencies |")
    w("| :- | :- | :- |")
    for a, b in sorted(edges):
        w(f"| {md_cell(labels.get(a, a))} | {md_cell(labels.get(b, b))} | "
          f"{md_cell(', '.join(f'{d}→{r}' for d, r in edges[(a, b)]), 180)} |")
    w("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", help="path to PLAN-INDEX.json (865-row registry)")
    parser.add_argument("--extract", help="path to plan-extract/addendum3.json")
    parser.add_argument("--output", help="report path (default: worktree root)")
    parser.add_argument("--check", action="store_true", help="fail if report is stale")
    args = parser.parse_args(argv)

    plan_path = resolve_plan_path(args.plan)
    extract_path = Path(args.extract).resolve() if args.extract else plan_path.parent / "plan-extract" / "addendum3.json"
    output = Path(args.output).resolve() if args.output else ROOT / "DEPENDENCY-GRAPH.md"
    features = load_json(plan_path)["features"]
    decomp = decompositions_from(extract_path)
    report = build_report(plan_path, extract_path, features, decomp)

    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != report:
            print(f"STALE: {output}", file=sys.stderr)
            return 1
        print(f"FRESH: {output}")
        return 0

    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output} ({len(report.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

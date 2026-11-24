"""P0 dev-workflow contract tests (stdlib-only, no processes/network/host state).

This suite covers the pure contract surface of ``keel.gate_scheduler`` that
supports four registry rows:

* **D7.1**  -- gates as a dependency graph with cycle detection, a bounded
  concurrency policy from ``KEEL_GATE_CONCURRENCY``, a ``KEEL_GATE_FAIL_FAST``
  switch, and failure isolation (a failure skips only its dependents so all
  independent errors are reported);
* **D7.9**  -- a strict dependency linker: undeclared deps fail, versions and
  hashes are pinned, and dependency build/postinstall scripts must be in an
  explicit allowlist;
* **D7.12** -- the CI lane layout: broad gates, small Python matrix, separate
  Windows/macOS workflows, hosted-Linux benchmarks, opt-in provider e2e that
  self-skips without a key, and timing-based coverage partitioning;
* **D7.19** -- the benchmark method: the ``sdk-minimal`` JSON-RPC agent profile
  with an isolated workspace and a distinct session id per independent task.

Simulation is a pure function of caller-supplied outcomes.  It never launches
a process, reads the environment, touches the filesystem, or uses a clock or
random source; an AST test enforces that.  Every malformed or unknown value
must fail closed.

Run from the worktree root with the standard-library runner::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_gate_scheduler.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import json
import math
import unittest
from pathlib import Path

import keel.gate_scheduler as gs
from keel.gate_scheduler import (
    CI_LANES,
    CONCURRENCY_ENV,
    DEFAULT_CONCURRENCY,
    FAIL_FAST_ENV,
    JSONRPC_TRANSPORT,
    LANE_BENCHMARKS,
    LANE_GATES,
    LANE_MATRIX,
    LANE_MACOS,
    LANE_PROVIDER_E2E,
    LANE_WINDOWS,
    MAX_CONCURRENCY,
    PLATFORMS,
    PYTHON_VERSIONS,
    SDK_MINIMAL_PROFILE,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    WORKSPACE_ROOT,
    BenchmarkMethod,
    CILane,
    ContractValidationError,
    CoveragePlan,
    DependencyManifest,
    GateGraph,
    GateRun,
    LaneKind,
    LockEntry,
    SchedulerPolicy,
    benchmark_dispatch,
    build_gate_graph,
    ci_layout_dict,
    find_cycle,
    is_isolated,
    is_script_allowed,
    lane_enabled,
    link_dependencies,
    lockfile_digest,
    make_benchmark_method,
    make_benchmark_task,
    make_ci_lane,
    make_gate,
    make_lock_entry,
    make_manifest,
    method_digest,
    parse_scheduler_env,
    partition_coverage,
    simulate_gates,
    topological_levels,
    transitive_dependents,
    undeclared_dependencies,
    validate_benchmark_method,
    validate_ci_layout,
    validate_gate_graph,
    validate_manifest,
)


def _gate(name, *deps, lane="gates"):
    return make_gate(name, depends_on=deps, lane=lane)


def _graph(*specs):
    return build_gate_graph(specs)


def _policy(concurrency=2, fail_fast=False):
    return SchedulerPolicy(concurrency=concurrency, fail_fast=fail_fast)


def _outcomes(**values):
    return values


def _py(package, version="1.2.3", digest=None):
    return make_lock_entry(
        package,
        version,
        digest or "sha256:" + "a" * 64,
    )


def _node(package, scripts=()):
    return make_lock_entry(
        package,
        "2.0.0",
        "sha512:" + "b" * 128,
        scripts=scripts,
        ecosystem="node",
    )


class TestFeatureAndPurity(unittest.TestCase):
    """The module is pure, deterministic and stdlib-only."""

    def test_registry_ids_declared(self):
        self.assertEqual(tuple(gs.FEATURE_IDS),
                         ("D7.1", "D7.9", "D7.12", "D7.19"))

    def test_public_api_exports_exist(self):
        for name in gs.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(gs, name))

    def test_imports_are_stdlib_only(self):
        source = Path(gs.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = {
            "__future__", "dataclasses", "enum", "hashlib", "json", "math",
            "re", "typing",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    with self.subTest(module=alias.name):
                        self.assertIn(alias.name.split(".")[0], allowed)
            elif isinstance(node, ast.ImportFrom):
                with self.subTest(module=node.module):
                    self.assertIn((node.module or "").split(".")[0], allowed)

    def test_no_host_effects_in_source(self):
        source = Path(gs.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_names = {
            "open", "system", "popen", "spawn", "spawnl", "fork", "exec",
            "execv", "sleep", "random", "choice", "urlopen", "socket",
        }
        forbidden_modules = {
            "os", "subprocess", "socket", "time", "random", "shutil",
            "pathlib", "requests", "urllib", "tempfile", "multiprocessing",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                name = target.id if isinstance(target, ast.Name) else (
                    target.attr if isinstance(target, ast.Attribute) else "")
                with self.subTest(call=name):
                    self.assertNotIn(name, forbidden_names)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""])
                for module in mods:
                    with self.subTest(module=module):
                        self.assertNotIn(module.split(".")[0], forbidden_modules)

    def test_errors_are_value_errors(self):
        self.assertTrue(issubclass(ContractValidationError, ValueError))
        with self.assertRaises(ValueError):
            make_gate("")


# ---------------------------------------------------------------------------
# D7.1 - gate graph
# ---------------------------------------------------------------------------


class TestGateGraph(unittest.TestCase):
    def test_make_gate_defaults_and_immutability(self):
        gate = _gate("lint")
        self.assertEqual(gate.gate_id, "lint")
        self.assertEqual(gate.depends_on, ())
        self.assertEqual(gate.lane, "gates")
        with self.assertRaises(Exception):
            gate.gate_id = "mutated"

    def test_make_gate_rejects_unsafe_identifiers(self):
        for gate_id in ("", " ", "../escape", "a/b", "a b", "a\nb", "-bad", "a;b"):
            with self.subTest(gate_id=gate_id):
                with self.assertRaises(ContractValidationError):
                    make_gate(gate_id)

    def test_make_gate_rejects_self_and_duplicate_deps(self):
        with self.assertRaises(ContractValidationError):
            make_gate("a", depends_on=("a",))
        with self.assertRaises(ContractValidationError):
            make_gate("a", depends_on=("b", "b"))

    def test_unknown_dependency_fails_closed(self):
        with self.assertRaises(ContractValidationError):
            _graph(_gate("a", "missing"))

    def test_duplicate_gate_ids_fails_closed(self):
        with self.assertRaises(ContractValidationError):
            _graph(_gate("a"), _gate("a"))

    def test_simple_cycle_detected(self):
        errors = validate_gate_graph([_gate("a", "b"), _gate("b", "a")])
        self.assertTrue(any("cycle" in e for e in errors))
        cycle = find_cycle([_gate("a", "b"), _gate("b", "a")])
        self.assertEqual(cycle[0], cycle[-1])

    def test_multi_node_cycle_detected(self):
        specs = [_gate("a", "c"), _gate("b", "a"), _gate("c", "b"), _gate("d")]
        with self.assertRaises(ContractValidationError):
            _graph(*specs)
        self.assertEqual(len(find_cycle(specs)), 4)

    def test_self_cycle_detected(self):
        # make_gate refuses a self dependency; a forged spec must still fail.
        forged = gs.GateSpec(gate_id="a", depends_on=("a",), lane="gates")
        self.assertIn("a", find_cycle([forged]))
        with self.assertRaises(ContractValidationError):
            build_gate_graph([forged])

    def test_topological_levels_are_deterministic(self):
        specs = [_gate("app", "core", "ui"), _gate("ui", "core"),
                 _gate("core"), _gate("lint")]
        levels = topological_levels(_graph(*specs))
        self.assertEqual(levels, (("core", "lint"), ("ui",), ("app",)))
        reverse = topological_levels(_graph(*reversed(specs)))
        self.assertEqual(levels, reverse)

    def test_transitive_dependents(self):
        graph = _graph(_gate("base"), _gate("mid", "base"), _gate("top", "mid"),
                       _gate("other"))
        self.assertEqual(transitive_dependents(graph, "base"), frozenset({"mid", "top"}))
        self.assertEqual(transitive_dependents(graph, "top"), frozenset())
        self.assertEqual(transitive_dependents(graph, "unknown"), frozenset())

    def test_graph_serializes_deterministically(self):
        graph = _graph(_gate("b", "a"), _gate("a"))
        self.assertEqual(
            graph.as_dict(),
            {"gates": [
                {"gate_id": "a", "depends_on": [], "lane": "gates"},
                {"gate_id": "b", "depends_on": ["a"], "lane": "gates"},
            ]},
        )
        self.assertEqual(json.dumps(graph.as_dict(), sort_keys=True),
                         json.dumps(_graph(_gate("a"), _gate("b", "a")).as_dict(),
                                    sort_keys=True))


# ---------------------------------------------------------------------------
# D7.1 - scheduler policy
# ---------------------------------------------------------------------------


class TestSchedulerPolicy(unittest.TestCase):
    def test_defaults_when_env_empty(self):
        policy = parse_scheduler_env({})
        self.assertEqual(policy.concurrency, DEFAULT_CONCURRENCY)
        self.assertFalse(policy.fail_fast)

    def test_valid_env(self):
        policy = parse_scheduler_env({CONCURRENCY_ENV: "3", FAIL_FAST_ENV: "TRUE"})
        self.assertEqual(policy.concurrency, 3)
        self.assertTrue(policy.fail_fast)
        self.assertEqual(parse_scheduler_env({FAIL_FAST_ENV: "0"}).fail_fast, False)
        self.assertEqual(parse_scheduler_env({FAIL_FAST_ENV: "yes"}).fail_fast, True)
        self.assertEqual(parse_scheduler_env({FAIL_FAST_ENV: "off"}).fail_fast, False)

    def test_invalid_concurrency_values_fail_closed(self):
        for value in ("", "0", "-1", "4.0", "1e2", "abc", " 4 ", "4;rm", True, None, []):
            with self.subTest(value=value):
                with self.assertRaises(ContractValidationError):
                    parse_scheduler_env({CONCURRENCY_ENV: value})

    def test_concurrency_bounds(self):
        self.assertEqual(parse_scheduler_env(
            {CONCURRENCY_ENV: str(MAX_CONCURRENCY)}).concurrency, MAX_CONCURRENCY)
        with self.assertRaises(ContractValidationError):
            parse_scheduler_env({CONCURRENCY_ENV: str(MAX_CONCURRENCY + 1)})

    def test_invalid_fail_fast_values_fail_closed(self):
        for value in ("maybe", "2", "", "tru", 1, None):
            with self.subTest(value=value):
                with self.assertRaises(ContractValidationError):
                    parse_scheduler_env({FAIL_FAST_ENV: value})

    def test_unknown_gate_env_key_fails_closed(self):
        for env in (
            {"KEEL_GATE_PARALLEL": "4"},
            {"KEEL_GATE_CONCURRENCYX": "4"},
            {CONCURRENCY_ENV: "2", "KEEL_GATE_TIMEOUT": "5"},
        ):
            with self.subTest(env=env):
                with self.assertRaises(ContractValidationError):
                    parse_scheduler_env(env)


# ---------------------------------------------------------------------------
# D7.1 - bounded-concurrency simulation
# ---------------------------------------------------------------------------


class TestGateSimulation(unittest.TestCase):
    def test_single_gate_pass(self):
        run = simulate_gates(_graph(_gate("lint")), _outcomes(lint=True), _policy())
        self.assertEqual(run.status_of("lint"), STATUS_PASSED)
        self.assertEqual(run.rounds, (("lint",),))
        self.assertEqual(run.max_in_flight(), 1)

    def test_dependency_chain(self):
        graph = _graph(_gate("a"), _gate("b", "a"), _gate("c", "b"))
        run = simulate_gates(graph, _outcomes(a=True, b=True, c=True),
                             _policy(concurrency=3))
        self.assertEqual(run.rounds, (("a",), ("b",), ("c",)))
        self.assertEqual(run.ids_with_status(STATUS_PASSED), ("a", "b", "c"))

    def test_failure_skips_only_dependents(self):
        graph = _graph(_gate("a"), _gate("b"), _gate("c"), _gate("d", "a"))
        run = simulate_gates(graph,
                             _outcomes(a=False, b=False, c=True, d=True),
                             _policy(concurrency=4))
        self.assertEqual(run.status_of("a"), STATUS_FAILED)
        self.assertEqual(run.status_of("b"), STATUS_FAILED)
        self.assertEqual(run.status_of("c"), STATUS_PASSED)
        self.assertEqual(run.status_of("d"), STATUS_SKIPPED)
        self.assertNotIn("d", [g for r in run.rounds for g in r])

    def test_independent_errors_are_all_reported(self):
        graph = _graph(*[_gate(f"gate{i}") for i in range(5)])
        outcomes = _outcomes(**{f"gate{i}": (i % 2 == 0) for i in range(5)})
        run = simulate_gates(graph, outcomes, _policy(concurrency=5))
        self.assertEqual(run.ids_with_status(STATUS_FAILED),
                         ("gate1", "gate3"))
        self.assertEqual(len(run.ids_with_status(STATUS_PASSED)), 3)

    def test_transitive_skip(self):
        graph = _graph(_gate("base"), _gate("mid", "base"), _gate("top", "mid"),
                       _gate("independent"))
        run = simulate_gates(graph,
                             _outcomes(base=False, mid=True, top=True,
                                       independent=True),
                             _policy(concurrency=4))
        self.assertEqual(run.status_of("mid"), STATUS_SKIPPED)
        self.assertEqual(run.status_of("top"), STATUS_SKIPPED)
        self.assertEqual(run.status_of("independent"), STATUS_PASSED)

    def test_fail_fast_cancels_the_rest(self):
        graph = _graph(_gate("a"), _gate("b"), _gate("c"))
        run = simulate_gates(graph, _outcomes(a=False, b=True, c=True),
                             _policy(concurrency=1, fail_fast=True))
        self.assertEqual(run.status_of("a"), STATUS_FAILED)
        self.assertEqual(run.ids_with_status(STATUS_CANCELLED), ("b", "c"))
        self.assertEqual(run.rounds, (("a",),))

    def test_fail_fast_keeps_inflight_results(self):
        graph = _graph(_gate("a"), _gate("b"), _gate("c"))
        run = simulate_gates(graph, _outcomes(a=False, b=True, c=True),
                             _policy(concurrency=2, fail_fast=True))
        self.assertEqual(run.rounds, (("a", "b"),))
        self.assertEqual(run.status_of("a"), STATUS_FAILED)
        self.assertEqual(run.status_of("b"), STATUS_PASSED)
        self.assertEqual(run.status_of("c"), STATUS_CANCELLED)

    def test_fail_fast_does_not_cancel_dependents_as_cancelled(self):
        graph = _graph(_gate("base"), _gate("child", "base"), _gate("other"))
        run = simulate_gates(graph, _outcomes(base=False, child=True, other=True),
                             _policy(concurrency=1, fail_fast=True))
        self.assertEqual(run.status_of("child"), STATUS_SKIPPED)
        self.assertEqual(run.status_of("other"), STATUS_CANCELLED)

    def test_bounded_concurrency(self):
        graph = _graph(*[_gate(f"g{i}") for i in range(10)])
        outcomes = _outcomes(**{f"g{i}": True for i in range(10)})
        for concurrency in (1, 2, 3, 7):
            with self.subTest(concurrency=concurrency):
                run = simulate_gates(graph, outcomes, _policy(concurrency=concurrency))
                self.assertLessEqual(run.max_in_flight(), concurrency)
                self.assertEqual(len(run.ids_with_status(STATUS_PASSED)), 10)

    def test_schedule_is_deterministic(self):
        specs = [_gate("zeta"), _gate("alpha"), _gate("mid", "alpha"),
                 _gate("beta"), _gate("omega", "zeta")]
        outcomes = _outcomes(zeta=True, alpha=False, mid=True, beta=True, omega=True)
        first = simulate_gates(_graph(*specs), outcomes, _policy(concurrency=2))
        second = simulate_gates(_graph(*reversed(specs)), dict(reversed(
            list(outcomes.items()))), _policy(concurrency=2))
        self.assertEqual(first.as_dict(), second.as_dict())

    def test_unknown_outcome_key_fails_closed(self):
        graph = _graph(_gate("a"))
        with self.assertRaises(ContractValidationError):
            simulate_gates(graph, _outcomes(a=True, typo=True), _policy())

    def test_missing_outcome_fails_closed(self):
        graph = _graph(_gate("a"), _gate("b"))
        with self.assertRaises(ContractValidationError):
            simulate_gates(graph, _outcomes(a=True), _policy(concurrency=2))

    def test_non_bool_outcome_fails_closed(self):
        graph = _graph(_gate("a"))
        for value in ("pass", 1, 0, None, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(ContractValidationError):
                    simulate_gates(graph, {"a": value}, _policy())

    def test_run_helpers_and_serialization(self):
        run = simulate_gates(_graph(_gate("a")), _outcomes(a=True), _policy())
        self.assertIsInstance(run, GateRun)
        self.assertEqual(run.status_of("missing"), "")
        self.assertEqual(run.as_dict()["policy"],
                         {"concurrency": 2, "fail_fast": False})
        self.assertEqual(run.as_dict()["results"][0]["status"], STATUS_PASSED)

    def test_empty_graph_is_a_noop(self):
        run = simulate_gates(_graph(), {}, _policy())
        self.assertEqual(run.rounds, ())
        self.assertEqual(run.results, ())

    def test_invalid_policy_fails_closed(self):
        graph = _graph(_gate("a"))
        for policy in (SchedulerPolicy(concurrency=0, fail_fast=False),
                       SchedulerPolicy(concurrency=65, fail_fast=False),
                       SchedulerPolicy(concurrency=True, fail_fast=False)):
            with self.subTest(policy=policy):
                with self.assertRaises(ContractValidationError):
                    simulate_gates(graph, _outcomes(a=True), policy)


# ---------------------------------------------------------------------------
# D7.9 - strict dependency linker
# ---------------------------------------------------------------------------


class TestStrictLinker(unittest.TestCase):
    def test_valid_python_lock(self):
        manifest = make_manifest(["tzdata"], [_py("tzdata", "2024.1")])
        report = link_dependencies(manifest)
        self.assertEqual(report.linked, ("tzdata==2024.1",))
        self.assertEqual(report.package_count, 1)
        self.assertEqual(undeclared_dependencies(manifest), ())

    def test_valid_node_lock_with_allowlisted_script(self):
        manifest = make_manifest(
            ["esbuild"], [_node("esbuild", scripts=("postinstall",))],
            allowed_scripts=("esbuild:postinstall",),
        )
        report = link_dependencies(manifest)
        self.assertEqual(report.linked, ("esbuild@2.0.0",))
        self.assertEqual(report.script_count, 1)

    def test_undeclared_dependency_fails(self):
        manifest = make_manifest(["tzdata", "cryptography"], [_py("tzdata")])
        self.assertEqual(undeclared_dependencies(manifest), ("cryptography",))
        with self.assertRaises(ContractValidationError):
            link_dependencies(manifest)

    def test_floating_version_rejected(self):
        for version in ("", "latest", "*", "^1.2.3", "~1.2", ">=1.0", "1.0 || 2.0"):
            with self.subTest(version=version):
                with self.assertRaises(ContractValidationError):
                    make_lock_entry("pkg", version, "sha256:" + "a" * 64)

    def test_missing_or_bad_hash_rejected(self):
        for digest in ("", "sha256:abc", "md5:" + "a" * 32,
                       "sha256:" + "A" * 64, "sha256:" + "g" * 64, None):
            with self.subTest(digest=digest):
                with self.assertRaises(ContractValidationError):
                    make_lock_entry("pkg", "1.0.0", digest)

    def test_duplicate_pin_rejected(self):
        manifest = make_manifest(["pkg"], [_py("pkg", "1.0.0"), _py("pkg", "2.0.0")])
        with self.assertRaises(ContractValidationError):
            link_dependencies(manifest)

    def test_unsafe_package_name_rejected(self):
        for package in ("", "../evil", "a/b", "a b", "-bad", "pkg;rm"):
            with self.subTest(package=package):
                with self.assertRaises(ContractValidationError):
                    make_lock_entry(package, "1.0.0", "sha256:" + "a" * 64)

    def test_scoped_node_package_accepted(self):
        entry = make_lock_entry("@scope/pkg", "1.0.0", "sha256:" + "a" * 64,
                                ecosystem="node")
        self.assertEqual(entry.package, "@scope/pkg")

    def test_script_not_allowlisted_fails(self):
        manifest = make_manifest(
            ["esbuild"], [_node("esbuild", scripts=("postinstall",))],
            allowed_scripts=("other:postinstall",),
        )
        self.assertFalse(is_script_allowed("esbuild", "postinstall",
                                           ("other:postinstall",)))
        with self.assertRaises(ContractValidationError):
            link_dependencies(manifest)

    def test_strict_scripts_mode_rejects_any_script_without_allowlist(self):
        manifest = make_manifest(["esbuild"],
                                 [_node("esbuild", scripts=("install",))])
        with self.assertRaises(ContractValidationError):
            link_dependencies(manifest)
        # Wildcards are never accepted as a blanket allowlist.
        with self.assertRaises(ContractValidationError):
            make_manifest(["esbuild"],
                          [_node("esbuild", scripts=("install",))],
                          allowed_scripts=("*:install",))

    def test_python_scripts_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_lock_entry("pkg", "1.0.0", "sha256:" + "a" * 64,
                            scripts=("postinstall",))
        # A forged entry still fails at the linker boundary, never silently
        # running a Python package's build script.
        forged = gs.LockEntry("pkg", "1.0.0", "sha256:" + "a" * 64,
                              scripts=("postinstall",))
        manifest = make_manifest(["pkg"], [forged])
        self.assertTrue(validate_manifest(manifest))
        with self.assertRaises(ContractValidationError):
            link_dependencies(manifest)

    def test_unknown_ecosystem_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_lock_entry("pkg", "1.0.0", "sha256:" + "a" * 64,
                            ecosystem="ruby")

    def test_lockfile_digest_is_deterministic_and_order_independent(self):
        a = make_manifest(["b", "a"], [_py("a", "1.0.0"), _py("b", "2.0.0")])
        b = make_manifest(["a", "b"], [_py("b", "2.0.0"), _py("a", "1.0.0")])
        self.assertEqual(lockfile_digest(a), lockfile_digest(b))
        self.assertEqual(len(lockfile_digest(a)), 64)
        self.assertNotEqual(lockfile_digest(a), lockfile_digest(
            make_manifest(["a"], [_py("a", "1.0.1")])))

    def test_manifest_round_trip_and_validation(self):
        manifest = make_manifest(["a"], [_py("a")],
                                 allowed_scripts=("a:install",), strict_scripts=False)
        self.assertEqual(DependencyManifest.from_dict(manifest.as_dict()), manifest)
        self.assertEqual(validate_manifest(manifest), ())
        self.assertIsInstance(_py("a"), LockEntry)


# ---------------------------------------------------------------------------
# D7.12 - CI lane layout
# ---------------------------------------------------------------------------


class TestCILayout(unittest.TestCase):
    def test_canonical_lanes_present(self):
        lanes = {lane.kind for lane in CI_LANES}
        self.assertEqual(lanes, {
            LaneKind.GATES, LaneKind.MATRIX, LaneKind.WINDOWS,
            LaneKind.MACOS, LaneKind.BENCHMARKS, LaneKind.PROVIDER_E2E,
        })
        self.assertEqual(validate_ci_layout(CI_LANES), ())

    def test_python_matrix_is_small_and_pinned(self):
        matrix = next(lane for lane in CI_LANES if lane.kind is LaneKind.MATRIX)
        self.assertEqual(tuple(matrix.matrix), PYTHON_VERSIONS)
        self.assertEqual(tuple(PYTHON_VERSIONS), ("3.11", "3.12", "3.13"))
        self.assertLessEqual(len(matrix.matrix), 3)

    def test_windows_and_macos_are_separate_workflows(self):
        workflows = {}
        for lane in CI_LANES:
            workflows.setdefault(lane.lane_id, []).append(lane.kind)
        self.assertNotIn(LaneKind.WINDOWS, workflows[LANE_GATES])
        self.assertNotIn(LaneKind.WINDOWS, workflows[LANE_MACOS])
        windows = next(l for l in CI_LANES if l.kind is LaneKind.WINDOWS)
        macos = next(l for l in CI_LANES if l.kind is LaneKind.MACOS)
        self.assertTrue(windows.runs_on.startswith("windows-"))
        self.assertTrue(macos.runs_on.startswith("macos-"))
        self.assertNotEqual(windows.workflow, macos.workflow)

    def test_benchmarks_on_standard_hosted_linux(self):
        bench = next(l for l in CI_LANES if l.kind is LaneKind.BENCHMARKS)
        self.assertEqual(bench.runs_on, "ubuntu-latest")
        self.assertFalse(bench.opt_in)

    def test_provider_e2e_is_opt_in_and_self_skipping(self):
        e2e = next(l for l in CI_LANES if l.kind is LaneKind.PROVIDER_E2E)
        self.assertTrue(e2e.opt_in)
        self.assertTrue(e2e.skip_without_key)
        self.assertEqual(e2e.key_ref, "env:KEEL_E2E_API_KEY")

    def test_duplicate_lane_kind_rejected(self):
        lanes = CI_LANES + (CI_LANES[0],)
        self.assertTrue(validate_ci_layout(lanes))
        with self.assertRaises(ContractValidationError):
            ci_layout_dict(lanes)

    def test_literal_key_ref_rejected(self):
        bad = CI_LANES[:-1] + (make_ci_lane(
            LANE_PROVIDER_E2E, LaneKind.PROVIDER_E2E, "provider-e2e.yml",
            "ubuntu-latest", opt_in=True, skip_without_key=True,
            key_ref="sk-literal-key-value"),)
        self.assertTrue(any("key" in e or "secret" in e
                            for e in validate_ci_layout(bad)))

    def test_lane_enabled_defaults(self):
        lanes = {lane.kind: lane for lane in CI_LANES}
        for kind in (LaneKind.GATES, LaneKind.MATRIX, LaneKind.BENCHMARKS):
            with self.subTest(kind=kind):
                self.assertTrue(lane_enabled(lanes[kind]))
        self.assertFalse(lane_enabled(lanes[LaneKind.PROVIDER_E2E]))

    def test_provider_e2e_requires_both_opt_in_and_key(self):
        lane = next(l for l in CI_LANES if l.kind is LaneKind.PROVIDER_E2E)
        self.assertFalse(lane_enabled(lane, {"api_key_present": True}))
        self.assertFalse(lane_enabled(lane, {"opt_in": True}))
        self.assertTrue(lane_enabled(lane, {"opt_in": True,
                                            "api_key_present": True}))
        self.assertFalse(lane_enabled(lane, {"opt_in": "yes",
                                             "api_key_present": True}))

    def test_coverage_partition_is_deterministic_and_balanced(self):
        timings = {"unit": 30.0, "e2e": 10.0, "slow": 20.0, "api": 40.0}
        plan = partition_coverage("linux", timings, partitions=2)
        self.assertIsInstance(plan, CoveragePlan)
        self.assertEqual(plan, partition_coverage("linux", dict(reversed(
            list(timings.items()))), partitions=2))
        all_shards = [s for part in plan.partitions for s in part]
        self.assertEqual(sorted(all_shards), sorted(timings))
        self.assertEqual(len(plan.partitions), 2)
        self.assertLess(abs(sum(plan.seconds[:1]) - sum(plan.seconds[1:])), 25)

    def test_coverage_partition_rejects_bad_timings(self):
        for timings in (
            {"a": 0}, {"a": -1.0}, {"a": float("nan")}, {"a": float("inf")},
            {"a": True}, {}, {"../escape": 1.0}, {"a b": 1.0}, {"a": "5"},
        ):
            with self.subTest(timings=timings):
                with self.assertRaises(ContractValidationError):
                    partition_coverage("linux", timings)

    def test_coverage_partition_rejects_unknown_platform_and_partitions(self):
        with self.assertRaises(ContractValidationError):
            partition_coverage("plan9", {"a": 1.0})
        for partitions in (0, -1, 17, True, 2.5):
            with self.subTest(partitions=partitions):
                with self.assertRaises(ContractValidationError):
                    partition_coverage("linux", {"a": 1.0}, partitions=partitions)
        self.assertEqual(tuple(PLATFORMS), ("linux", "windows", "macos"))

    def test_layout_is_serializable(self):
        doc = ci_layout_dict(CI_LANES)
        self.assertEqual(len(doc["lanes"]), 6)
        self.assertEqual(json.loads(json.dumps(doc, sort_keys=True)), doc)


# ---------------------------------------------------------------------------
# D7.19 - benchmark method
# ---------------------------------------------------------------------------


def _task(task_id, workspace=None, session_id=None):
    return make_benchmark_task(
        task_id,
        workspace or f"{WORKSPACE_ROOT}/{task_id}",
        session_id or f"sess-{task_id}",
    )


class TestBenchmarkMethod(unittest.TestCase):
    def test_valid_method_and_dispatch(self):
        method = make_benchmark_method(
            "bench-v1", [_task("b"), _task("a")])
        self.assertIsInstance(method, BenchmarkMethod)
        self.assertEqual(method.profile, SDK_MINIMAL_PROFILE)
        self.assertEqual(method.transport, JSONRPC_TRANSPORT)
        self.assertEqual(validate_benchmark_method(method), ())
        plan = benchmark_dispatch(method)
        self.assertEqual([inv.task_id for inv in plan], ["a", "b"])
        self.assertEqual(
            plan[0].workspace, f"{WORKSPACE_ROOT}/a")
        self.assertEqual(plan[0].session_id, "sess-a")
        self.assertTrue(all(inv.profile == SDK_MINIMAL_PROFILE for inv in plan))
        self.assertTrue(all(inv.transport == JSONRPC_TRANSPORT for inv in plan))

    def test_method_ids_consts(self):
        self.assertEqual(SDK_MINIMAL_PROFILE, "sdk-minimal")
        self.assertEqual(JSONRPC_TRANSPORT, "json-rpc")
        self.assertEqual(WORKSPACE_ROOT, "workspaces")

    def test_profile_and_transport_are_strict(self):
        for profile in ("", "full", "sdk-minimal ", "SDK-MINIMAL"):
            with self.subTest(profile=profile):
                with self.assertRaises(ContractValidationError):
                    make_benchmark_method("m", [_task("a")], profile=profile)
        for transport in ("", "http", "rest", "json-rpc/1.0"):
            with self.subTest(transport=transport):
                with self.assertRaises(ContractValidationError):
                    make_benchmark_method("m", [_task("a")], transport=transport)

    def test_duplicate_task_ids_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_benchmark_method("m", [_task("a"), _task("a")])

    def test_shared_workspace_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_benchmark_method("m", [
                _task("a", workspace="workspaces/shared"),
                _task("b", workspace="workspaces/shared"),
            ])

    def test_reused_session_id_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_benchmark_method("m", [
                _task("a", session_id="shared"),
                _task("b", session_id="shared"),
            ])

    def test_workspace_traversal_and_absolute_rejected(self):
        for workspace in (
            "../etc", "workspaces/../secret", "/tmp/x", "C:\\evil",
            "workspaces/%2e%2e/x", "workspaces/a/../../b", "workspaces/a b",
        ):
            with self.subTest(workspace=workspace):
                with self.assertRaises(ContractValidationError):
                    make_benchmark_task("a", workspace, "sess-a")

    def test_workspace_must_be_task_specific(self):
        with self.assertRaises(ContractValidationError):
            make_benchmark_task("a", "workspaces/b", "sess-a")
        with self.assertRaises(ContractValidationError):
            make_benchmark_task("a", "other/a", "sess-a")

    def test_unsafe_task_and_session_ids_rejected(self):
        for task_id in ("", "../a", "a/b", "a b"):
            with self.subTest(task_id=task_id):
                with self.assertRaises(ContractValidationError):
                    _task(task_id)
        for session_id in ("", "sess a", "../s", "sess;x"):
            with self.subTest(session_id=session_id):
                with self.assertRaises(ContractValidationError):
                    make_benchmark_task("a", "workspaces/a", session_id)

    def test_empty_tasks_rejected(self):
        with self.assertRaises(ContractValidationError):
            make_benchmark_method("m", [])

    def test_method_digest_deterministic_and_sensitive_to_isolation(self):
        a = make_benchmark_method("m", [_task("a"), _task("b")])
        b = make_benchmark_method("m", [_task("b"), _task("a")])
        self.assertEqual(method_digest(a), method_digest(b))
        self.assertEqual(len(method_digest(a)), 64)
        c = make_benchmark_method("m", [_task("a"),
                                        _task("b", session_id="changed")])
        self.assertNotEqual(method_digest(a), method_digest(c))

    def test_isolation_helper_and_forged_method(self):
        method = make_benchmark_method("m", [_task("a")])
        self.assertTrue(is_isolated(method))
        forged = gs.BenchmarkMethod(
            method_id="m", profile=SDK_MINIMAL_PROFILE,
            transport=JSONRPC_TRANSPORT, tasks=(_task("a"), _task("a")))
        self.assertFalse(is_isolated(forged))
        self.assertTrue(validate_benchmark_method(forged))
        with self.assertRaises(ContractValidationError):
            benchmark_dispatch(forged)


if __name__ == "__main__":
    unittest.main()

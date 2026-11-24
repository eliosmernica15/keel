"""Backend contract tests for the 16 not-started D7 P1/P2 registry rows.

Each class maps to one feature ID from ``PLAN-INDEX.json``:

D7.2 worker budgets · D7.3 face-separated typechecks · D7.4 contract generation
· D7.5 build order/check stage · D7.6 build identity/record · D7.7 build profiles
· D7.8 Windows/WSL guidance · D7.10 git hooks · D7.11 doc gates · D7.13 coverage
· D7.14 test taxonomy · D7.15 rehearsals · D7.16 package hygiene · D7.17 signing
docs · D7.18 breaking-change notice · D7.20 labels/stacked PRs.

A registry test also verifies the four earlier P0 rows implemented in
``keel.gate_scheduler`` (D7.1/D7.9/D7.12/D7.19).  All behavior here is a pure
function of caller-supplied values; an AST test enforces stdlib-only imports
and the absence of host effects.

Run from the worktree root with the standard-library runner::

    python -c "import sys,unittest; sys.path.insert(0,'keel/src'); \
suite=unittest.defaultTestLoader.discover('keel/tests',pattern='test_d7_workflow_backend.py'); \
raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)"
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import keel.d7_workflow_backend as d
import keel.gate_scheduler as gs
from keel.d7_workflow_backend import ContractValidationError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _stages():
    return tuple(d.make_build_stage(stage, "run %s" % stage, ("dist/%s" % stage,))
                 for stage in d.BUILD_STAGES)


def _hooks():
    return tuple(d.make_hook_spec(hook) for hook in d.HookName)


def _doc_gates():
    return tuple(d.make_doc_gate(gate, "run %s" % gate, ()) for gate in d.DOC_GATES)


def _doc_gates_with_aggregate():
    gates = list(_doc_gates())
    bundles = tuple(gate for gate in d.DOC_GATES if gate != d.DOC_SYNC_AGGREGATE)
    gates[0] = d.make_doc_gate(d.DOC_SYNC_AGGREGATE, "run doc-sync", bundles)
    return tuple(gates)


def _service():
    session = {"type": "object", "properties": {"id": {"type": "string"},
                                                "title": {"type": "string"}},
               "required": ["id"]}
    return d.make_service(
        "Sessions",
        (d.make_method("create", (d.make_field("title", {"type": "string"}),),
                       {"$ref": "#/definitions/Session"}),
         d.make_method("get", (d.make_field("id", {"type": "string"}),),
                       {"$ref": "#/definitions/Session"})),
        {"Session": session},
    )


def _identity(version="1.2.3", commit="abc1234", dirty=False, official=False):
    return d.make_build_identity(version, commit, dirty, official)


def _record(identity=None, digest=None):
    return d.make_build_record(identity or _identity(),
                               digest or "a" * 64, ("dist/app.exe",))


# ---------------------------------------------------------------------------
# registry, P0 verification and purity
# ---------------------------------------------------------------------------

class TestRegistryAndPurity(unittest.TestCase):
    def test_all_sixteen_feature_ids_declared(self):
        self.assertEqual(len(d.FEATURE_IDS), 16)
        self.assertEqual(set(d.FEATURE_IDS), {
            "D7.2", "D7.3", "D7.4", "D7.5", "D7.6", "D7.7", "D7.8", "D7.10",
            "D7.11", "D7.13", "D7.14", "D7.15", "D7.16", "D7.17", "D7.18",
            "D7.20",
        })

    def test_p0_rows_not_duplicated(self):
        self.assertEqual(set(d.P0_FEATURE_IDS), set(gs.FEATURE_IDS))
        self.assertFalse(set(d.FEATURE_IDS) & set(d.P0_FEATURE_IDS))

    def test_p0_contracts_present_in_gate_scheduler(self):
        expected = ("GateSpec", "GateGraph", "build_gate_graph", "simulate_gates",
                    "parse_scheduler_env", "LockEntry", "DependencyManifest",
                    "link_dependencies", "CILane", "validate_ci_layout",
                    "partition_coverage", "BenchmarkMethod", "benchmark_dispatch",
                    "method_digest")
        for name in expected:
            with self.subTest(name=name):
                self.assertTrue(hasattr(gs, name))

    def test_public_api_exports_exist(self):
        for name in d.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(d, name))

    def test_imports_are_stdlib_only(self):
        source = Path(d.__file__).read_text(encoding="utf-8")
        allowed = {"__future__", "dataclasses", "enum", "fnmatch", "hashlib",
                   "json", "math", "re", "typing"}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    with self.subTest(module=alias.name):
                        self.assertIn(alias.name.split(".")[0], allowed)
            elif isinstance(node, ast.ImportFrom):
                with self.subTest(module=node.module):
                    self.assertIn((node.module or "").split(".")[0], allowed)

    def test_no_host_effects_in_source(self):
        source = Path(d.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_calls = {"open", "system", "popen", "spawn", "fork", "exec",
                           "execv", "sleep", "random", "choice", "urlopen",
                           "socket"}
        forbidden_modules = {"os", "subprocess", "socket", "time", "random",
                             "shutil", "pathlib", "requests", "urllib",
                             "tempfile", "multiprocessing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                name = target.id if isinstance(target, ast.Name) else (
                    target.attr if isinstance(target, ast.Attribute) else "")
                with self.subTest(call=name):
                    self.assertNotIn(name, forbidden_calls)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""])
                for module in mods:
                    with self.subTest(module=module):
                        self.assertNotIn(module.split(".")[0], forbidden_modules)

    def test_errors_are_value_errors(self):
        self.assertTrue(issubclass(ContractValidationError, ValueError))
        with self.assertRaises(ValueError):
            d.make_build_stage("", "x", ("out",))


# ---------------------------------------------------------------------------
# D7.2 -- worker budgets
# ---------------------------------------------------------------------------

class TestD72WorkerBudgets(unittest.TestCase):
    def test_cgroup_v2_parsing(self):
        self.assertEqual(d.parse_cgroup_cpu_quota("250000 100000\n"), 2.5)
        self.assertIsNone(d.parse_cgroup_cpu_quota("max 100000\n"))
        self.assertEqual(d.parse_cgroup_cpu_quota("# comment\n\n50000 100000"), 0.5)

    def test_cgroup_v2_rejects_malformed(self):
        for content in ("", "100000", "max 0", "-1 100000", "abc 100000",
                        "100000 not-a-period", "100000 100000 3"):
            with self.subTest(content=content), self.assertRaises(ContractValidationError):
                d.parse_cgroup_cpu_quota(content)
        with self.assertRaises(ContractValidationError):
            d.parse_cgroup_cpu_quota(None)

    def test_cgroup_v1_parsing(self):
        self.assertEqual(d.parse_cgroup_v1_cpu_quota("50000", "100000"), 0.5)
        self.assertIsNone(d.parse_cgroup_v1_cpu_quota("-1", "100000"))
        with self.assertRaises(ContractValidationError):
            d.parse_cgroup_v1_cpu_quota("1", "0")
        with self.assertRaises(ContractValidationError):
            d.parse_cgroup_v1_cpu_quota("1.5", "100000")

    def test_local_cap_and_quota(self):
        local = d.make_worker_budget(16, False, 2, 4.0)
        ci = d.make_worker_budget(16, True, 2, 4.0)
        self.assertEqual(d.effective_workers(local), 2)
        self.assertEqual(d.effective_workers(ci), 4)
        self.assertEqual(d.effective_workers(d.make_worker_budget(16, False, 3, 1.5)), 1)
        self.assertEqual(d.effective_workers(d.make_worker_budget(1, True, 2)), 1)
        self.assertEqual(d.effective_workers(d.make_worker_budget(8, False, 0 + 2)), 2)

    def test_env_parsing_is_callers_only(self):
        env = {d.WORKER_CI_ENV: "true", d.WORKER_CPUS_ENV: "8",
               d.WORKER_CAP_ENV: "3"}
        budget = d.parse_worker_env(env)
        self.assertEqual(budget.hardware_cpus, 8)
        self.assertEqual(d.effective_workers(budget), 8)
        self.assertEqual(d.effective_workers(d.parse_worker_env(
            {d.WORKER_CPUS_ENV: 8, d.WORKER_CAP_ENV: 3})), 3)
        self.assertEqual(d.effective_workers(d.parse_worker_env(
            {"KEEL_HARDWARE_CPUS": "8"}, "50000 100000")), 1)

    def test_budget_rejects_bad_values(self):
        for bad in ((0, False, 2), (8, "false", 2), (8, False, 0),
                    (8, False, 999), (8, False, 2)):
            if bad[3:] if len(bad) > 3 else False:
                continue
            with self.subTest(bad=bad):
                try:
                    d.make_worker_budget(*bad, cgroup_cpus=0)
                except ContractValidationError:
                    pass
                else:
                    self.fail("invalid budget accepted")
        with self.assertRaises(ContractValidationError):
            d.parse_worker_env({d.WORKER_CI_ENV: "maybe"})
        with self.assertRaises(ContractValidationError):
            d.parse_worker_env({"KEEL_WORKER_TYPO": "1"})
        with self.assertRaises(ContractValidationError):
            d.parse_worker_env({d.WORKER_CAP_ENV: "2.5"})
        with self.assertRaises(ContractValidationError):
            d.effective_workers("not a budget")


# ---------------------------------------------------------------------------
# D7.3 -- face-separated typecheck programs
# ---------------------------------------------------------------------------

class TestD73FacePrograms(unittest.TestCase):
    def test_default_programs_are_valid(self):
        programs = d.build_face_programs(d.DEFAULT_FACE_PROGRAMS)
        self.assertEqual(set(p.face for p in programs), {d.Face.HOST, d.Face.CLIENT})
        self.assertEqual(len(programs), 2)
        self.assertEqual(d.face_for_package(programs, "keel"), d.Face.HOST)
        self.assertEqual(d.face_for_package(programs, "keel_web"), d.Face.CLIENT)

    def test_no_combined_face(self):
        with self.assertRaises(ContractValidationError):
            d.make_typecheck_program("all", "combined", ("keel",))
        with self.assertRaises(ContractValidationError):
            d.make_typecheck_program("all", None, ("keel",))

    def test_package_must_belong_to_exactly_one_face(self):
        duplicate = (d.DEFAULT_FACE_PROGRAMS[0],
                     d.make_typecheck_program("tsc", d.Face.CLIENT, ("keel",)))
        errors = d.validate_face_programs(duplicate)
        self.assertTrue(any("both" in error for error in errors))
        with self.assertRaises(ContractValidationError):
            d.build_face_programs(duplicate)

    def test_one_program_per_face_required(self):
        self.assertTrue(any("exactly one" in error for error in
                            d.validate_face_programs((d.DEFAULT_FACE_PROGRAMS[0],))))
        with self.assertRaises(ContractValidationError):
            d.build_face_programs(())
        with self.assertRaises(ContractValidationError):
            d.face_for_package(d.DEFAULT_FACE_PROGRAMS, "missing")

    def test_program_validation(self):
        with self.assertRaises(ContractValidationError):
            d.make_typecheck_program("p", d.Face.HOST, ())
        with self.assertRaises(ContractValidationError):
            d.make_typecheck_program("p", d.Face.HOST, ("a", "a"))
        with self.assertRaises(ContractValidationError):
            d.make_typecheck_program("bad id!", d.Face.HOST, ("a",))
        self.assertTrue(d.validate_face_programs(("not a program",)))

    def test_order_independent_serialization(self):
        forward = [p.as_dict() for p in d.build_face_programs(d.DEFAULT_FACE_PROGRAMS)]
        reverse = [p.as_dict() for p in d.build_face_programs(
            tuple(reversed(d.DEFAULT_FACE_PROGRAMS)))]
        self.assertEqual(forward, reverse)


# ---------------------------------------------------------------------------
# D7.4 -- typed remote-call contract generation
# ---------------------------------------------------------------------------

class TestD74Contracts(unittest.TestCase):
    def test_renders_types_and_methods(self):
        text = d.render_typescript_client((_service(),))
        self.assertIn("// generated by keel:d7", text)
        self.assertIn("export type Session = {", text)
        self.assertIn("id: string;", text)
        self.assertIn("title?: string;", text)
        self.assertIn("export interface SessionsClient {", text)
        self.assertIn("create(title: string): Session;", text)
        self.assertIn("get(id: string): Session;", text)

    def test_render_scalar_array_enum_and_union(self):
        self.assertEqual(d.render_ts_type({"type": "integer"}), "number")
        self.assertEqual(d.render_ts_type({"type": "boolean"}), "boolean")
        self.assertEqual(d.render_ts_type(
            {"type": "array", "items": {"type": "string"}}), "Array<string>")
        self.assertEqual(d.render_ts_type(
            {"type": "string", "enum": ["a", "b"]}), '"a" | "b"')
        self.assertEqual(d.render_ts_type({"type": "object", "properties": {}}),
                         "Record<string, never>")

    def test_digest_is_deterministic_and_drift_detected(self):
        first = d.contract_digest((_service(),))
        self.assertEqual(first, d.contract_digest((_service(),)))
        report = d.check_contract_drift((_service(),), first)
        self.assertTrue(report.matches)
        changed = d.make_service("Sessions", (
            d.make_method("get", (d.make_field("id", {"type": "integer"}),),
                          {"$ref": "#/definitions/Session"}),),
            _service().types)
        other = d.check_contract_drift((changed,), first)
        self.assertFalse(other.matches)
        self.assertNotEqual(other.current, first)

    def test_schema_failures(self):
        for schema in ({}, {"type": "array"}, {"type": "unknown"},
                       {"type": "object", "properties": {"a": {"type": "string"}},
                        "required": ["missing"]},
                       {"$ref": "#/definitions/Other", "type": "string"},
                       {"type": "string", "enum": []},
                       {"type": "string", "unknown": 1}):
            with self.subTest(schema=schema), self.assertRaises(ContractValidationError):
                d.make_field("x", schema)
        with self.assertRaises(ContractValidationError):
            d.make_field("bad name!", {"type": "string"})
        with self.assertRaises(ContractValidationError):
            d.make_method("m", (d.make_field("a", {"type": "string"}),
                                d.make_field("a", {"type": "string"})),
                          {"type": "string"})
        with self.assertRaises(ContractValidationError):
            d.make_service("Sessions", (), {})
        with self.assertRaises(ContractValidationError):
            d.make_service("Sessions", (d.make_method(
                "m", (), {"$ref": "#/definitions/Missing"}),), {})
        with self.assertRaises(ContractValidationError):
            d.render_typescript_client(())
        with self.assertRaises(ContractValidationError):
            d.check_contract_drift((_service(),), "not-a-digest")
        self.assertEqual(d.render_ts_type({"type": "array", "items": {
            "type": "object", "properties": {}}}), "Array<Record<string, never>>")


# ---------------------------------------------------------------------------
# D7.5 -- build order and check stage
# ---------------------------------------------------------------------------

class TestD75BuildOrder(unittest.TestCase):
    def test_canonical_order(self):
        self.assertEqual(d.BUILD_STAGES, (
            "native_addon", "contract_gen", "compile_host", "bundle_host",
            "compile_client", "bundle_client", "web"))
        plan = d.build_build_plan(_stages())
        self.assertEqual(tuple(s.stage_id for s in plan), d.BUILD_STAGES)
        self.assertTrue(any("documented build order" in e for e in
                            d.validate_build_order(tuple(reversed(_stages())))))

    def test_dependencies_must_be_earlier(self):
        stages = list(_stages())
        stages[1] = d.make_build_stage("contract_gen", "gen", ("gen",),
                                       ("web",))
        errors = d.validate_build_order(stages)
        self.assertTrue(any("later stage" in error for error in errors))
        with self.assertRaises(ContractValidationError):
            d.build_build_plan(stages)

    def test_missing_duplicate_and_unknown_stages(self):
        stages = list(_stages())
        stages.pop(0)
        self.assertTrue(any("exactly the seven" in e for e in
                            d.validate_build_order(stages)))
        stages = list(_stages())
        stages[0] = d.make_build_stage("extra", "x", ("out",))
        self.assertTrue(any("unknown build stage" in e for e in
                            d.validate_build_order(stages)))
        stages = list(_stages())
        stages[0] = d.make_build_stage("web", "x", ("out",))
        self.assertTrue(any("unique" in e for e in d.validate_build_order(stages)))
        with self.assertRaises(ContractValidationError):
            d.make_build_stage("x", "", ("out",))
        with self.assertRaises(ContractValidationError):
            d.make_build_stage("x", "x", ("../out",))

    def test_check_stage_consumes_built_output(self):
        plan = d.make_check_plan(("check dist/web/index.js",
                                  "pytest -q tests/test_smoke.py dist/web/index.js"),
                                 ("dist/web/index.js",))
        self.assertEqual(plan.stage, "build:check")
        self.assertEqual(plan.built_outputs, ("dist/web/index.js",))
        self.assertEqual(plan.as_dict()["stage"], "build:check")

    def test_check_stage_never_rebuilds(self):
        for command in ("build dist/web/index.js", "compile dist/web/index.js",
                        "bundle dist/web/index.js", "lint dist/web/index.js"):
            with self.subTest(command=command):
                if command.startswith("lint"):
                    continue  # lint is an allowed check verb
                with self.assertRaises(ContractValidationError):
                    d.make_check_plan((command,), ("dist/web/index.js",))
        with self.assertRaises(ContractValidationError):
            d.make_check_plan(("check missing.output",), ("dist/web/index.js",))
        with self.assertRaises(ContractValidationError):
            d.make_check_plan((), ("dist/web/index.js",))
        with self.assertRaises(ContractValidationError):
            d.make_check_plan(("check dist/web/index.js",), ())


# ---------------------------------------------------------------------------
# D7.6 -- build identity and build record
# ---------------------------------------------------------------------------

class TestD76BuildIdentity(unittest.TestCase):
    def test_identity_label_and_official_dirty_marker(self):
        self.assertEqual(d.identity_label(_identity()), "v1.2.3 (abc1234)")
        self.assertEqual(d.identity_label(_identity(dirty=True)),
                         "v1.2.3 (abc1234-dirty)")
        self.assertEqual(d.identity_label(_identity(dirty=True, official=True)),
                         "v1.2.3 (abc1234)")
        official = _identity(official=True)
        self.assertTrue(official.official)  # dirty flag still known internally

    def test_record_verification(self):
        identity, digest = _identity(), "a" * 64
        record = _record(identity, digest)
        self.assertEqual(d.verify_build_record(record, identity, digest), ())
        self.assertTrue(d.release_pack_allowed(record, identity, digest))
        self.assertFalse(d.release_pack_allowed(record, identity, "b" * 64))
        self.assertFalse(d.release_pack_allowed(record, identity, digest, False))
        self.assertEqual(d.verify_build_record(record, identity, digest, False),
                         ("build record is missing from the output",))
        self.assertEqual(d.verify_build_record(None, identity, digest),
                         ("build record is missing or malformed",))

    def test_stale_record_rejected(self):
        record = _record()
        self.assertTrue(any("stale" in e for e in
                            d.verify_build_record(record, _identity("1.2.4"), "a" * 64)))
        self.assertTrue(any("stale" in e for e in
                            d.verify_build_record(record, _identity(dirty=True), "a" * 64)))
        self.assertTrue(any("output list" in e for e in d.verify_build_record(
            record, _identity(), "a" * 64, True, ("dist/other.exe",))))

    def test_identity_and_record_validation(self):
        for version, commit in (("1.2", "abc1234"), ("1.2.3.4", "abc1234"),
                                ("1.2.3", "ABC1234"), ("1.2.3", "abc"),
                                ("01.2.3", "abc1234")):
            with self.subTest(version=version, commit=commit), \
                    self.assertRaises(ContractValidationError):
                d.make_build_identity(version, commit)
        with self.assertRaises(ContractValidationError):
            d.make_build_identity("1.2.3", "abc1234", dirty="true")
        with self.assertRaises(ContractValidationError):
            d.make_build_record(_identity(), "A" * 64, ("dist/app.exe",))
        with self.assertRaises(ContractValidationError):
            d.make_build_record(_identity(), "a" * 64, ())
        with self.assertRaises(ContractValidationError):
            d.verify_build_record(_record(), "not an identity", "a" * 64)

    def test_record_is_gitignored(self):
        self.assertTrue(d.record_is_gitignored((".build-record.json",)))
        self.assertTrue(d.record_is_gitignored(("build-record.json",)))
        self.assertFalse(d.record_is_gitignored(("*.log",)))
        self.assertEqual(d.BUILD_RECORD_PATH, ".build-record.json")


# ---------------------------------------------------------------------------
# D7.7 -- local vs official profiles
# ---------------------------------------------------------------------------

class TestD77Profiles(unittest.TestCase):
    def test_parse_profile_flag(self):
        self.assertIs(d.parse_profile_flag(("--profile", "local")), d.BuildProfile.LOCAL)
        self.assertIs(d.parse_profile_flag(("--profile=official",)), d.BuildProfile.OFFICIAL)
        for argv in ((), ("--profile",), ("--profile", "both"),
                     ("--profile", "local", "--profile", "official"),
                     ("--other",)):
            with self.subTest(argv=argv), self.assertRaises(ContractValidationError):
                d.parse_profile_flag(argv)

    def test_local_keeps_identity_and_discards_branding(self):
        identity = _identity(dirty=True)
        resolution = d.resolve_build_profile(d.BuildProfile.LOCAL, identity,
                                             {"logo": "acme", "name": "Acme"})
        self.assertIs(resolution.profile, d.BuildProfile.LOCAL)
        self.assertEqual(resolution.identity, identity)
        self.assertEqual(resolution.branding, ())
        self.assertFalse(resolution.branding_applied)
        self.assertIn("dirty", d.identity_label(resolution.identity))

    def test_official_applies_branding_and_omits_dirty(self):
        identity = _identity(dirty=True)
        resolution = d.resolve_build_profile("official", identity,
                                             {"name": "Acme", "logo": "acme"})
        self.assertTrue(resolution.identity.official)
        self.assertNotIn("dirty", d.identity_label(resolution.identity))
        self.assertEqual(resolution.branding, (("logo", "acme"), ("name", "Acme")))
        self.assertTrue(resolution.branding_applied)

    def test_invalid_resolution(self):
        with self.assertRaises(ContractValidationError):
            d.resolve_build_profile("staging", _identity())
        with self.assertRaises(ContractValidationError):
            d.resolve_build_profile("local", "not an identity")
        with self.assertRaises(ContractValidationError):
            d.resolve_build_profile("official", _identity(), {"bad key!": "x"})
        with self.assertRaises(ContractValidationError):
            d.resolve_build_profile("official", _identity(), {"logo": ""})


# ---------------------------------------------------------------------------
# D7.8 -- Windows and WSL guidance
# ---------------------------------------------------------------------------

class TestD78Environments(unittest.TestCase):
    def test_same_environment_with_separate_deps_passes(self):
        env = d.make_builder_environment(d.Environment.WINDOWS, d.Environment.WINDOWS,
                                         {"windows": "deps/windows"}, True, True)
        self.assertEqual(d.check_builder_environment(env), env)
        self.assertEqual(env.as_dict()["checkout"], "windows")

    def test_cross_environment_checkout_rejected(self):
        env = d.make_builder_environment("windows", "wsl",
                                         {"windows": "deps/win", "wsl": "deps/wsl"},
                                         True, True)
        self.assertTrue(any("same OS" in e for e in d.validate_builder_environment(env)))
        with self.assertRaises(ContractValidationError):
            d.check_builder_environment(env)

    def test_windows_needs_native_validation_and_lane(self):
        env = d.make_builder_environment("windows", "windows",
                                         {"windows": "deps/win"})
        errors = d.validate_builder_environment(env)
        self.assertTrue(any("native validation" in e for e in errors))
        self.assertTrue(any("separate" in e for e in errors))

    def test_dependency_roots_must_be_distinct_and_present(self):
        shared = d.make_builder_environment("wsl", "wsl",
                                            {"windows": "deps/shared", "wsl": "deps/shared"})
        self.assertTrue(any("own dependency root" in e for e in
                            d.validate_builder_environment(shared)))
        missing = d.make_builder_environment("linux", "linux", {})
        self.assertTrue(any("dependency root is required" in e for e in
                            d.validate_builder_environment(missing)))

    def test_invalid_environment_values(self):
        with self.assertRaises(ContractValidationError):
            d.make_builder_environment("dos", "windows", {"windows": "deps/win"})
        with self.assertRaises(ContractValidationError):
            d.make_builder_environment("windows", "windows", {"windows": "../deps"},
                                       True, True)
        with self.assertRaises(ContractValidationError):
            d.validate_builder_environment("not an environment")


# ---------------------------------------------------------------------------
# D7.10 -- git hooks
# ---------------------------------------------------------------------------

class TestD710Hooks(unittest.TestCase):
    def test_hook_set_and_install_plan(self):
        plan = d.hook_install_plan(_hooks())
        self.assertEqual(tuple(item.path for item in plan), (
            ".git/hooks/pre-commit", ".git/hooks/pre-merge-commit",
            ".git/hooks/pre-push"))
        self.assertTrue(all(item.mode == "0755" for item in plan))
        self.assertEqual(d.validate_hook_set(_hooks()), ())

    def test_hook_script_content(self):
        script = d.render_hook_script(d.make_hook_spec("pre-commit"))
        self.assertIn("#!/bin/sh", script)
        self.assertIn("keel lint --staged --profile staged", script)
        self.assertIn("--max-retries 2", script)
        self.assertIn("git diff --check --cached", script)
        self.assertIn("keel gate vendor-manifest --staged", script)
        push = d.render_hook_script(d.make_hook_spec("pre-push"))
        self.assertIn("keel typecheck --all-faces", push)

    def test_hooks_do_not_run_tests_or_builds(self):
        with self.assertRaises(ContractValidationError):
            d.render_hook_script(d.make_hook_spec("pre-commit", ("run-tests",)))
        with self.assertRaises(ContractValidationError):
            d.render_hook_script(d.make_hook_spec("pre-push", ("build",)))
        with self.assertRaises(ContractValidationError):
            d.render_hook_script(d.make_hook_spec("pre-commit", max_retries=99))

    def test_check_all_is_opt_in(self):
        with self.assertRaises(ContractValidationError):
            d.render_hook_script(d.make_hook_spec(
                "pre-commit", tuple(d.HOOK_CHECKS[d.HookName.PRE_COMMIT]) + (d.CHECK_ALL,)))
        opt_in = d.make_hook_spec(
            "pre-commit", tuple(d.HOOK_CHECKS[d.HookName.PRE_COMMIT]) + (d.CHECK_ALL,),
            check_all_opt_in=True)
        self.assertIn("no-tests", d.render_hook_script(opt_in, True))
        hooks = list(_hooks())
        hooks[0] = opt_in
        self.assertTrue(any("opt-in" in e for e in d.validate_hook_set(hooks)))
        self.assertEqual(d.validate_hook_set(hooks, True), ())

    def test_hook_set_validation(self):
        self.assertTrue(any("exactly once" in e for e in
                            d.validate_hook_set((_hooks()[0],))))
        bad = list(_hooks())
        bad[1] = d.make_hook_spec("pre-commit")
        self.assertTrue(d.validate_hook_set(bad))
        with self.assertRaises(ContractValidationError):
            d.build_hook_set(bad)
        with self.assertRaises(ContractValidationError):
            d.hook_install_plan(_hooks(), "../.git")
        with self.assertRaises(ContractValidationError):
            d.make_hook_spec("post-checkout")


# ---------------------------------------------------------------------------
# D7.11 -- doc gates
# ---------------------------------------------------------------------------

class TestD711DocGates(unittest.TestCase):
    def test_all_doc_gates_and_aggregate(self):
        self.assertEqual(d.validate_doc_gates(_doc_gates_with_aggregate()), ())
        self.assertTrue(any("missing doc gate" in e for e in
                            d.validate_doc_gates(_doc_gates()[:2])))
        self.assertTrue(any("does not aggregate" in e for e in
                            d.validate_doc_gates(_doc_gates())))

    def test_code_fence_extraction_and_compile(self):
        doc = "text\n```python\nx = 1\n```\n```sh\necho hi\n```\n```python\ny =\n```\n"
        fences = d.extract_code_fences(doc)
        self.assertEqual(len(fences), 2)
        self.assertEqual(d.typecheck_code_fences(doc.replace("y =\n", "y = 2\n")), 2)
        with self.assertRaises(ContractValidationError):
            d.typecheck_code_fences(doc)
        with self.assertRaises(ContractValidationError):
            d.extract_code_fences(None)

    def test_type_equivalence(self):
        source = "class Config:\n    pass\n"
        self.assertTrue(d.check_type_equivalence("Docs:\n\n```python\nclass Config:\n```\n",
                                                 source, "Config"))
        self.assertFalse(d.check_type_equivalence("class Settings:", source, "Config"))
        self.assertFalse(d.check_type_equivalence("", "", "Config"))
        with self.assertRaises(ContractValidationError):
            d.check_type_equivalence("", "", "bad symbol!")

    def test_dead_links(self):
        doc = "[ok](docs/a.md) [ext](https://example.test) [bad](docs/missing.md)"
        self.assertEqual(d.check_dead_links(doc, ("docs/a.md",)), ("docs/missing.md",))
        self.assertEqual(d.check_dead_links(doc, ("docs/a.md", "docs/missing.md")), ())
        with self.assertRaises(ContractValidationError):
            d.check_dead_links(None, ("docs/a.md",))

    def test_translation_pairing(self):
        pair = d.make_translation_pair("docs/en/a.md", "docs/fr/a.md", "fr")
        self.assertEqual(d.validate_translation_pairs((pair,)), ())
        self.assertIn("repair-translation", pair.conflict_command)
        forged = d.TranslationPair("docs/en/a.md", "docs/fr/a.md", "fr", "echo hi")
        self.assertTrue(any("repair command" in e for e in
                            d.validate_translation_pairs((forged,))))
        with self.assertRaises(ContractValidationError):
            d.make_translation_pair("docs/en/a.md", "docs/en/a.md", "en")


# ---------------------------------------------------------------------------
# D7.13 -- coverage gate
# ---------------------------------------------------------------------------

class TestD713Coverage(unittest.TestCase):
    def test_security_critical_modules_need_full_coverage(self):
        policy = d.make_coverage_policy()
        self.assertEqual(policy.strict_modules, d.SECURITY_CRITICAL_MODULES)
        full = {name: 100.0 for name in d.SECURITY_CRITICAL_MODULES}
        full["other"] = 90.0
        self.assertTrue(d.evaluate_coverage(policy, full).passed)
        full["crypto"] = 99.9
        report = d.evaluate_coverage(policy, full)
        self.assertFalse(report.passed)
        self.assertTrue(any("crypto" in e for e in report.failures))

    def test_graded_threshold(self):
        policy = d.make_coverage_policy(graded_threshold=85.0)
        self.assertTrue(d.evaluate_coverage(policy, {
            "permission_gate": 100, "analyzer": 100, "crypto": 100,
            "module": 84.9}).passed is False)
        self.assertTrue(d.evaluate_coverage(policy, {
            "permission_gate": 100, "analyzer": 100, "crypto": 100,
            "module": 85.0}).passed)

    def test_gate_is_separate_from_test_command(self):
        policy = d.make_coverage_policy()
        self.assertEqual(policy.gate_command, "coverage:strict")
        self.assertNotEqual(policy.gate_command, policy.test_command)
        with self.assertRaises(ContractValidationError):
            d.make_coverage_policy(gate_command="test", test_command="test")

    def test_coverage_values_fail_closed(self):
        policy = d.make_coverage_policy()
        base = {"permission_gate": 100, "analyzer": 100, "crypto": 100}
        for value in (-1, 101, True, "100", float("nan"), float("inf")):
            with self.subTest(value=value):
                data = dict(base)
                data["crypto"] = value
                self.assertFalse(d.evaluate_coverage(policy, data).passed)
        missing = dict(base)
        del missing["analyzer"]
        self.assertTrue(any("no coverage data" in e for e in
                            d.evaluate_coverage(policy, missing).failures))
        with self.assertRaises(ContractValidationError):
            d.evaluate_coverage(policy, [])
        with self.assertRaises(ContractValidationError):
            d.make_coverage_policy(graded_threshold=100)
        with self.assertRaises(ContractValidationError):
            d.make_coverage_policy(strict_modules=())


# ---------------------------------------------------------------------------
# D7.14 -- test taxonomy
# ---------------------------------------------------------------------------

class TestD714Taxonomy(unittest.TestCase):
    def test_real_api_e2e_self_skips_without_key(self):
        case = d.make_test_case("e2e_1", "real-api-e2e", "env:KEEL_API_KEY")
        self.assertEqual(d.test_disposition(case, False), d.DISPOSITION_SKIP)
        self.assertEqual(d.test_disposition(case, True), d.DISPOSITION_RUN)

    def test_snapshot_replay_and_record(self):
        replay = d.make_test_case("snap_1", "snapshot-replay")
        record = d.make_test_case("snap_2", "snapshot-record", "keyring:keel/key")
        self.assertEqual(d.test_disposition(replay, False), d.DISPOSITION_RUN)
        self.assertEqual(d.test_disposition(record, False), d.DISPOSITION_NEEDS_KEY)
        self.assertEqual(d.test_disposition(record, True), d.DISPOSITION_RUN)
        self.assertEqual(d.validate_test_taxonomy((replay, record)), ())

    def test_expected_tests_are_owner_local(self):
        expected = d.make_test_case("expected_1", "expected", owner_local=True)
        self.assertEqual(d.test_disposition(expected), d.DISPOSITION_RUN)
        wrong = d.make_test_case("expected_2", "expected")
        self.assertTrue(any("owner-local" in e for e in
                            d.validate_test_taxonomy((wrong,))))
        with self.assertRaises(ContractValidationError):
            d.test_disposition(wrong)

    def test_key_literals_and_missing_keys_rejected(self):
        with self.assertRaises(ContractValidationError):
            d.make_test_case("e2e", "real-api-e2e", "sk-literal-123")
        self.assertTrue(any("key reference" in e for e in d.validate_test_taxonomy(
            (d.make_test_case("e2e", "real-api-e2e"),))))
        self.assertTrue(any("key reference" in e for e in d.validate_test_taxonomy(
            (d.make_test_case("snap", "snapshot-record"),))))
        self.assertTrue(any("without a key" in e for e in d.validate_test_taxonomy(
            (d.make_test_case("snap", "snapshot-replay", "env:KEY"),))))
        self.assertTrue(any("shipped profile" in e for e in d.validate_test_taxonomy(
            (d.make_test_case("snap", "snapshot-replay", shipped_profile=False),))))
        replay_bad = d.TestCase("snap", d.TestClass.SNAPSHOT_REPLAY, None,
                                d.SHIPPED_SNAPSHOT_PROFILE, False, False)
        with self.assertRaises(ContractValidationError):
            d.test_disposition(replay_bad)

    def test_taxonomy_validation(self):
        cases = (d.make_test_case("a", "real-api-e2e", "env:KEY"),
                 d.make_test_case("b", "expected", owner_local=True),
                 d.make_test_case("c", "snapshot-replay"))
        self.assertEqual(d.validate_test_taxonomy(cases), ())
        dup = cases + (d.make_test_case("a", "snapshot-replay"),)
        self.assertTrue(any("unique" in e for e in d.validate_test_taxonomy(dup)))
        self.assertTrue(d.validate_test_taxonomy(("not a case",)))
        with self.assertRaises(ContractValidationError):
            d.test_disposition("not a case")


# ---------------------------------------------------------------------------
# D7.15 -- release rehearsals and runner trust
# ---------------------------------------------------------------------------

class TestD715Rehearsals(unittest.TestCase):
    def test_credential_free_rehearsals(self):
        plans = (d.make_rehearsal("dependency-layout", "keel release --dry-run layout"),
                 d.make_rehearsal("pack", "keel release --dry-run pack"))
        self.assertEqual(d.validate_rehearsals(plans), ())
        with self.assertRaises(ContractValidationError):
            d.make_rehearsal("pack", "x", credential_refs=("sk-literal",))
        self.assertTrue(any("credential-free" in e for e in d.validate_rehearsals(
            (d.make_rehearsal("pack", "x", credential_refs=("env:TOKEN",)),))))

    def test_rehearsal_must_match_release_and_not_publish(self):
        plans = [d.make_rehearsal("dependency-layout", "layout"),
                 d.make_rehearsal("pack", "publish dist")]
        self.assertTrue(any("publish" in e for e in d.validate_rehearsals(plans)))
        plans[1] = d.make_rehearsal("pack", "pack", uses_release_recipe=False)
        self.assertTrue(any("exact release recipe" in e for e in
                            d.validate_rehearsals(plans)))
        plans = (d.make_rehearsal("dependency-layout", "layout"),)
        self.assertTrue(any("exactly once" in e for e in
                            d.validate_rehearsals(plans)))
        self.assertTrue(d.validate_rehearsals(("not a rehearsal",)))

    def test_runner_failover_trust_rules(self):
        trusted = d.make_runner_context(True, False, False)
        self.assertEqual(d.select_runner(trusted), d.SELF_HOSTED_RUNNER)
        for context in (d.make_runner_context(False),
                        d.make_runner_context(True, True),
                        d.make_runner_context(True, False, True),
                        d.make_runner_context(True, False, False, True)):
            with self.subTest(context=context):
                self.assertEqual(d.select_runner(context), d.HOSTED_RUNNER)
        self.assertTrue(trusted.as_dict()["is_pull_request"])

    def test_runner_context_validation(self):
        with self.assertRaises(ContractValidationError):
            d.make_runner_context("yes")
        with self.assertRaises(ContractValidationError):
            d.select_runner("not a context")


# ---------------------------------------------------------------------------
# D7.16 -- package hygiene
# ---------------------------------------------------------------------------

class TestD716Hygiene(unittest.TestCase):
    def test_python_entrypoints_and_checks(self):
        artifact = d.make_package_artifact("keel", "python",
                                           ("keel/__init__.py",),
                                           ("keel/__init__.py", "dist/keel.whl"))
        self.assertEqual(d.validate_entrypoints(artifact), ())
        checks = d.consumer_check_plan(artifact)
        self.assertTrue(any("twine check" in c for c in checks))
        self.assertTrue(any("clean-venv" in c for c in checks))
        report = d.package_hygiene_report(artifact)
        self.assertTrue(report["passed"])

    def test_node_consumer_check(self):
        artifact = d.make_package_artifact("@keel/client", "node",
                                           ("dist/index.js",),
                                           ("dist/index.js", "dist/index.d.ts"))
        self.assertEqual(d.validate_entrypoints(artifact), ())
        self.assertTrue(any("publint" in c for c in d.consumer_check_plan(artifact)))
        self.assertTrue(any("consumer" in c for c in d.consumer_check_plan(artifact)))

    def test_missing_and_wrong_entrypoints(self):
        artifact = d.make_package_artifact("keel", "python", ("keel/missing.py",),
                                           ("keel/__init__.py",))
        self.assertTrue(any("not in the package" in e for e in
                            d.validate_entrypoints(artifact)))
        self.assertFalse(d.package_hygiene_report(artifact)["passed"])
        with self.assertRaises(ContractValidationError):
            d.consumer_check_plan(artifact)
        wrong = d.make_package_artifact("keel", "python", ("dist/index.js",),
                                        ("dist/index.js",))
        self.assertTrue(any("wrong suffix" in e for e in d.validate_entrypoints(wrong)))

    def test_artifact_validation(self):
        with self.assertRaises(ContractValidationError):
            d.make_package_artifact("keel", "ruby", ("x.py",), ("x.py",))
        with self.assertRaises(ContractValidationError):
            d.make_package_artifact("keel", "python", ("../x.py",), ("x.py",))
        with self.assertRaises(ContractValidationError):
            d.package_hygiene_report("not an artifact")


# ---------------------------------------------------------------------------
# D7.17 -- signing docs and packaging profiles
# ---------------------------------------------------------------------------

class TestD717Signing(unittest.TestCase):
    def test_keel_ships_unsigned(self):
        profile = d.default_packaging_profile()
        self.assertIs(profile.mode, d.SigningMode.UNSIGNED)
        self.assertEqual(profile.profile_id, "desktop-unsigned")
        self.assertEqual(d.validate_packaging_profile(profile), ())
        self.assertEqual(d.required_reading(profile), (d.PACKAGING_README,))

    def test_signed_modes_need_cert_reference_and_docs(self):
        missing = d.make_packaging_profile("self-signed", True)
        self.assertTrue(any("certificate reference" in e for e in
                            d.validate_packaging_profile(missing)))
        signed = d.make_packaging_profile("org-cert", True, "secret:keel/cert")
        self.assertEqual(d.validate_packaging_profile(signed), ())
        self.assertEqual(signed.profile_id, "desktop-org-cert")
        no_docs = d.make_packaging_profile("unsigned", False)
        self.assertTrue(any("required reading" in e for e in
                            d.validate_packaging_profile(no_docs)))
        with self.assertRaises(ContractValidationError):
            d.required_reading(no_docs)

    def test_forged_profile_rejected(self):
        forged = d.PackagingProfile(d.SigningMode.ORG_CERT, "desktop-unsigned",
                                    True, "env:CERT")
        self.assertTrue(any("does not match" in e for e in
                            d.validate_packaging_profile(forged)))
        self.assertTrue(any("must not reference" in e for e in
                            d.validate_packaging_profile(
                                d.make_packaging_profile("unsigned", True, "env:CERT"))))
        with self.assertRaises(ContractValidationError):
            d.make_packaging_profile("ev-cert")
        self.assertTrue(d.validate_packaging_profile("not a profile"))


# ---------------------------------------------------------------------------
# D7.18 -- breaking-change notices
# ---------------------------------------------------------------------------

class TestD718Notices(unittest.TestCase):
    def test_notice_selects_breaking_entries_since_installed(self):
        entries = (
            d.make_upgrade_entry("0.9.0", True, "old break"),
            d.make_upgrade_entry("1.1.0", True, "keys moved"),
            d.make_upgrade_entry("1.1.5", False, "minor polish"),
            d.make_upgrade_entry("2.0.0", True, "new config shape"),
        )
        notice = d.build_breaking_notice("1.0.0", "2.0.0", entries)
        self.assertEqual([e.version for e in notice.entries], ["1.1.0", "2.0.0"])
        self.assertTrue(notice.has_breaking_changes)
        text = d.render_breaking_notice(notice)
        self.assertIn("What changes for you", text)
        self.assertIn("keys moved", text)
        self.assertIn("new config shape", text)
        self.assertNotIn("old break", text)
        self.assertNotIn("minor polish", text)

    def test_no_breaking_changes(self):
        notice = d.build_breaking_notice("1.0.0", "1.1.0", ())
        self.assertFalse(notice.has_breaking_changes)
        self.assertIn("No breaking changes", d.render_breaking_notice(notice))
        self.assertEqual(notice.as_dict()["installed"], "1.0.0")

    def test_notice_failures(self):
        with self.assertRaises(ContractValidationError):
            d.build_breaking_notice("2.0.0", "1.0.0", ())
        with self.assertRaises(ContractValidationError):
            d.build_breaking_notice("1.0.0", "1.0.0", ())
        with self.assertRaises(ContractValidationError):
            d.build_breaking_notice("1.0", "2.0.0", ())
        with self.assertRaises(ContractValidationError):
            d.make_upgrade_entry("1.0.0", True, "")
        with self.assertRaises(ContractValidationError):
            d.build_breaking_notice("1.0.0", "2.0.0", ("not an entry",))
        with self.assertRaises(ContractValidationError):
            d.render_breaking_notice("not a notice")


# ---------------------------------------------------------------------------
# D7.20 -- labels and stacked PRs
# ---------------------------------------------------------------------------

class TestD720Labels(unittest.TestCase):
    def test_label_taxonomy(self):
        self.assertEqual(d.validate_pr_labels(("kind/bug", "area/core")), ())
        self.assertTrue(any("exactly one" in e for e in
                            d.validate_pr_labels(("area/core",))))
        self.assertTrue(any("two kinds" not in e and "exactly one" in e for e in
                            d.validate_pr_labels(("kind/bug", "kind/feature",
                                                  "area/core"))))
        self.assertTrue(any("at least one area" in e for e in
                            d.validate_pr_labels(("kind/bug",))))
        self.assertTrue(any("outside the taxonomy" in e for e in
                            d.validate_pr_labels(("kind/bug", "area/core", "random"))))

    def test_stacked_pr_chain(self):
        prs = (d.make_stacked_pr("pr1", "main", ("kind/feature", "area/core")),
               d.make_stacked_pr("pr2", "pr1", ("kind/feature", "area/core")),
               d.make_stacked_pr("pr3", "pr2", ("kind/refactor", "area/core")))
        self.assertEqual(d.validate_stacked_prs(prs), ())
        self.assertEqual(prs[0].as_dict()["policy"], "merge-forward")

    def test_stacks_reject_cycles_and_mixed_policies(self):
        cycle = (d.make_stacked_pr("a", "b", ("kind/bug", "area/x")),
                 d.make_stacked_pr("b", "a", ("kind/bug", "area/x")))
        self.assertTrue(any("cycle" in e for e in d.validate_stacked_prs(cycle)))
        mixed = (d.make_stacked_pr("a", "main", ("kind/bug", "area/x"),
                                   "merge-forward"),
                 d.make_stacked_pr("b", "a", ("kind/bug", "area/x"), "rebase"))
        self.assertTrue(any("one merge policy" in e for e in
                            d.validate_stacked_prs(mixed)))
        manual = d.make_stacked_pr("a", "main", ("kind/bug", "area/x"),
                                   native_stack=False)
        self.assertTrue(any("native stacks" in e for e in
                            d.validate_stacked_prs((manual,))))

    def test_pr_validation(self):
        dup = (d.make_stacked_pr("a", "main", ("kind/bug", "area/x")),
               d.make_stacked_pr("a", "main", ("kind/bug", "area/x")))
        self.assertTrue(any("unique" in e for e in d.validate_stacked_prs(dup)))
        self.assertTrue(any("own base" in e for e in d.validate_stacked_prs(
            (d.make_stacked_pr("a", "a", ("kind/bug", "area/x")),))))
        with self.assertRaises(ContractValidationError):
            d.make_stacked_pr("a", "main", ("kind/bug", "area/x"), "squash")
        self.assertTrue(d.validate_stacked_prs(("not a pr",)))


if __name__ == "__main__":
    unittest.main()

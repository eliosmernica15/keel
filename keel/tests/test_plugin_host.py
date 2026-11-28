"""Adversarial, stdlib-only tests for the local plugin host.

Temp directories come from ``tempfile``; no pytest fixtures or third-party test
helpers are required. The real ``keel`` package is used: loading duplicate
copies under a synthetic package name splits module/class identity and breaks
unrelated suites in the same pytest session.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import keel.plugin_host as ph  # noqa: E402
import keel.capabilities as capabilities  # noqa: E402
import keel.exec_guard as exec_guard  # noqa: E402
import keel.capability_registry as plugin_capabilities  # noqa: E402

ECHO_SCRIPT = """\
import json, sys
print(json.dumps({"args": json.loads(sys.argv[1])}))
"""

LOOP_SCRIPT = """\
import json, pathlib, subprocess, sys, time
args = json.loads(sys.argv[1])
marker = pathlib.Path(args["marker"])
subprocess.Popen([sys.executable, "-c",
    "import pathlib,sys,time; time.sleep(1.0); "
    "pathlib.Path(sys.argv[1]).write_text('grandchild survived')",
    str(marker)])
while True:
    time.sleep(0.05)
"""

CHATTY_SCRIPT = """\
import sys
print("x" * 200000)
print("y" * 200000, file=sys.stderr)
"""

SECRET_SCRIPT = """\
import json, os
print(json.dumps({
    "secret": os.environ.get("KEEL_TEST_SECRET", ""),
    "keys": sorted(k for k in os.environ if k.startswith("KEEL_")),
}))
"""


def manifest(name: str = "demo", version: str = "1.0.0", commands=None, **extra):
    document = {
        "name": name, "version": version,
        "description": "local test plugin", "author": "tester",
        "commands": commands if commands is not None else {
            "greet": {"argv": ["python", "echo.py"]}},
        "skills": [], "agents": [], "hooks": {}, "mcpServers": {},
        "capabilities": [], "permissions": [],
    }
    document.update(extra)
    return document


def write_plugin(base: Path, folder: str, document: dict,
                 files: dict[str, str] | None = None) -> Path:
    root = base / folder
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(document), encoding="utf-8")
    for relative, text in (files or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


class HostTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.host = ph.PluginHost(self.state)
        self.source = self.root / "source"
        self.source.mkdir()

    def make_source(self, *, name: str = "demo", folder: str = "demo-src",
                    commands=None, script: str = ECHO_SCRIPT, script_name="echo.py",
                    **extra) -> Path:
        return write_plugin(
            self.source, folder,
            manifest(name=name, commands=commands, **extra),
            {script_name: script})


class ManifestTests(HostTestCase):
    def test_parses_claude_subset_and_keel_fields(self):
        parsed = ph.parse_manifest({
            "name": "demo", "version": "1.2.3",
            "description": "desc", "author": {"name": "tester"},
            "commands": {"greet": {"argv": ["python", "bin/echo.py"]},
                         "other": {"argv": ["./bin/tool", "--flag"]}},
            "skills": ["skills/a.md"], "agents": ["agents/b.md"],
            "hooks": {"PreToolUse": ["hooks/check.py"]},
            "mcpServers": {"local": {"command": "ignored",
                                     "env": {"API_TOKEN": "secret-value"}}},
            "capabilities": ["context.read"], "permissions": ["read"],
        })
        data = parsed.to_dict()
        self.assertEqual(data["name"], "demo")
        self.assertEqual(data["version"], "1.2.3")
        self.assertEqual(data["author"], "tester")
        self.assertEqual([c["name"] for c in data["commands"]],
                         ["greet", "other"])
        self.assertEqual(data["commands"][0]["argv"],
                         ["python", "bin/echo.py"])
        self.assertEqual(data["skills"], ["skills/a.md"])
        self.assertEqual(data["hooks"],
                         [{"event": "PreToolUse", "path": "hooks/check.py"}])
        # MCP specs may carry credentials; only their names are retained.
        self.assertEqual(data["mcp_servers"], ["local"])
        self.assertNotIn("secret-value", json.dumps(data))
        self.assertEqual(data["capabilities"], ["context.read"])
        self.assertEqual(data["permissions"], ["read"])

    def test_invalid_version_rejected(self):
        for bad in ("1.0", "not-semver", "", 1, "1.2.3; rm -rf /"):
            with self.subTest(bad=bad), self.assertRaises(ph.ManifestError):
                ph.parse_manifest({"name": "demo", "version": bad})

    def test_path_traversal_rejected(self):
        cases = (
            ({"name": "../evil", "version": "1.0.0"}, ph.UnsafePathError),
            ({"name": "ok", "version": "1.0.0",
              "commands": {"x": {"argv": ["../outside.py"]}}},
             ph.UnsafePathError),
            ({"name": "ok", "version": "1.0.0",
              "commands": {"x": {"argv": ["/usr/bin/python"]}}},
             ph.UnsafePathError),
            ({"name": "ok", "version": "1.0.0",
              "commands": {"x": {"argv": ["python", "a/../../b.py"]}}},
             ph.UnsafePathError),
            ({"name": "ok", "version": "1.0.0",
              "skills": ["../secret.md"]}, ph.UnsafePathError),
        )
        for document, error in cases:
            with self.subTest(document=document), self.assertRaises(error):
                ph.parse_manifest(document)

    def test_forbidden_capability_rejected(self):
        for capability in ("exec", "shell", "network", "write"):
            with self.subTest(capability=capability), \
                    self.assertRaises(ph.ManifestError):
                ph.parse_manifest({"name": "demo", "version": "1.0.0",
                                   "capabilities": [capability]})

    def test_plugins_dir_must_stay_inside_state_root(self):
        with self.assertRaises(ph.UnsafePathError):
            ph.PluginHost(self.state, plugins_dir=self.root / "elsewhere")

    def test_corrupt_state_fails_closed(self):
        (self.state / "plugins-state.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(ph.PluginHostError):
            self.host.discover()


class LifecycleTests(HostTestCase):
    def test_discovery_never_executes_and_defaults_to_disabled(self):
        marker = self.root / "marker.txt"
        source = self.make_source(commands={
            "greet": {"argv": ["python", "echo.py"]}},
            script=f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
        self.host.install(source)
        records = self.host.discover()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["state"], ph.PluginState.DISABLED.value)
        self.assertEqual(records[0]["name"], "demo")
        self.assertFalse(marker.exists())
        with self.assertRaises(ph.PluginDisabled):
            self.host.invoke("demo", "greet")

    def test_tampering_after_enable_is_quarantined(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        script = self.host.plugins_root / "demo" / "echo.py"
        script.write_text("print('tampered')\n", encoding="utf-8")
        with self.assertRaises(ph.PluginQuarantined):
            self.host.invoke("demo", "greet")

    def test_enable_disable_and_invoke(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        result = self.host.invoke("demo", "greet", {"who": "keel"})
        self.assertTrue(result["ok"])
        self.assertEqual(json.loads(result["stdout"])["args"],
                         {"who": "keel"})
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])
        self.host.disable("demo")
        with self.assertRaises(ph.PluginDisabled):
            self.host.invoke("demo", "greet")

    def test_missing_manifest_is_invalid(self):
        broken = self.plugins_dir() / "broken"
        broken.mkdir(parents=True)
        (broken / "readme.txt").write_text("no manifest", encoding="utf-8")
        records = self.host.discover()
        record = next(r for r in records if r["name"] == "broken")
        self.assertEqual(record["state"], ph.PluginState.INVALID.value)
        self.assertEqual(record["reason"], "missing_manifest")
        with self.assertRaises(ph.PluginInvalid):
            self.host.enable("broken")
        with self.assertRaises(ph.PluginInvalid):
            self.host.invoke("broken", "greet")

    def test_symlink_escape_rejected(self):
        # Windows may forbid creating real symlinks without elevated privileges;
        # patch the check itself so the containment logic is exercised everywhere.
        outside = self.root / "outside"
        outside.mkdir()
        write_plugin(outside, "plugin", manifest(), {"echo.py": ECHO_SCRIPT})
        linked_root = self.plugins_dir() / "linked"
        linked_root.mkdir()
        real_is_symlink = Path.is_symlink

        def fake_is_symlink(path):
            return path.name in ("linked", "leak.txt") or real_is_symlink(path)

        with patch.object(Path, "is_symlink", fake_is_symlink):
            record = next(r for r in self.host.discover()
                          if r["name"] == "linked")
            self.assertEqual(record["reason"], "symlink_plugin_root")
            with self.assertRaises(ph.PluginInvalid):
                self.host.enable("linked")

            source = self.make_source(folder="symlink-src", name="symlinked")
            (source / "leak.txt").write_text("outside data", encoding="utf-8")
            with self.assertRaises(ph.UnsafePathError):
                self.host.install(source)

    def test_duplicate_names_are_refused_and_marked_invalid(self):
        first = self.make_source(folder="first", name="demo")
        self.host.install(first)
        second = write_plugin(
            self.source, "second",
            manifest(name="demo", commands={"greet": {"argv": ["python", "echo.py"]}}),
            {"echo.py": "print('other')"})
        with self.assertRaises(ph.DuplicatePlugin):
            self.host.install(second)

        # Even a direct copy into the plugins root cannot create ambiguity.
        direct = self.plugins_dir() / "another-folder"
        direct.mkdir()
        (direct / ".claude-plugin").mkdir()
        (direct / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(manifest(name="demo")), encoding="utf-8")
        (direct / "echo.py").write_text(ECHO_SCRIPT, encoding="utf-8")
        self.assertTrue(all(r["state"] == ph.PluginState.INVALID.value
                            and r["reason"] == "duplicate_name"
                            for r in self.host.discover()))
        with self.assertRaises(ph.PluginInvalid):
            self.host.enable("demo")

    def test_install_is_idempotent(self):
        source = self.make_source()
        first = self.host.install(source)
        second = self.host.install(source)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(len(self.host.discover()), 1)
        self.assertFalse([p for p in self.plugins_dir().iterdir()
                          if p.name.startswith(".staging-")])
        state = json.loads((self.state / "plugins-state.json").read_text())
        self.assertEqual(len(state["plugins"]), 1)
        self.assertFalse(state["plugins"]["demo"]["enabled"])

    def test_quarantine_and_remove(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        quarantined = self.host.quarantine("demo", reason="operator review")
        self.assertEqual(quarantined["state"], ph.PluginState.QUARANTINED.value)
        with self.assertRaises(ph.PluginQuarantined):
            self.host.invoke("demo", "greet")
        self.assertTrue(any(r["state"] == ph.PluginState.QUARANTINED.value
                            for r in self.host.discover()))
        self.assertTrue(self.host.remove("demo"))
        self.assertFalse(any(r["name"] == "demo"
                             for r in self.host.discover()))

    def test_quarantined_plugin_can_be_removed(self):
        self.host.install(self.make_source())
        self.host.quarantine("demo")
        self.assertTrue(self.host.remove("demo"))
        self.assertEqual(self.host.audit_events()[-1]["event"], "plugin.remove")

    def test_audit_records_are_structured_and_redacted(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        self.host.invoke("demo", "greet", {"who": "do-not-log-me"})
        events = self.host.audit_events()
        self.assertTrue(any(event["event"] == "plugin.install" for event in events))
        invoke = next(event for event in events if event["event"] == "plugin.invoke")
        self.assertEqual(invoke["args_keys"], ["who"])
        self.assertNotIn("do-not-log-me", json.dumps(events))
        self.assertEqual(invoke["plugin"], "demo")

    def plugins_dir(self) -> Path:
        return self.state / "plugins"


class ExecutionTests(HostTestCase):
    def invoke_with_script(self, script, *, name="runner", command="run",
                           args=None, **limits):
        source = write_plugin(
            self.source, "runner-src",
            manifest(name=name, commands={command: {"argv": ["python", "run.py"]}}),
            {"run.py": script})
        self.host.install(source)
        self.host.enable(name)
        return self.host.invoke(name, command, args or {}, **limits)

    def test_timeout_terminates_child_and_its_descendants(self):
        marker = self.root / "grandchild-marker.txt"
        started = time.monotonic()
        result = self.invoke_with_script(
            LOOP_SCRIPT, args={"marker": str(marker)}, timeout_s=0.4)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["ok"])
        self.assertLess(time.monotonic() - started, 8.0)
        time.sleep(1.4)
        self.assertFalse(marker.exists(), "grandchild survived process-tree kill")
        event = next(e for e in self.host.audit_events()
                     if e["event"] == "plugin.invoke")
        self.assertTrue(event["timed_out"])

    def test_oversized_output_is_bounded(self):
        result = self.invoke_with_script(
            CHATTY_SCRIPT, max_output_bytes=256)
        self.assertTrue(result["output_truncated"])
        self.assertLessEqual(len(result["stdout"]), 256)
        self.assertLessEqual(len(result["stderr"]), 256)
        event = next(e for e in self.host.audit_events()
                     if e["event"] == "plugin.invoke")
        self.assertTrue(event["output_truncated"])

    def test_secret_environment_is_not_inherited_or_audited(self):
        with patch.dict(os.environ, {"KEEL_TEST_SECRET": "top-secret-value"}):
            result = self.invoke_with_script(SECRET_SCRIPT)
        payload = json.loads(result["stdout"])
        self.assertEqual(payload["secret"], "")
        self.assertNotIn("KEEL_TEST_SECRET", payload["keys"])
        self.assertIn("KEEL_PLUGIN_NAME", payload["keys"])
        self.assertNotIn("top-secret-value", result["stderr"])
        self.assertNotIn("top-secret-value",
                         (self.state / "plugins-audit.jsonl").read_text())

    def test_unknown_command_is_rejected(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        with self.assertRaises(ph.InvocationError):
            self.host.invoke("demo", "not-declared")

    def test_capability_routes_are_registered_and_policy_bound(self):
        routes = {row["id"]: row for row in capabilities.list_capabilities()}
        self.assertEqual(routes["core.plugins.list"]["permission"], "read")
        self.assertEqual(routes["core.plugins.invoke"]["permission"], "execute")
        self.assertTrue(routes["core.plugins.invoke"]["mutates"])

        source = self.make_source()
        self.host.install(source)
        listed = capabilities.invoke(
            "core.plugins.list", {}, context={"state_root": str(self.state)})
        self.assertTrue(listed["ok"])
        self.assertEqual([p["name"] for p in listed["result"]["plugins"]],
                         ["demo"])

        with self.assertRaises(capabilities.CapabilityError):
            capabilities.invoke(
                "core.plugins.invoke", {"name": "demo", "command": "greet"},
                context={"state_root": str(self.state)})

        self.host.enable("demo")
        invoked = capabilities.invoke(
            "core.plugins.invoke", {"name": "demo", "command": "greet",
                                    "args": {"ok": True}},
            context={"state_root": str(self.state)})
        self.assertTrue(invoked["ok"])
        self.assertEqual(json.loads(invoked["result"]["stdout"]),
                         {"args": {"ok": True}})

    def test_exec_policy_sees_real_argv_not_synthetic_name(self):
        self.host.install(self.make_source())
        self.host.enable("demo")
        seen = {}

        def spy(cap_id, params, ctx=None, **kwargs):
            seen["cap_id"] = cap_id
            seen["argv"] = [str(x) for x in params.get("argv", [])]
            return None

        with patch.object(plugin_capabilities.exec_guard, "enforce_command", spy):
            invoked = capabilities.invoke(
                "core.plugins.invoke", {"name": "demo", "command": "greet"},
                context={"state_root": str(self.state)})
        self.assertTrue(invoked["ok"])
        self.assertEqual(seen["cap_id"], "core.plugins.invoke")
        self.assertTrue(any("echo.py" in part for part in seen["argv"]),
                        f"policy must see the real executable: {seen['argv']}")
        self.assertNotIn("demo:greet", " ".join(seen["argv"]))


if __name__ == "__main__":
    unittest.main()

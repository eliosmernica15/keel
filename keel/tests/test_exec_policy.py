"""A1.6/B3.4/B7.1 — declarative execution policy adapted from Codex execpolicy.

Semantics exercised here mirror the inspected upstream implementation
(openai/codex @ ef33e43a, codex-rs/execpolicy).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from keel.exec_policy import (ALLOW, FORBIDDEN, PROMPT, ExecPolicyStore,
                              PolicyError, from_dict, normalize_host, tokenize)

ROOT = Path(__file__).resolve().parents[1]


def _policy(**kwargs):
    return from_dict({"prefix_rules": [], "network_rules": [], **kwargs})


def test_tokenize():
    assert tokenize('git reset --hard "a b"') == [
        "git", "reset", "--hard", "a b"]
    assert tokenize(["ls", "-l"]) == ["ls", "-l"]


def test_decision_severity_max():
    p = _policy(prefix_rules=[
        {"pattern": ["git", "status"]},
        {"pattern": ["git", "reset", "--hard"], "decision": "forbidden",
         "justification": "destructive"},
    ])
    assert p.check("git status").decision == ALLOW
    assert p.check("git reset --hard").decision == FORBIDDEN
    # both match -> most restrictive wins
    both = _policy(prefix_rules=[
        {"pattern": ["git"]},
        {"pattern": ["git", "push", "--force"], "decision": "forbidden"},
    ])
    evaluation = both.check("git push --force")
    assert evaluation.decision == FORBIDDEN
    # Both prefix rules match; the most restrictive wins.
    assert {m.decision for m in evaluation.matched_rules} == {ALLOW, FORBIDDEN}


def test_prefix_alternatives_and_order():
    p = _policy(prefix_rules=[{"pattern": ["git", ["reset", "restore"], "--hard"],
                               "decision": "prompt"}])
    assert p.check("git reset --hard").decision == PROMPT
    assert p.check("git restore --hard").decision == PROMPT
    assert p.check("git checkout --hard").decision == ALLOW
    assert p.check("git reset").decision == ALLOW  # too short
    assert p.check("git reset --hard extra").matched_rules[0].matched_prefix == [
        "git", "reset", "--hard"]


def test_justification_and_is_match():
    p = _policy(prefix_rules=[{"pattern": ["ls"], "justification": "read only"}])
    evaluation = p.check("ls -la")
    assert evaluation.is_match is True
    assert evaluation.matched_rules[0].justification == "read only"
    assert _policy().check("unknown").is_match is False


def test_self_tests_validated_at_load():
    doc = {"prefix_rules": [{"pattern": ["git", "reset", "--hard"],
                             "decision": "forbidden",
                             "match": ["git reset --hard"],
                             "not_match": ["git reset --keep", "git reset --merge"]}]}
    policy = from_dict(doc)
    assert policy.check("git reset --hard").decision == FORBIDDEN
    with pytest.raises(PolicyError):
        from_dict({"prefix_rules": [{"pattern": ["ls"],
                                     "match": ["cat file"]}]})
    with pytest.raises(PolicyError):
        from_dict({"prefix_rules": [{"pattern": ["ls"],
                                     "not_match": ["ls -l"]}]})


def test_network_rules_and_compiled_domains():
    p = _policy(network_rules=[
        {"host": "api.example.com", "protocol": "https", "decision": "allow"},
        {"host": "bad.example.com", "protocol": "https", "decision": "forbidden",
         "justification": "exfiltration risk"},
    ])
    allowed, denied = p.compiled_network_domains()
    assert allowed == ["api.example.com"]
    assert denied == ["bad.example.com"]
    assert p.evaluate_network("api.example.com") == ALLOW
    assert p.evaluate_network("bad.example.com") == FORBIDDEN
    assert p.evaluate_network("unknown.example.com") == PROMPT
    # later rule for the same host overrides earlier
    p2 = _policy(network_rules=[
        {"host": "x.example.com", "protocol": "https", "decision": "forbidden"},
        {"host": "x.example.com", "protocol": "https", "decision": "allow"},
    ])
    assert p2.evaluate_network("x.example.com") == ALLOW


def test_network_protocol_specific_rules():
    p = _policy(network_rules=[
        {"host": "split.example.com", "protocol": "http", "decision": "allow"},
        {"host": "split.example.com", "protocol": "https",
         "decision": "forbidden"},
        {"host": "any.example.com", "protocol": "*", "decision": "forbidden"},
    ])
    assert p.evaluate_network("split.example.com", "http") == ALLOW
    assert p.evaluate_network("split.example.com", "https") == FORBIDDEN
    assert p.evaluate_network("split.example.com", "socks5_tcp") == PROMPT
    assert p.evaluate_network("any.example.com", "http") == FORBIDDEN
    assert p.evaluate_network("any.example.com", "socks5_udp") == FORBIDDEN


def test_malformed_policy_rejected():
    for doc in (
        {"prefix_rules": [{"pattern": []}]},
        {"prefix_rules": [{"pattern": ["ls"], "decision": "bogus"}]},
        {"prefix_rules": [{"pattern": [["a", "b"], []]}]},
        {"network_rules": [{"host": "", "protocol": "https"}]},
        {"network_rules": [{"host": "x.com", "protocol": "ftp"}]},
    ):
        with pytest.raises(PolicyError):
            from_dict(doc)


def test_network_host_normalization():
    assert normalize_host(" Example.COM. ") == "example.com"
    assert normalize_host("[::1]:8443") == "::1"
    assert normalize_host("host:443") == "host"
    with pytest.raises(PolicyError):
        normalize_host("https://example.com/path")


def test_fingerprint_order_independent_and_overlay():
    a = _policy(prefix_rules=[
        {"pattern": ["ls"]}, {"pattern": ["cat"]}])
    b = _policy(prefix_rules=[
        {"pattern": ["cat"]}, {"pattern": ["ls"]}])
    assert a.fingerprint() == b.fingerprint()
    overlay = _policy(prefix_rules=[
        {"pattern": ["rm", "-rf"], "decision": "forbidden"}])
    merged = a.merge_overlay(overlay)
    assert merged.check("rm -rf /").decision == FORBIDDEN
    assert merged.check("ls").decision == ALLOW
    assert set(merged.allowed_prefixes()) == {"ls", "cat"}


def test_host_executable_constraint(tmp_path):
    exe = tmp_path / "python"
    exe.write_text("", encoding="utf-8")
    p = _policy(prefix_rules=[{"pattern": ["python", "--version"]}],
                host_executables={"python": [str(exe.resolve())]})
    assert p.check([str(exe), "--version"],
                   resolve_host_executables=True).is_match is True
    other = _policy(prefix_rules=[{"pattern": ["python", "--version"]}],
                    host_executables={"python": [str(tmp_path / "other")]})
    assert other.check([str(exe), "--version"],
                       resolve_host_executables=True).is_match is False


def test_store_roundtrip(tmp_path):
    store = ExecPolicyStore(tmp_path)
    doc = {"prefix_rules": [{"pattern": ["ls"]}],
           "network_rules": [], "host_executables": {}}
    store.save("default", doc)
    assert store.list() == ["default"]
    assert store.load("default").check("ls").decision == ALLOW
    assert store.document("default")["prefix_rules"][0]["pattern"] == ["ls"]


def test_capabilities():
    from keel import capability_registry  # noqa: F401
    from keel.capabilities import invoke

    doc = {"prefix_rules": [{"pattern": ["git", "reset", "--hard"],
                             "decision": "forbidden"}], "network_rules": []}
    validated = invoke("core.execpolicy.validate", {"policy": doc},
                       context={})["result"]
    assert validated["ok"] is True
    result = invoke("core.execpolicy.evaluate",
                    {"policy": doc, "command": "git reset --hard"},
                    context={})["result"]
    assert result["decision"] == FORBIDDEN
    net = invoke("core.execpolicy.network",
                 {"policy": doc, "host": "example.com"}, context={})["result"]
    assert net["decision"] == PROMPT


def test_cli(tmp_path):
    doc = {"prefix_rules": [{"pattern": ["ls"], "match": ["ls -l"]}],
           "network_rules": []}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    for args, expected in [
        (["validate", str(path)], '"ok": true'),
        (["check", str(path), "ls", "-la"], '"decision": "allow"'),
    ]:
        proc = subprocess.run([sys.executable, "-m", "keel", "execpolicy", *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert expected in proc.stdout

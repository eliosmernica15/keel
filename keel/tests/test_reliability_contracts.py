"""Permanent contract-regression specs for the X9.x reliability contracts.

Covers the four not_started P0 rows of the 865-row registry:
X9.1 (loopback fixture model server), X9.3 (one provider behaviour suite for
every adapter), X9.5 (cross-platform path/permission matrix) and X9.7
(migration matrix with data checksums).

The specs are additive: they import only ``keel.reliability_contracts``.  The
server binds loopback sockets only when a test enters its context manager; no
external network, credential or filesystem mutation is used.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

import pytest

import keel.reliability_contracts as rc
from keel.reliability_contracts import (  # focused aliases for readability
    CURRENT_SCHEMA_VERSION, RELEASED_VERSIONS, Dialect, EventKind,
    PathCase, PathHazard, Permission, PermissionRequest, Platform, Principal,
    ScriptEvent,
)


def _post(server, path, model=None, *, body=None, headers=None, raw=None):
    if raw is None:
        payload = dict(body or {})
        if model is not None:
            payload["model"] = model
        raw = rc.canonical_bytes(payload)
    request = urllib.request.Request(
        server.base_url + path, data=raw, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except http.client.IncompleteRead as exc:
        # A deliberately cut stream is an observed outcome, not a test error.
        return 200, {}, exc.partial


def _sse_payloads(raw: bytes) -> list[bytes]:
    return [line[6:] for line in raw.split(b"\n\n")
            if line.startswith(b"data: ")]


def _sse_objects(raw: bytes) -> list[dict]:
    return [json.loads(p) for p in _sse_payloads(raw) if p != b"[DONE]"]


def _script_set(**replacements):
    scripts = list(rc.standard_scripts())
    for index, script in enumerate(scripts):
        if script.name in replacements:
            scripts[index] = replacements[script.name]
    return tuple(scripts)


# ===========================================================================
# X9.1 -- fixture model server
# ===========================================================================


def test_script_events_are_typed_and_fail_closed():
    with pytest.raises(rc.ValidationError):
        ScriptEvent("text")  # type: ignore[arg-type] - not an EventKind
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.SLOW_TOKEN, text="x", delay_ms=0)
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.ERROR, status=200, error="not an error")
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.ERROR, status=429)
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.MALFORMED_JSON, raw=b'{"valid":true}')
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.FINISH, finish_reason="banana")
    with pytest.raises(rc.ValidationError):
        ScriptEvent(EventKind.TEXT, text="x", delay_ms=-1)
    assert ScriptEvent(EventKind.TEXT, text="ok").as_dict()["kind"] == "text"


def test_scripts_validate_structure_tool_json_and_binding():
    good = ScriptEvent(EventKind.TEXT, text="x")
    with pytest.raises(rc.ValidationError):
        rc.FixtureScript("bad", "fx-bad", ())
    with pytest.raises(rc.ValidationError):
        rc.FixtureScript("bad", "fx bad", (good,))
    finish = ScriptEvent(EventKind.FINISH, finish_reason="stop")
    with pytest.raises(rc.ValidationError):
        rc.FixtureScript("bad", "fx-bad", (good, finish, finish))
    with pytest.raises(rc.ValidationError):
        rc.FixtureScript("bad", "fx-bad", (ScriptEvent(
            EventKind.TOOL_CALL, tool_name="t", arguments="{oops"),))
    with pytest.raises(rc.ValidationError):
        rc.FixtureScript("bad", "fx-bad", (ScriptEvent(
            EventKind.TOOL_CALL, tool_name="t", arguments="[1,2]"),))
    bound = rc.FixtureScript("bound", "fx-bound", (good,),
                             dialect=Dialect.OPENAI_CHAT)
    assert bound.frames(Dialect.OPENAI_CHAT)
    with pytest.raises(rc.ValidationError):
        bound.frames(Dialect.GEMINI_GENERATE)


def test_script_rendering_is_deterministic_across_all_dialects():
    scripts = rc.standard_scripts()
    assert len(scripts) == 7
    assert {s.name for s in scripts} == {
        "stream", "tool_call", "usage", "error", "malformed_json",
        "partial_stream", "slow_tokens"}
    for script in scripts:
        for dialect in Dialect:
            first = rc.render_script(script, dialect)
            second = rc.render_script(script, dialect)
            assert first == second
            assert first
            assert all(isinstance(f, rc.WireFrame) for f in first)
        assert script.fingerprint == rc.fingerprint(script.as_dict())


def test_server_refuses_non_loopback_duplicates_and_ambiguous_selectors():
    with pytest.raises(rc.ValidationError):
        rc.FixtureModelServer(host="0.0.0.0")
    text = ScriptEvent(EventKind.TEXT, text="x")
    dup = rc.FixtureScript("one", "fx-one", (text,))
    with pytest.raises(rc.ValidationError):
        rc.FixtureModelServer((dup, rc.FixtureScript("two", "fx-one", (text,))))
    with pytest.raises(rc.ValidationError):
        rc.FixtureModelServer((dup, rc.FixtureScript("fx-one", "fx-two", (text,))))
    with pytest.raises(rc.ValidationError):
        rc.FixtureModelServer(("not a script",))  # type: ignore[arg-type]
    with pytest.raises(rc.ValidationError):
        rc.FixtureModelServer(sleeper="not-callable")  # type: ignore[arg-type]


def test_server_streams_scripted_text_usage_and_done():
    with rc.make_fixture_server() as server:
        status, _headers, raw = _post(server, "/v1/chat/completions", "fx-stream")
        assert status == 200
        payloads = _sse_payloads(raw)
        assert payloads[-1] == b"[DONE]"
        objects = _sse_objects(raw)
        text = "".join(o["choices"][0]["delta"].get("content", "")
                       for o in objects if o.get("choices"))
        assert text == "Hello world."
        usage = next(o["usage"] for o in objects if "usage" in o)
        assert (usage["prompt_tokens"], usage["completion_tokens"]) == (12, 4)
        assert len(server.requests) == 1
        assert server.requests[0].script_name == "stream"
        stats = server.stream_stats("stream", Dialect.OPENAI_CHAT)
        assert stats.frames_sent == 6 and not stats.terminated
        assert _headers.get("Content-Type") == "text/event-stream"


def test_server_replays_tool_calls_with_fragmented_arguments():
    with rc.make_fixture_server() as server:
        _status, _headers, raw = _post(server, "/v1/chat/completions", "fx-tool")
        calls = [call for obj in _sse_objects(raw) for choice in obj.get("choices", [])
                 for call in choice["delta"].get("tool_calls", [])]
        arguments = "".join(c["function"].get("arguments", "") for c in calls)
        assert json.loads(arguments) == {"city": "Oslo"}
        assert calls[0]["id"] == "call_fx_0"
        assert "".join(c["function"].get("name", "") for c in calls) == "get_weather"


def test_server_replays_malformed_json_and_counts_it_on_the_wire():
    with rc.make_fixture_server() as server:
        _status, _headers, raw = _post(server, "/v1/chat/completions",
                                       "fx-malformed")
        payloads = _sse_payloads(raw)
        assert b"{not-json" in payloads
        with pytest.raises(json.JSONDecodeError):
            json.loads(b"{not-json")
        stats = server.stream_stats("malformed_json", Dialect.OPENAI_CHAT)
        assert stats.malformed_frames == 1
        assert "malformed_json" in stats.notes


def test_server_replays_partial_stream_without_a_terminal_frame():
    with rc.make_fixture_server() as server:
        _status, _headers, raw = _post(server, "/v1/chat/completions",
                                       "fx-partial")
        assert b"[DONE]" not in raw
        assert b"partial" in raw
        stats = server.stream_stats("partial_stream", Dialect.OPENAI_CHAT)
        assert stats.terminated is True


def test_server_replays_slow_tokens_with_an_injected_sleeper():
    delays: list[int] = []
    with rc.make_fixture_server(sleeper=delays.append) as server:
        _status, _headers, raw = _post(server, "/v1/chat/completions", "fx-slow")
        assert len(_sse_payloads(raw)) == 6  # three delayed tokens + usage/finish/done
        assert delays == [10, 10, 10]
        assert server.stream_stats("slow_tokens", Dialect.OPENAI_CHAT).delays_ms == 30


def test_server_replays_errors_and_fails_closed_on_bad_requests():
    with rc.make_fixture_server() as server:
        status, _headers, raw = _post(server, "/v1/chat/completions", "fx-error")
        assert status == 429
        body = json.loads(raw)
        assert body["error"]["type"] == "rate_limit_error"
        assert server.stream_stats("error", Dialect.OPENAI_CHAT).error_frames == 1

        assert _post(server, "/v1/chat/completions", "does-not-exist")[0] == 503
        assert _post(server, "/v1/chat/completions", raw=b"{broken")[0] == 400
        assert _post(server, "/v1/chat/completions", raw=b"[]")[0] == 400
        assert _post(server, "/nope", "fx-stream")[0] == 404
        assert _post(server, "/v1/chat/completions", raw=b"x" * (
            rc.MAX_BODY_BYTES + 1))[0] == 413
        with pytest.raises(urllib.error.HTTPError) as get_error:
            urllib.request.urlopen(server.base_url + "/v1/chat/completions",
                                   timeout=5)
        assert get_error.value.code == 405


def test_call_budget_is_fail_closed_and_reset_is_explicit():
    script = rc.FixtureScript("one", "fx-one", (
        ScriptEvent(EventKind.TEXT, text="x"),
        ScriptEvent(EventKind.FINISH, finish_reason="stop")), max_calls=1)
    with rc.make_fixture_server((script,)) as server:
        assert _post(server, "/v1/chat/completions", "fx-one")[0] == 200
        denied = _post(server, "/v1/chat/completions", "fx-one")
        assert denied[0] == 503
        assert "budget exhausted" in denied[2].decode("utf-8")
        server.reset()
        assert _post(server, "/v1/chat/completions", "fx-one")[0] == 200
        assert len(server.requests) == 1


def test_recorded_requests_redact_credentials():
    with rc.make_fixture_server() as server:
        _post(server, "/v1/chat/completions", "fx-stream",
              headers={"Authorization": "Bearer super-secret",
                       "X-Keel-Fixture-Script": "stream"})
        record = server.requests[0].as_dict()
        assert record["headers"]["authorization"] == "<redacted>"
        assert "super-secret" not in json.dumps(record)
        assert record["script_name"] == "stream"
        assert record["headers"]["x-keel-fixture-script"] == "stream"


# ===========================================================================
# X9.3 -- shared provider behaviour suite
# ===========================================================================


def test_suite_passes_for_every_real_adapter():
    with rc.make_fixture_server() as server:
        reports = rc.ProviderContractSuite().run_all(server)
    assert set(reports) == {"openai-compatible", "anthropic", "google-gemini"}
    for report in reports.values():
        assert report.ok, [f.as_dict() for f in report.failures]
        assert len(report.results) == len(rc.ProviderContractSuite.CASES) == 8
        assert {r.case for r in report.results} == {
            "streaming", "tool_call", "usage", "errors", "malformed_json",
            "partial_stream", "slow_tokens", "cancel"}
    assert len(rc.default_bindings()) == 3


def test_suite_fingerprints_are_deterministic_across_servers():
    fingerprints = []
    for _ in range(2):
        with rc.make_fixture_server() as server:
            reports = rc.ProviderContractSuite().run_all(server)
        fingerprints.append({name: r.fingerprint for name, r in reports.items()})
    assert fingerprints[0] == fingerprints[1]


def test_suite_checks_streaming_tools_and_usage_against_wire_truth():
    with rc.make_fixture_server() as server:
        report = rc.ProviderContractSuite().run(
            rc.default_bindings()[0], server)
    by_case = {r.case: r for r in report.results}
    assert "Hello world." in by_case["streaming"].detail
    assert "get_weather" in by_case["tool_call"].detail
    assert "{'city': 'Oslo'}" in by_case["tool_call"].detail
    assert "input_tokens': 101" in by_case["usage"].detail
    assert by_case["errors"].transport_closed is False  # status was returned
    assert by_case["cancel"].transport_closed is True
    assert by_case["cancel"].ok


def test_suite_reports_typed_error_mapping_for_each_status():
    for status, category in ((401, "authentication_failed"),
                             (500, "server_error"), (503, "overloaded")):
        error = rc.FixtureScript("error", "fx-error", (
            ScriptEvent(EventKind.ERROR, status=status, error="fixture failure"),))
        with rc.make_fixture_server(_script_set(error=error)) as server:
            report = rc.ProviderContractSuite().run(rc.default_bindings()[0],
                                                     server)
        result = next(r for r in report.results if r.case == "errors")
        assert result.ok, result.detail
        assert category in result.detail


def test_suite_never_claims_success_for_a_broken_adapter():
    class EmptyAdapter:
        def complete(self, _request):
            return iter(())

    binding = rc.AdapterBinding(
        "broken", Dialect.OPENAI_CHAT,
        lambda url, transport: rc.KeelAdapter(
            "broken", EmptyAdapter()))
    with rc.make_fixture_server() as server:
        report = rc.ProviderContractSuite().run(binding, server)
    assert not report.ok
    assert report.failures
    assert all(not r.ok for r in report.failures)


def test_malformed_frames_and_partial_streams_are_not_success():
    with rc.make_fixture_server() as server:
        report = rc.ProviderContractSuite().run(rc.default_bindings()[0], server)
    by_case = {r.case: r for r in report.results}
    malformed = by_case["malformed_json"]
    assert malformed.ok and "malformed_frames=1" in malformed.detail
    assert "not-json" not in "".join(
        str(e) for e in malformed.events)
    partial = by_case["partial_stream"]
    assert partial.ok and "terminated=True" in partial.detail
    assert "counted=False" in partial.detail


def test_slow_token_case_verifies_wire_delays():
    with rc.make_fixture_server() as server:
        report = rc.ProviderContractSuite().run(rc.default_bindings()[0], server)
    slow = next(r for r in report.results if r.case == "slow_tokens")
    assert slow.ok and "delays_ms=30" in slow.detail
    assert rc._text_of(slow.events) == "slo"


def test_transport_rejects_external_urls_and_malformed_requests():
    transport = rc.TrackingHTTPTransport()
    with pytest.raises(rc.ValidationError):
        transport({"url": "https://api.example.com/v1/chat/completions"})
    with pytest.raises(rc.ValidationError):
        transport({})
    with rc.make_fixture_server() as server:
        status, _headers, raw = _post(server, "/v1/chat/completions", "fx-stream")
        assert status == 200 and raw
    assert transport.calls == []


def test_request_and_adapter_wrappers_validate_inputs():
    with pytest.raises(rc.ValidationError):
        rc.AdapterRequest(model="")
    with pytest.raises(rc.ValidationError):
        rc.AdapterRequest(model="m", messages=[{"role": "user"}])  # type: ignore[arg-type]
    with pytest.raises(rc.ValidationError):
        rc.AdapterRequest(model="m", temperature=3.0)
    with pytest.raises(rc.ValidationError):
        rc.KeelAdapter("bad", object())
    with pytest.raises(rc.ValidationError):
        rc.CancellingAdapter(object(), 0)
    with pytest.raises(rc.ValidationError):
        rc.AdapterBinding("bad", "not-a-dialect", lambda _u, _t: None)  # type: ignore[arg-type]


# ===========================================================================
# X9.5 -- cross-platform path and permission matrix
# ===========================================================================


def test_path_matrix_all_independent_expectations_match():
    cases = rc.path_matrix()
    report = rc.run_path_matrix()
    assert len(cases) == 23
    assert report.ok, report.failures
    assert len(report.entries) == len(cases)
    assert report.fingerprint == rc.run_path_matrix().fingerprint


def test_windows_reserved_names_and_alternate_data_streams_are_blocked():
    for path in ("CON", "aux.txt", "dir\\COM1.log", "dir\\LPT9", "NUL"):
        verdict = rc.evaluate_path(PathCase(path, Platform.WINDOWS))
        assert not verdict.allowed, path
        assert PathHazard.RESERVED_DEVICE_NAME in verdict.hazards
    ads = rc.evaluate_path(PathCase("notes.txt:secret", Platform.WINDOWS))
    assert PathHazard.ALTERNATE_DATA_STREAM in ads.hazards
    # POSIX treats the same characters as ordinary filename bytes.
    assert rc.evaluate_path(PathCase("notes.txt:secret", Platform.POSIX)).ok


def test_long_paths_and_long_components_are_blocked():
    long_path = rc.evaluate_path(PathCase("\\".join(["folder"] * 40),
                                          Platform.WINDOWS))
    assert PathHazard.LONG_PATH in long_path.hazards
    long_component = rc.evaluate_path(PathCase("a" * 300, Platform.POSIX))
    assert PathHazard.LONG_COMPONENT in long_component.hazards
    assert not long_component.allowed


def test_case_insensitive_collisions_and_normalization_conflicts():
    collision = rc.evaluate_path(PathCase(
        "docs/README.md", Platform.WINDOWS, case_insensitive_fs=True,
        existing_paths=("docs/readme.MD",)))
    assert PathHazard.CASE_COLLISION in collision.hazards
    distinct = rc.evaluate_path(PathCase(
        "docs/README.md", Platform.POSIX, existing_paths=("docs/readme.MD",)))
    assert distinct.ok
    nfd = rc.evaluate_path(PathCase("docs/cafe\u0301.md", Platform.WINDOWS))
    assert PathHazard.NORMALIZATION_CONFLICT in nfd.hazards


def test_symlinks_and_junctions_cannot_escape_containment():
    link = rc.evaluate_path(PathCase(
        "sub/link.txt", Platform.POSIX, symlink_target="../../etc/passwd"))
    assert PathHazard.SYMLINK_ESCAPE in link.hazards
    safe_link = rc.evaluate_path(PathCase(
        "sub/link.txt", Platform.POSIX, symlink_target="sibling/ok.txt"))
    assert safe_link.ok
    junction = rc.evaluate_path(PathCase(
        "junction", Platform.WINDOWS, junction_target="C:\\other\\volume"))
    assert PathHazard.JUNCTION_ESCAPE in junction.hazards
    relative = rc.evaluate_path(PathCase(
        "junction", Platform.WINDOWS, junction_target="relative\\target"))
    assert PathHazard.JUNCTION_ESCAPE in relative.hazards
    contained = rc.evaluate_path(PathCase(
        "link.txt", Platform.WINDOWS,
        symlink_target="..\\workspace\\safe.txt"))
    assert contained.ok


def test_absolute_parent_and_control_paths_are_blocked_on_both_platforms():
    assert PathHazard.UNC in rc.evaluate_path(PathCase(
        "\\\\server\\share\\x", Platform.WINDOWS)).hazards
    assert PathHazard.DRIVE_QUALIFIED in rc.evaluate_path(PathCase(
        "C:\\evil.txt", Platform.WINDOWS)).hazards
    assert PathHazard.PARENT_TRAVERSAL in rc.evaluate_path(PathCase(
        "../evil", Platform.POSIX)).hazards
    assert PathHazard.NUL_OR_CONTROL in rc.evaluate_path(PathCase(
        "bad\x00name", Platform.POSIX)).hazards


def test_permission_matrix_all_independent_expectations_match():
    report = rc.run_permission_matrix()
    assert report.ok, report.failures
    assert len(report.entries) == 2 * 5 * 4 + 1
    assert report.fingerprint == rc.run_permission_matrix().fingerprint


def test_permissions_deny_by_default_and_never_escalate_a_hazard():
    safe = PathCase("reports/q3.md", Platform.WINDOWS)
    unsafe = PathCase("CON", Platform.WINDOWS)
    assert not rc.evaluate_permission(PermissionRequest(
        Principal.GUEST, Permission.READ, safe,
        approval_granted=True, elevated_token=True)).allowed
    assert not rc.evaluate_permission(PermissionRequest(
        Principal.SANDBOX, Permission.WRITE, safe,
        approval_granted=True)).allowed
    assert not rc.evaluate_permission(PermissionRequest(
        Principal.AGENT, Permission.WRITE, safe)).allowed
    assert rc.evaluate_permission(PermissionRequest(
        Principal.AGENT, Permission.WRITE, safe, approval_granted=True)).allowed
    assert not rc.evaluate_permission(PermissionRequest(
        Principal.USER, Permission.ADMIN, safe)).allowed
    assert rc.evaluate_permission(PermissionRequest(
        Principal.USER, Permission.ADMIN, safe, elevated_token=True)).allowed
    assert not rc.evaluate_permission(PermissionRequest(
        Principal.USER, Permission.READ, unsafe,
        approval_granted=True, elevated_token=True)).allowed
    with pytest.raises(rc.ValidationError):
        PermissionRequest("root", Permission.READ, safe)  # type: ignore[arg-type]
    with pytest.raises(rc.ValidationError):
        PermissionRequest(Principal.USER, "read", safe)  # type: ignore[arg-type]


def test_matrix_validation_and_wrong_expectations_fail_closed():
    with pytest.raises(rc.ValidationError):
        rc.run_path_matrix(())
    with pytest.raises(rc.ValidationError):
        rc.run_permission_matrix(())
    with pytest.raises(rc.ValidationError):
        PathCase("x", "dos")  # type: ignore[arg-type]
    with pytest.raises(rc.ValidationError):
        PathCase("x", Platform.WINDOWS, expected_hazards=("bad",))  # type: ignore[arg-type]
    wrong = rc.run_path_matrix((PathCase("CON", Platform.WINDOWS),))
    assert not wrong.ok and wrong.failures
    wrong_permission = rc.run_permission_matrix((PermissionRequest(
        Principal.GUEST, Permission.ADMIN, PathCase("safe.txt", Platform.POSIX)),))
    assert not wrong_permission.ok  # no expectation => fail closed


# ===========================================================================
# X9.7 -- migration matrix with data checksums
# ===========================================================================


def test_every_released_schema_version_upgrades_to_current():
    assert RELEASED_VERSIONS == tuple(range(1, 12))
    assert CURRENT_SCHEMA_VERSION == 11
    results = rc.MigrationMatrix().run_all()
    assert len(results) == len(RELEASED_VERSIONS)
    for result in results:
        assert result.ok, result.as_dict()
        assert result.to_version == CURRENT_SCHEMA_VERSION
        assert result.version_path[0] == result.from_version
        assert result.version_path[-1] == CURRENT_SCHEMA_VERSION
        assert result.payload_checksum_before == result.payload_checksum_after
    assert rc.MigrationMatrix().run_all() == results


def test_versions_have_the_shape_of_their_released_schema():
    v1 = rc.build_version_fixture(1)
    v11 = rc.build_version_fixture(11)
    assert "policies" not in v1 and "usage" not in v1
    assert v11["usage"] == []
    assert all("kind" in bot and "project_id" in bot for bot in v11["bots"])
    assert all("trusted" in p for p in v11["projects"])
    assert all("routine_id" in item for item in v11["library"])
    assert [t["position"] for t in sorted(
        v11["tasks"], key=lambda t: t["id"])] == [0, 1]


def test_checksums_are_canonical_strict_and_deterministic():
    assert rc.checksum_data({"a": 1, "b": 2}) == rc.checksum_data({"b": 2, "a": 1})
    # Unicode forms are distinct: canonical JSON does not normalize text.
    assert rc.checksum_data({"x": "caf\u00e9"}) != rc.checksum_data(
        {"x": "cafe\u0301"})
    assert rc.fingerprint([1, 2, 3]) == rc.fingerprint([1, 2, 3])
    with pytest.raises(ValueError):
        rc.canonical_bytes({"bad": float("nan")})
    with pytest.raises(rc.ValidationError):
        rc.checksum_data([1, 2])  # type: ignore[arg-type]


def test_migration_preserves_payload_but_changes_full_checksum():
    data = rc.build_version_fixture(4)
    before = rc.payload_view(data)
    result = rc.MigrationMatrix().upgrade(data, 4,
                                          expected_checksum=rc.checksum_data(data))
    after = rc.payload_view(rc.build_version_fixture(11))
    assert before == after
    assert result.checksum_before != result.checksum_after
    assert result.payload_checksum_before == result.payload_checksum_after
    assert result.obligations == ("verify_checksum_before_write",)


def test_unknown_version_and_downgrade_fail_closed():
    matrix = rc.MigrationMatrix()
    with pytest.raises(rc.ReliabilityError):
        matrix.path(CURRENT_SCHEMA_VERSION + 1)
    with pytest.raises(rc.ReliabilityError):
        matrix.upgrade(rc.build_version_fixture(1), 0)
    with pytest.raises(rc.ValidationError):
        matrix.path("11")  # type: ignore[arg-type]


def test_missing_step_cycle_and_backward_step_fail_closed():
    noop = lambda data: None
    with pytest.raises(rc.ReliabilityError):
        rc.MigrationMatrix(migrations={}, current=2, released=(1, 2)).path(1)
    cyclic = rc.MigrationMatrix(
        migrations={1: (2, noop), 2: (1, noop)}, current=3, released=(1, 3))
    with pytest.raises(rc.ReliabilityError):
        cyclic.path(1)
    overshoot = rc.MigrationMatrix(
        migrations={1: (4, noop)}, current=3, released=(1, 3))
    with pytest.raises(rc.ReliabilityError):
        overshoot.path(1)


def test_expected_checksum_mismatch_and_payload_loss_fail_closed():
    matrix = rc.MigrationMatrix()
    data = rc.build_version_fixture(6)
    with pytest.raises(rc.ReliabilityError, match="checksum mismatch"):
        matrix.upgrade(data, 6, expected_checksum="0" * 64)

    def destructive(payload: dict) -> None:
        payload["tasks"] = []

    bad_steps = dict(rc.MIGRATIONS)
    bad_steps[6] = (7, destructive)
    with pytest.raises(rc.ReliabilityError, match="lost or changed payload"):
        rc.MigrationMatrix(migrations=bad_steps).upgrade(
            rc.build_version_fixture(6), 6)


def test_upgrade_at_current_version_is_a_verified_no_op():
    data = rc.build_version_fixture(CURRENT_SCHEMA_VERSION)
    result = rc.MigrationMatrix().upgrade(data, CURRENT_SCHEMA_VERSION)
    assert result.version_path == (CURRENT_SCHEMA_VERSION,)
    assert result.checksum_before == result.checksum_after
    assert result.ok


def test_migration_matrix_validates_its_own_configuration():
    with pytest.raises(rc.ValidationError):
        rc.MigrationMatrix(migrations={1: (2, "not-callable")})  # type: ignore[dict-item]
    with pytest.raises(rc.ValidationError):
        rc.MigrationMatrix(released=(1, 1))
    with pytest.raises(rc.ValidationError):
        rc.MigrationMatrix(released=())
    with pytest.raises(rc.ReliabilityError):
        rc.MigrationMatrix(current=5, released=(1, 11)).run_all()

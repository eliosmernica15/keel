"""E5.x — desktop shell lifecycle, isolation and release/upload contracts.

Pure, adversarial coverage of the descriptors/policies in
`keel.desktop_contracts`. No network, subprocess or real credentials are used:
the credential reader is an injected callable that tests prove is never
invoked before validation succeeds.
"""

from __future__ import annotations

import hashlib

import pytest

from keel import desktop_contracts as dc

PUBLIC_URL = "https://releases.example.com/keel"
VERSION = "1.2.3"


def _artifact(name="keel-1.2.3-win-x64.exe", size=2048, sha512=None):
    return dc.Artifact(name, size, sha512 or "a" * 128)


def _record(**overrides):
    kwargs = dict(
        target="win-x64",
        environment="production",
        public_url=PUBLIC_URL,
        version=VERSION,
        channel="stable",
        artifacts=[_artifact()],
        steps=[{"name": "build", "ok": True}, {"name": "sign", "ok": True}],
    )
    kwargs.update(overrides)
    return dc.build_completion_record(**kwargs)


def _observed(record):
    return {a.name: (a.size, a.sha512) for a in record.artifacts}


def _authorized_call(record, reader, **overrides):
    kwargs = dict(
        environment=record.environment,
        target=record.target,
        public_url=record.public_url,
        version=record.version,
        observed_artifacts=_observed(record),
        credential_reader=reader,
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------
# E5.1 — framed-byte transport, no listening port
# --------------------------------------------------------------------------

def test_e5_1_transport_descriptor_has_no_listening_port():
    desc = dc.framed_transport_descriptor()
    assert desc["backend"] == "bundled_child"
    assert desc["transport"] == "framed_byte_pipe"
    assert desc["backpressure"] is True
    assert desc["ipc"] == "lifecycle_control_only"
    assert desc["assets"] == "app://"
    assert desc["listening_port"] is None
    assert desc["loopback_tcp"] is False
    assert desc["decision"] == "C-19"  # keel web/CLI keep loopback + token
    dc.assert_no_listening_port(desc)


def test_e5_1_adversarial_listening_port_and_loopback_rejected():
    desc = dc.framed_transport_descriptor()
    desc["listening_port"] = 8787
    with pytest.raises(dc.TransportError, match="listening port"):
        dc.assert_no_listening_port(desc)
    desc = dc.framed_transport_descriptor()
    desc["loopback_tcp"] = True
    with pytest.raises(dc.TransportError, match="loopback"):
        dc.assert_no_listening_port(desc)


def test_e5_1_frame_codec_roundtrip_and_backpressure_cap():
    payload = b'{"method":"chat","stream":true}'
    wire = dc.encode_frame(payload)
    frames, rest = dc.decode_frames(wire)
    assert frames == [payload] and rest == b""
    # An incomplete frame is buffered, never dispatched as a partial message.
    frames, rest = dc.decode_frames(wire[:-2])
    assert frames == [] and rest == wire[:-2]
    with pytest.raises(dc.TransportError, match="frame too large"):
        dc.encode_frame(b"x" * (dc.MAX_FRAME_BYTES + 1))


# --------------------------------------------------------------------------
# E5.4 — process-lifetime single-instance lock, two plugin environments
# --------------------------------------------------------------------------

def test_e5_4_lock_descriptor_and_data_separation():
    desc = dc.single_instance_lock_descriptor()
    assert desc["scope"] == "process_lifetime"
    assert desc["acquire_before"] == "profile_access"
    assert desc["profile_owner"] == "desktop_only"
    assert set(desc["shared_product_data"]) == {
        "sessions", "settings", "credentials", "workspaces"}
    assert set(desc["desktop_only_state"]) == {
        "executable_packages", "plugin_activation", "lockfiles", "site-packages"}
    assert tuple(desc["plugin_environments"]) == ("desktop", "cli")


def test_e5_4_lock_acquired_before_profile_access():
    guard = dc.SingleInstanceGuard()
    with pytest.raises(dc.ProfileAccessError, match="lock"):
        guard.access_profile("default")
    token = guard.acquire("default")
    assert token["profile"] == "default"
    assert token["process_lifetime"] is True
    assert guard.access_profile("default")["profile"] == "default"
    with pytest.raises(dc.ProfileAccessError, match="already held"):
        guard.acquire("other")  # second desktop instance must fail
    guard.release()
    with pytest.raises(dc.ProfileAccessError, match="lock"):
        guard.access_profile("default")


def test_e5_4_adversarial_wrong_profile_access_rejected():
    guard = dc.SingleInstanceGuard()
    guard.acquire("work")
    with pytest.raises(dc.ProfileAccessError, match="does not own"):
        guard.access_profile("personal")


# --------------------------------------------------------------------------
# E5.9 — install-time lifecycle scripts rejected unless allowlisted
# --------------------------------------------------------------------------

@pytest.mark.parametrize("hook", ["setup.py", "pre_install", "post_install", "build"])
def test_e5_9_lifecycle_scripts_rejected_by_default(hook):
    decision = dc.plugin_install_decision(
        "suspicious-pkg", "1.0", lifecycle_scripts=(hook,))
    assert decision["allowed"] is False
    assert decision["reason"] == "unallowlisted_lifecycle_script"


def test_e5_9_unknown_hook_and_sdist_are_rejected():
    assert dc.plugin_install_decision(
        "pkg", "1.0", lifecycle_scripts=("arbitrary_hook",))["allowed"] is False
    assert dc.plugin_install_decision(
        "src-pkg", "1.0", distribution_type="sdist")["allowed"] is False


def test_e5_9_wheel_without_scripts_allowed():
    decision = dc.plugin_install_decision("clean-wheel", "2.1")
    assert decision["allowed"] is True
    assert decision["reason"] == "wheel_without_scripts"


def test_e5_9_reviewed_allowlist_admits_exact_name_and_version():
    allow = frozenset({("vetted-pkg", "1.2")})
    assert dc.plugin_install_decision(
        "vetted-pkg", "1.2", distribution_type="sdist",
        allowlist=allow)["allowed"] is True
    assert dc.plugin_install_decision(
        "vetted-pkg", "1.2", lifecycle_scripts=("post_install",),
        allowlist=allow)["allowed"] is True


def test_e5_9_adversarial_allowlist_mismatch_rejected():
    allow = frozenset({("vetted-pkg", "1.2")})
    for kwargs in (
        dict(name="vetted-pkg", version="1.3", lifecycle_scripts=("post_install",)),
        dict(name="impostor", version="1.2", lifecycle_scripts=("post_install",)),
        dict(name="vetted-pkg", version="", lifecycle_scripts=("post_install",)),
    ):
        assert dc.plugin_install_decision(allowlist=allow, **kwargs)["allowed"] is False


# --------------------------------------------------------------------------
# E5.12 — per-target build isolation, shared cache verified by name+hash
# --------------------------------------------------------------------------

def test_e5_12_each_target_owns_its_layout():
    layout = dc.target_build_layout("win-x64")
    assert layout["root"] == "targets/win-x64"
    assert layout["inputs"] == "targets/win-x64/inputs"
    assert layout["runtime"] == "targets/win-x64/runtime"
    assert layout["seed"] == "targets/win-x64/seed"
    assert layout["artifacts"] == "targets/win-x64/artifacts"
    for path in layout.values():
        dc.assert_target_confined("win-x64", path)
    # Two targets never share a mutable directory.
    assert set(dc.target_build_layout("macos-arm64").values()).isdisjoint(
        set(layout.values()))


def test_e5_12_adversarial_cross_target_path_rejected():
    for path in ("targets/macos-arm64/runtime", "targets", "targets/win-x64/../macos-arm64/seed"):
        with pytest.raises(dc.TargetIsolationError):
            dc.assert_target_confined("win-x64", path)
    for target in ("../outside", "win-x64/nested", "", "C:\\absolute"):
        with pytest.raises(dc.TargetIsolationError):
            dc.target_build_layout(target)


def test_e5_12_shared_cache_verified_by_name_and_hash():
    digest = hashlib.sha256(b"prepared-runtime").hexdigest()
    entry = dc.shared_cache_entry("python-runtime", digest)
    assert entry["key"] == f"python-runtime-{digest}"
    assert dc.verify_shared_cache(
        entry, expected_name="python-runtime", expected_digest=digest) is True
    assert dc.verify_shared_cache(
        entry, expected_name="python-runtime", expected_digest="0" * 64) is False
    assert dc.verify_shared_cache(
        entry, expected_name="other-runtime", expected_digest=digest) is False
    with pytest.raises(dc.TargetIsolationError):
        dc.shared_cache_entry("../escape", digest)
    with pytest.raises(dc.TargetIsolationError):
        dc.shared_cache_entry("python-runtime", "not-a-sha256")


# --------------------------------------------------------------------------
# E5.14 — packaging stripped of upload credentials, completion record last
# --------------------------------------------------------------------------

def test_e5_14_strip_upload_credentials_proves_clean_env():
    env = {
        "PATH": "/usr/bin",
        "KEEL_BUILD_TARGET": "win-x64",
        "KEEL_UPLOAD_TOKEN": "s3cr3t-upload",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "GH_TOKEN": "ghp_xxx",
        "MACOS_NOTARIZATION_PASSWORD": "app-pass",
    }
    assert set(dc.find_upload_secrets(env)) == {
        "KEEL_UPLOAD_TOKEN", "AWS_SECRET_ACCESS_KEY", "GH_TOKEN",
        "MACOS_NOTARIZATION_PASSWORD"}
    with pytest.raises(dc.CredentialLeakError, match="KEEL_UPLOAD_TOKEN"):
        dc.assert_no_upload_secret(env)
    clean = dc.strip_upload_credentials(env)
    dc.assert_no_upload_secret(clean)  # proof: no upload secret survives
    assert clean["PATH"] == "/usr/bin"
    assert clean["KEEL_BUILD_TARGET"] == "win-x64"
    assert env["KEEL_UPLOAD_TOKEN"] == "s3cr3t-upload"  # original not mutated
    assert dc.packaging_env(env) == clean


def test_e5_14_adversarial_obfuscated_secret_names_detected():
    env = {
        "keel_release_token": "lowercase-token",
        "MY_API_KEY": "key",
        "CLIENT_SECRET": "secret",
        "AWS_SESSION_TOKEN": "session",
        "KEEL_PRIVATE_KEY": "private",
        "AWS_ACCESS_KEY_ID": "access-id",
    }
    with pytest.raises(dc.CredentialLeakError):
        dc.assert_no_upload_secret(env)
    dc.assert_no_upload_secret(dc.strip_upload_credentials(env))


def test_e5_14_completion_record_only_after_every_step_succeeds():
    record = _record()
    assert record.complete is True
    assert record.target == "win-x64"
    assert record.artifacts == (_artifact(),)
    with pytest.raises(dc.StepIncompleteError, match="sign"):
        _record(steps=[{"name": "build", "ok": True},
                       {"name": "sign", "ok": False}])
    with pytest.raises(dc.StepIncompleteError, match="no steps"):
        _record(steps=[])


# --------------------------------------------------------------------------
# E5.15 — upload guard: match record, verify artifacts before credentials
# --------------------------------------------------------------------------

def test_e5_15_guard_checks_then_orders_upload_plan():
    record = _record()
    read_calls = []

    def reader():
        read_calls.append("read")
        return "credential"

    plan = dc.authorize_upload(
        record, **_authorized_call(record, reader))
    assert read_calls == ["read"]  # credentials read exactly once, after checks
    kinds = [op["kind"] for op in plan.operations]
    assert kinds[0] == "put_artifact"
    assert kinds[-1] == "put_channel_metadata"
    assert plan.operations[-1]["cache_control"] == "no-cache"
    assert plan.operations[0]["cache_control"] == "immutable"
    assert plan.channel_metadata_name == "stable.json"
    assert plan.retains_history is True
    assert isinstance(plan.operations, tuple)
    dc.assert_no_deletes(plan)


@pytest.mark.parametrize("field,value", [
    ("environment", "staging"),
    ("target", "macos-arm64"),
    ("public_url", "https://evil.example.com/keel"),
    ("version", "9.9.9"),
])
def test_e5_15_adversarial_record_mismatch_blocks_before_credentials(field, value):
    record = _record()

    def reader():
        pytest.fail("credentials must not be read before validation")

    with pytest.raises(dc.UploadGuardError, match=field):
        dc.authorize_upload(
            record, **_authorized_call(record, reader, **{field: value}))


@pytest.mark.parametrize("mutate", ["name", "size", "sha512"])
def test_e5_15_adversarial_artifact_mismatch_blocks_before_credentials(mutate):
    record = _record()
    observed = _observed(record)
    artifact = record.artifacts[0]
    if mutate == "name":
        observed["renamed.exe"] = observed.pop(artifact.name)
    elif mutate == "size":
        observed[artifact.name] = (artifact.size + 1, artifact.sha512)
    else:
        observed[artifact.name] = (artifact.size, "b" * 128)

    def reader():
        pytest.fail("credentials must not be read before validation")

    with pytest.raises(dc.UploadGuardError, match=mutate):
        dc.authorize_upload(
            record, **_authorized_call(
                record, reader, observed_artifacts=observed))


def test_e5_15_stable_and_prerelease_channel_files():
    assert dc.channel_metadata_name("stable") == "stable.json"
    assert dc.channel_metadata_name("prerelease") == "prerelease.json"
    with pytest.raises(dc.UploadGuardError, match="channel"):
        dc.channel_metadata_name("nightly")
    record = _record(channel="prerelease")
    plan = dc.authorize_upload(
        record, **_authorized_call(record, lambda: "credential"))
    assert plan.channel_metadata_name == "prerelease.json"
    dc.assert_no_deletes(plan)


def test_e5_15_adversarial_completion_record_incomplete_blocks_upload():
    record = _record()
    incomplete = dc.CompletionRecord(
        environment=record.environment, target=record.target,
        public_url=record.public_url, version=record.version,
        channel=record.channel, artifacts=record.artifacts, complete=False)
    with pytest.raises(dc.UploadGuardError, match="completion"):
        dc.authorize_upload(
            incomplete, **_authorized_call(incomplete, lambda: pytest.fail("read")))

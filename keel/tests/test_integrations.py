"""External integrations with mock transports — no external environment needed."""

from __future__ import annotations

import pytest

from keel.integrations import (CIAdapter, MockTransport, RemoteTarget,
                               companion_pair_payload, image_gen_command)


def test_ci_adapter_with_mock():
    transport = MockTransport(ok=True, output="done")
    adapter = CIAdapter(transport=transport)
    result = adapter.run("say hi")
    assert result.ok is True and result.detail == "done"
    assert transport.calls[0][0] == "-p"
    assert adapter.command("x")[3] == "stream-json"


def test_remote_targets():
    ssh = RemoteTarget("ssh", "user@host")
    assert ssh.command("ls")[0] == "ssh"
    wsl = RemoteTarget("wsl", "Ubuntu")
    assert wsl.command("ls")[0] == "wsl"
    mock = MockTransport()
    result = ssh.test(lambda args: IntegrationResult(True, "ok", "mock"))
    assert result.ok is True
    with pytest.raises(ValueError):
        RemoteTarget("telnet", "x")


def test_image_and_companion():
    cmd = image_gen_command("a cat")
    assert cmd[0] == "comfyui" and "a cat" in cmd
    payload = companion_pair_payload("phone", "1234")
    assert payload["paired"] is True and "secret" not in payload


from keel.integrations import IntegrationResult  # noqa: E402

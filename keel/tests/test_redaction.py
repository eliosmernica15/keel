"""B3.5/B3.6/B3.8 — outbound redaction, output DLP, egress log."""

from __future__ import annotations

import pytest

from keel import redaction
from keel.fakes import SeededRng, VirtualClock
from keel.runner import RealTools
from keel.session import Session, SessionConfig


def test_redacts_known_credential_formats():
    text = ("key=sk-or-v1-abcdefghijklmnopqrstuvwx "
            "aws=AKIAIOSFODNN7EXAMPLE "
            "google=AIzaSyD-abcdefghijklmnopqrstuvwxyz123456")
    clean, counts = redaction.redact_text(text)
    assert "sk-or-v1-" not in clean
    assert "AKIA" not in clean
    assert "AIza" not in clean
    assert counts["openrouter_key"] == 1
    assert counts["aws_key"] == 1
    assert counts["google_key"] == 1


def test_ordinary_text_is_unchanged():
    text = "def greet(name): return f'hello {name}'  # sk-normal-variable"
    clean, counts = redaction.redact_text(text)
    assert clean == text
    assert counts == {}


def test_redact_messages_does_not_mutate_input():
    messages = [
        {"role": "user",
         "content": [{"type": "text", "text": "token sk-abcdefghijklmnopqrstuvwxyz"}]},
        {"role": "assistant", "content": "plain text"},
    ]
    clean, counts = redaction.redact_messages(messages)
    assert "sk-abcdefghijklmnopqrstuvwxyz" in messages[0]["content"][0]["text"]
    assert "[REDACTED]" in clean[0]["content"][0]["text"]
    assert counts["openai_key"] == 1
    assert clean[1]["content"] == "plain text"


def test_output_dlp_detects_secrets():
    assert redaction.check_output_dlp("ghp_abcdefghijklmnopqrstuvwxyz0123456789")
    assert redaction.check_output_dlp("just a normal sentence") == []


def test_output_dlp_and_redact_messages_catch_bearer_and_multiword_secrets():
    """Audit C4: unknown credential formats must not evade DLP or egress."""
    assert redaction.check_output_dlp("token=super secret value")
    assert redaction.check_output_dlp("Bearer abcdef1234567890")

    messages = [{"role": "user", "content": "Bearer plaintexttoken12345"},
                {"role": "assistant",
                 "content": [{"type": "text", "text": "token=super secret value"}]}]
    clean, counts = redaction.redact_messages(messages)
    assert "plaintexttoken12345" not in clean[0]["content"]
    assert "super secret value" not in clean[1]["content"][0]["text"]
    assert counts.get("bearer_token") and counts.get("inline_secret")
    assert messages[0]["content"] == "Bearer plaintexttoken12345"  # no mutation


def test_write_file_refuses_secret_content(tmp_path, monkeypatch):
    monkeypatch.delenv("KEEL_OUTPUT_DLP", raising=False)
    target = tmp_path / "out.txt"
    with pytest.raises(ValueError, match="output DLP"):
        RealTools().invoke("write_file", {
            "path": str(target),
            "content": "key sk-abcdefghijklmnopqrstuvwxyz",
        })
    assert not target.exists()


def test_dlp_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_OUTPUT_DLP", "0")
    target = tmp_path / "out.txt"
    RealTools().invoke("write_file", {
        "path": str(target), "content": "sk-abcdefghijklmnopqrstuvwxyz"})
    assert target.exists()


def test_egress_log_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_EGRESS_LOG", str(tmp_path / "egress.jsonl"))
    redaction.log_egress(str(tmp_path), provider="openrouter", model="m",
                         message_count=2, redactions={"openai_key": 1},
                         outbound_bytes=120)
    records = redaction.read_egress(str(tmp_path))
    assert len(records) == 1
    assert records[0]["redactions"] == {"openai_key": 1}
    assert records[0]["provider"] == "openrouter"


def _cfg(tmp_path):
    return SessionConfig(cwd=str(tmp_path),
                         state_root=str(tmp_path / "state"),
                         bare=True, permission_mode="default",
                         session_id="88888888-8888-4888-8888-888888888888",
                         model="boom-1", seed=0, redact_outbound=True,
                         egress_logging=True)


class _Executor:
    def invoke(self, name, tool_input):
        return "", {}


def test_session_redacts_outbound_and_logs_egress(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEL_EGRESS_LOG", str(tmp_path / "egress.jsonl"))
    seen = {}

    class CaptureModel:
        name = "openrouter"

        def complete(self, messages, tools):
            seen["messages"] = messages
            return [{"type": "text", "text": "done"}]

    session = Session(model_client=CaptureModel(), executor=_Executor(),
                      config=_cfg(tmp_path),
                      clock=VirtualClock(), rng=SeededRng(0))
    session.run("use key sk-abcdefghijklmnopqrstuvwxyz")
    rendered = str(seen["messages"])
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in rendered
    assert "[REDACTED]" in rendered
    records = redaction.read_egress(str(tmp_path))
    assert records and "openai_key" in records[0]["redactions"]

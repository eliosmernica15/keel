"""C2.1 — real Cowork email/calendar/meeting workflows."""

from __future__ import annotations

import wave

from keel.cowork_channels import (compose_email, parse_ics, send_email_draft,
                                  transcribe_if_available, write_wav)


def test_email_draft_is_real_rfc5322():
    draft = compose_email("a@test", "Hello", "Body text", cc="b@test")
    assert "To: a@test" in draft["draft"]
    assert "Subject: Hello" in draft["draft"]
    assert "Body text" in draft["draft"]
    assert send_email_draft(draft, host="x", user="u", password="p")["dry_run"] is True


def test_ics_parsing():
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Standup\n"
           "DTSTART:20260101T090000Z\nEND:VEVENT\nEND:VCALENDAR\n")
    events = parse_ics(ics)
    assert events[0]["SUMMARY"] == "Standup"
    assert events[0]["DTSTART"].startswith("20260101")


def test_wav_and_transcription(tmp_path):
    path = write_wav(tmp_path / "meeting.wav", b"\x00" * 3200, rate=16000)
    with wave.open(str(path)) as wav:
        assert wav.getframerate() == 16000
    assert transcribe_if_available(path)["engine"] == "user-installed"

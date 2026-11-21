"""Real Cowork channel workflows (C2.1 upgrade): local email drafts, ICS
calendars, meeting audio and transcription hooks. Uses only the standard
library; external accounts are never contacted without explicit opt-in.
"""

from __future__ import annotations

import imaplib
import json
import smtplib
import wave
from email.message import EmailMessage
from pathlib import Path


def compose_email(to: str, subject: str, body: str, *,
                  cc: str = "") -> dict:
    """Build a real RFC-5322 email message (draft only, never sent here)."""
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    message.set_content(body)
    return {"to": to, "subject": subject, "draft": message.as_string()}


def send_email_draft(draft: dict, *, host: str, user: str, password: str,
                     dry_run: bool = True) -> dict:
    """Send a draft via the user's own SMTP server; dry-run by default."""
    if dry_run:
        return {"sent": False, "dry_run": True, "bytes": len(draft["draft"])}
    from email.parser import Parser

    message = Parser().parsestr(draft["draft"])
    with smtplib.SMTP_SSL(host, 465, timeout=15) as server:
        server.login(user, password)
        server.send_message(message)
    return {"sent": True, "dry_run": False}


def parse_ics(text: str) -> list[dict]:
    """Parse VEVENT blocks from a local ICS calendar file."""
    events = []
    current = None
    for line in text.splitlines():
        if line.strip() == "BEGIN:VEVENT":
            current = {}
        elif line.strip() == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip()
    return events


def write_wav(path: str | Path, samples: bytes, *, rate: int = 16000,
              channels: int = 1, width: int = 2) -> Path:
    """Write a real PCM WAV file for a locally recorded meeting."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(samples)
    return target


def transcribe_if_available(path: str | Path, tool: str = "") -> dict:
    """Describe a local transcription job; requires a user-installed engine."""
    return {"file": str(path), "engine": tool or "user-installed",
            "note": "No audio is uploaded; engine must be local."}

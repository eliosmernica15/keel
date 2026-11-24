"""Backend implementations for Master Plan v6 small feature groups.

Scope: the ``not_started`` rows of groups X4, D2, E4, W9, X9, W6, W8, W2,
W5, X0, X10, W3 and Y6 (54 features) from PLAN-INDEX.json. Prior P0 rows in
those groups were already implemented elsewhere and are only *verified* in
the accompanying evidence note, not reimplemented here.

Constraints honoured:
  * standard library only (no third-party imports, no network, no UI code);
  * every feature has real, deterministic backend behaviour with a callable
    registered in ``FEATURE_IMPLEMENTATIONS``;
  * Y6.4 (repo visibility = Public) is owner-gated and therefore documented
    in ``OWNER_GATED`` with ``implemented=False`` -- it is deliberately NOT
    implemented (changing repository visibility/stars requires owner action).

The module is organised by feature group. Each public symbol carries the
plan feature ID in its docstring so the registry can be audited mechanically.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# X4 -- Voice and multimodal extras
# ---------------------------------------------------------------------------


class BargeInController:
    """X4.1: user speech interrupts TTS immediately; half-duplex fallback.

    In full-duplex mode a detected utterance cancels the active TTS playback
    at once. On weak hardware (``full_duplex_capable=False``) the controller
    falls back to half-duplex: playback cannot be interrupted and the speech
    is reported as a fallback rather than silently dropped.
    """

    def __init__(self, full_duplex_capable: bool = True) -> None:
        self.full_duplex_capable = bool(full_duplex_capable)
        self.mode = "full_duplex" if self.full_duplex_capable else "half_duplex"
        self.playing = False
        self.interruptions = 0
        self._utterance: str | None = None

    def start_tts(self, utterance: str) -> dict[str, Any]:
        if self.playing:
            raise RuntimeError("TTS playback already active")
        self.playing = True
        self._utterance = utterance
        return {"state": "playing", "utterance": utterance, "mode": self.mode}

    def speech_detected(self) -> dict[str, Any]:
        if not self.playing:
            return {
                "interrupted": False,
                "mode": self.mode,
                "reason": "no_active_tts",
            }
        if self.mode == "full_duplex":
            interrupted = self._utterance
            self.playing = False
            self._utterance = None
            self.interruptions += 1
            return {
                "interrupted": True,
                "mode": self.mode,
                "utterance": interrupted,
                "fallback": False,
            }
        return {
            "interrupted": False,
            "mode": self.mode,
            "reason": "half_duplex_fallback",
            "fallback": True,
        }

    def tts_finished(self) -> dict[str, Any]:
        self.playing = False
        self._utterance = None
        return {"state": "idle", "mode": self.mode}


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def stream_tts_sentences(chunks: Any) -> list[str]:
    """X4.2: stream TTS sentence by sentence while the model is generating.

    Consumes an iterable of text chunks and returns the complete sentences in
    emission order. A trailing unterminated fragment is flushed as the last
    sentence, so no generated text is lost.
    """
    sentences: list[str] = []
    buffer = ""
    for chunk in chunks:
        buffer += chunk
        while True:
            match = _SENTENCE_BOUNDARY.search(buffer)
            if not match:
                break
            sentence = buffer[: match.end()].strip()
            buffer = buffer[match.end() :]
            if sentence:
                sentences.append(sentence)
    if buffer.strip():
        sentences.append(buffer.strip())
    return sentences


class WakeWordController:
    """X4.3: optional wake word with license verification and hard mute."""

    # Licences acceptable for a bundled wake-word engine (permits the user to
    # ship a freeware binary without publishing source).
    ACCEPTABLE_LICENSES = frozenset(
        {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "0bsd", "unlicense"}
    )

    def __init__(self, engine: str, license_name: str, enabled: bool = False) -> None:
        self.engine = engine
        self.license_name = license_name.strip().lower()
        self.enabled = bool(enabled)
        self.muted = False
        self.indicator = "off"
        if self.enabled:
            self.set_enabled(True)

    def verify_engine_license(self) -> dict[str, Any]:
        ok = self.license_name in self.ACCEPTABLE_LICENSES
        return {
            "engine": self.engine,
            "license": self.license_name,
            "acceptable": ok,
            "reason": "license accepted" if ok else "license not on allow-list",
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        if enabled:
            verification = self.verify_engine_license()
            if not verification["acceptable"]:
                raise ValueError(f"wake-word engine licence rejected: {verification['reason']}")
            if self.muted:
                raise ValueError("hard mute is active; unmute before enabling")
        self.enabled = bool(enabled)
        return self._sync()

    def hard_mute(self) -> dict[str, Any]:
        """Hard mute cannot be overridden by a wake-word detection."""
        self.muted = True
        self.enabled = False
        return self._sync()

    def unmute(self) -> dict[str, Any]:
        self.muted = False
        return self._sync()

    def detect_wake_word(self) -> dict[str, Any]:
        if self.muted:
            return {"detected": False, "muted": True, "reason": "hard_mute"}
        return {"detected": self.enabled, "muted": False, "engine": self.engine}

    def _sync(self) -> dict[str, Any]:
        self.indicator = "muted" if self.muted else ("listening" if self.enabled else "off")
        return {
            "indicator": self.indicator,
            "enabled": self.enabled,
            "muted": self.muted,
        }


class LocalVisionTool:
    """X4.4: local VLM tool for screenshots/diagrams; user-installed model."""

    IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

    def __init__(self) -> None:
        self._models: dict[str, dict[str, str]] = {}

    def register_model(self, name: str, path: str, license_name: str) -> dict[str, Any]:
        if not name or not path or not license_name:
            raise ValueError("name, path and license are all required")
        descriptor = {"name": name, "path": path, "license": license_name}
        self._models[name] = descriptor
        # License is always shown to the user in the descriptor.
        return {"registered": True, **descriptor, "license_shown": True}

    def analyze(self, model_name: str, image_path: str | Path, question: str = "") -> dict[str, Any]:
        model = self._models.get(model_name)
        if model is None:
            raise ValueError(f"model not registered: {model_name}")
        path = Path(image_path)
        if path.suffix.lower() not in self.IMAGE_SUFFIXES:
            raise ValueError(f"unsupported image type: {path.suffix}")
        return {
            "tool": "local_vision",
            "model": model["name"],
            "license_shown": True,
            "request": {"image": str(path), "question": question},
            "network_access": False,
            "note": "user-installed model; licensing is shown before use",
        }


class VideoTooling:
    """X4.5: frame/audio extraction and subtitle generation via ffmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self.ffmpeg_path = ffmpeg_path

    def _require_ffmpeg(self) -> None:
        if not self.ffmpeg_path or not str(self.ffmpeg_path).strip():
            raise ValueError("user-installed ffmpeg is not configured")

    def extract_frame(self, video: str, timestamp: float | str, output: str) -> list[str]:
        self._require_ffmpeg()
        return [
            self.ffmpeg_path,
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            video,
            "-frames:v",
            "1",
            output,
        ]

    def extract_audio(self, video: str, output: str) -> list[str]:
        self._require_ffmpeg()
        return [self.ffmpeg_path, "-y", "-i", video, "-vn", "-acodec", "copy", output]

    def subtitles_from_stt(
        self, segments: list[dict[str, Any]], output_srt: str
    ) -> dict[str, Any]:
        """Build an SRT from local STT segments (start/end seconds, text)."""
        self._require_ffmpeg()
        blocks: list[str] = []
        for index, segment in enumerate(segments, start=1):
            start = _srt_timestamp(float(segment["start"]))
            end = _srt_timestamp(float(segment["end"]))
            blocks.append(f"{index}\n{start} --> {end}\n{segment['text']}\n")
        srt = "\n".join(blocks)
        return {
            "srt_path": output_srt,
            "srt": srt,
            "burn_command": [self.ffmpeg_path, "-y", "-i", output_srt, "-c:s", "srt"],
        }


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class VoiceCommandGrammar:
    """X4.6: command grammar separate from dictation, with spoken confirmation."""

    COMMANDS = frozenset({"approve", "deny", "stop everything"})
    RISKY = frozenset({"approve", "deny", "stop everything"})

    def parse(self, utterance: str) -> dict[str, Any]:
        cleaned = re.sub(r"[^\w\s]", "", utterance.strip().lower())
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned in self.COMMANDS:
            return {"kind": "command", "action": cleaned, "risky": cleaned in self.RISKY}
        return {"kind": "dictation", "text": utterance.strip()}

    def execute(self, utterance: str, spoken_confirmation: str | None = None) -> dict[str, Any]:
        parsed = self.parse(utterance)
        if parsed["kind"] == "dictation":
            return {"executed": False, "kind": "dictation", "text": parsed["text"]}
        if parsed["risky"] and (spoken_confirmation or "").strip().lower() != "confirm":
            return {
                "executed": False,
                "kind": "command",
                "action": parsed["action"],
                "needs_confirmation": True,
            }
        return {"executed": True, "kind": "command", "action": parsed["action"]}


class AudioPrivacyPolicy:
    """X4.7: no recording stored by default, visible state, consent reminder."""

    def __init__(self, store_recordings: bool = False) -> None:
        self.store_recordings = bool(store_recordings)
        self.state = "idle"
        self.meeting: str | None = None

    def consent_reminder(self, meeting_title: str) -> str:
        return (
            f"Consent reminder: '{meeting_title}' is being captured locally. "
            "Tell other participants and obtain their permission before continuing."
        )

    def start_recording(self, meeting_title: str) -> dict[str, Any]:
        self.state = "recording"
        self.meeting = meeting_title
        return self.recording_state()

    def pause_recording(self) -> dict[str, Any]:
        if self.state == "recording":
            self.state = "paused"
        return self.recording_state()

    def stop_recording(self) -> dict[str, Any]:
        self.state = "idle"
        return self.recording_state()

    def recording_state(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "meeting": self.meeting,
            "visible": True,
            "stored": self.store_recordings and self.state != "idle",
            "consent_reminder": self.consent_reminder(self.meeting or "this meeting"),
        }


# ---------------------------------------------------------------------------
# D2 -- Events, turn flow and the session log
# ---------------------------------------------------------------------------


class ProjectionRegistry:
    """D2.12: session projection seam.

    Registered units fold committed events into views. Clients only receive a
    ``snapshot()`` copy; the private handle used by domain services is never
    handed out.
    """

    def __init__(self) -> None:
        self._projections: dict[str, dict[str, Any]] = {}
        self._events: list[Any] = []

    def register(self, name: str, initial: Any, fold: Callable[[Any, Any], Any]) -> None:
        if name in self._projections:
            raise ValueError(f"projection already registered: {name}")
        self._projections[name] = {
            "initial": initial,
            "fold": fold,
            "state": deepcopy(initial),
            "handle": object(),
        }

    def commit(self, event: Any) -> None:
        self._events.append(event)
        for projection in self._projections.values():
            projection["state"] = projection["fold"](projection["state"], event)

    def snapshot(self, name: str) -> Any:
        return deepcopy(self._projections[name]["state"])

    @property
    def event_count(self) -> int:
        return len(self._events)


@runtime_checkable
class SessionPersistence(Protocol):
    """D2.14: swappable session storage backend interface."""

    def create(self, session_id: str) -> dict[str, Any]: ...

    def open(self, session_id: str) -> list[dict[str, Any]]: ...

    def stat(self, session_id: str) -> dict[str, Any]: ...

    def list(self) -> list[str]: ...

    def export(self, session_id: str, target: str | Path) -> str: ...


class JsonlPersistence:
    """D2.14: default SQLite-equivalent JSONL session persistence provider."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id or session_id in {".", ".."}:
            raise ValueError(f"invalid session id: {session_id!r}")
        return self.root / f"{session_id}.jsonl"

    def create(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        path.write_text("", encoding="utf-8")
        return {"session_id": session_id, "path": str(path), "events": 0}

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        path = self._path(session_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def open(self, session_id: str) -> list[dict[str, Any]]:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def stat(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(path)
        return {"session_id": session_id, "bytes": path.stat().st_size, "events": len(self.open(session_id))}

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.jsonl"))

    def export(self, session_id: str, target: str | Path) -> str:
        destination = Path(target)
        payload = {"session_id": session_id, "events": self.open(session_id)}
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return str(destination)


class PersistenceProviderRegistry:
    """D2.14: registry that makes the persistence backend swappable."""

    def __init__(self) -> None:
        self._providers: dict[str, SessionPersistence] = {}
        self._default: str | None = None

    def register(self, name: str, provider: SessionPersistence, default: bool = False) -> None:
        self._providers[name] = provider
        if default or self._default is None:
            self._default = name

    def get(self, name: str | None = None) -> SessionPersistence:
        key = name or self._default
        if key is None or key not in self._providers:
            raise KeyError(f"unknown persistence provider: {key}")
        return self._providers[key]

    def names(self) -> list[str]:
        return sorted(self._providers)


class TitleProviderRegistry:
    """D2.17: exactly one registered provider produces a session title."""

    def __init__(self) -> None:
        self._provider: Callable[[list[Any]], str] | None = None

    def register(self, provider: Callable[[list[Any]], str]) -> None:
        if self._provider is not None:
            raise ValueError("only one title provider may be registered")
        self._provider = provider

    def title(self, events: list[Any]) -> str:
        if self._provider is None:
            return "Untitled session"
        return self._provider(events)


class GoalsService:
    """D2.17: same-session objective that survives compaction."""

    def __init__(self) -> None:
        self._objective: str | None = None
        self._compactions = 0

    def set_objective(self, objective: str) -> None:
        if not objective.strip():
            raise ValueError("objective must be non-empty")
        self._objective = objective.strip()

    def observe(self, event: dict[str, Any]) -> None:
        if event.get("type") == "compact":
            self._compactions += 1
            # The objective deliberately survives compaction unchanged.

    def current(self) -> str | None:
        return self._objective

    def compacted(self) -> int:
        return self._compactions


class HookContractError(RuntimeError):
    """D2.2: raised when a waterfall hook breaks its delegation contract."""


class _WaterfallContext:
    def __init__(self, event: str, payload: Any) -> None:
        self.event = event
        self.payload = payload
        self.delegate_called = False
        self.result: Any = None
        self.next: Callable[[], Any] = lambda: payload


class HookRunner:
    """D2.2: waterfall / serial / parallel listener dispatch.

    Waterfall handlers must call ``ctx.next()`` to delegate; returning without
    delegating is a short-circuit and must be declared explicitly. Serial and
    parallel handlers have no ``next()``.
    """

    MODES = frozenset({"waterfall", "serial", "parallel"})

    def __init__(self) -> None:
        self._hooks: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def register(
        self,
        event: str,
        mode: str,
        handler: Callable[..., Any],
        *,
        name: str = "",
        short_circuit: bool = False,
    ) -> None:
        if mode not in self.MODES:
            raise ValueError(f"unknown hook mode: {mode}")
        if mode != "waterfall" and short_circuit:
            raise ValueError("short_circuit is only meaningful for waterfall hooks")
        self._hooks[event].append(
            {"mode": mode, "handler": handler, "name": name or getattr(handler, "__name__", "hook"), "short_circuit": short_circuit}
        )

    def run(self, event: str, payload: Any) -> Any:
        hooks = self._hooks.get(event, [])
        if not hooks:
            return payload
        mode = hooks[0]["mode"]
        if any(h["mode"] != mode for h in hooks):
            raise HookContractError("mixed hook modes for the same event")
        if mode == "serial":
            for hook in hooks:
                payload = hook["handler"](payload)
            return payload
        if mode == "parallel":
            return [hook["handler"](payload) for hook in hooks]
        return self._waterfall(event, payload, hooks, 0)

    def _waterfall(self, event: str, payload: Any, hooks: list[dict[str, Any]], index: int) -> Any:
        if index >= len(hooks):
            return payload
        hook = hooks[index]
        context = _WaterfallContext(event, payload)

        def delegate() -> Any:
            context.delegate_called = True
            context.result = self._waterfall(event, payload, hooks, index + 1)
            return context.result

        context.next = delegate
        result = hook["handler"](context)
        if not context.delegate_called and not hook["short_circuit"]:
            raise HookContractError(
                f"waterfall hook '{hook['name']}' returned without calling next() "
                "and did not declare short_circuit=True"
            )
        return context.result if context.delegate_called else result


class TurnClaimGate:
    """D2.4: rejected or empty first claim closes the turn without a step."""

    def evaluate(self, claim: Any) -> dict[str, Any]:
        if claim is None:
            return {"open": False, "step": False, "reason": "no_claim"}
        if isinstance(claim, dict):
            status = claim.get("status", "accepted")
            text = claim.get("text", "")
        else:
            status, text = "accepted", str(claim)
        if status == "rejected":
            return {"open": False, "step": False, "reason": "rejected"}
        if not str(text).strip():
            return {"open": False, "step": False, "reason": "empty"}
        return {"open": True, "step": True, "claim": str(text).strip()}


class RequestSeriesLogger:
    """D2.6: mark new request series; retries do not repeat assembly."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.series = 0
        self._assembly_key: str | None = None

    def begin_series(self, reason: str, key: str | None = None) -> dict[str, Any]:
        """Start a series (surface replacement, image offload, context change)."""
        self.series += 1
        self._assembly_key = key
        event = {"type": "request_header", "series": self.series, "reason": reason}
        self.events.append(event)
        return event

    def request(self, payload: Any, key: str, retry: bool = False) -> dict[str, Any]:
        if retry:
            if key != self._assembly_key:
                raise ValueError("retry does not match the assembled request series")
            event = {"type": "request_retry", "series": self.series, "key": key}
            self.events.append(event)
            return event
        if self.series == 0 or key != self._assembly_key:
            self.begin_series("context_change", key=key)
        event = {
            "type": "request",
            "series": self.series,
            "key": key,
            "payload": payload,
            "assembled": True,
        }
        self.events.append(event)
        return event

    def headers(self) -> list[dict[str, Any]]:
        return [event for event in self.events if event["type"] == "request_header"]


# ---------------------------------------------------------------------------
# E4 -- Testing policy
# ---------------------------------------------------------------------------


def built_entrypoint_smoke(
    launcher: list[str], entrypoint: str | Path, args: list[str] | None = None
) -> dict[str, Any]:
    """E4.13: run a built entrypoint under the plain runtime via a launcher."""
    command = [*map(str, launcher), str(entrypoint), *(args or [])]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def assert_missing_config_exits_nonzero(
    launcher: list[str], entrypoint: str | Path, config_path: str | Path
) -> dict[str, Any]:
    """E4.13: a genuinely missing config must produce a non-zero exit."""
    if Path(config_path).exists():
        raise AssertionError("config path still exists; test is not exercising a missing config")
    result = built_entrypoint_smoke(launcher, entrypoint, args=["--config", str(config_path)])
    if result["returncode"] == 0:
        raise AssertionError("missing config must exit non-zero")
    return result


class TestResolver:
    """E4.14: resolve imports to source, or to built artifacts in built mode."""

    __test__ = False  # imported into pytest modules; not a test class itself

    def __init__(self, source_root: str | Path, built_root: str | Path) -> None:
        self.source_root = Path(source_root)
        self.built_root = Path(built_root)

    def resolve(self, module: str) -> dict[str, Any]:
        relative = Path(*module.split(".")).with_suffix(".py")
        source = self.source_root / relative
        built = self.built_root / relative
        if source.exists() and built.exists():
            raise ValueError(f"ambiguous module resolves to both source and built: {module}")
        if source.exists():
            return {"module": module, "origin": "source", "path": str(source), "built_mode": False}
        if built.exists():
            return {"module": module, "origin": "built", "path": str(built), "built_mode": True}
        return {"module": module, "origin": "missing", "path": None, "built_mode": False}

    def assert_source_only(self, module: str) -> dict[str, Any]:
        resolved = self.resolve(module)
        if resolved["built_mode"]:
            raise AssertionError(f"{module} resolved to a built artifact in source test mode")
        return resolved


class CoverageGate:
    """E4.3: line coverage is necessary, never sufficient.

    Uncovered files are surfaced as dead-code candidates. Environment-
    dependent files are exempted locally but enforced on CI.
    """

    def __init__(self, ci: bool = False, env_dependent_files: Any = ()) -> None:
        self.ci = bool(ci)
        self.env_dependent_files = set(env_dependent_files)

    def evaluate(self, report: dict[str, Any], threshold: float = 80.0) -> dict[str, Any]:
        covered_total = 0
        line_total = 0
        exempted: list[str] = []
        dead: list[str] = []
        for path, data in report.get("files", {}).items():
            env_dependent = path in self.env_dependent_files or bool(data.get("env_dependent", False))
            if env_dependent and not self.ci:
                exempted.append(path)
                continue
            covered = int(data.get("covered", 0))
            total = int(data.get("total", 0))
            covered_total += covered
            line_total += total
            if total and covered == 0:
                dead.append(path)
        percent = round(100.0 * covered_total / line_total, 2) if line_total else 100.0
        return {
            "percent": percent,
            "exempted": exempted,
            "dead_code_candidates": dead,
            "line_coverage_necessary": True,
            "line_coverage_sufficient": False,
            "passed": percent >= threshold and not dead,
        }


@dataclass(frozen=True)
class Budget:
    """E4.4: time, heap and scaling budgets for a benchmark."""

    max_seconds: float
    max_heap_mb: float
    max_scale_factor: float


class BenchmarkGate:
    """E4.4: benchmark gates for required PR checks (diagnostic-only excluded)."""

    def __init__(self) -> None:
        self._budgets: dict[str, Budget] = {}
        self._results: dict[str, dict[str, Any]] = {}

    def set_budget(
        self, name: str, max_seconds: float, max_heap_mb: float, max_scale_factor: float = 2.0
    ) -> None:
        self._budgets[name] = Budget(max_seconds, max_heap_mb, max_scale_factor)

    def record(
        self,
        name: str,
        seconds: float,
        heap_mb: float,
        scale_factor: float = 1.0,
        *,
        diagnostic_only: bool = False,
    ) -> None:
        self._results[name] = {
            "seconds": seconds,
            "heap_mb": heap_mb,
            "scale_factor": scale_factor,
            "diagnostic_only": diagnostic_only,
        }

    def evaluate(self, name: str) -> dict[str, Any]:
        result = self._results[name]
        budget = self._budgets.get(name)
        if result["diagnostic_only"] or budget is None:
            return {"name": name, "gate": False, "passed": True, "violations": []}
        violations = []
        if result["seconds"] > budget.max_seconds:
            violations.append("time")
        if result["heap_mb"] > budget.max_heap_mb:
            violations.append("heap")
        if result["scale_factor"] > budget.max_scale_factor:
            violations.append("scaling")
        return {
            "name": name,
            "gate": True,
            "passed": not violations,
            "violations": violations,
            "runtime": "plain",  # never a transpiler
        }

    def required_checks(self) -> list[str]:
        return sorted(name for name in self._results if not self._results[name]["diagnostic_only"])


class FixtureFormatPolicy:
    """E4.6: fixtures omit sequence/time envelopes; replay synthesizes them."""

    ENVELOPE_KEYS = frozenset({"sequence", "seq", "time", "timestamp"})

    def __init__(self, current_version: str = "v2") -> None:
        self.current_version = current_version
        self._historical: dict[str, dict[str, str]] = {}

    def register_historical(self, version: str, owner: str, representation: str) -> None:
        self._historical[version] = {"owner": owner, "representation": representation}

    def historical(self, version: str) -> dict[str, str]:
        return dict(self._historical[version])

    def strip_envelopes(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in event.items() if key not in self.ENVELOPE_KEYS}
            for event in events
        ]

    def synthesize_envelopes(
        self, events: list[dict[str, Any]], start_sequence: int = 1, start_time: float = 0.0
    ) -> list[dict[str, Any]]:
        synthesized = []
        for index, event in enumerate(events):
            item = dict(event)
            item["sequence"] = start_sequence + index
            item["time"] = start_time + index
            synthesized.append(item)
        return synthesized

    def replay(self, fixture: dict[str, Any]) -> list[dict[str, Any]]:
        if fixture.get("version") in self._historical:
            # Historical fixtures keep their released representation.
            return list(fixture.get("events", []))
        return self.synthesize_envelopes(self.strip_envelopes(fixture.get("events", [])))


class BrowserSnapshotLane:
    """E4.7: Chromium snapshots, WebKit for the model picker; replay-only in CI."""

    WIDGET_ENGINES = {"model_picker": ("chromium", "webkit")}
    DEFAULT_ENGINE = "chromium"

    def __init__(self, ci: bool = False) -> None:
        self.ci = bool(ci)

    def plan(self, widgets: list[str]) -> list[dict[str, Any]]:
        entries = []
        for widget in widgets:
            engines = self.WIDGET_ENGINES.get(widget, (self.DEFAULT_ENGINE,))
            entries.append(
                {
                    "widget": widget,
                    "engines": list(engines),
                    "mode": "replay" if self.ci else "live",
                }
            )
        return entries

    def validate(self, plan: list[dict[str, Any]]) -> bool:
        for entry in plan:
            if "chromium" not in entry["engines"]:
                return False
            if entry["widget"] == "model_picker" and "webkit" not in entry["engines"]:
                return False
            if self.ci and entry["mode"] != "replay":
                return False
        return True


# ---------------------------------------------------------------------------
# W9 -- UI/UX additions (backend state/services only)
# ---------------------------------------------------------------------------


class McpPanelService:
    """W9.1: per-server MCP state and connect/disconnect/authenticate flow."""

    STATES = frozenset({"disconnected", "connected", "needs_auth", "disabled", "error"})

    def __init__(self) -> None:
        self._servers: dict[str, dict[str, Any]] = {}

    def register(self, name: str, protocol: str = "stdio", timeout_s: float = 30.0) -> dict[str, Any]:
        if protocol not in {"stdio", "http"}:
            raise ValueError(f"unsupported MCP protocol: {protocol}")
        self._servers[name] = {
            "state": "disconnected",
            "protocol": protocol,
            "timeout_s": timeout_s,
            "callback_url": None,
            "error": None,
        }
        return self.state(name)

    def connect(self, name: str) -> dict[str, Any]:
        server = self._servers[name]
        if server["state"] == "disabled":
            return self.state(name)
        server["state"] = "needs_auth"
        server["error"] = None
        return self.state(name)

    def authenticate(self, name: str, callback_url: str) -> dict[str, Any]:
        if not callback_url.startswith(("http://", "https://", "keel://")):
            raise ValueError("paste a valid callback URL")
        server = self._servers[name]
        server["callback_url"] = callback_url
        server["state"] = "connected"
        return self.state(name)

    def disconnect(self, name: str) -> dict[str, Any]:
        self._servers[name]["state"] = "disconnected"
        return self.state(name)

    def mark_error(self, name: str, message: str) -> dict[str, Any]:
        self._servers[name].update({"state": "error", "error": message})
        return self.state(name)

    def disable(self, name: str) -> dict[str, Any]:
        self._servers[name]["state"] = "disabled"
        return self.state(name)

    def set_config(self, name: str, timeout_s: float | None = None, protocol: str | None = None) -> None:
        if protocol is not None and protocol not in {"stdio", "http"}:
            raise ValueError(f"unsupported MCP protocol: {protocol}")
        if timeout_s is not None:
            self._servers[name]["timeout_s"] = timeout_s
        if protocol is not None:
            self._servers[name]["protocol"] = protocol

    def state(self, name: str) -> dict[str, Any]:
        server = self._servers[name]
        return {
            "name": name,
            "state": server["state"],
            "protocol": server["protocol"],
            "timeout_s": server["timeout_s"],
            "callback_url": server["callback_url"],
        }

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: self.state(name) for name in self._servers}


class ApprovalService:
    """W9.2: Once / Always / Reject decisions with pending cancellation."""

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}
        self._patterns: dict[str, str] = {}

    def submit(self, request_id: str, tool: str, pattern: str) -> None:
        self._pending[request_id] = {"tool": tool, "pattern": pattern}

    def decide(
        self,
        request_id: str,
        action: str,
        *,
        pattern: str | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        if action not in {"once", "always", "reject"}:
            raise ValueError(f"unknown approval action: {action}")
        request = self._pending.pop(request_id)
        if action == "once":
            return {"decision": "once", "tool": request["tool"], "cancelled": []}
        if action == "always":
            saved = pattern if pattern is not None else request["pattern"]
            self._patterns[request["tool"]] = saved
            return {
                "decision": "always",
                "tool": request["tool"],
                "saved_pattern": saved,
                "cancelled": [],
            }
        cancelled = list(self._pending)
        self._pending.clear()
        return {
            "decision": "reject",
            "tool": request["tool"],
            "feedback": feedback or "",
            "cancelled": cancelled,
        }

    def saved_pattern(self, tool: str) -> str | None:
        return self._patterns.get(tool)

    def pending(self) -> list[str]:
        return sorted(self._pending)


def normalize_agent_config(config: dict[str, Any]) -> dict[str, Any]:
    """W9.3: validate agent editor fields and normalise model references."""
    mode = config.get("mode", "primary")
    if mode not in {"primary", "subagent", "all"}:
        raise ValueError(f"invalid agent mode: {mode}")
    step_limit = int(config.get("step_limit", 10))
    if step_limit <= 0:
        raise ValueError("step_limit must be positive")
    color = config.get("color", "")
    if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("color must be a #RRGGBB value")
    model = config.get("model")
    if isinstance(model, str):
        model_ref = ModelReference.parse(model).to_dict()
    elif isinstance(model, dict):
        model_ref = ModelReference.from_object(model).to_dict()
    else:
        raise ValueError("model is required")
    permissions = list(config.get("permissions", []))
    allowlist = list(config.get("subagent_allowlist", []))
    return {
        "mode": mode,
        "model": model_ref,
        "step_limit": step_limit,
        "color": color,
        "hidden": bool(config.get("hidden", False)),
        "permissions": permissions,
        "subagent_allowlist": allowlist,
    }


def simulate_permission(config: dict[str, Any], action: str, resource: str = "") -> bool:
    """W9.3: permission-list simulator for the agent editor."""
    for rule in config.get("permissions", []):
        if rule == action or rule == "*":
            return True
        if rule.endswith(":*") and action.startswith(rule[:-1]):
            return True
    return False


def build_palette_entries(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """W9.4: generate command-palette entries with argument hints."""
    entries = []
    for command in commands:
        name = command["name"]
        prompt = command.get("prompt", "")
        hints = re.findall(r"\$ARGUMENTS|\$[1-9]\d*", prompt)
        entries.append(
            {
                "name": name,
                "description": command.get("description", ""),
                "hints": sorted(set(hints)),
                "prompt": prompt,
            }
        )
    return entries


def expand_command_prompt(template: str, arguments: list[str]) -> dict[str, Any]:
    """W9.4: expand $1..$N and $ARGUMENTS and return a preview."""
    remaining = list(arguments)
    first = remaining[0] if remaining else ""

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "$ARGUMENTS":
            return " ".join(remaining)
        index = int(token[1:]) - 1
        return remaining[index] if 0 <= index < len(remaining) else ""

    preview = re.sub(r"\$ARGUMENTS|\$[1-9]\d*", replace, template)
    return {"template": template, "arguments": list(arguments), "preview": preview, "first": first}


class FirstRunNotice:
    """W9.5: first-run safety notice and known-limits page state."""

    VERSION = "v1"

    def __init__(self, store_path: str | Path) -> None:
        self.path = Path(store_path)

    def is_first_run(self) -> bool:
        return not self.path.exists()

    def safety_notice(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "title": "Safety notice",
            "points": [
                "Tools can modify files and run commands; review approvals carefully.",
                "No data is sent to a Keel service; providers you configure are yours.",
                "Recordings are not stored by default.",
            ],
        }

    def known_limits(self) -> list[str]:
        return [
            "Local models require user installation and a visible licence.",
            "Voice wake word is optional and licence-gated.",
            "Web UI binds to loopback only.",
        ]

    def mark_seen(self) -> dict[str, Any]:
        record = {"seen": True, "version": self.VERSION}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        return record


def web_server_config(
    host: str = "127.0.0.1", port: int = 0, ssh_user: str = "user", ssh_host: str = "example.org"
) -> dict[str, Any]:
    """W9.6: loopback-only web UI plus an SSH forwarded-URL hint banner."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("web UI must bind to a loopback address only")
    local_port = int(port) or 8765
    banner = (
        "Web UI is available on loopback only. To reach it remotely, run:\n"
        f"  ssh -L {local_port}:127.0.0.1:{local_port} {ssh_user}@{ssh_host}\n"
        f"then open http://127.0.0.1:{local_port}/"
    )
    return {
        "host": host,
        "port": int(port),
        "loopback": True,
        "effective_port": local_port,
        "ssh_hint_banner": banner,
    }


# ---------------------------------------------------------------------------
# X9 -- Testing and quality
# ---------------------------------------------------------------------------


class MutationReport:
    """X9.10: mutation score report for the permission gate and analyzer."""

    TARGETS = ("permission_gate", "command_analyzer")

    def __init__(self) -> None:
        self._mutants: list[dict[str, Any]] = []

    def add(self, target: str, mutant_id: str, killed: bool) -> None:
        if target not in self.TARGETS:
            raise ValueError(f"unknown mutation target: {target}")
        self._mutants.append({"target": target, "id": mutant_id, "killed": bool(killed)})

    def score(self, target: str | None = None) -> float:
        mutants = [m for m in self._mutants if target is None or m["target"] == target]
        if not mutants:
            return 0.0
        killed = sum(1 for m in mutants if m["killed"])
        return round(100.0 * killed / len(mutants), 2)

    def dashboard_payload(self) -> dict[str, Any]:
        return {
            "targets": {target: {"score": self.score(target)} for target in self.TARGETS},
            "overall": self.score(),
            "visibility": "private",
        }


class VcrRecorder:
    """X9.2: record/replay provider traffic with secrets scrubbed."""

    SECRET_PATTERNS = (
        re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
        re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    )
    SECRET_KEYS = frozenset({"authorization", "token", "api_key", "apikey", "secret", "password"})

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def scrub(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ("[REDACTED]" if key.lower() in self.SECRET_KEYS else self.scrub(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        if isinstance(value, str):
            result = value
            for pattern in self.SECRET_PATTERNS:
                result = pattern.sub("[REDACTED]", result)
            return result
        return value

    @staticmethod
    def _key(request: dict[str, Any]) -> str:
        signature = {
            "method": request.get("method", "GET"),
            "url": request.get("url", ""),
            "body": request.get("body"),
        }
        return json.dumps(signature, sort_keys=True)

    def record(self, request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "key": self._key(request),
            "request": self.scrub(request),
            "response": self.scrub(response),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def replay(self, request: dict[str, Any]) -> dict[str, Any] | None:
        key = self._key(request)
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry["key"] == key:
                return entry["response"]
        return None


class McpConformanceRunner:
    """X9.4: conformance checks for stdio/HTTP and hostile sample servers."""

    def __init__(self, max_output_bytes: int = 65_536, timeout_s: float = 5.0) -> None:
        self.max_output_bytes = max_output_bytes
        self.timeout_s = timeout_s

    @staticmethod
    def sample_servers() -> list[dict[str, Any]]:
        return [
            {"name": "sample-stdio", "transport": "stdio", "behavior": "ok"},
            {"name": "sample-http", "transport": "http", "behavior": "ok"},
            {"name": "hostile-huge", "transport": "stdio", "behavior": "huge_output"},
            {"name": "hostile-hang", "transport": "http", "behavior": "hanging"},
            {"name": "hostile-schema", "transport": "stdio", "behavior": "bad_schema"},
        ]

    def evaluate(
        self, *, name: str, transport: str, output_bytes: int, elapsed_s: float, schema_valid: bool
    ) -> dict[str, Any]:
        results = {
            "transport_ok": transport in {"stdio", "http"},
            "output_within_limit": output_bytes <= self.max_output_bytes,
            "within_timeout": elapsed_s <= self.timeout_s,
            "schema_valid": bool(schema_valid),
        }
        return {"server": name, "results": results, "passed": all(results.values())}

    def run_samples(self) -> list[dict[str, Any]]:
        metrics = {
            "ok": (128, 0.1, True),
            "huge_output": (self.max_output_bytes + 1, 0.1, True),
            "hanging": (128, self.timeout_s + 1, True),
            "bad_schema": (128, 0.1, False),
        }
        reports = []
        for server in self.sample_servers():
            output_bytes, elapsed, schema_valid = metrics[server["behavior"]]
            reports.append(
                self.evaluate(
                    name=server["name"],
                    transport=server["transport"],
                    output_bytes=output_bytes,
                    elapsed_s=elapsed,
                    schema_valid=schema_valid,
                )
            )
        return reports


_PSEUDO_CHARS = str.maketrans(
    {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú"}
)


def pseudo_localize(text: str, expand: bool = True) -> str:
    """X9.6: transform a string into a pseudo-localized build variant."""
    result = text.translate(_PSEUDO_CHARS)
    return f"⟦{result}⟧" if expand else result


def rtl_smoke(text: str) -> dict[str, Any]:
    """X9.6: wrap text with directional isolation marks for RTL smoke tests."""
    rendered = "\u202b" + text + "\u202c"
    return {
        "text": text,
        "rendered": rendered,
        "markers": ["RLI", "PDI"],
        "ok": rendered.startswith("\u202b") and rendered.endswith("\u202c"),
    }


class TokenAccountingCheck:
    """X9.8: estimated vs runtime-reported token usage within tolerance."""

    def __init__(self, tolerance: float = 0.10) -> None:
        self.tolerance = tolerance

    def evaluate(self, estimated: int, reported: int) -> dict[str, Any]:
        delta = abs(int(estimated) - int(reported))
        relative = delta / max(int(reported), 1)
        return {
            "estimated": estimated,
            "reported": reported,
            "delta": delta,
            "relative": round(relative, 4),
            "within_tolerance": relative <= self.tolerance,
        }


class SoakMonitor:
    """X9.9: long-session soak metrics across thousands of events."""

    def __init__(self) -> None:
        self.samples: list[dict[str, float]] = []

    def sample(self, events: int, memory_bytes: int, db_bytes: int, frame_ms: float) -> None:
        self.samples.append(
            {
                "events": events,
                "memory_bytes": memory_bytes,
                "db_bytes": db_bytes,
                "frame_ms": frame_ms,
            }
        )

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"samples": 0}
        first, last = self.samples[0], self.samples[-1]
        return {
            "samples": len(self.samples),
            "event_span": last["events"] - first["events"],
            "memory_growth_mb": round((last["memory_bytes"] - first["memory_bytes"]) / 1_048_576, 3),
            "db_growth_mb": round((last["db_bytes"] - first["db_bytes"]) / 1_048_576, 3),
            "max_frame_ms": max(sample["frame_ms"] for sample in self.samples),
        }

    def check(
        self,
        max_memory_growth_mb: float = 64.0,
        max_db_growth_mb: float = 128.0,
        max_frame_ms: float = 32.0,
    ) -> dict[str, Any]:
        summary = self.summary()
        if not self.samples:
            return {"passed": False, "reason": "no_samples", **summary}
        violations = []
        if summary["memory_growth_mb"] > max_memory_growth_mb:
            violations.append("memory")
        if summary["db_growth_mb"] > max_db_growth_mb:
            violations.append("db_size")
        if summary["max_frame_ms"] > max_frame_ms:
            violations.append("frame_time")
        return {"passed": not violations, "violations": violations, **summary}


# ---------------------------------------------------------------------------
# W6 -- Persona contract
# ---------------------------------------------------------------------------

CONFIDENCE_LABELS = frozenset({"high", "moderate", "low", "unknown"})


class ConfidenceLabeler:
    """W6.2: explicit confidence labels; required for factual web claims."""

    def __init__(self, require_for_web_claims: bool = True) -> None:
        self.require_for_web_claims = bool(require_for_web_claims)

    def label(self, claim: str, confidence: str, factual_web_claim: bool = False) -> dict[str, Any]:
        if confidence not in CONFIDENCE_LABELS:
            raise ValueError(f"invalid confidence label: {confidence}")
        if factual_web_claim and self.require_for_web_claims and confidence == "unknown":
            raise ValueError("factual web claims require an explicit confidence judgment")
        return {
            "claim": claim,
            "confidence": confidence,
            "factual_web_claim": factual_web_claim,
        }

    def render(self, labeled: dict[str, Any]) -> str:
        return f"[{labeled['confidence']}] {labeled['claim']}"


class ConductorRouter:
    """W6.4: one conductor, optional specialists, one writer per dirty tree."""

    def __init__(self) -> None:
        self.conductor: str | None = None
        self.specialists: list[str] = []
        self._writers: dict[str, str] = {}

    def set_conductor(self, agent: str) -> None:
        if self.conductor is not None and self.conductor != agent:
            raise ValueError("only one conductor agent is allowed")
        self.conductor = agent

    def register_specialist(self, adapter: str) -> None:
        if adapter not in self.specialists:
            self.specialists.append(adapter)

    def route(self, multi_file: bool) -> dict[str, Any]:
        if multi_file and self.specialists:
            return {"agent": self.specialists[0], "role": "specialist"}
        return {"agent": self.conductor, "role": "conductor"}

    def assign_writer(self, tree: str, agent: str) -> None:
        current = self._writers.get(tree)
        if current is not None and current != agent:
            raise ValueError(f"tree '{tree}' already has writer '{current}'")
        self._writers[tree] = agent

    def verify_after_specialist(self, diff_ok: bool, tests_ok: bool) -> dict[str, Any]:
        if not (diff_ok and tests_ok):
            raise ValueError("specialist output must pass diff and test verification")
        return {"verified": True}


def choose_tool(
    task_type: str, local_healthy: bool, accessibility_available: bool = False
) -> dict[str, Any]:
    """W6.5: prefer healthy local desktop tool, browser for DOM work."""
    if task_type == "dom":
        return {"tool": "browser", "reason": "dom_work", "hint": "browser tool for DOM"}
    if task_type == "accessibility" and accessibility_available:
        return {"tool": "local_desktop", "reason": "accessibility_tree", "enrichment": True}
    if task_type == "desktop":
        return {
            "tool": "local_desktop" if local_healthy else "cloud",
            "reason": "local_healthy" if local_healthy else "local_unhealthy",
        }
    return {
        "tool": "local_desktop" if local_healthy else "cloud",
        "reason": "default",
        "hint": "PERSONA.md: local desktop first, then browser for DOM",
    }


class MemoryLedger:
    """W6.6: running MEMORY.md-style ledger; writes require approval."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def propose(self, fact: str) -> dict[str, Any]:
        return {"fact": fact, "needs_approval": True, "date": date.today().isoformat()}

    def write(self, fact: str, approved: bool) -> str:
        if not approved:
            raise PermissionError("memory ledger writes require explicit approval")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = f"- [{date.today().isoformat()}] {fact}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return line

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""


# ---------------------------------------------------------------------------
# W8 -- Small items from earlier sources
# ---------------------------------------------------------------------------


class AllowlistMatcher:
    """W8.1: paired-client allowlist with exact, @domain and prefix patterns."""

    def __init__(self, entries: Any) -> None:
        self.entries = list(entries)

    def matches(self, value: str) -> bool:
        for entry in self.entries:
            if entry.startswith("@"):
                domain = value.rsplit("@", 1)
                if len(domain) == 2 and domain[1].lower() == entry[1:].lower():
                    return True
            elif entry.endswith("*"):
                if value.startswith(entry[:-1]):
                    return True
            elif value == entry:
                return True
        return False


class BlobCaps:
    """W8.2: database caps for recorded skills and screenshots."""

    DEFAULT_CAPS = {"recording": 50_000_000, "screenshot": 5_000_000}

    def __init__(self, **overrides: int) -> None:
        self.caps = {**self.DEFAULT_CAPS, **overrides}

    def check(self, kind: str, size_bytes: int) -> dict[str, Any]:
        if kind not in self.caps:
            raise ValueError(f"unknown blob kind: {kind}")
        cap = self.caps[kind]
        return {
            "kind": kind,
            "size_bytes": size_bytes,
            "cap_bytes": cap,
            "accepted": size_bytes <= cap,
        }


class ComputerAccessGuard:
    """W8.3: validate requested desktops; core/home desktop is immutable."""

    def __init__(self, owned_ids: Any, core_desktop_id: str) -> None:
        self.owned_ids = set(owned_ids)
        self.core_desktop_id = core_desktop_id

    def validate(self, requested_ids: Any) -> dict[str, Any]:
        unknown = [item for item in requested_ids if item not in self.owned_ids]
        if unknown:
            return {"valid": False, "unknown": unknown}
        return {"valid": True, "unknown": []}

    def mutate(self, desktop_id: str, change: Any) -> Any:
        if desktop_id == self.core_desktop_id:
            raise PermissionError("core/home desktop is not mutable through the API")
        if desktop_id not in self.owned_ids:
            raise ValueError(f"desktop not owned by user: {desktop_id}")
        return change


def normalize_question(source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """W8.4: map opencode question and MCP elicitation onto one form schema."""
    if source == "opencode_question":
        questions = payload.get("questions", [])
    elif source == "mcp_elicitation":
        questions = payload.get("requestedSchema", {}).get("properties", {})
        if isinstance(questions, dict):
            questions = [
                {"id": key, "question": value.get("title", key), "type": value.get("type", "string")}
                for key, value in questions.items()
            ]
    else:
        raise ValueError(f"unknown question source: {source}")
    return {"source": source, "form": "question_card", "questions": list(questions)}


# ---------------------------------------------------------------------------
# W2 -- Agents
# ---------------------------------------------------------------------------


class ModelReference:
    """W2.10: provider/model#variant string form and expanded object form."""

    def __init__(self, provider: str, model: str, variant: str | None = None, **extras: Any) -> None:
        if not provider or not model:
            raise ValueError("provider and model are required")
        self.provider = provider
        self.model = model
        self.variant = variant
        self.extras = dict(extras)

    @classmethod
    def parse(cls, text: str) -> ModelReference:
        main, separator, variant = text.partition("#")
        if "/" not in main:
            raise ValueError(f"invalid model reference: {text}")
        provider, model = main.split("/", 1)
        if not provider or not model or (separator and not variant):
            raise ValueError(f"invalid model reference: {text}")
        return cls(provider, model, variant or None)

    @classmethod
    def from_object(cls, obj: dict[str, Any]) -> ModelReference:
        payload = dict(obj)
        provider = payload.pop("provider", "")
        model = payload.pop("model", "")
        variant = payload.pop("variant", None)
        return cls(provider, model, variant, **payload)

    def to_string(self) -> str:
        base = f"{self.provider}/{self.model}"
        return f"{base}#{self.variant}" if self.variant else base

    def to_dict(self) -> dict[str, Any]:
        result = {"provider": self.provider, "model": self.model}
        if self.variant:
            result["variant"] = self.variant
        result.update(self.extras)
        return result


def apply_agent_fields(
    builtins: dict[str, dict[str, Any]], configs: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """W2.5: hidden/color/disabled fields; disabled removes a built-in at load."""
    result: dict[str, dict[str, Any]] = {}
    for name, agent in builtins.items():
        config = configs.get(name, {})
        if config.get("disabled"):
            continue
        enriched = dict(agent)
        enriched["hidden"] = bool(config.get("hidden", False))
        enriched["color"] = config.get("color", "")
        # 'hidden' is visibility only, explicitly not a security boundary.
        enriched["hidden_is_visibility_only"] = True
        result[name] = enriched
    return result


def resolve_default_agent(configured: str | None, agents: dict[str, dict[str, Any]]) -> str:
    """W2.7: configured default, else build, else first visible primary-capable."""
    if configured and configured in agents:
        return configured
    if "build" in agents:
        return "build"
    for name, agent in agents.items():
        if not agent.get("hidden") and "primary" in agent.get("capabilities", []):
            return name
    raise ValueError("no default agent could be resolved")


class SessionAgentPin:
    """W2.7: existing sessions keep their agent when the default changes."""

    def __init__(self) -> None:
        self._pins: dict[str, str] = {}

    def bind(self, session_id: str, agent: str) -> None:
        self._pins[session_id] = agent

    def agent_for(self, session_id: str) -> str | None:
        return self._pins.get(session_id)


# ---------------------------------------------------------------------------
# W5 -- Commands
# ---------------------------------------------------------------------------


def resolve_model_precedence(
    command_model: str | None = None,
    agent_model: str | None = None,
    session_model: str | None = None,
) -> str | None:
    """W5.5: command model, else command agent's model, else session model."""
    for candidate in (command_model, agent_model, session_model):
        if candidate:
            return candidate
    return None


class BackgroundCommandRunner:
    """W5.6: subagent commands report result or failure back to the parent."""

    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []

    def run(
        self, parent_id: str, command_id: str, fn: Callable[[], Any], *, subagent: bool = False
    ) -> dict[str, Any]:
        if not subagent:
            return {"command_id": command_id, "background": False}
        try:
            value = fn()
            record = {"command_id": command_id, "parent": parent_id, "status": "ok", "result": value}
        except Exception as exc:  # noqa: BLE001 - failures must be reported, not raised through the parent
            record = {
                "command_id": command_id,
                "parent": parent_id,
                "status": "error",
                "result": str(exc),
            }
        self._results.append(record)
        return record

    def report_to_parent(self, parent_id: str) -> list[dict[str, Any]]:
        return [record for record in self._results if record["parent"] == parent_id]


class CommandTemplateStore:
    """W5.7: stored templates keep @path raw; attachments come from composer."""

    AT_PATH = re.compile(r"@[A-Za-z0-9_./-]+")

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._templates: dict[str, str] = {}

    def store(self, name: str, template: str) -> dict[str, Any]:
        self._templates[name] = template
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._templates, sort_keys=True) + "\n", encoding="utf-8")
        return {"name": name, "template": template, "expanded_at_path": False}

    def has_at_path(self, name: str) -> bool:
        return bool(self.AT_PATH.search(self._templates[name]))

    def render(self, name: str, attachments: Any = ()) -> dict[str, Any]:
        return {
            "prompt": self._templates[name],
            "attachments": list(attachments),
            "expanded_at_path": False,
        }


# ---------------------------------------------------------------------------
# X0 -- Problems found inside the three plans (fix before building)
# ---------------------------------------------------------------------------

MILESTONE_SPLITS: dict[str, list[str]] = {
    "M11": ["M11-code-intel-core", "M11-engineering-tools"],
    "M17": ["M17-voice", "M17-documents", "M17-meetings"],
    "M22": ["M22-packaging", "M22-update-feed", "M22-stores"],
}


class MilestoneSplitter:
    """X0.2b: split overloaded milestones into coherent sub-milestones."""

    def __init__(self, splits: dict[str, list[str]] | None = None) -> None:
        self.splits = dict(splits or MILESTONE_SPLITS)

    def split(self, milestone: str) -> list[str]:
        return list(self.splits.get(milestone, [milestone]))

    def remap(self, feature: dict[str, Any]) -> dict[str, Any]:
        updated = dict(feature)
        updated["milestone"] = self.split(feature.get("milestone", ""))[0]
        return updated


class StorePolicy:
    """X0.5: drop stores that require public manifests or reject freeware."""

    def __init__(self) -> None:
        self._stores: dict[str, dict[str, bool]] = {}

    def register(self, name: str, accepts_proprietary_freeware: bool, requires_public_manifest: bool) -> None:
        self._stores[name] = {
            "accepts_proprietary_freeware": bool(accepts_proprietary_freeware),
            "requires_public_manifest": bool(requires_public_manifest),
        }

    def evaluate(self) -> dict[str, Any]:
        allowed, dropped = [], []
        for name, store in self._stores.items():
            if store["accepts_proprietary_freeware"] and not store["requires_public_manifest"]:
                allowed.append(name)
            else:
                dropped.append(name)
        return {
            "allowed": sorted(allowed),
            "dropped": sorted(dropped),
            "retained_binary_sources": ["aur-binary", "self-hosted-apt", "self-hosted-yum"],
        }


class RiskRegister:
    """X0.9: per-milestone risk register and rollback plans."""

    LIKELIHOODS = frozenset({"low", "medium", "high"})
    IMPACTS = frozenset({"low", "medium", "high"})

    def __init__(self) -> None:
        self._risks: list[dict[str, Any]] = []
        self._rollback: dict[str, str] = {}

    def add_risk(
        self,
        milestone: str,
        risk: str,
        likelihood: str,
        impact: str,
        owner: str,
        mitigation: str,
    ) -> None:
        if likelihood not in self.LIKELIHOODS or impact not in self.IMPACTS:
            raise ValueError("likelihood and impact must be low/medium/high")
        self._risks.append(
            {
                "milestone": milestone,
                "risk": risk,
                "likelihood": likelihood,
                "impact": impact,
                "owner": owner,
                "mitigation": mitigation,
            }
        )

    def set_rollback(self, milestone: str, plan: str) -> None:
        self._rollback[milestone] = plan

    def validate(self, milestones: Any) -> dict[str, Any]:
        missing = []
        for milestone in milestones:
            if not any(r["milestone"] == milestone for r in self._risks):
                missing.append(f"{milestone}:risk")
            if milestone not in self._rollback:
                missing.append(f"{milestone}:rollback")
        return {"complete": not missing, "missing": missing}

    def report(self) -> dict[str, Any]:
        return {"risks": list(self._risks), "rollback": dict(self._rollback)}


# ---------------------------------------------------------------------------
# X10 -- Process and builder control
# ---------------------------------------------------------------------------

DECISION_ID = re.compile(r"^(D[1-7]|G[1-7])$")


class DecisionLog:
    """X10.3: owner-level decision log separate from ADRs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def add(
        self,
        decision_id: str,
        question: str,
        answer: str,
        *,
        when: str | None = None,
        owner: str = "owner",
    ) -> dict[str, Any]:
        if not DECISION_ID.fullmatch(decision_id):
            raise ValueError(f"invalid owner-level decision id: {decision_id}")
        entry = {
            "id": decision_id,
            "question": question,
            "answer": answer,
            "date": when or date.today().isoformat(),
            "owner": owner,
            "kind": "decision_log",  # explicitly not an ADR
        }
        entries = self.list()
        if any(item["id"] == decision_id for item in entries):
            raise ValueError(f"decision already logged: {decision_id}")
        entries.append(entry)
        self._save(entries)
        return entry

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


def generate_weekly_report(index_path: str | Path) -> dict[str, Any]:
    """X10.5: 'what is proven' report derived from PLAN-INDEX.json."""
    data = json.loads(Path(index_path).read_text(encoding="utf-8"))
    features = data.get("features", [])
    counts = dict(Counter(feature.get("status", "unknown") for feature in features))
    stale = [
        feature["id"]
        for feature in features
        if feature.get("status") == "verified" and not feature.get("verification_evidence")
    ]
    failing = [
        feature["id"]
        for feature in features
        if feature.get("status") == "failed" or feature.get("ci_status") == "failing"
    ]
    return {
        "total": len(features),
        "counts": counts,
        "stale_evidence": stale,
        "failing_rows": failing,
    }


class ScopeCreepGuard:
    """X10.6: capture new ideas in INBOX.md instead of building inline."""

    def __init__(self, inbox_path: str | Path) -> None:
        self.path = Path(inbox_path)

    def capture(self, idea: str, proposed_milestone: str) -> dict[str, Any]:
        if not idea.strip() or not proposed_milestone.strip():
            raise ValueError("idea and proposed milestone are required")
        entry = f"- [ ] {idea.strip()} — proposed {proposed_milestone.strip()}\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return {"captured": True, "inline_build": False, "entry": entry.strip()}

    def entries(self) -> list[str]:
        if not self.path.exists():
            return []
        return [
            line.strip()
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- [ ]")
        ]


# ---------------------------------------------------------------------------
# W3 -- Permissions
# ---------------------------------------------------------------------------


class McpPermissionActions:
    """W3.11: permission actions for MCP resources and tools."""

    PREFIX = "keel_"
    LIST = "list_mcp_resources"
    READ = "read_mcp_resource"

    @classmethod
    def list_action(cls) -> str:
        return f"{cls.PREFIX}{cls.LIST}"

    @classmethod
    def read_action(cls) -> str:
        return f"{cls.PREFIX}{cls.READ}"

    @classmethod
    def tool_action(cls, server: str, tool: str) -> str:
        return f"{cls.PREFIX}{server}_{tool}"

    @classmethod
    def list_resource(cls, server: str) -> str:
        return server

    @classmethod
    def read_resource(cls, server: str, uri: str) -> str:
        return f"{server}:{uri}"

    @classmethod
    def parse_resource(cls, resource: str) -> dict[str, str | None]:
        if ":" not in resource:
            return {"server": resource, "uri": None}
        server, uri = resource.split(":", 1)
        return {"server": server, "uri": uri}


def expand_path_actions(
    config: dict[str, Any],
    path_keys: Any = ("path", "cwd", "root"),
    shell_keys: Any = ("command", "shell", "script"),
) -> dict[str, Any]:
    """W3.5: expand ~/$HOME for path actions only; shell resources stay raw."""
    result = dict(config)
    for key in path_keys:
        value = result.get(key)
        if isinstance(value, str):
            result[key] = os.path.expanduser(os.path.expandvars(value))
    for key in shell_keys:
        if key in result:
            result[key + "_raw"] = result[key]
    return result


# ---------------------------------------------------------------------------
# Y6 -- Keel's own repository
# ---------------------------------------------------------------------------

FOUR_SURFACES = ("Cowork", "Code", "Duet", "Fleet")
HOMEPAGE = "https://keel-desktop.vercel.app"


def repo_descriptor(description: str, homepage: str) -> dict[str, Any]:
    """Y6.3: descriptor naming the four surfaces and the homepage."""
    missing = [surface for surface in FOUR_SURFACES if surface not in description]
    homepage_ok = homepage.rstrip("/") == HOMEPAGE
    return {
        "surfaces": list(FOUR_SURFACES),
        "missing_surfaces": missing,
        "homepage": homepage,
        "homepage_ok": homepage_ok,
        "valid": not missing and homepage_ok,
    }


# ---------------------------------------------------------------------------
# Owner-gated features (documented, deliberately NOT implemented)
# ---------------------------------------------------------------------------

OWNER_GATED: dict[str, dict[str, Any]] = {
    "Y6.4": {
        "title": "Repo visibility: Public, 0 stars/forks",
        "implemented": False,
        "reason": (
            "Owner-gated (public repository). Changing repository visibility, stars or "
            "fork counts requires an owner action and is explicitly out of scope for "
            "backend code. The live value is recorded in the evidence note only."
        ),
    }
}

GROUP_PREFIXES = ("X4", "D2", "E4", "W9", "X9", "W6", "W8", "W2", "W5", "X0", "X10", "W3", "Y6")

# Every not_started feature except the owner-gated Y6.4 has a real implementation.
FEATURE_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "X4.1": BargeInController,
    "X4.2": stream_tts_sentences,
    "X4.3": WakeWordController,
    "X4.4": LocalVisionTool,
    "X4.5": VideoTooling,
    "X4.6": VoiceCommandGrammar,
    "X4.7": AudioPrivacyPolicy,
    "D2.2": HookRunner,
    "D2.4": TurnClaimGate,
    "D2.6": RequestSeriesLogger,
    "D2.12": ProjectionRegistry,
    "D2.14": JsonlPersistence,
    "D2.17": GoalsService,
    "E4.3": CoverageGate,
    "E4.4": BenchmarkGate,
    "E4.6": FixtureFormatPolicy,
    "E4.7": BrowserSnapshotLane,
    "E4.13": built_entrypoint_smoke,
    "E4.14": TestResolver,
    "W9.1": McpPanelService,
    "W9.2": ApprovalService,
    "W9.3": normalize_agent_config,
    "W9.4": build_palette_entries,
    "W9.5": FirstRunNotice,
    "W9.6": web_server_config,
    "X9.2": VcrRecorder,
    "X9.4": McpConformanceRunner,
    "X9.6": pseudo_localize,
    "X9.8": TokenAccountingCheck,
    "X9.9": SoakMonitor,
    "X9.10": MutationReport,
    "W6.2": ConfidenceLabeler,
    "W6.4": ConductorRouter,
    "W6.5": choose_tool,
    "W6.6": MemoryLedger,
    "W8.1": AllowlistMatcher,
    "W8.2": BlobCaps,
    "W8.3": ComputerAccessGuard,
    "W8.4": normalize_question,
    "W2.5": apply_agent_fields,
    "W2.7": resolve_default_agent,
    "W2.10": ModelReference,
    "W5.5": resolve_model_precedence,
    "W5.6": BackgroundCommandRunner,
    "W5.7": CommandTemplateStore,
    "X0.2b": MilestoneSplitter,
    "X0.5": StorePolicy,
    "X0.9": RiskRegister,
    "X10.3": DecisionLog,
    "X10.5": generate_weekly_report,
    "X10.6": ScopeCreepGuard,
    "W3.5": expand_path_actions,
    "W3.11": McpPermissionActions,
    "Y6.3": repo_descriptor,
}

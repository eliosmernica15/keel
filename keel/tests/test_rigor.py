"""A4.4 — rigor contract in the agent persona."""

from __future__ import annotations

from keel.fakes import SeededRng, VirtualClock
from keel.instructions import instructions_attachment, rigor_attachment
from keel.session import Session, SessionConfig


def test_rigor_contract_requires_evidence():
    text = rigor_attachment()
    assert "Verify before claiming done" in text
    assert "Never invent" in text
    assert "not verified" in text


def test_fleet_guidance_includes_rigor_contract():
    assert rigor_attachment() in instructions_attachment()


def test_session_injects_rigor_contract(tmp_path):
    seen = {}

    class Model:
        def complete(self, messages, tools):
            seen["messages"] = messages
            return [{"type": "text", "text": "done"}]

    config = SessionConfig(cwd=str(tmp_path),
                           state_root=str(tmp_path / "state"),
                           bare=True, permission_mode="default",
                           session_id="11111111-1111-4111-8111-111111111111",
                           model="boom-1", seed=0)
    session = Session(model_client=Model(), executor=object(), config=config,
                      clock=VirtualClock(), rng=SeededRng(0))
    out = session.run("hello")
    assert "Verify before claiming done" in str(seen["messages"][0]["content"])

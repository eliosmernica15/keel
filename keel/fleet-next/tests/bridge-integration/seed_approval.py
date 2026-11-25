"""FIXTURE seeder: create a pending approval in the REAL bridge's SQLite DB.

Approvals are persisted by FleetStore, so a labeled helper process can seed one
deterministically; the decision itself is then made through the real BFF ->
real bridge HTTP path. This only exercises the HTTP decide contract; it does
not simulate a provider turn. Every test using it is labelled FIXTURE-SEEDED.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(SRC))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--bot", required=True)
    parser.add_argument("--tool", default="run_shell")
    args = parser.parse_args()

    from keel.fleet.service import FleetStore

    store = FleetStore(args.db)
    approval_id = "ap_" + uuid.uuid4().hex[:12]
    approval = store.create_approval(
        approval_id=approval_id,
        bot_id=args.bot,
        tool_name=args.tool,
        fingerprint="fixture-fingerprint",
        args_summary="echo bridge-integration",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    print(approval["approval_id"])
    store.close()


if __name__ == "__main__":
    main()

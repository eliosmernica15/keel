"""Start the real Keel Python bridge on a fixed QA-owned port for E2E runs.

Test-only throwaway token; never a provider key or production credential.
Uses the real ~/.keel state so Fleet tests see genuine bridge data.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEEL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(KEEL, "src"))

os.environ["KEEL_TOKEN"] = "local-e2e-bridge-token"

import keel.webapp as webapp  # noqa: E402

if __name__ == "__main__":
    webapp.serve(8739)

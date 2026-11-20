"""Release version consistency across all sources."""

from __future__ import annotations

import keel
from keel.release.common import load_versions, validate_version


def test_package_version_matches_all_release_sources():
    versions = load_versions()
    assert keel.__version__ == "0.1.1"
    assert "src/keel/__init__.py" in versions
    assert set(versions.values()) == {"0.1.1"}
    assert validate_version() == "0.1.1"

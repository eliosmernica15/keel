"""B7.8 — feature flags and kill switch."""

from __future__ import annotations

from keel.feature_flags import FeatureFlags


def test_flag_defaults_and_toggle(tmp_path):
    flags = FeatureFlags(tmp_path)
    assert flags.enabled("new-ui", default=False) is False
    flags.set("new-ui", True)
    assert flags.enabled("new-ui") is True
    flags.set("new-ui", False, kill_switch=True)
    assert flags.enabled("new-ui") is False
    assert flags.all()["new-ui"]["kill_switch"] is True

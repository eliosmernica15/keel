"""B5.2 — release feeds and version history."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from keel import release_feed


def test_latest_json_and_history():
    latest = release_feed.latest_json("https://example.test")
    assert latest["version"] == "0.1.1"
    assert latest["base_url"] == "https://example.test"
    assert len(release_feed.version_history()["versions"]) >= 2


def test_rss_is_wellformed_and_escaped():
    feed = release_feed.rss_feed("https://example.test")
    root = ET.fromstring(feed)
    items = root.findall("./channel/item")
    assert len(items) >= 2
    assert items[0].findtext("title") == "Keel 0.1.1"


def test_write_feeds(tmp_path):
    paths = release_feed.write_feeds(tmp_path, site_url="https://example.test")
    assert all(path.is_file() for path in paths)
    latest = json.loads(paths[0].read_text(encoding="utf-8"))
    assert latest["version"] == "0.1.1"
    ET.parse(paths[2])

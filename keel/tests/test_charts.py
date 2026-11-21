"""B2.11/C13.5 — offline SVG chart and diagram rendering."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from keel.charts import bar_chart, flow_diagram, sparkline


def test_bar_chart_is_valid_svg():
    svg = bar_chart([1, 3, 2], ["a", "b", "c"])
    root = ET.fromstring(svg)
    assert len(root.findall("{http://www.w3.org/2000/svg}rect")) == 3


def test_sparkline_and_escape():
    root = ET.fromstring(sparkline([1, 2, 3, 2]))
    assert root.findall("{http://www.w3.org/2000/svg}polyline")
    diagram = flow_diagram(["a<b", "c"], [("a<b", "c")])
    assert "&lt;" in diagram and ET.fromstring(diagram) is not None


def test_empty_inputs():
    assert ET.fromstring(bar_chart([])) is not None
    assert ET.fromstring(sparkline([])) is not None

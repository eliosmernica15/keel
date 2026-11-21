"""B2.x — knowledge-work descriptors."""

from __future__ import annotations

from keel.knowledge_work import (MacroRecorder, http_request_spec,
                                 mermaid_to_svg_stub, ocr_descriptor, template)


def test_http_spec_needs_approval():
    spec = http_request_spec("post", "https://api.test/x", body="{}")
    assert spec["method"] == "POST" and spec["approval_required"] is True


def test_mermaid_nodes():
    result = mermaid_to_svg_stub("graph TD; A[Start]-->B[End];")
    assert "A" in result["nodes"] and "B" in result["nodes"]


def test_ocr_and_macro_and_template(tmp_path):
    assert ocr_descriptor("doc.pdf")["engine"] == "tesseract"
    recorder = MacroRecorder(tmp_path)
    entry = recorder.record("deploy", [{"kind": "command", "name": "test"}])
    assert entry["name"] == "deploy"
    assert "Review" in template("code-review")

"""Locally achievable document/visual requirements: B2.12, B5.6, C4.11."""

from __future__ import annotations

import html
import json
import shutil
import time
from pathlib import Path


# --------------------------------------------------------------- B2.12
def ocr_tool_status() -> dict:
    """Detect local OCR/PDF tools without pretending they are installed."""
    import shutil as _shutil

    tools = {name: _shutil.which(name)
             for name in ("tesseract", "pdftotext", "pdftoppm")}
    try:
        import pypdf  # noqa: F401

        tools["pypdf"] = "python-module"
    except ImportError:
        tools["pypdf"] = None
    return {"tools": tools,
            "ocr_available": bool(tools.get("tesseract")),
            "pdf_available": bool(tools.get("pdftotext") or tools.get("pypdf")),
            "license_note": "Tesseract is Apache-2.0; pdftotext is GPL — check "
                            "before bundling either with a proprietary product."}


def parse_pdf(path: str | Path) -> dict:
    """Extract real text/tables from a PDF using local libraries only."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False, "reason": "pypdf not installed",
                "license": "BSD-3-Clause"}
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        return {"ok": False, "reason": f"invalid PDF: {type(exc).__name__}",
                "license": "BSD-3-Clause"}
    pages = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        tables = []
        try:
            for table in page.extract_tables() or []:
                tables.append(table)
        except (AttributeError, NotImplementedError):
            pass
        pages.append({"page": index + 1, "text": text, "tables": tables})
    return {"ok": True, "pages": pages,
            "page_count": len(pages), "engine": "pypdf",
            "license": "BSD-3-Clause"}


def ocr_image(path: str | Path, *, lang: str = "eng") -> dict:
    """OCR an image via a user-installed Tesseract; never fabricate text."""
    import shutil as _shutil
    import subprocess

    path = Path(path)
    if not path.is_file():
        return {"ok": False, "reason": "image file not found"}
    tesseract = _shutil.which("tesseract")
    if not tesseract:
        return {"ok": False, "reason": "tesseract not installed",
                "hint": "Install Tesseract (Apache-2.0) locally to enable OCR."}
    result = subprocess.run([tesseract, str(path), "stdout", "-l", lang],
                            capture_output=True, timeout=120, check=False)
    if result.returncode != 0:
        return {"ok": False,
                "reason": result.stderr.decode("utf-8", errors="replace")[:300]}
    return {"ok": True,
            "text": result.stdout.decode("utf-8", errors="replace"),
            "engine": "tesseract", "license": "Apache-2.0"}


# --------------------------------------------------------------- B5.6
def build_screenshot_gallery(source_dirs: list[str] | Path,
                             out_dir: str | Path,
                             *, title: str = "Keel screenshots") -> dict:
    """Build an honest gallery from real PNG/JPG files produced by E2E runs."""
    import importlib

    Image = importlib.import_module("PIL.Image")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for folder in source_dirs:
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                continue
            if "screenshot" not in path.name.lower() and \
                    root.name.lower() != "screenshots":
                continue
            try:
                with Image.open(path) as image:
                    width, height = image.size
                dest = out / path.name
                if path.resolve() != dest.resolve():
                    shutil.copy2(path, dest)
            except (OSError, ValueError):
                continue
            entries.append({"file": path.name, "width": width,
                            "height": height,
                            "source": "local E2E capture"})
    cards = "".join(
        f"<figure><img src='{html.escape(e['file'])}' alt='{html.escape(e['file'])}'>"
        f"<figcaption>{html.escape(e['file'])} · {e['width']}x{e['height']}"
        f" · {html.escape(e['source'])}</figcaption></figure>"
        for e in entries)
    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title><style>"
            "body{background:#0a0605;color:#f7f4ef;font-family:sans-serif;margin:2rem}"
            "figure{display:inline-block;margin:1rem;vertical-align:top}"
            "img{max-width:520px;border:1px solid #444;border-radius:8px}"
            "figcaption{font-size:12px;opacity:.7;max-width:520px}"
            "</style></head><body>"
            f"<h1>{html.escape(title)}</h1>"
            "<p>Generated from actual local application captures. No stock images.</p>"
            + (cards or "<p>No E2E screenshots available yet.</p>")
            + "</body></html>")
    (out / "index.html").write_text(page, encoding="utf-8")
    return {"count": len(entries), "entries": entries,
            "html": str(out / "index.html"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# --------------------------------------------------------------- C4.11
def visual_diff(before: str | Path, after: str | Path,
                *, out: str | Path | None = None) -> dict:
    """Pixel-level UI diff using Pillow; returns real metrics and diff image."""
    import importlib

    pil_image = importlib.import_module("PIL.Image")
    pil_chops = importlib.import_module("PIL.ImageChops")
    Image, ImageChops = pil_image, pil_chops

    before_path, after_path = Path(before), Path(after)
    if not before_path.is_file() or not after_path.is_file():
        raise FileNotFoundError("before/after screenshots required")
    with Image.open(before_path) as a, Image.open(after_path) as b:
        a = a.convert("RGB")
        b = b.convert("RGB")
        if a.size != b.size:
            return {"ok": False, "reason": "image dimensions differ",
                    "before": a.size, "after": b.size}
        diff = ImageChops.difference(a, b)
        bbox = diff.getbbox()
        changed = 0
        if bbox:
            # Count changed pixels from a grey histogram — no numpy needed.
            grey = diff.convert("L")
            histogram = grey.histogram()
            changed = sum(histogram[9:])
        total = a.size[0] * a.size[1]
        result = {
            "ok": True, "changed_pixels": changed, "total_pixels": total,
            "changed_pct": round(100 * changed / total, 3),
            "diff_bbox": list(bbox) if bbox else None,
        }
        if out:
            diff.save(out)
            result["diff_image"] = str(out)
        return result


def console_network_capture(events: list[dict]) -> dict:
    """Normalize captured console/network events from a real UI session."""
    console = [e for e in events if e.get("kind") == "console"]
    network = [e for e in events if e.get("kind") == "network"]
    return {
        "console": console, "network": network,
        "errors": [e for e in console if e.get("level") == "error"],
        "failed_requests": [e for e in network
                            if int(e.get("status", 200)) >= 400],
        "note": "Data must come from a real captured session; no simulation.",
    }

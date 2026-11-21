"""Cowork document and spreadsheet workflows (C2.1).

Real local processing of Office Open XML files using only the standard
library: extract text from DOCX/XLSX, read/write spreadsheet cells, and
convert between tabular formats. No cloud service or paid dependency.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_DOCX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>{body}</w:body></w:document>"""

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def read_docx(path: str | Path) -> str:
    """Extract paragraphs from a real DOCX file (no external library)."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs = []
    for para in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in para.iter(W_NS + "t"))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def write_docx(path: str | Path, text: str) -> Path:
    """Write a minimal, valid DOCX that Word/LibreOffice can open."""
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{_escape(line)}</w:t></w:r></w:p>"
        for line in str(text).splitlines())
    document = _DOCX_TEMPLATE.format(body=body or "<w:p/>")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", document)
    return target


def read_xlsx(path: str | Path, *, sheet: int = 0) -> list[list[str]]:
    """Read a worksheet's cells into a grid of strings."""
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            sroot = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(S_NS + "t"))
                      for si in sroot.iter(S_NS + "si")]
        name = f"xl/worksheets/sheet{sheet + 1}.xml"
        if name not in archive.namelist():
            return []
        root = ET.fromstring(archive.read(name))
    grid: list[list[str]] = []
    for row in root.iter(S_NS + "row"):
        cells: list[str] = []
        for cell in row.iter(S_NS + "c"):
            value_node = cell.find(S_NS + "v")
            value = value_node.text if value_node is not None else ""
            if cell.get("t") == "s" and value is not None:
                value = shared[int(value)] if int(value) < len(shared) else ""
            elif cell.get("t") == "inlineStr":
                value = "".join(t.text or "" for t in cell.iter(S_NS + "t"))
            cells.append(value or "")
        grid.append(cells)
    return grid


def write_xlsx(path: str | Path, rows: list[list]) -> Path:
    """Write a simple XLSX workbook with inline strings and numbers."""
    def col_letter(index: int) -> str:
        result = ""
        index += 1
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    sheet_rows = []
    for r_index, row in enumerate(rows, 1):
        cells = []
        for c_index, value in enumerate(row):
            ref = f"{col_letter(c_index)}{r_index}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = _escape(str(value))
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f'<row r="{r_index}">' + "".join(cells) + "</row>")
    sheet = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
             f'<worksheet xmlns="{S_NS[1:-1]}"><sheetData>'
             + "".join(sheet_rows) + "</sheetData></worksheet>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>')
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{S_NS[1:-1]}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return target


def spreadsheet_stats(grid: list[list[str]]) -> dict:
    """Compute basic statistics for a numeric spreadsheet column."""
    if not grid:
        return {"rows": 0}
    header = grid[0]
    stats = {}
    for index, name in enumerate(header):
        values = []
        for row in grid[1:]:
            if index < len(row):
                try:
                    values.append(float(row[index]))
                except (TypeError, ValueError):
                    continue
        if values:
            stats[name] = {"count": len(values), "sum": round(sum(values), 4),
                           "mean": round(sum(values) / len(values), 4),
                           "min": min(values), "max": max(values)}
    return {"rows": len(grid) - 1, "columns": len(header), "stats": stats}


def csv_to_grid(text: str, *, delimiter: str = ",") -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def grid_to_csv(grid: list[list], *, delimiter: str = ",") -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerows(grid)
    return buffer.getvalue()


def document_answer(question: str, text: str, *, max_chars: int = 300) -> list[dict]:
    """Document Q&A with citations: return matching paragraphs and offsets."""
    terms = [term.lower() for term in re.findall(r"\w+", question) if len(term) > 2]
    hits = []
    offset = 0
    for para in text.split("\n"):
        lowered = para.lower()
        matched = [term for term in terms if term in lowered]
        if matched:
            hits.append({"text": para[:max_chars], "offset": offset,
                         "terms": matched})
        offset += len(para) + 1
    return hits[:20]

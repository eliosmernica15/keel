"""C2.1 — real Cowork document and spreadsheet workflows."""

from __future__ import annotations

from keel.documents import (csv_to_grid, document_answer, grid_to_csv,
                            read_docx, read_xlsx, spreadsheet_stats,
                            write_docx, write_xlsx)


def test_docx_roundtrip(tmp_path):
    path = write_docx(tmp_path / "report.docx",
                      "Project Report\nKeel is local-first.\nSecond paragraph.")
    assert path.is_file()
    text = read_docx(path)
    assert "Project Report" in text
    assert "Second paragraph" in text


def test_xlsx_roundtrip(tmp_path):
    rows = [["Name", "Q1", "Q2"], ["Alice", 10, 20], ["Bob", 5, 15]]
    path = write_xlsx(tmp_path / "numbers.xlsx", rows)
    grid = read_xlsx(path)
    assert grid[0][0] == "Name" and grid[1][1] == "10"
    stats = spreadsheet_stats(grid)
    assert stats["columns"] == 3 and stats["stats"]["Q1"]["sum"] == 15.0


def test_csv_conversion_and_qa():
    grid = csv_to_grid("a,b\n1,2\n")
    assert grid == [["a", "b"], ["1", "2"]]
    assert grid_to_csv(grid).startswith("a,b")
    hits = document_answer("local-first report",
                           "Project Report\nKeel is local-first.")
    assert hits and any("local" in hit["terms"] for hit in hits)

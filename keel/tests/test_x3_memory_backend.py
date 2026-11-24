"""Adversarial backend tests for X3.1-X3.16 (stdlib-only local behaviour)."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import struct
import threading
import time
import zlib
from pathlib import Path

import pytest

from keel.x3_memory_backend import (ConsentDenied, X3Backend, X3Error,
                                    _decode_png_rgb)


@pytest.fixture()
def backend(tmp_path):
    return X3Backend(tmp_path / "state")


def _png(width: int, height: int, pixel=(0, 0, 0), change=None) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(pixel if change is None or change != (x, y) else (255, 255, 255))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


# --- X3.1 desktop search -----------------------------------------------------

def test_x31_search_approved_folders_only_and_safety(tmp_path, backend):
    good = tmp_path / "good"
    good.mkdir()
    (good / "notes.md").write_text("Keel desktop search finds local notebooks", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the allowlist", encoding="utf-8")
    backend.approve_folder(good)
    stats = backend.index_folders()
    assert stats["indexed"] >= 1
    assert not any("secret.txt" in d["path"] for d in backend.state_snapshot()["search"]["docs"].values())
    hits = backend.search_documents("notebooks", limit=5)
    assert hits and hits[0]["path"].endswith("notes.md")
    assert "notebooks" in hits[0]["snippet"]
    with pytest.raises(X3Error):
        backend.approve_folder(good / "does-not-exist")
    with pytest.raises(X3Error):
        backend.approve_folder(tmp_path / "secret.txt")  # a file is not a folder
    assert backend.search_tool_descriptor()["network"] is False
    assert backend.search_palette_entries()[0]["action"] == "desktop_search"
    assert backend.revoke_folder(good) is True
    assert backend.search_documents("notebooks") == []


def test_x31_search_fts_syntax_and_binary_are_safe(tmp_path, backend):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("alpha beta gamma", encoding="utf-8")
    (folder / "blob.bin").write_bytes(b"alpha\x00beta")
    backend.approve_folder(folder)
    stats = backend.index_folders(extensions=("txt", "bin"))
    assert stats["indexed"] == 1  # NUL-containing binary skipped
    assert backend.search_documents('" OR *') == []
    assert backend.search_documents("alpha", use_embeddings=True)[0]["score"] > 0


# --- X3.2 document redaction -------------------------------------------------

def test_x32_redaction_preview_pdf_and_verification(backend):
    text = ("Contact Jane Doe at jane@example.com or 123-45-6789.\n"
            "PASSPORT X1234567 authorized.\fPage two:customterm here.")
    result = backend.redact_document(text, custom_terms=("customterm",))
    assert {"email", "ssn", "id", "custom"} <= {s["kind"] for s in result["spans"]}
    assert "jane@example.com" not in result["preview"]
    assert "123-45-6789" not in result["preview"]
    assert "customterm" not in result["preview"]
    assert result["verification"]["clean"] is True
    assert result["verification"]["signature_ok"] is True
    assert result["pdf"].startswith(b"%PDF-") and result["pdf"].rstrip().endswith(b"%%EOF")
    assert result["page_count"] == 2


def test_x32_verification_catches_leaked_secret(backend):
    pdf = backend._render_pdf(["Secret: jane@example.com"])
    check = backend.verify_redacted_pdf(pdf, ["jane@example.com"])
    assert check["clean"] is False and check["leaks"] == ["jane@example.com"]
    with pytest.raises(X3Error):
        backend.detect_sensitive("abc", custom_terms=("x",))


# --- X3.3 receipt extractor --------------------------------------------------

def test_x33_receipt_parse_review_commit_csv(backend):
    raw = ("Corner Market\nDate: 04/05/2024\n2 x 3.50 apples 7.00\n"
           "Tax: 0.60\nTotal: $7.60\n")
    fields = backend.parse_receipt(raw)
    assert fields["merchant"] == "Corner Market"
    assert fields["date"] == "2024-04-05"
    assert fields["total"] == "7.60" and fields["tax"] == "0.60"
    assert fields["items"][0]["qty"] == 2
    receipt = backend.submit_receipt(raw, source="scan-1")
    assert receipt["status"] == "pending"
    committed = backend.review_receipt(receipt["id"], {"merchant": "Corner Market Ltd"})
    assert committed["status"] == "committed"
    rows = backend.receipt_rows()
    assert rows[0]["merchant"] == "Corner Market Ltd"
    assert "7.60" in backend.receipts_csv()
    again = backend.submit_receipt(raw, source="scan-2")
    assert again["duplicate"] is True


def test_x33_receipt_low_confidence_and_sql_safe(backend):
    weak = backend.submit_receipt("a stray line")
    assert weak["fields"]["overall_confidence"] < 0.7
    with pytest.raises(X3Error):
        backend.review_receipt(weak["id"])
    nasty = "Shop'); DROP TABLE receipts;--\nTotal: 1.00\nDate: 2024-01-02\n"
    rec = backend.submit_receipt(nasty, auto_commit=True)
    assert rec["status"] == "committed"
    assert any("DROP TABLE" in r["merchant"] for r in backend.receipt_rows())


# --- X3.4 contract comparison ------------------------------------------------

def test_x34_contract_clause_diff_with_page_citations(backend):
    original = "1. Term\nThe term is one year.\n\f2. Fee\nThe fee is $10.\n"
    revised = "1. Term\nThe term is two years.\n\f3. Notice\nWritten notice is required.\n"
    result = backend.compare_contracts(original, revised)
    assert any(c["heading"] == "3" for c in result["added"])
    assert any(c["heading"] == "2" for c in result["removed"])
    assert result["changed"][0]["similarity"] < 1
    assert {c["page"] for c in result["citations"]} == {1, 2}
    assert "added" in result["summary"]
    same = backend.compare_contracts(original, original.replace("term is one", "term  is  one"))
    assert same["summary"].startswith("No material")


# --- X3.5 spreadsheet helper -------------------------------------------------

def test_x35_formula_pivot_chart_and_copy_only(tmp_path, backend):
    grid = [["Region", "Sales"], ["North", "10"], ["North", "20"], ["South", "5"]]
    assert backend.explain_formula("=SUM(B2:B4)", grid)["value"] == 35.0
    assert backend.explain_formula("AVERAGE(B2,B3)", grid)["value"] == 15.0
    pivot = backend.build_pivot(grid, group_col=0, value_col=1)
    assert pivot == {"North": 30, "South": 5}
    assert "<svg" in backend.chart_svg(pivot)
    source = tmp_path / "book.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    before = source.read_bytes()
    outcome = backend.write_spreadsheet_results(source, {"grid": grid, "pivot": pivot})
    assert outcome["source_unchanged"] is True
    assert Path(outcome["output"]).read_text(encoding="utf-8").startswith("Region,Sales")
    assert Path(outcome["sidecar"]).exists()
    with pytest.raises(X3Error):
        backend.write_spreadsheet_results(source, {"grid": grid}, output=source)
    with pytest.raises(X3Error):
        backend.write_spreadsheet_results(source, {"grid": grid}, in_place=True)


def test_x35_spreadsheet_errors_including_circular(backend):
    grid = [["A", "B", "C"], ["1", "0", "=A2/B2"], ["=C3", "=ZZ999", "=A3"]]
    errors = {e["cell"]: e["error"] for e in backend.find_spreadsheet_errors(grid)}
    assert errors["C2"] == "#DIV/0!"
    assert errors["A3"] == "#CIRCULAR!"
    assert errors["B3"] == "#REF!"


def test_x35_formula_keeps_quoted_cell_references_intact(backend):
    grid = [["1"], ["2"]]
    assert backend.explain_formula('=CELL("A1")', grid)["value"] == 1.0
    assert backend.explain_formula("=CELL('A2')", grid)["value"] == 2.0
    assert backend.explain_formula('=SUM(CELL("A1"),CELL("A2"))', grid)["value"] == 3.0
    assert backend.explain_formula("=SUM(A1:A2)", grid)["value"] == 3.0


# --- X3.6 file organiser -----------------------------------------------------

def test_x36_organizer_dry_run_apply_undo_and_collisions(tmp_path, backend):
    root = tmp_path / "inbox"
    root.mkdir()
    (root / "photo.jpg").write_bytes(b"x")
    (root / "note.txt").write_text("hello", encoding="utf-8")
    rules = [{"name": "images", "kind": "type", "match": ["jpg"], "dest": "images"},
             {"name": "text", "kind": "name", "match": [r"^note"], "dest": "text"}]
    preview = backend.plan_organization(root, rules, dry_run=True)
    assert len(preview["plan"]) == 2 and preview["journal_id"] is None
    assert (root / "photo.jpg").exists()  # dry-run never moves
    applied = backend.plan_organization(root, rules, dry_run=False)
    assert applied["journal_id"]
    assert (root / "images" / "photo.jpg").exists()
    assert backend.undo_organization(applied["journal_id"]) == 2
    assert (root / "photo.jpg").exists()
    with pytest.raises(X3Error):
        backend.plan_organization(root, [{"kind": "type", "match": "jpg", "dest": "../escape"}])
    for sub in ("one", "two"):
        (root / sub).mkdir()
        (root / sub / "same.txt").write_text("x", encoding="utf-8")
    with pytest.raises(X3Error):
        backend.plan_organization(root, [{"kind": "name", "match": "same", "dest": "flat"}])


# --- X3.7 duplicate finder / safe delete ------------------------------------

def test_x37_duplicates_phash_trash_restore(tmp_path, backend):
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    first.write_bytes(b"identical bytes")
    second.write_bytes(b"identical bytes")
    p1 = tmp_path / "one.png"
    p2 = tmp_path / "two.png"
    p1.write_bytes(_png(16, 16))
    p2.write_bytes(_png(16, 16, change=(3, 3)))
    result = backend.find_duplicates([first, second, p1, p2])
    assert [sorted(g) for g in result["exact"]] == [[str(first), str(second)]]
    assert result["near"] and str(p1) in result["near"][0]["paths"]
    assert backend.image_phash(first) is None
    entry = backend.safe_delete(second)
    assert not second.exists() and Path(entry["stored"]).exists()
    assert backend.restore_trash(entry["id"]) == second
    assert second.exists() and backend.list_trash() == []
    with pytest.raises(X3Error):
        backend.restore_trash("missing")


# --- X3.8 web clipper --------------------------------------------------------

def test_x38_clipper_sanitizes_html_and_exports_once(tmp_path, backend):
    html_text = ("<html><head><title>My Page</title><style>bad{}</style></head>"
                 "<body><script>alert(1)</script><h1>Hello</h1>"
                 "<a href='javascript:alert(2)'>click</a>"
                 "<a href='https://example.test/x'>safe</a></body></html>")
    clip = backend.clip_page("https://news.test/1", html_text, tags=["research"])
    assert "alert(1)" not in clip["markdown"] and "bad{}" not in clip["markdown"]
    assert "javascript:" not in clip["markdown"]
    assert "https://example.test/x" in clip["markdown"]
    assert backend.clip_page("https://news.test/1", html_text)["id"] == clip["id"]
    with pytest.raises(X3Error):
        backend.clip_page("file:///etc/passwd", "x")
    vault = tmp_path / "vault"
    written = backend.export_clips_to_vault(vault)
    assert written and Path(written[0]).exists()
    assert backend.export_clips_to_vault(vault) == []  # no overwrite
    backend.mark_clip_read(clip["id"])
    assert backend.read_later_queue() == []


# --- X3.9 RSS digest ---------------------------------------------------------

def test_x39_rss_user_feeds_digest_and_xxe_guard(backend):
    with pytest.raises(X3Error):
        backend.ingest_feed("https://x.test/rss", "<rss/>")
    backend.register_feed("https://x.test/rss")
    xml = ('<?xml version="1.0"?><rss xmlns:dc="urn:dc"><channel>'
           '<item><title>One</title><link>https://x.test/1</link></item>'
           '<item><title>One</title><link>https://x.test/1</link></item>'
           '<item><title>Two</title><dc:creator>x</dc:creator>'
           '<link>https://x.test/2</link></item></channel></rss>')
    ingested = backend.ingest_feed("https://x.test/rss", xml)
    assert ingested["added"] == 2
    digest = backend.feed_digest()
    assert "One" in digest["summary"] and digest["items"] == 2
    assert backend.feed_digest()["items"] == 0
    assert "T" in backend.next_digest_due("https://x.test/rss", 1)
    with pytest.raises(X3Error):
        backend.ingest_feed("https://x.test/rss", '<!DOCTYPE rss [<!ENTITY x "y">]><rss/>')
    with pytest.raises(X3Error):
        backend.ingest_feed("https://x.test/rss", "<rss><broken>")
    with pytest.raises(X3Error):
        backend.next_digest_due("https://x.test/rss", 0)


# --- X3.10 flashcards --------------------------------------------------------

def test_x310_generate_review_sm2_and_consolidate(backend):
    cards = backend.generate_cards("Q: What is Keel?\nA: A local agent.\nterm :: definition\n"
                                   "The sky is {{c1::blue}} today.", deck="study")
    assert len(cards) == 3 and cards[-1]["kind"] == "cloze"
    card = cards[0]
    assert any(c["id"] == card["id"] for c in backend.due_cards("study"))  # new cards are due
    assert backend.review_card(card["id"], 4)["interval_days"] == 1
    failed = backend.review_card(card["id"], 0)
    assert failed["repetitions"] == 0 and failed["interval_days"] == 1
    assert not any(c["id"] == card["id"] for c in backend.due_cards("study"))
    backend._section("flashcards")["decks"]["study"][0]["due"] = "2001-01-01T00:00:00Z"
    assert any(c["id"] == card["id"] for c in backend.due_cards("study"))
    with pytest.raises(X3Error):
        backend.review_card(card["id"], 6)
    with pytest.raises(X3Error):
        backend.add_card("study", "", "back")
    backend.add_card("other", "What is Keel?", "A local agent.")
    assert backend.consolidate_cards() == 1
    assert len(backend.list_cards()) == 3


# --- X3.11 tutor -------------------------------------------------------------

def test_x311_tutor_modes_no_answer_leak(backend):
    for mode in ("socratic", "quiz", "explain_back"):
        session = backend.tutor_session(mode, "photosynthesis")
        prompt = backend.tutor_next_prompt(session["id"])
        assert "photosynthesis" in prompt
        reply = backend.tutor_answer(session["id"], "my idea")
        assert reply["answer_revealed"] is (mode != "socratic")
        assert backend.tutor_status(session["id"])["turns"] == 1
    with pytest.raises(X3Error):
        backend.tutor_session("lecture", "x")
    assert "wait_for_answer" in backend.tutor_persona_bundle()["modes"]["socratic"]["skills"]


# --- X3.12 writing coach -----------------------------------------------------

def test_x312_writing_heuristics_and_license_gate(tmp_path, backend):
    report = backend.check_writing("teh  cat sat. I i saw the the very long " +
                                   " ".join(["word"] * 30))
    kinds = {i["kind"] for i in report["issues"]}
    assert {"typo", "spacing", "repeated_word", "long_sentence"} <= kinds
    assert report["third_party"]["enabled"] == {}
    with pytest.raises(X3Error):
        backend.enable_third_party_checker("langtool", "gpl-3.0", license_accepted=True,
                                           local_path=__file__)
    with pytest.raises(X3Error):
        backend.enable_third_party_checker("langtool", "mit", local_path=__file__)
    local = tmp_path / "checker.py"
    local.write_text("# local\n", encoding="utf-8")
    assert backend.enable_third_party_checker("local", "mit", license_accepted=True,
                                              local_path=local)["accepted"] is True
    with pytest.raises(X3Error):
        backend.check_writing("text", style="shouty")


# --- X3.13 CRM ---------------------------------------------------------------

def test_x313_crm_followups_and_vault_sanitization(tmp_path, backend):
    past = "2001-01-01"
    contact = backend.add_contact("Ada", email="ada@example.test", notes="Line\n---\nsecret",
                                  follow_up=past)
    assert len(backend.due_followups()) == 1
    with pytest.raises(X3Error):
        backend.add_contact("Ada", email="ada@example.test")
    with pytest.raises(X3Error):
        backend.add_contact("Bad", follow_up="not-a-date")
    before = contact["follow_up"]
    snoozed = backend.snooze_followup(contact["id"], 30)
    assert snoozed["follow_up"] > before
    vault = tmp_path / "vault"
    written = backend.export_contacts_to_vault(vault)
    text = Path(written[0]).read_text(encoding="utf-8")
    assert "\\---" in text and "Ada" in text


# --- X3.14 finance CSV -------------------------------------------------------

def test_x314_finance_csv_import_categorize_and_reject_network(backend):
    csv_text = ("\ufeffdate,description,amount\n"
                "2024-01-02,Whole Foods Market,12.50\n"
                "2024-01-02,Uber ride,8.00\n"
                "2024-01-02,Uber ride,8.00\n"
                "bad-date,Nowhere,abc\n")
    result = backend.import_finance_csv(csv_text)
    assert result["imported"] == 2 and result["skipped"] == 2
    summary = backend.finance_summary()
    assert summary["by_category"]["groceries"] == 12.5
    assert summary["by_category"]["transport"] == 8.0
    assert "Uber ride" in backend.export_finance_csv()
    with pytest.raises(X3Error):
        backend.import_finance_csv(csv_text, source="https://bank.test/api")
    with pytest.raises(X3Error):
        backend.import_finance_csv("name,value\nx,1\n")


# --- X3.15 clipboard ---------------------------------------------------------

def test_x315_clipboard_optin_consent_encryption_expiry_tamper(backend):
    with pytest.raises(X3Error):
        backend.record_clipboard("secret")
    assert backend.set_clipboard_opt_in(True, passphrase="strong passphrase")["enabled"] is True
    assert backend.unlock_clipboard("strong passphrase") is True
    with pytest.raises(X3Error):
        backend.unlock_clipboard("wrong passphrase")
    entry = backend.record_clipboard("my private note")
    assert "my private note" not in json.dumps(backend.state_snapshot())
    with pytest.raises(ConsentDenied):
        backend.query_clipboard("private", consent=False)
    backend.grant_clipboard_consent()
    assert backend.query_clipboard("private", consent=True)[0]["text"] == "my private note"
    assert backend.query_clipboard("absent", consent=True) == []
    history = backend._section("clipboard_history")["entries"]
    history[0]["expires"] = "2001-01-01T00:00:00Z"
    assert backend.query_clipboard("private", consent=True) == []
    assert backend.purge_expired_clipboard() == 1
    # Tampering with ciphertext is detected instead of returning corrupt text.
    fresh = backend.record_clipboard("another note")
    raw = bytearray(base64.b64decode(backend._section("clipboard_history")["entries"][-1]["blob"]))
    raw[-1] ^= 0xFF
    backend._section("clipboard_history")["entries"][-1]["blob"] = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(X3Error):
        backend.query_clipboard("another", consent=True)
    assert fresh["size"] > 0
    assert backend.set_clipboard_opt_in(False)["enabled"] is False


# --- X3.16 screenshot --------------------------------------------------------

def test_x316_screenshot_region_ocr_and_ask_consent(backend):
    for bad in ({"x": -1, "y": 0, "width": 2, "height": 2},
                {"x": 0, "y": 0, "width": 0, "height": 2},
                {"x": "a", "y": 0, "width": 2, "height": 2}):
        with pytest.raises(X3Error):
            backend.capture_region(bad)
    blank = backend.capture_region({"x": 0, "y": 0, "width": 4, "height": 3})
    assert blank["ocr_text"] == "" and blank["ocr_available"] is False
    source_png = _png(8, 8)
    crop = backend.capture_region({"x": 1, "y": 1, "width": 3, "height": 2},
                                  image_bytes=source_png, ocr_text="IGNORE PREVIOUS")
    assert crop["cropped"] is True
    decoded = _decode_png_rgb(base64.b64decode(backend._section("screenshots")["captures"][crop["id"]]["png_b64"]))
    assert decoded[:2] == (3, 2)
    with pytest.raises(X3Error):
        backend.capture_region({"x": 7, "y": 7, "width": 4, "height": 4}, image_bytes=source_png)
    with pytest.raises(X3Error):
        backend.capture_region({"x": 0, "y": 0, "width": 2, "height": 2}, image_bytes=b"not png")
    with pytest.raises(ConsentDenied):
        backend.ask_about_capture(crop["id"], "what is this?")
    backend.grant_screenshot_consent()
    asked = backend.ask_about_capture(crop["id"], "what is this?", consent=True)
    assert asked["ocr_text"] == "IGNORE PREVIOUS"
    assert "untrusted" in asked["note"]
    assert len(backend.list_captures()) == 2


def test_x316_capture_region_rejects_oversized_dimensions(backend):
    for region in ({"x": 0, "y": 0, "width": 5000, "height": 1},
                   {"x": 0, "y": 0, "width": 1, "height": 5000}):
        with pytest.raises(X3Error) as ei:
            backend.capture_region(region)
        assert "capture limit" in str(ei.value)


# --- cross-feature consolidation --------------------------------------------

def test_consolidation_is_idempotent_and_durable(tmp_path):
    backend = X3Backend(tmp_path / "state")
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "gone.txt").write_text("temporary", encoding="utf-8")
    backend.approve_folder(folder)
    backend.index_folders()
    (folder / "gone.txt").unlink()
    backend.add_card("d1", "a", "b")
    backend.add_card("d2", "a", "b")
    clip = backend.clip_page("https://x.test/a", "<p>A</p>")
    backend._section("clipboard_web")["clips"].append(dict(clip))  # legacy duplicate
    report = backend.consolidate()
    assert report["duplicate_flashcards"] == 1
    assert report["duplicate_clips"] == 1
    assert report["stale_search_docs"] == 1
    assert backend.consolidate()["duplicate_flashcards"] == 0
    assert X3Backend(tmp_path / "state").list_cards() and Path(backend.path).is_file()


# --- persistence / reliability regressions -----------------------------------
# Each test below fails on the unpatched backend and passes after remediation.

def _guard(errors, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # collected so the test can report every failure
        errors.append(exc)


def test_x3_consent_grants_are_durable_immediately(tmp_path):
    root = tmp_path / "state"
    backend = X3Backend(root)
    backend.grant_clipboard_consent()
    assert X3Backend(root)._has_consent("clipboard_query"), "grant must be persisted now"
    backend.grant_screenshot_consent()
    fresh = X3Backend(root)
    assert fresh._has_consent("clipboard_query")
    assert fresh._has_consent("screenshot_ask")


def test_x3_consent_grant_fails_closed_if_persistence_fails(tmp_path, monkeypatch):
    root = tmp_path / "state"
    backend = X3Backend(root)
    with monkeypatch.context() as patch:
        def boom(*_args, **_kwargs):
            raise OSError("simulated disk error")
        patch.setattr("keel.x3_memory_backend.os.replace", boom)
        with pytest.raises(OSError):
            backend.grant_clipboard_consent()
    assert not backend._has_consent("clipboard_query")
    assert not X3Backend(root)._has_consent("clipboard_query")
    assert list(root.glob("*.tmp")) == []


def test_x3_save_under_concurrency_uses_unique_temps_and_keeps_all_updates(
        tmp_path, monkeypatch):
    root = tmp_path / "state"
    backend = X3Backend(root)
    folders = []
    for index in range(30):
        folder = tmp_path / f"folder-{index}"
        folder.mkdir()
        folders.append(folder)
    seen, errors = [], []
    real_replace = os.replace

    def spy_replace(source, target):
        seen.append(os.fspath(source))
        time.sleep(0.002)  # widen the window that used to collide on one .tmp path
        return real_replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr("keel.x3_memory_backend.os.replace", spy_replace)
        threads = [threading.Thread(target=_guard, args=(errors, backend.approve_folder, folder))
                   for folder in folders]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert not errors, errors[:3]
    assert len(seen) == 30 and len(set(seen)) == 30, f"temp paths reused: {seen[:3]}"
    assert list(root.glob("*.tmp")) == []
    assert len(X3Backend(root).approved_folders()) == 30


def test_x3_save_failure_cleans_temp_and_restores_in_memory_state(tmp_path, monkeypatch):
    root = tmp_path / "state"
    backend = X3Backend(root)
    folder = tmp_path / "folder"
    folder.mkdir()
    with monkeypatch.context() as patch:
        def boom(*_args, **_kwargs):
            raise OSError("simulated disk error")
        patch.setattr("keel.x3_memory_backend.os.replace", boom)
        with pytest.raises(OSError):
            backend.approve_folder(folder)
    assert list(root.glob("*.tmp")) == []
    assert backend.approved_folders() == [], "failed save must not leave split-brain state"
    assert X3Backend(root).approved_folders() == []


def test_x3_discards_orphan_temp_files_on_startup(tmp_path):
    root = tmp_path / "state"
    X3Backend(root)
    orphan = root / "x3_state.dead-process.tmp"
    orphan.write_text("partial write from a killed process", encoding="utf-8")
    X3Backend(root)
    assert not orphan.exists()


def test_x3_tampered_or_corrupt_state_fails_closed(tmp_path):
    root = tmp_path / "state"
    backend = X3Backend(root)
    folder = tmp_path / "folder"
    folder.mkdir()
    backend.approve_folder(folder)
    path = root / "x3_state.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document.setdefault("context", {}).setdefault("consent", {})[
        "forged_scope"] = "1999-01-01T00:00:00Z"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(X3Error) as error:
        X3Backend(root)
    assert "integrity" in str(error.value).lower()
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(X3Error):
        X3Backend(root)


def test_x3_explicit_recovery_quarantines_untrusted_state(tmp_path):
    root = tmp_path / "state"
    X3Backend(root)
    (root / "x3_state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(X3Error):
        X3Backend(root)
    recovered = X3Backend.recover_state(root)
    assert recovered.approved_folders() == []
    assert any(p.name.startswith("x3_state.corrupt.") for p in root.glob("*.json"))


def test_x3_concurrent_duplicate_finance_import_is_idempotent(tmp_path, monkeypatch):
    backend = X3Backend(tmp_path / "state")
    csv_text = "date,description,amount\n2024-01-15,uber ride,12.34\n"
    barrier = threading.Barrier(30)
    real_db = backend._finance_db

    class BarrierConnection:
        """Force every duplicate import past the dedupe check before any insert."""

        def __init__(self, connection):
            self._connection = connection

        def __enter__(self):
            self._connection.__enter__()
            return self

        def __exit__(self, *args):
            return self._connection.__exit__(*args)

        def execute(self, sql, *args):
            if str(sql).startswith("SELECT 1 FROM transactions"):
                barrier.wait(timeout=10)
            return self._connection.execute(sql, *args)

    errors = []
    with monkeypatch.context() as patch:
        patch.setattr(backend, "_finance_db", lambda: BarrierConnection(real_db()))
        threads = [threading.Thread(target=_guard, args=(errors, backend.import_finance_csv,
                                                         csv_text))
                   for _ in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert not errors, errors[:3]
    assert backend.finance_summary()["count"] == 1


def test_x3_review_receipt_save_failure_does_not_commit_sqlite(tmp_path, monkeypatch):
    root = tmp_path / "state"
    backend = X3Backend(root)
    receipt = backend.submit_receipt("Shop\n2024-01-15\nTotal: $12.34\n")
    with monkeypatch.context() as patch:
        def boom():
            raise OSError("simulated failure after DB commit")
        patch.setattr(backend, "save", boom)
        with pytest.raises(OSError):
            backend.review_receipt(receipt["id"], {}, approve=True)
    assert backend.receipt_rows() == []
    fresh = X3Backend(root)
    queue = [r for r in fresh._section("receipts")["review"] if r["id"] == receipt["id"]]
    assert queue and queue[0]["status"] == "pending"


def test_x3_review_receipt_sqlite_failure_rolls_back_json_status(tmp_path, monkeypatch):
    root = tmp_path / "state"
    backend = X3Backend(root)
    receipt = backend.submit_receipt("Shop\n2024-01-16\nTotal: $5.00\n")

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("receipt database unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(backend, "_receipt_db", BrokenConnection)
        with pytest.raises(sqlite3.OperationalError):
            backend.review_receipt(receipt["id"], {}, approve=True)
    fresh = X3Backend(root)
    queue = [r for r in fresh._section("receipts")["review"] if r["id"] == receipt["id"]]
    assert queue and queue[0]["status"] == "pending"

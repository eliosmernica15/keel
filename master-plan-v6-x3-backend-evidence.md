# Master Plan v6 — X3.* Backend Evidence (agent/b1-x3)

- **Baseline:** `982335d` (`Add remaining-backend feature analysis (430 not-started rows classified by prefix)`)
- **Worktree / branch:** `C:\Users\Admin\.local\share\opencode\worktree\backend\b1-x3` / `agent/b1-x3`
- **Rows read in full:** all 16 `X3.1`–`X3.16` `not_started` entries in `PLAN-INDEX.json`
  (lines 18134–18487), cross-checked against `REMAINING-BACKEND-ANALYSIS.txt` and
  `keel/docs/plan-sources/extracted/addendum3.json`.
- **Owned files (only these three):**
  - `keel/src/keel/x3_memory_backend.py`
  - `keel/tests/test_x3_memory_backend.py`
  - this evidence document

## Interpretation of "memory / context / consolidation"

`X3.*` is Addendum 3 section C, *Cowork and personal-productivity extras*; the
rows are not the generic memory subsystem. The backend is therefore implemented
as a local **memory/context/consolidation layer for these productivity stores**:

- **memory** — durable JSON state under `state_root/x3_state.json` (atomic
  replace), plus local SQLite tables for receipts and finance rows;
- **context** — an explicit allow-list of approved folders, recorded consent
  entries, provenance/timestamps on stored items, and per-feature opt-in flags;
- **consolidation** — `X3Backend.consolidate()` de-duplicates flashcards and
  clipped pages, removes duplicate feed entries, expires clipboard history and
  prunes index entries whose source file is gone; additionally SM-2 review
  reschedules cards, the organiser keeps an undo journal, and safe-delete uses
  a restorable trash directory.

Everything is stdlib-only (`json`, `sqlite3`, `hashlib`, `hmac`, `csv`, `ast`,
`xml.etree`, `html.parser`, `zlib`, `struct`, `difflib`, `pathlib`, …). No
third-party imports, no network calls, no hosted services, no edits to the
registry or to any pre-existing source file.

## Per-ID classification

All 16 IDs are **implemented** as real local backend behaviour. Where the
standard library cannot supply an OS/hardware/ML capability, the sub-capability
is **excluded with reason** and replaced by an explicit injection point or
pre-extracted input; the module never fabricates results. "Adversarial tests"
below refers to `test_x3_memory_backend.py`.

| ID | PLAN-INDEX feature (abridged) | Classification | Backend implementation | Adversarial tests | Excluded sub-capabilities + reason |
|----|-------------------------------|----------------|------------------------|-------------------|------------------------------------|
| X3.1 | Local desktop search across user-approved folders (FTS5 + optional embeddings), tool + palette | **Implemented** | `approve_folder`, `revoke_folder`, `approved_folders`, `index_folders`, `search_documents`, `search_tool_descriptor`, `search_palette_entries`; TF/IDF-style lexical ranking with phrase boost, sanitised query terms, hashed local embedding boost | `test_x31_search_approved_folders_only_and_safety`, `test_x31_search_fts_syntax_and_binary_are_safe` | **FTS5 virtual table excluded**: availability is build-dependent; an equivalent in-process ranked index is used so results are deterministic and portable. **Hosted/vector-DB embeddings excluded**: `use_embeddings` uses a deterministic hashed local vector only; no external embedding service is contacted. Symlinks that escape an approved root and NUL/binary/oversized files are skipped, never indexed. |
| X3.2 | Document redaction (names, emails, IDs) with preview and verified-redacted PDF | **Implemented** | `detect_sensitive`, `redact_document`, `verify_redacted_pdf`, `_render_pdf` (minimal valid PDF 1.4 writer); longest-span-wins overlap resolution, full preview, PDF byte+stream verification | `test_x32_redaction_preview_pdf_and_verification`, `test_x32_verification_catches_leaked_secret` | **Third-party PDF layout/redaction libraries excluded** (licensing + stdlib-only): a minimal Helvetica PDF is written directly; text outside the redaction spans is omitted, so verification finds no original secret in raw bytes or decoded streams. |
| X3.3 | Receipt/invoice extractor to local CSV/SQLite (OCR + field parser) with review | **Implemented** | `parse_receipt`, `submit_receipt`, `review_receipt`, `receipt_rows`, `receipts_csv`; SQLite table `receipts.sqlite3`, confidence scoring, duplicate fingerprint, review queue | `test_x33_receipt_parse_review_commit_csv`, `test_x33_receipt_low_confidence_and_sql_safe` | **OCR engine excluded**: no OCR library is stdlib; the parser consumes locally supplied/OCR-provided text. Values are written with parameterised SQL, so `DROP TABLE`-style merchant text stays inert data. |
| X3.4 | Contract/document comparison: clause diff + plain-language summary with page citations | **Implemented** | `compare_contracts` with `_split_pages`, `_clauses_with_pages`, `SequenceMatcher`; added/removed/changed clauses, word-level insert/delete detail, page citations, template summary | `test_x34_contract_clause_diff_with_page_citations` | **Hosted language model summarisation excluded**: deterministic plain-language templates are generated locally; whitespace-only changes are suppressed as non-material. |
| X3.5 | Spreadsheet helper: explain formulas, find errors, pivots, charts; write to a copy, never in place by default | **Implemented** | `_FormulaEvaluator` (safe AST, A1 refs and ranges, SUM/AVERAGE/MIN/MAX/COUNT), `explain_formula`, `find_spreadsheet_errors`, `build_pivot`, `chart_svg`, `write_spreadsheet_results` | `test_x35_formula_pivot_chart_and_copy_only`, `test_x35_spreadsheet_errors_including_circular` | **Excel/XLSX renderer excluded** (no openpyxl): CSV + JSON sidecar output. `#DIV/0!`, `#REF!`, `#CIRCULAR!`, `#VALUE!`, `#NAME?` are detected. In-place writes require the explicit `OVERWRITE` token; default writes a copy and asserts the source bytes are unchanged. |
| X3.6 | File organiser rules engine (type/date/EXIF/name) with dry-run, preview, undo journal | **Implemented** | `plan_organization` (dry-run default), `_exif_date` (JPEG APP1 EXIF DateTimeOriginal via `struct`), `_apply_moves`, `undo_organization`, `organization_journals` | `test_x36_organizer_dry_run_apply_undo_and_collisions` | **EXIF for non-JPEG formats excluded**: parsed directly from JPEG APP1 with stdlib; rules requiring absent EXIF do not match. Destination templates are confined to the selected root; overwrites/collisions and `..` escapes raise instead of moving files. |
| X3.7 | Duplicate finder (hash + perceptual hash for images) with safe-delete to Keel trash | **Implemented** | `sha256_file`, `image_phash` (8×8 average hash over a stdlib PNG decoder with all five PNG filters), `phash_distance`, `find_duplicates`, `safe_delete`, `list_trash`, `restore_trash` | `test_x37_duplicates_phash_trash_restore` | **JPEG/WebP perceptual hashing excluded**: no stdlib decoder; those files still get exact SHA-256 matching and are reported with `phash=None`. Safe-delete moves into `state_root/trash` with SHA-256 metadata and supports restore; no permanent deletion. |
| X3.8 | Web clipper and read-later queue (save page as Markdown into vault) | **Implemented** | `_MarkdownClipper` (stdlib `HTMLParser`), `clip_page`, `read_later_queue`, `mark_clip_read`, `export_clips_to_vault` | `test_x38_clipper_sanitizes_html_and_exports_once` | **Network fetching excluded**: HTML is supplied by the caller (or a separately approved fetcher); only http(s) URLs are accepted. `<script>`, `<style>`, `<iframe>`, `<svg>` and `javascript:`/`data:` links are dropped; vault export never overwrites an existing note. |
| X3.9 | RSS/Atom digest agent (user feeds only) with scheduled summary | **Implemented** | `register_feed`, `ingest_feed` (RSS 2.0 + Atom, namespace-aware), `feed_digest`, `next_digest_due` | `test_x39_rss_user_feeds_digest_and_xxe_guard` | **Automatic network polling excluded**: the caller supplies feed XML; only user-registered http(s) feeds are accepted. DTD/ENTITY declarations are rejected (XXE/billion-laughs guard) and malformed XML raises. Digest marks items seen and computes the next interval-based run. |
| X3.10 | Flashcards and spaced repetition generated from notes, stored locally | **Implemented** | `generate_cards` (`Q:`/`A:`, `term :: definition`, `{{c1::…}}` cloze), `add_card`, `list_cards`, `review_card` (SM-2), `due_cards`, `consolidate_cards` | `test_x310_generate_review_sm2_and_consolidate` | **LLM card generation excluded**: deterministic parsing of supplied notes; no model call. Quality must be an integer 0–5; duplicates within a deck are rejected at insert and cross-deck duplicates are removed by consolidation. |
| X3.11 | Study/tutor mode (Socratic, quiz, explain-back) as bundled persona + skills | **Implemented** | `tutor_session`, `tutor_next_prompt`, `tutor_answer`, `tutor_status`, `tutor_persona_bundle` | `test_x311_tutor_modes_no_answer_leak` | **Hosted tutor model excluded**: bundled persona/skill descriptors and deterministic turn-taking only. Socratic mode withholds the answer unless `reveal=True`; invalid modes are rejected. |
| X3.12 | Writing coach with local grammar/style checking; licence check before bundling | **Implemented** | `check_writing` (offset-bearing heuristics: typos, repeated words, spacing, passive voice, capitalisation, long sentences, punctuation), `enable_third_party_checker`, `third_party_status` | `test_x312_writing_heuristics_and_license_gate` | **Third-party grammar checker is NOT bundled by default**: enabling one requires explicit `license_accepted=True`, an approved OSI-style licence id, and an already-local file. Unapproved licences (e.g. GPL) are refused rather than vendored. |
| X3.13 | Personal CRM/contacts notes in vault with follow-up reminders | **Implemented** | `add_contact`, `update_contact`, `list_contacts`, `due_followups`, `snooze_followup`, `export_contacts_to_vault` | `test_x313_crm_followups_and_vault_sanitization` | **Cloud sync/email dispatch excluded**: all data is local; reminders are computed dates, not sent messages. Invalid dates and duplicate contacts are rejected; YAML front-matter delimiters in notes are escaped on vault export. |
| X3.14 | Local finance CSV import and categorization (no bank connections) | **Implemented** | `_finance_db` (SQLite), `import_finance_csv` (BOM/header aliases, dedupe, keyword categorisation), `finance_summary`, `export_finance_csv` | `test_x314_finance_csv_import_categorize_and_reject_network` | **Bank/aggregator connections explicitly excluded**: any `http(s)/ftp` source is rejected; only locally supplied CSV is imported. Malformed rows are reported with line numbers, duplicates skipped, and all inserts are parameterised. |
| X3.15 | Clipboard history (opt-in, encrypted, auto-expire) queryable with consent | **Implemented** | `set_clipboard_opt_in`, `set_clipboard_ttl`, `unlock_clipboard`, `record_clipboard`, `query_clipboard`, `grant_clipboard_consent`, `purge_expired_clipboard`, `clipboard_status`; PBKDF2-HMAC-SHA256 key, HMAC-CTR keystream, encrypt-then-HMAC tag | `test_x315_clipboard_optin_consent_encryption_expiry_tamper` | **OS clipboard capture excluded**: the caller supplies the text; recording is opt-in and the passphrase is held only in process memory (never persisted). Agent reads require both recorded owner consent and `consent=True`; expired entries are skipped, tampering raises an integrity error, and plaintext does not appear in the state file. |
| X3.16 | Screenshot region capture with OCR and "ask about this" action | **Implemented** | `capture_region` (region validation, stdlib PNG decode/crop/re-encode, blank PNG when no image supplied), `ask_about_capture`, `grant_screenshot_consent`, `list_captures` | `test_x316_screenshot_region_ocr_and_ask_consent` | **Live screen capture and pixel OCR excluded**: no cross-platform screenshot/OCR in the stdlib. Callers pass PNG bytes and either `ocr_text` or an injected `ocr_provider`; with neither, OCR is empty and `ocr_available=False` rather than invented. "Ask about this" requires recorded consent plus `consent=True`, and labels OCR text as untrusted data. |

## Cross-cutting safety evidence

- Unapproved folders, files outside an approved root, `..` destination templates,
  destination collisions, and in-place spreadsheet overwrites all raise `X3Error`.
- Clipboard and screenshot-agent reads raise `ConsentDenied` without explicit
  consent (`grant_clipboard_consent` / `grant_screenshot_consent` plus a
  `consent=True` argument).
- SQLite writes are parameterised; feed XML DTDs are rejected; HTML is parsed
  with a tag/attribute allow-list style stripper; PDF verification searches both
  raw bytes and decompressed streams for leaked secrets.
- `X3Backend.consolidate()` is idempotent and was verified across stale search
  entries, duplicate cards, duplicate clips, duplicate feed entries and expired
  clipboard items (`test_consolidation_is_idempotent_and_durable`).

## Verification

Command (from the worktree root, as required):

```
python -c "import sys; sys.path.insert(0,'keel/src'); import pytest; sys.exit(pytest.main(['keel/tests/test_x3_memory_backend.py','-q']))"
```

Result: **21 passed** (Python 3.11.9, pytest 9.0.2; runs completed in ~6–16 s).

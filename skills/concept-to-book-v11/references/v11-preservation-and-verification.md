# V11 manuscript preservation and release verification

Use these two capabilities within the existing fifteen-step route and CD01–CD12 sequence. Preserve versions 1–10. Both are optional execution capabilities selected by the project's actual content and endpoint. Writing needs no Python, private vault, prior skill or publishing account. No new literary pass follows from this version.

## 1. Broader manuscript conversion and preservation

Before scaling import, inventory meaningful structure and choose an adapter that can preserve it. The normal Markdown and strict DOCX routes retain their existing contracts. For supported richer DOCX, opt in explicitly:

```text
python -B scripts/import_manuscript.py --input-root "C:/Books/Book/source" --input book.docx --metadata metadata.json --output-root "C:/Books/Book/imports" --output-dir import-001 --extended-docx --preflight
python -B scripts/import_manuscript.py --input-root "C:/Books/Book/source" --input book.docx --metadata metadata.json --output-root "C:/Books/Book/imports" --output-dir import-001 --extended-docx
```

The optional project runner accepts `"extended_docx": true` in its `import` object. This setting participates in input/helper/configuration fingerprints, planning and recovery. The default remains strict import. Existing section role reconciliation still applies, including the generated collected Endnotes section.

### Supported extension

- Native footnotes/endnotes with 1–100 nonempty ordinary paragraphs per note become collected endnotes. Preserve paragraph boundaries, bold/italic text, unique IDs, reference destinations and return navigation. Page-footnote placement is not reproduced. The original one-reference-per-note rule remains.
- Rectangular DOCX tables preserve row, cell and paragraph order. Support 1–100 rows, 1–8 columns, 1–20 nonempty paragraphs per cell, and an optional first header row with at least one data row. HTML/EPUB emit native table/thead/tbody/th/td structure; header cells have column scope. No header role is inferred from boldness. Equal-width PDF cells use actual supplied semantic fonts and selectable text. A complete PDF table must fit one text frame; oversized tables are refused, never truncated, shrunk or flattened. Row/cell source geometry and visual table styling are not reproduced.
- Whole-paragraph bookmarks become stable generated `bm-N` anchors. Support direct internal bookmark hyperlinks and simple cached `REF Bookmark` / `REF Bookmark \\h` fields with supported runs. Preserve the stored visible label and link to the corresponding target in HTML, EPUB and PDF. This does not recalculate field text. Missing/duplicate targets, partial/spanning bookmarks, complex fields, PAGEREF, automatic numbering and unsupported switches are refused.
- Direct supported external hyperlinks in the main document and semantic emphasis retain their existing treatment. External hyperlinks inside note parts require a different adapter with actual note-specific relationships; main-document relationship IDs are never borrowed to invent their destinations. External URIs are serialized, never fetched. Source text, cell text, note paragraphs and meaningful destinations are audited against actual outputs.

Merged/nested tables, empty cells/paragraphs within the supported table/note subset, arbitrary table styles, inherited semantic formatting, tracked changes, comments, drawings, complex numbering and other unsupported DOCX structures remain explicit refusals. Use a suitable available word-processing/conversion tool when the book needs those features; inspect its real output and record the new adapter's evidence. Do not remove content to get through the bounded adapter.

The original ZIP/XML limits and no-overwrite/source-preservation rules in [manuscript import](manuscript-import.md) remain. Metadata and package layout are not evidence of visual fidelity. Refused structures can be legitimate manuscript content; refusal is a capability boundary.

### Shared schema and verification

An extended endnote keeps `type`, `id` and aggregate `text`, plus `paragraphs`, an ordered array of 2–100 `{text, runs?}` objects. Aggregate text must equal paragraph text joined with newline. One-paragraph endnotes keep the existing shape; flat runs and multi-paragraph content cannot conflict.

A table is `{type: "table", header_rows: 0 or 1, rows: [[[paragraph, ...], cell, ...], row, ...]}`. Cell paragraphs use `{text, runs?, anchors?}`. Ordered text is retained; layout geometry is an explicit export policy. Ordinary paragraphs/headings and section metadata may carry `anchors`, an array of unique `bm-...` IDs. Runs add `target_id`, mutually exclusive with `href` and `note_id`. Every internal target resolves uniquely; generated anchors cannot collide with section/asset/font/note identities.

Use the existing builders and `audit_exports.py` on actual HTML, EPUB and PDF. The audit compares paragraph/cell/note order, semantic runs and link destinations as well as deterministic bytes. PDF checks actual extracted text, supplied font faces and actual link annotations. Actual rendering/reader behavior remains a further check. After editing a target's wording, editorially review its cached REF label; import does not update it for the author.

## 2. Repeatable reader and print-proof verification

Establish relevant formats, viewing conditions, required checks and stopping state in the foundation. Use `scripts/verify_release.py` after an actual export, alongside the existing exact-file EPUBCheck route. The helper creates a new evidence directory and `verification.json`; it never upgrades a book to approved or published.

```text
python -B scripts/verify_release.py --artifact "C:/Books/Book/releases/book.epub" --kind epub --settings verification-settings.json --output-dir "C:/Books/Book/checks/reader-001"
python -B scripts/verify_release.py --artifact "C:/Books/Book/releases/book.pdf" --kind pdf --settings print-verification.json --observations proof-observations.json --output-dir "C:/Books/Book/checks/print-001"
python -B scripts/verify_release.py --recheck "C:/Books/Book/checks/reader-001/verification.json"
```

Use `--previous-report` for a new verification after a change. The prior file remains intact; its identity is compared and no old observation is automatically promoted. Recheck verifies current artifact and retained evidence hashes. An explicit `--artifact` override allows relocation of the same exact release. HTML rechecks also verify its selected local resources. Supplied observation attachments must still exist with their recorded bytes; preserve or relocate them deliberately.

### Actual local reader execution

Browser settings select existing absolute paths for `node`, the `playwright-core` entry file in `playwright_module`, and a compatible Chromium `browser`. No dependency is installed or downloaded. `conditions` contains 1–4 `{width, height, text_scale}` objects: width 240–1600, height 320–1200, text scale 0.5–3. Defaults are illustrative harness conditions, not author preferences. `timeout_seconds` is 5–600. Optional dependencies apply only to this check.

The Node helper uses Playwright's public API, an isolated temporary browser context and a temporary loopback-only server. Exact EPUB resources are unpacked under bounded path/expansion checks; nav and unique spine documents are loaded in reading order. HTML follows its selected local document/resource references. Active content, external/missing stylesheets or CSS dependencies, and CSS imports are refused; an unavailable required style must not turn into a passing unstyled reading check. Other-origin requests are blocked and external hyperlinks are not fetched. It does not attach to the user's logged-in browser or change global settings.

For each selected condition, actually load every selected document, measure horizontal overflow/hidden content/image loading, apply the stated text scaling and capture a viewport PNG. Actually click local links, including table of contents, cross-references, note and return destinations; retain observed URLs and target existence/visibility. Record exact document/resource hashes, conditions, browser/Playwright versions, selected executable/module hashes, screenshots, stdout/stderr and failed routes. Bounds: at most 100 documents, 200 screenshots and 500 links per document. A timeout or unavailable browser remains blocked/unavailable, not passed. Screenshots cover the viewport, not every vertical page area.

This is a **Chromium reading harness of the exact EPUB content**, not a named EPUB application/device emulator. It establishes the interactions and measurements it actually ran. It does not establish literary comprehension, correct link meaning, adequate image descriptions, full visual acceptance, independent reader compatibility or assistive usability. For requested named readers/devices, use the available appropriate app/UI tool and record actual environment, settings, coverage and observations. If the app/device is unavailable, keep that requirement pending.

### Print-oriented execution and physical findings

PDF settings optionally select `expected_size_pt`, `tolerance_pt` (0–5), `require_embedded_fonts`, `require_text`, an existing `pdfinfo`, an existing `renderer` (pdftoppm), explicit `pages` and `dpi` (36–150). Defaults require embedded fonts and selectable text on every page; change these explicitly for a legitimate illustration-only/blank-page scope. `expected_size_pt` is an explicit project requirement, not a measurement invented by the checker.

Use pypdf to inspect every page's MediaBox/CropBox, selected dimensions, text presence and fonts, including form XObjects and Type0 descendants. With selected Poppler pdfinfo, perform an actual independent native parse and retain its version, command result and raw page-box report. With the selected renderer, create actual hash-bound previews for the stated pages through the existing renderer. Rendering leaves visual review pending. These checks are useful local preflight, not PDF/X, color/ink/bleed conformance or printer acceptance.

For a requested formal destination standard, select a genuinely suitable available validator and current applicable profile, run it on the exact file, and retain the raw report, tool/profile identity and observations. This helper does not automatically invoke a formal PDF/X validator. Record that coverage separately as `destination-validator`; unavailable validation remains pending. Do not choose an unrelated PDF/A profile and label it printer approval.

Physical-proof records identify the real edition/file, proof/print conditions, inspected pages/surfaces, observation, defect and disposition. Attach real photos/scans/reports where useful and permitted. Never create a synthetic physical approval. Contacting readers, ordering proofs or uploading files needs the user's applicable authorization. A skill-development fixture does not authorize those actions.

### Evidence state and correction loop

Use [verification settings](../assets/templates/verification-settings.json) and [proof observations](../assets/templates/proof-observations.json) as relevant starting shapes, replacing example values with actual project inputs. An observation record binds `artifact_sha256` to the exact file and carries unique checks with method (`human-reader`, `assistive-technology`, `physical-proof`, `destination-validator`), environment, actual coverage, concrete observation, status and limitations. Optional local attachments have relative paths and explicit SHA-256. These are supplied observations, not independent proof that a human action happened.

`required_checks` can select browser, pdf-local, pdf-independent, pdf-render and the four observation methods. Defaults require browser for HTML/EPUB or pdf-local for PDF. A missing required capability/observation is pending. Failed execution/observations remain failed. `completed-scoped-checks` means the recorded selected checks completed; the report always disclaims automatic approval. Do not use an empty requirement list to hide a missing requested check. A method-level status covers only its actual recorded scope, not all readers/pages/devices.

For a finding: identify the actual defect and goal → preserve protected content → repair the affected source/layout → rebuild dependent output → rerun invalidated checks and inspect relevant context. A changed file invalidates its prior exact-file record. Preserve unaffected edition evidence when its inputs remain current. Include verification reports and their evidence in the selected handoff, using `--recheck` before claiming currency; keep pending reader/physical/destination requirements visible.

## Source transparency and skill maintenance

The foundation, covers and original reference ledger remain in force. Original literature, vault craft notes, project canon, source XML, code/fonts, templates and actual validator profiles have different roles. Tell the user what was read and what it changed. This capability does not require rereading a private vault or turn a consulted guide into a reader citation.

The implementation contracts follow primary references: [Microsoft simple fields](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.simplefield), [Microsoft bookmarks](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.bookmarkstart), [W3C EPUB 3.3](https://www.w3.org/TR/epub-33/), and [Playwright context](https://playwright.dev/docs/api/class-browsercontext), [page](https://playwright.dev/docs/api/class-page) and [browser](https://playwright.dev/docs/api/class-browser) APIs. Check current destination standards when actually needed.

For consequential maintenance, run the bundled tests with relevant real tools required, inspect actual rendered artifacts and run the new independent cases. Use synthetic files only; record failed, skipped, unrun and actual coverage honestly outside this package. Retain historical fixtures unchanged. No original vault, predecessor package or private harness is a runtime dependency.

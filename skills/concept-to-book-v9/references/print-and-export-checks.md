# Interior proof PDF and actual-export audits

The optional print adapter produces a local **interior proof**. It does not claim PDF/X conformance, print platform acceptance, a printer cover wrap, bleed, CMYK/ICC output, accessible PDF, or manufacturing readiness. Review rendered pages before handoff. Use the original unchanged `edition.json` input contract; `formats` continues to describe HTML/EPUB. Print settings are a separate file.

## Commands and write boundary

```text
python scripts/build_print_edition.py --input-root INPUT --config edition.json --settings print-settings.json --output-root EXISTING-OUTSIDE-INPUT --output-dir NEW-RELEASE --preflight
python scripts/build_print_edition.py --input-root INPUT --config edition.json --settings print-settings.json --output-root EXISTING-OUTSIDE-INPUT --output-dir NEW-RELEASE
python scripts/audit_exports.py --input-root INPUT --config edition.json --release-root ACTUAL-READING-RELEASE
python scripts/audit_exports.py --input-root INPUT --config edition.json --settings print-settings.json --release-root ACTUAL-PRINT-RELEASE
```

Both roots must already exist. The output root must resolve outside the input root. The new release name is one safe directory component; an existing directory, symlink, reserved name or overwrite is refused. Input paths use relative POSIX components; parent traversal, absolute paths and resolved symlink escapes are refused by the shared `Inputs` reader. Originals are read only. A failure after output creation retains the new directory for inspection. Preflight validates source, dependencies, font/glyphs, image pixel decoding and full in-memory pagination/PDF parsing but creates no output directory or files.

Build success exits 0; refused builds exit 2. The auditor writes JSON to stdout, modifies no inputs/releases, and exits 0 only if all covered checks pass; errors exit 1. Audit current source files, not stale paired metadata records. A handoff should preserve the audit JSON, actual release directory and separately recorded manifest hash.

## Settings and restrictions

Copy `assets/templates/print-settings.json` alongside the explicit source. Supply your own authorized standalone TrueType `.ttf` under the input root and set `font.path` relative to that root. `embedding_authorized:true` is an explicit rights assertion; table flags are additionally checked. No proprietary font is bundled. OpenType/CFF, collections, restricted/no-subsetting outline flags and malformed font tables are refused. ReportLab embeds a subset with ToUnicode. All printable source/metadata/footer characters must exist in the face actually used. Glyph index zero (`.notdef`) and out-of-range indices fail even when a character appears in the cmap. `font.variants` optionally maps `italic`, `bold` and `bold_italic` to supplied relative `.ttf` paths. Each variant is rights-authorized by the containing `embedding_authorized:true` declaration and receives the same table/embedding/glyph checks. Any semantic face used by runs must be supplied; absent variants fail before output rather than flattening or simulating a face. Actual TrueType italic/weight metadata is checked, so a regular face relabeled as bold fails. Full font hashes are recorded; fonts are subset in PDF.

`schema_version` and `font` are required. Other omitted top-level settings take the disclosed defaults below. Nested margin/footer objects, if supplied, must include every listed key; unknown keys fail. The resolved settings, font source hash and dependency versions are saved in the manifest.

| Setting | Default | Meaning |
| --- | --- | --- |
| `trim_inches` | `[6,9]` | Width/height, 3–14 inches each; MediaBox and CropBox equal trim |
| `margins_inches` | top/bottom `.65`, inner `.7`, outer `.6` | Mirrored inner/outer margins; each .1–5 inches |
| `font_size_pt` | `11` | Body and caption type size, 6–30 pt |
| `leading_pt` | `15` | Body baseline spacing, 7–60 pt and at least 1.1 times body size |
| `heading_size_pt` | `16` | Section heading, 8–48 pt; leading 1.4 times size |
| `paragraph_gap_pt` | `6` | Space after paragraph/image/caption, 0–60 pt |
| `section_start` | `new_page` | `new_page`, `recto` (odd physical page), or `continuous` |
| `footer` | page_numbers `true`, font_size_pt `9`, offset_pt `20` | Centered physical page number; baseline offset from page bottom; must fit beneath frame |

Support is deliberately bounded: LTR Latin letters, numbers, punctuation and symbols using language bases en/fr/de/es/it/pt/nl. Paragraphs with structured emphasis/strong runs, nested headings, explicit scene breaks and PNG/JPEG image blocks only. No bidi/shaping, combining-mark sequences, precomposed ligatures, tables, lists, HTML, footnotes, discretionary hyphens or unbreakable words wider than the frame. Invalid/insufficient frames, missing glyphs/assets, unsupported blocks, decode failures and over 5,000 pages fail instead of silently degrading. Whitespace in paragraphs collapses to single spaces. There is no hyphenation or general paragraph widow/orphan control. Nested headings reserve their actual font-aware wrapped height, following gap and at least the first following paragraph line (or actual following image height/scene-break line). Consecutive nested headings reserve the same minimum as one group. If that measured minimum cannot fit a fresh text frame, the adapter refuses instead of leaving a heading isolated or splitting the heading. This is a bounded heading keep-with-next rule, not general paragraph pagination control. Semantic run boundaries preserve word joins. Section headings use `heading_size_pt`; nested heading level L uses max(body size, heading_size_pt − (L − 1)) with 1.4-times leading. Scene breaks paint `* * *` in source order. These visual cues do not create tagged/accessible PDF heading semantics.

Sections retain explicit front/body/back order. Section headings start per settings; no synthetic title page is inserted. A config front-cover asset is validated but omitted from this interior. Images retain aspect ratio, are centered, and scale down to the available frame without upscaling beyond one point per source pixel. A caption may continue on the following page. Source pixel dimensions and placement sizes are recorded; DPI suitability and color reproduction require separate review. Supported image modes are 1/L/LA/P/RGB/RGBA; CMYK JPEG is refused.

`build-manifest.json` records current source/settings/font hashes, resolved settings, dependency versions, PDF bytes/hash, trim, physical page count, section page ranges and image positions/source hashes. The manifest excludes its own hash. PDF Title/Author are source title/author; Subject stores identifier, catalog Lang stores language. Deterministic PDF timestamps are used for reproducibility; the source `modified` timestamp remains in manifest metadata, not a claimed PDF creation date. Defaults and limitations are never a printer acceptance statement.

## What the auditor actually checks

The auditor reads actual exported files, then parses actual HTML XML, EPUB ZIP/XML or PDF objects. It compares them to fresh current config/section/asset data. It additionally regenerates the supported deterministic adapter output and compares exact bytes; a forged manifest with unchanged hashes cannot hide changed output or changed sources.

HTML checks include visible title/author, each actual section text stream and image order, reading order, resources and exact image/font bytes. Independent model-derived checks compare actual inline `em`/`strong` character semantics, heading levels and scene-break sequence, separate from exact-byte regeneration. **HTML identifier audit is unsupported** because the inherited HTML adapter does not serialize the identifier. EPUB checks include package title/creator/identifier/language, actual section text, source asset bytes, spine/nav order, resources, XML and ZIP CRC.

PDF checks include actual extracted text and section order, Title/Author/Subject identifier/Lang, physical page numbers, page count, trim MediaBox/CropBox/no rotation, embedded TrueType font streams and ToUnicode, parsed actual embedded subset italic/bold face metadata, painted character/font-face/size order against source runs and heading sizes, actual image paint operations and Pillow-decoded RGB pixels/occurrence counts. It also compares current-source regenerated bytes and current placements/settings to manifest values. Text uses NFC and whitespace-collapse normalization only; case and punctuation remain significant. Text extraction cannot prove glyph positioning or visual quality. Original PNG/JPEG container bytes are not recoverable from PDF; source container hashes and deterministic regeneration complement actual decoded-pixel checks. Nested PDF form XObjects are outside this adapter audit and fail explicitly.

Dependency versions affect byte reproduction; use the recorded tested versions in `requirements-print.txt`. A byte mismatch can mean dependency drift and remains an explicit failed reproducibility check. No visual quality, accessibility, EPUBCheck, real reader/device or printer acceptance is inferred from a passing audit.

## Portable verification

`python -m unittest discover -s selftests -p test_production.py -v` runs real HTML/EPUB and PDF tests in temporary directories. Optional print dependencies are imported lazily. Set `BOOK_TEST_FONT` to an authorized TTF; otherwise tests select ReportLab's bundled Bitstream Vera and preserve its license alongside generated fixture inputs. Missing dependencies/font produce an explicit skip. A full print acceptance run must reject skips. No Windows-specific font path is hardcoded. The tests exercise actual exports, source changes, metadata/content/assets corruption, embedded font/geometry/image checks, deterministic output, preflight/no-write/preservation, distinct layouts/recto sections and refusal paths.

Semantic regression command: `python -B -m unittest discover -s selftests -p test_semantics.py -v`. It exercises actual formatted Markdown and DOCX through all formats, missing/fake face refusal, malformed structured runs, same-text HTML semantic changes and PDF Tf changes that remove emphasis. The audit detects these using actual parsed semantics as well as deterministic bytes. Digital construction still needs only Python standard library; this PDF-inclusive suite requires print dependencies.

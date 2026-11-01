# Bounded manuscript import

`scripts/import_manuscript.py` is a Python 3.12+ standard-library adapter for an explicitly selected bounded manuscript. It does not discover, repair, infer or rewrite manuscript content. Unsupported features cause refusal before output creation. Use another suitable adapter when the manuscript needs richer formatting; do not delete meaningful formatting merely to obtain a green result.

```text
python scripts/import_manuscript.py --input-root "C:/Books/Lantern/source" --input manuscript.md --metadata metadata.json --output-root "C:/Books/Lantern/imports" --output-dir import-001 --preflight
python scripts/import_manuscript.py --input-root "C:/Books/Lantern/source" --input manuscript.md --metadata metadata.json --output-root "C:/Books/Lantern/imports" --output-dir import-001
```

Both roots must exist. The output root must resolve outside the input root. Input and metadata paths use `/`, are relative to the input root, and cannot traverse outside it, including through symlinks. The output directory is a single new name; existing destinations are never overwritten or reused. Only the two selected files are read; no network, installation, original-source writes or deletion occurs. Files are bounded at 32 MiB each. DOCX has at most 1,000 members, at most 32 MiB per expanded member and 64 MiB total expansion. ZIP members are inspected in memory and never extracted. The tool is not a defense against a hostile concurrent filesystem actor.

`metadata.json` is exactly the reading builder's metadata object, not a complete edition configuration:

```json
{"title":"The Lantern","author":"Author Name","identifier":"urn:example:lantern","language":"en","modified":"2026-01-01T00:00:00Z"}
```

All five fields must be supplied as nonempty strings. The language uses the builder's simple BCP 47 shape and the timestamp must be a real UTC date/time. The importer does not invent a book title, author, ISBN, timestamp or missing prose. Duplicate JSON keys and extra fields are refused.

## Accepted manuscript subset

Markdown must be UTF-8 (optional BOM), with explicit ATX headings (`# Title` through `###### Title`) and paragraphs separated by blank lines. The first heading establishes the section boundary level: subsequent headings at that level or above begin new sections; deeper headings remain ordered heading blocks with their exact level. Each section records `heading_level`; a level-2 first heading therefore produces level-2 section titles. All sections default to `part: body`, `kind: chapter`. Supply the book title in metadata. Preamble text, sections without a paragraph, more than 500 sections and more than 10,000 blocks per section are refused. Heading jumps are retained, not repaired.

Inline `*emphasis*`, `**strong**` and `***combined emphasis and strong***` are supported in paragraphs and headings. Delimiters must be balanced, enclose nonempty text without edge whitespace, and occur outside words. Adjacent plain and formatted text retains source order. Nested delimiter patterns, underscore emphasis and ambiguous asterisks are refused. A standalone exact `***` or `---` line becomes an explicit `scene_break` block, independent of adjacent paragraph separators. The source spelling of the break is normalized to a semantic break.

Within a paragraph, Unicode, punctuation, spaces and line order are preserved. CRLF/CR become LF. Unicode separators such as U+2028 remain text. Blank separators, BOM and original line-ending bytes are not retained in edition JSON; the exact original file hash remains in the manifest. This is text preservation, not byte-for-byte serialization of the manuscript.

Links/images, footnotes, HTML, entities, fenced or indented code, tables, lists, block quotes, other rule spellings, escaping, trailing double-space breaks and ambiguous markup are conservatively refused with line locations. Unsupported literal markup characters (`_`, backticks, brackets, angle brackets, backslash, pipe, tilde) also require explicit resolution with another adapter. Setext headings and closing ATX hashes are unsupported. This intentionally small grammar can refuse harmless literal text rather than silently interpreting or flattening it.

DOCX must be an unencrypted WordprocessingML ZIP containing the main document and package parts. Supported body content consists of ordinary `w:p` paragraphs with `w:r/w:t` runs and direct optional `w:rPr/w:b` and `w:rPr/w:i` properties and optional `w:pStyle` values `Normal` or `Heading1`–`Heading6`. Text runs concatenate exactly in source order; direct bold, italic and combined properties are preserved as structured booleans. Explicit true/false, 1/0 and on/off values are accepted. Standalone plain `***` or `---` paragraphs become scene breaks; formatted break markers are refused. Empty paragraphs are structural separators. Empty headings are refused. Section page geometry is allowed and disclosed as layout not reproduced. Plain typographic defaults and named heading appearance are not reproduced; inherited normal/default semantic emphasis is refused.

Other direct run formatting (including underline), custom styles, character style definitions other than `DefaultParagraphFont`, lists, tabs/breaks, tables, fields, hyperlinks, tracked insertions/deletions, drawings, embedded media/objects, notes, comments, headers/footers and unknown content parts are refused. The common plain DOCX package metadata/settings/font/theme parts are allowed; their presence does not establish visual fidelity. Many normal word-processor files include unsupported style definitions or paragraph properties and will be refused. The importer does not flatten such files. It supports the transitional WordprocessingML namespace, not Strict DOCX. DTD/entity declarations in parsed XML are refused. External relationships are reported and never followed.

## Outputs, evidence and handoff

Successful import writes `edition.json`, `sections/section-0001.json` onward, and `import-manifest.json`. The configuration uses schema 1, deterministic `edition_id: imported-edition`, HTML and EPUB formats, no assets and sequential section IDs. It is compatible with [the reading builder](production-adapters.md). The edition ID is a technical default, not an invented manuscript title. Review and explicitly prepare actual front/back matter roles, kind labels, assets or other edition choices before building when required; the default import contains body matter only.

The manifest records exact selected-source and metadata SHA-256/byte counts; section reading order, paragraph/character counts; one coverage record per source heading, paragraph or scene break; Markdown line ranges or DOCX paragraph locators; detected unsupported features (empty on success); output hashes; normalization/coverage policy and honest limitations. Coverage does not certify that the author intended every source element to be included. Blank paragraphs and allowed package/layout data are explicitly excluded. The manifest excludes its own hash; stdout supplies it. Identical inputs produce identical output bytes, including the manifest, independent of chosen new destination name.

Preflight validates the actual inputs and returns the report as stdout JSON with `status: preflight_passed_no_outputs_written`; it writes nothing. Success returns exit 0. Refusal/failure returns exit 2, stdout JSON with `status: import_refused` and `error`, plus concise stderr. Feature refusals include `unsupported_features` entries with concrete `feature` and `location`. A write failure can leave a new incomplete directory, identified in the report; preserve it for inspection and choose another new destination after resolving the failure. Malformed CLI usage is handled by argparse with exit 2 and stderr usage.

Review the manifest and compare the selected manuscript to imported sections before treating them as the authoritative edition source. Then run the reading builder using the imported directory as `--input-root` and `edition.json` as `--config`, with a separate existing output root. Import is not visual review, narrative review, EPUB validation, printer readiness or external platform acceptance.

## Portable tests

```text
python -B -m unittest discover -s selftests -p test_import.py -v
```

Tests generate actual synthetic Markdown and DOCX files in temporary directories and invoke the CLI in subprocesses. They cover text/order/hash preservation, deterministic outputs, refusal locations, preflight/no writes, unchanged sources/unrelated outputs, no overwrite, traversal, ZIP expansion limits, DTDs, metadata and XML text validation. The symlink escape case skips with a stated reason where the OS/user cannot create symlinks. They require neither private manuscripts, prior-version packages nor third-party Python libraries.

## Semantic JSON extension (schema 1)

Legacy `{ "type": "paragraph", "text": "Plain prose." }` remains valid. Paragraphs and heading blocks may additionally contain `runs`, an ordered nonempty array of exactly `{ "text": "text fragment", "emphasis": false, "strong": true }` objects. Run text must concatenate exactly to the containing `text`; booleans are required, unknown fields fail, and run text is XML-safe content, never executable markup. A run can have both booleans true. Runs do not carry arbitrary styling.

A nested heading is `{ "type": "heading", "level": 2, "text": "Nested heading" }`, optionally with runs. Levels are integers 1–6. A scene break is exactly `{ "type": "scene_break" }`. Sections optionally add `heading_level` (default 1) and `title_runs` (the same run array for `title`). The reading adapter emits escaped `em`/`strong`, actual heading elements and `hr`. Print uses real supplied semantic font variants and visible `* * *` breaks; it does not produce accessible PDF structure tags.

Run `python -B -m unittest discover -s selftests -p test_semantics.py -v` for actual Markdown and plain DOCX import through HTML, EPUB and PDF, preservation assertions and same-text formatting corruption tests. This suite requires the optional print dependencies. Its synthetic Vera copies rebuild historical bundled table checksums with ReportLab TTFontMaker, retain real glyph/face data and preserve the Bitstream license; no installed font is modified.

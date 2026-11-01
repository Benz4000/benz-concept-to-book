# Practical reading-edition adapters

Use `scripts/build_reading_edition.py` when the requested endpoint includes local reading files and the source fits this contract. It produces an actual single-document HTML reading proof, an actual EPUB 3 container, or both. It does not adapt arbitrary manuscripts automatically. For supported plain Markdown/DOCX, use the separate [manuscript importer](manuscript-import.md), reconcile its roles/order and verify conversion before treating section inputs as the book source. Use [print-and-export-checks.md](print-and-export-checks.md) for the separate PDF adapter and actual-file auditor. This reference's PDF limitations apply to the reading adapter only.

The adapter requires Python 3.10 or later and its standard library. No installation, network access, external service, PDF library, or publishing account is used. An unavailable interpreter is a capability gap, not a reason to claim a build. Other capable book-building tools remain valid choices when the project needs richer inputs or output formats.

## Capability preflight and commands

Create an input directory and a separate, existing release parent. From the skill directory, replace these example paths with the designated project paths:

```text
python scripts/build_reading_edition.py --input-root "C:/Books/Lantern/input" --config edition.json --output-root "C:/Books/Lantern/releases" --output-dir proof-001 --preflight
python scripts/build_reading_edition.py --input-root "C:/Books/Lantern/input" --config edition.json --output-root "C:/Books/Lantern/releases" --output-dir proof-001
```

Preflight reads and validates actual inputs, reports hashes, stored image dimensions, font inspection and tool capabilities, and writes nothing. A successful build creates only the named new directory. Exit code `0` means the requested operation completed; `2` means it was refused or failed. The final stdout identifies the output directory and manifest hash. Error details go to stderr. If writing fails after directory creation, the incomplete new directory is retained for inspection and is not a valid release.

| Capability | Implemented evidence | Remaining limit |
|---|---|---|
| HTML | Actual local document, contents links, ordered sections, escaped paragraphs, image alternatives, supplied assets and CSS | Browser, viewport, zoom, keyboard and visual acceptance require actual inspection |
| EPUB | Actual ZIP/OCF package, metadata, manifest, navigation document, spine, content documents, cover and assets | ZIP/XML checks are not EPUBCheck or a reading-system conformance result |
| Images | PNG chunk boundaries/CRCs and stored dimensions; baseline/extended/progressive JPEG marker dimensions; exact source bytes retained | No pixel decoding, orientation normalization, visual quality, effective print PPI or color-profile assessment |
| Fonts | Optional whole standalone TTF/OTF copied and embedded; table bounds and OS/2 embedding flags inspected | No shaping, glyph-coverage, rendering, licensing adjudication or obfuscation; fallback font appearance is not pinned |
| Front cover | Supplied PNG/JPEG appears in HTML and the EPUB spine; EPUB manifest marks its image as `cover-image` | Does not design a title treatment, repair artwork, produce a printer wrap, or obtain physical cover geometry |
| PDF/print | Explicitly unsupported by this adapter | Use a suitable actual layout/export tool and current printer inputs for requested print files |
| External acceptance | No external operation | No upload, platform receipt, proof approval, manufacturing or distribution |

`epubcheck` is detected on PATH only. Availability does not execute it or grant a pass. Unavailable capabilities remain reported even if the local build succeeds.

## Explicit input contract

Start with `assets/templates/edition-build.json`. It contains placeholders and paths to files that must actually exist; it is not a finished or immediately runnable book. The root object has exactly these supported fields:

| Field | Contract |
|---|---|
| `schema_version` | Integer `1` |
| `edition_id` | Safe stable ID; controls the EPUB filename |
| `metadata` | Exactly `title`, `author`, `identifier`, `language`, `modified`; nonempty strings |
| `metadata.identifier` | Supplied stable edition identifier; the adapter does not assign or certify an ISBN |
| `metadata.language` | Simple BCP 47 shaped language tag such as `en` or `en-GB`; no full registry validation |
| `metadata.modified` | Explicit valid UTC `YYYY-MM-DDTHH:MM:SSZ`; update when the edition changes, never inferred from the clock |
| `formats` | `['html']`, `['epub']` or both, expressed with JSON double quotes |
| `assets` | Up to 100 explicit PNG/JPEG image objects with `id`, `path`, `role`, `alt` |
| `cover_image` | Optional selected asset ID, or `null`; its role must be `front-cover` |
| `font` | Optional object described below, or `null` |
| `sections` | 1–500 objects in the exact intended reading order, each with `id`, `part`, `kind`, `title`, `source` |

`part` is `front`, `body` or `back`. Their overall sequence must be front → body → back, with at least one body section. Within a part, the supplied order is preserved. `kind` is a descriptive nonempty string such as `recap`, `chapter`, `afterword`, `sources` or `guide`; it is not an automatic narrative or spoiler check. Include all required support sections as actual files. Missing required material cannot be inferred from a schema-valid inventory.

IDs start with a lowercase letter, then contain up to 63 lowercase letters, digits, hyphens or underscores. Section, image and font IDs must be unique. `book-id`, `cover`, `nav`, `package`, `style` and Windows device names are reserved. `book-id` belongs to the EPUB package identifier; it cannot be reused by a supplied section, image or font. Output filenames derive from these IDs; original source paths remain in the manifest. All input paths use `/` relative to the input root. Absolute paths, `..`, backslashes and links resolving outside that root are refused. Each input is limited to 32 MiB; the combined input snapshot is limited to 128 MiB.

Each section source is a UTF-8 JSON file with exactly a `blocks` array containing 1–10,000 objects. Supported blocks are plain paragraphs and explicit references to supplied images:

```json
{
  "blocks": [
    {"type": "paragraph", "text": "Mara waited until the lantern stopped swaying."},
    {"type": "image", "asset_id": "chapter-art", "caption": "The crossing at dusk."},
    {"type": "paragraph", "text": "Then she wrote both names in the ledger."}
  ]
}
```

Image blocks require `type` and `asset_id`; `caption` is optional. Images require a meaningful nonempty `alt` string in the asset inventory and a role of `front-cover`, `illustration`, `map` or `portrait`. Exactly one `front-cover` asset may be selected; it is inserted first and must not also appear as a body block. Every listed image must be used. Decorative empty alternatives, raw HTML, Markdown interpretation, inline emphasis, tables, footnotes, clickable citations and automatic layout of a source DOCX/PDF are outside this small adapter's contract. Text is escaped, not executed as HTML.

Use `font: null` for a generic serif fallback. To pin an actual supplied font file:

```json
{"id": "reading-font", "path": "fonts/reading.ttf", "embedding_authorized": true}
```

That object is the value of `font`. Supply an appropriate license/permission record in the project. `embedding_authorized` records the caller's authorization; it is not independent legal verification. Restricted-license and bitmap-only OS/2 flags are refused. Whole font bytes are retained, including embedded notices; no subsetting is done. Unsupported collections and web-font containers require another adapter.

## Sequence, cover preparation and checks

1. Recover the authoritative manuscript and the included-section inventory. Convert the actual selected text into section JSON without quietly omitting supporting material. Inspect the conversion and inventory against the requested edition.
2. Supply the exact front-cover and interior image files with their roles and alternatives. The adapter does not infer a full cover from an interior illustration. Physical trim, bleed, wrap/spine width, barcode clearance, jacket flaps and printer templates remain separate unresolved facts when needed.
3. Run preflight. Resolve invalid inputs, missing resources and applicable font/image requirements before building. A stored pixel dimension does not establish sufficient resolution at an unspecified physical placement.
4. Build into a new release directory. The adapter inserts the selected front cover, then follows the explicit section list in both HTML and EPUB navigation/spine. It checks generated XML, applicable order/navigation, manifested resource presence and ZIP integrity, then verifies each written output hash.
5. Open the actual HTML and EPUB in suitable readers. Follow [format-reading-checks.md](format-reading-checks.md) for applicable layout, accessibility and reading review. Record exact filenames/hashes, reader/version, scope, observed defects and unresolved limits. Run EPUBCheck separately when available and appropriate; preserve its actual command and report.
6. Hand off the exact output package, its manifest hash, completed evidence, outstanding review and the supported state: **local reading files built; external acceptance unverified** unless later evidence establishes more.

## Reproducibility and preservation

The build manifest records exact source/configuration hashes and byte counts, section-source links, metadata, measured image information, font inspection, the adapter's own SHA-256, Python version, capability status, reading order and output hashes. It excludes its own hash to avoid a circular dependency; stdout reports that hash for the handoff record. Archive members have a fixed ZIP timestamp, stable order and no compression. The caller-supplied metadata timestamp is preserved. Manifest environment fields can differ across interpreters or PATH configurations; cross-environment identity is not asserted.

The output root must already exist outside the input root. `--output-dir` is a simple single new directory name beneath that resolved root. Existing files/directories are never reused, overwritten or deleted. Sources are read into a bounded snapshot before the build. The adapter does not scan for or replace other editions. It is a local workflow tool, not a defense against a hostile concurrent filesystem actor.

For a source change, select the affected edition, provide a new output directory and rebuild from the complete current input snapshot. This is a whole-edition rebuild, not an incremental patching system. Compare output/member hashes to identify unchanged assets and sections; preserve prior releases and unrelated editions. If the source-to-edition relationship is unknown, recover that dependency rather than guessing it from filenames.

The implementation was informed by selected sections of the official [W3C EPUB 3.3 Recommendation](https://www.w3.org/TR/epub-33/): OCF media type §4.3.3, package metadata §5.5.3/§5.5.5, manifest properties §5.6.2.1, and navigation §7.2. This is not a full specification audit or a conformance certification. See [integration-testing.md](integration-testing.md) for actual regression evidence and rerun instructions.

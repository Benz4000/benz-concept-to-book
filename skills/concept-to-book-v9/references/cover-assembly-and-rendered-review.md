# Flat paperback assembly and actual rendered review

These adapters create local proofs in new output directories. They do not modify sources, prior editions, prior review packets, or prior releases. They do not install dependencies, access the network, upload, publish, or assert printer acceptance, PDF/X compliance, color-managed output, jackets, hardcover cases, or barcode correctness. Install dependencies separately only if authorized; cover requires ReportLab, pypdf and Pillow, and rendering requires pypdf, Pillow and an existing `pdftoppm` executable.

## Commands and Python APIs

```text
python -B scripts/build_cover.py --config /absolute/inputs/cover-build.json --output-dir /absolute/new-cover
python -B scripts/render_review.py --config /absolute/inputs/render-review.json --output-dir /absolute/new-review
```

Python APIs are `build_cover.build_cover(config_path, output_dir)` and `render_review.render_review(config_path, output_dir)`, returning their manifest dictionaries. `build_cover.validate_cover_pair(manifest_path, interior_pdf=None)` and `render_review.validate_review(manifest_path, pdf_path=None)` return the validated manifest or raise `BuildError`. Both validators reopen actual files; they do not trust a stale status field. The exact interior SHA-256 changing invalidates a cover pair even when its page count stays constant. The review validator also checks every saved current, prior, and difference preview hash. The manifest is integrity evidence, not a digital signature or proof of who reviewed it.

Config and content paths are local. Asset/PDF/template paths are forward-slash relative paths contained within the config directory; traversal, absolute asset paths and symlink escapes are rejected through the shared Inputs contract. `renderer` and `previous_manifest` are deliberate exceptions: the renderer may be an explicit executable path or executable name on PATH; the previous manifest may be absolute or relative to the config directory. Output must be a nonexistent directory outside, and not containing, the config directory. Keep config/inputs and new outputs as siblings. Existing output paths are never overwritten. On execution failure a partial new directory may remain; no failed run is a completed proof.

## Cover config and explicit supplied geometry

Start with `assets/templates/cover-build.json`. Its zero boxes, zero page count and placeholder identity are intentionally invalid: supply actual facts. `interior` requires `path`, exact `sha256`, integer `page_count` and nonempty `edition`. The supplied template JSON requires:

```json
{
  "schema_version": 1,
  "units": "in",
  "edition": "paperback-proof-example",
  "page_count": 200,
  "source": "Explicit synthetic example only; replace with supplied template identity",
  "sheet": [12.75, 9.25],
  "panels": {
    "back": {"trim": [0.125, 0.125, 6, 9], "bleed": [0, 0, 6.25, 9.25], "safe": [0.375, 0.375, 5.5, 8.5]},
    "spine": {"trim": [6.125, 0.125, 0.5, 9], "bleed": [6.125, 0, 0.5, 9.25], "safe": [6.225, 0.375, 0.3, 8.5]},
    "front": {"trim": [6.625, 0.125, 6, 9], "bleed": [6.5, 0, 6.25, 9.25], "safe": [6.875, 0.375, 5.5, 8.5]}
  }
}
```

All rectangles are `[x,y,width,height]` with lower-left origin. Units must explicitly be `pt`, `in`, or `mm`; point conversion is only unit conversion. Page count never drives a spine formula. The template's exact source bytes/hash and declared source identity are recorded. Every actual interior TrimBox must match the front/back trim dimensions with zero page rotation. All three trim panels must be horizontally adjacent, equal in height, with equal back/front width. Each safe area must fit its trim, each trim its declared bleed area, and every bleed area the sheet. Nonflat, rotated, unequal, missing or unsupported geometry is rejected. Sheet dimensions cannot exceed 3600 pt (50 inches). The PDF's single page MediaBox/TrimBox represent the whole wrap sheet; panel cut/bleed/safe rectangles remain explicit in layout evidence, not separate PDF pages or misleading single-panel TrimBoxes.

Supply 1–8 standalone embedding-authorized TTF fonts, 2–12 PNG/JPEG images, and 1–30 real text blocks. Images require explicit `usage_authorized:true`, `role:art|barcode`, a panel and box. At least one art image must occupy the front; exactly one supplied barcode image must fit the back safe area. The adapter places that image after all artwork so later artwork cannot hide it; it does not decode or verify its encoded ISBN. Art fits its panel bleed area. Images must be static RGB/RGBA/L, at most 40 million pixels; aspect ratio must match its box within 2%, so prepare crops externally. Placement is explicit; no automatic crop or publisher math is applied. Copy boxes fit safe areas, cannot overlap other copy/barcode boxes, and use exact supplied fonts, size and leading. `rotation` is 0 or 90; optional `color_rgb` is three 0–1 values. Unsupported shaping, combining marks, missing glyphs, outline formats, font permissions, long unbreakable words, and horizontal/vertical overflow are rejected. Latin copy is the bounded supported text scope.

Outputs are actual `cover.pdf`, `manifest.json`, and `layout-evidence.json`. The manifest binds all input bytes, template facts, exact edition/interior pair, output PDF hash, planned panel/placement boxes, wrapped copy, and post-write PDF audits. Audits reopen the actual output and verify page geometry, extracted copy, embedded fonts, actual text run positions/size/rotation and actual image boxes/pixel dimensions/decoded color and alpha digests against planned placements. No placeholder cover is substituted. `review_state` remains `pending-rendered-human-review`: run the renderer against that cover PDF and inspect its preview before recording human dispositions. Structural/font/geometry checks do not establish visual fitness.

## Render packet and exact human review coverage

Start with `assets/templates/render-review.json`. Required fields are `schema_version:1` and relative `pdf`. Optional `renderer` selects an existing pdftoppm executable; omission searches PATH. No install or network fallback is attempted. Optional `pages` selects distinct one-based pages; omission selects all pages. A PDF can have 1–2000 pages; one invocation renders at most 200 pages and at most 120 million aggregate pixels. Optional integer `dpi` is 36–150, default 72. Encrypted PDFs and unsupported oversized geometry are rejected. Each renderer process has a finite timeout.

Outputs include actual `page-0001.png` previews, escaped/URL-encoded `review.html`, and `manifest.json`. The manifest binds the actual PDF SHA-256, page count and per-page text/MediaBox identities, renderer resolved path/version, selected page numbers, DPI, preview hashes and input hashes. Inspect cover typography, spine orientation, edge clearance and barcode placement; inspect interior pages for clipping, glyphs, headings, illustrations and pagination. A rendered image is evidence for a human decision, not an automatic completed review.

Optional explicit dispositions have shape `{"page":1,"status":"accepted","note":"Named reviewer inspected this exact preview"}`. Status may be `accepted` or `changes-required`; notes must be nonempty. If any dispositions are supplied, `disposition_pdf_sha256` must equal the actual current PDF hash. Duplicate, nonexistent or unrendered disposition pages are rejected. State is `pending` until unique dispositions cover every page of the exact PDF, then `changes-required` if any page requires changes, otherwise `accepted`. A representative subset remains pending even if every selected page is accepted. No fabricated dispositions or inherited acceptance are generated. Large books can be inspected in bounded page batches, but this adapter deliberately does not aggregate partial packets into full acceptance; supply exact complete coverage via an appropriate larger manual review workflow.

Optional `previous_manifest` creates verified local `previous-NNNN.png` and same-sized `diff-NNNN.png` images next to current previews. Their hashes are recorded. Observed text/box differences and detected pixel changes populate changed_pages and mark affected pages and neighbors. A different document hash conservatively lists every current page under possibly_affected_pages, while unverified_pages identifies pages without retained exact evidence. This distinction avoids claiming that unrendered graphics have been measured: graphics can change without text, including when a separate page also has a known text edit. A page count change also invalidates prior document evidence. Only exactly unchanged PDF identity, renderer version/DPI and equal pixels retain prior *evidence*, never prior acceptance. Missing, changed or incomparable prior previews remain unverified. No pixel comparison is described as semantic equivalence. Run validators after any output/source change; missing/changed hash or page identity invalidates the old exact pair/packet.

## Portable tests

`selftests/test_cover_review.py` generates actual PDFs, art and a clearly synthetic supplied barcode in an external temporary directory. It uses ReportLab's permitted bundled Vera fixture when available. Set `BOOK_TEST_PDFTOPPM` to an existing executable, or expose pdftoppm on PATH. Missing libraries/font/renderer produce explicit test skips, never a false claim that rendering passed. Tests cover actual output/audits, source preservation, exact-hash same-count invalidation, missing geometry/permissions/barcode, copy overflow, pending review, explicit coverage, stale dispositions, actual changed preview comparisons and neighbor review. Retained validation evidence is separate from fixtures and remains pending human review.

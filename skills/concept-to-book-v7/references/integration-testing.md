# Actual production integration tests

This reference defines practical file-based checks for `scripts/build_reading_edition.py`. Keep fixtures, execution logs and generated results outside the skill and outside any live book. The historical external harness is in the sibling `../concept-to-book-v6-validation/production/`; the reusable skill has no runtime dependency on that folder. Select the current candidate helper explicitly when reusing it. Historical results apply to their exact tested bytes and scope, not automatically to a new version name.

The harness at `production/run_integration.py` creates a fresh `runs/<UTC-time>-<random-id>/` directory for every execution. It creates all input files for a small fictional book, uses synthetic geometric test art, runs the real adapter in subprocesses, and inspects the actual generated files. It neither edits a real manuscript nor treats this tiny fixture as evidence about a full-length book's prose or appearance.

## Rerun the local harness

From the parent Skill Development directory:

```text
python concept-to-book-v6-validation/production/run_integration.py --builder concept-to-book-v7/scripts/build_reading_edition.py
python concept-to-book-v6-validation/production/run_integration.py --builder concept-to-book-v7/scripts/build_reading_edition.py --font-source "C:/Windows/Fonts/DejaVuSerif.ttf"
```

The first command uses only Python's standard library and explicitly skips the supplied-font test. The second copies the specified existing local font into the fixture and exercises real embedding and restricted-flag rejection. Use only an appropriately permitted font; the recorded run used DejaVu Serif, whose embedded license notice was also extracted beside the fixture font. No font or artwork is fetched or installed. A tiny genuine JPEG was generated locally once and stored as fixture bytes in the harness, so Pillow is not required for a rerun.

`--builder PATH` selects an explicit candidate script. Each result records that script's hash, interpreter, optional font hash, test count, elapsed time and unrun capabilities. Command/stdout/stderr logs, source fixtures and all outputs remain in that run directory. An existing run is never reused. A run failing before result serialization is incomplete evidence; keep it distinct from a successful report.

## Assertions against real files

| Test | Actual evidence |
|---|---|
| EPUB container and metadata | First uncompressed `mimetype`, exact media-type bytes, ZIP CRCs, unique members and package XML IDs, container rootfile, title/author/language/identifier/modified metadata |
| Navigation and full reader package | Exactly one EPUB TOC navigation, cover-image property, exact cover + title + recap + two chapters + afterword + sources order in spine and navigation; referenced resources exist |
| Text and supplied assets | HTML section order and paragraphs equal fixture sources; links target real files; PNG sizes and copied image/font bytes match sources |
| Manifest | Actual source, adapter and output hashes; dimensions, capability gaps, unrun visual/reader review, unsupported print state |
| Reproducibility | Two independent builds with identical inputs have identical complete output-tree SHA-256 maps, including the manifest |
| Preflight and preservation | Preflight creates no output; source snapshot is unchanged; an existing release is refused unchanged |
| Input boundary and validation | Reject path traversal, output under input root, duplicate IDs/JSON keys, invalid dates/order, device-name IDs, unsupported fields/blocks, unused or missing assets and corrupt PNG structure |
| Actual font path | Supplied font is copied and embedded; caller-denied embedding and restricted OS/2 flags are rejected |
| Source-change propagation | A changed paragraph changes HTML and EPUB; only its EPUB section and the explicitly changed package timestamp differ; untouched asset bytes, previous releases and original inputs remain unchanged |
| Unrelated edition | A separate HTML-only companion build survives another book rebuild unchanged; selecting one format does not emit the other |
| JPEG | A genuine small JPEG builds with measured dimensions and unchanged embedded bytes |
| Internal package identifier | Supplied section, image and font IDs of `book-id` are refused by both preflight and build without changing inputs or creating outputs |

These assertions inspect a bounded fixture, not every permitted input. Invalid or unsupported material must still fail honestly; passing these tests does not justify adding unsupported format promises.

## Current measured run

The completed result path and exact counts are recorded in the external validation report rather than frozen as a universal guarantee. The final production-agent handoff identifies the latest run and adapter hash. Earlier runs remain historical evidence for their exact versions. A harness setup failure during development was corrected before the completed suite; it is not counted as a passing run.

Keep the following evidence states separate:

- **Executed:** actual Python adapter, local file assertions, ZIP/XML parsing, hashes, deterministic rerun, change propagation, refusal and preservation checks.
- **Unrun by this suite:** rendered visual inspection, keyboard/screen-reader behavior, real EPUB reader interaction, EPUBCheck, glyph coverage and full-book reading quality. Any separately performed UI review needs its own exact-file evidence.
- **Unsupported by this adapter:** PDF layout/export, print geometry, printer-wrap generation, physical manufacturing and platform submission.

## Reconstruct tests without this local harness

Use the self-contained schema and commands in [production-adapters.md](production-adapters.md) to create a new fixture directory outside the skill. Include all input JSON, small supplied test PNG/JPEG files, a title/recap, at least two body sections, an afterword and sources. Identify all art as test material. If supplied font embedding is in scope, include the actual file and applicable permission record.

Build into two different new directories. Independently parse the actual OPF/spine/navigation and HTML, compare the content/order/assets/metadata with the fixture, recompute every manifest hash, and compare the two output trees. Change one paragraph in a separate fixture copy, advance its explicit metadata timestamp and build into a third new directory. Confirm affected outputs change while unrelated EPUB members, original inputs, prior releases and a separate edition remain unchanged. Try representative invalid inputs and existing output paths; confirm refusal without modifications. Record commands, expected behavior, observed behavior, versions, hashes and exact limitations.

When the adapter changes, rerun affected file tests plus the existing preservation and reproducibility cases. When only prose guidance changes, inspect the affected scenario routes instead of asserting that the unchanged adapter needs a new certification. A missing runtime, missing real-reader tool or absent printer template is a capability gap to report, not simulated success.

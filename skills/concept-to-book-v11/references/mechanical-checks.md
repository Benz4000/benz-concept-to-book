# Optional mechanical checks

Use `scripts/check_project.py` when Python 3.9+ is available and a project has explicit file and check declarations. It uses the standard library, does not access the network, and reads only the supplied manifest and its declared files. It neither installs dependencies nor searches private directories. Do not require this helper when unavailable: record **unverified / not run**, use available manual checks, and retain the corresponding acceptance gates.

This is evidence for a subset of mechanical checks. It does not decide editorial quality, semantic equivalence, visual quality, accessibility, readiness to publish, or acceptance by a platform. An exit code of zero means only that no declared mechanical check failed. Omitted checks are not passed checks.

## Run

```text
python "<skill-directory>/scripts/check_project.py" --root "<project-directory>" --manifest checks.json
python "<skill-directory>/scripts/check_project.py" --root "<project-directory>" --manifest checks.json --report checks-report-01.json
```

`--root` is the explicit project boundary. Manifest paths and every path inside the manifest are relative to that root, **not** relative to the manifest's folder or a link source. Use forward slashes for portable paths. The root is resolved before establishing the boundary. Absolute/drive paths, parent traversal, Windows alternate streams, and symlink/reparse traversal below the root are rejected. All inputs must be regular project files. Work on a stable project copy; this helper is not a filesystem snapshot or a defense against concurrent hostile filesystem changes.

Without `--report`, the report goes only to standard output. `--report` explicitly requests a new UTF-8 JSON file inside the project root. Its parent must exist; the helper refuses an existing report or collision with a declared input or destination. It does not create folders, overwrite inputs, fix files, move files, or delete files. Choose a new report filename on a later run.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | No detected failures in the declared mechanical checks; read all unverified results and limitations. |
| `1` | At least one mechanical check failed. |
| `2` | Invalid manifest, unsafe path, or invocation/report-writing error. A complete report may not exist. |

Reports use `PASS`, `FAIL`, `OBSERVED`, and `UNVERIFIED`. `OBSERVED` records a computed hash without a comparison baseline. `UNVERIFIED` means the check was not performed or cannot be established by this helper. The report's `outcome` is `no_failures_found` or `failures_found`; neither is release approval.

## Manifest version 1

The top-level `schema_version` and nonempty `files` array are required. Other arrays are optional and default to no checks. Unknown fields and duplicate JSON object keys are rejected to expose misspellings and ambiguous declarations. Duplicate file IDs, file paths, and check declarations are also rejected. There is no automatic discovery.

| Array | Entry fields | Check performed |
| --- | --- | --- |
| `files` | `id`, `path`, optional `sha256` | Require the declared file; stream SHA-256 in 1 MiB chunks. Compare exact bytes when an expected hash is supplied. |
| `sections` | `file`, `expected` | Extract explicit section comment IDs; compare the full sequence, including missing, extra, reordered, and duplicated markers. |
| `placeholder_scans` | `file`, `markers` | Count each declared literal string, case sensitively. Any occurrence fails. |
| `local_links` | `source`, `target`, optional `fragment` | Check that the declared local target is a file. Link presence in the source, navigation, fragment validity, and target content remain unverified. |
| `metadata_pairs` | `name`, `left`, `right` | Compare two declared scalar fields from JSON files by exact type and value. |
| `assets` | `file`, `pixels`, `placement_inches`, `minimum_ppi` | Calculate width and height PPI from recorded numbers; both must meet the explicitly supplied minimum. |
| `external_checks` | Strings naming requested checks | Always report unverified. No external tool, site, or platform is invoked. |

Every `file` or `source` refers to a declared file ID. `target` is a project-root-relative path; put a fragment in `fragment`, not in `target`. Distinct links may share a destination. Each file has at most one section declaration, placeholder scan, and asset declaration. Metadata pair names and external check names must be unique.

Text checks require UTF-8 (an initial BOM is accepted), with a 32 MiB limit per text file. The bytes actually read for a text check must match that file's recorded hash; a mismatch makes the dependent check unverified. Unsupported encoding fails the applicable text check; a file beyond the text limit is unverified. Missing files fail the file check and dependent text checks become unverified. Binary hashing does not have that text size limit. Reports list relative paths, hashes, marker IDs/counts, and declared dimensions, but omit manuscript excerpts and metadata values. Review the report before sharing it; these identifiers and filenames may themselves be sensitive.

### Example

The paths, section IDs, literal markers, metadata pairings, and thresholds below are illustrative. Declare only checks appropriate to the actual project. A hash baseline must come from a trusted, approved artifact; computing a hash now does not prove that the current artifact is correct.

```json
{
  "schema_version": 1,
  "files": [
    {"id": "manuscript", "path": "source/manuscript.md"},
    {"id": "source-meta", "path": "metadata/source.json"},
    {"id": "print-meta", "path": "metadata/print.json"},
    {"id": "cover", "path": "assets/cover.png"}
  ],
  "sections": [
    {"file": "manuscript", "expected": ["front-title", "chapter-01", "chapter-02", "back-notes"]}
  ],
  "placeholder_scans": [
    {"file": "manuscript", "markers": ["[TODO]", "[TBD]", "{{AUTHOR_NAME}}"]}
  ],
  "local_links": [
    {"source": "manuscript", "target": "extras/reading-guide.html", "fragment": "discussion"}
  ],
  "metadata_pairs": [
    {
      "name": "title-source-vs-print",
      "left": {"file": "source-meta", "pointer": "/title"},
      "right": {"file": "print-meta", "pointer": "/title"}
    },
    {
      "name": "edition-label-source-vs-print",
      "left": {"file": "source-meta", "pointer": "/edition_label"},
      "right": {"file": "print-meta", "pointer": "/edition_label"}
    }
  ],
  "assets": [
    {"file": "cover", "pixels": [3600, 5400], "placement_inches": [6, 9], "minimum_ppi": 300}
  ],
  "external_checks": ["pdf_font_embedding", "actual_embedded_image_ppi", "live_link_destinations"]
}
```

To compare a file to a known baseline, add `"sha256": "<64 lowercase hexadecimal characters>"` to its file entry, replacing the placeholder with the actual approved hash. Unchanged content saved with different line endings or encoding has a different byte hash; this is expected.

Section markers are complete lines in the declared text file:

```markdown
<!-- section: front-title -->
<!-- section: chapter-01 -->
<!-- section: chapter-02 -->
<!-- section: back-notes -->
```

IDs contain letters, digits, `.`, `_`, and `-`, and begin with a letter or digit. Leading/trailing horizontal whitespace and LF/CRLF line endings are accepted. Markers are structural declarations. They do not establish that a section's prose is complete or that headings in a PDF/EPUB have the same meaning. Markers inside a code example also count; choose a file where these lines are actual structural declarations. Malformed or undeclared marker syntax is not inferred.

Metadata references use JSON Pointer paths, for example `/title`, `/editions/0/label`, or `/a~1b` for a key named `a/b`. `~0` encodes a literal `~`; `~1` encodes `/`. Each pointer must resolve to a scalar string, number, boolean, or null. Null or blank values on either side are unverified, including two nulls or two blank strings. Otherwise comparison is case sensitive, has no trimming or other normalization, and distinguishes types (`"1"`, `1`, and `1.0` differ). Declare only fields that should agree. Edition-specific ISBNs, formats, publication dates, dimensions, and prices may intentionally differ and must not be treated as universal equality rules. A passing pair verifies only the two supplied records; the helper cannot infer whether a record faithfully represents an export or a platform listing.

Pixel counts are two positive integers. Placement dimensions and the threshold are positive finite numbers. PPI is `pixels / placement_inches` for each axis, calculated without rounding before comparison. A calculation from recorded values does not inspect image pixels, crop, resampling, placement in the final PDF, color space, bleed, or visual sharpness. It does not supply a universal platform threshold. Any maximum-PPI guidance, excessive file-size concern, or image appropriateness remains a manual or separately evidenced check.

## Integrate results with the project record

Record the command, manifest, report location, run time, observed hashes, failures, and remaining unverified checks in the existing project verification record. Fix failures through the normal authored-file workflow and rerun only affected checks or the small manifest. Preserve earlier reports when they support review; do not imply that any report applies to later changed bytes.

Keep semantic review, rendered visual review, final exported-file inspection, and destination platform preview/validation separate. PDF font embedding, actual embedded-image PPI, and live destinations stay unverified until an appropriate available tool or manual inspection produces evidence. If another tool is used, record its actual command/version/result and limitations; do not convert an intended or unavailable check into a pass. Automation remains optional and capability-adaptive.

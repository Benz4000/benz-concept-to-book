# Local project runner and explicit source coverage

The optional runner connects an explicitly selected manuscript import to configured section roles, HTML/EPUB, PDF interior proof, and independent export audits. It reads only the manifest and selected files; it has no network, publication, arbitrary shell command, approval, or preference discovery stage. Standalone cover and render-review helpers remain separate explicit commands.

Start from `assets/templates/project-run.json`. `input_root` is absolute or relative to the manifest directory. `selected_inputs` is the complete allowlist of manuscript, metadata, art, font and settings files. All file references beneath that root are relative POSIX paths. Duplicate JSON keys, unknown manifest/edition keys, escape paths, duplicate section IDs, conflicting front/body/back order, missing referenced allowlist entries, and unsupported manuscript content are refused. Section IDs/order must match importer preflight (section-0001, etc.). Every section requires an established `part` and `kind`; optional title overrides must be intentional. Metadata uses the importer metadata JSON contract. `edition` uses reading-edition settings for edition_id, formats, assets, optional cover_image and font. Optional `print_settings` names an explicitly selected print-settings JSON file; all of its font variants must also be selected. Optional edition.image_insertions is a bounded list of {section_id, block_index, asset_id, caption?}. Each insertion names an existing imported section and explicit asset. block_index inserts before the zero-based original block; the original block count appends. Duplicate positions within one section are refused. Preparation inserts in descending index order, preserving original text and order; the runner removes this runner-only field from the builder config. Plan validates placements before any output writes. The runner does not invent metadata, roles, trim, fonts, art, or settings.

Plan (read-only; creates no run directory):

```text
python -B scripts/run_project.py --manifest /path/project-run.json --output-root /external/existing-output --stages import,prepare,digital,audit-digital
```

The JSON plan shows dependencies, missing inputs, conflicts, proposed actions, Python runtime identity and relevant PDF package availability/version. Missing required runtime or PDF dependencies are capability gaps and block execution before any run directory is created. Directly referenced settings must be allowlisted before their bytes are read. It validates manuscript structure and explicit role alignment without writing. An empty stage list is allowed for planning. Full builder-specific asset/font validation happens in the requested builder; plan does not promise font/layout success.

Execute exactly the named stages:

```text
python -B scripts/run_project.py --manifest /path/project-run.json --output-root /external/existing-output --stages import,prepare,digital,pdf,audit-digital,audit-pdf --execute
```

Dependencies must appear earlier in the same explicit stage list. No dependency is executed by implication. `import` has none; `prepare` needs import; digital/pdf need prepare; each audit needs its corresponding build. PDF requires explicit print_settings and installed optional PDF dependencies. Digital execution uses only Python standard library. Output-root must already exist and be disjoint from the input root. Outputs use a fresh `run-UUID` directory, preserving every prior run. `inputs/` holds the selected source snapshot; the runner never changes its bytes after creation. Hashes are recorded in run-manifest.json. Stage folders are import/, prepare/, digital/, pdf/, audit-digital/, audit-pdf/. pdf-input/ holds the prepared content plus current explicitly selected print inputs. Audit JSON appears in runner-stdout.txt; helper diagnostics are retained alongside it. A local structural/audit pass is not visual, reader, printer or publication acceptance.

Resume uses a new run and source snapshot:

```text
python -B scripts/run_project.py --manifest /path/project-run.json --output-root /external/existing-output --stages import,prepare,digital,pdf,audit-digital,audit-pdf --execute --resume /external/existing-output/run-PREVIOUS
```

A prior completed stage is copied only if its consumed input/config/helper/dependency fingerprint matches and its complete actual output inventory/hashes match the saved record. Fingerprints include semantic helper code, interpreter implementation/version/executable, and for PDF build/audit only the actual available ReportLab, pypdf and Pillow versions. Standard-library stages do not consume PDF dependency identity. Each stage records inspectable fingerprint_components; a changed runtime cannot silently reuse a completed stage. Running, incomplete, missing or tampered stages execute again into the fresh run, preserving old material. Import consumes manuscript/metadata; prepare consumes edition roles/settings/art/digital font plus imported outputs; PDF additionally consumes print settings/font variants; audits consume their built branch. Changing PDF-only settings reuses the import, prepared digital configuration, digital build and digital audit. Unrelated selected files do not invalidate consumed branches. Copied outputs retain their actual original provenance; copying does not establish a new visual review. run-manifest.json records `reused_from` for reuse. Run records are local integrity evidence, not signatures or a defense against a maliciously rewritten record and matching files.

## Explicit source-to-output coverage

Reuse existing source-ledger or dependency-graph source IDs in `assets/templates/source-use.json`; do not create a second authorship ledger. This optional file records evidence/application claims for those IDs. Each source requires source_id, explicit availability, path/hash or null when unavailable, supplied read_record, interpretation, scoped_decision and destinations. No private vault is required. An unavailable source has null path/hash/excerpt byte fields and may carry a supplied partial/read assertion with its locator and scope; the report leaves that assertion unverified.

For an available file, sha256 is the expected full-file lowercase SHA-256. read_record has status read/partial/not-read, explicit scope and locator, plus start_byte/end_byte and excerpt_sha256 for a claimed read excerpt. Byte ranges use UTF-8 file bytes (or the raw supplied file bytes), start inclusive, end exclusive. Use null excerpt fields for not-read. This verifies only the selected byte excerpt. For binary containers such as DOCX, a raw byte range is not a semantic paragraph locator; the supplied locator remains a declaration.

Destinations each have relative path, expected sha256, explicit locator and use: citation, production-reference or declared-application. Selected destination files must live under the explicitly designated input-root; stage copies can be gathered into a separate explicit evidence input root when necessary. The report does not crawl directories or guess application from file existence. Available or missing sources need only the named paths. Citation accuracy/adequacy and locator correspondence inside a destination are declared, not automatically established by a file hash.

```text
python -B scripts/report_sources.py --input-root /selected/evidence-root --record source-use.json --output-root /external/existing-output --output-dir sources-001
```

This creates only a new source-coverage.md and source-coverage.json. Existing output directories are refused. The JSON retains supplied read records, interpretation, decision and destination declarations separately from verified-file-access, verified-selected-excerpt and destination hash results. Missing/changed sources and stale excerpt hashes flag affected destinations as stale-or-unavailable. Destination changes/missing files receive their own verification flags. A stale report is useful evidence and is generated successfully; success means report creation, not clean coverage. File access and matching excerpt bytes cannot prove understanding, full reading, influence or successful application. Inputs remain unchanged.

## Verification

`python -B selftests/test_runner_sources.py` exercises actual CLIs: read-only plans, dependency scope, schema/path conflicts, digital build/audit, fresh resume, interrupted-stage recovery, tamper checks, source changes, unrelated inputs, PDF settings branch invalidation, selected excerpt verification, stale/missing sources and unavailable-source operation without a vault. PDF regression requires the installed reportlab, pypdf and Pillow dependencies and ReportLab Vera font fixture.

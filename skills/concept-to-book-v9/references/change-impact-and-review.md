# Change impact and review packets

These optional helpers provide a compact view over existing source → decision → artifact → check links. They do not create new workflow approvals, change check status, or decide whether a manuscript is correct. Both use Python 3.12+ standard library only; they read source files and write only to the explicitly named new output location.

## Advisory change impact

Create a graph based on the links already maintained by the project. See `assets/templates/dependency-graph.json`.

```powershell
python scripts/plan_changes.py --root . --graph project/dependency-graph.json --report reports/change-impact-001.json
python scripts/plan_changes.py --root . --graph project/dependency-graph.json --baseline reports/change-impact-001.json
```

The graph has `schema_version: 1`, artifact records `{id,path,depends_on?}`, and check records `{id,inputs,status?,reviewed_sha256?,reviewed_state_sha256?}`. Unknown fields, duplicate JSON keys/IDs, malformed hashes, artifact cycles, and unknown artifact dependencies are errors. Check `inputs` that name absent artifact IDs are retained in `missing_inputs` so the report exposes incomplete mapping. Paths are root-relative POSIX paths; symlinks and Windows special path forms are rejected. Missing declared files are reported as missing and their dependents are marked for impact review. JSON inputs and total artifact bytes are bounded.

The report is also schema version 1. It stores current artifact hashes (or `null` for a missing file) and dependency lists, plus direct changes (new, removed, missing, content changed, or dependencies changed), downstream impacts, and an advisory row for every check. For every check it reports `current_state_sha256`, a digest over the check ID, declared input IDs, and the current upstream closure's artifact IDs, hashes, and dependency edges. For dependency-bearing checks, `reviewed_state_sha256` must be supplied by an actual review to match this digest; an absent or older value keeps the check marked for reconsideration across later quiet reports. Once a check requires this digest, the requirement persists across reports even if later graph edits remove its final dependency edge; the new closure still needs a reviewer-authored digest. This catches changes in dependency topology even when file bytes stay the same. Per-file `reviewed_sha256` remains useful for checking direct inputs and for leaf checks. A check whose own hash matches can still need reconsideration when an upstream dependency changed. Missing or stale hashes advise reconsideration. Hashes establish byte identity and declared review scope only, not semantic correctness or approval. The tool never edits authored check status or evidence declarations. A previous report can be used as `--baseline`; it is not itself fingerprinted unless explicitly listed as an artifact in the graph.

`--report` is optional and create-new only; omit it for stdout. Parent directories can be created, but an existing report path is an error.

## Self-contained review packet

Start from `assets/templates/review-packet.json`, replacing example paths with the exact current and previous versions, relevant context, and any page preview images already supplied. Then run:

```powershell
python scripts/make_review_packet.py --root . --manifest project/review-packet.json --output-root ../book-review-packets --output-dir packet-001
```

The manifest has `schema_version: 1`, a title, criteria strings, and an explicit item list. Each item has a unique safe `id`, label, current file, optional previous file, context files, and optional supplied PNG/JPEG previews. Current and previous files keep their original basenames; context and preview copies receive numeric prefixes to avoid filename collisions. `index.html` includes escaped UTF-8 text for supported small text files, unified before/after diffs when both versions are supported text, previews, criteria, a blank coverage record, and a pending review status. Links encode URL-reserved filename characters. `provenance.json` records every copied source path and SHA-256, plus the pending review scope.

The packet does not render PDFs, extract or read chapters from PDFs, create page images, or perform a review. A PDF is copied and linked as supplied; a provided page image is explicitly labeled as a supplied preview. Files over the size limit, unsafe paths, symlinks, missing files, and pre-existing output directories fail closed. Output must live outside the project root and `--output-dir` must be new.

## Boundaries

These tools are useful when a change needs a quick impact map or a reviewer needs a small, traceable bundle. Keep the graph and packet manifest beside the existing project records that already express those relationships. Do not maintain duplicate status ledgers solely for these helpers. Reviewers decide whether the impact matters and record the outcome in the project's established decision/check record.

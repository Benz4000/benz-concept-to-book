# Continuity through story time and disclosure order

Use this reference for scenes, recaps, companion stories, character profiles, illustrations, and covers whose accuracy depends on **when something is true** or **who may know it**. Reuse an existing scene map or canon table. The [JSON ledger](../assets/templates/continuity-ledger.json) is an optional worked example, not a mandatory project file or established canon. Its Ada, key, coat, cipher, sources, decisions, and scene names are invented examples; replace them before use.

## Establish the scene's coordinates

Keep two orders distinct. **Story time** locates an event in the world's chronology. **Reading order** locates its presentation to the reader. A flashback read in chapter 8 can occur before chapter 1. It uses the earlier character state, even when the reader already knows a later outcome. An unreliable recollection or a character's belief is not an objective fact: give it a separate property/scope and record the uncertainty.

Assign stable scene IDs and an explicit scope: for example, book, draft/edition, and timeline together. Decide the smallest time unit needed for relevant changes. Integer points can mean days, ordered events, or beats; they are not necessarily clock times. Split a scene into stable beat IDs if a possession, injury, knowledge state, or capability changes mid-scene. Do not force ambiguous simultaneous events into a false chronology. Leave their ordering unknown until the manuscript or an accepted decision resolves it.

For each consequential scene or beat record:

| Field | Meaning |
|---|---|
| Scope and scene ID | Exact applicable canon/version/timeline; do not inherit silently across books or editions |
| Story time | Where the represented event happens; unknown is permitted |
| Reading order | Where this unit appears to the reader, independently of story time |
| Reader ceiling | Latest disclosure rank this unit may reveal; a front-matter profile or early-book recap can have an earlier ceiling than its physical placement |
| Characters and facts | Relevant possessions, appearance, injuries, relationships, abilities, limits, and location at that time |
| Knowledge and reveal | Who knows the specific information; when the reader is first allowed to receive it |
| Evidence and dependencies | Exact source/version and locator, accepted decision ID if applicable, scene/asset IDs, and the review result |

Reading order and reader ceiling must use the same ranking system as the reveal gates. A reader-facing use must fit **both** its actual reading position and its allowed ceiling. Character knowledge and reader knowledge are independent: an omniscient narrator may reveal something the viewpoint character does not know, while a knowledgeable character may keep a secret from the reader. Record a `knowledge_use` when a character acts on information, and a `reveal` when text or art communicates it to the reader. Neither automatically creates the other.

## Record states and changes without rewriting the past

Use time intervals for a scoped property: start inclusive, end exclusive. A state from 0 until 20 applies at 19, not at 20. The new state beginning at 20 applies at that point. A transition records the before and after states at its scene's story time; it does not edit either interval automatically. A flashback at time 5 still uses the old interval even when read after the transition.

Examples to check in context:

- **Possession:** Ada has the brass key until she drops it at time 20. A later escape cannot use it unless recovery or another key is established. A flashback at time 5 may show it. Distinguish ownership, carrying, accessibility, and location if the plot depends on those differences.
- **Appearance:** Ada changes from a blue coat to a red one at time 20. A late-positioned illustration of time 5 needs the blue coat. Character sheets should list time-specific variants instead of replacing all earlier art with the latest appearance.
- **Capability:** Knowing how to read a cipher does not mean knowing the contents of an unread letter. Record skill, current physical capacity, access, and information separately where consequential. A temporary injury or magical limit needs its own interval and evidence.
- **Knowledge:** Before time 30 Ada is explicitly unaware of the letter's identity; afterward she knows. An assertion of her knowledge at time 10 conflicts. Missing records about another character mean unknown, not unaware.
- **Reader reveal:** The letter's identity is permitted from reading rank 4. A scene at rank 3 or a profile limited to rank 2 cannot disclose it, even if the depicted character already knows it.

Overlapping intervals for the same scoped subject/property need reconciliation, including duplicates with the same value. Prefer one evidenced state per time point. Exact scopes remain isolated. Do not let a new edition, later-book change, alternate timeline, draft proposal, prophecy, or later discovery overwrite earlier accepted history. If a revision deliberately changes history, record the accepted superseding decision, retain prior-version evidence, then update all affected destinations in the new scope. Do not silently select the newest file or whichever fact makes a check pass.

## Trace a correction to its dependents

Maintain **source ID → interpretation → scoped decision ID → state/transition → scene/beat → dependent reader material or asset → verification evidence**. A simple table is enough; reuse the [source ledger](reference-provenance.md) and existing foundation records. Creative decisions can have no external source; do not invent one. Distinguish original manuscript evidence from research, craft advice, and interpretation.

When a fact changes, inspect linked scenes, flashbacks, dialogue, recaps, profiles, companion stories, illustrations, and covers. Search for candidate omissions, but read the affected passages and view the affected art before claiming repair. Record changed, unchanged, pending, and unverified destinations separately. A dependent scene's correct state does not prove its prose, illustration, or narrator handles that state correctly. A source file's hash proves which bytes were read, not that every linked decision was accurately extracted.

## Manual review is a complete supported workflow

1. Open the authoritative manuscript and accepted scoped decisions; name the exact version and reading scope.
2. Walk important scenes in **story-time order** and compare each required state with the preceding transition. Resolve conflicting intervals; leave missing states unknown. Then review in **reading order** for character knowledge and reader disclosure.
3. Review flashbacks and supplements explicitly against their represented time and reader ceiling. Check scene-specific art against both.
4. For each finding, record scene/state/evidence IDs, exact passage or asset location, expected versus observed condition, impact, and the proposed correction. The author or established decision authority resolves ambiguities.
5. Reread the changed context and affected dependents. Report coverage and unresolved issues, not universal continuity proof.

Unknowns can be safely deferred when their dependent work can wait. Record what is missing, why it can wait, the role/input that resolves it, the milestone, and the blocked scenes/assets. Use the [issue register](../assets/templates/issue-register.md). Do not fill unknown values with guessed canon or treat an accepted deferral as a passed check.

## Optional local checker

[check_continuity.py](../scripts/check_continuity.py) is a small standard-library Python 3.9+ helper. It reads only the explicitly selected local manifest and its listed local files, hashes those inputs, compares structured declarations, and emits a JSON report to stdout. It has no network access, language-model extraction, autofix, or report-writing option. Python is optional; the manual workflow above remains sufficient.

```text
python /path/to/concept-to-book-v6/scripts/check_continuity.py --root /path/to/book-project --manifest continuity-ledger.json
```

Use actual absolute local paths for the script and project root. The manifest path and all input paths are relative to that root and use forward slashes. On Windows, quote absolute paths that contain spaces. Capture stdout outside the input files if a persistent report is useful; never redirect over the manifest or manuscript. No dependency installation is needed.

**Limits:** at most 1,000 records across all arrays, a 2 MiB manifest, 32 MiB per listed input, and 128 MiB total input reads. Paths cannot use parent traversal, absolute/network paths, drive/stream syntax, Windows device names, or symlink/reparse traversal below the resolved root. This is a bounded local helper, not a hostile-filesystem security boundary; use a stable local snapshot and do not concurrently replace its paths. Files are hashed but not interpreted. Evidence locators are human review aids and are not parsed or confirmed against the manuscript.

### Schema version 1

All top-level arrays below are required; use empty arrays for unused record types. Unknown fields, unresolved referenced IDs, duplicate IDs/JSON keys, malformed intervals, unsafe paths, and noninteger numbers are input errors. IDs are globally unique, case-sensitive strings of 1–96 ASCII letters/digits/dots/underscores/hyphens, starting with a letter or digit. Scope, entity, character, and property keys use that same syntax. Scope/entity/property values are labels, not a registry or ontology. Reuse stable project IDs.

| Array | Required fields per record |
|---|---|
| `files` | `id`, `path`; optional `sha256` baseline, 64 lowercase hex characters |
| `evidence` | `id`, `file` ID, `locator` |
| `scenes` | `id`, `scope`, `story_time`, `read_order`, `reader_ceiling`, `evidence` IDs |
| `facts` | `id`, `scope`, `entity`, `key`, `value`, `start`, `until`, `evidence` IDs |
| `transitions` | `id`, `scene` ID, `entity`, `key`, `from`, `to`, `evidence` IDs |
| `assertions` | `id`, `scene` ID, `entity`, `key`, `value`, `evidence` IDs |
| `topics` | `id`, `scope`, `reveal_from`, `evidence` IDs |
| `knowledge` | `id`, `scope`, `character`, `topic` ID, `state`, `start`, `until`, `evidence` IDs |
| `knowledge_uses` | `id`, `scene` ID, `character`, `topic` ID, `evidence` IDs |
| `reveals` | `id`, `scene` ID, `topic` ID, `evidence` IDs |

Every record from `scenes` through `reveals` may also carry `source_ids` and `decision_ids` arrays. These are links to project records, not evidence that the checker read or validated those sources/decisions. Evidence arrays can be empty but then produce `UNVERIFIED`. All records with evidence refer to IDs in the `evidence` table; each evidence record references a declared file. Identifiers survive renaming; locators should be updated when text moves.

`story_time`, `start`, and numeric `until` are integer points between −1,000,000,000 and 1,000,000,000. Disclosure ranks (`read_order`, `reader_ceiling`, `reveal_from`) are nonnegative integers within that range. `null` means unknown for these fields and for `value`, `from`, `to`, or knowledge `state`. `until: "open"` explicitly means no declared end; `until: null` means the end is unknown. Known finite intervals must have `start < until`. Property states use nonempty exact strings, including explicit `"yes"` or `"no"` when appropriate; no synonym normalization occurs. Knowledge `state` is `"knows"`, `"unaware"`, or `null`. Other non-ID strings are at most 2,000 characters.

Each assertion compares its declared value with the unique active fact at the referenced scene's story time and exact scope/entity/property. Transitions compare `from` immediately before the boundary and `to` at the boundary. Two explicit assertions or transitions demanding different values for the same scene/property/time side fail even without a known underlying interval. Knowledge uses compare with `"knows"`; a declared active `"unaware"` state fails. Gaps, unknown bounds/values, and ambiguous overlapping coverage cannot establish a unique state, so the dependent comparison is `UNVERIFIED`. Known overlapping intervals also produce an independent `FAIL`. A reveal passes only if `reveal_from <= min(read_order, reader_ceiling)` in the same scope.

### Reading a result

The report includes the manifest SHA-256, each successfully read input's SHA-256 and optional baseline, counts, limits, and checks with declaration, evidence, source, and decision IDs. An incorrect supplied baseline fails and marks its evidence unverified. Unavailable files or unknown declarations stay unverified. A known contradiction among ledger declarations can still fail even when manuscript evidence is unavailable: it is a **ledger contradiction**, not a claim that the manuscript was read or proved wrong.

| Status / exit | Meaning |
|---|---|
| `PASS` | The stated mechanical comparison of explicit declarations passed |
| `OBSERVED` | Input hashed, with no trusted expected baseline supplied |
| `UNVERIFIED` | Unknown/incomplete data, unavailable evidence, or absent declared scene coverage |
| `FAIL` | Explicit conflicting declarations, forbidden scope crossing, premature reveal, or hash mismatch |
| Exit `0` | Declared checks passed with no recorded unknowns; coverage still limited to the manifest |
| Exit `1` | One or more explicit failures; the report may also contain unverified checks |
| Exit `2` | Invalid invocation/manifest or unsafe path; stderr explains the input error |
| Exit `3` | No explicit failure, but one or more checks remain unverified |

An empty ledger cannot earn a continuity pass. A nonempty ledger can omit important facts; a zero exit code is never proof of complete coverage, semantic correctness, publication readiness, or source authority. After a repair, rerun only the affected checks on current stable inputs, then perform the required prose/art review. Preserve the old report as historical evidence rather than relabeling it as current.

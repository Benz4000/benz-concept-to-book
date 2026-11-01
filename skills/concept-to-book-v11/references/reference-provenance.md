# Reference provenance

## Record use at the time it happens

Maintain a source-use ledger alongside the project. Each applied reference needs:

| Field | What to record |
|---|---|
| ID | Stable identifier, such as CRAFT-01 or PROD-02 |
| Stage and checkpoint | Concept, outline, draft, revision, factual check, assembly, visuals, cover; date/version |
| Goal served | Intended reader/deliverable outcome and the outcome stage that owns it |
| Foundation setting affected | Decision ID, affected value and author/series/book/edition scope; source guidance does not itself establish a user preference |
| Interpretation | What was concluded from the source, with uncertainty and any fictional departure; distinguish quotation from interpretation |
| Source identity | Exact title, file path or URL, author/edition if known |
| Origin | Supplied source work; vault craft guide; project canon; external factual source; production reuse |
| Location read | Chapter, page, heading, line, or code section; sampled versus complete |
| Status | Consulted; applied; available but not consulted; unavailable; historical use documented |
| Question | The decision or gap that required this source |
| Application | Concrete change made, or why no change was warranted |
| Destination | Stable IDs plus locators for affected book/chapter/paragraph, supplement, metadata field, asset, or build component |
| Limits | Unverified edition, indirect citation, incomplete reading, interpretation, or fictional departure |
| Evidence | Read/tool record, contemporaneous report, revision diff, or manifest; connect to the specific reviewed input/output version |

Example: “Second-draft revision; imported ordinary-life craft brief; selected sections on possessions and social wants; applied to the guesthouse scene so the argument turns on the resident's existing needs; not a claim to imitate the source author's prose.”

## Distinctions that matter

- **Source work versus vault note:** reading an analysis of a novel is not the same as reading that novel. Name the intermediate note and its reading scope.
- **Inspiration versus factual authority:** a fantasy series can inform ensemble dynamics; it cannot establish the beliefs of a real religious community.
- **Canon versus research:** a prior draft establishes the project's continuity, not real-world truth.
- **Existence versus use:** a note in a vault proves availability only. A revision report explicitly mapping it to changes supports historical application.
- **Intention versus completion:** “read all chapters before drafting” is a directive, not evidence that every chapter was read.
- **Extraction versus reading:** extracting every PDF page is not a complete close reading. An automated alignment scan is not a consecutive human-like reading review.
- **Historical versus current:** a source audit may record a successful check on a date. Do not present it as a fresh verification of a current website, platform, or publishing state.
- **Original versus invented:** identify which element comes from tradition and which powers, dialogue, rules, relationships, or places the fiction adds.
- **Production reuse:** borrowed code, font sets, layout conventions, publisher decisions, image assets, and templates count as references too.

## Retrospective audits

Reconstruct work from accepted user decisions, dated reports, manifests, before/after copies, and accessible conversation records. Cite exact evidence. Prefer direct action/output evidence over a later “making of” essay; use the essay for the author's stated intent.

Use three clearly named confidence levels in an audit:

1. **Directly recorded:** an action, changed artifact, or contemporaneous report explicitly demonstrates the step or reference use.
2. **Supported reconstruction:** multiple artifacts establish the likely sequence, but the exact read/action is not recorded.
3. **Unconfirmed:** only a plan, suggestion, available resource, or unsupported claim exists.

A dated report can contain later edits. Describe its checkpoint rather than assigning every detail to the file's original creation date. Do not merge historical counts from one draft with current section or page counts from another. Record the audit cutoff when another chat is still editing the project.

## User-facing disclosure

When a new source affects the work, say what was read and why: “I used the vault's [guide] for [decision]; it changed [scene/build component].” At a checkpoint, summarize applied sources in a compact table and provide the full ledger path. Do not bury production references inside a bibliography intended for readers.

If a source cannot be opened, record that and use an accessible alternative transparently. Never fabricate bibliographic metadata or claim an unavailable file was consulted. Reusable skills should include the decision criteria needed to operate without private source files, while preserving historical paths in optional case studies.

## Follow consequential decisions through their implementations

For consequential uses maintain: source ID -> interpretation -> scoped decision ID -> destination IDs/locators -> verification evidence and version. Reuse the foundation, source ledger, asset manifest, and issue register instead of duplicating them. A plain table is sufficient; do not require a graph database or special software.

On a changed source or decision, inspect its linked destinations and downstream effects, including recaps, profiles, art, covers, and relevant reviews. Check likely omissions when the map is incomplete. Record changed, unchanged, pending, and unverified destinations separately. A text search can discover candidates but cannot establish semantic correctness by itself. An unavailable source stays unavailable; a supplied excerpt supports only its actual scope. A creative decision need not invent a supporting source.

See [calibration-and-learning.md](calibration-and-learning.md) for examples and [outcome-stages.md](outcome-stages.md) for the corresponding completion evidence. Continued use of an established reference does not imply a fresh reading.

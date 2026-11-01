# Exact-version release and session recovery

Use this reference for consequential staged changes, a handoff, a release candidate, or work resumed after interruption. Keep the needed fields in the existing manifest/handoff using the [handoff template](../assets/templates/handoff.md). A short outline handoff needs proportionate records; a publication package needs exact file identity and edition evidence.

## Establish authority before changing files

Identify the current working sources, selected assets, edition/build settings, last reviewed output, and prior released package if one exists. Record which decision or manifest makes each authoritative. Preserve conflicting candidates until reconciled; do not select by filename, modification time, a stale summary, or the strongest status label alone.

For a release candidate, create a stable snapshot or versioned copy of the relevant inputs and record actual content hashes, preferably SHA-256, plus the candidate ID and rebuild method. Keep working sources separate so ongoing editing can continue. Do not invent hashes or call an unmeasured file verified. A hash establishes byte identity, not quality, authority, or approval. Record a repository commit when useful, but ensure uncommitted or external inputs are also identified.

Record each output's exact path, edition, hash, source snapshot, asset/config/template identities, and applicable interior-cover pairing. Distinguish selected originals, production derivatives, transport derivatives, cropped previews, and guide proofs. Counts, ISBNs, dimensions, and template inputs remain unknown until established by evidence; never borrow another edition's facts.

## Tie each claim to its evidence

For every required check record method, coverage, result, reviewed version/hash, date when known, limitations, and evidence location. If only pages or sections were inspected, say which ones. Do not promote a sample or automated scan into full reading or full rendered review. Link a final acceptance check to the exact output being delivered; changes afterward require impact review before that claim carries forward.

Keep local and external states distinct: drafted, assembled reading proof, locally checked upload file, upload receipt recorded, platform validation, submitted, processed, proof approved, and distributed. A platform may use different names; retain its actual meaning and evidence. Do not assume every platform follows one linear sequence. An upload receipt is not validation or proof approval; a local check is not printer acceptance. Record interior and cover status separately when their evidence differs.

Before release or a staged replacement, compare current live hashes with the baseline used to prepare the change. If they differ, preserve the newer work and inspect the differences. Merge or reapply the intended repair against current sources, then restore the affected verification. If a conflict cannot safely be resolved from existing direction, keep both versions, flag the specific conflict, and continue independent work. Never overwrite current files merely because a staged copy was previously reviewed.

## Recover after an interruption

1. Read the latest handoff, issue register, selection/release manifest, and persisted tool or platform receipts. Establish the requested endpoint and current authorization from actual records.
2. Inspect real files and saved state; compare hashes with the recorded baseline. Classify artifacts as matching, changed, missing, or unverified. A prior “done” message is not enough to establish the current state.
3. Separate completed work with valid evidence, changed work needing targeted rechecks, outstanding blockers, optional work, and actions whose completion is unknown. Preserve valid unrelated review results.
4. If an external action may already have completed, inspect persisted state before retrying; do not duplicate uploads, submissions, purchases, approvals, or messages based only on a lost response. Unknown outcome remains unknown until checked, and requires no invented success claim.
5. Resume from the next concrete dependency. Record the next action, its inputs, expected evidence, and any required user decision. Do not restart the entire workflow or repeat unchanged checks to fill a missing narrative of the session.

## Preserve the prior release and explain the change

Keep the previous released package and its manifest intact when creating a replacement. Use a new candidate/release identity. Record what changed, why, affected decisions/files, checks invalidated and rerun, remaining limitations, and which edition pair is now selected. Separate the current work in progress from the last released version.

If a repair causes a regression, restore only the affected change after comparing with the current baseline, or build a new candidate from the prior release and merge newer authorized edits deliberately. Never blindly roll the live project back to an older folder, snapshot, or commit. Restoring old bytes does not restore current review status, platform state, or newer creative work automatically.

A complete handoff identifies authoritative artifacts and hashes where applicable, exact reviewed versions and coverage, highest evidenced status, references actually used, outstanding work, preserved prior release, change summary, and the next action or completed endpoint. Do not promise release, upload, approval, or distribution beyond the user's requested and authorized scope.

## Optional runner recovery and local package boundary

V10's optional cover, render, review, source-report, validator and package stages use the same fresh-run recovery model as the content stages. Resume by naming every wanted stage in dependency order and supplying --resume PRIOR_RUN. The runner compares stage fingerprints and complete current output inventories. A running/incomplete or tampered stage executes again; completed exact predecessors may be copied. Prior runs and independently built editions remain preserved. Do not edit a run manifest to grant a review disposition.

A changed interior requires new cover/interior binding, actual cover build, previews and applicable review records. The cover helper measures the new PDF identity but preserves supplied template geometry/edition. Template page-count or trim conflicts remain blockers. An old cover cannot be paired with a changed interior simply because dimensions look similar. Dispositions bind exact PDF and preview identities; rendering a replacement cannot grant acceptance to it.

The package stage assembles a final local handoff candidate with exact inventory and input hashes. It does not perform external release and never reports final acceptance. Required review records that remain pending or request changes leave the candidate pending. Accepted records are labeled accepted-records and preserve their actual evidence scope. Package payloads include relative evidence_bindings for copied exact PDFs, render packets and cover/interior pairs. validate_package(package-manifest.json) reopens those copies without needing the original run paths; the selftest relocates a candidate and makes its original run path unavailable before validating it. Immutable historical manifests retain absolute provenance paths, while relative overrides select the verified copied evidence. Retain full run history when needed for broader provenance; neither path mappings nor hashes are signatures.

Include relevant V11 verification reports with their exact release and retained evidence. Use [V11 recheck](v11-preservation-and-verification.md) to detect changed artifacts, HTML resources, screenshots and observation attachments before reporting currency. Supplied human/physical findings remain attributed assertions with actual coverage. Packaging a report does not grant approval; named-reader, destination and physical requirements stay pending until actually performed and evidenced.

# Validate the workflow at book scale

Use this reference for consequential changes to the reusable production workflow. It is not another author-facing book stage. The portable `selftests/test_book_scale.py` creates a substantial synthetic manuscript locally, with 30 chapters plus front/back matter, nested headings, emphasis, scene breaks, explicit illustrations and independent paperback/hardcover settings. Repeated fictional prose tests mechanics, not literary merit.

## Execute the actual route

From the complete skill folder, with an existing external output parent:

```text
python -B scripts/run_selftests.py --output-root C:/BookTests --run-name scale-001 --pattern test_book_scale.py --require-print --require-renderer
```

`--renderer PATH` can select an existing `pdftoppm` executable. The test uses the optional installed PDF packages and derives licensed synthetic font-family copies from ReportLab. It rebuilds those fixture copies' table checksums without modifying installed fonts or inventing glyphs. The copied license and fixture provenance describe this. No package, font or artwork is fetched. Missing capabilities must be reported as skips or refused prerequisites; use the required-capability flags for a complete acceptance run.

The fixture executes these actual operations:

1. Plan with no output writes; import the selected manuscript, reconcile explicit section roles and insert planned images without dropping source paragraphs.
2. Build and audit HTML, EPUB and a substantial PDF interior through the local runner.
3. Build a second edition with independently chosen layout; retain its exact output identity.
4. Change only paperback layout and verify import/prepared/digital branches are reused while PDF work is renewed.
5. Change a middle chapter and resume from a simulated incomplete checkpoint into a fresh run. Verify the old checkpoint and releases remain unchanged and old exports fail against the revised source.
6. Render selected actual pages and compare exact before/after review evidence, keeping unrendered coverage explicit.
7. Assemble a paperback wrap from supplied synthetic geometry and inputs; verify a changed interior invalidates that old cover pair. Render the actual cover proof.

The retained `scale-summary.json` records actual word/section/page counts and artifact locations. Command/stdout/stderr logs remain alongside generated inputs/releases under the external run. The test's chosen size is a regression fixture, not a universal word-count, page-count or performance target.

## Evidence boundaries

The second edition can retain valid checks after a paperback-only layout change. After a shared manuscript change, its old release is preserved as historical evidence; byte preservation does not establish that it is still current. This distinction also applies to cover pairings and visual review records.

The supplied template geometry and barcode pattern are test fixtures, not a printer formula or usable ISBN barcode. No physical proof, color calibration, platform submission, full human reading or real-reader acceptance follows from the test. Selected-page rendering does not mean every page was visually inspected.

Run the complete bundled suite before releasing changes that interact across helpers. For a narrow correction, rerun the affected cases first. Preserve failures and their exact tested versions. Add representative manual visual inspection and an independent workflow scenario when the relevant behavior changes. Stop when the documented scope passes and remaining limitations are clear.

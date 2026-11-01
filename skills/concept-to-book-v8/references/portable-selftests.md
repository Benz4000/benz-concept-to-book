# Portable synthetic workflow tests

Use this guide when changing or relocating the skill's executable helpers. The entire test package lives in `selftests/` and generates synthetic manuscripts, DOCX packages, images and project records locally. It does not need a previous skill version, original vault, author manuscript, network connection or publishing account. No test edits a live book. Use Python 3.12+.

## Run and read the evidence

Create an empty output parent outside the skill; then, from the skill folder:

```text
python -B scripts/run_selftests.py --output-root "C:/BookTests" --run-name check-001
python -B scripts/run_selftests.py --output-root "C:/BookTests" --run-name check-print-001 --require-print
```

Each run uses a new directory. Existing names are refused. `results.json` records individual case outcomes, skips, Python/package versions, font identity, script/test hashes and whether those files stayed unchanged. `test-output.txt` retains the detailed transcript; integration fixtures, CLI logs and outputs are retained under `artifacts/`. Some unit tests use temporary fixtures and retain their outcome rather than every intermediate file. A missing report or nonzero exit is not a completed pass. A passing report with skips establishes only executed coverage.

The standard-library import/change/review tests do not need PDF libraries. For the full PDF route, use an environment with the optional packages specified in [requirements-print.txt](../requirements-print.txt). The runner does not install them. It uses ReportLab's bundled Vera TTF for synthetic fixtures when available; `--font PATH` selects another existing permitted TTF. Production font permission and suitability remain project decisions. `--require-print` refuses a missing dependency/font; unrelated operating-system-dependent tests can still skip, so inspect the reported cases.

For a narrow correction, `--pattern test_changes_review.py` or another module name limits discovery. Record that partial scope. Do not represent it as a complete rerun. To check portability, copy the complete package to an isolated directory and run it there with a separate output parent. No installed predecessor should be needed.

## Observable coverage

| Tests | What the actual run exercises |
|---|---|
| Import | Plain Markdown and supported DOCX conversion; exact order/text and preservation records; unsupported-feature refusal; path boundaries, preflight and create-new behavior |
| Change/review | Changed, missing and stale evidence; downstream impact through old/current dependencies; unrelated scope; copied files, actual diffs and pending review packets; invalid schemas/paths and overwrite refusal |
| Production | Actual PDF pages, supplied embedded fonts and images; text/order, metadata, geometry and layout declarations; actual HTML/EPUB/PDF audit and tamper detection; reproducibility and refusal behavior |
| Full pipeline | Real CLI import → HTML/EPUB build → audit → changed source → impact → rebuild → stale-output rejection → review packet, plus import → PDF build → audit when dependencies exist |

The full pipeline confirms that the original source and prior release stay unchanged and that unrelated evidence is retained. Its synthetic images and short story do not establish quality for a real full-length book.

## Finish the validation

After changes to PDF layout, render a representative actual output and inspect all relevant pages for clipping, typography, placement, whitespace and page furniture. Preserve the file hash, render command and actual reviewed scope outside the skill. After workflow guidance changes, run relevant independent scenarios from [skill-evaluation.md](skill-evaluation.md), keeping evaluator criteria out of executor inputs.

Record failures and narrow corrections before rerunning affected checks. Tests establish only their actual assertions: literary quality, full consecutive reading, physical proofs, full accessibility, EPUBCheck, printer PDF conformance, platform validation and publication remain separate. Deliver when the required local behavior, preservation and review checks pass with remaining limits explicit; do not create another version merely to prolong the cycle.

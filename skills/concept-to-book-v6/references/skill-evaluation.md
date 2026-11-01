# Evaluate the skill's behavior

Use this file when developing or materially changing this skill, not as another review stage for every book. The inherited synthetic fixtures in [scenarios.json](../evals/scenarios.json) exercise scope, portability, preferences, revision, source honesty, and change propagation. The V5 fixtures in [v5-scenarios.json](../evals/v5-scenarios.json) exercise project records, criteria, priorities, feedback, mechanical-check limits and recovery. Both are bundled and require no private files or publishing services. Historical results from earlier versions do not establish results for V5.

## Run a relevant scenario

V6 adds [v6-scenarios.json](../evals/v6-scenarios.json) for profile/source-variant and temporal/reveal behavior, plus [integration-testing.md](integration-testing.md) for actual local output and regression evidence. Retain earlier fixtures as regression options; an earlier version's result is not a V6 result. Record the exact helpers and artifacts exercised and unsupported capabilities. Structured state checks establish declared relationships, not semantic coverage of an entire manuscript.

1. Choose cases affected by the skill change; include contrasting project sizes or endpoints for substantial changes. Do not substitute schema validation for behavioral evidence.
2. Give an independent executor the installed or candidate SKILL.md, only the selected case's `user_request` and `raw_inputs`, and an isolated output directory. Allow it to read runtime references linked by the skill. Withhold `evaluator_only` and this evaluation protocol from the executor.
3. Use only the fixture's supplied material. These scenarios authorize textual test artifacts, not external messages, paid generation, uploads, account actions, or edits to real books. An explicitly unavailable source stays unavailable. An asset brief is not an image, and a proposed proof is not a rendered proof.
4. Inspect actual outputs and any read/action records against `evaluator_only`. Judge decisions, artifact quality, omissions, and supported claims. Do not require exact wording, headings, file counts, or one preferred creative answer.
5. Record case ID, skill version/hash, execution date, request/input versions, produced artifacts, observed behavior, evidence scope, limitations, and status. Report specific failures before proposing narrow fixes. Re-run affected cases after corrections; retain unaffected evidence when its inputs remain valid.

## Status and evidence

- **pass:** observed artifacts and actions satisfy the applicable behavioral checks; state what was actually exercised.
- **fail:** observed behavior violates a check; cite the artifact or action and practical consequence.
- **blocked:** a required execution capability is unavailable, so the behavior cannot be assessed; do not treat this as pass or as a demonstrated skill defect.
- **not-run:** a fixture or planned check exists but has no execution evidence.

Fixtures ship as `not-run`; their presence is not evidence of a successful test. Keep run results outside the reusable fixtures, with the tested skill version. A text-only pilot plan can pass its planning case without demonstrating image generation, typography, rendered inspection, or printer acceptance. A partial run cannot establish full-workflow quality. Independent execution is preferred; if unavailable, disclose that a self-review was used and limit the claim accordingly.

The fixture set is a starting point. Add a scenario when an observed failure or a material new capability warrants it, not merely to increase the test count. Keep historical project values out of universal pass criteria.

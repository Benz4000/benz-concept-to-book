# Evaluate the skill's behavior

Use this file when developing or materially changing this skill, not as another review stage for every book. The inherited synthetic fixtures in [scenarios.json](../evals/scenarios.json) exercise scope, portability, preferences, revision, source honesty, and change propagation. The V5 fixtures in [v5-scenarios.json](../evals/v5-scenarios.json) exercise project records, criteria, priorities, feedback, mechanical-check limits and recovery. Both are bundled and require no private files or publishing services. Historical results from earlier versions do not establish results for V5.

## Run a relevant scenario

V10 adds [v10-scenarios.json](../evals/v10-scenarios.json) for foundation/endpoint discipline and exact-version review/handoff. Its executable tests cover the six new helper capabilities. Older refusal expectations are historical when the supported link/note subset or pagination contract expands; do not edit their historical fixture to manufacture a result.


V9 adds [v9-scenarios.json](../evals/v9-scenarios.json) for preserved-format digital production and a cover request with conflicting physical facts. New executable scenarios also live in the portable self-tests. Earlier fixture expectations describe their original capability scope: V8's emphasis-refusal expectation is superseded by V9's supported semantic subset, so do not treat the unchanged historical fixture as the V9 contract.

V8 adds [v8-scenarios.json](../evals/v8-scenarios.json) for import/refusal and evidence-aware revision behavior. Its [portable self-tests](portable-selftests.md) execute actual local files without historical harnesses. Behavioral scenarios assess how the workflow uses those capabilities and respects a partial endpoint; they do not replace the executable tests. Prior-version results retain their historical scope.

V7 adds [v7-scenarios.json](../evals/v7-scenarios.json) to test partial cover planning and independent edition recovery through the clarified production order. Reuse earlier fixtures when their behavior changes; do not label historical results as new runs. Unchanged helper hashes retain their earlier execution evidence with its original scope.

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

V11 adds [v11-scenarios.json](../evals/v11-scenarios.json) for rich-content endpoint discipline and current-release verification with stale proof evidence. Run independent actual-file cases using only their request/raw inputs, withholding evaluator criteria. Keep prior fixtures unchanged; strict-default refusals remain valid while the new rich route is explicit opt-in.

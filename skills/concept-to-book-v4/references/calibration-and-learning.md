# Version 4: calibrate, trace, and learn

Use this guidance with the [Book Foundation](foundation-settings.md) and [source-use ledger](reference-provenance.md). It makes established choices easier to apply, detects drift during creation, and carries useful lessons forward. It requires no private vault, earlier skill version, publishing platform, or particular software.

Add the relevant fields to existing foundation, source, and issue records. Do not require a new file or register for each section below. Scale detail to the project: an outline needs less tracking than an illustrated series.

## 1. Express preferences at the scope they govern

Recover existing user decisions before collecting new preferences. Give each consequential preference a scope:

| Scope | Applies to | Example of scope, not a default |
|---|---|---|
| Author | Work for which the user explicitly establishes an enduring preference | A stated preference for preserving supplied biographical wording |
| Series | The named series and its shared reader experience | A recurring recap policy or shared visual identity |
| Book | The named book or selected narrative material | A particular viewpoint or deliberately unresolved ending |
| Edition | A named format, binding, or output variant | Grayscale art for one print edition |

Use an existing setting ID when available. Record the value, scope, evidence, priority, accepted example, unwanted example, exceptions, and any override. Examples may be brief excerpts, file locations, images, or a plain-language description; never invent user acceptance.

```text
Preference ID / setting:
Value and scope:
Priority: requirement / target / preference
Evidence: explicit user direction / supplied guide / labeled inference
Evidence location and date or version:
Status: established / working assumption / candidate / deferred
Accepted example and what it demonstrates:
Unwanted example and the specific unwanted trait:
Exceptions and local overrides:
Affected work and verification milestone:
```

An explicit preference for one project does not establish an author-wide preference. Repeated behavior can support a candidate inference; retain its uncertainty and apply it only within justified scope. Do not silently write it into global instructions or reuse it as a requirement for unrelated books.

Apply an explicit local override to its stated scope and retain the broader setting elsewhere. Apply a later explicit decision to the work it actually changes. If two applicable requirements still conflict, use an existing priority or present the concrete unresolved tradeoff while continuing independent work.

Use examples to identify qualities, not to require identical wording, equal scene lengths, or replication of another author's distinctive prose. An unwanted example should identify a problem such as repetitive explanation, rather than banning all explanation.

**Complete when:** the next substantial work can distinguish the desired result, unacceptable drift, permitted variation, and applicable exceptions.

## 2. Connect samples into a useful pilot

Select a connected pilot when interaction between choices is uncertain or errors would be expensive to repeat. The pilot carries the same representative unit through the stages relevant to the requested endpoint. It supplements existing samples only where their interaction remains untested.

1. Name the uncertainty and the decision the pilot will inform.
2. Select an existing or planned unit that exposes it: for example, dialogue plus action, a cultural encounter, or a chapter with an illustration and an afterword reference.
3. Reuse accepted outlines, prose, images, and proofs where their inputs remain valid.
4. Carry that unit only as far as the requested deliverable requires.
5. Inspect how the choices work together and record the resulting decisions or remaining uncertainty.
6. Apply supported corrections to the foundation before scaling dependent work.

| Requested endpoint | Appropriate pilot extent |
|---|---|
| Concept or outline | A representative outlined unit with causal turns, research boundaries, and its role in the planned arc |
| Manuscript | Outline to prose to the relevant editorial check |
| Illustrated reading proof | Stable prose to planned asset treatment, assembly, and rendered inspection |
| Publication files | Relevant content and assets through the selected edition's export and applicable technical checks |

Do not manufacture future canon, final metadata, artwork, or cover geometry to complete an early outline. If a pilot uses provisional material, label it and prevent it from silently entering canon or final production. A tested unit establishes evidence for its tested conditions; it does not prove that every chapter or page will pass.

```text
Pilot unit / current inputs:
Uncertainty and intended decision:
Requested endpoint / stages included:
Existing accepted material reused:
Checks and observed result:
Foundation decisions established or changed:
Remaining uncertainty / dependent work:
```

Skip the pilot when valid existing evidence already answers the question or when its cost exceeds its likely benefit. A pilot creates no extra approval gate.

## 3. Check drift where it can change the outcome

During creation, choose brief checks when they offer useful evidence. Triggers include a new viewpoint or scene type, a long drafting run, a newly introduced source, a different contributor, a changed image method, or repeated small defects suggesting a shared cause.

Choose the scope from the risk or opportunity. Inspect relevant passages or assets against the foundation and accepted examples. Avoid fixed review rituals that repeat unchanged evidence.

For each check:

1. State the intended experience or criterion and the specific material inspected.
2. Compare actual work with the benchmark, allowing the documented variation and exceptions.
3. Identify whether there is a defect, a useful refinement, a new direction, or no action needed.
4. Before repair, record what already works and must be preserved.
5. Make the smallest sufficient change, or scope broader revision when the evidence warrants it.
6. Compare the result with both the repair goal and the preservation criteria.
7. Record affected dependencies and the exact review coverage.

Preservation criteria can include character intent, causal consequences, deliberate humor, a distinctive voice, important source distinctions, reader knowledge limits, or an approved image composition. Choose only the criteria relevant to the repair.

```text
Check / issue ID:
Trigger and intended outcome:
Inspected scope / source version:
Benchmark and observed gap or opportunity:
Preserve:
Repair or refinement:
Before/after evidence:
Affected outputs and rechecks:
Coverage and remaining uncertainty:
```

If the repair fixes one problem but damages a protected quality, revise or undo that attempted repair while preserving unrelated newer work. User-authorized changes may replace a previous preservation criterion; record that change instead of defending an obsolete constraint.

A selective check is evidence about its stated scope. Do not describe it as a complete manuscript read, full source consultation, or full rendered-page review. Retain the required integrated and final reviews from the main workflow.

## 4. Link consequential decisions to their implementations

Extend the existing source ledger and issue record with lightweight links where propagation matters:

**Source or user direction → decision or interpretation → exact affected content/assets → verification evidence.**

Use stable IDs or unambiguous file and section references. Record locations specific enough to find the affected work, such as a chapter and scene, afterword entry, asset ID, or edition page tied to an output version. Page numbers alone become unreliable after reflow.

| Link | Record |
|---|---|
| Source or direction | Exact identity, relevant location, actual read scope, and consultation status |
| Decision or interpretation | What was adopted, why, and whether it is a user choice, sourced fact, adaptation, or inference |
| Implementation | Affected chapter/scene, supplement, name entry, image, cover, or build setting |
| Verification | Check ID, reviewed version, method, coverage, result, and remaining limits |

Create detailed links for decisions with meaningful downstream effects: source-dependent claims, reveal rules, character appearance, recurring names, major continuity facts, or edition-wide layout choices. Ordinary wording edits need no elaborate dependency graph.

```text
Decision ID:
Input: source/user-direction ID and exact location
Interpretation or adopted setting:
Evidence status and limitations:
Implemented at: content/asset IDs and versions
Verified by: check IDs and coverage
If changed: affected implementations and evidence to reconsider
```

Keep the distinction between what a source says and what the project invents or infers from it. A historical report documenting source use is evidence of that reported use, not proof of fresh consultation. If a source is missing or unread, record that status and the unresolved question; do not fabricate a passage or imply verification.

When a source or decision changes, follow its links to locate likely effects, then inspect actual dependencies. Recheck changed implementations and any consequences they propagate. Preserve unrelated evidence with unchanged relevant inputs. A link is a navigation aid, not proof that every affected item has been found.

## 5. Learn from substantial rework

When substantial rework occurs, add a short cause and lesson to the existing issue record. Capture enough information to improve future decisions without turning every sentence edit into a retrospective.

| Cause | Useful lesson to consider |
|---|---|
| Missing preference | Was it available earlier, and what concise question or example would have exposed it? |
| Changed preference | What changed in the user's intended result, and what earlier work remains useful? |
| Weak or unrepresentative sample | Which condition did the sample miss, and what would test it next time? |
| Factual or source error | Which research boundary, source check, or interpretation needs improvement? |
| Continuity or execution error | Which shared record or targeted check would have caught the problem sooner? |
| Valuable creative discovery | What improved the story, and what room should future planning preserve for discovery? |

Use an unknown cause when the evidence does not support a conclusion. Do not label a newly supplied preference as something the workflow should necessarily have known earlier.

```text
Issue/change ID and affected work:
Cause, with evidence or uncertainty:
What was redone / what was retained:
Earlier detection opportunity, if one existed:
Resulting benefit or unresolved problem:
Candidate lesson, applicable scope, and exception:
```

At handoff, extract only the lessons likely to help the next project. Separate established user preferences from tentative recommendations. Identify where each lesson belongs: this book, the series, a particular edition, a reusable workflow improvement, or a candidate author preference.

Promote a lesson into the relevant future foundation when its evidence and scope support doing so. Changes to global preferences or the reusable installed skill require the user's actual direction; a project retrospective alone is not that direction.

Optional measurements can record effort spent on preventable rework or recurrence of a known defect when the information is available. Do not invent measurements, penalize creative discovery, or treat fewer revisions as proof of a better book. The goal is more reliable progress toward the intended reader experience.

**Handoff result:** a finished deliverable with an honest evidence trail, a small set of reusable lessons, and clear separation between confirmed preferences, local choices, and open hypotheses.

## 6. Apply calibration and learning to cover work

Read [cover-design-workflow.md](cover-design-workflow.md) when CD01–CD12 apply. The [later dialogue evidence](cover-workflow-example.md) demonstrates why these checks matter; it does not supply universal settings or fresh visual verification.

- **Preference scope and examples (CD01/CD02/CD06–CD08):** record which logo/hierarchy choices apply to the series, which scene/crop or icon applies to a book, and which typography/template treatment applies to an edition. Link the actual accepted front or panel and identify the quality accepted. Mark an unreviewed proposal, unavailable image, or historical approval record honestly. A successful contrast example can be carried across a series only within the user's direction; its exact color is not a universal author preference.
- **Connected pilot (CD03/CD05/CD08–CD10):** choose a unit that combines a demanding title, restrictive physical crop and narrow copy surface when those interactions are uncertain. Carry its actual source art/logo/type, back/flap purpose and relevant edition geometry through a small export and inspection. The longest title may expose fit while another composition exposes a face/crop conflict; add a second unit only when needed. A text-only pilot plan or cropped front preview does not establish a rendered wrap. Stop at the requested endpoint.
- **Drift and preservation (CD04/CD07/CD08/CD10/CD11):** check whether varied scene art has drifted into repetitive casting, whether fixed hierarchy has become inconsistent, or whether fit repairs change copy meaning, identity facts or spoilers. Before contrast/crop/resolution repair identify protected faces, hands, objects, lettering, source layers, text, placement, template geometry and barcode as relevant. Compare actual changes and rendered output; matching bytes in unrelated streams do not prove the repaired image looks right. Do not assume an icon of equal dimensions has equal apparent weight.
- **Decision and evidence links (all CD steps):** use the existing records for source/user ID -> interpretation and scoped decision -> scene/appearance brief, selected image/icon/portrait, copy surface, typography/config -> edition/ISBN/template and page-count basis -> exported hash -> review, receipt and validation scope. Separate selected design previews from technical print derivatives. Follow changed links and inspect likely missing destinations; a stale summary or catalog status cannot certify a file version. Missing original evidence remains missing even when a later report documents its use.
- **Rework causes and lessons (CD11/CD12):** distinguish a new composition/spacing preference from execution drift; an unrepresentative pilot from unavoidable new information; requested pixels from actual returned pixels; and stale selection/status records from a defective file. If repeated generation returns insufficient dimensions, record that capability evidence and select an available, permitted remedy rather than repeating an ineffective request. If restoration is authorized, retain source/method/derivative provenance and do not call reconstructed detail native. If high-resolution small icons trigger a warning, target those objects rather than reprocessing approved scene art. Record separate renewal evidence for the cover and its intended interior.

Keep these entries in the existing foundation, source/asset map and issue record. At handoff, identify which lessons are established project settings and which are candidates for future work. Carry forward unaffected checks only when their relevant inputs are demonstrably unchanged; keep actual output and platform status dated.

# Format reading and accessibility checks

Apply checks to the formats and reading experience requested. A manuscript task does not require an EPUB, PDF or print proof. An HTML proof does not establish EPUB behavior; a PDF preview does not establish physical print quality. Use [production adapters](production-adapters.md) to create supported local outputs, then inspect the actual artifacts. Record capability gaps explicitly instead of treating unavailable checks as passes.

## Define applicable evidence

Recover the selected reader-section inventory, meaningful image roles, navigation and format requirements. For each requested output identify the exact artifact/version, intended use, relevant checks, available methods and missing dependencies. Reuse the existing issue register and [handoff](../assets/templates/handoff.md); no separate accessibility database is required.

| Check record | Include |
|---|---|
| Artifact and method | Exact file/version or computed hash; tool/viewer and relevant environment; source inspection, automated check, rendered inspection, assistive-technology test or physical proof |
| Actual coverage | Sections/pages, navigation routes, images, viewport/text settings, print or thumbnail scale actually examined |
| Observation and result | Concrete observed behavior; passed, failed, blocked, unrun or not applicable |
| Limits and action | Unsupported features, untested coverage, required repair/recheck, or a scoped accepted exception |

Use “not applicable” for a check genuinely outside the format or endpoint, such as interior-image descriptions in a book with no interior images. If a required reading function is unsupported by the exporter, record a gap or blocker. Unsupported is not automatically not applicable. A source declaration, checker result or successful export does not prove the behavior of a reader application, screen reader or printer.

## Check the requested reading experience

| Area | What to inspect when relevant | Evidence limit |
|---|---|---|
| Reading order | Follow the intended sequence through front matter, body, captions, side material, notes and back matter. Inspect structural order where supported and the visible order after export; ensure no missing, duplicate or displaced units | A matching section count or visual page arrangement alone does not establish logical/assistive reading order |
| Navigation | Test the actual contents entries, chapter/section destinations, internal links and note/return links. Check labels, hierarchy and destinations against the selected inventory; check keyboard access where supported and relevant | A valid link target does not prove the link takes the reader to the correct content; source anchors do not prove exported behavior |
| Semantic headings | In structured outputs, use real heading/outline semantics with a meaningful hierarchy and labels; inspect their exported form as well as appearance. Include supporting sections as appropriate | Large or bold text is not evidence of a semantic heading; a styled source document may lose structure during conversion |
| Images and descriptions | Preserve the meaning/function of informative images through supported alternatives; supply useful descriptions for maps, diagrams or other complex content as needed. Treat decorative images deliberately. Keep captions, descriptions and nearby text consistent with intended reader knowledge | Merely filling an alt field does not show an adequate description; exporter support and reader behavior need separate evidence |
| Layout and text | Inspect representative ordinary and demanding content: long headings, chapter openings/endings, notes, captions, tables if present, and integrated art. Check clipping, overlap, lost characters, legibility and relationships between image and text | A source edit or thumbnail preview does not prove readable text in the exported artifact |
| Contrast and cues | Check actual type/background combinations, meaningful boundaries, and information conveyed only through color. Use measurements if a selected requirement calls for them, alongside visual inspection | A visual impression is not a measured ratio; a numeric result alone does not prove the full reading experience |

Descriptions should serve the image's purpose without adding unsupported facts or spoiling later reveals beyond the intended section's knowledge boundary. Where a format cannot carry a required description or reading structure, choose an appropriate supported treatment within the requested scope or state the remaining limitation. Do not silently replace the requested output with a different format and call it complete.

## Adapt to the output

**Editable manuscript or DOCX.** Check actual section order, heading styles/outline structure and navigation where included. Inspect exported descriptions, links and reading structure when they are part of the deliverable. Check the file in an available compatible viewer; name the viewer and coverage. Pagination or assistive behavior in one application does not prove the same behavior elsewhere.

**HTML or reflowable EPUB.** Inspect the requested artifact in an available viewer. Check section order and navigation, document semantics, meaningful text alternatives, link behavior and representative reflow at different text sizes or viewport widths. Watch for fixed sizes or placement that hide content, unreadable image text and excessive horizontal scrolling where it defeats the intended reading experience. An EPUB package also needs its own packaging/navigation checks and reader inspection as applicable; its source HTML or a browser proof alone cannot establish them. Record validator findings with the actual validator/version and report; if no validator or EPUB reader is available, name the unrun checks.

**Fixed-layout or PDF reading output.** Inspect actual pages at reading scale, including page order, image/caption relations, furniture, navigation and any required tags, logical order, text alternatives or bookmarks that the output supports. Check selectable text and missing glyphs where relevant. A visually good PDF can still lack required reading structure. Reflowable-file evidence does not transfer automatically to fixed pages, or the reverse.

**Print-oriented PDF and covers.** Inspect actual-size text, margins, page furniture, image detail and intended color/monochrome reproduction. Examine grayscale output when a monochrome edition is requested or color distinctions must survive grayscale; check symbols, labels and tonal separation. A simulated grayscale preview is evidence of that simulation, not a printed proof or verification of ink/paper behavior. Use actual applicable edition/printer inputs for production checks. Report a local visual proof separately from printer validation or physical proof approval.

**Covers and thumbnails.** When cover work or a catalog image is in scope, inspect the delivered cover at its relevant reading/print scale and a representative thumbnail scale. Check title/author/series hierarchy, contrast and recognizability without relying on full-size zoom. Record the dimensions or scale used; choose thresholds from the project or actual destination rather than inventing a universal thumbnail standard. Follow the applicable [cover workflow](cover-design-workflow.md) for wraps, spines and edition pairs.

## Keep conformance claims within evidence

Do not declare universal accessibility, WCAG conformance, EPUB conformance, or printer acceptance from this checklist. If a particular standard or destination requirement is part of the task, establish its applicable version/scope from current authoritative material when needed, map the required checks, and record their actual results and gaps. A tool with “accessible” or “valid” in its output does not establish checks beyond its documented scope. Local proof capability, automated inspection, assistive-technology testing, human reading, destination validation and physical proof each establish different evidence.

No platform login, credential request, upload, reader contact, new format or physical-proof purchase is implied. Obtain external requirements or access only for the relevant authorized work. Complete feasible local checks and state precisely which dependent commitments remain unsupported.

After repairs, recheck the changed content and affected navigation, neighbors, descriptions or edition-dependent outputs. Keep unaffected evidence when its inputs remain unchanged. Use [mechanical checks](mechanical-checks.md) for supported automation and [integration testing](integration-testing.md) for end-to-end skill evaluation; neither replaces the actual reading checks required for the book.

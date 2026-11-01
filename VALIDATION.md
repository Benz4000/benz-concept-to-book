# Validation and limits

Publication preparation checked on 2026-11-01. Current checkpoint: V10 (10.0.0).

- Every published folder passed skill metadata validation, UTF-8/JSON/YAML/Python parsing where applicable, relative Markdown link checks and a reviewed public-file inventory.
- Versioned ZIPs passed CRC and exact extracted-file SHA-256 comparisons. Each has one top-level skill folder. Executable Python and JavaScript sources match their original version byte for byte.
- All 10 available versions were extracted into an isolated Windows repository. Actual Codex 0.165.0-alpha.1.2 discovery found each expected skill path. This checked installation structure and discovery, without a model turn or changes to the user's installed skills.
- This setup-page version passed local Chromium checks at 1280px and 375px widths: release identity, history length, install request, manual links and measured overflow. The copy handler and failure fallback were tested with an isolated clipboard stub; the user's clipboard was untouched. Representative desktop/mobile pages received a visual review.
- Publication copies omit private project histories, conversation extracts, personal identity/contact details, original vault locations and local test artifacts. Bundled examples are explicitly synthetic. Source originals are preserved.

## Helper execution scope

This publication pass verifies this version's package and Codex discovery. It does not claim a fresh full execution of every historical version's optional production helpers, or an end-to-end real-book acceptance test.

Alternative-platform import paths are documented but untested with these packages. No account installation, authenticated book publishing, paid service, human approval or physical proof is implied. Live release assets and the deployed page are verified separately during the sequential rollout. See [installation](INSTALL.md) and [compatibility](COMPATIBILITY.md).

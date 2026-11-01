# Compatibility and platform setup

Codex is the primary environment. This publication uses ordinary skill folders, supporting references and optional local helpers. Tool permissions and installed runtimes determine which steps can run. The individual packages are standalone skills, not authenticated publishing connectors.

| Platform | Evidence and scope |
|---|---|
| Codex | Tested on Windows during publication: reviewed ZIP extracted into an isolated repository; actual Codex 0.165.0-alpha.1.2 discovery found this skill. Helper and real-book coverage are scoped in [validation](VALIDATION.md). |
| Claude Code | Documented folder import; this package is untested here. |
| Claude web / Desktop Skills | Documented custom-skill ZIP flow; this package is untested here and optional local tools may be unavailable. |
| Cursor | Documented local skill folders; this package is untested here. |
| Gemini CLI | Documented skill-folder/install support; this package is untested here. |

## Codex

Use the install request in [Manual installation](INSTALL.md) or extract the selected folder into a documented local skill location such as `~/.agents/skills/concept-to-book-v7/`. Invoke it with `$concept-to-book-v7` or select it through `/skills` where supported. `agents/openai.yaml` supplies optional Codex presentation metadata. Restart Codex if a change is not detected. [Official skills guidance](https://learn.chatgpt.com/docs/build-skills).

## Claude Code — documented path, untested

Copy the complete folder to `~/.claude/skills/concept-to-book-v7/` for personal local use, or `.claude/skills/concept-to-book-v7/` for a trusted project. Invoke `/concept-to-book-v7` or let the description trigger it. Keep relative references and helper files together. Codex UI metadata, invocation policy and model controls do not become Claude controls. Optional Python/Node/rendering capabilities depend on that environment. [Official Claude Code skills documentation](https://code.claude.com/docs/en/skills).

## Claude web / Desktop Skills — documented ZIP flow, untested

Upload the versioned ZIP containing its single top-level skill folder through Customize > Skills. Enable the skill and request a relevant task. Follow account prerequisites and any upload validation; adapt unsupported host metadata in a separate copy if necessary while retaining `name`, `description` and relative resources. This does not provide local browser binaries or publishing-account access. [Official upload instructions](https://support.claude.com/en/articles/12512180-use-skills-in-claude).

## Cursor — documented local folders, untested

Copy the folder into `.agents/skills/concept-to-book-v7/` or `.cursor/skills/concept-to-book-v7/` in a project, or a documented user-level skills directory. Use `/` to select the skill or request a matching task. Direct GitHub marketplace import needs Cursor plugin packaging; this repository supplies standalone folders. No cloud sync is enabled by these instructions. [Official Cursor skills documentation](https://cursor.com/docs/skills).

## Gemini CLI — documented path, untested

Use a complete folder under a documented `.gemini/skills/` location, or follow `gemini skills install <url-or-path>` for a selected downloaded folder. Verify with `/skills list`; `/skills reload` refreshes discovery. Project trust and activation consent still apply. Preserve relative resources; Codex-specific metadata and commands remain host-specific. [Official Gemini CLI tutorial](https://geminicli.com/docs/cli/tutorials/skills-getting-started/).

Shared `SKILL.md` support establishes a plausible import route, not certification or evidence that every helper works in another host. No alternative-platform installation or authenticated publishing operation was exercised for this release. Sources checked during the current publication preparation.

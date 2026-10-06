# AI workflow used during this exercise

Filled copy of `README.template.md`. The template is unchanged. Configuration records are in `manifest.json`.

This file covers development-time tools only. The model inside the application is separate and is pending: no application model has been selected, and no application model call has been made.

## Tools and models

Confirmed for this bootstrap:

- Cursor 3.23.23. User-reported. Not rechecked in this session.
- Coding-model display name, user-reported and not independently confirmed: Grok 4.7 High. This is not a verified API model ID. Reasoning: High, selected by the user.
- Python 3.12.14, using the existing `.venv`. User-reported. The interpreter path was not recorded in this session.
- Planning-model display name, user-reported and not independently confirmed: ChatGPT-6.1 Sol High. This is not a verified API model ID. It assisted with interpreting the assignment, planning, terminal setup instructions, and inspecting the seed records.

Unavailable, and not recorded as defaults:

- API model IDs for either display name above.
- Temperature, output limits, and any other coding-model parameters. None were changed in a recorded setting, and the product defaults are unknown.
- ChatGPT GitHub connector version and permissions. The connector returned Not Found and made no repository changes. It is a ChatGPT connector, not a Cursor extension.
- Cursor extension inventory. It was not exported and is unavailable. That is separate from the ChatGPT GitHub connector attempt.
- Cursor permission settings. None were exported.

The user may switch the coding model later for cost. That has not happened. When it does, record the new model and the reason.

## Configuration files

| What | Where | Status |
| --- | --- | --- |
| Project instructions | `AGENTS.md` | used, uncommitted |
| Bootstrap instruction | `ai-workflow/prompts/001-bootstrap.md` | used, uncommitted |
| This record | `ai-workflow/manifest.json`, `ai-workflow/README.md` | used, uncommitted |
| Original templates | `ai-workflow/manifest.template.json`, `ai-workflow/README.template.md` | preserved, commit `28ff74bbff53dc4d463a0434c40a78d9d0691d27` |
| Environment name placeholder | `ai-workflow/.env.example` | supplied placeholder only; application names pending |
| Domain rules | `data/domain.md` | source of truth; not an AI prompt |

No project skills, subagents, hooks, or hook scripts exist. No Cursor MCP configuration was added. User-level Cursor settings were not copied.

Restore by keeping `AGENTS.md` at the repository root and the files in `ai-workflow/` at these paths. Do not put API keys, tokens, or credentials in the repo. `.gitignore` already excludes `.env` and `.venv`.

A direct read of `docs/work-log.md` from disk during this review returned 0 bytes. The project-setup entry and the seed-verification entry are not in the saved file.

## One workflow example

Pending. No correction or improvement cycle has been completed, so no example is recorded. The bootstrap instruction itself is saved at `prompts/001-bootstrap.md`.

## Reproduce or replay

Replay is pending. There is no application and no saved model response to replay. `replay_command` in `manifest.json` is `pending`. No hook needs to be enabled.

Known tools when implementation starts: Cursor 3.23.23, the coding model recorded above, and Python 3.12.14 in `.venv`. Application-model replay, once responses exist, must use saved real responses and saved configuration, with credentials left out.

## Decisions and limitations

The user-reported coding-model display name is Grok 4.7 High, with reasoning set to High. ChatGPT, under the user-reported display name ChatGPT-6.1 Sol High, was used only before application code, for planning and seed inspection. Neither display name was independently confirmed, and neither is a verified API model ID. No skills, subagents, or hooks were added.

Initial query limits are engineering settings, not supplied business rules: 2 seconds maximum execution time and 200 rows maximum. Timeouts and truncation must be reported. `AGENTS.md` requires the database connection to enforce read-only access limited to `customers`, `orders`, and `refunds`.

Still open: application provider, API model ID, and parameters; the five reference cases; a replay command; and a real workflow example.

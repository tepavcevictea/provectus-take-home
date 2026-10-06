# 001 — Bootstrap

Saved: 2026-10-06.

This is the instruction that started Provectus Alternative D documentation. Project instructions written from it are in repository-root `AGENTS.md`.

## Instruction

We are starting Provectus Alternative D, Business Data Investigator.
This task is documentation and project instructions only.

Confirmed setup:

- Cursor version: 3.23.23.
- Coding model: Grok 4.7 High.
- Reasoning setting: High, as selected by me.
- Python: 3.12.14, with an existing .venv.
- ChatGPT assisted with interpreting the assignment, planning, terminal setup instructions, and inspecting the seed records.
- ChatGPT's GitHub connector attempted to read the repository, but returned Not Found. It made no repository changes.
- No application model calls have been made.
- I may switch coding models later for cost reasons.

First read:

- data/domain.md
- data/schema.sql
- data/seed.json
- data/expected-seed-results.json
- ai-workflow/manifest.template.json
- ai-workflow/README.template.md
- docs/work-log.md

Then:

1. Copy the AI workflow templates to manifest.json and README.md.
   Preserve the originals. Fill in confirmed development details.
   Keep unfinished application settings explicitly pending.
   Do not invent model IDs, versions, permissions, or checks.
   Explain unavailable details and record defaults only when known.

2. Create a concise root AGENTS.md with these project instructions:

   - Build a local application within the eight-hour working budget.
   - Treat data/domain.md as the source of truth.
   - Preserve original seed files and expected results.
   - Use integer cents and UTC half-open date ranges.
   - Aggregate orders and refunds separately.
   - Limit SQL access to the three supplied tables, read-only.
   - Enforce six query attempts per question, including failures, plus query time and result-size limits.
   - The model must choose a follow-up query using previous results.
   - Support contextual user follow-ups.
   - Ground reported figures in executed results.
   - Show failures, partial results, and missing evidence honestly.
   - Save real model responses and configuration for clearly labelled replay without credentials.
   - Independently verify five reference cases before using them to evaluate the application.
   - Keep documentation brief and update it at meaningful milestones.
   - Record coding-model changes and reasons.
   - Keep credentials and .venv out of Git.
   - Do not claim a check passed unless it was actually performed.

3. Save this instruction under ai-workflow/prompts/001-bootstrap.md and reference it and AGENTS.md in the AI configuration records.

Do not install dependencies, implement application code, modify data, or commit yet. Do not invent a workflow correction example.

Finish by listing the files changed and any missing information.

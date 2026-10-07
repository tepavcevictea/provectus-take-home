# AI workflow used during this exercise

Configuration records are in `manifest.json`. The starter templates `README.template.md` and `manifest.template.json` were committed in `28ff74b` and are no longer in the working tree. Their content remains in that commit.

This file covers development-time tools only. The application default is `gpt-4.1-2025-04-14` through the OpenAI Responses API, temperature 0, max_output_tokens 1500, store false, parallel_tool_calls false, client timeout 20 seconds, retries 0. The original specified model was `gpt-4.1-mini-2025-04-14`. The default changed after one controlled comparison on the same eight cases, prompt, tools, and temperature. Mini remains an explicit override. `gpt-6-luna` was probed and excluded because it rejects `temperature`. One early live investigation failed and is preserved.

## Tools and models

Confirmed for this bootstrap:

- Cursor 3.23.23. User-reported. Not rechecked in this session.
- Coding-model display name, user-reported and not independently confirmed: Grok 4.7 High. This is not a verified API model ID. Reasoning: High, selected by the user.
- Python 3.12.14, using the existing `.venv`. User-reported. The interpreter path was not recorded in this session.
- Planning and review display name, user-reported and not independently confirmed: ChatGPT-6.1 Sol High. This is not a verified API model ID. It was used before application code and again during review, evaluation design, and submission review. Those later discussions were not individually exported. `docs/work-log.md` summarizes the decisions and does not contain an API model ID.
- pytest 9.1.1, installed into `.venv` and pinned in `requirements-dev.txt` from `pip show`.
- Application package `openai` 3.24.0, pinned with its installed dependencies in `requirements.txt` from `pip freeze`. Those versions were not changed when the API packages were added.
- Local API packages, pinned from the versions installed into `.venv`: fastapi 0.142.2, starlette 1.7.0, uvicorn 0.54.0, click 8.5.0, annotated-doc 0.0.5, and opentelemetry-api 1.45.1. TestClient uses httpx 0.28.1, httpcore 1.0.9, and certifi 2026.7.22, pinned in `requirements-dev.txt`.

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
| Project instructions | `AGENTS.md` | used, commit `59dcc17` |
| Bootstrap instruction | `ai-workflow/prompts/001-bootstrap.md` | used, commit `59dcc17` |
| Query-tool instruction | `ai-workflow/prompts/002-sql-tool.md` | used, commit `5ed580b` |
| Review-fix instruction | `ai-workflow/prompts/003-sql-review.md` | used, commit `5ed580b` |
| Agent instruction | `ai-workflow/prompts/004-agent-loop.md` | used, commit `bc0c794` |
| Demo-data instruction | `ai-workflow/prompts/005-generate-demo-data.md` | used, commit `4ee5a57` |
| API and page instruction | `ai-workflow/prompts/006-api-page.md` | used, commit `c87da4f` |
| Demo-data method | `ai-workflow/demo-data.md` | used, commit `4ee5a57` |
| Fixture skill reference | `ai-workflow/reference/generate-assignment-data-SKILL.md` | used as a reference, commit `bc0c794`; not installed as a Cursor skill |
| Application prompt | `investigator/prompts/investigation.md` | used, commit `bc0c794` |
| Workflow example | `ai-workflow/workflow-example.md` | used, commit `5ed580b` |
| Pre-review query tool | `ai-workflow/snapshots/query-tool-before-review.py.txt` | preserved before the fix, commit `5ed580b` |
| Runtime pins | `requirements.txt` | openai 3.24.0 and installed dependencies |
| Development pins | `requirements-dev.txt` | pytest 9.1.1 and installed dependencies |
| This record | `ai-workflow/manifest.json`, `ai-workflow/README.md` | used, first committed in `59dcc17` |
| Starter templates | `README.template.md`, `manifest.template.json` | removed from the working tree; content remains in commit `28ff74b` |
| Environment name placeholder | `.env.example` and `ai-workflow/.env.example` | `OPENAI_API_KEY` name only; value not stored |
| Domain rules | `data/domain.md` | source of truth; not an AI prompt |

The supplied fixture skill was not installed as an active Cursor skill. `ai-workflow/reference/generate-assignment-data-SKILL.md` was read as a reference when the demo fixture was generated. No project skill, subagent, hook, or hook script was created. No Cursor MCP configuration was added. User-level Cursor settings were not copied. The bootstrap prompt still names the starter template paths because that was the instruction at the time. Those files are in commit `28ff74b`, not in the current tree.

Restore by keeping `AGENTS.md` at the repository root and the files in `ai-workflow/` at these paths. Do not put API keys, tokens, or credentials in the repo. `.gitignore` already excludes `.env` and `.venv`.

`docs/work-log.md` records the milestones. Active time was not kept as an exact total.

## One workflow example

`workflow-example.md` records the query-tool review. Four regression tests failed on the preserved module, including a 70,026-byte empty result and a 5.201619915664196 second lock wait. After the fix, `.venv/bin/python -m pytest` reported 14 passed in 2.08s.

## Reproduce or replay

Replay a saved investigation without a key or network:

```text
python -m investigator.cli replay INVESTIGATION_ID
```

That command prints the saved response and does not call the model. No hook needs to be enabled. Mocked tests label saved responses `response_source: mock`. The first live investigation, `inv_030848b96125484bac45bb814b259f84`, is checked in under `investigations/` and was not rewritten. Its second request failed because the SDK dump sent `async_` instead of the API alias `async`. Serialization now uses `to_dict(mode="json")`, which keeps API aliases and omits unset fields.

## Decisions and limitations

The user-reported coding-model display name is Grok 4.7 High, with reasoning set to High. ChatGPT, under the user-reported display name ChatGPT-6.1 Sol High, was used before application code for planning and seed inspection, and later for architecture and review discussion, frontend review, evaluation and golden-set design, adversarial-testing strategy, interpreting live evaluation failures, hardening decisions, model-comparison design, and final submission review. Those later discussions were not individually exported. Neither display name was independently confirmed, and neither is a verified API model ID. No project skill was installed. The fixture skill file was only a reference. No subagents or hooks were added.

Initial query limits are engineering settings, not supplied business rules: 2 seconds maximum execution time, 200 rows maximum, and 64 KiB maximum serialized result size. Timeouts and truncation must be reported. `AGENTS.md` requires the database connection to enforce read-only access limited to `customers`, `orders`, and `refunds`. The query tool is `investigator/query_tool.py`. The investigation agent is `investigator/agent.py`. The local API and page are `investigator/api.py`, `investigator/web.py`, and `investigator/frontend/`. Start them with `.venv/bin/python -m investigator.web`, bound to `127.0.0.1` with one worker.

A later review kept SQL errors, timeouts, and truncation incomplete, scoped evidence IDs to the investigation, and limited `.env` loading to live CLI commands. Replay stays offline. The first live call failed on `input[1].async_` and that report was kept. SDK responses are serialized with API field aliases, and unset optional fields are omitted. New reports record the database path and SHA-256. Follow-ups inherit that database unless an explicit different database is rejected. Older reports without that record are left unchanged and require `--database`. The investigation prompt now asks for both periods, and for the orders and refunds behind a change, without demo answers or SQL. The page shows tables from saved successful SQL results and shows failed, empty, and truncated attempts. It does not hardcode demo answers. Saved-report reads do not call the model. One live request may run at a time. The five reference cases are the expected values for the deterministic evaluation in `tests/test_evaluation.py`. That evaluation does not call the model. A later live comparison did run, on the same eight cases, and is recorded in `evaluation/live-comparison.md`. The pre-hardening run missed a refund-only segment, inspected the schema with PRAGMA, and shadowed the `refunds` table name. The prompt was hardened in general terms. Post-hardening, mini scored 7/8 and `gpt-4.1-2025-04-14` scored 8/8, both at temperature 0, with no unsafe SQL executed. The default model was then set to `gpt-4.1-2025-04-14`. Free-text explanations are not deterministically verified.

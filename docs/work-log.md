# Work log

## Project setup and seed inspection, October 6
- Created and cloned the repository; configured Python 3.12.14
  in .venv; confirmed Git ignores .venv.
- Imported the original D data and AI workflow templates.
- Independently inspected seed.json: August gross/refunds/net
  are 10000/1000/9000 cents; September 10000/3000/7000 cents.
- Both September refunds belong to O3, customer C1, segment small.
- ChatGPT assisted with planning, setup, and reviewing records.
  Cursor assisted with documentation.

## Read-only query tool, October 6
- Added the bounded SQLite query tool in investigator/query_tool.py,
  pytest coverage, and ai-workflow/prompts/002-sql-tool.md.
- Checked: .venv/bin/python -m pytest — 10 passed in 2.07s.
  pytest 9.1.1 is recorded in requirements-dev.txt.

## Query tool review fixes, October 6
- Preserved the pre-review module at
  ai-workflow/snapshots/query-tool-before-review.py.txt.
- Before the fix, four regression tests failed: nested evidence
  leaked; the empty wide alias payload was 70026 bytes; the timeout
  payload was 70026 bytes; a locked database waited 5.201619915664196
  seconds.
- Checked after the fix: .venv/bin/python -m pytest — 14 passed in 2.08s.
  The locked query then returned in 0.000194 seconds.

## Investigation agent and CLI, October 6
- Added the mocked investigation agent, CLI, and application prompt.
  No live model call was made.
- Checked: .venv/bin/python -m pytest — 25 passed in 2.59s.

## Investigation review fixes, October 6
- Before the fix, .venv/bin/python -m pytest --tb=line -q reported
  10 failed, 26 passed in 2.90s. Truncation or a later SQL error could
  still be marked complete. Evidence IDs restarted at E1. Replay omitted
  the saved question, definitions, and SQL. Live commands did not load .env.
- After the fix, .venv/bin/python -m pytest --tb=short -q reported
  36 passed in 2.82s. No live model call was made.

## SDK response serialization, October 6
- The first live investigation, inv_030848b96125484bac45bb814b259f84,
  failed on the second request: Unknown parameter 'input[1].async_'.
  The report is preserved. model_dump(mode="json") wrote the Python
  field name and unset defaults.
- SDK objects now serialize with to_dict(mode="json"), which uses API
  aliases and omits unset fields. A regression builds real SDK response
  objects and mocks the request. No further live call was made.
- Checked: .venv/bin/python -m pytest — 37 passed in 2.80s.

## Investigation prompt, October 6
- Updated investigator/prompts/investigation.md so later investigations
  ask SQL for gross_sales_cents, refunds_cents, and net_sales_cents,
  keep period or segment keys that appear only on the refund side, and
  state in the final explanation that refund reasons are unknown from
  these records. SQL stays model-generated. Saved reports and their
  prompt snapshots were not rewritten. No live call was made.

## Demo dataset, October 6
- scripts/generate_demo_data.py starts from data/seed.json and writes
  data/demo.json, data/demo.sqlite, and data/reference-cases.json.
  Expectations are Python sums over the demo records. The application
  was not used as the answer key. No live call was made.
- Validation passed: unique IDs, foreign keys, nonnegative integer cents,
  YYYY-MM-DD dates, and refund totals within each order amount.
  demo.sqlite integrity_check returned ok and foreign_key_check returned
  no rows. Seed file hashes were unchanged. The default database remains
  data/seed.sqlite.
- Demo size: 10 customers, 30 orders, 8 refunds.
  August gross/refunds/net: 28200/1600/26600 cents.
  September: 28200/4300/23900 cents. Net change: -2700 cents.
- Checked: .venv/bin/python -m pytest — 38 passed in 2.79s.

## Period comparison and database continuity, October 6
- The investigation prompt now says to compare both periods, name the
  orders and refunds that account for a change, and reconcile that
  difference separately from unknown customer motives. No demo figures
  or SQL were added. Saved prompt snapshots were not rewritten.
- New reports store the database's repository-relative path and SHA-256.
  A follow-up inherits that database when --database is omitted and
  stops if the hash changed or a different database is supplied. Older
  reports without a database record require --database and were not
  modified.
- Checked: .venv/bin/python -m pytest — 45 passed in 3.00s.
  No live model call was made.

## Local API and investigation page, October 7
- Added a FastAPI application and a plain page served by the same
  process. Startup is `.venv/bin/python -m investigator.web`, bound to
  127.0.0.1 with one worker. Each live request builds a new agent.
  Dataset choices are seed and demo only. Saved-report list, load, and
  download do not use a credential or call the model.
- Pinned fastapi 0.142.2, starlette 1.7.0, uvicorn 0.54.0, and their
  new installed dependencies. Existing OpenAI pins and model settings
  were not changed. No live model call was made. Existing saved reports
  were not modified.
- Checked: .venv/bin/python -m pytest — 55 passed in 3.50s.

## System evaluation, October 7
- Added 14 scripted system cases in `investigator/evaluation.py`.
  Expected business figures come from `data/reference-cases.json`, and the
  empty-period and absent-segment cases use a separate sum over
  `data/demo.json`. The optional live command is
  `python -m investigator.evaluate --live`. It was not run. Existing
  saved reports were not modified.
- Checked: .venv/bin/python -m pytest — 74 passed in 4.16s.
  No live model call was made.

## Evaluation hardening, October 7
- Added `evaluation/golden_cases.json` as the reviewer-readable case list.
  It points at the reference fixture and the independent demo sum instead of
  copying cent totals. The epistemic phrase check now fails when a caveat and
  an affirmative cause appear together. QueryTool was not changed. The live
  evaluator was not run.
- Checked: .venv/bin/python -m pytest tests/test_evaluation.py — 20 passed in 0.30s.
  .venv/bin/python -m pytest — 75 passed in 3.57s.
  No live model call was made.

## Live model comparison, October 7
- The live command now requires `--model` and records that id. The
  application default remains gpt-4.1-mini-2025-04-14. Prompts and
  QueryTool were not changed. `python -m investigator.evaluate` is the
  command entry.
- Before live calls: .venv/bin/python -m pytest — 77 passed in 3.64s.
- gpt-4.1-mini-2025-04-14 passed 6 of 8 live cases. gpt-6-luna failed
  the first case with an API error that `temperature` is unsupported,
  so the other seven cases were not run. No unsafe SQL executed.
  Fixture hashes were unchanged.
- After: .venv/bin/python -m pytest — 77 passed in 3.63s.

## Instruction and request hardening, October 7
- Requests for gpt-6-luna omit temperature. The default model still sends
  temperature 0 and was not changed. The prompt now states independent
  refund-date attribution, forbids schema-catalog queries, and warns against
  CTE names that shadow customers, orders, or refunds. QueryTool and the
  golden cases were not changed. No live model call was made. The earlier
  evaluation-runs directories were not rewritten. A byte copy of the
  pre-hardening comparison is in evaluation/pre-hardening/.
- Checked: .venv/bin/python -m pytest — 79 passed in 3.76s.
  No live model call was made.

## Post-hardening model comparison, October 7
- Compared gpt-4.1-mini-2025-04-14 and gpt-4.1-2025-04-14 on the same
  eight live cases, both at temperature 0. Prompts, tools, and golden
  cases were not changed between the runs. gpt-6-luna stays an excluded
  compatibility probe. The pre-hardening result directories were not
  rewritten.
- Before: .venv/bin/python -m pytest — 79 passed in 3.67s.
- gpt-4.1-mini passed 7 of 8. gpt-4.1 passed 8 of 8. No unsafe SQL executed.
  Demo and seed hashes were unchanged.
- After: .venv/bin/python -m pytest — 79 passed in 3.69s.

## Default model selection, October 7
- Set the application default to gpt-4.1-2025-04-14 because the
  post-hardening comparison, at temperature 0 with the same prompt and
  tools, scored 8/8 against 7/8 for gpt-4.1-mini. Mini remains an
  explicit override. gpt-6-luna stays a compatibility probe.
- Checked: .venv/bin/python -m pytest — 79 passed in 3.86s.
  .venv/bin/python -m pytest tests/test_evaluation.py — 21 passed in 0.27s.
  No live model call was made.

ChatGPT was also used during implementation for architecture and review discussion, frontend review, evaluation and golden-set design, adversarial-testing strategy, interpreting live failures, hardening decisions, model-comparison design, and the final repository review. Those discussions were not individually exported. The milestone entries above and the commit history record the decisions.

Active time was not kept as an exact total.

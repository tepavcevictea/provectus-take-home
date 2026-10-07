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
- Active time: not yet entered.

## Read-only query tool, October 6
- Added the bounded SQLite query tool in investigator/query_tool.py,
  pytest coverage, and ai-workflow/prompts/002-sql-tool.md.
- Checked: .venv/bin/python -m pytest — 10 passed in 2.07s.
  pytest 9.1.1 is recorded in requirements-dev.txt.
- Active time: not yet entered.

## Query tool review fixes, October 6
- Preserved the pre-review module at
  ai-workflow/snapshots/query-tool-before-review.py.txt.
- Before the fix, four regression tests failed: nested evidence
  leaked; the empty wide alias payload was 70026 bytes; the timeout
  payload was 70026 bytes; a locked database waited 5.201619915664196
  seconds.
- Checked after the fix: .venv/bin/python -m pytest — 14 passed in 2.08s.
  The locked query then returned in 0.000194 seconds.
- Active time: not yet entered.

## Investigation agent and CLI, October 6
- Added the mocked investigation agent, CLI, and application prompt.
  No live model call was made.
- Checked: .venv/bin/python -m pytest — 25 passed in 2.59s.
- Active time: not yet entered.

## Investigation review fixes, October 6
- Before the fix, .venv/bin/python -m pytest --tb=line -q reported
  10 failed, 26 passed in 2.90s. Truncation or a later SQL error could
  still be marked complete. Evidence IDs restarted at E1. Replay omitted
  the saved question, definitions, and SQL. Live commands did not load .env.
- After the fix, .venv/bin/python -m pytest --tb=short -q reported
  36 passed in 2.82s. No live model call was made.
- Active time: not yet entered.

## SDK response serialization, October 6
- The first live investigation, inv_030848b96125484bac45bb814b259f84,
  failed on the second request: Unknown parameter 'input[1].async_'.
  The report is preserved. model_dump(mode="json") wrote the Python
  field name and unset defaults.
- SDK objects now serialize with to_dict(mode="json"), which uses API
  aliases and omits unset fields. A regression builds real SDK response
  objects and mocks the request. No further live call was made.
- Checked: .venv/bin/python -m pytest — 37 passed in 2.80s.
- Active time: not yet entered.

## Investigation prompt, October 6
- Updated investigator/prompts/investigation.md so later investigations
  ask SQL for gross_sales_cents, refunds_cents, and net_sales_cents,
  keep period or segment keys that appear only on the refund side, and
  state in the final explanation that refund reasons are unknown from
  these records. SQL stays model-generated. Saved reports and their
  prompt snapshots were not rewritten. No live call was made.
- Active time: not yet entered.

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
- Active time: not yet entered.

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
- Active time: not yet entered.

Active time so far: 2.5 hours, including planning.
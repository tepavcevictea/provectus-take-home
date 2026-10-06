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

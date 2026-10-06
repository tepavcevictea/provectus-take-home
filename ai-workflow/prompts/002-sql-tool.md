# 002 — SQL tool

Saved: 2026-10-06.

This is the instruction for the bounded, read-only SQLite query tool. Project instructions remain in repository-root `AGENTS.md`.

## Instruction

Implement the first application milestone: the bounded, read-only
SQLite query tool. Read AGENTS.md and the supplied data files first.

1. Fix the empty work log by writing these confirmed facts directly
   to docs/work-log.md:

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

   Update stale statements about the empty log in the AI documents.
   Do not invent time spent.

2. Create a small Python application package and query-tool module.
   Use the existing seed.sqlite without modifying it.

   Requirements:
   - Open a fixed application-selected database path in read-only mode.
     SQL callers cannot choose another file.
   - Enforce an SQLite authorizer that allows reads only from
     customers, orders, and refunds, with permitted read operations
     and functions.
   - Reject writes, schema changes, ATTACH, PRAGMA, extension loading,
     and access to other tables or SQLite metadata.
   - Execute one statement per call. Support ordinary SELECT and
     read-only WITH queries. Do not rely on a SELECT-prefix check.
   - Enforce the 2-second execution limit, including result fetching.
   - Return at most 200 rows and cap serialized result size at 64 KiB.
     Report truncation explicitly.
   - Return structured columns, rows, status, and errors.
   - Keep a question-scoped budget of six attempts. Errors and rejected
     SQL consume attempts. Calls after exhaustion must not execute.
   - Retain each attempted SQL request and its result or failure,
     associated with its question. Make the records JSON-serializable.
   - Handle malformed SQL, empty results, timeout, and budget exhaustion.

3. Add meaningful pytest tests:
   - Seed database records agree with seed.json.
   - Correct separate aggregations produce the independently checked
     August and September totals.
   - O3's two refunds do not duplicate its sales in the correct query.
   - Write attempts are rejected and the database stays unchanged.
   - Unauthorized operations and multi-statement requests are rejected.
   - Failed and rejected queries consume the shared question budget;
     the seventh request cannot execute.
   - Empty results, row/byte limits, and timeout are handled visibly.

   Use temporary test databases where needed. Preserve supplied files.
   Install pytest using .venv/bin/python and record its actual installed
   version in requirements-dev.txt.

4. Save this instruction as ai-workflow/prompts/002-sql-tool.md.
   Update AI configuration references and add one brief work-log entry
   with actual test results. Do not fabricate a correction example.

Run the tests. Finish with changed files, the exact test command,
results, and limitations. Do not implement the model integration,
API, or UI yet. Do not commit.

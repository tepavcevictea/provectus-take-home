# 003 — SQL review

Saved: 2026-10-06.

This is the instruction for the query-tool review fixes. The pre-review module is preserved at `ai-workflow/snapshots/query-tool-before-review.py.txt`. The correction write-up is `ai-workflow/workflow-example.md`.

## Instruction

Independent review reproduced three bugs in query_tool.py.
Fix these within the existing scope.

Before changing the implementation:

- Preserve its current version at
  ai-workflow/snapshots/query-tool-before-review.py.txt.
- Add regression tests and run them against the current code.
  Record which fail, then implement the fixes.

1. Evidence isolation
   execute() and history() return shallow copies. Nested columns and
   rows still reference internal history.
   Ensure changing returned results or history cannot modify stored
   evidence. Test nested mutations through both methods.

2. Byte cap
   SELECT 1 AS "<70,000-character alias>" WHERE 0 returns status ok
   with a 70,026-byte columns/rows payload.
   Enforce the cap on column metadata before fetching, including
   empty results. Error and timeout result payloads must also respect
   the cap. Oversized metadata must produce a clear bounded failure.

3. Database lock waiting
   Hold BEGIN EXCLUSIVE on a temporary database through another
   connection, then query it using QueryTool.
   The current implementation waits about five seconds because
   sqlite3.connect uses its default lock timeout.
   Set a bounded or zero lock wait so it cannot exceed the question's
   query execution deadline. Report lock failures clearly.
   Add an elapsed-time regression check with reasonable tolerance.

Rerun the full suite. Preserve existing permission and budget checks.

Save this instruction as ai-workflow/prompts/003-sql-review.md.
Document this real review and correction in
ai-workflow/workflow-example.md, with actual before/after results.
Update the manifest references and one brief work-log entry.

Do not claim the fixes passed until tests run. Do not commit yet.
Finish with the test results and a concise explanation of the fixes.

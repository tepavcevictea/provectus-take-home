# Workflow example

Instruction excerpt from `prompts/003-sql-review.md`: fix three reproduced bugs in `investigator/query_tool.py`, add regression tests, and run those tests on the current code before changing it.

Configuration involved: `AGENTS.md` engineering limits (2 seconds, 200 rows, 64 KiB) and the query tool saved before edits at `snapshots/query-tool-before-review.py.txt`.

## Check before the change

Command:

`.venv/bin/python -m pytest tests/test_query_tool.py -k "isolate_nested or byte_cap or execution_deadline" --tb=short`

Result: 4 failed, 10 deselected, in 5.34s.

- `test_execute_and_history_isolate_nested_evidence` failed because a nested edit of the `execute()` result changed stored history. The stored columns became `changed-column` plus `extra-column`.
- `test_empty_result_column_metadata_respects_byte_cap` failed: `SELECT 1 AS "<70,000-character alias>" WHERE 0` produced a columns/rows payload of 70,026 bytes, above the 65,536 byte cap.
- `test_error_and_timeout_payloads_respect_byte_cap` failed on the timeout query: columns held the 70,000-character alias, rows were empty, and the payload was 70,026 bytes.
- `test_locked_database_fails_within_the_execution_deadline` failed: elapsed time was 5.201619915664196 seconds, which is not below 2.75 seconds.

## Correction

`execute()` and `history()` now deep-copy records, including nested columns and rows. Column metadata is measured before rows are fetched. Oversized metadata returns an error and omits the alias: "Column metadata exceeds the 65536 byte serialized result cap. The result was omitted." Error text and timeout payloads are bounded the same way. The read-only connection uses a zero SQLite lock timeout instead of the 5 second default. A lock failure says: "Database is locked. The query did not wait for the lock, so the wait cannot exceed the execution deadline."

## Check after the change

The same four tests: 4 passed, 10 deselected, in 0.05s.

A locked temporary database then returned that lock error in 0.000194 seconds. The empty wide-alias query returned status `error` with a 24-byte columns/rows payload.

Full suite:

`.venv/bin/python -m pytest`

14 passed in 2.08s.

"""Tests for the bounded read-only SQLite query tool."""

from __future__ import annotations

import hashlib
import json
import shutil
import signal
import sqlite3
import time
from pathlib import Path

from investigator.query_tool import (
    MAX_RESULT_BYTES,
    MAX_ROWS,
    TIMEOUT_SECONDS,
    QueryTool,
    open_query_tool,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DATABASE = REPO_ROOT / "data" / "seed.sqlite"
SEED_JSON = REPO_ROOT / "data" / "seed.json"
EXPECTED_RESULTS = REPO_ROOT / "data" / "expected-seed-results.json"
SCHEMA_SQL = REPO_ROOT / "data" / "schema.sql"
SEED_HASH = hashlib.sha256(SEED_DATABASE.read_bytes()).hexdigest()


def test_seed_database_records_agree_with_seed_json() -> None:
    seed = json.loads(SEED_JSON.read_text())
    tool = open_query_tool()

    customers = tool.execute(
        "seed-records",
        "SELECT customer_id, segment FROM customers ORDER BY customer_id",
    )
    orders = tool.execute(
        "seed-records",
        "SELECT order_id, customer_id, order_date, amount_cents FROM orders ORDER BY order_id",
    )
    refunds = tool.execute(
        "seed-records",
        "SELECT refund_id, order_id, refund_date, amount_cents FROM refunds ORDER BY refund_id",
    )

    assert customers["status"] == "ok"
    assert orders["status"] == "ok"
    assert refunds["status"] == "ok"
    assert customers["rows"] == [[row["customer_id"], row["segment"]] for row in seed["customers"]]
    assert orders["rows"] == [
        [row["order_id"], row["customer_id"], row["order_date"], row["amount_cents"]]
        for row in seed["orders"]
    ]
    assert refunds["rows"] == [
        [row["refund_id"], row["order_id"], row["refund_date"], row["amount_cents"]]
        for row in seed["refunds"]
    ]


def test_separate_aggregations_match_august_and_september_totals() -> None:
    expected = json.loads(EXPECTED_RESULTS.read_text())
    tool = open_query_tool()
    result = tool.execute(
        "monthly-totals",
        """
        WITH gross AS (
            SELECT
                CASE
                    WHEN order_date >= '2026-08-01' AND order_date < '2026-09-01' THEN 'august'
                    WHEN order_date >= '2026-09-01' AND order_date < '2026-10-01' THEN 'september'
                END AS period,
                SUM(amount_cents) AS gross_cents
            FROM orders
            GROUP BY period
        ),
        period_refunds AS (
            SELECT
                CASE
                    WHEN refund_date >= '2026-08-01' AND refund_date < '2026-09-01' THEN 'august'
                    WHEN refund_date >= '2026-09-01' AND refund_date < '2026-10-01' THEN 'september'
                END AS period,
                SUM(amount_cents) AS refunds_cents
            FROM refunds
            GROUP BY period
        )
        SELECT
            gross.period,
            gross.gross_cents,
            period_refunds.refunds_cents,
            gross.gross_cents - period_refunds.refunds_cents AS net_cents
        FROM gross
        JOIN period_refunds ON period_refunds.period = gross.period
        ORDER BY gross.period
        """,
    )
    assert result["status"] == "ok"
    assert result["error"] is None
    assert result["rows"] == [
        ["august", 10000, 1000, 9000],
        ["september", 10000, 3000, 7000],
    ]
    assert result["rows"][0][1:] == [
        expected["periods"][0]["gross_cents"],
        expected["periods"][0]["refunds_cents"],
        expected["periods"][0]["net_cents"],
    ]
    assert result["rows"][1][1:] == [
        expected["periods"][1]["gross_cents"],
        expected["periods"][1]["refunds_cents"],
        expected["periods"][1]["net_cents"],
    ]


def test_o3_refunds_do_not_duplicate_its_sales() -> None:
    tool = open_query_tool()
    result = tool.execute(
        "o3-sales",
        """
        WITH order_refunds AS (
            SELECT order_id, SUM(amount_cents) AS refunds_cents
            FROM refunds
            GROUP BY order_id
        )
        SELECT
            orders.order_id,
            orders.amount_cents AS gross_cents,
            order_refunds.refunds_cents
        FROM orders
        JOIN order_refunds ON order_refunds.order_id = orders.order_id
        WHERE orders.order_id = 'O3'
        """,
    )
    assert result["status"] == "ok"
    assert result["rows"] == [["O3", 5000, 3000]]


def test_write_attempts_are_rejected_and_database_stays_unchanged(tmp_path: Path) -> None:
    database = tmp_path / "copy.sqlite"
    shutil.copy(SEED_DATABASE, database)
    before = _sha256(database)
    tool = QueryTool(database)
    statements = [
        "INSERT INTO customers (customer_id, segment) VALUES ('C9', 'small')",
        "UPDATE customers SET segment = 'changed' WHERE customer_id = 'C1'",
        "DELETE FROM refunds",
        "CREATE TABLE extra (id TEXT)",
        "DROP TABLE customers",
    ]
    for sql in statements:
        result = tool.execute("writes", sql)
        assert result["status"] == "error"
        assert result["rows"] == []
        assert result["error"]
        assert result["executed"] is True
    assert _sha256(database) == before
    with sqlite3.connect(database) as connection:
        counts = (
            connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0],
        )
    assert counts == (2, 4, 3)


def test_unauthorized_operations_and_multi_statement_requests_are_rejected(tmp_path: Path) -> None:
    database = tmp_path / "guard.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE secrets (secret_id TEXT PRIMARY KEY, note TEXT)")
        connection.execute("INSERT INTO secrets VALUES ('S1', 'hidden')")
        connection.execute("INSERT INTO customers VALUES ('C1', 'small')")
    before = _sha256(database)
    tool = QueryTool(database)
    rejected = [
        "PRAGMA table_info(customers)",
        "PRAGMA user_version",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT name FROM sqlite_master",
        "SELECT name FROM sqlite_schema",
        "SELECT * FROM pragma_table_info('customers')",
        "SELECT load_extension('missing')",
        "SELECT sqlite_version()",
        "SELECT note FROM secrets",
        "SELECT customer_id FROM customers; DROP TABLE customers",
    ]
    for index, sql in enumerate(rejected):
        result = tool.execute(f"reject-{index}", sql)
        assert result["status"] == "error", sql
        assert result["rows"] == []
        assert result["error"]
        assert result["counts_against_budget"] is True
    visible = tool.execute(
        "still-readable",
        "SELECT customer_id FROM customers ORDER BY customer_id",
    )
    assert visible["status"] == "ok"
    assert visible["rows"] == [["C1"]]
    assert _sha256(database) == before


def test_failures_consume_the_question_budget_and_the_seventh_does_not_execute(tmp_path: Path) -> None:
    database = tmp_path / "budget.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO customers VALUES ('C1', 'small')")
    tool = QueryTool(database)
    failures = [
        "THIS IS NOT SQL",
        "SELECT * FROM customers; SELECT * FROM orders",
        "INSERT INTO customers (customer_id, segment) VALUES ('C9', 'small')",
        "PRAGMA user_version",
        "SELECT name FROM sqlite_master",
        "DELETE FROM customers",
    ]
    for sql in failures:
        result = tool.execute("shared-question", sql)
        assert result["status"] == "error"
        assert result["executed"] is True
        assert result["counts_against_budget"] is True
    blocked = tool.execute("shared-question", "SELECT customer_id FROM customers")
    assert blocked["status"] == "budget_exhausted"
    assert blocked["executed"] is False
    assert blocked["rows"] == []
    assert blocked["counts_against_budget"] is False
    assert "not executed" in blocked["error"]
    history = tool.history("shared-question")
    assert len(history) == 7
    assert [item["attempt_number"] for item in history[:6]] == [1, 2, 3, 4, 5, 6]
    assert history[6]["executed"] is False
    json.dumps(history)
    other = tool.execute("another-question", "SELECT customer_id FROM customers")
    assert other["status"] == "ok"
    assert other["rows"] == [["C1"]]
    assert other["attempt_number"] == 1


def test_empty_results_are_visible() -> None:
    tool = open_query_tool()
    result = tool.execute(
        "empty",
        "SELECT order_id, amount_cents FROM orders WHERE order_id = 'missing'",
    )
    assert result["status"] == "ok"
    assert result["columns"] == ["order_id", "amount_cents"]
    assert result["rows"] == []
    assert result["truncated"] is False
    assert result["truncation_reason"] is None
    assert result["error"] is None


def test_row_and_byte_limits_are_reported(tmp_path: Path) -> None:
    database = tmp_path / "limits.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        for number in range(MAX_ROWS + 1):
            connection.execute(
                "INSERT INTO customers (customer_id, segment) VALUES (?, ?)",
                (f"C{number:03d}", "small"),
            )
    tool = QueryTool(database)
    by_rows = tool.execute(
        "row-limit",
        "SELECT customer_id FROM customers ORDER BY customer_id",
    )
    assert by_rows["status"] == "truncated"
    assert by_rows["truncation_reason"] == "row_limit"
    assert by_rows["truncated"] is True
    assert len(by_rows["rows"]) == MAX_ROWS
    assert by_rows["rows"][0] == ["C000"]
    assert by_rows["rows"][-1] == [f"C{MAX_ROWS - 1:03d}"]

    wide = tmp_path / "wide.sqlite"
    _create_database(wide)
    small = "ok"
    large = "x" * (MAX_RESULT_BYTES + 1000)
    with sqlite3.connect(wide) as connection:
        connection.execute("INSERT INTO customers VALUES ('C1', ?)", (small,))
        connection.execute("INSERT INTO customers VALUES ('C2', ?)", (large,))
    wide_tool = QueryTool(wide)
    by_bytes = wide_tool.execute(
        "byte-limit",
        "SELECT customer_id, segment FROM customers ORDER BY customer_id",
    )
    assert by_bytes["status"] == "truncated"
    assert by_bytes["truncation_reason"] == "byte_limit"
    assert by_bytes["truncated"] is True
    assert by_bytes["rows"] == [["C1", small]]
    assert tool.timeout_seconds == TIMEOUT_SECONDS
    assert tool.max_rows == MAX_ROWS
    assert tool.max_result_bytes == MAX_RESULT_BYTES


def test_timeout_is_reported(tmp_path: Path) -> None:
    database = tmp_path / "slow.sqlite"
    _create_database(database)
    tool = QueryTool(database)
    assert tool.timeout_seconds == 2.0

    def _alarm(signum: int, frame: object) -> None:
        del signum, frame
        raise TimeoutError("query tool did not stop the long query")

    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(8)
    try:
        result = tool.execute(
            "timeout",
            """
            WITH RECURSIVE series(n) AS (
                SELECT 1
                UNION ALL
                SELECT n + 1 FROM series WHERE n < 1000000000
            )
            SELECT SUM(n) FROM series
            """,
        )
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)

    assert result["status"] == "error"
    assert result["executed"] is True
    assert result["rows"] == []
    assert result["error"] == "Query timed out after 2 seconds."
    json.dumps(result)


def test_execute_and_history_isolate_nested_evidence(tmp_path: Path) -> None:
    database = tmp_path / "evidence.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO customers VALUES ('C1', 'small')")
    tool = QueryTool(database)
    result = tool.execute("evidence", "SELECT customer_id, segment FROM customers")
    assert result["status"] == "ok"
    result["columns"].append("extra-column")
    result["columns"][0] = "changed-column"
    result["rows"][0].append("extra-cell")
    result["rows"][0][0] = "changed-cell"
    result["rows"].append(["new-row", "new-segment"])

    stored = tool.history("evidence")
    assert stored[0]["columns"] == ["customer_id", "segment"]
    assert stored[0]["rows"] == [["C1", "small"]]

    stored[0]["columns"].append("history-column")
    stored[0]["columns"][0] = "history-changed"
    stored[0]["rows"][0].append("history-cell")
    stored[0]["rows"][0][1] = "history-segment"
    stored[0]["rows"].append(["history-row", "history-segment"])

    reread = tool.history("evidence")
    assert reread[0]["columns"] == ["customer_id", "segment"]
    assert reread[0]["rows"] == [["C1", "small"]]
    assert result["columns"] != reread[0]["columns"]
    assert result["rows"] != reread[0]["rows"]


def test_empty_result_column_metadata_respects_byte_cap(tmp_path: Path) -> None:
    database = tmp_path / "metadata.sqlite"
    _create_database(database)
    alias = "a" * 70_000
    tool = QueryTool(database)
    result = tool.execute("wide-metadata", f'SELECT 1 AS "{alias}" WHERE 0')
    payload_bytes = _columns_rows_payload_bytes(result["columns"], result["rows"])
    assert payload_bytes <= MAX_RESULT_BYTES
    assert result["status"] == "error"
    assert result["columns"] == []
    assert result["rows"] == []
    assert result["error"]
    assert alias not in result["error"]
    assert "cap" in result["error"].lower()


def test_error_and_timeout_payloads_respect_byte_cap(tmp_path: Path) -> None:
    database = tmp_path / "payloads.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO customers VALUES ('C1', 'small')")
    alias = "b" * 70_000
    tool = QueryTool(database, timeout_seconds=0.3)

    errored = tool.execute("wide-error", f'SELECT 1 AS "{alias}" FROM missing_table')
    assert _columns_rows_payload_bytes(errored["columns"], errored["rows"]) <= MAX_RESULT_BYTES
    assert errored["status"] == "error"
    assert alias not in (errored["error"] or "")

    timed_out = tool.execute(
        "wide-timeout",
        f"""
        WITH RECURSIVE series(n) AS (
            SELECT 1
            UNION ALL
            SELECT n + 1 FROM series WHERE n < 1000000000
        )
        SELECT n AS "{alias}" FROM series
        """,
    )
    assert _columns_rows_payload_bytes(timed_out["columns"], timed_out["rows"]) <= MAX_RESULT_BYTES
    assert timed_out["status"] == "error"
    assert timed_out["columns"] == []
    assert timed_out["rows"] == []
    assert alias not in (timed_out["error"] or "")
    assert timed_out["error"]


def test_locked_database_fails_within_the_execution_deadline(tmp_path: Path) -> None:
    database = tmp_path / "locked.sqlite"
    _create_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO customers VALUES ('C1', 'small')")
    holder = sqlite3.connect(database, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        tool = QueryTool(database)
        started = time.monotonic()
        result = tool.execute("locked", "SELECT customer_id FROM customers")
        elapsed = time.monotonic() - started
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert result["status"] == "error"
    assert result["rows"] == []
    assert result["error"]
    assert "lock" in result["error"].lower()
    assert elapsed < tool.timeout_seconds + 0.75


def test_supplied_seed_file_is_unchanged() -> None:
    assert hashlib.sha256(SEED_DATABASE.read_bytes()).hexdigest() == SEED_HASH


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _columns_rows_payload_bytes(columns: list[str], rows: list[list[object]]) -> int:
    payload = {"columns": columns, "rows": rows}
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

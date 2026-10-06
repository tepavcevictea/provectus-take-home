"""Application prompt, schema snapshot, and the SQL tool definition."""

from __future__ import annotations

from pathlib import Path

from investigator.query_tool import REPO_ROOT

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "investigation.md"
SCHEMA_PATH = REPO_ROOT / "data" / "schema.sql"
MAX_PURPOSE_CHARACTERS = 200

ASSUMPTIONS = [
    "Stored dates are ISO-8601 calendar dates (YYYY-MM-DD). Lexicographic comparison matches chronological order for that format.",
    "Query time, row, byte, and attempt limits are engineering settings, not business rules.",
]

BUSINESS_DEFINITIONS = [
    "Use customers, orders, and refunds. IDs link refunds to orders and orders to customers; one order can have multiple refunds.",
    "Gross sales for a period sum orders by order_date. Refunds for that period sum refunds by refund_date. Net sales equal gross sales minus refunds. Use UTC dates and half-open periods: start included, end excluded.",
    "Use integer USD cents. Group order and refund totals separately before combining them; joining raw refund rows to orders can repeat order amounts.",
    "Assign refunds to the segment of the customer on the original order. The records show amounts and dates, not why a customer requested a refund.",
]


def load_prompt_text() -> str:
    return PROMPT_PATH.read_text()


def load_schema_text() -> str:
    return SCHEMA_PATH.read_text()


def build_instructions() -> str:
    return load_prompt_text().rstrip() + "\n\n## Schema\n\n" + load_schema_text().rstrip() + "\n"


def sql_tool() -> dict[str, object]:
    return {
        "type": "function",
        "name": "request_sql",
        "description": (
            "Run one read-only SQL statement against customers, orders, and refunds. "
            "Call it once, wait for the evidence result, then decide whether another query is useful."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "purpose": {
                    "type": "string",
                    "description": (
                        "Short reason for this query, at most 200 characters, "
                        "based on the question and evidence already returned."
                    ),
                },
                "sql": {
                    "type": "string",
                    "description": "One read-only SQL statement.",
                },
            },
            "required": ["purpose", "sql"],
        },
    }

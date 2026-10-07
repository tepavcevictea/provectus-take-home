"""Build the demo dataset from the supplied seed.

The script reads data/seed.json and data/schema.sql. It writes data/demo.json,
data/demo.sqlite, and data/reference-cases.json. It does not modify the seed
files, investigation reports, or the application's default database.

Added rows are listed below. Nothing is random. Expected figures are Python
sums over those records, not application queries and not model-written SQL.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SEED_JSON = DATA_DIR / "seed.json"
SCHEMA_SQL = DATA_DIR / "schema.sql"
DEMO_JSON = DATA_DIR / "demo.json"
DEMO_SQLITE = DATA_DIR / "demo.sqlite"
REFERENCE_JSON = DATA_DIR / "reference-cases.json"

AUGUST = (date(2026, 8, 1), date(2026, 9, 1))
SEPTEMBER = (date(2026, 9, 1), date(2026, 10, 1))
DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")

ADDED_CUSTOMERS = [
    {"customer_id": "C3", "segment": "medium"},
    {"customer_id": "C4", "segment": "small"},
    {"customer_id": "C5", "segment": "small"},
    {"customer_id": "C6", "segment": "large"},
    {"customer_id": "C7", "segment": "large"},
    {"customer_id": "C8", "segment": "small"},
    {"customer_id": "C9", "segment": "medium"},
    {"customer_id": "C10", "segment": "large"},
]

ADDED_ORDERS = [
    {"order_id": "O5", "customer_id": "C4", "order_date": "2026-08-01", "amount_cents": 1500},
    {"order_id": "O6", "customer_id": "C6", "order_date": "2026-09-01", "amount_cents": 2500},
    {"order_id": "O7", "customer_id": "C10", "order_date": "2026-10-01", "amount_cents": 4000},
    {"order_id": "O8", "customer_id": "C3", "order_date": "2026-08-18", "amount_cents": 3000},
    {"order_id": "O9", "customer_id": "C9", "order_date": "2026-08-28", "amount_cents": 2000},
    {"order_id": "O10", "customer_id": "C3", "order_date": "2026-07-20", "amount_cents": 1000},
    {"order_id": "O11", "customer_id": "C9", "order_date": "2026-10-05", "amount_cents": 1200},
    {"order_id": "O12", "customer_id": "C5", "order_date": "2026-09-15", "amount_cents": 4000},
    {"order_id": "O13", "customer_id": "C4", "order_date": "2026-08-03", "amount_cents": 800},
    {"order_id": "O14", "customer_id": "C5", "order_date": "2026-08-07", "amount_cents": 900},
    {"order_id": "O15", "customer_id": "C8", "order_date": "2026-08-12", "amount_cents": 1100},
    {"order_id": "O16", "customer_id": "C1", "order_date": "2026-08-22", "amount_cents": 700},
    {"order_id": "O17", "customer_id": "C6", "order_date": "2026-08-04", "amount_cents": 1600},
    {"order_id": "O18", "customer_id": "C7", "order_date": "2026-08-14", "amount_cents": 1800},
    {"order_id": "O19", "customer_id": "C10", "order_date": "2026-08-19", "amount_cents": 1400},
    {"order_id": "O20", "customer_id": "C2", "order_date": "2026-08-25", "amount_cents": 1300},
    {"order_id": "O21", "customer_id": "C6", "order_date": "2026-08-31", "amount_cents": 2100},
    {"order_id": "O22", "customer_id": "C4", "order_date": "2026-09-02", "amount_cents": 800},
    {"order_id": "O23", "customer_id": "C5", "order_date": "2026-09-08", "amount_cents": 900},
    {"order_id": "O24", "customer_id": "C8", "order_date": "2026-09-12", "amount_cents": 1100},
    {"order_id": "O25", "customer_id": "C1", "order_date": "2026-09-18", "amount_cents": 700},
    {"order_id": "O26", "customer_id": "C6", "order_date": "2026-09-03", "amount_cents": 1600},
    {"order_id": "O27", "customer_id": "C7", "order_date": "2026-09-14", "amount_cents": 1800},
    {"order_id": "O28", "customer_id": "C10", "order_date": "2026-09-19", "amount_cents": 1400},
    {"order_id": "O29", "customer_id": "C2", "order_date": "2026-09-25", "amount_cents": 1300},
    {"order_id": "O30", "customer_id": "C7", "order_date": "2026-09-30", "amount_cents": 2100},
]

ADDED_REFUNDS = [
    {"refund_id": "RF4", "order_id": "O8", "refund_date": "2026-09-12", "amount_cents": 800},
    {"refund_id": "RF5", "order_id": "O2", "refund_date": "2026-09-01", "amount_cents": 500},
    {"refund_id": "RF6", "order_id": "O5", "refund_date": "2026-08-01", "amount_cents": 200},
    {"refund_id": "RF7", "order_id": "O30", "refund_date": "2026-10-01", "amount_cents": 400},
    {"refund_id": "RF8", "order_id": "O9", "refund_date": "2026-08-31", "amount_cents": 400},
]


def main() -> None:
    seed = json.loads(SEED_JSON.read_text())
    demo = {
        "customers": seed["customers"] + ADDED_CUSTOMERS,
        "orders": seed["orders"] + ADDED_ORDERS,
        "refunds": seed["refunds"] + ADDED_REFUNDS,
    }
    validate(demo, seed)
    periods = {
        "august": totals(demo, AUGUST),
        "september": totals(demo, SEPTEMBER),
    }
    require_refund_driven_decline(periods)
    reference = build_reference(demo, periods)
    write_json(DEMO_JSON, demo)
    write_sqlite(demo)
    write_json(REFERENCE_JSON, reference)
    validate_sqlite_matches_json(demo)
    print("Wrote data/demo.json, data/demo.sqlite, and data/reference-cases.json")
    print(
        f"Rows: {len(demo['customers'])} customers, "
        f"{len(demo['orders'])} orders, {len(demo['refunds'])} refunds"
    )
    for name, period in periods.items():
        print(
            f"{name}: gross {period['gross_sales_cents']} "
            f"refunds {period['refunds_cents']} net {period['net_sales_cents']}"
        )


def validate(demo: dict, seed: dict) -> None:
    if demo["customers"][: len(seed["customers"])] != seed["customers"]:
        raise SystemExit("Seed customers were not preserved at the start of the demo.")
    if demo["orders"][: len(seed["orders"])] != seed["orders"]:
        raise SystemExit("Seed orders were not preserved at the start of the demo.")
    if demo["refunds"][: len(seed["refunds"])] != seed["refunds"]:
        raise SystemExit("Seed refunds were not preserved at the start of the demo.")
    customers = unique_by_id(demo["customers"], "customer_id")
    orders = unique_by_id(demo["orders"], "order_id")
    refunds = unique_by_id(demo["refunds"], "refund_id")
    refunded: dict[str, int] = {}
    for order in orders.values():
        require_money(order["amount_cents"], order["order_id"])
        parse_day(order["order_date"], order["order_id"])
        if order["customer_id"] not in customers:
            raise SystemExit(f"{order['order_id']} references unknown customer {order['customer_id']}")
    for refund in refunds.values():
        require_money(refund["amount_cents"], refund["refund_id"])
        parse_day(refund["refund_date"], refund["refund_id"])
        if refund["order_id"] not in orders:
            raise SystemExit(f"{refund['refund_id']} references unknown order {refund['order_id']}")
        refunded[refund["order_id"]] = refunded.get(refund["order_id"], 0) + refund["amount_cents"]
    for order_id, refund_total in refunded.items():
        if refund_total > orders[order_id]["amount_cents"]:
            raise SystemExit(f"Refunds for {order_id} exceed the order amount.")
    o3_refunds = [item for item in demo["refunds"] if item["order_id"] == "O3"]
    if len(o3_refunds) < 2:
        raise SystemExit("O3 must keep multiple refunds.")
    medium_september_orders = [
        order["order_id"]
        for order in demo["orders"]
        if customers[order["customer_id"]]["segment"] == "medium" and in_period(order["order_date"], SEPTEMBER)
    ]
    medium_september_refunds = [
        refund["refund_id"]
        for refund in demo["refunds"]
        if segment_for_refund(refund, orders, customers) == "medium" and in_period(refund["refund_date"], SEPTEMBER)
    ]
    if medium_september_orders or not medium_september_refunds:
        raise SystemExit("September medium must be a refund-only segment period.")


def require_refund_driven_decline(periods: dict) -> None:
    august = periods["august"]
    september = periods["september"]
    if august["gross_sales_cents"] != september["gross_sales_cents"]:
        raise SystemExit("August and September gross sales must stay equal.")
    if not september["refunds_cents"] > august["refunds_cents"]:
        raise SystemExit("September refunds must exceed August refunds.")
    if not september["net_sales_cents"] < august["net_sales_cents"]:
        raise SystemExit("Net sales must decline from August to September.")


def build_reference(demo: dict, periods: dict) -> dict:
    customers = unique_by_id(demo["customers"], "customer_id")
    orders = unique_by_id(demo["orders"], "order_id")
    august_segments = segment_totals(demo, AUGUST)
    september_segments = segment_totals(demo, SEPTEMBER)
    o3 = orders["O3"]
    o3_refunds = [item for item in demo["refunds"] if item["order_id"] == "O3"]
    repeated = o3["amount_cents"] * len(o3_refunds)
    return {
        "dataset": "data/demo.json",
        "scope": "expanded demo, not the original seed",
        "method": (
            "Python sums over data/demo.json. Orders contribute by order_date and "
            "refunds by refund_date. Each refund uses the segment of the customer "
            "on its original order. Net sales are gross sales minus refunds. "
            "These figures were not taken from the application or from model-written SQL."
        ),
        "date_comparison": "datetime.date half-open ranges; YYYY-MM-DD text sorts in the same order.",
        "cases": [
            {
                "id": "august-september-totals",
                "title": "Expanded August and September gross, refunds, and net totals",
                "rule": "data/domain.md rules 2 and 3",
                "calculation": (
                    "Sum order amount_cents where order_date is in the half-open month. "
                    "Sum refund amount_cents where refund_date is in that same month. "
                    "Net sales equal the first sum minus the second. August and September "
                    "gross sales are equal, September refunds are higher, and net sales fall."
                ),
                "august": periods["august"],
                "september": periods["september"],
                "gross_change_cents": periods["september"]["gross_sales_cents"] - periods["august"]["gross_sales_cents"],
                "refund_change_cents": periods["september"]["refunds_cents"] - periods["august"]["refunds_cents"],
                "net_change_cents": periods["september"]["net_sales_cents"] - periods["august"]["net_sales_cents"],
            },
            {
                "id": "multiple-refunds-without-duplicated-gross",
                "title": "Multiple refunds without duplicated gross sales",
                "rule": "data/domain.md rules 1 and 3",
                "calculation": (
                    "O3 is one September order. RF2 and RF3 are separate September refunds "
                    "for that same order. Gross sales include O3's amount once. Adding the "
                    "order amount once for every refund row would repeat it."
                ),
                "order": {
                    "order_id": o3["order_id"],
                    "customer_id": o3["customer_id"],
                    "segment": customers[o3["customer_id"]]["segment"],
                    "order_date": o3["order_date"],
                    "amount_cents": o3["amount_cents"],
                },
                "refunds": [
                    {
                        "refund_id": item["refund_id"],
                        "refund_date": item["refund_date"],
                        "amount_cents": item["amount_cents"],
                    }
                    for item in o3_refunds
                ],
                "expected": {
                    "order_counted_once_cents": o3["amount_cents"],
                    "refund_total_cents": sum(item["amount_cents"] for item in o3_refunds),
                    "september_gross_sales_cents": periods["september"]["gross_sales_cents"],
                },
                "not_the_expected_result": {
                    "description": "O3's amount added once per September refund row.",
                    "repeated_o3_amount_cents": repeated,
                },
            },
            {
                "id": "segment-totals-reconcile",
                "title": "Segment totals reconcile with overall totals",
                "rule": "data/domain.md rules 2, 3, and 4",
                "calculation": (
                    "For each month, group orders by order_date and the customer segment, "
                    "and group refunds by refund_date and the segment on the original order. "
                    "The small, large, and medium rows sum to the month totals."
                ),
                "august": {"overall": periods["august"], "segments": august_segments},
                "september": {"overall": periods["september"], "segments": september_segments},
            },
            {
                "id": "refund-only-segment-period",
                "title": "A refund-only segment and period remains visible",
                "rule": "data/domain.md rules 2 and 4",
                "calculation": (
                    "Medium customers have no order_date in September. RF4 refunds O8, "
                    "an August medium order, on a September refund_date. September medium "
                    "gross sales are zero and the refund remains in the September medium total."
                ),
                "segment": "medium",
                "period": {"start": "2026-09-01", "end_exclusive": "2026-10-01"},
                "medium_customer_ids": [
                    item["customer_id"] for item in demo["customers"] if item["segment"] == "medium"
                ],
                "september_medium_order_ids": september_segments["medium"]["order_ids"],
                "refund": next(item for item in demo["refunds"] if item["refund_id"] == "RF4"),
                "original_order": orders["O8"],
                "expected": {
                    "gross_sales_cents": september_segments["medium"]["gross_sales_cents"],
                    "refunds_cents": september_segments["medium"]["refunds_cents"],
                    "net_sales_cents": september_segments["medium"]["net_sales_cents"],
                },
            },
            {
                "id": "half-open-boundaries-and-refund-date",
                "title": "Half-open date boundaries and refund-date attribution",
                "rule": "data/domain.md rule 2",
                "calculation": (
                    "A date is inside a month when it is greater than or equal to the first "
                    "day and less than the first day of the next month. Refund amounts follow "
                    "refund_date, not order_date."
                ),
                "records": boundary_records(demo),
            },
        ],
    }


def boundary_records(demo: dict) -> list[dict]:
    customers = unique_by_id(demo["customers"], "customer_id")
    orders = unique_by_id(demo["orders"], "order_id")
    watched = {
        "O5",
        "O6",
        "O7",
        "O10",
        "O21",
        "O30",
        "RF5",
        "RF6",
        "RF7",
        "RF8",
    }
    records = []
    for order in demo["orders"]:
        if order["order_id"] not in watched:
            continue
        records.append(
            {
                "record_id": order["order_id"],
                "kind": "order",
                "date": order["order_date"],
                "amount_cents": order["amount_cents"],
                "august": in_period(order["order_date"], AUGUST),
                "september": in_period(order["order_date"], SEPTEMBER),
                "rationale": order_boundary_rationale(order["order_id"]),
            }
        )
    for refund in demo["refunds"]:
        if refund["refund_id"] not in watched:
            continue
        order = orders[refund["order_id"]]
        records.append(
            {
                "record_id": refund["refund_id"],
                "kind": "refund",
                "date": refund["refund_date"],
                "amount_cents": refund["amount_cents"],
                "order_id": refund["order_id"],
                "order_date": order["order_date"],
                "segment": customers[order["customer_id"]]["segment"],
                "august": in_period(refund["refund_date"], AUGUST),
                "september": in_period(refund["refund_date"], SEPTEMBER),
                "rationale": refund_boundary_rationale(refund["refund_id"]),
            }
        )
    return records


def order_boundary_rationale(order_id: str) -> str:
    return {
        "O5": "2026-08-01 is the August start and is included in August.",
        "O6": "2026-09-01 is the September start. It is included in September and excluded from August.",
        "O7": "2026-10-01 is the October start. It is excluded from September.",
        "O10": "2026-07-20 is before August, so it is outside both months.",
        "O21": "2026-08-31 is the last August day and is included in August.",
        "O30": "2026-09-30 is the last September day and is included in September.",
    }[order_id]


def refund_boundary_rationale(refund_id: str) -> str:
    return {
        "RF5": "Refund date 2026-09-01 counts in September. Order O2 is dated 2026-08-10, so the order itself counts in August.",
        "RF6": "Refund date 2026-08-01 is included in August.",
        "RF7": "Refund date 2026-10-01 is excluded from September. Order O30 is dated 2026-09-30 and still counts in September.",
        "RF8": "Refund date 2026-08-31 is included in August and excluded from September.",
    }[refund_id]


def totals(demo: dict, period: tuple[date, date]) -> dict:
    gross, order_ids = sum_orders(demo, period, segment=None)
    refunds, refund_ids = sum_refunds(demo, period, segment=None)
    return {
        "start": period[0].isoformat(),
        "end_exclusive": period[1].isoformat(),
        "gross_sales_cents": gross,
        "refunds_cents": refunds,
        "net_sales_cents": gross - refunds,
        "order_ids": order_ids,
        "refund_ids": refund_ids,
    }


def segment_totals(demo: dict, period: tuple[date, date]) -> dict:
    customers = unique_by_id(demo["customers"], "customer_id")
    segments = sorted({item["segment"] for item in customers.values()})
    result = {}
    for segment in segments:
        gross, order_ids = sum_orders(demo, period, segment)
        refunds, refund_ids = sum_refunds(demo, period, segment)
        result[segment] = {
            "gross_sales_cents": gross,
            "refunds_cents": refunds,
            "net_sales_cents": gross - refunds,
            "order_ids": order_ids,
            "refund_ids": refund_ids,
        }
    return result


def sum_orders(demo: dict, period: tuple[date, date], segment: str | None) -> tuple[int, list[str]]:
    customers = unique_by_id(demo["customers"], "customer_id")
    total = 0
    identifiers = []
    for order in demo["orders"]:
        if not in_period(order["order_date"], period):
            continue
        if segment is not None and customers[order["customer_id"]]["segment"] != segment:
            continue
        total += order["amount_cents"]
        identifiers.append(order["order_id"])
    return total, identifiers


def sum_refunds(demo: dict, period: tuple[date, date], segment: str | None) -> tuple[int, list[str]]:
    customers = unique_by_id(demo["customers"], "customer_id")
    orders = unique_by_id(demo["orders"], "order_id")
    total = 0
    identifiers = []
    for refund in demo["refunds"]:
        if not in_period(refund["refund_date"], period):
            continue
        if segment is not None and segment_for_refund(refund, orders, customers) != segment:
            continue
        total += refund["amount_cents"]
        identifiers.append(refund["refund_id"])
    return total, identifiers


def segment_for_refund(refund: dict, orders: dict, customers: dict) -> str:
    order = orders[refund["order_id"]]
    return customers[order["customer_id"]]["segment"]


def in_period(value: str, period: tuple[date, date]) -> bool:
    day = parse_day(value, "date")
    return period[0] <= day < period[1]


def unique_by_id(rows: list[dict], key: str) -> dict:
    found: dict[str, dict] = {}
    for row in rows:
        identifier = row[key]
        if identifier in found:
            raise SystemExit(f"Duplicate {key}: {identifier}")
        found[identifier] = row
    return found


def require_money(amount: object, identifier: str) -> None:
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise SystemExit(f"{identifier} amount must be a nonnegative integer number of cents.")


def parse_day(value: str, identifier: str) -> date:
    if not isinstance(value, str) or DATE_TEXT.fullmatch(value) is None:
        raise SystemExit(f"{identifier} date must be YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{identifier} date is not a real calendar date.") from exc


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_sqlite(demo: dict) -> None:
    if DEMO_SQLITE.exists():
        DEMO_SQLITE.unlink()
    connection = sqlite3.connect(DEMO_SQLITE)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_SQL.read_text())
        connection.executemany(
            "INSERT INTO customers (customer_id, segment) VALUES (:customer_id, :segment)",
            demo["customers"],
        )
        connection.executemany(
            """
            INSERT INTO orders (order_id, customer_id, order_date, amount_cents)
            VALUES (:order_id, :customer_id, :order_date, :amount_cents)
            """,
            demo["orders"],
        )
        connection.executemany(
            """
            INSERT INTO refunds (refund_id, order_id, refund_date, amount_cents)
            VALUES (:refund_id, :order_id, :refund_date, :amount_cents)
            """,
            demo["refunds"],
        )
        connection.commit()
    finally:
        connection.close()


def validate_sqlite_matches_json(demo: dict) -> None:
    connection = sqlite3.connect(DEMO_SQLITE)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise SystemExit(f"demo.sqlite integrity check failed: {integrity}")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise SystemExit(f"demo.sqlite foreign key check failed: {foreign_keys}")
        counts = {
            "customers": connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "orders": connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "refunds": connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0],
        }
    finally:
        connection.close()
    expected = {name: len(rows) for name, rows in demo.items()}
    if counts != expected:
        raise SystemExit(f"demo.sqlite row counts {counts} do not match demo.json {expected}.")


if __name__ == "__main__":
    main()

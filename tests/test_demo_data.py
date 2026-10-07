"""Independent checks for the demo fixture. These sums do not use the application."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from investigator.query_tool import SEED_DATABASE_PATH

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
AUGUST = (date(2026, 8, 1), date(2026, 9, 1))
SEPTEMBER = (date(2026, 9, 1), date(2026, 10, 1))


def test_demo_expectations_match_independent_python_sums() -> None:
    seed = json.loads((DATA_DIR / "seed.json").read_text())
    demo = json.loads((DATA_DIR / "demo.json").read_text())
    reference = json.loads((DATA_DIR / "reference-cases.json").read_text())
    cases = {item["id"]: item for item in reference["cases"]}

    assert demo["customers"][:2] == seed["customers"]
    assert demo["orders"][:4] == seed["orders"]
    assert demo["refunds"][:3] == seed["refunds"]
    assert (len(demo["customers"]), len(demo["orders"]), len(demo["refunds"])) == (10, 30, 8)
    _validate_records(demo)

    august = _totals(demo, AUGUST)
    september = _totals(demo, SEPTEMBER)
    assert cases["august-september-totals"]["august"]["gross_sales_cents"] == august["gross_sales_cents"]
    assert cases["august-september-totals"]["august"]["refunds_cents"] == august["refunds_cents"]
    assert cases["august-september-totals"]["august"]["net_sales_cents"] == august["net_sales_cents"]
    assert cases["august-september-totals"]["september"]["gross_sales_cents"] == september["gross_sales_cents"]
    assert cases["august-september-totals"]["september"]["refunds_cents"] == september["refunds_cents"]
    assert cases["august-september-totals"]["september"]["net_sales_cents"] == september["net_sales_cents"]
    assert august["gross_sales_cents"] == september["gross_sales_cents"]
    assert september["refunds_cents"] > august["refunds_cents"]
    assert cases["august-september-totals"]["net_change_cents"] == (
        september["net_sales_cents"] - august["net_sales_cents"]
    )

    o3 = next(order for order in demo["orders"] if order["order_id"] == "O3")
    o3_refunds = [item for item in demo["refunds"] if item["order_id"] == "O3"]
    multiple = cases["multiple-refunds-without-duplicated-gross"]
    assert multiple["expected"]["order_counted_once_cents"] == o3["amount_cents"]
    assert multiple["expected"]["refund_total_cents"] == sum(item["amount_cents"] for item in o3_refunds)
    assert multiple["not_the_expected_result"]["repeated_o3_amount_cents"] == o3["amount_cents"] * len(o3_refunds)
    assert o3["order_id"] in september["order_ids"]
    assert september["order_ids"].count("O3") == 1

    reconcile = cases["segment-totals-reconcile"]
    for period, label in ((AUGUST, "august"), (SEPTEMBER, "september")):
        segments = _segment_totals(demo, period)
        stored = reconcile[label]
        assert sum(item["gross_sales_cents"] for item in segments.values()) == stored["overall"]["gross_sales_cents"]
        assert sum(item["refunds_cents"] for item in segments.values()) == stored["overall"]["refunds_cents"]
        assert sum(item["net_sales_cents"] for item in segments.values()) == stored["overall"]["net_sales_cents"]
        assert segments == stored["segments"]

    medium = cases["refund-only-segment-period"]["expected"]
    september_medium = _segment_totals(demo, SEPTEMBER)["medium"]
    assert september_medium["order_ids"] == []
    assert september_medium["refund_ids"] == ["RF4"]
    assert medium == {
        "gross_sales_cents": 0,
        "refunds_cents": 800,
        "net_sales_cents": -800,
    }

    boundaries = {item["record_id"]: item for item in cases["half-open-boundaries-and-refund-date"]["records"]}
    assert boundaries["O5"]["august"] is True and boundaries["O6"]["august"] is False
    assert boundaries["O6"]["september"] is True and boundaries["O7"]["september"] is False
    assert boundaries["O21"]["august"] is True and boundaries["O30"]["september"] is True
    assert boundaries["RF5"]["september"] is True and boundaries["RF5"]["august"] is False
    assert boundaries["RF5"]["order_date"] == "2026-08-10"
    assert boundaries["RF7"]["september"] is False and boundaries["RF7"]["order_date"] == "2026-09-30"

    connection = sqlite3.connect(DATA_DIR / "demo.sqlite")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone() == (30,)
    finally:
        connection.close()
    assert SEED_DATABASE_PATH.name == "seed.sqlite"


def _validate_records(demo: dict) -> None:
    customers = {item["customer_id"]: item for item in demo["customers"]}
    orders = {item["order_id"]: item for item in demo["orders"]}
    assert len(customers) == len(demo["customers"])
    assert len(orders) == len(demo["orders"])
    assert len({item["refund_id"] for item in demo["refunds"]}) == len(demo["refunds"])
    refunded: dict[str, int] = {}
    for order in demo["orders"]:
        assert order["customer_id"] in customers
        assert isinstance(order["amount_cents"], int) and order["amount_cents"] >= 0
        date.fromisoformat(order["order_date"])
    for refund in demo["refunds"]:
        assert refund["order_id"] in orders
        assert isinstance(refund["amount_cents"], int) and refund["amount_cents"] >= 0
        date.fromisoformat(refund["refund_date"])
        refunded[refund["order_id"]] = refunded.get(refund["order_id"], 0) + refund["amount_cents"]
    for order_id, amount in refunded.items():
        assert amount <= orders[order_id]["amount_cents"]


def _totals(demo: dict, period: tuple[date, date]) -> dict:
    gross, order_ids = _sum_orders(demo, period, None)
    refunds, refund_ids = _sum_refunds(demo, period, None)
    return {
        "gross_sales_cents": gross,
        "refunds_cents": refunds,
        "net_sales_cents": gross - refunds,
        "order_ids": order_ids,
        "refund_ids": refund_ids,
    }


def _segment_totals(demo: dict, period: tuple[date, date]) -> dict:
    result = {}
    for segment in sorted({item["segment"] for item in demo["customers"]}):
        gross, order_ids = _sum_orders(demo, period, segment)
        refunds, refund_ids = _sum_refunds(demo, period, segment)
        result[segment] = {
            "gross_sales_cents": gross,
            "refunds_cents": refunds,
            "net_sales_cents": gross - refunds,
            "order_ids": order_ids,
            "refund_ids": refund_ids,
        }
    return result


def _sum_orders(demo: dict, period: tuple[date, date], segment: str | None) -> tuple[int, list[str]]:
    customers = {item["customer_id"]: item["segment"] for item in demo["customers"]}
    total = 0
    identifiers = []
    for order in demo["orders"]:
        if not _inside(order["order_date"], period):
            continue
        if segment is not None and customers[order["customer_id"]] != segment:
            continue
        total += order["amount_cents"]
        identifiers.append(order["order_id"])
    return total, identifiers


def _sum_refunds(demo: dict, period: tuple[date, date], segment: str | None) -> tuple[int, list[str]]:
    customers = {item["customer_id"]: item["segment"] for item in demo["customers"]}
    orders = {item["order_id"]: item for item in demo["orders"]}
    total = 0
    identifiers = []
    for refund in demo["refunds"]:
        if not _inside(refund["refund_date"], period):
            continue
        order = orders[refund["order_id"]]
        if segment is not None and customers[order["customer_id"]] != segment:
            continue
        total += refund["amount_cents"]
        identifiers.append(refund["refund_id"])
    return total, identifiers


def _inside(value: str, period: tuple[date, date]) -> bool:
    day = date.fromisoformat(value)
    return period[0] <= day < period[1]

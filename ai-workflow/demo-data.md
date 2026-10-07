# Demo data

`scripts/generate_demo_data.py` reads `data/seed.json` and appends a fixed list of customers, orders, and refunds. It does not use randomness. It writes `data/demo.json`, `data/demo.sqlite`, and `data/reference-cases.json`. The seed files and the application's default database, `data/seed.sqlite`, stay unchanged.

The additions keep August and September gross sales equal and make September refunds larger, so the net decline is refund-driven. O3 still has RF2 and RF3. C3 and C9 use the segment value `medium`, which is only another customer label; it is not a new metric rule. Neither has a September order. RF4 refunds C3's August order O8 on 2026-09-12, so September medium has refunds and zero gross sales. Boundary rows include 2026-08-01, 2026-08-31, 2026-09-01, 2026-09-30, and 2026-10-01. RF5 and RF7 are attributed by refund date, not order date.

Expectations are Python sums of `amount_cents` over `data/demo.json`. Orders use `order_date`. Refunds use `refund_date` and the segment of the customer on the original order. Net sales are gross sales minus refunds. The application and model-written SQL were not used as the answer key. `tests/test_demo_data.py` repeats those sums separately and compares them with `data/reference-cases.json`.

Regenerate with:

```text
.venv/bin/python scripts/generate_demo_data.py
```

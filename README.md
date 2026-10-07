# provectus-take-home

Local business data investigator. The query tool and investigation CLI are in `investigator/`.

`investigate` and `follow-up` load `OPENAI_API_KEY` from the repository-root `.env` only when that variable is unset. An existing value is not replaced, and the value is not printed. `.env.example` contains the name only. `replay` does not load `.env` or construct an API client.

```text
python -m investigator.cli investigate "How did net sales change from August to September 2026?"
python -m investigator.cli follow-up INVESTIGATION_ID "Which customer segment contributed the September refunds?"
python -m investigator.cli replay INVESTIGATION_ID
```

`replay` reads the saved JSON report. It does not call the model, use an API key, or use the network.

`follow-up` without `--database` uses the database recorded on the parent investigation and checks that its SHA-256 still matches. An explicit `--database` that differs from that record is rejected. A report saved before database identity existed has no record; its follow-up requires `--database`, and the old report is not rewritten.

Reports are written under `investigations/` unless `--reports-dir` is set. Evidence IDs are scoped to the investigation that produced them, and a follow-up keeps those IDs. A report stays incomplete when one of its queries errors, times out, or is truncated; the explanation and evidence are kept. Conclusion links are the evidence IDs named in the explanation. Unknown citations are recorded. Amounts in an explanation are integer USD cents with explicit UTC half-open date ranges. The investigation prompt asks SQL for gross_sales_cents, refunds_cents, and net_sales_cents, with net sales calculated in SQL, and it keeps a period or segment that has refunds but no orders. Refund amounts and refund reasons are separate: the final explanation must state that refund reasons are unknown from these records. Numerical verification of a free-text explanation is not available.

Assumption, not a domain rule: stored dates are ISO calendar dates (`YYYY-MM-DD`).

The expanded fixture is `data/demo.json` and `data/demo.sqlite`, generated from the seed by `scripts/generate_demo_data.py`. Expected figures are in `data/reference-cases.json`. The application's default database remains `data/seed.sqlite`. `medium` is an additional fictional customer segment label so one segment can have a September refund and no September orders. It does not add a metric rule. An empty set of orders sums to zero gross sales.

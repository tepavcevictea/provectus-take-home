# provectus-take-home

Local business data investigator. The query tool and investigation CLI are in `investigator/`.

`investigate` and `follow-up` load `OPENAI_API_KEY` from the repository-root `.env` only when that variable is unset. An existing value is not replaced, and the value is not printed. `.env.example` contains the name only. `replay` does not load `.env` or construct an API client.

```text
python -m investigator.cli investigate "How did net sales change from August to September 2026?"
python -m investigator.cli follow-up INVESTIGATION_ID "Which customer segment contributed the September refunds?"
python -m investigator.cli replay INVESTIGATION_ID
```

`replay` reads the saved JSON report. It does not call the model, use an API key, or use the network.

Reports are written under `investigations/` unless `--reports-dir` is set. Evidence IDs are scoped to the investigation that produced them, and a follow-up keeps those IDs. A report stays incomplete when one of its queries errors, times out, or is truncated; the explanation and evidence are kept. Conclusion links are the evidence IDs named in the explanation. Unknown citations are recorded. Amounts in an explanation are integer USD cents with explicit UTC half-open date ranges. The investigation prompt asks SQL for gross_sales_cents, refunds_cents, and net_sales_cents, with net sales calculated in SQL, and it keeps a period or segment that has refunds but no orders. Refund amounts and refund reasons are separate: the final explanation must state that refund reasons are unknown from these records. Numerical verification of a free-text explanation is not available.

Assumption, not a domain rule: stored dates are ISO calendar dates (`YYYY-MM-DD`).

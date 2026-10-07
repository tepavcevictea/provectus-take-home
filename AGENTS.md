# Business Data Investigator

Build a local application within the eight-hour working budget.

## Source of truth

`data/domain.md` is the source of truth. Do not add domain rules it does not state. Record unresolved ambiguity in the project README.

## Data and metrics

- Preserve `data/seed.json`, `data/seed.sqlite`, `data/schema.sql`, and `data/expected-seed-results.json`.
- Supplied expected totals apply only to the original seed.
- Use integer USD cents.
- Use UTC dates and half-open ranges: start included, end excluded.
- Sum orders by `order_date` and refunds by `refund_date` separately, then combine them. Joining raw refund rows to orders before aggregating can repeat order amounts.
- Assign each refund to the segment of the customer on the original order.
- The records give amounts and dates, not the reason for a refund.

## Queries

- The database connection must enforce read-only access, limited to `customers`, `orders`, and `refunds`.
- Limit each question to six query attempts. Count failed attempts.
- Initial engineering settings, not supplied business rules: maximum query execution time 2 seconds, maximum returned rows 200, and maximum serialized result size 64 KiB.
- Report timeouts and truncation clearly.
- The model must choose each follow-up query using previous results.
- Support follow-up questions that depend on earlier conversation context.
- Report a figure only when an executed result supports it.
- Show failures, partial results, and missing evidence honestly.

## Evaluation and records

- Save real model responses and the configuration used, clearly labeled for replay without credentials.
- Independently verify five reference cases before using them to evaluate the application.
- Keep documentation brief and update it at meaningful milestones.
- Record each coding-model change and why it was made.
- Keep credentials and `.venv` out of Git.
- Do not claim a check passed unless it was actually performed.

AI configuration for this exercise: `ai-workflow/manifest.json`, `ai-workflow/README.md`, `ai-workflow/prompts/001-bootstrap.md`, `ai-workflow/prompts/002-sql-tool.md`, `ai-workflow/prompts/003-sql-review.md`, `ai-workflow/prompts/004-agent-loop.md`, and `ai-workflow/prompts/005-generate-demo-data.md`.

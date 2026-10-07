# 005 — Generate demo data

Saved: 2026-10-06.

## Instruction

Prepare the expanded fictional dataset for Alternative D.

Read:

- AGENTS.md
- data/domain.md
- docs/starter-pack-README.md
- ai-workflow/reference/generate-assignment-data-SKILL.md

Preserve all original seed files and existing reports.

Create:

- data/demo.json and data/demo.sqlite
- A deterministic generation script that starts from the supplied seed
- data/reference-cases.json with five cases and independently calculated expectations
- A short explanation of the additions and verification method

Keep the dataset small, approximately ten customers, thirty orders, and eight refunds. These are suggested sizes, not requirements.

Preserve the refund-driven sales decline and O3’s multiple refunds. Include:

- A refund in September for an earlier order, whose customer segment has no September orders
- Records on period boundaries to check start-inclusive/end-exclusive filtering
- Useful segment breakdowns

Validate unique IDs, foreign keys, nonnegative integer cents, YYYY-MM-DD dates, and total refunds per order not exceeding its amount.

The five reference cases should cover:

1. Expanded August/September gross, refunds, and net totals
2. Multiple refunds without duplicated gross sales
3. Segment totals reconciling with overall totals
4. A refund-only segment/period remaining visible
5. Half-open date boundaries and refund-date attribution

Calculate expectations separately using Python sums over the source records. Do not use application answers or model-generated SQL as the answer key. Include the relevant IDs and calculation rationale so I can inspect them.

Keep the application’s default database unchanged for now.
No live calls or UI work.
Record the generation instruction and method in ai-workflow, and report the files, validation results, and expected figures.

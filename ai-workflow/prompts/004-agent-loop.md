# 004 — Agent loop

Saved: 2026-10-06.

This is the instruction for the investigation agent and CLI. The application prompt is `investigator/prompts/investigation.md`.

## Instruction

Implement the investigation agent and a small CLI using the existing
reviewed QueryTool. Read AGENTS.md and the supplied business rules.

Credential handling:

- Never inspect, print, copy, or include .env in your context.
- Application code may load OPENAI_API_KEY at runtime.
- Add a root .env.example containing placeholders only.
- Do not make live API calls during this task. Tests must use mocks.

Model integration:

- Use the OpenAI Python SDK and Responses API.
- Default model: gpt-4.1-mini-2025-04-14.
- temperature=0, max_output_tokens=1500, store=False.
- parallel_tool_calls=False.
- Client timeout: 20 seconds; automatic retries: 0.
- Pin actual installed runtime dependencies in requirements.txt.
  Keep development dependencies reproducible too.

Application limits:

- At most 7 model requests per question, including failed requests.
- Preserve the existing six SQL-attempt budget.
- Generate question IDs in application code. The model cannot
  choose IDs or reset budgets.
- Question length: at most 2,000 characters.
- Cap the full serialized request context, including instructions,
  tool definitions and previous evidence, at 64 KiB before sending.
  If exceeded, stop visibly rather than silently dropping evidence.
- Process tool requests sequentially.
- All limits must be enforced in code and covered by tests.

Agent behavior:

- Supply the schema and exact business definitions, not the seed
  answer key.
- Expose one strict function tool for requesting SQL.
- Give every request a short investigation purpose.
- Execute the model's SQL through QueryTool and return its result.
- Feed results back so the model chooses a useful follow-up.
  Do not hardcode the SQL sequence or refund conclusion.
- Require an initial successful query and an evidence-based follow-up
  before marking the main sales investigation complete.
- Support a new user question linked to a previous saved investigation.
  Preserve context, with a fresh budget for the new question.
- Stop tool execution at the SQL limit. Any final summarization must
  stay within the model-request budget and identify incomplete work.
- Handle malformed tool arguments, refusals, incomplete responses,
  API failures, and exhausted limits visibly.

Report and persistence:

- Save question, parent investigation ID, definitions, assumptions,
  prompt/schema snapshots, model settings, actual model responses,
  usage, SQL attempts/results, status, and explanation as local JSON.
- Save progress after each step, including failures.
- Assign stable evidence IDs and connect conclusions to query results.
- Explain amounts in cents/USD and explicit date ranges.
- Distinguish the numerical refund contribution from unknown reasons
  for refund requests.
- Do not claim deterministic verification of free-text explanations.
- Clearly distinguish mocked tests from real model responses.

CLI:

- Provide documented commands to investigate, ask a contextual
  follow-up, and replay a saved investigation.
- Replay must work without a key or network and display the saved
  response without regenerating it.
- Prevent saved-report paths from escaping the intended directory.

Tests:

Cover the initial-query/result/follow-up loop, context preservation,
independent question budgets, model and SQL limits, invalid tool
arguments, API failures, incomplete responses, evidence references,
saving partial runs, and credential-free offline replay.
Mocks must verify outgoing request settings and limits.

Save this instruction as ai-workflow/prompts/004-agent-loop.md.
Save the application prompt in the repository and update the manifest,
README and work log briefly. Keep original seed files unchanged.
Run the full test suite.

Finish with changed files, test results, CLI commands, and limitations.
Do not implement the API or UI yet. Do not commit.

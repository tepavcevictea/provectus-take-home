# 006 — Local API and investigation page

Saved: 2026-10-07.

This is the instruction for the local API and investigation page. The application reuses the reviewed investigation agent.

## Instruction

Build the required local API and investigation page around our existing, reviewed InvestigationAgent.

Read AGENTS.md and the assignment requirements first. Keep this milestone focused on the required application.

Architecture

- Use FastAPI and a plain HTML/CSS/JavaScript frontend served by the same application.
- Provide one documented startup command, bound to 127.0.0.1, using one worker.
- Reuse the existing agent, query safeguards, reports, and database continuity logic.
- Create a fresh agent for each live investigation.
- Add and pin the necessary dependencies without changing existing OpenAI model settings or dependency versions.

API

- Support starting an investigation, asking a linked follow-up, listing/loading saved reports, and downloading the original report JSON.
- Accept only server-defined dataset choices: seed or demo. Resolve those choices to fixed repository paths. Do not accept arbitrary database paths or browser-supplied SQL.
- Follow-ups inherit the recorded parent database and verify its hash. Legacy reports require an explicit dataset choice.
- Validate questions and investigation IDs. Return clear errors for missing reports, invalid requests, missing credentials, and database mismatches.
- Allow only one active live investigation at a time. Reject overlapping live requests clearly.
- Loading, listing, and exporting saved reports must work without credentials or model calls.
- Keep credentials on the backend. Serve only the frontend directory as static assets.

Investigation page

- Build a clean, responsive page with a question input and dataset selector, defaulting to demo.
- Provide explicit buttons for a live investigation and a contextual follow-up.
- Show the question, explanation, completion/error status, database identity, and evidence citations.
- Show a useful summary table from actual successful SQL results, with units and evidence IDs. Do not invent values or hardcode demo answers.
- Let users inspect every attempted SQL statement and its result, including failures, empty results, and truncation.
- Show parent context for follow-ups.
- Include saved-report selection and JSON download.
- Clearly distinguish saved real responses, new live responses, and mocks.
- Disable duplicate submissions while a request is running. Page loads, refreshes, and saved-report selection must never trigger paid calls.
- Render model text and SQL safely as text rather than raw HTML.

Verification and documentation

- Add meaningful API tests using mocked model responses, covering saved-report access without credentials, dataset restrictions, follow-up continuity, visible failures, and overlapping live requests.
- Run the full test suite.
- Update README setup instructions, the AI workflow manifest/write-up, and the brief work log. Save this development prompt.
- Report what was implemented, test results, startup command, and any remaining limitations.

Do not make live model calls, modify existing saved reports, or commit during this task.

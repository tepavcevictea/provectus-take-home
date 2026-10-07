"""Investigation agent. Question IDs and budgets are chosen here, not by the model."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from investigator.prompting import (
    ASSUMPTIONS,
    BUSINESS_DEFINITIONS,
    MAX_PURPOSE_CHARACTERS,
    build_instructions,
    load_prompt_text,
    load_schema_text,
    sql_tool,
)
from investigator.database import REPO_ROOT, database_record, resolve_follow_up_database
from investigator.query_tool import SEED_DATABASE_PATH, QueryTool
from investigator.reports import ReportStore

MODEL_NAME = "gpt-4.1-mini-2025-04-14"
TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 1500
STORE_RESPONSES = False
PARALLEL_TOOL_CALLS = False
CLIENT_TIMEOUT_SECONDS = 20.0
CLIENT_MAX_RETRIES = 0
MAX_MODEL_REQUESTS = 7
MAX_QUESTION_CHARACTERS = 2000
MAX_REQUEST_BYTES = 64 * 1024
SUCCESSFUL_SQL_STATUSES = frozenset({"ok"})
NAMESPACED_EVIDENCE_ID = re.compile(r"inv_[0-9a-f]{32}:E[1-9][0-9]*")
BARE_EVIDENCE_ID = re.compile(r"E[1-9][0-9]*")


class CredentialError(RuntimeError):
    """OPENAI_API_KEY is not available in the environment."""


class InvestigationAgent:
    def __init__(
        self,
        *,
        reports_dir: Path | str,
        database_path: Path | str = SEED_DATABASE_PATH,
        client: Any | None = None,
        query_tool: QueryTool | None = None,
        response_source: str = "live",
        repo_root: Path | str = REPO_ROOT,
    ) -> None:
        self.reports = ReportStore(reports_dir)
        self.repo_root = Path(repo_root)
        self.database_path = Path(database_path)
        self.client = client
        self.query_tool = query_tool or QueryTool(self.database_path)
        if response_source not in {"live", "mock"}:
            raise ValueError("response_source must be 'live' or 'mock'.")
        self.response_source = response_source
        self.instructions = build_instructions()
        self.tools = [sql_tool()]

    def investigate(self, question: str) -> dict[str, Any]:
        return self._run(question, parent=None)

    def follow_up(
        self,
        parent_investigation_id: str,
        question: str,
        *,
        database_path: Path | str | None = None,
    ) -> dict[str, Any]:
        parent = self.reports.load(parent_investigation_id)
        chosen = resolve_follow_up_database(parent, database_path, self.repo_root)
        previous_path = self.database_path
        previous_tool = self.query_tool
        if chosen.resolve() != Path(previous_path).resolve():
            self.database_path = chosen
            self.query_tool = QueryTool(chosen)
        try:
            return self._run(question, parent=parent)
        finally:
            self.database_path = previous_path
            self.query_tool = previous_tool

    def _run(self, question: str, parent: dict[str, Any] | None) -> dict[str, Any]:
        investigation_id = "inv_" + uuid.uuid4().hex
        question_id = "q_" + uuid.uuid4().hex
        report: dict[str, Any] = {
            "investigation_id": investigation_id,
            "question_id": question_id,
            "parent_investigation_id": None if parent is None else parent["investigation_id"],
            "question": question,
            "definitions": list(BUSINESS_DEFINITIONS),
            "assumptions": list(ASSUMPTIONS),
            "prompt_snapshot": load_prompt_text(),
            "schema_snapshot": load_schema_text(),
            "model_settings": _model_settings(),
            "model_responses": [],
            "usage": [],
            "sql_attempts": [],
            "evidence": [],
            "rejected_tool_calls": [],
            "status": "incomplete",
            "explanation": None,
            "conclusion_evidence_ids": [],
            "unknown_citations": [],
            "explanation_verification": "not_deterministically_verified",
            "incomplete_reason": None,
            "response_source": self.response_source,
            "amount_units": "integer USD cents; USD equals cents divided by 100",
            "date_ranges": "UTC, start included and end excluded",
            "refund_reasons": "unknown; the records contain amounts and dates only",
            "database": database_record(self.database_path, self.repo_root),
        }
        self._save(report)
        if not isinstance(question, str) or not question.strip():
            return self._finish(report, "invalid_question", "The question is empty.")
        if len(question) > MAX_QUESTION_CHARACTERS:
            return self._finish(
                report,
                "invalid_question",
                f"The question is {len(question)} characters. The maximum is {MAX_QUESTION_CHARACTERS}.",
            )

        context_chain = [] if parent is None else self._context_chain(parent)
        inherited_ids = {
            item["evidence_id"]
            for prior in context_chain
            for item in prior.get("evidence", [])
            if item.get("evidence_id")
        }
        conversation: list[dict[str, Any]] = [_opening_input(question, context_chain)]
        model_requests = 0
        successful_result_sent = False
        follow_up_succeeded = False
        is_main = parent is None

        while True:
            if model_requests >= MAX_MODEL_REQUESTS:
                reason = (
                    "Model request budget is exhausted "
                    f"({MAX_MODEL_REQUESTS} requests). "
                    "No further summary was requested. The investigation is incomplete."
                )
                if _sql_attempts_used(self.query_tool, question_id) >= self.query_tool.max_attempts:
                    reason += (
                        f" SQL tool execution stopped at the {self.query_tool.max_attempts}-attempt limit."
                    )
                return self._finish(report, "incomplete", reason)
            request = _request_body(self.instructions, self.tools, conversation)
            size = _serialized_size(request)
            if size > MAX_REQUEST_BYTES:
                return self._finish(
                    report,
                    "context_limit",
                    (
                        f"The serialized request is {size} bytes, above the "
                        f"{MAX_REQUEST_BYTES} byte cap. Evidence was not dropped."
                    ),
                )
            model_requests += 1
            try:
                response = self._client().responses.create(**request)
            except Exception as exc:
                record = {
                    "request_index": model_requests,
                    "response_source": self.response_source,
                    "error": _public_error(exc),
                    "response": None,
                    "usage": None,
                }
                report["model_responses"].append(record)
                self._save(report)
                return self._finish(report, "api_error", record["error"])

            saved = _response_record(response, model_requests, self.response_source)
            report["model_responses"].append(saved)
            if saved["usage"] is not None:
                report["usage"].append(saved["usage"])
            self._save(report)

            if _is_refusal(response):
                return self._finish(report, "refused", "The model refused the request.")
            if _field(response, "status") == "incomplete":
                return self._finish(
                    report,
                    "incomplete",
                    "The model response is incomplete and was not treated as a finished answer.",
                )

            tool_calls = _function_calls(response)
            if tool_calls:
                _append_model_output(conversation, response)
                evidence_before = len(report["evidence"])
                self._handle_tool_calls(report, conversation, question_id, tool_calls)
                if len(report["evidence"]) > evidence_before:
                    latest = report["evidence"][-1]
                    if latest["result"]["status"] in SUCCESSFUL_SQL_STATUSES:
                        if successful_result_sent:
                            follow_up_succeeded = True
                        successful_result_sent = True
                self._save(report)
                continue

            text = _output_text(response)
            if text is None:
                return self._finish(report, "incomplete", "The model response had no text and no tool call.")
            _append_model_output(conversation, response)
            problems = _sql_problems(report)
            gate_open = successful_result_sent and follow_up_succeeded
            sql_exhausted = _sql_attempts_used(self.query_tool, question_id) >= self.query_tool.max_attempts
            if is_main and not gate_open and not sql_exhausted and not problems:
                conversation.append(
                    {
                        "role": "user",
                        "content": (
                            "The main sales investigation is not complete. "
                            "Obtain one successful query. After that result is returned, "
                            "request one follow-up query that uses the earlier evidence. "
                            "Only then write the final explanation. "
                            "Cite the full evidence ID from the tool result. "
                            "Do not state figures without evidence IDs."
                        ),
                    }
                )
                self._save(report)
                continue
            known_ids = set(inherited_ids)
            known_ids.update(
                item["evidence_id"] for item in report["evidence"] if item.get("evidence_id")
            )
            cited, unknown = _citations(text, known_ids)
            report["explanation"] = text
            report["conclusion_evidence_ids"] = cited
            report["unknown_citations"] = unknown
            reasons: list[str] = []
            if problems:
                reasons.append("The report is partial. " + " ".join(problems))
            if is_main and not gate_open and sql_exhausted:
                reasons.append(
                    "SQL tool execution stopped at the "
                    f"{self.query_tool.max_attempts}-attempt limit before a successful "
                    "query and an evidence-based follow-up were both complete. "
                    "The summary describes incomplete work."
                )
            if reasons:
                return self._finish(report, "incomplete", " ".join(reasons))
            report["status"] = "complete"
            report["incomplete_reason"] = None
            self._save(report)
            return report

    def _handle_tool_calls(
        self,
        report: dict[str, Any],
        conversation: list[dict[str, Any]],
        question_id: str,
        tool_calls: list[Any],
    ) -> None:
        for index, call in enumerate(tool_calls):
            call_dict = _function_call_dict(call)
            if index > 0:
                conversation.append(
                    _tool_output(
                        call_dict.get("call_id"),
                        {
                            "status": "not_executed",
                            "executed": False,
                            "error": (
                                "Only one SQL request is executed per model response. "
                                "Use the result of the first request before choosing a follow-up."
                            ),
                        },
                    )
                )
                continue
            parsed, problem = _parse_tool_arguments(call_dict.get("arguments"))
            if problem is not None or parsed is None:
                report["rejected_tool_calls"].append(
                    {"call_id": call_dict.get("call_id"), "error": problem, "arguments": call_dict.get("arguments")}
                )
                conversation.append(
                    _tool_output(
                        call_dict.get("call_id"),
                        {"status": "invalid_arguments", "executed": False, "error": problem},
                    )
                )
                self._save(report)
                continue
            purpose = parsed["purpose"]
            sql = parsed["sql"]
            if _sql_attempts_used(self.query_tool, question_id) >= self.query_tool.max_attempts:
                attempt = {
                    "evidence_id": None,
                    "purpose": purpose,
                    "sql": sql,
                    "executed": False,
                    "status": "budget_exhausted",
                    "result": None,
                    "error": (
                        f"SQL attempt budget is exhausted ({self.query_tool.max_attempts}). "
                        "This request was not executed."
                    ),
                }
                report["sql_attempts"].append(attempt)
                conversation.append(_tool_output(call_dict.get("call_id"), attempt))
                self._save(report)
                continue
            result = self.query_tool.execute(question_id, sql)
            evidence_id = f"{report['investigation_id']}:E{len(report['evidence']) + 1}"
            evidence = {
                "evidence_id": evidence_id,
                "purpose": purpose,
                "sql": sql,
                "result": result,
            }
            report["evidence"].append(evidence)
            report["sql_attempts"].append(
                {
                    "evidence_id": evidence_id,
                    "purpose": purpose,
                    "sql": sql,
                    "executed": result["executed"],
                    "status": result["status"],
                    "result": result,
                    "error": result["error"],
                }
            )
            conversation.append(
                _tool_output(
                    call_dict.get("call_id"),
                    {
                        "evidence_id": evidence_id,
                        "status": result["status"],
                        "columns": result["columns"],
                        "rows": result["rows"],
                        "truncated": result["truncated"],
                        "truncation_reason": result["truncation_reason"],
                        "error": result["error"],
                        "executed": result["executed"],
                    },
                )
            )
            self._save(report)

    def _client(self) -> Any:
        if self.client is None:
            self.client = build_client()
        return self.client

    def _context_chain(self, parent: dict[str, Any]) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        current: dict[str, Any] | None = parent
        seen: set[str] = set()
        while current is not None:
            investigation_id = current["investigation_id"]
            if investigation_id in seen:
                break
            seen.add(investigation_id)
            chain.append(current)
            parent_id = current.get("parent_investigation_id")
            if not parent_id:
                break
            current = self.reports.load(parent_id)
        chain.reverse()
        return chain

    def _finish(self, report: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
        report["status"] = status
        report["incomplete_reason"] = reason
        self._save(report)
        return report

    def _save(self, report: dict[str, Any]) -> None:
        self.reports.save(report)


def build_client() -> Any:
    """Create the OpenAI client from the environment. Does not read or print .env."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise CredentialError("OPENAI_API_KEY is not set.")
    from openai import OpenAI

    return OpenAI(api_key=key, timeout=CLIENT_TIMEOUT_SECONDS, max_retries=CLIENT_MAX_RETRIES)


def _model_settings() -> dict[str, Any]:
    return {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": STORE_RESPONSES,
        "parallel_tool_calls": PARALLEL_TOOL_CALLS,
        "timeout_seconds": CLIENT_TIMEOUT_SECONDS,
        "max_retries": CLIENT_MAX_RETRIES,
        "max_model_requests": MAX_MODEL_REQUESTS,
        "max_question_characters": MAX_QUESTION_CHARACTERS,
        "max_request_bytes": MAX_REQUEST_BYTES,
    }


def _request_body(instructions: str, tools: list[dict[str, Any]], conversation: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": STORE_RESPONSES,
        "parallel_tool_calls": PARALLEL_TOOL_CALLS,
        "instructions": instructions,
        "tools": tools,
        "input": conversation,
    }


def _serialized_size(request: dict[str, Any]) -> int:
    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return len(encoded)


def _opening_input(question: str, chain: list[dict[str, Any]]) -> dict[str, str]:
    if not chain:
        return {"role": "user", "content": question}
    blocks = [json.dumps(_context_payload(prior), ensure_ascii=False) for prior in chain]
    content = (
        "This is a new question linked to previous investigations. "
        "Use that saved context. Evidence IDs keep their original investigation prefixes. "
        "Cite an evidence ID only when that result supports the conclusion.\n"
        "Previous investigations, oldest first:\n"
        + "\n".join(blocks)
        + f"\nNew question:\n{question}"
    )
    return {"role": "user", "content": content}


def _context_payload(prior: dict[str, Any]) -> dict[str, Any]:
    return {
        "investigation_id": prior["investigation_id"],
        "question": prior["question"],
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "purpose": item["purpose"],
                "sql": item["sql"],
                "status": item["result"]["status"],
                "columns": item["result"]["columns"],
                "rows": item["result"]["rows"],
                "error": item["result"]["error"],
            }
            for item in prior.get("evidence", [])
        ],
        "explanation": prior.get("explanation"),
        "status": prior.get("status"),
        "incomplete_reason": prior.get("incomplete_reason"),
    }


def _append_model_output(conversation: list[dict[str, Any]], response: Any) -> None:
    for item in _field(response, "output") or []:
        conversation.append(_plain_item(item))


def _sql_problems(report: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for attempt in report["sql_attempts"]:
        status = attempt.get("status")
        error = attempt.get("error") or ""
        evidence_id = attempt.get("evidence_id") or "unlabeled SQL attempt"
        result = attempt.get("result") or {}
        if status == "truncated" or result.get("truncated"):
            reason = result.get("truncation_reason") or "truncated"
            problems.append(f"{evidence_id} was truncated ({reason}).")
        elif "timed out" in str(error).lower():
            problems.append(f"{evidence_id} timed out: {error}")
        elif status == "error":
            problems.append(f"{evidence_id} failed: {error}")
    return problems


def _citations(text: str, known_ids: set[str]) -> tuple[list[str], list[str]]:
    cited: list[str] = []
    unknown: list[str] = []
    for match in NAMESPACED_EVIDENCE_ID.finditer(text):
        token = match.group(0)
        if token in known_ids:
            if token not in cited:
                cited.append(token)
        elif token not in unknown:
            unknown.append(token)
    for match in BARE_EVIDENCE_ID.finditer(text):
        if match.start() > 0 and text[match.start() - 1] == ":":
            continue
        token = match.group(0)
        if token not in unknown:
            unknown.append(token)
    return cited, unknown


def _sql_attempts_used(query_tool: QueryTool, question_id: str) -> int:
    return sum(1 for item in query_tool.history(question_id) if item["counts_against_budget"])


def _parse_tool_arguments(raw: Any) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(raw, str):
        return None, "Tool arguments must be a JSON string."
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Tool arguments are not valid JSON."
    if not isinstance(parsed, dict):
        return None, "Tool arguments must be a JSON object."
    allowed = {"purpose", "sql"}
    if set(parsed) != allowed:
        return None, "Tool arguments must contain only purpose and sql."
    purpose = parsed["purpose"]
    sql = parsed["sql"]
    if not isinstance(purpose, str) or not purpose.strip():
        return None, "Tool argument purpose must be a non-empty string."
    if len(purpose) > MAX_PURPOSE_CHARACTERS:
        return None, f"Tool argument purpose exceeds {MAX_PURPOSE_CHARACTERS} characters."
    if not isinstance(sql, str) or not sql.strip():
        return None, "Tool argument sql must be a non-empty string."
    return {"purpose": purpose, "sql": sql}, None


def _tool_output(call_id: Any, payload: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "function_call_output",
        "call_id": "" if call_id is None else str(call_id),
        "output": json.dumps(payload, ensure_ascii=False, default=str),
    }


def _function_call_dict(call: Any) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": _field(call, "call_id"),
        "name": _field(call, "name"),
        "arguments": _field(call, "arguments"),
    }


def _function_calls(response: Any) -> list[Any]:
    calls = []
    for item in _field(response, "output") or []:
        if _field(item, "type") == "function_call" and _field(item, "name") == "request_sql":
            calls.append(item)
    return calls


def _output_text(response: Any) -> str | None:
    texts: list[str] = []
    for item in _field(response, "output") or []:
        if _field(item, "type") != "message":
            continue
        for part in _field(item, "content") or []:
            if _field(part, "type") == "output_text" and isinstance(_field(part, "text"), str):
                texts.append(_field(part, "text"))
    if not texts:
        return None
    return "\n".join(texts)


def _is_refusal(response: Any) -> bool:
    for item in _field(response, "output") or []:
        if _field(item, "type") != "message":
            continue
        for part in _field(item, "content") or []:
            if _field(part, "type") == "refusal":
                return True
    return False


def _response_record(response: Any, request_index: int, response_source: str) -> dict[str, Any]:
    payload = _serialize_sdk(response)
    if payload is None:
        payload = {
            "status": _field(response, "status"),
            "output": [_plain_item(item) for item in (_field(response, "output") or [])],
            "incomplete_details": _plain_item(_field(response, "incomplete_details")),
        }
    usage = _field(response, "usage")
    usage_payload = None if usage is None else _plain_item(usage)
    return {
        "request_index": request_index,
        "response_source": response_source,
        "error": None,
        "response": payload,
        "usage": usage_payload,
    }


def _serialize_sdk(value: Any) -> Any | None:
    """Dump an SDK model with API aliases, omitting fields the API did not set."""
    if hasattr(value, "to_dict"):
        return value.to_dict(mode="json")
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return None


def _plain_item(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    serialized = _serialize_sdk(value)
    if serialized is not None:
        return serialized
    if isinstance(value, dict):
        return {str(key): _plain_item(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_item(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _plain_item(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _public_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    key = os.environ.get("OPENAI_API_KEY")
    if key and key in text:
        text = text.replace(key, "[redacted]")
    return text

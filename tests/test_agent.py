"""Mocked tests for the investigation agent. These are not live model calls."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace

import pytest

from investigator.agent import (
    MAX_MODEL_REQUESTS,
    MAX_QUESTION_CHARACTERS,
    MAX_REQUEST_BYTES,
    MODEL_NAME,
    InvestigationAgent,
    _model_settings,
    _request_body,
    build_client,
    sampling_parameters,
)
from investigator.prompting import PROMPT_PATH, sql_tool
from investigator.query_tool import MAX_ATTEMPTS, QueryTool

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = REPO_ROOT / "data" / "schema.sql"


def test_prompt_has_business_rules_and_not_the_seed_answer_key() -> None:
    text = PROMPT_PATH.read_text()
    domain = (REPO_ROOT / "data" / "domain.md").read_text()
    for rule in (
        "Use customers, orders, and refunds.",
        "half-open periods: start included, end excluded.",
        "Use integer USD cents.",
        "not why a customer requested a refund.",
    ):
        assert rule in text
        assert rule in domain
    assert "Worked example" not in text
    assert "10,000" not in text
    assert "10000" not in text
    assert "expected-seed-results" not in text
    assert "SELECT" not in text
    assert "gross_sales_cents" in text
    assert "refunds_cents" in text
    assert "net_sales_cents" in text
    assert "Calculate net_sales_cents in SQL" in text
    assert "refunds but no orders" in text
    assert "refund reasons are unknown from these records" in text
    assert "compare both periods" in text
    assert "orders and refunds from both periods" in text
    assert "Reconcile the numerical difference" in text
    assert "customer motive" in text
    assert "28200" not in text
    tool = sql_tool()
    assert tool["strict"] is True
    assert set(tool["parameters"]["properties"]) == {"purpose", "sql"}
    assert "question_id" not in tool["parameters"]["properties"]


def test_explicit_model_is_sent_and_the_default_name_stays(tmp_path: Path) -> None:
    assert MODEL_NAME == "gpt-4.1-2025-04-14"
    count_customers = "SELECT COUNT(*) AS customer_count FROM customers"
    count_orders = "SELECT COUNT(*) AS order_count FROM orders"
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", count_customers)]),
            response([tool_call("c2", "Count orders after the customer evidence", count_orders)]),
            response([message("Both counts were queried.")]),
        ]
    )
    report = _agent(tmp_path, scripted, model="gpt-6-luna").investigate("Count customers and orders.")
    assert scripted.calls[0]["model"] == "gpt-6-luna"
    assert "temperature" not in scripted.calls[0]
    assert report["model_settings"]["model"] == "gpt-6-luna"
    assert "temperature" not in report["model_settings"]
    default = _agent(tmp_path, Scripted([]))
    assert default.model == MODEL_NAME


def test_sampling_parameters_follow_the_model_and_do_not_replace_it() -> None:
    assert sampling_parameters(MODEL_NAME) == {"temperature": 0}
    assert sampling_parameters("gpt-4.1-mini-2025-04-14") == {"temperature": 0}
    assert sampling_parameters("gpt-6-luna") == {}
    default = _request_body("instructions", [], [], MODEL_NAME)
    mini = _request_body("instructions", [], [], "gpt-4.1-mini-2025-04-14")
    luna = _request_body("instructions", [], [], "gpt-6-luna")
    assert default["model"] == "gpt-4.1-2025-04-14"
    assert default["temperature"] == 0
    assert mini["model"] == "gpt-4.1-mini-2025-04-14"
    assert mini["temperature"] == 0
    assert luna["model"] == "gpt-6-luna"
    assert "temperature" not in luna
    assert default["instructions"] == mini["instructions"] == luna["instructions"]
    assert default["tools"] == mini["tools"] == luna["tools"]
    assert default["max_output_tokens"] == mini["max_output_tokens"] == 1500
    assert _model_settings(MODEL_NAME)["temperature"] == 0
    assert _model_settings(MODEL_NAME)["model"] == MODEL_NAME
    assert _model_settings("gpt-4.1-mini-2025-04-14")["temperature"] == 0
    recorded = _model_settings("gpt-6-luna")
    assert recorded["model"] == "gpt-6-luna"
    assert "temperature" not in recorded


def test_prompt_states_refund_attribution_and_forbids_schema_discovery() -> None:
    text = PROMPT_PATH.read_text()
    assert "orders.order_date" in text
    assert "refunds.refund_date" in text
    assert "original order" in text
    assert "zero orders" in text
    assert "joining refunds to orders" in text
    assert "Aggregate orders and refunds independently" in text
    assert "PRAGMA" in text
    assert "sqlite_master" in text
    assert "sqlite_schema" in text
    assert "order_totals" in text
    assert "refund_totals" in text
    assert "refund id" in text
    assert "refund amount" in text
    assert "refund date" in text
    assert "original order id" in text
    assert "original order date" in text
    assert "RF4" not in text
    assert "O8" not in text
    assert "800" not in text


def test_initial_query_result_and_follow_up_loop(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response(
                [
                    tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers"),
                    tool_call("c2", "Should wait", "SELECT COUNT(*) AS order_count FROM orders"),
                ]
            ),
            response([tool_call("c3", "Count orders after the customer evidence", "SELECT COUNT(*) AS order_count FROM orders")]),
            response([message("E1 and E2 are the executed counts. Refund reasons are unknown.")], usage={"input_tokens": 10, "output_tokens": 5}),
        ]
    )
    agent = _agent(tmp_path, scripted)
    report = agent.investigate("How many customers and orders are recorded?")

    assert report["status"] == "complete"
    assert report["response_source"] == "mock"
    assert report["explanation_verification"] == "not_deterministically_verified"
    assert [item["evidence_id"] for item in report["evidence"]] == [
        f"{report['investigation_id']}:E1",
        f"{report['investigation_id']}:E2",
    ]
    assert report["conclusion_evidence_ids"] == []
    assert report["unknown_citations"] == ["E1", "E2"]
    assert report["evidence"][0]["result"]["rows"] == [[1]]
    assert report["evidence"][1]["result"]["rows"] == [[0]]
    assert report["explanation"] == "E1 and E2 are the executed counts. Refund reasons are unknown."
    assert report["usage"] == [{"input_tokens": 10, "output_tokens": 5}]
    assert len(scripted.calls) == 3
    for call in scripted.calls:
        _assert_request_settings(call)
    second_input = json.dumps(scripted.calls[1]["input"])
    assert "Only one SQL request is executed" in second_input
    assert "E1" in second_input
    saved = json.loads((tmp_path / "reports" / f"{report['investigation_id']}.json").read_text())
    assert saved["model_responses"][0]["response_source"] == "mock"
    assert saved["question_id"] == report["question_id"]
    assert agent.query_tool.history(report["question_id"])[0]["question_id"] == report["question_id"]


def test_early_answer_is_not_complete_until_follow_up_exists(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response([message("Net sales fell, but this has no evidence.")]),
            response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
            response([tool_call("c2", "Count orders using the customer result", "SELECT COUNT(*) AS order_count FROM orders")]),
            response([message("E1 and E2 support the counts.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("What changed?")
    assert report["status"] == "complete"
    assert "not complete" in scripted.calls[1]["input"][-1]["content"]
    assert len(report["evidence"]) == 2


def test_follow_up_preserves_context_and_uses_a_fresh_budget(tmp_path: Path) -> None:
    sql = "SELECT COUNT(*) AS customer_count FROM customers"
    parent_script = Scripted([response([tool_call(f"p{i}", "repeat", sql)]) for i in range(MAX_MODEL_REQUESTS)])
    agent = _agent(tmp_path, parent_script)
    parent = agent.investigate("PARENT-QUESTION-MARKER")
    assert parent["status"] == "incomplete"
    assert "Model request budget is exhausted" in parent["incomplete_reason"]
    assert "SQL tool execution stopped" in parent["incomplete_reason"]
    parent_history = agent.query_tool.history(parent["question_id"])
    assert sum(1 for item in parent_history if item["counts_against_budget"]) == MAX_ATTEMPTS
    assert len(parent_script.calls) == MAX_MODEL_REQUESTS

    follow_script = Scripted(
        [
            response([tool_call("f1", "Count orders for the new question", "SELECT COUNT(*) AS order_count FROM orders")]),
            response([message("The new question used E1 from this question and the saved parent context.")]),
        ]
    )
    agent.client = SimpleNamespace(responses=follow_script)
    child = agent.follow_up(parent["investigation_id"], "How many orders are there?")
    assert child["status"] == "complete"
    assert child["parent_investigation_id"] == parent["investigation_id"]
    assert child["question_id"] != parent["question_id"]
    assert child["evidence"][0]["result"]["status"] == "ok"
    assert "PARENT-QUESTION-MARKER" in follow_script.calls[0]["input"][0]["content"]
    assert "E1" in follow_script.calls[0]["input"][0]["content"]
    child_history = agent.query_tool.history(child["question_id"])
    assert sum(1 for item in child_history if item["counts_against_budget"]) == 1
    assert sum(1 for item in agent.query_tool.history(parent["question_id"]) if item["counts_against_budget"]) == MAX_ATTEMPTS


def test_question_length_model_budget_and_request_size_are_enforced(tmp_path: Path) -> None:
    scripted = Scripted([])
    agent = _agent(tmp_path, scripted)
    too_long = agent.investigate("q" * (MAX_QUESTION_CHARACTERS + 1))
    assert too_long["status"] == "invalid_question"
    assert scripted.calls == []
    assert "2000" in too_long["incomplete_reason"]

    huge_parent = _agent(
        tmp_path,
        Scripted(
            [
                response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
                response([tool_call("c2", "Count orders", "SELECT COUNT(*) AS order_count FROM orders")]),
                response([message("done")]),
            ]
        ),
    ).investigate("small question")
    path = tmp_path / "reports" / f"{huge_parent['investigation_id']}.json"
    saved = json.loads(path.read_text())
    saved["evidence"][0]["result"]["rows"] = [["x" * 70_000]]
    path.write_text(json.dumps(saved))
    blocker = Scripted([response([message("should not be sent")])])
    agent.client = SimpleNamespace(responses=blocker)
    limited = agent.follow_up(huge_parent["investigation_id"], "What else?")
    assert limited["status"] == "context_limit"
    assert str(MAX_REQUEST_BYTES) in limited["incomplete_reason"]
    assert blocker.calls == []
    assert "Evidence was not dropped" in limited["incomplete_reason"]


def test_invalid_tool_arguments_are_visible_and_do_not_query(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response(
                [
                    {
                        "type": "function_call",
                        "call_id": "bad",
                        "name": "request_sql",
                        "arguments": "{",
                    }
                ]
            ),
            response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
            response([tool_call("c2", "Count orders after the error", "SELECT COUNT(*) AS order_count FROM orders")]),
            response([message("E1 and E2 recovered from the invalid call.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("Count the tables.")
    assert report["status"] == "complete"
    assert report["rejected_tool_calls"][0]["error"] == "Tool arguments are not valid JSON."
    assert "not valid JSON" in scripted.calls[1]["input"][-1]["output"]
    assert [item["evidence_id"] for item in report["evidence"]] == [
        f"{report['investigation_id']}:E1",
        f"{report['investigation_id']}:E2",
    ]
    assert report["sql_attempts"][0]["executed"] is True


def test_api_failure_incomplete_response_and_refusal_are_saved(tmp_path: Path) -> None:
    failed = _agent(tmp_path, Scripted([RuntimeError("connection failed")])).investigate("Question")
    assert failed["status"] == "api_error"
    assert "connection failed" in failed["incomplete_reason"]
    assert (tmp_path / "reports" / f"{failed['investigation_id']}.json").is_file()
    assert failed["model_responses"][0]["response_source"] == "mock"

    incomplete = _agent(
        tmp_path,
        Scripted([response([message("cut off")], status="incomplete")]),
    ).investigate("Question")
    assert incomplete["status"] == "incomplete"
    assert "incomplete" in incomplete["incomplete_reason"]
    assert incomplete["explanation"] is None

    refused = _agent(
        tmp_path,
        Scripted([response([{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}])]),
    ).investigate("Question")
    assert refused["status"] == "refused"
    assert refused["model_responses"][0]["response"]["output"][0]["content"][0]["type"] == "refusal"


def test_sdk_response_objects_keep_api_aliases_and_omit_unset_fields(tmp_path: Path) -> None:
    count_customers = "SELECT COUNT(*) AS customer_count FROM customers"
    count_orders = "SELECT COUNT(*) AS order_count FROM orders"
    scripted = Scripted(
        [
            _sdk_response(
                [
                    _sdk_message("msg_note", "Checking the customer count first."),
                    _sdk_function_call(
                        "call_customers",
                        "Count customers",
                        count_customers,
                        async_value=True,
                    ),
                ]
            ),
            _sdk_response(
                [
                    _sdk_function_call("call_orders", "Count orders after the customer evidence", count_orders),
                ]
            ),
            _sdk_response([_sdk_message("msg_final", "Both counts were queried.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("Count customers and orders.")

    follow_up_input = scripted.calls[1]["input"]
    assert _dict_keys(follow_up_input).isdisjoint({"async_"})
    assert [item.get("type") for item in follow_up_input] == [
        None,
        "message",
        "function_call",
        "function_call_output",
    ]
    message_item, call_item, output_item = follow_up_input[1:]
    assert message_item["content"][0]["text"] == "Checking the customer count first."
    assert "phase" not in message_item
    assert "logprobs" not in message_item["content"][0]
    assert call_item["call_id"] == "call_customers"
    assert call_item["async"] is True
    assert output_item["call_id"] == "call_customers"
    for omitted in ("id", "caller", "namespace", "status", "async_"):
        assert omitted not in call_item

    later_call = next(
        item
        for item in scripted.calls[2]["input"]
        if item.get("type") == "function_call" and item.get("call_id") == "call_orders"
    )
    assert "async" not in later_call
    assert "async_" not in later_call
    for omitted in ("id", "caller", "namespace", "status"):
        assert omitted not in later_call
    later_output = next(
        item
        for item in scripted.calls[2]["input"]
        if item.get("type") == "function_call_output" and item.get("call_id") == "call_orders"
    )
    assert later_output["call_id"] == later_call["call_id"]

    saved = json.dumps(report["model_responses"])
    assert "async_" not in saved
    assert report["model_responses"][0]["response"]["output"][1]["async"] is True
    assert report["status"] == "complete"


def test_client_uses_the_required_timeout_and_does_not_read_a_file(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    build_client()
    assert captured["api_key"] == "sk-test-not-real"
    assert captured["timeout"] == 20.0
    assert captured["max_retries"] == 0


def _agent(
    tmp_path: Path,
    scripted: Scripted,
    *,
    timeout_seconds: float | None = None,
    model: str | None = None,
) -> InvestigationAgent:
    database = tmp_path / f"agent-{uuid4().hex}.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_SQL.read_text())
        connection.execute("INSERT INTO customers (customer_id, segment) VALUES ('C1', 'small')")
    query_tool = None if timeout_seconds is None else QueryTool(database, timeout_seconds=timeout_seconds)
    return InvestigationAgent(
        reports_dir=tmp_path / "reports",
        database_path=database,
        client=SimpleNamespace(responses=scripted),
        query_tool=query_tool,
        response_source="mock",
        model=model,
    )


def _assert_request_settings(call: dict) -> None:
    assert call["model"] == MODEL_NAME
    assert call["temperature"] == 0
    assert call["max_output_tokens"] == 1500
    assert call["store"] is False
    assert call["parallel_tool_calls"] is False
    assert "10,000" not in call["instructions"]
    assert "10000" not in call["instructions"]
    assert "CREATE TABLE customers" in call["instructions"]
    tool = call["tools"][0]
    assert tool["name"] == "request_sql"
    assert tool["strict"] is True
    assert "question_id" not in json.dumps(tool["parameters"])


class Scripted:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(copy.deepcopy(kwargs))
        if not self._responses:
            raise AssertionError("unexpected model request")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(kwargs)
        return item


def response(output: list[dict], status: str = "completed", usage: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(status=status, output=output, usage=usage, incomplete_details=None)


def message(text: str) -> dict:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def _sdk_response(output: list[dict]) -> object:
    from openai.types.responses import Response

    return Response.model_validate(
        {
            "id": "resp_sdk_test",
            "created_at": 0,
            "model": MODEL_NAME,
            "object": "response",
            "output": output,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "status": "completed",
        }
    )


def _sdk_message(message_id: str, text: str) -> dict:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _sdk_function_call(call_id: str, purpose: str, sql: str, async_value: bool | None = None) -> dict:
    payload = {
        "type": "function_call",
        "call_id": call_id,
        "name": "request_sql",
        "arguments": json.dumps({"purpose": purpose, "sql": sql}),
    }
    if async_value is not None:
        payload["async"] = async_value
    return payload


def _dict_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        for item in value.values():
            found.update(_dict_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_dict_keys(item))
    return found


def tool_call(call_id: str, purpose: str, sql: str) -> dict:
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": "request_sql",
        "arguments": json.dumps({"purpose": purpose, "sql": sql}),
    }

"""Regressions for the investigation review. These use mocks, not live model calls."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from investigator.cli import main
from tests.test_agent import Scripted, _agent, message, response, tool_call

TRUNCATED_SQL = """
WITH RECURSIVE seq(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM seq WHERE n < 201
)
SELECT n FROM seq
"""
TIMEOUT_SQL = """
WITH RECURSIVE seq(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM seq WHERE n < 100000000
)
SELECT MAX(n) FROM seq
"""
COUNT_CUSTOMERS = "SELECT COUNT(*) AS customer_count FROM customers"
COUNT_ORDERS = "SELECT COUNT(*) AS order_count FROM orders"
BROKEN_SQL = "SELECT missing_column FROM customers"
EVIDENCE_ID = re.compile(r"inv_[0-9a-f]{32}:E[1-9][0-9]*")


def test_truncated_query_then_success_is_partial(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response([tool_call("c1", "List sequence rows", TRUNCATED_SQL)]),
            response([tool_call("c2", "Count customers after the truncated rows", COUNT_CUSTOMERS)]),
            response([message("Partial answer kept.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("How many rows are available?")
    assert report["status"] != "complete"
    assert report["explanation"] == "Partial answer kept."
    assert len(report["evidence"]) == 2
    assert report["evidence"][0]["result"]["status"] == "truncated"
    assert "truncat" in report["incomplete_reason"].lower()


def test_successful_queries_followed_by_sql_error_are_partial(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", COUNT_CUSTOMERS)]),
            response([tool_call("c2", "Count orders", COUNT_ORDERS)]),
            response([tool_call("c3", "Read a missing column", BROKEN_SQL)]),
            response([message("Explanation kept after the failure.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("What is recorded?")
    assert report["status"] != "complete"
    assert report["explanation"] == "Explanation kept after the failure."
    assert [item["result"]["status"] for item in report["evidence"]] == ["ok", "ok", "error"]
    assert "missing_column" in report["incomplete_reason"]


def test_timeout_is_partial_and_keeps_the_explanation(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response([tool_call("c1", "Scan a very long sequence", TIMEOUT_SQL)]),
            response([tool_call("c2", "Count customers after the timeout", COUNT_CUSTOMERS)]),
            response([message("Timeout explanation that must be kept.")]),
        ]
    )
    report = _agent(tmp_path, scripted, timeout_seconds=0.05).investigate("Did the scan finish?")
    assert report["status"] != "complete"
    assert report["explanation"] == "Timeout explanation that must be kept."
    assert "timed out" in report["incomplete_reason"].lower()
    assert report["evidence"][0]["result"]["status"] == "error"


def test_evidence_ids_keep_an_investigation_namespace(tmp_path: Path) -> None:
    report = _two_query_report(tmp_path, "Namespace question")
    identifiers = [item["evidence_id"] for item in report["evidence"]]
    assert identifiers == [
        f"{report['investigation_id']}:E1",
        f"{report['investigation_id']}:E2",
    ]


def test_citations_are_the_ids_the_explanation_names(tmp_path: Path) -> None:
    def cite_first(request: dict) -> object:
        found = EVIDENCE_ID.findall(json.dumps(request["input"]))
        token = found[0] if found else "inv_" + ("ab" * 16) + ":E1"
        return response([message(f"Only {token} is cited. Not E99.")])

    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", COUNT_CUSTOMERS)]),
            response([tool_call("c2", "Count orders", COUNT_ORDERS)]),
            cite_first,
        ]
    )
    report = _agent(tmp_path, scripted).investigate("Which result matters?")
    first, second = (item["evidence_id"] for item in report["evidence"])
    assert report["conclusion_evidence_ids"] == [first]
    assert second not in report["conclusion_evidence_ids"]
    assert report["unknown_citations"] == ["E99"]
    assert report["explanation_verification"] == "not_deterministically_verified"


def test_two_follow_ups_preserve_ancestor_context_and_citations(tmp_path: Path) -> None:
    agent = _agent(tmp_path, Scripted([]))
    parent = _two_query_report(tmp_path, "PARENT-QUESTION-MARKER", agent=agent)
    parent_evidence = parent["evidence"][0]["evidence_id"]
    unknown = "inv_" + ("cd" * 16) + ":E9"

    child_script = Scripted([response([message(f"The answer uses {parent_evidence} and {unknown}.")])])
    agent.client = _client(child_script)
    child = agent.follow_up(parent["investigation_id"], "CHILD-QUESTION-MARKER")
    assert child["evidence"] == []
    assert child["conclusion_evidence_ids"] == [parent_evidence]
    assert child["unknown_citations"] == [unknown]
    assert child["explanation_verification"] == "not_deterministically_verified"
    assert parent_evidence in child_script.calls[0]["input"][0]["content"]

    grandchild_script = Scripted(
        [response([message(f"The later answer still uses {parent_evidence}.")])]
    )
    agent.client = _client(grandchild_script)
    grandchild = agent.follow_up(child["investigation_id"], "GRANDCHILD-QUESTION-MARKER")
    opening = grandchild_script.calls[0]["input"][0]["content"]
    assert "PARENT-QUESTION-MARKER" in opening
    assert "CHILD-QUESTION-MARKER" in opening
    assert parent_evidence in opening
    assert child["investigation_id"] in opening
    assert grandchild["conclusion_evidence_ids"] == [parent_evidence]
    assert grandchild["parent_investigation_id"] == child["investigation_id"]
    assert grandchild["question_id"] != child["question_id"]


def test_assistant_message_and_tool_call_keep_output_order(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response(
                [
                    message("Checking the customer count first."),
                    tool_call("c1", "Count customers", COUNT_CUSTOMERS),
                ]
            ),
            response([tool_call("c2", "Count orders after the customer evidence", COUNT_ORDERS)]),
            response([message("Final counts.")]),
        ]
    )
    _agent(tmp_path, scripted).investigate("Count both tables.")
    items = scripted.calls[1]["input"]
    assert items[1]["type"] == "message"
    assert items[1]["content"][0]["text"] == "Checking the customer count first."
    assert items[2]["type"] == "function_call"
    assert items[2]["call_id"] == "c1"
    assert items[3]["type"] == "function_call_output"
    assert sum(1 for item in items if item.get("type") == "function_call" and item.get("call_id") == "c1") == 1


def test_early_answer_is_kept_before_the_corrective_instruction(tmp_path: Path) -> None:
    scripted = Scripted(
        [
            response([message("Net sales fell, but this has no evidence.")]),
            response([tool_call("c1", "Count customers", COUNT_CUSTOMERS)]),
            response([tool_call("c2", "Count orders using the customer result", COUNT_ORDERS)]),
            response([message("Counts are in the evidence.")]),
        ]
    )
    _agent(tmp_path, scripted).investigate("What changed?")
    items = scripted.calls[1]["input"]
    assert items[1]["type"] == "message"
    assert items[1]["content"][0]["text"] == "Net sales fell, but this has no evidence."
    assert items[2]["role"] == "user"
    assert "not complete" in items[2]["content"]


def test_live_command_loads_a_dummy_env_file_without_overriding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dummy = tmp_path / ".env"
    dummy.write_text("# temporary dummy credential\nOPENAI_API_KEY=sk-dummy-from-file\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("investigator.cli.ROOT_ENV_PATH", dummy, raising=False)
    constructed: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            constructed.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        "investigator.agent.InvestigationAgent.investigate",
        lambda self, question: _stopped_report(),
    )
    code = main(["investigate", "Question from the dummy-env test"])
    assert code in {0, 1}
    assert constructed["api_key"] == "sk-dummy-from-file"
    assert os.environ["OPENAI_API_KEY"] == "sk-dummy-from-file"

    dummy.write_text("OPENAI_API_KEY=sk-should-not-override\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-preset-not-from-file")
    constructed.clear()
    main(["investigate", "Question with a preset key"])
    assert constructed["api_key"] == "sk-preset-not-from-file"
    assert os.environ["OPENAI_API_KEY"] == "sk-preset-not-from-file"


def test_replay_does_not_load_a_dummy_env_or_construct_a_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _two_query_report(tmp_path, "Replay stays offline")
    dummy = tmp_path / ".env"
    dummy.write_text("OPENAI_API_KEY=sk-dummy-replay-should-not-load\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("investigator.cli.ROOT_ENV_PATH", dummy, raising=False)

    def boom(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("model client was constructed")

    monkeypatch.setattr("investigator.agent.build_client", boom)
    code = main(["replay", report["investigation_id"], "--reports-dir", str(tmp_path / "reports")])
    printed = capsys.readouterr().out
    assert code == 0
    assert os.environ.get("OPENAI_API_KEY") is None
    assert "sk-dummy-replay-should-not-load" not in printed
    assert "was not regenerated" in printed


def test_replay_shows_question_definitions_sql_evidence_and_partial_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scripted = Scripted(
        [
            response([tool_call("c1", "List sequence rows", TRUNCATED_SQL)]),
            response([tool_call("c2", "Count customers after the truncated rows", COUNT_CUSTOMERS)]),
            response([message("Partial answer kept.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("Replay the partial investigation")
    code = main(["replay", report["investigation_id"], "--reports-dir", str(tmp_path / "reports")])
    printed = capsys.readouterr().out
    assert code == 0
    assert "Replay the partial investigation" in printed
    assert "Use integer USD cents." in printed
    assert "SELECT n FROM seq" in printed
    assert report["evidence"][0]["evidence_id"] in printed
    assert "Partial answer kept." in printed
    assert "truncat" in printed.lower()
    assert report["status"] in printed
    assert "not_deterministically_verified" in printed


def _two_query_report(tmp_path: Path, question: str, agent=None):
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", COUNT_CUSTOMERS)]),
            response([tool_call("c2", "Count orders", COUNT_ORDERS)]),
            response([message("Both counts were queried.")]),
        ]
    )
    if agent is None:
        return _agent(tmp_path, scripted).investigate(question)
    agent.client = _client(scripted)
    return agent.investigate(question)


def _client(scripted: Scripted):
    from types import SimpleNamespace

    return SimpleNamespace(responses=scripted)


def _stopped_report() -> dict[str, object]:
    return {
        "investigation_id": "inv_" + ("a" * 32),
        "question_id": "q_test",
        "status": "incomplete",
        "response_source": "live",
        "explanation": None,
        "incomplete_reason": "stopped in test",
        "parent_investigation_id": None,
    }

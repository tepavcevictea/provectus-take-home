"""CLI tests. Replay is offline and does not construct a model client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from investigator.cli import main
from investigator.reports import ReportStore
from tests.test_agent import Scripted, _agent, message, response, tool_call


def test_replay_displays_the_saved_response_without_a_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
            response([tool_call("c2", "Count orders", "SELECT COUNT(*) AS order_count FROM orders")]),
            response([message("Saved explanation for replay.")]),
        ]
    )
    report = _agent(tmp_path, scripted).investigate("Replay source question")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def boom(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("model client was constructed")

    monkeypatch.setattr("investigator.agent.build_client", boom)
    code = main(["replay", report["investigation_id"], "--reports-dir", str(tmp_path / "reports")])
    printed = capsys.readouterr().out
    assert code == 0
    assert "was not regenerated" in printed
    assert "response_source: mock" in printed
    assert "Saved explanation for replay." in printed
    assert "Saved explanation for replay." in json.dumps(report["model_responses"])


def test_replay_rejects_paths_outside_the_reports_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text('{"explanation": "secret"}')
    code = main(["replay", "../secret", "--reports-dir", str(reports)])
    captured = capsys.readouterr()
    assert code == 2
    assert "not allowed" in captured.err
    assert "secret" not in captured.out
    with pytest.raises(Exception):
        ReportStore(reports).load("../secret")
    with pytest.raises(Exception):
        ReportStore(reports).load(str(outside))


def test_help_documents_investigate_follow_up_and_replay(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "investigate" in help_text
    assert "follow-up" in help_text
    assert "replay" in help_text
    assert "Does not call the model" in help_text

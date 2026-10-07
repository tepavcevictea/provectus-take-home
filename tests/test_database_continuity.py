"""Database identity and follow-up continuity. These tests do not call a live model."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from investigator.cli import main
from investigator.database import DatabaseContinuityError
from investigator.reports import ReportStore
from tests.test_agent import Scripted, message, response, tool_call

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = (REPO_ROOT / "data" / "schema.sql").read_text()
COUNT_SQL = "SELECT COUNT(*) AS customer_count FROM customers"


def test_new_report_records_repository_relative_path_and_hash(tmp_path: Path) -> None:
    database = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    report = _investigate(tmp_path, database)
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    assert report["database"] == {"path": "data/primary.sqlite", "sha256": digest}


def test_follow_up_inherits_the_parent_database_when_omitted(tmp_path: Path) -> None:
    primary = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    other = _database(tmp_path / "data" / "other.sqlite", customers=2)
    parent = _investigate(tmp_path, primary)
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers in the inherited database", COUNT_SQL)]),
            response([message("The inherited database has one customer.")]),
        ]
    )
    child = _agent(tmp_path, scripted, primary).follow_up(parent["investigation_id"], "How many customers?")
    assert child["database"] == parent["database"]
    assert child["evidence"][0]["result"]["rows"] == [[1]]
    assert other.is_file()


def test_explicit_database_mismatch_stops_without_mixing_or_rewriting(
    tmp_path: Path,
) -> None:
    primary = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    other = _database(tmp_path / "data" / "other.sqlite", customers=2)
    parent = _investigate(tmp_path, primary)
    saved = _report_text(tmp_path, parent["investigation_id"])
    scripted = Scripted([response([message("should not run")])])
    with pytest.raises(DatabaseContinuityError, match="differs from the database recorded"):
        _agent(tmp_path, scripted, primary).follow_up(
            parent["investigation_id"],
            "Use the other file",
            database_path=other,
        )
    assert scripted.calls == []
    assert _report_text(tmp_path, parent["investigation_id"]) == saved
    assert list((tmp_path / "reports").glob("inv_*.json")) == [
        tmp_path / "reports" / f"{parent['investigation_id']}.json"
    ]


def test_changed_database_hash_stops_the_follow_up(tmp_path: Path) -> None:
    primary = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    parent = _investigate(tmp_path, primary)
    saved = _report_text(tmp_path, parent["investigation_id"])
    with sqlite3.connect(primary) as connection:
        connection.execute("INSERT INTO customers (customer_id, segment) VALUES ('C2', 'large')")
    scripted = Scripted([response([message("should not run")])])
    with pytest.raises(DatabaseContinuityError, match="no longer matches the SHA-256"):
        _agent(tmp_path, scripted, primary).follow_up(parent["investigation_id"], "How many now?")
    assert scripted.calls == []
    assert _report_text(tmp_path, parent["investigation_id"]) == saved


def test_legacy_report_requires_an_explicit_database_and_is_not_rewritten(tmp_path: Path) -> None:
    primary = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    legacy_id = "inv_" + ("ab" * 16)
    legacy = {
        "investigation_id": legacy_id,
        "question_id": "q_legacy",
        "question": "Older question",
        "status": "complete",
        "explanation": "Saved before database identity.",
        "model_responses": [],
        "evidence": [],
    }
    ReportStore(tmp_path / "reports").save(legacy)
    saved = _report_text(tmp_path, legacy_id)
    scripted = Scripted([response([message("inherited answer")])])
    agent = _agent(tmp_path, scripted, primary)
    with pytest.raises(DatabaseContinuityError, match="no recorded database"):
        agent.follow_up(legacy_id, "What changed?")
    assert scripted.calls == []
    assert _report_text(tmp_path, legacy_id) == saved
    assert "database" not in json.loads(saved)

    child = agent.follow_up(legacy_id, "What changed?", database_path=primary)
    assert child["database"]["path"] == "data/primary.sqlite"
    assert child["database"]["sha256"] == hashlib.sha256(primary.read_bytes()).hexdigest()
    assert _report_text(tmp_path, legacy_id) == saved


def test_cli_follow_up_inherits_and_rejects_a_different_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    primary = _database(tmp_path / "data" / "primary.sqlite", customers=1)
    other = _database(tmp_path / "data" / "other.sqlite", customers=2)
    parent = _investigate(tmp_path, primary)
    monkeypatch.setattr("investigator.cli.REPO_ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    scripted = Scripted([response([message("Follow-up from the recorded database.")])])

    def client() -> SimpleNamespace:
        return SimpleNamespace(responses=scripted)

    monkeypatch.setattr("investigator.agent.build_client", client)
    code = main(
        ["follow-up", parent["investigation_id"], "What else?", "--reports-dir", str(tmp_path / "reports")]
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "Follow-up from the recorded database." in printed
    assert scripted.calls

    code = main(
        [
            "follow-up",
            parent["investigation_id"],
            "Use another file",
            "--reports-dir",
            str(tmp_path / "reports"),
            "--database",
            str(other),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "differs from the database recorded" in captured.err
    assert "were not mixed" in captured.err


def test_cli_legacy_follow_up_does_not_construct_a_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    legacy_id = "inv_" + ("cd" * 16)
    ReportStore(tmp_path / "reports").save(
        {"investigation_id": legacy_id, "question": "Old", "status": "complete"}
    )
    saved = _report_text(tmp_path, legacy_id)

    def boom() -> None:
        raise AssertionError("model client was constructed")

    monkeypatch.setattr("investigator.agent.build_client", boom)
    code = main(["follow-up", legacy_id, "Next?", "--reports-dir", str(tmp_path / "reports")])
    captured = capsys.readouterr()
    assert code == 2
    assert "no recorded database" in captured.err
    assert "saved report was not changed" in captured.err
    assert _report_text(tmp_path, legacy_id) == saved


def _investigate(tmp_path: Path, database: Path) -> dict:
    scripted = Scripted(
        [
            response([tool_call("p1", "Count customers", COUNT_SQL)]),
            response([tool_call("p2", "Count customers again after the first result", COUNT_SQL)]),
            response([message("Parent answer.")]),
        ]
    )
    return _agent(tmp_path, scripted, database).investigate("How many customers are recorded?")


def _agent(tmp_path: Path, scripted: Scripted, database: Path):
    from investigator.agent import InvestigationAgent

    return InvestigationAgent(
        reports_dir=tmp_path / "reports",
        database_path=database,
        client=SimpleNamespace(responses=scripted),
        response_source="mock",
        repo_root=tmp_path,
    )


def _database(path: Path, customers: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        for index in range(customers):
            connection.execute(
                "INSERT INTO customers (customer_id, segment) VALUES (?, 'small')",
                (f"C{index + 1}",),
            )
    return path


def _report_text(tmp_path: Path, investigation_id: str) -> str:
    return (tmp_path / "reports" / f"{investigation_id}.json").read_text()

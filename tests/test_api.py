"""API tests use mocked model responses. They do not call the live model."""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from investigator.agent import CredentialError, InvestigationAgent
from investigator.api import DATASETS, create_app
from investigator.database import database_record
from tests.test_agent import Scripted, message, response, tool_call

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "investigator" / "frontend"


def test_saved_reports_do_not_need_credentials_or_the_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("investigator.cli.load_local_env", _forbid_credentials)
    monkeypatch.setattr("investigator.agent.build_client", _forbid_credentials)
    reports = tmp_path / "reports"
    investigation_id = "inv_" + "ab" * 16
    original = {
        "investigation_id": investigation_id,
        "question": "How many customers are recorded?",
        "status": "complete",
        "response_source": "live",
        "explanation": "Saved text <script>alert(1)</script>",
        "parent_investigation_id": None,
        "database": {"path": "data/demo.sqlite", "sha256": "abc"},
        "sql_attempts": [{"sql": "SELECT 1", "status": "error", "error": "saved failure"}],
    }
    reports.mkdir()
    path = reports / f"{investigation_id}.json"
    path.write_text(json.dumps(original) + "\n")
    before = path.read_bytes()
    app = create_app(reports, _forbid_agent)

    with TestClient(app) as client:
        listed = client.get("/api/reports")
        loaded = client.get(f"/api/reports/{investigation_id}")
        downloaded = client.get(f"/api/reports/{investigation_id}/download")
        page = client.get("/")

    assert listed.status_code == 200
    assert listed.json()["reports"][0]["investigation_id"] == investigation_id
    assert listed.json()["reports"][0]["response_source"] == "live"
    assert loaded.status_code == 200
    assert loaded.json()["origin"] == "saved"
    assert loaded.json()["report"]["explanation"] == original["explanation"]
    assert downloaded.status_code == 200
    assert downloaded.content == before
    assert path.read_bytes() == before
    assert page.status_code == 200
    assert "Run investigation" in page.text


def test_dataset_choices_are_limited_to_seed_and_demo(tmp_path: Path) -> None:
    app = create_app(tmp_path / "reports", _forbid_agent)
    with TestClient(app) as client:
        unknown = client.post("/api/investigations", json={"question": "How many customers?", "dataset": "other"})
        extra = client.post(
            "/api/investigations",
            json={"question": "How many customers?", "dataset": "demo", "database": "/tmp/custom.sqlite", "sql": "SELECT 1"},
        )
        empty = client.post("/api/investigations", json={"question": "   ", "dataset": "demo"})
        missing = client.get("/api/reports/" + "inv_" + "0" * 32)
        invalid = client.get("/api/reports/inv_not-a-valid-id")

    assert unknown.status_code == 422
    assert extra.status_code == 422
    assert empty.status_code == 400
    assert "empty" in empty.json()["detail"]
    assert missing.status_code == 404
    assert invalid.status_code == 400
    assert DATASETS == {
        "seed": REPO_ROOT / "data" / "seed.sqlite",
        "demo": REPO_ROOT / "data" / "demo.sqlite",
    }


def test_follow_up_inherits_the_parent_database_and_rejects_a_different_one(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    scripted = Scripted(_complete_then_count())
    app = create_app(reports, _factory(reports, scripted))
    with TestClient(app) as client:
        started = client.post(
            "/api/investigations",
            json={"question": "How many customers are recorded?", "dataset": "demo"},
        )
        parent = started.json()["report"]
        inherited = client.post(
            f"/api/investigations/{parent['investigation_id']}/follow-ups",
            json={"question": "How many customers are on the same database?"},
        )
        calls_before_mismatch = len(scripted.calls)
        mismatched = client.post(
            f"/api/investigations/{parent['investigation_id']}/follow-ups",
            json={"question": "How many customers are on the seed database?", "dataset": "seed"},
        )

    assert started.status_code == 200
    assert started.json()["origin"] == "new"
    assert parent["database"]["path"] == "data/demo.sqlite"
    assert parent["database"]["sha256"] == database_record(DATASETS["demo"])["sha256"]
    assert inherited.status_code == 200
    assert inherited.json()["origin"] == "new"
    child = inherited.json()["report"]
    assert child["parent_investigation_id"] == parent["investigation_id"]
    assert child["database"] == parent["database"]
    count = _customer_count(DATASETS["demo"])
    assert child["evidence"][-1]["result"]["rows"] == [[count]]
    assert mismatched.status_code == 409
    assert "were not mixed" in mismatched.json()["detail"]
    assert len(scripted.calls) == calls_before_mismatch


def test_legacy_report_requires_a_dataset_and_is_not_rewritten(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    investigation_id = "inv_" + "cd" * 16
    path = reports / f"{investigation_id}.json"
    path.write_text(json.dumps({"investigation_id": investigation_id, "question": "Older question", "status": "complete"}) + "\n")
    before = path.read_bytes()
    scripted = Scripted(
        [
            response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
            response([message("The count is in the evidence. Refund reasons are unknown.")]),
        ]
    )
    app = create_app(reports, _factory(reports, scripted))
    with TestClient(app) as client:
        missing = client.post(f"/api/investigations/{investigation_id}/follow-ups", json={"question": "How many customers?"})
        chosen = client.post(
            f"/api/investigations/{investigation_id}/follow-ups",
            json={"question": "How many customers?", "dataset": "seed"},
        )

    assert missing.status_code == 400
    assert "Choose seed or demo" in missing.json()["detail"]
    assert "not changed" in missing.json()["detail"]
    assert path.read_bytes() == before
    assert chosen.status_code == 200
    assert chosen.json()["report"]["database"]["path"] == "data/seed.sqlite"
    assert chosen.json()["report"]["evidence"][-1]["result"]["rows"] == [[_customer_count(DATASETS["seed"])]]
    assert path.read_bytes() == before


def test_a_changed_database_hash_stops_the_follow_up(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    investigation_id = "inv_" + "ef" * 16
    path = reports / f"{investigation_id}.json"
    path.write_text(
        json.dumps(
            {
                "investigation_id": investigation_id,
                "question": "Earlier question",
                "status": "complete",
                "database": {"path": "data/demo.sqlite", "sha256": "0" * 64},
            }
        )
        + "\n"
    )
    before = path.read_bytes()
    scripted = Scripted([])
    app = create_app(reports, _factory(reports, scripted))
    with TestClient(app) as client:
        response = client.post(
            f"/api/investigations/{investigation_id}/follow-ups",
            json={"question": "How many customers?"},
        )
    assert response.status_code == 409
    assert "no longer matches" in response.json()["detail"]
    assert scripted.calls == []
    assert path.read_bytes() == before


def test_sql_and_model_failures_stay_visible(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    scripted = Scripted(
        [
            response([tool_call("bad", "Try an invalid query", "SELECT nope")]),
            response([message("The query failed. Refund reasons are unknown.")]),
            RuntimeError("connection failed"),
        ]
    )
    app = create_app(reports, _factory(reports, scripted))
    with TestClient(app) as client:
        failed_sql = client.post("/api/investigations", json={"question": "What failed?", "dataset": "demo"})
        failed_model = client.post("/api/investigations", json={"question": "What failed next?", "dataset": "demo"})

    assert failed_sql.status_code == 200
    sql_report = failed_sql.json()["report"]
    assert sql_report["status"] == "incomplete"
    assert sql_report["sql_attempts"][0]["status"] == "error"
    assert sql_report["sql_attempts"][0]["sql"] == "SELECT nope"
    assert sql_report["sql_attempts"][0]["error"]
    assert "partial" in sql_report["incomplete_reason"]
    assert failed_model.status_code == 200
    assert failed_model.json()["report"]["status"] == "api_error"
    assert "connection failed" in failed_model.json()["report"]["incomplete_reason"]


def test_a_second_live_request_is_rejected_while_one_is_running(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    started = threading.Event()
    release = threading.Event()
    scripted = Scripted(_two_queries_and_answer())

    def factory(database_path: Path) -> InvestigationAgent:
        started.set()
        assert release.wait(5)
        return _agent(reports, scripted, database_path)

    app = create_app(reports, factory)
    port = _free_port()
    server = _serve(app, port)
    url = f"http://127.0.0.1:{port}/api/investigations"
    body = {"question": "How many customers are recorded?", "dataset": "demo"}
    first: list[httpx.Response] = []

    def run_first() -> None:
        with httpx.Client(timeout=10) as client:
            first.append(client.post(url, json=body))

    worker = threading.Thread(target=run_first)
    worker.start()
    assert started.wait(5)
    try:
        with httpx.Client(timeout=5) as client:
            second = client.post(url, json=body)
            listed = client.get(f"http://127.0.0.1:{port}/api/reports")
        assert second.status_code == 409
        assert "already running" in second.json()["detail"]
        assert listed.status_code == 200
    finally:
        release.set()
        worker.join(5)
        server.should_exit = True
        server_thread_join(server)

    assert first and first[0].status_code == 200
    assert first[0].json()["origin"] == "new"
    assert first[0].json()["report"]["response_source"] == "mock"


def test_startup_uses_localhost_and_one_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", fake_run)
    from investigator.web import main

    main()
    assert captured["args"] == ("investigator.api:app",)
    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["workers"] == 1


def test_page_loads_saved_reports_without_posting_and_renders_text(tmp_path: Path) -> None:
    script = (FRONTEND / "app.js").read_text()
    html = (FRONTEND / "index.html").read_text()
    assert "innerHTML" not in script
    assert "textContent" in script
    assert 'value="demo" checked' in html
    reports = tmp_path / "reports"
    app = create_app(reports, _forbid_agent)
    with TestClient(app) as client:
        page = client.get("/")
        script_response = client.get("/app.js")
        hidden = client.get("/data/seed.sqlite")
        listed = client.get("/api/reports")
    assert page.status_code == 200
    assert script_response.status_code == 200
    assert hidden.status_code == 404
    assert listed.status_code == 200
    assert listed.json() == {"reports": []}


def test_missing_credentials_are_reported_for_a_live_request(tmp_path: Path) -> None:
    def factory(database_path: Path) -> InvestigationAgent:
        raise CredentialError("OPENAI_API_KEY is not set.")

    app = create_app(tmp_path / "reports", factory)
    with TestClient(app) as client:
        response = client.post("/api/investigations", json={"question": "How many customers?", "dataset": "demo"})
    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not set."
    assert list((tmp_path / "reports").glob("*.json")) == []


def _factory(reports: Path, scripted: Scripted):
    def factory(database_path: Path) -> InvestigationAgent:
        return _agent(reports, scripted, database_path)

    return factory


def _agent(reports: Path, scripted: Scripted, database_path: Path) -> InvestigationAgent:
    return InvestigationAgent(
        reports_dir=reports,
        database_path=database_path,
        client=SimpleNamespace(responses=scripted),
        response_source="mock",
        repo_root=REPO_ROOT,
    )


def _two_queries_and_answer() -> list[object]:
    return [
        response([tool_call("c1", "Count customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
        response([tool_call("c2", "Count customers again", "SELECT COUNT(*) AS customer_count FROM customers")]),
        response([message("Both counts are in the evidence. Refund reasons are unknown.")]),
    ]


def _complete_then_count() -> list[object]:
    return _two_queries_and_answer() + [
        response([tool_call("c3", "Count the inherited customers", "SELECT COUNT(*) AS customer_count FROM customers")]),
        response([message("The follow-up count is in the evidence. Refund reasons are unknown.")]),
    ]


def _customer_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT COUNT(*) FROM customers").fetchone()
    assert row is not None
    return int(row[0])


def _forbid_credentials(*args: object, **kwargs: object) -> None:
    raise AssertionError("credentials were requested")


def _forbid_agent(database_path: Path) -> InvestigationAgent:
    raise AssertionError(f"live agent created for {database_path}")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(app: object, port: int) -> object:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started
    server._test_thread = thread  # type: ignore[attr-defined]
    return server


def server_thread_join(server: object) -> None:
    thread = getattr(server, "_test_thread")
    thread.join(5)

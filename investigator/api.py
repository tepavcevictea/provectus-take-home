"""Local investigation API. Live requests use a fresh agent. Saved reports do not."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from investigator.agent import MAX_QUESTION_CHARACTERS, CredentialError, InvestigationAgent
from investigator.database import REPO_ROOT, DatabaseContinuityError, resolve_follow_up_database
from investigator.reports import INVESTIGATION_ID_RE, ReportPathError, ReportStore

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
DATASETS = {
    "seed": REPO_ROOT / "data" / "seed.sqlite",
    "demo": REPO_ROOT / "data" / "demo.sqlite",
}
DatasetName = Literal["seed", "demo"]


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    dataset: DatasetName


class FollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    dataset: DatasetName | None = None


def create_app(
    reports_dir: Path | str | None = None,
    agent_factory: Callable[[Path], Any] | None = None,
) -> FastAPI:
    """Build the application. The default factory is used only for live requests."""
    store = ReportStore(Path(reports_dir) if reports_dir is not None else REPO_ROOT / "investigations")
    factory = agent_factory or _live_agent_factory(store.root)
    app = FastAPI(title="Business data investigator", docs_url=None, redoc_url=None)
    app.state.reports = store
    app.state.agent_factory = factory
    app.state.live_lock = threading.Lock()

    @app.get("/api/reports")
    def list_reports() -> dict[str, list[dict[str, Any]]]:
        return {"reports": _list_reports(store)}

    @app.get("/api/reports/{investigation_id}")
    def load_report(investigation_id: str) -> dict[str, Any]:
        return {"origin": "saved", "report": _load(store, investigation_id)}

    @app.get("/api/reports/{investigation_id}/download")
    def download_report(investigation_id: str) -> FileResponse:
        path = _report_path(store, investigation_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"No saved investigation: {investigation_id}")
        return FileResponse(path, media_type="application/json", filename=path.name)

    @app.post("/api/investigations")
    def start_investigation(body: InvestigateRequest) -> dict[str, Any]:
        _validate_question(body.question)
        database = _dataset_path(body.dataset)
        with _live_slot(app):
            agent = _new_agent(factory, database)
            report = agent.investigate(body.question)
        return {"origin": "new", "report": report}

    @app.post("/api/investigations/{investigation_id}/follow-ups")
    def ask_follow_up(investigation_id: str, body: FollowUpRequest) -> dict[str, Any]:
        _validate_question(body.question)
        parent = _load(store, investigation_id)
        explicit = None if body.dataset is None else _dataset_path(body.dataset)
        if parent.get("database") in (None, {}) and explicit is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This saved investigation has no recorded database. "
                    "Choose seed or demo. The saved report was not changed."
                ),
            )
        try:
            chosen = resolve_follow_up_database(parent, explicit, REPO_ROOT)
        except DatabaseContinuityError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        with _live_slot(app):
            agent = _new_agent(factory, chosen)
            try:
                report = agent.follow_up(investigation_id, body.question, database_path=explicit)
            except DatabaseContinuityError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"origin": "new", "report": report}

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return app


def _live_agent_factory(reports_dir: Path) -> Callable[[Path], InvestigationAgent]:
    def factory(database_path: Path) -> InvestigationAgent:
        from investigator.agent import build_client
        from investigator.cli import load_local_env

        load_local_env()
        client = build_client()
        return InvestigationAgent(
            reports_dir=reports_dir,
            database_path=database_path,
            client=client,
            response_source="live",
            repo_root=REPO_ROOT,
        )

    return factory


class _LiveSlot:
    def __init__(self, app: FastAPI) -> None:
        self._lock = app.state.live_lock

    def __enter__(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="Another live investigation is already running. Wait for it to finish.",
            )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._lock.release()


def _live_slot(app: FastAPI) -> _LiveSlot:
    return _LiveSlot(app)


def _new_agent(factory: Callable[[Path], Any], database_path: Path) -> Any:
    try:
        return factory(database_path)
    except CredentialError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _dataset_path(dataset: str) -> Path:
    path = DATASETS.get(dataset)
    if path is None or not path.is_file():
        raise HTTPException(status_code=400, detail=f"Dataset {dataset} is not available.")
    return path


def _validate_question(question: str) -> None:
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=400, detail="The question is empty.")
    if len(question) > MAX_QUESTION_CHARACTERS:
        raise HTTPException(
            status_code=400,
            detail=f"The question is {len(question)} characters. The maximum is {MAX_QUESTION_CHARACTERS}.",
        )


def _load(store: ReportStore, investigation_id: str) -> dict[str, Any]:
    try:
        return store.load(investigation_id)
    except ReportPathError as exc:
        raise _http_report_error(exc) from exc


def _report_path(store: ReportStore, investigation_id: str) -> Path:
    try:
        return store.path_for(investigation_id)
    except ReportPathError as exc:
        raise _http_report_error(exc) from exc


def _http_report_error(exc: ReportPathError) -> HTTPException:
    text = str(exc)
    if text.startswith("No saved investigation"):
        return HTTPException(status_code=404, detail=text)
    return HTTPException(status_code=400, detail=text)


def _list_reports(store: ReportStore) -> list[dict[str, Any]]:
    root = store.root
    if not root.is_dir():
        return []
    paths = sorted(root.glob("inv_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    reports = []
    for path in paths:
        if INVESTIGATION_ID_RE.fullmatch(path.stem) is None:
            continue
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if report.get("investigation_id") != path.stem:
            continue
        reports.append(
            {
                "investigation_id": report["investigation_id"],
                "question": report.get("question"),
                "status": report.get("status"),
                "response_source": report.get("response_source"),
                "parent_investigation_id": report.get("parent_investigation_id"),
                "database": report.get("database"),
            }
        )
    return reports


app = create_app()

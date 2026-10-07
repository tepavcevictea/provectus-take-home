"""Identify the database used by an investigation and keep follow-ups on it."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class DatabaseContinuityError(RuntimeError):
    """A follow-up cannot safely choose or reuse a database."""


def database_record(path: Path | str, repo_root: Path | str = REPO_ROOT) -> dict[str, str]:
    """Return the repository-relative path and SHA-256 of a database file."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise DatabaseContinuityError(f"Database file was not found: {path}")
    root = Path(repo_root).resolve()
    try:
        stored = resolved.relative_to(root).as_posix()
    except ValueError:
        stored = resolved.as_posix()
    return {"path": stored, "sha256": _sha256(resolved)}


def resolve_follow_up_database(
    parent: dict,
    explicit: Path | str | None,
    repo_root: Path | str = REPO_ROOT,
) -> Path:
    """Choose the follow-up database without mixing it with another dataset.

    Omit explicit to inherit the parent report's database. A parent saved
    before database identity existed requires explicit. An explicit database
    that differs from a recorded parent database is rejected.
    """
    recorded = _recorded_database(parent)
    root = Path(repo_root).resolve()
    if recorded is None:
        if explicit is None:
            raise DatabaseContinuityError(
                "This saved investigation has no recorded database. "
                "Pass --database to choose one. The saved report was not changed."
            )
        return _existing_file(explicit)
    recorded_path = _resolve_stored_path(recorded["path"], root)
    if not recorded_path.is_file():
        raise DatabaseContinuityError(
            "The database recorded for this investigation was not found: "
            f"{recorded['path']}. The follow-up was not started."
        )
    current_hash = _sha256(recorded_path)
    if current_hash != recorded["sha256"]:
        raise DatabaseContinuityError(
            "The database no longer matches the SHA-256 recorded for this investigation. "
            f"Recorded path {recorded['path']}. Recorded sha256 {recorded['sha256']}. "
            f"Current sha256 {current_hash}. The follow-up was not started."
        )
    if explicit is None:
        return recorded_path
    supplied = _existing_file(explicit)
    supplied_hash = _sha256(supplied)
    if supplied != recorded_path or supplied_hash != recorded["sha256"]:
        raise DatabaseContinuityError(
            "The supplied database differs from the database recorded for the parent investigation. "
            f"Parent database is {recorded['path']} sha256 {recorded['sha256']}. "
            f"Supplied database is {supplied.as_posix()} sha256 {supplied_hash}. "
            "The follow-up was not started, so the datasets were not mixed."
        )
    return recorded_path


def _recorded_database(report: dict) -> dict[str, str] | None:
    value = report.get("database")
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(digest, str) or not digest:
        return None
    return {"path": path, "sha256": digest}


def _resolve_stored_path(stored: str, repo_root: Path) -> Path:
    raw = Path(stored)
    if raw.is_absolute():
        return raw
    return (repo_root / raw).resolve()


def _existing_file(path: Path | str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise DatabaseContinuityError(f"Database file was not found: {path}")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

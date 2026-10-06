"""Command line for investigate, contextual follow-up, and offline replay.

Examples:
  python -m investigator.cli investigate "How did net sales change?"
  python -m investigator.cli follow-up inv_... "Which segment contributed the refunds?"
  python -m investigator.cli replay inv_...

Replay reads the saved report only. It does not load `.env`, call the
network, or regenerate the model response. `investigate` and `follow-up`
load `OPENAI_API_KEY` from the repository-root `.env` only when that
variable is unset.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from investigator.query_tool import SEED_DATABASE_PATH
from investigator.reports import ReportPathError, ReportStore

DEFAULT_REPORTS_DIR = Path("investigations")
ROOT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "replay":
            return _replay(args.investigation_id, Path(args.reports_dir))
        if args.command == "investigate":
            return _investigate(args.question, Path(args.reports_dir), Path(args.database))
        if args.command == "follow-up":
            return _follow_up(args.investigation_id, args.question, Path(args.reports_dir), Path(args.database))
    except ReportPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("error: unknown command", file=sys.stderr)
    return 2


def _investigate(question: str, reports_dir: Path, database: Path) -> int:
    from investigator.agent import CredentialError, InvestigationAgent, build_client

    load_local_env()
    try:
        client = build_client()
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = InvestigationAgent(reports_dir=reports_dir, database_path=database, client=client).investigate(question)
    _print_report(report)
    return 0 if report["status"] == "complete" else 1


def _follow_up(investigation_id: str, question: str, reports_dir: Path, database: Path) -> int:
    from investigator.agent import CredentialError, InvestigationAgent, build_client

    load_local_env()
    try:
        client = build_client()
    except CredentialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    agent = InvestigationAgent(reports_dir=reports_dir, database_path=database, client=client)
    report = agent.follow_up(investigation_id, question)
    _print_report(report)
    return 0 if report["status"] == "complete" else 1


def load_local_env(path: Path | None = None) -> None:
    """Load OPENAI_API_KEY from the repository-root .env when it is unset.

    An existing environment value is left unchanged. The value is not printed.
    Replay does not call this function.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return
    env_path = ROOT_ENV_PATH if path is None else path
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "OPENAI_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ["OPENAI_API_KEY"] = value
        return


def _replay(investigation_id: str, reports_dir: Path) -> int:
    report = ReportStore(reports_dir).load(investigation_id)
    print(f"Replaying saved investigation {report['investigation_id']}")
    print("This is the saved response and was not regenerated.")
    print(f"response_source: {report['response_source']}")
    print(f"question: {report.get('question') or ''}")
    print(f"status: {report['status']}")
    if report.get("incomplete_reason"):
        print(f"incomplete_reason: {report['incomplete_reason']}")
    print("definitions:")
    for item in report.get("definitions") or []:
        print(f"- {item}")
    print("sql attempts:")
    for attempt in report.get("sql_attempts") or []:
        print(f"evidence_id: {attempt.get('evidence_id')}")
        print(f"attempt_status: {attempt.get('status')}")
        print(f"sql: {attempt.get('sql')}")
        print("result:")
        print(json.dumps(attempt.get("result"), indent=2, ensure_ascii=False, default=str))
    print("evidence ids:")
    for item in report.get("evidence") or []:
        print(item.get("evidence_id"))
    print("explanation:")
    print(report.get("explanation") or "")
    print(f"explanation_verification: {report.get('explanation_verification')}")
    print("conclusion evidence ids:")
    for item in report.get("conclusion_evidence_ids") or []:
        print(item)
    if report.get("unknown_citations"):
        print("unknown citations:")
        for item in report["unknown_citations"]:
            print(item)
    print("saved model responses:")
    print(json.dumps(report["model_responses"], indent=2, ensure_ascii=False))
    return 0


def _print_report(report: dict) -> None:
    print(f"investigation_id: {report['investigation_id']}")
    print(f"question_id: {report['question_id']}")
    print(f"status: {report['status']}")
    print(f"response_source: {report['response_source']}")
    if report.get("parent_investigation_id"):
        print(f"parent_investigation_id: {report['parent_investigation_id']}")
    if report.get("incomplete_reason"):
        print(f"incomplete_reason: {report['incomplete_reason']}")
    print("explanation:")
    print(report.get("explanation") or "")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m investigator.cli",
        description=(
            "Investigate business data and replay a saved investigation. "
            "Replay does not use an API key or the network."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate", help="Start an investigation for a new question.")
    investigate.add_argument("question", help="Question text, at most 2000 characters.")
    investigate.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    investigate.add_argument("--database", default=str(SEED_DATABASE_PATH))
    follow_up = subparsers.add_parser(
        "follow-up",
        help="Ask a new question linked to a saved investigation. The new question has a fresh budget.",
    )
    follow_up.add_argument("investigation_id")
    follow_up.add_argument("question")
    follow_up.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    follow_up.add_argument("--database", default=str(SEED_DATABASE_PATH))
    replay = subparsers.add_parser(
        "replay",
        help="Show a saved investigation. Does not call the model or use a credential.",
    )
    replay.add_argument("investigation_id")
    replay.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

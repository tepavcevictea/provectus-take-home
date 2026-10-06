"""Local investigation reports. Paths cannot leave the reports directory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

INVESTIGATION_ID_RE = re.compile(r"inv_[0-9a-f]{32}")


class ReportPathError(ValueError):
    """The requested report path is missing or escapes the reports directory."""


class ReportStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path_for(self, investigation_id: str) -> Path:
        if not isinstance(investigation_id, str) or INVESTIGATION_ID_RE.fullmatch(investigation_id) is None:
            raise ReportPathError("Investigation id is not allowed.")
        root = self.root.resolve()
        path = (root / f"{investigation_id}.json").resolve()
        if not path.is_relative_to(root):
            raise ReportPathError("Report path escapes the reports directory.")
        return path

    def save(self, report: dict[str, Any]) -> Path:
        path = self.path_for(str(report["investigation_id"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(path)
        return path

    def load(self, investigation_id: str) -> dict[str, Any]:
        path = self.path_for(investigation_id)
        if not path.is_file():
            raise ReportPathError(f"No saved investigation: {investigation_id}")
        return json.loads(path.read_text())

"""Versioned JSON persistence for Blueprint Mosaic Studio projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_VERSION = 1


def save_project(path: str | Path, payload: dict[str, Any]) -> None:
    document = {"version": PROJECT_VERSION, **payload}
    Path(path).write_text(
        json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def load_project(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("version") != PROJECT_VERSION:
        raise ValueError("Unsupported Blueprint Mosaic Studio project version.")
    if not isinstance(document.get("source_path"), str):
        raise ValueError("Project does not contain a valid source image path.")
    return document

from __future__ import annotations

import os

from .models import base_dir

EFFORT_OPTIONS = ["default", "minimal", "low", "medium", "high", "max"]


def normalize_effort(effort: str | None) -> str | None:
    value = (effort or "").strip().lower()
    if value in ("", "default", "none"):
        return None
    return value


def saved_effort() -> str | None:
    try:
        text = (base_dir() / "effort").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return normalize_effort(text)


def save_effort(effort: str | None) -> None:
    path = base_dir() / "effort"
    value = normalize_effort(effort)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if value is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(value + "\n", encoding="utf-8")
    except OSError:
        pass


def resolve_effort() -> str | None:
    return normalize_effort(os.environ.get("ORCHESTRA_EFFORT")) or saved_effort()

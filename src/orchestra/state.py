from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .home import base_dir


@dataclass
class SavedOrchestrator:
    id: str
    name: str
    session_id: str | None = None


def state_file() -> Path:
    return base_dir() / "orchestrators.json"


def transcripts_dir() -> Path:
    return base_dir() / "transcripts"


def load_orchestrators() -> list[SavedOrchestrator]:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    saved: list[SavedOrchestrator] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        session_id = item.get("session_id")
        saved.append(
            SavedOrchestrator(
                id=str(item["id"]),
                name=str(item["name"]),
                session_id=str(session_id) if session_id else None,
            )
        )
    return saved


def save_orchestrators(orchestrators: list[SavedOrchestrator]) -> None:
    path = state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(item) for item in orchestrators]
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def append_transcript(orch_id: str, entry: dict) -> None:
    path = transcripts_dir() / f"{orch_id}.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def load_transcript(orch_id: str) -> list[dict]:
    path = transcripts_dir() / f"{orch_id}.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict] = []
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("type") in ("user", "assistant") and isinstance(data.get("text"), str):
            entries.append(data)
    return entries


def delete_transcript(orch_id: str) -> None:
    try:
        (transcripts_dir() / f"{orch_id}.jsonl").unlink()
    except OSError:
        pass

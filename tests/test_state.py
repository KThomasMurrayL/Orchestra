from pathlib import Path

import pytest

from orchestra.state import (
    SavedOrchestrator,
    append_transcript,
    delete_transcript,
    load_orchestrators,
    load_transcript,
    save_orchestrators,
)


def test_save_and_load_orchestrators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    save_orchestrators(
        [
            SavedOrchestrator(id="o1", name="Alpha", session_id="ses_1"),
            SavedOrchestrator(id="o2", name="Beta", session_id=None),
        ]
    )
    assert load_orchestrators() == [
        SavedOrchestrator(id="o1", name="Alpha", session_id="ses_1"),
        SavedOrchestrator(id="o2", name="Beta", session_id=None),
    ]


def test_load_orchestrators_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    assert load_orchestrators() == []


def test_transcript_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    append_transcript("o1", {"type": "user", "text": "hi"})
    append_transcript("o1", {"type": "assistant", "text": "hello"})
    assert load_transcript("o1") == [
        {"type": "user", "text": "hi"},
        {"type": "assistant", "text": "hello"},
    ]
    delete_transcript("o1")
    assert load_transcript("o1") == []

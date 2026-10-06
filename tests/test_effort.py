from pathlib import Path

import pytest

from orchestra.effort import normalize_effort, resolve_effort, save_effort, saved_effort


def test_normalize_effort():
    assert normalize_effort("High") == "high"
    assert normalize_effort(" default ") is None
    assert normalize_effort("") is None
    assert normalize_effort(None) is None


def test_effort_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ORCHESTRA_EFFORT", raising=False)
    assert resolve_effort() is None
    save_effort("High")
    assert saved_effort() == "high"
    assert resolve_effort() == "high"
    save_effort("default")
    assert saved_effort() is None
    assert not (tmp_path / "home" / "effort").exists()


def test_effort_env_overrides_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    save_effort("high")
    monkeypatch.setenv("ORCHESTRA_EFFORT", "minimal")
    assert resolve_effort() == "minimal"

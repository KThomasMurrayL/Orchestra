from pathlib import Path

import pytest

from orchestra import models


def test_parse_models_strips_ansi_and_sorts():
    output = "\x1b[0mdeepseek/deepseek-v4-pro\nopencode/big-pickle\ndeepseek/deepseek-flash\n"
    assert models.parse_models(output) == [
        "deepseek/deepseek-flash",
        "deepseek/deepseek-v4-pro",
        "opencode/big-pickle",
    ]


def test_parse_models_ignores_noise_and_duplicates():
    output = "Loading...\nfoo\n\ndeepseek/deepseek-flash\n deepseek/deepseek-flash \n"
    assert models.parse_models(output) == ["deepseek/deepseek-flash"]


def test_resolve_model_prefers_saved_choice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    models.save_model("deepseek/deepseek-v4-pro")
    assert models.saved_model() == "deepseek/deepseek-v4-pro"
    assert models.resolve_model() == "deepseek/deepseek-v4-pro"


def test_resolve_model_none_without_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert models.resolve_model() is None


def test_list_models_caches(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Result:
        stdout = "\x1b[0mb/b\na/a\n"
        returncode = 0

    def fake_run(*args, **kwargs):
        calls.append(args)
        return Result()

    monkeypatch.setattr(models.subprocess, "run", fake_run)
    monkeypatch.setattr(models, "_CACHE", None)
    assert models.list_models() == ["a/a", "b/b"]
    assert models.list_models() == ["a/a", "b/b"]
    assert len(calls) == 1


def test_usable_models_hides_free_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models, "list_models", lambda ttl=-1: ["opencode/x", "deepseek/y"])
    assert models.usable_models() == (["deepseek/y"], 1)

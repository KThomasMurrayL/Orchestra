from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestra import skills


def fake_home(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("USERPROFILE", str(path))


def test_add_and_discover_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    fake_home(monkeypatch, tmp_path / "user")
    path = skills.add_skill("Paper Review", "Use when reviewing papers.")
    assert path.exists()
    assert path.parent.name == "paper-review"
    text = path.read_text(encoding="utf-8")
    assert "name: paper-review" in text
    found = {skill.name: skill for skill in skills.discover_skills()}
    assert "paper-review" in found
    assert found["paper-review"].source == "orchestra"
    assert found["paper-review"].description == "Use when reviewing papers."


def test_add_duplicate_and_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    skills.add_skill("demo")
    with pytest.raises(FileExistsError):
        skills.add_skill("demo")
    with pytest.raises(ValueError):
        skills.add_skill("Not Valid!")


def test_remove_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    skills.add_skill("demo")
    skills.remove_skill("demo")
    assert not (skills.user_skills_dir() / "demo").exists()
    with pytest.raises(FileNotFoundError):
        skills.remove_skill("demo")


def test_config_skill_paths_include_user_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    fake_home(monkeypatch, tmp_path / "user")
    paths = skills.config_skill_paths()
    assert str(tmp_path / "home" / "skills") in paths


def test_global_config_skill_paths_are_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    fake_home(monkeypatch, tmp_path / "user")
    config_dir = tmp_path / "user" / ".config" / "opencode"
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text('{"skills": {"paths": ["/custom/skills"]}}')
    paths = skills.config_skill_paths()
    assert "/custom/skills" in paths
    assert str(tmp_path / "home" / "skills") in paths


def test_generated_config_includes_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    fake_home(monkeypatch, tmp_path / "user")
    from orchestra.home import prepare_home

    home = prepare_home(model="deepseek/deepseek-flash")
    data = json.loads(home.config.read_text(encoding="utf-8"))
    assert str(tmp_path / "home" / "skills") in data["skills"]["paths"]


def test_cli_skills_add_list_path_remove(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    fake_home(monkeypatch, tmp_path / "user")
    from orchestra.__main__ import main

    assert main(["skills", "add", "demo", "--description", "Use when testing."]) == 0
    assert "created" in capsys.readouterr().out

    assert main(["skills", "list"]) == 0
    listing = capsys.readouterr().out
    assert "demo" in listing
    assert "Use when testing." in listing

    assert main(["skills", "path"]) == 0
    assert str(tmp_path / "home" / "skills") in capsys.readouterr().out

    assert main(["skills", "remove", "demo"]) == 0
    assert "removed" in capsys.readouterr().out

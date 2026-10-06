from pathlib import Path

import pytest
from textual.widgets import Input, ListView

from orchestra.app import NEW_ORCH_KEY, OrchestraApp
from orchestra.state import append_transcript
from orchestra.widgets import ConfirmQuit, ModelPicker, NameDialog


@pytest.mark.asyncio
async def test_app_mounts_with_one_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        agents = app.query_one("#agents", ListView)
        assert len(agents.children) == 2
        assert app.active_orch == "o1"
        assert app._orch_names["o1"] == "Orchestrator"
        assert len(app.controller.orchestrators) == 1
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_add_and_close_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.add_orchestrator()
        await pilot.pause()
        agents = app.query_one("#agents", ListView)
        assert len(agents.children) == 3
        assert app.active_orch == "o2"
        assert len(app.controller.orchestrators) == 2
        assert app._switcher.current == "chat-o2"
        app.close_orchestrator("o2")
        await pilot.pause()
        assert len(agents.children) == 2
        assert app.active_orch == "o1"
        assert len(app.controller.orchestrators) == 1
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_new_orchestrator_button_asks_for_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#new-orch")
        await pilot.pause()
        assert isinstance(app.screen, NameDialog)
        app.screen.query_one("#name-input", Input).value = "Research"
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.controller.orchestrators) == 2
        assert app._orch_names["o2"] == "Research"
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_new_orchestrator_key_opens_dialog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press(NEW_ORCH_KEY)
        await pilot.pause()
        assert isinstance(app.screen, NameDialog)
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.controller.orchestrators) == 2
        assert app.active_orch == "o2"
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_confirm_quit_button(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#quit")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmQuit)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmQuit)
        calls: list[bool] = []
        app.action_quit = lambda: calls.append(True)
        await pilot.click("#quit")
        await pilot.pause()
        await pilot.click("#confirm-yes")
        await pilot.pause()
        assert calls == [True]
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_input_routes_to_active_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    sent: list[tuple[str, str]] = []

    async def fake_send(orch_id: str, text: str) -> None:
        sent.append((orch_id, text))

    async with app.run_test() as pilot:
        await pilot.pause()
        await app.add_orchestrator()
        app.controller.send = fake_send
        prompt = app.query_one("#prompt", Input)
        prompt.value = "hello"
        prompt.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert sent == [("o2", "hello")]
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_orchestrators_persist_across_restarts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    first = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with first.run_test() as pilot:
        await pilot.pause()
        await first.add_orchestrator(name="Research", session_id="ses_research")
        append_transcript("o2", {"type": "user", "text": "find the bug"})
        append_transcript("o2", {"type": "assistant", "text": "found it"})
        await first.controller.shutdown()

    second = OrchestraApp(workspace=tmp_path, model=None, voice_enabled=False, max_workers=1)
    async with second.run_test() as pilot:
        await pilot.pause()
        assert set(second._orch_names) == {"o1", "o2"}
        assert second._orch_names["o2"] == "Research"
        assert second.controller.orchestrators["o2"].session_id == "ses_research"
        view = second._orch_views["o2"]
        assert len(view.children) == 2
        await second.controller.shutdown()


@pytest.mark.asyncio
async def test_model_picker_filters_and_selects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model="a/a", voice_enabled=False, max_workers=1)
    chosen: dict[str, str] = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ModelPicker("a/a", ["a/a", "b/b", "c/c"]), lambda model: chosen.update(model=model))
        await pilot.pause()
        app.screen.query_one("#picker-filter", Input).value = "c"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert chosen.get("model") == "c/c"
        await app.controller.shutdown()


@pytest.mark.asyncio
async def test_set_model_updates_all_orchestrators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORCHESTRA_HOME", str(tmp_path / "home"))
    app = OrchestraApp(workspace=tmp_path, model="a/a", voice_enabled=False, max_workers=1)
    async with app.run_test() as pilot:
        await pilot.pause()
        await app.add_orchestrator()
        app.set_model("b/b")
        assert app.model == "b/b"
        assert app.controller.dispatcher.model == "b/b"
        assert app.controller.orchestrators["o1"].model == "b/b"
        assert app.controller.orchestrators["o2"].model == "b/b"
        assert "b/b" in app.home.config.read_text()
        await app.controller.shutdown()

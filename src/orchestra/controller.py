from __future__ import annotations

import time
from pathlib import Path

from .home import Home, write_config
from .orchestrator import Orchestrator
from .process import OpencodeRunner
from .workers import Dispatcher


class Controller:
    def __init__(
        self,
        workspace: Path,
        home: Home,
        model: str | None = None,
        effort: str | None = None,
        max_workers: int = 4,
    ):
        self.workspace = workspace
        self.home = home
        self.model = model
        self.effort = effort
        self.ui = None
        self.dispatcher = Dispatcher(
            ui=None, home=home, workspace=workspace, max_workers=max_workers, model=model, effort=effort
        )
        self.orchestrators: dict[str, Orchestrator] = {}
        self._started = False

    def attach(self, ui) -> None:
        self.ui = ui
        self.dispatcher.ui = ui
        for orchestrator in self.orchestrators.values():
            orchestrator.ui = ui

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.dispatcher.start()

    def add_orchestrator(self, orch_id: str, name: str) -> Orchestrator:
        orchestrator = Orchestrator(
            orch_id=orch_id,
            name=name,
            ui=self.ui,
            config=self.home.config,
            inbox=self.home.inbox,
            workspace=self.workspace,
            model=self.model,
            effort=self.effort,
        )
        self.orchestrators[orch_id] = orchestrator
        return orchestrator

    def remove_orchestrator(self, orch_id: str) -> None:
        orchestrator = self.orchestrators.pop(orch_id, None)
        if orchestrator is not None:
            orchestrator.terminate_now()

    async def send(self, orch_id: str, text: str) -> None:
        orchestrator = self.orchestrators.get(orch_id)
        if orchestrator is None:
            return
        await orchestrator.send(text)

    def orchestrator_name_for(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        for orchestrator in self.orchestrators.values():
            if orchestrator.session_id == session_id:
                return orchestrator.name
        return None

    def orchestrator_id_for(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        for orch_id, orchestrator in self.orchestrators.items():
            if orchestrator.session_id == session_id:
                return orch_id
        return None

    def set_model(self, model: str) -> None:
        self.model = model
        self.dispatcher.model = model
        for orchestrator in self.orchestrators.values():
            orchestrator.model = model
        write_config(self.home.config, model)

    def set_effort(self, effort: str | None) -> None:
        self.effort = effort
        self.dispatcher.effort = effort
        for orchestrator in self.orchestrators.values():
            orchestrator.effort = effort

    def terminate_now(self, grace: float = 1.0) -> None:
        runners: list[OpencodeRunner] = []
        for orchestrator in self.orchestrators.values():
            if orchestrator.runner is not None:
                runners.append(orchestrator.runner)
        runners.extend(self.dispatcher.runners.values())
        for runner in runners:
            runner.signal_terminate()
        if runners and grace > 0:
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                if all(runner.proc is None or runner.proc.returncode is not None for runner in runners):
                    break
                time.sleep(0.05)
        for runner in runners:
            runner.kill_if_alive()
        for orchestrator in self.orchestrators.values():
            orchestrator.runner = None
        self.dispatcher.runners.clear()

    async def shutdown(self) -> None:
        self.terminate_now()
        await self.dispatcher.stop()

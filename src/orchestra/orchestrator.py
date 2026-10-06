from __future__ import annotations

import asyncio
from pathlib import Path

from .events import AgentEvent
from .process import OpencodeRunner, ProcessResult, build_argv, build_env


class Orchestrator:
    def __init__(
        self,
        orch_id: str,
        name: str,
        ui,
        config: Path,
        inbox: Path,
        workspace: Path,
        model: str | None = None,
        effort: str | None = None,
    ):
        self.orch_id = orch_id
        self.name = name
        self.ui = ui
        self.workspace = workspace
        self.model = model
        self.effort = effort
        self.env = build_env(config, inbox)
        self.session_id: str | None = None
        self.runner: OpencodeRunner | None = None
        self.turn_lock = asyncio.Lock()

    async def send(self, prompt: str) -> ProcessResult:
        if self.turn_lock.locked():
            self.ui.on_orchestrator_state(self.orch_id, "queued")
        async with self.turn_lock:
            self.ui.on_orchestrator_state(self.orch_id, "thinking")
            argv = build_argv(
                agent="orchestra",
                directory=self.workspace,
                session_id=self.session_id,
                model=self.model,
                variant=self.effort,
                title=None if self.session_id else self.name,
            )
            runner = OpencodeRunner(argv, self.env, self.workspace, prompt)
            self.runner = runner

            def on_event(event: AgentEvent) -> None:
                if event.session_id:
                    self.session_id = event.session_id
                self.ui.on_orchestrator_event(self.orch_id, event)

            try:
                result = await runner.run(on_event)
            finally:
                self.runner = None
            if result.session_id:
                self.session_id = result.session_id
            self.ui.on_orchestrator_done(self.orch_id, result)
            return result

    def terminate_now(self) -> None:
        if self.runner:
            self.runner.terminate()

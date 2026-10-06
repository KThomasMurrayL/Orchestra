from __future__ import annotations

import asyncio
import inspect
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .events import AgentEvent, parse_line

EventCallback = Callable[[AgentEvent], None | Awaitable[None]]


def opencode_command() -> str:
    return shutil.which("opencode") or "opencode"


@dataclass
class ProcessResult:
    exit_code: int
    session_id: str | None
    stderr: str
    cancelled: bool = False


def build_argv(
    prompt: str,
    agent: str,
    directory: Path,
    session_id: str | None = None,
    model: str | None = None,
    title: str | None = None,
    auto: bool = False,
) -> list[str]:
    argv = [opencode_command(), "run", "--format", "json", "--agent", agent, "--dir", str(directory)]
    if session_id:
        argv += ["--session", session_id]
    if model:
        argv += ["--model", model]
    if title:
        argv += ["--title", title]
    if auto:
        argv.append("--auto")
    argv.append(prompt)
    return argv


def build_env(config: Path, inbox: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["OPENCODE_CONFIG"] = str(config)
    env["ORCHESTRA_INBOX"] = str(inbox)
    env["ORCHESTRA_AGENT"] = "orchestra"
    return env


class OpencodeRunner:
    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path):
        self.argv = argv
        self.env = env
        self.cwd = str(cwd)
        self.proc: asyncio.subprocess.Process | None = None
        self.session_id: str | None = None
        self.cancelled = False

    async def run(self, on_event: EventCallback) -> ProcessResult:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
        )
        stderr_lines: list[str] = []

        async def pump_stdout() -> None:
            stream = self.proc.stdout
            assert stream is not None
            async for raw in stream:
                event = parse_line(raw.decode("utf-8", "replace"))
                if event is None:
                    continue
                if event.session_id:
                    self.session_id = event.session_id
                result = on_event(event)
                if inspect.isawaitable(result):
                    await result

        async def pump_stderr() -> None:
            stream = self.proc.stderr
            assert stream is not None
            async for raw in stream:
                stderr_lines.append(raw.decode("utf-8", "replace"))
                if len(stderr_lines) > 400:
                    del stderr_lines[:200]

        await asyncio.gather(pump_stdout(), pump_stderr())
        code = await self.proc.wait()
        return ProcessResult(code, self.session_id, "".join(stderr_lines)[-8000:], self.cancelled)

    def terminate(self) -> None:
        self.cancelled = True
        proc = self.proc
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

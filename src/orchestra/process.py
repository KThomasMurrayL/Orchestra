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
    agent: str,
    directory: Path,
    session_id: str | None = None,
    model: str | None = None,
    variant: str | None = None,
    title: str | None = None,
    auto: bool = False,
) -> list[str]:
    argv = [opencode_command(), "run", "--format", "json", "--agent", agent, "--dir", str(directory)]
    if session_id:
        argv += ["--session", session_id]
    if model:
        argv += ["--model", model]
    if variant:
        argv += ["--variant", variant]
    if title:
        argv += ["--title", title]
    if auto:
        argv.append("--auto")
    return argv


def build_env(config: Path, inbox: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["OPENCODE_CONFIG"] = str(config)
    env["ORCHESTRA_INBOX"] = str(inbox)
    env["ORCHESTRA_AGENT"] = "orchestra"
    return env


STREAM_LIMIT = 16 * 1024 * 1024


class OpencodeRunner:
    def __init__(self, argv: list[str], env: dict[str, str], cwd: Path, prompt: str = "", limit: int = STREAM_LIMIT):
        self.argv = argv
        self.env = env
        self.cwd = str(cwd)
        self.prompt = prompt
        self.limit = limit
        self.proc: asyncio.subprocess.Process | None = None
        self.session_id: str | None = None
        self.cancelled = False

    async def run(self, on_event: EventCallback) -> ProcessResult:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
            limit=self.limit,
        )
        stderr_lines: list[str] = []

        async def pump_stdin() -> None:
            stream = self.proc.stdin
            assert stream is not None
            try:
                if self.prompt:
                    stream.write(self.prompt.encode("utf-8"))
                    await stream.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        async def emit(event: AgentEvent) -> None:
            if event.session_id:
                self.session_id = event.session_id
            result = on_event(event)
            if inspect.isawaitable(result):
                await result

        async def pump_stdout() -> None:
            stream = self.proc.stdout
            assert stream is not None
            while True:
                try:
                    raw = await stream.readline()
                except ValueError:
                    await emit(
                        AgentEvent(
                            kind="stderr",
                            text="[orchestra] dropped an oversized opencode event (line exceeded the stream limit)",
                        )
                    )
                    continue
                if not raw:
                    break
                event = parse_line(raw.decode("utf-8", "replace"))
                if event is not None:
                    await emit(event)

        async def pump_stderr() -> None:
            stream = self.proc.stderr
            assert stream is not None
            while True:
                try:
                    raw = await stream.readline()
                except ValueError:
                    stderr_lines.append("[orchestra] dropped an oversized stderr line\n")
                    continue
                if not raw:
                    break
                stderr_lines.append(raw.decode("utf-8", "replace"))
                if len(stderr_lines) > 400:
                    del stderr_lines[:200]

        await asyncio.gather(pump_stdin(), pump_stdout(), pump_stderr())
        code = await self.proc.wait()
        return ProcessResult(code, self.session_id, "".join(stderr_lines)[-8000:], self.cancelled)

    def signal_terminate(self) -> None:
        self.cancelled = True
        proc = self.proc
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    def kill_if_alive(self) -> None:
        proc = self.proc
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    def terminate(self) -> None:
        self.signal_terminate()

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from rich.markup import escape

from .events import AgentEvent
from .home import Home
from .process import OpencodeRunner, build_argv, build_env

TERMINAL = {"done", "failed", "cancelled"}


def sweep_interrupted(inbox: Path) -> None:
    for status_file in inbox.glob("*.status.json"):
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("status") in TERMINAL:
            continue
        data["status"] = "failed"
        data["detail"] = "interrupted when orchestra closed"
        data["ended"] = data.get("ended") or time.time()
        tmp = status_file.with_name(status_file.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, status_file)
        except OSError:
            pass


@dataclass
class Worker:
    id: str
    title: str
    agent: str
    prompt: str
    orchestrator: str = ""
    created: float = field(default_factory=time.time)
    status: str = "queued"
    detail: str = "waiting for a free slot"
    session_id: str | None = None
    exit_code: int | None = None
    started: float | None = None
    ended: float | None = None
    cost: float = 0.0
    tokens: int = 0
    result: str = ""
    error: str = ""
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=4000))
    _texts: dict[str, str] = field(default_factory=dict, repr=False)
    _message_parts: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _message_order: list[str] = field(default_factory=list, repr=False)
    _last_status_write: float = field(default=0.0, repr=False)

    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        return (self.ended or time.time()) - self.started

    def apply_event(self, event: AgentEvent) -> list[str]:
        out: list[str] = []
        if event.kind == "text" and event.part_id:
            message = event.message_id
            if message not in self._message_parts:
                self._message_parts[message] = []
                self._message_order.append(message)
            if event.part_id not in self._message_parts[message]:
                self._message_parts[message].append(event.part_id)
                self._texts[event.part_id] = ""
            previous = self._texts.get(event.part_id, "")
            current = event.text
            self._texts[event.part_id] = current
            delta = current[len(previous):] if current.startswith(previous) else current
            if delta.strip():
                out.append(escape(delta.rstrip()))
        elif event.kind == "tool":
            label = escape(event.tool or "tool")
            summary = escape(event.title)
            if event.status == "running":
                self.detail = f"{event.tool}: {event.title}".strip(": ")
                out.append(f"[#2dd4bf]→[/] [b]{label}[/] [dim]{summary}[/]")
            elif event.status == "completed":
                if event.tool in ("edit", "write", "bash"):
                    out.append(f"[dim #4ade80]✓[/] [dim]{label} {summary}[/]")
            elif event.status == "error":
                self.error = event.error
                out.append(f"[#f87171]✘[/] [b]{label}[/] [#f87171]{escape(event.error[:300])}[/]")
        elif event.kind == "step_finish":
            if event.cost:
                self.cost += event.cost
            if event.tokens:
                self.tokens += int(event.tokens.get("input", 0) or 0) + int(event.tokens.get("output", 0) or 0)
        elif event.kind in ("stderr", "error") and (event.text or event.error):
            self.error = event.error or self.error
            out.append(f"[#fbbf24]{escape((event.text or event.error).rstrip())}[/]")
        for line in out:
            self.lines.append(line)
        return out

    def result_text(self) -> str:
        if not self._message_order:
            return ""
        parts = self._message_parts.get(self._message_order[-1], [])
        chunks = [self._texts.get(part, "").strip() for part in parts]
        return "\n\n".join(chunk for chunk in chunks if chunk)

    def status_payload(self) -> dict:
        preview = " ".join(self.result.split()) if self.result else ""
        return {
            "id": self.id,
            "title": self.title,
            "agent": self.agent,
            "orchestrator": self.orchestrator,
            "status": self.status,
            "detail": self.detail,
            "sessionID": self.session_id,
            "created": self.created,
            "started": self.started,
            "ended": self.ended,
            "exitCode": self.exit_code,
            "cost": round(self.cost, 4),
            "tokens": self.tokens,
            "resultPreview": preview[:800],
            "error": self.error[:500],
        }


class Dispatcher:
    def __init__(self, ui, home: Home, workspace: Path, max_workers: int, model: str | None = None):
        self.ui = ui
        self.home = home
        self.workspace = workspace
        self.inbox = home.inbox
        self.model = model
        self.env = build_env(home.config, home.inbox)
        self.workers: dict[str, Worker] = {}
        self.runners: dict[str, OpencodeRunner] = {}
        self._seen: set[str] = set()
        self._sem = asyncio.Semaphore(max_workers)
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        sweep_interrupted(self.inbox)
        task = asyncio.create_task(self._loop())
        self._tasks.add(task)

    def terminate_now(self) -> None:
        self._stop.set()
        for runner in list(self.runners.values()):
            runner.terminate()

    async def stop(self) -> None:
        self.terminate_now()
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._scan()
            except Exception as exc:
                self.ui.on_notice(f"dispatcher error: {exc}")
            await asyncio.sleep(0.4)

    def _scan(self) -> None:
        for path in sorted(self.inbox.glob("*.task.json")):
            task_id = path.name[: -len(".task.json")]
            if task_id in self._seen:
                continue
            if (self.inbox / f"{task_id}.status.json").exists():
                self._seen.add(task_id)
                continue
            self._seen.add(task_id)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            worker = Worker(
                id=task_id,
                title=str(data.get("title") or task_id),
                agent=str(data.get("agent") or "builder"),
                prompt=str(data.get("prompt") or ""),
                orchestrator=str(data.get("orchestrator") or ""),
                created=float(data.get("created") or time.time()),
            )
            self.workers[task_id] = worker
            self.ui.on_worker_added(worker)
            self._write_status(worker, force=True)
            task = asyncio.create_task(self._run_worker(worker))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        for path in self.inbox.glob("*.cancel"):
            task_id = path.name[: -len(".cancel")]
            runner = self.runners.get(task_id)
            worker = self.workers.get(task_id)
            if runner and worker and worker.status == "running":
                worker.detail = "cancelling"
                self.ui.on_worker_updated(worker)
                runner.terminate()

    async def _run_worker(self, worker: Worker) -> None:
        async with self._sem:
            if self._stop.is_set():
                return
            worker.status = "running"
            worker.started = time.time()
            worker.detail = "starting opencode"
            self.ui.on_worker_updated(worker)
            self._write_status(worker, force=True)
            argv = build_argv(
                prompt=worker.prompt,
                agent=worker.agent,
                directory=self.workspace,
                model=self.model,
                title=worker.title,
                auto=True,
            )
            runner = OpencodeRunner(argv, self.env, self.workspace)
            self.runners[worker.id] = runner

            def on_event(event: AgentEvent) -> None:
                lines = worker.apply_event(event)
                if event.session_id and not worker.session_id:
                    worker.session_id = event.session_id
                if lines:
                    self.ui.on_worker_events(worker, lines)
                if event.kind == "tool" and event.status in ("running", "completed", "error"):
                    self.ui.on_worker_updated(worker)
                self._write_status(worker)

            result = await runner.run(on_event)
            worker.exit_code = result.exit_code
            if result.session_id:
                worker.session_id = result.session_id
            worker.ended = time.time()
            result_text = worker.result_text()
            if result_text:
                worker.result = result_text
            if result.cancelled:
                worker.status = "cancelled"
                worker.detail = "cancelled by orchestrator"
            elif result.exit_code == 0:
                worker.status = "done"
                worker.detail = "completed"
            else:
                tail = (result.stderr.strip().splitlines() or ["opencode exited with an error"])[-1]
                worker.status = "failed"
                worker.detail = tail[:200]
            self.runners.pop(worker.id, None)
            self._write_result(worker)
            self._write_status(worker, force=True)
            color = {"done": "#4ade80", "failed": "#f87171", "cancelled": "#94a3b8"}.get(worker.status, "#e2e8f0")
            self.ui.on_worker_events(
                worker,
                [f"[b {color}]worker {worker.status}[/] [dim]in {worker.elapsed():.1f}s (exit {worker.exit_code})[/]"],
            )
            self.ui.on_worker_updated(worker)
            self.ui.on_worker_finished(worker)

    def _write_status(self, worker: Worker, force: bool = False) -> None:
        now = time.time()
        if not force and now - worker._last_status_write < 0.75:
            return
        worker._last_status_write = now
        self._atomic_write(self.inbox / f"{worker.id}.status.json", worker.status_payload())

    def _write_result(self, worker: Worker) -> None:
        if not worker.result and not worker.error:
            return
        self._atomic_write(
            self.inbox / f"{worker.id}.result.json",
            {"result": worker.result, "error": worker.error, "status": worker.status},
        )

    def _atomic_write(self, path: Path, payload: dict) -> None:
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

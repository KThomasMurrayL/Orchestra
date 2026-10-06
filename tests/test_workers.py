import asyncio
import json

import pytest

from orchestra.events import AgentEvent
from orchestra.home import Home
from orchestra.workers import Dispatcher, Worker, sweep_interrupted


class NullUI:
    def on_notice(self, text):
        pass

    def on_worker_added(self, worker):
        pass

    def on_worker_events(self, worker, lines):
        pass

    def on_worker_updated(self, worker):
        pass

    def on_worker_finished(self, worker):
        pass


def make_worker() -> Worker:
    return Worker(id="t-1", title="Task", agent="builder", prompt="do it")


def test_text_events_accumulate_deltas():
    worker = make_worker()
    first = worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="hel"))
    second = worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="hello"))
    assert first == ["hel"]
    assert second == ["lo"]
    assert worker.result_text() == "hello"


def test_text_replacement_prints_full():
    worker = make_worker()
    worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="hello"))
    replaced = worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="goodbye"))
    assert replaced == ["goodbye"]


def test_last_message_wins_for_result():
    worker = make_worker()
    worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="working"))
    worker.apply_event(AgentEvent(kind="text", part_id="p2", message_id="m2", text="final answer"))
    assert worker.result_text() == "final answer"


def test_tool_events_update_detail_and_lines():
    worker = make_worker()
    lines = worker.apply_event(
        AgentEvent(kind="tool", tool="bash", status="running", title="pytest -q", tool_input={"command": "pytest -q"})
    )
    assert worker.detail == "bash: pytest -q"
    assert any("pytest -q" in line for line in lines)
    error_lines = worker.apply_event(AgentEvent(kind="tool", tool="bash", status="error", error="boom"))
    assert worker.error == "boom"
    assert any("boom" in line for line in error_lines)


def test_step_finish_sums_cost_and_tokens():
    worker = make_worker()
    worker.apply_event(AgentEvent(kind="step_finish", cost=0.01, tokens={"input": 10, "output": 5}))
    worker.apply_event(AgentEvent(kind="step_finish", cost=0.02, tokens={"input": 1, "output": 2}))
    assert round(worker.cost, 4) == 0.03
    assert worker.tokens == 18


def test_status_payload_shape():
    worker = make_worker()
    worker.apply_event(AgentEvent(kind="text", part_id="p1", message_id="m1", text="all done"))
    worker.result = worker.result_text()
    payload = worker.status_payload()
    assert payload["id"] == "t-1"
    assert payload["status"] == "queued"
    assert payload["resultPreview"] == "all done"


def test_sweep_interrupted_marks_running_failed(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "t-1.status.json").write_text('{"id":"t-1","status":"running","detail":"x"}')
    (inbox / "t-2.status.json").write_text('{"id":"t-2","status":"done"}')
    sweep_interrupted(inbox)
    interrupted = json.loads((inbox / "t-1.status.json").read_text())
    finished = json.loads((inbox / "t-2.status.json").read_text())
    assert interrupted["status"] == "failed"
    assert "interrupted" in interrupted["detail"]
    assert finished["status"] == "done"


def test_dispatcher_skips_already_handled_tasks(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "t-x.task.json").write_text('{"id":"t-x","title":"x","agent":"builder","prompt":"y"}')
    (inbox / "t-x.status.json").write_text('{"id":"t-x","status":"done"}')
    home = Home(base=tmp_path, config=tmp_path / "opencode.json", plugin=tmp_path / "p", inbox=inbox, plugin_ready=True)
    dispatcher = Dispatcher(ui=NullUI(), home=home, workspace=tmp_path, max_workers=1)
    dispatcher._scan()
    assert dispatcher.workers == {}


@pytest.mark.asyncio
async def test_dispatcher_picks_up_new_tasks(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "t-new.task.json").write_text('{"id":"t-new","title":"fresh","agent":"researcher","prompt":"y"}')

    async def noop(self, worker):
        return None

    monkeypatch.setattr(Dispatcher, "_run_worker", noop)
    home = Home(base=tmp_path, config=tmp_path / "opencode.json", plugin=tmp_path / "p", inbox=inbox, plugin_ready=True)
    dispatcher = Dispatcher(ui=NullUI(), home=home, workspace=tmp_path, max_workers=1)
    dispatcher._scan()
    assert list(dispatcher.workers) == ["t-new"]
    assert dispatcher.workers["t-new"].status == "queued"
    await asyncio.sleep(0)
    for task in dispatcher._tasks:
        task.cancel()
    await asyncio.gather(*dispatcher._tasks, return_exceptions=True)


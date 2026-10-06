from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from orchestra.process import OpencodeRunner, build_argv


def test_build_argv_includes_variant_when_set():
    argv = build_argv("builder", Path("/tmp"), model="m/m", variant="high", title="T", auto=True)
    assert "--variant" in argv
    assert argv[argv.index("--variant") + 1] == "high"
    assert "--auto" in argv
    assert "prompt text" not in argv


def test_build_argv_omits_variant_by_default():
    argv = build_argv("builder", Path("/tmp"))
    assert "--variant" not in argv


@pytest.mark.asyncio
async def test_runner_pipes_prompt_over_stdin(tmp_path: Path):
    script = "import sys; sys.stdout.write(sys.stdin.read().upper() + chr(10))"
    runner = OpencodeRunner([sys.executable, "-c", script], dict(os.environ), tmp_path, prompt="hello " * 100_000)
    events = []
    result = await asyncio.wait_for(runner.run(lambda event: events.append(event)), timeout=30)
    assert result.exit_code == 0
    assert events and "HELLO " in events[0].text
    assert len(events[0].text) > 500_000


@pytest.mark.asyncio
async def test_runner_survives_oversized_output_line(tmp_path: Path):
    script = (
        "import sys, json\n"
        "sys.stdout.write('x' * 200000 + chr(10))\n"
        "sys.stdout.write(json.dumps({'type': 'text', 'part': {'type': 'text', 'text': 'after'}}) + chr(10))\n"
    )
    runner = OpencodeRunner([sys.executable, "-c", script], dict(os.environ), tmp_path, limit=65536)
    events = []
    result = await asyncio.wait_for(runner.run(lambda event: events.append(event)), timeout=30)
    assert result.exit_code == 0
    assert any(event.kind == "stderr" and "oversized" in event.text for event in events)
    assert any(event.kind == "text" and event.text == "after" for event in events)


@pytest.mark.asyncio
async def test_runner_terminate_kills_process(tmp_path: Path):
    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    runner = OpencodeRunner(argv, dict(os.environ), tmp_path)
    task = asyncio.create_task(runner.run(lambda event: None))
    for _ in range(100):
        if runner.proc is not None:
            break
        await asyncio.sleep(0.05)
    assert runner.proc is not None
    runner.signal_terminate()
    await asyncio.sleep(0.1)
    runner.kill_if_alive()
    result = await asyncio.wait_for(task, timeout=10)
    assert result.cancelled is True
    assert runner.proc.returncode is not None

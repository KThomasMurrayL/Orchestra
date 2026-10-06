from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    kind: str = "raw"
    session_id: str = ""
    part_id: str = ""
    message_id: str = ""
    call_id: str = ""
    text: str = ""
    tool: str = ""
    status: str = ""
    title: str = ""
    output: str = ""
    error: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    cost: float | None = None
    tokens: dict[str, Any] | None = None
    raw: Any = None


def _truncate(value: Any, limit: int = 240) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text[:limit]


def tool_summary(tool: str, tool_input: dict[str, Any], title: str = "") -> str:
    if title:
        return _truncate(title)
    if tool == "bash":
        return _truncate(tool_input.get("command", ""))
    if tool in ("read", "write", "edit", "list"):
        return _truncate(tool_input.get("filePath") or tool_input.get("path") or "")
    if tool == "grep":
        return _truncate(tool_input.get("pattern", ""))
    if tool == "dispatch_task":
        return _truncate(f"{tool_input.get('agent', '?')}: {tool_input.get('title', '')}")
    for value in tool_input.values():
        if isinstance(value, str) and value.strip():
            return _truncate(value)
    return ""


def parse_line(line: str) -> AgentEvent | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return AgentEvent(kind="stderr", text=line)
    if not isinstance(data, dict):
        return AgentEvent(kind="raw", raw=data)
    part = data.get("part") if isinstance(data.get("part"), dict) else {}
    event = AgentEvent(
        kind=str(data.get("type", "raw")),
        session_id=str(data.get("sessionID", "") or part.get("sessionID", "")),
        part_id=str(part.get("id", "")),
        message_id=str(part.get("messageID", "")),
        raw=data,
    )
    part_type = part.get("type")
    if part_type == "text" or event.kind == "text":
        event.kind = "text"
        event.text = str(part.get("text", ""))
    elif part_type == "reasoning":
        event.kind = "reasoning"
        event.text = str(part.get("text", ""))
    elif part_type == "tool":
        event.kind = "tool"
        event.tool = str(part.get("tool", ""))
        event.call_id = str(part.get("callID", ""))
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        event.status = str(state.get("status", ""))
        event.tool_input = state.get("input") if isinstance(state.get("input"), dict) else {}
        event.title = tool_summary(event.tool, event.tool_input, str(state.get("title", "") or ""))
        if event.status == "completed":
            event.output = str(state.get("output", ""))
        elif event.status == "error":
            event.error = str(state.get("error", ""))
    elif part_type == "step-finish":
        event.kind = "step_finish"
        cost = part.get("cost")
        event.cost = float(cost) if isinstance(cost, (int, float)) else None
        tokens = part.get("tokens")
        event.tokens = tokens if isinstance(tokens, dict) else None
    elif part_type == "step-start":
        event.kind = "step_start"
    elif event.kind == "error":
        error = data.get("error")
        event.error = _truncate(error if error is not None else data, 500)
    return event

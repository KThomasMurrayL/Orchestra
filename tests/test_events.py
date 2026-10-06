from orchestra.events import parse_line, tool_summary


def test_parse_text_event():
    line = '{"type":"text","sessionID":"ses_1","part":{"id":"prt_1","messageID":"msg_1","type":"text","text":"hello"}}'
    event = parse_line(line)
    assert event is not None
    assert event.kind == "text"
    assert event.text == "hello"
    assert event.session_id == "ses_1"
    assert event.part_id == "prt_1"


def test_parse_tool_event():
    line = (
        '{"type":"message.part.updated","sessionID":"ses_2","part":{"id":"prt_2","messageID":"msg_2",'
        '"type":"tool","callID":"call_1","tool":"dispatch_task","state":{"status":"completed",'
        '"input":{"title":"Do it","agent":"builder"},"output":"ok","title":"Dispatched","metadata":{}}}}'
    )
    event = parse_line(line)
    assert event is not None
    assert event.kind == "tool"
    assert event.tool == "dispatch_task"
    assert event.status == "completed"
    assert event.title == "Dispatched"


def test_parse_step_finish():
    line = (
        '{"type":"step_finish","sessionID":"ses_3","part":{"id":"prt_3","messageID":"msg_3",'
        '"type":"step-finish","cost":0.01,"tokens":{"input":10,"output":2}}}'
    )
    event = parse_line(line)
    assert event is not None
    assert event.kind == "step_finish"
    assert event.cost == 0.01
    assert event.tokens == {"input": 10, "output": 2}


def test_tool_summary_bash():
    assert tool_summary("bash", {"command": "ls -la"}) == "ls -la"


def test_parse_non_json():
    event = parse_line("plain error text")
    assert event is not None
    assert event.kind == "stderr"


def test_parse_blank():
    assert parse_line("   ") is None

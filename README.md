# orchestra

[![CI](https://github.com/KThomasMurrayL/Orchestra/actions/workflows/ci.yml/badge.svg)](https://github.com/KThomasMurrayL/Orchestra/actions/workflows/ci.yml)

Talk to one or more planner agents. Each plans and dispatches **real worker agents** — every worker
a separate `opencode run` process with its own session — and you can click any active agent in the
sidebar to watch what it is doing live.

`orchestra` is deliberately a thin host, not a router: the plan-only orchestrators decide what work
gets done and call `dispatch_task`; the CLI just spawns the worker instances they ask for.

Runs on macOS, Windows, and Linux — each worker is a real `opencode run` process, and the CLI
resolves the `opencode` executable itself so npm shims on Windows work too.

```
┌ Agents ──────────────┐┌ Orchestrator 2 ────────────────────────────┐
│ ✦ Orchestrator       ││ you › add caching to the search endpoint   │
│ ✦ Orchestrator 2     ││                                           │
│ ◐ Add cache layer    ││ orchestra › A: builder adds an LRU cache… │
│ ✓ Write tests        ││                                           │
│ ○ Review change      ││                                           │
└──────────────────────┘└───────────────────────────────────────────┘
```

## How it works

- **Orchestrators** — `opencode` agents named `orchestra` with edit/bash/task denied. They only
  read, plan, and call the dispatch tools. Press the new key to create another; a dialog asks for
  its name. Each gets its own chat, its own opencode session, and its own view of its tasks. You
  never talk to anyone else. Orchestrators (name, session, chat history) are saved and restored
  across restarts.
- **Dispatch bridge** — a local opencode plugin exposes `dispatch_task`, `check_tasks`,
  `wait_tasks`, and `cancel_task`. Tasks are written as JSON into a per-run inbox and tagged with
  the dispatching orchestrator's session, so orchestrators only ever see and manage their own work.
- **Dispatcher** — watches the inbox and starts each task as its own `opencode run --agent <role>
  --format json` subprocess, streaming events into the TUI and writing status back for `check_tasks`.
  One shared worker pool with a global concurrency cap serves all orchestrators.
- **Workers** — proper instances with their own session IDs, running as `builder`, `researcher`,
  `tester`, or `reviewer` with `--auto` permissions. They never see any conversation.

```
orchestrator 1 ─┐
orchestrator 2 ─┼─ dispatch_task ─► inbox (tagged by owner) ─► dispatcher ─► opencode run (worker)
orchestrator N ─┘        ▲                                                        │
                         └────────── check_tasks / wait_tasks (own tasks) ◄────────┘
```

## Requirements

- macOS, Windows, or Linux (macOS and Windows are the primary targets)
- [`opencode`](https://opencode.ai) on `PATH`, with at least one provider authenticated
- Python 3.11+

## Install

### From a release (no git clone)

Grab the source archive for the latest release from
<https://github.com/KThomasMurrayL/Orchestra/releases>, extract it, and run the installer for your
OS:

```sh
./install.sh                          # macOS / Linux
```

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1   # Windows
```

The installers create a virtualenv, install the package with voice support, and put `orchestra` on
your `PATH`.

### macOS and Linux

```sh
cd ~/orchestra
./install.sh
```

The installer creates `~/orchestra/.venv`, installs the package (editable, with voice support), and
symlinks the `orchestra` command into the first writable bin directory on your `PATH`
(`/opt/homebrew/bin`, `/usr/local/bin`, or `~/.local/bin`). Override the target with
`BIN_DIR=/some/bin ./install.sh`.

### Windows

```powershell
cd $HOME\orchestra
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer creates `.venv`, installs the package (editable, with voice support), writes an
`orchestra.cmd` shim to `%USERPROFILE%\.orchestra-bin`, and adds that directory to your user `PATH`
(restart your terminal afterwards). Set `$env:PYTHON` first to use a specific interpreter.

Voice support is optional: on Apple Silicon it installs `mlx-whisper`, and on Windows, Intel macOS,
and Linux it installs `faster-whisper`. If the voice extras are not installed the TUI still works
and `F2` reports that voice is unavailable. To install without voice, run the same installer after
removing the `[voice]` extra — or manually:

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

To uninstall: remove the `orchestra` symlink/shim created above, then delete the project's `.venv`
and `~/.orchestra` (`%USERPROFILE%\.orchestra` on Windows).

## Run

```sh
orchestra --dir ~/code/my-project
```

`orchestra --version` and `orchestra --help` work anywhere on your `PATH`.

If `--model` is not given, orchestra uses your last picked model (`~/.orchestra/model`), then `model`
from your global opencode config, then auto-selects the first model from an authenticated provider.
The free `opencode/*` Zen models cannot be used from spawned `opencode run` processes, so they are
hidden from the picker.

| Flag | Meaning |
| --- | --- |
| `--dir PATH` | workspace the agents operate in (default: current directory) |
| `--model PROVIDER/MODEL` | override the model for every agent |
| `--effort LEVEL` | reasoning effort: `minimal`, `low`, `medium`, `high`, or `max` |
| `--max-workers N` | cap concurrency (default 4) |
| `--no-voice` | disable microphone input |

### Keys

| Key | Action |
| --- | --- |
| `enter` | send your message to the active orchestrator |
| new key | create a new orchestrator (a dialog asks for its name) — `ctrl+t` on macOS, `ctrl+n` on Windows/Linux, or click **+ new** in the sidebar |
| `ctrl+w` | close the selected orchestrator (when it is idle) |
| `m` | open the model picker (or click the model badge, top right) |
| `e` | open the effort picker (or click the effort badge, top right) |
| `F2` / `ctrl+r` | start/stop voice recording (or click **mic**, top right) |
| mouse / arrows | select an orchestrator or worker in the sidebar |
| `ctrl+q` | quit, after a confirmation dialog (or click **✕** in the top right) |

The new-orchestrator key is chosen per platform because macOS terminals and IDE terminals often
capture `ctrl+n`. Override it with `ORCHESTRA_NEW_KEY=ctrl+shift+n` (any Textual key name). The
**+ new** button in the sidebar always works regardless of terminal shortcuts — keybinding hints are
also shown in the footer and under the sidebar.

### Multiple orchestrators

Press the new-orchestrator key (`ctrl+t` on macOS, `ctrl+n` on Windows/Linux) or click **+ new**
next to the ORCHESTRATORS heading; a dialog lets you name the new orchestrator (press `enter` to
accept the default). Each one has its own chat history, its own opencode session, and its own tasks —
`check_tasks`, `wait_tasks`, and `cancel_task` only see work that orchestrator dispatched, and
workers in the sidebar show which orchestrator they came from. The input always sends to the
orchestrator you last had selected; switch between them from the sidebar. `ctrl+w` closes the
selected orchestrator if it is idle (workers it already dispatched keep running).

### Persistence

Orchestrators survive quitting the CLI. Each one is saved with its name and opencode session in
`~/.orchestra/orchestrators.json`, and its chat history in `~/.orchestra/transcripts/<id>.jsonl`.
On the next launch they are restored with their history replayed, and your next message continues
the same session with full context. The task inbox at `~/.orchestra/inbox/` is stable across runs,
so old task statuses stay visible to `check_tasks`; tasks that were still running when you quit are
marked failed with an "interrupted" note instead of being re-run. Quitting (`ctrl+q` or **✕**) asks
for confirmation and terminates any running workers.

### Models

Click the model badge in the top-right corner (or press `m`) to open a searchable picker. The choice
applies immediately to the orchestrator's next turn and to every worker dispatched afterwards, and is
remembered for future runs. Models are listed from `opencode models`; models the provider cannot run
via `opencode run` are hidden with a note.

### Effort

Press `e` or click the effort badge in the top-right corner to choose reasoning effort: `default`,
`minimal`, `low`, `medium`, `high`, or `max`. This maps to opencode's `--variant` flag and is applied
to both orchestrators and workers, so planners and workers can think harder (or cheaper) on demand.
The choice applies from the next turn/dispatch and is remembered in `~/.orchestra/effort`.

Effort is provider-specific: unsupported levels are ignored by opencode rather than failing, and
providers without reasoning controls simply behave as usual. Set a starting value with
`ORCHESTRA_EFFORT=high` or `--effort high`; `default` sends no flag.

### Skills

Orchestrators and workers understand [opencode skills](https://opencode.ai/docs/skills/). Put a skill
in `~/.orchestra/skills/<name>/SKILL.md` and Orchestra wires it into the generated opencode config,
so every orchestrator and worker you launch can load it — it survives restarts and needs no config
editing:

```sh
orchestra skills add paper-review --description "Use when reviewing ML papers"
# edit ~/.orchestra/skills/paper-review/SKILL.md, then restart orchestra
orchestra skills list     # what is visible, and where it came from
orchestra skills path     # the user skills directory
orchestra skills remove paper-review
```

Skills are also picked up from opencode's own locations without any setup: your global
`~/.config/opencode/skill(s)`, custom `skills.paths` in your global opencode config (preserved when
Orchestra rewrites its config), project `.opencode/skill(s)`, and the auto-loaded `~/.claude/skills`
and `~/.agents/skills`. `orchestra skills list` shows each skill's source so you can tell where it
came from. Orchestrators fold matching skills into the tasks they dispatch, and workers load them
directly when relevant.

### Voice

Click the **mic** button in the top right, press `F2`, or press `ctrl+r`, speak, then stop. The
transcript is inserted into the prompt for review; press `enter` to send. Recording adapts to your
input device's native sample rate and channels, so it works with WASAPI (Windows), CoreAudio
(macOS), and ALSA/PulseAudio (Linux).

- Backends: `mlx-whisper` on Apple Silicon, `faster-whisper` on Windows/Intel macOS/Linux. The model
  is downloaded on first use and the transcript language is English (`*.en` models).
- `ORCHESTRA_WHISPER_MODEL` overrides the mlx model; `ORCHESTRA_FASTER_WHISPER_MODEL` overrides the
  faster-whisper model (default `base.en`).
- `ORCHESTRA_INPUT_DEVICE` picks a microphone by index or name substring, e.g.
  `ORCHESTRA_INPUT_DEVICE="usb"` or `ORCHESTRA_INPUT_DEVICE=2`.
- If dictation does nothing, run `orchestra --check-voice`: it lists input devices, records three
  seconds, reports the peak level, and attempts a transcription. On Windows also check
  **Settings > Privacy & security > Microphone** and allow desktop apps.
- `ORCHESTRA_HOME` (default `~/.orchestra`) holds generated config, the plugin, saved orchestrators,
  transcripts, and the task inbox.
- Tasks and statuses live in `~/.orchestra/inbox/`. Status files written there are what
  `check_tasks` reports.

### Example prompts

- `Research how auth works, then have a builder add rate limiting to the login endpoint.`
- `Review the diff on this branch and dispatch a builder to fix anything critical.`
- `Figure out why tests are slow and make it faster.`

## Notes

- The orchestrator is restricted to planning: it cannot edit, run shell commands, or spawn opencode
  subagents. Workers run with `--auto` so they never block on prompts.
- Workers are independent processes. Killing `orchestra` terminates them.
- Results are never auto-routed anywhere: the orchestrator pulls them with `check_tasks` /
  `wait_tasks`, and you can read each agent's pane directly.

## Development

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

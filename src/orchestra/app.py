from __future__ import annotations

import asyncio
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Button, ContentSwitcher, Footer, Input, ListItem, ListView, Markdown, RichLog, Static

from .controller import Controller
from .events import AgentEvent
from .home import prepare_home
from .keys import ALT_ORCH_KEY, NEW_ORCH_KEY
from .models import list_models, save_model
from .process import ProcessResult
from .state import (
    SavedOrchestrator,
    append_transcript,
    delete_transcript,
    load_orchestrators,
    load_transcript,
    save_orchestrators,
)
from .voice import MIN_PEAK, VoiceInput
from .widgets import ChatView, ConfirmQuit, ModelBadge, ModelPicker, NameDialog
from .workers import TERMINAL, Worker

THEME = Theme(
    name="orchestra",
    dark=True,
    primary="#2dd4bf",
    secondary="#818cf8",
    accent="#f59e0b",
    success="#4ade80",
    warning="#fbbf24",
    error="#f87171",
    foreground="#e2e8f0",
    background="#0b0f14",
    surface="#111827",
    panel="#151c28",
    boost="#1f2a3a",
)

STATUS_COLORS = {
    "queued": "#fbbf24",
    "running": "#38bdf8",
    "done": "#4ade80",
    "failed": "#f87171",
    "cancelled": "#94a3b8",
}

STATUS_ICONS = {
    "queued": "○",
    "running": "◐",
    "done": "✓",
    "failed": "✗",
    "cancelled": "⊘",
}

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ORCH_COLORS = ["#2dd4bf", "#818cf8", "#f59e0b", "#38bdf8", "#f472b6", "#a3e635"]


class OrchestraApp(App[None]):
    CSS = """
    Screen { background: $background; }

    #topbar {
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    #topbar-brand {
        width: 1fr;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    #topbar-model {
        width: auto;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    #topbar-model:hover { background: $primary 30%; }
    #voice {
        width: auto;
        height: 1;
        min-width: 5;
        border: none;
        background: $boost;
        color: $text-muted;
        padding: 0 1;
        margin: 0 0 0 1;
    }
    #voice:hover { background: $primary 30%; color: $text; }
    #voice.recording { background: $error; color: black; }
    #quit {
        width: auto;
        height: 1;
        min-width: 3;
        border: none;
        background: $boost;
        color: $text-muted;
        padding: 0 1;
        margin: 0 0 0 1;
    }
    #quit:hover { background: $error 50%; color: $text; }

    #body { height: 1fr; }

    #sidebar {
        width: 36;
        background: $surface;
        border-right: solid $panel;
    }
    #sidebar-head { height: 1; }
    #sidebar-title { width: 1fr; color: $text-muted; padding: 0 1; }
    #new-orch {
        height: 1;
        min-width: 7;
        border: none;
        background: $boost;
        color: $text;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    #new-orch:hover { background: $primary 30%; }
    #new-orch:focus { background: $primary 40%; }
    #agents {
        height: 1fr;
        background: transparent;
        padding: 0;
    }
    #agents > ListItem {
        padding: 0 1;
        border-left: wide transparent;
    }
    #agents > ListItem.-highlight {
        background: $boost;
        border-left: wide $primary;
    }
    #sidebar-hint {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }

    #main { width: 1fr; }
    #chat {
        height: 1fr;
        padding: 0 1;
        background: transparent;
    }
    ChatView {
        height: 1fr;
        padding: 0 1;
        background: transparent;
    }
    .hero {
        border: round $primary 45%;
        padding: 1 2;
        margin: 1 0;
    }
    .msg { width: auto; height: auto; }
    .msg.user {
        background: $primary 15%;
        border-left: thick $primary;
        padding: 0 1;
        margin: 1 0 1 6;
    }
    .msg.notice { color: $text-muted; margin: 0 0 0 6; }
    .msg.assistant {
        background: transparent;
        border-left: thick $secondary;
        padding: 0 1;
        margin: 0 8 1 0;
    }

    #detail { height: 1fr; }
    #detail-header {
        height: auto;
        background: $panel;
        padding: 1 2;
        margin: 0 1 1 1;
    }
    #detail-log {
        height: 1fr;
        background: transparent;
        padding: 0 2;
    }

    #statusbar { height: 1; background: $panel; }
    #status-state { width: auto; padding: 0 1; }
    #status-info { width: 1fr; color: $text-muted; padding: 0 1; }
    #status-voice { width: auto; padding: 0 1; color: $text-muted; }

    #prompt {
        border: round $primary 40%;
        background: $surface;
        margin: 1 1 0 1;
    }
    #prompt:focus { border: round $accent; }

    Footer { background: $panel; }
    """
    BINDINGS = [
        Binding("f2", "toggle_voice", "voice", show=True),
        Binding("ctrl+r", "toggle_voice", "voice", show=False),
        Binding("m", "pick_model", "model", show=True),
        Binding(NEW_ORCH_KEY, "new_orchestrator", "new", show=True, priority=True),
        Binding(ALT_ORCH_KEY, "new_orchestrator", "new", show=False),
        Binding("ctrl+w", "close_orchestrator", "close", show=True),
        Binding("ctrl+q", "confirm_quit", "quit", show=True),
        Binding("ctrl+c", "quit", "quit", show=False),
        Binding("escape", "focus_prompt", "prompt", show=False),
    ]

    def __init__(self, workspace: Path, model: str | None = None, voice_enabled: bool = True, max_workers: int = 4):
        super().__init__()
        self.workspace = workspace
        self.model = model
        self.voice = VoiceInput(enabled=voice_enabled)
        self.home = prepare_home(model=model)
        self.controller = Controller(workspace=workspace, home=self.home, model=model, max_workers=max_workers)
        self.worker_items: dict[str, ListItem] = {}
        self.selected = ""
        self.active_orch = ""
        self._orch_counter = 0
        self._orch_names: dict[str, str] = {}
        self._orch_shorts: dict[str, str] = {}
        self._orch_colors: dict[str, str] = {}
        self._orch_states: dict[str, str] = {}
        self._orch_items: dict[str, ListItem] = {}
        self._orch_views: dict[str, ChatView] = {}
        self._streams: dict[str, tuple[Markdown | None, str | None]] = {}
        self._turn_texts: dict[str, dict[str, str]] = {}
        self._voice_note = self.voice.status.reason
        self._shutdown_requested = False
        self._spin = 0
        self.register_theme(THEME)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("", id="topbar-brand", markup=True),
            ModelBadge("", id="topbar-model", markup=True),
            Button("mic", id="voice"),
            Button("✕", id="quit"),
            id="topbar",
        )
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                with Horizontal(id="sidebar-head"):
                    yield Static("ORCHESTRATORS", id="sidebar-title")
                    yield Button("+ new", id="new-orch")
                yield ListView(id="agents")
                yield Static(f"[dim]{NEW_ORCH_KEY} new · m model · F2 voice[/]", id="sidebar-hint", markup=True)
            with ContentSwitcher(initial="detail", id="main"):
                with Vertical(id="detail"):
                    yield Static("", id="detail-header", markup=True)
                    yield RichLog(id="detail-log", markup=True, wrap=True, highlight=False)
        with Horizontal(id="statusbar"):
            yield Static("", id="status-state", markup=True)
            yield Static("", id="status-info", markup=True)
            yield Static("", id="status-voice", markup=True)
        yield Input(placeholder="Ask the orchestrator to plan…", id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "orchestra"
        self.sub_title = str(self.workspace)
        self.theme = "orchestra"
        self._topbar_brand = self.query_one("#topbar-brand", Static)
        self._topbar_model = self.query_one("#topbar-model", ModelBadge)
        self._voice_button = self.query_one("#voice", Button)
        self._agents = self.query_one("#agents", ListView)
        self._switcher = self.query_one("#main", ContentSwitcher)
        self._detail_header = self.query_one("#detail-header", Static)
        self._detail_log = self.query_one("#detail-log", RichLog)
        self._status_state = self.query_one("#status-state", Static)
        self._status_info = self.query_one("#status-info", Static)
        self._status_voice = self.query_one("#status-voice", Static)
        self._prompt = self.query_one("#prompt", Input)
        self.controller.attach(self)
        await self._agents.append(ListItem(Static("[dim]WORKERS[/]", markup=True), id="workers-label", disabled=True))
        restored = load_orchestrators()
        if restored:
            for entry in restored:
                await self.add_orchestrator(name=entry.name, orch_id=entry.id, session_id=entry.session_id, quiet=True)
            self.notify(f"restored {len(restored)} orchestrator(s)", timeout=3)
        else:
            await self.add_orchestrator()
        await self.controller.start()
        self.run_worker(asyncio.to_thread(list_models), group="models", exclusive=False)
        self._render_topbar()
        self._render_status()
        self._prompt.focus()
        self.set_interval(0.2, self._tick)
        if not self.home.plugin_ready:
            message = (
                "dispatch plugin dependencies are missing; run: "
                "npm install --prefix " + str(self.home.base) + " @opencode-ai/plugin"
            )
            self._chat_for(self.active_orch).add_notice(message)
            self.notify(message, severity="warning", timeout=12)

    async def add_orchestrator(
        self,
        name: str | None = None,
        orch_id: str | None = None,
        session_id: str | None = None,
        quiet: bool = False,
    ) -> str:
        entries = load_transcript(orch_id) if orch_id else []
        if orch_id:
            self._orch_counter = max(self._orch_counter, int(orch_id.lstrip("o") or 0))
            oid = orch_id
        else:
            self._orch_counter += 1
            oid = f"o{self._orch_counter}"
        auto = "Orchestrator" if self._orch_counter == 1 else f"Orchestrator {self._orch_counter}"
        display = (name or auto).strip() or auto
        display = self._unique_name(display, exclude=oid)
        number = int(oid.lstrip("o") or 1)
        color = ORCH_COLORS[(number - 1) % len(ORCH_COLORS)]
        self._orch_names[oid] = display
        self._orch_shorts[oid] = f"O{number}"
        self._orch_colors[oid] = color
        self._orch_states[oid] = "idle"
        self._streams[oid] = (None, None)
        self._turn_texts[oid] = {}
        orchestrator = self.controller.add_orchestrator(oid, display)
        if session_id:
            orchestrator.session_id = session_id
        view = ChatView(id=f"chat-{oid}", hero_name=None if entries else display)
        self._orch_views[oid] = view
        await self._switcher.add_content(view, set_current=True)
        for entry in entries:
            if entry["type"] == "user":
                view.add_user(entry["text"])
            else:
                view.add_assistant().update(entry["text"])
        item = ListItem(Static(self._orch_label(oid), markup=True), id=oid)
        self._orch_items[oid] = item
        self._agents.insert(self._orch_counter - 1, [item])
        self._switch(oid)
        self._save_state()
        if not quiet:
            self.notify(f"{display} ready", timeout=2)
        return oid

    def _unique_name(self, base: str, exclude: str | None = None) -> str:
        existing = {name for oid, name in self._orch_names.items() if oid != exclude}
        if base not in existing:
            return base
        index = 2
        while f"{base} ({index})" in existing:
            index += 1
        return f"{base} ({index})"

    def _save_state(self) -> None:
        saved = [
            SavedOrchestrator(
                id=oid,
                name=self._orch_names[oid],
                session_id=getattr(self.controller.orchestrators.get(oid), "session_id", None),
            )
            for oid in self._orch_views
        ]
        save_orchestrators(saved)

    def close_orchestrator(self, orch_id: str) -> None:
        if orch_id not in self._orch_views:
            return
        name = self._orch_names[orch_id]
        if self._orch_states.get(orch_id) != "idle":
            self.notify(f"{name} is still working; wait for it to finish", severity="warning", timeout=4)
            return
        item = self._orch_items.pop(orch_id, None)
        index = list(self._agents.children).index(item) if item is not None else None
        if index is not None:
            self._agents.remove_items([index])
        self._orch_views.pop(orch_id).remove()
        self._orch_names.pop(orch_id, None)
        self._orch_shorts.pop(orch_id, None)
        self._orch_colors.pop(orch_id, None)
        self._orch_states.pop(orch_id, None)
        self._streams.pop(orch_id, None)
        self._turn_texts.pop(orch_id, None)
        self.controller.remove_orchestrator(orch_id)
        delete_transcript(orch_id)
        self._save_state()
        self.notify(f"{name} closed", timeout=2)
        if self.active_orch == orch_id:
            next_id = next(iter(self._orch_views))
            self._switch(next_id)

    def _chat_for(self, orch_id: str) -> ChatView:
        return self._orch_views[orch_id]

    def _orch_label(self, orch_id: str) -> str:
        color = self._orch_colors[orch_id]
        name = self._orch_names[orch_id]
        state = self._orch_states.get(orch_id, "idle")
        icon = SPINNER[self._spin] if state in ("thinking", "queued") else "✦"
        session = getattr(self.controller.orchestrators.get(orch_id), "session_id", None)
        session_label = f"…{session[-6:]}" if session else "new session"
        return f"[{color}]{icon}[/] [b]{name}[/]\n  [dim]{state} · {session_label}[/]"

    def _refresh_orch_item(self, orch_id: str) -> None:
        item = self._orch_items.get(orch_id)
        if item is not None:
            item.query_one(Static).update(self._orch_label(orch_id))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self._prompt:
            return
        text = event.value.strip()
        if not text or not self.active_orch:
            return
        event.input.value = ""
        self._chat_for(self.active_orch).add_user(text)
        append_transcript(self.active_orch, {"type": "user", "text": text})
        self._switch(self.active_orch)
        self.run_worker(self.controller.send(self.active_orch, text), group=f"orch-{self.active_orch}", exclusive=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-orch":
            self.prompt_new_orchestrator()
        elif event.button.id == "voice":
            self.action_toggle_voice()
        elif event.button.id == "quit":
            self.action_confirm_quit()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is not None and event.item.id:
            self._switch(event.item.id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is not None and event.item.id:
            self._switch(event.item.id)

    def action_focus_prompt(self) -> None:
        self._prompt.focus()

    def action_toggle_voice(self) -> None:
        self.run_worker(self._toggle_voice(), group="voice", exclusive=True)

    def action_pick_model(self) -> None:
        self.push_model_picker()

    def action_new_orchestrator(self) -> None:
        self.prompt_new_orchestrator()

    def prompt_new_orchestrator(self) -> None:
        self.push_screen(NameDialog(self._next_default_name()), self._on_name_chosen)

    def _next_default_name(self) -> str:
        return "Orchestrator" if self._orch_counter == 0 else f"Orchestrator {self._orch_counter + 1}"

    def _on_name_chosen(self, name: str | None) -> None:
        if name:
            self.run_worker(self.add_orchestrator(name=name), group="new-orchestrator", exclusive=False)

    def action_confirm_quit(self) -> None:
        self.push_screen(ConfirmQuit(), self._on_quit_confirmed)

    def _on_quit_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self.action_quit()

    def action_close_orchestrator(self) -> None:
        target = self.selected if self.selected in self._orch_views else self.active_orch
        if not target or target not in self._orch_views:
            self.notify("select an orchestrator to close", severity="warning")
            return
        if len(self._orch_views) <= 1:
            self.notify("at least one orchestrator is required", severity="warning")
            return
        self.close_orchestrator(target)

    def push_model_picker(self) -> None:
        self.push_screen(ModelPicker(self.model), self._on_model_chosen)

    def _on_model_chosen(self, model: str | None) -> None:
        if model:
            self.set_model(model)

    def set_model(self, model: str) -> None:
        if model == self.model:
            self.notify(f"already using {model}", timeout=2)
            return
        self.model = model
        try:
            save_model(model)
        except OSError:
            pass
        self.controller.set_model(model)
        self._render_topbar()
        self._render_status()
        if self.active_orch:
            self._chat_for(self.active_orch).add_notice(f"model set to {model}")
        self.notify(f"model → {model}", timeout=3)

    def action_quit(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self.controller.terminate_now()
        self.exit()

    async def _toggle_voice(self) -> None:
        if not self.voice.status.available:
            self.notify(self.voice.status.reason, severity="warning", timeout=6)
            return
        if self.voice.recording:
            try:
                path = self.voice.stop()
            except Exception as exc:
                self.notify(f"recording failed: {exc}", severity="error")
                self._render_status()
                return
            if path is None:
                self._voice_note = self.voice.status.reason
                self._render_status()
                self.notify("nothing recorded", severity="warning")
                return
            if self.voice.last_peak < MIN_PEAK:
                self._voice_note = self.voice.status.reason
                self._render_status()
                message = "no microphone signal detected"
                if self.voice.device_name:
                    message += f" from '{self.voice.device_name[:40]}'"
                self.notify(
                    message + " — check mic permissions/mute, or set ORCHESTRA_INPUT_DEVICE. Run `orchestra --check-voice`.",
                    severity="warning",
                    timeout=12,
                )
                return
            self._voice_note = "transcribing…"
            self._render_status()
            try:
                text = await self.voice.transcribe(path)
            except Exception as exc:
                self.notify(f"transcription failed: {exc}", severity="error", timeout=8)
                text = ""
            self._voice_note = self.voice.status.reason
            self._render_status()
            if text:
                self._prompt.value = (self._prompt.value + " " + text).strip()
                self._prompt.focus()
            else:
                self.notify("heard nothing", severity="warning")
        else:
            try:
                self.voice.start()
            except Exception as exc:
                self.notify(f"microphone failed: {exc}", severity="error", timeout=8)
                return
            self._voice_note = self.voice.status.reason
            self._render_status()

    def _switch(self, target: str) -> None:
        if target in self._orch_views:
            self.active_orch = target
            self.selected = target
            self._switcher.current = f"chat-{target}"
            self._prompt.placeholder = f"Message {self._orch_names[target]}…"
        elif target in self.worker_items:
            self.selected = target
            self._switcher.current = "detail"
            self._render_detail(target, full=True)

    def _render_detail(self, worker_id: str, full: bool = False) -> None:
        worker = self.controller.dispatcher.workers.get(worker_id)
        if worker is None:
            return
        self._detail_header.update(self._worker_header(worker))
        if full:
            self._detail_log.clear()
            for line in worker.lines:
                self._detail_log.write(line)

    def _worker_origin(self, worker: Worker) -> str:
        name = self.controller.orchestrator_name_for(worker.orchestrator)
        if name:
            return name
        if worker.orchestrator:
            return worker.orchestrator
        return "unknown"

    def _worker_header(self, worker: Worker) -> str:
        color = STATUS_COLORS.get(worker.status, "#94a3b8")
        pill = f"[black on {color}] {worker.status} [/]"
        meta = (
            f"[dim]{escape(worker.agent)} · from {escape(self._worker_origin(worker))} · {worker.id} · "
            f"{worker.session_id or 'no session'} · {worker.elapsed():.1f}s · "
            f"${worker.cost:.4f} · {worker.tokens} tok[/]"
        )
        lines = [f"[b]{escape(worker.title)}[/]  {pill}", meta]
        if worker.detail:
            lines.append(f"[dim]{escape(worker.detail[:160])}[/]")
        if worker.status == "failed" and worker.error:
            lines.append(f"[#f87171]{escape(worker.error[:300])}[/]")
        return "\n".join(lines)

    def _origin_short(self, session_id: str) -> str:
        orch_id = self.controller.orchestrator_id_for(session_id)
        return self._orch_shorts.get(orch_id, "") if orch_id else ""

    def _worker_label(self, worker: Worker) -> str:
        color = STATUS_COLORS.get(worker.status, "#94a3b8")
        icon = SPINNER[self._spin] if worker.status == "running" else STATUS_ICONS.get(worker.status, "?")
        label = f"[{color}]{icon}[/] [b]{escape(worker.title)}[/]"
        if worker.status in ("running", "queued") and worker.detail:
            short = self._origin_short(worker.orchestrator)
            suffix = f" · {short}" if short else ""
            label += f"\n  [dim]{escape(worker.detail[:26])}{suffix}[/]"
        return label

    def _refresh_worker_item(self, worker: Worker) -> None:
        item = self.worker_items.get(worker.id)
        if item is not None:
            item.query_one(Static).update(self._worker_label(worker))

    def _render_topbar(self) -> None:
        home = Path.home()
        try:
            rel = self.workspace.relative_to(home)
            display = "~" if str(rel) == "." else f"~/{rel}"
        except ValueError:
            display = str(self.workspace)
        self._topbar_brand.update(f"[b #2dd4bf]◆ orchestra[/]  [dim]·[/]  [b]{escape(display)}[/]")
        self._topbar_model.update(f"[dim]model[/] [b]{escape(self.model or 'default')}[/] [dim]▾[/]")

    def _worker_summary(self) -> str:
        workers = list(self.controller.dispatcher.workers.values())
        if not workers:
            return "[dim]no workers yet[/]"
        active = sum(1 for worker in workers if worker.status in ("running", "queued"))
        done = sum(1 for worker in workers if worker.status == "done")
        failed = sum(1 for worker in workers if worker.status == "failed")
        bits = []
        if active:
            bits.append(f"[#38bdf8]{active} active[/]")
        if done:
            bits.append(f"[#4ade80]{done} done[/]")
        if failed:
            bits.append(f"[#f87171]{failed} failed[/]")
        return "[dim] · [/]".join(bits) + f" [dim]· {len(workers)} total[/]"

    def _render_status(self) -> None:
        state = self._orch_states.get(self.active_orch, "idle")
        if state == "thinking":
            indicator = f"[#fbbf24]{SPINNER[self._spin]}[/] [b #fbbf24]thinking[/]"
        elif state == "queued":
            indicator = "[#fbbf24]○[/] [#fbbf24]queued[/]"
        else:
            indicator = "[#4ade80]●[/] [dim]ready[/]"
        if self.active_orch:
            indicator += f" [dim]· {escape(self._orch_names.get(self.active_orch, ''))}[/]"
        self._status_state.update(indicator)
        self._status_info.update(self._worker_summary())
        if self.voice.recording:
            voice = "[#f87171]●[/] [b #f87171]recording[/] [dim]F2 to stop[/]"
        elif self._voice_note.startswith("transcribing"):
            voice = f"[#fbbf24]{SPINNER[self._spin]}[/] [dim]transcribing…[/]"
        elif self.voice.status.available:
            voice = "[#4ade80]●[/] [dim]voice[/]"
        else:
            voice = "[dim]voice off[/]"
        self._status_voice.update(voice)
        recording = self.voice.recording
        self._voice_button.label = "stop" if recording else "mic"
        self._voice_button.set_class(recording, "recording")

    def _tick(self) -> None:
        self._spin = (self._spin + 1) % len(SPINNER)
        self._render_status()
        for orch_id, state in self._orch_states.items():
            if state in ("thinking", "queued"):
                self._refresh_orch_item(orch_id)
        for worker in self.controller.dispatcher.workers.values():
            if worker.status in ("running", "queued"):
                self._refresh_worker_item(worker)

    def on_orchestrator_state(self, orch_id: str, state: str) -> None:
        self._orch_states[orch_id] = state
        self._refresh_orch_item(orch_id)
        if self.active_orch == orch_id:
            self._render_status()

    def on_orchestrator_event(self, orch_id: str, event: AgentEvent) -> None:
        view = self._orch_views.get(orch_id)
        if view is None:
            return
        widget, part = self._streams.get(orch_id, (None, None))
        turn = self._turn_texts.setdefault(orch_id, {})
        if event.kind == "text":
            key = event.part_id or "current"
            if event.part_id and widget is not None and part == event.part_id:
                widget.update(event.text)
            else:
                widget = view.add_assistant()
                self._streams[orch_id] = (widget, event.part_id or None)
                widget.update(event.text)
                turn.pop("current", None)
            turn[key] = event.text
        elif event.kind == "tool" and event.status == "running":
            if event.tool == "dispatch_task":
                view.add_notice(f"dispatching {event.title}")
            elif event.tool in ("check_tasks", "wait_tasks", "cancel_task"):
                view.add_notice(f"{event.tool} {event.title}".rstrip())
        elif event.kind in ("error", "stderr") and (event.error or event.text):
            view.add_notice(f"orchestrator: {(event.error or event.text)[:300]}")

    def on_orchestrator_done(self, orch_id: str, result: ProcessResult) -> None:
        view = self._orch_views.get(orch_id)
        if view is not None:
            if result.cancelled:
                view.add_notice("orchestrator turn cancelled")
            elif result.exit_code != 0:
                tail = result.stderr.strip().splitlines()
                view.add_notice(f"orchestrator exited with {result.exit_code}: {(tail[-1] if tail else '')[:300]}")
                if "not found" in result.stderr.lower() and "session" in result.stderr.lower():
                    orchestrator = self.controller.orchestrators.get(orch_id)
                    if orchestrator is not None and orchestrator.session_id:
                        orchestrator.session_id = None
                        view.add_notice("previous session could not be resumed; a fresh one will start next turn")
        turn = self._turn_texts.pop(orch_id, {})
        answer = "\n\n".join(text.strip() for text in turn.values() if text.strip())
        if answer and not result.cancelled:
            append_transcript(orch_id, {"type": "assistant", "text": answer})
        self._turn_texts[orch_id] = {}
        self._streams[orch_id] = (None, None)
        self._save_state()
        self.on_orchestrator_state(orch_id, "idle")

    def on_worker_added(self, worker: Worker) -> None:
        item = ListItem(Static(self._worker_label(worker), markup=True), id=worker.id)
        self.worker_items[worker.id] = item
        self._agents.append(item)
        origin = self.controller.orchestrator_name_for(worker.orchestrator)
        prefix = f"{origin}: " if origin else ""
        self.notify(f"{prefix}{worker.title}", timeout=4)

    def on_worker_events(self, worker: Worker, lines: list[str]) -> None:
        if self.selected == worker.id:
            for line in lines:
                self._detail_log.write(line)

    def on_worker_updated(self, worker: Worker) -> None:
        self._refresh_worker_item(worker)
        if self.selected == worker.id:
            self._detail_header.update(self._worker_header(worker))

    def on_worker_finished(self, worker: Worker) -> None:
        workers = self.controller.dispatcher.workers.values()
        if workers and all(item.status in TERMINAL for item in workers):
            self.notify("all dispatched work has finished", timeout=5)

    def on_notice(self, text: str) -> None:
        if self.active_orch:
            self._chat_for(self.active_orch).add_notice(text)

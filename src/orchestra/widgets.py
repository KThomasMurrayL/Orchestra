from __future__ import annotations

import asyncio

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from .keys import NEW_ORCH_KEY
from .models import usable_models

HERO_TAIL = (
    "[dim]Describe what you want done. The orchestrator[/]\n"
    "[dim]plans it and dispatches real worker agents.[/]\n"
    "[dim]Click one in the sidebar to watch its output.[/]\n"
    f"[dim]Press [/][b #f59e0b]F2[/][dim] to talk, [/][b #f59e0b]{NEW_ORCH_KEY}[/]"
    "[dim] or [/][b #f59e0b]+ new[/][dim] for another orchestrator.[/]"
)


class ModelBadge(Static):
    def on_click(self, event) -> None:
        self.app.push_model_picker()


class ChatView(VerticalScroll):
    def __init__(self, *children, hero_name: str | None = "orchestra", **kwargs):
        super().__init__(*children, **kwargs)
        self.hero_name = hero_name

    def on_mount(self) -> None:
        if self.hero_name:
            self.add_hero(self.hero_name)

    def add_hero(self, name: str = "orchestra") -> None:
        self.mount(Static(f"[b #2dd4bf]◆ {escape(name)}[/]\n" + HERO_TAIL, classes="hero", markup=True))
        self._scroll_end()

    def add_user(self, text: str) -> None:
        self.mount(Static(f"[b #2dd4bf]you[/] [dim]›[/] {escape(text)}", classes="msg user", markup=True))
        self._scroll_end()

    def add_notice(self, text: str) -> None:
        self.mount(Static(f"[dim]· {escape(text)}[/]", classes="msg notice", markup=True))
        self._scroll_end()

    def add_assistant(self) -> Markdown:
        widget = Markdown("", classes="msg assistant")
        self.mount(widget)
        self._scroll_end()
        return widget

    def _scroll_end(self) -> None:
        self.call_after_refresh(self.scroll_end, animate=False)


class ModelPicker(ModalScreen[str | None]):
    CSS = """
    ModelPicker {
        align: center middle;
        background: $background 60%;
    }
    #picker {
        width: 72;
        max-height: 90%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #picker-title { text-style: bold; color: $primary; }
    #picker-filter { border: round $accent 50%; margin: 1 0 0 0; }
    #picker-note { color: $text-muted; height: auto; margin: 0 0 1 0; }
    #picker-list { height: auto; max-height: 14; background: transparent; }
    #picker-hint { color: $text-muted; margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "close_picker", "close", show=False)]

    def __init__(self, current: str | None, models: list[str] | None = None, note: str = ""):
        super().__init__()
        self.current = current
        self._models = models
        self._note = note

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static("Select model", id="picker-title")
            yield Input(placeholder="type to filter…", id="picker-filter")
            yield Static("", id="picker-note")
            yield OptionList(id="picker-list")
            yield Static("[dim]enter select · esc close[/]", id="picker-hint", markup=True)

    async def on_mount(self) -> None:
        self.query_one("#picker-filter", Input).focus()
        if self._models is None:
            self._populate("")
            usable, hidden = await asyncio.to_thread(usable_models)
            self._models = usable
            if hidden and not self._note:
                self._note = f"{hidden} Zen free model(s) hidden — they cannot run as spawned workers."
        self._populate(self.query_one("#picker-filter", Input).value)

    def _populate(self, query: str) -> None:
        note_widget = self.query_one("#picker-note", Static)
        option_list = self.query_one("#picker-list", OptionList)
        if self._models is None:
            note_widget.update("[dim]loading models…[/]")
            option_list.clear_options()
            return
        models = self._models
        note = self._note
        if not models:
            note = "no models available — authenticate a provider in opencode first"
        note_widget.update(f"[dim]{escape(note)}[/]" if note else "")
        matches = [model for model in models if query.lower() in model.lower()]
        option_list.clear_options()
        if not matches:
            option_list.add_options([Option(Text("no models match", style="dim"), disabled=True)])
            return
        options = []
        for model in matches:
            if model == self.current:
                options.append(Option(Text.assemble(("● ", "bold #2dd4bf"), (model, "bold")), id=model))
            else:
                options.append(Option(Text(model, style="dim"), id=model))
        option_list.add_options(options)
        option_list.highlighted = matches.index(self.current) if self.current in matches else 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        option_list = self.query_one("#picker-list", OptionList)
        if option_list.option_count:
            option_list.action_select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.dismiss(event.option.id)

    def action_close_picker(self) -> None:
        self.dismiss(None)


class NameDialog(ModalScreen[str | None]):
    CSS = """
    NameDialog { align: center middle; background: $background 60%; }
    #name-box {
        width: 56;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #name-title { text-style: bold; color: $primary; }
    #name-input { border: round $accent 50%; margin: 1 0 0 0; }
    #name-hint { color: $text-muted; margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "cancel", show=False)]

    def __init__(self, default: str):
        super().__init__()
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="name-box"):
            yield Static("Name this orchestrator", id="name-title")
            yield Input(value=self.default, id="name-input")
            yield Static("[dim]enter create · esc cancel[/]", id="name-hint", markup=True)

    def on_mount(self) -> None:
        field = self.query_one("#name-input", Input)
        field.focus()
        field.cursor_position = len(field.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or self.default)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmQuit(ModalScreen[bool]):
    CSS = """
    ConfirmQuit { align: center middle; background: $background 60%; }
    #confirm-box {
        width: 54;
        border: round $error;
        background: $surface;
        padding: 1 2;
    }
    #confirm-title { text-style: bold; color: $error; }
    #confirm-body { margin: 1 0; color: $text; }
    #confirm-buttons { height: auto; align-horizontal: right; }
    #confirm-buttons Button {
        height: 1;
        min-width: 0;
        border: none;
        padding: 0 1;
        margin-left: 1;
    }
    #confirm-yes { background: $error; color: black; }
    #confirm-yes:hover { background: $error 80%; }
    #confirm-no { background: $boost; color: $text; }
    #confirm-no:hover { background: $primary 30%; }
    #confirm-hint { color: $text-muted; margin-top: 1; }
    """
    BINDINGS = [Binding("escape", "stay", "stay", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Static("Close orchestra?", id="confirm-title")
            yield Static(
                "Running workers will be terminated. Named orchestrators and their chat history are saved and will be waiting next time.",
                id="confirm-body",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Stay", id="confirm-no")
                yield Button("Close", id="confirm-yes")
            yield Static("[dim]enter activates the focused button · esc stays[/]", id="confirm-hint", markup=True)

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_stay(self) -> None:
        self.dismiss(False)

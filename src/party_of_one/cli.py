"""Textual TUI for Party of One — dark fantasy RPG."""

from __future__ import annotations

import sys

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from party_of_one.agents.companion import load_companion_profiles
from party_of_one.config import load_config, AppConfig
from party_of_one.models import CharacterStatus, QuestStatus
from party_of_one.orchestrator import Orchestrator


# ── Theme CSS ──────────────────────────────────────────────────────────────

THEME_CSS = """
Screen {
    background: #1a1a2e;
}

Header {
    background: #16213e;
    color: #e2b714;
}

Footer {
    background: #16213e;
}

/* ── Setup ── */

#setup-container {
    align: center middle;
    width: 90%;
    height: auto;
    max-height: 90%;
    border: double #e2b714;
    background: #16213e;
    padding: 2 3;
}

#setup-title {
    text-align: center;
    text-style: bold;
    color: #e2b714;
    margin-bottom: 1;
}

#setup-subtitle {
    text-align: center;
    color: #a0a0b0;
    margin-bottom: 1;
}

ListView {
    height: auto;
    max-height: 22;
    background: #1a1a2e;
    border: round #3a3a5e;
}

ListView > ListItem {
    padding: 0 2;
    color: #c0c0d0;
}

ListView > ListItem.--highlight {
    background: #e2b714 20%;
    color: #ffffff;
}

#setup-input {
    margin-top: 1;
    border: round #3a3a5e;
    background: #1a1a2e;
}

/* ── Game ── */

#game-area {
    height: 1fr;
}

#narrative {
    width: 3fr;
    background: #0f0f23;
    padding: 1 2;
    scrollbar-size: 1 1;
    scrollbar-color: #3a3a5e;
    scrollbar-color-hover: #e2b714;
}

#sidebar {
    width: 1fr;
    min-width: 30;
    max-width: 40;
    padding: 1 2;
    background: #16213e;
    border-left: solid #3a3a5e;
}

#action-bar {
    dock: bottom;
    height: 5;
    background: #16213e;
    border-top: double #e2b714;
    padding: 0 2 1 2;
}

#action-input {
    width: 100%;
    height: 3;
    background: #1a1a2e;
    border: round #3a3a5e;
    color: #e0e0e0;
    margin: 0;
}

#action-input:focus {
    border: round #e2b714;
}

#action-input.-disabled {
    opacity: 0.4;
}
"""


# ── Setup screens ──────────────────────────────────────────────────────────


class SelectionScreen(Screen):
    """Arrow-key selection screen."""

    def __init__(self, title: str, subtitle: str, items: list[str],
                 multi: int = 1):
        super().__init__()
        self.sel_title = title
        self.sel_subtitle = subtitle
        self.items = items
        self.multi = multi
        self._selected: list[int] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-container"):
            yield Label(self.sel_title, id="setup-title")
            yield Label(self.sel_subtitle, id="setup-subtitle")
            yield ListView(
                *[ListItem(Label(f"   {item}")) for item in self.items],
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None:
            return

        if self.multi == 1:
            self.dismiss(result=[idx])
        else:
            if idx in self._selected:
                self._selected.remove(idx)
            else:
                self._selected.append(idx)

            for i, item in enumerate(event.list_view.children):
                label = item.query_one(Label)
                mark = " ✦ " if i in self._selected else "   "
                label.update(f"{mark}{self.items[i]}")

            if len(self._selected) >= self.multi:
                self.dismiss(result=list(self._selected))
            else:
                remaining = self.multi - len(self._selected)
                names = [self.items[i].split("(")[0].strip() for i in self._selected]
                self.query_one("#setup-subtitle", Label).update(
                    f"✦ {', '.join(names)}  — выберите ещё {remaining}"
                )


class TextInputScreen(Screen):
    """Text input screen."""

    def __init__(self, title: str, subtitle: str, placeholder: str, default: str = ""):
        super().__init__()
        self.inp_title = title
        self.inp_subtitle = subtitle
        self.placeholder = placeholder
        self.default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-container"):
            yield Label(self.inp_title, id="setup-title")
            yield Label(self.inp_subtitle, id="setup-subtitle")
            yield Input(placeholder=self.placeholder, id="setup-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(result=event.value.strip() or self.default)


# ── Sidebar ────────────────────────────────────────────────────────────────


class PartySidebar(Static):
    """Party stats + quests sidebar."""

    def update_party(self, orch: Orchestrator) -> None:
        players = orch.db.characters.list(role="player")
        companions = orch.db.characters.list(role="companion")
        party = players + companions

        parts = ["[bold #e2b714]━━━ Партия ━━━[/bold #e2b714]\n"]

        for c in party:
            hp_ratio = c.hp / c.max_hp if c.max_hp > 0 else 0
            if c.status == CharacterStatus.DEAD:
                name_style = "dim strike"
                hp_style = "dim"
            elif hp_ratio <= 0.25:
                name_style = "bold red"
                hp_style = "red"
            elif hp_ratio <= 0.5:
                name_style = "yellow"
                hp_style = "yellow"
            else:
                name_style = "bold #c0c0d0"
                hp_style = "green"

            role_icon = "⚔" if c.role.value == "player" else "🛡"
            status = f" [italic dim]({c.status.value})[/italic dim]" if c.status != CharacterStatus.ALIVE else ""

            parts.append(
                f"[{name_style}]{role_icon} {c.name}{status}[/{name_style}]\n"
                f"  [{hp_style}]♥ {c.hp}/{c.max_hp}[/{hp_style}]  "
                f"[dim]⛊ {c.armor}[/dim]\n"
                f"  [dim]СИЛ[/dim] {c.strength}  "
                f"[dim]ЛОВ[/dim] {c.dexterity}  "
                f"[dim]ВОЛ[/dim] {c.willpower}\n"
                f"  [dim]Зол[/dim] {c.gold}"
            )
            if c.inventory:
                inv = ", ".join(i.name for i in c.inventory[:3])
                if len(c.inventory) > 3:
                    inv += f" [dim](+{len(c.inventory) - 3})[/dim]"
                parts.append(f"  [italic dim]{inv}[/italic dim]")
            parts.append("")

        quests = orch.db.quests.get_all()
        active = [q for q in quests if q.status == QuestStatus.ACTIVE]
        done = [q for q in quests if q.status != QuestStatus.ACTIVE]
        if active or done:
            parts.append("[bold #e2b714]━━━ Квесты ━━━[/bold #e2b714]\n")
            for q in active:
                parts.append(f"  [green]▸[/green] {q.title}")
            for q in done:
                parts.append(f"  [dim]✓ {q.title}[/dim]")

        self.update("\n".join(parts))


# ── Game App ───────────────────────────────────────────────────────────────


class GameApp(App):
    """Main TUI application."""

    CSS = THEME_CSS

    BINDINGS = [
        Binding("ctrl+q", "quit_game", "Выход"),
        Binding("ctrl+s", "save_game", "Сохранить"),
    ]

    def __init__(self, config: AppConfig, watch_mode: bool = False, watch_rounds: int = 30):
        super().__init__()
        self.config = config
        self.watch_mode = watch_mode
        self.watch_rounds = watch_rounds
        self.orchestrator: Orchestrator | None = None
        self._profiles = load_companion_profiles(config.game.companion_profiles_path)
        self._archetypes = ["Воин", "Следопыт", "Маг", "Плут"]
        self._selected_archetype = ""
        self._selected_companions: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="game-area"):
            yield RichLog(id="narrative", wrap=True, markup=True)
            yield PartySidebar(id="sidebar")
        with Horizontal(id="action-bar"):
            yield Input(
                placeholder="Ожидание...",
                id="action-input",
                disabled=True,
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "⚔ Party of One"
        self.sub_title = "Cairn RPG"
        # Suppress structlog stderr output in TUI mode
        self._suppress_stderr()
        self._begin_setup()

    def _suppress_stderr(self) -> None:
        """Redirect structlog stderr to devnull so it doesn't pollute TUI."""
        import os
        devnull = open(os.devnull, "w")
        sys.stderr = devnull

    # ── Setup flow ─────────────────────────────────────────────────────

    def _begin_setup(self) -> None:
        self.push_screen(
            SelectionScreen(
                "⚔ Party of One ⚔",
                "Выберите архетип героя  (↑↓ Enter)",
                self._archetypes,
                multi=1,
            ),
            callback=self._on_archetype_selected,
        )

    def _on_archetype_selected(self, result: list[int]) -> None:
        self._selected_archetype = self._archetypes[result[0]]
        log = self.query_one("#narrative", RichLog)
        log.write(f"[#e2b714]⚔ Архетип:[/#e2b714] [bold]{self._selected_archetype}[/bold]\n")

        items = [
            f"{p.name} ({p.class_}) — {p.personality.traits[0]}"
            for p in self._profiles
        ]
        self.push_screen(
            SelectionScreen(
                "⚔ Party of One ⚔",
                "Выберите двух спутников  (Enter — выбрать)",
                items,
                multi=2,
            ),
            callback=self._on_companions_selected,
        )

    def _on_companions_selected(self, result: list[int]) -> None:
        self._selected_companions = [self._profiles[i].name for i in result]
        log = self.query_one("#narrative", RichLog)
        log.write(
            f"[#e2b714]🛡 Спутники:[/#e2b714] [bold]{', '.join(self._selected_companions)}[/bold]\n"
        )

        self.push_screen(
            TextInputScreen(
                "⚔ Party of One ⚔",
                "Опишите мир вашего приключения",
                placeholder="Тёмный лес, заброшенный замок, степные кочевники...",
                default="Мрачное средневековое фэнтези",
            ),
            callback=self._on_setting_entered,
        )

    def _on_setting_entered(self, result: str) -> None:
        log = self.query_one("#narrative", RichLog)
        log.write(f"[#e2b714]🌍 Мир:[/#e2b714] [italic]{result}[/italic]\n")
        log.write("[dim]⏳ Мастер подземелий готовит сцену...[/dim]\n")
        self._start_game(result)

    # ── Game ───────────────────────────────────────────────────────────

    @work(thread=True)
    def _start_game(self, setting: str) -> None:
        from party_of_one.logger import setup_logging
        setup_logging(log_file=self.config.logging.file, level=self.config.logging.level)

        self.orchestrator = Orchestrator(self.config)
        dm_response = self.orchestrator.init_game(
            player_name="Герой",
            player_archetype=self._selected_archetype,
            companion_choices=self._selected_companions,
            setting_description=setting,
        )
        self.call_from_thread(self._display_init, dm_response.narrative)

    def _display_init(self, narrative: str) -> None:
        log = self.query_one("#narrative", RichLog)
        log.write("")
        log.write("[bold #e2b714]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #e2b714]")
        log.write(f"\n[bold italic #d4a017]☠ Мастер Подземелий[/bold italic #d4a017]\n")
        log.write(f"[#c0c0d0]{narrative}[/#c0c0d0]\n")
        log.write("[bold #e2b714]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold #e2b714]")

        self.query_one("#sidebar", PartySidebar).update_party(self.orchestrator)

        # Show llm_call info in narrative
        log.write("\n[dim italic]⚙ Сцена создана[/dim italic]\n")

        inp = self.query_one("#action-input", Input)
        inp.disabled = False
        inp.placeholder = "⚔ Что вы делаете? (/help — команды)"
        inp.focus()
        self.sub_title = f"Раунд 1"

        if self.watch_mode:
            self._run_watch_mode()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "action-input":
            return
        value = event.value.strip()
        event.input.clear()
        if not value:
            return

        if value.startswith("/"):
            self._handle_command(value)
        else:
            self._process_round(value)

    def _handle_command(self, cmd: str) -> None:
        log = self.query_one("#narrative", RichLog)
        if cmd in ("/quit", "/q"):
            log.write("\n[dim italic]Сохранено. Да хранят вас боги, путник.[/dim italic]")
            if self.orchestrator:
                self.orchestrator.db.close()
            self.exit()
        elif cmd == "/save":
            log.write("[dim italic]⚙ Сессия сохранена.[/dim italic]")
        elif cmd == "/status":
            if self.orchestrator:
                log.write(f"\n[dim]{self.orchestrator.db.snapshot()}[/dim]")
        elif cmd == "/help":
            log.write(
                "\n[bold #e2b714]━━━ Команды ━━━[/bold #e2b714]\n"
                "  [bold #c0c0d0]/help[/bold #c0c0d0]   — [dim]эта справка[/dim]\n"
                "  [bold #c0c0d0]/status[/bold #c0c0d0] — [dim]состояние мира[/dim]\n"
                "  [bold #c0c0d0]/save[/bold #c0c0d0]   — [dim]сохранить[/dim]\n"
                "  [bold #c0c0d0]/quit[/bold #c0c0d0]   — [dim]сохранить и выйти[/dim]\n"
                "  [bold #c0c0d0]Ctrl+Q[/bold #c0c0d0]  — [dim]быстрый выход[/dim]\n"
            )
        else:
            log.write(f"[dim italic]Неведомая команда: {cmd}[/dim italic]")

    @work(thread=True)
    def _process_round(self, action: str) -> None:
        inp = self.query_one("#action-input", Input)
        self.call_from_thread(setattr, inp, "disabled", True)

        log_id = "#narrative"
        self.call_from_thread(
            self.query_one(log_id, RichLog).write,
            f"\n[bold #5b9bd5]▸ Вы:[/bold #5b9bd5] [italic #a0c4e8]{action}[/italic #a0c4e8]\n",
        )
        self.call_from_thread(
            self.query_one(log_id, RichLog).write,
            "[dim italic]⏳ Мастер размышляет...[/dim italic]",
        )

        result = self.orchestrator.process_round(action)

        companion_names = {
            "companion_a": self._selected_companions[0] if len(self._selected_companions) > 0 else "Спутник",
            "companion_b": self._selected_companions[1] if len(self._selected_companions) > 1 else "Спутник",
        }

        for actor_role, dm_resp in zip(result.actor_roles, result.dm_responses):
            role_val = actor_role.value

            # Companion speech
            if role_val in result.companion_texts:
                name = companion_names.get(role_val, role_val)
                self.call_from_thread(
                    self.query_one("#narrative", RichLog).write,
                    f"\n[bold #c77dff]🛡 {name}:[/bold #c77dff] "
                    f"[italic #d4a0ff]{result.companion_texts[role_val]}[/italic #d4a0ff]",
                )

            # DM narrative
            if role_val == "player":
                self.call_from_thread(
                    self.query_one("#narrative", RichLog).write,
                    f"\n[bold #d4a017]☠ Мастер:[/bold #d4a017]\n"
                    f"[#c0c0d0]{dm_resp.narrative}[/#c0c0d0]\n",
                )
            else:
                name = companion_names.get(role_val, role_val)
                self.call_from_thread(
                    self.query_one("#narrative", RichLog).write,
                    f"\n[bold #d4a017]☠ Мастер[/bold #d4a017] [dim]→ {name}[/dim][bold #d4a017]:[/bold #d4a017]\n"
                    f"[#c0c0d0]{dm_resp.narrative}[/#c0c0d0]\n",
                )

        # Tool calls — show real calls
        for dm_resp in result.dm_responses:
            for tc in dm_resp.tool_calls:
                name = tc.get("name", "?")
                args = tc.get("args", {})
                args_short = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
                self.call_from_thread(
                    self.query_one("#narrative", RichLog).write,
                    f"[dim]⚙ {name}({args_short})[/dim]",
                )

        self.call_from_thread(
            self.query_one("#sidebar", PartySidebar).update_party,
            self.orchestrator,
        )
        self.call_from_thread(
            setattr, self, "sub_title",
            f"Раунд {self.orchestrator.round_number}",
        )

        if result.session_ended:
            self.call_from_thread(
                self.query_one("#narrative", RichLog).write,
                f"\n[bold red]╔══════════════════════════════╗\n"
                f"║     КОНЕЦ ПРИКЛЮЧЕНИЯ        ║\n"
                f"║     {result.end_reason or ''}                      ║\n"
                f"╚══════════════════════════════╝[/bold red]",
            )
            self.call_from_thread(setattr, inp, "placeholder", "Приключение окончено.")
        else:
            self.call_from_thread(setattr, inp, "disabled", False)
            self.call_from_thread(setattr, inp, "placeholder", "⚔ Что вы делаете?")
            self.call_from_thread(inp.focus)

    @work(thread=True)
    def _run_watch_mode(self) -> None:
        for i in range(self.watch_rounds):
            if self.orchestrator.is_ended:
                break
            self.call_from_thread(
                self.query_one("#narrative", RichLog).write,
                f"\n[dim]── Раунд {i + 1}/{self.watch_rounds} ──[/dim]",
            )
            result = self.orchestrator.process_round("наблюдает")
            for dm_resp in result.dm_responses:
                self.call_from_thread(
                    self.query_one("#narrative", RichLog).write,
                    f"\n[#c0c0d0]{dm_resp.narrative}[/#c0c0d0]",
                )
            self.call_from_thread(
                self.query_one("#sidebar", PartySidebar).update_party,
                self.orchestrator,
            )
            self.call_from_thread(
                setattr, self, "sub_title",
                f"Watch: {i + 1}/{self.watch_rounds}",
            )
            if result.session_ended:
                break
        self.call_from_thread(
            self.query_one("#narrative", RichLog).write,
            "\n[bold #e2b714]Watch mode завершён.[/bold #e2b714]",
        )

    def action_quit_game(self) -> None:
        if self.orchestrator:
            self.orchestrator.db.close()
        self.exit()

    def action_save_game(self) -> None:
        self.query_one("#narrative", RichLog).write("[dim italic]⚙ Сохранено.[/dim italic]")


def run_tui(watch: bool = False, rounds: int = 30):
    config = load_config()
    app = GameApp(config, watch_mode=watch, watch_rounds=rounds)
    app.run()

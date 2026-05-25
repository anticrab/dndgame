"""LevelUpScreen — модальный экран level-up в середине боя (этап R1).

Показывается по событию ``LevelUpReady`` (PROGRESSION.md §4). Три выбора:
* «Сейчас!» (Enter/n) — применить повышение немедленно (``on_now``);
* «После боя» (l) — отложить до конца encounter (``on_later``);
* «Подробнее» (d) — показать, что даёт уровень (toggle, без закрытия).

Драматический эффект: +HP при низком HP может «воскресить» PC посреди боя.
Применение уровня — снаружи (LevelUpService), экран лишь UI-выбор.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from dnd.application.dto.engine_event import LevelUpReady


class LevelUpScreen(ModalScreen[None]):
    """Оверлей «Вы достигли уровня N!» с выбором момента прокачки."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("enter", "now", "Now"),
        ("n", "now", "Now"),
        ("l", "later", "Later"),
        ("d", "details", "Details"),
    ]

    def __init__(
        self,
        event: LevelUpReady,
        *,
        on_now: Callable[[], None],
        on_later: Callable[[], None],
        details: str = "",
    ) -> None:
        super().__init__()
        self._event = event
        self._on_now = on_now
        self._on_later = on_later
        self._details = details
        self._details_shown = False

    def compose(self) -> ComposeResult:
        ev = self._event
        with Vertical(classes="modal-box"):
            yield Label(
                f"LEVEL UP: {ev.actor_id} — уровень {ev.to_level}!",
                classes="modal-title",
            )
            yield Label(f"(с уровня {ev.from_level} → {ev.to_level})")
            yield Label("")
            yield Label("[Enter/n] Сейчас!   [l] После боя   [d] Подробнее")
            yield Label("", id="level-up-details")

    def action_now(self) -> None:
        self._on_now()
        self.dismiss(None)

    def action_later(self) -> None:
        self._on_later()
        self.dismiss(None)

    def action_details(self) -> None:
        # Toggle блока подробностей; экран НЕ закрывается.
        self._details_shown = not self._details_shown
        label = self.query_one("#level-up-details", Label)
        label.update(self._details if self._details_shown else "")


__all__ = ["LevelUpScreen"]

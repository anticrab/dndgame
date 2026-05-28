"""PlayerItemsScreen — модальный экран собственного инвентаря PC (U5-1).

Не путать с :class:`InventoryScreen` — тот lootает сундук. Этот показывает
**используемые** (``item.use is not None``) предметы из инвентаря актора, и
по Enter возвращает выбранный ``ItemId`` в :class:`BattleScreen`, который дальше:

* для SELF-эффекта формирует ``UseItemIntent`` сразу;
* для SINGLE/AREA/MULTI — заходит в соответствующий ``BattleMode`` (TARGET/
  AREA/MULTI_TARGET), как у заклинаний.

UI повторяет стиль ``InventoryScreen`` (общий «list-of-stacks»): один экран
без скролла, стрелки/Tab — курсор, Enter — выбор, Esc/Q — отмена.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.screen import ModalScreen
from textual.widgets import Static

from dnd.domain.values.item import ItemId

if TYPE_CHECKING:
    from dnd.domain.entities.inventory import Inventory


class PlayerItemsScreen(ModalScreen[ItemId | None]):
    """Список используемых предметов PC — выбор для применения."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("up", "cursor_up", "▲"),
        ("down", "cursor_down", "▼"),
        ("tab", "cursor_down", "Tab"),
        ("shift+tab", "cursor_up", "Shift+Tab"),
        ("enter", "confirm", "Use"),
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Close"),
    ]

    def __init__(self, inventory: Inventory) -> None:
        super().__init__()
        # Фильтрация по ``use``: не-используемые (gold, оружие, броня, квестовые)
        # сюда не попадают — у них нечего применять.
        self._stacks = [s for s in inventory.stacks if s.item.use is not None]
        self._idx = 0

    @property
    def has_items(self) -> bool:
        """Используется BattleScreen для решения, открывать ли экран."""
        return bool(self._stacks)

    def compose(self) -> ComposeResult:
        yield Static(self._render_body(), id="player-items-body", markup=True, classes="modal-box")

    def _render_body(self) -> str:
        if not self._stacks:
            return "[bold]Inventory[/]\n\n[dim]Нет используемых предметов.[/]\n\n[dim]Esc — закрыть.[/]"
        lines = ["[bold]Use item[/]", ""]
        for i, stack in enumerate(self._stacks):
            marker = "▶" if i == self._idx else " "
            qty = f" ×{stack.qty}" if stack.qty > 1 else ""
            assert stack.item.use is not None  # отфильтровано выше
            kind = "📜" if stack.item.use.is_scroll else "🧪"
            econ = stack.item.use.economy.replace("_", " ")
            line = f"{marker} {kind} {stack.item.name}{qty} [dim]({econ})[/]"
            if i == self._idx:
                line = f"[reverse]{line}[/]"
            lines.append(line)
        lines.append("")
        lines.append("[dim]↑↓ — выбор · Enter — использовать · Esc/Q — отмена[/]")
        return "\n".join(lines)

    def _refresh(self) -> None:
        self.query_one("#player-items-body", Static).update(self._render_body())

    # --- actions --------------------------------------------------------

    def action_cursor_up(self) -> None:
        if not self._stacks:
            return
        self._idx = (self._idx - 1) % len(self._stacks)
        self._refresh()

    def action_cursor_down(self) -> None:
        if not self._stacks:
            return
        self._idx = (self._idx + 1) % len(self._stacks)
        self._refresh()

    def action_confirm(self) -> None:
        if not self._stacks:
            self.dismiss(None)
            return
        self.dismiss(self._stacks[self._idx].item.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["PlayerItemsScreen"]

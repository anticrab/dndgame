"""InventoryScreen — модальный экран лута сундука (O-9).

Открывается hotkey'ем 'l' в BattleScreen, если в reach есть открытый
chest. Показывает его содержимое (через item_repository → красивые
имена); стрелки/Tab перемещают курсор, Enter подтверждает выбор
(qty = весь стак — для UI MVP), Esc/Q закрывают.

После Enter handler возвращает в BattleScreen через ``dismiss``
выбранный ``(ObjectId, ItemId)``; BattleScreen формирует PickupIntent.
``dismiss(None)`` означает «закрыто без выбора» (Esc / Q / пустой
сундук).

Drop / Equip / Unequip пока не реализованы — это отдельные сторонки UI
в составе R (level-up) / отдельного character-screen'а.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.screen import ModalScreen
from textual.widgets import Static

from dnd.application.dto.ids import ObjectId
from dnd.application.inventory.loot_helpers import parse_loot
from dnd.application.ports.item_repository import ItemRepository
from dnd.domain.values.item import ItemId

if TYPE_CHECKING:
    from dnd.domain.entities.interactable import InteractableObject


class InventoryScreen(ModalScreen[tuple[ObjectId, ItemId] | None]):
    """Простой list-of-stacks UI выбора предмета для Pickup.

    На MVP — одностраничный без скролла: для крипты сундука с 1-3
    items этого достаточно. Когда контента станет больше — заменим
    на DataTable от Textual с пагинацией.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("up", "cursor_up", "▲"),
        ("down", "cursor_down", "▼"),
        ("tab", "cursor_down", "Tab"),
        ("shift+tab", "cursor_up", "Shift+Tab"),
        ("enter", "confirm", "Take"),
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Close"),
    ]

    def __init__(
        self,
        chest: InteractableObject,
        item_repository: ItemRepository,
    ) -> None:
        super().__init__()
        self._chest = chest
        self._items = item_repository
        self._stacks = parse_loot(chest.state.get("contents"), item_repository)
        self._idx = 0

    def compose(self) -> ComposeResult:
        yield Static(self._render_body(), id="inv-body", markup=True, classes="modal-box")

    def _render_body(self) -> str:
        # Empty case — короткое сообщение + Esc to close.
        if not self._stacks:
            return (
                f"[bold]{self._chest.id}[/]\n\n"
                "[dim]Сундук пуст.[/]\n\n"
                "[dim]Esc — закрыть.[/]"
            )
        lines = [f"[bold]{self._chest.id}[/]", ""]
        for i, stack in enumerate(self._stacks):
            marker = "▶" if i == self._idx else " "
            qty = f" ×{stack.qty}" if stack.qty > 1 else ""
            weight = (
                f" [dim]({stack.total_weight_lb:.1f} lb)[/]"
                if stack.total_weight_lb else ""
            )
            line = f"{marker} {stack.item.name}{qty}{weight}"
            if i == self._idx:
                line = f"[reverse]{line}[/]"
            lines.append(line)
        lines.append("")
        lines.append(
            "[dim]↑↓ — выбор · Enter — взять весь стак · "
            "Esc/Q — закрыть[/]"
        )
        return "\n".join(lines)

    def _refresh(self) -> None:
        self.query_one("#inv-body", Static).update(self._render_body())

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
        chosen = self._stacks[self._idx]
        self.dismiss((ObjectId(str(self._chest.id)), chosen.item.id))

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["InventoryScreen"]

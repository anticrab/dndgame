"""InitiativeWidget — очередь инициативы.

См. ``docs/TUI.md`` §6.4 и mockup A.1 (INITIATIVE panel).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from dnd.application.dto.ids import CreatureId
    from dnd.application.dto.initiative import InitiativeEntry
    from dnd.domain.entities.creature import Creature


def format_initiative(
    order: Sequence[InitiativeEntry],
    participants: dict[CreatureId, Creature],
    *,
    active_id: CreatureId | None = None,
) -> str:
    """Многострочный листинг очереди.

    Маркеры:
      * ``▶`` — текущий актор;
      * ``✗`` — труп (is_alive=False);
      * ``-`` — обычная строка.
    """
    lines: list[str] = []
    for idx, entry in enumerate(order, start=1):
        creature = participants.get(entry.creature_id)
        if creature is None:
            marker = "?"
            name = str(entry.creature_id)
        elif not creature.is_alive:
            marker = "✗"
            name = creature.name
        elif entry.creature_id == active_id:
            marker = "▶"
            name = creature.name
        else:
            marker = "-"
            name = creature.name
        lines.append(f"{idx} {marker} {name:<12} {entry.total:>3}")
    return "\n".join(lines)


class InitiativeWidget(Static):
    DEFAULT_CSS = ""

    def refresh_from(
        self,
        order: Sequence[InitiativeEntry],
        participants: dict[CreatureId, Creature],
        *,
        active_id: CreatureId | None = None,
    ) -> None:
        self.update(format_initiative(order, participants, active_id=active_id))


__all__ = ["InitiativeWidget", "format_initiative"]

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
    """Многострочный листинг очереди (Rich-markup).

    Маркеры:
      * ``▶`` — текущий актор;
      * ``✗`` — труп (is_alive=False), название перечёркнуто и dim'ом;
      * ``-`` — обычная строка.

    Раньше мёртвых выделял только маленький символ ``✗``, который терялся
    среди ``-`` (UX-репорт «убил, но он жив»). Теперь:
    * маркер ``✗`` в красном,
    * имя перечёркнуто + затемнено,
    * суффикс ``DEAD`` яркий и сразу читается как «выбыл из боя».
    """
    lines: list[str] = []
    for idx, entry in enumerate(order, start=1):
        creature = participants.get(entry.creature_id)
        if creature is None:
            lines.append(f"{idx} ? {entry.creature_id!s:<12} {entry.total:>3}")
            continue
        name = creature.name
        if not creature.is_alive:
            lines.append(
                f"{idx} [red]✗[/] "
                f"[dim strike]{name:<12}[/] "
                f"[red bold]DEAD[/] "
                f"{entry.total:>3}"
            )
            continue
        marker = "▶" if entry.creature_id == active_id else "-"
        hp = creature.hit_points
        # N-2: показываем hp/max — на глаз сразу видно, кто
        # критически ранен (по терминологии PHB-2024 «bloodied» — < ½ HP).
        hp_str = _hp_markup(hp.current, hp.maximum)
        lines.append(f"{idx} {marker} {name:<12} {hp_str} {entry.total:>3}")
    return "\n".join(lines)


def _hp_markup(current: int, maximum: int) -> str:
    """``HP 4/7`` с цветом по % здоровья: зелёный ≥½, жёлтый ≥¼,
    красный ниже. Помогает мгновенно оценить «на ком сосредоточиться»."""
    ratio = current / maximum if maximum else 0.0
    if ratio >= 0.5:
        color = "green"
    elif ratio >= 0.25:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]HP {current:>2}/{maximum}[/]"


class InitiativeWidget(Static):
    DEFAULT_CSS = ""

    # markup=True — чтобы [dim strike]/[red bold] в format_initiative
    # реально рендерились, а не печатались как литерал.
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def refresh_from(
        self,
        order: Sequence[InitiativeEntry],
        participants: dict[CreatureId, Creature],
        *,
        active_id: CreatureId | None = None,
    ) -> None:
        self.update(format_initiative(order, participants, active_id=active_id))


__all__ = ["InitiativeWidget", "format_initiative"]

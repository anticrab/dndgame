"""StatusWidget — статус активного PC.

См. ``docs/TUI.md`` §6.2.

Формат строки (80×24): name / HP / AC / Init / экономия (act/bonus/react) / speed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


def format_status(actor: Creature, ctx: TurnContext | None = None) -> str:
    """Краткая строка статуса актора.

    ``ctx`` опционален: при ``None`` рендерим без экономики действия
    (например, в начале боя или для не-активного PC).
    """
    hp = actor.hit_points
    bits = [
        f"{actor.name}",
        f"HP {hp.current}/{hp.maximum}",
        f"AC {actor.armor_class}",
        f"Spd {actor.speed_ft}ft",
    ]
    if ctx is not None:
        bits.append(
            f"| act:{_yn(not ctx.action_used)} "
            f"bonus:{_yn(not ctx.bonus_action_used)} "
            f"move:{ctx.movement_remaining_ft}ft"
        )
    return "  ".join(bits)


def _yn(flag: bool) -> str:
    return "Y" if flag else "N"


class StatusWidget(Static):
    DEFAULT_CSS = ""

    def refresh_from(
        self, actor: Creature, ctx: TurnContext | None = None
    ) -> None:
        self.update(format_status(actor, ctx))


__all__ = ["StatusWidget", "format_status"]

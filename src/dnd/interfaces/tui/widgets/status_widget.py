"""StatusWidget — статус активного PC.

См. ``docs/TUI.md`` §6.2.

Формат строки (80×24): name / HP / AC / Spd / экономия (act/bonus/move).
HP и флаги действий используют цвет, чтобы критическое состояние и
израсходованные действия моментально читались (N-2/N-4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


def format_status(actor: Creature, ctx: TurnContext | None = None) -> str:
    """Краткая строка статуса актора с Rich-markup'ом.

    ``ctx`` опционален: при ``None`` рендерим без экономики действия
    (например, в начале боя или для не-активного PC).

    Цвет HP — как в initiative (green ≥½, yellow ≥¼, red <¼).
    Цвет флагов экономии — green/red, чтобы «потратил action» бросалось
    в глаза и игрок понял, почему `a` больше не работает.
    """
    hp = actor.hit_points
    bits = [
        f"{actor.name}",
        _hp_markup(hp.current, hp.maximum),
        f"AC {actor.armor_class}",
        f"Spd {actor.speed_ft}ft",
    ]
    if ctx is not None:
        bits.append(
            f"| act:{_flag_markup(not ctx.action_used)} "
            f"bonus:{_flag_markup(not ctx.bonus_action_used)} "
            f"move:{_move_markup(ctx.movement_remaining_ft, actor.speed_ft)}"
        )
    # Q-10: пипсы спасбросков от смерти (PHB-2024 стр. 27) — только когда
    # существо в dying (death_saves is not None).
    if actor.death_saves is not None:
        bits.append(_death_save_markup(
            actor.death_saves.successes, actor.death_saves.failures
        ))
    return "  ".join(bits)


def _death_save_markup(successes: int, failures: int) -> str:
    succ = "[green]" + "●" * successes + "[/]" + "○" * (3 - successes)
    fail = "[red]" + "●" * failures + "[/]" + "○" * (3 - failures)
    return f"| Death saves: {succ} / {fail}"


def _hp_markup(current: int, maximum: int) -> str:
    ratio = current / maximum if maximum else 0.0
    if ratio >= 0.5:
        color = "green"
    elif ratio >= 0.25:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]HP {current}/{maximum}[/]"


def _flag_markup(available: bool) -> str:
    if available:
        return "[green]Y[/]"
    return "[red]N[/]"


def _move_markup(remaining_ft: int, base_speed_ft: int) -> str:
    if remaining_ft == 0:
        return "[red]0ft[/]"
    if remaining_ft < base_speed_ft:
        return f"[yellow]{remaining_ft}ft[/]"
    return f"[green]{remaining_ft}ft[/]"


class StatusWidget(Static):
    DEFAULT_CSS = ""

    # markup=True — без него [green]…[/] печатается как литерал.
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def refresh_from(
        self, actor: Creature, ctx: TurnContext | None = None
    ) -> None:
        self.update(format_status(actor, ctx))


__all__ = ["StatusWidget", "format_status"]

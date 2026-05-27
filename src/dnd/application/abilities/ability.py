"""Ability — runtime-описание игрового умения для UI/action-bar.

В отличие от :class:`Action`-классов (выполняют игровую логику),
``Ability`` описывает UI-аспект: hotkey, иконку, что нужно собрать
перед запуском (target / path), и фабрику строящую готовый
``PlayerIntent``. Это позволяет BattleScreen'у динамически строить
action-bar и роутить нажатия клавиш через :class:`AbilityRegistry`.

См. spec §4.3.

Положено в ``application/abilities`` (а не в ``domain/values/ability.py``)
по двум причинам:
1. В ``dnd.domain.values.ability`` уже занято имя ``Ability`` для StrEnum
   шести ability scores (STR/DEX/CON/INT/WIS/CHA);
2. ``intent_factory`` возвращает ``PlayerIntent`` — это application-слой,
   не domain. Domain про правила игры, application — про оркестровку
   игрока и движка.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import PlayerIntent
from dnd.domain.values.ability_id import AbilityId


@dataclass(frozen=True)
class Ability:
    """Описание умения, доступного игроку в action-bar."""

    id: AbilityId
    name: str
    icon: str
    default_hotkey: str
    economy_cost: ActionEconomyCost
    requires_target: bool
    requires_path: bool
    intent_factory: Callable[..., PlayerIntent]
    requires_area: bool = False  # T1: AoE-заклинание → BattleMode.AREA

    def __post_init__(self) -> None:
        # Mode-handler один за раз (MOVE / TARGET / AREA); умение, которое
        # хочет несколько режимов сразу, нельзя выразить текущим mode-state-
        # machine'ом — явно запрещаем, чтобы не ловить рантайм-сюрприз.
        if sum((self.requires_target, self.requires_path, self.requires_area)) > 1:
            raise ValueError(
                f"Ability {self.id}: requires_target/requires_path/requires_area "
                "взаимоисключающие (режим один за раз)"
            )


__all__ = ["Ability", "AbilityId"]

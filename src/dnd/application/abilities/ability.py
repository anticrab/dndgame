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
from typing import NewType

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import PlayerIntent

AbilityId = NewType("AbilityId", str)


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

    def __post_init__(self) -> None:
        # Mode-handler у нас один за раз (MOVE либо TARGET); умение,
        # которое хочет и то и другое, нельзя выразить текущим mode-state-
        # machine'ом — лучше явно запретить, чем чинить рантайм-сюрприз.
        if self.requires_target and self.requires_path:
            raise ValueError(
                f"Ability {self.id}: requires_target и requires_path "
                "mutually exclusive (mode либо TARGET, либо MOVE)"
            )


__all__ = ["Ability", "AbilityId"]

"""build_keymap — собирает ``{hotkey: Ability}`` для конкретного актора.

Алгоритм: сначала раскладываем default hotkey'и из ``Ability.default_hotkey``,
затем накатываем override'ы из ``Creature.keybindings``. При override
старый default hotkey этого умения вычищается, иначе одна и та же
ability оказалась бы привязана к двум клавишам (играющему это
непонятно — какая клавиша «настоящая»).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.abilities.ability import Ability
from dnd.application.abilities.registry import AbilityRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability_id import AbilityId

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext


def rebind_ability(actor: Creature, key: str, ability_id: AbilityId) -> None:
    """Переназначить ``key`` на ``ability_id`` в ``actor.keybindings`` (этап S).

    На сессию (в памяти). Инвариант «одна клавиша = одна способность, одна
    способность = одна кастом-клавиша»: снимаем прежнюю клавишу этой
    способности и прежнюю привязку этой клавиши, затем ставим новую.
    Финальный ``{hotkey: Ability}`` собирает :func:`build_keymap`.
    """
    actor.keybindings = {
        k: aid for k, aid in actor.keybindings.items() if k != key and aid != ability_id
    }
    actor.keybindings[key] = ability_id


def ability_can_afford(ability: Ability, ctx: TurnContext) -> bool:
    """Хватает ли экономии действия на способность — для грейинга в меню (этап S).

    Проверяем только бюджет экономии (`ctx.can_spend(economy_cost)`): напр.
    после потраченного действия ability c `ACTION` становится недоступной.
    Ресурс/слоты НЕ проверяем (нет доступа к action/spell-реестрам из TUI) —
    их безопасно отклонит собственный `can_perform_against` при применении.
    См. спек этапа S §2.1.
    """
    return ctx.can_spend(ability.economy_cost)


def build_keymap(actor: Creature, registry: AbilityRegistry) -> dict[str, Ability]:
    keymap: dict[str, Ability] = {}
    for aid in actor.ability_ids:
        ab = registry.get(aid)
        keymap[ab.default_hotkey] = ab
    for key, aid in actor.keybindings.items():
        ab = registry.get(aid)
        old = ab.default_hotkey
        if old in keymap and keymap[old] is ab:
            del keymap[old]
        keymap[key] = ab
    return keymap


__all__ = ["ability_can_afford", "build_keymap", "rebind_ability"]

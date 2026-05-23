"""Default-политики реакций для ``Encounter``.

PHB-2024 стр. 22 («Перемещение около других существ»):
threatener вправе совершить OA на цель, покидающую его reach. Само
действие — :class:`OpportunityAttack` (E6); политика отвечает на вопрос
«взять ли реакцию автоматически».

``auto_melee_oa_policy`` — простая модель «всегда атаковать, если есть
melee-оружие и реакция не потрачена». Без неё бой выглядит как «гоблин
смотрит, как ты убегаешь» — что нарушает базовое правило книги.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dnd.application.dto.action import Allowed
from dnd.application.dto.engine_event import OpportunityAttackProvoked
from dnd.application.engine.actions.attack import AttackKind
from dnd.application.engine.actions.opportunity_attack import OpportunityAttack
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.turn_context import TurnContext

if TYPE_CHECKING:
    from dnd.application.engine.encounter import Encounter

_log = logging.getLogger(__name__)


def auto_melee_oa_policy(
    event: OpportunityAttackProvoked, encounter: Encounter
) -> None:
    """Простая default-политика: каждый OA-trigger превращается в
    реальную melee-атаку threatener'а по двигающемуся, если threatener
    держит melee-оружие и реакция ещё свободна.

    Чужой ход → собственный TurnContext threatener'а не существует, но
    OpportunityAttack устроен так, чтобы оценивать экономику по
    ``actor.reaction_used`` (своему Creature-полю), а карту/dice брать
    из переданного ctx. Мы конструируем минимальный временный ctx с
    участниками encounter — он валиден для одной атаки.
    """
    threatener = encounter.participants.get(event.threatener_id)
    if threatener is None or not threatener.is_alive or threatener.is_at_zero_hp:
        return
    if threatener.reaction_used:
        return
    weapon = threatener.equipped_weapon
    if weapon is None or weapon.kind is not AttackKind.MELEE:
        return

    target_id = event.actor_id
    try:
        params = weapon_attack_params(threatener, target_id)
    except ValueError:
        return

    ctx = TurnContext(
        actor_id=threatener.id,
        battlefield=encounter.battlefield,
        dice_roller=encounter.deps.dice_roller,
        modifier_applier=encounter.deps.modifier_applier,
        condition_service=encounter.deps.condition_service,
        event_bus=encounter.event_bus,
        rng=encounter.deps.rng,
        participants=encounter.participants,
        factions=encounter.factions,
        movement_remaining_ft=0,
    )
    oa = OpportunityAttack()
    if not isinstance(oa.can_perform_against(threatener, params, ctx), Allowed):
        return
    try:
        oa.execute(threatener, params, ctx)
    except Exception:
        _log.exception("auto_melee_oa_policy: OA execute raised")


__all__ = ["auto_melee_oa_policy"]

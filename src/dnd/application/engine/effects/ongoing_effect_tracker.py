"""OngoingEffectTracker — снятие состояний по событийным триггерам (T2).

Контроль-заклинания накладывают состояние «до момента X». Хендлер публикует
:class:`ConditionApplied` со всей метой снятия; трекер хранит активный эффект и
снимает состояние, когда срабатывает триггер:

* урон по цели (``ends_on_damage``) — пробуждение Sleep;
* конец хода цели (``repeat_save_ability``) — повторный спасбросок Hold Person;
* срыв концентрации кастера (``ConcentrationBroken``) — снятие удержания.

Связь только через шину — трекер не знает про хендлеры, хендлеры не знают про
трекер. Это фундамент длительностей для этапа T3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import (
    ConcentrationBroken,
    ConditionApplied,
    ConditionRemoved,
    DamageDealt,
    TurnEnded,
)
from dnd.application.engine.saving_throw import roll_saving_throw_raw

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dnd.application.engine.modifier_applier import ModifierApplier
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.ids import ConditionId, CreatureId, SpellId


@dataclass(slots=True)
class OngoingConditionEffect:
    """Активный условие-эффект: что снять и по какому триггеру."""

    caster_id: CreatureId
    target_id: CreatureId
    spell_id: SpellId | None
    conditions: frozenset[ConditionId]
    ends_on_damage: bool
    repeat_save_ability: Ability | None
    save_dc: int | None
    concentration: bool


class OngoingEffectTracker:
    """Хранит активные условие-эффекты и снимает их по триггерам с шины."""

    def __init__(
        self,
        participants: Mapping[CreatureId, Creature],
        event_bus: EventBus,
        *,
        dice_roller: DiceRoller,
        modifier_applier: ModifierApplier,
    ) -> None:
        self._participants = participants
        self._bus = event_bus
        self._dice = dice_roller
        self._mods = modifier_applier
        self._effects: list[OngoingConditionEffect] = []

    def subscribe(self) -> None:
        self._bus.subscribe(ConditionApplied, self._on_applied)
        self._bus.subscribe(TurnEnded, self._on_turn_ended)
        self._bus.subscribe(DamageDealt, self._on_damage)
        self._bus.subscribe(ConcentrationBroken, self._on_concentration_broken)

    # --- запись ---------------------------------------------------------
    def _on_applied(self, event: ConditionApplied) -> None:
        self._effects.append(OngoingConditionEffect(
            caster_id=event.caster_id, target_id=event.target_id,
            spell_id=event.spell_id, conditions=event.conditions,
            ends_on_damage=event.ends_on_damage,
            repeat_save_ability=event.repeat_save_ability,
            save_dc=event.save_dc, concentration=event.concentration,
        ))

    # --- триггеры снятия ------------------------------------------------
    def _on_turn_ended(self, event: TurnEnded) -> None:
        actor = self._participants.get(event.actor_id)
        if actor is None:
            return
        for effect in list(self._effects):
            if effect.target_id != event.actor_id:
                continue
            if effect.repeat_save_ability is None or effect.save_dc is None:
                continue
            saved = roll_saving_throw_raw(
                actor, effect.repeat_save_ability, dc=effect.save_dc,
                dice_roller=self._dice, modifier_applier=self._mods,
                tags=("repeat_save",),
            )
            if saved:
                self._remove(effect, reason="save")

    def _on_damage(self, event: DamageDealt) -> None:
        if event.final_amount <= 0:
            return
        for effect in list(self._effects):
            if effect.target_id == event.target_id and effect.ends_on_damage:
                self._remove(effect, reason="damage")

    def _on_concentration_broken(self, event: ConcentrationBroken) -> None:
        for effect in list(self._effects):
            if (
                effect.concentration
                and effect.caster_id == event.actor_id
                and effect.spell_id is not None
                and str(effect.spell_id) == event.spell_id
            ):
                self._remove(effect, reason="concentration_ended")

    # --- снятие ---------------------------------------------------------
    def _remove(self, effect: OngoingConditionEffect, *, reason: str) -> None:
        target = self._participants.get(effect.target_id)
        if target is not None:
            for cond in effect.conditions:
                target.remove_condition(cond)
        if effect in self._effects:
            self._effects.remove(effect)
        self._bus.publish(ConditionRemoved(
            target_id=effect.target_id, conditions=effect.conditions, reason=reason,
        ))


__all__ = ["OngoingConditionEffect", "OngoingEffectTracker"]

"""OngoingEffectTracker (T2): запись эффектов + триггеры снятия."""

from __future__ import annotations

import uuid

from dnd.application.dto.engine_event import (
    ConcentrationBroken,
    ConditionApplied,
    ConditionRemoved,
    DamageDealt,
    TurnEnded,
)
from dnd.application.engine.effects.ongoing_effect_tracker import (
    OngoingEffectTracker,
)
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import CreatureId, RollId, SpellId


def _victim() -> Creature:
    return Creature.create(
        id_=CreatureId("orc"),
        name="orc",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=8, wis=8, cha=8),
        max_hp=15,
        armor_class=13,
        speed_ft=30,
    )


def _tracker(rolls: list[int], victim: Creature) -> tuple[OngoingEffectTracker, object]:
    deps, bus, _rng = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=rolls)
    tracker = OngoingEffectTracker(
        participants={victim.id: victim},
        event_bus=bus,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
    )
    tracker.subscribe()
    return tracker, bus


def test_damage_wakes_sleeper() -> None:
    victim = _victim()
    victim.apply_condition(UNCONSCIOUS)
    _t, bus = _tracker([], victim)
    bus.publish(
        ConditionApplied(
            caster_id=CreatureId("mage"),
            target_id=victim.id,
            spell_id=SpellId("sleep"),
            conditions=frozenset({UNCONSCIOUS}),
            ends_on_damage=True,
            repeat_save_ability=None,
            save_dc=None,
            concentration=False,
        )
    )
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)
    bus.publish(
        DamageDealt(
            attacker_id=CreatureId("x"),
            target_id=victim.id,
            damage_roll_id=RollId(uuid.uuid4()),
            damage_type=DamageType.SLASHING,
            raw_amount=3,
            final_amount=3,
            is_critical=False,
            hp_after=12,
            hp_max=15,
            was_lethal=False,
        )
    )
    assert not victim.has_condition(UNCONSCIOUS)
    assert removed and removed[-1].reason == "damage"


def test_turn_end_save_frees_held() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    # WIS(-1); d20=20 → 19 >= dc 13 → успех.
    _t, bus = _tracker([20], victim)
    bus.publish(
        ConditionApplied(
            caster_id=CreatureId("mage"),
            target_id=victim.id,
            spell_id=SpellId("hold_person"),
            conditions=frozenset({PARALYZED}),
            ends_on_damage=False,
            repeat_save_ability=Ability.WIS,
            save_dc=13,
            concentration=True,
        )
    )
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)
    bus.publish(TurnEnded(actor_id=victim.id, round_number=1))
    assert not victim.has_condition(PARALYZED)
    assert removed[-1].reason == "save"


def test_turn_end_save_fail_keeps_held() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    # d20=1 → 0 < 13 → провал, держим.
    _t, bus = _tracker([1], victim)
    bus.publish(
        ConditionApplied(
            caster_id=CreatureId("mage"),
            target_id=victim.id,
            spell_id=SpellId("hold_person"),
            conditions=frozenset({PARALYZED}),
            ends_on_damage=False,
            repeat_save_ability=Ability.WIS,
            save_dc=13,
            concentration=True,
        )
    )
    bus.publish(TurnEnded(actor_id=victim.id, round_number=1))
    assert victim.has_condition(PARALYZED)


def test_concentration_break_frees() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    _t, bus = _tracker([], victim)
    bus.publish(
        ConditionApplied(
            caster_id=CreatureId("mage"),
            target_id=victim.id,
            spell_id=SpellId("hold_person"),
            conditions=frozenset({PARALYZED}),
            ends_on_damage=False,
            repeat_save_ability=Ability.WIS,
            save_dc=13,
            concentration=True,
        )
    )
    bus.publish(
        ConcentrationBroken(
            actor_id=CreatureId("mage"),
            spell_id="hold_person",
            dc=10,
            roll_total=3,
        )
    )
    assert not victim.has_condition(PARALYZED)

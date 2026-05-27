"""Истечение состояний/баффов по часам (X0-3, X0-4)."""

from __future__ import annotations

from dnd.application.dto.engine_event import (
    ConditionApplied,
    ConditionRemoved,
    RoundEnded,
)
from dnd.application.engine.effects.ongoing_effect_tracker import OngoingEffectTracker
from dnd.composition import build_scripted_runtime_services
from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId


def _victim() -> Creature:
    return Creature.create(
        id_=CreatureId("v"),
        name="v",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )


def test_condition_expires_when_clock_passes_deadline() -> None:
    services, bus, _ = build_scripted_runtime_services(rolls=[])
    reg = ConditionRegistry()
    register_default_conditions(reg)
    victim = _victim()
    victim.apply_condition(PARALYZED)
    clock = GameClock()
    tracker = OngoingEffectTracker(
        {victim.id: victim},
        bus,
        dice_roller=services.dice_roller,
        modifier_applier=services.modifier_applier,
        condition_service=services.condition_service,
        clock=clock,
    )
    tracker.subscribe()
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)

    bus.publish(
        ConditionApplied(
            caster_id=CreatureId("c"),
            target_id=victim.id,
            spell_id=SpellId("hold_person"),
            conditions=frozenset({PARALYZED}),
            concentration=True,
            expires_at_round=2,
        )
    )

    clock.advance(1)
    bus.publish(RoundEnded(round_number=1))
    assert victim.has_condition(PARALYZED)

    clock.advance(1)
    bus.publish(RoundEnded(round_number=2))
    assert not victim.has_condition(PARALYZED)
    assert removed and removed[-1].reason == "duration"

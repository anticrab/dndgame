"""BreakAction — атака по InteractableObject с HP."""
from __future__ import annotations

from dnd.application.dto.action import (
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import EngineEvent, ObjectDamaged
from dnd.application.engine.actions.break_object import (
    BreakAction,
    BreakParams,
)
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import CreatureId, ObjectId
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _setup(*, atk_d20: int, dmg_d8: int, obj_hp: int = 5, obj_ac: int = 10):
    actor = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    barrel = InteractableObject(
        id=ObjectId("bar-1"), kind=ObjectKind.BARREL, pos=Square(2, 3),
        state={"hp": obj_hp, "ac": obj_ac, "broken": False, "contents": ["bolts_10"]},
    )
    bf = Battlefield(5, 5)
    bf.place_creature(actor.id, Square(2, 2))
    bf.place_object(barrel)
    bus = InMemoryEventBus()
    rng = ScriptedRNG([atk_d20, dmg_d8])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=actor.id, battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus, rng=rng,
        participants={actor.id: actor}, movement_remaining_ft=30,
    )
    return actor, barrel, ctx, bus


def test_break_action_hits_and_damages() -> None:
    actor, barrel, ctx, bus = _setup(atk_d20=15, dmg_d8=4, obj_hp=10)
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    params = BreakParams(
        target_object_id=barrel.id,
        attack_bonus=5,
        damage_expr="1d8+3",
        damage_type=DamageType.BLUDGEONING,
    )
    av = BreakAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Allowed)
    BreakAction().execute(actor, params, ctx)
    # d20=15+5=20 vs AC 10 → hit. damage = 4+3 = 7.
    assert barrel.state["hp"] == 3  # 10 - 7
    events = [e for e in captured if isinstance(e, ObjectDamaged)]
    assert len(events) == 1
    assert events[0].final_amount == 7
    assert events[0].broken is False


def test_break_action_breaks_object_when_hp_zero() -> None:
    actor, barrel, ctx, bus = _setup(atk_d20=15, dmg_d8=8, obj_hp=5)
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    params = BreakParams(
        target_object_id=barrel.id, attack_bonus=5,
        damage_expr="1d8+3", damage_type=DamageType.BLUDGEONING,
    )
    BreakAction().execute(actor, params, ctx)
    # dmg = 8 + 3 = 11 > hp=5 → broken
    assert barrel.state["broken"] is True
    assert barrel.state["hp"] == 0
    events = [e for e in captured if isinstance(e, ObjectDamaged)]
    assert events[0].broken is True


def test_break_action_too_far_forbidden() -> None:
    actor = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    barrel = InteractableObject(
        id=ObjectId("b"), kind=ObjectKind.BARREL, pos=Square(4, 4),
        state={"hp": 5, "ac": 10, "broken": False, "contents": []},
    )
    bf = Battlefield(5, 5)
    bf.place_creature(actor.id, Square(0, 0))
    bf.place_object(barrel)
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=actor.id, battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus, rng=rng,
        participants={actor.id: actor}, movement_remaining_ft=30,
    )
    params = BreakParams(
        target_object_id=barrel.id, attack_bonus=5,
        damage_expr="1d8", damage_type=DamageType.BLUDGEONING,
    )
    av = BreakAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.OUT_OF_RANGE


def test_break_action_object_no_hp_rejected() -> None:
    """Если у объекта нет hp в state — Forbidden CUSTOM."""
    actor = Creature.create(
        id_=CreatureId("pc"), name="PC",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    chest = InteractableObject(
        id=ObjectId("c"), kind=ObjectKind.CHEST, pos=Square(2, 3),
        state={"open": False, "contents": []},  # нет hp!
    )
    bf = Battlefield(5, 5)
    bf.place_creature(actor.id, Square(2, 2))
    bf.place_object(chest)
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=actor.id, battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus, rng=rng,
        participants={actor.id: actor}, movement_remaining_ft=30,
    )
    params = BreakParams(
        target_object_id=chest.id, attack_bonus=5,
        damage_expr="1d8", damage_type=DamageType.BLUDGEONING,
    )
    av = BreakAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CUSTOM


def test_break_action_consumes_action() -> None:
    actor, barrel, ctx, _ = _setup(atk_d20=15, dmg_d8=4)
    params = BreakParams(
        target_object_id=barrel.id, attack_bonus=5,
        damage_expr="1d8+3", damage_type=DamageType.BLUDGEONING,
    )
    BreakAction().execute(actor, params, ctx)
    assert ctx.action_used is True

"""InteractAction — открытие/закрытие дверей и сундуков (PHB-2024 free)."""
from __future__ import annotations

from dnd.application.dto.action import (
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import EngineEvent, ObjectInteracted
from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.application.engine.actions.interact import (
    InteractAction,
    InteractKind,
    InteractParams,
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
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _setup(*, actor_pos: Square, obj_pos: Square, obj_state: dict) -> tuple[Creature, InteractableObject, TurnContext, InMemoryEventBus]:
    actor = Creature.create(
        id_=CreatureId("pc"),
        name="PC",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=obj_pos,
        state=obj_state,
    )
    bf = Battlefield(5, 5)
    bf.place_creature(actor.id, actor_pos)
    bf.place_object(door)
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants={actor.id: actor},
        movement_remaining_ft=30,
    )
    return actor, door, ctx, bus


def test_interact_open_door_adjacent_ok() -> None:
    actor, door, ctx, bus = _setup(
        actor_pos=Square(2, 2),
        obj_pos=Square(2, 3),
        obj_state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    params = InteractParams(target_object_id=door.id, kind=InteractKind.OPEN)
    assert isinstance(InteractAction().can_perform_against(actor, params, ctx), Allowed)
    InteractAction().execute(actor, params, ctx)
    assert door.state["open"] is True
    events = [e for e in captured if isinstance(e, ObjectInteracted)]
    assert len(events) == 1
    assert events[0].kind == "open"


def test_interact_locked_door_returns_forbidden_custom() -> None:
    actor, door, ctx, _ = _setup(
        actor_pos=Square(2, 2),
        obj_pos=Square(2, 3),
        obj_state={"open": False, "locked": True, "hp": 10, "ac": 13},
    )
    params = InteractParams(target_object_id=door.id, kind=InteractKind.OPEN)
    av = InteractAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CUSTOM
    assert "locked" in (av.details or "")


def test_interact_too_far_forbidden() -> None:
    actor, door, ctx, _ = _setup(
        actor_pos=Square(0, 0),
        obj_pos=Square(4, 4),  # > 5ft
        obj_state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    params = InteractParams(target_object_id=door.id, kind=InteractKind.OPEN)
    av = InteractAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.OUT_OF_RANGE


def test_interact_close_door() -> None:
    actor, door, ctx, bus = _setup(
        actor_pos=Square(2, 2),
        obj_pos=Square(2, 3),
        obj_state={"open": True, "locked": False, "hp": 10, "ac": 13},
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    params = InteractParams(target_object_id=door.id, kind=InteractKind.CLOSE)
    InteractAction().execute(actor, params, ctx)
    assert door.state["open"] is False


def test_interact_uses_free_object_interaction_once_per_turn() -> None:
    """PHB-2024 стр. 21: free object-interaction 1/ход."""
    actor, door, ctx, _ = _setup(
        actor_pos=Square(2, 2),
        obj_pos=Square(2, 3),
        obj_state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    params = InteractParams(target_object_id=door.id, kind=InteractKind.OPEN)
    InteractAction().execute(actor, params, ctx)
    # Второй раз в тот же ход — нельзя.
    av = InteractAction().can_perform(actor, ctx)
    assert isinstance(av, Forbidden)


def test_interact_open_chest_returns_loot_in_event() -> None:
    actor = Creature.create(
        id_=CreatureId("pc"),
        name="PC",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    chest = InteractableObject(
        id=ObjectId("chest-1"),
        kind=ObjectKind.CHEST,
        pos=Square(2, 3),
        state={"open": False, "contents": ["gold_50", "potion_heal"]},
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
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    params = InteractParams(target_object_id=chest.id, kind=InteractKind.OPEN)
    InteractAction().execute(actor, params, ctx)
    events = [e for e in captured if isinstance(e, ObjectInteracted)]
    assert len(events) == 1
    assert events[0].loot == ("gold_50", "potion_heal")

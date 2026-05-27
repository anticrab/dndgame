"""GameRunner._apply_intent корректно обрабатывает InteractIntent и
BreakIntent.

Solo-encounter сценарий для этих intent'ов неудобен: ``Encounter.start``
сразу же отдаёт ``EncounterEnded`` (одна сторона — победитель по
определению), и до PC-провайдера дело не доходит. Поэтому тут — прямой
вызов ``GameRunner._apply_intent`` с вручную собранным TurnContext'ом.
Это и есть единица, которую мы покрываем (трансляция intent → action).
"""

from __future__ import annotations

from dnd.application.dto.engine_event import (
    EngineEvent,
    ObjectDamaged,
    ObjectInteracted,
)
from dnd.application.dto.player_intent import BreakIntent, InteractIntent
from dnd.application.engine.actions.interact import InteractKind
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.game_runner import GameRunner
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, ObjectId
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG
from dnd.interfaces.cli.scripted_provider import ScriptedIntentProvider


def _make_warrior() -> Creature:
    return Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _make_ctx(
    actor: Creature,
    bf: Battlefield,
    rolls: list[int],
) -> tuple[TurnContext, InMemoryEventBus, list[EngineEvent]]:
    """Собрать минимальный TurnContext с подписанным сборщиком событий."""
    bus = InMemoryEventBus()
    rng = ScriptedRNG(rolls)
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
        movement_remaining_ft=actor.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    return ctx, bus, captured


def test_interact_intent_opens_door() -> None:
    """InteractIntent(OPEN) → InteractAction → ObjectInteracted + door.open."""
    warrior = _make_warrior()
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(2, 3),
        state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    bf = Battlefield(5, 5)
    bf.place_creature(warrior.id, Square(2, 2))
    bf.place_object(door)

    ctx, _bus, captured = _make_ctx(warrior, bf, rolls=[])

    runner = GameRunner(intent_provider=ScriptedIntentProvider([]))
    runner._apply_intent(  # type: ignore[attr-defined]
        warrior,
        InteractIntent(
            target_object_id=door.id,
            interact_kind=InteractKind.OPEN,
        ),
        ctx,
        encounter=None,  # type: ignore[arg-type]  # _apply_intent его не использует здесь
    )

    assert door.state["open"] is True
    assert any(isinstance(e, ObjectInteracted) for e in captured)


def test_break_intent_attacks_barrel() -> None:
    """BreakIntent → BreakAction.execute (через weapon_attack_params).

    atk d20=20 + STR mod 3 + prof 2 = 25 vs ac 10 → hit;
    dmg d8=8 + 3 = 11, barrel HP=5 → broken=True.
    """
    warrior = _make_warrior()
    barrel = InteractableObject(
        id=ObjectId("bar-1"),
        kind=ObjectKind.BARREL,
        pos=Square(3, 2),
        state={"hp": 5, "ac": 10, "broken": False, "contents": []},
    )
    bf = Battlefield(5, 5)
    bf.place_creature(warrior.id, Square(2, 2))
    bf.place_object(barrel)

    ctx, _bus, captured = _make_ctx(warrior, bf, rolls=[20, 8])

    runner = GameRunner(intent_provider=ScriptedIntentProvider([]))
    runner._apply_intent(  # type: ignore[attr-defined]
        warrior,
        BreakIntent(target_object_id=barrel.id),
        ctx,
        encounter=None,  # type: ignore[arg-type]
    )

    assert barrel.state["broken"] is True
    assert barrel.state["hp"] == 0
    damaged = [e for e in captured if isinstance(e, ObjectDamaged)]
    assert len(damaged) == 1
    assert damaged[0].broken is True


def test_break_intent_without_weapon_is_noop() -> None:
    """Без equipped_weapon BreakIntent тихо игнорируется (log.info)."""
    unarmed = Creature.create(
        id_=CreatureId("monk"),
        name="Monk",
        abilities=AbilityScores.of(str_=12, dex=14, con=12, int_=10, wis=14, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
    )
    barrel = InteractableObject(
        id=ObjectId("bar-1"),
        kind=ObjectKind.BARREL,
        pos=Square(3, 2),
        state={"hp": 5, "ac": 10, "broken": False},
    )
    bf = Battlefield(5, 5)
    bf.place_creature(unarmed.id, Square(2, 2))
    bf.place_object(barrel)

    ctx, _bus, captured = _make_ctx(unarmed, bf, rolls=[])

    runner = GameRunner(intent_provider=ScriptedIntentProvider([]))
    runner._apply_intent(  # type: ignore[attr-defined]
        unarmed,
        BreakIntent(target_object_id=barrel.id),
        ctx,
        encounter=None,  # type: ignore[arg-type]
    )

    assert barrel.state["hp"] == 5
    assert not any(isinstance(e, ObjectDamaged) for e in captured)

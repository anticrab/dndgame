"""Тесты EventRenderer — без поднятия Textual App.

Используем фейковый «экран» с тем же интерфейсом виджетов, что
у BattleScreen, и `call_from_thread = lambda f, *a, **kw: f(*a, **kw)`
для прямого вызова.

Покрытие:
* InitiativeRolled сохраняет порядок и обновляет InitiativeWidget;
* TurnStarted делает StatusWidget.refresh и помечает active actor;
* DamageDealt обновляет статус актора;
* StanceTaken обновляет статус;
* EncounterEnded дополнительно перерисовывает map/initiative;
* лог получает каждое событие через handle_event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from dnd.application.dto.engine_event import (
    AttackResolved,
    DamageDealt,
    EncounterEnded,
    EngineEvent,
    InitiativeRolled,
    StanceTaken,
    TurnStarted,
)
from dnd.application.dto.initiative import InitiativeEntry
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, RollId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.interfaces.tui.bridge.event_renderer import EventRenderer


@dataclass
class _FakeWidget:
    refresh_calls: list[tuple[tuple, dict]] = field(default_factory=list)
    log_events: list[EngineEvent] = field(default_factory=list)

    def refresh_from(self, *args: Any, **kwargs: Any) -> None:
        self.refresh_calls.append((args, kwargs))

    def handle_event(self, event: EngineEvent) -> None:
        self.log_events.append(event)


@dataclass
class _FakeScreen:
    map_widget: _FakeWidget = field(default_factory=_FakeWidget)
    status_widget: _FakeWidget = field(default_factory=_FakeWidget)
    initiative_widget: _FakeWidget = field(default_factory=_FakeWidget)
    log_widget: _FakeWidget = field(default_factory=_FakeWidget)
    cleared_calls: int = 0

    def clear_active_turn(self) -> None:
        self.cleared_calls += 1


def _warrior() -> Creature:
    return Creature.create(
        id_=CreatureId("warrior"),
        name="warrior",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _goblin() -> Creature:
    return Creature.create(
        id_=CreatureId("goblin"),
        name="goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _setup() -> tuple[_FakeScreen, Encounter, InMemoryEventBus, EventRenderer]:
    bf = Battlefield(5, 5)
    warrior = _warrior()
    goblin = _goblin()
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 5])
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    screen = _FakeScreen()

    def direct(f: Any, *a: Any, **kw: Any) -> Any:
        return f(*a, **kw)

    renderer = EventRenderer(screen, enc, call_from_thread=direct)  # type: ignore[arg-type]
    renderer.subscribe(bus)
    return screen, enc, bus, renderer


def _entry(cid: str, total: int, order: int) -> InitiativeEntry:
    return InitiativeEntry(
        creature_id=CreatureId(cid),
        total=total,
        d20_raw=total,
        dex_score=10,
        insertion_order=order,
        roll_id=RollId(uuid4()),
    )


def test_initiative_event_refreshes_initiative_widget() -> None:
    screen, _, bus, _ = _setup()
    bus.publish(
        InitiativeRolled(
            order=(_entry("warrior", 18, 0), _entry("goblin", 12, 1))
        )
    )
    assert len(screen.initiative_widget.refresh_calls) >= 1


def test_turn_started_for_pc_refreshes_status() -> None:
    screen, _, bus, _ = _setup()
    bus.publish(TurnStarted(actor_id=CreatureId("warrior"), round_number=1))
    # status refreshed
    assert len(screen.status_widget.refresh_calls) >= 1
    # PC turn — не должны очищать active state.
    assert screen.cleared_calls == 0


def test_turn_started_for_enemy_clears_active_state() -> None:
    screen, _, bus, _ = _setup()
    bus.publish(TurnStarted(actor_id=CreatureId("goblin"), round_number=1))
    assert screen.cleared_calls == 1


def test_stance_taken_refreshes_status() -> None:
    screen, _, bus, _ = _setup()
    # активный актор для контекста.
    bus.publish(TurnStarted(actor_id=CreatureId("warrior"), round_number=1))
    pre = len(screen.status_widget.refresh_calls)
    bus.publish(StanceTaken(actor_id=CreatureId("warrior"), stance="dodging"))
    assert len(screen.status_widget.refresh_calls) > pre


def test_damage_dealt_refreshes_status_of_active_actor() -> None:
    screen, _enc, bus, _ = _setup()
    bus.publish(TurnStarted(actor_id=CreatureId("warrior"), round_number=1))
    pre = len(screen.status_widget.refresh_calls)
    rid = RollId(uuid4())
    bus.publish(
        DamageDealt(
            attacker_id=CreatureId("goblin"),
            target_id=CreatureId("warrior"),
            damage_roll_id=rid,
            damage_type=DamageType.SLASHING,
            raw_amount=4,
            final_amount=4,
            is_critical=False,
            hp_after=16,
            hp_max=20,
        )
    )
    assert len(screen.status_widget.refresh_calls) > pre


def test_attack_resolved_downed_triggers_map_and_initiative_refresh() -> None:
    screen, _, bus, _ = _setup()
    bus.publish(TurnStarted(actor_id=CreatureId("warrior"), round_number=1))
    map_pre = len(screen.map_widget.refresh_calls)
    init_pre = len(screen.initiative_widget.refresh_calls)
    bus.publish(
        AttackResolved(
            attacker_id=CreatureId("warrior"),
            target_id=CreatureId("goblin"),
            attack_roll_id=RollId(uuid4()),
            hit=True,
            is_critical=False,
            downed=True,
        )
    )
    assert len(screen.map_widget.refresh_calls) > map_pre
    assert len(screen.initiative_widget.refresh_calls) > init_pre


def test_encounter_ended_refreshes_map_and_initiative() -> None:
    screen, _, bus, _ = _setup()
    bus.publish(
        EncounterEnded(
            winners=Faction.PARTY,
            round_number=3,
            survivors=(CreatureId("warrior"),),
        )
    )
    assert len(screen.map_widget.refresh_calls) >= 1
    assert len(screen.initiative_widget.refresh_calls) >= 1


def test_log_widget_receives_every_event() -> None:
    screen, _, bus, _ = _setup()
    events = [
        TurnStarted(actor_id=CreatureId("warrior"), round_number=1),
        StanceTaken(actor_id=CreatureId("warrior"), stance="dodging"),
    ]
    for e in events:
        bus.publish(e)
    assert screen.log_widget.log_events == events

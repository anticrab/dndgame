"""Тесты EventPrinter: рендеринг ключевых событий в строки.

Используем ``rich.console.Console`` с буфером (``file=StringIO``,
``force_terminal=False``) — никаких ANSI-кодов, чистый текст.
"""

from __future__ import annotations

from io import StringIO
from uuid import uuid4

from rich.console import Console

from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    DamageDealt,
    EncounterEnded,
    InitiativeRolled,
    RoundStarted,
    TurnStarted,
)
from dnd.application.dto.ids import CreatureId, RollId
from dnd.application.dto.initiative import InitiativeEntry
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.interfaces.cli.event_printer import EventPrinter


def _printer_with_buffer() -> tuple[EventPrinter, StringIO, InMemoryEventBus]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    printer = EventPrinter(console)
    bus = InMemoryEventBus()
    printer.subscribe(bus)
    return printer, buf, bus


def _rid() -> RollId:
    return RollId(uuid4())


def test_prints_initiative() -> None:
    _, buf, bus = _printer_with_buffer()
    entry = InitiativeEntry(
        creature_id=CreatureId("a"),
        total=18,
        d20_raw=17,
        dex_score=14,
        insertion_order=0,
        roll_id=_rid(),
    )
    bus.publish(InitiativeRolled(order=(entry,)))
    assert "Initiative" in buf.getvalue()
    assert "a (18)" in buf.getvalue()


def test_prints_round_and_turn() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(RoundStarted(round_number=1))
    bus.publish(TurnStarted(actor_id=CreatureId("a"), round_number=1))
    out = buf.getvalue()
    assert "Round 1" in out
    assert "a's turn" in out


def test_prints_attack_hit_then_damage() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(
        AttackRolled(
            attacker_id=CreatureId("a"),
            target_id=CreatureId("b"),
            attack_roll_id=_rid(),
            effective_ac=15,
            is_critical_hit=False,
            is_critical_miss=False,
            hit=True,
        )
    )
    bus.publish(
        DamageDealt(
            attacker_id=CreatureId("a"),
            target_id=CreatureId("b"),
            damage_roll_id=_rid(),
            damage_type=DamageType.SLASHING,
            raw_amount=8,
            final_amount=8,
            is_critical=False,
        )
    )
    out = buf.getvalue()
    assert "hit" in out
    assert "AC 15" in out
    assert "8" in out
    assert "slashing" in out


def test_prints_critical_hit() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(
        AttackRolled(
            attacker_id=CreatureId("a"),
            target_id=CreatureId("b"),
            attack_roll_id=_rid(),
            effective_ac=15,
            is_critical_hit=True,
            is_critical_miss=False,
            hit=True,
        )
    )
    assert "CRITICAL HIT" in buf.getvalue()


def test_prints_downed_in_resolved() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(
        AttackResolved(
            attacker_id=CreatureId("a"),
            target_id=CreatureId("b"),
            attack_roll_id=_rid(),
            hit=True,
            is_critical=False,
            downed=True,
        )
    )
    assert "falls" in buf.getvalue()


def test_prints_encounter_winners() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(
        EncounterEnded(
            winners=Faction.PARTY,
            round_number=3,
            survivors=(CreatureId("a"),),
        )
    )
    out = buf.getvalue()
    assert "ENCOUNTER ENDED" in out
    assert "PARTY WINS" in out


def test_prints_encounter_draw_when_winners_none() -> None:
    _, buf, bus = _printer_with_buffer()
    bus.publish(
        EncounterEnded(winners=None, round_number=100, survivors=())
    )
    assert "DRAW" in buf.getvalue()

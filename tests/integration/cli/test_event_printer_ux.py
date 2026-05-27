"""Интеграционные тесты UX-полей в game-логе (аудит 16).

Проверяют формат:
* AttackRolled — печатает d20/total/advantage.
* DamageDealt — печатает текущий HP цели.
* EncounterEnded — печатает survivors.
* StanceTaken — печатает «takes DODGING».
* Square — печатается как `(x,y)`, не `Square(x=2, y=2)`.

В отличие от unit-тестов `test_event_printer.py` (минимальные стабы),
эти бегут реальные AttackAction / DodgeAction через настоящий Encounter
+ ScriptedRNG и читают живой rich-вывод.
"""

from __future__ import annotations

import re
from io import StringIO

import pytest
from rich.console import Console

from dnd.application.dto.player_intent import (
    AttackIntent,
    DodgeIntent,
    EndTurnIntent,
)
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.game_runner import GameRunner
from dnd.composition import (
    build_default_runtime_services,
    build_scripted_dependencies,
)
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.cli.event_printer import EventPrinter
from dnd.interfaces.cli.scripted_provider import ScriptedIntentProvider


def _warrior() -> Creature:
    return Creature.create(
        id_=CreatureId("aelar"),
        name="aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _goblin(*, hp: int = 7) -> Creature:
    return Creature.create(
        id_=CreatureId("goblin"),
        name="goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=hp,
        armor_class=5,  # гарантия попаданий
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _printer_buffer() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, width=120, force_terminal=False, color_system=None)
    return console, buf


def _real_services(seed: int):
    """Production-сервисы с детерминированным seed. Лог фиксируется на
    `seed`, поэтому изменения формата ловятся, а исчерпание бросков
    как в ScriptedRNG невозможно."""
    return build_default_runtime_services(rng=RealRNG(seed=seed))


@pytest.mark.e2e
def test_log_attack_shows_d20_and_target_hp() -> None:
    """Проверяем формат `d20=NN→TOTAL vs AC X` и `(HP cur/max)` в логе
    атаки и урона."""
    bf = Battlefield(5, 5)
    warrior = _warrior()
    goblin = _goblin(hp=10)
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    services = _real_services(seed=42)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=services.with_battlefield(bf),
    )
    console, buf = _printer_buffer()
    EventPrinter(console).subscribe(enc.event_bus)

    intents = ScriptedIntentProvider([AttackIntent(target_id=goblin.id), EndTurnIntent()])
    GameRunner(intent_provider=intents).run(enc)

    out = buf.getvalue()
    # AttackRolled — есть d20=NN → TOTAL.
    assert re.search(r"d20=\d+→\d+", out), out
    # AC 5 — мы поставили goblin AC=5, это попадёт в лог.
    assert "AC 5" in out
    # DamageDealt — формат "(HP cur/max)" хотя бы один раз.
    assert re.search(r"HP \d+/\d+", out), out


@pytest.mark.e2e
def test_log_shows_dodge_and_disadvantage_marker() -> None:
    """PC делает Dodge → атака монстра по нему помечена как `dis`
    в логе."""
    bf = Battlefield(5, 5)
    warrior = _warrior()
    goblin = _goblin()
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    services = _real_services(seed=7)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=services.with_battlefield(bf),
    )
    console, buf = _printer_buffer()
    EventPrinter(console).subscribe(enc.event_bus)

    intents = ScriptedIntentProvider([DodgeIntent(), EndTurnIntent()])
    GameRunner(intent_provider=intents).run(enc)

    out = buf.getvalue()
    # StanceTaken — Dodge напечатан.
    assert "takes DODGING" in out, out
    # Атака goblin'а по защищающемуся warrior'у — disadvantage маркер.
    assert " dis" in out, out


@pytest.mark.e2e
def test_log_encounter_ended_lists_survivors() -> None:
    bf = Battlefield(5, 5)
    warrior = _warrior()
    goblin = _goblin(hp=1)
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    rolls = [20, 5, 18, 8]  # init + atk + dmg → goblin падает
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    console, buf = _printer_buffer()
    EventPrinter(console).subscribe(enc.event_bus)

    intents = ScriptedIntentProvider([AttackIntent(target_id=goblin.id), EndTurnIntent()])
    GameRunner(intent_provider=intents).run(enc)

    out = buf.getvalue()
    assert "ENCOUNTER ENDED" in out
    assert "PARTY WINS" in out
    assert "Survivors:" in out
    assert "aelar" in out


def test_square_str_compact_in_logs() -> None:
    """Square печатается как `(x,y)` — это влияет на читаемость
    логов перемещения."""
    sq = Square(3, 7)
    assert str(sq) == "(3,7)"
    # Через f-string — тоже.
    assert f"{sq}" == "(3,7)"

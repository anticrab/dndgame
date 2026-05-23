"""Интеграционный тест: GameRunner корректно прерывает PC-цикл, когда
encounter завершён убийством последнего врага во время хода PC.

Воспроизводит сценарий из аудита 16: после `☠ ... falls!` игроку не
должны больше задавать вопрос «choose action». PC-цикл `_run_pc_turn`
обязан вернуться, как только `encounter.is_concluded == True`.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import EncounterEnded, EngineEvent
from dnd.application.dto.ids import CreatureId
from dnd.application.dto.player_intent import (
    AttackIntent,
    EndTurnIntent,
    PlayerIntent,
)
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.game_runner import GameRunner
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


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
        max_hp=1,
        armor_class=5,  # гарантированно попадаем
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


class _CountingProvider:
    """Считает вызовы next_intent, чтобы убедиться: после смерти
    последнего врага runner не вернётся за следующим intent'ом."""

    def __init__(self, intents: list[PlayerIntent]) -> None:
        self._intents = list(intents)
        self.calls = 0

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        del actor, ctx, encounter
        self.calls += 1
        if self._intents:
            return self._intents.pop(0)
        return EndTurnIntent()


@pytest.mark.e2e
def test_runner_stops_polling_after_last_enemy_dies() -> None:
    bf = Battlefield(5, 5)
    warrior = _warrior()
    goblin = _goblin()
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))

    # warrior 21, goblin 5; warrior атакует одним выстрелом — goblin падает.
    # Запасные нули — на случай нежданных бросков (concentration save, и т.п.)
    rolls = [20, 5, 18, 8] + [10] * 30
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # PC хочет атаковать и затем ещё 9 раз попробовать. Без guard'а
    # runner спросил бы все 10 раз; с guard'ом — ровно 1 раз
    # (первый AttackIntent убивает goblin'а → encounter завершён).
    provider = _CountingProvider([AttackIntent(target_id=goblin.id)] * 10)
    GameRunner(intent_provider=provider).run(enc)

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY
    # ВАЖНОЕ: после смерти goblin'а PC не получил больше вопросов.
    assert provider.calls == 1, (
        f"GameRunner запросил {provider.calls} intent(s) — должен был 1: "
        "after EncounterEnded цикл должен прерваться."
    )

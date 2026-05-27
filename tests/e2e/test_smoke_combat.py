"""E2E smoke-сценарий: «Воин vs Гоблин» — бой до конца.

Цель — собрать весь движок целиком через ``composition`` и убедиться,
что цикл боя сходится:

1. composition root собирает EncounterDependencies.
2. Battlefield 5×5; Воин в (1,2), Гоблин в (3,2).
3. Encounter с двумя existo (PARTY/MONSTERS), инициатива по
   ScriptedRNG так, чтобы Воин ходил первым.
4. На своих ходах: Воин — атака; Гоблин — SimpleMonsterAI.
5. RNG подобран так, что Воин убивает Гоблина за один-два хода.
6. Финальная проверка: ``EncounterEnded(winners=Faction.PARTY)``.

Это **смок-тест**, не доказательство всех правил по book —
конкретные правила покрыты юнит-тестами. Здесь проверяем «движок
запускается и сходится».
"""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import (
    AttackResolved,
    EncounterEnded,
    EngineEvent,
    TurnStarted,
)
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD, SCIMITAR

_MAX_TURNS = 30  # защита от бесконечного цикла


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


def _make_goblin() -> Creature:
    return Creature.create(
        id_=CreatureId("goblin"),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=SCIMITAR,
    )


@pytest.mark.e2e
def test_smoke_warrior_kills_goblin() -> None:
    """Воин (STR 16, longsword 1d8) против Гоблина (HP 7, AC 13).

    RNG-скрипт (по очереди потребляется DiceRoller'ом):

    Этап         | rolls
    -------------|------
    Init warrior | 14   → 14 + DEX +1 = 15
    Init goblin  | 18   → 18 + DEX +2 = 20  (но 20 > 15, гоблин ходит первым)

    Чтобы воин был первым — поднимем гоблину d20=8 (10 < 15). Меняю
    порядок: warrior=18, goblin=8.

    Дальше — атака warrior'а: d20=18 + atk +5 = 23 vs 13 → попал
    (без крита). Damage 1d8 → 7 + STR 3 = 10. Goblin: 7 - 10 = 0 HP.

    Goblin DOWN на первом же ходу — EncounterEnded(PARTY).
    """
    bf = Battlefield(5, 5)
    warrior = _make_warrior()
    goblin = _make_goblin()
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(2, 2))  # соседняя, чтобы melee достал

    rolls = [
        18,  # warrior init d20: 18 + 1 = 19
        8,  # goblin  init d20:  8 + 2 = 10 → warrior первый
        18,  # warrior attack d20: 18 + 5 = 23 vs AC 13 → попал
        7,  # warrior damage 1d8 = 7; +3 STR = 10 → goblin 7-10 = 0
    ]
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)

    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )

    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    enc.start()

    # Игровой цикл: проигрываем ходы до концовки.
    turns = 0
    while not enc.is_concluded and turns < _MAX_TURNS:
        turns += 1
        actor_id = enc.current_actor_id
        ctx = enc.start_turn()
        actor = enc.participants[actor_id]

        if not actor.is_alive or actor.is_at_zero_hp:
            enc.end_turn()
            continue

        if enc.factions[actor_id] is Faction.PARTY:
            # Воин атакует ближайшего goblin'а через AttackAction.
            params = weapon_attack_params(actor, goblin.id)
            from dnd.application.dto.action import Allowed

            attack = AttackAction()
            av = attack.can_perform_against(actor, params, ctx)
            if isinstance(av, Allowed):
                attack.execute(actor, params, ctx)
        else:
            # MONSTERS — AI.
            take_monster_turn(
                actor, ctx, is_hostile=is_hostile_from_factions(actor_id, enc.factions)
            )

        enc.end_turn()

    # Бой сошёлся в пределах лимита.
    assert enc.is_concluded is True, (
        f"бой не сошёлся за {_MAX_TURNS} ходов; "
        f"warrior_hp={warrior.hit_points.current}, "
        f"goblin_hp={goblin.hit_points.current}"
    )

    # Проверяем итоговое событие.
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY
    assert warrior.id in ended.survivors
    assert goblin.id not in ended.survivors

    # Базовая событийная цепочка присутствует:
    # InitiativeRolled → TurnStarted (warrior) → AttackResolved → EncounterEnded.
    types = [type(e).__name__ for e in captured]
    assert types.index("InitiativeRolled") < types.index("TurnStarted")
    assert types.index("TurnStarted") < types.index("AttackResolved")
    assert types.index("AttackResolved") < types.index("EncounterEnded")

    # Сценарий: гоблин получил >= 7 урона.
    attack_resolved = [e for e in captured if isinstance(e, AttackResolved)]
    assert attack_resolved[0].downed is True
    assert attack_resolved[0].hit is True
    # Goblin никогда не получил TurnStarted (умер на первом же ходу воина).
    goblin_turns = [e for e in captured if isinstance(e, TurnStarted) and e.actor_id == goblin.id]
    assert goblin_turns == []


@pytest.mark.e2e
def test_smoke_monster_ai_moves_then_attacks() -> None:
    """Сценарий с движением: Воин в (1,2), Гоблин в (4,2) — слишком
    далеко для рукопашной. На своём первом ходу Goblin AI должен
    подойти и атаковать (или начать движение).

    RNG-скрипт:
    - init goblin=18 (+2 DEX) = 20 → ходит первым
    - init warrior=8 (+1)     = 9
    - goblin AI: атака недосягаемая → MoveAction (нет d20), потом
      повторная атака если в reach. После MoveAction Goblin может
      достичь (2,2), reach 5 ft от warrior(1,2) → попытка атаки
      → d20=18 + atk(+4) = 22 vs AC 16 → попал; damage 1d6=4+DEX(+2)=6.
    - warrior d20=20 (crit!) → damage 2d8 + STR(+3)=10+3=13 (если
      выпадет 5+5).
    """
    bf = Battlefield(10, 5)
    warrior = _make_warrior()
    goblin = _make_goblin()
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(goblin.id, Square(4, 2))  # 3 клетки = 15 фт

    rolls = [
        18,  # goblin init: 18+2 = 20 → первый
        8,  # warrior init: 8+1 = 9
        # goblin AI первый ход: подходит, затем атакует.
        # AttackAction.execute → 1 d20 (atk) + 1 d6 (damage) если попал.
        18,  # goblin atk d20: 18+4 = 22 vs 16 → попал
        4,  # goblin damage 1d6=4; +2 DEX = 6
        # warrior ход: critical hit.
        20,  # warrior atk: nat 20 = crit
        5,  # warrior damage 2d8 = 5+...
        5,  # ... + 5 = 10; +3 STR = 13 → goblin 7-13 = 0
    ]
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)

    enc = Encounter(
        participants={warrior.id: warrior, goblin.id: goblin},
        factions={warrior.id: Faction.PARTY, goblin.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    enc.start()

    turns = 0
    while not enc.is_concluded and turns < _MAX_TURNS:
        turns += 1
        actor_id = enc.current_actor_id
        ctx = enc.start_turn()
        actor = enc.participants[actor_id]

        if not actor.is_alive or actor.is_at_zero_hp:
            enc.end_turn()
            continue

        if enc.factions[actor_id] is Faction.PARTY:
            params = weapon_attack_params(actor, goblin.id)
            from dnd.application.dto.action import Allowed

            attack = AttackAction()
            if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
                attack.execute(actor, params, ctx)
        else:
            take_monster_turn(
                actor, ctx, is_hostile=is_hostile_from_factions(actor_id, enc.factions)
            )
        enc.end_turn()

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY

    # Warrior получил урон от goblin'а (movement+attack сработал).
    assert warrior.hit_points.current < warrior.hit_points.maximum

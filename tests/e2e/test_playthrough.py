"""E2E «играбельность»: длинные мульти-турн сценарии.

Не unit-тесты конкретного правила — проверка, что **система** играется
целиком: PC взаимодействует с миром через Intent'ы, AI ходит по своей
логике, бой сходится в разумное время.

Каждый сценарий — детерминированный (ScriptedRNG), чтобы CI был
стабилен.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import (
    AttackResolved,
    EncounterEnded,
    EngineEvent,
    TurnStarted,
)
from dnd.application.dto.ids import CreatureId
from dnd.application.dto.player_intent import (
    AttackIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    MoveIntent,
    PlayerIntent,
)
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.game_runner import GameRunner
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD, SCIMITAR, SHORTBOW
from dnd.interfaces.cli.scripted_provider import ScriptedIntentProvider


def _warrior(cid: str = "warrior") -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _goblin(cid: str, *, weapon=SCIMITAR) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=weapon,
    )


# -- Сценарий 1: 1v2 — Воин против двух гоблинов -----------------------


@pytest.mark.e2e
def test_playthrough_1v2_warrior_vs_two_goblins() -> None:
    """1v2: Воин (HP 20) против двух Гоблинов (HP 7 каждый).

    Скрипт PC: атаковать гоблина-1, потом гоблина-2 (когда первый умрёт).
    AI гоблинов делает то, что умеет.

    RNG подобран так, что Воин убивает обоих за 2-3 хода.
    """
    bf = Battlefield(6, 5)
    warrior = _warrior()
    g1 = _goblin("g1")
    g2 = _goblin("g2")
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(g1.id, Square(2, 2))  # соседний
    bf.place_creature(g2.id, Square(2, 3))  # соседний (диагональ)

    rolls = [
        20,  # warrior init: 21 → первый
        14,  # g1 init: 16
        8,   # g2 init: 10
        # warrior R1: attack g1
        18,  # warrior atk g1: 23 vs 13 → попал
        7,   # damage 7+3=10 → g1 falls
        # g1 falls, AI не ходит. g2 — atk warrior.
        15,  # g2 atk: 15+4=19 vs 16 → попал
        4,   # g2 damage 1d6=4+2=6 → warrior 20-6=14
        # warrior R2: attack g2 (не nat-20 чтобы не было крита)
        19,  # warrior atk g2: 19+5=24 vs 13 → попал
        7,   # damage 7+3=10 → g2 falls
    ]
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={warrior.id: warrior, g1.id: g1, g2.id: g2},
        factions={
            warrior.id: Faction.PARTY,
            g1.id: Faction.MONSTERS,
            g2.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # Интенты PC: всегда атакуем первого живого goblin'а.
    intents = _smart_attack_intents(warrior, enc, captured)
    GameRunner(intent_provider=intents).run(enc)

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY
    # Оба гоблина пали.
    assert g1.is_at_zero_hp
    assert g2.is_at_zero_hp


def _smart_attack_intents(
    actor: Creature, enc: Encounter, captured: list[EngineEvent]
) -> ScriptedIntentProvider:
    """Простой intent-провайдер: атаковать первого живого врага.

    Учитывает ``ctx.action_used`` — если Action уже потрачен, шлёт
    EndTurnIntent, чтобы избежать бесконечного цикла «попытка атаки
    после атаки».
    """
    del actor, captured

    class TargetingProvider:
        def next_intent(
            self,
            actor: Creature,
            ctx,
            encounter: Encounter,
        ) -> PlayerIntent:
            # Уже атаковал в этот ход — заканчиваем.
            if ctx.action_used:
                return EndTurnIntent()
            for cid, cr in encounter.participants.items():
                if cid == actor.id or not cr.is_alive or cr.is_at_zero_hp:
                    continue
                if encounter.factions[cid] is Faction.PARTY:
                    continue
                return AttackIntent(target_id=cid)
            return EndTurnIntent()

    return TargetingProvider()  # type: ignore[return-value]


# -- Сценарий 2: Dodge для выживания ------------------------------------


@pytest.mark.e2e
def test_playthrough_warrior_uses_dodge_when_low_hp() -> None:
    """Воин с низким HP уходит в Dodge — атаки гоблина идут с
    disadvantage, и Воин выживает чтобы добить."""
    bf = Battlefield(5, 5)
    warrior = _warrior()
    g = _goblin("g")
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(g.id, Square(2, 2))

    rolls = [
        20,  # warrior init
        10,  # goblin init
        # warrior R1: Dodge
        # goblin R1: attack warrior с disadvantage (Dodge активен).
        18, 5,  # disadv → min(18, 5) = 5; 5+4=9 vs 16 → промах
        # warrior R2: attack goblin
        18,  # 23 vs 13 → попал
        7,   # damage 10 → goblin falls
    ]
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={warrior.id: warrior, g.id: g},
        factions={warrior.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # Скрипт: Dodge R1, Attack R2.
    intents = ScriptedIntentProvider(
        [
            DodgeIntent(),
            EndTurnIntent(),  # R1 конец
            AttackIntent(target_id=g.id),
            EndTurnIntent(),  # R2 конец
        ]
    )
    GameRunner(intent_provider=intents).run(enc)

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY
    # Goblin промахнулся (его атака не нанесла урон).
    assert warrior.hit_points.current == warrior.hit_points.maximum


# -- Сценарий 3: Dash для отступления + ranged атака -------------------


@pytest.mark.e2e
def test_playthrough_warrior_dashes_to_ranged_position() -> None:
    """Воин с луком отбегает дальше (Dash) и стреляет с дистанции."""
    bf = Battlefield(15, 5)
    archer = Creature.create(
        id_=CreatureId("archer"),
        name="Archer",
        abilities=AbilityScores.of(str_=12, dex=16, con=12, int_=10, wis=10, cha=10),
        max_hp=15,
        armor_class=14,
        speed_ft=30,
        equipped_weapon=SHORTBOW,
    )
    g = _goblin("g")
    bf.place_creature(archer.id, Square(1, 2))
    bf.place_creature(g.id, Square(2, 2))  # рядом

    rolls = [
        20,  # archer init
        8,   # goblin init
        # archer R1: Disengage + Move 6 клеток (без бросков)
        # goblin R1: AI Move 5 шагов + Attack на archer
        15,  # goblin atk d20: 15+4=19 vs 14 → попал
        4,   # goblin damage 1d6=4+2=6 → archer 15-6=9
        # archer R2: ranged Attack
        18,  # atk 18 + 5 = 23 vs 13 → попал
        5,   # damage 5+3=8 → goblin falls
    ]
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={archer.id: archer, g.id: g},
        factions={archer.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # R1: Disengage (чтобы goblin не получил OA при Move) + Dash + Move на 8 клеток.
    # Disengage и Dash оба тратят Action; нельзя за один ход! Возьмём
    # только Disengage + Move 6 клеток (30 фт).
    move_path = tuple(Square(1 + i, 2) for i in range(1, 7))  # 6 клеток вправо
    intents = ScriptedIntentProvider(
        [
            DisengageIntent(),  # не провоцируем
            MoveIntent(path=move_path),
            EndTurnIntent(),
            # R2: атака
            AttackIntent(target_id=g.id),
            EndTurnIntent(),
        ]
    )
    GameRunner(intent_provider=intents).run(enc)

    assert enc.is_concluded is True
    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners is Faction.PARTY
    # Goblin не получил OA (Disengage сработал) — захвачено через события.
    from dnd.application.dto.engine_event import OpportunityAttackProvoked

    assert not any(
        isinstance(e, OpportunityAttackProvoked) for e in captured
    )


# -- Сценарий 4: бой сходится за разумное число ходов ------------------


@pytest.mark.e2e
def test_playthrough_combat_concludes_within_few_turns() -> None:
    """Smoke: realistic combat сходится за ≤ MAX_ROUNDS.

    Используем RealRNG со стабильным seed — это нормальный smoke
    «движок проходит реалистичный бой без застреваний».
    """
    from dnd.composition import build_default_dependencies
    from dnd.infrastructure.rng.real_rng import RealRNG

    bf = Battlefield(5, 5)
    warrior = _warrior()
    g = _goblin("g")
    bf.place_creature(warrior.id, Square(1, 2))
    bf.place_creature(g.id, Square(2, 2))

    rng = RealRNG(seed=42)
    deps = build_default_dependencies(battlefield=bf, rng=rng)
    enc = Encounter(
        participants={warrior.id: warrior, g.id: g},
        factions={warrior.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    enc.deps.event_bus.subscribe(EngineEvent, captured.append)

    GameRunner(
        intent_provider=_smart_attack_intents(warrior, enc, captured)
    ).run(enc)

    assert enc.is_concluded is True
    turn_count = sum(1 for e in captured if isinstance(e, TurnStarted))
    # ≤ 20 turns (10 раундов × 2 actor'а максимум).
    assert turn_count <= 20
    assert any(isinstance(e, AttackResolved) for e in captured)

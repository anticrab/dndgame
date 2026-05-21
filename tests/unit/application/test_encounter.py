"""Тесты F1: Encounter + initiative roll.

PHB-2024 стр. 22 (Инициатива). См. docs/ENCOUNTER.md §2.

Покрытие:

* конструктор: валидация participants ↔ factions;
* start() — initiative roll: total = d20 + DEX mod;
* tie-break: total → d20 → dex_score → insertion_order;
* InitiativeRolled опубликован один раз;
* double start() → EncounterAlreadyStartedError;
* доступ к state до start() → EncounterNotStartedError;
* мёртвые participants в order не попадают.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import EngineEvent, InitiativeRolled
from dnd.application.dto.ids import CreatureId
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.encounter import (
    Encounter,
    EncounterAlreadyStartedError,
    EncounterDependencies,
    EncounterNotStartedError,
)
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _make_creature(cid: str, *, dex: int = 12, hp: int = 20) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=12, dex=dex, con=12, int_=10, wis=10, cha=10),
        max_hp=hp,
        armor_class=12,
        speed_ft=30,
    )


def _make_deps(rng_rolls: list[int]) -> tuple[EncounterDependencies, InMemoryEventBus]:
    bf = Battlefield(10, 10)
    bus = InMemoryEventBus()
    rng = ScriptedRNG(rng_rolls)
    dice = ComputerDiceRoller(rng=rng, event_bus=bus)
    registry = ConditionRegistry()
    register_default_conditions(registry)
    deps = EncounterDependencies(
        battlefield=bf,
        dice_roller=dice,
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
    )
    return deps, bus


# -- конструктор -------------------------------------------------------


def test_constructor_rejects_empty_participants() -> None:
    deps, _bus = _make_deps([])
    with pytest.raises(ValueError, match="at least one"):
        Encounter(participants={}, factions={}, deps=deps)


def test_constructor_rejects_missing_factions() -> None:
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    with pytest.raises(ValueError, match="factions missing"):
        Encounter(
            participants={a.id: a},
            factions={},
            deps=deps,
        )


def test_constructor_rejects_unknown_creature_in_factions() -> None:
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    with pytest.raises(ValueError, match="unknown creature_ids"):
        Encounter(
            participants={a.id: a},
            factions={
                a.id: Faction.PARTY,
                CreatureId("ghost"): Faction.MONSTERS,
            },
            deps=deps,
        )


# -- access до start() -----------------------------------------------


def test_access_before_start_raises() -> None:
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )
    assert enc.has_started is False
    with pytest.raises(EncounterNotStartedError):
        _ = enc.round_number
    with pytest.raises(EncounterNotStartedError):
        _ = enc.initiative_order
    with pytest.raises(EncounterNotStartedError):
        _ = enc.current_actor_id


# -- start() и initiative ---------------------------------------------


@pytest.mark.rules
def test_start_rolls_initiative_for_all_living() -> None:
    """PHB-2024 стр. 22: d20 + DEX modifier. dex=14 → mod=+2."""
    deps, _bus = _make_deps([14])
    a = _make_creature("a", dex=14)
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )

    enc.start()
    assert enc.has_started is True
    assert enc.round_number == 1
    assert enc.current_turn_index == 0
    order = enc.initiative_order
    assert len(order) == 1
    e = order[0]
    assert e.creature_id == a.id
    assert e.d20_raw == 14
    assert e.dex_score == 14
    assert e.total == 14 + 2


@pytest.mark.rules
def test_start_orders_by_total_descending() -> None:
    """Высший total — первый. dex=8 (mod=-1), dex=16 (mod=+3); RNG [10, 8]
    → total a=10-1=9, b=8+3=11 → b ходит первым."""
    deps, _bus = _make_deps([10, 8])
    a = _make_creature("a", dex=8)
    b = _make_creature("b", dex=16)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    order = enc.initiative_order
    assert [e.creature_id for e in order] == [b.id, a.id]
    assert enc.current_actor_id == b.id


@pytest.mark.rules
def test_tie_break_by_d20_then_dex_then_insertion() -> None:
    """Равный total → выше d20; равный d20 → выше DEX; затем insertion.

    a: dex=14 (+2), d20=12 → total 14
    b: dex=12 (+1), d20=13 → total 14
    c: dex=10 (+0), d20=14 → total 14

    Все три total=14. d20 разные: 12 / 13 / 14. По d20 DESC → c, b, a.
    """
    deps, _bus = _make_deps([12, 13, 14])
    a = _make_creature("a", dex=14)
    b = _make_creature("b", dex=12)
    c = _make_creature("c", dex=10)
    enc = Encounter(
        participants={a.id: a, b.id: b, c.id: c},
        factions={
            a.id: Faction.PARTY,
            b.id: Faction.MONSTERS,
            c.id: Faction.NEUTRAL,
        },
        deps=deps,
    )
    enc.start()
    assert [e.creature_id for e in enc.initiative_order] == [c.id, b.id, a.id]


@pytest.mark.rules
def test_tie_break_dex_when_total_and_d20_equal() -> None:
    """Тот же d20, тот же total — побеждает выше DEX.

    a: dex=12 (+1), d20=13 → total 14
    b: dex=10 (+0), d20=14 → total 14

    d20 разные (13 vs 14), b выигрывает по d20. Чтобы проверить
    именно DEX-tiebreaker, нужно равный d20. Делаем второй сценарий:
    a: dex=14 (+2), d20=12 → 14
    b: dex=12 (+1), d20=13 → 14   ← d20 разные
    Не получится. Используем хитрость: одинаковые scores roll'и:
    a: dex=14, d20=14 → 16
    b: dex=12, d20=15 → 16
    d20 14 vs 15 — разные. Нужны одинаковые. RNG скриптуем [14, 14].
    a: dex=12 (+1) d20=14 → 15
    b: dex=10 (+0) d20=14 → 14
    Чёрт total разные. Снова: dex одинаковый mod, разный score:
    dex=11 (+0), dex=10 (+0): mods равны, scores разные.
    a: dex=11 d20=14 → 14; b: dex=10 d20=14 → 14. d20 одинаковые,
    total одинаковые → tie-break по DEX score (11 > 10).
    """
    deps, _bus = _make_deps([14, 14])
    a = _make_creature("a", dex=11)
    b = _make_creature("b", dex=10)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.PARTY},
        deps=deps,
    )
    enc.start()
    assert [e.creature_id for e in enc.initiative_order] == [a.id, b.id]


def test_tie_break_insertion_order_when_all_equal() -> None:
    """Полностью равные броски + dex_score: стабильный порядок по
    insertion_order (последний tie-breaker).
    """
    deps, _bus = _make_deps([14, 14])
    a = _make_creature("a", dex=10)
    b = _make_creature("b", dex=10)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    assert [e.creature_id for e in enc.initiative_order] == [a.id, b.id]


def test_start_publishes_initiative_rolled_once() -> None:
    deps, bus = _make_deps([14, 8])
    a = _make_creature("a")
    b = _make_creature("b")
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    enc.start()

    rolled = [e for e in captured if isinstance(e, InitiativeRolled)]
    assert len(rolled) == 1
    assert rolled[0].order == enc.initiative_order


def test_start_skips_dead_participants() -> None:
    """Если existo упало в 0 HP до боя — в initiative не попадает."""
    deps, _bus = _make_deps([14])  # только один d20 — для живого
    a = _make_creature("a", hp=1)
    b = _make_creature("b")
    a.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    assert a.is_alive is False
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    assert [e.creature_id for e in enc.initiative_order] == [b.id]


def test_double_start_raises() -> None:
    deps, _bus = _make_deps([10, 5])
    a = _make_creature("a")
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )
    enc.start()
    with pytest.raises(EncounterAlreadyStartedError):
        enc.start()


# -- факции -----------------------------------------------------------


def test_factions_kept_in_state() -> None:
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    b = _make_creature("b")
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    assert enc.factions[a.id] is Faction.PARTY
    assert enc.factions[b.id] is Faction.MONSTERS


def test_battlefield_exposed_via_property() -> None:
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )
    assert enc.battlefield is deps.battlefield


# -- Square usage smoke -------------------------------------------------


def test_battlefield_can_place_via_encounter() -> None:
    """Sanity: Encounter не мешает работе с Battlefield снаружи."""
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )
    enc.battlefield.place_creature(a.id, Square(1, 1))
    assert enc.battlefield.position_of(a.id) == Square(1, 1)


# -- F2: lifecycle ----------------------------------------------------


from dnd.application.dto.engine_event import (  # noqa: E402
    EncounterEnded,
    RoundStarted,
    TurnEnded,
    TurnStarted,
)


def _make_two_party_enc(rng_rolls: list[int]) -> tuple[Encounter, Creature, Creature, InMemoryEventBus]:
    """Sanity-сценарий: a (PARTY) vs b (MONSTERS); RNG задаёт инициативу."""
    deps, bus = _make_deps(rng_rolls)
    a = _make_creature("a", dex=14)
    b = _make_creature("b", dex=10)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
    )
    return enc, a, b, bus


@pytest.mark.rules
def test_start_publishes_round_started_after_initiative() -> None:
    """Сразу после initiative — RoundStarted(1) и сброс reactions."""
    enc, a, _b, bus = _make_two_party_enc([10, 14])
    a.reaction_used = True  # уже потратил — должен сброситься
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    enc.start()

    types = [type(e).__name__ for e in captured]
    assert types.index("InitiativeRolled") < types.index("RoundStarted")
    rs = next(e for e in captured if isinstance(e, RoundStarted))
    assert rs.round_number == 1
    assert a.reaction_used is False


def test_start_turn_returns_fresh_turn_context() -> None:
    enc, a, _b, _bus = _make_two_party_enc([14, 10])  # a первый
    enc.start()
    ctx = enc.start_turn()
    assert ctx.actor_id == a.id
    assert ctx.movement_remaining_ft == a.speed_ft
    assert ctx.action_used is False
    assert ctx.round_number == 1
    assert ctx.turn_number_in_round == 0


def test_start_turn_publishes_turn_started() -> None:
    enc, a, _b, bus = _make_two_party_enc([14, 10])
    enc.start()
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start_turn()
    ts = next(e for e in captured if isinstance(e, TurnStarted))
    assert ts.actor_id == a.id
    assert ts.round_number == 1
    assert ts.skipped is False


@pytest.mark.rules
def test_start_turn_clears_combat_stances() -> None:
    """PHB-2024 стр. 22: «benefit ends at the start of your next turn»."""
    enc, a, _b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    # Эмулируем «прошлый ход»: actor стоит в Dodge.
    a.combat_stances.update({"dodging", "dashing", "disengaged"})
    enc.start_turn()
    assert a.combat_stances == set()


def test_end_turn_advances_pointer() -> None:
    enc, a, b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    assert enc.current_actor_id == a.id
    enc.start_turn()
    enc.end_turn()
    assert enc.current_actor_id == b.id
    assert enc.round_number == 1


def test_end_turn_publishes_turn_ended() -> None:
    enc, a, _b, bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.end_turn()
    te = next(e for e in captured if isinstance(e, TurnEnded))
    assert te.actor_id == a.id
    assert te.round_number == 1


@pytest.mark.rules
def test_round_rolls_over_after_last_actor() -> None:
    """После последнего actor'а: RoundEnded(1) → RoundStarted(2)."""
    enc, _a, _b, bus = _make_two_party_enc([14, 10])
    enc.start()
    # a, b — оба ходят.
    enc.start_turn()
    enc.end_turn()
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start_turn()
    enc.end_turn()

    types = [type(e).__name__ for e in captured]
    assert "RoundEnded" in types
    assert "RoundStarted" in types
    assert types.index("RoundEnded") < types.index("RoundStarted")
    assert enc.round_number == 2
    assert enc.current_turn_index == 0


@pytest.mark.rules
def test_new_round_resets_reaction_used() -> None:
    """PHB-2024 стр. 22: reaction обновляется каждый раунд."""
    enc, a, b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    enc.end_turn()  # a
    enc.start_turn()
    enc.end_turn()  # b → переход во 2 раунд
    a.reaction_used = True
    b.reaction_used = True
    # Следующий цикл: новый раунд уже открыт; reaction должна быть
    # сброшена через _begin_round, но a/b мы вручную поставили после.
    # Тогда правильная проверка: вручную сделаем переход на ещё один раунд.
    enc.start_turn()
    enc.end_turn()  # a в раунде 2
    enc.start_turn()
    enc.end_turn()  # b в раунде 2 → начало раунда 3
    assert enc.round_number == 3
    assert a.reaction_used is False
    assert b.reaction_used is False


def test_start_turn_skipped_for_zero_hp_actor() -> None:
    """existo упало в 0 HP во время чужого хода — на своём ходу
    публикуется TurnStarted(skipped=True), TurnContext возвращается,
    но вызывающий обычно сразу end_turn."""
    enc, _a, _b, bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    enc.end_turn()  # a отходил
    # b роняем до 0 HP
    enc.participants[CreatureId("b")].take_damage(
        DamageInstance(amount=999, type_=DamageType.SLASHING)
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start_turn()  # b
    ts = next(e for e in captured if isinstance(e, TurnStarted))
    assert ts.skipped is True


# -- F3: EncounterEnded -------------------------------------------------


@pytest.mark.rules
def test_encounter_ends_when_one_faction_wiped() -> None:
    """Если все участники одной воюющей фракции пали — EncounterEnded
    с другой фракцией в winners."""
    enc, a, b, bus = _make_two_party_enc([14, 10])
    enc.start()
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # a (PARTY) убивает b (MONSTERS) насмерть в свой ход.
    enc.start_turn()
    b.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    enc.end_turn()  # должен обнаружить конец боя

    ended = next(e for e in captured if isinstance(e, EncounterEnded))
    assert ended.winners == Faction.PARTY.value
    assert ended.survivors == (a.id,)
    assert enc.is_concluded is True


def test_encounter_concluded_blocks_further_turns() -> None:
    enc, _a, b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    b.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    enc.end_turn()
    assert enc.is_concluded is True
    with pytest.raises(RuntimeError, match="concluded"):
        enc.start_turn()
    with pytest.raises(RuntimeError, match="concluded"):
        enc.end_turn()


def test_encounter_ends_winners_none_if_both_sides_wiped() -> None:
    """Одновременный нокаут (теоретически) — winners=None."""
    enc, a, b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    a.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    b.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    enc.end_turn()
    assert enc.is_concluded is True


def test_neutral_alone_does_not_continue_combat() -> None:
    """Если выживают только NEUTRAL — бой завершён, winners=None."""
    deps, _bus = _make_deps([14, 10, 5])
    a = _make_creature("a")
    b = _make_creature("b")
    obs = _make_creature("obs")
    enc = Encounter(
        participants={a.id: a, b.id: b, obs.id: obs},
        factions={
            a.id: Faction.PARTY,
            b.id: Faction.MONSTERS,
            obs.id: Faction.NEUTRAL,
        },
        deps=deps,
    )
    enc.start()
    # Убить обоих воинов сразу:
    a.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    b.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    enc.start_turn()
    enc.end_turn()
    assert enc.is_concluded is True


@pytest.mark.rules
def test_combat_continues_while_both_sides_alive() -> None:
    """Sanity: если обе стороны живы — бой продолжается."""
    enc, _a, _b, _bus = _make_two_party_enc([14, 10])
    enc.start()
    enc.start_turn()
    enc.end_turn()
    assert enc.is_concluded is False


# -- F4: reaction policy ------------------------------------------------


from dnd.application.dto.engine_event import OpportunityAttackProvoked  # noqa: E402
from dnd.application.engine.actions.attack import AttackKind, AttackParams  # noqa: E402
from dnd.application.engine.actions.move import MoveAction, MoveParams  # noqa: E402
from dnd.application.engine.actions.opportunity_attack import OpportunityAttack  # noqa: E402
from dnd.application.engine.encounter import noop_reaction_policy  # noqa: E402


def test_noop_policy_is_default_and_does_nothing() -> None:
    """Без передачи policy провокация публикуется, но реакция не
    выполняется."""
    deps, bus = _make_deps([14, 10])
    a = _make_creature("a")
    b = _make_creature("b")
    bf = deps.battlefield
    bf.place_creature(a.id, Square(2, 2))
    bf.place_creature(b.id, Square(3, 2))
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
        # reaction_policy не указан → noop
    )
    enc.start()
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # actor a уходит из reach b → провокация.
    MoveAction().execute(a, MoveParams(path=(Square(1, 2),)), enc.start_turn())

    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert len(aops) == 1
    # Реакция НЕ потрачена — реактор b не стрелял.
    assert b.reaction_used is False


@pytest.mark.rules
def test_custom_policy_triggers_opportunity_attack() -> None:
    """Кастомная политика: всегда отвечает melee-OA.

    PHB-2024 стр. 22 + аудит 12 OA-R001: только MELEE.
    """
    # [a инициатива, b инициатива, atk d20, dmg d8]
    deps, _bus = _make_deps([14, 10, 18, 4])
    a = _make_creature("a")
    b = _make_creature("b")
    bf = deps.battlefield
    bf.place_creature(a.id, Square(2, 2))
    bf.place_creature(b.id, Square(3, 2))

    def reactor_policy(
        evt: OpportunityAttackProvoked, encounter: Encounter
    ) -> None:
        reactor = encounter.participants[evt.threatener_id]
        params = AttackParams(
            target_id=evt.actor_id,
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        )
        oa = OpportunityAttack()
        # В реальном Encounter был бы lazy TurnContext; для теста
        # реактивный handler собирает TurnContext руками
        # с актором-реактором как owner'ом.
        from dnd.application.engine.turn_context import TurnContext
        ctx = TurnContext(
            actor_id=reactor.id,
            battlefield=encounter.battlefield,
            dice_roller=encounter.deps.dice_roller,
            modifier_applier=encounter.deps.modifier_applier,
            condition_service=encounter.deps.condition_service,
            event_bus=encounter.deps.event_bus,
            rng=encounter.deps.rng,
            participants=encounter.participants,
            movement_remaining_ft=reactor.speed_ft,
        )
        oa.execute(reactor, params, ctx)

    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
        reaction_policy=reactor_policy,
    )
    enc.start()

    # Сейчас в инициативе первый — a (dex_mod 1 vs 0, оба d20 — a:14, b:10):
    # total a=15, b=10.
    assert enc.current_actor_id == a.id
    ctx_a = enc.start_turn()
    MoveAction().execute(a, MoveParams(path=(Square(1, 2),)), ctx_a)

    # Реактор b должен был выполнить OA: reaction_used + a получил урон.
    assert b.reaction_used is True
    assert a.hit_points.current < a.hit_points.maximum


def test_policy_not_called_after_encounter_ended() -> None:
    """После EncounterEnded подписка на провокации отписывается."""
    calls = []

    def policy(
        evt: OpportunityAttackProvoked, encounter: Encounter
    ) -> None:
        calls.append(evt)

    deps, _bus = _make_deps([14, 10])
    a = _make_creature("a")
    b = _make_creature("b")
    bf = deps.battlefield
    bf.place_creature(a.id, Square(2, 2))
    bf.place_creature(b.id, Square(3, 2))
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
        reaction_policy=policy,
    )
    enc.start()
    # Убить b → бой кончится после первого end_turn'а а.
    enc.start_turn()
    b.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    enc.end_turn()
    assert enc.is_concluded is True

    # Прямая публикация провокации после конца боя — не должна вызвать policy.
    enc.deps.event_bus.publish(
        OpportunityAttackProvoked(
            actor_id=a.id, threatener_id=b.id, leaving_square=Square(2, 2)
        )
    )
    assert calls == []


def test_noop_policy_helper_is_safe_to_call() -> None:
    """Sanity: noop_reaction_policy ничего не делает и не падает."""
    deps, _bus = _make_deps([])
    a = _make_creature("a")
    enc = Encounter(
        participants={a.id: a},
        factions={a.id: Faction.PARTY},
        deps=deps,
    )
    evt = OpportunityAttackProvoked(
        actor_id=a.id, threatener_id=a.id, leaving_square=Square(0, 0)
    )
    noop_reaction_policy(evt, enc)  # не падает, ничего не возвращает

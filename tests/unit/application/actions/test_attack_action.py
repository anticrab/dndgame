"""Тесты AttackAction — атака оружием.

Источник правил: «Книга Игрока 2024» стр. 25 (Совершение атаки,
Укрытие, Критическое попадание).

Покрытие:

* can_perform / can_perform_against — все ForbiddenReason'ы;
* execute: hit/miss/crit/natural-1; cover в effective_AC; ranged
  long-range disadvantage; resistance цели; downed на lethal;
* публикация AttackRolled / DamageDealt / AttackResolved в нужном
  порядке.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.action import (
    ActionEconomyCost,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    DamageDealt,
    EngineEvent,
)
from dnd.application.engine.actions.attack import (
    AttackAction,
    AttackKind,
    AttackParams,
)
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import ConditionId, CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import HIGH_COVER, WALL
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG

# Square — frozen, его можно использовать как singleton-дефолт.
_DEFAULT_ATTACKER_POS = Square(1, 1)
_DEFAULT_TARGET_POS = Square(2, 1)

# -- Фабрики ------------------------------------------------------------


def _make_fighter(creature_id: str = "fighter", *, ac: int = 15) -> Creature:
    return Creature.create(
        id_=CreatureId(creature_id),
        name="Fighter",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=ac,
        speed_ft=30,
    )


def _make_goblin(creature_id: str = "goblin", *, hp: int = 7, ac: int = 14) -> Creature:
    return Creature.create(
        id_=CreatureId(creature_id),
        name="Goblin",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=hp,
        armor_class=ac,
        speed_ft=30,
    )


def _setup(
    *,
    rng_rolls: list[int],
    attacker_pos: Square = _DEFAULT_ATTACKER_POS,
    target_pos: Square = _DEFAULT_TARGET_POS,
    attacker: Creature | None = None,
    target: Creature | None = None,
    bf_size: tuple[int, int] = (10, 10),
) -> tuple[Creature, Creature, TurnContext, InMemoryEventBus]:
    """Поднять минимальный «бой»: два существа, поле, EventBus, шины."""
    if attacker is None:
        attacker = _make_fighter()
    if target is None:
        target = _make_goblin()

    bf = Battlefield(*bf_size)
    bf.place_creature(attacker.id, attacker_pos)
    bf.place_creature(target.id, target_pos)

    bus = InMemoryEventBus()
    rng = ScriptedRNG(rng_rolls)
    dice = ComputerDiceRoller(rng=rng, event_bus=bus)

    registry = ConditionRegistry()
    register_default_conditions(registry)

    ctx = TurnContext(
        actor_id=attacker.id,
        battlefield=bf,
        dice_roller=dice,
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants={attacker.id: attacker, target.id: target},
        movement_remaining_ft=attacker.speed_ft,
    )
    return attacker, target, ctx, bus


def _params(target_id: str, **overrides: object) -> AttackParams:
    defaults: dict[str, object] = {
        "target_id": CreatureId(target_id),
        "kind": AttackKind.MELEE,
        "attack_bonus": 5,
        "damage_expr": "1d8+3",
        "damage_type": DamageType.SLASHING,
        "range_ft": 5,
        "long_range_ft": 0,
    }
    defaults.update(overrides)
    return AttackParams(**defaults)  # type: ignore[arg-type]


def _capture(bus: InMemoryEventBus) -> list[EngineEvent]:
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    return captured


# -- can_perform / can_perform_against ----------------------------------


def test_can_perform_allowed_when_fresh_turn() -> None:
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    assert isinstance(AttackAction().can_perform(attacker, ctx), Allowed)


def test_can_perform_no_economy_left() -> None:
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    ctx.spend(ActionEconomyCost.ACTION)
    av = AttackAction().can_perform(attacker, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_ECONOMY_LEFT


@pytest.mark.rules
@pytest.mark.parametrize(
    "condition_id",
    ["incapacitated", "stunned", "paralyzed", "unconscious"],
)
def test_can_perform_blocked_by_condition(condition_id: str) -> None:
    """PHB-2024 стр. 367: Incapacitated → нет actions."""
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    attacker.apply_condition(ConditionId(condition_id))
    av = AttackAction().can_perform(attacker, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CONDITION_BLOCKS_ACTION
    assert av.details == condition_id


def test_against_no_target_in_participants() -> None:
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    av = AttackAction().can_perform_against(
        attacker, _params("ghost"), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_VALID_TARGETS


@pytest.mark.rules
def test_against_self_target_forbidden() -> None:
    """Аудит 16 AT-R-NEW-003: атака на самого себя — Forbidden."""
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    av = AttackAction().can_perform_against(
        attacker, _params(attacker.id), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.SELF_TARGET


@pytest.mark.rules
def test_against_dead_target_forbidden() -> None:
    """Аудит 16 AT-R-NEW-004: атака на цель с 0 HP — Forbidden."""
    from dnd.domain.values.damage import DamageInstance

    attacker, target, ctx, _ = _setup(rng_rolls=[])
    target.take_damage(DamageInstance(amount=999, type_=DamageType.SLASHING))
    assert target.is_at_zero_hp
    av = AttackAction().can_perform_against(
        attacker, _params(target.id), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.TARGET_DOWN


@pytest.mark.rules
def test_against_dying_pc_allowed_to_finish() -> None:
    """Добивание лежачего спасаемого PC разрешено: удар в упор = авто-крит
    (PHB-2024 стр. 27). Иначе соло-PC лежит стабильным, а бой висит до
    round-limit (этап D — «ничья-зависание»)."""
    from dnd.domain.values.death_save_state import DeathSaveState

    pc = _make_goblin("downed_pc")
    pc.uses_death_saves = True
    pc.hit_points = pc.hit_points.take_damage(pc.hit_points.maximum)  # → 0 HP
    pc.death_saves = DeathSaveState()  # dying, ещё не мёртв
    attacker, target, ctx, _ = _setup(rng_rolls=[], target=pc)

    assert target.is_at_zero_hp and target.death_saves is not None
    assert not target.death_saves.is_dead
    av = AttackAction().can_perform_against(attacker, _params(target.id), ctx)
    assert isinstance(av, Allowed)


@pytest.mark.rules
def test_against_no_line_of_sight() -> None:
    """Стена между атакующим и целью блокирует LoS."""
    attacker, target, ctx, _ = _setup(
        rng_rolls=[],
        attacker_pos=Square(0, 0),
        target_pos=Square(4, 0),
    )
    ctx.battlefield.set_terrain(Square(2, 0), WALL)
    av = AttackAction().can_perform_against(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_LINE_OF_SIGHT


@pytest.mark.rules
def test_against_total_cover_forbidden() -> None:
    """PHB-2024 стр. 25: цель за полной защитой нельзя выбрать целью."""
    attacker, target, ctx, _ = _setup(
        rng_rolls=[],
        attacker_pos=Square(0, 0),
        target_pos=Square(3, 0),
    )
    # Цель стоит на клетке-стене (нестандартно, но движок должен это
    # отлавливать): cover_against → TOTAL.
    ctx.battlefield.set_terrain(Square(3, 0), WALL)
    av = AttackAction().can_perform_against(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.TARGET_HAS_TOTAL_COVER


@pytest.mark.rules
def test_against_out_of_range_melee() -> None:
    """Melee reach=5 фт; через 2 клетки (10 фт) — нельзя."""
    attacker, target, ctx, _ = _setup(
        rng_rolls=[],
        attacker_pos=Square(0, 0),
        target_pos=Square(2, 0),
    )
    av = AttackAction().can_perform_against(
        attacker, _params(target.id, range_ft=5), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.OUT_OF_RANGE


@pytest.mark.rules
def test_against_out_of_long_range_ranged() -> None:
    """RANGED: дальше long_range_ft — OUT_OF_RANGE."""
    attacker, target, ctx, _ = _setup(
        rng_rolls=[],
        attacker_pos=Square(0, 0),
        target_pos=Square(9, 0),  # 45 фт
        bf_size=(20, 5),
    )
    av = AttackAction().can_perform_against(
        attacker,
        _params(
            target.id,
            kind=AttackKind.RANGED,
            range_ft=30,
            long_range_ft=40,
        ),
        ctx,
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.OUT_OF_RANGE


def test_against_allowed_when_all_conditions_met() -> None:
    attacker, target, ctx, _ = _setup(rng_rolls=[])
    av = AttackAction().can_perform_against(
        attacker, _params(target.id), ctx
    )
    assert isinstance(av, Allowed)


# -- execute: hit / miss / crit ----------------------------------------


def test_execute_hit_publishes_three_events_in_order() -> None:
    """d20=14 + bonus=5 = 19 vs AC 14 → попадание. Урон d8+3 → 5+3=8."""
    target = _make_goblin(hp=20)  # достаточно HP, чтобы не упал от 8
    attacker, target, ctx, bus = _setup(
        rng_rolls=[14, 5], target=target
    )
    captured = _capture(bus)

    outcome = AttackAction().execute(attacker, _params(target.id), ctx)

    # ActionOutcome
    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.ACTION
    assert outcome.events_published == (
        "attack.rolled",
        "damage.dealt",
        "attack.resolved",
    )

    # Шина: RollIssued/Applied×2 (atk+dmg) + 3 наших события.
    # Проверяем именно ПОРЯДОК и ТИПЫ ключевых событий.
    main_events = [e for e in captured if isinstance(
        e, (AttackRolled, DamageDealt, AttackResolved)
    )]
    assert [type(e).__name__ for e in main_events] == [
        "AttackRolled",
        "DamageDealt",
        "AttackResolved",
    ]

    atk = main_events[0]
    assert isinstance(atk, AttackRolled)
    assert atk.hit is True
    assert atk.is_critical_hit is False
    assert atk.is_critical_miss is False
    assert atk.effective_ac == 14

    dmg = main_events[1]
    assert isinstance(dmg, DamageDealt)
    assert dmg.final_amount == 8
    assert dmg.damage_type is DamageType.SLASHING

    res = main_events[2]
    assert isinstance(res, AttackResolved)
    assert res.hit is True
    assert res.downed is False
    assert target.hit_points.current == target.hit_points.maximum - 8


def test_execute_miss_publishes_no_damage_event() -> None:
    """d20=7 + 5 = 12 vs AC 14 → промах."""
    attacker, target, ctx, bus = _setup(rng_rolls=[7])
    captured = _capture(bus)

    outcome = AttackAction().execute(attacker, _params(target.id), ctx)

    assert outcome.events_published == ("attack.rolled", "attack.resolved")
    main_events = [e for e in captured if isinstance(
        e, (AttackRolled, DamageDealt, AttackResolved)
    )]
    assert [type(e).__name__ for e in main_events] == [
        "AttackRolled",
        "AttackResolved",
    ]
    assert target.hit_points.current == target.hit_points.maximum  # цела


@pytest.mark.rules
def test_execute_natural_20_is_critical_hit() -> None:
    """PHB-2024 стр. 25: natural 20 = критическое попадание (всегда попадает,
    кубы урона удваиваются)."""
    # AC цели 50 — без крита промахнулись бы.
    target = _make_goblin(ac=50, hp=50)
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[20, 4, 5],
        attacker=attacker,
        target=target,
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    main = [e for e in captured if isinstance(
        e, (AttackRolled, DamageDealt, AttackResolved)
    )]
    atk = main[0]
    assert isinstance(atk, AttackRolled)
    assert atk.is_critical_hit is True
    assert atk.hit is True

    dmg = main[1]
    assert isinstance(dmg, DamageDealt)
    # crit удваивает кубы: 1d8 → 2d8 = 4+5 = 9, +mod 3 = 12.
    assert dmg.raw_amount == 12
    assert dmg.is_critical is True


@pytest.mark.rules
def test_execute_natural_1_is_automatic_miss() -> None:
    """PHB-2024 стр. 25: natural 1 = автоматический промах."""
    # AC цели 1 — без крит-фейла попали бы (d20=1 + 5 = 6 > 1, но natural-1
    # автомисс по правилу).
    target = _make_goblin(ac=1)
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(rng_rolls=[1], attacker=attacker, target=target)
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    main = [e for e in captured if isinstance(
        e, (AttackRolled, DamageDealt, AttackResolved)
    )]
    atk = main[0]
    assert isinstance(atk, AttackRolled)
    assert atk.is_critical_miss is True
    assert atk.hit is False
    assert target.hit_points.current == target.hit_points.maximum
    # damage не публикуется
    assert not any(isinstance(e, DamageDealt) for e in main)


# -- cover в effective_AC ----------------------------------------------


@pytest.mark.rules
def test_execute_cover_adds_to_effective_ac() -> None:
    """PHB-2024 стр. 25: three-quarters cover = +5 к КД."""
    attacker, target, ctx, bus = _setup(
        rng_rolls=[15, 4],
        attacker_pos=Square(0, 0),
        target_pos=Square(4, 0),
    )
    ctx.battlefield.set_terrain(Square(2, 0), HIGH_COVER)  # three_quarters
    captured = _capture(bus)

    AttackAction().execute(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.effective_ac == 14 + 5
    # d20=15 + bonus=5 = 20 vs AC 19 → попал.
    assert atk.hit is True


# -- ranged disadvantage за long_range ---------------------------------


@pytest.mark.rules
def test_execute_ranged_long_range_imposes_disadvantage() -> None:
    """PHB-2024 стр. 25: дальше нормальной дальности (но ближе long) —
    атаки с помехой."""
    attacker, target, ctx, bus = _setup(
        rng_rolls=[18, 14, 5],
        attacker_pos=Square(0, 0),
        target_pos=Square(8, 0),  # 40 фт = за range, в long_range
        bf_size=(20, 5),
    )
    captured = _capture(bus)

    AttackAction().execute(
        attacker,
        _params(
            target.id,
            kind=AttackKind.RANGED,
            range_ft=30,
            long_range_ft=60,
        ),
        ctx,
    )
    # При disadvantage берётся меньший d20 — это 14, +5 = 19 vs AC 14.
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.hit is True
    # Если бы не было disadvantage, итог тот же; но мы проверяем,
    # что disadvantage реально применился — d20=14 на damage не должен уйти.
    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    assert dmg.raw_amount == 5 + 3  # 1d8=5, +mod 3


# -- downed --------------------------------------------------------------


def test_execute_lethal_damage_marks_downed() -> None:
    """Если урон сводит цель в 0 HP — AttackResolved.downed=True."""
    target = _make_goblin(hp=3)
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[20, 5, 4],
        attacker=attacker,
        target=target,
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    res = next(e for e in captured if isinstance(e, AttackResolved))
    assert res.hit is True
    assert res.downed is True
    assert target.is_at_zero_hp is True


# -- интеграция с экономикой ------------------------------------------


def test_execute_spends_action() -> None:
    attacker, target, ctx, _ = _setup(rng_rolls=[7])
    AttackAction().execute(attacker, _params(target.id), ctx)
    assert ctx.action_used is True


def test_execute_rejects_wrong_params_type() -> None:
    from dnd.application.dto.action import NoParams

    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    with pytest.raises(TypeError, match="AttackParams"):
        AttackAction().execute(attacker, NoParams(), ctx)


# -- параметры ----------------------------------------------------------


def test_attack_params_frozen_and_validated() -> None:
    from pydantic import ValidationError

    p = _params("g")
    with pytest.raises(ValidationError):
        p.target_id = CreatureId("other")  # type: ignore[misc]
    with pytest.raises(ValidationError):
        AttackParams(  # type: ignore[call-arg]
            target_id=CreatureId("g"),
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=3,  # < 5, валидация Field(ge=5)
        )


# -- AT-R001 фикс: damage modifier через ModifierBag --------------------


def _modifier_bag_with_damage_bonus(numeric: int = 0, extra_dice: str | None = None):
    """Утилита: построить ModifierBag для actor'а с указанным DAMAGE_ROLL
    модификатором (numeric и/или extra_dice)."""
    from dnd.domain.values.modifiers import (
        DiceBonusEffect,
        Modifier,
        ModifierSourceKind,
        ModifierTargetKind,
        NumericBonusEffect,
        StackingPolicy,
    )

    bag = ModifierBag()
    if numeric:
        bag.add(
            Modifier(
                owner_id=CreatureId("fighter"),
                source_id="magic_weapon",
                source_kind=ModifierSourceKind.ITEM,
                target_kind=ModifierTargetKind.DAMAGE_ROLL,
                effect=NumericBonusEffect(value=numeric),
                stacking=StackingPolicy.STACK_ALL,
                stack_key="",
            )
        )
    if extra_dice:
        bag.add(
            Modifier(
                owner_id=CreatureId("fighter"),
                source_id="sneak_attack",
                source_kind=ModifierSourceKind.FEATURE,
                target_kind=ModifierTargetKind.DAMAGE_ROLL,
                effect=DiceBonusEffect(dice=extra_dice),
                stacking=StackingPolicy.STACK_ALL,
                stack_key="",
            )
        )
    return bag


@pytest.mark.rules
def test_execute_magic_weapon_plus_1_damage_does_not_crash() -> None:
    """AT-R001 (S0): damage_expr='1d8+3' + numeric_bonus=+1 от магии
    раньше падал DiceParseError на '1d8+3+1'. Фикс через
    dataclasses.replace(modifier=base.modifier + adj.numeric_bonus).

    d20=18+5=23 vs AC 14 → попадание; d8=5; итог 5 + 3 + 1 = 9.
    """
    target = _make_goblin(hp=20)
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[18, 5], attacker=attacker, target=target
    )
    ctx.modifier_applier = ModifierApplier(
        _modifier_bag_with_damage_bonus(numeric=1)
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    assert dmg.final_amount == 9


# -- AT-R002: крит удваивает extra_dice ---------------------------------


@pytest.mark.rules
def test_critical_hit_doubles_extra_dice() -> None:
    """PHB-2024 стр. 25: на крите удваиваются ВСЕ кости урона, включая
    Sneak Attack / Divine Smite / Hex. ComputerDiceRoller прокидывает
    crit=True в extra_dice — проверяем, что в EngineRollResult два
    броска от extra_dice (1d6 → 2d6) даже когда основные кубы уже
    удвоены.

    RNG: [20] for d20 attack (nat 20 = crit) +
         [4, 5] for damage 1d8 → удвоено 2d8 +
         [2, 6] for extra 1d6 → удвоено 2d6.
    """
    target = _make_goblin(hp=50, ac=50)  # AC 50 — без крита не попали бы
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[20, 4, 5, 2, 6], attacker=attacker, target=target
    )
    ctx.modifier_applier = ModifierApplier(
        _modifier_bag_with_damage_bonus(extra_dice="1d6")
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    # Основные кубы: 2d8 = 4+5 = 9, +mod 3 = 12
    # Extra: 2d6 = 2+6 = 8
    # Итого: 12 + 8 = 20.
    assert dmg.raw_amount == 20
    assert dmg.is_critical is True


# -- AT-R003: half cover (+2) -------------------------------------------


@pytest.mark.rules
def test_half_cover_adds_2_to_effective_ac() -> None:
    """PHB-2024 стр. 25: half cover = +2 к КД."""
    attacker, target, ctx, bus = _setup(
        rng_rolls=[15, 4],
        attacker_pos=Square(0, 0),
        target_pos=Square(4, 0),
    )
    from dnd.domain.values.terrain import LOW_COVER

    ctx.battlefield.set_terrain(Square(2, 0), LOW_COVER)
    captured = _capture(bus)

    AttackAction().execute(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.effective_ac == 14 + 2
    # d20=15 + 5 = 20 vs 16 → попал.
    assert atk.hit is True


# -- AT-G001: concentration save ----------------------------------------


@pytest.mark.rules
def test_concentration_save_dc_propagated_when_hit() -> None:
    """PHB-2024 стр. 352: получив урон, концентрация требует CON-save с
    DC = max(10, damage // 2). AttackAction передаёт это поле в
    AttackResolved для движка."""
    target = _make_goblin(hp=30)
    from dnd.domain.values.ids import SpellId

    target.concentration = SpellId("bless")
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[18, 5], attacker=attacker, target=target
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    res = next(e for e in captured if isinstance(e, AttackResolved))
    # damage = 5 + 3 = 8 → DC = max(10, 4) = 10
    assert res.concentration_save_dc == 10
    assert res.downed is False


# -- AT-G002: execute не валидирует повторно ----------------------------


def test_execute_does_not_re_validate_after_can_perform() -> None:
    """ACTIONS.md §6: execute не проверяет повторно. Сценарий:
    after_can_perform_against → ставим WALL между attacker и target,
    вызываем execute. По контракту execute идёт «как есть» — атака
    случается, даже если LoS теперь нет.

    Этот тест **документирует** контракт, а не баг.
    """
    target = _make_goblin(hp=20)
    attacker, _, ctx, bus = _setup(
        rng_rolls=[18, 5],
        attacker_pos=Square(0, 0),
        target_pos=Square(4, 0),
        target=target,
    )
    av = AttackAction().can_perform_against(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )
    assert isinstance(av, Allowed)
    # Ставим стену МЕЖДУ — теперь по правилам атака бы не прошла.
    ctx.battlefield.set_terrain(Square(2, 0), WALL)

    captured = _capture(bus)
    outcome = AttackAction().execute(
        attacker,
        _params(target.id, kind=AttackKind.RANGED, range_ft=60),
        ctx,
    )

    # Execute не запрещает; атака состоялась.
    assert outcome.success is True
    assert any(isinstance(e, AttackRolled) for e in captured)


def test_execute_raises_when_target_not_in_participants() -> None:
    """AT-A001: execute страхует contract violation чётким RuntimeError,
    а не KeyError."""
    attacker, _target, ctx, _ = _setup(rng_rolls=[])
    bad_params = _params("phantom")
    with pytest.raises(RuntimeError, match="contract violation"):
        AttackAction().execute(attacker, bad_params, ctx)


# -- AT-G004: полный FIFO порядок событий ------------------------------


def test_full_event_fifo_order_on_hit() -> None:
    """ENGINE.md §5.2 + §7.4: одно попадание даёт ровно такую цепочку
    типов событий в шине:

        RollIssued (atk d20) → RollApplied (atk d20) → AttackRolled →
        RollIssued (damage)  → RollApplied (damage)  → DamageDealt →
        AttackResolved

    Если кто-то поменяет порядок publish — тест поймает.
    """
    from dnd.application.dto.engine_event import RollApplied, RollIssued

    target = _make_goblin(hp=20)
    attacker, _, ctx, bus = _setup(
        rng_rolls=[14, 5], target=target
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    types = [type(e).__name__ for e in captured]
    # Удаляем только наши «бизнес»-события и Roll*; tags/other нет.
    assert types == [
        "RollIssued",
        "RollApplied",
        "AttackRolled",
        "RollIssued",
        "RollApplied",
        "DamageDealt",
        "AttackResolved",
    ]
    # Дополнительно: RollIssued и RollApplied первой пары — один roll_id.
    roll_issued_atk = next(e for e in captured if isinstance(e, RollIssued))
    roll_applied_atk = next(e for e in captured if isinstance(e, RollApplied))
    assert roll_issued_atk.result.roll_id == roll_applied_atk.result.roll_id


# -- AT-G005: resistance / vulnerability цели ---------------------------


@pytest.mark.rules
def test_target_resistance_halves_damage() -> None:
    """PHB-2024 стр. 26: resistant ×½ (floor). Goblin со resistant
    slashing получает 8 → 4."""
    target = _make_goblin(hp=30)
    # Resistance хранится как множество строковых значений DamageType.value.
    object.__setattr__(target, "resistances", frozenset({DamageType.SLASHING.value}))
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[18, 5], attacker=attacker, target=target
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    assert dmg.raw_amount == 8  # 5 + 3 (raw — до resist)
    assert dmg.final_amount == 4  # после resistance ×½


@pytest.mark.rules
def test_target_immunity_zeroes_damage() -> None:
    target = _make_goblin(hp=30)
    object.__setattr__(target, "immunities", frozenset({DamageType.SLASHING.value}))
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[18, 5], attacker=attacker, target=target
    )
    captured = _capture(bus)

    AttackAction().execute(attacker, _params(target.id), ctx)

    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    assert dmg.final_amount == 0
    assert target.hit_points.current == target.hit_points.maximum


# -- VS-R002 (audit 14): clamp damage>=0 ------------------------------


@pytest.mark.rules
def test_negative_damage_modifier_clamped_to_zero() -> None:
    """PHB-2024 стр. 26: «минимальный урон». 1d4-2, roll=1 → total=-1
    клампим к 0. Аудит 14 VS-R002.
    """
    target = _make_goblin(hp=20)
    attacker = _make_fighter()
    _, _, ctx, bus = _setup(
        rng_rolls=[18, 1],  # atk=18 → попал; damage=1
        attacker=attacker, target=target,
    )
    # Делаем разбойного «слабого» с STR=6 (mod=-2), используем 1d4-2
    weak_params = AttackParams(
        target_id=target.id,
        kind=AttackKind.MELEE,
        attack_bonus=5,
        damage_expr="1d4-2",  # 1-2 = -1
        damage_type=DamageType.SLASHING,
        range_ft=5,
    )
    captured = _capture(bus)
    AttackAction().execute(attacker, weak_params, ctx)

    dmg = next(e for e in captured if isinstance(e, DamageDealt))
    assert dmg.raw_amount == 0  # клампим
    # HP цели не изменилось
    assert target.hit_points.current == target.hit_points.maximum

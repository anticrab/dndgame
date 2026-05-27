"""T1: единый бросок спасброска с учётом профициентности класса."""

from __future__ import annotations

from dnd.application.engine.saving_throw import roll_saving_throw, saving_throw_bonus
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId


def _actor(*, con_prof: bool) -> Creature:
    c = Creature.create(
        id_=CreatureId("h"),
        name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=14, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    c.proficiency_bonus = 2
    if con_prof:
        c.saving_throw_proficiencies = frozenset({Ability.CON})
    return c


def _ctx(actor: Creature, rolls: list[int]) -> TurnContext:
    bf = Battlefield(3, 3)
    deps, _bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    return TurnContext(
        actor_id=actor.id,
        battlefield=deps.battlefield,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={actor.id: actor},
        movement_remaining_ft=actor.speed_ft,
    )


def test_saving_throw_bonus_with_and_without_proficiency() -> None:
    assert saving_throw_bonus(_actor(con_prof=True), Ability.CON) == 4  # +2 mod +2 prof
    assert saving_throw_bonus(_actor(con_prof=False), Ability.CON) == 2  # только +2 mod


def test_proficient_save_adds_proficiency() -> None:
    actor = _actor(con_prof=True)
    # d20=10 + CON(2) + prof(2) = 14 ≥ DC 13 → успех
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=_ctx(actor, [10])) is True


def test_nonproficient_save_no_proficiency() -> None:
    actor = _actor(con_prof=False)
    # d20=10 + CON(2) = 12 < DC 13 → провал (prof не добавился)
    assert roll_saving_throw(actor, Ability.CON, dc=13, ctx=_ctx(actor, [10])) is False


def test_roll_saving_throw_raw_uses_services() -> None:
    """raw-вариант не требует TurnContext — берёт службы напрямую."""
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    deps, _bus, _rng = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=[10])
    actor = Creature.create(
        id_=CreatureId("a"),
        name="a",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=14, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    # d20=10 + WIS(+2) = 12 >= 12 → успех.
    assert (
        roll_saving_throw_raw(
            actor,
            Ability.WIS,
            dc=12,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
        )
        is True
    )


def test_auto_fails_save_paralyzed_dex() -> None:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    reg = ConditionRegistry()
    register_default_conditions(reg)
    svc = ConditionService(reg)
    c = Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=10, dex=18, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    c.apply_condition(PARALYZED)
    assert svc.auto_fails_save(c, Ability.DEX) is True
    assert svc.auto_fails_save(c, Ability.CON) is False


def test_roll_saving_throw_auto_fails_under_paralyzed() -> None:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    reg = ConditionRegistry()
    register_default_conditions(reg)
    svc = ConditionService(reg)
    deps, _bus, _ = build_scripted_dependencies(
        battlefield=Battlefield(1, 1),
        rolls=[20],  # даже d20=20 не спасёт
    )
    c = Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=10, dex=18, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    c.apply_condition(PARALYZED)
    assert (
        roll_saving_throw_raw(
            c,
            Ability.DEX,
            dc=5,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
            condition_service=svc,
        )
        is False
    )


def test_auto_fails_save_paralyzed_str_and_dex() -> None:
    """Paralyzed авто-проваливает И Силу, И Ловкость (PHB-2024 стр. 367)."""
    from dnd.application.engine.condition_service import ConditionService
    from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    reg = ConditionRegistry()
    register_default_conditions(reg)
    svc = ConditionService(reg)
    c = Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=14, dex=14, con=14, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    c.apply_condition(PARALYZED)
    assert svc.auto_fails_save(c, Ability.STR) is True
    assert svc.auto_fails_save(c, Ability.DEX) is True
    assert svc.auto_fails_save(c, Ability.CON) is False
    assert svc.auto_fails_save(c, Ability.WIS) is False


def _dodge_dex_setup(rolls: list[int]):
    from dnd.application.engine.condition_service import ConditionService
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    from dnd.domain.values.ids import CreatureId

    deps, _bus, _ = build_scripted_dependencies(battlefield=Battlefield(1, 1), rolls=rolls)
    reg = ConditionRegistry()
    register_default_conditions(reg)
    c = Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    return c, deps, ConditionService(reg)


def test_dodge_grants_dex_save_advantage() -> None:
    """Dodge → преимущество на DEX-спасбросок: из [1, 18] берётся больший 18."""
    from dnd.application.engine.actions.stances import CombatStance
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.domain.values.ability import Ability

    c, deps, svc = _dodge_dex_setup([1, 18])  # advantage → 2 d20, берём 18
    c.combat_stances.add(CombatStance.DODGING.value)
    # d20=18 (преимущество) + DEX 0 = 18 >= 15 → успех; без advantage был бы 1 → провал.
    assert (
        roll_saving_throw_raw(
            c,
            Ability.DEX,
            dc=15,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
            condition_service=svc,
        )
        is True
    )


def test_dodge_dex_advantage_suppressed_by_incapacitated() -> None:
    """Incapacitated гасит преимущество Dodge (PHB-2024 стр. 22): один d20."""
    from dnd.application.engine.actions.stances import CombatStance
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.domain.conditions.builtin import INCAPACITATED
    from dnd.domain.values.ability import Ability

    c, deps, svc = _dodge_dex_setup([1])  # без advantage — один d20=1
    c.combat_stances.add(CombatStance.DODGING.value)
    c.apply_condition(INCAPACITATED)  # сам по себе не авто-проваливает DEX
    # d20=1 + 0 = 1 < 15 → провал; если бы advantage не погасили — нужен 2-й d20
    # (IndexError при попытке), значит advantage действительно подавлен.
    assert (
        roll_saving_throw_raw(
            c,
            Ability.DEX,
            dc=15,
            dice_roller=deps.dice_roller,
            modifier_applier=deps.modifier_applier,
            condition_service=svc,
        )
        is False
    )

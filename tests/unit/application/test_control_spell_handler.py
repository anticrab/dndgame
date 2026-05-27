"""ControlSpellHandler (T2): пул Sleep + спасбросок Hold Person."""
from __future__ import annotations

from dnd.application.dto.engine_event import ConditionApplied
from dnd.application.engine.spells.handlers import ControlSpellHandler
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind


def _mage() -> Creature:
    m = Creature.create(
        id_=CreatureId("mage"), name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    m.spellcasting_ability = Ability.INT
    m.spell_slots = {1: 2, 2: 2}
    return m


def _weak(id_: str, hp: int) -> Creature:
    return Creature.create(
        id_=CreatureId(id_), name=id_,
        abilities=AbilityScores.of(str_=8, dex=10, con=10, int_=8, wis=8, cha=8),
        max_hp=hp, armor_class=12, speed_ft=30,
    )


def _ctx(rolls: list[int], creatures: list[Creature]) -> tuple[TurnContext, object]:
    bf = Battlefield(8, 8)
    deps, bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    ctx = TurnContext(
        actor_id=creatures[0].id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=bus,
        rng=deps.rng,
        participants={c.id: c for c in creatures},
        movement_remaining_ft=30,
    )
    return ctx, bus


def _sleep() -> Spell:
    return Spell(
        id=SpellId("sleep"), name="Sleep", level=1, school="enchantment",
        effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),  # цели уже отрезолвлены
        range_ft=90, description="", condition=UNCONSCIOUS,
        hp_pool_dice="5d8", condition_ends_on_damage=True,
    )


def test_sleep_pool_orders_by_hp_and_stops() -> None:
    mage = _mage()
    low = _weak("low", 5)
    high = _weak("high", 30)
    ctx, bus = _ctx([2, 2, 2, 2, 2], [mage, low, high])  # 5d8 = 10 пула
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    # Пул 10 → хватает на low(5), не хватает на high(30): сначала идёт low.
    ControlSpellHandler().apply(mage, (high, low), _sleep(), ctx)
    assert low.has_condition(UNCONSCIOUS)
    assert not high.has_condition(UNCONSCIOUS)
    assert any(a.target_id == low.id for a in applied)


def _hold() -> Spell:
    return Spell(
        id=SpellId("hold_person"), name="Hold Person", level=2,
        school="enchantment", effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.SINGLE), range_ft=60,
        description="", condition=PARALYZED, save_ability=Ability.WIS,
        concentration=True, condition_repeat_save=True,
    )


def test_hold_person_fail_save_paralyzes_and_sets_concentration() -> None:
    mage = _mage()
    orc = _weak("orc", 15)  # WIS -1
    ctx, bus = _ctx([1], [mage, orc])  # d20=1 → провал
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    ControlSpellHandler().apply(mage, (orc,), _hold(), ctx)
    assert orc.has_condition(PARALYZED)
    assert mage.concentration == SpellId("hold_person")
    assert applied[-1].repeat_save_ability is Ability.WIS


def test_hold_person_success_save_no_effect() -> None:
    mage = _mage()
    orc = _weak("orc", 15)
    ctx, _bus = _ctx([20], [mage, orc])  # d20=20 → успех
    ControlSpellHandler().apply(mage, (orc,), _hold(), ctx)
    assert not orc.has_condition(PARALYZED)

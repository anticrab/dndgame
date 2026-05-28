"""U3-1: BuffSpellHandler — concentration-source только при концентрации.

Раньше любой BUFF (в т.ч. не-концентрационный, как зелье силы) регистрировался
с ``source_id = concentration:{caster}`` — старт нового concentration-заклинания
кастера снимал и его. Теперь не-концентрационный бафф имеет собственный
``source_id = buff:{spell}:{owner}``: независим от концентрации, не сносится
при её смене."""

from __future__ import annotations

from dnd.application.engine.spells.handlers import BuffSpellHandler, concentration_source
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import SpellId
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.spell import BuffSpec, Spell, SpellEffect, TargetingSpec, TargetKind
from dnd.domain.values.spell_power import SpellPower
from dnd.domain.values.square import Square


def _hero() -> Creature:
    h = Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )
    h.spellcasting_ability = Ability.INT
    return h


def _ctx(hero: Creature) -> TurnContext:
    bf = Battlefield(5, 5)
    bf.place_creature(hero.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[1])
    return TurnContext(
        actor_id=hero.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={hero.id: hero},
        movement_remaining_ft=30,
    )


def _potion_strength_buff() -> Spell:
    """Не-концентрационный BUFF: +2 к проверкам Силы (зелье силы)."""
    return Spell(
        id=SpellId("potion_strength_buff"),
        name="Strength Potion",
        level=0,
        school="-",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.SELF),
        range_ft=0,
        description="",
        concentration=False,
        buffs=(BuffSpec(target=ModifierTargetKind.ABILITY_CHECK, numeric_bonus=2),),
    )


def _shield_of_faith() -> Spell:
    """Концентрационный BUFF: +2 к КД (Shield of Faith)."""
    return Spell(
        id=SpellId("shield_of_faith"),
        name="Shield of Faith",
        level=1,
        school="abjuration",
        effect=SpellEffect.BUFF,
        targeting=TargetingSpec(kind=TargetKind.SELF),
        range_ft=60,
        description="",
        concentration=True,
        buffs=(BuffSpec(target=ModifierTargetKind.ARMOR_CLASS, numeric_bonus=2),),
    )


def test_non_concentration_buff_uses_own_source_id() -> None:
    hero = _hero()
    ctx = _ctx(hero)
    BuffSpellHandler().apply(
        hero, (hero,), _potion_strength_buff(), ctx, SpellPower.from_caster(hero)
    )
    mods = ctx.modifier_applier.collect(
        owner_id=hero.id, target_kind=ModifierTargetKind.ABILITY_CHECK
    )
    assert len(mods) == 1
    assert mods[0].source_id == "buff:potion_strength_buff:hero"
    assert mods[0].source_id != concentration_source(hero.id)


def test_starting_concentration_does_not_remove_potion_buff() -> None:
    """Зелье силы (не-конц.) на герое; герой кастует Shield of Faith
    (концентрационный) — бафф зелья остаётся в силе (свой source_id)."""
    hero = _hero()
    ctx = _ctx(hero)
    BuffSpellHandler().apply(
        hero, (hero,), _potion_strength_buff(), ctx, SpellPower.from_caster(hero)
    )
    BuffSpellHandler().apply(hero, (hero,), _shield_of_faith(), ctx, SpellPower.from_caster(hero))
    # Бафф зелья жив (свой source_id).
    str_mods = ctx.modifier_applier.collect(
        owner_id=hero.id, target_kind=ModifierTargetKind.ABILITY_CHECK
    )
    assert any(m.source_id == "buff:potion_strength_buff:hero" for m in str_mods)
    # Концентрация — Shield of Faith.
    assert hero.concentration == SpellId("shield_of_faith")


def test_concentration_buff_still_uses_concentration_source() -> None:
    """Регрессия: концентрационный бафф по-прежнему оседает на
    concentration-source (для корректного срыва концентрации)."""
    hero = _hero()
    ctx = _ctx(hero)
    BuffSpellHandler().apply(hero, (hero,), _shield_of_faith(), ctx, SpellPower.from_caster(hero))
    mods = ctx.modifier_applier.collect(
        owner_id=hero.id, target_kind=ModifierTargetKind.ARMOR_CLASS
    )
    assert len(mods) == 1
    assert mods[0].source_id == concentration_source(hero.id)

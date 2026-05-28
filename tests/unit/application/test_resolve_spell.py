"""resolve_and_apply_spell — чистое slotless-ядро применения эффекта (U1-3).

Ядро не тратит слот и экономику и не публикует SpellCast — это забота
вызывающего действия (CastSpellAction / UseItemAction). Проверяем, что эффект
действительно применился (на примере HEAL — публикуется HealingApplied)."""

from __future__ import annotations

from dnd.application.dto.engine_event import HealingApplied
from dnd.application.engine.spells.area import default_area_shape_registry
from dnd.application.engine.spells.defaults import default_spell_effect_registry
from dnd.application.engine.spells.resolve import resolve_and_apply_spell
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
from dnd.domain.values.spell_power import SpellPower


def test_resolve_self_heal_slotless_publishes_event() -> None:
    hero = Creature.create(
        id_=CreatureId("h"),
        name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=10,
        speed_ft=30,
    )
    hero.hit_points = hero.hit_points.take_damage(15)  # 20 → 5, чтобы лечение было видно
    bf = Battlefield(5, 5)
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[4, 4])
    ctx = TurnContext(
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
    healed: list[HealingApplied] = []
    bus.subscribe(HealingApplied, healed.append)
    spell = Spell(
        id=SpellId("potion_healing"),
        name="x",
        level=0,
        school="-",
        effect=SpellEffect.HEAL,
        targeting=TargetingSpec(kind=TargetKind.SELF),
        range_ft=5,
        description="",
        heal_dice="2d4+2",
    )
    resolve_and_apply_spell(
        hero,
        spell,
        ctx=ctx,
        power=SpellPower.potion(),
        target_id=None,
        target_ids=(),
        target_point=None,
        direction=None,
        effect_registry=default_spell_effect_registry(),
        area_registry=default_area_shape_registry(),
    )
    assert healed and healed[-1].target_id == hero.id  # 2d4+2 = 10 (без мода)
    assert healed[-1].amount > 0

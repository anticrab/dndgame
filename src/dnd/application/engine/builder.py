"""Builder'ы: ``MonsterTemplate`` → ``Creature``, ``WeaponTemplate`` →
``WeaponProfile``.

Разделение «шаблон vs runtime entity» — pure-функция здесь, никакого
state. Один и тот же template может породить несколько инстансов (gob#1,
gob#2). Идентификатор инстанса передаётся снаружи.
"""

from __future__ import annotations

from dnd.application.dto.templates import (
    AbilityScoresTemplate,
    MonsterTemplate,
    WeaponTemplate,
)
from dnd.application.ports.content_repository import ContentRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.weapon import WeaponProfile


def build_weapon_profile(template: WeaponTemplate) -> WeaponProfile:
    """``WeaponTemplate`` → ``WeaponProfile``.

    Заодно валидирует `ability` (строка "STR"/"DEX"/...) — недопустимое
    значение даст ``KeyError`` от ``Ability(value)``.
    """
    ability = Ability(template.ability)
    return WeaponProfile(
        name=template.name,
        kind=template.kind,
        damage_expr=template.damage_expr,
        damage_type=template.damage_type,
        range_ft=template.range_ft,
        long_range_ft=template.long_range_ft,
        ability=ability,
        finesse=template.finesse,
    )


def build_creature_from_template(
    template: MonsterTemplate,
    *,
    instance_id: CreatureId,
    content: ContentRepository,
) -> Creature:
    """Собрать ``Creature`` из шаблона.

    ``content`` нужен, чтобы достать ``WeaponProfile`` по ``weapon_id``.
    Без оружия — ``equipped_weapon=None``.
    """
    weapon: WeaponProfile | None = None
    if template.weapon_id is not None:
        weapon = build_weapon_profile(content.weapon_by_id(template.weapon_id))

    creature = Creature.create(
        id_=instance_id,
        name=template.name,
        abilities=_build_abilities(template.abilities),
        max_hp=template.max_hp,
        armor_class=template.armor_class,
        speed_ft=template.speed_ft,
        proficiency_bonus=template.proficiency_bonus,
        equipped_weapon=weapon,
        resistances=frozenset(template.resistances),
        vulnerabilities=frozenset(template.vulnerabilities),
        immunities=frozenset(template.immunities),
    )
    # Заклинания (P1): кастер получает характеристику/ячейки/список заклинаний.
    if template.spellcasting_ability is not None:
        creature.spellcasting_ability = Ability(template.spellcasting_ability)
        creature.known_spells = tuple(SpellId(s) for s in template.known_spells)
        creature.spell_slots = dict(template.spell_slots)
    return creature


def _build_abilities(t: AbilityScoresTemplate) -> AbilityScores:
    return AbilityScores.of(
        str_=t.str_,
        dex=t.dex,
        con=t.con,
        int_=t.int_,
        wis=t.wis,
        cha=t.cha,
    )


__all__ = [
    "build_creature_from_template",
    "build_weapon_profile",
]

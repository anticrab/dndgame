"""Builder'ы: ``MonsterTemplate`` → ``Creature``, ``WeaponTemplate`` →
``WeaponProfile``.

Разделение «шаблон vs runtime entity» — pure-функция здесь, никакого
state. Один и тот же template может породить несколько инстансов (gob#1,
gob#2). Идентификатор инстанса передаётся снаружи.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.templates import (
    AbilityScoresTemplate,
    MonsterTemplate,
    WeaponTemplate,
)
from dnd.application.ports.content_repository import ContentRepository
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId, FeatureId, SpellId
from dnd.domain.values.item import ItemId
from dnd.domain.values.skill import Skill
from dnd.domain.values.weapon import WeaponProfile

if TYPE_CHECKING:
    from dnd.application.ports.class_repository import ClassRepository
    from dnd.application.ports.item_repository import ItemRepository


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
    class_repository: ClassRepository | None = None,
    item_repository: ItemRepository | None = None,
) -> Creature:
    """Собрать ``Creature`` из шаблона.

    ``content`` нужен, чтобы достать ``WeaponProfile`` по ``weapon_id``.
    Без оружия — ``equipped_weapon=None``.

    ``class_repository`` (T1) — чтобы выставить профициентные спасброски из
    класса PC; None → пусто (обычные монстры).

    ``item_repository`` (U5-3) — чтобы заполнить стартовый инвентарь по
    ``template.starting_inventory`` (list of item-id). Без репозитория поле
    игнорируется (backward-compat: тесты, не работающие с предметами).
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
    # Прогрессия (R1): cr для XP, класс/уровень для PC.
    creature.challenge_rating = template.cr
    creature.character_class = template.character_class
    creature.level = template.level
    creature.xp = template.xp
    # T4: выбор данными шаблона (интерактив отложен) — боевой стиль/подкласс.
    creature.fighting_style = (
        FeatureId(template.fighting_style) if template.fighting_style else None
    )
    creature.subclass = FeatureId(template.subclass) if template.subclass else None
    # T1: профициентные спасброски из класса (для бросков спасбросков с prof).
    # V1: владение навыками — из класса И из шаблона (объединение).
    skills: set[Skill] = set()
    if (
        class_repository is not None
        and template.character_class is not None
        and class_repository.contains(template.character_class)
    ):
        progression = class_repository.load(template.character_class)
        creature.saving_throw_proficiencies = progression.saving_throw_proficiencies
        skills |= progression.skill_proficiencies
    skills |= {Skill(code) for code in template.skill_proficiencies}
    creature.skill_proficiencies = frozenset(skills)
    creature.skill_expertise = frozenset(Skill(code) for code in template.skill_expertise)
    # U5-3: стартовый инвентарь — по одной единице каждого предмета из шаблона.
    if item_repository is not None and template.starting_inventory:
        for raw_id in template.starting_inventory:
            item = item_repository.load(ItemId(raw_id))
            creature.inventory.add(item)
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

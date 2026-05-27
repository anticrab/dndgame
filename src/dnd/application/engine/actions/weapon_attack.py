"""Helper'ы для сборки ``AttackParams`` из экипированного оружия.

См. ``docs/ACTIONS.md`` §2 + ``WeaponProfile``.

Зачем: ``AttackParams`` принимает atk_bonus и damage_expr в готовом виде
(статика оружия + ability_mod + proficiency). UI / AI / тесты не должны
руками собирать эти числа — для этого есть :func:`weapon_attack_params`.
"""

from __future__ import annotations

from dnd.application.engine.actions.attack import AttackParams
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId


def _ability_for_attack(creature: Creature) -> Ability:
    """Выбрать характеристику атаки для экипированного оружия.

    Без weapon → STR (raise: оружие должно быть). Для finesse — берём
    max(STR, DEX); иначе — `weapon.ability`.
    """
    weapon = creature.equipped_weapon
    assert weapon is not None, "creature must have equipped_weapon"
    if not weapon.finesse:
        return weapon.ability
    str_mod = creature.abilities.modifier(Ability.STR)
    dex_mod = creature.abilities.modifier(Ability.DEX)
    return Ability.STR if str_mod >= dex_mod else Ability.DEX


def weapon_attack_params(creature: Creature, target_id: CreatureId) -> AttackParams:
    """Собрать ``AttackParams`` для атаки экипированным оружием.

    Складывает:

    * ``attack_bonus = proficiency_bonus + ability_mod``;
    * ``damage_expr = weapon.damage_expr + ability_mod`` (если bonus != 0);
    * ``kind / range_ft / long_range_ft / damage_type`` берёт из weapon.

    ValueError если у creature нет equipped_weapon.
    """
    weapon = creature.equipped_weapon
    if weapon is None:
        raise ValueError(
            f"creature {creature.id!r} has no equipped_weapon; cannot build weapon_attack_params"
        )

    ability = _ability_for_attack(creature)
    ability_mod = creature.abilities.modifier(ability)
    attack_bonus = creature.proficiency_bonus + ability_mod

    # damage = weapon.damage_expr + ability_mod. Все оружия в MVP
    # имеют dice-форму ("1d8", "1d6"); чистый bonus-only (unarmed) пока
    # не поддерживается — см. weapon.py / аудит 14 VS-R001.
    if ability_mod == 0:
        damage_expr = weapon.damage_expr
    else:
        damage_expr = f"{weapon.damage_expr}{ability_mod:+d}"

    return AttackParams(
        target_id=target_id,
        kind=weapon.kind,
        attack_bonus=attack_bonus,
        damage_expr=damage_expr,
        damage_type=weapon.damage_type,
        range_ft=weapon.range_ft,
        long_range_ft=weapon.long_range_ft,
    )


__all__ = ["weapon_attack_params"]

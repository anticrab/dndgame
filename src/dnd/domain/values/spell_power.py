"""SpellPower (U) — эффективные Сл/атака/мод применяемого эффекта.

Развязывает «силу» эффекта от источника: заклинание волшебника берёт её из
кастера, свиток — фикс по уровню (PHB-2024, таблица свитков), зелье — нулевой
мод (лечит ровно по кости). Хендлеры читают эти числа вместо прямых
``caster.spell_*()`` — поэтому один и тот же эффект-пакет (напр. ``fireball``)
работает и как заклинание (DC кастера), и как свиток (фикс-DC по уровню).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from dnd.domain.entities.creature import Creature


@dataclass(frozen=True, slots=True)
class SpellPower:
    """Источник Сл/атаки/мода для применения эффекта."""

    save_dc: int  # для SAVE / CONTROL
    attack_bonus: int  # для ATTACK
    ability_mod: int  # прибавка к HEAL ("+ мод заклинательной хар-ки")

    # PHB-2024 «Spell Scroll»: Сл/атака свитка по уровню заклинания.
    # Запись (max_level, dc, attack); первое совпадение по `spell_level <=`.
    _SCROLL: ClassVar[tuple[tuple[int, int, int], ...]] = (
        (2, 13, 5),
        (4, 15, 7),
        (6, 17, 9),
        (8, 18, 10),
        (9, 19, 11),
    )

    @classmethod
    def scroll(cls, spell_level: int) -> SpellPower:
        """Фикс-Сл/атака свитка по уровню заклинания (`ability_mod=0`)."""
        for max_level, dc, atk in cls._SCROLL:
            if spell_level <= max_level:
                return cls(save_dc=dc, attack_bonus=atk, ability_mod=0)
        last = cls._SCROLL[-1]
        return cls(save_dc=last[1], attack_bonus=last[2], ability_mod=0)

    @classmethod
    def potion(cls) -> SpellPower:
        """Зелье/предмет без своей «силы» — лечит/баффает ровно по данным."""
        return cls(save_dc=0, attack_bonus=0, ability_mod=0)

    @staticmethod
    def from_caster(caster: Creature) -> SpellPower:
        """Сила эффекта из заклинательных параметров кастера (CastSpellAction)."""
        mod = (
            caster.abilities.modifier(caster.spellcasting_ability)
            if caster.spellcasting_ability is not None
            else 0
        )
        return SpellPower(
            save_dc=caster.spell_save_dc(),
            attack_bonus=caster.spell_attack_bonus(),
            ability_mod=mod,
        )


__all__ = ["SpellPower"]

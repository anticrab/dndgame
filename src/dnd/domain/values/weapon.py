"""WeaponProfile — value-объект «оружие» для MVP.

Минимальная модель: достаточно, чтобы собрать ``AttackParams``
(`atb`-бонус, damage, range). Полная модель (свойства Versatile,
Two-Handed, Heavy, Light, Loading, специальные мастер-варианты) — после
расширения Equipment-системы.

См. ENGINE.md §4 и «Книгу Игрока 2024» стр. 211–212 (Свойства оружия).
"""

from __future__ import annotations

from dataclasses import dataclass

from dnd.domain.values.ability import Ability
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.damage import DamageType


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    """Профиль оружия. Frozen — оружие как ID-карта, не как инвентарный
    объект (потерянного оружия в MVP нет).

    * ``ability`` — характеристика, по которой считается attack_bonus
      и damage_mod. Для большинства Melee — STR; для большинства
      Ranged — DEX.
    * ``finesse`` — Finesse-оружие (PHB-2024 стр. 212): атакующий
      сам выбирает STR или DEX (берём ``max``).
    * ``range_ft`` для MELEE — это reach (обычно 5; глефа 10);
      для RANGED — нормальная дальность.
    * ``long_range_ft`` для RANGED — за пределами range_ft до
      long_range_ft действует disadvantage; дальше — нельзя.
      Для MELEE должен быть 0.
    """

    name: str
    kind: AttackKind
    damage_expr: str  # кубы без mod: "1d8", "2d6"
    damage_type: DamageType
    range_ft: int = 5
    long_range_ft: int = 0
    ability: Ability = Ability.STR
    finesse: bool = False


# --- библиотека самых ходовых оружий MVP ------------------------------

LONGSWORD = WeaponProfile(
    name="Long Sword",
    kind=AttackKind.MELEE,
    damage_expr="1d8",
    damage_type=DamageType.SLASHING,
)

SHORTSWORD = WeaponProfile(
    name="Short Sword",
    kind=AttackKind.MELEE,
    damage_expr="1d6",
    damage_type=DamageType.PIERCING,
    finesse=True,
)

SCIMITAR = WeaponProfile(
    name="Scimitar",
    kind=AttackKind.MELEE,
    damage_expr="1d6",
    damage_type=DamageType.SLASHING,
    finesse=True,
)

SHORTBOW = WeaponProfile(
    name="Short Bow",
    kind=AttackKind.RANGED,
    damage_expr="1d6",
    damage_type=DamageType.PIERCING,
    range_ft=80,
    long_range_ft=320,
    ability=Ability.DEX,
)

# Unarmed Strike (PHB-2024 стр. 209: «1 + STR mod bludgeoning») —
# **намеренно не включён** в MVP. Текущий ``damage_expr`` —
# это строка для ``DiceExpr.parse`` («1d8», «1d6+2»), а формула
# «1 + STR mod» без кубов не выражается в этом формате (нет
# обязательного `d`-блока). См. аудит 14 VS-R001. Добавим, когда
# damage-формат расширится поддержкой fixed-bonus-без-dice.


__all__ = [
    "LONGSWORD",
    "SCIMITAR",
    "SHORTBOW",
    "SHORTSWORD",
    "WeaponProfile",
]

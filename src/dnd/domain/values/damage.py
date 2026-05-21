"""Типы урона и множители (сопротивление/уязвимость/иммунитет).

Книга 2024, «Урон и лечение» (стр. 26):

* у каждого случая урона — **тип** (один из 13 в таблице ниже);
* существо может иметь **сопротивление** (×½), **уязвимость** (×2) или
  **иммунитет** (×0) к конкретному типу;
* множители одного типа **не складываются** (несколько сопротивлений
  огню — это одно сопротивление);
* порядок применения: бонусы/штрафы → сопротивление → уязвимость
  (см. подраздел «Порядок применения» в книге).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DamageType(StrEnum):
    """13 типов урона из книги 2024 (стр. 26)."""

    ACID = "acid"
    BLUDGEONING = "bludgeoning"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    PIERCING = "piercing"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    SLASHING = "slashing"
    THUNDER = "thunder"


class DamageMultiplier(StrEnum):
    """Множитель урона по типу.

    NORMAL == 1.0; RESISTANT == 0.5 (округление вниз);
    VULNERABLE == 2.0; IMMUNE == 0.
    """

    NORMAL = "normal"
    RESISTANT = "resistant"
    VULNERABLE = "vulnerable"
    IMMUNE = "immune"


@dataclass(frozen=True, slots=True)
class DamageInstance:
    """Одна порция урона: число + тип.

    Атаки часто наносят несколько `DamageInstance` (оружие + бонус от
    заклинания и т.п.) — это разные «инстансы», каждый со своим
    типом и своими множителями цели.
    """

    amount: int
    type_: DamageType

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"damage amount must be >= 0, got {self.amount}")


def apply_damage_multiplier(amount: int, multiplier: DamageMultiplier) -> int:
    """Применить множитель урона к числу, по правилам книги.

    * ``IMMUNE`` → 0.
    * ``RESISTANT`` → ``floor(amount / 2)`` (округление вниз по правилу
      «Округление вниз» из книги).
    * ``VULNERABLE`` → ``amount * 2``.
    * ``NORMAL`` → ``amount``.

    Особый случай: ``RESISTANT`` от 0 даёт 0; ``RESISTANT`` от 1
    даёт 0 (округление вниз). Книга явно подсвечивает это правило.
    """
    if amount < 0:
        raise ValueError(f"damage amount must be >= 0, got {amount}")
    match multiplier:
        case DamageMultiplier.IMMUNE:
            return 0
        case DamageMultiplier.RESISTANT:
            return amount // 2
        case DamageMultiplier.VULNERABLE:
            return amount * 2
        case DamageMultiplier.NORMAL:
            return amount


def combine_multipliers(resistant: bool, vulnerable: bool, immune: bool) -> DamageMultiplier:
    """Свести три булевых отметки в один множитель по правилу «не складываются».

    Книга: «множества сопротивлений/уязвимостей к одному типу считаются
    одним». Логически:

    * immune > всё остальное.
    * если **одновременно** resistant и vulnerable — взаимно гасятся
      (правило книги «бонусы одного типа не складываются»: один источник
      резиста и один уязвимости дают NORMAL).
    * иначе — берём то, что есть.

    Это полезный helper для `Creature` — сводит набор пометок к одному
    множителю на тип.
    """
    if immune:
        return DamageMultiplier.IMMUNE
    if resistant and vulnerable:
        return DamageMultiplier.NORMAL
    if resistant:
        return DamageMultiplier.RESISTANT
    if vulnerable:
        return DamageMultiplier.VULNERABLE
    return DamageMultiplier.NORMAL

"""Spell — декларативное описание заклинания (этап P1).

Заклинание — **данные**, а не код: единственный ``CastSpellAction`` исполняет
его по полю :attr:`Spell.effect`. Это позволяет добавлять заклинания строками в
``data/content/spells.yaml`` без новых классов (см. docs/SPELLS.md).

Модель сразу несёт поля под будущее (этап P2 — AoE/мультитаргет, P3 — справка):
:class:`TargetingSpec` и :attr:`Spell.description`. В P1 реализуются только
``SELF`` / ``SINGLE``-цели; ``MULTI`` / ``AREA`` — задел.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import SpellId


class SpellEffect(StrEnum):
    """Тип эффекта — определяет ветку исполнения в CastSpellAction."""

    ATTACK = "attack"   # spell attack roll → урон при попадании
    SAVE = "save"       # цель кидает спасбросок vs DC → урон (полный/половина)
    AUTO = "auto"       # авто-попадание → урон без броска (Magic Missile)
    HEAL = "heal"       # восстановление HP
    BUFF = "buff"       # модификатор/бафф на цель (± концентрация)


class TargetKind(StrEnum):
    """Как выбирается цель. SELF/SINGLE — P1; AREA — P2; MULTI — P2b."""

    SELF = "self"
    SINGLE = "single"
    MULTI = "multi"
    AREA = "area"


class OriginMode(StrEnum):
    """Откуда строится зона (AREA, этап P2)."""

    FROM_CASTER = "from_caster"   # эманация от клетки кастера в направлении
    AT_POINT = "at_point"         # зона вокруг выбранной точки (в пределах range)


class AreaShape(StrEnum):
    """Форма зоны поражения (AREA, этап P2). Расширяемо через реестр резолверов."""

    CIRCLE = "circle"   # chebyshev-диск радиуса radius_ft/5
    CONE = "cone"       # конус от origin в направлении, длина length_ft/5
    LINE = "line"       # луч от origin в направлении, длина length_ft/5


@dataclass(frozen=True, slots=True)
class TargetingSpec:
    """Спецификация нацеливания.

    Для ``kind=AREA`` (P2): ``origin`` (от кастера / в точку), ``shape`` и размер
    (``radius_ft`` для CIRCLE, ``length_ft`` для CONE/LINE). ``max_targets`` —
    задел под мультитаргет (P2b)."""

    kind: TargetKind
    max_targets: int = 1
    origin: OriginMode = OriginMode.AT_POINT
    shape: AreaShape | None = None
    radius_ft: int = 0
    length_ft: int = 0

    def __post_init__(self) -> None:
        if self.kind is not TargetKind.AREA:
            return
        if self.shape is None:
            raise ValueError("AREA targeting requires a shape")
        if self.shape is AreaShape.CIRCLE and self.radius_ft <= 0:
            raise ValueError("CIRCLE area requires radius_ft > 0")
        if self.shape in (AreaShape.CONE, AreaShape.LINE) and self.length_ft <= 0:
            raise ValueError(f"{self.shape} area requires length_ft > 0")


@dataclass(frozen=True, slots=True)
class Spell:
    """Заклинание (иммутабельные данные). Валидация по effect в __post_init__."""

    id: SpellId
    name: str
    level: int                       # 0 = заговор (cantrip)
    school: str
    effect: SpellEffect
    targeting: TargetingSpec
    range_ft: int
    description: str
    dice: str | None = None          # урон ATTACK/AUTO/SAVE ("1d10", "3d4+3")
    damage_type: DamageType | None = None
    save_ability: Ability | None = None   # для SAVE
    save_for_half: bool = True             # успех спасброска → половина урона
    concentration: bool = False
    heal_dice: str | None = None           # для HEAL
    ac_bonus: int = 0                      # для BUFF (Shield of Faith +2)

    def __post_init__(self) -> None:
        if self.level < 0:
            raise ValueError(f"spell level must be >= 0, got {self.level}")
        if self.effect in (SpellEffect.ATTACK, SpellEffect.AUTO):
            if self.dice is None or self.damage_type is None:
                raise ValueError(
                    f"{self.effect} spell {self.id} requires dice + damage_type"
                )
        elif self.effect is SpellEffect.SAVE:
            if self.dice is None or self.damage_type is None or self.save_ability is None:
                raise ValueError(
                    f"SAVE spell {self.id} requires dice + damage_type + save_ability"
                )
        elif self.effect is SpellEffect.HEAL:
            if self.heal_dice is None:
                raise ValueError(f"HEAL spell {self.id} requires heal_dice")
        elif self.effect is SpellEffect.BUFF and self.ac_bonus <= 0:
            raise ValueError(
                f"BUFF spell {self.id} requires ac_bonus > 0 (P1: только AC-баффы)"
            )


__all__ = [
    "AreaShape",
    "OriginMode",
    "Spell",
    "SpellEffect",
    "TargetKind",
    "TargetingSpec",
]

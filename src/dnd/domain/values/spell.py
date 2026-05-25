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

from dnd.application.dto.ids import SpellId
from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType


class SpellEffect(StrEnum):
    """Тип эффекта — определяет ветку исполнения в CastSpellAction."""

    ATTACK = "attack"   # spell attack roll → урон при попадании
    SAVE = "save"       # цель кидает спасбросок vs DC → урон (полный/половина)
    AUTO = "auto"       # авто-попадание → урон без броска (Magic Missile)
    HEAL = "heal"       # восстановление HP
    BUFF = "buff"       # модификатор/бафф на цель (± концентрация)


class TargetKind(StrEnum):
    """Как выбирается цель. P1: SELF / SINGLE. MULTI / AREA — этап P2."""

    SELF = "self"
    SINGLE = "single"
    MULTI = "multi"
    AREA = "area"


@dataclass(frozen=True, slots=True)
class TargetingSpec:
    """Спецификация нацеливания. ``max_targets`` / ``area_radius_ft`` —
    задел под P2 (мультитаргет / AoE), в P1 не используются."""

    kind: TargetKind
    max_targets: int = 1
    area_radius_ft: int = 0


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


__all__ = ["Spell", "SpellEffect", "TargetKind", "TargetingSpec"]

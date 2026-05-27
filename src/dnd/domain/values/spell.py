"""Spell — декларативное описание заклинания (этап P1).

Заклинание — **данные**, а не код: единственный ``CastSpellAction`` исполняет
его по полю :attr:`Spell.effect`. Это позволяет добавлять заклинания строками в
``data/content/spells.yaml`` без новых классов (см. docs/SPELLS.md).

Модель сразу несёт поля под будущее (этап P2 — AoE/мультитаргет, P3 — справка):
:class:`TargetingSpec` и :attr:`Spell.description`. В P1 реализуются только
``SELF`` / ``SINGLE``-цели; ``MULTI`` / ``AREA`` — задел.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.duration import Duration
from dnd.domain.values.ids import ConditionId, SpellId
from dnd.domain.values.modifiers import ModifierTargetKind


class SpellEffect(StrEnum):
    """Тип эффекта — определяет ветку исполнения в CastSpellAction."""

    ATTACK = "attack"  # spell attack roll → урон при попадании
    SAVE = "save"  # цель кидает спасбросок vs DC → урон (полный/половина)
    AUTO = "auto"  # авто-попадание → урон без броска (Magic Missile)
    HEAL = "heal"  # восстановление HP
    BUFF = "buff"  # модификатор/бафф на цель (± концентрация)
    CONTROL = "control"  # наложение состояния (± длительность/снятие) — T2


class TargetKind(StrEnum):
    """Как выбирается цель. SELF/SINGLE — P1; AREA — P2; MULTI — P2b."""

    SELF = "self"
    SINGLE = "single"
    MULTI = "multi"
    AREA = "area"


class OriginMode(StrEnum):
    """Откуда строится зона (AREA, этап P2)."""

    FROM_CASTER = "from_caster"  # эманация от клетки кастера в направлении
    AT_POINT = "at_point"  # зона вокруг выбранной точки (в пределах range)


class AreaShape(StrEnum):
    """Форма зоны поражения (AREA, этап P2). Расширяемо через реестр резолверов."""

    CIRCLE = "circle"  # chebyshev-диск радиуса radius_ft/5
    CONE = "cone"  # конус от origin в направлении, длина length_ft/5
    LINE = "line"  # луч от origin в направлении, длина length_ft/5


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
    allow_repeat_target: bool = False  # MULTI: можно ли несколько «попаданий» в одну цель

    def __post_init__(self) -> None:
        if self.kind is TargetKind.MULTI and self.max_targets < 1:
            raise ValueError("MULTI targeting requires max_targets >= 1")
        if self.kind is not TargetKind.AREA:
            return
        if self.shape is None:
            raise ValueError("AREA targeting requires a shape")
        if self.shape is AreaShape.CIRCLE and self.radius_ft <= 0:
            raise ValueError("CIRCLE area requires radius_ft > 0")
        if self.shape in (AreaShape.CONE, AreaShape.LINE) and self.length_ft <= 0:
            raise ValueError(f"{self.shape} area requires length_ft > 0")


@dataclass(frozen=True, slots=True)
class BuffSpec:
    """Один модификатор, накладываемый BUFF-заклинанием на цель.

    Ровно одно из полей задаёт эффект: ``numeric_bonus`` (например, +2 КД у
    Shield of Faith) ИЛИ ``dice_bonus`` (например, +1d4 к атаке/спасброскам у
    Bless). ``target`` — категория броска/значения (:class:`ModifierTargetKind`).
    """

    target: ModifierTargetKind
    numeric_bonus: int = 0
    dice_bonus: str | None = None

    def __post_init__(self) -> None:
        has_numeric = self.numeric_bonus != 0
        has_dice = self.dice_bonus is not None
        if has_numeric == has_dice:
            raise ValueError("BuffSpec требует ровно одно: numeric_bonus ИЛИ dice_bonus")


@dataclass(frozen=True, slots=True)
class Spell:
    """Заклинание (иммутабельные данные). Валидация по effect в __post_init__."""

    id: SpellId
    name: str
    level: int  # 0 = заговор (cantrip)
    school: str
    effect: SpellEffect
    targeting: TargetingSpec
    range_ft: int
    description: str
    dice: str | None = None  # урон ATTACK/AUTO/SAVE ("1d10", "3d4+3")
    damage_type: DamageType | None = None
    save_ability: Ability | None = None  # для SAVE
    save_for_half: bool = True  # успех спасброска → половина урона
    concentration: bool = False
    heal_dice: str | None = None  # для HEAL
    buffs: tuple[BuffSpec, ...] = ()  # для BUFF (Shield of Faith, Bless)
    # CONTROL (T2): наложение состояния. condition — что; ровно один гейт —
    # hp_pool_dice (Sleep: пул хитов, без спасброска) ИЛИ save_ability (резист).
    condition: ConditionId | None = None
    hp_pool_dice: str | None = None
    condition_ends_on_damage: bool = False  # Sleep: пробуждение от урона
    condition_repeat_save: bool = False  # Hold Person: спасбросок в конце хода
    # X0: длительность эффекта. INSTANT (по умолчанию) — нет снятия по часам;
    # конечная положительная → дедлайн через GameClock; concentration/безлимит —
    # снимается своими триггерами (срыв концентрации). Дополняет, не заменяет их.
    duration: Duration = field(default_factory=Duration.instant)

    def __post_init__(self) -> None:
        if self.level < 0:
            raise ValueError(f"spell level must be >= 0, got {self.level}")
        if self.effect in (SpellEffect.ATTACK, SpellEffect.AUTO):
            if self.dice is None or self.damage_type is None:
                raise ValueError(f"{self.effect} spell {self.id} requires dice + damage_type")
        elif self.effect is SpellEffect.SAVE:
            if self.dice is None or self.damage_type is None or self.save_ability is None:
                raise ValueError(f"SAVE spell {self.id} requires dice + damage_type + save_ability")
        elif self.effect is SpellEffect.HEAL:
            if self.heal_dice is None:
                raise ValueError(f"HEAL spell {self.id} requires heal_dice")
        elif self.effect is SpellEffect.BUFF and not self.buffs:
            raise ValueError(f"BUFF spell {self.id} requires at least one BuffSpec")
        elif self.effect is SpellEffect.CONTROL:
            if self.condition is None:
                raise ValueError(f"CONTROL spell {self.id} requires condition")
            has_pool = self.hp_pool_dice is not None
            has_save = self.save_ability is not None
            if has_pool == has_save:
                raise ValueError(
                    f"CONTROL spell {self.id}: ровно один гейт — hp_pool_dice ИЛИ save_ability"
                )
            if self.condition_repeat_save and not has_save:
                raise ValueError(
                    f"CONTROL spell {self.id}: condition_repeat_save требует "
                    "save_ability (есть что перебрасывать)"
                )


__all__ = [
    "AreaShape",
    "BuffSpec",
    "OriginMode",
    "Spell",
    "SpellEffect",
    "TargetKind",
    "TargetingSpec",
]

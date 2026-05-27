"""ClassProgression — декларативная таблица прогрессии класса (этап R1).

Класс — **данные** (data/content/classes.yaml), а не код: LevelUpService читает
таблицу, FeatureRegistry исполняет фичи по id. Новый класс = строки в YAML +
(при необходимости) хендлеры фич, без правки движка.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from dnd.domain.values.ability import Ability
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import FeatureId


@dataclass(frozen=True, slots=True)
class ClassLevel:
    """Что даёт один уровень класса."""

    proficiency_bonus: int
    features: tuple[FeatureId, ...] = ()
    spell_slots: dict[int, int] | None = None   # None у не-кастеров (Воин/Плут)


@dataclass(frozen=True, slots=True)
class ClassProgression:
    """Таблица класса: кость хитов + что даётся на каждом уровне."""

    id: str
    name: str
    hit_die: str                                 # сериализованный DiceExpr, "1d10"
    levels: dict[int, ClassLevel] = field(default_factory=dict)
    # Спасброски, в которых класс профициентен (PHB-2024 стр. 9): d20+mod+prof.
    # Пусто у не-PC. T1: Воин STR/CON, Плут DEX/INT, Маг INT/WIS.
    saving_throw_proficiencies: frozenset[Ability] = frozenset()

    def __post_init__(self) -> None:
        if 1 not in self.levels:
            raise ValueError(f"class {self.id} must define level 1")
        DiceExpr.parse(self.hit_die)             # валидируем нотацию кости

    def hit_die_average(self) -> int:
        """Фикс. среднее кости хитов (PHB «fixed value»): ⌈(sides+1)/2⌉."""
        sides = DiceExpr.parse(self.hit_die).sides
        return ceil((sides + 1) / 2)


__all__ = ["ClassLevel", "ClassProgression"]

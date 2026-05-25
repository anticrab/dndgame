"""RollPurpose — категория броска (доменное понятие).

*Что* за бросок: атака / спасбросок / тест / урон / инициатива / hit dice /
спасбросок от смерти / прочее. Книга 2024 называет их «Тесты к20», но мы
выделяем подкатегории для статистики, аудита и применения модификаторов.

Живёт в ``domain`` (правила оперируют типом броска); ``application`` (DiceRoller-
порт, RollContext/EngineRollResult) импортирует отсюда.
"""

from __future__ import annotations

from enum import StrEnum


class RollPurpose(StrEnum):
    ATTACK = "attack"
    DAMAGE = "damage"
    SAVE = "save"
    ABILITY_CHECK = "ability_check"
    INITIATIVE = "initiative"
    HIT_DICE = "hit_dice"
    DEATH_SAVE = "death_save"
    STATS_GEN = "stats_gen"
    LOOT = "loot"
    OTHER = "other"


__all__ = ["RollPurpose"]

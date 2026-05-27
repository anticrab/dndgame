"""Боевые стили Воина (T4-a) — данные + чистые helper'ы боевых бонусов.

Числовые/пассивные эффекты стиля. ``attack.py`` зовёт helper'ы (не switch по
классам). Defense применяется при получении фичи (см. ``StyleDefenseHandler``);
здесь — только ситуативные бонусы атаки/урона.

T4: выбор стиля — данными шаблона (``Creature.fighting_style``), интерактив
отложен (см. память project_interactive_choice_deferred).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import FeatureId

if TYPE_CHECKING:
    from dnd.domain.entities.creature import Creature

STYLE_DEFENSE = FeatureId("style_defense")
STYLE_DUELING = FeatureId("style_dueling")
STYLE_ARCHERY = FeatureId("style_archery")
STYLE_GWF = FeatureId("style_gwf")  # отложен (нужен reroll-хук урона)

#: Известные стили — для валидации и автодефолта.
KNOWN_STYLES = frozenset({STYLE_DEFENSE, STYLE_DUELING, STYLE_ARCHERY, STYLE_GWF})


def fighting_style_attack_bonus(actor: Creature, kind: AttackKind) -> int:
    """Archery: +2 к броску дальней атаки (PHB-2024)."""
    if actor.fighting_style == STYLE_ARCHERY and kind is AttackKind.RANGED:
        return 2
    return 0


def fighting_style_damage_bonus(actor: Creature, kind: AttackKind) -> int:
    """Dueling: +2 к урону рукопашной (приближение «одноручного» — любое melee)."""
    if actor.fighting_style == STYLE_DUELING and kind is AttackKind.MELEE:
        return 2
    return 0


__all__ = [
    "KNOWN_STYLES",
    "STYLE_ARCHERY",
    "STYLE_DEFENSE",
    "STYLE_DUELING",
    "STYLE_GWF",
    "fighting_style_attack_bonus",
    "fighting_style_damage_bonus",
]

"""Хендлеры классовых фич (этап R1). Регистрируются в default_feature_registry.

Каждая фича — отдельный класс. Пассивные правят деривации/вешают модификаторы;
активные инициализируют ресурс и выдают способность (Ability), исполняемую
своим Action (см. second_wind.py / action_surge.py).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.ids import FeatureId

if TYPE_CHECKING:
    from dnd.application.engine.features.registry import FeatureRegistry
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


class ImprovedCriticalHandler:
    """Чемпион L3: крит на 19–20. Пассив — ставит crit_range_min=19."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.crit_range_min = 19


class SneakAttackHandler:
    """Плут L1: Sneak Attack. Поведение — в AttackAction по наличию фичи в
    creature.features; on_gain — пасс (фича уже добавлена LevelUpService'ом)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return


def _grant_ability(creature: Creature, ability_id: str) -> None:
    """Выдать существу активную способность (добавить id в ability_ids)."""
    from dnd.domain.values.ability_id import AbilityId
    aid = AbilityId(ability_id)
    if aid not in creature.ability_ids:
        creature.ability_ids = (*creature.ability_ids, aid)


class SecondWindHandler:
    """Воин L1: Second Wind. on_gain — инициализирует ресурс и выдаёт ability."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("second_wind", 1)
        _grant_ability(creature, "second_wind")


class ActionSurgeHandler:
    """Воин L2: Action Surge. on_gain — инициализирует ресурс и выдаёт ability."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("action_surge", 1)
        _grant_ability(creature, "action_surge")


# --- T4: боевые стили, подклассы, Cunning Action -----------------------
# T4: выбор стиля/подкласса — данными шаблона (интерактив отложен).


class StyleDefenseHandler:
    """Боевой стиль Defense: +1 КД (пассив, persist в Creature.armor_class)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.armor_class += 1


class NoEffectFeatureHandler:
    """Фича без on_gain-эффекта (бонусы — ситуативно в attack.py/cast_spell,
    либо это флаг-подкласс, чьё поведение читается по наличию в features)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return


class FightingStyleHandler:
    """Воин L1: применяет выбранный боевой стиль (данные шаблона) или дефолт
    (Defense). Конкретный стиль применяется через тот же FeatureRegistry."""

    def __init__(self, registry: FeatureRegistry) -> None:
        self._reg = registry

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        from dnd.application.engine.features.fighting_styles import (
            KNOWN_STYLES,
            STYLE_DEFENSE,
        )
        style = creature.fighting_style
        if style is None or style not in KNOWN_STYLES:
            style = STYLE_DEFENSE
            creature.fighting_style = style
        if style not in creature.features:
            creature.features = (*creature.features, style)
        self._reg.get(style).on_gain(creature, ctx)


#: Дефолтный подкласс по классу (T4: выбор данными шаблона, интерактив отложен).
_DEFAULT_SUBCLASS: dict[str, FeatureId] = {
    "fighter": FeatureId("subclass_champion"),
    "rogue": FeatureId("subclass_thief"),
    "wizard": FeatureId("subclass_evoker"),
}


class SubclassHandler:
    """L3: применяет выбранный подкласс (данные шаблона) или дефолт по классу."""

    def __init__(self, registry: FeatureRegistry) -> None:
        self._reg = registry

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        sub = creature.subclass
        if sub is None or not self._reg.contains(sub):
            sub = _DEFAULT_SUBCLASS.get(creature.character_class or "")
        if sub is None:
            return
        creature.subclass = sub
        if sub not in creature.features:
            creature.features = (*creature.features, sub)
        self._reg.get(sub).on_gain(creature, ctx)


class ThiefHandler:
    """Вор L3 (лёгкая версия): Fast Hands — взаимодействие доступно бонусным
    действием (Interact уже есть). Second-Story Work (лазание) — вне scope,
    описано в docs/PROGRESSION.md. Флаг подкласса хранится в features."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        _grant_ability(creature, "interact")


class CunningActionHandler:
    """Плут L2: Cunning Action — Dash/Disengage бонусным действием (Hide —
    вне scope). Грантит соответствующие bonus-абилки."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        _grant_ability(creature, "cunning_dash")
        _grant_ability(creature, "cunning_disengage")


__all__ = [
    "ActionSurgeHandler",
    "CunningActionHandler",
    "FightingStyleHandler",
    "ImprovedCriticalHandler",
    "NoEffectFeatureHandler",
    "SecondWindHandler",
    "SneakAttackHandler",
    "StyleDefenseHandler",
    "SubclassHandler",
    "ThiefHandler",
]

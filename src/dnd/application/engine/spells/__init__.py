"""Подсистема заклинаний (этап P1): реестр эффект-хендлеров (open/closed).

Заклинания — data-driven (:class:`dnd.domain.values.spell.Spell` из YAML);
обработка эффекта — через :class:`SpellEffectRegistry`. Новый тип воздействия =
новый :class:`SpellEffectHandler` + регистрация, без касания CastSpellAction.
"""
from __future__ import annotations

from dnd.application.engine.spells.defaults import default_spell_effect_registry
from dnd.application.engine.spells.effect_handler import (
    SpellEffectHandler,
    SpellEffectRegistry,
)

__all__ = [
    "SpellEffectHandler",
    "SpellEffectRegistry",
    "default_spell_effect_registry",
]

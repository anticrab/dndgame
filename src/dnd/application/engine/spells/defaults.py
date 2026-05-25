"""Регистрация встроенных эффект-хендлеров заклинаний.

``default_spell_effect_registry`` собирает реестр со всеми типами эффектов,
поддержанными ядром. Контент-паки/плагины могут добавлять свои хендлеры в
полученный реестр через ``register(...)``.
"""
from __future__ import annotations

from dnd.application.engine.spells.effect_handler import SpellEffectRegistry
from dnd.application.engine.spells.handlers import (
    AttackSpellHandler,
    AutoSpellHandler,
    SaveSpellHandler,
)
from dnd.domain.values.spell import SpellEffect


def default_spell_effect_registry() -> SpellEffectRegistry:
    registry = SpellEffectRegistry()
    registry.register(SpellEffect.ATTACK, AttackSpellHandler())
    registry.register(SpellEffect.SAVE, SaveSpellHandler())
    registry.register(SpellEffect.AUTO, AutoSpellHandler())
    # HEAL / BUFF — добавляются в P1-7..8.
    return registry


__all__ = ["default_spell_effect_registry"]

"""SpellEffectHandler + SpellEffectRegistry — расширяемая обработка эффектов.

Каждый тип эффекта заклинания (:class:`SpellEffect`) обрабатывает свой хендлер.
Реестр (open/closed): новый тип воздействия = новый хендлер + ``register(...)``,
без касания ``CastSpellAction`` и существующих хендлеров.

Интерфейс принимает **кортеж целей** — задел под P2 (AoE/мультитаргет): в P1
кортеж всегда из одной цели, хендлеры не придётся менять, когда появится
резолвинг нескольких целей.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.spell import Spell, SpellEffect


@runtime_checkable
class SpellEffectHandler(Protocol):
    """Обработчик одного типа эффекта заклинания."""

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        """Применить эффект ``spell`` от ``caster`` к ``targets``.

        Хендлер сам публикует свои события (урон/хил/бафф) через
        ``ctx.event_bus``. ``CastSpellAction`` уже опубликовал ``SpellCast`` и
        списал слот/экономику до вызова.
        """
        ...


class SpellEffectRegistry:
    """Реестр {SpellEffect → SpellEffectHandler}."""

    def __init__(self) -> None:
        self._handlers: dict[SpellEffect, SpellEffectHandler] = {}

    def register(self, effect: SpellEffect, handler: SpellEffectHandler) -> None:
        if effect in self._handlers:
            raise ValueError(f"spell effect handler already registered: {effect}")
        self._handlers[effect] = handler

    def get(self, effect: SpellEffect) -> SpellEffectHandler:
        if effect not in self._handlers:
            raise KeyError(f"no handler registered for spell effect: {effect}")
        return self._handlers[effect]

    def __contains__(self, effect: SpellEffect) -> bool:
        return effect in self._handlers


__all__ = ["SpellEffectHandler", "SpellEffectRegistry"]

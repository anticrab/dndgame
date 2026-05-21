"""Порт ``DiceRoller`` — семантический слой бросков движка.

Контракт зафиксирован в ``docs/ENGINE.md`` §7. Главные обязательства
любой реализации:

1. **Единая точка входа.** Все правила домена (``attack_roll``, ``save``,
   ``ability_check``, ``damage_roll``) делают броски только через
   ``DiceRoller``. Прямой ``DiceExpr.roll(rng)`` остаётся легитимным
   лишь в трёх случаях: генерация stats в CharacterBuilder, внутренние
   unit-тесты механики костей и **внутри** реализаций DiceRoller-а.

2. **Двухфазная модель.** На каждый бросок реализация публикует пару
   событий через ``EventBus`` — сначала ``RollIssued``, потом
   ``RollApplied``. Между ними мастер может вмешаться (см.
   ``MasterIntent.reroll`` / ``set_roll``). Уникальный
   ``EngineRollResult.roll_id`` совпадает в обоих событиях и
   используется мастером для адресации.

3. **Доп. кости.** ``RollContext.extra_dice`` — список сериализованных
   DiceExpr (например, ``"1d4"`` от Bless или ``"2d6"`` от Sneak Attack
   на крите). Реализация бросает каждую и суммирует в ``total``;
   результаты этих костей возвращаются отдельно в
   ``EngineRollResult.extra_dice_rolls`` для аудита и UI.

4. **Преимущество/помеха/крит.** Прокидываются в ``DiceExpr.roll`` и
   ложатся в флаги ``EngineRollResult``. На не-d20 advantage/disadvantage
   запрещены (см. ``domain/values/dice.py`` — там ``ValueError``).

Реализация по умолчанию — ``ComputerDiceRoller`` в
``application/engine/dice_roller.py``.
"""

from __future__ import annotations

from typing import Protocol

from dnd.application.dto.rolls import EngineRollResult, RollContext
from dnd.domain.values.dice import DiceExpr


class DiceRoller(Protocol):
    """Семантический слой бросков движка. См. ``docs/ENGINE.md`` §7."""

    def roll(self, expr: DiceExpr, ctx: RollContext) -> EngineRollResult:
        """Бросить ``expr`` в контексте ``ctx``.

        Обязательства:

        * Публикует ``RollIssued`` до возврата.
        * Применяет преимущество/помеху/крит из ``ctx``.
        * Бросает дополнительно ``ctx.extra_dice`` и включает их в total.
        * Публикует ``RollApplied`` с тем же ``roll_id``.
        * Возвращает иммутабельный :class:`EngineRollResult`.
        """

"""``ComputerDiceRoller`` — реализация порта ``DiceRoller`` поверх ``RNG``.

Семантика — ``docs/ENGINE.md`` §7. Двухфазная модель публикации событий
(``RollIssued`` → ``RollApplied``) с одинаковым ``roll_id``.

В MVP вмешательство мастера между двумя событиями не реализовано:
оба события публикуются последовательно. Когда появится
``LiveGameMaster``, в этом месте появится интерсептор-хук «проверь
ожидающие master operations для roll_id и применяй их к result», но
сам контракт DiceRoller от этого не меняется.

Архитектурная заметка. ``ComputerDiceRoller`` живёт в
``application/engine/``, потому что:

* DiceRoller — application-уровневая абстракция (знает про EventBus,
  про RollContext-DTO);
* реализация использует domain-VO ``DiceExpr`` и driven-порт ``RNG``;
* других реализаций пока нет, но ``LiveDiceRoller`` (ввод значения
  игроком) встанет рядом без переделок.
"""

from __future__ import annotations

from dnd.application.dto.engine_event import RollApplied, RollIssued
from dnd.application.dto.rolls import EngineRollResult, RollContext, make_roll_id
from dnd.application.ports.dice_roller import DiceRoller
from dnd.application.ports.event_bus import EventBus
from dnd.domain.ports.rng import RNG
from dnd.domain.values.dice import DiceExpr


class ComputerDiceRoller(DiceRoller):
    """Бросает кости через ``RNG``. Публикует пару событий на каждый бросок.

    Не потокобезопасен — этого не требуется (пошаговая игра).
    """

    def __init__(self, rng: RNG, event_bus: EventBus) -> None:
        self._rng = rng
        self._bus = event_bus

    def roll(self, expr: DiceExpr, ctx: RollContext) -> EngineRollResult:
        """См. контракт ``DiceRoller.roll``.

        Алгоритм:

        1. Бросаем основное выражение ``expr`` с флагами из ``ctx``.
        2. Бросаем каждое выражение из ``ctx.extra_dice`` без флагов
           (advantage/disadvantage применимы только к одиночному d20,
           а extra_dice — это всегда кости урона/бонусов).
        3. Собираем итоговый :class:`EngineRollResult`, складывая total.
        4. Публикуем ``RollIssued``, затем ``RollApplied`` (одинаковый
           ``roll_id``). В MVP между ними ничего не происходит.
        """
        main = expr.roll(
            self._rng,
            advantage=ctx.advantage,
            disadvantage=ctx.disadvantage,
            crit=ctx.crit,
        )

        # Книга 2024 стр. 12 «Критические попадания»: «все кости урона
        # удваиваются». Это включает доп. кости (Sneak Attack, Divine
        # Smite, дополнительные кости от заклинаний-баффов). На
        # purpose != DAMAGE значение `ctx.crit` обычно False, так что
        # для атак/спасбросков extra_dice (Bless +1d4, Guidance +1d4)
        # пройдут с `crit=False` — это правильно, к атаке крит не
        # применяется.
        # Advantage/disadvantage в extra_dice НЕ пробрасываются: они
        # применимы только к одиночному d20 основного броска (Bless'овский
        # d4 не получает преимущества).
        extra_rolls: list[int] = []
        extra_total = 0
        for extra_expr_text in ctx.extra_dice:
            extra_expr = DiceExpr.parse(extra_expr_text)
            extra_result = extra_expr.roll(self._rng, crit=ctx.crit)
            extra_rolls.extend(extra_result.kept)
            extra_total += extra_result.total

        result = EngineRollResult(
            roll_id=make_roll_id(),
            expr=str(expr),
            raw=main.rolls,
            kept=main.kept,
            modifier=main.modifier,
            extra_dice_rolls=tuple(extra_rolls),
            total=main.total + extra_total,
            advantage=main.advantage,
            disadvantage=main.disadvantage,
            crit=main.crit,
            context=ctx,
        )

        # Контракт §7.4 — пара событий с одинаковым roll_id.
        # Tags из context дублируются на оба события для удобной
        # фильтрации в подписчиках (например, "master_intervention").
        self._bus.publish(RollIssued(tags=ctx.tags, result=result))
        # Здесь, при появлении LiveGameMaster, будет hook на проверку
        # ожидающих переборосов по `result.roll_id`. См. ENGINE.md §7.4.
        self._bus.publish(RollApplied(tags=ctx.tags, result=result))

        return result

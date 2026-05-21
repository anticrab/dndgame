"""Тесты костей и нотации."""

from __future__ import annotations

import pytest

from dnd.domain.values.dice import DiceExpr, DiceParseError
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def test_parse_d20() -> None:
    expr = DiceExpr.parse("d20")
    assert expr.count == 1
    assert expr.sides == 20
    assert expr.modifier == 0


def test_parse_with_modifier_and_keep() -> None:
    expr = DiceExpr.parse("4d6kh3")
    assert (expr.count, expr.sides, expr.keep_highest) == (4, 6, 3)
    expr2 = DiceExpr.parse("2d6+3")
    assert expr2.modifier == 3


def test_parse_cyrillic_k() -> None:
    expr = DiceExpr.parse("1к20+5")
    assert expr.sides == 20
    assert expr.modifier == 5


def test_parse_rejects_garbage() -> None:
    with pytest.raises(DiceParseError):
        DiceExpr.parse("hello")


def test_simple_roll_two_d6() -> None:
    rng = ScriptedRNG([4, 2])
    result = DiceExpr.parse("2d6+3").roll(rng)
    assert result.rolls == (4, 2)
    assert result.total == 4 + 2 + 3


def test_keep_highest_3_of_4d6() -> None:
    # 4к6, оставить 3 старших — классическая генерация stats
    rng = ScriptedRNG([1, 6, 4, 5])
    result = DiceExpr.parse("4d6kh3").roll(rng)
    assert sorted(result.kept, reverse=True) == [6, 5, 4]
    assert result.dropped == (1,)
    assert result.total == 6 + 5 + 4


def test_advantage_picks_higher_of_two_d20() -> None:
    rng = ScriptedRNG([7, 19])
    result = DiceExpr.parse("d20+5").roll(rng, advantage=True)
    assert result.total == 19 + 5
    assert result.advantage is True


def test_disadvantage_picks_lower() -> None:
    rng = ScriptedRNG([7, 19])
    result = DiceExpr.parse("d20+5").roll(rng, disadvantage=True)
    assert result.total == 7 + 5


def test_advantage_and_disadvantage_cancel() -> None:
    # При одновременном преимуществе и помехе бросаем один к20 без бонуса
    rng = ScriptedRNG([12])
    result = DiceExpr.parse("d20").roll(rng, advantage=True, disadvantage=True)
    assert result.total == 12
    assert result.advantage is False and result.disadvantage is False


def test_natural_20_and_1_flags() -> None:
    rng = ScriptedRNG([20])
    nat20 = DiceExpr.parse("d20+5").roll(rng)
    assert nat20.is_natural_20

    rng2 = ScriptedRNG([1])
    nat1 = DiceExpr.parse("d20+5").roll(rng2)
    assert nat1.is_natural_1


def test_crit_doubles_dice_but_not_modifier() -> None:
    """Книга: «кости урона удваиваются, модификатор — нет»."""
    # 1d8+3, крит → бросаем 2 кости и добавляем +3 один раз.
    rng = ScriptedRNG([5, 7])
    result = DiceExpr.parse("1d8+3").roll(rng, crit=True)
    assert result.rolls == (5, 7)
    assert result.total == 5 + 7 + 3


def test_str_round_trip() -> None:
    for text in ("1d20", "2d6+3", "4d6kh3", "1d20-1", "8d6"):
        expr = DiceExpr.parse(text)
        # __str__ нормализует, не обязан совпадать буквально:
        assert DiceExpr.parse(str(expr)) == expr

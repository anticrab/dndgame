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


@pytest.mark.parametrize(
    "bad_input",
    [
        "",
        "hello",
        "d",
        "1d",
        "+5",
        "0d6",
        "1d0",
        "2d6kh5",  # keep > count
        "0d20kh0",  # 0 dice
    ],
)
def test_parse_rejects_garbage(bad_input: str) -> None:
    """K-011: все некорректные формы должны давать DiceParseError."""
    with pytest.raises(DiceParseError):
        DiceExpr.parse(bad_input)


def test_simple_roll_two_d6() -> None:
    rng = ScriptedRNG([4, 2])
    result = DiceExpr.parse("2d6+3").roll(rng)
    assert result.rolls == (4, 2)
    assert result.total == 4 + 2 + 3


@pytest.mark.rules
def test_keep_highest_3_of_4d6() -> None:
    # 4к6, оставить 3 старших — классическая генерация stats
    rng = ScriptedRNG([1, 6, 4, 5])
    result = DiceExpr.parse("4d6kh3").roll(rng)
    assert sorted(result.kept, reverse=True) == [6, 5, 4]
    assert result.dropped == (1,)
    assert result.total == 6 + 5 + 4


def test_keep_lowest_works() -> None:
    """K-010: ранее не покрытое — keep_lowest."""
    rng = ScriptedRNG([6, 5, 4, 1])
    r = DiceExpr.parse("4d6kl1").roll(rng)
    assert r.kept == (1,)
    assert set(r.dropped) == {4, 5, 6}
    assert r.total == 1


@pytest.mark.rules
def test_advantage_picks_higher_of_two_d20() -> None:
    rng = ScriptedRNG([7, 19])
    result = DiceExpr.parse("d20+5").roll(rng, advantage=True)
    assert result.total == 19 + 5
    assert result.advantage is True


@pytest.mark.rules
def test_disadvantage_picks_lower() -> None:
    rng = ScriptedRNG([7, 19])
    result = DiceExpr.parse("d20+5").roll(rng, disadvantage=True)
    assert result.total == 7 + 5


@pytest.mark.rules
def test_advantage_and_disadvantage_cancel() -> None:
    # При одновременном преимуществе и помехе бросаем один к20 без бонуса
    rng = ScriptedRNG([12])
    result = DiceExpr.parse("d20").roll(rng, advantage=True, disadvantage=True)
    assert result.total == 12
    assert result.advantage is False and result.disadvantage is False


def test_advantage_on_non_d20_raises() -> None:
    """K-004: advantage/disadvantage применимы только к одиночному d20.

    Книга (стр. 11): «Преимущество отражает благоприятные обстоятельства
    [и применяется] на тест к20». Применять к 2d6/4d6kh3/броску урона —
    программная ошибка, не «удобно для единообразия API».
    """
    rng = ScriptedRNG([4, 3])
    with pytest.raises(ValueError, match="single d20"):
        DiceExpr.parse("2d6").roll(rng, advantage=True)
    with pytest.raises(ValueError, match="single d20"):
        DiceExpr.parse("4d6kh3").roll(rng, disadvantage=True)


@pytest.mark.rules
def test_natural_20_and_1_flags() -> None:
    rng = ScriptedRNG([20])
    nat20 = DiceExpr.parse("d20+5").roll(rng)
    assert nat20.is_natural_20
    assert nat20.d20_raw == 20

    rng2 = ScriptedRNG([1])
    nat1 = DiceExpr.parse("d20+5").roll(rng2)
    assert nat1.is_natural_1
    assert nat1.d20_raw == 1


def test_natural_20_with_advantage() -> None:
    """K-013: нат.20 на одном из двух при преимуществе — корректно засчитывается."""
    rng = ScriptedRNG([7, 20])
    r = DiceExpr.parse("d20+5").roll(rng, advantage=True)
    assert r.is_natural_20 is True
    assert r.d20_raw == 20


def test_d20_raw_returns_none_for_other_expr() -> None:
    rng = ScriptedRNG([3, 5])
    r = DiceExpr.parse("2d6").roll(rng)
    assert r.d20_raw is None


@pytest.mark.rules
def test_crit_doubles_dice_but_not_modifier() -> None:
    """Книга (стр. 12): «кости урона удваиваются, модификатор — нет»."""
    rng = ScriptedRNG([5, 7])
    result = DiceExpr.parse("1d8+3").roll(rng, crit=True)
    assert result.rolls == (5, 7)
    assert result.total == 5 + 7 + 3


@pytest.mark.rules
def test_crit_doubles_extra_damage_dice() -> None:
    """K-007: крит на доп. кости (Скрытая атака плута 2d6) тоже удваивает."""
    rng = ScriptedRNG([6, 5, 4, 3])  # 2d6 → 4d6 при крите
    r = DiceExpr.parse("2d6").roll(rng, crit=True)
    assert r.rolls == (6, 5, 4, 3)
    assert r.total == 6 + 5 + 4 + 3


def test_str_round_trip() -> None:
    for text in ("1d20", "2d6+3", "4d6kh3", "1d20-1", "8d6", "4d6kl1"):
        expr = DiceExpr.parse(text)
        # __str__ нормализует, не обязан совпадать буквально:
        assert DiceExpr.parse(str(expr)) == expr


def test_str_normalizes_zero_modifier() -> None:
    """K-008: `+0` отбрасывается при сериализации."""
    expr = DiceExpr.parse("1d20+0")
    assert str(expr) == "1d20"
    assert expr.modifier == 0


def test_scripted_rng_exhausted_raises_index_error() -> None:
    rng = ScriptedRNG([5])
    rng.roll(6)
    with pytest.raises(IndexError, match="exhausted"):
        rng.roll(6)


def test_scripted_rng_out_of_range_raises_value_error() -> None:
    rng = ScriptedRNG([7])
    with pytest.raises(ValueError, match="out of range"):
        rng.roll(6)


def test_describe_basic() -> None:
    rng = ScriptedRNG([4, 2])
    r = DiceExpr.parse("2d6+3").roll(rng)
    text = r.describe()
    assert "2d6+3" in text
    assert "4,2" in text
    assert "= 9" in text


def test_describe_advantage_and_dropped() -> None:
    rng = ScriptedRNG([7, 19])
    r = DiceExpr.parse("d20+5").roll(rng, advantage=True)
    text = r.describe()
    assert "with advantage" in text
    assert "dropped" in text


def test_describe_crit() -> None:
    rng = ScriptedRNG([5, 7])
    r = DiceExpr.parse("1d8+3").roll(rng, crit=True)
    assert "crit" in r.describe()


def test_describe_disadvantage() -> None:
    rng = ScriptedRNG([7, 19])
    r = DiceExpr.parse("d20").roll(rng, disadvantage=True)
    assert "with disadvantage" in r.describe()

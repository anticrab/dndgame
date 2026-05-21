"""Тесты характеристик и модификаторов."""

from __future__ import annotations

import pytest

from dnd.domain.values.ability import Ability, AbilityScore, AbilityScores, modifier


@pytest.mark.parametrize(
    "score,expected",
    [
        (1, -5),
        (2, -4),
        (3, -4),
        (8, -1),
        (9, -1),
        (10, 0),
        (11, 0),
        (12, 1),
        (15, 2),
        (20, 5),
        (30, 10),
    ],
)
def test_modifier_matches_table(score: int, expected: int) -> None:
    """Таблица модификаторов из книги (стр. 9)."""
    assert modifier(score) == expected


def test_modifier_rejects_zero_and_below() -> None:
    with pytest.raises(ValueError):
        modifier(0)


def test_ability_score_validates_range() -> None:
    with pytest.raises(ValueError):
        AbilityScore(Ability.STR, 0)
    with pytest.raises(ValueError):
        AbilityScore(Ability.STR, 31)


def test_ability_score_adjusted_respects_cap() -> None:
    score = AbilityScore(Ability.STR, 19)
    assert score.adjusted(2).score == 20
    # понижение игнорирует cap
    assert score.adjusted(-3).score == 16


def test_ability_scores_lookup_and_modifier() -> None:
    scores = AbilityScores.of(str_=15, dex=14, con=13, int_=12, wis=10, cha=8)
    assert scores.get(Ability.STR).score == 15
    assert scores.modifier(Ability.STR) == 2
    assert scores.modifier(Ability.CHA) == -1

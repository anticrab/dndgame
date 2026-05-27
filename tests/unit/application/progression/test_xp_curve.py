"""R1-3: XP-кривые."""

from __future__ import annotations

import pytest

from dnd.application.engine.progression.xp_curve import (
    FastXpCurve,
    MilestoneXpCurve,
    make_xp_curve,
)


def test_fast_thresholds() -> None:
    c = FastXpCurve()
    assert c.threshold(2) == 100
    assert c.threshold(3) == 250
    assert c.threshold(4) == 500


def test_fast_level_for_xp() -> None:
    c = FastXpCurve()
    assert c.level_for_xp(0) == 1
    assert c.level_for_xp(99) == 1
    assert c.level_for_xp(100) == 2
    assert c.level_for_xp(260) == 3
    assert c.level_for_xp(10_000) == 20  # клампится верхним уровнем таблицы


def test_milestone_never_advances_by_xp() -> None:
    c = MilestoneXpCurve()
    assert c.level_for_xp(999) == 1  # milestone: рост по событиям, не по XP


def test_factory() -> None:
    assert isinstance(make_xp_curve("fast"), FastXpCurve)
    with pytest.raises(ValueError):
        make_xp_curve("nope")

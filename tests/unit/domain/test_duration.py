"""Duration — игровое время в раундах (X0)."""

from __future__ import annotations

import pytest

from dnd.domain.values.duration import Duration, DurationUnit


def test_instant_is_zero_rounds() -> None:
    assert Duration.instant().to_rounds() == 0
    assert Duration.instant().unit is DurationUnit.INSTANT


def test_rounds_minutes_hours_conversion() -> None:
    assert Duration.rounds(3).to_rounds() == 3
    assert Duration.minutes(1).to_rounds() == 10
    assert Duration.hours(1).to_rounds() == 600


def test_unbounded_durations_are_none() -> None:
    assert Duration(DurationUnit.PERMANENT).to_rounds() is None
    assert Duration(DurationUnit.UNTIL_ENCOUNTER_END).to_rounds() is None


def test_concentration_cap_in_minutes() -> None:
    assert Duration.concentration(cap_min=1).to_rounds() == 10
    assert Duration.concentration(cap_min=10).to_rounds() == 100
    assert Duration.concentration().to_rounds() is None


def test_positive_amount_required() -> None:
    with pytest.raises(ValueError, match="amount"):
        Duration(DurationUnit.ROUNDS, 0)

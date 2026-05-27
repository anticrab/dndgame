"""GameClock — монотонные игровые часы в раундах (X0)."""

from __future__ import annotations

import pytest

from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.duration import Duration


def test_starts_at_zero_and_advances() -> None:
    clock = GameClock()
    assert clock.now_round == 0
    clock.advance(1)
    assert clock.now_round == 1
    clock.advance_minutes(1)  # +10
    assert clock.now_round == 11
    clock.advance_hours(1)  # +600
    assert clock.now_round == 611


def test_advance_rejects_negative() -> None:
    with pytest.raises(ValueError, match="rounds"):
        GameClock().advance(-1)


def test_expires_at_counts_from_now() -> None:
    clock = GameClock()
    clock.advance(5)
    assert clock.expires_at(Duration.minutes(1)) == 15  # 5 + 10
    assert clock.expires_at(Duration.instant()) == 5
    assert clock.expires_at(Duration.concentration()) is None

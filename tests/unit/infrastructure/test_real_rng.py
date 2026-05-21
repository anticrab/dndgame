"""Тесты RealRNG — реальной реализации порта на random.Random."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dnd.infrastructure.rng.real_rng import RealRNG


def test_real_rng_basic_d20_in_range() -> None:
    rng = RealRNG(seed=42)
    for _ in range(50):
        v = rng.roll(20)
        assert 1 <= v <= 20


def test_real_rng_reproducible_with_seed() -> None:
    """Один и тот же seed даёт одну и ту же последовательность."""
    a = RealRNG(seed=12345)
    b = RealRNG(seed=12345)
    seq_a = [a.roll(20) for _ in range(20)]
    seq_b = [b.roll(20) for _ in range(20)]
    assert seq_a == seq_b


def test_real_rng_different_seeds_diverge() -> None:
    a = RealRNG(seed=1)
    b = RealRNG(seed=2)
    seq_a = [a.roll(100) for _ in range(50)]
    seq_b = [b.roll(100) for _ in range(50)]
    assert seq_a != seq_b


def test_real_rng_rejects_zero_and_negative_sides() -> None:
    rng = RealRNG(seed=0)
    with pytest.raises(ValueError, match="die sides must be >= 1"):
        rng.roll(0)
    with pytest.raises(ValueError, match="die sides must be >= 1"):
        rng.roll(-1)


def test_real_rng_d1_always_returns_one() -> None:
    rng = RealRNG(seed=999)
    for _ in range(20):
        assert rng.roll(1) == 1


@pytest.mark.property
@given(
    sides=st.integers(min_value=1, max_value=1000),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_real_rng_property_within_range(sides: int, seed: int) -> None:
    """Бросок d-X всегда в [1, X] независимо от сида и числа граней."""
    rng = RealRNG(seed=seed)
    for _ in range(10):
        v = rng.roll(sides)
        assert 1 <= v <= sides

"""Тесты типов урона и множителей."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dnd.domain.values.damage import (
    DamageInstance,
    DamageMultiplier,
    DamageType,
    apply_damage_multiplier,
    combine_multipliers,
)


def test_damage_types_canonical_list() -> None:
    """Книга 2024 (стр. 26): 13 типов урона."""
    assert len(DamageType) == 13
    expected = {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }
    assert {t.value for t in DamageType} == expected


def test_damage_instance_rejects_negative() -> None:
    with pytest.raises(ValueError, match="damage amount must be >= 0"):
        DamageInstance(-1, DamageType.FIRE)


def test_damage_instance_allows_zero() -> None:
    """Урон 0 валиден: атака может попасть, но нанести 0 (например, штраф)."""
    di = DamageInstance(0, DamageType.PIERCING)
    assert di.amount == 0


@pytest.mark.rules
@pytest.mark.parametrize(
    "amount,multiplier,expected",
    [
        (10, DamageMultiplier.NORMAL, 10),
        (10, DamageMultiplier.RESISTANT, 5),
        (10, DamageMultiplier.VULNERABLE, 20),
        (10, DamageMultiplier.IMMUNE, 0),
        (1, DamageMultiplier.RESISTANT, 0),  # ÷2 округляется вниз
        (3, DamageMultiplier.RESISTANT, 1),
        (0, DamageMultiplier.VULNERABLE, 0),
        (0, DamageMultiplier.IMMUNE, 0),
        (7, DamageMultiplier.VULNERABLE, 14),
    ],
)
def test_apply_damage_multiplier_table(
    amount: int, multiplier: DamageMultiplier, expected: int
) -> None:
    """Таблица применения множителей по книге (стр. 26)."""
    assert apply_damage_multiplier(amount, multiplier) == expected


def test_apply_damage_multiplier_rejects_negative() -> None:
    with pytest.raises(ValueError):
        apply_damage_multiplier(-1, DamageMultiplier.NORMAL)


@pytest.mark.rules
@pytest.mark.parametrize(
    "resistant,vulnerable,immune,expected",
    [
        (False, False, False, DamageMultiplier.NORMAL),
        (True, False, False, DamageMultiplier.RESISTANT),
        (False, True, False, DamageMultiplier.VULNERABLE),
        (False, False, True, DamageMultiplier.IMMUNE),
        # immune перекрывает всё
        (True, True, True, DamageMultiplier.IMMUNE),
        (True, False, True, DamageMultiplier.IMMUNE),
        (False, True, True, DamageMultiplier.IMMUNE),
        # книга: resist+vulnerable одновременно — гасятся
        (True, True, False, DamageMultiplier.NORMAL),
    ],
)
def test_combine_multipliers_table(
    resistant: bool, vulnerable: bool, immune: bool, expected: DamageMultiplier
) -> None:
    assert combine_multipliers(resistant, vulnerable, immune) == expected


@pytest.mark.property
@given(amount=st.integers(min_value=0, max_value=10_000))
def test_immune_always_yields_zero(amount: int) -> None:
    assert apply_damage_multiplier(amount, DamageMultiplier.IMMUNE) == 0


@pytest.mark.property
@given(amount=st.integers(min_value=0, max_value=10_000))
def test_normal_is_identity(amount: int) -> None:
    assert apply_damage_multiplier(amount, DamageMultiplier.NORMAL) == amount


@pytest.mark.property
@given(amount=st.integers(min_value=0, max_value=10_000))
def test_vulnerable_doubles(amount: int) -> None:
    assert apply_damage_multiplier(amount, DamageMultiplier.VULNERABLE) == amount * 2


@pytest.mark.property
@given(amount=st.integers(min_value=0, max_value=10_000))
def test_resistant_halves_rounded_down(amount: int) -> None:
    """Свойство: RESISTANT(N) == N // 2 для любых N >= 0."""
    assert apply_damage_multiplier(amount, DamageMultiplier.RESISTANT) == amount // 2


@pytest.mark.property
@given(amount=st.integers(min_value=0, max_value=10_000))
def test_resist_then_vulnerable_does_not_overshoot(amount: int) -> None:
    """Свойство: применение «обоих» (по combine) даёт NORMAL, т.е. идентичность."""
    result = apply_damage_multiplier(
        amount, combine_multipliers(resistant=True, vulnerable=True, immune=False)
    )
    assert result == amount

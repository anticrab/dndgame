"""Тесты HitPoints — book-rule fidelity для урона/лечения/временных хитов.

Книга 2024, «Урон и лечение», стр. 26–27.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from dnd.domain.values.hit_points import HitPoints

# ---------- Стратегии для property-based -----------------------------------

_hp_ints = st.integers(min_value=0, max_value=10_000)


@st.composite
def _hp_state(draw: st.DrawFn) -> HitPoints:
    maximum = draw(st.integers(min_value=0, max_value=500))
    current = draw(st.integers(min_value=0, max_value=maximum))
    temporary = draw(st.integers(min_value=0, max_value=500))
    return HitPoints(current=current, maximum=maximum, temporary=temporary)


# ---------- Инварианты конструктора ----------------------------------------


def test_constructor_basic() -> None:
    hp = HitPoints(current=12, maximum=18)
    assert hp.current == 12
    assert hp.maximum == 18
    assert hp.temporary == 0


def test_constructor_rejects_negative_max() -> None:
    with pytest.raises(ValueError, match="max HP must be >= 0"):
        HitPoints(current=0, maximum=-1)


def test_constructor_rejects_current_exceeds_max() -> None:
    with pytest.raises(ValueError, match="out of range"):
        HitPoints(current=20, maximum=18)


def test_constructor_rejects_negative_current() -> None:
    with pytest.raises(ValueError, match="out of range"):
        HitPoints(current=-1, maximum=18)


def test_constructor_rejects_negative_temp() -> None:
    with pytest.raises(ValueError, match="temp HP must be >= 0"):
        HitPoints(current=10, maximum=10, temporary=-1)


# ---------- Состояния ------------------------------------------------------


def test_unconscious_at_zero() -> None:
    hp = HitPoints(current=0, maximum=10)
    assert hp.is_at_zero is True
    assert HitPoints(current=1, maximum=10).is_at_zero is False


def test_at_full() -> None:
    assert HitPoints(10, 10).is_at_full is True
    assert HitPoints(9, 10).is_at_full is False


# ---------- take_damage ----------------------------------------------------


@pytest.mark.rules
def test_take_damage_basic() -> None:
    hp = HitPoints(current=18, maximum=20).take_damage(5)
    assert hp.current == 13
    assert hp.maximum == 20
    assert hp.temporary == 0


@pytest.mark.rules
def test_take_damage_floor_at_zero() -> None:
    """Книга: текущие хиты не уходят ниже 0 (для целей этой структуры)."""
    hp = HitPoints(current=5, maximum=20).take_damage(100)
    assert hp.current == 0


@pytest.mark.rules
def test_take_damage_consumes_temp_first() -> None:
    """Книга (стр. 27): «временные хиты теряются первыми»."""
    hp = HitPoints(current=10, maximum=20, temporary=5).take_damage(3)
    assert hp.current == 10
    assert hp.temporary == 2


@pytest.mark.rules
def test_take_damage_overflow_temp_to_current() -> None:
    """Лишний урон по временным переносится на текущие."""
    hp = HitPoints(current=10, maximum=20, temporary=5).take_damage(8)
    assert hp.current == 10 - 3
    assert hp.temporary == 0


def test_take_damage_zero_is_noop() -> None:
    hp = HitPoints(current=10, maximum=20, temporary=3)
    assert hp.take_damage(0) == hp


def test_take_damage_rejects_negative() -> None:
    with pytest.raises(ValueError, match="damage must be >= 0"):
        HitPoints(10, 10).take_damage(-1)


# ---------- heal -----------------------------------------------------------


@pytest.mark.rules
def test_heal_basic() -> None:
    hp = HitPoints(current=5, maximum=20).heal(7)
    assert hp.current == 12


@pytest.mark.rules
def test_heal_caps_at_maximum() -> None:
    """Книга: лечение не превышает максимум хитов."""
    hp = HitPoints(current=15, maximum=20).heal(100)
    assert hp.current == 20


def test_heal_does_not_touch_temp() -> None:
    hp = HitPoints(current=5, maximum=20, temporary=4).heal(7)
    assert hp.current == 12
    assert hp.temporary == 4


def test_heal_zero_is_noop() -> None:
    hp = HitPoints(current=5, maximum=20)
    assert hp.heal(0) == hp


def test_heal_rejects_negative() -> None:
    with pytest.raises(ValueError):
        HitPoints(10, 10).heal(-1)


# ---------- with_temporary -------------------------------------------------


@pytest.mark.rules
def test_temp_hp_replaces_smaller() -> None:
    """Книга (стр. 27): «временные хиты не складываются; выбираете лучший вариант»."""
    hp = HitPoints(current=10, maximum=20, temporary=3).with_temporary(8)
    assert hp.temporary == 8


@pytest.mark.rules
def test_temp_hp_keeps_larger() -> None:
    """Если новые меньше старых — оставляем старые."""
    hp = HitPoints(current=10, maximum=20, temporary=10).with_temporary(4)
    assert hp.temporary == 10


def test_temp_hp_rejects_negative() -> None:
    with pytest.raises(ValueError):
        HitPoints(10, 10).with_temporary(-1)


# ---------- with_maximum ---------------------------------------------------


def test_with_maximum_keeps_current_when_above() -> None:
    hp = HitPoints(current=15, maximum=20).with_maximum(30)
    assert hp.current == 15
    assert hp.maximum == 30


@pytest.mark.rules
def test_with_maximum_clamps_current_when_below() -> None:
    """Книга: если максимум опускается ниже текущих, текущие тоже снижаются."""
    hp = HitPoints(current=15, maximum=20).with_maximum(10)
    assert hp.current == 10
    assert hp.maximum == 10


def test_with_maximum_rejects_negative() -> None:
    with pytest.raises(ValueError):
        HitPoints(10, 10).with_maximum(-1)


# ---------- restored_to_full ----------------------------------------------


@pytest.mark.rules
def test_restored_to_full_resets_current_and_drops_temp() -> None:
    """Книга: продолжительный отдых восстанавливает все хиты и СНИМАЕТ временные."""
    hp = HitPoints(current=2, maximum=18, temporary=5).restored_to_full()
    assert hp.current == 18
    assert hp.maximum == 18
    assert hp.temporary == 0


# ---------- Property-based --------------------------------------------------


@pytest.mark.property
@given(state=_hp_state(), damage=_hp_ints)
def test_property_take_damage_never_goes_negative(state: HitPoints, damage: int) -> None:
    new = state.take_damage(damage)
    assert new.current >= 0
    assert new.temporary >= 0
    assert new.maximum == state.maximum


@pytest.mark.property
@given(state=_hp_state(), heal=_hp_ints)
def test_property_heal_never_exceeds_max(state: HitPoints, heal: int) -> None:
    new = state.heal(heal)
    assert new.current <= new.maximum
    assert new.maximum == state.maximum


@pytest.mark.property
@given(state=_hp_state(), damage=_hp_ints, heal=_hp_ints)
def test_property_round_trip_under_full_heal_after_damage(
    state: HitPoints, damage: int, heal: int
) -> None:
    """Свойство: если урон <= total HP и затем лечим до максимума —
    дойдём до максимума."""
    assume(state.maximum > 0)
    after_damage = state.take_damage(damage)
    after_heal = after_damage.heal(after_damage.maximum)  # с запасом
    assert after_heal.current == state.maximum


@pytest.mark.property
@given(state=_hp_state(), new_temp=_hp_ints)
def test_property_temp_hp_is_monotonically_non_decreasing_per_call(
    state: HitPoints, new_temp: int
) -> None:
    """`with_temporary` никогда не уменьшает текущие временные хиты."""
    after = state.with_temporary(new_temp)
    assert after.temporary >= state.temporary

"""Тесты DeathSaveState — буквально по книге 2024, стр. 27.

Каждый сценарий из подраздела «Падение до 0 хитов» — отдельный тест.
"""

from __future__ import annotations

import pytest

from dnd.domain.values.death_save_state import DeathSaveState

# -- инициализация --------------------------------------------------------


def test_fresh_state_is_neutral() -> None:
    s = DeathSaveState()
    assert s.successes == 0
    assert s.failures == 0
    assert s.stable is False
    assert s.is_dead is False
    assert s.is_stable is False


def test_constructor_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="successes"):
        DeathSaveState(successes=4)
    with pytest.raises(ValueError, match="failures"):
        DeathSaveState(failures=-1)


# -- apply_save_roll: пороги ---------------------------------------------


@pytest.mark.rules
def test_roll_10_or_higher_is_success() -> None:
    """Книга: «10 или больше — успех»."""
    for n in (10, 11, 15, 19):
        s = DeathSaveState().apply_save_roll(n)
        assert s.successes == 1
        assert s.failures == 0


@pytest.mark.rules
def test_roll_below_10_is_failure() -> None:
    """Книга: «меньше 10 — провал»."""
    for n in (2, 5, 9):
        s = DeathSaveState().apply_save_roll(n)
        assert s.successes == 0
        assert s.failures == 1


@pytest.mark.rules
def test_nat_20_recovers() -> None:
    """Книга: «нат-20 — восстанавливаете 1 HP».

    На уровне VO это значит: счётчики сбрасываются. Само
    восстановление 1 HP — забота Character, который интерпретирует
    «после нат-20 я живой».
    """
    s = DeathSaveState(successes=2, failures=2).apply_save_roll(20)
    assert s == DeathSaveState()


@pytest.mark.rules
def test_nat_1_is_two_failures() -> None:
    """Книга: «нат-1 — два провала»."""
    s = DeathSaveState().apply_save_roll(1)
    assert s.failures == 2
    assert s.successes == 0


@pytest.mark.rules
def test_nat_1_can_finish_with_one_existing_failure() -> None:
    """Один провал + нат-1 → 3 провала → смерть."""
    s = DeathSaveState(failures=1).apply_save_roll(1)
    assert s.is_dead is True


# -- накопление до порогов ------------------------------------------------


@pytest.mark.rules
def test_three_successes_make_stable() -> None:
    s = DeathSaveState()
    for n in (10, 12, 11):
        s = s.apply_save_roll(n)
    assert s.successes == 3
    assert s.is_stable is True
    assert s.is_dead is False


@pytest.mark.rules
def test_three_failures_means_death() -> None:
    s = DeathSaveState()
    for n in (2, 5, 9):
        s = s.apply_save_roll(n)
    assert s.failures == 3
    assert s.is_dead is True


# -- терминальные состояния -----------------------------------------------


@pytest.mark.rules
def test_stable_state_does_not_roll_more() -> None:
    """Стабилизированный больше не бросает — возвращает self."""
    stable = DeathSaveState(successes=3)
    assert stable.is_stable is True
    assert stable.apply_save_roll(15) is stable
    assert stable.apply_save_roll(1) is stable


@pytest.mark.rules
def test_dead_state_does_not_change() -> None:
    """Мёртвый — терминально мёртв."""
    dead = DeathSaveState(failures=3)
    assert dead.is_dead is True
    assert dead.apply_save_roll(20) is dead


# -- apply_damage_at_zero -------------------------------------------------


@pytest.mark.rules
def test_damage_at_zero_is_one_failure() -> None:
    """Книга: «получение урона при 0 HP — один провал спасброска»."""
    s = DeathSaveState().apply_damage_at_zero()
    assert s.failures == 1


@pytest.mark.rules
def test_critical_damage_at_zero_is_two_failures() -> None:
    """Книга: «крит на бессознательном — два провала»."""
    s = DeathSaveState().apply_damage_at_zero(is_critical=True)
    assert s.failures == 2


@pytest.mark.rules
def test_critical_damage_can_kill_outright() -> None:
    """Один существующий провал + крит → 3 провала → смерть."""
    s = DeathSaveState(failures=1).apply_damage_at_zero(is_critical=True)
    assert s.is_dead is True


def test_damage_at_zero_does_nothing_on_dead_or_stable() -> None:
    """Мёртвый не становится «более мёртвым». Стабилизированный не
    получает провалов от случайного урона (но Character после этого
    снова войдёт в обычный режим спасбросков — это уже на нём)."""
    dead = DeathSaveState(failures=3)
    assert dead.apply_damage_at_zero() is dead
    stable = DeathSaveState(successes=3)
    assert stable.apply_damage_at_zero() is stable


# -- stabilized / reset ---------------------------------------------------


@pytest.mark.rules
def test_stabilized_preserves_counters() -> None:
    """Стабилизация Медициной сохраняет накопленные счётчики, но
    добавляет stable=True. Логика: если потом игрок снова получает
    урон, счётчики берутся с того места, где остановились."""
    s = DeathSaveState(successes=1, failures=2).stabilized()
    assert s.successes == 1
    assert s.failures == 2
    assert s.stable is True


def test_stabilized_does_not_revive_dead() -> None:
    dead = DeathSaveState(failures=3)
    assert dead.stabilized() is dead


def test_reset_returns_neutral_state() -> None:
    s = DeathSaveState(successes=2, failures=2, stable=False).reset()
    assert s == DeathSaveState()


# -- валидация входа ------------------------------------------------------


@pytest.mark.parametrize("bad", [0, 21, -1, 100])
def test_apply_save_roll_rejects_invalid_d20(bad: int) -> None:
    with pytest.raises(ValueError, match=r"1\.\.20"):
        DeathSaveState().apply_save_roll(bad)


# -- сложные сценарии (книжные) ------------------------------------------


@pytest.mark.rules
def test_book_scenario_two_failures_then_nat20_recovers() -> None:
    """Сценарий: PC получает крит на 0 HP (2 провала), потом успешный
    спасбросок (1 успех), потом нат-20 — всё обнуляется и он жив."""
    s = DeathSaveState().apply_damage_at_zero(is_critical=True)
    assert s.failures == 2
    s = s.apply_save_roll(15)
    assert s.successes == 1
    s = s.apply_save_roll(20)
    assert s == DeathSaveState()


@pytest.mark.rules
def test_book_scenario_close_call_then_three_successes() -> None:
    """PC балансирует на грани: 2 провала, затем три успеха подряд →
    стабилен. (Получает 1 HP только через час; в этом VO — пока stable.)"""
    s = DeathSaveState(failures=2)
    s = s.apply_save_roll(11)
    assert s.successes == 1
    s = s.apply_save_roll(12)
    s = s.apply_save_roll(13)
    assert s.is_stable is True
    assert s.is_dead is False
    assert s.failures == 2

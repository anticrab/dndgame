"""Тесты ``ConditionService`` — каскадное применение состояний."""

from __future__ import annotations

import pytest

from dnd.application.engine.condition_service import ConditionService
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    POISONED,
    PRONE,
    STUNNED,
    UNCONSCIOUS,
    register_default_conditions,
)
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId

# -- фикстуры ------------------------------------------------------------


def make_creature(*, condition_immunities: frozenset = frozenset()) -> Creature:
    return (
        Creature.create(
            id_=CreatureId("test"),
            name="Test",
            abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
            max_hp=20,
            armor_class=15,
        )
        if not condition_immunities
        else _with_immunities(condition_immunities)
    )


def _with_immunities(immunities: frozenset) -> Creature:
    c = Creature.create(
        id_=CreatureId("test"),
        name="Test",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=15,
    )
    c.condition_immunities = immunities
    return c


@pytest.fixture
def service() -> ConditionService:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return ConditionService(reg)


# -- базовое применение --------------------------------------------------


def test_apply_simple_condition(service: ConditionService) -> None:
    """Состояние без implies накладывается само."""
    c = make_creature()
    result = service.apply_with_implies(c, POISONED)

    assert result.applied == frozenset({POISONED})
    assert result.skipped_immune == frozenset()
    assert result.already_present == frozenset()
    assert c.has_condition(POISONED)


@pytest.mark.rules
def test_apply_stunned_implies_incapacitated(service: ConditionService) -> None:
    """Книга стр. 367: Stunned → Incapacitated. Оба состояния
    оказываются на существе."""
    c = make_creature()
    result = service.apply_with_implies(c, STUNNED)

    assert result.applied == frozenset({STUNNED, INCAPACITATED})
    assert c.has_condition(STUNNED)
    assert c.has_condition(INCAPACITATED)


@pytest.mark.rules
def test_apply_unconscious_implies_incapacitated_and_prone(
    service: ConditionService,
) -> None:
    """Книга стр. 367: Unconscious → Incapacitated + Prone."""
    c = make_creature()
    result = service.apply_with_implies(c, UNCONSCIOUS)

    assert result.applied == frozenset({UNCONSCIOUS, INCAPACITATED, PRONE})
    assert c.has_condition(UNCONSCIOUS)
    assert c.has_condition(INCAPACITATED)
    assert c.has_condition(PRONE)


# -- иммунитеты ----------------------------------------------------------


def test_immunity_to_root_blocks_entire_cascade(
    service: ConditionService,
) -> None:
    """Иммунитет к корневому состоянию (Unconscious) → ни оно, ни
    implies (Incapacitated, Prone) не накладываются.

    Логика: иммунитет к «бессознательному» означает, что существо
    в принципе не может в это состояние перейти — каскад не
    запускается."""
    c = make_creature(condition_immunities=frozenset({UNCONSCIOUS}))
    result = service.apply_with_implies(c, UNCONSCIOUS)

    assert result.applied == frozenset()
    assert result.skipped_immune == frozenset({UNCONSCIOUS})
    assert not c.has_condition(UNCONSCIOUS)
    assert not c.has_condition(INCAPACITATED)
    assert not c.has_condition(PRONE)


def test_immunity_to_implied_skips_only_that_one(
    service: ConditionService,
) -> None:
    """Иммунитет к одному из implies (например, к Prone) — остальное
    каскадируется. Существо становится Unconscious + Incapacitated, но
    не Prone (потому что Prone заблокирован иммунитетом).

    Это сознательный выбор: некоторые существа физически не могут
    «упасть» (плавающий, бесплотный), но обычные эффекты сна на них
    действуют."""
    c = make_creature(condition_immunities=frozenset({PRONE}))
    result = service.apply_with_implies(c, UNCONSCIOUS)

    assert UNCONSCIOUS in result.applied
    assert INCAPACITATED in result.applied
    assert PRONE not in result.applied
    assert PRONE in result.skipped_immune
    assert c.has_condition(UNCONSCIOUS)
    assert c.has_condition(INCAPACITATED)
    assert not c.has_condition(PRONE)


# -- повторное применение -----------------------------------------------


def test_already_present_recorded_and_not_reapplied(
    service: ConditionService,
) -> None:
    """Если состояние уже есть — пишется в already_present, не в applied.
    Книжное правило «без накопления» (стр. 27) — Poisoned не становится
    «два раза отравлен»."""
    c = make_creature()
    c.apply_condition(POISONED)  # ставим заранее

    result = service.apply_with_implies(c, POISONED)
    assert result.applied == frozenset()
    assert result.already_present == frozenset({POISONED})


def test_partial_already_present_in_cascade(service: ConditionService) -> None:
    """Если у существа уже Prone, а накладываем Unconscious — Prone
    идёт в already_present, остальное (Unconscious, Incapacitated) —
    в applied."""
    c = make_creature()
    c.apply_condition(PRONE)

    result = service.apply_with_implies(c, UNCONSCIOUS)
    assert UNCONSCIOUS in result.applied
    assert INCAPACITATED in result.applied
    assert PRONE in result.already_present


# -- ошибки --------------------------------------------------------------


def test_unknown_condition_raises(service: ConditionService) -> None:
    """Незарегистрированный ConditionId — KeyError (контент-баг)."""
    from dnd.domain.values.ids import ConditionId

    c = make_creature()
    with pytest.raises(KeyError, match="not in registry"):
        service.apply_with_implies(c, ConditionId("nonexistent"))

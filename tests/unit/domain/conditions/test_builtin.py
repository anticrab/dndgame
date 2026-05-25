"""Тесты восьми базовых MVP-состояний (DESIGN.md §5.2, Книга стр. 367).

Для каждого состояния проверяем:

* registry получает все 8 после register_default_conditions;
* implies (каскад: Stunned/Paralyzed → Incapacitated, Unconscious → both);
* provides_modifiers возвращает правильные DisadvantageEffect-ы на
  правильные ModifierTargetKind.

Интеграция с Creature.apply_condition (распространение implies) —
в отдельном test_creature.py пост-фикс. Здесь — только сам плагин.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.modifiers import (
    DisadvantageEffect,
    ModifierSourceKind,
    ModifierTargetKind,
)
from dnd.domain.conditions.builtin import (
    FRIGHTENED,
    INCAPACITATED,
    INVISIBLE,
    PARALYZED,
    POISONED,
    PRONE,
    STUNNED,
    UNCONSCIOUS,
    FrightenedCondition,
    IncapacitatedCondition,
    InvisibleCondition,
    ParalyzedCondition,
    PoisonedCondition,
    ProneCondition,
    StunnedCondition,
    UnconsciousCondition,
    register_default_conditions,
)
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.values.ids import CreatureId

_AELAR = CreatureId("aelar")


# -- register_default_conditions -----------------------------------------


def test_register_default_conditions_registers_eight() -> None:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    assert len(reg) == 8
    expected = {
        INCAPACITATED,
        PRONE,
        POISONED,
        FRIGHTENED,
        STUNNED,
        PARALYZED,
        UNCONSCIOUS,
        INVISIBLE,
    }
    assert reg.ids() == frozenset(expected)


def test_register_default_conditions_rejects_non_registry() -> None:
    with pytest.raises(TypeError, match="ConditionRegistry"):
        register_default_conditions("not a registry")  # type: ignore[arg-type]


# -- implies (каскадирование) --------------------------------------------


@pytest.mark.rules
def test_stunned_implies_incapacitated() -> None:
    """Книга стр. 367: «Ошеломлённый» — также Incapacitated."""
    assert INCAPACITATED in StunnedCondition().implies


@pytest.mark.rules
def test_paralyzed_implies_incapacitated() -> None:
    """Книга стр. 367: «Парализованный» — также Incapacitated."""
    assert INCAPACITATED in ParalyzedCondition().implies


@pytest.mark.rules
def test_unconscious_implies_incapacitated_and_prone() -> None:
    """Книга стр. 367: «Бессознательный» — также Incapacitated и Prone."""
    implies = UnconsciousCondition().implies
    assert INCAPACITATED in implies
    assert PRONE in implies


def test_standalone_conditions_have_no_implies() -> None:
    """Poisoned, Frightened, Prone, Invisible, Incapacitated — сами по себе."""
    for cls in (
        IncapacitatedCondition,
        ProneCondition,
        PoisonedCondition,
        FrightenedCondition,
        InvisibleCondition,
    ):
        assert cls().implies == frozenset(), f"{cls.__name__} should not imply anything"


# -- provides_modifiers --------------------------------------------------


@pytest.mark.rules
def test_prone_gives_disadvantage_on_own_attacks() -> None:
    """Книга стр. 367: лежащий — помеха на свои атаки."""
    mods = ProneCondition().provides_modifiers(_AELAR)
    assert len(mods) == 1
    m = mods[0]
    assert isinstance(m.effect, DisadvantageEffect)
    assert m.target_kind is ModifierTargetKind.ATTACK_ROLL
    assert m.owner_id == _AELAR
    assert m.source_kind is ModifierSourceKind.CONDITION
    assert m.source_id == f"condition:{PRONE}"


@pytest.mark.rules
def test_poisoned_gives_disadvantage_on_attacks_and_checks() -> None:
    """Книга стр. 367: отравлен — помеха на атаки И проверки характеристик."""
    mods = PoisonedCondition().provides_modifiers(_AELAR)
    targets = {m.target_kind for m in mods}
    assert targets == {ModifierTargetKind.ATTACK_ROLL, ModifierTargetKind.ABILITY_CHECK}
    assert all(isinstance(m.effect, DisadvantageEffect) for m in mods)


@pytest.mark.rules
def test_frightened_gives_disadvantage_on_attacks_and_checks() -> None:
    """Книга стр. 367: испуган — помеха на атаки И проверки (пока
    источник в поле зрения, что в MVP считается всегда True)."""
    mods = FrightenedCondition().provides_modifiers(_AELAR)
    targets = {m.target_kind for m in mods}
    assert targets == {ModifierTargetKind.ATTACK_ROLL, ModifierTargetKind.ABILITY_CHECK}


def test_stunned_gives_disadvantage_on_saves() -> None:
    """Stunned — авто-провал STR/DEX-saves (книга). В MVP моделируем
    как помеху на спасброски — приближение, см. TODO в builtin.py."""
    mods = StunnedCondition().provides_modifiers(_AELAR)
    assert all(m.target_kind is ModifierTargetKind.SAVING_THROW for m in mods)
    assert all(isinstance(m.effect, DisadvantageEffect) for m in mods)


def test_paralyzed_gives_disadvantage_on_saves() -> None:
    mods = ParalyzedCondition().provides_modifiers(_AELAR)
    assert all(m.target_kind is ModifierTargetKind.SAVING_THROW for m in mods)


def test_unconscious_gives_disadvantage_on_saves() -> None:
    mods = UnconsciousCondition().provides_modifiers(_AELAR)
    assert all(m.target_kind is ModifierTargetKind.SAVING_THROW for m in mods)


def test_incapacitated_provides_no_self_modifiers() -> None:
    """Incapacitated сам по себе не накладывает self-модификаторов —
    его эффект «нет действий» обрабатывается в TurnBudget."""
    assert IncapacitatedCondition().provides_modifiers(_AELAR) == ()


def test_invisible_provides_no_self_modifiers() -> None:
    """Invisible — это эффект против атак ПО невидимому (cross-creature),
    сам по себе self-модификаторов не даёт. Реализуется в attack_roll."""
    assert InvisibleCondition().provides_modifiers(_AELAR) == ()


# -- modifier source_id и stack_key --------------------------------------


def test_modifier_source_id_is_canonical() -> None:
    """source_id вида 'condition:<id>' — используется для аудит-лога
    («бонус от: Poisoned») и для bag.remove_by_source при снятии
    состояния."""
    for cond, expected_source in [
        (ProneCondition(), f"condition:{PRONE}"),
        (PoisonedCondition(), f"condition:{POISONED}"),
    ]:
        mods = cond.provides_modifiers(_AELAR)
        assert all(m.source_id == expected_source for m in mods)


def test_modifier_stack_key_is_unique_per_target() -> None:
    """Для одного состояния по разным таргетам — разные stack_key,
    чтобы они не конкурировали друг с другом в ModifierApplier."""
    mods = PoisonedCondition().provides_modifiers(_AELAR)
    stack_keys = {m.stack_key for m in mods}
    assert len(stack_keys) == len(mods)  # все уникальны


# -- интеграция: implies-каскад с ConditionRegistry ---------------------


def test_unconscious_implications_resolve_via_registry() -> None:
    """Сценарий применения каскада: накладываем Unconscious, по
    `implies` дополнительно должны примениться Incapacitated и Prone.

    Само распространение реализуется в `Creature.apply_condition`
    (следующий коммит). Здесь — что `implies` достаточно для
    рекурсивного применения."""
    reg = ConditionRegistry()
    register_default_conditions(reg)

    uncon = reg.get(UNCONSCIOUS)
    chain = set(uncon.implies)
    # Раскручиваем транзитивно (как сделает Creature.apply_condition):
    seen: set = set()
    stack = list(chain)
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        stack.extend(reg.get(cid).implies)
    # Unconscious → {Incapacitated, Prone}. Incapacitated не implies ничего;
    # Prone тоже. Итого транзитивное замыкание: {Incapacitated, Prone}.
    assert seen == {INCAPACITATED, PRONE}

"""Тесты ``ModifierApplier`` — спецификация ``docs/MODIFIERS.md``.

Покрытие:

* ``ModifierBag``: add / remove_by_source / фильтр по owner.
* ``ModifierApplier.collect``: фильтр по owner_id и target_kind.
* ``to_roll_adjustments``:
  - NumericBonusEffect: суммирование по группам, BEST_ONLY,
    STACK_ALL, REPLACE.
  - DiceBonusEffect: накопление extra_dice (Bless +1d4, Sneak Attack 2d6).
  - AdvantageEffect / DisadvantageEffect: одиночные.
  - Книжное правило «advantage + disadvantage = обычный»
    (стр. 11).
  - source_id попадают в sources для аудита.
* Книжные сценарии: Талисман +1 КД, Bless к атаке, Poisoned помеха.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.ids import CreatureId
from dnd.application.dto.modifiers import (
    AdvantageEffect,
    DiceBonusEffect,
    DisadvantageEffect,
    Modifier,
    ModifierSourceKind,
    ModifierTargetKind,
    NumericBonusEffect,
    StackingPolicy,
)
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag

# -- помощники --------------------------------------------------------------

_AELAR = CreatureId("aelar")
_GOBLIN = CreatureId("goblin-1")


def _make(
    *,
    owner: CreatureId = _AELAR,
    source: str = "test:src",
    source_kind: ModifierSourceKind = ModifierSourceKind.ITEM,
    target: ModifierTargetKind = ModifierTargetKind.ATTACK_ROLL,
    effect: object,
    stack_key: str = "",
    stacking: StackingPolicy = StackingPolicy.BEST_ONLY,
) -> Modifier:
    """Удобная фабрика для тестовых модификаторов."""
    return Modifier(
        owner_id=owner,
        source_id=source,
        source_kind=source_kind,
        target_kind=target,
        effect=effect,  # type: ignore[arg-type]
        stack_key=stack_key,
        stacking=stacking,
    )


# -- ModifierBag ----------------------------------------------------------


def test_bag_starts_empty() -> None:
    bag = ModifierBag()
    assert len(bag) == 0
    assert bag.all_for(_AELAR) == []


def test_bag_add_and_filter_by_owner() -> None:
    bag = ModifierBag()
    m1 = _make(owner=_AELAR, effect=NumericBonusEffect(value=1))
    m2 = _make(owner=_GOBLIN, effect=NumericBonusEffect(value=2))
    bag.add(m1)
    bag.add(m2)

    aelar_mods = bag.all_for(_AELAR)
    goblin_mods = bag.all_for(_GOBLIN)
    assert aelar_mods == [m1]
    assert goblin_mods == [m2]


def test_bag_remove_by_source() -> None:
    bag = ModifierBag()
    bag.add(_make(source="bless", effect=NumericBonusEffect(value=1)))
    bag.add(_make(source="bless", effect=DiceBonusEffect(dice="1d4")))
    bag.add(_make(source="other", effect=NumericBonusEffect(value=2)))

    removed = bag.remove_by_source("bless")
    assert removed == 2
    assert len(bag) == 1


def test_bag_remove_unknown_source_returns_zero() -> None:
    bag = ModifierBag()
    bag.add(_make(source="bless", effect=NumericBonusEffect(value=1)))
    assert bag.remove_by_source("missing") == 0
    assert len(bag) == 1


# -- collect ----------------------------------------------------------------


def test_collect_filters_by_owner_and_target() -> None:
    bag = ModifierBag()
    # Aelar — атака
    bag.add(_make(target=ModifierTargetKind.ATTACK_ROLL, effect=NumericBonusEffect(value=1)))
    # Aelar — спасбросок (не должен попасть в atk)
    bag.add(_make(target=ModifierTargetKind.SAVING_THROW, effect=NumericBonusEffect(value=99)))
    # Goblin — атака (чужой owner, не должен попасть)
    bag.add(
        _make(
            owner=_GOBLIN, target=ModifierTargetKind.ATTACK_ROLL, effect=NumericBonusEffect(value=5)
        )
    )

    applier = ModifierApplier(bag)
    found = applier.collect(owner_id=_AELAR, target_kind=ModifierTargetKind.ATTACK_ROLL)
    assert len(found) == 1
    assert isinstance(found[0].effect, NumericBonusEffect)
    assert found[0].effect.value == 1


def test_collect_returns_empty_for_no_modifiers() -> None:
    bag = ModifierBag()
    applier = ModifierApplier(bag)
    assert applier.collect(owner_id=_AELAR, target_kind=ModifierTargetKind.ATTACK_ROLL) == []


# -- to_roll_adjustments: NumericBonus -------------------------------------


def test_numeric_bonus_single_modifier() -> None:
    """Талисман Стойкости: +1 к КД."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [_make(target=ModifierTargetKind.ARMOR_CLASS, effect=NumericBonusEffect(value=1))]
    )
    assert adj.numeric_bonus == 1
    assert adj.extra_dice == ()
    assert adj.advantage is False
    assert adj.disadvantage is False


@pytest.mark.rules
def test_numeric_bonus_best_only_picks_max_same_stack_key() -> None:
    """Книга стр. 12 «Бонус не складывается»: два магических меча
    +1 и +2 — действует только +2, не +3."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                source="sword-of-prowess-1",
                stack_key="magic_weapon",
                effect=NumericBonusEffect(value=1),
                stacking=StackingPolicy.BEST_ONLY,
            ),
            _make(
                source="sword-of-prowess-2",
                stack_key="magic_weapon",
                effect=NumericBonusEffect(value=2),
                stacking=StackingPolicy.BEST_ONLY,
            ),
        ]
    )
    assert adj.numeric_bonus == 2


def test_numeric_bonus_different_stack_keys_sum() -> None:
    """Разные группы бонусов суммируются: +2 проф. бонус и
    +1 от магического меча = +3 к атаке."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(stack_key="proficiency", effect=NumericBonusEffect(value=2)),
            _make(stack_key="magic_weapon", effect=NumericBonusEffect(value=1)),
        ]
    )
    assert adj.numeric_bonus == 3


def test_numeric_bonus_stack_all_sums_within_group() -> None:
    """STACK_ALL: все модификаторы складываются даже в одной группе.

    Используется редко — например, для PHB Inspire Heroics + Bless
    (но это не Numeric; для Numeric — нетипично). Тест проверяет, что
    политика работает."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                stack_key="weird",
                effect=NumericBonusEffect(value=1),
                stacking=StackingPolicy.STACK_ALL,
            ),
            _make(
                stack_key="weird",
                effect=NumericBonusEffect(value=2),
                stacking=StackingPolicy.STACK_ALL,
            ),
        ]
    )
    assert adj.numeric_bonus == 3


def test_numeric_bonus_replace_takes_first() -> None:
    """REPLACE: только первый модификатор группы. Порядок добавления
    = приоритет. Используется для replacement-эффектов типа «КД
    монаха = 10 + DEX + WIS» (но это другой effect kind пост-MVP;
    здесь — синтетический тест политики)."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                stack_key="override",
                effect=NumericBonusEffect(value=10),
                stacking=StackingPolicy.REPLACE,
            ),
            _make(
                stack_key="override",
                effect=NumericBonusEffect(value=99),
                stacking=StackingPolicy.REPLACE,
            ),
        ]
    )
    assert adj.numeric_bonus == 10  # первый


def test_empty_stack_key_means_unique_group() -> None:
    """Пустой stack_key = модификатор сам по себе, никогда не
    конкурирует с другими — даже если они тоже с пустым ключом.

    Это нужно для случая «несколько Sneak Attack-кубиков от разных
    срабатываний фичи одного существа» — каждый — отдельный модификатор
    без указания stack_key, и они **должны** складываться."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(stack_key="", effect=NumericBonusEffect(value=2)),
            _make(stack_key="", effect=NumericBonusEffect(value=3)),
        ]
    )
    # Каждый модификатор — своя группа → оба применяются → сумма.
    assert adj.numeric_bonus == 5


# -- DiceBonus ------------------------------------------------------------


@pytest.mark.rules
def test_dice_bonus_bless_to_attack() -> None:
    """Bless: +1d4 к броску атаки. MODIFIERS.md §2.2 DiceBonusEffect."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [_make(source="spell:bless", effect=DiceBonusEffect(dice="1d4"))]
    )
    assert adj.extra_dice == ("1d4",)


def test_dice_bonus_multiple_sources_accumulate() -> None:
    """Sneak Attack 1d6 + Hunter's Mark 1d6 на броске урона —
    обе кости в extra_dice."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                source="feature:sneak-attack",
                target=ModifierTargetKind.DAMAGE_ROLL,
                effect=DiceBonusEffect(dice="1d6"),
            ),
            _make(
                source="spell:hunters-mark",
                target=ModifierTargetKind.DAMAGE_ROLL,
                effect=DiceBonusEffect(dice="1d6"),
            ),
        ]
    )
    assert sorted(adj.extra_dice) == ["1d6", "1d6"]


# -- Advantage / Disadvantage ---------------------------------------------


@pytest.mark.rules
def test_advantage_single_effect() -> None:
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [_make(source="bardic:inspiration", effect=AdvantageEffect())]
    )
    assert adj.advantage is True
    assert adj.disadvantage is False


@pytest.mark.rules
def test_disadvantage_single_effect_poisoned() -> None:
    """Poisoned накладывает помеху на броски атаки и тесты к20."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                source="condition:poisoned",
                source_kind=ModifierSourceKind.CONDITION,
                effect=DisadvantageEffect(),
            )
        ]
    )
    assert adj.disadvantage is True
    assert adj.advantage is False


@pytest.mark.rules
def test_advantage_and_disadvantage_cancel_each_other() -> None:
    """Книга стр. 11 «Они не складываются»: если есть И преимущество,
    И помеха — бросок обычный, оба флага гасятся."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(source="hide", effect=AdvantageEffect()),
            _make(source="poisoned", effect=DisadvantageEffect()),
        ]
    )
    assert adj.advantage is False
    assert adj.disadvantage is False


@pytest.mark.rules
def test_multiple_advantages_still_just_advantage() -> None:
    """Книга стр. 11: «несколько обстоятельств преимущества — всё
    равно одно преимущество»."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(source="hide", effect=AdvantageEffect()),
            _make(source="help-action", effect=AdvantageEffect()),
            _make(source="invisible", effect=AdvantageEffect()),
        ]
    )
    assert adj.advantage is True


@pytest.mark.rules
def test_multiple_disadvantages_against_one_advantage_still_cancels() -> None:
    """Книга стр. 11: «это верно даже если несколько обстоятельств
    дают помеху, а только одно — преимущество». Result: обычный
    бросок."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(source="hide", effect=AdvantageEffect()),
            _make(source="poisoned", effect=DisadvantageEffect()),
            _make(source="frightened", effect=DisadvantageEffect()),
        ]
    )
    assert adj.advantage is False
    assert adj.disadvantage is False


# -- Комбинированные сценарии --------------------------------------------


def test_combination_talisman_and_bless() -> None:
    """Aelar получает атаку под Bless и носит магическое оружие +1.

    Bless: +1d4 к атаке. Магическое оружие: +1 к атаке (numeric).
    Результат — numeric_bonus=1, extra_dice=("1d4",).
    """
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(
                source="spell:bless",
                source_kind=ModifierSourceKind.SPELL,
                effect=DiceBonusEffect(dice="1d4"),
            ),
            _make(
                source="item:longsword-of-prowess",
                source_kind=ModifierSourceKind.ITEM,
                stack_key="magic_weapon",
                effect=NumericBonusEffect(value=1),
            ),
        ]
    )
    assert adj.numeric_bonus == 1
    assert adj.extra_dice == ("1d4",)
    assert adj.advantage is False
    assert adj.disadvantage is False


def test_sources_are_recorded_for_audit() -> None:
    """source_id всех применённых модификаторов попадают в sources
    результата — для аудит-лога мастера и UI («бонус от: меч +1,
    Bless»)."""
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments(
        [
            _make(source="item:sword", effect=NumericBonusEffect(value=1)),
            _make(source="spell:bless", effect=DiceBonusEffect(dice="1d4")),
        ]
    )
    assert set(adj.sources) == {"item:sword", "spell:bless"}


def test_empty_modifier_list_yields_neutral_adjustments() -> None:
    applier = ModifierApplier(ModifierBag())
    adj = applier.to_roll_adjustments([])
    assert adj.numeric_bonus == 0
    assert adj.extra_dice == ()
    assert adj.advantage is False
    assert adj.disadvantage is False
    assert adj.sources == ()


# -- DTO валидация --------------------------------------------------------


def test_dice_bonus_rejects_empty_dice_string() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DiceBonusEffect(dice="")


def test_modifier_is_frozen() -> None:
    from pydantic import ValidationError

    m = _make(effect=NumericBonusEffect(value=1))
    with pytest.raises(ValidationError):
        m.stack_key = "changed"  # type: ignore[misc]

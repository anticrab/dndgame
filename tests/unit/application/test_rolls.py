"""Тесты pydantic-DTO бросков (RollContext, EngineRollResult, RollPurpose).

Здесь — только про валидацию, иммутабельность и конфиг pydantic-моделей.
Семантика бросков (как DiceRoller их применяет) — в test_dice_roller.py.
Свойства EngineRollResult вроде ``d20_raw`` тоже здесь — это чистое
свойство DTO, не зависящее от DiceRoller.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from dnd.application.dto.rolls import (
    EngineRollResult,
    RollContext,
    RollPurpose,
    make_roll_id,
)
from dnd.domain.values.ids import RollId

# -- RollPurpose ----------------------------------------------------------


def test_roll_purpose_has_expected_kinds() -> None:
    """10 категорий бросков, из которых статистика и аудит отбирают
    нужные. Если в будущем добавим — этот тест напомнит обновить
    DiceStatistics и UI."""
    expected = {
        "attack",
        "damage",
        "save",
        "ability_check",
        "initiative",
        "hit_dice",
        "death_save",
        "stats_gen",
        "loot",
        "other",
    }
    assert {p.value for p in RollPurpose} == expected


# -- RollContext ----------------------------------------------------------


def test_roll_context_minimum_fields() -> None:
    ctx = RollContext(purpose=RollPurpose.ATTACK)
    assert ctx.purpose is RollPurpose.ATTACK
    assert ctx.advantage is False
    assert ctx.extra_dice == ()
    assert ctx.tags == ()


def test_roll_context_is_frozen() -> None:
    ctx = RollContext(purpose=RollPurpose.SAVE)
    with pytest.raises(ValidationError):
        ctx.advantage = True  # type: ignore[misc]


def test_roll_context_rejects_extra_fields() -> None:
    """`extra='forbid'` отлавливает опечатки (например, `advantadge`)."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        RollContext.model_validate({"purpose": "attack", "advantage": True, "advantadge": True})


# -- EngineRollResult: конфиг ---------------------------------------------


def _make_result(**overrides: object) -> EngineRollResult:
    base: dict[str, object] = {
        "roll_id": RollId(uuid4()),
        "expr": "1d20+5",
        "raw": (15,),
        "kept": (15,),
        "modifier": 5,
        "total": 20,
        "context": RollContext(purpose=RollPurpose.ATTACK),
    }
    base.update(overrides)
    return EngineRollResult.model_validate(base)


def test_engine_roll_result_is_frozen() -> None:
    result = _make_result()
    with pytest.raises(ValidationError):
        result.total = 99  # type: ignore[misc]


def test_engine_roll_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        EngineRollResult.model_validate(
            {
                "roll_id": uuid4(),
                "expr": "d20",
                "raw": (10,),
                "kept": (10,),
                "modifier": 0,
                "total": 10,
                "context": {"purpose": "attack"},
                "phantom_field": "what",
            }
        )


# -- EngineRollResult.d20_raw / is_natural_* -----------------------------


def test_d20_raw_for_single_d20() -> None:
    result = _make_result(expr="1d20+5", raw=(14,), kept=(14,))
    assert result.d20_raw == 14


def test_d20_raw_none_for_non_d20() -> None:
    result = _make_result(expr="2d6", raw=(3, 5), kept=(3, 5), modifier=0, total=8)
    assert result.d20_raw is None


def test_d20_raw_none_for_keep_highest() -> None:
    """4d6kh3 — не одиночный d20."""
    result = _make_result(expr="4d6kh3", raw=(1, 6, 4, 5), kept=(6, 5, 4), modifier=0, total=15)
    assert result.d20_raw is None


def test_d20_raw_with_advantage_keeps_chosen() -> None:
    """При advantage `kept` содержит выбранное (max), и d20_raw — его."""
    result = _make_result(
        expr="1d20+5",
        raw=(7, 18),
        kept=(18,),
        modifier=5,
        total=23,
        advantage=True,
    )
    assert result.d20_raw == 18


def test_is_natural_20() -> None:
    assert _make_result(expr="1d20", raw=(20,), kept=(20,), modifier=0, total=20).is_natural_20()
    assert not _make_result(
        expr="1d20", raw=(19,), kept=(19,), modifier=0, total=19
    ).is_natural_20()
    # Для не-d20 — никогда True
    assert not _make_result(expr="2d6", raw=(20,), kept=(20,), modifier=0, total=20).is_natural_20()


def test_is_natural_1() -> None:
    assert _make_result(expr="1d20", raw=(1,), kept=(1,), modifier=0, total=1).is_natural_1()
    assert not _make_result(expr="1d20", raw=(2,), kept=(2,), modifier=0, total=2).is_natural_1()


# -- make_roll_id --------------------------------------------------------


def test_make_roll_id_returns_unique_ids() -> None:
    ids = {make_roll_id() for _ in range(100)}
    assert len(ids) == 100

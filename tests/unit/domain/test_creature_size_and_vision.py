"""Тесты CreatureSize и Vision — value-объекты для Creature."""

from __future__ import annotations

import pytest

from dnd.domain.values.creature_size import CreatureSize
from dnd.domain.values.vision import NORMAL_VISION, Vision, VisionKind

# -- CreatureSize ---------------------------------------------------------


def test_creature_size_has_six_values() -> None:
    """Книга 2024 (стр. 24) — 6 категорий размера."""
    assert {s.value for s in CreatureSize} == {
        "tiny",
        "small",
        "medium",
        "large",
        "huge",
        "gargantuan",
    }


@pytest.mark.rules
@pytest.mark.parametrize(
    "size,squares_side",
    [
        (CreatureSize.TINY, 1),
        (CreatureSize.SMALL, 1),
        (CreatureSize.MEDIUM, 1),
        (CreatureSize.LARGE, 2),
        (CreatureSize.HUGE, 3),
        (CreatureSize.GARGANTUAN, 4),
    ],
)
def test_creature_size_squares_side(size: CreatureSize, squares_side: int) -> None:
    assert size.squares_side == squares_side


# -- Vision ---------------------------------------------------------------


def test_normal_vision_works_without_radius() -> None:
    v = Vision(kind=VisionKind.NORMAL)
    assert v.radius_ft == 0


def test_normal_vision_constant_is_canonical() -> None:
    assert NORMAL_VISION.kind is VisionKind.NORMAL


@pytest.mark.parametrize(
    "kind", [VisionKind.DARKVISION, VisionKind.BLINDSIGHT, VisionKind.TRUESIGHT]
)
def test_special_vision_requires_positive_radius(kind: VisionKind) -> None:
    with pytest.raises(ValueError, match="positive radius_ft"):
        Vision(kind=kind, radius_ft=0)


def test_vision_rejects_negative_radius() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        Vision(kind=VisionKind.NORMAL, radius_ft=-5)


def test_darkvision_60_typical_elf() -> None:
    v = Vision(kind=VisionKind.DARKVISION, radius_ft=60)
    assert v.kind is VisionKind.DARKVISION
    assert v.radius_ft == 60

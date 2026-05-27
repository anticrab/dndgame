"""P2-3: AreaShapeRegistry + резолверы (клетки + clamp к границам)."""

from __future__ import annotations

import pytest

from dnd.application.engine.spells.area import (
    AreaShapeResolver,
    default_area_shape_registry,
)
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.direction import Direction
from dnd.domain.values.spell import AreaShape, OriginMode, TargetingSpec, TargetKind
from dnd.domain.values.square import Square


def _bf() -> Battlefield:
    return Battlefield(10, 10)


def _spec_circle(r: int) -> TargetingSpec:
    return TargetingSpec(
        kind=TargetKind.AREA,
        origin=OriginMode.AT_POINT,
        shape=AreaShape.CIRCLE,
        radius_ft=r,
    )


def test_registry_has_three_shapes() -> None:
    reg = default_area_shape_registry()
    assert AreaShape.CIRCLE in reg
    assert AreaShape.CONE in reg
    assert AreaShape.LINE in reg
    assert isinstance(reg.get(AreaShape.CIRCLE), AreaShapeResolver)


def test_circle_resolver_cells() -> None:
    reg = default_area_shape_registry()
    cells = reg.get(AreaShape.CIRCLE).squares(
        Square(5, 5),
        None,
        _spec_circle(10),
        _bf(),  # 10ft → 2 клетки
    )
    assert Square(5, 5) in cells
    assert Square(7, 7) in cells and Square(3, 3) in cells
    assert len(cells) == 25  # (2*2+1)^2


def test_circle_clamped_to_bounds() -> None:
    reg = default_area_shape_registry()
    cells = reg.get(AreaShape.CIRCLE).squares(Square(0, 0), None, _spec_circle(10), _bf())
    assert all(0 <= c.x < 10 and 0 <= c.y < 10 for c in cells)
    assert Square(0, 0) in cells


def test_cone_resolver_requires_direction() -> None:
    reg = default_area_shape_registry()
    spec = TargetingSpec(
        kind=TargetKind.AREA,
        origin=OriginMode.FROM_CASTER,
        shape=AreaShape.CONE,
        length_ft=15,
    )
    with pytest.raises(ValueError):
        reg.get(AreaShape.CONE).squares(Square(5, 5), None, spec, _bf())


def test_line_resolver_cells() -> None:
    reg = default_area_shape_registry()
    spec = TargetingSpec(
        kind=TargetKind.AREA,
        origin=OriginMode.FROM_CASTER,
        shape=AreaShape.LINE,
        length_ft=15,  # 3 клетки
    )
    cells = reg.get(AreaShape.LINE).squares(Square(2, 2), Direction.E, spec, _bf())
    assert cells == frozenset({Square(3, 2), Square(4, 2), Square(5, 2)})

"""R1-5 каркас: FeatureRegistry + ResourceRegistry."""
from __future__ import annotations

import pytest

from dnd.application.engine.features.registry import (
    FeatureRegistry,
    ResourceRegistry,
    ResourceSpec,
)
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.rest import RechargeOn


class _Dummy:
    def __init__(self) -> None:
        self.gained = False

    def on_gain(self, creature: object, ctx: object) -> None:
        self.gained = True


def test_registry_register_get_contains() -> None:
    reg = FeatureRegistry()
    h = _Dummy()
    reg.register(FeatureId("x"), h)
    assert reg.contains(FeatureId("x"))
    assert reg.get(FeatureId("x")) is h


def test_get_unknown_raises() -> None:
    reg = FeatureRegistry()
    with pytest.raises(KeyError):
        reg.get(FeatureId("nope"))


def test_resource_registry() -> None:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(max_uses=1, recharge_on=RechargeOn.SHORT_REST))
    spec = rr.get("second_wind")
    assert spec.max_uses == 1 and spec.recharge_on is RechargeOn.SHORT_REST
    assert rr.all_specs()["second_wind"].max_uses == 1


def test_improved_critical_handler_sets_crit_range() -> None:
    from dnd.application.engine.features.handlers import ImprovedCriticalHandler
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    c = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    assert c.crit_range_min == 20
    ImprovedCriticalHandler().on_gain(c, None)
    assert c.crit_range_min == 19

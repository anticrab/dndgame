"""R1-6: RestService — восстановление ресурсов по recharge_on + HP на LONG."""
from __future__ import annotations

from dnd.application.engine.features.registry import ResourceRegistry, ResourceSpec
from dnd.application.engine.progression.rest import RestService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.rest import RechargeOn, RestKind


def _c() -> Creature:
    return Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=14, speed_ft=30,
    )


def _rr() -> ResourceRegistry:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(1, RechargeOn.SHORT_REST))
    rr.register("daily", ResourceSpec(1, RechargeOn.LONG_REST))
    return rr


def test_short_rest_restores_short_resource_not_long() -> None:
    c = _c()
    c.resource_uses = {"second_wind": 0, "daily": 0}
    RestService(_rr()).apply(c, RestKind.SHORT)
    assert c.resource_uses["second_wind"] == 1   # short восстановлен
    assert c.resource_uses["daily"] == 0         # long НЕ тронут


def test_long_rest_restores_all_and_full_hp() -> None:
    c = _c()
    c.resource_uses = {"second_wind": 0, "daily": 0}
    c.take_damage(DamageInstance(amount=5, type_=DamageType.SLASHING))
    RestService(_rr()).apply(c, RestKind.LONG)
    assert c.resource_uses["second_wind"] == 1 and c.resource_uses["daily"] == 1
    assert c.hit_points.current == c.hit_points.maximum   # полный HP


def test_short_rest_does_not_restore_full_hp() -> None:
    c = _c()
    c.take_damage(DamageInstance(amount=5, type_=DamageType.SLASHING))
    RestService(_rr()).apply(c, RestKind.SHORT)
    assert c.hit_points.current == 7   # SHORT не лечит автоматически в R1

"""R1-1: прогрессионные поля Creature (level/xp/класс/фичи/крит/ресурсы)."""

from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores


def _c() -> Creature:
    return Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=14,
        speed_ft=30,
    )


def test_progression_defaults() -> None:
    c = _c()
    assert c.level == 1 and c.xp == 0
    assert c.character_class is None
    assert c.challenge_rating == 0.0
    assert c.features == ()
    assert c.crit_range_min == 20
    assert c.resource_uses == {}


def test_progression_fields_mutable() -> None:
    c = _c()
    c.level = 2
    c.xp = 120
    c.character_class = "fighter"
    c.crit_range_min = 19
    c.resource_uses["second_wind"] = 1
    assert c.level == 2 and c.resource_uses["second_wind"] == 1

"""Подклассы L3 (T4-b): автовыбор по классу + эффект."""

from __future__ import annotations

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId, FeatureId


def _c(cls: str) -> Creature:
    c = Creature.create(
        id_=CreatureId("c"),
        name="c",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=12, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )
    c.character_class = cls
    return c


def test_fighter_subclass_default_champion_sets_crit() -> None:
    reg = default_feature_registry()
    c = _c("fighter")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_champion")
    assert c.crit_range_min == 19  # Improved Critical


def test_wizard_subclass_default_evoker_flag() -> None:
    reg = default_feature_registry()
    c = _c("wizard")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_evoker")
    assert FeatureId("subclass_evoker") in c.features


def test_rogue_subclass_default_thief() -> None:
    reg = default_feature_registry()
    c = _c("rogue")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.subclass == FeatureId("subclass_thief")


def test_explicit_subclass_choice_respected() -> None:
    reg = default_feature_registry()
    c = _c("fighter")
    c.subclass = FeatureId("subclass_champion")
    reg.get(FeatureId("subclass")).on_gain(c, None)
    assert c.crit_range_min == 19

"""Боевые стили Воина (T4-a)."""
from __future__ import annotations

from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.features.fighting_styles import (
    fighting_style_attack_bonus,
    fighting_style_damage_bonus,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import CreatureId, FeatureId


def _c() -> Creature:
    return Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=14, dex=14, con=12, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=15, speed_ft=30,
    )


def test_defense_style_adds_ac_on_gain() -> None:
    reg = default_feature_registry()
    c = _c()
    c.fighting_style = FeatureId("style_defense")
    reg.get(FeatureId("fighting_style")).on_gain(c, None)
    assert c.armor_class == 16
    assert FeatureId("style_defense") in c.features


def test_fighting_style_default_is_defense() -> None:
    reg = default_feature_registry()
    c = _c()  # стиль не задан → дефолт Defense
    reg.get(FeatureId("fighting_style")).on_gain(c, None)
    assert c.armor_class == 16
    assert c.fighting_style == FeatureId("style_defense")


def test_archery_attack_bonus_ranged_only() -> None:
    c = _c()
    c.fighting_style = FeatureId("style_archery")
    assert fighting_style_attack_bonus(c, AttackKind.RANGED) == 2
    assert fighting_style_attack_bonus(c, AttackKind.MELEE) == 0


def test_dueling_damage_bonus_melee_only() -> None:
    c = _c()
    c.fighting_style = FeatureId("style_dueling")
    assert fighting_style_damage_bonus(c, AttackKind.MELEE) == 2
    assert fighting_style_damage_bonus(c, AttackKind.RANGED) == 0

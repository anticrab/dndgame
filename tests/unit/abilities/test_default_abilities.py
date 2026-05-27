"""6 базовых ability'ев регистрируются без коллизий hotkey'ев."""

from __future__ import annotations

from dnd.application.abilities.ability import AbilityId
from dnd.application.abilities.defaults import register_default_abilities
from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.player_intent import (
    AttackIntent,
    BreakIntent,
    DodgeIntent,
    InteractIntent,
)
from dnd.domain.values.ids import CreatureId, ObjectId


def test_all_default_abilities_registered() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    ids = {a.id for a in r.all()}
    assert ids == {
        AbilityId("weapon_attack"),
        AbilityId("dodge"),
        AbilityId("dash"),
        AbilityId("disengage"),
        AbilityId("interact"),
        AbilityId("break_object"),
        AbilityId("stabilize"),
        AbilityId("second_wind"),
        AbilityId("action_surge"),
        # T4: Cunning Action (Плут L2) — без дефолтного хоткея (через меню).
        AbilityId("cunning_dash"),
        AbilityId("cunning_disengage"),
    }


def test_no_hotkey_collisions() -> None:
    """ИНВАРИАНТ §11-7: default hotkey'и не должны коллидировать. Пустой
    хоткей ("" — «нет дефолтного», T4 cunning-абилки) не считается коллизией."""
    r = AbilityRegistry()
    register_default_abilities(r)
    keys = [a.default_hotkey for a in r.all() if a.default_hotkey]
    assert len(keys) == len(set(keys)), f"hotkey collision: {keys}"


def test_weapon_attack_requires_target() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    assert r.get(AbilityId("weapon_attack")).requires_target is True


def test_dodge_no_target_no_path() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    d = r.get(AbilityId("dodge"))
    assert d.requires_target is False
    assert d.requires_path is False


def test_attack_factory_builds_intent_with_target_id() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    ability = r.get(AbilityId("weapon_attack"))
    intent = ability.intent_factory(CreatureId("goblin-1"))
    assert isinstance(intent, AttackIntent)
    assert intent.target_id == CreatureId("goblin-1")


def test_dodge_factory_no_args() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    intent = r.get(AbilityId("dodge")).intent_factory()
    assert isinstance(intent, DodgeIntent)


def test_interact_factory_wraps_to_object_id() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    intent = r.get(AbilityId("interact")).intent_factory(CreatureId("door-1"))
    assert isinstance(intent, InteractIntent)
    assert intent.target_object_id == ObjectId("door-1")


def test_break_factory_wraps_to_object_id() -> None:
    r = AbilityRegistry()
    register_default_abilities(r)
    intent = r.get(AbilityId("break_object")).intent_factory(CreatureId("crate-1"))
    assert isinstance(intent, BreakIntent)
    assert intent.target_object_id == ObjectId("crate-1")

"""Ability — frozen dataclass с runtime-описанием умения."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from dnd.application.abilities.ability import Ability, AbilityId
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import DodgeIntent, PlayerIntent


def _dodge_factory() -> PlayerIntent:
    return DodgeIntent()


def test_ability_frozen() -> None:
    a = Ability(
        id=AbilityId("dodge"), name="Dodge", icon="d",
        default_hotkey="d", economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_dodge_factory,
    )
    with pytest.raises(FrozenInstanceError):
        a.name = "X"  # type: ignore[misc]


def test_ability_id_is_str() -> None:
    aid = AbilityId("weapon_attack")
    assert str(aid) == "weapon_attack"


def test_ability_required_flags_exclusive() -> None:
    """``requires_target`` и ``requires_path`` не могут быть оба True
    одновременно — mode-state-machine поддерживает только один из режимов
    за раз."""
    with pytest.raises(ValueError, match="взаимоисключающие"):
        Ability(
            id=AbilityId("x"), name="X", icon="x", default_hotkey="x",
            economy_cost=ActionEconomyCost.ACTION,
            requires_target=True, requires_path=True,
            intent_factory=_dodge_factory,
        )


def test_requires_area_flag_and_exclusivity() -> None:
    import pytest

    from dnd.application.abilities.ability import Ability, AbilityId
    from dnd.application.dto.action import ActionEconomyCost

    ab = Ability(
        id=AbilityId("fb"), name="Fireball", icon="*", default_hotkey="",
        economy_cost=ActionEconomyCost.ACTION, requires_target=False,
        requires_path=False, requires_area=True, intent_factory=lambda: None,
    )
    assert ab.requires_area is True

    with pytest.raises(ValueError):
        Ability(
            id=AbilityId("bad"), name="Bad", icon="*", default_hotkey="",
            economy_cost=ActionEconomyCost.ACTION, requires_target=True,
            requires_path=False, requires_area=True, intent_factory=lambda: None,
        )

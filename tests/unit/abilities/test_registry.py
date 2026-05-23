"""AbilityRegistry — register/get/all + дубликаты."""
from __future__ import annotations

import pytest

from dnd.application.abilities.ability import Ability, AbilityId
from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import DodgeIntent, PlayerIntent


def _dodge() -> PlayerIntent:
    return DodgeIntent()


def _make(id_: str, hotkey: str = "x") -> Ability:
    return Ability(
        id=AbilityId(id_), name=id_, icon=id_[0], default_hotkey=hotkey,
        economy_cost=ActionEconomyCost.ACTION,
        requires_target=False, requires_path=False,
        intent_factory=_dodge,
    )


def test_register_and_get() -> None:
    r = AbilityRegistry()
    a = _make("foo")
    r.register(a)
    assert r.get(AbilityId("foo")) is a


def test_get_missing_raises() -> None:
    r = AbilityRegistry()
    with pytest.raises(KeyError):
        r.get(AbilityId("missing"))


def test_duplicate_register_raises() -> None:
    r = AbilityRegistry()
    r.register(_make("foo"))
    with pytest.raises(ValueError, match="already registered"):
        r.register(_make("foo"))


def test_all_returns_registered() -> None:
    r = AbilityRegistry()
    r.register(_make("a", "1"))
    r.register(_make("b", "2"))
    assert {a.id for a in r.all()} == {AbilityId("a"), AbilityId("b")}


def test_all_returns_tuple_not_iterator() -> None:
    """``all()`` отдаёт tuple — два прохода читают одни и те же элементы."""
    r = AbilityRegistry()
    r.register(_make("a", "1"))
    snap1 = r.all()
    snap2 = r.all()
    assert snap1 == snap2
    assert len(list(snap1)) == 1
    assert len(list(snap1)) == 1

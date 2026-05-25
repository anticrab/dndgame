"""Тесты ConditionRegistry — реестр плагинов состояний."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.values.ids import ConditionId, CreatureId
from dnd.domain.values.modifiers import Modifier

_FAKE_ID = ConditionId("fake")


@dataclass(frozen=True, slots=True)
class _FakeCondition:
    id: ConditionId = _FAKE_ID
    implies: frozenset[ConditionId] = field(default_factory=frozenset)

    def provides_modifiers(self, owner_id: CreatureId) -> tuple[Modifier, ...]:
        return ()


def test_registry_starts_empty() -> None:
    reg = ConditionRegistry()
    assert len(reg) == 0
    assert reg.ids() == frozenset()


def test_register_and_lookup() -> None:
    reg = ConditionRegistry()
    cond = _FakeCondition()
    reg.register(cond)

    assert len(reg) == 1
    assert reg.has(ConditionId("fake"))
    assert reg.get(ConditionId("fake")) is cond


def test_double_register_raises() -> None:
    """Регистрация второго плагина с тем же id — явная ошибка на старте,
    не в рантайме."""
    reg = ConditionRegistry()
    reg.register(_FakeCondition())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakeCondition())


def test_get_unknown_raises_with_helpful_message() -> None:
    reg = ConditionRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get(ConditionId("missing"))


def test_iter_yields_all_conditions() -> None:
    reg = ConditionRegistry()
    a = _FakeCondition(id=ConditionId("a"))
    b = _FakeCondition(id=ConditionId("b"))
    reg.register(a)
    reg.register(b)

    found = list(reg)
    assert {c.id for c in found} == {ConditionId("a"), ConditionId("b")}

"""События наложения/снятия состояний (T2)."""

from __future__ import annotations

from dnd.application.dto.engine_event import ConditionApplied, ConditionRemoved
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId, SpellId


def test_condition_applied_fields() -> None:
    ev = ConditionApplied(
        caster_id=CreatureId("mage"),
        target_id=CreatureId("orc"),
        spell_id=SpellId("hold_person"),
        conditions=frozenset({PARALYZED}),
        ends_on_damage=False,
        repeat_save_ability=Ability.WIS,
        save_dc=13,
        concentration=True,
    )
    assert ev.target_id == CreatureId("orc")
    assert PARALYZED in ev.conditions
    assert ev.repeat_save_ability is Ability.WIS


def test_condition_removed_fields() -> None:
    ev = ConditionRemoved(
        target_id=CreatureId("orc"),
        conditions=frozenset({PARALYZED}),
        reason="save",
    )
    assert ev.reason == "save"
    assert PARALYZED in ev.conditions

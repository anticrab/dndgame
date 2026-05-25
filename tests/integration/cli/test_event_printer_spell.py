"""P1-11: EventPrinter рендерит SpellCast и HealingApplied."""
from __future__ import annotations

from dnd.application.dto.engine_event import EngineEvent, HealingApplied, SpellCast
from dnd.interfaces.cli.event_printer import EventPrinter


def _capture(event: EngineEvent) -> str:
    lines: list[str] = []
    EventPrinter(sink=lines.append).dispatch_event(event)
    return "\n".join(lines)


def test_spell_cast_with_target() -> None:
    out = _capture(SpellCast(
        caster_id="mage", spell_id="fire_bolt", spell_name="Fire Bolt",
        slot_level=0, target_id="gob",
    ))
    assert "mage" in out and "Fire Bolt" in out and "gob" in out


def test_spell_cast_self() -> None:
    out = _capture(SpellCast(
        caster_id="mage", spell_id="shield_of_faith", spell_name="Shield of Faith",
        slot_level=1, target_id=None,
    ))
    assert "Shield of Faith" in out and " at " not in out


def test_healing_applied() -> None:
    out = _capture(HealingApplied(
        healer_id="cleric", target_id="hero", amount=7, hp_after=9, hp_max=12,
    ))
    assert "hero" in out and "7" in out and "9/12" in out

"""Q-6: EventPrinter рендерит события умирания (CLI+TUI общий форматтер)."""

from __future__ import annotations

from dnd.application.dto.engine_event import (
    CreatureDied,
    CreatureStabilized,
    DeathSaveRolled,
    EngineEvent,
)
from dnd.interfaces.cli.event_printer import EventPrinter


def _capture(event: EngineEvent) -> str:
    lines: list[str] = []
    printer = EventPrinter(sink=lines.append)
    printer.dispatch_event(event)
    return "\n".join(lines)


def test_death_save_rolled_rendered() -> None:
    out = _capture(
        DeathSaveRolled(
            actor_id="hero",
            d20_raw=14,
            result="success",
            successes=1,
            failures=0,
        )
    )
    assert "hero" in out and "death save" in out.lower() and "14" in out


def test_death_save_recovered_rendered() -> None:
    out = _capture(
        DeathSaveRolled(
            actor_id="hero",
            d20_raw=20,
            result="recovered",
            successes=0,
            failures=0,
        )
    )
    assert "hero" in out and "20" in out


def test_creature_died_rendered() -> None:
    out = _capture(CreatureDied(actor_id="hero"))
    assert "hero" in out and "died" in out.lower()


def test_creature_stabilized_rendered() -> None:
    out = _capture(CreatureStabilized(actor_id="hero", by="cleric"))
    assert "hero" in out and "cleric" in out

"""Q-10: StatusWidget показывает пипсы спасбросков от смерти."""

from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.death_save_state import DeathSaveState
from dnd.interfaces.tui.widgets.status_widget import format_status


def _pc() -> Creature:
    c = Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
    )
    c.uses_death_saves = True
    return c


def test_status_shows_death_save_pips_when_dying() -> None:
    c = _pc()
    c.hit_points = c.hit_points.take_damage(10)
    c.death_saves = DeathSaveState(successes=2, failures=1)
    text = format_status(c)
    assert "Death saves" in text
    # 2 успеха + 1 провал = 3 заполненных пипса
    assert text.count("●") == 3
    # остаток до 3: 1 успех-пустой + 2 провал-пустых = 3
    assert text.count("○") == 3


def test_status_no_pips_when_healthy() -> None:
    c = _pc()
    text = format_status(c)
    assert "Death saves" not in text

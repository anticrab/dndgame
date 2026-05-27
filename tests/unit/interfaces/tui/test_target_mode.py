"""TargetModeHandler: Tab-cycle по достижимым врагам, highlights, Enter."""

from unittest.mock import MagicMock

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD
from dnd.interfaces.tui.screens.battle_modes.target_mode import TargetModeHandler


def _make_goblin(cid: str, max_hp: int = 7, ac: int = 13) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=max_hp,
        armor_class=ac,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _screen(
    targets: list[tuple[CreatureId, Square]],
    *,
    actor_pos: Square | None = None,
    participants: dict[CreatureId, Creature] | None = None,
) -> MagicMock:
    s = MagicMock()
    s._reachable_targets = targets
    s._current_actor_position = actor_pos if actor_pos is not None else Square(0, 0)
    s._participants = participants or {}
    return s


def test_initial_target_first_in_list() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    data = h.overlay()
    assert data.cursor == Square(3, 3)
    assert data.highlights.get(Square(3, 3)) == "reverse bold"
    assert data.highlights.get(Square(5, 5)) == "bold"


def test_tab_cycles_to_next() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    cursor = h.overlay().cursor
    assert cursor == Square(5, 5)


def test_tab_wraps_around() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    h.on_key(_screen(targets), "tab")
    cursor = h.overlay().cursor
    assert cursor == Square(3, 3)


def test_shift_tab_cycles_back() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "shift+tab")
    cursor = h.overlay().cursor
    assert cursor == Square(5, 5)  # wrap-around к последней


def test_enter_records_confirmed_target() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "enter")
    assert h.confirmed_target == CreatureId("g1")


def test_escape_marks_cancel() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "escape")
    assert h.cancelled is True


def test_empty_targets_overlay_is_none() -> None:
    h = TargetModeHandler()
    h.on_enter(_screen([]))
    data = h.overlay()
    assert data.cursor is None
    assert data.highlights == {}


def test_hint_shows_index_and_total() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    assert "1/2" in h.overlay().hint
    assert "g1" in h.overlay().hint
    h.on_key(_screen(targets), "tab")
    assert "2/2" in h.overlay().hint
    assert "g2" in h.overlay().hint


def test_hint_includes_hp_ac_and_distance_when_known() -> None:
    g1 = _make_goblin("g1", max_hp=7, ac=13)
    g2 = _make_goblin("g2", max_hp=20, ac=18)
    targets = [(g1.id, Square(3, 3)), (g2.id, Square(8, 0))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets, actor_pos=Square(2, 3), participants={g1.id: g1, g2.id: g2}))
    hint = h.overlay().hint
    assert "HP 7/7" in hint
    assert "AC 13" in hint
    assert "dist=5ft" in hint  # chebyshev (3,3)-(2,3) = 1 клетка = 5 ft
    h.on_key(_screen(targets), "tab")
    hint2 = h.overlay().hint
    assert "HP 20/20" in hint2
    assert "AC 18" in hint2
    # chebyshev (8,0)-(2,3) = max(6,3)=6 клеток = 30 ft
    assert "dist=30ft" in hint2


def test_hint_works_without_participants() -> None:
    """Fallback: если creature нет в _participants — hint без HP/AC,
    но всё ещё показывает id и index. Это не должно ронять рендер."""
    targets = [(CreatureId("ghost"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))  # participants={} по умолчанию
    hint = h.overlay().hint
    assert "ghost" in hint
    assert "1/1" in hint

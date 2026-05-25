"""P2-6/P2-7: AreaModeHandler — выбор зоны (точка / направление) + превью."""
from __future__ import annotations

from dnd.application.engine.spells.area import default_area_shape_registry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.direction import Direction
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import (
    AreaShape,
    OriginMode,
    TargetingSpec,
    TargetKind,
)
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.area_mode import AreaModeHandler


class _FakeScreen:
    """Минимальный ModeScreenContext для AreaModeHandler."""

    def __init__(self, spec: TargetingSpec, range_ft: int, actor: Square) -> None:
        self._pending_area_spec = spec
        self._pending_area_range_ft = range_ft
        self._current_actor_position = actor
        self._current_battlefield = Battlefield(10, 10)
        self._area_registry = default_area_shape_registry()


def _circle_spec() -> TargetingSpec:
    return TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.AT_POINT,
        shape=AreaShape.CIRCLE, radius_ft=10,
    )


def _cone_spec() -> TargetingSpec:
    return TargetingSpec(
        kind=TargetKind.AREA, origin=OriginMode.FROM_CASTER,
        shape=AreaShape.CONE, length_ft=15,
    )


def test_at_point_cursor_moves_and_confirms() -> None:
    h = AreaModeHandler()
    screen = _FakeScreen(_circle_spec(), range_ft=150, actor=Square(2, 2))
    h.on_enter(screen)
    h.on_key(screen, "right")   # курсор → (3,2)
    h.on_key(screen, "down")    # → (3,3)
    assert h.confirmed_point is None
    h.on_key(screen, "enter")
    assert h.confirmed_point == Square(3, 3)
    assert not h.cancelled


def test_at_point_clamped_by_range() -> None:
    # range 5ft = 1 клетка: курсор не уходит дальше 1 от кастера.
    h = AreaModeHandler()
    screen = _FakeScreen(_circle_spec(), range_ft=5, actor=Square(5, 5))
    h.on_enter(screen)
    for _ in range(5):
        h.on_key(screen, "right")
    h.on_key(screen, "enter")
    assert h.confirmed_point == Square(6, 5)  # дальше 1 клетки не ушёл


def test_at_point_preview_highlights_circle() -> None:
    h = AreaModeHandler()
    screen = _FakeScreen(_circle_spec(), range_ft=150, actor=Square(5, 5))
    h.on_enter(screen)
    ov = h.overlay()
    # курсор в центре (на кастере), круг r=2 → задеты 25 клеток (+ курсор-стиль).
    assert ov.cursor == Square(5, 5)
    assert Square(7, 7) in ov.highlights and Square(3, 3) in ov.highlights


def test_from_caster_direction_cycle_and_confirm() -> None:
    h = AreaModeHandler()
    screen = _FakeScreen(_cone_spec(), range_ft=0, actor=Square(5, 5))
    h.on_enter(screen)
    h.on_key(screen, "up")      # направление N
    assert h.confirmed_direction is None
    h.on_key(screen, "enter")
    assert h.confirmed_direction is Direction.N


def test_from_caster_tab_cycles() -> None:
    h = AreaModeHandler()
    screen = _FakeScreen(_cone_spec(), range_ft=0, actor=Square(5, 5))
    h.on_enter(screen)
    h.on_key(screen, "tab")     # default E (idx2) → SE
    h.on_key(screen, "enter")
    assert h.confirmed_direction is Direction.SE


def test_escape_cancels() -> None:
    h = AreaModeHandler()
    screen = _FakeScreen(_circle_spec(), range_ft=150, actor=Square(2, 2))
    h.on_enter(screen)
    h.on_key(screen, "escape")
    assert h.cancelled


def test_pilot_fireball_enters_area_mode_and_casts() -> None:
    """Pilot: PC-кастер давит '6' (Fireball), AREA mode → Enter → CastSpellIntent."""
    import asyncio

    import pytest
    pytest.importorskip("textual")
    from pathlib import Path

    from dnd.application.engine.encounter import Encounter
    from dnd.composition import build_default_runtime_services
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.terrain import FLOOR
    from dnd.domain.values.weapon import LONGSWORD
    from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
    from dnd.infrastructure.rng.real_rng import RealRNG
    from dnd.interfaces.tui.app import TuiApp

    spells = YamlSpellRepository(
        Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"
    )
    mage = Creature.create(
        id_="aelar", name="Aelar",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    mage.spellcasting_ability = Ability.INT
    # порядок known_spells → Fireball на hotkey по позиции
    mage.known_spells = (SpellId("fireball"),)
    mage.spell_slots = {1: 3}
    gob = Creature.create(
        id_="g", name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(10, 10)
    for y in range(10):
        for x in range(10):
            bf.set_terrain(Square(x, y), FLOOR)
    bf.place_creature(mage.id, Square(2, 2))
    bf.place_creature(gob.id, Square(5, 5))
    deps = build_default_runtime_services(rng=RealRNG(seed=1)).with_battlefield(bf)
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(encounter=enc, spell_repository=spells)

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == mage.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("mage не получил ход")
            await pilot.press("1")  # Fireball — первый в action-bar
            await pilot.pause(0.2)
            from dnd.interfaces.tui.screens.battle_modes.protocol import BattleMode
            assert screen._mode is BattleMode.AREA
            await pilot.press("enter")  # каст в текущую точку (на кастере)
            await pilot.pause(0.3)
            assert screen._mode is BattleMode.NORMAL

    asyncio.run(_go())

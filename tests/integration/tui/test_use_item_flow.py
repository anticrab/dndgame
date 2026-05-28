"""U5-1: TUI-флоу «Использовать предмет» — pilot-smoke.

Hotkey 'u' открывает :class:`PlayerItemsScreen` со списком используемых
предметов из инвентаря PC; Enter на SELF-зелье отправляет ``UseItemIntent``
в очередь GameRunner'а, и зелье реально применяется (HP вырос).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from dnd.application.engine.encounter import Encounter
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.item_use import ItemUseSpec
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR
from dnd.domain.values.weapon import LONGSWORD
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
from dnd.infrastructure.rng.real_rng import RealRNG
from dnd.interfaces.tui.app import TuiApp

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


class _MiniItemsRepo:
    def __init__(self) -> None:
        self._items = {
            ItemId("healing_potion"): Item(
                id=ItemId("healing_potion"),
                name="Healing Potion",
                kind=ItemKind.CONSUMABLE,
                weight_lb=0.5,
                stackable=True,
                use=ItemUseSpec(
                    effect_id=SpellId("cure_wounds"),
                    economy="bonus_action",
                    consumed=True,
                    is_scroll=False,
                ),
            ),
            # Свиток cure_wounds — SINGLE + is_scroll=True: при выборе должен
            # вести в TARGET mode для пика цели вручную (а не лечить себя).
            ItemId("scroll_of_cure_wounds"): Item(
                id=ItemId("scroll_of_cure_wounds"),
                name="Scroll of Cure Wounds",
                kind=ItemKind.CONSUMABLE,
                weight_lb=0.1,
                stackable=True,
                use=ItemUseSpec(
                    effect_id=SpellId("cure_wounds"),
                    economy="action",
                    consumed=True,
                    is_scroll=True,
                ),
            ),
        }

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(self._items.keys())

    def load(self, item_id: ItemId) -> Item:
        return self._items[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._items


def _open_bf(w: int, h: int) -> Battlefield:
    bf = Battlefield(w, h)
    for y in range(h):
        for x in range(w):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_u_opens_items_screen_enter_uses_self_potion() -> None:
    pc = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    pc.hit_points = pc.hit_points.take_damage(15)  # 20 → 5
    items_repo = _MiniItemsRepo()
    pc.inventory.add(items_repo.load(ItemId("healing_potion")))
    g = Creature.create(
        id_=CreatureId("g"),
        name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = _open_bf(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(g.id, Square(7, 7))  # далеко, не атакует
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(
        encounter=enc,
        item_repository=items_repo,
        spell_repository=YamlSpellRepository(_SPELLS),
    )

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            hp_before = pc.hit_points.current
            await pilot.press("u")
            await pilot.pause(0.2)
            assert "PlayerItemsScreen" in type(pilot.app.screen).__name__
            await pilot.press("enter")
            await pilot.pause(0.5)
            assert "BattleScreen" in type(pilot.app.screen).__name__
            # Зелье выпито: HP вырос, расходник списан.
            assert pc.hit_points.current > hp_before
            assert not pc.inventory.contains(ItemId("healing_potion"))

    asyncio.run(_go())


def test_u_without_usable_items_skips() -> None:
    """Если в инвентаре нет используемых предметов — экран НЕ открывается."""
    pc = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    # Положим не-используемый предмет (gold) — экран всё равно не должен открыться.
    pc.inventory.add(
        Item(id=ItemId("gold"), name="Gold", kind=ItemKind.MISC, weight_lb=0.02, stackable=True)
    )
    g = Creature.create(
        id_=CreatureId("g"),
        name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = _open_bf(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(g.id, Square(7, 7))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, g.id: g},
        factions={pc.id: Faction.PARTY, g.id: Faction.MONSTERS},
        deps=deps,
    )
    app = TuiApp(encounter=enc, spell_repository=YamlSpellRepository(_SPELLS))

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("u")
            await pilot.pause(0.2)
            # Остались в BattleScreen — PlayerItemsScreen не открылся.
            assert "BattleScreen" in type(pilot.app.screen).__name__

    asyncio.run(_go())


def test_u_scroll_single_enters_target_mode_then_uses() -> None:
    """SINGLE-свиток (is_scroll=True): после выбора в PlayerItemsScreen
    BattleScreen входит в TARGET mode (а не лечит сразу), Enter на цели
    отправляет ``UseItemIntent`` — союзник реально лечится."""
    pc = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    ally = Creature.create(
        id_=CreatureId("ally"),
        name="Ally",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=12,
        speed_ft=30,
    )
    ally.hit_points = ally.hit_points.take_damage(12)  # 20 → 8
    items_repo = _MiniItemsRepo()
    pc.inventory.add(items_repo.load(ItemId("scroll_of_cure_wounds")))
    # Encounter не заключается, пока живы враги — нужен далёкий гоблин.
    g = Creature.create(
        id_=CreatureId("g"),
        name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    bf = _open_bf(12, 12)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(ally.id, Square(3, 2))  # 5 ft — в reach у cure_wounds
    bf.place_creature(g.id, Square(11, 11))  # далеко, не атакует
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, ally.id: ally, g.id: g},
        factions={
            pc.id: Faction.PARTY,
            ally.id: Faction.PARTY,
            g.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    app = TuiApp(
        encounter=enc,
        item_repository=items_repo,
        spell_repository=YamlSpellRepository(_SPELLS),
    )

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            hp_before_ally = ally.hit_points.current
            await pilot.press("u")
            await pilot.pause(0.2)
            assert "PlayerItemsScreen" in type(pilot.app.screen).__name__
            await pilot.press("enter")  # выбрали свиток
            await pilot.pause(0.3)
            # После выбора SINGLE-свитка должен открыться TARGET mode
            # в BattleScreen, а не сразу применить.
            assert "BattleScreen" in type(pilot.app.screen).__name__
            assert pilot.app.screen._mode.value == "target"  # type: ignore[attr-defined]
            # В TARGET mode сейчас выбран первый из reachable (PC). Tab —
            # на следующего (ally), потом Enter — confirm.
            await pilot.press("tab")
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.5)
            # Свиток применился: HP союзника вырос, расходник списан.
            assert ally.hit_points.current > hp_before_ally
            assert not pc.inventory.contains(ItemId("scroll_of_cure_wounds"))

    asyncio.run(_go())


def test_u_escape_clears_pending_use_item() -> None:
    """Cancel SINGLE-таргетинга после выбора свитка должен очистить
    ``_pending_use_item`` — иначе следующая операция атаки/каста ушла бы
    как UseItemIntent."""
    pc = Creature.create(
        id_=CreatureId("aelar"),
        name="Aelar",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    ally = Creature.create(
        id_=CreatureId("ally"),
        name="Ally",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=12,
        speed_ft=30,
    )
    ally.hit_points = ally.hit_points.take_damage(12)
    g = Creature.create(
        id_=CreatureId("g"),
        name="G",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    items_repo = _MiniItemsRepo()
    pc.inventory.add(items_repo.load(ItemId("scroll_of_cure_wounds")))
    bf = _open_bf(12, 12)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(ally.id, Square(3, 2))
    bf.place_creature(g.id, Square(11, 11))
    services = build_default_runtime_services(rng=RealRNG(seed=42))
    deps = services.with_battlefield(bf)
    enc = Encounter(
        participants={pc.id: pc, ally.id: ally, g.id: g},
        factions={
            pc.id: Faction.PARTY,
            ally.id: Faction.PARTY,
            g.id: Faction.MONSTERS,
        },
        deps=deps,
    )
    app = TuiApp(
        encounter=enc,
        item_repository=items_repo,
        spell_repository=YamlSpellRepository(_SPELLS),
    )

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.3)
            screen = pilot.app.screen
            for _ in range(60):
                if getattr(screen, "_current", None) is not None:
                    actor, _, _ = screen._current
                    if actor.id == pc.id:
                        break
                await pilot.pause(0.1)
            if getattr(screen, "_current", None) is None:
                pytest.skip("PC did not get a turn within timeout")
            await pilot.press("u")
            await pilot.pause(0.2)
            await pilot.press("enter")  # выбрали свиток → в TARGET mode
            await pilot.pause(0.2)
            assert pilot.app.screen._mode.value == "target"  # type: ignore[attr-defined]
            assert pilot.app.screen._pending_use_item is not None  # type: ignore[attr-defined]
            await pilot.press("escape")  # отмена таргетинга
            await pilot.pause(0.2)
            assert pilot.app.screen._mode.value == "normal"  # type: ignore[attr-defined]
            # _pending_use_item очищен — иначе следующая атака ушла бы как Use.
            assert pilot.app.screen._pending_use_item is None  # type: ignore[attr-defined]
            # Свиток на месте (не применили).
            assert pc.inventory.contains(ItemId("scroll_of_cure_wounds"))

    asyncio.run(_go())

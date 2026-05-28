"""U4: свитки cure_wounds/fireball — slotless с фикс-Сл по уровню (PHB-2024).

Свиток у не-кастера работает (нет ``spellcasting_ability`` — это норма для
свитка), эффект применяется по ``SpellPower.scroll(spell_level)``: DC по
таблице PHB-2024, ability_mod=0. Слот не тратится (его и нет у не-кастера),
расходник списан, ``ItemUsed`` опубликован."""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.engine_event import DamageDealt, HealingApplied, ItemUsed
from dnd.application.engine.actions.use_item import UseItemAction, UseItemParams
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.item import ItemId
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_DATA = Path(__file__).resolve().parents[3] / "data" / "content"
_ITEMS = _DATA / "items.yaml"
_SPELLS = _DATA / "spells.yaml"


def _non_caster() -> Creature:
    """Воин — НЕ-кастер: ``spellcasting_ability`` остаётся None."""
    return Creature.create(
        id_="fighter",
        name="Fighter",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=8, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
    )


def _goblin(id_: str, x: int, y: int) -> Creature:
    # max_hp=50, чтобы пережили 8d6 (для проверки точных чисел урона).
    return Creature.create(
        id_=id_,
        name=id_,
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=50,
        armor_class=13,
        speed_ft=30,
    )


def test_scroll_of_cure_wounds_heals_without_slot() -> None:
    fighter = _non_caster()
    fighter.hit_points = fighter.hit_points.take_damage(12)  # 20 → 8
    items = YamlItemRepository(_ITEMS)
    spells = YamlSpellRepository(_SPELLS)
    fighter.inventory.add(items.load(ItemId("scroll_of_cure_wounds")))
    bf = Battlefield(5, 5)
    bf.place_creature(fighter.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[6])  # 1d8 = 6
    ctx = TurnContext(
        actor_id=fighter.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={fighter.id: fighter},
        movement_remaining_ft=30,
    )
    healed: list[HealingApplied] = []
    used: list[ItemUsed] = []
    ctx.event_bus.subscribe(HealingApplied, healed.append)
    ctx.event_bus.subscribe(ItemUsed, used.append)
    out = UseItemAction(spells).execute(
        fighter,
        UseItemParams(item_id=ItemId("scroll_of_cure_wounds"), target_id=fighter.id),
        ctx,
    )
    assert out.success
    # ability_mod=0 у свитка → 1d8 чистыми = 6 (не +INT кастера).
    assert healed and healed[0].amount == 6
    assert fighter.hit_points.current == 14  # 8 + 6
    assert fighter.inventory.contains(ItemId("scroll_of_cure_wounds")) is False
    assert used and used[0].effect == "heal"


def test_scroll_of_fireball_works_for_non_caster_at_scroll_dc() -> None:
    """Не-кастер использует свиток fireball (ур.3, DC15 по таблице PHB):

    * каст проходит (нет ``spellcasting_ability`` — у свитка DC своя);
    * урон применяется к обеим целям в AoE (фрэндли-фaйр включён, кастер
      вне зоны);
    * один цел проваливает спас → полный урон, другой успешен → половина
      (различимое отношение урона свидетельствует о реальном DC, а не нулевом).
    """
    fighter = _non_caster()
    assert fighter.spellcasting_ability is None  # суть теста
    g_fail, g_save = _goblin("g_fail", 5, 5), _goblin("g_save", 6, 5)
    items = YamlItemRepository(_ITEMS)
    spells = YamlSpellRepository(_SPELLS)
    fighter.inventory.add(items.load(ItemId("scroll_of_fireball")))
    bf = Battlefield(10, 10)
    # Кастер в дальнем углу: Chebyshev(0,0)↔(5,5) = 5 клеток = 25 ft, вне
    # радиуса 20 ft — friendly-fire на себя не сработает.
    bf.place_creature(fighter.id, Square(0, 0))
    bf.place_creature(g_fail.id, Square(5, 5))
    bf.place_creature(g_save.id, Square(6, 5))
    # SaveSpellHandler катит per-target: 8d6 (damage) + d20 (save). У гоблина
    # DEX=14 → +2. g_fail: d20=5+2=7 vs DC15 → провал, полный 24. g_save:
    # d20=20+2=22 → успех (save_for_half) → половина 12. С запасом 3-ек.
    deps, _bus, _ = build_scripted_dependencies(
        battlefield=bf,
        rolls=[3] * 8 + [5] + [3] * 8 + [20] + [3] * 20,
    )
    ctx = TurnContext(
        actor_id=fighter.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={fighter.id: fighter, g_fail.id: g_fail, g_save.id: g_save},
        factions={
            fighter.id: Faction.PARTY,
            g_fail.id: Faction.MONSTERS,
            g_save.id: Faction.MONSTERS,
        },
        movement_remaining_ft=30,
    )
    used: list[ItemUsed] = []
    dmg: list[DamageDealt] = []
    ctx.event_bus.subscribe(ItemUsed, used.append)
    ctx.event_bus.subscribe(DamageDealt, dmg.append)
    out = UseItemAction(spells).execute(
        fighter,
        UseItemParams(item_id=ItemId("scroll_of_fireball"), target_point=Square(5, 5)),
        ctx,
    )
    assert out.success
    by_target: dict[CreatureId, int] = {d.target_id: d.final_amount for d in dmg}
    # Один провалил → полный 24, второй спасся → половина 12 (save_for_half).
    assert by_target.get(g_fail.id) == 24
    assert by_target.get(g_save.id) == 12
    # Свиток списан, событие опубликовано, эффект — SAVE-fireball.
    assert fighter.inventory.contains(ItemId("scroll_of_fireball")) is False
    assert used and used[0].effect == "save"

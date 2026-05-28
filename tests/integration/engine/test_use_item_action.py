"""UseItemAction — slotless-применение эффекта предмета (U2-4).

Покрытие: зелье лечения у не-кастера выпивается, ``ItemUsed`` + ``HealingApplied``
публикуются, расходник списывается из инвентаря, экономика тратится из данных
``ItemUseSpec.economy`` (``bonus_action`` — не ACTION)."""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.action import ActionEconomyCost, Allowed, Forbidden
from dnd.application.dto.engine_event import HealingApplied, ItemUsed
from dnd.application.engine.actions.use_item import UseItemAction, UseItemParams
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import SpellId
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.item_use import ItemUseSpec
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path(__file__).resolve().parents[3] / "data" / "content" / "spells.yaml"


def _repo() -> YamlSpellRepository:
    return YamlSpellRepository(_SPELLS)


def _hero() -> Creature:
    # Намеренно не кастер — свиток/зелье должны работать без spellcasting_ability.
    return Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=8, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )


def _healing_potion() -> Item:
    return Item(
        id=ItemId("healing_potion"),
        name="Healing Potion",
        kind=ItemKind.CONSUMABLE,
        weight_lb=0.5,
        description="2d4+2",
        stackable=True,
        use=ItemUseSpec(
            effect_id=SpellId("cure_wounds"),  # 1d8 — есть в каталоге
            economy="bonus_action",
            consumed=True,
            is_scroll=False,
        ),
    )


def _setup(rolls: list[int]) -> tuple[Creature, TurnContext]:
    hero = _hero()
    hero.inventory.add(_healing_potion())
    bf = Battlefield(5, 5)
    bf.place_creature(hero.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    ctx = TurnContext(
        actor_id=hero.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={hero.id: hero},
        movement_remaining_ft=30,
    )
    return hero, ctx


def test_use_healing_potion_self_heals_and_consumes() -> None:
    hero, ctx = _setup(rolls=[6])  # 1d8 = 6
    hero.hit_points = hero.hit_points.take_damage(15)  # 20 → 5
    used: list[ItemUsed] = []
    healed: list[HealingApplied] = []
    ctx.event_bus.subscribe(ItemUsed, used.append)
    ctx.event_bus.subscribe(HealingApplied, healed.append)
    action = UseItemAction(_repo())
    params = UseItemParams(item_id=ItemId("healing_potion"), target_id=hero.id)
    avail = action.can_perform_against(hero, params, ctx)
    assert isinstance(avail, Allowed)
    out = action.execute(hero, params, ctx)
    assert out.success
    assert out.consumed is ActionEconomyCost.BONUS_ACTION
    assert used and used[0].item_id == ItemId("healing_potion")
    assert used[0].effect == "heal"
    assert used[0].consumed is True
    assert healed and healed[0].target_id == hero.id
    assert healed[0].amount > 0  # 1d8 = 6, ability_mod=0 (зелье)
    # Расходник списан (был 1 — должен исчезнуть).
    assert hero.inventory.contains(ItemId("healing_potion")) is False


def test_use_item_forbidden_if_not_in_inventory() -> None:
    hero, ctx = _setup(rolls=[6])
    # инвентарь содержит зелье — но другой id
    action = UseItemAction(_repo())
    params = UseItemParams(item_id=ItemId("nonexistent"), target_id=hero.id)
    avail = action.can_perform_against(hero, params, ctx)
    assert isinstance(avail, Forbidden)


def test_use_item_forbidden_if_no_use_spec() -> None:
    hero, ctx = _setup(rolls=[6])
    # положим в инвентарь не-используемый предмет
    plain = Item(
        id=ItemId("gold"),
        name="Gold",
        kind=ItemKind.MISC,
        weight_lb=0.0,
        stackable=True,
    )
    hero.inventory.add(plain)
    action = UseItemAction(_repo())
    params = UseItemParams(item_id=ItemId("gold"))
    avail = action.can_perform_against(hero, params, ctx)
    assert isinstance(avail, Forbidden)


# === Forbidden-ветки can_perform_against (U-post-review #3) ===


def _item_with_use(effect_id: SpellId, *, economy: str = "bonus_action") -> Item:
    return Item(
        id=ItemId("custom_use"),
        name="Custom",
        kind=ItemKind.CONSUMABLE,
        weight_lb=0.0,
        stackable=True,
        use=ItemUseSpec(effect_id=effect_id, economy=economy, consumed=True, is_scroll=False),
    )


def test_forbidden_unknown_effect() -> None:
    """``ItemUseSpec.effect_id`` отсутствует в каталоге — Forbidden."""
    hero, ctx = _setup(rolls=[1])
    hero.inventory.add(_item_with_use(SpellId("nonexistent_spell")))
    avail = UseItemAction(_repo()).can_perform_against(
        hero, UseItemParams(item_id=ItemId("custom_use"), target_id=hero.id), ctx
    )
    assert isinstance(avail, Forbidden)
    assert "unknown effect" in avail.details


def test_forbidden_no_economy_left() -> None:
    """Бонусное действие уже потрачено в этом ходу — Forbidden."""
    hero, ctx = _setup(rolls=[1])
    ctx.spend(ActionEconomyCost.BONUS_ACTION)  # съели бонусное наперёд
    avail = UseItemAction(_repo()).can_perform_against(
        hero, UseItemParams(item_id=ItemId("healing_potion"), target_id=hero.id), ctx
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "no_economy_left"


def test_forbidden_single_no_target_id() -> None:
    """SINGLE без target_id — NO_VALID_TARGETS."""
    hero, ctx = _setup(rolls=[1])
    avail = UseItemAction(_repo()).can_perform_against(
        hero, UseItemParams(item_id=ItemId("healing_potion"), target_id=None), ctx
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "no_valid_targets"


def test_forbidden_single_target_not_in_participants() -> None:
    """SINGLE с target_id, отсутствующим в encounter — NO_VALID_TARGETS."""
    hero, ctx = _setup(rolls=[1])
    avail = UseItemAction(_repo()).can_perform_against(
        hero,
        UseItemParams(item_id=ItemId("healing_potion"), target_id="ghost"),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "no_valid_targets"


def test_forbidden_target_down_dead() -> None:
    """Лечение/бафф мёртвой (не dying) цели — TARGET_DOWN."""
    hero, ctx = _setup(rolls=[1])
    # ally в encounter, но мёртв окончательно
    ally = Creature.create(
        id_="ally",
        name="Ally",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    ally.hit_points = ally.hit_points.take_damage(100)  # 0 HP
    ctx.participants[ally.id] = ally  # type: ignore[index]
    ctx.battlefield.place_creature(ally.id, Square(3, 3))
    avail = UseItemAction(_repo()).can_perform_against(
        hero,
        UseItemParams(item_id=ItemId("healing_potion"), target_id=ally.id),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "target_down"


def test_forbidden_out_of_range_single() -> None:
    """SINGLE-цель за пределами range (cure_wounds = 5 ft) — OUT_OF_RANGE."""
    hero, ctx = _setup(rolls=[1])
    ally = Creature.create(
        id_="ally",
        name="Ally",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
    )
    ctx.participants[ally.id] = ally  # type: ignore[index]
    ctx.battlefield.place_creature(ally.id, Square(4, 4))  # 2 клетки = 10 ft > 5
    avail = UseItemAction(_repo()).can_perform_against(
        hero,
        UseItemParams(item_id=ItemId("healing_potion"), target_id=ally.id),
        ctx,
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "out_of_range"


def test_forbidden_area_no_target_point() -> None:
    """AREA AT_POINT без target_point — NO_VALID_TARGETS."""
    hero, ctx = _setup(rolls=[1])
    # Свиток fireball: AREA AT_POINT, требует target_point.
    hero.inventory.add(
        Item(
            id=ItemId("scroll"),
            name="Scroll",
            kind=ItemKind.CONSUMABLE,
            weight_lb=0.0,
            stackable=True,
            use=ItemUseSpec(effect_id=SpellId("fireball"), economy="action", is_scroll=True),
        )
    )
    avail = UseItemAction(_repo()).can_perform_against(
        hero, UseItemParams(item_id=ItemId("scroll"), target_point=None), ctx
    )
    assert isinstance(avail, Forbidden)
    assert avail.reason.value == "no_valid_targets"


def test_forbidden_multi_too_many_targets() -> None:
    """MULTI с числом целей > max_targets — CUSTOM (too many targets).

    magic_missile в каталоге — MULTI с max_targets=3."""
    hero, ctx = _setup(rolls=[1])
    hero.inventory.add(
        Item(
            id=ItemId("scroll_mm"),
            name="Scroll MM",
            kind=ItemKind.CONSUMABLE,
            weight_lb=0.0,
            stackable=True,
            use=ItemUseSpec(effect_id=SpellId("magic_missile"), economy="action", is_scroll=True),
        )
    )
    # 4 цели > 3 max
    targets = (hero.id, hero.id, hero.id, hero.id)
    avail = UseItemAction(_repo()).can_perform_against(
        hero, UseItemParams(item_id=ItemId("scroll_mm"), target_ids=targets), ctx
    )
    assert isinstance(avail, Forbidden)
    assert "too many" in avail.details

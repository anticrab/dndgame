"""Creature.ability_ids + Creature.keybindings — поля L2-T4."""

from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.weapon import LONGSWORD


def _make() -> Creature:
    return Creature.create(
        id_=CreatureId("x"),
        name="X",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def test_default_abilities_includes_attack() -> None:
    c = _make()
    assert AbilityId("weapon_attack") in c.ability_ids


def test_default_abilities_six_basic() -> None:
    """6 базовых — синхронизировано с register_default_abilities (L2-3)."""
    c = _make()
    assert set(c.ability_ids) == {
        AbilityId("weapon_attack"),
        AbilityId("dodge"),
        AbilityId("dash"),
        AbilityId("disengage"),
        AbilityId("interact"),
        AbilityId("break_object"),
    }


def test_default_keybindings_empty() -> None:
    c = _make()
    assert c.keybindings == {}


def test_custom_keybinding_override() -> None:
    """Mutable dict: пользователь может переназначить hotkey."""
    c = _make()
    c.keybindings["z"] = AbilityId("weapon_attack")
    assert c.keybindings == {"z": AbilityId("weapon_attack")}


def test_each_creature_has_own_keybindings_dict() -> None:
    """default_factory=dict гарантирует, что dict не шарится между instance'ами."""
    c1 = _make()
    c2 = _make()
    c1.keybindings["z"] = AbilityId("weapon_attack")
    assert c2.keybindings == {}


def test_creature_has_empty_inventory_by_default() -> None:
    """O-4: новые существа без явного inventory получают пустой."""
    c = _make()
    assert c.inventory.slot_count() == 0
    assert c.inventory.total_weight_lb() == 0


def test_creature_keeps_each_inventory_separate() -> None:
    """default_factory=Inventory — у каждого инстанса свой рюкзак,
    не shared mutable default."""
    c1 = _make()
    c2 = _make()
    from dnd.domain.values.item import Item, ItemId, ItemKind

    c1.inventory.add(Item(id=ItemId("x"), name="X", kind=ItemKind.MISC))
    assert c2.inventory.slot_count() == 0


def test_creature_accepts_preloaded_inventory_via_create() -> None:
    """Стартовый набор — через kwarg Creature.create(inventory=...)."""
    from dnd.domain.entities.inventory import Inventory
    from dnd.domain.values.item import Item, ItemId, ItemKind

    inv = Inventory()
    inv.add(Item(id=ItemId("gold"), name="Gold", kind=ItemKind.MISC, stackable=True), qty=10)
    c = Creature.create(
        id_=CreatureId("y"),
        name="Y",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=10,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
        inventory=inv,
    )
    assert c.inventory.find_by_id(ItemId("gold")).qty == 10  # type: ignore[union-attr]

"""U5-3: ``MonsterTemplate.starting_inventory`` — PC/монстр начинает со
стартовым набором предметов.

Поле — кортеж item-id'ов; конкретный ``Item`` грузится из ``ItemRepository``
(прокидывается опциональным kwarg'ом в :func:`build_creature_from_template`).
Без репозитория — поле игнорируется (для тестов, не прокидывающих его)."""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.templates import AbilityScoresTemplate, MonsterTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.application.ports.content_repository import ContentRepository
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.item import ItemId
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_DATA = Path(__file__).resolve().parents[3] / "data" / "content"


def _content() -> ContentRepository:
    return YamlContentRepository(content_dir=_DATA)


def _abilities() -> AbilityScoresTemplate:
    return AbilityScoresTemplate.model_validate(
        {"str": 14, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 10}
    )


def test_starting_inventory_applied_when_item_repo_given() -> None:
    tpl = MonsterTemplate(
        id="hero_demo",
        name="Hero",
        abilities=_abilities(),
        max_hp=20,
        armor_class=14,
        starting_inventory=("healing_potion", "scroll_of_fireball"),
    )
    items = YamlItemRepository(_DATA / "items.yaml")
    creature = build_creature_from_template(
        tpl,
        instance_id=CreatureId("hero"),
        content=_content(),
        item_repository=items,
    )
    assert creature.inventory.contains(ItemId("healing_potion"))
    assert creature.inventory.contains(ItemId("scroll_of_fireball"))


def test_starting_inventory_ignored_without_item_repo() -> None:
    """Backward-compat: тесты без item_repository не падают."""
    tpl = MonsterTemplate(
        id="hero_demo",
        name="Hero",
        abilities=_abilities(),
        max_hp=20,
        armor_class=14,
        starting_inventory=("healing_potion",),
    )
    creature = build_creature_from_template(tpl, instance_id=CreatureId("hero"), content=_content())
    assert not creature.inventory.contains(ItemId("healing_potion"))


def test_default_empty_starting_inventory() -> None:
    tpl = MonsterTemplate(
        id="hero_demo", name="Hero", abilities=_abilities(), max_hp=20, armor_class=14
    )
    items = YamlItemRepository(_DATA / "items.yaml")
    creature = build_creature_from_template(
        tpl,
        instance_id=CreatureId("hero"),
        content=_content(),
        item_repository=items,
    )
    assert creature.inventory.slot_count() == 0

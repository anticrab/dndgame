"""Тесты ``YamlContentRepository`` + builder'ов из шаблонов.

Используем настоящие YAML-файлы из ``data/content/`` — это и есть
контракт «MVP контент существует и валиден».
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.engine.builder import (
    build_creature_from_template,
    build_weapon_profile,
)
from dnd.application.ports.content_repository import ContentRepository
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTENT = _REPO_ROOT / "data" / "content"


@pytest.fixture
def repo() -> YamlContentRepository:
    return YamlContentRepository(_DEFAULT_CONTENT)


# -- Protocol conformance ---------------------------------------------


def test_yaml_repo_is_content_repository(repo: YamlContentRepository) -> None:
    """runtime_checkable Protocol: YamlContentRepository — это
    ContentRepository по структуре."""
    assert isinstance(repo, ContentRepository)


# -- Weapons -----------------------------------------------------------


def test_weapons_loaded(repo: YamlContentRepository) -> None:
    ids = {w.id for w in repo.weapons()}
    assert {"longsword", "shortsword", "scimitar", "shortbow"} <= ids


def test_longsword_template_fields(repo: YamlContentRepository) -> None:
    w = repo.weapon_by_id("longsword")
    assert w.name == "Long Sword"
    assert w.kind is AttackKind.MELEE
    assert w.damage_expr == "1d8"
    assert w.damage_type is DamageType.SLASHING
    assert w.range_ft == 5
    assert w.ability == "STR"
    assert w.finesse is False


def test_unknown_weapon_raises(repo: YamlContentRepository) -> None:
    with pytest.raises(KeyError, match="unknown weapon"):
        repo.weapon_by_id("plasma_sword")


# -- Monsters ----------------------------------------------------------


def test_goblin_template(repo: YamlContentRepository) -> None:
    m = repo.monster_by_id("goblin")
    assert m.name == "Goblin"
    assert m.max_hp == 7
    assert m.armor_class == 13
    assert m.weapon_id == "scimitar"
    assert m.default_faction is Faction.MONSTERS
    assert m.abilities.dex == 14


# -- Builder: Weapon ---------------------------------------------------


def test_build_weapon_profile(repo: YamlContentRepository) -> None:
    profile = build_weapon_profile(repo.weapon_by_id("scimitar"))
    assert profile.name == "Scimitar"
    assert profile.kind is AttackKind.MELEE
    assert profile.finesse is True


# -- Builder: Creature -------------------------------------------------


def test_build_creature_from_goblin_template(
    repo: YamlContentRepository,
) -> None:
    """Полный цикл: YAML → MonsterTemplate → Creature с оружием."""
    template = repo.monster_by_id("goblin")
    goblin = build_creature_from_template(
        template,
        instance_id=CreatureId("goblin#1"),
        content=repo,
    )
    assert goblin.id == "goblin#1"
    assert goblin.name == "Goblin"
    assert goblin.hit_points.current == 7
    assert goblin.hit_points.maximum == 7
    assert goblin.armor_class == 13
    assert goblin.equipped_weapon is not None
    assert goblin.equipped_weapon.name == "Scimitar"


def test_build_creature_without_weapon(
    repo: YamlContentRepository,
) -> None:
    """Если weapon_id=None в шаблоне — equipped_weapon=None."""
    # Конструируем шаблон в памяти, без weapon.
    from dnd.application.dto.templates import (
        AbilityScoresTemplate,
        MonsterTemplate,
    )
    template = MonsterTemplate(
        id="dummy",
        name="Dummy",
        abilities=AbilityScoresTemplate(
            str=10, dex=10, con=10, int=10, wis=10, cha=10
        ),
        max_hp=5,
        armor_class=10,
        weapon_id=None,
    )
    creature = build_creature_from_template(
        template,
        instance_id=CreatureId("dummy#1"),
        content=repo,
    )
    assert creature.equipped_weapon is None


# -- Repository: edge cases -------------------------------------------


def test_repo_rejects_nonexistent_dir() -> None:
    with pytest.raises(FileNotFoundError, match="content_dir"):
        YamlContentRepository(Path("/nonexistent/path/qwerty"))


def test_empty_repo_dir(tmp_path: Path) -> None:
    """Пустой каталог — репозиторий валиден, всё пусто."""
    empty = YamlContentRepository(tmp_path)
    assert empty.weapons() == ()
    assert empty.monsters() == ()
    assert empty.scenarios() == ()


def test_repo_rejects_malformed_yaml(tmp_path: Path) -> None:
    """YAML с топ-уровневым словарём вместо списка → ValueError."""
    (tmp_path / "weapons.yaml").write_text("not_a_list: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level list"):
        YamlContentRepository(tmp_path)

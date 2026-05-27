"""T1: профициентные спасброски заполняются из класса при сборке Creature."""

from __future__ import annotations

from pathlib import Path

from dnd.application.dto.templates import AbilityScoresTemplate, MonsterTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository


class _NoContent:
    """ContentRepository-заглушка: шаблон без оружия её не трогает."""


def _tmpl(cc: str | None) -> MonsterTemplate:
    return MonsterTemplate(
        id="t",
        name="T",
        abilities=AbilityScoresTemplate.model_validate(
            {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
        ),
        max_hp=20,
        armor_class=16,
        character_class=cc,
        level=1,
    )


def _repo() -> YamlClassRepository:
    return YamlClassRepository(Path("data/content/classes.yaml"))


def test_builder_sets_class_save_proficiencies() -> None:
    c = build_creature_from_template(
        _tmpl("fighter"),
        instance_id=CreatureId("f1"),
        content=_NoContent(),  # type: ignore[arg-type]
        class_repository=_repo(),
    )
    assert c.saving_throw_proficiencies == frozenset({Ability.STR, Ability.CON})


def test_builder_no_class_repo_empty_profs() -> None:
    c = build_creature_from_template(
        _tmpl("fighter"),
        instance_id=CreatureId("f2"),
        content=_NoContent(),  # type: ignore[arg-type]
    )
    assert c.saving_throw_proficiencies == frozenset()


def test_builder_monster_without_class_empty_profs() -> None:
    c = build_creature_from_template(
        _tmpl(None),
        instance_id=CreatureId("m1"),
        content=_NoContent(),  # type: ignore[arg-type]
        class_repository=_repo(),
    )
    assert c.saving_throw_proficiencies == frozenset()

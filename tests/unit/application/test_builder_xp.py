"""Этап D: `MonsterTemplate.xp` переносится в Creature.xp билдером.

Нужно для демо-сцены: воин-«бывалый» стартует с накопленным XP (как после
пары стычек по канону SCENARIO_DEMO), чтобы первое же добивание в демо-бою
перешагнуло порог уровня — level-up прямо в бою без лишающего смысла свармя
из четырёх гоблинов на соло-персонажа.
"""

from __future__ import annotations

from dnd.application.dto.templates import AbilityScoresTemplate, MonsterTemplate
from dnd.application.engine.builder import build_creature_from_template
from dnd.domain.values.ids import CreatureId


class _NoContent:
    """ContentRepository-заглушка: шаблон без оружия/заклинаний её не трогает."""


def _abilities() -> AbilityScoresTemplate:
    return AbilityScoresTemplate.model_validate(
        {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
    )


def test_template_xp_defaults_to_zero() -> None:
    tmpl = MonsterTemplate(id="m", name="M", abilities=_abilities(), max_hp=10, armor_class=12)
    assert tmpl.xp == 0
    creature = build_creature_from_template(
        tmpl,
        instance_id=CreatureId("m1"),
        content=_NoContent(),  # type: ignore[arg-type]
    )
    assert creature.xp == 0


def test_template_xp_propagates_to_creature() -> None:
    tmpl = MonsterTemplate(
        id="vet",
        name="Veteran",
        abilities=_abilities(),
        max_hp=20,
        armor_class=16,
        character_class="fighter",
        level=1,
        xp=60,
    )
    creature = build_creature_from_template(
        tmpl,
        instance_id=CreatureId("vet1"),
        content=_NoContent(),  # type: ignore[arg-type]
    )
    assert creature.xp == 60

"""Spell.duration (X0-5): дефолт INSTANT + парсинг длительности из YAML."""

from __future__ import annotations

from pathlib import Path

from dnd.domain.values.damage import DamageType
from dnd.domain.values.duration import Duration, DurationUnit
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path("data/content/spells.yaml")


def test_default_duration_is_instant() -> None:
    spell = Spell(
        id=SpellId("x"),
        name="x",
        level=1,
        school="evocation",
        effect=SpellEffect.AUTO,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=30,
        description="",
        dice="1d4",
        damage_type=DamageType.FORCE,
    )
    assert spell.duration == Duration.instant()


def test_bless_duration_parsed_from_yaml() -> None:
    bless = YamlSpellRepository(_SPELLS).load(SpellId("bless"))
    assert bless.duration.unit is DurationUnit.CONCENTRATION
    assert bless.duration.to_rounds() == 10  # 1 минута концентрации = 10 раундов


def test_instant_spell_has_no_clock_deadline() -> None:
    fire_bolt = YamlSpellRepository(_SPELLS).load(SpellId("fire_bolt"))
    assert fire_bolt.duration.to_rounds() == 0

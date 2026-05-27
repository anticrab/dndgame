"""YamlSpellRepository — каталог заклинаний из одного YAML-файла.

Формат — список заклинаний (см. data/content/spells.yaml). Поля совпадают с
:class:`Spell`; ``targeting`` — вложенный объект ``{kind, max_targets, origin,
shape, radius_ft, length_ft}``. Отсутствующий файл → пустой репозиторий.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dnd.domain.values.ability import Ability
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import ConditionId, SpellId
from dnd.domain.values.modifiers import ModifierTargetKind
from dnd.domain.values.spell import (
    AreaShape,
    BuffSpec,
    OriginMode,
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)


class YamlSpellRepository:
    def __init__(self, spells_file: Path) -> None:
        self._file = spells_file
        self._by_id: dict[SpellId, Spell] = {}
        if spells_file.exists():
            self._reload()

    def _reload(self) -> None:
        raw = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        if raw is None:
            return
        if not isinstance(raw, list):
            raise ValueError(f"spells file {self._file} must contain a list, got {type(raw)}")
        self._by_id = {}
        for entry in raw:
            spell = self._parse(entry)
            if spell.id in self._by_id:
                raise ValueError(f"duplicate spell id {spell.id!r} in {self._file}")
            self._by_id[spell.id] = spell

    def _parse(self, entry: dict[str, Any]) -> Spell:
        tgt = entry["targeting"]
        shape_raw = tgt.get("shape")
        targeting = TargetingSpec(
            kind=TargetKind(tgt["kind"]),
            max_targets=int(tgt.get("max_targets", 1)),
            origin=OriginMode(tgt.get("origin", OriginMode.AT_POINT.value)),
            shape=AreaShape(shape_raw) if shape_raw is not None else None,
            radius_ft=int(tgt.get("radius_ft", 0)),
            length_ft=int(tgt.get("length_ft", 0)),
            allow_repeat_target=bool(tgt.get("allow_repeat_target", False)),
        )
        dmg = entry.get("damage_type")
        save = entry.get("save_ability")
        buffs = tuple(
            BuffSpec(
                target=ModifierTargetKind(b["target"]),
                numeric_bonus=int(b.get("numeric_bonus", 0)),
                dice_bonus=b.get("dice_bonus"),
            )
            for b in entry.get("buffs", [])
        )
        return Spell(
            id=SpellId(entry["id"]),
            name=entry["name"],
            level=int(entry["level"]),
            school=entry["school"],
            effect=SpellEffect(entry["effect"]),
            targeting=targeting,
            range_ft=int(entry["range_ft"]),
            description=entry.get("description", ""),
            dice=entry.get("dice"),
            damage_type=DamageType(dmg) if dmg is not None else None,
            save_ability=Ability(save) if save is not None else None,
            save_for_half=bool(entry.get("save_for_half", True)),
            concentration=bool(entry.get("concentration", False)),
            heal_dice=entry.get("heal_dice"),
            buffs=buffs,
            condition=ConditionId(entry["condition"]) if entry.get("condition") else None,
            hp_pool_dice=entry.get("hp_pool_dice"),
            condition_ends_on_damage=bool(entry.get("condition_ends_on_damage", False)),
            condition_repeat_save=bool(entry.get("condition_repeat_save", False)),
        )

    def list_ids(self) -> tuple[SpellId, ...]:
        return tuple(sorted(self._by_id.keys()))

    def load(self, spell_id: SpellId) -> Spell:
        if spell_id not in self._by_id:
            raise KeyError(f"unknown spell: {spell_id!r}")
        return self._by_id[spell_id]

    def contains(self, spell_id: SpellId) -> bool:
        return spell_id in self._by_id


__all__ = ["YamlSpellRepository"]

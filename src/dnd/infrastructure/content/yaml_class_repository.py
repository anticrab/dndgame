"""YamlClassRepository — таблицы классов из одного YAML (этап R1).

Формат — список классов (см. data/content/classes.yaml). Поля совпадают с
ClassProgression; ``levels`` — мапа уровень → {proficiency_bonus, features,
spell_slots}.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dnd.domain.values.ability import Ability
from dnd.domain.values.class_progression import ClassLevel, ClassProgression
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.skill import Skill


class YamlClassRepository:
    def __init__(self, classes_file: Path) -> None:
        self._file = classes_file
        self._by_id: dict[str, ClassProgression] = {}
        if classes_file.exists():
            self._reload()

    def _reload(self) -> None:
        raw = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        if raw is None:
            return
        if not isinstance(raw, list):
            raise ValueError(f"classes file {self._file} must contain a list")
        self._by_id = {}
        for entry in raw:
            cp = self._parse(entry)
            if cp.id in self._by_id:
                raise ValueError(f"duplicate class id {cp.id!r}")
            self._by_id[cp.id] = cp

    def _parse(self, entry: dict[str, Any]) -> ClassProgression:
        levels: dict[int, ClassLevel] = {}
        for lvl_raw, data in entry["levels"].items():
            slots = data.get("spell_slots")
            levels[int(lvl_raw)] = ClassLevel(
                proficiency_bonus=int(data["proficiency_bonus"]),
                features=tuple(FeatureId(f) for f in data.get("features", [])),
                spell_slots=({int(k): int(v) for k, v in slots.items()} if slots else None),
            )
        return ClassProgression(
            id=entry["id"],
            name=entry["name"],
            hit_die=entry["hit_die"],
            levels=levels,
            saving_throw_proficiencies=frozenset(
                Ability(code) for code in entry.get("saving_throw_proficiencies", [])
            ),
            skill_proficiencies=frozenset(
                Skill(code) for code in entry.get("skill_proficiencies", [])
            ),
        )

    def load(self, class_id: str) -> ClassProgression:
        if class_id not in self._by_id:
            raise KeyError(f"unknown class: {class_id!r}")
        return self._by_id[class_id]

    def contains(self, class_id: str) -> bool:
        return class_id in self._by_id

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id.keys()))


__all__ = ["YamlClassRepository"]

"""YamlMapRepository — карты в data/content/maps/{id}.yaml.

Реализация MapRepository Port. Карты сериализуются через pydantic
`MapDocument.model_dump(mode="json")` и записываются в `yaml.safe_dump`.
При `__init__` создаёт каталог если его нет (для удобства использования
в тестах с tmp_path и в CLI `dnd map new`).
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from dnd.application.dto.map_dto import MapDocument


class YamlMapRepository:
    def __init__(self, maps_dir: Path) -> None:
        self._dir = maps_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self._dir.glob("*.yaml")))

    def load(self, id_: str) -> MapDocument:
        path = self._dir / f"{id_}.yaml"
        if not path.exists():
            raise KeyError(f"unknown map: {id_!r}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return MapDocument.model_validate(raw)

    def save(self, doc: MapDocument) -> None:
        path = self._dir / f"{doc.id}.yaml"
        path.write_text(
            yaml.safe_dump(
                doc.model_dump(mode="json"),
                sort_keys=False,
                allow_unicode=True,
                width=120,
            ),
            encoding="utf-8",
        )

    def delete(self, id_: str) -> None:
        path = self._dir / f"{id_}.yaml"
        if path.exists():
            path.unlink()


__all__ = ["YamlMapRepository"]

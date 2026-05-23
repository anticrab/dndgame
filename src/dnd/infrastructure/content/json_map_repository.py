"""JsonMapRepository — карты в data/content/maps/{id}.json.

Реализация MapRepository Port через JSON. Используется для CLI
import/export + скриптовая интеграция (JSON = канонический interchange).
"""
from __future__ import annotations

import json
from pathlib import Path

from dnd.application.dto.map_dto import MapDocument


class JsonMapRepository:
    def __init__(self, maps_dir: Path) -> None:
        self._dir = maps_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self._dir.glob("*.json")))

    def load(self, id_: str) -> MapDocument:
        path = self._dir / f"{id_}.json"
        if not path.exists():
            raise KeyError(f"unknown map: {id_!r}")
        return MapDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, doc: MapDocument) -> None:
        path = self._dir / f"{doc.id}.json"
        path.write_text(
            json.dumps(doc.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, id_: str) -> None:
        path = self._dir / f"{id_}.json"
        if path.exists():
            path.unlink()


__all__ = ["JsonMapRepository"]

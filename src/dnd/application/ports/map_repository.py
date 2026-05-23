"""Port: load/save/list карт.

Реализации: YamlMapRepository (default), JsonMapRepository (для import/
export). Будущие: SqliteMapRepository, RemoteMapRepository.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from dnd.application.dto.map_dto import MapDocument


@runtime_checkable
class MapRepository(Protocol):
    def list_ids(self) -> tuple[str, ...]: ...
    def load(self, id_: str) -> MapDocument: ...
    def save(self, doc: MapDocument) -> None: ...
    def delete(self, id_: str) -> None: ...


__all__ = ["MapRepository"]

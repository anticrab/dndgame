"""DTO для сериализации карт в YAML/JSON.

Этот формат — канонический interchange между MapRepository
реализациями (YAML / JSON / SQLite). Содержит ID-references на
sprite_id и object_id, не сами объекты.

Содержит метаданные карты + список tiles (только не-default; default
floor подразумевается для пустых клеток) + список объектов.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MapTileDoc(BaseModel):
    """Одна клетка: координаты + base terrain_id + features ids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    base: str               # terrain_id (см. SpriteRegistry)
    features: tuple[str, ...] = ()


class MapObjectDoc(BaseModel):
    """Interactable объект на карте."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str              # "door" / "chest" / "barrel" / "window"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    state: dict[str, Any] = Field(default_factory=dict)


class MapDocument(BaseModel):
    """Полная карта — header + tiles + objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    tiles: tuple[MapTileDoc, ...] = ()
    objects: tuple[MapObjectDoc, ...] = ()

    @model_validator(mode="after")
    def _validate_bounds(self) -> MapDocument:
        for t in self.tiles:
            if t.x >= self.width or t.y >= self.height:
                raise ValueError(
                    f"tile ({t.x},{t.y}) out of bounds {self.width}x{self.height}"
                )
        for o in self.objects:
            if o.x >= self.width or o.y >= self.height:
                raise ValueError(
                    f"object {o.id} pos ({o.x},{o.y}) out of bounds"
                )
        return self


__all__ = ["MapDocument", "MapObjectDoc", "MapTileDoc"]

"""Метаданные спрайтов: TerrainBase (пол), FeatureKind (наклейки).

Чистые value-объекты — pydantic frozen-модели. НЕ содержат render-кода;
рендером занимается UI-слой, который берёт ``glyph_5x3`` / ``glyph_1x1``
и применяет ``color_token`` через CSS.

Sprite = content, не код: эти классы — типизированные представления
данных из ``data/content/sprites/**/*.yaml``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dnd.domain.values.direction import Direction
from dnd.domain.values.terrain import CoverLevel

# Тип поля — открытый кортеж строк. Точная форма (3×5) проверяется
# нашим валидатором, чтобы выдавать понятные сообщения с «3 rows» /
# «5 chars», а не сырое pydantic «tuple length mismatch».
_Glyph5x3 = tuple[str, ...]


def _validate_glyph_5x3(g: tuple[str, ...]) -> tuple[str, str, str]:
    if len(g) != 3:
        raise ValueError(f"glyph_5x3 must be 3 rows, got {len(g)}")
    for i, row in enumerate(g):
        if len(row) != 5:
            raise ValueError(f"glyph_5x3 row {i} must be 5 chars, got {len(row)} ({row!r})")
    return (g[0], g[1], g[2])


class TerrainBase(BaseModel):
    """Базовый пол клетки — то, что под ногами.

    Сам по себе всегда ``passable`` (стены — это features, не base).
    ``difficult=True`` соответствует PHB-2024 «труднопроходимая местность»
    (×2 стоимость).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    passable: bool
    difficult: bool
    glyph_5x3: _Glyph5x3
    glyph_1x1: str = Field(min_length=1, max_length=1)
    color_token: str

    @model_validator(mode="after")
    def _check_glyph(self) -> TerrainBase:
        object.__setattr__(self, "glyph_5x3", _validate_glyph_5x3(self.glyph_5x3))
        return self


class FeatureKind(BaseModel):
    """Тип фичи — стена, колонна, мебель.

    Применяется поверх ``TerrainBase``. Несколько features на одной
    клетке — допустимо (стол + бочка стоят рядом и т.п.); их семантика
    суммируется по правилу «самое строгое побеждает».
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    blocks_los: bool
    cover: CoverLevel
    blocks_passage_dirs: frozenset[Direction]
    passable_cost_ft: int = Field(ge=0)  # 0 = непроходимо, 5 = норм, 10 = difficult
    glyph_5x3: _Glyph5x3
    glyph_1x1: str = Field(min_length=1, max_length=1)
    color_token: str

    @model_validator(mode="after")
    def _check_glyph(self) -> FeatureKind:
        object.__setattr__(self, "glyph_5x3", _validate_glyph_5x3(self.glyph_5x3))
        return self


__all__ = ["FeatureKind", "TerrainBase"]

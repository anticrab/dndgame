"""Editor screen smoke + paint roundtrip.

Покрытие:

* Editor поднимается под Pilot, paint+save сохраняет tile в YAML →
  после reload в репозитории видна непустая ``tiles``.
* Клавиша ``q`` корректно выходит из приложения.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from dnd.application.dto.map_dto import MapDocument
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry
from dnd.interfaces.tui.app import TuiApp

SPRITES = Path(__file__).resolve().parents[3] / "data" / "content" / "sprites"


def test_editor_screen_loads_and_paints(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    doc = MapDocument(id="t", name="T", width=4, height=4, tiles=(), objects=())
    repo.save(doc)
    sprites = YamlSpriteRegistry(SPRITES)

    app = TuiApp(editor=(doc, repo, sprites))

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            # Двигаем курсор и paint
            await pilot.press("right")
            await pilot.press("down")
            await pilot.press("enter")  # paint default sprite (первый в TERRAIN list)
            await pilot.press("s")  # save
            await pilot.pause(0.1)

    asyncio.run(_go())

    # Проверим что save сработал — после reload tiles должны быть != ()
    reloaded = YamlMapRepository(tmp_path).load("t")
    assert len(reloaded.tiles) >= 1


def test_editor_screen_quit(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    doc = MapDocument(id="q", name="Q", width=3, height=3, tiles=(), objects=())
    repo.save(doc)
    sprites = YamlSpriteRegistry(SPRITES)

    app = TuiApp(editor=(doc, repo, sprites))

    async def _go() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)

    asyncio.run(_go())

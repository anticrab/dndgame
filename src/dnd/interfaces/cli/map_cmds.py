"""Семья команд ``dnd map ...`` — управление картами из shell.

Все команды работают через ``MapRepository`` Port; default-реализация —
``YamlMapRepository`` поверх ``data/content/maps/``. JSON-формат
доступен для скриптовой интеграции.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

if TYPE_CHECKING:
    from dnd.application.dto.map_dto import MapDocument


map_app = typer.Typer(name="map", help="Manage and inspect maps.")
_DEFAULT_MAPS = Path("data/content/maps")
_DEFAULT_SPRITES = Path("data/content/sprites")


def _repo(maps_dir: Path) -> YamlMapRepository:
    return YamlMapRepository(maps_dir)


@map_app.command("list")
def list_(
    format_: str = typer.Option("table", "--format"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Список карт + метаданные."""
    repo = _repo(maps_dir)
    items: list[dict[str, object]] = []
    for id_ in repo.list_ids():
        doc = repo.load(id_)
        items.append({
            "id": doc.id, "name": doc.name,
            "size": f"{doc.width}x{doc.height}",
            "tiles": len(doc.tiles), "objects": len(doc.objects),
        })
    if format_ == "json":
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    console = Console()
    for it in items:
        console.print(
            f"[bold]{it['id']:24}[/] {it['size']:8} "
            f"tiles={it['tiles']:4} objects={it['objects']:3} {it['name']}"
        )


@map_app.command("show")
def show(
    id_: str = typer.Argument(..., metavar="ID"),
    format_: str = typer.Option("ascii", "--format"),
    zoom: str = typer.Option("small", "--zoom", help="small | medium"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
    sprites_dir: Path = typer.Option(_DEFAULT_SPRITES, "--sprites-dir"),
) -> None:
    """Показать карту в терминале (ascii) или JSON."""
    repo = _repo(maps_dir)
    try:
        doc = repo.load(id_)
    except KeyError:
        typer.echo(f"map not found: {id_!r}", err=True)
        raise typer.Exit(code=2) from None

    if format_ == "json":
        typer.echo(json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    sprites = YamlSpriteRegistry(sprites_dir)
    console = Console()
    console.print(f"[bold]{doc.id}[/] — {doc.name} ({doc.width}x{doc.height})")
    if zoom == "small":
        _render_small(doc, sprites, console)
    else:
        _render_medium(doc, sprites, console)


def _render_small(doc: MapDocument, sprites: YamlSpriteRegistry, console: Console) -> None:
    grid = [["."] * doc.width for _ in range(doc.height)]
    for t in doc.tiles:
        glyph = _has_terrain_glyph(sprites, t.base) or "?"
        for fid in t.features:
            with contextlib.suppress(KeyError):
                glyph = sprites.get_feature(fid).glyph_1x1
        grid[t.y][t.x] = glyph
    for o in doc.objects:
        grid[o.y][o.x] = o.kind[0].upper()  # D/C/B/W placeholder
    for row in grid:
        console.print("".join(row))


def _render_medium(doc: MapDocument, sprites: YamlSpriteRegistry, console: Console) -> None:
    """5×3 без рамок: каждая клетка — 3 строки по 5 ячеек."""
    for y in range(doc.height):
        cell_rows = ["", "", ""]
        for x in range(doc.width):
            base_id, feature_ids = _tile_at(doc, x, y)
            glyph = _compose_5x3(sprites, base_id, feature_ids)
            for i in range(3):
                cell_rows[i] += glyph[i]
        for r in cell_rows:
            console.print(r)


def _tile_at(doc: MapDocument, x: int, y: int) -> tuple[str, tuple[str, ...]]:
    for t in doc.tiles:
        if t.x == x and t.y == y:
            return t.base, t.features
    return "floor", ()


def _has_terrain_glyph(sprites: YamlSpriteRegistry, id_: str) -> str | None:
    try:
        return sprites.get_terrain(id_).glyph_1x1
    except KeyError:
        return None


def _compose_5x3(
    sprites: YamlSpriteRegistry, base_id: str, feature_ids: tuple[str, ...]
) -> tuple[str, str, str]:
    try:
        base = sprites.get_terrain(base_id).glyph_5x3
    except KeyError:
        base = ("     ", "  ?  ", "     ")
    rows = [list(r) for r in base]
    for fid in feature_ids:
        try:
            fg = sprites.get_feature(fid).glyph_5x3
        except KeyError:
            continue
        for i in range(3):
            for j in range(5):
                if fg[i][j] != " ":
                    rows[i][j] = fg[i][j]
    return ("".join(rows[0]), "".join(rows[1]), "".join(rows[2]))


@map_app.command("validate")
def validate(
    id_: str = typer.Argument(...),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Проверить YAML-валидность + sanity (через pydantic schema)."""
    repo = _repo(maps_dir)
    try:
        doc = repo.load(id_)
        typer.echo(f"OK: {doc.id} {doc.width}x{doc.height} "
                   f"tiles={len(doc.tiles)} objects={len(doc.objects)}")
    except (KeyError, ValueError) as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=2) from None

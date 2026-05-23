"""Семья команд ``dnd map ...`` — управление картами из shell.

Все команды работают через ``MapRepository`` Port; default-реализация —
``YamlMapRepository`` поверх ``data/content/maps/``. JSON-формат
доступен для скриптовой интеграции.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

import typer
from rich.console import Console

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

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


@map_app.command("new")
def new(
    id_: str = typer.Argument(...),
    size: str = typer.Option(..., "--size", help="WxH"),
    name: str = typer.Option("", "--name"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Создать новую пустую карту."""
    m = re.fullmatch(r"(\d+)x(\d+)", size)
    if not m:
        typer.echo(f"bad size: {size!r} (expected WxH)", err=True)
        raise typer.Exit(code=2)
    w, h = int(m.group(1)), int(m.group(2))
    doc = MapDocument(id=id_, name=name or id_, width=w, height=h, tiles=(), objects=())
    _repo(maps_dir).save(doc)
    typer.echo(f"created: {id_} {w}x{h}")


@map_app.command("paint")
def paint(
    id_: str = typer.Argument(...),
    at: str = typer.Option(..., "--at", help="X,Y"),
    base: str | None = typer.Option(None, "--base"),
    feature: str | None = typer.Option(None, "--feature"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Точечно изменить tile карты — поставить base и/или добавить feature."""
    m = re.fullmatch(r"(\d+),(\d+)", at)
    if not m:
        typer.echo(f"bad at: {at!r} (expected X,Y)", err=True)
        raise typer.Exit(code=2)
    x, y = int(m.group(1)), int(m.group(2))
    repo = _repo(maps_dir)
    doc = repo.load(id_)
    new_tiles = list(doc.tiles)
    idx = next((i for i, t in enumerate(new_tiles) if t.x == x and t.y == y), None)
    if idx is None:
        current = MapTileDoc(x=x, y=y, base=base or "floor", features=())
    else:
        current = new_tiles[idx]
    new_base = base or current.base
    if feature and feature not in current.features:
        new_features = (*current.features, feature)
    else:
        new_features = current.features
    updated = MapTileDoc(x=x, y=y, base=new_base, features=new_features)
    if idx is None:
        new_tiles.append(updated)
    else:
        new_tiles[idx] = updated
    repo.save(MapDocument(
        id=doc.id, name=doc.name, width=doc.width, height=doc.height,
        tiles=tuple(new_tiles), objects=doc.objects,
    ))
    typer.echo(f"painted {at}: base={new_base} features={list(new_features)}")


@map_app.command("export")
def export(
    id_: str = typer.Argument(...),
    format_: str = typer.Option("yaml", "--format", help="yaml | json"),
    output: Path = typer.Option(None, "--output", help="File to write; stdout if absent"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Экспорт карты в YAML или JSON (stdout или файл)."""
    doc = _repo(maps_dir).load(id_)
    if format_ == "json":
        body = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2)
    else:
        import yaml  # type: ignore[import-untyped]
        body = yaml.safe_dump(
            doc.model_dump(mode="json"), sort_keys=False, allow_unicode=True
        )
    if output:
        output.write_text(body, encoding="utf-8")
        typer.echo(f"exported to {output}")
    else:
        typer.echo(body)


@map_app.command("import")
def import_(
    file: Path = typer.Argument(...),
    as_: str = typer.Option(None, "--as", help="override id"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    """Импорт карты из YAML/JSON файла (формат по расширению)."""
    text = file.read_text(encoding="utf-8")
    if file.suffix == ".json":
        data = json.loads(text)
    else:
        import yaml
        data = yaml.safe_load(text)
    if as_:
        data["id"] = as_
    doc = MapDocument.model_validate(data)
    _repo(maps_dir).save(doc)
    typer.echo(f"imported as {doc.id}")

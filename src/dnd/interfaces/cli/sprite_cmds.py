"""Семья команд ``dnd sprite ...`` — управление sprite-content из shell.

Все команды работают через ``SpriteRegistry`` Port; default-реализация —
``YamlSpriteRegistry`` поверх ``data/content/sprites/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

sprite_app = typer.Typer(name="sprite", help="Manage sprite content.")
_DEFAULT_SPRITES = Path("data/content/sprites")


def _registry(content_dir: Path) -> YamlSpriteRegistry:
    return YamlSpriteRegistry(content_dir)


@sprite_app.command("list")
def list_(
    category: str = typer.Option(
        None, "--category", help="terrain | feature | object | creature"
    ),
    format_: str = typer.Option("table", "--format", help="table | json"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Список загруженных sprites."""
    reg = _registry(content_dir)
    categories = (
        [SpriteCategory(category)] if category
        else list(SpriteCategory)
    )
    items: list[dict[str, str]] = []
    for cat in categories:
        for sp in reg.list_by_category(cat):
            items.append({
                "id": sp.id, "name": sp.name, "category": cat.value,
            })

    if format_ == "json":
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    console = Console()
    for it in items:
        console.print(f"[bold]{it['id']:24}[/] {it['category']:10} {it['name']}")


@sprite_app.command("show")
def show(
    id_: str = typer.Argument(..., metavar="ID"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Превью sprite: glyph_5x3 + флаги."""
    reg = _registry(content_dir)
    sp = None
    for cat in SpriteCategory:
        for cand in reg.list_by_category(cat):
            if cand.id == id_:
                sp = cand
                break
        if sp is not None:
            break
    if sp is None:
        typer.echo(f"sprite not found: {id_!r}", err=True)
        raise typer.Exit(code=2)
    console = Console()
    console.print(f"[bold]{sp.id}[/] — {sp.name}")
    for row in sp.glyph_5x3:
        console.print(row)
    console.print(f"glyph_1x1: {sp.glyph_1x1}")
    console.print(f"color: {sp.color_token}")


@sprite_app.command("validate")
def validate(
    id_: str = typer.Argument(..., metavar="ID"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Проверка существования sprite + базовая схема."""
    reg = _registry(content_dir)
    try:
        for cat in SpriteCategory:
            for cand in reg.list_by_category(cat):
                if cand.id == id_:
                    typer.echo(f"OK: {id_} ({cat.value})")
                    return
        raise KeyError(id_)
    except KeyError:
        typer.echo(f"sprite not found: {id_!r}", err=True)
        raise typer.Exit(code=2) from None

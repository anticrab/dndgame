"""Точка входа CLI. Используется console_script `dnd`.

Команды-заглушки выводят сообщение «не реализовано» — реализуются по мере
готовности соответствующих сервисов (см. ``docs/ARCHITECTURE.md``).
"""

from __future__ import annotations

from enum import StrEnum

import typer

from dnd import __version__
from dnd.interfaces.cli.map_cmds import map_app
from dnd.interfaces.cli.sprite_cmds import sprite_app

app = typer.Typer(
    name="dnd",
    help="Console D&D 5e — educational project.",
    no_args_is_help=False,  # обрабатывается в callback ниже
    add_completion=False,
)
app.add_typer(sprite_app)
app.add_typer(map_app)


class DbAction(StrEnum):
    """Подкоманды управления БД."""

    INIT = "init"
    SEED = "seed"
    RESET = "reset"


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit.", is_eager=True),
) -> None:
    """Корневой callback: обрабатывает --version и показывает help без аргументов."""
    if version:
        typer.echo(f"dnd {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command("play")
def play(
    scenario_id: str = typer.Argument(
        "mvp_skirmish",
        help="Scenario id from data/content/scenarios.yaml.",
    ),
    content_dir: str = typer.Option(
        "data/content",
        "--content-dir",
        help="Path to YAML content directory.",
    ),
    tui: bool = typer.Option(
        False,
        "--tui",
        help="Run in TUI mode (Textual). Without — questionary-based CLI.",
    ),
    theme: str = typer.Option(
        "color",
        "--theme",
        help="TUI theme: color (default) or monochrome.",
    ),
) -> None:
    """Запустить сценарий боя в интерактивном режиме (CLI или TUI)."""
    from pathlib import Path

    from rich.console import Console

    from dnd.application.engine.scenario_builder import (
        build_encounter_from_scenario,
    )
    from dnd.composition import build_default_runtime_services
    from dnd.infrastructure.content.yaml_item_repository import (
        YamlItemRepository,
    )
    from dnd.infrastructure.content.yaml_map_repository import (
        YamlMapRepository,
    )
    from dnd.infrastructure.content.yaml_repository import (
        YamlContentRepository,
    )
    from dnd.infrastructure.content.yaml_spell_repository import (
        YamlSpellRepository,
    )
    from dnd.infrastructure.content.yaml_sprite_registry import (
        YamlSpriteRegistry,
    )

    repo = YamlContentRepository(Path(content_dir))
    try:
        scenario = repo.scenario_by_id(scenario_id)
    except KeyError:
        typer.echo(f"Scenario not found: {scenario_id}", err=True)
        raise typer.Exit(code=2) from None

    # K9 S1-1: для scenarios с map_id нужны MapRepository и SpriteRegistry,
    # чтобы загрузить MapDocument и построить Tile-aware Battlefield.
    # Для legacy inline-map путь не задействует их (None допустимо).
    services = build_default_runtime_services()
    map_repo = YamlMapRepository(Path(content_dir) / "maps")
    sprite_reg = YamlSpriteRegistry(Path(content_dir) / "sprites")
    # ItemRepository — для Pickup (CLI/TUI). Файл может отсутствовать —
    # тогда инвентарь-меню работает с голыми item_id. Прокидывается
    # и в provider (для красивых имён), и в GameRunner (для PickupAction).
    item_repo = YamlItemRepository(Path(content_dir) / "items.yaml")
    # SpellRepository — для заклинаний (P1): action-bar в TUI + CastSpellAction.
    spell_repo = YamlSpellRepository(Path(content_dir) / "spells.yaml")
    enc = build_encounter_from_scenario(
        scenario,
        content=repo,
        services=services,
        map_repository=map_repo,
        sprite_registry=sprite_reg,
    )

    if tui:
        # Импорт здесь — чтобы --no-tui не тащил textual.
        from dnd.interfaces.tui import run_tui

        if theme not in ("color", "monochrome"):
            typer.echo(
                f"Unknown theme {theme!r}; expected color|monochrome",
                err=True,
            )
            raise typer.Exit(code=2)
        run_tui(encounter=enc, theme=theme, item_repository=item_repo, spell_repository=spell_repo)  # type: ignore[arg-type]  # theme: str vs ThemeName Literal
        return

    from dnd.application.engine.game_runner import GameRunner
    from dnd.interfaces.cli.console_provider import ConsoleIntentProvider
    from dnd.interfaces.cli.event_printer import EventPrinter

    console = Console()
    console.print(f"[bold]{scenario.name}[/]\n")
    EventPrinter(console).subscribe(enc.event_bus)
    runner = GameRunner(
        intent_provider=ConsoleIntentProvider(item_repository=item_repo),
        item_repository=item_repo,
        spell_repository=spell_repo,
    )
    runner.run(enc)


@app.command("character")
def character() -> None:
    """Create or show a character."""
    typer.echo("[character] not implemented yet — needs CharacterCreationService.")


@app.command("db")
def db(action: DbAction = typer.Argument(..., help="init | seed | reset")) -> None:
    """Database management."""
    typer.echo(f"[db {action.value}] not implemented yet — needs infrastructure/db.")


@app.command("content")
def content() -> None:
    """List or validate loaded content packs."""
    typer.echo("[content] not implemented yet — needs ContentService.")


@app.command("settings")
def settings() -> None:
    """Show or edit settings (language, theme, paths)."""
    typer.echo("[settings] not implemented yet — needs ConfigService.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

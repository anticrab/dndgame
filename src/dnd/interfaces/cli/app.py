"""Точка входа CLI. Используется console_script `dnd`.

Команды-заглушки выводят сообщение «не реализовано» — реализуются по мере
готовности соответствующих сервисов (см. ``docs/ARCHITECTURE.md``).
"""

from __future__ import annotations

from enum import StrEnum

import typer

from dnd import __version__

app = typer.Typer(
    name="dnd",
    help="Console D&D 5e — educational project.",
    no_args_is_help=False,  # обрабатывается в callback ниже
    add_completion=False,
)


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
) -> None:
    """Запустить сценарий боя в интерактивном CLI-режиме."""
    from pathlib import Path

    from rich.console import Console

    from dnd.application.engine.game_runner import GameRunner
    from dnd.application.engine.scenario_builder import (
        build_encounter_from_scenario,
    )
    from dnd.composition import build_default_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.infrastructure.content.yaml_repository import (
        YamlContentRepository,
    )
    from dnd.interfaces.cli.console_provider import ConsoleIntentProvider
    from dnd.interfaces.cli.event_printer import EventPrinter

    repo = YamlContentRepository(Path(content_dir))
    try:
        scenario = repo.scenario_by_id(scenario_id)
    except KeyError:
        typer.echo(f"Scenario not found: {scenario_id}", err=True)
        raise typer.Exit(code=2) from None

    console = Console()
    console.print(f"[bold]{scenario.name}[/]\n")

    deps = build_default_dependencies(battlefield=Battlefield(1, 1))
    enc = build_encounter_from_scenario(scenario, content=repo, deps=deps)
    printer = EventPrinter(console)
    printer.subscribe(enc.deps.event_bus)

    runner = GameRunner(intent_provider=ConsoleIntentProvider())
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

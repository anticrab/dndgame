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
def play() -> None:
    """Start a new game or continue."""
    typer.echo("[play] not implemented yet — needs GameEngine + UI.")


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

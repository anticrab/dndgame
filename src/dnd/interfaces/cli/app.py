"""Точка входа CLI. Используется console_script `dnd`.

Команды-заглушки выводят сообщение «не реализовано» — реализуются по мере
готовности соответствующих сервисов (см. ``docs/ARCHITECTURE.md``).
"""

from __future__ import annotations

import typer

from dnd import __version__

app = typer.Typer(
    name="dnd",
    help="Консольная D&D 5e — учебный проект.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", help="Показать версию и выйти.", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(f"dnd {__version__}")
        raise typer.Exit()


@app.command("play")
def play() -> None:
    """Начать новую игру или продолжить."""
    typer.echo("[play] ещё не реализовано — будет после готовности GameSession.")


@app.command("character")
def character() -> None:
    """Создать или показать персонажа."""
    typer.echo("[character] ещё не реализовано — будет после CharacterCreationService.")


@app.command("db")
def db(action: str = typer.Argument(..., help="init | seed | reset")) -> None:
    """Управление базой данных."""
    typer.echo(f"[db {action}] ещё не реализовано — будет после слоя infrastructure/db.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

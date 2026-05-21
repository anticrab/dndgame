"""Тесты CLI-обвязки (interfaces/cli/app.py).

Проверяем, что команды доступны, --version работает, заглушки выводят
ожидаемый префикс. Реальная функциональность пока заглушки —
полноценные тесты появятся вместе с GameEngine.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from dnd import __version__
from dnd.interfaces.cli.app import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("play", "character", "db", "content", "settings"):
        assert cmd in result.stdout


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


@pytest.mark.parametrize(
    "cmd,marker",
    [
        ("play", "[play]"),
        ("character", "[character]"),
        ("content", "[content]"),
        ("settings", "[settings]"),
    ],
)
def test_stub_commands_print_marker(cmd: str, marker: str) -> None:
    result = runner.invoke(app, [cmd])
    assert result.exit_code == 0
    assert marker in result.stdout
    assert "not implemented" in result.stdout


@pytest.mark.parametrize("action", ["init", "seed", "reset"])
def test_db_accepts_valid_actions(action: str) -> None:
    result = runner.invoke(app, ["db", action])
    assert result.exit_code == 0
    assert f"[db {action}]" in result.stdout


def test_db_rejects_invalid_action() -> None:
    result = runner.invoke(app, ["db", "hello"])
    assert result.exit_code != 0
    # Typer выводит сообщение об ошибке вроде "Invalid value for 'ACTION'"

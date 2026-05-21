"""Тесты композиционного корня (interfaces/cli/composition.py).

Сейчас composition root содержит только заглушки — тесты проверяют,
что модуль импортируется, классы доступны, сигнатуры стабильны.
По мере появления реальных портов и GameEngine эти тесты будут расти
вместе с реализацией.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.interfaces.cli.composition import (
    AppPaths,
    build_engine,
    register_default_plugins,
)


def test_app_paths_under_workdir() -> None:
    paths = AppPaths.under(Path("/tmp/mywork"))
    assert paths.db == Path("/tmp/mywork/dnd.sqlite")
    assert paths.content == Path("/tmp/mywork/content")
    assert paths.config == Path("/tmp/mywork/config.toml")
    assert paths.logs == Path("/tmp/mywork/logs")


def test_app_paths_default_raises_until_implemented() -> None:
    """Будет заменено реальной реализацией поверх platformdirs."""
    with pytest.raises(NotImplementedError):
        AppPaths.default()


def test_build_engine_raises_until_engine_exists() -> None:
    """Контракт сигнатуры зафиксирован; реализация — вместе с GameEngine."""
    with pytest.raises(NotImplementedError):
        build_engine()


def test_register_default_plugins_is_noop_for_now() -> None:
    """Возвращает None и не падает — заготовка для будущих регистраций."""
    assert register_default_plugins() is None

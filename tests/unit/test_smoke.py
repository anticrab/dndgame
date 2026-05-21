"""Дымовой тест: пакет импортируется, версия читается."""

from __future__ import annotations


def test_package_imports() -> None:
    import dnd

    assert dnd.__version__


def test_cli_app_constructed() -> None:
    from dnd.interfaces.cli.app import app

    assert app is not None

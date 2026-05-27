"""Архитектурный guard: domain не зависит от внешних слоёв.

Гексагональная архитектура (docs/ARCHITECTURE.md): domain — ядро правил, не
знает про application / infrastructure / interfaces. Этот тест статически
сканирует исходники domain на запрещённые импорты, чтобы нарушение слоя ловилось
сразу (а не всплывало рефактором месяцы спустя).

Закрепляет рефактор: id-типы, модификаторы и RollPurpose переехали в domain,
поэтому `from dnd.application…` в domain быть НЕ должно.
"""

from __future__ import annotations

import ast
from pathlib import Path

_DOMAIN = Path(__file__).resolve().parents[2] / "src" / "dnd" / "domain"
_FORBIDDEN_PREFIXES = ("dnd.application", "dnd.infrastructure", "dnd.interfaces")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def test_domain_does_not_import_outer_layers() -> None:
    offenders: list[str] = []
    for py in _DOMAIN.rglob("*.py"):
        for mod in _imported_modules(py.read_text(encoding="utf-8")):
            if any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES):
                rel = py.relative_to(_DOMAIN.parents[2])
                offenders.append(f"{rel}: import {mod}")
    assert not offenders, "domain импортирует внешние слои:\n" + "\n".join(offenders)

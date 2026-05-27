"""Порт каталога классов (этап R1)."""

from __future__ import annotations

from typing import Protocol

from dnd.domain.values.class_progression import ClassProgression


class ClassRepository(Protocol):
    def load(self, class_id: str) -> ClassProgression: ...
    def contains(self, class_id: str) -> bool: ...
    def list_ids(self) -> tuple[str, ...]: ...


__all__ = ["ClassRepository"]

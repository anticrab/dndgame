"""Общие фикстуры pytest."""

from __future__ import annotations

import sys
from pathlib import Path

# Гарантируем, что src на sys.path в дев-режиме (на случай тестов без editable install).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

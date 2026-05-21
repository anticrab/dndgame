"""Общие фикстуры и настройки pytest."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Гарантируем, что src на sys.path в дев-режиме (на случай тестов без editable install).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# -- hypothesis: профили ----------------------------------------------------
#
# Профиль выбирается переменной окружения HYPOTHESIS_PROFILE:
#   dev   — 50 примеров, быстрый цикл (по умолчанию локально).
#   ci    — 300 примеров, дольше, но шире покрытие. Используется в CI.
#   debug — 1000 примеров + verbose, для отладки конкретного property-теста.
#
# Маркер @pytest.mark.property можно использовать на тестах с hypothesis
# (см. pyproject.toml [tool.pytest.ini_options].markers).

try:  # pragma: no cover — hypothesis может отсутствовать в минимальной среде
    from hypothesis import HealthCheck, Phase, Verbosity, settings

    settings.register_profile(
        "dev",
        max_examples=50,
        deadline=1500,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.register_profile(
        "ci",
        max_examples=300,
        deadline=2500,
        derandomize=True,
        phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink),
    )
    settings.register_profile(
        "debug",
        max_examples=1000,
        verbosity=Verbosity.verbose,
        deadline=None,
    )
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
except ImportError:  # pragma: no cover
    pass

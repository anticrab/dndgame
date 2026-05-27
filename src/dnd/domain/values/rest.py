"""Отдых: типы отдыха и политика восстановления ресурсов.

«Словарь» отдыха, на который опираются классовые фичи (поле ``recharge_on``)
и ``RestService``. В R1 отдых триггерится только «между боями» (SHORT на старте
encounter), но абстракция полная — будущие внебоевые short/long rest подключатся
к той же ``RestService`` без переделок.
"""

from __future__ import annotations

from enum import StrEnum


class RestKind(StrEnum):
    SHORT = "short"
    LONG = "long"


class RechargeOn(StrEnum):
    TURN = "turn"
    ENCOUNTER = "encounter"
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"


# Ранг «силы»: чем больше, тем больше восстанавливает.
_RANK: dict[RechargeOn, int] = {
    RechargeOn.TURN: 0,
    RechargeOn.ENCOUNTER: 1,
    RechargeOn.SHORT_REST: 2,
    RechargeOn.LONG_REST: 3,
}
_REST_RANK: dict[RestKind, int] = {
    RestKind.SHORT: _RANK[RechargeOn.SHORT_REST],
    RestKind.LONG: _RANK[RechargeOn.LONG_REST],
}


def recharge_covers(kind: RestKind, recharge: RechargeOn) -> bool:
    """Восстанавливает ли отдых ``kind`` ресурс с политикой ``recharge``.

    SHORT восстанавливает всё с recharge ≤ short_rest; LONG — всё."""
    return _RANK[recharge] <= _REST_RANK[kind]


__all__ = ["RechargeOn", "RestKind", "recharge_covers"]

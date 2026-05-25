"""R1-1: RestKind / RechargeOn + покрытие отдыхом."""
from __future__ import annotations

from dnd.domain.values.rest import RechargeOn, RestKind, recharge_covers


def test_short_rest_covers_short_and_encounter_and_turn() -> None:
    assert recharge_covers(RestKind.SHORT, RechargeOn.TURN)
    assert recharge_covers(RestKind.SHORT, RechargeOn.ENCOUNTER)
    assert recharge_covers(RestKind.SHORT, RechargeOn.SHORT_REST)
    assert not recharge_covers(RestKind.SHORT, RechargeOn.LONG_REST)


def test_long_rest_covers_everything() -> None:
    for r in RechargeOn:
        assert recharge_covers(RestKind.LONG, r)

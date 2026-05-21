"""Тесты MasterIntent — discriminated union, сериализация, тип-narrowing.

Smoke по решению Q22: проверяем, что pydantic v2 + Annotated +
Field(discriminator) корректно работает в нашей конфигурации и mypy
strict видит сужение типа через `match intent.kind`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from dnd.application.dto.ids import CreatureId, PlayerId, RollId
from dnd.application.dto.master_intent import (
    MasterIntentAdapter,
    NarrateIntent,
    RerollIntent,
    SetHpIntent,
)

# -- helpers ---------------------------------------------------------------

_MASTER = PlayerId("master-1")


def _reroll() -> RerollIntent:
    return RerollIntent(roll_id=RollId(uuid4()), reason="fudge against TPK", issued_by=_MASTER)


def _set_hp() -> SetHpIntent:
    return SetHpIntent(
        creature_id=CreatureId("goblin-1"),
        value=1,
        reason="dramatic last stand",
        issued_by=_MASTER,
    )


def _narrate() -> NarrateIntent:
    return NarrateIntent(
        text="A cold wind sweeps through the cavern...",
        reason="atmosphere",
        issued_by=_MASTER,
    )


# -- creation --------------------------------------------------------------


def test_reroll_intent_construction() -> None:
    intent = _reroll()
    assert intent.kind == "reroll"
    assert intent.reason == "fudge against TPK"


def test_set_hp_intent_construction() -> None:
    intent = _set_hp()
    assert intent.kind == "set_hp"
    assert intent.value == 1


def test_narrate_intent_default_audience_is_all() -> None:
    intent = _narrate()
    assert intent.audience == "all"


def test_narrate_intent_master_only_audience() -> None:
    intent = NarrateIntent(
        text="GM-only hint", reason="hint", issued_by=_MASTER, audience="master_only"
    )
    assert intent.audience == "master_only"


def test_narrate_intent_creature_targeted_audience() -> None:
    """Narrate можно направить конкретному PC (например, видение)."""
    target = CreatureId("aelar")
    intent = NarrateIntent(
        text="You sense an ancient evil...",
        reason="vision",
        issued_by=_MASTER,
        audience=target,
    )
    assert intent.audience == target


# -- validation ------------------------------------------------------------


def test_reason_must_be_non_empty() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        RerollIntent(roll_id=RollId(uuid4()), reason="", issued_by=_MASTER)


def test_set_hp_value_must_be_non_negative() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        SetHpIntent(creature_id=CreatureId("g1"), value=-1, reason="oops", issued_by=_MASTER)


def test_extra_fields_rejected() -> None:
    """`extra="forbid"` защищает от опечаток (например, `kine` вместо `kind`)."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        RerollIntent.model_validate(
            {
                "kind": "reroll",
                "roll_id": uuid4(),
                "reason": "test",
                "issued_by": "master",
                "typo_field": "what",
            }
        )


def test_frozen_immutability() -> None:
    """`model_config frozen=True` — после создания менять нельзя."""
    intent = _reroll()
    with pytest.raises(ValidationError):
        intent.reason = "different"  # type: ignore[misc]


# -- serialization through TypeAdapter -------------------------------------


def test_round_trip_reroll() -> None:
    original = _reroll()
    blob = MasterIntentAdapter.dump_json(original)
    back = MasterIntentAdapter.validate_json(blob)
    assert back == original


def test_round_trip_set_hp() -> None:
    original = _set_hp()
    blob = MasterIntentAdapter.dump_json(original)
    back = MasterIntentAdapter.validate_json(blob)
    assert back == original


def test_round_trip_narrate() -> None:
    original = _narrate()
    blob = MasterIntentAdapter.dump_json(original)
    back = MasterIntentAdapter.validate_json(blob)
    assert back == original


def test_adapter_discriminates_by_kind() -> None:
    """TypeAdapter выбирает правильный класс по полю `kind`."""
    reroll_json = MasterIntentAdapter.dump_json(_reroll())
    set_hp_json = MasterIntentAdapter.dump_json(_set_hp())
    narrate_json = MasterIntentAdapter.dump_json(_narrate())

    assert isinstance(MasterIntentAdapter.validate_json(reroll_json), RerollIntent)
    assert isinstance(MasterIntentAdapter.validate_json(set_hp_json), SetHpIntent)
    assert isinstance(MasterIntentAdapter.validate_json(narrate_json), NarrateIntent)


def test_unknown_kind_rejected() -> None:
    """Неизвестный `kind` приводит к явной ошибке валидации.

    pydantic v2 на discriminated union возвращает `union_tag_invalid`
    с понятным сообщением «Input tag X does not match any of the
    expected tags».
    """
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        MasterIntentAdapter.validate_python(
            {
                "kind": "nuke_planet",
                "reason": "lol",
                "issued_by": "master",
            }
        )


# -- type narrowing via match ----------------------------------------------


def _describe(intent: RerollIntent | SetHpIntent | NarrateIntent) -> str:
    """Демонстрирует, что match по полю kind сужает тип.

    Этот код проверяется и pytest'ом, и mypy strict: если бы у одной
    из веток не было нужного поля, mypy бы упал на стадии typecheck.
    """
    match intent.kind:
        case "reroll":
            # mypy здесь знает, что intent — RerollIntent → есть roll_id
            return f"reroll {intent.roll_id}"
        case "set_hp":
            return f"set_hp {intent.creature_id}={intent.value}"
        case "narrate":
            return f"narrate '{intent.text}' to {intent.audience}"


def test_match_narrowing_works_at_runtime() -> None:
    assert _describe(_reroll()).startswith("reroll ")
    assert _describe(_set_hp()).startswith("set_hp goblin-1=1")
    assert _describe(_narrate()).startswith("narrate")

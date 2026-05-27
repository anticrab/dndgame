"""Protocol-проверка: MapRepository."""

from __future__ import annotations

from dnd.application.ports.map_repository import MapRepository


def test_protocol_runtime_checkable() -> None:
    class _Stub:
        def list_ids(self) -> tuple[str, ...]:
            return ()

        def load(self, id_: str): ...
        def save(self, doc): ...
        def delete(self, id_: str) -> None: ...

    assert isinstance(_Stub(), MapRepository)

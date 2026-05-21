"""``InMemoryEventBus`` — синхронная реализация порта ``EventBus``.

Реализует контракт ``docs/ENGINE.md`` §5.2 (FIFO, отложенные публикации
в хендлерах, изоляция исключений, отложенные изменения подписок).

Ключевая идея — **две очереди**:

* ``_subscribers[Type] → list[EventHandler]`` — кому доставлять;
* ``_pending: deque[EngineEvent]`` — события, ждущие диспатча.

``publish`` ставит событие в ``_pending``. Если уже идёт диспатч —
просто возвращается (текущий цикл подберёт). Если нет — запускается
цикл, пока очередь не опустеет.

Изменения подписок (``subscribe``/``unsubscribe``) во время диспатча
сохраняются в ``_pending_subscription_ops`` и применяются между
событиями.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from typing import TypeVar, cast

from dnd.application.dto.engine_event import EngineEvent
from dnd.application.ports.event_bus import EventBus, EventHandler, Unsubscribe

_logger = logging.getLogger(__name__)

E = TypeVar("E", bound=EngineEvent)


class InMemoryEventBus(EventBus):
    """Синхронная FIFO publish/subscribe.

    Не потокобезопасен — это сознательное решение. Пошаговая игра
    односекторная; добавлять блокировки = пессимизация без пользы.
    """

    def __init__(self) -> None:
        # NOTE: тип хранения — `EventHandler` без параметра, потому что
        # на этапе runtime Python не различает типы хендлеров после
        # стирания generics. Тип-сохранность гарантирует Protocol-API
        # `subscribe`/`publish` и mypy.
        self._subscribers: dict[type[EngineEvent], list[EventHandler[EngineEvent]]] = defaultdict(
            list
        )
        self._pending: deque[EngineEvent] = deque()
        # Отложенные операции над подписками во время диспатча.
        # Каждая — функция, применяющая изменение к `_subscribers`.
        self._pending_subscription_ops: list[Callable[[], None]] = []
        self._dispatching: bool = False

    def publish(self, event: EngineEvent) -> None:
        """Опубликовать событие. См. контракт ``EventBus.publish``."""
        self._pending.append(event)
        if self._dispatching:
            # Вложенный publish: текущий цикл подберёт.
            return
        self._drain()

    def subscribe(
        self,
        event_type: type[E],
        handler: EventHandler[E],
    ) -> Unsubscribe:
        """Подписаться. См. контракт ``EventBus.subscribe``."""
        # Конкретный тип хендлера стирается на runtime, и `_subscribers`
        # хранит список общего типа `EventHandler[EngineEvent]`.
        # Cast здесь безопасен: dispatch внутри сужает по типу события.
        erased_handler = cast(EventHandler[EngineEvent], handler)
        erased_type = cast(type[EngineEvent], event_type)

        if self._dispatching:
            # Отложить применение до межсобытийной паузы, чтобы текущая
            # волна работала с зафиксированным набором подписчиков.
            self._pending_subscription_ops.append(
                lambda: self._do_subscribe(erased_type, erased_handler)
            )
        else:
            self._do_subscribe(erased_type, erased_handler)

        def unsubscribe() -> None:
            if self._dispatching:
                self._pending_subscription_ops.append(
                    lambda: self._do_unsubscribe(erased_type, erased_handler)
                )
            else:
                self._do_unsubscribe(erased_type, erased_handler)

        return unsubscribe

    # --- внутреннее -----------------------------------------------------

    def _do_subscribe(
        self, event_type: type[EngineEvent], handler: EventHandler[EngineEvent]
    ) -> None:
        self._subscribers[event_type].append(handler)

    def _do_unsubscribe(
        self, event_type: type[EngineEvent], handler: EventHandler[EngineEvent]
    ) -> None:
        # Не падаем, если уже отписан или подписки нет — это допустимо
        # при повторной отписке.
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return

    def _drain(self) -> None:
        """Прогнать очередь событий до пустоты, поддерживая контракт §5.2."""
        self._dispatching = True
        try:
            while self._pending:
                event = self._pending.popleft()
                self._dispatch_one(event)
                # Между событиями — применить отложенные изменения подписок.
                # Это даёт контрактное «изменения применяются со следующей
                # публикации, а не задним числом к текущей».
                if self._pending_subscription_ops:
                    ops = self._pending_subscription_ops
                    self._pending_subscription_ops = []
                    for op in ops:
                        op()
        finally:
            self._dispatching = False

    def _dispatch_one(self, event: EngineEvent) -> None:
        # Подписки матчатся по типу события **и его базам** (любой
        # подписчик на EngineEvent получит все события).
        # Для каждого типа в MRO собираем хендлеров в порядке регистрации.
        # Снимок списка нужен, чтобы изменения подписок во время
        # дисптача не повлияли на текущую итерацию.
        handlers: list[EventHandler[EngineEvent]] = []
        for klass in type(event).__mro__:
            if klass is object:
                break
            handlers.extend(self._subscribers.get(klass, ()))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Контракт §5.2 п.4: ловим, логируем, продолжаем.
                _logger.exception(
                    "EventBus subscriber raised on %s; continuing dispatch",
                    type(event).__name__,
                )

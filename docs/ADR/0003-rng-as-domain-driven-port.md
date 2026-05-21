# ADR 0003 — RNG как driven-port в `domain/ports/`

## Контекст

В первой итерации `Protocol RNG` положен в `src/dnd/application/ports/rng.py`.
Это работает, тесты зелёные. Но `src/dnd/domain/values/dice.py:33` импортирует
`from dnd.application.ports.rng import RNG` — что прямо нарушает
заявленное направление зависимостей:

> `interfaces → application → domain ← infrastructure`

`domain` не должен импортировать из `application`. Аудит 03
(`docs/audit/03_architecture_isolation.md`, A-001) выделил это как S1.

## Решение

`RNG` переносится в **`src/dnd/domain/ports/rng.py`**. Это **driven-port**
по терминологии гексагональной архитектуры: правила домена «дёргают
наружу» за случайностью, поэтому соответствующий порт принадлежит
домену.

`application/ports/` остаётся местом для **driver-портов** (`UserInterface`,
`ContentRepository`, `SaveRepository`, `TurnIntentProvider`, `Translator`,
`Clock`, `ConfigService`, `EventBus`) — это интерфейсы, через которые
**внешний мир** вызывает application-сервисы.

```
domain/ports/      ← driven-порты (правила вызывают внешний мир)
  └── rng.py
application/ports/ ← driver-порты (внешний мир вызывает приложение)
  ├── user_interface.py
  ├── content_repository.py
  ├── save_repository.py
  ├── ...
```

Реализации остаются в `infrastructure/`:

- `infrastructure/rng/real_rng.py` импортирует
  `from dnd.domain.ports.rng import RNG` (это разрешённое направление —
  infrastructure знает про domain).

## Причины

1. **Соблюдение направления зависимостей.** Без этого `domain` фактически
   зависит от `application`, что ломает изоляцию.
2. **Соответствие гексагональной архитектуре.** Driven-порты в `domain` —
   это каноника (Cockburn, Ports & Adapters).
3. **Возможность вынести `domain` в отдельный пакет.** Если когда-нибудь
   захочется поставлять domain как самостоятельную библиотеку (например,
   для CLI-калькулятора правил без всей инфраструктуры) — это станет
   возможным.
4. **Тестируемость не страдает.** `ScriptedRNG` в `infrastructure/rng/`
   импортирует только `domain.ports.rng.RNG` — тесты не зависят от
   application.

## Последствия

**Плюсы:**
- direction-стрелки соблюдены;
- архитектурный пример «driven vs driver» становится явным;
- удаляется единственное реальное нарушение, найденное аудитом A-001.

**Минусы:**
- появляется новый каталог `domain/ports/`, который надо документировать;
- небольшая инверсия привычки «все порты в одном месте».

**Что меняется в коде:**

1. Создаётся `src/dnd/domain/ports/__init__.py`.
2. Создаётся `src/dnd/domain/ports/rng.py` (содержимое — `Protocol RNG`,
   без `random()` и без `@runtime_checkable` — см. отдельный YAGNI-фикс
   из коммита C).
3. `src/dnd/domain/values/dice.py` импортирует
   `from dnd.domain.ports.rng import RNG`.
4. `src/dnd/infrastructure/rng/real_rng.py` и
   `src/dnd/infrastructure/rng/scripted_rng.py` импортируют оттуда же.
5. `src/dnd/application/ports/rng.py` — **удаляется**.

Тесты — pass без изменений (импорты тестов не привязаны к application).

## Альтернативы и почему отвергнуты

- **Локальный `Protocol RNG` в `domain/values/dice.py`.** Не плодит
  отдельный каталог, но множит протоколы по разным файлам и теряет
  «единое место для портов домена». Если завтра нужен другой driven-port
  (`Clock` тоже может стать driven, например), мы не хотим разбрасывать
  Protocol-ы.
- **Оставить как есть с пометкой «осознанное послабление».** Это
  закрепляет паттерн «domain → application можно», по которому пойдут
  следующие модули. Аудит явно показал, что это создаёт прецедент.
- **Перенести ВСЕ порты в `domain/ports/`.** Тогда `application/ports/`
  пустует. Но `UserInterface`, `ContentRepository`, `SaveRepository` —
  это **driver**-порты (внешний мир вызывает приложение), их место
  по канонике — в application.

## Когда применяется

Реализация — в **коммите C** серии правок аудита (refactor(domain):
изоляция и i18n). После этого ADR — в силе; любые новые driven-порты
(когда понадобятся — например, для гипотетического `RandomTimer`)
кладутся в `domain/ports/` по тому же принципу.

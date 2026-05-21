# Тесты

Тесты разбиты по уровням, маркерам и автоматизированы локально и в CI.

## Уровни

| Каталог | Уровень | Маркер | Цель |
|---|---|---|---|
| `tests/unit/` | юнит | (none) | Чистый домен и application без I/O. Должно гонять мгновенно. |
| `tests/integration/` | интеграция | `integration` | SQLite-репозитории, загрузка YAML контента, `ScenarioRuntime` на InMemory-репозитории. |
| `tests/e2e/` | end-to-end | `e2e` | Сквозные сценарии партии: создание персонажа → бой → сейв → загрузка → продолжение. С `ScriptedRNG` и `RecordingUI`. |

Дополнительные маркеры:

- `rules` — тесты, которые буквально проверяют соответствие правилам книги 2024 (точные таблицы модификаторов, поведение крита, преимущество/помеха, …). Помечать всё, что является **тестом-доказательством правила**.
- `property` — property-based тесты (hypothesis). Запускаются увеличенным числом примеров в CI.
- `slow` — длинные тесты (>1 сек), исключаются из `make test-fast`.

## Запуск локально

```bash
# Установить зависимости
make install-dev

# Всё разом (то же, что в CI)
make test-cov

# Быстрый прогон (юниты, fail-fast)
make test-fast

# Только property-based (с CI-профилем hypothesis)
make test-property

# По уровням
make test-unit
make test-integration
make test-e2e

# Линт и типы (без тестов)
make check
```

## Hypothesis: профили

Управляется переменной окружения `HYPOTHESIS_PROFILE`:

- `dev` (по умолчанию) — 50 примеров на тест, дедлайн 1.5 с. Быстрый цикл.
- `ci` — 300 примеров, дедлайн 2.5 с, derandomize (воспроизводимость на CI).
- `debug` — 1000 примеров, verbose, без дедлайна. Для отладки конкретного property.

```bash
HYPOTHESIS_PROFILE=ci pytest tests/unit/domain
HYPOTHESIS_PROFILE=debug pytest tests/unit/domain/test_dice.py::test_invariant_property
```

## Покрытие

Цель — **≥85%** по `src/dnd/` (порог в `[tool.coverage.report].fail_under`).
Падение покрытия ниже порога ломает CI.

```bash
make test-cov           # консольный отчёт + html в htmlcov/
xdg-open htmlcov/index.html
```

## Тестовые двойники (test doubles)

Живут в [`tests/_doubles/`](_doubles/__init__.py):

- `ScriptedRNG` (в `infrastructure/rng/`, потому что используется и за пределами тестов) — детерминированные броски.
- (по мере появления) `RecordingUI`, `DictTranslator`, `FrozenClock`, `StubMonsterAI` и т.п.

«InMemoryContentRepository» — не дабл, а полноценная реализация в `infrastructure/content/`, см. ADR-обоснование в `docs/ARCHITECTURE.md` §10.

## Docker

Если хочется прогнать весь CI-цикл в чистой среде:

```bash
make docker-build
make docker-test
```

Образ зафиксирован на `python:3.12-slim`. Локальный код монтируется через volume, перезаписи слоёв не требуется.

## CI

Файл [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Три параллельных job-а:

1. **Lint** — `ruff check` + `ruff format --check`.
2. **Type-check** — `mypy src` (strict).
3. **Tests** — матрица Python `3.11` / `3.12`, `pytest --cov`, артефакт `coverage.xml`.
4. **Docs lint** — мягкая проверка битых внутри-док ссылок (только warning'и).

Триггеры: push в `main`, любой PR в `main`, ручной запуск через UI.

## pre-commit

```bash
make pre-commit-install   # один раз
git commit ...            # хуки сработают автоматически
```

Хуки на коммит — быстрые: `ruff check --fix`, `ruff format`, `mypy src`, базовые гигиенические (trailing-whitespace, EOL, YAML/TOML-валидность).
Хук на push — `pytest tests/unit -x`, чтобы случайно не отправить сломанный код.

## Соглашения

1. **Один тест — одно поведение.** Если хочется проверить три случая —
   три отдельные `test_*` или `@parametrize`.
2. **Не моки ради моков.** Используем настоящий домен; для портов
   (`RNG`, `UserInterface`) — детерминированные двойники.
3. **Тесты правил книги — с маркером `@pytest.mark.rules`**, и в
   docstring — ссылка на страницу книги.
4. **Property-based — с маркером `@pytest.mark.property`**, и стратегия
   объявлена рядом с тестом.
5. **Никаких `time.sleep`/`datetime.now()`** в тестах. Время — через
   `FrozenClock` (когда появится порт `Clock`), случайность — через
   `ScriptedRNG`.

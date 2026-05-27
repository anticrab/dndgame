# dnd — консольная D&D 5e

Эталонный учебный Python-проект: текстовая ролевая игра по правилам Dungeons &
Dragons 5-й редакции (издание 2024) с CLI и ретро-TUI в стиле 80–90х.

## Цели

- Чёткая гексагональная архитектура (domain / application / infrastructure /
  interfaces), SOLID, паттерны (Repository, Strategy, Builder, Command,
  EventBus, Plugin Registry).
- SQLite как хранилище правил и сохранений; контент (расы, классы, монстры,
  предметы, сценарии) описывается в YAML и грузится сидером.
- Два интерфейса поверх одного движка: классический CLI и Textual-TUI в
  стилистике «зелёного фосфора».
- Высокое покрытие тестами (юнит / интеграция / e2e сценарий).

## Документация

- `docs/DESIGN.md` — бизнес-логика (бой, создание персонажа, исследование мира,
  сценарии мастера).
- `docs/ARCHITECTURE.md` — структура кода, слои, ключевые интерфейсы и стек.
- `docs/ADR/` — архитектурные решения и их обоснование.

## Быстрый старт

```bash
# установка (editable + dev-зависимости)
pip install -e ".[dev]"

# демо-бой в ретро-TUI (рекомендуется для показа)
dnd play demo_skirmish --tui

# тот же бой в классическом CLI (rich-лог, без TUI)
dnd play demo_skirmish
```

`dnd play` принимает id сценария из `data/content/scenarios.yaml`
(по умолчанию `mvp_skirmish`). Флаг `--tui` включает Textual-интерфейс
в стилистике «зелёного фосфора»; без него — пошаговый CLI на `rich` +
`questionary`. Тема TUI: `--theme color` (по умолчанию) или `--theme monochrome`.

> Команды `dnd db …`, `dnd character …`, `dnd content`, `dnd settings` —
> заглушки (выводят «not implemented»); реализуются по мере готовности
> соответствующих сервисов.

### Демо за минуту

Полный сценарий показа — в [`docs/DEMO.md`](docs/DEMO.md). Коротко:

```bash
dnd play demo_skirmish --tui
```

Воин 1-го уровня против пяти гоблинов. Подводите воина к врагам (`m` —
движение, `a` — атака), убивайте по одному. На **четвёртом** убийстве
всплывёт окно level-up — «Сейчас!» поднимет воина до 2 уровня прямо в бою
(+HP и новая способность **Action Surge**). Добейте последнего гоблина — победа.

## Структура

```
content/           данные правил и сценариев (YAML)
docs/              проектная документация
src/dnd/           исходники
  domain/            чистые правила D&D
  application/       use-cases и порты
  infrastructure/    SQLite, YAML, RNG, ИИ
  interfaces/        CLI (Typer) и TUI (Textual)
tests/             pytest
```

## Лицензия

MIT. D&D — товарный знак Wizards of the Coast; используется для учебных целей
по русскому переводу «Книги игрока 2024» (см. `Книга Игрока 2024.pdf` в корне).

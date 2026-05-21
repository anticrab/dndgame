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

## Быстрый старт (когда реализация будет готова)

```bash
# установка
pip install -e ".[dev]"

# инициализация БД и загрузка базового контента
dnd db init
dnd db seed

# создание персонажа и старт сценария
dnd play

# или классический CLI без TUI
dnd character new
dnd play --no-tui --scenario ravenloft-tutorial
```

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

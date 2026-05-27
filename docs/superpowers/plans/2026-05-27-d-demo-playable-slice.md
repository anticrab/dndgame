# Играбельный демо-срез — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать курированную боевую демо-сцену `demo_skirmish` и честные
инструкции запуска (TUI-first), чтобы за минуту показать рабочий цикл движка
с фирменным level-up в бою — реализуя всё **данными и доками**, без правок движка.

**Architecture:** Демо = контент (YAML-сценарий) + документация + смоук-тесты.
Сцена строится существующим `scenario_builder`; XP/level-up идут через уже
готовые `XpAwardService` + `LevelUpService` (как в `cli/app.py`). Ноль нового
кода движка — это и есть проверка расширяемости.

**Tech Stack:** Python 3.12, pydantic v2, pytest, YAML-контент, Textual (TUI),
typer (CLI). Тесты: `python3 -m pytest -q`, `python3 -m mypy src`,
`python3 -m ruff check src tests`.

**Спек:** `docs/superpowers/specs/2026-05-27-d-demo-playable-slice-design.md`.

**Имя коммитов:** `Maxim Lokotkov` / `anticrab@users.noreply.github.com`.
Язык доков/комментариев — русский.

---

## File Structure

- `data/content/scenarios.yaml` — **modify**: добавить блок `demo_skirmish`
  (карта 11×7 + 1 воин + 5 гоблинов).
- `tests/e2e/test_demo_skirmish.py` — **create**: смоук-тесты (загрузка сцены +
  XP→level-up арка через реальные сервисы).
- `README.md` — **modify**: переписать quickstart, добавить «Демо за минуту».
- `docs/DEMO.md` — **create**: пошаговый сценарий показа для защиты.
- `docs/SCENARIO_DEMO.md` — **modify**: врезка «Статус реализации».
- `docs/ROADMAP.md` — **modify**: веха «играбельное демо».

---

## Task D-1: Демо-сценарий `demo_skirmish` (контент) + тест загрузки

**Files:**
- Test: `tests/e2e/test_demo_skirmish.py` (create)
- Modify: `data/content/scenarios.yaml`

Карта 11×7. `#` — стены-колонны (укрытия), делящие подход врагов, чтобы воин
не получал 5 атак за раунд. Воин слева, 5 гоблинов справа волнами.

- [ ] **Step 1: Написать падающий тест загрузки сцены**

Создать `tests/e2e/test_demo_skirmish.py`:

```python
"""E2E демо-сцена `demo_skirmish` — основа «первичного показа».

Проверяем, что курированная боевая сцена корректно собрана из контента:
один воин-PC (fighter L1, со спасбросками от смерти) против пяти гоблинов,
и что суммарного XP за гоблинов заведомо хватает на level-up до 2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.engine.progression.xp_curve import FastXpCurve
from dnd.application.engine.scenario_builder import build_encounter_from_scenario
from dnd.composition import build_default_runtime_services
from dnd.domain.values.faction import Faction
from dnd.infrastructure.content.yaml_repository import YamlContentRepository

_CONTENT = Path("data/content")


def _build_demo():
    repo = YamlContentRepository(_CONTENT)
    scenario = repo.scenario_by_id("demo_skirmish")
    services = build_default_runtime_services()
    return scenario, build_encounter_from_scenario(
        scenario, content=repo, services=services
    )


@pytest.mark.e2e
def test_demo_skirmish_loads_with_warrior_vs_five_goblins() -> None:
    _scenario, enc = _build_demo()

    party = [cid for cid, f in enc.factions.items() if f is Faction.PARTY]
    monsters = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    assert len(party) == 1, "в демо ровно один PC-воин"
    assert len(monsters) == 5, "в демо пять гоблинов"

    warrior = enc.participants[party[0]]
    assert warrior.character_class == "fighter"
    assert warrior.level == 1
    assert warrior.uses_death_saves is True  # PARTY → death saves (страховка драмы)


@pytest.mark.e2e
def test_demo_skirmish_xp_budget_reaches_level_two() -> None:
    """Суммарный XP за всех гоблинов ≥ порога 2 уровня (100 по FastXpCurve)."""
    _scenario, enc = _build_demo()
    total_xp = sum(
        int(enc.participants[cid].challenge_rating * 100)
        for cid, f in enc.factions.items()
        if f is Faction.MONSTERS
    )
    assert total_xp >= FastXpCurve().threshold(2), (
        f"XP-бюджет демо ({total_xp}) меньше порога 2 уровня"
    )
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python3 -m pytest tests/e2e/test_demo_skirmish.py -q`
Expected: FAIL — `KeyError`/`scenario not found: demo_skirmish` (блока ещё нет).

- [ ] **Step 3: Добавить сценарий в `data/content/scenarios.yaml`**

Дописать в конец файла (отдельным блоком списка):

```yaml
# Этап D: курированная демо-сцена для «первичного показа» (TUI-first).
# Один воин L1 против 5 гоблинов; стены-колонны делят подход врагов на
# волны, чтобы воин не получал свалку атак. XP-бюджет (5×25=125) с запасом
# покрывает порог 2 уровня (100, FastXpCurve) — level-up срабатывает в бою
# на 4-м убийстве, пока жив 5-й гоблин. См. docs/DEMO.md, docs/SCENARIO_DEMO.md.
- id: demo_skirmish
  name: "Демо: Туннель гоблинов"
  map:
    width: 11
    height: 7
    legend:
      ".": floor
      "#": wall
    grid:
      - "..........."
      - "...#...#..."
      - "..........."
      - "...#...#..."
      - "..........."
      - "...#...#..."
      - "..........."
  spawns:
    - template_id: warrior_lv1
      instance_id: aelar
      at: [0, 3]
      faction: party
    - template_id: goblin
      instance_id: goblin1
      at: [10, 3]
      faction: monsters
    - template_id: goblin
      instance_id: goblin2
      at: [9, 1]
      faction: monsters
    - template_id: goblin
      instance_id: goblin3
      at: [9, 5]
      faction: monsters
    - template_id: goblin
      instance_id: goblin4
      at: [8, 2]
      faction: monsters
    - template_id: goblin
      instance_id: goblin5
      at: [8, 4]
      faction: monsters
```

- [ ] **Step 4: Запустить тест — зелёный**

Run: `python3 -m pytest tests/e2e/test_demo_skirmish.py -q`
Expected: PASS (2 теста).

- [ ] **Step 5: Коммит**

```bash
git add data/content/scenarios.yaml tests/e2e/test_demo_skirmish.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "feat(d): демо-сцена demo_skirmish (воин L1 vs 5 гоблинов) + тест загрузки"
```

---

## Task D-2: Смоук-тест XP→level-up арки на демо-контенте

**Files:**
- Modify: `tests/e2e/test_demo_skirmish.py`

Детерминированно (без бросков на попадание) проверяем главную фишку показа:
смерти 4 гоблинов через реальный `XpAwardService` дают воину 100 XP, что
поднимает `LevelUpReady`, а авто-применение `LevelUpService` (как в CLI)
повышает воина до 2 уровня. Это доказывает, что «4 убийства = level-up в бою»
работает на фактическом контенте демо.

- [ ] **Step 1: Дописать падающий тест в `tests/e2e/test_demo_skirmish.py`**

Добавить импорты в начало файла (рядом с существующими):

```python
from dnd.application.dto.engine_event import CreatureDied, LevelUpReady
from dnd.application.engine.features.defaults import default_feature_registry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.application.engine.progression.xp_award import XpAwardService
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository
```

Добавить тест в конец файла:

```python
@pytest.mark.e2e
def test_demo_skirmish_fourth_kill_triggers_levelup_to_two() -> None:
    """Смерти 4 гоблинов → 100 XP → LevelUpReady → авто level-up до 2.

    Воспроизводит ровно тот wiring, что в interfaces/cli/app.py (non-TUI):
    XpAwardService.subscribe() + авто-применение LevelUpService на LevelUpReady.
    """
    _scenario, enc = _build_demo()
    warrior_id = next(cid for cid, f in enc.factions.items() if f is Faction.PARTY)
    goblin_ids = [cid for cid, f in enc.factions.items() if f is Faction.MONSTERS]
    warrior = enc.participants[warrior_id]

    XpAwardService(
        event_bus=enc.event_bus, curve=FastXpCurve(),
        participants=enc.participants, factions=enc.factions,
    ).subscribe()
    level_up = LevelUpService(
        class_repository=YamlClassRepository(_CONTENT / "classes.yaml"),
        feature_registry=default_feature_registry(),
        event_bus=enc.event_bus,
    )
    ready: list[LevelUpReady] = []

    def _auto(ev: LevelUpReady) -> None:
        ready.append(ev)
        level_up.apply(enc.participants[ev.actor_id], to_level=ev.to_level, ctx=None)

    enc.event_bus.subscribe(LevelUpReady, _auto)

    # «Убиваем» первых четырёх гоблинов — публикуем их смерть в шину.
    for gid in goblin_ids[:4]:
        enc.event_bus.publish(CreatureDied(actor_id=gid))

    assert warrior.xp == 100, "4 гоблина × CR0.25×100 = 100 XP"
    assert ready and ready[-1].to_level == 2, "LevelUpReady на 2 уровень"
    assert warrior.level == 2, "авто level-up поднял воина до 2"
```

- [ ] **Step 2: Запустить — зелёный (логика опирается на готовые сервисы)**

Run: `python3 -m pytest tests/e2e/test_demo_skirmish.py -q`
Expected: PASS (3 теста). Если `warrior.xp` не 100 — проверить, что у goblin
`cr: 0.25` в `monsters.yaml` (он есть), и что XpAwardService начисляет всем
живым PARTY.

- [ ] **Step 3: Прогнать mypy + ruff на тесте**

Run: `python3 -m mypy tests/e2e/test_demo_skirmish.py && python3 -m ruff check tests/e2e/test_demo_skirmish.py`
Expected: чисто. При жалобе ruff на сортировку импортов — `ruff check --fix`.

- [ ] **Step 4: Коммит**

```bash
git add tests/e2e/test_demo_skirmish.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "test(d): смоук XP→level-up арки demo_skirmish (4 убийства → уровень 2)"
```

---

## Task D-3: README quickstart под реальный CLI + «Демо за минуту»

**Files:**
- Modify: `README.md`

Сейчас README обещает несуществующие команды (`dnd db seed`, `--no-tui`,
`ravenloft-tutorial`). Реальный интерфейс — `dnd play [SCENARIO_ID] [--tui]`.

- [ ] **Step 1: Заменить блок «Быстрый старт»**

Найти в `README.md` секцию «## Быстрый старт (когда реализация будет готова)»
и заменить её целиком на:

````markdown
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
````

- [ ] **Step 2: Проверить, что упомянутые команды реальны**

Run: `python3 -m dnd.interfaces.cli play --help`
Expected: показывает `[SCENARIO_ID]`, `--tui`, `--theme` — совпадает с README.

- [ ] **Step 3: Коммит**

```bash
git add README.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "docs(d): README quickstart под реальный dnd play + «Демо за минуту»"
```

---

## Task D-4: `docs/DEMO.md` — сценарий показа для защиты

**Files:**
- Create: `docs/DEMO.md`

- [ ] **Step 1: Создать `docs/DEMO.md`**

```markdown
# DEMO — сценарий «первичного показа»

Минутный показ рабочего движка для защиты/презентации. Сцена `demo_skirmish`:
воин 1-го уровня против пяти гоблинов в туннеле. Демонстрирует весь реально
работающий цикл и фирменный момент — **level-up прямо в бою**.

## Запуск

```bash
dnd play demo_skirmish --tui     # ретро-TUI (рекомендуется)
dnd play demo_skirmish           # классический CLI (rich-лог)
```

## Что показывает

| Фича движка | Где в демо |
|---|---|
| Инициатива, пошаговый бой | старт боя |
| Движение и атаки на сетке | `m` (движение), `a` (атака) |
| Retro-TUI (карта, спрайты, action-bar, лог) | весь экран |
| AI монстров | ходы гоблинов |
| XP за убийства | после каждого убитого гоблина |
| **Level-up в середине боя** | на 4-м убийстве — окно прокачки |
| Классовая фича после уровня | Action Surge (`x`) после 2 уровня |
| Спасброски от смерти (страховка) | если воин уйдёт в 0 HP |

## Ход показа (что говорить и нажимать)

1. **Старт.** «Воин 1-го уровня, пять гоблинов. Бросок инициативы — порядок
   ходов в панели справа.»
2. **Сближение.** `m`, навести курсор, подтвердить — воин идёт к ближайшему
   гоблину. Колонны (`#`) — укрытия, враги подходят волнами.
3. **Атаки.** `a`, выбрать цель — воин (длинный меч +5) обычно ваншотит
   гоблина (7 HP). «За каждого — 25 XP.»
4. **Level-up (кульминация).** На 4-м убийстве (100 XP) всплывает окно:
   «Вы достигли 2 уровня!» — выбрать **«Сейчас!»**. Воин получает +HP и
   **Action Surge** прямо в бою. «Это и есть фишка коротких партий — прокачка
   в драматический момент.»
5. **Добивание.** `x` (Action Surge — лишнее действие) и `a` — добить
   последнего гоблина. **Победа** (`EncounterEnded`, партия победила).

## Если что-то пойдёт не так

- Воин упал в 0 HP — он не умирает мгновенно (спасброски от смерти, пипсы
  в оверлее). Это тоже часть демонстрации, а не баг.
- Броски невезучие — бой по чистым правилам книги, исход честный; перезапустить
  командой запуска.

## Границы демо

`demo_skirmish` — **одна боевая сцена**. Исследование локаций, загадки,
ловушки, диалоги, save/load из полного сценария «Шахта Гнилого Дуба»
(`docs/SCENARIO_DEMO.md`) — запланированы, но в движке пока не реализованы.
```

- [ ] **Step 2: Коммит**

```bash
git add docs/DEMO.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "docs(d): DEMO.md — пошаговый сценарий показа demo_skirmish"
```

---

## Task D-5: Статус-врезка в SCENARIO_DEMO.md + веха в ROADMAP

**Files:**
- Modify: `docs/SCENARIO_DEMO.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Добавить врезку в начало `docs/SCENARIO_DEMO.md`**

Сразу после строки `Демонстрационный сценарий, на котором тестируются все
фичи MVP.` вставить:

```markdown
> **Статус реализации (этап D).** Это полный аспирационный сценарий. Движок
> сейчас отыгрывает только **боевые сцены**, поэтому из него реализована
> компактная боевая сцена `demo_skirmish` (см. `docs/DEMO.md`) — бой в стиле
> локации 2 («туннель гоблинов») с level-up в середине боя. Исследование
> локаций, скрытые объекты, загадки, ловушки, диалоги и save/load —
> **запланированы, пока не реализованы** (см. `docs/ROADMAP.md`).
```

- [ ] **Step 2: Отметить веху в `docs/ROADMAP.md`**

Найти раздел про этап R (или конец списка этапов) и дописать запись об этапе D.
Сначала прочитать текущий формат:

Run: `grep -n "R1\|R2\|##\|этап\|✅\|⏳" docs/ROADMAP.md | head -40`

Затем добавить строку в том же стиле, что соседние записи, например:

```markdown
- **Этап D — играбельное демо ✅** — курированная боевая сцена `demo_skirmish`
  (воин L1 vs 5 гоблинов) + честный quickstart и `docs/DEMO.md` для показа.
  Демо реализовано данными+доками, без правок движка (проверка расширяемости).
```

(Точная формулировка/маркеры — под фактический стиль ROADMAP.md.)

- [ ] **Step 3: Коммит**

```bash
git add docs/SCENARIO_DEMO.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
  commit -m "docs(d): статус реализации в SCENARIO_DEMO + веха демо в ROADMAP"
```

---

## Task D-6: Финальная проверка всего среза

**Files:** —

- [ ] **Step 1: Полный прогон тестов**

Run: `python3 -m pytest -q`
Expected: все тесты зелёные (1315 + 3 новых = 1318).

- [ ] **Step 2: mypy + ruff на всём**

Run: `python3 -m mypy src && python3 -m ruff check src tests`
Expected: чисто.

- [ ] **Step 3: Ручной дым-тест загрузки демо (CLI, без интерактива)**

Run: `python3 -c "from pathlib import Path; from dnd.infrastructure.content.yaml_repository import YamlContentRepository; print(YamlContentRepository(Path('data/content')).scenario_by_id('demo_skirmish').name)"`
Expected: печатает `Демо: Туннель гоблинов`.

- [ ] **Step 4: Сверить, что план покрыл спек**

Пройтись по §2 спека: демо-сцена (D-1) ✓, арка/level-up (D-2) ✓,
README+«демо за минуту» (D-3) ✓, DEMO.md (D-4) ✓, SCENARIO_DEMO+ROADMAP (D-5) ✓,
тесты (D-1/D-2/D-6) ✓. Инвариант «ноль правок движка» — соблюдён (менялись
только `data/`, `docs/`, `tests/`, `README.md`).
```
```

---

## Self-Review

- **Spec coverage:** §2.1 демо-сцена → D-1; §2.2 арка/level-up → D-2; §2.4
  README → D-3, DEMO.md → D-4, SCENARIO_DEMO+ROADMAP → D-5; §4 тесты → D-1/D-2/D-6;
  §3 «ноль правок движка» → проверяется в D-6 Step 4. Полное покрытие.
- **Placeholder scan:** конкретные тесты, YAML и тексты доков приведены целиком;
  единственное «под стиль файла» — формулировка строки ROADMAP (D-5 Step 2),
  т.к. формат ROADMAP читается на месте. Это не заглушка кода.
- **Type consistency:** `build_encounter_from_scenario(scenario, content=, services=)`,
  `XpAwardService(event_bus=, curve=, participants=, factions=).subscribe()`,
  `LevelUpService(class_repository=, feature_registry=, event_bus=).apply(creature, to_level=, ctx=)`,
  `CreatureDied(actor_id=)`, `LevelUpReady.to_level` — сверены с фактическими
  сигнатурами в коде.

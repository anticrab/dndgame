# Аудит 17: TUI (этап J)

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-23
**Под ревью:** этап J целиком (J1 design + J2 каркас + J3 bridge + J4
play --tui + e2e Pilot). Базовое состояние перед аудитом: 762 теста
зелёные, mypy strict clean (105 файлов), ruff clean.

Метод: один независимый агент (general-purpose) против `docs/TUI.md`
и реализации в `src/dnd/interfaces/tui/`. Зоны проверки — семь
пунктов из `docs/TUI.md`: архитектурная изоляция, sync/async связка,
PlayerIntentProvider-контракт, виджеты+темы, тесты, open questions,
UX. **S0 не найдено.**

---

## 1. Сводка находок

### S1 (нарушения инвариантов / DoD)

| ID | Где | Что |
|---|---|---|
| **TUI-A001** | `bridge/event_renderer.py:130-144` + `screens/battle.py:142-156` | Property `screen.map_widget` (и аналоги) выполняет `query_one(...)` синхронно. В вызове `self._call(self._screen.map_widget.refresh_from, ...)` property резолвится **в worker-треде** до того, как лямбда уйдёт в main-thread. Текущий NoMatches-catch — страховка стартовой гонки, но не thread-safety. Корректный паттерн — резолвить виджет внутри main-thread (передавать функцию-callback, не bound method виджета). |
| **TUI-T001** | `widgets/map_widget.py:50-117` | Inline-стили `style="yellow"/"red"/"cyan"/"white"/"magenta reverse"` в `render_battlefield`. Rich-разметка имеет приоритет над CSS Textual внутри Static → тема `monochrome` не действует на клетки карты (только на рамки). Инвариант TUI.md §2 пункт 5 нарушен. CSS-классы `.cell-*` из §6.1 не используются нигде. |
| **TUI-DoD001** | `docs/TUI.md` §3, §4, §11 vs `src/dnd/interfaces/tui/screens/` | `EndScreen` обещан как часть MVP, но не реализован. В §10 (Open questions) не вынесен в отложенные. Сейчас вместо него `log_widget.write("— Encounter complete; press Q to exit —")` — несимметрично заявленной DoD «сценарий проходится до Victory или Defeat». |
| **TUI-UX001** | `screens/battle.py:165-216` + `docs/TUI.md` §6.5 | После EncounterEnded action-меню (Footer) остаётся «живым»; нажатие `a/m/d/h/g/e` молча no-op (через `_current is None`). Нет фокусной точки победы. `q` без подтверждения, хотя §6.5 обещает «Quit (с подтверждением)». |

### S2 (косметика / тесты / минорные нюансы)

| ID | Где | Что |
|---|---|---|
| TUI-S2-LOG | `widgets/log_widget.py:42` | LogWidget зовёт приватный `printer._on_event(event)`. Если рефакторинг EventPrinter переименует метод — LogWidget сломается без warning. |
| TUI-S2-FLAKY | `tests/e2e/test_tui_play.py` | `pilot.pause(0.1-0.5)` + условный assert «если PC получил ход» (строки 75-92) — на загруженной CI станет тихим no-op. |
| TUI-S2-PICKERS | `tests/` | Нет тестов на `TargetPicker` / `MovePicker` (рендер chebyshev-пути, Tab/Enter в TargetPicker, валидация границ карты). |
| TUI-S2-STATUS | `bridge/event_renderer.py:84-97` | StatusWidget показывает только PC; на ходу монстра status не обновляется — игрок не видит HP монстра, который собирается ударить. |
| TUI-S2-HARDCODE | `screens/battle.py:174` | `[yellow]No reachable targets.[/]` — точечный inline-цвет вне CSS-классов. |
| TUI-S2-HKEY | `screens/battle.py:84-89` + UI.md/TUI.md | `h` (Dash) визуально путается с `H` (high cover на карте). На функциональность не влияет, но note в дизайн-документе стоит сделать. |

### Совпадает с дизайном (без замечаний)

* `import textual` локализован в `interfaces/tui/`; `domain/application/cli` чистые.
* `TuiIntentProvider` соответствует `PlayerIntentProvider` Protocol.
* `RunnerWorker` — daemon-thread, корректное `on_finished` callback,
  не блокирует exit.
* `BattleScreen.Ready` сигнал — полноценное решение стартовой гонки.
* `render_battlefield` — pure-функция, тестируема без Textual.

---

## 2. Что лечим в коммите `fix(audit-17)`

### S1 — все четыре

1. **TUI-A001** — `EventRenderer._refresh_*` оборачиваем в отдельные
   методы, которые ходят к виджетам **внутри main-thread**:
   `self._call(self._do_refresh_map)`. Property-доступы `screen.X`
   уходят в `_do_refresh_map`, исполняющуюся уже после
   `call_from_thread`.
2. **TUI-T001** — `render_battlefield` получает параметр
   `with_color: bool = True`. `MapWidget.refresh_from` сам подмешивает
   `with_color = (app.theme != "monochrome")`. В monochrome-теме
   inline-стили НЕ применяются — клетки печатаются plain'ом, и
   monochrome-тема воспринимается визуально.
3. **TUI-DoD001** — минимальный `EndScreen` (модальный overlay
   «Victory!/Defeat!/Draw» + кнопка Quit), `TuiApp` пушит его на
   `EncounterEnded`. Обновить TUI.md §3/§11 + добавить EndScreen в §6
   как реализованный.
4. **TUI-UX001** — после EncounterEnded `BattleScreen` ставит
   «дисэйблед» режим: action-handlers (a/m/d/h/g/e) сразу выходят
   через флаг `_concluded`. EndScreen перехватывает фокус. `q`
   подтверждение пока не делаем — обновляем §6.5: «Quit (мгновенно,
   подтверждение — пост-MVP)».

### S2 — половина (дёшево, по делу)

* **TUI-S2-LOG** — поднимаем `EventPrinter.dispatch_event` как
  public alias для `_on_event`.
* **TUI-S2-PICKERS** — добавляем 4-5 тестов на picker'ы (рендер
  пути chebyshev'ом + границы карты).
* **TUI-S2-STATUS** — `EventRenderer._on_turn_started` обновляет
  status для **любой** фракции, не только PARTY.
* **TUI-S2-HARDCODE** — `[yellow]` в battle.py заменяем на
  rich-маркап без цвета (только bold/dim).

### Откладываем (явный TODO в дизайне)

* **TUI-S2-FLAKY** — flaky e2e оставляем как есть; вторая итерация
  e2e-набора (через `pilot.press("a")→Pilot.click_target` + явные
  ассерты по логу) — отдельной задачей после реального
  пользовательского покликивания (пользователь сказал: «доделай TUI,
  я попробую покликать»).
* **TUI-S2-HKEY** — note в TUI.md §6.5: «`h` — Dash; не путать с
  глифом `H` (high cover на карте)».

---

## 3. После фиксов

DoD: `pytest -q` зелёный (~770 тестов), mypy strict / ruff clean,
`dnd play --tui --theme monochrome mvp_skirmish` рендерит карту
монохромно, после Victory появляется EndScreen с фокусом, action-меню
не реагирует.

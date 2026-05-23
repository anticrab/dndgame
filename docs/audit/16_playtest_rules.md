# Аудит 16: Playtest + PHB-2024 rules — сводный отчёт

**Автор:** Maxim Lokotkov
**Дата:** 2026-05-23
**Метод:** два независимых агента в параллель + ручные пробы автора.

* **Агент A (QA-playtest)** — гонял CLI через `ScriptedIntentProvider`
  по сценариям `mvp_skirmish` и `mvp_room`, искал UX-засады и тихие
  баги в `application/engine` + `interfaces/cli`.
* **Агент B (rules-vs-code)** — сверял реализацию с
  «Книга игрока 2024 - перевод от Phantom Studio.pdf», искал
  расхождения с RAW.
* Автор — отдельные пробы с невалидными intent'ами (атака на
  несуществующий ID / self / пустой path).

**Перед аудитом:** 727 тестов зелёных, mypy clean, ruff clean.
Все ранее открытые S0/S1 (AT-R001, HS-R001, MV-R001, ST-R001,
EN-R001..04, VS-R002, CL-A001/A002/R001/UX001) закрыты в коммитах
`fix(audit-08..15)`. Этот аудит — следующая итерация.

---

## 1. Сводная таблица находок

Полные обоснования с цитатами PHB и `файл:строка` — в отчётах
агентов (этот документ — приоритизированная сводка).

### S0 (нарушения правил / тихие баги — лечим сейчас)

| ID | Где | Что | Источник |
|---|---|---|---|
| **AT-R-NEW-003** | `actions/attack.py:175-214` | `AttackAction.can_perform_against` пропускает self-target → `aelar attacks aelar (AC 16): miss`. Действие тратится. | playtest S0-1 + автор |
| **AT-R-NEW-004** | `actions/attack.py:175-214` | Атака на мёртвую цель проходит как `Allowed`. Защита есть только на стороне `console_provider` (фильтрация в UI). Через scripted/AI/TUI — дыра. | playtest S0-2 |
| **MV-R-NEW-001** | `actions/move.py:118-162` | `MoveAction` не проверяет occupancy цели пути. PHB-2024 стр. 24: нельзя добровольно завершить ход в чужой клетке; нельзя проходить сквозь враждебных. | rules-audit |
| **SC-R-NEW-001** | `data/content/scenarios.yaml:30-53` | Сценарий `mvp_room` неразрешим: `CLOSED_DOOR` непроходима + нет `InteractIntent` / OpenDoorAction. Завершается только по `MAX_ROUNDS=100`. | playtest S0-3 |

### S1 (UX/правила — лечим сейчас)

| ID | Где | Что |
|---|---|---|
| **CL-UX002** | `engine_event.py` + `event_printer.py` | Dodge/Dash/Disengage не публикуют события и не печатаются → игрок не видит реакцию системы. |
| **CL-UX003** | `event_printer.py:85-97` | `AttackRolled` печатается без d20 / bonus / advantage-маркера → нельзя проверить, сработал ли Dodge. |
| **CL-UX004** | `game_runner.py:123-148` | Невыполнимые intents (Forbidden) — молча проглатываются. Игрок теряет ход без feedback. |
| **CL-UX005** | `event_printer.py:137-145` | `EncounterEnded.survivors` — есть в DTO, не печатается. После победы непонятно, кто из пати жив и с каким HP. |
| **CL-UX006** | `event_printer.py:99-104` | `DamageDealt` без текущего HP цели — игрок считает в уме. |
| **HS-R-NEW-002** | `actions/help_search.py:166-180` | `SearchKind = {PERCEPTION, INVESTIGATION}`. PHB-2024 стр. 357: Search — Wisdom-проверка, варианты Insight/Medicine/Perception/Survival. INVESTIGATION (Intelligence) в книге для Search не упомянут. |
| **MV-R-NEW-002** | `actions/move.py` | Проход через **союзника** должен стоить как difficult terrain (PHB-2024 стр. 24). Не реализовано. Фиксим вместе с MV-R-NEW-001. |

### S2 (косметика — лечим сейчас, дёшево)

| ID | Где | Что |
|---|---|---|
| **CL-S2-1** | `domain/values/square.py` | `Square` без `__str__` → лог печатает `Square(x=2, y=2)`. |
| **CL-S2-6** | `event_printer.py:_on_initiative` | Initiative не помечает фракции — в смешанных партиях игрок не видит, кто свой. |

### Откладываем (требуют отдельных подсистем / явный TODO)

| ID | Где | Что | Почему откладываем |
|---|---|---|---|
| AT-R-NEW-001 | `attack.py:19-20` | Ranged-в-melee disadvantage. TODO в коде. | Нужен явный «есть ли враг в 5 ft от меня + видит ли он меня + Incapacitated?» — это новый утиль; не блокирует MVP. |
| IN-R-NEW-001 | `encounter.py:531-563` | Disadvantage на initiative при Surprise / Incapacitated. | Нужен surprise-механизм + Condition-чек. Отдельная задача. |
| AT-R-NEW-002 | `attack.py:272-275` | Dodge «если цель видит атакующего». TODO. | Нужен Invisible-Condition; не блокер. |
| ST-R-NEW-001 | `stances.py:151` | Dash без модификаторов скорости. | Нет Bless/Slow/Haste в MVP. |
| ST-R-NEW-002 | `stances.py:74-110` | Docstring-TODO про DEX-save advantage. | Нужен SavingThrowAction. |
| CV-R-NEW-001 | `terrain.py` + `attack.py` | Cover-бонус к DEX-saves. | То же. |
| HP-R-NEW-002 | `creature.py` | Creature не различает PC/NPC при 0 HP. | Появится с `Character`. |
| CL-S2-2..5 | `event_printer.py`, `encounter.py` | Mark «end of turn», свернуть `skipped`-логи, console-script. | Косметика без блокеров. |
| PT-S1-7, PT-S1-8 | `console_provider.py` | Фильтр меню по доступности + показ карты. | UX-улучшения на следующих итерациях CLI; карта закрывается TUI (этап J). |

---

## 2. Что лечим в этом коммите (`fix(audit-16)`)

Один коммит на 4×S0 + 7×S1 + 2×S2:

1. **AT-R-NEW-003** — `AttackAction.can_perform_against`: запрет self-target (`Forbidden(SELF_TARGET)`).
2. **AT-R-NEW-004** — она же: запрет target.is_alive=False (`Forbidden(TARGET_DOWN)`).
3. **MV-R-NEW-001 + MV-R-NEW-002** — `MoveAction`: проверка occupancy финальной клетки (запрет); проход через враждебного — запрет; проход через союзника — стоимость ×2 (как difficult). Tiny размера: достаточно в _walk-helper'е сверять `_battlefield.creatures_at(cell)` против `actor.id` + factions.
4. **SC-R-NEW-001** — заменить `CLOSED_DOOR` в `mvp_room` на `FLOOR` (door по факту открыта) — это унифицирует сценарий с реальностью «нет OpenDoor action». TODO для будущей `OpenDoorAction` — в комментарии к YAML.
5. **CL-UX002** — `StanceTaken` event (одно на 3 stances, поле `stance: CombatStance`); подписать в `EventPrinter._dispatch`.
6. **CL-UX003** — `_on_attack` показывает `d20:NN total:NN [adv|dis|−] vs AC X → hit/miss`.
7. **CL-UX004** — `GameRunner._apply_intent` логирует причину Forbidden (через `_log` + новый event `IntentRejected`? Минимально — без события, только `_log.info`, в CLI слышно через `--verbose` будущий, в TUI — через notify). На этом этапе достаточно `_log` (test smoke не ломаем).
8. **CL-UX005** — `_on_encounter_ended` печатает `Survivors:` с HP.
9. **CL-UX006** — `_on_damage` приписывает `(HP cur/max)` целевого creature.
10. **HS-R-NEW-002** — `SearchKind`: убрать `INVESTIGATION`, добавить `INSIGHT / MEDICINE / PERCEPTION / SURVIVAL` (все Wisdom). Обновить `SearchPerformed.skill_kind` использование.
11. **CL-S2-1** — `Square.__str__` → `(x,y)`.
12. **CL-S2-6** — `_on_initiative` — добавить метку фракции `(PARTY)/(MONSTERS)` per entry.

### Что НЕ ломаем

* Существующие тесты — счёт событий и формат строк лога есть в
  `test_event_printer.py` и `test_playthrough.py`. Эти тесты будут
  скорректированы вместе с фиксами (`fix(audit-16)`-коммит).
* `MAX_ROUNDS=100` остаётся как hard guard (не сломанный сценарий).

### Ожидаемый результат

После фиксов:
* Полный pytest зелёный, новые тесты под каждый S0/S1.
* mypy strict / ruff чистые.
* Игрок в CLI видит каждый stance, причину промаха, survivors после
  победы, текущие HP при уроне.
* AttackAction не пропускает self/dead.
* MoveAction соответствует PHB-2024 стр. 24.
* `mvp_room` проходим без `OpenDoor` (дверь открыта по умолчанию).
* `SearchKind` соответствует книге.

---

## 3. Следующие итерации (после J)

* `InteractAction` / `OpenDoorAction` — превращает `CLOSED_DOOR` в
  `FLOOR` через interact-with-object (PHB-2024 стр. 21, free).
* `SurpriseMechanic` + Disadvantage on initiative.
* `Character` сущность + death saves + Unconscious-condition при 0 HP.
* `RangedAttackInMeleeRule` — disadvantage при враге в 5 ft.
* `SavingThrowAction` — закрывает DEX-save для Dodge / Cover.

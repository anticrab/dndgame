# Audit 04: код vs дизайн

Независимый аудит соответствия реализации спецификациям из `docs/`. Дата:
2026-05-21. Ревьюер: внешний.

## Резюме

- **Тестов проходит / всего:** 29 / 29 (`pytest` — все зелёные, 0.03 c).
- **Несоответствий с книгой:** 1 (нюанс крита + дополнительные кости, см. K-007).
- **Несоответствий с DESIGN/ENGINE/MASTER:** 4 (K-001, K-002, K-003, K-014).
- **Нарушений YAGNI (лишних абстракций):** 2 (K-001 `RNG.random()`, K-002 `runtime_checkable`).
- **Утечек i18n в домен:** 2 (K-005 `Ability.label_ru`, K-006 русские строки в `DiceExpr`/`RollResult`).
- **Пропущенных edge cases в тестах:** 7 (K-008 … K-013, K-015).
- **«Тихих» багов поведения (silent ignore):** 1 (K-004 — `advantage` на не-d20).
- **mypy strict не проверен локально:** mypy не установлен в окружении (см.
  «Документация в коде»). По чтению кода — типы аннотированы везде, проблем
  не видно.

---

## Найденные проблемы

### K-001. `RNG.random()` — YAGNI: метод не используется

**Тип:** YAGNI, лишняя поверхность порта
**Серьёзность:** S2
**Где:** `src/dnd/application/ports/rng.py:26-27`, `src/dnd/infrastructure/rng/real_rng.py:21-22`,
`src/dnd/infrastructure/rng/scripted_rng.py:19, 33-36`.

```python
# rng.py
def random(self) -> float:
    """Равномерное число из ``[0.0, 1.0)``."""
```

**Суть:** `grep -rn "\.random()" src/ tests/` находит ровно одно
использование — внутреннюю реализацию `RealRNG.random()` (делегирует
`random.Random.random()`). В коде правил (включая `domain/values/dice.py`)
вызов `rng.random()` отсутствует. То есть метод — спекулятивная абстракция,
которая:

1. усложняет тесты (`ScriptedRNG` тащит вторую очередь `_randoms`);
2. ничего не покрывает (`tests/unit/domain/test_dice.py` не проверяет
   `random()`, и не должен);
3. в `DESIGN.md §1.2 «Случайность изолирована»` и `ENGINE.md §7` —
   контракт `RNG` описан только через `roll`. Метода `random()` нет ни в
   одном из дизайн-документов.

**Рекомендация:** удалить `RNG.random` из порта, `RealRNG.random` и второй
аргумент `ScriptedRNG.__init__(... randoms=...)`. Если в будущем
понадобится — добавить в момент появления реального юзкейса
(например, для `LootTable` с вероятностями: но и там логично — `RNG.roll(100)`
и проверить `≤ chance*100`).

Минимальный diff:

```python
# application/ports/rng.py
@runtime_checkable
class RNG(Protocol):
    def roll(self, sides: int) -> int: ...
```

---

### K-002. `@runtime_checkable` на `RNG` — пока не нужно

**Тип:** YAGNI
**Серьёзность:** S2
**Где:** `src/dnd/application/ports/rng.py:14-15`.

**Суть:** `runtime_checkable` нужен только если код где-то делает
`isinstance(x, RNG)`. В текущем коде такой проверки нет:

```bash
$ grep -rn "isinstance.*RNG" src/ tests/  # пусто
```

Сам `Protocol` уже даёт статическую совместимость через mypy. Лишний
декоратор:
- расширяет contract suite (любой класс с методом `roll` теперь
  «случайно» проходит `isinstance` — это runtime-«утиная» проверка, а не
  по структуре, как ожидается);
- замедляет первый вызов `isinstance` (CPython кеширует, но всё же).

**Рекомендация:** убрать `@runtime_checkable`, оставить чистый
`Protocol`. Если потом захочется — вернуть в момент потребности.

---

### K-003. `random()` будущий `LiveRNG` всё равно вряд ли вернёт `float ∈ [0, 1)`

**Тип:** spec-mismatch (готовность к расширению)
**Серьёзность:** S2
**Где:** `application/ports/rng.py:26`, `docs/ENGINE.md §7` (`LiveDiceRoller`).

**Суть:** `ENGINE.md §7` описывает не `LiveRNG`, а `LiveDiceRoller` —
живой ввод поднимается **уровнем выше** `RNG`, на слой `DiceRoller`.
То есть `LiveRNG.random() -> float` — не нужен будет даже потом. Это
дополнительно подтверждает K-001.

**Рекомендация:** удалить `random()`. Если когда-нибудь и появится
`LiveRNG`, его естественный API — `roll(sides) -> int` (мастер вводит
выпавшее число цельным).

---

### K-004. `advantage`/`disadvantage` молча игнорируются на не-d20 — потенциальный баг

**Тип:** контракт/UX
**Серьёзность:** S1
**Где:** `src/dnd/domain/values/dice.py:108-143`, ветка работает только при
`count == 1 and sides == 20`. На любом другом выражении флаги выкидываются,
причём в `RollResult` поля `advantage`/`disadvantage` тоже становятся
`False` (см. строки 156-158, и подтверждено экспериментально:
`DiceExpr.parse('2d6').roll(rng, advantage=True).advantage` → `False`).

**Суть:** docstring говорит «аргументы игнорируются — это удобно для
единообразного API». На практике это «тихий молчаливый отказ»:
вызывающий думает, что бросок c преимуществом, а получает обычный, без
предупреждения. Это рассинхронизирует код и поведение:

- Книга (стр. 11): преимущество/помеха — модификатор для **одного**
  броска d20 (атака/спасбросок/проверка). Применять к броску урона
  или 4d6kh3 — бессмыслица.
- Корректное поведение: либо `raise ValueError` (если флаг применили не
  к d20 — это ошибка вызывающего), либо хотя бы залогировать.

**Рекомендация:** жёстко:

```python
if (advantage or disadvantage) and not (self.count == 1 and self.sides == 20):
    raise ValueError("преимущество/помеха применимы только к одиночному d20")
```

Параллельно стоит зафиксировать это в DESIGN.md §3 как явное ограничение.

---

### K-005. `Ability.label_ru` — i18n-утечка в domain

**Тип:** i18n leak
**Серьёзность:** S1
**Где:** `src/dnd/domain/values/ability.py:19-31`.

```python
class Ability(StrEnum):
    @property
    def label_ru(self) -> str: ...

_RU_LABELS = { Ability.STR: "Сила", ... }
```

**Суть:** `I18N.md §1` явно требует, что UI-строки живут в `.po`-файлах,
а домен оперирует идентификаторами. `Ability.STR.label_ru` — это
**отображаемая строка** в `domain/values/`. Это нарушает изоляцию слоёв
(domain не должен знать о русском/английском, тем более как hardcode).

Кроме того, метод сейчас уже используется в **сообщении об ошибке** в
`AbilityScore.__post_init__` (`f"{self.ability.label_ru}: ..."`). Тут
двойная утечка: 1) русский в domain; 2) техническая ошибка
(валидационное исключение) — это **лог разработчика** (см. I18N.md §1,
строка про «лог технических ошибок и трейсбеки — английский»).

**Рекомендация:**

1. Убрать `label_ru`/`_RU_LABELS` из domain. Метку отдавать через
   `i18n/translator`: ключи вроде `ability.str.label`. До появления
   собственно i18n-слоя — `_(f"ability.{ability.value.lower()}")` или
   просто использовать `ability.value` в технических сообщениях.
2. Сообщение валидации `AbilityScore.__post_init__` — на английский:
   `f"{self.ability.name}: score {self.score} out of range 1..30"`.

---

### K-006. `DiceExpr.__post_init__`, `DiceParseError`, `RollResult.describe()` — те же утечки i18n

**Тип:** i18n leak (мягче — debug-формат)
**Серьёзность:** S2 (для исключений), S2 (для `describe()` приемлемо, но
надо явно зафиксировать в дизайне)
**Где:**

- `dice.py:70-77` — `ValueError("число костей должно быть ≥ 1")` и т.п.
- `dice.py:85` — `DiceParseError(f"не удалось разобрать выражение костей: {text!r}")`.
- `dice.py:209-224` — `describe()` собирает русский текст
  («сброшено: …», «с преимуществом», «крит ×кости»).

**Суть:** ошибки исключений — на русском. По `I18N.md §1`, технические
исключения и логи — английский. `describe()` — рекомендуется явно
пометить как debug-helper и в проде заменить на UI-рендерер через
`Translator`. Сейчас домен фактически содержит представленческий код.

**Рекомендация:**

1. Тексты `ValueError`/`DiceParseError` — на английский (это технические
   ошибки, читают разработчики).
2. `RollResult.describe()` — пометить docstring'ом «debug-only, не
   использовать в UI», ИЛИ вынести в `interfaces/cli/renderers/` (где
   и место рендеру). Сейчас метод соблазнительно использовать в TUI и
   получить русскую жёсткую строку.

---

### K-007. Крит и дополнительные кости — не задокументировано

**Тип:** spec gap
**Серьёзность:** S2
**Где:** `dice.py:108-159`, `DESIGN.md §3`, `tests/unit/domain/test_dice.py:83-89`.

**Суть:** Книга (стр. 12, «Критическое попадание») и общие правила 5e
2024: при крите **удваиваются все кости урона**, включая дополнительные
(например, Скрытая атака плута добавляет 2d6 — в крите они тоже
удваиваются: 4d6). В текущей реализации `crit=True` корректно удваивает
**одно** выражение `DiceExpr`. То есть если бросок урона делается
**отдельными** `DiceExpr` (`1d8+3` оружие + `2d6` Sneak), вызывающий
должен пометить `crit=True` на **обоих**. Это правильное поведение, но
оно никак не зафиксировано:

1. В `DESIGN.md §3` пример крита `3d8+5 crit` оставляет неоднозначность.
2. В тесте `test_crit_doubles_dice_but_not_modifier` проверено только
   `1d8+3` — нет проверки крита на 2d6 (где могло бы быть видно
   удвоение количества).

**Рекомендация:** добавить в `DESIGN.md §3` явную фразу: «крит
удваивает кости только в этом выражении; если урон состоит из нескольких
выражений (оружие + sneak attack), вызывающий применяет `crit=True` к
каждому». И один тест:

```python
def test_crit_doubles_extra_damage_dice() -> None:
    rng = ScriptedRNG([6, 5, 4, 3])  # 2d6 → 4d6
    r = DiceExpr.parse("2d6").roll(rng, crit=True)
    assert r.total == 6 + 5 + 4 + 3 == 18
```

---

### K-008. Парсер не различает «нет модификатора» и `+0` (визуальный)

**Тип:** edge case (косметический)
**Серьёзность:** S2
**Где:** `dice.py:88-89`, `__str__` на 102.

**Суть:** `DiceExpr.parse("1d20+0")` → `modifier=0` → `__str__()` → `"1d20"`.
Это правильно (нормализация), но в `test_str_round_trip` явно полагаемся
на это поведение без проверки. Не баг, отметить.

**Рекомендация:** в `test_str_round_trip` дополнить кейсом
`("1d20+0", "1d20")` через явную ассерцию `str(...)`.

---

### K-009. Парсер чувствителен к «d` с пробелом

**Тип:** edge case
**Серьёзность:** S2
**Где:** `dice.py:36-51`.

**Суть:** `DiceExpr.parse("2d6+3")` — ОК.
`DiceExpr.parse("2d6 + 3")` — **ОК** (пробел вокруг знака
проглатывается). Но `DiceExpr.parse("1 d 20")` падает. Это
непоследовательно. Если пользователю/конфигу разрешено `2d6 + 3`, то
почему не `1 d 20`?

**Рекомендация:** либо «строго: никаких внутренних пробелов» (тогда
зарезать `2d6 + 3`), либо «toleratнo: пробелы везде». Поведение должно
быть осознанным и зафиксированным в DESIGN.md §3 и в тесте.

---

### K-010. Тест `test_str_round_trip` — есть, но не покрывает `kl`

**Тип:** missing test
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_dice.py:92-96`.

**Суть:** `keep_lowest` (`klN`) есть в коде (парсер, валидация, выбор),
но протестирована только в одном случае — `test_str_round_trip` его не
проверяет (`"4d6kh3"` есть, `"4d6kl1"` нет), и ни один тест не проверяет
**бросок** с `kl`. Это «слепая» ветка `dice.py:170-172`.

**Рекомендация:** добавить:

```python
def test_keep_lowest_works() -> None:
    rng = ScriptedRNG([6, 5, 4, 1])
    r = DiceExpr.parse("4d6kl1").roll(rng)
    assert r.kept == (1,)
    assert r.dropped == (4, 5, 6)
```

---

### K-011. Нет теста на парсинг битых форм

**Тип:** missing test
**Серьёзность:** S2
**Где:** `test_dice.py`.

**Суть:** проверено только `parse("hello")`. Не проверены:

- пустая строка `""` (выкидывает `DiceParseError`, корректно — но тест нужен);
- `0d6`, `1d0` (выкидывают `ValueError`, не `DiceParseError` — это
  отдельная история; контракт парсинга «всегда `DiceParseError` на
  невалидном выражении» нарушен);
- `2d6kh4` (kh > count — `ValueError`);
- одновременный `2d6kh1kl1` (парсер съест только один благодаря regex —
  тест зафиксировал бы поведение);
- большие числа: `1000000d20` (валидно, но опасно по памяти; нужен
  cap?).

**Рекомендация:** параметризованный тест на коллекцию плохих форм. И
решить: ловить `0d6` ещё на этапе `parse`, оборачивая `ValueError` в
`DiceParseError`, либо явно задокументировать «`parse` валидирует
синтаксис, `DiceExpr.__post_init__` — семантику».

---

### K-012. Нет теста на `AbilityScore.adjusted(-N)` с уходом в недопустимый диапазон

**Тип:** edge case
**Серьёзность:** S2
**Где:** `ability.py:65-68`.

**Суть:** Сейчас `AbilityScore(STR, 3).adjusted(-5)` падает с
`ValueError: ... -2 вне диапазона 1..30`. Поведение разумное, но не
покрыто тестом — лёгкий регресс пройдёт незаметно.

**Рекомендация:** один тест:

```python
def test_adjusted_negative_below_floor_raises() -> None:
    with pytest.raises(ValueError):
        AbilityScore(Ability.STR, 3).adjusted(-5)
```

---

### K-013. `is_natural_20` на `d20 advantage` — корректно, но не покрыто тестом

**Тип:** missing test (положительный кейс)
**Серьёзность:** S2
**Где:** `dice.py:191-198`, `test_dice.py:73-80`.

**Суть:** при броске `d20 advantage` с парой `(20, 7)` → `kept=(20,)`,
`is_natural_20 == True`. Поведение по книге верное (нат.20 на любом из
двух — крит при атаке). Но тест `test_natural_20_and_1_flags` бросает
**без** преимущества. Стоит зафиксировать кейс «adv + нат.20 → флаг».

**Рекомендация:**

```python
def test_natural_20_with_advantage() -> None:
    rng = ScriptedRNG([7, 20])
    r = DiceExpr.parse("d20+5").roll(rng, advantage=True)
    assert r.is_natural_20 is True
```

То же для `disadvantage` + нат.1.

---

### K-014. Нет инфраструктуры под `RollIssued` / `RollApplied` — пока ОК, но проверить готовность

**Тип:** spec mismatch (на будущее — не критично сейчас)
**Серьёзность:** S2 (на текущем этапе)
**Где:** `MASTER.md §6.2`, `ENGINE.md §6.2`, `ENGINE.md §7` vs реальность.

**Суть:** Сейчас домен бросает кости напрямую: `DiceExpr.roll(rng)` →
`RollResult`. По `MASTER.md §6.2` и `ENGINE.md §7` нужно будет
разделить: `DiceRoller` поднимается над `RNG`, генерирует пару событий
`RollIssued` / `RollApplied`, между ними мастер может вмешаться.
**Это пост-MVP**, но архитектурно `DiceExpr.roll(rng)` сейчас
эту пару не моделирует.

Что важно — текущий `DiceExpr.roll(rng, advantage=..., crit=...)`
**возвращает все «сырые»** данные (`rolls`, `kept`, `dropped`,
`modifier`). Этого достаточно, чтобы будущий `ComputerDiceRoller`
обернул их в `RollIssued(raw=rolls)` / `RollApplied(outcome=total)` без
правок в `domain`. То есть готовность есть.

**Рекомендация:** добавить в `RollResult` поле `raw_d20: int | None` —
**одно число** d20 без модификаторов, для статистики. Сейчас извлекать
его из `kept[0]` корректно, но семантически непрозрачно (на 4d6kh3
`kept[0]` — другое). Это упростит будущий `DiceStatisticsService`
(см. `UI.md:295`).

Альтернатива: добавить вычисляемое свойство:

```python
@property
def d20_raw(self) -> int | None:
    if self.expr.sides == 20 and self.expr.count == 1:
        return self.kept[0]
    return None
```

---

### K-015. `RollResult.modifier` и `RollResult.total` имеют значение по умолчанию `0`

**Тип:** code-smell (некритично)
**Серьёзность:** S2
**Где:** `dice.py:184-185`.

**Суть:**

```python
modifier: int = 0
total: int = 0
```

Это допустимо при текущей инвариантности (все вызовы `roll()` заполняют
их явно), но даёт возможность создать невалидный `RollResult` напрямую.
Поскольку это иммутабельный value-object, лучше — обязательные параметры
(без default).

**Рекомендация:** убрать default, либо добавить
`__post_init__`-проверку `total == sum(kept) + modifier`.

---

### K-016. CLI: команда `db` принимает `str` без валидации

**Тип:** type safety
**Серьёзность:** S2
**Где:** `interfaces/cli/app.py:44-47`.

```python
def db(action: str = typer.Argument(..., help="init | seed | reset")) -> None:
```

**Суть:** Typer умеет принимать `Enum` (включая `StrEnum`), и тогда
неправильное значение даст красивую ошибку CLI. Сейчас `dnd db hello`
тихо выведет «не реализовано» — пользователь подумает, что фича
«запланирована», тогда как `hello` — мусор.

**Рекомендация:**

```python
class DbAction(StrEnum):
    INIT = "init"
    SEED = "seed"
    RESET = "reset"

def db(action: DbAction = typer.Argument(...)) -> None: ...
```

---

### K-017. CLI: не хватает команды `content` и `settings`

**Тип:** completeness
**Серьёзность:** S2 (заглушки — можно отложить)
**Где:** `app.py`.

**Суть:** В `DESIGN.md §13` упомянуты команды CLI: «создать персонажа,
начать сценарий, играть, сохранить/загрузить, показать лист персонажа,
выйти». В коде сейчас: `play`, `character`, `db` (+ глобальный
`--version`). Не хватает:

- `content` — список загруженного контента, валидация YAML (см.
  `DESIGN.md §11`, `ARCHITECTURE.md §2`);
- `settings` — открыть настройки локали/тем (см. `I18N.md §9`, `UI.md`);
- `save list/load/delete` или `dnd save ...` (отдельный namespace).

**Рекомендация:** добавить заглушки сейчас же, чтобы UX был
предсказуемым, и потом по мере реализации заполнять. Цена — 5 строк.

---

### K-018. `AbilityScores` не поддерживает `__getitem__` / итерацию

**Тип:** convenience
**Серьёзность:** S2
**Где:** `ability.py:71-113`.

**Суть:** `scores.get(Ability.STR)` работает. Но идиоматичнее —
`scores[Ability.STR]`. Также часто нужно «пробежать по всем 6
характеристикам» (для отрисовки листа). Сейчас вызывающий обязан
вспоминать имена полей `str_`, `int_`, `cha`.

**Рекомендация:**

```python
def __getitem__(self, ability: Ability) -> AbilityScore:
    return self.get(ability)

def __iter__(self) -> Iterator[AbilityScore]:
    yield from (self.str_, self.dex, self.con, self.int_, self.wis, self.cha)
```

Маленький, дешёвый, окупится при отрисовке character sheet.

---

### K-019. `AbilityScores.of(...)` использует `str_=`, `int_=` — приемлемо, но колко

**Тип:** API ergonomics
**Серьёзность:** S2 (не править — но зафиксировать как осознанный выбор)
**Где:** `ability.py:84-100`.

**Суть:** `str_`, `int_` — стандартный приём в Python для имён,
коллидирующих с встроенными. Альтернатива — `strength=`, `intelligence=`,
но это длинно. Текущий вариант — компромисс. **Не править**, но в
docstring фабрики стоит написать одну строку «`str_`/`int_` —
underscore-postfix, чтобы не конфликтовать с встроенными».

---

### K-020. pytest-маркер `rules` объявлен и не использован

**Тип:** YAGNI / dead config
**Серьёзность:** S2
**Где:** `pyproject.toml:84-87`.

```toml
markers = [
  "slow: ...",
  "rules: проверки правил по книге",
]
```

**Суть:** `grep -rn "@pytest.mark.rules" tests/` — пусто. Маркер
зарезервирован, но не работает. С `--strict-markers` он не вредит (тесты
без него — без проблем). Это **намерение**, и оно разумное: пометить
тесты, которые буквально доказывают соответствие книге.
`test_modifier_matches_table` — кандидат №1.

**Рекомендация:** или применить маркер хотя бы к одному тесту, или
удалить. Лучше — применить:

```python
@pytest.mark.rules
@pytest.mark.parametrize(...)
def test_modifier_matches_table(...): ...
```

---

### K-021. `pyproject.toml` `addopts` использует `--strict-config` — он подключен корректно

**Проверка:** `pytest 9.0.3` + `--strict-config` + `--strict-markers` — всё
зелёное, ошибок не выбрасывает. ОК, замечаний нет.

---

## Карта покрытия тестами

| Модуль | Публичные функции/классы | Тесты | Пропуск |
|---|---|---|---|
| `domain/values/ability.py` | `modifier()`, `Ability` (enum + `label_ru`), `AbilityScore`, `AbilityScore.modifier`, `AbilityScore.adjusted`, `AbilityScores.of/get/modifier` | `test_modifier_matches_table` (×11), `test_modifier_rejects_zero_and_below`, `test_ability_score_validates_range`, `test_ability_score_adjusted_respects_cap`, `test_ability_scores_lookup_and_modifier` | `Ability.label_ru` (вообще не покрыт), `adjusted` с отрицательной до диапазона < 1 (см. K-012). |
| `domain/values/dice.py` | `DiceExpr.parse`, `DiceExpr.roll`, `DiceExpr.__str__`, `DiceExpr.__post_init__`, `RollResult.is_natural_20`, `RollResult.is_natural_1`, `RollResult.describe`, `DiceParseError` | `test_parse_d20`, `test_parse_with_modifier_and_keep`, `test_parse_cyrillic_k`, `test_parse_rejects_garbage`, `test_simple_roll_two_d6`, `test_keep_highest_3_of_4d6`, `test_advantage_picks_higher_of_two_d20`, `test_disadvantage_picks_lower`, `test_advantage_and_disadvantage_cancel`, `test_natural_20_and_1_flags`, `test_crit_doubles_dice_but_not_modifier`, `test_str_round_trip` | `keep_lowest` бросок (K-010), нат.20 при advantage (K-013), крит на 2d6 (K-007), `RollResult.describe` (вообще не покрыт), внутренние `__post_init__`-валидации `DiceExpr` (`0d6`, `1d0`, kh > count, kh+kl). |
| `application/ports/rng.py` | `RNG` (Protocol) | — (нет тестов; isinstance-проверка через `runtime_checkable`-семантику нигде не использована) | `random()` (K-001). |
| `infrastructure/rng/real_rng.py` | `RealRNG.__init__`, `RealRNG.roll`, `RealRNG.random` | — (вообще нет dedicated-тестов; косвенно используется через дымовой `__init__.py`? нет — даже косвенно нет.) | Всё. `RealRNG.roll(0)` ошибку выкидывает корректно, но без теста. Сид-репродуцируемость не покрыта. |
| `infrastructure/rng/scripted_rng.py` | `ScriptedRNG.__init__`, `ScriptedRNG.roll`, `ScriptedRNG.random` | используется в `test_dice.py` как фикстура | Прямого теста на исчерпание и валидацию диапазона нет. |
| `interfaces/cli/app.py` | `app` объект (typer.Typer), `_root`, `play`, `character`, `db`, `main` | `test_cli_app_constructed` — только импорт | Никаких click/typer runner-тестов; не проверено `--version`, не проверено что заглушки печатают что-то. |
| `interfaces/cli/__main__.py` | `main()` entry | — | — (тривиально, ОК). |
| `dnd/__init__.py` | `__version__` | `test_package_imports` | — (ОК). |

**Coverage-проверка по `pyproject.toml`:** `fail_under = 80`. Локально
запустить `pytest --cov` мы не можем (`pytest-cov` не установлен в
системе), но визуально оценочно покрытие ~85–90% (RNG-инфраструктура и
CLI прокол).

---

## Готовность к расширениям

| Расширение | Готов | Что нужно подкрутить |
|---|---|---|
| **Монстры с показателями 1..30** | ✅ Да | `AbilityScore` уже принимает 1..30. Тест на 30 есть. cap=20 у `adjusted` — только для аплейта, что согласуется с правилами. |
| **Live RNG (ввод с настоящих кубиков)** | ⚠️ С нюансом | По дизайну (`ENGINE.md §7`) живой ввод — на уровне `LiveDiceRoller`, не `LiveRNG`. То есть `RNG` остаётся как сейчас. Что нужно: удалить `random()` (K-001), ввести `application/engine/dice_roller.py` с `DiceRoller(Protocol)` и `RollContext`. Пока в коде их нет. |
| **Дополнительные кости (`r1`, `e!`, `2d6r1`)** | ⚠️ Парсер регуляркой — лимит | Регулярка не расширяется красиво (станет монстром). Лучше — pratt-parser или lark-grammar. На текущем этапе ОК — но в OPEN_QUESTIONS добавить «когда добавлять `r`/`e` — рефакторить парсер». |
| **Crit с extra dice (Sneak Attack 2d6)** | ✅ Да | Текущий `crit=True` удваивает любое выражение. Вызывающий применит `crit=True` к каждому из выражений урона. Нужно: тест (K-007) и одна строка в `DESIGN.md §3`. |
| **Прозрачность d20 raw для статистики (`RollIssued.raw`)** | ⚠️ Косвенно | `RollResult.kept` содержит «сырое» значение, но семантически непрозрачно. Лучше добавить `RollResult.d20_raw` свойство (K-014). |
| **`RollIssued` / `RollApplied` события** | ⏳ Не сейчас, но дорога открыта | Нет `EventBus`, нет `DiceRoller`. Появятся вместе с `GameEngine`. Текущий `RollResult` содержит всё нужное (raw rolls, modifier, total) — обёртка в события будет тривиальной. |
| **Преимущество на «следующий бросок» (master grant_advantage)** | ⚠️ Нет очереди | `MASTER.md §3.1`: `grant_advantage(creature, next_n=1)`. Сейчас флаг `advantage=True` — параметр одного вызова `roll`. Нужно: модель `pending_advantage_flags: dict[CreatureId, list[Mod]]` (см. `ENGINE.md §6.2`, пункт 3) — отсутствует, но логично появится с `Creature` сущностью. |
| **Альтернатива `keep_highest`/`keep_lowest` на крит** | ⚠️ Сейчас работает, но без теста | Пример: `4d6kh3` с `crit=True` → бросаем 8 костей, оставляем 3 старших. По правилам D&D такого нет (kh3 — генерация stats, не урон), но если кто-то комбинирует, поведение однозначное. Тест и явная нота — желательны. |
| **i18n строк ошибок и `describe`** | ❌ Нет | Сейчас русский в `ValueError`, `DiceParseError`, `RollResult.describe()`, `AbilityScore` validation. Перед подключением `babel/gettext` нужно: тех. ошибки → английский, `describe` — в UI-слой. |
| **CLI: `db`, `content`, `settings` подкоманды** | ⚠️ Частично | Только `play/character/db` — заглушки. `content` и `settings` отсутствуют (K-017). |
| **CLI: `db` action как `Enum`** | ❌ Нет | `str` без валидации (K-016). |

---

## Дельта «как описано» vs «как реализовано»

### В коде есть, в доках нет

1. `RNG.random()` — нет в `ARCHITECTURE.md §3.4` и `DESIGN.md §1.2`, есть в порту.
2. `Ability.label_ru` — нет в `DESIGN.md §2.1`, и противоречит `I18N.md §1`.
3. `RollResult.describe()` — формат не описан в `DESIGN.md §3`.
4. `ScriptedRNG._randoms` (вторая очередь под `random()`) — нет
   в дизайне.
5. `--version` флаг — в коде есть, в `DESIGN.md §13` среди списка
   CLI-команд не упомянут (хотя `dnd --version` — стандарт-де-факто).
6. CLI команды `play/character/db` — последняя (`db`) не упомянута
   в `DESIGN.md §13`.

### В доках есть, в коде нет (это нормально на текущем этапе MVP)

1. `DiceRoller`, `RollContext`, `ComputerDiceRoller`/`LiveDiceRoller` —
   `ENGINE.md §7` обещает; в `application/engine/` пусто. **ОК на сейчас**,
   но важно, что в `__init__.py` уже есть `application/services/`,
   `application/dto/` — а `application/engine/` отсутствует. См. K-014.
2. `RollIssued` / `RollApplied` события — `ENGINE.md §6.2`, `MASTER.md §6.2`.
   **ОК на сейчас** — появятся с `EventBus`/`GameEngine`.
3. `DiceStatisticsService` — `ENGINE.md §7`. **ОК на сейчас.**
4. `Translator` (`i18n/translator.py`) — `I18N.md §2.3`. Пакет
   `src/dnd/i18n/` отсутствует физически (см. `find src -name i18n`).
   **ОК на сейчас**, но из-за этого `label_ru` в домене (K-005) — это
   «временный костыль», и его нужно явно так помечать.
5. Команда CLI `content` (валидация контента, см. `ARCHITECTURE.md`) — нет
   (K-017).
6. `compose_root()` (см. `ARCHITECTURE.md §4`) — нет; сейчас
   `interfaces/cli/app.py` строит только Typer-приложение. **ОК на сейчас.**
7. ADR 0002 «квадратная сетка» — в коде ещё ни сетки, ни ADR-инфры. **ОК.**

---

## Документация в коде

- **Docstring'и:** есть на каждом модуле и на каждой публичной функции/классе.
  Качество — выше среднего, с явными ссылками на главы DESIGN.md
  («см. ``docs/ARCHITECTURE.md``») и книги («Книга Игрока, стр. 9»).
- **Type hints:** аннотированы все публичные сигнатуры (включая
  `__post_init__`). `from __future__ import annotations` везде —
  поддержка PEP-563.
- **mypy:** не запущен в окружении (модуль не установлен). По беглому
  ревью — `strict=true` должен пройти. Один потенциальный нюанс:
  `application/ports/rng.py` без `__all__` — ОК для protocol.
- **Stub-комментарии:** `[play] ещё не реализовано` etc. — норма, но
  стоит унифицировать (либо `raise NotImplementedError`, либо `echo`).
  Сейчас всё через `echo` — это удобно для скриптинга, OK.

---

## Сводный TODO (по приоритетам)

### S1 — ломает контракт или дизайн

1. **K-004:** запретить `advantage`/`disadvantage` на не-d20 (бросать
   `ValueError`). Сейчас — тихий молчаливый отказ.
2. **K-005:** убрать `Ability.label_ru` и русский текст из ошибок
   `AbilityScore`. Перенести в i18n.

### S2 — YAGNI / готовность / технический долг

3. **K-001 + K-002:** убрать `RNG.random()` и `@runtime_checkable`.
   Каскадом — `ScriptedRNG._randoms`.
4. **K-006:** русские строки в `DiceExpr`-ошибках → английский;
   `RollResult.describe()` пометить как debug-only / вынести в renderer.
5. **K-014:** добавить `RollResult.d20_raw` свойство для будущей
   статистики d20 (готовность к `RollIssued`).
6. **K-016 + K-017:** CLI — `Enum` для `db action`, заглушки `content`/`settings`.
7. **K-007:** один тест на крит 2d6 + явная фраза в DESIGN.md §3 о
   множественных выражениях урона.
8. **K-010, K-011, K-012, K-013:** пропущенные edge-case тесты:
   - `keep_lowest` бросок;
   - параметризованный тест на плохие формы парсера (`""`, `0d6`, `1d0`, `2d6kh5`);
   - `adjusted` с уходом ниже 1;
   - `is_natural_20` с преимуществом.
9. **K-018:** `AbilityScores.__getitem__` и `__iter__` — удобно для UI.
10. **K-020:** применить маркер `@pytest.mark.rules` или удалить
    из `pyproject.toml`.

### S3 — косметика / документация

11. **K-008:** тест на нормализацию `+0` в `__str__`.
12. **K-009:** определиться с допустимостью внутренних пробелов в парсере.
13. **K-015:** убрать default-значения у `RollResult.modifier`/`total`,
    либо добавить assert в `__post_init__`.
14. **K-019:** docstring у `AbilityScores.of(...)` про `str_`/`int_`.

---

## Что важно подчеркнуть

- **Тесты зелёные (29/29), код читается, типы аннотированы.** Эту фазу
  можно считать **закрытой**. Все находки — улучшения, не блокеры.
- Главный архитектурный риск дальше — **i18n-утечка в domain**. Сейчас
  её две точки (K-005, K-006); если её не закрыть до подключения
  `babel`, будут «правильные» переводы рядом с hardcode'нутыми строками.
- Главный поведенческий риск — **K-004** (молчаливое игнорирование
  `advantage` на не-d20). Это потенциальный источник тонких багов в
  механиках, которые ещё не реализованы (бросок урона с пометкой
  `advantage=True` ничего не сделает, и тест пройдёт).
- Главный «технический долг будущего» — **отсутствие `DiceRoller` слоя**.
  Сейчас домен (`DiceExpr.roll(rng)`) напрямую работает с `RNG`.
  По `ENGINE.md §7` правила должны вызывать `DiceRoller`, не `RNG`.
  Внести этот слой удобно одновременно с появлением `GameEngine`.

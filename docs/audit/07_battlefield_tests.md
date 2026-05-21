# Audit 07: тесты Battlefield и Terrain

Независимый ревью **тестов** в `tests/unit/domain/test_battlefield.py`
и `tests/unit/domain/test_terrain.py` против их кода и правил книги.
Дата: 2026-05-21. Ревьюер: внешний.

Источники правды:

- `docs/ENGINE.md` §2 (квадратная сетка, 5 фут, 8 соседей, Chebyshev,
  несколько существ на клетке).
- `docs/VISIBILITY.md` §1, §3, §7.1, §7.3 (LoS Брезенхэма, cover,
  правило «угла стены»).
- `docs/ADR/0002-square-grid.md` (решение по квадратам).
- `docs/OPEN_QUESTIONS.md` Q1 (множественные существа), Q24
  (mutable + snapshot).
- «Книга Игрока 2024»: стр. 23 («Перемещение», труднопроходимая
  местность), стр. 24 («Размер существа», «Перемещение около других
  существ»), стр. 25 («Совершение атаки», «Укрытие»).

Запуск: `pytest tests/unit/domain/test_battlefield.py
tests/unit/domain/test_terrain.py` — **59 passed**.

## Резюме

- Архитектурных замечаний: **3** (S0=0, S1=1, S2=2)
- Расхождений с книгой: **2** (S0=0, S1=1, S2=1)
- Пропущенных тестов: **7** (S0=0, S1=3, S2=4)
- Качество тестов: **3** замечания (S0=0, S1=1, S2=2)

Общая оценка — набор тестов хороший: покрытие осмысленное, разделение
«rules vs property vs unit» прозрачное, упрощения движка явно
задокументированы. Главные проблемы — **TR-G001** (нет ни одного теста
на cover при WALL «между и на цели» одновременно, что важно при
проектировании Action.attack: реализация возвращает разный cover для
случаев «WALL посередине» = TOTAL и «WALL ровно на цели» = NONE,
поведение неинтуитивно и нигде не зафиксировано юнит-тестом) и
**TR-A001** (часть тестов на занятость и `creatures_at_returns_immutable_snapshot`
проверяют тривиальные свойства типа tuple, а не контракт). Ни одна из
находок не критична для MVP, но S1 стоит закрыть до подключения
Action.attack.

## Что точно хорошо

1. **Сценарные тесты с книжным контекстом** — `test_book_scenario_archer_behind_wall_blocked`
   и `test_book_scenario_archer_behind_high_cover_can_shoot_with_cover`:
   читаются как описание правила, привязаны к стр. 25 книги. Это лучший
   стиль для подсистемы боя.
2. **Корректный уровень изоляции от Square** — Battlefield-тесты не
   повторяют test_square.py (chebyshev, neighbors, distance), а тестируют
   только то, что добавляет Battlefield (in_bounds, террейн, занятость).
3. **Out-of-bounds → wall-like** — TR-семантика «за границей карты = стена»
   зафиксирована тестом (`test_terrain_out_of_bounds_is_wall_like`).
   Это документация контракта через тест, не дублирование Terrain.
4. **Cover-приоритет** — `test_cover_picks_strongest_along_line` точно
   соответствует правилу книги стр. 25 «несколько источников — берётся
   самое сильное», с ясной геометрией.
5. **Reach 5/10 ft с конкретными ожиданиями (8/24 клетки)** — это
   именно то, что нужно проверить на уровне Battlefield, а не на Square.
6. **Маркер `@pytest.mark.rules` на ключевых правилах книги** —
   проставлен для cover, reach, LoS-stena, scenarii.
7. **DIFFICULT отделён от cover/LoS** — `test_difficult_terrain_does_not_affect_los_or_cover`
   фиксирует, что разный «слой» свойств Terrain не смешивается. Полезно
   против регрессий.
8. **HIGH_COVER vs WALL семантика** — есть и для LoS
   (`test_los_through_high_cover_not_blocked`), и для cover. Это пара
   тестов, отделяющая «непроходимо ≠ блокирует LoS».
9. **Property-based + детерминированные unit-тесты сосуществуют** —
   границы карты в `_within_bf` (0..19 при size 20) выбраны корректно,
   стратегии не выходят за рамки.
10. **Terrain.frozen + hashable** — оба свойства проверены отдельно
    (`test_terrain_is_frozen`, `test_terrain_is_hashable`), что важно
    для флайвейт-стиля из docstring.

## Найденные проблемы

### TR-A001. `creatures_at_returns_immutable_snapshot` тестирует tuple, а не контракт
**Тип:** architecture / quality
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_battlefield.py:178-186`
**Проблема:** тест сводится к двум проверкам — что результат это
`tuple` и что повторный запрос даёт ту же последовательность. Первое —
тавтология (тип возвращаемого значения и так указан в коде); второе —
не тестирует «иммутабельность снапшота», а тестирует, что состояние не
изменилось между двумя соседними вызовами без мутаций. Реальный
контракт — «вызывающий не может повлиять на внутренний `_occupancy`
через возвращённое значение» — не проверяется. Доказать это можно
только косвенно: попытаться приписать `.append`/`__setitem__`/`+=` к
снапшоту и убедиться, что внутреннее состояние не меняется.
**Рекомендация:** заменить тест на: получить снапшот, попытаться
изменить его (`snap + (CreatureId("z"),)` — это даст новый tuple, но
не должен затронуть внутренний список), затем повторно прочитать
`creatures_at` и убедиться, что результат не изменился. Или просто
удалить тест — обещание «иммутабельности» уже даёт сам тип `tuple`.

### TR-A002. `test_property_los_symmetric_on_empty_map` не доказывает симметрию реального алгоритма
**Тип:** architecture / quality
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_battlefield.py:344-349`
**Проблема:** на **пустой** карте LoS всегда True для любой пары
точек — независимо от Брезенхэма. Этот тест не способен поймать
ассиметрию алгоритма (если бы она была); он проверяет тождество
`True == True`. Симметрия — реальное свойство — должна тестироваться
**на карте со случайными препятствиями**: тогда асимметричный Брезенхэм
(зависящий от направления обхода) развалит тест.
**Рекомендация:** усилить стратегию: hypothesis-стратегия генерирует
несколько случайных WALL-клеток (например, 0..5 штук в `_within_bf×_within_bf`),
затем проверяет `los(a,b) == los(b,a)`. Это и есть честный property-тест.
Сейчас комментарий («LoS симметричен на пустой карте без препятствий») —
честный, но проверяемое свойство тривиально.

### TR-A003. `test_property_cover_no_obstacles_is_none` — дубликат двух unit-тестов
**Тип:** architecture
**Серьёзность:** S1
**Где:** `tests/unit/domain/test_battlefield.py:352-357`
**Проблема:** на пустой карте cover всегда NONE — это уже зафиксировано
двумя unit-тестами (`test_cover_no_obstacles_is_none`,
`test_cover_same_square_is_none`). Property-вариант на пустой карте
ничего нового не добавляет, но платит за hypothesis-сэмплинг временем
прогона. Это та же проблема, что TR-A002, — псевдо-property.
**Рекомендация:** либо удалить, либо переделать в осмысленный property
(например, «cover симметричен относительно перестановки attacker/target
при отсутствии существ» — этот инвариант сейчас в коде есть и нетривиален).

### TR-R001. Cover при цели на WALL-клетке возвращает NONE — не книжно
**Тип:** rules
**Серьёзность:** S1
**Где:** `src/dnd/domain/entities/battlefield.py:221-231`, тест
`test_cover_endpoint_terrain_does_not_count`
(`tests/unit/domain/test_battlefield.py:281-285`)
**Проблема:** реализация `cover_against` исключает endpoint-клетки
(attacker_pos и target_pos), что для LoS оправдано книгой («вы видите
то, на что навели» — стр. 25). Но для **cover** это даёт странный
результат: если стена ровно на клетке цели, метод возвращает
`CoverLevel.NONE`. По книге же — если цель стоит «за полной защитой»,
её **нельзя выбрать целью** (`CoverLevel.TOTAL`, `can_be_targeted=False`).
Тест явно фиксирует поведение `NONE` (как cover на endpoint не
считается); это **симметрично с LoS, но не симметрично с книгой**:
LoS-эндпоинт — «вижу что-то на клетке-цели сквозь полу-прозрачную
плёнку», а cover-эндпоинт — это другой вопрос.

Сейчас это компенсируется на уровне выбора цели: Action.attack должен
запрещать выбор клетки с непроходимым террейном как цели. Но тест
`test_cover_endpoint_terrain_does_not_count` использует именно
`HIGH_COVER` (а не WALL), и для high-cover поведение «cover не считается
на endpoint, потому что цель стоит **внутри** high-cover, а не за ним» —
это терпимо. Для WALL — это не покрыто отдельным тестом, и комментарий
«как и для LoS» сводит два разных правила в одно.
**Рекомендация:** разделить два кейса: (а) endpoint = HIGH_COVER/LOW_COVER —
действительно NONE (цель внутри обвала/парапета); добавить
явный тест с пояснением; (б) endpoint = WALL — на уровне
Action.attack эту цель нельзя выбрать. Это можно зафиксировать тестом
**на уровень Action.attack**, а на уровне Battlefield добавить
комментарий «WALL-эндпоинт в cover_against — undefined; вызывающий
обязан валидировать цель». Альтернатива — сделать cover_against
возвращающим TOTAL, если `target` в непроходимой клетке.

### TR-R002. «Правило угла стены» (книжное упрощение wargame) не реализовано — заявлено как осознанное упрощение, но не проверено тестом-документацией
**Тип:** rules (документация в коде)
**Серьёзность:** S2
**Где:** `src/dnd/domain/entities/battlefield.py:287-291` (docstring
`_bresenham_line`), `docs/VISIBILITY.md` §7.1
**Проблема:** код и документация явно описывают это как
**сознательное упрощение MVP**: «правило угла стены не моделируем,
стандартный Брезенхэм даёт диагональ проходит». Это нормальная позиция
MVP. Однако в тесте этот контракт **не зафиксирован**. Если кто-то
позже «улучшит» алгоритм (добавит проверку обеих ортогоналей при
диагональном переходе) — упадёт другой тест, но останется неясно, что
именно упрощение было намеренным.
**Рекомендация:** добавить один декларативный тест с поясняющим именем
вроде `test_los_corner_of_wall_simplification_no_block`:
```python
@pytest.mark.rules
def test_los_corner_of_wall_is_not_blocked_simplified() -> None:
    """MVP-упрощение (VISIBILITY.md §7.1): диагональный LoS через
    «угол» из двух ортогональных стен — НЕ блокирован. Полное
    wargame-правило «обе ортогонали → блок» — пост-MVP."""
    bf = Battlefield(5, 5)
    bf.set_terrain(Square(1, 0), WALL)
    bf.set_terrain(Square(0, 1), WALL)
    # Атакующий (0,0), цель (2,2); линия идёт через (1,1) — FLOOR
    assert bf.line_of_sight(Square(0, 0), Square(2, 2)) is True
```
Это пометит упрощение, и если кто-то реализует правило угла — тест
обоснованно сломается и заставит обновить документацию.

### TR-G001. Нет теста для пары «WALL посередине + endpoint = WALL»
**Тип:** gap
**Серьёзность:** S1
**Где:** недостаёт в `tests/unit/domain/test_battlefield.py`
**Проблема:** cover_against тестируется только для LOW/HIGH cover на
endpoint и WALL посередине. Случай «WALL и в середине, и на цели» —
не проверен. Это важно для будущего Action.attack, который должен
понять «можно ли вообще атаковать клетку с WALL».
**Рекомендация:** добавить тест `test_cover_wall_between_returns_total`
и `test_cover_wall_on_target_documented_as_none_at_battlefield_level`
(или TOTAL, в зависимости от выбранного решения по TR-R001).

### TR-G002. cover_against / line_of_sight для out-of-bounds координат не валидируется
**Тип:** gap
**Серьёзность:** S1
**Где:** `src/dnd/domain/entities/battlefield.py:189`, `:212`
**Проблема:** `line_of_sight(Square(-1,-1), Square(2,2))` и
`cover_against(...)` молча работают (Брезенхэм пройдёт по клеткам,
часть из которых OOB → wall-like → блок LoS). Это даёт «магическую»
семантику: атакующий «извне карты» обычно видит цель в углу карты, но
не дальше. Поведение не покрыто ни тестом, ни ValueError-валидацией.
Если контракт — «вызывающий должен передавать только in_bounds»,
нужна явная проверка. Если контракт — «OOB допустим и трактуется как
wall-like» — нужен явный тест.
**Рекомендация:** выбрать политику и зафиксировать тестом. По духу
текущего кода (terrain_at для OOB возвращает _OUT_OF_BOUNDS) — второй
вариант последовательнее: добавить `test_los_attacker_out_of_bounds_treated_as_wall`.

### TR-G003. Cover в упор (attacker и target — соседи) не покрыт явным тестом
**Тип:** gap
**Серьёзность:** S2
**Где:** недостаёт
**Проблема:** при `is_adjacent(attacker, target)` промежуточных
клеток нет, и cover должен быть `NONE` (книга стр. 25 — cover только
от «препятствия между»). Это базовый кейс для melee-атаки и его стоит
зафиксировать.
**Рекомендация:** добавить `test_cover_adjacent_target_always_none`
для нескольких направлений (ортогональ + диагональ).

### TR-G004. Battlefield 1×1 — крайний случай не покрыт
**Тип:** gap
**Серьёзность:** S2
**Где:** недостаёт
**Проблема:** 1×1 — валидный размер по конструктору (`>= 1`), но
поведение `threatens_squares` (пустое множество), `in_bounds` (только
(0,0)) и т.п. не зафиксировано. Это полезный canary-test для будущих
больших-существ (которые могут «не помещаться»).
**Рекомендация:** один тест `test_battlefield_1x1_minimal_case`,
проверяющий: in_bounds(0,0)=True/(1,0)=False; place+threatens_squares
возвращает frozenset().

### TR-G005. place→remove→place того же ID — не покрыт явным тестом
**Тип:** gap
**Серьёзность:** S2
**Где:** недостаёт
**Проблема:** в условии задания запрос «place→remove→place того же
ID — корректно?». Поведение в коде корректное (проверил вручную), но
теста нет. Это важный сценарий «существо вышло из боя и вернулось»,
который стоит зафиксировать.
**Рекомендация:** добавить
```python
def test_place_remove_place_same_id_works() -> None:
    bf = Battlefield(10, 10)
    a = CreatureId("a")
    bf.place_creature(a, Square(1, 1))
    bf.remove_creature(a)
    bf.place_creature(a, Square(2, 2))
    assert bf.position_of(a) == Square(2, 2)
    assert bf.creatures_at(Square(1, 1)) == ()
    assert bf.has_creature(a) is True
```

### TR-G006. Порядок в `creatures_at` после `remove_creature` среднего из 3 — не зафиксирован
**Тип:** gap
**Серьёзность:** S2
**Где:** недостаёт
**Проблема:** docstring `creatures_at` говорит «порядок — по времени
постановки». При remove среднего — порядок должен сохраниться. Это
тонкость, которую легко сломать рефакторингом `_occupancy` (например,
переход на dict-вместо-list для уникальности).
**Рекомендация:**
```python
def test_creatures_at_preserves_insertion_order_after_remove_middle() -> None:
    bf = Battlefield(5, 5)
    for cid in ("a", "b", "c"):
        bf.place_creature(CreatureId(cid), Square(2, 2))
    bf.remove_creature(CreatureId("b"))
    assert bf.creatures_at(Square(2, 2)) == (CreatureId("a"), CreatureId("c"))
```

### TR-G007. Книжное правило «проход сквозь враждебного запрещён» (стр. 24) — нигде не зафиксировано
**Тип:** gap (документация контракта)
**Серьёзность:** S2
**Где:** `src/dnd/domain/entities/battlefield.py:14-18` (docstring говорит
«это на уровне движения, не Battlefield»)
**Проблема:** docstring явно делегирует это правило на Action.Move.
Это разумно архитектурно. Но это значит: при ревью Action.Move нужно
будет помнить, что **Battlefield само по себе не блокирует**
postановку нескольких враждебных существ на одну клетку — и `Action.Move`
обязан это проверять перед `move_creature()`. Сейчас тест
`test_multiple_creatures_in_same_square` фиксирует разрешённость, но
не оставляет «маркера» о книжном ограничении.
**Рекомендация:** добавить в docstring теста-разрешения ссылку на
PHB-2024 стр. 24 «Перемещение около других существ» и явное «ограничение
по враждебности — на Action.Move, см. task #NN». Это не код, но
читатель тестов получит контекст.

### TR-Q001. Часть rules-тестов без `@pytest.mark.rules`, хотя цитируют книгу
**Тип:** quality
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_battlefield.py:217-222`
(`test_los_not_blocked_by_endpoint_terrain` — цитирует «вы видите то,
на что навели»), `:225-228` (`test_los_blocked_by_closed_door` —
книга стр. 25 «дверь»), `:271-273` (`test_cover_no_obstacles_is_none` —
книга стр. 25), `:281-285` (`test_cover_endpoint_terrain_does_not_count` —
книга стр. 25), `:406-412` (`test_difficult_terrain_does_not_affect_los_or_cover` —
книга стр. 23, в самом docstring сказано «не даёт cover»),
`:397-403` (`test_book_scenario_archer_behind_high_cover_can_shoot_with_cover` —
книжный сценарий без `rules`)
**Проблема:** маркер `@pytest.mark.rules` проставлен непоследовательно
— часть «книжных» тестов им помечена, часть нет, без видимой логики.
Это мешает `pytest -m rules` собрать всё, что прибито к книге.
**Рекомендация:** проставить `@pytest.mark.rules` всем тестам, чей
docstring/имя ссылается на книжное правило. Минимум — 6 перечисленных.

### TR-Q002. Hypothesis-диапазоны для координат — широковаты для 20×20
**Тип:** quality
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_battlefield.py:340-341`
**Проблема:** `_within_bf = st.integers(min_value=0, max_value=19)`
для `Battlefield(20, 20)` — корректно. Но в
`test_property_threatens_stays_in_bounds(centre=_squares)` существо
размещается в любой in_bounds-клетке, и Hypothesis может выбирать
тысячи комбинаций, из которых 80% — внутренние (тривиальный случай).
Не баг, но эффективная мощность теста падает. Это не критично, но
для `test_property_los_symmetric_on_empty_map` (как уже сказано в
TR-A002) — это вообще делает свойство тривиальным.
**Рекомендация:** если property-тестов будет больше, добавить
hypothesis-композицию, которая «больше любит» границу: например,
`st.one_of(corners_strategy, interior_strategy)` с весами. Сейчас
терпимо, но стоит держать в голове.

### TR-Q003. `test_set_terrain_out_of_bounds_raises` использует `Square(10, 10)` для карты 5×5 — лучше границы
**Тип:** quality
**Серьёзность:** S2
**Где:** `tests/unit/domain/test_battlefield.py:83-86`
**Проблема:** проверка «вне границ» использует точку `(10, 10)`,
далёкую от границы 5×5. Самые подлые баги — на границе («off-by-one»:
координата `5` для карты 5×5). Этот случай не покрыт. Аналогично
`test_placing_out_of_bounds_raises` (`:126-129`).
**Рекомендация:** дополнить параметризацией:
```python
@pytest.mark.parametrize("coord", [Square(5, 0), Square(0, 5), Square(-1, 0), Square(0, -1), Square(10, 10)])
def test_set_terrain_out_of_bounds_raises(coord: Square) -> None: ...
```

## Сводный TODO (по приоритету)

**S1 (закрыть до Action.attack):**

1. TR-R001 — разделить семантику cover на endpoint для WALL vs HIGH_COVER;
   решить, что возвращать (NONE/TOTAL); зафиксировать тестом или
   делегировать на Action.attack явно (комментарий + тест-документация).
2. TR-G001 — тест «WALL посередине + WALL на цели» (вытекает из TR-R001).
3. TR-G002 — определить контракт LoS/cover при OOB-координатах и
   зафиксировать тестом.
4. TR-A003 — заменить или удалить псевдо-property
   `test_property_cover_no_obstacles_is_none`.

**S2 (улучшение качества, без блокеров):**

5. TR-A001 — переработать `test_creatures_at_returns_immutable_snapshot`
   или удалить.
6. TR-A002 — усилить `test_property_los_symmetric_on_empty_map`:
   добавить случайные стены в hypothesis-стратегию.
7. TR-R002 — добавить документирующий тест об упрощении «угла стены».
8. TR-G003…TR-G006 — добавить пропущенные единичные тесты (cover в
   упор, 1×1, place-remove-place, порядок после remove среднего).
9. TR-G007 — расширить docstring `test_multiple_creatures_in_same_square`
   ссылкой на книгу и таск Action.Move.
10. TR-Q001 — расставить `@pytest.mark.rules` последовательно.
11. TR-Q003 — параметризовать out-of-bounds-тесты границей.

**Не делать сейчас:**

- TR-Q002 — частный вопрос, hypothesis-стратегии для bias к границам
  стоит обсуждать только при росте property-набора.

---

Все находки — на свежем коде после `tests/unit/domain/test_battlefield.py`
и `tests/unit/domain/test_terrain.py`. Тесты сейчас все зелёные
(59 passed), правки не сломают существующий код, только усилят
гарантии и документацию.

---

## Применённые фиксы (2026-05-21)

**S1 — закрыто полностью:**

* **TR-R001 / TR-G001** — `cover_against` теперь возвращает `TOTAL`,
  если `target_pos` стоит на клетке с `Terrain.cover == TOTAL` (стена,
  закрытая дверь). Зафиксировано тестами
  `test_cover_wall_on_target_is_total`,
  `test_cover_wall_between_and_on_target_returns_total`,
  `test_cover_closed_door_on_target_is_total`. Семантика HIGH_COVER на
  endpoint = `NONE` сохранена (цель внутри парапета) и переименована в
  `test_cover_high_cover_on_target_endpoint_is_none` с явным docstring.
* **TR-G002** — `line_of_sight` и `cover_against` явно бросают
  `ValueError` при OOB endpoint'ах (метод `_require_in_bounds`). Тесты
  `test_los_out_of_bounds_raises`, `test_cover_out_of_bounds_raises`
  параметризованы по граничным точкам. OOB-семантика `terrain_at`
  оставлена wall-like — это **внутренний** контракт для обхода
  Брезенхэмом, что задокументировано в обновлённом docstring
  `test_terrain_out_of_bounds_is_wall_like`.
* **TR-A003** — псевдо-property `test_property_cover_no_obstacles_is_none`
  заменён осмысленным `test_property_cover_symmetric_with_random_walls`:
  на карте со случайными стенами проверяется `cover(a,b) == cover(b,a)`.

**Дополнительно (bug, найденный hypothesis при усилении property-теста):**
стандартный Брезенхэм направленно-зависим — `los(a,b) != los(b,a)` на
карте с одной диагональной стеной. Это реальное нарушение книжной
симметрии. Фикс: helper `_canonical_segment` сортирует endpoint'ы
лексикографически перед обходом — `los` и `cover_against` теперь
гарантированно симметричны. Зафиксировано документом VISIBILITY.md
§7.1 и property-тестом `test_property_los_symmetric_with_random_walls`.

**S2 — закрыто частично (значимые пункты):**

* **TR-A001** — `test_creatures_at_returns_immutable_snapshot` заменён
  на `test_creatures_at_snapshot_does_not_leak_internal_list`: добавляем
  существо после получения снапшота и проверяем, что снапшот не
  изменился — это ловит регрессию «вернули `list` напрямую».
* **TR-A002** — property-LoS усилен: добавлены случайные стены
  (`_wall_set`), что даёт нетривиальные конфигурации и реально проверяет
  симметрию алгоритма (см. найденный баг выше).
* **TR-R002** — добавлен документирующий тест
  `test_los_corner_of_wall_is_not_blocked_simplified`: фиксирует
  MVP-упрощение «угла стены», ссылается на VISIBILITY.md §7.1.
* **TR-G003** — `test_cover_adjacent_target_always_none`,
  параметризован по ортогональным и диагональным соседям. Важно для
  melee-сценариев.
* **TR-G004** — `test_battlefield_1x1_minimal_case`.
* **TR-G005** — `test_place_remove_place_same_id_works`.
* **TR-G006** — `test_creatures_at_preserves_insertion_order_after_remove_middle`.
* **TR-G007** — docstring `test_multiple_creatures_in_same_square`
  расширен ссылкой на PHB-2024 стр. 24 и явным указанием, что
  валидация «враждебности» — на `Action.Move`.
* **TR-Q001** — добавлены `@pytest.mark.rules` на
  `test_los_not_blocked_by_endpoint_terrain`,
  `test_los_blocked_by_closed_door`,
  `test_cover_no_obstacles_is_none`,
  `test_book_scenario_archer_behind_high_cover_can_shoot_with_cover`,
  `test_difficult_terrain_does_not_affect_los_or_cover`.
* **TR-Q003** — `test_set_terrain_out_of_bounds_raises` и
  `test_placing_out_of_bounds_raises` параметризованы по граничным
  off-by-one координатам.

**Не сделано (решение «не делать сейчас»):**

* **TR-Q002** — hypothesis-композиция для bias к границам.
  Решение: текущий property-набор это не требует; вернёмся, если он
  вырастет ещё на 2-3 теста.

**Итоговые цифры (после фиксов):**

* pytest:   **445 passed** (+24)
* tests/unit/domain/test_battlefield.py: **69 passed** (+21)
* ruff:     All checks passed
* mypy:     Success: no issues found in 64 source files
* coverage: **98.55%** (+0.08)

**Реальный баг, который дал аудит:** TR-A002. Усилив property-тест,
hypothesis нашёл нарушение симметрии LoS из-за направленной природы
Брезенхэма. Это **не было видно** на старых тестах с конкретной
геометрией (которая случайно использовала «симметричные» направления).
Подтверждает ценность property-based: бесполезный тест-тождество не
ловит, осмысленный — ловит.

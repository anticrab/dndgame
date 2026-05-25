# Этап P2: AoE-заклинания (конфигурируемые зоны) — Design

**Дата:** 2026-05-25
**Автор:** Maxim Lokotkov (github.com/anticrab)
**Статус:** черновик на ревью

---

## 1. Контекст и мотивация

P1 дал движок заклинаний (data-driven `Spell` + реестр эффект-хендлеров) для
single-target/self. P2 добавляет **зоны поражения (AoE)** с богатой,
**конфигурируемой** моделью: разные формы (круг/конус/линия, расширяемо) и два
способа задания источника:

- **от персонажа** (эманация): волна/конус/луч от клетки кастера в выбранном
  направлении (8 сторон, включая диагонали) — Thunderwave, Burning Hands;
- **в точку** (снаряд): заклинание летит в выбранную клетку в пределах
  дальности и «взрывается» там — Fireball.

Принцип расширяемости (memory `feedback-extensibility-registries`): формы зоны —
через **реестр shape-резолверов** (open/closed), геометрия — чистые функции.
Новая форма добавляется резолвером + регистрацией, без правки `CastSpellAction`.

**Мультитаргет** (выбор N отдельных целей — Bless, распределение Magic Missile)
— механически другое (набор целей, не зона) и вынесен в отдельный срез **P2b**.

## 2. Скоп

**Включено в P2:**

- Расширение `TargetingSpec`: `origin: OriginMode`, `shape: AreaShape`,
  `radius_ft`, `length_ft` (+ существующий `area_radius_ft` переименовать/
  согласовать).
- Геометрия на квадратной сетке (чистые функции): круг (chebyshev-диск), линия,
  конус.
- `AreaShapeRegistry` + резолверы CIRCLE/CONE/LINE.
- `CastSpellAction._resolve_targets` для AREA (origin + direction → клетки →
  существа; friendly fire включён).
- `CastSpellParams`/`CastSpellIntent`: `target_point`, `direction`.
- TUI `BattleMode.AREA`: выбор точки (at-point) и направления (from-caster) с
  превью задетых клеток.
- 3 заклинания: Fireball (at-point круг), Burning Hands (from-caster конус),
  Lightning Bolt (from-caster линия) — все SAVE.
- docs SPELLS.md + ROADMAP.

**НЕ в P2 (отложено):**

- Мультитаргет pick-N (Bless, распределение Magic Missile) → **P2b**.
- Блокировка зоны стенами/LoS внутри AoE (в P2 — зона по геометрии без учёта
  препятствий; задел в резолвере есть). Уточнение — позже.
- Половина урона союзникам / «умные» зоны без friendly fire, спасброски с
  укрытием — позже.

## 3. Ключевые решения

### 3.1. Три независимые оси конфигурации зоны (data-driven)

`TargetingSpec` (domain/values/spell.py) для `kind=AREA`:
```python
class OriginMode(StrEnum):
    FROM_CASTER = "from_caster"   # зона от клетки кастера в направлении
    AT_POINT = "at_point"         # зона вокруг выбранной точки (в range)

class AreaShape(StrEnum):
    CIRCLE = "circle"             # chebyshev-диск радиуса radius_ft/5
    CONE = "cone"                 # от origin в direction, длина length_ft/5
    LINE = "line"                 # луч от origin в direction, длина length_ft/5

@dataclass(frozen=True, slots=True)
class TargetingSpec:
    kind: TargetKind
    max_targets: int = 1
    # AoE (P2):
    origin: OriginMode = OriginMode.AT_POINT
    shape: AreaShape | None = None
    radius_ft: int = 0            # CIRCLE
    length_ft: int = 0            # CONE / LINE
```
Валидация (`__post_init__`): `kind=AREA` требует `shape`; CIRCLE → radius_ft>0;
CONE/LINE → length_ft>0; CONE/LINE обычно FROM_CASTER (directional). Поле
`area_radius_ft` из P1 заменяется на `radius_ft` (в P1 не использовалось — без
миграции).

### 3.2. Геометрия — чистые функции (domain/values/geometry.py)

```python
def circle_squares(center: Square, radius_sq: int) -> frozenset[Square]
def line_squares(origin: Square, direction: Direction, length_sq: int) -> frozenset[Square]
def cone_squares(origin: Square, direction: Direction, length_sq: int) -> frozenset[Square]
```
- круг = `center.chebyshev_disk(radius_sq)` (уже есть);
- линия = клетки от origin по дельте `Direction` на `length_sq` шагов (origin не
  включается; ширина 1);
- конус = аппроксимация на сетке: на расстоянии k (1..length) по направлению
  включаются клетки шириной ~`2k-1` (расширяется от вершины). Точную формулу
  фиксируем тестами по клеткам в P2-2.

Футы→клетки: `radius_sq = radius_ft // 5`, `length_sq = length_ft // 5`.
`Direction → (dx,dy)` — helper в geometry (дельты как в `direction._BY_DELTA`).

### 3.3. Реестр shape-резолверов (open/closed)

`application/engine/spells/area/`:
```python
class AreaShapeResolver(Protocol):
    def squares(self, origin: Square, direction: Direction | None,
                spec: TargetingSpec, battlefield: Battlefield) -> frozenset[Square]: ...

class AreaShapeRegistry:  # как SpellEffectRegistry
    register(shape, resolver); get(shape); __contains__

def default_area_shape_registry() -> AreaShapeRegistry  # CIRCLE/CONE/LINE
```
Резолверы (`CircleResolver`/`ConeResolver`/`LineResolver`) зовут geometry-функции;
`battlefield` передаётся для будущей блокировки стенами (в P2 не используется).
**Новая форма = новый резолвер + register**, без касания CastSpellAction.

### 3.4. Резолвинг целей в `CastSpellAction`

`_resolve_targets` для `kind=AREA`:
1. origin square: `caster.pos` (FROM_CASTER) или `params.target_point` (AT_POINT);
2. `squares = area_registry.get(spec.shape).squares(origin, params.direction, spec, bf)`;
3. цели = все существа, чья клетка ∈ squares (и живые) — **включая союзников и
   самого кастера** (friendly fire). Возвращается tuple.

`can_perform_against` для AREA: AT_POINT — `target_point` задан и в пределах
`range_ft` от кастера; FROM_CASTER — `direction` задан. Слот/экономика — как P1.

`CastSpellParams` / `CastSpellIntent` расширяются:
`target_point: Square | None = None`, `direction: Direction | None = None`
(в дополнение к `target_id` для SINGLE). Резолвер целей выбирается по
`spec.kind`/`spec.shape` — без switch в Action (делегирование реестру).

### 3.5. TUI — `BattleMode.AREA` с превью

Новый mode-handler (`battle_modes/area_mode.py`, через `ModeHandler` Protocol):
- **AT_POINT**: курсор свободно двигается по полю (clamp в границы + проверка
  range), превью = задетые клетки (резолвер) подсвечиваются; Enter →
  `CastSpellIntent(target_point=cursor)`; Esc — отмена.
- **FROM_CASTER**: стрелки/клавиши выбирают одно из 8 направлений; превью рисует
  форму от кастера; Enter → `CastSpellIntent(direction=dir)`.
BattleScreen при касте AoE-заклинания входит в `AREA` mode (вместо `TARGET`),
зная `spec` выбранного заклинания. Превью использует тот же `AreaShapeRegistry`.

## 4. Поток данных (Fireball, happy path)

```
[1] Fireball → BattleScreen видит spec: AREA/AT_POINT/CIRCLE r=10ft
 → BattleMode.AREA: курсор на клетку в range 150ft, превью круга r=2
 → Enter → CastSpellIntent(spell_id=fireball, target_point=(x,y))
 → GameRunner._do_cast → CastSpellAction
 → _resolve_targets: circle squares вокруг точки → 3 существа в зоне
 → SaveSpellHandler.apply(caster, (3 цели), spell, ctx)
 → каждый кидает DEX-save vs DC; урон half/full; DamageDealt на каждого
```

## 5. Инварианты

1. Новая форма зоны добавляется резолвером + регистрацией, без правки
   `CastSpellAction`/`_resolve_targets` (open/closed).
2. Геометрия — чистые функции (domain), детерминирована, тестируется по клеткам.
3. AREA-зона бьёт всех живых существ в клетках (friendly fire); урон/save идёт
   через существующие хендлеры (tuple целей) — death-saves/CORPSE (Q) работают.
4. AT_POINT: точка в пределах range; FROM_CASTER: обязательно direction.
5. Все 1212 тестов зелёные; backward-compat (P1 single/self-заклинания
   используют `_resolve_targets` без изменений семантики).

## 6. Тестирование

- geometry: круг/линия/конус по клеткам для разных направлений (вкл. диагонали),
  граничные (длина 1, у края поля).
- AreaShapeRegistry: get/contains; новая форма регистрируется.
- `_resolve_targets` AREA: правильный набор существ (friendly fire), AT_POINT vs
  FROM_CASTER origin.
- CastSpellAction AoE: несколько целей получают save+урон; can_perform_against
  (range для at-point, обязательность direction).
- TUI pilot: `BattleMode.AREA` at-point (курсор+preview+Enter) и from-caster
  (направление+preview).
- регрессия: pytest -q + mypy strict + ruff.

## 7. Декомпозиция

- **P2-1** `OriginMode`/`AreaShape` + расширение `TargetingSpec` + валидация.
- **P2-2** geometry: circle/line/cone (чистые функции) + тесты по клеткам.
- **P2-3** `AreaShapeRegistry` + резолверы + `default_area_shape_registry`.
- **P2-4** `CastSpellParams`/`CastSpellIntent` (target_point/direction) +
  `_resolve_targets` AREA + `can_perform_against` AREA.
- **P2-5** 3 заклинания (Fireball/Burning Hands/Lightning Bolt) в spells.yaml +
  смоук-каст с несколькими целями (friendly fire).
- **P2-6** TUI `BattleMode.AREA` — at-point (точка + preview).
- **P2-7** TUI from-caster directional (направление + preview) + проброс в
  BattleScreen.
- **P2-8** docs SPELLS.md + ROADMAP.
- Финальный независимый аудит P2 (упор на маскирующие тесты, корректность
  геометрии, open/closed).

## 8. Definition of Done

- `dnd play --tui`: PC-кастер выбирает Fireball → целит точку → круг-превью →
  каст бьёт всех в зоне (включая союзников); Burning Hands/Lightning Bolt —
  выбор направления от себя с превью.
- Новая форма зоны = резолвер + строка регистрации (проверено в коде/доке).
- 1212 + новые тесты зелёные; mypy strict / ruff clean.
- `docs/SPELLS.md` описывает конфигурацию зон; ROADMAP помечает P2.

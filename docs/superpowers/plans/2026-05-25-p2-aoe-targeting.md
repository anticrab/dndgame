# Этап P2: AoE-заклинания — Implementation Plan

> REQUIRED SUB-SKILL: subagent-driven-development или executing-plans. Шаги — TDD.

**Goal:** Конфигурируемые зоны поражения (круг/конус/линия; from-caster/at-point) через реестр shape-резолверов + чистую геометрию; 3 AoE-заклинания; TUI-выбор зоны с превью.

**Architecture:** `TargetingSpec` расширяется осями origin/shape/size (data-driven). Геометрия — чистые функции (domain). `AreaShapeRegistry` (open/closed) резолвит клетки. `CastSpellAction._resolve_targets` для AREA берёт существ в клетках (friendly fire) и делегирует существующим эффект-хендлерам. TUI `BattleMode.AREA` рисует превью.

**Tech Stack:** Python 3.12, pydantic v2, Textual, pytest, mypy strict, ruff.

**Конвенции:** коммиты `Maxim Lokotkov`/`anticrab@users.noreply.github.com`; рус. доки/комментарии; после каждого таска `python3 -m pytest -q && mypy src/ && ruff check`; git push/reset --hard/rebase запрещены.

Спека: docs/superpowers/specs/2026-05-25-p2-aoe-targeting-design.md.

## Образцы
- `domain/values/square.py` — `chebyshev_disk`, `distance_to_feet`.
- `domain/values/direction.py` — `Direction` (8), дельты в `_BY_DELTA`.
- `application/engine/spells/effect_handler.py` + `defaults.py` — образец реестра (open/closed).
- `application/engine/actions/cast_spell.py` — `_resolve_targets`, `can_perform_against`.
- `interfaces/tui/screens/battle_modes/` — Move/Target mode-handler'ы + Protocol.

---

## P2-1: enums + TargetingSpec
**Files:** Modify `src/dnd/domain/values/spell.py`; Test `tests/unit/domain/test_spell.py` (дополнить).
Добавить `OriginMode`, `AreaShape`; в `TargetingSpec` — `origin`, `shape`, `radius_ft`, `length_ft` (заменить неиспользуемый `area_radius_ft`). Валидация: AREA требует shape; CIRCLE→radius_ft>0; CONE/LINE→length_ft>0.
- [ ] Тест: валидные AREA-spec (circle/cone/line); ValueError при пропуске size.
- [ ] Реализация → зелено. Sweep + commit `feat(domain): P2-1 OriginMode/AreaShape + TargetingSpec AoE`.

## P2-2: геометрия
**Files:** Create `src/dnd/domain/values/geometry.py`; Test `tests/unit/domain/test_geometry.py`.
`circle_squares(center, radius_sq)` (через chebyshev_disk → frozenset), `line_squares(origin, direction, length_sq)`, `cone_squares(origin, direction, length_sq)`. Helper `direction_delta(Direction)->(dx,dy)`.
Конус: на шаге k (1..length) включать клетки на главной оси ± (k-1) по перпендикуляру (ширина 2k-1). Зафиксировать тестами по клеткам.
- [ ] Тест: круг r=1 (9 клеток), линия E длиной 3 (3 клетки), линия NE (диагональ), конус N длиной 2 (1+3 клетки), у края поля origin не включается в линию.
- [ ] Реализация → зелено. Sweep + commit `feat(domain): P2-2 geometry circle/line/cone`.

## P2-3: AreaShapeRegistry + резолверы
**Files:** Create `src/dnd/application/engine/spells/area/__init__.py`, `area/resolver.py` (Protocol+Registry), `area/resolvers.py` (Circle/Cone/Line), `area/defaults.py`; Test `tests/integration/engine/test_area_resolvers.py`.
Резолвер `squares(origin, direction, spec, battlefield) -> frozenset[Square]`; CircleResolver игнорит direction (origin=точка), Cone/Line используют direction. `default_area_shape_registry()` регистрирует 3.
- [ ] Тест: каждый резолвер даёт ожидаемые клетки; registry get/contains; clamp к границам battlefield (клетки вне поля отбрасываются).
- [ ] Реализация → зелено. Sweep + commit `feat(engine): P2-3 AreaShapeRegistry + резолверы (open/closed)`.

## P2-4: CastSpell params/intent + _resolve_targets AREA
**Files:** Modify `cast_spell.py`, `dto/player_intent.py`; Test `tests/integration/engine/test_cast_spell_area.py`.
`CastSpellParams`/`CastSpellIntent`: `+ target_point: Square | None`, `direction: Direction | None`. `_resolve_targets` AREA: origin=caster.pos|target_point; squares через registry; цели=живые существа в клетках (friendly fire вкл.). `can_perform_against` AREA: AT_POINT→target_point в range; FROM_CASTER→direction задан. Реестр резолверов — поле Action (DI, default из defaults).
- [ ] Тест: at-point круг задевает нескольких (вкл. союзника); from-caster конус по направлению; вне range → Forbidden; нет direction → Forbidden.
- [ ] Реализация → зелено. Sweep + commit `feat(engine): P2-4 AoE-резолвинг целей в CastSpellAction`.

## P2-5: 3 заклинания + smoke
**Files:** Modify `data/content/spells.yaml`; добавить в `mage_apprentice` known_spells; Test `tests/integration/engine/test_cast_spell_area.py` (дополнить).
- fireball: level1, save, AREA/at_point/circle radius_ft=10, range 150, DEX, fire, save_for_half.
- burning_hands: level1, save, AREA/from_caster/cone length_ft=15, DEX, fire, save_for_half.
- lightning_bolt: level1, save, AREA/from_caster/line length_ft=30, DEX, lightning, save_for_half.
- [ ] Тест: каждое грузится; каст Fireball через CastSpellAction бьёт 2+ цели (урон применён каждому).
- [ ] Реализация → зелено. Sweep + commit `feat(content): P2-5 Fireball/Burning Hands/Lightning Bolt`.

## P2-6: TUI BattleMode.AREA (at-point)
**Files:** Modify `interfaces/tui/screens/battle.py`, `battle_modes/` (+ area handler), Test `tests/integration/tui/test_area_mode.py`.
Каст AoE-заклинания AT_POINT → `BattleMode.AREA`: курсор по полю (clamp+range), превью задетых клеток (через registry) в OverlayData.highlights; Enter→CastSpellIntent(target_point); Esc отмена. Реализатор сверяет OverlayData/ModeHandler Protocol.
- [ ] Тест (pilot): каст fireball → AREA mode → курсор → Enter → CastSpellIntent с target_point в очереди/эффект.
- [ ] Реализация → зелено. Sweep + commit `feat(tui): P2-6 BattleMode.AREA at-point + preview`.

## P2-7: TUI from-caster directional
**Files:** Modify area handler + battle.py; Test дополнить.
FROM_CASTER-заклинание → AREA mode в режиме направления: стрелки выбирают 1 из 8 dir, превью формы от кастера; Enter→CastSpellIntent(direction). 8 направлений: стрелки = ортогональные; диагонали — клавишами (напр. q/e/z/c) или Tab-цикл по 8. Реализатор выбирает удобную раскладку, документирует.
- [ ] Тест (pilot): burning_hands → выбор направления → CastSpellIntent(direction).
- [ ] Реализация → зелено. Sweep + commit `feat(tui): P2-7 from-caster directional AoE`.

## P2-8: docs
**Files:** Modify `docs/SPELLS.md`, `docs/ROADMAP.md`.
Описать конфигурацию зон (origin/shape/size), как добавить форму (резолвер+register) и AoE-заклинание (YAML); пометить P2 в ROADMAP; P2b (мультитаргет) — следующий.
- [ ] Sweep + commit `docs: P2-8 SPELLS.md AoE + ROADMAP`.

## Финальный аудит
Независимый аудит P2 (general-purpose): open/closed резолверов, корректность геометрии (по клеткам, диагонали, границы), friendly fire, маскирующие тесты (реальный флоу через can_perform_against/GameRunner, не только execute), регрессии.

## Self-Review
- Spec §2 «Включено» → таски P2-1..P2-8 покрывают всё.
- Геометрия (§3.2) → P2-2 с тестами по клеткам (конус уточняется там).
- Реестр резолверов (§3.3, open/closed) → P2-3.
- Резолвинг+friendly fire (§3.4) → P2-4. TUI (§3.5) → P2-6/P2-7.
- Типы согласованы: OriginMode/AreaShape/TargetingSpec поля едины; CastSpellParams target_point/direction — между P2-4 и TUI.

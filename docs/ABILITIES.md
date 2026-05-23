# Ability Framework

> Этап L2. Spec: `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md`.
> Plan: `docs/superpowers/plans/2026-05-23-l-inline-ux-and-abilities.md`.

## Концепция

`Ability` — runtime-описание игрового умения, ориентированное на UI:
hotkey, иконка, требования к выбору (target / path) и фабрика
`PlayerIntent`. Это отдельная сущность от `Action`-классов в
`application/engine/actions/`: `Action` выполняет игровую логику и
её результат — событие в EventBus; `Ability` отвечает за то, как
игрок инициирует это действие из TUI и как клавиша на клавиатуре
превращается в `PlayerIntent`.

Граница такая: BattleScreen берёт нажатую клавишу → ищет `Ability` в
keymap → вызывает её `intent_factory(...)` → кладёт `PlayerIntent` в
очередь → GameRunner транслирует его в соответствующий `Action`.

## Структура

```python
@dataclass(frozen=True)
class Ability:
    id: AbilityId              # NewType(str), напр. "weapon_attack"
    name: str                  # "Attack" — для action-bar и логов
    icon: str                  # 1 символ — для action-bar
    default_hotkey: str        # "a"
    economy_cost: ActionEconomyCost
    requires_target: bool      # True → mode TARGET (Tab-cycle)
    requires_path: bool        # True → mode MOVE (курсор по карте)
    intent_factory: Callable[..., PlayerIntent]
```

`requires_target` и `requires_path` взаимоисключающие — mode-state-
machine BattleScreen'а поддерживает только один из режимов за раз;
ability, требующий и того и другого, нельзя выразить текущим
machine'ом, поэтому `__post_init__` поднимает `ValueError`.

## Default-набор (6 умений)

| id            | name      | hotkey | requires_target |
|---------------|-----------|--------|-----------------|
| weapon_attack | Attack    | a      | yes             |
| dodge         | Dodge     | d      | —               |
| dash          | Dash      | h      | —               |
| disengage     | Disengage | g      | —               |
| interact      | Interact  | i      | yes (object)    |
| break_object  | Break     | k      | yes (object)    |

`Move` — намеренно НЕ ability: это **движение** (MOVEMENT), а не
**действие** (ACTION), и обрабатывается отдельным hotkey'ем `m` с
собственным `MoveModeHandler`-ом.

`Help` / `Search` / заклинания — пока без `*Intent`-классов, поэтому
не зарегистрированы. Добавим параллельно с самими intent'ами, чтобы
не плодить ability с фабриками-«заглушками».

См. `register_default_abilities` в `application/abilities/defaults.py`.

## Переопределение хоткеев

Каждое существо несёт `Creature.keybindings: dict[str, AbilityId]` —
персональный override default-хоткеев. По умолчанию пуст, и keymap
строится из `Ability.default_hotkey`. Чтобы переназначить `z` на
атаку:

```python
creature.keybindings["z"] = AbilityId("weapon_attack")
```

`build_keymap(actor, registry)` (`interfaces/tui/screens/keymap.py`)
собирает финальный `{hotkey: Ability}`:

1. для каждого `aid` в `actor.ability_ids` → `keymap[ability.default_hotkey] = ability`;
2. для каждого `(key, aid)` в `actor.keybindings`:
   - снимаем старый `default_hotkey` этой ability (если он там есть),
     иначе одна и та же ability оказалась бы привязана к двум клавишам;
   - назначаем новый `key`.

В BattleScreen.on_key (NORMAL mode) override-хоткей идёт через keymap
и `_trigger_ability(...)`, а **default hotkey'и** остаются на откуп
Textual `BINDINGS` (`action_intent_attack` и пр.) — это сохраняет всё
текущее интеграционное покрытие без изменений и оставляет один путь
выполнения для типичного игрока.

## Расширение

Новое умение регистрируется в `AbilityRegistry` в composition root
(сейчас — внутри `TuiApp.__init__`, при отсутствии явного
`ability_registry`-аргумента):

```python
registry.register(Ability(
    id=AbilityId("fire_bolt"), name="Fire Bolt", icon="*",
    default_hotkey="f", economy_cost=ActionEconomyCost.ACTION,
    requires_target=True, requires_path=False,
    intent_factory=lambda target_id: CastSpellIntent(
        spell_id=SpellId("fire_bolt"), target_id=target_id,
    ),
))
```

Чтобы PC-волшебник видел `[f] Fire Bolt` в action-bar — добавляем
`AbilityId("fire_bolt")` в `Creature.ability_ids` при создании
существа. ActionBarWidget пересоберётся на ближайшем TurnStarted.

## ИНВАРИАНТЫ

* default hotkey'и зарегистрированных ability'ев не коллидируют
  (тест: `tests/unit/abilities/test_default_abilities.py::test_no_hotkey_collisions`);
* `actor.ability_ids` валидируются через registry — `build_keymap`
  вызывает `registry.get(aid)`, который бросает `KeyError` на
  неизвестный id (fail-fast);
* `requires_target ∧ requires_path` запрещены в `__post_init__`.

## См. также

* `docs/TUI.md` §6 — mode-state machine, ActionBarWidget;
* `docs/ACTIONS.md` — серверная сторона: что делает каждое `Action`;
* `docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md` §4.3 — исходный дизайн.

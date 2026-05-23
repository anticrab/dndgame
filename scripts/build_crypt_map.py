"""Генератор большой demo-карты `crypt_of_black_candle` из ASCII-шаблона.

Запуск: python3 scripts/build_crypt_map.py

Парсит ASCII-шаблон с легендой, собирает MapDocument и записывает в
data/content/maps/crypt_of_black_candle.yaml через YamlMapRepository.
Также печатает spawns в формате для вклейки в scenarios.yaml.
Скрипт идемпотентный — повторный запуск перезаписывает файл картой
из того же шаблона.
"""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.map_dto import MapDocument, MapObjectDoc, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository

# Легенда:
#   .   floor             #   wall_full
#   ,   dirt              =   stone
#   ~   water             o   column (feature, high cover)
#   T   table_long        t   table_small
#   c   chair             b   brazier
#   H   high_cover_obj    L   low_cover_obj
#   D   door closed       K   door closed+locked
#   C   chest (loot)      B   barrel
#   W   window
#   @   floor + PC spawn       (объект не создаётся)
#   g   floor + goblin spawn
#   a   floor + goblin_archer spawn
#
# Все спецсимволы лежат на base=floor (поверх floor рисуется
# объект/спрайт). Walls и terrain (dirt/stone/water) — terrain без
# объекта. Координаты x — слева направо, y — сверху вниз.
TEMPLATE = [
    # 40 колонок × 24 строки. Одна связная подземная гробница без
    # «вне-карты» пустот: внешняя стена замкнута, внутренние
    # перегородки делят её на 5 связанных комнат с дверями.
    #
    # Северная половина:
    #   * Прихожая (1..8, 1..6) — вход для PC, бочки, стол.
    #   * Караульная (10..18, 1..6) — патруль гоблинов и стол.
    #   * Алтарь (20..38, 1..6) — колонны+факел, сторожевой лучник.
    # Центральный коридор (1..38, 7..11) соединяет крылья.
    # Южная половина:
    #   * Сокровищница (1..18, 13..22) — сундуки за запертой дверью.
    #   * Болото (20..38, 13..22) — dirt + water, difficult terrain,
    #     с засадой лучника.
    "########################################",
    "#......##.........##...................#",
    "#..@...D...g....t.D...b....o....o....b.#",
    "#......#..........#....................#",
    "#..b...#....t.....#......a.............#",
    "#......#..........#....................#",
    "#####D######D######D####################",
    "#......................................#",
    "#..o.................................o.#",
    "#......................................#",
    "#..o.................................o.#",
    "#......................................#",
    "######D###############D#################",
    "#....................#.................#",
    "#..C....b...c........#......a..........#",
    "#..C........t...g....K...,,,,,,,,......#",
    "#..C....b...c........#...,~~~~,,.......#",
    "#....................#...,~~~~,,.......#",
    "######D##############D...,,,,,,,,......#",
    "#......................................#",
    "#..b.....o.......o....g................#",
    "#..t...............................b...#",
    "#......................................#",
    "########################################",
]


def _coerce_template(rows: list[str], width: int, height: int) -> list[str]:
    """Все строки одинаковой длины (правый паддинг пробелами)."""
    out: list[str] = []
    for i, r in enumerate(rows[:height]):
        if len(r) < width:
            r = r + " " * (width - len(r))
        elif len(r) > width:
            raise ValueError(f"row {i} too wide: {len(r)} > {width}")
        out.append(r)
    while len(out) < height:
        out.append(" " * width)
    return out


def _terrain_of(ch: str) -> str | None:
    """Терраин для символа; None означает «вне карты» (пробел)."""
    if ch == " ":
        return None
    if ch == ",":
        return "dirt"
    if ch == "~":
        return "water"
    if ch == "=":
        return "stone"
    return "floor"


def _feature_of(ch: str) -> str | None:
    if ch == "#":
        return "wall_full"
    if ch == "T":
        return "table_long"
    if ch == "t":
        return "table_small"
    if ch == "c":
        return "chair"
    if ch == "b":
        return "brazier"
    if ch == "o":
        return "column"
    if ch == "H":
        return "high_cover_obj"
    if ch == "L":
        return "low_cover_obj"
    return None


def _object_of(ch: str, idx: int) -> MapObjectDoc | None:
    if ch == "D":
        return MapObjectDoc(
            id=f"door-{idx}", kind="door", x=0, y=0,
            state={"open": False, "locked": False, "hp": 10, "ac": 13},
        )
    if ch == "K":
        return MapObjectDoc(
            id=f"door-locked-{idx}", kind="door", x=0, y=0,
            state={"open": False, "locked": True, "hp": 12, "ac": 14},
        )
    if ch == "C":
        return MapObjectDoc(
            id=f"chest-{idx}", kind="chest", x=0, y=0,
            state={"open": False, "locked": False, "hp": 8, "ac": 14},
        )
    if ch == "B":
        return MapObjectDoc(
            id=f"barrel-{idx}", kind="barrel", x=0, y=0,
            state={"open": False, "hp": 6, "ac": 12},
        )
    if ch == "W":
        return MapObjectDoc(
            id=f"window-{idx}", kind="window", x=0, y=0,
            state={"open": False, "hp": 4, "ac": 12},
        )
    return None


def build() -> tuple[MapDocument, list[tuple[str, int, int]]]:
    width = 40
    height = 24
    rows = _coerce_template(TEMPLATE, width, height)

    tiles: list[MapTileDoc] = []
    objects: list[MapObjectDoc] = []
    spawns: list[tuple[str, int, int]] = []  # (template_id, x, y)
    next_id = 0
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            base = _terrain_of(ch)
            if base is None:
                continue  # вне карты — пропускаем (на рендере просто floor по умолчанию)
            feature = _feature_of(ch)
            features: tuple[str, ...] = (feature,) if feature else ()
            tiles.append(MapTileDoc(x=x, y=y, base=base, features=features))

            obj = _object_of(ch, next_id)
            if obj is not None:
                # MapObjectDoc — frozen pydantic, пересоздаём с координатами.
                objects.append(obj.model_copy(update={"x": x, "y": y}))
                next_id += 1

            if ch == "@":
                spawns.append(("warrior_lv1", x, y))
            elif ch == "g":
                spawns.append(("goblin", x, y))
            elif ch == "a":
                spawns.append(("goblin_archer", x, y))

    doc = MapDocument(
        id="crypt_of_black_candle",
        name="Crypt of the Black Candle",
        width=width,
        height=height,
        tiles=tuple(tiles),
        objects=tuple(objects),
    )
    return doc, spawns


def main() -> None:
    doc, spawns = build()
    root = Path(__file__).resolve().parent.parent
    maps_dir = root / "data" / "content" / "maps"
    repo = YamlMapRepository(maps_dir=maps_dir)
    repo.save(doc)
    print(f"saved: {maps_dir / (doc.id + '.yaml')}")
    print(f"size: {doc.width}x{doc.height}, tiles: {len(doc.tiles)}, "
          f"objects: {len(doc.objects)}")
    print("---spawns (для scenarios.yaml)---")
    pc_seen = False
    monster_idx = 1
    for template_id, x, y in spawns:
        if template_id == "warrior_lv1":
            iid = "aelar"
            faction = "party"
            pc_seen = True
        else:
            iid = f"{template_id}{monster_idx}"
            faction = "monsters"
            monster_idx += 1
        print(f"    - template_id: {template_id}")
        print(f"      instance_id: {iid}")
        print(f"      at: [{x}, {y}]")
        print(f"      faction: {faction}")
    if not pc_seen:
        print("WARNING: в шаблоне нет PC ('@') — сценарий будет неиграбельным.")


if __name__ == "__main__":
    main()

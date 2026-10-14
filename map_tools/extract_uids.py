#!/usr/bin/env python3
"""Extract item UIDs from ETS2/ATS map ``.base`` files.

The UIDs (converted from hex to decimal) of every configured item type are
combined into ``combined_output_results.txt`` using the
``discovered_items[i]: uid`` format. With ``--per-type`` they are also written
to separate ``output_results_type_<N>.txt`` files.

With ``--split-dlc {ets2,ats}`` the UIDs are additionally grouped by their
DLC guard value and written to one file per guard (e.g. texas, montana)
inside ``<output>/dlc_guards/``.

With ``--cities`` the City items (type 12) are collected into ``cities.txt`` as
a ``visited_cities`` list with a visit count per city.
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

ITEM_TYPES = (3, 4, 6, 7, 18, 42)
DEFAULT_INPUT_DIR = r"C:\Users\doode\Documents\Euro Truck Simulator 2\mod\user_map\map\europka"
INPUT_SUFFIXES = (".base", ".txt")
CITY_ITEM_TYPE = 12
CITIES_FILENAME = "cities.txt"
COMBINED_FILENAME = "combined_output_results.txt"
DLC_SUBDIR = "dlc_guards"

# Where the DLC guard lives, per item type: (field name in the dump, bit shift).
# Per https://github.com/sk-zk/map-docs/wiki:
#   Road (3):         "Byte 1" of road_flags (the second flag field)
#   Map Overlay (18): "Byte 1" of flags
#   Map Area (42):    "Byte 1" of flags
# Prefab (4) has no documented DLC guard; Company (6) / Service (7) are slave
# items of prefabs and carry none either.
DLC_GUARD_SOURCES = {
    3: ("road_flags", 8),
    18: ("flags", 8),
    42: ("flags", 8),
}

# https://github.com/sk-zk/map-docs/wiki/DLC-guard
DLC_GUARDS = {
    "ets2": {
        1: "East", 2: "Scandinavia", 3: "France", 4: "Italy",
        5: "Italy and France", 6: "Baltic", 7: "Baltic and East",
        8: "Baltic and Scandinavia", 9: "Black Sea", 10: "Black Sea and East",
        11: "Iberia", 12: "Iberia and France", 13: "Russia",
        14: "Russia and Baltic", 15: "Krone", 16: "West Balkans",
        17: "West Balkans and East", 18: "West Balkans and Black Sea",
        19: "Feldbinder", 20: "Greece", 21: "Greece and East Balkans",
        22: "Greece and West Balkans", 23: "Nordic", 24: "Nordic and Baltic",
        25: "Nordic and Scandinavia",
    },
    "ats": {
        1: "Nevada", 2: "Arizona", 3: "New Mexico", 4: "Oregon",
        5: "Washington", 6: "Washington and Oregon", 7: "Utah",
        8: "Utah and New Mexico", 9: "Idaho", 10: "Idaho and Oregon",
        11: "Idaho and Utah", 12: "Idaho and Washington", 13: "Colorado",
        14: "Colorado and New Mexico", 15: "Colorado and Utah", 16: "Wyoming",
        17: "Wyoming and Colorado", 18: "Wyoming and Idaho",
        19: "Wyoming and Utah", 20: "Texas", 21: "Texas and New Mexico",
        22: "Montana", 23: "Montana and Idaho", 24: "Montana and Wyoming",
        25: "Oklahoma", 26: "Oklahoma and Colorado",
        27: "Oklahoma and New Mexico", 28: "Oklahoma and Texas", 29: "Kansas",
        30: "Kansas and Colorado", 31: "Kansas and Oklahoma", 32: "Nebraska",
        33: "Nebraska and Colorado", 34: "Nebraska and Kansas",
        35: "Nebraska and Wyoming", 36: "Arkansas", 37: "Arkansas and Oklahoma",
        38: "Arkansas and Texas", 39: "Missouri", 40: "Missouri and Arkansas",
        41: "Missouri and Kansas", 42: "Missouri and Nebraska",
        43: "Missouri and Oklahoma", 44: "Iowa", 45: "Iowa and Missouri",
        46: "Iowa and Nebraska", 47: "Louisiana", 48: "Louisiana and Arkansas",
        49: "Louisiana and Texas", 50: "Illinois", 51: "Illinois and Iowa",
        52: "Illinois and Missouri", 53: "South Dakota",
        54: "South Dakota and Iowa", 55: "South Dakota and Montana",
        56: "South Dakota and Nebraska", 57: "South Dakota and Wyoming",
    },
}


def build_pattern(item_type: int, value_field: str = "flags") -> re.Pattern:
    """Match an item of the given type up to its uid and the given u32 field.

    Groups: 1 = uid (hex), 2 = value of ``value_field``.
    """
    return re.compile(
        rf"u32\s+item_type:\s*{item_type}(?:\n.+?)+?"
        rf"u64\s+uid:\s+x([^\s]+)(?:\n.+?)+?"
        rf"u32\s+{value_field}:\s*(\d+)\n"
    )


def build_city_pattern() -> re.Pattern:
    """Match a City item (type 12) up to its ``token city`` field (group 1)."""
    return re.compile(
        rf"u32\s+item_type:\s*{CITY_ITEM_TYPE}(?:\n.+?)+?"
        rf"token\s+city:[ \t]*(\S*)"
    )


def scan(input_dir: Path, item_types=ITEM_TYPES, dlc_sources=None, find_cities=False):
    """Scan every .base/.txt file once.

    Returns ``(uids_by_type, uids_by_dlc_guard, cities)``. The DLC dict is empty
    unless ``dlc_sources`` is given; ``cities`` is a list of unique city names
    in order of first appearance and is empty unless ``find_cities`` is set.
    """
    uid_patterns = {t: build_pattern(t) for t in item_types}
    dlc_patterns = {
        t: (build_pattern(t, field), shift)
        for t, (field, shift) in (dlc_sources or {}).items()
    }
    by_type = {t: [] for t in item_types}
    by_guard = defaultdict(list)
    city_pattern = build_city_pattern() if find_cities else None
    cities = {}  # dict used as an ordered set

    for path in sorted(p for p in input_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in INPUT_SUFFIXES):
        data = path.read_text(encoding="utf-8", errors="ignore")

        for item_type, pattern in uid_patterns.items():
            by_type[item_type].extend(int(uid, 16) for uid, _ in pattern.findall(data))

        for pattern, shift in dlc_patterns.values():
            for uid, value in pattern.findall(data):
                guard = (int(value) >> shift) & 0xFF
                by_guard[guard].append(int(uid, 16))

        if city_pattern:
            for name in city_pattern.findall(data):
                name = name.strip("\"'")
                if name:  # skip City items with an empty name
                    cities.setdefault(name, None)

    return by_type, by_guard, list(cities)


def write_lines(path: Path, lines) -> None:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def write_type_files(results: dict, output_dir: Path) -> None:
    for item_type, uids in results.items():
        write_lines(output_dir / f"output_results_type_{item_type}.txt", uids)


def write_combined_file(results: dict, output_dir: Path) -> None:
    all_uids = [uid for uids in results.values() for uid in uids]
    lines = [f"discovered_items: {len(all_uids)}"]
    lines += [f"discovered_items[{i}]: {uid}" for i, uid in enumerate(all_uids)]
    write_lines(output_dir / COMBINED_FILENAME, lines)


def write_cities_file(cities: list, visit_count: int, output_dir: Path) -> None:
    n = len(cities)
    lines = [f" visited_cities: {n}"]
    lines += [f" visited_cities[{i}]: {name}" for i, name in enumerate(cities)]
    lines.append(f" visited_cities_count: {n}")
    lines += [f" visited_cities_count[{i}]: {visit_count}" for i in range(n)]
    write_lines(output_dir / CITIES_FILENAME, lines)
    print(f"Cities: {n}")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def write_dlc_files(by_guard: dict, game: str, output_dir: Path) -> None:
    names = DLC_GUARDS[game]
    dlc_dir = output_dir / DLC_SUBDIR
    dlc_dir.mkdir(parents=True, exist_ok=True)

    for guard in sorted(by_guard):
        name = "none" if guard == 0 else names.get(guard, f"unknown_{guard}")
        path = dlc_dir / f"dlc_guard_{guard:02d}_{slugify(name)}.txt"
        write_lines(path, by_guard[guard])
        print(f"DLC guard {guard} ({name}): {len(by_guard[guard])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract item UIDs from ETS2/ATS map .base/.txt files.")
    parser.add_argument(
        "-i", "--input", type=Path, default=Path(DEFAULT_INPUT_DIR),
        help="folder containing the .base/.txt files (default: %(default)s)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path.cwd(),
        help="folder for the result files (default: current directory)",
    )
    parser.add_argument(
        "--per-type", action="store_true",
        help="also write one output_results_type_<N>.txt file per item type",
    )
    parser.add_argument(
        "--cities", action="store_true",
        help=f"also write {CITIES_FILENAME} with a visited_cities list of all City items",
    )
    parser.add_argument(
        "--city-visits", type=int, default=1, metavar="N",
        help="visit count written for every city with --cities (default: %(default)s)",
    )
    parser.add_argument(
        "--split-dlc", choices=sorted(DLC_GUARDS), metavar="{ets2,ats}",
        help="also write one file per DLC guard (e.g. texas, montana) to "
             f"<output>/{DLC_SUBDIR}/; the value selects which game's guard table to use",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.is_dir():
        raise SystemExit(f"Input folder not found: {args.input}")
    args.output.mkdir(parents=True, exist_ok=True)

    dlc_sources = DLC_GUARD_SOURCES if args.split_dlc else None
    by_type, by_guard, cities = scan(args.input, ITEM_TYPES, dlc_sources, args.cities)

    if args.per_type:
        write_type_files(by_type, args.output)
    else:
        for item_type, uids in by_type.items():
            print(f"Total results (Type {item_type}): {len(uids)}")
    write_combined_file(by_type, args.output)
    if args.cities:
        write_cities_file(cities, args.city_visits, args.output)
    if args.split_dlc:
        write_dlc_files(by_guard, args.split_dlc, args.output)
    print(f"Output written to: {args.output.resolve()}")


if __name__ == "__main__":
    main()
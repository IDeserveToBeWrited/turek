#!/usr/bin/env python3
"""
photo_album_gen.py - generate "fully completed" photo album data for an
American Truck Simulator save, based on the game's def/photo_album files.

It reads the def files (photo_album.sii + *.sui) from a directory and
(re)generates these four save blocks:

    discovered_cutscene_items        (objects_uid of viewpoints / POIs / boards)
    discovered_cutscene_items_states
    tourist_atlas_log_units          (item / board names)
    tourist_atlas_log_flags

It also generates a landmarks.sii (album_landmarks_info / album_landmarks_data
units). By default it lists only the landmarks that need a photo, which the defs
identify only indirectly: they are the landmarks that are objectives of a tourist
board (tourist_boards.sui -> items[]), 9 in total. Use --landmarks-mode all for every
landmark, or --extra-landmarks for ids you know need a photo as well. New entries use
screenshot_file "blank.png"; entries from an existing landmarks.sii (--landmarks-in)
are always kept as they are.

Existing entries in the save are KEPT (including UIDs unknown to the defs);
only what is missing is appended, so it is safe to run repeatedly.

Usage:
    python photo_album_gen.py --defs path/to/def/photo_album --save save.txt
        -> writes photo_album_output.txt and landmarks.sii
    python photo_album_gen.py --defs ... --save save.txt --landmarks-in old/landmarks.sii
    python photo_album_gen.py --defs ... --save save.txt --dlc base ats_oregon ats_montana ats_wa
    python photo_album_gen.py --defs ... --save save.txt --list-dlc

Observed semantics (inferred from a real save, NOT from official docs):
    cutscene state: viewpoints / POIs -> 2, tourist boards -> 3
    atlas log flag: board started -> 2, item visited+photo -> 3, board completed -> 4
All values can be overridden from the command line.
Always back up your save before using the output.
"""
import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

CATEGORY_PREFIX = {
    "landmarks": "album.landmarks.",
    "viewpoints": "album.viewpoints.",
    "cities": "album.cities.",
    "pointsoi": "album.pointsoi.",
    "touristbs": "album.touristbs.",
}
# categories written to discovered_cutscene_items by default (what the sample save contains)
DEFAULT_CATEGORIES = ["viewpoints", "pointsoi", "touristbs"]

BLOCK_RE = re.compile(r"^\s*(\w+)\s*:\s*([\w.]+)\s*\{(.*?)^\s*\}", re.S | re.M)


# --------------------------------------------------------------------------
# def parsing
# --------------------------------------------------------------------------
def strip_comments(text):
    """Remove '#' comments (not inside quotes)."""
    out = []
    for line in text.splitlines():
        res, in_q = [], False
        for ch in line:
            if ch == '"':
                in_q = not in_q
            if ch == "#" and not in_q:
                break
            res.append(ch)
        out.append("".join(res))
    return "\n".join(out)


class Item:
    def __init__(self, kind, name):
        self.kind = kind            # photo_album_item / photo_album_group / tourist_board_item
        self.name = name
        self.uids = []              # ints
        self.items = []             # child names
        self.dlc = "base"

    @property
    def category(self):
        for cat, pre in CATEGORY_PREFIX.items():
            if self.name.startswith(pre):
                return cat
        return None


def parse_defs(def_dir):
    items = OrderedDict()
    sheets = []                     # list of (content_type, [content names])
    d = Path(def_dir)
    files = sorted(list(d.glob("*.sui")) + list(d.glob("*.sii")))
    if not files:
        sys.exit(f"No .sui/.sii files found in {d}")
    for f in files:
        text = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for m in BLOCK_RE.finditer(text):
            kind, name, body = m.groups()
            if kind == "photo_album_sheet":
                ctype = re.search(r'content_type:\s*"([^"]+)"', body)
                sheets.append((ctype.group(1) if ctype else None,
                               re.findall(r"content\[\]:\s*([\w.]+)", body)))
                continue
            if kind not in ("photo_album_item", "photo_album_group", "tourist_board_item"):
                continue
            it = Item(kind, name)
            it.uids = [int(u, 16) for u in re.findall(r"objects_uid\[\]:\s*(0x[0-9A-Fa-f]+)", body)]
            it.items = re.findall(r"items\[\]:\s*([\w.]+)", body)
            dm = re.search(r'dlc_id:\s*"?([\w]+)"?', body)
            if dm:
                it.dlc = dm.group(1)
            items[name] = it
    return items, sheets


def reachable_leaves(items, sheets):
    """Resolve sheet content[] -> groups -> items. Only what the album really shows."""
    seen, leaves = set(), OrderedDict()

    def walk(name):
        if name in seen or name not in items:
            return
        seen.add(name)
        it = items[name]
        if it.kind == "photo_album_group":
            for c in it.items:
                walk(c)
        else:
            leaves[name] = it

    for ctype, content in sheets:
        for c in content:
            walk(c)
    return leaves


# --------------------------------------------------------------------------
# save parsing / writing
# --------------------------------------------------------------------------
KEYS = ["discovered_cutscene_items", "discovered_cutscene_items_states",
        "tourist_atlas_log_units", "tourist_atlas_log_flags"]


def read_array(lines, key, conv):
    vals = []
    pat = re.compile(r"^\s*" + re.escape(key) + r"\[(\d+)\]:\s*(.+?)\s*$")
    for l in lines:
        m = pat.match(l)
        if m:
            vals.append((int(m.group(1)), conv(m.group(2).strip('"'))))
    return [v for _, v in sorted(vals)]


def format_array(key, vals, quote=False):
    out = [f" {key}: {len(vals)}"]
    for i, v in enumerate(vals):
        out.append(f' {key}[{i}]: "{v}"' if quote else f" {key}[{i}]: {v}")
    return out


def write_save(lines, cut_ids, cut_states, log_units, log_flags):
    """Replace the 4 blocks in place (at the position of the first one found)."""
    pat = re.compile(r"^\s*(" + "|".join(KEYS) + r")(\[\d+\])?:")
    new_block = (format_array(KEYS[0], cut_ids) + format_array(KEYS[1], cut_states)
                 + format_array(KEYS[2], log_units, quote=True) + format_array(KEYS[3], log_flags))
    out, inserted = [], False
    for l in lines:
        if pat.match(l):
            if not inserted:
                out.extend(new_block)
                inserted = True
            continue
        out.append(l)
    if not inserted:
        out.extend(new_block)
    return out


# --------------------------------------------------------------------------
# landmarks.sii
# --------------------------------------------------------------------------
BLANK_SCREENSHOT = "blank.png"


def parse_landmarks_sii(path):
    """Return (info_name, [(unit_name, landmark_id, screenshot_file), ...]) from an existing file."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    im = re.search(r"album_landmarks_info\s*:\s*([\w.]+)", text)
    entries = []
    for m in re.finditer(r"album_landmarks_data\s*:\s*([\w.]+)\s*\{(.*?)\}", text, re.S):
        lid = re.search(r"landmark_id:\s*([\w.]+)", m.group(2))
        shot = re.search(r'screenshot_file:\s*"([^"]*)"', m.group(2))
        if lid:
            entries.append((m.group(1), lid.group(1), shot.group(1) if shot else BLANK_SCREENSHOT))
    return (im.group(1) if im else None), entries


def make_nameless(key, used):
    """Deterministic '_nameless.146.xxxx.xxxx' id (the format used by the game), unique within `used`."""
    import zlib
    n = zlib.crc32(key.encode())
    while True:
        name = f"_nameless.146.{(n >> 16) & 0xFFFF:04x}.{n & 0xFFFF:04x}"
        if name not in used:
            used.add(name)
            return name
        n = (n + 0x9E37) & 0xFFFFFFFF


def generate_landmarks_sii(landmark_ids, existing=None, nl="\r\n"):
    """Build landmarks.sii text. `existing` = (info_name, entries) from parse_landmarks_sii().
    Existing landmarks keep their unit names and screenshots; missing ones get blank.png."""
    info_name, entries = existing if existing else (None, [])
    used = {e[0] for e in entries}
    if info_name:
        used.add(info_name)
    else:
        info_name = make_nameless("album_landmarks_info", used)
    have = {e[1] for e in entries}
    entries = list(entries)
    for lid in landmark_ids:
        if lid not in have:
            entries.append((make_nameless(lid, used), lid, BLANK_SCREENSHOT))
            have.add(lid)
    out = ["SiiNunit", "{", f"album_landmarks_info : {info_name} {{", f" landmarks: {len(entries)}"]
    out += [f" landmarks[{i}]: {e[0]}" for i, e in enumerate(entries)]
    out += ["}", ""]
    for unit, lid, shot in entries:
        out += [f"album_landmarks_data : {unit} {{", f" landmark_id: {lid}",
                f' screenshot_file: "{shot}"', "}", ""]
    out += ["}", ""]
    return nl.join(out), len(entries)


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--defs", required=True, help="path to the def/photo_album directory")
    ap.add_argument("--save", help="input save text file (existing entries are preserved)")
    ap.add_argument("-o", "--out", default="photo_album_output.txt",
                    help="output file (default: photo_album_output.txt, '-' = stdout)")
    ap.add_argument("--landmarks-in", help="existing landmarks.sii whose entries/screenshots are kept")
    ap.add_argument("--landmarks-out", default="landmarks.sii",
                    help="generated landmarks.sii path (default: landmarks.sii)")
    ap.add_argument("--no-landmarks", action="store_true", help="do not generate landmarks.sii")
    ap.add_argument("--landmarks-mode", choices=["boards", "all"], default="boards",
                    help="boards (default): only landmarks that are tourist board objectives; "
                         "all: every landmark of the album")
    ap.add_argument("--extra-landmarks", nargs="*", default=[], metavar="ID",
                    help="additional landmark ids to include, e.g. mt_oberlin or_newport_b")
    ap.add_argument("--dlc", nargs="*", help="only include items of these dlc_id values (default: all)")
    ap.add_argument("--list-dlc", action="store_true", help="list dlc ids found in the defs and exit")
    ap.add_argument("--categories", nargs="*", default=DEFAULT_CATEGORIES,
                    choices=list(CATEGORY_PREFIX),
                    help="categories written to discovered_cutscene_items "
                         "(default: viewpoints pointsoi touristbs; landmarks/cities are not "
                         "present in the sample save, so they are opt-in)")
    ap.add_argument("--state-item", type=int, default=2, help="cutscene state for viewpoints/POIs (default 2)")
    ap.add_argument("--state-board", type=int, default=3, help="cutscene state for tourist boards (default 3)")
    ap.add_argument("--flag-board-start", type=int, default=2)
    ap.add_argument("--flag-item", type=int, default=3, help="atlas log flag for a visited+photographed item")
    ap.add_argument("--flag-board-done", type=int, default=4)
    ap.add_argument("--done-flags", type=int, nargs="*", default=[4, 5],
                    help="log flags that mean 'board already completed' (default 4 5)")
    ap.add_argument("--normalize", action="store_true",
                    help="also overwrite states of already-present cutscene entries with the defaults")
    args = ap.parse_args()

    items, sheets = parse_defs(args.defs)
    leaves = reachable_leaves(items, sheets)

    if args.list_dlc:
        for dlc in sorted({i.dlc for i in leaves.values()}):
            n = sum(1 for i in leaves.values() if i.dlc == dlc)
            print(f"{dlc:16s} {n} items")
        return

    allowed = set(args.dlc) if args.dlc else None
    ok = lambda it: allowed is None or it.dlc in allowed

    # ---- load existing save ----
    nl = "\n"
    lines = []
    if args.save:
        raw = Path(args.save).read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"      # keep the save's line endings
        lines = raw.splitlines()
    cut_ids = read_array(lines, KEYS[0], int)
    cut_states = read_array(lines, KEYS[1], int)
    cut_states += [0] * (len(cut_ids) - len(cut_states))
    log_units = read_array(lines, KEYS[2], str)
    log_flags = read_array(lines, KEYS[3], int)
    log_flags += [0] * (len(log_units) - len(log_flags))

    # ---- discovered_cutscene_items ----
    index = {u: i for i, u in enumerate(cut_ids)}
    added_cut = 0
    for it in leaves.values():
        if it.category not in args.categories or not ok(it):
            continue
        state = args.state_board if it.category == "touristbs" else args.state_item
        for u in it.uids:
            if u in index:
                if args.normalize:
                    cut_states[index[u]] = state
            else:
                index[u] = len(cut_ids)
                cut_ids.append(u)
                cut_states.append(state)
                added_cut += 1

    # ---- tourist atlas log ----
    seen_units = {}
    for u, f in zip(log_units, log_flags):
        seen_units[u] = max(seen_units.get(u, 0), f)
    added_log = 0
    for b in leaves.values():
        if b.kind != "tourist_board_item" or not ok(b):
            continue
        if seen_units.get(b.name, 0) in args.done_flags:
            continue                                  # board already completed
        if b.name not in seen_units:                  # board never started
            log_units.append(b.name); log_flags.append(args.flag_board_start); added_log += 1
        for child in b.items:
            if child in seen_units and child != b.name:
                continue                              # already logged
            if child not in items:
                print(f"warning: {b.name} references unknown item {child}", file=sys.stderr)
                continue
            log_units.append(child); log_flags.append(args.flag_item)
            seen_units[child] = args.flag_item; added_log += 1
        log_units.append(b.name); log_flags.append(args.flag_board_done); added_log += 1
        seen_units[b.name] = args.flag_board_done

    # ---- output ----
    result = write_save(lines, cut_ids, cut_states, log_units, log_flags)
    text = nl.join(result) + nl
    if args.out != "-":
        Path(args.out).write_bytes(text.encode("utf-8"))
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))

    if not args.no_landmarks:
        pre = CATEGORY_PREFIX["landmarks"]
        if args.landmarks_mode == "all":
            lm_ids = [it.name[len(pre):] for it in leaves.values()
                      if it.category == "landmarks" and ok(it)]
        else:
            lm_ids = []
            for b in leaves.values():
                if b.kind == "tourist_board_item" and ok(b):
                    lm_ids += [c[len(pre):] for c in b.items
                               if c.startswith(pre) and c in items and ok(items[c])]
        for x in args.extra_landmarks:
            x = x[len(pre):] if x.startswith(pre) else x
            if pre + x not in items:
                print(f"warning: unknown landmark id {x}", file=sys.stderr)
            lm_ids.append(x)
        lm_ids = list(OrderedDict.fromkeys(lm_ids))
        existing = parse_landmarks_sii(args.landmarks_in) if args.landmarks_in else None
        lm_text, lm_total = generate_landmarks_sii(lm_ids, existing)
        Path(args.landmarks_out).write_bytes(lm_text.encode("utf-8"))
        kept = len(existing[1]) if existing else 0
        print(f"landmarks.sii: {lm_total} entries ({kept} kept, {lm_total - kept} new with "
              f'"{BLANK_SCREENSHOT}") -> {args.landmarks_out}', file=sys.stderr)
    print(f"cutscene items: +{added_cut} (total {len(cut_ids)}), "
          f"atlas log entries: +{added_log} (total {len(log_units)})", file=sys.stderr)


if __name__ == "__main__":
    main()
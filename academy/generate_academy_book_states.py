#!/usr/bin/env python3
"""
Generate an ETS2 / ATS `academy_book_states.sii` with every book, scenario and
goal completed (all goals succeeded, 3 stars wherever stars exist).

Usage:
    python generate_academy_book_states.py /path/to/def/academy
    python generate_academy_book_states.py /path/to/def/academy -o out.sii \
        --vehicle-from my_old_academy_book_states.sii

What the script reads from <academy>:
    books.sii, chapters.sii, scenarios.sii (+ every @include: scenario/*.sui,
    scenario/share/*.sui) and truck/*.sii

How a result is built (derived from cross-checking a real save against the defs):
  * goal_ids      = goal `id` (falls back to `value_name`), in the scenario's goals[] order
  * goal_values   = one value per goal `value_name`, chosen inside the intersection of
                    allowed_value_min / allowed_value_max of every goal sharing that name
  * goal_success  = true when the value is inside the goal's allowed range
  * score         = sum of `score_success` (default 1) of succeeded goals
  * rank          = number of `score_ranks` thresholds <= score (0 if none defined)
  * trigger_state_names = CityHash64 v1.0.3 of each scenario-level trigger_states[] (deduped,
                    declaration order; variant-level states are not stored)
  * log           = vehicle_data + scenario_start/scenario_end per scenario
"""
import argparse
import os
import re
import struct
import sys
import time
from collections import OrderedDict, defaultdict

INF = float("inf")

# ----------------------------------------------------------------------------
# CityHash64 (v1.0.3, the variant SCS uses for tokens) - only the <=32 byte paths
# are needed for trigger-state names, longer input is handled for completeness.
# ----------------------------------------------------------------------------
_M = (1 << 64) - 1
_K0, _K1, _K2, _K3 = (0xC3A5C85C97CB3127, 0xB492B66FBE98F273,
                      0x9AE16A3B2F90404F, 0xC949D7C7509E6557)


def _f64(s, i): return int.from_bytes(s[i:i + 8], "little")
def _f32(s, i): return int.from_bytes(s[i:i + 4], "little")
def _rot(v, sh): return v if sh == 0 else ((v >> sh) | (v << (64 - sh))) & _M
def _smix(v): return v ^ (v >> 47)


def _h128to64(u, v):
    mul = 0x9DDFEA08EB382D69
    a = ((u ^ v) * mul) & _M; a ^= a >> 47
    b = ((v ^ a) * mul) & _M; b ^= b >> 47
    return (b * mul) & _M


def _len0to16(s):
    n = len(s)
    if n > 8:
        a, b = _f64(s, 0), _f64(s, n - 8)
        return _h128to64(a, _rot((b + n) & _M, n)) ^ b
    if n >= 4:
        return _h128to64((n + (_f32(s, 0) << 3)) & _M, _f32(s, n - 4))
    if n > 0:
        y = (s[0] + (s[n >> 1] << 8)) & 0xFFFFFFFF
        z = (n + (s[n - 1] << 2)) & 0xFFFFFFFF
        return (_smix(((y * _K2) & _M) ^ ((z * _K3) & _M)) * _K2) & _M
    return _K2


def _len17to32(s):
    n = len(s)
    a = _f64(s, 0) * _K1 & _M; b = _f64(s, 8)
    c = _f64(s, n - 8) * _K2 & _M; d = _f64(s, n - 16) * _K0 & _M
    return _h128to64((_rot((a - b) & _M, 43) + _rot(c, 30) + d) & _M,
                     (a + _rot(b ^ _K3, 20) - c + n) & _M)


def _weak32(w, x, y, z, a, b):
    a = (a + w) & _M
    b = _rot((b + a + z) & _M, 21)
    c = a
    a = (a + x) & _M
    a = (a + y) & _M
    b = (b + _rot(a, 44)) & _M
    return (a + z) & _M, (b + c) & _M


def _weak32s(s, i, a, b):
    return _weak32(_f64(s, i), _f64(s, i + 8), _f64(s, i + 16), _f64(s, i + 24), a, b)


def _len33to64(s):
    n = len(s)
    z = _f64(s, 24)
    a = (_f64(s, 0) + (n + _f64(s, n - 16)) * _K0) & _M
    b = _rot((a + z) & _M, 52)
    c = _rot(a, 37)
    a = (a + _f64(s, 8)) & _M
    c = (c + _rot(a, 7)) & _M
    a = (a + _f64(s, 16)) & _M
    vf = (a + z) & _M
    vs = (b + _rot(a, 31) + c) & _M
    a = (_f64(s, 16) + _f64(s, n - 32)) & _M
    z = _f64(s, n - 8)
    b = _rot((a + z) & _M, 52)
    c = _rot(a, 37)
    a = (a + _f64(s, n - 24)) & _M
    c = (c + _rot(a, 7)) & _M
    a = (a + _f64(s, n - 16)) & _M
    wf = (a + z) & _M
    ws = (b + _rot(a, 31) + c) & _M
    r = _smix(((vf + ws) * _K2 + (wf + vs) * _K0) & _M)
    return (_smix((r * _K0 + vs) & _M) * _K2) & _M


def cityhash64(s):
    if isinstance(s, str):
        s = s.encode("utf-8")
    n = len(s)
    if n <= 32:
        return _len0to16(s) if n <= 16 else _len17to32(s)
    if n <= 64:
        return _len33to64(s)
    x = _f64(s, n - 40)
    y = (_f64(s, n - 16) + _f64(s, n - 56)) & _M
    z = _h128to64((_f64(s, n - 48) + n) & _M, _f64(s, n - 24))
    v = _weak32s(s, n - 64, n, z)
    w = _weak32s(s, n - 32, (y + _K1) & _M, x)
    x = (x * _K1 + _f64(s, 0)) & _M
    k = (n - 1) & ~63
    i = 0
    while k > 0:
        x = (_rot((x + y + v[0] + _f64(s, i + 8)) & _M, 37) * _K1) & _M
        y = (_rot((y + v[1] + _f64(s, i + 48)) & _M, 42) * _K1) & _M
        x ^= w[1]
        y = (y + v[0] + _f64(s, i + 40)) & _M
        z = (_rot((z + w[0]) & _M, 33) * _K1) & _M
        v = _weak32s(s, i, (v[1] * _K1) & _M, (x + w[0]) & _M)
        w = _weak32s(s, i + 32, (z + w[1]) & _M, (y + _f64(s, i + 16)) & _M)
        z, x = x, z
        i += 64
        k -= 64
    return _h128to64((_h128to64(v[0], w[0]) + _smix(y) * _K1 + z) & _M,
                     (_h128to64(v[1], w[1]) + x) & _M)


# ----------------------------------------------------------------------------
# SII reading (defs side)
# ----------------------------------------------------------------------------
def expand_includes(path, root):
    """Return the file's lines with every @include textually expanded."""
    out = []
    here = os.path.dirname(path)
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()
    for ln in lines:
        m = re.match(r'\s*@include\s+"([^"]+)"', ln)
        if not m:
            out.append(ln)
            continue
        for base in (here, root, os.path.join(root, "scenario")):
            p = os.path.normpath(os.path.join(base, m.group(1)))
            if os.path.isfile(p):
                out += expand_includes(p, root)
                break
        else:
            print(f"warning: include not found: {m.group(1)} (in {path})", file=sys.stderr)
    return out


def _strip_comment(s):
    quoted = False
    for i, c in enumerate(s):
        if c == '"':
            quoted = not quoted
        if not quoted and (c == "#" or s[i:i + 2] == "//"):
            return s[:i].strip()
    return s.strip()


def parse_units(lines):
    """-> OrderedDict name -> (type, OrderedDict key -> str | list[str])"""
    units = OrderedDict()
    cur = None
    pending = None
    for raw in lines:
        s = _strip_comment(raw)
        if not s:
            continue
        if cur is None:
            m = re.match(r"^(\w+)\s*:\s*(\S+?)\s*(\{)?$", s)
            if m:
                pending = (m.group(1), m.group(2))
                if m.group(3):
                    cur = OrderedDict()
                    units[pending[1]] = (pending[0], cur)
                    pending = None
            elif s == "{" and pending:
                cur = OrderedDict()
                units[pending[1]] = (pending[0], cur)
                pending = None
            continue
        if s == "}":
            cur = None
            continue
        m = re.match(r"^([\w.]+)(\[\d*\])?\s*:\s*(.*)$", s)
        if not m:
            continue
        key, arr, val = m.groups()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] == '"':
            val = val[1:-1]
        if arr is not None:
            cur.setdefault(key, []).append(val)
        else:
            cur[key] = val
    return units


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------------
# Scenario model
# ----------------------------------------------------------------------------
class Defs:
    def __init__(self, academy_dir):
        self.root = academy_dir
        self.units = OrderedDict()
        for f in ("books.sii", "chapters.sii", "scenarios.sii"):
            p = os.path.join(academy_dir, f)
            if not os.path.isfile(p):
                sys.exit(f"error: {p} not found - is this the def/academy folder?")
            self.units.update(parse_units(expand_includes(p, academy_dir)))

    def of_type(self, typ):
        return [(n, d) for n, (t, d) in self.units.items() if t == typ]

    def books(self):
        return self.of_type("academy_book")

    def book_scenarios(self, book):
        """Intro scenario followed by every chapter scenario, in order."""
        d = self.units[book][1]
        out = []
        if d.get("intro_scenario"):
            out.append(d["intro_scenario"])
        for ch in d.get("chapters", []):
            for sc in self.units[ch][1].get("scenarios", []) if ch in self.units else []:
                if sc not in out:
                    out.append(sc)
        return out

    def scenario(self, name):
        d = self.units[name][1]
        goals = []
        for g in d.get("goals", []):
            gd = self.units[g][1]
            goals.append(dict(
                id=gd.get("id", gd.get("value_name")),
                value_name=gd.get("value_name"),
                min=_num(gd.get("allowed_value_min")),
                max=_num(gd.get("allowed_value_max")),
                score=_num(gd.get("score_success"), 1.0),
            ))
        trig = []
        for s in d.get("trigger_states", []):
            if s not in trig:
                trig.append(s)
        ranks = sorted(float(x) for x in d.get("score_ranks", []))
        return dict(goals=goals, triggers=trig, ranks=ranks)


def in_range(v, g):
    return (g["min"] is None or v >= g["min"]) and (g["max"] is None or v <= g["max"])


def build_result(sc, time_fraction, default_duration_s, transmission):
    """Compute a fully successful result for a scenario model."""
    goals = sc["goals"]
    groups = defaultdict(list)
    for g in goals:
        groups[g["value_name"]].append(g)

    def bounds(name):
        gs = groups[name]
        lo = max([g["min"] for g in gs if g["min"] is not None], default=-INF)
        hi = min([g["max"] for g in gs if g["max"] is not None], default=INF)
        return lo, hi

    values = {}
    duration_ms = 0
    if goals:
        duration_ms = int(default_duration_s * 1000)
    for name in groups:
        lo, hi = bounds(name)
        if name == "time":
            t = max(1, int(hi * time_fraction)) if hi != INF else int(default_duration_s)
            if t < lo:
                t = int(lo)
            values[name] = t
            duration_ms = t * 1000 + 500
            continue
        if lo != -INF:
            v = lo
        elif hi >= 0:
            v = 0
        else:
            v = hi
        if lo > hi:
            print(f"warning: no value satisfies all goals on '{name}' "
                  f"({lo}..{hi}); marking as best effort", file=sys.stderr)
        values[name] = int(v)

    success = [in_range(values[g["value_name"]], g) for g in goals]
    score = int(sum(g["score"] for g, ok in zip(goals, success) if ok))
    passed = all(success)
    rank = sum(1 for r in sc["ranks"] if score >= r) if passed else None

    # trigger-state values describing the "run" that produced those goal values
    n = values.get("direction_change", 0)
    segments = n + 1
    final_forward = (n % 2 == 0)
    tv = {
        "exterior_camera_use": 0, "exterior_camera_move": 0, "collision": 0,
        "drive_forward": (segments + 1) // 2, "drive_backward": segments // 2,
        "direction_forward": 1 if final_forward else 0,
        "direction_backward": 0 if final_forward else 1,
        "direction_change": n,
    }
    for t in ("trans_arcade", "trans_automatic", "trans_manual", "trans_direct"):
        tv[t] = 1 if t == "trans_" + transmission else 0

    return dict(
        score=score, rank=rank, duration_ms=duration_ms,
        ids=[g["id"] for g in goals],
        values=[values[g["value_name"]] for g in goals],
        success=success,
        trig_names=[cityhash64(t) for t in sc["triggers"]],
        trig_values=[tv.get(t, 0) for t in sc["triggers"]],
        passed=passed,
    )


# ----------------------------------------------------------------------------
# Vehicle handling (raw block copy with id renaming + float encoding)
# ----------------------------------------------------------------------------
BLOCK_RE = re.compile(r"^(\w+)\s*:\s*(\S+)\s*\{\s*\n(.*?)^\}", re.M | re.S)
FLOAT_RE = re.compile(r"(?<![\w&.\"])-?\d+\.\d+(?![\w.\"])")


def enc_float(m):
    f = float(m.group(0))
    if f == int(f):
        return str(int(f))
    return "&" + struct.pack(">f", f).hex()


def convert_value_line(line):
    """Encode decimal floats as SII &hex floats, leaving quoted strings alone."""
    parts = re.split(r'("[^"]*")', line)
    return "".join(p if p.startswith('"') else FLOAT_RE.sub(enc_float, p) for p in parts)


def load_vehicle_blocks(path, vehicle_id=None):
    """Return (vehicle_unit_name, [(type, name, body_text)...]) for one vehicle."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        text = f.read().replace("\r\n", "\n")
    blocks = [(m.group(1), m.group(2), m.group(3)) for m in BLOCK_RE.finditer(text)]
    vehicles = [b for b in blocks if b[0] == "vehicle"]
    if not vehicles:
        sys.exit(f"error: no vehicle block in {path}")
    veh = next((b for b in vehicles if b[1] == vehicle_id), vehicles[0])
    refs = set(re.findall(r"accessories\[\d+\]:\s*(\S+)", veh[2]))
    keep = [veh] + [b for b in blocks if b[1] in refs]
    return veh[1], keep


class IdGen:
    def __init__(self):
        self.n = 0

    def new(self):
        self.n += 1
        return "_nameless.%x.%04x.%04x" % (0x23A + (self.n >> 32), (self.n >> 16) & 0xFFFF, self.n & 0xFFFF)


def instantiate_vehicle(blocks, idgen):
    """Rename units to fresh nameless ids, encode floats. Returns (vehicle_id, text)."""
    mapping = {b[1]: idgen.new() for b in blocks}
    out = []
    for typ, name, body in blocks:
        lines = []
        for ln in body.split("\n"):
            if not ln.strip():
                continue
            ln = convert_value_line(ln)
            for old, new in mapping.items():
                ln = re.sub(r"(?<=[\s:])" + re.escape(old) + r"$", new, ln)
            lines.append(ln if ln.startswith(" ") else " " + ln.lstrip())
        out.append(f"{typ} : {mapping[name]} {{\n" + "\n".join(lines) + "\n}\n")
    return mapping[blocks[0][1]], "\n".join(out)


def find_truck_file(academy_dir, truck_id):
    tdir = os.path.join(academy_dir, "truck")
    if not os.path.isdir(tdir):
        return None
    for fn in sorted(os.listdir(tdir)):
        if not fn.endswith(".sii"):
            continue
        p = os.path.join(tdir, fn)
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            if re.search(r"^vehicle\s*:\s*" + re.escape(truck_id) + r"\s*\{", f.read(), re.M):
                return p
    return None


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academy_dir", help="path to def/academy")
    ap.add_argument("-o", "--output", default="academy_book_states.sii")
    ap.add_argument("--books", nargs="*", help="book ids to include, e.g. book1 book2 (default: all)")
    ap.add_argument("--truck", help="academy truck id, e.g. scania.academy.r.2016 "
                                    "(default: first truck of each book that has a file in <academy>/truck)")
    ap.add_argument("--vehicle-from", metavar="SAVE.sii",
                    help="reuse the vehicle (and its accessories) from an existing save "
                         "instead of <academy>/truck - needed for ATS (no truck defs) or trucks "
                         "not in the repo. Without any truck source the books are written without one.")
    ap.add_argument("--time-fraction", type=float, default=0.5,
                    help="finish time as a fraction of the tightest time limit (default 0.5)")
    ap.add_argument("--default-duration", type=float, default=30,
                    help="seconds for scenarios without a time goal (default 30)")
    ap.add_argument("--transmission", choices=["arcade", "automatic", "manual", "direct"],
                    default="automatic", help="which trans_* trigger state is set (default automatic)")
    ap.add_argument("--include-unreferenced", action="store_true",
                    help="also add scenarios that no chapter references (legacy/unused)")
    ap.add_argument("--start-time", type=int, default=int(time.time()) - 6 * 3600,
                    help="unix time of the first log entry (default: 6h ago)")
    ap.add_argument("--lf", action="store_true", help="write LF instead of CRLF line endings")
    args = ap.parse_args()

    defs = Defs(args.academy_dir)
    idgen = IdGen()
    books = defs.books()
    if args.books:
        want = {b if b.startswith("academy.book.") else "academy.book." + b for b in args.books}
        books = [(n, d) for n, d in books if n in want]
        if not books:
            sys.exit("error: no matching books")

    t = args.start_time
    body = []       # blocks after the container
    book_state_ids, log_entry_ids, log_blocks = [], [], []
    stats = []
    warned_no_truck = False

    def log(typ, link, when):
        eid = idgen.new()
        log_entry_ids.append(eid)
        log_blocks.append(f"academy_log_entry : {eid} {{\n time: {when}\n type: {typ}\n link: {link}\n}}\n")

    for book_name, bd in books:
        # ---- vehicle ----
        # Priority: --vehicle-from save > truck file in <academy>/truck > none.
        vehicle_id, vehicle_text, truck_id = None, "", None
        if args.vehicle_from:
            veh_id_src, blocks = load_vehicle_blocks(args.vehicle_from)
            with open(args.vehicle_from, encoding="utf-8-sig", errors="replace") as f:
                m = re.search(r"^ link: (\S+\.academy\.\S+)", f.read(), re.M)
            truck_id = m.group(1) if m else veh_id_src
            vehicle_id, vehicle_text = instantiate_vehicle(blocks, idgen)
        else:
            candidates = [args.truck] if args.truck else bd.get("trucks", [])
            for c in candidates:
                p = find_truck_file(args.academy_dir, c)
                if p:
                    truck_id = c
                    _, blocks = load_vehicle_blocks(p, c)
                    vehicle_id, vehicle_text = instantiate_vehicle(blocks, idgen)
                    break
            if not vehicle_id and not warned_no_truck:
                warned_no_truck = True
                print("warning: no truck definition found in <academy>/truck (normal for ATS); "
                      "writing book states WITHOUT a truck. Pass --vehicle-from <your existing "
                      "academy_book_states.sii> to embed your own truck.", file=sys.stderr)

        # ---- scenarios ----
        order = defs.book_scenarios(book_name)
        if args.include_unreferenced:
            prefix = book_name.replace("academy.book.", "academy.scenario.") + "."
            order += [n for n, _ in defs.of_type("academy_scenario")
                      if n.startswith(prefix) and n not in order]

        if truck_id:
            log("vehicle_data", truck_id, t)
        results, n_goals = [], 0
        first = True
        t += 12
        for scn in order:
            if scn not in defs.units:
                print(f"warning: {scn} not defined, skipped", file=sys.stderr)
                continue
            model = defs.scenario(scn)
            res = build_result(model, args.time_fraction, args.default_duration, args.transmission)
            rid = idgen.new()
            results.append(rid)
            n_goals += len(model["goals"])
            if not model["goals"]:
                # intro / outro: no log entries, no duration (as in a real save)
                creation = t
            else:
                log("scenario_start", scn, t)
                t += max(1, res["duration_ms"] // 1000) + 6
                creation = t
            if model["goals"]:
                eid_link = rid
                log("scenario_end", eid_link, creation)
                t += 8
            else:
                t += 4
            L = [f"academy_scenario_result : {rid} {{", " version: 104",
                 f" creation_time: {creation}", f" scenario: {scn}", " scenario_version: 0",
                 f" scenario_score: {res['score']}",
                 f" scenario_rank: {'nil' if res['rank'] is None else res['rank']}",
                 f" scenario_duration: {res['duration_ms'] if model['goals'] else 0}"]
            for key, arr, fmt in (("goal_ids", res["ids"], str),
                                  ("goal_values", res["values"], str),
                                  ("goal_success", res["success"], lambda b: "true" if b else "false"),
                                  ("trigger_state_names", res["trig_names"], str),
                                  ("trigger_state_values", res["trig_values"], str)):
                L.append(f" {key}: {len(arr)}")
                L += [f" {key}[{i}]: {fmt(v)}" for i, v in enumerate(arr)]
            L.append("}\n")
            body.append("\n".join(L))
            stats.append((scn, res["score"], res["rank"], res["passed"]))

        bs_id = idgen.new()
        book_state_ids.append(bs_id)
        bs = [f"academy_book_state : {bs_id} {{", f" book: {book_name}"]
        if vehicle_id:
            bs.append(f" truck: {vehicle_id}")
        bs += [f" scenario_results: {len(results)}"]
        bs += [f" scenario_results[{i}]: {r}" for i, r in enumerate(results)]
        bs.append("}\n")
        # book state, then vehicle, then results (mirrors a real save)
        body.insert(len(body) - len(results), "\n".join(bs) + "\n" + vehicle_text)
        t += 20

    log_id = idgen.new()
    cont_id = idgen.new()
    head = [f"academy_save_container : {cont_id} {{", f" book_states: {len(book_state_ids)}"]
    head += [f" book_states[{i}]: {b}" for i, b in enumerate(book_state_ids)]
    head += [f" log: {log_id}", "}\n"]
    logb = [f"academy_log : {log_id} {{", f" entries: {len(log_entry_ids)}"]
    logb += [f" entries[{i}]: {e}" for i, e in enumerate(log_entry_ids)]
    logb.append("}\n")

    text = "SiiNunit\n{\n" + "\n".join(head) + "\n" + "\n".join(body) + "\n" + "\n".join(logb) + "\n" + \
           "\n".join(log_blocks) + "\n}\n"
    text = text.replace("\n\n\n", "\n\n")
    if not args.lf:
        text = text.replace("\n", "\r\n")
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    bad = [s for s in stats if not s[3]]
    print(f"wrote {args.output}: {len(books)} book(s), {len(stats)} scenarios, "
          f"{sum(1 for s in stats if s[2] == 3)} at 3 stars")
    if bad:
        print("scenarios not fully succeeded:", ", ".join(b[0] for b in bad), file=sys.stderr)


if __name__ == "__main__":
    main()
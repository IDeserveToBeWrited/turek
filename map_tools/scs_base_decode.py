#!/usr/bin/env python3
"""
scs_base_decode.py - convert raw SCS map sector ".base" files (Euro Truck
Simulator 2 / American Truck Simulator) into the annotated, human-readable
text format ("SCSAnnotatedFileV1").

NOTE: the raw .base file is not encrypted. It is a plain little-endian binary
format; this script just parses it and prints it as text.

Usage:
    python scs_base_decode.py sec+0000+0000_encrypted.base
    python scs_base_decode.py in.base -o out.txt
    python scs_base_decode.py sector_dir/                 # every *.base/*.aux/*.snd inside
    python scs_base_decode.py sector_dir/ -o decoded/     # ... written to another folder
    python scs_base_decode.py in.base --compare ref.txt   # verify vs. a known-good dump

Binary layout (all little endian)
---------------------------------
    u32   core_map_version
    token game_id                    (u64, base-38 packed string)
    u32   game_map_version
    u32   item_count
    item  * item_count               (u32 item_type selects the layout)
    u32   node_count
    node  * node_count
    u32   vis_area_child_count
    u64   * vis_area_child_count

Primitive encodings
-------------------
    u8/u16/u32/u64, s8/s16/s32, float   native little-endian
    token    u64; value = sum(idx(char_i) * 38**i), charset "\\0" "0-9" "a-z" "_"
    string   u64 length + raw bytes
    fixed3   3 x s32 (value / 256)
    float3   3 x float
    quaternion 4 x float (w, x, y, z)
"""

import argparse
import os
import struct
import sys

HEADER = "SCSAnnotatedFileV1"
EXTENSIONS = (".base", ".aux", ".snd")      # all three share one layout
TOKEN_CHARSET = "\0" "0123456789" "abcdefghijklmnopqrstuvwxyz" "_"


class FormatError(Exception):
    """Raised when the file contains something this decoder cannot interpret."""


# --------------------------------------------------------------------------- #
# value helpers
# --------------------------------------------------------------------------- #
def decode_token(value: int) -> str:
    prefix = ""
    if value >> 63:                       # high bit set: printed as "!" + the rest
        prefix, value = "!", value & ((1 << 63) - 1)
    chars = []
    while value:
        value, idx = divmod(value, 38)
        chars.append(TOKEN_CHARSET[idx])
    return prefix + "".join(chars)


def esc(s: str) -> str:
    """Escape a string the way the reference dump does."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32:
            out.append("\\x%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def f32(x: float) -> float:
    """Round to single precision (the reference prints fixed-point values via float32)."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def g(x: float) -> str:
    """Format like a C++ ostream with default precision (== printf %g)."""
    return "%g" % x


def fbits(x: float) -> str:
    return "&%08x" % struct.unpack("<I", struct.pack("<f", x))[0]


# --------------------------------------------------------------------------- #
# decoder
# --------------------------------------------------------------------------- #
class Decoder:
    def __init__(self, data: bytes):
        self.d = data
        self.p = 0
        self.out = []
        self.ind = 0
        self.section = "header"      # header / items / nodes / footer
        self.item_index = self.item_start = self.item_line = None
        self.prev_item = None        # (index, start, line) of the item before the current one
        self.line_pos = []           # byte offset reached when each output line was produced
        # constructs decoded from documentation only: their binary layout is
        # known but the exact text rendering has not been checked against a
        # reference dump. name -> location of the first occurrence.
        self.unverified = {}

    def note_unverified(self, name):
        self.unverified.setdefault(name, {
            "start": self.item_start, "line": self.item_line,
            "index": self.item_index, "pos": self.p})

    # -- low level reading ------------------------------------------------- #
    def _read(self, fmt: str):
        size = struct.calcsize("<" + fmt)
        if self.p + size > len(self.d):
            raise FormatError("unexpected end of file at offset %d" % self.p)
        v = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += size
        return v if len(v) > 1 else v[0]

    def peek_u32(self) -> int:
        return struct.unpack_from("<I", self.d, self.p)[0]

    def _string(self) -> str:
        n = self._read("Q")
        if self.p + n > len(self.d):
            raise FormatError("string runs past end of file at offset %d" % self.p)
        s = self.d[self.p:self.p + n].decode("utf-8", errors="replace")
        self.p += n
        return s

    # -- output ------------------------------------------------------------ #
    def line(self, s: str):
        self.out.append("    " * self.ind + s)
        self.line_pos.append(self.p)

    def _raw(self, s: str):
        self.out.append(s)
        self.line_pos.append(self.p)

    class _Block:
        def __init__(self, dec, open_line, close_line):
            self.dec, self.o, self.c = dec, open_line, close_line

        def __enter__(self):
            self.dec.line(self.o)
            self.dec.ind += 1

        def __exit__(self, *exc):
            self.dec.ind -= 1
            if exc[0] is None:
                self.dec.line(self.c)

    def struct_(self, name):
        return self._Block(self, "struct %s {" % name, "}")

    # -- typed fields: read + print + return value ------------------------- #
    def f(self, typ: str, name: str = ""):
        v = self._value(typ)
        self.line("%s %s: %s" % (typ, name, self._fmt(typ, v)))
        return v

    def _value(self, typ):
        if typ == "u8":
            return self._read("B")
        if typ == "u16":
            return self._read("H")
        if typ == "u32":
            return self._read("I")
        if typ == "u64":
            return self._read("Q")
        if typ == "s8":
            return self._read("b")
        if typ == "s16":
            return self._read("h")
        if typ == "s32":
            return self._read("i")
        if typ == "float":
            return self._read("f")
        if typ == "token":
            return decode_token(self._read("Q"))
        if typ == "string":
            return self._string()
        if typ == "float3":
            return self._read("fff")
        if typ == "fixed3":
            return self._read("iii")
        if typ == "quaternion":
            return self._read("ffff")
        raise FormatError("unknown type " + typ)

    @staticmethod
    def _fmt(typ, v):
        if typ in ("u8", "u16", "u32", "s8", "s16", "s32"):
            return "%d" % v
        if typ == "u64":
            return "x%X" % v
        if typ == "float":
            return "%s # %s" % (fbits(v), g(v))
        if typ == "token":
            return '"%s"' % v
        if typ == "string":
            return '"%s"' % esc(v)
        if typ == "float3":
            return "%s # x:%s y:%s z:%s" % (
                " ".join(fbits(c) for c in v), g(v[0]), g(v[1]), g(v[2]))
        if typ == "fixed3":
            return "%s # x:%s y:%s z:%s" % (
                " ".join("i%d" % c for c in v),
                g(f32(v[0] / 256.0)), g(f32(v[1] / 256.0)), g(f32(v[2] / 256.0)))
        if typ == "quaternion":
            return "%s # w:%s x:%s y:%s z:%s" % (
                " ".join(fbits(c) for c in v), g(v[0]), g(v[1]), g(v[2]), g(v[3]))
        raise FormatError("cannot format " + typ)

    # -- arrays ------------------------------------------------------------ #
    def array(self, kind: str, name: str, count: int, elem=None):
        """Print 'array_<kind> name [ ... ]'. `elem(i)` is called per element."""
        self.line("array_%s %s [" % (kind, name))
        self.ind += 1
        for i in range(count):
            if elem is not None:
                elem(i)
            elif kind == "u64":
                self.line("x%X" % self._read("Q"))
            elif kind == "u32":
                self.line("%d" % self._read("I"))
            elif kind == "token":
                self.line('"%s"' % decode_token(self._read("Q")))
            elif kind == "float":
                v = self._read("f")
                self.line("%s # %s" % (fbits(v), g(v)))
            else:
                raise FormatError("array element kind %s needs a callback" % kind)
        self.ind -= 1
        self.line("]")

    # ===================================================================== #
    # shared sub-structures
    # ===================================================================== #
    def kdop_item(self):
        with self.struct_("kdop_item"):
            self.f("u32", "item_type")
            self.f("u64", "uid")
            with self.struct_("kdop"):
                self.array("float", "minimums", 5)
                self.array("float", "maximums", 5)
            self.f("u32", "flags")
            self.f("u8", "view_dist")

    def tags(self):
        n = self.f("u32", "tags_count")
        self.array("token", "item_tags", n)

    def node_uids(self):
        n = self.f("u32", "node_count")
        self.array("u64", "node_uids", n)
        return n

    def railings(self, count=3, left_right=False):
        for _ in range(count):
            if left_right:
                self.f("token", "right_railing")
                self.f("s16", "right_railing_offset")
                self.f("token", "left_railing")
                self.f("s16", "left_railing_offset")
            else:
                self.f("token", "railing")
                self.f("s16", "railing_offset")

    def node_info(self, _i=None):
        with self.struct_("node"):
            self.f("token", "ter_profile")
            self.f("float", "ter_profile_coef")

    # ===================================================================== #
    # items
    # ===================================================================== #
    def item_road(self):
        with self.struct_("road_item"):
            self.kdop_item()
            self.f("u32", "road_flags")
            for n in ("road_look", "right_lanes_variant", "left_lanes_variant",
                      "right_tmpl_variant", "left_tmpl_variant",
                      "right_edge_right", "right_edge_left",
                      "left_edge_right", "left_edge_left", "right_profile"):
                self.f("token", n)
            self.f("float", "right_profile_coef")
            self.f("token", "left_profile")
            self.f("float", "left_profile_coef")
            for n in ("right_tmpl_look", "left_tmpl_look", "road_material"):
                self.f("token", n)
            self.railings(3, left_right=True)
            self.f("s32", "right_road_height")
            self.f("s32", "left_road_height")
            self.f("u64", "node0_uid")
            self.f("u64", "node1_uid")
            self.f("float", "length")

    def item_cut_plane(self):
        with self.struct_("cut_plane_item"):
            self.kdop_item()
            self.node_uids()

    def _subcurve(self, _i=None):
        with self.struct_("subcurve"):
            self.f("token", "model")
            self.f("u32", "flags")
            self.f("u32", "random_seed")
            self.f("float", "stretch_coef")
            self.f("float", "scale")
            self.f("float", "fixed_step")
            self.f("token", "terrain_material")
            self.f("u32", "terrain_color")
            self.f("float", "terrain_rot")
            self.f("token", "first_part")
            self.f("token", "last_part")
            self.f("token", "center_part_variation")
            self.f("token", "model_look")
            n = self.f("u32", "height_offset_count")
            self.array("float", "height_offsets", n)
            for nm in ("initial_height_offset",
                       "offset_from_base_curve_start_x",
                       "offset_from_base_curve_start_y",
                       "offset_from_base_curve_end_x",
                       "offset_from_base_curve_end_y"):
                self.f("float", nm)

    def item_curve(self):
        with self.struct_("curve_item"):
            self.kdop_item()
            self.array("u64", "node_uids", 4)
            self.f("float", "length")
            mask = self.f("u32", "subcurve_use_mask")
            self.array("struct", "subcurves", bin(mask).count("1"), self._subcurve)

    def _vegetation(self, side):
        def one(_i):
            with self.struct_(side + "_vegetation"):
                self.f("token", "vegetation")
                self.f("u16", "density")
                self.f("u8", "hi_poly_distance")
                self.f("u8", "scale_type")
                self.f("u16", "start")
                self.f("u16", "end")
        self.array("struct", "vegetation", 3, one)

    def _veg_spheres(self):
        def sphere(_i):
            with self.struct_("veg_sphere"):
                self.f("float3", "center")
                self.f("float", "radius")
                self.f("u32", "type")
        n = self.f("u32", "veg_sphere_count")
        self.array("struct", "veg_spheres", n, sphere)

    def _quad_info(self):
        with self.struct_("quad_info"):
            n = self.f("u16", "material_count")
            for _ in range(n):
                self.f("token", "material")
                self.f("u16", "material_rot")
            n = self.f("u16", "color_count")
            for _ in range(n):
                self.f("u32", "color")
            self.f("u16", "size_x")
            self.f("u16", "size_y")
            n = self.f("u32", "storage_size")
            for _ in range(n):
                self.f("u32", "data")
            n = self.f("u32", "offset_count")
            for _ in range(n):
                self.f("u16", "offset_pos_x")
                self.f("u16", "offset_pos_y")
                self.f("float3", "data")
            n = self.f("u32", "normal_count")
            for _ in range(n):
                self.f("u16", "normal_pos_x")
                self.f("u16", "normal_pos_y")
                self.f("float3", "data")

    def item_terrain(self):
        with self.struct_("terrain_item"):
            self.kdop_item()
            self.f("u64", "node0_uid")
            self.f("u64", "node1_uid")
            self.f("float3", "node0_offset")
            self.f("float3", "node1_offset")
            self.f("float", "length")
            self.f("float", "previous_length")
            self.f("u32", "rnd_seed")
            self.railings(3)
            self.f("u16", "right_terrain_size")
            self.f("token", "right_profile")
            self.f("float", "right_profile_coef")
            self.f("token", "right_prev_profile")
            self.f("float", "right_prev_profile_coef")
            self._vegetation("right")
            self.f("u16", "right_dvdm")
            self.f("u16", "right_dvd")
            self.f("u16", "left_terrain_size")
            self.f("token", "left_profile")
            self.f("float", "left_profile_coef")
            self.f("token", "left_prev_profile")
            self.f("float", "left_prev_profile_coef")
            self._vegetation("left")
            self.f("u16", "left_dvdm")
            self.f("u16", "left_dvd")
            self._veg_spheres()
            self._quad_info()
            self._quad_info()
            for nm in ("right_edge", "right_edge_look",
                       "left_edge", "left_edge_look"):
                self.f("token", nm)

    def item_model(self):
        with self.struct_("model_item"):
            self.kdop_item()
            self.f("token", "model")
            self.f("token", "model_look")
            self.f("token", "model_variant")
            self._add_parts()
            self.f("u64", "node_uid")
            self.f("float", "scale_x")
            self.f("float", "scale_y")
            self.f("float", "scale_z")
            self.f("token", "terrain_material")
            self.f("u32", "terrain_color")
            self.f("float", "terrain_rot")

    def _add_parts(self):
        n = self.f("u32", "add_parts_count")

        def part(_i):
            self.line('"%s" # part' % decode_token(self._read("Q")))
        self.array("token", "add_parts", n, part)

    def item_prefab(self):
        with self.struct_("prefab_item"):
            self.kdop_item()
            self.f("token", "prefab_model")
            self.f("token", "prefab_variant")
            self._add_parts()
            nodes = self.node_uids()
            n = self.f("u32", "slave_count")
            self.array("u64", "slave_uids", n)
            self.f("u64", "ferry_link_uid")
            self.f("u16", "origin_idx")
            self.array("struct", "node_infos", nodes, self.node_info)
            self.f("token", "semaphores")

    def item_map_area(self):
        with self.struct_("map_area_item"):
            self.kdop_item()
            self.node_uids()
            self.f("u32", "color")

    def _sign_override(self):
        def attribute(_i):
            with self.struct_("sign_override_attribute"):
                t = self.f("u16", "type")
                self.f("u32", "index")
                if t == 1:
                    self.f("s8", "bvalue")
                elif t == 2:
                    self.f("s32", "ivalue")
                elif t == 3:
                    self.f("u32", "uvalue")
                elif t == 4:
                    self.f("float", "fvalue")
                elif t == 5:
                    self.f("string", "svalue")
                elif t == 6:
                    self.f("u64", "u64value")
                else:
                    raise FormatError("unknown sign override attribute type %d" % t)

        def item(_i):
            with self.struct_("sign_override_item"):
                self.f("u32", "id")
                self.f("token", "area_name")
                n = self.f("u32", "attribute_count")
                self.array("struct", "attributes", n, attribute)

        def board_override(_i):
            # binary layout per the unofficial map-docs wiki; the text
            # rendering (struct/field names) is a best guess - no sample yet.
            with self.struct_("board_override"):
                self.f("token", "area_name")
                flags = self.f("u8", "flags")
                if flags & 1:
                    self.f("s8", "x")
                    self.f("s8", "y")
                if flags & 2:
                    self.f("token", "board_def")

        with self.struct_("sign_override"):
            n = self.f("u32", "board_override_count")
            if n:
                self.note_unverified("sign board_overrides")
            self.array("struct", "board_overrides", n, board_override)
            n = self.f("u32", "item_count")
            self.array("struct", "items", n, item)

    def item_sign(self):
        with self.struct_("sign_item"):
            self.kdop_item()
            self.f("token", "sign_model")
            self.f("u64", "node_uid")
            self.f("token", "sign_look")
            self.f("token", "sign_variant")
            boards = self.f("u8", "board count")
            if boards:                       # (the array is omitted when empty)
                def board(_i):
                    with self.struct_("sign_board"):
                        self.f("token", "road")
                        self.f("token", "city1")
                        self.f("token", "city2")
                self.array("struct", "sign_boards", boards, board)
            tmpl = self.f("string", "override_template")
            if tmpl:
                self._sign_override()

    def item_city(self):
        with self.struct_("city_item"):
            self.kdop_item()
            self.f("token", "city")
            self.f("float", "width")
            self.f("float", "height")
            self.f("u64", "node_uid")

    def item_traffic_area(self):
        with self.struct_("traffic_area_item"):
            self.kdop_item()
            self.tags()
            self.node_uids()
            self.f("token", "rule")
            self.f("float", "range")

    def item_trajectory(self):
        def rule(_i):
            with self.struct_("rule_item"):
                self.f("u32", "rule_item_node_idx")
                self.f("token", "rule_item_rule")
                n = self.f("u32", "rule_item_params_count")

                def param(i):
                    v = self._read("f")
                    self.line("%s # rule_item_param%d - %s" % (fbits(v), i + 1, g(v)))
                self.array("float", "rule_item_params", n, param)

        def checkpoint(_i):
            with self.struct_("checkpoint_item"):
                self.f("token", "checkpoint_item_route")
                self.f("token", "checkpoint_item_token")

        with self.struct_("trajectory_item"):
            self.kdop_item()
            self.node_uids()
            self.f("token", "access_rule")
            n = self.f("u32", "rules_count")
            self.array("struct", "rules", n, rule)
            n = self.f("u32", "checkpoints_count")
            self.array("struct", "checkpoints", n, checkpoint)
            self.tags()

    def _action_params(self):
        """Body shared by trigger 'custom_params' and cutscene 'action_params'."""
        n = self.f("u32", "num_param_count")
        if n == 0xFFFFFFFF:
            return                                   # "no params" marker
        for _ in range(n):
            self.f("float", "")                      # unnamed float parameter
        n = self.f("u32", "str_param_count")
        for _ in range(n):
            self.f("string", "")                     # unnamed string parameter
        n = self.f("u32", "target_tag_count")
        for _ in range(n):
            self.f("token", "")                      # unnamed target tag
        self.f("float", "target_range")
        self.f("u32", "action_flags")

    def item_trigger(self):
        def action(_i):
            with self.struct_("action"):
                self.f("token", "name")
                with self.struct_("custom_params"):
                    self._action_params()

        with self.struct_("trigger_item"):
            self.kdop_item()
            self.tags()
            nodes = self.node_uids()
            n = self.f("u32", "action_count")
            self.array("struct", "actions", n, action)
            if nodes == 1:                   # legacy single-node trigger (map-docs wiki)
                self.f("float", "trigger_range")

    def item_visibility_area(self):
        with self.struct_("visibility_area_item"):
            self.kdop_item()
            self.f("u64", "node_uid")
            self.f("float", "half_size_x")
            self.f("float", "half_size_y")
            n = self.f("u32", "children_count")
            for _ in range(n):
                self.f("u64", "child_uid")

    def item_map_overlay(self):
        with self.struct_("map_overlay_item"):
            self.kdop_item()
            self.f("token", "look_name")
            self.f("u64", "node_uid")

    def item_company(self):
        with self.struct_("company_item"):
            with self.struct_("economy_link_item"):
                self.kdop_item()
                self.f("token", "linked_city_name")
                self.f("u64", "linked_item_uid")
            self.f("token", "company_name")
            self.f("u64", "node_uid")
            n = self.node_uids()
            self.array("u32", "node_flags", n)

    def item_services(self):
        with self.struct_("services_item"):
            self.kdop_item()
            self.f("u64", "node_uid")
            self.f("u64", "prefab_link_uid")
            self.node_uids()

    def item_garage(self):
        with self.struct_("garage_item"):
            self.kdop_item()
            self.f("token", "city_name")
            self.f("u32", "buy_mode")
            self.f("u64", "node_uid")
            self.f("u64", "prefab_link_uid")
            self.node_uids()

    def item_buildings(self):
        with self.struct_("buildings_item"):
            self.kdop_item()
            self.f("token", "scheme")
            self.f("token", "look_override")
            self.array("u64", "node_uids", 2)
            self.f("float", "length")
            self.f("u32", "random_seed")
            self.f("float", "stretch_coef")
            n = self.f("u32", "building_height_offset_count")
            self.array("float", "building_height_offsets", n)

    def item_bezier_patch(self):
        with self.struct_("bezier_patch_item"):
            self.kdop_item()
            for _ in range(16):
                self.f("float3", "ctrl_point")
            self.f("u16", "x_tess")
            self.f("u16", "z_tess")
            self.f("u64", "node_uid")
            self.f("u32", "rnd_seed")
            for _ in range(3):
                with self.struct_("vegetation"):
                    self.f("token", "vegetation")
                    self.f("u16", "density")
                    self.f("u8", "scale_type")
            self._veg_spheres()
            self._quad_info()                # a bezier patch has ONE quad_info

    def item_ferry(self):
        with self.struct_("ferry_item"):
            self.kdop_item()
            self.f("token", "ferry_name")
            self.f("u64", "prefab_link_uid")
            self.f("u64", "node_uid")
            self.f("float3", "unload_offset")

    def item_cutscene(self):
        def action(_i):
            with self.struct_("action_params"):
                self._action_params()

        with self.struct_("cutscene_item"):
            self.kdop_item()
            self.tags()
            self.f("u64", "node_uid")
            n = self.f("u32", "action_count")
            self.array("struct", "actions", n, action)

    # item_type -> handler
    ITEM_TYPES = {
        1: "item_terrain",
        2: "item_buildings",
        3: "item_road",
        4: "item_prefab",
        5: "item_model",
        6: "item_company",
        7: "item_services",
        8: "item_cut_plane",
        12: "item_city",
        18: "item_map_overlay",
        19: "item_ferry",
        22: "item_garage",
        34: "item_trigger",
        35: "item_services",
        36: "item_sign",
        38: "item_traffic_area",
        39: "item_bezier_patch",
        41: "item_trajectory",
        42: "item_map_area",
        44: "item_curve",
        46: "item_cutscene",
        48: "item_visibility_area",
    }

    def item(self, _i=None):
        # remember where this item starts (used for error reports / sample collection)
        if self.item_start is not None:
            self.prev_item = (self.item_index, self.item_start, self.item_line)
        self.item_index, self.item_start, self.item_line = _i, self.p, len(self.out)
        if self.p + 4 > len(self.d):
            raise FormatError("unexpected end of file at offset %d" % self.p)
        t = self.peek_u32()
        handler = self.ITEM_TYPES.get(t)
        if handler is None:
            raise FormatError("unknown item type %d at offset %d" % (t, self.p))
        getattr(self, handler)()

    def node_item(self, _i=None):
        with self.struct_("node_item"):
            self.f("u64", "uid")
            self.f("fixed3", "position")
            self.f("quaternion", "rotation")
            self.f("u64", "backward_item_uid")
            self.f("u64", "forward_item_uid")
            self.f("u32", "flags")

    # ===================================================================== #
    # whole file
    # ===================================================================== #
    def decode(self) -> str:
        self._raw(HEADER)
        self._raw("")
        self.f("u32", "core_map_version")
        self.f("token", "game_id")
        self.f("u32", "game_map_version")
        n = self.f("u32", "item_count")
        self.section = "items"
        self.array("struct", "items", n, self.item)
        n = self.f("u32", "node_count")
        self.section = "nodes"
        self.array("struct", "nodes", n, self.node_item)
        self.section = "footer"
        n = self.f("u32", "vis_area_child_count")
        self.array("u64", "uids", n,
                   lambda _i: self.line("x%X # child_uid" % self._read("Q")))
        if self.p != len(self.d):
            raise FormatError("%d unparsed byte(s) left at offset %d"
                              % (len(self.d) - self.p, self.p))
        self._raw("")
        self._raw("# EOF #")
        return "\n".join(self.out) + "\n"


def decode_bytes(data: bytes) -> str:
    return Decoder(data).decode()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _output_path(path: str, output, input_is_dir: bool, ext: str) -> str:
    """Decide where the decoded text for `path` goes."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if input_is_dir:
        if output:                                  # -o is an output *folder*
            os.makedirs(output, exist_ok=True)
            return os.path.join(output, stem + ext)
        return os.path.join(os.path.dirname(path), stem + "_decoded" + ext)
    if output:
        if os.path.isdir(output) or output.endswith(("/", os.sep)):
            os.makedirs(output, exist_ok=True)      # -o is a folder
            return os.path.join(output, stem + ext)
        parent = os.path.dirname(output)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return output                               # -o is a file
    return os.path.join(os.path.dirname(path), stem + "_decoded" + ext)


def _first_diff(a: str, b: str):
    al, bl = a.split("\n"), b.split("\n")
    for i, (x, y) in enumerate(zip(al, bl)):
        if x != y:
            return i + 1, x, y
    if len(al) != len(bl):
        return min(len(al), len(bl)) + 1, "<end>", "<end>"
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help=".base file or a directory containing .base files")
    ap.add_argument("-o", "--output",
                    help="output file; if the input is a folder (or this is an "
                         "existing folder) it is used as the output folder")
    ap.add_argument("--ext", default=".txt",
                    help="extension for generated output files (default: .txt)")
    ap.add_argument("--compare", metavar="REF",
                    help="compare the result with a reference text file")
    args = ap.parse_args(argv)

    input_is_dir = os.path.isdir(args.input)
    if input_is_dir:
        files = sorted(os.path.join(args.input, f) for f in os.listdir(args.input)
                       if f.lower().endswith(EXTENSIONS))
    else:
        files = [args.input]
    if not files:
        print("no .base files found", file=sys.stderr)
        return 1
    rc = 0
    for path in files:
        try:
            with open(path, "rb") as fh:
                d = Decoder(fh.read())
                text = d.decode()
        except FormatError as e:
            print("%s: ERROR: %s" % (path, e), file=sys.stderr)
            rc = 1
            continue
        out = _output_path(path, args.output, input_is_dir, args.ext)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("%s -> %s (%d lines)" % (path, out, text.count("\n")))
        for name in d.unverified:
            print("  note: contains %s - binary layout is documented but its text "
                  "rendering is unverified; check it against a reference dump" % name,
                  file=sys.stderr)
        if args.compare:
            with open(args.compare, encoding="utf-8", newline="") as fh:
                ref = fh.read()
            d = _first_diff(text, ref)
            if d is None:
                print("compare: IDENTICAL to %s" % args.compare)
            else:
                print("compare: DIFFERENT at line %d\n  ours: %s\n  ref : %s" % d)
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
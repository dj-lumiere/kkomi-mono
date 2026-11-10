#!/usr/bin/env python3
"""Builds Wanted Sans Mono, a fixed-width version of Wanted Sans for editors and terminals.

Every Latin, symbol and mark glyph gets one cell (885 units, half the Hangul width).
Hangul and other East Asian wide characters get two cells (1770 units), which is the
width they already have, so the Hangul glyphs are kept as they are.

A glyph wider than its cell is narrowed horizontally. Narrowing thins its vertical
strokes, so the outline is taken from a heavier instance of the variable font before
it is narrowed. ALPHA sets how much of the lost stroke width this gives back.

Proportional features (kerning, the original contextual alternates and ligatures) are
turned off. The `calt` feature is replaced with coding ligatures that keep the cell grid:
the leading characters become empty spacer glyphs and the last one draws the whole shape
leftwards over their cells.

Needs: fonttools, skia-pathops.
Usage: make_mono.py <wanted sans folder> <output folder>
"""
import copy
import math
import os
import shutil
import sys
import unicodedata

from fontTools.feaLib.builder import Builder
from fontTools.feaLib.parser import Parser
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.varLib import instancer
from io import StringIO

CELL = 885
WIDE = 2 * CELL
MARGIN = 45            # smallest side bearing a narrowed glyph keeps
MARK_SCALE = 0.8       # horizontal scale for zero-width combining marks
ALPHA = 0.6            # 0 = no stroke compensation, 1 = full compensation
WEIGHT_STEP = 25       # donor instances are taken on this grid of the wght axis

STYLES = [
    ("Regular", 400), ("Medium", 500), ("SemiBold", 600), ("Bold", 700),
    ("ExtraBold", 800), ("Black", 900), ("ExtraBlack", 1000),
]

OLD_FAMILY = "Wanted Sans"
NEW_FAMILY = "Wanted Sans Mono"
OLD_PS = "WantedSans"
NEW_PS = "WantedSansMono"

# Features whose effect depends on proportional widths. Their lookups are unhooked.
DROP_GSUB = {"calt", "clig", "dlig", "liga"}
DROP_GPOS = {"kern"}

# Glyphs that are easy to confuse in code get the font's own distinct alternate as
# their default shape: slashed zero, I with serifs, l with a tail.
BAKE_ALTERNATES = {"zero": "zero.zero", "I": "I.cv18", "l": "l.cv16"}

# (name, characters). Longer sequences come first so they win over their prefixes.
LIGATURES = [
    ("less_hyphen_greater", "<->"),
    ("less_equal_greater", "<=>"),
    ("equal_equal_equal", "==="),
    ("exclam_equal_equal", "!=="),
    ("hyphen_hyphen_greater", "-->"),
    ("less_hyphen_hyphen", "<--"),
    ("equal_equal_greater", "==>"),
    ("less_equal_equal", "<=="),
    ("tilde_tilde_greater", "~~>"),
    ("hyphen_greater", "->"),
    ("less_hyphen", "<-"),
    ("equal_greater", "=>"),
    ("equal_equal", "=="),
    ("exclam_equal", "!="),
    ("less_equal", "<="),     # only when the font has its own ≤ and ≥
    ("greater_equal", ">="),
    ("tilde_greater", "~>"),
    ("less_tilde", "<~"),
    ("bar_greater", "|>"),
    ("less_bar", "<|"),
    ("slash_backslash", "/\\"),
    ("backslash_slash", "\\/"),
    ("period_period_period", "..."),
    ("colon_equal", ":="),
    ("ampersand_ampersand", "&&"),
    ("bar_bar", "||"),
]
# These are off by default and turned on with their feature: not everyone reads
# `&&` and `||` as the logic symbols.
STYLISTIC = {"ampersand_ampersand": "ss01", "bar_bar": "ss01"}
FEATURE_NAMES = {
    "ss01": "Logic symbols for && and ||",
    "ss02": "Original 0 i j l",
    "ss03": "Italic letters without cursive forms",
    "ss04": "Visible Hangul fillers",
}
# Alternate glyphs turned on by a feature: tag -> [(glyph, alternate)]. The build adds
# to it before the features are written.
ALTERNATES = {}
# Drawn after the symbols, from the font's own symbol widened to two cells.
FROM_SYMBOL = {"ampersand_ampersand": 0x2227, "bar_bar": 0x2228}
# A ligature is not formed when one of these stands right before or after it,
# so `<!--`, `<==>`, `<|>` and `====` keep their plain characters.
OPERATOR_CHARS = "-=<>!~|/\\"
# These also need a space (or anything but a letter, digit or _) on both sides, so
# regular expressions (`/\d+/`) and escaped slashes (`http:\/\/`) stay as typed.
WORD_GUARDED = {"slash_backslash", "backslash_slash"}
# Ligatures guarded by other characters than OPERATOR_CHARS: `....` keeps its dots,
# `::=` its colons, `&&&` its ampersands.
GUARD_CHARS = {
    "period_period_period": ".",
    "colon_equal": OPERATOR_CHARS + ":",
    "ampersand_ampersand": OPERATOR_CHARS + "&",
}
LIGATURE_CHARS = "".join(sorted(set(OPERATOR_CHARS + "".join(c for _, c in LIGATURES)
                                    + "".join(GUARD_CHARS.values()))))


# ---------------------------------------------------------------- outlines

def record(glyph_set, name):
    pen = DecomposingRecordingPen(glyph_set, reverseFlipped=True)
    glyph_set[name].draw(pen)
    return pen.value


def bounds(ops):
    pen = BoundsPen(None)
    for op, args in ops:
        getattr(pen, op)(*args)
    return pen.bounds


def transformed(ops, sx, dx, sy=1.0, dy=0.0):
    out = RecordingPen()
    pen = TransformPen(out, (sx, 0, 0, sy, dx, dy))
    for op, args in ops:
        getattr(pen, op)(*args)
    return out.value


def to_glyph(ops):
    pen = TTGlyphPen(None)
    for op, args in ops:
        getattr(pen, op)(*args)
    glyph = pen.glyph(dropImpliedOnCurves=False)
    if glyph.numberOfContours > 0:
        glyph.coordinates.toInt()
    return glyph


CLOCKWISE = True  # set from the font in add_ligatures


def rect(x0, y0, x1, y1):
    pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
    return quad(pts)


def quad(pts):
    # pts are given clockwise. Filled contours must turn the same way as the font's
    # own, or removing overlaps would cut holes where they cross.
    if not CLOCKWISE:
        pts = pts[::-1]
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def signed_area(pts):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])) / 2


def polygon_points(ops):
    contours, cur = [], []
    for op, args in ops:
        if op == "moveTo":
            cur = [args[0]]
        elif op in ("lineTo", "qCurveTo", "curveTo"):
            cur.extend(a for a in args if a is not None)
        elif op in ("closePath", "endPath"):
            if cur:
                contours.append(cur)
            cur = []
    return contours


def crossings(ops, y):
    xs = []
    for pts in polygon_points(ops):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
    return sorted(xs)


# ---------------------------------------------------------------- donors

class Donors:
    """Heavier instances of the variable font, used for narrowed glyphs."""

    def __init__(self, var_path, glyph_names):
        self.var = TTFont(var_path)
        keep = set(glyph_names) & set(self.var.getGlyphOrder())
        # Drop the Hangul outlines and layout tables so each instance is quick to make.
        from fontTools import subset
        opts = subset.Options()
        opts.glyph_names = True
        opts.layout_features = []
        opts.notdef_outline = True
        opts.name_IDs = []
        opts.drop_tables += ["GSUB", "GPOS", "GDEF", "STAT"]
        sub = subset.Subsetter(opts)
        sub.populate(glyphs=keep)
        sub.subset(self.var)
        self.cache = {}

    def glyph_set(self, wght):
        if wght not in self.cache:
            inst = instancer.instantiateVariableFont(self.var, {"wght": wght})
            self.cache[wght] = inst.getGlyphSet()
        return self.cache[wght]


class StemCurve:
    """Vertical stem width of `l` against the wght value, from the static fonts."""

    def __init__(self, samples):
        self.samples = sorted(samples)

    def stem(self, w):
        s = self.samples
        for (w0, t0), (w1, t1) in zip(s, s[1:]):
            if w0 <= w <= w1:
                return t0 + (t1 - t0) * (w - w0) / (w1 - w0)
        return s[0][1] if w < s[0][0] else s[-1][1]

    def weight_for(self, stem):
        s = self.samples
        if stem <= s[0][1]:
            return s[0][0]
        for (w0, t0), (w1, t1) in zip(s, s[1:]):
            if t0 <= stem <= t1:
                return w0 + (w1 - w0) * (stem - t0) / (t1 - t0)
        return s[-1][0]


# ---------------------------------------------------------------- per font

def classify(font):
    hmtx = font["hmtx"]
    codepoints = {}
    for cp, name in font.getBestCmap().items():
        codepoints.setdefault(name, []).append(cp)
    kinds = {}
    for name in font.getGlyphOrder():
        adv = hmtx[name][0]
        cps = codepoints.get(name, [])
        if adv == 0:
            kinds[name] = "zero"
        elif any(unicodedata.east_asian_width(chr(cp)) in "WF" for cp in cps):
            kinds[name] = "wide"
        elif not cps and adv == WIDE:
            kinds[name] = "wide"
        else:
            kinds[name] = "narrow"
    return kinds


def joins(b, adv, box):
    return b[0] <= 0 and b[2] >= adv and adv > box


def fit(ops, adv, box, donor_ops=None):
    """Places a glyph in a box `box` units wide. Returns (new ops, (s, src_center, dst_center))."""
    b = bounds(ops)
    if b is None:
        return [], (1.0, 0.0, 0.0)
    x0, _, x1, _ = b
    # A wide glyph whose ink reaches its advance edges joins its neighbours (underscore,
    # horizontal bars). Its advance box is mapped onto the cell so it keeps joining.
    if joins(b, adv, box):
        s = box / adv
        return transformed(ops, s, 0.0), (s, 0.0, 0.0)
    avail = box - 2 * MARGIN
    s = min(1.0, avail / (x1 - x0))
    src = donor_ops if donor_ops is not None else ops
    db = bounds(src)
    dx0, _, dx1, _ = db
    sd = min(s, avail / (dx1 - dx0))
    center = (dx0 + dx1) / 2
    return transformed(src, sd, box / 2 - sd * center), (sd, (x0 + x1) / 2, box / 2)


def build_style(src_path, wght, donors, stems, out_path):
    font = TTFont(src_path)
    glyph_set = font.getGlyphSet()
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    kinds = classify(font)
    xforms = {}
    changed = []
    base_stem = stems.stem(wght)

    for name in font.getGlyphOrder():
        kind = kinds[name]
        adv = hmtx[name][0]
        if kind == "wide" and adv == WIDE and not glyf[name].isComposite():
            continue  # Hangul: already two cells
        ops = record(glyph_set, name)
        if kind == "zero":
            new_ops = transformed(ops, MARK_SCALE, 0.0)
            xforms[name] = (MARK_SCALE, 0.0, 0.0)
            new_adv = 0
        else:
            box = WIDE if kind == "wide" else CELL
            donor_ops = None
            b = bounds(ops)
            if b is not None and not joins(b, adv, box):
                s = (box - 2 * MARGIN) / (b[2] - b[0])
                if s < 0.97:
                    want = base_stem * (1 + ALPHA * (1 / s - 1))
                    w = round(stems.weight_for(want) / WEIGHT_STEP) * WEIGHT_STEP
                    w = min(1000, max(wght, w))
                    if w > wght:
                        dset = donors.glyph_set(w)
                        if name in dset:
                            donor_ops = record(dset, name)
            new_ops, xforms[name] = fit(ops, adv, box, donor_ops)
            new_adv = box
        glyf[name] = to_glyph(new_ops)
        hmtx[name] = (new_adv, 0)
        changed.append(name)

    for base, alt in BAKE_ALTERNATES.items():
        if base in glyf and alt in glyf:
            glyf[base] = copy.deepcopy(glyf[alt])
    transform_anchors(font, xforms)
    unhook_features(font)
    lig_names = add_ligatures(font, kinds)
    changed += lig_names

    removeOverlaps(font, glyphNames=changed, removeHinting=True, ignoreErrors=True)
    for name in font.getGlyphOrder():
        g = glyf[name]
        g.recalcBounds(glyf)
        hmtx[name] = (hmtx[name][0], getattr(g, "xMin", 0) if g.numberOfContours else 0)

    finish_tables(font)
    rename(font)
    font.save(out_path)


# ---------------------------------------------------------------- GPOS anchors

def transform_anchors(font, xforms):
    if "GPOS" not in font:
        return
    seen = set()

    def move(anchor, glyph):
        if anchor is None or id(anchor) in seen or glyph not in xforms:
            return
        seen.add(id(anchor))
        s, src, dst = xforms[glyph]
        anchor.XCoordinate = round(s * (anchor.XCoordinate - src) + dst)

    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            ltype = lookup.LookupType
            if ltype == 9:
                ltype, st = st.ExtensionLookupType, st.ExtSubTable
            if ltype == 4:
                for g, rec in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord):
                    move(rec.MarkAnchor, g)
                for g, rec in zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord):
                    for a in rec.BaseAnchor:
                        move(a, g)
            elif ltype == 5:
                for g, rec in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord):
                    move(rec.MarkAnchor, g)
                for g, att in zip(st.LigatureCoverage.glyphs, st.LigatureArray.LigatureAttach):
                    for comp in att.ComponentRecord:
                        for a in comp.LigatureAnchor:
                            move(a, g)
            elif ltype == 6:
                for g, rec in zip(st.Mark1Coverage.glyphs, st.Mark1Array.MarkRecord):
                    move(rec.MarkAnchor, g)
                for g, rec in zip(st.Mark2Coverage.glyphs, st.Mark2Array.Mark2Record):
                    for a in rec.Mark2Anchor:
                        move(a, g)


def unhook_features(font):
    for tag, drop in (("GSUB", DROP_GSUB), ("GPOS", DROP_GPOS)):
        for fr in font[tag].table.FeatureList.FeatureRecord:
            if fr.FeatureTag in drop:
                fr.Feature.LookupListIndex = []
                fr.Feature.LookupCount = 0


# ---------------------------------------------------------------- ligatures

def add_ligatures(font, kinds, relation=None, extra_fea=""):
    """relation, when given, is ((kx, ky), weight): `<=` and `>=` then become the font's
    own < and > squeezed by kx and ky over a bar, with weight(ops, dx, dy) giving back
    the stroke width the squeeze took."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    gname = {ch: cmap[ord(ch)] for ch in LIGATURE_CHARS}

    hyphen = bounds(record(glyph_set, gname["-"]))
    axis = (hyphen[1] + hyphen[3]) / 2
    stroke = hyphen[3] - hyphen[1]
    equal_ops = record(glyph_set, gname["="])
    equal = bounds(equal_ops)
    eq_bar = bounds(polygon_points_ops(equal_ops)[0])
    eq_stroke = eq_bar[3] - eq_bar[1]
    eq_gap = (equal[3] - equal[1]) - 2 * eq_stroke
    greater = record(glyph_set, gname[">"])
    global CLOCKWISE
    CLOCKWISE = signed_area(polygon_points(greater)[0]) < 0
    less = record(glyph_set, gname["<"])
    slash = slash_of(font, glyph_set)

    def shaft_end(chev, y0, y1, right_side):
        inner, outer = [], []
        for y in (y0 + 1, (y0 + y1) / 2, y1 - 1):
            xs = crossings(chev, y)
            if len(xs) < 2:
                continue
            if right_side:
                outer.append(xs[-1]); inner.append(xs[-2])
            else:
                outer.append(xs[0]); inner.append(xs[1])
        if right_side:
            return (max(inner) + min(outer)) / 2
        return (min(inner) + max(outer)) / 2

    def bars(count, gap):
        total = count * eq_stroke + (count - 1) * gap
        top = axis + total / 2
        return [(top - i * (eq_stroke + gap) - eq_stroke, top - i * (eq_stroke + gap))
                for i in range(count)]

    left_hy = hyphen[0]
    left_eq = equal[0]
    hyphen_ops = record(glyph_set, gname["-"])

    def bar(x0, x1, yc):
        # The font's own hyphen, lengthened in the middle so its ends keep their shape.
        hx0, hy0, hx1, hy1 = hyphen
        mid = (hx0 + hx1) / 2
        dy = yc - (hy0 + hy1) / 2
        return [(op, tuple(None if pt is None else
                           (pt[0] + (x0 - hx0 if pt[0] < mid else x1 - hx1), pt[1] + dy)
                           for pt in args)) for op, args in hyphen_ops]

    shapes = {}
    W2, W3 = 2 * CELL, 3 * CELL

    # ->  <-  <->
    g_right = transformed(greater, 1.0, W2 - CELL)
    end = shaft_end(g_right, axis - stroke / 2, axis + stroke / 2, True)
    shapes["hyphen_greater"] = (2, g_right + bar(left_hy, end, axis))
    l_left = less
    start = shaft_end(l_left, axis - stroke / 2, axis + stroke / 2, False)
    shapes["less_hyphen"] = (2, l_left + bar(start, W2 - (CELL - hyphen[2]), axis))
    g3 = transformed(greater, 1.0, W3 - CELL)
    end3 = shaft_end(g3, axis - stroke / 2, axis + stroke / 2, True)
    shapes["less_hyphen_greater"] = (3, less + g3 + bar(start, end3, axis))

    # =>
    ops = list(g_right)
    for y0, y1 in bars(2, eq_gap):
        ops += bar(left_eq, shaft_end(g_right, y0, y1, True), (y0 + y1) / 2)
    shapes["equal_greater"] = (2, ops)

    # ==  ===  !=  !==
    def bar_ops(n, count, gap):
        out = []
        for y0, y1 in bars(count, gap):
            out += bar(left_eq, n * CELL - (CELL - equal[2]), (y0 + y1) / 2)
        return out

    gap3 = eq_gap
    shapes["equal_equal"] = (2, bar_ops(2, 2, eq_gap))
    shapes["equal_equal_equal"] = (3, bar_ops(3, 3, gap3))
    slash_glyph = record(glyph_set, cmap[ord("/")]) if relation is not None else None

    def slash_ops(cx, extra):
        if relation is None:
            return slash(cx, axis, extra)
        # the font's own / with its round ends, as tall as the bars plus an overhang
        sb0 = bounds(slash_glyph)
        height = (bars_height(extra) + 2 * eq_stroke * 1.6)
        k = height / (sb0[3] - sb0[1])
        ops = transformed(slash_glyph, k, cx - k * (sb0[0] + sb0[2]) / 2,
                          k, axis - k * (sb0[1] + sb0[3]) / 2)
        # thicken the stroke to the bars' thickness, measured across the stroke
        sb = bounds(ops)
        xs = crossings(ops, (sb[1] + sb[3]) / 2)
        across_x = xs[-1] - xs[0]
        run = (sb[2] - sb[0]) - across_x
        rise = sb[3] - sb[1]
        across = across_x * rise / math.hypot(run, rise)
        grow = eq_stroke - across
        return relation[1](ops, grow, grow) if abs(grow) > 1 else ops

    def bars_height(extra):
        return 2 * eq_stroke + eq_gap + extra

    shapes["exclam_equal"] = (2, bar_ops(2, 2, eq_gap) + slash_ops(W2 / 2, 0))
    tall3 = (3 * eq_stroke + 2 * gap3) - (2 * eq_stroke + eq_gap)
    shapes["exclam_equal_equal"] = (3, bar_ops(3, 3, gap3) + slash_ops(W3 / 2, tall3))

    # <=>
    ops = less + g3
    for y0, y1 in bars(2, eq_gap):
        ops += bar(shaft_end(less, y0, y1, False), shaft_end(g3, y0, y1, True), (y0 + y1) / 2)
    shapes["less_equal_greater"] = (3, ops)

    # <=  >=  as the font's own < and > with a copy of the lower arm set under it
    if relation is not None:
        kx, ky = relation[0]
        weight = relation[1]
        for name, chev, tip_right in (("less_equal", less, False), ("greater_equal", greater, True)):
            cb = bounds(chev)
            ccx, ccy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
            flat = transformed(chev, kx, -kx * ccx, ky, -ky * ccy)
            flat = weight(flat, stroke * (1 - kx), stroke * (1 - ky))
            fb = bounds(flat)
            r = stroke / 2
            tip = (fb[2] - r if tip_right else fb[0] + r, (fb[1] + fb[3]) / 2)
            end_ = (fb[0] + r if tip_right else fb[2] - r, fb[1] + r)
            vx, vy = end_[0] - tip[0], end_[1] - tip[1]
            vl = math.hypot(vx, vy)
            vx, vy = vx / vl, vy / vl
            # cut the lower arm across its stroke, a little past the tip
            p0 = (tip[0] + vx * stroke * 1.2, tip[1] + vy * stroke * 1.2)
            nx, ny = -vy, vx
            big = 5000
            half = [(p0[0] + nx * big, p0[1] + ny * big),
                    (p0[0] + nx * big + vx * big, p0[1] + ny * big + vy * big),
                    (p0[0] - nx * big + vx * big, p0[1] - ny * big + vy * big),
                    (p0[0] - nx * big, p0[1] - ny * big)]
            below = [(-big, tip[1]), (big, tip[1]), (big, -big), (-big, -big)]
            arm = clip_polygon(clip_polygon(flat, below), half)
            # round the cut end: a circle on the cut edge's midpoint, as wide as the edge
            on_cut = [pt for c in polygon_points(arm) for pt in c
                      if abs((pt[0] - p0[0]) * vx + (pt[1] - p0[1]) * vy) < 1.0]
            if len(on_cut) >= 2:
                a_, b_ = min(on_cut, key=lambda q: q[0] * nx + q[1] * ny), max(on_cut, key=lambda q: q[0] * nx + q[1] * ny)
                mid = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
                # lengthen the stroke back along itself until it starts under the bend
                ext = abs(mid[0] - tip[0]) / abs(vx)
                arm = [(op, tuple(None if pt is None else
                                  ((pt[0] - vx * ext, pt[1] - vy * ext)
                                   if abs((pt[0] - p0[0]) * vx + (pt[1] - p0[1]) * vy) < 1.0 else pt)
                                  for pt in args)) for op, args in arm]
                arm += circle((mid[0] - vx * ext, mid[1] - vy * ext), math.dist(a_, b_) / 2)
            # centre-to-centre distance across the strokes: 2.2 strokes
            drop = stroke * 2.2 / abs(vx)
            ops = flat + transformed(arm, 1.0, 0.0, 1.0, -drop)
            ob = bounds(ops)
            shapes[name] = (2, transformed(ops, 1.0, W2 / 2 - (ob[0] + ob[2]) / 2,
                                           1.0, axis - (ob[1] + ob[3]) / 2))

    # -->  <--  ==>  <==  : the two-cell arrows, a cell longer
    shapes["hyphen_hyphen_greater"] = (3, g3 + bar(left_hy, end3, axis))
    shapes["less_hyphen_hyphen"] = (3, less + bar(start, W3 - (CELL - hyphen[2]), axis))
    ops = list(g3)
    for y0, y1 in bars(2, eq_gap):
        ops += bar(left_eq, shaft_end(g3, y0, y1, True), (y0 + y1) / 2)
    shapes["equal_equal_greater"] = (3, ops)
    ops = list(less)
    for y0, y1 in bars(2, eq_gap):
        ops += bar(shaft_end(less, y0, y1, False), W3 - (CELL - equal[2]), (y0 + y1) / 2)
    shapes["less_equal_equal"] = (3, ops)

    lb, gb = bounds(less), bounds(greater)

    # |>  <|  : the open end closed by the font's own | , a triangle
    pipe = record(glyph_set, gname["|"])
    pib = bounds(pipe)
    for name, chev, cb, right in (("bar_greater", greater, gb, True), ("less_bar", less, lb, False)):
        ky = (cb[3] - cb[1]) / (pib[3] - pib[1])
        side_x = cb[0] + stroke / 2 if right else cb[2] - stroke / 2
        side = transformed(pipe, 1.0, side_x - (pib[0] + pib[2]) / 2, ky, cb[1] - ky * pib[1])
        tri = chev + side
        tb = bounds(tri)
        shapes[name] = (2, transformed(tri, 1.0, W2 / 2 - (tb[0] + tb[2]) / 2))

    # ~>  <~  ~~>  : the font's own ~ as the shaft. Its ends are round caps, so a longer
    # wave is made from its middle: the stretch from the crest down to the trough, and
    # the same stretch turned upside down (trough up to crest), joined where the stroke
    # runs flat. The shaft ends where the stroke rises through the middle height on the
    # right, inside the arrow head.
    tilde = record(glyph_set, gname["~"])
    tib = bounds(tilde)
    tcy = (tib[1] + tib[3]) / 2
    txs = crossings(tilde, tcy)
    rise_b = (txs[-2] + txs[-1]) / 2
    swapped = [(op, tuple(None if pt is None else (pt[1], pt[0]) for pt in args)) for op, args in tilde]

    def band(x):
        ys = crossings(swapped, x)
        return (ys[0], ys[-1]) if len(ys) >= 2 else None

    samples = [(x, band(x)) for x in range(int(tib[0]) + 1, int(tib[2]))]
    samples = [(x, b) for x, b in samples if b]
    crest_x, crest = max(samples, key=lambda s_: s_[1][1])
    trough_x, trough = min(samples, key=lambda s_: s_[1][0])
    crest_y, trough_y = sum(crest) / 2, sum(trough) / 2
    seam = 6

    def strip(ops, x0, x1):
        return clip_polygon(ops, [(x0, -5000), (x0, 5000), (x1, 5000), (x1, -5000)])

    down = strip(tilde, crest_x - seam, trough_x + seam)          # crest to trough
    # trough to crest: flipping turns the outline the other way round, so turn it back
    up = clip_polygon(transformed(down, 1.0, 0.0, -1.0, crest_y + trough_y), [(-5000, -5000), (-5000, 5000), (5000, 5000), (5000, -5000)])
    half = trough_x - crest_x

    def wave(extra):
        """The ~ with `extra` whole waves set in its middle, and the x where it ends."""
        out = strip(tilde, -5000, trough_x + seam)
        x = trough_x
        for _ in range(extra):
            out += transformed(up, 1.0, x - crest_x)
            out += transformed(down, 1.0, x + half - crest_x)
            x += 2 * half
        out += transformed(strip(tilde, trough_x - seam, rise_b + seam), 1.0, x - trough_x)
        # one outline, so thinning it later cannot open the joins
        return strip(out, -5000, 5000), rise_b + (x - trough_x)

    def stretch(ops, cut_x, target_x):
        kx = (target_x - tib[0]) / (cut_x - tib[0])
        out = transformed(ops, kx, tib[0] * (1 - kx), 1.0, axis - tcy)
        if relation is not None and abs(kx - 1) > 0.01:
            # widening slants the rising strokes flatter and thicker: take that back
            dx = stroke * (1 - kx) * 0.5
            out = transformed(relation[1](out, dx, 0), 1.0, -dx / 2)
        return out

    w, cut = wave(0)
    shaft = stretch(w, cut, end)
    shapes["tilde_greater"] = (2, g_right + shaft)
    # <~ is ~> turned half round, on the font's own <
    shapes["less_tilde"] = (2, less + transformed(shaft, -1.0, W2, -1.0, 2 * axis))
    w, cut = wave(1)
    shapes["tilde_tilde_greater"] = (3, g3 + stretch(w, cut, end3))

    # /\  \/  : the slashes leaning together until their ends meet
    sl, bsl = record(glyph_set, gname["/"]), record(glyph_set, gname["\\"])
    sb, bb = bounds(sl), bounds(bsl)
    touch = stroke * 0.7
    shapes["slash_backslash"] = (2, transformed(sl, 1.0, W2 / 2 + touch / 2 - sb[2])
                                 + transformed(bsl, 1.0, W2 / 2 - touch / 2 - bb[0]))
    shapes["backslash_slash"] = (2, transformed(bsl, 1.0, W2 / 2 + touch / 2 - bb[2])
                                 + transformed(sl, 1.0, W2 / 2 - touch / 2 - sb[0]))

    # ...  : the font's own period raised to the middle of the operators, one per cell
    period = record(glyph_set, gname["."])
    pb = bounds(period)
    mid = transformed(period, 1.0, 0.0, 1.0, axis - (pb[1] + pb[3]) / 2)
    shapes["period_period_period"] = (3, [op for i in range(3) for op in transformed(mid, 1.0, i * CELL)])

    # :=  : the colon's dots at the heights of the = bars, the pair centred in two cells
    colon = contours(record(glyph_set, gname[":"]))
    colon.sort(key=lambda c: bounds(c)[1])
    bar_mid = [equal[1] + eq_stroke / 2, equal[3] - eq_stroke / 2]
    dots = []
    for c, y in zip(colon, bar_mid):
        cb = bounds(c)
        dots += transformed(c, 1.0, 0.0, 1.0, y - (cb[1] + cb[3]) / 2)
    db = bounds(dots)
    gap = stroke * 1.2
    width = (db[2] - db[0]) + gap + (equal[2] - equal[0])
    x0 = (W2 - width) / 2
    shapes["colon_equal"] = (2, transformed(dots, 1.0, x0 - db[0])
                             + transformed(equal_ops, 1.0, x0 + (db[2] - db[0]) + gap - equal[0]))

    # &&  ||  : left empty here, drawn by fill_from_symbols once the symbols exist
    for name in FROM_SYMBOL:
        shapes[name] = (2, [])

    glyf = font["glyf"]
    hmtx = font["hmtx"]
    order = font.getGlyphOrder()
    new = []
    for name, (n, ops) in shapes.items():
        lig = f"{name}.liga"
        glyf[lig] = to_glyph(transformed(ops, 1.0, -(n - 1) * CELL))
        hmtx[lig] = (CELL, 0)
        new.append(lig)
        for i in range(n - 1):
            sp = f"{name}.spacer{i}"
            glyf[sp] = to_glyph([])
            hmtx[sp] = (CELL, 0)
            new.append(sp)
    font.setGlyphOrder(order + [g for g in new if g not in order])
    glyf.glyphOrder = font.getGlyphOrder()

    install_calt(font, gname, set(shapes), extra_fea)
    return new


def fill_from_symbols(font, weight, glyph_of=to_glyph, widen=1.5):
    """Draws the ligatures in FROM_SYMBOL: the font's own symbol widened by `widen`,
    its stroke given back with weight(ops, dx, dy), centred in the two cells."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    stroke = bounds(record(glyph_set, cmap[ord("-")]))
    stroke = stroke[3] - stroke[1]
    for name, cp in FROM_SYMBOL.items():
        lig = f"{name}.liga"
        if lig not in font["glyf"] or cp not in cmap:
            continue
        ops = record(glyph_set, cmap[cp])
        b = bounds(ops)
        out = transformed(ops, widen, 0.0)
        out = weight(out, stroke * (1 - widen) * 0.5, 0)
        ob = bounds(out)
        out = transformed(out, 1.0, CELL - (ob[0] + ob[2]) / 2, 1.0, 0.0)
        font["glyf"][lig] = glyph_of(transformed(out, 1.0, -CELL))


def contours(ops):
    """The pen ops split into one list per contour."""
    out = []
    for op, args in ops:
        if op == "moveTo" or not out:
            out.append([])
        out[-1].append((op, args))
    return out


def circle(center, radius, steps=24):
    cx, cy = center
    pts = [(cx + radius * math.cos(-2 * math.pi * i / steps), cy + radius * math.sin(-2 * math.pi * i / steps))
           for i in range(steps)]  # clockwise
    if not CLOCKWISE:
        pts = pts[::-1]
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def flattened(ops, steps=16):
    """The outline with its curves walked point by point, so crossings() measures the
    curve itself and not the polygon of its control points."""
    from fontTools.pens.basePen import BasePen
    from fontTools.pens.recordingPen import RecordingPen
    rec = RecordingPen()

    class Flat(BasePen):
        def _moveTo(self, p):
            rec.moveTo(p)

        def _lineTo(self, p):
            rec.lineTo(p)

        def _curveToOne(self, p1, p2, p3):
            p0 = self._getCurrentPoint()
            for i in range(1, steps + 1):
                s = i / steps
                u = 1 - s
                rec.lineTo((u ** 3 * p0[0] + 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s ** 3 * p3[0],
                            u ** 3 * p0[1] + 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s ** 3 * p3[1]))

        def _qCurveToOne(self, p1, p2):
            p0 = self._getCurrentPoint()
            for i in range(1, steps + 1):
                s = i / steps
                u = 1 - s
                rec.lineTo((u * u * p0[0] + 2 * u * s * p1[0] + s * s * p2[0],
                            u * u * p0[1] + 2 * u * s * p1[1] + s * s * p2[1]))

        def _closePath(self):
            rec.closePath()

        def _endPath(self):
            rec.endPath()

    pen = Flat(None)
    for op, args in ops:
        getattr(pen, op)(*args)
    return rec.value


def stem_pair(ops, y, near_x):
    """The left and right edge of the stroke nearest near_x at height y."""
    xs = crossings(flattened(ops), y)
    pairs = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
    if not pairs:
        return None
    return min(pairs, key=lambda p: abs((p[0] + p[1]) / 2 - near_x))


def bridge_between(top_ops, bottom_ops, y_hi, y_lo, near_x, ccw):
    """The piece joining a stem that stops at y_hi (above) to one that starts at y_lo
    (below), following each stem's own edges a little way into it, so the outline has
    no step where they meet."""
    e = 12
    a, a_in = stem_pair(top_ops, y_hi + e, near_x), stem_pair(top_ops, y_hi, near_x)
    b, b_in = stem_pair(bottom_ops, y_lo - e, near_x), stem_pair(bottom_ops, y_lo, near_x)
    if not (a and a_in and b and b_in):
        return []
    pts = [(a[0], y_hi + e), (a[1], y_hi + e), (a_in[1], y_hi), (b_in[1], y_lo),
           (b[1], y_lo - e), (b[0], y_lo - e), (b_in[0], y_lo), (a_in[0], y_hi)]
    if ccw:
        pts = pts[::-1]
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def bridge(top_ops, bottom_ops, y, span, near_x, ccw):
    """Where a stem from one glyph meets a stem from another at height y: the piece
    between y - span and y + span, running from the lower stem's edges to the upper's,
    so the two widths meet without a step. The two parts are cut back to y +- span."""
    e = 12                                 # well into each part, so no seam is left
    a, a_in = stem_pair(top_ops, y + span + e, near_x), stem_pair(top_ops, y + span, near_x)
    b, b_in = stem_pair(bottom_ops, y - span - e, near_x), stem_pair(bottom_ops, y - span, near_x)
    if not (a and a_in and b and b_in):
        return []
    # inside each part the piece follows that part's own edges, so the outline has no step
    pts = [(a[0], y + span + e), (a[1], y + span + e), (a_in[1], y + span), (b_in[1], y - span),
           (b[1], y - span - e), (b[0], y - span - e), (b_in[0], y - span), (a_in[0], y + span)]
    if ccw:
        pts = pts[::-1]
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def clip_polygon(ops, poly):
    """The part of an outline inside a polygon, through skia-pathops, turned the font's way."""
    import pathops
    shape, box = pathops.Path(), pathops.Path()
    pen = shape.getPen()
    for op, args in ops:
        getattr(pen, op)(*args)
    bpen = box.getPen()
    bpen.moveTo(poly[0])
    for pt in poly[1:]:
        bpen.lineTo(pt)
    bpen.closePath()
    out = pathops.op(shape, box, pathops.PathOp.INTERSECTION)
    rec = RecordingPen()
    out.draw(rec)
    kept = []
    for part in polygon_points_ops(rec.value):
        pts = polygon_points(part)[0]
        area = signed_area(pts)
        if abs(area) < 200:
            continue
        if (area < 0) != CLOCKWISE:
            from fontTools.pens.reverseContourPen import ReverseContourPen
            r = RecordingPen()
            rev = ReverseContourPen(r)
            for op, args in part:
                getattr(rev, op)(*args)
            part = r.value
        kept += part
    return kept


def polygon_points_ops(ops):
    out, cur = [], []
    for op, args in ops:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def slash_of(font, glyph_set):
    """The stroke of `≠`, as a function that places it centered at (cx, cy)."""
    ops = record(glyph_set, font.getBestCmap()[0x2260])
    contours = polygon_points_ops(ops)
    if len(contours) > 1:
        # The stroke is drawn on its own: use the tallest contour as it is.
        tallest = max(contours, key=lambda c: bounds(c)[3] - bounds(c)[1])
        tb = bounds(tallest)
        tcx, tcy = (tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2

        def place_contour(cx, cy, extra):
            return [(op, tuple(None if pt is None else
                               (pt[0] + cx - tcx, pt[1] + cy - tcy + (extra / 2 if pt[1] > tcy else -extra / 2))
                               for pt in args)) for op, args in tallest]
        return place_contour
    pts = [p for contour in polygon_points(ops) for p in contour]
    ymin = min(p[1] for p in pts)
    ymax = max(p[1] for p in pts)
    bottom = sorted(p[0] for p in pts if p[1] == ymin)
    top = sorted(p[0] for p in pts if p[1] == ymax)
    bx = (bottom[0] + bottom[-1]) / 2
    tx = (top[0] + top[-1]) / 2
    half_w = (bottom[-1] - bottom[0]) / 2
    slope = (tx - bx) / (ymax - ymin)

    def place(cx, cy, extra):
        h = (ymax - ymin) / 2 + extra / 2
        bxc = cx - slope * h
        txc = cx + slope * h
        y0, y1 = cy - h, cy + h
        return quad([(bxc - half_w, y0), (txc - half_w, y1), (txc + half_w, y1), (bxc + half_w, y0)])

    return place


def install_calt(font, gname, built, extra_fea=""):
    def cls(chars):
        return "[" + " ".join(sorted({gname[c] for c in chars})) + "]"
    lines = [f"@OPS = {cls(OPERATOR_CHARS)};"]
    cmap = font.getBestCmap()
    word = sorted({cmap[ord(c)] for c in
                   "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" if ord(c) in cmap})
    lines.append(f"@WORD = [{' '.join(word)}];")
    ligatures = [(n, c) for n, c in LIGATURES if n in built]
    for name, chars in ligatures:
        g = [gname[c] for c in chars]
        sp = [f"{name}.spacer{i}" for i in range(len(chars) - 1)]
        seq = " ".join(g[1:])
        lines.append(f"lookup {name} {{")
        guard = cls(GUARD_CHARS[name]) if name in GUARD_CHARS else "@OPS"
        lines.append(f"    ignore sub {guard} {g[0]}' {seq};")
        lines.append(f"    ignore sub {g[0]}' {seq} {guard};")
        if name in WORD_GUARDED:
            lines.append(f"    ignore sub @WORD {g[0]}' {seq};")
            lines.append(f"    ignore sub {g[0]}' {seq} @WORD;")
        # Rules for later positions come first: they see the spacers already placed.
        for i in range(len(chars) - 1, 0, -1):
            before = " ".join(sp[:i])
            after = " ".join(g[i + 1:])
            target = f"{name}.liga" if i == len(chars) - 1 else sp[i]
            lines.append(f"    sub {before} {g[i]}' {after} by {target};".replace("  ", " "))
        lines.append(f"    sub {g[0]}' {seq} by {sp[0]};")
        lines.append(f"}} {name};")
    for tag, pairs in sorted(ALTERNATES.items()):
        lines.append(f"lookup alt_{tag} {{")
        for glyph, alt in pairs:
            lines.append(f"    sub {glyph} by {alt};")
        lines.append(f"}} alt_{tag};")
    tags = ["calt"] + sorted({STYLISTIC[n] for n, _ in ligatures if n in STYLISTIC} | set(ALTERNATES))
    for tag in tags:
        lines.append(f"feature {tag} {{")
        if tag in FEATURE_NAMES:
            lines.append(f'    featureNames {{ name "{FEATURE_NAMES[tag]}"; }};')
        for name, _ in ligatures:
            if STYLISTIC.get(name, "calt") == tag:
                lines.append(f"    lookup {name};")
        if tag in ALTERNATES:
            lines.append(f"    lookup alt_{tag};")
        lines.append(f"}} {tag};")
    # extra_fea (the Hangul composition in ccmp) goes first: lookups run in the order
    # they are listed, and the alternates must see the syllables already composed
    fea = extra_fea + "\n" + "\n".join(lines) + "\n"

    # feaLib writes a whole GSUB table. Build it on the side, then move its lookups
    # into the font's own GSUB and point every `calt` record at them.
    parsed = Parser(StringIO(fea), glyphNames=font.getGlyphOrder()).parse()
    if "GSUB" not in font:
        Builder(font, parsed).build(tables={"GSUB"})
        return
    old = font["GSUB"]
    del font["GSUB"]
    Builder(font, parsed).build(tables={"GSUB"})
    built = font["GSUB"].table
    font["GSUB"] = old
    table = old.table

    offset = len(table.LookupList.Lookup)
    for lookup in built.LookupList.Lookup:
        for st in lookup.SubTable:
            shift_lookup_refs(st, offset)
        table.LookupList.Lookup.append(lookup)
    table.LookupList.LookupCount = len(table.LookupList.Lookup)
    for new in built.FeatureList.FeatureRecord:
        idx = [offset + i for i in new.Feature.LookupListIndex]
        found = False
        for fr in table.FeatureList.FeatureRecord:
            if fr.FeatureTag == new.FeatureTag:
                fr.Feature.LookupListIndex = list(idx)
                fr.Feature.LookupCount = len(idx)
                found = True
        if not found:
            raise NotImplementedError(f"the font has no {new.FeatureTag} feature to point at")


def shift_lookup_refs(obj, offset, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, list):
        for x in obj:
            shift_lookup_refs(x, offset, seen)
        return
    if not hasattr(obj, "__dict__"):
        return
    for key, val in list(vars(obj).items()):
        if key == "LookupListIndex" and isinstance(val, int):
            setattr(obj, key, val + offset)
        elif isinstance(val, (list, object)) and not isinstance(val, (str, int, float, bytes)):
            shift_lookup_refs(val, offset, seen)


# ---------------------------------------------------------------- tables

def finish_tables(font):
    font["post"].isFixedPitch = 1
    os2 = font["OS/2"]
    os2.xAvgCharWidth = CELL
    os2.panose.bProportion = 9  # monospaced
    for tag in ("DSIG",):
        if tag in font:
            del font[tag]


VERSION = "1.500"   # this font's own version, written over the original's


def rename(font):
    font["head"].fontRevision = float(VERSION)
    for rec in font["name"].names:
        if rec.nameID == 5:
            rec.string = f"Version {VERSION}"
            continue
        if rec.nameID not in (1, 3, 4, 6, 16, 17, 18, 21, 22, 25):
            continue
        text = rec.toUnicode()
        text = text.replace(OLD_FAMILY, NEW_FAMILY).replace(OLD_PS, NEW_PS)
        if rec.nameID == 3 and ";" in text:
            text = VERSION + text[text.index(";"):]
        rec.string = text


# ---------------------------------------------------------------- main

def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    static = {style: os.path.join(src, "ttf", f"WantedSans-{style}.ttf") for style, _ in STYLES}

    samples = []
    for style, w in STYLES:
        f = TTFont(static[style])
        b = bounds(record(f.getGlyphSet(), "l"))
        samples.append((w, b[2] - b[0]))
    stems = StemCurve(samples)

    names = TTFont(static["Regular"]).getGlyphOrder()
    hmtx = TTFont(static["Regular"])["hmtx"]
    donors = Donors(os.path.join(src, "variable", "WantedSansVariable.ttf"),
                    [n for n in names if hmtx[n][0] != WIDE])

    only = sys.argv[3:] or [s for s, _ in STYLES]
    for style, w in STYLES:
        if style not in only:
            continue
        path = os.path.join(out, f"{NEW_PS}-{style}.ttf")
        build_style(static[style], w, donors, stems, path)
        print("wrote", path, flush=True)
    shutil.copy(os.path.join(src, "OFL.txt"), os.path.join(out, "OFL.txt"))


if __name__ == "__main__":
    main()

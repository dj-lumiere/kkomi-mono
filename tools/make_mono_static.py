#!/usr/bin/env python3
"""Builds a fixed-width TrueType font from one static font (no variable font beside it).

Latin and symbols get one cell, half the em. Hangul and other East Asian wide characters
get two cells, a full em, and are centered in it (their outlines are kept as they are).

A glyph wider than its cell is narrowed horizontally and then thickened horizontally
by the stroke width the narrowing took away (the FreeType "embolden" method, x only).
This suits fonts drawn with one even stroke width, where the vertical strokes would
otherwise turn thinner than the horizontal ones.

Kerning and the font's own substitution features are dropped. `calt` gets the coding
ligatures from make_mono.py.

Needs: fonttools, skia-pathops.
Usage: make_mono_static.py <font.otf|ttf> <output.ttf> <old family> <new family>
"""
import math
import sys
import unicodedata

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.removeOverlaps import removeOverlaps

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import make_mono as M  # noqa: E402
import hangul_fill  # noqa: E402
import symbols  # noqa: E402

ALPHA = 0.5  # share of the lost vertical stroke width given back
# Hangul is enlarged to fill its two cells, then its strokes are thinned back.
# Each syllable is widened toward HANGUL_WIDTH (at most HANGUL_MAX_X times), and all
# of them are made HANGUL_Y times taller.
HANGUL_WIDTH = 0.8   # share of the two-cell box
HANGUL_MAX_X = 1.6
HANGUL_Y = 1.04


def is_hangul(cp):
    return 0xAC00 <= cp <= 0xD7A3 or 0x3130 <= cp <= 0x318F or 0x1100 <= cp <= 0x11FF


def embolden_x(ops, strength):
    """Widens every stroke horizontally by `strength` units."""
    return embolden(ops, strength, 0.0)


def embolden(ops, x_strength, y_strength):
    """Widens every stroke by `x_strength` units across and `y_strength` units up and down
    (FreeType's FT_Outline_EmboldenXY). Negative strengths make strokes thinner."""
    contours, cur = [], []
    for op, args in ops:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    pts_all = [[pt for _, args in c for pt in args if pt is not None] for c in contours]
    area = sum(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1])) for p in pts_all)
    truetype = area < 0  # clockwise outer contours
    half, yhalf = x_strength / 2, y_strength / 2
    out = []
    for contour, pts in zip(contours, pts_all):
        n = len(pts)
        moved = []
        for i, (x, y) in enumerate(pts):
            # nearest distinct neighbours
            j = (i - 1) % n
            while j != i and pts[j] == pts[i]:
                j = (j - 1) % n
            k = (i + 1) % n
            while k != i and pts[k] == pts[i]:
                k = (k + 1) % n
            if j == i or k == i:
                moved.append((x + half, y + yhalf))
                continue
            ix, iy = x - pts[j][0], y - pts[j][1]
            ox, oy = pts[k][0] - x, pts[k][1] - y
            l_in, l_out = math.hypot(ix, iy), math.hypot(ox, oy)
            ix, iy, ox, oy = ix / l_in, iy / l_in, ox / l_out, oy / l_out
            d = ix * ox + iy * oy
            sx = sy = 0.0
            if d > -0.9375:
                d += 1
                sx, sy = iy + oy, ix + ox
                if truetype:
                    sx = -sx
                else:
                    sy = -sy
                q = ox * iy - oy * ix
                if truetype:
                    q = -q
                lim = min(l_in, l_out)
                sx = sx * half / d if half * q <= lim * d else sx * lim / q
                sy = sy * yhalf / d if yhalf * q <= lim * d else sy * lim / q
            moved.append((x + half + sx, y + yhalf + sy))
        it = iter(moved)
        for op, args in contour:
            out.append((op, tuple(None if pt is None else next(it) for pt in args)))
    return out


def enlarge_hangul(ops, stem):
    """Scales a Hangul glyph up around its middle, then thins its strokes by what the
    scaling added, so it fills its cells with the stroke weight of the Latin letters."""
    b = M.bounds(ops)
    if b is None:
        return ops
    sy = HANGUL_Y
    sx = min(HANGUL_MAX_X, max(sy, HANGUL_WIDTH * M.WIDE / (b[2] - b[0])))
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    big = M.transformed(ops, sx, cx - sx * cx, sy, cy - sy * cy)
    return embolden(big, -stem * (sx - 1), -stem * (sy - 1))


# Standalone jamo (ㄱ ㅏ ㄾ) keep their own proportions and where the font sets them
# in the box: ㅏ has its stem near the middle, not its outline centred.
JAMO_X = 1.2


def place_jamo(ops, adv, box, stem):
    b = M.bounds(ops)
    if b is None:
        return []
    sx, sy = JAMO_X, HANGUL_Y
    cx, cy = adv / 2, (b[1] + b[3]) / 2
    big = M.transformed(ops, sx, box / 2 - sx * cx, sy, cy - sy * cy)
    return embolden(big, -stem * (sx - 1), -stem * (sy - 1))


def place(ops, adv, box, stem):
    b = M.bounds(ops)
    if b is None:
        return []
    x0, _, x1, _ = b
    if M.joins(b, adv, box):
        return M.transformed(ops, box / adv, 0.0)
    avail = box - 2 * M.MARGIN
    ink = x1 - x0
    if ink <= avail:
        return M.transformed(ops, 1.0, box / 2 - (x0 + x1) / 2)
    gain = ALPHA * stem
    s = (avail - gain) / (ink - gain)
    out = embolden_x(M.transformed(ops, s, 0.0), gain * (1 - s))
    nb = M.bounds(out)
    return M.transformed(out, 1.0, box / 2 - (nb[0] + nb[2]) / 2)


def capsule(p0, p1, w, ccw, steps=12):
    """A stroke from p0 to p1, `w` wide, with round ends."""
    (x0, y0), (x1, y1) = p0, p1
    ang = math.atan2(y1 - y0, x1 - x0)
    r = w / 2
    pts = []
    for i in range(steps + 1):  # end cap around p1
        a = ang - math.pi / 2 + math.pi * i / steps
        pts.append((x1 + r * math.cos(a), y1 + r * math.sin(a)))
    for i in range(steps + 1):  # start cap around p0
        a = ang + math.pi / 2 + math.pi * i / steps
        pts.append((x0 + r * math.cos(a), y0 + r * math.sin(a)))
    if not ccw:
        pts.reverse()
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def bar_thickness(ops):
    """Vertical thickness of a glyph's crossbar, read just inside its left end (t's bar)."""
    x0 = M.bounds(ops)[0]
    swapped = [(op, tuple(None if p is None else (p[1], p[0]) for p in args)) for op, args in ops]
    ys = M.crossings(swapped, x0 + 3)
    return ys[1] - ys[0]


def clip(ops, y0, y1, x0=-10000, x1=10000):
    """The part of an outline inside a box, through skia-pathops."""
    import pathops
    from fontTools.pens.recordingPen import RecordingPen
    shape, box = pathops.Path(), pathops.Path()
    pen = shape.getPen()
    for op, args in ops:
        getattr(pen, op)(*args)
    bpen = box.getPen()
    for op, args in M.rect(x0, y0, x1, y1):
        getattr(bpen, op)(*args)
    out = pathops.op(shape, box, pathops.PathOp.INTERSECTION)
    rec = RecordingPen()
    out.draw(rec)
    # cutting can leave hairline slivers along the box edge: drop them
    kept = []
    for part in M.polygon_points_ops(rec.value):
        if abs(M.signed_area(M.polygon_points(part)[0])) >= 200:
            kept += part
    return kept


def stem_span(ops):
    """Heights where the outline is a single upright stroke, and that stroke's centre."""
    _, y0, _, y1 = M.bounds(ops)
    rows = []
    for i in range(1, 60):
        y = y0 + (y1 - y0) * i / 60
        xs = M.crossings(ops, y)
        if len(xs) == 2:
            rows.append((y, (xs[0] + xs[1]) / 2, xs[1] - xs[0]))
    width = min(r[2] for r in rows)
    return [r for r in rows if r[2] < width * 1.3]


def l_with_t_hook(l_ops, t_ops, ccw, under_bar=False):
    """The glyph (l or i) keeps its own top and takes t's lower stem and hook, so the hook is the font's own."""
    t_rows = stem_span(t_ops)
    # the stem of t between its crossbar and its hook: cut in the middle of that run
    tb = M.bounds(t_ops)
    lower = [r for r in t_rows if r[0] < (tb[1] + tb[3]) / 2]
    y_cut, t_cx, _ = lower[len(lower) // 2]
    if under_bar:
        # join just under t's crossbar, where the flag will cover the seam
        _, t_cx, by0, _ = t_crossbar(t_ops)
        y_cut = by0 - 4
    l_rows = [r for r in stem_span(l_ops) if abs(r[0] - y_cut) < (tb[3] - tb[1]) * 0.1]
    l_cx = l_rows[0][1] if l_rows else (M.bounds(l_ops)[0] + M.bounds(l_ops)[2]) / 2
    # the two stems meet through a short tapered piece, so their widths join smoothly
    span = 30
    t_moved = M.transformed(t_ops, 1.0, l_cx - t_cx)
    top = clip(l_ops, y_cut + span, 100000)
    bottom = clip(t_moved, -100000, y_cut - span)
    out = M.bridge(l_ops, t_moved, y_cut, span, l_cx, ccw)
    for part in M.polygon_points_ops(top) + M.polygon_points_ops(bottom):
        pts = M.polygon_points(part)[0]
        if (M.signed_area(pts) > 0) != ccw:
            from fontTools.pens.recordingPen import RecordingPen
            from fontTools.pens.reverseContourPen import ReverseContourPen
            rec = RecordingPen()
            rev = ReverseContourPen(rec)
            for op, args in part:
                getattr(rev, op)(*args)
            part = rec.value
        out += part
    return out


def oriented(parts, ccw):
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    out = []
    for part in parts:
        pts = M.polygon_points(part)[0]
        if (M.signed_area(pts) > 0) != ccw:
            rec = RecordingPen()
            rev = ReverseContourPen(rec)
            for op, args in part:
                getattr(rev, op)(*args)
            part = rec.value
        out += part
    return out


def t_crossbar(t_ops):
    """t's stem width, stem centre and the bottom and top of its crossbar."""
    tb = M.bounds(t_ops)
    rows = stem_span(t_ops)
    stem_w = min(r[2] for r in rows)
    t_cx = rows[len(rows) // 2][1]
    # the heights in the upper half where t is clearly wider than its stem
    # (the lower half holds the hook, which is wide too)
    mid = (tb[1] + tb[3]) / 2
    bar = [y for y in (mid + (tb[3] - mid) * i / 120 for i in range(1, 120))
           if len(M.crossings(t_ops, y)) >= 2
           and M.crossings(t_ops, y)[-1] - M.crossings(t_ops, y)[0] > stem_w * 2]
    return stem_w, t_cx, min(bar), max(bar)


def t_arm_flag(ops, t_ops, ccw, angle=30):
    """Adds t's own left crossbar arm, tilted down-left, to the top of the stem (i as /|)."""
    stem_w, t_cx, by0, by1 = t_crossbar(t_ops)
    # the arm up to the middle of t's stem, only as tall as the bar, so the cut end
    # sits deep inside the i's stem and no piece of t's stem sticks out
    arm = clip(t_ops, by0, by1, -10000, t_cx)
    pivot = (t_cx, (by0 + by1) / 2)
    bar_h = by1 - by0

    contours = M.polygon_points_ops(ops)
    dot = max(contours, key=lambda c: M.bounds(c)[1])
    stem = max((c for c in contours if c is not dot), key=lambda c: M.bounds(c)[3])
    sx0, _, sx1, sy1 = M.bounds(stem)
    target = ((sx0 + sx1) / 2, sy1 - bar_h * 0.55)

    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    placed = []
    for op, args in arm:
        new = []
        for pt in args:
            if pt is None:
                new.append(None)
                continue
            x, y = pt[0] - pivot[0], pt[1] - pivot[1]
            new.append((x * ca - y * sa + target[0], x * sa + y * ca + target[1]))
        placed.append((op, tuple(new)))
    return list(ops) + oriented(M.polygon_points_ops(placed), ccw)


def flag(ops, stem_w, cell, ccw, line_w):
    """Adds a flag going down-left from the top of the stem (i as /|). The dot, the
    contour that starts highest, is left out, and the stem may be in several pieces."""
    contours = M.polygon_points_ops(ops)
    dot = max(contours, key=lambda c: M.bounds(c)[1])
    stem = max((c for c in contours if c is not dot), key=lambda c: M.bounds(c)[3])
    x0, y0, x1, y1 = M.bounds(stem)
    cx = (x0 + x1) / 2
    r = stem_w / 2
    top, bottom = y1 - r, y0 + r
    reach = cell * 0.26
    out = list(ops)
    out += capsule((cx, top), (cx - reach, top - reach * 0.55), line_w, ccw)
    return out


def dotted_center(zero_ops, period_ops):
    """A smaller copy of the font's own period, set in the middle of the zero."""
    zb, pb = M.bounds(zero_ops), M.bounds(period_ops)
    k = 0.75
    cx, cy = (zb[0] + zb[2]) / 2, (zb[1] + zb[3]) / 2
    pcx, pcy = (pb[0] + pb[2]) / 2, (pb[1] + pb[3]) / 2
    return M.transformed(period_ops, k, cx - k * pcx, k, cy - k * pcy)


def mirrored(ops):
    """The outline flipped left to right, contours turned back to their own direction."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    b = M.bounds(ops)
    flipped = M.transformed(ops, -1.0, b[0] + b[2])
    rec = RecordingPen()
    rev = ReverseContourPen(rec)
    for op, args in flipped:
        getattr(rev, op)(*args)
    return rec.value


# combining mark -> the font's spacing accent drawn for it
ACCENT_FOR = {0x300: 0x60, 0x301: 0xB4, 0x302: 0x5E, 0x303: 0x7E, 0x308: 0xA8, 0x30A: 0x2DA, 0x327: 0xB8}


def add_accented(font):
    """Builds accented Latin letters the font lacks from its own letters and spacing
    accents: the accent is made smaller and set above the letter (the cedilla below)."""
    import unicodedata
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    gs = font.getGlyphSet()
    made = {}
    # Latin-1 and Latin Extended-A letters, Greek letters with tonos or dialytika
    for cp in list(range(0xC0, 0x180)) + list(range(0x386, 0x3D0)):
        if cp in cmap:
            continue
        parts = unicodedata.decomposition(chr(cp)).split()
        if len(parts) != 2 or parts[0].startswith("<"):
            continue
        base, mark = int(parts[0], 16), int(parts[1], 16)
        accent = ACCENT_FOR.get(mark)
        if base not in cmap or accent not in cmap:
            continue
        base_ops = M.record(gs, cmap[base])
        if chr(base) in "ij":
            contours = M.polygon_points_ops(base_ops)
            dot = max(contours, key=lambda c: M.bounds(c)[1])
            base_ops = [op for c in contours if c is not dot for op in c]
        acc_ops = M.record(gs, cmap[accent])
        bb, ab = M.bounds(base_ops), M.bounds(acc_ops)
        upper = chr(base).isupper()
        k = (0.5 if upper else 0.55) if mark == 0x303 else (0.7 if upper else 0.8)
        cx = (bb[0] + bb[2]) / 2
        acx = (ab[0] + ab[2]) / 2
        if mark == 0x327:
            dy = bb[1] + 30 - k * ab[3]
        else:
            dy = bb[3] + 40 - k * ab[1]
            room = 880 - dy
            if k * ab[3] > room:
                k = room / ab[3]
                dy = bb[3] + 40 - k * ab[1]
        placed = M.transformed(acc_ops, k, cx - k * acx, k, dy)
        if k < 0.98:
            placed = embolden(placed, 68 * (1 - k) * 0.6, 68 * (1 - k) * 0.6)
        name = f"uni{cp:04X}"
        glyf[name] = to_tt_glyph_quadratic(base_ops + placed)
        hmtx[name] = (M.CELL, 0)
        made[cp] = name
    order = font.getGlyphOrder()
    font.setGlyphOrder(order + [n for n in made.values() if n not in order])
    glyf.glyphOrder = font.getGlyphOrder()
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(made)
    return list(made.values())


def to_tt_glyph_quadratic(ops):
    """For outlines that are already TrueType (quadratic): no curve conversion."""
    pen = TTGlyphPen(None)
    for op, args in ops:
        getattr(pen, op)(*args)
    glyph = pen.glyph(dropImpliedOnCurves=False)
    if glyph.numberOfContours > 0:
        glyph.coordinates.toInt()
    return glyph


def to_tt_glyph(ops):
    pen = TTGlyphPen(None)
    cu = Cu2QuPen(pen, max_err=1.0, reverse_direction=True)
    for op, args in ops:
        getattr(cu, op)(*args)
    glyph = pen.glyph(dropImpliedOnCurves=False)
    if glyph.numberOfContours > 0:
        glyph.coordinates.toInt()
    return glyph


def main():
    src, out_path, old_family, new_family = sys.argv[1:5]
    font = TTFont(src)
    upm = font["head"].unitsPerEm
    M.WIDE = upm
    M.CELL = upm // 2
    M.MARGIN = round(upm * 0.022)
    M.OLD_FAMILY, M.NEW_FAMILY = old_family, new_family
    M.OLD_PS, M.NEW_PS = old_family.replace(" ", ""), new_family.replace(" ", "")

    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]
    kinds = M.classify(font)
    lb = M.bounds(M.record(glyph_set, font.getBestCmap()[ord("l")]))
    stem = lb[2] - lb[0]

    order = list(font.getGlyphOrder())
    # A glyph the font shares between a narrow character and its wide form (· and ・,
    # ¥ and ￥) would be two cells for both: the narrow one gets its own copy, in one cell.
    alias = {}
    sharing = {}
    for cp, name in font.getBestCmap().items():
        sharing.setdefault(name, []).append(cp)
    for name, cps in sharing.items():
        wide = [unicodedata.east_asian_width(chr(cp)) in "WF" for cp in cps]
        if not (any(wide) and not all(wide)):
            continue
        for cp, w in zip(cps, wide):
            if w:
                continue
            new = f"uni{cp:04X}"
            alias[new], kinds[new], hmtx[new] = name, "narrow", hmtx[name]
            order.append(new)
            for table in font["cmap"].tables:
                if table.isUnicode() and cp in table.cmap:
                    table.cmap[cp] = new
    font.setGlyphOrder(order)
    cmap = font.getBestCmap()
    zero, period = cmap.get(ord("0")), cmap.get(ord("."))
    glyph_i, glyph_l = cmap.get(ord("i")), cmap.get(ord("l"))
    hangul = {n for cp, n in cmap.items() if is_hangul(cp)}
    compat_jamo = {n for cp, n in cmap.items() if 0x3131 <= cp <= 0x318E}
    l_pts = M.polygon_points(M.record(glyph_set, cmap[ord("l")]))[0]
    ccw = M.signed_area(l_pts) > 0
    t_bar = bar_thickness(M.record(glyph_set, cmap[ord("t")]))
    # Hangul syllables the font maps but never draws are built from the ones it does draw.
    filled, fill_stats = hangul_fill.fill(glyph_set, cmap, embolden)
    for what, count in fill_stats.items():
        print(f"hangul: {count} {what}")

    glyphs, narrow = {}, []
    backslash, slash = cmap.get(0x5C), cmap.get(0x2F)
    asterisk = cmap.get(0x2A)
    hb = M.bounds(M.record(glyph_set, cmap[ord("-")]))
    operator_axis = (hb[1] + hb[3]) / 2
    for name in order:
        ops = filled.get(name) or M.record(glyph_set, alias.get(name, name))
        if name == backslash and slash:
            # the font draws the won sign here: a backslash, the slash flipped
            ops = mirrored(M.record(glyph_set, slash))
        adv = hmtx[name][0]
        kind = kinds[name]
        if kind == "zero":
            new_ops, new_adv = M.transformed(ops, M.MARK_SCALE, 0.0), 0
        else:
            box = M.WIDE if kind == "wide" else M.CELL
            if name in compat_jamo:
                glyphs[name] = to_tt_glyph(place_jamo(ops, adv, box, stem))
                hmtx[name] = (box, 0)
                continue
            if name in hangul:
                ops = enlarge_hangul(ops, stem)
            if name in (glyph_i, glyph_l):
                ops = l_with_t_hook(ops, M.record(glyph_set, cmap[ord("t")]), ccw,
                                    under_bar=name == glyph_i)
            new_ops, new_adv = place(ops, adv, box, stem), box
            if kind == "narrow":
                narrow.append(name)
            if name == glyph_i:
                new_ops = t_arm_flag(new_ops, M.record(glyph_set, cmap[ord("t")]), ccw)
                ib = M.bounds(new_ops)
                new_ops = M.transformed(new_ops, 1.0, M.CELL / 2 - (ib[0] + ib[2]) / 2)
            if name == asterisk:
                # an operator in code: centred on the hyphen like + - =, not raised
                ab = M.bounds(new_ops)
                new_ops = M.transformed(new_ops, 1.0, 0.0, 1.0, operator_axis - (ab[1] + ab[3]) / 2)
            if name == zero and period:
                new_ops = new_ops + dotted_center(new_ops, M.record(glyph_set, period))
        glyphs[name] = to_tt_glyph(new_ops)
        hmtx[name] = (new_adv, 0)

    # CFF outlines become TrueType outlines.
    for tag in ("CFF ", "VORG", "GSUB", "GPOS", "DSIG"):
        if tag in font:
            del font[tag]
    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    font["head"].glyphDataFormat = 0
    font.sfntVersion = "\x00\x01\x00\x00"
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for field in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
                  "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions",
                  "maxComponentElements", "maxPoints", "maxContours",
                  "maxCompositePoints", "maxCompositeContours", "maxComponentDepth"):
        setattr(maxp, field, 1 if field == "maxZones" else 0)
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = order

    jamo, compose_fea = symbols.add_conjoining_jamo(font, to_tt_glyph_quadratic)
    print(f"conjoining jamo: {len(jamo)}")
    ligs = M.add_ligatures(font, kinds, relation=((1.65, 0.72), embolden), extra_fea=compose_fea)
    ligs += jamo
    accented = add_accented(font)
    print(f"accented letters: {len(accented)}")
    ligs += accented
    drawn_symbols = symbols.add_symbols(font, to_tt_glyph_quadratic, embolden)
    print(f"symbols: {len(drawn_symbols)}")
    ligs += drawn_symbols
    removeOverlaps(font, glyphNames=narrow + ligs, removeHinting=True, ignoreErrors=True)
    for name in font.getGlyphOrder():
        g = font["glyf"][name]
        g.recalcBounds(font["glyf"])
        hmtx[name] = (hmtx[name][0], getattr(g, "xMin", 0) if g.numberOfContours else 0)

    # Syllables the font maps but never draws would show as blank space. Unmapping them
    # lets the editor or terminal take them from its fallback font instead.
    blank = {cp for cp, n in font.getBestCmap().items()
             if is_hangul(cp) and font["glyf"][n].numberOfContours == 0}
    for table in font["cmap"].tables:
        if table.isUnicode():
            for cp in blank:
                table.cmap.pop(cp, None)
    print(f"unmapped {len(blank)} blank Hangul code points")

    font["post"].isFixedPitch = 1
    os2 = font["OS/2"]
    os2.xAvgCharWidth = M.CELL
    os2.panose.bProportion = 9
    M.rename(font)
    # Names in other languages (the Korean family name, for one) do not contain the
    # English family name, so they get the suffix appended.
    suffix = new_family[len(old_family):] if new_family.startswith(old_family) else ""
    for rec in font["name"].names:
        english = (rec.platformID == 3 and rec.langID == 0x409) or (rec.platformID == 1 and rec.langID == 0)
        if rec.nameID in (1, 4, 16) and not english and suffix:
            text = rec.toUnicode()
            if not text.endswith(suffix):
                rec.string = text + suffix
    font.save(out_path)
    print("wrote", out_path)


if __name__ == "__main__":
    main()

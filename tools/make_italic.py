#!/usr/bin/env python3
"""Builds the Italic of a fixed-width font made by make_mono_static.py.

An italic is more than slanted letters: handwriting run fast ends its strokes in hooks.
So the Latin letters first take italic forms built from the font's own strokes:
- a d h m n u end their right stem in the hook of t (i and l already do, in the Regular);
- f runs its stem below the baseline and ends it in the hook of j;
- x becomes two curves back to back, ɔc, made from the font's own c and its mirror image.
Then every one-cell glyph leans by ANGLE degrees.

Left upright: Hangul and other two-cell glyphs (slanted Hangul looks wrong), the
conjoining jamo, and everything that must meet the cell edges (box drawing, blocks,
braille, Powerline).

Usage: make_italic.py <Regular.ttf> <Italic.ttf>
"""
import math
import os
import sys

from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_mono as M  # noqa: E402
from make_mono_static import to_tt_glyph_quadratic  # noqa: E402

ANGLE = 13
# Hangul, kana and the full-width forms slant with the Latin letters. Only the glyphs
# that must join up with their neighbours (box drawing, blocks, braille, Powerline)
# stay upright.
UPRIGHT_RANGES = M.KEEP_RANGES
HOOKED = "adhmnu"


def path_op(a_ops, b_ops, kind):
    import pathops
    a, b = pathops.Path(), pathops.Path()
    for path, ops in ((a, a_ops), (b, b_ops)):
        pen = path.getPen()
        for op, args in ops:
            getattr(pen, op)(*args)
    out = pathops.op(a, b, kind)
    rec = RecordingPen()
    out.draw(rec)
    # joining two strokes can trap specks of empty space where their edges cross:
    # drop contours far smaller than any real counter
    parts = [part for part in M.polygon_points_ops(rec.value)
             if abs(M.signed_area(M.polygon_points(part)[0])) >= 2500]
    if not parts:
        return []
    # skia turns outlines its own way: turn them back the way the font's outer contours
    # run (clockwise), or thickening them later would thin them instead
    outer = max(parts, key=lambda q: abs(M.signed_area(M.polygon_points(q)[0])))
    if M.signed_area(M.polygon_points(outer)[0]) > 0:
        from fontTools.pens.reverseContourPen import ReverseContourPen
        flipped = []
        for part in parts:
            r = RecordingPen()
            rev = ReverseContourPen(r)
            for op, args in part:
                getattr(rev, op)(*args)
            flipped.append(r.value)
        parts = flipped
    return [op for part in parts for op in part]


def box(x0, y0, x1, y1):
    return [("moveTo", ((x0, y0),)), ("lineTo", ((x0, y1),)), ("lineTo", ((x1, y1),)),
            ("lineTo", ((x1, y0),)), ("closePath", ())]


SLANT_T = math.tan(math.radians(ANGLE))
# how far in from the cell's edges a slanted letter keeps its ink, leaving room for the
# Bold to grow
INSET = 22


def right_stem_hook(ops, x_height, free, trim_left=None):
    """The rightmost stem's foot with a hook branching out of it: a stroke of the round
    pen that starts inside the stem, runs down with it and turns out to the right, ending
    where it stays INSET inside the cell once slanted. Nothing of the stem is cut away,
    so there is no joint to show."""
    import pathops
    from symbols import pen_stroke
    flat = M.flattened(ops)
    y_in = x_height * 0.3
    xs = M.crossings(flat, y_in)
    if len(xs) < 2:
        return ops
    x0, x1 = xs[-2], xs[-1]
    w = (x1 - x0) * 0.98                 # just inside the stem, so its edges stay the stem's
    cx = (x0 + x1) / 2
    low = M.stem_pair(flat, 60, cx)
    bx = (low[0] + low[1]) / 2 if low else cx
    foot = w / 2 + 2
    end_y = foot + 60
    end_x = M.CELL - INSET - w / 2 - SLANT_T * (end_y - x_height / 2)
    run = max(end_x - bx, 40)
    end_y = foot + run * 0.55
    end_x = M.CELL - INSET - w / 2 - SLANT_T * (end_y - x_height / 2)
    run = max(end_x - bx, 40)
    if free:
        # a stem standing free (n m h): its own round end goes, the hook takes its place
        hook = pen_stroke((cx, y_in), [
            ("line", (bx, foot + 45)),
            ("curve", (bx, foot + 5), (bx + run * 0.4, foot - 5), (bx + run, end_y)),
        ], w)
        left = x0 - 30 if trim_left is None else bx - w / 2 - trim_left
        ops = path_op(ops, box(left, -200, M.CELL + 200, foot + 40), pathops.PathOp.DIFFERENCE)
    else:
        # a bowl runs into the stem (u a d): the stem is kept whole, and the hook runs down
        # with it to its round end before it turns, so the two ends lie one over the other
        hook = pen_stroke((cx, y_in), [
            ("line", (bx, foot + 12)),
            ("curve", (bx + run * 0.25, foot - 4), (bx + run * 0.6, foot), (bx + run, end_y)),
        ], w)
    return path_op(ops, hook, pathops.PathOp.UNION)


def f_descender(f_ops, x_height):
    """f's stem below its crossbar redrawn with the round pen and carried below the
    baseline, ending in an open curl to the left that stays INSET inside the cell once
    slanted. The new stroke starts inside the bar, in line with the stem above it, so
    the joint is hidden in the bar and the stem runs straight through."""
    import pathops
    from symbols import pen_stroke
    flat = M.flattened(f_ops)
    fb = M.bounds(flat)
    base = M.crossings(flat, fb[1] + 80)
    if len(base) < 2:
        return f_ops
    stem_w = base[1] - base[0]
    # the bar: going up from the foot, the heights where f is much wider than its stem
    y, bar_lo, bar_hi = fb[1] + 80, None, None
    while y < fb[3]:
        row = M.crossings(flat, y)
        wide = row and row[-1] - row[0] > stem_w * 1.8
        if wide and bar_lo is None:
            bar_lo = y
        elif not wide and bar_lo is not None:
            bar_hi = y
            break
        y += 2
    if bar_lo is None or bar_hi is None:
        return f_ops
    above = M.crossings(flat, bar_hi + 15)
    if len(above) < 2:
        return f_ops
    w = above[1] - above[0]
    cx = (above[0] + above[1]) / 2
    bar_mid = (bar_lo + bar_hi) / 2
    # everything under the bar goes; the bar itself and all above it stay
    f_ops = path_op(f_ops, box(-10000, -10000, 10000, bar_lo + 3), pathops.PathOp.DIFFERENCE)
    low = -150
    x_low = cx + 75                 # leaning on down, which leaves the tail room to run out
    # the tail turns left at the bottom and runs out flat, as far as the cell allows: no
    # turn back up, so it stays open and clear of the stem
    end_y = low + 12
    end_x = INSET + w / 2 - SLANT_T * (end_y - x_height / 2)
    # one straight line from inside the bar down to the turn
    tail = pen_stroke((cx, bar_mid), [
        ("line", (x_low, low + 80)),
        ("curve", (x_low, low + 20), (x_low - 30, low + 2), (x_low - 70, low + 4)),
        ("line", (end_x, end_y)),
    ], w)
    return path_op(f_ops, tail, pathops.PathOp.UNION)


def loop_l(l_ops, x_height):
    """The italic l: the / half of ℓ and its mirror image, one loop that crosses itself
    near the foot, tails at the bottom left and the bottom right. Drawn upright with
    the round pen and slanted with the other letters. Its right half is the Regular l."""
    from symbols import pen_stroke, l_halves
    lb = M.bounds(l_ops)
    # the Regular l is already the \\ half: its stroke is the width at its middle
    xs = M.crossings(M.flattened(l_ops), (lb[1] + lb[3]) * 0.6)
    s = xs[1] - xs[0] if len(xs) >= 2 else 70
    start, _, slash, backslash = l_halves(lb[3] - s / 2, s, inset=20)
    loop = pen_stroke(start, slash + backslash, s)
    # the slant pushes the foot left by as much as half the x-height leans: move the
    # letter right by that first, so the left tail stays inside the cell
    return M.transformed(loop, 1.0, math.tan(math.radians(ANGLE)) * x_height / 2)


def cursive_i(i_ops, x_height):
    """The italic i written as by hand: up from near the baseline on the left (/), down
    the stem (\\), and out up to the right (/), its dot raised clear above. Drawn upright
    with the round pen and slanted with the other letters, its ends kept in the cell."""
    from symbols import pen_stroke
    lb = M.bounds(i_ops)
    cs = M.polygon_points_ops(i_ops)
    dot = max(cs, key=lambda q: M.bounds(q)[1])
    stem = [q for q in cs if q is not dot]
    xs = M.crossings(M.flattened([op for q in stem for op in q]), x_height * 0.4)
    s = 70
    if len(xs) >= 2:
        s = min(b - a for a, b in zip(xs[0::2], xs[1::2]))
    w = M.CELL
    top = x_height - s / 2 - 60
    xm = w / 2
    t = math.tan(math.radians(ANGLE))
    # the slant moves a point at height y by t * (y - x_height / 2): start and end are
    # set so that after it they sit inside the cell with a margin
    margin = 25
    start_y, end_y = 110, 190
    start_x = margin + s / 2 - t * (start_y - x_height / 2)
    end_x = w - margin - s / 2 - t * (end_y - x_height / 2)
    body = pen_stroke((start_x, start_y), [
        ("curve", (start_x + 70, start_y + 100), (xm - 50, top - 70), (xm, top)),
        ("curve", (xm - 10, top - 135), (xm - 30, 120), (xm, s / 2 + 20)),
        ("curve", (xm + 40, s / 2 - 10), (end_x - 60, 80), (end_x, end_y)),
    ], s)
    db = M.bounds(dot)
    # the dot sits over the top of the stem once slanted: shift it back by the slant
    dot = M.transformed(dot, 1.0, xm + 10 - (db[0] + db[2]) / 2, 1.0, 40)
    return body, dot


class Cursive:
    """Cursive italic letters drawn upright with the round pen, before the slant. The
    slant moves a point at height y sideways by tan(ANGLE) * (y - x_height / 2), so
    left() and right() give the x a stroke's centre may take at a height and still
    stay inside the cell once slanted."""

    def __init__(self, x_height, stroke):
        self.xh, self.s = x_height, stroke
        self.t = math.tan(math.radians(ANGLE))
        self.top = x_height - stroke / 2

    def shift(self, y):
        return self.t * (y - self.xh / 2)

    def left(self, y, margin=25):
        return margin + self.s / 2 - self.shift(y)

    def right(self, y, margin=25):
        return M.CELL - margin - self.s / 2 - self.shift(y)

    def pen(self, start, segments):
        from symbols import pen_stroke
        return pen_stroke(start, segments, self.s)

    def entry(self, x):
        """The hook a hand makes coming into the top of a stem at x from the left: a short
        curl up and over into the stem, kept inside the cell."""
        y0 = self.top - 70
        x0 = max(self.left(y0), x - 70)
        return self.pen((x0, y0), [("curve", (x0, self.top), (x - 30, self.top + 15), (x, self.top))])

    def j(self, dot):
        """j as the cursive i with a tail: up from the bottom left, down the stem below
        the baseline, curling back to the left."""
        xm = M.CELL / 2 + 30
        top = self.top - 60
        sy = 110
        body = self.pen((self.left(sy), sy), [
            ("curve", (self.left(sy) + 70, sy + 100), (xm - 50, top - 70), (xm, top)),
            ("line", (xm, -90)),
            ("curve", (xm, -215), (xm - 150, -235), (self.left(-150), -150)),
        ])
        db = M.bounds(dot)
        return body + M.transformed(dot, 1.0, xm + 10 - (db[0] + db[2]) / 2, 1.0, 40)

    def k(self, ascender):
        """k with a simple hook into the top of its stem from the left (as m n u have at
        the x-height), and the arm as a small bowl and a leg away to the bottom right, as
        in R."""
        stem = 150
        top = ascender - self.s / 2
        y0 = top - 80
        x0 = max(self.left(y0), stem - 75)
        hook = self.pen((x0, y0), [("curve", (x0, top), (stem - 35, top + 15), (stem, top)),
                                   ("line", (stem, self.s / 2))])
        ey = 70
        arm = self.pen((stem, 370), [
            ("curve", (stem + 110, 430), (stem + 250, 400), (stem + 250, 300)),
            ("curve", (stem + 250, 210), (stem + 120, 185), (stem + 20, 200)),
            ("curve", (stem + 150, 175), (stem + 210, 40), (self.right(ey), ey)),
        ])
        return hook + arm

    def y(self):
        """y as u with its right stem carried below the baseline, curling back left."""
        xl, xr = 145, 355
        bowl = self.pen((xl, self.top), [
            ("line", (xl, 170)),
            ("curve", (xl, 40), (xr, 40), (xr, 170)),
        ])
        tail = self.pen((xr, self.top), [
            ("line", (xr, -100)),
            ("curve", (xr, -225), (xr - 170, -240), (self.left(-160), -160)),
        ])
        return self.entry(xl) + bowl + tail


def c_x(x_ops, c_ops):
    """x as ɔc: the c and its mirror image back to back at the x-height, their backs
    overlapping by about a stroke so they read as one letter."""
    import pathops
    from make_mono_static import embolden
    from symbols import flip_h
    xb, cb = M.bounds(x_ops), M.bounds(c_ops)
    overlap = 60
    half = ((xb[2] - xb[0]) + overlap) / 2
    kx = half / (cb[2] - cb[0])
    # 2% under the x-height: at full height the two round backs look taller than w
    ky = (xb[3] - xb[1]) / (cb[3] - cb[1]) * 0.98
    cx = (xb[0] + xb[2]) / 2
    c = M.transformed(c_ops, kx, 0.0, ky, xb[1] - ky * cb[1])
    # narrowing thins the curve's upright parts: give that width back
    c = embolden(c, 68 * (1 - kx), 68 * (1 - ky))
    b = M.bounds(c)
    right = M.transformed(c, 1.0, cx - overlap / 2 - b[0])
    rb = M.bounds(right)
    left = flip_h(right, (2 * cx - rb[2], 0, rb[2], 0))
    return path_op(right, left, pathops.PathOp.UNION)


def narrowed(ops, k, cx=None):
    """ops narrowed by k about cx (their middle by default), the stroke the narrowing
    takes from the upright strokes given back."""
    from make_mono_static import embolden
    if k >= 0.995:
        return ops
    b = M.bounds(ops)
    cx = (b[0] + b[2]) / 2 if cx is None else cx
    return embolden(M.transformed(ops, k, cx * (1 - k)), 68 * (1 - k) * 0.8, 0.0)


def fit_scale(ops, y0, width=None):
    """How much ops must be narrowed to stay INSET inside the cell once slanted."""
    width = width or M.CELL
    sb = M.bounds(M.flattened(skew(ops, ANGLE, y0)))
    return min(1.0, (width - 2 * INSET) / (sb[2] - sb[0]))


def fit_cell(ops, y0, width=None):
    """ops narrowed (about their middle) and moved, if need be, so that once slanted
    they stay INSET inside their cells (`width` wide, one cell by default); the stroke
    the narrowing takes is given back."""
    width = width or M.CELL
    for _ in range(3):
        sb = M.bounds(M.flattened(skew(ops, ANGLE, y0)))
        lo, hi = INSET, width - INSET
        if sb[0] >= lo - 0.5 and sb[2] <= hi + 0.5:
            return ops
        ops = narrowed(ops, min(1.0, (hi - lo) / (sb[2] - sb[0])))
        sb = M.bounds(M.flattened(skew(ops, ANGLE, y0)))
        dx = 0.0
        if sb[0] < lo:
            dx = lo - sb[0]
        elif sb[2] > hi:
            dx = hi - sb[2]
        ops = M.transformed(ops, 1.0, dx)
    return ops


def skew(ops, angle, y0):
    t = math.tan(math.radians(angle))
    rec = RecordingPen()
    pen = TransformPen(rec, (1, 0, t, 1, -t * y0, 0))
    for op, args in ops:
        getattr(pen, op)(*args)
    return rec.value


def main():
    src, out = sys.argv[1], sys.argv[2]
    font = TTFont(src)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    M.CELL = hmtx[cmap[ord("a")]][0]
    gt = M.record(gs, cmap[ord(">")])
    M.CLOCKWISE = M.signed_area(M.polygon_points(gt)[0]) < 0

    x_height = M.bounds(M.record(gs, cmap[ord("x")]))[3]
    changed = {}
    for ch in HOOKED:
        # n m h end their stem free; in d u a bowl runs into it. a's stem has its own small
        # curl at the foot, which goes too, trimmed close along the stem so its bowl stays
        changed[cmap[ord(ch)]] = right_stem_hook(M.record(gs, cmap[ord(ch)]), x_height, free=ch in "nmha",
                                                 trim_left=3 if ch == "a" else None)
    changed[cmap[ord("f")]] = f_descender(M.record(gs, cmap[ord("f")]), x_height)
    changed[cmap[ord("l")]] = loop_l(M.record(gs, cmap[ord("l")]), x_height)
    i_body, i_dot = cursive_i(M.record(gs, cmap[ord("i")]), x_height)
    changed[cmap[ord("i")]] = i_body + i_dot
    if 0x131 in cmap:
        changed[cmap[0x131]] = i_body                     # ı, the same without its dot
    # í ì î ï ĩ ī ĭ į: the cursive body with the marks of the upright letter. The cursive
    # stem stands 20 further left and its top 60 lower than the upright one, so marks
    # above move with it (į's dot sits where the i's dot does); an ogonek moves under it.
    if 0x12F in cmap:
        # į: the cursive i and an ogonek under the foot of its stem, drawn as the
        # upright ones are (one stroke of the round pen, down left and curling back)
        from symbols import pen_stroke
        ax, w = M.CELL / 2 + 20, 54
        hook = pen_stroke((ax, w / 2), [("curve", (ax - 75 * 0.9, -40 * 0.9), (ax - 70 * 0.9, -205 * 0.9),
                                          (ax + 60 * 0.9, -200 * 0.9))], w)
        changed[cmap[0x12F]] = i_body + i_dot + hook
    for cp in (0xEC, 0xED, 0xEE, 0xEF, 0x129, 0x12B, 0x12D):
        if cp not in cmap:
            continue
        cs = M.polygon_points_ops(M.record(gs, cmap[cp]))
        body = max(cs, key=lambda q: abs(M.signed_area(M.polygon_points(q)[0])))
        marks = []
        for q in cs:
            if q is body:
                continue
            qb = M.bounds(q)
            if qb[1] < 0:
                marks += M.transformed(q, 1.0, -40)
            elif cp == 0x12F:
                marks += M.transformed(q, 1.0, -20, 1.0, 40)
            else:
                marks += M.transformed(q, 1.0, -20, 1.0, -60)
        changed[cmap[cp]] = i_body + marks
    changed[cmap[ord("x")]] = c_x(M.record(gs, cmap[ord("x")]), M.record(gs, cmap[ord("c")]))

    # j k y in cursive
    nx = M.crossings(M.flattened(M.record(gs, cmap[ord("n")])), x_height * 0.6)
    stroke = nx[1] - nx[0] if len(nx) >= 2 else 70
    cur = Cursive(x_height, stroke)
    j_ops = M.record(gs, cmap[ord("j")])
    j_dot = max(M.polygon_points_ops(j_ops), key=lambda q: M.bounds(q)[1])
    ascender = M.bounds(M.record(gs, cmap[ord("l")]))[3]
    changed[cmap[ord("j")]] = cur.j(j_dot)
    changed[cmap[ord("k")]] = cur.k(ascender)
    changed[cmap[ord("y")]] = cur.y()


    upright = set()
    for cp, name in cmap.items():
        if any(a <= cp <= b for a, b in UPRIGHT_RANGES):
            upright.add(name)
    y0 = x_height / 2
    # Hangul and the other two-cell glyphs slant about the middle of the syllables, so
    # they stay centred in their two cells. The conjoining jamo drawn over the cells
    # before them slant the same way, to line up with their initial.
    ga = M.bounds(M.record(gs, cmap[0xAC00]))
    wide_y0 = (ga[1] + ga[3]) / 2
    jamo = {name for cp, name in cmap.items()
            if 0x1100 <= cp <= 0x11FF or 0xA960 <= cp <= 0xA97F or 0xD7B0 <= cp <= 0xD7FF}
    # and their forms for each place in a syllable (uni1100.L01, uni1161.V1, uni11A8.T2)
    jamo |= {name for name in font.getGlyphOrder() if name.partition(".")[0] in jamo}
    joining = {cmap[cp] for cp in (0x5F, 0x203E, 0x2017) if cp in cmap}
    mapped = set(cmap.values())
    for name in font.getGlyphOrder():
        adv = hmtx[name][0]
        if name in upright or adv > 2 * M.CELL:
            continue
        ops = changed.get(name) or M.record(gs, name)
        if M.bounds(ops) is None:
            continue
        # Only a letter or sign of its own, one cell wide, is kept inside its cell. A
        # ligature reaches back over the cells before it, a combining mark sits over the
        # letter before it, and lines that run on into the next cell (_ ‾ ‗) join up:
        # all of those are drawn past their cell on purpose.
        # an alternate letter (0.ss02, a.ss03) is fitted like the letter it stands for
        base, _, suffix = name.partition(".")
        letter = name in mapped or (suffix in ("ss02", "ss03", "ss05") and base in mapped)
        own_cell = letter and adv == M.CELL and name not in joining
        if adv == 2 * M.CELL:
            # a two-cell glyph is always one of its own, kept inside its two cells
            fitted = fit_cell(ops, wide_y0, 2 * M.CELL)
            glyf[name] = to_tt_glyph_quadratic(skew(fitted, ANGLE, wide_y0))
        else:
            gy = wide_y0 if name in jamo else y0
            fitted = fit_cell(ops, gy) if own_cell else ops
            glyf[name] = to_tt_glyph_quadratic(skew(fitted, ANGLE, gy))
        changed[name] = True
    names = [n for n in changed]
    removeOverlaps(font, glyphNames=names, removeHinting=True, ignoreErrors=True)
    for name in names:
        g = glyf[name]
        g.recalcBounds(glyf)
        hmtx[name] = (hmtx[name][0], getattr(g, "xMin", 0) if g.numberOfContours else 0)

    # style: Italic of the same family
    font["post"].italicAngle = -ANGLE
    font["hhea"].caretSlopeRise = 1000
    font["hhea"].caretSlopeRun = round(1000 * math.tan(math.radians(ANGLE)))
    os2 = font["OS/2"]
    os2.fsSelection = (os2.fsSelection | 0x01) & ~0x40      # italic on, regular off
    font["head"].macStyle |= 0x02
    for rec in font["name"].names:
        text = rec.toUnicode()
        if rec.nameID == 2:
            rec.string = "Italic"
        elif rec.nameID in (3, 6):
            rec.string = text.replace("-Regular", "-Italic").replace("Regular", "Italic")
        elif rec.nameID == 4:
            rec.string = text.replace(" Regular", "") + " Italic"
        elif rec.nameID == 17:
            rec.string = "Italic"
    font.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()

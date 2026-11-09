#!/usr/bin/env python3
"""Builds the Italic of a fixed-width font made by make_mono_static.py.

An italic is more than slanted letters: handwriting run fast ends its strokes in hooks.
So the Latin letters first take italic forms built from the font's own strokes:
- a d h m n u end their right stem in the hook of t (i and l already do, in the Regular);
- f runs its stem below the baseline and ends it in the hook of j;
- x becomes two arcs back to back, )( , made from the font's own parentheses.
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
UPRIGHT_RANGES = [(0x1100, 0x11FF), (0x2500, 0x259F), (0x2800, 0x28FF), (0xE0A0, 0xE0B3)]
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
    kept = []
    for part in M.polygon_points_ops(rec.value):
        if abs(M.signed_area(M.polygon_points(part)[0])) >= 2500:
            kept += part
    return kept


def box(x0, y0, x1, y1):
    return [("moveTo", ((x0, y0),)), ("lineTo", ((x0, y1),)), ("lineTo", ((x1, y1),)),
            ("lineTo", ((x1, y0),)), ("closePath", ())]


def lower_part(ops, y_cut):
    """The part of an outline below a height."""
    import pathops
    return path_op(ops, box(-10000, -10000, 10000, y_cut), pathops.PathOp.INTERSECTION)


def hook_of(t_ops, x_height):
    """t's stem below a cut low in the x-height, with its hook, and the stem's centre there."""
    y_cut = x_height * 0.32
    xs = M.crossings(t_ops, y_cut)
    # taken from well above the cut, so it overlaps the stem it is joined to
    return lower_part(t_ops, y_cut + 45), (xs[0] + xs[1]) / 2, y_cut


def right_stem_hook(ops, hook, x_height):
    """Replaces the foot of the rightmost stem with the hook."""
    import pathops
    piece, hook_cx, y_cut = hook
    xs = M.crossings(ops, y_cut)
    if len(xs) < 2:
        return ops
    x0, x1 = xs[-2], xs[-1]
    # the old foot, with the bit that curls out to the right of the stem
    cut = path_op(ops, box(x0 - 4, -10000, x1 + 70, y_cut), pathops.PathOp.DIFFERENCE)
    stem_cx = (x0 + x1) / 2
    moved = M.transformed(piece, 1.0, stem_cx - hook_cx)
    return path_op(cut, moved, pathops.PathOp.UNION)


def f_descender(f_ops, j_ops):
    """f's stem carried below the baseline, ending in j's hook."""
    import pathops
    fb, jb = M.bounds(f_ops), M.bounds(j_ops)
    y_cut = 120
    fx = M.crossings(f_ops, y_cut)
    jx = M.crossings(j_ops, y_cut)
    if len(fx) < 2 or len(jx) < 2:
        return f_ops
    # j below the cut (the hook), lined up under f's stem
    tail = lower_part(j_ops, y_cut + 45)
    tail = M.transformed(tail, 1.0, (fx[0] + fx[1]) / 2 - (jx[-2] + jx[-1]) / 2)
    # f's old foot goes, flared ends and all
    cut = path_op(f_ops, box(fx[0] - 40, -10000, fx[1] + 40, y_cut), pathops.PathOp.DIFFERENCE)
    return path_op(cut, tail, pathops.PathOp.UNION)


def arcs_x(x_ops, close_ops, open_ops):
    """x as )( : the parentheses brought down to the x-height, meeting in the middle."""
    from make_mono_static import embolden
    xb = M.bounds(x_ops)
    h = xb[3] - xb[1]
    cx = (xb[0] + xb[2]) / 2
    out = []
    for ops, side in ((close_ops, -1), (open_ops, 1)):
        b = M.bounds(ops)
        ky = h / (b[3] - b[1])
        kx = ky * 2.0                       # wider than tall, so the arcs bow out
        # the inner side of each arc touches the centre line, a little overlapped
        inner = b[2] if side < 0 else b[0]
        dx = cx - kx * inner + side * -12
        piece = M.transformed(ops, kx, dx, ky, xb[1] - ky * b[1])
        # the arcs run mostly up and down, so pressing them down leaves their stroke
        # as it was: only the widening changes it, and that is taken back across
        # the font's parentheses are drawn heavier than its letters: thin them a little more
        out += embolden(piece, 68 * (1 - kx) - 12, -4)
    return out


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
    hook = hook_of(M.record(gs, cmap[ord("t")]), x_height)
    changed = {}
    for ch in HOOKED:
        changed[cmap[ord(ch)]] = right_stem_hook(M.record(gs, cmap[ord(ch)]), hook, x_height)
    changed[cmap[ord("f")]] = f_descender(M.record(gs, cmap[ord("f")]), M.record(gs, cmap[ord("j")]))
    changed[cmap[ord("x")]] = arcs_x(M.record(gs, cmap[ord("x")]), M.record(gs, cmap[ord(")")]),
                                     M.record(gs, cmap[ord("(")]))

    upright = set()
    for cp, name in cmap.items():
        if any(a <= cp <= b for a, b in UPRIGHT_RANGES):
            upright.add(name)
    y0 = x_height / 2
    for name in font.getGlyphOrder():
        adv = hmtx[name][0]
        if name in upright or adv > M.CELL:
            continue
        ops = changed.get(name) or M.record(gs, name)
        if M.bounds(ops) is None:
            continue
        glyf[name] = to_tt_glyph_quadratic(skew(ops, ANGLE, y0))
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

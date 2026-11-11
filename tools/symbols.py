"""Symbols a terminal font is expected to have, drawn to the cell.

Box drawing, block elements, braille and the Powerline separators must reach the cell
edges exactly, so neighbouring cells join: they are drawn as straight geometry, not
taken from the font. The rest (check marks, bullets, superscripts, accented letters of
Latin Extended-A) is built from the font's own glyphs.

Everything works on the font after it has become TrueType and fixed-width, in cell
coordinates: x from 0 to CELL, y from the descent to the ascent.
"""
import collections
import math
import unicodedata

import make_mono as M

LIGHT = 60
HEAVY = 128
DOUBLE_LINE = 48
DOUBLE_GAP = 56   # between the two lines of a double stroke


class Cell:
    def __init__(self, font):
        self.w = M.CELL
        self.top = font["hhea"].ascent
        self.bottom = font["hhea"].descent
        self.cx = self.w / 2
        self.cy = (self.top + self.bottom) / 2


# ---------------------------------------------------------------- box drawing

def parse_box(name):
    """{direction: weight} from a BOX DRAWINGS name, plus dash count and arc flag."""
    words = name.replace("BOX DRAWINGS ", "")
    dashes = 0
    for word, n in (("DOUBLE DASH", 2), ("TRIPLE DASH", 3), ("QUADRUPLE DASH", 4)):
        if word in words:
            dashes = n
            words = words.replace(word + " ", "")
    arc = "ARC" in words
    words = words.replace("ARC ", "")
    weights = {"LIGHT": "l", "SINGLE": "l", "HEAVY": "h", "DOUBLE": "d"}
    dirs = {"UP": ["u"], "DOWN": ["d"], "LEFT": ["l"], "RIGHT": ["r"],
            "VERTICAL": ["u", "d"], "HORIZONTAL": ["l", "r"]}
    out = {}
    carried = None
    for group in words.split(" AND "):
        toks = group.split()
        if toks[0] in weights:
            w, toks = weights[toks[0]], toks[1:]
        elif toks[-1] in weights:
            w, toks = weights[toks[-1]], toks[:-1]
        else:
            w = carried
        carried = w
        for t in toks:
            for d in dirs.get(t, []):
                out[d] = w
    return out, dashes, arc


def box_glyph(cp, cell):
    name = unicodedata.name(chr(cp), "")
    c = cell
    if "DIAGONAL" in name:
        ops = []
        if "UPPER RIGHT TO LOWER LEFT" in name or "CROSS" in name:
            ops += stroke_line((c.w, c.top), (0, c.bottom), LIGHT)
        if "UPPER LEFT TO LOWER RIGHT" in name or "CROSS" in name:
            ops += stroke_line((0, c.top), (c.w, c.bottom), LIGHT)
        return ops
    segs, dashes, arc = parse_box(name)
    if arc:
        return arc_glyph(segs, c)
    thick = {"l": LIGHT, "h": HEAVY}
    off = DOUBLE_GAP / 2 + DOUBLE_LINE / 2       # each line of a double, from the centre
    other = {"u": "d", "d": "u", "l": "r", "r": "l"}

    def single_start(perp, sign, center):
        """Where a light or heavy stroke starts, near the centre."""
        a, b = segs.get(perp[0]), segs.get(perp[1])
        if a == "d" and b == "d":
            return center + sign * off           # between two doubles: touch the near line
        if a == "d" or b == "d":
            return center - sign * off - DOUBLE_LINE / 2   # a double on one side: reach its far line
        e = max(thick.get(a, 0) / 2, thick.get(b, 0) / 2)
        return center - sign * e

    def double_start(perp, side_dir, sign, center):
        """Where one line of a double starts. side_dir is the perpendicular direction
        on this line's side of the centre."""
        near, far = segs.get(side_dir), segs.get(other[side_dir])
        if near == "d":
            return center + sign * off           # meets the double on its side: inner corner
        if near:
            return center - sign * thick[near] / 2 if far != "d" else center + sign * off
        if far == "d":
            return center - sign * off - DOUBLE_LINE / 2   # the double turns away: outer corner
        if far:
            return center - sign * thick[far] / 2
        return center

    ops = []
    for d, w in segs.items():
        horiz = d in "lr"
        sign = 1 if d in "ru" else -1
        perp = ("u", "d") if horiz else ("l", "r")
        edge = (c.w if sign > 0 else 0) if horiz else (c.top if sign > 0 else c.bottom)
        center = c.cx if horiz else c.cy
        line_at = c.cy if horiz else c.cx
        if w in "lh":
            t = thick[w]
            start = single_start(perp, sign, center)
            if dashes:
                ops += dashed(horiz, start, edge, center, t, dashes, c)
            else:
                ops += bar(horiz, start, edge, line_at, t)
        else:
            # two lines: for a horizontal stroke the upper one faces "u", the lower one "d"
            for side, side_dir in ((1, perp[0] if horiz else "r"), (-1, perp[1] if horiz else "l")):
                start = double_start(perp, side_dir, sign, center)
                ops += bar(horiz, start, edge, line_at + side * off, DOUBLE_LINE)
    return ops


def bar(horiz, a, b, pos, t):
    lo, hi = min(a, b), max(a, b)
    if horiz:
        return M.rect(lo, pos - t / 2, hi, pos + t / 2)
    return M.rect(pos - t / 2, lo, pos + t / 2, hi)


def dashed(horiz, a, b, center, t, n, c):
    length = (c.w if horiz else c.top - c.bottom) / n
    gap = length * 0.3
    origin = 0 if horiz else c.bottom
    ops = []
    for k in range(n):
        lo = origin + k * length + gap / 2
        hi = lo + length - gap
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if hi > lo:
            ops += bar(horiz, lo, hi, c.cy if horiz else c.cx, t)
    return ops


def arc_glyph(segs, c):
    """Rounded corner: a quarter circle from the middle of one edge to the middle of
    the other, with straight runs where the cell is longer than the radius."""
    r = c.w / 2
    sx = 1 if "r" in segs else -1
    sy = 1 if "u" in segs else -1
    ox, oy = c.cx + sx * r, c.cy + sy * r          # circle centre, towards the open corner
    a0 = math.atan2(-sy, 0)                        # where the horizontal run meets the arc
    a1 = math.atan2(0, -sx)                        # where the vertical run meets the arc
    sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    steps = 16
    outer, inner = [], []
    for k in range(steps + 1):
        ang = a0 + sweep * k / steps
        outer.append((ox + (r + LIGHT / 2) * math.cos(ang), oy + (r + LIGHT / 2) * math.sin(ang)))
        inner.append((ox + (r - LIGHT / 2) * math.cos(ang), oy + (r - LIGHT / 2) * math.sin(ang)))
    ops = polygon(outer + inner[::-1])
    ops += bar(True, c.cx + sx * r, c.w if sx > 0 else 0, c.cy, LIGHT)
    ops += bar(False, c.cy + sy * r, c.top if sy > 0 else c.bottom, c.cx, LIGHT)
    return ops


def polygon(pts):
    area = M.signed_area(pts)
    if (area < 0) != M.CLOCKWISE:
        pts = pts[::-1]
    return [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


def stroke_line(p0, p1, t):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L * t / 2, dx / L * t / 2
    return polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)])


def round_line(p0, p1, t):
    """A stroke with round ends, like the font's own pen."""
    return stroke_line(p0, p1, t) + M.circle(p0, t / 2) + M.circle(p1, t / 2)


# ---------------------------------------------------------------- blocks

def block_glyph(cp, c):
    w, top, bot = c.w, c.top, c.bottom
    h = top - bot
    R = lambda x0, y0, x1, y1: M.rect(x0, y0, x1, y1)
    if cp == 0x2580:
        return R(0, bot + h / 2, w, top)
    if 0x2581 <= cp <= 0x2588:            # lower n/8
        return R(0, bot, w, bot + h * (cp - 0x2580) / 8)
    if 0x2589 <= cp <= 0x258F:            # left n/8, from 7/8 down
        return R(0, bot, w * (0x2590 - cp) / 8, top)
    if cp == 0x2590:
        return R(w / 2, bot, w, top)
    if cp in (0x2591, 0x2592, 0x2593):    # shades: a grid of squares
        share = {0x2591: 0.25, 0x2592: 0.5, 0x2593: 0.75}[cp]
        cols, rows = 4, 9
        cw, rh = w / cols, h / rows
        ops = []
        for i in range(cols):
            for j in range(rows):
                if cp == 0x2592 and (i + j) % 2:
                    continue
                if cp == 0x2591 and (i % 2 or j % 2):
                    continue
                if cp == 0x2593 and (i % 2 and j % 2):
                    continue
                ops += R(i * cw, bot + j * rh, (i + 1) * cw, bot + (j + 1) * rh)
        return ops
    if cp == 0x2594:
        return R(0, top - h / 8, w, top)
    if cp == 0x2595:
        return R(w * 7 / 8, bot, w, top)
    quads = {0x2596: "3", 0x2597: "4", 0x2598: "1", 0x2599: "134", 0x259A: "14",
             0x259B: "123", 0x259C: "124", 0x259D: "2", 0x259E: "23", 0x259F: "234"}
    if cp in quads:
        boxes = {"1": (0, bot + h / 2, w / 2, top), "2": (w / 2, bot + h / 2, w, top),
                 "3": (0, bot, w / 2, bot + h / 2), "4": (w / 2, bot, w, bot + h / 2)}
        return [op for q in quads[cp] for op in R(*boxes[q])]
    return None


# ---------------------------------------------------------------- braille

def braille_glyph(cp, c):
    bits = cp - 0x2800
    # dot numbers 1..8 -> (column, row from top)
    where = {0: (0, 0), 1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 1), 5: (1, 2), 6: (0, 3), 7: (1, 3)}
    h = c.top - c.bottom
    r = c.w * 0.11
    ops = []
    for bit, (col, row) in where.items():
        if bits & (1 << bit):
            x = c.w * (0.3 if col == 0 else 0.7)
            y = c.top - h * (0.14 + row * 0.24)
            ops += M.circle((x, y), r)
    return ops


# ---------------------------------------------------------------- powerline

def powerline_glyph(cp, c, gs, cmap):
    w, top, bot, cy = c.w, c.top, c.bottom, c.cy
    if cp == 0xE0B0:
        return polygon([(0, top), (w, cy), (0, bot)])
    if cp == 0xE0B2:
        return polygon([(w, top), (0, cy), (w, bot)])
    if cp == 0xE0B1:
        return stroke_line((0, top), (w, cy), LIGHT) + stroke_line((w, cy), (0, bot), LIGHT)
    if cp == 0xE0B3:
        return stroke_line((w, top), (0, cy), LIGHT) + stroke_line((0, cy), (w, bot), LIGHT)
    t = 64
    if cp == 0xE0A0:   # branch: a line with a fork joining it
        x0, x1 = w * 0.32, w * 0.72
        y0, y1, yb = cy + 300, cy - 300, cy + 170
        ops = round_line((x0, y1 + 70), (x0, y0 - 70), t)
        ops += circle_ring((x0, y0), 62, t * 0.8) + circle_ring((x0, y1), 62, t * 0.8)
        ops += circle_ring((x1, yb + 60), 62, t * 0.8)
        ops += round_line((x1, yb), (x1, cy - 20), t) + round_line((x1, cy - 20), (x0, y1 + 140), t)
        return ops
    if cp == 0xE0A2:   # padlock
        body = M.rect(w * 0.15, cy - 260, w * 0.85, cy + 60)
        shackle = []
        r = w * 0.22
        for k in range(13):
            ang = math.pi * k / 12
            shackle.append((c.cx + r * math.cos(ang), cy + 60 + r * 1.3 * math.sin(ang)))
        ops = body
        for a, b in zip(shackle, shackle[1:]):
            ops += round_line(a, b, t)
        return ops
    if cp == 0xE0A1:   # "LN", line number
        ops = []
        for ch, (dx, dy) in (("L", (-w * 0.2, 180)), ("N", (w * 0.2, -180))):
            g = M.record(gs, cmap[ord(ch)])
            b = M.bounds(g)
            k = 0.5
            ops += M.transformed(g, k, c.cx + dx - k * (b[0] + b[2]) / 2, k, cy + dy - k * (b[1] + b[3]) / 2)
        return ops
    return None


def circle_ring(center, r, t):
    """A ring: outer circle with the inner one cut out (inner turns the other way)."""
    outer = M.circle(center, r + t / 2)
    inner = M.circle(center, r - t / 2)
    pts = M.polygon_points(inner)[0][::-1]
    return outer + [("moveTo", (pts[0],))] + [("lineTo", (p,)) for p in pts[1:]] + [("closePath", ())]


# ---------------------------------------------------------------- from the font's own glyphs

def from_font(cp, c, gs, cmap, weight):
    def g(ch):
        return M.record(gs, cmap[ord(ch) if isinstance(ch, str) else ch])

    def fit(ops, k, cx, cy):
        b = M.bounds(ops)
        out = M.transformed(ops, k, cx - k * (b[0] + b[2]) / 2, k, cy - k * (b[1] + b[3]) / 2)
        return weight(out, 68 * (1 - k), 68 * (1 - k)) if abs(1 - k) > 0.02 else out

    hy = M.bounds(g("-"))
    axis = (hy[1] + hy[3]) / 2
    x_top = M.bounds(g("x"))[3]
    t = 68
    if cp == 0x2022:                               # bullet
        return fit(g(0x25CF), 0.5, c.cx, axis)
    if cp in (0x2713, 0x2714):                     # check mark
        tw = t if cp == 0x2713 else t * 1.5
        a, b, d = (c.w * 0.14, axis + 20), (c.w * 0.4, axis - 170), (c.w * 0.88, axis + 260)
        return round_line(a, b, tw) + round_line(b, d, tw)
    if cp in (0x2717, 0x2718):                     # ballot x
        tw = t if cp == 0x2717 else t * 1.5
        s = c.w * 0.36
        return round_line((c.cx - s, axis + s), (c.cx + s, axis - s), tw) + \
            round_line((c.cx - s, axis - s), (c.cx + s, axis + s), tw)
    if cp == 0x2039:
        return fit(g("<"), 0.7, c.cx, axis)
    if cp == 0x203A:
        return fit(g(">"), 0.7, c.cx, axis)
    if cp == 0x201E:                               # „ low double quote
        q = g(0x201D)
        b = M.bounds(q)
        return M.transformed(q, 1.0, 0.0, 1.0, -b[1] - 60)
    if cp == 0x201A:                               # ‚
        q = g(0x2019)
        b = M.bounds(q)
        return M.transformed(q, 1.0, 0.0, 1.0, -b[1] - 60)
    if cp == 0x203C:                               # ‼
        e = g("!")
        b = M.bounds(e)
        k = 0.85
        return fit(e, k, c.w * 0.3, (b[1] + b[3]) / 2) + fit(e, k, c.w * 0.7, (b[1] + b[3]) / 2)
    if cp == 0xB5:                                 # µ from Greek mu
        return g(0x3BC)
    if cp == 0xA6:                                 # broken bar
        b = M.bounds(g("|"))
        mid = (b[1] + b[3]) / 2
        return round_line((c.cx, b[1] + t / 2), (c.cx, mid - 70), t) + round_line((c.cx, mid + 70), (c.cx, b[3] - t / 2), t)
    if cp == 0xAF:                                 # macron
        return round_line((c.w * 0.18, 700), (c.w * 0.82, 700), t)
    if cp == 0x23FA:                               # ⏺ record (Claude Code's tool marker)
        return fit(g(0x25CF), 0.7, c.cx, axis)
    if cp == 0x23BF:                               # ⎿ (Claude Code's result corner)
        y = x_top * 0.35
        return round_line((c.w * 0.3, c.top - 40), (c.w * 0.3, y), t) + round_line((c.w * 0.3, y), (c.w, y), t)
    if cp == 0xFFFD:                               # replacement character: diamond with a ? cut out
        import pathops
        from fontTools.pens.recordingPen import RecordingPen
        dia = polygon([(c.cx, c.top - 60), (c.w - 10, c.cy), (c.cx, c.bottom + 60), (10, c.cy)])
        q = fit(g("?"), 0.62, c.cx, c.cy)
        a, b = pathops.Path(), pathops.Path()
        for path, ops in ((a, dia), (b, q)):
            pen = path.getPen()
            for op, args in ops:
                getattr(pen, op)(*args)
        out = pathops.op(a, b, pathops.PathOp.DIFFERENCE)
        rec = RecordingPen()
        out.draw(rec)
        return rec.value
    # superscript and subscript digits
    sup = {0x2070: "0", 0x2074: "4", 0x2075: "5", 0x2076: "6", 0x2077: "7", 0x2078: "8", 0x2079: "9"}
    sub = {0x2080 + n: str(n) for n in range(10)}
    if cp in sup or cp in sub:
        d = g(sup.get(cp) or sub.get(cp))
        out = fit(d, 0.6, c.cx, 600 if cp in sup else -40)
        # stand on the line the font's own ones stand on (¹ ² ³ ⁴, ₁ ₂ ₃ ₄), so a
        # number made of drawn and built digits keeps one line
        own = [0xB9, 0xB2, 0xB3, 0x2074] if cp in sup else [0x2081, 0x2082, 0x2083, 0x2084]
        bottoms = sorted(M.bounds(g(o))[1] for o in own if o in cmap and o != cp)
        if bottoms:
            out = M.transformed(out, 1.0, 0.0, 1.0, bottoms[len(bottoms) // 2] - M.bounds(out)[1])
        return out
    return None


# Latin Extended-A: combining mark -> how to draw the accent
def latin_ext_a(font, gs, cmap, c, weight, made):
    def g(cp):
        return M.record(gs, cmap[cp])

    def accent(mark):
        if mark == 0x304:                                   # macron
            return round_line((0, 0), (220, 0), 64)
        if mark == 0x306:                                   # breve: a small cup
            pts = [(110 + 110 * math.cos(math.pi + math.pi * k / 10), 110 * math.sin(math.pi + math.pi * k / 10) + 110)
                   for k in range(11)]
            out = []
            for a, b in zip(pts, pts[1:]):
                out += round_line(a, b, 56)
            return out
        if mark == 0x307:                                   # dot above
            return M.circle((0, 0), 48)
        if mark == 0x30C:                                   # caron: circumflex upside down
            ci = g(0x5E)
            b = M.bounds(ci)
            return flip_v(ci, b)
        if mark == 0x30B:                                   # double acute
            a = g(0xB4)
            b = M.bounds(a)
            return M.transformed(a, 0.75, -60, 0.75, 0) + M.transformed(a, 0.75, 90, 0.75, 0)
        if mark == 0x328:                                   # ogonek: cedilla mirrored
            ce = g(0xB8)
            b = M.bounds(ce)
            return flip_h(ce, b)
        return None

    for cp in range(0x100, 0x180):
        if cp in cmap or cp in made:
            continue
        parts = unicodedata.decomposition(chr(cp)).split()
        if len(parts) != 2 or parts[0].startswith("<"):
            continue
        base, mark = int(parts[0], 16), int(parts[1], 16)
        acc = accent(mark)
        if acc is None or base not in cmap:
            continue
        base_ops = g(base)
        dot_cx = None
        if chr(base) in "ij" and mark != 0x328:
            cs = M.polygon_points_ops(base_ops)
            dot = max(cs, key=lambda q: M.bounds(q)[1])
            dot_cx = (M.bounds(dot)[0] + M.bounds(dot)[2]) / 2
            base_ops = [op for q in cs if q is not dot for op in q]
        bb, ab = M.bounds(base_ops), M.bounds(acc)
        upper = chr(base).isupper()
        k = 0.75 if upper else 0.85
        if mark == 0x328:
            # the ogonek, one stroke of the round pen: from the bottom of the letter down
            # and to the left, curling back to the right. It starts on the lowest point of
            # U, which has no foot, and on the right foot of the others (u's right stem).
            pts = [p for q in M.polygon_points(M.flattened(base_ops)) for p in q]
            if chr(base) == "U":
                ax = min(pts, key=lambda p: p[1])[0] + 30
            else:
                ax = bb[2] - 45
            near = [p[1] for p in pts if abs(p[0] - ax) < 30]
            floor = min(near) if near else bb[1]
            w = 58 if upper else 54
            size = 1.0 if upper else 0.9
            start = (ax, floor + w / 2)
            end = (ax + 60 * size, floor - 200 * size)
            hook = pen_stroke(start, [("curve", (ax - 75 * size, floor - 40 * size),
                                       (ax - 70 * size, floor - 205 * size), end)], w)
            hb = M.bounds(hook)
            if hb[2] > M.CELL - 10:
                hook = M.transformed(hook, 1.0, M.CELL - 10 - hb[2])
            made[cp] = base_ops + hook
            continue
        elif chr(base) in "dlLtk" and mark == 0x30C:
            # ď ľ Ľ ť: a small apostrophe-like caron to the right of the ascender
            q = g(0x2019)
            qb = M.bounds(q)
            made[cp] = base_ops + M.transformed(q, 0.8, bb[2] + 10 - 0.8 * qb[0], 0.8, bb[3] - 0.8 * qb[3])
            continue
        else:
            # over the stem of i and j (where the dot was), the middle of the others
            mid = dot_cx if dot_cx is not None else (bb[0] + bb[2]) / 2
            dx = mid - k * (ab[0] + ab[2]) / 2
            dy = bb[3] + 50 - k * ab[1]
            room = 880 - dy
            if k * (ab[3] - ab[1]) > room:
                k = room / (ab[3] - ab[1])
                dy = bb[3] + 50 - k * ab[1]
                dx = (bb[0] + bb[2]) / 2 - k * (ab[0] + ab[2]) / 2
        made[cp] = base_ops + M.transformed(acc, k, dx, k, dy)

    # letters with a stroke or other shape, not a mark
    def with_bar(base, y_frac, x0f=0.15, x1f=0.85):
        b = M.bounds(g(base))
        y = b[1] + (b[3] - b[1]) * y_frac
        return g(base) + round_line((b[0] + (b[2] - b[0]) * x0f, y), (b[0] + (b[2] - b[0]) * x1f, y), 60)

    extra = {
        0x110: lambda: with_bar(ord("D"), 0.5, -0.15, 0.45),   # Đ
        0x111: lambda: with_bar(ord("d"), 0.78, 0.45, 1.05),   # đ
        0x126: lambda: with_bar(ord("H"), 0.75, -0.05, 1.05),  # Ħ
        0x127: lambda: with_bar(ord("h"), 0.8, -0.1, 0.55),    # ħ
        0x166: lambda: with_bar(ord("T"), 0.45, 0.2, 0.8),     # Ŧ
        0x167: lambda: with_bar(ord("t"), 0.35, 0.1, 0.9),     # ŧ
    }
    for cp, fn in extra.items():
        if cp not in cmap:
            made[cp] = fn()
    for cp, base in ((0x141, "L"), (0x142, "l")):            # Ł ł: a slash through the stem
        if cp in cmap:
            continue
        b = M.bounds(g(ord(base)))
        sx = b[0] + 70 if base == "L" else (b[0] + b[2]) / 2
        cy = b[1] + (b[3] - b[1]) * 0.5
        made[cp] = g(ord(base)) + round_line((sx - 110, cy - 70), (sx + 110, cy + 70), 60)
    if 0x17F not in cmap:                                    # ſ long s: f without its crossbar
        f_ops = g(ord("f"))
        fb = M.bounds(f_ops)
        xs = M.crossings(f_ops, fb[1] + 60)                  # the stem, low down
        if len(xs) >= 2:
            # the crossbar: the lowest height (above the stem's foot) where f is wider than its stem
            stem_w = xs[1] - xs[0]
            bar_top = bar_bottom = None
            y = fb[1] + 60
            while y < fb[3]:
                row = M.crossings(f_ops, y)
                if row and row[-1] - row[0] > stem_w * 1.8:
                    bar_bottom = y
                    while y < fb[3]:
                        row = M.crossings(f_ops, y)
                        if not row or row[-1] - row[0] <= stem_w * 1.8:
                            bar_top = y
                            break
                        y += 5
                    break
                y += 5
            if bar_top and bar_bottom:
                # the stem above and below the crossbar, joined through the crossbar's height
                # by a piece that follows the stem's own edges, so the waist has no step
                hi, lo = bar_top + 15, bar_bottom - 15
                top = M.clip_polygon(f_ops, [(-9999, hi), (-9999, 9999), (9999, 9999), (9999, hi)])
                stem = M.clip_polygon(f_ops, [(-9999, -9999), (-9999, lo), (9999, lo), (9999, -9999)])
                mid = (xs[0] + xs[1]) / 2
                join = M.bridge_between(f_ops, f_ops, hi, lo, mid, not M.CLOCKWISE)
                made[0x17F] = top + stem + join
    if 0x131 not in cmap:                                    # ı dotless i
        made[0x131] = regular_i(gs, cmap, dotless=True)


def flip_v(ops, b):
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    f = M.transformed(ops, 1.0, 0.0, -1.0, b[1] + b[3])
    rec = RecordingPen()
    rev = ReverseContourPen(rec)
    for op, args in f:
        getattr(rev, op)(*args)
    return rec.value


def flip_h(ops, b):
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    f = M.transformed(ops, -1.0, b[0] + b[2])
    rec = RecordingPen()
    rev = ReverseContourPen(rec)
    for op, args in f:
        getattr(rev, op)(*args)
    return rec.value


# ---------------------------------------------------------------- control pictures

CONTROL_NAMES = ("NUL SOH STX ETX EOT ENQ ACK BEL BS HT LF VT FF CR SO SI "
                 "DLE DC1 DC2 DC3 DC4 NAK SYN ETB CAN EM SUB ESC FS GS RS US SP DEL").split()


def control_picture(cp, c, gs, cmap, weight):
    """U+2400..2426: the control code's standard short name in small capitals."""
    def letters(text):
        # Two letters step down diagonally. Three sit as two over one, which leaves room
        # for larger letters than a diagonal of three. The pair on top is made narrower
        # (kx) than tall (ky) so it keeps clear of the cell edges and of its neighbours.
        n = len(text)
        if n == 2:
            spots = [(0.34, 560, 0.42, 0.52), (0.66, 150, 0.42, 0.52)]
        else:
            spots = [(0.32, 560, 0.36, 0.48), (0.68, 560, 0.36, 0.48), (0.5, 150, 0.42, 0.48)]
        ops = []
        for ch, (xf, y, kx, ky) in zip(text, spots):
            g = M.record(gs, cmap[ord(ch)])
            b = M.bounds(g)
            one = M.transformed(g, kx, c.w * xf - kx * (b[0] + b[2]) / 2, ky, y - ky * (b[1] + b[3]) / 2)
            ops += weight(one, 68 * (1 - kx) * 0.5, 68 * (1 - ky) * 0.5)
        return ops

    idx = cp - 0x2400
    if idx < len(CONTROL_NAMES):
        return letters(CONTROL_NAMES[idx])
    if cp == 0x2422:                       # blank symbol: b with a stroke through it
        g = M.record(gs, cmap[ord("b")])
        b = M.bounds(g)
        return g + round_line((b[0] - 20, b[1] + 120), (b[2] + 20, b[3] - 120), 60)
    if cp == 0x2423:                       # open box, the visible space
        y0, y1 = 0, 180
        return round_line((c.w * 0.12, y1), (c.w * 0.12, y0), 64) + \
            round_line((c.w * 0.12, y0), (c.w * 0.88, y0), 64) + round_line((c.w * 0.88, y0), (c.w * 0.88, y1), 64)
    if cp == 0x2424:                       # newline
        return letters("NL")
    if cp == 0x2425:                       # delete form two: hatching
        return round_line((c.w * 0.15, 120), (c.w * 0.45, 620), 60) + \
            round_line((c.w * 0.4, 120), (c.w * 0.7, 620), 60) + round_line((c.w * 0.65, 120), (c.w * 0.95, 620), 60)
    if cp == 0x2426:                       # substitute form two: a reversed question mark
        g = M.record(gs, cmap[ord("?")])
        return flip_h(g, M.bounds(g))
    return None


# ---------------------------------------------------------------- conjoining jamo

COMPAT_INITIAL = [0x3131, 0x3132, 0x3134, 0x3137, 0x3138, 0x3139, 0x3141, 0x3142, 0x3143, 0x3145,
                  0x3146, 0x3147, 0x3148, 0x3149, 0x314A, 0x314B, 0x314C, 0x314D, 0x314E]
COMPAT_FINAL = [None, 0x3131, 0x3132, 0x3133, 0x3134, 0x3135, 0x3136, 0x3137, 0x3139, 0x313A, 0x313B,
                0x313C, 0x313D, 0x313E, 0x313F, 0x3140, 0x3141, 0x3142, 0x3144, 0x3145, 0x3146,
                0x3147, 0x3148, 0x314A, 0x314B, 0x314C, 0x314D, 0x314E]


# Where each conjoining jamo sits in its two cells, the same place whatever it is joined
# with, so jamo drawn one over another where nothing joins them never collide:
# the initial at the top left, a tall vowel on the right, a flat vowel under the
# initial, the final along the bottom. (x0, y0, x1, y1), x across the two cells.
JAMO_SLOT_INITIAL = (70, 500, 540, 790)
JAMO_SLOT_TALL = (600, 290, 930, 790)
JAMO_SLOT_FLAT = (70, 290, 540, 470)
JAMO_SLOT_FINAL = (70, -110, 930, 240)
TALL_VOWELS = {0, 1, 2, 3, 4, 5, 6, 7, 20}           # ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅣ
FLAT_VOWELS = {8, 12, 13, 17, 18}                    # ㅗ ㅛ ㅜ ㅠ ㅡ
MIXED_VOWELS = {9: (8, 0), 10: (8, 1), 11: (8, 20),  # ㅘ ㅙ ㅚ
                14: (13, 4), 15: (13, 5), 16: (13, 20), 19: (18, 20)}   # ㅝ ㅞ ㅟ ㅢ


def add_conjoining_jamo(font, to_glyph, weight):
    """Modern conjoining jamo (U+1100..), as Hangul written in decomposed form arrives
    (file names saved on macOS, for one). Each is its compatibility jamo made smaller
    and set in its own fixed place in the two cells (the JAMO_SLOT_ boxes), so an initial,
    a vowel and a final drawn one over another where nothing joins them still read as
    one syllable, like a syllable of the non-square kind. An initial takes two cells; a
    vowel or final takes none, as terminals count them, and is drawn over the cells
    before it. The fillers U+115F (an initial, two cells) and U+1160 (a vowel, none) are
    blank. Returns the feature code that joins an initial, a vowel and an optional final
    into the drawn syllable, in ccmp, which stays on even with ligatures turned off."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    wide = 2 * M.CELL
    names = {}
    for i, compat in enumerate(COMPAT_INITIAL):
        names[0x1100 + i] = (compat, wide, 0)
    for v in range(21):
        names[0x1161 + v] = (0x314F + v, 0, -wide)
    for f in range(1, 28):
        names[0x11A7 + f] = (COMPAT_FINAL[f], 0, -wide)
    hy = M.bounds(M.record(gs, cmap[ord("-")]))
    stroke = hy[3] - hy[1]

    def fit(compat, slot):
        """The compatibility jamo scaled to fit the slot (its proportions kept), its stroke
        given back to the weight of the syllables, centred in the slot."""
        ops = M.record(gs, cmap[compat])
        b = M.bounds(ops)
        k = min((slot[2] - slot[0]) / (b[2] - b[0]), (slot[3] - slot[1]) / (b[3] - b[1]))
        out = weight(M.transformed(ops, k, 0.0, k, 0.0), stroke * (1 - k), stroke * (1 - k))
        ob = M.bounds(out)
        return M.transformed(out, 1.0, (slot[0] + slot[2]) / 2 - (ob[0] + ob[2]) / 2,
                             1.0, (slot[1] + slot[3]) / 2 - (ob[1] + ob[3]) / 2)

    def drawn(cp):
        if cp <= 0x1112:
            return fit(COMPAT_INITIAL[cp - 0x1100], JAMO_SLOT_INITIAL)
        if cp <= 0x1175:
            v = cp - 0x1161
            if v in TALL_VOWELS:
                return fit(0x314F + v, JAMO_SLOT_TALL)
            if v in FLAT_VOWELS:
                return fit(0x314F + v, JAMO_SLOT_FLAT)
            flat, tall = MIXED_VOWELS[v]
            return fit(0x314F + flat, JAMO_SLOT_FLAT) + fit(0x314F + tall, JAMO_SLOT_TALL)
        return fit(COMPAT_FINAL[cp - 0x11A7], JAMO_SLOT_FINAL)

    order = font.getGlyphOrder()
    new = []
    for cp, (compat, adv, dx) in names.items():
        if cp in cmap or compat not in cmap:
            continue
        name = f"uni{cp:04X}"
        ops = drawn(cp)
        glyf[name] = to_glyph(M.transformed(ops, 1.0, dx) if dx else ops)
        hmtx[name] = (adv, 0)
        new.append(name)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[cp] = name
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    for cp, adv in ((0x115F, wide), (0x1160, 0)):
        if cp in cmap:
            continue
        name = f"uni{cp:04X}"
        glyf[name] = TTGlyphPen(None).glyph()
        hmtx[name] = (adv, 0)
        new.append(name)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[cp] = name
    # ss04: the fillers drawn as a ring of dots where their jamo would stand, the
    # initial filler in the initial's place, the vowel filler in the vowel's place
    period = M.record(gs, cmap[ord(".")])
    pb = M.bounds(period)
    k = 0.55

    def dotted_ring(slot, dx):
        cx, cy = (slot[0] + slot[2]) / 2 + dx, (slot[1] + slot[3]) / 2
        r = min(slot[2] - slot[0], slot[3] - slot[1]) * 0.46
        out = []
        for i in range(12):
            a = 2 * math.pi * i / 12
            x, y = cx + r * math.sin(a), cy + r * math.cos(a)
            out += M.transformed(period, k, x - k * (pb[0] + pb[2]) / 2, k, y - k * (pb[1] + pb[3]) / 2)
        return out

    visible = []
    for cp, slot, dx in ((0x115F, JAMO_SLOT_INITIAL, 0), (0x1160, JAMO_SLOT_TALL, -wide)):
        if cp not in font.getBestCmap():
            continue
        name = font.getBestCmap()[cp]
        alt = f"{name}.ss04"
        glyf[alt] = to_glyph(dotted_ring(slot, dx))
        hmtx[alt] = hmtx[name]
        new.append(alt)
        visible.append((name, alt))
    M.ALTERNATES["ss04"] = visible
    font.setGlyphOrder(order + [n for n in new if n not in order])
    glyf.glyphOrder = font.getGlyphOrder()
    cmap = font.getBestCmap()

    rules = []
    for cp in range(0xAC00, 0xD7A4):
        if cp not in cmap:
            continue
        n = cp - 0xAC00
        i, v, f = n // 588, (n % 588) // 28, n % 28
        seq = [cmap.get(0x1100 + i), cmap.get(0x1161 + v)] + ([cmap.get(0x11A7 + f)] if f else [])
        if all(seq):
            rules.append(f"    sub {' '.join(seq)} by {cmap[cp]};")
    # A vowel or final with no initial before it to sit on (after a letter, a digit, a
    # space) would be drawn over the two cells before it, on someone else's glyph. Where
    # text is shaped it is swapped for a version that stands on its own, two cells wide,
    # drawn like its compatibility jamo. A vowel after an initial, and a final after an
    # initial (with or without a vowel) or after a syllable with no final, still join.
    alone = {}
    for cp, compat in [(0x1100 + i, COMPAT_INITIAL[i]) for i in range(19)] + \
                      [(0x1161 + v, 0x314F + v) for v in range(21)] + \
                      [(0x11A7 + f, COMPAT_FINAL[f]) for f in range(1, 28)]:
        if cp in cmap and compat in cmap:
            name = cmap[cp] + ".alone"
            glyf[name] = glyf[cmap[compat]]
            hmtx[name] = (wide, 0)
            alone[cmap[cp]] = name
    font.setGlyphOrder(font.getGlyphOrder() + [n for n in alone.values() if n not in font.getGlyphOrder()])
    glyf.glyphOrder = font.getGlyphOrder()

    initials = [cmap[c] for c in list(range(0x1100, 0x1113)) + [0x115F] if c in cmap]
    # an initial with nothing after it stands alone too, full size in its two cells. An
    # initial with a final straight after it (ᄀᆲ, or ᄀ with the vowel filler) keeps its
    # place with the final under it, in the same two cells: a terminal gives the pair
    # two cells, and anything drawn wider would be cut off there.
    lone_initials = [cmap[c] for c in range(0x1100, 0x1113) if c in cmap and cmap[c] in alone]
    vowel_or_filler = [cmap[c] for c in range(0x1160, 0x1176) if c in cmap]
    vowels = [cmap[c] for c in range(0x1161, 0x1176) if c in cmap and cmap[c] in alone]
    finals = [cmap[c] for c in range(0x11A8, 0x11C3) if c in cmap and cmap[c] in alone]
    open_syllables = [cmap[0xAC00 + i * 588 + v * 28] for i in range(19) for v in range(21)
                      if 0xAC00 + i * 588 + v * 28 in cmap]
    fea_alone = ""
    if vowels and finals and initials:
        fea_alone = (
            "@JAMO_L = [" + " ".join(initials) + "];\n"
            "@JAMO_V = [" + " ".join(vowels) + "];\n"
            "@JAMO_V_ALONE = [" + " ".join(alone[g] for g in vowels) + "];\n"
            "@JAMO_T = [" + " ".join(finals) + "];\n"
            "@JAMO_T_ALONE = [" + " ".join(alone[g] for g in finals) + "];\n"
            "@SYLLABLE_LV = [" + " ".join(open_syllables) + "];\n"
            "@JAMO_L1 = [" + " ".join(lone_initials) + "];\n"
            "@JAMO_L1_ALONE = [" + " ".join(alone[g] for g in lone_initials) + "];\n"
            "@JAMO_V_ANY = [" + " ".join(vowel_or_filler) + "];\n"
            "lookup jamo_l_alone {\n    sub @JAMO_L1 by @JAMO_L1_ALONE;\n} jamo_l_alone;\n"
            "lookup jamo_v_alone {\n    sub @JAMO_V by @JAMO_V_ALONE;\n} jamo_v_alone;\n"
            "lookup jamo_t_alone {\n    sub @JAMO_T by @JAMO_T_ALONE;\n} jamo_t_alone;\n"
            "lookup hangul_alone {\n"
            "    ignore sub @JAMO_L @JAMO_V';\n"
            "    ignore sub @JAMO_L @JAMO_V_ANY @JAMO_T';\n"
            "    ignore sub @JAMO_L @JAMO_T';\n"
            "    ignore sub @SYLLABLE_LV @JAMO_T';\n"
            "    ignore sub @JAMO_L1' @JAMO_V_ANY;\n"
            "    ignore sub @JAMO_L1' @JAMO_T;\n"
            "    sub @JAMO_L1' lookup jamo_l_alone;\n"
            "    sub @JAMO_V' lookup jamo_v_alone;\n"
            "    sub @JAMO_T' lookup jamo_t_alone;\n"
            "} hangul_alone;\n")
    fea = fea_alone + "lookup hangul_compose {\n" + "\n".join(rules) + "\n} hangul_compose;\n" \
        "feature ccmp {\n    lookup hangul_compose;\n" + \
        ("    lookup hangul_alone;\n" if fea_alone else "") + "} ccmp;\n"
    return new, fea


# ---------------------------------------------------------------- Korean extras

def korean_extras(font, gs, cmap, weight, made):
    """⑯..⑳ and ⒃..⒇: the ring of ⑮ or the parentheses of ⒂ with two new digits inside.
    ㈝ ㈞: the parentheses of ㈜, drawn in towards the edges, around 오전 and 오후."""
    def contours(cp):
        return M.polygon_points_ops(M.record(gs, cmap[cp]))

    def flat(cs):
        return [op for q in cs for op in q]

    def place(ch, box, kmax_x=None):
        """A glyph scaled to the box's height (narrower if the box needs it), centred in it."""
        d = M.record(gs, cmap[ord(ch)])
        db = M.bounds(d)
        ky = (box[3] - box[1]) / (db[3] - db[1])
        kx = min(ky, (box[2] - box[0]) / (db[2] - db[0]))
        ky = min(ky, kx * 2.4)               # no more than 2.4 times taller than it is wide
        out = M.transformed(d, kx, (box[0] + box[2]) / 2 - kx * (db[0] + db[2]) / 2,
                            ky, (box[1] + box[3]) / 2 - ky * (db[1] + db[3]) / 2)
        # a narrower squeeze thins the upright strokes: bring them back to the
        # thickness of the crossing strokes, no further (small digits stay light)
        return weight(out, 68 * (ky - kx) * 0.5, 0.0) if ky - kx > 0.02 else out

    def like(n, digits):
        """n's two digits at the size and place of the digits of ⑮ or ⒂."""
        mid = (M.bounds(flat(digits))[0] + M.bounds(flat(digits))[2]) / 2
        left = [q for q in digits if (M.bounds(q)[0] + M.bounds(q)[2]) / 2 < mid]
        right = [q for q in digits if (M.bounds(q)[0] + M.bounds(q)[2]) / 2 >= mid]
        if not left or not right:
            return None
        lb, rb = M.bounds(flat(left)), M.bounds(flat(right))
        five = M.bounds(M.record(gs, cmap[ord("5")]))
        kx = (rb[2] - rb[0]) / (five[2] - five[0])
        ky = (rb[3] - rb[1]) / (five[3] - five[1])
        gap = rb[0] - lb[2]
        glyphs = []
        for ch in str(n):
            g = M.record(gs, cmap[ord(ch)])
            if ch == "0":
                # no dot in the zero here: "20" reads as twenty without it
                cs = M.polygon_points_ops(g)
                if len(cs) > 2:
                    dot = min(cs, key=lambda q: (M.bounds(q)[2] - M.bounds(q)[0]) * (M.bounds(q)[3] - M.bounds(q)[1]))
                    g = [op for q in cs if q is not dot for op in q]
            glyphs.append(g)
        bs = [M.bounds(g) for g in glyphs]
        total = sum(kx * (b[2] - b[0]) for b in bs) + gap
        left_x = (lb[0] + rb[2]) / 2 - total / 2
        out = []
        for g, b in zip(glyphs, bs):
            one = M.transformed(g, kx, left_x - kx * b[0], ky, rb[1] - ky * b[1])
            out += weight(one, 68 * (1 - kx) * 0.5, 68 * (1 - ky) * 0.5)
            left_x += kx * (b[2] - b[0]) + gap
        return out

    if 0x246E in cmap:                                   # ⑮: keep the ring (the two largest contours)
        cs = sorted(contours(0x246E), key=lambda q: -(M.bounds(q)[2] - M.bounds(q)[0]))
        ring, digits = cs[:2], cs[2:]
        for n in range(16, 21):
            cp = 0x246F + (n - 16)
            if cp not in cmap and (ops := like(n, digits)):
                made[cp] = flat(ring) + ops

    if 0x2482 in cmap:                                   # ⒂: keep the parentheses (the outermost contours)
        cs = contours(0x2482)
        gb = M.bounds(flat(cs))
        parens = [q for q in cs if M.bounds(q)[0] - gb[0] < 15 or gb[2] - M.bounds(q)[2] < 15]
        digits = [q for q in cs if not any(q is p for p in parens)]
        if len(parens) == 2 and digits:
            for n in range(16, 21):
                cp = 0x2483 + (n - 16)
                if cp not in cmap and (ops := like(n, digits)):
                    made[cp] = flat(parens) + ops

    if 0x321C in cmap:                                   # ㈜ -> ㈝ (오전), ㈞ (오후)
        cs = contours(0x321C)
        gb = M.bounds(flat(cs))
        parens = [q for q in cs if M.bounds(q)[0] - gb[0] < 15 or gb[2] - M.bounds(q)[2] < 15]
        inner = [q for q in cs if not any(q is p for p in parens)]
        if len(parens) == 2 and inner:
            ib = M.bounds(flat(inner))
            squeezed = []
            for q in parens:
                b = M.bounds(q)
                left_side = b[0] - gb[0] < 15
                anchor = b[0] if left_side else b[2]      # keep the outer edge where it is
                one = M.transformed(q, 0.55, anchor * 0.45)
                squeezed += weight(one, 68 * 0.45 * 0.6, 0.0)
            sq = M.bounds(squeezed)
            lp_in = max(M.bounds(q)[2] for q in M.polygon_points_ops(squeezed) if M.bounds(q)[0] - sq[0] < 15)
            rp_in = min(M.bounds(q)[0] for q in M.polygon_points_ops(squeezed) if sq[2] - M.bounds(q)[2] < 15)
            for cp, word in ((0x321D, "오전"), (0x321E, "오후")):
                if cp in cmap:
                    continue
                x0, x1 = lp_in + 10, rp_in - 10
                mid = (x0 + x1) / 2
                y0, y1 = ib[1] + 40, ib[3] - 10
                ops = squeezed + place(word[0], (x0, y0, mid - 5, y1)) + place(word[1], (mid + 5, y0, x1, y1))
                # keep it inside its two cells, with room for the Bold to grow
                ob = M.bounds(ops)
                lo, hi = 45, 2 * M.CELL - 45
                if ob[0] < lo or ob[2] > hi:
                    k = (hi - lo) / (ob[2] - ob[0])
                    ops = M.transformed(ops, k, lo - k * ob[0])
                made[cp] = ops


def rotated(ops, quarter_turns, cx, cy):
    """Turned by 90° steps about (cx, cy). A turn keeps the contour direction."""
    out = ops
    for _ in range(quarter_turns % 4):
        out = [(op, tuple(None if pt is None else (cx - (pt[1] - cy), cy + (pt[0] - cx)) for pt in args))
               for op, args in out]
    return out


def arrows(gs, cmap, weight, made):
    """← ↑ → ↓ ↔ ↕ ↖ ↗ ↘ ↙ drawn like the -> ligature: the font's own > as the head, the
    hyphen lengthened as the shaft. The head is made smaller to fit one cell, and its
    stroke is brought back to the hyphen's weight."""
    if not all(ord(ch) in cmap for ch in "->"):
        return
    hy_ops = M.record(gs, cmap[ord("-")])
    hy = M.bounds(hy_ops)
    axis, stroke = (hy[1] + hy[3]) / 2, hy[3] - hy[1]
    gt = M.record(gs, cmap[ord(">")])

    def make_head(kx, ky):
        """The > scaled by kx, ky with its stroke given back, tip at (0, 0)."""
        h = M.transformed(gt, kx, 0.0, ky, 0.0)
        h = weight(h, stroke * (1 - kx), stroke * (1 - ky))
        b = M.bounds(h)
        return M.transformed(h, 1.0, -b[2], 1.0, -(b[1] + b[3]) / 2)

    single, double = make_head(0.5, 0.52), make_head(0.36, 0.46)

    def bar(x0, x1):
        """The hyphen lengthened in the middle, its ends keeping their shape, on y = 0."""
        mid = (hy[0] + hy[2]) / 2
        return [(op, tuple(None if pt is None else
                           (pt[0] + (x0 - hy[0] if pt[0] < mid else x1 - hy[2]), pt[1] - axis)
                           for pt in args)) for op, args in hy_ops]

    def shaft_end(head):
        xs = M.crossings(head, 0.0)
        return (xs[-1] + xs[-2]) / 2 if len(xs) >= 2 else M.bounds(head)[0] + stroke

    def right(length, both=False):
        """An arrow pointing right from x = 0 to x = length on y = 0."""
        head = M.transformed(double if both else single, 1.0, length)
        end = shaft_end(head)
        if not both:
            return head + bar(0.0, end)
        tail = flip_h(head, (0.0, 0, length, 0))
        start = length - end
        return head + tail + bar(start, end)

    margin = 30
    h_len = M.CELL - 2 * margin
    # the upright ones run as tall as the capitals, centred on them
    cap = M.bounds(M.record(gs, cmap[ord("H")])) if ord("H") in cmap else (0, 0, 0, 700)
    v_len = cap[3] - cap[1]
    vy = (cap[1] + cap[3]) / 2
    cx = M.CELL / 2
    for cp, length, both, turns in ((0x2192, h_len, False, 0), (0x2190, h_len, False, 2),
                                    (0x2194, h_len, True, 0), (0x2191, v_len, False, 1),
                                    (0x2193, v_len, False, 3), (0x2195, v_len, True, 1)):
        ops = M.transformed(right(length, both), 1.0, -length / 2)       # centred on (0, 0)
        ops = rotated(ops, turns, 0.0, 0.0)
        made[cp] = M.transformed(ops, 1.0, cx, 1.0, vy if turns % 2 else axis)

    # ↖ ↗ ↘ ↙: the same arrow turned by 45°, as long as fits the cell's width
    def turned(ops, degrees):
        a = math.radians(degrees)
        c, s = math.cos(a), math.sin(a)
        return [(op, tuple(None if pt is None else (pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c)
                           for pt in args)) for op, args in ops]

    # ↗ is drawn, the other three are its mirror images, so all four are the same size
    length = h_len * 1.3
    for _ in range(3):
        b = M.bounds(turned(M.transformed(right(length), 1.0, -length / 2), 45))
        length *= h_len / (b[2] - b[0])
    ne = turned(M.transformed(right(length), 1.0, -length / 2), 45)
    b = M.bounds(ne)
    ne = M.transformed(ne, 1.0, cx - (b[0] + b[2]) / 2, 1.0, vy - (b[1] + b[3]) / 2)
    b = M.bounds(ne)
    made[0x2197] = ne                                             # ↗
    made[0x2196] = flip_h(ne, b)                                  # ↖
    made[0x2198] = flip_v(ne, b)                                  # ↘
    made[0x2199] = flip_h(flip_v(ne, b), b)                       # ↙


def fractions(gs, cmap, weight, made):
    """¼ ½ ¾ ⅓ ... set as a stacked fraction in one cell: the numerator over a bar on the
    hyphen's height, the denominator under it."""
    if ord("-") not in cmap:
        return
    hy_ops = M.record(gs, cmap[ord("-")])
    hy = M.bounds(hy_ops)
    axis, stroke = (hy[1] + hy[3]) / 2, hy[3] - hy[1]
    rule = stroke * 0.8
    gap = stroke * 0.7
    digit_h = M.bounds(M.record(gs, cmap[ord("0")]))
    k = 330 / (digit_h[3] - digit_h[1])
    margin = 40

    def number(text, cy):
        glyphs = [M.record(gs, cmap[ord(ch)]) for ch in text]
        bs = [M.bounds(g) for g in glyphs]
        widths = [k * (b[2] - b[0]) for b in bs]
        between = 14
        total = sum(widths) + between * (len(glyphs) - 1)
        kx = min(1.0, (M.CELL - 2 * margin) / total)
        left = M.CELL / 2 - kx * total / 2
        out = []
        for g, b, w in zip(glyphs, bs, widths):
            one = M.transformed(g, k * kx, left - k * kx * b[0], k, cy - k * (digit_h[1] + digit_h[3]) / 2)
            # small digits keep half the weight they lose, so they stay light but readable
            out += weight(one, 68 * (1 - k * kx) * 0.5, 68 * (1 - k) * 0.5)
            left += kx * (w + between)
        return out

    half = 330 / 2
    top_cy = axis + rule / 2 + gap + half
    bottom_cy = axis - rule / 2 - gap - half
    bar = M.rect(margin, axis - rule / 2, M.CELL - margin, axis + rule / 2)
    for cp in list(range(0xBC, 0xBF)) + list(range(0x2150, 0x215F)) + [0x2189]:
        parts = unicodedata.decomposition(chr(cp)).split()
        if not parts or parts[0] != "<fraction>":
            continue
        chars = [chr(int(p, 16)) for p in parts[1:]]
        if "⁄" not in chars:
            continue
        cut = chars.index("⁄")
        num, den = "".join(chars[:cut]), "".join(chars[cut + 1:])
        if not all(ord(ch) in cmap for ch in num + den):
            continue
        made[cp] = number(num, top_cy) + bar + number(den, bottom_cy)


def below(ops, y):
    """The part of an outline under the height y, holes kept as holes."""
    import pathops
    shape, box = pathops.Path(), pathops.Path()
    pen = shape.getPen()
    for op, args in ops:
        getattr(pen, op)(*args)
    bp = box.getPen()
    bp.moveTo((-5000, -5000)); bp.lineTo((-5000, y)); bp.lineTo((5000, y)); bp.lineTo((5000, -5000)); bp.closePath()
    out = pathops.op(shape, box, pathops.PathOp.INTERSECTION)
    from fontTools.pens.recordingPen import RecordingPen
    rec = RecordingPen()
    out.draw(rec)
    ops2 = rec.value
    # skia turns outer contours its own way: turn them all to the font's if needed
    cs = M.polygon_points_ops(ops2)
    if cs:
        outer = max(cs, key=lambda q: abs(M.signed_area(M.polygon_points(q)[0])))
        if (M.signed_area(M.polygon_points(outer)[0]) < 0) != M.CLOCKWISE:
            from fontTools.pens.reverseContourPen import ReverseContourPen
            r2 = RecordingPen()
            rev = ReverseContourPen(r2)
            for op, args in ops2:
                getattr(rev, op)(*args)
            ops2 = r2.value
    return ops2


def partial(six):
    """∂: the 6 turned around, its stem cut short and ended in a round hook that curls
    back over the bowl, as a ∂ does."""
    b = M.bounds(six)
    turned = flip_h(six, b)
    height = b[3] - b[1]
    cut = b[1] + height * 0.66
    # the stem's middle and width where it is cut
    xs = M.crossings(turned, cut)
    if len(xs) < 2:
        return turned
    inner, outer = xs[-2], xs[-1]
    width = outer - inner
    mid = (inner + outer) / 2
    body = below(turned, cut)
    # the hook: an arc from the top of the stem over to the left, ending a little lower
    r = (b[3] - width / 2 - cut) * 0.95
    cx, cy = mid - r, cut
    steps = 20
    end = math.radians(165)
    outer_arc = [(cx + (r + width / 2) * math.cos(end * i / steps), cy + (r + width / 2) * math.sin(end * i / steps))
                 for i in range(steps + 1)]
    inner_arc = [(cx + (r - width / 2) * math.cos(end * i / steps), cy + (r - width / 2) * math.sin(end * i / steps))
                 for i in range(steps + 1)]
    band = outer_arc + inner_arc[::-1]
    # below the cut the band runs straight down a little, so it joins the stem
    band = [(mid + width / 2, cut - width * 1.2)] + band + [(mid - width * 0.75, cut - width * 1.2)]
    if (M.signed_area(band) < 0) != M.CLOCKWISE:
        band = band[::-1]
    hook = [("moveTo", (band[0],))] + [("lineTo", (q,)) for q in band[1:]] + [("closePath", ())]
    tip = (cx + r * math.cos(end), cy + r * math.sin(end))
    return body + hook + M.circle(tip, width / 2)


def math_operators(gs, cmap, weight, made):
    """The math operators the font draws wide, redrawn in one cell from the font's own
    letters and the parts of the ligatures: ∪ ∩ ⊂ ⊃ ∈ from U, ≤ ≥ ≪ ≫ from < and > over
    the bars of =, ≠ ≡ from = and /, ∀ ∃ ⊥ from A E T turned over, ∏ from ㅠ, ∑ from M,
    ∇ from ㅿ."""
    need = "-=<>/U.AETV~:|6"
    if not all(ord(ch) in cmap for ch in need):
        return

    def rec(ch):
        return M.record(gs, cmap[ord(ch)])

    hy = M.bounds(rec("-"))
    axis, stroke = (hy[1] + hy[3]) / 2, hy[3] - hy[1]
    eq_ops = rec("=")
    eq_bars = sorted(M.polygon_points_ops(eq_ops), key=lambda q: M.bounds(q)[1])
    eqb = M.bounds(eq_ops)
    bar_h = M.bounds(eq_bars[0])[3] - M.bounds(eq_bars[0])[1]
    bar_gap = M.bounds(eq_bars[1])[1] - M.bounds(eq_bars[0])[3]
    cx = M.CELL / 2
    cap = M.bounds(rec("H")) if ord("H") in cmap else (0, 0, 0, 650)
    side = 420                     # the width an operator fills

    def at(ops, x, y):
        """Moved so its outline is centred on (x, y)."""
        b = M.bounds(ops)
        return M.transformed(ops, 1.0, x - (b[0] + b[2]) / 2, 1.0, y - (b[1] + b[3]) / 2)

    def fit(ops, w=None, h=None, x=cx, y=axis):
        """Scaled to width w and/or height h (one of them keeps the proportions), the
        stroke given back to the font's weight, centred on (x, y)."""
        b = M.bounds(ops)
        kx = w / (b[2] - b[0]) if w else None
        ky = h / (b[3] - b[1]) if h else None
        kx, ky = kx or ky, ky or kx
        out = M.transformed(ops, kx, 0.0, ky, 0.0)
        out = weight(out, stroke * (1 - kx), stroke * (1 - ky))
        return at(out, x, y)

    def bar(x0, x1, y):
        return M.rect(x0, y - bar_h / 2, x1, y + bar_h / 2)

    us_ops = rec("_")
    us = M.bounds(us_ops)
    us_h = us[3] - us[1]

    def under(x0, x1, y):
        """The font's _ made as long as x0..x1, its ends keeping their shape, centred on y."""
        mid = (us[0] + us[2]) / 2
        dy = y - (us[1] + us[3]) / 2
        return [(op, tuple(None if pt is None else
                           (pt[0] + (x0 - us[0] if pt[0] < mid else x1 - us[2]), pt[1] + dy)
                           for pt in args)) for op, args in us_ops]

    def dot(x, y):
        return at(rec("."), x, y)

    U = rec("U")
    cup = fit(U, w=side * 0.92, h=side)
    made[0x222A] = cup                                            # ∪
    made[0x2229] = flip_v(cup, M.bounds(cup))                     # ∩
    sub = fit(rotated(U, 3, 0.0, 0.0), w=side * 0.9, h=side * 0.92)   # opening to the right
    made[0x2282] = sub                                            # ⊂
    made[0x2283] = flip_h(sub, M.bounds(sub))                     # ⊃
    low = axis - side * 0.5 - bar_gap * 0.5
    sub_up = M.transformed(sub, 1.0, 0.0, 1.0, bar_gap * 0.5 + bar_h * 0.5 + side * 0.05)
    sb = M.bounds(sub_up)
    made[0x2286] = sub_up + under(sb[0], sb[2], sb[1] - bar_gap - us_h / 2)      # ⊆
    made[0x2287] = flip_h(made[0x2286], (sb[0], 0, sb[2], 0))                    # ⊇
    small = fit(rotated(U, 3, 0.0, 0.0), w=side * 0.82, h=side * 0.82)
    smb = M.bounds(small)
    made[0x2208] = small + bar(smb[0] + stroke * 0.5, smb[2], axis)              # ∈
    made[0x220B] = flip_h(made[0x2208], (smb[0], 0, smb[2], 0))                  # ∋

    V = rec("V")
    vee = fit(V, w=side * 0.92, h=side)
    made[0x2228] = vee                                            # ∨
    made[0x2227] = flip_v(vee, M.bounds(vee))                     # ∧

    # ≤ ≥ : < and > made shorter, over one bar of =
    lt = rec("<")
    rel_h = side * 0.72
    rel_y = axis + (bar_gap + bar_h) / 2
    lt_s = fit(lt, w=side * 0.86, h=rel_h, y=rel_y + bar_h * 0.2)
    lb = M.bounds(lt_s)
    made[0x2264] = lt_s + under(lb[0], lb[2], lb[1] - bar_gap * 0.9 - us_h / 2)  # ≤
    made[0x2265] = flip_h(made[0x2264], (lb[0], 0, lb[2], 0))                  # ≥
    # ≪ ≫ : two chevrons, nested as in the >>= ligature
    one = fit(lt, w=side * 0.62, h=side * 0.9)
    ob = M.bounds(one)
    step = stroke * 2.4
    pair = M.transformed(one, 1.0, -step / 2) + M.transformed(one, 1.0, step / 2)
    made[0x226A] = at(pair, cx, axis)                             # ≪
    made[0x226B] = flip_h(made[0x226A], M.bounds(made[0x226A]))   # ≫

    # ≡ ≠ ≒ : the bars of =
    eq = at(eq_ops, cx, axis)
    one_bar = eq_bars[0]
    b0 = M.bounds(one_bar)
    three = []
    for i in (-1, 0, 1):
        three += at(one_bar, cx, axis + i * (bar_h + bar_gap))
    made[0x2261] = three                                          # ≡
    slash = fit(rec("/"), h=(eqb[3] - eqb[1]) * 2.3, x=cx, y=axis)
    made[0x2260] = eq + slash                                     # ≠
    eb = M.bounds(eq)
    dy = (eb[3] - eb[1]) / 2 + bar_gap * 1.1
    made[0x2252] = eq + dot(eb[0] + 40, axis + dy) + dot(eb[2] - 40, axis - dy)  # ≒

    # ∼ ∽ ∶ ∴ ∵ ⋯ ∥
    tilde = at(rec("~"), cx, axis)
    made[0x223C] = tilde                                          # ∼
    made[0x223D] = flip_h(tilde, M.bounds(tilde))                 # ∽
    made[0x2236] = at(rec(":"), cx, axis)                         # ∶
    r = side * 0.3
    made[0x2234] = dot(cx, axis + r * 0.9) + dot(cx - r, axis - r * 0.7) + dot(cx + r, axis - r * 0.7)   # ∴
    made[0x2235] = dot(cx, axis - r * 0.9) + dot(cx - r, axis + r * 0.7) + dot(cx + r, axis + r * 0.7)   # ∵
    made[0x22EF] = dot(cx - 150, axis) + dot(cx, axis) + dot(cx + 150, axis)   # ⋯
    pipe = rec("|")
    made[0x2225] = at(pipe, cx - 70, axis) + at(pipe, cx + 70, axis)            # ∥

    # ∀ ∃ ⊥ ∂ : letters turned over
    A = rec("A")
    # √: in a box of half an em, from the baseline up, through (0, 0.35), (0.5, 0) and
    # (1, 1.5) of that box (the long right arm keeps it from reading as a check mark),
    # drawn with the round pen and kept inside the cell
    s = stroke
    em2 = M.CELL

    def in_box(u, v):
        return (s / 2 + u * (em2 - s), s / 2 + v * (em2 - s))

    made[0x221A] = (round_line(in_box(0, 0.35), in_box(0.5, 0), s)
                    + round_line(in_box(0.5, 0), in_box(1, 1.5), s))              # √

    # ∀: two legs meeting at the foot and a bar, drawn with the font's round pen so no
    # end of the A's crossbar is left sticking out
    ab = M.bounds(A)
    s = stroke
    tl, tr = (ab[0] + s / 2, ab[3] - s / 2), (ab[2] - s / 2, ab[3] - s / 2)
    foot = ((ab[0] + ab[2]) / 2, ab[1] + s / 2)
    by = ab[1] + (ab[3] - ab[1]) * 0.58

    def on_leg(top, y):
        k = (y - foot[1]) / (top[1] - foot[1])
        return (foot[0] + (top[0] - foot[0]) * k, y)

    made[0x2200] = (round_line(tl, foot, s) + round_line(tr, foot, s)
                    + round_line(on_leg(tl, by), on_leg(tr, by), s))           # ∀
    E = rec("E")
    made[0x2203] = flip_h(E, M.bounds(E))                         # ∃
    T = rec("T")
    made[0x22A5] = flip_v(T, M.bounds(T))                         # ⊥
    made[0x2202] = partial(rec("6"))                              # ∂

    # ∏ from ㅠ, ∑ from M turned a quarter: its stems become the two bars, its V the point
    cap_h, cap_y = cap[3] - cap[1], (cap[1] + cap[3]) / 2
    if 0x3160 in cmap:
        made[0x220F] = fit(M.record(gs, cmap[0x3160]), w=side, h=cap_h, y=cap_y)          # ∏
    if ord("M") in cmap:
        made[0x2211] = fit(rotated(rec("M"), 1, 0.0, 0.0), w=side, h=cap_h, y=cap_y)      # ∑

    # ∇ ∆ after ㅿ: a triangle as tall as the capitals, turned over for ∇
    if 0x317F in cmap:
        # the size of ㅿ's triangle, redrawn with the round pen: its strokes cross at the
        # top, and those ends would show
        s = stroke
        x0, x1 = cx - side / 2 + s / 2, cx + side / 2 - s / 2
        y0, y1 = cap[1] + s / 2, cap[3] - s / 2
        top, left, right = (cx, y1), (x0, y0), (x1, y0)
        made[0x2206] = round_line(left, top, s) + round_line(top, right, s) + round_line(right, left, s)   # ∆
        made[0x2207] = (round_line((x0, y1), (cx, y0), s) + round_line((cx, y0), (x1, y1), s)
                        + round_line((x1, y1), (x0, y1), s))                                              # ∇


UNIT_PARTS = {0x2215: "/"}


def units(gs, cmap, weight, made):
    """㎜ ㎏ ㎡ ...: the letters of the unit, set side by side in two cells. Units
    of three letters or more are narrowed to fit, and a little shorter. A unit with a
    slash (㎧ m/s, ㎯ rad/s², ㏆ C/kg) is set as a fraction: what is over the slash
    above a bar, what is under it below."""
    if ord("-") not in cmap:
        return
    hy = M.bounds(M.record(gs, cmap[ord("-")]))
    stroke = hy[3] - hy[1]
    axis = (hy[1] + hy[3]) / 2
    avail = 2 * M.CELL - 2 * 34

    def gaps_of(chars):
        # the period of a.m. and the superscripts sit close to what they follow
        return [10 if ch == "." or nxt in "²³." else 40 for ch, nxt in zip(chars, chars[1:])]

    def line(chars, kx, ky, baseline):
        """The letters side by side, scaled by kx and ky, centred across the two cells."""
        glyphs = [M.record(gs, cmap[ord(ch)]) for ch in chars]
        bs = [M.bounds(g) for g in glyphs]
        gaps = gaps_of(chars)
        width = sum(b[2] - b[0] for b in bs) + sum(gaps)
        out, x = [], M.CELL - kx * width / 2
        for g, b, gap in zip(glyphs, bs, gaps + [0]):
            one = M.transformed(g, kx, x - kx * b[0], ky, baseline)
            if kx < 0.99 or ky < 0.99:
                one = weight(one, stroke * (1 - kx) * 0.7, stroke * (1 - ky) * 0.7)
            out += one
            x += kx * (b[2] - b[0] + gap)
        return out, kx * width

    def natural_width(chars):
        bs = [M.bounds(M.record(gs, cmap[ord(ch)])) for ch in chars]
        return sum(b[2] - b[0] for b in bs) + sum(gaps_of(chars))

    cap = M.bounds(M.record(gs, cmap[ord("H")])) if ord("H") in cmap else (0, 0, 0, 650)
    for cp in range(0x3380, 0x33E0):
        if cp not in cmap:
            continue
        parts = unicodedata.decomposition(chr(cp)).split()
        if not parts or parts[0] != "<square>":
            continue
        chars = [UNIT_PARTS.get(int(p, 16), chr(int(p, 16))) for p in parts[1:]]
        if not all(ord(ch) in cmap for ch in chars):
            continue
        if any(M.bounds(M.record(gs, cmap[ord(ch)])) is None for ch in chars if ch != " "):
            continue
        if "/" in chars:
            cut = chars.index("/")
            num, den = chars[:cut], chars[cut + 1:]
            # each line about half the capital height, narrowed further if it is long
            k = 0.5
            rule, gap = stroke * 0.8, stroke * 0.8
            kx = min(k, avail / max(natural_width(num), natural_width(den)))
            top_base = axis + rule / 2 + gap                              # numerator baseline
            bottom_base = axis - rule / 2 - gap - k * cap[3]              # denominator top at the gap
            n_ops, nw = line(num, kx, k, top_base)
            d_ops, dw = line(den, kx, k, bottom_base)
            half = max(nw, dw) / 2 + 30
            bar = M.rect(M.CELL - half, axis - rule / 2, M.CELL + half, axis + rule / 2)
            made[cp] = n_ops + bar + d_ops
            continue
        width = natural_width(chars)
        kx = min(1.0, avail / width)
        ky = min(1.0, kx * 1.3)
        made[cp], _ = line(chars, kx, ky, 0.0)


KANA_SCALE = 0.92


def kana_extras(gs, cmap, made, weight):
    """ー from the lower stroke of ニ, ゛ and ゜ from the marks of ガ and パ.
    The marks stand at the top left of their two cells, next to the kana before them.
    Then every kana is drawn at 92%: at full size the kana look larger than the Hangul
    beside them, which leaves more room between its strokes."""
    def contours(ch):
        return M.polygon_points_ops(M.record(gs, cmap[ord(ch)]))

    def flat(cs):
        return [op for q in cs for op in q]

    def box(ch):
        return M.bounds(M.record(gs, cmap[ord(ch)]))

    if 0x30FC not in cmap and ord("ニ") in cmap and ord("カ") in cmap:
        lower = min(contours("ニ"), key=lambda q: M.bounds(q)[1])
        b, kb = M.bounds(lower), box("カ")
        # centred on the height of the katakana
        made[0x30FC] = M.transformed(lower, 1.0, 0.0, 1.0, (kb[1] + kb[3]) / 2 - (b[1] + b[3]) / 2)

    def mark(ch, plain):
        """The small contours ch has in the upper right, where plain has nothing."""
        pb = box(plain)
        return [q for q in contours(ch) if M.bounds(q)[1] > (pb[1] + pb[3]) / 2
                and M.bounds(q)[0] > (pb[0] + pb[2]) / 2 and M.bounds(q)[2] - M.bounds(q)[0] < 250]

    for cp, ch, plain in ((0x309B, "ガ", "ハ"), (0x309C, "パ", "ハ")):
        if cp in cmap or ord(ch) not in cmap:
            continue
        cs = mark(ch, plain)
        if not cs:
            continue
        ops = flat(cs)
        b = M.bounds(ops)
        made[cp] = M.transformed(ops, 1.0, 120 - b[0])

    if ord("カ") not in cmap:
        return
    kb = box("カ")
    cx, cy, k = M.CELL, (kb[1] + kb[3]) / 2, KANA_SCALE
    # the stroke shrinks with the glyph: bring it back to the weight of the Hangul
    grow = 80 * (1 - k)
    kana = list(range(0x3041, 0x3097)) + list(range(0x30A1, 0x30FB)) + [0x309B, 0x309C, 0x30FC]
    for cp in kana:
        ops = made.get(cp) or (M.record(gs, cmap[cp]) if cp in cmap else None)
        if not ops:
            continue
        small = M.transformed(ops, k, cx * (1 - k), k, cy * (1 - k))
        made[cp] = M.transformed(weight(small, grow, grow), 1.0, -grow / 2, 1.0, -grow / 2)


# ---------------------------------------------------------------- round kana

KANA_RANGES = [(0x3041, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF), (0xFF66, 0xFF9F)]
# The kana come with square stroke ends and sharp turns, drawn like a gothic. Every sharp
# corner of their outlines becomes a curve: an outer corner with KANA_ROUND_OUT, an inner
# one with KANA_ROUND_IN. The outer radius is the inner one plus about a stroke, so the
# stroke keeps its width through a turn. A stroke end, two outer corners close together,
# turns into a full round end like the Hangul strokes.
KANA_ROUND_IN = 50
KANA_ROUND_OUT = 170
KANA_THIN = 10          # the kana strokes are this much thicker than the Hangul ones
KANA_SHARP = math.radians(35)


def _polygons(ops):
    out, cur = [], []
    for op, args in M.flattened(ops, 10):
        if op == "moveTo":
            cur = [args[0]]
        elif op == "lineTo":
            if math.dist(cur[-1], args[0]) > 0.5:     # a repeated point would make an edge of no direction
                cur.append(args[0])
        elif op in ("closePath", "endPath"):
            if cur and math.dist(cur[0], cur[-1]) <= 0.5:
                cur = cur[:-1]
            if len(cur) > 2:
                out.append(cur)
            cur = []
    return out


def _point_at(p, cum, s):
    """The point at arc length s along the closed polyline p (cum: running lengths)."""
    total = cum[-1]
    s %= total
    for i in range(len(p)):
        if cum[i] <= s <= cum[i + 1]:
            a, b = p[i], p[(i + 1) % len(p)]
            t = (s - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return p[-1]


def _area(p):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(p, p[1:] + p[:1])) / 2


def round_corners(p, r_in, r_out, ccw):
    """The closed polyline p with each sharp corner replaced by a curve: a quadratic from
    a point `cut` before the corner to one `cut` after it, the corner its control point.
    Neighbouring corners take at most half the way to each other. `ccw` is the direction
    of the glyph's outer contours: a corner the outline turns that way round is an outer
    corner of the ink, in a hole as well as on the outside."""
    n = len(p)
    cum = [0.0]
    for a, b in zip(p, p[1:] + p[:1]):
        cum.append(cum[-1] + math.dist(a, b))
    total = cum[-1]
    corners = []
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        turn = (math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi) \
            % (2 * math.pi) - math.pi
        if abs(turn) < KANA_SHARP:
            continue
        r = r_out if (turn > 0) == ccw else r_in
        corners.append([i, r * math.tan(min(abs(turn), math.radians(120)) / 2)])
    if not corners:
        return p
    for k, (i, cut) in enumerate(corners):
        if len(corners) == 1:
            back = fwd = total
        else:
            back = (cum[i] - cum[corners[k - 1][0]]) % total
            fwd = (cum[corners[(k + 1) % len(corners)][0]] - cum[i]) % total
        corners[k][1] = min(cut, back * 0.48, fwd * 0.48)
    # Each corner's curve runs over the arc lengths [cum[i] - cut, cum[i] + cut]. The walk
    # starts halfway between the last curve and the first one, so no curve wraps past it.
    spans = [(cum[i] - cut, cum[i] + cut, i) for i, cut in corners]
    start = (spans[-1][1] + spans[0][0] + total) / 2 if len(spans) > 1 else spans[0][1] + 1e-6
    rel = lambda s: (s - start) % total
    spans.sort(key=lambda sp: rel(sp[0]))
    order = sorted(range(n), key=lambda j: rel(cum[j]))
    out, k = [], 0
    for j in order:
        s = rel(cum[j])
        while k < len(spans) and rel(spans[k][0]) <= s:
            s0, s1, i = spans[k]
            p0, p2, ctrl = _point_at(p, cum, s0), _point_at(p, cum, s1), p[i]
            for m in range(9):
                t_ = m / 8
                out.append(((1 - t_) ** 2 * p0[0] + 2 * (1 - t_) * t_ * ctrl[0] + t_ * t_ * p2[0],
                            (1 - t_) ** 2 * p0[1] + 2 * (1 - t_) * t_ * ctrl[1] + t_ * t_ * p2[1]))
            k += 1
        inside = any(rel(s0) <= s <= rel(s0) + (s1 - s0) for s0, s1, _ in spans)
        if not inside:
            out.append(p[j])
    while k < len(spans):
        s0, s1, i = spans[k]
        p0, p2, ctrl = _point_at(p, cum, s0), _point_at(p, cum, s1), p[i]
        out += [((1 - m / 8) ** 2 * p0[0] + 2 * (1 - m / 8) * (m / 8) * ctrl[0] + (m / 8) ** 2 * p2[0],
                 (1 - m / 8) ** 2 * p0[1] + 2 * (1 - m / 8) * (m / 8) * ctrl[1] + (m / 8) ** 2 * p2[1]) for m in range(9)]
        k += 1
    return out


def round_kana(font, to_glyph, weight):
    """Every kana drawn with round turns and ends, at the weight of the Hangul strokes.
    Returns the glyph names it rewrote."""
    gs = font.getGlyphSet()
    glyf = font["glyf"]
    done = []
    for cp, name in font.getBestCmap().items():
        if not any(a <= cp <= b for a, b in KANA_RANGES) or name in done:
            continue
        ops = M.record(gs, name)
        if not M.bounds(ops):
            continue
        ops = weight(ops, -KANA_THIN, -KANA_THIN)
        polys = _polygons(ops)
        ccw = _area(max(polys, key=lambda q: abs(_area(q)))) > 0
        polys = [round_corners(q, KANA_ROUND_IN, KANA_ROUND_OUT, ccw) for q in polys]
        drawn = []
        for q in polys:
            drawn.append(("moveTo", (q[0],)))
            drawn += [("lineTo", (pt,)) for pt in q[1:]]
            drawn.append(("closePath", ()))
        glyf[name] = to_glyph(drawn)
        done.append(name)
    return done


# ---------------------------------------------------------------- driver

FROM_FONT = [0x2022, 0x2713, 0x2714, 0x2717, 0x2718, 0x2039, 0x203A, 0x201E, 0x201A, 0x203C,
             0xB5, 0xA6, 0xAF, 0x23FA, 0x23BF, 0xFFFD, 0x2070] + list(range(0x2074, 0x207A)) + \
            list(range(0x2080, 0x208A))
POWERLINE = [0xE0A0, 0xE0A1, 0xE0A2, 0xE0B0, 0xE0B1, 0xE0B2, 0xE0B3]


def pen_stroke(start, segments, width):
    """The outline of a round pen drawn along a path: start, then ("line", p) or
    ("curve", c1, c2, p) segments. skia strokes the curves themselves, so the outline
    is made of curves too, with round ends and round turns."""
    import pathops
    from fontTools.pens.recordingPen import RecordingPen
    centre = pathops.Path()
    pen = centre.getPen()
    pen.moveTo(start)
    for seg in segments:
        if seg[0] == "line":
            pen.lineTo(seg[1])
        else:
            pen.curveTo(seg[1], seg[2], seg[3])
    pen.endPath()
    centre.stroke(width, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    centre.convertConicsToQuads()
    centre.simplify()
    rec = RecordingPen()
    centre.draw(rec)
    out = rec.value
    cs = M.polygon_points_ops(out)
    outer = max(cs, key=lambda q: abs(M.signed_area(M.polygon_points(q)[0])))
    if (M.signed_area(M.polygon_points(outer)[0]) < 0) != M.CLOCKWISE:
        from fontTools.pens.reverseContourPen import ReverseContourPen
        r = RecordingPen()
        rev = ReverseContourPen(r)
        for op, args in out:
            getattr(rev, op)(*args)
        out = r.value
    return out


def l_halves(top_y, s, inset=0):
    """ℓ split at its highest point into two strokes. The / half runs from the bottom
    left, through a crossing near the foot, up the right of the loop to the top. The
    \\ half is its mirror image, from the top down the left of the loop, through the
    crossing and out to the bottom right. Returns (bottom left, top, / segments,
    \\ segments), each segment list for pen_stroke."""
    w = M.CELL
    start, end = (s / 2 + inset, s / 2), (w - s / 2 - inset, s / 2)
    cross = (w / 2, 165)
    top = (w / 2, top_y)
    slash = [("curve", (w * 0.2, 75), (w * 0.4, 130), cross),
             ("curve", (w * 0.66, 215), (w * 0.7, top_y), top)]
    backslash = [("curve", (w * 0.3, top_y), (w * 0.34, 215), cross),
                 ("curve", (w * 0.6, 130), (w * 0.8, 75), end)]
    return start, top, slash, backslash


def l_stroke_width(gs, cmap):
    old = M.record(gs, cmap[ord("l")])
    lb = M.bounds(old)
    xs = M.crossings(M.flattened(old), (lb[1] + lb[3]) * 0.6)
    return (xs[1] - xs[0] if len(xs) >= 2 else 70), lb[3]


def regular_l(gs, cmap):
    """l as one stroke of the round pen: straight down a little left of the middle, then
    a short tail that curves down and to the right onto the baseline."""
    s, top_y = l_stroke_width(gs, cmap)
    x = M.CELL * 0.42
    foot = s / 2

    def up(y):
        # the tail's drop, 5% steeper than an even curve from the stem
        return foot + (y - foot) * 1.05

    return pen_stroke((x, top_y - s / 2), [
        ("line", (x, up(190))),
        ("curve", (x, up(110)), (x + 40, up(60)), (x + 170, foot)),
    ], s)


def diamond_dot(cx, cy, hw=88 * 0.95, hh=96 * 0.95, soft=26 * 0.95):
    """The dot of i and j: a diamond with its corners rounded by the round pen."""
    import pathops
    from fontTools.pens.recordingPen import RecordingPen
    pts = [(cx, cy + hh), (cx + hw, cy), (cx, cy - hh), (cx - hw, cy)]
    inner = [(cx + (x - cx) * (1 - soft / hw), cy + (y - cy) * (1 - soft / hh)) for x, y in pts]
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(inner[0])
    for q in inner[1:]:
        pen.lineTo(q)
    pen.closePath()
    edge = pathops.Path()
    edge.addPath(path)
    edge.stroke(2 * soft, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    edge.convertConicsToQuads()
    out = pathops.op(path, edge, pathops.PathOp.UNION)
    rec = RecordingPen()
    out.draw(rec)
    ops = rec.value
    if (M.signed_area(M.polygon_points(ops)[0]) < 0) != M.CLOCKWISE:
        from fontTools.pens.reverseContourPen import ReverseContourPen
        r = RecordingPen()
        rev = ReverseContourPen(r)
        for op, args in ops:
            getattr(rev, op)(*args)
        ops = r.value
    return ops


def regular_i(gs, cmap, dotless=False):
    """i as a plain stem of the round pen down to the baseline, with a diamond for its
    dot, raised clear of it. The diamond fills the cell a plain stem leaves empty, and
    tells i from l, 1 and | at small sizes. The stem starts where j's stem starts, so the
    two match and i does not run up to meet its dot. ı (dotless) starts at the x-height
    like the other short letters."""
    s, _ = l_stroke_width(gs, cmap)
    top = M.bounds(M.record(gs, cmap[ord("x")]))[3]
    if not dotless and ord("j") in cmap:
        cs = M.polygon_points_ops(M.record(gs, cmap[ord("j")]))
        dot = max(cs, key=lambda q: M.bounds(q)[1])
        top = M.bounds([op for q in cs if q is not dot for op in q])[3]
    x = M.CELL / 2
    body = round_line((x, top - s / 2), (x, s / 2), s)
    return body if dotless else body + diamond_dot(x, dot_height(gs, cmap))


def dot_height(gs, cmap):
    """The height of the middle of the diamond on i and on j, the same for both: the
    font's own i dot raised clear of the stem."""
    cs = M.polygon_points_ops(M.record(gs, cmap[ord("i")]))
    db = M.bounds(max(cs, key=lambda q: M.bounds(q)[1]))
    return (db[1] + db[3]) / 2 + 80


def j_with_diamond(gs, cmap):
    """j with the same diamond as i for its dot, at the same height, over its own stem
    where the round dot was."""
    cs = M.polygon_points_ops(M.record(gs, cmap[ord("j")]))
    dot = max(cs, key=lambda q: M.bounds(q)[1])
    db = M.bounds(dot)
    rest = [op for q in cs if q is not dot for op in q]
    return rest + diamond_dot((db[0] + db[2]) / 2, dot_height(gs, cmap))


def redraw_i_l(font, to_glyph):
    """The new l, i and j, written before anything is built from them (the accented
    letters, ı, the units lm and lx)."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    glyf = font["glyf"]
    if ord("l") in cmap and ord("i") in cmap and ord("x") in cmap:
        new_l = regular_l(gs, cmap)
        new_j = j_with_diamond(gs, cmap) if ord("j") in cmap else None
        new_i = regular_i(gs, cmap)
        glyf[cmap[ord("l")]] = to_glyph(new_l)
        glyf[cmap[ord("i")]] = to_glyph(new_i)
        if new_j:
            glyf[cmap[ord("j")]] = to_glyph(new_j)
        if 0x131 in cmap:
            glyf[cmap[0x131]] = to_glyph(regular_i(gs, cmap, dotless=True))


def f_stems(gs, cmap):
    """f with the stem under its crossbar redrawn as one stroke of the round pen. The
    font's own stem bends right and back, which reads as a squiggle at small sizes.
    Returns two f: the stem ending in a short foot to the left (the mirror of t's foot),
    and the stem running straight down to a round end (ss05). The crossbar and the arch
    above it stay as they are."""
    import pathops
    from make_italic import path_op, box
    ops = M.record(gs, cmap[ord("f")])
    flat = M.flattened(ops)
    fb = M.bounds(flat)
    low = M.crossings(flat, fb[1] + 80)
    if len(low) < 2:
        raise SystemExit("f: no stem found near the baseline")
    stem_w = low[1] - low[0]
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
        raise SystemExit("f: no crossbar found")
    above = M.crossings(flat, bar_hi + 15)
    if len(above) < 2:
        raise SystemExit("f: no stem found above the crossbar")
    w = above[1] - above[0]
    cx = (above[0] + above[1]) / 2
    top = path_op(ops, box(-10000, -10000, 10000, bar_lo + 3), pathops.PathOp.DIFFERENCE)
    # the new stem starts inside the bar, in line with the stem above it, so the joint
    # is hidden in the bar. It leans 0.5 degrees like the upright strokes of the Hangul.
    start, foot, x = (cx, (bar_lo + bar_hi) / 2), w / 2, cx - 4
    footed = pen_stroke(start, [
        ("line", (x, foot + 90)),
        ("curve", (x, foot + 30), (x - 26, foot), (x - 91, foot)),
    ], w)
    straight = pen_stroke(start, [("line", (x, foot))], w)
    return (path_op(top, footed, pathops.PathOp.UNION),
            path_op(top, straight, pathops.PathOp.UNION))


def open_tail(gs, cmap, ch, spans, cut, clear, bottom):
    """y or g with its right stem and the tail under the baseline redrawn as one stroke
    of the round pen. The font's own tail curls back to the right under the letter and
    closes into a loop, which fills in at small sizes and makes y and g look alike. The
    new stroke follows the old stem's lean from its top, keeps that direction into the
    turn, runs left along the bottom and lifts a little at its end, like the tail of j.
    spans: [(lo, hi), ...], heights where the stem stands alone (above and below where
    the bowl meets it), to measure its line and width over its whole length.
    cut: everything below this height goes. clear: (x, y), everything left of x and
    below y goes too (g's loop comes back up under its bowl). bottom: the lowest edge."""
    import statistics
    import pathops
    from make_italic import path_op, box
    ops = M.record(gs, cmap[ord(ch)])
    flat = M.flattened(ops)
    fb = M.bounds(flat)
    ys, xs, ws = [], [], []
    for y in (y for lo, hi in spans for y in range(lo, hi + 1, 10)):
        row = M.crossings(flat, y)
        if len(row) < 2:
            raise SystemExit(f"{ch}: no right stem at height {y}")
        ys.append(y)
        xs.append((row[-2] + row[-1]) / 2)
        ws.append(row[-1] - row[-2])
    w = statistics.median(ws)
    # the stem's centre line, x = a + b * y, fitted by least squares
    my, mx = statistics.fmean(ys), statistics.fmean(xs)
    b = sum((y - my) * (x - mx) for y, x in zip(ys, xs)) / sum((y - my) ** 2 for y in ys)
    a = mx - b * my

    def at(y):
        return a + b * y

    if clear and at(clear[1]) - w / 2 <= clear[0]:
        raise SystemExit(f"{ch}: the stem reaches into the area cleared for the tail")
    # the old stem goes from its centre line rightwards, the bowl's ends stop inside the new
    # stroke. The old tail goes below cut.
    right_of_stem = [("moveTo", ((at(-10000), -10000),)), ("lineTo", ((10000, -10000),)),
                     ("lineTo", ((10000, 10000),)), ("lineTo", ((at(10000), 10000),)), ("closePath", ())]
    top = path_op(ops, right_of_stem, pathops.PathOp.DIFFERENCE)
    top = path_op(top, box(-10000, -10000, 10000, cut), pathops.PathOp.DIFFERENCE)
    if clear:
        top = path_op(top, box(-10000, -10000, clear[0], clear[1]), pathops.PathOp.DIFFERENCE)
    low = bottom + w / 2
    head = fb[3] - w / 2
    knee = low + 150
    # the first handle of the turn carries on along the stem, so the stroke bends without a corner
    reach = 100
    tail = pen_stroke((at(head), head), [
        ("line", (at(knee), knee)),
        ("curve", (at(knee - reach), knee - reach), (at(low) - 50, low), (at(low) - 115, low)),
        ("curve", (at(low) - 165, low), (at(low) - 200, low + 28), (at(low) - 215, low + 66)),
    ], w)
    return path_op(top, tail, pathops.PathOp.UNION)


def redraw_y_g(font, to_glyph):
    """y and g with open tails. Written before the accented letters are built from them."""
    cmap = font.getBestCmap()
    gs = font.getGlyphSet()
    if ord("y") not in cmap or ord("g") not in cmap:
        raise SystemExit("the font has no y or no g")
    # both tails reach as deep as y's does now
    bottom = M.bounds(M.flattened(M.record(gs, cmap[ord("y")])))[1]
    # heights measured on the finished font, which is drawn M.TALL times taller later
    def h(y):
        return round(y / M.TALL)

    new_y = open_tail(gs, cmap, "y", [(h(0), h(160)), (h(280), h(440))], h(-10), None, bottom)
    new_g = open_tail(gs, cmap, "g", [(h(10), h(90)), (h(270), h(340))], h(-40), (355, h(60)), bottom)
    font["glyf"][cmap[ord("y")]] = to_glyph(new_y)
    font["glyf"][cmap[ord("g")]] = to_glyph(new_g)


def redraw_digits(font, to_glyph):
    """6, 9 and 8 told apart from b, g and B at small sizes. 6's stroke above its bowl
    bends right as it rises, so it no longer stands straight like b's stem. 9 is that 6
    turned half round. 8 is one closed stroke of the round pen crossing itself at a
    raised waist (a lemniscate of Gerono with its halves scaled apart), so its upper loop
    is smaller than its lower one, unlike B.
    Written before the stretch to the finished height: heights are given as measured
    on the finished font and divided by M.TALL here."""
    import pathops
    from make_italic import path_op, box
    from fontTools.pens.recordingPen import RecordingPen
    cmap = font.getBestCmap()
    for ch in "689":
        if ord(ch) not in cmap:
            raise SystemExit(f"the font has no {ch}")
    gs = font.getGlyphSet()
    glyf = font["glyf"]

    def h(y):
        return y / M.TALL

    six = M.record(gs, cmap[ord("6")])
    flat = M.flattened(six)
    row = M.crossings(flat, h(250))
    if len(row) != 4:
        raise SystemExit("6: its bowl is not where it was measured")
    w = row[1] - row[0]
    top = M.bounds(flat)[3] - h(w / 2)
    # the old stroke above the bowl goes, the bowl stays
    six = path_op(six, box(-10000, h(330), 140, 10000), pathops.PathOp.DIFFERENCE)
    six = path_op(six, box(-10000, h(420), 10000, 10000), pathops.PathOp.DIFFERENCE)
    rise = pen_stroke((88, h(280)), [("curve", (86, h(520)), (170, top), (335, top - h(6)))], w)
    six = path_op(six, rise, pathops.PathOp.UNION)
    sb = M.bounds(six)
    nine = M.transformed(six, -1.0, sb[0] + sb[2], -1.0, sb[1] + sb[3])

    eb = M.bounds(M.flattened(M.record(gs, cmap[ord("8")])))
    cx, waist = M.CELL / 2, h(395)
    hi, lo = eb[3] - h(w / 2), eb[1] + h(w / 2)
    upper_half, lower_half = 135, 170          # half widths of the loops, along the centre line
    # the centre line as 32 cubic curves through points on the curve (Catmull-Rom), so the
    # outline has few, long segments: a scaled-down copy (⁸, ⅛) keeps a clean outline
    n = 32
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        ct, st = math.cos(t), math.sin(t)
        up = ct >= 0
        y = waist + (hi - waist) * ct if up else waist + (waist - lo) * ct
        x = cx + (upper_half if up else lower_half) * 2 * st * ct
        pts.append((x, y))
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        pen.curveTo((p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6),
                    (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6), p2)
    pen.closePath()
    path.stroke(w, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    path.convertConicsToQuads()
    path.simplify()
    rec = RecordingPen()
    path.draw(rec)
    eight = path_op(rec.value, [], pathops.PathOp.UNION)

    glyf[cmap[ord("6")]] = to_glyph(six)
    glyf[cmap[ord("9")]] = to_glyph(nine)
    glyf[cmap[ord("8")]] = to_glyph(eight)


def redraw_f(font, to_glyph):
    """The new f, and the straight f as f.ss05. Written before anything is built from
    f (ſ, the italic f, the ss03 copies). Returns the name of the alternate."""
    cmap = font.getBestCmap()
    if ord("f") not in cmap:
        raise SystemExit("the font has no f")
    name = cmap[ord("f")]
    footed, straight = f_stems(font.getGlyphSet(), cmap)
    glyf, hmtx = font["glyf"], font["hmtx"]
    alt = f"{name}.ss05"
    glyf[name] = to_glyph(footed)
    glyf[alt] = to_glyph(straight)
    hmtx[alt] = hmtx[name]
    order = font.getGlyphOrder()
    if alt not in order:
        font.setGlyphOrder(order + [alt])
    glyf.glyphOrder = font.getGlyphOrder()
    M.ALTERNATES["ss05"] = [(name, alt)]
    return alt


def add_symbols(font, to_glyph, weight):
    """Adds or redraws the symbols. Returns the glyph names it wrote."""
    cell = Cell(font)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    glyf, hmtx = font["glyf"], font["hmtx"]
    made = {}
    # geometry: drawn even where the font has the code point, so all of it joins up
    for cp in range(0x2500, 0x2580):
        if unicodedata.name(chr(cp), ""):
            made[cp] = box_glyph(cp, cell)
    for cp in range(0x2580, 0x25A0):
        ops = block_glyph(cp, cell)
        if ops is not None:
            made[cp] = ops
    for cp in range(0x2800, 0x2900):
        made[cp] = braille_glyph(cp, cell)
    for cp in POWERLINE:
        made[cp] = powerline_glyph(cp, cell, gs, cmap)
    # from the font, only where it has nothing
    for cp in FROM_FONT:
        if cp not in cmap:
            ops = from_font(cp, cell, gs, cmap, weight)
            if ops:
                made[cp] = ops
    for cp in range(0x2400, 0x2427):
        if cp not in cmap:
            ops = control_picture(cp, cell, gs, cmap, weight)
            if ops:
                made[cp] = ops
    latin_ext_a(font, gs, cmap, cell, weight, made)
    korean_extras(font, gs, cmap, weight, made)
    arrows(gs, cmap, weight, made)
    fractions(gs, cmap, weight, made)
    math_operators(gs, cmap, weight, made)
    units(gs, cmap, weight, made)
    kana_extras(gs, cmap, made, weight)
    if 0x3C2 not in cmap and ord("c") in cmap:              # ς final sigma: c with a tail
        cb = M.bounds(M.record(gs, cmap[ord("c")]))
        made[0x3C2] = M.record(gs, cmap[ord("c")]) + round_line(
            ((cb[0] + cb[2]) / 2, cb[1] + 30), ((cb[0] + cb[2]) / 2 + 60, cb[1] - 160), 60)

    names = []
    order = font.getGlyphOrder()
    new_names = []
    shared = collections.Counter(cmap.values())
    for cp, ops in made.items():
        if not ops:
            continue
        name = cmap.get(cp) or f"uni{cp:04X}"
        if shared[name] > 1:
            # the glyph also draws another character (∶ and :): this one gets its own
            name = f"uni{cp:04X}"
        glyf[name] = to_glyph(ops)
        # two cells for what Unicode calls wide (㈝ ㈞), one for the rest
        wide = unicodedata.east_asian_width(chr(cp)) in "WF"
        hmtx[name] = (2 * M.CELL if wide else M.CELL, 0)
        names.append(name)
        if name not in order:
            new_names.append(name)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[cp] = name
    font.setGlyphOrder(order + new_names)
    glyf.glyphOrder = font.getGlyphOrder()
    return names

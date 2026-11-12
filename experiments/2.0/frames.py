"""2.0 experiment: each jamo as a frame of points and strokes, fitted to the drawn part.

A frame is a few points and the straight strokes between them, plus rings (ㅇ, the ring of
ㅎ) as ellipses, all in the part's box (0..1, y up). ㅁ is four corners and four sides
whether the designer joined its corners or not; ㄹ is six points on one path whether its
middle runs flat or slants. Fitting moves the points (and ellipses) so the strokes lie on
the skeleton of the drawn part and the skeleton lies on the strokes.

fit(contours, name) -> {"points": [(x, y)], "rings": [(cx, cy, rx, ry)], "err": ...}
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

ROOT = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT + "/tools")
import make_mono as M

PEN = 64


def F(points, strokes, rings=()):
    return {"p": points, "s": strokes, "r": list(rings)}


def chain(*pts):
    return F(list(pts), [(k, k + 1) for k in range(len(pts) - 1)])


def join(a, b):
    """Two frames as one: b's point numbers shifted past a's."""
    n = len(a["p"])
    return F(a["p"] + b["p"], a["s"] + [(i + n, j + n) for i, j in b["s"]], a["r"] + b["r"])


def placed(f, x0, y0, x1, y1):
    """A frame squeezed into the box (x0, y0)-(x1, y1) of the unit box."""
    sx, sy = x1 - x0, y1 - y0
    return F([(x0 + x * sx, y0 + y * sy) for x, y in f["p"]], list(f["s"]),
             [(x0 + cx * sx, y0 + cy * sy, rx * sx, ry * sy) for cx, cy, rx, ry in f["r"]])


C = {
    "ㄱ": chain((.05, .9), (.9, .9), (.6, .05)),
    "ㄴ": chain((.1, .95), (.1, .1), (.95, .1)),
    "ㄷ": chain((.95, .9), (.1, .9), (.1, .1), (.95, .1)),
    "ㄹ": chain((.1, .92), (.9, .92), (.9, .52), (.1, .52), (.1, .08), (.95, .08)),
    "ㅁ": F([(.1, .9), (.9, .9), (.9, .1), (.1, .1)], [(0, 1), (1, 2), (2, 3), (3, 0)]),
    "ㅂ": F([(.1, .95), (.1, .1), (.9, .1), (.9, .95), (.1, .5), (.9, .5)], [(0, 1), (1, 2), (2, 3), (4, 5)]),
    "ㅅ": F([(.5, .95), (.05, .05), (.4, .5), (.95, .08)], [(0, 1), (2, 3)]),
    "ㅇ": F([], [], [(.5, .5, .45, .45)]),
    "ㅈ": F([(.05, .9), (.8, .9), (.05, .05), (.5, .48), (.95, .08)], [(0, 1), (1, 2), (3, 4)]),
    "ㅋ": F([(.05, .9), (.9, .9), (.6, .05), (.1, .5), (.8, .5)], [(0, 1), (1, 2), (3, 4)]),
    "ㅌ": F([(.95, .92), (.1, .92), (.1, .08), (.95, .08), (.1, .5), (.85, .5)], [(0, 1), (1, 2), (2, 3), (4, 5)]),
    "ㅍ": F([(.02, .9), (.98, .9), (.3, .9), (.3, .1), (.7, .9), (.7, .1), (.02, .1), (.98, .1)],
           [(0, 1), (2, 3), (4, 5), (6, 7)]),
    "ㅎ": F([(.3, 1), (.7, .93), (.05, .78), (.95, .78)], [(0, 1), (2, 3)], [(.5, .3, .35, .3)]),
}
C["ㅊ"] = join(F([(.3, 1), (.7, .92)], [(0, 1)]), placed(C["ㅈ"], 0, 0, 1, .78))


def bar(y, x0=0.0, x1=1.0):
    return chain((x0, y), (x1, y))


def stem(x, y0=0.0, y1=1.0):
    return chain((x, y1), (x, y0))


def many(*fs):
    out = fs[0]
    for f in fs[1:]:
        out = join(out, f)
    return out


V = {
    "ㅏ": many(stem(.2), bar(.5, .2, .95)),
    "ㅐ": many(stem(.1, .1), bar(.5, .1, .6), stem(.9)),
    "ㅑ": many(stem(.2), bar(.65, .2, .95), bar(.35, .2, .95)),
    "ㅒ": many(stem(.1, .1), bar(.65, .1, .6), bar(.35, .1, .6), stem(.9)),
    "ㅓ": many(bar(.5, .05, .8), stem(.8)),
    "ㅔ": many(bar(.5, .05, .5), stem(.5, .1), stem(.9)),
    "ㅕ": many(bar(.65, .05, .8), bar(.35, .05, .8), stem(.8)),
    "ㅖ": many(bar(.65, .05, .5), bar(.35, .05, .5), stem(.5, .1), stem(.9)),
    "ㅗ": many(stem(.5, .1, 1), bar(.05)),
    "ㅛ": many(stem(.33, .1, 1), stem(.67, .1, 1), bar(.05)),
    "ㅜ": many(bar(.95), stem(.5, 0, .95)),
    "ㅠ": many(bar(.95), stem(.35, 0, .95), stem(.65, 0, .95)),
    "ㅡ": bar(.5),
    "ㅣ": stem(.5),
    "ㅘ": many(stem(.3, .1, .4), bar(.06, 0, .65), stem(.8), bar(.5, .8, 1)),
    "ㅙ": many(stem(.25, .1, .4), bar(.06, 0, .55), stem(.65, .05), bar(.5, .65, .8), stem(.95)),
    "ㅚ": many(stem(.35, .1, .4), bar(.06, 0, .75), stem(.92)),
    # read off 워 and 웨: ㅜ sits low at the left, ㅓ's bar is higher and short
    "ㅝ": many(bar(.36, 0, .64), stem(.34, 0, .36), bar(.57, .6, .95), stem(.95)),
    "ㅞ": many(bar(.35, 0, .52), stem(.25, 0, .35), bar(.5, .42, .72), stem(.72, .06, .97), stem(.97)),
    "ㅟ": many(bar(.6, 0, .7), stem(.35, .05, .6), stem(.9)),
    "ㅢ": many(bar(.15, 0, .75), stem(.92)),
}
FRAMES = dict(C, **V)
for dbl, one in (("ㄲ", "ㄱ"), ("ㄸ", "ㄷ"), ("ㅃ", "ㅂ"), ("ㅆ", "ㅅ"), ("ㅉ", "ㅈ")):
    FRAMES[dbl] = join(placed(C[one], 0, 0, .48, 1), placed(C[one], .52, 0, 1, 1))
for dbl, (a, b) in {"ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ",
                    "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ"}.items():
    FRAMES[dbl] = join(placed(C[a], 0, 0, .48, 1), placed(C[b], .52, 0, 1, 1))


TEMPLATE = dict(FRAMES)     # the hand-made frames, kept when learned ones replace FRAMES


def ink(contours):
    """The part's ink, one pixel per font unit, and where pixel (0, 0) is in font units."""
    import pathops
    from fontTools.pens.recordingPen import RecordingPen
    path = pathops.Path(); pen = path.getPen()
    for op, args in [o for c in contours for o in c]:
        getattr(pen, op)(*args)
    path.simplify(fix_winding=True)
    rec = RecordingPen(); path.draw(rec)
    flat = M.flattened(rec.value)
    b = M.bounds(flat)
    x0, y1 = b[0] - 40, b[3] + 40
    w, h = int(b[2] - b[0]) + 81, int(b[3] - b[1]) + 81
    acc = np.zeros((h, w), bool)
    for poly in M.polygon_points(flat):
        if len(poly) < 3:
            continue
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon([(x - x0, y1 - y) for x, y in poly], fill=255)
        acc ^= np.asarray(m) > 127
    return np.ascontiguousarray(acc), (x0, y1), b


def draw(points, strokes, rings, shape, off, width=PEN, bends=None):
    """A frame drawn with a round pen, as an ink mask like ink()'s."""
    h, w = shape
    img = Image.new("L", (w, h), 0); d = ImageDraw.Draw(img)
    px = lambda p: (p[0] - off[0], off[1] - p[1])
    r = width / 2
    for k, (i, j) in enumerate(strokes):
        Q = [px(q) for q in curve(points[i], points[j], bends[k] if bends is not None else 0.0)]
        d.line(Q, fill=255, width=int(width), joint="curve")
        for c in Q:
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=255)
    for cx, cy, rx, ry in rings:
        rx, ry = abs(rx), abs(ry)
        c = px((cx, cy))
        d.ellipse([c[0] - rx - r, c[1] - ry - r, c[0] + rx + r, c[1] + ry + r], fill=255)
        if rx > r and ry > r:
            d.ellipse([c[0] - rx + r, c[1] - ry + r, c[0] + rx - r, c[1] + ry - r], fill=0)
    return np.asarray(img) > 127


NB = int(__import__("os").environ.get("FRAME_BENDS", "1"))   # numbers per stroke's bend: 1 or 2


def curve(a, b, bend, n=6):
    """Points along a stroke from a to b. One number: a quadratic whose middle is pushed
    `bend` units to the stroke's left. Two numbers: a cubic whose controls sit at the
    thirds, pushed so that equal numbers bend the middle by that much."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    d = b - a
    L = max(np.hypot(*d), 1e-9)
    nrm = np.array([-d[1], d[0]]) / L
    t = np.linspace(0, 1, n + 1)[:, None]
    bend = np.atleast_1d(np.asarray(bend, float))
    if len(bend) == 1:
        c = (a + b) / 2 + nrm * 2 * bend[0]
        return (1 - t) ** 2 * a + 2 * t * (1 - t) * c + t * t * b
    c1 = a + d / 3 + nrm * 4 / 3 * bend[0]
    c2 = a + 2 * d / 3 + nrm * 4 / 3 * bend[1]
    return (1 - t) ** 3 * a + 3 * t * (1 - t) ** 2 * c1 + 3 * t * t * (1 - t) * c2 + t ** 3 * b


def poly_dist(P, Q):
    return np.min(np.vstack([seg_dist(P, Q[k], Q[k + 1]) for k in range(len(Q) - 1)]), axis=0)


def seg_dist(P, a, b):
    ab = b - a
    L2 = max(float(ab @ ab), 1e-9)
    t = np.clip(((P - a) @ ab) / L2, 0, 1)
    q = a + t[:, None] * ab
    return np.hypot(*(P - q).T)


def ring_dist(P, cx, cy, rx, ry):
    rx, ry = max(abs(rx), 5), max(abs(ry), 5)
    u = (P[:, 0] - cx) / rx; v = (P[:, 1] - cy) / ry
    rho = np.hypot(u, v)
    return np.abs(rho - 1) * min(rx, ry)


BEND_W = 0.3     # how strongly a bend is held back (per unit of bend)


def in_box(f, box):
    """A unit-box frame placed on centrelines inside the ink box (x0, y0, x1, y1)."""
    ix0, iy0 = box[0] + PEN / 2, box[1] + PEN / 2
    iw, ih = max(box[2] - box[0] - PEN, 10), max(box[3] - box[1] - PEN, 10)
    return F([(ix0 + x * iw, iy0 + y * ih) for x, y in f["p"]], list(f["s"]),
             [(ix0 + cx * iw, iy0 + cy * ih, rx * iw, ry * ih) for cx, cy, rx, ry in f["r"]])


def on_holes(m, off, rs):
    """Rings started on the holes of the ink: a ring takes the nearest hole whose centre
    is inside the ring as placed, grown by half, and fits round it. Each hole goes once."""
    if not len(rs):
        return rs
    lab, n = ndimage.label(~m)
    edge = set(lab[0]) | set(lab[-1]) | set(lab[:, 0]) | set(lab[:, -1])
    holes = []
    for k in range(1, n + 1):
        if k in edge:
            continue
        rr, cc = np.nonzero(lab == k)
        if len(rr) < 150:
            continue
        holes.append((off[0] + cc.mean(), off[1] - rr.mean(), (np.ptp(cc) + 1) / 2, (np.ptp(rr) + 1) / 2))
    rs = rs.copy()
    used = set()
    for k, (cx, cy, rx, ry) in enumerate(rs):
        best = None
        for h, (hx, hy, hw, hh) in enumerate(holes):
            u = np.hypot((hx - cx) / (1.5 * max(abs(rx), 20)), (hy - cy) / (1.5 * max(abs(ry), 20)))
            if h not in used and u < 1 and (best is None or u < best[0]):
                best = (u, h)
        if best:
            hx, hy, hw, hh = holes[best[1]]
            rs[k] = (hx, hy, hw + PEN / 2, hh + PEN / 2)
            used.add(best[1])
    return rs


PRIOR_W = 0.12    # residual per unit a point moves from where the box fit put it
RING_W = 0.4      # the same for a ring, which starts on its hole and so is trusted more


def fit_frame(contours, f, sample=3, units=None):
    """Moves frame f (in font units) onto the drawn ink, in three steps:
      1. each unit (a jamo's frame, `units` = [(first point, last point + 1, first ring,
         last ring + 1)]) only moves and scales as a whole,
      2. every point and ring moves, held near where step 1 put it,
      3. the strokes may bend as well."""
    m, off, b = ink(contours)
    sk = skeletonize(m)
    rc = np.argwhere(sk)
    # every k-th pixel in raster order would take the same column again and again (a
    # row crosses each vertical stroke once), so the sample is drawn at random instead
    n = min(len(rc), max(len(rc) // sample, 1), 300)
    rc = rc[np.sort(np.random.default_rng(0).choice(len(rc), n, replace=False))]
    if len(rc) < 5:
        return None
    P = np.column_stack([off[0] + rc[:, 1], off[1] - rc[:, 0]]).astype(float)
    whole_tree = cKDTree(P)
    np_, nr, ns = len(f["p"]), len(f["r"]), len(f["s"])
    if units is None:
        units = [(0, np_, 0, nr)]

    def on_skeleton(q):
        return whole_tree.query(q)[0]

    def pieces(pts, rs, bs):
        """Each stroke as points along it, each ring as 16 points round it."""
        out = [curve(pts[i], pts[j], bs[k * NB:(k + 1) * NB]) for k, (i, j) in enumerate(f["s"])]
        for cx, cy, rx, ry in rs:
            a = np.linspace(0, 2 * math.pi, 16, endpoint=False)
            out.append(np.column_stack([cx + rx * np.cos(a), cy + ry * np.sin(a)]))
        return out

    def dists(pts, rs, bs):
        ds = [poly_dist(P, Q) for Q in pieces(pts, rs, bs)[:ns]]
        ds += [ring_dist(P, *q) for q in rs]
        return np.vstack(ds)

    def match(pts, rs, bs, trees=None):
        """cover: each skeleton point to its nearest piece. along: each piece's points to
        the skeleton, or, given `trees`, to the skeleton points given to that piece only."""
        cover = np.min(dists(pts, rs, bs), axis=0)
        along = []
        for k, Q in enumerate(pieces(pts, rs, bs)):
            if trees is None or trees[k] is None:
                along.append(on_skeleton(Q))
            else:
                along.append(trees[k].query(Q)[0])
        return np.concatenate([cover] + along), len(cover)

    def assigned(pts, rs, bs):
        """The skeleton shared out: each point to its nearest piece. A piece with fewer
        than 3 points keeps the whole skeleton."""
        own = np.argmin(dists(pts, rs, bs), axis=0)
        trees = []
        for k in range(ns + nr):
            q = P[own == k]
            trees.append(cKDTree(q) if len(q) >= 3 else None)
        return trees

    pts0 = np.array(f["p"], float).reshape(-1, 2)
    rs0 = np.array(f["r"], float).reshape(-1, 4)
    zero = np.zeros(ns * NB)

    # 1. whole units: (dx, dy, log sx, log sy) each, about each unit's centre
    centres = []
    for a, z, ra, rz in units:
        q = [pts0[a:z]] + ([rs0[ra:rz, :2]] if rz > ra else [])
        q = np.vstack([x for x in q if len(x)])
        centres.append(q.mean(axis=0))

    def moved(x):
        pts, rs = pts0.copy(), rs0.copy()
        for u, (a, z, ra, rz) in enumerate(units):
            dx, dy, lx, ly = x[4 * u:4 * u + 4]
            sx, sy = math.exp(lx), math.exp(ly)
            c = centres[u]
            pts[a:z] = c + (pts0[a:z] - c) * (sx, sy) + (dx, dy)
            if rz > ra:
                rs[ra:rz, 0] = c[0] + (rs0[ra:rz, 0] - c[0]) * sx + dx
                rs[ra:rz, 1] = c[1] + (rs0[ra:rz, 1] - c[1]) * sy + dy
                rs[ra:rz, 2] *= sx; rs[ra:rz, 3] *= sy
        return pts, rs

    # coarse first (far ink still pulls), then fine
    x1 = np.zeros(4 * len(units))
    for fs in (40.0, 8.0):
        x1 = least_squares(lambda x: match(*moved(x), zero)[0], x1, loss="soft_l1", f_scale=fs, max_nfev=100).x
    s1 = type("S", (), {"x": x1})
    ptsA, rsA = moved(s1.x)
    rsA = on_holes(m, off, rsA)

    # 2. and 3. free points (and bends), held near step 1
    def unpack(x, with_bends):
        pts = x[:2 * np_].reshape(-1, 2)
        rs = x[2 * np_:2 * np_ + 4 * nr].reshape(-1, 4)
        bs = x[2 * np_ + 4 * nr:] if with_bends else zero
        return pts, rs, bs

    def resid(x, with_bends, trees):
        pts, rs, bs = unpack(x, with_bends)
        r, _ = match(pts, rs, bs, trees)
        prior = np.concatenate([PRIOR_W * (pts - ptsA).ravel(), RING_W * (rs - rsA).ravel()])
        return np.concatenate([r, prior] + ([BEND_W * bs] if with_bends else []))

    x = np.concatenate([ptsA.ravel(), rsA.ravel()])
    for _ in range(3):
        trees = assigned(*unpack(x, False))
        x = least_squares(lambda y: resid(y, False, trees), x, loss="soft_l1", f_scale=8.0, max_nfev=100).x
    x = np.concatenate([x, zero])
    for _ in range(2):
        trees = assigned(*unpack(x, True))
        x = least_squares(lambda y: resid(y, True, trees), x, loss="soft_l1", f_scale=8.0, max_nfev=100).x
    trees = assigned(*unpack(x, True))

    pts, rs, bs = unpack(x, True)
    r, n_cover = match(pts, rs, bs, trees)
    pts_l = [tuple(q) for q in pts]; rs_l = [tuple(q) for q in rs]
    bl = [float(v) for v in bs] if NB == 1 else [tuple(bs[k * NB:(k + 1) * NB]) for k in range(ns)]
    drawn = draw(pts_l, f["s"], rs_l, m.shape, off, bends=bl)
    iou = (m & drawn).sum() / max(1, (m | drawn).sum())
    return {"points": pts_l, "rings": rs_l, "bends": bl,
            "init": ([tuple(q) for q in ptsA], [tuple(q) for q in rsA]),
            "cover95": float(np.percentile(r[:n_cover], 95)),
            "along95": float(np.percentile(r[n_cover:], 95)), "iou": float(iou)}


def _segs_cross(a, b, c, d):
    """Segments ab and cd cross properly (not just touch at an end)."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and min(abs(o1), abs(o2), abs(o3), abs(o4)) > 1e-6


def crossings(points, strokes, bends=None, unit_of=None, trim=0.08):
    """Per unit, how many pairs of its strokes cross. Each stroke is trimmed by `trim` of
    its length at both ends, so strokes meeting at a corner or a branch do not count."""
    out = {}
    curves = []
    for k, (i, j) in enumerate(strokes):
        Q = curve(points[i], points[j], bends[k] if bends is not None else 0.0, n=12)
        n = len(Q); cut = max(1, int(round(trim * (n - 1))))
        curves.append(Q[cut:n - cut])
    for x in range(len(strokes)):
        for y in range(x + 1, len(strokes)):
            u = unit_of[x] if unit_of is not None else 0
            if unit_of is not None and unit_of[y] != u:
                continue
            A, B = curves[x], curves[y]
            hit = any(_segs_cross(A[i], A[i + 1], B[j], B[j + 1]) for i in range(len(A) - 1) for j in range(len(B) - 1))
            out[u] = out.get(u, 0) + int(hit)
    return out


TEMPLATE_CROSS = {}


def template_crossings(name):
    """How many crossing stroke pairs the jamo's hand-made frame has (ㅊ, ㅍ ... may have some)."""
    if name not in TEMPLATE_CROSS:
        f = TEMPLATE[name]
        TEMPLATE_CROSS[name] = crossings(np.array(f["p"], float) * 1000, f["s"]).get(0, 0)
    return TEMPLATE_CROSS[name]


def twisted(r, names):
    """Units of a syllable fit whose strokes cross more than their frame's do."""
    if not r or "strokes" not in r:
        return []
    c = crossings(np.array(r["points"]), r["strokes"], r["bends"], r["owner_s"])
    return [u for u, n in c.items() if n > template_crossings(names[u])]


def good(r):
    """A fit holds when the frame and the skeleton are within 25 units of each other
    (95th percentile both ways). IoU depends on the one pen width, so it only informs."""
    return bool(r) and "cover95" in r and r["cover95"] < 25 and r["along95"] < 25


def unit_boxes(r):
    """Each unit of a syllable fit as its ink box (centrelines' extent grown by half the
    pen) and its frame in that box, the form in_box() reads back."""
    out = []
    for n in sorted(set(r["owner_s"]) | set(r["owner_r"])):
        ss = [s for s, o in zip(r["strokes"], r["owner_s"]) if o == n]
        ids = sorted({i for s in ss for i in s})
        rs = [q for q, o in zip(r["rings"], r["owner_r"]) if o == n]
        xs = [r["points"][i][0] for i in ids] + [c - abs(a) for c, _, a, _ in rs] + [c + abs(a) for c, _, a, _ in rs]
        ys = [r["points"][i][1] for i in ids] + [c - abs(b) for _, c, _, b in rs] + [c + abs(b) for _, c, _, b in rs]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
        u = lambda x, y: ((x - x0) / w if x1 - x0 > 1 else .5, (y - y0) / h if y1 - y0 > 1 else .5)
        pts = [u(*r["points"][i]) for i in ids]
        frame = F(pts, [(ids.index(i), ids.index(j)) for i, j in ss],
                  [(*u(cx, cy), abs(rx) / w, abs(ry) / h) for cx, cy, rx, ry in rs])
        # bends, as a share of the box's larger side
        frame["b"] = [b / max(w, h) for b, o in zip(r["bends"], r["owner_s"]) if o == n]
        out.append((n, (x0 - PEN / 2, y0 - PEN / 2, x1 + PEN / 2, y1 + PEN / 2), frame))
    return out


def mean_frame(frames):
    """The average of frames of one jamo (same points, strokes and rings in order)."""
    f0 = frames[0]
    p = np.mean([np.array(f["p"], float).reshape(-1, 2) for f in frames], axis=0)
    r = np.mean([np.array(f["r"], float).reshape(-1, 4) for f in frames], axis=0)
    out = F([tuple(q) for q in p], list(f0["s"]), [tuple(q) for q in r])
    if all("b" in f for f in frames):
        out["b"] = list(np.mean([f["b"] for f in frames], axis=0))
    return out


def fit(contours, name, sample=3):
    """One jamo part fitted to its frame, started from the part's own box."""
    m, off, b = ink(contours)
    return fit_frame(contours, in_box(FRAMES[name], b), sample)


def fit_syllable(contours, parts, sample=3):
    """A whole syllable fitted at once. parts = [(jamo name, role, ink box)]; the frames
    start in those boxes. Returns the fit with "owner": the part each point, stroke and
    ring belongs to."""
    whole = F([], [], [])
    owner_p, owner_s, owner_r = [], [], []
    for n, (name, role, box) in enumerate(parts):
        g = in_box(FRAMES[name], box)
        whole = join(whole, g)
        owner_p += [n] * len(g["p"]); owner_s += [n] * len(g["s"]); owner_r += [n] * len(g["r"])
    units, a, ra = [], 0, 0
    for name, role, box in parts:
        g = FRAMES[name]
        units.append((a, a + len(g["p"]), ra, ra + len(g["r"])))
        a += len(g["p"]); ra += len(g["r"])
    out = fit_frame(contours, whole, sample, units)
    if out:
        out.update(strokes=whole["s"], owner_p=owner_p, owner_s=owner_s, owner_r=owner_r)
    return out

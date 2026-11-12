"""How closely the 2.0 way redraws the designer's own syllables: their fitted centrelines
stroked into real outlines (skia-pathops, round caps and joins, an elliptical pen made by
stroking in a y-stretched space), compared with the drawn ink (IoU).

Decisions added one at a time, each read off the drawn syllables:
  corner  where two strokes of a jamo meet at an angle, the centreline turns on a curve
          that starts `cut` units before the corner on both strokes
  ring    a ring is not an ellipse but a closed curve r(θ) (3 harmonics) fitted to the
          skeleton points around it
  pen     the pen width

usage: recon2.py audit_prep.pkl audit_fits2.pkl audit_prep_glyphs.pkl [step]"""
import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys, pickle, math
import numpy as np
from multiprocessing import Pool
import pathops
from fontTools.pens.recordingPen import RecordingPen
from PIL import Image, ImageDraw
import frames as FR, make_mono as M, hangul_fill as H

PREP, FITS, GLYPHS = sys.argv[1:4]
STEP = int(sys.argv[4]) if len(sys.argv) > 4 else 9
PR = pickle.load(open(PREP, "rb")); FT = pickle.load(open(FITS, "rb")); GL = pickle.load(open(GLYPHS, "rb"))
DRAWN = sorted(PR["_drawn"])
I = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"; V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
F = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


# ---- geometry -----------------------------------------------------------------------
def stroke_lines(r, cut=0.0):
    """Polylines of a fit's strokes. With cut > 0, where exactly two strokes of one unit
    share a point at a real angle (over 25°), both are trimmed by `cut` there and joined
    by a quadratic curve through the corner."""
    lines = [np.asarray(FR.curve(r["points"][i], r["points"][j], r["bends"][k], n=40)) for k, (i, j) in enumerate(r["strokes"])]
    if cut <= 0:
        return lines
    users = {}
    for k, (i, j) in enumerate(r["strokes"]):
        users.setdefault(i, []).append((k, 0)); users.setdefault(j, []).append((k, -1))
    extra = []
    trims = {}
    for p, us in users.items():
        if len(us) != 2:
            continue
        (k1, e1), (k2, e2) = us
        if r["owner_s"][k1] != r["owner_s"][k2]:
            continue
        A, B = lines[k1], lines[k2]
        a_dir = (A[1] - A[0]) if e1 == 0 else (A[-2] - A[-1])
        b_dir = (B[1] - B[0]) if e2 == 0 else (B[-2] - B[-1])
        cosang = a_dir @ b_dir / (np.hypot(*a_dir) * np.hypot(*b_dir) + 1e-9)
        if cosang > math.cos(math.radians(155)):        # turning more than 25 degrees
            pass
        else:
            continue
        pts = []
        for k, e in ((k1, e1), (k2, e2)):
            Q = lines[k]
            seg = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
            c = min(cut, 0.4 * seg[-1])
            if e == 0:
                t = np.searchsorted(seg, c); trims[(k, 0)] = t
                pts.append(Q[min(t, len(Q) - 1)])
            else:
                t = np.searchsorted(seg, seg[-1] - c); trims[(k, -1)] = t
                pts.append(Q[max(t, 0)])
        corner = np.asarray(r["points"][p], float)
        tt = np.linspace(0, 1, 16)[:, None]
        extra.append((1 - tt) ** 2 * pts[0] + 2 * tt * (1 - tt) * corner + tt * tt * pts[1])
    out = []
    for k, Q in enumerate(lines):
        a, b = trims.get((k, 0), 0), trims.get((k, -1), len(Q) - 1)
        out.append(Q[a:b + 1] if b > a else Q)
    return out + extra


def ring_lines(r, cp, free=False):
    out = []
    P = PR[cp]["P"]
    for cx, cy, rx, ry in r["rings"]:
        rx, ry = abs(rx), abs(ry)
        th = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        if free:
            u = (P[:, 0] - cx) / max(rx, 5); v = (P[:, 1] - cy) / max(ry, 5)
            rho = np.hypot(u, v)
            near = np.abs(rho - 1) < 0.35
            if near.sum() >= 12:
                ang = np.arctan2(P[near, 1] - cy, P[near, 0] - cx)
                rad = np.hypot(P[near, 0] - cx, P[near, 1] - cy)
                A = np.column_stack([np.ones_like(ang)] + [f(k * ang) for k in (1, 2, 3) for f in (np.cos, np.sin)])
                coef = np.linalg.solve(A.T @ A + 0.5 * np.eye(A.shape[1]), A.T @ rad)
                B = np.column_stack([np.ones_like(th)] + [f(k * th) for k in (1, 2, 3) for f in (np.cos, np.sin)])
                rr = B @ coef
                out.append(np.column_stack([cx + rr * np.cos(th), cy + rr * np.sin(th)])); continue
        out.append(np.column_stack([cx + rx * np.cos(th), cy + ry * np.sin(th)]))
    return out


# ---- the pen ------------------------------------------------------------------------
def outline(lines, rings, w, h):
    """Stroked outlines of open polylines and closed rings, pen w x h: one op list per
    piece (their union is left to the rasteriser, or to the font's overlap removal)."""
    s = w / h
    out = []
    for Q, closed in [(q, False) for q in lines] + [(q, True) for q in rings]:
        if len(Q) < 2:
            continue
        p = pathops.Path()
        p.moveTo(Q[0][0], Q[0][1] * s)
        for x, y in Q[1:]:
            p.lineTo(x, y * s)
        if closed:
            p.close()
        p.stroke(w, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
        p.convertConicsToQuads()
        try:
            p.simplify(fix_winding=True)       # a closed ring's stroke overlaps itself
        except Exception:
            pass
        rec = RecordingPen(); p.draw(rec)
        out.append([(op, tuple((x, y / s) for x, y in args)) for op, args in rec.value])
    return out


def raster(pieces, off, shape):
    """Union of the pieces, each filled even-odd on its own (a stroked piece's own
    contours already have the right winding)."""
    h, w = shape
    acc = np.zeros((h, w), bool)
    for ops in pieces:
        one = np.zeros((h, w), bool)
        for poly in M.polygon_points(M.flattened(ops)):
            if len(poly) < 3:
                continue
            m = Image.new("L", (w, h), 0)
            ImageDraw.Draw(m).polygon([(x - off[0], off[1] - y) for x, y in poly], fill=255)
            one ^= np.asarray(m) > 127
        acc |= one
    return acc


def refine(r, m, off, pen=64, iters=60):
    """The fit's points and bends moved so each stroke runs along the middle of its ink:
    stroke samples (ends left out) pulled to where the ink's distance transform peaks,
    the ends to cover the skeleton's ends. Small steps, held near the fit."""
    from scipy import ndimage
    from scipy.optimize import least_squares
    from skimage.morphology import skeletonize
    edt = ndimage.distance_transform_edt(m)
    sk = skeletonize(m)
    nb = ndimage.convolve(sk.astype(int), np.ones((3, 3)), mode="constant")
    er, ec = np.nonzero(sk & (nb == 2))
    tips = np.column_stack([off[0] + ec, off[1] - er]).astype(float)
    pts0 = np.array(r["points"], float); bs0 = np.array(r["bends"], float)
    S = r["strokes"]
    look = lambda q: ndimage.map_coordinates(edt, [off[1] - q[:, 1], q[:, 0] - off[0]], order=1, mode="nearest")
    ends = {i for i, j in S} | {j for i, j in S}
    deg = {}
    for i, j in S:
        deg[i] = deg.get(i, 0) + 1; deg[j] = deg.get(j, 0) + 1
    free_ends = [p for p in ends if deg[p] == 1]

    def resid(x):
        pts = x[:2 * len(pts0)].reshape(-1, 2); bs = x[2 * len(pts0):]
        out = []
        for k, (i, j) in enumerate(S):
            Q = np.asarray(FR.curve(pts[i], pts[j], bs[k], n=20))[3:-3]
            out.append(pen / 2 + 2 - look(Q))          # zero on the ridge of a 64 stroke
        if len(tips) and free_ends:
            for p in free_ends:
                d = np.hypot(*(tips - pts[p]).T).min()
                out.append([min(d, 60) * 0.5])
        out.append(0.15 * (pts - pts0).ravel()); out.append(0.15 * (bs - bs0))
        return np.concatenate(out)
    x0 = np.concatenate([pts0.ravel(), bs0])
    x = least_squares(resid, x0, loss="soft_l1", f_scale=4.0, max_nfev=iters).x
    r2 = dict(r)
    r2["points"] = [tuple(q) for q in x[:2 * len(pts0)].reshape(-1, 2)]
    r2["bends"] = list(x[2 * len(pts0):])
    return r2


def iou_of(cp, cut, free, pen, ridge=False):
    """pen: a width, or (across, up) for an elliptical pen."""
    r = FT.get(cp)
    if not r or "strokes" not in r:
        return None
    m, off, _ = FR.ink(GL[cp])
    w, h = (pen, pen) if np.isscalar(pen) else pen
    if ridge:
        r = refine(r, m, off, pen=(w + h) / 2)
    ops = outline(stroke_lines(r, cut), ring_lines(r, cp, free), w, h)
    d = raster(ops, off, m.shape)
    return float((m & d).sum() / max(1, (m | d).sum()))


SETTINGS = {"A 매끈한 펜 64": (0, False, 64)}


def job(args):
    cp, cut, free, pen = args[:4]
    return iou_of(cp, cut, free, pen, ridge=len(args) > 4 and args[4])


if __name__ == "__main__":
    sample = DRAWN[::STEP]
    trials = [("E round 64 + ridge", 0, True, 64, True), ("F ellipse 68x62", 0, True, (68, 62), True),
              ("F ellipse 70x62", 0, True, (70, 62), True), ("F ellipse 68x60", 0, True, (68, 60), True), ("F ellipse 66x62", 0, True, (66, 62), True)]
    with Pool(6) as pool:
        for name, c, fr, pen, rd in trials:
            vals = [v for v in pool.map(job, [(cp, c, fr, pen, rd) for cp in sample]) if v is not None]
            print(f"{name:22} median {np.median(vals):.3f}  p10 {np.percentile(vals, 10):.3f}  mean {np.mean(vals):.3f}", flush=True)
